"""Tangle lab — 雲林 10 案星圖試作（feat/tangle-lab，不合併）。

只在 TANGLE_LAB=1 時由 app/main.py 載入：
- 取代首頁，提供「法規檢核／媒合分析」兩個入口（v17 同流程）
- 星圖以 CustomElement(TangleOrbit) 放在 Chainlit 右側欄（ElementSidebar）
- 點衛星 → tangle_pick → 對話顯示原文與提問；輸入 → 草稿 → 確認後才記錄
- 補充存在 user_session（伺服器端），收合再開側欄會重送標示

資料：雲林社區 AI 知識系統公開計畫理念固定快照；不連正式系統、不呼叫 AI。
"""
import json
import uuid
from pathlib import Path

import chainlit as cl

_DATA = json.loads((Path(__file__).with_name("tangle_data.json")).read_text(encoding="utf-8"))
PROJECTS = {p["id"]: p for p in _DATA["projects"]}
ORDER = [p["id"] for p in _DATA["projects"]]
THEMES = _DATA["themes"]
NAMES = {"law": "法規檢核", "match": "媒合分析"}
ASSET_V = "lab1"


def _theme(p, code):
    return next((i for i in p["issues"] if i["theme"] == code), None)


def _shared(a, b):
    return sum(1 for i in a["issues"] if _theme(b, i["theme"]))


def _partners(pid):
    a = PROJECTS[pid]
    return sorted((x for x in ORDER if x != pid), key=lambda x: -_shared(a, PROJECTS[x]))


def _quote(p, code):
    i = _theme(p, code)
    if not i:
        return f"**{p['name']}**：原文未提到"
    tail = "" if i["concrete"] else "（原文只寫方向）"
    return f"> 「{i['quote']}」\n> — {p['name']}・公開計畫理念{tail}"


def _sessions():
    s = cl.user_session.get("tangle_sessions")
    if s is None:
        s = {}
        cl.user_session.set("tangle_sessions", s)
    return s


async def start():
    await cl.Message(
        content=("## 把判斷說清楚，讓下一步有依據。\n\n"
                 "雲林 10 個農村再生計畫（公開計畫理念固定快照）。要做哪一種分析？\n\n"
                 "_試作環境：不連線正式系統、不呼叫 AI，說明為示範文字，不作法規適用或合作判定。_"),
        actions=[cl.Action(name="tangle_mode", payload={"mode": "match"}, label="🤝 媒合分析"),
                 cl.Action(name="tangle_mode", payload={"mode": "law"}, label="⚖ 法規檢核")],
    ).send()


def _setup_actions(mode):
    return [cl.Action(name="tangle_project", payload={"mode": mode, "p": pid},
                      label=PROJECTS[pid]["name"]) for pid in ORDER]


@cl.action_callback("tangle_mode")
async def on_mode(action: cl.Action):
    mode = action.payload["mode"]
    await cl.Message(content=f"**{NAMES[mode]}**：請選擇分析專案。",
                     actions=_setup_actions(mode)).send()


@cl.action_callback("tangle_project")
async def on_project(action: cl.Action):
    mode, pid = action.payload["mode"], action.payload["p"]
    if mode == "law":
        return await _open(mode, pid, None)
    acts = [cl.Action(name="tangle_partner", payload={"p": pid, "q": q},
                      label=f"{PROJECTS[q]['name']}（共同議題 {_shared(PROJECTS[pid], PROJECTS[q])}）")
            for q in _partners(pid)]
    await cl.Message(content=f"分析專案：**{PROJECTS[pid]['name']}**\n\n請選擇合作對象（依共同議題多寡排序）。",
                     actions=acts).send()


@cl.action_callback("tangle_partner")
async def on_partner(action: cl.Action):
    await _open("match", action.payload["p"], action.payload["q"])


async def _open(mode, pid, qid):
    sid = uuid.uuid4().hex[:8]
    title = PROJECTS[pid]["name"] + (f" × {PROJECTS[qid]['name']}" if qid else "")
    _sessions()[sid] = {"mode": mode, "p": pid, "q": qid, "title": title, "supp": {}}
    cl.user_session.set("tangle_active", sid)
    cl.user_session.set("tangle_focus", None)
    await _show(sid)
    await cl.Message(
        content=f"已開啟 **{NAMES[mode]}**：{title}\n\n右側是星圖。點一顆衛星，我會在這裡列出原文依據與要先確認的事。",
        actions=[cl.Action(name="tangle_reopen", payload={"sid": sid}, label=f"↗ 重新開啟{NAMES[mode]}工作區")],
    ).send()


def _element(sid):
    s = _sessions()[sid]
    supp = [{"subject": int(k.split(":", 1)[0]), "code": k.split(":", 1)[1], "text": v} for k, v in s["supp"].items()]
    el = cl.CustomElement(name="TangleOrbit", display="side",
                            props={"sid": sid, "mode": s["mode"], "p": s["p"], "q": s["q"] or "",
                                   "v": ASSET_V, "supplements": supp})
    return el


async def _show(sid):
    s = _sessions()[sid]
    el = _element(sid)
    cl.user_session.set("tangle_element", el)
    # Chainlit 2.12: set_elements keeps the previous title, so elements first, then title.
    await cl.ElementSidebar.set_elements([el], key=f"tangle-{sid}-{len(s['supp'])}")
    await cl.ElementSidebar.set_title(f"{NAMES[s['mode']]} / {s['title']}")


@cl.action_callback("tangle_reopen")
async def on_reopen(action: cl.Action):
    sid = action.payload["sid"]
    if sid not in _sessions():
        await cl.Message(content="這份分析已不在本次對話中（重新整理後會清除）。").send()
        return
    cl.user_session.set("tangle_active", sid)
    await _show(sid)


@cl.action_callback("tangle_pick")
async def on_pick(action: cl.Action):
    d = action.payload or {}
    sid = d.get("sid")
    s = _sessions().get(sid)
    if not s or not d.get("code"):
        return
    code, subject = d["code"], int(d.get("subject") or 1)
    T = THEMES.get(code)
    if not T:
        return
    focus = {"sid": sid, "code": code, "subject": subject, "label": T["label"]}
    cl.user_session.set("tangle_active", sid)
    cl.user_session.set("tangle_focus", focus)
    A = PROJECTS[s["p"]]
    B = PROJECTS[s["q"]] if s["q"] else None
    who = B if (subject == 2 and B) else A
    prev = s["supp"].get(f"{subject}:{code}")
    if s["mode"] == "law":
        body = f"{_quote(A, code)}\n\n**可能要留意**\n{T['law']}\n\n**想先確認**\n{T['lawQ']}"
    elif d.get("kind") == "relation" and B:
        body = (f"{_quote(A, code)}\n\n{_quote(B, code)}\n\n**可以從這裡談**\n{T['match']}。\n\n"
                "**還不知道**\n雙方意願與可投入的人力、時間，原文沒有寫。")
    else:
        body = f"{_quote(who, code)}\n\n這項有更具體的人力、時間或資源嗎？知道的話可以補充，「還不知道」也可以。"
    note = f"\n\n本次已確認補充（未查證）：{prev}" if prev else "\n\n_直接在下方輸入你知道的情況；送出後會先讓你確認，不會直接記錄。_"
    await cl.Message(content=f"**{T['label']}**・{who['name']}\n\n{body}{note}").send()


async def handle_message(msg: cl.Message) -> bool:
    """有選取中的衛星時，把輸入變成補充草稿。回傳 True 表示已處理。"""
    focus = cl.user_session.get("tangle_focus")
    text = (msg.content or "").strip()
    if not focus or not text:
        return False
    did = uuid.uuid4().hex[:8]
    drafts = cl.user_session.get("tangle_drafts") or {}
    drafts[did] = {**focus, "text": text}
    cl.user_session.set("tangle_drafts", drafts)
    await cl.Message(
        content=(f"**確認補充到「{focus['label']}」？**\n\n> {text}\n\n"
                 "_僅本次分析・使用者陳述未查證・不改原專案、不改判定。_"),
        actions=[cl.Action(name="tangle_confirm", payload={"d": did, "ok": True}, label="確認納入"),
                 cl.Action(name="tangle_confirm", payload={"d": did, "ok": False}, label="取消")],
    ).send()
    return True


@cl.action_callback("tangle_confirm")
async def on_confirm(action: cl.Action):
    drafts = cl.user_session.get("tangle_drafts") or {}
    d = drafts.pop(action.payload["d"], None)
    cl.user_session.set("tangle_drafts", drafts)
    await action.remove()
    if not d:
        await cl.Message(content="這份草稿已處理過。").send()
        return
    if not action.payload.get("ok"):
        await cl.Message(content="已取消，沒有納入這段補充。").send()
        return
    if d.get("cop"):
        ok = await copilot_confirmed(d)
        await cl.Message(content=(f"已確認補充到「{d['label']}」，" + ("星圖上的衛星已標示「已補充・未查證」。" if ok else "但星圖沒有回應，請重新開啟分析後再看一次。")) +
                         "\n\n_補了資訊，不代表驗證完成、法規符合或合作成立。_").send()
        return
    s = _sessions().get(d["sid"])
    if not s:
        return
    s["supp"][f"{d['subject']}:{d['code']}"] = d["text"]
    await cl.Message(content=f"已確認補充到「{d['label']}」，衛星標示「已補充・未查證」。\n\n_補了資訊，不代表驗證完成、法規符合或合作成立。_").send()
    if cl.user_session.get("tangle_active") == d["sid"]:
        await _show(d["sid"])


# ── Copilot mode：v17 工作區是主畫面，Eva 以 copilot 掛在旁邊 ─────────────
# 頁面 → Eva：sendChainlitMessage(type=system_message, metadata.tangle=...)
# Eva → 頁面：CopilotFunction("tangle_mark") 讓頁面標記衛星
def _copilot_state():
    st = cl.user_session.get("tangle_cop")
    if st is None:
        st = {"supp": {}}
        cl.user_session.set("tangle_cop", st)
    return st


async def copilot_start():
    await cl.Message(content=("我是 **Eva**，這次的副駕。\n\n"
                              "在左邊工作區選好專案、按「確認並開始分析」，星圖會出現。"
                              "**點星圖上的衛星，我會在這裡列出原文與要確認的事；你在這裡補充，確認後我會改星圖上的標示。**\n\n"
                              "_試作：不連線正式系統、不呼叫 AI，說明為示範文字，不作法規適用或合作判定。_")).send()


async def copilot_event(msg: cl.Message) -> bool:
    meta = (msg.metadata or {}).get("tangle")
    if not meta:
        return False
    ev = meta.get("event")
    if ev == "open":
        cl.user_session.set("tangle_focus", None)
        mode, pid, qid = meta.get("mode"), meta.get("p"), meta.get("q")
        if pid not in PROJECTS:
            return True
        title = PROJECTS[pid]["name"] + (f" × {PROJECTS[qid]['name']}" if qid in PROJECTS else "")
        await cl.Message(content=f"已開啟 **{NAMES.get(mode, mode)}**：{title}\n\n點一顆衛星，我們從那裡開始。").send()
        return True
    if ev == "pick":
        await _copilot_pick(meta)
        return True
    return True


async def _copilot_pick(m):
    code, pid, qid = m.get("code"), m.get("p"), m.get("q")
    T = THEMES.get(code)
    if not T or pid not in PROJECTS:
        return
    subject = int(m.get("subject") or 1)
    A = PROJECTS[pid]
    B = PROJECTS.get(qid) if m.get("mode") == "match" else None
    who = B if (subject == 2 and B) else A
    key = f"{m.get('id')}:{subject}:{code}"
    cl.user_session.set("tangle_focus", {"cop": True, "id": m.get("id"), "code": code, "subject": subject, "label": T["label"], "key": key})
    prev = _copilot_state()["supp"].get(key)
    if m.get("mode") == "law":
        body = f"{_quote(A, code)}\n\n**可能要留意**\n{T['law']}\n\n**想先確認**\n{T['lawQ']}"
    elif m.get("kind") == "relation" and B:
        body = (f"{_quote(A, code)}\n\n{_quote(B, code)}\n\n**可以從這裡談**\n{T['match']}。\n\n"
                "**還不知道**\n雙方意願與可投入的人力、時間，原文沒有寫。")
    else:
        body = f"{_quote(who, code)}\n\n這項有更具體的人力、時間或資源嗎？知道的話可以補充，「還不知道」也可以。"
    note = f"\n\n本次已確認補充（未查證）：{prev}" if prev else "\n\n_直接在下方輸入你知道的情況；送出後會先讓你確認。_"
    await cl.Message(content=f"**{T['label']}**・{who['name']}\n\n{body}{note}").send()


async def copilot_confirmed(d) -> bool:
    """草稿確認後：存伺服器端，並請頁面標記星圖。回傳頁面是否成功標記。"""
    _copilot_state()["supp"][d["key"]] = d["text"]
    res = await cl.CopilotFunction(name="tangle_mark", args={
        "id": d["id"], "subject": d["subject"], "code": d["code"], "text": d["text"]}).acall()
    return bool(res and res.get("ok"))
