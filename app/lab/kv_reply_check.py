"""Check what Eva says when a law-domain satellite is clicked (step 2a). No Chainlit, no third-party deps.

  python3 app/lab/kv_reply_check.py             -> "OK <n> replies" when every reply matches the demo data
  python3 app/lab/kv_reply_check.py --self-test -> exit 0 when a tampered quote is rejected

reply_for() is loaded straight from tangle_lab.py source (the module imports chainlit at the top,
which is not needed for this pure function), so the check runs on the host without the app's deps.
"""
import ast
import copy
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BANNED = ("通過", "已判定", "建議合作")


def load_reply_for():
    src = (HERE / "tangle_lab.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("load_kv_law", "reply_for", "_reply_markdown", "load_kv_match", "match_reply_for", "peer_reply_for", "pair_reply_for", "planet_summary_for",
                                                                       "load_match_standard", "_is_need", "_is_offer", "complement_pairs", "match_status_for", "next_question_for", "third_reply_for",
                                                                       "load_law_standard", "law_question", "parse_law_answer", "law_rule_verdict", "law_status_for", "law_next_question")]
    if len(keep) != 21:
        raise SystemExit("FAIL tangle_lab.py must define the 21 reply, match-rule and law-rule functions (incl. law_rule_verdict, law_next_question)")
    mod = types.ModuleType("reply")
    mod.json, mod.Path, mod._KV_JS, mod.DEMO = json, Path, ROOT / "public/tangle/kv-law-mock.js", "_示範資料_"
    mod._KVM_JS = ROOT / "public/tangle/kv-match-mock.js"
    mod._STD_YAML = ROOT / "app/matching/standard_yunlin_v1.yaml"   # must exist before the functions' default args are evaluated
    mod._LAW_STD_YAML = ROOT / "app/regulations/corpus/standard_yunlin_v1.yaml"
    mod._UNKNOWN = ("還不知道", "不知道", "不確定", "不清楚")
    exec(compile(ast.Module(body=keep, type_ignores=[]), "tangle_lab.py", "exec"), mod.__dict__)
    mod.KV_LAW = mod.load_kv_law()
    mod.KV_MATCH = mod.load_kv_match()
    mod.MATCH_STD = mod.load_match_standard()
    mod.LAW_STD = mod.load_law_standard()
    return mod


def problems(mod, kv):
    out, n = [], 0
    for pid, p in kv["projects"].items():
        for key in list(kv["domains"]) + list(p.get("uncovered", [])):
            r = mod.reply_for("law", pid, key, kv)
            n += 1
            if not r:
                out.append(f"{pid} {key}: no reply")
                continue
            text = r["body"] + "".join(r["quotes"]) + (r["question"] or "")
            if any(b in text for b in BANNED):
                out.append(f"{pid} {key}: banned conclusion word in reply")
            if key in p.get("uncovered", []):
                if r["state"] != "uncovered" or "不代表合規" not in r["body"]:
                    out.append(f"{pid} {key}: uncovered reply must say 沒檢查不代表合規")
                continue
            if "合規" in text:
                out.append(f"{pid} {key}: '合規' only allowed in uncovered replies")
            v = p["law"][key]
            if r["state"] != v["state"]:
                out.append(f"{pid} {key}: state {r['state']} != data {v['state']}")
            if v["state"] == "hit" and r["quotes"] != v["evidence"]:
                out.append(f"{pid} {key}: quotes differ from evidence")
            if v["state"] == "hit":
                if r.get("clauses") != v.get("clauses"):
                    out.append(f"{pid} {key}: reply clauses differ from data clauses")
                md = mod._reply_markdown(r, "P")
                if not all(f"{c['law']} {c['no']}" in md for c in v.get("clauses", [])) or "示範假設" not in md:
                    out.append(f"{pid} {key}: shown reply must list every clause and say 示範假設")
            elif r.get("clauses"):
                out.append(f"{pid} {key}: only 對上了 replies list clauses")
            if v["state"] == "gap" and r["question"] != v["question"]:
                out.append(f"{pid} {key}: question differs from data")
            if v["state"] == "na" and (r["quotes"] or r["question"]):
                out.append(f"{pid} {key}: na reply must carry no quote or question")
    if mod.reply_for("law", "no-such-project", "農村再生", kv) is not None:
        out.append("unknown project must return None")
    # Step E: law clarify loop, rules only from the law standard v0.3
    std = mod.LAW_STD
    for pid, p in kv["projects"].items():
        gaps = [d for d, v in p["law"].items() if v["state"] == "gap"]
        st, open_ = mod.law_status_for(pid, {}, kv)
        if st != ("CLARIFY_FIRST" if gaps else "READY") or sorted(open_) != sorted(gaps):
            out.append(f"{pid}: law status {st} / open {open_} != gaps {gaps}")
        if gaps and mod.law_status_for(pid, {d: "unknown" for d in gaps}, kv)[0] != "CLARIFY_FIRST":
            out.append(f"{pid}: 還不知道 must not count as filled")
        if gaps and mod.law_status_for(pid, {d: "na" for d in gaps}, kv)[0] != "READY":
            out.append(f"{pid}: all gaps answered must be READY")
        asked, seen = set(), []
        while True:
            q = mod.law_next_question(pid, asked, kv, std)
            if not q:
                break
            if q["text"] != mod.law_question(q["field"], std)["ask"]:
                out.append(f"{pid}: question text not from the YAML ({q['field']})")
            seen.append(q["domain"]); asked.add(q["domain"])
            if len(seen) > 20:
                out.append(f"{pid}: questions never end"); break
        if sorted(seen) != sorted(gaps):
            out.append(f"{pid}: asked {seen} but gaps are {gaps}")
        n += 1
    # threshold rules (numbers from the YAML; answers parsed with units)
    qa = mod.law_question("申請開發面積", std)
    th = qa["rule"]["hit_if_gte"] if qa else None
    cases = [("0.8 公頃", "na"), ("1.2公頃", "hit"), (f"{th} 公頃", "hit"), ("8000 平方公尺", "na"), ("12000平方公尺", "hit"),
             ("還不知道", None), ("不清楚", None), ("很大", None)]
    for text, want in cases:
        got = mod.law_rule_verdict(qa, mod.parse_law_answer(qa, text), text) if qa else "no question"
        if got != want:
            out.append(f"開發審議 「{text}」: verdict {got} != {want}")
    ql = mod.law_question("土地使用編定", std)
    for text, want in (("農牧用地", "hit"), ("鄉村區乙種建築用地", "na"), ("還不知道", None)):
        got = mod.law_rule_verdict(ql, mod.parse_law_answer(ql, text), text) if ql else "no question"
        if got != want:
            out.append(f"非都 「{text}」: verdict {got} != {want}")
    qe = mod.law_question("工程規模與位置", std)
    if qe and mod.law_rule_verdict(qe, mod.parse_law_answer(qe, "0.5 公頃，在山坡地"), "0.5 公頃，在山坡地") != "hit":
        out.append("環評: a sensitive area must count as 觸及 even below the area threshold")
    # labels on the law reply (事實 when quotes, 推論 when a judgement is shown)
    for pid, p in kv["projects"].items():
        for d, v in p["law"].items():
            if v["state"] in ("hit", "gap"):
                md = mod._reply_markdown(mod.reply_for("law", pid, d, kv), "P")
                if "**事實**" not in md or "推論（AI，未經 Owner 確認）" not in md:
                    out.append(f"{pid} {d}: law reply must label 事實 and 推論")
    return out, n


def match_problems(mod):
    """Every need/offer key of every project, against every other project as partner."""
    kvm, out, n = mod.KV_MATCH, [], 0
    ids = list(kvm["projects"])
    for pid in ids:
        for k, v in kvm["projects"][pid]["match"].items():
            for q in [None] + [x for x in ids if x != pid]:
                r = mod.match_reply_for(pid, k, q, kvm)
                if v["role"] == "none":
                    if r is not None:
                        out.append(f"{pid} {k}: none must give no reply")
                    continue
                n += 1
                if not r:
                    out.append(f"{pid} {k}: no reply"); continue
                if r["quotes"] != v["evidence"]:
                    out.append(f"{pid} {k}: quotes differ from evidence")
                if r["role"] != v["role"] or {"need": "需要", "offer": "能提供", "both": "需要＋能提供"}[v["role"]] not in r["body"]:
                    out.append(f"{pid} {k}: role not stated")
                if any(b in r["body"] for b in BANNED):
                    out.append(f"{pid} {k}: banned conclusion word")
                if q:
                    other = kvm["projects"][q]["match"][k]["role"]
                    linked = (v["role"] in ("need", "both") and other in ("offer", "both")) or (v["role"] in ("offer", "both") and other in ("need", "both"))
                    if linked != ("航跡" in r["body"]):
                        out.append(f"{pid} {k} vs {q}: route mention does not match need×offer")
    # peer lines: both offer the same B -> reply says 交流經驗, never 互補 or 需要; anything else -> no peer reply
    for a in ids:
        for b in ids:
            if a == b:
                continue
            for k in kvm["keys"]:
                both = kvm["projects"][a]["match"][k]["role"] == "offer" and kvm["projects"][b]["match"][k]["role"] == "offer"
                r = mod.peer_reply_for(a, b, k, kvm)
                if both != (r is not None):
                    out.append(f"{a}×{b} {k}: peer reply exists={r is not None} but both-offer={both}"); continue
                if r:
                    n += 1
                    if "交流經驗" not in r["body"] or "互補" in r["body"] or "需要" in r["body"]:
                        out.append(f"{a}×{b} {k}: peer reply must say 交流經驗 and not 互補/需要")
                    if r["quotes"][a] != kvm["projects"][a]["match"][k]["evidence"] or r["quotes"][b] != kvm["projects"][b]["match"][k]["evidence"]:
                        out.append(f"{a}×{b} {k}: peer quotes differ from evidence")
    # B1 pair replies: exist exactly for need×offer, quote both sides; B2 planet summary = counts from the data
    for a in ids:
        for b in ids:
            if a == b:
                continue
            for k in kvm["keys"]:
                ra, rb = kvm["projects"][a]["match"][k]["role"], kvm["projects"][b]["match"][k]["role"]
                comp = (ra in ("need", "both") and rb in ("offer", "both")) or (rb in ("need", "both") and ra in ("offer", "both"))
                r = mod.pair_reply_for(a, b, k, kvm)
                if comp != (r is not None):
                    out.append(f"{a}×{b} {k}: pair reply exists={r is not None} but complementary={comp}"); continue
                if r:
                    n += 1
                    if r["quotes"][r["need"]] != kvm["projects"][r["need"]]["match"][k]["evidence"] or r["quotes"][r["offer"]] != kvm["projects"][r["offer"]]["match"][k]["evidence"]:
                        out.append(f"{a}×{b} {k}: pair quotes differ")
                    if kvm["projects"][r["need"]]["match"][k]["role"] not in ("need", "both") or kvm["projects"][r["offer"]]["match"][k]["role"] not in ("offer", "both") or "建議合作" in r["body"]:
                        out.append(f"{a}×{b} {k}: pair roles or wording wrong")
            s = mod.planet_summary_for(a, b, kvm)
            m, q = kvm["projects"][a]["match"], kvm["projects"][b]["match"]
            Nn, Oo = ("need", "both"), ("offer", "both")
            want_links = sorted(k for k in kvm["keys"] if (m[k]["role"] in Nn and q[k]["role"] in Oo) or (m[k]["role"] in Oo and q[k]["role"] in Nn))
            want_peers = sorted(k for k in kvm["keys"] if m[k]["role"] == q[k]["role"] == "offer")
            if sorted(s["links"]) != want_links or sorted(s["peers"]) != want_peers or sorted(s["need"]) != sorted(k for k in m if m[k]["role"] in Nn):
                out.append(f"{a}×{b}: planet summary counts wrong")
            n += 1
    # Step C: status rules, questions, third-party replies (standard v1.1)
    std = mod.MATCH_STD
    mf = std["status_transition"]["minimum_fields"]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            st = mod.match_status_for(a, b, {}, kvm, std)
            comp = mod.complement_pairs(a, b, kvm)
            if st == "RECOMMEND":
                out.append(f"{a}×{b}: RECOMMEND must not appear in phase 1")
            if comp and st != "CLARIFY_FIRST":
                out.append(f"{a}×{b}: with candidates and nothing filled, status must be CLARIFY_FIRST ({st})")
            if comp:
                n_, o_, k_ = comp[0]
                half = {f"{n_}:{k_}:{mf['NEED']}": True}
                if mod.match_status_for(a, b, half, kvm, std) != "CLARIFY_FIRST":
                    out.append(f"{a}×{b}: one minimum field alone must not move the status")
                full = {**half, f"{o_}:{k_}:{mf['OFFER']}": True}
                if mod.match_status_for(a, b, full, kvm, std) != "EXPLORE":
                    out.append(f"{a}×{b}: both minimum fields of one candidate must give EXPLORE")
                q1 = mod.next_question_for(a, b, set(), kvm, std)
                if not q1 or not q1["minimum"] or q1["field"] != mf["NEED"]:
                    out.append(f"{a}×{b}: first question must be the NEED minimum field ({q1 and q1['field']})")
                q2 = mod.next_question_for(a, b, {q1["id"]}, kvm, std)
                if not q2 or q2["field"] != mf["OFFER"]:
                    out.append(f"{a}×{b}: second question must be the OFFER minimum field ({q2 and q2['field']})")
                fields = set(std["clarify_questions"]["NEED"]) | set(std["clarify_questions"]["OFFER"])
                seen, ans = [], set()
                while True:
                    q = mod.next_question_for(a, b, ans, kvm, std)
                    if not q:
                        break
                    if q["field"] not in fields or "{" in q["text"]:
                        out.append(f"{a}×{b}: question not from the YAML or unfilled template: {q['text']}")
                        break
                    seen.append(q["id"]); ans.add(q["id"])
                    if len(seen) > 200:
                        out.append(f"{a}×{b}: questions never end"); break
                if len(seen) != len(set(seen)):
                    out.append(f"{a}×{b}: a question was asked twice")
                n += 1
            else:
                A, B = kvm["projects"][a]["match"], kvm["projects"][b]["match"]
                peer = any(A[k]["role"] == "offer" and B[k]["role"] == "offer" for k in kvm["keys"])
                if st != ("EXPLORE" if peer else "ELIGIBLE"):
                    out.append(f"{a}×{b}: no candidates → {('EXPLORE' if peer else 'ELIGIBLE')} expected ({st})")
            for k in kvm["keys"]:
                both_need = kvm["projects"][a]["match"][k]["role"] == "need" and kvm["projects"][b]["match"][k]["role"] == "need"
                r = mod.third_reply_for(a, b, k, kvm)
                if both_need != (r is not None):
                    out.append(f"{a}×{b} {k}: third-party reply exists={r is not None} but both-need={both_need}")
                if r and ("共同尋找第三方" not in r["body"] or "不算互補" not in r["body"]):
                    out.append(f"{a}×{b} {k}: third-party wording")
                pr = mod.pair_reply_for(a, b, k, kvm)
                if pr and ("對上了" in pr["body"] or "互補候選" not in pr["body"]):
                    out.append(f"{a}×{b} {k}: pair wording must say 互補候選, never 對上了")
    return out, n


if __name__ == "__main__":
    mod = load_reply_for()
    kv = mod.KV_LAW
    if "--self-test" in sys.argv:
        bad = copy.deepcopy(kv)
        pid, key = next((pid, k) for pid, p in bad["projects"].items() for k, v in p["law"].items() if v["state"] == "hit")
        real = mod.reply_for
        mod.reply_for = lambda *a, **k: (lambda r: {**r, "quotes": ["竄改過的引文"]} if r and r["state"] == "hit" else r)(real(*a, **k))
        caught = any("quotes differ" in m for m in problems(mod, bad)[0])
        mod.reply_for = real
        print("self-test:", "tampered quote rejected" if caught else "NOT rejected")
        sys.exit(0 if caught and not problems(mod, kv)[0] else 1)
    errs, n = problems(mod, kv)
    merrs, mn = match_problems(mod)
    for m in errs + merrs:
        print("FAIL", m)
    if errs or merrs:
        sys.exit(1)
    if "MATCH_DEMO" not in (HERE / "tangle_lab.py").read_text(encoding="utf-8"):
        print("FAIL match replies must carry the demo note"); sys.exit(1)
    print(f"OK {n} replies")
    print(f"OK {mn} match replies")
