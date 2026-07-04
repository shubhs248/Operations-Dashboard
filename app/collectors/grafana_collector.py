"""Collector for Grafana user login tracking and dashboard panels (Python 3.6+)."""
import logging
from datetime import datetime

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import config, cache

logger = logging.getLogger(__name__)


def _headers():
    h = {"Accept": "application/json"}
    if config.GRAFANA_API_KEY:
        h["Authorization"] = "Bearer {}".format(config.GRAFANA_API_KEY)
    return h


def _session():
    s = requests.Session()
    s.verify = False
    s.trust_env = False
    return s


# ── User Login Tracking ──

def collect_grafana_users():
    """Fetch all Grafana users and filter to non-admin, with last login timestamps."""
    base = config.GRAFANA_BASE_URL.rstrip("/") if config.GRAFANA_BASE_URL else ""

    if not base or not config.GRAFANA_API_KEY:
        logger.warning("Grafana not configured")
        cache.set("grafana:users", {"users": [], "summary": {}}, ttl=1800)
        return {}

    session = _session()
    headers = _headers()
    all_users = _fetch_all_users(session, base, headers)

    non_admin = [u for u in all_users if not u.get("isAdmin", False)]

    now = datetime.utcnow()
    active_7d = 0
    active_30d = 0
    inactive = 0
    never_logged = 0

    for user in non_admin:
        last_seen = user.get("lastSeenAt", "")
        if not last_seen or last_seen == "0001-01-01T00:00:00Z":
            user["_status"] = "never"
            user["_days_ago"] = None
            never_logged += 1
            continue

        try:
            seen_dt = datetime.strptime(last_seen[:19], "%Y-%m-%dT%H:%M:%S")
            days_ago = (now - seen_dt).days
            user["_days_ago"] = days_ago

            if days_ago <= 7:
                user["_status"] = "active_7d"
                active_7d += 1
            elif days_ago <= 30:
                user["_status"] = "active_30d"
                active_30d += 1
            else:
                user["_status"] = "inactive"
                inactive += 1
        except (ValueError, TypeError):
            user["_status"] = "unknown"
            user["_days_ago"] = None
            never_logged += 1

    users_clean = []
    for u in non_admin:
        users_clean.append({
            "id": u.get("id"),
            "login": u.get("login", ""),
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "lastSeenAt": u.get("lastSeenAt", ""),
            "lastSeenAtAge": u.get("lastSeenAtAge", ""),
            "isDisabled": u.get("isDisabled", False),
            "status": u.get("_status", "unknown"),
            "days_ago": u.get("_days_ago"),
            "authLabels": u.get("authLabels", []),
        })

    users_clean.sort(key=lambda x: x.get("lastSeenAt") or "", reverse=True)

    summary = {
        "total_users": len(non_admin),
        "active_7d": active_7d,
        "active_30d": active_30d,
        "inactive": inactive,
        "never_logged": never_logged,
        "collected_at": datetime.utcnow().isoformat() + "Z",
    }

    result = {"users": users_clean, "summary": summary}
    cache.set("grafana:users", result, ttl=600)
    logger.info("Grafana users collected: %d non-admin (%d active 7d, %d active 30d, %d inactive)",
                len(non_admin), active_7d, active_30d, inactive)
    return result


def _fetch_all_users(session, base, headers, page_size=1000):
    """Try /api/org/users first (Org Admin), fall back to /api/users (Server Admin)."""
    users = _try_org_users(session, base, headers)
    if users is not None:
        return users

    return _try_admin_users(session, base, headers, page_size)


def _try_org_users(session, base, headers):
    """Fetch from /api/org/users (requires Org Admin role)."""
    try:
        resp = session.get(
            "{}/api/org/users".format(base),
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            users = resp.json()
            mapped = []
            for u in users:
                mapped.append({
                    "id": u.get("userId", u.get("id")),
                    "login": u.get("login", ""),
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "isAdmin": u.get("role", "").lower() == "admin",
                    "isDisabled": False,
                    "lastSeenAt": u.get("lastSeenAt", ""),
                    "lastSeenAtAge": u.get("lastSeenAtAge", ""),
                    "authLabels": [u.get("role", "Viewer")],
                })
            logger.info("Fetched %d users from /api/org/users", len(mapped))
            return mapped
        logger.debug("/api/org/users returned %d, trying /api/users", resp.status_code)
    except Exception as e:
        logger.debug("/api/org/users failed: %s, trying /api/users", e)
    return None


def _try_admin_users(session, base, headers, page_size=1000):
    """Paginate through /api/users (requires Server Admin)."""
    all_users = []
    page = 1

    while True:
        try:
            resp = session.get(
                "{}/api/users".format(base),
                params={"perpage": page_size, "page": page},
                headers=headers,
                timeout=30,
            )
            if resp.status_code in (401, 403):
                logger.error("Grafana /api/users returned %d - need admin API key", resp.status_code)
                break
            if resp.status_code != 200:
                logger.warning("Grafana /api/users returned %d", resp.status_code)
                break

            users = resp.json()
            if not users:
                break
            all_users.extend(users)
            if len(users) < page_size:
                break
            page += 1
        except Exception as e:
            logger.error("Grafana user fetch failed: %s", e)
            break

    return all_users


# ── Panel Tracking (kept from before) ──

def collect_grafana_panels():
    """Collect user logins; only collect panels if UIDs are explicitly configured."""
    collect_grafana_users()
    if config.GRAFANA_DASHBOARD_UIDS:
        _collect_dashboard_panels()
    else:
        cache.set("grafana:panels", [], ttl=1800)


def _collect_dashboard_panels():
    base = config.GRAFANA_BASE_URL.rstrip("/") if config.GRAFANA_BASE_URL else ""
    uids = config.GRAFANA_DASHBOARD_UIDS

    if not base or not config.GRAFANA_API_KEY:
        cache.set("grafana:panels", [], ttl=1800)
        return []

    session = _session()
    headers = _headers()
    all_panels = []

    dash_uids = uids if uids else _search_dashboards(session, base, headers)

    for uid in dash_uids:
        panels = _fetch_dashboard_panels(session, base, headers, uid)
        all_panels.extend(panels)

    cache.set("grafana:panels", all_panels, ttl=1800)
    return all_panels


def _search_dashboards(session, base, headers):
    try:
        resp = session.get(
            "{}/api/search".format(base),
            params={"type": "dash-db", "limit": 20},
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            return [d["uid"] for d in resp.json() if "uid" in d]
    except Exception as e:
        logger.error("Grafana dashboard search failed: %s", e)
    return []


def _fetch_dashboard_panels(session, base, headers, uid):
    try:
        resp = session.get(
            "{}/api/dashboards/uid/{}".format(base, uid),
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        dash = data.get("dashboard", {})
        meta = data.get("meta", {})
        title = dash.get("title", uid)
        slug = meta.get("slug", uid)

        panels = []
        for panel in dash.get("panels", []):
            if panel.get("type") == "row":
                for sub in panel.get("panels", []):
                    panels.append(_format_panel(base, uid, slug, title, sub))
                continue
            panels.append(_format_panel(base, uid, slug, title, panel))
        return panels
    except Exception as e:
        logger.error("Failed to fetch dashboard %s: %s", uid, e)
        return []


def _format_panel(base, uid, slug, dash_title, panel):
    panel_id = panel.get("id", 0)
    return {
        "dashboard_uid": uid,
        "dashboard_title": dash_title,
        "panel_id": panel_id,
        "panel_title": panel.get("title", "Untitled"),
        "panel_type": panel.get("type", "unknown"),
        "embed_url": "{}/d-solo/{}/{}?panelId={}&theme=dark".format(base, uid, slug, panel_id),
    }
