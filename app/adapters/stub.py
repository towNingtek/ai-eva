"""Stub adapter — 假資料後端（#128 / 測試用）。

拿固定資料回，作用是證明「同一個 module 換後端，邏輯不用動」：
把 chart module 在新接好的 CMSDataSource 與 StubDataSource 上各跑一次，輸出應一致。

資料格式：{"<tool>": <已剝信封的 data>}；未登記的 tool 回 denied。
"""
from __future__ import annotations

from typing import Any

from app.adapters.base import AdapterResult, QuerySpec


class StubDataSource:
    provider = "stub"

    def __init__(self, data: dict | None = None, *, fail: set[str] | None = None):
        self._data = dict(data or {})
        self._fail = set(fail or [])
        self.calls: list[QuerySpec] = []   # 記錄呼叫，測試斷言用

    async def query(self, spec: QuerySpec) -> AdapterResult:
        self.calls.append(spec)
        if spec.tool in self._fail:
            return AdapterResult(
                status="error", provider=self.provider, tool=spec.tool, reason="stub forced error",
            )
        if spec.tool not in self._data:
            return AdapterResult(
                status="denied", provider=self.provider, tool=spec.tool,
                reason=f"tool '{spec.tool}' not in stub data",
            )
        return AdapterResult(
            status="ok", provider=self.provider, tool=spec.tool, data=self._data[spec.tool],
        )