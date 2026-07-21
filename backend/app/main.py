import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.browser_agent import run_test
from app.config import (
    DATA_DIR,
    PROVIDER_PRESETS,
    create_provider,
    delete_provider,
    get_providers,
    get_smtp_settings,
    is_configured,
    is_smtp_configured,
    patch_provider,
    reorder_providers,
    save_smtp_settings,
)
from app.models import RunStatus, TestRequest, TestRun
from app.reports.emailer import EmailNotConfiguredError, InvalidRecipientsError, send_report_email
from app.storage import store

app = FastAPI(title="QA Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")

store.load_from_disk()

_running_tasks: dict[str, asyncio.Task] = {}


@app.get("/api/health")
async def health():
    return {"ok": True, "configured": is_configured()}


def _public_provider(p: dict) -> dict:
    key = p.get("api_key", "")
    masked = (key[:4] + "…" + key[-4:]) if len(key) > 8 else ("••••" if key else "")
    out = {**p}
    out["api_key"] = masked
    out["has_api_key"] = bool(key)
    return out


class ProviderCreatePayload(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    vision_model: str
    text_model: str
    enabled: bool = True


class ProviderPatchPayload(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    vision_model: str | None = None
    text_model: str | None = None
    enabled: bool | None = None


class ReorderPayload(BaseModel):
    order: list[str]


@app.get("/api/providers")
async def list_providers():
    return [_public_provider(p) for p in get_providers()]


@app.get("/api/providers/presets")
async def list_presets():
    return PROVIDER_PRESETS


@app.post("/api/providers")
async def add_provider(payload: ProviderCreatePayload):
    providers = create_provider(payload.model_dump())
    return [_public_provider(p) for p in providers]


@app.patch("/api/providers/{provider_id}")
async def edit_provider(provider_id: str, payload: ProviderPatchPayload):
    providers = patch_provider(provider_id, payload.model_dump(exclude_unset=True))
    return [_public_provider(p) for p in providers]


@app.delete("/api/providers/{provider_id}")
async def remove_provider(provider_id: str):
    providers = delete_provider(provider_id)
    return [_public_provider(p) for p in providers]


@app.post("/api/providers/reorder")
async def reorder(payload: ReorderPayload):
    providers = reorder_providers(payload.order)
    return [_public_provider(p) for p in providers]


@app.post("/api/tests")
async def start_test(payload: TestRequest):
    run = TestRun(
        url=payload.url,
        goal=payload.goal,
        max_steps=payload.max_steps,
        headless=payload.headless,
        status=RunStatus.QUEUED,
    )
    store.create(run)
    task = asyncio.create_task(run_test(run, payload.username, payload.password))
    _running_tasks[run.id] = task
    task.add_done_callback(lambda _t, run_id=run.id: _running_tasks.pop(run_id, None))
    return {"run_id": run.id}


@app.get("/api/tests")
async def list_tests():
    return [
        {
            "id": r.id,
            "url": r.url,
            "goal": r.goal,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "issue_count": len(r.issues),
            "score": r.summary.score,
        }
        for r in store.list()
    ]


@app.get("/api/tests/{run_id}")
async def get_test(run_id: str):
    run = store.get(run_id)
    if not run:
        return {"error": "not_found"}
    return run.model_dump()


@app.post("/api/tests/{run_id}/cancel")
async def cancel_test(run_id: str):
    run = store.get(run_id)
    if not run:
        return {"ok": False, "error": "Teste não encontrado."}
    task = _running_tasks.get(run_id)
    if not task or task.done():
        return {"ok": False, "error": "Este teste não está em execução."}
    task.cancel()
    return {"ok": True}


class SmtpPatchPayload(BaseModel):
    host: str | None = None
    port: int | None = None
    encryption: str | None = None
    username: str | None = None
    password: str | None = None
    from_email: str | None = None
    from_name: str | None = None


def _public_smtp(smtp: dict) -> dict:
    password = smtp.get("password", "")
    masked = (password[:2] + "…") if password else ""
    out = {**smtp}
    out["password"] = masked
    out["has_password"] = bool(password)
    return out


@app.get("/api/smtp")
async def get_smtp():
    return {**_public_smtp(get_smtp_settings()), "configured": is_smtp_configured()}


@app.patch("/api/smtp")
async def update_smtp(payload: SmtpPatchPayload):
    smtp = save_smtp_settings(payload.model_dump(exclude_unset=True))
    return {**_public_smtp(smtp), "configured": is_smtp_configured()}


class SendEmailPayload(BaseModel):
    recipients: list[str]
    message: str | None = None


@app.post("/api/tests/{run_id}/send-email")
async def send_email(run_id: str, payload: SendEmailPayload):
    run = store.get(run_id)
    if not run:
        return {"ok": False, "error": "Teste não encontrado."}
    try:
        await asyncio.to_thread(send_report_email, run, payload.recipients, payload.message)
        return {"ok": True}
    except (InvalidRecipientsError, EmailNotConfiguredError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Falha ao enviar e-mail: {exc}"}


@app.websocket("/api/tests/{run_id}/stream")
async def stream_test(websocket: WebSocket, run_id: str):
    await websocket.accept()
    queue = store.subscribe(run_id)
    try:
        run = store.get(run_id)
        if run:
            await websocket.send_json({"type": "snapshot", "run": run.model_dump()})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") == "finished":
                break
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(run_id, queue)
