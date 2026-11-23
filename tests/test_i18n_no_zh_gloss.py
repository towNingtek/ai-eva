"""#222：外文回覆不在括號附中文原詞（假 LLM，不打網路）。"""
from __future__ import annotations

import asyncio
import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.i18n.llm import (
    NO_ZH_GLOSS_MARK,
    apply_output_language,
    language_directive,
    strip_zh_gloss,
    with_output_language,
)
from app.i18n.quote import Bilingual, extract_original, extract_translation


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[list] = []

    async def ainvoke(self, msgs):
        self.calls.append(list(msgs))
        return AIMessage(content=self.reply)


def ask(llm: FakeLLM, lang: str, question: str = "다음에 뭘 해야 하나요?") -> str:
    msgs = apply_output_language(
        [SystemMessage(content="你是 Eva。"), HumanMessage(content=question)], lang
    )
    resp = asyncio.run(llm.ainvoke(msgs))
    return strip_zh_gloss(resp.content, lang)


class TestSystemPromptRule(unittest.TestCase):
    def test_foreign_langs_have_rule(self):
        for lang in ("en", "ja", "ko"):
            d = language_directive(lang)
            self.assertIn(NO_ZH_GLOSS_MARK, d, lang)
            self.assertIn("parentheses", d)
            self.assertIn("Tool descriptions", d)
            self.assertIn(NO_ZH_GLOSS_MARK, with_output_language("你是 Eva。", lang))

    def test_zh_has_no_rule(self):
        self.assertEqual(language_directive("zh"), "")
        self.assertEqual(with_output_language("你是 Eva。", "zh"), "你是 Eva。")
        self.assertNotIn(NO_ZH_GLOSS_MARK, with_output_language("你是 Eva。", "zh"))

    def test_rule_sent_to_llm(self):
        llm = FakeLLM("ok")
        ask(llm, "ko")
        system = llm.calls[0][0]
        self.assertIsInstance(system, SystemMessage)
        self.assertIn(NO_ZH_GLOSS_MARK, system.content)


class TestStripGloss(unittest.TestCase):
    def test_korean_reported_case(self):
        llm = FakeLLM("다음 단계: 프로젝트 철학(計畫理念) 보충문 추가")
        out = ask(llm, "ko")
        self.assertEqual(out, "다음 단계: 프로젝트 철학 보충문 추가")
        self.assertNotIn("計畫理念", out)

    def test_fullwidth_and_spaced(self):
        self.assertEqual(
            strip_zh_gloss("프로젝트 철학 （計畫理念）과 예산 (預算 編列) 확인", "ko"),
            "프로젝트 철학과 예산 확인",
        )
        self.assertEqual(
            strip_zh_gloss("Use the regulation check (法規檢核) tool.", "en"),
            "Use the regulation check tool.",
        )

    def test_non_gloss_parentheses_kept(self):
        for text in (
            "Budget (NT$ 300,000) approved.",
            "예산 (약 30만 원) 확인",
            "Philosophy (計畫理念, project philosophy)",
        ):
            self.assertEqual(strip_zh_gloss(text, "en"), text)

    def test_japanese_keeps_japanese_kanji(self):
        self.assertEqual(strip_zh_gloss("申請書（様式）を確認", "ja"), "申請書（様式）を確認")
        self.assertEqual(
            strip_zh_gloss("プロジェクト理念（計畫理念）を追加", "ja"), "プロジェクト理念を追加"
        )

    def test_zh_untouched(self):
        text = "補充計畫理念(計畫理念)段落"
        self.assertEqual(strip_zh_gloss(text, "zh"), text)

    def test_quote_block_untouched(self):
        b = Bilingual(
            original="本計畫理念（計畫理念）以社區為本。",
            source_lang="zh",
            translation="이 프로젝트 철학(計畫理念)은 지역 사회 중심입니다.",
            reader_lang="ko",
        )
        rendered = b.render()
        reply = f"프로젝트 철학(計畫理念) 보충문을 추가하세요.\n\n{rendered}\n\n> 본문(計畫書) 인용"
        llm = FakeLLM(reply)
        out = ask(llm, "ko")
        self.assertTrue(out.startswith("프로젝트 철학 보충문을 추가하세요."))
        self.assertIn(rendered, out)
        self.assertEqual(extract_original(out), b.original)
        self.assertEqual(extract_translation(out), b.translation)
        self.assertTrue(out.endswith("> 본문(計畫書) 인용"))


if __name__ == "__main__":
    unittest.main()
