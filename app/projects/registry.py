"""Project registry — PG 表 `projects`。

project = 擁有 {apps + nodes + profile} 的範圍（虎科 / 縣府 / 機器人部門 / 俊毓個人 …），
不是登入帳號。identity（Chainlit password / CF Access email / LINE userId）另外映射到 project。

這層只管 project 的「身分 + profile」：
  - id        project 代號（app meta 的 project 欄位指這個）
  - label     人看的名字
  - line_recipient  該 project 預設 push 的 LINE userId
  - contacts  聯絡人 map，e.g. {"chika": "Uxxxx"}（主動通報用）
  - metadata  其餘擴充

app↔project 的歸屬在 app meta（project 欄位）+ _registry；這裡不存 app/node。
node registry 之後跟機器人部門合寫（capability provider）。

用純 asyncpg，跟 line.py / line_session.py 同風格。啟動時 ensure_projects_table() 建表 + seed。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")

CORE_PROJECT = "core"
DEFAULT_PROJECT = "yillkid"


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


# 啟動 seed：平台內建 + 俊毓個人。line_recipient 之後可在 DB 改。
_SEED = [
    {"id": CORE_PROJECT, "label": "平台內建", "line_recipient": None, "contacts": {}},
    {
        "id": DEFAULT_PROJECT,
        "label": "俊毓個人",
        "line_recipient": os.getenv("DEFAULT_LINE_RECIPIENT") or None,
        "contacts": {},
    },
    # CMS「AI 秘書」遷移專案（#50）。CMS issuer tplanet-cms 映到這個 project。
    # copilot 是互動式（web），不走 LINE push，line_recipient 留空。
    {"id": "sechome", "label": "Sechome（CMS AI 秘書）", "line_recipient": None, "contacts": {}},
]


async def ensure_projects_table() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; project registry disabled")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id             TEXT PRIMARY KEY,
                label          TEXT NOT NULL,
                line_recipient TEXT,
                contacts       JSONB DEFAULT '{}'::jsonb,
                metadata       JSONB DEFAULT '{}'::jsonb,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # seed（已存在就不覆蓋，避免蓋掉手動改過的 profile）
        for p in _SEED:
            await conn.execute(
                """
                INSERT INTO projects (id, label, line_recipient, contacts)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                p["id"], p["label"], p["line_recipient"], json.dumps(p["contacts"]),
            )
        logger.info("projects table ready (seeded %s)", [p["id"] for p in _SEED])
    finally:
        await conn.close()


async def get_project(project_id: str) -> Optional[dict]:
    if not _DATABASE_URL:
        return None
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT id, label, line_recipient, contacts, metadata FROM projects WHERE id = $1",
            project_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def list_projects() -> list[dict]:
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        rows = await conn.fetch("SELECT id, label, line_recipient FROM projects ORDER BY id")
        return [dict(r) for r in rows]
    finally:
        await conn.close()
