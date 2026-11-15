"""The VM choice, the preflight checks that need no machine, and the Lima helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arhugula_kit import lima, preflight, vm
from arhugula_kit.layout import KIT_VM_NAME, Home
from arhugula_kit.preflight import Level, Subject

from tests.support import answers, machine

KIT = {"enabled": True, "engine": "kit", "lima_home": "", "instance": ""}
NONE = {"enabled": False, "engine": "none", "lima_home": "", "instance": ""}


def check(check_id: str, subject: Subject) -> preflight.Finding:
    return next(c for c in preflight.CHECKS if c.id == check_id).run(subject)


class VmChoice(unittest.TestCase):
    def setUp(self):
        self.home = Home(Path("/tmp/arhugula-home"))

    def test_the_kits_vm_is_located_from_the_home(self):
        ref = vm.ref_of(KIT, self.home)
        self.assertEqual((ref.lima_home, ref.name, ref.kit_owned), (self.home.lima, KIT_VM_NAME, True))

    def test_an_existing_instance_is_the_operators(self):
        ref = vm.ref_of({"enabled": True, "engine": "existing", "lima_home": "/l", "instance": "x"}, self.home)
        self.assertEqual((ref.lima_home, ref.name, ref.kit_owned), (Path("/l"), "x", False))

    def test_no_engine_means_no_vm(self):
        self.assertIsNone(vm.ref_of(NONE, self.home))

    def test_the_kits_vm_sees_fixed_paths_and_an_existing_one_sees_the_home(self):
        self.assertEqual(vm.project_dir(vm.ref_of(KIT, self.home), self.home), "/arhugula/observability")
        theirs = lima.VmRef(Path("/l"), "x", kit_owned=False)
        self.assertEqual(vm.project_dir(theirs, self.home), str(self.home.observability))

    def test_an_instance_for_another_cpu_is_refused_with_both_ways_out(self):
        other = "x86_64" if lima.host_arch() == "aarch64" else "aarch64"
        refusal = vm.emulation_refusal(lima.Instance(Path("/l"), "old", "Stopped", "qemu", other, 2, 1))
        self.assertIn(other, refusal.message)
        self.assertIn("arhugula observability vm create", refusal.fix)
        self.assertIn("lima-additional-guestagents", refusal.fix)


class LimaHelpers(unittest.TestCase):
    def test_a_short_home_leaves_room_for_the_sockets(self):
        self.assertGreater(lima.socket_path_budget(Path("/Users/someone/arhugula/lima"), "arhugula"), 0)

    def test_a_deep_home_does_not(self):
        deep = Path("/Users/someone") / ("very-long-directory-name/" * 4) / "lima"
        self.assertLess(lima.socket_path_budget(deep, "arhugula"), 0)

    def test_the_host_architecture_uses_limas_spelling(self):
        self.assertIn(lima.host_arch(), ("aarch64", "x86_64"))


class PreflightWithoutAMachine(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Home(Path(self.scratch.name) / "home")

    def subject(self, mach=None, **changes) -> Subject:
        return Subject(mach or machine(), answers(self.home.root, **changes), self.home)

    def test_the_eighteen_checks_are_documented(self):
        self.assertEqual([c.id for c in preflight.CHECKS], [f"P{n}" for n in range(1, 19)])
        for item in preflight.CHECKS:
            self.assertTrue(item.fails_when and item.fix, item.id)

    def test_a_non_mac_fails(self):
        self.assertIs(check("P1", self.subject(machine(system="Linux", macos_version=""))).level, Level.FAIL)

    def test_missing_uv_fails_with_the_tables_command(self):
        finding = check("P2", self.subject(machine(uv=None)))
        self.assertIs(finding.level, Level.FAIL)
        self.assertEqual(finding.fix, "brew install uv")

    def test_missing_python_carries_an_offer(self):
        finding = check("P3", self.subject(machine(python312="")))
        self.assertEqual(finding.offer, ("uv", "python", "install", "3.12"))

    def test_a_home_inside_a_checkout_fails(self):
        (self.home.root / ".git").mkdir(parents=True)
        self.assertIs(check("P5", self.subject()).level, Level.FAIL)

    def test_a_signed_out_default_provider_fails_and_a_spare_one_warns(self):
        from arhugula_kit import providers

        def signed_out(name: str):
            return tuple(
                providers.ProviderState(s.provider, providers.Status.NOT_SIGNED_IN, "signed out", fix="sign in")
                if s.provider.name == name else s
                for s in machine().provider_states
            )

        self.assertIs(check("P6", self.subject(machine(provider_states=signed_out("claude_code")))).level, Level.FAIL)
        spare = self.subject(machine(provider_states=signed_out("codex")), providers=["claude_code", "ollama", "codex"])
        self.assertIs(check("P6", spare).level, Level.WARN)

    def test_a_state_root_with_strangers_files_fails(self):
        self.home.state.mkdir(parents=True, mode=0o700)
        (self.home.state / "stray").write_text("x")
        finding = check("P8", self.subject())
        self.assertIs(finding.level, Level.FAIL)
        self.assertIn("marker-missing", finding.detail)

    def test_a_project_with_leftover_state_fails_with_the_archive_command(self):
        project = Path(self.scratch.name) / "project"
        (project / ".harness" / "memory").mkdir(parents=True)
        (project / ".harness" / "memory" / "r.json").write_text("{}")
        finding = preflight.project_finding(project)
        self.assertIs(finding.level, Level.FAIL)
        self.assertIn("arhugula state archive-legacy", finding.fix)

    def test_no_vm_chosen_skips_the_vm_check(self):
        self.assertIs(check("P14", self.subject()).level, Level.SKIP)

    def test_a_vm_without_lima_fails_with_the_install_command(self):
        finding = check("P14", self.subject(machine(limactl=None, lima_version=None), observability=KIT))
        self.assertIs(finding.level, Level.FAIL)
        self.assertEqual(finding.fix, "brew install lima")

    def test_an_old_lima_fails(self):
        finding = check("P14", self.subject(machine(lima_version=(1, 0, 7)), observability=KIT))
        self.assertIs(finding.level, Level.FAIL)

    def test_tier_three_without_a_vm_fails(self):
        self.assertIs(check("P15", self.subject(isolation_tier3=True)).level, Level.FAIL)

    def test_a_leftover_placeholder_fails(self):
        generated = Path(self.scratch.name) / "harness.toml"
        generated.write_text('[runtime]\nrepository_root = "{{REPOSITORY}}"\n')
        self.assertIs(preflight.placeholder_finding([generated]).level, Level.FAIL)

    def test_a_failed_check_stops_init_and_names_the_fix(self):
        from arhugula_kit.errors import KitError

        results = [(c, c.run(self.subject(machine(uv=None)))) for c in preflight.CHECKS if c.id == "P2"]
        with self.assertRaises(KitError) as caught:
            preflight.report(results, out=lambda line: None)
        self.assertIn("nothing was written", caught.exception.message)
        self.assertIn("brew install uv", caught.exception.fix)


if __name__ == "__main__":
    unittest.main()
