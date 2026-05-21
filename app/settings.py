import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

CHROMA_DIR = os.getenv("CHROMA_DIR", str(ROOT / "data" / "chroma"))
DOCS_DIR = os.getenv("DOCS_DIR", str(ROOT / "data" / "docs"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
WEB_SEARCH_TOP_K = int(os.getenv("WEB_SEARCH_TOP_K", "5"))

LITELLM_API_BASE = os.getenv("LITELLM_API_BASE", "http://host.docker.internal:4000/v1")
LITELLM_DEFAULT_MODEL = os.getenv("LITELLM_DEFAULT_MODEL", "cloud-fast")
LITELLM_CHEAP_MODEL = os.getenv("LITELLM_CHEAP_MODEL", "local-cheap")
