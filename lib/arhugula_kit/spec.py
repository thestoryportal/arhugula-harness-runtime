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
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from arhugula_kit import providers
from arhugula_kit.errors import Exit, KitError

__all__ = [
    "MEMORY_MODES",
    "RESERVED_NAMES",
    "WORKLOADS",
    "CustomProvider",
    "Engine",
    "Observability",
    "Project",
    "Spec",
    "enabled_custom",
    "load",
    "lookup",
    "migrate",
    "parse",
    "project_name_for",
    "read_raw",
    "save",
    "without_provider",
]

FORMAT = 2
"""Format 2 stores, per provider, the list of models it makes available (first = default).
Format 1 stored one model per provider and Ollama's in `ollama_model`; `migrate` reads it."""

WORKLOADS: tuple[str, ...] = (
    "pipeline-automation",
    "software-engineering",
    "research",
    "content-creation",
)

MEMORY_MODES: tuple[str, ...] = ("packet", "packet+tools")

_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
RESERVED_NAMES = ("default", "harness")
"""`default` addresses the deployment default on the command line; `harness` is its config file."""

# What a format-1 file meant for a provider it gave no model: the model that kit version
# had fixed in its catalogue. Frozen here so an old file keeps its meaning; a name that
# has since gone stale is then reported by `provider check` and `doctor`, never replaced.
_FORMAT_1_MODELS: Mapping[str, str] = {
    "claude_code": "sonnet",
    "codex": "gpt-5",
    "antigravity": "Gemini 3.5 Flash (Low)",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o",
}


class Engine(StrEnum):
    """Which Lima VM provides the deployment's Docker engine."""

    NONE = "none"  # no VM: no trace stack and no tier 3
    KIT = "kit"  # the kit's own VM under `<home>/lima`, built for this machine's CPU
    EXISTING = "existing"  # a Lima instance the operator already had


@dataclass(frozen=True)
class Observability:
    """Answer 11: whether the trace stack runs, and the VM whose Docker engine hosts it.

    `lima_home` and `instance` name an existing instance and are empty otherwise: the
    kit's own VM is located from the deployment home, so it survives `relocate`.
    """

    enabled: bool = False
    engine: Engine = Engine.NONE
    lima_home: str = ""
    instance: str = ""


@dataclass(frozen=True)
class Project:
    """An attached project repository. Its name is also its tenant id (decision 7)."""

    path: str
    workloads: tuple[str, ...] = WORKLOADS


@dataclass(frozen=True)
class CustomProvider:
    """A provider the operator added: the runtime's `generic-command` CLI kind."""

    command: str  # the absolute path of the executable
    args: tuple[str, ...]  # the argv after it; `{model}` and `{prompt}` are replaced per call
    family: str
    prompt_transport: str = "stdin"
    response_format: str = "text"
    auth_args: tuple[str, ...] = ()  # the argv of its sign-in check; none means no check


@dataclass(frozen=True)
class Spec:
    home: str
    providers: tuple[str, ...]
    primary: str
    fallback: str  # "" for none
    ollama_host: str
    workloads: tuple[str, ...]
    features: tuple[str, ...]  # enabled fragment names, in the order they were enabled
    memory_mode: str
    observability: Observability
    isolation_tier3: bool
    forbidden_roots: tuple[str, ...]
    smoke: bool
    # provider -> the models it makes available, `<model>` or `<model>@<level>`; the first
    # is its default. Every selected provider has at least one.
    models: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    custom_providers: Mapping[str, CustomProvider] = field(default_factory=dict)
    commands: Mapping[str, str] = field(default_factory=dict)  # CLI provider -> executable path
    python_paths: tuple[str, ...] = ()  # directories added to PYTHONPATH for runs (validators)
    skill_hook: str = ""  # `module:Class` of the skill-activation hook, when one is set
    provider_settings: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # CLI knobs
    drift_thresholds: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # primitive -> threshold, window
    # Ledgers signed from their first entry, by project name ("" is the deployment default).
    # Each carries a cutover record; `deploy.apply` adds a ledger here while it is still empty.
    cutover_ledgers: tuple[str, ...] = ()
    projects: Mapping[str, Project] = field(default_factory=dict)
    current_project: str = ""
    overlay: Mapping[str, Any] = field(default_factory=dict)  # merged last into every config
    project_overlays: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def provider(self, name: str) -> providers.Provider:
        """A provider of this deployment by name: built in, or added by the operator."""
        if name in self.custom_providers:
            return _as_provider(name, self.custom_providers[name], self.models.get(name, ()))
        try:
            return providers.by_name(name)
        except KeyError:
            raise KitError(
                Exit.PRECONDITION,
                f"unknown provider {name!r} (known: {', '.join(p.name for p in self.known_providers())})",
                fix="arhugula provider list, or add your own: arhugula provider add --help",
            ) from None

    def known_providers(self) -> tuple[providers.Provider, ...]:
        """Every provider this deployment can enable: the built-in ones, then the operator's."""
        return (*providers.CATALOGUE, *(self.provider(name) for name in self.custom_providers))

    def available(self, provider: str) -> tuple[str, ...]:
        return tuple(self.models.get(provider, ()))

    def model_of(self, provider: str) -> str:
        """The provider's default model: the first of its available models."""
        return self.models[provider][0]

    def with_feature(self, name: str, enabled: bool) -> Spec:
        kept = tuple(f for f in self.features if f != name)
        return replace(self, features=(*kept, name) if enabled else kept)

    def to_json(self) -> dict[str, Any]:
        return {"format": FORMAT, **asdict(self)}


def _as_provider(name: str, entry: CustomProvider, models: tuple[str, ...]) -> providers.Provider:
    return providers.custom(
        name,
        command=entry.command,
        args=entry.args,
        family=entry.family,
        prompt_transport=entry.prompt_transport,
        response_format=entry.response_format,
        auth_args=entry.auth_args,
        suggested_model=models[0] if models else "",
    )


def project_name_for(path: Path) -> str:
    """A project name from its directory name: lowercase, digits and hyphens."""
    name = re.sub(r"[^a-z0-9]+", "-", path.name.lower()).strip("-")
    return name or "project"


def _refuse(message: str, *, fix: str | None = None) -> KitError:
    return KitError(Exit.PRECONDITION, message, fix=fix)


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


def _observability(raw: Mapping[str, Any]) -> Observability:
    enabled = _take(raw, "enabled", bool)
    word = _take(raw, "engine", str)
    if word not in tuple(Engine):
        raise _refuse(f"`observability.engine` must be one of {', '.join(Engine)}")
    engine = Engine(word)
    lima_home, instance = str(raw.get("lima_home", "")), str(raw.get("instance", ""))
    if engine is Engine.EXISTING and not (lima_home and instance):
        raise _refuse("`observability.engine` is `existing` but no `lima_home` and `instance` are given")
    if engine is not Engine.EXISTING and (lima_home or instance):
        raise _refuse("`observability.lima_home` and `.instance` belong to the `existing` engine only")
    if enabled and engine is Engine.NONE:
        raise _refuse("`observability.enabled` is true but `observability.engine` is `none`")
    return Observability(enabled=enabled, engine=engine, lima_home=lima_home, instance=instance)


def migrate(raw: Mapping[str, Any]) -> dict[str, Any]:
    """An answers document in the current shape, whatever format it was written in.

    Format 1 kept one model per provider and Ollama's under `ollama_model`. Each becomes
    the provider's one available model, so the file means what it meant. A document that
    is already current comes back unchanged.
    """
    stored = raw.get("models", {})
    one_model_each = isinstance(stored, Mapping) and any(isinstance(m, str) for m in stored.values())
    if not (raw.get("format") == 1 or "ollama_model" in raw or one_model_each):
        return dict(raw)
    models = {name: [m] if isinstance(m, str) else list(m) for name, m in dict(stored).items()}
    for name in raw.get("providers", ()):
        meant = raw.get("ollama_model", "") if name == "ollama" else _FORMAT_1_MODELS.get(name, "")
        if name not in models and meant:
            models[name] = [meant]
    document = {key: value for key, value in raw.items() if key != "ollama_model"}
    return {**document, "models": models, **({"format": FORMAT} if "format" in raw else {})}


def without_provider(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    """An answers document with every mention of one provider's selection and settings removed.

    A fallback that was this provider becomes no fallback; a default provider cannot be
    removed this way, because only the operator can name the next one.
    """
    document = dict(raw)
    document["providers"] = [n for n in raw.get("providers", ()) if n != name]
    if raw.get("fallback") == name:
        document["fallback"] = ""
    for key in ("models", "commands", "provider_settings"):
        document[key] = {n: value for n, value in dict(raw.get(key, {})).items() if n != name}
    return document


def _strings(entry: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    values = entry.get(key, ())
    if not isinstance(values, list | tuple) or not all(isinstance(v, str) and v.strip() for v in values):
        raise _refuse(f"`{where}.{key}` must be a list of non-empty strings")
    return tuple(values)


def _custom_providers(raw: Mapping[str, Any]) -> dict[str, CustomProvider]:
    found: dict[str, CustomProvider] = {}
    builtin = tuple(p.name for p in providers.CATALOGUE)
    for name, entry in dict(raw.get("custom_providers", {})).items():
        where = f"custom_providers.{name}"
        if not providers.CUSTOM_NAME.fullmatch(name):
            raise _refuse(
                f"the custom provider name {name!r} must start with a lowercase letter and hold "
                "lowercase letters, digits and underscores only, at most 32 characters"
            )
        if name in builtin or name in providers.RETIRED:
            raise _refuse(f"the custom provider name {name!r} is the name of a built-in provider; choose another")
        if name in providers.RESERVED_NAMES:
            raise _refuse(f"the custom provider name {name!r} has a meaning of its own on the command line; choose another")
        if not isinstance(entry, Mapping):
            raise _refuse(f"`{where}` must be an object")
        command = entry.get("command", "")
        if not isinstance(command, str) or not Path(command).is_absolute():
            raise _refuse(f"`{where}.command` must be the absolute path of an executable")
        choices = (
            ("family", providers.FAMILIES, None),
            ("prompt_transport", providers.PROMPT_TRANSPORTS, "stdin"),
            ("response_format", providers.RESPONSE_FORMATS, "text"),
        )
        picked = {key: entry.get(key, default) for key, _, default in choices}
        for key, allowed, _ in choices:
            if picked[key] not in allowed:
                raise _refuse(f"`{where}.{key}` must be one of: {', '.join(allowed)} (got {picked[key]!r})")
        args = _strings(entry, "args", where)
        if any("{prompt}" in arg for arg in args) and picked["prompt_transport"] != "arg":
            raise _refuse(
                f"`{where}.args` uses `{{prompt}}`, which the runtime fills in only when the prompt "
                "is passed as an argument",
                fix="add `--prompt-transport arg`, or drop `{prompt}` and let the command read the prompt from standard input",
            )
        found[name] = CustomProvider(
            command=command, args=args, auth_args=_strings(entry, "auth_args", where), **picked
        )
    return found


def lookup(raw: Mapping[str, Any]) -> dict[str, providers.Provider]:
    """Every provider an answers document can name: the built-in ones, then the operator's."""
    document = migrate(raw)
    models = dict(document.get("models", {}))
    return {p.name: p for p in providers.CATALOGUE} | {
        name: _as_provider(name, entry, tuple(models.get(name, ())))
        for name, entry in _custom_providers(document).items()
    }


def enabled_custom(raw: Mapping[str, Any]) -> tuple[providers.Provider, ...]:
    """The operator's own providers that an answers document selects, as provider values."""
    document = migrate(raw)
    selected = tuple(document.get("providers", ()))
    models = dict(document.get("models", {}))
    return tuple(
        _as_provider(name, entry, tuple(models.get(name, ())))
        for name, entry in _custom_providers(document).items()
        if name in selected
    )


def _models(
    raw: Mapping[str, Any], selected: tuple[str, ...], lookup: Mapping[str, providers.Provider]
) -> dict[str, tuple[str, ...]]:
    stored = raw.get("models", {})
    if not isinstance(stored, Mapping):
        raise _refuse("`models` must be an object: one list of models per provider")
    models: dict[str, tuple[str, ...]] = {}
    for name, listed in stored.items():
        if name in providers.RETIRED:
            # A retired provider that is not selected leaves only this entry behind; it
            # configures nothing. A selected one was refused above, with its fix.
            continue
        if name not in lookup:
            raise _refuse(f"`models` names an unknown provider {name!r} (known: {', '.join(lookup)})")
        if not isinstance(listed, list | tuple) or not all(isinstance(m, str) for m in listed):
            raise _refuse(f"`models.{name}` must be a list of model names")
        try:
            # With no list to check against, this still holds the vocabulary: a level only
            # where the provider takes one, and only a level the provider has.
            models[name] = tuple(providers.resolve(lookup[name], model, ()).ref for model in listed)
        except providers.ModelRefused as refused:
            raise _refuse(f"`models.{name}`: {refused}") from refused
    for name in selected:
        if not models.get(name):
            raise _refuse(
                f"`models` names no model for the selected provider `{name}`",
                fix=f"arhugula provider enable {name} --model <model>  (in an answers file for "
                f'`init --answers`: add "{name}": ["<model>"] under `models`)',
            )
    return models


def parse(raw: Mapping[str, Any], *, known_features: tuple[str, ...]) -> Spec:
    """Parse the JSON document into a `Spec`, or refuse naming what is wrong."""
    raw = migrate(raw)
    if raw.get("format") != FORMAT:
        raise _refuse(f"`format` must be {FORMAT} (got {raw.get('format')!r})")
    for name in _take(raw, "providers", list):
        if name in providers.RETIRED:
            removal = (
                "run the kit's `init --reconfigure` and choose another default provider"
                if raw.get("primary") == name
                else f"arhugula provider disable {name}"
            )
            raise _refuse(
                f"`providers` names `{name}`, which is no longer a provider: {providers.RETIRED[name]}",
                fix=f"{removal}  (in an answers file for `init --answers`: delete `{name}` from "
                "`providers`, `primary` and `fallback`)",
            )
    custom = _custom_providers(raw)
    lookup = {p.name: p for p in providers.CATALOGUE} | {
        name: _as_provider(name, entry, ()) for name, entry in custom.items()
    }
    selected = _names(raw, "providers", tuple(lookup), "provider")
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
    projects: dict[str, Project] = {}
    for name, entry in dict(raw.get("projects", {})).items():
        if not _NAME.fullmatch(name):
            raise _refuse(
                f"project name {name!r} must be lowercase letters, digits and hyphens, "
                "at most 63 characters"
            )
        if name in RESERVED_NAMES:
            raise _refuse(f"project name {name!r} is reserved; attach it under another name with --name")
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
        ollama_host=_take(raw, "ollama_host", str),
        workloads=_names(raw, "workloads", WORKLOADS, "workload class"),
        features=_names(raw, "features", known_features, "feature"),
        memory_mode=memory_mode,
        observability=_observability(_take(raw, "observability", dict)),
        isolation_tier3=_take(raw, "isolation_tier3", bool),
        forbidden_roots=tuple(_take(raw, "forbidden_roots", list)),
        smoke=_take(raw, "smoke", bool),
        models=_models(raw, selected, lookup),
        custom_providers=custom,
        commands=dict(raw.get("commands", {})),
        python_paths=tuple(raw.get("python_paths", ())),
        skill_hook=str(raw.get("skill_hook", "")),
        provider_settings=dict(raw.get("provider_settings", {})),
        drift_thresholds=dict(raw.get("drift_thresholds", {})),
        cutover_ledgers=tuple(raw.get("cutover_ledgers", ())),
        projects=projects,
        current_project=current,
        overlay=dict(raw.get("overlay", {})),
        project_overlays=dict(raw.get("project_overlays", {})),
    )


def read_raw(path: Path) -> dict[str, Any]:
    """The answers file as stored, before any parsing."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KitError(
            Exit.PRECONDITION,
            f"this deployment has no answers file at {path}",
            fix="run the kit's `init` first",
        ) from None
    except ValueError as exc:
        raise _refuse(f"{path} is not valid JSON: {exc}") from exc


def load(path: Path, *, known_features: tuple[str, ...]) -> Spec:
    raw = read_raw(path)
    try:
        return parse(raw, known_features=known_features)
    except KitError as refused:
        raise KitError(refused.exit_code, f"{path}: {refused.message}", fix=refused.fix) from refused


def save(spec: Spec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    scratch.write_text(json.dumps(spec.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scratch.replace(path)
