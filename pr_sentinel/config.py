import os
from enum import Enum
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Settings
    llm_model: str = "gemini/gemini-1.5-flash"
    llm_temperature: float = 0.2
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_api_base: Optional[str] = "http://localhost:11434"

    # GitHub Settings
    github_token: Optional[str] = None

    # Review Settings
    severity_threshold: Severity = Severity.LOW
    enable_auto_fix: bool = True
    auto_generate_tests: bool = True
    max_diff_lines: int = 2500


# Singleton settings instance
settings = Config()
