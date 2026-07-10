# Workflow: Task Automation

Draft a short CRM task description for an automatically generated next step.

## Use This Context
- Entity snapshot for the related lead/deal/customer/task.
- RAG docs containing notes, calls, existing tasks, organization/customer context, and prior outcomes.
- Event metadata describing why the task is being created.

## Output Requirements
- Return plain text only.
- Write 1 concise sentence, max 180 characters when possible.
- Make the task executable by a sales rep.
- Include the reason or evidence when available.
- Do not duplicate an existing open task if context shows one already exists.
- Do not create outbound-message wording; describe the task only.
- Do not set or imply a due date unless the provided context contains one.
- Do not assign blame or say the customer was neglected; describe the operational next step.

## Good Output Shape
`Complete [specific next step] for [lead/deal/customer] and update CRM with [missing detail].`

## Fallback
If context is thin, return:
`Complete the next step for this record and update CRM with outcome, timeline, and owner.`
