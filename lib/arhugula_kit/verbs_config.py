"""Configuration verbs: providers, routing, features, policy, MCP, and raw config keys.

Every verb here changes the answers file and lets `deploy.apply` regenerate. The runtime's
own loader accepts the result, or the verb fails and nothing changes.
"""

from __future__ import annotations

import argparse
import getpass
import json
import tomllib
from dataclasses import replace
from typing import Any

from arhugula_kit import deploy, overlay, providers, render, runtime
from arhugula_kit.common import say, table
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.spec import WORKLOADS, Spec
from arhugula_kit.verbs import Arg, Verb

ON_OFF = ("on", "off")
SCOPE_ARG = Arg(
    ("--project",),
    "apply to this project's config only (default: every config of the deployment)",
    {"metavar": "NAME", "default": ""},
)


def scope_of(deployment: Deployment, project: str) -> str:
    """A `--project` scope value as an overlay scope; `""` is the whole deployment."""
    if project:
        deployment.target(project)
    return project


def rendered(deployment: Deployment, project: str | None = None) -> dict[str, Any]:
    """The runtime table of the config as it is generated now."""
    target = deployment.target(project)
    document = render.render_config(deployment.spec, deployment.home, target, deployment.fragments)
    return document["runtime"]


def _binding(text: str, spec: Spec) -> dict[str, str]:
    """`provider:model` (or just `provider`) as a model binding of a selected provider."""
    name, _, model = text.partition(":")
    if name not in spec.providers:
        raise KitError(
            Exit.PRECONDITION,
            f"{name!r} is not an enabled provider (enabled: {', '.join(spec.providers)})",
            fix=f"arhugula provider enable {name}",
        )
    return {"provider": name, "model": model or spec.model_of(name)}


# --- provider ---------------------------------------------------------------------------


def _states(deployment: Deployment) -> list[providers.ProviderState]:
    return [
        providers.check(
            provider,
            ollama_host=deployment.spec.ollama_host,
            ollama_model=deployment.spec.ollama_model if provider.name == "ollama" else "",
        )
        for provider in providers.CATALOGUE
    ]


def _role(spec: Spec, name: str) -> str:
    if name == spec.primary:
        return "default"
    if name == spec.fallback:
        return "fallback"
    return "enabled" if name in spec.providers else "-"


def _provider_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    table(
        [
            (
                state.provider.name,
                _role(spec, state.provider.name),
                spec.model_of(state.provider.name) if state.provider.name in spec.providers else "-",
                state.provider.access.value,
                state.status.value,
            )
            for state in _states(deployment)
        ],
        header=("provider", "role", "model", "access", "state"),
    )
    return Exit.OK


def _provider_check(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    problems = 0
    for state in _states(deployment):
        name = state.provider.name
        if name not in spec.providers and not args.all:
            continue
        say(f"{name} ({_role(spec, name)}): {state.status.value}")
        say(f"    {state.detail}")
        if state.command:
            say(f"    command: {state.command}")
        if state.fix:
            say(f"    fix: {state.fix}")
        if state.provider.caveat:
            say(f"    note: {state.provider.caveat}")
        if name in (spec.primary, spec.fallback) and not state.usable:
            problems += 1
    if problems:
        raise KitError(
            Exit.PRECONDITION,
            f"{problems} provider(s) that the routing depends on are not usable",
            fix="follow the `fix:` lines above, or `arhugula routing chain set <provider>`",
        )
    return Exit.OK


def _provider_enable(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    provider = providers.by_name(args.name)
    if provider.caveat:
        say(f"note: {provider.caveat}")
    models = {**spec.models, **({args.name: args.model} if args.model else {})}
    commands = {**spec.commands, **({args.name: args.command} if args.command else {})}
    selected = tuple(dict.fromkeys((*spec.providers, args.name)))
    deploy.apply(deployment, replace(spec, providers=selected, models=models, commands=commands))
    say(f"enabled {args.name} (model {models.get(args.name, provider.default_model)}).")
    say("check it:   arhugula provider check")
    say(f"try it:     arhugula run minimal.toml --provider {args.name}")
    return Exit.OK


def _provider_disable(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    if args.name in (spec.primary, spec.fallback):
        raise KitError(
            Exit.PRECONDITION,
            f"{args.name} is the {_role(spec, args.name)} provider",
            fix="arhugula routing chain set <another-provider> first",
        )
    if args.name not in spec.providers:
        say(f"{args.name} is not enabled.")
        return Exit.OK
    selected = tuple(n for n in spec.providers if n != args.name)
    deploy.apply(deployment, replace(spec, providers=selected))
    say(f"disabled {args.name}.")
    return Exit.OK


def _provider_key_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    provider = providers.by_name(args.name)
    secret = getpass.getpass(f"API key for {provider.title} (input is hidden): ").strip()
    if not secret:
        raise KitError(Exit.USAGE, "no key was entered; nothing was stored")
    runtime.call(
        deployment.home,
        "keyring-set",
        service=providers.KEYRING_SERVICE,
        name=provider.secret_name,
        secret=secret,
    )
    say(f"stored `{provider.secret_name}` in the keyring service `{providers.KEYRING_SERVICE}`.")
    say("The key is not written to any file of this deployment.")
    return Exit.OK


def _provider_key_delete(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    provider = providers.by_name(args.name)
    runtime.call(
        deployment.home,
        "keyring-delete",
        service=providers.KEYRING_SERVICE,
        name=provider.secret_name,
    )
    say(f"removed `{provider.secret_name}` from the keyring.")
    return Exit.OK


PROVIDER_SETTINGS = {
    "timeout_seconds": "how long one call may take, in seconds (a number)",
    "args": "extra arguments for every call, as a JSON list of strings",
    "auth_args": "the arguments of the sign-in check, as a JSON list of strings",
    "auth_check": "whether the runtime checks sign-in at start (true or false)",
    "response_format": "how the CLI answers: text, json or jsonl",
    "prompt_transport": "how the prompt is passed: stdin or arg",
}


def _cli_provider(deployment: Deployment, name: str) -> providers.Provider:
    provider = providers.by_name(name)
    if provider.access is not providers.Access.CLI or name not in deployment.spec.providers:
        raise KitError(
            Exit.PRECONDITION,
            f"{name} is not an enabled command-line provider; these settings belong to "
            "the CLI providers (claude_code, codex, gemini, antigravity)",
            fix=f"arhugula provider enable {name}",
        )
    return provider


def _provider_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    _cli_provider(deployment, args.name)
    try:
        value = json.loads(args.value)
    except ValueError:
        value = args.value
    settings = {**deployment.spec.provider_settings}
    settings[args.name] = {**settings.get(args.name, {}), args.key: value}
    deploy.apply(deployment, replace(deployment.spec, provider_settings=settings))
    say(f"{args.name}: {args.key} = {json.dumps(value)}")
    return Exit.OK


def _provider_unset(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    _cli_provider(deployment, args.name)
    settings = {**deployment.spec.provider_settings}
    kept = {k: v for k, v in settings.get(args.name, {}).items() if k != args.key}
    settings = {**{n: s for n, s in settings.items() if n != args.name}, **({args.name: kept} if kept else {})}
    deploy.apply(deployment, replace(deployment.spec, provider_settings=settings))
    say(f"{args.name}: {args.key} is back to the runtime's default")
    return Exit.OK


# --- routing ----------------------------------------------------------------------------


def _shown(candidate: dict[str, str]) -> str:
    return f"{candidate['provider']}/{candidate['model']}"


def _routing_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    manifest = rendered(deployment)["routing_manifest"]
    chain = manifest["fallback_chains"][0]
    say("The first fallback chain serves every step unless a run passes --provider.")
    say(f"  default:        {_shown(chain['primary'])}")
    for label in ("same_family", "cross_family"):
        for candidate in chain[label]:
            say(f"  fallback:       {_shown(candidate)}  ({label.replace('_', ' ')})")
    say("\nper-role bindings:")
    for role, binding in manifest["per_role_bindings"].items():
        say(f"  {role}: {_shown(binding['preferred_model_binding'])}")
    say("per-workload overrides:")
    for workload, entry in manifest["per_workload_overrides"].items():
        parts = [f"{k}={v}" for k, v in entry.items() if k != "model_binding_override"]
        if "model_binding_override" in entry:
            parts.insert(0, _shown(entry["model_binding_override"]))
        say(f"  {workload}: {', '.join(parts)}")
    say("retry policies:")
    for key, policy in manifest["retry_policies"].items():
        say(f"  {key}: {', '.join(f'{k}={v}' for k, v in policy.items())}")
    embedding = "on" if "embedding-routing" in deployment.spec.features else "off"
    say(f"\nembedding routing: {embedding}")
    return Exit.OK


def _chain_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    primary = _binding(args.primary, spec)
    named_fallback = args.fallback is not None and args.fallback != "none"
    fallback = _binding(args.fallback, spec) if named_fallback else None
    if primary["provider"] == "codex":
        say(f"note: {providers.by_name('codex').caveat}")
    if fallback and fallback["provider"] == primary["provider"]:
        raise KitError(Exit.USAGE, "the fallback must be a different provider from the default")
    models = {**spec.models, primary["provider"]: primary["model"]}
    if fallback:
        models[fallback["provider"]] = fallback["model"]
    kept = spec.fallback if args.fallback is None and spec.fallback != primary["provider"] else ""
    changed = replace(
        spec,
        primary=primary["provider"],
        fallback=fallback["provider"] if fallback else kept,
        models=models,
        ollama_model=models.get("ollama", spec.ollama_model),
    )
    deploy.apply(deployment, changed)
    say(f"default provider: {changed.primary}/{changed.model_of(changed.primary)}")
    described = f"{changed.fallback}/{changed.model_of(changed.fallback)}" if changed.fallback else "none"
    say(f"fallback:         {described}")
    return Exit.OK


def _model_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    binding = _binding(f"{args.provider}:{args.model}", spec)
    changed = replace(
        spec,
        models={**spec.models, binding["provider"]: binding["model"]},
        ollama_model=binding["model"] if binding["provider"] == "ollama" else spec.ollama_model,
    )
    deploy.apply(deployment, changed)
    say(f"{binding['provider']} now runs {binding['model']}.")
    return Exit.OK


ROUTING = ("runtime", "routing_manifest")


def _role_bind(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    binding = _binding(args.binding, deployment.spec)
    path = (*ROUTING, "per_role_bindings", args.role)
    entry = {
        "preferred_model_binding": binding,
        "layer_budget_overrides": {},
        "fallback_chain_ref": "default",
    }
    changed = overlay.set_value(deployment.spec, "", path, entry)
    deploy.apply(deployment, changed)
    say(f"role {args.role} -> {_shown(binding)}")
    return Exit.OK


def _role_unbind(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    path = (*ROUTING, "per_role_bindings", args.role)
    deploy.apply(deployment, overlay.dropped(deployment.spec, "", path))
    say(f"role {args.role}: no binding")
    return Exit.OK


def _workload_override(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    binding = _binding(args.binding, deployment.spec)
    path = (*ROUTING, "per_workload_overrides", args.workload, "model_binding_override")
    deploy.apply(deployment, overlay.set_value(deployment.spec, "", path, binding))
    say(f"workload {args.workload} -> {_shown(binding)}")
    return Exit.OK


def _workload_clear(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    path = (*ROUTING, "per_workload_overrides", args.workload)
    deploy.apply(deployment, overlay.dropped(deployment.spec, "", path))
    say(f"workload {args.workload}: no override")
    return Exit.OK


def _retry_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    policy: dict[str, Any] = {"max_attempts": args.max_attempts, "backoff": args.backoff}
    if args.jitter:
        policy["jitter"] = args.jitter
    path = (*ROUTING, "retry_policies", args.key)
    deploy.apply(deployment, overlay.set_value(deployment.spec, "", path, policy))
    say(f"retry policy {args.key}: {', '.join(f'{k}={v}' for k, v in policy.items())}")
    return Exit.OK


def _retry_clear(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    path = (*ROUTING, "retry_policies", args.key)
    deploy.apply(deployment, overlay.dropped(deployment.spec, "", path))
    say(f"retry policy {args.key}: removed")
    return Exit.OK


# --- feature ----------------------------------------------------------------------------


def fragment_of(deployment: Deployment, name: str) -> render.Fragment:
    try:
        return deployment.fragments[name]
    except KeyError:
        known = ", ".join(sorted(deployment.fragments))
        raise KitError(Exit.USAGE, f"unknown feature {name!r} (known: {known})") from None


def set_feature(deployment: Deployment, name: str, enabled: bool) -> Deployment:
    fragment_of(deployment, name)
    return deploy.apply(deployment, deployment.spec.with_feature(name, enabled))


def _feature_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    table(
        [
            (
                "on" if name in deployment.spec.features else "off",
                name,
                fragment.title,
                fragment.needs or "-",
            )
            for name, fragment in sorted(deployment.fragments.items())
        ],
        header=("state", "feature", "what it is", "needs"),
    )
    say("\ndetails: arhugula feature show <feature>")
    return Exit.OK


def _feature_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    fragment = fragment_of(deployment, args.name)
    say(f"{fragment.name}: {fragment.title}")
    say(f"state:  {'on' if fragment.name in deployment.spec.features else 'off'}")
    say(f"needs:  {fragment.needs or 'nothing'}")
    say(f"\n{fragment.summary}\n")
    say("It merges this into every generated config:\n")
    body = "\n".join(line for line in fragment.body.splitlines() if not line.startswith("#:"))
    say(body.strip())
    return Exit.OK


def _feature_enable(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    fragment = fragment_of(deployment, args.name)
    set_feature(deployment, args.name, True)
    say(f"{args.name}: on")
    if fragment.needs and fragment.needs != "nothing":
        say(f"needs: {fragment.needs}")
    return Exit.OK


def _feature_disable(args: argparse.Namespace) -> int:
    set_feature(deploy.open_deployment(), args.name, False)
    say(f"{args.name}: off")
    return Exit.OK


# --- config (any key) -------------------------------------------------------------------


def _key_path(text: str) -> tuple[str, ...]:
    parts = tuple(part for part in text.split(".") if part)
    if not parts:
        raise KitError(Exit.USAGE, "give a dotted key, for example `step_dispatch_timeout_seconds`")
    return parts if parts[0] == "runtime" else ("runtime", *parts)


def _config_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    if args.overlay:
        stored = overlay.scoped(deployment.spec, scope_of(deployment, args.project))
        say(json.dumps(stored, indent=2, sort_keys=True))
        return Exit.OK
    target = deployment.target(args.project or None)
    say(target.config_file.read_text(encoding="utf-8"))
    return Exit.OK


def _config_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    try:
        value = tomllib.loads(f"value = {args.value}")["value"]
    except tomllib.TOMLDecodeError as exc:
        raise KitError(
            Exit.USAGE,
            f'write the value as TOML, for example 120, true, "text" or ["a"]: {exc}',
        ) from exc
    path = _key_path(args.key)
    deploy.apply(deployment, overlay.set_value(deployment.spec, scope, path, value))
    where = f"project {scope}" if scope else "every config"
    say(f"{'.'.join(path)} = {json.dumps(value)}  ({where})")
    return Exit.OK


def _config_unset(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    path = _key_path(args.key)
    deploy.apply(deployment, overlay.dropped(deployment.spec, scope, path))
    say(f"{'.'.join(path)}: back to its generated or default value")
    return Exit.OK


def _config_keys(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    for name in runtime.call(deployment.home, "config-fields"):
        say(name)
    say("\nEach is a key under [runtime]; docs/configure.md says what each one does.")
    return Exit.OK


# --- policy -----------------------------------------------------------------------------

POLICY_KEYS = {
    "solo-floor-auto": "solo_persona_floor_auto",
    "local-mutation-floor-auto": "solo_local_mutation_floor_auto",
}


def _policy_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    policy = rendered(deployment).get("hitl_auto_approve_policy", {})
    solo = "on" if policy.get("solo_persona_floor_auto", True) else "off"
    mutation = "on" if policy.get("solo_local_mutation_floor_auto", False) else "off"
    say("What an approval gate approves without asking (solo-developer persona):")
    say(f"  solo-floor-auto:            {solo:3}  read-only tool calls at the solo floor")
    say(f"  local-mutation-floor-auto:  {mutation:3}  tool calls that change local files")
    say("\nWith a setting off, the gate asks you in the terminal. A run without a terminal rejects the gate.")
    return Exit.OK


def _policy_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    path = ("runtime", "hitl_auto_approve_policy", POLICY_KEYS[args.setting])
    deploy.apply(deployment, overlay.set_value(deployment.spec, "", path, args.state == "on"))
    say(f"{args.setting}: {args.state}")
    return Exit.OK


# --- mcp --------------------------------------------------------------------------------

TRANSPORTS = (
    "stdio",
    "streamable_http_l0",
    "streamable_http_l1",
    "streamable_http_l2",
    "streamable_http_l3",
)
TRUST_LEVELS = ("L0_REFUSE_REMOTE", "L1_SIGNED_PINNED", "L2_SANDBOX_ALL", "L3_ALLOW_WITH_AUDIT")
BLAST_RADII = ("READ_ONLY", "LOCAL_MUTATION", "EXTERNAL_REVERSIBLE", "EXTERNAL_IRREVERSIBLE")
MCP_CLIENTS = ("runtime", "mcp_clients")


def mcp_clients(spec: Spec) -> list[dict[str, Any]]:
    return list(overlay.get(spec.overlay, MCP_CLIENTS, []))


def _mcp_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    clients = mcp_clients(deployment.spec)
    if not clients:
        say("no MCP client is configured. Add one with: arhugula mcp add <name> --url <url>")
        return Exit.OK
    table(
        [
            (
                c["client_name"],
                c["transport"],
                c["trust_level"],
                c["blast_radius"],
                c["connection_url"],
                "tier-3" if "sandbox_driver" in c else "-",
            )
            for c in clients
        ],
        header=("name", "transport", "trust", "blast radius", "url or command", "sandbox"),
    )
    return Exit.OK


def _mcp_add(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    clients = mcp_clients(deployment.spec)
    if any(c["client_name"] == args.name for c in clients):
        raise KitError(Exit.PRECONDITION, f"an MCP client named {args.name!r} already exists")
    client: dict[str, Any] = {
        "client_name": args.name,
        "transport": args.transport,
        "trust_level": args.trust,
        "blast_radius": args.blast_radius,
        "connection_url": args.url,
    }
    if args.auth_secret_name:
        client["auth_secret_name"] = args.auth_secret_name
    if args.transport == "stdio":
        say(
            "note: the runtime runs every stdio MCP server at isolation tier 3, so this "
            "client needs the sandbox: arhugula isolation enable tier-3"
        )
    changed = overlay.set_value(deployment.spec, "", MCP_CLIENTS, [*clients, client])
    deploy.apply(deployment, changed)
    say(f"added MCP client {args.name} ({args.transport}, {args.trust}, {args.blast_radius}).")
    say(f"check it: arhugula mcp test {args.name}")
    return Exit.OK


def _mcp_remove(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    clients = mcp_clients(deployment.spec)
    kept = [c for c in clients if c["client_name"] != args.name]
    if len(kept) == len(clients):
        raise KitError(Exit.PRECONDITION, f"no MCP client named {args.name!r}")
    deploy.apply(deployment, overlay.set_value(deployment.spec, "", MCP_CLIENTS, kept))
    say(f"removed MCP client {args.name}.")
    return Exit.OK


def _mcp_test(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    found = [c for c in mcp_clients(deployment.spec) if c["client_name"] == args.name]
    if not found:
        raise KitError(Exit.PRECONDITION, f"no MCP client named {args.name!r}", fix="arhugula mcp list")
    client = found[0]
    if client["transport"] == "stdio":
        raise KitError(
            Exit.PRECONDITION,
            "a stdio server only runs inside the tier-3 sandbox; test it with a workflow "
            "that calls one of its tools",
        )
    listing = runtime.call(deployment.home, "mcp-tools", url=client["connection_url"])
    say(f"{args.name} answers at {client['connection_url']} with {len(listing['tools'])} tool(s):")
    for tool in listing["tools"]:
        first = tool["description"].splitlines()[0] if tool["description"] else ""
        say(f"  {tool['name']}: {first}")
    return Exit.OK


PROVIDER_NAMES = tuple(p.name for p in providers.CATALOGUE)
SDK_NAMES = tuple(p.name for p in providers.CATALOGUE if p.access is providers.Access.SDK)

VERBS: tuple[Verb, ...] = (
    Verb(
        ("provider", "list"),
        "List every provider, its role, model and state.",
        "runtime",
        _provider_list,
        example="arhugula provider list",
    ),
    Verb(
        ("provider", "check"),
        "Ask each enabled provider's own tool whether it is installed and signed in.",
        "runtime",
        _provider_check,
        (Arg(("--all",), "also check providers that are not enabled", {"action": "store_true"}),),
        example="arhugula provider check",
        detail=(
            "For Codex it reports the sign-in method and warns when an API key makes it "
            "a paid route."
        ),
    ),
    Verb(
        ("provider", "enable"),
        "Make a provider available to routing and to `--provider`.",
        "runtime",
        _provider_enable,
        (
            Arg(("name",), "the provider", {"choices": PROVIDER_NAMES}),
            Arg(("--model",), "the model this provider runs (default: the provider's usual model)"),
            Arg(("--command",), "the absolute path of its executable (default: found on PATH)"),
        ),
        example="arhugula provider enable codex",
    ),
    Verb(
        ("provider", "disable"),
        "Remove a provider from the configs.",
        "runtime",
        _provider_disable,
        (Arg(("name",), "the provider", {"choices": PROVIDER_NAMES}),),
        example="arhugula provider disable gemini",
        detail="The default and the fallback provider cannot be disabled; change the chain first.",
    ),
    Verb(
        ("provider", "set"),
        "Set one setting of a command-line provider.",
        "runtime",
        _provider_set,
        (
            Arg(("name",), "an enabled CLI provider"),
            Arg(("key",), "the setting", {"choices": tuple(PROVIDER_SETTINGS)}),
            Arg(("value",), "the value; JSON for lists, numbers and true/false"),
        ),
        example="arhugula provider set claude_code timeout_seconds 300",
        detail="Settings: " + "; ".join(f"`{key}`: {meaning}" for key, meaning in PROVIDER_SETTINGS.items()) + ".",
    ),
    Verb(
        ("provider", "unset"),
        "Return one setting of a command-line provider to the runtime's default.",
        "runtime",
        _provider_unset,
        (
            Arg(("name",), "an enabled CLI provider"),
            Arg(("key",), "the setting", {"choices": tuple(PROVIDER_SETTINGS)}),
        ),
        example="arhugula provider unset claude_code timeout_seconds",
    ),
    Verb(
        ("provider", "key", "set"),
        "Store a hosted API provider's key in the OS keyring.",
        "runtime",
        _provider_key_set,
        (Arg(("name",), "the hosted API provider", {"choices": SDK_NAMES}),),
        example="arhugula provider key set anthropic",
        detail="You type the key at a hidden prompt. It is never an argument and never in a file.",
    ),
    Verb(
        ("provider", "key", "delete"),
        "Remove a hosted API provider's key from the OS keyring.",
        "runtime",
        _provider_key_delete,
        (Arg(("name",), "the hosted API provider", {"choices": SDK_NAMES}),),
        example="arhugula provider key delete anthropic",
    ),
    Verb(
        ("routing", "show"),
        "Show the fallback chain, bindings, overrides and retry policies.",
        "runtime",
        _routing_show,
        example="arhugula routing show",
    ),
    Verb(
        ("routing", "chain", "set"),
        "Choose the default provider and, optionally, the fallback.",
        "runtime",
        _chain_set,
        (
            Arg(("primary",), "the default, as `provider` or `provider:model`"),
            Arg(("--fallback",), "the fallback, as `provider`, `provider:model` or `none`"),
        ),
        example="arhugula routing chain set claude_code:sonnet --fallback ollama",
    ),
    Verb(
        ("routing", "model", "set"),
        "Change the model a provider runs.",
        "runtime",
        _model_set,
        (
            Arg(("provider",), "an enabled provider"),
            Arg(("model",), "the model name as the provider knows it"),
        ),
        example="arhugula routing model set ollama llama3.1:8b",
    ),
    Verb(
        ("routing", "role", "bind"),
        "Bind a role to a provider and model, for example a reviewer on another model family.",
        "runtime",
        _role_bind,
        (
            Arg(("role",), "the role name"),
            Arg(("binding",), "`provider` or `provider:model`"),
        ),
        example="arhugula routing role bind reviewer ollama:llama3.1:8b",
    ),
    Verb(
        ("routing", "role", "unbind"),
        "Remove a role's binding.",
        "runtime",
        _role_unbind,
        (Arg(("role",), "the role name"),),
        example="arhugula routing role unbind reviewer",
    ),
    Verb(
        ("routing", "workload", "override"),
        "Route one workload class to a provider and model.",
        "runtime",
        _workload_override,
        (
            Arg(("workload",), "the workload class", {"choices": WORKLOADS}),
            Arg(("binding",), "`provider` or `provider:model`"),
        ),
        example="arhugula routing workload override research ollama",
    ),
    Verb(
        ("routing", "workload", "clear"),
        "Remove a workload class's override.",
        "runtime",
        _workload_clear,
        (Arg(("workload",), "the workload class", {"choices": WORKLOADS}),),
        example="arhugula routing workload clear research",
    ),
    Verb(
        ("routing", "retry", "set"),
        "Set a retry policy under a key.",
        "runtime",
        _retry_set,
        (
            Arg(("key",), "the policy key"),
            Arg(
                ("--max-attempts",),
                "attempts before the fallback chain takes over",
                {"type": int, "required": True},
            ),
            Arg(("--backoff",), "the backoff strategy (default: full-jitter)", {"default": "full-jitter"}),
            Arg(("--jitter",), "the jitter token (default: full)", {"default": "full"}),
        ),
        example="arhugula routing retry set my_tool --max-attempts 3",
    ),
    Verb(
        ("routing", "retry", "clear"),
        "Remove a retry policy.",
        "runtime",
        _retry_clear,
        (Arg(("key",), "the policy key"),),
        example="arhugula routing retry clear my_tool",
    ),
    Verb(
        ("feature", "list"),
        "List every named feature and whether it is on.",
        "kit",
        _feature_list,
        example="arhugula feature list",
    ),
    Verb(
        ("feature", "show"),
        "Show what a feature does and the exact TOML it merges.",
        "kit",
        _feature_show,
        (Arg(("name",), "the feature"),),
        example="arhugula feature show deadlines",
    ),
    Verb(
        ("feature", "enable"),
        "Switch a feature on in every generated config.",
        "kit",
        _feature_enable,
        (Arg(("name",), "the feature"),),
        example="arhugula feature enable data-flow",
    ),
    Verb(
        ("feature", "disable"),
        "Switch a feature off.",
        "kit",
        _feature_disable,
        (Arg(("name",), "the feature"),),
        example="arhugula feature disable data-flow",
    ),
    Verb(
        ("config", "show"),
        "Print a generated config, or the settings your verbs have stored.",
        "kit",
        _config_show,
        (
            SCOPE_ARG,
            Arg(("--overlay",), "print only the stored settings, as JSON", {"action": "store_true"}),
        ),
        example="arhugula config show",
    ),
    Verb(
        ("config", "set"),
        "Set any runtime config key.",
        "kit",
        _config_set,
        (
            Arg(("key",), "the key under [runtime], dotted for nested tables"),
            Arg(("value",), 'the value, written as TOML: 120, true, "text", ["a", "b"]'),
            SCOPE_ARG,
        ),
        example="arhugula config set step_dispatch_timeout_seconds 120",
        detail=(
            "This reaches every knob the runtime has, including those no other verb names. "
            "The runtime's own loader must accept the result, or nothing changes."
        ),
    ),
    Verb(
        ("config", "unset"),
        "Remove a setting you stored with `config set` or another verb.",
        "kit",
        _config_unset,
        (Arg(("key",), "the key under [runtime], dotted for nested tables"), SCOPE_ARG),
        example="arhugula config unset step_dispatch_timeout_seconds",
    ),
    Verb(
        ("config", "keys"),
        "List every runtime config key at the installed pin.",
        "runtime",
        _config_keys,
        example="arhugula config keys",
    ),
    Verb(
        ("policy", "show"),
        "Show what an approval gate approves without asking.",
        "runtime",
        _policy_show,
        example="arhugula policy show",
    ),
    Verb(
        ("policy", "set"),
        "Change what an approval gate approves without asking.",
        "runtime",
        _policy_set,
        (
            Arg(("setting",), "which floor", {"choices": tuple(POLICY_KEYS)}),
            Arg(("state",), "on or off", {"choices": ON_OFF}),
        ),
        example="arhugula policy set solo-floor-auto off",
    ),
    Verb(("mcp", "list"), "List the configured MCP clients.", "runtime", _mcp_list, example="arhugula mcp list"),
    Verb(
        ("mcp", "add"),
        "Connect an MCP tool server.",
        "runtime",
        _mcp_add,
        (
            Arg(("name",), "a name for the client"),
            Arg(("--url",), "the server URL, or for stdio the command to run", {"required": True}),
            Arg(
                ("--transport",),
                "how the runtime reaches it (default: streamable_http_l3)",
                {"choices": TRANSPORTS, "default": "streamable_http_l3"},
            ),
            Arg(
                ("--trust",),
                "the trust level (default: L3_ALLOW_WITH_AUDIT)",
                {"choices": TRUST_LEVELS, "default": "L3_ALLOW_WITH_AUDIT"},
            ),
            Arg(
                ("--blast-radius",),
                "the most its tools can change (default: READ_ONLY)",
                {"choices": BLAST_RADII, "default": "READ_ONLY"},
            ),
            Arg(("--auth-secret-name",), "the keyring entry that holds its credential"),
        ),
        example="arhugula mcp add docs --url http://127.0.0.1:8931/mcp",
    ),
    Verb(
        ("mcp", "remove"),
        "Remove an MCP client.",
        "runtime",
        _mcp_remove,
        (Arg(("name",), "the client"),),
        example="arhugula mcp remove docs",
    ),
    Verb(
        ("mcp", "test"),
        "Connect to an MCP server and list its tools.",
        "runtime",
        _mcp_test,
        (Arg(("name",), "the client"),),
        example="arhugula mcp test docs",
    ),
)
