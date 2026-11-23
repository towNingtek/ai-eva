"""多輪狀態機核心。

規則 YAML 格式（參考媒合標準 v1.1 的 status_rules／status_transition／clarify_questions）::

    status_transition:
      from: CLARIFY_FIRST          # 起點狀態（缺最低欄位時）
      to: EXPLORE                  # 最低欄位補齊後的狀態
      minimum_fields: [a, b]       # list，或 {群組: 欄位} 的 mapping（如 {NEED: 用途, OFFER: 可提供形式}）
      unknown_counts_as_filled: false
      unknown_values: [還不知道]   # 視為「還不知道」的回答（選填）

    status_rules:                  # 選填；依 YAML 順序評估，第一條成立的 when 勝出
      EXCLUDED:
        when: {fact_in: {可分享: [否]}}
      EXPLORE:
        when: {all_filled: minimum_fields}
      CLARIFY_FIRST:
        when: {always: true}

    clarify_questions:             # list of {field, ask}，或 {群組: {欄位: 題目}}
      - {field: a, ask: "……？"}

when 條件（dict 內各鍵為 AND；list of dict 為 OR）::

    always: true
    all_filled / any_filled / all_missing / any_missing: [欄位…] 或 "minimum_fields"
    fact_in:  {欄位: [值…]}
    fact_gte: {欄位: 數字}
    fact_lt:  {欄位: 數字}

status_transition 沒寫 from/to 時，取 status_rules（或 status_transition.states）的前兩個狀態；
也可在 load_rules(..., start=, target=) 覆寫。沒列 minimum_fields 時，所有題目欄位都算最低欄位。

沒有任何 when 成立時，依 status_transition：最低欄位全補齊 → to，否則 → from。
狀態只用規則算，不呼叫 AI；同一輸入永遠得到同一結果。
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


class _Unknown:
    """「還不知道」的哨兵值：會被記錄，但不算補齊。"""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN = _Unknown()
_DEFAULT_UNKNOWN_VALUES = ("還不知道",)
_MIN = "minimum_fields"


@dataclass(frozen=True)
class Question:
    field: str
    text: str | None
    minimum: bool
    group: str | None = None
    extra: Mapping[str, Any] = dc_field(default_factory=dict, compare=False)

    def as_dict(self) -> dict:
        return {"field": self.field, "text": self.text, "minimum": self.minimum, "group": self.group}


@dataclass(frozen=True)
class Evaluation:
    state: str
    missing: tuple[str, ...]          # 還沒補齊的欄位（依題目順序；最低欄位在前）
    missing_minimum: tuple[str, ...]  # 還沒補齊的最低欄位
    unknown: tuple[str, ...]          # 回答「還不知道」的欄位
    next_question: Question | None

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "missing": list(self.missing),
            "missing_minimum": list(self.missing_minimum),
            "unknown": list(self.unknown),
            "next_question": self.next_question.as_dict() if self.next_question else None,
        }


def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Rules:
    """一份規則 YAML 解析後的結果（不可變）。"""

    def __init__(self, spec: Mapping[str, Any], *, start: str | None = None, target: str | None = None):
        if not isinstance(spec, Mapping):
            raise ValueError("rules spec must be a mapping")
        st = spec.get("status_transition") or {}
        rules = spec.get("status_rules") or {}

        mf = st.get("minimum_fields") or []
        if isinstance(mf, Mapping):
            mf = list(mf.values())
        elif isinstance(mf, str):
            mf = [mf]
        self.minimum_fields: tuple[str, ...] = tuple(_dedupe(str(f) for f in mf))
        if not self.minimum_fields:   # 沒列最低欄位 → 每一題都是必要欄位
            self.minimum_fields = tuple(q.field for q in self._parse_questions(spec.get("clarify_questions")))

        self.questions: tuple[Question, ...] = tuple(self._parse_questions(spec.get("clarify_questions")))
        q_fields = [q.field for q in self.questions]
        self.fields: tuple[str, ...] = tuple(_dedupe(list(self.minimum_fields) + q_fields))

        states = list(rules.keys()) if isinstance(rules, Mapping) else []
        if not states and isinstance(st.get("states"), Mapping):
            states = list(st["states"].keys())
        self.start: str | None = start or st.get("from") or st.get("start") or (states[0] if states else None)
        self.target: str | None = target or st.get("to") or st.get("target") or (states[1] if len(states) > 1 else None)
        if not self.start or not self.target:
            raise ValueError("status_transition needs from/to (or at least two states)")

        self.rules: tuple[tuple[str, Any], ...] = tuple(
            (name, body["when"]) for name, body in (rules.items() if isinstance(rules, Mapping) else [])
            if isinstance(body, Mapping) and "when" in body
        )
        self.unknown_counts_as_filled = bool(st.get("unknown_counts_as_filled", False))
        self.unknown_values: tuple[str, ...] = tuple(st.get("unknown_values") or _DEFAULT_UNKNOWN_VALUES)

    # ── parsing ───────────────────────────────────────────────────────────
    def _parse_questions(self, cq: Any) -> list[Question]:
        raw: list[tuple[str, str | None, str | None, dict]] = []
        if isinstance(cq, list):
            for item in cq:
                if isinstance(item, Mapping) and "field" in item:
                    text = item.get("ask", item.get("text"))
                    raw.append((str(item["field"]), text, item.get("group"), dict(item)))
        elif isinstance(cq, Mapping):
            for group, body in cq.items():
                if isinstance(body, Mapping):
                    for f, text in body.items():
                        if isinstance(text, str):
                            raw.append((str(f), text, str(group), {}))
        mins = set(self.minimum_fields)
        seen, qs = set(), []
        for f, text, group, extra in raw:
            if f in seen:
                continue
            seen.add(f)
            qs.append(Question(f, text, f in mins, group, extra))
        # 最低欄位若沒有題目，仍要能被問到
        for f in self.minimum_fields:
            if f not in seen:
                qs.append(Question(f, None, True))
        # 先問最低欄位（照 YAML 題目順序），再問其他
        return [q for q in qs if q.minimum] + [q for q in qs if not q.minimum]

    # ── evaluation ───────────────────────────────────────────────────────
    def is_unknown(self, value: Any) -> bool:
        return value is UNKNOWN or (isinstance(value, str) and value.strip() in self.unknown_values)

    def is_filled(self, facts: Mapping[str, Any], f: str) -> bool:
        if f not in facts:
            return False
        v = facts[f]
        if self.is_unknown(v):
            return self.unknown_counts_as_filled
        if v is None:
            return False
        if isinstance(v, str) and not v.strip():
            return False
        return True

    def _fields(self, spec: Any) -> list[str]:
        if spec == _MIN:
            return list(self.minimum_fields)
        if isinstance(spec, str):
            return [spec]
        return [str(x) for x in spec or []]

    def _cond(self, when: Any, facts: Mapping[str, Any]) -> bool:
        if isinstance(when, list):
            return any(self._cond(w, facts) for w in when)
        if not isinstance(when, Mapping) or not when:
            return False
        for op, arg in when.items():
            if op == "always":
                ok = bool(arg)
            elif op == "all_filled":
                ok = all(self.is_filled(facts, f) for f in self._fields(arg))
            elif op == "any_filled":
                ok = any(self.is_filled(facts, f) for f in self._fields(arg))
            elif op == "all_missing":
                ok = not any(self.is_filled(facts, f) for f in self._fields(arg))
            elif op == "any_missing":
                ok = not all(self.is_filled(facts, f) for f in self._fields(arg))
            elif op == "fact_in":
                ok = all(self.is_filled(facts, f) and facts[f] in list(vals) for f, vals in arg.items())
            elif op in ("fact_gte", "fact_lt"):
                ok = True
                for f, n in arg.items():
                    v = facts.get(f)
                    if not self.is_filled(facts, f) or not isinstance(v, (int, float)) or isinstance(v, bool):
                        ok = False
                        break
                    ok = ok and (v >= n if op == "fact_gte" else v < n)
            else:
                raise ValueError(f"unknown condition: {op}")
            if not ok:
                return False
        return True

    def state(self, facts: Mapping[str, Any]) -> str:
        for name, when in self.rules:
            if self._cond(when, facts):
                return name
        return self.target if all(self.is_filled(facts, f) for f in self.minimum_fields) else self.start

    def missing(self, facts: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(f for f in self.fields if not self.is_filled(facts, f))

    def next_question(self, facts: Mapping[str, Any], asked: Iterable[str] = ()) -> Question | None:
        done = set(asked)
        for q in self.questions:
            if q.field in done or q.field in facts:   # 問過、跳過、已回答（含還不知道）都不再問
                continue
            return q
        return None

    def evaluate(self, facts: Mapping[str, Any] | None = None, asked: Iterable[str] = ()) -> Evaluation:
        facts = dict(facts or {})
        missing = self.missing(facts)
        return Evaluation(
            state=self.state(facts),
            missing=missing,
            missing_minimum=tuple(f for f in self.minimum_fields if f in missing),
            unknown=tuple(f for f in self.fields if f in facts and self.is_unknown(facts[f])),
            next_question=self.next_question(facts, asked),
        )


def load_rules(source: str | Path | Mapping[str, Any], **kw: Any) -> Rules:
    """從 YAML 路徑、YAML 文字或已解析的 dict 建立 Rules。kw：start／target 覆寫起點與目標狀態。"""
    if isinstance(source, Mapping):
        return Rules(source, **kw)
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        return Rules(yaml.safe_load(Path(source).read_text(encoding="utf-8")), **kw)
    return Rules(yaml.safe_load(source), **kw)


class Session:
    """一輪對話的狀態：記錄回答／還不知道／跳過，每次記錄後只用規則重算。"""

    def __init__(self, rules: Rules, facts: Mapping[str, Any] | None = None, asked: Iterable[str] = ()):
        self.rules = rules
        self.facts: dict[str, Any] = dict(facts or {})
        self.asked: list[str] = _dedupe(asked)
        self.history: list[tuple[str, str, Any]] = []
        self.last: Evaluation = rules.evaluate(self.facts, self.asked)

    def _mark(self, f: str) -> None:
        if f not in self.asked:
            self.asked.append(f)

    def answer(self, f: str, value: Any) -> Evaluation:
        if self.rules.is_unknown(value):
            return self.unknown(f)
        self.facts[f] = value
        self._mark(f)
        self.history.append(("answer", f, value))
        return self.recompute()

    def unknown(self, f: str) -> Evaluation:
        self.facts[f] = UNKNOWN
        self._mark(f)
        self.history.append(("unknown", f, UNKNOWN))
        return self.recompute()

    def skip(self, f: str) -> Evaluation:
        self._mark(f)
        self.history.append(("skip", f, None))
        return self.recompute()

    def recompute(self) -> Evaluation:
        self.last = self.rules.evaluate(self.facts, self.asked)
        return self.last

    @property
    def state(self) -> str:
        return self.last.state

    @property
    def missing(self) -> tuple[str, ...]:
        return self.last.missing

    def next_question(self) -> Question | None:
        return self.last.next_question
