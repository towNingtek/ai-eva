"""Node registry — PG 表 `nodes`。

node = 提供 **capability** 的 edge 裝置（pi4 / esp32 / browser / 手機 …），歸屬某個 project。
這是 issue #25 的核心：ai-eva 決策中樞要能查「哪個 node 提供哪個 capability」，
而不是把能力寫死在決策邏輯裡（pilot 的 `decide()` 直接回傳 camera.capture 就是要被取代的）。

正規模型：**node 主動 `/device/register` 報到**，自報能力清單 → 寫進這張表。
中樞要派工時查 `nodes_with_capability()`，不反向硬寫。

NAT 備註：`endpoint` 欄位可空。家裡的 node 多半在 NAT 後，中樞**不反連**進去；
連線靠 node 主動拉（intent 當下回 command，或之後長輪詢）。endpoint 只在 node 確實可被回連時才填。

欄位：
  node_id       node 代號（"pi4"），主鍵
  project       擁有這個 node 的 project（對應 projects.id，如 "home"）
  label         人看的名字
  capabilities  能力清單 JSONB，如 ["camera.capture"]
  endpoint      可選回連位址（NAT 後留空）
  metadata      能力細節 JSONB，如 {"lenses": ["front", "rear"]}
  last_seen     每次 register / 報到更新
  created_at    建立時間

用純 asyncpg，跟 projects/registry.py、line.py 同風格。啟動時 ensure_nodes_table() 建表。
node 自己報到，不 seed（避免又變成硬寫）。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def ensure_nodes_table() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; node registry disabled")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                node_id      TEXT PRIMARY KEY,
                project      TEXT NOT NULL,
                label        TEXT,
                capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
                endpoint     TEXT,
                metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_seen    TIMESTAMPTZ,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # project 過濾 + capability 查詢用得上索引
        await conn.execute("CREATE INDEX IF NOT EXISTS nodes_project_idx ON nodes (project)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS nodes_capabilities_idx ON nodes USING GIN (capabilities)"
        )
        logger.info("nodes table ready")
    finally:
        await conn.close()


async def register_node(
    node_id: str,
    project: str,
    capabilities: list[str],
    label: Optional[str] = None,
    endpoint: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Node 報到：upsert 能力 + 更新 last_seen。同一 node_id 重報就覆蓋能力（以最新自報為準）。"""
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; cannot register node %s", node_id)
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, project, label, capabilities, endpoint, metadata, last_seen)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb, NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                project      = EXCLUDED.project,
                label        = COALESCE(EXCLUDED.label, nodes.label),
                capabilities = EXCLUDED.capabilities,
                endpoint     = COALESCE(EXCLUDED.endpoint, nodes.endpoint),
                metadata     = EXCLUDED.metadata,
                last_seen    = NOW()
            """,
            node_id, project, label,
            json.dumps(capabilities), endpoint, json.dumps(metadata or {}),
        )
        logger.info("node registered: %s (project=%s, caps=%s)", node_id, project, capabilities)
    finally:
        await conn.close()


async def touch_node(node_id: str) -> None:
    """輕量心跳：只更新 last_seen（node 報到但能力沒變時用）。"""
    if not _DATABASE_URL:
        return
    conn = await _connect()
    try:
        await conn.execute("UPDATE nodes SET last_seen = NOW() WHERE node_id = $1", node_id)
    finally:
        await conn.close()


async def get_node(node_id: str) -> Optional[dict]:
    if not _DATABASE_URL:
        return None
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT node_id, project, label, capabilities, endpoint, metadata, last_seen "
            "FROM nodes WHERE node_id = $1",
            node_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def list_nodes(project: Optional[str] = None) -> list[dict]:
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        if project is None:
            rows = await conn.fetch(
                "SELECT node_id, project, label, capabilities, last_seen FROM nodes ORDER BY node_id"
            )
        else:
            rows = await conn.fetch(
                "SELECT node_id, project, label, capabilities, last_seen FROM nodes "
                "WHERE project = $1 ORDER BY node_id",
                project,
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def nodes_with_capability(capability: str, project: Optional[str] = None) -> list[dict]:
    """查「誰能做這個 capability」。dispatch 派工的核心查詢。

    project 給定時只查該 project 的 node（scope 隔離）；None 則跨 project（admin / debug 用）。
    """
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        if project is None:
            rows = await conn.fetch(
                "SELECT node_id, project, label, capabilities, endpoint, metadata "
                "FROM nodes WHERE capabilities ? $1 ORDER BY node_id",
                capability,
            )
        else:
            rows = await conn.fetch(
                "SELECT node_id, project, label, capabilities, endpoint, metadata "
                "FROM nodes WHERE capabilities ? $1 AND project = $2 ORDER BY node_id",
                capability, project,
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()
