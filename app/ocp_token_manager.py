"""OCP bearer-token lifecycle manager.

Handles automatic token acquisition and refresh for a service account
(e.g. ``svc-monitoring``) so the dashboard never goes stale because of an
expired token.

Token flow:
  1. On startup, if OCP_SA_USER/OCP_SA_PASSWORD are set, obtain a fresh
     token via the OCP OAuth challenge endpoint.
  2. A scheduler job calls ``refresh_if_needed()`` periodically.
  3. Collectors call ``get_token()`` which returns the current valid token.
  4. On a 401/403 from the K8s API, call ``force_refresh()`` to get a new
     token immediately.
"""
import logging
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, urlencode

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

_lock = threading.Lock()
_current_token: str = ""
_token_acquired_at: float = 0.0
_token_ttl_seconds: int = 43200

_chatops_lock = threading.Lock()
_chatops_token: str = ""
_chatops_acquired_at: float = 0.0
_chatops_ttl_seconds: int = 43200


def _derive_oauth_url(api_url: str) -> str:
    """Derive the OCP OAuth server URL from the console/API URL.

    Handles both URL conventions:
      api.ocp-cluster.example.com:6443
        → oauth-openshift.apps.ocp-cluster.example.com
      console-openshift-console.apps.ocp-cluster.example.com
        → oauth-openshift.apps.ocp-cluster.example.com
    """
    parsed = urlparse(api_url)
    host = parsed.hostname or ""

    apps_idx = host.find(".apps.")
    if apps_idx >= 0:
        cluster_domain = host[apps_idx + 1:]
        return f"https://oauth-openshift.{cluster_domain}"

    if host.startswith("api."):
        cluster_domain = host[4:]
        return f"https://oauth-openshift.apps.{cluster_domain}"

    dot = host.find(".")
    if dot > 0:
        domain = host[dot + 1:]
        return f"https://oauth-openshift.{domain}"

    return f"https://oauth-openshift.{host}"


def _request_token(oauth_url: str, username: str, password: str) -> tuple[str, int]:
    """Authenticate via the OCP OAuth challenge and return (token, expires_in).

    OCP flow: GET /oauth/authorize with Basic-Auth and ``response_type=token``
    returns a 302 redirect whose Location fragment contains the access_token.
    """
    authorize_url = f"{oauth_url}/oauth/authorize"
    params = {
        "response_type": "token",
        "client_id": "openshift-challenging-client",
    }

    try:
        resp = requests.get(
            authorize_url,
            params=params,
            auth=(username, password),
            headers={"X-CSRF-Token": "1"},
            verify=False,
            allow_redirects=False,
            timeout=30,
        )

        if resp.status_code in (302, 301):
            location = resp.headers.get("Location", "")
            fragment = location.split("#", 1)[1] if "#" in location else ""
            token_match = re.search(r"access_token=([^&]+)", fragment)
            expires_match = re.search(r"expires_in=(\d+)", fragment)
            if token_match:
                token = token_match.group(1)
                expires_in = int(expires_match.group(1)) if expires_match else 86400
                return token, expires_in

            logger.error("OAuth redirect missing access_token. Location: %s", location[:200])
            return "", 0

        if resp.status_code == 401:
            logger.error("OAuth authentication failed for user '%s' — check password", username)
            return "", 0

        logger.error("Unexpected OAuth response: HTTP %d", resp.status_code)
        return "", 0

    except Exception as e:
        logger.error("OAuth token request failed: %s", e)
        return "", 0


def init(api_url: str, static_token: str, sa_user: str, sa_password: str,
         refresh_hours: int = 12):
    """Initialize the token manager.

    If service-account credentials are provided, immediately fetch a fresh
    token.  Otherwise fall back to the static ``OCP_TOKEN`` from .env.
    """
    global _current_token, _token_acquired_at, _token_ttl_seconds

    _token_ttl_seconds = refresh_hours * 3600

    if sa_user and sa_password:
        logger.info("OCP token manager: using service-account '%s' with auto-refresh every %dh", sa_user, refresh_hours)
        oauth_url = _derive_oauth_url(api_url)
        logger.info("OCP OAuth endpoint: %s", oauth_url)
        token, expires_in = _request_token(oauth_url, sa_user, sa_password)
        if token:
            with _lock:
                _current_token = token
                _token_acquired_at = time.time()
                _token_ttl_seconds = min(expires_in - 300, refresh_hours * 3600)
            logger.info(
                "OCP token acquired for '%s' (expires in %ds, will refresh in %ds)",
                sa_user, expires_in, _token_ttl_seconds,
            )
        else:
            logger.warning("Failed to acquire initial OCP token — falling back to static OCP_TOKEN")
            with _lock:
                _current_token = static_token
    else:
        logger.info("OCP token manager: no SA credentials, using static OCP_TOKEN")
        with _lock:
            _current_token = static_token


def get_token() -> str:
    """Return the current valid bearer token."""
    with _lock:
        return _current_token


def force_refresh() -> str:
    """Force an immediate token refresh (e.g. after receiving a 401)."""
    global _current_token, _token_acquired_at, _token_ttl_seconds

    from app.config import get_settings
    settings = get_settings()

    if not (settings.ocp_sa_user and settings.ocp_sa_password):
        logger.warning("Cannot refresh token — no SA credentials configured")
        return _current_token

    oauth_url = _derive_oauth_url(settings.ocp_api_url)
    token, expires_in = _request_token(oauth_url, settings.ocp_sa_user, settings.ocp_sa_password)

    if token:
        with _lock:
            _current_token = token
            _token_acquired_at = time.time()
            _token_ttl_seconds = min(expires_in - 300, settings.ocp_token_refresh_hours * 3600)
        logger.info("OCP token force-refreshed (expires in %ds)", expires_in)
        return token
    else:
        logger.error("OCP token force-refresh FAILED — collections will use stale token")
        return _current_token


def refresh_if_needed() -> bool:
    """Check token age and refresh if it's past the TTL. Returns True if refreshed."""
    age = time.time() - _token_acquired_at
    if age < _token_ttl_seconds:
        return False

    logger.info("OCP token age %ds exceeds TTL %ds — refreshing", int(age), _token_ttl_seconds)
    force_refresh()
    return True


# ── ChatOps cluster token management ──────────────────────────────

def init_chatops(api_url: str, static_token: str, sa_user: str, sa_password: str,
               refresh_hours: int = 12):
    """Initialize the ChatOps cluster token (separate OCP cluster)."""
    global _chatops_token, _chatops_acquired_at, _chatops_ttl_seconds

    _chatops_ttl_seconds = refresh_hours * 3600

    if sa_user and sa_password:
        logger.info("ChatOps token manager: using SA '%s' on %s", sa_user, api_url)
        oauth_url = _derive_oauth_url(api_url)
        logger.info("ChatOps OAuth endpoint: %s", oauth_url)
        token, expires_in = _request_token(oauth_url, sa_user, sa_password)
        if token:
            with _chatops_lock:
                _chatops_token = token
                _chatops_acquired_at = time.time()
                _chatops_ttl_seconds = min(expires_in - 300, refresh_hours * 3600)
            logger.info("ChatOps token acquired (expires in %ds)", expires_in)
        else:
            logger.warning("ChatOps SA auth failed — falling back to static OCP_ChatOps_TOKEN")
            with _chatops_lock:
                _chatops_token = static_token
    elif static_token:
        logger.info("ChatOps token manager: using static OCP_ChatOps_TOKEN")
        with _chatops_lock:
            _chatops_token = static_token
    else:
        logger.info("ChatOps token manager: no token or SA configured — ChatOps panel disabled")


def get_chatops_token() -> str:
    with _chatops_lock:
        return _chatops_token


def refresh_chatops_if_needed() -> bool:
    global _chatops_token, _chatops_acquired_at, _chatops_ttl_seconds

    age = time.time() - _chatops_acquired_at
    if age < _chatops_ttl_seconds:
        return False

    from app.config import get_settings
    settings = get_settings()
    sa_user = settings.ocp_chatops_sa_user or settings.ocp_sa_user
    sa_password = settings.ocp_chatops_sa_password or settings.ocp_sa_password

    if not (sa_user and sa_password):
        return False

    logger.info("ChatOps token age %ds exceeds TTL — refreshing", int(age))
    oauth_url = _derive_oauth_url(settings.ocp_chatops_api_url)
    token, expires_in = _request_token(oauth_url, sa_user, sa_password)
    if token:
        with _chatops_lock:
            _chatops_token = token
            _chatops_acquired_at = time.time()
            _chatops_ttl_seconds = min(expires_in - 300, settings.ocp_token_refresh_hours * 3600)
        logger.info("ChatOps token refreshed (expires in %ds)", expires_in)
        return True
    return False
