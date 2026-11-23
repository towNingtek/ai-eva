"""原文＋翻譯（EPIC #205 / #207；#204 第 4、5 題定案）。

- 引用計畫書原文：照原語言**逐字**顯示，下方附閱讀者語言的翻譯並標「翻譯」。
- 逐字核對（防 LLM 改寫原文）**只對原文段做**；翻譯段只供閱讀，內容怎麼變都不影響核對。
- 人寫的內容（合作草稿、邀請附言、補問回答）存原文；對方語言不同 → 看原文＋翻譯。
- **確認關卡的對象是原文的特定版本**（`version` = 原文內容雜湊），翻譯不參與。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.i18n import DEFAULT_LANG, normalize_lang
from app.i18n.llm import Translator

# 翻譯段標籤：一律含「翻譯」二字（#204 定案），非中文讀者再附自己語言的字
TRANSLATION_LABELS: dict[str, str] = {
    "zh": "翻譯",
    "en": "翻譯 Translation",
    "ja": "翻譯 翻訳",
    "ko": "翻譯 번역",
}
ORIGINAL_LABELS: dict[str, str] = {
    "zh": "原文",
    "en": "原文 Original",
    "ja": "原文 原文",
    "ko": "原文 원문",
}

# 機器可解析的段落標記（HTML 註解，Markdown 渲染時看不到）
_ORIG_OPEN, _ORIG_CLOSE = "<!--quote:original-->", "<!--/quote:original-->"
_TR_OPEN, _TR_CLOSE = "<!--quote:translation-->", "<!--/quote:translation-->"
_ORIG_RE = re.compile(re.escape(_ORIG_OPEN) + r"\n?(.*?)\n?" + re.escape(_ORIG_CLOSE), re.S)
_TR_RE = re.compile(re.escape(_TR_OPEN) + r"\n?(.*?)\n?" + re.escape(_TR_CLOSE), re.S)


def text_version(text: str) -> str:
    """原文版本識別：內容 sha256 前 16 碼（同內容同版本、改一字就換版本）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


@dataclass
class Bilingual:
    """一段「原文 ＋（可選）翻譯」。原文是唯一權威；翻譯只供閱讀。"""

    original: str
    source_lang: str = DEFAULT_LANG
    translation: str | None = None
    reader_lang: str = DEFAULT_LANG
    version: str = field(default="")

    def __post_init__(self) -> None:
        self.source_lang = normalize_lang(self.source_lang)
        self.reader_lang = normalize_lang(self.reader_lang)
        if not self.version:
            self.version = text_version(self.original)

    @property
    def needs_translation(self) -> bool:
        return self.source_lang != self.reader_lang

    def render(self) -> str:
        """Markdown：原文逐字（引用區塊）＋ 下方「翻譯」段（語言相同時不附）。"""
        quoted = "\n".join(f"> {ln}" if ln else ">" for ln in self.original.split("\n"))
        parts = [_ORIG_OPEN, quoted, _ORIG_CLOSE]
        if self.needs_translation and self.translation:
            label = TRANSLATION_LABELS[self.reader_lang]
            parts += ["", _TR_OPEN, f"**{label}**：{self.translation}", _TR_CLOSE]
        return "\n".join(parts)

    def confirm_target(self) -> dict:
        """確認關卡要記錄／比對的對象：原文的特定版本（不含翻譯）。"""
        return {"original": self.original, "source_lang": self.source_lang, "version": self.version}


async def bilingual(original: str, source_lang: Any, reader_lang: Any,
                    translate: Translator | None = None) -> Bilingual:
    """組「原文＋翻譯」；語言不同且有翻譯器才翻。"""
    b = Bilingual(original=original, source_lang=source_lang, reader_lang=reader_lang)
    if b.needs_translation and translate is not None and original.strip():
        b.translation = await translate(original, b.reader_lang)
    return b


def extract_original(rendered: str) -> str:
    """從 render() 的輸出取回原文（去掉引用符號）；只看原文段。"""
    m = _ORIG_RE.search(rendered or "")
    if not m:
        return ""
    lines = []
    for ln in m.group(1).split("\n"):
        if ln.startswith("> "):
            lines.append(ln[2:])
        elif ln == ">":
            lines.append("")
        else:
            lines.append(ln)
    return "\n".join(lines)


def extract_translation(rendered: str) -> str | None:
    m = _TR_RE.search(rendered or "")
    if not m:
        return None
    body = m.group(1)
    return body.split("：", 1)[1] if "：" in body else body


def verify_verbatim(quote: "Bilingual | str", source_text: str, *, ignore_whitespace: bool = True) -> bool:
    """逐字核對：引用的**原文段**是否真的出現在來源全文中。翻譯段一律不看。

    quote 可給 Bilingual 物件或 render() 後的字串。
    """
    original = quote.original if isinstance(quote, Bilingual) else extract_original(quote)
    if not original.strip():
        return False
    if ignore_whitespace:
        return _normalize_ws(original) in _normalize_ws(source_text)
    return original in (source_text or "")


@dataclass
class HumanContent:
    """人寫的內容（合作草稿、邀請附言、補問回答）：存原文＋作者語言＋版本。"""

    text: str
    author_lang: str = DEFAULT_LANG
    version: str = field(default="")

    def __post_init__(self) -> None:
        self.author_lang = normalize_lang(self.author_lang)
        if not self.version:
            self.version = text_version(self.text)

    async def view_for(self, reader_lang: Any, translate: Translator | None = None) -> Bilingual:
        """給某位閱讀者看：同語言 → 原文；不同 → 原文＋翻譯。"""
        b = await bilingual(self.text, self.author_lang, reader_lang, translate)
        b.version = self.version
        return b

    def confirm_target(self) -> dict:
        return {"original": self.text, "source_lang": self.author_lang, "version": self.version}


def confirmation_matches(confirmed: dict, current: "Bilingual | HumanContent") -> bool:
    """確認紀錄是否仍對應目前原文版本（原文改了就要重新確認；翻譯變動不影響）。"""
    target = current.confirm_target()
    return bool(confirmed) and confirmed.get("version") == target["version"] \
        and text_version(confirmed.get("original", "")) == target["version"]


__all__ = [
    "Bilingual",
    "HumanContent",
    "ORIGINAL_LABELS",
    "TRANSLATION_LABELS",
    "bilingual",
    "confirmation_matches",
    "extract_original",
    "extract_translation",
    "text_version",
    "verify_verbatim",
]
