"""Node command queue — 給「非裝置自身發起」的指令排隊，等 node 主動拉（issue #25 增量 3 / 用例 C）。

情境：LINE/web 也能指揮 device（「在 LINE 跟 Eva 說拍照 → pi4 拍」）。
但 node（pi4）在家裡 NAT 後，ai-eva 不反連；指令不是 node 當下 POST intent 換來的，
就存進這張表，node 靠 /device/poll 主動拉走。

這就是「message queue 一定在後面」——指令的收斂點。用 PG 表：durable、簡單，
而且 edge 只要會 HTTP poll（未來 ESP32 也接得動，不用會 AMQP）。

欄位：
  id           SERIAL 主鍵（也當拉取順序）
  node_id      目標 node
  project      歸屬 project
  command      指令 JSONB，如 {"capability":"camera.capture","params":{"lens":"front"}}
  source       來源 surface（line / web …），給 log / 稽核
  status       pending → delivered
  created_at / delivered_at
"""
from __future__ import annotations

import json
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def ensure_commands_table() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; node command queue disabled")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS node_commands (
                id           BIGSERIAL PRIMARY KEY,
                node_id      TEXT NOT NULL,
                project      TEXT NOT NULL,
                command      JSONB NOT NULL,
                source       TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                delivered_at TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS node_commands_pull_idx "
            "ON node_commands (node_id, status, id)"
        )
        logger.info("node_commands table ready")
    finally:
        await conn.close()


async def enqueue_command(node_id: str, project: str, command: dict, source: str | None = None) -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; cannot enqueue command for %s", node_id)
        return
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO node_commands (node_id, project, command, source) "
            "VALUES ($1, $2, $3::jsonb, $4)",
            node_id, project, json.dumps(command), source,
        )
    finally:
        await conn.close()


async def pull_pending(node_id: str, limit: int = 50) -> list[dict]:
    """Node 來拉：回傳 pending 指令並原子標記 delivered。"""
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            UPDATE node_commands SET status = 'delivered', delivered_at = NOW()
            WHERE id IN (
                SELECT id FROM node_commands
                WHERE node_id = $1 AND status = 'pending'
                ORDER BY id
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            RETURNING command
            """,
            node_id, limit,
        )
        out = []
        for r in rows:
            cmd = r["command"]
            out.append(json.loads(cmd) if isinstance(cmd, str) else cmd)
        return out
    finally:
        await conn.close()
