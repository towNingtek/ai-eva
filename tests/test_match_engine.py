"""#200 媒合引擎（第一期兩維）：硬條件過濾、各維度分開不合成總分、規則可揭露。"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from app.matching import engine as eng
from app.matching import records as rec
from app.matching import schema as sch
from app.matching.records import Viewer

HERE = Path(__file__).resolve().parent

A_TEXT = "我們有閒置穀倉可借用。希望找人協助行銷通路。也想有人幫忙設計品牌。"


def proj(pid, caps, *, site="yunlin", public=True, text=""):
    return {"id": pid, "name": f"計畫{pid}", "site": site, "public": public, "capabilities": caps,
            "philosophy": text}


A = proj("A", {"capabilities": {
    "B1": {"direction": "OFFER", "evidence": [{"quote": "閒置穀倉可借用", "kind": "concrete"}]},
    "B7": {"direction": "NEED", "evidence": [{"quote": "希望找人協助行銷通路", "kind": "aim"}]},
    "B4": {"direction": "NEED", "evidence": [{"quote": "想有人幫忙設計品牌", "kind": "aim"}]},
}}, text=A_TEXT)
# 雙向互補（B1、B7）
T_BI = proj("bi", {"B1": "NEED", "B7": "OFFER"})
# 單向互補，2 條（A 需要的 B7、B4 對方都能提供；對方的 B3 需求 A 不能提供）
T_ONE2 = proj("one2", {"B7": "BOTH", "B4": "OFFER", "B3": "NEED"})
# 單向互補，1 條
T_ONE1 = proj("one1", {"B7": "OFFER"})
# 無互補
T_NONE = proj("none", {"B1": "OFFER", "B5": "NEED"})
T_PRIVATE = proj("priv", {"B1": "NEED", "B7": "OFFER"}, public=False)
T_OTHER = proj("other", {"B1": "NEED", "B7": "OFFER"}, site="tainan")

FORBIDDEN = {"score", "total", "total_score", "總分", "fit", "overall"}


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


# ── (a) 2、3、4 個對象 ───────────────────────────────────────────────

@pytest.mark.parametrize("targets", [
    [T_ONE1, T_BI],
    [T_NONE, T_ONE1, T_BI],
    [T_NONE, T_ONE1, T_ONE2, T_BI],
])
def test_two_to_four_targets(targets):
    r = eng.match(A, targets)
    assert len(r["results"]) == len(targets)
    assert len(r["ranking"]) == len(targets)
    assert r["order"][0] == "bi"
    assert [x["rank"] for x in r["ranking"]] == list(range(1, len(targets) + 1))


@pytest.mark.parametrize("n", [0, 1, 5])
def test_target_count_out_of_range(n):
    pool = [proj(f"t{i}", {}) for i in range(n)]
    with pytest.raises(eng.MatchInputError):
        eng.match(A, pool)


def test_duplicate_or_self_rejected():
    with pytest.raises(eng.MatchInputError):
        eng.match(A, [T_BI, T_BI])
    with pytest.raises(eng.MatchInputError):
        eng.match(A, [T_BI, A])


# ── (b) 兩維各自輸出，沒有總分 ───────────────────────────────────────

def test_two_dimensions_separate_no_total():
    r = eng.match(A, [T_BI, T_ONE1, T_NONE])
    for res in r["results"]:
        assert set(res["dimensions"]) == {"need_offer", "b1_b8"}
        assert res["dimensions"]["need_offer"]["verdict"] in (eng.BIDIRECTIONAL, eng.ONE_WAY, eng.NO_COMPLEMENT)
        assert res["dimensions"]["b1_b8"]["verdict"].startswith("互補候選")
    keys = {k.lower() for k in walk_keys(r)}
    assert not (keys & FORBIDDEN), keys & FORBIDDEN
    by = {x["target"]: x["dimensions"] for x in r["results"]}
    assert by["bi"]["need_offer"]["verdict"] == eng.BIDIRECTIONAL
    assert by["bi"]["b1_b8"]["complement_count"] == 2
    assert by["one1"]["need_offer"]["verdict"] == eng.ONE_WAY
    assert by["none"]["need_offer"]["verdict"] == eng.NO_COMPLEMENT
    assert by["none"]["b1_b8"]["complement_count"] == 0
    assert by["none"]["b1_b8"]["peer"] == ["B1"]
    assert by["none"]["b1_b8"]["categories"]["B1"]["relation"] == "可聯合或交流"


def test_evidence_quotes_from_philosophy():
    r = eng.match(A, [T_BI, T_ONE1])
    no = next(x for x in r["results"] if x["target"] == "bi")["dimensions"]["need_offer"]
    a_gets = no["a_needs_target_offers"]
    assert [e["key"] for e in a_gets] == ["B7"]
    assert a_gets[0]["need_evidence"] == ["希望找人協助行銷通路"]
    t_gets = no["target_needs_a_offers"]
    assert t_gets[0]["offer_evidence"] == ["閒置穀倉可借用"]
    for q in a_gets[0]["need_evidence"] + t_gets[0]["offer_evidence"]:
        assert q in A_TEXT


# ── (c) 四維標「未評估」 ─────────────────────────────────────────────

def test_four_dimensions_not_evaluated():
    r = eng.match(A, [T_BI, T_ONE1])
    want = {"議題與目標對象", "合作可執行性", "跨國語境與成本", "階段與時程"}
    assert {v["name"] for v in r["not_evaluated"].values()} == want
    assert all(v["status"] == "未評估" for v in r["not_evaluated"].values())
    for res in r["results"]:
        assert len(res["not_evaluated"]) == 4
        assert all(v["status"] == "未評估" for v in res["not_evaluated"].values())


# ── (d) 硬條件排除附原因 ─────────────────────────────────────────────

def test_hard_filter_excludes_with_reason():
    r = eng.match(A, [T_PRIVATE, T_BI, T_OTHER, T_ONE1])
    ex = {e["target"]: e for e in r["excluded"]}
    assert ex["priv"]["reasons"] == ["非公開"]
    assert ex["other"]["reasons"] == ["不同站"]
    assert ex["priv"]["rules"][0]["原文"]
    assert r["order"] == ["bi", "one1"]
    assert {x["target"] for x in r["results"]} == {"bi", "one1"}


def test_hard_filter_multiple_reasons():
    both = proj("both", {}, site="x", public=False)
    r = eng.match(A, [both, T_BI])
    assert r["excluded"][0]["reasons"] == ["非公開", "不同站"]


def test_all_excluded():
    r = eng.match(A, [T_PRIVATE, T_OTHER])
    assert r["ranking"] == [] and r["order"] == [] and len(r["excluded"]) == 2


# ── (e) profile_id 記在結果裡；同 profile 重跑順序相同 ────────────────

def _profile_copy(tmp_path, **changes):
    prof = yaml.safe_load(eng.PROFILE.read_text(encoding="utf-8"))
    prof.update(changes)
    p = tmp_path / "ranking_profile.yaml"
    p.write_text(yaml.safe_dump(prof, allow_unicode=True), encoding="utf-8")
    return p


def test_profile_id_recorded(tmp_path):
    default = yaml.safe_load(eng.PROFILE.read_text(encoding="utf-8"))
    r = eng.match(A, [T_BI, T_ONE1])
    assert r["profile_id"] == default["profile_id"]
    assert r["effective_at"] == str(default["effective_at"])
    assert r["ranking_config"]["profile_id"] == default["profile_id"]

    p = _profile_copy(tmp_path, profile_id="test-profile-x", effective_at="2027-01-01")
    r2 = eng.match(A, [T_BI, T_ONE1], profile=p)
    assert r2["profile_id"] == "test-profile-x"
    assert r2["effective_at"] == "2027-01-01"
    assert r2["ranking_config"]["version"] == "test-profile-x"


def test_same_profile_same_order():
    targets = [T_NONE, T_ONE1, T_ONE2, T_BI]
    first = eng.match(A, targets)
    for _ in range(5):
        again = eng.match(A, targets)
        assert again["order"] == first["order"]
        assert json.dumps(again, ensure_ascii=False, sort_keys=True) == \
            json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert first["order"] == ["bi", "one2", "one1", "none"]


def test_profile_rules_drive_order(tmp_path):
    # 把互補候選數放到第一條：單向 2 條 vs 雙向 2 條同分 → 再看雙向
    prof = yaml.safe_load(eng.PROFILE.read_text(encoding="utf-8"))
    rules = list(reversed(prof["ranking_rules"]))
    p = _profile_copy(tmp_path, profile_id="count-first", ranking_rules=rules)
    r = eng.match(A, [T_ONE2, T_BI], profile=p)
    assert r["profile_id"] == "count-first"
    counts = {x["target"]: x["dimensions"]["b1_b8"]["complement_count"] for x in r["results"]}
    assert counts["one2"] == 2 and counts["bi"] == 2
    assert r["order"] == ["bi", "one2"]
    assert r["ranking"][0]["decided_by"]["rule"] == "bidirectional"


def test_tie_break_by_input_order():
    t1, t2 = proj("x1", {"B7": "OFFER"}), proj("x2", {"B7": "OFFER"})
    assert eng.match(A, [t1, t2])["order"] == ["x1", "x2"]
    r = eng.match(A, [t2, t1])
    assert r["order"] == ["x2", "x1"]
    assert r["ranking"][0]["decided_by"]["rule"] == "input_order"
    assert r["ranking"][0]["decided_by"]["原文"]


# ── (f) 每個名次附規則名稱與原文 ─────────────────────────────────────

def test_each_rank_discloses_rules():
    prof = yaml.safe_load(eng.PROFILE.read_text(encoding="utf-8"))
    names = {r["name"] for r in prof["ranking_rules"]}
    r = eng.match(A, [T_NONE, T_ONE1, T_ONE2, T_BI])
    for pos in r["ranking"]:
        assert names <= {x["name"] for x in pos["rules"]}
        assert all(x["name"] and x["原文"] for x in pos["rules"])
        d = pos["decided_by"]
        assert d["name"] and d["原文"] and d["compared_with"]
    by = {p["target"]: p for p in r["ranking"]}
    assert by["bi"]["decided_by"]["name"] == "雙向互補優先"
    assert by["one2"]["decided_by"]["name"] == "雙向互補優先"
    assert by["one1"]["decided_by"]["name"] == "互補候選數多者優先"
    assert by["none"]["decided_by"]["name"] == "雙向互補優先"
    vals = {x["rule"]: x["value"] for x in by["bi"]["rules"]}
    assert vals["bidirectional"] == 2 and vals["complement_count"] == 2


def test_profile_file_shape():
    prof = eng.load_profile()
    assert prof["profile_id"] and prof["effective_at"]
    assert all(r.get("原文") for r in prof["ranking_rules"])
    assert all(f.get("原文") and f.get("reason") for f in prof["hard_filters"])


# ── 寫入媒合紀錄（#198），可重播 ─────────────────────────────────────

def _sqlite_conn():
    spec = importlib.util.spec_from_file_location("_match_records_fake", HERE / "test_match_records.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SqliteConn()


def test_write_record_and_replay():
    async def go():
        conn = _sqlite_conn()
        await sch.ensure_schema(conn)
        r = eng.match(A, [T_PRIVATE, T_ONE1, T_NONE, T_BI])
        run_id = await eng.write_record(conn, r, tenant="yunlin", initiator="u1")
        viewer = Viewer(user_id="admin", roles=[rec.ROLE_SUPER_ADMIN])
        return r, await rec.load_run(conn, run_id, viewer)

    r, record = asyncio.run(go())
    run = record["run"]
    assert run["ranking_config_version"] == r["profile_id"]
    assert run["meta"]["profile_id"] == r["profile_id"]
    ex = [e for e in record["events"] if e["kind"] == "exclude"]
    assert ex[0]["target"] == "priv" and ex[0]["payload"]["reasons"] == ["非公開"]
    dims = {(j["target"], j["dimension"]) for j in record["judgements"]}
    assert dims == {(t, d) for t in ("one1", "none", "bi") for d in ("need_offer", "b1_b8")}
    assert rec.recorded_ranking(record) == r["order"]
    assert rec.replay_ranking(record) == r["order"] == ["bi", "one1", "none"]
