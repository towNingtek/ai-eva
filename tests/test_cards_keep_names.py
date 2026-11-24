"""外文建議卡逐字保留專案名稱（ai-eva #252，EPIC #205）。

假 LLM 把專案名稱改寫（韓文把「…食農教育」寫成「…食農교육은」、日文「…食農の教育」、
英文直接翻成「[Test] riverside community food…」），卡片輸出的 LLM 欄位裡：
凡提到專案的地方都是完整原名或該語言的代稱，不存在「名稱前綴＋非原名字元」的殘缺形式；
正確完整名稱＋助詞原樣保留；送給 LLM 的系統提示含「專案名稱一字不改照抄」規則。
"""
import json

import pytest

from app.matching import cards as cd, engine as eng
from app.matching import i18n as mi

A_NAME = "[測試] 溪畔社區食農教育"
T_NAME = "【媒合測試B】竹山竹藝體驗工坊"


def ev(q, k):
    return {"quote": q, "kind": k}


def proj(pid, name, text, caps):
    return {"id": pid, "name": name, "site": "yunlin", "public": True, "philosophy": text,
            "capabilities": {"capabilities": caps}}


A = proj("A", A_NAME, "我們有閒置穀倉可借用。希望找人協助行銷通路。", {
    "B1": {"direction": "OFFER", "evidence": [ev("閒置穀倉可借用", "concrete")]},
    "B7": {"direction": "NEED", "evidence": [ev("希望找人協助行銷通路", "aim")]}})
T = proj("B", T_NAME, "我們經營農產電商平台。正在尋找可以辦市集的場地。", {
    "B7": {"direction": "OFFER", "evidence": [ev("我們經營農產電商平台", "concrete")]},
    "B1": {"direction": "NEED", "evidence": [ev("正在尋找可以辦市集的場地", "aim")]}})
T2 = proj("C", "社區活動中心", "社區活動中心可以出借。缺研究人員協助調查。", {
    "B1": {"direction": "OFFER", "evidence": [ev("社區活動中心可以出借", "concrete")]},
    "B5": {"direction": "NEED", "evidence": [ev("缺研究人員協助調查", "aim")]}})

CASES = {
    "ko": (f"[測試] 溪畔社區食農교육은 지역 어르신과 함께합니다. 【媒合測試B】竹山竹藝체험공방은 장터를 엽니다.", "ko"),
    "ja": ("[測試] 溪畔社區食農の教育は地域とつながります。【媒合測試B】竹山竹藝の体験工坊と協力します。", "ja"),
    "en": ("[Test] riverside community food education works with [測試] 溪畔社區食農 elders.", "en"),
    "ok": (f"{A_NAME}은 지역 어르신과 함께합니다. 「{T_NAME}」와 협력합니다.", "ko"),
}


class FakeLLM:
    def __init__(self, text):
        self.text, self.seen = text, []

    def __call__(self, messages):
        self.seen.append(messages)
        return json.dumps({f: self.text for f in cd.LLM_FIELDS}, ensure_ascii=False)


def mangled(text, name):
    """名稱前 NAME_PREFIX 字以上相同、但後面不是完整名稱的殘缺形式。"""
    i = 0
    while True:
        k = text.find(name[:cd.NAME_PREFIX], i)
        if k < 0:
            return None
        if not text.startswith(name, k):
            return text[k:k + len(name) + 3]
        i = k + len(name)


def build(case):
    text, lang = CASES[case]
    llm = FakeLLM(text)
    cards = cd.build_cards(eng.match(A, [T, T2]), [A, T, T2], llm=llm, top_n=1, lang=lang)
    assert cards and cards[0]["llm"] and cards[0]["name"] == T_NAME
    return cards[0], llm, lang


@pytest.mark.parametrize("case", list(CASES))
def test_no_mangled_names(case):
    card, llm, lang = build(case)
    for f in cd.FIELDS:
        v = card["fields"][f]
        for name in (A_NAME, T_NAME):
            assert mangled(v, name) is None, f"{case} {f}: {v}"
    for f in cd.LLM_FIELDS:
        assert "교육은" not in card["fields"][f] or case != "ko"


def test_ko_restored_to_full_name():
    card, _, _ = build("ko")
    v = card["fields"][cd.F_COMPLEMENT]
    assert v.startswith(f"{A_NAME}은 지역 어르신과"), v
    assert f"{T_NAME}은 장터를" in v, v


def test_ja_restored_to_full_name():
    card, _, _ = build("ja")
    v = card["fields"][cd.F_COLLAB]
    assert v.startswith(f"{A_NAME}は地域"), v
    assert f"{T_NAME}と協力" in v, v


def test_en_partial_restored():
    card, _, _ = build("en")
    v = card["fields"][cd.F_RISK]
    assert f"{A_NAME} elders" in v, v


def test_correct_name_kept_verbatim():
    card, _, _ = build("ok")
    for f in cd.LLM_FIELDS:
        assert card["fields"][f] == CASES["ok"][0]


def test_alias_when_still_incomplete():
    names = {A_NAME: mi.msg("a_default", "ko")}
    # 正常情形：換回完整名稱
    assert cd.keep_names("[測試] 溪畔社區食農교육은 좋다", names) == f"{A_NAME}은 좋다"
    # 保險：殘缺名稱改用代稱
    assert cd._alias_partial("[測試] 溪畔社區食農교육은 좋다", A_NAME, "발의 계획", [A_NAME]) == "발의 계획 좋다"


@pytest.mark.parametrize("case", list(CASES))
def test_system_prompt_has_keep_name_rule(case):
    _, llm, _ = build(case)
    system = llm.seen[0][0]["content"]
    assert "專案名稱一字不改照抄" in system
