"""
LLM Module - Agnostic LLM interface with factory pattern.

Industry Standard: Strategy Pattern for pluggable LLM backends.
Supports OpenAI (default), Qwen (local), and extensible for future providers.
"""
from app.llm.factory import get_llm, LLMProvider
from app.llm.base import LLMAdapter, LLMResponse

__all__ = ["get_llm", "LLMProvider", "LLMAdapter", "LLMResponse"]
