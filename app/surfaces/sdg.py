"""Internal SDG generation service for CMS-triggered, explicit requests."""
import hmac
import os

from chainlit.server import app as fastapi_app
from fastapi import HTTPException, Request

from app.core.copilot import generate_sdg

_SERVICE_TOKEN = os.getenv("CMS_SDG_SERVICE_TOKEN", "").strip()


def _check_service_token(request: Request) -> None:
    if not _SERVICE_TOKEN:
        raise HTTPException(503, "SDG service is not configured")
    supplied = request.headers.get("x-sdg-service-token", "")
    if not hmac.compare_digest(supplied, _SERVICE_TOKEN):
        raise HTTPException(403, "Invalid SDG service token")


@fastapi_app.post("/internal/sdg/generate")
async def generate_sdg_endpoint(request: Request):
    _check_service_token(request)
    data = await request.json()
    project = data.get("project") or {}
    if not isinstance(project, dict) or not (project.get("name") or "").strip():
        raise HTTPException(400, "project.name is required")
    try:
        sdgs = await generate_sdg(project, user=str(data.get("user_id") or ""))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"SDG generation failed: {type(exc).__name__}") from exc
    sdgs = {
        str(key): value for key, value in sdgs.items()
        if str(key).isdigit() and 1 <= int(key) <= 17
        and isinstance(value, str) and 0 < len(value.strip()) <= 1000
    }
    if not sdgs or len(sdgs) > 6:
        raise HTTPException(502, "SDG generation returned no results")
    return {"project_sdgs": sdgs}
