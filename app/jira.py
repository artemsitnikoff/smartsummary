import logging

import httpx

from app.config import settings

logger = logging.getLogger("smartsummary")


async def create_issue(project_key: str, summary: str, description: str = "") -> dict:
    """Create a Jira issue via REST API v2 with Basic auth.

    Returns dict with 'key' (e.g. 'DC-123'), 'id', 'self'.
    """
    url = f"{settings.jira_url.rstrip('/')}/rest/api/2/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Task"},
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            auth=(settings.jira_username, settings.jira_password),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()

    logger.info("Jira issue created: %s", result.get("key"))
    return result
