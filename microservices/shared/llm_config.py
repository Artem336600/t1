"""
LLM Configuration - Shared configuration for all microservices

SciBox LLM API:
- qwen3-32b-awq: Universal chat model (2 RPS), supports /no_think to disable reasoning
- qwen3-coder-30b-a3b-instruct-fp8: Code assistant (2 RPS)
- bge-m3: Embeddings model (7 RPS)
"""
import os
from openai import AsyncOpenAI

class Models:
    """Available LLM models from SciBox"""
    CHAT = os.getenv("LLM_CHAT_MODEL", "qwen3-32b-awq")
    CODE = os.getenv("LLM_CODE_MODEL", "qwen3-coder-30b-a3b-instruct-fp8")
    EMBEDDING = os.getenv("EMBEDDING_MODEL", "bge-m3")

# Default API configuration
DEFAULT_API_KEY = "sk-SSWP5NVJpHecmOFI_yxp7Q"
DEFAULT_BASE_URL = "https://llm.t1v.scibox.tech/v1"

def get_client() -> AsyncOpenAI:
    """Get configured AsyncOpenAI client for SciBox LLM"""
    return AsyncOpenAI(
        api_key=os.getenv("LLM_API_KEY", DEFAULT_API_KEY),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    )

def get_system_prompt(base_prompt: str, disable_thinking: bool = True) -> str:
    """
    Wrap system prompt with /no_think marker to disable reasoning mode.
    This makes responses faster and more direct.
    """
    if disable_thinking:
        return f"/no_think {base_prompt}"
    return base_prompt
