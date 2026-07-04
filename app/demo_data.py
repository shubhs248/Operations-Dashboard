"""Demo-mode data seeding.

When ``DEMO_MODE=true`` the app skips every live collector (OCP/K8s, Jira,
Grafana, ChatOps) and instead serves the realistic mock payloads generated
here. This lets anyone run the full dashboard locally with zero credentials
and zero external systems — ideal for a portfolio walkthrough.

The mock data is written straight into the cache layer using the exact keys
and shapes the API routers expect, so every tab renders as it would in
production.
"""
import random
from datetime import datetime, timezone, timedelta

from app import cache

# Effectively "never expires" during a demo session.
_TTL = 10 * 365 * 24 * 3600

_TOOLS = ["nexus", "bitbucket", "artifactory", "jenkins", "ocp", "eaas"]

_TOOL_FUNCTIONS = {
    "nexus": ["search_artifacts", "list_repositories", "get_system_status",
              "check_filesystem_space", "rebuild_index"],
    "bitbucket": ["get_pull_requests", "search_bitbucket", "get_commit_details",
                  "scan_pr_secrets", "manage_branches", "pr_analytics"],
    "artifactory": ["artifactory_search", "artifactory_aql_query", "artifactory_get",
                    "artifactory_cleanup_policy"],
    "jenkins": ["jenkins_jobs", "jenkins_builds", "jenkins_build_log_snapshot",
                "jenkins_queue", "jenkins_nodes"],
    "ocp": ["get_current_cluster_state", "get_not_running_pods", "get_nodes",
            "get_cpu_ram_requests_limits_per_namespace", "oc_run"],
    "eaas": ["get_vapps", "power_on_vapp", "create_vapp_from_template",
             "check_vm_connectivity", "get_vm_performance_metrics"],
}

_USERS = [
    "jsmith", "apatel", "mwang", "rgomez", "lchen", "kdubois", "ssingh",
    "torourke", "nkowalski", "fbianchi", "hokafor", "ymoreau",
]


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat()


# ── MCP pod health ──────────────────────────────────────────────
def _build_pod_health():
    """One deliberately-critical and one warning pod so the health scoring,
    alerting story, and charts all have something to show."""
    now = datetime.utcnow()
    specs = [
        # tool, status, restarts, age_hours, ready, mem_pct, cpu_m, mem_mib
        ("nexus",       "up", 1,  620.0, True,  61.0, 145, 512),
        ("bitbucket",   "up", 18, 300.0, True,  84.0, 210, 860),   # warning: memory > 80%
        ("artifactory", "up", 0,  700.0, True,  55.0, 120, 430),
        ("jenkins",     "up", 2,  540.0, True,  68.0, 260, 720),
        ("ocp",         "up", 0,  680.0, True,  40.0,  90, 300),
        ("eaas",        "up", 0,  210.0, True,  96.5, 180, 985),   # critical: memory
    ]
    servers = []
    for tool, status, restarts, age_h, ready, mem_pct, cpu_m, mem_mib in specs:
        rate = restarts / max(age_h / 24, 0.042)
        if status != "up" or mem_pct > 95:
            health = "critical"
        elif rate > 4 or (mem_pct > 80) or not ready:
            health = "warning"
        else:
            health = "healthy"
        d, h = divmod(int(age_h), 24)
        servers.append({
            "name": f"{tool}-mcp-7d{random.randint(100,999)}-{random.choice('abcdef')}{random.randint(1000,9999)}",
            "namespace": f"{tool}-mcp",
            "container": f"{tool}-mcp",
            "host": f"{tool}-mcp/{tool}-mcp-pod",
            "port": 8000,
            "status": status,
            "restarts": restarts,
            "age": f"{d}d {h}h" if d else f"{h}h",
            "age_hours": age_h,
            "ready": ready,
            "cpu_limit": 500,
            "cpu_request": 100,
            "memory_limit": 1024,
            "memory_request": 256,
            "cpu_millicores": cpu_m,
            "memory_mib": mem_mib,
            "memory_pct": mem_pct,
            "health": health,
            "tool": tool,
            "request_count": 0,
            "checked_at": _iso(now),
        })
    return servers


def _pod_summary(servers):
    up = sum(1 for s in servers if s["status"] == "up")
    return {
        "servers_up": up,
        "servers_down": len(servers) - up,
        "total_pods": len(servers),
        "healthy_pods": sum(1 for s in servers if s["health"] == "healthy"),
        "warning_pods": sum(1 for s in servers if s["health"] == "warning"),
        "critical_pods": sum(1 for s in servers if s["health"] == "critical"),
        "total_requests": sum(s["request_count"] for s in servers),
        "total_tool_calls": sum(s["request_count"] for s in servers),
        "tools_active": len({s["tool"] for s in servers}),
        "total_cpu_millicores": sum(s["cpu_millicores"] for s in servers),
        "total_memory_mib": sum(s["memory_mib"] for s in servers),
        "total_restarts": sum(s["restarts"] for s in servers),
        "collected_at": _iso(datetime.utcnow()),
    }


# ── MCP usage stats ─────────────────────────────────────────────
def _build_mcp_stats(days):
    random.seed(days)  # stable per-period
    by_application, func_tool_map, by_function = [], {}, []
    per_tool_calls = {}
    for tool in _TOOLS:
        base = random.randint(180, 900) * days
        per_tool_calls[tool] = base
        by_application.append({"name": tool, "count": base})
        fns = _TOOL_FUNCTIONS[tool]
        remaining = base
        for i, fn in enumerate(fns):
            func_tool_map[fn] = tool
            c = remaining // (len(fns) - i) if i < len(fns) - 1 else remaining
            c = max(1, int(c * random.uniform(0.6, 1.4)))
            remaining = max(0, remaining - c)
            by_function.append({"name": fn, "count": c})
    by_application.sort(key=lambda x: -x["count"])
    by_function.sort(key=lambda x: -x["count"])
    total = sum(a["count"] for a in by_application)

    # Per-user function usage
    all_user_functions, top_users = {}, []
    for user in _USERS:
        n_tools = random.randint(1, 3)
        user_tools = random.sample(_TOOLS, n_tools)
        fns = {}
        for tool in user_tools:
            for fn in random.sample(_TOOL_FUNCTIONS[tool], random.randint(1, len(_TOOL_FUNCTIONS[tool]))):
                fns[fn] = random.randint(3, 60) * days
        all_user_functions[user] = fns
        count = sum(fns.values())
        top = sorted(fns.items(), key=lambda x: -x[1])[:5]
        top_users.append({
            "username": user,
            "count": count,
            "top_functions": [
                {"name": fn, "count": c, "pct": round(c / count * 100, 1)}
                for fn, c in top
            ],
            "tools_used": user_tools,
        })
    top_users.sort(key=lambda u: -u["count"])

    # Daily time-series
    daily_users = []
    today = datetime.utcnow().date()
    for i in range(days * (24 if days == 1 else 1)):
        if days == 1:
            label = f"{today}T{i:02d}:00"
            bucket = {t: max(0, int(per_tool_calls[t] / 24 * random.uniform(0.4, 1.6))) for t in _TOOLS}
        else:
            day = today - timedelta(days=days - 1 - i)
            label = str(day)
            bucket = {t: max(0, int(per_tool_calls[t] / days * random.uniform(0.5, 1.5))) for t in _TOOLS}
        daily_users.append({
            "date": label,
            "users": random.randint(6, len(_USERS)),
            "requests": sum(bucket.values()),
            "by_tool": bucket,
        })

    return {
        "collected_at": _iso(datetime.utcnow()),
        "period_days": days,
        "total_requests": total,
        "total_tool_calls": total,
        "by_application": by_application,
        "by_function": by_function,
        "top_users": top_users,
        "all_user_functions": all_user_functions,
        "func_tool_map": func_tool_map,
        "daily_users": daily_users,
    }


# ── Jira ────────────────────────────────────────────────────────
def _build_jira():
    random.seed(7)
    projects = ["DEVOPS", "EAAS", "CLOUD"]
    types = ["Bug", "Support", "Task", "Incident", "Change"]
    priorities = ["Critical", "Major", "Minor", "Trivial"]
    statuses = [("Open", "To Do"), ("In Progress", "In Progress"),
                ("Resolved", "Done"), ("Closed", "Done")]
    summaries = [
        "MCP pod restarting repeatedly", "Add self-service repo cleanup policy",
        "Grafana dashboard access request", "Pipeline fails on artifact upload",
        "Increase memory limit for tool pod", "Token auto-refresh not triggering",
        "Onboard new team to platform", "Slow response from search endpoint",
        "Add alert routing for new namespace", "Document runbook for token expiry",
    ]
    issues = []
    now = datetime.utcnow()
    for n in range(140):
        proj = random.choice(projects)
        created = now - timedelta(days=random.randint(0, 330))
        status, cat = random.choice(statuses)
        tool = random.choice(_TOOLS + ["platform", "grafana"])
        issues.append({
            "key": f"{proj}-{1000 + n}",
            "summary": random.choice(summaries),
            "type": random.choice(types),
            "priority": random.choice(priorities),
            "status": status,
            "status_category": cat,
            "assignee": random.choice(_USERS),
            "tool": tool,
            "created": created.strftime("%Y-%m-%d"),
            "created_month": created.strftime("%Y-%m"),
            "url": f"https://jira.example.com/browse/{proj}-{1000 + n}",
        })
    return {"issues": issues}


# ── Grafana users ───────────────────────────────────────────────
def _build_grafana():
    random.seed(11)
    auth_options = [["OAuth"], ["LDAP"], ["Basic"]]
    users = []
    now = datetime.utcnow()
    for i in range(64):
        roll = random.random()
        if roll < 0.35:
            days_ago = random.randint(0, 7); status = "active_7d"
        elif roll < 0.65:
            days_ago = random.randint(8, 30); status = "active_30d"
        elif roll < 0.9:
            days_ago = random.randint(31, 200); status = "inactive"
        else:
            days_ago = None; status = "never"
        last_seen = "0001-01-01T00:00:00Z" if days_ago is None else _iso(now - timedelta(days=days_ago))
        login = f"{random.choice('abcdefghijklm')}{random.choice(_USERS)}{i}"
        users.append({
            "login": login,
            "name": login.replace(".", " ").title(),
            "email": f"{login}@example.com",
            "status": status,
            "days_ago": days_ago,
            "lastSeenAt": last_seen,
            "authLabels": random.choice(auth_options),
        })
    summary = {
        "total_users": len(users),
        "active_7d": sum(1 for u in users if u["status"] == "active_7d"),
        "active_30d": sum(1 for u in users if u["status"] == "active_30d"),
        "inactive": sum(1 for u in users if u["status"] == "inactive"),
        "never_logged": sum(1 for u in users if u["status"] == "never"),
    }
    return {"users": users, "summary": summary}


# ── ChatOps analytics ───────────────────────────────────────────
def _build_chatops():
    random.seed(23)
    today = datetime.utcnow().date()
    daily = []
    for i in range(45):
        day = today - timedelta(days=44 - i)
        daily.append({
            "date": str(day),
            "users": random.randint(15, 55),
            "requests": random.randint(120, 480),
            "mcp_calls": random.randint(40, 220),
            "mails_sent": random.randint(10, 90),
            "errors": random.randint(0, 4),
        })
    total_mcp = sum(d["mcp_calls"] for d in daily)
    summary = {
        "teams_messages": sum(d["requests"] for d in daily),
        "unique_users": 78,
        "errors_5xx": sum(d["errors"] for d in daily),
        "mail": {"mails_sent": sum(d["mails_sent"] for d in daily)},
    }
    activity = {"daily": daily, "total_users": 78, "mail": {"mails_sent": summary["mail"]["mails_sent"]}}
    channels = {
        "mail_forward": {"messages": 3120, "pct": 41.0},
        "teams_direct": {"messages": 2560, "pct": 33.7},
        "mail_direct": {"messages": 1180, "pct": 15.5},
        "teams_forward": {"messages": 740, "pct": 9.8},
        "total_messages": 7600,
    }
    mcp = {
        "total_calls": total_mcp,
        "adoption": {"pct": 62, "mcp_users": 48, "total_users": 78},
        "tools": [{"tool": t, "count": random.randint(120, 900)} for t in _TOOLS],
    }
    health = {
        "services": [
            {"name": "ChatOps Analytics API", "env": "prod", "status": "ok"},
            {"name": "ChatOps Pod", "env": "prod", "status": "Running",
             "restarts": 1, "ready": True, "age": "12d 4h"},
        ],
        "pod": {"name": "chatops-analytics-api-abc123", "phase": "Running",
                "restarts": 1, "ready": True, "age": "12d 4h"},
    }
    return summary, activity, channels, mcp, health


def seed_demo_cache():
    """Populate every cache key the routers read with mock data."""
    servers = _build_pod_health()
    summary = _pod_summary(servers)
    for days in (1, 2, 3):
        cache.set(f"mcp:ocp_status_{days}", {"servers": servers, "summary": summary}, ttl=_TTL)
    cache.set("mcp:tools", _TOOLS, ttl=_TTL)

    for days in (1, 2, 3):
        stats = _build_mcp_stats(days)
        cache.set(f"mcp_stats_{days}", stats, ttl=_TTL)
        # Backfill request counts into pod health for the 1d view
        if days == 1:
            counts = {a["name"]: a["count"] for a in stats["by_application"]}
            for s in servers:
                s["request_count"] = counts.get(s["tool"], 0)
            summary["total_requests"] = summary["total_tool_calls"] = sum(counts.values())
            cache.set("mcp:ocp_status_1", {"servers": servers, "summary": summary}, ttl=_TTL)

    cache.set("jira:all", _build_jira(), ttl=_TTL)
    cache.set("grafana:users", _build_grafana(), ttl=_TTL)
    cache.set("grafana:panels", [], ttl=_TTL)

    s, a, c, m, h = _build_chatops()
    cache.set("chatops:data:production", s, ttl=_TTL)
    cache.set("chatops:activity:production", a, ttl=_TTL)
    cache.set("chatops:channels:production", c, ttl=_TTL)
    cache.set("chatops:mcp:production", m, ttl=_TTL)
    cache.set("chatops:health", h, ttl=_TTL)
