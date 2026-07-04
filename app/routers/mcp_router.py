import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app import cache, database
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

_RE_CPU = re.compile(r"^(\d+)(n|u|m|)$")
_RE_MEM = re.compile(r"^(\d+)(Ki|Mi|Gi|k|M|G|)$")

_MEM_MULTIPLIER = {
    "Ki": 1 / 1024, "Mi": 1, "Gi": 1024,
    "k": 1 / 1024, "M": 1, "G": 1024, "": 1 / (1024 * 1024),
}


def _parse_cpu(val: str) -> int | None:
    """Parse K8s CPU value to millicores.
    '100m' -> 100, '1' -> 1000, '12345678n' -> 12, '500u' -> 0."""
    if not val:
        return None
    m = _RE_CPU.match(val.strip())
    if not m:
        return None
    n = int(m.group(1))
    suffix = m.group(2)
    if suffix == "n":
        return round(n / 1_000_000)
    if suffix == "u":
        return round(n / 1_000)
    if suffix == "m":
        return n
    return n * 1000


def _parse_mem(val: str) -> int | None:
    """Parse K8s memory value to MiB. '150Mi' -> 150, '1Gi' -> 1024."""
    if not val:
        return None
    m = _RE_MEM.match(val.strip())
    if not m:
        return None
    n = int(m.group(1))
    suffix = m.group(2)
    return round(n * _MEM_MULTIPLIER.get(suffix, 1))


def _health_status(pod: dict) -> str:
    """Rate-aware health: uses restarts/day so long-running pods with a few
    accumulated restarts aren't penalised the same as rapid crash-loops."""
    if pod["status"] != "up":
        return "critical"
    mem_pct = pod.get("memory_pct")
    if mem_pct is not None and mem_pct > 95:
        return "critical"

    restarts = pod["restarts"]
    age_hours = pod.get("age_hours") or 1
    rate_per_day = restarts / max(age_hours / 24, 0.042)

    if rate_per_day > 10:
        return "critical"
    if rate_per_day > 4:
        return "warning"

    if not pod["ready"]:
        return "warning"
    if mem_pct is not None and mem_pct > 80:
        return "warning"
    return "healthy"


_bg_status_collecting = set()

@router.get("/status")
async def mcp_status(days: int = Query(1)):
    """Return OCP pod health for all MCP tool deployments."""
    days = max(1, min(days, 3))
    cache_key = f"mcp:ocp_status_{days}"
    cached = cache.get(cache_key)
    if cached and cached.get("servers"):
        return cached

    if not cached or not cached.get("servers"):
        db_data = database.get_latest_snapshot("ocp_status")
        if db_data and isinstance(db_data, dict) and db_data.get("data"):
            raw = db_data["data"]
            if isinstance(raw, (list, tuple)) and len(raw) >= 4:
                try:
                    result = {"servers": raw[3], "summary": raw[4] if len(raw) > 4 else {}}
                    if result["servers"]:
                        cache.set(cache_key, result, ttl=300)
                        logger.info("OCP status restored from DB snapshot (%d servers)", len(result["servers"]))
                        return result
                except Exception:
                    pass
            elif isinstance(raw, dict) and raw.get("servers"):
                cache.set(cache_key, raw, ttl=300)
                logger.info("OCP status restored from DB snapshot (%d servers)", len(raw["servers"]))
                return raw

    if cache_key not in _bg_status_collecting:
        _bg_status_collecting.add(cache_key)
        import threading

        def _bg():
            try:
                _collect_ocp_server_status(days)
            except Exception as e:
                logger.error("Background OCP status collection failed: %s", e)
            finally:
                _bg_status_collecting.discard(cache_key)

        threading.Thread(target=_bg, daemon=True).start()

    return cached or {"servers": [], "summary": _empty_summary()}


def _collect_ocp_server_status(days: int = 1):
    import concurrent.futures
    from app.collectors.ocp_mcp_collector import (
        _get_ocp_config, _session, _discover_pods,
    )

    cfg = _get_ocp_config()
    if not cfg["token"]:
        logger.warning("OCP status: no OCP_TOKEN configured — cannot collect pod health")
        return {"servers": [], "summary": _empty_summary()}

    sess = _session(cfg["token"])
    try:
        test_resp = sess.get(f"{cfg['api_url']}/api/v1/namespaces", timeout=10)
        if test_resp.status_code in (401, 403):
            logger.error("OCP status: token expired or forbidden (HTTP %d) — run refresh-ocp-token.sh", test_resp.status_code)
            return {"servers": [], "summary": _empty_summary()}
    except Exception as e:
        logger.error("OCP status: cannot reach API at %s — %s", cfg['api_url'], e)
        return {"servers": [], "summary": _empty_summary()}

    servers = []
    stats_cache_key = f"mcp_stats_{days}"
    stats_data = cache.get(stats_cache_key) or {}
    app_counts = {a["name"]: a["count"] for a in stats_data.get("by_application", [])}

    def _collect_tool_pods(tool):
        tool_servers = []
        tool_sess = _session(cfg["token"])
        pods = _discover_pods(tool_sess, cfg["api_url"], tool)
        for pod in pods:
            pod_detail = _fetch_pod_detail(tool_sess, cfg["api_url"], pod)
            metrics = _fetch_pod_metrics(tool_sess, cfg["api_url"], pod)
            pod_detail.update(metrics)
            if pod_detail.get("memory_limit") and pod_detail.get("memory_mib"):
                pod_detail["memory_pct"] = round(
                    pod_detail["memory_mib"] / pod_detail["memory_limit"] * 100, 1
                )
            pod_detail["health"] = _health_status(pod_detail)
            pod_detail["tool"] = tool
            pod_detail["request_count"] = app_counts.get(tool, 0)
            tool_servers.append(pod_detail)
        return tool_servers

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cfg["tools"])) as pool:
        futures = {pool.submit(_collect_tool_pods, t): t for t in cfg["tools"]}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=120):
                try:
                    servers.extend(future.result())
                except Exception as e:
                    logger.error("Tool pod collection failed for %s: %s", futures[future], e)
        except concurrent.futures.TimeoutError:
            finished = sum(1 for f in futures if f.done())
            logger.warning("OCP status timed out: %d/%d tools — caching partial", finished, len(futures))

    up = sum(1 for s in servers if s["status"] == "up")
    down = len(servers) - up
    healthy = sum(1 for s in servers if s.get("health") == "healthy")
    warning = sum(1 for s in servers if s.get("health") == "warning")
    critical = sum(1 for s in servers if s.get("health") == "critical")
    _seen_tools: dict[str, int] = {}
    for s in servers:
        _seen_tools.setdefault(s["tool"], s["request_count"])
    total_req = sum(_seen_tools.values())
    unique_tools = len(set(s["tool"] for s in servers))
    total_cpu = sum(s.get("cpu_millicores") or 0 for s in servers)
    total_mem = sum(s.get("memory_mib") or 0 for s in servers)
    total_restarts = sum(s.get("restarts", 0) for s in servers)

    summary = {
        "servers_up": up,
        "servers_down": down,
        "total_pods": len(servers),
        "healthy_pods": healthy,
        "warning_pods": warning,
        "critical_pods": critical,
        "total_requests": total_req,
        "total_tool_calls": total_req,
        "tools_active": unique_tools,
        "total_cpu_millicores": total_cpu,
        "total_memory_mib": total_mem,
        "total_restarts": total_restarts,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    result = {"servers": servers, "summary": summary}
    if servers:
        cache.set(f"mcp:ocp_status_{days}", result, ttl=900)
        try:
            database.save_snapshot("ocp_status", {"servers": servers, "summary": summary})
        except Exception as e:
            logger.error("Failed to persist OCP status snapshot: %s", e)
        try:
            from app.alerting import check_and_alert, check_resolved
            check_and_alert(servers)
            check_resolved(servers)
        except Exception as e:
            logger.error("Alerting check failed: %s", e)
    else:
        cache.set(f"mcp:ocp_status_{days}", result, ttl=30)
        logger.warning("OCP status: no pods found for any tool — caching for 30s only")
    return result


def _fetch_pod_detail(sess, api_url, pod):
    url = f"{api_url}/api/v1/namespaces/{pod['namespace']}/pods/{pod['name']}"
    detail = {
        "name": pod["name"],
        "namespace": pod["namespace"],
        "container": pod["container"],
        "host": f"{pod['namespace']}/{pod['name']}",
        "port": 8000,
        "status": "down",
        "restarts": 0,
        "age": "",
        "ready": False,
        "cpu_limit": None,
        "cpu_request": None,
        "memory_limit": None,
        "memory_request": None,
        "latency_ms": None,
        "error_count": 0,
        "request_count": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            return detail
        data = resp.json()
        phase = data.get("status", {}).get("phase", "Unknown")
        detail["status"] = "up" if phase == "Running" else "down"

        containers_status = data.get("status", {}).get("containerStatuses", [])
        for cs in containers_status:
            if cs.get("name") == pod["container"] or pod["container"] in cs.get("name", ""):
                detail["restarts"] = cs.get("restartCount", 0)
                detail["ready"] = cs.get("ready", False)
                break

        for c_spec in data.get("spec", {}).get("containers", []):
            if c_spec.get("name") == pod["container"] or pod["container"] in c_spec.get("name", ""):
                limits = c_spec.get("resources", {}).get("limits", {})
                requests = c_spec.get("resources", {}).get("requests", {})
                detail["cpu_limit"] = _parse_cpu(limits.get("cpu", ""))
                detail["cpu_request"] = _parse_cpu(requests.get("cpu", ""))
                detail["memory_limit"] = _parse_mem(limits.get("memory", ""))
                detail["memory_request"] = _parse_mem(requests.get("memory", ""))
                break

        created = data.get("metadata", {}).get("creationTimestamp", "")
        if created:
            try:
                ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - ct
                days = delta.days
                hours = delta.seconds // 3600
                detail["age"] = f"{days}d {hours}h" if days else f"{hours}h"
                detail["age_hours"] = round(delta.total_seconds() / 3600, 1)
            except Exception:
                detail["age"] = created
    except Exception as e:
        logger.error("Failed to fetch pod detail %s/%s: %s", pod["namespace"], pod["name"], e)
    return detail


def _fetch_pod_metrics(sess, api_url, pod) -> dict:
    """Fetch live CPU/memory usage from the Kubernetes Metrics API."""
    url = f"{api_url}/apis/metrics.k8s.io/v1beta1/namespaces/{pod['namespace']}/pods/{pod['name']}"
    result = {"cpu_millicores": None, "memory_mib": None, "memory_pct": None}
    try:
        resp = sess.get(url, timeout=10)
        if resp.status_code != 200:
            return result
        data = resp.json()
        for c in data.get("containers", []):
            if c.get("name") == pod["container"] or pod["container"] in c.get("name", ""):
                usage = c.get("usage", {})
                raw_cpu = usage.get("cpu", "")
                raw_mem = usage.get("memory", "")
                logger.info("Metrics API raw for %s: cpu=%s mem=%s", pod["name"], raw_cpu, raw_mem)
                result["cpu_millicores"] = _parse_cpu(raw_cpu)
                result["memory_mib"] = _parse_mem(raw_mem)
                break
    except Exception as e:
        logger.debug("Metrics API unavailable for %s/%s: %s", pod["namespace"], pod["name"], e)
    return result


def _empty_summary():
    return {
        "servers_up": 0, "servers_down": 0, "total_pods": 0,
        "healthy_pods": 0, "warning_pods": 0, "critical_pods": 0,
        "total_requests": 0, "total_tool_calls": 0, "tools_active": 0,
        "total_cpu_millicores": 0, "total_memory_mib": 0, "total_restarts": 0,
    }


@router.get("/metrics")
async def mcp_metrics():
    cached = cache.get("mcp:ocp_status_1")
    if cached:
        return cached.get("summary", _empty_summary())
    return _empty_summary()


@router.get("/tools")
async def mcp_tools():
    data = cache.get("mcp:tools")
    return {"tools": data or []}
