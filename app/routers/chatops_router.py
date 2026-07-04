"""API endpoints for ChatOps Analytics data."""
import logging

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def chatops_summary(env: str = Query("production")):
    from app.collectors.chatops_collector import get_summary
    return get_summary(env) or {}


@router.get("/activity")
async def chatops_activity(env: str = Query("production")):
    from app.collectors.chatops_collector import get_activity
    return get_activity(env) or {}


@router.get("/channels")
async def chatops_channels(env: str = Query("production")):
    from app.collectors.chatops_collector import get_channels
    data = get_channels(env)
    if data and env in data:
        return data[env]
    return data or {}


@router.get("/mcp")
async def chatops_mcp(env: str = Query("production")):
    from app.collectors.chatops_collector import get_mcp
    data = get_mcp(env)
    if data and env in data:
        return data[env]
    return data or {}


@router.get("/health")
async def chatops_health():
    from app.collectors.chatops_collector import get_health
    return get_health() or {}


@router.get("/diagnostics")
async def chatops_diagnostics():
    """Test ChatOps OCP connectivity: pod discovery + all proxy URL formats."""
    from app.collectors.chatops_collector import diagnose
    return diagnose()
