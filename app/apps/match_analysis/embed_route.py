"""讓工作區 embed.html 在「真實媒合任務」時多載入 /public/workspace/match-task.js。

embed.html 不在 #203 可修改範圍內，卻是 overlay 固定打開的頁面；只有 `mode=match&v=live-match`
（本 app 的 CopilotFunction 參數）才在 </body> 前補一行 script，其它請求（示範、法規、雲林）原樣回傳檔案。
等 embed.html 自己加上這行後，這裡偵測到已存在就不再重複插入。
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
EMBED = ROOT / "public" / "workspace" / "embed.html"
SCRIPT = '<script src="./match-task.js?v=live-match"></script>'
MARK = "match-task.js"


def inject(html: str) -> str:
    if MARK in html:
        return html
    at = html.rfind("</body>")
    return html + SCRIPT if at < 0 else html[:at] + SCRIPT + html[at:]


def wants(query) -> bool:
    from .task import LIVE_VERSION
    return query.get("mode") == "match" and query.get("v") == LIVE_VERSION


def install(app=None) -> bool:
    """在 Chainlit 的 /public/{path} 之前插一條 embed.html 路由；可重複呼叫。"""
    try:
        from starlette.responses import FileResponse, HTMLResponse
        from starlette.routing import Route
        if app is None:
            from chainlit.config import config
            from chainlit.server import app
            prefix = config.run.root_path or ""
        else:
            prefix = ""
    except Exception:  # noqa: BLE001
        logger.debug("match task: embed route unavailable", exc_info=True)
        return False
    routes = app.router.routes
    if any(getattr(r, "_match_task_embed", False) for r in routes):
        return True

    async def embed(request):
        if not wants(request.query_params):
            return FileResponse(EMBED)
        return HTMLResponse(inject(EMBED.read_text(encoding="utf-8")),
                            headers={"Cache-Control": "no-store"})

    route = Route(f"{prefix}/public/workspace/embed.html", embed, methods=["GET"])
    route._match_task_embed = True
    routes.insert(0, route)
    return True
