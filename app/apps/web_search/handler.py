"""Web search app: Tavily → DuckDuckGo fallback → LLM summarize.

對使用者不暴露 provider 名稱；server log 才會記錄實際 provider。
"""
import logging

import chainlit as cl

from app.core.llm import make_llm
from app.core.search import search

logger = logging.getLogger(__name__)


def _badge(provider: str, note: str) -> str:
    if provider == "tavily":
        return "🔍 已搜尋"
    if provider == "duckduckgo":
        return "🔍 已搜尋（備援來源）" if note else "🔍 已搜尋"
    return "🔍 搜尋失敗"


async def handle(payload: str, msg: cl.Message) -> None:
    query = payload.strip()
    if not query:
        await cl.Message(
            content="🔍 **網頁搜尋**\n\n從左下 **+** → 「網頁搜尋」，再輸入你要查的關鍵字送出。"
        ).send()
        return

    status = cl.Message(content=f"🔍 搜尋中：**{query}**")
    await status.send()

    outcome = await search(query)
    logger.info("web_search provider=%s hits=%d note=%s", outcome.provider, len(outcome.hits), outcome.note)
    badge = _badge(outcome.provider, outcome.note)

    if not outcome.hits:
        status.content = f"{badge} — 沒有結果，稍後再試一次。"
        await status.update()
        return

    sources_md = "\n".join(
        f"{i+1}. [{h.title}]({h.url})" for i, h in enumerate(outcome.hits) if h.url
    )
    status.content = f"{badge} — 找到 {len(outcome.hits)} 筆\n\n{sources_md}"
    await status.update()

    context = "\n\n".join(
        f"[{i+1}] {h.title}\n{h.url}\n{h.content}"
        for i, h in enumerate(outcome.hits)
    )
    prompt = (
        "你是工程實驗助手 Eva。使用者下了網頁搜尋查詢，以下是搜尋結果。"
        "請綜合這些結果以繁體中文回答，條列清楚，"
        "每段引用標註 [編號]，對應下方來源列表。不要編造未出現的內容。\n\n"
        f"=== 搜尋結果 ===\n{context}\n\n"
        f"=== 查詢 ===\n{query}"
    )

    response = cl.Message(content="")
    await response.send()
    async for chunk in make_llm().astream(prompt):
        content = getattr(chunk, "content", "") or ""
        if content:
            await response.stream_token(content)
    await response.update()
