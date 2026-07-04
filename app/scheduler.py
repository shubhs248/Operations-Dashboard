"""APScheduler background tasks for periodic data collection."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = None


def _collect_mcp():
    try:
        from app.collectors.mcp_collector import collect_all_mcp_metrics
        from app import cache, database
        collect_all_mcp_metrics()
        data = cache.get("mcp_metrics")
        if data:
            database.save_snapshot("mcp", {"servers": data, "summary": {"count": len(data)}})
        logger.info("MCP metrics collected")
    except Exception as e:
        logger.error("MCP collection failed: %s", e)


def _collect_jira():
    try:
        from app.collectors.jira_collector import collect_jira_data
        from app import cache, database
        collect_jira_data()
        data = cache.get("jira_issues")
        if data:
            database.save_snapshot("jira", {"issues": data})
        logger.info("Jira data collected")
    except Exception as e:
        logger.error("Jira collection failed: %s", e)


def _collect_grafana():
    try:
        from app.collectors.grafana_collector import collect_grafana_panels
        from app import cache, database
        collect_grafana_panels()
        data = cache.get("grafana_users")
        if data:
            summary = data.get("summary", {}) if isinstance(data, dict) else {}
            users = data.get("users", []) if isinstance(data, dict) else data
            database.save_snapshot("grafana_users", {"users": users, "summary": summary})
        logger.info("Grafana panels collected")
    except Exception as e:
        logger.error("Grafana collection failed: %s", e)


def _collect_mcp_stats():
    try:
        from app.config import get_settings
        from app import ocp_token_manager
        settings = get_settings()
        token = ocp_token_manager.get_token() or settings.ocp_token
        if token:
            from app.collectors.ocp_mcp_collector import collect_ocp_mcp_stats
            collect_ocp_mcp_stats(days=1, cache_key="mcp_stats_1", persist=True)
            logger.info("MCP stats 1d done — starting 2d+3d")
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futs = {
                    pool.submit(collect_ocp_mcp_stats, days=2, cache_key="mcp_stats_2", persist=False): "2d",
                    pool.submit(collect_ocp_mcp_stats, days=3, cache_key="mcp_stats_3", persist=False): "3d",
                }
                for f in concurrent.futures.as_completed(futs, timeout=600):
                    try:
                        f.result()
                    except Exception as e:
                        logger.error("MCP stats %s failed: %s", futs[f], e)
            logger.info("MCP stats collected from OCP pod logs (1d + 2d + 3d)")
        else:
            from app.collectors.mcp_stats_collector import collect_mcp_stats
            collect_mcp_stats(days=30, cache_key="mcp_stats_30")
            logger.info("MCP stats collected from Grafana ES")
    except Exception as e:
        logger.error("MCP stats collection failed: %s", e)


def _collect_chatops():
    try:
        from app.collectors.chatops_collector import get_summary, get_activity, get_channels, get_mcp
        get_summary("production")
        get_activity("production")
        get_channels("production")
        get_mcp("production")
        logger.info("ChatOps data collected and persisted")
    except Exception as e:
        logger.error("ChatOps collection failed: %s", e)


def _collect_ocp_status():
    try:
        from app.routers.mcp_router import _collect_ocp_server_status
        _collect_ocp_server_status(days=1)
        logger.info("OCP pod status collected")
    except Exception as e:
        logger.error("OCP pod status collection failed: %s", e)


def _refresh_ocp_token():
    try:
        from app import ocp_token_manager
        refreshed = ocp_token_manager.refresh_if_needed()
        if refreshed:
            logger.info("OCP token refreshed by scheduler")
        chatops_refreshed = ocp_token_manager.refresh_chatops_if_needed()
        if chatops_refreshed:
            logger.info("ChatOps token refreshed by scheduler")
    except Exception as e:
        logger.error("OCP token refresh failed: %s", e)


def _cleanup_mcp_usage():
    try:
        from app import database
        database.cleanup_mcp_usage(keep_days=7)
    except Exception as e:
        logger.error("MCP usage cleanup failed: %s", e)


def start_scheduler(poll_interval=300):
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_collect_mcp, "interval", seconds=poll_interval, id="mcp", max_instances=1)
    _scheduler.add_job(_collect_jira, "interval", seconds=poll_interval * 2, id="jira", max_instances=1)
    _scheduler.add_job(_collect_grafana, "interval", seconds=poll_interval * 2, id="grafana", max_instances=1)
    _scheduler.add_job(_collect_mcp_stats, "interval", seconds=poll_interval, id="mcp_stats", max_instances=1)
    _scheduler.add_job(_collect_ocp_status, "interval", seconds=poll_interval, id="ocp_status", max_instances=1)
    _scheduler.add_job(_collect_chatops, "interval", seconds=poll_interval * 2, id="chatops", max_instances=1)
    _scheduler.add_job(_refresh_ocp_token, "interval", seconds=3600, id="ocp_token", max_instances=1)
    _scheduler.add_job(_cleanup_mcp_usage, "cron", hour=3, minute=0, id="mcp_usage_cleanup", max_instances=1)
    _scheduler.start()
    logger.info("Scheduler started (MCP health every %ds, MCP stats every %ds, Jira/Grafana every %ds, token check every 1h)", poll_interval, poll_interval, poll_interval * 2)

    # Initial collection after short delay
    import threading
    threading.Timer(3.0, _initial_collect).start()


def _initial_collect():
    import concurrent.futures
    logger.info("Running initial data collection (parallel)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_collect_mcp_stats): "mcp_stats",
            pool.submit(_collect_mcp): "mcp",
            pool.submit(_collect_jira): "jira",
            pool.submit(_collect_grafana): "grafana",
            pool.submit(_collect_chatops): "chatops",
        }
        for future in concurrent.futures.as_completed(futures, timeout=600):
            name = futures[future]
            try:
                future.result()
                logger.info("Initial %s collection done", name)
            except Exception as e:
                logger.error("Initial %s collection failed: %s", name, e)

    # OCP status depends on cached MCP stats; run after stats are ready
    try:
        _collect_ocp_status()
        logger.info("Initial ocp_status collection done")
    except Exception as e:
        logger.error("Initial ocp_status collection failed: %s", e)


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
