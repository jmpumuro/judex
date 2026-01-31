"""
LLM Factory - Creates appropriate LLM adapter based on configuration.

Industry Standard: Factory Pattern for pluggable provider selection.
"""
from typing import Optional, Dict, Type
from enum import Enum

from app.llm.base import LLMAdapter
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("llm.factory")


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    QWEN = "qwen"
    TEMPLATE = "template"  # Fallback with no LLM


# Registry of adapters
_ADAPTERS: Dict[LLMProvider, Type[LLMAdapter]] = {}
_instances: Dict[LLMProvider, LLMAdapter] = {}


def register_adapter(provider: LLMProvider, adapter_class: Type[LLMAdapter]):
    """Register an adapter class for a provider."""
    _ADAPTERS[provider] = adapter_class
    logger.info(f"Registered LLM adapter: {provider.value}")


def _register_default_adapters():
    """Register default adapters."""
    from app.llm.openai_adapter import OpenAIAdapter
    from app.llm.qwen_adapter import QwenAdapter
    
    register_adapter(LLMProvider.OPENAI, OpenAIAdapter)
    register_adapter(LLMProvider.QWEN, QwenAdapter)


def get_llm(
    provider: Optional[str] = None,
    fallback: bool = True,
    **kwargs
) -> Optional[LLMAdapter]:
    """
    Get LLM adapter for the specified provider.
    
    Args:
        provider: Provider name ('openai', 'qwen'). Defaults to settings.llm_provider.
        fallback: If True, try fallback providers if primary is unavailable.
        **kwargs: Provider-specific configuration.
    
    Returns:
        LLMAdapter instance or None if no provider available.
    
    Example:
        llm = get_llm()  # Uses default from settings
        llm = get_llm("openai")  # Force OpenAI
        llm = get_llm("qwen", fallback=False)  # Qwen only, no fallback
    """
    # Ensure adapters are registered
    if not _ADAPTERS:
        _register_default_adapters()
    
    # Determine provider
    provider_name = provider or settings.llm_provider
    
    try:
        provider_enum = LLMProvider(provider_name.lower())
    except ValueError:
        logger.warning(f"Unknown LLM provider: {provider_name}, using openai")
        provider_enum = LLMProvider.OPENAI
    
    # Try to get/create adapter
    adapter = _try_get_adapter(provider_enum, **kwargs)
    
    if adapter and adapter.is_available():
        return adapter
    
    # Fallback chain: openai -> qwen -> None
    if fallback:
        fallback_order = [LLMProvider.OPENAI, LLMProvider.QWEN]
        
        for fallback_provider in fallback_order:
            if fallback_provider == provider_enum:
                continue  # Already tried this one
            
            adapter = _try_get_adapter(fallback_provider, **kwargs)
            if adapter and adapter.is_available():
                logger.info(f"Using fallback LLM provider: {fallback_provider.value}")
                return adapter
    
    logger.warning("No LLM provider available")
    return None


def _try_get_adapter(provider: LLMProvider, **kwargs) -> Optional[LLMAdapter]:
    """Try to create or get cached adapter."""
    if provider == LLMProvider.TEMPLATE:
        return None
    
    if provider not in _ADAPTERS:
        logger.warning(f"No adapter registered for: {provider.value}")
        return None
    
    # Check cache (singleton per provider)
    if provider in _instances and not kwargs:
        return _instances[provider]
    
    try:
        adapter_class = _ADAPTERS[provider]
        adapter = adapter_class(**kwargs) if kwargs else adapter_class()
        
        # Cache if no custom kwargs
        if not kwargs:
            _instances[provider] = adapter
        
        return adapter
    except Exception as e:
        logger.warning(f"Failed to create adapter for {provider.value}: {e}")
        return None


def unload_llm(provider: Optional[str] = None):
    """
    Unload LLM to free memory.
    
    Args:
        provider: Specific provider to unload, or None for all.
    """
    if provider:
        try:
            provider_enum = LLMProvider(provider.lower())
            if provider_enum in _instances:
                _instances[provider_enum].unload()
                del _instances[provider_enum]
                logger.info(f"Unloaded LLM: {provider}")
        except (ValueError, KeyError):
            pass
    else:
        # Unload all
        for p, adapter in list(_instances.items()):
            adapter.unload()
        _instances.clear()
        logger.info("Unloaded all LLMs")


def list_providers() -> Dict[str, Dict]:
    """List all registered providers with their status."""
    if not _ADAPTERS:
        _register_default_adapters()
    
    result = {}
    for provider in LLMProvider:
        if provider == LLMProvider.TEMPLATE:
            result[provider.value] = {"available": True, "type": "template"}
            continue
        
        adapter = _try_get_adapter(provider)
        if adapter:
            result[provider.value] = adapter.health_check()
        else:
            result[provider.value] = {"available": False, "registered": provider in _ADAPTERS}
    
    return result


def get_default_provider() -> str:
    """Get the default provider from settings."""
    return settings.llm_provider
