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

from arhugula_kit import detect, providers, spec
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT

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
    default: Callable[[Machine, Answers], Any]
    parse: Callable[[str, Machine, Answers], Any]
    options: Callable[[Machine, Answers], tuple[Option, ...]] = _no_options
    applies: Callable[[Machine, Answers], bool] = _always
    applies_when: str = "always"
    notes: Callable[[Machine, Answers], tuple[str, ...]] = _no_notes


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


def _provider_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(
        Option(
            value=state.provider.letter,
            label=state.provider.title,
            note=f"{state.status.value}: {state.detail}",
        )
        for state in machine.provider_states
    )


def _default_providers(machine: Machine, answers: Answers) -> list[str]:
    return [
        state.provider.name
        for state in machine.provider_states
        if state.usable and state.provider.access is not providers.Access.SDK
    ]


def _parse_providers(text: str, machine: Machine, answers: Answers) -> list[str]:
    by_letter = {p.letter: p.name for p in providers.CATALOGUE}
    letters = [c for c in text if not c.isspace() and c != ","]
    unknown = [c for c in letters if c not in by_letter]
    if unknown or not letters:
        raise ValueError(f"use the letters shown, for example `co` (unknown: {''.join(unknown)})")
    return list(dict.fromkeys(by_letter[c] for c in letters))


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


def _primary_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(Option(name, providers.by_name(name).title) for name in _selected(answers))


def _parse_primary(text: str, machine: Machine, answers: Answers) -> str:
    return _one_of(_selected(answers), text)


def _fallback_candidates(answers: Answers) -> tuple[str, ...]:
    return tuple(name for name in _selected(answers) if name != answers["primary"])


def _default_fallback(machine: Machine, answers: Answers) -> str:
    return "ollama" if "ollama" in _fallback_candidates(answers) else ""


def _fallback_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    named = tuple(Option(n, providers.by_name(n).title) for n in _fallback_candidates(answers))
    return (*named, Option("none", "no fallback"))


def _parse_fallback(text: str, machine: Machine, answers: Answers) -> str:
    word = _one_of((*_fallback_candidates(answers), "none"), text)
    return "" if word == "none" else word


# --- 5 ollama model, 6 ollama host ------------------------------------------------------


def _ollama_selected(machine: Machine, answers: Answers) -> bool:
    return "ollama" in _selected(answers)


def _model_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(Option(name, "pulled") for name in machine.ollama_models or ())


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


def _engine_options(machine: Machine, answers: Answers) -> tuple[Option, ...]:
    return tuple(
        Option(
            value=f"{instance.lima_home}::{instance.name}",
            label=f"Lima instance {instance.name}",
            note=f"{instance.status}, {instance.vm_type}, {instance.cpus} CPU, "
            f"{instance.memory_bytes // 2**30} GiB, LIMA_HOME={instance.lima_home}",
        )
        for instance in machine.lima_instances
    )


def _default_engine(machine: Machine, answers: Answers) -> dict[str, Any]:
    if not machine.lima_instances:
        return {"enabled": False, "lima_home": "", "instance": ""}
    first = machine.lima_instances[0]
    return {"enabled": True, "lima_home": str(first.lima_home), "instance": first.name}


def _parse_engine(text: str, machine: Machine, answers: Answers) -> dict[str, Any]:
    word = text.strip()
    if word.lower() in ("n", "no"):
        return {"enabled": False, "lima_home": "", "instance": ""}
    if word.lower() in ("y", "yes"):
        chosen = _default_engine(machine, answers)
        if not chosen["enabled"]:
            raise ValueError(
                "no Lima instance was found. Give the Lima home that holds the VM as "
                "`<lima-home>::<instance>`, or answer n"
            )
        return chosen
    lima_home, _, name = word.partition("::")
    if not name or not Path(lima_home).expanduser().is_dir():
        raise ValueError("answer y, n, or `<lima-home>::<instance>` with an existing Lima home")
    return {"enabled": True, "lima_home": str(Path(lima_home).expanduser()), "instance": name}


def _engine_notes(machine: Machine, answers: Answers) -> tuple[str, ...]:
    notes = [
        "The stack (OpenTelemetry Collector, Tempo, Grafana) runs inside a Lima virtual "
        "machine's own Docker engine. Docker Desktop is not used.",
    ]
    if not machine.lima_instances:
        notes.append(
            "No Lima instance was found under $LIMA_HOME or the default Lima home. If your "
            "VM lives elsewhere, answer `<lima-home>::<instance>`."
        )
    return tuple(notes)


def _tier_available(machine: Machine, answers: Answers) -> bool:
    return bool(answers["observability"]["instance"])


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
        default=_default_home,
        parse=_parse_home,
    ),
    Question(
        number=2,
        id="providers",
        prompt="Which providers should be available? Type the letters of each one you want.",
        kind="multi",
        why="Each selected provider is checked in preflight and written into the config.",
        default=_default_providers,
        parse=_parse_providers,
        options=_provider_options,
        notes=_provider_notes,
    ),
    Question(
        number=3,
        id="primary",
        prompt="Default provider for workflows?",
        kind="choice",
        why="The first fallback chain serves every step unless a run overrides it.",
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
        default=_default_fallback,
        parse=_parse_fallback,
        options=_fallback_options,
    ),
    Question(
        number=5,
        id="ollama_model",
        prompt="Ollama model?",
        kind="text",
        why="The model Ollama steps run on. Init offers to pull it when it is absent.",
        default=lambda machine, answers: providers.by_name("ollama").default_model,
        parse=_parse_text,
        options=_model_options,
        applies=_ollama_selected,
        applies_when="Ollama is selected",
    ),
    Question(
        number=6,
        id="ollama_host",
        prompt="Ollama host URL?",
        kind="text",
        why="Asked only when Ollama does not answer at its default address.",
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
        default=lambda machine, answers: "",
        parse=_parse_project,
    ),
    Question(
        number=8,
        id="workloads",
        prompt="Workload classes to bind? Type the numbers.",
        kind="multi",
        why="All four are needed for the shipped topology examples and for the daemon.",
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
        default=lambda machine, answers: "packet+tools",
        parse=_parse_memory_mode,
        options=_memory_options,
        applies=_memory_on,
        applies_when="memory is enabled",
    ),
    Question(
        number=11,
        id="observability",
        prompt="Set up the observability tier (collector, Tempo, Grafana)? Answer y, n, or "
        "`<lima-home>::<instance>`.",
        kind="engine",
        why="Traces, dashboards and alerts. Without it, traces stay in the local span store only.",
        default=_default_engine,
        parse=_parse_engine,
        options=_engine_options,
        notes=_engine_notes,
    ),
    Question(
        number=12,
        id="isolation_tier3",
        prompt="Enable isolation tier 3 (tools run under gVisor in the Lima VM)?",
        kind="yesno",
        why="Tool calls from MCP clients run in a sandboxed container. Off by default.",
        default=lambda machine, answers: False,
        parse=_yes_no,
        applies=_tier_available,
        applies_when="a Lima instance was chosen at question 11",
    ),
    Question(
        number=13,
        id="forbidden_roots",
        prompt="Backup or restore locations that can reach the state root? Comma-separated "
        "paths, or press Enter for none.",
        kind="paths",
        why="The runtime refuses a state root inside a location that could restore over it.",
        default=lambda machine, answers: [],
        parse=_parse_paths,
        notes=_forbidden_notes,
    ),
    Question(
        number=14,
        id="smoke",
        prompt="Run the smoke workflows now?",
        kind="yesno",
        why="Two short runs prove the deployment end to end.",
        default=lambda machine, answers: True,
        parse=_yes_no,
    ),
)


def _shown(value: Any) -> str:
    """A default as the operator would type it."""
    match value:
        case bool():
            return "y" if value else "n"
        case {"enabled": enabled, "lima_home": lima_home, "instance": instance}:
            return f"{lima_home}::{instance}" if enabled else "n"
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
            return "".join(providers.by_name(name).letter for name in value)
        case "workloads":
            return "".join(str(spec.WORKLOADS.index(name) + 1) for name in value)
        case "features":
            letters = {name: letter for letter, name, _ in FEATURE_LETTERS}
            return "".join(letters[name] for name in value) or "none"
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
        default = preset.get(question.id, fallback)
        typed_default = _typed_default(question, default)
        print(f"\n[{question.number}/{len(QUESTIONS)}] {question.prompt}", file=out)
        for option in question.options(machine, answers):
            note = f"  ({option.note})" if option.note else ""
            print(f"      [{option.value}] {option.label}{note}", file=out)
        for note in question.notes(machine, answers):
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


def describe(machine: Machine, preset: Answers) -> list[dict[str, Any]]:
    """The questions as data, for an agent to ask through its own surface.

    Defaults and options are computed for this machine. A question whose `applies_when`
    depends on an earlier answer is listed with the condition in words; `complete`
    enforces it when the answers file comes back.
    """
    described: list[dict[str, Any]] = []
    assumed: dict[str, Any] = {}
    for question in QUESTIONS:
        default = preset.get(question.id, question.default(machine, assumed))
        assumed[question.id] = default
        described.append(
            {
                "number": question.number,
                "id": question.id,
                "prompt": question.prompt,
                "kind": question.kind,
                "why": question.why,
                "applies_when": question.applies_when,
                "default": default,
                "default_as_typed": _typed_default(question, default),
                "options": [
                    {"value": o.value, "label": o.label, "note": o.note}
                    for o in question.options(machine, assumed)
                ],
                "notes": list(question.notes(machine, assumed)),
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
            answers[question.id] = given[question.id]
        else:
            answers[question.id] = given.get(question.id, question.default(machine, answers))
    return answers
