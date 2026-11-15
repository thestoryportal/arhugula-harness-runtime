"""Configuration verbs: providers, routing, features, policy, MCP, and raw config keys.

Every verb here changes the answers file and lets `deploy.apply` regenerate. The runtime's
own loader accepts the result, or the verb fails and nothing changes.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from arhugula_kit import deploy, modelwrap, overlay, providers, render, runtime, spec as answers_file
from arhugula_kit.common import say, table
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home
from arhugula_kit.providers import Listing, Offer, Provider
from arhugula_kit.spec import WORKLOADS, CustomProvider, Spec
from arhugula_kit.verbs import Arg, Verb

ON_OFF = ("on", "off")
SCOPE_ARG = Arg(
    ("--project",),
    "apply to this project's config only (default: every config of the deployment)",
    {"metavar": "NAME", "default": ""},
)


def scope_of(deployment: Deployment, project: str) -> str:
    """A `--project` scope value as an overlay scope; `""` is the whole deployment."""
    if project in ("", "default"):
        return ""
    deployment.target(project)
    return project


def rendered(deployment: Deployment, project: str | None = None) -> dict[str, Any]:
    """The runtime table of the config as it is generated now."""
    target = deployment.target(project)
    document = render.render_config(deployment.spec, deployment.home, target, deployment.fragments)
    return document["runtime"]


def _state(spec: Spec, provider: Provider) -> providers.ProviderState:
    """What the provider's own tool reports now, its model list included."""
    default = spec.model_of(provider.name) if provider.name == "ollama" and provider.name in spec.models else ""
    return providers.check(provider, ollama_host=spec.ollama_host, ollama_model=default)


def offers(spec: Spec, provider: Provider) -> tuple[Offer, ...]:
    """The models the provider's own tool lists now; empty for a tool that lists none."""
    return _state(spec, provider).models if provider.listing is not Listing.NONE else ()


def _resolved(provider: Provider, text: str, offered: Sequence[Offer]) -> providers.Chosen:
    """A model as `resolve` reads it, or the kit's refusal with the command that lists the models."""
    try:
        return providers.resolve(provider, text, offered)
    except providers.ModelRefused as refused:
        raise KitError(Exit.PRECONDITION, str(refused), fix=f"arhugula provider models {provider.name}") from None


def _enabled(spec: Spec, name: str) -> Provider:
    provider = spec.provider(name)
    if name not in spec.providers:
        raise KitError(
            Exit.PRECONDITION,
            f"{name!r} is not an enabled provider (enabled: {', '.join(spec.providers)})",
            fix=f"arhugula provider enable {name} --model <model>",
        )
    return provider


def _available_model(spec: Spec, provider: Provider, text: str) -> str:
    """A model routing may use: one this deployment made available, with any level it has."""
    offered = offers(spec, provider)
    chosen = _resolved(provider, text, offered)
    available = spec.available(provider.name)
    if providers.model_id(provider, chosen.ref, offered) not in providers.available_ids(provider, available, offered):
        raise KitError(
            Exit.PRECONDITION,
            f"`{chosen.ref}` is not one of the models available for {provider.name} "
            f"({', '.join(available)})",
            fix=providers.enable_command(provider.name, [*available, chosen.ref]),
        )
    return chosen.ref


def _binding(text: str, spec: Spec) -> dict[str, str]:
    """`provider:model` (or just `provider`) as a model binding of an enabled provider."""
    name, _, model = text.partition(":")
    provider = _enabled(spec, name)
    return {"provider": name, "model": _available_model(spec, provider, model) if model else spec.model_of(name)}


def _with_default(spec: Spec, provider: str, model: str) -> dict[str, tuple[str, ...]]:
    """The deployment's models with `model` first for `provider`, so it becomes the default."""
    rest = tuple(m for m in spec.available(provider) if m != model)
    return {**spec.models, provider: (model, *rest)}


# Where the routing verbs store a model binding in an overlay: the table, the binding's key
# inside an entry, what an entry is called, and the verb that removes one deployment-wide.
BINDING_TABLES: tuple[tuple[str, str, str, str], ...] = (
    ("per_role_bindings", "preferred_model_binding", "role", "arhugula routing role unbind {key}"),
    ("per_workload_overrides", "model_binding_override", "workload", "arhugula routing workload clear {key}"),
)


def _bindings(spec: Spec) -> list[tuple[str, Mapping[str, Any], str]]:
    """Every model binding the stored overlays hold: where it is, the binding, the command that removes it."""
    found = []
    for scope, tree in {"": spec.overlay, **spec.project_overlays}.items():
        for table, field, called, unbind in BINDING_TABLES:
            entries = overlay.get(tree, ("runtime", "routing_manifest", table), {})
            for key, entry in entries.items() if isinstance(entries, Mapping) else ():
                binding = entry.get(field) if isinstance(entry, Mapping) else None
                if isinstance(binding, Mapping):
                    where = f"{called} {key}" + (f" (project {scope})" if scope else "")
                    fix = (
                        f"arhugula config unset routing_manifest.{table}.{key} --project {scope}"
                        if scope else unbind.format(key=key)
                    )
                    found.append((where, binding, fix))
    return found


def _refuse_dangling(spec: Spec, provider: Provider, kept: Sequence[str], offered: Sequence[Offer] = ()) -> None:
    """Refuse a change that leaves a stored binding naming `provider` with a model outside `kept`.

    `kept` empty means the provider itself goes. The runtime loads a config whose binding
    names a provider or model the deployment no longer has, so this is the one check.
    """
    keep = providers.available_ids(provider, kept, offered)
    dangling = [
        (where, binding, fix)
        for where, binding, fix in _bindings(spec)
        if binding.get("provider") == provider.name
        and providers.model_id(provider, str(binding.get("model", "")), offered) not in keep
    ]
    if dangling:
        what = f"models of {provider.name} that this leaves out" if kept else provider.name
        raise KitError(
            Exit.PRECONDITION,
            f"routing still binds to {what}: "
            + ", ".join(f"{where} -> {binding.get('provider')}/{binding.get('model')}" for where, binding, _ in dangling),
            fix="; ".join(dict.fromkeys(fix for _, _, fix in dangling)) + " first",
        )


# --- provider ---------------------------------------------------------------------------


def _states(deployment: Deployment) -> list[providers.ProviderState]:
    spec = deployment.spec
    return [_state(spec, provider) for provider in spec.known_providers()]


def _role(spec: Spec, name: str) -> str:
    if name == spec.primary:
        return "default"
    if name == spec.fallback:
        return "fallback"
    return "enabled" if name in spec.providers else "-"


def _shown_models(spec: Spec, name: str) -> str:
    available = spec.available(name)
    return ", ".join(available) if available else "-"


def _provider_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    table(
        [
            (
                state.provider.name,
                _role(spec, state.provider.name),
                _shown_models(spec, state.provider.name) if state.provider.name in spec.providers else "-",
                state.provider.access.value,
                state.status.value,
            )
            for state in _states(deployment)
        ],
        header=("provider", "role", "models (first = default)", "access", "state"),
    )
    say("\nmodels and thinking levels in detail: arhugula provider models")
    return Exit.OK


def _model_report(spec: Spec, state: providers.ProviderState) -> tuple[list[str], int]:
    """The lines about a provider's available models, and how many its tool no longer offers."""
    provider, available = state.provider, spec.available(state.provider.name)
    stale = providers.refusals(provider, available, state.models)
    lines = [f"    models: {', '.join(available)} (default {available[0]})"] if available else []
    lines += [f"    not offered: {reason}" for _, reason in stale]
    if stale:
        lines.append(f"    fix: {providers.repair_command(provider, available, state.models)}")
    elif provider.listing is Listing.NONE or not state.models:
        lines.append(f"    note: {provider.title} gave no model list here, so these names could not be checked")
    return lines, len(stale)


def _provider_check(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    problems = stale = 0
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
        if name in spec.providers:
            lines, count = _model_report(spec, state)
            for line in lines:
                say(line)
            stale += count
        if state.provider.caveat:
            say(f"    note: {state.provider.caveat}")
        if name in (spec.primary, spec.fallback) and not state.usable:
            problems += 1
    if problems or stale:
        parts = [f"{problems} provider(s) that the routing depends on are not usable"] if problems else []
        parts += [f"{stale} model(s) named here are not offered by the provider's own tool"] if stale else []
        raise KitError(
            Exit.PRECONDITION,
            "; ".join(parts),
            fix="follow the `fix:` lines above, or `arhugula routing chain set <provider>`",
        )
    return Exit.OK


def _levels_of(provider: Provider, offer: Offer | None) -> str:
    if not provider.level_args:
        return "-"
    levels = providers.levels_of(provider, offer)
    default = offer.default_level if offer is not None else ""
    return " ".join(f"{level}*" if level == default else level for level in levels) or (
        "none" if offer is not None else "any"
    )


def _here(available: Sequence[str], ref: str) -> str:
    """Whether a listed model is available in this deployment, and with which level."""
    if not ref:
        return "-"
    _, at, level = ref.rpartition("@")
    return ("default" if ref == available[0] else "available") + (f" @{level}" if at else "")


def _provider_models(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    chosen = [spec.provider(args.name)] if args.name else [spec.provider(n) for n in spec.providers]
    for provider in chosen:
        state = _state(spec, provider)
        available = spec.available(provider.name)
        names = {providers.model_id(provider, ref, state.models): ref for ref in reversed(available)}
        enabled = provider.name in spec.providers
        say(f"{provider.name} ({provider.title}){'' if enabled else ': not enabled'}")
        if state.models:
            source = {Listing.SIGN_IN: "this sign-in offers", Listing.PULLED: "pulled here"}[provider.listing]
            say(f"  {source} (from `{provider.list_command}`):")
            # A column the tool gives nothing for (Ollama has neither levels nor titles) is left out.
            columns = [("    model", lambda offer, ref: f"    {offer.id}"),
                       ("here", lambda offer, ref: _here(available, ref))]
            if provider.level_args:
                columns.append(("levels (* = its default)", lambda offer, ref: _levels_of(provider, offer)))
            if any(offer.title for offer in state.models):
                columns.append(("shown as", lambda offer, ref: offer.title or "-"))
            table(
                [tuple(cell(offer, names.get(offer.id, "")) for _, cell in columns) for offer in state.models],
                header=tuple(title for title, _ in columns),
            )
            listed = {offer.id for offer in state.models}
            missing = [ref for ref in available if providers.model_id(provider, ref, state.models) not in listed]
            for ref in missing:
                say(f"  {ref}: available here, but not in that list")
            if missing:
                fix = (
                    "; ".join(f"ollama pull {ref}" for ref in missing)
                    if provider.listing is Listing.PULLED
                    else providers.repair_command(provider, available, state.models)
                )
                say(f"  fix: {fix}")
        else:
            why = (
                f"`{provider.list_command}` gave no list ({state.status.value}: {state.detail})"
                if provider.list_command
                else "its tool lists no models"
            )
            examples = f"; for example {', '.join(provider.examples)}" if provider.examples else ""
            say(f"  {why}, so any model name is accepted unchecked{examples}")
            say(f"  available here: {', '.join(available) or '-'}" + (f" (default {available[0]})" if available else ""))
            if provider.level_args:
                say(f"  thinking levels, written <model>@<level>: {_levels_of(provider, None)}")
        if not provider.level_args:
            say(f"  thinking level: {provider.level_elsewhere}")
        say("")
    say("make models available (the first is the default): arhugula provider enable <provider> --model <model> [--model ...]")
    return Exit.OK


def _executable(text: str) -> str:
    path = Path(text).expanduser()
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise KitError(
            Exit.PRECONDITION,
            f"{text} is not the absolute path of an executable file",
            fix="give the full path, for example the output of `command -v <tool>`",
        )
    # The runtime already runs the kit's wrapper; as the real command it would exec itself.
    if modelwrap.is_generated(path):
        raise KitError(
            Exit.PRECONDITION,
            f"{text} is the kit's own wrapper for a provider, not the provider's CLI",
            fix="give the CLI's own path, for example the output of `command -v <tool>`",
        )
    return str(path)


def _provider_enable(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    provider = spec.provider(args.name)
    if provider.caveat:
        say(f"note: {provider.caveat}")
    state = _state(spec, provider)
    requested = args.model or list(spec.available(args.name)) or [providers.first_choice(provider, state.models)]
    if not all(requested):
        raise KitError(
            Exit.PRECONDITION,
            f"{provider.title} has no model to propose: {state.detail}",
            fix=f"arhugula provider enable {args.name} --model <model>  (the models: arhugula provider models {args.name})",
        )
    chosen = [_resolved(provider, model, state.models) for model in requested]
    for note in dict.fromkeys(c.note for c in chosen if c.note):
        say(f"note: {note}")
    models = {**spec.models, args.name: tuple(dict.fromkeys(c.ref for c in chosen))}
    _refuse_dangling(spec, provider, models[args.name], state.models)
    commands, custom = dict(spec.commands), dict(spec.custom_providers)
    if args.command and provider.is_custom:
        custom[args.name] = replace(custom[args.name], command=_executable(args.command))
    elif args.command:
        commands[args.name] = _executable(args.command)
    selected = tuple(dict.fromkeys((*spec.providers, args.name)))
    deploy.apply(
        deployment,
        replace(spec, providers=selected, models=models, commands=commands, custom_providers=custom),
    )
    say(f"enabled {args.name}; models: {', '.join(models[args.name])} (default {models[args.name][0]}).")
    say("check it:   arhugula provider check")
    say(f"try it:     arhugula run minimal.toml --provider {args.name}")
    return Exit.OK


def _disable_retired(name: str) -> int:
    """Remove a provider the kit no longer knows from an answers file that still names it.

    The deployment does not load while its answers name such a provider, so this works on
    the stored document itself and then regenerates as any verb does.
    """
    home = Home.of_kit()
    raw = answers_file.migrate(answers_file.read_raw(home.spec_file))
    if name not in raw.get("providers", ()):
        say(f"{name} is not enabled.")
        return Exit.OK
    if raw.get("primary") == name:
        raise KitError(
            Exit.PRECONDITION,
            f"{name} is the default provider, and it is no longer a provider: {providers.RETIRED[name]}",
            fix=f"{home.kit / 'init'} --reconfigure  (it asks for another default provider)",
        )
    fragments = render.fragments()
    changed = answers_file.parse(answers_file.without_provider(raw, name), known_features=tuple(fragments))
    deploy.apply(Deployment(home, changed, fragments), changed)
    say(f"removed {name} from this deployment ({providers.RETIRED[name]}).")
    return Exit.OK


def _provider_disable(args: argparse.Namespace) -> int:
    if args.name in providers.RETIRED:
        return _disable_retired(args.name)
    deployment = deploy.open_deployment()
    spec = deployment.spec
    spec.provider(args.name)
    if args.name in (spec.primary, spec.fallback):
        raise KitError(
            Exit.PRECONDITION,
            f"{args.name} is the {_role(spec, args.name)} provider",
            fix="arhugula routing chain set <another-provider> first",
        )
    if args.name not in spec.providers:
        say(f"{args.name} is not enabled.")
        return Exit.OK
    _refuse_dangling(spec, spec.provider(args.name), ())
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


def _provider_add(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    name = args.name
    if name in spec.custom_providers:
        raise KitError(
            Exit.PRECONDITION,
            f"a provider named {name!r} was already added",
            fix=f"arhugula provider remove {name}, then add it again",
        )
    if any(p.name == name for p in providers.CATALOGUE) or name in providers.RETIRED:
        raise KitError(
            Exit.USAGE,
            f"{name!r} is the name of a {'retired' if name in providers.RETIRED else 'built-in'} provider; "
            "choose another name",
            fix=(f"arhugula provider enable {name}" if name not in providers.RETIRED
                 else "arhugula provider add <another-name> --command ... --args ... --model ..."),
        )
    try:
        argv, auth = shlex.split(args.args), shlex.split(args.auth_args or "")
    except ValueError as exc:
        raise KitError(
            Exit.USAGE,
            f"--args or --auth-args is not a valid command line: {exc}",
            fix='close every quote inside the string, for example --args="--model {model} --name \'two words\'"',
        ) from None
    entry = CustomProvider(
        command=_executable(args.command),
        args=tuple(argv),
        family=args.family,
        prompt_transport=args.prompt_transport,
        response_format=args.response_format,
        auth_args=tuple(auth),
    )
    shaped = providers.custom(
        name, command=entry.command, args=entry.args, family=entry.family,
        prompt_transport=entry.prompt_transport, response_format=entry.response_format,
        auth_args=entry.auth_args,
    )
    models = tuple(dict.fromkeys(_resolved(shaped, model, ()).ref for model in args.model))
    if not any("{model}" in word for word in argv):
        say("note: --args has no {model}, so the command is not told which model a step asks for")
    changed = replace(
        spec,
        custom_providers={**spec.custom_providers, name: entry},
        providers=tuple(dict.fromkeys((*spec.providers, name))),
        models={**spec.models, name: models},
    )
    deploy.apply(deployment, changed)
    say(f"added and enabled {name}; models: {', '.join(models)} (default {models[0]}).")
    say("check it:   arhugula provider check")
    say(f"try it:     arhugula run minimal.toml --provider {name}")
    return Exit.OK


def _provider_remove(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    spec = deployment.spec
    name = args.name
    if name not in spec.custom_providers:
        raise KitError(
            Exit.PRECONDITION,
            f"{name!r} is not a provider added with `provider add` (added: {', '.join(spec.custom_providers) or 'none'})",
            fix=f"arhugula provider disable {name}" if name in spec.providers else "arhugula provider list",
        )
    if name in (spec.primary, spec.fallback):
        raise KitError(
            Exit.PRECONDITION,
            f"{name} is the {_role(spec, name)} provider",
            fix="arhugula routing chain set <another-provider> first",
        )
    _refuse_dangling(spec, spec.provider(name), ())

    def without(mapping: Any) -> dict[str, Any]:
        return {key: value for key, value in mapping.items() if key != name}

    changed = replace(
        spec,
        providers=tuple(n for n in spec.providers if n != name),
        custom_providers=without(spec.custom_providers),
        models=without(spec.models),
        provider_settings=without(spec.provider_settings),
    )
    deploy.apply(deployment, changed)
    say(f"removed {name}.")
    return Exit.OK


# Only the settings the runtime reads for the provider kinds this kit configures.
PROVIDER_SETTINGS = {
    "timeout_seconds": "how long one call may take, in seconds",
    "auth_check": "whether the runtime checks the sign-in when it starts (true or false)",
}


def _cli_provider(deployment: Deployment, name: str) -> providers.Provider:
    provider = deployment.spec.provider(name)
    if provider.access is not providers.Access.CLI or name not in deployment.spec.providers:
        cli = ", ".join(p.name for p in deployment.spec.known_providers() if p.access is providers.Access.CLI)
        raise KitError(
            Exit.PRECONDITION,
            f"{name} is not an enabled command-line provider; these settings belong to "
            f"the CLI providers ({cli})",
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
    say(f"{args.name}: {args.key} is back to the value the kit generates")
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
    models = _with_default(spec, primary["provider"], primary["model"])
    if fallback:
        models = _with_default(replace(spec, models=models), fallback["provider"], fallback["model"])
    kept = spec.fallback if args.fallback is None and spec.fallback != primary["provider"] else ""
    changed = replace(
        spec,
        primary=primary["provider"],
        fallback=fallback["provider"] if fallback else kept,
        models=models,
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
    changed = replace(spec, models=_with_default(spec, binding["provider"], binding["model"]))
    deploy.apply(deployment, changed)
    say(f"{binding['provider']} now runs {binding['model']} by default "
        f"(available: {', '.join(changed.available(binding['provider']))}).")
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


CONFIG_SHOW_PROJECT = Arg(
    ("--project",),
    "the project whose config to print (default: the current project). With --overlay: the "
    "project whose stored settings to print (default: the deployment-wide ones)",
    {"metavar": "NAME", "default": ""},
)


def _ollama_host(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    if providers.ollama_models(args.url) is None:
        raise KitError(Exit.PRECONDITION, f"no Ollama server answers at {args.url}",
                       fix="start it, or check the address: curl <url>/api/tags")
    deploy.apply(deployment, replace(deployment.spec, ollama_host=args.url))
    say(f"Ollama address: {args.url}")
    return Exit.OK


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
    if args.state == "off":
        say("note: answer a gate within the step deadline (30 seconds unless set). After that the "
            "run fails with RT-FAIL-STEP-DISPATCH-TIMEOUT. For more time: arhugula config set "
            "step_dispatch_timeout_seconds <seconds>, and drain_timeout_seconds for the whole run.")
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
        # The runtime stamps each tool from `default_blast_radius`; its gates and its tier
        # computation never read `blast_radius`. Both carry the one declared value.
        "default_blast_radius": args.blast_radius,
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
    if args.blast_radius != "READ_ONLY":
        say("note: the runtime runs a client that can change things at a sandbox tier above 1. "
            "This deployment provides tier 3 only, and only for stdio clients. While a client "
            "needs a tier it does not have, the runtime refuses every run at its start "
            f"(SandboxDriverUnavailableError). To undo: arhugula mcp remove {args.name}")
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


BUILT_IN = ", ".join(p.name for p in providers.CATALOGUE)
SDK_NAMES = tuple(p.name for p in providers.CATALOGUE if p.access is providers.Access.SDK)
PROVIDER_ARG = Arg(("name",), f"the provider: a built-in one ({BUILT_IN}) or one added with `provider add`")

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
        ("provider", "models"),
        "Show the models each enabled provider offers, which are available here, the default and the thinking levels.",
        "kit",
        _provider_models,
        (Arg(("name",), "only this provider (it need not be enabled)", {"nargs": "?", "default": ""}),),
        example="arhugula provider models codex",
        detail=(
            "Where the provider's own tool lists its models (Codex: `codex debug models`; "
            "Antigravity: `agy models`; Ollama: the pulled models), that list is shown. Claude "
            "Code and the hosted APIs list none, so any name is accepted unchecked. A thinking "
            "level is written `<model>@<level>` for Claude Code and Codex."
        ),
    ),
    Verb(
        ("provider", "enable"),
        "Make a provider and its models available to routing and to `--provider`.",
        "runtime",
        _provider_enable,
        (
            PROVIDER_ARG,
            Arg(
                ("--model",),
                "a model to make available, as `<model>` or `<model>@<level>`; repeat it for more. "
                "The first is the provider's default. These replace the provider's models (default: "
                "the ones it already has, else the first its own tool lists)",
                {"action": "append", "metavar": "MODEL"},
            ),
            Arg(("--command",), "the absolute path of its executable (default: found on PATH)"),
        ),
        example="arhugula provider enable codex --model gpt-6.1-sol@medium --model gpt-6-astra",
        detail=(
            "A model the provider's own tool does not list for your sign-in is refused, and the "
            "message shows the list. To add a model later, name every model you want kept."
        ),
    ),
    Verb(
        ("provider", "disable"),
        "Remove a provider from the configs.",
        "runtime",
        _provider_disable,
        (PROVIDER_ARG,),
        example="arhugula provider disable codex",
        detail=(
            "The default and the fallback provider cannot be disabled; change the chain first. "
            "Its models are kept for when it is enabled again."
        ),
    ),
    Verb(
        ("provider", "add"),
        "Add your own provider: any command that reads a prompt and prints a reply.",
        "kit",
        _provider_add,
        (
            Arg(("name",), "a new name: a lowercase letter, then lowercase letters, digits or `_`"),
            Arg(("--command",), "the absolute path of the executable", {"required": True}),
            Arg(
                ("--args",),
                "the arguments after the command, as one quoted string; `{model}` becomes the "
                "step's model and `{prompt}` the prompt (with --prompt-transport arg); write "
                "`--args=...` when the string starts with `-`",
                {"required": True},
            ),
            Arg(("--model",), "a model name to pass as `{model}`; repeat it for more; the first is the default",
                {"action": "append", "required": True, "metavar": "MODEL"}),
            Arg(("--family",), "the model family, for fallback-chain placement (default: local_open_weight)",
                {"choices": providers.FAMILIES, "default": "local_open_weight"}),
            Arg(("--prompt-transport",), "how the prompt reaches the command (default: stdin)",
                {"choices": providers.PROMPT_TRANSPORTS, "default": "stdin"}),
            Arg(("--response-format",), "how the command prints its reply (default: text)",
                {"choices": providers.RESPONSE_FORMATS, "default": "text"}),
            Arg(("--auth-args",), "arguments of a sign-in check the runtime runs at start, as one "
                "quoted string; it must exit 0 (default: no check); write `--auth-args=...` when "
                "the string starts with `-`"),
        ),
        example=(
            "arhugula provider add local_echo --command <home>/kit/examples/providers/echo-provider "
            '--args="--model {model}" --auth-args=--version --model echo-1'
        ),
        detail=(
            "The runtime runs it as its `generic-command` kind: the command, then the arguments, "
            "with the prompt on standard input unless --prompt-transport is `arg`. `json` reads a "
            "Claude-style result object; `jsonl` reads Codex-style events. The provider is enabled "
            "at once and then behaves like a built-in one in `provider`, `routing` and `--provider`."
        ),
    ),
    Verb(
        ("provider", "remove"),
        "Remove a provider added with `provider add`.",
        "kit",
        _provider_remove,
        (Arg(("name",), "a provider added with `provider add`"),),
        example="arhugula provider remove local_echo",
        detail="The default and the fallback provider cannot be removed; change the chain first.",
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
        detail=" ".join(f"`{key}` is {meaning}." for key, meaning in PROVIDER_SETTINGS.items()),
    ),
    Verb(
        ("provider", "unset"),
        "Return one setting of a command-line provider to the value the kit generates.",
        "runtime",
        _provider_unset,
        (
            Arg(("name",), "an enabled CLI provider"),
            Arg(("key",), "the setting", {"choices": tuple(PROVIDER_SETTINGS)}),
        ),
        example="arhugula provider unset claude_code timeout_seconds",
    ),
    Verb(
        ("provider", "ollama-host"),
        "Set the address of the Ollama server.",
        "runtime",
        _ollama_host,
        (Arg(("url",), "the server address, for example http://127.0.0.1:11434"),),
        example="arhugula provider ollama-host http://127.0.0.1:11434",
        detail="The server must answer at the address, or nothing changes.",
    ),
    Verb(
        ("provider", "key", "set"),
        "Store a hosted API provider's key in the macOS keychain.",
        "runtime",
        _provider_key_set,
        (Arg(("name",), "the hosted API provider", {"choices": SDK_NAMES}),),
        example="arhugula provider key set anthropic",
        detail="You type the key at a hidden prompt. It is never an argument and never in a file.",
    ),
    Verb(
        ("provider", "key", "delete"),
        "Remove a hosted API provider's key from the macOS keychain.",
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
            Arg(("model",), "one of its available models, as <model> or <model>@<level> "
                            "(`arhugula provider models` lists them)"),
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
            CONFIG_SHOW_PROJECT,
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
