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
    api_key: str | None = None,
    user: str | None = None,
    temperature: float = 0.2,
    streaming: bool = True,
) -> ChatOpenAI:
    """LiteLLM 後 ChatOpenAI factory。

    `api_key` 可以傳指定 virtual key（例如 LINE bot 用獨立 key 帳單分離），
    不傳就走預設的 LITELLM_API_KEY（通常是 master key 或 ai-eva-web 的 virtual key）。
    `user` 傳 SSO user_id → 帶進請求的 `user` 欄，LiteLLM 按 end-user/customer 計量（帳號層，#62 B）。
    """
    # OpenAI 的 `user` 欄必須是字串；SSO 帶進來的 user_id 可能是整數 → 一律 str()（否則 400）。
    extra = {"model_kwargs": {"user": str(user)}} if user else {}
    return ChatOpenAI(
        model=alias or LITELLM_DEFAULT_MODEL,
        api_key=api_key or LITELLM_API_KEY or "litellm-no-auth",
        base_url=LITELLM_API_BASE,
        temperature=temperature,
        streaming=streaming,
        **extra,
    )
