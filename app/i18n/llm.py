"""LLM 輸出語言共用層（EPIC #205 / #207；#204 第 3、4、5 題定案）。

原則：
- 判斷規則（標準 YAML）與系統提示本體只維護**中文一份**，不翻規則；
  送給 LLM 前由這裡統一加上「以 {lang} 回覆」的輸出語言指示。
- zh（預設）**不加任何指示** —— 既有中文行為、提示字串一個字都不變。
- AI 產生的內容依「閱讀者」語言產生：同一份結構化結果（例如媒合判斷）
  可被不同語言的人讀，各自用 `localize_result()` 取自己語言的版本；
  結構化欄位（分數、代碼、id）不翻，只翻指定的文字欄位。

套用點：Eva 一般對話（app/core/copilot.py）、法規檢核摘要、媒合（建議卡、判斷說明、補問）。
"""
from __future__ import annotations

import copy
from typing import Any, Awaitable, Callable, Iterable

from app.i18n import DEFAULT_LANG, current_lang, normalize_lang

# 給 LLM 看的語言名稱（指示本身用英文寫，所有模型都看得懂）
LANG_NAMES: dict[str, str] = {
    "zh": "Traditional Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}

DIRECTIVE_MARK = "[output-language]"

# 翻譯器：async (text, target_lang) -> translated text
Translator = Callable[[str, str], Awaitable[str]]


def resolve_lang(lang: Any = None) -> str:
    """lang 省略 → 本連線語言（current_lang）；否則正規化。"""
    return current_lang() if lang is None else normalize_lang(lang)


def language_directive(lang: Any = None) -> str:
    """回「以 {lang} 回覆」的系統提示片段；zh 回空字串。"""
    lang = resolve_lang(lang)
    if lang == DEFAULT_LANG:
        return ""
    name = LANG_NAMES[lang]
    return (
        f"{DIRECTIVE_MARK} The reader's language is {name}. "
        f"Write your entire reply in {name}, regardless of the language used in the "
        f"instructions above or in the data (rules, tool results, documents). "
        f"Keep JSON keys, codes, ids, numbers and URLs unchanged. "
        f"When quoting an original document verbatim, keep the quote in its original "
        f"language exactly as written; do not translate inside the quote."
    )


def with_output_language(system_prompt: str, lang: Any = None) -> str:
    """系統提示 + 輸出語言指示（zh 原樣回傳）。重複套用不會疊加。"""
    directive = language_directive(lang)
    if not directive or DIRECTIVE_MARK in (system_prompt or ""):
        return system_prompt
    return f"{system_prompt}\n\n{directive}" if system_prompt else directive


def apply_output_language(messages: list, lang: Any = None) -> list:
    """對訊息串（langchain messages 或 {"role","content"} dict）套輸出語言。

    有 system 訊息 → 加在第一則 system 後；沒有 → 前插一則 system。回新 list，不改原物件。
    """
    directive = language_directive(lang)
    if not directive:
        return list(messages)
    out = list(messages)
    for i, m in enumerate(out):
        if _role(m) == "system":
            out[i] = _with_content(m, with_output_language(_content(m), lang))
            return out
    return [_make_system(directive, like=out[0] if out else None)] + out


def _role(m: Any) -> str | None:
    if isinstance(m, dict):
        return m.get("role")
    t = getattr(m, "type", None)
    return "system" if t == "system" else t


def _content(m: Any) -> str:
    return (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""


def _with_content(m: Any, content: str) -> Any:
    if isinstance(m, dict):
        return {**m, "content": content}
    try:
        return m.model_copy(update={"content": content})
    except AttributeError:  # pragma: no cover — 非 pydantic 物件
        new = copy.copy(m)
        new.content = content
        return new


def _make_system(content: str, like: Any = None) -> Any:
    if like is None or isinstance(like, dict):
        return {"role": "system", "content": content}
    from langchain_core.messages import SystemMessage

    return SystemMessage(content=content)


def make_llm_translator(make_llm: Callable[..., Any], **llm_kwargs: Any) -> Translator:
    """用專案的 make_llm 組翻譯器（測試可直接塞假 translator）。"""

    async def _translate(text: str, target_lang: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        target = normalize_lang(target_lang)
        llm = make_llm(streaming=False, **llm_kwargs)
        resp = await llm.ainvoke([
            SystemMessage(content=(
                f"Translate the user's text into {LANG_NAMES[target]}. "
                "Output only the translation, no notes. Keep numbers, ids and URLs unchanged."
            )),
            HumanMessage(content=text),
        ])
        return (getattr(resp, "content", "") or "").strip()

    return _translate


async def localize_result(
    result: dict,
    reader_lang: Any,
    translate: Translator,
    *,
    fields: Iterable[str],
    source_lang: str = DEFAULT_LANG,
) -> dict:
    """同一份結構化結果 → 給某位閱讀者的版本（只翻 fields 指定的文字欄位）。

    - 原結果不被修改；閱讀者語言 = 來源語言 → 原樣（深拷貝）回傳、不呼叫翻譯器。
    - fields 支援點路徑（"reason"、"card.summary"）與清單展開（"items.*.reason"）。
    - 翻譯結果快取在原結果的 `_i18n[lang][path]`，A、B 輪流讀不重複呼叫 LLM。
    """
    lang = normalize_lang(reader_lang)
    out = copy.deepcopy({k: v for k, v in result.items() if k != "_i18n"})
    out["lang"] = lang
    if lang == normalize_lang(source_lang):
        return out
    cache: dict = result.setdefault("_i18n", {}).setdefault(lang, {})
    for field in fields:
        for path, value, setter in _walk(out, field.split(".")):
            if not isinstance(value, str) or not value.strip():
                continue
            key = f"{path}\x00{value}"
            if key not in cache:
                cache[key] = await translate(value, lang)
            setter(cache[key])
    return out


def _walk(obj: Any, parts: list[str], prefix: str = ""):
    """依路徑走結構，yield (路徑, 值, setter)。"""
    if not parts:
        return
    head, rest = parts[0], parts[1:]
    if head == "*":
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from _walk_item(obj, i, item, rest, f"{prefix}{i}")
        return
    if isinstance(obj, dict) and head in obj:
        yield from _walk_item(obj, head, obj[head], rest, f"{prefix}{head}")


def _walk_item(container: Any, key: Any, value: Any, rest: list[str], path: str):
    if not rest:
        def _set(v, c=container, k=key):
            c[k] = v
        yield path, value, _set
    else:
        yield from _walk(value, rest, path + ".")


__all__ = [
    "DIRECTIVE_MARK",
    "LANG_NAMES",
    "Translator",
    "apply_output_language",
    "language_directive",
    "localize_result",
    "make_llm_translator",
    "resolve_lang",
    "with_output_language",
]
