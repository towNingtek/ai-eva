"""模型對照場域 — 同一個問題、所有模型平行回答。

每個「node」就是一條獨立 streaming 路徑（plain asyncio.gather 並行）。
要加新 model：在 `_MODELS` list 加一行（前提是 LiteLLM config 已註冊該 alias）。
Model selection 是 node 自己宣告的責任，不是 app 統一規定。
"""
import asyncio
import logging

import chainlit as cl

from app.core.llm import make_llm

logger = logging.getLogger(__name__)

# (顯示用 label, LiteLLM alias) — alias=None 走 LITELLM_DEFAULT_MODEL (cloud-fast)
_MODELS: list[tuple[str, str | None]] = [
    ("🟢 OpenAI gpt-4o-mini", None),
    ("🟡 Pi5 Qwen 2.5:3b",    "local-cheap"),
    # 未來加 Claude / Gemini：先在 litellm-config.yaml 新增 model_name，再加一行：
    # ("🔵 Claude 3.5 Sonnet", "claude-sonnet"),
    # ("🟣 Gemini 2.0 Flash",  "gemini-flash"),
]


async def _stream_one(label: str, alias: str | None, prompt: str, parent_id: str) -> None:
    """一個 model = 一個 Chainlit message bubble，平行 streaming。"""
    bubble = cl.Message(content=f"### {label}\n\n", parent_id=parent_id)
    await bubble.send()
    try:
        async for chunk in make_llm(alias=alias).astream(prompt):
            content = getattr(chunk, "content", "") or ""
            if content:
                await bubble.stream_token(content)
    except Exception as e:
        logger.exception("model %s failed: %s", alias or "default", e)
        await bubble.stream_token(f"\n\n❌ 此模型呼叫失敗：`{type(e).__name__}: {e}`")
    await bubble.update()


async def handle(payload: str, msg: cl.Message) -> None:
    query = payload.strip()
    if not query:
        await cl.Message(
            content="🪞 **模型對照**\n\n輸入任何問題，所有設定好的模型會同時回答給你看。",
            parent_id=msg.id,
        ).send()
        return

    await asyncio.gather(
        *(_stream_one(label, alias, query, msg.id) for label, alias in _MODELS)
    )
