"""法規知識庫（#112）—— 薄介面，語料邏輯全在 app/regulations/。"""
import hashlib
import logging
from pathlib import Path

import chainlit as cl

from app.regulations import registry
from app.settings import ROOT

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
                   f"| {'repo' if r['origin'] == 'manifest' else (r['uploaded_by'] or '上傳')} |")
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


async def handle(payload: str, msg: cl.Message) -> None:
    uploaded = await _ingest_uploads(msg)
    stats = await registry.corpus_stats()
    parts = [_status_text(stats), "", "### 法規清單", "", await _list_table()]
    if uploaded:
        parts.insert(1, f"\n✅ 已收到 **{uploaded}** 份上傳的法規，狀態為「待審核」。"
                        f"未經啟用前不會影響檢核結果。\n")
    # 不掛 parent_id：子訊息會被收合，而且從按鈕（Action）進來時 msg 是我們自己造的、
    # 根本沒送出過，掛上去等於指向不存在的父訊息 → 整段輸出看不見
    await cl.Message(content="\n".join(parts)).send()
