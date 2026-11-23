"""ai-eva #235：寄站內邀請時附上「為什麼找你」（由建議卡組成）。

假 runtime（假 CMS）、假卡片 LLM：判斷 → 建議卡 → 確認框 → 寄出；
確認 /matching/invite 收到的 message 含發起專案名與「建議合作」、≤ 200 字、無網址，
且與確認框顯示的附言一字不差；建議卡全「不足」時只寫「…想跟你談談合作的可能」。
"""
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.apps.match_analysis import handler, task
from app.matching import capability, cards, flow

ROOT = Path(__file__).resolve().parents[1]

PHIL = {
    "a": "我們的社區有閒置穀倉可以提供場地，也需要行銷通路協助販售農產品。",
    "b": "合作社有通路可以協助販售，需要場地辦理市集。",
    "c": "青年團隊有行銷通路可以協助販售，想找人一起開發。",
}
RAW = {
    "a": {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
          "B7": [{"quote": "需要行銷通路協助販售農產品", "kind": "aim"}]},
    "b": {"B7": [{"quote": "有通路可以協助販售", "kind": "concrete"}],
          "B1": [{"quote": "需要場地辦理市集", "kind": "aim"}]},
    "c": {"B7": [{"quote": "有行銷通路可以協助販售", "kind": "concrete"}]},
}
NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊"}
TARGETS = ["b", "c"]
URL = re.compile(r"http|www", re.I)


class Runtime:
    """假 runtime：記下每次呼叫；manifest 以 endpoint 找工具。"""

    def __init__(self):
        self.calls = []
        self._tools = {
            "matching_card_action": {"endpoint": "/matching/card_action"},
            "matching_invite": {"endpoint": "/matching/invite"},
        }

    def invites(self):
        return [c for c in self.calls if c[0] == "matching_invite"]

    async def execute(self, name, args, confirmed=False):
        self.calls.append((name, dict(args), confirmed))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": list(NAMES)}}}
        if name == "get_project_info":
            u = args["uuid"]
            return {"status": "ok", "result": {"data": {"name": NAMES[u], "philosophy": f"<p>{PHIL[u]}</p>"}}}
        if name in ("matching_card_action", "matching_invite"):
            return {"status": "ok", "result": {"data": {"ok": True}}}
        return {"status": "error", "reason": f"unknown tool {name}"}


FULL = {
    cards.F_COMPLEMENT: "一方有場地、一方有通路，可以互相補上。第二句不該出現在附言裡。",
    cards.F_RECIPROCITY: "雙方都能得到實際幫助。",
    cards.F_COLLAB: "先在穀倉辦一場小型市集試試看，詳情見 https://example.com/x 或 www.example.org",
    cards.F_CONFIRM: "市集預計辦在哪一個月份？",
    cards.F_RISK: "雙方時程可能不同步。",
}
THIN = {f: cards.INSUFFICIENT for f in cards.LLM_FIELDS}


def llm_with(fields):
    return lambda messages: json.dumps(fields, ensure_ascii=False)


class Message:
    def __init__(self, content="", actions=None, **_):
        self.content = content

    async def send(self):
        return self


async def settle(path):
    for _ in range(50):
        worker = task._ACTIVE.get(path)
        if worker is None:
            return
        await worker


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(task, "TASK_DIR", tmp_path)
    task._ACTIVE.clear()

    async def acall(args):
        return None

    def copilot(name, args):
        return SimpleNamespace(acall=lambda: acall(args))

    def judge_project(project, llm=None):
        return capability.judge(project["philosophy_text"], RAW[project["uuid"]])

    async def no_record(*a, **k):
        return None

    monkeypatch.setattr(task.cl, "CopilotFunction", copilot)
    monkeypatch.setattr(task.cl, "Message", Message)
    monkeypatch.setattr(handler, "judge_project", judge_project)
    monkeypatch.setattr(flow, "record_run", no_record)
    monkeypatch.setattr(flow, "record_action", no_record)
    path = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-235")
    return SimpleNamespace(path=path, rt=Runtime())


def run(coro):
    return asyncio.run(coro)


async def select(env, llm):
    await task.open_task(env.path, env.rt)
    await settle(env.path)
    t = task._load(env.path)
    await task.handle_event(env.path, env.rt, {"action": "select", "task_id": t["task_id"],
                                               "a": "a", "targets": TARGETS}, llm=llm,
                            identity={"issuer": "cms", "project": "sechome", "user_id": 7})
    await settle(env.path)
    t = task._load(env.path)
    assert t["status"] == "done", t.get("error")
    return t


async def confirm_and_send(env, t):
    """照面板流程：按「寄站內邀請」→ 確認框顯示附言 → 按「確定」送回同一段附言。"""
    card = t["cards"][0]
    shown = card["invite_message"]           # 確認框顯示的附言全文
    await task.handle_event(env.path, env.rt, {"task_id": t["task_id"], "action": "invite",
                                               "target": card["target"]})
    assert env.rt.invites() == []            # 未確認不寄
    await task.handle_event(env.path, env.rt, {"task_id": t["task_id"], "action": "invite",
                                               "target": card["target"], "confirmed": True,
                                               "message": shown})
    sent = env.rt.invites()
    assert len(sent) == 1
    return shown, sent[0][1]


def test_invite_carries_why_message_from_card(env):
    async def go():
        t = await select(env, llm_with(FULL))
        shown, args = await confirm_and_send(env, t)
        msg = args["message"]
        assert msg == shown                                   # 確認框文字＝送出的 message
        assert msg.startswith("大庄社區 想跟你合作：")
        assert "先在穀倉辦一場小型市集試試看" in msg
        assert "一方有場地、一方有通路，可以互相補上。" in msg
        assert "第二句" not in msg                            # 互補性只取第一句
        assert len(msg) <= 200
        assert not URL.search(msg) and "example" not in msg   # 不含網址
        assert args["project_uuid"] == "a" and args["target_project_uuid"] == t["cards"][0]["target"]
    run(go())


def test_all_insufficient_says_lets_talk(env):
    async def go():
        t = await select(env, llm_with(THIN))
        shown, args = await confirm_and_send(env, t)
        assert args["message"] == shown == "大庄社區 想跟你談談合作的可能"
    run(go())


def test_message_not_shown_is_not_sent(env):
    """面板沒回傳附言（或回傳的與卡上不同）→ 不附言，絕不寄出使用者沒看到的文字。"""
    async def go():
        t = await select(env, llm_with(FULL))
        card = t["cards"][0]
        await task.handle_event(env.path, env.rt, {"task_id": t["task_id"], "action": "invite",
                                                   "target": card["target"], "confirmed": True,
                                                   "message": "被竄改的附言 http://evil"})
        [(_, args, _)] = env.rt.invites()
        assert "message" not in args
    run(go())


@pytest.mark.parametrize("fields, expected", [
    ({cards.F_COLLAB: "一起辦市集。", cards.F_COMPLEMENT: "不足"}, "甲 想跟你合作：一起辦市集。"),
    ({cards.F_COLLAB: "不足", cards.F_COMPLEMENT: "場地加通路。還有別的"}, "甲 想跟你合作。場地加通路。"),
    ({cards.F_COLLAB: "Insufficient", cards.F_COMPLEMENT: ""}, "甲 想跟你談談合作的可能"),
    ({}, "甲 想跟你談談合作的可能"),
])
def test_message_skips_insufficient_fields(fields, expected):
    assert flow.invite_message("甲", fields) == expected


def test_message_is_capped_at_200_and_has_no_links():
    long = {cards.F_COLLAB: "共同經營" * 80 + " https://a.b/c", cards.F_COMPLEMENT: "互補" * 80 + "。"}
    msg = flow.invite_message("很長的專案名稱" * 3, long)
    assert len(msg) <= 200 and not URL.search(msg)
    assert msg.startswith("很長的專案名稱很長的專案名稱很長的專案名稱 想跟你合作：共同經營")
    assert "互補" in msg


def test_panel_dialog_shows_and_sends_the_same_message():
    """面板：確認框列出 card.invite_message 全文，按「確定」送回的就是同一段。"""
    js = (ROOT / "public/tangle/match-cards.js").read_text(encoding="utf-8")
    body = js[js.index("function confirmInvite"):js.index("function stateLine")]
    assert "card.invite_message" in body and "data-invite-message" in body
    assert "quote.textContent = message" in body
    assert re.search(r"send\('invite', message \? \{target: card\.target, confirmed: true, message\}", body)
