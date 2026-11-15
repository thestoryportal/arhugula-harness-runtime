"""An example MCP tool server for docs/workflows.md: two tools on loopback.

    <home>/env/bin/python notes_server.py 18765

`notes.read` returns its argument; `notes.write` appends it to notes.txt beside this file.
The example workflow `gated-tool.toml` puts an approval gate in front of `notes.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

server = FastMCP("example-notes", host="127.0.0.1", port=int(sys.argv[1]))


@server.tool(name="notes.read")
def read(value: str) -> str:
    """Return the value unchanged."""
    return value


@server.tool(name="notes.write")
def write(value: str) -> str:
    """Append the value to notes.txt."""
    with (Path(__file__).parent / "notes.txt").open("a", encoding="utf-8") as notes:
        notes.write(value + "\n")
    return f"wrote: {value}"


if __name__ == "__main__":
    server.run(transport="streamable-http")
