"""SSO handoff 入口（issue #37 / tplanet #89）。

CMS 使用者點「進 AI-Eva」→ CMS 簽 RS256 handoff token（aud=ai-eva，短 TTL）→
轉址到這裡。本入口：

  1. verify_handoff(token)  → 驗 RS256 + aud + exp，拿 identity（project/tenant/user）
  2. fetch_manifest(token)  → 握手選 (a)：帶 handoff token 抓該帳號的工具白名單
  3. ToolRuntime(manifest)  → 載入白名單（deny-by-default）
  4. 存 session（corr：session_id → identity + runtime）+ 種 cookie → 轉址進聊天

骨架階段：
- session store 用 in-memory dict（之後挪 PG，跟 #31 pending 同樣 durable 考量）
- Chainlit 聊天 UI 取用 identity/runtime 的 wire（on_chat_start / header_auth_callback）
  留給 #35 第一個副駕；這裡先把「驗章→manifest→runtime→session」整鏈備好。

安全：token 驗不過 → 403（un-authed 打這個端點就是 403，不放行）。
"""
import logging
import secrets
import json
import os

import asyncpg
from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth import issuers
from app.tools.runtime import ToolRuntime

logger = logging.getLogger(__name__)

# SSO session 存 PG（durable）—— ai-eva 重啟/部署後 session 仍在，使用者不會掉回散客（#44）。
# 存 identity + manifest（不存 ToolRuntime 物件）；取回時用 manifest 重建 ToolRuntime（便宜）。
_DATABASE_URL = os.getenv("DATABASE_URL", "")
_SESSION_TTL = 28800   # 8h（beta：1h 對一整天測試太短，會做到一半過期；prod 可再縮短或改 refresh）


def _pg_url() -> str:
    return _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def ensure_sso_sessions_table() -> None:
    if not _DATABASE_URL:
        logger.warning("DATABASE_URL not set; SSO session 不持久化（重啟即掉）")
        return
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sso_sessions (
                id          TEXT PRIMARY KEY,
                identity    JSONB NOT NULL,
                manifest    JSONB NOT NULL,
                refresh_token TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at  TIMESTAMPTZ NOT NULL
            );
            ALTER TABLE sso_sessions ADD COLUMN IF NOT EXISTS refresh_token TEXT;
            CREATE INDEX IF NOT EXISTS ix_sso_sessions_exp ON sso_sessions (expires_at);
            """
        )
        logger.info("sso_sessions table ready")
    finally:
        await conn.close()


async def establish_sso_session(token: str, refresh_token: str | None = None) -> dict:
    """驗章 → manifest → 存 durable session（PG）。回 {session_id, identity, tools}。

    任一步失敗就 raise（caller 轉 403）。這是整條 SSO 鏈的可測核心。
    """
    identity = issuers.verify_handoff(token)                      # 1. RS256 驗章 → identity
    manifest = issuers.fetch_manifest(
        identity["issuer"], token, tenant_id=identity.get("tenant_id")
    )  # 2. 帶 token 抓 manifest（選 a）
    tools = [t["function"]["name"] for t in ToolRuntime(manifest).visible_tools()]  # 驗 manifest 可用 + 列 tools

    sid = secrets.token_urlsafe(24)
    if _DATABASE_URL:
        conn = await _connect()
        try:
            await conn.execute(
                "INSERT INTO sso_sessions (id, identity, manifest, refresh_token, expires_at) "
                "VALUES ($1, $2::jsonb, $3::jsonb, $4, NOW() + ($5 || ' seconds')::interval)",
                sid, json.dumps(identity), json.dumps(manifest), refresh_token, str(_SESSION_TTL),
            )
        finally:
            await conn.close()
    logger.info(
        "SSO session %s… project=%s user=%s → %d tool(s)",
        sid[:8], identity["project"], identity.get("user_id"), len(tools),
    )
    return {"session_id": sid, "identity": identity, "tools": tools}


async def get_sso_session(session_id: str | None, *, allow_expired: bool = False) -> dict | None:
    """用 cookie 的 session_id 取回 {identity, runtime}。durable（PG）→ 重啟/部署後仍在。

    重建 ToolRuntime（用存的 manifest），所以不依賴記憶體物件存活。
    """
    if not session_id or not _DATABASE_URL:
        return None
    conn = await _connect()
    try:
        expiry_clause = "" if allow_expired else " AND expires_at > NOW()"
        row = await conn.fetchrow(
            "SELECT identity, manifest, refresh_token, (expires_at <= NOW()) AS expired "
            f"FROM sso_sessions WHERE id = $1{expiry_clause}", session_id,
        )
    finally:
        await conn.close()
    if not row:
        return None
    identity = row["identity"] if isinstance(row["identity"], dict) else json.loads(row["identity"])
    manifest = row["manifest"] if isinstance(row["manifest"], dict) else json.loads(row["manifest"])
    return {"session_id": session_id, "identity": identity, "expired": bool(row["expired"]),
            "refresh_token": row["refresh_token"], "manifest": manifest,
            "runtime": ToolRuntime(manifest)}


async def refresh_sso_session(session_id: str | None) -> dict | None:
    """Rotate the callback credential（confirmed write 前、讀取 401 自癒、過期 session 復活都走這）。

    Refresh 成功 → 回傳完整 session（新 manifest + 新 credential）。
    Refresh 失敗 → 降級沿用既有 manifest（tools 已載入，runtime 不被拆除）。
    """
    current = await get_sso_session(session_id, allow_expired=True)
    if not current or not _DATABASE_URL:
        return None
    identity = current["identity"]
    refresh_token = current.get("refresh_token")
    if refresh_token:
        try:
            manifest = issuers.refresh_manifest(
                identity["issuer"], refresh_token, tenant_id=identity.get("tenant_id")
            )
            next_refresh_token = manifest.get("refresh_token") or refresh_token
            conn = await _connect()
            try:
                await conn.execute(
                    "UPDATE sso_sessions SET manifest = $2::jsonb, refresh_token = $3, "
                    "expires_at = NOW() + ($4 || ' seconds')::interval WHERE id = $1",
                    session_id, json.dumps(manifest), next_refresh_token, str(_SESSION_TTL),
                )
            finally:
                await conn.close()
            return {"session_id": session_id, "identity": identity, "expired": False,
                    "refresh_token": next_refresh_token, "manifest": manifest,
                    "runtime": ToolRuntime(manifest)}
        except Exception:
            logger.warning("SSO credential refresh failed (degraded) for session %s", (session_id or "")[:8], exc_info=True)
            manifest = current["manifest"]
            conn = await _connect()
            try:
                await conn.execute(
                    "UPDATE sso_sessions SET expires_at = NOW() + ($2 || ' seconds')::interval "
                    "WHERE id = $1",
                    session_id, str(_SESSION_TTL),
                )
            finally:
                await conn.close()
            return {"session_id": session_id, "identity": identity, "expired": False,
                    "refresh_token": refresh_token, "manifest": manifest,
                    "runtime": ToolRuntime(manifest), "degraded": True}
    return None


@fastapi_app.get("/sso/handoff")
async def sso_handoff(token: str, request: Request, refresh_token: str | None = None):
    """CMS 轉址進來：?token=<RS256 handoff>。驗過 → 種 cookie → 轉址進 /。"""
    try:
        sess = await establish_sso_session(token, refresh_token)
    except Exception as e:  # noqa: BLE001
        logger.warning("SSO handoff rejected: %s: %s", type(e).__name__, e)
        raise HTTPException(403, f"SSO handoff failed: {type(e).__name__}")

    resp = RedirectResponse(url="/", status_code=303)
    # Chainlit 的 websocket 認證讀它自己的 access_token cookie，不讀 eva_sso。每次 handoff
    # 都要覆寫，否則瀏覽器沿用上一次的 JWT（可能是別的租戶、已過期），裡面帶舊的
    # sso_session_id → refresh 打到錯的租戶 401 → cms_runtime 消失（#100）。
    from chainlit.auth import create_jwt, set_auth_cookie
    from chainlit.user import User

    idn = sess["identity"]
    set_auth_cookie(request, resp, create_jwt(User(
        identifier=idn.get("email") or f'{idn["project"]}:{idn.get("user_id")}',
        metadata={
            "sso_session_id": sess["session_id"],
            "project": idn["project"],
            "tenant_id": idn.get("tenant_id"),
            "role": "cms-user",
        },
    )))
    resp.set_cookie(
        "eva_sso", sess["session_id"],
        httponly=True, secure=True, samesite="lax", max_age=_SESSION_TTL,
    )
    # 非 HttpOnly 提示旗標：純給前端 custom.js 偵測「這是 SSO 來源」以蓋 splash（#43）。
    # 不含 secret（只是 "1"），所以可被 JS 讀；真正的 session 仍在 HttpOnly 的 eva_sso。
    resp.set_cookie(
        "eva_sso_hint", "1",
        httponly=False, secure=True, samesite="lax", max_age=_SESSION_TTL,
    )
    return resp


# Chainlit 掛了 SPA 萬用 GET 路由（/{path:path}），會搶先吃掉 GET /sso/handoff
# 並回 SPA index.html。跟 device.py /device/img 同雷 —— 把本路由提到 router 最前面，
# 搶在 catch-all 前（Starlette 依註冊順序配對）。
for _r in list(fastapi_app.router.routes):
    if getattr(_r, "path", None) == "/sso/handoff":
        fastapi_app.router.routes.remove(_r)
        fastapi_app.router.routes.insert(0, _r)
        break
