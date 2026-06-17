"""CMS 副駕 tool-loop（issue #35，讀類）。

給一個已載入 manifest 的 ToolRuntime + 使用者問句，跑「LLM 選工具 → ToolRuntime 執行
→ 結果餵回 → 回答」的迴圈。只用 manifest 白名單內的工具（ToolRuntime deny-by-default）。

安全：寫類工具回 need_confirm 時**不自動執行**，原樣交給 LLM 轉述「需要確認」。
#35 範圍是讀類，manifest v1 全 read（needs_confirm=false）→ 直接跑。
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.llm import make_llm

logger = logging.getLogger(__name__)

COPILOT_SYSTEM = (
    "你是使用者在 CMS 的 AI 副駕。你只能用系統提供的工具查資料，"
    "不要臆測沒有的資訊。查到什麼就如實回答，查不到就說查不到。"
    "用繁體中文、簡潔。涉及需要確認的寫入操作時，先說明再請使用者確認。\n"
    "重要：當某工具需要專案 uuid 但使用者沒提供時，**先呼叫 list_my_projects 取得**，"
    "再用拿到的 uuid 去查（例如查 SROI）。不要反過來要使用者提供 uuid。"
)


async def run_copilot(
    runtime,
    user_text: str,
    history: list | None = None,
    *,
    api_key: str | None = None,
    max_rounds: int = 4,
) -> str:
    """跑一輪副駕對話，回最終文字。

    runtime: 已 load(manifest) 的 ToolRuntime
    history: 之前的 langchain messages（可選）
    """
    tools = runtime.visible_tools()
    llm = make_llm(api_key=api_key, streaming=False)
    if tools:
        llm = llm.bind_tools(tools)

    msgs: list = [SystemMessage(content=COPILOT_SYSTEM)]
    msgs += history or []
    msgs.append(HumanMessage(content=user_text))

    for _ in range(max_rounds):
        resp: AIMessage = await llm.ainvoke(msgs)
        msgs.append(resp)

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            return (resp.content or "").strip() or "（這次沒拿到回應）"

        for tc in tool_calls:
            name, args, tc_id = tc.get("name", ""), tc.get("args") or {}, tc.get("id", "")
            result = await runtime.execute(name, args, confirmed=False)  # 寫類不自動 confirm
            logger.info("copilot tool %s(%s) → %s", name, args, result.get("status"))
            msgs.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=tc_id,
            ))

    # 用完 max_rounds 還在叫工具 → 收尾要它直接回答
    final = await llm.ainvoke(msgs + [HumanMessage(content="請根據以上工具結果直接回答，不要再呼叫工具。")])
    return (final.content or "").strip() or "（查了多輪仍未完成）"
