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


CORPUS = ROOT / "app/lab/negative_list.json"   # copy of app/regulations/corpus/negative_list.json (production corpus)
RISK_TAGS = ("實質管制", "罰則")


def load():
    s = (ROOT / "public/tangle/kv-law-mock.js").read_text(encoding="utf-8")
    kv = json.loads(s[s.index("{"):s.rindex("}") + 1])
    texts = {p["id"]: p["philosophy"] for p in json.loads((ROOT / "app/lab/tangle_data.json").read_text(encoding="utf-8"))["projects"]}
    return kv, texts


def corpus_index():
    src = CORPUS if CORPUS.exists() else ROOT / "app/regulations/corpus/negative_list.json"
    idx = {}
    for law, items in json.loads(src.read_text(encoding="utf-8")).items():
        for it in items:
            idx.setdefault((law, it["article_no"]), set()).add((it["law_domain"], it["tag"]))
    return idx


def problems(kv, texts, idx=None):
    idx = idx if idx is not None else corpus_index()
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
            if v["state"] == "hit":
                cl = v.get("clauses", [])
                if len(cl) != v["count"]["risk"] + v["count"]["note"]:
                    out.append(f"{pid} {key}: clauses {len(cl)} != risk+note {v['count']['risk'] + v['count']['note']}")
                if sum(1 for c in cl if c.get("tag") in RISK_TAGS) != v["count"]["risk"]:
                    out.append(f"{pid} {key}: risk clauses do not match count.risk")
                for c in cl:
                    real = idx.get((c.get("law"), c.get("no")))
                    if not real:
                        out.append(f"{pid} {key}: clause not in corpus: {c.get('law')} {c.get('no')}")
                    elif (key, c.get("tag")) not in real:
                        out.append(f"{pid} {key}: clause {c['law']} {c['no']} is not a {key}/{c.get('tag')} clause in the corpus")
            elif v.get("clauses"):
                out.append(f"{pid} {key}: only 對上了 may carry clauses")
            for e in v.get("evidence", []):
                if e not in texts.get(pid, ""):
                    out.append(f"{pid} {key}: evidence not in the plan text: {e[:20]}…")
        if len(p.get("uncovered", [])) > 2 or set(p.get("uncovered", [])) & set(DOMAINS):
            out.append(f"{pid}: uncovered must be 0–2 names outside the 10 domains")
    return out


if __name__ == "__main__":
    kv, texts = load()
    if "--self-test" in sys.argv:
        idx = corpus_index()
        bad = copy.deepcopy(kv)
        pid, key = next((pid, k) for pid, p in bad["projects"].items() for k, v in p["law"].items() if v.get("evidence"))
        bad["projects"][pid]["law"][key]["evidence"][0] = "這句話不在計畫書裡"
        c1 = any("evidence not in the plan text" in m for m in problems(bad, texts, idx))
        # swap one debris clause for a real clause from a DIFFERENT domain: must be rejected
        bad2 = copy.deepcopy(kv)
        pid, key = next((pid, k) for pid, p in bad2["projects"].items() for k, v in p["law"].items() if v.get("clauses"))
        other = next((law, no) for (law, no), dom in idx.items() if all(d != key for d, _ in dom))
        bad2["projects"][pid]["law"][key]["clauses"][0].update({"law": other[0], "no": other[1]})
        c2 = any("is not a" in m for m in problems(bad2, texts, idx))
        print("self-test:", "corrupted evidence rejected" if c1 else "evidence NOT rejected", "|", "wrong-domain clause rejected" if c2 else "wrong-domain clause NOT rejected")
        sys.exit(0 if c1 and c2 and not problems(kv, texts, idx) else 1)
    errs = problems(kv, texts)
    for m in errs:
        print("FAIL", m)
    if errs:
        sys.exit(1)
    print(f"OK {len(kv['projects'])} projects")
