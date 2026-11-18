import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.apps.regulation_check import task


class CMS:
    def __init__(self):
        self.allowed = ["p1"]
        self.calls = []

    async def execute(self, name, args):
        self.calls.append((name, args))
        data = {"projects": self.allowed} if name == "list_my_projects" else {
            "name": "測試計畫", "philosophy": "<p>計畫理念</p>" * 30,
        }
        return {"status": "ok", "result": {"data": data}}


def setup_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task, "TASK_DIR", tmp_path)
    calls = []

    async def acall(args):
        calls.append(args)

    def copilot(name, args):
        assert name == "tangle_workspace"
        return SimpleNamespace(acall=lambda: acall(args))

    session = SimpleNamespace(set=lambda *_: None)
    monkeypatch.setattr(task.cl, "CopilotFunction", copilot)
    monkeypatch.setattr(task.cl, "user_session", session)
    path = task.scope_path({"issuer": "cms", "tenant_id": "a", "user_id": 1}, "chat-a")
    return path, calls


def test_task_full_lifecycle_and_original_attachment(monkeypatch, tmp_path):
    path, pushes = setup_task(monkeypatch, tmp_path)
    cms = CMS()
    messages = []

    class Message:
        def __init__(self, content, elements=None):
            self.content, self.elements, self.id = content, elements, "chat-message"

        async def send(self):
            messages.append(self)
            return self

    async def check(plan, category, *, model, on_progress):
        assert len(plan) >= 100 and "<p>" not in plan
        assert category == "農村再生" and model == "model"
        await on_progress({"domain": "土地", "total": 1, "hit": 0, "elapsed": 1})
        ready.set()
        await release.wait()
        return {"findings": [], "coverage": {"evaluated": 1, "domains": ["土地"]}, "elapsed": 2}

    from chainlit.context import context_var
    run_check = AsyncMock(side_effect=check)
    notify = AsyncMock()
    monkeypatch.setattr(task.cl, "Message", Message)
    monkeypatch.setattr(task.handler.judge, "run_check", run_check)
    monkeypatch.setattr(task.handler.report, "build", lambda *_, **__: "# 原始報告\n")
    monkeypatch.setattr(task.handler, "notify_result", notify)

    async def run():
        nonlocal release, ready
        release, ready = asyncio.Event(), asyncio.Event()
        await task.open_task(path, cms)
        await task._ACTIVE[path]
        current = task._load(path)
        assert current["status"] == "select"
        assert current["projects"] == [{"uuid": "p1", "name": "測試計畫"}]
        assert pushes[0].get("update") is None and pushes[-1]["update"] is True

        async def event(action, uuid=None, task_id=current["task_id"]):
            await task.handle_event(path, cms, {"action": action, "task_id": task_id, "uuid": uuid}, "model")

        await event("select", "invalid")
        assert task._load(path)["status"] == "select"
        await event("select", "p1", "stale-task")
        assert task._load(path)["status"] == "select"
        await event("select", "p1")
        worker = task._ACTIVE[path]
        await event("select", "p1")
        context_var.set(SimpleNamespace(session=SimpleNamespace(thread_id="resumed-chat")))
        await event("get")
        await event("new")
        await task.open_task(path, cms)
        assert task._load(path)["task_id"] == current["task_id"]
        await asyncio.wait_for(ready.wait(), 2)
        assert task._load(path)["progress"][0]["domain"] == "土地"
        release.set()
        await worker
        done = task._load(path)
        assert done["status"] == "done"
        attachment = done["result"]["attachment"]
        assert attachment == {"message_id": "chat-message", "name": messages[1].elements[0].name}
        assert messages[1].elements[0].content.decode() == "# 原始報告\n"
        assert messages[1].elements[0].mime == "text/markdown"
        assert messages[1].elements[0].thread_id == "resumed-chat"
        await task.open_task(path, cms)
        assert task._load(path) == done
        run_check.assert_awaited_once()
        notify.assert_awaited_once()
        await event("new")
        await task._ACTIVE[path]
        assert task._load(path)["task_id"] != current["task_id"]
        assert task._load(path)["status"] == "select"

    release = ready = None
    asyncio.run(run())


def test_task_scope_restart_and_revoked_cms_permission(monkeypatch, tmp_path):
    path, pushes = setup_task(monkeypatch, tmp_path)
    identity = {"issuer": "cms", "tenant_id": "a", "user_id": 1}
    assert path != task.scope_path(identity, "chat-b")
    assert path != task.scope_path({**identity, "tenant_id": "b"}, "chat-a")
    assert path != task.scope_path({**identity, "user_id": 2}, "chat-a")
    cms = CMS()
    check = AsyncMock()
    monkeypatch.setattr(task.handler.judge, "run_check", check)

    async def run():
        await task.open_task(path, cms)
        await task._ACTIVE[path]
        task_id = task._load(path)["task_id"]
        push_count = len(pushes)
        await task.handle_event(task.scope_path(identity, "chat-b"), cms,
                                {"action": "get", "task_id": task_id}, None)
        assert len(pushes) == push_count
        cms.allowed = []
        await task.handle_event(path, cms, {"action": "select", "task_id": task_id, "uuid": "p1"}, None)
        await task._ACTIVE[path]
        assert task._load(path)["status"] == "error"
        assert "無法管理" in task._load(path)["error"]
        task._save(path, {**task._load(path), "status": "running"})
        await task.open_task(path, cms)
        assert task._load(path)["task_id"] == task_id
        assert "已中斷" in task._load(path)["error"]
        check.assert_not_awaited()

    asyncio.run(run())
