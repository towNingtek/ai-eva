"""媒合星球整合（ai-eva #203）：對話任務生命週期、只判一次、新任務才換 ID、按租戶開關。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.apps.match_analysis import handler, task
from app.matching import capability

PHIL = {
    "a": "我們的社區有閒置穀倉可以提供場地，也需要行銷通路協助販售農產品。",
    "b": "合作社有通路可以協助販售，需要場地辦理市集。",
    "c": "青年團隊需要行銷通路，想找人一起開發。",
    "d": "協會可以提供導覽人才。",
}
# 每案 B1–B8 的假判斷（quote 都是 PHIL 的逐字子字串，走真的 capability.judge 驗證）
RAW = {
    "a": {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
          "B7": [{"quote": "需要行銷通路協助販售農產品", "kind": "aim"}]},
    "b": {"B7": [{"quote": "有通路可以協助販售", "kind": "concrete"}],
          "B1": [{"quote": "需要場地辦理市集", "kind": "aim"}]},
    "c": {"B7": [{"quote": "需要行銷通路", "kind": "aim"}]},
    "d": {"B5": [{"quote": "可以提供導覽人才", "kind": "concrete"}]},
}
NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊", "d": "導覽協會"}


class CMS:
    def __init__(self, allowed=("a", "b", "c", "d")):
        self.allowed = list(allowed)
        self.calls = []

    async def execute(self, name, args):
        self.calls.append((name, args))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": self.allowed}}}
        u = args["uuid"]
        return {"status": "ok", "result": {"data": {"name": NAMES[u], "philosophy": f"<p>{PHIL[u]}</p>"}}}


class Message:
    sent = []

    def __init__(self, content="", actions=None, **_):
        self.content, self.actions = content, actions

    async def send(self):
        Message.sent.append(self)
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
    Message.sent = []
    pushes, judged = [], []

    async def acall(args):
        pushes.append(args)

    def copilot(name, args):
        assert name == "tangle_workspace"
        return SimpleNamespace(acall=lambda: acall(args))

    def judge_project(project, llm=None):
        judged.append(project["uuid"])
        return capability.judge(project["philosophy_text"], RAW[project["uuid"]])

    monkeypatch.setattr(task.cl, "CopilotFunction", copilot)
    monkeypatch.setattr(task.cl, "Message", Message)
    monkeypatch.setattr(handler, "judge_project", judge_project)
    path = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-1")
    return SimpleNamespace(path=path, pushes=pushes, judged=judged, cms=CMS())


def run(coro):
    return asyncio.run(coro)


async def _open_and_select(env, targets=("b", "c")):
    await task.open_task(env.path, env.cms)
    await settle(env.path)
    t = task._load(env.path)
    assert t["status"] == "select"
    assert [p["uuid"] for p in t["projects"]] == ["a", "b", "c", "d"]
    await task.handle_event(env.path, env.cms, {"action": "select", "task_id": t["task_id"],
                                                "a": "a", "targets": list(targets)}, llm=object())
    await settle(env.path)
    return task._load(env.path)


# ── 1. 同一對話重入同一任務，判斷只執行一次 ─────────────────────────

def test_reenter_same_thread_reuses_task_and_judges_once(env):
    async def go():
        done = await _open_and_select(env)
        assert done["status"] == "done"
        assert sorted(env.judged) == ["a", "b", "c"]          # A + 2 個對象各判一次
        first_id = done["task_id"]

        # 同一對話再點工具區按鈕兩次：接回原任務、不重跑
        await task.open_task(env.path, env.cms)
        await task.open_task(env.path, env.cms)
        await settle(env.path)
        again = task._load(env.path)
        assert again["task_id"] == first_id and again["status"] == "done"
        assert sorted(env.judged) == ["a", "b", "c"]
        assert again["result"] == done["result"]

        # 重入時推給面板的就是原任務的快照（opening 不帶 update）
        opening = [p for p in env.pushes if "update" not in p]
        assert len(opening) == 3
        assert all(p["mode"] == "match" and p["v"] == task.LIVE_VERSION for p in env.pushes)
        assert opening[-1]["matchTask"]["task_id"] == first_id
        assert opening[-1]["matchTask"]["status"] == "done"

        # get / 重複 select 也不重跑
        await task.handle_event(env.path, env.cms, {"action": "get"})
        await task.handle_event(env.path, env.cms, {"action": "select", "task_id": first_id,
                                                    "a": "a", "targets": ["c", "d"]})
        await settle(env.path)
        assert sorted(env.judged) == ["a", "b", "c"]
        assert task._load(env.path)["targets"] == ["b", "c"]
    run(go())


def test_double_select_claims_once(env):
    async def go():
        await task.open_task(env.path, env.cms)
        await settle(env.path)
        tid = task._load(env.path)["task_id"]
        ev = {"action": "select", "task_id": tid, "a": "a", "targets": ["b", "c"]}
        await asyncio.gather(task.handle_event(env.path, env.cms, ev),
                             task.handle_event(env.path, env.cms, dict(ev)))
        await settle(env.path)
        assert sorted(env.judged) == ["a", "b", "c"]
    run(go())


def test_different_thread_is_a_different_task(env):
    other = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-2")
    assert other != env.path
    assert task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-1") == env.path


# ── 2. 明確新任務才換 ID ─────────────────────────────────────────────

def test_only_explicit_new_changes_id(env):
    async def go():
        done = await _open_and_select(env)
        first_id = done["task_id"]
        # 舊分頁帶錯 task_id 的 new：不換
        await task.handle_event(env.path, env.cms, {"action": "new", "task_id": "stale"})
        assert task._load(env.path)["task_id"] == first_id
        # 說明事件不換 ID、不重判
        await task.handle_event(env.path, env.cms, {"action": "explain", "task_id": first_id,
                                                    "code": "B7", "pa": "a", "pb": "b"})
        assert task._load(env.path)["task_id"] == first_id
        assert sorted(env.judged) == ["a", "b", "c"]
        # 明確「開始新媒合」：換 ID，回到選擇
        await task.handle_event(env.path, env.cms, {"action": "new", "task_id": first_id})
        await settle(env.path)
        fresh = task._load(env.path)
        assert fresh["task_id"] != first_id
        assert fresh["status"] == "select" and fresh["result"] is None
        # 新任務才會再判斷一次
        await task.handle_event(env.path, env.cms, {"action": "select", "task_id": fresh["task_id"],
                                                    "a": "a", "targets": ["b", "c", "d"]})
        await settle(env.path)
        assert task._load(env.path)["status"] == "done"
        assert sorted(env.judged) == ["a", "a", "b", "b", "c", "c", "d"]
    run(go())


def test_new_is_ignored_while_running(env):
    async def go():
        await task.open_task(env.path, env.cms)
        await settle(env.path)
        t = task._load(env.path)
        t["status"] = "running"
        task._save(env.path, t)
        task._ACTIVE[env.path] = asyncio.get_running_loop().create_future()
        await task.handle_event(env.path, env.cms, {"action": "new", "task_id": t["task_id"]})
        assert task._load(env.path)["task_id"] == t["task_id"]
        task._ACTIVE.clear()
    run(go())


def test_interrupted_task_is_not_rerun(env):
    t = task._new_task()
    t["status"] = "running"
    task._save(env.path, t)
    loaded = task._load(env.path)
    assert loaded["status"] == "error" and loaded["task_id"] == t["task_id"]
    assert env.judged == []


# ── 選擇驗證：A + 2–4 個 ──────────────────────────────────────────────

@pytest.mark.parametrize("targets,ok", [
    (["b"], False), (["b", "c"], True), (["b", "c", "d"], True),
    (["a", "b"], False), (["b", "b"], False), (["b", "zz"], False),
])
def test_select_requires_two_to_four_targets(env, targets, ok):
    async def go():
        await task.open_task(env.path, env.cms)
        await settle(env.path)
        tid = task._load(env.path)["task_id"]
        await task.handle_event(env.path, env.cms, {"action": "select", "task_id": tid,
                                                    "a": "a", "targets": targets})
        await settle(env.path)
        t = task._load(env.path)
        assert (t["status"] == "done") is ok
        if not ok:
            assert t["status"] == "select" and t["error"] and env.judged == []
    run(go())


def test_five_targets_rejected():
    t = {"projects": [{"uuid": u} for u in "abcdef"]}
    assert task._validate(t, "a", list("bcdef"))
    assert task._validate(t, "a", list("bcde")) is None


# ── 結果：星圖資料 ────────────────────────────────────────────────────

def test_result_is_galaxy_shaped_from_real_judgement(env):
    async def go():
        done = await _open_and_select(env)
        res = done["result"]
        assert res["demo"] is False and res["a"] == "a"
        assert [p["pid"] for p in res["projects"]] == ["a", "b", "c"]
        a = res["projects"][0]
        assert set(a["match"]) == {f"B{i}" for i in range(1, 9)}
        assert a["match"]["B1"] == {"role": "offer", "evidence": ["閒置穀倉可以提供場地"]}
        assert a["match"]["B7"]["role"] == "need"
        assert a["match"]["B3"] == {"role": "none", "evidence": []}
        ab = next(p for p in res["pairs"] if p["pb"] == "b")
        assert ab["pair"] == "a|b"
        assert ab["status"] == "CLARIFY_FIRST" and ab["status_text"] == "先補資料"
        assert ab["counts"]["complement"] == 2
        ac = next(p for p in res["pairs"] if p["pb"] == "c")
        assert ac["relations"]["共同尋找第三方"] == ["B7"]
        assert res["keys"]["B7"]
        assert any("媒合星球" in m.content for m in Message.sent)
    run(go())


def test_explain_uses_stored_result_without_rejudging(env):
    async def go():
        done = await _open_and_select(env)
        Message.sent = []
        await task.handle_event(env.path, env.cms, {"action": "explain", "task_id": done["task_id"],
                                                    "code": "B7", "kind": "relation", "pa": "b", "pb": "a"})
        assert len(Message.sent) == 1
        text = Message.sent[0].content
        assert "B7" in text and "有通路可以協助販售" in text and "互補候選" in text
        assert "沒有重新判斷" in text
        await task.handle_event(env.path, env.cms, {"action": "explain", "task_id": done["task_id"],
                                                    "code": "planet", "who": "c"})
        assert "青年團隊" in Message.sent[-1].content
        assert sorted(env.judged) == ["a", "b", "c"]
    run(go())


def test_cms_error_is_not_reported_as_too_few(env):
    class Broken(CMS):
        async def execute(self, name, args):
            return {"status": "error", "reason": "forbidden"}

    async def go():
        await task.open_task(env.path, Broken())
        await settle(env.path)
        t = task._load(env.path)
        assert t["status"] == "error" and "forbidden" in t["error"]
    run(go())


# ── 3. 按租戶開關：sechome 開、yunlin 不開 ────────────────────────────

def _session(monkeypatch, project, cms):
    store = {"user": SimpleNamespace(identifier="u@x", metadata={"project": project}),
             "cms_runtime": cms,
             "law_task_identity": {"issuer": "cms", "project": project, "user_id": 7}}
    session = SimpleNamespace(get=lambda k, d=None: store.get(k, d),
                              set=lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(task.cl, "user_session", session)
    monkeypatch.setattr(task.cl, "context", SimpleNamespace(session=SimpleNamespace(thread_id="thread-9")))
    monkeypatch.setattr(handler.cl, "Action", lambda **kw: SimpleNamespace(**kw))
    return store


def test_enabled_for_only_sechome(monkeypatch):
    monkeypatch.delenv("MATCH_TASK_PROJECTS", raising=False)
    assert task.enabled_for("sechome") and task.enabled_for("SECHOME")
    assert not task.enabled_for("yunlin")
    assert not task.enabled_for(None) and not task.enabled_for("")


def test_project_sechome_opens_galaxy(env, monkeypatch):
    monkeypatch.setenv("TANGLE_LAW_TASK", "1")
    monkeypatch.delenv("MATCH_TASK_PROJECTS", raising=False)
    _session(monkeypatch, "sechome", env.cms)

    async def go():
        await handler.handle("", None)
        path = task.context()[0]
        await settle(path)
        assert env.pushes and env.pushes[0]["mode"] == "match" and "matchTask" in env.pushes[0]
        assert task._load(path)["status"] == "select"
        # 沒走原本的聊天按鈕流程
        assert not any("請先選擇你的專案 A" in m.content for m in Message.sent)
        first = task._load(path)["task_id"]
        await handler.handle("", None)            # 同一對話再點：同一任務
        assert task._load(path)["task_id"] == first
        assert env.pushes[-1]["matchTask"]["task_id"] == first
    run(go())


def test_project_yunlin_keeps_original_flow(env, monkeypatch):
    monkeypatch.setenv("TANGLE_LAW_TASK", "1")
    monkeypatch.delenv("MATCH_TASK_PROJECTS", raising=False)
    _session(monkeypatch, "yunlin", env.cms)

    async def go():
        await handler.handle("", None)
        assert env.pushes == []                   # 沒開星球
        assert not list(task.TASK_DIR.glob("*.json"))
        assert any("請先選擇你的專案 A" in m.content for m in Message.sent)   # 原樣
    run(go())


def test_without_overlay_keeps_original_flow(env, monkeypatch):
    monkeypatch.delenv("TANGLE_LAW_TASK", raising=False)
    monkeypatch.delenv("TANGLE_LAB", raising=False)
    _session(monkeypatch, "sechome", env.cms)
    run(handler.handle("", None))
    assert env.pushes == []
    assert any("請先選擇你的專案 A" in m.content for m in Message.sent)


def test_window_router_intercepts_match_task_only(env, monkeypatch):
    _session(monkeypatch, "sechome", env.cms)
    seen = []

    async def original(data):
        seen.append(data)

    code = SimpleNamespace(on_window_message=original)
    task.install_window_router(code)
    task.install_window_router(code)              # 冪等：不重複包
    assert code.on_window_message._match_task_inner is original

    async def go():
        await code.on_window_message({"tangle": {"kind": "law_task", "action": "get"}})
        await code.on_window_message({"type": "other"})
        assert len(seen) == 2
        await task.open_task(task.context()[0], env.cms)
        await settle(task.context()[0])
        n = len(env.pushes)
        await code.on_window_message({"tangle": {"kind": "match_task", "action": "get"}})
        assert len(seen) == 2 and len(env.pushes) == n + 1
    run(go())


def test_window_router_blocks_other_tenants(env, monkeypatch):
    _session(monkeypatch, "yunlin", env.cms)
    code = SimpleNamespace(on_window_message=None)
    task.install_window_router(code)

    async def go():
        await code.on_window_message({"tangle": {"kind": "match_task", "action": "new", "task_id": "x"}})
        assert env.pushes == [] and not list(task.TASK_DIR.glob("*.json"))
    run(go())


def test_embed_route_adds_panel_script_only_for_live_match():
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from starlette.testclient import TestClient
    from app.apps.match_analysis import embed_route

    async def fallback(request):
        return PlainTextResponse("original")

    app = Starlette(routes=[Route("/public/{filename:path}", fallback)])
    assert embed_route.install(app) and embed_route.install(app)   # 冪等
    assert sum(getattr(r, "_match_task_embed", False) for r in app.router.routes) == 1
    client = TestClient(app)
    live = client.get("/public/workspace/embed.html?mode=match&v=live-match")
    assert live.status_code == 200 and live.text.count("match-task.js") == 1
    assert live.text.rstrip().endswith("</body></html>")
    for query in ("mode=match&v=1", "mode=law&v=live-match", ""):
        plain = client.get(f"/public/workspace/embed.html?{query}")
        assert "match-task.js" not in plain.text and plain.text == embed_route.EMBED.read_text(encoding="utf-8")
    assert client.get("/public/workspace/law-task.js").text == "original"
    assert embed_route.inject("<body>x" + embed_route.SCRIPT + "</body>").count("match-task.js") == 1
