"""#178 多輪狀態機的 Chainlit 轉接層：用假 Chainlit 物件測一題一問、草稿確認、重算回報、跳過。"""
import asyncio
import copy
import json

from app.loop import load_rules
from app.loop.chainlit_adapter import (
    ACTION_CANCEL, ACTION_CONFIRM, ACTION_SKIP, ACTION_UNKNOWN, SOURCE_USER, ClarifyLoop,
    register_action_callbacks,
)

YAML = """
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
clarify_questions:
  NEED:
    用途: "主要用在哪裡？"
    缺口: "現在缺的是什麼？"
  OFFER:
    可提供形式: "可以用什麼形式提供？"
"""


class FakeAction:
    def __init__(self, name, label, payload):
        self.name, self.label, self.payload = name, label, payload


class FakeSession:
    """模擬 cl.user_session；值以 JSON 往返，確保可存入 thread metadata。"""

    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.store.get(key, default))

    def set(self, key, value):
        self.store[key] = json.loads(json.dumps(value, ensure_ascii=False))


class FakeCL:
    def __init__(self, session=None):
        self.sent = []
        self.user_session = session or FakeSession()
        self.callbacks = {}
        cl = self

        class Message:
            def __init__(self, content="", actions=None, **kw):
                self.content, self.actions = content, list(actions or [])

            async def send(self):
                cl.sent.append(self)
                return self

        self.Message = Message
        self.Action = lambda name, label, payload: FakeAction(name, label, payload)

    def action_callback(self, name):
        def deco(fn):
            self.callbacks[name] = fn
            return fn
        return deco

    def take(self):
        out, self.sent = self.sent, []
        return out


def run(coro):
    return asyncio.run(coro)


def make():
    cl = FakeCL()
    return cl, ClarifyLoop(load_rules(YAML), cl)


def labels(msg):
    return [a.label for a in msg.actions]


def question_msgs(msgs):
    return [m for m in msgs if labels(m) == ["還不知道", "跳過"]]


# (a) 一次只送出一題，帶「還不知道」「跳過」
def test_start_sends_exactly_one_question_with_buttons():
    cl, loop = make()
    run(loop.start())
    msgs = cl.take()
    assert len(msgs) == 1
    assert msgs[0].content == "主要用在哪裡？"
    assert labels(msgs[0]) == ["還不知道", "跳過"]
    assert [a.payload for a in msgs[0].actions] == [{"field": "用途"}] * 2
    assert loop.pending["field"] == "用途"


# (b) 打字後先出草稿，未確認不寫入；確認後寫入並標「使用者陳述・未查證」
def test_typed_answer_is_draft_until_confirmed():
    cl, loop = make()
    run(loop.start())
    cl.take()

    assert run(loop.on_message("社區共餐")) is True
    msgs = cl.take()
    assert len(msgs) == 1 and "草稿" in msgs[0].content and "社區共餐" in msgs[0].content
    assert labels(msgs[0]) == ["確認納入", "取消"]
    assert "用途" not in loop.session.facts and loop.records == []
    assert loop.rounds == []

    run(loop.on_action(ACTION_CONFIRM, {"field": "用途"}))
    assert loop.session.facts["用途"] == "社區共餐"
    assert loop.records == [{"field": "用途", "value": "社區共餐", "source": SOURCE_USER}]
    assert SOURCE_USER == "使用者陳述・未查證"
    assert loop.rounds[-1]["answer"]["source"] == "使用者陳述・未查證"
    msgs = cl.take()
    assert any("使用者陳述・未查證" in m.content for m in msgs)
    # 記錄後接著問下一題，而且只問一題
    qs = question_msgs(msgs)
    assert len(qs) == 1 and qs[0].content == "可以用什麼形式提供？"


def test_cancel_does_not_record_and_keeps_question():
    cl, loop = make()
    run(loop.start())
    run(loop.on_message("亂打的"))
    cl.take()
    run(loop.on_action(ACTION_CANCEL, {"field": "用途"}))
    assert "用途" not in loop.session.facts and loop.records == [] and loop.draft is None
    assert loop.pending["field"] == "用途"
    msgs = cl.take()
    assert len(msgs) == 1 and "取消" in msgs[0].content and not question_msgs(msgs)
    # 取消後的「確認納入」不能把舊草稿寫進去
    run(loop.on_action(ACTION_CONFIRM, {"field": "用途"}))
    assert "用途" not in loop.session.facts


# (c) 補齊最低欄位後回報「起點 → 下一狀態」，未補齊時回報「仍是」
def test_state_report_transition_and_unchanged():
    cl, loop = make()
    run(loop.start())
    cl.take()

    run(loop.on_message("社區共餐"))
    run(loop.on_action(ACTION_CONFIRM, {"field": "用途"}))
    msgs = cl.take()
    assert any("仍是 CLARIFY_FIRST" in m.content for m in msgs)
    assert loop.state == "CLARIFY_FIRST"

    run(loop.on_message("場地"))
    run(loop.on_action(ACTION_CONFIRM, {"field": "可提供形式"}))
    msgs = cl.take()
    assert any("CLARIFY_FIRST → EXPLORE" in m.content for m in msgs)
    assert loop.state == "EXPLORE"
    last = loop.rounds[-1]
    assert (last["before"], last["after"], last["changed"]) == ("CLARIFY_FIRST", "EXPLORE", True)
    assert loop.rounds[0]["changed"] is False


def test_unknown_is_recorded_but_not_filled():
    cl, loop = make()
    run(loop.start())
    cl.take()
    run(loop.on_action(ACTION_UNKNOWN, {"field": "用途"}))
    msgs = cl.take()
    assert any("仍是 CLARIFY_FIRST" in m.content for m in msgs)
    assert loop.rounds[-1]["answer"]["kind"] == "unknown"
    assert [q.content for q in question_msgs(msgs)] == ["可以用什麼形式提供？"]


# (d) 跳過後換下一題，不重問
def test_skip_moves_on_and_never_reasks():
    cl, loop = make()
    run(loop.start())
    cl.take()
    run(loop.on_action(ACTION_SKIP, {"field": "用途"}))
    msgs = cl.take()
    assert any("仍是 CLARIFY_FIRST" in m.content for m in msgs)
    qs = question_msgs(msgs)
    assert len(qs) == 1 and qs[0].content == "可以用什麼形式提供？"
    assert "用途" not in loop.session.facts

    asked = ["主要用在哪裡？", qs[0].content]
    run(loop.on_action(ACTION_SKIP, {"field": "可提供形式"}))
    asked += [m.content for m in question_msgs(cl.take())]
    run(loop.on_action(ACTION_SKIP, {"field": "缺口"}))
    tail = cl.take()
    assert not question_msgs(tail) and any("沒有其他要問的" in m.content for m in tail)
    assert asked == ["主要用在哪裡？", "可以用什麼形式提供？", "現在缺的是什麼？"]
    assert loop.pending is None


def test_stale_button_is_ignored():
    cl, loop = make()
    run(loop.start())
    run(loop.on_action(ACTION_SKIP, {"field": "用途"}))
    cl.take()
    run(loop.on_action(ACTION_SKIP, {"field": "用途"}))  # 舊訊息上的按鈕
    msgs = cl.take()
    assert len(msgs) == 1 and "過期" in msgs[0].content
    assert loop.pending["field"] == "可提供形式"


# 每一輪的狀態、問題、回答、重算結果寫進 session，重新整理（重建物件）後仍在
def test_rounds_persist_in_session_across_reload():
    cl, loop = make()
    run(loop.start())
    run(loop.on_message("社區共餐"))
    run(loop.on_action(ACTION_CONFIRM, {"field": "用途"}))
    run(loop.on_action(ACTION_UNKNOWN, {"field": "可提供形式"}))
    run(loop.on_message("人力"))  # 草稿也要撐過重新整理
    cl.take()

    stored = cl.user_session.store["clarify_loop"]
    assert [r["question"]["field"] for r in stored["rounds"]] == ["用途", "可提供形式"]
    assert stored["rounds"][0]["answer"] == {"kind": "answer", "value": "社區共餐", "source": SOURCE_USER}
    assert stored["rounds"][1]["after"] == "CLARIFY_FIRST"

    cl2 = FakeCL(cl.user_session)
    loop2 = ClarifyLoop.restore(load_rules(YAML), cl2)
    assert loop2.rounds == loop.rounds and loop2.records == loop.records
    assert loop2.session.facts["用途"] == "社區共餐"
    assert loop2.session.rules.is_unknown(loop2.session.facts["可提供形式"])
    assert loop2.pending["field"] == "缺口" and loop2.draft["value"] == "人力"

    run(loop2.start())  # 重新整理後重送目前題目，不跳到新題
    msgs = cl2.take()
    assert len(msgs) == 1 and msgs[0].content == "現在缺的是什麼？"

    run(loop2.on_action(ACTION_CONFIRM, {"field": "缺口"}))
    assert loop2.session.facts["缺口"] == "人力"
    assert len(cl2.user_session.store["clarify_loop"]["rounds"]) == 3


def test_message_without_pending_question_is_not_consumed():
    cl, loop = make()
    assert run(loop.on_message("hi")) is False
    assert cl.sent == []


def test_register_action_callbacks_routes_to_session():
    cl = FakeCL()
    rules = load_rules(YAML)
    run(ClarifyLoop(rules, cl).start())
    register_action_callbacks(lambda: rules, cl)
    assert set(cl.callbacks) == {ACTION_UNKNOWN, ACTION_SKIP, ACTION_CONFIRM, ACTION_CANCEL}
    cl.take()
    run(cl.callbacks[ACTION_SKIP](FakeAction(ACTION_SKIP, "跳過", {"field": "用途"})))
    assert ClarifyLoop.restore(rules, cl).pending["field"] == "可提供形式"
