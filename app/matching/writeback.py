"""補問回答寫回 philosophy（ai-eva #201，MVP 步驟 5；決策見 docs/match-mvp-decisions.md §2）。

規則：
- 使用者回答補問後，Eva 問「要把這段補充寫回計畫書嗎？」；**明確同意才寫**，
  不同意（或答得含糊）只留在本次媒合紀錄。
- **只對使用者自己能管理的那一案詢問**：CMS ``list_my_projects`` 有這案才問；
  對方專案（或查不到清單）不問、不寫。
- **只附加、不改寫**：補充接在原文後並標註來源
  （例：「（2026-11-23 補充，經 AI-Eva 媒合補問）」）。
- 寫入走 CMS 寫入工具 ``append_philosophy``（kind=write、needs_confirm；
  town-intelligent/tplanet-multi-tenant#504），參數只有 uuid 與補充文字。
  使用者已明確同意，所以以 ``confirmed=True`` 呼叫。
- 寫回結果（not_manageable／declined／ok／error）記進媒合紀錄：
  ``records.add_answer``（writeback＝是否同意）＋一筆 ``status`` 事件。
- 寫回成功後 philosophy 雜湊改變；有給 chunk store 就立刻以新內容
  ``chunks.ensure_chunks`` 重跑判斷（Label and chunk）。

runtime 為 ToolRuntime 風格物件（``await runtime.execute(name, args, confirmed=...)``）；
ask 為 ``async (prompt) -> 回覆``（字串或 bool），由 Chainlit 轉接層（#178）提供。
"""
from __future__ import annotations

import datetime as _dt
import inspect
import logging
import re
from typing import Any, Awaitable, Callable, MutableMapping, Optional, Union

from app.matching import chunks as chk
from app.matching import records as rec

logger = logging.getLogger(__name__)

TOOL = "append_philosophy"
LIST_TOOL = "list_my_projects"
INFO_TOOL = "get_project_info"
ASK_PROMPT = "要把這段補充寫回計畫書嗎？"
SEPARATOR = "\n\n"
EVENT_TYPE = "philosophy_writeback"

# 結果
NOT_MANAGEABLE = "not_manageable"
DECLINED = "declined"
OK = "ok"
ERROR = "error"

Ask = Callable[[str], Union[Awaitable[Any], Any]]

_NO = re.compile(r"不要|不用|不必|不需要|不想|不好|不行|不同意|先不|別|算了|拒絕|免了|\bno\b|\bnope\b|\bn\b", re.I)
_YES = re.compile(r"^(要|好|可以|同意|是|對|確定|沒問題|請?寫回|寫吧|ok|okay|yes|y$|sure)", re.I)


def source_note(today: Optional[_dt.date] = None) -> str:
    """來源標註，例：「（2026-11-23 補充，經 AI-Eva 媒合補問）」。"""
    d = today or _dt.date.today()
    return f"（{d.isoformat()} 補充，經 AI-Eva 媒合補問）"


def addition_text(answer: str, today: Optional[_dt.date] = None) -> str:
    """要附加的一段：補充內容＋來源標註（送給 append_philosophy 的文字）。"""
    return f"{(answer or '').strip()}{source_note(today)}"


def appended(original: str, answer: str, today: Optional[_dt.date] = None) -> str:
    """原文＋附加段＋來源標註；原文一字不動（是新內容的前綴）。"""
    original = original or ""
    sep = SEPARATOR if original.strip() else ""
    return f"{original}{sep}{addition_text(answer, today)}"


def parse_consent(reply: Any) -> bool:
    """只有明確同意才算同意；拒絕、含糊、空白一律 False。"""
    if isinstance(reply, bool):
        return reply
    text = re.sub(r"[\s。．.！!，,～~]+", "", str(reply or "")).strip()
    if not text or _NO.search(text):
        return False
    return bool(_YES.match(text))


def _data(result: dict) -> Any:
    inner = (result or {}).get("result", {})
    return inner.get("data", inner) if isinstance(inner, dict) else inner


async def _maybe_await(v):
    return await v if inspect.isawaitable(v) else v


async def is_manageable(runtime, uuid: str) -> bool:
    """這案是否在使用者 CMS ``list_my_projects`` 裡；查詢失敗視為不可管理（不問、不寫）。"""
    try:
        res = await runtime.execute(LIST_TOOL, {})
    except Exception:  # noqa: BLE001
        logger.exception("writeback: list_my_projects failed")
        return False
    if (res or {}).get("status") != "ok":
        logger.warning("writeback: list_my_projects %s", (res or {}).get("reason") or (res or {}).get("status"))
        return False
    data = _data(res)
    items = data.get("projects", []) if isinstance(data, dict) else data
    uuids = set()
    for p in items or []:
        if isinstance(p, str):
            uuids.add(p)
        elif isinstance(p, dict) and p.get("uuid"):
            uuids.add(str(p["uuid"]))
    return str(uuid) in uuids


async def _fetch_philosophy(runtime, uuid: str) -> str:
    res = await runtime.execute(INFO_TOOL, {"uuid": uuid})
    if (res or {}).get("status") != "ok":
        return ""
    info = _data(res)
    return str(info.get("philosophy") or "") if isinstance(info, dict) else ""


async def _record(conn, run_id, *, uuid, question, answer, consented, outcome) -> None:
    if conn is None or run_id is None:
        return
    await rec.add_answer(conn, run_id, question=question, answer=answer, target=uuid, writeback=consented)
    await rec.add_event(conn, run_id, "status", target=uuid, payload={"type": EVENT_TYPE, **outcome})


async def offer_writeback(
    runtime,
    *,
    uuid: str,
    question: str,
    answer: str,
    ask: Ask,
    conn=None,
    run_id: Optional[int] = None,
    philosophy: Optional[str] = None,
    today: Optional[_dt.date] = None,
    store: Optional[MutableMapping[str, Any]] = None,
    analyzer: Optional[Callable[[str], dict]] = None,
) -> dict:
    """補問回答後的寫回流程；回傳結果 dict（``result`` ∈ not_manageable／declined／ok／error）。

    philosophy：原文（沒給就以 get_project_info 讀）；用來算新內容與雜湊。
    conn / run_id：有給就把回答與寫回結果記進媒合紀錄。
    store / analyzer：有給 store 且寫回成功，就以新內容重跑判斷與切段。
    """
    uuid = str(uuid)
    answer = answer or ""
    if not answer.strip() or not await is_manageable(runtime, uuid):
        out = {"result": NOT_MANAGEABLE, "asked": False, "uuid": uuid}
        await _record(conn, run_id, uuid=uuid, question=question, answer=answer, consented=False, outcome=out)
        return out

    consented = parse_consent(await _maybe_await(ask(ASK_PROMPT)))
    if not consented:
        out = {"result": DECLINED, "asked": True, "uuid": uuid}
        await _record(conn, run_id, uuid=uuid, question=question, answer=answer, consented=False, outcome=out)
        return out

    original = philosophy if philosophy is not None else await _fetch_philosophy(runtime, uuid)
    text = addition_text(answer, today)
    try:
        res = await runtime.execute(TOOL, {"uuid": uuid, "supplement": text}, confirmed=True)
    except Exception as e:  # noqa: BLE001
        logger.exception("writeback: append_philosophy transport error")
        res = {"status": "error", "reason": f"{type(e).__name__}: {e}"}

    if (res or {}).get("status") != "ok":
        reason = (res or {}).get("reason") or (res or {}).get("status") or "unknown"
        out = {"result": ERROR, "asked": True, "uuid": uuid, "reason": str(reason)}
        await _record(conn, run_id, uuid=uuid, question=question, answer=answer, consented=True, outcome=out)
        return out

    new_philosophy = appended(original, answer, today)
    out = {
        "result": OK,
        "asked": True,
        "uuid": uuid,
        "appended": text,
        "old_hash": chk.content_hash(original),
        "new_hash": chk.content_hash(new_philosophy),
    }
    await _record(conn, run_id, uuid=uuid, question=question, answer=answer, consented=True, outcome=out)
    out["philosophy"] = new_philosophy
    if store is not None:
        rerun = chk.ensure_chunks(uuid, new_philosophy, store, analyzer=analyzer)
        out["recomputed"] = rerun["recomputed"]
    return out
