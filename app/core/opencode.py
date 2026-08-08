"""opencode serve client — 無狀態 HTTP primitive（跟 core/llm.py 的 LiteLLM factory 平行）。

opencode serve 對 ai-eva 而言是「另一個 LLM 後端」：session 記憶在 opencode 那側。
這層只負責 HTTP（建 session / 送訊息 / 查模型），**不碰 PG、不含 surface 邏輯**——
LINE 的 session 映射在 `app/surfaces/line_opencode.py`，
Discord 的在 `app/surfaces/discord_voice.py`（core=primitive / app=strategy）。

env：
- `OPENCODE_SERVE_BASE`   例 `http://host.docker.internal:4096`；空 → 停用（is_enabled()=False）
- `OPENCODE_SERVE_USER`   basic auth 帳號（對應 opencode serve 的 OPENCODE_SERVER_USERNAME）
- `OPENCODE_SERVE_PASS`   basic auth 密碼
- `OPENCODE_MODEL`        例 `litellm/local-cheap`；空 → litellm/cloud-fast
- `OPENCODE_SESSION_TITLE` 新 session 的固定 title；空 → 由 caller 決定
- `OPENCODE_IMAGE_HOST_DIR` 圖片的 host 側目錄（container /app/data ↔ host data/ 共享，
  opencode server 跑在 host 要用 host 路徑讀圖）；空 → 直接用 image_path
- `OPENCODE_VISION_MODEL` / `OPENCODE_VISION_PROVIDERS` / `OPENCODE_VISION_MODELS`
  圖片訊息的模型策略（litellm/OpenAI-compatible 在 opencode 吃圖有 bug，anthropic 原生支援）
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_OPENCODE_SERVE_BASE = os.getenv("OPENCODE_SERVE_BASE", "").strip().rstrip("/")
_OPENCODE_SERVE_USER = os.getenv("OPENCODE_SERVE_USER", "").strip()
_OPENCODE_SERVE_PASS = os.getenv("OPENCODE_SERVE_PASS", "").strip()
_HTTP_TIMEOUT = float(os.getenv("OPENCODE_HTTP_TIMEOUT", "180"))

MODEL = os.getenv("OPENCODE_MODEL", "").strip()
DEFAULT_MODEL_STR = MODEL or "litellm/cloud-fast"
SESSION_TITLE = os.getenv("OPENCODE_SESSION_TITLE", "").strip()

# 圖片走 file:// URL 給 opencode server（跑在 host）讀
_OPENCODE_IMAGE_HOST_DIR = os.getenv("OPENCODE_IMAGE_HOST_DIR", "").strip().rstrip("/")
VISION_MODEL = os.getenv("OPENCODE_VISION_MODEL", "anthropic/claude-haiku-4-5").strip()
_VISION_PROVIDERS = {
    p.strip() for p in os.getenv("OPENCODE_VISION_PROVIDERS", "anthropic,openai,google").split(",")
    if p.strip()
}
_VISION_MODELS = {
    m.strip() for m in os.getenv("OPENCODE_VISION_MODELS", "").split(",") if m.strip()
}


def is_enabled() -> bool:
    return bool(_OPENCODE_SERVE_BASE)


def is_vision_model(provider_id: str, model_id: str) -> bool:
    return provider_id in _VISION_PROVIDERS or model_id in _VISION_MODELS


def _auth() -> Optional[httpx.BasicAuth]:
    if _OPENCODE_SERVE_USER and _OPENCODE_SERVE_PASS:
        return httpx.BasicAuth(_OPENCODE_SERVE_USER, _OPENCODE_SERVE_PASS)
    return None


def _default_model_ref() -> dict:
    """新 session 的 default model（ModelRef schema: providerID+id）。"""
    provider_id, _, model_id = DEFAULT_MODEL_STR.partition("/")
    return {"providerID": provider_id, "id": model_id}


def _message_model_ref(model_str: str = "") -> dict:
    """Message POST 的 model ref（schema: providerID+modelID）。"""
    provider_id, _, model_id = (model_str or DEFAULT_MODEL_STR).partition("/")
    return {"providerID": provider_id, "modelID": model_id}


def _extract_reply(payload: dict) -> str:
    parts = payload.get("parts", []) or []
    texts = [
        p.get("text", "")
        for p in parts
        if p.get("type") == "text" and p.get("text")
    ]
    return "\n".join(texts).strip()


def _image_url(image_path: str) -> str:
    if _OPENCODE_IMAGE_HOST_DIR:
        return f"file://{_OPENCODE_IMAGE_HOST_DIR}/{os.path.basename(image_path)}"
    return f"file://{image_path}"


def _send_body(
    text: str,
    image_path: Optional[str] = None,
    image_mime: Optional[str] = None,
    model_str: Optional[str] = None,
) -> dict:
    """組 message POST body。

    - model_str 明確 → 該次訊息用此模型（圖片暫切 / 自動切回用）
    - 純文字且沒指定 → 不帶 model，沿用 session 目前模型（Desktop 換模型後 surface 自動跟）
    - 圖片 → file:// URL（非 vision 模型強制切 VISION_MODEL）
    """
    parts: list = [{"type": "text", "text": text}]
    body: dict = {"parts": parts}
    if image_path:
        parts.insert(
            0,
            {
                "type": "file",
                "mime": image_mime or "image/jpeg",
                "filename": os.path.basename(image_path),
                "url": _image_url(image_path),
            },
        )
        if not model_str:
            model_str = VISION_MODEL
    if model_str:
        body["model"] = _message_model_ref(model_str)
    return body


async def create_session(title: str) -> str:
    """建 session：指定 title + default model。

    session 的 project 由 server 的 WorkingDirectory 決定，
    opencode Desktop 開同一個資料夾就看得到。
    """
    body: dict = {"title": title, "model": _default_model_ref()}
    async with httpx.AsyncClient(timeout=15, auth=_auth()) as cx:
        r = await cx.post(
            f"{_OPENCODE_SERVE_BASE}/session",
            headers={"Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    sid = data.get("id")
    if not sid:
        raise RuntimeError(f"opencode session create returned no id: {data}")
    return sid


async def get_session_model(session_id: str) -> Optional[tuple]:
    """問 opencode server 目前 session 的模型，回 (providerID, modelID) 或 None。"""
    async with httpx.AsyncClient(timeout=10, auth=_auth()) as cx:
        r = await cx.get(f"{_OPENCODE_SERVE_BASE}/session/{session_id}")
        if r.status_code >= 400:
            logger.warning("GET session %s failed: %s", session_id, r.status_code)
            return None
        m = (r.json() or {}).get("model") or {}
        pid, mid = m.get("providerID"), m.get("id")
        if pid and mid:
            return (pid, mid)
        return None


async def send_message(
    session_id: str,
    text: str,
    image_path: Optional[str] = None,
    image_mime: Optional[str] = None,
    model_str: Optional[str] = None,
) -> str:
    """送一則訊息進 session（同步），回覆從 parts[].text 取出。"""
    body = _send_body(text, image_path, image_mime, model_str)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, auth=_auth()) as cx:
        r = await cx.post(
            f"{_OPENCODE_SERVE_BASE}/session/{session_id}/message",
            headers={"Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        payload = r.json()
    reply = _extract_reply(payload)
    if not reply:
        logger.warning("opencode session %s returned no text parts", session_id)
    return reply or "（這次沒拿到回應，再試一次）"
