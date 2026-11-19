"""Opt-in, thread-scoped lifecycle for the real CMS regulation check.

Active workers assume the current single-process deployment. Snapshots survive
restart on the mounted data volume; interrupted jobs never rerun automatically.
"""

import asyncio
import copy
import hashlib
import json
import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import chainlit as cl
from chainlit.context import context_var, local_steps

from app.settings import ROOT
from . import handler

logger = logging.getLogger(__name__)
TASK_DIR = ROOT / "data" / "regulations" / "tasks"
_ACTIVE: dict[Path, asyncio.Task] = {}
_LIVE_CONTEXTS: dict[Path, object] = {}


@contextmanager
def _live_context(path: Path):
    # A resumed tab polling the same task should receive the attachment live.
    current = _LIVE_CONTEXTS.get(path)
    token = context_var.set(current) if current is not None else None
    steps = local_steps.set(None)  # Results are top-level messages, not collapsed steps.
    try:
        yield
    finally:
        local_steps.reset(steps)
        if token is not None:
            context_var.reset(token)


def _remember_context(path: Path) -> None:
    if path in _ACTIVE and (current := context_var.get(None)) is not None:
        _LIVE_CONTEXTS[path] = current


def scope_path(identity: dict, thread_id: str) -> Path:
    # Only server-authenticated session data; never a client-supplied task or thread ID.
    scope = [identity.get(key) for key in ("issuer", "project", "tenant_id", "user_id", "email")]
    digest = hashlib.sha256(json.dumps([scope, thread_id]).encode()).hexdigest()
    return TASK_DIR / f"{digest}.json"


def _save(path: Path, task: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Readers see either the old or new snapshot, never partially written JSON.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as f:
        json.dump(task, f, ensure_ascii=False)
    Path(f.name).replace(path)


def _load(path: Path) -> dict | None:
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if task["status"] in {"loading", "running"} and path not in _ACTIVE:
        task.update(status="error", error="檢核已中斷，請選擇新增檢核。")
        _save(path, task)
    return task


async def _publish(task: dict, *, opening: bool = False) -> None:
    args = {"mode": "law", "lawTask": copy.deepcopy(task)}
    if not opening:
        args["update"] = True
    try:
        # A closed panel or disconnected browser must not stall the CMS/judge pipeline.
        await asyncio.wait_for(cl.CopilotFunction(name="tangle_workspace", args=args).acall(), 2)
    except TimeoutError:
        pass
    except Exception:
        logger.debug("Could not publish regulation task", exc_info=True)


def _spawn(path: Path, coro) -> None:
    worker = asyncio.create_task(coro)
    _ACTIVE[path] = worker
    _remember_context(path)

    def finished(done):
        if _ACTIVE.get(path) is done:
            _ACTIVE.pop(path)
            _LIVE_CONTEXTS.pop(path, None)
        if not done.cancelled() and (exc := done.exception()):
            logger.error("Regulation task worker failed", exc_info=exc)

    worker.add_done_callback(finished)


def _create(path: Path, runtime) -> dict:
    task = {"task_id": uuid4().hex, "status": "loading", "projects": [], "project": None,
            "progress": [], "result": None, "error": None}
    _save(path, task)
    _spawn(path, _list(path, task, runtime))
    return task


async def _list(path: Path, task: dict, runtime) -> None:
    try:
        projects = await handler._my_projects(runtime, refresh=True)
        task["projects"] = [{"uuid": p["uuid"], "name": p["name"]} for p in projects]
        if projects:
            task["status"] = "select"
        else:
            task.update(status="error", error="沒有找到你可管理的計畫書。")
    except Exception:
        logger.exception("Could not list CMS plans for regulation check")
        task.update(status="error", error="讀取計畫書失敗，請新增檢核再試。")
    # Only loading/running are active. Release before publish so 'new' can run immediately.
    _save(path, task)
    with _live_context(path):
        _ACTIVE.pop(path, None)
        _LIVE_CONTEXTS.pop(path, None)
        await _publish(task)


async def open_task(path: Path, runtime) -> None:
    task = _load(path)
    if task is None:
        task = _create(path, runtime)
    _remember_context(path)
    await _publish(task, opening=True)


async def handle_event(path: Path, runtime, data: dict, judge_model: str | None) -> None:
    action, task_id = data.get("action"), data.get("task_id")
    if action not in ("get", "select", "new"):
        return
    task = _load(path)
    if not task:
        return
    _remember_context(path)
    if action == "get":
        # Always return this chat's current task so older tabs recover after an explicit new.
        await _publish(task)
        return
    if task["task_id"] != task_id:
        await _publish(task)
        return
    if action == "new" and task["status"] not in {"loading", "running"}:
        task = _create(path, runtime)
    elif action == "select" and task["status"] == "select":
        picked = next((p for p in task["projects"] if p["uuid"] == data.get("uuid")), None)
        if picked:
            task.update(status="running", project=picked)
            # Claim synchronously before awaiting to avoid duplicate scans from two tabs/clicks.
            _save(path, task)
            _spawn(path, _run(path, task, runtime, judge_model))
    await _publish(task)


async def _run(path: Path, task: dict, runtime, judge_model: str | None) -> None:
    picked = task["project"]

    async def progress(event: dict):
        task["progress"].append({key: event[key] for key in ("domain", "total", "hit", "elapsed")})
        _save(path, task)
        with _live_context(path):
            await _publish(task)

    try:
        # Re-check CMS visibility at selection time (the persisted picker can be stale).
        listing = await runtime.execute("list_my_projects", {})
        if (listing.get("status") != "ok"
                or picked["uuid"] not in (handler._unwrap(listing).get("projects") or [])):
            task.update(status="error", error="你目前無法管理這份計畫書，請新增檢核。")
            return
        detail = await runtime.execute("get_project_info", {"uuid": picked["uuid"]})
        if detail.get("status") != "ok":
            task.update(status="error", error="無法讀取這份計畫書，請新增檢核。")
            return
        plan = handler._plan_text(handler._unwrap(detail))
        if len(plan) < 100:
            task.update(status="error", error=f"計畫理念欄位太短（{len(plan)} 字），請先在 CMS 補上內容。")
            return
        result = await handler.judge.run_check(plan, handler.DEFAULT_CATEGORY,
                                               model=judge_model, on_progress=progress)
        stats = handler.result_stats(result, picked, judge_model)
        md = handler.report.build(result, plan_name=picked["name"], plan_uuid=picked["uuid"])
        stats["attachment"] = None
        try:
            with _live_context(path):
                await cl.Message(content=stats["summary"]).send()
        except Exception:
            logger.exception("Could not send regulation summary to chat")
        try:
            name = f"法規檢核報告_{task['task_id']}.md"
            with _live_context(path):
                file = cl.File(name=name, content=md.encode("utf-8"), display="inline", mime="text/markdown")
                message = await cl.Message(content=f"📄 {name}", elements=[file]).send()
            stats["attachment"] = {"message_id": message.id, "name": name}
        except Exception:
            logger.exception("Could not send regulation report attachment")
        task.update(status="done", result=stats)
    except Exception:
        logger.exception("Regulation task failed")
        task.update(status="error", error="檢核失敗，請稍後新增檢核。")
    finally:
        _save(path, task)
        with _live_context(path):
            _ACTIVE.pop(path, None)
            _LIVE_CONTEXTS.pop(path, None)
            await _publish(task)
    if task["status"] == "done":
        try:
            await handler.notify_result(picked, task["result"])
        except Exception:
            logger.exception("Could not notify regulation task completion")
