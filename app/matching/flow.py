"""媒合流程串接（ai-eva #215）：星球判斷之後的建議卡、卡片動作、寄站內邀請、補問寫回、全程紀錄。

這裡只放「可單獨測」的零件；呼叫 engine.match / cards.build_cards 的地方在
app/apps/match_analysis/task.py（媒合任務完成那一步）。

- 切段（#199）：判斷前先把每案 philosophy 切段（chunks.split_segments），判斷後以
  chunks.label_chunks 標籤；建議卡上的原文引用都附上「第幾段」。
- 引擎輸入：CMS 專案 → engine 的 {id, site, public, name, philosophy, capabilities}。
  使用者在 CMS 看得到、自己指定的對象視為公開、同站台（第一期只在同一租戶內媒合）。
- 卡片動作：收藏／略過／補資料 → CMS 工具 ``/matching/card_action``
  （action + project_uuid + target_project_uuid）。
- 寄站內邀請 → CMS 工具 ``/matching/invite``。**AI 不自動寄**：``send_invite`` 只接受
  使用者在面板按下「寄站內邀請」並在確認框按「確定」後送來的事件（confirmed=True）；
  沒確認一律不呼叫 CMS。這個模組沒有任何其他呼叫 invite 工具的路徑，也不登錄成 LLM 工具。
- 補問寫回（#201）：``clarify_writeback`` 包 writeback.offer_writeback，同意才 append_philosophy。
- 紀錄（#198）：選案（run + candidate）、判斷（judgements + ranked，同 engine.write_record）、
  建議卡（status / type=cards）、每個動作（favorite / skip / invite / status）。
  沒有 DATABASE_URL 就不寫（比照 schema.ensure_matching_tables），不影響使用者流程。
- 閱讀者語言（#227）：面板上的卡片、動作名稱、寫回詢問跟 current_lang()；
  **紀錄與 CMS 寫回一律中文**：卡片紀錄用 card["record_fields"]，補問題目換回中文版再記，
  寫回內容（回答＋來源標註）照 writeback 原樣。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from app.i18n import DEFAULT_LANG
from app.matching import chunks as chk
from app.matching import engine as eng
from app.matching import i18n as mi
from app.matching import records as rec
from app.matching import writeback as wb

logger = logging.getLogger(__name__)

CARD_ACTION_TOOL = "/matching/card_action"
INVITE_TOOL = "/matching/invite"

FAVORITE, SKIP, SUPPLEMENT = "favorite", "skip", "supplement"
CARD_ACTIONS = (FAVORITE, SKIP, SUPPLEMENT)
ACTION_LABEL = {FAVORITE: "收藏", SKIP: "略過", SUPPLEMENT: "補資料", "invite": "寄站內邀請"}


def action_labels(lang: Any = None) -> dict[str, str]:
    """卡片動作的顯示名稱（依閱讀者語言；zh 與 ACTION_LABEL 相同）。"""
    return {k: mi.msg(f"action.{k}", lang) for k in ACTION_LABEL}


# 面板上顯示的（外文）補問題目 → 中文版：寫回紀錄只記中文。public_cards 登記，clarify_writeback 查。
_RECORD_TEXT: dict[str, str] = {}
_RECORD_TEXT_MAX = 2048


def record_text(text: str) -> str:
    """顯示文字 → 紀錄用中文；沒登記過（本來就是中文）原樣。"""
    return _RECORD_TEXT.get(text, text)
# 紀錄的事件種類（records.EVENT_KINDS）；補資料沒有專屬種類，記成 status。
EVENT_KIND = {FAVORITE: "favorite", SKIP: "skip", SUPPLEMENT: "status", "invite": "invite"}


# ── 切段與引擎輸入 ───────────────────────────────────────────────────

def segment(philosophy: str) -> list[dict]:
    """判斷前切段：[{index, start, end, text}]。"""
    text = philosophy or ""
    return [{"index": i, "start": s, "end": e, "text": text[s:e]}
            for i, (s, e) in enumerate(chk.split_segments(text))]


def segment_of(quote: str, philosophy: str, segments: Sequence[Mapping]) -> Optional[int]:
    """原文引用落在第幾段（0 起算）；找不到回 None。"""
    pos = (philosophy or "").find(quote or "")
    if not quote or pos < 0:
        return None
    end = pos + len(quote)
    for seg in segments:
        if seg["start"] < end and seg["end"] > pos:
            return int(seg["index"])
    return None


def engine_project(info: Mapping, judgement: Mapping, *, site: str) -> dict:
    """CMS 專案（handler.fetch_info）＋判斷 → engine.match 的輸入。"""
    return {
        "id": str(info["uuid"]),
        "name": info.get("name") or str(info["uuid"]),
        "philosophy": info.get("philosophy_text") or "",
        "site": site,
        "public": True,
        "capabilities": dict(judgement or {}),
    }


def chunk_all(infos: Mapping[str, Mapping], judged: Mapping[str, Mapping]) -> dict[str, dict]:
    """每案 {segments, chunks}：segments 是判斷前的切段，chunks 是判斷後有標籤的段落。"""
    out = {}
    for uuid, info in infos.items():
        text = info.get("philosophy_text") or ""
        out[uuid] = {"segments": segment(text),
                     "chunks": chk.label_chunks(text, judged.get(uuid) or {})}
    return out


def annotate_cards(cards: list[dict], projects: Mapping[str, Mapping],
                   chunked: Mapping[str, Mapping]) -> list[dict]:
    """在每張卡的「推薦依據」上加「原文段落」：每段引文 → 哪一案第幾段。"""
    by_name = {p.get("name"): uid for uid, p in projects.items()}
    for card in cards:
        refs = []
        both = (card.get("推薦依據") or {}).get("雙方原文") or {}
        for name, quotes in both.items():
            uid = by_name.get(name)
            if uid is None:
                continue
            text = projects[uid].get("philosophy") or ""
            segs = (chunked.get(uid) or {}).get("segments") or []
            for q in quotes:
                idx = segment_of(q, text, segs)
                if idx is not None:
                    refs.append({"計畫": name, "段落": idx + 1, "原文": q})
        card["原文段落"] = refs
    return cards


def public_cards(cards: Sequence[Mapping]) -> list[dict]:
    """給面板的卡：只帶白話欄位（不含內部結構與 B 代號）。

    外文卡（build_cards 附 lang）另帶 lang 與動作名稱 action_labels；鍵名維持中文（面板依鍵取值）。
    """
    out = []
    for c in cards:
        card = {
            "rank": c["rank"], "target": c["target"], "name": c["name"],
            "fields": dict(c["fields"]),
            "未評估": dict(c.get("未評估") or {}),
            "原文段落": list(c.get("原文段落") or []),
            "合作起步草案": c.get("合作起步草案"),
        }
        lang = c.get("lang")
        if lang and lang != DEFAULT_LANG:
            card["lang"] = lang
            card["action_labels"] = action_labels(lang)
            _remember_record_text(c)
        out.append(card)
    return out


def _remember_record_text(card: Mapping) -> None:
    from app.matching.cards import F_CONFIRM

    shown = (card.get("fields") or {}).get(F_CONFIRM)
    zh = (card.get("record_fields") or {}).get(F_CONFIRM)
    if shown and zh and shown != zh:
        if len(_RECORD_TEXT) >= _RECORD_TEXT_MAX:
            _RECORD_TEXT.clear()
        _RECORD_TEXT[shown] = zh


# ── CMS 工具 ────────────────────────────────────────────────────────

def tool_name(runtime, endpoint: str) -> str:
    """manifest 工具名：找 endpoint 相符的工具（CMS 可能取別的名字），找不到就用 endpoint 本身。"""
    tools = getattr(runtime, "_tools", None)
    if isinstance(tools, Mapping):
        if endpoint in tools:
            return endpoint
        for name, spec in tools.items():
            ep = str((spec or {}).get("endpoint") or "") if isinstance(spec, Mapping) else ""
            if ep and (ep == endpoint or ep.rstrip("/").endswith(endpoint.rstrip("/"))):
                return name
    return endpoint


async def card_action(runtime, *, action: str, project_uuid: str, target_project_uuid: str) -> dict:
    """收藏／略過／補資料 → CMS /matching/card_action（使用者已按下按鈕，以 confirmed=True 送）。"""
    if action not in CARD_ACTIONS:
        raise ValueError(f"未知卡片動作：{action}")
    args = {"action": action, "project_uuid": str(project_uuid),
            "target_project_uuid": str(target_project_uuid)}
    return await _call(runtime, CARD_ACTION_TOOL, args)


class InviteNotConfirmed(PermissionError):
    """寄站內邀請必須由使用者確認。"""


async def send_invite(runtime, *, project_uuid: str, target_project_uuid: str,
                      confirmed: bool, message: str = "") -> dict:
    """寄站內邀請：只有使用者按下並確認（confirmed=True）才呼叫 CMS /matching/invite。"""
    if confirmed is not True:
        raise InviteNotConfirmed("寄站內邀請需要使用者確認")
    args = {"project_uuid": str(project_uuid), "target_project_uuid": str(target_project_uuid)}
    if message:
        args["message"] = message
    return await _call(runtime, INVITE_TOOL, args)


async def _call(runtime, endpoint: str, args: dict) -> dict:
    try:
        res = await runtime.execute(tool_name(runtime, endpoint), args, confirmed=True)
    except Exception as e:  # noqa: BLE001
        logger.exception("match flow: %s 呼叫失敗", endpoint)
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}
    return res if isinstance(res, dict) else {"status": "error", "reason": "bad response"}


# ── 補問寫回 ────────────────────────────────────────────────────────

async def clarify_writeback(runtime, *, uuid: str, question: str, answer: str,
                            ask: Callable[[str], Awaitable[Any] | Any], conn=None,
                            run_id: Optional[int] = None, philosophy: Optional[str] = None) -> dict:
    """補問回答後：問要不要寫回自己可管理那案的計畫理念；同意才 append_philosophy。

    詢問句依閱讀者語言（zh 與 writeback.ASK_PROMPT 相同），日韓的「好／不要」換成中文同意詞再判斷；
    紀錄的題目換回中文版，寫回內容（回答＋中文來源標註）不翻。
    """
    lang = mi.resolve(None)
    if lang != DEFAULT_LANG:
        inner = ask

        async def ask(prompt: str):  # noqa: F811 —— 換成閱讀者語言的詢問句
            text = mi.msg("writeback.ask", lang) if prompt == wb.ASK_PROMPT else prompt
            reply = inner(text)
            if hasattr(reply, "__await__"):
                reply = await reply
            return mi.normalize_consent(reply)

    return await wb.offer_writeback(runtime, uuid=uuid, question=record_text(question), answer=answer,
                                    ask=ask, conn=conn, run_id=run_id, philosophy=philosophy)


# ── 紀錄（#198） ────────────────────────────────────────────────────

_SCHEMA_READY = False


async def connect():
    """媒合紀錄連線：沒有 DATABASE_URL 回 None（不寫紀錄）。測試以 monkeypatch 換成假連線。"""
    global _SCHEMA_READY
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return None
    import asyncpg

    from app.matching import schema

    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    if not _SCHEMA_READY:
        await schema.ensure_schema(conn)
        _SCHEMA_READY = True
    return conn


async def _close(conn) -> None:
    close = getattr(conn, "close", None)
    if close is None:
        return
    try:
        out = close()
        if hasattr(out, "__await__"):
            await out
    except Exception:  # noqa: BLE001
        logger.debug("match flow: close conn failed", exc_info=True)


async def _with_conn(fn):
    conn = None
    try:
        conn = await connect()
        if conn is None:
            return None
        return await fn(conn)
    except Exception:  # noqa: BLE001 —— 紀錄失敗不能擋住使用者流程
        logger.exception("match flow: 寫媒合紀錄失敗")
        return None
    finally:
        if conn is not None:
            await _close(conn)


async def record_run(result: Mapping, cards: Sequence[Mapping], *, tenant: str, initiator: str,
                     model: str = "", actor: Optional[str] = None) -> Optional[int]:
    """依序寫：選案（run + candidate）→ 判斷（judgements、exclude、ranked）→ 建議卡（status/cards）。"""
    async def go(conn):
        cfg = dict(result["ranking_config"])
        run_id = await rec.start_run(
            conn, tenant=tenant, initiator=initiator, project_a=result["a"], targets=result["targets"],
            standard_version=result["standard_version"] or "unknown",
            ranking_config_version=cfg["version"], ranking_config=cfg, model=model,
            meta={"profile_id": result["profile_id"], "effective_at": result["effective_at"],
                  "not_evaluated": result["not_evaluated"], "flow": "match_task"},
        )
        for t in result["targets"]:
            await rec.add_event(conn, run_id, "candidate", target=t, actor=actor,
                                payload={"type": "selection", "a": result["a"]})
        for ex in result["excluded"]:
            await rec.add_event(conn, run_id, "exclude", target=ex["target"], actor=actor,
                                payload={"reasons": ex["reasons"], "rules": ex["rules"]})
        for r in result["results"]:
            for dim in eng.DIMENSIONS:
                d = r["dimensions"][dim]
                evidence = (
                    {"a_needs_target_offers": d["a_needs_target_offers"],
                     "target_needs_a_offers": d["target_needs_a_offers"]}
                    if dim == eng.DIM_NEED_OFFER else
                    {"complements": d["complements"], "categories": d["categories"]}
                )
                await rec.add_judgement(conn, run_id, target=r["target"], dimension=dim, verdict=d["verdict"],
                                        rationale=d.get("rationale", d["verdict"]), evidence=evidence)
        await rec.add_event(conn, run_id, "ranked", actor=actor,
                            payload={"order": result["order"], "ranking": result["ranking"],
                                     "profile_id": result["profile_id"]})
        await rec.add_event(conn, run_id, "status", actor=actor,
                            payload={"type": "cards",
                                     "cards": [{"rank": c["rank"], "target": c["target"], "name": c["name"],
                                                "fields": c.get("record_fields") or c["fields"]}
                                               for c in cards]})
        return run_id
    return await _with_conn(go)


async def record_action(run_id: Optional[int], action: str, *, target: str, actor: Optional[str] = None,
                        payload: Optional[dict] = None) -> Optional[int]:
    """一個卡片動作（含寄邀請的請求與結果）記一筆事件。"""
    if run_id is None:
        return None
    kind = EVENT_KIND.get(action, "status")
    body = {"type": "card_action", "action": action, **(payload or {})}
    return await _with_conn(lambda conn: rec.add_event(conn, run_id, kind, target=target, actor=actor,
                                                       payload=body))


async def writeback_with_record(runtime, run_id: Optional[int], **kw) -> dict:
    """補問寫回 + 紀錄（有連線才記）。"""
    conn = None
    try:
        conn = await connect() if run_id is not None else None
    except Exception:  # noqa: BLE001
        logger.exception("match flow: 紀錄連線失敗")
        conn = None
    try:
        return await clarify_writeback(runtime, conn=conn, run_id=run_id if conn is not None else None, **kw)
    finally:
        if conn is not None:
            await _close(conn)
