"""Render the answers file into the files the runtime reads.

One function turns a `Spec` and a target (the deployment default, or one attached
project) into a configuration document: the base the answers decide, then each enabled
feature fragment, then the overlay the operator's verbs have built. Nothing else writes a
runtime config.

[LAW:dataflow-not-control-flow] Every config is produced by the same three merges in the
same order. A deployment with no features and no overlay merges two empty documents.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from arhugula_kit import modelwrap, proc, providers
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, STACK_PORTS, Home
from arhugula_kit.spec import Spec

__all__ = [
    "Fragment",
    "Target",
    "cutover_record",
    "deep_merge",
    "fragments",
    "header",
    "render_config",
    "with_new_cutover_ledgers",
    "targets",
    "wrappers",
    "write_installation_state",
]

AUDIT_SIGNING = "audit-signing"  # the feature fragment that turns the local signer on
RECORD_KEY_ID = "arhugula-cutover-record"
RECORD_KEY = "audit-cutover-ed25519.pem"
CUTOVER_RECORD = "audit-cutover-record.json"
OTLP_ENDPOINT = f"http://127.0.0.1:{STACK_PORTS['OTLP gRPC']}"
SERVICE_NAME = "arhugula-harness"
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


@dataclass(frozen=True)
class Target:
    """What one generated config is for: the deployment default or an attached project."""

    name: str  # "" for the deployment default
    repository: Path
    state: Path  # where this target's ledger and memory live, inside the state root
    tenant_id: str  # "" for none
    workloads: tuple[str, ...]
    config_file: Path

    @property
    def label(self) -> str:
        return self.name or "deployment default"


def targets(spec: Spec, home: Home) -> tuple[Target, ...]:
    """The deployment default, then one target per attached project."""
    default = Target(
        name="",
        repository=home.upstream,
        state=home.state,
        tenant_id="",
        workloads=spec.workloads,
        config_file=home.deployment_config,
    )
    attached = tuple(
        Target(
            name=name,
            repository=Path(project.path),
            state=home.project_state(name),
            tenant_id=name,
            workloads=project.workloads,
            config_file=home.project_config(name),
        )
        for name, project in sorted(spec.projects.items())
    )
    return (default, *attached)


@dataclass(frozen=True)
class Fragment:
    """A named feature: a TOML document with placeholders, merged into every config."""

    name: str
    title: str
    summary: str
    needs: str  # what the operator must have in place, in words; "" for nothing
    body: str  # TOML text, placeholders unresolved


def fragments(kit: Path = KIT_ROOT) -> dict[str, Fragment]:
    """Every fragment the kit ships, by name. A fragment's `#:` lines are its description."""
    found: dict[str, Fragment] = {}
    for path in sorted((kit / "fragments").glob("*.toml")):
        meta: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#: "):
                key, _, value = line[3:].partition(" = ")
                meta[key.strip()] = value.strip()
        try:
            found[path.stem] = Fragment(
                name=path.stem,
                title=meta["title"],
                summary=meta["summary"],
                needs=meta.get("needs", ""),
                body=path.read_text(encoding="utf-8"),
            )
        except KeyError as missing:
            raise KitError(
                Exit.INTERNAL, f"fragment {path.name} has no `#: {missing.args[0]} = ...` line"
            ) from None
    return found


def deep_merge(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    """`extra` over `base`: mappings merge key by key; every other value replaces."""
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _substitutions(spec: Spec, home: Home, target: Target) -> dict[str, str]:
    return {
        **home.substitutions(),
        "{{PRIMARY_LABEL}}": f"{spec.primary}:{spec.model_of(spec.primary)}",
        "{{REPOSITORY}}": str(target.repository),
        "{{TARGET_STATE}}": str(target.state),
    }


def _resolve(text: str, values: Mapping[str, str], *, where: str) -> str:
    for token, value in values.items():
        text = text.replace(token, value)
    left = PLACEHOLDER.search(text)
    if left is not None:
        raise KitError(Exit.INTERNAL, f"{where} uses an unknown placeholder {left.group(0)}")
    return text


def _resolve_tree(tree: Any, values: Mapping[str, str], *, where: str) -> Any:
    """Resolve placeholders inside a stored overlay (JSON) the same way as in a fragment."""
    return json.loads(_resolve(json.dumps(tree), values, where=where))


def _binding(provider: str, spec: Spec) -> dict[str, str]:
    return {
        "provider": provider,
        "model": spec.model_of(provider),
        "family": spec.provider(provider).family,
    }


def _command_of(provider: providers.Provider, spec: Spec) -> str:
    """The absolute path of a CLI provider's executable: the operator's override, else found.

    A provider the operator added is its own absolute command, given at `provider add`. An
    override written as a bare name is looked up on PATH here, as the runtime did before the
    wrapper: the wrapper runs in the runtime's working directory, where a bare name finds nothing.
    """
    override = provider.command if provider.is_custom else spec.commands.get(provider.name, "")
    repoint = f"arhugula provider enable {provider.name} --command <absolute-path-to-{provider.command}>"
    if override:
        found = Path(override) if Path(override).is_absolute() else proc.which(override)
        if found is None:
            raise KitError(
                Exit.PRECONDITION, f"the command `{override}` set for {provider.name} is not on PATH", fix=repoint
            )
    else:
        found = providers.resolve_command(provider)
        if found is None:
            raise KitError(
                Exit.PRECONDITION,
                f"the {provider.title} is selected but `{provider.command}` is not installed",
                fix=f"install it, or run `arhugula provider disable {provider.name}`",
            )
    # The kit's own wrapper given as the real executable would exec itself until the step times out.
    if modelwrap.is_generated(found):
        raise KitError(
            Exit.PRECONDITION,
            f"the command for {provider.name} is {found}, the kit's own wrapper, not the provider's CLI",
            fix=repoint,
        )
    return str(found)


def _wrapped(spec: Spec) -> tuple[providers.Provider, ...]:
    """The selected providers whose CLI the runtime reaches through the kit's level wrapper."""
    return tuple(p for p in map(spec.provider, spec.providers) if p.level_args)


def wrappers(spec: Spec, home: Home) -> dict[Path, str]:
    """Every level wrapper the deployment needs, by path, with the real executable written in."""
    return {modelwrap.path(home, p): modelwrap.script(p, _command_of(p, spec)) for p in _wrapped(spec)}


def _cli_entry(provider: providers.Provider, spec: Spec, home: Home, required: set[str]) -> dict[str, Any]:
    """One `external_cli_providers` entry: a built-in CLI kind, or the operator's own command."""
    wrapped = provider in _wrapped(spec)
    entry: dict[str, Any] = {
        "provider": provider.name,
        "kind": provider.cli_kind,
        "command": str(modelwrap.path(home, provider)) if wrapped else _command_of(provider, spec),
        "timeout_seconds": 120,
        "auth_check": provider.runtime_auth_check,
        "optional": provider.name not in required,
    }
    if provider.is_custom:
        entry |= {
            "args": list(provider.args),
            "auth_args": list(provider.auth_args),
            "response_format": provider.response_format,
            "prompt_transport": provider.prompt_transport,
        }
    return {**entry, **spec.provider_settings.get(provider.name, {})}


def _base(spec: Spec, home: Home, target: Target) -> dict[str, Any]:
    """The config the init answers decide, before any feature or overlay."""
    required = {spec.primary, spec.fallback} - {""}
    ordered = [spec.primary, *([spec.fallback] if spec.fallback else [])]
    ordered += [name for name in spec.providers if name not in ordered]
    selected = [spec.provider(name) for name in ordered]

    primary = spec.provider(spec.primary)
    same_family: list[dict[str, str]] = []
    cross_family: list[dict[str, str]] = []
    if spec.fallback:
        bucket = (
            same_family
            if spec.provider(spec.fallback).family == primary.family
            else cross_family
        )
        bucket.append(_binding(spec.fallback, spec))

    places = {
        "SKILLS": target.repository / ".agents" / "skills",
        "PROMPTS": target.repository / ".harness" / "onboarding" / "prompts",
        "ROUTING_MANIFEST": target.repository / ".harness" / "onboarding" / "routing-manifest",
        "STATE_LEDGER": target.state / "state-ledger",
    }
    runtime: dict[str, Any] = {
        "deployment_surface": "local-development",
        "repository_root": str(target.repository),
        "default_topology": "single-threaded-linear",
        "enabled_provider_names": ordered,
        "mcp_clients": [],
        "pidfile_path": str(home.run / f"{target.name or 'default'}.pid"),
        "memory": {
            "enabled": False,
            "standard_tools_enabled": spec.memory_mode == "packet+tools",
        },
        "otel": {
            "otlp_endpoint": OTLP_ENDPOINT,
            # The runtime sets no service name; without one a trace backend files every
            # run under `unknown_service`.
            "additional_resource_attrs": [
                ["service.name", SERVICE_NAME],
                ["service.namespace", target.name or "default"],
            ],
        },
        "collector": {"span_store_path": str(home.span_store)},
        "state_placement": {
            "state_root": str(home.state),
            "forbidden_roots": list(spec.forbidden_roots),
        },
        "path_bindings": {
            "raw_entries": [
                {
                    "path_class": path_class,
                    "workflow_class": workload,
                    "deployment_surface": "local-development",
                    "path": str(place),
                }
                for workload in target.workloads
                for path_class, place in places.items()
            ]
        },
        "external_cli_providers": [
            _cli_entry(provider, spec, home, required)
            for provider in selected
            if provider.access is providers.Access.CLI
        ],
        "routing_manifest": {
            "manifest_version": 1,
            "per_role_bindings": {},
            "per_workload_overrides": {},
            "retry_policies": {},
            "fallback_chains": [
                {
                    "primary": _binding(spec.primary, spec),
                    "same_family": same_family,
                    "cross_family": cross_family,
                }
            ],
        },
    }
    if target.tenant_id:
        runtime["tenant_id"] = target.tenant_id
    if "ollama" in spec.providers:
        runtime["ollama_host"] = spec.ollama_host
        runtime["ollama_optional"] = "ollama" not in required
    for sdk in ("anthropic", "openai"):
        if sdk in spec.providers:
            runtime[f"{sdk}_optional"] = sdk not in required
    return {"runtime": runtime}


def cutover_record(target: Target) -> Path:
    return target.state / "state-ledger" / CUTOVER_RECORD


def ledger_is_empty(target: Target) -> bool:
    """Whether a target's ledger has no history yet, so its first run can be a signed one."""
    ledger = target.state / "state-ledger"
    return not any(
        path.is_file() and path.stat().st_size > 0
        for path in (ledger / "state.jsonl", ledger / "audit-entries.jsonl")
    )


def with_new_cutover_ledgers(spec: Spec, home: Home) -> Spec:
    """Record every still-empty ledger as signed from its first entry, while signing is on.

    The runtime writes a ledger's cutover record at its first signed run, and refuses to
    start on a ledger that has entries and no record. So the decision is taken once, while
    the ledger is empty, and stored; it is never re-derived from what is on disk later.
    A record that goes missing afterwards is the runtime's to refuse, loudly.
    """
    if AUDIT_SIGNING not in spec.features:
        return spec
    fresh = [
        target.name
        for target in targets(spec, home)
        if target.name not in spec.cutover_ledgers and ledger_is_empty(target)
    ]
    return replace(spec, cutover_ledgers=(*spec.cutover_ledgers, *fresh)) if fresh else spec


def _cutover(spec: Spec, home: Home, target: Target) -> dict[str, Any]:
    """The cutover-record settings for a ledger signed from its first entry, else nothing."""
    if AUDIT_SIGNING not in spec.features or target.name not in spec.cutover_ledgers:
        return {}
    return {
        "runtime": {
            "audit_cutover_record_key_id": RECORD_KEY_ID,
            "audit_cutover_record_path": str(cutover_record(target)),
            "audit_ledger_binding_id": target.name or "default",
            "audit_signing": {"local_key_paths": {RECORD_KEY_ID: str(home.keys / RECORD_KEY)}},
        }
    }


def render_config(
    spec: Spec, home: Home, target: Target, known: Mapping[str, Fragment]
) -> dict[str, Any]:
    """The complete config document for one target."""
    values = _substitutions(spec, home, target)
    document = _base(spec, home, target)
    for name in spec.features:
        text = _resolve(known[name].body, values, where=f"fragment {name}")
        document = deep_merge(document, tomllib.loads(text))
    document = deep_merge(document, _cutover(spec, home, target))
    document = deep_merge(document, _resolve_tree(spec.overlay, values, where="the overlay"))
    project_overlay = spec.project_overlays.get(target.name, {})
    return deep_merge(
        document, _resolve_tree(project_overlay, values, where=f"the {target.label} overlay")
    )


def header(target: Target, home: Home) -> str:
    return (
        f"Arhugula Harness runtime config: {target.label}.\n"
        f"GENERATED from {home.spec_file}. Do not edit: your change would be overwritten.\n"
        "Change it with an `arhugula` verb (`arhugula --help`), which edits the answers file\n"
        "and regenerates this file. No secret belongs here; keys live in the OS keyring."
    )


def write_installation_state(home: Home) -> Path:
    """The runtime's installation-state document, naming this home's pause-journal root."""
    template = (KIT_ROOT / "templates" / "installation-state.json.tmpl").read_text(encoding="utf-8")
    text = _resolve(template, home.substitutions(), where="installation-state.json.tmpl")
    json.loads(text)
    home.installation_state.parent.mkdir(parents=True, exist_ok=True)
    home.installation_state.write_text(text, encoding="utf-8")
    return home.installation_state
