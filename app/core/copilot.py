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
    "再用拿到的 uuid 去查（例如查 SROI）。不要反過來要使用者提供 uuid。\n"
    "\n建立專案（create_project）請走『引導式問答』，不要拿到名稱就急著呼叫工具：\n"
    "1. 名稱（必填）：**先從使用者描述推測一個名稱**（例：『關於鄉村走讀計劃的專案』→ 名稱『鄉村走讀計劃』），"
    "推得出來就直接用、別空問『名稱是什麼』；真的推不出來才問。\n"
    "2. 拿到名稱後，**一次問一兩項**選填欄位，每項都明講『可跳過、直接說不用』：\n"
    "   主辦單位(org)、期程(project_start_date/project_due_date)、預算(budget)、動機(motivation)。\n"
    "   長文欄位（理念 philosophy / 規劃 project_planning）：問『要不要我幫你代擬一版、你再改？』願意就代擬。\n"
    "3. 使用者說『跳過/不用/沒有』→ 略過該項續問下一項；說『都不用了/直接建』→ 停止收集。\n"
    "4. 禮貌、簡短，尊重跳過，**別一口氣丟一長串表單**。\n"
    "5. 收集告一段落 → 彙整已填欄位摘要給使用者看 → 才呼叫 create_project（帶上收集到的所有欄位）。\n"
    "6. 專案建立後，**主動問一次**：『要不要順便幫你產一版 SROI 草稿？會花一點時間，產完你可進試算表自己改。』"
    "願意才往下；不想就略過、不糾纏。"
)


def _confirm_question(name: str, args: dict) -> str:
    """寫類工具待確認時，給使用者看的確認問句。"""
    if name == "create_project":
        return f"要建立專案「{args.get('name') or '（未命名）'}」嗎？確認後我就送出。"
    summary = "、".join(f"{k}={v}" for k, v in list(args.items())[:5])
    return f"要執行「{name}」嗎？（{summary}）確認後執行。"


def _fmt_result(name: str, data) -> str:
    """confirmed 執行成功後的回報。"""
    if isinstance(data, dict):
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        inner = inner or {}
        if name == "create_project":
            pname = inner.get("name") or "（未命名）"
            url = inner.get("url")
            uuid = inner.get("uuid") or inner.get("uuid_project")
            # ① 名稱+超連結（不要裸 uuid）
            link = f"[{pname}]({url})" if url else f"「{pname}」（uuid {uuid}）"
            # ② 告知 SDG 自動 + 主動問一次 SROI
            return (
                f"✅ 專案已建立：{link}\n\n"
                "我會自動幫你產生 **SDG 描述**。\n"
                "要不要順便產一版 **SROI 草稿**？會花一點時間，產完你可以進試算表自己修。"
            )
    return f"✅ 完成。\n```\n{json.dumps(data, ensure_ascii=False)[:500]}\n```"


async def run_copilot(
    runtime,
    user_text: str,
    history: list | None = None,
    *,
    api_key: str | None = None,
    max_rounds: int = 4,
) -> dict:
    """跑一輪副駕對話。回 {"reply": str, "pending": {name,args}|None}。

    讀類工具直接執行；寫類工具（needs_confirm）→ **停下、回 pending**，
    由 caller 出確認 UI，使用者同意後再以 confirmed=True 重打（execute_confirmed）。
    runtime: 已 load(manifest) 的 ToolRuntime；history: 之前的 langchain messages。
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
            return {"reply": (resp.content or "").strip() or "（這次沒拿到回應）", "pending": None}

        for tc in tool_calls:
            name, args, tc_id = tc.get("name", ""), tc.get("args") or {}, tc.get("id", "")
            result = await runtime.execute(name, args, confirmed=False)  # 先不 confirm
            logger.info("copilot tool %s(%s) → %s", name, args, result.get("status"))
            if result.get("status") == "need_confirm":
                # 寫類待確認：停下、把 pending 交給 caller（出確認鈕），不繼續這輪迴圈
                return {"reply": _confirm_question(name, args), "pending": {"name": name, "args": args}}
            msgs.append(ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=tc_id,
            ))

    final = await llm.ainvoke(msgs + [HumanMessage(content="請根據以上工具結果直接回答，不要再呼叫工具。")])
    return {"reply": (final.content or "").strip() or "（查了多輪仍未完成）", "pending": None}


async def execute_confirmed(runtime, name: str, args: dict) -> str:
    """使用者確認後，以 confirmed=True 真的執行 pending 寫類工具，回報結果。"""
    result = await runtime.execute(name, args, confirmed=True)
    logger.info("copilot confirmed %s(%s) → %s", name, args, result.get("status"))
    if result.get("status") == "ok":
        return _fmt_result(name, result.get("result"))
    return f"⚠️ 執行失敗：{result.get('reason', result.get('status'))}"
