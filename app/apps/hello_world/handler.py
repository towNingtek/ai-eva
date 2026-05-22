"""模型對照場域 — 同一個問題、所有 LiteLLM 已註冊 model 平行回答。

設計：每次請求時動態抓 LiteLLM `/v1/models`，新增 model 進 `litellm-config.yaml`
後 hello_world 立即看到、零程式碼變動。

Model selection 是 node 的責任 — 每個 model 就是一個獨立 streaming node，
平行跑 asyncio.gather。Icon 用簡單字串 heuristic 推斷（純展示用，不維護對照表）。
"""
import asyncio
import logging

import chainlit as cl
import httpx

from app.core.llm import make_llm
from app.settings import LITELLM_API_BASE

logger = logging.getLogger(__name__)

# LiteLLM 內部別名「default」是 cloud-fast 的 alias，顯示會重複，跳過。
_SKIP_ALIASES = {"default"}


def _icon_for(alias: str) -> str:
    """從 alias 字串猜個視覺標記（零維護成本，命中不到就用 🔧）。"""
    a = alias.lower()
    if any(k in a for k in ("gpt", "openai", "cloud")):
        return "🟢"
    if any(k in a for k in ("claude", "anthropic")):
        return "🔵"
    if any(k in a for k in ("gemini", "google")):
        return "🟣"
    if any(k in a for k in ("qwen", "llama", "ollama", "local", "pi5")):
        return "🟡"
    return "🔧"


async def _list_aliases() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=3) as cx:
            r = await cx.get(f"{LITELLM_API_BASE}/models")
            r.raise_for_status()
            ids = [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        logger.warning("LiteLLM /v1/models query failed: %s", e)
        return []
    return [a for a in ids if a not in _SKIP_ALIASES]


async def _stream_one(label: str, alias: str, prompt: str, parent_id: str) -> None:
    bubble = cl.Message(content=f"### {label}\n\n", parent_id=parent_id)
    await bubble.send()
    try:
        async for chunk in make_llm(alias=alias).astream(prompt):
            content = getattr(chunk, "content", "") or ""
            if content:
                await bubble.stream_token(content)
    except Exception as e:
        logger.exception("model %s failed: %s", alias, e)
        await bubble.stream_token(f"\n\n❌ 此模型呼叫失敗：`{type(e).__name__}: {e}`")
    await bubble.update()


async def handle(payload: str, msg: cl.Message) -> None:
    query = payload.strip()
    if not query:
        await cl.Message(
            content="🪞 **模型對照**\n\n輸入任何問題，所有 LiteLLM 已註冊的 model 會同時回答。",
            parent_id=msg.id,
        ).send()
        return

    aliases = await _list_aliases()
    if not aliases:
        await cl.Message(
            content="🔴 拿不到 model 清單（LiteLLM 可能掛了或網路不通）",
            parent_id=msg.id,
        ).send()
        return

    await asyncio.gather(
        *(_stream_one(f"{_icon_for(a)} {a}", a, query, msg.id) for a in aliases)
    )
