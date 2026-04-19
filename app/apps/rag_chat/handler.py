"""Default RAG chat: retrieve → generate, streaming."""
from typing import List, TypedDict

import chainlit as cl
from langgraph.graph import END, StateGraph

from app.core.llm import make_llm
from app.core.rag import retrieve


class State(TypedDict, total=False):
    question: str
    docs: List[dict]
    answer: str


def _retrieve(state: State) -> State:
    return {"docs": retrieve(state["question"])}


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
    resp = make_llm().invoke(prompt)
    return {"answer": resp.content}


def _build_graph():
    g = StateGraph(State)
    g.add_node("retrieve", _retrieve)
    g.add_node("generate", _generate)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


_graph = _build_graph()


async def handle(payload: str, msg: cl.Message) -> None:
    if not payload.strip():
        return

    response = cl.Message(content="")
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
            chunk, _meta = data
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
