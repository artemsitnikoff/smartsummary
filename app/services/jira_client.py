import logging

import httpx

from app.config import settings

logger = logging.getLogger("smartsummary")


class JiraClient:
    _instance: "JiraClient | None" = None

    def __init__(self):
        self._http = httpx.AsyncClient()

    @classmethod
    def get(cls) -> "JiraClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def close(self):
        await self._http.aclose()

    async def create_issue(
        self, project_key: str, summary: str, description: str = ""
    ) -> dict:
        url = f"{settings.jira_url.rstrip('/')}/rest/api/2/issue"
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Task"},
            }
        }

        resp = await self._http.post(
            url,
            json=payload,
            auth=(settings.jira_username, settings.jira_password),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()

        logger.info("Jira issue created: %s", result.get("key"))
        return result
