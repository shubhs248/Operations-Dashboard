from fastapi import APIRouter, Request
from datetime import datetime, timedelta
from collections import defaultdict
from app import cache

router = APIRouter()


def _get_filtered_issues(request: Request) -> list:
    data = cache.get("jira:all")
    if not data:
        return []

    issues = data.get("issues", [])

    project = request.query_params.get("project", "").upper()
    if project:
        issues = [i for i in issues if i.get("key", "").startswith(project + "-")]

    days = int(request.query_params.get("days", 0))
    date_from = request.query_params.get("from", "")
    date_to = request.query_params.get("to", "")

    if date_from and date_to:
        return [i for i in issues if date_from <= i.get("created", "") <= date_to]
    elif days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return [i for i in issues if i.get("created", "") >= cutoff]
    return issues


@router.get("/trends")
async def jira_trends(request: Request):
    issues = _get_filtered_issues(request)
    monthly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in issues:
        m = i.get("created_month", "unknown")
        monthly[m]["total"] += 1
        monthly[m][i.get("type", "Other")] += 1

    trends = sorted(
        [{"month": m, **dict(counts)} for m, counts in monthly.items()],
        key=lambda x: x["month"],
    )
    return {"trends": trends}


@router.get("/by-tool")
async def jira_by_tool(request: Request):
    issues = _get_filtered_issues(request)
    by_tool: dict[str, int] = defaultdict(int)
    for i in issues:
        by_tool[i.get("tool", "Other")] += 1

    tool_dist = sorted(
        [{"tool": t, "count": c} for t, c in by_tool.items()],
        key=lambda x: -x["count"],
    )
    return {"by_tool": tool_dist}


@router.get("/open")
async def jira_open(request: Request):
    issues = _get_filtered_issues(request)
    by_type: dict[str, int] = defaultdict(int)
    by_priority: dict[str, int] = defaultdict(int)
    open_count = 0
    resolved_count = 0

    for i in issues:
        by_type[i.get("type", "Other")] += 1
        by_priority[i.get("priority", "None")] += 1
        if i.get("status_category") in ("Done", "Complete"):
            resolved_count += 1
        else:
            open_count += 1

    return {"open_summary": {
        "total_issues": len(issues),
        "open": open_count,
        "resolved": resolved_count,
        "by_type": dict(by_type),
        "by_priority": dict(by_priority),
    }}


@router.get("/issues")
async def jira_issues(request: Request):
    issues = _get_filtered_issues(request)
    return {"issues": issues, "total": len(issues)}


@router.get("/projects")
async def jira_projects():
    data = cache.get("jira:all")
    if not data:
        return {"projects": []}
    issues = data.get("issues", [])
    from collections import Counter
    proj_counts = Counter(i.get("key", "").split("-")[0] for i in issues if "-" in i.get("key", ""))
    projects = sorted(
        [{"key": k, "count": c} for k, c in proj_counts.items()],
        key=lambda x: -x["count"],
    )
    return {"projects": projects}
