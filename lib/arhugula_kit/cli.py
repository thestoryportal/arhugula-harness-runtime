"""`arhugula`: the operator command line.

Builds the argument parser from the verb registry, runs one verb, and turns a `KitError`
into one message, its fix, and the documented exit code.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from arhugula_kit.errors import Exit, KitError
from arhugula_kit.verbs import GROUPS, Verb

__all__ = ["all_verbs", "build_parser", "main"]

PROGRAM = "arhugula"


def all_verbs() -> tuple[Verb, ...]:
    """Every verb, in the order the reference lists them."""
    from arhugula_kit import (
        verbs_agent,
        verbs_authoring,
        verbs_config,
        verbs_lifecycle,
        verbs_memory,
        verbs_observability,
        verbs_project,
        verbs_run,
        verbs_state,
    )

    return (
        *verbs_lifecycle.VERBS,
        *verbs_project.VERBS,
        *verbs_run.VERBS,
        *verbs_config.VERBS,
        *verbs_authoring.VERBS,
        *verbs_memory.VERBS,
        *verbs_observability.VERBS,
        *verbs_state.VERBS,
        *verbs_agent.VERBS,
    )


def build_parser(verbs: Sequence[Verb]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Operate a standalone Arhugula Harness deployment.",
        epilog="Every verb takes --help. The full reference is docs/reference/cli.md.",
    )
    parser.add_argument(
        "--help-markdown",
        action="store_true",
        help="print the complete verb reference as Markdown and exit",
    )
    # One subparser level per word of a verb's path, created the first time a path needs it.
    levels: dict[tuple[str, ...], argparse._SubParsersAction[argparse.ArgumentParser]] = {
        (): parser.add_subparsers(metavar="<verb>")
    }
    for verb in verbs:
        for depth in range(1, len(verb.path)):
            prefix = verb.path[:depth]
            if prefix not in levels:
                about = GROUPS[prefix[0]] if depth == 1 else f"`{' '.join(prefix)}` commands."
                group = levels[prefix[:-1]].add_parser(prefix[-1], help=about, description=about)
                levels[prefix] = group.add_subparsers(metavar="<action>")
                group.set_defaults(_usage=group)
        leaf = levels[verb.path[:-1]].add_parser(
            verb.path[-1], help=verb.summary, description=_describe(verb)
        )
        for arg in verb.args:
            leaf.add_argument(*arg.names, help=arg.help, **arg.options)
        leaf.set_defaults(_verb=verb)
    return parser


def _describe(verb: Verb) -> str:
    return verb.summary + (f"\n\n{verb.detail}" if verb.detail else "")


def main(argv: Sequence[str]) -> int:
    verbs = all_verbs()
    parser = build_parser(verbs)
    args, passthrough = parser.parse_known_args(list(argv))
    if args.help_markdown:
        from arhugula_kit import helpmd

        print(helpmd.render(verbs), end="")
        return Exit.OK
    verb: Verb | None = getattr(args, "_verb", None)
    if verb is None:
        (getattr(args, "_usage", None) or parser).print_help()
        return Exit.USAGE
    args.passthrough = passthrough
    if passthrough and not verb.passthrough:
        parser.error(f"unrecognized arguments: {' '.join(passthrough)}")
    try:
        return int(verb.handler(args))
    except KitError as error:
        print(f"{PROGRAM}: {error.message}", file=sys.stderr)
        if error.fix:
            print(f"  fix: {error.fix}", file=sys.stderr)
        return int(error.exit_code)
    except KeyboardInterrupt:
        print(f"{PROGRAM}: interrupted", file=sys.stderr)
        return 130
