from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AutoCRM AI Agent Service"
    app_env: str = "development"
    log_level: str = "info"

    autocrm_base_url: str = "http://localhost:8000"
    autocrm_auth_email: str = ""
    autocrm_auth_password: str = ""
    autocrm_auth_timeout: int = 10

    database_url: str = ""

    scheduler_enabled: bool = True

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""

    vector_store: str = "faiss"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
