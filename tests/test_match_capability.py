"""#182：philosophy → B1–B8 方向與原文依據。全部用假 LLM，不打真模型。"""
import json
import logging

from app.matching import capability as cap

PHIL = (
    "本社區已活化閒置穀倉作為共同工作空間，每月舉辦兩場農事體驗。"
    "我們希望發展在地品牌，並推動青年返鄉。"
)


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)


def run(reply, phil=PHIL):
    fake = FakeLLM(reply)
    return cap.analyze(phil, llm=fake), fake


def test_non_substring_quote_dropped_and_logged_direction_none(caplog):
    caplog.set_level(logging.WARNING, logger=cap.__name__)
    out, _ = run({
        "B1": [{"quote": "已活化閒置穀倉作為共同工作空間", "kind": "concrete"},
               {"quote": "我們擁有三公頃農地", "kind": "concrete"}],      # 捏造
        "B4": [{"quote": "希望發展在地的品牌", "kind": "aim"}],             # 改字 → 不是子字串
    })
    b1, b4 = out["capabilities"]["B1"], out["capabilities"]["B4"]
    assert b1["direction"] == "OFFER"
    assert [e["quote"] for e in b1["evidence"]] == ["已活化閒置穀倉作為共同工作空間"]
    assert b4["direction"] == "none" and b4["evidence"] == []
    dropped = {(d["capability"], d["quote"]) for d in out["dropped"]}
    assert ("B1", "我們擁有三公頃農地") in dropped
    assert ("B4", "希望發展在地的品牌") in dropped
    assert "我們擁有三公頃農地" in caplog.text and "希望發展在地的品牌" in caplog.text
    for b in out["capabilities"].values():
        for e in b["evidence"]:
            assert e["quote"] in PHIL


def test_concrete_and_aim_in_same_category_is_both():
    out, _ = run({
        "B3": [{"quote": "每月舉辦兩場農事體驗", "kind": "concrete"},
               {"quote": "推動青年返鄉", "kind": "aim"}],
        "B4": [{"quote": "希望發展在地品牌", "kind": "aim"}],
    })
    assert out["capabilities"]["B3"]["direction"] == "BOTH"
    assert out["capabilities"]["B4"]["direction"] == "NEED"


def test_every_category_has_result_no_missing_key():
    out, _ = run({"B2": [{"quote": "農事", "kind": "concrete"}], "B9": [{"quote": "農事", "kind": "aim"}]})
    caps = out["capabilities"]
    assert list(caps) == [f"B{i}" for i in range(1, 9)]
    for k, v in caps.items():
        assert set(v) >= {"name", "direction", "evidence", "label"}
        assert v["direction"] in {"NEED", "OFFER", "BOTH", "none"}
        assert v["name"]
    assert caps["B1"]["name"] == "空間與場域"
    assert caps["B5"]["direction"] == "none"


def test_output_marked_inference():
    out, _ = run({"B1": [{"quote": "共同工作空間", "kind": "concrete"}]})
    assert "推論" in out["label"]
    assert out["label"] == "推論（AI，未經 Owner 確認）"
    assert out["semantics"] == "INFERENCE" and out["confirmation"] == "AI_CANDIDATE"
    assert all("推論" in v["label"] for v in out["capabilities"].values())


def test_garbage_reply_all_none_and_fenced_json_ok():
    out, _ = run("抱歉我無法回答")
    assert all(v["direction"] == "none" for v in out["capabilities"].values())
    fenced = "```json\n" + json.dumps({"B1": [{"quote": "穀倉", "kind": "concrete"}]}, ensure_ascii=False) + "\n```"
    out, _ = run(fenced)
    assert out["capabilities"]["B1"]["direction"] == "OFFER"


def test_unknown_kind_dropped_not_guessed():
    out, _ = run({"B1": [{"quote": "穀倉", "kind": "maybe"}]})
    assert out["capabilities"]["B1"]["direction"] == "none"
    assert out["dropped"][0]["capability"] == "B1"


def test_prompt_from_yaml_contains_philosophy_and_registry():
    _, fake = run({})
    msgs = fake.calls[0]
    assert PHIL in msgs[-1]["content"]
    assert "B8 治理與平台" in msgs[0]["content"]
    assert cap.PROMPT.exists() and cap.PROMPT.suffix == ".yaml"


def test_empty_philosophy_skips_llm():
    fake = FakeLLM({})
    out = cap.analyze("   ", llm=fake)
    assert fake.calls == []
    assert all(v["direction"] == "none" for v in out["capabilities"].values())


def test_langchain_style_invoke_supported():
    class Msg:
        content = json.dumps({"B6": [{"quote": "推動青年返鄉", "kind": "aim"}]}, ensure_ascii=False)

    class Chat:
        def invoke(self, messages):
            assert messages[0][0] == "system"
            return Msg()

    out = cap.analyze(PHIL, llm=Chat())
    assert out["capabilities"]["B6"]["direction"] == "NEED"
