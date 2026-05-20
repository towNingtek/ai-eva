"""
Hello World — LangGraph plug-in 範例。

兩節點 pipeline：
  greet     純 Python：把 user input 包成 state，產生短招呼語
  elaborate LLM streaming：根據 state 產生個人化回應

未來新 app 沿用此骨架：meta.py 宣告、handler.py 實作 handle()。
"""
from typing import TypedDict

import chainlit as cl
from langgraph.graph import END, StateGraph

from app.core.llm import make_llm


class State(TypedDict, total=False):
    raw: str
    greeting: str


def _greet(state: State) -> State:
    raw = (state.get("raw") or "").strip()
    return {"greeting": f"👋 嗨，{raw}！" if raw else "👋 嗨！"}


def _elaborate_prompt(greeting: str, raw: str) -> str:
    return (
        "你是工程實驗助手 Eva。使用者剛剛跟你打招呼或自我介紹了一句。"
        "請以繁體中文、輕鬆友善的口吻，**接續這個招呼**展開兩到三句回應："
        "可以重述/呼應對方的內容、提出一個與該內容相關的友善開放式問題。"
        "不要客套冗詞、不要列點、不要超過 3 句話。\n\n"
        f"=== 招呼 ===\n{greeting}\n\n"
        f"=== 原始輸入 ===\n{raw}"
    )


def _build_graph():
    g = StateGraph(State)
    g.add_node("greet", _greet)
    # elaborate 直接 inline 在 handle() 內 streaming（LangGraph 不擅長把 token-level
    # stream 經由 graph 串回去 Chainlit），這邊 graph 收尾於 greet 後。
    g.set_entry_point("greet")
    g.add_edge("greet", END)
    return g.compile()


_graph = _build_graph()


async def handle(payload: str, msg: cl.Message) -> None:
    raw = (payload or "").strip()
    if not raw:
        await cl.Message(
            content="🫱 **打個招呼**\n\n輸入你想說的話（例如「我是 Yillkid」），會走 LangGraph 兩節點回應你。",
            parent_id=msg.id,
        ).send()
        return

    # Node 1: greet（純 Python）
    state = _graph.invoke({"raw": raw})
    greeting = state.get("greeting", "")

    status = cl.Message(content=greeting, parent_id=msg.id)
    await status.send()

    # Node 2: elaborate（LLM streaming）
    response = cl.Message(content="", parent_id=msg.id)
    await response.send()
    async for chunk in make_llm().astream(_elaborate_prompt(greeting, raw)):
        content = getattr(chunk, "content", "") or ""
        if content:
            await response.stream_token(content)
    await response.update()
