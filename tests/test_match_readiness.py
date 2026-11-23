"""媒合準備度（ai-eva #238）：選好 A 時先看資料夠不夠，不夠就多問、永不擋開始。

用假的能力判斷結果（capability.judge 驗證過的 RAW）測：
(a) 四項狀態推導；(b) 最多 3 題、每題 2–4 選項；(c) 不同意不寫、同意走既有 append 流程；
(d) 任何準備度狀態下 select 都被接受；(e) 四語文字齊全。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.apps.match_analysis import handler, task
from app.matching import capability, flow, writeback
from app.matching import i18n as mi
from app.matching import readiness as ready

LANGS = ("zh", "en", "ja", "ko")


def judged(text, raw):
    return capability.judge(text, raw)


def states(res):
    return {i["key"]: i["state"] for i in res["items"]}


# ── (a) 四項狀態推導 ──────────────────────────────────────────────

def test_offer_ok_need_vague_scale_missing():
    text = "我們有閒置穀倉可以提供場地，行銷通路是弱項。"
    j = judged(text, {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
                      "B7": [{"quote": "行銷通路是弱項", "kind": "aim"}]})
    s = states(ready.assess(j, text))
    assert s["offer"] == ready.OK                 # 有 OFFER → ✅
    assert s["need"] == ready.VAGUE               # NEED 只一類、原文沒細節 → ⚠
    assert s["scale"] == ready.MISSING            # 沒有規模／時間詞 → ？
    assert s["collab"] == ready.MISSING
    assert [i["key"] for i in ready.assess(j, text)["items"]] == ["offer", "need", "scale", "collab"]
    assert ready.assess(j, text)["complete"] is False


def test_nothing_written_is_missing_everywhere():
    res = ready.assess(capability.judge("", {}), "")
    assert set(states(res).values()) == {ready.MISSING}
    assert res["complete"] is False


def test_need_detail_or_two_categories_is_enough():
    text = "我們需要行銷通路協助販售農產品。"
    one = judged(text, {"B7": [{"quote": "需要行銷通路協助販售農產品", "kind": "aim"}]})
    assert states(ready.assess(one, text))["need"] == ready.OK          # 原文有細節
    text2 = "行銷通路是弱項，人才也是弱項。"
    two = judged(text2, {"B7": [{"quote": "行銷通路是弱項", "kind": "aim"}],
                         "B5": [{"quote": "人才也是弱項", "kind": "aim"}]})
    assert states(ready.assess(two, text2))["need"] == ready.OK         # 兩類


COMPLETE_TEXT = "我們有閒置穀倉可以提供場地，需要行銷通路協助販售；預計一年辦 12 場市集，想和夥伴共同經營。"
COMPLETE_RAW = {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
                "B7": [{"quote": "需要行銷通路協助販售", "kind": "aim"}]}


def test_complete_data_all_ok_and_no_questions():
    j = judged(COMPLETE_TEXT, COMPLETE_RAW)
    res = ready.assess(j, COMPLETE_TEXT)
    assert set(states(res).values()) == {ready.OK} and res["complete"] is True
    built = ready.build(j, COMPLETE_TEXT, a="a", lang="zh")
    assert built["complete"] is True and built["questions"] == []
    assert built["texts"]["complete"] == "資料完整，可以開始"


# ── (b) 最多 3 題、每題 2–4 選項 ──────────────────────────────────

def test_at_most_three_questions_with_two_to_four_options():
    items = ready.assess(capability.judge("", {}), "")["items"]       # 四項都不足
    for lang in LANGS:
        qs = ready.questions(items, lang)
        assert 1 <= len(qs) <= ready.MAX_QUESTIONS == 3
        assert len({q["key"] for q in qs}) == len(qs)
        for q in qs:
            assert q["text"].strip()
            assert 2 <= len(q["options"]) <= 4 and all(o.strip() for o in q["options"])
    for key in ready.ITEMS:                                            # 每一題本身也是 2–4
        for lang in LANGS:
            assert 2 <= len(ready.question(key, lang)["options"]) <= 4


def test_questions_only_for_weak_items():
    items = [{"key": "offer", "state": "ok"}, {"key": "need", "state": "vague"},
             {"key": "scale", "state": "missing"}, {"key": "collab", "state": "ok"}]
    assert [q["key"] for q in ready.questions(items, "zh")] == ["need", "scale"]
    assert ready.questions([{"key": k, "state": "ok"} for k in ready.ITEMS], "zh") == []


# ── (c) 不同意不寫；同意走既有 append 流程 ─────────────────────────

class CMS:
    def __init__(self, allowed=("a",), philosophy="原本的理念。"):
        self.allowed, self.philosophy, self.calls = list(allowed), philosophy, []

    async def execute(self, name, args, confirmed=False):
        self.calls.append((name, args, confirmed))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": self.allowed}}}
        if name == "get_project_info":
            return {"status": "ok", "result": {"data": {"name": "A 案", "philosophy": self.philosophy}}}
        if name == "append_philosophy":
            return {"status": "ok", "result": {"data": {}}}
        return {"status": "error", "reason": "unknown"}


def appends(cms):
    return [c for c in cms.calls if c[0] == "append_philosophy"]


def test_without_consent_nothing_is_written():
    cms = CMS()
    used = []

    async def spy(*a, **kw):
        used.append((a, kw))
        return {"result": "ok"}

    out = asyncio.run(ready.answer(cms, uuid="a", key="scale", answer="一年期計畫", consent=False, writeback=spy))
    assert out["result"] == "declined"
    assert used == [] and cms.calls == []
    out = asyncio.run(ready.answer(cms, uuid="a", key="scale", answer="一年期計畫", consent=None))
    assert out["result"] == "declined" and cms.calls == []


def test_with_consent_calls_existing_append_flow(monkeypatch):
    async def no_db():
        return None

    monkeypatch.setattr(flow, "connect", no_db)
    seen = []
    real = writeback.offer_writeback

    async def spy(*a, **kw):
        seen.append(kw)
        return await real(*a, **kw)

    monkeypatch.setattr(writeback, "offer_writeback", spy)
    cms = CMS()
    out = asyncio.run(ready.answer(cms, uuid="a", key="scale", answer="一年期計畫", consent=True))
    assert out["result"] == writeback.OK
    assert len(seen) == 1 and seen[0]["uuid"] == "a"                   # 走既有 #201 寫回
    (name, args, confirmed), = appends(cms)
    assert args["uuid"] == "a" and confirmed is True
    assert args["text"].startswith("規模與時間：一年期計畫")              # 只附加，不改原文


def test_consent_on_unmanageable_project_does_not_write(monkeypatch):
    async def no_db():
        return None

    monkeypatch.setattr(flow, "connect", no_db)
    cms = CMS(allowed=())
    out = asyncio.run(ready.answer(cms, uuid="a", key="need", answer="專業人才", consent=True))
    assert out["result"] == writeback.NOT_MANAGEABLE and appends(cms) == []


# ── (d) 任何準備度狀態都接受 select ───────────────────────────────

PHIL = {"a": "我們有閒置穀倉可以提供場地，行銷通路是弱項。", "b": "合作社有通路可以協助販售。",
        "c": "青年團隊需要行銷通路。", "d": COMPLETE_TEXT}
RAW = {"a": {"B1": [{"quote": "閒置穀倉可以提供場地", "kind": "concrete"}],
             "B7": [{"quote": "行銷通路是弱項", "kind": "aim"}]},
       "b": {"B7": [{"quote": "有通路可以協助販售", "kind": "concrete"}]},
       "c": {"B7": [{"quote": "需要行銷通路", "kind": "aim"}]},
       "d": COMPLETE_RAW}
NAMES = {"a": "大庄社區", "b": "農產合作社", "c": "青年團隊", "d": "完整案"}


class TaskCMS:
    def __init__(self):
        self.calls = []

    async def execute(self, name, args, confirmed=False):
        self.calls.append((name, args))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": list(NAMES)}}}
        if name == "append_philosophy":
            return {"status": "ok", "result": {"data": {}}}
        u = args["uuid"]
        return {"status": "ok", "result": {"data": {"name": NAMES[u], "philosophy": f"<p>{PHIL[u]}</p>"}}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(task, "TASK_DIR", tmp_path)
    task._ACTIVE.clear()
    task._READY_CACHE.clear()
    pushes = []

    async def acall(args):
        pushes.append(args)

    monkeypatch.setattr(task.cl, "CopilotFunction", lambda name, args: SimpleNamespace(acall=lambda: acall(args)))
    monkeypatch.setattr(task, "_lang", lambda: "zh")
    monkeypatch.setattr(handler, "judge_project",
                        lambda p, llm=None: capability.judge(p["philosophy_text"], RAW[p["uuid"]]))

    async def no_db():
        return None

    monkeypatch.setattr(flow, "connect", no_db)
    path = task.scope_path({"issuer": "cms", "project": "sechome", "user_id": 7}, "thread-1")
    return SimpleNamespace(path=path, pushes=pushes, cms=TaskCMS())


async def settle(env):
    for _ in range(50):
        worker = task._ACTIVE.get(env.path)
        if worker is not None:
            await worker
            continue
        if task._BACKGROUND:
            await asyncio.gather(*list(task._BACKGROUND))
            continue
        return


async def opened(env):
    await task.open_task(env.path, env.cms)
    await settle(env)
    t = task._load(env.path)
    assert t["status"] == "select"
    return t


async def select(env, t):
    await task.handle_event(env.path, env.cms, {"action": "select", "task_id": t["task_id"],
                                                "a": "a", "targets": ["b", "c"]}, llm=object())
    await settle(env)
    return task._load(env.path)


def test_readiness_snapshot_for_low_data_a(env):
    async def go():
        t = await opened(env)
        await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": t["task_id"], "a": "a"},
                                llm=object())
        checking = env.pushes[-1]["matchTask"]["readiness"]
        assert checking == {"a": "a", "state": "checking"}
        await settle(env)
        r = task._load(env.path)["readiness"]
        assert r["state"] == "ready" and r["a"] == "a" and r["complete"] is False
        assert {i["key"]: i["state"] for i in r["items"]} == {"offer": "ok", "need": "vague",
                                                              "scale": "missing", "collab": "missing"}
        assert [i["icon"] for i in r["items"]] == ["✅", "⚠", "？", "？"]
        assert 1 <= len(r["questions"]) <= 3
        assert r["texts"]["hint"] == "資料不夠也可以直接媒合；補完推薦會更準"
        assert env.pushes[-1]["matchTask"]["readiness"] == r
        # 完整的案：只有一行「可以開始」、沒有題目
        await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": t["task_id"], "a": "d"},
                                llm=object())
        await settle(env)
        r = task._load(env.path)["readiness"]
        assert r["a"] == "d" and r["complete"] is True and r["questions"] == []
    asyncio.run(go())


@pytest.mark.parametrize("state", ["none", "checking", "ready", "error"])
def test_select_is_accepted_in_every_readiness_state(env, state):
    async def go():
        t = await opened(env)
        if state == "checking":
            t["readiness"] = {"a": "a", "state": "checking"}
            task._save(env.path, t)
        elif state == "error":
            t["readiness"] = {"a": "a", "state": "error"}
            task._save(env.path, t)
        elif state == "ready":
            await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": t["task_id"], "a": "a"},
                                    llm=object())
            await settle(env)
            assert task._load(env.path)["readiness"]["complete"] is False   # 不足也照樣可開始
        done = await select(env, t)
        assert done["error"] is None and done["status"] == "done"
        assert done["a"] == "a" and done["targets"] == ["b", "c"]
    asyncio.run(go())


def test_ready_answer_writes_only_with_consent(env):
    async def go():
        t = await opened(env)
        await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": t["task_id"], "a": "a"},
                                llm=object())
        await settle(env)
        base = {"action": "ready_answer", "task_id": t["task_id"], "a": "a", "key": "scale", "answer": "一年期計畫"}
        await task.handle_event(env.path, env.cms, {**base, "consent": False})
        await settle(env)
        assert not [c for c in env.cms.calls if c[0] == "append_philosophy"]
        await task.handle_event(env.path, env.cms, {**base, "consent": True})
        await settle(env)
        (_, args), = [c for c in env.cms.calls if c[0] == "append_philosophy"]
        assert args["uuid"] == "a" and "一年期計畫" in args["text"]
    asyncio.run(go())


def test_readiness_ignored_for_unknown_a_and_outside_select(env):
    async def go():
        t = await opened(env)
        await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": t["task_id"], "a": "zzz"})
        assert "readiness" not in task._load(env.path)
        done = await select(env, t)
        await task.handle_event(env.path, env.cms, {"action": "readiness", "task_id": done["task_id"], "a": "a"})
        assert task._load(env.path).get("readiness") is None
    asyncio.run(go())


# ── (e) 四語文字齊全 ──────────────────────────────────────────────

def test_all_four_languages_have_complete_text():
    keys = [k for k in mi.MSG if k.startswith("readiness.")]
    need = ({f"readiness.item.{k}" for k in ready.ITEMS} | {f"readiness.q.{k}" for k in ready.ITEMS}
            | {f"readiness.opt.{k}" for k in ready.ITEMS} | {f"readiness.state.{s}" for s in ready.STATES}
            | {f"readiness.{k}" for k in ("hint", "complete", "ask", "skip", "other", "stop", "consent")})
    assert need <= set(keys)
    for k in keys:
        assert set(mi.MSG[k]) == set(LANGS), k
        for lang in LANGS:
            assert mi.MSG[k][lang].strip(), (k, lang)
        if k.startswith("readiness.opt."):
            assert len({len(mi.MSG[k][lang].split("|")) for lang in LANGS}) == 1, k   # 各語選項數一致
    assert mi.msg("readiness.hint", "zh") == "資料不夠也可以直接媒合；補完推薦會更準"
    assert mi.msg("readiness.complete", "zh") == "資料完整，可以開始"
    assert mi.msg("readiness.ask", "zh") == "回答幾個問題（約 2 分鐘）"
    assert mi.msg("readiness.skip", "zh") == "先直接媒合"
    assert mi.msg("readiness.consent", "zh") == "要不要補進計畫理念（不會改原本寫的）"
    for lang in ("en", "ja", "ko"):                                    # 外文不是漏翻的中文
        assert mi.msg("readiness.hint", lang) != mi.msg("readiness.hint", "zh")
        built = ready.build(capability.judge("", {}), "", a="a", lang=lang)
        assert all(i["label"] == mi.msg(f"readiness.item.{i['key']}", lang) for i in built["items"])
        assert all(q["text"] == mi.msg(f"readiness.q.{q['key']}", lang) for q in built["questions"])
