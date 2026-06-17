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
import time

from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth import issuers
from app.tools.runtime import ToolRuntime

logger = logging.getLogger(__name__)

# session_id → {identity, runtime, exp}。骨架用 in-memory；durable 版之後挪 PG。
_SESSIONS: dict[str, dict] = {}
_SESSION_TTL = 3600   # 1h


def _sweep() -> None:
    now = time.time()
    for sid in [k for k, v in _SESSIONS.items() if v["exp"] < now]:
        _SESSIONS.pop(sid, None)


async def establish_sso_session(token: str) -> dict:
    """驗章 → manifest → ToolRuntime → 建 session。回 {session_id, identity, tools}。

    任一步失敗就 raise（caller 轉 403）。這是整條 SSO 鏈的可測核心。
    """
    identity = issuers.verify_handoff(token)                 # 1. RS256 驗章 → identity
    manifest = issuers.fetch_manifest(identity["issuer"], token)  # 2. 帶 token 抓 manifest（選 a）
    runtime = ToolRuntime(manifest)                          # 3. 載白名單

    _sweep()
    sid = secrets.token_urlsafe(24)
    _SESSIONS[sid] = {
        "identity": identity,
        "runtime": runtime,
        "exp": time.time() + _SESSION_TTL,
    }
    tools = [t["function"]["name"] for t in runtime.visible_tools()]
    logger.info(
        "SSO session for project=%s tenant=%s user=%s → %d tool(s)",
        identity["project"], identity.get("tenant_id"), identity.get("user_id"), len(tools),
    )
    return {"session_id": sid, "identity": identity, "tools": tools}


def get_sso_session(session_id: str | None) -> dict | None:
    """供 Chainlit 端（#35）用 cookie 取回 identity + runtime。"""
    if not session_id:
        return None
    s = _SESSIONS.get(session_id)
    if not s or s["exp"] < time.time():
        return None
    return s


@fastapi_app.get("/sso/handoff")
async def sso_handoff(token: str, request: Request):
    """CMS 轉址進來：?token=<RS256 handoff>。驗過 → 種 cookie → 轉址進 /。"""
    try:
        sess = await establish_sso_session(token)
    except Exception as e:  # noqa: BLE001
        logger.warning("SSO handoff rejected: %s: %s", type(e).__name__, e)
        raise HTTPException(403, f"SSO handoff failed: {type(e).__name__}")

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(
        "eva_sso", sess["session_id"],
        httponly=True, secure=True, samesite="lax", max_age=_SESSION_TTL,
    )
    return resp
