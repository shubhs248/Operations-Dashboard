import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.database import init_db
from app.cache import init_cache
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    os.makedirs("data", exist_ok=True)
    init_cache(settings.redis_url)
    from app.cache import clear as clear_cache
    clear_cache()
    logger.info("Cleared stale cache on startup")
    init_db(settings.database_url)

    if settings.demo_mode:
        from app.demo_data import seed_demo_cache
        seed_demo_cache()
        logger.info("DEMO MODE enabled — seeded mock data, live collectors disabled")
        logger.info("Platform Operations Dashboard started on %s:%d", settings.app_host, settings.app_port)
        yield
        logger.info("Dashboard shutting down")
        return

    from app import ocp_token_manager
    ocp_token_manager.init(
        api_url=settings.ocp_api_url,
        static_token=settings.ocp_token,
        sa_user=settings.ocp_sa_user,
        sa_password=settings.ocp_sa_password,
        refresh_hours=settings.ocp_token_refresh_hours,
    )
    ocp_token_manager.init_chatops(
        api_url=settings.ocp_chatops_api_url,
        static_token=settings.ocp_chatops_token,
        sa_user=settings.ocp_chatops_sa_user or settings.ocp_sa_user,
        sa_password=settings.ocp_chatops_sa_password or settings.ocp_sa_password,
        refresh_hours=settings.ocp_token_refresh_hours,
    )
    start_scheduler(poll_interval=settings.mcp_poll_interval_seconds)
    logger.info("Platform Operations Dashboard started on %s:%d", settings.app_host, settings.app_port)
    yield
    stop_scheduler()
    logger.info("Dashboard shutting down")


app = FastAPI(title="Platform Operations Dashboard", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

from app.routers import dashboard_router, mcp_router, jira_router, grafana_router, mcp_stats_router  # noqa: E402
from app.routers import chatops_router  # noqa: E402

app.include_router(dashboard_router.router)
app.include_router(mcp_router.router, prefix="/api/mcp", tags=["MCP"])
app.include_router(mcp_stats_router.router, prefix="/api/mcp-stats", tags=["MCP Stats"])
app.include_router(jira_router.router, prefix="/api/jira", tags=["Jira"])
app.include_router(grafana_router.router, prefix="/api/grafana", tags=["Grafana"])
app.include_router(chatops_router.router, prefix="/api/chatops", tags=["ChatOps"])


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "public, max-age=60"
    elif path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return response


@app.get("/api/meta")
def meta():
    return {"demo_mode": get_settings().demo_mode, "version": "1.1"}


@app.post("/api/refresh")
def force_refresh():
    if get_settings().demo_mode:
        from app.demo_data import seed_demo_cache
        seed_demo_cache()
        return {"success": True, "errors": [], "demo": True}

    import concurrent.futures
    from app.collectors.mcp_collector import collect_all_mcp_metrics
    from app.collectors.jira_collector import collect_jira_data
    from app.collectors.grafana_collector import collect_grafana_panels
    from app.collectors.chatops_collector import get_summary as chatops_refresh_summary

    def _refresh_mcp_stats():
        settings = get_settings()
        if settings.ocp_token:
            from app.collectors.ocp_mcp_collector import collect_ocp_mcp_stats
            collect_ocp_mcp_stats(days=1, cache_key="mcp_stats_1")
            collect_ocp_mcp_stats(days=2, cache_key="mcp_stats_2")
            collect_ocp_mcp_stats(days=3, cache_key="mcp_stats_3")

    def _refresh_ocp_status():
        from app.routers.mcp_router import _collect_ocp_server_status
        _collect_ocp_server_status(days=1)

    collectors = {
        "mcp": collect_all_mcp_metrics,
        "jira": collect_jira_data,
        "grafana": collect_grafana_panels,
        "chatops": lambda: chatops_refresh_summary("production"),
        "mcp_stats": _refresh_mcp_stats,
        "ocp_status": _refresh_ocp_status,
    }

    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn): name for name, fn in collectors.items()}
        for future in concurrent.futures.as_completed(futures, timeout=600):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                errors.append(f"{name}: {e}")

    return {"success": len(errors) == 0, "errors": errors}


def main():
    import uvicorn
    settings = get_settings()
    workers = int(os.environ.get("WEB_WORKERS", 4))
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=1 if settings.debug else workers,
        reload=settings.debug,
        log_level="info",
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    main()
