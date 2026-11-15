"""Lifecycle verbs: init, doctor, upgrade, relocate, uninstall."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from arhugula_kit import dependencies, deploy, detect, initflow, lima, preflight, spec, vm
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home
from arhugula_kit.preflight import Stage, Subject
from arhugula_kit.verbs import Arg, Verb


def _doctor(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    if args.self_test:
        from arhugula_kit import selftest

        return selftest.run(deployment)
    raw = json.loads(deployment.home.spec_file.read_text(encoding="utf-8"))
    print("Surveying this machine (nothing is changed)...")
    machine = detect.survey(
        deployment.home,
        ollama_host=deployment.spec.ollama_host,
        lima_home=deployment.spec.observability.lima_home or None,
        added=spec.enabled_custom(raw),
    )
    print("\nDependencies:")
    for index, (dependency, state) in enumerate(dependencies.report(machine, deployment.home), start=1):
        word = "ok" if state.ready else ("MISSING" if dependency.need is dependencies.Need.REQUIRED else "absent")  # noqa: E501
        print(f"  {word:7}  D{index:<2} {dependency.title}: {state.detail}")
        if not state.ready:
            for setup in dependency.setup:
                print(f"           set it up: {setup.command}")
    print("\nPreflight:")
    subject = Subject(machine, raw, deployment.home)
    results = [
        result
        for stage in (Stage.MACHINE, Stage.INSTALLED, Stage.GENERATED)
        for result in preflight.run_stage(stage, subject)
    ]
    preflight.report(results, consequence="doctor changes nothing")
    print("\nEvery check passed or is a warning.")
    return Exit.OK


def _reverify_under_uv(home: Home, *flags: str) -> int:
    """Hand over to `init`, which runs outside the environment it is about to replace."""
    program = str(home.kit / "init")
    sys.stdout.flush()  # what was printed so far must not be lost when this process is replaced
    os.execv(program, [program, "--reverify", *flags])


def _stack_is_up(deployment: deploy.Deployment) -> bool:
    from arhugula_kit import observability

    return observability.is_up(deployment)


def _refuse_while_daemon_runs(deployment: deploy.Deployment, action: str) -> None:
    """The environment is about to be replaced; a daemon running from it must stop first."""
    from arhugula_kit import daemon

    running = daemon.running(deployment.home)
    if running:
        raise KitError(
            Exit.PRECONDITION,
            f"a harness daemon is running (pid {', '.join(str(p) for p in running)}); "
            f"stop it before you {action}",
            fix="arhugula daemon stop",
        )


def _refuse_while_vm_runs(deployment: deploy.Deployment, action: str) -> None:
    """The home is about to move or go; the VM's disk and the stack's files live under it."""
    machine = lima.find(vm.kit_ref(deployment.home))
    if (machine is not None and machine.running) or _stack_is_up(deployment):
        raise KitError(
            Exit.PRECONDITION,
            f"the virtual machine or the observability stack is running from this home; "
            f"stop them before you {action}",
            fix="arhugula observability down --stop-vm",
        )


def _relocate(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    old = deployment.home
    new = Home(Path(args.new_home).expanduser().resolve())
    if new.root == old.root:
        raise KitError(Exit.USAGE, "the new home is the current home")
    if new.root.exists() and any(new.root.iterdir()):
        raise KitError(Exit.PRECONDITION, f"{new.root} exists and is not empty")
    above = detect.checkout_above(new.root.parent)
    if above is not None:
        raise KitError(
            Exit.PRECONDITION,
            f"{new.root} would be inside the git checkout at {above}; the runtime refuses a "
            "state root there (inside-checkout)",
        )
    if not new.root.parent.is_dir():
        raise KitError(Exit.PRECONDITION, f"{new.root.parent} does not exist")
    _refuse_while_daemon_runs(deployment, "relocate")
    _refuse_while_vm_runs(deployment, "relocate")
    if lima.find(vm.kit_ref(old)) is not None and lima.socket_path_budget(new.lima, vm.kit_ref(new).name) < 0:
        raise KitError(
            Exit.PRECONDITION,
            f"{new.root} is too long a path for the virtual machine: macOS limits a socket "
            "path to 104 bytes and Lima keeps its sockets under the home",
            fix="choose a new home with a shorter path",
        )
    print(f"Moving {old.root} to {new.root} ...")
    if new.root.exists():
        new.root.rmdir()
    shutil.move(str(old.root), str(new.root))
    print("Moved. Rebuilding the environment and regenerating every config for the new path.")
    print("The trace stack stays down after a move; start it with: arhugula observability up")
    return _reverify_under_uv(new, "--reinstall")


def _upgrade(args: argparse.Namespace) -> int:
    """Move to another pin. The environment in use stays until the new one is built.

    `bin/install.sh` builds the new pin and passes upstream's packaging gate before it
    touches the environment, keeps the earlier one at `env.rollback`, and puts it back if
    the new one cannot be completed. The PIN file changes only after that succeeded.
    """
    deployment = deploy.open_deployment()
    home = deployment.home
    pin_file = home.kit / "PIN"
    # What is installed, not what the PIN file says: after a `git pull` of the kit the
    # file already names the new commit while the environment is still the earlier one.
    installed = home.env / ".arhugula-pin"
    current = (installed if installed.is_file() else pin_file).read_text(encoding="utf-8").strip()
    rollback = home.root / "env.rollback"
    installer = str(home.kit / "bin" / "install.sh")
    if args.rollback:
        record = rollback / ".arhugula-pin"
        if not record.is_file():
            raise KitError(
                Exit.PRECONDITION,
                f"there is no complete earlier environment at {rollback} to return to",
                fix="arhugula upgrade --pin <sha> installs any commit again",
            )
        if not home.env.is_dir():
            raise KitError(
                Exit.PRECONDITION,
                f"there is no environment at {home.env} to replace",
                fix=f"run {home.kit / 'init'} --reverify --reinstall",
            )
        previous = record.read_text(encoding="utf-8").strip()
        _refuse_while_daemon_runs(deployment, "roll back")
        aside = home.root / "env.replaced"
        shutil.rmtree(aside, ignore_errors=True)
        home.env.rename(aside)
        rollback.rename(home.env)
        aside.rename(rollback)
        pin_file.write_text(previous + "\n", encoding="utf-8")
        print(f"Rolled back to {previous}. The environment it replaced is kept at {rollback}. Re-verifying.")
        return _reverify_under_uv(home)
    wanted = (args.pin or pin_file.read_text(encoding="utf-8")).strip()
    if len(wanted) != 40 or any(c not in "0123456789abcdef" for c in wanted):
        source = "--pin" if args.pin else f"the file {pin_file}"
        raise KitError(Exit.USAGE, f"{source} must give a full 40-character commit id of the upstream repository")
    _refuse_while_daemon_runs(deployment, "upgrade")
    if wanted == current and not args.reinstall:
        print(f"The deployment is already at {current}. Pass --reinstall to rebuild it.")
        return Exit.OK
    print(f"Upgrading {current[:8]} -> {wanted[:8]}. The environment in use stays until the new one is built.")
    code = subprocess.call([installer, str(home.root), "--reinstall", "--pin", wanted])
    if code != 0:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"the install of {wanted[:8]} stopped (exit {code}); its message is above. "
            f"The deployment is unchanged at {current[:8]}",
            fix=f"logs are under {home.logs}",
        )
    pin_file.write_text(wanted + "\n", encoding="utf-8")
    print(f"Installed {wanted[:8]}. The earlier environment is kept at {rollback} "
          "(`arhugula upgrade --rollback`). Re-verifying.")
    return _reverify_under_uv(home)


def _uninstall(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    home = deployment.home
    removable = [home.env, home.root / "env.rollback", home.dist, home.upstream, home.config,
                 home.run, home.logs, home.bin, home.observability, home.lima,
                 home.root / "AGENTS.md", home.root / "CLAUDE.md"]
    kept = [home.state, home.keys, home.secrets, home.backups]
    if args.delete_state:
        removable += kept
        kept = []
    print("This removes:")
    for path in removable:
        print(f"  {path}")
    for path in kept:
        print(f"  (kept) {path}")
    print(f"  (kept) {home.kit}  — the kit itself; delete {home.root} by hand when you are done")
    if not args.yes:
        print("\nNothing was removed. Run again with --yes to remove these.")
        return Exit.OK
    _refuse_while_daemon_runs(deployment, "uninstall")
    _refuse_while_vm_runs(deployment, "uninstall")
    machine = lima.find(vm.kit_ref(home))
    if machine is not None:
        machine.delete()
        print(f"deleted the virtual machine {machine.name}")
    for path in removable:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    print(f"\nRemoved. Also remove this line from your shell profile if you added it:")
    print(f'  export PATH="{home.bin}:$PATH"')
    return Exit.OK


VERBS: tuple[Verb, ...] = (
    Verb(
        path=("init",),
        summary="Create the deployment, or re-verify or reconfigure an existing one.",
        tier="kit",
        handler=initflow.run_init,
        args=(
            Arg(("--answers",), "replay an answers file instead of asking", {"metavar": "FILE"}),
            Arg(("--yes",), "accept every default without asking", {"action": "store_true"}),
            Arg(
                ("--reconfigure",),
                "ask every question again, with your earlier answers as defaults",
                {"action": "store_true"},
            ),
            Arg(
                ("--reinstall",),
                "rebuild the environment even when it is already at the pin",
                {"action": "store_true"},
            ),
            Arg(
                ("--questions-json",),
                "print the questions, defaults and options as JSON and exit",
                {"action": "store_true"},
            ),
            Arg(("--smoke",), "run only the smoke workflows", {"action": "store_true"}),
            Arg(
                ("--reverify",),
                "keep the stored answers without asking; regenerate and check everything",
                {"action": "store_true"},
            ),
        ),
        example="arhugula init --reconfigure",
        detail=(
            "Without a flag, init asks its questions in the terminal. "
            "Enter accepts the default shown."
        ),
    ),
    Verb(
        path=("doctor",),
        summary="Re-run every preflight check against the current deployment.",
        tier="kit",
        handler=_doctor,
        args=(
            Arg(
                ("--self-test",),
                "prove on this machine that the runtime refuses what it should",
                {"action": "store_true"},
            ),
        ),
        example="arhugula doctor",
    ),
    Verb(
        path=("upgrade",),
        summary="Rebuild the deployment at another upstream commit, keeping the earlier environment.",
        tier="kit",
        handler=_upgrade,
        args=(
            Arg(("--pin",), "the upstream commit to move to (default: the kit's PIN file)", {"metavar": "SHA"}),
            Arg(("--reinstall",), "rebuild even when already at that commit", {"action": "store_true"}),
            Arg(("--rollback",), "return to the environment the last upgrade replaced", {"action": "store_true"}),
        ),
        example="arhugula upgrade --pin <commit>",
        detail=(
            "Rebuilds the environment, regenerates every config, has the runtime load each "
            "project's config, and runs the smoke workflows."
        ),
    ),
    Verb(
        path=("relocate",),
        summary="Move the whole deployment home to another directory.",
        tier="kit",
        handler=_relocate,
        args=(Arg(("new_home",), "the new home directory; it must not exist or must be empty"),),
        example="arhugula relocate ~/work/arhugula",
        detail=(
            "Moves the tree and rebuilds the environment, because its scripts carry their own "
            "path. Then it regenerates every config and the installation-state document, and "
            "has the runtime verify the state root at its new place."
        ),
    ),
    Verb(
        path=("uninstall",),
        summary="Remove the deployment. Without --yes it only lists what it would remove.",
        tier="kit",
        handler=_uninstall,
        args=(
            Arg(("--yes",), "really remove", {"action": "store_true"}),
            Arg(("--delete-state",), "also remove the state root, keys, secrets and backups", {"action": "store_true"}),
        ),
        example="arhugula uninstall",
    ),
)
