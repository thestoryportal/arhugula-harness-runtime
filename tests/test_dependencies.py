"""The dependency table: what init says about a machine, and what the docs say."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arhugula_kit import dependencies
from arhugula_kit.dependencies import DEPENDENCIES, Need
from arhugula_kit.errors import KitError
from arhugula_kit.layout import KIT_ROOT, Home

from tests.support import machine


def stage(mach, *, offer=False, confirm=None):
    printed: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        dependencies.run_stage(
            mach, Home(Path(scratch)), offer=offer, resurvey=lambda: mach,
            out=printed.append, confirm=confirm,
        )
    return "\n".join(printed)


class DependencyStage(unittest.TestCase):
    def test_a_complete_machine_passes_and_names_every_dependency(self):
        text = stage(machine())
        for dependency in DEPENDENCIES:
            self.assertIn(dependency.title, text)

    def test_a_missing_required_dependency_is_explained_and_stops_init(self):
        printed: list[str] = []
        broken = machine(command_line_tools="")
        with tempfile.TemporaryDirectory() as scratch, self.assertRaises(KitError) as caught:
            dependencies.run_stage(broken, Home(Path(scratch)), offer=False,
                                   resurvey=lambda: broken, out=printed.append)
        text = "\n".join(printed)
        self.assertIn("what it is for:", text)
        self.assertIn("xcode-select --install", text)
        self.assertIn("Xcode Command Line Tools", caught.exception.message)

    def test_a_missing_optional_dependency_is_explained_and_init_goes_on(self):
        text = stage(machine(limactl=None, lima_version=None))
        self.assertIn("brew install lima", text)
        self.assertIn("the observability tier and isolation tier 3", text)

    def test_an_offer_is_asked_and_nothing_runs_on_a_no(self):
        asked: list[str] = []

        def decline(question: str) -> bool:
            asked.append(question)
            return False

        with self.assertRaises(KitError):
            stage(machine(python312=""), offer=True, confirm=decline)
        self.assertEqual(asked, ["Run `uv python install 3.12` now?"])

    def test_without_a_terminal_nothing_is_offered(self):
        asked: list[str] = []
        stage(machine(limactl=None, lima_version=None), offer=False, confirm=lambda q: asked.append(q) or True)
        self.assertEqual(asked, [])

    def test_no_provider_at_all_stops_init(self):
        nothing = tuple(
            type(state)(state.provider, dependencies.providers.Status.NOT_INSTALLED, "absent")
            for state in machine().provider_states
        )
        with self.assertRaises(KitError) as caught:
            stage(machine(provider_states=nothing, ollama_models=None))
        self.assertIn("At least one usable provider", caught.exception.message)

    def test_not_macos_is_refused_with_the_reason(self):
        printed: list[str] = []
        linux = machine(system="Linux", macos_version="")
        with tempfile.TemporaryDirectory() as scratch, self.assertRaises(KitError):
            dependencies.run_stage(linux, Home(Path(scratch)), offer=False,
                                   resurvey=lambda: linux, out=printed.append)
        self.assertIn("macOS only", "\n".join(printed))

    def test_intel_is_accepted_and_marked_untested(self):
        self.assertIn("Intel is untested", stage(machine(arch="x86_64")))


class DependencyTable(unittest.TestCase):
    def test_every_missing_dependency_has_a_way_to_check_and_a_purpose(self):
        for dependency in DEPENDENCIES:
            self.assertTrue(dependency.purpose and dependency.check_by_hand, dependency.id)

    def test_every_required_tool_has_a_setup_command(self):
        for dependency in DEPENDENCIES:
            if dependency.need is Need.REQUIRED and dependency.id not in ("macos", "disk", "provider"):
                self.assertTrue(dependency.setup, dependency.id)

    def test_the_docs_section_lists_every_dependency_with_its_commands(self):
        text = dependencies.markdown()
        for dependency in DEPENDENCIES:
            self.assertIn(dependency.title, text)
            for setup in dependency.setup:
                self.assertIn(setup.command, text)

    def test_the_init_entry_script_shows_the_same_commands_as_the_table(self):
        """`init` (zsh) guides uv and Python before any Python can run; it must not drift."""
        script = (KIT_ROOT / "init").read_text(encoding="utf-8")
        for dependency_id in ("uv", "python"):
            row = next(d for d in DEPENDENCIES if d.id == dependency_id)
            for setup in row.setup:
                self.assertIn(setup.command, script, f"init lacks `{setup.command}`")
            self.assertIn(row.check_by_hand, script)

    def test_no_dependency_text_names_a_machine(self):
        text = dependencies.markdown()
        for word in ("/Users/", "/Volumes/", "this Mac"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
