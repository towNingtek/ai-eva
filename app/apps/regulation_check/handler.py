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


# get_project_info 是**延遲綁定**（每次一個小 JSON 往返），走 Cloudflare tunnel 時
# 延遲被放大。25 個專案在 8 併發要跑 4 輪、20 併發只要 2 輪。上限仍留著避免打爆 CMS。
_PROJECT_FETCH_CONCURRENCY = 20
_PROJECTS_CACHE_KEY = "regcheck_projects"


async def _my_projects(runtime, *, refresh: bool = False) -> list[dict]:
    """列出可管理的計畫書，**同一個 session 只抓一次**。

    CMS 的 list_scoped 只回 uuid，名稱要逐一問 —— 二十幾份專案就是 1+N 次呼叫。
    這段卡在使用者看到任何東西之前，走 Cloudflare tunnel 時延遲被放大到會超時
    （實測：打 localhost 十幾秒、打公開網址超過兩分鐘）。清單在一次對話裡幾乎
    不會變，快取起來即可；真的變了就重開工具（或傳 refresh=True）。
    """
    if not refresh:
        cached = cl.user_session.get(_PROJECTS_CACHE_KEY)
        if cached:
            return cached

    res = await runtime.execute("list_my_projects", {})
    if res.get("status") != "ok":
        return []
    data = _unwrap(res)
    uuids = (data.get("projects") or []) if isinstance(data, dict) else []
    sem = asyncio.Semaphore(_PROJECT_FETCH_CONCURRENCY)

    async def one(uuid: str) -> dict | None:
        async with sem:
            detail = await runtime.execute("get_project_info", {"uuid": uuid})
        if detail.get("status") != "ok":
            return None
        info = _unwrap(detail)
        return {"uuid": uuid, "name": info["name"], "info": info} if info.get("name") else None

    projects = [p for p in await asyncio.gather(*(one(u) for u in uuids)) if p]
    cl.user_session.set(_PROJECTS_CACHE_KEY, projects)
    return projects


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
    """讓使用者挑一份計畫書。

    比對順序：完整名稱 → 唯一的部分比對 → 編號。
    編號放最後而且**不當主要指引**：清單在 Chainlit 是 markdown 有序列表，
    前端渲染後畫面上看不到我們寫的數字，叫使用者「回覆編號」等於叫他猜。
    """
    if len(projects) == 1:
        return projects[0]

    listing = "\n".join(f"{i}. {p['name']}" for i, p in enumerate(projects, 1))
    prompt = (f"找到 **{len(projects)}** 份你可管理的計畫書。\n\n"
              f"{listing}\n\n"
              "請直接回覆計畫名稱（打得出關鍵字就行，例如「晴耕」）。")

    for attempt in range(3):
        ans = await cl.AskUserMessage(content=prompt, timeout=300).send()
        choice = ((ans or {}).get("output") or "").strip()
        if not choice:
            return None

        exact = next((p for p in projects if p["name"] == choice), None)
        if exact:
            return exact

        hits = [p for p in projects if choice and choice in p["name"]]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            names = "\n".join(f"- {p['name']}" for p in hits[:10])
            prompt = (f"「{choice}」對到 {len(hits)} 份，請講得更精確一點：\n\n{names}")
            continue

        if choice.isdigit() and 1 <= int(choice) <= len(projects):
            return projects[int(choice) - 1]

        prompt = (f"找不到含「{choice}」的計畫書。請從下面挑一個關鍵字回覆：\n\n{listing}")

    return None


async def handle(payload: str, msg: cl.Message) -> None:
    runtime = cl.user_session.get("cms_runtime")
    if not runtime:
        await cl.Message(content="⚠️ 請先從 CMS 重新進入 AI-Eva（法規檢核需要讀取你的專案）。").send()
        return

    await cl.Message(
        content="## ⚖️ 法規檢核\n\n"
                "拿你的計畫書逐條比對法規語料，產出風險報告。流程：\n\n"
                "1. 挑一份計畫書\n"
                "2. 逐條判定（約一分鐘，會顯示進度）\n"
                "3. 產出 5 區塊報告，可下載 `.md`\n\n"
                "正在讀取你可管理的計畫書…"
    ).send()

    # 先出聲再做慢動作：CMS 的 list_scoped 只回 uuid，名稱要逐一問，
    # 二十幾個專案就算並行也要好幾秒。不先回話的話使用者只看到一片空白，
    # 不知道是在跑還是點壞了。
    async with cl.Step(name="讀取你可管理的計畫書", type="tool") as step:
        projects = await _my_projects(runtime)
        step.output = f"找到 {len(projects)} 份"

    if not projects:
        await cl.Message(
            content="⚠️ 沒有找到你可管理的計畫書。\n\n"
                    "法規檢核是對「你在 CMS 底下的專案」做比對；"
                    "如果你確定有專案，可能是登入的角色沒有管理權限。"
        ).send()
        return

    picked = await _pick_project(projects)
    if not picked:
        await cl.Message(
            content="沒有挑到計畫書，這次就先停在這裡。要重跑的話，"
                    "點輸入框旁的 `...` → 選「法規檢核」→ 按送出。"
        ).send()
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
        # ai-eva#110：判定模型可由 CMS 在簽 SSO token 時指定（目前只給 e2e 帳號）。
        # 沒有這個 claim 就用 standard.yaml 設定的正式模型 —— 一般使用者不受影響。
        judge_model = cl.user_session.get("judge_model")
        result = await judge.run_check(plan, DEFAULT_CATEGORY,
                                       model=judge_model, on_progress=on_progress)
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
               f"逐條評估 {cov['evaluated']} 條管制條目，涵蓋 {len(cov['domains'])} 個法領域。"
               + (f"\n判定模型：{judge_model}" if judge_model else ""))

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
