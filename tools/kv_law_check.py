"""Validate public/tangle/kv-law-mock.js against the fixed project snapshot. No third-party deps.

  python3 tools/kv_law_check.py            -> exit 0 and "OK 10 projects" when every rule holds
  python3 tools/kv_law_check.py --self-test -> exit 0 when a corrupted copy is correctly rejected
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ["農村再生", "區域計畫", "國土計畫", "都市計畫", "非都市土地使用管制",
           "開發審議", "環境影響評估", "水土保持", "農業發展", "農地農用認定"]


def load():
    s = (ROOT / "public/tangle/kv-law-mock.js").read_text(encoding="utf-8")
    kv = json.loads(s[s.index("{"):s.rindex("}") + 1])
    texts = {p["id"]: p["philosophy"] for p in json.loads((ROOT / "app/lab/tangle_data.json").read_text(encoding="utf-8"))["projects"]}
    return kv, texts


def problems(kv, texts):
    out = []
    if kv.get("demo") is not True:
        out.append("top-level demo flag missing")
    if sorted(kv.get("projects", {})) != sorted(texts):
        out.append("project ids differ from snapshot")
    for pid, p in kv.get("projects", {}).items():
        if sorted(p["law"]) != sorted(DOMAINS):
            out.append(f"{pid}: law keys are not exactly the 10 domains")
            continue
        states = [v["state"] for v in p["law"].values()]
        for need in ("hit", "gap", "na"):
            if need not in states:
                out.append(f"{pid}: no '{need}' entry")
        for key, v in p["law"].items():
            if v["state"] not in ("hit", "gap", "na"):
                out.append(f"{pid} {key}: bad state {v['state']}")
            if v["state"] == "hit" and (v.get("confidence") not in ("high", "mid", "low") or not v.get("evidence")
                                        or not isinstance(v.get("count", {}).get("risk"), int) or not isinstance(v["count"].get("note"), int)
                                        or v["count"]["risk"] + v["count"]["note"] < 1):
                out.append(f"{pid} {key}: hit needs confidence, evidence and a positive count")
            if v["state"] == "gap" and not (v.get("question") and 0 < len(v.get("missing", "")) <= 8):
                out.append(f"{pid} {key}: gap needs a question and a short 'missing' label (≤8 chars)")
            if v["state"] == "na" and v.get("evidence"):
                out.append(f"{pid} {key}: na must not carry evidence")
            for e in v.get("evidence", []):
                if e not in texts.get(pid, ""):
                    out.append(f"{pid} {key}: evidence not in the plan text: {e[:20]}…")
        if len(p.get("uncovered", [])) > 2 or set(p.get("uncovered", [])) & set(DOMAINS):
            out.append(f"{pid}: uncovered must be 0–2 names outside the 10 domains")
    return out


if __name__ == "__main__":
    kv, texts = load()
    if "--self-test" in sys.argv:
        bad = copy.deepcopy(kv)
        pid, key = next((pid, k) for pid, p in bad["projects"].items() for k, v in p["law"].items() if v.get("evidence"))
        bad["projects"][pid]["law"][key]["evidence"][0] = "這句話不在計畫書裡"
        caught = any("evidence not in the plan text" in m for m in problems(bad, texts))
        print("self-test:", "corrupted evidence rejected" if caught else "NOT rejected")
        sys.exit(0 if caught and not problems(kv, texts) else 1)
    errs = problems(kv, texts)
    for m in errs:
        print("FAIL", m)
    if errs:
        sys.exit(1)
    print(f"OK {len(kv['projects'])} projects")
