from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from app.settings import (
    CHROMA_DIR,
    EMBEDDING_MODEL,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    RAG_TOP_K,
)

_store: Chroma | None = None


def _get_store() -> Chroma:
    global _store
    if _store is None:
        emb = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
        )
        _store = Chroma(persist_directory=CHROMA_DIR, embedding_function=emb)
    return _store


def retrieve(query: str, k: int = RAG_TOP_K):
    store = _get_store()
    docs = store.similarity_search(query, k=k)
    return [
        {
            "text": d.page_content,
            "source": d.metadata.get("source", "unknown"),
            "page": d.metadata.get("page"),
        }
        for d in docs
    ]
