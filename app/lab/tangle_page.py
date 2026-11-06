"""Copilot 工作區頁（feat/tangle-lab）。

/workspace：v17 工作區當主畫面，Eva 以 Chainlit copilot 掛在右側。
copilot 需要 accessToken：已登入（Chainlit access_token cookie）就直接沿用同一個 JWT；
未登入導去 /login，登入完回來。
"""
from pathlib import Path

from chainlit.auth.cookie import get_token_from_cookies
from chainlit.server import app as fastapi_app
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

_ROOT = Path(__file__).resolve().parents[2] / "public" / "workspace"


@fastapi_app.get("/workspace")
async def workspace(request: Request):
    token = get_token_from_cookies(request.cookies)
    if not token:
        return RedirectResponse("/login?next=/workspace", status_code=302)
    html = (_ROOT / "index.html").read_text(encoding="utf-8")
    boot = (
        '<script src="/copilot/index.js"></script>'
        "<script>window.mountChainlitWidget({chainlitServer:location.origin,"
        f'accessToken:{token!r},displayMode:"sidebar",opened:true,'
        'theme:"light"});window.__copilotReady=true;</script>'
    )
    html = html.replace("</body>", boot + "</body>")
    # 相對路徑資產改指 /public/workspace/
    html = html.replace('src="./', 'src="/public/workspace/')
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@fastapi_app.get("/")
async def root(request: Request):
    """試作站：登入後首頁直接是 copilot 工作區（Chainlit 登入後固定回 /，不看 next）。
    未登入交給 Chainlit 原本的頁面（它會顯示登入）。"""
    if get_token_from_cookies(request.cookies):
        return RedirectResponse("/workspace", status_code=302)
    from chainlit.server import serve
    return await serve(request)


# FastAPI 依註冊順序比對；Chainlit 的 /{full_path:path} 會吃掉後加的路由，
# 所以把本路由移到最前面。
_r = fastapi_app.router.routes
_mine = [r for r in _r if getattr(r, "path", None) in ("/workspace", "/") and getattr(r, "endpoint", None) in (workspace, root)]
for r in _mine:
    _r.remove(r)
    _r.insert(0, r)
