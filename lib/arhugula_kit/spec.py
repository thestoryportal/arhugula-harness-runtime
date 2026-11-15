"""The deployment's answers file: the single source every generated file is rendered from.

`<home>/config/init-answers.json` holds what the operator decided (the init answers, the
attached projects, the enabled features) and the settings later verbs add. It holds nothing
the machine can derive. Verbs change this file and regenerate; they never edit a generated
TOML file directly.

[LAW:parse-dont-validate] `parse` is the one checkpoint. It returns a `Spec` or refuses
with the name of the missing or malformed answer; nothing downstream re-checks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from arhugula_kit import providers
from arhugula_kit.errors import Exit, KitError

__all__ = [
    "MEMORY_MODES",
    "WORKLOADS",
    "Observability",
    "Project",
    "Spec",
    "load",
    "parse",
    "project_name_for",
    "save",
]

FORMAT = 1

WORKLOADS: tuple[str, ...] = (
    "pipeline-automation",
    "software-engineering",
    "research",
    "content-creation",
)

MEMORY_MODES: tuple[str, ...] = ("packet", "packet+tools")

_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


@dataclass(frozen=True)
class Observability:
    """Answer 11: the observability tier and the Lima instance that hosts it."""

    enabled: bool = False
    lima_home: str = ""
    instance: str = ""


@dataclass(frozen=True)
class Project:
    """An attached project repository. Its name is also its tenant id (decision 7)."""

    path: str
    workloads: tuple[str, ...] = WORKLOADS


@dataclass(frozen=True)
class Spec:
    home: str
    providers: tuple[str, ...]
    primary: str
    fallback: str  # "" for none
    ollama_model: str
    ollama_host: str
    workloads: tuple[str, ...]
    features: tuple[str, ...]  # enabled fragment names, in the order they were enabled
    memory_mode: str
    observability: Observability
    isolation_tier3: bool
    forbidden_roots: tuple[str, ...]
    smoke: bool
    models: Mapping[str, str] = field(default_factory=dict)  # provider -> model, when not default
    commands: Mapping[str, str] = field(default_factory=dict)  # CLI provider -> executable path
    python_paths: tuple[str, ...] = ()  # directories added to PYTHONPATH for runs (validators)
    skill_hook: str = ""  # `module:Class` of the skill-activation hook, when one is set
    provider_settings: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # CLI knobs
    projects: Mapping[str, Project] = field(default_factory=dict)
    current_project: str = ""
    overlay: Mapping[str, Any] = field(default_factory=dict)  # merged last into every config
    project_overlays: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def model_of(self, provider: str) -> str:
        if provider == "ollama":
            return self.models.get(provider, self.ollama_model)
        return self.models.get(provider, providers.by_name(provider).default_model)

    def with_feature(self, name: str, enabled: bool) -> Spec:
        kept = tuple(f for f in self.features if f != name)
        return replace(self, features=(*kept, name) if enabled else kept)

    def to_json(self) -> dict[str, Any]:
        return {"format": FORMAT, **asdict(self)}


def project_name_for(path: Path) -> str:
    """A project name from its directory name: lowercase, digits and hyphens."""
    name = re.sub(r"[^a-z0-9]+", "-", path.name.lower()).strip("-")
    return name or "project"


def _refuse(message: str) -> KitError:
    return KitError(Exit.PRECONDITION, f"answers file: {message}")


def _take(raw: Mapping[str, Any], key: str, kind: type | tuple[type, ...]) -> Any:
    if key not in raw:
        raise _refuse(f"answer `{key}` is missing; nothing is defaulted silently")
    if not isinstance(raw[key], kind) or isinstance(raw[key], bool) and kind is not bool:
        raise _refuse(f"answer `{key}` has the wrong type (got {type(raw[key]).__name__})")
    return raw[key]


def _names(raw: Mapping[str, Any], key: str, allowed: tuple[str, ...], what: str) -> tuple[str, ...]:
    values = tuple(_take(raw, key, list))
    for value in values:
        if value not in allowed:
            raise _refuse(f"`{key}` names an unknown {what} {value!r} (known: {', '.join(allowed)})")
    return values


def parse(raw: Mapping[str, Any], *, known_features: tuple[str, ...]) -> Spec:
    """Parse the JSON document into a `Spec`, or refuse naming what is wrong."""
    if raw.get("format") != FORMAT:
        raise _refuse(f"`format` must be {FORMAT} (got {raw.get('format')!r})")
    provider_names = tuple(p.name for p in providers.CATALOGUE)
    selected = _names(raw, "providers", provider_names, "provider")
    if not selected:
        raise _refuse("`providers` selects no provider")
    primary = _take(raw, "primary", str)
    if primary not in selected:
        raise _refuse(f"`primary` {primary!r} is not one of the selected providers")
    fallback = _take(raw, "fallback", str)
    if fallback and (fallback not in selected or fallback == primary):
        raise _refuse(f"`fallback` {fallback!r} must be a selected provider other than the primary")
    memory_mode = _take(raw, "memory_mode", str)
    if memory_mode not in MEMORY_MODES:
        raise _refuse(f"`memory_mode` must be one of {', '.join(MEMORY_MODES)}")
    observability = _take(raw, "observability", dict)
    projects: dict[str, Project] = {}
    for name, entry in dict(raw.get("projects", {})).items():
        if not _NAME.fullmatch(name):
            raise _refuse(f"project name {name!r} must be lowercase letters, digits and hyphens")
        projects[name] = Project(
            path=_take(entry, "path", str),
            workloads=_names(entry, "workloads", WORKLOADS, "workload class"),
        )
    current = str(raw.get("current_project", ""))
    if current and current not in projects:
        raise _refuse(f"`current_project` {current!r} is not an attached project")
    home = _take(raw, "home", str)
    if not Path(home).is_absolute():
        raise _refuse("`home` must be an absolute path")
    return Spec(
        home=home,
        providers=selected,
        primary=primary,
        fallback=fallback,
        ollama_model=_take(raw, "ollama_model", str),
        ollama_host=_take(raw, "ollama_host", str),
        workloads=_names(raw, "workloads", WORKLOADS, "workload class"),
        features=_names(raw, "features", known_features, "feature"),
        memory_mode=memory_mode,
        observability=Observability(
            enabled=_take(observability, "enabled", bool),
            lima_home=str(observability.get("lima_home", "")),
            instance=str(observability.get("instance", "")),
        ),
        isolation_tier3=_take(raw, "isolation_tier3", bool),
        forbidden_roots=tuple(_take(raw, "forbidden_roots", list)),
        smoke=_take(raw, "smoke", bool),
        models=dict(raw.get("models", {})),
        commands=dict(raw.get("commands", {})),
        python_paths=tuple(raw.get("python_paths", ())),
        skill_hook=str(raw.get("skill_hook", "")),
        provider_settings=dict(raw.get("provider_settings", {})),
        projects=projects,
        current_project=current,
        overlay=dict(raw.get("overlay", {})),
        project_overlays=dict(raw.get("project_overlays", {})),
    )


def load(path: Path, *, known_features: tuple[str, ...]) -> Spec:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KitError(
            Exit.PRECONDITION,
            f"this deployment has no answers file at {path}",
            fix="run the kit's `init` first",
        ) from None
    except ValueError as exc:
        raise _refuse(f"{path} is not valid JSON: {exc}") from exc
    return parse(raw, known_features=known_features)


def save(spec: Spec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(spec.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scratch.replace(path)
