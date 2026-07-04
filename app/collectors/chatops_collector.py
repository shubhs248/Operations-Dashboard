"""Collector that proxies ChatOps Analytics API endpoints and caches results.

Uses K8s pod proxy via the OCP API on the aiops403 cluster.
Requires OCP_ChatOps_TOKEN to be configured.
"""
import logging
import time

import requests
import urllib3

from app import cache, database
from app.config import get_settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

_pod_name_cache: dict = {"name": None, "ts": 0}
_POD_CACHE_TTL = 300

_proxy_format_cache: dict = {"fmt": None}

_PROXY_FORMATS = [
    "{api}/api/v1/namespaces/{ns}/pods/{pod}:8080/proxy{path}",
    "{api}/api/v1/namespaces/{ns}/pods/http:{pod}:8080/proxy{path}",
    "{api}/api/v1/namespaces/{ns}/pods/{pod}/proxy{path}",
    "{api}/api/v1/namespaces/{ns}/services/chatops-analytics-api:8080/proxy{path}",
    "{api}/api/v1/namespaces/{ns}/services/chatops-analytics-api/proxy{path}",
]


def _get_chatops_token() -> str:
    from app import ocp_token_manager
    token = ocp_token_manager.get_chatops_token()
    if token:
        return token
    return get_settings().ocp_chatops_token


def _ocp_session():
    token = _get_chatops_token()
    s = requests.Session()
    s.verify = False
    s.trust_env = False
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def _discover_analytics_pod() -> str | None:
    """Find the running chatops-analytics-api pod in the ChatOps namespace."""
    now = time.time()
    if _pod_name_cache["name"] and (now - _pod_name_cache["ts"]) < _POD_CACHE_TTL:
        return _pod_name_cache["name"]

    settings = get_settings()
    api_url = settings.ocp_chatops_api_url.rstrip("/")
    ns = settings.ocp_chatops_namespace
    sess = _ocp_session()

    url = f"{api_url}/api/v1/namespaces/{ns}/pods"
    try:
        resp = sess.get(url, timeout=30)
        if resp.status_code in (401, 403):
            logger.error("ChatOps OCP token invalid (HTTP %d) for namespace %s", resp.status_code, ns)
            return None
        resp.raise_for_status()
        pods = resp.json().get("items", [])
        for pod in pods:
            name = pod.get("metadata", {}).get("name", "")
            phase = pod.get("status", {}).get("phase", "")
            if phase == "Running" and name.startswith("chatops-analytics-api"):
                _pod_name_cache["name"] = name
                _pod_name_cache["ts"] = now
                logger.info("Discovered ChatOps analytics pod: %s/%s", ns, name)
                return name
        logger.warning("No running chatops-analytics-api pod found in %s", ns)
    except Exception as e:
        logger.error("Failed to discover ChatOps pods in %s: %s", ns, e)
    return None


def _proxy_get(path: str, timeout: int = 30):
    """GET an analytics-api endpoint through the K8s proxy.
    Auto-discovers the working URL format on first call."""
    token = _get_chatops_token()
    if not token:
        logger.warning("No ChatOps token available — ChatOps data unavailable")
        return None

    settings = get_settings()
    pod = _discover_analytics_pod()
    if not pod:
        return None

    api_url = settings.ocp_chatops_api_url.rstrip("/")
    ns = settings.ocp_chatops_namespace
    sess = _ocp_session()

    if _proxy_format_cache["fmt"]:
        url = _proxy_format_cache["fmt"].format(api=api_url, ns=ns, pod=pod, path=path)
        try:
            resp = sess.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("ChatOps proxy (cached fmt) %s returned %d — retrying all formats", path, resp.status_code)
            _proxy_format_cache["fmt"] = None
        except Exception as e:
            logger.warning("ChatOps proxy (cached fmt) %s error: %s — retrying all formats", path, e)
            _proxy_format_cache["fmt"] = None

    for fmt in _PROXY_FORMATS:
        url = fmt.format(api=api_url, ns=ns, pod=pod, path=path)
        try:
            resp = sess.get(url, timeout=timeout)
            if resp.status_code == 200:
                _proxy_format_cache["fmt"] = fmt
                logger.info("ChatOps proxy format discovered: %s", fmt)
                return resp.json()
            logger.debug("ChatOps proxy attempt %d for %s: %s", resp.status_code, path, url)
        except Exception as e:
            logger.debug("ChatOps proxy attempt failed for %s: %s", url, e)

    logger.error("All ChatOps proxy formats failed for %s (pod=%s)", path, pod)
    _pod_name_cache["name"] = None
    _pod_name_cache["ts"] = 0
    return None


def diagnose() -> dict:
    """Run a full diagnostic check and return results (never cached)."""
    settings = get_settings()
    token = _get_chatops_token()
    result = {
        "ocp_chatops_token_set": bool(token),
        "ocp_chatops_api_url": settings.ocp_chatops_api_url,
        "ocp_chatops_namespace": settings.ocp_chatops_namespace,
        "pod_discovery": None,
        "proxy_attempts": [],
        "working_format": _proxy_format_cache.get("fmt"),
    }

    if not token:
        result["error"] = "No ChatOps token — set OCP_ChatOps_TOKEN or OCP_ChatOps_SA_USER/PASSWORD"
        return result

    sess = _ocp_session()
    api_url = settings.ocp_chatops_api_url.rstrip("/")
    ns = settings.ocp_chatops_namespace

    list_url = f"{api_url}/api/v1/namespaces/{ns}/pods"
    try:
        resp = sess.get(list_url, timeout=15)
        result["pod_discovery"] = {
            "url": list_url,
            "status": resp.status_code,
        }
        if resp.status_code == 200:
            pods = resp.json().get("items", [])
            running = [
                p.get("metadata", {}).get("name", "")
                for p in pods
                if p.get("status", {}).get("phase") == "Running"
            ]
            result["pod_discovery"]["running_pods"] = running
        else:
            result["pod_discovery"]["body"] = resp.text[:500]
    except Exception as e:
        result["pod_discovery"] = {"error": str(e)}
        return result

    pod = None
    for name in result["pod_discovery"].get("running_pods", []):
        if name.startswith("chatops-analytics-api"):
            pod = name
            break

    if not pod:
        result["error"] = "No running chatops-analytics-api pod found"
        return result

    result["target_pod"] = pod
    test_path = "/api/health"

    for fmt in _PROXY_FORMATS:
        url = fmt.format(api=api_url, ns=ns, pod=pod, path=test_path)
        attempt = {"format": fmt, "url": url}
        try:
            resp = sess.get(url, timeout=15)
            attempt["status"] = resp.status_code
            attempt["body_preview"] = resp.text[:200] if resp.status_code != 200 else "(ok)"
            if resp.status_code == 200:
                attempt["success"] = True
        except Exception as e:
            attempt["error"] = str(e)
        result["proxy_attempts"].append(attempt)

    return result


def _fetch_and_persist(data_type: str, api_path: str, env: str = "production"):
    """Shared helper: check cache -> fetch upstream -> persist to DB -> fallback to DB."""
    cache_key = f"chatops:{data_type}:{env}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    data = _proxy_get(api_path)
    if data:
        cache.set(cache_key, data, ttl=300)
        try:
            database.save_chatops_snapshot(data_type, env, data)
        except Exception as e:
            logger.error("Failed to persist ChatOps %s snapshot: %s", data_type, e)
        return data

    db_data = database.get_chatops_snapshot(data_type, env)
    if db_data:
        cache.set(cache_key, db_data, ttl=120)
        logger.info("ChatOps %s restored from DB snapshot", data_type)
        return db_data

    return None


def get_summary(env: str = "production"):
    return _fetch_and_persist("data", "/api/data", env)


def get_activity(env: str = "production"):
    return _fetch_and_persist("activity", "/api/activity", env)


def get_channels(env: str = "production"):
    return _fetch_and_persist("channels", "/api/channel-stats", env)


def get_mcp(env: str = "production"):
    return _fetch_and_persist("mcp", "/api/mcp-stats", env)


def get_health():
    """Build service health: ChatOps API liveness + OCP pod status."""
    cache_key = "chatops:health"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = {"services": [], "pod": None}

    basic = _proxy_get("/api/health", timeout=10)
    api_ok = basic is not None and basic.get("status") in ("ok", "healthy")
    result["services"].append(
        {"name": "ChatOps Analytics API", "env": "prod", "status": "ok" if api_ok else "down"}
    )

    pod_info = _get_chatops_pod_status()
    if pod_info:
        result["pod"] = pod_info
        result["services"].append({
            "name": "ChatOps Pod",
            "env": "prod",
            "status": pod_info.get("phase", "Unknown"),
            "restarts": pod_info.get("restarts", 0),
            "ready": pod_info.get("ready", False),
            "age": pod_info.get("age", ""),
        })

    cache.set(cache_key, result, ttl=120)
    return result


def _get_chatops_pod_status() -> dict | None:
    """Get detailed status for the chatops-analytics-api pod from OCP."""
    token = _get_chatops_token()
    if not token:
        return None

    settings = get_settings()
    api_url = settings.ocp_chatops_api_url.rstrip("/")
    ns = settings.ocp_chatops_namespace
    sess = _ocp_session()

    url = f"{api_url}/api/v1/namespaces/{ns}/pods"
    try:
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        pods = resp.json().get("items", [])
        for pod in pods:
            name = pod.get("metadata", {}).get("name", "")
            if not name.startswith("chatops-analytics-api"):
                continue

            status = pod.get("status", {})
            phase = status.get("phase", "Unknown")
            containers = status.get("containerStatuses", [])

            restarts = 0
            ready = True
            for c in containers:
                restarts += c.get("restartCount", 0)
                if not c.get("ready", False):
                    ready = False

            creation = pod.get("metadata", {}).get("creationTimestamp", "")
            age = ""
            if creation:
                from datetime import datetime, timezone
                try:
                    created = datetime.fromisoformat(creation.replace("Z", "+00:00"))
                    delta = datetime.now(timezone.utc) - created
                    days = delta.days
                    hours = delta.seconds // 3600
                    if days > 0:
                        age = f"{days}d {hours}h"
                    else:
                        age = f"{hours}h {(delta.seconds % 3600) // 60}m"
                except Exception:
                    age = creation

            return {
                "name": name,
                "phase": phase,
                "restarts": restarts,
                "ready": ready,
                "age": age,
            }
    except Exception as e:
        logger.warning("Failed to get ChatOps pod status: %s", e)
    return None
