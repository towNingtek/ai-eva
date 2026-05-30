"""Tool registry — capability → LLM-facing tool（framework primitive，issue #25 第 4 點）。

dispatch 把 device intent 交給 LLM 做 function-calling 時，只把「該 project 真的有 node
能執行」的 capability 轉成 tool schema 餵給模型（tool 動態長出來，模型不會叫出沒硬體支援的能力）。

每個 capability 登記：
  - schema       OpenAI function 格式（給 LLM 看的 tool 定義）
  - tool name    schema.function.name；LLM 回 tool_call 時用這個名字反查 capability

新增能力 = 在 _CATALOG 加一筆，dispatch 不用動。
這是 framework primitive：tool「機制」在這裡；「哪些 tool 對哪個 project 可見」由
dispatch 依 node registry 決定（策略），符合 core=primitive / app=strategy 分工。
"""
from __future__ import annotations

_CATALOG: dict[str, dict] = {
    "camera.capture": {
        "schema": {
            "type": "function",
            "function": {
                "name": "take_photo",
                "description": (
                    "用裝置上的相機拍照。當使用者要求拍照、自拍、拍一張、"
                    "或想看某個方向現在的畫面時呼叫。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lens": {
                            "type": "string",
                            "enum": ["front", "rear", "both"],
                            "description": (
                                "front=前鏡頭（對著使用者/自拍）、rear=後鏡頭（對著前方環境）、"
                                "both=兩個都拍。沒特別指定就用 both。"
                            ),
                        }
                    },
                },
            },
        },
    },
}

# tool function name → capability（反查）
_TOOL_TO_CAP: dict[str, str] = {
    spec["schema"]["function"]["name"]: cap for cap, spec in _CATALOG.items()
}


def tools_for_capabilities(capabilities: list[str]) -> list[dict]:
    """一組 capability → LLM tool schema 清單（只收目錄裡有登記的）。"""
    seen = []
    out = []
    for cap in capabilities:
        if cap in _CATALOG and cap not in seen:
            seen.append(cap)
            out.append(_CATALOG[cap]["schema"])
    return out


def capability_for_tool(tool_name: str) -> str | None:
    """LLM 回的 tool_call name → capability。"""
    return _TOOL_TO_CAP.get(tool_name)
