"""The command surface, the generated docs, the agent context section and the docs witness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arhugula_kit import agentctx, cli, docgen, helpmd, witness
from arhugula_kit.errors import EXIT_MEANINGS, Exit
from arhugula_kit.verbs import GROUPS


class CommandSurface(unittest.TestCase):
    def setUp(self):
        self.verbs = cli.all_verbs()

    def test_every_verb_has_a_group_a_summary_and_an_example_that_names_it(self):
        for verb in self.verbs:
            self.assertIn(verb.path[0], GROUPS, verb.path)
            self.assertTrue(verb.summary.endswith("."), verb.path)
            self.assertTrue(verb.example.startswith("arhugula " + " ".join(verb.path)), verb.path)
            self.assertIn(verb.tier, helpmd.TIERS, verb.path)

    def test_no_two_verbs_share_a_path(self):
        paths = [verb.path for verb in self.verbs]
        self.assertEqual(len(paths), len(set(paths)))

    def test_every_example_parses_as_a_command_line(self):
        import shlex

        parser = cli.build_parser(self.verbs)
        for verb in self.verbs:
            words = shlex.split(verb.example)[1:]
            args, extra = parser.parse_known_args(words)
            self.assertIs(args._verb, verb, verb.example)
            self.assertTrue(verb.passthrough or not extra, verb.example)

    def test_a_bare_group_prints_help_and_is_a_usage_error(self):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["project"]), Exit.USAGE)

    def test_every_exit_code_has_a_meaning(self):
        self.assertEqual(set(EXIT_MEANINGS), set(Exit))


class GeneratedDocs(unittest.TestCase):
    def test_the_reference_lists_every_verb(self):
        text = helpmd.render(cli.all_verbs())
        for verb in cli.all_verbs():
            self.assertIn(f"### `arhugula {' '.join(verb.path)}`", text)

    def test_a_marked_part_is_replaced_and_the_rest_is_left_alone(self):
        page = "before\n<!-- BEGIN GENERATED: exit-codes -->\nstale\n<!-- END GENERATED: exit-codes -->\nafter\n"
        filled = docgen._fill(page, Path("page.md"))
        self.assertTrue(filled.startswith("before\n") and filled.endswith("after\n"))
        self.assertNotIn("stale", filled)
        self.assertIn("| 3 |", filled)
        self.assertEqual(docgen._fill(filled, Path("page.md")), filled)

    def test_an_unknown_part_is_an_error_not_a_blank(self):
        with self.assertRaises(SystemExit):
            docgen._fill("<!-- BEGIN GENERATED: nope -->\n<!-- END GENERATED: nope -->", Path("p.md"))

    def test_every_generated_part_has_content_and_no_machine_path(self):
        for name, build in docgen.SECTIONS.items():
            text = build()
            self.assertTrue(text.strip(), name)
            self.assertNotIn("/Users/", text, name)


class Dashboards(unittest.TestCase):
    def test_the_shipped_files_are_what_the_generator_renders(self):
        import importlib.util

        from arhugula_kit.layout import KIT_ROOT

        spec = importlib.util.spec_from_file_location("dashboards", KIT_ROOT / "tools" / "dashboards.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path, text in module.rendered().items():
            self.assertEqual(Path(path).read_text(encoding="utf-8"), text, f"{path} is stale")

    def test_every_dashboard_is_valid_json_on_the_tempo_datasource_with_no_machine_path(self):
        import json

        from arhugula_kit.layout import KIT_ROOT

        files = sorted((KIT_ROOT / "observability" / "dashboards").glob("*.json"))
        self.assertEqual(len(files), 7)
        for file in files:
            text = file.read_text(encoding="utf-8")
            board = json.loads(text)
            self.assertTrue(board["uid"].startswith("arhugula-"), file.name)
            self.assertNotIn("/Users/", text)
            for panel in board["panels"]:
                self.assertTrue(panel.get("description"), f"{file.name}: {panel['title']}")
                for target in panel.get("targets", ()):
                    self.assertEqual(target["datasource"], {"type": "tempo", "uid": "tempo"}, file.name)


class AgentContextSection(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.file = Path(self.scratch.name) / "CLAUDE.md"

    def test_it_is_added_after_existing_text_and_replaced_in_place(self):
        self.file.write_text("# Mine\n\nmy rules\n")
        agentctx._write(self.file, "first body")
        agentctx._write(self.file, "second body")
        text = self.file.read_text()
        self.assertTrue(text.startswith("# Mine\n\nmy rules\n"))
        self.assertEqual(text.count(agentctx.BEGIN), 1)
        self.assertIn("second body", text)
        self.assertNotIn("first body", text)

    def test_removing_it_leaves_the_operators_text(self):
        self.file.write_text("# Mine\n")
        agentctx._write(self.file, "body")
        agentctx.remove(Path(self.scratch.name))
        self.assertEqual(self.file.read_text(), "# Mine\n")

    def test_a_file_that_held_only_the_section_is_removed(self):
        agentctx._write(self.file, "body")
        agentctx.remove(Path(self.scratch.name))
        self.assertFalse(self.file.exists())


class DocsWitness(unittest.TestCase):
    def test_only_marked_blocks_are_collected_with_their_expected_exit(self):
        page = (
            "```sh\nnot marked\n```\n\n"
            "<!-- witness -->\n```sh\narhugula status\n```\n\n"
            "<!-- witness: exit=3 -->\n```sh\narhugula project use nope\n```\n"
        )
        blocks = witness.blocks_of("docs/x.md", page)
        self.assertEqual([(b.script, b.expected_exit) for b in blocks],
                         [("arhugula status", 0), ("arhugula project use nope", 3)])


if __name__ == "__main__":
    unittest.main()
