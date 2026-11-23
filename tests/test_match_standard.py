"""#181 媒合標準 YAML 與離線檢查：原檔通過；複本做三種竄改都要讓檢查失敗。"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.matching import check_standard as cs

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app/matching/check_standard.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, cwd=ROOT)


def test_original_passes():
    p = run()
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip() == "OK standard v0.1.1-r0"


def test_original_has_no_problems():
    errs, d = cs.check()
    assert errs == []
    assert d["standard"]["version"] == "0.1.1-r0"


def _open_recommend(d):
    d["status_rules"]["RECOMMEND"]["條件"] = "適配與信心達門檻即開放"


def _rename_b6(d):
    d["capability_registry"]["B6"]["名稱"] = "社群經營"


def _drop_clarify_field(d):
    del d["clarify_questions"]["OFFER"]["規模"]


@pytest.mark.parametrize("tamper,expect", [
    (_open_recommend, "RECOMMEND"),
    (_rename_b6, "B6"),
    (_drop_clarify_field, "clarify_questions"),
])
def test_tampered_copy_fails(tmp_path, tamper, expect):
    d = yaml.safe_load(cs.F.read_text(encoding="utf-8"))
    tamper(d)
    copy = tmp_path / "standard_copy.yaml"
    copy.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    p = run(copy)
    assert p.returncode == 1, p.stdout
    assert "FAIL" in p.stdout and expect in p.stdout
    assert "OK standard" not in p.stdout


def test_untampered_copy_passes(tmp_path):
    d = yaml.safe_load(cs.F.read_text(encoding="utf-8"))
    copy = tmp_path / "standard_copy.yaml"
    copy.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert run(copy).returncode == 0


def test_body_strips_added_header():
    text = cs.F.read_text(encoding="utf-8")
    b = cs.body(text)
    assert b.startswith(cs.HEADER + "\n# 程式照這份設定跑流程")
    assert "# 來源：" not in b
