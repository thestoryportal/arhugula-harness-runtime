"""The two local keys of audit signing, and the key map that verification reads.

One key signs every audit entry. A second one signs each ledger's cutover record: the
runtime requires that to be different key material, so that a leaked entry key cannot
rewrite which entries a ledger must hold. The runtime ships no key generator (*upstream
limit*); the kit makes the keys through the runtime's own cryptography library.
"""

from __future__ import annotations

import json
from pathlib import Path

from arhugula_kit import render, runtime
from arhugula_kit.layout import Home

__all__ = ["KEY_MAP", "PRIVATE_KEY", "RECORD_KEY", "generate", "present"]

SIGNING_KEY_IDS = ("harness-runtime-dev", "harness-cost-attribution-v1")
PRIVATE_KEY = "audit-ed25519.pem"
PUBLIC_KEY = "audit-ed25519.pub.pem"
RECORD_KEY = render.RECORD_KEY
RECORD_PUBLIC_KEY = "audit-cutover-ed25519.pub.pem"
KEY_MAP = "signing-key-map.json"


def present(home: Home) -> bool:
    return all((home.keys / name).is_file() for name in (PRIVATE_KEY, RECORD_KEY, KEY_MAP))


def generate(home: Home) -> list[str]:
    """Create both keys and the key map; return what to tell the operator.

    A key that exists is never overwritten: the runtime refuses, and so does this.
    """
    keys = home.keys
    keys.mkdir(mode=0o700, exist_ok=True)
    keys.chmod(0o700)
    entry = runtime.call(home, "audit-keygen", private=str(keys / PRIVATE_KEY), public=str(keys / PUBLIC_KEY))
    record = runtime.call(home, "audit-keygen", private=str(keys / RECORD_KEY), public=str(keys / RECORD_PUBLIC_KEY))
    key_map = {
        **{
            f"ed25519:{key_id}": {
                "kind": "local-ed25519-public",
                "public_key_path": PUBLIC_KEY,
                "spki_sha256": entry["identity"],
            }
            for key_id in SIGNING_KEY_IDS
        },
        f"ed25519:{render.RECORD_KEY_ID}": {
            "kind": "local-ed25519-public",
            "public_key_path": RECORD_PUBLIC_KEY,
            "spki_sha256": record["identity"],
        },
    }
    (keys / KEY_MAP).write_text(json.dumps(key_map, indent=2) + "\n", encoding="utf-8")
    return [
        f"wrote {keys / PRIVATE_KEY} (mode 0600): signs every audit entry.",
        f"wrote {keys / RECORD_KEY} (mode 0600): signs each ledger's cutover record.",
        f"wrote the two public keys and {keys / KEY_MAP}: what `audit verify --signatures` reads.",
        "Back up both private keys; they are in no archive.",
    ]


def signature_inputs(home: Home, target: render.Target) -> list[str | Path]:
    """What the inspector needs to verify a ledger signed from its first entry; empty otherwise.

    With a cutover record configured, the inspector accepts nothing less than the full
    check, so every verb that reads such a ledger through it must hand these over.
    """
    key_map, record = home.keys / KEY_MAP, render.cutover_record(target)
    if not (key_map.is_file() and record.is_file()):
        return []
    tenant: list[str | Path] = ["--expected-tenant", target.tenant_id] if target.tenant_id else []
    return ["--signing-key-map", key_map, "--cutover-record", record, *tenant]
