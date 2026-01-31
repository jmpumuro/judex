"""
OpenAI LLM Adapter - Default cloud-based LLM provider.

Industry Standard: Uses official OpenAI Python SDK.
"""
from typing import Optional, Dict, Any
from app.llm.base import LLMAdapter, LLMResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("llm.openai")


class OpenAIAdapter(LLMAdapter):
    """
    OpenAI LLM adapter using the official SDK.
    
    Default provider - fast, reliable, production-ready.
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._base_url = base_url  # For OpenAI-compatible APIs
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                import openai
                kwargs = {"api_key": self._api_key}
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = openai.OpenAI(**kwargs)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def is_available(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self._api_key)
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.3,
        **kwargs
    ) -> LLMResponse:
        """Generate completion using OpenAI API."""
        if not self.is_available():
            raise ValueError("OpenAI API key not configured")
        
        client = self._get_client()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"Generating with OpenAI {self._model}...")
            
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            content = response.choices[0].message.content
            
            logger.info(f"OpenAI generation successful ({response.usage.total_tokens} tokens)")
            
            return LLMResponse(
                content=content,
                model=self._model,
                provider=self.provider_name,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                raw_response=response
            )
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise
    
    def health_check(self) -> Dict[str, Any]:
        """Check OpenAI API health."""
        base = super().health_check()
        base["api_key_set"] = bool(self._api_key)
        base["base_url"] = self._base_url
        return base
