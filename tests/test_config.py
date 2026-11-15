"""The answers file, the overlay, the TOML writer and the config rendering."""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

from arhugula_kit import overlay, render, spec, toml_out
from arhugula_kit.errors import KitError
from arhugula_kit.layout import Home
from arhugula_kit.spec import Engine

from tests.support import answers

KNOWN = tuple(render.fragments())


def parsed(home: Path, **changes) -> spec.Spec:
    raw = {**answers(home, **changes), "format": spec.FORMAT}
    raw.pop("project")
    return spec.parse(raw, known_features=KNOWN)


class AnswersFileParsing(unittest.TestCase):
    def setUp(self):
        self.home = Path("/tmp/arhugula-home")

    def test_a_complete_file_parses(self):
        got = parsed(self.home)
        self.assertEqual(got.primary, "claude_code")
        self.assertIs(got.observability.engine, Engine.NONE)

    def test_a_missing_answer_is_named_never_defaulted(self):
        raw = {**answers(self.home), "format": spec.FORMAT}
        del raw["smoke"]
        with self.assertRaises(KitError) as caught:
            spec.parse(raw, known_features=KNOWN)
        self.assertIn("`smoke` is missing", caught.exception.message)

    def test_the_primary_must_be_a_selected_provider(self):
        with self.assertRaises(KitError):
            parsed(self.home, primary="codex")

    def test_the_fallback_must_differ_from_the_primary(self):
        with self.assertRaises(KitError):
            parsed(self.home, fallback="claude_code")

    def test_an_unknown_feature_is_refused(self):
        with self.assertRaises(KitError) as caught:
            parsed(self.home, features=["no-such-feature"])
        self.assertIn("no-such-feature", caught.exception.message)

    def test_the_engine_states_that_make_no_sense_are_refused(self):
        tier_without_vm = {"enabled": True, "engine": "none", "lima_home": "", "instance": ""}
        existing_without_name = {"enabled": True, "engine": "existing", "lima_home": "", "instance": ""}
        kit_with_a_name = {"enabled": True, "engine": "kit", "lima_home": "/x", "instance": "y"}
        for bad in (tier_without_vm, existing_without_name, kit_with_a_name):
            with self.assertRaises(KitError, msg=str(bad)):
                parsed(self.home, observability=bad)

    def test_it_round_trips_through_the_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "init-answers.json"
            original = parsed(self.home, observability={"enabled": True, "engine": "kit", "lima_home": "", "instance": ""})
            spec.save(original, path)
            self.assertEqual(spec.load(path, known_features=KNOWN), original)

    def test_a_project_name_that_would_collide_or_escape_is_refused(self):
        for name in ("harness", "default", "My_Service", "../x", "a" * 64):
            raw = {**answers(self.home), "format": spec.FORMAT,
                   "projects": {name: {"path": "/work/p", "workloads": ["research"]}}}
            raw.pop("project")
            with self.assertRaises(KitError, msg=name):
                spec.parse(raw, known_features=KNOWN)

    def test_a_project_name_is_derived_from_its_directory(self):
        self.assertEqual(spec.project_name_for(Path("/work/My Project_2")), "my-project-2")


class Overlay(unittest.TestCase):
    def test_setting_and_dropping_a_nested_value(self):
        base = parsed(Path("/tmp/h"))
        changed = overlay.set_value(base, "", ("runtime", "memory", "token_budget"), 900)
        self.assertEqual(overlay.get(changed.overlay, ("runtime", "memory", "token_budget")), 900)
        self.assertEqual(overlay.dropped(changed, "", ("runtime", "memory", "token_budget")).overlay, {})

    def test_a_project_scope_does_not_touch_the_deployment_overlay(self):
        base = parsed(Path("/tmp/h"))
        changed = overlay.set_value(base, "demo", ("runtime", "drain_timeout_seconds"), 5)
        self.assertEqual(changed.overlay, {})
        self.assertEqual(changed.project_overlays["demo"]["runtime"]["drain_timeout_seconds"], 5)


class TomlWriter(unittest.TestCase):
    def test_what_it_writes_reads_back_equal(self):
        document = {
            "runtime": {
                "name": 'quote " and \\ backslash',
                "ratio": 0.5,
                "on": True,
                "list": ["a", "b"],
                "table": {"key with space": 1},
                "rows": [{"a": 1, "nested": {"b": [1, 2]}}, {"a": 2}],
                "empty": [],
            }
        }
        self.assertEqual(tomllib.loads(toml_out.dumps(document, header="two\nlines")), document)

    def test_the_header_is_comment_lines(self):
        text = toml_out.dumps({"a": 1}, header="first\nsecond")
        self.assertTrue(text.startswith("# first\n# second\n"))


class Rendering(unittest.TestCase):
    """Ollama-only answers, so no provider CLI has to be installed where the tests run."""

    def setUp(self):
        self.home = Home(Path("/tmp/arhugula-home"))
        self.spec = parsed(self.home.root, providers=["ollama"], primary="ollama", fallback="", features=[])

    def config(self, wanted: spec.Spec, index: int = 0) -> dict:
        target = render.targets(wanted, self.home)[index]
        return render.render_config(wanted, self.home, target, render.fragments())["runtime"]

    def test_every_path_is_inside_the_home(self):
        runtime = self.config(self.spec)
        self.assertEqual(runtime["state_placement"]["state_root"], str(self.home.state))
        self.assertEqual(runtime["collector"]["span_store_path"], str(self.home.span_store))
        self.assertTrue(runtime["pidfile_path"].startswith(str(self.home.root)))

    def test_the_first_chain_is_the_primary(self):
        chain = self.config(self.spec)["routing_manifest"]["fallback_chains"][0]
        self.assertEqual(chain["primary"]["provider"], "ollama")

    def test_a_project_gets_its_own_tenant_ledger_and_repository(self):
        wanted = replace(self.spec, projects={"demo": spec.Project("/work/demo")})
        runtime = self.config(wanted, index=1)
        self.assertEqual(runtime["tenant_id"], "demo")
        self.assertEqual(runtime["repository_root"], "/work/demo")
        ledgers = {e["path"] for e in runtime["path_bindings"]["raw_entries"] if e["path_class"] == "STATE_LEDGER"}
        self.assertEqual(ledgers, {str(self.home.project_state("demo") / "state-ledger")})

    def test_a_feature_fragment_changes_the_config_and_leaves_no_placeholder(self):
        wanted = self.spec.with_feature("memory", True)
        runtime = self.config(wanted)
        self.assertTrue(runtime["memory"]["enabled"])
        self.assertNotIn("{{", str(runtime))

    def test_the_overlay_wins_over_base_and_fragments(self):
        wanted = overlay.set_value(self.spec, "", ("runtime", "default_topology"), "parallelization")
        self.assertEqual(self.config(wanted)["default_topology"], "parallelization")

    def test_every_shipped_fragment_is_described_and_valid_toml(self):
        values = {**self.home.substitutions(), "{{PRIMARY_LABEL}}": "ollama:m",
                  "{{REPOSITORY}}": "/r", "{{TARGET_STATE}}": "/s"}
        for name, fragment in render.fragments().items():
            self.assertTrue(fragment.title and fragment.summary, name)
            text = fragment.body
            for token, value in values.items():
                text = text.replace(token, value)
            self.assertIn("runtime", tomllib.loads(text), name)

    def test_an_empty_ledger_is_recorded_as_signed_from_its_first_entry(self):
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            home = Home(Path(scratch))
            wanted = render.with_new_cutover_ledgers(self.spec.with_feature("audit-signing", True), home)
            self.assertEqual(wanted.cutover_ledgers, ("",))
            target = render.targets(wanted, home)[0]
            runtime = render.render_config(wanted, home, target, render.fragments())["runtime"]
            self.assertIn("audit_cutover_record_path", runtime)
            self.assertIn("arhugula-cutover-record", runtime["audit_signing"]["local_key_paths"])

    def test_a_ledger_with_history_is_signed_without_a_cutover_record(self):
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            home = Home(Path(scratch))
            ledger = home.state / "state-ledger"
            ledger.mkdir(parents=True)
            (ledger / "state.jsonl").write_text("{}\n")
            wanted = render.with_new_cutover_ledgers(self.spec.with_feature("audit-signing", True), home)
            self.assertEqual(wanted.cutover_ledgers, ())
            target = render.targets(wanted, home)[0]
            runtime = render.render_config(wanted, home, target, render.fragments())["runtime"]
            self.assertNotIn("audit_cutover_record_path", runtime)
            self.assertEqual(runtime["audit_signing"]["backend"], "local-ed25519")

    def test_a_recorded_ledger_keeps_demanding_its_record_whatever_is_on_disk(self):
        """A record that goes missing must be the runtime's refusal, never a quiet downgrade."""
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            home = Home(Path(scratch))
            wanted = render.with_new_cutover_ledgers(self.spec.with_feature("audit-signing", True), home)
            ledger = home.state / "state-ledger"
            ledger.mkdir(parents=True)
            (ledger / "state.jsonl").write_text("{}\n")  # history now exists; the record does not
            again = render.with_new_cutover_ledgers(wanted, home)
            target = render.targets(again, home)[0]
            runtime = render.render_config(again, home, target, render.fragments())["runtime"]
            self.assertIn("audit_cutover_record_path", runtime)

    def test_signing_off_records_nothing(self):
        self.assertEqual(render.with_new_cutover_ledgers(self.spec, self.home).cutover_ledgers, ())

    def test_merging_keeps_siblings(self):
        self.assertEqual(render.deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 3}}), {"a": {"x": 1, "y": 3}})


if __name__ == "__main__":
    unittest.main()


class SignatureInputs(unittest.TestCase):
    """`status` and `audit verify` hand the inspector the same inputs for a signed ledger."""

    def _target(self, root: Path) -> "render.Target":
        from arhugula_kit import render
        state = root / "state"
        (state / "state-ledger").mkdir(parents=True)
        return render.Target("proj", root, state, "proj", (), root / "proj.toml")

    def test_a_ledger_signed_from_its_first_entry_gets_the_key_map_record_and_tenant(self):
        import tempfile
        from arhugula_kit import audit_keys, render
        from arhugula_kit.layout import Home
        with tempfile.TemporaryDirectory() as scratch:
            home = Home(Path(scratch))
            target = self._target(Path(scratch))
            self.assertEqual(audit_keys.signature_inputs(home, target), [])
            home.keys.mkdir(parents=True, exist_ok=True)
            (home.keys / audit_keys.KEY_MAP).write_text("{}")
            self.assertEqual(audit_keys.signature_inputs(home, target), [])  # no cutover record yet
            render.cutover_record(target).write_text("{}")
            words = [str(word) for word in audit_keys.signature_inputs(home, target)]
            self.assertEqual(words[0::2], ["--signing-key-map", "--cutover-record", "--expected-tenant"])
            self.assertEqual(words[-1], "proj")
