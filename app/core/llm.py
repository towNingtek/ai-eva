from langchain_openai import ChatOpenAI

from app.settings import LLM_MODEL, OPENAI_API_BASE, OPENAI_API_KEY


def make_llm(temperature: float = 0.2, streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
        temperature=temperature,
        streaming=streaming,
    )
