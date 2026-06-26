from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.dependencies import require_webhook_token
from app.schemas.transcriptions import RecordingReadyIn, RecordingReadyResponse, TranscriptJobOut
from app.services.transcription_service import TranscriptionService


router = APIRouter()


@router.post(
    "/recording-ready",
    response_model=RecordingReadyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_webhook_token)],
)
async def recording_ready(payload: RecordingReadyIn, background_tasks: BackgroundTasks) -> RecordingReadyResponse:
    service = TranscriptionService()
    job = await service.accept_recording(payload)
    if job["status"] in {"pending", "failed"} and job["attempt_count"] < job["max_attempts"]:
        background_tasks.add_task(service.process_recording, payload.recording_id)
    return RecordingReadyResponse(status="accepted", recording_id=payload.recording_id, job_status=job["status"])


@router.get("/{recording_id}", response_model=TranscriptJobOut)
async def get_transcription_job(recording_id: UUID) -> TranscriptJobOut:
    service = TranscriptionService()
    job = await service.get_job(recording_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript job not found")
    return TranscriptJobOut(**job)


@router.post(
    "/{recording_id}/retry",
    response_model=RecordingReadyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_webhook_token)],
)
async def retry_transcription_job(
    recording_id: UUID,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
) -> RecordingReadyResponse:
    service = TranscriptionService()
    try:
        job = await service.retry_recording(recording_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if job["status"] != "completed":
        background_tasks.add_task(service.process_recording, recording_id, force=force)
    return RecordingReadyResponse(status="accepted", recording_id=recording_id, job_status=job["status"])


@router.post("/sweep-stale", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_webhook_token)])
async def sweep_stale_transcription_jobs() -> dict[str, int]:
    service = TranscriptionService()
    count = await service.sweep_stale_processing_jobs()
    await asyncio.sleep(0)
    return {"recovered": count}
