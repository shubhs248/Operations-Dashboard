"""Cache layer: Redis if available, falls back to in-memory TTL cache."""
import json
import time
import threading
import logging

logger = logging.getLogger(__name__)

_redis = None
_fallback_store = {}
_fallback_lock = threading.Lock()

REDIS_DB = 2


def init_cache(redis_url: str = ""):
    """Try to connect to Redis. Falls back silently to in-memory."""
    global _redis
    if not redis_url:
        logger.info("No REDIS_URL configured, using in-memory cache")
        return

    try:
        import redis as redis_lib
        _redis = redis_lib.Redis.from_url(redis_url, db=REDIS_DB, decode_responses=True, socket_timeout=3)
        _redis.ping()
        logger.info("Connected to Redis (db=%d)", REDIS_DB)
    except Exception as e:
        logger.warning("Redis unavailable (%s), falling back to in-memory cache", e)
        _redis = None


def get(key: str):
    if _redis:
        try:
            raw = _redis.get(f"platformops:{key}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Redis GET failed for %s: %s", key, e)

    with _fallback_lock:
        entry = _fallback_store.get(key)
        if entry and entry[0] > time.time():
            return entry[1]
        _fallback_store.pop(key, None)
    return None


def set(key: str, value, ttl: int = 300):
    stored = False
    if _redis:
        try:
            payload = json.dumps(value, default=str)
            _redis.setex(f"platformops:{key}", ttl, payload)
            stored = True
        except Exception as e:
            logger.warning("Redis SET failed for %s (%s) — using in-memory fallback", key, e)

    if not stored:
        with _fallback_lock:
            _fallback_store[key] = (time.time() + ttl, value)


def delete(key: str):
    if _redis:
        try:
            _redis.delete(f"platformops:{key}")
            return
        except Exception:
            pass

    with _fallback_lock:
        _fallback_store.pop(key, None)


def clear():
    if _redis:
        try:
            for k in _redis.scan_iter("platformops:*"):
                _redis.delete(k)
            return
        except Exception:
            pass

    with _fallback_lock:
        _fallback_store.clear()
