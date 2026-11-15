"""The providers the runtime can dispatch to, and how the kit finds and checks each.

[LAW:one-type-per-behavior] One `Provider` type; the seven providers are seven values.
The catalogue is the single place a provider's command, default model, model family and
caveat are stated; prompts, generated configuration, `provider check` and the docs read it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from arhugula_kit import proc

__all__ = [
    "CATALOGUE",
    "Access",
    "Provider",
    "ProviderState",
    "Status",
    "by_name",
    "check",
    "ollama_models",
    "resolve_command",
]


KEYRING_SERVICE = "harness"
"""The runtime's default keyring service (`provider_secrets.keyring_service`)."""


class Access(StrEnum):
    """How the runtime reaches a provider."""

    CLI = "cli"  # a signed-in command-line tool, run once per step in print mode
    OLLAMA = "ollama"  # the local Ollama server
    SDK = "sdk"  # a hosted API, with a key in the OS keyring


@dataclass(frozen=True)
class Provider:
    name: str  # the name configs and `--provider` use
    letter: str  # the key in the init multi-select
    title: str
    access: Access
    default_model: str
    family: str  # the runtime's model family for fallback-chain placement
    command: str = ""  # CLI providers: the executable
    cli_kind: str = ""  # CLI providers: the runtime's `kind`
    runtime_auth_check: bool = False  # whether the runtime probes sign-in at bootstrap
    extra_dirs: tuple[str, ...] = ()  # home-relative directories searched besides PATH
    secret_name: str = ""  # SDK providers: the keyring entry name the runtime reads
    install: tuple[str, ...] = ()  # terminal commands that install it; the first is preferred
    sign_in: str = ""  # the terminal command that signs in, or starts the tool so it can
    caveat: str = ""  # printed at the init prompt, by `provider check`, and in the docs


CATALOGUE: tuple[Provider, ...] = (
    Provider(
        name="claude_code",
        letter="c",
        title="Claude Code CLI",
        access=Access.CLI,
        default_model="sonnet",
        family="anthropic",
        command="claude",
        cli_kind="claude-code",
        runtime_auth_check=True,
        install=(
            "curl -fsSL https://claude.ai/install.sh | bash",
            "brew install --cask claude-code",
        ),
        sign_in="claude",
    ),
    Provider(
        name="ollama",
        letter="o",
        title="Ollama (local models)",
        access=Access.OLLAMA,
        default_model="llama3.2:3b",
        family="local_open_weight",
        command="ollama",
        install=("brew install ollama",),
        sign_in="brew services start ollama",
    ),
    Provider(
        name="codex",
        letter="x",
        title="Codex CLI",
        access=Access.CLI,
        default_model="gpt-5",
        family="openai",
        command="codex",
        cli_kind="codex",
        runtime_auth_check=True,
        install=("brew install --cask codex", "npm install -g @openai/codex"),
        sign_in="codex login",
        caveat=(
            "Upstream marks the Codex profile HELD: the CLI's filesystem read exposure is "
            "an untested boundary. Sign in with `codex login` to use your ChatGPT "
            "subscription; an API key makes every call a paid call. Codex is never the "
            "default primary."
        ),
    ),
    Provider(
        name="gemini",
        letter="g",
        title="Gemini CLI",
        access=Access.CLI,
        default_model="gemini-2.5-flash",
        family="google",
        command="gemini",
        cli_kind="gemini",
        install=("brew install gemini-cli", "npm install -g @google/gemini-cli"),
        sign_in="gemini",
        caveat=(
            "The Gemini CLI refuses individual Google accounts at this release and points "
            "to Antigravity. The runtime dispatches correctly; the CLI itself declines."
        ),
    ),
    Provider(
        name="antigravity",
        letter="a",
        title="Antigravity CLI (agy)",
        access=Access.CLI,
        default_model="Gemini 3.5 Flash (Low)",
        family="google",
        command="agy",
        cli_kind="antigravity",
        runtime_auth_check=True,
        extra_dirs=(".local/bin", ".gemini/bin"),
        install=("curl -fsSL https://antigravity.google/cli/install.sh | bash",),
        sign_in="agy",
    ),
    Provider(
        name="anthropic",
        letter="A",
        title="Anthropic API (key in the keyring; paid)",
        access=Access.SDK,
        default_model="claude-haiku-4-5",
        family="anthropic",
        secret_name="anthropic_key",
        caveat="A hosted API billed per call. The key lives in the OS keyring, never in TOML.",
    ),
    Provider(
        name="openai",
        letter="O",
        title="OpenAI API (key in the keyring; paid)",
        access=Access.SDK,
        default_model="gpt-4o",
        family="openai",
        secret_name="openai_key",
        caveat="A hosted API billed per call. The key lives in the OS keyring, never in TOML.",
    ),
)


def by_name(name: str) -> Provider:
    for provider in CATALOGUE:
        if provider.name == name:
            return provider
    known = ", ".join(p.name for p in CATALOGUE)
    raise KeyError(f"unknown provider {name!r} (known: {known})")


def resolve_command(provider: Provider) -> Path | None:
    """The provider's executable: on PATH, else in one of its known home-relative places."""
    found = proc.which(provider.command)
    if found is not None:
        return found
    for directory in provider.extra_dirs:
        candidate = Path.home() / directory / provider.command
        if candidate.is_file():
            return candidate
    return None


class Status(StrEnum):
    READY = "ready"  # present and signed in (or reachable)
    PAID_ROUTE = "paid-route"  # works, but through an API key billed per call
    NOT_SIGNED_IN = "not-signed-in"
    NOT_INSTALLED = "not-installed"
    UNREACHABLE = "unreachable"
    UNVERIFIED = "unverified"  # present; the tool offers no sign-in check


@dataclass(frozen=True)
class ProviderState:
    provider: Provider
    status: Status
    detail: str
    command: Path | None = None
    fix: str = ""

    @property
    def usable(self) -> bool:
        return self.status in (Status.READY, Status.PAID_ROUTE, Status.UNVERIFIED)


def ollama_models(host: str) -> tuple[str, ...] | None:
    """The models the Ollama server has pulled, or None when it does not answer."""
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=3) as reply:
            listing = json.load(reply)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return tuple(model["name"] for model in listing.get("models", ()))


def _version(command: Path) -> str:
    outcome = proc.run([command, "--version"], timeout=20)
    return outcome.stdout.strip().splitlines()[0] if outcome.ok and outcome.stdout.strip() else ""


def _check_cli(provider: Provider) -> ProviderState:
    command = resolve_command(provider)
    if command is None:
        return ProviderState(
            provider,
            Status.NOT_INSTALLED,
            f"`{provider.command}` is not on PATH",
            fix=f"{provider.install[0]}  (then sign in: `{provider.sign_in}`)",
        )
    version = _version(command)
    match provider.name:
        case "claude_code":
            outcome = proc.run([command, "auth", "status", "--json"], timeout=30)
            try:
                signed_in = bool(json.loads(outcome.stdout).get("loggedIn"))
                method = json.loads(outcome.stdout).get("authMethod", "unknown")
            except ValueError:
                signed_in, method = False, "unknown"
            if signed_in:
                return ProviderState(
                    provider, Status.READY, f"{version}; signed in ({method})", command
                )
            return ProviderState(
                provider,
                Status.NOT_SIGNED_IN,
                f"{version}; `claude auth status` reports not signed in",
                command,
                fix="run `claude` once and sign in",
            )
        case "codex":
            outcome = proc.run([command, "login", "status"], timeout=30)
            report = (outcome.stdout + outcome.stderr).strip()
            first = report.splitlines()[0] if report else "no output"
            if "api key" in report.lower():
                return ProviderState(
                    provider,
                    Status.PAID_ROUTE,
                    f"{version}; API key configured: every call is billed",
                    command,
                    fix="run `codex logout` then `codex login` to use your ChatGPT subscription",
                )
            if outcome.ok and "logged in" in report.lower():
                return ProviderState(provider, Status.READY, f"{version}; {first}", command)
            return ProviderState(
                provider,
                Status.NOT_SIGNED_IN,
                f"{version}; {first}",
                command,
                fix="run `codex login`",
            )
        case _:
            if not version:
                return ProviderState(
                    provider,
                    Status.UNREACHABLE,
                    f"`{command} --version` gave no answer",
                    command,
                    fix=f"run `{command}` once by hand",
                )
            return ProviderState(
                provider,
                Status.UNVERIFIED,
                f"{version}; this CLI offers no sign-in check, so the first run is the check",
                command,
            )


def check(provider: Provider, *, ollama_host: str, ollama_model: str = "") -> ProviderState:
    """The provider's state as its own tool reports it. Reads only; changes nothing."""
    match provider.access:
        case Access.CLI:
            return _check_cli(provider)
        case Access.OLLAMA:
            models = ollama_models(ollama_host)
            if models is None:
                return ProviderState(
                    provider,
                    Status.UNREACHABLE,
                    f"no answer from {ollama_host}",
                    fix="start it with `ollama serve`",
                )
            if ollama_model and ollama_model not in models:
                return ProviderState(
                    provider,
                    Status.NOT_SIGNED_IN,
                    f"reachable at {ollama_host}; model {ollama_model} is not pulled",
                    fix=f"ollama pull {ollama_model}",
                )
            return ProviderState(
                provider, Status.READY, f"reachable at {ollama_host}; {len(models)} models pulled"
            )
        case Access.SDK:
            outcome = proc.run(
                ["security", "find-generic-password", "-s", KEYRING_SERVICE, "-a",
                 provider.secret_name],
                timeout=20,
            )
            if outcome.ok:
                return ProviderState(
                    provider,
                    Status.PAID_ROUTE,
                    f"`{provider.secret_name}` is in the keyring service `{KEYRING_SERVICE}`",
                )
            return ProviderState(
                provider,
                Status.NOT_SIGNED_IN,
                f"`{provider.secret_name}` is not in the keyring service `{KEYRING_SERVICE}`",
                fix=f"arhugula provider key set {provider.name}",
            )
