"""Default RAG chat: query_rewrite → retrieve → generate, streaming.

M2 起內部分流：
  query_rewrite  → Pi5 Qwen 把口語化問句改寫成檢索友善的 query（省 OpenAI 額度）
  retrieve       → Chroma 相似度搜尋（純本地、無 LLM）
  generate       → OpenAI 綜合 RAG 結果產生最終回應（streaming）
"""
import logging
from typing import List, TypedDict

import chainlit as cl
from langgraph.graph import END, StateGraph

from app.core.llm import make_llm
from app.core.rag import retrieve
from app.settings import LITELLM_CHEAP_MODEL

logger = logging.getLogger(__name__)


class State(TypedDict, total=False):
    question: str
    rewritten: str
    docs: List[dict]
    answer: str


def _query_rewrite(state: State) -> State:
    """用 cheap model（Pi5 Qwen）把口語問題改寫成適合 retrieve 的 query。

    失敗時退回原問題（LiteLLM 的 fallback 也會自動接手回 cloud-fast）。"""
    question = state["question"]
    prompt = (
        "把下列使用者口語問題，改寫成更精確的「檢索查詢」。要求：\n"
        "- 保留所有專有名詞 / 關鍵字\n"
        "- 移除冗詞、贅字、語助詞\n"
        "- 不要回答問題本身\n"
        "- 30 字內、單行\n"
        "- 只輸出改寫後的 query，不加任何說明\n\n"
        f"原問題：{question}\n"
        "改寫後："
    )
    try:
        llm = make_llm(alias=LITELLM_CHEAP_MODEL, temperature=0, streaming=False)
        rewritten = (llm.invoke(prompt).content or "").strip().split("\n")[0]
        if not rewritten or len(rewritten) > 200:
            rewritten = question
    except Exception as e:
        logger.warning("query_rewrite failed (%s); fall back to raw question", e)
        rewritten = question
    logger.info("query_rewrite: %r → %r", question, rewritten)
    return {"rewritten": rewritten}


def _retrieve(state: State) -> State:
    query = state.get("rewritten") or state["question"]
    return {"docs": retrieve(query)}


def _generate(state: State) -> State:
    docs = state.get("docs", [])

    def _label(d):
        tag = "📎" if d.get("scope") == "session" else "📚"
        src = d["source"]
        page = f" p.{d['page']}" if d.get("page") is not None else ""
        return f"{tag} {src}{page}"

    context = "\n\n".join(
        f"[來源: {_label(d)}]\n{d['text']}" for d in docs
    ) or "（無檢索結果）"

    prompt = (
        "你是工程實驗助手 Eva。請根據下列參考資料回答問題，"
        "回答以繁體中文、條列清楚，若引用資料請標示來源。\n"
        "標記說明：📎 = 使用者本次對話上傳；📚 = 知識庫。\n\n"
        f"=== 參考資料 ===\n{context}\n\n"
        f"=== 問題 ===\n{state['question']}"
    )
    resp = make_llm().invoke(prompt)   # 走預設 alias (cloud-fast / OpenAI)
    return {"answer": resp.content}


def _build_graph():
    g = StateGraph(State)
    g.add_node("query_rewrite", _query_rewrite)
    g.add_node("retrieve", _retrieve)
    g.add_node("generate", _generate)
    g.set_entry_point("query_rewrite")
    g.add_edge("query_rewrite", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


_graph = _build_graph()


async def handle(payload: str, msg: cl.Message) -> None:
    if not payload.strip():
        return

    response = cl.Message(content="", parent_id=msg.id)
    sources: list[dict] = []

    async for mode, data in _graph.astream(
        {"question": payload},
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates":
            retrieve_out = data.get("retrieve")
            if retrieve_out:
                sources = retrieve_out.get("docs", [])
        elif mode == "messages":
            chunk, meta = data
            # 只串 generate 節點的 token（query_rewrite 的中間結果不外露）
            if meta.get("langgraph_node") != "generate":
                continue
            content = getattr(chunk, "content", "") or ""
            if content:
                await response.stream_token(content)

    if sources:
        src_text = "\n".join(
            ("📎 " if d.get("scope") == "session" else "📚 ")
            + f"`{d['source']}`"
            + (f" (p.{d['page']})" if d.get("page") is not None else "")
            for d in sources
        )
        response.content = (response.content or "") + f"\n\n---\n**參考來源：**\n{src_text}"

    await response.send()
