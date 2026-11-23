"""媒合星球整合（ai-eva EPIC #176 / #203）：比照法規工作區（#195/#197）的對話任務。

- 只對指定租戶開（MATCH_TASK_PROJECTS，預設 sechome）；其他租戶（如雲林）維持原本的聊天流程。
- 任務以「伺服器端驗證過的身分 + thread」為範圍存成 JSON：同一對話再進入接回原任務、**不重跑**；
  只有面板上的「開始新媒合」（action=new）才建新任務、換 task_id。
- 選 A 與 2–4 個指定對象 → 背景執行一次 B1–B8 判斷與關係／狀態（handler.judge_all + handler.analyze），
  結果整理成星圖可直接吃的格式（projects[].match[Bk].{role,evidence}、pairs[] 狀態與三種關係）。
- 點星圖衛星／一對 → action=explain：只用本次已存的結果由 Eva 在對話說明，不重判。

推送走既有 overlay 的 CopilotFunction("tangle_workspace")：mode=match、v=live-match、matchTask=快照。
視窗訊息 {tangle:{kind:"match_task",...}} 由 install_window_router() 掛在 Chainlit 既有的
on_window_message 前面攔截，其他訊息原封不動交給原本的處理（app/main.py 不改）。
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import chainlit as cl

from app.matching import pair
from app.settings import ROOT

from . import handler

logger = logging.getLogger(__name__)

TASK_DIR = ROOT / "data" / "matching" / "tasks"
KIND = "match_task"
ACTIONS = ("get", "select", "new", "explain")
LIVE_VERSION = "live-match"
DEFAULT_PROJECTS = "sechome"
ACTIVE_STATES = {"loading", "running"}
ROLE = {pair.NEED: "need", pair.OFFER: "offer", pair.BOTH: "both", pair.NONE: "none"}

_ACTIVE: dict[Path, asyncio.Task] = {}


# ── 租戶開關 ──────────────────────────────────────────────────────────

def enabled_projects() -> set[str]:
    raw = os.getenv("MATCH_TASK_PROJECTS", DEFAULT_PROJECTS)
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def enabled_for(project: str | None) -> bool:
    """只有列在 MATCH_TASK_PROJECTS 的租戶開星球；沒有 project（非 SSO）一律不開。"""
    return bool(project) and str(project).strip().lower() in enabled_projects()


def overlay_live() -> bool:
    """星球面板靠 tangle overlay（custom_js）顯示；沒載入 overlay 的部署不能切過去，否則使用者看不到東西。"""
    return os.getenv("TANGLE_LAW_TASK") == "1" or os.getenv("TANGLE_LAB") == "1"


# ── 範圍與存檔 ────────────────────────────────────────────────────────

def scope_path(identity: Mapping, thread_id: str) -> Path:
    # 只用伺服器端的 session 資料；不接受前端傳來的 task/thread ID。
    scope = [identity.get(key) for key in ("issuer", "project", "tenant_id", "user_id", "email")]
    digest = hashlib.sha256(json.dumps([scope, thread_id]).encode()).hexdigest()
    return TASK_DIR / f"{digest}.json"


def _save(path: Path, task: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as f:
        json.dump(task, f, ensure_ascii=False)
    Path(f.name).replace(path)


def _load(path: Path) -> dict | None:
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.exception("match task: 讀取失敗 %s", path)
        return None
    if task.get("status") in ACTIVE_STATES and path not in _ACTIVE:
        # 服務重啟時中斷的任務不自動重跑。
        task.update(status="error", error="媒合已中斷，請按「開始新媒合」。")
        _save(path, task)
    return task


def snapshot(task: dict) -> dict:
    return copy.deepcopy(task)


async def _publish(task: dict, *, opening: bool = False) -> None:
    args = {"mode": "match", "v": LIVE_VERSION, "matchTask": snapshot(task)}
    if not opening:
        args["update"] = True
    try:
        # 面板關了／瀏覽器斷線不能卡住背景判斷。
        await asyncio.wait_for(cl.CopilotFunction(name="tangle_workspace", args=args).acall(), 2)
    except (TimeoutError, asyncio.TimeoutError):
        pass
    except Exception:  # noqa: BLE001
        logger.debug("match task: publish failed", exc_info=True)


def _spawn(path: Path, coro) -> None:
    worker = asyncio.create_task(coro)
    _ACTIVE[path] = worker

    def finished(done):
        if _ACTIVE.get(path) is done:
            _ACTIVE.pop(path, None)
        if not done.cancelled() and (exc := done.exception()):
            logger.error("match task worker failed", exc_info=exc)

    worker.add_done_callback(finished)


def _new_task() -> dict:
    return {"task_id": uuid4().hex, "status": "loading", "projects": [], "a": None, "targets": [],
            "min_targets": handler.MIN_TARGETS, "max_targets": handler.MAX_TARGETS,
            "progress": [], "result": None, "error": None}


def _create(path: Path, runtime) -> dict:
    task = _new_task()
    _save(path, task)
    _spawn(path, _list(path, task, runtime))
    return task


async def _list(path: Path, task: dict, runtime) -> None:
    try:
        projects = await handler.load_projects(runtime)
        task["projects"] = [{"uuid": u, "name": p["name"]} for u, p in projects.items()]
        if len(projects) >= 1 + handler.MIN_TARGETS:
            task["status"] = "select"
        else:
            task.update(status="error",
                        error=f"媒合需要 A 加上至少 {handler.MIN_TARGETS} 個對象，目前可用的專案只有 {len(projects)} 個。")
    except Exception as exc:  # noqa: BLE001 —— 不可誤報成專案不足
        logger.exception("match task: 讀取專案清單失敗")
        task.update(status="error", error=f"讀取專案清單失敗（{exc}），請按「開始新媒合」再試。")
    _save(path, task)
    _ACTIVE.pop(path, None)   # 先釋放再推送，讓「開始新媒合」可以立刻接手
    await _publish(task)


# ── 對外：開啟與事件 ──────────────────────────────────────────────────

async def open_task(path: Path, runtime) -> dict:
    """點工具區按鈕：有任務就接回（不重跑），沒有才建新的。"""
    task = _load(path)
    if task is None:
        task = _create(path, runtime)
    await _publish(task, opening=True)
    return task


async def handle_event(path: Path, runtime, data: Mapping, llm: Any = None) -> None:
    action, task_id = data.get("action"), data.get("task_id")
    if action not in ACTIONS:
        return
    task = _load(path)
    if not task:
        return
    if action == "get":
        await _publish(task)
        return
    if task["task_id"] != task_id:
        # 舊分頁：送回目前的任務讓它跟上，不動作。
        await _publish(task)
        return
    if action == "explain":
        if task["status"] == "done":
            await explain(task, data)
        return
    if action == "new" and task["status"] not in ACTIVE_STATES:
        task = _create(path, runtime)
    elif action == "select" and task["status"] == "select":
        err = _validate(task, data.get("a"), data.get("targets"))
        if err:
            task["error"] = err
            _save(path, task)
        else:
            task.update(status="running", a=data["a"], targets=list(data["targets"]), error=None)
            _save(path, task)   # 先同步佔住，兩個分頁連點也只跑一次
            _spawn(path, _run(path, task, runtime, llm))
    await _publish(task)


def _validate(task: dict, a, targets) -> str | None:
    ids = {p["uuid"] for p in task["projects"]}
    if not isinstance(a, str) or a not in ids:
        return "請先選擇你的專案 A。"
    if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
        return "請勾選媒合對象。"
    if len(set(targets)) != len(targets) or a in targets or not set(targets) <= ids:
        return "媒合對象不正確，請重新勾選。"
    if not (handler.MIN_TARGETS <= len(targets) <= handler.MAX_TARGETS):
        return f"請指定 {handler.MIN_TARGETS}–{handler.MAX_TARGETS} 個媒合對象（目前 {len(targets)} 個）。"
    return None


# ── 背景判斷 ──────────────────────────────────────────────────────────

def galaxy(a: dict, targets: list[dict], judged: Mapping[str, dict], results: list[dict]) -> dict:
    """判斷結果 → 星圖資料（與 kv-match-mock.js 的 KV_MATCH 同形，另附每一對的狀態與關係）。"""
    def side(p: dict) -> dict:
        caps = (judged.get(p["uuid"]) or {}).get("capabilities") or {}
        match = {}
        for k in pair.B_KEYS:
            c = caps.get(k) or {}
            role = ROLE.get(pair.directions({"capabilities": {k: c}})[k], "none")
            ev = [e["quote"] for e in c.get("evidence") or [] if e.get("quote")] if role != "none" else []
            match[k] = {"role": role, "evidence": ev}
        return {"pid": p["uuid"], "name": p["name"], "match": match}

    pairs = []
    for r in results:
        rel = r["relations"]
        pairs.append({
            "pa": a["uuid"], "pb": r["target"]["uuid"],
            "pair": "|".join(sorted([a["uuid"], r["target"]["uuid"]])),
            "status": r["status"], "status_text": r["status_text"],
            "relations": {name: rel.get(name) or [] for name in handler.RELATIONS},
            "counts": {"complement": len(rel.get(pair.REL_COMPLEMENT) or []),
                       "third": len(rel.get(pair.REL_THIRD_PARTY) or []),
                       "peer": len(rel.get(pair.REL_PEER) or [])},
            "next_question": (r.get("next_question") or {}).get("text"),
        })
    std = pair.load_standard()
    keys = {k: ((std.get("capability_registry") or {}).get(k) or {}).get("名稱", k) for k in pair.B_KEYS}
    return {
        "demo": False,
        "note": "B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。",
        "keys": keys,
        "a": a["uuid"],
        "projects": [side(p) for p in [a, *targets]],
        "pairs": pairs,
        "not_evaluated": handler.not_evaluated(),
    }


async def _run(path: Path, task: dict, runtime, llm: Any) -> None:
    try:
        visible = set(await handler.list_uuids(runtime))   # 選定時再確認一次 CMS 權限
        wanted = [task["a"], *task["targets"]]
        if not set(wanted) <= visible:
            task.update(status="error", error="你目前無法讀取其中一個專案，請按「開始新媒合」。")
            return
        infos = {}
        for uuid in wanted:
            info = await handler.fetch_info(runtime, uuid)
            if info is None:
                task.update(status="error", error="無法讀取其中一個專案，請按「開始新媒合」。")
                return
            infos[uuid] = info
            task["progress"].append({"uuid": uuid, "name": info["name"], "step": "fetch"})
        a, targets = infos[task["a"]], [infos[u] for u in task["targets"]]
        judged = await handler.judge_all([a, *targets], llm)
        task["progress"].append({"step": "judged", "count": len(judged)})
        results = handler.analyze(a, targets, judged)
        task.update(status="done", result=galaxy(a, targets, judged, results))
        try:
            await cl.Message(content=summary(task)).send()
        except Exception:  # noqa: BLE001
            logger.exception("match task: 摘要送出失敗")
    except Exception:  # noqa: BLE001
        logger.exception("match task failed")
        task.update(status="error", error="媒合失敗，請稍後按「開始新媒合」。")
    finally:
        _save(path, task)
        _ACTIVE.pop(path, None)
        await _publish(task)


# ── Eva 說明（只用已存結果，不重判） ──────────────────────────────────

def _names(task: dict) -> dict[str, str]:
    return {p["pid"]: p["name"] for p in (task.get("result") or {}).get("projects") or []}


def summary(task: dict) -> str:
    res = task["result"]
    names = _names(task)
    lines = [f"## 🧭 媒合星球：{names.get(res['a'], '')} × {len(res['pairs'])} 個指定對象", ""]
    for p in res["pairs"]:
        c = p["counts"]
        lines.append(f"- **{names.get(p['pb'], p['pb'])}**：{p['status_text']}"
                     f"（互補候選 {c['complement']}・共同尋找第三方 {c['third']}・可聯合或交流 {c['peer']}）")
    lines += ["", "點星球上的衛星或一對，Eva 會用這次的結果說明（不重新判斷）。",
              "第一期不推薦、不自動聯絡；B1–B8 與方向是 AI 推論（未經 Owner 確認）。"]
    return "\n".join(lines)


def explain_text(task: dict, data: Mapping) -> str | None:
    res = task.get("result") or {}
    projects = {p["pid"]: p for p in res.get("projects") or []}
    keys = res.get("keys") or {}
    code = data.get("code")
    pa, pb = data.get("pa"), data.get("pb")
    who = data.get("who") or data.get("subject")
    if isinstance(code, str) and code in keys:
        key = code
        if pa in projects and pb in projects:
            sides = [projects[pa], projects[pb]]
        elif who in projects:
            sides = [projects[who]]
        else:
            sides = list(projects.values())
        head = f"**{key} {keys[key]}**（本次媒合結果）"
        lines = [head, ""]
        label = {"need": "需要（月牙）", "offer": "能提供", "both": "需要也能提供", "none": "沒有依據"}
        for p in sides:
            m = p["match"].get(key) or {}
            lines.append(f"- {handler.INFER}{p['name']}：{label.get(m.get('role'), '沒有依據')}")
            for q in m.get("evidence") or []:
                lines.append(f"  - {handler.FACT}「{q}」")
        if len(sides) == 2:
            pr = _pair(res, sides[0]["pid"], sides[1]["pid"])
            if pr:
                rel = pr["relations"]
                if any(c["key"] == key for c in rel.get(pair.REL_COMPLEMENT) or []):
                    lines.append(f"- 這一類是兩案的**互補候選**（光流：能提供 → 需要）。")
                elif key in (rel.get(pair.REL_THIRD_PARTY) or []):
                    lines.append("- 兩案在這一類都只需要：**共同尋找第三方**，不算互補。")
                elif key in (rel.get(pair.REL_PEER) or []):
                    lines.append("- 兩案在這一類都能提供：**可聯合或交流**。")
                lines.append(f"- 這一對的狀態：{pr['status_text']}（依媒合標準規則算出）")
        lines += ["", "以上只說明這次已完成的判斷，沒有重新判斷；是否聯繫由人決定。"]
        return "\n".join(lines)
    if pa in projects and pb in projects:
        pr = _pair(res, pa, pb)
        if not pr:
            return None
        c = pr["counts"]
        lines = [f"**{projects[pa]['name']} × {projects[pb]['name']}**（本次媒合結果）", "",
                 f"- 狀態：{pr['status_text']}",
                 f"- 互補候選 {c['complement']}・共同尋找第三方 {c['third']}・可聯合或交流 {c['peer']}"]
        for it in pr["relations"].get(pair.REL_COMPLEMENT) or []:
            lines.append(f"  - {it['key']} {keys.get(it['key'], '')}："
                         f"{projects[it['need']]['name']} 需要 ← {projects[it['offer']]['name']} 可提供")
        if pr.get("next_question"):
            lines.append(f"- 下一步可先確認：{pr['next_question']}")
        lines += ["", "以上只說明這次已完成的判斷，沒有重新判斷。"]
        return "\n".join(lines)
    if who in projects:
        p = projects[who]
        need = [k for k, m in p["match"].items() if m["role"] in ("need", "both")]
        offer = [k for k, m in p["match"].items() if m["role"] in ("offer", "both")]
        fmt = lambda ks: "、".join(f"{k} {keys.get(k, '')}" for k in ks) or "（無）"
        return "\n".join([f"**{p['name']}**（本次媒合結果）", "",
                          f"- {handler.INFER}需要：{fmt(need)}", f"- {handler.INFER}能提供：{fmt(offer)}",
                          "", "以上只說明這次已完成的判斷，沒有重新判斷。"])
    return None


def _pair(res: Mapping, x: str, y: str) -> dict | None:
    k = "|".join(sorted([x, y]))
    return next((p for p in res.get("pairs") or [] if p["pair"] == k), None)


async def explain(task: dict, data: Mapping) -> None:
    text = explain_text(task, data)
    if not text:
        return
    try:
        await cl.Message(content=text).send()
    except Exception:  # noqa: BLE001
        logger.exception("match task: 說明送出失敗")


# ── Chainlit 接線（app/main.py 不改） ─────────────────────────────────

def current_user():
    try:
        return cl.user_session.get("user")
    except Exception:  # noqa: BLE001
        return None


def current_project() -> str | None:
    user = current_user()
    md = getattr(user, "metadata", None) or {}
    project = md.get("project")
    if not project:
        idn = _session_get("law_task_identity") or {}
        project = idn.get("project")
    return project


def _session_get(key: str):
    try:
        return cl.user_session.get(key)
    except Exception:  # noqa: BLE001
        return None


def context() -> tuple[Path, Any] | None:
    """(任務路徑, CMS runtime)；身分只取伺服器端 session，缺任何一個就回 None。"""
    runtime = _session_get("cms_runtime")
    identity = _session_get("law_task_identity")
    if not identity:
        user = current_user()
        md = getattr(user, "metadata", None) or {}
        uid = getattr(user, "identifier", None)
        if uid:
            identity = {"project": md.get("project"), "user_id": uid, "issuer": "chainlit-user"}
    try:
        thread_id = cl.context.session.thread_id
    except Exception:  # noqa: BLE001
        thread_id = None
    if runtime and identity and thread_id:
        return scope_path(identity, thread_id), runtime
    return None


def wants_task() -> bool:
    """這次點按鈕要不要走星球：租戶有開、overlay 有載。"""
    return overlay_live() and enabled_for(current_project())


async def on_window_message(data) -> bool:
    """處理 {tangle:{kind:"match_task"}}；回 True 表示已處理（不是就交還原本的處理）。"""
    meta = data.get("tangle") if isinstance(data, dict) else None
    if not (isinstance(meta, dict) and meta.get("kind") == KIND):
        return False
    if meta.get("action") not in ACTIONS or not enabled_for(current_project()):
        return True
    ctx = context()
    if ctx:
        await handle_event(*ctx, meta)
    return True


def install_window_router(code_config=None) -> None:
    """在 Chainlit 目前的 on_window_message 前面掛一層：match_task 自己處理，其餘照舊交給原本的。"""
    if code_config is None:
        from chainlit.config import config as chainlit_config
        code_config = chainlit_config.code
    current = getattr(code_config, "on_window_message", None)
    if getattr(current, "_match_task_router", False):
        return

    async def router(data):
        if await on_window_message(data):
            return
        if current is not None:
            await current(data)

    router._match_task_router = True
    router._match_task_inner = current
    code_config.on_window_message = router


async def open_from_tool() -> bool:
    """工具區按鈕進來：租戶有開就打開／接回星球任務並回 True；否則回 False 讓原流程繼續。"""
    if not wants_task():
        return False
    ctx = context()
    if ctx is None:
        return False
    install_window_router()
    from . import embed_route
    embed_route.install()
    await open_task(*ctx)
    return True
