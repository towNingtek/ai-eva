"""媒合分析 app（ai-eva EPIC #176 / #184）：A 指定 2–4 個對象做媒合。

流程：

    handle("")               → list_my_projects + get_project_info，列出可管理的專案，請選 A
    ma_pick_a（按鈕）         → 記下 A，列出其他專案讓使用者勾選對象
    ma_toggle（按鈕）         → 勾選／取消對象（最多 4 個）
    ma_run（按鈕）            → 檢查 2–4 個 → run_analysis()

run_analysis()：
1. 每案 philosophy → B1–B8 與方向（app.matching.capability，#182）。
2. A × 每個對象 → 關係與狀態（app.matching.pair，#183）。
3. 組一則回覆（render_reply，純規則、不經 LLM 改寫）：
   - 狀態；互補候選／共同尋找第三方／可聯合或交流三種分開列，每一項附兩邊原文；
   - 【事實】＝計畫書原文、【推論】＝AI 判的類別與方向（及據此照規則算出的狀態）、【建議】＝下一步選項；
   - 「為何列出」只以媒合標準的揭露規則原文與兩邊原文呈現，不顯示任何分數；
   - 第一期聲明：不推薦、不自動聯絡；未評估的四個維度明列（取自 YAML out_of_scope）。
4. 有一組是「先補資料」→ 回覆後緊接著接 Chainlit 轉接層（app.loop.chainlit_adapter，#178）送出一題補問。
   使用者在本工具下直接打字 → handle(payload) 轉給轉接層當草稿；按鈕由下方 action callback 處理。

過渡版 project_match 不動；兩者並存，由站台工具設定（enabled_apps）決定開哪個。

閱讀者語言（EPIC #205 / #227）：render_pair／render_reply／disclaimer／_status_text 與流程訊息、
補問題目都跟 current_lang()（也可傳 lang）。規則 YAML 只有中文一份，顯示用的對照在 app.matching.i18n；
計畫原文照「原文＋翻譯」標記呈現（原文是中文屬正常）。lang＝zh 時輸出與修改前一字不差。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Mapping

import chainlit as cl

from app.loop import Rules
from app.loop.chainlit_adapter import ACTIONS as CLARIFY_ACTIONS
from app.loop.chainlit_adapter import ClarifyLoop
from app.i18n import DEFAULT_LANG
from app.matching import capability, pair
from app.matching import i18n as mi

logger = logging.getLogger(__name__)

MIN_TARGETS, MAX_TARGETS = 2, 4
LIST_LIMIT = 20                     # 一次列出的專案數（按鈕清單，不做分頁）
STATE_KEY = "match_analysis_state"
CLARIFY_KEY = "match_analysis_clarify"
CLARIFY_CTX_KEY = "match_analysis_clarify_ctx"

ACTION_PICK_A = "ma_pick_a"
ACTION_TOGGLE = "ma_toggle"
ACTION_RUN = "ma_run"

FACT, INFER, SUGGEST = "【事實】", "【推論】", "【建議】"
RELATIONS = (pair.REL_COMPLEMENT, pair.REL_THIRD_PARTY, pair.REL_PEER)

_TAG = re.compile(r"<[^>]*>")


class CmsError(RuntimeError):
    """CMS 查詢失敗（含權限不足）；和「專案不足」分開回報。"""


# ── 小工具 ────────────────────────────────────────────────────────────

def plain(value: Any) -> str:
    """去掉 CMS 富文字的 HTML tag（B1–B8 的原文依據要是這段文字的逐字子字串）。"""
    if not value:
        return ""
    text = _TAG.sub("", str(value))
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(a, b)
    return text.strip()


def _data(result: dict):
    inner = result.get("result", {})
    return inner.get("data", inner) if isinstance(inner, dict) else inner


def _std() -> Mapping:
    return pair.load_standard()


def _bname(key: str, lang: Any = DEFAULT_LANG) -> str:
    zh = ((_std().get("capability_registry") or {}).get(key) or {}).get("名稱", key)
    return zh if mi.resolve(lang) == DEFAULT_LANG else mi.capability_name(key, lang, default=zh)


def not_evaluated(lang: Any = DEFAULT_LANG) -> list[str]:
    """第一期未評估的四個維度（YAML out_of_scope.not_used；lang≠zh 時給顯示用譯名）。"""
    return [mi.tr(d, lang) for d in (_std().get("out_of_scope") or {}).get("not_used") or []]


def _bridge_texts(lang: Any = DEFAULT_LANG) -> dict[str, str]:
    """三種關係各自的揭露規則原文（YAML bridge_rules）。"""
    rules = _std().get("bridge_rules") or []
    out = {}
    for r in rules:
        rel = str(r.get("關係", ""))
        text = mi.tr(r.get("原文", ""), lang)
        if rel.startswith("互補"):
            out[pair.REL_COMPLEMENT] = text
        elif "第三方" in rel:
            out[pair.REL_THIRD_PARTY] = text
        elif "聯合" in rel or "交流" in rel:
            out[pair.REL_PEER] = text
    return out


def _status_text(status: str, lang: Any = None) -> str:
    """狀態規則原文（YAML status_rules）；lang 省略 → current_lang()。"""
    body = (_std().get("status_rules") or {}).get(status) or {}
    return mi.tr(body.get("原文", ""), mi.resolve(lang))


# ── CMS ───────────────────────────────────────────────────────────────

async def list_uuids(runtime) -> list[str]:
    result = await runtime.execute("list_my_projects", {})
    if result.get("status") != "ok":
        reason = result.get("reason") or result.get("error") or result.get("status") or "unknown"
        raise CmsError(f"list_my_projects: {reason}")
    data = _data(result)
    uuids = data.get("projects", []) if isinstance(data, dict) else []
    return list(dict.fromkeys(u for u in uuids if isinstance(u, str) and u))


async def fetch_info(runtime, uuid: str) -> dict | None:
    detail = await runtime.execute("get_project_info", {"uuid": uuid})
    if detail.get("status") != "ok":
        logger.warning("match_analysis: get_project_info %s failed: %s",
                       uuid, detail.get("reason") or detail.get("status"))
        return None
    info = _data(detail)
    if not isinstance(info, dict):
        return None
    name = plain(info.get("name"))
    return {**info, "uuid": uuid, "name": name or f"（未命名專案 {uuid}）",
            "philosophy_text": plain(info.get("philosophy"))}


INITIABLE_TOOL = "list_match_initiable_projects"   # CMS #520：本站可發起媒合／寄邀請的專案


def has_manifest(runtime) -> bool:
    """runtime 能不能回答「某工具在不在 manifest」（正式的 ToolRuntime 都可以）。"""
    return callable(getattr(runtime, "is_allowed", None))


async def list_initiable(runtime) -> list[dict] | None:
    """本站可發起媒合的專案 [{uuid, name}]（CMS 排序）；工具不存在（舊版 CMS）回 None。

    讀取失敗（非「工具不存在」）丟 CmsError，和「沒有可發起的案」分開回報。
    """
    if has_manifest(runtime) and not runtime.is_allowed(INITIABLE_TOOL):
        return None
    result = await runtime.execute(INITIABLE_TOOL, {})
    status = result.get("status")
    if status == "denied":
        return None
    if status != "ok":
        reason = result.get("reason") or result.get("error") or status or "unknown"
        raise CmsError(f"{INITIABLE_TOOL}: {reason}")
    data = _data(result)
    items = data.get("items", []) if isinstance(data, dict) else data
    out: dict[str, dict] = {}
    for item in items if isinstance(items, list) else []:
        uuid = item.get("uuid") if isinstance(item, dict) else item
        if isinstance(uuid, str) and uuid and uuid not in out:
            name = plain(item.get("name")) if isinstance(item, dict) else ""
            out[uuid] = {"uuid": uuid, "name": name}
    return list(out.values())


async def load_projects(runtime, limit: int = LIST_LIMIT, first: list[str] | tuple = ()) -> dict[str, dict]:
    """list_my_projects → {uuid: info}。

    first（本站的案）一律排最前面、不受 limit 截斷；其餘照 list_my_projects 順序補到 limit 案。
    """
    first = list(dict.fromkeys(u for u in first if isinstance(u, str) and u))
    rest = [u for u in await list_uuids(runtime) if u not in set(first)]
    wanted = first + rest[:max(0, limit - len(first))]
    projects: dict[str, dict] = {}
    for uuid in wanted:
        try:
            info = await fetch_info(runtime, uuid)
        except Exception:  # noqa: BLE001
            logger.exception("match_analysis: get_project_info %s raised", uuid)
            info = None
        if info is not None:
            projects[uuid] = info
    return projects


# ── 分析（不碰 UI） ──────────────────────────────────────────────────

def _default_llm():
    return capability._default_llm()


def judge_project(project: dict, llm: Any = None) -> dict:
    """單案 philosophy → B1–B8（推論）。"""
    return capability.analyze(project.get("philosophy_text") or plain(project.get("philosophy")), llm=llm)


async def judge_all(projects: list[dict], llm: Any = None) -> dict[str, dict]:
    llm = llm if llm is not None else _default_llm()
    out: dict[str, dict] = {}
    for p in projects:
        if p["uuid"] in out:
            continue
        try:
            out[p["uuid"]] = await asyncio.to_thread(judge_project, p, llm)
        except Exception:  # noqa: BLE001 —— 判斷失敗 = 全部無依據（不臆測），不中斷整批
            logger.exception("match_analysis: B1–B8 判斷失敗 %s", p["uuid"])
            out[p["uuid"]] = capability.judge("", {})
    return out


def analyze(a: dict, targets: list[dict], judged: Mapping[str, dict]) -> list[dict]:
    """A × 每個對象 → [{target, status, status_text, relations, next_question}]。"""
    results = []
    for t in targets:
        names = {a["uuid"]: a["name"], t["uuid"]: t["name"]}
        res = pair.analyze_pair(a["uuid"], judged[a["uuid"]], t["uuid"], judged[t["uuid"]], names=names)
        results.append({"target": t, **res})
    return results


# ── 呈現 ──────────────────────────────────────────────────────────────

def _quotes(result: Mapping, key: str) -> list[str]:
    cap = (result.get("capabilities") or {}).get(key) or {}
    return [e["quote"] for e in cap.get("evidence") or [] if e.get("quote")]


def _direction(result: Mapping, key: str) -> str:
    return ((result.get("capabilities") or {}).get(key) or {}).get("direction", pair.NONE)


def _tags(lang: str) -> tuple[str, str, str]:
    """【事實】【推論】【建議】（依 lang）。"""
    return mi.msg("ma.fact", lang), mi.msg("ma.infer", lang), mi.msg("ma.suggest", lang)


def _side_lines(project: dict, result: Mapping, key: str, lang: Any = DEFAULT_LANG) -> list[str]:
    lang = mi.resolve(lang)
    fact, infer, _ = _tags(lang)
    quotes = _quotes(result, key)
    lines = [mi.msg("ma.side_fact", lang, fact=fact, name=project["name"], quotes=(
        mi.join([mi.quote(q, lang) for q in quotes], lang) if quotes else mi.msg("ma.no_quote", lang)))]
    lines.append(mi.msg("ma.side_infer", lang, infer=infer, name=project["name"], b=_bname(key, lang),
                        dir=_direction(result, key), label=mi.tr(capability.INFERENCE_LABEL, lang)))
    return lines


def _status_label(res: Mapping, lang: str) -> str:
    text = res.get("status_text") or pair.STATUS_TEXT.get(res["status"], "")
    return mi.tr(text, lang) if lang != DEFAULT_LANG else text


def render_pair(a: dict, res: dict, judged: Mapping[str, dict], lang: Any = None) -> str:
    lang = mi.resolve(lang)
    _, infer, suggest = _tags(lang)
    t = res["target"]
    by_id = {a["uuid"]: a, t["uuid"]: t}
    rules = _bridge_texts(lang)
    status = res["status"]
    lines = [
        f"### 🧭 {a['name']} × {t['name']}",
        "",
        mi.msg("ma.status", lang, label=_status_label(res, lang), status=status),
        mi.msg("ma.status_rule", lang, infer=infer, text=_status_text(status, lang)),
        "",
    ]
    rel = res["relations"]
    for name in RELATIONS:
        items = rel.get(name) or []
        lines.append(mi.msg("ma.relation", lang, name=mi.tr(name, lang), n=len(items)))
        if not items:
            lines.append(mi.msg("ma.none", lang))
            lines.append("")
            continue
        lines.append(mi.msg("ma.disclosure", lang, text=rules.get(name, "")))
        for it in items:
            if name == pair.REL_COMPLEMENT:
                need, offer, key = by_id[it["need"]], by_id[it["offer"]], it["key"]
                lines.append(mi.msg("ma.complement_item", lang, key=key, b=_bname(key, lang),
                                    need=need["name"], offer=offer["name"]))
                lines += _side_lines(need, judged[need["uuid"]], key, lang)
                lines += _side_lines(offer, judged[offer["uuid"]], key, lang)
            else:
                key = it
                lines.append(mi.msg("ma.key_item", lang, key=key, b=_bname(key, lang)))
                lines += _side_lines(a, judged[a["uuid"]], key, lang)
                lines += _side_lines(t, judged[t["uuid"]], key, lang)
        lines.append("")

    opts = mi.join([mi.tr(o, lang) for o in (_std().get("output") or {}).get("next_action_options") or []], lang)
    lines.append(mi.msg("ma.next", lang))
    if status == pair.CLARIFY_FIRST:
        lines.append(mi.msg("ma.next_clarify", lang, s=suggest))
    elif status == pair.EXPLORE:
        lines.append(mi.msg("ma.next_explore", lang, s=suggest, opts=opts))
    else:
        lines.append(mi.msg("ma.next_none", lang, s=suggest))
    return "\n".join(lines)


def disclaimer(lang: Any = None) -> str:
    lang = mi.resolve(lang)
    fact, infer, suggest = _tags(lang)
    return mi.msg("ma.disclaimer", lang, dims=mi.join(not_evaluated(lang), lang),
                  fact=fact, infer=infer, suggest=suggest)


def render_reply(a: dict, results: list[dict], judged: Mapping[str, dict], lang: Any = None) -> str:
    lang = mi.resolve(lang)
    parts = [mi.msg("ma.title", lang, a=a["name"], n=len(results))]
    parts += [render_pair(a, r, judged, lang) for r in results]
    parts.append(disclaimer(lang))
    return "\n\n".join(parts)


# ── 補問（Chainlit 轉接層 #178） ─────────────────────────────────────

def clarify_context(a: dict, results: list[dict], lang: Any = None) -> dict | None:
    """第一組「先補資料」的第一條互補候選 → 補問脈絡。"""
    for r in results:
        if r["status"] != pair.CLARIFY_FIRST:
            continue
        comp = r["relations"].get(pair.REL_COMPLEMENT) or []
        if not comp:
            continue
        c = comp[0]
        by_id = {a["uuid"]: a, r["target"]["uuid"]: r["target"]}
        return {"need": c["need"], "offer": c["offer"], "key": c["key"],
                "need_name": by_id[c["need"]]["name"], "offer_name": by_id[c["offer"]]["name"],
                "b_name": _bname(c["key"], mi.resolve(lang))}
    return None


def _questions(std: Mapping, side: str, lang: str) -> Mapping:
    """補問題目：zh 用 YAML 中文；其他語言用 YAML clarify_questions.i18n（人校對版），缺題退回中文。"""
    zh = std["clarify_questions"][side]
    if lang == DEFAULT_LANG:
        return zh
    loc = (((std["clarify_questions"].get("i18n") or {}).get(lang) or {}).get(side)) or {}
    return {f: loc.get(f) or text for f, text in zh.items()}


def rules_for(ctx: Mapping, lang: Any = None) -> Rules:
    """一條互補候選的狀態機規則：題目套上兩案名稱與類別（題目仍取自 YAML，不靠 AI）。

    lang 省略 → current_lang()；題目與類別名依閱讀者語言（欄位名維持中文）。
    """
    lang = mi.resolve(lang)
    base = pair.candidate_rules()
    std = _std()
    b_name = ctx["b_name"]
    if lang != DEFAULT_LANG and ctx.get("key"):
        b_name = _bname(ctx["key"], lang)
    cq = {
        side: {f: str(text).format(need=ctx["need_name"], offer=ctx["offer_name"], b=b_name)
               for f, text in _questions(std, side, lang).items()}
        for side in (pair.NEED, pair.OFFER)
    }
    return Rules({
        "status_transition": {
            "from": base.start, "to": base.target,
            "minimum_fields": dict(std["status_transition"]["minimum_fields"]),
            "unknown_counts_as_filled": False,
        },
        "clarify_questions": cq,
    })


def _clarify_loop() -> ClarifyLoop | None:
    ctx = cl.user_session.get(CLARIFY_CTX_KEY)
    if not ctx:
        return None
    return ClarifyLoop.restore(rules_for(ctx), cl, key=CLARIFY_KEY)


async def start_clarify(ctx: dict) -> ClarifyLoop:
    cl.user_session.set(CLARIFY_CTX_KEY, dict(ctx))
    cl.user_session.set(CLARIFY_KEY, None)    # 新的一輪分析 → 新的補問狀態
    loop = ClarifyLoop(rules_for(ctx), cl, key=CLARIFY_KEY)
    await loop.start()
    return loop


# ── 主流程 ────────────────────────────────────────────────────────────

async def run_analysis(runtime, a: dict, targets: list[dict], llm: Any = None) -> dict:
    """判 B1–B8 → 關係與狀態 → 一則回覆；有「先補資料」就緊接著送出一題補問。"""
    if not (MIN_TARGETS <= len(targets) <= MAX_TARGETS):
        await cl.Message(content=mi.msg("ma.targets_range", lo=MIN_TARGETS, hi=MAX_TARGETS, n=len(targets))).send()
        return {"results": [], "reply": None}
    judged = await judge_all([a, *targets], llm)
    results = analyze(a, targets, judged)
    reply = render_reply(a, results, judged)
    await cl.Message(content=reply).send()
    ctx = clarify_context(a, results)
    if ctx:
        await start_clarify(ctx)
    else:
        cl.user_session.set(CLARIFY_CTX_KEY, None)
    return {"results": results, "reply": reply, "judged": judged, "clarify": ctx}


def _action(name: str, label: str, payload: dict):
    return cl.Action(name=name, label=label, payload=payload)


async def _send(content: str, actions: list | None = None):
    msg = cl.Message(content=content, actions=actions) if actions else cl.Message(content=content)
    return await msg.send()


async def _send_targets(state: dict) -> None:
    a = state["projects"][state["a"]]
    chosen = state["targets"]
    actions = []
    for uuid, p in state["projects"].items():
        if uuid == state["a"]:
            continue
        mark = "☑" if uuid in chosen else "☐"
        actions.append(_action(ACTION_TOGGLE, f"{mark} {p['name']}", {"uuid": uuid}))
    actions.append(_action(ACTION_RUN, mi.msg("ma.run_button", n=len(chosen)), {}))
    names = mi.join([state["projects"][u]["name"] for u in chosen]) or mi.msg("ma.none_selected")
    await _send(mi.msg("ma.pick_targets", a=a["name"], lo=MIN_TARGETS, hi=MAX_TARGETS, names=names), actions)


async def handle(payload: str, msg) -> None:
    text = (payload or "").strip()
    if not text:
        # #203：按租戶開關。sechome 從工具區點進來 → 打開／接回媒合星球任務（同一對話不重跑）；
        # 其他租戶（雲林共用 beta-eva）維持下面原本的聊天流程。
        from . import task as match_task
        if await match_task.open_from_tool():
            return
    if text:
        # #215：工作區卡片「補資料」的回答 → 問要不要寫回自己的計畫理念。
        from . import task as match_task
        if await match_task.on_text(text):
            return
        loop = _clarify_loop()
        if loop is not None and await loop.on_message(text):
            return

    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await _send(mi.msg("ma.reenter"))
        return
    try:
        projects = await load_projects(runtime)
    except Exception as exc:  # noqa: BLE001 —— 不可誤報成專案不足
        logger.exception("match_analysis: 取專案清單失敗")
        await _send(mi.msg("ma.list_failed", exc=exc))
        return
    if len(projects) < 1 + MIN_TARGETS:
        await _send(mi.msg("ma.too_few", lo=MIN_TARGETS, n=len(projects)))
        return
    state = {"projects": projects, "a": None, "targets": []}
    cl.user_session.set(STATE_KEY, state)
    actions = [_action(ACTION_PICK_A, p["name"], {"uuid": u}) for u, p in projects.items()]
    await _send(mi.msg("ma.pick_a"), actions)


def _state() -> dict | None:
    return cl.user_session.get(STATE_KEY)


async def pick_a(payload: Mapping | None) -> None:
    state = _state()
    uuid = (payload or {}).get("uuid")
    if not state or uuid not in state["projects"]:
        await _send(mi.msg("ma.expired"))
        return
    state["a"], state["targets"] = uuid, []
    cl.user_session.set(STATE_KEY, state)
    await _send_targets(state)


async def toggle_target(payload: Mapping | None) -> None:
    state = _state()
    uuid = (payload or {}).get("uuid")
    if not state or not state.get("a") or uuid not in state["projects"] or uuid == state["a"]:
        await _send(mi.msg("ma.expired"))
        return
    chosen = state["targets"]
    if uuid in chosen:
        chosen.remove(uuid)
    elif len(chosen) >= MAX_TARGETS:
        await _send(mi.msg("ma.max_targets", hi=MAX_TARGETS))
        return
    else:
        chosen.append(uuid)
    cl.user_session.set(STATE_KEY, state)
    await _send_targets(state)


async def run_selected(llm: Any = None) -> dict | None:
    state = _state()
    runtime = cl.user_session.get("cms_runtime")
    if not state or not state.get("a") or not runtime:
        await _send(mi.msg("ma.expired"))
        return None
    a = state["projects"][state["a"]]
    targets = [state["projects"][u] for u in state["targets"]]
    return await run_analysis(runtime, a, targets, llm)


@cl.action_callback(ACTION_PICK_A)
async def _on_pick_a(action):
    await pick_a(getattr(action, "payload", None))


@cl.action_callback(ACTION_TOGGLE)
async def _on_toggle(action):
    await toggle_target(getattr(action, "payload", None))


@cl.action_callback(ACTION_RUN)
async def _on_run(action):
    await run_selected()


async def clarify_action(name: str, payload: Mapping | None) -> bool:
    loop = _clarify_loop()
    if loop is None:
        return False
    await loop.on_action(name, payload)
    return True


def _make_clarify_cb(name: str):
    async def _cb(action):
        await clarify_action(name, getattr(action, "payload", None))

    _cb.__name__ = f"_on_{name}"
    return _cb


for _name in CLARIFY_ACTIONS:
    cl.action_callback(_name)(_make_clarify_cb(_name))
