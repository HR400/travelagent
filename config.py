"""Configuration management for production deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    """Production configuration with validation and environment-specific settings."""

    # API Keys
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    tavily_api_key: str | None = None

    # API Configuration
    openai_base_url: str | None = None
    openai_model: str | None = None

    # Budget Settings
    hard_cap: float = 800.0

    # ReAct Loop Settings
    max_steps: int = 15
    max_tokens: int = 800
    temperature: float = 0.2

    # Timeout & Retry Settings
    api_timeout: int = 30
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    initial_retry_delay: float = 1.0

    # Token Management
    max_context_window: int = 6

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Health Check
    health_check_enabled: bool = True

    # MongoDB Settings
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "travelagent"
    mongo_timeout_ms: int = 2000

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "Config":
        """Load configuration from environment variables with validation."""
        if env_path and env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)

        config = cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL"),
            openai_model=os.environ.get("OPENAI_MODEL"),
            hard_cap=float(os.environ.get("HARD_CAP", "800.0")),
            max_steps=int(os.environ.get("MAX_STEPS", "15")),
            max_tokens=int(os.environ.get("MAX_TOKENS", "800")),
            temperature=float(os.environ.get("TEMPERATURE", "0.2")),
            api_timeout=int(os.environ.get("API_TIMEOUT", "30")),
            max_retries=int(os.environ.get("MAX_RETRIES", "3")),
            retry_backoff_factor=float(os.environ.get("RETRY_BACKOFF_FACTOR", "2.0")),
            initial_retry_delay=float(os.environ.get("INITIAL_RETRY_DELAY", "1.0")),
            max_context_window=int(os.environ.get("MAX_CONTEXT_WINDOW", "6")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            log_format=os.environ.get("LOG_FORMAT", "json"),
            health_check_enabled=os.environ.get("HEALTH_CHECK_ENABLED", "true").lower() == "true",
            mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db_name=os.environ.get("MONGO_DB_NAME", "travelagent"),
            mongo_timeout_ms=int(os.environ.get("MONGO_TIMEOUT_MS", "2000")),
        )

        config.validate()
        return config

    def validate(self) -> None:
        """Validate required configuration values."""
        errors = []

        # At least one API key must be set
        if not self.openai_api_key and not self.groq_api_key:
            errors.append("Either OPENAI_API_KEY or GROQ_API_KEY must be set")

        # Tavily API key is required for search functionality
        if not self.tavily_api_key:
            errors.append("TAVILY_API_KEY must be set")

        # Validate numeric ranges
        if not (0 <= self.temperature <= 2):
            errors.append(f"Temperature must be between 0 and 2, got {self.temperature}")

        if self.max_steps < 1 or self.max_steps > 100:
            errors.append(f"max_steps must be between 1 and 100, got {self.max_steps}")

        if self.api_timeout < 5 or self.api_timeout > 300:
            errors.append(f"api_timeout must be between 5 and 300 seconds, got {self.api_timeout}")

        if self.hard_cap <= 0:
            errors.append(f"hard_cap must be positive, got {self.hard_cap}")

        if errors:
            raise ConfigurationError("Configuration validation failed:\n" + "\n".join(errors))

    def has_api_credentials(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.openai_api_key or self.groq_api_key)

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary (excluding sensitive data)."""
        return {
            "hard_cap": self.hard_cap,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "api_timeout": self.api_timeout,
            "max_retries": self.max_retries,
            "retry_backoff_factor": self.retry_backoff_factor,
            "max_context_window": self.max_context_window,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "health_check_enabled": self.health_check_enabled,
            "has_openai_key": bool(self.openai_api_key),
            "has_groq_key": bool(self.groq_api_key),
            "has_tavily_key": bool(self.tavily_api_key),
            "mongo_uri": self.mongo_uri,
            "mongo_db_name": self.mongo_db_name,
            "mongo_timeout_ms": self.mongo_timeout_ms,
        }


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""

    pass


# Global configuration instance (lazy-loaded)
_config: Config | None = None


def get_config(env_path: Path | None = None) -> Config:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        if env_path is None:
            env_path = Path(__file__).resolve().parent / ".env"
        _config = Config.from_env(env_path)
    return _config


def reset_config() -> None:
    """Reset global configuration (useful for testing)."""
    global _config
    _config = None
