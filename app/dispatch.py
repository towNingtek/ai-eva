"""統一 dispatch + Message 信封（issue #25 第 3、4 點）。

目標：web / LINE / device 各 surface 把輸入正規化成同一個 `Envelope`，
丟進同一條 dispatch，core 不需要知道訊息從哪個 surface / 哪種協議進來（headless）。

目前狀態（誠實標記）：
- ✅ device intent 走這裡（`handle_device_intent`）
- ✅ 「哪個 node 執行」正規化：查 node registry（`nodes_with_capability`），不硬寫
- ✅ 「intent → 要哪個 capability」用 **LLM function-calling**（cloud-fast）：
     只把該 project 真有 node 能執行的 capability 轉成 tool 餵給模型（tool 動態長出來），
     取代了 pilot 的關鍵字比對。決策中樞用可靠模型，edge 裝置才 downgrade。
- ⏳ web / LINE 還沒收斂進來（仍在各自的 on_message / webhook），後續再接。

tool 目錄（capability → tool schema）在 app/tools/registry.py（framework primitive）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.core.llm import make_llm
from app.nodes.registry import list_nodes, nodes_with_capability
from app.tools.registry import capability_for_tool, tools_for_capabilities

logger = logging.getLogger(__name__)

_DISPATCH_SYSTEM = (
    "你是 edge 裝置群的調度中樞。使用者透過某台裝置說了一句話，"
    "你要判斷這句話是否對應某個裝置動作（tool）。"
    "若對應就呼叫對的 tool（可多個）；若只是閒聊、提問、沒有要裝置做事，就不要呼叫任何 tool。"
    "只能使用提供給你的 tool，不要臆測不存在的能力。"
)


@dataclass
class Envelope:
    """各 surface 正規化後的統一訊息信封。"""
    surface: str                       # "device" | "line" | "web"
    project: str                       # 歸屬 project（決定可見性 / 收件人）
    text: str                          # 使用者意圖文字
    node_id: str | None = None         # device surface 才有：來源 node
    meta: dict = field(default_factory=dict)


def _json_list(v) -> list:
    """asyncpg JSONB 欄位可能回 str；統一成 list。"""
    if isinstance(v, str):
        try:
            v = json.loads(v or "[]")
        except json.JSONDecodeError:
            return []
    return v if isinstance(v, list) else []


def _json_obj(v) -> dict:
    if isinstance(v, str):
        try:
            v = json.loads(v or "{}")
        except json.JSONDecodeError:
            return {}
    return v if isinstance(v, dict) else {}


async def _select_capabilities(text: str, available: list[str]) -> list[tuple[str, dict]]:
    """LLM function-calling：intent → [(capability, args)]。

    只把 available（該 project 有 node 能做的）capability 轉成 tool 餵給 LLM。
    LLM / LiteLLM 出錯就回空（不派工），避免亂動裝置。
    """
    tools = tools_for_capabilities(available)
    if not tools:
        return []
    try:
        llm = make_llm(alias="cloud-fast", temperature=0, streaming=False).bind_tools(tools)
        resp = await llm.ainvoke(
            [("system", _DISPATCH_SYSTEM), ("human", text)]
        )
    except Exception as e:
        logger.exception("dispatch LLM tool-selection 失敗，不派工：%s", e)
        return []

    picked: list[tuple[str, dict]] = []
    for tc in getattr(resp, "tool_calls", None) or []:
        cap = capability_for_tool(tc.get("name", ""))
        if cap and cap in available:
            picked.append((cap, tc.get("args") or {}))
    return picked


async def handle_device_intent(env: Envelope) -> dict:
    """device intent → command 信封。

    回傳 {project, commands:[{capability, node, params}]}，node 主動拉走執行（NAT-friendly）。
    """
    # 1. 這個 project 有哪些 capability（node 自報的聯集）
    nodes = await list_nodes(env.project)
    available = sorted({c for n in nodes for c in _json_list(n.get("capabilities"))})
    if not available:
        logger.info("dispatch: project=%s 沒有任何 node 能力，不派工", env.project)
        return {"project": env.project, "commands": []}

    # 2. LLM 選 capability（function-calling）
    picked = await _select_capabilities(env.text, available)

    # 3. 每個選中的 capability 配 node + 展開 params → command
    commands = await _picked_to_commands(env.project, picked)

    logger.info(
        "dispatch device intent: node=%s project=%s text=%r → %d command(s)",
        env.node_id, env.project, env.text[:40], len(commands),
    )
    return {"project": env.project, "commands": commands}


async def _picked_to_commands(project: str, picked: list[tuple[str, dict]]) -> list[dict]:
    """[(capability, args)] → command 信封清單（查 node registry 配 node + 展開 params）。"""
    commands: list[dict] = []
    for cap, args in picked:
        cap_nodes = await nodes_with_capability(cap, project=project)
        if not cap_nodes:
            continue
        node = cap_nodes[0]   # 先挑第一個；之後可加偏好 / 負載策略
        commands.extend(_expand(cap, args, node))
    return commands


# 對話 surface（LINE / web）要拍照時的 ack 樣板（tool 被呼叫時 LLM content 多半空的）
_DEVICE_ACK = "好，已經請 {nodes} 處理（{n} 個動作），完成後傳給你 👌"


async def converse(project: str, messages: list, *, api_key=None, alias=None) -> dict:
    """對話 surface 的 agentic 單次呼叫：把該 project 的 device tools 綁進這一次 LLM。

    一次呼叫決定「派工」或「純聊天」，消掉「先 function-calling 再聊天」的雙呼叫。
    回 {"commands": [...], "reply": str}：
      - 有 tool_calls → commands + ack reply（node 靠 poll 拉走執行）
      - 沒有          → commands=[] + 對話 reply

    project 沒有任何 device 能力時，等同一般對話（不綁 tool、行為不變）。
    """
    nodes = await list_nodes(project)
    available = sorted({c for n in nodes for c in _json_list(n.get("capabilities"))})
    tools = tools_for_capabilities(available)

    llm = make_llm(api_key=api_key, alias=alias, streaming=False)
    if tools:
        llm = llm.bind_tools(tools)
    resp = await llm.ainvoke(messages)

    picked: list[tuple[str, dict]] = []
    for tc in getattr(resp, "tool_calls", None) or []:
        cap = capability_for_tool(tc.get("name", ""))
        if cap and cap in available:
            picked.append((cap, tc.get("args") or {}))

    if not picked:
        return {"commands": [], "reply": (resp.content or "").strip()}

    commands = await _picked_to_commands(project, picked)
    nodes_hit = sorted({c["node"] for c in commands})
    reply = (resp.content or "").strip() or _DEVICE_ACK.format(
        nodes="、".join(nodes_hit) or "裝置", n=len(commands)
    )
    return {"commands": commands, "reply": reply}


def _expand(capability: str, args: dict, node: dict) -> list[dict]:
    """capability + LLM args + node → 一或多個 command。"""
    node_id = node["node_id"]
    if capability == "camera.capture":
        node_lenses = _json_obj(node.get("metadata")).get("lenses") or ["front"]
        want = args.get("lens", "both")
        if want == "both":
            lenses = node_lenses
        elif want in node_lenses:
            lenses = [want]
        else:
            lenses = node_lenses[:1]   # node 沒這顆鏡頭，退而求其次
        return [
            {"capability": capability, "node": node_id, "params": {"lens": ln}}
            for ln in lenses
        ]
    # 其他 capability：直接把 args 當 params
    return [{"capability": capability, "node": node_id, "params": args}]
