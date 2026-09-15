"""Module registry — 自動發現 app/modules/*/（#84 / #129）。

module ≠ app：module 不碰 Chainlit UI，只吃 DataSource + ModuleContext，
可被 app 呼叫、可單元測試、可換後端。

啟用：`enabled_modules` 在 projects.metadata（跟 enabled_apps 同模式）。
未設 / None = 全開（向後相容、default 不擋任何 module）。
core（平台內建）project 的 module 永遠可見。
"""
from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Optional

from app.modules.base import ModuleContext, result

logger = logging.getLogger(__name__)


class Module:
    """Module 元資料。"""

    def __init__(self, meta: dict, handle: Callable[..., Any]):
        self.id: str = meta["id"]
        self.label: str = meta.get("label", self.id)
        self.project: str = meta.get("project", "core")
        self.description: str = meta.get("description", "")
        # 每個 module 可宣告支援的 action（list[str]）；空白/未設=不限。
        self.actions: list[str] = meta.get("actions") or []
        self._handle = handle

    async def handle(self, ctx: ModuleContext, payload: dict) -> dict:
        return await self._handle(ctx, payload)

    def supports(self, action: str) -> bool:
        if not self.actions:
            return True
        return action in self.actions


_MODULES: dict[str, Module] = {}


def discover() -> dict[str, Module]:
    global _MODULES
    if _MODULES:
        return _MODULES

    modules_dir = Path(__file__).parent

    def _iter_meta_dirs(root: Path):
        """掃 meta.py：支援一層（chart/）與兩層（sustainability/sdg/）巢狀。"""
        for path in sorted(root.glob("**/meta.py")):
            if any(part.startswith("_") or part.startswith(".") for part in path.parts):
                continue
            yield path.parent.relative_to(root)

    for rel in sorted(_iter_meta_dirs(modules_dir)):
        try:
            sub = Path(rel)
            pkg = ".".join(("app", "modules") + tuple(sub.parts))
            meta_mod = import_module(f"{pkg}.meta")
            meta = getattr(meta_mod, "META")
            handle_mod = import_module(f"{pkg}.handler")
            handle_fn = getattr(handle_mod, "handle")
            mod = Module(meta, handle_fn)
            if mod.id in _MODULES:
                raise RuntimeError(f"Module id collision: '{mod.id}'")
            _MODULES[mod.id] = mod
            logger.info("Loaded module: %s (project=%s)", mod.id, mod.project)
        except Exception as e:
            logger.exception("Failed to load module '%s': %s", rel, e)
    return _MODULES


CORE_PROJECT = "core"


def modules_for_project(
    project: str, enabled: set[str] | None = None
) -> list[Module]:
    """某個 project 看得到的 module = 自己的 + core 的（再過 enabled_modules）。

    enabled=None → 全開；enabled=set → 只留有在 set 裡 / project=core 的。
    """
    discover()
    candidates = [m for m in _MODULES.values() if m.project == project or m.project == CORE_PROJECT]
    if enabled is None:
        return list(candidates)
    return [m for m in candidates if m.project == CORE_PROJECT or m.id in enabled]


def get_by_id(module_id: str) -> Module | None:
    discover()
    return _MODULES.get(module_id)


async def invoke(module_id: str, ctx: ModuleContext, payload: dict) -> dict:
    """定位 module → 執行 action（from ctx.action）。找不到回 error。"""
    mod = get_by_id(module_id)
    if mod is None:
        return result(False, f"找不到 module：{module_id}")
    if ctx.action and not mod.supports(ctx.action):
        return result(False, f"module {module_id} 不支援 action：{ctx.action}")
    return await mod.handle(ctx, payload)