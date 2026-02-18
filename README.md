# SmartSummary

Telegram userbot for chat monitoring, AI summarization, and Bitrix24 calendar integration. Runs as a personal Telegram account (via Telethon), not a bot.

## Features

### Chat Summarization
- **In-chat trigger**: write "Суммаризация" in any chat to get an AI summary of today's messages
- **Daily report**: automatic summary of all active chats sent to Saved Messages (configurable schedule)
- **REST API**: trigger summarization programmatically via `/api/summarize`

### Auto-Replies
- **"Гринкеев"** trigger: responds with a rare pig fact (GPT-generated, high temperature for creativity)
- **"Ситников"** trigger: responds with a Seneca quote

### Jira Task Creation
Write in any chat (as a reply to the task text):
```
Создай задачу DC
```

The bot will create a Jira issue in the specified project with the reply message as description.

### Free Slot Finder (Bitrix24)
Write in any chat:
```
Найди время @ivan @petrov @sidorov
```

The bot will:
- Look up @nicknames in Bitrix24
- Fetch calendar availability for the next 5 business days (Mon-Fri)
- Find common free slots within working hours (9:00–19:00, Asia/Novosibirsk)
- Handle timezone offsets for users in different timezones
- Filter out slots shorter than 30 minutes
- Reply with a day-by-day breakdown of available time

### Meeting Creation (Bitrix24)
Write in any chat:
```
Сделай встречу 16:00 18.02 @ivan @petrov user@mail.ru
```

Supported formats:
- **Time**: `16:00` or `1600`
- **Date**: `18.02` or `18 февраля`

The bot will:
- Parse time, date, @nicknames, and email addresses from the message
- Look up @nicknames in Bitrix24 by custom user field
- Look up emails among regular users and email guests
- Create a calendar event with all found participants
- Reply with a summary of who was added and who wasn't found

Reply to a message with the command to use its text as the meeting title and description.

### REST API
- `GET /api/me` — account info
- `GET /api/chats` — list dialogs
- `GET /api/monitor` — monitored chats
- `POST /api/monitor/add` — add chat to monitoring
- `POST /api/monitor/remove` — remove chat from monitoring
- `GET /api/monitor/{chat_id}/messages` — buffered messages
- `POST /api/summarize` — AI summary for a chat
- `POST /api/daily-report` — trigger daily report manually

Swagger UI available at `http://localhost:8001/docs`.

## Setup

### Prerequisites
- Python 3.11+
- Telegram API credentials (`API_ID`, `API_HASH` from https://my.telegram.org)
- OpenAI API key
- Bitrix24 OAuth app (for calendar features)
- Jira Server (for task creation)

### Installation

```bash
git clone https://github.com/artemsitnikoff/smartsummary.git
cd smartsummary
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
| Variable | Description |
|---|---|
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `OPENAI_API_KEY` | OpenAI API key |
| `BITRIX_CLIENT_ID` | Bitrix24 OAuth client ID |
| `BITRIX_CLIENT_SECRET` | Bitrix24 OAuth client secret |
| `BITRIX_REFRESH_TOKEN` | Initial Bitrix24 refresh token |
| `JIRA_URL` | Jira Server URL |
| `JIRA_USERNAME` | Jira username |
| `JIRA_PASSWORD` | Jira password |

### Telegram Authorization

Run once to create a session file:

```bash
python auth.py
```

### Running

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Architecture

```
Uvicorn (event loop owner)
  -> FastAPI (REST API via api/routes.py)
  -> Telethon (TelegramService singleton, connected in lifespan)
     -> Trigger router (triggers/__init__.py — matches all messages)
        -> Individual triggers (summarize, auto_reply, jira_task, free_slots, meeting)
  -> APScheduler (daily summary cron job at 23:15)
  -> Services (singleton classes with shared clients):
     -> AIClient         — OpenAI GPT-5.2
     -> BitrixClient     — Bitrix24 REST API (calendar, users, OAuth)
     -> JiraClient       — Jira REST API (issue creation)
     -> TelegramService  — Telethon client wrapper
  -> ChatState (in-memory state: monitored chats, message buffer, daily tracking)
```

## Project Structure

```
app/
  main.py                  # FastAPI app, lifespan, scheduler, daily_summary_job
  config.py                # pydantic-settings from .env
  chat_state.py            # ChatState — monitored chats, message buffer, daily tracking
  utils.py                 # Parsers, constants, helpers
  summarizer.py            # GPT summarization (single chat, daily overview)
  compliments.py           # Wife compliment generator (disabled)
  date_experiment.py       # Autonomous GPT dialog experiment
  services/
    ai_client.py           # AIClient singleton (OpenAI)
    bitrix_client.py       # BitrixClient singleton (Bitrix24 REST API)
    jira_client.py         # JiraClient singleton (Jira REST API)
    telegram_service.py    # TelegramService singleton (Telethon)
  triggers/
    __init__.py            # register_all() — event router
    summarize.py           # "суммаризация" trigger
    auto_reply.py          # "ситников", "гринкеев" triggers
    jira_task.py           # "создай задачу" trigger
    free_slots.py          # "найди время" trigger
    meeting.py             # "сделай/создай встречу" trigger
  api/
    routes.py              # REST API endpoints
auth.py                    # One-time Telegram authorization
```

## Tech Stack

- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto client
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — REST API
- [OpenAI](https://platform.openai.com/) — GPT-5.2 for summarization and generation
- [APScheduler](https://apscheduler.readthedocs.io/) — scheduled tasks
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — configuration
- [httpx](https://www.python-httpx.org/) — async HTTP client for Bitrix24 and Jira APIs
