"""Shared fixtures: a machine and a set of answers that need no real machine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from arhugula_kit import providers
from arhugula_kit.detect import Machine


def machine(**changes: Any) -> Machine:
    """A Mac with everything in place; pass a field to break it."""
    states = tuple(
        providers.ProviderState(provider, providers.Status.READY, "ready (fixture)", Path("/fixture/bin") / (provider.command or provider.name))
        for provider in providers.CATALOGUE
    )
    base: dict[str, Any] = dict(
        system="Darwin",
        arch="arm64",
        macos_version="15.1",
        command_line_tools="/Library/Developer/CommandLineTools",
        git=Path("/usr/bin/git"),
        brew=Path("/opt/homebrew/bin/brew"),
        uv=Path("/opt/homebrew/bin/uv"),
        python312="3.12.9",
        ollama_cli=Path("/opt/homebrew/bin/ollama"),
        limactl=Path("/opt/homebrew/bin/limactl"),
        lima_version=(2, 2, 1),
        kit_vm=None,
        kit_engine=None,
        provider_states=states,
        ollama_host="http://127.0.0.1:11434",
        ollama_models=("llama3.2:3b",),
        lima_instances=(),
        time_machine_destinations=(),
    )
    return Machine(**{**base, **changes})


def answers(home: Path, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "home": str(home),
        "providers": ["claude_code", "ollama"],
        "primary": "claude_code",
        "fallback": "ollama",
        "ollama_model": "llama3.2:3b",
        "ollama_host": "http://127.0.0.1:11434",
        "project": "",
        "workloads": ["pipeline-automation", "software-engineering", "research", "content-creation"],
        "features": ["memory"],
        "memory_mode": "packet+tools",
        "observability": {"enabled": False, "engine": "none", "lima_home": "", "instance": ""},
        "isolation_tier3": False,
        "forbidden_roots": [],
        "smoke": True,
    }
    return {**base, **changes}
