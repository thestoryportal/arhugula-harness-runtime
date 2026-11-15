"""Which provider really served a run, read from the run's spans.

A run started with `--provider` can end `completed` although that provider failed and the
fallback chain served every step. The status line hides it. The runtime writes one
`chat <model>` span per model call, with the provider as an attribute and a failed call's
reason as the status message; this module turns those spans into one plain line.

[LAW:effects-at-boundaries] `served_line` is pure over the spans; `after_run` is the one
read of the span store.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Chat", "after_run", "served_line"]

ERROR = 2  # the OpenTelemetry status code of a failed span
ROOT = "workflow.envelope"


@dataclass(frozen=True)
class Chat:
    provider: str
    model: str
    failed: bool
    reason: str = ""


def served_line(chats: Sequence[Chat], named: str, model: str) -> str:
    """One line when `named` failed and another provider served; "" when that is not what happened."""
    failures = [chat for chat in chats if chat.failed and chat.provider == named]
    others = list(dict.fromkeys(f"{c.provider}/{c.model}" for c in chats if not c.failed and c.provider != named))
    if not failures or not others:
        return ""
    reason = " ".join(failures[-1].reason.split())[:240] or "no reason was recorded"
    return (
        f"served by {', '.join(others)}, not by {named}/{model or failures[-1].model}: "
        f"{named} failed ({reason})"
    )


def _chats(store: Path, since_ns: int) -> tuple[Chat, ...]:
    """The model calls of the one run whose root span began at or after `since_ns`.

    Nothing when no run, or more than one (another run overlapped), began since then.
    """
    if not store.is_file():
        return ()
    try:
        # `as_uri` escapes a `#`, `?` or `%` in the path, which would otherwise end it early.
        with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as conn:
            traces = [row[0] for row in conn.execute(
                "select distinct trace_id from spans where name = ? and start_time_ns >= ?", (ROOT, since_ns)
            )]
            if len(traces) != 1:
                return ()
            rows = conn.execute(
                "select name, status_code, status_message, attributes_json from spans "
                "where trace_id = ? and name like 'chat %' order by start_time_ns",
                (traces[0],),
            ).fetchall()
    except sqlite3.Error:
        return ()
    chats = []
    for name, status, message, attributes in rows:
        try:
            facts = json.loads(attributes)
        except ValueError:
            continue
        chats.append(
            Chat(
                provider=str(facts.get("gen_ai.provider.name", "")),
                model=str(facts.get("gen_ai.request.model", name.removeprefix("chat "))),
                failed=status == ERROR,
                reason=message or "",
            )
        )
    return tuple(chats)


def after_run(store: Path, since_ns: int, named: str, model: str) -> str:
    return served_line(_chats(store, since_ns), named, model)
