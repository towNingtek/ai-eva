"""Validate public/tangle/kv-match-mock.js against the fixed project snapshot. No third-party deps.

  python3 tools/kv_match_check.py            -> exit 0 and "OK 10 projects" when every rule holds
  python3 tools/kv_match_check.py --self-test -> exit 0 when corrupted copies are rejected
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]


def load():
    s = (ROOT / "public/tangle/kv-match-mock.js").read_text(encoding="utf-8")
    kv = json.loads(s[s.index("{"):s.rindex("}") + 1])
    texts = {p["id"]: p["philosophy"] for p in json.loads((ROOT / "app/lab/tangle_data.json").read_text(encoding="utf-8"))["projects"]}
    return kv, texts


TOPIC_TO_B = {"facility": "B1", "house": "B1", "industry": "B2", "experience": "B3", "care": "B3",
              "culture": "B4", "youth": "B6", "participation": "B6"}


def kinds_in_snapshot():
    """For each plan and B key: which kinds of quote (concrete / direction-only) the snapshot has."""
    out = {}
    for p in json.loads((ROOT / "app/lab/tangle_data.json").read_text(encoding="utf-8"))["projects"]:
        for it in p["issues"]:
            k = TOPIC_TO_B.get(it["theme"])
            if k:
                out.setdefault((p["id"], k), set()).add("offer" if it["concrete"] else "need")
    return out


def problems(kv, texts):
    out = []
    if kv.get("demo") is not True:
        out.append("top-level demo flag missing")
    if sorted(kv.get("keys", {})) != KEYS:
        out.append("keys must be exactly B1–B8")
    if sorted(kv.get("projects", {})) != sorted(texts):
        out.append("project ids differ from snapshot")
    for pid, p in kv.get("projects", {}).items():
        if sorted(p.get("match", {})) != KEYS:
            out.append(f"{pid}: match keys are not exactly B1–B8")
            continue
        roles = [v["role"] for v in p["match"].values()]
        if "need" not in roles and "offer" not in roles:
            out.append(f"{pid}: no need or offer at all")
        for k, v in p["match"].items():
            if v["role"] not in ("need", "offer", "both", "none"):
                out.append(f"{pid} {k}: bad role {v['role']}")
            if v["role"] == "none" and v.get("evidence"):
                out.append(f"{pid} {k}: none must not carry evidence")
            if v["role"] != "none" and not v.get("evidence"):
                out.append(f"{pid} {k}: need/offer must cite evidence")
            K = KINDS.get((pid, k), set())
            if k != "B7" and v["role"] in ("need", "offer", "both"):
                want = "both" if K == {"need", "offer"} else (next(iter(K)) if len(K) == 1 else None)
                if want and v["role"] != want:
                    out.append(f"{pid} {k}: role {v['role']} but quotes say {want} (standard v1.1 Q1)")
            for e in v.get("evidence", []):
                if e not in texts.get(pid, ""):
                    out.append(f"{pid} {k}: evidence not in the plan text: {e[:20]}…")
    return out


KINDS = {}

if __name__ == "__main__":
    kv, texts = load()
    KINDS.update(kinds_in_snapshot())
    if "--self-test" in sys.argv:
        bad = copy.deepcopy(kv)
        pid, k = next((pid, k) for pid, p in bad["projects"].items() for k, v in p["match"].items() if v.get("evidence"))
        bad["projects"][pid]["match"][k]["evidence"][0] = "這句話不在計畫書裡"
        c1 = any("evidence not in the plan text" in m for m in problems(bad, texts))
        bad2 = copy.deepcopy(kv)
        pid, k = next((pid, k) for pid, p in bad2["projects"].items() for k, v in p["match"].items() if v["role"] == "none")
        bad2["projects"][pid]["match"][k]["evidence"] = [next(iter(texts.values()))[:10]]
        c2 = any("none must not carry evidence" in m for m in problems(bad2, texts))
        bad3 = copy.deepcopy(kv)
        pid, k = next(((pid, k) for pid, p in bad3["projects"].items() for k, v in p["match"].items() if v["role"] == "both"), (None, None))
        c3 = True
        if pid:
            bad3["projects"][pid]["match"][k]["role"] = "offer"
            c3 = any("standard v1.1 Q1" in m for m in problems(bad3, texts))
        print("self-test: both collapsed to offer", "rejected" if c3 else "NOT rejected")
        c2 = c2 and c3
        print("self-test:", "tampered quote rejected" if c1 else "quote NOT rejected", "|", "evidence on none rejected" if c2 else "none NOT rejected")
        sys.exit(0 if c1 and c2 and not problems(kv, texts) else 1)
    errs = problems(kv, texts)
    for m in errs:
        print("FAIL", m)
    if errs:
        sys.exit(1)
    print(f"OK {len(kv['projects'])} projects")
