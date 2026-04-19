"""
App registry: auto-discover apps/*/, expose manifest + dispatcher.

Each app package must define:
  - meta.py with META dict: {id, label, icon, trigger?, is_default?, show_in_menu?, enabled?}
  - handler.py with async handle(payload: str, msg) coroutine
"""
import logging
from importlib import import_module
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[str, object], Awaitable[None]]


class App:
    def __init__(self, meta: dict, handle: Handler):
        self.id: str = meta["id"]
        self.label: str = meta.get("label", self.id)
        self.icon: str = meta.get("icon", "🔧")
        self.trigger: str | None = meta.get("trigger")
        self.is_default: bool = bool(meta.get("is_default", False))
        self.show_in_menu: bool = bool(meta.get("show_in_menu", True))
        self.enabled: bool = bool(meta.get("enabled", True))
        self.description: str = meta.get("description", "")
        self.handle: Handler = handle


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
            _APPS[app.id] = app
            if app.is_default:
                _DEFAULT = app
            logger.info("Loaded app: %s (trigger=%s, default=%s)", app.id, app.trigger, app.is_default)
        except Exception as e:
            logger.exception("Failed to load app '%s': %s", sub.name, e)

    if _DEFAULT is None and _APPS:
        _DEFAULT = next(iter(_APPS.values()))
        logger.warning("No is_default app, using first: %s", _DEFAULT.id)
    return _APPS


def manifest() -> list[dict]:
    """For frontend /public/apps.json — menu items only."""
    discover()
    return [
        {
            "id": a.id,
            "label": a.label,
            "icon": a.icon,
            "trigger": a.trigger,
            "description": a.description,
            "enabled": a.enabled,
        }
        for a in _APPS.values()
        if a.show_in_menu and a.trigger
    ]


def dispatch(message: str) -> tuple[App, str]:
    """Match message against triggers; return (app, payload)."""
    discover()
    for a in _APPS.values():
        if a.trigger and message.startswith(a.trigger):
            payload = message[len(a.trigger):].strip()
            return a, payload
    return _DEFAULT, message
