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

    # AI Vision (supports OpenAI and Groq)
    AI_PROVIDER: str = "groq"  # "groq" or "openai"
    AI_API_KEY: str = ""
    AI_API_KEY_1: str = ""
    AI_API_KEY_2: str = ""
    AI_API_KEY_3: str = ""
    AI_BASE_URL: str = "https://api.groq.com/openai/v1"
    AI_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
