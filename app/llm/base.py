"""
LLM Adapter Base Class - Abstract interface for all LLM providers.

Industry Standard: Protocol/Interface pattern for pluggable implementations.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


@dataclass
class LLMResponse:
    """Standardized LLM response across all providers."""
    content: str
    model: str
    provider: str
    usage: Optional[Dict[str, int]] = None  # tokens used
    finish_reason: Optional[str] = None
    raw_response: Optional[Any] = None


class LLMAdapter(ABC):
    """
    Abstract base class for LLM adapters.
    
    All LLM providers must implement this interface.
    This enables swapping providers without changing application code.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'openai', 'qwen', 'anthropic')."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model being used."""
        pass
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.3,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text completion.
        
        Args:
            prompt: User prompt/message
            system_prompt: System message for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            **kwargs: Provider-specific options
            
        Returns:
            LLMResponse with generated content
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available (API key set, model loaded, etc.)."""
        pass
    
    def unload(self) -> None:
        """
        Unload model/free resources (optional).
        
        Override for local models that need memory management.
        """
        pass
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the provider.
        
        Returns dict with status and details.
        """
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "available": self.is_available(),
        }
