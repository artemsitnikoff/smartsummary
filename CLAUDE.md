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
  main.py                  # FastAPI app, lifespan, APScheduler, daily_summary_job
  config.py                # pydantic-settings (Settings class, reads .env)
  chat_state.py            # ChatState class — monitored chats, message buffer, daily tracking
  utils.py                 # Parsers (time, attendees, Bitrix datetime), constants, helpers
  summarizer.py            # GPT summarization (single chat, daily overview)
  compliments.py           # Wife compliment generator (disabled)
  date_experiment.py       # Autonomous GPT dialog experiment (with consent)
  services/
    ai_client.py           # AIClient singleton — single OpenAI client for the whole app
    bitrix_client.py       # BitrixClient singleton — OAuth, user search, calendar, email guest cache
    jira_client.py         # JiraClient singleton — Jira issue creation
    telegram_service.py    # TelegramService singleton — Telethon client, clean_html, send_long_message
  triggers/
    __init__.py            # register_all() — event router, sequential trigger matching
    summarize.py           # "суммаризация" trigger
    auto_reply.py          # "ситников" (Seneca quote), "гринкеев" (pig fact) triggers
    jira_task.py           # "создай задачу" trigger
    free_slots.py          # "найди время" trigger
    meeting.py             # "сделай/создай встречу" trigger
  api/
    routes.py              # REST API endpoints
auth.py                    # One-time Telegram authorization script
```

## Key Patterns

### Architecture
- Each external service is a singleton class with a shared httpx/OpenAI client
- Services are accessed via `ServiceClass.get()` (e.g. `AIClient.get()`, `BitrixClient.get()`)
- Global state (monitored chats, message buffer, daily tracking) is encapsulated in `ChatState` (`app/chat_state.py`)
- Lifespan in `main.py` initializes and closes all services

### Telegram Event Handling
- Single handler in `triggers/__init__.py` catches ALL messages (`incoming=True, outgoing=True`)
- Triggers are checked sequentially: "суммаризация" → "ситников" → "гринкеев" → "создай задачу" → "найди время" → "сделай/создай встречу"
- Each trigger is a separate module in `app/triggers/`
- `return` after trigger prevents double-processing

### Bitrix24 Integration
- `BitrixClient` manages OAuth tokens (`bitrix_tokens.json`), auto-refreshes on expiry
- `_request()` is the single entry point for all Bitrix API calls (shared httpx client)
- **Important**: `user.get` excludes email-type guests by design. Email guests are found via `im.user.list.get` cache (loaded once on first email lookup, stored in `BitrixClient` instance)
- `find_user_by_nickname()` searches custom field `UF_USR_1678964886664` (with and without @)
- `resolve_email_user()` chains: regular user search → email guest cache lookup

### Free Slot Finder
- Trigger: `найди\s+время` (e.g. "Найди время @nick1 @nick2") — handler in `triggers/free_slots.py`
- Resolves @nicknames via `BitrixClient.find_user_by_nickname()` → Bitrix user IDs
- Calls `BitrixClient.get_users_accessibility()` → `calendar.accessibility.get` API
- Computes 5 business days forward (skips Sat/Sun)
- For each day: collects busy intervals, converts to Novosibirsk time using `~USER_OFFSET_FROM`, merges overlapping intervals, finds gaps in 9:00–19:00 window
- Filters slots < 30 min
- Helper functions in `utils.py`: `parse_bitrix_dt()`, `merge_intervals()`

### Meeting Creation Flow
1. Parse time/date from text (`utils.parse_meeting_time`) — supports `HH:MM` / `HHMM` time and `DD.MM` / `DD месяц` date formats
2. Parse @nicknames and emails (`utils.parse_attendees`) — emails removed from text before @nick extraction to avoid domain-as-nick false positives
3. Resolve nicknames via `BitrixClient.find_user_by_nickname()` by custom field
4. Resolve emails: first `find_user_by_email()`, then email guest cache via `im.user.list.get`
5. Unfound emails go into event description as "Пригласить по email: ..."
6. `BitrixClient.create_meeting()` with `attendee_ids` → `is_meeting: Y`, `attendees`, `host`, `meeting.notify`

### OpenAI
- Single `AIClient` singleton wraps `AsyncOpenAI` — methods `complete()` and `chat()`
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
- `ChatState` (monitored chats, message buffer, daily tracking) and email guest cache are in-memory (reset on restart)
- Email guests cannot be created via REST API (only UI); unfound emails go to event description
