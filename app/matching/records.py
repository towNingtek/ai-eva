"""媒合紀錄的寫入、查詢與排序重播（#198）。

- 寫入：`start_run` / `add_judgement` / `add_answer` / `add_event` / `add_correction`
  —— 全部是 INSERT。沒有修改或刪除的函式；更正以新增一筆 `correction` 事件表示。
- 查詢：`load_run` / `list_runs` 一律先過 `can_query`：只有 CMS 角色「總管理者」
  「系統管理者」，或該租戶 hosters[0]（站台擁有者）可查，其他角色一律拒絕。
- 重播：`rank` 是純函式；`replay_ranking` 用同一份紀錄（判斷 + run 上存的排序設定快照）
  重算一次排序，同排序設定版本必得同結果。

conn 為 asyncpg 風格連線（execute / fetchrow / fetch，參數用 $1…）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

# ── 常數 ─────────────────────────────────────────────────────────────

ROLE_SUPER_ADMIN = "總管理者"
ROLE_SYSTEM_ADMIN = "系統管理者"
ADMIN_ROLES = frozenset({ROLE_SUPER_ADMIN, ROLE_SYSTEM_ADMIN})

DIMENSIONS = ("need_offer", "b1_b8")

MIN_TARGETS = 2
MAX_TARGETS = 4

# 事件種類：候選／掃描／排除、互動、狀態變化、排序結果、更正
EVENT_KINDS = frozenset({
    "candidate", "scan", "exclude",
    "view", "skip", "favorite", "invite", "accept", "reject",
    "status",
    "ranked",
    "correction",
})


class MatchingRecordError(ValueError):
    """寫入參數不合法。"""


class PermissionDenied(PermissionError):
    """查詢者沒有權限讀媒合紀錄。"""


# ── 權限 ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Viewer:
    """查詢者身分。

    user_id  CMS 使用者識別（與 hosters 裡的值同一種識別）
    roles    CMS 角色名稱（例：總管理者、系統管理者、單位管理者、一般使用者）
    tenant   查詢者所在租戶（project）
    hosters  該租戶的 hosters 清單（CMS 保證 hosters[0] 為站台擁有者且不可移除）
    """
    user_id: str
    roles: Sequence[str] = field(default_factory=tuple)
    tenant: Optional[str] = None
    hosters: Sequence[str] = field(default_factory=tuple)


def can_query(viewer: Optional[Viewer], tenant: Optional[str]) -> bool:
    """viewer 能否查 tenant 的媒合紀錄。tenant=None 表示跨租戶（只有管理角色可以）。"""
    if viewer is None:
        return False
    if any(r in ADMIN_ROLES for r in (viewer.roles or ())):
        return True
    if tenant is None or viewer.tenant != tenant:
        return False
    hosters = list(viewer.hosters or ())
    if not hosters or not viewer.user_id:
        return False
    return str(hosters[0]) == str(viewer.user_id)


def _require(viewer: Optional[Viewer], tenant: Optional[str]) -> None:
    if not can_query(viewer, tenant):
        raise PermissionDenied("媒合紀錄僅限總管理者、系統管理者或該租戶 hosters[0] 查詢")


# ── JSON 小工具 ──────────────────────────────────────────────────────

def _dump(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _load(v: Any) -> Any:
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _row(r: Any, json_cols: Iterable[str] = ()) -> dict:
    d = dict(r)
    for c in json_cols:
        if c in d:
            d[c] = _load(d[c])
    if "created_at" in d and d["created_at"] is not None and not isinstance(d["created_at"], str):
        d["created_at"] = d["created_at"].isoformat()
    return d


# ── 寫入（只新增） ───────────────────────────────────────────────────

async def start_run(
    conn,
    *,
    tenant: str,
    initiator: str,
    project_a: str,
    targets: Sequence[str],
    standard_version: str,
    ranking_config_version: str,
    ranking_config: dict,
    model: str = "",
    meta: Optional[dict] = None,
) -> int:
    """新增一次媒合，回傳 run id。對象須 2–4 個、不得重複、不得含 A。"""
    targets = [str(t) for t in targets]
    if not (MIN_TARGETS <= len(targets) <= MAX_TARGETS):
        raise MatchingRecordError(f"對象需 {MIN_TARGETS}–{MAX_TARGETS} 個，收到 {len(targets)} 個")
    if len(set(targets)) != len(targets) or str(project_a) in targets:
        raise MatchingRecordError("對象不得重複、不得包含 A 本身")
    if not tenant or not initiator or not project_a:
        raise MatchingRecordError("tenant / initiator / project_a 必填")
    if not standard_version or not ranking_config_version:
        raise MatchingRecordError("standard_version / ranking_config_version 必填")
    cfg = dict(ranking_config or {})
    cfg.setdefault("version", ranking_config_version)
    if cfg["version"] != ranking_config_version:
        raise MatchingRecordError("ranking_config.version 與 ranking_config_version 不一致")
    row = await conn.fetchrow(
        "INSERT INTO matching.runs "
        "(tenant, initiator, project_a, targets, standard_version, "
        " ranking_config_version, ranking_config, model, meta) "
        "VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8, $9::jsonb) RETURNING id",
        tenant, initiator, str(project_a), _dump(targets), standard_version,
        ranking_config_version, _dump(cfg), model or "", _dump(meta),
    )
    return int(row["id"])


async def add_judgement(
    conn,
    run_id: int,
    *,
    target: str,
    dimension: str,
    verdict: str,
    rationale: str = "",
    evidence: Any = None,
) -> int:
    """新增一筆判斷（dimension ∈ need_offer / b1_b8；evidence＝原文依據）。"""
    if dimension not in DIMENSIONS:
        raise MatchingRecordError(f"未知維度：{dimension}")
    if not verdict:
        raise MatchingRecordError("verdict 必填")
    row = await conn.fetchrow(
        "INSERT INTO matching.judgements (run_id, target, dimension, verdict, rationale, evidence) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING id",
        int(run_id), str(target), dimension, verdict, rationale or "", _dump(evidence),
    )
    return int(row["id"])


async def add_answer(
    conn,
    run_id: int,
    *,
    question: str,
    answer: str = "",
    target: Optional[str] = None,
    writeback: bool = False,
) -> int:
    """新增一筆補問／回答；writeback＝使用者是否同意寫回 philosophy。"""
    if not question:
        raise MatchingRecordError("question 必填")
    row = await conn.fetchrow(
        "INSERT INTO matching.answers (run_id, target, question, answer, writeback) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        int(run_id), None if target is None else str(target), question, answer or "", bool(writeback),
    )
    return int(row["id"])


async def add_event(
    conn,
    run_id: int,
    kind: str,
    *,
    target: Optional[str] = None,
    actor: Optional[str] = None,
    payload: Optional[dict] = None,
) -> int:
    """新增一筆事件（候選／掃描／排除、互動、狀態變化、排序結果、更正）。"""
    if kind not in EVENT_KINDS:
        raise MatchingRecordError(f"未知事件種類：{kind}")
    row = await conn.fetchrow(
        "INSERT INTO matching.events (run_id, kind, target, actor, payload) "
        "VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id",
        int(run_id), kind, None if target is None else str(target), actor, _dump(payload),
    )
    return int(row["id"])


async def add_correction(
    conn,
    run_id: int,
    *,
    table: str,
    record_id: int,
    reason: str,
    actor: Optional[str] = None,
    replacement: Any = None,
) -> int:
    """更正：不動原紀錄，新增一筆 correction 事件指向它。"""
    if table not in ("runs", "judgements", "answers", "events"):
        raise MatchingRecordError(f"未知表：{table}")
    return await add_event(
        conn, run_id, "correction", actor=actor,
        payload={"table": table, "record_id": int(record_id), "reason": reason,
                 "replacement": replacement},
    )


async def record_ranking(conn, run_id: int, order: Sequence[str], *, actor: Optional[str] = None) -> int:
    """把當次排序結果記成 ranked 事件，供日後重播比對。"""
    return await add_event(conn, run_id, "ranked", actor=actor, payload={"order": [str(t) for t in order]})


# ── 查詢（須權限） ───────────────────────────────────────────────────

_RUN_JSON = ("targets", "ranking_config", "meta")


async def _fetch_run(conn, run_id: int) -> Optional[dict]:
    r = await conn.fetchrow("SELECT * FROM matching.runs WHERE id = $1", int(run_id))
    return None if r is None else _row(r, _RUN_JSON)


async def load_run(conn, run_id: int, viewer: Optional[Viewer]) -> dict:
    """依 run 讀回完整紀錄（run + judgements + answers + events，各依 id 排序）。

    無權限 → PermissionDenied；run 不存在 → 管理角色得 KeyError，其他人一律
    PermissionDenied（無法用錯誤訊息探測別租戶 run 是否存在）。
    """
    if viewer is None:
        _require(viewer, None)
    run = await _fetch_run(conn, run_id)
    if run is None:
        _require(viewer, None)  # 只有管理角色看得到「不存在」
        raise KeyError(run_id)
    _require(viewer, run["tenant"])
    rid = int(run_id)
    judgements = [
        _row(r, ("evidence",)) for r in await conn.fetch(
            "SELECT * FROM matching.judgements WHERE run_id = $1 ORDER BY id", rid)
    ]
    answers = [
        _row(r) for r in await conn.fetch(
            "SELECT * FROM matching.answers WHERE run_id = $1 ORDER BY id", rid)
    ]
    for a in answers:
        a["writeback"] = bool(a.get("writeback"))
    events = [
        _row(r, ("payload",)) for r in await conn.fetch(
            "SELECT * FROM matching.events WHERE run_id = $1 ORDER BY id", rid)
    ]
    return {"run": run, "judgements": judgements, "answers": answers, "events": events}


async def list_runs(conn, tenant: str, viewer: Optional[Viewer], *, limit: int = 100) -> list[dict]:
    """列出某租戶的 run（新到舊）。"""
    _require(viewer, tenant)
    rows = await conn.fetch(
        "SELECT * FROM matching.runs WHERE tenant = $1 ORDER BY id DESC LIMIT $2",
        tenant, int(limit),
    )
    return [_row(r, _RUN_JSON) for r in rows]


# ── 排序與重播 ───────────────────────────────────────────────────────

DEFAULT_VERDICT_RANK = {"match": 0, "partial": 1, "insufficient": 2, "no_match": 3}


def _effective(record: dict) -> tuple[dict, set]:
    """套用 correction 事件後的有效判斷 {(target, dim): verdict} 與被排除對象。"""
    judgements = {j["id"]: dict(j) for j in record.get("judgements", [])}
    excluded: set = set()
    events = record.get("events", [])
    for e in events:
        if e.get("kind") != "correction":
            continue
        p = e.get("payload") or {}
        if p.get("table") == "judgements" and p.get("record_id") in judgements:
            rep = p.get("replacement")
            if isinstance(rep, dict) and rep.get("verdict"):
                judgements[p["record_id"]]["verdict"] = rep["verdict"]
            elif rep is None:
                judgements[p["record_id"]]["_void"] = True
    voided_events = {
        (e.get("payload") or {}).get("record_id")
        for e in events
        if e.get("kind") == "correction" and (e.get("payload") or {}).get("table") == "events"
    }
    for e in events:
        if e.get("kind") == "exclude" and e.get("id") not in voided_events and e.get("target"):
            excluded.add(str(e["target"]))
    latest: dict = {}
    for jid in sorted(judgements):
        j = judgements[jid]
        if j.get("_void"):
            continue
        latest[(str(j["target"]), j["dimension"])] = j["verdict"]
    return latest, excluded


def rank(targets: Sequence[str], verdicts: dict, config: dict, excluded: Iterable[str] = ()) -> list[str]:
    """純函式排序。

    config:
      dimensions    依序比較的維度（預設 need_offer, b1_b8）
      verdict_rank  verdict → 名次（小者在前；未知或缺判斷排最後）
    同分依 run 上 targets 原順序，確保結果唯一、可重播。
    """
    dims = list(config.get("dimensions") or DIMENSIONS)
    vrank = dict(config.get("verdict_rank") or DEFAULT_VERDICT_RANK)
    worst = (max(vrank.values()) + 1) if vrank else 0
    excl = {str(t) for t in excluded}
    pool = [(i, str(t)) for i, t in enumerate(targets) if str(t) not in excl]

    def key(item):
        i, t = item
        return tuple(vrank.get(verdicts.get((t, d)), worst) for d in dims) + (i,)

    return [t for _, t in sorted(pool, key=key)]


def replay_ranking(record: dict) -> list[str]:
    """用 load_run 讀回的紀錄重算排序（用 run 上存的排序設定快照）。"""
    run = record["run"]
    verdicts, excluded = _effective(record)
    return rank(run["targets"], verdicts, run["ranking_config"], excluded)


def recorded_ranking(record: dict) -> Optional[list[str]]:
    """紀錄裡最後一次 ranked 事件的順序（沒有則 None）。"""
    order = None
    for e in record.get("events", []):
        if e.get("kind") == "ranked":
            order = list((e.get("payload") or {}).get("order") or [])
    return order
