"""The kit's failure type and its exit codes.

Exit codes are a contract. `EXIT_MEANINGS` states it once; docs/operate.md renders it.
"""

from __future__ import annotations

from enum import IntEnum


class Exit(IntEnum):
    OK = 0
    WORKFLOW = 1
    USAGE = 2
    PRECONDITION = 3
    RUNTIME_REFUSED = 4
    EXTERNAL_TOOL = 5
    INTERNAL = 6


EXIT_MEANINGS: dict[Exit, str] = {
    Exit.OK: "Success.",
    Exit.WORKFLOW: "A workflow did not complete, an evaluation assertion failed, or a drift "
    "check found drift. A pass-through verb returns the runtime tool's own exit code instead.",
    Exit.USAGE: "The command line was wrong: unknown verb, missing argument, bad value.",
    Exit.PRECONDITION: "A precondition you can fix: a failed preflight check, a missing "
    "answer, an unknown project or name, a tool that is not installed.",
    Exit.RUNTIME_REFUSED: "The installed runtime refused: for example a config its loader "
    "does not accept. Nothing was changed.",
    Exit.EXTERNAL_TOOL: "An external tool failed: uv, git, limactl, docker or a provider CLI.",
    Exit.INTERNAL: "The kit's own invariant broke, or a self-test case did not refuse. Please file an issue.",
}


class KitError(Exception):
    """A failure the operator sees as one message plus, where there is one, the fix."""

    def __init__(self, exit_code: Exit, message: str, *, fix: str | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message
        self.fix = fix
