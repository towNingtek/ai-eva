"""法規語料 registry — PG 表 `regulations` / `regulation_articles` / `negative_list`。

法規檢核（#111 / #112）的**語料層**。這是 domain 模組不是 app：擁有表、開機建表，
跟 app/nodes/ 與 app/projects/ 同層。app/apps/{knowledge_base,regulation_check}
只是薄薄的 Chainlit 介面，邏輯全在這裡。

## 為什麼沒有向量欄位

法規檢核**不走 similarity 檢索**。理由：判定的 recall 是驗收 KPI，而 top-k 檢索
天生會靜默漏條文；且計畫書用工程語言（「邊坡闢建生態步道」）、法條用類型化法律
語言（「於山坡地從事開發、經營或使用」），embedding 相似度低，正是向量檢索最弱
的場景。這裡的「檢索」= `scope_negative_list()` 的一條確定性 SQL（按類別過濾），
同一份計畫書跑幾次都撈到同一批條目 —— 覆蓋率可數、可宣告、可斷言。

未來若要做 chatroom 單點問答（「水保法對坡度怎麼規定」），那是對稱檢索、漏一條不
致命，屆時再 `CREATE EXTENSION vector` + `ALTER TABLE regulation_articles ADD
embedding vector(...)`。這輪不建空欄位。

## status 語意（治理閘門）

  active       進判定分母。**只有 corpus/MANIFEST.yaml 裡、sha256 對得上的才會拿到**
  pending      runtime 上傳的新法規預設值；不進判定，要管理者審核才 active
  no_fulltext  Drive 有檔但內容是「查不到全文」的說明書（政策方針 / 雲林審查小組
               設置要點）；不進判定，改在報告「需補語料」區塊列出
  draft        尚未生效的草案（國土計畫土地使用管制規則）。**不進判定** ——
               拿草案判「違規風險」在合約上站不住，甲方一句「這不是法」就全數作廢。
               報告會在「未評估」區塊講明有收錄但未納入。
  superseded   被新版取代

語料釘在 repo（corpus/），開機從 JSON 灌表；不從 Google Drive 動態拉 —— 語料庫是
判定的分母，被偷換一部假法規就會憑空長出違規，且無從察覺。

用純 asyncpg，跟 projects/registry.py、nodes/registry.py 同風格。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "")

CORPUS_DIR = Path(__file__).parent / "corpus"
MANIFEST = CORPUS_DIR / "MANIFEST.yaml"
ARTICLES_JSON = CORPUS_DIR / "articles.json"
NEGATIVE_JSON = CORPUS_DIR / "negative_list.json"

# 類別 → 檢核時一併納入的相鄰類別（R0 定案：主類 + 相鄰白名單）
# 農再計畫類法規幾乎無實質禁令、多指向母法，牙齒集中在跨領域土地/開發/環評/水保群，
# 所以農村再生一定要帶上鄉村地區，否則撈不到真正會踩的條文。
SCOPE_WHITELIST: dict[str, list[str]] = {
    "農村再生": ["農村再生", "鄉村地區"],
    "鄉村地區": ["鄉村地區"],
    "都市地區": ["都市地區", "鄉村地區"],
}

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending"
STATUS_NO_FULLTEXT = "no_fulltext"
STATUS_DRAFT = "draft"


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def ensure_regulations_tables() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; regulations registry disabled")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regulations (
                id           SERIAL PRIMARY KEY,
                name         TEXT NOT NULL,
                category     TEXT NOT NULL,
                version      TEXT NOT NULL DEFAULT '',
                source_file  TEXT,
                sha256       TEXT,
                chars        INTEGER NOT NULL DEFAULT 0,
                status       TEXT NOT NULL DEFAULT 'pending',
                origin       TEXT NOT NULL DEFAULT 'upload',
                uploaded_by  TEXT,
                reviewed_by  TEXT,
                activated_at TIMESTAMPTZ,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (name, version)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regulation_articles (
                id            SERIAL PRIMARY KEY,
                regulation_id INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
                seq           INTEGER NOT NULL DEFAULT 0,
                article_no    TEXT NOT NULL,
                chapter       TEXT,
                text          TEXT NOT NULL
            )
            """
        )
        # negative_list = 判定用的管制條目（ingest 從全文抽出）。
        # situation 而非 trigger：TRIGGER 是 PG 保留字，欄位名避開免得每次都要 quote。
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS negative_list (
                id             SERIAL PRIMARY KEY,
                regulation_id  INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
                article_no     TEXT NOT NULL DEFAULT '',
                law_domain     TEXT NOT NULL,
                tag            TEXT NOT NULL,
                situation      TEXT NOT NULL,
                requirement    TEXT,
                penalty        TEXT,
                corpus_version TEXT,
                extracted_by   TEXT,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS regulations_scope_idx ON regulations (category, status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS reg_articles_reg_idx ON regulation_articles (regulation_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS negative_list_reg_idx ON negative_list (regulation_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS negative_list_domain_idx ON negative_list (law_domain)"
        )
        logger.info("regulations tables ready")
    finally:
        await conn.close()


# ── corpus → DB（開機 seed）──────────────────────────────────
def _load_manifest() -> dict:
    import yaml
    if not MANIFEST.exists():
        return {}
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}


def verify_corpus() -> tuple[list[dict], list[str]]:
    """對 MANIFEST 逐檔驗 sha256。回 (通過的條目, 問題訊息)。

    對不上就不給 active —— 語料庫是判定的分母，寧可少一部也不能載入被動過的檔案。
    """
    man = _load_manifest()
    ok: list[dict] = []
    problems: list[str] = []
    for entry in man.get("regulations") or []:
        pdf = CORPUS_DIR / "raw" / entry["file"]
        if not pdf.exists():
            problems.append(f"{entry['name']}：PDF 不存在（{entry['file']}）")
            continue
        actual = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if actual != entry.get("sha256"):
            problems.append(f"{entry['name']}：sha256 不符，拒絕載入")
            continue
        ok.append(entry)
    return ok, problems


async def seed_from_corpus() -> dict:
    """開機把 repo 內的語料灌進表（idempotent）。

    只讀 corpus/ 的 JSON，不呼叫 LLM、不連外網 —— 抽管制條目是建置時的事
    （`python -m app.regulations.ingest`），產物進版控。
    """
    if not _DATABASE_URL:
        return {"seeded": 0, "problems": ["DATABASE_URL not set"]}
    if not ARTICLES_JSON.exists() or not NEGATIVE_JSON.exists():
        return {"seeded": 0, "problems": ["corpus 尚未 ingest（缺 articles.json / negative_list.json）"]}

    entries, problems = verify_corpus()
    man = _load_manifest()
    corpus_version = man.get("corpus_version", "v1")
    articles = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    negatives = json.loads(NEGATIVE_JSON.read_text(encoding="utf-8"))

    conn = await _connect()
    seeded = 0
    try:
        for entry in entries:
            name = entry["name"]
            # 不進判定分母、但要留在清單裡讓報告能誠實交代的兩種：
            #   no_fulltext = 有檔沒內容；draft = 有內容還沒生效
            if entry.get("no_fulltext"):
                status = STATUS_NO_FULLTEXT
            elif entry.get("draft"):
                status = STATUS_DRAFT
            else:
                status = STATUS_ACTIVE
            reg_id = await conn.fetchval(
                """
                INSERT INTO regulations
                    (name, category, version, source_file, sha256, chars, status, origin, activated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,'manifest',NOW())
                ON CONFLICT (name, version) DO UPDATE SET
                    category=EXCLUDED.category, sha256=EXCLUDED.sha256,
                    chars=EXCLUDED.chars, status=EXCLUDED.status, origin='manifest'
                RETURNING id
                """,
                name, entry["category"], entry.get("version") or "",
                entry["file"], entry["sha256"], entry.get("chars") or 0, status,
            )
            # 條文 / 管制條目每次重灌（以 repo 為單一真相）
            await conn.execute("DELETE FROM regulation_articles WHERE regulation_id=$1", reg_id)
            rows = [
                (reg_id, a.get("seq", i), a["article_no"], a.get("chapter"), a["text"])
                for i, a in enumerate(articles.get(name) or [])
            ]
            if rows:
                await conn.copy_records_to_table(
                    "regulation_articles",
                    records=rows,
                    columns=["regulation_id", "seq", "article_no", "chapter", "text"],
                )
            await conn.execute("DELETE FROM negative_list WHERE regulation_id=$1", reg_id)
            nrows = [
                (reg_id, n.get("article_no", ""), n["law_domain"], n["tag"], n["situation"],
                 n.get("requirement"), n.get("penalty"), corpus_version, n.get("extracted_by"))
                for n in (negatives.get(name) or [])
            ]
            if nrows:
                await conn.copy_records_to_table(
                    "negative_list",
                    records=nrows,
                    columns=["regulation_id", "article_no", "law_domain", "tag", "situation",
                             "requirement", "penalty", "corpus_version", "extracted_by"],
                )
            seeded += 1

        # 對帳：repo 是 manifest 來源法規的唯一真相。清掉表裡有、MANIFEST 沒有的
        # （改版換 version、換檔名、下架都會留下孤兒列，不清就會混進判定分母）。
        # origin='upload' 的不動 —— 那是管理者上傳的，走 pending/審核那條路。
        keep_names = [e["name"] for e in entries]
        keep_versions = [e.get("version") or "" for e in entries]
        removed = await conn.fetch(
            """
            DELETE FROM regulations r
            WHERE r.origin = 'manifest' AND NOT EXISTS (
                SELECT 1 FROM unnest($1::text[], $2::text[]) AS m(name, version)
                WHERE m.name = r.name AND m.version = r.version
            )
            RETURNING r.name, r.version
            """,
            keep_names, keep_versions,
        )
        for r in removed:
            problems.append(f"清掉不在 MANIFEST 的舊列：{r['name']}（version={r['version'] or '空'}）")
    finally:
        await conn.close()

    if problems:
        logger.warning("corpus seed 有問題：%s", "；".join(problems))
    logger.info("corpus seeded: %d 部法規", seeded)
    return {"seeded": seeded, "problems": problems}


# ── 檢核用查詢（這裡就是「檢索」）────────────────────────────
async def scope_negative_list(category: str) -> list[dict]:
    """按計畫類別撈出該進判定的管制條目 —— 確定性，非相似度。

    同一個 category 跑幾次都回同一批（同一個 corpus 版本下），所以報告可以誠實宣告
    「本次檢核涵蓋 N 條、M 個法領域」，而且 Playwright 斷言得起來。
    """
    if not _DATABASE_URL:
        return []
    cats = SCOPE_WHITELIST.get(category, [category])
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT nl.id, nl.article_no, nl.law_domain, nl.tag, nl.situation,
                   nl.requirement, nl.penalty, r.name AS regulation, r.category
            FROM negative_list nl JOIN regulations r ON r.id = nl.regulation_id
            WHERE r.status = 'active' AND r.category = ANY($1::text[])
            ORDER BY nl.law_domain, r.name, nl.id
            """,
            cats,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def corpus_meta() -> dict:
    """語料版本資訊（給報告表頭用，讓每份報告自證是哪一版語料跑的）。"""
    man = _load_manifest()
    return {
        "corpus_version": man.get("corpus_version", ""),
        "count": man.get("count", 0),
        "count_fulltext": man.get("count_fulltext", 0),
        "extracted_by": man.get("extracted_by", ""),
    }


async def non_judging_regulations() -> list[dict]:
    """收錄了但不進判定的法規（草案 / 全文未取得）—— 報告要交代，不能靜靜消失。"""
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT name, category, status FROM regulations "
            "WHERE status IN ('draft','no_fulltext') ORDER BY status, name"
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def excluded_categories(category: str) -> list[str]:
    """本次 scope 外的類別 —— 報告要誠實寫「未評估」，不能靜默消失。"""
    if not _DATABASE_URL:
        return []
    cats = SCOPE_WHITELIST.get(category, [category])
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT category FROM regulations WHERE status='active' AND NOT (category = ANY($1::text[]))",
            cats,
        )
        return sorted(r["category"] for r in rows)
    finally:
        await conn.close()


async def list_regulations(status: Optional[str] = None) -> list[dict]:
    if not _DATABASE_URL:
        return []
    conn = await _connect()
    try:
        sql = """
            SELECT r.id, r.name, r.category, r.version, r.status, r.origin, r.chars,
                   r.uploaded_by, r.reviewed_by, r.created_at,
                   (SELECT COUNT(*) FROM regulation_articles a WHERE a.regulation_id=r.id) AS articles,
                   (SELECT COUNT(*) FROM negative_list n WHERE n.regulation_id=r.id) AS controls
            FROM regulations r
        """
        if status:
            rows = await conn.fetch(sql + " WHERE r.status=$1 ORDER BY r.category, r.name", status)
        else:
            rows = await conn.fetch(sql + " ORDER BY r.category, r.name")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def corpus_stats() -> dict:
    """知識庫面板用的一眼狀態。"""
    if not _DATABASE_URL:
        return {}
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE status='active')      AS active,
              COUNT(*) FILTER (WHERE status='pending')     AS pending,
              COUNT(*) FILTER (WHERE status='no_fulltext') AS no_fulltext,
              COUNT(*) FILTER (WHERE status='draft')       AS draft,
              COUNT(*)                                     AS total
            FROM regulations
            """
        )
        arts = await conn.fetchval(
            "SELECT COUNT(*) FROM regulation_articles a JOIN regulations r ON r.id=a.regulation_id WHERE r.status='active'"
        )
        ctrls = await conn.fetchval(
            "SELECT COUNT(*) FROM negative_list n JOIN regulations r ON r.id=n.regulation_id WHERE r.status='active'"
        )
        domains = await conn.fetch(
            "SELECT DISTINCT law_domain FROM negative_list n JOIN regulations r ON r.id=n.regulation_id WHERE r.status='active' ORDER BY 1"
        )
        by_cat = await conn.fetch(
            "SELECT category, COUNT(*) AS n FROM regulations WHERE status='active' GROUP BY category ORDER BY 1"
        )
        return {
            **dict(row),
            "articles": arts or 0,
            "controls": ctrls or 0,
            "domains": [d["law_domain"] for d in domains],
            "by_category": {c["category"]: c["n"] for c in by_cat},
        }
    finally:
        await conn.close()


async def add_upload(name: str, category: str, *, source_file: str, sha256: str,
                     chars: int, uploaded_by: str, version: str = "") -> Optional[int]:
    """管理者上傳的法規 → 一律先進 pending，**不進判定分母**。

    語料庫是判定的分母：混進一部錯的法規，報告就會憑空長出違規，而且沒人看得出來。
    所以 runtime 上傳只到 pending 為止，要有人按下啟用（activate_regulation）才生效；
    repo MANIFEST 裡的 31 部則在開機 seed 時直接 active（有 sha256 把關）。
    """
    if not _DATABASE_URL:
        return None
    conn = await _connect()
    try:
        return await conn.fetchval(
            """
            INSERT INTO regulations
                (name, category, version, source_file, sha256, chars, status, origin, uploaded_by)
            VALUES ($1,$2,$3,$4,$5,$6,'pending','upload',$7)
            ON CONFLICT (name, version) DO UPDATE SET
                source_file=EXCLUDED.source_file, sha256=EXCLUDED.sha256,
                chars=EXCLUDED.chars, uploaded_by=EXCLUDED.uploaded_by
            RETURNING id
            """,
            name, category, version, source_file, sha256, chars, uploaded_by,
        )
    finally:
        await conn.close()


async def activate_regulation(reg_id: int, reviewed_by: str) -> bool:
    """管理者審核通過 → 上傳的法規才進判定分母（#112 治理閘門）。"""
    if not _DATABASE_URL:
        return False
    conn = await _connect()
    try:
        res = await conn.execute(
            "UPDATE regulations SET status='active', reviewed_by=$2, activated_at=NOW() WHERE id=$1 AND status='pending'",
            reg_id, reviewed_by,
        )
        return res.endswith("1")
    finally:
        await conn.close()
