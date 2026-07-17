"""Action policy enforcement for LLM-planned actions.

Validates and normalises ``PlannedAction`` objects to ensure the model
output conforms to the allowed action types and approval rules, even
when the LLM is fed adversarial / injected content.
"""

from __future__ import annotations

import logging

from app.schemas.events import AgentEventIn
from app.schemas.planner import PlannedAction

logger = logging.getLogger(__name__)

# Allowed action types — anything outside this set is rejected / normalised.
_ALLOWED_ACTION_TYPES = frozenset({"create_task", "create_note", "create_alert"})

# Action types that must always require human approval, regardless of what
# the model decides.  Matches the rules already stated in the planner prompt.
_HIGH_RISK_ACTION_TYPES = frozenset({"create_task"})


def validate_planned_action(
    plan: PlannedAction,
    payload: AgentEventIn,
) -> PlannedAction:
    """Enforce action policy on a planned action.

    1. ``action_type`` / ``selected_tool`` must be in the allowed set.
    2. ``requires_approval`` is forced ``True`` for high-risk action types.
    3. ``recipient_id`` is restricted to the actor or empty.
    """
    # --- 1. action_type allowlist ---
    if plan.action_type not in _ALLOWED_ACTION_TYPES:
        logger.warning(
            "action_policy_rejected action_type=%s → defaulting to create_task",
            plan.action_type,
        )
        plan.action_type = "create_task"

    if plan.selected_tool is not None and plan.selected_tool not in _ALLOWED_ACTION_TYPES:
        logger.warning(
            "action_policy_rejected selected_tool=%s → defaulting to action_type",
            plan.selected_tool,
        )
        plan.selected_tool = plan.action_type

    # --- 2. requires_approval enforcement ---
    if plan.action_type in _HIGH_RISK_ACTION_TYPES:
        if plan.requires_approval is not True:
            logger.info(
                "action_policy_forced_approval action_type=%s",
                plan.action_type,
            )
            plan.requires_approval = True

    # For alerts: default to not requiring approval (informational).
    if plan.action_type == "create_alert" and plan.requires_approval is None:
        plan.requires_approval = False

    # For notes: default to not requiring approval.
    if plan.action_type == "create_note" and plan.requires_approval is None:
        plan.requires_approval = False

    # --- 3. recipient_id sanitisation ---
    # Only allow recipient_id to be the actor or empty — never an arbitrary
    # user the model decided to target.
    actor_id = payload.actor_id or ""
    if plan.recipient_id and plan.recipient_id != actor_id:
        logger.warning(
            "action_policy_sanitised_recipient original=%s actor=%s",
            plan.recipient_id,
            actor_id,
        )
        plan.recipient_id = actor_id

    return plan
