import logging

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

from app.core.copilot import run_copilot

logger = logging.getLogger(__name__)


_START_INTENT = (
    "使用者剛點選了『社群貼文』工具，請主動開始製作流程。"
    "請先用 list_my_projects 取得使用者可管理的專案；若有多個，列出專案名稱並請使用者選一個。"
    "請告訴使用者可以回覆專案編號或完整名稱；下一輪若使用者只回覆編號，依上一則清單對應該專案。"
    "若只有一個，直接告知你會根據該專案製作社群貼文，並詢問平台（Facebook/Instagram/一般社群）、"
    "語氣（正式/溫暖/活潑）與篇幅；若適合，先提出一個預設建議。"
    "只使用 CMS 專案資料，不要捏造事實；不自動發布或寫回 CMS。"
)


async def _projects(runtime):
    result = await runtime.execute("list_my_projects", {})
    if result.get("status") != "ok":
        return []
    data = result.get("result", {}).get("data", result.get("result", {}))
    projects = []
    for uuid in data.get("projects", []) if isinstance(data, dict) else []:
        detail = await runtime.execute("get_project_info", {"uuid": uuid})
        if detail.get("status") != "ok":
            continue
        info = detail.get("result", {}).get("data", detail.get("result", {}))
        if info.get("name"):
            projects.append({"uuid": uuid, "name": info["name"]})
    return projects


async def handle(payload: str, msg: cl.Message) -> None:
    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await cl.Message(content="⚠️ 請先從 Yunlin CMS 重新進入 AI-Eva。 ").send()
        return

    history = cl.user_session.get("cms_history") or []
    try:
        cl.user_session.set("social_post_active", True)
        cl.user_session.set("social_post_completed", False)
        result = await run_copilot(
            runtime,
            _START_INTENT,
            history,
            api_key=cl.user_session.get("llm_key"),
            user=cl.user_session.get("llm_user"),
        )
        reply = result.get("reply") or "（社群貼文工具沒有產生回應）"
        history += [HumanMessage(content="（使用者點選社群貼文工具）"), AIMessage(content=reply)]
        cl.user_session.set("cms_history", history[-12:])
        await cl.Message(content=reply).send()
    except Exception as exc:  # noqa: BLE001
        logger.exception("social_post tool failed")
        await cl.Message(content=f"⚠️ 社群貼文工具啟動失敗（{type(exc).__name__}）。").send()


async def handle_selection(content: str) -> None:
    """Resolve the user's project number/name before returning to Copilot."""
    runtime = cl.user_session.get("cms_runtime")
    projects = await _projects(runtime) if runtime else []
    choice = content.strip()
    selected = None
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(projects):
            selected = projects[index]
    else:
        selected = next((p for p in projects if p["name"] == choice), None)
    if not selected:
        names = "\n".join(f"{i}. {p['name']}" for i, p in enumerate(projects, 1))
        await cl.Message(content=f"請回覆專案編號或完整名稱：\n{names}").send()
        return

    cl.user_session.set("social_post_active", False)
    cl.user_session.set("social_post_completed", True)
    history = cl.user_session.get("cms_history") or []
    prompt = (
        f"使用者已選擇專案「{selected['name']}」（uuid={selected['uuid']}）。"
        "請用 get_project_info 取得該專案資料，接著詢問社群平台、語氣與篇幅；"
        "不要再詢問使用者要選哪個專案，也不要要求使用者輸入 prompt。"
    )
    result = await run_copilot(
        runtime, prompt, history,
        api_key=cl.user_session.get("llm_key"),
        user=cl.user_session.get("llm_user"),
    )
    reply = result.get("reply") or "（社群貼文工具沒有產生回應）"
    history += [HumanMessage(content=f"（選擇專案：{selected['name']}）"), AIMessage(content=reply)]
    cl.user_session.set("cms_history", history[-12:])
    await cl.Message(content=reply).send()
