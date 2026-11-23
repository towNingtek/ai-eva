"""#198 媒合紀錄 matching schema：永久、只新增，限總管理者／系統管理者／hosters[0] 查詢。

測試不需要真的 PostgreSQL：用 sqlite 記憶體 DB 包一個 asyncpg 風格的假連線
（`matching` schema 以 ATTACH 一個名為 matching 的資料庫模擬，PG 專屬語法做最小翻譯）。
若設了 MATCHING_TEST_PG_URL，另跑一次真 PG 的建表與讀寫。
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from pathlib import Path

import pytest

from app.matching import records as rec
from app.matching import schema as sch
from app.matching.records import PermissionDenied, Viewer

ROOT = Path(__file__).resolve().parents[1]


# ── sqlite 版 asyncpg 假連線 ────────────────────────────────────────

class _Row(dict):
    pass


class SqliteConn:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.statements: list[str] = []

    @staticmethod
    def _translate(sql: str) -> str:
        s = re.sub(r"\bBIGSERIAL PRIMARY KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", sql)
        s = re.sub(r"\bJSONB\b", "TEXT", s)
        s = re.sub(r"\bTIMESTAMPTZ\b", "TEXT", s)
        s = s.replace("NOW()", "CURRENT_TIMESTAMP")
        s = s.replace("::jsonb", "")
        s = re.sub(r"REFERENCES matching\.", "REFERENCES ", s)
        # sqlite 的索引名要帶 schema 前綴、表名不帶
        s = re.sub(r"CREATE INDEX IF NOT EXISTS (\w+) ON matching\.(\w+)",
                   r"CREATE INDEX IF NOT EXISTS matching.\1 ON \2", s)
        s = re.sub(r"\$(\d+)", r"?\1", s)
        return s

    def _run(self, sql: str, args):
        self.statements.append(sql)
        if sql.strip().upper().startswith("CREATE SCHEMA IF NOT EXISTS MATCHING"):
            names = [r[1] for r in self.db.execute("PRAGMA database_list")]
            if "matching" not in names:
                self.db.execute("ATTACH DATABASE ':memory:' AS matching")
            return self.db.execute("SELECT 1")
        return self.db.execute(self._translate(sql), args)

    async def execute(self, sql, *args):
        self._run(sql, args)
        return "OK"

    async def fetchrow(self, sql, *args):
        # sqlite < 3.35 不支援 RETURNING：拿掉後以 lastrowid 模擬 `RETURNING id`
        m = re.search(r"\s+RETURNING\s+id\s*$", sql, re.IGNORECASE)
        if m:
            self.statements.append(sql)
            cur = self.db.execute(self._translate(sql[:m.start()]), args)
            return _Row({"id": cur.lastrowid})
        r = self._run(sql, args).fetchone()
        return None if r is None else _Row(dict(r))

    async def fetch(self, sql, *args):
        return [_Row(dict(r)) for r in self._run(sql, args).fetchall()]


def run(coro):
    return asyncio.run(coro)


async def _fresh():
    conn = SqliteConn()
    await sch.ensure_schema(conn)
    return conn


RANK_CFG = {
    "version": "rank-v1",
    "dimensions": ["need_offer", "b1_b8"],
    "verdict_rank": {"match": 0, "partial": 1, "insufficient": 2, "no_match": 3},
}

ADMIN = Viewer(user_id="u-root", roles=["總管理者"])
SYSADMIN = Viewer(user_id="u-sys", roles=["系統管理者"], tenant="other")
OWNER = Viewer(user_id="u-owner", roles=["單位管理者"], tenant="sechome", hosters=["u-owner", "u-co"])
UNIT_ADMIN = Viewer(user_id="u-unit", roles=["單位管理者"], tenant="sechome", hosters=["u-owner", "u-co"])
MEMBER = Viewer(user_id="u-mem", roles=["一般使用者"], tenant="sechome", hosters=["u-owner", "u-co"])
HOSTER1 = Viewer(user_id="u-co", roles=["單位管理者"], tenant="sechome", hosters=["u-owner", "u-co"])


async def _seed(conn):
    rid = await rec.start_run(
        conn, tenant="sechome", initiator="u-mem", project_a="P-A",
        targets=["P-1", "P-2", "P-3"], standard_version="yunlin-v1",
        ranking_config_version="rank-v1", ranking_config=RANK_CFG, model="claude-x",
    )
    for t in ("P-1", "P-2", "P-3"):
        await rec.add_event(conn, rid, "candidate", target=t)
        await rec.add_event(conn, rid, "scan", target=t, payload={"fields": ["philosophy"]})
    await rec.add_judgement(conn, rid, target="P-1", dimension="need_offer", verdict="partial",
                            rationale="A 需要場地、P-1 部分提供", evidence=[{"quote": "提供場地"}])
    await rec.add_judgement(conn, rid, target="P-1", dimension="b1_b8", verdict="match")
    await rec.add_judgement(conn, rid, target="P-2", dimension="need_offer", verdict="match",
                            evidence=[{"quote": "徵求志工", "source": "P-2 philosophy"}])
    await rec.add_judgement(conn, rid, target="P-2", dimension="b1_b8", verdict="partial")
    await rec.add_judgement(conn, rid, target="P-3", dimension="need_offer", verdict="match")
    await rec.add_judgement(conn, rid, target="P-3", dimension="b1_b8", verdict="match")
    await rec.add_answer(conn, rid, target="P-A", question="你們能提供什麼？", answer="導覽人力", writeback=True)
    await rec.add_answer(conn, rid, question="預計何時開始？", answer="明年春天")
    order = rec.replay_ranking(await rec.load_run(conn, rid, ADMIN))
    await rec.record_ranking(conn, rid, order)
    for kind in ("view", "skip", "favorite", "invite", "accept", "reject"):
        await rec.add_event(conn, rid, kind, target="P-3", actor="u-mem")
    await rec.add_event(conn, rid, "status", payload={"from": "running", "to": "done"})
    return rid


# ── (a) 四張表在 matching schema 建立 ───────────────────────────────

class TestSchema:
    def test_four_tables_created_in_matching_schema(self):
        async def go():
            conn = await _fresh()
            names = {r["name"] for r in await conn.fetch(
                "SELECT name FROM matching.sqlite_master WHERE type = 'table'")}
            main = {r["name"] for r in await conn.fetch(
                "SELECT name FROM main.sqlite_master WHERE type = 'table'")}
            return names, main
        names, main = run(go())
        assert {"runs", "judgements", "answers", "events"} <= names
        assert not ({"runs", "judgements", "answers", "events"} & main)  # 不落在預設 schema

    def test_ddl_is_idempotent_and_schema_qualified(self):
        async def go():
            conn = await _fresh()
            await sch.ensure_schema(conn)  # 第二次不炸
        run(go())
        assert sch.DDL[0] == "CREATE SCHEMA IF NOT EXISTS matching"
        for t in sch.TABLES:
            assert any(f"CREATE TABLE IF NOT EXISTS matching.{t} (" in d for d in sch.DDL), t

    def test_ensure_matching_tables_noop_without_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        run(sch.ensure_matching_tables())  # 不連線、不炸


# ── (b) 寫入各類事件後可依 run 讀回 ─────────────────────────────────

class TestWriteAndRead:
    def test_roundtrip_by_run(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            other = await rec.start_run(
                conn, tenant="sechome", initiator="u-x", project_a="P-9", targets=["P-1", "P-2"],
                standard_version="yunlin-v1", ranking_config_version="rank-v1", ranking_config=RANK_CFG)
            await rec.add_event(conn, other, "candidate", target="P-1")
            return await rec.load_run(conn, rid, ADMIN)
        r = run(go())
        run_row = r["run"]
        assert run_row["tenant"] == "sechome" and run_row["initiator"] == "u-mem"
        assert run_row["project_a"] == "P-A" and run_row["targets"] == ["P-1", "P-2", "P-3"]
        assert run_row["standard_version"] == "yunlin-v1"
        assert run_row["ranking_config_version"] == "rank-v1"
        assert run_row["ranking_config"]["verdict_rank"]["match"] == 0
        assert run_row["model"] == "claude-x" and run_row["created_at"]

        assert len(r["judgements"]) == 6
        j = r["judgements"][0]
        assert (j["target"], j["dimension"], j["verdict"]) == ("P-1", "need_offer", "partial")
        assert j["evidence"] == [{"quote": "提供場地"}]

        assert [(a["question"], a["writeback"]) for a in r["answers"]] == [
            ("你們能提供什麼？", True), ("預計何時開始？", False)]

        kinds = [e["kind"] for e in r["events"]]
        for k in ("candidate", "scan", "ranked", "view", "skip", "favorite",
                  "invite", "accept", "reject", "status"):
            assert k in kinds, k
        assert kinds.count("candidate") == 3  # 別的 run 的事件不混進來
        assert r["events"][-1]["payload"] == {"from": "running", "to": "done"}

    def test_exclude_event(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            await rec.add_event(conn, rid, "exclude", target="P-1", payload={"reason": "同單位"})
            return await rec.load_run(conn, rid, ADMIN)
        r = run(go())
        assert r["events"][-1]["kind"] == "exclude"
        assert "P-1" not in rec.replay_ranking(r)

    def test_correction_is_new_event_original_kept(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            before = await rec.load_run(conn, rid, ADMIN)
            jid = before["judgements"][4]["id"]  # P-3 need_offer
            await rec.add_correction(conn, rid, table="judgements", record_id=jid,
                                     reason="誤判", actor="u-root", replacement={"verdict": "no_match"})
            return before, await rec.load_run(conn, rid, ADMIN)
        before, after = run(go())
        assert after["judgements"] == before["judgements"]  # 原紀錄不動
        assert len(after["events"]) == len(before["events"]) + 1
        assert after["events"][-1]["kind"] == "correction"
        assert rec.replay_ranking(before)[0] == "P-3"
        assert rec.replay_ranking(after)[-1] == "P-3"  # 更正後 P-3 掉到最後

    @pytest.mark.parametrize("targets", [["P-1"], ["P-1", "P-2", "P-3", "P-4", "P-5"],
                                         ["P-1", "P-1"], ["P-A", "P-1"]])
    def test_targets_must_be_two_to_four_distinct(self, targets):
        async def go():
            conn = await _fresh()
            await rec.start_run(conn, tenant="t", initiator="u", project_a="P-A", targets=targets,
                                standard_version="s", ranking_config_version="rank-v1",
                                ranking_config=RANK_CFG)
        with pytest.raises(rec.MatchingRecordError):
            run(go())

    def test_unknown_event_kind_and_dimension_rejected(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            with pytest.raises(rec.MatchingRecordError):
                await rec.add_event(conn, rid, "erase")
            with pytest.raises(rec.MatchingRecordError):
                await rec.add_judgement(conn, rid, target="P-1", dimension="b9", verdict="match")
        run(go())


# ── (c) 原始碼不含修改／刪除語句 ────────────────────────────────────

class TestAppendOnly:
    FILES = [ROOT / "app/matching/records.py", ROOT / "app/matching/schema.py"]

    @pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
    def test_source_has_no_update_or_delete(self, path):
        src = path.read_text(encoding="utf-8")
        for word in ("UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER", "UPSERT", "MERGE"):
            assert not re.search(rf"\b{word}\b", src, re.IGNORECASE), f"{path.name} 含 {word}"
        assert not re.search(r"ON\s+CONFLICT", src, re.IGNORECASE)

    def test_no_mutating_functions_exposed(self):
        names = [n for n in dir(rec) if not n.startswith("_")]
        assert not [n for n in names if re.search(r"update|delete|remove|edit|purge|drop", n, re.I)]

    def test_only_insert_and_select_executed(self):
        async def go():
            conn = await _fresh()
            n = len(conn.statements)
            rid = await _seed(conn)
            await rec.load_run(conn, rid, ADMIN)
            await rec.list_runs(conn, "sechome", ADMIN)
            return conn.statements[n:]
        stmts = run(go())
        assert stmts
        for s in stmts:
            assert re.match(r"\s*(INSERT|SELECT)\b", s, re.I), s


# ── (d) 查詢權限 ─────────────────────────────────────────────────────

class TestPermission:
    @pytest.mark.parametrize("viewer", [ADMIN, SYSADMIN, OWNER], ids=["總管理者", "系統管理者", "hosters0"])
    def test_allowed(self, viewer):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            r = await rec.load_run(conn, rid, viewer)
            lst = await rec.list_runs(conn, "sechome", viewer)
            return rid, r, lst
        rid, r, lst = run(go())
        assert r["run"]["id"] == rid and r["judgements"]
        assert [x["id"] for x in lst] == [rid]

    @pytest.mark.parametrize("viewer", [UNIT_ADMIN, MEMBER, HOSTER1, None],
                             ids=["單位管理者", "一般使用者", "hosters1", "未登入"])
    def test_denied(self, viewer):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            with pytest.raises(PermissionDenied):
                await rec.load_run(conn, rid, viewer)
            with pytest.raises(PermissionDenied):
                await rec.list_runs(conn, "sechome", viewer)
        run(go())

    def test_hosters0_of_other_tenant_denied(self):
        other_owner = Viewer(user_id="u-owner", roles=[], tenant="yunlin", hosters=["u-owner"])
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            with pytest.raises(PermissionDenied):
                await rec.load_run(conn, rid, other_owner)
        run(go())

    def test_missing_run_does_not_leak_to_non_admin(self):
        async def go():
            conn = await _fresh()
            await _seed(conn)
            with pytest.raises(PermissionDenied):
                await rec.load_run(conn, 9999, OWNER)
            with pytest.raises(KeyError):
                await rec.load_run(conn, 9999, ADMIN)
        run(go())

    def test_can_query_empty_hosters(self):
        v = Viewer(user_id="u", roles=[], tenant="t", hosters=[])
        assert rec.can_query(v, "t") is False


# ── (e) 以紀錄重播排序得到相同順序 ──────────────────────────────────

class TestReplay:
    def test_replay_matches_recorded_order(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            return await rec.load_run(conn, rid, OWNER)
        r = run(go())
        recorded = rec.recorded_ranking(r)
        assert recorded == ["P-3", "P-2", "P-1"]
        assert rec.replay_ranking(r) == recorded
        assert rec.replay_ranking(r) == rec.replay_ranking(r)

    def test_same_config_version_same_result_across_reads(self):
        async def go():
            conn = await _fresh()
            rid = await _seed(conn)
            a = await rec.load_run(conn, rid, ADMIN)
            b = await rec.load_run(conn, rid, SYSADMIN)
            return a, b
        a, b = run(go())
        assert a["run"]["ranking_config_version"] == b["run"]["ranking_config_version"]
        assert rec.replay_ranking(a) == rec.replay_ranking(b)

    def test_ties_broken_by_target_order(self):
        cfg = {"version": "x"}
        verdicts = {("B", "need_offer"): "match", ("A", "need_offer"): "match"}
        assert rec.rank(["B", "A", "C"], verdicts, cfg) == ["B", "A", "C"]

    def test_config_version_mismatch_rejected(self):
        async def go():
            conn = await _fresh()
            await rec.start_run(conn, tenant="t", initiator="u", project_a="A", targets=["B", "C"],
                                standard_version="s", ranking_config_version="rank-v2",
                                ranking_config=RANK_CFG)
        with pytest.raises(rec.MatchingRecordError):
            run(go())


# ── 選配：真 PostgreSQL ──────────────────────────────────────────────

@pytest.mark.skipif(not os.getenv("MATCHING_TEST_PG_URL"), reason="MATCHING_TEST_PG_URL 未設定")
def test_real_postgres_roundtrip():
    asyncpg = pytest.importorskip("asyncpg")

    async def go():
        conn = await asyncpg.connect(os.environ["MATCHING_TEST_PG_URL"])
        try:
            await sch.ensure_schema(conn)
            await sch.ensure_schema(conn)
            tables = {r["table_name"] for r in await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'matching'")}
            assert set(sch.TABLES) <= tables
            rid = await _seed(conn)
            r = await rec.load_run(conn, rid, OWNER)
            assert r["run"]["targets"] == ["P-1", "P-2", "P-3"]
            assert rec.replay_ranking(r) == rec.recorded_ranking(r)
        finally:
            await conn.close()
    run(go())
