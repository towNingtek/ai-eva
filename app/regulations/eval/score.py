#!/usr/bin/env python3
"""Recall / Precision for the regulation check against a golden sample (tplanet-multi-tenant#113).

Unit of scoring (spec §5.1(十三), Asst. PM 2026-11-03):
  - judged at the **law level**, inside the covered domains only (out-of-scope = 未評估, not scored);
  - 鄰條 / 同風險不同條 count as correct  -> a law counts as hit if ANY of its articles is 觸發;
  - 系統正確而 golden 漏標 -> golden is corrected, no penalty  -> handled by `adjudications` (accept_system);
  - 系統錯誤 -> counts against the system.

golden.json:
  {"cases": {"<uuid>": {"name": "...", "expected": ["<law>", ...], "not_expected": ["<law>", ...]}},
   "adjudications": [{"case": "<uuid>", "law": "<law>", "decision": "accept_system" | "reject_system", "by": "...", "note": "..."}]}
run dir: one <uuid>.json per case = the judge output ({"findings": [...], ...}).

Recall    = TP / (TP + FN)   over all cases combined
Precision = TP / (TP + FP)   over all cases combined
Usage: score_regcheck.py golden.json run_dir [--self-test]
"""
import json
import sys
from pathlib import Path

COVERED = {"農村再生", "區域計畫", "國土計畫", "都市計畫", "非都市土地使用管制",
           "開發審議", "環境影響評估", "水土保持", "農業發展", "農地農用認定"}
TARGET = {"recall": 0.85, "precision": 0.65}


def system_laws(run):
    """Laws the system flags (any article 觸發), covered domains only."""
    return {f["regulation"] for f in run["findings"]
            if f.get("verdict") == "觸發" and (f.get("law_domain") in COVERED)}


def score(golden, runs):
    adj = {(a["case"], a["law"]): a["decision"] for a in golden.get("adjudications", [])}
    tp = fp = fn = 0
    per = {}
    for uuid, g in golden["cases"].items():
        if uuid not in runs:
            raise SystemExit(f"FAIL no system output for case {uuid}")
        sys_l = system_laws(runs[uuid])
        exp = set(g["expected"])
        # golden corrected where the system was right and the golden missed it
        exp |= {law for law in sys_l if adj.get((uuid, law)) == "accept_system"}
        # explicitly rejected system hits stay false positives even if listed as expected by mistake
        c_tp = len(sys_l & exp)
        c_fp = len(sys_l - exp)
        c_fn = len(exp - sys_l)
        tp, fp, fn = tp + c_tp, fp + c_fp, fn + c_fn
        per[uuid] = {"name": g.get("name", ""), "tp": c_tp, "fp": c_fp, "fn": c_fn,
                     "missed": sorted(exp - sys_l), "extra": sorted(sys_l - exp)}
    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    return {"recall": recall, "precision": precision, "tp": tp, "fp": fp, "fn": fn, "cases": per,
            "pass": recall >= TARGET["recall"] and precision >= TARGET["precision"]}


def self_test():
    f = lambda law, v="觸發", d="農村再生": {"regulation": law, "verdict": v, "law_domain": d}
    runs = {"A": {"findings": [f("甲法"), f("甲法"), f("乙法"), f("丙法", "不觸及"), f("外法", d="觀光民宿")]},
            "B": {"findings": [f("甲法"), f("丁法")]}}
    golden = {"cases": {"A": {"expected": ["甲法", "丙法"]}, "B": {"expected": ["甲法"]}}}
    s = score(golden, runs)
    # A: sys {甲,乙} (外法 out of scope), exp {甲,丙} -> tp1 fp1 fn1 ; B: sys {甲,丁}, exp {甲} -> tp1 fp1 fn0
    assert (s["tp"], s["fp"], s["fn"]) == (2, 2, 1), s
    assert abs(s["recall"] - 2 / 3) < 1e-9 and abs(s["precision"] - 0.5) < 1e-9, s
    # adjudication: the system's 丁法 in B was right, golden missed it -> no penalty
    golden["adjudications"] = [{"case": "B", "law": "丁法", "decision": "accept_system"}]
    s2 = score(golden, runs)
    assert (s2["tp"], s2["fp"], s2["fn"]) == (3, 1, 1), s2
    # several articles of one law count once (鄰條 / 同風險不同條 = correct, not double-counted)
    assert s["cases"]["A"]["tp"] == 1
    # out-of-scope domain never scored
    assert "外法" not in s["cases"]["A"]["extra"]
    print("self-test: law-level, out-of-scope ignored, 鄰條 counted once, adjudication accept_system — all OK")


def main():
    if "--self-test" in sys.argv:
        return self_test()
    golden = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    run_dir = Path(sys.argv[2])
    runs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in run_dir.glob("*.json") if p.stem in golden["cases"]}
    s = score(golden, runs)
    for uuid, c in s["cases"].items():
        print(f"{uuid} {c['name'][:14]:14} tp {c['tp']:2} fp {c['fp']:2} fn {c['fn']:2}"
              + (f"  missed {c['missed']}" if c["missed"] else "") + (f"  extra {c['extra']}" if c["extra"] else ""))
    print(f"Recall {s['recall']:.1%} (≥85%)  Precision {s['precision']:.1%} (≥65%)  TP {s['tp']} FP {s['fp']} FN {s['fn']}  ->  {'PASS' if s['pass'] else 'NOT YET'}")
    sys.exit(0 if s["pass"] else 1)


if __name__ == "__main__":
    main()
