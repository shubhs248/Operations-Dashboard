"""Collector for MCP usage stats from OCP pod logs.

Fetches logs directly from the Kubernetes API for each MCP tool pod,
parses uvicorn/application log lines, and aggregates usage statistics.
"""
import re
import logging
import base64
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import urllib3

from app import config, cache, database

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

# Log line patterns — flexible enough for both log formats:
#   Nexus/Artifactory: 'TS' - module - INFO - trace_id=... - content
#   Bitbucket/Jenkins:  'TS' INFO [module] [file:line] - content
RE_AUTH = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"Authenticated to system \(username=(\w+)"
)
# Header-based auth — Jenkins (x-jenkins-user) and Bitbucket (x-bitbucket-username)
RE_HEADER_USER = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:x-jenkins-user|x-bitbucket-username|x-user-id|x-username)[=:\s]+['\"]?(\w+)",
    re.IGNORECASE,
)
# Broader auth — "user=xxx" or "username=xxx" or "Resolved user: xxx" or
# "Authenticated user: xxx" (covers token-based auth like Artifactory)
RE_USER_RESOLVED = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:Resolved user|Authenticated user|Authenticated as|Request from user|"
    r"User identified|Token user|user_id=|user_name=)"
    r"[=:\s(]+['\"]?(\w+)",
    re.IGNORECASE,
)
# Basic Auth header — Jenkins "Authorization: Basic <base64(user:token)>"
RE_BASIC_AUTH = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:Authorization|authorization)[=:\s]+['\"]?Basic\s+([A-Za-z0-9+/=]+)",
)
# MCP request log — captures username from structured request logs
RE_MCP_REQUEST_USER = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:MCP request|Incoming request).*?(?:user|username)[=:\s]+['\"]?(\w+)",
    re.IGNORECASE,
)
# Jenkins/Nexus connect — "Connected to Jenkins as shubhas8" or "Connected as shubhas8"
RE_CONNECTED_AS = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:Connected to \w+ as|Connected as|Logged in as|Session (?:created|started) (?:for|as))"
    r"\s+['\"]?(\w+)",
    re.IGNORECASE,
)
# Generic username in JSON log — {"username": "shubhas8"} or user: shubhas8
RE_JSON_USER = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"[\"']?username[\"']?\s*[:=]\s*[\"'](\w+)[\"']",
    re.IGNORECASE,
)


def _get_ocp_config():
    from app import ocp_token_manager
    settings = config.get_settings()
    token = ocp_token_manager.get_token() or settings.ocp_token
    return {
        "api_url": settings.ocp_api_url.rstrip("/"),
        "token": token,
        "tools": [t.strip() for t in settings.ocp_mcp_tools.split(",") if t.strip()],
    }


def _session(token: str):
    s = requests.Session()
    s.verify = False
    s.trust_env = False
    s.headers["Authorization"] = f"Bearer {token}"
    return s


_EXTRA_NS_ALIASES = {
    "nexus": ["nexus-user", "nxrm", "nexus-rm", "nexus3", "sonatype-nexus", "nexus-repository"],
    "bitbucket": ["bb", "stash"],
    "artifactory": ["jfrog", "art"],
}


def _discover_pods(sess, api_url: str, tool: str) -> list[dict]:
    """Find running pods for a given MCP tool across all candidate namespaces.

    Tries multiple namespace conventions (including aliases for tools like
    Nexus/NXRM) and combines results so we don't miss deployments that live
    in a namespace without the ``at-`` prefix.
    """
    aliases = [tool] + _EXTRA_NS_ALIASES.get(tool, [])
    namespace_candidates = []
    for alias in aliases:
        namespace_candidates.extend([
            f"at-{alias}-mcp", f"{alias}-mcp", f"at-{alias}", f"at-mcp-{alias}", alias,
            f"{alias}-rm-mcp", f"at-{alias}-rm-mcp",
        ])
    namespace_candidates = list(dict.fromkeys(namespace_candidates))

    all_running = []
    seen_pods = set()
    checked = []

    for namespace in namespace_candidates:
        url = f"{api_url}/api/v1/namespaces/{namespace}/pods"
        try:
            resp = sess.get(url, timeout=30)
            if resp.status_code in (404, 403):
                checked.append((namespace, resp.status_code))
                continue
            resp.raise_for_status()
            pods = resp.json().get("items", [])
            checked.append((namespace, f"OK:{len(pods)} pods"))
            for pod in pods:
                name = pod.get("metadata", {}).get("name", "")
                phase = pod.get("status", {}).get("phase", "")
                if phase != "Running" or name in seen_pods:
                    continue
                name_lower = name.lower()
                tool_lower = tool.lower()
                match = (
                    any(name.startswith(f"{a}-mcp") or name.startswith(f"at-{a}-mcp")
                        or name.startswith(f"at-mcp-{a}")
                        or name.startswith(f"{a}-") or name.startswith(f"at-{a}-")
                        for a in aliases)
                    or (tool_lower in name_lower and "mcp" in name_lower)
                    or any(a in name_lower for a in aliases if a != tool)
                )
                if not match:
                    continue
                container = _detect_container(pod, tool)
                if container:
                    seen_pods.add(name)
                    all_running.append({"name": name, "namespace": namespace, "container": container})
        except Exception as e:
            checked.append((namespace, f"ERR:{e}"))
            logger.error("Failed to discover pods for %s in %s: %s", tool, namespace, e)

    if all_running:
        namespaces = set(p["namespace"] for p in all_running)
        logger.info("Discovered %d running pod(s) for %s in %s", len(all_running), tool, namespaces)
    else:
        logger.error(
            "No pods discovered for tool '%s'. Checked namespaces: %s",
            tool, "; ".join(f"{ns}={st}" for ns, st in checked),
        )
    return all_running


def _detect_container(pod: dict, tool: str) -> str:
    """Return the best container name for the given tool inside a pod spec."""
    aliases = [tool] + _EXTRA_NS_ALIASES.get(tool, [])
    containers = pod.get("spec", {}).get("containers", [])
    names = [c.get("name", "") for c in containers]
    for alias in aliases:
        for preferred in [f"at-{alias}-mcp", f"{alias}-mcp", f"at-mcp-{alias}", alias, "mcp-server", f"at-{alias}"]:
            if preferred in names:
                return preferred
    for n in names:
        if any(a in n for a in aliases) or "mcp" in n:
            return n
    return names[0] if names else ""


def _fetch_pod_logs(sess, api_url: str, pod: dict, since_seconds: int = 86400) -> str:
    """Fetch logs from a specific pod, including previous container instance."""
    base = (
        f"{api_url}/api/v1/namespaces/{pod['namespace']}/pods/{pod['name']}/log"
        f"?container={pod['container']}&sinceSeconds={since_seconds}&timestamps=false"
    )
    parts = []
    try:
        resp = sess.get(base + "&previous=true", timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            parts.append(resp.text)
    except Exception:
        pass
    try:
        resp = sess.get(base, timeout=60)
        resp.raise_for_status()
        parts.append(resp.text)
    except Exception as e:
        logger.error("Failed to fetch logs for %s/%s: %s", pod['namespace'], pod['name'], e)
    return "\n".join(parts)


RE_TOOL_STATS = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"Recording MCP stats for (\w+)\s*-\s*App:\s*(\S+).*?Function:\s*([\w/.:-]+)"
)

RE_CALL_TOOL = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"Processing request of type CallToolRequest"
)

RE_TOOL_EXEC = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"(?:Executing tool|Tool execution|Calling tool|Tool called|Running tool)[:\s]+(\S+)"
)
# Captures tool name from JSON-style MCP protocol logs: "name": "func_name"
RE_TOOL_NAME_JSON = re.compile(
    r"'?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'?\s.*?"
    r"tools/call.*?\"name\"\s*:\s*\"([\w/.:-]+)\""
)

RE_TRACE_ID = re.compile(r"trace_id=([a-f0-9]+)")

MCP_PROTOCOL_FUNCTIONS = {
    "ping", "initialize", "initialized",
    "tools/list", "resources/list", "prompts/list",
    "resources/subscribe", "resources/unsubscribe",
    "resources/templates/list",
    "notifications/initialized", "notifications/cancelled",
    "completion/complete", "logging/setLevel",
    "manage_session",
}


def _parse_logs(log_text: str, tool: str, hourly: bool = False, cutoff: datetime = None) -> dict:
    """Parse log text and extract usage statistics.

    Primary: counts 'Recording MCP stats' lines (with function names).
    Fallback: counts 'CallToolRequest' lines correlated with auth via trace_id
    for MCPs that don't emit the stats line.
    """
    bucket_users = defaultdict(set)
    bucket_calls = defaultdict(int)
    user_call_count = defaultdict(int)
    functions_count = defaultdict(int)
    user_functions = defaultdict(lambda: defaultdict(int))
    daily_user_functions = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    total_calls = 0

    users_by_trace = {}
    last_auth_user = None
    auth_timeline = []
    call_tool_events = []
    tool_exec_events = []
    has_stats_lines = False
    protocol_skipped = 0
    seen_trace_ids = set()
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S") if cutoff else None

    def _bucket_key(ts_str):
        if hourly:
            return ts_str[:13] + ":00"
        return ts_str[:10]

    def _decode_basic_auth(b64_str):
        """Decode a Basic Auth base64 string and return the username."""
        try:
            decoded = base64.b64decode(b64_str).decode("utf-8", errors="replace")
            if ":" in decoded:
                return decoded.split(":", 1)[0]
        except Exception:
            pass
        return None

    def _extract_auth(line):
        """Try all auth regex patterns; return (ts_str, username) or None."""
        for pat in (RE_AUTH, RE_HEADER_USER, RE_USER_RESOLVED, RE_MCP_REQUEST_USER,
                    RE_CONNECTED_AS, RE_JSON_USER):
            m = pat.search(line)
            if m:
                uname = m.group(2).lower()
                if uname not in ("unknown", "_unknown", "none", "null", "true", "false"):
                    return m.group(1), uname
        m = RE_BASIC_AUTH.search(line)
        if m:
            user = _decode_basic_auth(m.group(2))
            if user:
                return m.group(1), user.lower()
        return None

    for line in log_text.splitlines():
        tool_match = RE_TOOL_STATS.search(line)
        if tool_match:
            has_stats_lines = True
            ts_str, username, app, func_name = tool_match.groups()
            username = username.lower()
            if cutoff_str and ts_str < cutoff_str:
                continue
            if username in ("unknown", "_unknown"):
                trace_match = RE_TRACE_ID.search(line)
                tid = trace_match.group(1) if trace_match else None
                if tid and tid in users_by_trace:
                    username = users_by_trace[tid][0]
                elif last_auth_user and last_auth_user[0] not in ("unknown", "_unknown"):
                    username = last_auth_user[0]
            if func_name.lower() in MCP_PROTOCOL_FUNCTIONS:
                protocol_skipped += 1
                if username not in ("unknown", "_unknown"):
                    last_auth_user = (username, ts_str)
                    auth_timeline.append((ts_str, username))
                bk = _bucket_key(ts_str)
                bucket_users[bk].add(username)
                trace_match = RE_TRACE_ID.search(line)
                if trace_match:
                    users_by_trace[trace_match.group(1)] = (username, ts_str)
                continue
            trace_match = RE_TRACE_ID.search(line)
            if trace_match:
                tid = trace_match.group(1)
                if tid in seen_trace_ids:
                    continue
                seen_trace_ids.add(tid)
            bk = _bucket_key(ts_str)
            day_key = ts_str[:10]
            bucket_users[bk].add(username)
            bucket_calls[bk] += 1
            user_call_count[username] += 1
            functions_count[func_name] += 1
            user_functions[username][func_name] += 1
            daily_user_functions[day_key][username][func_name] += 1
            total_calls += 1
            continue

        auth_result = _extract_auth(line)
        if auth_result:
            ts_str, username = auth_result
            if cutoff_str and ts_str < cutoff_str:
                continue
            last_auth_user = (username, ts_str)
            auth_timeline.append((ts_str, username))
            bk = _bucket_key(ts_str)
            bucket_users[bk].add(username)
            trace_match = RE_TRACE_ID.search(line)
            if trace_match:
                users_by_trace[trace_match.group(1)] = (username, ts_str)
            continue

        json_tool_match = RE_TOOL_NAME_JSON.search(line)
        if json_tool_match:
            ts_str, func_name = json_tool_match.groups()
            if cutoff_str and ts_str < cutoff_str:
                continue
            if func_name.lower() in MCP_PROTOCOL_FUNCTIONS:
                protocol_skipped += 1
                continue
            trace_match = RE_TRACE_ID.search(line)
            trace_id = trace_match.group(1) if trace_match else None
            tool_exec_events.append((ts_str, trace_id, func_name))
            continue

        exec_match = RE_TOOL_EXEC.search(line)
        if exec_match:
            ts_str, func_name = exec_match.groups()
            if cutoff_str and ts_str < cutoff_str:
                continue
            if func_name.lower() in MCP_PROTOCOL_FUNCTIONS:
                protocol_skipped += 1
                continue
            trace_match = RE_TRACE_ID.search(line)
            trace_id = trace_match.group(1) if trace_match else None
            tool_exec_events.append((ts_str, trace_id, func_name))
            continue

        call_match = RE_CALL_TOOL.search(line)
        if call_match:
            ts_str = call_match.group(1)
            if cutoff_str and ts_str < cutoff_str:
                continue
            trace_match = RE_TRACE_ID.search(line)
            trace_id = trace_match.group(1) if trace_match else None
            call_tool_events.append((ts_str, trace_id))

    import bisect
    auth_timeline.sort(key=lambda x: x[0])
    auth_ts_list = [a[0] for a in auth_timeline]

    def _resolve_user_by_proximity(ts_str):
        """Find the nearest preceding auth event within 10 seconds."""
        idx = bisect.bisect_right(auth_ts_list, ts_str) - 1
        if idx >= 0:
            auth_ts, auth_user = auth_timeline[idx]
            if auth_user not in ("unknown", "_unknown"):
                return auth_user
        return None

    extra_events = tool_exec_events if tool_exec_events else call_tool_events
    if extra_events:
        for evt in extra_events:
            if len(evt) == 3:
                ts_str, trace_id, func_name = evt
            else:
                ts_str, trace_id = evt
                func_name = f"{tool}_call"
            if trace_id and trace_id in seen_trace_ids:
                continue
            if trace_id:
                seen_trace_ids.add(trace_id)
            username = "_unknown"
            if trace_id:
                user_info = users_by_trace.get(trace_id)
                if user_info:
                    username = user_info[0]
            if username == "_unknown":
                resolved = _resolve_user_by_proximity(ts_str)
                if resolved:
                    username = resolved
            bk = _bucket_key(ts_str)
            day_key = ts_str[:10]
            bucket_users[bk].add(username)
            bucket_calls[bk] += 1
            user_call_count[username] += 1
            functions_count[func_name] += 1
            user_functions[username][func_name] += 1
            daily_user_functions[day_key][username][func_name] += 1
            total_calls += 1

    unique_users = sorted(user_call_count.keys())
    protocol_users = set()
    for ts, u in auth_timeline:
        protocol_users.add(u)
    all_seen_users = sorted(protocol_users | set(unique_users))

    logger.info(
        "[%s] Parse results: stats_lines=%s, auth_users=%d (last=%s), tool_exec=%d, "
        "call_tool=%d, json_tool=%d, protocol_skipped=%d, total_calls=%d, "
        "active_users=[%s], all_seen_users=[%s]",
        tool, has_stats_lines, len(users_by_trace),
        last_auth_user[0] if last_auth_user else "none",
        len(tool_exec_events), len(call_tool_events),
        sum(1 for e in tool_exec_events if len(e) == 3),
        protocol_skipped, total_calls,
        ",".join(unique_users[:30]),
        ",".join(all_seen_users[:30]),
    )

    return {
        "tool": tool,
        "total_calls": total_calls,
        "daily_users": bucket_users,
        "daily_calls": bucket_calls,
        "user_call_count": user_call_count,
        "functions_count": functions_count,
        "user_functions": {u: dict(fns) for u, fns in user_functions.items()},
        "daily_user_functions": {
            day: {u: dict(fns) for u, fns in users.items()}
            for day, users in daily_user_functions.items()
        },
    }


def _top_n_functions(fn_dict, n=5, func_tool_map=None):
    """Return top-N functions with percentage share.

    When *func_tool_map* is provided, guarantees at least one function per tool
    so that tools with few calls still appear in the TOP FUNCTIONS column.
    """
    if not fn_dict:
        return []
    total = sum(fn_dict.values())
    sorted_fns = sorted(fn_dict.items(), key=lambda x: x[1], reverse=True)

    if func_tool_map:
        all_user_tools = {func_tool_map.get(fn, "") for fn in fn_dict} - {""}
        selected = {}
        tools_seen = set()
        for name, count in sorted_fns:
            tool = func_tool_map.get(name, "")
            if tool and tool not in tools_seen:
                tools_seen.add(tool)
                selected[name] = count
            elif len(selected) < n:
                selected[name] = count
            if tools_seen >= all_user_tools and len(selected) >= n:
                break
        final = sorted(selected.items(), key=lambda x: x[1], reverse=True)
    else:
        final = sorted_fns[:n]

    return [
        {"name": name, "count": count, "pct": round(count / total * 100, 1)}
        for name, count in final
    ]


def _collect_tool_logs(tool, api_url, token, since_seconds, hourly, cutoff):
    """Collect and parse logs for a single tool (thread-safe)."""
    sess = _session(token)
    pods = _discover_pods(sess, api_url, tool)
    if not pods:
        logger.warning("[%s] No running pods found — skipping", tool)
        return None

    logger.info("[%s] Found %d pod(s): %s", tool, len(pods),
                ", ".join(p["name"] + " (" + p["namespace"] + "/" + p["container"] + ")" for p in pods))

    tool_result = {
        "bucket_users": defaultdict(set),
        "bucket_calls": defaultdict(int),
        "user_counts": defaultdict(int),
        "functions": defaultdict(int),
        "user_functions": defaultdict(lambda: defaultdict(int)),
        "daily_user_functions": defaultdict(lambda: defaultdict(lambda: defaultdict(int))),
        "tool_bucket_calls": defaultdict(int),
        "total_calls": 0,
    }

    for pod in pods:
        log_text = _fetch_pod_logs(sess, api_url, pod, since_seconds)
        if not log_text:
            logger.warning("[%s] Empty logs from pod %s", tool, pod["name"])
            continue
        log_lines = len(log_text.splitlines())
        parsed = _parse_logs(log_text, tool, hourly=hourly, cutoff=cutoff)
        user_detail = ", ".join(
            f"{u}={c}" for u, c in sorted(parsed["user_call_count"].items(),
                                           key=lambda x: x[1], reverse=True)[:15]
        ) or "none"
        logger.info("[%s] Pod %s (%s/%s): %d lines → %d calls, user_counts: {%s}",
                    tool, pod["name"], pod["namespace"], pod["container"],
                    log_lines, parsed["total_calls"], user_detail)
        if parsed["total_calls"] == 0 and log_lines > 50:
            sample = [l.strip() for l in log_text.splitlines()[-20:] if l.strip()]
            logger.info("[%s] Zero-call pod log sample (last 20 lines):\n  %s",
                        tool, "\n  ".join(sample[-10:]))
        tool_result["total_calls"] += parsed["total_calls"]
        for bucket, users in parsed["daily_users"].items():
            tool_result["bucket_users"][bucket].update(users)
        for bucket, count in parsed["daily_calls"].items():
            tool_result["bucket_calls"][bucket] += count
            tool_result["tool_bucket_calls"][bucket] += count
        for user, count in parsed["user_call_count"].items():
            tool_result["user_counts"][user] += count
        for func, count in parsed["functions_count"].items():
            tool_result["functions"][func] += count
        for user, fns in parsed["user_functions"].items():
            for fn, count in fns.items():
                tool_result["user_functions"][user][fn] += count
        for day, users in parsed.get("daily_user_functions", {}).items():
            for user, fns in users.items():
                for fn, count in fns.items():
                    tool_result["daily_user_functions"][day][user][fn] += count

    return tool_result


def collect_ocp_mcp_stats(days: int = 1, cache_key: str = "ocp_mcp_stats", tool_filter: str = "", persist: bool = True):
    """Collect MCP usage from OCP pod logs for all configured tools."""
    import concurrent.futures
    from app import ocp_token_manager

    cfg = _get_ocp_config()
    if not cfg["token"]:
        logger.warning("OCP token not configured, skipping OCP MCP stats collection")
        return None

    sess = _session(cfg["token"])
    try:
        resp = sess.get(f"{cfg['api_url']}/api/v1/namespaces", timeout=10)
        if resp.status_code in (401, 403):
            logger.warning("OCP token expired (HTTP %d) — attempting auto-refresh", resp.status_code)
            new_token = ocp_token_manager.force_refresh()
            if new_token and new_token != cfg["token"]:
                cfg["token"] = new_token
                logger.info("OCP token refreshed successfully, retrying collection")
            else:
                logger.error("OCP token refresh failed — skipping collection")
                return None
    except Exception as e:
        logger.error("OCP API connectivity check failed: %s", e)

    tools = cfg["tools"]
    if tool_filter:
        tools = [t for t in tools if tool_filter.lower() in t.lower()]

    since_seconds = days * 86400
    hourly = days <= 1
    cutoff = datetime.utcnow() - timedelta(seconds=since_seconds)

    all_bucket_users = defaultdict(set)
    all_bucket_calls = defaultdict(int)
    all_user_counts = defaultdict(int)
    all_functions = defaultdict(int)
    all_user_functions = defaultdict(lambda: defaultdict(int))
    all_daily_user_functions = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    all_apps = defaultdict(int)
    func_tool_map = {}
    tool_bucket_calls = defaultdict(lambda: defaultdict(int))
    total_calls = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tools)) as pool:
        futures = {
            pool.submit(
                _collect_tool_logs, tool, cfg["api_url"], cfg["token"],
                since_seconds, hourly, cutoff,
            ): tool
            for tool in tools
        }
        try:
            for future in concurrent.futures.as_completed(futures, timeout=300):
                tool = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.error("Log collection failed for %s: %s", tool, e)
                    continue
                if result is None:
                    continue
                tool_calls = result["total_calls"]
                total_calls += tool_calls
                for bucket, users in result["bucket_users"].items():
                    all_bucket_users[bucket].update(users)
                for bucket, count in result["bucket_calls"].items():
                    all_bucket_calls[bucket] += count
                    tool_bucket_calls[tool][bucket] += count
                for user, count in result["user_counts"].items():
                    all_user_counts[user] += count
                for func, count in result["functions"].items():
                    all_functions[func] += count
                    if func not in func_tool_map:
                        func_tool_map[func] = tool
                for user, fns in result["user_functions"].items():
                    for fn, count in fns.items():
                        all_user_functions[user][fn] += count
                        if fn not in func_tool_map:
                            func_tool_map[fn] = tool
                for day, users in result.get("daily_user_functions", {}).items():
                    for user, fns in users.items():
                        for fn, count in fns.items():
                            all_daily_user_functions[day][user][fn] += count
                if tool_calls > 0:
                    all_apps[tool] = tool_calls
        except concurrent.futures.TimeoutError:
            finished = sum(1 for f in futures if f.done())
            logger.warning(
                "OCP collection timed out after 300s: %d/%d tools finished — caching partial data",
                finished, len(futures),
            )

    # ── Merge with persisted DB data (per-day max, no double-counting) ──
    _merge_db_history(
        days, all_bucket_users, all_bucket_calls, all_user_counts,
        all_functions, all_user_functions, all_daily_user_functions, all_apps,
        func_tool_map, tool_bucket_calls, hourly,
    )

    active_tools = sorted(all_apps.keys())

    if hourly:
        now = datetime.utcnow()
        all_hours = []
        for h in range(24):
            dt = now - timedelta(hours=23 - h)
            all_hours.append(dt.strftime("%Y-%m-%d %H:00"))
        visible_buckets = set(all_hours)
        daily_list = []
        for bucket in all_hours:
            entry = {
                "date": bucket,
                "users": len(all_bucket_users.get(bucket, set())),
                "requests": all_bucket_calls.get(bucket, 0),
                "by_tool": {t: tool_bucket_calls[t].get(bucket, 0) for t in active_tools},
            }
            daily_list.append(entry)
        total_calls = sum(all_bucket_calls.get(b, 0) for b in visible_buckets)
    else:
        sorted_buckets = sorted(all_bucket_users.keys())
        daily_list = []
        for bucket in sorted_buckets:
            entry = {
                "date": bucket,
                "users": len(all_bucket_users[bucket]),
                "requests": all_bucket_calls.get(bucket, 0),
                "by_tool": {t: tool_bucket_calls[t].get(bucket, 0) for t in active_tools},
            }
            daily_list.append(entry)
        total_calls = sum(all_user_counts.values())

    _GHOST_USERS = {"_unknown", "unknown", "none", "null", "system", "anonymous"}
    sorted_users = sorted(
        ((u, c) for u, c in all_user_counts.items() if u.lower() not in _GHOST_USERS),
        key=lambda x: x[1], reverse=True,
    )
    sorted_functions = sorted(all_functions.items(), key=lambda x: x[1], reverse=True)
    sorted_apps = sorted(all_apps.items(), key=lambda x: x[1], reverse=True)

    all_unique_users = set()
    for users in all_bucket_users.values():
        all_unique_users.update(u for u in users if u.lower() not in _GHOST_USERS)

    all_user_fn_serialized = {
        u: {fn: c for fn, c in fns.items()}
        for u, fns in all_user_functions.items()
    }

    result = {
        "collected_at": datetime.utcnow().isoformat() + "Z",
        "period_days": days,
        "total_requests": total_calls,
        "total_tool_calls": total_calls,
        "daily_users": daily_list,
        "by_application": [{"name": name, "count": count} for name, count in sorted_apps],
        "by_function": [{"name": name, "count": count} for name, count in sorted_functions],
        "top_users": [
            {
                "username": user,
                "count": count,
                "top_functions": _top_n_functions(all_user_functions.get(user, {}), 5, func_tool_map),
                "tools_used": sorted(
                    {func_tool_map.get(fn, "") for fn in all_user_functions.get(user, {})}
                    - {""},
                ),
            }
            for user, count in sorted_users
        ],
        "all_user_functions": all_user_fn_serialized,
        "func_tool_map": func_tool_map,
    }

    cache.set(cache_key, result, ttl=900)

    # ── Persist to DB for future runs (only from 1-day collection) ──
    if persist:
        _persist_usage_to_db(all_daily_user_functions, func_tool_map)

    logger.info(
        "OCP MCP stats cached → key=%s, days=%d: %d tool calls, %d apps, %d users",
        cache_key, days, total_calls, len(all_apps), len(all_unique_users),
    )
    return result


def _persist_usage_to_db(daily_user_functions, func_tool_map):
    """Write per-(date, user, function) records from the daily breakdown."""
    records = []
    for day, users in daily_user_functions.items():
        for user, fns in users.items():
            for fn, count in fns.items():
                if count <= 0:
                    continue
                records.append({
                    "date": day,
                    "username": user,
                    "function_name": fn,
                    "tool_name": func_tool_map.get(fn, "unknown"),
                    "call_count": count,
                })
    if records:
        try:
            database.save_mcp_usage(records)
        except Exception as e:
            logger.error("Failed to persist MCP usage to DB: %s", e)


def _merge_db_history(
    days, all_bucket_users, all_bucket_calls, all_user_counts,
    all_functions, all_user_functions, all_daily_user_functions, all_apps,
    func_tool_map, tool_bucket_calls, hourly,
):
    """Load historical records from the DB and merge into the live aggregates.

    Uses a true per-(date, user, function) max: for each key, take the higher
    of the pod log count and the DB count. Only the excess from DB (for dates
    where pod logs are missing or incomplete) is added to the live aggregates.
    This prevents the feedback loop that previously caused runaway inflation.
    """
    try:
        db_records = database.get_mcp_usage(days)
    except Exception as e:
        logger.warning("Could not load MCP usage history from DB: %s", e)
        return

    if not db_records:
        return

    db_matrix = defaultdict(lambda: defaultdict(dict))
    for r in db_records:
        db_matrix[r["date"]][r["username"]][r["function_name"]] = (
            r["call_count"], r["tool_name"],
        )

    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    merged_count = 0
    for day, users in db_matrix.items():
        if hourly and day < today_str:
            continue
        for user, fns in users.items():
            for fn, (db_count, db_tool) in fns.items():
                pod_count = all_daily_user_functions.get(day, {}).get(user, {}).get(fn, 0)
                if db_count <= pod_count:
                    continue
                delta = db_count - pod_count
                merged_count += 1

                all_user_counts[user] += delta
                all_functions[fn] += delta
                all_user_functions[user][fn] += delta
                all_daily_user_functions[day][user][fn] = db_count

                if fn not in func_tool_map:
                    func_tool_map[fn] = db_tool
                tool = func_tool_map.get(fn, db_tool)

                all_apps[tool] = all_apps.get(tool, 0) + delta

                bucket = day if not hourly else day + " 00:00"
                all_bucket_users[bucket].add(user)
                all_bucket_calls[bucket] += delta
                tool_bucket_calls[tool][bucket] += delta

    if merged_count:
        logger.info("Merged %d user/function entries from DB history", merged_count)
