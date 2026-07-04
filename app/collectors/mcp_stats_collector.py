"""Collector for MCP usage stats from Grafana-stats Elasticsearch datasource.

Uses Grafana's /api/ds/query endpoint (same as Grafana dashboards use internally)
which properly handles time range filtering.
"""
import json
import logging
from datetime import datetime, timedelta

import requests
import urllib3

from app import config, cache

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

GRAFANA_STATS_URL = None
GRAFANA_STATS_AUTH = None
MCP_DS_UID = "bew1dosw9rcaoe"

TOOLS_MCP_KEYWORDS = []


def _get_config():
    global GRAFANA_STATS_URL, GRAFANA_STATS_AUTH
    settings = config.get_settings()
    GRAFANA_STATS_URL = settings.grafana_stats_url
    GRAFANA_STATS_AUTH = (settings.grafana_stats_user, settings.grafana_stats_password)


def _session():
    s = requests.Session()
    s.verify = False
    s.trust_env = False
    return s


def _ds_query(bucket_aggs: list, metrics: list, query: str = "", time_from: str = "now-30d", time_to: str = "now"):
    """Query ES via Grafana /api/ds/query — respects time range natively."""
    _get_config()
    if not GRAFANA_STATS_URL:
        return None

    url = f"{GRAFANA_STATS_URL}/api/ds/query"
    payload = {
        "queries": [
            {
                "refId": "A",
                "datasource": {"type": "elasticsearch", "uid": MCP_DS_UID},
                "query": query,
                "timeField": "timestamp",
                "bucketAggs": bucket_aggs,
                "metrics": metrics,
            }
        ],
        "from": time_from,
        "to": time_to,
    }

    try:
        sess = _session()
        resp = sess.post(url, json=payload, auth=GRAFANA_STATS_AUTH, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Grafana ds/query failed: %s", e)
        return None


def _extract_frames(response):
    """Extract data frames from Grafana /api/ds/query response."""
    if not response or "results" not in response:
        return []
    result_a = response.get("results", {}).get("A", {})
    return result_a.get("frames", [])


def collect_mcp_stats(days: int = 30, cache_key: str = "mcp_stats", application: str = ""):
    """Collect MCP usage statistics for the given time range and optional tool filter."""
    _get_config()
    if not GRAFANA_STATS_URL:
        logger.warning("Grafana stats not configured, skipping MCP stats collection")
        return None

    now = datetime.utcnow()
    time_from = str(int((now - timedelta(days=days)).timestamp() * 1000))
    time_to = str(int(now.timestamp() * 1000))

    if application:
        es_query = f"application:\"{application}\""
    else:
        es_query = ""

    # 1. Daily unique users
    daily_resp = _ds_query(
        bucket_aggs=[{"type": "date_histogram", "field": "timestamp", "id": "2", "settings": {"interval": "1d"}}],
        metrics=[{"type": "cardinality", "field": "username", "id": "1"}],
        query=es_query, time_from=time_from, time_to=time_to,
    )

    # 2. Requests by application (MCP tool) — only when not filtering by specific app
    apps_resp = None
    if not application:
        apps_resp = _ds_query(
            bucket_aggs=[
                {"type": "terms", "field": "application", "id": "4", "settings": {"size": "50", "order": "desc", "orderBy": "_count", "min_doc_count": "1"}},
            ],
            metrics=[{"type": "count", "id": "1"}],
            query=es_query, time_from=time_from, time_to=time_to,
        )

    # 3. Top functions
    funcs_resp = _ds_query(
        bucket_aggs=[
            {"type": "terms", "field": "function_name", "id": "4", "settings": {"size": "50", "order": "desc", "orderBy": "_count", "min_doc_count": "1"}},
        ],
        metrics=[{"type": "count", "id": "1"}],
        query=es_query, time_from=time_from, time_to=time_to,
    )

    # 4. Top users
    users_resp = _ds_query(
        bucket_aggs=[
            {"type": "terms", "field": "username", "id": "4", "settings": {"size": "100", "order": "desc", "orderBy": "_count", "min_doc_count": "1"}},
        ],
        metrics=[{"type": "count", "id": "1"}],
        query=es_query, time_from=time_from, time_to=time_to,
    )

    result = {
        "collected_at": now.isoformat() + "Z",
        "period_days": days,
        "total_requests": 0,
        "daily_users": [],
        "by_application": [],
        "by_function": [],
        "top_users": [],
    }

    # Parse daily users
    frames = _extract_frames(daily_resp)
    if frames:
        for frame in frames:
            schema_fields = frame.get("schema", {}).get("fields", [])
            data_values = frame.get("data", {}).get("values", [])
            if len(data_values) >= 2:
                timestamps = data_values[0]
                values = data_values[1]
                total = 0
                for i, ts in enumerate(timestamps):
                    dt = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
                    v = values[i] if i < len(values) else 0
                    result["daily_users"].append({"date": dt, "users": v, "requests": 0})
                    total += v
                result["total_requests"] = total

    # Parse applications
    frames = _extract_frames(apps_resp)
    if frames:
        for frame in frames:
            data_values = frame.get("data", {}).get("values", [])
            if len(data_values) >= 2:
                labels = data_values[0]
                counts = data_values[1]
                for i, label in enumerate(labels):
                    count = counts[i] if i < len(counts) else 0
                    result["by_application"].append({"name": label, "count": count})
                    result["total_requests"] += count

    # If we got app data, use that as total (more accurate than daily user cardinality sum)
    if result["by_application"]:
        result["total_requests"] = sum(a["count"] for a in result["by_application"])

    # Parse functions
    frames = _extract_frames(funcs_resp)
    if frames:
        for frame in frames:
            data_values = frame.get("data", {}).get("values", [])
            if len(data_values) >= 2:
                labels = data_values[0]
                counts = data_values[1]
                for i, label in enumerate(labels):
                    result["by_function"].append({"name": label, "count": counts[i] if i < len(counts) else 0})

    # Parse users
    frames = _extract_frames(users_resp)
    if frames:
        for frame in frames:
            data_values = frame.get("data", {}).get("values", [])
            if len(data_values) >= 2:
                labels = data_values[0]
                counts = data_values[1]
                for i, label in enumerate(labels):
                    result["top_users"].append({"username": label, "count": counts[i] if i < len(counts) else 0})

    # Also get daily request counts (separate query)
    if result["daily_users"] and not result["daily_users"][0].get("requests"):
        daily_req_resp = _ds_query(
            bucket_aggs=[{"type": "date_histogram", "field": "timestamp", "id": "2", "settings": {"interval": "1d"}}],
            metrics=[{"type": "count", "id": "1"}],
            query=es_query, time_from=time_from, time_to=time_to,
        )
        req_frames = _extract_frames(daily_req_resp)
        if req_frames:
            for frame in req_frames:
                data_values = frame.get("data", {}).get("values", [])
                if len(data_values) >= 2:
                    counts = data_values[1]
                    for i, c in enumerate(counts):
                        if i < len(result["daily_users"]):
                            result["daily_users"][i]["requests"] = c

    if application:
        result["by_application"] = [
            a for a in result["by_application"]
            if application.lower() in a["name"].lower()
        ]

    cache.set(cache_key, result, ttl=900)
    logger.info(
        "MCP stats collected (days=%d, key=%s): %d total requests, %d apps, %d users",
        days, cache_key, result["total_requests"],
        len(result["by_application"]), len(result["top_users"]),
    )
    return result
