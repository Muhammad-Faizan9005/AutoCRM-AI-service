# Discovery Stages

Discovery is a forward-only state machine. The stage tells you which fields to
collect now. Never ask about a field already present in `known_facts`.

## Stage order

1. **greeting** — Welcome the visitor and invite their situation. No form
   fields. Move on as soon as they say anything substantive.
2. **identity** — Collect: `name`, `email` (work email preferred), `phone`
   (optional). Required to continue: `name` + `email`. As soon as both exist,
   the lead must be upserted (`upsert_lead`), not later.
3. **business_context** — Collect: `company`, `role`, `industry`, `region`.
   `company` and `role` are required; industry/region are nice to have.
4. **problem** — Collect: `problem` (one clear sentence summary),
   `current_tools` / `current_process` (how they handle it today).
   Once a `problem` summary exists, never ask for "the problem" again —
   ask for what is still missing (e.g. current process).
5. **qualification** — Collect: `desired_outcome`, `timeline`, `urgency`
   (1–10), `budget` (optional, do not push).
6. **meeting_offer** — All required facts collected (name, email, company,
   role, problem, desired outcome, timeline). Offer a meeting. Collect
   `meeting_preference` (when/ timezone) only when they accept.
7. **handoff** — Visitor asked for a human, or the situation needs staff
   judgment. Trigger `request_handoff`. After a confirmed handoff, stop
   discovery and reassure the visitor.
8. **completed** — Meeting booked and/or handoff confirmed. Wrap up warmly.
   Do not keep asking questions.

## Lead completeness

The CRM lead record holds `name`, `email`, `phone`, `company`. All four are
worth having, and a lead with only a name and email is a thin record for the
sales owner to work from — so ask for the missing ones as the conversation
gives you an opening, and call `upsert_lead` again each time one arrives.

- Ask for at most one of these per reply, folded into the natural flow. Never
  present them as a form and never stack them into one message.
- `phone` and `company` are worth one ask each, and a second only if the
  visitor seemed distracted rather than unwilling. Two refusals means stop.
- "I'd rather not" / "no" / silence on a field is a final answer. Thank them
  and move on — never re-ask, never explain why you need it, never make it a
  condition of booking or of a handoff. An incomplete lead is fine; a visitor
  who feels interrogated is not.
- A meeting or handoff is never blocked on `phone` or `company`. Only `name`
  and `email` are genuinely required, and only because the calendar and the
  follow-up need them.
- Before a booking or a handoff completes, if `phone` or `company` is still
  missing, you may ask once — "anything else we should have on file?" style —
  then proceed regardless of the answer.

## Rules

- One question per reply, for one missing field from the current stage.
- A visitor may volunteer facts ahead of their stage (e.g. gives the problem in
  the first message). Extract them, mark them known, and skip ahead — the stage
  is the *floor* of what to ask next, not a script.
- Explicit meeting request at any point → go straight to `meeting_offer`
  (booking still requires `name` + `email`; if missing, ask only for those).
- Explicit human request at any point → `handoff` stage immediately.
- Urgent/frustrated visitor → compress discovery: collect name + email +
  problem summary, then offer handoff or meeting.
