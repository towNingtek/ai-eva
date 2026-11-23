"""從計畫理念（philosophy）判 B1–B8 與方向（ai-eva #182）。

分工（媒合標準「YAML 訂規則，LLM 做判斷，人做決定」）：
- LLM：讀 philosophy，對每一類回原文依據（quote）與 kind（concrete＝具體做法／對象／成果；aim＝只寫目標或方向）。
- 程式：
  1. 每段 quote 必須是 philosophy 逐字存在的子字串，不是就丟掉並記錄（dropped + logger.warning）。
  2. 方向依標準 v1.1 Q1 由留下的依據算出：只有 concrete＝OFFER、只有 aim＝NEED、兩者都有＝BOTH、
     沒有依據＝none（不臆測）。
  3. 每一類（B1–B8）都有結果，不缺 key；整份結果標「推論（AI，未經 Owner 確認）」。

提示詞在 app/matching/prompts/capability.yaml，不寫死在程式。LLM 可注入（測試用假物件，不打真模型）：
    analyze(philosophy, llm=fake)
llm 可以是 callable(messages) -> str，或有 .invoke(messages) 的 LangChain chat model。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
STANDARD = HERE / "standard_yunlin_v1.yaml"
PROMPT = HERE / "prompts" / "capability.yaml"

B_KEYS = [f"B{i}" for i in range(1, 9)]
NEED, OFFER, BOTH, NONE = "NEED", "OFFER", "BOTH", "none"
KINDS = {"concrete": OFFER, "aim": NEED}
INFERENCE_LABEL = "推論（AI，未經 Owner 確認）"
SEMANTICS = "INFERENCE"
CONFIRMATION = "AI_CANDIDATE"


def load_registry(path: Path | str = STANDARD) -> dict:
    """B1–B8 名稱與典型內容，取自媒合標準 YAML（不在這裡另抄一份）。"""
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    reg = d.get("capability_registry") or {}
    return {k: reg[k] for k in B_KEYS if isinstance(reg.get(k), dict)}


def load_prompt(path: Path | str = PROMPT) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_messages(philosophy: str, *, prompt: dict | None = None, registry: dict | None = None) -> list[dict]:
    prompt = prompt if prompt is not None else load_prompt()
    registry = registry if registry is not None else load_registry()
    reg_text = "\n".join(
        f"  {k} {v.get('名稱', '')}：{'、'.join(v.get('典型內容') or [])}" for k, v in registry.items()
    )
    return [
        {"role": "system", "content": prompt["system"].format(registry=reg_text)},
        {"role": "user", "content": prompt["user"].format(philosophy=philosophy)},
    ]


def _call(llm: Any, messages: list[dict]) -> str:
    if hasattr(llm, "invoke"):
        out = llm.invoke([(m["role"], m["content"]) for m in messages])
        return getattr(out, "content", out)
    return llm(messages)


def _default_llm():
    from app.core.llm import make_llm  # 延後載入：測試注入假物件時不需要 langchain / LiteLLM 設定

    return make_llm(temperature=0, streaming=False, json_mode=True)


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)


def parse_reply(reply: Any) -> dict:
    """LLM 回覆 → dict。可接受 dict、JSON 字串、包在 ```json 裡的字串；壞掉就回 {}（全部 none）。"""
    if isinstance(reply, dict):
        return reply
    text = _FENCE.sub("", str(reply or "")).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        logger.warning("capability: LLM 回覆不是 JSON 物件，全部視為無依據")
        return {}
    return data


def _items(raw: Any) -> list:
    """一類的原始依據 → list。容許 {"evidence": [...]}、單一 dict、單一字串。"""
    if isinstance(raw, dict):
        raw = raw.get("evidence", raw.get("依據", [raw]))
    if isinstance(raw, (str, dict)):
        raw = [raw]
    return raw if isinstance(raw, list) else []


def direction_of(kinds: set[str]) -> str:
    dirs = {KINDS[k] for k in kinds if k in KINDS}
    if not dirs:
        return NONE
    return BOTH if len(dirs) == 2 else dirs.pop()


def judge(philosophy: str, data: dict, *, registry: dict | None = None) -> dict:
    """把 LLM 的原始判斷驗證成最終結果（不呼叫 LLM，可單獨測）。"""
    registry = registry if registry is not None else load_registry()
    text = philosophy or ""
    caps, dropped = {}, []
    for b in B_KEYS:
        evidence, seen = [], set()
        for item in _items(data.get(b)):
            if isinstance(item, str):
                quote, kind = item, None
            elif isinstance(item, dict):
                quote, kind = item.get("quote") or item.get("text") or "", item.get("kind")
            else:
                continue
            quote = quote if isinstance(quote, str) else str(quote)
            kind = str(kind).strip().lower() if kind is not None else None
            reason = None
            if not quote.strip():
                reason = "空白依據"
            elif quote not in text:
                reason = "不是 philosophy 的逐字子字串"
            elif kind not in KINDS:
                reason = f"kind 無法辨識（{kind!r}），不臆測方向"
            if reason:
                dropped.append({"capability": b, "quote": quote, "kind": kind, "reason": reason})
                logger.warning("capability: 丟棄 %s 依據 %r（%s）", b, quote, reason)
                continue
            if (quote, kind) in seen:
                continue
            seen.add((quote, kind))
            evidence.append({"quote": quote, "kind": kind, "start": text.index(quote)})
        direction = direction_of({e["kind"] for e in evidence})
        caps[b] = {
            "name": (registry.get(b) or {}).get("名稱", ""),
            "direction": direction,
            "evidence": evidence if direction != NONE else [],
            "label": INFERENCE_LABEL,
        }
    return {
        "label": INFERENCE_LABEL,
        "semantics": SEMANTICS,
        "confirmation": CONFIRMATION,
        "capabilities": caps,
        "dropped": dropped,
    }


def analyze(
    philosophy: str,
    *,
    llm: Any | Callable[[list[dict]], str] | None = None,
    prompt: dict | None = None,
    registry: dict | None = None,
) -> dict:
    """philosophy → B1–B8 每一類的方向與原文依據（標「推論（AI，未經 Owner 確認）」）。"""
    registry = registry if registry is not None else load_registry()
    if not (philosophy or "").strip():
        return judge("", {}, registry=registry)
    llm = llm if llm is not None else _default_llm()
    reply = _call(llm, build_messages(philosophy, prompt=prompt, registry=registry))
    return judge(philosophy, parse_reply(reply), registry=registry)
