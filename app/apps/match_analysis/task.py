"""媒合星球整合（ai-eva EPIC #176 / #203）：比照法規工作區（#195/#197）的對話任務。

- 只對指定租戶開（MATCH_TASK_PROJECTS，預設 sechome）；其他租戶（如雲林）維持原本的聊天流程。
- 任務以「伺服器端驗證過的身分 + thread」為範圍存成 JSON：同一對話再進入接回原任務、**不重跑**；
  只有面板上的「開始新媒合」（action=new）才建新任務、換 task_id。
- 選 A 與 2–4 個指定對象 → 背景執行一次 B1–B8 判斷與關係／狀態（handler.judge_all + handler.analyze），
  結果整理成星圖可直接吃的格式（projects[].match[Bk].{role,evidence}、pairs[] 狀態與三種關係）。
- 點星圖衛星／一對 → action=explain：只用本次已存的結果由 Eva 在對話說明，不重判。
- #215 判斷完成後：先切段（#199）→ engine.match（#200）→ cards.build_cards（#202）出建議卡，
  放在快照的 cards[]，由 public/tangle/match-cards.js 顯示在工作區。
  卡片動作 action=card_action（op=favorite/skip/supplement）→ CMS /matching/card_action；
  action=invite 只有面板確認框按「確定」後（confirmed=true）才呼叫 CMS /matching/invite，AI 不自動寄。
  補資料 → Eva 在對話補問，回答後依 #201 問要不要寫回自己的計畫理念。全程寫進 #198 媒合紀錄。

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

from app.matching import cards, engine, flow, pair
from app.matching import readiness as ready
from app.settings import ROOT

from . import handler

logger = logging.getLogger(__name__)

TASK_DIR = ROOT / "data" / "matching" / "tasks"
KIND = "match_task"
ACTIONS = ("get", "select", "new", "explain", "card_action", "invite", "readiness", "ready_answer")
CARD_TOP_N = 3
LIVE_VERSION = "live-match"
DEFAULT_PROJECTS = "sechome"
ACTIVE_STATES = {"loading", "running"}
LIST_CONCURRENCY = 4      # #232 清單背景補齊名稱時同時讀幾案
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


def _lang() -> str:
    """面板介面語言（#226）：session 語言（zh／en／ja／ko）；取不到一律 zh。"""
    try:
        from app.i18n import current_lang

        return current_lang()
    except Exception:  # noqa: BLE001
        return "zh"


async def _publish(task: dict, *, opening: bool = False) -> None:
    state = snapshot(task)
    # #226：任務狀態帶使用者語言，面板依它顯示介面文字（cookie eva_lang 只是備用）。
    state["lang"] = _lang()
    args = {"mode": "match", "v": LIVE_VERSION, "matchTask": state}
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
    return {"task_id": uuid4().hex, "status": "loading", "projects": [], "initiable": [], "a": None, "targets": [],
            "min_targets": handler.MIN_TARGETS, "max_targets": handler.MAX_TARGETS,
            "progress": [], "result": None, "error": None,
            "cards": [], "card_state": {}, "run_id": None, "clarify": None}


def _create(path: Path, runtime, preselect_a: str | None = None) -> dict:
    task = _new_task()
    _save(path, task)
    _spawn(path, _list(path, task, runtime, preselect_a))
    return task


def _preselect(task: dict, a: str | None) -> bool:
    """#237：從 CMS 帶 a=<uuid> 開啟 → 預選 A；只在該案在「可發起清單」裡才選（否則忽略）。"""
    if isinstance(a, str) and a and a in (task.get("initiable") or ()):
        task["a"] = a
        return True
    return False


NO_INITIABLE = "你在這個站還沒有可以發起媒合的專案（只有本站可管理的專案能寄出媒合邀請）。"


def _release(path: Path) -> None:
    """worker 結束：只釋放自己（「開始新媒合」／選定後可能已換成別的 worker）。"""
    me = asyncio.current_task()
    if _ACTIVE.get(path) is me or me is None:
        _ACTIVE.pop(path, None)


def _current(path: Path, task: dict) -> dict | None:
    """背景補齊時重讀存檔：任務已換（新媒合）或已離開選案（開始判斷）就回 None，不覆蓋。"""
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if cur.get("task_id") != task["task_id"] or cur.get("status") not in ("loading", "select"):
        return None
    return cur


def _list_status(task: dict, final: bool) -> None:
    n = len(task["projects"])
    if n >= 1 + handler.MIN_TARGETS:
        task.update(status="select", error=None)
    elif final:
        task.update(status="error",
                    error=f"媒合需要 A 加上至少 {handler.MIN_TARGETS} 個對象，目前可用的專案只有 {n} 個。")


async def _list(path: Path, task: dict, runtime, preselect_a: str | None = None) -> None:
    """#217：A 只列本站可發起媒合的案（list_match_initiable_projects）；對象清單仍用 list_my_projects，
    但本站的案排最前面、不受 LIST_LIMIT 截斷。initiable 工具不存在或 0 案 → 錯誤，不退回 list_my_projects。

    #232：清單先用兩個清單工具回來的名稱立即推送（可選），沒有名稱的案才在背景逐案用 get_project_info 補齊，
    每補到一案推送一次；不再等每案都讀完才可選。"""
    stale = bg = False   # stale：任務已被換掉／已開始判斷，不再寫入這份；bg：已進入背景補齊
    try:
        if handler.has_manifest(runtime):
            initiable = await handler.list_initiable(runtime)
            if not initiable:
                task.update(status="error", error=NO_INITIABLE, initiable=[])
                return
        else:
            # 沒有 manifest 的 runtime（離線測試替身，非 CMS 連線）沒有站別可言：清單全部可當 A。
            initiable = None
        first = [p["uuid"] for p in initiable or ()]
        names = {p["uuid"]: p["name"] for p in initiable or () if p.get("name")}
        items = await handler.list_items(runtime)
        for p in items:
            if p["name"]:
                names.setdefault(p["uuid"], p["name"])
        rest = [p["uuid"] for p in items if p["uuid"] not in set(first)]
        wanted = first + rest[:max(0, handler.LIST_LIMIT - len(first))]
        order = {u: i for i, u in enumerate(wanted)}
        task["projects"] = [{"uuid": u, "name": names[u]} for u in wanted if u in names]
        task["initiable"] = first if initiable is not None else list(wanted)
        _preselect(task, preselect_a)
        missing = [u for u in wanted if u not in names]
        task["listing"] = bool(missing)
        _list_status(task, final=not missing)
        if not missing:
            return
        _save(path, task)
        await _publish(task)
        bg = True

        gate = asyncio.Semaphore(LIST_CONCURRENCY)

        async def one(uuid):
            try:
                async with gate:
                    return uuid, await handler.fetch_info(runtime, uuid)
            except Exception:  # noqa: BLE001
                logger.exception("match task: get_project_info %s raised", uuid)
                return uuid, None

        for job in asyncio.as_completed([one(u) for u in missing]):
            uuid, info = await job
            if info is None and uuid not in set(first):
                continue   # 讀不到的對象不列（與原本相同）；本站的案用 CMS 名稱或代稱，仍可當 A
            cur = _current(path, task)
            if cur is None:
                stale = True
                return
            name = info["name"] if info else f"（未命名專案 {uuid}）"
            listed = [p for p in cur["projects"] if p["uuid"] != uuid] + [{"uuid": uuid, "name": name}]
            cur["projects"] = sorted(listed, key=lambda p: order.get(p["uuid"], len(order)))
            _list_status(cur, final=False)
            task.clear()
            task.update(cur)
            _save(path, task)
            await _publish(task)
        cur = _current(path, task)
        if cur is None:
            stale = True
            return
        task.clear()
        task.update(cur, listing=False)
        _list_status(task, final=True)
    except Exception as exc:  # noqa: BLE001 —— 不可誤報成專案不足
        logger.exception("match task: 讀取專案清單失敗")
        if bg and _current(path, task) is None:
            stale = True
            return
        task.update(status="error", error=f"讀取專案清單失敗（{exc}），請按「開始新媒合」再試。", listing=False)
    finally:
        if stale:
            _release(path)
        else:
            _save(path, task)
            _release(path)   # 先釋放再推送，讓「開始新媒合」可以立刻接手
            await _publish(task)


# ── 對外：開啟與事件 ──────────────────────────────────────────────────

async def open_task(path: Path, runtime, preselect_a: str | None = None) -> dict:
    """點工具區按鈕：有任務就接回（不重跑），沒有才建新的。

    preselect_a（#237，從 CMS 帶 a=）：新任務在清單回來後預選；接回的任務還在選案時也套用。"""
    task = _load(path)
    if task is None:
        task = _create(path, runtime, preselect_a)
    elif preselect_a and task.get("status") == "select" and _preselect(task, preselect_a):
        _save(path, task)
    await _publish(task, opening=True)
    return task


async def handle_event(path: Path, runtime, data: Mapping, llm: Any = None,
                       identity: Mapping | None = None) -> None:
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
    if action in ("card_action", "invite"):
        if task["status"] == "done":
            await on_card(path, task, runtime, data)
        return
    if action == "readiness":
        # #238：選好 A 的當下先看資料夠不夠（只在選案時；不影響之後的 select）
        if task["status"] == "select":
            await check_readiness(path, task, runtime, data.get("a"), llm)
        return
    if action == "ready_answer":
        _keep(asyncio.create_task(_ready_answer_and_report(path, task, runtime, data)))
        return
    if action == "new" and task["status"] not in ACTIVE_STATES:
        task = _create(path, runtime)
    elif action == "select" and task["status"] == "select":
        err = _validate(task, data.get("a"), data.get("targets"))
        if err:
            task["error"] = err
            _save(path, task)
        else:
            task.pop("preview", None)
            task.update(status="running", a=data["a"], targets=list(data["targets"]), error=None,
                        scope=_scope(identity))
            _save(path, task)   # 先同步佔住，兩個分頁連點也只跑一次
            _spawn(path, _run(path, task, runtime, llm))
    await _publish(task)


# ── #238 媒合準備度 ───────────────────────────────────────────────────

_READY_CACHE: dict[tuple[str, str], dict] = {}   # (task_id, A) → 準備度（同一任務換回同一個 A 不重判）
_BACKGROUND: set[asyncio.Task] = set()


def _keep(job: asyncio.Task) -> None:
    _BACKGROUND.add(job)
    job.add_done_callback(_BACKGROUND.discard)


def _can_be_a(task: dict, a) -> bool:
    if not isinstance(a, str) or a not in {p["uuid"] for p in task.get("projects") or ()}:
        return False
    initiable = task.get("initiable")
    return not initiable or a in initiable


async def check_readiness(path: Path, task: dict, runtime, a, llm: Any = None) -> None:
    """選好 A → 先回「檢查中」，背景用既有能力判斷（handler.judge_project）算四項準備度後推送。"""
    if not _can_be_a(task, a):
        return
    cached = _READY_CACHE.get((task["task_id"], a))
    if cached is not None:
        task["readiness"] = copy.deepcopy(cached)
        _save(path, task)
        await _publish(task)
        return
    if (task.get("readiness") or {}).get("a") == a:
        await _publish(task)   # 已在檢查／已有結果
        return
    task["readiness"] = {"a": a, "state": "checking"}
    _save(path, task)
    await _publish(task)
    _keep(asyncio.create_task(_readiness_worker(path, task["task_id"], runtime, a, llm, _lang())))


async def _readiness_worker(path: Path, task_id: str, runtime, a: str, llm: Any, lang: str) -> None:
    try:
        info = await handler.fetch_info(runtime, a)
        if info is None:
            result = {"a": a, "state": "error"}
        else:
            judged = await asyncio.to_thread(handler.judge_project, info,
                                             llm if llm is not None else handler._default_llm())
            result = ready.build(judged, info.get("philosophy_text") or "", a=a, lang=lang)
            _READY_CACHE[(task_id, a)] = result
    except Exception:  # noqa: BLE001 —— 準備度失敗不影響媒合
        logger.exception("match task: 準備度判斷失敗 %s", a)
        result = {"a": a, "state": "error"}
    cur = _load(path)
    if not cur or cur.get("task_id") != task_id or cur.get("status") != "select":
        return
    if (cur.get("readiness") or {}).get("a") not in (None, a):
        return   # 使用者已改選別的 A
    cur["readiness"] = result
    _save(path, cur)
    await _publish(cur)


async def ready_answer(task: dict, runtime, data: Mapping) -> dict:
    """補問的一個回答：consent 為 true 才走既有寫回流程（不改原文，只附加）。"""
    a = (task.get("readiness") or {}).get("a")
    if not a or data.get("a") not in (None, a):
        return {"result": "invalid"}
    try:
        return await ready.answer(runtime, uuid=a, key=str(data.get("key") or ""),
                                  answer=str(data.get("answer") or ""), consent=data.get("consent") is True,
                                  run_id=task.get("run_id"))
    except Exception:  # noqa: BLE001
        logger.exception("match task: 準備度寫回失敗 %s", a)
        return {"result": "error"}


async def _ready_answer_and_report(path: Path, task: dict, runtime, data: Mapping) -> None:
    """寫回後把結果記在快照（readiness.saved[key]＝ok／error），面板據此告訴使用者有沒有補進去。"""
    key = str(data.get("key") or "")
    out = await ready_answer(task, runtime, data)
    result = (out or {}).get("result")
    if data.get("consent") is not True or not key:
        return
    cur = _load(path)
    if not cur or cur.get("task_id") != task.get("task_id"):
        return
    r = cur.get("readiness") or {}
    if r.get("a") != (task.get("readiness") or {}).get("a"):
        return
    r.setdefault("saved", {})[key] = "ok" if result == "ok" else "error"
    cur["readiness"] = r
    _save(path, cur)
    await _publish(cur)


def _validate(task: dict, a, targets) -> str | None:
    ids = {p["uuid"] for p in task["projects"]}
    if not isinstance(a, str) or a not in ids:
        return "請先選擇你的專案 A。"
    initiable = task.get("initiable")
    if initiable is not None and a not in initiable:
        return "這個專案不能在本站發起媒合（寄不出邀請），請改選清單中的專案 A。"
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


def preview(task: dict, infos: Mapping[str, dict], judged: Mapping[str, dict]) -> dict:
    """#232 判斷中的星圖資料：讀到的案先出現（A 在第一顆），判斷完的帶 B1–B8（亮起），未判的沒有衛星。"""
    order = [u for u in [task["a"], *task["targets"]] if u in infos]
    projects = []
    for u in order:
        info = infos[u]
        side = galaxy(info, [], judged, [])["projects"][0] if u in judged else {
            "pid": u, "name": info["name"], "match": {k: {"role": "none", "evidence": []} for k in pair.B_KEYS}}
        projects.append({**side, "judged": u in judged})
    std = pair.load_standard()
    keys = {k: ((std.get("capability_registry") or {}).get(k) or {}).get("名稱", k) for k in pair.B_KEYS}
    return {"demo": False, "preview": True, "keys": keys, "a": task["a"], "projects": projects, "pairs": [],
            "total": len(task["targets"]) + 1}


async def _step(path: Path, task: dict, entry: dict, infos: Mapping[str, dict] | None = None,
                judged: Mapping[str, dict] | None = None) -> None:
    """記一筆進度並立刻推送（#232：每讀完一案、每判完一案都推，不等到最後）。"""
    task["progress"].append(entry)
    if infos is not None:
        task["preview"] = preview(task, infos, judged or {})
    _save(path, task)
    await _publish(task)


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
            await _step(path, task, {"uuid": uuid, "name": info["name"], "step": "fetch"}, infos)
        a, targets = infos[task["a"]], [infos[u] for u in task["targets"]]
        # #199：判斷前先切段，之後的原文引用都指回段落。
        segments = {u: flow.segment(info.get("philosophy_text") or "") for u, info in infos.items()}
        done: dict[str, dict] = {}

        async def on_judged(p: dict, result: dict) -> None:
            done[p["uuid"]] = result
            await _step(path, task, {"uuid": p["uuid"], "name": p["name"], "step": "judge"}, infos, done)

        judged = await handler.judge_all([a, *targets], llm, on_judged=on_judged)
        task["progress"].append({"step": "judged", "count": len(judged)})
        results = handler.analyze(a, targets, judged)
        await _step(path, task, {"step": "compare", "count": len(results)}, infos, judged)
        task.update(result=galaxy(a, targets, judged, results))
        try:
            await _suggest(task, infos, judged, segments, llm)
        except Exception:  # noqa: BLE001 —— 建議卡失敗不影響星圖結果
            logger.exception("match task: 建議卡產生失敗")
            task["cards"] = []
        task.pop("preview", None)
        task.update(status="done")
        try:
            await cl.Message(content=summary(task)).send()
        except Exception:  # noqa: BLE001
            logger.exception("match task: 摘要送出失敗")
    except Exception:  # noqa: BLE001
        logger.exception("match task failed")
        task.update(status="error", error="媒合失敗，請稍後按「開始新媒合」。")
    finally:
        _save(path, task)
        _release(path)
        await _publish(task)


def _scope(identity: Mapping | None) -> dict:
    idn = dict(identity or _session_get("law_task_identity") or {})
    if not idn:
        user = current_user()
        md = getattr(user, "metadata", None) or {}
        idn = {"project": md.get("project"), "user_id": getattr(user, "identifier", None)}
    tenant = idn.get("project") or idn.get("tenant_id") or "unknown"
    initiator = idn.get("user_id") or idn.get("email") or "unknown"
    return {"tenant": str(tenant), "initiator": str(initiator)}


async def _suggest(task: dict, infos: Mapping[str, dict], judged: Mapping[str, dict],
                   segments: Mapping[str, list], llm: Any) -> None:
    """#215：判斷完成 → engine.match → build_cards → 建議卡進快照；選案／判斷／卡片寫紀錄。"""
    scope = task.get("scope") or _scope(None)
    site = scope["tenant"]
    projects = {u: flow.engine_project(info, judged.get(u) or {}, site=site) for u, info in infos.items()}
    pa, pts = projects[task["a"]], [projects[u] for u in task["targets"]]
    matched = engine.match(pa, pts)
    try:
        built = cards.build_cards(matched, [pa, *pts], llm=llm, top_n=CARD_TOP_N)
    except Exception:  # noqa: BLE001 —— LLM 失敗就只用程式依引擎結果組字（不臆測）
        logger.exception("match task: 建議卡 LLM 失敗，改用程式組字")
        built = cards.build_cards(matched, [pa, *pts], llm=None, top_n=0)
    chunked = {u: {"segments": segments.get(u) or [],
                   "chunks": flow.chk.label_chunks(projects[u]["philosophy"], judged.get(u) or {})}
               for u in projects}
    flow.annotate_cards(built, projects, chunked)
    task["cards"] = flow.public_cards(built)
    for c in task["cards"]:  # #235：寄站內邀請的附言（確認框顯示全文，送出同一段）
        c["invite_message"] = flow.invite_message(pa.get("name") or "", c.get("fields"))
    task["card_state"] = {}
    task["progress"].append({"step": "cards", "count": len(built)})
    task["run_id"] = await flow.record_run(matched, built, tenant=scope["tenant"],
                                           initiator=scope["initiator"], actor=scope["initiator"])


# ── #215 卡片動作／寄站內邀請／補資料 ─────────────────────────────────

def _card(task: dict, target) -> dict | None:
    return next((c for c in task.get("cards") or [] if c["target"] == target), None)


async def _say(text: str) -> None:
    try:
        await cl.Message(content=text).send()
    except Exception:  # noqa: BLE001
        logger.exception("match task: 訊息送出失敗")


async def on_card(path: Path, task: dict, runtime, data: Mapping) -> None:
    """面板上的卡片按鈕（使用者親手按的）；寄邀請另須確認框按「確定」（confirmed=true）。"""
    card = _card(task, data.get("target"))
    if card is None:
        return
    target, a = card["target"], task["a"]
    scope = task.get("scope") or {}
    actor = scope.get("initiator")
    state = task.setdefault("card_state", {}).setdefault(target, {})
    if data.get("action") == "invite":
        if data.get("confirmed") is not True:
            # 未確認：不呼叫 CMS，只回快照讓面板顯示確認框。
            state["invite"] = "confirm"
            await flow.record_action(task.get("run_id"), "invite_requested", target=target, actor=actor)
        elif state.get("invite") == "sent":
            return
        else:
            # #235：附言只送使用者在確認框看到的那段（面板回傳的 message 與卡上附言相同才附上）。
            message = card.get("invite_message") or ""
            if data.get("message") != message:
                message = ""
            res = await flow.send_invite(runtime, project_uuid=a, target_project_uuid=target,
                                         confirmed=True, message=message)
            ok = res.get("status") == "ok"
            state["invite"] = "sent" if ok else "error"
            await flow.record_action(task.get("run_id"), "invite", target=target, actor=actor,
                                     payload={"result": res.get("status"), "reason": res.get("reason")})
            await _say(f"已寄出站內邀請給「{card['name']}」。" if ok
                       else f"站內邀請沒有寄出（{res.get('reason') or res.get('status')}），請稍後再試。")
    else:
        op = data.get("op")
        if op not in flow.CARD_ACTIONS:
            return
        res = await flow.card_action(runtime, action=op, project_uuid=a, target_project_uuid=target)
        state[op] = res.get("status") == "ok"
        await flow.record_action(task.get("run_id"), op, target=target, actor=actor,
                                 payload={"result": res.get("status"), "reason": res.get("reason")})
        if op == flow.SUPPLEMENT:
            question = card["fields"].get(cards.F_CONFIRM) or "請補充這次合作還需要確認的事。"
            task["clarify"] = {"target": target, "uuid": a, "question": question}
            await _say(f"**補資料｜{card['name']}**\n\n{question}\n\n請直接在對話回覆，Eva 會記在這次媒合。")
    _save(path, task)
    await _publish(task)


async def answer_clarify(path: Path, runtime, answer: str, ask) -> dict | None:
    """補資料的回答：問要不要寫回自己可管理那案的計畫理念（#201），同意才 append_philosophy。"""
    task = _load(path)
    pending = (task or {}).get("clarify")
    if not pending or not (answer or "").strip():
        return None
    task["clarify"] = None
    _save(path, task)
    out = await flow.writeback_with_record(runtime, task.get("run_id"), uuid=pending["uuid"],
                                           question=pending["question"], answer=answer, ask=ask)
    task = _load(path) or task
    task.setdefault("card_state", {}).setdefault(pending["target"], {})["supplement"] = out.get("result")
    _save(path, task)
    msg = {"ok": "已把補充附加到你的計畫理念（只附加、不改寫原文）。",
           "declined": "好的，補充只留在這次媒合紀錄，不寫回計畫書。",
           "not_manageable": "已記下補充；這個計畫不是你能管理的，所以不寫回。",
           }.get(out.get("result"), "補充已記下，但寫回計畫書沒有成功，請稍後再試。")
    await _say(msg)
    await _publish(task)
    return out


async def _ask_user(prompt: str):
    try:
        res = await cl.AskUserMessage(content=prompt, timeout=300).send()
    except Exception:  # noqa: BLE001
        logger.exception("match task: 詢問寫回失敗")
        return None
    if isinstance(res, Mapping):
        return res.get("output") or res.get("content")
    return getattr(res, "output", None) or getattr(res, "content", None)


async def on_text(text: str) -> bool:
    """對話文字：若有待回答的補資料就接手（回 True）；否則交還原本的處理。"""
    if not (text or "").strip() or not enabled_for(current_project()):
        return False
    ctx = context()
    if ctx is None:
        return False
    task = _load(ctx[0])
    if not task or not task.get("clarify"):
        return False
    await answer_clarify(*ctx, text, _ask_user)
    return True


# ── Eva 說明（只用已存結果，不重判） ──────────────────────────────────

def _names(task: dict) -> dict[str, str]:
    return {p["pid"]: p["name"] for p in (task.get("result") or {}).get("projects") or []}


def summary(task: dict, lang: str | None = None) -> str:
    """聊天裡的媒合摘要；依使用者語言（#229，預設本連線語言）。專案名稱不翻；zh 與修改前一字不差。"""
    from app.matching import i18n as mi18n

    lang = mi18n.resolve(lang) if lang else _lang()
    res = task["result"]
    names = _names(task)
    lines = [mi18n.msg("summary.head", lang, a=names.get(res["a"], ""), n=len(res["pairs"])), ""]
    for p in res["pairs"]:
        c = p["counts"]
        lines.append(mi18n.msg("summary.pair", lang, name=names.get(p["pb"], p["pb"]),
                               status=mi18n.tr(p["status_text"], lang),
                               c=c["complement"], t=c["third"], p=c["peer"]))
    if task.get("cards"):
        lines += ["", mi18n.msg("summary.cards", lang, n=len(task["cards"]))]
    lines += ["", mi18n.msg("summary.explain", lang), mi18n.msg("summary.note", lang)]
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
        await handle_event(*ctx, meta, identity=_session_get("law_task_identity"))
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
    await open_task(*ctx, preselect_a=take_preselect())
    return True


PRESELECT_KEY = "match_preselect_a"   # app/main.py 開場依 eva_open cookie 自動開啟時放進 session（#237）


def take_preselect() -> str | None:
    """取出並清掉預選 A（只用一次）。"""
    value = _session_get(PRESELECT_KEY)
    if value:
        try:
            cl.user_session.set(PRESELECT_KEY, None)
        except Exception:  # noqa: BLE001
            pass
    return value if isinstance(value, str) and value else None
