"""CMS adapter — tplanet-cms 資料後端（#128）。

包既有 `ToolRuntime`（app/tools/runtime.py）：manifest 白名單、deny-by-default、
needs_confirm、encoding 都在那層，這裡只做「把 execute() 結果正規化成 AdapterResult」。

module 呼叫側一律 `await cms.query(QuerySpec(tool=..., args=..., ...))`，
不直接碰 runtime.execute —— 這就是 (b) 卡的界線：換後端（如 stub）module 不用改。
"""
from __future__ import annotations

from typing import Any

from app.adapters.base import AdapterResult, QuerySpec, unwrap_cms
from app.tools.runtime import ToolRuntime

_status_map = {
    "ok": "ok",
    "denied": "denied",
    "need_confirm": "need_confirm",
    "error": "error",
}


class CMSDataSource:
    provider = "tplanet-cms"

    def __init__(self, runtime: ToolRuntime | None = None, *, timeout: float = 30.0):
        self._runtime = runtime
        self._timeout = timeout

    def bind(self, runtime: ToolRuntime) -> None:
        """把已 load(manifest) 的 ToolRuntime 綁進來（SSO session 建立後再綁）。"""
        self._runtime = runtime

    async def query(self, spec: QuerySpec) -> AdapterResult:
        if self._runtime is None:
            return AdapterResult(
                status="error", provider=self.provider, tool=spec.tool,
                reason="no CMS runtime bound",
            )
        result = await self._runtime.execute(
            spec.tool,
            spec.args or {},
            confirmed=spec.confirmed,
            timeout=spec.timeout or self._timeout,
            encoding=spec.encoding,
        )
        status = _status_map.get(str(result.get("status", "error")), "error")
        raw = result.get("result")
        return AdapterResult(
            status=status,
            provider=self.provider,
            data=unwrap_cms(raw) if status == "ok" else None,
            raw=raw,
            reason=str(result.get("reason", "")) if status != "ok" else "",
            tool=spec.tool,
        )