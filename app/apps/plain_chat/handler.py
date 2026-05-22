"""Plain chat — 單一 LLM call streaming。

沒有 RAG、沒有 graph。`make_llm()` 預設走 cloud-fast（LiteLLM → OpenAI gpt-4o-mini）。
"""
import chainlit as cl

from app.core.llm import make_llm


async def handle(payload: str, msg: cl.Message) -> None:
    if not payload.strip():
        return

    response = cl.Message(content="", parent_id=msg.id)
    await response.send()

    async for chunk in make_llm().astream(payload):
        content = getattr(chunk, "content", "") or ""
        if content:
            await response.stream_token(content)

    await response.update()
