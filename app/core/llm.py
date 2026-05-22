"""
LLM factory — 所有 LLM 呼叫都走 LiteLLM proxy（M2 起）。

使用方式：
    llm = make_llm()                        # 預設 alias (cloud-fast / OpenAI)
    llm = make_llm(alias="local-cheap")     # Pi5 Qwen
    llm = make_llm(alias="local-cheap", temperature=0)

alias 是 litellm-config.yaml 裡的 model_name；新增 provider 改 config，這層不動。
"""
from langchain_openai import ChatOpenAI

from app.settings import LITELLM_API_BASE, LITELLM_API_KEY, LITELLM_DEFAULT_MODEL


def make_llm(
    *,
    alias: str | None = None,
    temperature: float = 0.2,
    streaming: bool = True,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=alias or LITELLM_DEFAULT_MODEL,
        api_key=LITELLM_API_KEY or "litellm-no-auth",
        base_url=LITELLM_API_BASE,
        temperature=temperature,
        streaming=streaming,
    )
