"""Check app/matching/standard_yunlin_v1.yaml against the locked-in HackMD and the source documents.

Ported from ai-eva-tangle-lab afd0425 tools/match_standard_check.py. No network unless --hackmd.

  python app/matching/check_standard.py            -> structure + decided rules; exit 0 and "OK standard v<version>"
  python app/matching/check_standard.py --hackmd   -> also: the YAML body equals the ```yaml block of the HackMD note
  python app/matching/check_standard.py PATH       -> check another file (e.g. a copy)
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

F = Path(__file__).resolve().parent / "standard_yunlin_v1.yaml"
NOTE = "VFUJQzdQR1OdZZBQrkwB-g"   # https://hackmd.io/@yillkid/BkKiUSPRMl
HEADER = "# 媒合標準 — 雲林農村再生 v1"
B_REG = {"B1": "空間與場域", "B2": "產品與生產", "B3": "服務與體驗", "B4": "內容與品牌",
         "B5": "人才與專業", "B6": "社群與關係", "B7": "市場與通路", "B8": "治理與平台"}   # SH-METHOD-02 §6
STATUSES = ["EXCLUDED", "CLARIFY_FIRST", "EXPLORE", "RECOMMEND", "ELIGIBLE"]              # SH-COLLAB-03 §5


def body(text):
    """YAML body without the header comment lines this file adds (the HackMD block starts at the 2nd HEADER)."""
    lines = text.splitlines()
    if text.startswith(HEADER + "\n#\n# 來源"):
        i = next((k for k, l in enumerate(lines) if k > 0 and l.startswith(HEADER)), 0)
    else:
        i = 0
    return "\n".join(lines[i:]).strip()


def _d(x):
    return x if isinstance(x, dict) else {}


def problems(d):
    out = []
    d = _d(d)
    reg = _d(d.get("capability_registry"))
    for k, name in B_REG.items():
        if _d(reg.get(k)).get("名稱") != name:
            out.append(f"{k} must be {name} (SH-METHOD-02 §6)")
    r = _d(d.get("direction_rules"))
    if r.get("values") != ["NEED", "OFFER", "BOTH"]:
        out.append("directions must be NEED/OFFER/BOTH")
    st = _d(d.get("status_rules"))
    if sorted(st) != sorted(STATUSES):
        out.append("status names must be the five of SH-COLLAB-03 §5")
    if "不開放" not in str(_d(st.get("RECOMMEND")).get("條件", "")):
        out.append("Q4: RECOMMEND must stay closed in phase 1")
    if _d(d.get("out_of_scope")).get("used") != ["Need–Offer 互補", "B1–B8 能力互補"]:
        out.append("Q2: phase 1 uses only Need–Offer and B1–B8")
    if "不補 0" not in str(_d(d.get("missing_policy")).get("rule", "")):
        out.append("missing values must not be filled with 0")
    # v1.1 (Q6/Q7): questions = exactly the fields the source requires; minimum fields among them
    q = _d(d.get("clarify_questions"))
    qn, qo = _d(q.get("NEED")), _d(q.get("OFFER"))
    if sorted(qn) != sorted(r.get("NEED_requires") or []) or sorted(qo) != sorted(r.get("OFFER_requires") or []):
        out.append("clarify_questions must cover exactly NEED_requires / OFFER_requires (SH-METHOD-02 §2)")
    mf = _d(_d(d.get("status_transition")).get("minimum_fields"))
    if mf.get("NEED") not in qn or mf.get("OFFER") not in qo:
        out.append("Q6: minimum_fields must be question fields")
    if "一次只問一題" not in str(q.get("pace", "")):
        out.append("Q7: one question at a time")
    if any("待拍板" in json.dumps(v, ensure_ascii=False) for v in d.values()):
        out.append("still contains 待拍板")
    return out


def check(path=F, hackmd=False):
    """Return (errors, data) for the standard file at path."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        d = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"], None
    errs = problems(d)
    if hackmd:
        tok = os.environ.get("HACKMD_TOKEN", "").strip()
        req = urllib.request.Request(f"https://api.hackmd.io/v1/notes/{NOTE}",
                                     headers={"Authorization": f"Bearer {tok}"})
        note = json.load(urllib.request.urlopen(req, timeout=30))["content"]
        block = note[note.index("```yaml") + 8:note.rindex("```")].strip()
        if block != body(text):
            errs.append("YAML differs from the HackMD note — change HackMD first, then re-extract")
    return errs, d


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    hackmd = "--hackmd" in argv
    paths = [a for a in argv if not a.startswith("--")]
    errs, d = check(paths[0] if paths else F, hackmd=hackmd)
    for e in errs:
        print("FAIL", e)
    if errs:
        return 1
    print(f"OK standard v{_d(d.get('standard')).get('version')}" + (" (matches HackMD)" if hackmd else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
