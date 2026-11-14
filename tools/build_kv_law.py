"""Build public/tangle/kv-law-mock.js — DEMO data for the 法領域 view (step 1).

evidence: verbatim substrings of each project's public philosophy (reusing the already
          verified topic quotes). Everything else (state, confidence, count, question,
          uncovered) is an illustrative assumption, NOT a legal determination.

Assumption pattern (same for every project, grounded in what the texts do/don't say):
  - no plan states an area/household figure  -> 開發審議, 環境影響評估 are 缺資料 when the
    plan mentions works; otherwise 不適用
  - no plan mentions slopes/hills           -> 水土保持 不適用
  - all are rural communities               -> 都市計畫 不適用
"""
import json
import sys
from pathlib import Path

DOMAINS = ["農村再生", "區域計畫", "國土計畫", "都市計畫", "非都市土地使用管制",
           "開發審議", "環境影響評估", "水土保持", "農業發展", "農地農用認定"]
Q_AREA = "申請開發或變更的基地面積多大？（原文沒有寫）"
Q_SCALE = "這次的工程規模與位置？（原文沒有寫）"
Q_LAND = "要整建的土地目前編定為哪一種用地？"
Q_FARM = "這塊地目前是否作農業使用？"
# short label shown under a 缺資料 satellite (must fit; the full question is for Eva in step 2)
M = {Q_AREA: "申請開發面積", Q_SCALE: "工程規模與位置", Q_LAND: "土地使用編定", Q_FARM: "是否作農業使用"}


def build(data):
    out = {}
    for p in data["projects"]:
        q = {i["theme"]: i for i in p["issues"]}
        ev = lambda *themes: [q[t]["quote"] for t in themes if t in q]
        concrete = lambda t: t in q and q[t]["concrete"]
        works = ev("facility", "house", "env")            # anything that implies construction / land change
        law = {}
        # 農村再生: participation + the plan itself — always touches the rural-regen programme rules
        e = ev("participation", "culture", "industry")[:3]
        law["農村再生"] = {"state": "hit", "confidence": "high", "count": {"risk": 0, "note": 3 + len(e) * 2}, "evidence": e}
        # 非都市土地使用管制: works on rural land
        if works:
            law["非都市土地使用管制"] = ({"state": "hit", "confidence": "mid", "count": {"risk": 1 + (1 if concrete("house") else 0), "note": 3}, "evidence": works[:2]}
                                 if any(concrete(t) for t in ("facility", "house", "env")) else
                                 {"state": "gap", "evidence": works[:1], "question": Q_LAND})
        else:
            law["非都市土地使用管制"] = {"state": "na", "evidence": []}
        # 開發審議 / 環評: depend on a size threshold nobody states
        law["開發審議"] = {"state": "gap", "evidence": works[:1], "question": Q_AREA} if works else {"state": "na", "evidence": []}
        eco = ev("ecology")
        law["環境影響評估"] = ({"state": "gap", "evidence": (eco or works)[:1], "question": Q_SCALE} if (eco and concrete("ecology")) or len(works) >= 2
                           else {"state": "na", "evidence": []})
        # 農業發展 / 農地農用認定
        ind = ev("industry", "experience")
        law["農業發展"] = ({"state": "hit", "confidence": "mid" if concrete("industry") else "low", "count": {"risk": 0, "note": 2 + len(ind)}, "evidence": ind[:2]}
                       if ind else {"state": "na", "evidence": []})
        law["農地農用認定"] = ({"state": "gap", "evidence": ev("experience")[:1], "question": Q_FARM} if "experience" in q and concrete("experience")
                         else {"state": "hit", "confidence": "low", "count": {"risk": 1, "note": 0}, "evidence": ev("industry")[:1]} if concrete("industry") and works
                         else {"state": "na", "evidence": []})
        # planning-level laws: nothing in a community plan triggers them directly
        for d in ("區域計畫", "國土計畫", "都市計畫", "水土保持"):
            law[d] = {"state": "na", "evidence": []}
        # outside the corpus: what the plan mentions that no collected law covers
        unc = []
        if "culture" in q and concrete("culture"):
            unc.append("文化資產")
        if "ecology" in q and concrete("ecology"):
            unc.append("水利")
        if "experience" in q and concrete("experience") and len(unc) < 2:
            unc.append("觀光休閒")
        for v in law.values():
            if v["state"] == "gap":
                v["missing"] = M[v["question"]]
        out[p["id"]] = {"name": p["name"], "law": {d: law[d] for d in DOMAINS}, "uncovered": unc[:2]}
    return {"demo": True, "note": "示範資料：狀態、把握、數量、缺口問題、未收錄領域與「對上哪幾條」是假設值，不是實際判定結果；evidence 是計畫理念原文，clauses 是條文庫裡的真實條文。",
            "domains": DOMAINS, "projects": out}


RISK_TAGS = ("實質管制", "罰則")


def attach_clauses(kv, corpus):
    """Step 2b: give every 對上了 domain the clause debris it shows when you walk into it.

    Real clauses from the regulation corpus (negative_list.json), picked deterministically: per kind
    (risk = 實質管制/罰則, note = the rest) take the first clause of each different law, then fill up.
    WHICH clauses "match" is a demo assumption — no judgement has been run.
    """
    pool = {}
    for law, items in corpus.items():
        for it in items:
            kind = "risk" if it["tag"] in RISK_TAGS else "note"
            pool.setdefault((it["law_domain"], kind), []).append(
                {"law": law, "no": it["article_no"], "tag": it["tag"], "situation": it["situation"], "kind": kind})

    def pick(domain, kind, n, salt):
        cand = pool.get((domain, kind), [])
        if len(cand) < n:
            raise SystemExit(f"corpus has only {len(cand)} {kind} clauses for {domain}, need {n}")
        # rotate by project so neighbouring plans do not all show the identical first clauses
        cand = cand[salt % len(cand):] + cand[:salt % len(cand)]
        first, rest, seen = [], [], set()
        for c in cand:
            (rest if c["law"] in seen else first).append(c)
            seen.add(c["law"])
        return (first + rest)[:n]

    for i, (pid, p) in enumerate(kv["projects"].items()):
        for domain, v in p["law"].items():
            if v["state"] == "hit":
                v["clauses"] = pick(domain, "risk", v["count"]["risk"], i * 7) + pick(domain, "note", v["count"]["note"], i * 7)
    return kv


if __name__ == "__main__":
    # usage: build_kv_law.py <tangle_data.json> <out kv-law-mock.js> <negative_list.json>
    src, dst, corpus = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    kv = attach_clauses(build(json.loads(src.read_text(encoding="utf-8"))), json.loads(corpus.read_text(encoding="utf-8")))
    dst.write_text("// Generated by tools/build_kv_law.py — DEMO data, do not hand edit.\nconst KV_LAW=" + json.dumps(kv, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    from collections import Counter
    c = Counter(v["state"] for p in kv["projects"].values() for v in p["law"].values())
    print("written", len(kv["projects"]), "projects", dict(c))
