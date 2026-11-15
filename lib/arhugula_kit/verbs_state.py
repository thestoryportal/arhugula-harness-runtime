"""The state root: what is in it, backing it up, restoring it, and leftover project state."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path

from arhugula_kit import deploy, preflight, render, runtime
from arhugula_kit.common import say, table
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.verbs import Arg, Verb


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _human(count: int) -> str:
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def _lines(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _span_rows(store: Path) -> str:
    if not store.is_file():
        return "no span store yet"
    with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as conn:
        spans, traces = conn.execute("SELECT COUNT(*), COUNT(DISTINCT trace_id) FROM spans").fetchone()
    return f"{spans} spans in {traces} traces"


def _status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    home = deployment.home
    verified = runtime.call(home, "bootstrap-state-root", config=str(home.deployment_config))
    journal = runtime.call(home, "resolve-pause-journal", config=str(home.deployment_config))
    say(f"state root:        {verified['state_root']}  (verified by the runtime)")
    say(f"size:              {_human(_size(home.state))}")
    say(f"pause-journal:     {journal['pause_journal_root']}  "
        f"({sum(1 for _ in home.pause_journal.iterdir())} files)")
    say(f"span store:        {home.span_store}  ({_span_rows(home.span_store)})")
    say("")
    table(
        [
            (
                target.label,
                str(_lines(target.state / "state-ledger" / "state.jsonl")),
                "yes" if (target.state / "memory").is_dir() else "no",
                str(target.state),
            )
            for target in render.targets(deployment.spec, home)
        ],
        header=("project", "ledger entries", "memory", "state directory"),
    )
    return Exit.OK


def _backup(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    home = deployment.home
    home.backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive = (
        Path(args.output).expanduser().resolve()
        if args.output
        else home.backups / f"state-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
    )
    if archive.exists():
        raise KitError(Exit.PRECONDITION, f"{archive} already exists")
    # The archive holds the private state root, so it is private from its first byte, and a
    # write that fails leaves no partial archive behind.
    partial = archive.with_name(archive.name + ".partial")
    handle = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
            tar.add(home.state, arcname="state")
            tar.add(home.spec_file, arcname="config/init-answers.json")
        partial.replace(archive)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    say(f"wrote {archive} ({_human(archive.stat().st_size)}): the state root and the answers file.")
    say("Keys under keys/ and secrets under secrets/ are not in it; back those up separately.")
    return Exit.OK


def _restore(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    home = deployment.home
    archive = Path(args.archive).expanduser().resolve()
    if not archive.is_file():
        raise KitError(Exit.PRECONDITION, f"{archive} is not a file")
    from arhugula_kit import daemon

    if daemon.running(home):
        raise KitError(Exit.PRECONDITION, "a harness daemon is running", fix="arhugula daemon stop")
    aside = home.root / f"state.before-restore-{time.strftime('%Y%m%dT%H%M%S')}"
    try:
        opened = tarfile.open(archive, "r:gz")
    except tarfile.TarError as unreadable:
        raise KitError(
            Exit.PRECONDITION, f"{archive} is not an archive written by `state backup`: {unreadable}"
        ) from unreadable
    with opened as tar:
        members = [m for m in tar.getmembers() if m.name == "state" or m.name.startswith("state/")]
        if not members:
            raise KitError(Exit.PRECONDITION, f"{archive} holds no `state` directory")
        home.state.rename(aside)
        try:
            tar.extractall(home.root, members=members, filter="data")
            # The `data` filter extracts directories with default permissions. The runtime
            # requires the state root to be private, so each directory gets its archived mode.
            for member in members:
                if member.isdir():
                    (home.root / member.name).chmod(member.mode & 0o777)
            verified = runtime.call(home, "bootstrap-state-root", config=str(home.deployment_config))
        except BaseException:
            # Restore is all or nothing: put the earlier state root back and report.
            shutil.rmtree(home.state)
            aside.rename(home.state)
            raise
    say(f"restored {archive} to {verified['state_root']}; the runtime verified it.")
    say(f"The state root from before the restore is kept at {aside}; delete it when you are sure.")
    return Exit.OK


def _adopt(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    home = deployment.home
    verified = runtime.call(home, "bootstrap-state-root", config=str(home.deployment_config))
    journal = runtime.call(home, "resolve-pause-journal", config=str(home.deployment_config))
    say(f"the runtime verified the state root at {verified['state_root']}")
    say(f"the pause-journal root resolves to {journal['pause_journal_root']}")
    return Exit.OK


def _archive_legacy(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    project = Path(args.project_path).expanduser().resolve()
    found = [project / ".harness" / relative for relative in preflight.LEGACY_STATE]
    found = [p for p in found if p.is_file() or (p.is_dir() and any(p.iterdir()))]
    if not found:
        say(f"{project} holds no leftover harness state.")
        return Exit.OK
    destination = deployment.home.backups / f"legacy-{project.name}-{time.strftime('%Y%m%dT%H%M%S')}"
    destination.mkdir(parents=True)
    for path in found:
        target = destination / path.relative_to(project / ".harness")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        say(f"moved {path} -> {target}")
    say("The runtime never copies or deletes this state itself; it is kept under backups/.")
    return Exit.OK


VERBS: tuple[Verb, ...] = (
    Verb(("state", "status"), "Show the state root, its size, and each project's ledger.", "runtime", _status, example="arhugula state status"),
    Verb(
        ("state", "backup"),
        "Write the state root and the answers file to one archive.",
        "kit",
        _backup,
        (Arg(("--output",), "the archive to write (default: backups/state-<time>.tar.gz)", {}),),
        example="arhugula state backup",
        detail="Stop the daemon first so the archive is consistent.",
    ),
    Verb(
        ("state", "restore"),
        "Replace the state root with one from a backup archive.",
        "kit",
        _restore,
        (Arg(("archive",), "an archive written by `state backup`"),),
        example="arhugula state restore backups/state-20261115T101500.tar.gz",
        detail="The current state root is moved aside, not deleted. The runtime verifies the restored root.",
    ),
    Verb(
        ("state", "adopt"),
        "Have the runtime verify the state root again, for example after a move.",
        "runtime",
        _adopt,
        example="arhugula state adopt",
    ),
    Verb(
        ("state", "archive-legacy"),
        "Move a project's leftover checkout-local harness state into backups/.",
        "kit",
        _archive_legacy,
        (Arg(("project_path",), "the project repository that holds the leftover state"),),
        example="arhugula state archive-legacy ~/code/my-service",
        detail="The runtime refuses a project with such state (legacy-state-present) and never moves it itself.",
    ),
)
