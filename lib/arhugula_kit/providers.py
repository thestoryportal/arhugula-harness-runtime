"""The providers the runtime can dispatch to, and how the kit finds and checks each.

[LAW:one-type-per-behavior] One `Provider` type. The built-in providers are values in
`CATALOGUE`; a provider the operator adds (`arhugula provider add`) is one more value of
the same type, built by `custom`. The catalogue is the single place a provider's command,
model vocabulary, model family and caveat are stated; prompts, generated configuration,
`provider check` and the docs read it.

A model is written `<model>` or `<model>@<level>`, where the level is the thinking level.
`resolve` is the one place that vocabulary is checked against what a provider offers.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from arhugula_kit import proc

__all__ = [
    "CATALOGUE",
    "FAMILIES",
    "PROMPT_TRANSPORTS",
    "RESPONSE_FORMATS",
    "RETIRED",
    "Access",
    "Chosen",
    "Listing",
    "ModelRefused",
    "Offer",
    "Provider",
    "ProviderState",
    "Status",
    "available_ids",
    "by_name",
    "check",
    "custom",
    "enable_command",
    "first_choice",
    "levels_of",
    "model_id",
    "model_name",
    "ollama_models",
    "parse_antigravity_models",
    "parse_codex_models",
    "resolve",
    "refusals",
    "repair_command",
    "resolve_command",
    "still_offered",
]


KEYRING_SERVICE = "harness"
"""The runtime's default keyring service (`provider_secrets.keyring_service`)."""

# The three vocabularies below are the runtime's own, at the pinned commit: `ProviderFamily`
# in harness_cp/cross_family_fallback_chain.py, and `ExternalCLIPromptTransport` and
# `ExternalCLIResponseFormat` in harness_runtime/types.py. The runtime's loader refuses any
# other value, so a drift here shows as a refused config, never as a wrong one.
FAMILIES: tuple[str, ...] = ("anthropic", "openai", "google", "local_open_weight")
PROMPT_TRANSPORTS: tuple[str, ...] = ("stdin", "arg")
RESPONSE_FORMATS: tuple[str, ...] = ("text", "json", "jsonl")
GENERIC_KIND = "generic-command"
"""The runtime's CLI kind for a command the operator describes (`provider add`)."""

CUSTOM_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
RESERVED_NAMES: tuple[str, ...] = ("none", "default")
"""Words the command line gives a meaning of its own (`--fallback none`, `--project default`)."""

RETIRED: Mapping[str, str] = {
    "gemini": "Google retired the Gemini CLI. The Antigravity CLI (`antigravity`, command "
    "`agy`) is its replacement",
}
"""Providers this kit once configured and no longer does, each with the reason."""

PER_STEP = (
    "its thinking is set per step, in the step's `params` in a workflow manifest "
    "(see docs/workflows.md)"
)


class Access(StrEnum):
    """How the runtime reaches a provider."""

    CLI = "cli"  # a signed-in command-line tool, run once per step in print mode
    OLLAMA = "ollama"  # the local Ollama server
    SDK = "sdk"  # a hosted API, with a key in the OS keyring


class Listing(StrEnum):
    """Where a provider's list of models comes from, which decides what a check can say."""

    NONE = "none"  # the tool lists nothing: any model name is accepted, unchecked
    SIGN_IN = "sign-in"  # the tool lists what this sign-in offers: the authority
    PULLED = "pulled"  # Ollama lists what is pulled; any other model can still be pulled


@dataclass(frozen=True)
class Provider:
    name: str  # the name configs and `--provider` use
    letter: str  # the key in the init multi-select; "" for a custom provider
    title: str
    access: Access
    family: str  # the runtime's model family for fallback-chain placement
    examples: tuple[str, ...] = ()  # model names to show where the tool lists none; the first is proposed
    listing: Listing = Listing.NONE
    list_command: str = ""  # the terminal command that prints the tool's own model list
    command: str = ""  # CLI providers: the executable
    cli_kind: str = ""  # CLI providers: the runtime's `kind`
    runtime_auth_check: bool = False  # whether the runtime probes sign-in at bootstrap
    extra_dirs: tuple[str, ...] = ()  # home-relative directories searched besides PATH
    secret_name: str = ""  # SDK providers: the keyring entry name the runtime reads
    install: tuple[str, ...] = ()  # terminal commands that install it; the first is preferred
    sign_in: str = ""  # the terminal command that signs in, or starts the tool so it can
    caveat: str = ""  # printed at the init prompt, by `provider check`, and in the docs
    # Thinking levels. The runtime passes these CLIs a model and nothing else, so the kit
    # puts a wrapper in front of the CLI that turns `<model>@<level>` into the CLI's own
    # option (see modelwrap.py). A provider with no `level_args` takes no `@level`.
    model_flag: str = ""  # the argv word the runtime puts before the model
    level_args: tuple[str, ...] = ()  # the CLI's option for a level; `{level}` is replaced
    levels: tuple[str, ...] = ()  # the levels, where the tool does not list them per model
    level_elsewhere: str = PER_STEP  # where thinking is set, for a provider that takes no `@level`
    # A custom provider (`generic-command`): how the runtime calls the operator's command.
    args: tuple[str, ...] = ()
    auth_args: tuple[str, ...] = ()
    response_format: str = ""
    prompt_transport: str = ""

    @property
    def suggested_model(self) -> str:
        return self.examples[0] if self.examples else ""

    @property
    def is_custom(self) -> bool:
        return self.cli_kind == GENERIC_KIND


CATALOGUE: tuple[Provider, ...] = (
    Provider(
        name="claude_code",
        letter="c",
        title="Claude Code CLI",
        access=Access.CLI,
        family="anthropic",
        examples=("sonnet", "opus", "haiku", "fable"),
        command="claude",
        cli_kind="claude-code",
        runtime_auth_check=True,
        install=(
            "curl -fsSL https://claude.ai/install.sh | bash",
            "brew install --cask claude-code",
        ),
        sign_in="claude",
        model_flag="--model",
        level_args=("--effort", "{level}"),
        levels=("low", "medium", "high", "xhigh", "max"),
    ),
    Provider(
        name="ollama",
        letter="o",
        title="Ollama (local models)",
        access=Access.OLLAMA,
        family="local_open_weight",
        examples=("llama3.2:3b",),
        listing=Listing.PULLED,
        list_command="ollama list",
        command="ollama",
        install=("brew install ollama",),
        sign_in="brew services start ollama",
    ),
    Provider(
        name="codex",
        letter="x",
        title="Codex CLI",
        access=Access.CLI,
        family="openai",
        listing=Listing.SIGN_IN,
        list_command="codex debug models",
        command="codex",
        cli_kind="codex",
        runtime_auth_check=True,
        install=("brew install --cask codex", "npm install -g @openai/codex"),
        sign_in="codex login",
        caveat=(
            "Upstream marks the Codex profile HELD: the CLI's filesystem read exposure is "
            "an untested boundary. Sign in with `codex login` to use your ChatGPT "
            "subscription; an API key makes every call a paid call. Init does not propose "
            "Codex as the default provider when you selected another one."
        ),
        model_flag="-m",
        level_args=("-c", 'model_reasoning_effort="{level}"'),
    ),
    Provider(
        name="antigravity",
        letter="a",
        title="Antigravity CLI (agy)",
        access=Access.CLI,
        family="google",
        listing=Listing.SIGN_IN,
        list_command="agy models",
        command="agy",
        cli_kind="antigravity",
        runtime_auth_check=True,
        extra_dirs=(".local/bin", ".gemini/bin"),
        install=("curl -fsSL https://antigravity.google/cli/install.sh | bash",),
        sign_in="agy",
        level_elsewhere=(
            "its thinking level is part of the model, so choose the model id that carries "
            "the level you want (`arhugula provider models antigravity` lists them)"
        ),
    ),
    Provider(
        name="anthropic",
        letter="A",
        title="Anthropic API (key in the keyring; paid)",
        access=Access.SDK,
        family="anthropic",
        examples=("claude-haiku-4-5",),
        secret_name="anthropic_key",
        caveat="A hosted API billed per call. The key lives in the OS keyring, never in TOML.",
    ),
    Provider(
        name="openai",
        letter="O",
        title="OpenAI API (key in the keyring; paid)",
        access=Access.SDK,
        family="openai",
        examples=("gpt-4o",),
        secret_name="openai_key",
        caveat="A hosted API billed per call. The key lives in the OS keyring, never in TOML.",
    ),
)


def by_name(name: str) -> Provider:
    """A built-in provider. A deployment's own lookup, custom providers included, is `Spec.provider`."""
    for provider in CATALOGUE:
        if provider.name == name:
            return provider
    known = ", ".join(p.name for p in CATALOGUE)
    raise KeyError(f"unknown provider {name!r} (known: {known})")


def custom(
    name: str,
    *,
    command: str,
    args: Sequence[str],
    family: str,
    prompt_transport: str,
    response_format: str,
    auth_args: Sequence[str] = (),
    suggested_model: str = "",
) -> Provider:
    """A provider the operator described: any command that takes a prompt and prints a reply."""
    return Provider(
        name=name,
        letter="",
        title=f"{name} (custom command)",
        access=Access.CLI,
        family=family,
        examples=(suggested_model,) if suggested_model else (),
        command=command,
        cli_kind=GENERIC_KIND,
        # The runtime's sign-in probe for this kind is the operator's own `auth_args`.
        runtime_auth_check=bool(auth_args),
        args=tuple(args),
        auth_args=tuple(auth_args),
        response_format=response_format,
        prompt_transport=prompt_transport,
        # The runtime hands a custom command only `{model}` and `{prompt}`; a step's
        # `params` never reach it.
        level_elsewhere=(
            "a custom command receives only `{model}` and `{prompt}`, so a thinking option "
            "belongs in its `--args` (arhugula provider add --help)"
        ),
    )


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


# --- models: what a provider offers, and the one check of a model against it --------------


@dataclass(frozen=True)
class Offer:
    """One model a provider's own tool lists."""

    id: str  # what the tool's model option takes
    title: str = ""  # the tool's display name, when it has one
    levels: tuple[str, ...] = ()  # this model's thinking levels, when the tool lists them
    default_level: str = ""  # the level the tool uses when none is named


def _effort(entry: object) -> str:
    return str(entry.get("effort", "")) if isinstance(entry, Mapping) else str(entry)


def parse_codex_models(text: str) -> tuple[Offer, ...]:
    """The models in `codex debug models` output, the CLI's first choice first.

    The CLI marks the models it shows a person with `visibility == "list"` and orders
    them by `priority`.
    """
    try:
        document = json.loads(text)
    except ValueError:
        return ()
    entries = document.get("models", ()) if isinstance(document, dict) else ()
    listed = [m for m in entries if isinstance(m, dict) and m.get("visibility") == "list" and m.get("slug")]
    ranked = sorted(enumerate(listed), key=lambda pair: (pair[1].get("priority", len(listed)), pair[0]))
    return tuple(
        Offer(
            id=str(model["slug"]),
            title=str(model.get("display_name") or ""),
            levels=tuple(level for level in map(_effort, model.get("supported_reasoning_levels") or ()) if level),
            default_level=str(model.get("default_reasoning_level") or ""),
        )
        for _, model in ranked
    )


def parse_antigravity_models(text: str) -> tuple[Offer, ...]:
    """The models in `agy models` output: one `<id><tab><display name>` per line.

    The level is part of an Antigravity model, so an offer carries no separate levels.
    """
    pairs = (line.split("\t", 1) for line in text.splitlines() if "\t" in line)
    return tuple(Offer(id=id_.strip(), title=title.strip()) for id_, title in pairs if id_.strip())


def ollama_models(host: str) -> tuple[str, ...] | None:
    """The models the Ollama server has pulled, or None when it does not answer."""
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=3) as reply:
            listing = json.load(reply)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return tuple(model["name"] for model in listing.get("models", ()))


class ModelRefused(ValueError):
    """A model or level the provider does not have. The message shows what it does have."""


@dataclass(frozen=True)
class Chosen:
    ref: str  # the model as it is stored and passed on: `<id>` or `<id>@<level>`
    note: str = ""  # what could not be checked, and why; "" when the tool's list confirmed it


def model_name(provider: Provider, ref: str) -> str:
    """The model of a stored reference, without its level."""
    return ref.rpartition("@")[0] if provider.level_args and "@" in ref else ref


def _offer_of(model: str, offered: Sequence[Offer]) -> Offer | None:
    """The listed model a name means: its id, or the display name the tool shows for it."""
    return next((offer for offer in offered if model in (offer.id, offer.title)), None)


def model_id(provider: Provider, ref: str, offered: Sequence[Offer]) -> str:
    """The model of a reference as the tool's id, without its level.

    A format-1 answers file stored the display name; this is the id that name means, so a
    stored reference and a typed one compare equal.
    """
    name = model_name(provider, ref)
    offer = _offer_of(name, offered)
    return offer.id if offer is not None else name


def available_ids(provider: Provider, refs: Sequence[str], offered: Sequence[Offer]) -> set[str]:
    """The models of a deployment's available references, as ids, whatever level each carries."""
    return {model_id(provider, ref, offered) for ref in refs}


def levels_of(provider: Provider, offer: Offer | None) -> tuple[str, ...]:
    """A model's thinking levels: its own list's when the tool listed it, else the provider's."""
    return offer.levels if offer is not None else provider.levels


def _listed(offered: Sequence[Offer]) -> str:
    return ", ".join(offer.id for offer in offered)


def resolve(provider: Provider, text: str, offered: Sequence[Offer]) -> Chosen:
    """Check `<model>` or `<model>@<level>` against what the provider offers.

    [LAW:single-enforcer] Init, the verbs and the answers file all pass a model through
    here. `offered` is the tool's own list for this sign-in, empty when it gave none.
    Nothing is ever substituted: a model is confirmed, accepted with a note that says it
    could not be checked, or refused with the list.
    """
    text = text.strip()
    model, at, level = text.rpartition("@") if "@" in text else (text, "", "")
    if at and not provider.level_args:
        raise ModelRefused(f"{provider.title} takes no `@level` on a model (got `{text}`): {provider.level_elsewhere}")
    if not model or (at and not level):
        raise ModelRefused("write a model as `<model>` or `<model>@<level>`" + (f" (got `{text}`)" if text else ""))
    offer = _offer_of(model, offered)
    if offer is None and provider.listing is Listing.SIGN_IN and offered:
        raise ModelRefused(
            f"{provider.title}: this sign-in does not offer the model `{model}`. It offers: {_listed(offered)}"
        )
    canonical = offer.id if offer is not None else model
    # The model goes to the CLI as one argv word: a leading `-` would read as one of its
    # options, and a space would reach it inside the name. A tool that lists models for a
    # sign-in also knows them by display names, which hold spaces; without its list one
    # cannot be told from a typo (an answers file is read without it), so it is noted unchecked.
    spaced = any(char.isspace() for char in level) or canonical != canonical.strip() or (
        provider.listing is not Listing.SIGN_IN and any(char.isspace() for char in canonical)
    )
    if spaced or canonical.startswith("-") or level.startswith("-"):
        raise ModelRefused(
            f"`{text}` is not a model name: a model and a level hold no spaces and do not start with `-`"
        )
    levels = levels_of(provider, offer)
    # A model the tool listed with no levels takes none: the CLI would be sent a level it lacks.
    if level and (levels or offer is not None) and level not in levels:
        raise ModelRefused(
            f"{provider.title}: `{level}` is not a thinking level of `{model}`. "
            + (f"Its levels: {', '.join(levels)}" if levels else "Its list shows none, so write it without `@level`")
        )
    ref = f"{canonical}@{level}" if level else canonical
    if offer is not None:
        return Chosen(ref)
    if provider.listing is Listing.PULLED and offered:
        return Chosen(ref, f"`{canonical}` is not pulled yet. Pull it with: ollama pull {canonical}")
    why = "has no model list" if provider.listing is Listing.NONE else "gave no model list"
    return Chosen(ref, f"`{ref}` could not be checked: {provider.title} {why}")


def first_choice(provider: Provider, offered: Sequence[Offer]) -> str:
    """The model to propose for a provider: its own list's first, else the catalogue's example.

    A sign-in's list is the authority. Ollama's list is only what is pulled, which may be an
    embedding model that cannot chat, so its catalogue model stays the proposal and init
    offers to pull it. "" when neither exists; the operator then names one.
    """
    ids = [offer.id for offer in offered]
    if provider.suggested_model and (provider.listing is not Listing.SIGN_IN or provider.suggested_model in ids):
        return provider.suggested_model
    return ids[0] if ids else ""


def refusals(provider: Provider, refs: Sequence[str], offered: Sequence[Offer]) -> tuple[tuple[str, str], ...]:
    """Each stored model that `resolve` now refuses, with the reason: a model the sign-in stopped offering."""
    found: list[tuple[str, str]] = []
    for ref in refs:
        try:
            resolve(provider, ref, offered)
        except ModelRefused as refused:
            found.append((ref, str(refused)))
    return tuple(found)


def still_offered(provider: Provider, refs: Sequence[str], offered: Sequence[Offer]) -> list[str]:
    """The stored models that still pass `resolve`, in their order."""
    refused = {ref for ref, _ in refusals(provider, refs, offered)}
    return [ref for ref in refs if ref not in refused]


def repair_command(provider: Provider, refs: Sequence[str], offered: Sequence[Offer]) -> str:
    """The command that drops the models a sign-in no longer offers, naming one it does when none is left."""
    kept = still_offered(provider, refs, offered) or [first_choice(provider, offered)]
    return enable_command(provider.name, [ref for ref in kept if ref])


def enable_command(name: str, refs: Sequence[str]) -> str:
    """The command that makes exactly these models a provider's available models."""
    chosen = " ".join(f'--model "{ref}"' if " " in ref else f"--model {ref}" for ref in refs)
    return f"arhugula provider enable {name} {chosen or '--model <model>'}"


# --- state: what the provider's own tool reports on this machine ---------------------------


class Status(StrEnum):
    READY = "ready"  # present and signed in (or reachable)
    PAID_ROUTE = "paid-route"  # works, but through an API key billed per call
    NOT_SIGNED_IN = "not-signed-in"
    NOT_INSTALLED = "not-installed"
    UNREACHABLE = "unreachable"
    MODEL_MISSING = "model-missing"  # Ollama answers, but the chosen model is not pulled
    UNVERIFIED = "unverified"  # present; the tool offers no sign-in check


@dataclass(frozen=True)
class ProviderState:
    provider: Provider
    status: Status
    detail: str
    command: Path | None = None
    fix: str = ""
    models: tuple[Offer, ...] = ()  # what the tool lists, in its own order; empty when it lists nothing

    @property
    def usable(self) -> bool:
        return self.status in (Status.READY, Status.PAID_ROUTE, Status.UNVERIFIED)


def _version(command: Path) -> str:
    outcome = proc.run([command, "--version"], timeout=20)
    return outcome.stdout.strip().splitlines()[0] if outcome.ok and outcome.stdout.strip() else ""


def _codex_models(command: Path) -> tuple[Offer, ...]:
    return parse_codex_models(proc.run([command, "debug", "models"], timeout=30).stdout)


def _check_custom(provider: Provider, command: Path) -> ProviderState:
    if not provider.auth_args:
        return ProviderState(
            provider,
            Status.UNVERIFIED,
            "present; no sign-in check is configured for it (`--auth-args`), so the first run is the check",
            command,
        )
    outcome = proc.run([command, *provider.auth_args], timeout=30)
    shown = " ".join((provider.command, *provider.auth_args))
    if outcome.ok:
        return ProviderState(provider, Status.READY, f"its sign-in check passes (`{shown}`)", command)
    return ProviderState(
        provider,
        Status.NOT_SIGNED_IN,
        f"its sign-in check `{shown}` exited {outcome.code}",
        command,
        fix=f"run `{shown}` by hand and follow what it says",
    )


def _check_cli(provider: Provider) -> ProviderState:
    command = resolve_command(provider)
    if command is None:
        setup = (
            f"{provider.install[0]}  (then sign in: `{provider.sign_in}`)"
            if provider.install
            else f"arhugula provider enable {provider.name} --command <path>  (or: arhugula provider remove {provider.name})"
        )
        return ProviderState(
            provider, Status.NOT_INSTALLED, f"`{provider.command}` is not on PATH", fix=setup
        )
    if provider.is_custom:
        return _check_custom(provider, command)
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
                    models=_codex_models(command),
                )
            if outcome.ok and "logged in" in report.lower():
                return ProviderState(
                    provider, Status.READY, f"{version}; {first}", command, models=_codex_models(command)
                )
            return ProviderState(
                provider,
                Status.NOT_SIGNED_IN,
                f"{version}; {first}",
                command,
                fix="run `codex login`",
            )
        case "antigravity":
            # The runtime's own sign-in check for this CLI is `agy models`.
            outcome = proc.run([command, "models"], timeout=30)
            if outcome.ok and outcome.stdout.strip():
                return ProviderState(
                    provider,
                    Status.READY,
                    f"{version}; signed in (`agy models` answers)",
                    command,
                    models=parse_antigravity_models(outcome.stdout),
                )
            return ProviderState(
                provider,
                Status.NOT_SIGNED_IN,
                f"{version}; `agy models` gave no model list",
                command,
                fix="run `agy` once and sign in",
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
            pulled = tuple(Offer(id=name) for name in models)
            if ollama_model and ollama_model not in models:
                return ProviderState(
                    provider,
                    Status.MODEL_MISSING,
                    f"reachable at {ollama_host}; model {ollama_model} is not pulled",
                    fix=f"ollama pull {ollama_model}",
                    models=pulled,
                )
            return ProviderState(
                provider, Status.READY, f"reachable at {ollama_host}; {len(models)} models pulled", models=pulled
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
