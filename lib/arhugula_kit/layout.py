"""The deployment home and the fixed places inside it.

[LAW:one-source-of-truth] Every path the kit uses derives from one value, the home. The
home is the directory that contains the kit clone, so a moved deployment needs no stored
path to find itself; only generated files carry absolute paths, and `relocate`
regenerates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["KIT_ROOT", "KIT_VM_NAME", "STACK_PORTS", "Home"]

KIT_ROOT = Path(__file__).resolve().parents[2]
"""The kit clone: `<home>/kit` in an initialized deployment."""

STACK_PORTS: dict[str, int] = {"Grafana": 3000, "Tempo": 3200, "OTLP gRPC": 4317, "OTLP HTTP": 4318}
"""The loopback ports upstream's Compose project publishes (its defaults; the kit keeps them)."""

KIT_VM_NAME = "arhugula"
"""The Lima instance the kit creates under `<home>/lima`."""


@dataclass(frozen=True)
class Home:
    """A deployment home: a plain directory, never a git checkout."""

    root: Path

    @classmethod
    def of_kit(cls) -> Home:
        """The home this kit clone sits in."""
        return cls(KIT_ROOT.parent)

    @property
    def kit(self) -> Path:
        return self.root / "kit"

    @property
    def upstream(self) -> Path:
        return self.root / "upstream"

    @property
    def env(self) -> Path:
        return self.root / "env"

    @property
    def python(self) -> Path:
        return self.env / "bin" / "python"

    @property
    def harness(self) -> Path:
        return self.env / "bin" / "harness"

    @property
    def harness_inspect(self) -> Path:
        return self.env / "bin" / "harness-inspect"

    @property
    def harness_shutdown(self) -> Path:
        return self.env / "bin" / "harness-shutdown"

    @property
    def installation_state(self) -> Path:
        return self.env / "etc" / "arhugula" / "installation-state.json"

    @property
    def dist(self) -> Path:
        return self.root / "dist"

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def pause_journal(self) -> Path:
        return self.state / "pause-journal"

    @property
    def span_store(self) -> Path:
        return self.state / "observability" / "spans.sqlite"

    @property
    def evaluation(self) -> Path:
        return self.state / "observability" / "evaluation"

    def project_state(self, name: str) -> Path:
        return self.state / "projects" / name

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def spec_file(self) -> Path:
        return self.config / "init-answers.json"

    @property
    def deployment_config(self) -> Path:
        return self.config / "harness.toml"

    def project_config(self, name: str) -> Path:
        return self.config / "projects" / f"{name}.toml"

    @property
    def observability(self) -> Path:
        return self.root / "observability"

    @property
    def lima(self) -> Path:
        """The Lima home of the kit's own VM. It moves with the deployment."""
        return self.root / "lima"

    @property
    def grafana_password(self) -> Path:
        return self.secrets / "grafana-admin-password"

    @property
    def secrets(self) -> Path:
        return self.root / "secrets"

    @property
    def keys(self) -> Path:
        return self.root / "keys"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def run(self) -> Path:
        return self.root / "run"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def private_backups(self) -> Path:
        """The backups directory, created if need be and readable by its owner only."""
        self.backups.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backups.chmod(0o700)
        return self.backups

    @property
    def bin(self) -> Path:
        return self.root / "bin"

    def substitutions(self) -> dict[str, str]:
        """The placeholders fragments and stored overlays may carry, and their values."""
        return {
            "{{HOME}}": str(self.root),
            "{{UPSTREAM}}": str(self.upstream),
            "{{STATE_ROOT}}": str(self.state),
            "{{KEYS}}": str(self.keys),
            "{{LOGS}}": str(self.logs),
            "{{RUN}}": str(self.run),
            "{{OBSERVABILITY}}": str(self.observability),
        }
