import os
from pathlib import Path

import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

from app.graph import build_graph
from app.rag.ingest import SUPPORTED_SUFFIXES, ingest_one_file

_graph = build_graph()

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


@cl.on_chat_start
async def on_start():
    await cl.Message(
        content="嗨，我是 **Eva**。輸入問題開始，或把文件放進 `data/docs/` 再跑 ingest 餵 RAG。"
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

        status = cl.Message(content=f"🔍 處理中：`{name}`（若為圖片型 PDF 會走 Vision OCR，較慢）")
        await status.send()
        try:
            n = await cl.make_async(ingest_one_file)(path, name)
            if n:
                status.content = f"✅ `{name}` 已索引（{n} chunks）"
            else:
                status.content = f"⚠️ `{name}`：讀取後沒有可索引內容"
            await status.update()
        except Exception as e:
            status.content = f"❌ `{name}` 索引失敗：{e}"
            await status.update()


@cl.on_message
async def on_message(msg: cl.Message):
    if msg.elements:
        await _ingest_attachments(msg)

    if not (msg.content or "").strip():
        return

    response = cl.Message(content="")
    sources: list[dict] = []

    async for mode, data in _graph.astream(
        {"question": msg.content},
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates":
            retrieve_out = data.get("retrieve")
            if retrieve_out:
                sources = retrieve_out.get("docs", [])
        elif mode == "messages":
            chunk, _meta = data
            content = getattr(chunk, "content", "") or ""
            if content:
                await response.stream_token(content)

    if sources:
        src_text = "\n".join(
            f"- `{d['source']}`" + (f" (p.{d['page']})" if d.get("page") is not None else "")
            for d in sources
        )
        response.elements = [cl.Text(name="參考來源", content=src_text, display="inline")]

    await response.send()
