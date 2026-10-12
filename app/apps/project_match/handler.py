"""專案媒合 1.5 版：手動選擇媒合對象（townway#66 規格、#71 開發）。

1.0（ai-eva#134 過渡版）是隨機抽兩個專案丟 LLM。1.5 改成承辦人自己挑：

    list_my_projects        → 只拿 uuid 清單（便宜）
    MatchPicker 元件         → 下拉多選；一次 20 筆，「載入更多」再帶下一批 20 筆
    get_project_info(uuid)  → 逐筆抓、抓到一筆就推一筆到元件（不等整批）
    match_run               → 「我的專案」× 每個勾選的對象，各出一張媒合分析

規格：
- 手動選擇：AI 不隨機混入其他對象（julia 2026-09-24 確認：「AI 不隨機混入」）
- Panel 單次 20 筆、逐筆呈現

錯誤處理（ai-eva#137）：CMS 查詢失敗 / 權限不足要講清楚並記 log，
不可以被誤報成「專案不足」。「專案不足」只在真的少於 2 個專案時出現。
"""
import logging
import re

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

from app.core.copilot import run_copilot

logger = logging.getLogger(__name__)

MIN_PROJECTS = 2
BATCH_SIZE = 20
SESSION_KEY = "match_state"

NEED_TWO_PROJECTS = (
    "⚠️ 專案媒合至少需要兩個專案，目前可用的專案不足。"
    "請先在 CMS 建立另一個專案，或確認你有第二個專案的管理權限後再試一次。"
)

_TAG = re.compile(r"<[^>]*>")


class CmsError(RuntimeError):
    """CMS 查詢失敗（含權限不足）—— 和「專案不足」是不同的事，要分開回報。"""


def _plain(value, fallback: str = "未提供") -> str:
    """去掉 CMS 富文字欄位的 HTML tag；空值給明確的 fallback，不留空字串。"""
    text = _TAG.sub("", str(value)).strip() if value else ""
    return text or fallback


def _budget(value) -> str:
    try:
        return f"NT$ {int(float(value)):,}"
    except (TypeError, ValueError):
        return _plain(value, "未揭露")


def _data(result: dict):
    inner = result.get("result", {})
    return inner.get("data", inner) if isinstance(inner, dict) else inner


async def list_uuids(runtime) -> list[str]:
    """只拿 uuid（不抓明細）。失敗時丟 CmsError，不回空清單。"""
    result = await runtime.execute("list_my_projects", {})
    if result.get("status") != "ok":
        reason = result.get("reason") or result.get("error") or result.get("status") or "unknown"
        raise CmsError(f"list_my_projects: {reason}")
    data = _data(result)
    uuids = data.get("projects", []) if isinstance(data, dict) else []
    seen: set[str] = set()
    return [u for u in uuids if isinstance(u, str) and u and not (u in seen or seen.add(u))]


async def fetch_info(runtime, uuid: str) -> dict | None:
    """單筆明細；查不到或沒有名稱 → None（記 log，不中斷整批）。"""
    detail = await runtime.execute("get_project_info", {"uuid": uuid})
    if detail.get("status") != "ok":
        logger.warning("project_match: get_project_info %s failed: %s", uuid, detail.get("reason") or detail.get("status"))
        return None
    info = _data(detail)
    if isinstance(info, dict) and info.get("name"):
        return {**info, "uuid": uuid}
    return None


def _option(project: dict) -> dict:
    return {
        "uuid": project["uuid"],
        "name": _plain(project.get("name"), project["uuid"]),
        "period": _plain(project.get("period"), ""),
    }


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
        "使用者在『專案媒合』中手動選定了以下兩個專案。資料我已經查好了，"
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


# ---------------------------------------------------------------- 元件與狀態

def _new_element(total: int) -> cl.CustomElement:
    return cl.CustomElement(
        name="MatchPicker",
        display="inline",
        props={
            "options": [],      # 已載入的專案（逐筆增加）
            "loaded": 0,        # 已處理的 uuid 數（含查不到的）
            "total": total,     # 可選總數
            "loading": True,
            "running": False,
            "error": "",
        },
    )


async def load_batch(runtime, state: dict, element) -> None:
    """載入下一批 BATCH_SIZE 筆；每抓到一筆就 update 一次元件（逐筆呈現）。"""
    uuids = state["uuids"]
    start = state["cursor"]
    batch = uuids[start:start + BATCH_SIZE]
    element.props.update({"loading": True, "error": ""})
    await element.update()
    failed = 0
    for uuid in batch:
        try:
            project = await fetch_info(runtime, uuid)
        except Exception:  # noqa: BLE001
            logger.exception("project_match: get_project_info %s raised", uuid)
            project = None
        state["cursor"] += 1
        if project is None:
            failed += 1
        else:
            state["projects"][uuid] = project
            element.props["options"] = element.props["options"] + [_option(project)]
        element.props["loaded"] = state["cursor"]
        await element.update()
    element.props["loading"] = False
    if failed:
        element.props["error"] = f"有 {failed} 筆專案資料讀取失敗，已略過。"
    await element.update()


async def handle(payload: str, msg: cl.Message) -> None:
    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await cl.Message(content="⚠️ 請先從 CMS 重新進入 AI-Eva。").send()
        return

    try:
        uuids = await list_uuids(runtime)
    except Exception as exc:  # noqa: BLE001  —— ai-eva#137：不可誤報成專案不足
        logger.exception("project_match: 取專案清單失敗")
        await cl.Message(content=f"⚠️ 專案媒合無法讀取專案清單（{exc}）。請確認 CMS 連線與帳號權限後再試。").send()
        return

    if len(uuids) < MIN_PROJECTS:
        await cl.Message(content=NEED_TWO_PROJECTS).send()
        return

    element = _new_element(len(uuids))
    state = {"uuids": uuids, "cursor": 0, "projects": {}}
    cl.user_session.set(SESSION_KEY, state)
    cl.user_session.set("match_element", element)
    await cl.Message(
        content="🤝 請選擇「我的專案」，再勾選要媒合的對象（可多選）。",
        elements=[element],
    ).send()
    await load_batch(runtime, state, element)


@cl.action_callback("match_more")
async def match_more(action: cl.Action):
    runtime = cl.user_session.get("cms_runtime")
    state = cl.user_session.get(SESSION_KEY)
    element = cl.user_session.get("match_element")
    if not (runtime and state and element):
        await cl.Message(content="⚠️ 媒合面板已過期，請重新開啟「專案媒合」。").send()
        return
    if state["cursor"] >= len(state["uuids"]):
        return
    await load_batch(runtime, state, element)


async def run_matches(runtime, mine: dict, partners: list[dict]) -> None:
    """我的專案 × 每個對象，各送一次 LLM、各出一張卡。"""
    history = cl.user_session.get("cms_history") or []
    for partner in partners:
        pair = [mine, partner]
        try:
            result = await run_copilot(
                runtime,
                build_intent(pair),
                history,
                api_key=cl.user_session.get("llm_key"),
                user=cl.user_session.get("llm_user"),
            )
            reply = result.get("reply") or "（專案媒合沒有產生回應）"
            history = history + [
                HumanMessage(content=f"（專案媒合：{mine.get('name')} × {partner.get('name')}）"),
                AIMessage(content=reply),
            ]
            await cl.Message(content=f"### 🤝 {mine.get('name')} × {partner.get('name')}\n\n{reply}").send()
        except Exception as exc:  # noqa: BLE001
            logger.exception("project_match: 媒合分析失敗 %s × %s", mine.get("uuid"), partner.get("uuid"))
            await cl.Message(
                content=f"⚠️ {mine.get('name')} × {partner.get('name')} 媒合分析失敗（{type(exc).__name__}）。"
            ).send()
    cl.user_session.set("cms_history", history[-12:])


@cl.action_callback("match_run")
async def match_run(action: cl.Action):
    runtime = cl.user_session.get("cms_runtime")
    state = cl.user_session.get(SESSION_KEY)
    element = cl.user_session.get("match_element")
    if not (runtime and state):
        await cl.Message(content="⚠️ 媒合面板已過期，請重新開啟「專案媒合」。").send()
        return
    payload = action.payload or {}
    projects = state["projects"]
    mine = projects.get(payload.get("mine") or "")
    # 只用使用者勾選且已載入的對象；不補、不隨機（1.5 規格：AI 不隨機混入）
    partners = [projects[u] for u in dict.fromkeys(payload.get("partners") or [])
                if u in projects and u != (mine or {}).get("uuid")]
    if not mine or not partners:
        await cl.Message(content="⚠️ 請先選擇「我的專案」並至少勾選一個媒合對象。").send()
        return
    if element:
        element.props["running"] = True
        await element.update()
    try:
        await run_matches(runtime, mine, partners)
    finally:
        if element:
            element.props["running"] = False
            await element.update()
