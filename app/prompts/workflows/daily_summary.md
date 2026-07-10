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

## Fallback Check
Check owned_leads, owned_deals, rag_docs, and entity_memory before writing.
If ALL of the following are true:
- owned_leads is empty
- owned_deals is empty
- rag_docs is empty
- entity_memory has no outstanding actions

Then return exactly this line and nothing else:
`No meaningful CRM activity was available for today. Review open leads, pending tasks, and active deals for updates.`

Do not add extra bullets, questions, hypotheses, or suggested investigations alongside this line. If the fallback fires, stop here.

## Anti-Speculation Rules
- Never phrase a bullet as a question.
- Do not say "investigate", "check", "verify", or "review" unless the specific item is explicitly named in context.
- Do not generate hypotheses about causes such as assignment rules, import failure, or sync issues unless present in the data.
- Do not recommend actions outside CRM data hygiene, such as scheduling 1:1s or territory planning.
- Do not write customer-facing copy or promises. This summary is internal.

## Output Requirements
- Return plain text only.
- Use 3 to 6 bullets, or 1 bullet only if fallback fires.
- Start every bullet with "- ".
- Every bullet must start with one of these exact prefixes: "Follow up:", "Deal risk:", "Task due:", "Meeting note:", "Data gap:".
- Each bullet must be actionable and grounded only in owned_leads, owned_deals, rag_docs, or entity_memory.
- Mention concrete entities when known: lead, company, deal, stage, blocker, or task name.
- If overdue task context is present, use the "Task due:" prefix and mention the task name when known.
- Do not include empty sections.
- Do not invent metrics or counts.
- Do not include implementation details.
- Do not include a title, date header, role/status header, "Pipeline Overview", "Key Observations", "Next Steps", or "Note" section.
- Do not use emojis, icons, decorative symbols, markdown headings, bold markers, italic markers, tables, or horizontal rules.
- Do not use numbered lists; use simple bullets only.
- Keep each bullet under 180 characters.

## Formatting Checks
- Before returning, check whether the response is already separated into bullets.
- If useful bullet points are already present, keep those ideas but normalize each bullet to start with "- ".
- If bullet points are not present, split each distinct CRM observation or recommendation into its own "- " bullet.
- Never return a paragraph blob.
- Never combine multiple recommendations into one bullet using dash separators.
- Remove formatting labels such as "Pipeline Overview", "Key Observations", "Recommended Actions", "Next Steps", and "Note".

## Bullet Style Examples
1. `Follow up: Lead "Acme Corp" has had no contact in 9 days; last touch was a demo call.`
2. `Deal risk: "Northwind Renewal" is stuck in Negotiation for 14 days with no next step logged.`
3. `Task due: "Send proposal to Beta Inc" was due yesterday and is still open.`
4. `Meeting note: Call with "Delta LLC" logged a next step to send pricing; task is not completed.`
5. `Data gap: No leads or deals are currently assigned to this rep in the system.`

## Fallback
If the Fallback Check above triggers, return only:
`No meaningful CRM activity was available for today. Review open leads, pending tasks, and active deals for updates.`
