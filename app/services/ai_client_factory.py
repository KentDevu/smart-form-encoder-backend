"""Factory for creating AI clients (NVIDIA, OpenRouter, OpenAI, Groq).

Supports provider selection via config.AI_PROVIDER setting.
Returns OpenAI-compatible client for all providers.
All clients support chat.completions.create() API.
Primary: NVIDIA (free tier, 40 req/min)
Fallback: OpenRouter, OpenAI, Groq
"""

from openai import OpenAI
from app.config import get_settings


def get_ai_client() -> OpenAI:
    """Return appropriately configured AI client based on AI_PROVIDER setting.
    
    Returns:
        OpenAI: OpenAI-compatible client for the configured provider.
        
    Raises:
        ValueError: If AI_PROVIDER is not recognized or required credentials missing.
    """
    settings = get_settings()
    provider = settings.AI_PROVIDER.lower()
    
    if provider == "nvidia":
        # NVIDIA: Free tier with 40 req/min limit, OpenAI-compatible API
        api_key = settings.NVIDIA_API_KEY
        if not api_key:
            raise ValueError(
                "NVIDIA_API_KEY must be set when using NVIDIA provider. "
                "Get free key at https://build.nvidia.com (format: nvapi-xxxxxxxx)"
            )
        return OpenAI(
            api_key=api_key,
            base_url=settings.NVIDIA_BASE_URL or "https://integrate.api.nvidia.com/v1",
        )
    
    elif provider == "openrouter":
        # OpenRouter: Free tier supports chat completions via OpenAI-compatible API (fallback)
        api_key = settings.OPENROUTER_API_KEY or settings.AI_API_KEY
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY (or AI_API_KEY as fallback) must be set "
                "when using OpenRouter provider"
            )
        return OpenAI(
            api_key=api_key,
            base_url=settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1",
        )
    
    elif provider == "openai":
        # OpenAI: Standard OpenAI API
        api_key = settings.OPENAI_API_KEY or settings.AI_API_KEY
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY (or AI_API_KEY as fallback) must be set "
                "when using OpenAI provider"
            )
        return OpenAI(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
        )
    
    elif provider == "groq":
        # Groq: Primary provider for structured field extraction
        # Try GROQ_API_KEY first, fall back to AI_API_KEY for backwards compatibility
        api_key = settings.GROQ_API_KEY or settings.AI_API_KEY
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY or AI_API_KEY must be set when using Groq provider"
            )
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq package not installed. Install with: pip install groq"
            )
        return Groq(api_key=api_key)
    
    else:
        raise ValueError(
            f"Unknown AI provider: {provider}. "
            f"Supported: nvidia (primary), openrouter (fallback), openai, groq (deprecated)"
        )
