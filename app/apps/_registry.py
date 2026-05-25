"""
App registry: auto-discover apps/*/, expose manifest + dispatcher.

Each app package must define:
  - meta.py with META dict: {id, label, icon, owner?, trigger?, is_default?, show_in_menu?, enabled?}
  - handler.py with async handle(payload: str, msg) coroutine

Owner namespace:
  meta["owner"] 預設 "yillkid"。未來其他 owner（虎科 / 縣府 / …）的 apps 進來時必須
  自己宣告 owner。完整命名 = f"{owner}.{id}"；目前只有 yillkid、id 撞名直接 raise，
  避免 silent override。
"""
import logging
from importlib import import_module
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[str, object], Awaitable[None]]

DEFAULT_OWNER = "yillkid"


class App:
    def __init__(self, meta: dict, handle: Handler):
        self.id: str = meta["id"]
        self.owner: str = meta.get("owner", DEFAULT_OWNER)
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
        return f"{self.owner}.{self.id}"


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
                    f"App id collision: '{app.id}' from owner='{app.owner}' conflicts with "
                    f"existing owner='{existing.owner}'. Rename one, or switch dispatch to "
                    f"full_id (<owner>.<id>) form."
                )
            _APPS[app.id] = app
            if app.is_default:
                _DEFAULT = app
            logger.info(
                "Loaded app: %s (owner=%s, trigger=%s, default=%s)",
                app.id, app.owner, app.trigger, app.is_default,
            )
        except Exception as e:
            logger.exception("Failed to load app '%s': %s", sub.name, e)

    if _DEFAULT is None and _APPS:
        _DEFAULT = next(iter(_APPS.values()))
        logger.warning("No is_default app, using first: %s", _DEFAULT.id)
    return _APPS


def chainlit_commands() -> list[dict]:
    """CommandDict list for cl.context.emitter.set_commands()."""
    discover()
    return [
        {
            "id": a.id,
            "description": a.label,
            "icon": a.cl_icon,
            "persistent": True,
        }
        for a in _APPS.values()
        if a.show_in_menu and a.enabled and not a.is_default
    ]


def get_by_id(app_id: str) -> App | None:
    discover()
    return _APPS.get(app_id)


def default_app() -> App | None:
    discover()
    return _DEFAULT
