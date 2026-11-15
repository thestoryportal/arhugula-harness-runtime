"""Authoring and safety verbs: prompts, skills, validators, pause, webhook, audit,
isolation and the daemon."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from arhugula_kit import daemon, deploy, isolation, overlay, render, runtime
from arhugula_kit.common import PROJECT_ARG, say, table, target_of
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.spec import WORKLOADS
from arhugula_kit.verbs import Arg, Verb
from arhugula_kit.verbs_config import SCOPE_ARG, rendered, scope_of, set_feature

# --- prompts ----------------------------------------------------------------------------

PROMPTS = ("runtime", "prompt_manifest")
SELECTION = ("runtime", "prompt_selection_manifest")
APPROVED = ("runtime", "approved_prompt_version_shas")


def _versions(deployment: Deployment, scope: str) -> list[dict[str, str]]:
    stored = overlay.get(overlay.scoped(deployment.spec, scope), (*PROMPTS, "versions"), [])
    return list(stored)


def _find(versions: list[dict[str, str]], reference: str) -> dict[str, str]:
    """A prompt version by label or by a unique prefix of its sha."""
    hits = [v for v in versions if v.get("version") == reference or v["version_sha"].startswith(reference)]
    if len(hits) != 1:
        known = ", ".join(f"{v.get('version', '?')} ({v['version_sha'][:12]})" for v in versions) or "none"
        raise KitError(
            Exit.PRECONDITION,
            f"{reference!r} names {len(hits)} authored prompt versions (authored: {known})",
            fix="arhugula prompt list",
        )
    return hits[0]


def _prompt_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    stored = overlay.scoped(deployment.spec, scope)
    versions = _versions(deployment, scope)
    if not versions:
        say("no prompt version is authored. Author one with: arhugula prompt author <label> --file <text-file>")
        return Exit.OK
    active = overlay.get(stored, (*PROMPTS, "active_prompt_version", "version_sha"), "")
    approved = set(overlay.get(stored, APPROVED, []))
    selected = overlay.get(stored, (*SELECTION, "per_workload_overrides"), {})
    by_sha: dict[str, list[str]] = {}
    for workload, binding in selected.items():
        by_sha.setdefault(binding["version_sha"], []).append(workload)
    table(
        [
            (
                v.get("version", "-"),
                v["version_sha"][:12],
                "active" if v["version_sha"] == active else "",
                "approved" if v["version_sha"] in approved else "",
                ",".join(by_sha.get(v["version_sha"], [])) or "-",
                v["content"].replace("\n", " ")[:50],
            )
            for v in versions
        ],
        header=("label", "sha", "", "", "selected for", "content"),
    )
    return Exit.OK


def _prompt_author(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    content = Path(args.file).expanduser().read_text(encoding="utf-8").strip()
    if not content:
        raise KitError(Exit.USAGE, f"{args.file} is empty")
    sha = runtime.call(deployment.home, "prompt-sha", content=content)["version_sha"]
    versions = _versions(deployment, scope)
    if any(v["version_sha"] == sha for v in versions):
        raise KitError(Exit.PRECONDITION, f"this exact text is already authored ({sha[:12]})")
    if any(v.get("version") == args.label for v in versions):
        raise KitError(Exit.PRECONDITION, f"the label {args.label!r} is already used; choose another")
    entry = {"version_sha": sha, "content": content, "version": args.label}
    spec = overlay.set_value(deployment.spec, scope, (*PROMPTS, "manifest_version"), 1)
    spec = overlay.set_value(spec, scope, (*PROMPTS, "versions"), [*versions, entry])
    if args.activate or not versions:
        spec = overlay.set_value(spec, scope, (*PROMPTS, "active_prompt_version"), entry)
    deploy.apply(deployment, spec)
    say(f"authored prompt version {args.label}: {sha}")
    say("active" if args.activate or not versions else f"not active; activate it with: arhugula prompt activate {args.label}")
    return Exit.OK


def _prompt_activate(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    version = _find(_versions(deployment, scope), args.version)
    deploy.apply(
        deployment,
        overlay.set_value(deployment.spec, scope, (*PROMPTS, "active_prompt_version"), version),
    )
    say(f"active prompt version: {version.get('version', '-')} ({version['version_sha'][:12]})")
    return Exit.OK


def _prompt_select(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    version = _find(_versions(deployment, scope), args.version)
    spec = overlay.set_value(deployment.spec, scope, (*SELECTION, "manifest_version"), 1)
    spec = overlay.set_value(
        spec, scope, (*SELECTION, "per_workload_overrides", args.workload),
        {"version_sha": version["version_sha"]},
    )
    deploy.apply(deployment, spec)
    say(f"workload {args.workload} uses prompt version {version.get('version', '-')} "
        f"({version['version_sha'][:12]})")
    return Exit.OK


def _prompt_approve(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    version = _find(_versions(deployment, scope), args.version)
    approved = list(overlay.get(overlay.scoped(deployment.spec, scope), APPROVED, []))
    if version["version_sha"] not in approved:
        approved.append(version["version_sha"])
    deploy.apply(deployment, overlay.set_value(deployment.spec, scope, APPROVED, approved))
    say(f"approved prompt version {version.get('version', '-')} ({version['version_sha'][:12]})")
    return Exit.OK


def _prompt_diff(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    versions = _versions(deployment, scope_of(deployment, args.project))
    first, second = _find(versions, args.first), _find(versions, args.second)
    lines = difflib.unified_diff(
        first["content"].splitlines(),
        second["content"].splitlines(),
        fromfile=f"{first.get('version', '-')} {first['version_sha'][:12]}",
        tofile=f"{second.get('version', '-')} {second['version_sha'][:12]}",
        lineterm="",
    )
    say("\n".join(lines) or "the two versions have the same text")
    return Exit.OK


# --- skills -----------------------------------------------------------------------------


def _skills_dir(target: render.Target) -> Path:
    return target.repository / ".agents" / "skills"


def _skill_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    directory = _skills_dir(target)
    if not directory.is_dir():
        say(f"{target.label} has no skills directory yet ({directory}).")
        return Exit.OK
    listing = runtime.call(deployment.home, "skills-load", directory=str(directory))
    say(f"{directory}: {len(listing['skills'])} skill(s) load in the runtime")
    table(
        [(s["skill_id"], s["version_sha"][:12], str(s["body_tokens"])) for s in listing["skills"]],
        header=("skill", "content sha", "tokens"),
    )
    hook = deployment.spec.skill_hook or "none: no skill is activated in a run"
    say(f"\nactivation hook: {hook}")
    return Exit.OK


def _skill_add(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    source = Path(args.source).expanduser().resolve()
    manifests = sorted(source.glob("*.skill.json")) if source.is_dir() else []
    if not manifests:
        raise KitError(
            Exit.PRECONDITION,
            f"{source} holds no `<name>.skill.json`. A skill is two files: `<name>.skill.json` "
            "and `<name>.SKILL.md`",
            fix="see docs/authoring.md, section `Write a skill`",
        )
    directory = _skills_dir(target)
    directory.mkdir(parents=True, exist_ok=True)
    for manifest in manifests:
        content = manifest.with_name(manifest.name.replace(".skill.json", ".SKILL.md"))
        if not content.is_file():
            raise KitError(Exit.PRECONDITION, f"{manifest.name} has no matching {content.name}")
        for path in (manifest, content):
            if (directory / path.name).exists():
                raise KitError(Exit.PRECONDITION, f"{directory / path.name} already exists")
        for path in (manifest, content):
            shutil.copy2(path, directory / path.name)
            say(f"copied {path.name} -> {directory}")
    listing = runtime.call(deployment.home, "skills-load", directory=str(directory))
    say(f"{len(listing['skills'])} skill(s) now load from {directory}")
    return Exit.OK


def _skill_validate(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    directory = (
        Path(args.directory).expanduser().resolve()
        if args.directory
        else _skills_dir(target_of(deployment, args.project))
    )
    match runtime.ask(deployment.home, "skills-load", directory=str(directory)):
        case runtime.Refusal(kind=kind, message=message):
            raise KitError(Exit.RUNTIME_REFUSED, f"{directory} does not load ({kind}): {message}")
        case listing:
            say(f"{directory}: {len(listing['skills'])} skill(s) load in the runtime")
            for skill in listing["skills"]:
                say(f"  {skill['skill_id']} ({skill['body_tokens']} tokens)")
    return Exit.OK


def _skill_hook_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    name = "arhugula_kit.skillhooks:EverySkill" if args.hook == "every" else args.hook
    if ":" not in name:
        raise KitError(Exit.USAGE, "give the hook as `module:Class`, or `every` for the kit's hook")
    deploy.apply(deployment, replace(deployment.spec, skill_hook=name))
    say(f"skill-activation hook: {name}")
    say("`arhugula run` now passes this hook to the runtime (a kit extension; see docs/authoring.md).")
    return Exit.OK


def _skill_hook_clear(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    deploy.apply(deployment, replace(deployment.spec, skill_hook=""))
    say("skill-activation hook: none")
    return Exit.OK


# --- validators -------------------------------------------------------------------------

BINDINGS = ("runtime", "validator_framework_config", "bindings")


def _bindings(deployment: Deployment, scope: str) -> list[dict[str, Any]]:
    return list(overlay.get(overlay.scoped(deployment.spec, scope), BINDINGS, []))


def python_paths(deployment: Deployment, target: render.Target) -> list[str]:
    """Directories the runtime must import from: the project's validators/ and skills/
    directories, then any the operator added."""
    conventional = [target.repository / "validators", target.repository / "skills"]
    return [str(p) for p in conventional if p.is_dir()] + list(deployment.spec.python_paths)


def _validator_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    bindings = _bindings(deployment, scope)
    if not bindings:
        say("no validator is bound. Bind one with: arhugula validator bind <step-id> <module:Class>")
        return Exit.OK
    table(
        [(b["step_id"], b["class_qualified_name"], json.dumps(b.get("params", {}))) for b in bindings],
        header=("step", "class", "params"),
    )
    return Exit.OK


def _validator_bind(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    params: dict[str, Any] = {}
    for item in args.param or ():
        key, separator, raw = item.partition("=")
        if not separator:
            raise KitError(Exit.USAGE, f"--param takes key=value (got {item!r})")
        try:
            params[key] = json.loads(raw)
        except ValueError:
            params[key] = raw
    spec = deployment.spec
    if args.pythonpath:
        added = str(Path(args.pythonpath).expanduser().resolve())
        spec = replace(spec, python_paths=tuple(dict.fromkeys((*spec.python_paths, added))))
    target = deployment.target(scope or None)
    checked = runtime.ask(
        deployment.home,
        "validator-inspect",
        class_qualified_name=args.class_name,
        params=params,
        python_paths=python_paths(replace(deployment, spec=spec), target),
    )
    if isinstance(checked, runtime.Refusal):
        raise KitError(
            Exit.PRECONDITION,
            f"{args.class_name} cannot be used ({checked.kind}): {checked.message}",
            fix="put the module in the project's validators/ directory, or pass --pythonpath <dir>",
        )
    kept = [b for b in _bindings(deployment, scope) if b["step_id"] != args.step]
    binding = {"step_id": args.step, "class_qualified_name": args.class_name, "params": params}
    deploy.apply(deployment, overlay.set_value(spec, scope, BINDINGS, [*kept, binding]))
    say(f"step {args.step} is validated by {checked['class']}")
    return Exit.OK


def _validator_unbind(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    scope = scope_of(deployment, args.project)
    bindings = _bindings(deployment, scope)
    kept = [b for b in bindings if b["step_id"] != args.step]
    if len(kept) == len(bindings):
        raise KitError(Exit.PRECONDITION, f"no validator is bound to step {args.step!r}")
    changed = (
        overlay.set_value(deployment.spec, scope, BINDINGS, kept)
        if kept
        else overlay.dropped(deployment.spec, scope, ("runtime", "validator_framework_config"))
    )
    deploy.apply(deployment, changed)
    say(f"step {args.step}: no validator")
    return Exit.OK


def _validator_test(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    bindings = rendered(deployment, target.name).get("validator_framework_config", {}).get("bindings", [])
    if not bindings:
        say(f"{target.label} binds no validator.")
        return Exit.OK
    failures = 0
    for binding in bindings:
        checked = runtime.ask(
            deployment.home,
            "validator-inspect",
            class_qualified_name=binding["class_qualified_name"],
            params=binding.get("params", {}),
            python_paths=python_paths(deployment, target),
        )
        if isinstance(checked, runtime.Refusal):
            failures += 1
            say(f"FAIL  {binding['step_id']}: {binding['class_qualified_name']} ({checked.kind}): {checked.message}")
        else:
            say(f"ok    {binding['step_id']}: {checked['class']} imports, constructs, and has `validate`")
    if failures:
        raise KitError(Exit.PRECONDITION, f"{failures} bound validator(s) would fail at bootstrap")
    return Exit.OK


# --- pause, webhook ---------------------------------------------------------------------


def _pause_enable(args: argparse.Namespace) -> int:
    deployment = set_feature(deploy.open_deployment(), "durable-pause", True)
    say("durable pause: on. A run you put on hold at a gate is journalled, and "
        "`arhugula gate approve` or `arhugula resume` continues it later.")
    if "webhook_delivery_composer_config" not in rendered(deployment):
        say("To answer `hold` at a gate the runtime also needs somewhere to send the "
            "notification: arhugula webhook set <url>")
    return Exit.OK


def _pause_disable(args: argparse.Namespace) -> int:
    set_feature(deploy.open_deployment(), "durable-pause", False)
    say("durable pause: off.")
    return Exit.OK


def journals(deployment: Deployment, target: render.Target) -> dict[str, Any]:
    """The runtime's own read-only listing of pause journals."""
    outcome = runtime.run_tool(
        deployment.home.harness_inspect,
        [
            "--ledger-path", target.state / "state-ledger" / "state.jsonl",
            "--runtime-config", target.config_file,
            "--pause-journal-dir", deployment.home.pause_journal,
            "--json",
        ],
        cwd=target.repository,
    )
    try:
        return json.loads(outcome.stdout)
    except ValueError:
        raise KitError(Exit.RUNTIME_REFUSED, f"harness-inspect gave no listing:\n{outcome.last_lines()}") from None


def _pause_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    listing = journals(deployment, target)
    found = listing.get("pause_journals", [])
    say(f"pause journals: {listing.get('pause_journal_count', len(found))}")
    for journal in found:
        say(f"  {json.dumps(journal, sort_keys=True)}")
    say(f"\nupstream limit: {listing.get('pause_journal_upper_bound_disclaimer', '')}")
    return Exit.OK


def _journal_tool(args: argparse.Namespace, command: str, extra: list[str]) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    tenant = ["--tenant-id", target.tenant_id] if target.tenant_id else []
    return runtime.exec_tool(
        deployment.home.harness,
        [command, deployment.home.pause_journal, *tenant, *extra],
        cwd=target.repository,
    )


def _pause_adopt(args: argparse.Namespace) -> int:
    return _journal_tool(args, "adopt-pause-journals", [])


def _pause_dispose(args: argparse.Namespace) -> int:
    extra = ["--delete"] if args.delete else []
    if args.acknowledge_discarding_recoverable_state:
        extra.append("--acknowledge-discarding-recoverable-state")
    return _journal_tool(args, "dispose-pause-journals", extra)


WEBHOOK = ("runtime", "webhook_delivery_composer_config")


def _webhook_set(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    entry = {"webhook_id": args.id, "endpoint_url": args.url, "timeout_seconds": args.timeout}
    deploy.apply(deployment, overlay.set_value(deployment.spec, "", WEBHOOK, entry))
    say(f"webhook {args.id}: {args.url} (timeout {args.timeout} s)")
    return Exit.OK


def _webhook_clear(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    deploy.apply(deployment, overlay.dropped(deployment.spec, "", WEBHOOK))
    say("webhook: none")
    return Exit.OK


# --- audit ------------------------------------------------------------------------------

SIGNING_KEY_IDS = ("harness-runtime-dev", "harness-cost-attribution-v1")
PRIVATE_KEY = "audit-ed25519.pem"
PUBLIC_KEY = "audit-ed25519.pub.pem"
RECORD_KEY = render.RECORD_KEY
RECORD_PUBLIC_KEY = "audit-cutover-ed25519.pub.pem"
RECORD_KEY_ID = render.RECORD_KEY_ID
KEY_MAP = "signing-key-map.json"


def _audit_keygen(args: argparse.Namespace) -> int:
    """Two keys: one signs audit entries, the other signs each ledger's cutover record.

    The runtime requires the record key to be different key material from the entry key,
    so that a leaked entry key cannot rewrite which entries a ledger must hold.
    """
    deployment = deploy.open_deployment()
    keys = deployment.home.keys
    keys.mkdir(mode=0o700, exist_ok=True)
    keys.chmod(0o700)
    entry = runtime.call(
        deployment.home, "audit-keygen", private=str(keys / PRIVATE_KEY), public=str(keys / PUBLIC_KEY)
    )
    record = runtime.call(
        deployment.home, "audit-keygen", private=str(keys / RECORD_KEY), public=str(keys / RECORD_PUBLIC_KEY)
    )
    key_map = {
        **{
            f"ed25519:{key_id}": {
                "kind": "local-ed25519-public",
                "public_key_path": PUBLIC_KEY,
                "spki_sha256": entry["identity"],
            }
            for key_id in SIGNING_KEY_IDS
        },
        f"ed25519:{RECORD_KEY_ID}": {
            "kind": "local-ed25519-public",
            "public_key_path": RECORD_PUBLIC_KEY,
            "spki_sha256": record["identity"],
        },
    }
    (keys / KEY_MAP).write_text(json.dumps(key_map, indent=2) + "\n", encoding="utf-8")
    say(f"wrote {keys / PRIVATE_KEY} (mode 0600): signs every audit entry.")
    say(f"wrote {keys / RECORD_KEY} (mode 0600): signs each ledger's cutover record.")
    say(f"wrote the two public keys and {keys / KEY_MAP}: what `audit verify --signatures` reads.")
    say("Back up both private keys; they are in no archive.")
    say("next: arhugula audit enable")
    return Exit.OK


def _audit_enable(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    missing = [name for name in (PRIVATE_KEY, RECORD_KEY) if not (deployment.home.keys / name).is_file()]
    if missing:
        raise KitError(
            Exit.PRECONDITION,
            f"there is no {' and no '.join(missing)} under {deployment.home.keys}",
            fix="arhugula audit keygen",
        )
    deployment = set_feature(deployment, "audit-signing", True)
    before = [
        t for t in render.targets(deployment.spec, deployment.home)
        if t.name not in deployment.spec.cutover_ledgers
    ]
    say("audit signing: on. Every audit entry of every later run is signed with the local key.")
    if before:
        say("")
        say("These ledgers already hold entries written before signing was on:")
        for target in before:
            say(f"  {target.label}")
        say("Their new entries are signed, but an earlier unsigned entry never verifies, so")
        say("`audit verify --signatures` is not available for them; `audit verify` checks")
        say("their hash chain. A project attached from now on is signed from its first")
        say("entry and verifies in full.")
    return Exit.OK


def _audit_disable(args: argparse.Namespace) -> int:
    set_feature(deploy.open_deployment(), "audit-signing", False)
    say("audit signing: off. Entries already written keep their signatures.")
    say("Entries written from now on are unsigned, and a ledger that holds them no longer "
        "passes `audit verify --signatures`.")
    return Exit.OK


def _audit_status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    keys = deployment.home.keys
    signing = rendered(deployment).get("audit_signing", {})
    say(f"backend:     {signing.get('backend', 'none')}")
    for label, name in (("entry key", PRIVATE_KEY), ("record key", RECORD_KEY), ("key map", KEY_MAP)):
        say(f"{label + ':':12} {'present' if (keys / name).is_file() else 'absent'} ({keys / name})")
    say("")
    rows = []
    for target in render.targets(deployment.spec, deployment.home):
        sidecar = target.state / "state-ledger" / "audit-entries.jsonl"
        count = sum(1 for _ in sidecar.open("rb")) if sidecar.is_file() else 0
        if target.name not in deployment.spec.cutover_ledgers:
            verifies = "hash chain only" + (": it began unsigned" if signing else ": signing is off")
        elif render.cutover_record(target).is_file():
            verifies = "in full: signed from its first entry"
        else:
            verifies = "in full, from its first run (the runtime writes its cutover record then)"
        rows.append((target.label, str(count), verifies))
    table(rows, header=("project", "audit entries", "verifies"))
    return Exit.OK


def _audit_verify(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    words: list[str | Path] = [
        "--ledger-path", target.state / "state-ledger" / "state.jsonl",
        "--runtime-config", target.config_file,
        "--pause-journal-dir", deployment.home.pause_journal,
        "--last-n", str(args.last_n),
    ]
    if args.signatures:
        key_map, record = deployment.home.keys / KEY_MAP, render.cutover_record(target)
        if not key_map.is_file():
            raise KitError(Exit.PRECONDITION, f"there is no key map at {key_map}", fix="arhugula audit keygen")
        if not record.is_file():
            raise KitError(
                Exit.PRECONDITION,
                f"{target.label} has no cutover record ({record}). The runtime writes it at the "
                "first run of a ledger while signing is on; a ledger that began unsigned has none "
                "and cannot be signature-verified",
                fix="check the hash chain with `arhugula audit verify`; turn signing on before a "
                "project's first run to have it verify in full",
            )
        words += ["--signing-key-map", key_map, "--cutover-record", record]
        if target.tenant_id:
            words += ["--expected-tenant", target.tenant_id]
    code = runtime.exec_tool(deployment.home.harness_inspect, words, cwd=target.repository)
    checked = "the hash chain is intact and every entry's signature verified" if args.signatures else (
        "the hash chain is intact (signatures were not checked; add --signatures)")
    meaning = {
        0: checked,
        3: "UNVERIFIED: the inspector lacked an input it needs; its message above names it",
        4: "verification ran and FAILED; the message above names the entry",
    }
    say(f"\nharness-inspect exit {code}: {meaning.get(code, 'see the message above')}")
    return code


def _audit_migrate(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    return runtime.exec_tool(
        deployment.home.harness,
        ["migrate-audit-sidecar", target.state / "state-ledger" / "state.jsonl", *args.passthrough],
        cwd=target.repository,
    )


# --- isolation --------------------------------------------------------------------------


def _isolation_show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    wrapper = isolation.wrapper_path(deployment.home)
    say("tier 1 (host process): the default for every tool call on this deployment.")
    say(f"tier 3 (gVisor in the Lima VM): {'enabled' if deployment.spec.isolation_tier3 else 'not enabled'}")
    if wrapper.is_file():
        say(f"  container CLI: {wrapper}")
    for client in overlay.get(deployment.spec.overlay, ("runtime", "mcp_clients"), []):
        driver = client.get("sandbox_driver")
        state = f"tier 3, image {driver['image']}" if driver else "no sandbox driver"
        say(f"  MCP client {client['client_name']} ({client['transport']}): {state}")
    say("tiers 2 and 4 are outside this deployment (see docs/security-and-isolation.md).")
    return Exit.OK


def _isolation_enable(args: argparse.Namespace) -> int:
    isolation.enable_tier3(deploy.open_deployment(), out=say)
    say("isolation tier 3: enabled")
    return Exit.OK


def _isolation_attach(args: argparse.Namespace) -> int:
    try:
        command = json.loads(args.command)
    except ValueError as exc:
        raise KitError(Exit.USAGE, f'--command takes a JSON array, for example \'["python","/runner.py"]\': {exc}') from exc
    isolation.attach(deploy.open_deployment(), args.client, args.image, command)
    say(f"MCP client {args.client} now runs its tools under gVisor in image {args.image}.")
    return Exit.OK


def _isolation_disable(args: argparse.Namespace) -> int:
    isolation.disable(deploy.open_deployment())
    say("isolation tier 3: disabled. The sandboxed echo client and every tier-3 driver are removed.")
    return Exit.OK


# --- daemon -----------------------------------------------------------------------------


def _daemon_start(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    pid = daemon.start(deployment, target)
    say(f"daemon for {target.label}: pid {pid}")
    say(f"  socket: {daemon.socket_path(deployment.home, target)}")
    say(f"  log:    {daemon.log_path(deployment.home, target)}")
    say("send it a run with: arhugula run <manifest> --daemon")
    return Exit.OK


def _daemon_stop(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    stopped = daemon.stop(deployment, target)
    say(f"daemon for {target.label}: {'stopped' if stopped else 'was not running'}")
    return Exit.OK


def _daemon_status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    rows = []
    for target in render.targets(deployment.spec, deployment.home):
        pid = daemon.pid_of(deployment.home, target)
        rows.append(
            (
                target.label,
                f"running (pid {pid})" if pid else "not running",
                str(daemon.socket_path(deployment.home, target)) if pid else "-",
            )
        )
    table(rows, header=("project", "daemon", "socket"))
    return Exit.OK


def _daemon_expose(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    socket = daemon.socket_path(deployment.home, target)
    state = "running" if daemon.pid_of(deployment.home, target) else "not running; start it with `arhugula daemon start`"
    say(f"daemon for {target.label}: {state}")
    say(f"MCP endpoint (streamable HTTP over a Unix socket): {socket}")
    say("tool: run_workflow(workflow_id)")
    say("\nAn agent CLI in the project reaches the harness most simply through this command:")
    say(f"  {deployment.home.bin / 'arhugula'} run <manifest> --project {target.name or 'default'} --daemon")
    say("\nUpstream limit: MCP clients such as Claude Code connect over stdio or TCP HTTP, not a Unix")
    say("socket, so `claude mcp add` cannot point at this endpoint directly at this pin.")
    return Exit.OK


VERSION_ARG = Arg(("version",), "a version's label, or the start of its sha")

VERBS: tuple[Verb, ...] = (
    Verb(("prompt", "list"), "List authored prompt versions and where each is used.", "runtime", _prompt_list, (SCOPE_ARG,), example="arhugula prompt list"),
    Verb(
        ("prompt", "author"),
        "Author a prompt version from a text file.",
        "runtime",
        _prompt_author,
        (
            Arg(("label",), "a label for this version, for example v2"),
            Arg(("--file",), "the text file that holds the prompt", {"required": True}),
            Arg(("--activate",), "make it the active version", {"action": "store_true"}),
            SCOPE_ARG,
        ),
        example="arhugula prompt author v1 --file prompts/system.md",
        detail="A version is identified by the sha256 of its text. The first version authored becomes active.",
    ),
    Verb(("prompt", "activate"), "Make an authored version the active prompt.", "runtime", _prompt_activate, (VERSION_ARG, SCOPE_ARG), example="arhugula prompt activate v2"),
    Verb(
        ("prompt", "select"),
        "Use an authored version for one workload class.",
        "runtime",
        _prompt_select,
        (Arg(("workload",), "the workload class", {"choices": WORKLOADS}), VERSION_ARG, SCOPE_ARG),
        example="arhugula prompt select research v2",
    ),
    Verb(("prompt", "approve"), "Record an authored version as approved.", "runtime", _prompt_approve, (VERSION_ARG, SCOPE_ARG), example="arhugula prompt approve v2"),
    Verb(
        ("prompt", "diff"),
        "Show the text difference between two authored versions.",
        "kit",
        _prompt_diff,
        (Arg(("first",), "a version's label or sha prefix"), Arg(("second",), "a version's label or sha prefix"), SCOPE_ARG),
        example="arhugula prompt diff v1 v2",
    ),
    Verb(("skill", "list"), "List the skills that load from the current project.", "runtime", _skill_list, (PROJECT_ARG,), example="arhugula skill list"),
    Verb(
        ("skill", "add"),
        "Copy a skill's two files into the current project's skills directory.",
        "kit",
        _skill_add,
        (Arg(("source",), "a directory holding `<name>.skill.json` and `<name>.SKILL.md`"), PROJECT_ARG),
        example="arhugula skill add ~/skills/haiku",
    ),
    Verb(
        ("skill", "validate"),
        "Load a skills directory through the runtime's loader.",
        "runtime",
        _skill_validate,
        (Arg(("directory",), "the directory to check (default: the current project's)", {"nargs": "?"}), PROJECT_ARG),
        example="arhugula skill validate",
    ),
    Verb(
        ("skill", "hook", "set"),
        "Choose the hook that decides which skills a run activates.",
        "kit",
        _skill_hook_set,
        (Arg(("hook",), "`module:Class`, or `every` to activate every loaded skill"),),
        example="arhugula skill hook set every",
        detail=(
            "The runtime accepts a hook only as a Python object, which a config file cannot "
            "carry. With a hook set, `arhugula run` starts the runtime's own CLI with the hook "
            "attached."
        ),
    ),
    Verb(("skill", "hook", "clear"), "Remove the skill-activation hook.", "kit", _skill_hook_clear, example="arhugula skill hook clear"),
    Verb(("validator", "list"), "List the validators bound to workflow steps.", "runtime", _validator_list, (SCOPE_ARG,), example="arhugula validator list"),
    Verb(
        ("validator", "bind"),
        "Bind a validator class to a step id.",
        "runtime",
        _validator_bind,
        (
            Arg(("step",), "the step id the validator checks"),
            Arg(("class_name",), "the class, as `module:Class`", {"metavar": "module:Class"}),
            Arg(("--param",), "a constructor parameter as key=value; repeat for several", {"action": "append"}),
            Arg(("--pythonpath",), "a directory to import the module from (default: the project's validators/)"),
            SCOPE_ARG,
        ),
        example="arhugula validator bind review-step my_validators:MaxChars --param max_chars=200",
        detail="The class is imported and constructed before the binding is stored, so a bad class is refused here.",
    ),
    Verb(("validator", "unbind"), "Remove the validator from a step.", "runtime", _validator_unbind, (Arg(("step",), "the step id"), SCOPE_ARG), example="arhugula validator unbind review-step"),
    Verb(
        ("validator", "test"),
        "Import and construct every bound validator. No provider is called.",
        "kit",
        _validator_test,
        (PROJECT_ARG,),
        example="arhugula validator test",
    ),
    Verb(("pause", "enable"), "Turn durable pause and resume on.", "runtime", _pause_enable, example="arhugula pause enable"),
    Verb(("pause", "disable"), "Turn durable pause and resume off.", "runtime", _pause_disable, example="arhugula pause disable"),
    Verb(("pause", "list"), "List the pause journals the runtime finds.", "runtime", _pause_list, (PROJECT_ARG,), example="arhugula pause list"),
    Verb(
        ("pause", "adopt"),
        "Adopt legacy untenanted pause journals into the project's tenant.",
        "runtime",
        _pause_adopt,
        (PROJECT_ARG,),
        example="arhugula pause adopt --project my-service",
    ),
    Verb(
        ("pause", "dispose"),
        "Report, or with --delete remove, orphaned legacy pause journals.",
        "runtime",
        _pause_dispose,
        (
            PROJECT_ARG,
            Arg(("--delete",), "really remove; without it nothing is removed", {"action": "store_true"}),
            Arg(
                ("--acknowledge-discarding-recoverable-state",),
                "proceed although an adoption could still recover some journals",
                {"action": "store_true"},
            ),
        ),
        example="arhugula pause dispose",
    ),
    Verb(
        ("webhook", "set"),
        "Deliver pause notifications to a URL.",
        "runtime",
        _webhook_set,
        (
            Arg(("url",), "the endpoint that receives the notification"),
            Arg(("--id",), "a name for the webhook (default: local-approval)", {"default": "local-approval"}),
            Arg(("--timeout",), "seconds to wait for the endpoint, 1 to 5 (default: 3)", {"type": int, "default": 3}),
        ),
        example="arhugula webhook set http://127.0.0.1:8723/hitl",
    ),
    Verb(("webhook", "clear"), "Stop delivering pause notifications.", "runtime", _webhook_clear, example="arhugula webhook clear"),
    Verb(("audit", "keygen"), "Create the local Ed25519 signing key.", "kit", _audit_keygen, example="arhugula audit keygen", detail="The runtime ships no key generator. The key is never overwritten."),
    Verb(("audit", "enable"), "Sign every audit entry with the local key.", "runtime", _audit_enable, example="arhugula audit enable"),
    Verb(("audit", "disable"), "Stop signing new audit entries.", "runtime", _audit_disable, example="arhugula audit disable"),
    Verb(("audit", "status"), "Show the signing backend, the key files and each ledger's audit entries.", "kit", _audit_status, example="arhugula audit status"),
    Verb(
        ("audit", "verify"),
        "Verify a project's audit ledger with the runtime's inspector.",
        "runtime",
        _audit_verify,
        (
            PROJECT_ARG,
            Arg(("--last-n",), "how many recent entries to print (default: 5)", {"type": int, "default": 5}),
            Arg(("--signatures",), "also verify every entry's signature and the ledger's cutover record", {"action": "store_true"}),
        ),
        example="arhugula audit verify --signatures",
    ),
    Verb(
        ("audit", "migrate-sidecar"),
        "Run the runtime's one-time audit sidecar migration on a project's ledger.",
        "runtime",
        _audit_migrate,
        (PROJECT_ARG,),
        example="arhugula audit migrate-sidecar",
        passthrough=True,
        detail="Needed only for a ledger written before the audit sidecar existed.",
    ),
    Verb(("isolation", "show"), "Show which isolation tiers are in use.", "runtime", _isolation_show, example="arhugula isolation show"),
    Verb(
        ("isolation", "enable"),
        "Enable tier 3: tools run under gVisor in the Lima VM.",
        "runtime",
        _isolation_enable,
        (Arg(("tier",), "the tier to enable", {"choices": ("tier-3",)}),),
        example="arhugula isolation enable tier-3",
    ),
    Verb(
        ("isolation", "attach"),
        "Give one of your MCP clients a tier-3 sandbox.",
        "runtime",
        _isolation_attach,
        (
            Arg(("client",), "the MCP client"),
            Arg(("--image",), "the container image that holds the tool runner", {"required": True}),
            Arg(("--command",), "the in-container runner, as a JSON array", {"required": True}),
        ),
        example="""arhugula isolation attach files --image python:3.12-alpine --command '["python","/runner.py"]'""",
        detail="The runner reads one MCP request as JSON on stdin and writes one MCP result as JSON on stdout.",
    ),
    Verb(("isolation", "disable"), "Disable tier 3 and remove its drivers.", "runtime", _isolation_disable, example="arhugula isolation disable"),
    Verb(("daemon", "start"), "Start the harness daemon for a project.", "runtime", _daemon_start, (PROJECT_ARG,), example="arhugula daemon start"),
    Verb(("daemon", "stop"), "Ask a project's daemon to drain and exit.", "runtime", _daemon_stop, (PROJECT_ARG,), example="arhugula daemon stop"),
    Verb(("daemon", "status"), "Show which projects have a running daemon.", "runtime", _daemon_status, example="arhugula daemon status"),
    Verb(("daemon", "expose"), "Print how to reach a project's daemon.", "kit", _daemon_expose, (PROJECT_ARG,), example="arhugula daemon expose"),
)
