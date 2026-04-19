"""
Ingest documents in DOCS_DIR into Chroma.
圖片型 PDF 會自動 fallback 到 Vision OCR (gpt-4o-mini vision)。
Run:
    python -m app.rag.ingest
"""
import base64
import logging
from pathlib import Path

import fitz  # PyMuPDF
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.settings import (
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCS_DIR,
    EMBEDDING_MODEL,
    LLM_MODEL,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
)

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md")

# 當 PDF pdfminer 抽取總字數 < 此值，判定為圖片型 → 走 Vision OCR
OCR_FALLBACK_THRESHOLD = 30


def _pdf_has_text(docs: list[Document]) -> bool:
    total = sum(len((d.page_content or "").strip()) for d in docs)
    return total >= OCR_FALLBACK_THRESHOLD


def _ocr_pdf_with_vision(path: Path) -> list[Document]:
    """Render each page to PNG, call OpenAI Vision, return Documents."""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
        temperature=0,
    )
    prompt = (
        "請完整辨識圖片中的所有文字。保留原始段落結構。"
        "若有表格，請用 markdown 表格格式呈現。"
        "若有手寫文字，請盡量辨識並標記 [手寫]。"
        "只輸出辨識結果，不要加任何說明。"
    )

    pdf = fitz.open(str(path))
    results: list[Document] = []
    try:
        for i in range(len(pdf)):
            page = pdf.load_page(i)
            pix = page.get_pixmap(dpi=200, alpha=False)
            img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            resp = llm.invoke(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                            },
                        ],
                    }
                ]
            )
            text = (resp.content or "").strip()
            if text:
                results.append(Document(page_content=text, metadata={"page": i + 1}))
    finally:
        pdf.close()
    return results


def _load_one(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            docs = PyPDFLoader(str(path)).load()
        except Exception as e:
            logger.warning(f"PyPDFLoader failed for {path}: {e}")
            docs = []
        if _pdf_has_text(docs):
            return docs
        # image-based PDF → Vision OCR fallback
        logger.info(f"PDF {path.name} 文字少，改用 Vision OCR")
        return _ocr_pdf_with_vision(path)
    if suffix in (".txt", ".md"):
        return TextLoader(str(path), encoding="utf-8").load()
    return []


def _build_store():
    emb = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
    )
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=emb)


def ingest_one_file(path, source_label: str | None = None) -> int:
    """Load a single file → split → embed → persist. Returns chunk count."""
    p = Path(path)
    docs = _load_one(p)
    if not docs:
        return 0
    label = source_label or p.name
    for d in docs:
        d.metadata["source"] = label

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(docs)
    if not chunks:
        return 0
    _build_store().add_documents(chunks)
    return len(chunks)


def main():
    docs_root = Path(DOCS_DIR)
    if not docs_root.exists():
        print(f"DOCS_DIR not found: {docs_root}")
        return

    raw = []
    for p in docs_root.rglob("*"):
        if p.is_file():
            loaded = _load_one(p)
            for d in loaded:
                d.metadata["source"] = str(p.relative_to(docs_root))
            raw.extend(loaded)

    if not raw:
        print(f"No supported files in {docs_root}")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(raw)
    _build_store().add_documents(chunks)

    print(f"Ingested {len(chunks)} chunks from {len(raw)} document(s) into {CHROMA_DIR}")


if __name__ == "__main__":
    main()
