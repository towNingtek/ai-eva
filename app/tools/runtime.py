"""ToolRuntime — 通用工具執行引擎（issue #34，core=primitive）。

不認得任何 project：誰給 manifest 就照辦。同時服務 multi-tenant CMS 與 IoT。

職責：
- `load(manifest)`        吃一份 manifest（某帳號可用的工具白名單）
- `visible_tools()`       回 OpenAI function schema 清單（餵給 LLM bind_tools）
- `execute(name, args)`   執行：白名單外拒絕；寫類/缺欄位 → 要確認；帶 credential 回打發起專案

安全預設（deny by default）：
- 不在 manifest 的工具 → 拒絕（防 NLP 無差別觸發）
- kind 缺漏 / 非 read → 當 write、要確認（寧可多問一次，不默默寫）

授權不在這層：ToolRuntime 帶 `manifest.credential`（通常 = 使用者原始 JWT）回打
`callback_base + endpoint`，**授權由發起專案的後端判**（越權它回 403）。core 不複製權限邏輯。

manifest schema（與 multi-tenant `GET /api/tools/manifest`、tplanet #88 共用）：
    {
      "callback_base": "https://cms.example/api",
      "credential": "<bearer token，多半是該 user 的 JWT>",
      "tools": [
        {"name","kind"(read|write),"needs_confirm"(bool),"endpoint","method"?,
         "auth"?(bearer),"description","parameters"(JSON schema)}
      ]
    }
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ToolRuntime:
    def __init__(self, manifest: Optional[dict] = None, *, timeout: float = 30.0):
        self._tools: dict[str, dict] = {}
        self._callback_base: str = ""
        self._credential: str = ""
        self._timeout = timeout
        if manifest is not None:
            self.load(manifest)

    # ── 載入 ──────────────────────────────────────────────
    def load(self, manifest: dict) -> None:
        """吃 manifest。重複 load 會覆蓋（per-session 換帳號時用）。"""
        self._callback_base = (manifest.get("callback_base") or "").rstrip("/")
        self._credential = manifest.get("credential") or ""
        self._tools = {}
        for t in manifest.get("tools") or []:
            name = (t.get("name") or "").strip()
            if not name:
                continue
            self._tools[name] = t
        logger.info("ToolRuntime loaded %d tool(s): %s", len(self._tools), list(self._tools))

    # ── 安全預設 ──────────────────────────────────────────
    @staticmethod
    def _needs_confirm(tool: dict) -> bool:
        """寫類 / 危險 / 欄位缺漏 → 要確認。安全預設：拿不準就要確認。"""
        if "needs_confirm" in tool:
            return bool(tool["needs_confirm"])
        kind = (tool.get("kind") or "").lower()
        return kind != "read"   # 只有明確 read 才免確認；其餘（含缺漏）都要

    # ── 給 LLM 的白名單 ───────────────────────────────────
    def visible_tools(self) -> list[dict]:
        """回 OpenAI function schema 清單（只有 manifest 內的；白名單外不存在）。"""
        out = []
        for name, t in self._tools.items():
            out.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                },
            })
        return out

    def is_allowed(self, name: str) -> bool:
        return name in self._tools

    # ── 執行 ──────────────────────────────────────────────
    async def execute(self, name: str, args: dict, *, confirmed: bool = False) -> dict:
        """執行工具。

        回傳：
          {"status":"denied", ...}        不在白名單
          {"status":"need_confirm", ...}  寫類未確認 → 回 draft，等二次確認
          {"status":"ok", "result": ...}  成功（HTTP 回傳）
          {"status":"error", ...}         呼叫失敗（含發起專案回的 403 越權）
        """
        tool = self._tools.get(name)
        if tool is None:
            # deny by default：白名單外一律拒絕
            return {"status": "denied", "reason": f"tool '{name}' not in manifest"}

        if self._needs_confirm(tool) and not confirmed:
            return {
                "status": "need_confirm",
                "tool": name,
                "draft": {"name": name, "args": args, "kind": tool.get("kind", "write")},
                "message": f"「{name}」是寫入/危險操作，需要你確認後才執行。",
            }

        # 帶 credential 回打發起專案；授權由它的後端判（越權它回 403）
        endpoint = tool.get("endpoint") or ""
        url = f"{self._callback_base}{endpoint}"
        method = (tool.get("method") or ("GET" if (tool.get("kind") == "read") else "POST")).upper()
        headers = {}
        if self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as cx:
                if method == "GET":
                    r = await cx.get(url, params=args, headers=headers)
                else:
                    r = await cx.request(method, url, json=args, headers=headers)
        except Exception as e:  # noqa: BLE001
            logger.exception("ToolRuntime execute '%s' transport error", name)
            return {"status": "error", "reason": f"{type(e).__name__}: {e}", "tool": name}

        if r.status_code == 403:
            # 發起專案後端判定越權 —— core 不複製權限，原樣回報
            return {"status": "error", "reason": "forbidden by source backend (403)", "tool": name}
        if r.status_code >= 400:
            return {"status": "error", "reason": f"HTTP {r.status_code}: {r.text[:200]}", "tool": name}

        try:
            result = r.json()
        except ValueError:
            result = {"text": r.text}
        return {"status": "ok", "tool": name, "result": result}
