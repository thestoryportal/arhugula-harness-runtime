"""Run the harness CLI with a skill-activation hook attached (*kit extension*).

    <home>/env/bin/python -m arhugula_kit.hookrun <module:Class> run <manifest> --config ...

The runtime takes a skill-activation hook only as a Python object on its config
(`skill_activation_hook_config.hook`), which no TOML file can express. This module runs the
runtime's own CLI unchanged, with one substitution at the config boundary: the loaded
config gains the hook. Everything else, including gates, flags and exit codes, is the
runtime's.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any


def _hook(spec: str) -> Any:
    module_name, _, class_name = spec.partition(":")
    return getattr(importlib.import_module(module_name), class_name)()


def main(argv: list[str]) -> None:
    from harness_runtime.cli.app import app
    from harness_runtime.config_source import RuntimeConfigSource
    from harness_runtime.lifecycle.skill_activation import SkillActivationHookConfig

    hook = _hook(argv[0])
    load = RuntimeConfigSource.load.__func__

    def load_with_hook(cls: type, *args: Any, **kwargs: Any) -> Any:
        config = load(cls, *args, **kwargs)
        return config.model_copy(
            update={"skill_activation_hook_config": SkillActivationHookConfig(hook=hook)}
        )

    RuntimeConfigSource.load = classmethod(load_with_hook)  # type: ignore[method-assign]
    sys.argv = ["harness", *argv[1:]]
    app()


if __name__ == "__main__":
    main(sys.argv[1:])
