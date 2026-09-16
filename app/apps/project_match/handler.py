"""過渡版專案媒合（ai-eva#134）。

舊版（tplanet-multi-tenant `stable` 的 `PlanningModule.jsx`）在前端隨機抽兩個專案、
拼中文 prompt 丟舊的外部聊天後端 `/api/chat`。這裡照 `social_post` 的取料路徑搬到 ai-eva：

    list_plans(email) → runtime.execute("list_my_projects")
    plan_info(uuid)   → runtime.execute("get_project_info", {"uuid": ...})
    前端 prompt       → build_intent() → run_copilot()

與舊版的差異只有兩處（都是修缺陷，不是重構）：
1. 每個專案只取一次 `get_project_info`（舊版抽中後會再抓一遍）。
2. 走 ai-eva 自己的 LLM 路徑（舊的外部聊天後端維持退場，這裡不得回頭接）。

候選排序、相似度、SDG 比對一律不做 —— 那是正式媒合（townway#63）的範圍。
"""
import logging
import random
import re

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

from app.core.copilot import run_copilot

logger = logging.getLogger(__name__)

MIN_PROJECTS = 2

NEED_TWO_PROJECTS = (
    "⚠️ 專案媒合至少需要兩個專案，目前可用的專案不足。"
    "請先在 CMS 建立另一個專案，或確認你有第二個專案的管理權限後再試一次。"
)

_TAG = re.compile(r"<[^>]*>")


def _plain(value, fallback: str = "未提供") -> str:
    """去掉 CMS 富文字欄位的 HTML tag；空值給明確的 fallback，不留空字串。"""
    text = _TAG.sub("", str(value)).strip() if value else ""
    return text or fallback


def _budget(value) -> str:
    try:
        return f"NT$ {int(float(value)):,}"
    except (TypeError, ValueError):
        return _plain(value, "未揭露")


async def _projects(runtime) -> list[dict]:
    """取可管理的專案池。每個 uuid 只呼叫一次 get_project_info。"""
    result = await runtime.execute("list_my_projects", {})
    if result.get("status") != "ok":
        return []
    data = result.get("result", {}).get("data", result.get("result", {}))
    uuids = data.get("projects", []) if isinstance(data, dict) else []

    projects: list[dict] = []
    for uuid in uuids:
        detail = await runtime.execute("get_project_info", {"uuid": uuid})
        if detail.get("status") != "ok":
            continue
        info = detail.get("result", {}).get("data", detail.get("result", {}))
        if isinstance(info, dict) and info.get("name"):
            projects.append({**info, "uuid": uuid})
    return projects


def _describe(label: str, project: dict) -> str:
    return (
        f"【專案{label}：{project.get('name')}】\n"
        f"執行期間：{_plain(project.get('period'))}\n"
        f"預算：{_budget(project.get('budget'))}\n"
        f"主辦單位：{_plain(project.get('hoster') or project.get('org'))}\n"
        f"計劃理念：{_plain(project.get('philosophy'))}"
    )


def build_intent(pair: list[dict]) -> str:
    """組媒合 prompt。四個分析面向沿用舊版（實測有效），只補「資料已查好」的指示。"""
    first, second = pair[0], pair[1]
    return (
        "使用者剛點選了『專案媒合』工具。以下兩個專案的資料我已經查好了，"
        "請不要再呼叫工具查專案，直接根據這些資料進行媒合分析，並提出一個創新的合作提案：\n\n"
        f"{_describe('一', first)}\n\n"
        f"{_describe('二', second)}\n\n"
        "請分析這兩個專案的互補性，並提出具體的合作方案，包括：\n"
        "1. 兩個專案的共同目標和互補優勢\n"
        "2. 具體的合作模式和執行方式\n"
        "3. 預期的綜效和社會影響力\n"
        "4. 可能面臨的挑戰及解決方案\n"
        "只使用上面提供的專案資料，不要捏造事實；不自動寫回 CMS。"
    )


def pick_pair(projects: list[dict]) -> list[dict]:
    """隨機抽兩個不同專案（舊版是前端洗牌取前兩筆）。"""
    return random.sample(projects, MIN_PROJECTS)


async def handle(payload: str, msg: cl.Message) -> None:
    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await cl.Message(content="⚠️ 請先從 Yunlin CMS 重新進入 AI-Eva。").send()
        return

    try:
        projects = await _projects(runtime)
    except Exception as exc:  # noqa: BLE001
        logger.exception("project_match: 取專案資料失敗")
        await cl.Message(content=f"⚠️ 專案媒合取專案資料失敗（{type(exc).__name__}）。").send()
        return

    # 舊版是 alert("need_two_projects")；這裡同樣要講清楚，不可靜默失效。
    if len(projects) < MIN_PROJECTS:
        await cl.Message(content=NEED_TWO_PROJECTS).send()
        return

    pair = pick_pair(projects)
    intent = build_intent(pair)
    names = "、".join(p.get("name", "") for p in pair)
    history = cl.user_session.get("cms_history") or []
    try:
        result = await run_copilot(
            runtime,
            intent,
            history,
            api_key=cl.user_session.get("llm_key"),
            user=cl.user_session.get("llm_user"),
        )
        reply = result.get("reply") or "（專案媒合沒有產生回應）"
        history += [
            HumanMessage(content=f"（使用者點選專案媒合工具：{names}）"),
            AIMessage(content=reply),
        ]
        cl.user_session.set("cms_history", history[-12:])
        await cl.Message(content=reply).send()
    except Exception as exc:  # noqa: BLE001
        logger.exception("project_match tool failed")
        await cl.Message(content=f"⚠️ 專案媒合工具啟動失敗（{type(exc).__name__}）。").send()
