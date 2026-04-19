"""
Web search with graceful degradation:
  Tavily (primary) → DuckDuckGo (fallback) → empty + reason.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from app.settings import TAVILY_API_KEY, WEB_SEARCH_TOP_K

logger = logging.getLogger(__name__)

Provider = Literal["tavily", "duckduckgo", "none"]


@dataclass
class SearchHit:
    title: str
    url: str
    content: str


@dataclass
class SearchOutcome:
    provider: Provider
    hits: list[SearchHit]
    note: str = ""


async def _tavily(query: str, k: int) -> list[SearchHit]:
    async with httpx.AsyncClient(timeout=15) as cx:
        r = await cx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": k,
                "search_depth": "basic",
                "include_answer": False,
            },
        )
        r.raise_for_status()
        data = r.json()
    return [
        SearchHit(
            title=x.get("title", ""),
            url=x.get("url", ""),
            content=x.get("content", ""),
        )
        for x in data.get("results", [])
    ]


def _ddg_sync(query: str, k: int) -> list[SearchHit]:
    from ddgs import DDGS

    out: list[SearchHit] = []
    with DDGS() as d:
        for x in d.text(query, max_results=k) or []:
            out.append(
                SearchHit(
                    title=x.get("title", ""),
                    url=x.get("href", "") or x.get("url", ""),
                    content=x.get("body", "") or x.get("content", ""),
                )
            )
    return out


async def _ddg(query: str, k: int) -> list[SearchHit]:
    return await asyncio.to_thread(_ddg_sync, query, k)


async def search(query: str, k: int | None = None) -> SearchOutcome:
    k = k or WEB_SEARCH_TOP_K
    q = (query or "").strip()
    if not q:
        return SearchOutcome("none", [], "（空查詢）")

    if TAVILY_API_KEY:
        try:
            hits = await _tavily(q, k)
            return SearchOutcome("tavily", hits)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (401, 403):
                reason = "Tavily key 無效或過期"
            elif code == 429:
                reason = "Tavily 已達限額"
            else:
                reason = f"Tavily HTTP {code}"
            logger.warning("%s，降級到 DuckDuckGo", reason)
        except Exception as e:
            reason = f"Tavily 連線失敗：{type(e).__name__}"
            logger.warning("%s，降級到 DuckDuckGo", reason)
    else:
        reason = "未設定 TAVILY_API_KEY"

    try:
        hits = await _ddg(q, k)
        note = f"（降級：{reason}，改用 DuckDuckGo）" if TAVILY_API_KEY else ""
        return SearchOutcome("duckduckgo", hits, note)
    except Exception as e:
        logger.error("DuckDuckGo 也失敗：%s", e)
        return SearchOutcome(
            "none",
            [],
            f"搜尋服務都無法使用（{reason}；DuckDuckGo: {type(e).__name__}）",
        )


def is_configured() -> bool:
    """Tavily key 是否設定（供前端決定 UI 狀態）。DuckDuckGo 永遠算有，所以只判斷主 provider。"""
    return bool(TAVILY_API_KEY)
