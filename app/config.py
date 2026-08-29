from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

from app.core.retry import RetryPolicy
from app.core.circuit_breaker import CircuitBreakerConfig


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
    backend_startup_max_attempts: int = Field(default=5, validation_alias=AliasChoices("BACKEND_STARTUP_MAX_ATTEMPTS"))
    backend_startup_retry_delay_seconds: float = Field(default=2.0, validation_alias=AliasChoices("BACKEND_STARTUP_RETRY_DELAY_SECONDS"))
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

    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL"))

    # Zone the business books in; must match the backend's CAL_TIMEZONE. Bare
    # clock times from a visitor ("3pm") are resolved in this zone, not UTC.
    cal_timezone: str = Field(default="UTC", validation_alias=AliasChoices("CAL_TIMEZONE"))

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

    # ---- Per-provider retry configuration (Issue #1c) ----
    # Default retry policy (applies to any unlisted provider).
    llm_retry_default_attempts: int = Field(
        default=3, validation_alias=AliasChoices("LLM_RETRY__DEFAULT__ATTEMPTS")
    )
    llm_retry_default_base_delay: float = Field(
        default=1.0, validation_alias=AliasChoices("LLM_RETRY__DEFAULT__BASE_DELAY_SECONDS")
    )
    llm_retry_default_max_delay: float = Field(
        default=30.0, validation_alias=AliasChoices("LLM_RETRY__DEFAULT__MAX_DELAY_SECONDS")
    )
    # Ollama retry policy overrides.
    llm_retry_ollama_attempts: int | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OLLAMA__ATTEMPTS")
    )
    llm_retry_ollama_base_delay: float | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OLLAMA__BASE_DELAY_SECONDS")
    )
    llm_retry_ollama_max_delay: float | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OLLAMA__MAX_DELAY_SECONDS")
    )
    # OpenAI retry policy overrides.
    llm_retry_openai_attempts: int | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OPENAI__ATTEMPTS")
    )
    llm_retry_openai_base_delay: float | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OPENAI__BASE_DELAY_SECONDS")
    )
    llm_retry_openai_max_delay: float | None = Field(
        default=None, validation_alias=AliasChoices("LLM_RETRY__OPENAI__MAX_DELAY_SECONDS")
    )

    # ---- Per-provider circuit breaker configuration (Issue #1d) ----
    circuit_breaker_default_failure_threshold: int = Field(
        default=5, validation_alias=AliasChoices("CIRCUIT_BREAKER__DEFAULT__FAILURE_THRESHOLD")
    )
    circuit_breaker_default_reset_timeout: float = Field(
        default=30.0, validation_alias=AliasChoices("CIRCUIT_BREAKER__DEFAULT__RESET_TIMEOUT_SECONDS")
    )
    circuit_breaker_ollama_failure_threshold: int | None = Field(
        default=None, validation_alias=AliasChoices("CIRCUIT_BREAKER__OLLAMA__FAILURE_THRESHOLD")
    )
    circuit_breaker_ollama_reset_timeout: float | None = Field(
        default=None, validation_alias=AliasChoices("CIRCUIT_BREAKER__OLLAMA__RESET_TIMEOUT_SECONDS")
    )
    circuit_breaker_openai_failure_threshold: int | None = Field(
        default=None, validation_alias=AliasChoices("CIRCUIT_BREAKER__OPENAI__FAILURE_THRESHOLD")
    )
    circuit_breaker_openai_reset_timeout: float | None = Field(
        default=None, validation_alias=AliasChoices("CIRCUIT_BREAKER__OPENAI__RESET_TIMEOUT_SECONDS")
    )

    # ---- Trace PII retention (Issue #6) ----
    ai_trace_retention_days: int = Field(
        default=30, validation_alias=AliasChoices("AI_TRACE_RETENTION_DAYS")
    )

    # ---- Dev-mode / ensure_schema gating (Issue #2 / #5) ----
    dev_mode: bool | None = Field(
        default=None, validation_alias=AliasChoices("DEV_MODE")
    )
    transcription_ensure_schema: bool | None = Field(
        default=None, validation_alias=AliasChoices("TRANSCRIPTION_ENSURE_SCHEMA")
    )

    # Persist the shared RAG index on disk so requests never rebuild it.
    vector_store: str = Field(default="faiss", validation_alias=AliasChoices("VECTOR_STORE"))
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
    rag_sync_interval_hours: int = Field(default=12, validation_alias=AliasChoices("RAG_SYNC_INTERVAL_HOURS"))
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
    # AssemblyAI model config. Stored as a comma-separated string in the env var
    # (pydantic-settings would otherwise JSON-decode a list[str] env value);
    # use the `assemblyai_speech_models` property to get the parsed ordered
    # fallback list. language_code is the transcription language.
    # e.g. ASSEMBLYAI_SPEECH_MODELS="universal-3-pro,universal-2".
    assemblyai_speech_models_raw: str = Field(
        default="universal-3-pro,universal-2",
        validation_alias=AliasChoices("ASSEMBLYAI_SPEECH_MODELS"),
    )
    assemblyai_language_code: str = Field(
        default="en",
        validation_alias=AliasChoices("ASSEMBLYAI_LANGUAGE_CODE"),
    )

    @property
    def assemblyai_speech_models(self) -> list[str]:
        """Ordered AssemblyAI speech-model fallback list, parsed from the
        comma-separated ``ASSEMBLYAI_SPEECH_MODELS`` setting."""
        return [item.strip() for item in self.assemblyai_speech_models_raw.split(",") if item.strip()]

    class Config:
        env_file = ENV_FILE
        case_sensitive = False
        extra = "ignore"

    # ----- Computed helpers -----

    @property
    def is_dev(self) -> bool:
        """True when the service is running in a development / test environment."""
        if self.dev_mode is not None:
            return self.dev_mode
        return self.app_env.strip().lower() in {"development", "dev", "test"}

    @property
    def should_ensure_transcription_schema(self) -> bool:
        """Whether ``TranscriptionService.ensure_schema()`` should run DDL.

        In non-dev the service relies on the Alembic migration.
        """
        if self.transcription_ensure_schema is not None:
            return self.transcription_ensure_schema
        return self.is_dev

    def retry_policy_for(self, provider: str) -> RetryPolicy:
        """Resolve the retry policy for *provider*, falling back to defaults."""
        p = provider.strip().lower()
        if p == "ollama":
            return RetryPolicy(
                attempts=self.llm_retry_ollama_attempts or self.llm_retry_default_attempts,
                base_delay=self.llm_retry_ollama_base_delay if self.llm_retry_ollama_base_delay is not None else self.llm_retry_default_base_delay,
                max_delay=self.llm_retry_ollama_max_delay if self.llm_retry_ollama_max_delay is not None else self.llm_retry_default_max_delay,
            )
        if p == "openai":
            return RetryPolicy(
                attempts=self.llm_retry_openai_attempts or self.llm_retry_default_attempts,
                base_delay=self.llm_retry_openai_base_delay if self.llm_retry_openai_base_delay is not None else self.llm_retry_default_base_delay,
                max_delay=self.llm_retry_openai_max_delay if self.llm_retry_openai_max_delay is not None else self.llm_retry_default_max_delay,
            )
        return RetryPolicy(
            attempts=self.llm_retry_default_attempts,
            base_delay=self.llm_retry_default_base_delay,
            max_delay=self.llm_retry_default_max_delay,
        )

    def circuit_breaker_config_for(self, provider: str) -> CircuitBreakerConfig:
        """Resolve the circuit breaker config for *provider*, falling back to defaults."""
        p = provider.strip().lower()
        if p == "ollama":
            return CircuitBreakerConfig(
                failure_threshold=self.circuit_breaker_ollama_failure_threshold or self.circuit_breaker_default_failure_threshold,
                reset_timeout_seconds=self.circuit_breaker_ollama_reset_timeout if self.circuit_breaker_ollama_reset_timeout is not None else self.circuit_breaker_default_reset_timeout,
            )
        if p == "openai":
            return CircuitBreakerConfig(
                failure_threshold=self.circuit_breaker_openai_failure_threshold or self.circuit_breaker_default_failure_threshold,
                reset_timeout_seconds=self.circuit_breaker_openai_reset_timeout if self.circuit_breaker_openai_reset_timeout is not None else self.circuit_breaker_default_reset_timeout,
            )
        return CircuitBreakerConfig(
            failure_threshold=self.circuit_breaker_default_failure_threshold,
            reset_timeout_seconds=self.circuit_breaker_default_reset_timeout,
        )


settings = Settings()
