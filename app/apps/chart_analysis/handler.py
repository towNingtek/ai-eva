import chainlit as cl


def _element():
    element = cl.CustomElement(
        name="ChartAnalysis",
        display="inline",
        props={
            "year": "2025",
            "district": "",
            "sdgs": ["sdg9", "sdg12"],
            "items": [],
            "totalBudget": 0,
            "totalProjects": 0,
            "loading": False,
            "error": "",
        },
    )
    cl.user_session.set("chart_element", element)
    return element


async def handle(payload: str, msg: cl.Message) -> None:
    element = _element()
    await cl.Message(
        content="📊 請設定條件後生成 SDG 投入圖表，或匯出成 PDF / PNG。數值來自 CMS 專案資料。",
        elements=[element],
        parent_id=getattr(msg, "id", None),
    ).send()


async def open_panel() -> None:
    await handle("", cl.Message(content="圖表分析"))
