"""Adapter registry — provider 名稱 → 實作（#128）。

新增後端：註冊一行 + 實作 DataSource 介面，module 不用動。
"""
from __future__ import annotations

from typing import Any

from app.adapters.base import DataSource
from app.adapters.cms import CMSDataSource
from app.adapters.stub import StubDataSource

REGISTRY: dict[str, type] = {
    "tplanet-cms": CMSDataSource,
    "stub": StubDataSource,
}


def register(provider: str, cls: type) -> None:
    REGISTRY[provider] = cls


def get_adapter_cls(provider: str) -> type | None:
    return REGISTRY.get(provider)


def create(provider: str, *args: Any, **kwargs: Any) -> DataSource | None:
    """依 provider 名字建實例。沒註冊回 None。"""
    cls = get_adapter_cls(provider)
    if cls is None:
        return None
    return cls(*args, **kwargs)