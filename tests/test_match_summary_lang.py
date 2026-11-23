"""#229 聊天裡的媒合摘要（task.summary）依使用者語言輸出。

lang＝en／ja／ko：扣掉專案名稱後沒有漢字（ja 以假名占比判定：不得有中文專用字形、也不得有「長句無假名」）。
lang＝zh：與修改前（beta a69d75e）一字不差。語言來源預設 current_lang()（經 task._lang）。
"""
from __future__ import annotations

import re

import pytest

from app.apps.match_analysis import task as mt
from app.matching import pair

NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊", "d": "導覽協會"}
STATUS = {"b": pair.EXPLORE, "c": pair.CLARIFY_FIRST, "d": pair.ELIGIBLE}


def _task(cards: int = 3) -> dict:
    pairs = [{"pa": "a", "pb": pb, "status": STATUS[pb], "status_text": pair.STATUS_TEXT[STATUS[pb]],
              "counts": {"complement": 1, "third": i, "peer": 2 - i}} for i, pb in enumerate("bcd")]
    return {"result": {"a": "a", "pairs": pairs,
                       "projects": [{"pid": k, "name": v} for k, v in NAMES.items()]},
            "cards": [{"target": t} for t in "bcd"][:cards]}


ZH = """## 🧭 媒合星球：大庄社區 × 3 個指定對象

- **農產合作社**：可探索（互補候選 1・共同尋找第三方 0・可聯合或交流 2）
- **青年團隊**：先補資料（互補候選 1・共同尋找第三方 1・可聯合或交流 1）
- **導覽協會**：可排序・未建議（互補候選 1・共同尋找第三方 2・可聯合或交流 0）

工作區列出 3 張媒合建議卡：可收藏、略過、補資料；要聯絡對方請按卡片上的「寄站內邀請」並確認，Eva 不會自動寄出。

點星球上的衛星或一對，Eva 會用這次的結果說明（不重新判斷）。
第一期不推薦、不自動聯絡；B1–B8 與方向是 AI 推論（未經 Owner 確認）。"""

ZH_NO_CARDS = """## 🧭 媒合星球：大庄社區 × 3 個指定對象

- **農產合作社**：可探索（互補候選 1・共同尋找第三方 0・可聯合或交流 2）
- **青年團隊**：先補資料（互補候選 1・共同尋找第三方 1・可聯合或交流 1）
- **導覽協會**：可排序・未建議（互補候選 1・共同尋找第三方 2・可聯合或交流 0）

點星球上的衛星或一對，Eva 會用這次的結果說明（不重新判斷）。
第一期不推薦、不自動聯絡；B1–B8 與方向是 AI 推論（未經 Owner 確認）。"""

HAN = re.compile(r"[㐀-鿿豈-﫿]")
KANA = re.compile(r"[぀-ヿ]")
CN_ONLY = re.compile("[們這會為與對說號關讀從還經實寫錄邀狀專畫處應來嗎您讓麼將个们这会为与对说号关读从还经实写录邀状专画处应来吗让么将选择项确认补资时间开启请]")


def _strip(text: str) -> str:
    for n in NAMES.values():
        text = text.replace(n, "")
    return text


def _violations(lang: str, text: str) -> list[str]:
    t = _strip(text)
    if lang != "ja":
        return [line for line in t.splitlines() if HAN.search(line)]
    bad = [f"中文字形: {line}" for line in t.splitlines() if CN_ONLY.search(line)]
    for piece in re.split(r"[\n。！？!?]", t):
        if len(HAN.findall(piece)) >= 4 and len(piece.strip()) >= 8 and not KANA.search(piece):
            bad.append(f"長句無假名: {piece.strip()}")
    return bad


def test_zh_unchanged():
    assert mt.summary(_task(), "zh") == ZH
    assert mt.summary(_task(0), "zh") == ZH_NO_CARDS


def test_default_zh_outside_chainlit():
    assert mt.summary(_task()) == ZH


@pytest.mark.parametrize("lang", ["en", "ja", "ko"])
@pytest.mark.parametrize("cards", [3, 0])
def test_foreign_has_no_chinese(lang, cards):
    out = mt.summary(_task(cards), lang)
    assert _violations(lang, out) == [], out
    # 專案名稱原樣保留，數字都在。
    for n in NAMES.values():
        assert n in out
    assert out.startswith("## 🧭 ")
    assert len(out.split("\n\n")) == len(mt.summary(_task(cards), "zh").split("\n\n"))


@pytest.mark.parametrize("lang", ["en", "ja", "ko"])
def test_lang_from_current_lang(monkeypatch, lang):
    import app.i18n

    monkeypatch.setattr(app.i18n, "current_lang", lambda: lang)
    out = mt.summary(_task())
    assert out == mt.summary(_task(), lang)
    assert _violations(lang, out) == []
