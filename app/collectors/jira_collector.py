"""Collector for Jira issue data (Python 3.6+, sync requests)."""
import logging
from datetime import datetime

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import config, cache

logger = logging.getLogger(__name__)

TOOL_COMPONENT_MAPPING = {
    "Nexus": ["nexus", "docker registry"],
    "Jenkins": ["jenkins", "build", "pipeline", "ci-cd", "ci/cd", "job"],
    "Artifactory": ["artifactory", "jfrog", "artifact", "art-"],
    "Bitbucket": ["bitbucket", "git", "scm", "source control", "bb"],
    "Swarm": ["swarm", "helix swarm", "code review"],
    "Perforce": ["perforce", "helix", "p4", "depot", "changelist"],
    "SonarQube": ["sonar", "sonarqube", "sonar-", "code quality", "code scan"],
    "Fortify": ["fortify", "security scan", "sast"],
}


def _get_auth(session):
    """Configure auth: PAT (Bearer) if no username, else basic auth."""
    token = config.JIRA_API_TOKEN
    username = config.JIRA_USERNAME

    if username and token:
        session.auth = (username, token)
    elif token:
        session.headers["Authorization"] = "Bearer {}".format(token)


def _jira_search(session, jql, fields, max_results=200):
    base = config.JIRA_BASE_URL.rstrip("/")
    url = "{}/rest/api/2/search".format(base)

    all_issues = []
    start_at = 0

    while True:
        params = {
            "jql": jql,
            "fields": fields,
            "maxResults": min(100, max_results - len(all_issues)),
            "startAt": start_at,
        }
        try:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 401:
                logger.error("Jira authentication failed (check JIRA_API_TOKEN / credentials)")
                break
            if resp.status_code == 403:
                logger.error("Jira forbidden - token may lack permissions")
                break
            if resp.status_code != 200:
                logger.warning("Jira search returned %d: %s", resp.status_code, resp.text[:200])
                break
            data = resp.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            if len(all_issues) >= data.get("total", 0) or len(all_issues) >= max_results:
                break
            start_at += len(issues)
        except Exception as e:
            logger.error("Jira search failed: %s", e)
            break

    return all_issues


def _classify_tool(issue):
    fields = issue.get("fields", {})
    text = " ".join([
        (fields.get("summary") or "").lower(),
        " ".join(c.get("name", "").lower() for c in (fields.get("components") or [])),
        " ".join(l.lower() for l in (fields.get("labels") or [])),
    ])

    for tool_name, keywords in TOOL_COMPONENT_MAPPING.items():
        if any(kw in text for kw in keywords):
            return tool_name

    return "Other"


def _extract_month(issue):
    created = issue.get("fields", {}).get("created", "")
    if created:
        return created[:7]
    return "unknown"


def collect_jira_data():
    projects = config.JIRA_PROJECTS

    if not projects or not config.JIRA_API_TOKEN:
        logger.warning("Jira not configured (set JIRA_PROJECTS and JIRA_API_TOKEN in .env)")
        empty = {"trends": [], "by_tool": [], "open_summary": {}, "collected_at": datetime.utcnow().isoformat() + "Z"}
        cache.set("jira:all", empty, ttl=600)
        return empty

    logger.info("Jira projects configured: %s", projects)
    project_jql = " OR ".join('project = "{}"'.format(p) for p in projects)
    full_jql = "({}) AND created >= -365d ORDER BY created DESC".format(project_jql)
    logger.info("Jira JQL: %s", full_jql)

    session = requests.Session()
    session.verify = False
    session.trust_env = False
    _get_auth(session)
    issues = _jira_search(
        session,
        jql=full_jql,
        fields="summary,issuetype,priority,status,assignee,components,labels,created,resolutiondate",
        max_results=2000,
    )

    issue_records = []

    base_url = config.JIRA_BASE_URL.rstrip("/")

    for issue in issues:
        f = issue.get("fields", {})
        issue_type = (f.get("issuetype") or {}).get("name", "Unknown")
        priority = (f.get("priority") or {}).get("name", "None")
        status_name = (f.get("status") or {}).get("name", "Unknown")
        status_cat = (f.get("status") or {}).get("statusCategory", {}).get("name", "To Do")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        tool = _classify_tool(issue)
        created = f.get("created", "")
        key = issue.get("key", "")

        issue_records.append({
            "key": key,
            "url": "{}/browse/{}".format(base_url, key) if key else "",
            "summary": f.get("summary", ""),
            "type": issue_type,
            "priority": priority,
            "status": status_name,
            "status_category": status_cat,
            "assignee": assignee,
            "tool": tool,
            "created": created[:10] if created else "",
            "created_month": created[:7] if created else "unknown",
            "components": ", ".join(c.get("name", "") for c in (f.get("components") or [])),
            "labels": ", ".join(f.get("labels") or []),
        })

    result = {
        "issues": issue_records,
        "collected_at": datetime.utcnow().isoformat() + "Z",
    }

    cache.set("jira:all", result, ttl=600)
    from collections import Counter
    proj_counts = Counter(r["key"].split("-")[0] for r in issue_records if "-" in r.get("key", ""))
    logger.info("Jira collected: %d issues from %d projects — breakdown: %s",
                len(issue_records), len(projects), dict(proj_counts))
    return result
