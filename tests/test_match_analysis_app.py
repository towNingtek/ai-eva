"""#184 媒合分析 app：假 runtime（CMS 專案）＋假 LLM（B1–B8 判斷），不碰真 CMS／模型／瀏覽器。

驗收：
(a) 回覆同時含「事實」「推論」「建議」標示；「為何列出」只以揭露規則與原文呈現，不出現分數
(b) 每個互補候選都附兩邊 philosophy 原文
(c) 狀態為先補資料時，回覆後緊接著送出一題補問
(d) 回覆中列出四個未評估維度
(e) A 搭配 2、3、4 個對象都可（1 個、5 個不行）
"""
import asyncio
import json
import re

import pytest

from app.apps.match_analysis import handler as ma
from app.apps.match_analysis.meta import META
from app.loop.chainlit_adapter import ACTION_CONFIRM, ACTION_UNKNOWN, LABEL_SKIP, LABEL_UNKNOWN
from app.matching import pair

# 每案 philosophy 與假 LLM 要回的依據（依據都是原文逐字子字串）
PROJECTS = {
    "a": ("甲社區", "<p>我們希望推動農事體驗教育。本社區已經營運三合院民宿，每月接待遊客。也想發展品牌故事。</p>",
          {"B3": [{"quote": "希望推動農事體驗教育", "kind": "aim"}],
           "B1": [{"quote": "已經營運三合院民宿", "kind": "concrete"}],
           "B4": [{"quote": "想發展品牌故事", "kind": "aim"}]}),
    "t1": ("乙協會", "本團隊每週帶團辦理導覽活動。",
           {"B3": [{"quote": "每週帶團辦理導覽活動", "kind": "concrete"}]}),
    "t2": ("丙工作室", "我們提供共享空間租借給工作者。希望發展品牌設計。",
           {"B1": [{"quote": "提供共享空間租借給工作者", "kind": "concrete"}],
            "B4": [{"quote": "希望發展品牌設計", "kind": "aim"}]}),
    "t3": ("丁合作社", "希望發展品牌設計與行銷。",
           {"B4": [{"quote": "希望發展品牌設計與行銷", "kind": "aim"}]}),
    "t4": ("戊農場", "已建置電商平台販售農產。",
           {"B7": [{"quote": "已建置電商平台販售農產", "kind": "concrete"}]}),
    "t5": ("己基金會", "每月舉辦兩場社區共餐。",
           {"B6": [{"quote": "每月舉辦兩場社區共餐", "kind": "concrete"}]}),
}
NOT_EVALUATED = ["議題與目標對象", "合作可執行性", "階段與時程", "跨國語境與成本"]


def project(uuid: str) -> dict:
    name, philosophy, _ = PROJECTS[uuid]
    return {"uuid": uuid, "name": name, "philosophy": philosophy, "period": "2026", "budget": 1}


class FakeRuntime:
    def __init__(self, uuids):
        self.uuids = list(uuids)
        self.calls = []

    async def execute(self, name, args):
        self.calls.append((name, args))
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": list(self.uuids)}}}
        if name == "get_project_info" and args.get("uuid") in self.uuids:
            return {"status": "ok", "result": {"data": project(args["uuid"])}}
        return {"status": "error", "reason": "forbidden"}


class FakeLLM:
    """capability.analyze 用：依 philosophy 內容回該案的 B1–B8 JSON。"""

    def __init__(self):
        self.calls = 0

    def __call__(self, messages):
        self.calls += 1
        user = messages[-1]["content"]
        for _uuid, (_n, _p, reply) in PROJECTS.items():
            if all(item["quote"] in user for items in reply.values() for item in items):
                return json.dumps(reply, ensure_ascii=False)
        return "{}"


class FakeChainlit:
    def __init__(self, session):
        self._session = dict(session)
        self.sent = []  # [(content, [action labels], [action names])]
        outer = self

        class Action:
            def __init__(self, name, label="", payload=None, **kw):
                self.name, self.label, self.payload = name, label, payload or {}

        class Message:
            def __init__(self, content="", actions=None, **kw):
                self.content, self.actions = content, actions or []

            async def send(self):
                outer.sent.append((self.content, [a.label for a in self.actions],
                                   [(a.name, a.payload) for a in self.actions]))
                return self

        self.Action, self.Message, self.user_session = Action, Message, self

    def get(self, key, default=None):
        return self._session.get(key, default)

    def set(self, key, value):
        self._session[key] = value

    def contents(self):
        return [c for c, _, _ in self.sent]


@pytest.fixture
def env(monkeypatch):
    def _make(uuids=tuple(PROJECTS)):
        rt = FakeRuntime(uuids)
        fake = FakeChainlit({"cms_runtime": rt})
        llm = FakeLLM()
        monkeypatch.setattr(ma, "cl", fake)
        monkeypatch.setattr(ma, "_default_llm", lambda: llm)
        return fake, rt, llm

    return _make


def run(coro):
    return asyncio.run(coro)


def loaded(uuid: str) -> dict:
    p = project(uuid)
    return {**p, "philosophy_text": ma.plain(p["philosophy"])}


def analyze(env, targets):
    fake, rt, _ = env()
    out = run(ma.run_analysis(rt, loaded("a"), [loaded(t) for t in targets]))
    return fake, out


class TestRegistry:
    def test_discoverable_alongside_project_match(self):
        from app.apps._registry import discover

        apps = discover()
        assert "match_analysis" in apps and "project_match" in apps
        assert META["id"] == "match_analysis"


class TestReply:
    def test_fact_inference_suggestion_and_no_score(self, env):
        """(a)"""
        fake, out = analyze(env, ["t1", "t2"])
        reply = out["reply"]
        for tag in ("【事實】", "【推論】", "【建議】"):
            assert tag in reply
        # 揭露規則原文
        assert "Primary Bridge 成立須有明確 Need、相對應 Offer 及可行合作形式" in reply
        # 不出現分數
        assert "分數" not in reply and "score" not in reply.lower()
        assert not re.search(r"\d+\s*(分|/\s*100|%)", reply)
        assert "fit" not in reply.lower() and "信心" not in reply

    def test_three_relations_listed_separately(self, env):
        _, out = analyze(env, ["t1", "t2"])
        reply = out["reply"]
        for name in (pair.REL_COMPLEMENT, pair.REL_THIRD_PARTY, pair.REL_PEER):
            assert f"#### {name}" in reply
        statuses = [r["status"] for r in out["results"]]
        assert statuses == [pair.CLARIFY_FIRST, pair.EXPLORE]

    def test_every_complement_has_both_quotes(self, env):
        """(b)"""
        _, out = analyze(env, ["t1", "t2", "t3"])
        reply = out["reply"]
        comps = [(r, c) for r in out["results"] for c in r["relations"][pair.REL_COMPLEMENT]]
        assert comps
        for r, c in comps:
            key = c["key"]
            for pid in (c["need"], c["offer"]):
                for q in PROJECTS[pid][2][key]:
                    assert f"「{q['quote']}」" in reply
        # 甲 B3 需要 ← 乙 B3 提供：兩邊原文都在同一段
        block = reply.split("#### 互補候選")[1].split("#### ")[0]
        assert "希望推動農事體驗教育" in block and "每週帶團辦理導覽活動" in block

    def test_not_evaluated_dimensions_and_disclaimer(self, env):
        """(d)"""
        _, out = analyze(env, ["t3", "t4"])
        for d in NOT_EVALUATED:
            assert d in out["reply"]
        assert "不推薦" in out["reply"] and "不自動聯絡" in out["reply"]


class TestClarify:
    def test_clarify_first_sends_one_question_right_after_reply(self, env):
        """(c)"""
        fake, out = analyze(env, ["t1", "t4"])
        assert out["results"][0]["status"] == pair.CLARIFY_FIRST
        contents = fake.contents()
        idx = contents.index(out["reply"])
        assert len(contents) == idx + 2                 # 回覆後緊接著一題，只有一題
        q, labels, _ = fake.sent[idx + 1]
        assert "甲社區" in q and "服務與體驗" in q and "用在哪裡" in q
        assert labels == [LABEL_UNKNOWN, LABEL_SKIP]

    def test_no_clarify_when_not_clarify_first(self, env):
        fake, out = analyze(env, ["t2", "t3"])
        assert pair.CLARIFY_FIRST not in [r["status"] for r in out["results"]]
        assert fake.contents()[-1] == out["reply"]

    def test_typed_answer_goes_to_loop_then_next_question(self, env):
        fake, out = analyze(env, ["t1", "t4"])
        run(ma.handle("辦農事體驗營", None))
        assert "草稿" in fake.contents()[-1]
        run(ma.clarify_action(ACTION_CONFIRM, {"field": "用途"}))
        tail = "\n".join(fake.contents()[-2:])
        assert "辦農事體驗營" in tail and "乙協會" in fake.contents()[-1]   # 下一題問能提供方「可提供形式」
        run(ma.clarify_action(ACTION_UNKNOWN, {"field": "可提供形式"}))
        assert "仍是" in "\n".join(fake.contents()[-3:])


class TestTargets:
    @pytest.mark.parametrize("targets", [["t1", "t2"], ["t1", "t2", "t3"], ["t1", "t2", "t3", "t4"]])
    def test_two_to_four_targets(self, env, targets):
        """(e)"""
        _, out = analyze(env, targets)
        assert [r["target"]["uuid"] for r in out["results"]] == targets
        assert out["reply"].count("### 🧭 甲社區 × ") == len(targets)

    @pytest.mark.parametrize("targets", [["t1"], ["t1", "t2", "t3", "t4", "t5"]])
    def test_out_of_range_rejected(self, env, targets):
        fake, out = analyze(env, targets)
        assert out["reply"] is None and "2–4" in fake.contents()[-1]

    def test_picker_flow(self, env):
        fake, rt, llm = env()
        run(ma.handle("", None))
        _, labels, actions = fake.sent[-1]
        assert labels == [PROJECTS[u][0] for u in PROJECTS]
        run(ma.pick_a({"uuid": "a"}))
        for t in ("t1", "t2", "t3", "t4"):
            run(ma.toggle_target({"uuid": t}))
        run(ma.toggle_target({"uuid": "t5"}))
        assert "最多" in fake.contents()[-1]
        run(ma.toggle_target({"uuid": "t4"}))           # 取消
        out = run(ma.run_selected())
        assert [r["target"]["uuid"] for r in out["results"]] == ["t1", "t2", "t3"]
        assert llm.calls == 4
        # HTML tag 去掉後，原文依據仍逐字存在
        assert "希望推動農事體驗教育" in out["reply"]

    def test_too_few_projects(self, env):
        fake, _, _ = env(["a", "t1"])
        run(ma.handle("", None))
        assert "至少" in fake.contents()[-1]
