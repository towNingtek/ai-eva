#!/usr/bin/env python3
"""Law standard checks (v0.3).  python3 tools/law_standard_check.py [--hackmd]

- every 缺資料 field in the demo data has a clarify question; every question names a covered domain
- every rule is numeric (hit_if_gte) or a closed choice (hit_if_in ⊆ options); no free-form judging
- status_transition: rule_only, affected_domain_only, unknown does not count, one question at a time
- --hackmd: the YAML body in the repo == the ```yaml block on HackMD BJIzoEIzzg (token from $HACKMD_TOKEN)
"""
import json, os, sys, urllib.request
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
STD = ROOT / "app/regulations/corpus/standard_yunlin_v1.yaml"
KV = ROOT / "public/tangle/kv-law-mock.js"


def body(text):
    return text.split("standard:", 1)[1].strip()


def check(std, kv):
    out = []
    cq, st, dom = std.get("clarify_questions") or [], std.get("status_transition") or {}, set(std["coverage"]["covered"])
    fields = {q["field"] for q in cq}
    if not cq:
        out.append("clarify_questions missing")
    for q in cq:
        if q.get("domain") not in dom:
            out.append(f"{q.get('field')}: domain {q.get('domain')} not in coverage")
        r = q.get("rule") or {}
        if not ("hit_if_gte" in r or "hit_if_in" in r):
            out.append(f"{q['field']}: rule must be hit_if_gte or hit_if_in")
        if "hit_if_in" in r and not set(r["hit_if_in"]) <= set(q.get("options") or []):
            out.append(f"{q['field']}: hit_if_in not within options")
        if "{" in q.get("ask", "") or not q.get("ask"):
            out.append(f"{q['field']}: ask text")
    for pid, p in kv["projects"].items():
        for d, v in p["law"].items():
            if v["state"] == "gap" and v.get("missing") not in fields:
                out.append(f"{pid} {d}: gap field {v.get('missing')} has no clarify question")
    want = {"recompute": "rule_only", "scope": "affected_domain_only", "unknown_counts_as_filled": False, "pace": "one_question_at_a_time"}
    for k, v in want.items():
        if st.get(k) != v:
            out.append(f"status_transition.{k} must be {v!r} (is {st.get(k)!r})")
    if st.get("buttons") != ["還不知道", "跳過"]:
        out.append("status_transition.buttons must be [還不知道, 跳過]")
    return out


def main():
    std = yaml.safe_load(STD.read_text(encoding="utf-8"))
    s = KV.read_text(encoding="utf-8")
    kv = json.loads(s[s.index("{"):s.rindex("}") + 1])
    if "--self-test" in sys.argv:
        bad = json.loads(json.dumps(std))
        bad["clarify_questions"] = [q for q in bad["clarify_questions"] if q["field"] != "申請開發面積"]
        assert any("申請開發面積" in x for x in check(bad, kv)), "missing question not caught"
        bad = json.loads(json.dumps(std)); bad["status_transition"]["recompute"] = "llm"
        assert check(bad, kv), "llm recompute not caught"
        print("self-test: missing question and llm recompute both rejected"); return
    problems = check(std, kv)
    if "--hackmd" in sys.argv:
        tok = os.environ.get("HACKMD_TOKEN")
        if not tok:
            sys.exit("FAIL --hackmd needs HACKMD_TOKEN")
        note = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.hackmd.io/v1/notes/BJIzoEIzzg", headers={"Authorization": "Bearer " + tok}), timeout=30))["content"]
        block = note.split("```yaml", 1)[1].split("```", 1)[0]
        if body(block) != body(STD.read_text(encoding="utf-8")):
            problems.append("repo YAML differs from HackMD BJIzoEIzzg (change HackMD first, then re-extract)")
    for p in problems:
        print("FAIL", p)
    if problems:
        sys.exit(1)
    print(f"OK law standard {std['standard']['version']} · {len(std['clarify_questions'])} questions")


if __name__ == "__main__":
    main()
