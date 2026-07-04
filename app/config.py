"""Configuration using Pydantic Settings with backward-compatible attribute access."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 9100
    debug: bool = False
    db_path: str = "data/dashboard.db"

    # Demo mode: seed the cache with realistic mock data and skip all live
    # collectors. Lets the dashboard run with zero external systems/credentials.
    demo_mode: bool = False

    database_url: str = ""
    redis_url: str = ""

    jira_base_url: str = "https://jira"
    jira_username: str = ""
    jira_api_token: str = ""
    jira_projects: str = "DEVOPS,EAAS,CLOUD"

    grafana_base_url: str = ""
    grafana_api_key: str = ""
    grafana_dashboard_uids: str = ""

    grafana_stats_url: str = ""
    grafana_stats_user: str = "readonly"
    grafana_stats_password: str = "readonly"

    ocp_api_url: str = "https://console-openshift-console.apps.ocp-cluster.example.com/api/kubernetes"
    ocp_token: str = ""
    ocp_sa_user: str = ""
    ocp_sa_password: str = ""
    ocp_token_refresh_hours: int = 12
    ocp_mcp_tools: str = "nexus,bitbucket,artifactory,jenkins,ocp,eaas"

    mcp_servers: str = "mcp-host.example.com:8000"
    mcp_poll_interval_seconds: int = 300

    ocp_chatops_api_url: str = "https://console-openshift-console.apps.analytics-cluster.example.com/api/kubernetes"
    ocp_chatops_token: str = ""
    ocp_chatops_namespace: str = "chatops-analytics"
    ocp_chatops_sa_user: str = ""
    ocp_chatops_sa_password: str = ""

    deploy_host: str = "dashboard-host.example.com"

    # Alerting
    alert_enabled: bool = True
    alert_smtp_host: str = "smtp.example.com"
    alert_smtp_port: int = 25
    alert_from: str = "platform-dashboard@example.com"
    alert_default_to: str = ""
    alert_cc: str = ""
    alert_owners: str = ""
    alert_cooldown_hours: int = 6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def jira_project_list(self) -> list[str]:
        return [p.strip() for p in self.jira_projects.split(",") if p.strip()]

    @property
    def grafana_uid_list(self) -> list[str]:
        return [u.strip() for u in self.grafana_dashboard_uids.split(",") if u.strip()]

    @property
    def alert_owner_map(self) -> dict[str, list[str]]:
        result = {}
        if not self.alert_owners:
            return result
        for entry in self.alert_owners.split(","):
            entry = entry.strip()
            if ":" not in entry:
                continue
            tool, emails = entry.split(":", 1)
            result[tool.strip().lower()] = [e.strip() for e in emails.split(";") if e.strip()]
        return result

    def mcp_server_list(self) -> list[dict]:
        servers = []
        for entry in self.mcp_servers.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 8000
            servers.append({"host": host, "port": port, "url": f"http://{host}:{port}"})
        return servers


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Backward-compatible attribute access for collectors
_s = get_settings()

APP_HOST = _s.app_host
APP_PORT = _s.app_port
DEBUG = _s.debug
DB_PATH = _s.db_path

JIRA_BASE_URL = _s.jira_base_url
JIRA_USERNAME = _s.jira_username
JIRA_API_TOKEN = _s.jira_api_token
JIRA_PROJECTS = _s.jira_project_list

GRAFANA_BASE_URL = _s.grafana_base_url
GRAFANA_API_KEY = _s.grafana_api_key
GRAFANA_DASHBOARD_UIDS = _s.grafana_uid_list

MCP_SERVERS_RAW = _s.mcp_servers
MCP_POLL_INTERVAL = _s.mcp_poll_interval_seconds

DEPLOY_HOST = _s.deploy_host


def mcp_server_list():
    return _s.mcp_server_list()
