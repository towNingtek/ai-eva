"""法規知識庫（#112）—— 薄介面，語料邏輯全在 app/regulations/。

治理閘門：上傳只到「待審核」，管理者按下啟用才進判定分母。啟用時才就地抽
條文與管制條目（唯一在 runtime 呼叫 LLM 的 ingest 路徑），抽完才真的能被引用。
"""
import hashlib
import logging
from pathlib import Path

import chainlit as cl

from app.regulations import ingest, registry
from app.settings import ROOT

logger = logging.getLogger(__name__)


def _source_label(row: dict) -> str:
    """法規清單「來源」欄的顯示值（#109）。

    這一欄要回答的是「這筆是內建的還是有人上傳的」，不需要完整信箱。
    2026-08-30 之前直接顯示 uploaded_by，於是期中報告的截圖裡出現了
    真實個人信箱，並隨素材上到公開圖床。

    遮成 local-part@… ——「誰放的」還看得出來（同一個人前後對得起來），
    但不再是可直接使用的聯絡方式。完整值仍在資料庫，管理者查得到。
    """
    if row.get("origin") == "manifest":
        return "repo"
    who = (row.get("uploaded_by") or "").strip()
    if not who:
        return "上傳"
    return f"{who.split('@')[0]}@…" if "@" in who else who

logger = logging.getLogger(__name__)

UPLOAD_DIR = ROOT / "data" / "regulations" / "uploads"
_CATEGORIES = ("農村再生", "鄉村地區", "都市地區")


def _status_text(s: dict) -> str:
    by_cat = "　".join(f"{k} {v}" for k, v in (s.get("by_category") or {}).items())
    lines = [
        "## 📚 法規知識庫",
        "",
        f"**語料庫**　{s.get('active', 0)} 部生效　·　{s.get('articles', 0)} 條文　·　"
        f"{s.get('controls', 0)} 條管制　·　{len(s.get('domains') or [])} 個法領域",
        f"**分類**　{by_cat or '（無）'}",
    ]
    if s.get("no_fulltext"):
        lines.append(f"**全文未取得**　{s['no_fulltext']} 部（不納入判定，報告會列在「需補語料」）")
    if s.get("pending"):
        lines.append(f"**待審核**　{s['pending']} 部（上傳後尚未啟用，**不影響檢核結果**）")
    lines += ["", "上傳法規 PDF 請直接把檔案拖進對話框。上傳的法規一律先進待審核，"
              "由管理者確認後才會納入檢核。"]
    return "\n".join(lines)


async def _list_table() -> str:
    rows = await registry.list_regulations()
    if not rows:
        return "_語料庫是空的。_"
    icon = {"active": "✅", "pending": "⏳", "no_fulltext": "📭", "superseded": "🗄️"}
    out = ["| | 法規 | 類別 | 版本 | 條文 | 管制 | 來源 |", "|---|---|---|---|--:|--:|---|"]
    for r in rows:
        out.append(f"| {icon.get(r['status'], '•')} | {r['name']} | {r['category']} "
                   f"| {r['version'] or '—'} | {r['articles']} | {r['controls']} "
                   f"| {_source_label(r)} |")
    return "\n".join(out)


async def _ingest_uploads(msg: cl.Message) -> int:
    """收 PDF → 存檔 → 建 pending 紀錄。

    這裡**不做**切條文與抽管制條目：那要跑 LLM、要進版控，是建置時的事
    （app/regulations/ingest.py）。runtime 只負責收件與留痕。
    """
    pdfs = [e for e in (msg.elements or [])
            if (e.name or "").lower().endswith(".pdf") and getattr(e, "path", None)]
    if not pdfs:
        return 0
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    user = getattr(cl.user_session.get("user"), "identifier", "") or "unknown"
    ok = 0
    for e in pdfs:
        data = Path(e.path).read_bytes()
        name = Path(e.name).stem
        dest = UPLOAD_DIR / e.name
        dest.write_bytes(data)
        reg_id = await registry.add_upload(
            name, _CATEGORIES[0], source_file=str(dest.name),
            sha256=hashlib.sha256(data).hexdigest(), chars=0, uploaded_by=user)
        if reg_id:
            ok += 1
    return ok


def _pending_actions(rows: list[dict]) -> list[cl.Action]:
    actions: list[cl.Action] = []
    for r in rows:
        actions.append(cl.Action(name="reg_activate", payload={"id": r["id"]},
                                 label=f"啟用 {r['name'][:18]}"))
        actions.append(cl.Action(name="reg_delete", payload={"id": r["id"]},
                                 label=f"刪除 {r['name'][:18]}"))
    return actions


@cl.action_callback("reg_activate")
async def reg_activate(action: cl.Action) -> None:
    """審核通過 → 就地抽條文與管制條目 → 進判定分母。

    抽取要花時間（一部法規約 10~90 秒），所以有進度顯示；抽不出東西的
    （掃描件、不是法規全文）不給啟用，標成 no_fulltext 讓報告誠實列出。
    """
    reg_id = int((action.payload or {}).get("id") or 0)
    reg = await registry.get_regulation(reg_id)
    if not reg:
        await cl.Message(content="⚠️ 找不到這部法規（可能已被刪除）。").send()
        return
    if reg["status"] != "pending":
        await cl.Message(content=f"「{reg['name']}」目前狀態是 `{reg['status']}`，不需要啟用。").send()
        return

    pdf = UPLOAD_DIR / (reg["source_file"] or "")
    if not pdf.exists():
        await cl.Message(content=f"⚠️ 找不到檔案 `{reg['source_file']}`，無法啟用。").send()
        return

    user = getattr(cl.user_session.get("user"), "identifier", "") or "unknown"
    async with cl.Step(name=f"建立索引：{reg['name']}", type="tool") as step:
        result = await ingest.ingest_uploaded_pdf(pdf, reg["name"])
        step.output = (f"{len(result['articles'])} 條文 → {len(result['controls'])} 條管制"
                       if not result.get("error") else f"失敗：{result['error']}")

    if result.get("no_fulltext") or not result["controls"]:
        await registry.mark_no_fulltext(reg_id)
        await cl.Message(
            content=f"⚠️ 「{reg['name']}」抽不出可用的管制條目"
                    f"（{result.get('error') or '內容為空'}），已標為**全文未取得**、不納入判定。\n\n"
                    "掃描件需要先 OCR；若這份不是法規全文，請改上傳正式條文。"
        ).send()
        return

    await registry.replace_content(reg_id, result["articles"], result["controls"],
                                   extracted_by=result["controls"][0].get("extracted_by", ""))
    if result.get("version"):
        await registry.set_version(reg_id, result["version"])
    ok = await registry.activate_regulation(reg_id, user)
    if not ok:
        await cl.Message(content="⚠️ 啟用失敗（狀態已被別人改過），請重新開啟面板確認。").send()
        return

    clashes = await registry.name_clashes(reg["name"], reg_id)
    warn = ""
    if clashes:
        warn = ("\n\n⚠️ 語料庫裡已經有同名法規（"
                + "、".join(f"{c['name']}／{c['origin']}／{c['status']}" for c in clashes[:3])
                + "）。兩份都生效會讓同一條文重複計入判定，建議刪掉其中一份。")

    await cl.Message(
        content=f"✅ 「{reg['name']}」已啟用並建立索引："
                f"**{len(result['articles'])}** 條文 → **{len(result['controls'])}** 條管制條目。\n\n"
                f"下次執行法規檢核時就會納入比對。{warn}"
    ).send()
    await handle("", cl.Message(content="法規知識庫"))


@cl.action_callback("reg_delete")
async def reg_delete(action: cl.Action) -> None:
    reg_id = int((action.payload or {}).get("id") or 0)
    reg = await registry.get_regulation(reg_id)
    if not reg:
        await cl.Message(content="⚠️ 找不到這部法規。").send()
        return
    if reg["origin"] != "upload":
        await cl.Message(
            content=f"「{reg['name']}」來自版控語料（MANIFEST），不能從介面刪除。"
                    "要移除請改 repo 的 corpus 再重新部署。"
        ).send()
        return
    await registry.delete_regulation(reg_id)
    await cl.Message(content=f"🗑️ 已刪除上傳的「{reg['name']}」。").send()
    await handle("", cl.Message(content="法規知識庫"))


async def handle(payload: str, msg: cl.Message) -> None:
    uploaded = await _ingest_uploads(msg)
    stats = await registry.corpus_stats()
    parts = [_status_text(stats), "", "### 法規清單", "", await _list_table()]
    if uploaded:
        parts.insert(1, f"\n✅ 已收到 **{uploaded}** 份上傳的法規，狀態為「待審核」。"
                        f"未經啟用前不會影響檢核結果。\n")

    pending = await registry.list_regulations(status=registry.STATUS_PENDING)
    if pending:
        parts += ["", "### 待審核（按「啟用」才會納入檢核）", "",
                  *(f"- **{r['name']}**（{r['category']}・上傳者 {_source_label(r)}）"
                    for r in pending),
                  "", "啟用時會就地建立索引（抽條文與管制條目），一部法規約需 10~90 秒。"]

    # 不掛 parent_id：子訊息會被收合，而且從按鈕（Action）進來時 msg 是我們自己造的、
    # 根本沒送出過，掛上去等於指向不存在的父訊息 → 整段輸出看不見
    await cl.Message(content="\n".join(parts),
                     actions=_pending_actions(pending) if pending else []).send()
