"""DataSource 介面契約（#128）。

`query()` 是 module ↔ 資料後端的唯一界線。任何 adapter 都要把後端結果
正規化成 `AdapterResult`，module 才不用「認後端」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class QuerySpec:
    """一次資料查詢/動作的標準規格。

    - tool       後端提供的動作名稱（CMS 的 manifest tool / stub 的 key）
    - args       參數 dict（module 依自身 schema 填，不寫死後端欄位）
    - timeout    覆寫預設 HTTP timeout（慢操作如 SROI Google Sheet）
    - encoding   form|json 送法覆寫（同 ToolRuntime.execute；後端特定，module 一般不設）
    - confirmed  是否已人工確認（寫類工具用）
    """
    tool: str
    args: dict = field(default_factory=dict)
    timeout: float | None = None
    encoding: str | None = None
    confirmed: bool = False


@dataclass
class AdapterResult:
    """標準化結果 — module 只需要這一份，不讀後端原始格式。

    - status   ok | denied | need_confirm | error
    - provider 實際回應者的名稱（log / 除錯）
    - data     成功時「剝信封後」的資料（對 CMS = {success,data}.data）
    - raw      原始回傳（保留給需要的人）
    - reason   非成功時的說明
    """
    status: str
    provider: str
    data: Any = None
    raw: Any = None
    reason: str = ""
    tool: str = ""


@runtime_checkable
class DataSource(Protocol):
    """想當「資料後端」就實作這三樣。runtime_checkable 讓 isinstance() 也能查。"""

    provider: str

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    async def query(self, spec: QuerySpec) -> AdapterResult:
        """打一次動作，回標準 AdapterResult。後端錯誤一律轉 status=error，不 raise。"""
        ...


def unwrap_cms(data: Any) -> Any:
    """剝 CMS 的 {success, data} 信封（沿用 copilot._inner 的慣例）。"""
    if isinstance(data, dict):
        inner = data.get("data")
        return inner if isinstance(inner, dict) else data
    return data