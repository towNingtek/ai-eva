"""Module 執行環境與契約（#129）。

ModuleContext 是 module 的唯一「插座」——把執行環境（project、資料後端 adapter、
LLM factory…）注入 module，module 本體不自己抓環境、不 import DB。

好處：
- 可測試：餵 StubDataSource + 假 LLM 就能驗 module 邏輯，不必碰真實 CMS/DB。
- 可換後端：同一個 module 換 ctx.data 就好。
- 可做 project-aware：ctx.project 決定要綁哪個 adapter / 哪條 key。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.adapters.base import DataSource


@dataclass
class ModuleContext:
    """一次 module 執行的注入環境。"""

    project: str                       # 登入者所屬 project（決定可見性/收件人）
    data: DataSource                   # 資料後端 adapter（module 只認這個）
    action: str = ""                   # 本次要執行的動作（module 的 action name）
    make_llm: Optional[Callable[..., Any]] = None   # 造 LLM 的 factory（可選注入）
    api_key: Optional[str] = None      # LiteLLM virtual key
    llm_user: Optional[str] = None     # 計量 user
    meta: dict = field(default_factory=dict)   # 額外環境（surface 專用資訊）

    @property
    def llm(self) -> Any:
        """便利：有 make_llm 就用，否則 None（module 要自行處理無 LLM 的情況）。"""
        if self.make_llm is None:
            return None
        return self.make_llm(api_key=self.api_key, user=self.llm_user, streaming=False)


def result(ok: bool, reply: str, data: dict | None = None, *, error: str = "") -> dict:
    """module handler 標準回傳 {ok, reply, data, error}。"""
    return {"ok": ok, "reply": reply, "data": data or {}, "error": error or ""}