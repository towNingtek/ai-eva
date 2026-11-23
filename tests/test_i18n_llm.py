"""#207：LLM 文字依閱讀者語言產生；原文＋翻譯；確認以原文版本為準（假 LLM，不打網路）。"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core import copilot
from app.i18n.llm import (
    DIRECTIVE_MARK,
    apply_output_language,
    language_directive,
    localize_result,
    make_llm_translator,
    with_output_language,
)
from app.i18n.quote import (
    Bilingual,
    HumanContent,
    bilingual,
    confirmation_matches,
    extract_original,
    extract_translation,
    verify_verbatim,
)


def run(coro):
    return asyncio.run(coro)


class FakeLLM:
    """記錄收到的訊息；回固定內容。"""

    def __init__(self, reply="ok"):
        self.calls: list[list] = []
        self.reply = reply

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, msgs):
        self.calls.append(list(msgs))
        return AIMessage(content=self.reply)


class FakeRuntime:
    def visible_tools(self):
        return []


# 假翻譯器：標上目標語言，便於斷言；記錄呼叫次數
class FakeTranslator:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, text, lang):
        self.calls.append((text, lang))
        return f"[{lang}] {text}"


SOURCE_DOC = (
    "本計畫於花蓮縣豐濱鄉推動部落走讀，\n"
    "預計培訓在地青年導覽員二十名，並建立長期共學機制。"
)


class TestOutputLanguage(unittest.TestCase):
    """(a) ja → 系統提示要求日文；zh → 不加。"""

    def test_directive_ja_requires_japanese(self):
        d = language_directive("ja")
        self.assertIn("Japanese", d)
        self.assertIn(DIRECTIVE_MARK, d)

    def test_directive_zh_empty_and_prompt_unchanged(self):
        self.assertEqual(language_directive("zh"), "")
        self.assertEqual(with_output_language("中文規則", "zh"), "中文規則")
        self.assertEqual(with_output_language("中文規則", "bogus"), "中文規則")

    def test_with_output_language_idempotent_and_keeps_rules(self):
        once = with_output_language("規則一份", "en")
        self.assertTrue(once.startswith("規則一份"))  # 規則本體只維護中文、不翻
        self.assertIn("English", once)
        self.assertEqual(with_output_language(once, "en"), once)

    def test_apply_output_language_message_lists(self):
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "q"}]
        out = apply_output_language(msgs, "ko")
        self.assertIn("Korean", out[0]["content"])
        self.assertEqual(msgs[0]["content"], "S")  # 原物件不動
        self.assertEqual(apply_output_language(msgs, "zh"), msgs)
        lc = apply_output_language([HumanMessage(content="q")], "ja")
        self.assertIsInstance(lc[0], SystemMessage)
        self.assertIn("Japanese", lc[0].content)

    def test_copilot_system_prompt_ja(self):
        llm = FakeLLM("こんにちは")
        with patch.object(copilot, "make_llm", return_value=llm):
            res = run(copilot.run_copilot(FakeRuntime(), "hi", lang="ja"))
        self.assertEqual(res["reply"], "こんにちは")
        sys_msg = llm.calls[0][0]
        self.assertIsInstance(sys_msg, SystemMessage)
        self.assertIn("Japanese", sys_msg.content)
        self.assertTrue(sys_msg.content.startswith(copilot.COPILOT_SYSTEM))

    def test_copilot_system_prompt_zh_unchanged(self):
        llm = FakeLLM()
        with patch.object(copilot, "make_llm", return_value=llm):
            run(copilot.run_copilot(FakeRuntime(), "hi", lang="zh"))
        self.assertEqual(llm.calls[0][0].content, copilot.COPILOT_SYSTEM)

    def test_copilot_defaults_to_session_lang(self):
        llm = FakeLLM()
        with patch.object(copilot, "make_llm", return_value=llm), \
                patch("app.i18n.llm.current_lang", return_value="en"):
            run(copilot.run_copilot(FakeRuntime(), "hi"))
        self.assertIn("English", llm.calls[0][0].content)

    def test_llm_translator_uses_target_language(self):
        llm = FakeLLM("translated")
        tr = make_llm_translator(lambda **kw: llm)
        self.assertEqual(run(tr("原文", "en")), "translated")
        self.assertIn("English", llm.calls[0][0].content)


class TestQuoteWithTranslation(unittest.TestCase):
    """(b) 中文原文給 en 使用者 → 原文逐字保留＋標「翻譯」的英文段。"""

    def test_original_verbatim_plus_labelled_translation(self):
        tr = FakeTranslator()
        q = run(bilingual(SOURCE_DOC, "zh", "en", tr))
        md = q.render()
        self.assertEqual(extract_original(md), SOURCE_DOC)       # 逐字
        self.assertIn("翻譯", md)
        self.assertIn("Translation", md)
        self.assertEqual(extract_translation(md), f"[en] {SOURCE_DOC}")
        # 翻譯段在原文段之後
        self.assertLess(md.index("部落走讀"), md.index("翻譯"))
        self.assertEqual(tr.calls, [(SOURCE_DOC, "en")])

    def test_same_language_no_translation(self):
        tr = FakeTranslator()
        q = run(bilingual(SOURCE_DOC, "zh", "zh", tr))
        self.assertNotIn("翻譯", q.render())
        self.assertEqual(tr.calls, [])


class TestVerbatimCheck(unittest.TestCase):
    """(c) 逐字核對只比對原文段；翻譯段竄改不影響核對結果。"""

    def setUp(self):
        self.q = run(bilingual("預計培訓在地青年導覽員二十名", "zh", "en", FakeTranslator()))

    def test_original_passes(self):
        self.assertTrue(verify_verbatim(self.q, SOURCE_DOC))
        self.assertTrue(verify_verbatim(self.q.render(), SOURCE_DOC))

    def test_tampered_translation_does_not_affect(self):
        md = self.q.render()
        tampered = md.replace("[en]", "[en] totally fabricated: 500 guides, NT$9,999,999")
        self.assertNotEqual(md, tampered)
        self.assertTrue(verify_verbatim(tampered, SOURCE_DOC))
        self.q.translation = "anything at all"
        self.assertTrue(verify_verbatim(self.q, SOURCE_DOC))

    def test_tampered_original_fails(self):
        md = self.q.render().replace("二十名", "兩百名")
        self.assertFalse(verify_verbatim(md, SOURCE_DOC))
        self.assertFalse(verify_verbatim(Bilingual("不存在的句子"), SOURCE_DOC))

    def test_translation_text_matching_source_does_not_rescue(self):
        # 原文段被改、翻譯段塞真原文 → 仍失敗（翻譯段一律不看）
        fake = Bilingual("捏造的承諾", "zh", translation=SOURCE_DOC, reader_lang="en")
        self.assertFalse(verify_verbatim(fake.render(), SOURCE_DOC))


class TestCrossLanguageReaders(unittest.TestCase):
    """(d) A＝ja、B＝zh 讀同一份結構化結果，各自拿到自己語言。"""

    def test_same_result_two_readers(self):
        result = {
            "score": 0.82,
            "project_id": "p-1",
            "reason": "兩案都在花東推動青年培力，場域互補。",
            "followups": [{"id": "q1", "question": "預計何時開始合作？"}],
        }
        snapshot = {k: v for k, v in result.items()}
        tr = FakeTranslator()
        fields = ["reason", "followups.*.question"]
        a = run(localize_result(result, "ja", tr, fields=fields))
        b = run(localize_result(result, "zh", tr, fields=fields))
        self.assertEqual(a["lang"], "ja")
        self.assertEqual(a["reason"], "[ja] 兩案都在花東推動青年培力，場域互補。")
        self.assertEqual(a["followups"][0]["question"], "[ja] 預計何時開始合作？")
        self.assertEqual(a["score"], 0.82)            # 結構化欄位不翻
        self.assertEqual(a["followups"][0]["id"], "q1")
        self.assertEqual(b["lang"], "zh")
        self.assertEqual(b["reason"], snapshot["reason"])
        self.assertEqual(b["followups"][0]["question"], "預計何時開始合作？")
        # 原結果文字不被改寫
        self.assertEqual(result["reason"], snapshot["reason"])
        # 再讀一次 ja → 用快取，不重打 LLM
        n = len(tr.calls)
        run(localize_result(result, "ja", tr, fields=fields))
        self.assertEqual(len(tr.calls), n)

    def test_human_content_original_plus_translation_and_confirm_original_version(self):
        draft = HumanContent("合作草稿：雙方共同辦理三場走讀。", author_lang="zh")
        tr = FakeTranslator()
        view_ja = run(draft.view_for("ja", tr))
        view_zh = run(draft.view_for("zh", tr))
        self.assertEqual(view_ja.original, draft.text)
        self.assertIn("翻譯", view_ja.render())
        self.assertNotIn("翻譯", view_zh.render())
        # 確認對象 = 原文特定版本；兩位讀者確認的是同一個版本
        self.assertEqual(view_ja.confirm_target(), draft.confirm_target())
        self.assertNotIn("translation", draft.confirm_target())
        confirmed = view_ja.confirm_target()
        view_ja.translation = "changed translation"
        self.assertTrue(confirmation_matches(confirmed, view_ja))   # 翻譯變動不影響
        edited = HumanContent("合作草稿：雙方共同辦理五場走讀。", author_lang="zh")
        self.assertFalse(confirmation_matches(confirmed, edited))  # 原文改了要重確認


if __name__ == "__main__":
    unittest.main()
