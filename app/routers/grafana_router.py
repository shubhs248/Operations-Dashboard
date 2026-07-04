from fastapi import APIRouter, Query
from app import cache

router = APIRouter()


@router.get("/panels")
async def grafana_panels(dashboard_uid: str | None = Query(None)):
    panels = cache.get("grafana:panels") or []
    if dashboard_uid:
        panels = [p for p in panels if p["dashboard_uid"] == dashboard_uid]
    return {"panels": panels}


@router.get("/users")
async def grafana_users(status: str | None = Query(None)):
    data = cache.get("grafana:users") or {"users": [], "summary": {}}
    users = data.get("users", [])
    if status:
        users = [u for u in users if u.get("status") == status]
    return {"users": users, "summary": data.get("summary", {})}
