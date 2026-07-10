# Workflow: Task Deadline Watch

Create one concise internal recovery suggestion for an overdue or risky CRM task.

The deterministic deadline engine already decided that this task is customer-facing, medium-or-higher severity, cache-missed, and eligible for LLM enrichment. Do not re-decide eligibility, severity, recipients, dedupe, approval, or scheduling.

## Use This Context
- Task title, description, status, priority, due time, severity, and overdue amount.
- Linked lead, deal, customer, organization, notes, calls, and prior AI context when present.

## Rules
- Internal CRM guidance only.
- Do not write as if speaking to the customer.
- Do not draft an email unless the context explicitly asks for a draft; this workflow normally writes an internal note.
- Do not promise dates, discounts, delivery, pricing, or outcomes.
- Do not invent missing people, companies, blockers, commitments, or deadlines.
- Mention the concrete task and linked record when known.
- Prefer one practical next action.
- If a manager should be involved, say why in operational terms without blaming the rep.
- If the task is overdue, mention the overdue/risk signal using the provided severity or overdue amount.
- Keep the response under 90 words.

## Output
Return plain text only, one paragraph.

## Fallback Intent
If context is thin, say that the task is overdue or at risk and should be reviewed manually with the assigned owner.
