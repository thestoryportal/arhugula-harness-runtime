"""Workflow manifests: where they live, and how a new one is derived.

`workflow new` does not carry its own templates. It derives a starting manifest from the
example upstream ships for that topology, at the installed pin, so a new manifest always
has the shape this runtime version loads.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from arhugula_kit import providers, toml_out
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home
from arhugula_kit.spec import Spec

__all__ = ["TOPOLOGY_EXAMPLES", "derive", "manifests_in"]

TOPOLOGY_EXAMPLES: Mapping[str, str] = {
    "single-threaded-linear": "ollama-first.toml",
    "decentralized-handoff": "ollama-decentralized-handoff.toml",
    "parallelization": "ollama-parallelization.toml",
    "orchestrator-workers": "ollama-orchestrator-workers.toml",
    "hierarchical-delegation": "ollama-hierarchical-delegation.toml",
    "evaluator-optimizer": "ollama-evaluator-optimizer.toml",
}


def manifests_in(directory: Path) -> tuple[Path, ...]:
    """Manifest files directly in a directory: TOML and YAML."""
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(p for p in directory.iterdir() if p.suffix in (".toml", ".yaml", ".yml") and p.is_file())
    )


def _params_for(family: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Step parameters in the shape the provider family reads.

    The shipped topology examples carry Ollama's shape (`options.num_predict`, `format`).
    Every other provider reads the messages shape (`max_tokens`).
    """
    if family == "local_open_weight":
        return dict(params)
    limit = dict(params.get("options", {})).get("num_predict", params.get("max_tokens", 256))
    return {"max_tokens": limit}


def _retarget(node: Any, binding: Mapping[str, str], family: str) -> Any:
    """Rewrite every model binding and step payload in a manifest tree for one provider."""
    if isinstance(node, list):
        return [_retarget(item, binding, family) for item in node]
    if not isinstance(node, Mapping):
        return node
    rewritten = {key: _retarget(value, binding, family) for key, value in node.items()}
    if {"provider", "model"} <= rewritten.keys() and all(
        isinstance(rewritten[k], str) for k in ("provider", "model")
    ):
        rewritten.update({k: v for k, v in binding.items() if k in rewritten})
    if "messages" in rewritten and "params" in rewritten:
        rewritten["params"] = _params_for(family, rewritten["params"])
    return rewritten


def derive(home: Home, spec: Spec, topology: str, name: str) -> str:
    """A new manifest for `topology`, bound to the deployment's default provider."""
    try:
        source = home.upstream / "examples" / TOPOLOGY_EXAMPLES[topology]
    except KeyError:
        raise KitError(
            Exit.USAGE,
            f"unknown topology {topology!r} (known: {', '.join(TOPOLOGY_EXAMPLES)})",
        ) from None
    document = tomllib.loads(source.read_text(encoding="utf-8"))
    provider = providers.by_name(spec.primary)
    binding = {"provider": provider.name, "model": spec.model_of(provider.name), "family": provider.family}
    document = _retarget(document, binding, provider.family)
    document["workflow"]["workflow_id"] = name
    header = (
        f"Workflow manifest `{name}`: {topology}.\n"
        f"Derived by `arhugula workflow new` from upstream's examples/{source.name} at the\n"
        "installed pin. Edit the steps and their prompts; keep the field names.\n"
        "Which provider serves a step is decided by the deployment's routing, not by the\n"
        "bindings written here: see `arhugula routing show`.\n"
        "Check your edits without calling any provider: arhugula workflow validate <file>"
    )
    return toml_out.dumps(document, header=header)
