"""
App registry: auto-discover apps/*/, expose manifest + dispatcher.

Each app package must define:
  - meta.py with META dict: {id, label, icon, project?, trigger?, is_default?, show_in_menu?, enabled?}
  - handler.py with async handle(payload: str, msg) coroutine

Project namespace:
  meta["project"] 預設 "yillkid"。project = 擁有 {apps + nodes + profile} 的範圍
  （虎科 / 縣府 / 機器人部門 / 俊毓個人 …），不是登入帳號。完整命名 = f"{project}.{id}"；
  目前只有 yillkid、id 撞名直接 raise，避免 silent override。
  project 的 profile（LINE 收件人 / 聯絡人）存在 PG projects 表，見 app/projects/registry.py。
"""
import logging
from importlib import import_module
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[str, object], Awaitable[None]]

DEFAULT_PROJECT = "yillkid"


class App:
    def __init__(self, meta: dict, handle: Handler):
        self.id: str = meta["id"]
        # 向後相容：舊欄位名 owner 仍接受，逐步遷到 project
        self.project: str = meta.get("project", meta.get("owner", DEFAULT_PROJECT))
        self.label: str = meta.get("label", self.id)
        self.icon: str = meta.get("icon", "🔧")
        self.cl_icon: str = meta.get("cl_icon", "Sparkles")  # Lucide icon for Chainlit
        self.trigger: str | None = meta.get("trigger")
        self.is_default: bool = bool(meta.get("is_default", False))
        self.show_in_menu: bool = bool(meta.get("show_in_menu", True))
        self.enabled: bool = bool(meta.get("enabled", True))
        self.description: str = meta.get("description", "")
        self.handle: Handler = handle

    @property
    def full_id(self) -> str:
        return f"{self.project}.{self.id}"


_APPS: dict[str, App] = {}
_DEFAULT: App | None = None


def discover() -> dict[str, App]:
    global _APPS, _DEFAULT
    if _APPS:
        return _APPS

    apps_dir = Path(__file__).parent
    for sub in sorted(apps_dir.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
            continue
        try:
            meta = import_module(f"app.apps.{sub.name}.meta").META
            handle = import_module(f"app.apps.{sub.name}.handler").handle
            app = App(meta, handle)
            if app.id in _APPS:
                existing = _APPS[app.id]
                raise RuntimeError(
                    f"App id collision: '{app.id}' from project='{app.project}' conflicts with "
                    f"existing project='{existing.project}'. Rename one, or switch dispatch to "
                    f"full_id (<project>.<id>) form."
                )
            _APPS[app.id] = app
            if app.is_default:
                _DEFAULT = app
            logger.info(
                "Loaded app: %s (project=%s, trigger=%s, default=%s)",
                app.id, app.project, app.trigger, app.is_default,
            )
        except Exception as e:
            logger.exception("Failed to load app '%s': %s", sub.name, e)

    if _DEFAULT is None and _APPS:
        _DEFAULT = next(iter(_APPS.values()))
        logger.warning("No is_default app, using first: %s", _DEFAULT.id)
    return _APPS


def menu_apps() -> list[App]:
    """會出現在工具選單的 app（也給 Action 按鈕用）。"""
    discover()
    return [
        a for a in _APPS.values()
        if a.show_in_menu and a.enabled and not a.is_default
    ]


def chainlit_commands() -> list[dict]:
    """CommandDict list for cl.context.emitter.set_commands()."""
    return [
        {
            "id": a.id,
            "description": a.label,
            "icon": a.cl_icon,
            "persistent": True,
        }
        for a in menu_apps()
    ]


def get_by_id(app_id: str) -> App | None:
    discover()
    return _APPS.get(app_id)


def default_app() -> App | None:
    discover()
    return _DEFAULT


# 平台內建 project — 通用 app（chat / search …）放這，全 project 可見
CORE_PROJECT = "core"


def apps_for_project(project: str) -> list[App]:
    """某個 project 看得到的 app = 自己的 + core 的。

    給未來 project-aware 的 surface 用（機器人 / 多租戶 web）。
    目前 webchat 仍走 chainlit_commands() 顯示全部，不依賴這個。
    """
    discover()
    return [
        a for a in _APPS.values()
        if a.project == project or a.project == CORE_PROJECT
    ]
