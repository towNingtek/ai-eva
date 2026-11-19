"""星圖用的法領域資料：從真實判定結果算出示範資料同形狀的欄位，讓原有特效能畫。"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

from app.apps.regulation_check import handler, task

RESULT = json.loads((Path(__file__).parent / "fixtures" / "regcheck_result_48060125.json").read_text(encoding="utf-8"))


def test_domain_view_drives_all_three_drawings():
    view = handler.domain_view(RESULT)
    # every covered domain gets a satellite (10), not only the six that were judged clause by clause
    assert len(view) == 10
    hit = view["農村再生"]
    assert hit["state"] == "hit" and hit["confidence"] in ("high", "mid", "low")
    assert hit["clauses"] and all(c["kind"] in ("risk", "note") and c["law"] and c["no"] for c in hit["clauses"])
    assert hit["count"]["risk"] + hit["count"]["note"] >= len(hit["clauses"])  # counts are all clauses; debris is capped
    assert hit["evidence"], "verified plan quotes drive the evidence dots and light flow"
    assert view["開發審議"]["state"] == "gap" and view["開發審議"]["missing"]      # gate 待確認 → fog + 缺：…
    assert view["水土保持"]["state"] == "na"                                          # gate 不成立 → small dim moon
    assert view["都市計畫"]["state"] == "na"


def test_satellite_click_explains_without_rejudging(monkeypatch, tmp_path):
    sent = []

    class Message:
        def __init__(self, content, elements=None):
            self.content = content

        async def send(self):
            sent.append(self.content)
            return self

    monkeypatch.setattr(task.cl, "Message", Message)
    run_check = AsyncMock()
    monkeypatch.setattr(task.handler.judge, "run_check", run_check)
    monkeypatch.setattr(task, "_publish", AsyncMock())
    monkeypatch.setattr(task, "_remember_context", lambda p: None)
    path = tmp_path / "t.json"
    done = {"task_id": "t1", "status": "done", "projects": [], "progress": [],
            "project": {"uuid": "48060125", "name": "大庄"}, "error": None,
            "result": {"law": handler.domain_view(RESULT)}}
    task._save(path, done)

    async def go(**kw):
        await task.handle_event(path, None, {"action": "domain", "task_id": "t1", **kw}, "m")

    asyncio.run(go(domain="農村再生"))
    asyncio.run(go(domain="開發審議"))
    asyncio.run(go(domain="不存在"))
    asyncio.run(task.handle_event(path, None, {"action": "domain", "task_id": "stale", "domain": "農村再生"}, "m"))
    assert len(sent) == 2
    assert "農村再生" in sent[0] and "觸發" in sent[0]
    assert "缺資料" in sent[1]
    run_check.assert_not_called()
