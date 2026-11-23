"""#202 媒合建議卡 Top 3–5：白話、無 B 代號，「為何推薦」比照法規揭露規則與原文。

假引擎結果（engine.match 跑在假 capabilities 上）＋假 LLM，不打真模型。
"""
from __future__ import annotations

import json
import re

import pytest

from app.matching import cards as cd
from app.matching import engine as eng

B_CODE = re.compile(r"B[1-8]")

A_TEXT = "我們有閒置穀倉可借用。希望找人協助行銷通路。也想有人幫忙設計品牌。"
BI_TEXT = "我們經營農產電商平台，已有三千名會員。正在尋找可以辦市集的場地。"
ONE2_TEXT = "我們已在全聯上架雜糧禮盒。團隊有專職設計師做包裝。想找人帶小學生體驗課。"
ONE1_TEXT = "我們有固定合作的農會通路。"
NONE_TEXT = "社區活動中心可以出借。缺研究人員協助調查。"


def ev(quote, kind):
    return {"quote": quote, "kind": kind}


def proj(pid, text, caps, **kw):
    return {"id": pid, "name": f"計畫{pid}", "site": "yunlin", "public": True,
            "philosophy": text, "capabilities": {"capabilities": caps}, **kw}


A = proj("A", A_TEXT, {
    "B1": {"direction": "OFFER", "evidence": [ev("閒置穀倉可借用", "concrete")]},
    "B7": {"direction": "NEED", "evidence": [ev("希望找人協助行銷通路", "aim")]},
    "B4": {"direction": "NEED", "evidence": [ev("想有人幫忙設計品牌", "aim")]},
})
T_BI = proj("bi", BI_TEXT, {
    "B7": {"direction": "OFFER", "evidence": [ev("我們經營農產電商平台", "concrete")]},
    "B1": {"direction": "NEED", "evidence": [ev("正在尋找可以辦市集的場地", "aim")]},
})
T_ONE2 = proj("one2", ONE2_TEXT, {
    "B7": {"direction": "OFFER", "evidence": [ev("已在全聯上架雜糧禮盒", "concrete")]},
    "B4": {"direction": "OFFER", "evidence": [ev("團隊有專職設計師做包裝", "concrete")]},
    "B3": {"direction": "NEED", "evidence": [ev("想找人帶小學生體驗課", "aim")]},
})
T_ONE1 = proj("one1", ONE1_TEXT, {
    # 一段不在原文裡的依據：卡上不得採用
    "B7": {"direction": "OFFER", "evidence": [ev("我們有固定合作的農會通路", "concrete"),
                                             ev("憑空捏造的通路", "concrete")]},
})
T_NONE = proj("none", NONE_TEXT, {
    "B1": {"direction": "OFFER", "evidence": [ev("社區活動中心可以出借", "concrete")]},
    "B5": {"direction": "NEED", "evidence": [ev("缺研究人員協助調查", "aim")]},
})
ALL = [A, T_BI, T_ONE2, T_ONE1, T_NONE]
PHIL = {p["id"]: p["philosophy"] for p in ALL}
RULE_NAMES = ("雙向互補優先", "互補候選數多者優先")
NOT_EVAL = ("議題與目標對象", "合作可執行性", "跨國語境與成本", "階段與時程")


class FakeLLM:
    """假 LLM：記錄呼叫次數；故意在回覆裡夾 B 代號、留一欄空白，驗證卡會白話化並填「不足」。"""

    def __init__(self):
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return json.dumps({
            "互補性": "對方在 B7 市場與通路上能補足發起計畫。",
            "互惠價值": "雙方都能得到 B1–B8 中缺的資源。",
            "建議合作": "先一起辦一場週末市集。",
            "待確認": "",
            "風險": "雙方時間可能排不攏。",
        }, ensure_ascii=False)


class InvokeLLM:
    def __init__(self):
        self.n = 0

    def invoke(self, messages):
        self.n += 1

        class R:
            content = "```json\n{\"互補性\": \"互補\"}\n```"
        return R()


def run(targets, *, top_n=3, llm=None):
    llm = llm if llm is not None else FakeLLM()
    result = eng.match(A, targets)
    return result, cd.build_cards(result, ALL, llm=llm, top_n=top_n), llm


def full_text(card):
    return cd.render(card) + json.dumps(card, ensure_ascii=False)


# ── (a) 卡數 ≤ min(5, 對象數) ────────────────────────────────────────

@pytest.mark.parametrize("targets", [
    [T_ONE1, T_BI],
    [T_NONE, T_ONE1, T_BI],
    [T_NONE, T_ONE1, T_ONE2, T_BI],
])
def test_card_count(targets):
    result, cards, _ = run(targets)
    assert 0 < len(cards) <= min(5, len(targets))
    assert len(cards) == min(5, len(result["ranking"]))
    assert [c["rank"] for c in cards] == list(range(1, len(cards) + 1))
    assert [c["target"] for c in cards] == result["order"][:len(cards)]


def test_excluded_targets_get_no_card():
    priv = {**T_BI, "id": "priv", "public": False}
    result, cards, _ = run([priv, T_ONE1, T_BI])
    assert "priv" not in [c["target"] for c in cards]
    assert len(cards) <= min(5, 3)


def test_card_count_capped_at_five():
    fake = {"a": "A", "targets": [f"t{i}" for i in range(7)],
            "ranking": [{"rank": i + 1, "target": f"t{i}"} for i in range(7)]}
    assert cd.card_count(fake) == 5


# ── (b) 六欄齊全；無依據寫「不足」 ──────────────────────────────────

def test_six_fields_and_insufficient():
    _, cards, _ = run([T_NONE, T_ONE1, T_ONE2, T_BI], top_n=1)
    for c in cards:
        assert tuple(c["fields"]) == cd.FIELDS
        assert all(isinstance(v, str) and v.strip() for v in c["fields"].values())
    # LLM 回空白的欄位 → 不足
    assert cards[0]["fields"]["待確認"] == "不足"
    # 程式組字的卡：沒有依據的欄位不臆測
    rest = {c["target"]: c for c in cards[1:]}
    assert rest["none"]["fields"]["為何推薦"] == "不足"
    assert rest["none"]["fields"]["互補性"] == "不足"
    for c in cards[1:]:
        assert c["fields"]["建議合作"] == "不足"
        assert c["fields"]["風險"] == "不足"
    # 單向互補沒有互惠依據
    assert rest["one2"]["fields"]["互惠價值"] == "不足"


# ── (c) 全文不含 B1–B8 代號 ─────────────────────────────────────────

def test_no_b_codes_anywhere():
    _, cards, _ = run([T_NONE, T_ONE1, T_ONE2, T_BI], top_n=2)
    for c in cards:
        text = full_text(c)
        assert not B_CODE.search(text), text
    # 代號換成中文類別名稱
    assert "市場與通路" in cards[0]["fields"]["互補性"]


# ── (d) 「為何推薦」含規則名稱與雙方原文，原文逐字存在於 philosophy ───

def test_why_discloses_rule_and_verbatim_quotes():
    _, cards, _ = run([T_NONE, T_ONE1, T_ONE2, T_BI])
    top = cards[0]
    assert top["target"] == "bi"
    why = top["fields"]["為何推薦"]
    assert any(n in why for n in RULE_NAMES)
    assert "規則原文" in why
    quotes = top["推薦依據"]["雙方原文"]
    a_q, t_q = quotes["計畫A"], quotes["計畫bi"]
    assert a_q and t_q
    for q in a_q:
        assert q in PHIL["A"] and f"「{q}」" in why
    for q in t_q:
        assert q in PHIL["bi"] and f"「{q}」" in why
    # 每一段被引用的原文都逐字存在於某一方的 philosophy
    for c in cards:
        for side, qs in c["推薦依據"]["雙方原文"].items():
            pid = side.removeprefix("計畫")
            for q in qs:
                assert q in PHIL[pid]
        _, _, cited = c["fields"]["為何推薦"].partition("對應原文——")
        for q in re.findall(r"「([^」]+)」", cited.split("排在第")[0]):
            assert q in PHIL["A"] or q in PHIL[c["target"]], q
    assert [r["規則"] for r in top["推薦依據"]["成立規則"]] == list(RULE_NAMES)
    assert "分數" not in why and "總分" not in why


def test_fabricated_quote_not_used():
    _, cards, _ = run([T_ONE1, T_NONE])
    one1 = next(c for c in cards if c["target"] == "one1")
    assert "憑空捏造的通路" not in full_text(one1)
    assert "我們有固定合作的農會通路" in one1["fields"]["為何推薦"]


# ── (e) 四維標「未評估」 ─────────────────────────────────────────────

def test_not_evaluated_dimensions():
    _, cards, _ = run([T_ONE1, T_BI])
    for c in cards:
        assert set(c["未評估"]) == set(NOT_EVAL)
        assert all(v == "未評估" for v in c["未評估"].values())
        assert "未評估" in cd.render(c)


# ── (f) LLM 只被呼叫 N 次 ───────────────────────────────────────────

@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_llm_called_only_top_n(n):
    _, cards, llm = run([T_NONE, T_ONE1, T_ONE2, T_BI], top_n=n)
    assert len(llm.calls) == min(n, len(cards))
    assert [c["llm"] for c in cards] == [i < n for i in range(len(cards))]
    # 送進 LLM 的內容也不含代號
    for msgs in llm.calls:
        assert not B_CODE.search(msgs[1]["content"])


def test_top_n_larger_than_cards():
    _, cards, llm = run([T_ONE1, T_BI], top_n=10)
    assert len(llm.calls) == len(cards) == 2


def test_invoke_style_llm():
    llm = InvokeLLM()
    _, cards, _ = run([T_ONE1, T_BI], top_n=1, llm=llm)
    assert llm.n == 1
    assert cards[0]["fields"]["互補性"] == "互補"
    assert cards[0]["fields"]["風險"] == "不足"


# ── 合作起步草案 ────────────────────────────────────────────────────

def test_start_draft_options():
    _, cards, _ = run([T_ONE1, T_BI])
    for c in cards:
        d = c["合作起步草案"]
        assert d["決定者"] == "發起人"
        assert [s["name"] for s in d["選項"]] == ["介紹", "會議", "資料交換", "小型 Pilot"]


def test_prompt_loads():
    p = cd.load_prompt()
    assert p["system"] and "{{context}}" in p["user"]
    assert "不足" in p["system"]
