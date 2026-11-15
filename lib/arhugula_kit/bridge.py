"""The operations the kit asks the installed runtime to perform.

This module runs under the deployment's own interpreter (`<home>/env/bin/python -m
arhugula_kit.bridge <operation>`), reads one JSON object of arguments on stdin and prints
one JSON object: `{"ok": true, "value": ...}` or `{"ok": false, "kind": ..., "message": ...}`.

[LAW:single-enforcer] Placement, config loading, manifest loading, pause-journal
resolution and prompt hashing are the runtime's rules. The kit calls them here and never
re-implements one, so the kit cannot disagree with the runtime it configures.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

Operation = Callable[[dict[str, Any]], Any]


class Refused(Exception):
    """The runtime refused; `kind` is its typed discriminator and `message` its own words."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _load(config_file: str) -> Any:
    from harness_runtime.config_source import RuntimeConfigLoadError, RuntimeConfigSource

    try:
        return RuntimeConfigSource.load(config_file=Path(config_file))
    except RuntimeConfigLoadError as exc:
        raise Refused(exc.FAIL_CLASS, exc.reason) from exc


def load_config(args: dict[str, Any]) -> Any:
    """Load a config through the runtime's loader and report the facts the kit shows."""
    config = _load(args["config"])
    chain = config.routing_manifest.fallback_chains[0] if config.routing_manifest else None
    return {
        "deployment_surface": str(config.deployment_surface.value),
        "repository_root": str(config.repository_root),
        "tenant_id": config.tenant_id,
        "enabled_provider_names": list(config.enabled_provider_names),
        "state_root": str(config.state_placement.state_root) if config.state_placement else None,
        "primary": (
            {"provider": chain.primary.provider, "model": chain.primary.model} if chain else None
        ),
        "memory_enabled": bool(config.memory.enabled),
        "field_count": len(type(config).model_fields),
    }


def config_fields(args: dict[str, Any]) -> Any:
    """Every `RuntimeConfig` field name at this pin, so the kit's matrix can be checked."""
    from harness_runtime.types import RuntimeConfig

    return sorted(RuntimeConfig.model_fields)


def bootstrap_state_root(args: dict[str, Any]) -> Any:
    """Verify the declared state root and, when every check passes, create and stamp it."""
    from harness_runtime.config import state_placement

    config = _load(args["config"])
    if config.state_placement is None:
        raise Refused("placement-required", "the config declares no [runtime.state_placement]")
    try:
        verified = state_placement.bootstrap_state_root(
            config.state_placement,
            repository_root=config.repository_root,
            worktree_base=state_placement.transient_worktree_base(config.repository_root),
            path_bindings=config.path_bindings,
        )
    except state_placement.StateRootPlacementError as exc:
        raise Refused(exc.reason.value, exc.detail) from exc
    return {"state_root": str(verified.realpath)}


def resolve_pause_journal(args: dict[str, Any]) -> Any:
    """Resolve the installation's pause-journal root exactly as a fresh run will."""
    from harness_runtime.lifecycle.installation_state import installation_state_bound
    from harness_runtime.lifecycle.pause_journal_root_resolver import (
        PauseJournalRootUnresolvedError,
        resolve_pause_journal_root,
    )

    config = _load(args["config"])
    with installation_state_bound():
        try:
            return {"pause_journal_root": str(resolve_pause_journal_root(config))}
        except PauseJournalRootUnresolvedError as exc:
            raise Refused(exc.cause.value, str(exc)) from exc


def filesystem_type(args: dict[str, Any]) -> Any:
    from harness_runtime.config import state_placement

    return {"filesystem_type": state_placement.host_filesystem_type(Path(args["path"]))}


def validate_workflow(args: dict[str, Any]) -> Any:
    """Load a manifest through the runtime's loader. No provider is contacted."""
    from harness_runtime.lifecycle.workflow_manifest_loader import (
        WorkflowManifestLoader,
        WorkflowManifestLoadError,
    )

    try:
        workflow = WorkflowManifestLoader.load_workflow(Path(args["manifest"]))
    except WorkflowManifestLoadError as exc:
        raise Refused(exc.FAIL_CLASS, exc.reason) from exc
    entry = workflow.manifest_entry
    return {
        "workflow_id": str(entry.workflow_id),
        "workload_class": str(entry.workload_class.value),
        "topology_pattern": str(entry.topology_pattern.value),
        "engine_class": str(entry.engine_class.value),
        "default_model_binding": {
            "provider": workflow.default_model_binding.provider,
            "model": workflow.default_model_binding.model,
        },
        "steps": [
            {"step_id": str(step.step_id), "step_kind": str(step.step_kind.value)}
            for step in workflow.steps
        ],
    }


def prompt_sha(args: dict[str, Any]) -> Any:
    from harness_is.prompt_manifest import prompt_version_sha

    return {"version_sha": prompt_version_sha(args["content"])}


def versions(args: dict[str, Any]) -> Any:
    from importlib.metadata import version

    return {
        "python": sys.version.split()[0],
        "prefix": sys.prefix,
        "harness_runtime": version("harness-runtime"),
    }


def audit_keygen(args: dict[str, Any]) -> Any:
    """Create an Ed25519 signing key in the form the runtime's local signer loads.

    The runtime ships no key generator. The private key is written as unencrypted PKCS#8
    PEM with mode 0600; the public key and its identity string are written beside it for
    `harness-inspect --signing-key-map`.
    """
    import hashlib
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_path, public_path = Path(args["private"]), Path(args["public"])
    if private_path.exists():
        raise Refused("key-exists", f"{private_path} already exists; a signing key is never overwritten")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    handle = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, "wb") as out:
        out.write(pem)
    public = key.public_key()
    public_path.write_bytes(
        public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    public_path.chmod(0o644)
    der = public.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return {"identity": "ed25519-spki-sha256:" + hashlib.sha256(der).hexdigest()}


def keyring_set(args: dict[str, Any]) -> Any:
    """Store a provider API key in the OS keyring entry the runtime reads."""
    import keyring

    keyring.set_password(args["service"], args["name"], args["secret"])
    return {"stored": args["name"]}


def keyring_delete(args: dict[str, Any]) -> Any:
    import keyring
    from keyring.errors import PasswordDeleteError

    try:
        keyring.delete_password(args["service"], args["name"])
    except PasswordDeleteError as exc:
        raise Refused("not-stored", str(exc)) from exc
    return {"deleted": args["name"]}


def validator_inspect(args: dict[str, Any]) -> Any:
    """Import a validator class the way the runtime will and construct it with its params."""
    import importlib
    import inspect

    sys.path[:0] = list(args.get("python_paths", ()))
    module_name, _, class_name = args["class_qualified_name"].partition(":")
    try:
        cls = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise Refused("not-importable", f"{type(exc).__name__}: {exc}") from exc
    try:
        instance = cls(**args.get("params", {}))
    except Exception as exc:
        raise Refused("not-constructible", f"{type(exc).__name__}: {exc}") from exc
    validate = getattr(instance, "validate", None)
    if validate is None or not inspect.iscoroutinefunction(validate):
        raise Refused("no-validate", "the class has no `async def validate(...)` method")
    return {"class": f"{cls.__module__}:{cls.__qualname__}", "doc": (cls.__doc__ or "").strip()}


def mcp_tools(args: dict[str, Any]) -> Any:
    """Connect to an MCP server over streamable HTTP and list the tools it offers."""
    import asyncio

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def listing() -> list[dict[str, str]]:
        async with streamablehttp_client(args["url"]) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [
                    {"name": tool.name, "description": (tool.description or "").strip()}
                    for tool in tools.tools
                ]

    try:
        return {"tools": asyncio.run(asyncio.wait_for(listing(), timeout=20))}
    except Exception as exc:
        raise Refused("unreachable", f"{type(exc).__name__}: {exc}") from exc


def drift_check(args: dict[str, Any]) -> Any:
    """Compare one alignment-floor primitive's current value with the operator's threshold.

    Uses upstream's own pure functions: the current value over the window (computed from
    the span store for the cache-hit-rate primitive, operator-supplied for the three that
    need a judge by upstream's design), then `detect_drift`. It emits no span event:
    upstream's emitter needs a live parent span, which only a running workflow has.
    """
    import sqlite3
    import time

    from harness_od import alignment_floor_drift_algorithm as algorithm
    from harness_od.alignment_floor_drift_detection import (
        AlignmentFloorPrimitive,
        AlignmentFloorThreshold,
        ObservationWindow,
        ObservationWindowKind,
        detect_drift,
    )

    primitive = AlignmentFloorPrimitive(args["primitive"])
    kind = ObservationWindowKind(args["window_kind"])
    window = (
        ObservationWindow(kind=kind, time_window_seconds=float(args["window_size"]))
        if kind is ObservationWindowKind.TIME_WINDOW
        else ObservationWindow(kind=kind, sample_window_count=int(args["window_size"]))
    )
    threshold = AlignmentFloorThreshold(
        primitive=primitive, threshold_value=float(args["threshold"]), observation_window=window
    )
    current = args.get("judge_value")
    if current is None:
        conn = sqlite3.connect(f"file:{args['store']}?mode=ro", uri=True)
        try:
            current = algorithm.compute_current_value(conn, primitive, window, now_ns=time.time_ns())
        except algorithm.NotSpanDerivableError as exc:
            raise Refused("needs-judge-value", str(exc)) from exc
        finally:
            conn.close()
    if current is None:
        return {"current_value": None, "drift": False, "reason": "no data in the window"}
    return {
        "current_value": current,
        "threshold": threshold.threshold_value,
        "drift": detect_drift(primitive, float(current), threshold) is not None,
    }


def skills_load(args: dict[str, Any]) -> Any:
    """Load a skills directory through the runtime's own loader and list what it accepted."""
    from harness_runtime.lifecycle.skills import load_skills_from_dir

    try:
        loaded = load_skills_from_dir(Path(args["directory"]))
    except ValueError as exc:
        raise Refused(type(exc).__name__, str(exc)) from exc
    return {
        "skills": [
            {
                "skill_id": str(skill_id),
                "version_sha": str(skill.manifest.version_sha or ""),
                "body_tokens": int(skill.manifest.body_tokens or 0),
            }
            for skill_id, skill in loaded.items()
        ]
    }


OPERATIONS: dict[str, Operation] = {
    "skills-load": skills_load,
    "audit-keygen": audit_keygen,
    "keyring-set": keyring_set,
    "keyring-delete": keyring_delete,
    "validator-inspect": validator_inspect,
    "mcp-tools": mcp_tools,
    "drift-check": drift_check,
    "load-config": load_config,
    "config-fields": config_fields,
    "bootstrap-state-root": bootstrap_state_root,
    "resolve-pause-journal": resolve_pause_journal,
    "filesystem-type": filesystem_type,
    "validate-workflow": validate_workflow,
    "prompt-sha": prompt_sha,
    "versions": versions,
}


def main(argv: list[str]) -> int:
    operation = OPERATIONS[argv[0]]
    arguments = json.loads(sys.stdin.read() or "{}")
    try:
        reply: dict[str, Any] = {"ok": True, "value": operation(arguments)}
    except Refused as refusal:
        reply = {"ok": False, "kind": refusal.kind, "message": refusal.message}
    print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
