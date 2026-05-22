import asyncio
import logging
import os

import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

from app.apps._registry import chainlit_commands, default_app, discover, get_by_id
from app.core.storage import LocalStorageClient
from app.settings import ROOT
from app.surfaces import line as line_surface  # 註冊 /webhook/line route

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    cl_data._data_layer = SQLAlchemyDataLayer(
        conninfo=DATABASE_URL,
        storage_provider=LocalStorageClient(ROOT / "public" / "elements"),
    )

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

if ADMIN_PASS:
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        if username == ADMIN_USER and password == ADMIN_PASS:
            return cl.User(identifier=username, metadata={"role": "admin"})
        return None


discover()

# 啟動時建 line_users 表（給 LINE follow event 紀錄用）。Chainlit 沒 on_app_startup
# decorator，這裡直接用 asyncio fire-and-forget。
try:
    asyncio.get_event_loop().create_task(line_surface.ensure_line_table())
except RuntimeError:
    # 沒 loop 就同步跑一次（import 階段）
    asyncio.run(line_surface.ensure_line_table())


async def _register_commands():
    cmds = chainlit_commands()
    await cl.context.emitter.set_commands(cmds)
    logger.info("Registered %d command(s): %s", len(cmds), [c["id"] for c in cmds])


@cl.on_chat_resume
async def on_chat_resume(thread):
    await _register_commands()


@cl.on_chat_start
async def on_start():
    await _register_commands()
    await cl.Message(
        content=(
            "嗨，我是 **Eva**。\n\n"
            "- 直接輸入問題 → 一般對話（OpenAI gpt-4o-mini）\n"
            "- 輸入框工具選單可挑：🪞 模型對照 / 🌐 網頁搜尋"
        )
    ).send()


@cl.on_message
async def on_message(msg: cl.Message):
    content = (msg.content or "").strip()
    if not content:
        return

    app = get_by_id(msg.command) if msg.command else None
    if app is None:
        app = default_app()
    if app is None:
        await cl.Message(content="⚠️ 沒有可用的處理器").send()
        return

    logger.info("dispatch → %s (command=%s, payload=%r)", app.id, msg.command, content[:60])
    await app.handle(content, msg)
