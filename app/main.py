import json
import logging
import os
from pathlib import Path

import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

from app.apps._registry import discover, dispatch, manifest
from app.core.rag import ingest_to_session
from app.rag.ingest import SUPPORTED_SUFFIXES
from app.settings import ROOT

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    cl_data._data_layer = SQLAlchemyDataLayer(conninfo=DATABASE_URL)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

if ADMIN_PASS:
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        if username == ADMIN_USER and password == ADMIN_PASS:
            return cl.User(identifier=username, metadata={"role": "admin"})
        return None


discover()
_APPS_JSON = ROOT / "public" / "apps.json"
_APPS_JSON.write_text(
    json.dumps({"apps": manifest()}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
logger.info("Wrote %s with %d menu app(s)", _APPS_JSON, len(manifest()))


@cl.on_chat_start
async def on_start():
    await cl.Message(
        content=(
            "嗨，我是 **Eva**。\n\n"
            "- 直接輸入問題 → 走 RAG 問答\n"
            "- 點左下 **+** → 叫出工具（目前：🔍 網頁搜尋）\n"
            "- 把檔案拖進來 → 加入本次對話（僅此 session，關閉就清除）"
        )
    ).send()


async def _ingest_attachments(msg: cl.Message) -> None:
    for el in msg.elements or []:
        path = getattr(el, "path", None)
        if not path:
            continue
        name = getattr(el, "name", None) or Path(path).name
        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            await cl.Message(
                content=f"⚠️ `{name}`：暫不支援 `{suffix}`（目前支援 {', '.join(SUPPORTED_SUFFIXES)}）"
            ).send()
            continue

        status = cl.Message(content=f"📎 處理中：`{name}`（圖片型 PDF 會走 Vision OCR，較慢）")
        await status.send()
        try:
            n = await cl.make_async(ingest_to_session)(path, name)
            status.content = (
                f"📎 `{name}` 已加入本次對話（{n} chunks，僅此 session 可用）"
                if n
                else f"⚠️ `{name}`：讀取後沒有可索引內容"
            )
            await status.update()
        except Exception as e:
            status.content = f"❌ `{name}` 索引失敗：{e}"
            await status.update()


@cl.on_message
async def on_message(msg: cl.Message):
    if msg.elements:
        await _ingest_attachments(msg)

    content = (msg.content or "").strip()
    if not content:
        return

    app, payload = dispatch(content)
    logger.info("dispatch → %s (payload=%r)", app.id, payload[:60])
    await app.handle(payload, msg)
