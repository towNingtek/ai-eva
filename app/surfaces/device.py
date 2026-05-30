"""Device surface — edge node 的入口 adapter（issue #25）。

掛在 Chainlit 的 FastAPI app：
- POST /device/register        node 自報能力 → node registry（NAT-friendly，node 主動）
- POST /device/intent          node 報意圖 → 正規化成 Envelope → dispatch → 回 command 信封
- POST /device/result          node 回報 capability 執行結果（影像）→ 推給 project 的 LINE 收件人
- GET  /device/img/{filename}  影像公開來源（無認證；LINE 抓圖用，避開 Chainlit /public 的 302）

正規化拋棄式 pilot（ai-cat-pilot.py）的三個繞路：
  1. 能力來自 node registry，不再硬寫 decide() 回傳
  2. 收件人查 projects 表 line_recipient，不再直接吃 env LINE_USER_ID
  3. intent 進統一 dispatch（跟 web/LINE 同一條），不再自成一套

認證：node 帶 `X-Device-Token`（= DEVICE_SURFACE_TOKEN）。沒設 token 就整個擋掉，避免裸跑。

影像出口：node 把 base64 傳上來，ai-eva 落地 + 用自己的公開 hostname 當圖床
（DEVICE_PUBLIC_BASE）。beta 沒公開 hostname 時 LINE 抓不到圖屬正常，register/intent/
result 路由邏輯仍可驗；完整影像 round-trip 在有公開 hostname 的部署（pi5 / stable）驗。
"""
import base64
import logging
import os
import time

from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.dispatch import Envelope, handle_device_intent
from app.nodes import registry as node_registry
from app.projects import registry as project_registry
from app.surfaces import line as line_surface
from app.settings import ROOT

logger = logging.getLogger(__name__)

_DEVICE_TOKEN = os.getenv("DEVICE_SURFACE_TOKEN", "").strip()
_PUBLIC_BASE = os.getenv("DEVICE_PUBLIC_BASE", "").rstrip("/")
_IMG_DIR = ROOT / "public" / "device-img"
_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _check_token(req: Request) -> None:
    if not _DEVICE_TOKEN:
        raise HTTPException(503, "Device surface not configured (DEVICE_SURFACE_TOKEN missing)")
    if req.headers.get("x-device-token", "") != _DEVICE_TOKEN:
        raise HTTPException(403, "Invalid device token")


@fastapi_app.post("/device/register")
async def device_register(req: Request):
    """Node 報到：自報 {node, project, capabilities, label?, endpoint?, metadata?}。"""
    _check_token(req)
    data = await req.json()
    node_id = (data.get("node") or "").strip()
    project = (data.get("project") or "").strip()
    capabilities = data.get("capabilities") or []
    if not node_id or not project or not isinstance(capabilities, list):
        raise HTTPException(400, "node, project, capabilities[] required")

    await node_registry.register_node(
        node_id=node_id,
        project=project,
        capabilities=capabilities,
        label=data.get("label"),
        endpoint=data.get("endpoint"),
        metadata=data.get("metadata") or {},
    )
    return {"ok": True, "node": node_id, "project": project, "capabilities": capabilities}


@fastapi_app.post("/device/intent")
async def device_intent(req: Request):
    """Node 報意圖：{node, project, text} → dispatch → {project, commands}。"""
    _check_token(req)
    data = await req.json()
    node_id = (data.get("node") or "").strip()
    project = (data.get("project") or "").strip()
    text = (data.get("text") or "").strip()
    if not project or not text:
        raise HTTPException(400, "project and text required")

    # node 報意圖順帶當心跳（證明它還活著）
    if node_id:
        await node_registry.touch_node(node_id)

    env = Envelope(surface="device", project=project, text=text, node_id=node_id or None)
    result = await handle_device_intent(env)
    return result


@fastapi_app.post("/device/result")
async def device_result(req: Request):
    """Node 回報執行結果。目前支援影像：

    {node, project, images:[{lens, b64}]}  → 落地 + LINE image push 給 project 收件人。
    """
    _check_token(req)
    data = await req.json()
    node_id = (data.get("node") or "").strip()
    project = (data.get("project") or "").strip()
    images = data.get("images") or []
    if not project:
        raise HTTPException(400, "project required")

    # 收件人查 projects 表（正規：不吃 env）
    proj = await project_registry.get_project(project)
    recipient = (proj or {}).get("line_recipient")
    if not recipient:
        logger.warning("device_result: project=%s 沒有 line_recipient，結果無處可推", project)
        raise HTTPException(409, f"project '{project}' has no line_recipient")

    urls = []
    ts = int(time.time())
    for i, img in enumerate(images):
        b64 = img.get("b64", "")
        if not b64:
            continue
        lens = img.get("lens", str(i))
        fn = f"{node_id or 'node'}_{ts}_{lens}.jpg"
        (_IMG_DIR / fn).write_bytes(base64.b64decode(b64))
        if _PUBLIC_BASE:
            urls.append(f"{_PUBLIC_BASE}/device/img/{fn}")
        else:
            logger.warning("DEVICE_PUBLIC_BASE 未設，影像存了但 LINE 抓不到：%s", fn)

    sent = False
    if urls:
        sent = await line_surface.push_images_to_user(recipient, urls)
    logger.info("device_result: node=%s project=%s imgs=%d pushed=%s", node_id, project, len(urls), sent)
    return {"ok": sent, "stored": len([i for i in images if i.get("b64")]), "pushed": len(urls) if sent else 0}


@fastapi_app.get("/device/img/{filename}")
async def device_img(filename: str):
    """影像公開來源（無認證，給 LINE 抓圖）。只回 device-img 目錄下的檔案。"""
    safe = os.path.basename(filename)
    fp = _IMG_DIR / safe
    if not fp.is_file():
        raise HTTPException(404, "not found")
    return Response(content=fp.read_bytes(), media_type="image/jpeg")
