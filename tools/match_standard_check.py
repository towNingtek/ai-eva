"""Check app/matching/standard_yunlin_v1.yaml against the locked-in HackMD and the source documents. No network unless --hackmd.

  python3 tools/match_standard_check.py            -> structure + decided rules; exit 0 and "OK standard v<version>"
  python3 tools/match_standard_check.py --hackmd   -> also: the YAML body equals the ```yaml block of the HackMD note
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "app/matching/standard_yunlin_v1.yaml"
NOTE = "VFUJQzdQR1OdZZBQrkwB-g"   # https://hackmd.io/@yillkid/BkKiUSPRMl
B_REG = {"B1": "空間與場域", "B2": "產品與生產", "B3": "服務與體驗", "B4": "內容與品牌",
         "B5": "人才與專業", "B6": "社群與關係", "B7": "市場與通路", "B8": "治理與平台"}   # SH-METHOD-02 §6


def body(text):
    """YAML body without the header comment lines this file adds."""
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith("# 媒合標準 — 雲林農村再生 v1") and k > 0) if text.startswith("# 媒合標準 — 雲林農村再生 v1\n#\n# 來源") else 0
    return "\n".join(lines[i:]).strip()


def problems(d):
    out = []
    reg = d.get("capability_registry", {})
    for k, name in B_REG.items():
        if reg.get(k, {}).get("名稱") != name:
            out.append(f"{k} must be {name} (SH-METHOD-02 §6)")
    if d.get("direction_rules", {}).get("values") != ["NEED", "OFFER", "BOTH"]:
        out.append("directions must be NEED/OFFER/BOTH")
    if sorted(d.get("status_rules", {})) != sorted(["EXCLUDED", "CLARIFY_FIRST", "EXPLORE", "RECOMMEND", "ELIGIBLE"]):
        out.append("status names must be the five of SH-COLLAB-03 §5")
    rec = str(d.get("status_rules", {}).get("RECOMMEND", {}).get("條件", ""))
    if "不開放" not in rec:
        out.append("Q4: RECOMMEND must stay closed in phase 1")
    if d.get("out_of_scope", {}).get("used") != ["Need–Offer 互補", "B1–B8 能力互補"]:
        out.append("Q2: phase 1 uses only Need–Offer and B1–B8")
    if "不補 0" not in d.get("missing_policy", {}).get("rule", ""):
        out.append("missing values must not be filled with 0")
    if any("待拍板" in json.dumps(v, ensure_ascii=False) for v in d.values()):
        out.append("still contains 待拍板")
    return out


if __name__ == "__main__":
    text = F.read_text(encoding="utf-8")
    d = yaml.safe_load(text)
    errs = problems(d)
    if "--hackmd" in sys.argv:
        tok = os.environ.get("HACKMD_TOKEN", "").strip()
        req = urllib.request.Request(f"https://api.hackmd.io/v1/notes/{NOTE}", headers={"Authorization": f"Bearer {tok}"})
        note = json.load(urllib.request.urlopen(req, timeout=30))["content"]
        block = note[note.index("```yaml") + 8:note.rindex("```")].strip()
        if block != body(text):
            errs.append("YAML differs from the HackMD note — change HackMD first, then re-extract")
    for e in errs:
        print("FAIL", e)
    if errs:
        sys.exit(1)
    print(f"OK standard v{d['standard']['version']}" + (" (matches HackMD)" if "--hackmd" in sys.argv else ""))
