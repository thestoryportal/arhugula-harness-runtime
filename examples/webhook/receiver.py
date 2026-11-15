"""An example webhook receiver for docs/operate.md: it records every notification.

    <home>/env/bin/python receiver.py 18766

The harness posts here when you answer `hold` at an approval gate. Each request is
appended to received.jsonl beside this file. A real receiver would notify a person.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RECORD = Path(__file__).parent / "received.jsonl"


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        with RECORD.open("a", encoding="utf-8") as record:
            record.write(json.dumps({"path": self.path, "body": body.decode("utf-8", "replace")}) + "\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    do_PUT = do_POST

    def log_message(self, *args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), Receiver).serve_forever()
