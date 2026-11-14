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
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("load_kv_law", "reply_for")]
    if len(keep) != 2:
        raise SystemExit("FAIL tangle_lab.py must define load_kv_law and reply_for")
    mod = types.ModuleType("reply")
    mod.json, mod.Path, mod._KV_JS = json, Path, ROOT / "public/tangle/kv-law-mock.js"
    exec(compile(ast.Module(body=keep, type_ignores=[]), "tangle_lab.py", "exec"), mod.__dict__)
    mod.KV_LAW = mod.load_kv_law()
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
            if v["state"] == "gap" and r["question"] != v["question"]:
                out.append(f"{pid} {key}: question differs from data")
            if v["state"] == "na" and (r["quotes"] or r["question"]):
                out.append(f"{pid} {key}: na reply must carry no quote or question")
    if mod.reply_for("law", "no-such-project", "農村再生", kv) is not None:
        out.append("unknown project must return None")
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
    for m in errs:
        print("FAIL", m)
    if errs:
        sys.exit(1)
    print(f"OK {n} replies")
