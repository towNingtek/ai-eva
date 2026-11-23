"""Label and chunk：philosophy 切段、標籤、原文位置（ai-eva #199，MVP 步驟 3-2）。

- 切段：依句末標點（。！？!?；;）與換行切成段落，每段記原文起訖位置
  （``philosophy[start:end] == text`` 逐字成立）。
- 標籤：只來自 #182 的判斷結果（``capability.analyze`` / ``judge`` 的 evidence）。
  依據區間與段落重疊，該段就標上該類（B1–B8）與方向（concrete→OFFER、aim→NEED，
  兩者都有→BOTH）。沒有任何依據重疊的段落不存（不臆測標籤），所以存下來的每段都 ≥1 個標籤。
- 重跑：以 philosophy 內容雜湊（sha256）判斷；雜湊相同沿用已存結果，不同就重跑
  3-1（判斷）與 3-2（切段標籤）。
- 對使用者隱藏：chunk 與 B 代號只供內部媒合比對；給使用者的文字一律經
  ``user_message`` / ``scrub`` 產生，不含 chunk 與 B1–B8 代號。

存放：``store`` 是任何類 dict 物件（``get`` / ``__setitem__``），key 為 philosophy 所屬識別
（例如計畫 id）。預設可用 ``MemoryStore``；正式環境可換成資料庫包裝。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, MutableMapping, Optional

from app.matching import capability as cap

ALGO_VERSION = 1
_SENTENCE = re.compile(r"[^。！？!?；;\n]*(?:[。！？!?；;]+|\n+|$)")
_B_CODE = re.compile(r"(?<![A-Za-z0-9])[Bb]\s*[1-8](?![0-9])")
DIRECTION_TEXT = {cap.OFFER: "可提供", cap.NEED: "有需求", cap.BOTH: "可提供也有需求"}


def content_hash(philosophy: str) -> str:
    return hashlib.sha256((philosophy or "").encode("utf-8")).hexdigest()


def split_segments(philosophy: str) -> list[tuple[int, int]]:
    """切段 → [(start, end)]；去掉前後空白，空段不算。"""
    text = philosophy or ""
    spans = []
    for m in _SENTENCE.finditer(text):
        s, e = m.start(), m.end()
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            spans.append((s, e))
    return spans


def _evidence_spans(philosophy: str, judgement: dict) -> list[tuple[int, int, str, str]]:
    """judgement 的依據 → [(start, end, B代號, 方向)]；只收逐字存在於 philosophy 的依據。"""
    out = []
    for b, info in ((judgement or {}).get("capabilities") or {}).items():
        if b not in cap.B_KEYS:
            continue
        for ev in (info or {}).get("evidence") or []:
            quote, kind = ev.get("quote") or "", ev.get("kind")
            if not quote or kind not in cap.KINDS:
                continue
            start = ev.get("start")
            if not isinstance(start, int) or philosophy[start:start + len(quote)] != quote:
                start = philosophy.find(quote)
            if start < 0:
                continue
            out.append((start, start + len(quote), b, cap.KINDS[kind]))
    return out


def label_chunks(philosophy: str, judgement: dict) -> list[dict]:
    """philosophy + #182 判斷 → 有標籤的 chunk 清單（純函式，可單獨測）。"""
    text = philosophy or ""
    evs = _evidence_spans(text, judgement)
    chunks = []
    for s, e in split_segments(text):
        dirs: dict[str, set] = {}
        for es, ee, b, d in evs:
            if es < e and ee > s:  # 區間重疊
                dirs.setdefault(b, set()).add(d)
        if not dirs:
            continue
        labels = [
            {"capability": b, "direction": cap.BOTH if len(dirs[b]) > 1 else next(iter(dirs[b]))}
            for b in cap.B_KEYS if b in dirs
        ]
        chunks.append({"index": len(chunks), "start": s, "end": e, "text": text[s:e], "labels": labels})
    return chunks


class MemoryStore(dict):
    """最簡單的存放：記憶體 dict。"""


def ensure_chunks(
    key: str,
    philosophy: str,
    store: MutableMapping[str, Any],
    *,
    analyzer: Optional[Callable[[str], dict]] = None,
    llm: Any = None,
) -> dict:
    """取得 philosophy 的 chunk 紀錄；雜湊沒變就沿用，變了（或沒有）就重跑 3-1、3-2 並存起來。

    回傳 ``{"hash", "version", "judgement", "chunks", "recomputed"}``（內部用，勿直接給使用者）。
    """
    h = content_hash(philosophy)
    cached = store.get(key)
    if cached and cached.get("hash") == h and cached.get("version") == ALGO_VERSION:
        return {**cached, "recomputed": False}
    if analyzer is None:
        analyzer = lambda p: cap.analyze(p, llm=llm)  # noqa: E731
    judgement = analyzer(philosophy)
    record = {
        "hash": h,
        "version": ALGO_VERSION,
        "judgement": judgement,
        "chunks": label_chunks(philosophy, judgement),
    }
    store[key] = record
    return {**record, "recomputed": True}


def scrub(text: str) -> str:
    """移除使用者文字裡的 B1–B8 代號（保險用）。"""
    return re.sub(r"\s{2,}", " ", _B_CODE.sub("", text or "")).strip()


def user_message(record: dict, *, registry: Optional[dict] = None) -> str:
    """給使用者看的摘要：只講能力類別名稱與方向，不含 chunk、原文位置與 B 代號。"""
    registry = registry if registry is not None else cap.load_registry()
    caps = ((record or {}).get("judgement") or {}).get("capabilities") or {}
    parts = []
    for b in cap.B_KEYS:
        d = (caps.get(b) or {}).get("direction")
        if d in DIRECTION_TEXT:
            name = (registry.get(b) or {}).get("名稱") or (caps.get(b) or {}).get("name") or "其他能力"
            parts.append(f"{name}（{DIRECTION_TEXT[d]}）")
    if not parts:
        return "已讀過計畫理念，目前資料還不足以判斷能力方向。"
    return scrub(f"已讀過計畫理念，找到的能力線索：{'、'.join(parts)}。{cap.INFERENCE_LABEL}")
