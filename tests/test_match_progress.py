"""#232 等待不僵住：判斷中逐案推送進度、清單先出名稱。

假 runtime：每案讀取 0.2 秒、判斷 0.2 秒；A + 4 個對象。
"""
import asyncio
import time
from types import SimpleNamespace

import pytest

from app.apps.match_analysis import handler, task
from app.matching import capability

FETCH_S = JUDGE_S = 0.2
IDS = ["a", "b", "c", "d", "e"]
NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊", "d": "導覽協會", "e": "漁村工作室"}
PHIL = {
    "a": "我們的社區有閒置穀倉可以提供場地，也需要行銷通路協助販售農產品。",
    "b": "合作社有通路可以協助販售，需要場地辦理市集。",
    "c": "青年團隊需要行銷通路，想找人一起開發。",
    "d": "協會可以提供導覽人才。",
    "e": "工作室需要場地辦理活動。",
}
RAW = {
    "a": {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
          "B7": [{"quote": "需要行銷通路協助販售農產品", "kind": "aim"}]},
    "b": {"B7": [{"quote": "有通路可以協助販售", "kind": "concrete"}],
          "B1": [{"quote": "需要場地辦理市集", "kind": "aim"}]},
    "c": {"B7": [{"quote": "需要行銷通路", "kind": "aim"}]},
    "d": {"B5": [{"quote": "可以提供導覽人才", "kind": "concrete"}]},
    "e": {"B1": [{"quote": "需要場地辦理活動", "kind": "aim"}]},
}


class SlowCMS:
    """list_my_projects 帶名稱（{uuid, name}）；get_project_info 每案 0.2 秒。"""

    def __init__(self, named=True):
        self.named = named
        self.calls = []

    async def execute(self, name, args):
        self.calls.append(name)
        if name == "list_my_projects":
            projects = [{"uuid": u, "name": NAMES[u]} for u in IDS] if self.named else list(IDS)
            return {"status": "ok", "result": {"data": {"projects": projects}}}
        await asyncio.sleep(FETCH_S)
        u = args["uuid"]
        return {"status": "ok", "result": {"data": {"name": NAMES[u], "philosophy": f"<p>{PHIL[u]}</p>"}}}


class RealShapeCMS(SlowCMS):
    """正式 CMS 的形狀：list_my_projects 只回 uuid，list_match_initiable_projects 回 {uuid, name}。"""

    def __init__(self):
        super().__init__(named=False)

    def is_allowed(self, tool):
        return True

    async def execute(self, name, args):
        if name == handler.INITIABLE_TOOL:
            self.calls.append(name)
            return {"status": "ok", "result": {"data": {"items": [{"uuid": "a", "name": NAMES["a"]}]}}}
        return await super().execute(name, args)


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
    pushes = []

    async def acall(args):
        pushes.append({**args, "at": time.monotonic()})

    def copilot(name, args):
        return SimpleNamespace(acall=lambda: acall(args))

    def judge_project(project, llm=None):
        time.sleep(JUDGE_S)
        return capability.judge(project["philosophy_text"], RAW[project["uuid"]])

    monkeypatch.setattr(task.cl, "CopilotFunction", copilot)
    monkeypatch.setattr(task.cl, "Message", Message)
    monkeypatch.setattr(handler, "judge_project", judge_project)
    path = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-232")
    return SimpleNamespace(path=path, pushes=pushes)


def run(coro):
    return asyncio.run(coro)


def states(pushes):
    return [p["matchTask"] for p in pushes]


# ── 1. 判斷中逐案推送，progress 每次都長大 ─────────────────────────

def test_running_pushes_every_fetch_and_judge(env):
    async def go():
        cms = SlowCMS()
        await task.open_task(env.path, cms)
        await settle(env.path)
        t = task._load(env.path)
        assert t["status"] == "select"
        env.pushes.clear()
        await task.handle_event(env.path, cms, {"action": "select", "task_id": t["task_id"],
                                               "a": "a", "targets": ["b", "c", "d", "e"]}, llm=object())
        await settle(env.path)
        return task._load(env.path)

    done = run(go())
    assert done["status"] == "done", done.get("error")
    running = [s for s in states(env.pushes) if s["status"] == "running"]
    # A + 4 個對象：讀 5 次＋判 5 次，判斷中至少推 8 次
    assert len(running) >= 8, len(running)
    sizes = [len(s["progress"]) for s in running]
    assert all(b > a for a, b in zip(sizes, sizes[1:])), sizes
    steps = [s["progress"][-1]["step"] for s in running[1:]]
    assert steps.count("fetch") == 5 and steps.count("judge") == 5, steps
    # 推送間隔不超過一案的處理時間太多（等待不僵住）
    times = [p["at"] for p in env.pushes if p["matchTask"]["status"] == "running"]
    assert max(b - a for a, b in zip(times, times[1:])) < 1.0
    # 判斷中帶星圖預覽：讀到的案先出現，判完的亮起（judged）
    previews = [s.get("preview") for s in running[1:]]
    assert all(previews)
    counts = [len(p["projects"]) for p in previews]
    assert counts == sorted(counts) and counts[0] == 1 and counts[-1] == 5
    assert previews[0]["projects"][0]["pid"] == "a"
    lit = [sum(1 for x in p["projects"] if x["judged"]) for p in previews]
    assert lit == sorted(lit) and lit[-1] == 5
    # 完成後不留預覽，最後一包是 done
    assert "preview" not in done
    assert states(env.pushes)[-1]["status"] == "done"


# ── 2. 清單先出名稱 ─────────────────────────────────────────────────

def test_list_first_publish_has_all_names(env):
    async def go():
        cms = SlowCMS()
        await task.open_task(env.path, cms)
        await settle(env.path)
        return cms

    cms = run(go())
    listed = [s for p, s in zip(env.pushes, states(env.pushes)) if "update" in p]
    assert listed, "清單沒有推送"
    first = listed[0]
    assert first["status"] == "select"
    assert {p["uuid"]: p["name"] for p in first["projects"]} == NAMES
    assert "get_project_info" not in cms.calls      # 名稱來自清單工具，不必逐案讀


def test_list_real_shape_names_first_then_fill(env):
    async def go():
        cms = RealShapeCMS()
        await task.open_task(env.path, cms)
        await settle(env.path)
        return task._load(env.path)

    final = run(go())
    listed = [s for p, s in zip(env.pushes, states(env.pushes)) if "update" in p]
    first = listed[0]
    # 第一包就有 list_match_initiable_projects 給的名稱，背景補齊中
    assert [p["name"] for p in first["projects"]] == [NAMES["a"]]
    assert first["listing"] is True
    # 之後每補一案推一次，名單只增不減
    sizes = [len(s["projects"]) for s in listed]
    assert sizes == sorted(sizes) and sizes[-1] == 5
    assert final["status"] == "select" and final["listing"] is False
    assert {p["uuid"]: p["name"] for p in final["projects"]} == NAMES
    assert [p["uuid"] for p in final["projects"]][0] == "a"
