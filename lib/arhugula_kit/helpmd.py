"""Render the verb registry as the Markdown reference (docs/reference/cli.md)."""

from __future__ import annotations

from collections.abc import Sequence

from arhugula_kit.verbs import GROUPS, Verb

__all__ = ["render"]

TIERS = {
    "runtime": "drives a capability of the harness runtime",
    "kit": "*kit extension*: added by this kit, not part of upstream",
}


def _usage(verb: Verb) -> str:
    words = ["arhugula", *verb.path]
    for arg in verb.args:
        name = arg.names[0]
        if name.startswith("--"):
            takes_value = arg.options.get("action") not in ("store_true", "store_false")
            metavar = arg.options.get("metavar") or name[2:].upper().replace("-", "_")
            text = f"{name} {metavar}" if takes_value else name
            words.append(text if arg.options.get("required") else f"[{text}]")
        else:
            words.append(f"<{name}>")
    return " ".join(words)


def render(verbs: Sequence[Verb]) -> str:
    lines = [
        "# `arhugula` command reference",
        "",
        "This page is for anyone who operates the deployment. It lists every verb, its "
        "arguments and one example.",
        "",
        "It is generated from the program itself by `arhugula --help-markdown`. Do not edit "
        "it by hand: run `just docs-reference` to refresh it.",
        "",
        "Each verb is marked with where its capability comes from:",
        "",
    ]
    lines += [f"- **{tier}**: {meaning}." for tier, meaning in TIERS.items()]
    lines += ["", "## Verbs by group", ""]
    seen: list[str] = []
    for verb in verbs:
        if verb.path[0] not in seen:
            seen.append(verb.path[0])
    lines += [f"- [`{group}`](#{group}): {GROUPS[group]}" for group in seen]
    for group in seen:
        lines += ["", f"## {group}", "", GROUPS[group], ""]
        for verb in (v for v in verbs if v.path[0] == group):
            lines += [f"### `{' '.join(('arhugula', *verb.path))}`", "", verb.summary, ""]
            if verb.detail:
                lines += [verb.detail, ""]
            lines += [f"Source: {verb.tier} ({TIERS[verb.tier].replace('*', '')}).", ""]
            lines += ["```text", _usage(verb), "```", ""]
            if verb.args:
                lines += ["| Argument | Meaning |", "| --- | --- |"]
                for arg in verb.args:
                    choices = arg.options.get("choices")
                    extra = f" One of: {', '.join(f'`{c}`' for c in choices)}." if choices else ""
                    names = ", ".join(f"`{n}`" for n in arg.names)
                    lines.append(f"| {names} | {arg.help[0].upper()}{arg.help[1:]}.{extra} |")
                lines.append("")
            if verb.example:
                lines += ["Example:", "", "```sh", verb.example, "```", ""]
    return "\n".join(lines).rstrip() + "\n"
