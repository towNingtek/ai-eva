"""Tangle lab — 雲林 10 案星圖試作（feat/tangle-lab，不合併）。

只在 TANGLE_LAB=1 時由 app/main.py 載入：
- 首頁仍是 Chainlit 預設聊天畫面，只多「媒合分析／法規檢核」兩個按鈕
- 按下後 CopilotFunction("tangle_workspace") 讓頁面在左側打開 v17 工作區、收合 session list；
  這個聊天視窗就是工作區的副駕。工作區右上「收合」恢復原狀
- 工作區事件（開啟分析、點衛星）經 Chainlit window_message → on_window_message
- 輸入 → 草稿 → 確認後才記錄；CopilotFunction("tangle_mark") 標記星圖

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

# 第 2a 步：法領域衛星的回覆。示範資料與星圖共用 public/tangle/kv-law-mock.js（不另存一份）。
_KV_JS = Path(__file__).resolve().parents[2] / "public" / "tangle" / "kv-law-mock.js"


def load_kv_law(path=_KV_JS):
    s = Path(path).read_text(encoding="utf-8")
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


KV_LAW = load_kv_law() if _KV_JS.exists() else {"domains": [], "projects": {}}
DEMO = "_示範資料：狀態與數字是假設值，不是實際判定結果。_"


def reply_for(mode, project_id, key, kv=None):
    """法領域衛星被點時，Eva 要說什麼。純函式，不依賴 Chainlit。

    回傳 {"state", "title", "quotes", "body", "question"}；查不到回 None。
    """
    kv = kv or KV_LAW
    if mode != "law":
        return None
    p = kv["projects"].get(project_id)
    if not p:
        return None
    if key in p.get("uncovered", []):
        return {"state": "uncovered", "title": key, "quotes": [], "clauses": [], "question": None,
                "body": f"「{key}」不在目前的條文庫裡，這一項沒有檢查。**沒檢查不代表合規**，需要另外查相關法規。"}
    v = p["law"].get(key)
    if not v:
        return None
    st, quotes = v["state"], list(v.get("evidence", []))
    if st == "hit":
        c = v["count"]
        parts = ([f"{c['risk']} 條可能的風險"] if c["risk"] else []) + ([f"{c['note']} 條提醒"] if c["note"] else [])
        return {"state": st, "title": key, "quotes": quotes, "question": None, "clauses": list(v.get("clauses", [])),
                "body": f"計畫書裡有內容和「{key}」相關，對上 {'、'.join(parts)}。左邊已展開這幾條條文。"}
    if st == "gap":
        return {"state": st, "title": key, "quotes": quotes, "clauses": [], "question": v["question"],
                "body": f"「{key}」要看一個計畫書沒寫的資訊才能判斷。"}
    return {"state": "na", "title": key, "quotes": [], "clauses": [], "question": None,
            "body": f"計畫書裡沒有和「{key}」相關的內容。"}


def _reply_markdown(r, project_name, prev=None):
    q = "\n\n".join(f"> 「{x}」" for x in r["quotes"])
    src = f"\n> — {project_name}・公開計畫理念" if r["quotes"] else ""
    ask = f"\n\n**想先確認**\n{r['question']}\n\n_直接在下方輸入你知道的情況；送出後會先讓你確認。_" if r["question"] else ""
    if prev:
        ask = f"\n\n本次已補充（未查證、待重判）：{prev}"
    cl_md = ""
    if r.get("clauses"):
        rows = "\n".join(f"- {'⚠ 風險' if c['kind'] == 'risk' else '提醒'}｜{c['law']} {c['no']}：{c['situation']}" for c in r["clauses"])
        cl_md = f"\n\n**條文**（條文是真的；哪幾條對上是示範假設，還沒有實際判斷）\n{rows}"
    return f"**{r['title']}**・{project_name}\n\n{(q + src + chr(10) + chr(10)) if q else ''}{r['body']}{cl_md}{ask}\n\n{DEMO}"


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


def _mode_actions():
    return [cl.Action(name=MODE_ACTION["match"], payload={"mode": "match"}, label="🤝 媒合分析"),
            cl.Action(name=MODE_ACTION["law"], payload={"mode": "law"}, label="⚖ 法規檢核")]


async def resume():
    """回到舊對話（重新整理、點左側紀錄）時，舊訊息上的按鈕已失效 → 補一組可用的入口。

    on_chat_resume 跑完後 Chainlit 才把舊訊息整批送到前端（會蓋掉先送的訊息），
    所以稍等再送，讓它排在還原內容之後。
    """
    import asyncio

    async def later():
        await asyncio.sleep(1.2)
        await cl.Message(content="要繼續分析嗎？", actions=_mode_actions()).send()

    asyncio.create_task(later())


async def start():
    await cl.Message(
        content=("## 把判斷說清楚，讓下一步有依據。\n\n"
                 "雲林 10 個農村再生計畫（公開計畫理念固定快照）。要做哪一種分析？\n\n"
                 "_試作環境：不連線正式系統、不呼叫 AI，說明為示範文字，不作法規適用或合作判定。_"),
        actions=_mode_actions(),
    ).send()


# Chainlit 用第一個 action 的名稱當對話標題（左側 session list），所以取可讀的名字。
MODE_ACTION = {"match": "雲林 10 案・媒合分析", "law": "雲林 10 案・法規檢核"}


async def on_mode(action: cl.Action):
    """選了法規／媒合 → 左邊打開 v17 工作區，這個聊天視窗變成它的副駕。"""
    mode = action.payload["mode"]
    cl.user_session.set("tangle_focus", None)
    res = await cl.CopilotFunction(name="tangle_workspace", args={"mode": mode, "v": ASSET_V}).acall()
    if not (res and res.get("ok")):
        await cl.Message(content="工作區沒有打開，請重新整理後再試一次。").send()
        return
    await cl.Message(content=(f"已打開 **{NAMES[mode]}** 工作區。在左邊選專案、按「確認並開始分析」。\n\n"
                              "之後**點星圖上的衛星，我會在這裡回應；你在這裡補充，確認後我會改星圖**。"
                              "做完按工作區右上角「收合」，就回到原本的畫面。")).send()


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
    ok = await copilot_confirmed(d)
    mark = "已補充・待重判" if d.get("kv") else "已補充・未查證"
    tail = "示範版不會重新判斷。" if d.get("kv") else ""
    await cl.Message(content=(f"已記下「{d['label']}」的補充，" + (f"星圖上這一項標成「{mark}」。{tail}" if ok else "但工作區沒有回應（可能已收合），補充已記在本次對話。")) +
                     "\n\n_補了資訊，不代表驗證完成、法規符合或合作成立。_").send()


# ── Copilot mode：v17 工作區是主畫面，Eva 以 copilot 掛在旁邊 ─────────────
# 頁面 → Eva：sendChainlitMessage(type=system_message, metadata.tangle=...)
# Eva → 頁面：CopilotFunction("tangle_mark") 讓頁面標記衛星
def _copilot_state():
    st = cl.user_session.get("tangle_cop")
    if st is None:
        st = {"supp": {}}
        cl.user_session.set("tangle_cop", st)
    return st


@cl.on_window_message
async def on_window_message(data):
    meta = (data or {}).get("tangle") if isinstance(data, dict) else None
    if meta:
        await _dispatch(meta)


async def copilot_event(msg: cl.Message) -> bool:
    meta = (msg.metadata or {}).get("tangle")
    if not meta:
        return False
    await _dispatch(meta)
    return True


async def _dispatch(meta) -> bool:
    ev = meta.get("event")
    if ev == "open":
        cl.user_session.set("tangle_focus", None)
        mode, pid, qid = meta.get("mode"), meta.get("p"), meta.get("q")
        if pid not in PROJECTS:
            return True
        title = PROJECTS[pid]["name"] + (f" × {PROJECTS[qid]['name']}" if qid in PROJECTS else "")
        await cl.Message(content=f"已開啟 **{NAMES.get(mode, mode)}**：{title}\n\n點星圖上的一顆衛星，我們從那裡開始。").send()
        return True
    if ev == "pick":
        await _copilot_pick(meta)
        return True
    return True


async def _copilot_pick(m):
    code, pid, qid = m.get("code"), m.get("p"), m.get("q")
    if m.get("mode") == "law" and m.get("kind") == "domain":
        await _law_domain_pick(m)
        return
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


async def _law_domain_pick(m):
    pid, key = m.get("p"), m.get("code")
    r = reply_for("law", pid, key)
    if not r or pid not in PROJECTS:
        return
    fkey = f"{m.get('id')}:1:{key}"
    # 只有缺資料可以補充；其他狀態點了不進入補充模式
    cl.user_session.set("tangle_focus", {"cop": True, "id": m.get("id"), "code": key, "subject": 1, "label": key, "key": fkey,
                                         "kv": True} if r["state"] == "gap" else None)
    prev = _copilot_state()["supp"].get(fkey)
    await cl.Message(content=_reply_markdown(r, PROJECTS[pid]["name"], prev)).send()


async def copilot_confirmed(d) -> bool:
    """草稿確認後：存伺服器端，並請頁面標記星圖。回傳頁面是否成功標記。"""
    _copilot_state()["supp"][d["key"]] = d["text"]
    res = await cl.CopilotFunction(name="tangle_mark", args={
        "id": d["id"], "subject": d["subject"], "code": d["code"], "text": d["text"], "kv": bool(d.get("kv"))}).acall()
    return bool(res and res.get("ok"))


for _name in MODE_ACTION.values():
    cl.action_callback(_name)(on_mode)
