"""LINE Bot 對話記憶（session memory）。

從 4-learn/rag-kit/apps/huwei_landmarks (虎科大 ch5) 移植過來、改寫成：
- 純 asyncpg（跟 line.py 的 line_users 表同風格）
- LLM 走 dispatch.converse()（device tools 綁同一次呼叫；用 LITELLM_LINE_KEY 算帳）

兩張表：
  line_sessions          一筆 = 一段對話。ended_at IS NULL → active
  line_session_messages  role=user/assistant、按 created_at 排序

對外 5 個 function：
- ensure_session_tables()        啟動建表
- start_session(session_key)     開新 session（若有 active 先收掉）
- end_session(session_id, reason)
- chat(session_key, text)        收訊 → 拿/建 active session → LLM → 回覆字串
- scan_timeouts(idle_minutes)    回傳逾時的 active session（給 /tasks 用）

session_key：1:1 = userId；群組 = `group:<groupId>`；聊天室 = `room:<roomId>`。
（line_sessions.user_id 欄位實際存的是 session_key。）
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import asyncpg

from app import dispatch
from app.settings import LITELLM_LINE_KEY

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_CONTEXT_TURNS = int(os.getenv("SESSION_CONTEXT_TURNS", "12"))
_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))

EVA_SYSTEM_PROMPT = """你是 Eva，使用者的個人 AI 助手。

回答原則：
- 簡短、口語、繁體中文（每則回覆 100 字內）
- 不確定的事情誠實說「我不確定」、不要編造
- 跟使用者像朋友聊天，不端架子
- 你可以聊一般話題、知識問答、生活想法；不適合的請求（醫療診斷 / 法律意見）建議找專業
"""


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def ensure_session_tables() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; session memory disabled")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS line_sessions (
                id              BIGSERIAL PRIMARY KEY,
                user_id         TEXT NOT NULL,
                started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ended_at        TIMESTAMPTZ,
                end_reason      TEXT,
                summary         TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_line_sessions_user_active
                ON line_sessions (user_id, ended_at);

            CREATE TABLE IF NOT EXISTS line_session_messages (
                id          BIGSERIAL PRIMARY KEY,
                session_id  BIGINT NOT NULL REFERENCES line_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS ix_line_session_messages_session
                ON line_session_messages (session_id, created_at);
            """
        )
    finally:
        await conn.close()


async def get_active_session(session_key: str) -> Optional[dict]:
    if not _DATABASE_URL:
        return None
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT id, user_id, started_at FROM line_sessions "
            "WHERE user_id = $1 AND ended_at IS NULL "
            "ORDER BY id DESC LIMIT 1",
            session_key,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def start_session(session_key: str) -> dict:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE line_sessions SET ended_at = NOW(), end_reason = 'replaced' "
            "WHERE user_id = $1 AND ended_at IS NULL",
            session_key,
        )
        row = await conn.fetchrow(
            "INSERT INTO line_sessions (user_id) VALUES ($1) "
            "RETURNING id, user_id, started_at",
            session_key,
        )
        return dict(row)
    finally:
        await conn.close()


async def end_session(session_id: int, reason: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE line_sessions SET ended_at = NOW(), end_reason = $2 "
            "WHERE id = $1 AND ended_at IS NULL",
            session_id, reason,
        )
    finally:
        await conn.close()


async def _add_message(session_id: int, role: str, content: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO line_session_messages (session_id, role, content) VALUES ($1, $2, $3)",
            session_id, role, content,
        )
        await conn.execute(
            "UPDATE line_sessions SET last_message_at = NOW() WHERE id = $1",
            session_id,
        )
    finally:
        await conn.close()


async def _recent_messages(session_id: int, limit: int) -> list[dict]:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT role, content FROM line_session_messages "
            "WHERE session_id = $1 ORDER BY id DESC LIMIT $2",
            session_id, limit,
        )
        return list(reversed([dict(r) for r in rows]))
    finally:
        await conn.close()


async def chat(
    session_key: str,
    user_text: str,
    project: Optional[str] = None,
    image_path: Optional[str] = None,
    image_mime: Optional[str] = None,
) -> dict:
    """收 user 一則訊息 → 拿 active session（沒有就建）→ append → agentic LLM → 回 {reply, commands}。

    session_key：1:1 = userId，群組 = `group:<groupId>`，聊天室 = `room:<roomId>`（每個群獨立記憶）。
    結束關鍵字判斷在 caller (line.py)，這層只處理「一般對話 / 順手指揮裝置」。
    走 dispatch.converse：device tools 綁進同一次呼叫，要嘛派工要嘛聊天（不再雙呼叫）。
    commands 由 caller 負責 enqueue（這層不碰 node queue）。
    image_path/image_mime：LINE 圖片訊息用（opencode 路由限定；LiteLLM 路徑不吃圖）。
    """
    sess = await get_active_session(session_key) or await start_session(session_key)
    sid = sess["id"]

    await _add_message(sid, "user", user_text or "（圖片）")

    history = await _recent_messages(sid, _CONTEXT_TURNS)

    messages = [{"role": "system", "content": EVA_SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]

    commands: list = []
    try:
        result = await dispatch.converse(
            project or "", messages, api_key=LITELLM_LINE_KEY or None
        )
        reply = result["reply"] or "（這次沒拿到回應，再試一次）"
        commands = result["commands"]
    except Exception as e:  # noqa: BLE001
        logger.exception("converse failed for LINE user %s", session_key)
        reply = f"⚠️ 我這邊暫時遇到問題，再試一次（{type(e).__name__}）"

    await _add_message(sid, "assistant", reply)
    return {"reply": reply, "commands": commands}


async def scan_timeouts(idle_minutes: Optional[int] = None) -> list[dict]:
    """回傳 idle 超過 N 分鐘的 active session（已 mark ended、reason=timeout）。

    呼叫者拿到 user_id 後負責 push 告別訊息（避免本模組 import LINE SDK）。
    """
    if not _DATABASE_URL:
        return []
    minutes = idle_minutes if idle_minutes is not None else _TIMEOUT_MINUTES
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "UPDATE line_sessions SET ended_at = NOW(), end_reason = 'timeout' "
            "WHERE ended_at IS NULL "
            "  AND last_message_at < NOW() - ($1 || ' minutes')::interval "
            "RETURNING id, user_id",
            str(minutes),
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────
# 結束關鍵字 + 告別訊息（從 rag-kit ch5 直抄）
# ──────────────────────────────────────────────────────────────────

END_KEYWORDS = {
    "bye", "Bye", "BYE",
    "/end", "/bye",
    "end", "End",
    "再見", "掰掰", "結束", "結束對話", "下次見",
}

GOODBYE_USER_INITIATED = "好的，這次對話結束 ✅\n再傳訊息給我就會開始新對話、記憶會重置。"
GOODBYE_TIMEOUT = "🌙 30 分鐘沒互動，這次對話自動結束。\n再傳訊息給我就會開始新對話、記憶會重置。"


def is_end_keyword(text: str) -> bool:
    return text.strip() in END_KEYWORDS
