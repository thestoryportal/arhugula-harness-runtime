"""Models and thinking levels: the catalogues, the one check, the question, the answers file,
the level wrapper, and the line that says which provider really served a run."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sqlite3
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from arhugula_kit import deploy, initflow, modelwrap, overlay, providers, questions, render, servedby, spec, verbs_config, verbs_run
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import KitError
from arhugula_kit.layout import Home
from arhugula_kit.providers import ModelRefused, by_name, resolve

from tests.support import answers, fixture, machine, offered

KNOWN = tuple(render.fragments())


def by_id(question_id: str) -> questions.Question:
    return next(q for q in questions.QUESTIONS if q.id == question_id)


class Catalogues(unittest.TestCase):
    def test_codex_lists_only_what_it_shows_a_person_in_its_own_order(self):
        got = providers.parse_codex_models(fixture("codex-debug-models.json"))
        self.assertEqual([o.id for o in got], ["omega-1", "omega-2", "omega-mini"])
        self.assertEqual(got[0].levels, ("low", "medium", "high", "max"))
        self.assertEqual(got[1].levels, ("low", "medium", "high"))
        self.assertEqual((got[1].title, got[1].default_level), ("Omega 2", "medium"))
        self.assertEqual(got[2].levels, ())

    def test_codex_output_that_is_not_its_json_gives_no_list(self):
        self.assertEqual(providers.parse_codex_models("Error: not signed in"), ())
        self.assertEqual(providers.parse_codex_models('["a list, not an object"]'), ())

    def test_antigravity_lines_are_id_tab_title_and_nothing_else_counts(self):
        got = providers.parse_antigravity_models(fixture("agy-models.txt"))
        self.assertEqual([(o.id, o.title) for o in got],
                         [("sky-2-low", "Sky 2 (Low)"), ("sky-2-high", "Sky 2 (High)"), ("sky-flash", "Sky Flash")])

    def test_the_gemini_cli_is_gone_and_its_name_is_retired(self):
        self.assertNotIn("gemini", [p.name for p in providers.CATALOGUE])
        self.assertNotIn("g", [p.letter for p in providers.CATALOGUE])
        self.assertIn("gemini", providers.RETIRED)


class OneCheck(unittest.TestCase):
    codex = by_name("codex")
    claude = by_name("claude_code")
    agy = by_name("antigravity")

    def refused(self, provider, text, listed=()):
        with self.assertRaises(ModelRefused) as caught:
            resolve(provider, text, listed)
        return str(caught.exception)

    def test_a_listed_model_and_one_of_its_levels_pass_without_a_note(self):
        self.assertEqual(resolve(self.codex, "omega-1@max", offered()["codex"]), providers.Chosen("omega-1@max"))

    def test_a_model_the_sign_in_does_not_offer_is_refused_with_the_list(self):
        message = self.refused(self.codex, "gpt-5", offered()["codex"])
        self.assertIn("does not offer the model `gpt-5`", message)
        self.assertIn("omega-1, omega-2, omega-mini", message)

    def test_a_level_the_model_does_not_have_is_refused_with_its_levels(self):
        message = self.refused(self.codex, "omega-2@max", offered()["codex"])
        self.assertIn("`max` is not a thinking level of `omega-2`", message)
        self.assertIn("low, medium, high", message)

    def test_without_a_list_any_name_passes_and_says_it_was_not_checked(self):
        chosen = resolve(self.claude, "sonnet@high", ())
        self.assertEqual(chosen.ref, "sonnet@high")
        self.assertIn("could not be checked", chosen.note)

    def test_claude_levels_are_still_held_without_a_list(self):
        self.assertIn("low, medium, high, xhigh, max", self.refused(self.claude, "opus@ultra"))

    def test_antigravity_takes_its_display_name_and_stores_the_id(self):
        self.assertEqual(resolve(self.agy, "Sky 2 (High)", offered()["antigravity"]).ref, "sky-2-high")

    def test_antigravity_takes_no_level_because_the_level_is_in_the_model(self):
        self.assertIn("part of the model", self.refused(self.agy, "sky-2-low@high", offered()["antigravity"]))

    def test_providers_without_levels_say_where_thinking_is_set(self):
        for name in ("ollama", "anthropic", "openai"):
            message = self.refused(by_name(name), "some-model@high")
            self.assertIn("params", message, name)
            self.assertIn("docs/workflows.md", message, name)

    def test_a_malformed_reference_is_refused(self):
        for text in ("@high", "sonnet@", ""):
            self.assertIn("<model>@<level>", self.refused(self.claude, text), text)

    def test_an_ollama_model_not_pulled_passes_with_the_pull_command(self):
        chosen = resolve(by_name("ollama"), "mistral:7b", offered()["ollama"])
        self.assertIn("ollama pull mistral:7b", chosen.note)

    def test_the_proposed_model_is_the_tools_first_else_the_catalogues(self):
        self.assertEqual(providers.first_choice(self.codex, offered()["codex"]), "omega-1")
        self.assertEqual(providers.first_choice(self.claude, ()), "sonnet")
        self.assertEqual(providers.first_choice(by_name("ollama"), offered()["ollama"]), "llama3.2:3b")
        self.assertEqual(providers.first_choice(self.codex, ()), "")

    def test_a_level_on_a_listed_model_whose_list_shows_no_levels_is_refused(self):
        message = self.refused(self.codex, "omega-mini@whatever", offered()["codex"])
        self.assertIn("`whatever` is not a thinking level of `omega-mini`", message)
        self.assertIn("without `@level`", message)
        self.assertEqual(resolve(self.codex, "omega-mini", offered()["codex"]).ref, "omega-mini")

    def test_a_model_or_level_with_a_space_or_a_leading_dash_is_refused(self):
        for text in ("sonnet @high", "son net", "--tools", "sonnet@-x", "sonnet@hi gh"):
            self.assertIn("not a model name", self.refused(self.claude, text), text)
        # A display name with spaces is fine: it is stored as the id it names.
        self.assertEqual(resolve(self.agy, "Sky 2 (High)", offered()["antigravity"]).ref, "sky-2-high")

    def test_ollama_proposes_its_catalogue_model_even_when_only_an_embedding_model_is_pulled(self):
        pulled = (providers.Offer("nomic-embed-text:latest"), providers.Offer("mistral:7b"))
        self.assertEqual(providers.first_choice(by_name("ollama"), pulled), "llama3.2:3b")
        self.assertIn("ollama pull llama3.2:3b", resolve(by_name("ollama"), "llama3.2:3b", pulled).note)

    def test_a_missing_custom_executable_names_a_fix_the_kit_accepts(self):
        provider = providers.custom("local_echo", command="/nonexistent/echo", args=("{model}",),
                                    family="local_open_weight", prompt_transport="stdin", response_format="text")
        state = providers.check(provider, ollama_host="http://127.0.0.1:1")
        self.assertEqual(state.status, providers.Status.NOT_INSTALLED)
        self.assertTrue(state.fix.startswith("arhugula provider enable local_echo --command <path>"), state.fix)
        self.assertNotIn("provider add", state.fix)

    def test_a_stale_model_is_named_and_the_repair_keeps_what_still_works(self):
        stored = ("gpt-5", "omega-2@high")
        self.assertEqual([ref for ref, _ in providers.refusals(self.codex, stored, offered()["codex"])], ["gpt-5"])
        self.assertEqual(providers.repair_command(self.codex, stored, offered()["codex"]),
                         "arhugula provider enable codex --model omega-2@high")
        self.assertEqual(providers.repair_command(self.codex, ("gpt-5",), offered()["codex"]),
                         "arhugula provider enable codex --model omega-1")


class ModelsQuestion(unittest.TestCase):
    selection = {"providers": ["claude_code", "codex", "ollama"]}

    def setUp(self):
        self.question = by_id("models")

    def parse(self, text):
        return self.question.parse(text, machine(), self.selection)

    def test_it_is_question_five_of_fourteen(self):
        self.assertEqual((self.question.number, len(questions.QUESTIONS)), (5, 14))

    def test_the_default_is_valid_for_this_sign_in(self):
        self.assertEqual(self.question.default(machine(), self.selection),
                         {"claude_code": ["sonnet"], "codex": ["omega-1"], "ollama": ["llama3.2:3b"]})

    def test_a_good_answer_names_several_models_a_level_and_leaves_the_rest_default(self):
        got = self.parse(" codex = omega-2@high , omega-1 ; claude_code=opus@low")
        self.assertEqual(got, {"claude_code": ["opus@low"], "codex": ["omega-2@high", "omega-1"],
                               "ollama": ["llama3.2:3b"]})

    def test_the_typed_default_parses_back_to_the_default(self):
        default = self.question.default(machine(), self.selection)
        self.assertEqual(self.parse(questions._typed_default(self.question, default)), default)

    def test_bad_answers_say_what_was_wrong(self):
        cases = {
            "codex omega-1": "has no `=`",
            "antigravity=sky-flash": "not one of the providers selected",
            "codex=": "names no model",
            "codex=gpt-5": "omega-1, omega-2, omega-mini",
            "codex=omega-2@max": "not a thinking level",
            "ollama=llama3.2:3b@high": "docs/workflows.md",
            ";": "name at least one provider",
        }
        for text, wanted in cases.items():
            with self.assertRaises(ValueError, msg=text) as caught:
                self.parse(text)
            self.assertIn(wanted, str(caught.exception), text)

    def test_a_provider_named_twice_is_refused_not_overwritten(self):
        with self.assertRaises(ValueError) as caught:
            self.parse("codex=omega-1@high; codex=omega-2")
        self.assertIn("`codex` is named twice", str(caught.exception))

    def test_with_no_model_list_the_prompt_and_its_refusal_still_show_the_format(self):
        signed_out = tuple(
            replace(s, status=providers.Status.NOT_SIGNED_IN, models=()) if s.provider.name == "codex" else s
            for s in machine().provider_states
        )
        bare, selection = machine(provider_states=signed_out), {"providers": ["codex"]}
        self.assertTrue(any("codex=<model>" in note for note in self.question.notes(bare, selection)))
        with self.assertRaises(ValueError) as caught:
            self.question.parse(questions._typed_default(self.question, self.question.default(bare, selection)),
                                bare, selection)
        self.assertIn("for example codex=<model>", str(caught.exception))

    def test_an_added_provider_can_stay_the_default_and_fallback_when_init_asks_again(self):
        with tempfile.TemporaryDirectory() as scratch:
            raw = spec.migrate({**answers(Path(scratch)), "format": spec.FORMAT})
            raw.pop("project")
            raw.update(providers=["claude_code", "ollama", "local_echo"], primary="local_echo", fallback="claude_code",
                       custom_providers={"local_echo": {"command": "/opt/tools/echo", "args": ["{model}"],
                                                        "family": "local_open_weight"}})
            raw["models"]["local_echo"] = ["echo-1"]
            added = spec.enabled_custom(raw)[0]
            here = machine(provider_states=(*machine().provider_states,
                                            providers.ProviderState(added, providers.Status.UNVERIFIED, "fixture")))
            preset = initflow._preset(raw)
            got = initflow._asked(preset, questions.ask_all(here, preset=preset, accept_defaults=True,
                                                           out=io.StringIO()))
        self.assertEqual((got["primary"], got["fallback"]), ("local_echo", "claude_code"))
        self.assertEqual(got["providers"].count("local_echo"), 1)
        self.assertEqual(got["models"]["local_echo"], ["echo-1"])

    def test_a_bad_answer_is_asked_again_at_the_prompt(self):
        replies = iter(["/tmp/somewhere", "cxo", "claude_code", "ollama", "codex=gpt-5", "codex=omega-2,omega-1",
                        "", "", "", "", "", "n", "", "n"])
        out = io.StringIO()
        got = questions.ask_all(machine(), preset={}, out=out, read=lambda prompt: next(replies))
        self.assertEqual(got["models"]["codex"], ["omega-2", "omega-1"])
        text = out.getvalue()
        self.assertIn("does not offer the model `gpt-5`", text)
        self.assertIn("Format: <provider>=<model>", text)
        self.assertIn("Example built from the lists above: claude_code=sonnet@low,opus; codex=omega-1@low,omega-2", text)

    def test_the_prompt_shows_each_providers_models_and_levels(self):
        lines = [o.note for o in self.question.options(machine(), self.selection)]
        self.assertIn("this sign-in offers: omega-1, omega-2, omega-mini", lines[1])
        self.assertIn("low, medium, high, max for omega-1", lines[1])
        self.assertIn("lists no models", lines[0])

    def test_a_stored_model_the_sign_in_dropped_is_named_where_the_default_changes(self):
        preset = {"models": {"codex": ["gpt-5", "omega-2@high"], "claude_code": ["opus@low"]}}
        default, notes = questions._preset_default(self.question, preset, {}, machine(), self.selection)
        self.assertEqual(default, {"claude_code": ["opus@low"], "codex": ["omega-2@high"], "ollama": ["llama3.2:3b"]})
        self.assertTrue(any("`gpt-5`" in note for note in notes), notes)
        preset = {"models": {"codex": ["gpt-5"]}}
        default, notes = questions._preset_default(self.question, preset, {}, machine(), self.selection)
        self.assertEqual(default["codex"], ["omega-1"])
        self.assertIn("so the default shown for codex is omega-1", notes)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as scratch:
            questions.ask_all(machine(), preset={"home": scratch, "providers": ["codex"], **preset},
                              accept_defaults=True, out=out)
        self.assertIn("no longer usable: Codex CLI: this sign-in does not offer the model `gpt-5`", out.getvalue())

    def test_the_json_carries_the_same_data(self):
        described = {d["id"]: d for d in questions.describe(machine(), {"home": "/tmp/h", **self.selection})}
        models = described["models"]
        self.assertEqual(models["default"]["codex"], ["omega-1"])
        self.assertEqual([o["value"] for o in models["options"]], ["claude_code", "codex", "ollama"])
        self.assertTrue(any(note.startswith("Example built from") for note in models["notes"]))

    def test_the_answers_file_is_checked_against_the_lists_and_normalized(self):
        given = answers(Path("/tmp/home"), providers=["antigravity", "ollama"], primary="antigravity",
                        models={"antigravity": ["Sky Flash"], "ollama": ["llama3.2:3b"]})
        self.assertEqual(questions.complete(machine(), given)["models"]["antigravity"], ["sky-flash"])
        given["models"] = {"antigravity": ["Gemini 3.5 Flash (Low)"]}
        with self.assertRaises(KitError) as caught:
            questions.complete(machine(), given)
        self.assertIn("sky-2-low, sky-2-high, sky-flash", caught.exception.message)


class AnswersFileMigration(unittest.TestCase):
    def old(self, **changes):
        raw = {**answers(Path("/tmp/h")), "format": 1, "ollama_model": "llama3.1:8b",
               "providers": ["claude_code", "ollama", "codex"], "models": {"claude_code": "sonnet@low"}}
        raw.pop("project")
        return {**raw, **changes}

    def test_format_one_keeps_every_model_it_meant(self):
        got = spec.migrate(self.old())
        self.assertEqual(got["format"], spec.FORMAT)
        self.assertNotIn("ollama_model", got)
        # Codex had no model stored: the one that kit version meant is kept, to be reported, not replaced.
        self.assertEqual(got["models"], {"claude_code": ["sonnet@low"], "ollama": ["llama3.1:8b"], "codex": ["gpt-5"]})
        parsed = spec.parse(self.old(), known_features=KNOWN)
        self.assertEqual(parsed.model_of("ollama"), "llama3.1:8b")
        self.assertEqual(parsed.available("claude_code"), ("sonnet@low",))

    def test_a_current_file_comes_back_unchanged(self):
        current = spec.migrate(self.old())
        self.assertEqual(spec.migrate(current), current)

    def test_it_round_trips_through_the_file_in_the_new_shape(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "init-answers.json"
            original = spec.parse(self.old(), known_features=KNOWN)
            spec.save(original, path)
            self.assertEqual(spec.load(path, known_features=KNOWN), original)
            self.assertNotIn("ollama_model", path.read_text())

    def test_a_retired_provider_is_refused_with_the_command_that_removes_it(self):
        with self.assertRaises(KitError) as caught:
            spec.parse(self.old(providers=["claude_code", "ollama", "gemini"]), known_features=KNOWN)
        self.assertIn("no longer a provider", caught.exception.message)
        self.assertIn("arhugula provider disable gemini", caught.exception.fix)
        with self.assertRaises(KitError) as caught:
            spec.parse(self.old(providers=["gemini", "ollama"], primary="gemini"), known_features=KNOWN)
        self.assertIn("init --reconfigure", caught.exception.fix)

    def test_removing_a_retired_provider_leaves_a_file_that_parses(self):
        raw = self.old(providers=["claude_code", "ollama", "gemini"], fallback="gemini",
                       provider_settings={"gemini": {"timeout_seconds": 5}})
        cleaned = spec.without_provider(spec.migrate(raw), "gemini")
        parsed = spec.parse(cleaned, known_features=KNOWN)
        self.assertEqual((parsed.providers, parsed.fallback), (("claude_code", "ollama"), ""))

    def test_a_selected_provider_without_a_model_is_refused_with_the_fix(self):
        raw = spec.migrate(self.old())
        raw["models"].pop("codex")
        with self.assertRaises(KitError) as caught:
            spec.parse(raw, known_features=KNOWN)
        self.assertIn("arhugula provider enable codex --model", caught.exception.fix)


class CustomProviders(unittest.TestCase):
    def raw(self, name="local_echo", **entry):
        definition = {"command": "/opt/tools/echo", "args": ["--model", "{model}"], "family": "local_open_weight",
                      **entry}
        raw = spec.migrate({**answers(Path("/tmp/h")), "format": spec.FORMAT})
        raw.pop("project")
        raw["providers"] = [*raw["providers"], name]
        raw["models"] = {**raw["models"], name: ["echo-1"]}
        raw["custom_providers"] = {name: definition}
        return raw

    def test_one_parses_and_renders_as_the_generic_command_kind(self):
        parsed = spec.parse(self.raw(), known_features=KNOWN)
        home = Home(Path("/tmp/arhugula-home"))
        wanted = replace(parsed, providers=("ollama", "local_echo"), primary="ollama", fallback="")
        entry = render.render_config(wanted, home, render.targets(wanted, home)[0], render.fragments())[
            "runtime"]["external_cli_providers"][0]
        self.assertEqual(entry["kind"], "generic-command")
        self.assertEqual((entry["command"], entry["args"]), ("/opt/tools/echo", ["--model", "{model}"]))
        self.assertEqual((entry["prompt_transport"], entry["response_format"], entry["auth_check"]),
                         ("stdin", "text", False))

    def test_names_that_collide_are_refused(self):
        for name in ("claude_code", "gemini", "none", "Bad-Name"):
            with self.assertRaises(KitError, msg=name):
                spec.parse(self.raw(name), known_features=KNOWN)

    def test_prompt_in_the_arguments_needs_the_argument_transport(self):
        with self.assertRaises(KitError) as caught:
            spec.parse(self.raw(args=["{prompt}"]), known_features=KNOWN)
        self.assertIn("--prompt-transport arg", caught.exception.fix)
        spec.parse(self.raw(args=["{prompt}"], prompt_transport="arg"), known_features=KNOWN)

    def test_only_the_runtimes_own_values_are_accepted(self):
        for key, bad in (("family", "gemini"), ("prompt_transport", "file"), ("response_format", "xml")):
            with self.assertRaises(KitError, msg=key):
                spec.parse(self.raw(**{key: bad}), known_features=KNOWN)

    def test_a_custom_provider_takes_no_level_and_says_why(self):
        provider = spec.parse(self.raw(), known_features=KNOWN).provider("local_echo")
        with self.assertRaises(ModelRefused) as caught:
            resolve(provider, "echo-1@high", ())
        self.assertIn("--args", str(caught.exception))


@unittest.skipUnless(Path("/bin/zsh").is_file(), "the wrapper is a zsh script")
class LevelWrapper(unittest.TestCase):
    """The generated wrapper, run in front of a stand-in that records the argv it receives."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        self.record = self.dir / "argv"
        self.stand_in = self.dir / "stand-in"
        self.stand_in.write_text('#!/bin/sh\nfor word in "$@"; do printf \'%s\\0\' "$word"; done > "$RECORD"\n')
        self.stand_in.chmod(0o755)

    def through(self, name: str, argv: list[str], real: Path | None = None) -> subprocess.CompletedProcess:
        wrapper = self.dir / f"provider-{name}"
        wrapper.write_text(modelwrap.script(by_name(name), str(real or self.stand_in)))
        wrapper.chmod(0o755)
        return subprocess.run([str(wrapper), *argv], env={**os.environ, "RECORD": str(self.record)},
                              capture_output=True, text=True)

    def received(self) -> list[str]:
        return self.record.read_bytes().decode().split("\0")[:-1]

    def test_claude_gets_its_effort_option_and_the_empty_tools_argument_survives(self):
        runtime_argv = ["--print", "--output-format", "json", "--tools", "", "--permission-mode", "dontAsk",
                        "--model", "sonnet@high"]
        self.assertEqual(self.through("claude_code", runtime_argv).returncode, 0)
        self.assertEqual(self.received(), ["--print", "--output-format", "json", "--tools", "",
                                           "--permission-mode", "dontAsk", "--model", "sonnet", "--effort", "high"])

    def test_codex_gets_its_reasoning_effort_setting_before_the_stdin_marker(self):
        runtime_argv = ["exec", "--json", "-c", 'web_search="disabled"', "-m", "omega-1@max", "-"]
        self.assertEqual(self.through("codex", runtime_argv).returncode, 0)
        self.assertEqual(self.received(), ["exec", "--json", "-c", 'web_search="disabled"', "-m", "omega-1",
                                           "-c", 'model_reasoning_effort="max"', "-"])

    def test_an_argv_without_a_level_passes_through_byte_for_byte(self):
        for name, argv in (
            ("claude_code", ["--tools", "", "--model", "sonnet", ""]),
            ("claude_code", ["auth", "status", "--json"]),
            ("codex", ["login", "status"]),
            ("codex", ["", "-m", "omega-1", " spaced  word ", "$HOME", "*", "a'b\"c", "x@y"]),
        ):
            self.assertEqual(self.through(name, argv).returncode, 0)
            self.assertEqual(self.received(), argv, argv)

    def test_a_missing_real_executable_fails_loudly_with_the_fix(self):
        done = self.through("claude_code", ["--model", "sonnet"], real=self.dir / "gone")
        self.assertEqual(done.returncode, 127)
        self.assertIn("is gone", done.stderr)
        self.assertIn("arhugula provider enable claude_code --command", done.stderr)

    def test_render_points_the_runtime_at_the_wrapper_and_bakes_the_real_path(self):
        home = Home(self.dir / "home")
        raw = spec.migrate({**answers(home.root), "format": spec.FORMAT})
        raw.pop("project")
        raw["commands"] = {"claude_code": str(self.stand_in)}
        wanted = spec.parse(raw, known_features=KNOWN)
        entry = render.render_config(wanted, home, render.targets(wanted, home)[0], render.fragments())[
            "runtime"]["external_cli_providers"][0]
        self.assertEqual(entry["command"], str(home.bin / "provider-claude_code"))
        scripts = render.wrappers(wanted, home)
        self.assertEqual(list(scripts), [home.bin / "provider-claude_code"])
        self.assertIn(str(self.stand_in), scripts[home.bin / "provider-claude_code"])
        modelwrap.sync(home, scripts)
        (home.bin / "provider-codex").write_text(modelwrap.script(by_name("codex"), "/old/codex"))
        modelwrap.sync(home, scripts)
        self.assertEqual(sorted(p.name for p in home.bin.iterdir()), ["provider-claude_code"])
        self.assertTrue(os.access(home.bin / "provider-claude_code", os.X_OK))


class ServedBy(unittest.TestCase):
    def test_a_fallback_that_served_is_named_with_the_reason(self):
        chats = [servedby.Chat("codex", "gpt-5", True, "not supported when using Codex with a ChatGPT account"),
                 servedby.Chat("ollama", "llama3.2:3b", False)]
        line = servedby.served_line(chats, "codex", "gpt-5")
        self.assertEqual(line, "served by ollama/llama3.2:3b, not by codex/gpt-5: codex failed "
                               "(not supported when using Codex with a ChatGPT account)")

    def test_nothing_is_said_when_the_named_provider_served(self):
        self.assertEqual(servedby.served_line([servedby.Chat("codex", "m", False)], "codex", "m"), "")
        retried = [servedby.Chat("codex", "m", True, "timeout"), servedby.Chat("codex", "m", False)]
        self.assertEqual(servedby.served_line(retried, "codex", "m"), "")
        self.assertEqual(servedby.served_line([], "codex", "m"), "")

    def test_a_missing_span_store_says_nothing(self):
        self.assertEqual(servedby.after_run(Path("/nonexistent/spans.sqlite"), 0, "codex", "m"), "")


class SpanStore(unittest.TestCase):
    """The query behind the served-by line, against a span store the test builds."""

    def store(self, directory: str, spans: list[tuple]) -> Path:
        path = Path(directory) / "spans.sqlite"
        with contextlib.closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("create table spans (span_id text primary key, trace_id text, name text, "
                         "start_time_ns integer, status_code integer, status_message text, attributes_json text)")
            conn.executemany("insert into spans values (?, ?, ?, ?, ?, ?, ?)",
                             [(f"s{i}", *span) for i, span in enumerate(spans)])
        return path

    @staticmethod
    def chat(trace: str, at: int, provider: str, model: str, failed: bool, reason: str = "") -> tuple:
        facts = f'{{"gen_ai.provider.name": "{provider}", "gen_ai.request.model": "{model}"}}'
        return (trace, f"chat {model}", at, servedby.ERROR if failed else 1, reason, facts)

    def run_of(self, trace: str, at: int) -> list[tuple]:
        return [(trace, servedby.ROOT, at, 1, "", "{}"),
                self.chat(trace, at + 1, "codex", "omega-1", True, "not supported"),
                self.chat(trace, at + 2, "ollama", "llama3.2:3b", False)]

    def test_the_one_run_since_the_start_is_read_in_order(self):
        with tempfile.TemporaryDirectory() as scratch:
            store = self.store(scratch, [*self.run_of("old", 10), *self.run_of("new", 100)])
            self.assertEqual(servedby.after_run(store, 50, "codex", "omega-1"),
                             "served by ollama/llama3.2:3b, not by codex/omega-1: codex failed (not supported)")

    def test_overlapping_runs_say_nothing(self):
        with tempfile.TemporaryDirectory() as scratch:
            store = self.store(scratch, [*self.run_of("one", 100), *self.run_of("two", 110)])
            self.assertEqual(servedby.after_run(store, 50, "codex", "omega-1"), "")

    def test_a_home_path_with_url_characters_is_read_and_nothing_is_created(self):
        with tempfile.TemporaryDirectory() as scratch:
            odd = Path(scratch) / "a#b?c%41"
            odd.mkdir()
            store = self.store(str(odd), self.run_of("new", 100))
            self.assertTrue(servedby.after_run(store, 50, "codex", "omega-1").startswith("served by ollama"))
            self.assertEqual(sorted(p.name for p in Path(scratch).iterdir()), ["a#b?c%41"])
            self.assertEqual(sorted(p.name for p in odd.iterdir()), ["spans.sqlite"])


class RunModel(unittest.TestCase):
    """`run --provider --model`: refused when the provider's own list refuses it, noted when unavailable."""

    def spec(self) -> spec.Spec:
        raw = spec.migrate({**answers(Path("/tmp/h")), "format": spec.FORMAT})
        raw.pop("project")
        raw["providers"] = [*raw["providers"], "codex"]
        raw["models"] = {**raw["models"], "codex": ["omega-1@high"]}
        return spec.parse(raw, known_features=KNOWN)

    def note(self, name: str, model: str) -> str:
        lists = offered()
        out = io.StringIO()
        with mock.patch.object(verbs_run, "offers", lambda _spec, p: lists.get(p.name, ())), \
                contextlib.redirect_stderr(out):
            verbs_run._note_unavailable(self.spec(), by_name(name), model)
        return out.getvalue()

    def test_a_level_the_models_own_list_lacks_is_refused(self):
        with self.assertRaises(KitError) as caught:
            self.note("codex", "omega-2@max")
        self.assertIn("`max` is not a thinking level of `omega-2`", str(caught.exception))

    def test_a_model_the_sign_in_does_not_offer_is_refused(self):
        with self.assertRaises(KitError) as caught:
            self.note("codex", "gpt-9")
        self.assertIn("does not offer the model `gpt-9`", str(caught.exception))

    def test_an_offered_model_not_made_available_gets_one_note_with_the_fix(self):
        line = self.note("codex", "omega-2@low")
        self.assertEqual(line.count("\n"), 1)
        self.assertIn("arhugula provider enable codex --model omega-1@high --model omega-2@low", line)

    def test_an_ollama_model_not_pulled_says_how_to_pull_it(self):
        line = self.note("ollama", "qwen9:1b")
        self.assertIn("ollama pull qwen9:1b", line)
        self.assertEqual(line.count("\n"), 1)

    def test_an_available_model_says_nothing(self):
        self.assertEqual(self.note("codex", "omega-1@low"), "")


def deployment_with(**changes) -> Deployment:
    """A deployment with Codex (two models) and an added provider, without a home on disk."""
    raw = spec.migrate({**answers(Path("/tmp/h")), "format": spec.FORMAT})
    raw.pop("project")
    raw.update(providers=["claude_code", "ollama", "codex", "local_echo"],
               custom_providers={"local_echo": {"command": "/opt/tools/echo", "args": ["{model}"],
                                                "family": "local_open_weight"}})
    raw["models"] = {**raw["models"], "codex": ["omega-1@high", "omega-2"], "local_echo": ["echo-1"]}
    raw.update(changes)
    return Deployment(Home(Path("/tmp/h")), spec.parse(raw, known_features=KNOWN), {})


def fixture_state(_spec, provider: providers.Provider) -> providers.ProviderState:
    return providers.ProviderState(provider, providers.Status.READY, "fixture", models=offered().get(provider.name, ()))


def run_verb(verb, deployment: Deployment, **args) -> tuple[list[spec.Spec], str]:
    """Run a configuration verb against `deployment`: what it would apply, and what it printed."""
    applied: list[spec.Spec] = []
    out = io.StringIO()
    with mock.patch.object(deploy, "open_deployment", lambda: deployment), \
            mock.patch.object(deploy, "apply", lambda _d, changed: applied.append(changed)), \
            mock.patch.object(verbs_config, "_state", fixture_state), contextlib.redirect_stdout(out):
        verb(argparse.Namespace(**args))
    return applied, out.getvalue()


ROLE = ("runtime", "routing_manifest", "per_role_bindings", "reviewer")
WORKLOAD = ("runtime", "routing_manifest", "per_workload_overrides", "research")


class DanglingBindings(unittest.TestCase):
    """A provider or model a stored routing binding names cannot be taken away under it."""

    def bound(self, path, provider: str, model: str, project: str = "") -> Deployment:
        plain = deployment_with()
        entry = {"provider": provider, "model": model}
        value = ({"preferred_model_binding": entry, "layer_budget_overrides": {}, "fallback_chain_ref": "default"}
                 if path == ROLE else {"model_binding_override": entry})
        return replace(plain, spec=overlay.set_value(plain.spec, project, path, value))

    def refused(self, verb, deployment, **args) -> KitError:
        with self.assertRaises(KitError) as caught:
            run_verb(verb, deployment, **args)
        return caught.exception

    def test_disabling_a_provider_a_role_is_bound_to_is_refused_with_the_unbind_verb(self):
        error = self.refused(verbs_config._provider_disable, self.bound(ROLE, "codex", "omega-1@high"), name="codex")
        self.assertIn("role reviewer -> codex/omega-1@high", error.message)
        self.assertEqual(error.fix, "arhugula routing role unbind reviewer first")
        applied, _ = run_verb(verbs_config._provider_disable, deployment_with(), name="codex")
        self.assertEqual(len(applied), 1)

    def test_enabling_without_a_bound_model_is_refused_and_keeping_it_at_any_level_passes(self):
        deployment = self.bound(WORKLOAD, "codex", "omega-1@high")
        error = self.refused(verbs_config._provider_enable, deployment, name="codex", model=["omega-2"], command=None)
        self.assertIn("models of codex that this leaves out: workload research -> codex/omega-1@high", error.message)
        self.assertEqual(error.fix, "arhugula routing workload clear research first")
        applied, _ = run_verb(verbs_config._provider_enable, deployment, name="codex",
                              model=["omega-2", "omega-1@low"], command=None)
        self.assertEqual(applied[0].available("codex"), ("omega-2", "omega-1@low"))

    def test_removing_an_added_provider_a_project_binds_is_refused_with_the_unset(self):
        error = self.refused(verbs_config._provider_remove,
                             self.bound(WORKLOAD, "local_echo", "echo-1", project="web"), name="local_echo")
        self.assertIn("workload research (project web) -> local_echo/echo-1", error.message)
        self.assertEqual(error.fix, "arhugula config unset routing_manifest.per_workload_overrides.research "
                                    "--project web first")


class StoredDisplayName(unittest.TestCase):
    """A format-1 file stored Antigravity's display name; it still counts as the model it names."""

    def deployment(self) -> Deployment:
        raw = {**answers(Path("/tmp/h")), "format": 1, "providers": ["claude_code", "ollama", "antigravity"],
               "models": {"antigravity": "Sky Flash"}, "ollama_model": "llama3.2:3b"}
        raw.pop("project")
        return Deployment(Home(Path("/tmp/h")), spec.parse(raw, known_features=KNOWN), {})

    def test_routing_run_validate_and_the_models_table_count_it_as_available(self):
        stored, agy, lists = self.deployment().spec, by_name("antigravity"), offered()
        self.assertEqual(stored.available("antigravity"), ("Sky Flash",))
        with mock.patch.object(verbs_config, "offers", lambda _s, p: lists.get(p.name, ())):
            self.assertEqual(verbs_config._available_model(stored, agy, "sky-flash"), "sky-flash")
        self.assertEqual(verbs_run._binding_note(stored, "antigravity", "sky-flash", lists["antigravity"]), "")
        with mock.patch.object(verbs_run, "offers", lambda _s, p: lists.get(p.name, ())), \
                contextlib.redirect_stderr(io.StringIO()) as noted:
            verbs_run._note_unavailable(stored, agy, "sky-flash")
        self.assertEqual(noted.getvalue(), "")
        _, printed = run_verb(verbs_config._provider_models, self.deployment(), name="antigravity")
        self.assertRegex(printed, r"sky-flash +default")
        self.assertNotIn("not in that list", printed)


class RunVerb(unittest.TestCase):
    """`arhugula run --provider`: what reaches the runtime, and where the kit's own lines go."""

    def run_with(self, **args) -> tuple[list, str, str]:
        deployment = deployment_with()
        sent: list = []
        out, err = io.StringIO(), io.StringIO()
        given = dict(manifest="minimal.toml", project=None, provider="codex", model="", json=True, daemon=False)
        with mock.patch.object(deploy, "open_deployment", lambda: deployment), \
                mock.patch.object(verbs_run, "target_of", lambda _d, _p: render.targets(deployment.spec, deployment.home)[0]), \
                mock.patch.object(verbs_run, "resolve_manifest", lambda _d, _t, m: Path(m)), \
                mock.patch.object(verbs_run, "offers", lambda _s, p: offered().get(p.name, ())), \
                mock.patch.object(verbs_run, "_exec_harness", lambda _d, _t, words, label: sent.extend(words) or 0), \
                mock.patch.object(servedby, "after_run", lambda *_: "served by ollama/llama3.2:3b, not by codex"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            verbs_run._run(argparse.Namespace(**{**given, **args}))
        return sent, out.getvalue(), err.getvalue()

    def test_with_json_the_kits_lines_go_to_standard_error(self):
        sent, out, err = self.run_with(model="omega-mini")
        self.assertEqual(out, "")
        self.assertIn("note: `omega-mini` is not one of the models available", err)
        self.assertIn("served by ollama/llama3.2:3b", err)
        self.assertEqual(sent[-2:], ["--output", "json"])

    def test_a_display_title_reaches_the_runtime_as_the_models_id(self):
        sent, _, _ = self.run_with(model="Omega 2@high")
        self.assertEqual(sent[sent.index("--model") + 1], "omega-2@high")


class WrapperFiles(unittest.TestCase):
    """What the kit writes, removes and accepts under `<home>/bin`."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Home(Path(scratch.name) / "home")
        self.home.bin.mkdir(parents=True)

    def executable(self, name: str, text: str) -> Path:
        path = self.home.bin / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def spec_with(self, **commands: str) -> spec.Spec:
        raw = spec.migrate({**answers(self.home.root), "format": spec.FORMAT})
        raw.pop("project")
        raw["commands"] = commands
        return spec.parse(raw, known_features=KNOWN)

    def test_sync_keeps_a_provider_file_the_kit_did_not_write(self):
        mine = self.executable("provider-mine", "#!/bin/sh\necho the operator's own\n")
        old = self.executable("provider-codex", modelwrap.script(by_name("codex"), "/old/codex"))
        modelwrap.sync(self.home, {self.home.bin / "provider-claude_code": "#!/bin/zsh -f\n"})
        self.assertTrue(mine.is_file())
        self.assertFalse(old.exists())

    def test_the_kits_own_wrapper_is_refused_as_a_providers_command(self):
        wrapper = self.executable("provider-codex", modelwrap.script(by_name("codex"), "/old/codex"))
        with self.assertRaises(KitError) as caught:
            verbs_config._executable(str(wrapper))
        self.assertIn("the kit's own wrapper", caught.exception.message)
        with self.assertRaises(KitError) as caught:
            render.wrappers(self.spec_with(claude_code=str(wrapper)), self.home)
        self.assertIn("--command", caught.exception.fix)

    def test_a_bare_command_override_is_found_on_path_and_a_missing_one_is_refused(self):
        real = self.executable("my-claude", "#!/bin/sh\n")
        with mock.patch.dict(os.environ, {"PATH": str(self.home.bin)}):
            scripts = render.wrappers(self.spec_with(claude_code="my-claude"), self.home)
            self.assertIn(f"real='{real}'", scripts[self.home.bin / "provider-claude_code"])
            with self.assertRaises(KitError) as caught:
                render.wrappers(self.spec_with(claude_code="not-there"), self.home)
        self.assertIn("`not-there`", caught.exception.message)
        self.assertIn("arhugula provider enable claude_code --command", caught.exception.fix)


if __name__ == "__main__":
    unittest.main()
