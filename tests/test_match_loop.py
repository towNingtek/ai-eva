"""#183 指定媒合：兩案 B1–B8 → 關係與狀態，資料不足時接多輪狀態機追問。題目來自 YAML，不打 AI。"""
import itertools

import yaml

from app.matching import pair
from app.matching.pair import CLARIFY_FIRST, ELIGIBLE, EXPLORE, RECOMMEND

STD = yaml.safe_load(pair.STANDARD.read_text(encoding="utf-8"))
CQ = STD["clarify_questions"]
NAMES = {"a": "甲社區", "b": "乙社區"}

# 固定兩案：B3 甲需要／乙提供（互補），B4 兩邊都 NEED（第三方），B1 兩邊都 OFFER（交流）
A = {"capabilities": {"B1": {"direction": "OFFER"}, "B3": {"direction": "NEED"}, "B4": {"direction": "NEED"}}}
B = {"capabilities": {"B1": {"direction": "OFFER"}, "B3": {"direction": "OFFER"}, "B4": {"direction": "NEED"}}}


# (a) 狀態轉換
def test_complement_unfilled_is_clarify_first_then_explore():
    assert pair.match_status("a", A, "b", B) == CLARIFY_FIRST
    ans = {"a:B3:用途": "辦農事體驗營"}
    assert pair.match_status("a", A, "b", B, ans) == CLARIFY_FIRST     # 只補需要方「用途」
    ans["b:B3:可提供形式"] = "帶團"
    assert pair.match_status("a", A, "b", B, ans) == EXPLORE           # 再補能提供方「可提供形式」


def test_offer_form_alone_or_wrong_side_does_not_explore():
    assert pair.match_status("a", A, "b", B, {"b:B3:可提供形式": "帶團"}) == CLARIFY_FIRST
    # 欄位補在錯的一方不算
    assert pair.match_status("a", A, "b", B, {"b:B3:用途": "x", "a:B3:可提供形式": "y"}) == CLARIFY_FIRST


def test_unknown_answer_is_recorded_but_not_filled():
    ans = {"a:B3:用途": "還不知道", "b:B3:可提供形式": "帶團"}
    assert pair.match_status("a", A, "b", B, ans) == CLARIFY_FIRST
    q = pair.next_question("a", A, "b", B, ans, names=NAMES)
    assert q["id"] != "a:B3:用途"                                      # 記下了，不再問


def test_peer_only_is_explore_and_none_is_eligible():
    assert pair.match_status("a", {"B2": "OFFER"}, "b", {"B2": "OFFER"}) == EXPLORE
    assert pair.match_status("a", {"B2": "NEED"}, "b", {"B2": "NEED"}) == ELIGIBLE
    assert pair.match_status("a", {}, "b", {"B5": "OFFER"}) == ELIGIBLE


# (b) BOTH 兩邊都算
def test_both_counts_both_ways():
    comp = pair.complement_pairs("a", {"B2": "BOTH"}, "b", {"B2": "BOTH"})
    assert set(comp) == {("a", "b", "B2"), ("b", "a", "B2")}
    assert pair.complement_pairs("a", {"B2": "BOTH"}, "b", {"B2": "OFFER"}) == [("a", "b", "B2")]
    assert pair.complement_pairs("a", {"B2": "NEED"}, "b", {"B2": "BOTH"}) == [("a", "b", "B2")]
    # BOTH × OFFER 是互補，不是交流
    rel = pair.relations("a", {"B2": "BOTH"}, "b", {"B2": "OFFER"})
    assert rel[pair.REL_PEER] == [] and rel[pair.REL_COMPLEMENT]
    assert pair.match_status("a", {"B2": "BOTH"}, "b", {"B2": "OFFER"}) == CLARIFY_FIRST


def test_both_either_direction_filled_explores():
    a, b = {"B2": "BOTH"}, {"B2": "BOTH"}
    assert pair.match_status("a", a, "b", b, {"b:B2:用途": "u", "a:B2:可提供形式": "f"}) == EXPLORE


# (c) 兩邊都 NEED → 共同尋找第三方，不在互補候選
def test_both_need_is_third_party_not_complement():
    rel = pair.relations("a", A, "b", B)
    assert "B4" in rel[pair.REL_THIRD_PARTY]
    assert all(c["key"] != "B4" for c in rel[pair.REL_COMPLEMENT])
    assert rel[pair.REL_COMPLEMENT] == [{"need": "a", "offer": "b", "key": "B3"}]
    assert rel[pair.REL_PEER] == ["B1"]


# (d) 永遠不出 RECOMMEND
def test_never_recommend():
    dirs = ["NEED", "OFFER", "BOTH", "none"]
    full = {f"{p}:{k}:{f}": "有" for p in "ab" for k in pair.B_KEYS
            for side in ("NEED", "OFFER") for f in CQ[side]}
    for da, db in itertools.product(dirs, repeat=2):
        a = {k: da for k in pair.B_KEYS[:2]} | {"B5": db}
        b = {k: db for k in pair.B_KEYS[:2]} | {"B5": da}
        for ans in ({}, full):
            out = pair.analyze_pair("a", a, "b", b, ans)
            assert out["status"] != RECOMMEND
            assert out["status"] in (CLARIFY_FIRST, EXPLORE, ELIGIBLE)


# (e) 題目順序與來源
def test_first_need_use_then_offer_form_from_yaml():
    q1 = pair.next_question("a", A, "b", B, names=NAMES)
    assert (q1["pid"], q1["side"], q1["field"], q1["minimum"]) == ("a", "NEED", "用途", True)
    assert q1["text"] == CQ["NEED"]["用途"].format(need="甲社區", offer="乙社區", b="服務與體驗")
    q2 = pair.next_question("a", A, "b", B, {q1["id"]: "辦體驗營"}, names=NAMES)
    assert (q2["pid"], q2["side"], q2["field"], q2["minimum"]) == ("b", "OFFER", "可提供形式", True)
    assert q2["text"] == CQ["OFFER"]["可提供形式"].format(need="甲社區", offer="乙社區", b="服務與體驗")
    # 第三題起才是其他欄位
    q3 = pair.next_question("a", A, "b", B, {q1["id"]: "x", q2["id"]: "y"}, names=NAMES)
    assert q3["minimum"] is False and q3["field"] in set(CQ["NEED"]) | set(CQ["OFFER"])


def test_skip_moves_on_and_questions_end():
    q1 = pair.next_question("a", A, "b", B, asked=["a:B3:用途"], names=NAMES)
    assert q1["id"] == "b:B3:可提供形式"
    all_ids = [f"{p}:B3:{f}" for p, side in (("a", "NEED"), ("b", "OFFER")) for f in CQ[side]]
    assert pair.next_question("a", A, "b", B, asked=all_ids) is None
    assert pair.next_question("a", {"B1": "OFFER"}, "b", {"B1": "OFFER"}) is None


def test_questions_follow_yaml_strings(tmp_path):
    std = yaml.safe_load(pair.STANDARD.read_text(encoding="utf-8"))
    std["clarify_questions"]["NEED"]["用途"] = "TEST {need}/{offer}/{b}"
    q = pair.next_question("a", A, "b", B, names=NAMES, std=std)
    assert q["text"] == "TEST 甲社區/乙社區/服務與體驗"


def test_analyze_pair_with_capability_output_shape():
    out = pair.analyze_pair("a", A, "b", B, names=NAMES)
    assert out["status"] == CLARIFY_FIRST and out["status_text"] == "先補資料"
    assert out["next_question"]["field"] == "用途"
