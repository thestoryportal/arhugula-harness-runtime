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

Upstream pin: `a9761ddca7f1a07cd1c0ccd9bcf550c2dc951ab5`

This version first pinned `2e1ba1f764be27601441936692da2b6c30d61f7c`, and it moved to the pin above for upstream pull request 1760.

### What this version provides

The list follows the feature groups of [the kit overview](README.md).

- **Install and operate.** `init` checks every dependency, asks 14 questions, runs 18 preflight checks, installs the pin and runs smoke workflows. The `arhugula` command does everything after that, and `arhugula --version` prints the kit version and the upstream pin.
- **An install that proves what it installed.** Every harness wheel carries the version `0.0.0`, so the package cache could not tell one commit's build from another's, and an upgrade could install the earlier commit's files (*witnessed*). The installer now installs the wheels without the cache. Its `verify` step compares the hash of every installed harness file with the wheel just built, and a mismatch stops the install with exit code 78. If an earlier kit version upgraded your deployment, run `arhugula upgrade --reinstall` once: see [Rebuild at the same pin](docs/upgrade.md#rebuild-at-the-same-pin).
- **Providers.** Three subscription command-line providers (Claude Code, Codex and Antigravity), two hosted API providers with keys in the macOS keychain, and local Ollama, with `arhugula provider ollama-host` to set its address. The kit does not offer the Gemini CLI, because Google deprecated it.
- **Models and thinking levels.** The models come from each tool's own list. `arhugula provider models` shows them, and init question 5 asks for them (answers file format 2, with `models`; an older file is migrated). A thinking level is written `<model>@<level>` for Claude Code and Codex (*kit extension*). [Choose a model and a thinking level](docs/providers.md#choose-a-model-and-a-thinking-level) gives the command for each place to choose one.
- **Your own provider.** `arhugula provider add` and `arhugula provider remove` add any command that reads a prompt and prints a reply.
- **Who served a run.** When the provider you named failed and the fallback served the step, the run prints a `served by` line. A stored model that a tool no longer offers is reported by `provider check` and `doctor`.
- **Codex from `2e1ba1f7…` on.** Three runs with `--provider codex` at upstream commit `2e1ba1f7…` were each served by Codex, with no error (*witnessed*). Upstream pull request 1753 fixed it, and the kit pins a commit that holds the fix.
- **Routing.** One fallback chain serves every step, with overrides for one run and verbs for finer routing.
- **Topologies and multi-agent execution.** The six upstream topologies, and `arhugula workflow new` to create a manifest from one.
- **Approval gates.** Gates that ask at the terminal, and a policy for what a gate approves without asking. The kit sets a step deadline of 960 seconds and a run limit of 3600 seconds in every generated config (*kit extension*). A gate can then wait its own 900 seconds. The runtime's own 30 and 60 seconds failed a gate answered after 45 seconds (*upstream limit*, *witnessed*).
- **Validators.** Verbs to bind a validator class to a step and to test the bindings.
- **Prompts and skills.** Versioned prompts, skills for each project, and a hook that activates skills.
- **Memory.** Memory for each project, with your review before a captured memory is reused.
- **MCP tools.** Verbs to connect Model Context Protocol (MCP) tool servers, and the daemon. Tool servers of different kinds can be connected together: a `stdio` server under tier 3 and an HTTP server both ran, and both runs ended `status: completed` (*witnessed*).
- **Tools and permissions.** [Give agents tools](docs/workflows.md#give-agents-tools) says which steps and providers can use tools and how to connect a server. [Set what a gate approves without asking](docs/security-and-isolation.md#set-what-a-gate-approves-without-asking) says who approves a tool call. [Run an agent that acts with its own tools](docs/providers.md#run-an-agent-that-acts-with-its-own-tools) and the example `examples/workflows/agent-acts.toml` show a subscription agent that acts (*witnessed*).
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
| 1753 | The runtime accepts the reply of Codex CLI 0.169. | A run with `--provider codex` is served by Codex. |
| 1760 | The runtime closes its tool-server connections in an order that lets any two connected servers shut down cleanly. It fixes upstream issue 1756. | A run with two tool servers configured, for example a `stdio` client under tier 3 and an HTTP client, ends `status: completed` (*witnessed*). Before the fix, such a run ended with `CancelledError: Cancelled via cancel scope`. |

## Sources

- `PIN`: the upstream commit
- `docs/reference/cli.md`: the verbs this version provides
- `lib/arhugula_kit/questions.py` and `lib/arhugula_kit/preflight.py`: the 14 questions and the 18 checks
- The upstream commit log at the pin, for pull requests 1750, 1751, 1752 and 1760
