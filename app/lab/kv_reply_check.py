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
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("load_kv_law", "reply_for", "_reply_markdown", "load_kv_match", "match_reply_for", "peer_reply_for", "pair_reply_for", "planet_summary_for")]
    if len(keep) != 8:
        raise SystemExit("FAIL tangle_lab.py must define load_kv_law, reply_for, _reply_markdown, load_kv_match and match_reply_for")
    mod = types.ModuleType("reply")
    mod.json, mod.Path, mod._KV_JS, mod.DEMO = json, Path, ROOT / "public/tangle/kv-law-mock.js", "_示範資料_"
    mod._KVM_JS = ROOT / "public/tangle/kv-match-mock.js"
    exec(compile(ast.Module(body=keep, type_ignores=[]), "tangle_lab.py", "exec"), mod.__dict__)
    mod.KV_LAW = mod.load_kv_law()
    mod._KVM_JS = ROOT / "public/tangle/kv-match-mock.js"
    mod.KV_MATCH = mod.load_kv_match()
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
                if r["role"] != v["role"] or ("需要" if v["role"] == "need" else "能提供") not in r["body"]:
                    out.append(f"{pid} {k}: role not stated")
                if any(b in r["body"] for b in BANNED):
                    out.append(f"{pid} {k}: banned conclusion word")
                if q:
                    other = kvm["projects"][q]["match"][k]["role"]
                    linked = (v["role"] == "need" and other == "offer") or (v["role"] == "offer" and other == "need")
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
                comp = {ra, rb} == {"need", "offer"}
                r = mod.pair_reply_for(a, b, k, kvm)
                if comp != (r is not None):
                    out.append(f"{a}×{b} {k}: pair reply exists={r is not None} but complementary={comp}"); continue
                if r:
                    n += 1
                    if r["quotes"][r["need"]] != kvm["projects"][r["need"]]["match"][k]["evidence"] or r["quotes"][r["offer"]] != kvm["projects"][r["offer"]]["match"][k]["evidence"]:
                        out.append(f"{a}×{b} {k}: pair quotes differ")
                    if kvm["projects"][r["need"]]["match"][k]["role"] != "need" or "建議合作" in r["body"]:
                        out.append(f"{a}×{b} {k}: pair roles or wording wrong")
            s = mod.planet_summary_for(a, b, kvm)
            m, q = kvm["projects"][a]["match"], kvm["projects"][b]["match"]
            want_links = sorted(k for k in kvm["keys"] if {m[k]["role"], q[k]["role"]} == {"need", "offer"})
            want_peers = sorted(k for k in kvm["keys"] if m[k]["role"] == q[k]["role"] == "offer")
            if sorted(s["links"]) != want_links or sorted(s["peers"]) != want_peers or sorted(s["need"]) != sorted(k for k in m if m[k]["role"] == "need"):
                out.append(f"{a}×{b}: planet summary counts wrong")
            n += 1
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
