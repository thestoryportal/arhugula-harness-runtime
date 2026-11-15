"""The init questions: one table, rendered as terminal prompts and as JSON.

[LAW:one-source-of-truth] `QUESTIONS` is the only statement of what init asks. The
interactive prompts, `init --questions-json` (the agent contract), the validation of an
answers file and the walkthrough in docs/install.md are all renderings of it.

[LAW:dataflow-not-control-flow] Every question runs through the same steps: applies?,
default, options, parse. What differs between questions is data in the table.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from arhugula_kit import detect, lima, providers, spec
from arhugula_kit.detect import Machine
from arhugula_kit.providers import Offer, Provider
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, Home

__all__ = ["FEATURE_LETTERS", "QUESTIONS", "Option", "Question", "ask_all", "complete", "describe"]

Answers = Mapping[str, Any]

FEATURE_LETTERS: tuple[tuple[str, str, str], ...] = (
    ("m", "memory", "memory: the harness remembers across runs, with review before promotion"),
    ("p", "durable-pause", "durable pause and resume: a paused run survives the process"),
    ("d", "data-flow", "inter-step data flow: each step receives the previous step's output"),
    ("s", "audit-signing", "audit signing: every audit entry is signed with a local key"),
    ("e", "embedding-routing", "offline embedding routing: route by a local embedding model"),
)


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    note: str = ""


def _no_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return ()


def _no_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    return ()


def _always(machine: Machine, answers: Answers) -> bool:
    return True


@dataclass(frozen=True)
class Question:
    number: int
    id: str
    prompt: str
    kind: str  # path | multi | choice | text | yesno | engine | paths
    why: str
    default_doc: str  # the default in words, for docs/install.md; the value itself is computed
    default: Callable[[Machine, Answers], Any]
    parse: Callable[[str, Machine, Answers], Any]
    options: Callable[[Machine, Answers], tuple[Option, ...]] = _no_options
    applies: Callable[[Machine, Answers], bool] = _always
    applies_when: str = "always"
    notes: Callable[[Machine, Answers], tuple[str, ...]] = _no_notes
    # An answer given as data (an earlier run's answer, or the answers file) in the shape
    # this machine and the earlier answers accept; raises ValueError naming what is wrong.
    adopt: Callable[[Any, Machine, Answers], Any] = lambda value, machine, answers: value
    # An earlier answer as the default to show, with a note for each part of it that no
    # longer holds; None keeps the strict `adopt` (a stale earlier answer is shown and refused).
    keep: Callable[[Any, Machine, Answers], tuple[Any, tuple[str, ...]]] | None = None


# --- shared parsers ---------------------------------------------------------------------


def _absolute(text: str) -> str:
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("give an absolute path (a leading ~ is expanded)")
    return str(path)


def _yes_no(text: str, machine: Machine, answers: Answers) -> bool:
    word = text.strip().lower()
    if word in ("y", "yes"):
        return True
    if word in ("n", "no"):
        return False
    raise ValueError("answer y or n")


def _one_of(allowed: tuple[str, ...], text: str) -> str:
    word = text.strip()
    if word not in allowed:
        raise ValueError(f"choose one of: {', '.join(allowed)}")
    return word


# --- 1 home -----------------------------------------------------------------------------


def _default_home(machine: Machine, answers: Answers) -> str:
    parent = KIT_ROOT.parent
    cloned_into_a_home = KIT_ROOT.name == "kit" and detect.checkout_above(parent) is None
    return str(parent if cloned_into_a_home else Path.home() / "arhugula")


def _parse_home(text: str, machine: Machine, answers: Answers) -> str:
    return _absolute(text)


# --- 2 providers ------------------------------------------------------------------------


def _lettered(machine: Machine) -> tuple[providers.ProviderState, ...]:
    """The providers question 2 offers: the built-in ones. An added one is kept by `provider add`."""
    return tuple(state for state in machine.provider_states if state.provider.letter)


def _added(machine: Machine) -> list[str]:
    """The providers this deployment added with `provider add`: selected without a letter.

    They belong to the selection the later questions (default, fallback, models) choose from.
    """
    return [state.provider.name for state in machine.provider_states if not state.provider.letter]


def _provider_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(
        Option(
            value=state.provider.letter,
            label=state.provider.title,
            note=f"{state.status.value}: {state.detail}",
        )
        for state in _lettered(machine)
    )


def _default_providers(machine: Machine, answers: Answers) -> list[str]:
    return [
        *(
            state.provider.name
            for state in _lettered(machine)
            # Preselect what was checked and works. A CLI whose sign-in cannot be checked
            # (`unverified`) stays one keystroke away, but is not chosen for the operator.
            if state.status in (providers.Status.READY, providers.Status.PAID_ROUTE)
            and state.provider.access is not providers.Access.SDK
        ),
        *_added(machine),
    ]


def _adopt_providers(value: Any, machine: Machine, answers: Answers) -> list[str]:
    known = [state.provider.name for state in machine.provider_states]
    unknown = [name for name in value if name not in known]
    if unknown:
        raise ValueError(
            f"unknown provider(s) {', '.join(unknown)} (known: {', '.join(known)}); a provider "
            "of your own is added after init with `arhugula provider add`"
        )
    return list(value)


def _parse_providers(text: str, machine: Machine, answers: Answers) -> list[str]:
    by_letter = {p.letter: p.name for p in providers.CATALOGUE}
    letters = [c for c in text if not c.isspace() and c != ","]
    unknown = [c for c in letters if c not in by_letter]
    if unknown or not letters:
        raise ValueError(f"use the letters shown, for example `co` (unknown: {''.join(unknown)})")
    return list(dict.fromkeys([*(by_letter[c] for c in letters), *_added(machine)]))


def _provider_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    return tuple(f"{p.title}: {p.caveat}" for p in providers.CATALOGUE if p.caveat)


# --- 3 primary, 4 fallback --------------------------------------------------------------


def _selected(answers: Answers) -> tuple[str, ...]:
    return tuple(answers["providers"])


def _default_primary(machine: Machine, answers: Answers) -> str:
    selected = _selected(answers)
    for preferred in ("claude_code", "ollama"):
        if preferred in selected:
            return preferred
    not_codex = [name for name in selected if name != "codex"]
    return (not_codex or list(selected))[0]


def _provider(machine: Machine, name: str) -> Provider:
    return machine.state_of(name).provider


def _primary_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(Option(name, _provider(machine, name).title) for name in _selected(answers))


def _parse_primary(text: str, machine: Machine, answers: Answers) -> str:
    return _one_of(_selected(answers), text)


def _fallback_candidates(answers: Answers) -> tuple[str, ...]:
    return tuple(name for name in _selected(answers) if name != answers["primary"])


def _default_fallback(machine: Machine, answers: Answers) -> str:
    return "ollama" if "ollama" in _fallback_candidates(answers) else ""


def _fallback_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    named = tuple(Option(n, _provider(machine, n).title) for n in _fallback_candidates(answers))
    return (*named, Option("none", "no fallback"))


def _parse_fallback(text: str, machine: Machine, answers: Answers) -> str:
    word = _one_of((*_fallback_candidates(answers), "none"), text)
    return "" if word == "none" else word


# --- 5 models, 6 ollama host -----------------------------------------------------------

MODEL_FORMAT = (
    "Format: <provider>=<model>,<model>; <provider>=<model>. The first model named for a "
    "provider is its default; Enter keeps the default shown. A provider you do not name "
    "keeps its default. Add a thinking level as <model>@<level> where the provider has levels."
)


def _offers(machine: Machine, name: str) -> tuple[Offer, ...]:
    return machine.state_of(name).models


def _default_models(machine: Machine, answers: Answers) -> dict[str, list[str]]:
    """One model per selected provider: the first its own list offers, else the catalogue's."""
    return {
        name: [chosen]
        for name in _selected(answers)
        if (chosen := providers.first_choice(_provider(machine, name), _offers(machine, name)))
    }


def _grouped_levels(offered: tuple[Offer, ...]) -> str:
    """The levels of a provider's models, one group per distinct set, so the line stays short."""
    groups: dict[tuple[str, ...], list[str]] = {}
    for offer in offered:
        groups.setdefault(offer.levels, []).append(offer.id)
    return "; ".join(
        f"{', '.join(levels)} for {', '.join(ids) if len(groups) > 1 else 'every model'}"
        for levels, ids in groups.items()
        if levels
    )


def _offer_line(provider: Provider, offered: tuple[Offer, ...]) -> str:
    """What a provider makes available on this machine, in words, for the prompt and the JSON."""
    ids = ", ".join(offer.id for offer in offered)
    match provider.listing:
        case providers.Listing.SIGN_IN if offered:
            listed = f"this sign-in offers: {ids}"
        case providers.Listing.SIGN_IN:
            listed = f"its model list could not be read (`{provider.list_command}`), so a model is accepted unchecked"
        case providers.Listing.PULLED if offered:
            listed = f"pulled here: {ids}; a model not pulled yet is accepted, then `ollama pull <model>`"
        case _:
            examples = ", ".join(provider.examples)
            listed = "it lists no models, so any name it knows is accepted unchecked" + (
                f", for example {examples}" if examples else ""
            )
    if provider.level_args:
        levels = _grouped_levels(offered) or ", ".join(provider.levels) or "the ones its model list shows"
        thinking = f"thinking levels, written <model>@<level>: {levels}"
    else:
        thinking = f"no @level: {provider.level_elsewhere}"
    return f"{listed}. {thinking}"


def _model_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(
        Option(name, _provider(machine, name).title, _offer_line(_provider(machine, name), _offers(machine, name)))
        for name in _selected(answers)
    )


def _example_models(machine: Machine, answers: Answers) -> str:
    """A worked answer built from this machine's own lists: two models and a level where it can."""
    parts = []
    for name in _selected(answers):
        provider, offered = _provider(machine, name), _offers(machine, name)
        names = [offer.id for offer in offered] or list(provider.examples)
        if not names:
            continue
        first = providers.first_choice(provider, offered) or names[0]
        offer = next((o for o in offered if o.id == first), None)
        levels = (offer.levels if offer is not None else ()) or provider.levels
        level = levels[0] if provider.level_args and levels else ""
        chosen = [f"{first}@{level}" if level else first, *[n for n in names if n != first][:1]]
        parts.append(f"{name}={','.join(chosen)}")
        if len(parts) == 2:
            break
    return "; ".join(parts)


def _example_or_format(machine: Machine, answers: Answers) -> str:
    """A worked answer, else the format with the first selected provider: no list gave a name."""
    return _example_models(machine, answers) or f"{next(iter(_selected(answers)), '<provider>')}=<model>"


def _model_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    example = _example_models(machine, answers)
    shown = (
        f"Example built from the lists above: {example}"
        if example
        else f"No model list could be read here, so name the model yourself, for example "
        f"{_example_or_format(machine, answers)}"
    )
    return (MODEL_FORMAT, shown, "Add or change models later: arhugula provider enable <provider> --model <model> [--model ...]")


def _checked_models(name: str, listed: Any, machine: Machine) -> list[str]:
    if isinstance(listed, str) or not isinstance(listed, list | tuple) or not listed:
        raise ValueError(f"name at least one model for {name}")
    provider, offered = _provider(machine, name), _offers(machine, name)
    try:
        return list(dict.fromkeys(providers.resolve(provider, str(model), offered).ref for model in listed))
    except providers.ModelRefused as refused:
        raise ValueError(str(refused)) from None


def _adopt_models(value: Any, machine: Machine, answers: Answers) -> dict[str, list[str]]:
    """Models given as data, checked against what each provider offers on this machine.

    A provider the data leaves out takes its default; one that is not selected is dropped,
    because the providers question decides the selection.
    """
    if not isinstance(value, Mapping):
        raise ValueError("give the models as an object: one list of models per provider")
    selected = _selected(answers)
    given = {name: listed for name, listed in value.items() if name in selected}
    models = {**_default_models(machine, answers), **{n: _checked_models(n, m, machine) for n, m in given.items()}}
    unnamed = [name for name in selected if name not in models]
    if unnamed:
        state = machine.state_of(unnamed[0])
        raise ValueError(
            f"name a model for {', '.join(unnamed)}: no default is known, because "
            f"`{state.provider.list_command or state.provider.command}` gave no model list "
            f"({state.status.value}: {state.detail})"
        )
    return {name: models[name] for name in selected}


def _keep_models(value: Any, machine: Machine, answers: Answers) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """The models an earlier run stored, as the default: each one still offered is kept.

    Where none of a provider's stored models is offered any more, the default shown is
    the provider's own first choice, and a note says which stored model was dropped and why.
    """
    stored = value if isinstance(value, Mapping) else {}
    defaults = _default_models(machine, answers)
    kept: dict[str, list[str]] = {}
    notes: list[str] = []
    for name in _selected(answers):
        provider, offered = _provider(machine, name), _offers(machine, name)
        listed = [str(m) for m in stored.get(name, ()) if isinstance(m, str)]
        refused = dict(providers.refusals(provider, listed, offered))
        still = [providers.resolve(provider, m, offered).ref for m in listed if m not in refused]
        notes += [f"stored before, no longer usable: {reason}" for reason in refused.values()]
        if still or name in defaults:
            kept[name] = still or defaults[name]
        if refused and not still and name in defaults:
            notes.append(f"so the default shown for {name} is {', '.join(defaults[name])}")
    return kept, tuple(notes)


def _parse_models(text: str, machine: Machine, answers: Answers) -> dict[str, list[str]]:
    selected = _selected(answers)
    named: dict[str, list[str]] = {}
    for part in (piece.strip() for piece in text.split(";")):
        if not part:
            continue
        name, equals, listed = (word.strip() for word in part.partition("="))
        if not equals:
            raise ValueError(f"`{part}` has no `=`: write <provider>=<model>, for example {_example_or_format(machine, answers)}")
        if name not in selected:
            raise ValueError(f"`{name}` is not one of the providers selected at question 2 ({', '.join(selected)})")
        if name in named:
            raise ValueError(f"`{name}` is named twice: put all its models in one part, {name}=<model>,<model>")
        models = [model.strip() for model in listed.split(",") if model.strip()]
        if not models:
            raise ValueError(f"`{name}=` names no model: write {name}=<model>")
        named[name] = models
    if not named:
        raise ValueError(f"name at least one provider, for example {_example_or_format(machine, answers)}")
    return _adopt_models(named, machine, answers)


def _ollama_selected(machine: Machine, answers: Answers) -> bool:
    return "ollama" in _selected(answers)


def _parse_text(text: str, machine: Machine, answers: Answers) -> str:
    word = text.strip()
    if not word:
        raise ValueError("give a value")
    return word


def _ollama_unreachable(machine: Machine, answers: Answers) -> bool:
    return _ollama_selected(machine, answers) and machine.ollama_models is None


# --- 7 project, 8 workloads -------------------------------------------------------------


def _parse_project(text: str, machine: Machine, answers: Answers) -> str:
    word = text.strip()
    if word in ("", "none"):
        return ""
    path = Path(_absolute(word))
    if not path.is_dir():
        raise ValueError(f"{path} is not a directory")
    return str(path)


def _workload_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(Option(str(i), name) for i, name in enumerate(spec.WORKLOADS, start=1))


def _parse_workloads(text: str, machine: Machine, answers: Answers) -> list[str]:
    picks = [c for c in text if not c.isspace() and c != ","]
    try:
        chosen = [spec.WORKLOADS[int(c) - 1] for c in picks]
    except (ValueError, IndexError):
        raise ValueError("use the numbers shown, for example `1234`") from None
    if not chosen or any(int(c) < 1 for c in picks):
        raise ValueError("choose at least one workload class")
    return list(dict.fromkeys(chosen))


# --- 9 features, 10 memory mode ---------------------------------------------------------


def _feature_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(Option(letter, text) for letter, _, text in FEATURE_LETTERS)


def _parse_features(text: str, machine: Machine, answers: Answers) -> list[str]:
    word = text.strip().lower()
    if word in ("none", "-"):
        return []
    by_letter = {letter: name for letter, name, _ in FEATURE_LETTERS}
    letters = [c for c in word if not c.isspace() and c != ","]
    unknown = [c for c in letters if c not in by_letter]
    if unknown:
        raise ValueError(f"use the letters shown, or `none` (unknown: {''.join(unknown)})")
    return list(dict.fromkeys(by_letter[c] for c in letters))


def _memory_on(machine: Machine, answers: Answers) -> bool:
    return "memory" in answers["features"]


def _memory_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return (
        Option("packet", "a memory packet is added to each prompt"),
        Option("packet+tools", "the packet, plus memory tools the agent can call"),
    )


def _parse_memory_mode(text: str, machine: Machine, answers: Answers) -> str:
    return _one_of(spec.MEMORY_MODES, text)


# --- 11 observability, 12 isolation -----------------------------------------------------

NO_ENGINE: dict[str, Any] = {"enabled": False, "engine": "none", "lima_home": "", "instance": ""}
KIT_ENGINE: dict[str, Any] = {"enabled": True, "engine": "kit", "lima_home": "", "instance": ""}


def _kit_lima_home(answers: Answers) -> Path:
    return Home(Path(answers["home"])).lima


def _other_instances(machine: Machine, answers: Answers) -> tuple[lima.Instance, ...]:
    """Lima instances the operator already had (the kit's own VM is not one of them)."""
    return tuple(i for i in machine.lima_instances if i.lima_home != _kit_lima_home(answers))


_LIMA_WANTED = ".".join(str(part) for part in lima.MINIMUM_VERSION[:2])


def _lima_usable(machine: Machine) -> bool:
    return machine.lima_version is not None and machine.lima_version >= lima.MINIMUM_VERSION


def _engine_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    existing = tuple(
        Option(
            value=f"{instance.lima_home}::{instance.name}",
            label=f"your existing Lima instance {instance.name}",
            note=f"{instance.status}, {instance.arch}, {instance.cpus} CPU, "
            f"{instance.memory_bytes // 2**30} GiB",
        )
        for instance in _other_instances(machine, answers)
        if instance.native
    )
    return (
        Option(
            "kit",
            "the kit's own virtual machine, built for this machine",
            f"created under {_kit_lima_home(answers)}; 5 to 10 minutes the first time",
        ),
        *existing,
        Option("n", "no observability tier"),
    )


def _default_engine(machine: Machine, answers: Answers) -> dict[str, Any]:
    return dict(KIT_ENGINE) if _lima_usable(machine) else dict(NO_ENGINE)


def _parse_engine(text: str, machine: Machine, answers: Answers) -> dict[str, Any]:
    word = text.strip()
    if word.lower() in ("n", "no"):
        return dict(NO_ENGINE)
    if not _lima_usable(machine):
        raise ValueError(
            f"the tier needs Lima {_LIMA_WANTED} or later, which is not installed (see the "
            "Lima row of the dependency list above). Answer n now; install Lima and run "
            "init again to add it"
        )
    # `:off` keeps the virtual machine without the trace stack (for isolation tier 3 alone).
    enabled = not word.lower().endswith(":off")
    choice = word if enabled else word[: -len(":off")]
    if choice.lower() in ("y", "yes", "kit"):
        return {**KIT_ENGINE, "enabled": enabled}
    lima_home, _, name = choice.partition("::")
    chosen = [
        i for i in _other_instances(machine, answers)
        if i.name == name and i.lima_home == Path(lima_home).expanduser()
    ]
    if not chosen:
        raise ValueError("answer kit, n, or one of the `<lima-home>::<instance>` values shown")
    if not chosen[0].native:
        raise ValueError(
            f"{name} holds a {chosen[0].arch} guest, and this machine is {lima.host_arch()}: "
            "Lima could only run it by emulating the other CPU. Answer kit to use a VM built "
            "for this machine"
        )
    return {"enabled": enabled, "engine": "existing", "lima_home": str(chosen[0].lima_home), "instance": name}


def _engine_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    notes = [
        "The stack (OpenTelemetry Collector, Tempo, Grafana) runs inside a Lima virtual "
        "machine's own Docker engine. Docker Desktop is not used.",
        "To have the virtual machine without the trace stack (for isolation tier 3 alone), "
        "add `:off`, for example `kit:off`.",
    ]
    if not _lima_usable(machine):
        notes.append("Lima is not installed, so the only answer available now is n.")
    notes += [
        f"Not offered: the Lima instance {i.name} holds a {i.arch} guest. This machine is "
        f"{lima.host_arch()}, so Lima could only run it by emulation, which is many times slower."
        for i in _other_instances(machine, answers)
        if not i.native
    ]
    return tuple(notes)


def _tier_available(machine: Machine, answers: Answers) -> bool:
    return answers["observability"]["engine"] != "none"


# --- 13 forbidden roots -----------------------------------------------------------------


def _parse_paths(text: str, machine: Machine, answers: Answers) -> list[str]:
    word = text.strip()
    if word in ("", "none"):
        return []
    return [_absolute(part.strip()) for part in word.split(",") if part.strip()]


def _forbidden_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    found = machine.time_machine_destinations
    seen = (
        f"Time Machine destinations found: {', '.join(found)}."
        if found
        else "No Time Machine destination was found."
    )
    return (
        "List every backup, snapshot or restore location that could reach the state root. "
        "The runtime treats an empty list as no evidence either way.",
        seen,
    )


QUESTIONS: tuple[Question, ...] = (
    Question(
        number=1,
        id="home",
        prompt="Deployment home directory? Everything the harness installs and stores lives here.",
        kind="path",
        why="The location is yours to choose. It must not be inside a git checkout.",
        default_doc="`~/arhugula`, or the directory that already holds this kit clone as `kit/`",
        default=_default_home,
        parse=_parse_home,
    ),
    Question(
        number=2,
        id="providers",
        prompt="Which providers should be available? Type the letters of each one you want.",
        kind="multi",
        why="Each selected provider is checked in preflight and written into the config.",
        default_doc="every command-line provider found installed and signed in, plus Ollama when it answers",
        default=_default_providers,
        parse=_parse_providers,
        options=_provider_options,
        notes=_provider_notes,
        adopt=_adopt_providers,
    ),
    Question(
        number=3,
        id="primary",
        prompt="Default provider for workflows?",
        kind="choice",
        why="The first fallback chain serves every step unless a run overrides it.",
        default_doc="Claude Code when selected, else Ollama, else the first selected provider; never Codex when another is selected",
        default=_default_primary,
        parse=_parse_primary,
        options=_primary_options,
    ),
    Question(
        number=4,
        id="fallback",
        prompt="Fallback provider when the default fails?",
        kind="choice",
        why="A second provider keeps a run going when the first one refuses.",
        default_doc="Ollama when it is selected and is not the default provider; otherwise none",
        default=_default_fallback,
        parse=_parse_fallback,
        options=_fallback_options,
    ),
    Question(
        number=5,
        id="models",
        prompt="Which models should each selected provider make available? Type "
        "<provider>=<model>,<model>, providers separated by `;`, or press Enter for the defaults.",
        kind="models",
        why="Routing, workflows and `--model` can use only the models named here. The first "
        "one named for a provider is its default. Where a provider's tool lists its models "
        "(Codex, Antigravity, Ollama), init checks each name against that list.",
        default_doc="the first model each provider's own tool lists for your sign-in. Ollama: "
        "`llama3.2:3b` (init offers to pull it when it is not pulled). Where a tool lists none: "
        "`sonnet` for Claude Code, the catalogue's example model for a hosted API",
        default=_default_models,
        parse=_parse_models,
        options=_model_options,
        notes=_model_notes,
        adopt=_adopt_models,
        keep=_keep_models,
    ),
    Question(
        number=6,
        id="ollama_host",
        prompt="Ollama host URL?",
        kind="text",
        why="Asked only when Ollama does not answer at its default address.",
        default_doc="`http://127.0.0.1:11434`",
        default=lambda machine, answers: machine.ollama_host,
        parse=_parse_text,
        applies=_ollama_unreachable,
        applies_when="Ollama is selected and does not answer at the default address",
    ),
    Question(
        number=7,
        id="project",
        prompt="Attach a project now? Give the path to a project repository, or press Enter to skip.",
        kind="path",
        why="One install serves many projects. You can attach more later with `project add`.",
        default_doc="none",
        default=lambda machine, answers: "",
        parse=_parse_project,
    ),
    Question(
        number=8,
        id="workloads",
        prompt="Workload classes to bind? Type the numbers.",
        kind="multi",
        why="A workload class is the kind of work a workflow declares. A workflow runs only when its class is bound. The shipped examples and the daemon need all four, so keep all four unless you know you want fewer.",
        default_doc="all four",
        default=lambda machine, answers: list(spec.WORKLOADS),
        parse=_parse_workloads,
        options=_workload_options,
    ),
    Question(
        number=9,
        id="features",
        prompt="Enable now? Type the letters, or `none`.",
        kind="multi",
        why="Each stays switchable later with `feature enable` and `feature disable`.",
        default_doc="memory",
        default=lambda machine, answers: ["memory"],
        parse=_parse_features,
        options=_feature_options,
    ),
    Question(
        number=10,
        id="memory_mode",
        prompt="Memory access?",
        kind="choice",
        why="Both modes are witnessed. Tools let the agent look things up on its own.",
        default_doc="`packet+tools`",
        default=lambda machine, answers: "packet+tools",
        parse=_parse_memory_mode,
        options=_memory_options,
        applies=_memory_on,
        applies_when="memory is enabled",
    ),
    Question(
        number=11,
        id="observability",
        prompt="Set up the observability tier (collector, Tempo, Grafana)? Answer kit, n, or an "
        "existing instance shown below.",
        kind="engine",
        why="Traces, dashboards and alerts. Without it, traces stay in the local span store only.",
        default_doc="`kit` when Lima is installed, otherwise `n`",
        default=_default_engine,
        parse=_parse_engine,
        options=_engine_options,
        notes=_engine_notes,
    ),
    Question(
        number=12,
        id="isolation_tier3",
        prompt="Enable isolation tier 3 (tools run under gVisor in the virtual machine)?",
        kind="yesno",
        why="Tool calls from Model Context Protocol (MCP) clients run in a sandboxed container. Off by default.",
        default_doc="no",
        default=lambda machine, answers: False,
        parse=_yes_no,
        applies=_tier_available,
        applies_when="a virtual machine was chosen at question 11",
    ),
    Question(
        number=13,
        id="forbidden_roots",
        prompt="Backup or restore locations that can reach the state root? Comma-separated "
        "paths, or press Enter for none.",
        kind="paths",
        why="A backup tool that restores old files over the state root would silently undo the harness's records. The runtime refuses a state root inside any location you list here. If you do not know of one, press Enter.",
        default_doc="none",
        default=lambda machine, answers: [],
        parse=_parse_paths,
        notes=_forbidden_notes,
    ),
    Question(
        number=14,
        id="smoke",
        prompt="Run the smoke workflows now?",
        kind="yesno",
        why="One short run on each route proves the deployment end to end: the default provider, Ollama when selected, and the attached project.",
        default_doc="yes",
        default=lambda machine, answers: True,
        parse=_yes_no,
    ),
)


def _shown(value: Any) -> str:
    """A default as the operator would type it."""
    match value:
        case bool():
            return "y" if value else "n"
        case {"engine": "none"}:
            return "n"
        case {"engine": "existing", "lima_home": lima_home, "instance": instance, "enabled": enabled}:
            return f"{lima_home}::{instance}" + ("" if enabled else ":off")
        case {"engine": "kit", "enabled": enabled}:
            return "kit" if enabled else "kit:off"
        case list():
            return ",".join(str(item) for item in value) or "none"
        case "":
            return "none"
        case _:
            return str(value)


def _typed_default(question: Question, value: Any) -> str:
    """The text that parses back to `value`, for prompts whose input is letters or numbers."""
    match question.id:
        case "providers":
            # Only the built-in providers have letters; init keeps an added one selected.
            letters = {p.name: p.letter for p in providers.CATALOGUE}
            return "".join(letters[name] for name in value if name in letters)
        case "models":
            return "; ".join(f"{name}={','.join(models)}" for name, models in value.items())
        case "workloads":
            return "".join(str(spec.WORKLOADS.index(name) + 1) for name in value)
        case "features":
            # Question 9 offers five features; the others are switched with `feature enable`.
            letters = {name: letter for letter, name, _ in FEATURE_LETTERS}
            return "".join(letters[name] for name in value if name in letters) or "none"
        case _:
            return _shown(value)


def ask_all(
    machine: Machine,
    *,
    preset: Answers,
    accept_defaults: bool = False,
    out: TextIO = sys.stdout,
    read: Callable[[str], str] = input,
) -> dict[str, Any]:
    """Ask every applicable question on the terminal. Enter accepts the default shown.

    `preset` holds answers from an earlier run: each one becomes that question's default.
    """
    answers: dict[str, Any] = {}
    for question in QUESTIONS:
        fallback = question.default(machine, answers)
        if not question.applies(machine, answers):
            answers[question.id] = fallback
            continue
        default, kept_notes = _preset_default(question, preset, fallback, machine, answers)
        typed_default = _typed_default(question, default)
        print(f"\n[{question.number}/{len(QUESTIONS)}] {question.prompt}", file=out)
        for option in question.options(machine, answers):
            note = f"  ({option.note})" if option.note else ""
            print(f"      [{option.value}] {option.label}{note}", file=out)
        for note in (*question.notes(machine, answers), *kept_notes):
            print(f"      note: {note}", file=out)
        while True:
            if accept_defaults:
                print(f"    default accepted: {typed_default}", file=out)
                text = ""
            else:
                text = read(f"    answer [{typed_default}]: ")
            try:
                answers[question.id] = (
                    question.parse(text, machine, answers) if text.strip() else default
                )
                # A default is parsed too, so a stale preset is caught here, not later.
                if not text.strip():
                    answers[question.id] = question.parse(typed_default, machine, answers)
                break
            except ValueError as exc:
                if accept_defaults:
                    raise KitError(
                        Exit.PRECONDITION,
                        f"question {question.number} ({question.id}) has no usable default: {exc}",
                        fix="run `init` without --yes and answer it",
                    ) from exc
                print(f"    {exc}", file=out)
    return answers


def _preset_default(
    question: Question, preset: Answers, fallback: Any, machine: Machine, answers: Answers
) -> tuple[Any, tuple[str, ...]]:
    """An earlier answer as this question's default, with a note for each part that no longer holds.

    Nothing stale is dropped quietly: either a note says what was dropped, or the stale
    answer is shown as the default and parsing it says what is wrong.
    """
    if question.id not in preset:
        return fallback, ()
    if question.keep is not None:
        return question.keep(preset[question.id], machine, answers)
    try:
        return question.adopt(preset[question.id], machine, answers), ()
    except ValueError:
        return preset[question.id], ()


def describe(machine: Machine, preset: Answers) -> list[dict[str, Any]]:
    """The questions as data, for an agent to ask through its own surface.

    Defaults and options are computed for this machine. A question whose `applies_when`
    depends on an earlier answer is listed with the condition in words; `complete`
    enforces it when the answers file comes back.
    """
    described: list[dict[str, Any]] = []
    assumed: dict[str, Any] = {}
    for question in QUESTIONS:
        default, kept_notes = _preset_default(question, preset, question.default(machine, assumed), machine, assumed)
        assumed[question.id] = default
        described.append(
            {
                "number": question.number,
                "id": question.id,
                "prompt": question.prompt,
                "kind": question.kind,
                "why": question.why,
                "default_in_words": question.default_doc,
                "applies_when": question.applies_when,
                "default": default,
                "default_as_typed": _typed_default(question, default),
                "options": [
                    {"value": o.value, "label": o.label, "note": o.note}
                    for o in question.options(machine, assumed)
                ],
                "notes": [*question.notes(machine, assumed), *kept_notes],
            }
        )
    return described


def complete(machine: Machine, given: Answers) -> dict[str, Any]:
    """Check an answers file against the table: every applicable question must be answered.

    A question that does not apply takes its neutral default; that is not a silent
    default, because the operator was never going to be asked it.
    """
    answers: dict[str, Any] = {}
    for question in QUESTIONS:
        if question.applies(machine, answers):
            if question.id not in given:
                raise KitError(
                    Exit.PRECONDITION,
                    f"the answers file has no answer for question {question.number} "
                    f"(`{question.id}`): {question.prompt}",
                    fix="add the answer; `init --questions-json` lists every question",
                )
            try:
                answers[question.id] = question.adopt(given[question.id], machine, answers)
            except ValueError as wrong:
                raise KitError(
                    Exit.PRECONDITION,
                    f"the answers file's answer to question {question.number} (`{question.id}`) "
                    f"is not usable: {wrong}",
                    fix="correct it; `init --questions-json` shows what this machine offers",
                ) from wrong
        else:
            answers[question.id] = given.get(question.id, question.default(machine, answers))
    return answers
