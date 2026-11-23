"""ai-eva#213：進入 AI 秘書時提醒媒合邀請（讀 CMS list_my_match_invites，不存副本）。"""
import asyncio
import builtins
import os
import sqlite3

import pytest

from app.matching import invites
from app.matching.invites import TOOL_NAME, build_invite_reminder


class FakeRuntime:
    def __init__(self, result=None, *, tools=(TOOL_NAME,), raises=None):
        self._result = result
        self._tools = set(tools)
        self._raises = raises
        self.calls = []

    def is_allowed(self, name):
        return name in self._tools

    async def execute(self, name, args, **kw):
        self.calls.append((name, args))
        if name not in self._tools:
            return {"status": "denied", "reason": "not in manifest"}
        if self._raises:
            raise self._raises
        return self._result


TWO = {"status": "ok", "result": {"success": True, "data": {"invites": [
    {"id": 1, "from_project_name": "雲林海口共好計畫", "created_at": "2026-11-20 10:00", "status": "pending"},
    {"id": 2, "from_project_name": "麥寮食農教育", "created_at": "2026-11-22 15:30"},
    {"id": 3, "from_project_name": "已回覆的專案", "created_at": "2026-11-01", "status": "accepted"},
]}}}


def run(coro):
    return asyncio.run(coro)


def test_two_invites_reminder_has_count_and_projects():
    rt = FakeRuntime(TWO)
    r = run(build_invite_reminder(rt, lang="zh-TW"))
    assert r is not None and r.count == 2
    assert "2 個媒合邀請" in r.content
    assert "雲林海口共好計畫" in r.content and "麥寮食農教育" in r.content
    assert "2026-11-20 10:00" in r.content
    assert "已回覆的專案" not in r.content
    assert rt.calls == [(TOOL_NAME, {})]


def test_plain_list_payload_also_works():
    rt = FakeRuntime({"status": "ok", "result": [
        {"project_name": "A 專案", "created_at": "2026-11-21"},
        {"project": {"name": "B 專案"}, "invited_at": "2026-11-22"},
    ]})
    r = run(build_invite_reminder(rt, lang="zh"))
    assert r.count == 2 and "A 專案" in r.content and "B 專案" in r.content


def test_zero_invites_no_reminder():
    rt = FakeRuntime({"status": "ok", "result": {"success": True, "data": {"invites": []}}})
    assert run(build_invite_reminder(rt, lang="zh")) is None


@pytest.mark.parametrize("rt", [
    FakeRuntime(TWO, tools=()),                                   # 工具不存在（manifest 沒給）
    FakeRuntime(TWO, raises=RuntimeError("boom")),               # 呼叫拋錯
    FakeRuntime({"status": "error", "reason": "HTTP 500"}),      # CMS 回錯
    FakeRuntime({"status": "ok", "result": "garbage"}),          # 看不懂的格式
    None,                                                        # 沒有 runtime
])
def test_missing_or_failing_tool_is_silent(rt):
    assert run(build_invite_reminder(rt, lang="zh")) is None


def test_runtime_without_is_allowed_denied_is_silent():
    class Bare:
        async def execute(self, name, args, **kw):
            return {"status": "denied", "reason": "not in manifest"}
    assert run(build_invite_reminder(Bare(), lang="zh")) is None


def test_japanese_reminder():
    r = run(build_invite_reminder(FakeRuntime(TWO), lang="ja"))
    assert r.lang == "ja"
    assert "マッチング招待が 2 件" in r.content
    assert "雲林海口共好計畫" in r.content
    assert "媒合邀請" not in r.content
    assert invites.text("action", "ja") != invites.text("action", "zh")


def test_lang_defaults_to_current_lang(monkeypatch):
    monkeypatch.setattr(invites, "current_lang", lambda: "en")
    r = run(build_invite_reminder(FakeRuntime(TWO)))
    assert r.lang == "en" and "2 match invitation" in r.content


def test_no_local_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real_open = builtins.open

    def guarded_open(file, mode="r", *a, **kw):
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"unexpected write to {file}")
        return real_open(file, mode, *a, **kw)

    def no_sqlite(*a, **kw):
        raise AssertionError("unexpected sqlite connect")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(sqlite3, "connect", no_sqlite)
    for rt in (FakeRuntime(TWO), FakeRuntime({"status": "ok", "result": []}),
               FakeRuntime(TWO, raises=RuntimeError("x"))):
        run(build_invite_reminder(rt, lang="ja"))
    assert os.listdir(tmp_path) == []
    # 不在模組上留快取：每次都重讀 CMS
    rt = FakeRuntime(TWO)
    run(build_invite_reminder(rt, lang="zh"))
    run(build_invite_reminder(rt, lang="zh"))
    assert len(rt.calls) == 2
