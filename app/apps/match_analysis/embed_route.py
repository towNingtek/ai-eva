"""讓工作區 embed.html 在「真實媒合任務」時多載入 /public/workspace/match-task.js。

embed.html 不在 #203 可修改範圍內，卻是 overlay 固定打開的頁面；只有 `mode=match&v=live-match`
（本 app 的 CopilotFunction 參數）才在 </body> 前補一行 script，其它請求（示範、法規、雲林）原樣回傳檔案。
等 embed.html 自己加上這行後，這裡偵測到已存在就不再重複插入。
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.assets_version import content_hash

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
EMBED = ROOT / "public" / "workspace" / "embed.html"
TASK_JS = ROOT / "public" / "workspace" / "match-task.js"
# #215：建議卡（收藏／略過／補資料／寄站內邀請）由 public/tangle/match-cards.js 畫在任務面板下方
CARDS_JS = ROOT / "public" / "tangle" / "match-cards.js"
MARK = "match-task.js"
CARDS_MARK = "match-cards.js"


# #240：版本參數＝檔案內容雜湊（啟動時算一次）。寫死的版本在內容改了之後網址不變，CDN 會一直給舊檔。
def script_tags() -> tuple[str, str]:
    """依目前檔案內容重算 match-task.js、match-cards.js 的 <script>（測試改檔後可重呼叫）。"""
    return (f'<script src="./match-task.js?v={content_hash(TASK_JS)}"></script>',
            f'<script src="../tangle/match-cards.js?v={content_hash(CARDS_JS)}"></script>')


SCRIPT, CARDS_SCRIPT = script_tags()


def refresh() -> None:
    """重新計算 SCRIPT／CARDS_SCRIPT（檔案內容變了之後）。"""
    global SCRIPT, CARDS_SCRIPT
    SCRIPT, CARDS_SCRIPT = script_tags()


def _add(html: str, script: str) -> str:
    at = html.rfind("</body>")
    return html + script if at < 0 else html[:at] + script + html[at:]


def inject(html: str) -> str:
    if MARK not in html:
        html = _add(html, SCRIPT)
    if CARDS_MARK not in html:
        html = _add(html, CARDS_SCRIPT)
    return html


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
