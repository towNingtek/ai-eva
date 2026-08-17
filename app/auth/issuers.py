"""Multi-issuer 驗章層（issue #37 契約 A / tplanet #89 SSO）。

ai-eva 是多 project 信任中樞：每個發起專案（tplanet CMS、未來 IoT 玉設…）是一個
**issuer**，各自簽 RS256 handoff token，ai-eva **只用公鑰驗、不簽**（被攻破也無法偽造）。

verify_handoff(token) 做三件事：
1. 認 issuer（token 的 `iss`）→ 查 registry 拿它的 jwks_url / audience / project
2. 用該 issuer 的 JWKS 公鑰驗 RS256 簽章 + `aud` + `exp`（擋重放/過期）
3. 回 identity：**把 token 映成 project + tenant + user**（正是 #31 卡住的 identity→project）

issuer registry 目前 hardcode dev 那筆；上 stable 補各環境的 jwks（per-env issuer key）。
之後可挪去 DB / project registry。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)

# ── issuer registry（誰可信 + 怎麼驗 + 映哪個 project）──────────────
ISSUERS: dict[str, dict] = {
    "tplanet-cms": {
        "jwks_url": "https://dev.4impact.cc/api/tools/jwks",
        "manifest_url": "https://dev.4impact.cc/api/tools/manifest",
        "refresh_url": "https://dev.4impact.cc/api/accounts/tools/refresh",
        "audience": "ai-eva",
        "project": "sechome",   # CMS AI 秘書遷移專案（#50）；tenant 取自 token 的 tenant_id
    },
}

TENANT_CMS_BASE_URL: dict[str, str] = {
    "yunlin": "https://yunlin-beta.4impact.cc",
}

# tenant → project 覆寫（#94 雲林雙軌）：特定租戶獨立成自己的 project，
# 讓用量/LiteLLM key 分流（見 projects.metadata.litellm_key）。
# 沒列到的 tenant 沿用 issuer 的預設 project（如一般 CMS 租戶 → sechome）。
TENANT_PROJECT_MAP: dict[str, str] = {
    "yunlin": "yunlin",   # 雲林租戶 → 走 yunlin project 的 LiteLLM key/team
}

_AUDIENCE_DEFAULT = "ai-eva"

# ── JWKS 快取（kid→公鑰物件；含 TTL，支援輪替）─────────────────────
_JWKS_CACHE: dict[str, dict] = {}   # jwks_url -> {"keys": {kid: pubkey}, "exp": ts}
_JWKS_TTL = 600   # 10 分鐘；輪替時最多 stale 這麼久（要更即時可在 kid miss 時強制 refresh）


def _now() -> float:
    return time.time()


def _fetch_jwks(jwks_url: str, *, force: bool = False) -> dict[str, Any]:
    """抓 JWKS → 解析成 {kid: 公鑰物件}，帶 TTL 快取。"""
    cached = _JWKS_CACHE.get(jwks_url)
    if cached and not force and cached["exp"] > _now():
        return cached["keys"]
    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    keys = {}
    for jwk in resp.json().get("keys", []):
        kid = jwk.get("kid")
        if not kid:
            continue
        keys[kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))
    _JWKS_CACHE[jwks_url] = {"keys": keys, "exp": _now() + _JWKS_TTL}
    logger.info("fetched JWKS %s: %d key(s)", jwks_url, len(keys))
    return keys


def _pubkey_for(issuer: dict, kid: str):
    keys = _fetch_jwks(issuer["jwks_url"])
    if kid not in keys:
        # kid miss → 可能剛輪替，強制 refresh 一次
        keys = _fetch_jwks(issuer["jwks_url"], force=True)
    key = keys.get(kid)
    if key is None:
        raise ValueError(f"kid '{kid}' not in JWKS {issuer['jwks_url']}")
    return key


def verify_handoff(token: str) -> dict:
    """驗 RS256 handoff token → 回 identity dict。

    raises:
      jwt.PyJWTError（簽章/aud/exp/iss 不對）、ValueError（未知 issuer / kid）
    回：
      {"project","tenant_id","user_id","email","issuer","claims"}
    """
    # 先看未驗 header / iss（決定用哪個 issuer 的公鑰）
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    unverified = jwt.decode(token, options={"verify_signature": False})
    iss = unverified.get("iss")

    issuer = ISSUERS.get(iss or "")
    if issuer is None:
        raise ValueError(f"unknown issuer: {iss!r}")

    pub = _pubkey_for(issuer, kid)
    claims = jwt.decode(
        token,
        pub,
        algorithms=["RS256"],
        audience=issuer.get("audience", _AUDIENCE_DEFAULT),
        issuer=iss,
    )
    tenant_id = claims.get("tenant_id")
    return {
        "project": TENANT_PROJECT_MAP.get(tenant_id) or issuer["project"],
        "tenant_id": tenant_id,
        "user_id": claims.get("user_id"),
        "email": claims.get("email"),
        "issuer": iss,
        "claims": claims,
    }


def fetch_manifest(issuer_id: str, token: str, *, tenant_id: str | None = None,
                   timeout: float = 15.0) -> dict:
    """抓某 issuer 的 tool manifest，帶 token（握手選 (a)：直接帶 handoff token）。

    回該帳號可用的 manifest（{callback_base, credential, tools}），交給 ToolRuntime.load。
    """
    issuer = ISSUERS.get(issuer_id)
    if issuer is None:
        raise ValueError(f"unknown issuer: {issuer_id!r}")
    url = issuer.get("manifest_url")
    tenant_base = TENANT_CMS_BASE_URL.get(tenant_id or "")
    if tenant_base:
        url = f"{tenant_base.rstrip('/')}/api/tools/manifest"
    if not url:
        raise ValueError(f"issuer {issuer_id!r} has no manifest_url")
    r = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    # CMS 回 {"success":true,"data":{callback_base,credential,tools}}；拆 data 信封交給 ToolRuntime。
    # 若無信封（其他 issuer 直接回 manifest）則原樣回。
    return body.get("data", body) if isinstance(body, dict) else body


def refresh_manifest(issuer_id: str, refresh_token: str, *, tenant_id: str | None = None,
                     timeout: float = 15.0) -> dict:
    """Exchange a CMS-issued AI-Eva refresh token for a new tool manifest."""
    issuer = ISSUERS.get(issuer_id)
    if issuer is None:
        raise ValueError(f"unknown issuer: {issuer_id!r}")
    tenant_base = TENANT_CMS_BASE_URL.get(tenant_id or "")
    url = (
        f"{tenant_base.rstrip('/')}/api/accounts/tools/refresh"
        if tenant_base else issuer.get("refresh_url")
    )
    if not url:
        raise ValueError(f"issuer {issuer_id!r} has no refresh endpoint")
    r = httpx.post(url, headers={"Authorization": f"Bearer {refresh_token}"}, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    return body.get("data", body) if isinstance(body, dict) else body
