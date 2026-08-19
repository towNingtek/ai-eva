"""法規檢核標準（YAML）載入器。

YAML 訂規則、LLM 做判斷 —— 這個模組只負責把規則讀進來並提供查表。
換 corpus/standard_*.yaml 就換行為，程式不動（R0 說的「YAML 熱換」）。
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CORPUS = Path(__file__).parent / "corpus"
DEFAULT_STANDARD = "standard_yunlin_v1.yaml"


@lru_cache(maxsize=4)
def load(name: str = DEFAULT_STANDARD) -> dict:
    path = CORPUS / name
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    logger.info("loaded standard %s (%s)", name, data.get("standard", {}).get("version"))
    return data


def route(std: dict, tag: str, confidence: str = "high") -> tuple[str, str]:
    """(tag, 判定信心) → (報告區塊, 嚴重度)。

    `false_positive_policy.on_uncertain: 保守不列入違規` 在這裡生效：信心不足的
    就算類型是實質管制/罰則，也降到合規提醒 —— 誤報也是錯，且人工複核成本高。
    """
    routing = std.get("verdict_routing") or {}
    spec = routing.get(tag) or {"section": "合規提醒", "severity": "low"}
    section, severity = spec.get("section", "合規提醒"), spec.get("severity", "low")
    policy = (std.get("false_positive_policy") or {}).get("on_uncertain") or ""
    if confidence == "low" and "保守" in policy and section == "違規風險":
        return "合規提醒", "medium"
    return section, severity


def sections(std: dict) -> list[str]:
    return (std.get("output") or {}).get("sections") or ["摘要", "違規風險", "合規提醒", "需補語料", "免責"]


def covered_domains(std: dict) -> list[str]:
    return (std.get("coverage") or {}).get("covered") or []


def judge_model(std: dict) -> str | None:
    """判定模型別名：環境變數 > YAML > None（交給 core/llm.py 的預設）。"""
    import os
    return os.getenv("REGCHECK_JUDGE_MODEL") or ((std.get("standard") or {}).get("judge") or {}).get("model")


def applicability_gates(std: dict) -> list[dict]:
    """法規層級的適用前提（見 YAML 的 applicability_gate）。"""
    return std.get("applicability_gate") or []


def scale_thresholds(std: dict) -> list[dict]:
    """YAML 點名「一定要看規模才算」的條文（目前 3 條）。

    這幾條會單獨跑一次判定，不跟大批混在一起 —— 埋在 40 題的批次裡，
    判出來的結果會被同批其他題目影響而飄動（實測環評§5 就是這樣）。
    """
    return std.get("scale_thresholds") or []


def scale_thresholds_text(std: dict) -> str:
    """規模門檻餵給 judge 的文字（門檻固定，套用要 LLM 從計畫書抓規模）。"""
    lines = []
    for t in std.get("scale_thresholds") or []:
        note = f"（{t['note']}）" if t.get("note") else ""
        lines.append(f"- {t.get('law')} {t.get('article')}：{t.get('trigger')}{note}")
    return "\n".join(lines)
