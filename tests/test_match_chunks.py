"""#199：philosophy 切段標籤＋原文位置。全部用假判斷結果，不打真模型。"""
import re

from app.matching import capability as cap
from app.matching import chunks as ch

PHIL = (
    "本社區已活化閒置穀倉作為共同工作空間，每月舉辦兩場農事體驗。\n"
    "我們希望發展在地品牌，並推動青年返鄉！\n\n"
    "社區也有長者共餐。"
)

RAW = {
    "B1": [{"quote": "已活化閒置穀倉作為共同工作空間", "kind": "concrete"}],
    "B3": [{"quote": "每月舉辦兩場農事體驗", "kind": "concrete"},
           {"quote": "推動青年返鄉", "kind": "aim"}],
    "B4": [{"quote": "希望發展在地品牌", "kind": "aim"}],
    "B5": [{"quote": "我們擁有三公頃農地", "kind": "concrete"}],  # 捏造 → #182 會丟掉
}


class Analyzer:
    """假的 3-1：數呼叫次數，用 #182 的 judge 驗證假 LLM 回覆。"""

    def __init__(self, raw=RAW):
        self.raw, self.calls = raw, 0

    def __call__(self, philosophy):
        self.calls += 1
        return cap.judge(philosophy, self.raw)


def test_positions_slice_back_verbatim_and_every_chunk_labelled():
    rec = ch.ensure_chunks("p1", PHIL, ch.MemoryStore(), analyzer=Analyzer())
    chunks = rec["chunks"]
    assert chunks, "應該有 chunk"
    for c in chunks:
        assert PHIL[c["start"]:c["end"]] == c["text"]
        assert c["text"].strip() == c["text"] and c["text"]
        assert len(c["labels"]) >= 1
        for lb in c["labels"]:
            assert lb["capability"] in cap.B_KEYS
            assert lb["direction"] in (cap.NEED, cap.OFFER, cap.BOTH)
    # 第三段沒有依據 → 不存（不臆測）
    assert all("長者共餐" not in c["text"] for c in chunks)


def test_labels_only_from_judgement():
    rec = ch.ensure_chunks("p1", PHIL, ch.MemoryStore(), analyzer=Analyzer())
    by_text = {c["text"]: {lb["capability"]: lb["direction"] for lb in c["labels"]} for c in rec["chunks"]}
    first, second = list(by_text)
    assert by_text[first] == {"B1": "OFFER", "B3": "OFFER"}
    assert by_text[second] == {"B3": "NEED", "B4": "NEED"}
    used = {lb["capability"] for c in rec["chunks"] for lb in c["labels"]}
    assert "B5" not in used  # 捏造的依據被 #182 丟掉，不會變成標籤


def test_empty_judgement_gives_no_chunks():
    assert ch.label_chunks(PHIL, cap.judge(PHIL, {})) == []
    assert ch.label_chunks("", {}) == []


def test_same_hash_reuses_changed_one_char_recomputes():
    store, an = ch.MemoryStore(), Analyzer()
    r1 = ch.ensure_chunks("p1", PHIL, store, analyzer=an)
    assert r1["recomputed"] and an.calls == 1
    r2 = ch.ensure_chunks("p1", PHIL, store, analyzer=an)
    assert not r2["recomputed"] and an.calls == 1
    assert r2["hash"] == r1["hash"] and r2["chunks"] == r1["chunks"]

    changed = PHIL.replace("兩場", "三場")
    assert ch.content_hash(changed) != ch.content_hash(PHIL)
    r3 = ch.ensure_chunks("p1", changed, store, analyzer=an)
    assert r3["recomputed"] and an.calls == 2
    assert store["p1"]["hash"] == ch.content_hash(changed)
    for c in r3["chunks"]:
        assert changed[c["start"]:c["end"]] == c["text"]


def test_default_analyzer_uses_injected_llm():
    import json

    calls = []

    def fake_llm(messages):
        calls.append(messages)
        return json.dumps(RAW, ensure_ascii=False)

    rec = ch.ensure_chunks("p2", PHIL, ch.MemoryStore(), llm=fake_llm)
    assert len(calls) == 1 and rec["chunks"]


def test_user_message_hides_b_codes_and_chunks():
    rec = ch.ensure_chunks("p1", PHIL, ch.MemoryStore(), analyzer=Analyzer())
    msg = ch.user_message(rec)
    assert msg
    assert not re.search(r"B\s*[1-8]", msg)
    assert "chunk" not in msg.lower()
    for c in rec["chunks"]:
        assert c["text"] not in msg
    assert "空間與場域" in msg and "可提供" in msg
    empty = ch.user_message({"judgement": cap.judge(PHIL, {})})
    assert not re.search(r"B\s*[1-8]", empty) and "chunk" not in empty.lower()


def test_scrub_removes_b_codes():
    assert not re.search(r"[Bb][1-8](?![0-9])", ch.scrub("屬於 B1 與 b8 類，B12 保留"))
    assert "B12" in ch.scrub("B12 保留")
