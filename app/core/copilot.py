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


def _inner(raw):
    """剝 CMS 的 {success,data} 信封，回 data dict。"""
    if isinstance(raw, dict):
        return raw.get("data") if isinstance(raw.get("data"), dict) else raw
    return {}


def _fmt_result(name: str, data) -> str:
    """confirmed 執行成功後的回報（建專案 = 名稱+超連結；SDG/SROI 由各自 generator 回報）。"""
    inner = _inner(data) or {}
    if name == "create_project":
        pname = inner.get("name") or "（未命名）"
        url = inner.get("url")
        uuid = inner.get("uuid") or inner.get("uuid_project")
        return f"✅ 專案已建立：[{pname}]({url})" if url else f"✅ 專案已建立：「{pname}」（uuid {uuid}）"
    return f"✅ 完成。\n```\n{json.dumps(data, ensure_ascii=False)[:500]}\n```"


def _parse_json_obj(text: str) -> dict:
    """從 LLM 回應挖出 JSON 物件（可能包 markdown code fence）。"""
    if not text:
        return {}
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {}
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return {}


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


async def execute_confirmed(runtime, name: str, args: dict) -> dict:
    """使用者確認後，以 confirmed=True 真執行 pending 寫類工具。

    回 {"reply": str, "ok": bool, "data": dict}（data = 剝信封後的結果，給 caller 取 uuid 等）。
    """
    result = await runtime.execute(name, args, confirmed=True)
    logger.info("copilot confirmed %s(%s) → %s", name, args, result.get("status"))
    if result.get("status") == "ok":
        raw = result.get("result")
        return {"reply": _fmt_result(name, raw), "ok": True, "data": _inner(raw) or {}}
    return {"reply": f"⚠️ 執行失敗：{result.get('reason', result.get('status'))}", "ok": False, "data": {}}


# ── Phase 1：SDG 產生器（#57）──────────────────────────────────
_SDG_PROMPT = (
    "你是 SDG 顧問。根據專案資訊，從聯合國 17 個 SDG 中挑出 **3~6 個最相關的**，"
    "為每個寫一句『這專案如何推進該 SDG』的繁體中文描述（約 30~60 字）。"
    "只放真的命中的，別硬湊。**只回 JSON 物件** {\"SDG編號(字串1~17)\":\"描述\"}，不要其他文字。"
)


async def generate_and_save_sdg(runtime, project_info: dict, uuid: str, *, api_key=None) -> str:
    """讀專案資訊 → LLM 產 {SDG編號:描述} → save_sdg。自動（save_sdg needs_confirm=false）。"""
    llm = make_llm(api_key=api_key, streaming=False)
    resp = await llm.ainvoke([
        SystemMessage(content=_SDG_PROMPT),
        HumanMessage(content=json.dumps(project_info, ensure_ascii=False)),
    ])
    sdgs = _parse_json_obj(resp.content or "")
    sdgs = {str(k): v for k, v in sdgs.items() if str(k).isdigit() and v}  # 清成 {編號:描述}
    if not sdgs:
        return "（SDG 自動產生失敗，可稍後再說「幫我產 SDG」重試）"
    result = await runtime.execute("save_sdg", {"uuid": uuid, "project_sdgs": sdgs}, confirmed=True)
    if result.get("status") == "ok":
        return "已自動產生並存好 SDG：" + "、".join(f"SDG {k}" for k in sorted(sdgs, key=int))
    return f"（SDG 儲存失敗：{result.get('reason')}）"


# ── Phase 2：SROI 估算器（#57）──────────────────────────────────
_SROI_PROMPT = (
    "你是 SROI 估算顧問。下面有專案資訊與 SROI 指標表（每個指標含『輸入欄標籤』）。"
    "請根據專案資訊，為**能合理對應**的指標估出輸入欄的草稿數字（依標籤由左到右、跳過公式欄）。"
    "只填有把握的指標、其餘留空，數字是粗估草稿。**只回 JSON** "
    "{\"social\":{\"S-1\":[數字,...]},\"economy\":{\"E-1\":[...]},\"environment\":{\"E-1-1\":[...]}}。"
)


def _sroi_indicators(get_sroi_result: dict) -> dict:
    """從 get_sroi 結果抽出 {social:[{id,inputs}], economy:[...], environment:[...]}。"""
    data = _inner(get_sroi_result.get("result") if "result" in get_sroi_result else get_sroi_result)
    out = {}
    for face, key in (("social", "sroi_social"), ("economy", "sroi_economy"), ("environment", "sroi_environment")):
        items = []
        for it in (data.get(key) or []):
            head = (it.get("head") or [""])[0]
            iid = head.split(".")[0].strip() if head else ""
            keys = it.get("key") or []
            # 輸入欄 = 「價值計算」之前的標籤
            inputs = []
            for k in keys:
                if k in ("價值計算", "評估標準"):
                    break
                if k:
                    inputs.append(k)
            if iid:
                items.append({"id": iid, "inputs": inputs})
        out[face] = items
    return out


async def estimate_and_save_sroi(runtime, project_info: dict, uuid: str, *, api_key=None) -> str:
    """get_sroi 拿指標 template → LLM 估草稿值 → save_sroi。草稿，提醒使用者自行核對。"""
    # SROI 走 Google Sheet：新專案第一次取表要初始化試算表，比一般 API 慢很多 → 給足 timeout。
    tmpl = await runtime.execute("get_sroi", {"uuid_project": uuid}, confirmed=False, timeout=120.0)
    if tmpl.get("status") != "ok":
        return f"（拿不到 SROI 指標表：{tmpl.get('reason')}）"
    indicators = _sroi_indicators(tmpl)
    llm = make_llm(api_key=api_key, streaming=False)
    resp = await llm.ainvoke([
        SystemMessage(content=_SROI_PROMPT),
        HumanMessage(content=json.dumps({"project": project_info, "indicators": indicators}, ensure_ascii=False)),
    ])
    vals = _parse_json_obj(resp.content or "")
    payload = {"uuid_project": uuid}
    n = 0
    for face in ("social", "economy", "environment"):
        block = vals.get(face) or {}
        if isinstance(block, dict) and block:
            payload[face] = block
            n += len(block)
    if n == 0:
        return "（這個專案的描述還不足以估出 SROI 指標，補一點社會/經濟/環境影響的細節再試。）"
    result = await runtime.execute("save_sroi", payload, confirmed=True, timeout=120.0)
    if result.get("status") == "ok":
        return (
            f"已產生 SROI 草稿（估了 {n} 個指標）。\n"
            "⚠️ 這是 **AI 初估值**，請進試算表自行核對、修正數字（公式會自動重算）。"
        )
    return f"（SROI 儲存失敗：{result.get('reason')}）"
