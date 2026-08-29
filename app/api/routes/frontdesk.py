from uuid import UUID
import asyncio
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.api.dependencies import require_webhook_token
from app.workflows.frontdesk import FrontDeskWorkflow
from app.schemas.events import AgentEventIn

router = APIRouter(dependencies=[Depends(require_webhook_token)])

class FrontDeskChatIn(BaseModel):
    session_id: UUID
    message: str = Field(..., min_length=1, max_length=10000)
    history: list[dict[str, object]] = Field(default_factory=list)

@router.post("/chat")
async def chat(payload: FrontDeskChatIn):
    event = AgentEventIn(event_type="frontdesk_message", entity_id=payload.session_id, entity_type="frontdesk", metadata={"message": payload.message, "history": payload.history})
    return await FrontDeskWorkflow().run(event, None)


@router.post("/chat/stream")
async def chat_stream(payload: FrontDeskChatIn):
    """Stream only visitor-visible assistant text; internal actions stay in the final record."""
    event = AgentEventIn(event_type="frontdesk_message", entity_id=payload.session_id, entity_type="frontdesk", metadata={"message": payload.message, "history": payload.history})
    result = await FrontDeskWorkflow().run(event, None)

    async def events():
        text = str(result.get("reply") or "")
        # Chunk on words to provide immediate progressive rendering without exposing retrieval/tool events.
        words = text.split(" ")
        for index, word in enumerate(words):
            token = word if index == 0 else " " + word
            yield f"event: token\ndata: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        done = {"workflow": result.get("workflow", "frontdesk"), "sources": result.get("sources", []), "handoff": bool(result.get("handoff")), "actions": result.get("actions", []), "state": result.get("state", {})}
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
