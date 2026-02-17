# SmartSummary

Telegram userbot (personal account, NOT BotFather) for chat monitoring, AI summarization, auto-replies, and Bitrix24 calendar integration.

## Tech Stack

- **Python 3.11+**, Telethon (Telegram MTProto), FastAPI + Uvicorn, OpenAI GPT-5.2, Bitrix24 REST API
- Uvicorn owns the event loop; Telethon connects in FastAPI lifespan
- APScheduler for cron jobs (daily summary)
- pydantic-settings for config from `.env`

## Project Structure

```
app/
  main.py               # FastAPI app, lifespan, APScheduler, daily_summary_job
  config.py             # pydantic-settings (Settings class, reads .env)
  telegram_client.py    # Singleton Telethon client
  monitor.py            # Event handlers, triggers, message buffer, parse_attendees
  summarizer.py         # GPT summarization (single chat, daily overview)
  bitrix.py             # Bitrix24 OAuth, user search, calendar event creation
  compliments.py        # Wife compliment generator (disabled)
  date_experiment.py    # Autonomous GPT dialog experiment (with consent)
  api/
    routes.py           # REST API endpoints
auth.py                 # One-time Telegram authorization script
```

## Key Patterns

### Telegram Event Handling
- Single handler `on_new_message` in `monitor.py` catches ALL messages (`incoming=True, outgoing=True`)
- Triggers are checked sequentially: "суммаризация" → "ситников" → "гринкеев" → "сделай/создай встречу"
- `return` after trigger prevents double-processing

### Bitrix24 Integration
- OAuth tokens stored in `bitrix_tokens.json`, auto-refreshed on expiry
- `_bitrix_request()` is the single entry point for all Bitrix API calls
- **Important**: `user.get` excludes email-type guests by design. Email guests are found via `im.user.list.get` cache (loaded once on first email lookup)
- `find_user_by_nickname()` searches custom field `UF_USR_1678964886664` (with and without @)
- `resolve_email_user()` chains: regular user search → email guest cache lookup

### Meeting Creation Flow
1. Parse time/date from text (`parse_meeting_time`)
2. Parse @nicknames and emails (`parse_attendees`) — emails removed from text before @nick extraction to avoid domain-as-nick false positives
3. Resolve nicknames via Bitrix `user.get` by custom field
4. Resolve emails: first `user.get` by EMAIL, then email guest cache via `im.user.list.get`
5. Unfound emails go into event description as "Пригласить по email: ..."
6. `create_meeting()` with `attendee_ids` → `is_meeting: Y`, `attendees`, `host`, `meeting.notify`

### OpenAI
- Model: `gpt-5.2` — uses `max_completion_tokens` (NOT `max_tokens`)
- VPN required (403 without it due to region restrictions)

## Running

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Port 8001 (8000 is taken). Swagger UI: http://localhost:8001/docs

## Config (.env)

Required: `API_ID`, `API_HASH`, `OPENAI_API_KEY`, `BITRIX_CLIENT_ID`, `BITRIX_CLIENT_SECRET`, `BITRIX_REFRESH_TOKEN`

Key settings in `config.py`: `my_user_id = 33570147`, `timezone = "Asia/Novosibirsk"`, daily report at 23:15.

## Known Issues

- OpenAI API returns 403 without VPN (unsupported region)
- Telethon loses connection on unstable VPN — needs restart
- `today_active_chats`, `monitored_chats`, email guest cache are in-memory (reset on restart)
- Email guests cannot be created via REST API (only UI); unfound emails go to event description
