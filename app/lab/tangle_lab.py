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

# 第 3a 步：媒合衛星是 B1–B8，示範資料與星圖共用 public/tangle/kv-match-mock.js。
_KVM_JS = Path(__file__).resolve().parents[2] / "public" / "tangle" / "kv-match-mock.js"


def load_kv_match(path=_KVM_JS):
    s = Path(path).read_text(encoding="utf-8")
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


KV_MATCH = load_kv_match() if _KVM_JS.exists() else {"keys": {}, "projects": {}}
MATCH_DEMO = "_示範資料：需要／能提供是依計畫理念寫得具體或只寫方向推估的假設，不是媒合判定。_"

# Step C：媒合標準 v1.1（HackMD BkKiUSPRMl → app/matching/standard_yunlin_v1.yaml）。規則照 YAML，不靠 AI。
_STD_YAML = Path(__file__).resolve().parents[1] / "matching" / "standard_yunlin_v1.yaml"


def load_match_standard(path=_STD_YAML):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


MATCH_STD = load_match_standard() if _STD_YAML.exists() else {}
STATUS_TEXT = {"EXPLORE": "可探索", "CLARIFY_FIRST": "先補資料", "ELIGIBLE": "可排序・未建議", "EXCLUDED": "不在範圍"}
SEM = {"FACT": "**事實**", "INFERENCE": "**推論（AI，未經 Owner 確認）**", "SUGGESTION": "**建議**"}


def _is_need(r):
    return r in ("need", "both")


def _is_offer(r):
    return r in ("offer", "both")


def complement_pairs(a_id, b_id, kvm=None):
    """互補候選：(need_pid, offer_pid, key)，BOTH 兩邊都算（標準 v1.1 bridge_rules）。"""
    kvm = kvm or KV_MATCH
    A, B = kvm["projects"][a_id]["match"], kvm["projects"][b_id]["match"]
    out = []
    for k in kvm["keys"]:
        if _is_need(A[k]["role"]) and _is_offer(B[k]["role"]):
            out.append((a_id, b_id, k))
        if _is_need(B[k]["role"]) and _is_offer(A[k]["role"]):
            out.append((b_id, a_id, k))
    return out


def match_status_for(a_id, b_id, filled=None, kvm=None, std=None):
    """一組計畫的狀態（SH-COLLAB-03 §5；標準 v1.1 status_rules＋status_transition）。只用規則。RECOMMEND 第一期不開放。"""
    kvm, std, filled = kvm or KV_MATCH, std or MATCH_STD, filled or {}
    mf = std["status_transition"]["minimum_fields"]
    comp = complement_pairs(a_id, b_id, kvm)
    if comp:
        done = any(filled.get(f"{n}:{k}:{mf['NEED']}") and filled.get(f"{o}:{k}:{mf['OFFER']}") for n, o, k in comp)
        return "EXPLORE" if done else "CLARIFY_FIRST"
    A, B = kvm["projects"][a_id]["match"], kvm["projects"][b_id]["match"]
    if any(A[k]["role"] == "offer" and B[k]["role"] == "offer" for k in kvm["keys"]):
        return "EXPLORE"
    return "ELIGIBLE"


def next_question_for(a_id, b_id, answered=None, kvm=None, std=None, key=None):
    """下一題主動補問（標準 v1.1 clarify_questions）：先問 minimum_fields，再問其他；一次一題。沒有就回 None。
    answered：已答或跳過的 "pid:key:field"。key：只問這一類（走進一對時）。"""
    kvm, std, answered = kvm or KV_MATCH, std or MATCH_STD, answered or set()
    cq, mf = std["clarify_questions"], std["status_transition"]["minimum_fields"]
    comp = [c for c in complement_pairs(a_id, b_id, kvm) if key is None or c[2] == key]
    names = {pid: kvm["projects"][pid]["name"] for pid in (a_id, b_id)}
    order = []
    for n, o, k in comp:   # minimum fields first, across all candidates
        order += [(n, k, "NEED", mf["NEED"], o), (o, k, "OFFER", mf["OFFER"], n)]
    for n, o, k in comp:
        order += [(n, k, "NEED", f, o) for f in cq["NEED"] if f != mf["NEED"]]
        order += [(o, k, "OFFER", f, n) for f in cq["OFFER"] if f != mf["OFFER"]]
    for pid, k, side, field, other in order:
        qid = f"{pid}:{k}:{field}"
        if qid in answered:
            continue
        b = kvm["keys"][k]
        text = cq[side][field].format(need=names[pid] if side == "NEED" else names[other], offer=names[pid] if side == "OFFER" else names[other], b=b)
        return {"id": qid, "pid": pid, "key": k, "side": side, "field": field, "text": text,
                "minimum": field == mf[side]}
    return None


def third_reply_for(a_id, b_id, key, kvm=None):
    """兩方都只 NEED 同一類（SH-METHOD-02 §7）：可推薦共同尋找第三方，不得標示為互補完成。"""
    kvm = kvm or KV_MATCH
    A, B = kvm["projects"].get(a_id), kvm["projects"].get(b_id)
    if not A or not B or A["match"][key]["role"] != "need" or B["match"][key]["role"] != "need":
        return None
    name = kvm["keys"][key]
    return {"title": f"{key} {name}", "quotes": {a_id: list(A["match"][key]["evidence"]), b_id: list(B["match"][key]["evidence"])},
            "body": f"兩個計畫在「{name}」都只寫了方向（都是需要），彼此補不上。依 SH-METHOD-02，可以**共同尋找第三方**，但不算互補。"}


def peer_reply_for(a_id, b_id, key, kvm=None):
    """兩邊都能提供同一類（淡線）被點時，Eva 要說什麼。不是互補，只作經驗交流。查不到回 None。"""
    kvm = kvm or KV_MATCH
    A, B = kvm["projects"].get(a_id), kvm["projects"].get(b_id)
    if not A or not B or key not in A["match"] or A["match"][key]["role"] != "offer" or B["match"][key]["role"] != "offer":
        return None
    name = kvm["keys"][key]
    return {"title": f"{key} {name}", "quotes": {a_id: list(A["match"][key]["evidence"]), b_id: list(B["match"][key]["evidence"])},
            "body": f"兩個計畫在「{name}」都寫得具體，都已經在做。依 SH-METHOD-02，適合**聯合市場、交流經驗或共同擴張**，但要另外判斷彼此會不會競爭；兩邊都有，所以不是一方補另一方的缺口。"}


def pair_reply_for(a_id, b_id, key, kvm=None):
    """B1：走進一對「需要 × 能提供」時，列出兩邊原文並說明為什麼互補。不是互補回 None。"""
    kvm = kvm or KV_MATCH
    A, B = kvm["projects"].get(a_id), kvm["projects"].get(b_id)
    if not A or not B or key not in A["match"]:
        return None
    ra, rb = A["match"][key]["role"], B["match"][key]["role"]
    if _is_need(ra) and _is_offer(rb):
        need, offer = a_id, b_id
    elif _is_need(rb) and _is_offer(ra):
        need, offer = b_id, a_id
    else:
        return None
    name = kvm["keys"][key]
    return {"title": f"{key} {name}", "need": need, "offer": offer,
            "quotes": {need: list(kvm["projects"][need]["match"][key]["evidence"]), offer: list(kvm["projects"][offer]["match"][key]["evidence"])},
            "body": f"一方在「{name}」只寫了方向（**需要**），另一方寫得具體（**能提供**），所以是**互補候選**。原文要求有可行合作形式才算成立，計畫書看不出來，所以還不能說成立。"}


def planet_summary_for(project_id, partner_id=None, kvm=None):
    """B2：點行星時，列出這個計畫的 B1–B8 需要／能提供，以及和對方對上幾條、可交流經驗幾條。"""
    kvm = kvm or KV_MATCH
    p = kvm["projects"].get(project_id)
    if not p:
        return None
    m, keys = p["match"], kvm["keys"]
    need = [k for k in keys if _is_need(m[k]["role"])]
    offer = [k for k in keys if _is_offer(m[k]["role"])]
    q = kvm["projects"].get(partner_id, {}).get("match") if partner_id else None
    links = [k for k in keys if q and ((_is_need(m[k]["role"]) and _is_offer(q[k]["role"])) or (_is_offer(m[k]["role"]) and _is_need(q[k]["role"])))]
    peers = [k for k in keys if q and m[k]["role"] == "offer" and q[k]["role"] == "offer"]
    return {"need": need, "offer": offer, "links": links, "peers": peers}


def match_reply_for(project_id, key, partner_id=None, kvm=None):
    """B1–B8 衛星被點時，Eva 要說什麼。純函式，不依賴 Chainlit。查不到回 None。"""
    kvm = kvm or KV_MATCH
    p = kvm["projects"].get(project_id)
    if not p or key not in p["match"]:
        return None
    v, name = p["match"][key], kvm["keys"][key]
    if v["role"] == "none":
        return None
    q = kvm["projects"].get(partner_id, {}).get("match", {}).get(key) if partner_id else None
    qr = q["role"] if q else "none"
    if v["role"] == "both":   # standard v1.1 Q1
        linked = qr != "none"
        other = "和對方在這一類有互補候選，左邊有航跡連過去。" if linked else "選中的合作對象在這一類沒有寫。"
        body = f"這個計畫在「{name}」同時有寫得具體的部分和只寫方向的部分，視為**需要＋能提供**（兩者皆是）。{other}"
    elif v["role"] == "need":
        other = "對方能提供這一類，左邊有航跡連過去。" if _is_offer(qr) else "選中的合作對象沒有能提供這一類的內容（沒有對象）。"
        body = f"這個計畫在「{name}」只寫了方向，視為**需要**。{other}"
    else:
        other = "對方需要這一類，左邊有航跡連過去。" if _is_need(qr) else "選中的合作對象沒有寫需要這一類。"
        body = f"這個計畫在「{name}」寫得具體，視為**能提供**。{other}"
    return {"role": v["role"], "title": f"{key} {name}", "quotes": list(v["evidence"]), "body": body}


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


RESUME_TEXT = "要繼續分析嗎？"


async def resume(thread=None):
    """回到舊對話（重新整理、點左側紀錄）時，舊訊息上的按鈕已失效 → 補一組可用的入口。

    on_chat_resume 跑完後 Chainlit 才把舊訊息整批送到前端（會蓋掉先送的訊息），
    所以稍等再送，讓它排在還原內容之後。

    A（2026-11-15）：先移除這個對話裡所有舊的「要繼續分析嗎？」（按鈕早已失效），再送一則新的，
    所以不管重新整理幾次，對話裡只會有一則可用的入口。舊對話裡已累積的也一併清掉。
    """
    import asyncio

    async def old_prompt_ids():
        t = thread
        if t is None:  # app/main.py calls resume() without the thread; read it from the data layer
            try:
                from chainlit.data import get_data_layer
                dl = get_data_layer()
                t = await dl.get_thread(cl.context.session.thread_id) if dl else None
            except Exception:
                t = None
        return [s["id"] for s in ((t or {}).get("steps") or [])
                if s.get("type") == "assistant_message" and (s.get("output") or "").strip() == RESUME_TEXT]

    async def later():
        await asyncio.sleep(1.2)
        for sid in await old_prompt_ids():
            try:
                await cl.Message(id=sid, content=RESUME_TEXT).remove()
            except Exception:  # 刪不到不影響新入口
                pass
        await cl.Message(content=RESUME_TEXT, actions=_mode_actions()).send()

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


NO_AI_TEXT = ("試作環境沒有接 AI，無法自由問答。請按「媒合分析」或「法規檢核」打開星圖，"
              "點一顆衛星後，就可以在這裡補充。")


async def handle_message(msg: cl.Message) -> bool:
    """有選取中的衛星時，把輸入變成補充草稿；沒有選取時回固定說明（E：不交給沒有金鑰的 AI）。
    試作站所有輸入都在這裡處理完，回傳 True。"""
    focus = cl.user_session.get("tangle_focus")
    text = (msg.content or "").strip()
    if not text:
        return True
    if not focus:
        await cl.Message(content=NO_AI_TEXT, actions=_mode_actions()).send()
        return True
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
    if d.get("mq"):
        mq = d["mq"]
        s_ = _mq_state(mq["p"], mq["q"])
        before = match_status_for(mq["p"], mq["q"], s_["filled"])
        if mq["qid"] not in s_["answered"]:
            s_["answered"].append(mq["qid"])
        s_["filled"][mq["qid"]] = True
        _copilot_state()["supp"][d["key"]] = d["text"]
        after = await _push_status(d, mq["p"], mq["q"])
        moved = f"狀態照規則重算：**{STATUS_TEXT[before]} → {STATUS_TEXT[after]}**。" if after != before else f"狀態照規則重算：仍是 **{STATUS_TEXT[after]}**。"
        await cl.Message(content=f"已記下「{d['label']}」：{d['text']}\n\n_使用者陳述・未查證。_ {moved}\n\n_補了資訊，不代表驗證完成或合作成立。_").send()
        await _ask_next({"p": mq["p"], "q": mq["q"], "id": d.get("id")}, intro=False)
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
        title += "".join(f" × {PROJECTS[e]['name']}" for e in (meta.get("x") or []) if e in PROJECTS)   # step D: 3–4 plans
        await cl.Message(content=f"已開啟 **{NAMES.get(mode, mode)}**：{title}\n\n點星圖上的一顆衛星，我們從那裡開始。").send()
        return True
    if ev == "pick":
        await _copilot_pick(meta)
        return True
    return True


async def _copilot_pick(m):
    if m.get("mode") == "match" and m.get("pa") and m.get("pb"):   # step D: 3–4 plans — this event is about pa × pb
        m = {**m, "p": m["pa"], "q": m["pb"], "subject": 1}
    code, pid, qid = m.get("code"), m.get("p"), m.get("q")
    if m.get("mode") == "law" and m.get("kind") == "domain":
        await _law_domain_pick(m)
        return
    if m.get("mode") == "match" and m.get("kind") == "third" and code in KV_MATCH.get("keys", {}):
        await _match_third_pick(m)
        return
    if m.get("mode") == "match" and m.get("kind") == "status":
        await _match_status_pick(m)
        return
    if m.get("mode") == "match" and m.get("kind") == "planet":
        await _match_planet_pick(m)
        return
    if m.get("mode") == "match" and m.get("kind") in ("relation", "pair") and code in KV_MATCH.get("keys", {}):
        await _match_pair_pick(m)
        return
    if m.get("mode") == "match" and m.get("kind") == "peer" and code in KV_MATCH.get("keys", {}):
        await _match_peer_pick(m)
        return
    if m.get("mode") == "match" and code in KV_MATCH.get("keys", {}):
        await _match_key_pick(m)
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


def _mq_state(pid, qid):
    st = cl.user_session.get("tangle_mq") or {}
    k = f"{pid}|{qid}"
    st.setdefault(k, {"answered": [], "filled": {}})
    cl.user_session.set("tangle_mq", st)
    return st[k]


def _status_line(pid, qid):
    st = match_status_for(pid, qid, _mq_state(pid, qid)["filled"])
    return st, f"**媒合狀態：{STATUS_TEXT[st]}**（依媒合標準 v1.1；不是合作決定）"


async def _ask_next(m, key=None, intro=True):
    """Eva 主動問下一題（一次一題，附「還不知道」「跳過」）。回答走原本的補充流程。"""
    pid, qid = m.get("p"), m.get("q")
    s_ = _mq_state(pid, qid)
    q = next_question_for(pid, qid, set(s_["answered"]), key=key)
    if not q:
        if intro:
            await cl.Message(content="這一組目前沒有要補問的項目。").send()
        return
    label = f"{q['key']} {KV_MATCH['keys'][q['key']]}・{q['field']}"
    cl.user_session.set("tangle_focus", {"cop": True, "id": m.get("id"), "code": q["key"], "subject": 1, "label": label,
                                         "key": f"mq:{pid}|{qid}:{q['id']}", "mq": {"p": pid, "q": qid, "qid": q["id"], "field": q["field"]}})
    tag = "（補齊這項，狀態可以往前一步）" if q["minimum"] else ""
    await cl.Message(content=f"{SEM['SUGGESTION']}・想先確認一件事{tag}\n\n**{q['text']}**\n\n_直接在下方輸入；送出後會先讓你確認。_",
                     actions=[cl.Action(name="tangle_mq", payload={"p": pid, "q": qid, "qid": q["id"], "a": "unknown", "id": m.get("id"), "key": key}, label="還不知道"),
                              cl.Action(name="tangle_mq", payload={"p": pid, "q": qid, "qid": q["id"], "a": "skip", "id": m.get("id"), "key": key}, label="跳過")]).send()


async def _push_status(m_or_d, pid, qid):
    """狀態重算後告訴星圖（經工作區轉給 iframe）。"""
    s_ = _mq_state(pid, qid)
    st = match_status_for(pid, qid, s_["filled"])
    try:
        await cl.CopilotFunction(name="tangle_mark", args={"id": m_or_d.get("id"), "mfStatus": st, "filled": s_["filled"],
                                                          "pair": "|".join(sorted([pid, qid]))}).acall()
    except Exception:
        pass
    return st


@cl.action_callback("tangle_mq")
async def on_mq(action: cl.Action):
    p_ = action.payload
    s_ = _mq_state(p_["p"], p_["q"])
    if p_["qid"] not in s_["answered"]:
        s_["answered"].append(p_["qid"])
    await action.remove()
    cl.user_session.set("tangle_focus", None)
    await cl.Message(content="好，先記成「還不知道」，不算補齊。" if p_["a"] == "unknown" else "好，先跳過。").send()
    await _ask_next({"p": p_["p"], "q": p_["q"], "id": p_.get("id")}, key=p_.get("key"), intro=False)


async def _match_third_pick(m):
    pid, qid = m.get("p"), m.get("q")
    r = third_reply_for(pid, qid, m.get("code"))
    if not r or pid not in PROJECTS or qid not in PROJECTS:
        return
    parts = []
    for x in (pid, qid):
        q = "\n\n".join(f"> 「{t}」" for t in r["quotes"][x])
        parts.append(f"{q}\n> — {PROJECTS[x]['name']}・公開計畫理念")
    await cl.Message(content=f"**{r['title']}**・兩邊都需要\n\n{SEM['FACT']}\n\n" + "\n\n".join(parts) +
                     f"\n\n{SEM['INFERENCE']}　{r['body']}\n\n{SEM['SUGGESTION']}　一起找能提供這一類的第三個計畫或單位。\n\n{MATCH_DEMO}").send()


async def _match_status_pick(m):
    pid, qid = m.get("p"), m.get("q")
    if pid not in PROJECTS or qid not in PROJECTS:
        return
    st, line = _status_line(pid, qid)
    comp = complement_pairs(pid, qid)
    K = KV_MATCH["keys"]
    why = {"CLARIFY_FIRST": f"有 {len(comp)} 條互補候選，但都還缺最低必要資料（需要方的「用途」、能提供方的「可提供形式」）。補齊任一條，就會照規則轉成「可探索」。",
           "EXPLORE": "已有互補候選補齊最低必要資料，或兩邊能提供同一類。建議先低成本交流（介紹、會議、資料交換）。",
           "ELIGIBLE": "沒有互補，也沒有兩邊都能提供的類別；可以排序，但目前不建議。",
           "EXCLUDED": "不在目前範圍。"}[st]
    items = "、".join(sorted({f"{k} {K[k]}" for _, _, k in comp})) or "（無）"
    await cl.Message(content=f"{line}\n\n{SEM['INFERENCE']}　{why}\n\n互補候選：{items}\n\n_第一期不顯示「推薦」：方向還沒經 Owner 確認，也看不出可行合作形式。_\n\n{MATCH_DEMO}").send()
    if st == "CLARIFY_FIRST":
        await _ask_next(m)


async def _match_peer_pick(m):
    pid, qid = m.get("p"), m.get("q")
    r = peer_reply_for(pid, qid, m.get("code"))
    if not r or pid not in PROJECTS or qid not in PROJECTS:
        return
    parts = []
    for x in (pid, qid):
        q = "\n\n".join(f"> 「{t}」" for t in r["quotes"][x])
        parts.append(f"{q}\n> — {PROJECTS[x]['name']}・公開計畫理念")
    await cl.Message(content=f"**{r['title']}**・兩邊都能提供\n\n{SEM['FACT']}\n\n" + "\n\n".join(parts) + f"\n\n{SEM['INFERENCE']}　{r['body']}\n\n{MATCH_DEMO}").send()


async def _match_pair_pick(m):
    pid, qid = m.get("p"), m.get("q")
    r = pair_reply_for(pid, qid, m.get("code"))
    if not r or pid not in PROJECTS or qid not in PROJECTS:
        return
    parts = []
    for x, role in ((r["need"], "需要"), (r["offer"], "能提供")):
        q = "\n\n".join(f"> 「{t}」" for t in r["quotes"][x])
        parts.append(f"**{role}**・{PROJECTS[x]['name']}\n\n{q}\n> — 公開計畫理念")
    st, line = _status_line(pid, qid)
    await cl.Message(content=f"**{r['title']}**・互補候選\n\n{SEM['FACT']}\n\n" + "\n\n".join(parts) + f"\n\n{SEM['INFERENCE']}　{r['body']}\n\n{line}\n\n{MATCH_DEMO}").send()
    await _ask_next(m, key=m.get("code"), intro=False)


async def _match_planet_pick(m):
    if m.get("who") and m.get("others"):   # step D: 3–4 plans — one line per other plan, then its status
        who = m["who"]
        if who not in PROJECTS:
            return
        K = KV_MATCH["keys"]
        fmt = lambda ks: "、".join(f"{k} {K[k]}" for k in ks) or "（無）"
        r0 = planet_summary_for(who, None)
        lines = []
        for o in m["others"]:
            if o not in PROJECTS:
                continue
            r = planet_summary_for(who, o)
            st = match_status_for(who, o, _mq_state(who, o)["filled"])
            lines.append(f"- 和 **{PROJECTS[o]['name']}**：互補候選 {len(r['links'])} 條（{fmt(r['links'])}）；可聯合或交流 {len(r['peers'])} 條・**{STATUS_TEXT[st]}**")
        await cl.Message(content=f"**{PROJECTS[who]['name']}**・B1–B8\n\n{SEM['INFERENCE']}\n\n**需要**：{fmt(r0['need'])}\n\n**能提供**：{fmt(r0['offer'])}\n\n" +
                         "\n".join(lines) + "\n\n_狀態依媒合標準 v1.1；不是合作決定。點兩顆行星之間的狀態，可以看那一組的依據。_\n\n" + MATCH_DEMO).send()
        return
    subject = int(m.get("subject") or 1)
    pid, qid = m.get("p"), m.get("q")
    who, other = (qid, pid) if subject == 2 else (pid, qid)
    r = planet_summary_for(who, other)
    if not r or who not in PROJECTS:
        return
    K = KV_MATCH["keys"]
    fmt = lambda ks: "、".join(f"{k} {K[k]}" for k in ks) or "（無）"
    oname = PROJECTS[other]["name"] if other in PROJECTS else "對方"
    body = (f"**需要**：{fmt(r['need'])}\n\n**能提供**：{fmt(r['offer'])}\n\n"
            f"和 {oname}：**互補候選 {len(r['links'])} 條**（{fmt(r['links'])}）；兩邊都能提供、可聯合或交流 {len(r['peers'])} 條（{fmt(r['peers'])}）。"
            "\n\n點一顆有航跡的衛星，可以走進那一對看兩邊的原文。")
    st, line = _status_line(pid, qid)
    await cl.Message(content=f"**{PROJECTS[who]['name']}**・B1–B8\n\n{SEM['INFERENCE']}\n\n{body}\n\n{line}\n\n{MATCH_DEMO}").send()
    await _ask_next(m, intro=False)


async def _match_key_pick(m):
    subject = int(m.get("subject") or 1)
    pid, qid = m.get("p"), m.get("q")
    who, other = (qid, pid) if subject == 2 else (pid, qid)
    r = match_reply_for(who, m.get("code"), other)
    if not r or who not in PROJECTS:
        return
    name = PROJECTS[who]["name"]
    q = "\n\n".join(f"> 「{x}」" for x in r["quotes"])
    await cl.Message(content=f"**{r['title']}**・{name}\n\n{q}\n> — {name}・公開計畫理念\n\n{r['body']}\n\n{MATCH_DEMO}").send()


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
