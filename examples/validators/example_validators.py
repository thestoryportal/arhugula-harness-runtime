"""Example validators for docs/authoring.md. Copy one and change it.

A validator is a class the runtime builds as `cls(**params)` from the binding's `params`
and calls after its step: `await validator.validate(step, step_result, step_context=...)`.
It returns a `ValidatorResult`: PASS lets the workflow go on, PERMANENT_FAIL stops it, and
ESCALATE asks a person at an approval gate.
"""

from __future__ import annotations

import json
from typing import Any

from harness_cp.validator_framework_types import (
    HITLEscalationBrief,
    ValidatorFailClass,
    ValidatorOutcome,
    ValidatorResult,
)


def reply_text(step_result: Any) -> str:
    """The model's reply as text, for both reply shapes the providers return."""
    if isinstance(step_result, dict):
        message = step_result.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        content = step_result.get("content")
        if isinstance(content, list):
            return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return json.dumps(step_result, default=str)


class MaxCharsValidator:
    """PASS when the reply has at most `max_chars` characters; otherwise PERMANENT_FAIL."""

    def __init__(self, *, max_chars: int) -> None:
        self.max_chars = int(max_chars)

    async def validate(self, step: Any, step_result: Any, *, step_context: Any) -> ValidatorResult:
        if len(reply_text(step_result).strip()) <= self.max_chars:
            return ValidatorResult(outcome=ValidatorOutcome.PASS)
        return ValidatorResult(
            outcome=ValidatorOutcome.PERMANENT_FAIL, fail_class=ValidatorFailClass.SCHEMA_VIOLATION
        )


class AskAPersonValidator:
    """Always ESCALATE: the workflow stops at an approval gate and a person decides."""

    def __init__(self) -> None: ...

    async def validate(self, step: Any, step_result: Any, *, step_context: Any) -> ValidatorResult:
        brief = HITLEscalationBrief(
            parent_step_id=str(step.step_id),
            parent_action_id=f"workflow:{step_context.workflow_id}:step:{step_context.step_index}",
            fail_class=ValidatorFailClass.SEMANTIC_INCONSISTENCY,
            escalation_reason="example validator: please confirm this output",
        )
        return ValidatorResult(
            outcome=ValidatorOutcome.ESCALATE,
            fail_class=ValidatorFailClass.SEMANTIC_INCONSISTENCY,
            escalation_brief=brief,
        )
