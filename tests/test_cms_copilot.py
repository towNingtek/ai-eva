import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.surfaces import cms_copilot, sdg


class Request:
    def __init__(self, data, token="tok"):
        self.headers = {"x-sdg-service-token": token}
        self.data = data

    async def json(self):
        return self.data


BODY = {"message": "幫我寫計畫理念", "step": "basic", "project": {"name": "溪畔食農"}, "history": []}


class CmsCopilotTests(TestCase):
    def setUp(self):
        self.prev = sdg._SERVICE_TOKEN
        sdg._SERVICE_TOKEN = "tok"

    def tearDown(self):
        sdg._SERVICE_TOKEN = self.prev

    def run_ep(self, body, token="tok"):
        return asyncio.run(cms_copilot.cms_copilot_endpoint(Request(body, token)))

    def test_requires_service_token(self):
        with self.assertRaises(HTTPException) as e:
            self.run_ep(BODY, token="bad")
        self.assertEqual(e.exception.status_code, 403)

    def test_requires_message_and_project(self):
        for body in ({**BODY, "message": ""}, {**BODY, "message": "x" * 1001}, {**BODY, "project": None}):
            with self.assertRaises(HTTPException) as e:
                self.run_ep(body)
            self.assertEqual(e.exception.status_code, 400)

    def test_returns_reply_and_whitelisted_suggestions(self):
        content = '```json\n{"reply":"好","suggestions":{"philosophy":"理念","sdgs":[2,"4",99,4],' \
                  '"sdg_texts":{"2":"食農","x":"bad","4":""},"tasks":[{"name":"共餐","overview":"每月"},{"overview":"no name"}],' \
                  '"budget":"999999"}}\n```'
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=content)))
        with patch.object(cms_copilot, "make_llm", return_value=llm):
            out = self.run_ep(BODY)
        self.assertEqual(out["reply"], "好")
        self.assertEqual(out["suggestions"], {
            "philosophy": "理念", "sdgs": [2, 4], "sdg_texts": {"2": "食農"},
            "tasks": [{"name": "共餐", "overview": "每月"}],
        })

    def test_unformatted_reply_has_no_suggestions(self):
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="SROI 是社會投資報酬率")))
        with patch.object(cms_copilot, "make_llm", return_value=llm):
            out = self.run_ep({**BODY, "message": "SROI 是什麼"})
        self.assertEqual(out, {"reply": "SROI 是社會投資報酬率", "suggestions": {}})

    def test_too_many_sdgs_dropped(self):
        self.assertEqual(cms_copilot.clean_suggestions({"sdgs": list(range(1, 9))}), {})

    def test_history_is_bounded(self):
        hist = [{"who": "me", "text": str(i)} for i in range(20)] + [{"who": "ai", "text": ""}, "junk"]
        self.assertEqual(len(cms_copilot._history(hist)), cms_copilot.MAX_HISTORY - 2)

    def test_llm_error_is_502(self):
        llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("down")))
        with patch.object(cms_copilot, "make_llm", return_value=llm), self.assertRaises(HTTPException) as e:
            self.run_ep(BODY)
        self.assertEqual(e.exception.status_code, 502)

    def test_raw_newlines_inside_json_strings_are_accepted(self):
        content = '{"reply":"整理好了","suggestions":{"philosophy":"第一段\n第二段"}}'
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=content)))
        with patch.object(cms_copilot, "make_llm", return_value=llm):
            out = self.run_ep(BODY)
        self.assertEqual(out["suggestions"], {"philosophy": "第一段\n第二段"})

    def test_broken_json_never_shown_raw(self):
        content = '{"reply":"整理好了\\n請看","suggestions":{"philosophy":"未結束'
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=content)))
        with patch.object(cms_copilot, "make_llm", return_value=llm):
            out = self.run_ep(BODY)
        self.assertEqual(out, {"reply": "整理好了\n請看", "suggestions": {}})
        llm.ainvoke.return_value = SimpleNamespace(content='{"suggestions": {"sdgs": [1]')
        with patch.object(cms_copilot, "make_llm", return_value=llm):
            out = self.run_ep(BODY)
        self.assertNotIn("{", out["reply"])

    def test_common_sdg_shapes_are_understood(self):
        c = cms_copilot.clean_suggestions
        self.assertEqual(c({"sdgs": ["SDG 3", "SDG11：永續城鄉", {"sdg": 12, "text": "減少浪費"}, True]}),
                         {"sdgs": [3, 11, 12], "sdg_texts": {"12": "減少浪費"}})
        self.assertEqual(c({"sdg_texts": {"SDG 3": "健康", "目標4": "教育", "x": "bad"}}),
                         {"sdg_texts": {"3": "健康", "4": "教育"}})
        self.assertEqual(c({"sdg_texts": [{"sdg": "3", "description": "健康"}, {"n": 99, "text": "bad"}]}),
                         {"sdg_texts": {"3": "健康"}})

    def test_slow_llm_times_out_as_502(self):
        async def slow(*_a, **_k):
            await asyncio.sleep(1)
        llm = SimpleNamespace(ainvoke=slow)
        with patch.object(cms_copilot, "make_llm", return_value=llm), patch.object(cms_copilot, "LLM_TIMEOUT", 0.05), \
                self.assertRaises(HTTPException) as e:
            self.run_ep(BODY)
        self.assertEqual(e.exception.status_code, 502)

    def test_prompt_allows_answering_sroi_questions(self):
        self.assertIn("SROI", cms_copilot.SYSTEM)
        self.assertIn("不要拒絕回答", cms_copilot.SYSTEM)
