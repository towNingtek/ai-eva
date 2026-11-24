"""媒合產生的內容依閱讀者語言輸出（EPIC #205 / #227）。

en／ja／ko 各跑一次：
  (a) 建議卡欄位與「為何推薦」去掉原文引用段後沒有漢字（ja 改看假名比例）；
  (b) 給 LLM 的 prompt 要求閱讀者語言，且不含「請用白話中文」；
  (c) render_reply／disclaimer／_status_text 沒有漢字（ja 看假名比例）；
  (d) B1–B8 類別名四語齊全；
  (e) 寫回補充內容與紀錄內容維持中文；
  (f) zh 輸出與修改前一字不差（快照雜湊）。
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path

import pytest

from app.apps.match_analysis import handler as ma
from app.matching import capability, cards as cd, engine as eng, flow
from app.matching import i18n as mi
from app.matching import writeback as wb

ROOT = Path(__file__).resolve().parents[1]
FOREIGN = ("en", "ja", "ko")
HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
KANA = re.compile(r"[぀-ヿ]")
STATUSES = ("CLARIFY_FIRST", "EXPLORE", "ELIGIBLE", "EXCLUDED", "RECOMMEND")


def ev(q, k):
    return {"quote": q, "kind": k}


def proj(pid, name, text, caps):
    return {"id": pid, "name": name, "site": "yunlin", "public": True, "philosophy": text,
            "capabilities": {"capabilities": caps}}


A = proj("A", "Sunrise Barn", "我們有閒置穀倉可借用。希望找人協助行銷通路。也想有人幫忙設計品牌。", {
    "B1": {"direction": "OFFER", "evidence": [ev("閒置穀倉可借用", "concrete")]},
    "B7": {"direction": "NEED", "evidence": [ev("希望找人協助行銷通路", "aim")]},
    "B4": {"direction": "NEED", "evidence": [ev("想有人幫忙設計品牌", "aim")]}})
T1 = proj("bi", "Market Hub", "我們經營農產電商平台，已有三千名會員。正在尋找可以辦市集的場地。", {
    "B7": {"direction": "OFFER", "evidence": [ev("我們經營農產電商平台", "concrete")]},
    "B1": {"direction": "NEED", "evidence": [ev("正在尋找可以辦市集的場地", "aim")]}})
T2 = proj("one", "Craft Lab", "我們已在全聯上架雜糧禮盒。團隊有專職設計師做包裝。想找人帶小學生體驗課。", {
    "B7": {"direction": "OFFER", "evidence": [ev("已在全聯上架雜糧禮盒", "concrete"), ev("憑空捏造", "concrete")]},
    "B4": {"direction": "OFFER", "evidence": [ev("團隊有專職設計師做包裝", "concrete")]},
    "B3": {"direction": "NEED", "evidence": [ev("想找人帶小學生體驗課", "aim")]}})
T3 = proj("none", "Hall Club", "社區活動中心可以出借。缺研究人員協助調查。", {
    "B1": {"direction": "OFFER", "evidence": [ev("社區活動中心可以出借", "concrete")]},
    "B5": {"direction": "NEED", "evidence": [ev("缺研究人員協助調查", "aim")]}})
ALL = [A, T1, T2, T3]

# 修改前（#227 之前）zh 快照的 sha256：建議卡、render、render_reply、disclaimer、_status_text。
ZH_GOLDEN = "aaa34751834c7c8459cf5c76248ec99094e3dfde72e55859e1f505fd91a8050d"

LLM_REPLY = {
    "zh": {"互補性": "對方在 B7 上能補足。", "互惠價值": "", "建議合作": "先辦市集。",
           "待確認": "時間？", "風險": "不足"},
    "en": {"互補性": "They can fill the gap in B7.", "互惠價值": "Both sides gain new visitors.",
           "建議合作": "Start with a small market.", "待確認": "Which month works for both?",
           "風險": "Insufficient"},
    "ja": {"互補性": "あいてが B7 をおぎなえます。", "互惠價值": "", "建議合作": "まずは小さなマルシェをひらきます。",
           "待確認": "いつごろがよいですか？", "風險": "根拠が足りません"},
    "ko": {"互補性": "상대가 B7을 보완할 수 있습니다.", "互惠價值": "서로 방문객이 늘어납니다.",
           "建議合作": "작은 장터부터 시작해 봅니다.", "待確認": "어느 달이 좋을까요?", "風險": "근거 부족"},
}
DIRECTIVE = {"English": "en", "Japanese": "ja", "Korean": "ko"}


class FakeLLM:
    """依 system prompt 的輸出語言指示回對應語言的 JSON；記下收到的 messages。"""

    def __init__(self):
        self.seen = []

    def __call__(self, messages):
        self.seen.append(messages)
        system = messages[0]["content"]
        m = re.search(r"Write your entire reply in (\w+)", system)
        lang = DIRECTIVE.get(m.group(1), "zh") if m else "zh"
        return json.dumps(LLM_REPLY[lang], ensure_ascii=False)


def zh_llm(messages):
    return json.dumps(LLM_REPLY["zh"], ensure_ascii=False)


@pytest.fixture
def reader(monkeypatch):
    """把閱讀者語言（current_lang）設成指定值。"""
    def set_lang(lang):
        monkeypatch.setattr(mi, "current_lang", lambda: lang)
        return lang
    return set_lang


def to_ma(p):
    return {"uuid": p["id"], "name": p["name"], "philosophy_text": p["philosophy"]}


def judged_all():
    return {p["id"]: capability.judge(p["philosophy"], {k: v["evidence"]
                                                         for k, v in p["capabilities"]["capabilities"].items()})
            for p in ALL}


def handler_inputs():
    judged = judged_all()
    a = to_ma(A)
    results = ma.analyze(a, [to_ma(t) for t in (T1, T2, T3)], judged)
    return a, results, judged


def assert_reader_text(text, lang, where):
    """去掉原文引用段後：en/ko 不得有漢字；ja 假名要佔日文字元的多數。"""
    body = mi.strip_quotes(text)
    assert "<!--" not in body, f"{where}: 未成對的原文標記"
    if lang == "ja":
        kana, han = len(KANA.findall(body)), len(HAN.findall(body))
        assert kana > 0 and kana / (kana + han) >= 0.6, f"{where}: 假名比例過低 kana={kana} han={han}\n{body}"
    else:
        assert not HAN.search(body), f"{where}: 有漢字 {sorted(set(HAN.findall(body)))}\n{body}"


# ── (a) 建議卡 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", FOREIGN)
def test_card_fields_in_reader_language(reader, lang):
    reader(lang)
    llm = FakeLLM()
    res = eng.match(A, [T1, T2, T3])
    built = cd.build_cards(res, ALL, llm=llm, top_n=2)
    assert built and any(c["llm"] for c in built) and any(not c["llm"] for c in built)
    for c in built:
        assert set(c["fields"]) == set(cd.FIELDS)  # 鍵名維持中文（面板依鍵取值）
        assert c["lang"] == lang
        for f, v in c["fields"].items():
            assert v, f
            assert_reader_text(v, lang, f"{lang} {c['name']} {f}")
        assert_reader_text(c["fields"][cd.F_WHY], lang, f"{lang} 為何推薦")
        for k, v in c["未評估"].items():
            assert_reader_text(f"{k} {v}", lang, f"{lang} 未評估")
        draft = c["合作起步草案"]
        assert_reader_text(" ".join([draft["說明"], *[s["name"] for s in draft["選項"]]]), lang, "合作起步草案")
        assert_reader_text(cd.render(c), lang, f"{lang} render")
        assert not cd.has_b_code(cd.render(c))
    # 計畫原文以原文標記呈現（原文是中文屬正常）
    why = built[0]["fields"][cd.F_WHY]
    assert mi.quote("x", lang).split("「")[0] in why
    # LLM 照 prompt 指定的「依據不足」寫法回 → 判為不足（與程式組的不足同字）
    assert LLM_REPLY[lang]["風險"] == mi.msg("insufficient", lang)
    assert built[0]["fields"][cd.F_RISK] == mi.msg("insufficient", lang)
    # LLM 沒寫的欄位 → 該語言的「不足」，不會冒出中文「不足」
    if not LLM_REPLY[lang]["互惠價值"]:
        assert built[0]["fields"][cd.F_RECIPROCITY] == mi.msg("insufficient", lang)


@pytest.mark.parametrize("lang", FOREIGN)
def test_public_cards_carry_lang_and_action_labels(reader, lang):
    reader(lang)
    built = cd.build_cards(eng.match(A, [T1, T2, T3]), ALL, llm=FakeLLM(), top_n=1)
    pub = flow.public_cards(built)
    for c in pub:
        assert c["lang"] == lang and set(c["action_labels"]) == set(flow.ACTION_LABEL)
        for label in c["action_labels"].values():
            assert_reader_text(label, lang, "action label")
        assert "record_fields" not in c and "推薦依據" not in c


# ── (b) LLM prompt ──────────────────────────────────────────────────

def test_cards_prompt_has_no_plain_chinese_rule():
    text = (ROOT / "app/matching/prompts/cards.md").read_text(encoding="utf-8")
    assert "請用白話中文" not in text
    assert "閱讀者的語言" in text


@pytest.mark.parametrize("lang", FOREIGN)
def test_llm_prompt_asks_reader_language(reader, lang):
    reader(lang)
    llm = FakeLLM()
    cd.build_cards(eng.match(A, [T1, T2, T3]), ALL, llm=llm, top_n=2)
    assert len(llm.seen) == 2
    name = {v: k for k, v in DIRECTIVE.items()}[lang]
    for messages in llm.seen:
        whole = "\n".join(m["content"] for m in messages)
        assert "請用白話中文" not in whole
        assert f"Write your entire reply in {name}" in messages[0]["content"]
        assert mi.msg("insufficient", lang) in messages[0]["content"]


def test_zh_prompt_has_no_language_directive(reader):
    reader("zh")
    llm = FakeLLM()
    cd.build_cards(eng.match(A, [T1, T2, T3]), ALL, llm=llm, top_n=1)
    assert "[output-language]" not in llm.seen[0][0]["content"]
    assert "請用白話中文" not in llm.seen[0][0]["content"]


# ── (c) 媒合分析回覆 ────────────────────────────────────────────────

@pytest.mark.parametrize("lang", FOREIGN)
def test_handler_reply_in_reader_language(reader, lang):
    reader(lang)
    a, results, judged = handler_inputs()
    reply = ma.render_reply(a, results, judged)
    assert_reader_text(reply, lang, f"{lang} render_reply")
    assert_reader_text(ma.disclaimer(), lang, f"{lang} disclaimer")
    for s in STATUSES:
        text = ma._status_text(s)
        assert text, s
        assert_reader_text(text, lang, f"{lang} _status_text {s}")
    # 原文以「原文＋翻譯」標記呈現，原文本身不改
    assert "正在尋找可以辦市集的場地" in reply and mi.strip_quotes(reply) != reply
    # 明傳 lang 與 current_lang 相同結果
    assert ma.render_reply(a, results, judged, lang) == reply


@pytest.mark.parametrize("lang", FOREIGN)
def test_clarify_questions_in_reader_language(reader, lang):
    reader(lang)
    a, results, _ = handler_inputs()
    ctx = ma.clarify_context(a, results)
    assert ctx is not None
    assert_reader_text(ctx["b_name"], lang, f"{lang} clarify b_name")
    rules = ma.rules_for(ctx)
    texts = [q.text for q in rules.questions if q.text]
    assert len(texts) >= 2
    for q in texts:
        assert_reader_text(q, lang, f"{lang} clarify question")
    # 欄位名（紀錄用）維持中文、與 zh 版相同
    assert [q.field for q in rules.questions] == [q.field for q in ma.rules_for(ctx, "zh").questions]


@pytest.mark.parametrize("lang", FOREIGN)
def test_flow_messages_in_reader_language(lang):
    keys = [k for k in mi.MSG if k.startswith("ma.") or k.startswith("action.") or k == "writeback.ask"]
    kw = dict(lo=2, hi=5, n=3, a="Sunrise Barn", names="Market Hub", exc="boom", fact="", infer="",
              suggest="", s="", label="x", status="X", text="x", name="x", key="B1", b="x", need="x",
              offer="x", quotes="x", dir="NEED", opts="x", dims="x")
    texts = [mi.msg(k, lang, **kw) for k in keys]
    if lang == "ja":  # 短句（如【事実】）單看比例沒意義：合起來看
        assert_reader_text("\n".join(texts), lang, "ja flow messages")
    else:
        for k, text in zip(keys, texts):
            assert_reader_text(text, lang, f"{lang} {k}")


# ── (d) 類別名四語 ──────────────────────────────────────────────────

def test_capability_names_four_languages():
    keys = [f"B{i}" for i in range(1, 9)]
    for lang in ("zh", *FOREIGN):
        names = mi.capability_names(lang)
        assert set(names) == set(keys), lang
        for k in keys:
            assert names[k].strip(), (lang, k)
            if lang in ("en", "ko"):
                assert not HAN.search(names[k]), (lang, k, names[k])
        assert len(set(names.values())) == 8, lang
    # zh 名稱與 YAML 相同（YAML 不改）
    reg = (ma._std().get("capability_registry") or {})
    for k in keys:
        assert mi.capability_name(k, "zh") == reg[k]["名稱"]


# ── (e) 寫回內容與紀錄維持中文 ───────────────────────────────────────

class Runtime:
    def __init__(self):
        self.calls = []

    async def execute(self, name, args, confirmed=False):
        self.calls.append((name, dict(args)))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": ["A"]}}}
        if name == "append_philosophy":
            return {"status": "ok", "result": {"data": {"ok": True}}}
        return {"status": "error", "reason": name}


class Conn:
    def __init__(self):
        self.args = []

    async def fetchrow(self, sql, *args):
        self.args.append((sql, args))
        return {"id": len(self.args)}

    async def execute(self, *a, **k):
        return "OK"

    async def fetch(self, *a, **k):
        return []

    async def close(self):
        pass

    def strings(self):
        out = []
        for _, args in self.args:
            for v in args:
                if isinstance(v, str):
                    out.append(v)
        return out


@pytest.mark.parametrize("lang", FOREIGN)
def test_writeback_and_records_stay_chinese(reader, monkeypatch, lang):
    reader(lang)
    built = cd.build_cards(eng.match(A, [T1, T2, T3]), ALL, llm=FakeLLM(), top_n=1)
    pub = flow.public_cards(built)
    shown_q = pub[0]["fields"][cd.F_CONFIRM]
    assert_reader_text(shown_q, lang, "shown question")

    conn = Conn()

    async def connect():
        return conn

    monkeypatch.setattr(flow, "connect", connect)
    runtime = Runtime()
    asked = []
    yes = {"en": "yes", "ja": "はい", "ko": "네"}[lang]

    async def go():
        out = await flow.writeback_with_record(runtime, 1, uuid="A", question=shown_q,
                                               answer="We plan to hold it in October.",
                                               ask=lambda p: asked.append(p) or yes)
        run_id = await flow.record_run(eng.match(A, [T1, T2, T3]), built, tenant="t", initiator="u")
        return out, run_id

    out, run_id = asyncio.run(go())
    assert out["result"] == "ok"
    # 詢問句依閱讀者語言
    assert asked == [mi.msg("writeback.ask", lang)]
    assert_reader_text(asked[0], lang, "writeback ask")
    # 寫回 CMS 的補充內容：回答原樣＋中文來源標註
    appends = [c for c in runtime.calls if c[0] == "append_philosophy"]
    assert len(appends) == 1
    text = appends[0][1]["supplement"]
    assert "We plan to hold it in October." in text and "補充，經 AI-Eva 媒合補問" in text
    # 紀錄：補問題目換回中文版
    strings = conn.strings()
    zh_q = built[0]["record_fields"][cd.F_CONFIRM]
    assert HAN.search(zh_q) and zh_q in strings and shown_q not in strings
    # 紀錄：建議卡欄位是中文版
    payloads = [json.loads(s) for s in strings if s.startswith("{") and '"cards"' in s]
    assert payloads and run_id
    for card in payloads[-1]["cards"]:
        for f in cd.FIELDS:
            assert HAN.search(card["fields"][f]), (f, card["fields"][f])


@pytest.mark.parametrize("reply,ok", [("いいえ", False), ("아니요", False), ("no", False), ("ok", True)])
def test_foreign_consent_declines(reader, monkeypatch, reply, ok):
    reader("ja" if reply in ("いいえ",) else "ko" if reply == "아니요" else "en")
    runtime = Runtime()

    async def go():
        return await flow.clarify_writeback(runtime, uuid="A", question="q", answer="a",
                                            ask=lambda p: reply)

    out = asyncio.run(go())
    assert (out["result"] == "ok") is ok


def test_zh_writeback_prompt_unchanged(reader):
    reader("zh")
    asked = []

    async def go():
        return await flow.clarify_writeback(Runtime(), uuid="A", question="q", answer="a",
                                            ask=lambda p: asked.append(p) or "好")

    assert asyncio.run(go())["result"] == "ok"
    assert asked == [wb.ASK_PROMPT]


# ── (f) zh 與修改前一字不差 ─────────────────────────────────────────

def zh_snapshot(**kw):
    res = eng.match(A, [T1, T2, T3])
    built = cd.build_cards(res, ALL, llm=zh_llm, top_n=2, **kw)
    a, results, judged = handler_inputs()
    return {"cards": built, "render": [cd.render(c) for c in built],
            "reply": ma.render_reply(a, results, judged), "disclaimer": ma.disclaimer(),
            "status": {s: ma._status_text(s) for s in STATUSES}}


def test_zh_output_identical_to_before(reader):
    reader("zh")
    snap = zh_snapshot()
    s = json.dumps(snap, ensure_ascii=False, sort_keys=True, default=str)
    assert hashlib.sha256(s.encode()).hexdigest() == ZH_GOLDEN
    for c in snap["cards"]:
        assert "lang" not in c and "record_fields" not in c
    # 明傳 lang="zh" 與預設相同
    assert zh_snapshot(lang="zh")["cards"] == snap["cards"]
    assert flow.public_cards(snap["cards"])[0].keys() == {"rank", "target", "name", "fields", "未評估",
                                                         "原文段落", "合作起步草案"}
