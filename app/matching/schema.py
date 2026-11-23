"""媒合紀錄 `matching` schema（#198；MVP 原則 6「全程保留媒合過程紀錄」，#185 定案）。

四張表，全部在 AI-Eva DB 的 `matching` schema（與 chainlit、法規分開）：

  matching.runs        一次媒合：發起人、租戶、A 與 2–4 個對象、標準版本、
                       排序設定版本（＋設定快照，供重播）、模型、時間
  matching.judgements  每案兩維判斷（need_offer / b1_b8）與原文依據
  matching.answers     補問、回答、是否寫回 philosophy
  matching.events      候選／掃描／排除、互動（看／略過／收藏／邀請／接受／拒絕）、
                       狀態變化、更正

## 永久、只新增

這份 DDL 與 records.py 只有 CREATE 與 INSERT／SELECT。沒有修改或刪除的程式路徑，
外鍵也不帶任何連帶動作；要更正一筆紀錄就新增一筆 `correction` 事件指向原紀錄。
tests/test_match_records.py 會掃描這兩個檔的原始碼確保如此。

開機時 `CREATE SCHEMA/TABLE IF NOT EXISTS`，比照 regulations/registry.py，純 asyncpg。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SCHEMA = "matching"
TABLES = ("runs", "judgements", "answers", "events")

DDL: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS matching",
    """
    CREATE TABLE IF NOT EXISTS matching.runs (
        id                      BIGSERIAL PRIMARY KEY,
        tenant                  TEXT NOT NULL,
        initiator               TEXT NOT NULL,
        project_a               TEXT NOT NULL,
        targets                 JSONB NOT NULL,
        standard_version        TEXT NOT NULL,
        ranking_config_version  TEXT NOT NULL,
        ranking_config          JSONB NOT NULL,
        model                   TEXT NOT NULL DEFAULT '',
        meta                    JSONB,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matching.judgements (
        id          BIGSERIAL PRIMARY KEY,
        run_id      BIGINT NOT NULL REFERENCES matching.runs(id),
        target      TEXT NOT NULL,
        dimension   TEXT NOT NULL,
        verdict     TEXT NOT NULL,
        rationale   TEXT NOT NULL DEFAULT '',
        evidence    JSONB,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matching.answers (
        id          BIGSERIAL PRIMARY KEY,
        run_id      BIGINT NOT NULL REFERENCES matching.runs(id),
        target      TEXT,
        question    TEXT NOT NULL,
        answer      TEXT NOT NULL DEFAULT '',
        writeback   BOOLEAN NOT NULL DEFAULT FALSE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matching.events (
        id          BIGSERIAL PRIMARY KEY,
        run_id      BIGINT NOT NULL REFERENCES matching.runs(id),
        kind        TEXT NOT NULL,
        target      TEXT,
        actor       TEXT,
        payload     JSONB,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS matching_runs_tenant_idx ON matching.runs (tenant, created_at)",
    "CREATE INDEX IF NOT EXISTS matching_judgements_run_idx ON matching.judgements (run_id)",
    "CREATE INDEX IF NOT EXISTS matching_answers_run_idx ON matching.answers (run_id)",
    "CREATE INDEX IF NOT EXISTS matching_events_run_idx ON matching.events (run_id)",
)


async def ensure_schema(conn) -> None:
    """在給定連線上建 schema 與四張表（冪等）。conn 為 asyncpg 風格（有 execute）。"""
    for stmt in DDL:
        await conn.execute(stmt)


def _pg_url() -> str:
    return os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")


async def ensure_matching_tables() -> None:
    """開機呼叫：沒有 DATABASE_URL 就停用（比照 regulations registry）。"""
    if not os.getenv("DATABASE_URL", ""):
        logger.warning("DATABASE_URL not set; matching records disabled")
        return
    import asyncpg

    conn = await asyncpg.connect(_pg_url())
    try:
        await ensure_schema(conn)
    finally:
        await conn.close()
