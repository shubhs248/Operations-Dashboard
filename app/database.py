"""PostgreSQL persistent storage with JSON file fallback."""
import os
import json
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

_conn = None
_data_dir = "data"

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS jira_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    issues JSONB NOT NULL,
    total_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date)
);

CREATE TABLE IF NOT EXISTS grafana_user_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    users JSONB NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date)
);

CREATE TABLE IF NOT EXISTS mcp_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    servers JSONB NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date)
);

CREATE TABLE IF NOT EXISTS mcp_usage_daily (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    username TEXT NOT NULL,
    function_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, username, function_name)
);
CREATE INDEX IF NOT EXISTS idx_mud_date ON mcp_usage_daily(date);

CREATE TABLE IF NOT EXISTS ocp_status_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    servers JSONB NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(snapshot_date)
);

CREATE TABLE IF NOT EXISTS chatops_snapshots (
    id SERIAL PRIMARY KEY,
    data_type TEXT NOT NULL,
    env TEXT NOT NULL DEFAULT 'production',
    data JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(data_type, env)
);
"""


def init_db(database_url: str = ""):
    global _conn
    os.makedirs(_data_dir, exist_ok=True)

    if not database_url:
        logger.info("No DATABASE_URL configured, using JSON file storage in %s/", _data_dir)
        return

    try:
        import psycopg2
        _conn = psycopg2.connect(database_url)
        _conn.autocommit = True
        with _conn.cursor() as cur:
            cur.execute(DB_SCHEMA)
        logger.info("PostgreSQL connected and schema ready")
    except Exception as e:
        logger.warning("PostgreSQL unavailable (%s), falling back to JSON files", e)
        _conn = None


def save_snapshot(name: str, data):
    """Save a daily snapshot. Upserts by date."""
    today = date.today().isoformat()

    if _conn:
        try:
            _save_pg(name, today, data)
            return
        except Exception as e:
            logger.error("PG save failed for %s: %s", name, e)

    _save_json(name, data)


def get_latest_snapshot(name: str):
    if _conn:
        try:
            return _get_pg_latest(name)
        except Exception as e:
            logger.error("PG read failed for %s: %s", name, e)

    return _get_json(name)


def get_history(name: str, days: int = 30) -> list:
    """Get historical snapshots for trend comparison."""
    if not _conn:
        return []

    table = _table_for(name)
    if not table:
        return []

    try:
        with _conn.cursor() as cur:
            cur.execute(
                f"SELECT snapshot_date, summary FROM {table} "
                f"WHERE snapshot_date >= CURRENT_DATE - %s "
                f"ORDER BY snapshot_date",
                (days,)
            )
            return [{"date": str(row[0]), "summary": row[1]} for row in cur.fetchall()]
    except Exception as e:
        logger.error("PG history failed: %s", e)
        return []


# ── MCP usage daily persistence ──

def save_mcp_usage(records: list):
    """Persist per-user/function/day call counts.

    Uses UPSERT with GREATEST so counts never decrease even if pod logs
    are lost after a restart.  Each record is a dict with keys:
    date, username, function_name, tool_name, call_count.
    """
    if not records:
        return

    if _conn:
        try:
            _save_mcp_usage_pg(records)
            return
        except Exception as e:
            logger.error("PG save_mcp_usage failed: %s", e)

    _save_mcp_usage_json(records)


def get_mcp_usage(days: int = 3) -> list:
    """Load historical usage records for the last *days* days."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    if _conn:
        try:
            return _get_mcp_usage_pg(cutoff)
        except Exception as e:
            logger.error("PG get_mcp_usage failed: %s", e)

    return _get_mcp_usage_json(cutoff)


def cleanup_mcp_usage(keep_days: int = 7):
    """Delete usage records older than *keep_days*."""
    cutoff = (datetime.utcnow() - timedelta(days=keep_days)).strftime("%Y-%m-%d")

    if _conn:
        try:
            with _conn.cursor() as cur:
                cur.execute("DELETE FROM mcp_usage_daily WHERE date < %s", (cutoff,))
                deleted = cur.rowcount
            if deleted:
                logger.info("Cleaned up %d old mcp_usage_daily rows (before %s)", deleted, cutoff)
            return
        except Exception as e:
            logger.error("PG cleanup_mcp_usage failed: %s", e)

    _cleanup_mcp_usage_json(cutoff)


def _save_mcp_usage_pg(records: list):
    from psycopg2.extras import execute_values
    sql = (
        "INSERT INTO mcp_usage_daily (date, username, function_name, tool_name, call_count, updated_at) "
        "VALUES %s "
        "ON CONFLICT (date, username, function_name) DO UPDATE SET "
        "call_count = GREATEST(mcp_usage_daily.call_count, EXCLUDED.call_count), "
        "tool_name = EXCLUDED.tool_name, "
        "updated_at = NOW()"
    )
    rows = [
        (r["date"], r["username"], r["function_name"], r["tool_name"], r["call_count"])
        for r in records
    ]
    with _conn.cursor() as cur:
        execute_values(cur, sql, rows, template="(%s, %s, %s, %s, %s, NOW())")
    logger.info("Persisted %d mcp_usage_daily records to PostgreSQL", len(rows))


def _get_mcp_usage_pg(cutoff: str) -> list:
    with _conn.cursor() as cur:
        cur.execute(
            "SELECT date, username, function_name, tool_name, call_count "
            "FROM mcp_usage_daily WHERE date >= %s",
            (cutoff,),
        )
        return [
            {"date": r[0], "username": r[1], "function_name": r[2],
             "tool_name": r[3], "call_count": r[4]}
            for r in cur.fetchall()
        ]


def _save_mcp_usage_json(records: list):
    """JSON file fallback: merge into existing file using GREATEST semantics."""
    path = os.path.join(_data_dir, "mcp_usage_daily.json")
    existing = {}
    try:
        with open(path, "r") as f:
            for item in json.load(f):
                key = (item["date"], item["username"], item["function_name"])
                existing[key] = item
    except (IOError, ValueError, KeyError):
        pass

    for r in records:
        key = (r["date"], r["username"], r["function_name"])
        prev = existing.get(key)
        if prev and prev.get("call_count", 0) >= r["call_count"]:
            continue
        existing[key] = r

    try:
        with open(path, "w") as f:
            json.dump(list(existing.values()), f, default=str)
        logger.info("Persisted %d mcp_usage_daily records to JSON", len(existing))
    except Exception as e:
        logger.error("Failed to save mcp_usage_daily JSON: %s", e)


def _get_mcp_usage_json(cutoff: str) -> list:
    path = os.path.join(_data_dir, "mcp_usage_daily.json")
    try:
        with open(path, "r") as f:
            return [r for r in json.load(f) if r.get("date", "") >= cutoff]
    except (IOError, ValueError):
        return []


def _cleanup_mcp_usage_json(cutoff: str):
    path = os.path.join(_data_dir, "mcp_usage_daily.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
        kept = [r for r in data if r.get("date", "") >= cutoff]
        removed = len(data) - len(kept)
        if removed:
            with open(path, "w") as f:
                json.dump(kept, f, default=str)
            logger.info("Cleaned up %d old mcp_usage_daily JSON entries (before %s)", removed, cutoff)
    except (IOError, ValueError):
        pass


# ── ChatOps snapshot persistence ──

def save_chatops_snapshot(data_type: str, env: str, data):
    """Upsert a ChatOps snapshot (summary, activity, channels, or mcp)."""
    if _conn:
        try:
            with _conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chatops_snapshots (data_type, env, data, updated_at) "
                    "VALUES (%s, %s, %s, NOW()) "
                    "ON CONFLICT (data_type, env) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()",
                    (data_type, env, json.dumps(data, default=str)),
                )
            return
        except Exception as e:
            logger.error("PG save_chatops_snapshot failed (%s/%s): %s", data_type, env, e)

    path = os.path.join(_data_dir, f"chatops_{data_type}_{env}.json")
    try:
        with open(path, "w") as f:
            json.dump({"data": data, "updated_at": datetime.utcnow().isoformat() + "Z"}, f, default=str)
    except Exception as e:
        logger.error("Failed to save ChatOps JSON (%s/%s): %s", data_type, env, e)


def get_chatops_snapshot(data_type: str, env: str = "production"):
    """Load the latest ChatOps snapshot for a given type and env."""
    if _conn:
        try:
            with _conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM chatops_snapshots WHERE data_type = %s AND env = %s",
                    (data_type, env),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logger.error("PG get_chatops_snapshot failed (%s/%s): %s", data_type, env, e)

    path = os.path.join(_data_dir, f"chatops_{data_type}_{env}.json")
    try:
        with open(path, "r") as f:
            return json.load(f).get("data")
    except (IOError, ValueError):
        return None


# ── PostgreSQL helpers ──

def _table_for(name: str) -> str:
    mapping = {
        "jira": "jira_snapshots",
        "grafana_users": "grafana_user_snapshots",
        "mcp": "mcp_snapshots",
        "ocp_status": "ocp_status_snapshots",
    }
    return mapping.get(name, "")


def _save_pg(name: str, today: str, data):
    table = _table_for(name)
    if not table:
        return

    import psycopg2.extras
    with _conn.cursor() as cur:
        if name == "jira":
            issues = data.get("issues", [])
            cur.execute(
                f"INSERT INTO {table} (snapshot_date, issues, total_count) "
                f"VALUES (%s, %s, %s) "
                f"ON CONFLICT (snapshot_date) DO UPDATE SET issues = EXCLUDED.issues, total_count = EXCLUDED.total_count",
                (today, json.dumps(issues, default=str), len(issues))
            )
        else:
            users_or_servers = data.get("users", data.get("servers", []))
            summary = data.get("summary", {})
            col = "users" if "users" in data else "servers"
            cur.execute(
                f"INSERT INTO {table} (snapshot_date, {col}, summary) "
                f"VALUES (%s, %s, %s) "
                f"ON CONFLICT (snapshot_date) DO UPDATE SET {col} = EXCLUDED.{col}, summary = EXCLUDED.summary",
                (today, json.dumps(users_or_servers, default=str), json.dumps(summary, default=str))
            )


def _get_pg_latest(name: str):
    table = _table_for(name)
    if not table:
        return None

    with _conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} ORDER BY snapshot_date DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        return {"data": row, "collected_at": str(row[-1])}


# ── JSON file fallback ──

def _save_json(name: str, data):
    path = os.path.join(_data_dir, f"{name}.json")
    payload = {"data": data, "collected_at": datetime.utcnow().isoformat() + "Z"}
    try:
        with open(path, "w") as f:
            json.dump(payload, f, default=str)
    except Exception as e:
        logger.error("Failed to save JSON %s: %s", name, e)


def _get_json(name: str):
    path = os.path.join(_data_dir, f"{name}.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (IOError, ValueError):
        return None
