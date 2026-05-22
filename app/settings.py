import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
WEB_SEARCH_TOP_K = int(os.getenv("WEB_SEARCH_TOP_K", "5"))

LITELLM_API_BASE = os.getenv("LITELLM_API_BASE", "http://host.docker.internal:4000/v1")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "").strip()
LITELLM_LINE_KEY = os.getenv("LITELLM_LINE_KEY", "").strip()
LITELLM_DEFAULT_MODEL = os.getenv("LITELLM_DEFAULT_MODEL", "cloud-fast")
LITELLM_CHEAP_MODEL = os.getenv("LITELLM_CHEAP_MODEL", "local-cheap")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
