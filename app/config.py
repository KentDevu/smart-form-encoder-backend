from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "SmartForm Encoder API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smartform"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/smartform"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Redis Pool Configuration
    REDIS_POOL_SIZE: int = 10  # Maximum connections in pool
    REDIS_POOL_TIMEOUT: int = 5  # Connection timeout in seconds

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "smartform-uploads"
    R2_ENDPOINT_URL: str = ""

    # AI Vision (supports Groq, NVIDIA, OpenRouter, OpenAI)
    # Provider options: "groq" (Llama 3.3 70B for field extraction), "nvidia", "openrouter", "openai"
    AI_PROVIDER: str = "groq"  # Switched to Groq for better field extraction accuracy
    AI_API_KEY: str = ""  # Groq API key (https://console.groq.com)
    AI_API_KEY_1: str = ""
    AI_API_KEY_2: str = ""
    AI_API_KEY_3: str = ""
    
    # Groq Configuration (primary provider - Llama 3.3 70B for structured extraction)
    GROQ_API_KEY: str = ""  # Groq API key
    GROQ_API_KEY_1: str = ""  # Backup Groq API key
    GROQ_API_KEY_2: str = ""  # Backup Groq API key
    GROQ_API_KEY_3: str = ""  # Backup Groq API key
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # Best for structured field extraction (280 tokens/sec, $0.59/$0.79)
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TEMPERATURE: float = 0.3  # Lower temperature for structured extraction
    GROQ_MAX_TOKENS: int = 1024
    
    # NVIDIA API (fallback - free tier with 40 req/min limit)
    NVIDIA_API_KEY: str = ""  # NVIDIA API key (https://build.nvidia.com) — format: nvapi-xxxxxxxx
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"  # NVIDIA endpoint
    AI_VISION_MODEL: str = "llama-3.3-70b-versatile"  # Groq model for structured field extraction (text-to-fields reasoning)
    NVIDIA_RATE_LIMIT: int = 40  # Requests per minute (free tier limit)
    
    # OpenRouter configuration (fallback)
    OPENROUTER_API_KEY: str = ""  # OpenRouter API key (https://openrouter.ai) — fallback
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"  # OpenRouter endpoint (fallback)

    # Multi-AI Consensus Validation (off by default — single AI + human verification is faster)
    AI_CONSENSUS_ENABLED: bool = False
    AI_CONSENSUS_MIN_VALIDATORS: int = 3
    AI_CONSENSUS_TARGET_AGREEMENT: float = 0.98
    AI_CONSENSUS_MAX_ROUNDS: int = 3

    # Legacy OpenAI key (fallback)
    OPENAI_API_KEY: str = ""

    @property
    def ai_api_keys(self) -> list[str]:
        """Return all configured AI API keys (non-empty)."""
        keys = [self.AI_API_KEY, self.AI_API_KEY_1, self.AI_API_KEY_2, self.AI_API_KEY_3]
        return [k for k in keys if k]

    @property
    def groq_api_keys(self) -> list[str]:
        """Return all configured Groq API keys (non-empty)."""
        keys = [self.GROQ_API_KEY, self.GROQ_API_KEY_1, self.GROQ_API_KEY_2, self.GROQ_API_KEY_3]
        return [k for k in keys if k]

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # Performance / RAM Management
    # Set LOW_RAM_MODE=true to minimize memory usage (slower OCR, smaller model)
    LOW_RAM_MODE: bool = False
    # Set CACHE_OCR_MODEL=true to keep PaddleOCR in memory (70% faster, uses 500MB)
    # Set CACHE_OCR_MODEL=false to reload per task (slower, uses less peak RAM)
    CACHE_OCR_MODEL: bool = True

    # Worker Configuration
    # Max tasks per worker before restart (prevents memory accumulation)
    CELERY_MAX_TASKS_PER_CHILD: int = 50  # Restart every 50 tasks for memory health

    # Image Processing Settings
    # Max image size in MB before downscaling (e.g., 3 = downscale if > 3MB)
    OCR_MAX_IMAGE_SIZE_MB: int = 3
    
    # JPEG quality for downscaling (1-100, lower = smaller file, faster processing)
    OCR_DOWNSCALE_QUALITY: int = 75

    # Field Validators (Phase C - Validation & Hardening)
    # Enable field-level validators to normalize and adjust confidence on extracted values
    # Validators: date, phone, checkbox, amount, required
    # Impact: +2-5% confidence boost, normalizes values (e.g., phone to +639XXXXXXXXX)
    ENABLE_FIELD_VALIDATORS: bool = True

    # Template-first OCR pipeline (hard cutover)
    # Deterministic template extraction is the primary strategy, with targeted AI
    # only for unresolved fields.
    TEMPLATE_FIRST_OCR: bool = True
    
    # Pattern-Based Field Extraction (Phase C Option A - Increase extraction rate)
    # Search raw OCR lines for missed fields using regex patterns (date, phone, amount, checkbox)
    # Used when Groq AI extraction misses fields
    # Impact: +20-40% additional fields extraction (e.g., 16/55 → 25-35/55)
    ENABLE_PATTERN_EXTRACTION: bool = True
    PATTERN_EXTRACTION_MIN_CONFIDENCE: float = 0.45  # Skip patterns below this confidence

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
