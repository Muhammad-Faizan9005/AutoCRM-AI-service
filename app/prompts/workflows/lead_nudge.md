# Workflow: Lead Follow-Up Nudge

Create a useful follow-up task description for a sales rep when a lead needs attention.

## Use This Context
- Lead snapshot: name, company, status, score, source, owner, recent updates.
- RAG docs: notes, calls, tasks, customer requirements, objections, timeline, decision-maker details.
- Entity memory: previous AI tasks or notes so you do not repeat the same vague instruction.
- Event metadata: why this lead was flagged.

## Output Requirements
- Return plain text only.
- Write 1 to 2 concise sentences.
- Include the specific reason for follow-up when available.
- Include the next information to capture: timeline, decision maker, need, budget, blocker, or preferred channel.
- Do not write a greeting or email body.
- Do not mention implementation details.

## Good Output Shape
`Follow up with the lead about [specific context]. Confirm [missing decision/timeline/blocker] and record the next step.`

## Fallback
If context is too thin, return:
`Follow up with the lead and capture the next step, timeline, decision maker, and current blocker.`
