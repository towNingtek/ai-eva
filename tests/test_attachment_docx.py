"""附件建專案支援南投 DOCX 計畫書範本（ai-eva#186）。

範本 fixture 是 tplanet-multi-tenant `apps/tplanet-AI/public/docx-template.docx`
（前台公開下載的南投計畫書範本）的逐位元組複本。
"""
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from docx import Document

from app import main

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "nantou_template.docx")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _tmp_docx(build) -> str:
    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    doc = Document()
    build(doc)
    doc.save(path)
    return path


class NantouTemplateTests(TestCase):
    def test_template_text_has_plan_name_and_budget(self):
        text = main._read_attachment({"name": "計畫書.docx", "mime": DOCX_MIME, "path": FIXTURE})
        self.assertIsNotNone(text)
        self.assertIn("計畫名稱：國際事務推動運用計畫", text)
        self.assertIn("經費概數：1909000", text)
        self.assertIn("單位名稱：計畫處", text)
        self.assertIn("計畫期間：114.1-114.12", text)
        self.assertIn("實施區域：南投縣全區", text)

    def test_template_fields_in_template_order(self):
        text = main._read_attachment({"name": "x.docx", "mime": "", "path": FIXTURE})
        keys = [ln.split("：", 1)[0] for ln in text.splitlines() if "：" in ln]
        self.assertEqual(keys, list(main._NANTOU_DOCX_FIELDS))

    def test_routed_by_mime_only(self):
        text = main._read_attachment({"name": "沒有副檔名", "mime": DOCX_MIME, "path": FIXTURE})
        self.assertIn("計畫名稱：國際事務推動運用計畫", text)


class NonTemplateDocxTests(TestCase):
    def test_freeform_docx_returns_full_text(self):
        def build(doc):
            doc.add_paragraph("社區食農教育推廣計畫")
            doc.add_paragraph("預計於埔里鎮辦理三場工作坊。")
            t = doc.add_table(rows=1, cols=2)
            t.cell(0, 0).text, t.cell(0, 1).text = "預算", "50 萬元"
        path = _tmp_docx(build)
        try:
            text = main._read_attachment({"name": "free.docx", "mime": DOCX_MIME, "path": path})
        finally:
            os.remove(path)
        self.assertIsNotNone(text)
        self.assertNotIn("南投計畫書範本", text)
        self.assertIn("社區食農教育推廣計畫", text)
        self.assertIn("預算 | 50 萬元", text)

    def test_merged_cells_not_repeated(self):
        def build(doc):
            t = doc.add_table(rows=1, cols=3)
            t.cell(0, 0).merge(t.cell(0, 1)).text = "合併"
            t.cell(0, 2).text = "右"
        path = _tmp_docx(build)
        try:
            text = main._read_attachment({"name": "m.docx", "mime": "", "path": path})
        finally:
            os.remove(path)
        self.assertEqual(text, "合併 | 右")

    def test_empty_docx_returns_none(self):
        path = _tmp_docx(lambda doc: None)
        try:
            self.assertIsNone(main._read_attachment({"name": "e.docx", "mime": "", "path": path}))
        finally:
            os.remove(path)

    def test_broken_docx_returns_none_without_raising(self):
        fd, path = tempfile.mkstemp(suffix=".docx")
        os.write(fd, b"not a zip")
        os.close(fd)
        try:
            self.assertIsNone(main._read_attachment({"name": "bad.docx", "mime": DOCX_MIME, "path": path}))
        finally:
            os.remove(path)


class UploadGateTests(TestCase):
    def test_docx_is_readable_and_goes_through_copilot(self):
        """DOCX 進來會被收下並送進既有 copilot 流程（建專案仍由確認閘把關）。"""
        msg = SimpleNamespace(elements=[SimpleNamespace(name="計畫書.docx", mime=DOCX_MIME, path=FIXTURE)])
        fake_cl = MagicMock()
        fake_cl.Message.return_value.send = AsyncMock()
        with patch.object(main, "cl", fake_cl), \
                patch.object(main, "_run_with_attachments", new=AsyncMock()) as run:
            asyncio.run(main._handle_cms_attachments(msg, "幫我建專案", runtime=None, history=[]))
        run.assert_awaited_once()
        readable = run.await_args.args[2]
        self.assertEqual([a["name"] for a in readable], ["計畫書.docx"])
        fake_cl.user_session.set.assert_any_call("pending_attachments", readable)

    def test_other_office_formats_still_rejected(self):
        msg = SimpleNamespace(elements=[SimpleNamespace(name="old.doc", mime="application/msword", path=FIXTURE)])
        fake_cl = MagicMock()
        fake_cl.Message.return_value.send = AsyncMock()
        with patch.object(main, "cl", fake_cl), \
                patch.object(main, "_run_with_attachments", new=AsyncMock()) as run:
            asyncio.run(main._handle_cms_attachments(msg, "幫我建專案", runtime=None, history=[]))
        run.assert_not_awaited()
        sent = fake_cl.Message.call_args.kwargs.get("content", "")
        self.assertIn("old.doc", sent)
