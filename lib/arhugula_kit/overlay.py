"""Edit the stored overlay: the settings verbs add on top of the init answers.

The overlay is a plain nested mapping in the shape of the runtime's TOML. These helpers
return a changed copy; `deploy.apply` then has the runtime accept the result or nothing
changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from arhugula_kit.spec import Spec

__all__ = ["dropped", "get", "scoped", "set_value", "with_value", "without"]

Path = tuple[str, ...]


def get(tree: Mapping[str, Any], path: Path, default: Any = None) -> Any:
    here: Any = tree
    for key in path:
        if not isinstance(here, Mapping) or key not in here:
            return default
        here = here[key]
    return here


def with_value(tree: Mapping[str, Any], path: Path, value: Any) -> dict[str, Any]:
    """A copy of `tree` with `value` at `path`, creating the mappings on the way."""
    head, rest = path[0], path[1:]
    child = tree.get(head, {})
    return {
        **tree,
        head: value if not rest else with_value(child if isinstance(child, Mapping) else {}, rest, value),
    }


def without(tree: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """A copy of `tree` with `path` removed, and with any mapping that leaves empty removed."""
    head, rest = path[0], path[1:]
    if head not in tree:
        return dict(tree)
    if not rest:
        return {k: v for k, v in tree.items() if k != head}
    child = tree[head]
    if not isinstance(child, Mapping):
        return dict(tree)
    pruned = without(child, rest)
    return {**{k: v for k, v in tree.items() if k != head}, **({head: pruned} if pruned else {})}


def scoped(spec: Spec, project: str) -> Mapping[str, Any]:
    """The overlay for one scope: `""` is every config, a name is that project's config."""
    return spec.project_overlays.get(project, {}) if project else spec.overlay


def _rescoped(spec: Spec, project: str, tree: Mapping[str, Any]) -> Spec:
    if not project:
        return replace(spec, overlay=dict(tree))
    overlays = {**spec.project_overlays, project: dict(tree)}
    return replace(spec, project_overlays={k: v for k, v in overlays.items() if v})


def set_value(spec: Spec, project: str, path: Path, value: Any) -> Spec:
    return _rescoped(spec, project, with_value(scoped(spec, project), path, value))


def dropped(spec: Spec, project: str, path: Path) -> Spec:
    return _rescoped(spec, project, without(scoped(spec, project), path))
