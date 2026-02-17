from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import monitor, summarizer
from app.date_experiment import experiments, get_or_create
from app.telegram_client import get_client

router = APIRouter()


class ChatIdBody(BaseModel):
    chat_id: int


class SummarizeRequest(BaseModel):
    chat_id: int
    use_buffer: bool = False
    limit: int = 200


class ExperimentStart(BaseModel):
    chat_id: int
    name: str


@router.get("/me")
async def whoami():
    client = get_client()
    me = await client.get_me()
    return {"id": me.id, "name": me.first_name, "username": me.username}


@router.get("/chats")
async def list_dialogs():
    client = get_client()
    dialogs = await client.get_dialogs(limit=50)
    return [
        {"id": d.id, "name": d.name, "unread": d.unread_count}
        for d in dialogs
    ]


@router.get("/monitor")
async def list_monitored():
    return {"monitored": monitor.get_monitored()}


@router.post("/monitor/add")
async def add_monitor(body: ChatIdBody):
    monitor.add_chat(body.chat_id)
    return {"status": "ok", "monitored": monitor.get_monitored()}


@router.post("/monitor/remove")
async def remove_monitor(body: ChatIdBody):
    monitor.remove_chat(body.chat_id)
    return {"status": "ok", "monitored": monitor.get_monitored()}


@router.get("/monitor/{chat_id}/messages")
async def get_buffered_messages(chat_id: int):
    msgs = monitor.get_messages(chat_id)
    return {"chat_id": chat_id, "count": len(msgs), "messages": msgs}


@router.post("/summarize")
async def summarize_chat(body: SummarizeRequest):
    try:
        summary = await summarizer.summarize(
            body.chat_id,
            use_buffer=body.use_buffer,
            limit=body.limit,
        )
        return {"chat_id": body.chat_id, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daily-report")
async def trigger_daily_report():
    """Manually trigger the daily summary report (same as the cron job)."""
    from app.main import daily_summary_job
    try:
        await daily_summary_job()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiment/start")
async def start_experiment(body: ExperimentStart):
    exp = get_or_create(body.chat_id, body.name)
    if exp.active:
        return {"status": "already_running", "chat_id": body.chat_id, "name": body.name}
    client = get_client()
    await exp.start(client)
    return {"status": "started", "chat_id": body.chat_id, "name": body.name}


@router.post("/experiment/stop")
async def stop_experiment(body: ChatIdBody):
    exp = experiments.get(body.chat_id)
    if not exp:
        return {"status": "not_found"}
    exp.stop()
    return {"status": "stopped", "chat_id": body.chat_id, "exchanges": exp._reply_count}


@router.post("/experiment/nudge")
async def nudge_experiment(body: ChatIdBody):
    exp = experiments.get(body.chat_id)
    if not exp or not exp.active:
        return {"status": "not_active"}
    client = get_client()
    msg = await exp.nudge(client)
    return {"status": "sent", "message": msg}


@router.get("/experiment/status")
async def experiment_status():
    result = {}
    for chat_id, exp in experiments.items():
        result[str(chat_id)] = {
            "name": exp.name,
            "active": exp.active,
            "exchanges": exp._reply_count,
            "conversation": exp.conversation,
        }
    return result


