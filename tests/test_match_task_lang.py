"""#226 外文通道：_publish 推給媒合面板的任務狀態帶 lang＝session 語言。"""
import asyncio

import pytest

from app.apps.match_analysis import task


class Session(dict):
    def get(self, key, default=None):
        return super().get(key, default)


@pytest.fixture
def published(monkeypatch):
    calls = []

    class Copilot:
        def __init__(self, name, args):
            self.name, self.args = name, args

        async def acall(self):
            calls.append(self.args)

    monkeypatch.setattr(task.cl, "CopilotFunction", Copilot)
    return calls


@pytest.mark.parametrize("lang", ["zh", "en", "ja", "ko"])
def test_publish_carries_session_lang(monkeypatch, published, lang):
    monkeypatch.setattr(task.cl, "user_session", Session(lang=lang))
    t = {"task_id": "t1", "status": "select", "projects": []}
    asyncio.run(task._publish(t))
    asyncio.run(task._publish(t, opening=True))
    assert [c["matchTask"]["lang"] for c in published] == [lang, lang]
    assert published[0]["matchTask"]["task_id"] == "t1"
    assert "lang" not in t  # 不寫進存檔的任務本身


def test_publish_lang_defaults_to_zh(monkeypatch, published):
    monkeypatch.setattr(task.cl, "user_session", Session())
    asyncio.run(task._publish({"task_id": "t2", "status": "loading"}))
    assert published[0]["matchTask"]["lang"] == "zh"


def test_publish_lang_normalized(monkeypatch, published):
    monkeypatch.setattr(task.cl, "user_session", Session(lang="EN"))
    asyncio.run(task._publish({"task_id": "t3", "status": "loading"}))
    assert published[0]["matchTask"]["lang"] == "en"
