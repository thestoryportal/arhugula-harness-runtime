"""Run the documentation's marked command blocks against a real deployment.

A page marks a block it promises will work:

    <!-- witness -->
    ```sh
    arhugula status
    ```

`<!-- witness: exit=3 -->` marks a block that must fail with that exit code (a documented
refusal). Blocks run in page order, each as one zsh script, with `<home>/bin` first on
PATH and the home as working directory. `<home>`, `<project>` and `<project-path>` in a
block are replaced with the values given on the command line.

A page whose marked commands do not run is not done; this is the check.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit.layout import KIT_ROOT

__all__ = ["PAGE_ORDER", "Block", "blocks_of", "main"]

PAGE_ORDER = (
    "README.md",
    "docs/concepts.md",
    "docs/install.md",
    "docs/operate.md",
    "docs/troubleshooting.md",
    "docs/projects.md",
    "docs/providers.md",
    "docs/workflows.md",
    "docs/authoring.md",
    "docs/prompts-skills-validators.md",
    "docs/configure.md",
    "docs/memory.md",
    "docs/observability.md",
    "docs/evaluation.md",
    "docs/security-and-isolation.md",
    "docs/agents.md",
    "docs/upgrade.md",
    "docs/reference/known-gaps.md",
)

MARKED = re.compile(
    r"<!-- witness(?:: exit=(?P<exit>\d+))? -->\n```(?:sh|zsh|bash|console)\n(?P<body>.*?)\n```",
    re.DOTALL,
)


@dataclass(frozen=True)
class Block:
    page: str
    index: int
    script: str
    expected_exit: int


def blocks_of(page: str, text: str) -> list[Block]:
    return [
        Block(page, index, match.group("body"), int(match.group("exit") or 0))
        for index, match in enumerate(MARKED.finditer(text), start=1)
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="witness", description=__doc__.splitlines()[0])
    parser.add_argument("home", type=Path, help="the deployment home to run against")
    parser.add_argument("pages", nargs="*", help="pages to run (default: every page, in order)")
    parser.add_argument("--project", default="witness", help="the value for <project>")
    parser.add_argument("--project-path", default="", help="the value for <project-path>")
    parser.add_argument("--list", action="store_true", help="list the marked blocks and exit")
    args = parser.parse_args(argv)

    home = args.home.expanduser().resolve()
    pages = args.pages or list(PAGE_ORDER)
    missing = [page for page in pages if not (KIT_ROOT / page).is_file()]
    if missing:
        print(f"witness: page(s) not found, so nothing was run: {', '.join(missing)}", file=sys.stderr)
        return 2
    blocks = [
        block
        for page in pages
        for block in blocks_of(page, (KIT_ROOT / page).read_text(encoding="utf-8"))
    ]
    if args.list:
        for block in blocks:
            print(f"{block.page} #{block.index} (exit {block.expected_exit}): {block.script.splitlines()[0]}")
        print(f"{len(blocks)} marked block(s) in {len(pages)} page(s)")
        return 0

    if not args.pages:
        # A full run attaches the project and creates files in it, so it runs once.
        listed = subprocess.run(
            [str(home / "bin" / "arhugula"), "project", "list"], capture_output=True, text=True
        )
        if any(line.split()[:2][-1:] == [args.project] or line.split()[:1] == [args.project]
               for line in listed.stdout.splitlines()[1:]):
            print(
                f"witness: the project `{args.project}` is already attached, so a full run was "
                "already made on this deployment. The witness is for a fresh one. To repeat it: "
                f"`arhugula project remove {args.project}`, then give a new empty repository as "
                "--project-path.",
                file=sys.stderr,
            )
            return 2
    if not blocks:
        print("witness: no page marks a block with <!-- witness -->, so nothing was run", file=sys.stderr)
        return 2
    logs = home / "logs" / "witness"
    logs.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "PATH": f"{home / 'bin'}:{os.environ['PATH']}"}
    failed = 0
    for number, block in enumerate(blocks, start=1):
        script = (
            block.script.replace("<home>", str(home))
            .replace("<project-path>", args.project_path)
            .replace("<project>", args.project)
        )
        started = time.monotonic()
        done = subprocess.run(
            ["/bin/zsh", "-c", script], cwd=home, env=environment,
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
        )
        took = time.monotonic() - started
        name = f"{number:03d}-{Path(block.page).stem}-{block.index}.log"
        (logs / name).write_text(
            f"$ {script}\n--- stdout\n{done.stdout}--- stderr\n{done.stderr}--- exit {done.returncode}\n",
            encoding="utf-8",
        )
        passed = done.returncode == block.expected_exit
        failed += 0 if passed else 1
        print(f"{'ok  ' if passed else 'FAIL'}  {block.page} #{block.index}  exit {done.returncode}"
              f"{'' if passed else f' (expected {block.expected_exit})'}  {took:.1f} s  {name}", flush=True)
        if not passed:
            print("      " + "\n      ".join((done.stderr.strip() or done.stdout.strip()).splitlines()[-5:]))
    print(f"\n{len(blocks) - failed} of {len(blocks)} marked block(s) ran as documented; logs in {logs}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
