# Workflow: Meeting Intelligence

Extract one concrete CRM follow-up task from a meeting transcript.

## Create A Task Only When The Transcript Contains
- A clear customer request.
- A promised follow-up.
- A deadline, meeting, demo, quote, contract, proposal, invoice, or document to send.
- A requirement, blocker, quantity, product interest, or next decision step that needs owner action.

## Do Not Create A Task From
- Greetings, introductions, mic checks, repeated words, or small talk.
- Vague interest without a next step.
- Internal speculation not supported by the transcript.
- Already-completed actions.
- Generic "follow up" when the transcript has no concrete reason.

## Required Output
If no concrete action exists, return exactly:
NO_ACTION_ITEMS

If an action exists, return valid JSON only. Do not include Markdown, commentary, or code fences.

Use exactly these keys:
{
  "title": "short imperative task title, max 10 words",
  "task_description": "one concise sentence, max 25 words",
  "due_at": null,
  "priority": "low | medium | high",
  "note_content": "supporting customer details, transcript context, products, quantities, blockers, and longer notes"
}

## Due Date Rules
- Use `due_at` only when the transcript clearly states a date or time.
- Use ISO 8601 format.
- For relative/local meeting times, use timezone `+05:00`.
- If no deadline is clear, use `null`.

## Priority Rules
- `high`: deadline, escalation, customer blocker, commercial commitment, or urgent follow-up.
- `medium`: normal next step, proposal, demo, quote, meeting, or requested information.
- `low`: minor admin follow-up with no deadline.

## Content Rules
- Do not invent due dates, products, quantities, or customer commitments.
- Keep `task_description` short enough for a task card.
- Put verbose details in `note_content`, not `task_description`.
