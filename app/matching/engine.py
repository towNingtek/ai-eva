"""媒合引擎（第一期兩維）：A × 2–4 個指定對象 → 硬條件過濾 → 排序（ai-eva #200，MVP 步驟 7）。

- 只算兩維（yillkid 2026-11-23：先做兩維）：
  ① need_offer  Need／Offer 互補：A 需要的對方能不能提供、對方需要的 A 能不能提供（雙向／單向／無）
  ② b1_b8       B1–B8 能力互補：每一類的關係（互補候選／共同尋找第三方／可聯合或交流），互補候選條數
  議題、可執行性、跨國成本、階段時程四維一律輸出「未評估」。
- 各維度分開輸出，**不合成單一總分**；排序依 ranking_profile.yaml 的規則逐條比較
  （雙向互補優先 → 互補候選數），全部相同依指定順序，同一 profile 重跑順序必相同。
- 硬條件（非公開、不同站…）不符就排除並記原因。
- 規則可揭露：每個名次附每條規則的名稱、原文與數值，以及「依哪條規則」排在這裡（decided_by）；
  兩維結果附 philosophy 原文依據（capability.analyze 的 evidence）。
- `write_record` 把結果、判斷與排除原因寫入媒合紀錄（#198），排序設定快照可用
  `records.replay_ranking` 重播出同一順序。

關係判斷沿用 pair.py（#183），規則與權重只在 ranking_profile.yaml，程式不寫死。

對象（含 A）格式：
    {"id": "p1", "site": "yunlin", "public": True, "name": "…",
     "capabilities": capability.analyze() 的輸出，或 {"B1": "NEED", ...}}
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from app.matching import pair
from app.matching import records as rec

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "ranking_profile.yaml"

B_KEYS = pair.B_KEYS
DIM_NEED_OFFER, DIM_B1_B8 = "need_offer", "b1_b8"
DIMENSIONS = (DIM_NEED_OFFER, DIM_B1_B8)

# need_offer 的三個結論（數值越大越前面）
BIDIRECTIONAL, ONE_WAY, NO_COMPLEMENT = "雙向互補", "單向互補", "無互補"
LEVEL = {BIDIRECTIONAL: 2, ONE_WAY: 1, NO_COMPLEMENT: 0}

# 排序規則 metric → 計算方式與它對應的維度（供媒合紀錄重播）
METRIC_DIMENSION = {"bidirectional": DIM_NEED_OFFER, "complement_count": DIM_B1_B8}
MAX_COMPLEMENTS = 2 * len(B_KEYS)


class MatchInputError(ValueError):
    """輸入不合法（對象數、重複、含 A 本身、設定缺漏）。"""


# ── 設定 ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_profile(path: Path | str = PROFILE) -> dict:
    """讀排序設定；必須有 profile_id、effective_at、ranking_rules。"""
    prof = _load(str(path))
    for k in ("profile_id", "effective_at", "ranking_rules"):
        if not prof.get(k):
            raise MatchInputError(f"ranking profile 缺 {k}：{path}")
    for r in prof["ranking_rules"]:
        if r.get("metric") not in METRIC_DIMENSION:
            raise MatchInputError(f"未知排序 metric：{r.get('metric')}")
    return prof


def _profile(profile: Mapping | Path | str | None) -> Mapping:
    if profile is None:
        return load_profile()
    if isinstance(profile, (str, Path)):
        return load_profile(profile)
    return profile


# ── 硬條件 ───────────────────────────────────────────────────────────

def _check(rule: str, value: Any, a_value: Any) -> bool:
    if rule == "is_true":
        return value is True
    if rule == "equals_a":
        return value is not None and str(value) == str(a_value)
    if rule == "not_equals_a":
        return str(value) != str(a_value)
    raise MatchInputError(f"未知硬條件規則：{rule}")


def hard_filter(a: Mapping, target: Mapping, profile: Mapping) -> list[dict]:
    """回傳不符的硬條件（空清單＝通過），每筆附規則名稱、原因與原文。"""
    out = []
    for f in profile.get("hard_filters") or []:
        field = f["field"]
        if not _check(f["rule"], target.get(field), a.get(field)):
            out.append({"rule": f["id"], "name": f.get("name", f["id"]), "reason": f.get("reason", f["id"]),
                        "原文": f.get("原文", ""), "field": field, "value": target.get(field)})
    return out


# ── 兩維 ─────────────────────────────────────────────────────────────

def _quotes(project: Mapping, key: str) -> list[str]:
    caps = project.get("capabilities") or {}
    caps = caps.get("capabilities", caps) if isinstance(caps, Mapping) else {}
    info = caps.get(key) if isinstance(caps, Mapping) else None
    if not isinstance(info, Mapping):
        return []
    return [e["quote"] for e in info.get("evidence") or [] if isinstance(e, Mapping) and e.get("quote")]


def _names(std: Mapping) -> dict[str, str]:
    reg = std.get("capability_registry") or {}
    return {k: (reg.get(k) or {}).get("名稱", k) for k in B_KEYS}


def evaluate(a: Mapping, target: Mapping, std: Mapping | None = None) -> dict:
    """A × 一個對象的兩維結果（各自獨立，沒有總分）。"""
    std = std if std is not None else pair.load_standard()
    bname = _names(std)
    a_id, t_id = str(a["id"]), str(target["id"])
    a_caps, t_caps = a.get("capabilities") or {}, target.get("capabilities") or {}
    comp = pair.complement_pairs(a_id, a_caps, t_id, t_caps)

    def ev(need_pid, offer_pid, k):
        need_p, offer_p = (a, target) if need_pid == a_id else (target, a)
        return {"key": k, "name": bname[k], "need": need_pid, "offer": offer_pid,
                "need_evidence": _quotes(need_p, k), "offer_evidence": _quotes(offer_p, k)}

    a_gets = [ev(n, o, k) for n, o, k in comp if n == a_id]
    t_gets = [ev(n, o, k) for n, o, k in comp if n == t_id]
    if a_gets and t_gets:
        verdict = BIDIRECTIONAL
    elif a_gets or t_gets:
        verdict = ONE_WAY
    else:
        verdict = NO_COMPLEMENT
    need_offer = {
        "verdict": verdict,
        "a_needs_target_offers": a_gets,
        "target_needs_a_offers": t_gets,
        "rationale": f"A 需要、{t_id} 能提供 {len(a_gets)} 類；{t_id} 需要、A 能提供 {len(t_gets)} 類",
    }

    third, peer = set(pair.third_party_keys(a_caps, t_caps)), set(pair.peer_keys(a_caps, t_caps))
    comp_keys = {k for _, _, k in comp}
    A, T = pair.directions(a_caps), pair.directions(t_caps)
    per_key = {}
    for k in B_KEYS:
        if k in comp_keys:
            rel = pair.REL_COMPLEMENT
        elif k in third:
            rel = pair.REL_THIRD_PARTY
        elif k in peer:
            rel = pair.REL_PEER
        else:
            rel = None
        per_key[k] = {"name": bname[k], "a": A[k], "target": T[k], "relation": rel,
                      "a_evidence": _quotes(a, k), "target_evidence": _quotes(target, k)}
    b1_b8 = {
        "verdict": b1_b8_verdict(len(comp)),
        "complement_count": len(comp),
        "complements": [{"need": n, "offer": o, "key": k, "name": bname[k]} for n, o, k in comp],
        "third_party": sorted(third, key=B_KEYS.index),
        "peer": sorted(peer, key=B_KEYS.index),
        "categories": per_key,
    }
    return {DIM_NEED_OFFER: need_offer, DIM_B1_B8: b1_b8}


def b1_b8_verdict(n: int) -> str:
    return f"互補候選 {n} 條"


def metrics(dims: Mapping) -> dict[str, int]:
    """排序用的數值（各規則一個，不加總）。"""
    return {
        "bidirectional": LEVEL[dims[DIM_NEED_OFFER]["verdict"]],
        "complement_count": dims[DIM_B1_B8]["complement_count"],
    }


# ── 排序 ─────────────────────────────────────────────────────────────

def _rule_info(r: Mapping) -> dict:
    return {"rule": r.get("id", r.get("metric")), "name": r.get("name", ""), "原文": r.get("原文", "")}


def rank_entries(entries: Sequence[dict], profile: Mapping) -> list[dict]:
    """entries：[{target, index, metrics}] → 名次清單，每個名次附規則名稱、原文、數值與 decided_by。"""
    rules = list(profile["ranking_rules"])
    tie = profile.get("tie_break") or {"id": "input_order", "name": "同分依指定順序", "原文": ""}

    def val(e, r):
        v = e["metrics"][r["metric"]]
        return -v if r.get("order", "desc") == "desc" else v

    def key(e):
        return tuple(val(e, r) for r in rules) + (e["index"],)

    ordered = sorted(entries, key=key)
    out = []
    for i, e in enumerate(ordered):
        other = ordered[i - 1] if i > 0 else (ordered[1] if len(ordered) > 1 else None)
        decided = None
        if other is not None:
            for r in rules:
                if val(e, r) != val(other, r):
                    decided = _rule_info(r)
                    break
            else:
                decided = _rule_info(tie)
            decided["compared_with"] = other["target"]
        out.append({
            "rank": i + 1,
            "target": e["target"],
            "rules": [{**_rule_info(r), "value": e["metrics"][r["metric"]], "order": r.get("order", "desc")}
                      for r in rules] + [{**_rule_info(tie), "value": e["index"], "order": "asc"}],
            "decided_by": decided,
        })
    return out


# ── 主流程 ───────────────────────────────────────────────────────────

def _validate(a: Mapping, targets: Sequence[Mapping], profile: Mapping) -> None:
    lim = profile.get("targets") or {}
    lo, hi = int(lim.get("min", rec.MIN_TARGETS)), int(lim.get("max", rec.MAX_TARGETS))
    if not (lo <= len(targets) <= hi):
        raise MatchInputError(f"對象需 {lo}–{hi} 個，收到 {len(targets)} 個")
    if not a.get("id") or any(not t.get("id") for t in targets):
        raise MatchInputError("A 與每個對象都要有 id")
    ids = [str(t["id"]) for t in targets]
    if len(set(ids)) != len(ids):
        raise MatchInputError("對象不得重複")
    if str(a["id"]) in ids:
        raise MatchInputError("對象不得包含 A 本身")


def match(a: Mapping, targets: Sequence[Mapping], *, profile: Mapping | Path | str | None = None,
          std: Mapping | None = None) -> dict:
    """A × 2–4 個指定對象 → 硬條件過濾 → 兩維各自評估 → 依規則排序。"""
    prof = _profile(profile)
    std = std if std is not None else pair.load_standard()
    _validate(a, targets, prof)
    ne = prof.get("not_evaluated") or {}
    label = ne.get("label", "未評估")
    not_evaluated = {k: {"name": name, "status": label, "原文": ne.get("原文", "")}
                     for k, name in (ne.get("dimensions") or {}).items()}

    results, excluded, entries = [], [], []
    for i, t in enumerate(targets):
        tid = str(t["id"])
        fails = hard_filter(a, t, prof)
        if fails:
            excluded.append({"target": tid, "reasons": [f["reason"] for f in fails], "rules": fails})
            continue
        dims = evaluate(a, t, std)
        m = metrics(dims)
        results.append({"target": tid, "name": t.get("name", tid), "dimensions": dims,
                        "not_evaluated": not_evaluated})
        entries.append({"target": tid, "index": i, "metrics": m})

    ranking = rank_entries(entries, prof)
    return {
        "profile_id": prof["profile_id"],
        "effective_at": str(prof["effective_at"]),
        "standard_version": str((std.get("standard") or {}).get("version", "")),
        "a": str(a["id"]),
        "targets": [str(t["id"]) for t in targets],
        "dimensions": {k: {"name": (prof.get("dimensions") or {}).get(k, {}).get("name", k),
                           "原文": (prof.get("dimensions") or {}).get(k, {}).get("原文", "")}
                       for k in DIMENSIONS},
        "not_evaluated": not_evaluated,
        "results": results,
        "excluded": excluded,
        "ranking": ranking,
        "order": [r["target"] for r in ranking],
        "ranking_config": ranking_config(prof),
    }


def ranking_config(profile: Mapping) -> dict:
    """給媒合紀錄（#198 runs.ranking_config）的快照：records.rank 可用它重播出同一順序。"""
    dims, vrank = [], {}
    for r in profile["ranking_rules"]:
        d = METRIC_DIMENSION[r["metric"]]
        dims.append(d)
        desc = r.get("order", "desc") == "desc"
        if r["metric"] == "bidirectional":
            for v, lvl in LEVEL.items():
                vrank[v] = (max(LEVEL.values()) - lvl) if desc else lvl
        else:
            for n in range(MAX_COMPLEMENTS + 1):
                vrank[b1_b8_verdict(n)] = (MAX_COMPLEMENTS - n) if desc else n
    return {
        "version": str(profile["profile_id"]),
        "profile_id": str(profile["profile_id"]),
        "effective_at": str(profile["effective_at"]),
        "dimensions": dims,
        "verdict_rank": vrank,
        "rules": [_rule_info(r) for r in profile["ranking_rules"]],
        "tie_break": _rule_info(profile.get("tie_break") or {"id": "input_order"}),
    }


# ── 寫入媒合紀錄（#198） ─────────────────────────────────────────────

async def write_record(conn, result: Mapping, *, tenant: str, initiator: str, model: str = "",
                       actor: str | None = None) -> int:
    """把 match() 的結果寫進 matching schema：run、每案兩維判斷、排除原因、排序結果。回傳 run id。"""
    cfg = dict(result["ranking_config"])
    run_id = await rec.start_run(
        conn, tenant=tenant, initiator=initiator, project_a=result["a"], targets=result["targets"],
        standard_version=result["standard_version"] or "unknown",
        ranking_config_version=cfg["version"], ranking_config=cfg, model=model,
        meta={"profile_id": result["profile_id"], "effective_at": result["effective_at"],
              "not_evaluated": result["not_evaluated"]},
    )
    for ex in result["excluded"]:
        await rec.add_event(conn, run_id, "exclude", target=ex["target"], actor=actor,
                            payload={"reasons": ex["reasons"], "rules": ex["rules"]})
    for r in result["results"]:
        for dim in DIMENSIONS:
            d = r["dimensions"][dim]
            evidence = (
                {"a_needs_target_offers": d["a_needs_target_offers"],
                 "target_needs_a_offers": d["target_needs_a_offers"]}
                if dim == DIM_NEED_OFFER else
                {"complements": d["complements"], "categories": d["categories"]}
            )
            await rec.add_judgement(conn, run_id, target=r["target"], dimension=dim, verdict=d["verdict"],
                                    rationale=d.get("rationale", d["verdict"]), evidence=evidence)
    await rec.add_event(conn, run_id, "ranked", actor=actor,
                        payload={"order": result["order"], "ranking": result["ranking"],
                                 "profile_id": result["profile_id"]})
    return run_id
