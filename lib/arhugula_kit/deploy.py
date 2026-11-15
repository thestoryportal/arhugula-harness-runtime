"""A loaded deployment, and the one way its configuration changes.

[LAW:single-enforcer] `apply` is the only writer of the answers file and of generated
configs. It renders every config to a staging directory, has the runtime's own loader
accept each one, and only then moves them into place and saves the answers. A change the
runtime refuses leaves the deployment exactly as it was.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit import render, runtime, spec, toml_out
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home
from arhugula_kit.spec import Spec

__all__ = ["Deployment", "apply", "open_deployment"]


@dataclass(frozen=True)
class Deployment:
    home: Home
    spec: Spec
    fragments: dict[str, render.Fragment]

    def target(self, project: str | None = None) -> render.Target:
        """The config target for a project name, the current project, or the default."""
        name = self.spec.current_project if project is None else project
        for target in render.targets(self.spec, self.home):
            if target.name == name:
                return target
        attached = ", ".join(sorted(self.spec.projects)) or "none"
        raise KitError(
            Exit.PRECONDITION,
            f"no attached project named {name!r} (attached: {attached})",
            fix="arhugula project add <path>",
        )


def open_deployment(home: Home | None = None) -> Deployment:
    home = home or Home.of_kit()
    known = render.fragments()
    return Deployment(home, spec.load(home.spec_file, known_features=tuple(known)), known)


def apply(deployment: Deployment, changed: Spec) -> Deployment:
    """Regenerate every config from `changed`; commit only when the runtime accepts them all."""
    home = deployment.home
    runtime.require_installed(home)
    staging = home.config / ".staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for target in render.targets(changed, home):
            document = render.render_config(changed, home, target, deployment.fragments)
            scratch = staging / f"{target.name or 'harness'}.toml"
            scratch.write_text(
                toml_out.dumps(document, header=render.header(target, home)), encoding="utf-8"
            )
            match runtime.ask(home, "load-config", config=str(scratch)):
                case runtime.Refusal(kind=kind, message=message):
                    raise KitError(
                        Exit.RUNTIME_REFUSED,
                        f"the runtime refuses the new config for {target.label} ({kind}): "
                        f"{message}\nNothing was changed.",
                    )
                case _:
                    staged.append((scratch, target.config_file))
        wanted = {final for _, final in staged}
        for scratch, final in staged:
            final.parent.mkdir(parents=True, exist_ok=True)
            scratch.replace(final)
        for stale in (home.config / "projects").glob("*.toml"):
            if stale not in wanted:
                stale.unlink()
        spec.save(changed, home.spec_file)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return Deployment(home, changed, deployment.fragments)
