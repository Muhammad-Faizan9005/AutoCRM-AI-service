"""Front desk agent workflow.

Owns conversation intelligence: persona, discovery state, fact extraction,
identity decisions, tool selection, and visitor response generation. Every CRM
side effect is executed through the backend's validated internal contracts —
this service never writes to the database directly.

Turn pipeline:
  load state -> retrieve knowledge -> decide (facts + stage + tool) ->
  merge facts -> resolve identity when possible -> execute tool via backend ->
  persist state -> compose reply from the confirmed outcome -> stream.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import settings
from app.schemas.frontdesk import (
    ALLOWED_TOOLS,
    FrontDeskDecision,
    FrontDeskState,
    IdentityState,
    TOOL_ARGUMENT_MODELS,
    tool_contracts,
)
from app.services.frontdesk_backend import FrontDeskBackendClient
from app.services.llm_service import LLMService
from app.services.rag_service import RagService
from app.workflows.base import BaseWorkflow

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "frontdesk"
_PROMPT_CACHE: dict[str, str] | None = None
_RAG_SERVICE: RagService | None = None
_MOCK_CACHE: tuple[float, list[dict[str, object]]] | None = None
_KNOWLEDGE_REFRESH_SECONDS = 12 * 60 * 60
_LLM = LLMService()
_BACKEND = FrontDeskBackendClient()

# Facts the runtime treats as identity-critical for lead creation.
IDENTITY_FACTS = ("name", "email")

STAGE_ORDER = [
    "greeting", "identity", "business_context", "problem",
    "qualification", "meeting_offer", "handoff", "completed",
]


def _load_prompts() -> dict[str, str]:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        parts = {}
        for name in ("persona", "guardrails", "system", "discovery", "tools"):
            parts[name] = (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
        parts["tools"] = parts["tools"].replace(
            "{{TOOL_SCHEMAS}}",
            json.dumps(tool_contracts(), ensure_ascii=False, indent=2),
        )
        _PROMPT_CACHE = parts
    return _PROMPT_CACHE

def _business_zone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.cal_timezone or "UTC")
    except Exception:
        logger.warning("frontdesk_bad_cal_timezone: %s", settings.cal_timezone)
        return ZoneInfo("UTC")

def _human_slots(slots: list[str]) -> str:
    """ISO slot strings as business-local clock times a visitor can read."""
    zone, out = _business_zone(), []
    for raw in slots:
        try:
            out.append(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(zone).strftime("%a %d %b %I:%M %p").replace(" 0", " "))
        except Exception:
            continue
    return ", ".join(out)

def _now_line() -> str:
    """Both clocks, business time first, so 'meeting times' are unambiguous."""
    now = datetime.now(timezone.utc)
    local = now.astimezone(_business_zone())
    return (f"{local.strftime('%Y-%m-%d %H:%M')} {settings.cal_timezone} ({local.strftime('%A')})"
            f" - business time, use this for meeting times\n{now.strftime('%Y-%m-%d %H:%M')} UTC")


def _stage_rank(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return 0


async def warm_frontdesk_runtime() -> None:
    global _RAG_SERVICE
    if _RAG_SERVICE is None:
        _RAG_SERVICE = RagService()
    await _RAG_SERVICE.embeddings.embed("front desk startup warmup")


class FrontDeskWorkflow(BaseWorkflow):
    name = "frontdesk"

    async def run(self, payload, run_context):
        metadata = payload.metadata or {}
        session_id = str(payload.entity_id)
        message = str(metadata.get("message") or "").strip()
        history = metadata.get("history") if isinstance(metadata.get("history"), list) else []

        state = await self._load_state(session_id, history)
        contexts = await self._retrieve(message, session_id)

        decision = await self._decide(state, message, history, contexts)
        state.known_facts = self._merge_facts(state.known_facts, decision.extracted_facts)
        state.stage = self._advance_stage(state.stage, decision.stage)

        executed: dict[str, Any] | None = None
        if decision.tool != "answer":
            executed = await self._execute_tool(session_id, state, decision)

        await self._persist_state(session_id, state)

        reply = await self._compose_reply(state, message, contexts, decision, executed)
        state.last_questions = [*state.last_questions, reply.strip()][-5:]
        state.last_action = self._action_record(decision, executed)
        await self._persist_state(session_id, state)

        return {
            "workflow": self.name,
            "reply": reply,
            "sources": [item.get("source_id") for item in contexts if item.get("source_id")],
            "handoff": decision.tool == "request_handoff" and bool(executed and executed.get("ok")),
            "actions": [{"tool": decision.tool, "arguments": decision.arguments, "result": executed}] if decision.tool != "answer" else [],
            "state": {"stage": state.stage, "identity": state.identity.model_dump(), "known_facts": state.known_facts},
        }

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def _load_state(self, session_id: str, history: list) -> FrontDeskState:
        try:
            session = await _BACKEND.get_session(session_id)
            raw = session.get("ai_state") or {}
            state = FrontDeskState(**{**raw, "session_id": session_id})
            if session.get("contact_type") == "lead" and session.get("contact_id"):
                state.identity = IdentityState(
                    status="matched",
                    lead_id=str(session["contact_id"]),
                    owner_id=str(session.get("lead_owner_id")) if session.get("lead_owner_id") else None,
                )
            if session.get("contact_name") and not state.known_facts.get("name"):
                state.known_facts.setdefault("name", session["contact_name"])
            if session.get("contact_email") and not state.known_facts.get("email"):
                state.known_facts.setdefault("email", session["contact_email"])
            if session.get("discovery_stage") and _stage_rank(session["discovery_stage"]) >= _stage_rank(state.stage):
                state.stage = session["discovery_stage"]
            if session.get("summary"):
                state.conversation_summary = session["summary"]
        except Exception as exc:
            logger.warning("frontdesk_state_load_failed: %s", exc)
            state = FrontDeskState(session_id=session_id)
        # Safety net: seed facts from the transcript when state was lost so the
        # agent never re-asks what the visitor already typed.
        state.known_facts = self._merge_facts(state.known_facts, self._regex_facts(history))
        return state

    async def _persist_state(self, session_id: str, state: FrontDeskState) -> None:
        try:
            await _BACKEND.save_state(
                session_id,
                state=state.model_dump(mode="json"),
                stage=state.stage,
                summary=state.conversation_summary or None,
                facts=state.known_facts,
            )
        except Exception as exc:
            logger.warning("frontdesk_state_persist_failed: %s", exc)

    @staticmethod
    def _merge_facts(current: dict, incoming: dict) -> dict:
        merged = dict(current)
        for key, value in (incoming or {}).items():
            if value is None:
                continue
            text = str(value).strip()
            if not text or text.lower() in {"none", "null", "n/a", "unknown"}:
                continue
            if key == "email":
                text = text.lower()
            if not merged.get(key):
                merged[key] = text
        return merged

    @staticmethod
    def _advance_stage(current: str, proposed: str) -> str:
        # Forward-only: the runtime never lets the model rewind discovery.
        return proposed if _stage_rank(proposed) > _stage_rank(current) else current

    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------

    async def _retrieve(self, message: str, session_id: str) -> list[dict[str, object]]:
        try:
            global _RAG_SERVICE
            if _RAG_SERVICE is None:
                _RAG_SERVICE = RagService()
            return await _RAG_SERVICE.retrieve(
                entity_id=session_id, entity_type="frontdesk", query=message,
                limit=5, source_filter="frontdesk_knowledge", global_search=True, workflow="frontdesk",
            )
        except Exception:
            return self._mock_retrieve(message)

    @staticmethod
    def _regex_facts(history: list) -> dict:
        text = "\n".join(str(x.get("content") or "") for x in history if isinstance(x, dict))
        facts: dict[str, Any] = {}
        email = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        if email:
            facts["email"] = email[-1].lower()
        for pattern, key in [
            (r"my name is ([A-Za-z][A-Za-z .'-]{1,60})", "name"),
            (r"i(?:'m| am) ([A-Z][a-z]+(?: [A-Z][a-z'-]+){0,3})\b", "name"),
            (r"company(?: name)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 .&'-]{2,80})", "company"),
        ]:
            matches = re.findall(pattern, text, re.I)
            if matches:
                facts[key] = matches[-1].strip(" .,")
        if facts.get("name") and len(str(facts["name"]).split()) > 4:
            facts.pop("name")
        return facts

    @staticmethod
    def _mock_retrieve(query):
        global _MOCK_CACHE
        root = Path(__file__).resolve().parents[2] / "dev_knowledge"
        now = time.time()
        if _MOCK_CACHE is None or now - _MOCK_CACHE[0] >= _KNOWLEDGE_REFRESH_SECONDS:
            docs = []
            for path in root.glob("*.md"):
                content = path.read_text(encoding="utf-8")
                docs.append({"path": path.stem, "content": content.split("\n\n", 1)[-1], "terms": set(re.findall(r"[a-z0-9]+", content.lower()))})
            _MOCK_CACHE = (now, docs)
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        matches = [{"content": d["content"], "source_id": d["path"], "score": len(terms & d["terms"]) / max(1, len(terms))} for d in _MOCK_CACHE[1] if terms & d["terms"]]
        return sorted(matches, key=lambda item: float(item["score"]), reverse=True)[:3]

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    async def _decide(self, state: FrontDeskState, message: str, history: list, contexts: list) -> FrontDeskDecision:
        prompts = _load_prompts()
        knowledge = "\n\n".join(str(item.get("content") or "")[:3000] for item in contexts[:5]) or "(No approved knowledge matched.)"
        prompt = f"""{prompts['persona']}

{prompts['guardrails']}

{prompts['system']}

{prompts['discovery']}

{prompts['tools']}

Current date and time:
{_now_line()}
Resolve every relative date ("tomorrow", "next Tuesday", "3pm") against the
business time above. A bare clock time from the visitor means business time,
never UTC. Never emit a starts_at in the past.

Runtime state (authoritative memory; never ask for any fact already in known_facts):
{json.dumps(state.model_dump(mode='json'), ensure_ascii=False, default=str)}

Recent questions you already asked (never repeat them):
{json.dumps(state.last_questions, ensure_ascii=False)}

Conversation history (oldest first):
{json.dumps(history[-40:], ensure_ascii=False, default=str)}

Approved knowledge:
{knowledge}

Latest visitor message:
{message}

Return the JSON decision now."""
        try:
            raw = await _LLM.generate(prompt=prompt, model_tier="small", json_mode=True)
            parsed = self._parse_json(raw or "")
            if parsed is not None:
                if not isinstance(parsed.get("extracted_facts"), dict):
                    parsed["extracted_facts"] = {}
                if not isinstance(parsed.get("arguments"), dict):
                    parsed["arguments"] = {}
                if parsed.get("stage") not in STAGE_ORDER:
                    parsed["stage"] = "greeting"  # forward-only merge keeps the real stage
                if not isinstance(parsed.get("reply"), str):
                    parsed["reply"] = str(parsed.get("reply") or "")
                if parsed.get("tool") not in ALLOWED_TOOLS:
                    parsed["tool"] = "answer"
                return FrontDeskDecision(**{k: v for k, v in parsed.items() if k in FrontDeskDecision.model_fields})
        except Exception as exc:
            logger.warning("frontdesk_decision_failed: %s", exc)
        return FrontDeskDecision(tool="answer", reply=self._state_aware_fallback(state), reason="decision_provider_failure")

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        text = text.strip()
        try:
            result = json.loads(text)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                result = json.loads(text[start:end + 1])
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _state_aware_fallback(state: FrontDeskState) -> str:
        # Provider outage: continue from real state instead of restarting discovery.
        facts = state.known_facts
        if not facts.get("name") or not facts.get("email"):
            return "Thanks for reaching out to AutoCRM. So I can set this up properly, could you share your name and work email?"
        if not facts.get("problem"):
            return "Thanks for the details. In one or two sentences, what would you most like to improve?"
        return "Understood — I've noted that. Would you like me to arrange a quick call with the team, or is there anything else I can help with right now?"

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, session_id: str, state: FrontDeskState, decision: FrontDeskDecision) -> dict:
        tool = decision.tool
        args_model = TOOL_ARGUMENT_MODELS.get(tool)
        try:
            model = args_model(**decision.arguments) if args_model else None
        except Exception as exc:
            logger.warning("frontdesk_tool_args_invalid tool=%s: %s", tool, exc)
            return {"ok": False, "tool": tool, "error": f"invalid_arguments: {exc}"}

        # Resolve identity as soon as enough information exists, before any
        # lead-bound operation.
        if tool in {"save_note", "create_task", "book_meeting"} and not state.identity.lead_id:
            ensured = await self._ensure_lead(session_id, state)
            if not ensured.get("ok"):
                return {"ok": False, "tool": tool, "error": "identity_required", "detail": ensured.get("error")}

        payload = model.model_dump(mode="json") if model else {}
        payload.pop("suggested_assignee_id", None)
        try:
            if tool == "upsert_lead":
                result = await _BACKEND.upsert_lead({"session_id": session_id, **payload, "source": "frontdesk_chat"})
                state.identity = IdentityState(
                    status=result.get("identity_status", "unknown"),
                    lead_id=result.get("lead_id"),
                    owner_id=result.get("owner_id"),
                    matched_by=result.get("matched_by"),
                )
                for fact_key, result_key in (("name", "name"), ("email", "email")):
                    if payload.get(fact_key):
                        state.known_facts.setdefault(fact_key, payload[fact_key])
                if result.get("matched_by"):
                    state.completed_stages = sorted(set(state.completed_stages) | {"identity"})
                return {"ok": True, "tool": tool, "result": result}
            if tool == "save_note":
                result = await _BACKEND.create_note({"session_id": session_id, **payload})
                return {"ok": True, "tool": tool, "result": result}
            if tool == "create_task":
                if decision.arguments.get("suggested_assignee_id"):
                    payload["suggested_assignee_id"] = decision.arguments["suggested_assignee_id"]
                result = await _BACKEND.create_task({"session_id": session_id, **payload})
                return {"ok": True, "tool": tool, "result": result}
            if tool == "request_handoff":
                if decision.arguments.get("suggested_assignee_id"):
                    payload["suggested_assignee_id"] = decision.arguments["suggested_assignee_id"]
                result = await _BACKEND.create_handoff({"session_id": session_id, **payload})
                if payload.get("summary"):
                    state.conversation_summary = str(payload["summary"])[:5000]
                state.stage = "handoff"
                return {"ok": True, "tool": tool, "result": result}
            if tool == "list_slots":
                result = await _BACKEND.list_slots(day=payload["day"], time_zone=payload.get("time_zone"))
                # Remember the openings so the next turn books one verbatim
                # instead of re-deriving a timestamp from free text.
                state.known_facts["offered_slots"] = result.get("slots") or []
                return {"ok": bool(result.get("slots")), "tool": tool, "result": result}
            if tool == "book_meeting":
                if decision.arguments.get("suggested_assignee_id"):
                    payload["suggested_assignee_id"] = decision.arguments["suggested_assignee_id"]
                meeting = {key: payload.pop(key) for key in ("provider", "uid", "starts_at", "ends_at", "meeting_url", "title", "time_zone") if key in payload}
                result = await _BACKEND.create_appointment({"session_id": session_id, "meeting": meeting, "summary": payload.get("summary"), "requested_task": payload.get("requested_task")})
                # A 200 with an unsynced calendar is NOT a booking: the slot was
                # refused. Reporting ok here is what let the agent claim a
                # meeting that did not exist.
                booked = bool(result.get("calendar_synced"))
                if not booked:
                    state.known_facts["offered_slots"] = result.get("alternative_slots") or []
                    return {"ok": False, "tool": tool, "error": "calendar_rejected",
                            "detail": result.get("calendar_error"), "result": result}
                state.stage = "completed"
                return {"ok": True, "tool": tool, "result": result}
        except Exception as exc:
            logger.warning("frontdesk_tool_failed tool=%s: %s", tool, exc)
            return {"ok": False, "tool": tool, "error": "backend_rejected", "detail": str(exc)[:400]}
        return {"ok": False, "tool": tool, "error": "unknown_tool"}

    async def _ensure_lead(self, session_id: str, state: FrontDeskState) -> dict:
        facts = state.known_facts
        if not facts.get("name") or not facts.get("email"):
            return {"ok": False, "error": "missing_name_or_email"}
        result = await self._execute_tool(
            session_id, state, FrontDeskDecision(
                tool="upsert_lead",
                arguments={"name": facts["name"], "email": facts.get("email"), "phone": facts.get("phone"), "company": facts.get("company")},
            ),
        )
        return result

    @staticmethod
    def _action_record(decision: FrontDeskDecision, executed: dict | None) -> dict | None:
        if decision.tool == "answer" and not executed:
            return None
        record = {"tool": decision.tool, "at": datetime.now(timezone.utc).isoformat()}
        if executed:
            record["ok"] = bool(executed.get("ok"))
            if not executed.get("ok"):
                record["error"] = executed.get("error")
        return record

    # ------------------------------------------------------------------
    # Response composition
    # ------------------------------------------------------------------

    async def _compose_reply(self, state: FrontDeskState, message: str, contexts: list, decision: FrontDeskDecision, executed: dict | None) -> str:
        draft = str(decision.reply or "").strip()
        if decision.tool == "answer" or executed is None:
            return draft or self._state_aware_fallback(state)
        prompts = _load_prompts()
        knowledge = "\n\n".join(str(item.get("content") or "")[:1500] for item in contexts[:3])
        prompt = f"""{prompts['persona']}

{prompts['guardrails']}

The backend has just processed the action you selected. Write the final visitor-facing reply.

Runtime state:
{json.dumps(state.model_dump(mode='json'), ensure_ascii=False, default=str)}

Selected tool: {decision.tool}
Backend result (authoritative): {json.dumps(executed, ensure_ascii=False, default=str)}

Approved knowledge:
{knowledge or "(none)"}

Latest visitor message:
{message}

Requirements:
- If the backend result is ok, confirm the real outcome to the visitor in natural language (booking time, handoff, saved details) without exposing IDs, owners, routing, or internals.
- If the result failed, be honest: say it could not be completed right now and that a team member will follow up. Never pretend it succeeded.
- Never say a meeting is booked or confirmed unless the result contains `calendar_synced: true`. A 200 response with `calendar_synced: false` means the calendar REFUSED the slot: say that time is not available.
- If the result contains `slots` or `alternative_slots`, offer those times to the visitor (business-local wording, no offsets or ISO strings) and ask which one works.
- Times you state must be in {settings.cal_timezone}; convert from the result's timestamps, never restate a UTC hour as if it were local.
- 1-3 sentences, warm and concise. No new discovery question unless the failure means a required detail is missing.
Reply text only, no JSON."""
        try:
            raw = await _LLM.generate(prompt=prompt, model_tier="small")
            text = (raw or "").strip()
            if text:
                return text
        except Exception as exc:
            logger.warning("frontdesk_compose_failed: %s", exc)
        return self._template_reply(decision.tool, executed) or draft or self._state_aware_fallback(state)

    @staticmethod
    def _template_reply(tool: str, executed: dict) -> str:
        ok = bool(executed.get("ok"))
        result = executed.get("result") or {}
        if tool == "upsert_lead":
            return "Thank you — I've saved your details so the team knows who you are." if ok else "I couldn't save your details just now, but a team member will follow up with you."
        if tool == "request_handoff":
            if not ok:
                return "I couldn't complete the handoff just now. A team member will still follow up with you — I'm flagging this conversation for them."
            # Inside the grace period a rep may still join and answer live, so
            # promising an email here would pre-empt them.
            minutes = result.get("wait_minutes")
            return (f"I've asked a team member to join us — they should be with you within {minutes} minutes."
                    if minutes else "I've asked an AutoCRM team member to reach out to you shortly.")
        if tool == "list_slots":
            slots = _human_slots((result.get("slots") or [])[:6])
            if slots:
                return f"Here's what's open: {slots}. Which time suits you?"
            return "I don't see any openings that day. Would another day work for you?"
        if tool == "book_meeting":
            # `ok` already means the calendar accepted the slot.
            if ok:
                appointment = result.get("appointment") or {}
                when = _human_slots([str(appointment.get("starts_at"))]) if appointment.get("starts_at") else ""
                return f"You're booked{' for ' + when if when else ''}. A calendar invitation with the details will follow."
            slots = _human_slots((result.get("alternative_slots") or [])[:6])
            if slots:
                return f"That time isn't open on our calendar. These are free that day: {slots}. Which works for you?"
            return "I couldn't confirm that time on our calendar. A team member will follow up to arrange the meeting with you."
        if tool == "create_task":
            return "Noted — I've set a follow-up on this for the team." if ok else "I couldn't set that follow-up just now, but I've noted it in our conversation."
        if tool == "save_note":
            return "Noted — I've summarized that for the team." if ok else "I couldn't save that note just now, but it stays in our conversation for the team."
        return ""
