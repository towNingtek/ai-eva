"""計分程式的行為（tplanet-multi-tenant#113）：不連網、不叫 LLM。"""
import json
import subprocess
import sys
from pathlib import Path

from app.regulations.eval import score as S

ROOT = Path(__file__).resolve().parents[1]


def _f(law, v="觸發", d="農村再生"):
    return {"regulation": law, "verdict": v, "law_domain": d}


def test_law_level_scope_and_adjudication():
    runs = {"A": {"findings": [_f("甲法"), _f("甲法"), _f("乙法"), _f("丙法", "不觸及"), _f("外法", d="觀光民宿")]},
            "B": {"findings": [_f("甲法"), _f("丁法")]}}
    golden = {"cases": {"A": {"expected": ["甲法", "丙法"]}, "B": {"expected": ["甲法"]}}}
    s = S.score(golden, runs)
    assert (s["tp"], s["fp"], s["fn"]) == (2, 2, 1)          # 同一部法多條只算一次；範圍外不計
    assert "外法" not in s["cases"]["A"]["extra"]
    golden["adjudications"] = [{"case": "B", "law": "丁法", "decision": "accept_system"}]
    s2 = S.score(golden, runs)
    assert (s2["tp"], s2["fp"], s2["fn"]) == (3, 1, 1)        # 甲方裁定系統對 → 不扣分


def test_thresholds_are_the_spec():
    assert S.TARGET == {"recall": 0.85, "precision": 0.65}


def test_golden_is_reproducible_from_the_plans():
    """golden.json 必須能由 golden_draft.py 從 plans10.json 原樣重建（不是手改、不是抄系統輸出）。"""
    out = subprocess.run([sys.executable, str(ROOT / "app/regulations/eval/golden_draft.py"),
                          str(ROOT / "app/regulations/eval/plans10.json")], capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["cases"] == json.loads((ROOT / "app/regulations/eval/golden.json").read_text(encoding="utf-8"))["cases"]


def test_golden_covers_the_ten_cases():
    g = json.loads((ROOT / "app/regulations/eval/golden.json").read_text(encoding="utf-8"))
    assert len(g["cases"]) == 10
    for c in g["cases"].values():
        assert c["expected"] and all(isinstance(x, str) for x in c["expected"])
