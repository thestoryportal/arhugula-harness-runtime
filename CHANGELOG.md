# Changelog

This page is for everyone who installs, operates or reviews the kit.
It lists each kit version, newest first, with the upstream commit that version pins.
Use it to see what a version provides and which upstream changes it relies on.

The kit installs the upstream harness, `thestoryportal/arhugula-harness`, at one commit.
The file `PIN` at the kit root holds that commit.
To move a deployment to another pin, read [the upgrade guide](docs/upgrade.md).
For what upstream lacks at a pin, read [the known gaps](docs/reference/known-gaps.md).

## 0.1.0 (2026-11-15)

The first version of the kit.

Upstream pin: `0a75b1d06707faebee892f8f55ee04f1a2b20b28`

### What this version provides

The list follows the feature groups of [the kit overview](README.md).

- **Install and operate.** `init` checks every dependency, asks 14 questions, runs 18 preflight checks, installs the pin and runs smoke workflows. The `arhugula` command does everything after that, and `arhugula --version` prints the kit version and the upstream pin.
- **Providers.** Four subscription command-line providers, two hosted API providers with keys in the macOS keychain, and local Ollama, with `arhugula provider ollama-host` to set its address.
- **Routing.** One fallback chain serves every step, with overrides for one run and verbs for finer routing.
- **Topologies and multi-agent execution.** The six upstream topologies, and `arhugula workflow new` to create a manifest from one.
- **Approval gates.** Gates that ask at the terminal, and a policy for what a gate approves without asking.
- **Validators.** Verbs to bind a validator class to a step and to test the bindings.
- **Prompts and skills.** Versioned prompts, skills for each project, and a hook that activates skills.
- **Memory.** Memory for each project, with your review before a captured memory is reused.
- **MCP tools.** Verbs to connect Model Context Protocol (MCP) tool servers, and the daemon.
- **Pause and resume.** Durable pause, webhook notification, and verbs to answer a held gate.
- **Audit signing.** A key generator, signing of every new audit entry, and verification.
- **Observability.** The local span store, and a trace stack in the kit's own Lima virtual machine with seven dashboards and seven alert rules.
- **Evaluation.** The holdout loop and drift checks.
- **Isolation.** Tier 3: tool calls under gVisor inside the virtual machine.
- **Agent context.** Instructions for an agent that operates the deployment, and a section for attached projects.
- **Documentation.** These pages, with [a command reference](docs/reference/cli.md) generated from the program.

### Upstream changes at this pin that the kit relies on

Each is a pull request of `thestoryportal/arhugula-harness`.

| Pull request | Change | Why the kit relies on it |
| --- | --- | --- |
| 1750 | The first-run refusal names its cause. | A fresh run that the runtime refuses says why, and the kit passes that message on. |
| 1751 | `--model` works without `--provider`. | `arhugula run --model <model>` applies the model to an enabled provider, or is refused. |
| 1752 | The runtime writes the local span store. | `arhugula trace list` works with no bridge process. |

## Sources

- `PIN`: the upstream commit
- `docs/reference/cli.md`: the verbs this version provides
- `lib/arhugula_kit/questions.py` and `lib/arhugula_kit/preflight.py`: the 14 questions and the 18 checks
- The upstream commit log at the pin, for pull requests 1750, 1751 and 1752
