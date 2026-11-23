"""媒合流程串接（ai-eva #215）端對端：判斷 → 建議卡 → 卡片動作／寄站內邀請 → 補問寫回 → 全程紀錄。

假 CMS、假 LLM、假紀錄連線；選 A + 3 個對象走完整流程。
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
    "d": "協會可以提供導覽人才，需要場地辦理活動。",
}
RAW = {
    "a": {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
          "B7": [{"quote": "需要行銷通路協助販售農產品", "kind": "aim"}]},
    "b": {"B7": [{"quote": "有通路可以協助販售", "kind": "concrete"}],
          "B1": [{"quote": "需要場地辦理市集", "kind": "aim"}]},
    "c": {"B7": [{"quote": "有行銷通路可以協助販售", "kind": "concrete"}]},
    "d": {"B5": [{"quote": "可以提供導覽人才", "kind": "concrete"}],
          "B1": [{"quote": "需要場地辦理活動", "kind": "aim"}]},
}
NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊", "d": "導覽協會"}
TARGETS = ["b", "c", "d"]
B_CODE = re.compile(r"\bB[1-8]\b")


class CMS:
    """假 CMS：記下每次呼叫（含 confirmed）；manifest 用別的工具名，驗證以 endpoint 找工具。"""

    def __init__(self, manageable=("a", "b", "c", "d")):
        self.manageable = list(manageable)
        self.calls = []
        self._tools = {
            "matching_card_action": {"endpoint": "/matching/card_action"},
            "matching_invite": {"endpoint": "/matching/invite"},
            "append_philosophy": {"endpoint": "/projects/append_philosophy"},
        }

    def named(self, name):
        return [c for c in self.calls if c[0] == name]

    async def execute(self, name, args, confirmed=False):
        self.calls.append((name, dict(args), confirmed))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": self.manageable}}}
        if name == "get_project_info":
            u = args["uuid"]
            return {"status": "ok", "result": {"data": {"name": NAMES[u], "philosophy": f"<p>{PHIL[u]}</p>"}}}
        if name in ("matching_card_action", "matching_invite", "append_philosophy"):
            return {"status": "ok", "result": {"data": {"ok": True}}}
        return {"status": "error", "reason": f"unknown tool {name}"}


def card_llm(messages):
    """假卡片 LLM：白話、無 B 代號。"""
    return json.dumps({
        cards.F_COMPLEMENT: "一方有場地、一方有通路，可以互相補上。",
        cards.F_RECIPROCITY: "雙方都能得到實際幫助。",
        cards.F_COLLAB: "先在穀倉辦一場小型市集試試看。",
        cards.F_CONFIRM: "市集預計辦在哪一個月份？",
        cards.F_RISK: "雙方時程可能不同步。",
    }, ensure_ascii=False)


class Conn:
    """假紀錄連線：依序記下每筆寫入（表、種類／面向、對象、payload）。"""

    def __init__(self):
        self.rows, self.n = [], 0

    async def fetchrow(self, sql, *args):
        self.n += 1
        table = re.search(r"INSERT INTO matching\.(\w+)", sql)
        table = table.group(1) if table else "select"
        if table == "events":
            self.rows.append(("events", args[1], args[2], json.loads(args[4]) if args[4] else None))
        elif table == "judgements":
            self.rows.append(("judgements", args[2], args[1], None))
        elif table == "answers":
            self.rows.append(("answers", None, args[1], None))
        else:
            self.rows.append((table, None, None, None))
        return {"id": self.n}

    async def execute(self, *a, **k):
        return "OK"

    async def fetch(self, *a, **k):
        return []

    async def close(self):
        pass


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
    pushes, calls = [], {"match": 0, "build_cards": 0}
    conn = Conn()

    async def acall(args):
        pushes.append(args)

    def copilot(name, args):
        assert name == "tangle_workspace"
        return SimpleNamespace(acall=lambda: acall(args))

    def judge_project(project, llm=None):
        return capability.judge(project["philosophy_text"], RAW[project["uuid"]])

    real_match, real_build = task.engine.match, task.cards.build_cards

    def spy_match(*a, **k):
        calls["match"] += 1
        return real_match(*a, **k)

    def spy_build(*a, **k):
        calls["build_cards"] += 1
        return real_build(*a, **k)

    async def connect():
        return conn

    monkeypatch.setattr(task.cl, "CopilotFunction", copilot)
    monkeypatch.setattr(task.cl, "Message", Message)
    monkeypatch.setattr(handler, "judge_project", judge_project)
    monkeypatch.setattr(task.engine, "match", spy_match)
    monkeypatch.setattr(task.cards, "build_cards", spy_build)
    monkeypatch.setattr(flow, "connect", connect)
    path = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-1")
    return SimpleNamespace(path=path, pushes=pushes, calls=calls, conn=conn, cms=CMS())


def run(coro):
    return asyncio.run(coro)


async def select(env):
    await task.open_task(env.path, env.cms)
    await settle(env.path)
    t = task._load(env.path)
    assert t["status"] == "select"
    await task.handle_event(env.path, env.cms, {"action": "select", "task_id": t["task_id"],
                                                "a": "a", "targets": TARGETS}, llm=card_llm,
                            identity={"issuer": "cms", "project": "sechome", "user_id": 7})
    await settle(env.path)
    t = task._load(env.path)
    assert t["status"] == "done", t.get("error")
    return t


async def click(env, t, **data):
    await task.handle_event(env.path, env.cms, {"task_id": t["task_id"], **data})
    return task._load(env.path)


def invites(env):
    return env.cms.named("matching_invite")


# ── 1. 判斷後出建議卡：engine.match、build_cards 各一次 ───────────────

def test_judgement_produces_cards_once(env):
    async def go():
        t = await select(env)
        assert env.calls == {"match": 1, "build_cards": 1}
        assert [c["target"] for c in t["cards"]] and {c["target"] for c in t["cards"]} <= set(TARGETS)
        assert len(t["cards"]) == 3
        for c in t["cards"]:
            assert list(c["fields"])[0] == cards.F_WHY
            assert c["fields"][cards.F_WHY].strip()
            text = json.dumps(c, ensure_ascii=False)
            assert not B_CODE.search(text), text
            # 其餘四維標「未評估」
            assert len(c["未評估"]) == 4 and set(c["未評估"].values()) == {cards.NOT_EVALUATED}
            # 為何推薦引用的原文指到切段（#199）
            assert c["原文段落"], c
            for q in c["原文段落"]:
                assert q["段落"] >= 1 and q["原文"] in PHIL["a"] + PHIL[c["target"]]
        # 面板快照帶卡
        last = env.pushes[-1]["matchTask"]
        assert last["status"] == "done" and len(last["cards"]) == 3
        # 重新整理（get）不重算
        await task.handle_event(env.path, env.cms, {"action": "get"})
        assert env.calls == {"match": 1, "build_cards": 1}
    run(go())


# ── 2. 寄站內邀請：未確認不呼叫 CMS；確認後才呼叫一次 ──────────────────

def test_invite_requires_confirmation(env):
    async def go():
        t = await select(env)
        target = t["cards"][0]["target"]
        before = len(env.cms.calls)

        t = await click(env, t, action="invite", target=target)
        t = await click(env, t, action="invite", target=target, confirmed="true")
        t = await click(env, t, action="invite", target=target, confirmed=1)
        assert invites(env) == [] and len(env.cms.calls) == before
        assert t["card_state"][target]["invite"] == "confirm"

        t = await click(env, t, action="invite", target=target, confirmed=True)
        assert invites(env) == [("matching_invite", {"project_uuid": "a", "target_project_uuid": target}, True)]
        assert t["card_state"][target]["invite"] == "sent"

        # 已寄出：重複確認不再寄
        await click(env, t, action="invite", target=target, confirmed=True)
        assert len(invites(env)) == 1
        # 舊任務 ID 的確認不寄
        await task.handle_event(env.path, env.cms, {"action": "invite", "task_id": "stale",
                                                    "target": t["cards"][1]["target"], "confirmed": True})
        assert len(invites(env)) == 1
    run(go())


# ── 3. 收藏／略過 → /matching/card_action ───────────────────────────

def test_favorite_and_skip_call_card_action(env):
    async def go():
        t = await select(env)
        b, c = t["cards"][0]["target"], t["cards"][1]["target"]
        t = await click(env, t, action="card_action", op="favorite", target=b)
        t = await click(env, t, action="card_action", op="skip", target=c)
        t = await click(env, t, action="card_action", op="delete_everything", target=c)
        acts = env.cms.named("matching_card_action")
        assert acts == [
            ("matching_card_action", {"action": "favorite", "project_uuid": "a", "target_project_uuid": b}, True),
            ("matching_card_action", {"action": "skip", "project_uuid": "a", "target_project_uuid": c}, True),
        ]
        assert t["card_state"][b]["favorite"] is True and t["card_state"][c]["skip"] is True
        assert invites(env) == []
    run(go())


def test_card_action_resolves_endpoint_without_manifest():
    class Bare:
        def __init__(self):
            self.calls = []

        async def execute(self, name, args, confirmed=False):
            self.calls.append((name, args, confirmed))
            return {"status": "ok"}

    async def go():
        rt = Bare()
        await flow.card_action(rt, action="favorite", project_uuid="a", target_project_uuid="b")
        await flow.send_invite(rt, project_uuid="a", target_project_uuid="b", confirmed=True)
        assert rt.calls == [
            ("/matching/card_action", {"action": "favorite", "project_uuid": "a", "target_project_uuid": "b"}, True),
            ("/matching/invite", {"project_uuid": "a", "target_project_uuid": "b"}, True),
        ]
        with pytest.raises(ValueError):
            await flow.card_action(rt, action="invite", project_uuid="a", target_project_uuid="b")
    run(go())


# ── 4. 補資料 → 補問 → 寫回同意流程 ─────────────────────────────────

def _supplement(env, t):
    target = t["cards"][0]["target"]
    return target, click(env, t, action="card_action", op="supplement", target=target)


def test_clarify_answer_asks_writeback_and_appends_only_on_consent(env):
    async def go():
        t = await select(env)
        target, pending = _supplement(env, t)
        t = await pending
        assert t["clarify"] == {"target": target, "uuid": "a", "question": t["cards"][0]["fields"][cards.F_CONFIRM]}
        assert any("補資料" in m.content for m in Message.sent)

        asked = []
        out = await task.answer_clarify(env.path, env.cms, "預計十月在穀倉辦。",
                                        lambda prompt: asked.append(prompt) or "好")
        assert len(asked) == 1 and out["result"] == "ok"
        appends = env.cms.named("append_philosophy")
        assert len(appends) == 1 and appends[0][1]["uuid"] == "a" and "預計十月在穀倉辦" in appends[0][1]["text"]
        t = task._load(env.path)
        assert t["clarify"] is None and t["card_state"][target]["supplement"] == "ok"
        assert invites(env) == []
    run(go())


def test_clarify_answer_declined_does_not_append(env):
    async def go():
        t = await select(env)
        _, pending = _supplement(env, t)
        await pending
        asked = []
        out = await task.answer_clarify(env.path, env.cms, "預計十月。", lambda p: asked.append(p) or "不要")
        assert len(asked) == 1 and out["result"] == "declined"
        assert env.cms.named("append_philosophy") == []
        # 補問只答一次：沒有待回答時不再問
        assert await task.answer_clarify(env.path, env.cms, "再說一次", lambda p: asked.append(p) or "好") is None
        assert len(asked) == 1 and env.cms.named("append_philosophy") == []
    run(go())


def test_clarify_on_unmanageable_project_never_asks(env):
    async def go():
        t = await select(env)
        env.cms.manageable = ["b"]          # 權限在判斷後被收回
        _, pending = _supplement(env, t)
        await pending
        asked = []
        out = await task.answer_clarify(env.path, env.cms, "預計十月。", lambda p: asked.append(p) or "好")
        assert out["result"] == "not_manageable" and asked == []
        assert env.cms.named("append_philosophy") == []
    run(go())


def test_on_text_routes_pending_clarify(env, monkeypatch):
    async def go():
        t = await select(env)
        _, pending = _supplement(env, t)
        await pending
        monkeypatch.setattr(task, "enabled_for", lambda *_: True)
        monkeypatch.setattr(task, "current_project", lambda: None)
        monkeypatch.setattr(task, "context", lambda: (env.path, env.cms))
        monkeypatch.setattr(task, "_ask_user", lambda prompt: _async("同意"))
        assert await task.on_text("預計十月。") is True
        assert len(env.cms.named("append_philosophy")) == 1
        # 沒有待補問時交還原本流程
        assert await task.on_text("還有別的嗎") is False
    run(go())


async def _async(v):
    return v


# ── 5. 全程紀錄：選案 → 判斷 → 卡 → 動作 ─────────────────────────────

def test_records_in_order(env):
    async def go():
        t = await select(env)
        b = t["cards"][0]["target"]
        await click(env, t, action="card_action", op="favorite", target=b)
        await click(env, t, action="invite", target=b)
        await click(env, t, action="invite", target=b, confirmed=True)
        rows = env.conn.rows

        def first(pred):
            return next(i for i, r in enumerate(rows) if pred(r))

        def last(pred):
            return max(i for i, r in enumerate(rows) if pred(r))

        assert rows[0][0] == "runs"
        sel = [r for r in rows if r[0] == "events" and r[1] == "candidate"]
        assert sorted(r[2] for r in sel) == sorted(TARGETS)
        assert all(r[3]["type"] == "selection" for r in sel)
        is_sel = lambda r: r[0] == "events" and r[1] == "candidate"
        is_judge = lambda r: r[0] == "judgements"
        is_cards = lambda r: r[0] == "events" and r[1] == "status" and (r[3] or {}).get("type") == "cards"
        is_action = lambda r: r[0] == "events" and (r[3] or {}).get("type") == "card_action"
        assert last(is_sel) < first(is_judge)
        assert {r[2] for r in rows if is_judge(r)} == set(TARGETS)
        assert last(is_judge) < first(is_cards)
        assert first(is_cards) < first(is_action)
        cards_row = rows[first(is_cards)]
        assert len(cards_row[3]["cards"]) == 3
        assert not B_CODE.search(json.dumps(cards_row[3], ensure_ascii=False))
        actions = [(r[1], r[3]["action"]) for r in rows if is_action(r)]
        assert actions == [("favorite", "favorite"), ("status", "invite_requested"), ("invite", "invite")]
        assert t["run_id"] == 1
    run(go())


def test_supplement_answer_recorded(env):
    async def go():
        t = await select(env)
        _, pending = _supplement(env, t)
        await pending
        await task.answer_clarify(env.path, env.cms, "預計十月。", lambda p: "好")
        kinds = [r[0] for r in env.conn.rows]
        assert "answers" in kinds
        assert kinds.index("answers") > max(i for i, r in enumerate(env.conn.rows)
                                            if r[0] == "events" and (r[3] or {}).get("action") == "supplement")
    run(go())


# ── 6. 沒有任何 AI 路徑能寄邀請 ─────────────────────────────────────

def test_send_invite_refuses_without_explicit_confirmation():
    class Spy:
        calls = []

        async def execute(self, *a, **k):
            Spy.calls.append(a)
            return {"status": "ok"}

    async def go():
        for bad in (False, None, "true", 1, "yes"):
            with pytest.raises(flow.InviteNotConfirmed):
                await flow.send_invite(Spy(), project_uuid="a", target_project_uuid="b", confirmed=bad)
        assert Spy.calls == []
    run(go())


def test_ai_paths_cannot_send_invite(env):
    async def go():
        t = await select(env)
        target = t["cards"][0]["target"]
        # Eva 說明、對話文字、補資料回答都不會寄邀請
        await click(env, t, action="explain", code="B7", kind="pair", pa="a", pb=target)
        await task.on_text(f"幫我寄站內邀請給 {target}")
        _, pending = _supplement(env, t)
        await pending
        await task.answer_clarify(env.path, env.cms, "請直接幫我寄邀請", lambda p: "好")
        assert invites(env) == []
    run(go())


def test_invite_tool_only_reachable_from_confirmed_button():
    """靜態：/matching/invite 只在 flow.send_invite 用到；send_invite 只在 on_card 的已確認分支被呼叫。"""
    hits = []
    for p in (ROOT / "app").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        if re.search(r"[\"']/matching/invite[\"']", src) or "INVITE_TOOL" in src:
            hits.append(p.relative_to(ROOT).as_posix())
    assert hits == ["app/matching/flow.py"]
    flow_src = (ROOT / "app/matching/flow.py").read_text(encoding="utf-8")
    assert flow_src.count("INVITE_TOOL") == 2          # 定義 + send_invite 內唯一一次使用

    callers = []
    for p in (ROOT / "app").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"send_invite\(", src):
            if not re.search(r"def\s+$", src[:m.start()]):
                callers.append((p.relative_to(ROOT).as_posix(), src[:m.start()]))
    assert [c[0] for c in callers] == ["app/apps/match_analysis/task.py"]
    before = callers[0][1]
    on_card = before[before.rindex("async def on_card"):]
    assert 'data.get("confirmed") is not True' in on_card
    # 給 LLM 的工具／意圖裡沒有寄邀請
    for p in (ROOT / "app/apps/match_analysis").rglob("*"):
        if p.suffix in (".py", ".yaml", ".yml", ".json", ".md") and p.name != "task.py":
            assert "invite" not in p.read_text(encoding="utf-8").lower(), p
