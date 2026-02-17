import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger("smartsummary")

TOKENS_FILE = Path(__file__).resolve().parent.parent / "bitrix_tokens.json"
OAUTH_URL = "https://oauth.bitrix24.tech/oauth/token"


def _load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    try:
        return json.loads(TOKENS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load Bitrix tokens: %s", e)
        return None


def _save_tokens(data: dict):
    """Save tokens + client_endpoint from Bitrix OAuth response."""
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "client_endpoint": data["client_endpoint"],
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
    }
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    logger.info("Bitrix tokens saved (endpoint: %s)", tokens["client_endpoint"])


async def _refresh_access_token(refresh_token: str) -> dict:
    """Refresh expired access_token. Returns updated tokens dict."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            OAUTH_URL,
            params={
                "grant_type": "refresh_token",
                "client_id": settings.bitrix_client_id,
                "client_secret": settings.bitrix_client_secret,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Bitrix refresh error: {data['error']} — {data.get('error_description', '')}")

    _save_tokens(data)
    return _load_tokens()


async def _get_tokens() -> dict:
    """Return valid tokens, refreshing if expired. First run uses refresh_token from .env."""
    tokens = _load_tokens()

    if tokens is None:
        # первый запуск — берём refresh_token из .env
        if not settings.bitrix_refresh_token:
            raise RuntimeError("BITRIX_REFRESH_TOKEN не задан в .env")
        logger.info("Bitrix: first run, refreshing from .env token...")
        return await _refresh_access_token(settings.bitrix_refresh_token)

    if time.time() < tokens["expires_at"] - 60:
        return tokens

    logger.info("Bitrix access_token expired, refreshing...")
    return await _refresh_access_token(tokens["refresh_token"])


async def _bitrix_request(method: str, params: dict | None = None) -> dict:
    """Call Bitrix24 REST API. Auth passed in JSON body per Bitrix convention."""
    tokens = await _get_tokens()
    url = f"{tokens['client_endpoint']}{method}"

    body = dict(params or {})
    body["auth"] = tokens["access_token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body)
        data = resp.json()

    if not resp.is_success or "error" in data:
        error = data.get("error", resp.status_code)
        desc = data.get("error_description", resp.reason_phrase)
        raise RuntimeError(f"Bitrix API error ({method}): {error} — {desc}")

    return data


async def find_user_by_nickname(nickname: str) -> tuple[int | None, str | None]:
    """Find Bitrix user by nickname in custom field UF_USR_1678964886664.

    Tries without @ first, then with @. Returns (user_id, full_name) or (None, None).
    """
    clean = nickname.lstrip("@")
    for variant in [clean, f"@{clean}"]:
        result = await _bitrix_request("user.get", {
            "filter": {"UF_USR_1678964886664": variant},
        })
        users = result.get("result", [])
        if users:
            user = users[0]
            full_name = f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip()
            return int(user["ID"]), full_name
    return None, None


async def find_user_by_email(email: str) -> tuple[int | None, str | None]:
    """Find Bitrix user by primary EMAIL. Returns (user_id, full_name) or (None, None)."""
    result = await _bitrix_request("user.get", {
        "filter": {"EMAIL": email},
    })
    users = result.get("result", [])
    if users:
        user = users[0]
        full_name = f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip()
        logger.info("User found by EMAIL=%s: id=%s name=%s", email, user["ID"], full_name)
        return int(user["ID"]), full_name
    return None, None


# Cache for email guests (invisible to user.get, found via im.user.list.get)
_email_guests_cache: dict[str, tuple[int, str]] = {}  # email -> (id, name)
_email_guests_loaded = False


async def _load_email_guests():
    """Load all email-type guest users via im.user.list.get into cache."""
    global _email_guests_loaded
    if _email_guests_loaded:
        return

    # Get max user ID from user.get total
    result = await _bitrix_request("user.get", {"start": 0})
    total_regular = result.get("total", 0)
    # Email guests have IDs beyond regular users, scan up to total*3 to be safe
    max_id = max(total_regular * 3, 2000)

    batch_size = 100
    for start in range(1, max_id + 1, batch_size):
        ids = list(range(start, min(start + batch_size, max_id + 1)))
        try:
            result = await _bitrix_request("im.user.list.get", {"ID": ids})
        except Exception:
            continue
        for uid_str, u in result.get("result", {}).items():
            if u and u.get("external_auth_id") == "email" and u.get("email"):
                email = u["email"].lower()
                _email_guests_cache[email] = (u["id"], u.get("name", ""))

    _email_guests_loaded = True
    logger.info("Loaded %d email guests from Bitrix", len(_email_guests_cache))


async def resolve_email_user(email: str) -> tuple[int | None, str | None]:
    """Find Bitrix user by email: first regular users, then email guests."""
    # 1. Regular user
    uid, name = await find_user_by_email(email)
    if uid:
        return uid, name

    # 2. Email guest (loaded via im API)
    await _load_email_guests()
    cached = _email_guests_cache.get(email.lower())
    if cached:
        uid, name = cached
        logger.info("Email guest found: id=%s email=%s name=%s", uid, email, name)
        return uid, name

    return None, None


async def create_meeting(
    title: str,
    date: datetime,
    description: str = "",
    duration_minutes: int = 60,
    attendee_ids: list[int] | None = None,
) -> dict:
    """Create a calendar event in Bitrix24."""
    date_from = date.strftime("%d.%m.%Y %H:%M:%S")
    date_to = (date + timedelta(minutes=duration_minutes)).strftime("%d.%m.%Y %H:%M:%S")

    # resolve current user ID
    profile = await _bitrix_request("profile")
    user_id = profile["result"]["ID"]

    event_params = {
        "type": "user",
        "ownerId": user_id,
        "name": title,
        "description": description,
        "from": date_from,
        "to": date_to,
        "timezone_from": settings.timezone,
        "timezone_to": settings.timezone,
    }

    if attendee_ids:
        all_ids = [int(user_id)] + [aid for aid in attendee_ids if aid != int(user_id)]
        event_params.update({
            "is_meeting": "Y",
            "host": user_id,
            "attendees": all_ids,
            "meeting": {
                "notify": True,
                "open": False,
                "reinvite": False,
            },
        })

    result = await _bitrix_request("calendar.event.add", event_params)
    event_id = result.get("result")
    logger.info("Bitrix calendar event created: id=%s title=%s date=%s attendees=%s",
                event_id, title, date_from, attendee_ids)
    return {"status": "ok", "id": event_id}
