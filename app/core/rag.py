"""
RAG stores, session-scoped:
  - persistent_store(): long-term knowledge base（data/chroma/），跨 session 共用
  - session_store(): 單一 WebSocket session 的 in-memory 暫存，上傳檔案用
  - retrieve(): 兩邊都查，合併結果，標 scope

CLI ingest (`python -m app.rag.ingest`) 寫進 persistent；
chat 內拖檔只進 session，該 session 關閉就消失。
"""
import logging
from pathlib import Path

import chainlit as cl
from langchain_chroma import Chroma
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.settings import (
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    RAG_TOP_K,
)

logger = logging.getLogger(__name__)

_embeddings: OpenAIEmbeddings | None = None
_persistent: Chroma | None = None


def embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
        )
    return _embeddings


def persistent_store() -> Chroma:
    global _persistent
    if _persistent is None:
        _persistent = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings())
    return _persistent


def _session_store_or_none() -> InMemoryVectorStore | None:
    try:
        return cl.user_session.get("rag_session_store")
    except Exception:
        return None


def ensure_session_store() -> InMemoryVectorStore:
    store = _session_store_or_none()
    if store is None:
        store = InMemoryVectorStore(embedding=embeddings())
        cl.user_session.set("rag_session_store", store)
    return store


def retrieve(query: str, k: int | None = None) -> list[dict]:
    """Query session (priority) + persistent, merge, tag scope."""
    k = k or RAG_TOP_K
    results: list[dict] = []

    sess = _session_store_or_none()
    if sess is not None:
        try:
            for d in sess.similarity_search(query, k=k):
                results.append({
                    "text": d.page_content,
                    "source": d.metadata.get("source", "unknown"),
                    "page": d.metadata.get("page"),
                    "scope": "session",
                })
        except Exception as e:
            logger.warning("session RAG search failed: %s", e)

    try:
        for d in persistent_store().similarity_search(query, k=k):
            results.append({
                "text": d.page_content,
                "source": d.metadata.get("source", "unknown"),
                "page": d.metadata.get("page"),
                "scope": "base",
            })
    except Exception as e:
        logger.warning("persistent RAG search failed: %s", e)

    return results


def ingest_to_session(path, source_label: str | None = None) -> int:
    """Load + split + embed + store in session-only in-memory vector store."""
    from app.rag.ingest import _load_one  # reuse loader (PDF / OCR / txt / md)

    p = Path(path)
    docs = _load_one(p)
    if not docs:
        return 0
    label = source_label or p.name
    for d in docs:
        d.metadata["source"] = label

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(docs)
    if not chunks:
        return 0
    ensure_session_store().add_documents(chunks)
    return len(chunks)
