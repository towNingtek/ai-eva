"""法規語料 ingest —— 建置時跑一次，產物進版控。

    docker run --rm --network host -v "$PWD:/app" -w /app --env-file .env \
      -e LITELLM_API_BASE=http://localhost:4000/v1 -e LITELLM_API_KEY=$LITELLM_MASTER_KEY \
      ai-eva python -m app.regulations.ingest --model openai-5.4-xiaozhen

流程：corpus/extracted/*.txt → 切條文 → LLM 抽管制條目 → articles.json + negative_list.json

**runtime 不跑這支**。開機只讀 JSON（registry.seed_from_corpus），不呼叫 LLM、不連外網。
語料是判定的分母，必須可版控、可 diff、可追「這條管制是哪個模型在哪一版抽出來的」。

法領域（law_domain）是**每部法規固定**的，寫在下面的 LAW_DOMAIN，不讓 LLM 自由發揮 ——
判定時要按法領域分組平行跑，分組必須穩定，否則覆蓋率報表每次都長不一樣。

抽取結果有 cache（corpus/.cache/），中途掛掉重跑不會重花錢；改 prompt 記得 --no-cache。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

import yaml

from app.core.llm import make_llm

logger = logging.getLogger(__name__)

CORPUS = Path(__file__).parent / "corpus"
CACHE = CORPUS / ".cache"

# 每部法規歸屬的法領域（判定時的平行分組單位）
LAW_DOMAIN: dict[str, str] = {
    # 名稱對齊 YAML 標準 v1 的 coverage.covered（合約宣告的 10 個涵蓋領域），
    # 報告的「涵蓋 N 法領域」才對得上規格書。
    "水土保持法": "水土保持",
    "農業發展條例": "農業發展",
    "農業用地作農業使用認定及核發證明辦法": "農地農用認定",
    "區域計畫法": "區域計畫",
    "區域計畫法施行細則": "區域計畫",
    "國土計畫法": "國土計畫",
    "國土計畫法施行細則": "國土計畫",
    "國土計畫土地使用管制規則（草案）": "國土計畫",
    "環境影響評估法": "環境影響評估",
    "環境影響評估法施行細則": "環境影響評估",
    "非都市土地使用管制規則": "非都市土地使用管制",
    "非都市土地開發影響費徵收辦法": "非都市土地使用管制",
    "非都市土地開發許可審查收費標準": "非都市土地使用管制",
    "非都市土地開發審議作業規範": "開發審議",
    "都市計畫法": "都市計畫",
    "都市計畫法臺灣省施行細則": "都市計畫",
    "農村再生條例": "農村再生",
    "農村再生條例施行細則": "農村再生",
    "農村再生發展區計畫審核及管理監督辦法": "農村再生",
    "農村再生計畫審核作業注意事項": "農村再生",
    "農村再生計畫審核及執行監督辦法": "農村再生",
    "農村再生培根計畫執行注意事項": "農村再生",
    "農村再生政策方針": "農村再生",
    "農村社區辦理訂定社區公約作業方式": "農村再生",
    "都市計畫或國家公園區域內農民集居聚落認定農村活化再生需要作業方式": "農村再生",
    "辦理農村再生相關公共設施作業處理原則": "農村再生",
    "農村社區自辦整體環境改善作業要點": "農村再生",
    "農村社區執行農村再生相關計畫經費編列及核銷說明": "農村再生",
    "農業委員會補助或委辦計畫助理人員工作酬金支給薪點參考表": "農村再生",
    "農業部補助直轄市及縣（市）政府推動社區農村再生計畫審查及管考作業要點": "農村再生",
    # YAML v1 明列「地方自治」為未涵蓋領域；這部也沒有全文，雙重排除。
    "雲林縣政府農村再生計畫審查小組設置要點": "地方自治",
}

# 「第 8 條」與「第8條」兩種排版都要吃（PDF 抽出來的空白不一致）
ART_RE = re.compile(r"第\s*(\d+)\s*條")
# 行政規則多半不是條文式，而是「一、二、三、」點次（含「三之一、」）
POINT_RE = re.compile(r"(?m)^\s*([一二三四五六七八九十百]+(?:之[一二三四五六七八九十]+)?)、")
MAX_UNIT_CHARS = 8000
CHAPTER_RE = re.compile(r"第\s*[一二三四五六七八九十百]+\s*[章編]\s*[^\n]{0,20}")
VERSION_RE = re.compile(r"(公布日期|最後修正日期|修正日期)[：: ]*([^\n　]{4,30})")

TAGS = ["實質管制", "罰則", "行政經費", "程序要件"]

_PROMPT = """你在建立「法規負面清單」，供後續比對社區計畫書用。

以下是《{name}》的條文。請逐條檢視，把**會對計畫內容形成拘束**的規定抽成條目。

要抽的四類（tag）：
- 實質管制：禁止、限制、應經許可/核准、應先擬具計畫等，對行為本身的拘束
- 罰則：違反時的罰鍰、停工、拆除、追繳等法律效果
- 行政經費：補助上限、經費編列與核銷的限制
- 程序要件：應報請核定、公告、審查、備查等程序上的要求

每個條目輸出：
- article_no：條號，格式「第8條」；若原文非條文式（點次、表格）就寫「第X點」或「全文」
- tag：上面四類其中之一
- situation：**什麼情況會觸發這條**。寫成計畫書可能出現的行為描述，不要照抄法條術語。
  例：「於山坡地或森林區內從事開發、經營或使用」而不是「違反本法第八條規定」
- requirement：這種情況下法律要求做什麼（一句話）
- penalty：違反的法律效果；沒有就給 null

不要抽：定義性條文、主管機關權責分配、施行日期、純程序性的機關內部事項。
寧可少抽也不要把不構成拘束的條文塞進來 —— 這份清單會直接變成檢核報告的告警。

只輸出 JSON 陣列，不要任何其他文字：
[{{"article_no":"第8條","tag":"實質管制","situation":"...","requirement":"...","penalty":"..."}}]

條文：
{text}"""


def _window_split(text: str, label: str, max_chars: int = MAX_UNIT_CHARS) -> list[dict]:
    """結構抓不到（或單一單位過長）時，按段落邊界切成固定大小視窗。

    切了會失去條號粒度，但抽取 prompt 要求 LLM 自己標「第X點」，引用仍然回得來；
    比硬塞 38,000 字進一次呼叫可靠得多。
    """
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if cur and len(cur) + len(p) > max_chars:
            chunks.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + p
    if cur:
        chunks.append(cur)
    if len(chunks) == 1:
        return [{"seq": 0, "article_no": label, "chapter": None, "text": chunks[0].strip()}]
    return [
        {"seq": i, "article_no": f"{label}（第{i+1}段）", "chapter": None, "text": c.strip()}
        for i, c in enumerate(chunks)
    ]


def split_articles(text: str) -> list[dict]:
    """切成判定/引用的最小單位。

    三段式：條文式（第 N 條）→ 點次式（一、二、三、）→ 視窗切分。
    法規語料混了法律、施行細則、行政規則、審議規範與表格，沒有單一切法吃得下全部。
    """
    marks = [(m.start(), f"第{m.group(1)}條") for m in ART_RE.finditer(text)]
    if len({n for _, n in marks}) < 3:
        marks = [(m.start(), f"第{m.group(1)}點") for m in POINT_RE.finditer(text)]
        if len({n for _, n in marks}) < 3:
            return _window_split(text, "全文")

    chapters = [(m.start(), m.group(0).strip()) for m in CHAPTER_RE.finditer(text)]

    def chapter_at(pos: int) -> str | None:
        cur = None
        for cpos, cname in chapters:
            if cpos > pos:
                break
            cur = cname
        return cur

    out: list[dict] = []
    for i, (pos, no) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end].strip()
        if len(body) < 10:
            continue
        chap = chapter_at(pos)
        if len(body) > MAX_UNIT_CHARS:      # 單條過長（審議規範的某些點）→ 再切
            for j, part in enumerate(_window_split(body, no)):
                out.append({"seq": len(out), "article_no": part["article_no"],
                            "chapter": chap, "text": part["text"]})
        else:
            out.append({"seq": len(out), "article_no": no, "chapter": chap, "text": body})
    return out


def detect_version(text: str) -> str:
    m = VERSION_RE.search(text[:600])
    return m.group(2).strip() if m else ""


def is_no_fulltext(text: str) -> bool:
    """Drive 裡有兩份不是法規，是「查不到全文」的說明書 —— 不能進判定分母。"""
    head = text[:400]
    return ("未取得" in head and "原因" in text[:1500]) or "抓取狀態說明" in head


def _batches(articles: list[dict], max_chars: int = 14000) -> list[list[dict]]:
    out, cur, size = [], [], 0
    for a in articles:
        if cur and size + len(a["text"]) > max_chars:
            out.append(cur)
            cur, size = [], 0
        cur.append(a)
        size += len(a["text"])
    if cur:
        out.append(cur)
    return out


def _parse_json_array(raw: str) -> list[dict]:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    start, end = s.find("["), s.rfind("]")
    if start < 0 or end < 0:
        return []
    try:
        data = json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("situation")]


async def extract_controls(name: str, articles: list[dict], llm, model: str,
                           batch_chars: int = 14000) -> list[dict]:
    got: list[dict] = []
    for batch in _batches(articles, batch_chars):
        # a["text"] 本身就以「第 N 條」開頭，不用再補條號
        text = "\n\n".join(a["text"] for a in batch)
        resp = await llm.ainvoke(_PROMPT.format(name=name, text=text))
        items = _parse_json_array(resp.content or "")
        for it in items:
            tag = it.get("tag") if it.get("tag") in TAGS else "實質管制"
            got.append({
                "article_no": str(it.get("article_no") or "").strip(),
                "tag": tag,
                "situation": str(it["situation"]).strip(),
                "requirement": (str(it["requirement"]).strip() if it.get("requirement") else None),
                "penalty": (str(it["penalty"]).strip() if it.get("penalty") else None),
                "extracted_by": model,
            })
    return got


# ── runtime 用：啟用一部上傳的法規時，就地抽條文與管制條目 ─────────────
async def ingest_uploaded_pdf(pdf_path: Path, name: str, *, model: str | None = None,
                              reasoning: str = "none") -> dict:
    """一部上傳的 PDF → {articles, controls, version, no_fulltext}。

    這是唯一會在 runtime 呼叫 LLM 的 ingest 路徑，只給「管理者上傳並審核啟用」用。
    MANIFEST 內的 31 部走建置時抽取、產物進版控（可 diff、可追是哪個模型抽的）；
    使用者上傳的沒有 repo 產物，只能就地抽 —— 所以 corpus_version 留空、
    extracted_by 記下模型，報告才分得出這條管制是哪來的。
    """
    from app.regulations import standard

    txt = pdf_to_text(pdf_path)
    if not txt.strip():
        return {"articles": [], "controls": [], "version": "", "no_fulltext": True,
                "error": "PDF 抽不出文字（可能是掃描件，需要 OCR）"}
    if is_no_fulltext(txt):
        return {"articles": [], "controls": [], "version": detect_version(txt),
                "no_fulltext": True, "error": "內容不是法規全文"}

    articles = split_articles(txt)
    model = model or standard.judge_model(standard.load()) or None
    if reasoning == "none":
        llm = make_llm(alias=model, temperature=0, streaming=False).bind(max_completion_tokens=16000)
    else:
        llm = make_llm(alias=model, temperature=1, streaming=False).bind(
            max_completion_tokens=16000, reasoning_effort=reasoning)
    controls = await extract_controls(name, articles, llm, model or "(預設)")
    domain = LAW_DOMAIN.get(name, "其他")
    for c in controls:
        c["law_domain"] = domain
    return {"articles": articles, "controls": controls,
            "version": detect_version(txt), "no_fulltext": False, "error": ""}


def pdf_to_text(pdf_path: Path) -> str:
    """PDF → 純文字。抽不出來（掃描件）回空字串，讓上層標成需要 OCR。

    優先用 PyMuPDF（已是既有依賴、純 Python，容器裡就有）；沒有才退回 pdftotext。
    註：版控語料（corpus/extracted/）是建置時用 pdftotext 抽的，兩者斷行細節略有
    差異；影響只在條文切分的邊界，判定用的是條文內容，不受影響。
    """
    try:
        try:
            import pymupdf                      # 新名稱
        except ImportError:
            import fitz as pymupdf              # 舊名稱（1.24 之前）
        with pymupdf.open(pdf_path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("PyMuPDF 抽文字失敗，改試 pdftotext：%s", pdf_path.name)

    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.txt"
        try:
            subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf_path), str(out)],
                           check=True, capture_output=True, timeout=120)
        except Exception:  # noqa: BLE001
            return ""
        return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai-5.4-xiaozhen", help="LiteLLM alias")
    ap.add_argument("--only", default="", help="只處理名稱含這個字串的法規")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--batch-chars", type=int, default=14000,
                    help="每次呼叫餵多少字；條文密的法規調小可避免 timeout")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="單次呼叫逾時秒數（LiteLLM 預設只有 60s，長法規會爆）")
    ap.add_argument("--reasoning", default="low",
                    choices=["none", "low", "medium", "high"],
                    help="推理模型的 reasoning_effort；none = 當一般模型跑")
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    man = yaml.safe_load((CORPUS / "MANIFEST.yaml").read_text(encoding="utf-8"))
    entries = man["regulations"]

    # gpt-5.x：(a) reasoning 會吃掉 completion 額度，給不夠會吐空字串（R0 踩過）；
    # (b) 只吃 temperature=1，給 0 直接 400。抽取結果進版控 + 人工複核，
    # 所以這裡放棄 temperature=0 的可重現性是可接受的取捨。
    if args.reasoning == "none":
        llm = make_llm(alias=args.model, temperature=0, streaming=False).bind(
            max_tokens=args.max_tokens, timeout=args.timeout
        )
    else:
        llm = make_llm(alias=args.model, temperature=1, streaming=False).bind(
            max_completion_tokens=args.max_tokens, reasoning_effort=args.reasoning,
            timeout=args.timeout,
        )

    # --only 是「補跑某一部」，不是「只留這一部」：先載入既有結果再更新，
    # 否則單獨重跑一部會把另外 30 部從 JSON 裡抹掉。
    def _load(f: Path) -> dict:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    all_articles: dict[str, list[dict]] = _load(CORPUS / "articles.json") if args.only else {}
    all_negatives: dict[str, list[dict]] = _load(CORPUS / "negative_list.json") if args.only else {}
    skipped: list[str] = []
    t0 = time.time()

    for i, entry in enumerate(entries, 1):
        name = entry["name"]
        if args.only and args.only not in name:
            continue
        text = (CORPUS / "extracted" / f"{name}.txt").read_text(encoding="utf-8")
        entry["version"] = detect_version(text)
        entry["law_domain"] = LAW_DOMAIN.get(name, "其他")

        if is_no_fulltext(text):
            entry["no_fulltext"] = True
            skipped.append(name)
            print(f"[{i:2d}/{len(entries)}] ⚠️  {name[:30]:32s} 全文未取得 → 不進判定分母", flush=True)
            continue
        entry.pop("no_fulltext", None)
        # 草案尚未生效 —— 照樣抽條目（上路後就能用），但 seed 時給 draft 狀態、不進判定
        if "草案" in name:
            entry["draft"] = True
        else:
            entry.pop("draft", None)

        articles = split_articles(text)
        all_articles[name] = articles

        cache_f = CACHE / f"{name}.json"
        if cache_f.exists() and not args.no_cache:
            controls = json.loads(cache_f.read_text(encoding="utf-8"))
            mark = "(cache)"
            dt = 0.0
        else:
            t = time.time()
            try:
                controls = await extract_controls(name, articles, llm, args.model,
                                                  batch_chars=args.batch_chars)
            except Exception as e:  # noqa: BLE001
                print(f"[{i:2d}/{len(entries)}] ❌ {name[:30]:32s} {type(e).__name__}: {e}", flush=True)
                continue
            cache_f.write_text(json.dumps(controls, ensure_ascii=False, indent=1), encoding="utf-8")
            mark = ""
            dt = time.time() - t
        # law_domain 在這裡才套（不進 cache）：改分組只要重跑寫檔，不必重花 LLM 的錢
        domain = LAW_DOMAIN.get(name, "其他")
        for c in controls:
            c["law_domain"] = domain
        all_negatives[name] = controls
        print(f"[{i:2d}/{len(entries)}] ✅ {name[:30]:32s} {len(text):6d}字 "
              f"→ {len(articles):3d} 條 → 抽出 {len(controls):3d} 條管制 {dt:5.1f}s {mark}", flush=True)

    (CORPUS / "articles.json").write_text(
        json.dumps(all_articles, ensure_ascii=False, indent=1), encoding="utf-8")
    (CORPUS / "negative_list.json").write_text(
        json.dumps(all_negatives, ensure_ascii=False, indent=1), encoding="utf-8")
    man["extracted_by"] = args.model
    man["count_fulltext"] = len(all_negatives)
    yaml.safe_dump(man, (CORPUS / "MANIFEST.yaml").open("w", encoding="utf-8"),
                   allow_unicode=True, sort_keys=False)

    total = sum(len(v) for v in all_negatives.values())
    domains = sorted({c["law_domain"] for v in all_negatives.values() for c in v})
    print(f"\n完成 {time.time()-t0:.0f}s：{len(all_negatives)} 部有全文 / {len(skipped)} 部未取得")
    print(f"條文 {sum(len(v) for v in all_articles.values())} 條 → 管制條目 {total} 條")
    print(f"法領域 {len(domains)}：{'、'.join(domains)}")
    if skipped:
        print(f"未取得全文：{'、'.join(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
