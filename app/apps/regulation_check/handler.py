"""法規檢核（#111）—— 薄介面，判定與報告在 app/regulations/。

流程：選專案 → 抓計畫書 → 逐條判定（進度顯示）→ 5 區塊報告 → 下載 + LINE 推播。

專案資料一律走 CMS **現成的** manifest 工具（list_my_projects / get_project_info）。
ai-eva 只消費 manifest，不擴充它 —— 新增 CMS 工具要改 tplanet 那個 repo。
"""
import asyncio
import html
import logging
import re
from datetime import datetime
from pathlib import Path

import chainlit as cl

from app.projects import registry as project_registry
from app.regulations import judge, report
from app.settings import ROOT
from app.surfaces import push

logger = logging.getLogger(__name__)

REPORT_DIR = ROOT / "data" / "regulations" / "reports"
YUNLIN_PROJECT = "yunlin"
# 計畫類別暫以農村再生為預設（雲林本期標的）。之後由計畫欄位或使用者選擇決定。
DEFAULT_CATEGORY = "農村再生"


def _unwrap(result: dict) -> dict:
    inner = result.get("result", {})
    return inner.get("data", inner) if isinstance(inner, dict) else {}


async def _my_projects(runtime) -> list[dict]:
    res = await runtime.execute("list_my_projects", {})
    if res.get("status") != "ok":
        return []
    data = _unwrap(res)
    out = []
    for uuid in (data.get("projects") or []) if isinstance(data, dict) else []:
        detail = await runtime.execute("get_project_info", {"uuid": uuid})
        if detail.get("status") != "ok":
            continue
        info = _unwrap(detail)
        if info.get("name"):
            out.append({"uuid": uuid, "name": info["name"], "info": info})
    return out


def _plan_text(info: dict) -> str:
    """計畫書載體 = 專案 philosophy 欄（YAML standard.subject）。HTML 洗掉。"""
    raw = info.get("philosophy") or ""
    text = re.sub(r"<br\s*/?>", "\n", raw)
    text = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)          # &nbsp; / &amp; 之類進了 judge 會變雜訊
    text = text.replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def _pick_project(projects: list[dict]) -> dict | None:
    if len(projects) == 1:
        return projects[0]
    listing = "\n".join(f"{i}. {p['name']}" for i, p in enumerate(projects, 1))
    ans = await cl.AskUserMessage(
        content=f"要檢核哪一份計畫書？請回覆編號或完整名稱：\n\n{listing}",
        timeout=180,
    ).send()
    choice = ((ans or {}).get("output") or "").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(projects):
        return projects[int(choice) - 1]
    return next((p for p in projects if p["name"] == choice), None)


async def handle(payload: str, msg: cl.Message) -> None:
    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await cl.Message(content="⚠️ 請先從 CMS 重新進入 AI-Eva（法規檢核需要讀取你的專案）。").send()
        return

    projects = await _my_projects(runtime)
    if not projects:
        await cl.Message(content="⚠️ 沒有找到你可管理的專案。").send()
        return
    picked = await _pick_project(projects)
    if not picked:
        await cl.Message(content="沒有對應到專案，請重新點一次「法規檢核」。").send()
        return

    plan = _plan_text(picked["info"])
    if len(plan) < 100:
        await cl.Message(content=f"⚠️「{picked['name']}」的計畫理念欄位太短（{len(plan)} 字），"
                                 f"無法檢核。請先在 CMS 補上計畫書內容。").send()
        return

    await cl.Message(
        content=f"⚖️ 開始檢核「**{picked['name']}**」（{len(plan)} 字）。\n"
                f"整份計畫逐條比對，需要一到兩分鐘；完成後會推播通知，你可以先去忙別的。"
    ).send()

    async def on_progress(ev: dict) -> None:
        """每個法領域跑完就長一列出來 —— 使用者看得到進度，
        Playwright 也斷言得到「10 個法領域都出現且都完成」（#111 KPI）。"""
        async with cl.Step(name=f"{ev['domain']}（{ev['total']} 條）", type="tool") as step:
            step.output = f"觸發 {ev['hit']} 條 · {ev['elapsed']:.0f}s"

    try:
        result = await judge.run_check(plan, DEFAULT_CATEGORY, on_progress=on_progress)
    except Exception as e:  # noqa: BLE001
        logger.exception("法規檢核失敗")
        await cl.Message(content=f"⚠️ 檢核失敗（{type(e).__name__}）。請稍後再試。").send()
        return

    md = report.build(result, plan_name=picked["name"], plan_uuid=picked["uuid"])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"法規檢核報告_{picked['uuid']}_{stamp}.md"
    path.write_text(md, encoding="utf-8")

    hit = [f for f in result["findings"] if f["verdict"] == "觸發"]
    def _arts(items): return len({(f["regulation"], f["article_no"]) for f in items})
    violations = _arts([f for f in hit if f["section"] == "違規風險"])
    reminders = _arts([f for f in hit if f["section"] == "合規提醒"])
    gaps = _arts([f for f in result["findings"] if f["verdict"] in ("需補資訊", "需補語料")])
    cov = result["coverage"]

    summary = (f"✅ **{picked['name']}** 檢核完成（{result['elapsed']:.0f} 秒）\n\n"
               f"🔴 違規風險 **{violations}** 條文　🟡 合規提醒 **{reminders}** 條文　"
               f"📚 需補 **{gaps}** 條文\n\n"
               f"逐條評估 {cov['evaluated']} 條管制條目，涵蓋 {len(cov['domains'])} 個法領域。")

    # 結果分兩則送，而且都不掛 parent_id：
    #   1. 子訊息在 Chainlit 會被收合，使用者要展開才看得到（E2E 實測踩到：
    #      報告檔已產生、畫面卻等不到「檢核完成」）
    #   2. 文字先送、附件後送 —— 檔案元素若上傳失敗，至少結論還在，
    #      不會讓跑了一分鐘的檢核整個消失
    await cl.Message(content=summary).send()
    try:
        await cl.Message(
            content=f"📄 {path.name}",
            # mime 一定要給：不給的話前端算 mime 時對 null 呼叫 startsWith，
            # 整個 React 樹會崩掉卸載（E2E 實測：畫面連先前訊息都消失）
            elements=[cl.File(name=path.name, path=str(path),
                              display="inline", mime="text/markdown")],
        ).send()
    except Exception:  # noqa: BLE001
        logger.exception("報告檔附件送出失敗（報告已存在 %s）", path)
        await cl.Message(content=f"⚠️ 報告已產生但附件送出失敗，檔案位置：`{path}`").send()

    # PUSH：非即時流程的收尾。沒設 LINE 收件人就靜靜跳過（web 上已經看到結果了）。
    profile = await project_registry.get_project(YUNLIN_PROJECT)
    recipient = (profile or {}).get("line_recipient")
    if recipient:
        await push.push_line(
            recipient,
            f"【法規檢核完成】{picked['name']}\n"
            f"違規風險 {violations} 條文 / 合規提醒 {reminders} 條文 / 需補 {gaps} 條文\n"
            f"完整報告請至 AI-Eva 下載。",
            source="regulation-check",
        )
