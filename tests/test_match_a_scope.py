"""#217：媒合面板的 A 只列本站可發起媒合的案（list_match_initiable_projects）。

- A 選項＝initiable 清單；對象選項＝list_my_projects 扣掉所選 A。
- 本站的案排最前面，不被 LIST_LIMIT（20）截掉。
- 送出 A 不在 initiable 內 → 被拒。
- initiable 工具不存在（舊版 CMS）或回 0 案 → 錯誤訊息，不退回 list_my_projects。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.apps.match_analysis import handler, task

INITIABLE = handler.INITIABLE_TOOL


class CMS:
    """假 CMS runtime：和正式 ToolRuntime 一樣有 manifest（is_allowed），白名單外回 denied。"""

    def __init__(self, mine, initiable, *, has_tool=True):
        self.mine, self.initiable = list(mine), list(initiable)
        self.tools = {"list_my_projects", "get_project_info"} | ({INITIABLE} if has_tool else set())
        self.calls = []

    def is_allowed(self, name):
        return name in self.tools

    async def execute(self, name, args, confirmed=False):
        self.calls.append(name)
        if name not in self.tools:
            return {"status": "denied", "reason": f"tool '{name}' not in manifest"}
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": self.mine}}}
        if name == INITIABLE:
            items = [{"uuid": u, "name": f"本站 {u}"} for u in self.initiable]
            return {"status": "ok", "result": {"data": {"count": len(items), "items": items}}}
        return {"status": "ok", "result": {"data": {"name": f"專案 {args['uuid']}", "philosophy": ""}}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(task, "TASK_DIR", tmp_path)
    task._ACTIVE.clear()
    pushes = []

    async def acall(args):
        pushes.append(args)

    monkeypatch.setattr(task.cl, "CopilotFunction",
                        lambda name, args: SimpleNamespace(acall=lambda: acall(args)))
    path = task.scope_path({"issuer": "cms", "project": "dev", "user_id": 1}, "thread-217")
    return SimpleNamespace(path=path, pushes=pushes)


async def _settle(path):
    for _ in range(50):
        worker = task._ACTIVE.get(path)
        if worker is None:
            return
        await worker


def _open(env, cms):
    async def go():
        await task.open_task(env.path, cms)
        await _settle(env.path)
        return task._load(env.path)
    return asyncio.run(go())


def a_options(t):
    """面板 A 下拉的選項（與 match-task.js 同規則）。"""
    return [p["uuid"] for p in t["projects"] if p["uuid"] in set(t["initiable"])]


def target_options(t, a):
    return [p["uuid"] for p in t["projects"] if p["uuid"] != a]


def test_a_options_are_initiable_targets_are_my_projects(env):
    mine = ["p1", "p2", "p3", "p4", "p5"]
    t = _open(env, CMS(mine, ["p4", "p2"]))
    assert t["status"] == "select", t["error"]
    assert sorted(a_options(t)) == ["p2", "p4"]
    assert sorted(target_options(t, "p4")) == ["p1", "p2", "p3", "p5"]
    assert sorted(p["uuid"] for p in t["projects"]) == mine


def test_site_projects_not_cut_by_list_limit(env):
    assert handler.LIST_LIMIT == 20
    mine = [f"p{i:02d}" for i in range(1, 31)]
    site = ["p28", "p30"]                      # 第 28、30 案
    t = _open(env, CMS(mine, site))
    assert t["status"] == "select", t["error"]
    uuids = [p["uuid"] for p in t["projects"]]
    assert uuids[:2] == site                   # 本站的案排最前面
    assert len(uuids) == handler.LIST_LIMIT    # 其餘補到上限
    assert sorted(a_options(t)) == site
    assert "p30" in target_options(t, "p28") and "p28" in target_options(t, "p30")


def test_select_a_outside_initiable_is_rejected(env):
    cms = CMS(["p1", "p2", "p3", "p4", "p5"], ["p1", "p2"])
    t = _open(env, cms)

    async def go(a, targets):
        await task.handle_event(env.path, cms, {"action": "select", "task_id": t["task_id"],
                                                "a": a, "targets": targets})
        return task._load(env.path)

    after = asyncio.run(go("p3", ["p1", "p2"]))
    assert after["status"] == "select" and after["error"]
    assert after["a"] is None
    assert task._validate(t, "p3", ["p1", "p2"])
    assert task._validate(t, "p1", ["p2", "p3"]) is None
    assert task._validate(t, "p1", ["p3", "p4"]) is None


@pytest.mark.parametrize("cms", [
    CMS(["p1", "p2", "p3", "p4", "p5"], [], has_tool=False),   # 舊版 CMS 沒這個工具
    CMS(["p1", "p2", "p3", "p4", "p5"], []),                   # 工具在，但本站 0 案
], ids=["tool-missing", "zero-initiable"])
def test_no_initiable_is_error_without_fallback(env, cms):
    t = _open(env, cms)
    assert t["status"] == "error"
    assert "還沒有可以發起媒合的專案" in t["error"]
    assert t["projects"] == [] and t["initiable"] == []
    assert "list_my_projects" not in cms.calls           # 不退回用 list_my_projects 當 A
    assert task._validate(t, "p1", ["p2", "p3"])          # 也無法硬送 select
    assert env.pushes and env.pushes[-1]["matchTask"]["status"] == "error"


def test_initiable_read_failure_is_reported_not_as_zero(env):
    cms = CMS(["p1", "p2", "p3"], ["p1"])

    async def broken(name, args, confirmed=False):
        return {"status": "error", "reason": "HTTP 500"}

    cms.execute = broken
    t = _open(env, cms)
    assert t["status"] == "error" and "讀取專案清單失敗" in t["error"]
