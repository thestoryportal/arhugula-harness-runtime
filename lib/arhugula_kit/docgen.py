"""Generate the parts of the documentation that restate the program.

    python -m arhugula_kit.docgen           rewrite the generated parts
    python -m arhugula_kit.docgen --check   exit 1 when a generated part is stale

[LAW:one-source-of-truth] A table in the docs that repeats a table in the program would
drift. So the program writes those tables: the command reference is one whole file, and
every other generated part sits between two marker comments inside a hand-written page:

    <!-- BEGIN GENERATED: dependencies -->
    ...
    <!-- END GENERATED: dependencies -->
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

from arhugula_kit import dependencies, helpmd, preflight, providers, questions, render
from arhugula_kit.cli import all_verbs
from arhugula_kit.errors import EXIT_MEANINGS
from arhugula_kit.layout import KIT_ROOT

__all__ = ["SECTIONS", "main", "regenerate"]

REGION = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<name>[a-z-]+) -->\n)(?P<body>.*?)(<!-- END GENERATED: (?P=name) -->)",
    re.DOTALL,
)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _questions() -> str:
    lines: list[str] = []
    for question in questions.QUESTIONS:
        lines += [
            f"### Question {question.number}: `{question.id}`",
            "",
            f"> {question.prompt}",
            "",
            f"- Default: {question.default_doc}.",
            f"- Why init asks: {question.why}",
            f"- Asked: {question.applies_when}.",
            "",
        ]
    return "\n".join(lines)


def _preflight() -> str:
    lines = ["| Check | What it checks | Runs | Fails when | What to do |", "| --- | --- | --- | --- | --- |"]
    lines += [
        f"| {check.id} | {_cell(check.title)} | {_cell(check.applies_when)} | "
        f"{_cell(check.fails_when)} | {_cell(check.fix)} |"
        for check in preflight.CHECKS
    ]
    return "\n".join(lines) + "\n"


def _fragments() -> str:
    lines: list[str] = []
    for name, fragment in render.fragments().items():
        body = "\n".join(l for l in fragment.body.splitlines() if not l.startswith("#:")).strip()
        lines += [f"### `{name}`: {fragment.title}", "", fragment.summary, ""]
        if fragment.needs:
            lines += [f"Needs: {fragment.needs}", ""]
        lines += [f"Switch it on with `arhugula feature enable {name}`. It adds:", "", "```toml", body, "```", ""]
    return "\n".join(lines)


def _providers() -> str:
    lines = [
        "| Name | Provider | Reached through | Default model | Install | Sign in |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    access = {
        providers.Access.CLI: "its command-line tool, signed in by you",
        providers.Access.OLLAMA: "the local Ollama server",
        providers.Access.SDK: "a hosted API, with a key in the macOS keychain",
    }
    for provider in providers.CATALOGUE:
        install = "<br>".join(f"`{_cell(command)}`" for command in provider.install) or "nothing to install"
        sign_in = f"`{provider.sign_in}`" if provider.sign_in else f"`arhugula provider key set {provider.name}`"
        lines.append(
            f"| `{provider.name}` | {provider.title} | {access[provider.access]} | "
            f"`{provider.default_model}` | {install} | {sign_in} |"
        )
    return "\n".join(lines) + "\n"


def _exit_codes() -> str:
    lines = ["| Code | Meaning |", "| --- | --- |"]
    lines += [f"| {int(code)} | {_cell(meaning)} |" for code, meaning in EXIT_MEANINGS.items()]
    return "\n".join(lines) + "\n"


SECTIONS: dict[str, Callable[[], str]] = {
    "dependencies": dependencies.markdown,
    "questions": _questions,
    "preflight": _preflight,
    "fragments": _fragments,
    "providers": _providers,
    "exit-codes": _exit_codes,
}


def _fill(text: str, where: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in SECTIONS:
            raise SystemExit(f"docgen: {where} names an unknown generated part `{name}`")
        return match.group(1) + SECTIONS[name]().rstrip("\n") + "\n" + match.group(4)

    return REGION.sub(replace, text)


def regenerate(kit: Path = KIT_ROOT) -> dict[Path, str]:
    """Every file with generated content, mapped to what it should contain now."""
    wanted: dict[Path, str] = {kit / "docs" / "reference" / "cli.md": helpmd.render(all_verbs())}
    pages = [kit / "README.md", *sorted((kit / "docs").glob("*.md")), *sorted((kit / "docs" / "reference").glob("*.md"))]
    for page in pages:
        if page in wanted or not page.is_file():
            continue
        text = page.read_text(encoding="utf-8")
        filled = _fill(text, page)
        if filled != text or REGION.search(text):
            wanted[page] = filled
    return wanted


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, text in regenerate().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"docgen: wrote {path.relative_to(KIT_ROOT)}")
    if check and stale:
        for path in stale:
            print(f"docgen: stale: {path.relative_to(KIT_ROOT)}", file=sys.stderr)
        print("docgen: run `just docs-reference` and commit the result", file=sys.stderr)
        return 1
    if not stale:
        print("docgen: every generated part is current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
