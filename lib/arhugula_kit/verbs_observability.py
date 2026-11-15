"""Observability verbs: the VM, the trace stack, traces, the span store, logs, evaluation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from arhugula_kit import deploy, lima, observability, runtime, vm
from arhugula_kit.common import say, table
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.spec import Engine, Observability
from arhugula_kit.verbs import Arg, Verb

HOLDOUT_PRIMITIVES = ("routing_accuracy_holdout", "sandbox_tier_routing_accuracy")
DRIFT_PRIMITIVES = (
    "cache_hit_rate_alignment_floor",
    "routing_accuracy_holdout",
    "sandbox_tier_routing_accuracy",
    "judge_human_cohens_kappa",
)
WINDOW_KINDS = ("TIME_WINDOW", "SAMPLE_WINDOW")


# --- the VM -----------------------------------------------------------------------------


def _with_engine(deployment: Deployment, engine: Observability) -> Deployment:
    return deploy.apply(deployment, replace(deployment.spec, observability=engine))


def _vm_create(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    say("Virtual machine:")
    engine = vm.create(deployment.home, out=say)
    _with_engine(deployment, replace(deployment.spec.observability, engine=Engine.KIT, lima_home="", instance=""))
    say(f"  Docker {engine.server_version}, Compose {engine.compose_version}, "
        f"gVisor {'runsc' if engine.has_gvisor else 'MISSING'}")
    say("The VM is ready. Start the trace stack with: arhugula observability up")
    return Exit.OK


def _vm_use(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    lima_home, _, name = args.instance.partition("::")
    ref = lima.VmRef(Path(lima_home).expanduser(), name, kit_owned=False)
    found = lima.find(ref) if name else None
    if found is None:
        raise KitError(
            Exit.PRECONDITION,
            f"no Lima instance named {name!r} under {ref.lima_home}",
            fix="give it as `<lima-home>::<instance>`; `limactl list` shows the instances of the default Lima home",
        )
    if not found.native:
        raise vm.emulation_refusal(found)
    if observability.is_up(deployment):
        raise KitError(Exit.PRECONDITION, "the stack is running in the current VM",
                       fix="arhugula observability down")
    _with_engine(
        deployment,
        replace(deployment.spec.observability, engine=Engine.EXISTING,
                lima_home=str(ref.lima_home), instance=name),
    )
    say(f"This deployment now uses the Lima instance {name} under {ref.lima_home}.")
    return Exit.OK


def _vm_delete(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    ref = vm.kit_ref(deployment.home)
    found = lima.find(ref)
    if found is None:
        say(f"There is no VM named {ref.name} under {ref.lima_home}.")
        return Exit.OK
    if deployment.spec.isolation_tier3:
        raise KitError(Exit.PRECONDITION, "isolation tier 3 runs tools in this VM",
                       fix="arhugula isolation disable")
    if not args.yes:
        say(f"This deletes the VM {ref.name} under {ref.lima_home}, with the traces and "
            "Grafana data stored inside it.")
        say("Nothing was deleted. Run again with --yes to delete it.")
        return Exit.OK
    found.delete()
    if deployment.spec.observability.engine is Engine.KIT:
        _with_engine(deployment, Observability())
    say(f"Deleted the VM {ref.name}. The observability tier is off.")
    return Exit.OK


def _vm_status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    current = observability.status(deployment)
    say(f"engine choice: {deployment.spec.observability.engine.value}")
    say(f"VM:            {current.vm}")
    if current.engine:
        say(f"inside it:     {current.engine}")
    return Exit.OK


# --- the stack --------------------------------------------------------------------------


def _up(args: argparse.Namespace) -> int:
    observability.up(deploy.open_deployment(), out=say)
    return Exit.OK


def _down(args: argparse.Namespace) -> int:
    observability.down(
        deploy.open_deployment(), stop_vm=args.stop_vm, delete_data=args.delete_data, out=say
    )
    return Exit.OK


def _status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    current = observability.status(deployment)
    say(f"tier:    {'on' if deployment.spec.observability.enabled else 'off'}")
    say(f"VM:      {current.vm}")
    say(f"engine:  {current.engine or 'not reachable while the VM is stopped'}")
    say("")
    if current.containers:
        table(current.containers, header=("service", "state"))
    else:
        say("no container of the stack exists (`arhugula observability up`)")
    say("")
    table(
        [(name, f"127.0.0.1:{port}", "listening" if listening else "closed")
         for name, port, listening in current.ports],
        header=("port", "address", "state"),
    )
    say("")
    say(f"newest trace in Tempo: {current.newest_trace or 'none (or Tempo does not answer)'}")
    say(f"local span store:      {_store_summary(deployment.home.span_store)}")
    return Exit.OK


# --- traces and the span store ----------------------------------------------------------


def _store(deployment: Deployment) -> Path:
    store = deployment.home.span_store
    if not store.is_file():
        raise KitError(
            Exit.PRECONDITION,
            f"there is no span store at {store} yet; the runtime creates it on the first run",
            fix="arhugula run examples/minimal.toml --project default",
        )
    return store


def _store_summary(store: Path) -> str:
    if not store.is_file():
        return f"{store} (not created yet; the first run creates it)"
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as conn:
        spans, traces, newest = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT trace_id), MAX(end_time_ns) FROM spans"
        ).fetchone()
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(newest / 1e9)) if newest else "never"
    return f"{store}: {spans} spans in {traces} traces; newest span ended {when}"


def _trace_list(args: argparse.Namespace) -> int:
    store = _store(deploy.open_deployment())
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """
            SELECT trace_id, MIN(start_time_ns), MAX(end_time_ns), COUNT(*),
                   MAX(workflow_id), MAX(status_code)
            FROM spans GROUP BY trace_id ORDER BY MIN(start_time_ns) DESC LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    table(
        [
            (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start / 1e9)),
                f"{(end - start) / 1e9:.1f} s",
                str(count),
                workflow or "-",
                "error" if status == 2 else "ok",
                trace_id,
            )
            for trace_id, start, end, count, workflow, status in rows
        ],
        header=("started", "took", "spans", "workflow", "status", "trace id"),
    )
    return Exit.OK


def _trace_browse(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    return runtime.exec_tool(
        deployment.home.harness_inspect,
        ["--browse", "--collector-path", _store(deployment)],
        cwd=deployment.home.upstream,
    )


def _trace_export(args: argparse.Namespace) -> int:
    store = _store(deploy.open_deployment())
    where, values = ("WHERE trace_id = ?", (args.trace_id,)) if args.trace_id else ("", ())
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM spans {where} ORDER BY start_time_ns", values).fetchall()
    if args.trace_id and not rows:
        raise KitError(Exit.PRECONDITION, f"no trace {args.trace_id} in the span store",
                       fix="arhugula trace list")
    lines = []
    for row in rows:
        record: dict[str, Any] = dict(row)
        record["attributes"] = json.loads(record.pop("attributes_json"))
        record["events"] = json.loads(record.pop("events_json"))
        lines.append(json.dumps(record, sort_keys=True))
    text = "\n".join(lines) + ("\n" if lines else "")
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        say(f"wrote {len(lines)} span(s) to {args.out}")
    else:
        print(text, end="")
    return Exit.OK


def _collector_status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    say(f"span store: {_store_summary(deployment.home.span_store)}")
    say("written by: the runtime itself, on every run "
        "(`[runtime.collector] span_store_path` in the generated config)")
    say("read by:    arhugula trace list | browse | export, and arhugula eval sample")
    return Exit.OK


def _collector_bridge(args: argparse.Namespace) -> int:
    say("No bridge is needed at this pin. The runtime writes the local span store itself "
        "on every run, and sends the same spans to the collector when the stack is up.")
    say("See: arhugula collector status")
    return Exit.OK


# --- logs -------------------------------------------------------------------------------


def _logs(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    if args.collected:
        text = observability.collected_logs(deployment)
        print("\n".join(text.splitlines()[-args.lines:]) if text else
              "the logs pipeline has written nothing yet")
        return Exit.OK
    logs = sorted(deployment.home.logs.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if args.list or not logs:
        table(
            [(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)),
              str(p.stat().st_size), p.name) for p in logs],
            header=("written", "bytes", "file"),
        )
        say(f"\ndirectory: {deployment.home.logs}")
        return Exit.OK
    chosen = deployment.home.logs / args.name if args.name else logs[0]
    if not chosen.is_file():
        raise KitError(Exit.PRECONDITION, f"no log file {chosen}", fix="arhugula logs --list")
    say(f"# {chosen}")
    print("\n".join(chosen.read_text(encoding="utf-8", errors="replace").splitlines()[-args.lines:]))
    return Exit.OK


# --- evaluation -------------------------------------------------------------------------


def _eval_dir(deployment: Deployment, primitive: str) -> Path:
    return deployment.home.evaluation / primitive


def _inspect(deployment: Deployment, words: list[str | Path]) -> int:
    return runtime.exec_tool(deployment.home.harness_inspect, words, cwd=deployment.home.upstream)


def _eval_sample(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    directory = _eval_dir(deployment, args.primitive)
    directory.mkdir(parents=True, exist_ok=True)
    holdout = directory / "holdout.json"
    if holdout.exists() and not args.replace:
        raise KitError(
            Exit.PRECONDITION,
            f"a holdout set already exists at {holdout}",
            fix="review it with `arhugula eval review`, or draw a new one with --replace",
        )
    holdout.unlink(missing_ok=True)
    return _inspect(
        deployment,
        ["--collector-path", _store(deployment), "--holdout-sample", str(args.count),
         "--primitive", args.primitive, "--seed", str(args.seed), "--holdout-path", holdout],
    )


def _eval_review(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    directory = _eval_dir(deployment, args.primitive)
    if not (directory / "holdout.json").is_file():
        raise KitError(Exit.PRECONDITION, f"no holdout set for {args.primitive}",
                       fix=f"arhugula eval sample --primitive {args.primitive}")
    return _inspect(
        deployment,
        ["--holdout-review", "--holdout-path", directory / "holdout.json",
         "--review-ledger-path", directory / "review-ledger.jsonl"],
    )


def _eval_scaffold(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    directory = _eval_dir(deployment, args.primitive)
    if not (directory / "review-ledger.jsonl").is_file():
        raise KitError(Exit.PRECONDITION, f"nothing is reviewed for {args.primitive} yet",
                       fix=f"arhugula eval review --primitive {args.primitive}")
    return _inspect(
        deployment,
        ["--holdout-scaffold", "--review-ledger-path", directory / "review-ledger.jsonl",
         "--stub-dir", directory / "stubs"],
    )


def _run_stub(path: Path) -> str:
    """Run one operator-authored assertion file: passed, failed, not filled in, or broken."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        for name in sorted(vars(module)):
            if name.startswith("test_holdout_"):
                getattr(module, name)()
    except NotImplementedError:
        return "not filled in"
    except AssertionError as failure:
        return f"FAILED: {failure}" if str(failure) else "FAILED"
    except Exception as broken:  # the operator's own code: report whatever it raised
        return f"broken: {type(broken).__name__}: {broken}"
    return "passed"


def _ledger(directory: Path) -> list[dict[str, Any]]:
    path = directory / "review-ledger.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _eval_rows(deployment: Deployment) -> list[tuple[str, int, list[dict[str, Any]], dict[str, str]]]:
    rows = []
    for primitive in HOLDOUT_PRIMITIVES:
        directory = _eval_dir(deployment, primitive)
        holdout = directory / "holdout.json"
        sampled = len(json.loads(holdout.read_text(encoding="utf-8"))["traces"]) if holdout.is_file() else 0
        stubs = {p.name: _run_stub(p) for p in sorted((directory / "stubs").glob("test_holdout_*.py"))}
        rows.append((primitive, sampled, _ledger(directory), stubs))
    return rows


def _eval_status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    failed = False
    for primitive, sampled, ledger, stubs in _eval_rows(deployment):
        outcomes = Counter(result.split(":")[0] for result in stubs.values())
        say(f"{primitive}: {sampled} sampled, {len(ledger)} reviewed, {len(stubs)} assertion file(s)"
            + (f" ({', '.join(f'{count} {word}' for word, count in sorted(outcomes.items()))})" if stubs else ""))
        for name, result in stubs.items():
            say(f"    {name}: {result}")
            failed = failed or result.startswith(("FAILED", "broken"))
    say(f"\nfiles: {deployment.home.evaluation}")
    say("The loop: eval sample -> eval review -> eval scaffold -> fill in each assertion -> eval status.")
    return Exit.WORKFLOW if failed else Exit.OK


def _eval_report(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    report = {
        primitive: {
            "sampled": sampled,
            "reviewed": len(ledger),
            "categories": dict(Counter(str(entry.get("category", "?")) for entry in ledger)),
            "assertions": stubs,
        }
        for primitive, sampled, ledger, stubs in _eval_rows(deployment)
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return Exit.OK
    for primitive, body in report.items():
        say(f"## {primitive}")
        say(f"sampled {body['sampled']}, reviewed {body['reviewed']}")
        if body["categories"]:
            table(sorted((k, str(v)) for k, v in body["categories"].items()), header=("category", "traces"))
        if body["assertions"]:
            table(sorted(body["assertions"].items()), header=("assertion file", "result"))
        say("")
    return Exit.OK


def _drift_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    stored = deployment.spec.drift_thresholds
    chosen = [args.primitive] if args.primitive else list(stored)
    if not chosen:
        say("No drift threshold is set. Set one with: arhugula eval drift set-threshold "
            "<primitive> <value>")
        say(f"Primitives: {', '.join(DRIFT_PRIMITIVES)}")
        return Exit.OK
    drifted = False
    for primitive in chosen:
        if primitive not in stored:
            raise KitError(Exit.PRECONDITION, f"no threshold is set for {primitive}",
                           fix=f"arhugula eval drift set-threshold {primitive} <value>")
        setting = stored[primitive]
        arguments = {**setting, "primitive": primitive, "store": str(_store(deployment))}
        if args.judge_value is not None:
            arguments["judge_value"] = args.judge_value
        match runtime.ask(deployment.home, "drift-check", **arguments):
            case runtime.Refusal(kind="needs-judge-value", message=message):
                say(f"{primitive}: cannot be computed from spans ({message}). "
                    "Pass your own measured value with --judge-value.")
            case runtime.Refusal(kind=kind, message=message):
                raise KitError(Exit.RUNTIME_REFUSED, f"the runtime refused ({kind}): {message}")
            case {"current_value": None}:
                say(f"{primitive}: no data in the window (threshold {setting['threshold']})")
            case value:
                drifted = drifted or bool(value["drift"])
                say(f"{primitive}: current {value['current_value']:.4f}, threshold "
                    f"{value['threshold']}, window {setting['window_kind']} {setting['window_size']}: "
                    f"{'DRIFT' if value['drift'] else 'within the floor'}")
    return Exit.WORKFLOW if drifted else Exit.OK


def _drift_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    thresholds = {
        **deployment.spec.drift_thresholds,
        args.primitive: {
            "threshold": args.value,
            "window_kind": args.window_kind,
            "window_size": args.window_size,
        },
    }
    deploy.apply(deployment, replace(deployment.spec, drift_thresholds=thresholds))
    say(f"{args.primitive}: threshold {args.value} over {args.window_kind} {args.window_size}")
    say("The kit keeps this threshold; the runtime has no setting for it at this pin "
        "(upstream limit). Check it with: arhugula eval drift show")
    return Exit.OK


_PRIMITIVE = Arg(
    ("--primitive",),
    "which holdout primitive",
    {"choices": HOLDOUT_PRIMITIVES, "default": HOLDOUT_PRIMITIVES[0]},
)

VERBS: tuple[Verb, ...] = (
    Verb(
        ("observability", "vm", "create"),
        "Create the deployment's own Lima VM with Docker Engine, Compose and gVisor.",
        "kit",
        _vm_create,
        example="arhugula observability vm create",
        detail=(
            "The VM lives under `<home>/lima`, is built for this machine's CPU, and sees only "
            "the Compose project and the run logs, read-only. It is the deployment's only "
            "Docker engine; Docker Desktop is not used. Allow 5 to 10 minutes."
        ),
    ),
    Verb(
        ("observability", "vm", "use"),
        "Use a Lima instance you already have instead of the kit's VM.",
        "kit",
        _vm_use,
        args=(Arg(("instance",), "the instance, as `<lima-home>::<instance>`"),),
        example="arhugula observability vm use ~/.lima::default",
        detail="The instance must be built for this machine's CPU and must see the deployment home.",
    ),
    Verb(
        ("observability", "vm", "status"),
        "Show the VM, and the Docker engine, Compose and gVisor inside it.",
        "kit",
        _vm_status,
        example="arhugula observability vm status",
    ),
    Verb(
        ("observability", "vm", "delete"),
        "Delete the kit's VM. Without --yes it only says what it would delete.",
        "kit",
        _vm_delete,
        args=(Arg(("--yes",), "really delete", {"action": "store_true"}),),
        example="arhugula observability vm delete",
    ),
    Verb(
        ("observability", "up"),
        "Start the VM and the trace stack: collector, Tempo and Grafana.",
        "kit",
        _up,
        example="arhugula observability up",
        detail=(
            "Renders the Compose project from the pinned upstream files and the kit's "
            "dashboards and alert rules, starts the VM (creating the kit's VM if it does "
            "not exist), starts the stack, and waits until Grafana, Tempo and the trace "
            "endpoint answer on loopback."
        ),
    ),
    Verb(
        ("observability", "down"),
        "Stop the trace stack and turn the tier off. Stored traces and Grafana data are kept.",
        "kit",
        _down,
        args=(
            Arg(("--stop-vm",), "also stop the VM", {"action": "store_true"}),
            Arg(("--delete-data",), "also delete the stored traces and Grafana data", {"action": "store_true"}),
        ),
        example="arhugula observability down --stop-vm",
    ),
    Verb(
        ("observability", "status"),
        "Show the VM, the containers, the loopback ports and the newest trace.",
        "kit",
        _status,
        example="arhugula observability status",
    ),
    Verb(
        ("trace", "list"),
        "List the most recent traces in the local span store.",
        "kit",
        _trace_list,
        args=(Arg(("--limit",), "how many traces", {"type": int, "default": 20, "metavar": "N"}),),
        example="arhugula trace list",
    ),
    Verb(
        ("trace", "browse"),
        "Open the runtime's terminal trace browser on the local span store.",
        "runtime",
        _trace_browse,
        example="arhugula trace browse",
    ),
    Verb(
        ("trace", "export"),
        "Write spans from the local span store as JSON lines.",
        "kit",
        _trace_export,
        args=(
            Arg(("--trace-id",), "only this trace", {"metavar": "ID"}),
            Arg(("--out",), "write to this file instead of the terminal", {"metavar": "FILE"}),
        ),
        example="arhugula trace export --out traces.jsonl",
    ),
    Verb(
        ("collector", "status"),
        "Show the local span store: where it is, how much it holds, who writes it.",
        "runtime",
        _collector_status,
        example="arhugula collector status",
    ),
    Verb(
        ("collector", "bridge", "start"),
        "Explain why no span-store bridge is needed at this pin.",
        "kit",
        _collector_bridge,
        example="arhugula collector bridge start",
        detail="Kept so that earlier instructions still lead somewhere. The runtime writes the span store itself.",
    ),
    Verb(
        ("collector", "bridge", "stop"),
        "Explain why no span-store bridge is needed at this pin.",
        "kit",
        _collector_bridge,
        example="arhugula collector bridge stop",
    ),
    Verb(
        ("logs",),
        "Show a run log: the newest one, a named one, or the list.",
        "kit",
        _logs,
        args=(
            Arg(("name",), "a log file name from `arhugula logs --list` (default: the newest)", {"nargs": "?"}),
            Arg(("--list",), "list the log files", {"action": "store_true"}),
            Arg(("--lines",), "how many lines from the end", {"type": int, "default": 60, "metavar": "N"}),
            Arg(("--collected",), "show what the collector's logs pipeline has written", {"action": "store_true"}),
        ),
        example="arhugula logs --list",
    ),
    Verb(
        ("eval", "sample"),
        "Draw a holdout set of traces from the local span store.",
        "runtime",
        _eval_sample,
        args=(
            _PRIMITIVE,
            Arg(("--count",), "how many traces to draw", {"type": int, "default": 10, "metavar": "N"}),
            Arg(("--seed",), "the sampling seed; the same seed draws the same set", {"type": int, "default": 0}),
            Arg(("--replace",), "replace an existing holdout set", {"action": "store_true"}),
        ),
        example="arhugula eval sample --count 5",
    ),
    Verb(
        ("eval", "review"),
        "Review each sampled trace and type its category. No model is called.",
        "runtime",
        _eval_review,
        args=(_PRIMITIVE,),
        example="arhugula eval review",
    ),
    Verb(
        ("eval", "scaffold"),
        "Write one assertion file per reviewed trace, for you to fill in.",
        "runtime",
        _eval_scaffold,
        args=(_PRIMITIVE,),
        example="arhugula eval scaffold",
    ),
    Verb(
        ("eval", "status"),
        "Count sampled and reviewed traces and run every assertion file.",
        "kit",
        _eval_status,
        example="arhugula eval status",
        detail="Exits 1 when an assertion fails or cannot run.",
    ),
    Verb(
        ("eval", "report"),
        "Summarize the review categories and assertion results.",
        "kit",
        _eval_report,
        args=(Arg(("--json",), "print JSON", {"action": "store_true"}),),
        example="arhugula eval report",
    ),
    Verb(
        ("eval", "drift", "show"),
        "Compare an alignment-floor primitive with its threshold.",
        "runtime",
        _drift_show,
        args=(
            Arg(("primitive",), "the primitive (default: every one with a threshold)",
                {"nargs": "?", "choices": DRIFT_PRIMITIVES}),
            Arg(("--judge-value",), "your own measured value, for a primitive spans cannot give",
                {"type": float, "metavar": "VALUE"}),
        ),
        example="arhugula eval drift show cache_hit_rate_alignment_floor",
        detail="Exits 1 when a primitive has drifted below its threshold.",
    ),
    Verb(
        ("eval", "drift", "set-threshold"),
        "Set the threshold and observation window of an alignment-floor primitive.",
        "kit",
        _drift_set,
        args=(
            Arg(("primitive",), "the primitive", {"choices": DRIFT_PRIMITIVES}),
            Arg(("value",), "the threshold value", {"type": float}),
            Arg(("--window-kind",), "a time window in seconds or a count of samples",
                {"choices": WINDOW_KINDS, "default": "TIME_WINDOW"}),
            Arg(("--window-size",), "seconds, or samples", {"type": float, "default": 86400.0, "metavar": "N"}),
        ),
        example="arhugula eval drift set-threshold cache_hit_rate_alignment_floor 0.5",
    ),
)
