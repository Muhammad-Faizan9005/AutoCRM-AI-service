# Workflow: Deal Risk Alert

Write a manager-facing risk alert for a deal that may need intervention.

## Look For
- Stalled stage, overdue close date, low probability, missing next task, no recent notes/calls.
- Objections, legal/procurement/security blockers, budget concern, decision-maker uncertainty.
- Negative signals from related lead, customer, organization, notes, calls, and prior AI actions.

## Output Requirements
- Return plain text only.
- Write 1 to 2 concise sentences.
- State the risk signal and the recommended review action.
- If the owner or next step is known, mention it.
- Avoid certainty unless the context supports it.
- Do not blame a rep or customer.

## Good Output Shape
`Deal risk: [specific signal]. Ask the owner to review [blocker/next step] and update the close plan.`

## Fallback
If context is thin, return:
`Deal appears at risk. Review stage progress, recent activity, owner follow-up, and next steps.`
