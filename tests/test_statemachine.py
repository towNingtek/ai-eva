"""#177 多輪狀態機核心（app/loop）：狀態、規則評估、下一題、回答後重算。"""
from pathlib import Path

import pytest

from app.loop import UNKNOWN, Session, load_rules

# 測試用 YAML：兩個最低欄位 + 兩個其他欄位（v1.1 mapping 格式）
YAML_A = """
status_rules:
  CLARIFY_FIRST:
    原文: 缺關鍵資料
  EXPLORE:
    原文: 最低欄位補齊
status_transition:
  from: CLARIFY_FIRST
  to: EXPLORE
  minimum_fields:
    NEED: 用途
    OFFER: 可提供形式
  unknown_counts_as_filled: false
clarify_questions:
  pace: 一次只問一題
  buttons: [還不知道, 跳過]
  NEED:
    用途: "主要用在哪裡？"
    缺口: "現在缺的是什麼？"
  OFFER:
    可提供形式: "可以用什麼形式提供？"
    地區: "可以在哪些地方提供？"
"""

# 另一份 YAML：完全不同欄位名、狀態名、list 題目格式、還有規則條件
YAML_B = """
status_rules:
  BLOCKED:
    when: {fact_in: {color: [red]}}
  DONE:
    when: {all_filled: minimum_fields}
  WAIT:
    when: {always: true}
status_transition:
  from: WAIT
  to: DONE
  minimum_fields: [size, color]
clarify_questions:
  - {field: weight, ask: "How heavy?"}
  - {field: color, ask: "What color?", options: [red, blue, 還不知道]}
  - {field: size, ask: "How big?"}
"""


@pytest.fixture
def rules_a():
    return load_rules(YAML_A)


@pytest.fixture
def rules_b():
    return load_rules(YAML_B)


# (a) 起點狀態 → 只補一個仍是起點 → 兩個都補才轉下一狀態
def test_state_transition_requires_both_minimum_fields(rules_a):
    assert rules_a.evaluate({}).state == "CLARIFY_FIRST"
    assert rules_a.evaluate({"用途": "共學"}).state == "CLARIFY_FIRST"
    assert rules_a.evaluate({"可提供形式": "借用"}).state == "CLARIFY_FIRST"
    ev = rules_a.evaluate({"用途": "共學", "可提供形式": "借用"})
    assert ev.state == "EXPLORE"
    assert ev.missing_minimum == ()


def test_missing_list(rules_a):
    ev = rules_a.evaluate({})
    assert ev.missing == ("用途", "可提供形式", "缺口", "地區")
    assert ev.missing_minimum == ("用途", "可提供形式")
    assert rules_a.evaluate({"用途": "x"}).missing == ("可提供形式", "缺口", "地區")


def test_session_recomputes_after_each_answer(rules_a):
    s = Session(rules_a)
    assert s.state == "CLARIFY_FIRST"
    assert s.answer("用途", "共學").state == "CLARIFY_FIRST"
    assert s.answer("可提供形式", "借用").state == "EXPLORE"
    assert s.missing == ("缺口", "地區")


# (b) 下一題：先最低欄位、依 YAML 順序；問過、跳過的不再出現；問完回 None
def test_next_question_order_and_exhaustion(rules_a):
    s = Session(rules_a)
    seen = []
    q = s.next_question()
    assert q.field == "用途" and q.minimum and q.text == "主要用在哪裡？"
    seen.append(q.field)
    s.skip(q.field)                     # 跳過
    q = s.next_question()
    assert q.field == "可提供形式" and q.minimum
    seen.append(q.field)
    s.answer(q.field, "借用")           # 回答
    q = s.next_question()
    assert q.field == "缺口" and not q.minimum
    seen.append(q.field)
    s.unknown(q.field)                  # 還不知道
    q = s.next_question()
    assert q.field == "地區"
    seen.append(q.field)
    s.answer(q.field, "雲林")
    assert s.next_question() is None
    assert seen == ["用途", "可提供形式", "缺口", "地區"]
    assert len(set(seen)) == len(seen)
    # 跳過的最低欄位仍算缺 → 狀態維持起點
    assert s.state == "CLARIFY_FIRST"
    assert s.missing == ("用途", "缺口")


def test_next_question_minimum_first_even_if_listed_later(rules_b):
    order = []
    s = Session(rules_b)
    while (q := s.next_question()) is not None:
        order.append(q.field)
        s.skip(q.field)
    assert order == ["color", "size", "weight"]


def test_next_question_with_asked_param(rules_a):
    assert rules_a.next_question({}, asked=["用途", "可提供形式"]).field == "缺口"
    assert rules_a.next_question({}, asked=["用途", "可提供形式", "缺口", "地區"]) is None


# (c) 「還不知道」記錄後不算補齊
def test_unknown_recorded_but_not_filled(rules_a):
    s = Session(rules_a)
    s.answer("用途", "共學")
    ev = s.answer("可提供形式", "還不知道")
    assert s.facts["可提供形式"] is UNKNOWN
    assert ev.unknown == ("可提供形式",)
    assert "可提供形式" in ev.missing
    assert ev.state == "CLARIFY_FIRST"
    assert ("unknown", "可提供形式", UNKNOWN) in s.history
    # 不再重複問
    assert ev.next_question.field == "缺口"
    # 之後補上真實答案才轉狀態
    assert s.answer("可提供形式", "借用").state == "EXPLORE"


def test_unknown_string_in_facts_not_filled(rules_a):
    ev = rules_a.evaluate({"用途": "共學", "可提供形式": "還不知道"})
    assert ev.state == "CLARIFY_FIRST"
    assert ev.unknown == ("可提供形式",)


# (d) 同一輸入跑兩次結果相同
def test_deterministic(rules_a, rules_b):
    facts = {"用途": "共學", "缺口": "還不知道"}
    r1 = rules_a.evaluate(facts, asked=["地區"]).as_dict()
    r2 = load_rules(YAML_A).evaluate(dict(facts), asked=["地區"]).as_dict()
    assert r1 == r2
    for _ in range(3):
        assert rules_a.evaluate(facts, asked=["地區"]).as_dict() == r1

    def run():
        s = Session(load_rules(YAML_B))
        s.answer("size", 3)
        s.skip("color")
        return s.last.as_dict(), list(s.history)

    assert run() == run()


# (e) 換另一份 YAML（不同欄位名）不改程式即可運作
def test_other_yaml_works(rules_b):
    assert rules_b.evaluate({}).state == "WAIT"
    assert rules_b.evaluate({"size": 1}).state == "WAIT"
    assert rules_b.evaluate({"size": 1, "color": "blue"}).state == "DONE"
    assert rules_b.evaluate({"size": 1, "color": "red"}).state == "BLOCKED"
    assert rules_b.evaluate({"size": 1, "color": "還不知道"}).state == "WAIT"
    assert rules_b.next_question({}).extra["options"] == ["red", "blue", "還不知道"]


def test_real_standards_load():
    root = Path(__file__).resolve().parents[1] / "app"
    # 媒合標準 v1.1：status_transition 沒寫 from/to，由呼叫端指定
    match = load_rules(root / "matching" / "standard_yunlin_v1.yaml", start="CLARIFY_FIRST", target="EXPLORE")
    assert match.minimum_fields == ("用途", "可提供形式")
    assert match.evaluate({}).state == "CLARIFY_FIRST"
    assert match.evaluate({"用途": "x"}).state == "CLARIFY_FIRST"
    assert match.evaluate({"用途": "x", "可提供形式": "y"}).state == "EXPLORE"
    assert [q.field for q in match.questions[:2]] == ["用途", "可提供形式"]
    # 法規標準 v0.3：states 取 CLARIFY_FIRST／READY；沒列最低欄位 → 每題都必要
    law = load_rules(root / "regulations" / "corpus" / "standard_yunlin_v1.yaml")
    fields = [q.field for q in law.questions]
    assert fields[0] == "申請開發面積"
    assert law.evaluate({}).state == "CLARIFY_FIRST"
    assert law.evaluate({f: "x" for f in fields[:-1]}).state == "CLARIFY_FIRST"
    assert law.evaluate({f: "x" for f in fields}).state == "READY"


def test_module_does_not_hardcode_field_names():
    """核心程式（不含 docstring）不得出現任何法規／媒合的欄位名或狀態名。"""
    import ast

    banned = {"用途", "可提供形式", "申請開發面積", "NEED", "OFFER", "EXPLORE", "CLARIFY_FIRST", "READY"}
    for p in (Path(__file__).resolve().parents[1] / "app" / "loop").glob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        consts = [n.value for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
        assert not [c for c in consts if any(b in c for b in banned)], p
