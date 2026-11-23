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
import re
import secrets
import json
import os

import asyncpg
from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import issuers
from app.i18n import SESSION_KEY as LANG_KEY, chainlit_locale, normalize_lang, t
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
    return {"session_id": sid, "identity": identity, "tools": tools, "manifest": manifest}


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
    identity = dict(current["identity"])
    identity[LANG_KEY] = normalize_lang(identity.get(LANG_KEY))
    refresh_token = current.get("refresh_token")
    if refresh_token:
        try:
            manifest = issuers.refresh_manifest(
                identity["issuer"], refresh_token, tenant_id=identity.get("tenant_id")
            )
            next_refresh_token = manifest.get("refresh_token") or refresh_token
            # #206：refresh 時語言一併更新（CMS 端使用者改了語言，下次換 credential 就跟上）
            identity[LANG_KEY] = issuers.lang_from_refresh(manifest, identity.get(LANG_KEY))
            conn = await _connect()
            try:
                await conn.execute(
                    "UPDATE sso_sessions SET manifest = $2::jsonb, refresh_token = $3, "
                    "expires_at = NOW() + ($4 || ' seconds')::interval, identity = $5::jsonb "
                    "WHERE id = $1",
                    session_id, json.dumps(manifest), next_refresh_token, str(_SESSION_TTL),
                    json.dumps(identity),
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


# ── ai-eva#233：轉跳過場 ─────────────────────────────────────────────
# 從 CMS 點 AI 秘書 → 驗章、抓 manifest、Chainlit SPA 載入，實測約 2 秒全白。
# 瀏覽器導覽（Accept 含 text/html）第一次打 /sso/handoff 時先回一張品牌過場頁（logo＋「正在帶你到
# AI 秘書…」，依語言），頁面再自己轉到 ?go=1 做真正的驗章＋303 → /；後端處理期間畫面停在過場頁。
# 到了 / 之後由 custom.css（#root 還空時）＋ custom.js（SSO splash）接手，同一套外觀，不會閃白。
# 非瀏覽器（API／測試，Accept 不含 text/html）或 go=1 → 直接走原本的 303。
_HANDOFF_BG = "linear-gradient(160deg,#e3f3f1 0%,#c9e8e3 100%)"
_HANDOFF_FG = "#0f5f57"
_HANDOFF_BG_SOLID = "#d6eeea"   # #244：<html> 先上實色底（漸層的中間色），任何一格都不出白底


def _token_lang(token: str, accept_language: str = "") -> str:
    """過場頁用的語言：讀 token 的 lang claim（**未驗章，只拿來選顯示文字**），沒有就看 Accept-Language。"""
    try:
        import jwt
        claims = jwt.decode(token, options={"verify_signature": False})
        if claims.get("lang"):
            return normalize_lang(claims.get("lang"))
    except Exception:  # noqa: BLE001 —— 壞 token 交給 go=1 那一步回 403
        pass
    return normalize_lang((accept_language or "").split(",")[0].split("-")[0].strip().lower() or None)


def render_handoff_page(lang: str, next_url: str) -> str:
    """品牌過場頁 HTML（logo＋依語言的「正在帶你到 AI 秘書…」），畫面至少繪製一次後才轉到 next_url。

    #244：手機曾截到只畫左半邊的過場（轉頁太快、截到繪製中途）→ 轉頁放在兩層
    requestAnimationFrame 之後；分頁在背景時 rAF 不跑，另以 setTimeout 保底。
    """
    import html as _html
    lang = normalize_lang(lang)
    text = _html.escape(t("handoff.loading", lang=lang))
    loc = _html.escape(chainlit_locale(lang), quote=True)
    nxt_attr = _html.escape(next_url, quote=True)
    nxt_js = json.dumps(next_url).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="{loc}" style="background:{_HANDOFF_BG_SOLID};"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>AI Eva</title>
<noscript><meta http-equiv="refresh" content="0;url={nxt_attr}"></noscript>
<style>
html{{background:{_HANDOFF_BG_SOLID};background:{_HANDOFF_BG};}}
html,body{{margin:0;height:100%;background:{_HANDOFF_BG};}}
.eva-handoff{{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;
  color:{_HANDOFF_FG};font:500 18px -apple-system,system-ui,'Noto Sans TC',sans-serif;}}
.eva-handoff img{{width:180px;max-width:50vw;height:auto;}}
.eva-dots{{display:flex;gap:6px}}.eva-dots i{{width:8px;height:8px;border-radius:50%;background:{_HANDOFF_FG};opacity:.3;
  animation:eva-dot 1s infinite ease-in-out}}.eva-dots i:nth-child(2){{animation-delay:.15s}}.eva-dots i:nth-child(3){{animation-delay:.3s}}
@keyframes eva-dot{{50%{{opacity:1}}}}
</style></head>
<body><div class="eva-handoff" role="status" aria-live="polite">
<img src="/public/logo_light.png" alt="AI Eva"><div>{text}</div><div class="eva-dots"><i></i><i></i><i></i></div>
</div>
<script>(function(){{var u={nxt_js},done=false;
function go(){{if(done)return;done=true;location.replace(u);}}
if(window.requestAnimationFrame){{requestAnimationFrame(function(){{requestAnimationFrame(go);}});
setTimeout(go,1000);}}else{{setTimeout(go,50);}}}})();</script>
</body></html>"""


# ── ai-eva#237：從 CMS 直接開啟某個工具（open=<app_id>，媒合可再帶 a=<專案 uuid> 預選 A）──────
# /sso/handoff 驗過之後才看 open：只接受「已註冊、在工具列上、該 project 啟用、角色允許」的 app id，
# 其餘一律忽略（不報錯，照常進開場）。合格的 open／a 放進 eva_open cookie（短效、HttpOnly），開場
# （app/main.py on_chat_start）讀到就等同按下該工具按鈕；每個 cookie 帶一次性 nonce，只生效一次
# （之後重新整理／開新對話不再自動開）。a 只在 open=match_analysis 時保留，真正能不能當 A 由
# 媒合任務拿到「可發起清單」後再判斷（不在清單就不預選）。
OPEN_COOKIE = "eva_open"
OPEN_TTL = 300               # cookie 只需撐過「轉址 → 開場」；過期後就算 nonce 紀錄遺失也不會再開
_OPEN_MAX_USED = 4096
_OPEN_USED: dict[str, None] = {}   # 已用過的 nonce（insertion-ordered，超量丟最舊的）
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def resolve_open(open_id: str | None, a: str | None, manifest: dict | None,
                 enabled: set[str] | None, project: str | None = None) -> dict | None:
    """open／a 參數 → {"app": id, "a": uuid?}；不合格（未註冊、不在工具列、未啟用、角色不允許）→ None。純函式。"""
    from app.apps._registry import DEFAULT_PROJECT, get_by_id, is_enabled_for, menu_apps, role_allows

    if not isinstance(open_id, str) or not _SAFE_ID.match(open_id):
        return None
    app = get_by_id(open_id)
    if app is None or app not in menu_apps():
        return None
    if not is_enabled_for(app, project or DEFAULT_PROJECT, enabled):
        return None
    role_apps = (manifest or {}).get("apps")
    if not role_allows(app, role_apps if isinstance(role_apps, dict) else None):
        return None
    out = {"app": app.id}
    if app.id == "match_analysis" and isinstance(a, str) and _SAFE_ID.match(a):
        out["a"] = a
    return out


def encode_open(intent: dict) -> str:
    """eva_open cookie 值：JSON（含一次性 nonce）再 URL-encode。"""
    from urllib.parse import quote
    body = {**intent, "n": secrets.token_urlsafe(12)}
    return quote(json.dumps(body, separators=(",", ":")), safe="")


def read_open(cookie_header: str | None) -> dict | None:
    """從 Cookie 標頭解出 eva_open（不消耗）；壞值 → None。"""
    from urllib.parse import unquote
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k != OPEN_COOKIE or not v:
            continue
        try:
            data = json.loads(unquote(v))
        except ValueError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("app"), str) or not isinstance(data.get("n"), str):
            return None
        out = {"app": data["app"], "n": data["n"]}
        if isinstance(data.get("a"), str) and _SAFE_ID.match(data["a"]):
            out["a"] = data["a"]
        return out
    return None


def consume_open(cookie_header: str | None) -> dict | None:
    """開場用：讀 eva_open，nonce 沒用過才回 {"app", "a"?} 並記為已用（只生效一次）。"""
    intent = read_open(cookie_header)
    if not intent or intent["n"] in _OPEN_USED:
        return None
    _OPEN_USED[intent.pop("n")] = None
    while len(_OPEN_USED) > _OPEN_MAX_USED:
        _OPEN_USED.pop(next(iter(_OPEN_USED)))
    return intent


async def _open_intent(sess: dict, open_id: str | None, a: str | None) -> dict | None:
    if not open_id:
        return None
    project = (sess.get("identity") or {}).get("project")
    try:
        from app.projects import registry as project_registry
        enabled = await project_registry.get_enabled_apps(project)
    except Exception:  # noqa: BLE001 —— 讀不到啟用矩陣就不自動開（開場照常）
        logger.warning("SSO open: enabled_apps lookup failed", exc_info=True)
        return None
    intent = resolve_open(open_id, a, sess.get("manifest"), enabled, project)
    if intent is None:
        logger.info("SSO open ignored: %r (project=%s)", open_id, project)
    return intent


@fastapi_app.get("/sso/handoff")
async def sso_handoff(token: str, request: Request, refresh_token: str | None = None, go: int = 0,
                      open: str | None = None, a: str | None = None):  # noqa: A002 —— 參數名照 CMS 網址
    """CMS 轉址進來：?token=<RS256 handoff>[&open=<app_id>[&a=<uuid>]]。驗過 → 種 cookie → 轉址進 /。"""
    if not go and "text/html" in request.headers.get("accept", ""):
        from urllib.parse import urlencode
        params = {"token": token, "go": "1"}
        if refresh_token:
            params["refresh_token"] = refresh_token
        if open:
            params["open"] = open
            if a:
                params["a"] = a
        page = render_handoff_page(
            _token_lang(token, request.headers.get("accept-language", "")),
            "/sso/handoff?" + urlencode(params),
        )
        # token 在網址上：不快取、不帶 referrer
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
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
            LANG_KEY: normalize_lang(idn.get(LANG_KEY)),
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
    # #206：介面語言提示（非 HttpOnly，給 custom.js 在 Chainlit SPA 啟動前覆寫 navigator.language，
    # 讓 .chainlit/translations/ 的對應語系生效）。值是 Chainlit locale（zh-TW／en-US／ja／ko），非機密。
    resp.set_cookie(
        "eva_lang", chainlit_locale(idn.get(LANG_KEY)),
        httponly=False, secure=True, samesite="lax", max_age=_SESSION_TTL,
    )
    # ai-eva#172：通用「返回來源網站」。值已由 issuers.safe_return 驗過（https＋issuer 登記的網域）；
    # 非 HttpOnly 給 custom.js 畫頁首按鈕，非機密。沒帶或不合格 → 刪掉舊的，不留上一次的連結。
    ret = idn.get("return")
    if ret:
        # cookie 值只能是 ASCII → JSON 再 URL-encode（站名是中文），custom.js 端 decodeURIComponent。
        from urllib.parse import quote
        resp.set_cookie(
            "eva_return", quote(json.dumps(ret, ensure_ascii=False, separators=(",", ":")), safe=""),
            httponly=False, secure=True, samesite="lax", max_age=_SESSION_TTL,
        )
    else:
        resp.delete_cookie("eva_return")
    # ai-eva#237：直接開啟某工具。沒帶或不合格 → 刪掉舊的，不讓上一次的 open 再生效。
    intent = await _open_intent(sess, open, a)
    if intent:
        resp.set_cookie(
            OPEN_COOKIE, encode_open(intent),
            httponly=True,   # 只有伺服器（開場的 websocket 握手）要讀
            secure=True, samesite="lax", max_age=OPEN_TTL,
        )
    else:
        resp.delete_cookie(OPEN_COOKIE)
    return resp


# Chainlit 掛了 SPA 萬用 GET 路由（/{path:path}），會搶先吃掉 GET /sso/handoff
# 並回 SPA index.html。跟 device.py /device/img 同雷 —— 把本路由提到 router 最前面，
# 搶在 catch-all 前（Starlette 依註冊順序配對）。
for _r in list(fastapi_app.router.routes):
    if getattr(_r, "path", None) == "/sso/handoff":
        fastapi_app.router.routes.remove(_r)
        fastapi_app.router.routes.insert(0, _r)
        break
