from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    app_name: str = "AutoCRM AI Agent Service"
    app_env: str = "development"
    log_level: str = "info"

    autocrm_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("AUTOCRM_BASE_URL", "AUTOCRM_BACKEND_URL"),
    )
    autocrm_auth_timeout: int = Field(default=10, validation_alias=AliasChoices("AUTOCRM_AUTH_TIMEOUT"))
    autocrm_batch_timeout: int = Field(default=60, validation_alias=AliasChoices("AUTOCRM_BATCH_TIMEOUT"))
    ai_backend_connectivity_required: bool = Field(
        default=True,
        validation_alias=AliasChoices("AI_BACKEND_CONNECTIVITY_REQUIRED"),
    )

    # AI service-to-backend auth.
    # Set token after issuing a credential from Profile Settings -> Developer Mode.
    # Agent key is optional runtime attribution, not the token owner.
    autocrm_ai_agent_key: str = Field(default="", validation_alias=AliasChoices("AUTOCRM_AI_AGENT_KEY"))
    autocrm_ai_service_token: str = Field(default="", validation_alias=AliasChoices("AUTOCRM_AI_SERVICE_TOKEN"))
    ai_service_webhook_token: str = Field(default="", validation_alias=AliasChoices("AI_SERVICE_WEBHOOK_TOKEN"))

    # Legacy human-login auth is no longer supported after cookie auth migration.
    autocrm_auth_email: str = Field(default="", validation_alias=AliasChoices("AUTOCRM_AUTH_EMAIL"))
    autocrm_auth_password: str = Field(default="", validation_alias=AliasChoices("AUTOCRM_AUTH_PASSWORD"))

    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL"))

    # Enables or disables all AI service scheduled background jobs.
    scheduler_enabled: bool = Field(default=True, validation_alias=AliasChoices("SCHEDULER_ENABLED"))
    # Hour of day when daily summary workflows are queued.
    scheduler_daily_summary_hour: int = Field(default=8, validation_alias=AliasChoices("SCHEDULER_DAILY_SUMMARY_HOUR"))
    # Minute of the hour when daily summary workflows are queued.
    scheduler_daily_summary_minute: int = Field(default=0, validation_alias=AliasChoices("SCHEDULER_DAILY_SUMMARY_MINUTE"))
    # How often lead scores are recalculated by the scheduler.
    scheduler_lead_score_sweep_interval_hours: int = Field(
        default=6,
        validation_alias=AliasChoices("SCHEDULER_LEAD_SCORE_SWEEP_INTERVAL_HOURS"),
    )
    # How often stale lead follow-up workflows are scanned and queued.
    scheduler_stale_lead_sweep_interval_hours: int = Field(
        default=6,
        validation_alias=AliasChoices("SCHEDULER_STALE_LEAD_SWEEP_INTERVAL_HOURS"),
    )
    # How often deal risk workflows are scanned and queued.
    scheduler_deal_risk_sweep_interval_hours: int = Field(
        default=6,
        validation_alias=AliasChoices("SCHEDULER_DEAL_RISK_SWEEP_INTERVAL_HOURS"),
    )
    # Maximum stale lead candidates processed per scheduler run.
    scheduler_stale_lead_candidate_limit: int = Field(
        default=500,
        validation_alias=AliasChoices("SCHEDULER_STALE_LEAD_CANDIDATE_LIMIT"),
    )
    # Maximum deal risk candidates processed per scheduler run.
    scheduler_deal_risk_candidate_limit: int = Field(
        default=500,
        validation_alias=AliasChoices("SCHEDULER_DEAL_RISK_CANDIDATE_LIMIT"),
    )
    # Maximum users processed for daily summaries per scheduler run.
    scheduler_summary_candidate_limit: int = Field(
        default=500,
        validation_alias=AliasChoices("SCHEDULER_SUMMARY_CANDIDATE_LIMIT"),
    )
    scheduler_task_deadline_sweep_interval_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("SCHEDULER_TASK_DEADLINE_SWEEP_INTERVAL_MINUTES"),
    )
    scheduler_task_deadline_candidate_limit: int = Field(
        default=100,
        validation_alias=AliasChoices("SCHEDULER_TASK_DEADLINE_CANDIDATE_LIMIT"),
    )
    # Minimum hours before creating another AI follow-up task for the same lead.
    lead_nudge_task_cooldown_hours: int = Field(
        default=72,
        validation_alias=AliasChoices("LEAD_NUDGE_TASK_COOLDOWN_HOURS"),
    )

    llm_provider: str = "ollama"
    llm_model_small: str = "minimax-m3:cloud"
    llm_model_large: str = "minimax-m3:cloud"
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
    rag_index_dir: str = "storage/faiss"
    # Enables or disables scheduled RAG index synchronization.
    rag_sync_enabled: bool = Field(default=True, validation_alias=AliasChoices("RAG_SYNC_ENABLED"))
    # How often the RAG index sync runs.
    rag_sync_interval_hours: int = Field(default=24, validation_alias=AliasChoices("RAG_SYNC_INTERVAL_HOURS"))
    # Maximum backend documents fetched in one RAG sync batch.
    rag_sync_batch_size: int = Field(default=100, validation_alias=AliasChoices("RAG_SYNC_BATCH_SIZE"))
    # Small delay between indexing individual RAG documents.
    rag_sync_min_delay_seconds: float = Field(default=0.05, validation_alias=AliasChoices("RAG_SYNC_MIN_DELAY_SECONDS"))
    # File used to remember the latest synced backend document timestamp.
    rag_sync_state_file: str = Field(
        default="storage/rag_sync_state.json",
        validation_alias=AliasChoices("RAG_SYNC_STATE_FILE"),
    )

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
    transcription_stale_sweep_interval_minutes: int = 30

    class Config:
        env_file = ENV_FILE
        case_sensitive = False
        extra = "ignore"


settings = Settings()
