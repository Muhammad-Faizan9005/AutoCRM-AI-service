# Workflow: Daily CRM Summary

Create a concise daily CRM summary for one user or manager.

## Use This Context
- `owned_leads`: current leads owned by the user.
- `owned_deals`: current deals owned by the user.
- `rag_docs`: recent or relevant notes, calls, tasks, leads, deals, organizations, customers.
- `entity_memory`: prior AI activity and outstanding AI-created actions.

## Prioritize
1. Overdue or urgent tasks.
2. Stale leads that need follow-up.
3. At-risk deals or blocked deals.
4. Meetings/calls with clear next steps.
5. High-value or high-score opportunities.
6. Missing CRM data that should be captured.

## Output Requirements
- Return plain text only.
- Use 3 to 6 bullets.
- Each bullet should be actionable and specific.
- Mention concrete entities when known: lead/company/deal/stage/blocker.
- Do not include empty sections.
- Do not invent metrics or counts.
- Do not include implementation details.

## Bullet Style
- `Follow up: ...`
- `Deal risk: ...`
- `Task due: ...`
- `Meeting note: ...`
- `Data gap: ...`

## Fallback
If the context has no useful CRM activity, return:
`- No meaningful CRM activity was available for today. Review open leads, pending tasks, and active deals for updates.`
