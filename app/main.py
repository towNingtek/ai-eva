import asyncio
import logging
import os
from typing import Optional

import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from langchain_core.messages import AIMessage, HumanMessage

from app.apps._registry import chainlit_commands, default_app, discover, get_by_id
from app.core.copilot import run_copilot, execute_confirmed
from app.core.storage import LocalStorageClient
from app.dispatch import Envelope, handle_device_intent
from app.nodes import commands as node_commands
from app.settings import ROOT
from app.surfaces import line as line_surface  # 註冊 /webhook/line route
from app.surfaces import device as device_surface  # noqa: F401  # 註冊 /device/* route
from app.surfaces import sso as sso_surface  # noqa: F401  # 註冊 /sso/handoff route + SSO session
from app.surfaces import queue_consumer  # RabbitMQ consumer 給 M4 cron push 用

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
# web 來的裝置指令派給哪個 project（暫用單一 project；同 LINE，待 identity→project 映射）
WEB_DEVICE_PROJECT = os.getenv("WEB_DEVICE_PROJECT", "home")
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


# SSO（CMS 等 issuer）：/sso/handoff 種的 eva_sso cookie → 認證成 CMS 使用者。
# 與上面的 password auth 共存（Chainlit headerAuth / passwordAuth 是獨立 flag）：
# 有 cookie → header auth 認證；無 cookie → 退回 admin 密碼登入。
@cl.header_auth_callback
async def sso_header_auth(headers) -> Optional[cl.User]:
    cookie = headers.get("cookie") or ""
    sid = None
    for part in cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "eva_sso":
            sid = v
            break
    sess = await sso_surface.get_sso_session(sid)
    if not sess:
        return None  # 無有效 SSO → 退回 password 登入
    idn = sess["identity"]
    return cl.User(
        identifier=idn.get("email") or f'{idn["project"]}:{idn.get("user_id")}',
        metadata={
            "sso_session_id": sid,
            "project": idn["project"],
            "tenant_id": idn.get("tenant_id"),
            "role": "cms-user",
        },
    )


discover()

# 啟動時建表：line_users / line_sessions / line_session_messages（LINE 用）+ projects。
# Chainlit 沒 on_app_startup decorator，這裡直接用 asyncio fire-and-forget。
from app.surfaces import line_session  # noqa: E402
from app.projects import registry as project_registry  # noqa: E402
from app.nodes import registry as node_registry  # noqa: E402


async def _init_tables():
    await project_registry.ensure_projects_table()
    await node_registry.ensure_nodes_table()
    await node_commands.ensure_commands_table()
    await line_surface.ensure_line_table()
    await line_session.ensure_session_tables()
    await sso_surface.ensure_sso_sessions_table()


try:
    asyncio.get_event_loop().create_task(_init_tables())
except RuntimeError:
    asyncio.run(_init_tables())

# 啟 RabbitMQ consumer（如果 .env 有設 RABBITMQ_URL）
queue_consumer.start_in_background()


async def _register_commands():
    cmds = chainlit_commands()
    await cl.context.emitter.set_commands(cmds)
    logger.info("Registered %d command(s): %s", len(cmds), [c["id"] for c in cmds])


@cl.on_chat_resume
async def on_chat_resume(thread):
    await _register_commands()


async def _sso_session_for_current_user():
    """目前 Chainlit user 若是 SSO 認證的，回它的 SSO session（含 ToolRuntime）；否則 None。"""
    user = cl.user_session.get("user")
    sid = (getattr(user, "metadata", None) or {}).get("sso_session_id") if user else None
    return await sso_surface.get_sso_session(sid) if sid else None


@cl.on_chat_start
async def on_start():
    sess = await _sso_session_for_current_user()
    if sess:
        # CMS 副駕模式：載入該帳號的 ToolRuntime，走 copilot
        cl.user_session.set("cms_runtime", sess["runtime"])
        cl.user_session.set("cms_history", [])
        idn = sess["identity"]
        tools = [t["function"]["name"] for t in sess["runtime"].visible_tools()]
        await cl.Message(
            content=(
                f"嗨，我是你在 CMS 的 AI 副駕（{idn.get('email') or idn['project']}）。\n\n"
                f"我可以幫你查：{', '.join(tools) or '（目前無可用工具）'}。\n"
                "試試問「**列出我的專案**」或「**我的 SROI**」。"
            )
        ).send()
        return

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

    # CMS 副駕模式（SSO 認證）：用該帳號 manifest 的工具跑 copilot tool-loop。
    runtime = cl.user_session.get("cms_runtime")
    if runtime is not None:
        history = cl.user_session.get("cms_history") or []
        pending = None
        try:
            result = await run_copilot(runtime, content, history)
            ans, pending = result["reply"], result.get("pending")
        except Exception as e:  # noqa: BLE001
            logger.exception("CMS copilot failed")
            ans = f"⚠️ 查詢失敗，請再試一次（{type(e).__name__}）"
        history += [HumanMessage(content=content), AIMessage(content=ans)]
        cl.user_session.set("cms_history", history[-12:])
        if pending:
            # 寫類待確認：存 pending + 出確認鈕（confirm 控制訊號，避免 NLP 猜「好」）
            cl.user_session.set("pending_tool", pending)
            await cl.Message(content=ans, actions=[
                cl.Action(name="cms_confirm", payload={"decision": "yes"}, label="✅ 確認"),
                cl.Action(name="cms_confirm", payload={"decision": "no"}, label="✖ 取消"),
            ]).send()
        else:
            cl.user_session.set("pending_tool", None)
            await cl.Message(content=ans).send()
        return

    # 沒選特定工具時，先看是不是要指揮裝置（function-calling）。
    # 有派工 → enqueue 給 node（靠 /device/poll 拉）+ ack；沒派工 → 走原本 app 對話。
    # 註：執行結果走 project.line_recipient（→ LINE），不回 web（之後可做 per-surface 回送）。
    if not msg.command:
        try:
            dev = await handle_device_intent(
                Envelope(surface="web", project=WEB_DEVICE_PROJECT, text=content)
            )
        except Exception:
            logger.exception("web device dispatch failed")
            dev = {"commands": []}
        cmds = dev.get("commands") or []
        if cmds:
            nodes = set()
            for c in cmds:
                nid = c.get("node")
                if nid:
                    nodes.add(nid)
                    await node_commands.enqueue_command(nid, WEB_DEVICE_PROJECT, c, source="web")
            await cl.Message(
                content=f"好，已請 {'、'.join(sorted(nodes))} 處理（{len(cmds)} 個動作），結果會傳到 LINE 👌"
            ).send()
            return

    app = get_by_id(msg.command) if msg.command else None
    if app is None:
        app = default_app()
    if app is None:
        await cl.Message(content="⚠️ 沒有可用的處理器").send()
        return

    logger.info("dispatch → %s (command=%s, payload=%r)", app.id, msg.command, content[:60])
    await app.handle(content, msg)


@cl.action_callback("cms_confirm")
async def cms_confirm(action: cl.Action):
    """使用者按確認鈕 → 對 pending 寫類工具以 confirmed=True 重打（#51）。"""
    pending = cl.user_session.get("pending_tool")
    runtime = cl.user_session.get("cms_runtime")
    cl.user_session.set("pending_tool", None)
    if not (pending and runtime):
        await cl.Message(content="這個確認已失效，請重新說一次需求。").send()
        return
    if (action.payload or {}).get("decision") != "yes":
        await cl.Message(content="好，已取消，沒有送出。").send()
        return
    try:
        reply = await execute_confirmed(runtime, pending["name"], pending["args"])
    except Exception as e:  # noqa: BLE001
        logger.exception("CMS confirm execute failed")
        reply = f"⚠️ 執行失敗（{type(e).__name__}）"
    # 把執行結果寫回對話 history，讓後續輪次（如建好後主動問 SROI）知道已執行 + uuid
    history = cl.user_session.get("cms_history") or []
    history += [
        HumanMessage(content=f"（已確認執行 {pending['name']}）"),
        AIMessage(content=reply),
    ]
    cl.user_session.set("cms_history", history[-12:])
    await cl.Message(content=reply).send()
