"""#201 補問回答寫回 philosophy：AI 詢問、同意才附加，只寫自己可管理的案。

假 runtime（不碰 CMS）、假 asyncpg 連線（只記 INSERT），驗：
(a) 使用者拒絕 → 不呼叫寫入工具
(b) 同意 → 呼叫一次，內容＝原文＋附加段＋來源標註，原文不變
(c) 對方專案（不在 list_my_projects）不詢問、不寫
(d) 結果寫入媒合紀錄
"""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from app.matching import chunks as chk
from app.matching import writeback as wb

TODAY = dt.date(2026, 11, 23)
NOTE = "（2026-11-23 補充，經 AI-Eva 媒合補問）"
MINE, THEIRS = "p-mine", "p-theirs"
ORIGINAL = "我們在雲林經營社區農場。希望找到行銷夥伴。"
Q = "你們目前可以提供哪些具體資源？"
A = "我們每月可提供 200 公斤有機米，並開放場地辦理食農體驗。"


class FakeRuntime:
    def __init__(self, mine=(MINE,), philosophy=None, append_result=None, list_result=None):
        self.mine = list(mine)
        self.philosophy = dict(philosophy or {MINE: ORIGINAL, THEIRS: "對方的計畫理念。"})
        self.append_result = append_result
        self.list_result = list_result
        self.calls: list[tuple[str, dict, bool]] = []

    def count(self, name):
        return sum(1 for n, _, _ in self.calls if n == name)

    async def execute(self, name, args, *, confirmed=False):
        self.calls.append((name, dict(args), confirmed))
        if name == "list_my_projects":
            if self.list_result is not None:
                return self.list_result
            return {"status": "ok", "result": {"data": {"projects": list(self.mine)}}}
        if name == "get_project_info":
            return {"status": "ok", "result": {"data": {"uuid": args["uuid"], "philosophy": self.philosophy.get(args["uuid"], "")}}}
        if name == "append_philosophy":
            if not confirmed:
                return {"status": "need_confirm", "tool": name}
            if self.append_result is not None:
                return self.append_result
            u = args["uuid"]
            self.philosophy[u] = self.philosophy[u] + "\n\n" + args["supplement"]
            return {"status": "ok", "result": {"data": {"uuid": u}}}
        return {"status": "denied", "reason": f"tool '{name}' not in manifest"}


class FakeConn:
    """asyncpg 風格：只記錄 INSERT，回 RETURNING id。"""

    def __init__(self):
        self.rows: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.rows.append((sql, args))
        return {"id": len(self.rows)}

    def table(self, name):
        return [args for sql, args in self.rows if f"matching.{name}" in sql]


class Asker:
    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[str] = []

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def run(coro):
    return asyncio.run(coro)


def offer(rt, uuid, reply, conn=None, **kw):
    ask = Asker(reply)
    out = run(wb.offer_writeback(rt, uuid=uuid, question=Q, answer=A, ask=ask, conn=conn,
                                 run_id=7 if conn is not None else None, today=TODAY, **kw))
    return out, ask


# ── (a) 拒絕 → 不寫 ──────────────────────────────────────────────────

@pytest.mark.parametrize("reply", ["不要", "先不用，謝謝", "no", False, "", "嗯…再看看"])
def test_declined_does_not_call_write_tool(reply):
    rt = FakeRuntime()
    out, ask = offer(rt, MINE, reply)
    assert ask.prompts == [wb.ASK_PROMPT]
    assert out["result"] == wb.DECLINED and out["asked"] is True
    assert rt.count("append_philosophy") == 0
    assert rt.philosophy[MINE] == ORIGINAL


# ── (b) 同意 → 寫一次，原文＋附加段＋來源標註 ──────────────────────────

@pytest.mark.parametrize("reply", ["要", "好，寫回吧", "可以", "同意", "OK", True])
def test_consent_appends_once_with_source_note(reply):
    rt = FakeRuntime()
    out, ask = offer(rt, MINE, reply, philosophy=ORIGINAL)
    assert ask.prompts == [wb.ASK_PROMPT]
    assert out["result"] == wb.OK
    writes = [(a, c) for n, a, c in rt.calls if n == "append_philosophy"]
    assert len(writes) == 1
    args, confirmed = writes[0]
    assert confirmed is True
    assert set(args) == {"uuid", "supplement"}  # CMS manifest 參數；只附加、沒有覆寫欄位
    assert args["uuid"] == MINE
    assert args["supplement"] == A + NOTE
    expected = ORIGINAL + "\n\n" + A + NOTE
    assert out["philosophy"] == expected
    assert out["philosophy"].startswith(ORIGINAL)  # 原文不變
    assert rt.philosophy[MINE] == expected


def test_consent_reads_original_when_not_given():
    rt = FakeRuntime()
    out, _ = offer(rt, MINE, "要")
    assert out["philosophy"] == ORIGINAL + "\n\n" + A + NOTE
    assert rt.count("get_project_info") == 1


def test_helpers():
    assert wb.source_note(TODAY) == NOTE
    assert wb.appended(ORIGINAL, "補充", TODAY) == ORIGINAL + "\n\n補充" + NOTE
    assert wb.appended("", "補充", TODAY) == "補充" + NOTE
    assert wb.parse_consent("要") and not wb.parse_consent("不要")


# ── (c) 對方專案 → 不問、不寫 ─────────────────────────────────────────

def test_other_project_not_asked_not_written():
    rt = FakeRuntime()
    out, ask = offer(rt, THEIRS, "要")
    assert out["result"] == wb.NOT_MANAGEABLE and out["asked"] is False
    assert ask.prompts == []
    assert rt.count("append_philosophy") == 0
    assert rt.count("list_my_projects") == 1


def test_list_failure_treated_as_not_manageable():
    rt = FakeRuntime(list_result={"status": "error", "reason": "forbidden by source backend (403)"})
    out, ask = offer(rt, MINE, "要")
    assert out["result"] == wb.NOT_MANAGEABLE
    assert ask.prompts == [] and rt.count("append_philosophy") == 0


def test_list_with_dict_items():
    rt = FakeRuntime(list_result={"status": "ok", "result": {"data": {"projects": [{"uuid": MINE}]}}})
    out, _ = offer(rt, MINE, "要", philosophy=ORIGINAL)
    assert out["result"] == wb.OK


# ── (d) 結果寫入媒合紀錄 ─────────────────────────────────────────────

def _event_payload(conn):
    import json
    events = conn.table("events")
    assert len(events) == 1
    run_id, kind, target, _actor, payload = events[0]
    assert run_id == 7 and kind == "status" and target is not None
    p = json.loads(payload)
    assert p["type"] == wb.EVENT_TYPE
    return target, p


def test_record_success():
    conn, rt = FakeConn(), FakeRuntime()
    out, _ = offer(rt, MINE, "要", conn=conn, philosophy=ORIGINAL)
    answers = conn.table("answers")
    assert answers == [(7, MINE, Q, A, True)]
    target, p = _event_payload(conn)
    assert target == MINE and p["result"] == "ok"
    assert p["old_hash"] == chk.content_hash(ORIGINAL)
    assert p["new_hash"] == chk.content_hash(out["philosophy"]) != p["old_hash"]


def test_record_declined():
    conn, rt = FakeConn(), FakeRuntime()
    offer(rt, MINE, "不要", conn=conn)
    assert conn.table("answers") == [(7, MINE, Q, A, False)]
    assert _event_payload(conn)[1]["result"] == "declined"


def test_record_failure():
    conn = FakeConn()
    rt = FakeRuntime(append_result={"status": "error", "reason": "forbidden by source backend (403)"})
    out, _ = offer(rt, MINE, "要", conn=conn, philosophy=ORIGINAL)
    assert out["result"] == wb.ERROR
    assert conn.table("answers") == [(7, MINE, Q, A, True)]
    p = _event_payload(conn)[1]
    assert p["result"] == "error" and "403" in p["reason"]


def test_record_tool_missing_from_manifest():
    class NoTool(FakeRuntime):
        async def execute(self, name, args, *, confirmed=False):
            if name == "append_philosophy":
                self.calls.append((name, dict(args), confirmed))
                return {"status": "denied", "reason": "tool 'append_philosophy' not in manifest"}
            return await super().execute(name, args, confirmed=confirmed)

    conn, rt = FakeConn(), NoTool()
    out, _ = offer(rt, MINE, "要", conn=conn, philosophy=ORIGINAL)
    assert out["result"] == wb.ERROR
    assert _event_payload(conn)[1]["result"] == "error"


def test_record_other_project_answer_kept_without_writeback():
    conn, rt = FakeConn(), FakeRuntime()
    offer(rt, THEIRS, "要", conn=conn)
    assert conn.table("answers") == [(7, THEIRS, Q, A, False)]
    assert _event_payload(conn)[1]["result"] == "not_manageable"


# ── 寫回後雜湊改變 → 重跑判斷 ─────────────────────────────────────────

def test_hash_change_triggers_rerun():
    calls = []

    def analyzer(p):
        calls.append(p)
        return {"capabilities": {}}

    store = chk.MemoryStore()
    chk.ensure_chunks(MINE, ORIGINAL, store, analyzer=analyzer)
    rt = FakeRuntime()
    out, _ = offer(rt, MINE, "要", philosophy=ORIGINAL, store=store, analyzer=analyzer)
    assert out["recomputed"] is True
    assert calls == [ORIGINAL, out["philosophy"]]
    assert store[MINE]["hash"] == chk.content_hash(out["philosophy"])
