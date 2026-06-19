from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AutoCRM AI Agent Service"
    app_env: str = "development"
    log_level: str = "info"

    autocrm_base_url: str = "http://localhost:8000"
    autocrm_auth_timeout: int = 10

    # New: AI service-to-backend auth (preferred over email/password)
    # Set these after issuing a credential via POST /api/agent/ai-agents/{key}/credentials
    autocrm_ai_agent_key: str = ""      # e.g. action_manager_agent
    autocrm_ai_service_token: str = ""  # raw token returned once on credential creation

    # Legacy: email/password login (kept for backward compat; ignored when ai_agent_key is set)
    autocrm_auth_email: str = ""
    autocrm_auth_password: str = ""

    database_url: str = ""

    scheduler_enabled: bool = True

    llm_provider: str = "ollama"
    llm_model_small: str = "gemma2:2b"
    llm_model_large: str = "glm-4.6:cloud"
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_enabled: bool = True

    vector_store: str = "memory"
    embedding_provider: str = "local"
    embedding_dimensions: int = 384
    huggingface_api_token: str = ""
    huggingface_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    huggingface_api_base_url: str = "https://api-inference.huggingface.co"
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 120
    rag_top_k: int = 5

    assemblyai_api_key: str = ""
    transcription_recordings_dir: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TRANSCRIPTION_RECORDINGS_DIR",
            "AUTOCRM_RECORDINGS_DIR",
            "CALL_RECORDINGS_DIR",
            "RECORDINGS_STORAGE_DIR",
        ),
    )
    transcription_max_attempts: int = 3
    transcription_retry_delay_seconds: int = 5
    transcription_processing_timeout_minutes: int = 30
    transcription_stale_sweep_interval_minutes: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
