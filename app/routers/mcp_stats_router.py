"""API endpoints for MCP usage statistics — OCP pod logs (primary) or Grafana ES (fallback)."""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

from app import cache
from app.config import get_settings
from app.collectors.mcp_stats_collector import collect_mcp_stats
from app.collectors.ocp_mcp_collector import (
    collect_ocp_mcp_stats, _get_ocp_config, _session, _discover_pods,
    _fetch_pod_logs, _parse_logs,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_period(days: int = None, date_from: str = None, date_to: str = None) -> int:
    if date_from and date_to:
        try:
            d1 = datetime.strptime(date_from, "%Y-%m-%d")
            d2 = datetime.strptime(date_to, "%Y-%m-%d")
            return max(1, (d2 - d1).days)
        except ValueError:
            pass
    return days or 1


_bg_collecting = set()

_FALLBACK_TOOL_FUNCTIONS = {
    "jenkins": {
        "get_username", "jenkins_build_log_snapshot", "jenkins_build_multibranch_job",
        "jenkins_builds", "jenkins_connect", "jenkins_debug_headers",
        "jenkins_get_multibranch_job_info", "jenkins_jobs", "jenkins_list_branches",
        "jenkins_nodes", "jenkins_queue", "jenkins_views", "list_jenkins_servers",
    },
    "nexus": {
        "check_filesystem_space", "create_task", "get_repository_info",
        "get_system_status", "invalidate_cache", "list_repositories",
        "manage_session", "manage_task", "rebuild_index", "search_artifacts",
        "trace_proxy_chain", "update_task",
    },
    "bitbucket": {
        "audit_user_security", "compare_refs", "detect_code_antipatterns",
        "detect_dependency_changes", "find_large_files", "get_commit_details",
        "get_content_of_file", "get_mirror_status", "get_project_overview",
        "get_repository_id", "get_user_profile", "health_check",
        "lint_commit_messages", "manage_branches", "manage_pull_requests",
        "manage_repos", "manage_webhooks", "pr_analytics",
        "scan_pr_secrets", "search_bitbucket", "search_users",
        "create_pull_request", "get_branches", "get_commits",
        "get_content_of_file_bulk", "get_diff", "get_project",
        "get_project_id", "get_projects", "get_pull_request_activities",
        "get_pull_request_by_id", "get_pull_request_changes",
        "get_pull_requests", "get_repo", "get_repos",
    },
    "artifactory": {
        "artifactory_aql_query", "artifactory_cleanup_policy", "artifactory_delete",
        "artifactory_federated_sync", "artifactory_get", "artifactory_logs",
        "artifactory_rb_duplicates", "artifactory_search", "artifactory_worker_manage",
    },
    "ocp": {
        "delete_namespace", "get_adm_top_nodes_utilization", "get_adm_top_pods_utilization",
        "get_cert_ed_ver", "get_cluster_daily_grades", "get_cluster_information",
        "get_cpu_ram_requests_limits_per_namespace", "get_cpu_ram_requests_limits_per_pod",
        "get_current_cluster_state", "get_ed_version", "get_esxi",
        "get_helm_charts_ms360_details", "get_mcp_state", "get_nodes",
        "get_not_running_pods", "get_ocp_ceritification_details", "get_operators_state",
        "get_physical_cpu_utilization", "get_physical_memory_utilization",
        "get_user_ldap_groups", "oc_list_clusters", "oc_login", "oc_logout", "oc_run",
    },
    "eaas": {
        "add_sudo_permissions", "check_vapp_expiration", "check_vm_connectivity",
        "check_vm_rh_registration", "consolidate_template_disks", "consolidate_vm_disks",
        "copy_catalog_templates", "create_catalog", "create_catalog_item_from_vapp",
        "create_vapp_from_template", "delete_catalog", "delete_template_from_catalog",
        "delete_vapp", "exit_maintenance_mode_vapp", "find_vapp_by_ip",
        "get_all_organizations", "get_catalogs", "get_external_ips_from_vapps",
        "get_local_templates", "get_org", "get_org_resources",
        "get_subscription_catalogs", "get_vapps", "get_vm_filesystem_utilization",
        "get_vm_logs_and_diagnostics", "get_vm_performance_metrics",
        "increase_vm_filesystem", "list_dr_templates", "modify_cpu_for_vm",
        "modify_memory_for_vm", "power_off_vapp", "power_on_vapp",
        "register_vm_to_satellite", "reset_vapp_lease",
    },
}


def _filter_for_tool(combined: dict, tool: str) -> dict:
    """Derive tool-specific stats from the combined cached data instantly.

    Function-to-tool resolution order:
      1. Dynamic ``func_tool_map`` from OCP pod log parsing (auto-detected)
      2. Static ``_FALLBACK_TOOL_FUNCTIONS`` (cold-cache safety net only)
    New tools/functions are picked up automatically once they appear in logs.
    """
    tool_lower = tool.lower()
    server_map = combined.get("func_tool_map", {})
    fallback_fns = _FALLBACK_TOOL_FUNCTIONS.get(tool_lower, set())

    def _fn_matches(fn_name: str) -> bool:
        fn = fn_name.lower()
        mapped = server_map.get(fn) or server_map.get(fn_name)
        if mapped and mapped.lower() == tool_lower:
            return True
        if fn in fallback_fns or fn_name in fallback_fns:
            return True
        return False

    app_count = 0
    for app in combined.get("by_application", []):
        if app["name"].lower() == tool_lower:
            app_count = app["count"]
            break

    filtered_functions = [
        f for f in combined.get("by_function", []) if _fn_matches(f["name"])
    ]

    all_uf = combined.get("all_user_functions", {})
    filtered_users = []
    for user in combined.get("top_users", []):
        uname = user["username"]
        full_fns = all_uf.get(uname, {})
        matching = {fn: c for fn, c in full_fns.items() if _fn_matches(fn)}
        if not matching:
            user_fns = [f for f in user.get("top_functions", []) if _fn_matches(f["name"])]
            matching = {f["name"]: f["count"] for f in user_fns}
        user_count = sum(matching.values())
        if user_count > 0:
            sorted_fns = sorted(matching.items(), key=lambda x: x[1], reverse=True)[:5]
            filtered_users.append({
                "username": uname,
                "count": user_count,
                "top_functions": [
                    {"name": fn, "count": c,
                     "pct": round(c / user_count * 100, 1) if user_count else 0}
                    for fn, c in sorted_fns
                ],
                "tools_used": [tool_lower],
            })
    filtered_users.sort(key=lambda u: u["count"], reverse=True)

    daily = []
    for d in combined.get("daily_users", []):
        tool_reqs = (d.get("by_tool") or {}).get(tool_lower, 0)
        daily.append({
            "date": d["date"],
            "users": d["users"] if tool_reqs else 0,
            "requests": tool_reqs,
            "by_tool": {tool_lower: tool_reqs},
        })

    return {
        "collected_at": combined.get("collected_at"),
        "period_days": combined.get("period_days"),
        "total_requests": app_count,
        "total_tool_calls": app_count,
        "daily_users": daily,
        "by_application": [{"name": tool_lower, "count": app_count}] if app_count else [],
        "by_function": filtered_functions,
        "top_users": filtered_users,
        "func_tool_map": combined.get("func_tool_map", {}),
    }


def _get_data(days: int, application: str = ""):
    """Return cached data instantly. If cache is empty, kick off background
    collection and return empty dict so the API never blocks the event loop.
    For tool-filtered requests, derive from combined cache instantly."""
    suffix = f"_{application}" if application else ""
    cache_key = f"mcp_stats_{days}{suffix}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if application:
        combined = cache.get(f"mcp_stats_{days}")
        if combined:
            return _filter_for_tool(combined, application)

    base_key = f"mcp_stats_{days}"
    if base_key not in _bg_collecting:
        _bg_collecting.add(base_key)
        import threading

        def _bg():
            try:
                from app import ocp_token_manager
                settings = get_settings()
                token = ocp_token_manager.get_token() or settings.ocp_token
                if token:
                    collect_ocp_mcp_stats(days=days, cache_key=base_key)
                else:
                    collect_mcp_stats(days=days, cache_key=base_key)
            except Exception as exc:
                logger.error("Background MCP stats collection failed: %s", exc)
            finally:
                _bg_collecting.discard(base_key)

        threading.Thread(target=_bg, daemon=True).start()
        logger.info("Background collection started for %s", base_key)

    return {}


@router.get("/summary")
async def mcp_stats_summary(
    days: int = Query(None),
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    application: str = Query("", alias="app"),
):
    period = _resolve_period(days, date_from, date_to)
    data = _get_data(period, application)
    if not data:
        return {"error": "No MCP stats data available yet", "total_requests": 0}

    return {
        "total_requests": data.get("total_requests", 0),
        "total_tool_calls": data.get("total_tool_calls", 0),
        "period_days": data.get("period_days", period),
        "collected_at": data.get("collected_at"),
        "unique_users": len(data.get("top_users", [])),
        "unique_applications": len(data.get("by_application", [])),
        "unique_functions": len(data.get("by_function", [])),
    }


@router.get("/daily")
async def mcp_stats_daily(
    days: int = Query(None),
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    application: str = Query("", alias="app"),
):
    period = _resolve_period(days, date_from, date_to)
    data = _get_data(period, application)
    return {"daily": data.get("daily_users", []) if data else []}


@router.get("/applications")
async def mcp_stats_by_application(
    days: int = Query(None),
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
):
    period = _resolve_period(days, date_from, date_to)
    data = _get_data(period)
    return {"applications": data.get("by_application", []) if data else []}


@router.get("/functions")
async def mcp_stats_by_function(
    days: int = Query(None),
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    application: str = Query("", alias="app"),
):
    period = _resolve_period(days, date_from, date_to)
    data = _get_data(period, application)
    return {"functions": data.get("by_function", []) if data else []}


@router.get("/discover")
async def mcp_discover_tools():
    """Diagnostic: show which OCP namespaces/pods are reachable per tool, including log access test."""
    from app.collectors.ocp_mcp_collector import _fetch_pod_logs
    cfg = _get_ocp_config()
    if not cfg["token"]:
        return {"error": "OCP token not configured"}
    sess = _session(cfg["token"])
    result = {}
    for tool in cfg["tools"]:
        pods = _discover_pods(sess, cfg["api_url"], tool)
        pod_info = []
        for p in pods:
            log_url = (
                f"{cfg['api_url']}/api/v1/namespaces/{p['namespace']}/pods/{p['name']}/log"
                f"?container={p['container']}&tailLines=5"
            )
            try:
                resp = sess.get(log_url, timeout=15)
                log_status = resp.status_code
                log_lines = len(resp.text.splitlines()) if resp.status_code == 200 else 0
            except Exception as e:
                log_status = f"error: {e}"
                log_lines = 0
            pod_info.append({
                "name": p["name"], "namespace": p["namespace"], "container": p["container"],
                "log_access": log_status, "log_lines_sample": log_lines,
            })
        result[tool] = {"pods_found": len(pods), "pods": pod_info}
    return {"tools": result, "ocp_api_url": cfg["api_url"]}


@router.get("/users")
async def mcp_stats_top_users(
    days: int = Query(None),
    date_from: str = Query(None, alias="from"),
    date_to: str = Query(None, alias="to"),
    application: str = Query("", alias="app"),
):
    period = _resolve_period(days, date_from, date_to)
    data = _get_data(period, application)
    return {
        "users": data.get("top_users", []) if data else [],
        "func_tool_map": data.get("func_tool_map", {}) if data else {},
    }


@router.get("/diagnostics")
async def mcp_diagnostics(days: int = Query(1)):
    """Real-time diagnostic snapshot: pod age, restarts, log volume, and parsed
    event counts per tool.  Never cached -- always runs fresh queries."""
    days = max(1, min(days, 3))
    cfg = _get_ocp_config()
    if not cfg["token"]:
        return {"error": "OCP token not configured"}

    sess = _session(cfg["token"])
    since_seconds = days * 86400
    cutoff = datetime.utcnow() - timedelta(seconds=since_seconds)

    token_ok = True
    try:
        resp = sess.get(f"{cfg['api_url']}/api/v1/namespaces", timeout=10)
        if resp.status_code in (401, 403):
            token_ok = False
    except Exception:
        token_ok = False

    tools_report = []
    total_pods = 0
    pods_with_restarts = 0
    total_log_bytes = 0
    total_parsed_calls = 0
    errors = []

    for tool in cfg["tools"]:
        pods = _discover_pods(sess, cfg["api_url"], tool)
        tool_entry = {"tool": tool, "pods_found": len(pods), "pods": []}

        for pod in pods:
            total_pods += 1
            pod_diag = {
                "name": pod["name"],
                "namespace": pod["namespace"],
                "container": pod["container"],
                "age": None,
                "age_hours": None,
                "restarts": 0,
                "last_terminated": None,
                "log_bytes": 0,
                "log_lines": 0,
                "parsed_calls": 0,
                "status": "ok",
            }

            try:
                url = f"{cfg['api_url']}/api/v1/namespaces/{pod['namespace']}/pods/{pod['name']}"
                resp = sess.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    created = data.get("metadata", {}).get("creationTimestamp", "")
                    if created:
                        try:
                            ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            delta = datetime.now(timezone.utc) - ct
                            d = delta.days
                            h = delta.seconds // 3600
                            pod_diag["age"] = f"{d}d {h}h" if d else f"{h}h"
                            pod_diag["age_hours"] = round(delta.total_seconds() / 3600, 1)
                        except Exception:
                            pod_diag["age"] = created

                    for cs in data.get("status", {}).get("containerStatuses", []):
                        if cs.get("name") == pod["container"] or pod["container"] in cs.get("name", ""):
                            pod_diag["restarts"] = cs.get("restartCount", 0)
                            last_state = cs.get("lastState", {})
                            terminated = last_state.get("terminated", {})
                            if terminated.get("finishedAt"):
                                pod_diag["last_terminated"] = terminated["finishedAt"]
                            break
                elif resp.status_code in (401, 403):
                    pod_diag["status"] = f"auth_error_{resp.status_code}"
                    errors.append(f"{pod['name']}: HTTP {resp.status_code} fetching pod detail")
                else:
                    pod_diag["status"] = f"http_{resp.status_code}"
            except Exception as e:
                pod_diag["status"] = f"error: {e}"
                errors.append(f"{pod['name']}: {e}")

            try:
                log_text = _fetch_pod_logs(sess, cfg["api_url"], pod, since_seconds)
                pod_diag["log_bytes"] = len(log_text)
                pod_diag["log_lines"] = len(log_text.splitlines()) if log_text else 0
                total_log_bytes += pod_diag["log_bytes"]

                if log_text:
                    parsed = _parse_logs(log_text, tool, hourly=(days <= 1), cutoff=cutoff)
                    pod_diag["parsed_calls"] = parsed["total_calls"]
                    total_parsed_calls += parsed["total_calls"]
            except Exception as e:
                pod_diag["status"] = f"log_error: {e}"
                errors.append(f"{pod['name']}: log fetch failed — {e}")

            if pod_diag["restarts"] > 0:
                pods_with_restarts += 1

            tool_entry["pods"].append(pod_diag)

        tools_report.append(tool_entry)

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "token_status": "ok" if token_ok else "EXPIRED_OR_INVALID",
        "tools": tools_report,
        "summary": {
            "total_pods": total_pods,
            "pods_with_restarts": pods_with_restarts,
            "total_log_bytes": total_log_bytes,
            "total_parsed_calls": total_parsed_calls,
            "errors": errors,
        },
    }
