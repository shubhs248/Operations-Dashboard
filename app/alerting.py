"""Pod health alerting via email (SMTP).

Sends one email per incident (tool + health state). Tracks sent alerts
in memory with a configurable cooldown so the same issue doesn't spam
recipients.
"""
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import get_settings

logger = logging.getLogger(__name__)

_sent_alerts: dict[str, datetime] = {}


def _recipients_for_tool(tool: str) -> list[str]:
    settings = get_settings()
    owner_map = settings.alert_owner_map
    recipients = owner_map.get(tool.lower(), [])
    if not recipients and settings.alert_default_to:
        recipients = [e.strip() for e in settings.alert_default_to.split(";") if e.strip()]
    return recipients


def _alert_key(tool: str, health: str) -> str:
    return f"{tool.lower()}:{health.lower()}"


def _is_on_cooldown(key: str) -> bool:
    settings = get_settings()
    last_sent = _sent_alerts.get(key)
    if not last_sent:
        return False
    return datetime.utcnow() - last_sent < timedelta(hours=settings.alert_cooldown_hours)


def _build_email(tool: str, health: str, pods: list[dict]) -> MIMEMultipart:
    settings = get_settings()
    severity = "CRITICAL" if health == "critical" else "WARNING"
    subject = f"[Platform Dashboard] {severity}: {tool.upper()} MCP pod health alert"

    pod_rows = ""
    for p in pods:
        pod_rows += (
            f"  - {p.get('name', 'unknown')}: {p.get('health', health).upper()}, "
            f"restarts={p.get('restarts', 0)}, ready={p.get('ready', False)}, "
            f"age={p.get('age', 'N/A')}\n"
        )

    body = f"""Platform Operations Dashboard — Pod Health Alert

Tool:     {tool.upper()}
Status:   {severity}
Time:     {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Affected pods:
{pod_rows}
Dashboard: http://{settings.deploy_host}:{settings.app_port}

---
This alert fires once per incident. Next alert for this tool/state
will be suppressed for {settings.alert_cooldown_hours} hours.
"""

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.alert_from
    msg.attach(MIMEText(body, "plain"))
    return msg


def _cc_list() -> list[str]:
    settings = get_settings()
    if not settings.alert_cc:
        return []
    return [e.strip() for e in settings.alert_cc.split(";") if e.strip()]


def _send_email(msg: MIMEMultipart, to_list: list[str]):
    settings = get_settings()
    cc = _cc_list()
    msg["To"] = ", ".join(to_list)
    if cc:
        msg["Cc"] = ", ".join(cc)
    all_recipients = to_list + [e for e in cc if e not in to_list]
    try:
        with smtplib.SMTP(settings.alert_smtp_host, settings.alert_smtp_port, timeout=15) as smtp:
            smtp.sendmail(settings.alert_from, all_recipients, msg.as_string())
        logger.info("Alert email sent to=%s cc=%s: %s", to_list, cc, msg["Subject"])
    except Exception as e:
        logger.error("Failed to send alert email to %s: %s", all_recipients, e)


def check_and_alert(servers: list[dict]):
    """Evaluate pod health and send alerts for warning/critical tools.

    Called after each OCP status collection cycle. Groups pods by tool,
    checks for warning/critical health, and sends one email per tool+state
    if not on cooldown.
    """
    settings = get_settings()
    if not settings.alert_enabled:
        return

    if not settings.alert_default_to and not settings.alert_owners:
        return

    tool_pods: dict[str, list[dict]] = {}
    for s in servers:
        tool = s.get("tool", "unknown")
        tool_pods.setdefault(tool, []).append(s)

    for tool, pods in tool_pods.items():
        critical = [p for p in pods if p.get("health") == "critical"]
        warning = [p for p in pods if p.get("health") == "warning"]

        for health, affected in [("critical", critical), ("warning", warning)]:
            if not affected:
                continue

            key = _alert_key(tool, health)
            if _is_on_cooldown(key):
                continue

            recipients = _recipients_for_tool(tool)
            if not recipients:
                logger.debug("No alert recipients configured for tool=%s", tool)
                continue

            msg = _build_email(tool, health, affected)
            _send_email(msg, recipients)
            _sent_alerts[key] = datetime.utcnow()


def clear_alert(tool: str, health: str):
    """Remove cooldown for a tool+health when the issue resolves."""
    key = _alert_key(tool, health)
    _sent_alerts.pop(key, None)


def check_resolved(servers: list[dict]):
    """Clear cooldowns for tools that have returned to healthy."""
    tool_health: dict[str, set[str]] = {}
    for s in servers:
        tool = s.get("tool", "unknown")
        tool_health.setdefault(tool, set()).add(s.get("health", "healthy"))

    for tool, states in tool_health.items():
        if "critical" not in states:
            clear_alert(tool, "critical")
        if "warning" not in states:
            clear_alert(tool, "warning")
