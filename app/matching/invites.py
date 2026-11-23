"""進入 AI 秘書時提醒媒合邀請（ai-eva#213，EPIC #176）。

開啟對話時呼叫 CMS 工具 `list_my_match_invites`（tplanet-multi-tenant#505）：
- 有未回覆邀請 → 回一段「你有 N 個媒合邀請」＋列出發起專案與時間，讓 Eva 第一則訊息帶上。
- 0 個 → 回 None（不說）。
- 工具不存在 / 呼叫失敗 / 回傳格式看不懂 → 回 None，只記 log，不拋例外。

邀請資料只存在 CMS：這裡不寫檔、不寫表、不寫 session，每次開對話重新讀。
本模組不 import chainlit，方便以假 runtime 測試；按鈕由 main.py 依 `ACTION_NAME` 組。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

TOOL_NAME = "list_my_match_invites"
ACTION_NAME = "match_invites"
MAX_LISTED = 5

# 視為「已回覆／已結束」的狀態；其餘（含沒帶 status）都當未回覆。
_DONE_STATUSES = {
    "accepted", "declined", "rejected", "replied", "responded", "cancelled", "canceled",
    "expired", "closed", "done", "withdrawn",
    "已接受", "已婉拒", "已拒絕", "已回覆", "已取消", "已過期",
}
_LIST_KEYS = ("invites", "items", "results", "data", "list")
_PROJECT_KEYS = (
    "from_project_name", "initiator_project_name", "source_project_name", "inviter_project_name",
    "project_name", "from_project", "initiator_project", "source_project", "project", "name", "title",
)
_TIME_KEYS = ("created_at", "invited_at", "sent_at", "time", "date", "created")
_URL_KEYS = ("url", "link", "reply_url", "view_url")

_TEXT = {
    "zh": {
        "header": "📬 你有 {n} 個媒合邀請待回覆：",
        "more": "…還有 {n} 個",
        "unknown_project": "（未命名專案）",
        "view": "查看",
        "action": "📬 查看／回覆媒合邀請",
        "ask": "請列出我的媒合邀請，並告訴我怎麼回覆。",
    },
    "en": {
        "header": "📬 You have {n} match invitation(s) awaiting your reply:",
        "more": "…and {n} more",
        "unknown_project": "(unnamed project)",
        "view": "View",
        "action": "📬 View / reply to match invitations",
        "ask": "Please list my match invitations and tell me how to reply.",
    },
    "ja": {
        "header": "📬 未回答のマッチング招待が {n} 件あります：",
        "more": "…ほか {n} 件",
        "unknown_project": "（名称未設定のプロジェクト）",
        "view": "表示",
        "action": "📬 マッチング招待を確認／回答",
        "ask": "私のマッチング招待を一覧表示して、回答方法を教えてください。",
    },
}


def normalize_lang(lang: Optional[str]) -> str:
    s = (lang or "").strip().lower().replace("_", "-")
    if s.startswith("ja") or s == "jp":
        return "ja"
    if s.startswith("en"):
        return "en"
    return "zh"


def current_lang() -> str:
    """使用者語言（外文通道）。有共用 `current_lang()` 就用它，否則讀 chainlit session / user metadata。"""
    for mod_name in ("app.i18n", "app.core.i18n", "app.core.lang"):
        try:
            mod = __import__(mod_name, fromlist=["current_lang"])
            fn: Callable[[], Any] = getattr(mod, "current_lang")
            return normalize_lang(fn())
        except Exception:  # noqa: BLE001
            continue
    try:
        import chainlit as cl

        lang = cl.user_session.get("lang")
        if not lang:
            user = cl.user_session.get("user")
            lang = (getattr(user, "metadata", None) or {}).get("lang")
        return normalize_lang(lang)
    except Exception:  # noqa: BLE001
        return "zh"


def text(key: str, lang: Optional[str] = None) -> str:
    return _TEXT[normalize_lang(lang)][key]


@dataclass
class InviteReminder:
    count: int
    content: str
    lang: str
    invites: list[dict] = field(default_factory=list)


def _extract_list(raw: Any) -> Optional[list]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in _LIST_KEYS:
            if k in raw:
                inner = _extract_list(raw[k])
                if inner is not None:
                    return inner
    return None


def _first(d: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("title")
        if v not in (None, ""):
            return v
    return None


def _is_pending(inv: dict) -> bool:
    if inv.get("replied") is True or inv.get("responded") is True:
        return False
    status = str(inv.get("status") or "").strip().lower()
    return status not in _DONE_STATUSES


def format_reminder(invites: list[dict], lang: Optional[str] = None) -> str:
    lang = normalize_lang(lang)
    t = _TEXT[lang]
    lines = [t["header"].format(n=len(invites))]
    for inv in invites[:MAX_LISTED]:
        project = _first(inv, _PROJECT_KEYS) or t["unknown_project"]
        when = _first(inv, _TIME_KEYS)
        url = _first(inv, _URL_KEYS)
        line = f"- **{project}**"
        if when:
            line += f"（{when}）" if lang != "en" else f" ({when})"
        if url:
            line += f" [{t['view']}]({url})"
        lines.append(line)
    if len(invites) > MAX_LISTED:
        lines.append(t["more"].format(n=len(invites) - MAX_LISTED))
    return "\n".join(lines)


async def build_invite_reminder(runtime: Any, lang: Optional[str] = None) -> Optional[InviteReminder]:
    """讀 CMS 的未回覆媒合邀請，組成提醒；不該說話時回 None。永不拋例外。"""
    try:
        if runtime is None:
            return None
        is_allowed = getattr(runtime, "is_allowed", None)
        if callable(is_allowed) and not is_allowed(TOOL_NAME):
            logger.info("match invite reminder skipped: %s not in manifest", TOOL_NAME)
            return None
        result = await runtime.execute(TOOL_NAME, {})
        if not isinstance(result, dict) or result.get("status") != "ok":
            logger.warning("match invite reminder: %s failed: %r", TOOL_NAME,
                           (result or {}).get("reason") if isinstance(result, dict) else result)
            return None
        items = _extract_list(result.get("result"))
        if items is None:
            logger.warning("match invite reminder: unexpected %s payload shape", TOOL_NAME)
            return None
        pending = [i for i in items if isinstance(i, dict) and _is_pending(i)]
        if not pending:
            return None
        lang = normalize_lang(lang if lang is not None else current_lang())
        return InviteReminder(count=len(pending), content=format_reminder(pending, lang),
                              lang=lang, invites=pending)
    except Exception:  # noqa: BLE001
        logger.exception("match invite reminder failed")
        return None
