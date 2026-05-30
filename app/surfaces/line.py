"""LINE Messaging API adapter。

掛在 Chainlit 的 FastAPI app 上：
- `/webhook/line`        收 LINE 事件 → 簽章驗證 → message / follow / unfollow
  - message text → session.chat() (with memory) → reply
  - 結束關鍵字 → end_session + reply 告別
- `/tasks/scan-timeouts` 給 sidecar curl 每 60s 戳，掃 idle 過久 session、push 告別
- follow → 把 userId 存進 PG `line_users`（給 push 用）

session 記憶實作在 line_session.py（兩張表 line_sessions / line_session_messages）。
push helper `push_to_user()` 給 M4 cron worker / scan_timeouts 用。
"""
import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Optional

import asyncpg
import httpx
from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request

from app.surfaces import line_session
from app.settings import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
)

logger = logging.getLogger(__name__)

_LINE_API = "https://api.line.me/v2/bot"
_DATABASE_URL = os.getenv("DATABASE_URL", "")
_SESSION_SCAN_TOKEN = os.getenv("SESSION_SCAN_TOKEN", "").strip()


def _pg_url() -> str:
    """SQLAlchemy URL → asyncpg-compatible URL."""
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def ensure_line_table() -> None:
    """啟動時跑：建 line_users 表（沒就建，有就跳過）。"""
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; LINE follow events won't be persisted")
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS line_users (
                user_id       TEXT PRIMARY KEY,
                display_name  TEXT,
                followed_at   TIMESTAMPTZ DEFAULT NOW(),
                unfollowed_at TIMESTAMPTZ,
                metadata      JSONB DEFAULT '{}'::jsonb
            )
            """
        )
    finally:
        await conn.close()


async def _save_follow(user_id: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            """
            INSERT INTO line_users (user_id, followed_at, unfollowed_at)
            VALUES ($1, NOW(), NULL)
            ON CONFLICT (user_id) DO UPDATE SET
                followed_at = NOW(),
                unfollowed_at = NULL
            """,
            user_id,
        )
    finally:
        await conn.close()


async def _mark_unfollow(user_id: str) -> None:
    if not _DATABASE_URL:
        return
    conn = await asyncpg.connect(_pg_url())
    try:
        await conn.execute(
            "UPDATE line_users SET unfollowed_at = NOW() WHERE user_id = $1",
            user_id,
        )
    finally:
        await conn.close()


async def _line_reply(reply_token: str, text: str) -> None:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.warning("LINE access token missing; skipping reply")
        return
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(
            f"{_LINE_API}/message/reply",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        if r.status_code >= 400:
            logger.error("LINE reply failed: %s %s", r.status_code, r.text[:200])


async def push_to_user(user_id: str, text: str) -> bool:
    """M4 cron worker 會 import 來用。沒有 access token 就 no-op。"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(
            f"{_LINE_API}/message/push",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        if r.status_code >= 400:
            logger.error("LINE push failed: %s %s", r.status_code, r.text[:200])
            return False
    return True


async def push_images_to_user(user_id: str, image_urls: list[str]) -> bool:
    """推一批圖片給 user。device surface 收 node 回報的影像時用。

    LINE image message 需要 HTTPS 公開 URL（originalContentUrl / previewImageUrl）。
    一次最多 5 則（LINE multicast 上限），多的截掉。
    """
    if not LINE_CHANNEL_ACCESS_TOKEN or not image_urls:
        return False
    messages = [
        {"type": "image", "originalContentUrl": u, "previewImageUrl": u}
        for u in image_urls[:5]
    ]
    async with httpx.AsyncClient(timeout=15) as cx:
        r = await cx.post(
            f"{_LINE_API}/message/push",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            json={"to": user_id, "messages": messages},
        )
        if r.status_code >= 400:
            logger.error("LINE image push failed: %s %s", r.status_code, r.text[:200])
            return False
    return True


def _verify_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(signature, expected)


@fastapi_app.post("/tasks/scan-timeouts")
async def scan_timeouts_endpoint(req: Request):
    """Sidecar 每 60s 來戳，掃 idle 過久的 session、push 告別訊息。

    `X-Scan-Token` 要符合 SESSION_SCAN_TOKEN（沒設就完全擋掉、避免裸跑）。
    """
    if not _SESSION_SCAN_TOKEN:
        raise HTTPException(503, "Session scanner not configured (SESSION_SCAN_TOKEN missing)")
    if req.headers.get("x-scan-token", "") != _SESSION_SCAN_TOKEN:
        raise HTTPException(403, "Invalid token")

    timed_out = await line_session.scan_timeouts()
    pushed = 0
    for row in timed_out:
        if await push_to_user(row["user_id"], line_session.GOODBYE_TIMEOUT):
            pushed += 1
    return {"ended": len(timed_out), "pushed": pushed}


@fastapi_app.post("/webhook/line")
async def line_webhook(req: Request):
    if not LINE_CHANNEL_SECRET:
        raise HTTPException(503, "LINE not configured (LINE_CHANNEL_SECRET missing)")

    body = await req.body()
    signature = req.headers.get("x-line-signature", "")
    if not _verify_signature(body, signature):
        logger.warning("LINE webhook bad signature")
        raise HTTPException(403, "Invalid signature")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Bad JSON")

    for event in data.get("events", []):
        await _handle_event(event)

    return {"ok": True}


async def _handle_event(event: dict) -> None:
    evt_type = event.get("type")
    source = event.get("source", {}) or {}
    user_id: Optional[str] = source.get("userId")

    if evt_type == "follow" and user_id:
        await _save_follow(user_id)
        logger.info("LINE follow: %s", user_id)
        return

    if evt_type == "unfollow" and user_id:
        await _mark_unfollow(user_id)
        logger.info("LINE unfollow: %s", user_id)
        return

    if evt_type != "message":
        return

    msg = event.get("message", {}) or {}
    if msg.get("type") != "text":
        return

    text = (msg.get("text") or "").strip()
    reply_token = event.get("replyToken")
    if not text or not reply_token or not user_id:
        return

    logger.info("LINE message from %s: %r", user_id, text[:80])

    # 順手把 message sender 也 upsert 進 line_users（如果之前 follow 沒抓到）
    await _save_follow(user_id)

    # 結束關鍵字 → 收掉 active session、回告別訊息
    if line_session.is_end_keyword(text):
        sess = await line_session.get_active_session(user_id)
        if sess is not None:
            await line_session.end_session(sess["id"], "user")
        await _line_reply(reply_token, line_session.GOODBYE_USER_INITIATED)
        return

    answer = await line_session.chat(user_id, text)
    await _line_reply(reply_token, answer)
