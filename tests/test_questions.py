"""The question table: defaults, parsing, and the two renderings of it."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from arhugula_kit import lima, questions
from arhugula_kit.errors import KitError
from arhugula_kit.questions import QUESTIONS

from tests.support import answers, machine


def by_id(question_id: str) -> questions.Question:
    return next(q for q in QUESTIONS if q.id == question_id)


def foreign_instance(arch: str) -> lima.Instance:
    return lima.Instance(Path("/elsewhere/lima"), "other", "Stopped", "qemu", arch, 2, 4 * 2**30)


class QuestionTable(unittest.TestCase):
    def test_there_are_fourteen_numbered_in_order(self):
        self.assertEqual([q.number for q in QUESTIONS], list(range(1, 15)))

    def test_every_question_says_why_and_what_its_default_is(self):
        for question in QUESTIONS:
            self.assertTrue(question.why and question.default_doc, question.id)

    def test_accepting_every_default_yields_a_complete_answer_set(self):
        with tempfile.TemporaryDirectory() as scratch:
            out = io.StringIO()
            got = questions.ask_all(machine(), preset={"home": scratch}, accept_defaults=True, out=out)
        self.assertEqual(set(got), {q.id for q in QUESTIONS})
        self.assertEqual(got["primary"], "claude_code")
        self.assertEqual(got["fallback"], "ollama")
        self.assertEqual(got["observability"]["engine"], "kit")

    def test_typed_answers_are_read_as_the_prompt_describes(self):
        replies = iter(["/tmp/somewhere", "co", "ollama", "none", "", "", "1", "none", "n", "", "n"])
        out = io.StringIO()
        got = questions.ask_all(machine(), preset={}, out=out, read=lambda prompt: next(replies))
        self.assertEqual(got["providers"], ["claude_code", "ollama"])
        self.assertEqual(got["primary"], "ollama")
        self.assertEqual(got["fallback"], "")
        self.assertEqual(got["workloads"], ["pipeline-automation"])
        self.assertEqual(got["features"], [])
        self.assertEqual(got["observability"]["engine"], "none")

    def test_a_wrong_answer_is_asked_again_not_defaulted(self):
        replies = iter(["relative/path", "/tmp/ok", *[""] * 12])
        out = io.StringIO()
        got = questions.ask_all(machine(), preset={}, out=out, read=lambda prompt: next(replies))
        self.assertEqual(got["home"], "/tmp/ok")
        self.assertIn("give an absolute path", out.getvalue())

    def test_codex_is_never_the_default_primary_when_another_is_selected(self):
        got = by_id("primary").default(machine(), {"providers": ["codex", "gemini"]})
        self.assertEqual(got, "gemini")


class Reconfigure(unittest.TestCase):
    def test_a_feature_enabled_by_a_verb_survives_being_asked_again(self):
        from arhugula_kit import initflow

        preset = {"features": ["memory", "deadlines"], "models": {"ollama": "x"}}
        got = initflow._asked(preset, {"features": ["memory", "data-flow"], "smoke": True})
        self.assertEqual(got["features"], ["memory", "data-flow", "deadlines"])
        self.assertEqual(got["models"], {"ollama": "x"})

    def test_such_a_feature_does_not_break_the_prompts_default(self):
        with tempfile.TemporaryDirectory() as scratch:
            got = questions.ask_all(
                machine(), preset={"home": scratch, "features": ["memory", "deadlines"]},
                accept_defaults=True, out=io.StringIO(),
            )
        self.assertEqual(got["features"], ["memory"])


class EngineQuestion(unittest.TestCase):
    def setUp(self):
        self.question = by_id("observability")
        self.answers = {"home": "/tmp/home"}

    def test_the_kits_own_vm_is_the_default_when_lima_is_installed(self):
        self.assertEqual(self.question.default(machine(), self.answers)["engine"], "kit")

    def test_without_lima_the_default_is_no_tier_and_kit_is_explained(self):
        bare = machine(limactl=None, lima_version=None)
        self.assertEqual(self.question.default(bare, self.answers)["engine"], "none")
        with self.assertRaises(ValueError) as caught:
            self.question.parse("kit", bare, self.answers)
        self.assertIn("Lima", str(caught.exception))
        self.assertEqual(self.question.parse("n", bare, self.answers)["engine"], "none")

    def test_an_existing_native_instance_is_offered_and_accepted(self):
        mach = machine(lima_instances=(foreign_instance(lima.host_arch()),))
        values = [option.value for option in self.question.options(mach, self.answers)]
        self.assertIn("/elsewhere/lima::other", values)
        got = self.question.parse("/elsewhere/lima::other", mach, self.answers)
        self.assertEqual((got["engine"], got["instance"]), ("existing", "other"))

    def test_an_instance_for_another_cpu_is_not_offered_and_says_why(self):
        other = "x86_64" if lima.host_arch() == "aarch64" else "aarch64"
        mach = machine(lima_instances=(foreign_instance(other),))
        values = [option.value for option in self.question.options(mach, self.answers)]
        self.assertNotIn("/elsewhere/lima::other", values)
        self.assertTrue(any("emulation" in note for note in self.question.notes(mach, self.answers)))
        with self.assertRaises(ValueError) as caught:
            self.question.parse("/elsewhere/lima::other", mach, self.answers)
        self.assertIn("emulating", str(caught.exception))

    def test_every_engine_state_is_shown_in_a_form_that_parses_back_to_itself(self):
        mach = machine(lima_instances=(foreign_instance(lima.host_arch()),))
        states = [
            {"enabled": False, "engine": "none", "lima_home": "", "instance": ""},
            {"enabled": True, "engine": "kit", "lima_home": "", "instance": ""},
            {"enabled": False, "engine": "kit", "lima_home": "", "instance": ""},
            {"enabled": True, "engine": "existing", "lima_home": "/elsewhere/lima", "instance": "other"},
            {"enabled": False, "engine": "existing", "lima_home": "/elsewhere/lima", "instance": "other"},
        ]
        for state in states:
            typed = questions._typed_default(self.question, state)
            self.assertEqual(self.question.parse(typed, mach, self.answers), state, typed)

    def test_tier_three_is_only_asked_when_a_vm_was_chosen(self):
        tier = by_id("isolation_tier3")
        self.assertFalse(tier.applies(machine(), {"observability": {"engine": "none"}}))
        self.assertTrue(tier.applies(machine(), {"observability": {"engine": "kit"}}))


class AnswersFile(unittest.TestCase):
    def test_a_missing_answer_is_refused_by_name(self):
        given = answers(Path("/tmp/home"))
        del given["primary"]
        with self.assertRaises(KitError) as caught:
            questions.complete(machine(), given)
        self.assertIn("primary", caught.exception.message)

    def test_a_question_that_does_not_apply_needs_no_answer(self):
        given = answers(Path("/tmp/home"), providers=["claude_code"], fallback="")
        del given["ollama_model"]
        self.assertIn("ollama_model", questions.complete(machine(), given))

    def test_the_json_rendering_carries_every_question(self):
        described = questions.describe(machine(), {"home": "/tmp/home"})
        self.assertEqual([d["id"] for d in described], [q.id for q in QUESTIONS])
        self.assertTrue(all(d["prompt"] and d["why"] and d["default_in_words"] for d in described))


if __name__ == "__main__":
    unittest.main()
