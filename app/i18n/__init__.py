"""AI-Eva 介面語言（EPIC #205 / #206）。

CMS 通行證（handoff token）帶 `lang` claim（tplanet-multi-tenant#507）→
`verify_handoff` 正規化後放進 identity → 存進 SSO session 與 Chainlit 使用者 metadata，
之後所有功能用 `current_lang()` 取得、用 `t(key)` 取固定文字。

只接受 zh／en／ja／ko；其他值或缺少一律 `zh`（既有使用者行為不變）。
"""
from __future__ import annotations

import logging
from typing import Any

from app.i18n.strings import APP_LABELS, STRINGS

logger = logging.getLogger(__name__)

SUPPORTED_LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")
DEFAULT_LANG = "zh"

# AI-Eva 語言 → Chainlit `.chainlit/translations/<locale>.json` 的 locale（前端 navigator.language 覆寫用）
CHAINLIT_LOCALES: dict[str, str] = {
    "zh": "zh-TW",
    "en": "en-US",
    "ja": "ja",
    "ko": "ko",
}

SESSION_KEY = "lang"   # cl.user_session / 使用者 metadata 的鍵


def normalize_lang(value: Any) -> str:
    """只接受 zh／en／ja／ko（大小寫、前後空白不計）；其他或缺少 → zh。"""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in SUPPORTED_LANGS:
            return v
    return DEFAULT_LANG


def chainlit_locale(lang: Any) -> str:
    return CHAINLIT_LOCALES[normalize_lang(lang)]


def current_lang() -> str:
    """目前這條 Chainlit 連線的語言。

    優先序：user_session["lang"]（SSO 載入時寫入、refresh 時更新）→ 使用者 metadata["lang"]
    → zh。不在 Chainlit context（LINE、背景工作、測試）一律 zh。
    """
    try:
        import chainlit as cl

        lang = cl.user_session.get(SESSION_KEY)
        if lang:
            return normalize_lang(lang)
        user = cl.user_session.get("user") or getattr(cl.context.session, "user", None)
        md = getattr(user, "metadata", None) or {}
        return normalize_lang(md.get(SESSION_KEY))
    except Exception:  # noqa: BLE001 — 沒有 context / 沒裝 chainlit
        return DEFAULT_LANG


def set_current_lang(lang: Any) -> str:
    """把語言寫進本連線的 Chainlit user_session；回正規化後的值。"""
    norm = normalize_lang(lang)
    try:
        import chainlit as cl

        cl.user_session.set(SESSION_KEY, norm)
    except Exception:  # noqa: BLE001
        logger.debug("set_current_lang outside Chainlit context", exc_info=True)
    return norm


def t(key: str, lang: Any = None, **kwargs: Any) -> str:
    """取固定文字。lang 省略 → current_lang()。缺語言退回 zh，缺鍵回 key 本身（不炸）。"""
    lang = normalize_lang(lang) if lang is not None else current_lang()
    entry = STRINGS.get(key)
    if entry is None:
        logger.warning("i18n: missing key %r", key)
        return key
    text = entry.get(lang) or entry[DEFAULT_LANG]
    return text.format(**kwargs) if kwargs else text


def app_label(app_id: str, default: str = "", lang: Any = None) -> str:
    """工具按鈕／命令選單的標籤。表上沒有的 app 退回它 meta.py 的 label。"""
    lang = normalize_lang(lang) if lang is not None else current_lang()
    entry = APP_LABELS.get(app_id)
    if not entry:
        return default or app_id
    return entry.get(lang) or entry.get(DEFAULT_LANG) or default or app_id


def all_app_labels(app_id: str) -> set[str]:
    """某 app 在所有語言的標籤（比對「使用者點了選單送出的標籤字」用）。"""
    return set((APP_LABELS.get(app_id) or {}).values())


__all__ = [
    "APP_LABELS",
    "CHAINLIT_LOCALES",
    "DEFAULT_LANG",
    "SESSION_KEY",
    "STRINGS",
    "SUPPORTED_LANGS",
    "all_app_labels",
    "app_label",
    "chainlit_locale",
    "current_lang",
    "normalize_lang",
    "set_current_lang",
    "t",
]
