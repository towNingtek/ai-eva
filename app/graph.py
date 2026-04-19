from typing import List, TypedDict
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.rag.retriever import retrieve
from app.settings import LLM_MODEL, OPENAI_API_BASE, OPENAI_API_KEY


class State(TypedDict, total=False):
    question: str
    docs: List[dict]
    answer: str


def _llm():
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
        temperature=0.2,
        streaming=True,
    )


def retrieve_node(state: State) -> State:
    return {"docs": retrieve(state["question"])}


def generate_node(state: State) -> State:
    docs = state.get("docs", [])
    context = "\n\n".join(
        f"[來源: {d['source']}]\n{d['text']}" for d in docs
    ) or "（無檢索結果）"

    prompt = (
        "你是工程實驗助手 Eva。請根據下列參考資料回答問題，"
        "回答以繁體中文、條列清楚，若引用資料請標示來源。\n\n"
        f"=== 參考資料 ===\n{context}\n\n"
        f"=== 問題 ===\n{state['question']}"
    )

    resp = _llm().invoke(prompt)
    return {"answer": resp.content}


def build_graph():
    g = StateGraph(State)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()
