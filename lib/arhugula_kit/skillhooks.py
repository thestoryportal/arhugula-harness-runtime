"""Skill-activation hooks the kit ships (*kit extension*).

The runtime activates a skill only when a hook selects it, and a hook is a Python object
that a TOML file cannot carry. `arhugula skill hook set` names one, and `arhugula run`
passes it to the runtime (see `hookrun.py`). Write your own in a project's `skills/`
directory with the same two methods.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class EverySkill:
    """Activate every loaded skill before each model call, and none at workflow start."""

    def select_for_workflow_init(self, loaded_skills: Iterable[Any], workflow_id: str) -> list[Any]:
        return []

    def select_for_llm_dispatch(
        self, loaded_skills: Iterable[Any], workflow_id: str, step_index: int
    ) -> list[Any]:
        return list(loaded_skills)
