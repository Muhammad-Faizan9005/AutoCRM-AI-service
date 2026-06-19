from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import settings
from app.db.pool import get_pool
from app.schemas.events import AgentEventIn
from app.schemas.transcriptions import RecordingReadyIn
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)
_schema_ready = False
_schema_lock = asyncio.Lock()


class TranscriptionService:
    STATUSES = {"pending", "processing", "completed", "failed"}

    async def ensure_schema(self) -> None:
        global _schema_ready
        if _schema_ready:
            return
        async with _schema_lock:
            if _schema_ready:
                return
            await self._ensure_schema()
            _schema_ready = True

    async def _ensure_schema(self) -> None:
        await get_pool().execute(
            """
            CREATE TABLE IF NOT EXISTS ai_meeting_transcripts (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                recording_id UUID NOT NULL UNIQUE,
                meeting_id UUID,
                entity_id UUID,
                entity_type VARCHAR(50) NOT NULL DEFAULT 'meeting',
                source_type VARCHAR(30) NOT NULL DEFAULT 'local_path',
                recording_path TEXT,
                recording_url TEXT,
                assemblyai_transcript_id TEXT,
                transcript_text TEXT,
                meeting_summary TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                error TEXT,
                last_attempted_at TIMESTAMPTZ,
                next_retry_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_ai_meeting_transcripts_status
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                CONSTRAINT ck_ai_meeting_transcripts_source_type
                    CHECK (source_type IN ('local_path', 'url'))
            )
            """
        )
        await get_pool().execute("ALTER TABLE ai_meeting_transcripts ADD COLUMN IF NOT EXISTS meeting_summary TEXT")
        await get_pool().execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_status ON ai_meeting_transcripts(status)"
        )
        await get_pool().execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_meeting_id ON ai_meeting_transcripts(meeting_id)"
        )
        await get_pool().execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_last_attempted_at ON ai_meeting_transcripts(last_attempted_at)"
        )

    async def accept_recording(self, payload: RecordingReadyIn) -> dict[str, Any]:
        await self.ensure_schema()
        stale = await self._mark_stale_if_needed(payload.recording_id)
        existing = await self.get_job(payload.recording_id)
        if existing and existing["status"] == "completed":
            return dict(existing)
        metadata = {**(payload.metadata or {})}
        if payload.actor_id:
            metadata.setdefault("actor_id", payload.actor_id)

        if existing is None:
            row = await get_pool().fetchrow(
                """
                INSERT INTO ai_meeting_transcripts (
                    recording_id, meeting_id, entity_id, entity_type, source_type,
                    recording_path, recording_url, status, max_attempts, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8, $9::jsonb)
                RETURNING *
                """,
                payload.recording_id,
                payload.meeting_id,
                payload.entity_id,
                payload.entity_type,
                payload.source_type,
                payload.recording_path,
                payload.recording_url,
                settings.transcription_max_attempts,
                self._json(metadata),
            )
            await self._update_call_session_status(payload.recording_id, "pending")
            return dict(row)

        if stale or existing["status"] in {"failed", "pending"}:
            row = await get_pool().fetchrow(
                """
                UPDATE ai_meeting_transcripts
                SET meeting_id=COALESCE($2, meeting_id),
                    entity_id=COALESCE($3, entity_id),
                    entity_type=COALESCE($4, entity_type),
                    source_type=$5,
                    recording_path=COALESCE($6, recording_path),
                    recording_url=COALESCE($7, recording_url),
                    metadata=COALESCE(metadata, '{}'::jsonb) || $8::jsonb,
                    status=CASE WHEN status='failed' AND attempt_count >= max_attempts THEN status ELSE 'pending' END,
                    updated_at=NOW()
                WHERE recording_id=$1
                RETURNING *
                """,
                payload.recording_id,
                payload.meeting_id,
                payload.entity_id,
                payload.entity_type,
                payload.source_type,
                payload.recording_path,
                payload.recording_url,
                self._json(metadata),
            )
            await self._update_call_session_status(payload.recording_id, row["status"])
            return dict(row)

        return dict(existing)

    async def process_recording(self, recording_id: UUID, *, force: bool = False) -> None:
        await self.ensure_schema()
        await self._mark_stale_if_needed(recording_id)
        job = await self.get_job(recording_id)
        if job is None:
            logger.warning("transcription_job_missing recording_id=%s", recording_id)
            return
        if job["status"] == "completed" and not force:
            return
        if job["status"] == "processing" and not force:
            if not self._is_stale(job):
                return
        if job["attempt_count"] >= job["max_attempts"] and not force:
            await self._set_failed(recording_id, "Maximum transcription attempts reached")
            return

        delay_seconds = max(0, settings.transcription_retry_delay_seconds)
        while True:
            job = await self._start_attempt(recording_id)
            if job is None:
                return
            try:
                transcript = await self._transcribe(job)
                summary = await self._generate_meeting_summary(transcript.get("text") or "")
                await self._complete_job(recording_id, transcript, summary)
                await self._trigger_meeting_intel(recording_id)
                return
            except Exception as exc:
                logger.exception("transcription_attempt_failed recording_id=%s", recording_id)
                job = await self._record_attempt_failure(recording_id, str(exc))
                if job is None or job["status"] == "failed":
                    return
                if delay_seconds:
                    await asyncio.sleep(delay_seconds)

    async def retry_recording(self, recording_id: UUID, *, force: bool = False) -> dict[str, Any]:
        await self.ensure_schema()
        await self._mark_stale_if_needed(recording_id)
        job = await self.get_job(recording_id)
        if job is None:
            raise ValueError("Transcript job not found")
        if job["status"] == "completed" and not force:
            return dict(job)
        if force and job["status"] != "completed":
            await get_pool().execute(
                """
                UPDATE ai_meeting_transcripts
                SET status='pending', error=NULL, next_retry_at=NULL, updated_at=NOW()
                WHERE recording_id=$1
                """,
                recording_id,
            )
        elif job["status"] == "failed" and job["attempt_count"] >= job["max_attempts"]:
            await get_pool().execute(
                """
                UPDATE ai_meeting_transcripts
                SET status='pending', attempt_count=0, error=NULL, next_retry_at=NULL, updated_at=NOW()
                WHERE recording_id=$1
                """,
                recording_id,
            )
        return dict(await self.get_job(recording_id))

    async def sweep_stale_processing_jobs(self) -> int:
        await self.ensure_schema()
        rows = await get_pool().fetch(
            """
            SELECT recording_id, attempt_count, max_attempts
            FROM ai_meeting_transcripts
            WHERE status='processing'
              AND last_attempted_at IS NOT NULL
              AND last_attempted_at < NOW() - ($1::int * INTERVAL '1 minute')
            LIMIT 25
            """,
            settings.transcription_processing_timeout_minutes,
        )
        count = 0
        for row in rows:
            recording_id = row["recording_id"]
            message = f"Processing timed out after {settings.transcription_processing_timeout_minutes} minutes"
            if row["attempt_count"] >= row["max_attempts"]:
                await self._set_failed(recording_id, message)
                count += 1
                continue
            await get_pool().execute(
                """
                UPDATE ai_meeting_transcripts
                SET status='pending', error=$2, updated_at=NOW()
                WHERE recording_id=$1 AND status='processing'
                """,
                recording_id,
                message,
            )
            await self._update_call_session_status(recording_id, "pending")
            asyncio.create_task(self.process_recording(recording_id))
            count += 1
        return count

    async def get_job(self, recording_id: UUID) -> dict[str, Any] | None:
        await self.ensure_schema()
        row = await get_pool().fetchrow("SELECT * FROM ai_meeting_transcripts WHERE recording_id=$1", recording_id)
        return dict(row) if row else None

    async def _start_attempt(self, recording_id: UUID) -> dict[str, Any] | None:
        row = await get_pool().fetchrow(
            """
            UPDATE ai_meeting_transcripts
            SET status='processing',
                attempt_count=attempt_count + 1,
                last_attempted_at=NOW(),
                next_retry_at=NULL,
                error=NULL,
                updated_at=NOW()
            WHERE recording_id=$1
              AND (status IN ('pending', 'failed') OR status='processing')
              AND attempt_count < max_attempts
            RETURNING *
            """,
            recording_id,
        )
        if row:
            await self._update_call_session_status(recording_id, "processing")
        return dict(row) if row else None

    async def _transcribe(self, job: dict[str, Any]) -> dict[str, str | None]:
        try:
            import assemblyai as aai
        except ImportError as exc:
            raise RuntimeError("assemblyai package is not installed. Run: pip install assemblyai") from exc

        if not settings.assemblyai_api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is not configured")

        audio_source = self._resolve_audio_source(job)

        def _run_transcription():
            aai.settings.api_key = settings.assemblyai_api_key
            try:
                config = aai.TranscriptionConfig(
                    speech_models=["universal-3-pro", "universal-2"],
                    language_code="en",
                )
            except TypeError:
                # Older SDKs available on some package indexes do not expose the
                # newer speech_models fallback-list parameter yet. Keep the
                # pipeline working with English transcription and the SDK default
                # speech model instead of failing at runtime.
                config = aai.TranscriptionConfig(language_code="en")
            return aai.Transcriber(config=config).transcribe(audio_source)

        transcript = await asyncio.to_thread(_run_transcription)
        status = str(getattr(transcript, "status", "") or "").lower()
        if status == "error":
            raise RuntimeError(getattr(transcript, "error", None) or "AssemblyAI transcription failed")
        text = getattr(transcript, "text", None)
        if not text:
            raise RuntimeError("AssemblyAI returned an empty transcript")
        return {"id": str(getattr(transcript, "id", "") or "") or None, "text": text}

    def _resolve_audio_source(self, job: dict[str, Any]) -> str:
        source_type = str(job.get("source_type") or "local_path")
        if source_type == "url":
            url = str(job.get("recording_url") or "").strip()
            if not url:
                raise ValueError("recording_url is missing")
            return url

        raw_path = str(job.get("recording_path") or "").strip()
        if not raw_path:
            raise ValueError("recording_path is missing")

        base_dir = self._recordings_dir()
        requested = Path(raw_path)
        candidates: list[Path] = []
        if requested.is_absolute():
            candidates.append(requested)
        else:
            candidates.extend([base_dir / requested.name, base_dir / requested])

        for candidate in candidates:
            resolved = candidate.resolve()
            if not self._is_within(resolved, base_dir):
                continue
            if resolved.is_file():
                return str(resolved)
        raise FileNotFoundError(f"Recording file not found under {base_dir}: {raw_path}")

    def _recordings_dir(self) -> Path:
        configured = str(settings.transcription_recordings_dir or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        project_root = Path(__file__).resolve().parents[4]
        candidates = [
            project_root / "AutoCRM" / "storage" / "recordings",
            project_root / "storage" / "recordings",
            Path.cwd() / "storage" / "recordings",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return candidates[0].resolve()

    def _is_within(self, path: Path, base_dir: Path) -> bool:
        try:
            path.relative_to(base_dir)
            return True
        except ValueError:
            return False

    async def _generate_meeting_summary(self, transcript_text: str) -> str:
        if not transcript_text.strip():
            return ""
        prompt = (
            "Summarize this CRM meeting transcript in 2-4 concise sentences. "
            "If it is only greetings, audio testing, or small talk, say that no meaningful business discussion occurred. "
            "Do not invent customer requirements or next steps.\n\n"
            f"Transcript:\n{transcript_text}"
        )
        try:
            summary = await LLMService().generate(prompt=prompt, workflow=None, context="", model_tier="small")
            return str(summary or "").strip()
        except Exception:
            return "Meeting summary could not be generated automatically."

    async def _complete_job(self, recording_id: UUID, transcript: dict[str, str | None], meeting_summary: str = "") -> None:
        await get_pool().execute(
            """
            UPDATE ai_meeting_transcripts
            SET status='completed',
                assemblyai_transcript_id=$2,
                transcript_text=$3,
                meeting_summary=$4,
                error=NULL,
                completed_at=NOW(),
                updated_at=NOW()
            WHERE recording_id=$1
            """,
            recording_id,
            transcript.get("id"),
            transcript.get("text"),
            meeting_summary,
        )
        await self._update_call_session_transcript(recording_id, transcript.get("text") or "", meeting_summary)

    async def _record_attempt_failure(self, recording_id: UUID, error: str) -> dict[str, Any] | None:
        row = await get_pool().fetchrow(
            """
            UPDATE ai_meeting_transcripts
            SET status=CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'pending' END,
                error=$2,
                next_retry_at=CASE WHEN attempt_count >= max_attempts THEN NULL ELSE NOW() + ($3::int * INTERVAL '1 second') END,
                updated_at=NOW()
            WHERE recording_id=$1
            RETURNING *
            """,
            recording_id,
            error[:4000],
            settings.transcription_retry_delay_seconds,
        )
        if row:
            await self._update_call_session_status(recording_id, row["status"])
        return dict(row) if row else None

    async def _set_failed(self, recording_id: UUID, error: str) -> None:
        await get_pool().execute(
            """
            UPDATE ai_meeting_transcripts
            SET status='failed', error=$2, updated_at=NOW()
            WHERE recording_id=$1
            """,
            recording_id,
            error[:4000],
        )
        await self._update_call_session_status(recording_id, "failed")

    async def _mark_stale_if_needed(self, recording_id: UUID) -> bool:
        row = await get_pool().fetchrow(
            """
            UPDATE ai_meeting_transcripts
            SET status=CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'pending' END,
                error=$2,
                updated_at=NOW()
            WHERE recording_id=$1
              AND status='processing'
              AND last_attempted_at IS NOT NULL
              AND last_attempted_at < NOW() - ($3::int * INTERVAL '1 minute')
            RETURNING status
            """,
            recording_id,
            f"Processing timed out after {settings.transcription_processing_timeout_minutes} minutes",
            settings.transcription_processing_timeout_minutes,
        )
        if row:
            await self._update_call_session_status(recording_id, row["status"])
        return row is not None

    def _is_stale(self, job: dict[str, Any]) -> bool:
        last_attempted = job.get("last_attempted_at")
        if not last_attempted:
            return False
        if last_attempted.tzinfo is None:
            last_attempted = last_attempted.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_attempted
        return elapsed.total_seconds() > settings.transcription_processing_timeout_minutes * 60

    async def _trigger_meeting_intel(self, recording_id: UUID) -> None:
        job = await self.get_job(recording_id)
        if not job or not job.get("transcript_text"):
            return
        entity_id = job.get("entity_id") or job.get("meeting_id") or job.get("recording_id")
        entity_type = str(job.get("entity_type") or "meeting")
        metadata_raw = job.get("metadata") or {}
        if isinstance(metadata_raw, str):
            try:
                import json

                metadata = json.loads(metadata_raw)
            except Exception:
                metadata = {}
        else:
            metadata = dict(metadata_raw)
        payload = AgentEventIn(
            event_type="meeting_complete",
            entity_id=entity_id,
            entity_type=entity_type,
            actor_id=str(metadata.get("actor_id") or "") or None,
            metadata={
                **metadata,
                "source": "transcription_service",
                "recording_id": str(job["recording_id"]),
                "meeting_id": str(job.get("meeting_id") or ""),
                "transcript": job["transcript_text"],
                "assemblyai_transcript_id": job.get("assemblyai_transcript_id"),
            },
        )
        await AgentOrchestrator().handle_event(payload)

    async def _update_call_session_status(self, recording_id: UUID, status: str) -> None:
        if status not in self.STATUSES:
            return
        try:
            await get_pool().execute(
                """
                UPDATE call_sessions
                SET processing_status=$2, updated_at=NOW()
                WHERE id=$1
                """,
                recording_id,
                status,
            )
        except Exception:
            logger.debug("call_sessions status update skipped", exc_info=True)

    async def _update_call_session_transcript(self, recording_id: UUID, transcript_text: str, meeting_summary: str = "") -> None:
        try:
            await get_pool().execute(
                """
                UPDATE call_sessions
                SET transcript=$2, meeting_summary=$3, processing_status='completed', updated_at=NOW()
                WHERE id=$1
                """,
                recording_id,
                transcript_text,
                meeting_summary,
            )
        except Exception:
            logger.debug("call_sessions transcript update skipped", exc_info=True)

    def _json(self, value: dict[str, Any]) -> str:
        import json

        return json.dumps(value, default=str)
