"""Collector for MCP server health and per-tool metrics (Python 3.6+, sync)."""
import time
import logging
from datetime import datetime

import requests

from app import config, cache

logger = logging.getLogger(__name__)

TOOL_NAMES = ["nexus", "jenkins", "artifactory", "bitbucket"]


def _probe_server(session, server):
    url = server["url"]
    result = {
        "host": server["host"],
        "port": server["port"],
        "url": url,
        "status": "down",
        "latency_ms": None,
        "request_count": 0,
        "error_count": 0,
        "active_connections": 0,
        "tools": [],
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }

    try:
        start = time.monotonic()
        resp = session.get("{}/health".format(url), timeout=10)
        result["latency_ms"] = round((time.monotonic() - start) * 1000, 1)

        if resp.status_code == 200:
            result["status"] = "up"
            try:
                data = resp.json()
            except Exception:
                data = {}
            result["request_count"] = data.get("request_count", 0)
            result["error_count"] = data.get("error_count", 0)
            result["active_connections"] = data.get("active_connections", 0)
        else:
            result["status"] = "degraded"
    except requests.ConnectionError:
        result["status"] = "down"
    except requests.Timeout:
        result["status"] = "timeout"
    except Exception as e:
        logger.warning("Probe failed for %s: %s", url, e)
        result["status"] = "error"

    for tool_name in TOOL_NAMES:
        tool_data = _probe_tool(session, url, tool_name)
        result["tools"].append(tool_data)

    return result


def _probe_tool(session, base_url, tool_name):
    tool = {
        "name": tool_name,
        "status": "unknown",
        "request_count": 0,
        "error_count": 0,
        "avg_response_ms": None,
        "last_success_at": None,
        "last_error_at": None,
        "last_error_message": None,
    }

    try:
        resp = session.get("{}/api/tools/{}/status".format(base_url, tool_name), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            tool["status"] = data.get("status", "up")
            tool["request_count"] = data.get("request_count", 0)
            tool["error_count"] = data.get("error_count", 0)
            tool["avg_response_ms"] = data.get("avg_response_ms")
            tool["last_success_at"] = data.get("last_success_at")
            tool["last_error_at"] = data.get("last_error_at")
            tool["last_error_message"] = data.get("last_error_message")
        elif resp.status_code == 404:
            tool["status"] = "not_available"
        else:
            tool["status"] = "error"
    except requests.Timeout:
        tool["status"] = "timeout"
    except Exception:
        tool["status"] = "unreachable"

    return tool


def collect_all_mcp_metrics():
    servers = config.mcp_server_list()

    if not servers:
        logger.warning("No MCP servers configured")
        return []

    results = []
    session = requests.Session()
    session.verify = False

    for server in servers:
        result = _probe_server(session, server)
        results.append(result)

    cache.set("mcp:status", results, ttl=config.MCP_POLL_INTERVAL + 60)

    tool_agg = _aggregate_tool_metrics(results)
    cache.set("mcp:tools", tool_agg, ttl=config.MCP_POLL_INTERVAL + 60)

    summary = {
        "total_servers": len(results),
        "servers_up": sum(1 for r in results if r["status"] == "up"),
        "servers_down": sum(1 for r in results if r["status"] in ("down", "error")),
        "servers_degraded": sum(1 for r in results if r["status"] in ("degraded", "timeout")),
        "total_requests": sum(r["request_count"] for r in results),
        "total_errors": sum(r["error_count"] for r in results),
        "avg_latency_ms": round(
            sum(r["latency_ms"] for r in results if r["latency_ms"]) /
            max(1, sum(1 for r in results if r["latency_ms"])), 1
        ),
        "collected_at": datetime.utcnow().isoformat() + "Z",
    }
    cache.set("mcp:summary", summary, ttl=config.MCP_POLL_INTERVAL + 60)

    return results


def _aggregate_tool_metrics(server_results):
    tool_map = {}

    for server in server_results:
        for tool in server.get("tools", []):
            name = tool["name"]
            if name not in tool_map:
                tool_map[name] = {
                    "name": name,
                    "servers_total": 0,
                    "servers_up": 0,
                    "total_requests": 0,
                    "total_errors": 0,
                    "latencies": [],
                    "last_error_message": None,
                    "last_error_at": None,
                }
            agg = tool_map[name]
            agg["servers_total"] += 1
            if tool["status"] == "up":
                agg["servers_up"] += 1
            agg["total_requests"] += tool["request_count"]
            agg["total_errors"] += tool["error_count"]
            if tool["avg_response_ms"]:
                agg["latencies"].append(tool["avg_response_ms"])
            if tool["last_error_at"]:
                if not agg["last_error_at"] or tool["last_error_at"] > agg["last_error_at"]:
                    agg["last_error_at"] = tool["last_error_at"]
                    agg["last_error_message"] = tool["last_error_message"]

    result = []
    for tool in tool_map.values():
        lats = tool.pop("latencies")
        tool["avg_response_ms"] = round(sum(lats) / len(lats), 1) if lats else None
        tool["error_rate"] = round(
            tool["total_errors"] / max(1, tool["total_requests"]) * 100, 2
        )
        result.append(tool)

    return sorted(result, key=lambda t: t["name"])
