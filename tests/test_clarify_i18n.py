"""#208: every clarify question in both standards has zh/en/ja/ko with the same placeholders.

Translations live in the YAML (human-reviewed); nothing is machine-translated at run time.
"""
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LANGS = ("en", "ja", "ko")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


match_check = _load("match_standard_check")
law_check = _load("law_standard_check")
MATCH = yaml.safe_load((ROOT / "app/matching/standard_yunlin_v1.yaml").read_text(encoding="utf-8"))
LAW = yaml.safe_load((ROOT / "app/regulations/corpus/standard_yunlin_v1.yaml").read_text(encoding="utf-8"))


# ── current standards pass ────────────────────────────────────────────────────

def test_match_standard_all_four_languages():
    assert match_check.clarify_i18n_problems(MATCH) == []
    q = MATCH["clarify_questions"]
    for side in ("NEED", "OFFER"):
        assert q[side], side
        for field, zh in q[side].items():
            for lang in LANGS:
                s = q["i18n"][lang][side][field]
                assert s.strip() and s != zh
                assert match_check.placeholders(s) == match_check.placeholders(zh)


def test_match_questions_format_in_every_language():
    q = MATCH["clarify_questions"]
    args = {"need": "N", "offer": "O", "b": "B"}
    for side in ("NEED", "OFFER"):
        for field in q[side]:
            for lang in LANGS:
                assert q["i18n"][lang][side][field].format(**args)


def test_law_standard_all_four_languages():
    assert law_check.clarify_i18n_problems(LAW) == []
    cq = LAW["clarify_questions"]
    assert cq
    for q in cq:
        for lang in LANGS:
            s = q["ask_i18n"][lang]
            assert s.strip() and s != q["ask"]
            assert law_check.placeholders(s) == law_check.placeholders(q["ask"])


# ── a missing language or a placeholder mismatch fails ────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_match_missing_language_fails(lang):
    bad = copy.deepcopy(MATCH)
    del bad["clarify_questions"]["i18n"][lang]["NEED"]["用途"]
    errs = match_check.clarify_i18n_problems(bad)
    assert any("NEED.用途" in e and lang in e for e in errs), errs
    assert match_check.problems(bad)   # the CLI check fails too


def test_match_whole_language_missing_fails():
    bad = copy.deepcopy(MATCH)
    del bad["clarify_questions"]["i18n"]["ko"]
    assert any("i18n.ko missing" in e for e in match_check.clarify_i18n_problems(bad))


def test_match_placeholder_mismatch_fails():
    bad = copy.deepcopy(MATCH)
    bad["clarify_questions"]["i18n"]["en"]["OFFER"]["可提供形式"] = "In what form can {offer} provide it?"   # {b} dropped
    errs = match_check.clarify_i18n_problems(bad)
    assert any("OFFER.可提供形式" in e and "placeholders" in e for e in errs), errs


def test_match_new_zh_question_without_translation_fails():
    bad = copy.deepcopy(MATCH)
    bad["clarify_questions"]["OFFER"]["費用"] = "{offer} 的費用怎麼算？"
    errs = match_check.clarify_i18n_problems(bad)
    assert {f"clarify OFFER.費用: {lang} missing" for lang in LANGS} <= set(errs), errs


@pytest.mark.parametrize("lang", LANGS)
def test_law_missing_language_fails(lang):
    bad = copy.deepcopy(LAW)
    del bad["clarify_questions"][0]["ask_i18n"][lang]
    errs = law_check.clarify_i18n_problems(bad)
    assert any(f"ask_i18n.{lang} missing" in e for e in errs), errs


def test_law_placeholder_mismatch_fails():
    bad = copy.deepcopy(LAW)
    bad["clarify_questions"][1]["ask_i18n"]["ja"] = "{b} は何戸ですか？"
    errs = law_check.clarify_i18n_problems(bad)
    assert any("ask_i18n.ja placeholders" in e for e in errs), errs


def test_law_question_without_i18n_fails():
    bad = copy.deepcopy(LAW)
    del bad["clarify_questions"][2]["ask_i18n"]
    errs = law_check.clarify_i18n_problems(bad)
    assert len([e for e in errs if bad["clarify_questions"][2]["field"] in e]) == 3, errs
