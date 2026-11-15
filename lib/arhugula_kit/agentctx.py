"""The project-side context section for agent CLIs (Claude Code, Codex).

A `CLAUDE.md` or `AGENTS.md` in a project does not reach the agents that run *inside* a
harness workflow: those calls are isolated. This section is for the agent CLI a person
opens in the project, so it knows the harness exists and how to drive it.
"""

from __future__ import annotations

from pathlib import Path

from arhugula_kit.deploy import Deployment
from arhugula_kit.layout import KIT_ROOT

__all__ = ["BEGIN", "END", "install", "section"]

BEGIN = "<!-- arhugula-harness:begin -->"
END = "<!-- arhugula-harness:end -->"
FILES = ("CLAUDE.md", "AGENTS.md")


def section(deployment: Deployment, name: str) -> str:
    template = (KIT_ROOT / "templates" / "project-agent-context.md.tmpl").read_text(encoding="utf-8")
    return (
        template.replace("{{PROJECT}}", name)
        .replace("{{COMMAND}}", str(deployment.home.bin / "arhugula"))
        .replace("{{KIT_DOCS}}", str(deployment.home.kit / "docs"))
    )


def _write(path: Path, body: str) -> str:
    block = f"{BEGIN}\n{body.rstrip()}\n{END}\n"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if BEGIN in existing and END in existing:
        head, _, rest = existing.partition(BEGIN)
        _, _, tail = rest.partition(END)
        path.write_text(head + block + tail.lstrip("\n"), encoding="utf-8")
        return f"refreshed the harness section in {path}"
    separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    path.write_text(existing + separator + block, encoding="utf-8")
    return f"added the harness section to {path}"


def install(deployment: Deployment, name: str) -> list[str]:
    """Write the section into the project's CLAUDE.md and AGENTS.md, replacing an earlier one."""
    project = Path(deployment.spec.projects[name].path)
    body = section(deployment, name)
    return [_write(project / filename, body) for filename in FILES]
