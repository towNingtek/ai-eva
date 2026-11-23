"""Multi-issuer 驗章層（issue #37 契約 A / tplanet #89 SSO）。

ai-eva 是多 project 信任中樞：每個發起專案（tplanet CMS、未來 IoT 玉設…）是一個
**issuer**，各自簽 RS256 handoff token，ai-eva **只用公鑰驗、不簽**（被攻破也無法偽造）。

verify_handoff(token) 做三件事：
1. 認 issuer（token 的 `iss`）→ 查 registry 拿它的 jwks_url / audience / project
2. 用該 issuer 的 JWKS 公鑰驗 RS256 簽章 + `aud` + `exp`（擋重放/過期）
3. 回 identity：**把 token 映成 project + tenant + user**（正是 #31 卡住的 identity→project）

issuer registry 目前 hardcode dev / stable 兩筆（per-env issuer key：CMS 每個環境
自己生 RS256 keypair、自己一個 iss）。之後可挪去 DB / project registry。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.i18n import normalize_lang

logger = logging.getLogger(__name__)

# ── issuer registry（誰可信 + 怎麼驗 + 映哪個 project）──────────────
# tenant_cms_base_url：同名 tenant（如 yunlin）在 dev/stable 都存在，CMS host 不同，
#   所以 tenant → CMS base 的映射跟著 issuer 走，不能全域共用。
# tenant_project_map：tenant → project 覆寫（#94 雲林雙軌）：特定租戶獨立成自己的
#   project，讓用量/LiteLLM key 分流（見 projects.metadata.litellm_key）。
#   沒列到的 tenant 沿用 issuer 的預設 project（如一般 CMS 租戶 → sechome）。
# return_hosts：通用的「返回來源網站」（ai-eva#172）。issuer 可在 handoff token 帶
#   `return_url`／`return_label`，AI-Eva 頁首顯示「← 返回 {label}」。只接受 https 且
#   host 符合這份清單（完整網域或 "*.網域" 萬用字元）的網址，其餘一律忽略——避免被拿來
#   轉址到任意網站。沒設 return_hosts 的 issuer 不顯示返回鈕。
ISSUERS: dict[str, dict] = {
    # dev / beta CMS（dev.4impact.cc、yunlin-beta.4impact.cc、beta.sechome.cc）
    "tplanet-cms": {
        "jwks_url": "https://dev.4impact.cc/api/tools/jwks",
        "manifest_url": "https://dev.4impact.cc/api/tools/manifest",
        "refresh_url": "https://dev.4impact.cc/api/accounts/tools/refresh",
        "audience": "ai-eva",
        "project": "sechome",   # CMS AI 秘書遷移專案（#50）；tenant 取自 token 的 tenant_id
        "tenant_cms_base_url": {
            "yunlin": "https://yunlin-beta.4impact.cc",
            # *.sechome.cc 租戶經 tenant-env-router 到 dev origin；manifest / refresh 要打租戶自己的
            # host，否則 origin 會解析成預設租戶（townway#78 工商搬遷）。
            "ntidipc": "https://ntidipc.sechome.cc",
            "newtaipei-city": "https://newtaipei-city.sechome.cc",
            # 南投測試站（tplanet-multi-tenant#480）；正式站 issuer 待 #482 路由確定後另加
            "nantou-gov": "https://nantou-gov.sechome.cc",
        },
        "tenant_project_map": {
            "yunlin": "yunlin",   # 雲林租戶 → 走 yunlin project 的 LiteLLM key/team
        },
        "return_hosts": ["dev.4impact.cc", "yunlin-beta.4impact.cc", "*.sechome.cc"],
    },
    # stable CMS（stable.4impact.cc、sechome.cc、yunlin.4impact.cc）
    # stable backend 需設 AI_EVA_ISSUER=tplanet-cms-stable（各環境自己的 RS256 key）
    "tplanet-cms-stable": {
        "jwks_url": "https://stable.4impact.cc/api/tools/jwks",
        "manifest_url": "https://stable.4impact.cc/api/tools/manifest",
        "refresh_url": "https://stable.4impact.cc/api/accounts/tools/refresh",
        "audience": "ai-eva",
        "project": "sechome",
        "tenant_cms_base_url": {
            "yunlin": "https://yunlin.4impact.cc",
        },
        "tenant_project_map": {
            "yunlin": "yunlin",
        },
        "return_hosts": ["stable.4impact.cc", "yunlin.4impact.cc", "sechome.cc", "*.sechome.cc"],
    },
}


def _host_allowed(host: str, patterns: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for p in patterns or []:
        p = p.lower()
        if p.startswith("*."):
            if host.endswith(p[1:]) and host != p[2:]:
                return True
        elif host == p:
            return True
    return False


def safe_return(issuer_id: str | None, url: Any, label: Any) -> dict | None:
    """通行證帶的返回網址（ai-eva#172）→ {"url","label"}，不合格回 None。

    只接受：字串、https、沒有帳密、host 在該 issuer 的 return_hosts 內。
    label 只留純文字、最多 40 字；沒給就用 host。
    """
    from urllib.parse import urlsplit

    issuer = ISSUERS.get(issuer_id or "") or {}
    if not isinstance(url, str) or len(url) > 2000:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    if not _host_allowed(parts.hostname, issuer.get("return_hosts", [])):
        return None
    text = label.strip() if isinstance(label, str) else ""
    text = "".join(ch for ch in text if ch.isprintable() and ch not in "<>\"'`")[:40].strip()
    return {"url": parts.geturl(), "label": text or parts.hostname}

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
      {"project","tenant_id","user_id","email","lang","issuer","claims"}

    lang：通行證的 `lang` claim（tplanet-multi-tenant#507），只接受 zh／en／ja／ko，
    其他值或缺少 → zh（#206）。
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
        "project": issuer.get("tenant_project_map", {}).get(tenant_id) or issuer["project"],
        "tenant_id": tenant_id,
        "user_id": claims.get("user_id"),
        "email": claims.get("email"),
        "lang": normalize_lang(claims.get("lang")),
        "issuer": iss,
        # ai-eva#172：通用「返回來源網站」；不合格（非 https、網域不在 return_hosts）→ None
        "return": safe_return(iss, claims.get("return_url"), claims.get("return_label")),
        "claims": claims,
    }


def lang_from_refresh(manifest: Any, current: Any = None) -> str:
    """refresh 回應（新 manifest）帶的語言（#206：refresh 時一併更新）。

    CMS refresh 端點帶 `lang`（或換發新的 handoff `token`，其 claim 帶 lang）→ 用新值；
    回應完全沒提語言 → 沿用目前的（不因舊版 CMS 沒帶就把使用者打回 zh）。
    """
    if isinstance(manifest, dict):
        if "lang" in manifest:
            return normalize_lang(manifest.get("lang"))
        tok = manifest.get("token") or manifest.get("handoff_token")
        if isinstance(tok, str) and tok:
            try:
                return verify_handoff(tok)["lang"]
            except Exception:  # noqa: BLE001 — 驗不過的 token 不採信
                logger.warning("refresh token claim rejected; keep current lang", exc_info=True)
    return normalize_lang(current)


def fetch_manifest(issuer_id: str, token: str, *, tenant_id: str | None = None,
                   timeout: float = 15.0) -> dict:
    """抓某 issuer 的 tool manifest，帶 token（握手選 (a)：直接帶 handoff token）。

    回該帳號可用的 manifest（{callback_base, credential, tools}），交給 ToolRuntime.load。
    """
    issuer = ISSUERS.get(issuer_id)
    if issuer is None:
        raise ValueError(f"unknown issuer: {issuer_id!r}")
    url = issuer.get("manifest_url")
    tenant_base = issuer.get("tenant_cms_base_url", {}).get(tenant_id or "")
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
    tenant_base = issuer.get("tenant_cms_base_url", {}).get(tenant_id or "")
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
