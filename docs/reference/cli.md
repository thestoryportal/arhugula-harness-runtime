# `arhugula` command reference

This page is for anyone who operates the deployment. It lists every verb, its arguments and one example.

It is generated from the program itself by `arhugula --help-markdown`. Do not edit it by hand: run `just docs-reference` to refresh it.

Each verb is marked with where its capability comes from:

- **runtime**: drives a capability of the harness runtime.
- **kit**: *kit extension*: added by this kit, not part of upstream.

## Verbs by group

- [`init`](#init): Create or reconfigure the deployment.
- [`doctor`](#doctor): Re-run the preflight checks; `--self-test` proves the runtime's refusals.
- [`upgrade`](#upgrade): Move the deployment to another upstream pin.
- [`relocate`](#relocate): Move the deployment home to another directory.
- [`uninstall`](#uninstall): Remove the deployment.
- [`project`](#project): Attach project repositories and choose the current one.
- [`run`](#run): Run a workflow.
- [`resume`](#resume): Resume a paused workflow.
- [`gate`](#gate): Answer a workflow that paused at an approval gate.
- [`status`](#status): Show the most recent ledger entries.
- [`workflow`](#workflow): List, create, validate and run workflow manifests.
- [`provider`](#provider): See, enable and check providers.
- [`routing`](#routing): Choose which provider and model serve which work.
- [`feature`](#feature): Switch named configuration features on and off.
- [`config`](#config): Show the generated config and set any runtime key.
- [`policy`](#policy): Set what an approval gate may approve on its own.
- [`mcp`](#mcp): Connect Model Context Protocol (MCP) tool servers.
- [`prompt`](#prompt): Author and select versioned prompts.
- [`skill`](#skill): Manage the skills agents can load.
- [`validator`](#validator): Bind validators to workflow steps.
- [`pause`](#pause): Durable pause and resume, and its journals.
- [`webhook`](#webhook): Deliver pause notifications to a URL.
- [`audit`](#audit): Sign and verify the audit ledger.
- [`isolation`](#isolation): Sandboxed tool execution.
- [`daemon`](#daemon): Run the harness as a long-lived service.
- [`memory`](#memory): Review and manage what the harness remembers.
- [`observability`](#observability): The trace stack: collector, Tempo and Grafana.
- [`trace`](#trace): Browse and export traces from the local span store.
- [`collector`](#collector): The local span store the runtime writes.
- [`logs`](#logs): Read the deployment's run logs.
- [`eval`](#eval): The holdout evaluation loop and drift checks.
- [`state`](#state): Inspect, back up and restore the state root.
- [`agent`](#agent): Context files for agent CLIs that operate this deployment.

## init

Create or reconfigure the deployment.

### `arhugula init`

Create the deployment, or re-verify or reconfigure an existing one.

Without a flag, init asks its questions in the terminal. Enter accepts the default shown.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula init [--answers FILE] [--yes] [--reconfigure] [--reinstall] [--questions-json] [--smoke] [--reverify]
```

| Argument | Meaning |
| --- | --- |
| `--answers` | Replay an answers file instead of asking. |
| `--yes` | Accept every default without asking. |
| `--reconfigure` | Ask every question again, with your earlier answers as defaults. |
| `--reinstall` | Rebuild the environment even when it is already at the pin. |
| `--questions-json` | Print the questions, defaults and options as JSON and exit. |
| `--smoke` | Run only the smoke workflows. |
| `--reverify` | Keep the stored answers without asking; regenerate and check everything. |

Example:

```sh
arhugula init --reconfigure
```


## doctor

Re-run the preflight checks; `--self-test` proves the runtime's refusals.

### `arhugula doctor`

Re-run every preflight check against the current deployment.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula doctor [--self-test]
```

| Argument | Meaning |
| --- | --- |
| `--self-test` | Prove on this machine that the runtime refuses what it should. |

Example:

```sh
arhugula doctor
```


## upgrade

Move the deployment to another upstream pin.

### `arhugula upgrade`

Rebuild the deployment at another upstream commit, keeping the earlier environment.

Rebuilds the environment, regenerates every config, has the runtime load each project's config, and runs the smoke workflows.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula upgrade [--pin SHA] [--reinstall] [--rollback]
```

| Argument | Meaning |
| --- | --- |
| `--pin` | The upstream commit to move to (default: the kit's PIN file). |
| `--reinstall` | Rebuild even when already at that commit. |
| `--rollback` | Return to the environment the last upgrade replaced. |

Example:

```sh
arhugula upgrade --pin 0a75b1d06707faebee892f8f55ee04f1a2b20b28
```


## relocate

Move the deployment home to another directory.

### `arhugula relocate`

Move the whole deployment home to another directory.

Moves the tree and rebuilds the environment, because its scripts carry their own path. Then it regenerates every config and the installation-state document, and has the runtime verify the state root at its new place.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula relocate <new_home>
```

| Argument | Meaning |
| --- | --- |
| `new_home` | The new home directory; it must not exist or must be empty. |

Example:

```sh
arhugula relocate ~/work/arhugula
```


## uninstall

Remove the deployment.

### `arhugula uninstall`

Remove the deployment. Without --yes it only lists what it would remove.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula uninstall [--yes] [--delete-state]
```

| Argument | Meaning |
| --- | --- |
| `--yes` | Really remove. |
| `--delete-state` | Also remove the state root, keys, secrets and backups. |

Example:

```sh
arhugula uninstall
```


## project

Attach project repositories and choose the current one.

### `arhugula project add`

Attach a project repository to this deployment.

The project gets its own config, ledger, memory and tenant id. The harness itself is not copied into it.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula project add <path> [--name NAME] [--workload WORKLOAD] [--gitignore] [--agent-context]
```

| Argument | Meaning |
| --- | --- |
| `path` | The project repository. |
| `--name` | The project's name and tenant id (default: from the directory name). |
| `--workload` | A workload class to bind; repeat for several (default: the deployment's). One of: `pipeline-automation`, `software-engineering`, `research`, `content-creation`. |
| `--gitignore` | Add `.harness/` to the project's .gitignore. |
| `--agent-context` | Append the harness section to the project's CLAUDE.md and AGENTS.md. |

Example:

```sh
arhugula project add ~/code/my-service --gitignore --agent-context
```

### `arhugula project list`

List attached projects; `*` marks the current one.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula project list
```

Example:

```sh
arhugula project list
```

### `arhugula project use`

Choose the project that verbs act on by default.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula project use <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | An attached project, or `default` for the deployment default. |

Example:

```sh
arhugula project use my-service
```

### `arhugula project show`

Show where a project's config, ledger and memory live.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula project show <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | An attached project, or `default`. |

Example:

```sh
arhugula project show my-service
```

### `arhugula project remove`

Detach a project. Its state is kept.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula project remove <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The project to detach. |

Example:

```sh
arhugula project remove my-service
```


## run

Run a workflow.

### `arhugula run`

Run a workflow on the current project.

The config's first fallback chain serves every step. --provider and --model override it for one run; a manifest's own binding does not select the provider. The run's stderr is also written to the home's logs/ directory.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula run <manifest> [--project NAME] [--provider PROVIDER] [--model MODEL] [--daemon] [--json]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--provider` | Dispatch every step to this enabled provider, for this run only. |
| `--model` | Dispatch every step to this model, for this run only. |
| `--daemon` | Send the run to the running daemon instead of starting a process. |
| `--json` | Print the full run result as JSON, including each step's reply. |

Example:

```sh
arhugula run ollama-first.toml --provider ollama
```


## resume

Resume a paused workflow.

### `arhugula resume`

Resume the latest durable pause of a workflow.

Needs the durable pause feature: arhugula pause enable.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula resume <manifest> [--project NAME] [--decision DECISION] [--edited-proposal EDITED_PROPOSAL] [--response-text RESPONSE_TEXT] [--reason REASON] [--json]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--decision` | The answer for a held approval gate. One of: `approve`, `edit`, `reject`, `respond`. |
| `--edited-proposal` | With --decision edit: a JSON object that replaces the payload. |
| `--response-text` | With --decision respond: the response text. |
| `--reason` | With --decision reject: the reason. |
| `--json` | Print the result or the refusal as JSON. |

Example:

```sh
arhugula resume my-workflow.toml --decision approve
```


## gate

Answer a workflow that paused at an approval gate.

### `arhugula gate list`

List the pause journals that may hold a paused workflow.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula gate list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula gate list
```

### `arhugula gate approve`

Approve the held gate of a paused workflow and continue it.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula gate approve <manifest> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula gate approve my-workflow.toml
```

### `arhugula gate deny`

Reject the held gate of a paused workflow.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula gate deny <manifest> [--project NAME] [--reason REASON]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--reason` | Why the action is rejected. |

Example:

```sh
arhugula gate deny my-workflow.toml --reason "wrong branch"
```


## status

Show the most recent ledger entries.

### `arhugula status`

Show the most recent entries of a project's state ledger.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula status [--project NAME] [--last LAST] [--json]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--last` | How many entries to show (default: 10). |
| `--json` | Print the summary as JSON. |

Example:

```sh
arhugula status --last 5
```


## workflow

List, create, validate and run workflow manifests.

### `arhugula workflow list`

List the manifests of the current project and of upstream's examples.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula workflow list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula workflow list
```

### `arhugula workflow new`

Create a manifest for a topology, derived from upstream's example for it.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula workflow new <topology> --name NAME [--project NAME] [--output OUTPUT]
```

| Argument | Meaning |
| --- | --- |
| `topology` | The topology pattern. One of: `single-threaded-linear`, `decentralized-handoff`, `parallelization`, `orchestrator-workers`, `hierarchical-delegation`, `evaluator-optimizer`. |
| `--name` | The workflow id and file name. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--output` | Write to this file instead of the project's workflows/ directory. |

Example:

```sh
arhugula workflow new evaluator-optimizer --name tagline-review
```

### `arhugula workflow validate`

Load a manifest through the runtime's loader. No provider is called.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula workflow validate <manifest> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula workflow validate tagline-review.toml
```

### `arhugula workflow run`

Run a workflow (the same as `arhugula run`).

Source: runtime (drives a capability of the harness runtime).

```text
arhugula workflow run <manifest> [--project NAME] [--provider PROVIDER] [--model MODEL] [--daemon] [--json]
```

| Argument | Meaning |
| --- | --- |
| `manifest` | A manifest file, or its name in the project's workflows/ or upstream's examples/. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--provider` | Dispatch every step to this enabled provider, for this run only. |
| `--model` | Dispatch every step to this model, for this run only. |
| `--daemon` | Send the run to the running daemon. |
| `--json` | Print the full run result as JSON. |

Example:

```sh
arhugula workflow run tagline-review.toml
```


## provider

See, enable and check providers.

### `arhugula provider list`

List every provider, its role, model and state.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider list
```

Example:

```sh
arhugula provider list
```

### `arhugula provider check`

Ask each enabled provider's own tool whether it is installed and signed in.

For Codex it reports the sign-in method and warns when an API key makes it a paid route.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider check [--all]
```

| Argument | Meaning |
| --- | --- |
| `--all` | Also check providers that are not enabled. |

Example:

```sh
arhugula provider check
```

### `arhugula provider enable`

Make a provider available to routing and to `--provider`.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider enable <name> [--model MODEL] [--command COMMAND]
```

| Argument | Meaning |
| --- | --- |
| `name` | The provider. One of: `claude_code`, `ollama`, `codex`, `gemini`, `antigravity`, `anthropic`, `openai`. |
| `--model` | The model this provider runs (default: the provider's usual model). |
| `--command` | The absolute path of its executable (default: found on PATH). |

Example:

```sh
arhugula provider enable codex
```

### `arhugula provider disable`

Remove a provider from the configs.

The default and the fallback provider cannot be disabled; change the chain first.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider disable <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The provider. One of: `claude_code`, `ollama`, `codex`, `gemini`, `antigravity`, `anthropic`, `openai`. |

Example:

```sh
arhugula provider disable gemini
```

### `arhugula provider set`

Set one setting of a command-line provider.

`timeout_seconds` is how long one call may take, in seconds. `auth_check` is whether the runtime checks the sign-in when it starts (true or false). `auth_args` is the arguments of the sign-in check, as a JSON list of strings; the runtime reads it for the Gemini tool only.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider set <name> <key> <value>
```

| Argument | Meaning |
| --- | --- |
| `name` | An enabled CLI provider. |
| `key` | The setting. One of: `timeout_seconds`, `auth_check`, `auth_args`. |
| `value` | The value; JSON for lists, numbers and true/false. |

Example:

```sh
arhugula provider set claude_code timeout_seconds 300
```

### `arhugula provider unset`

Return one setting of a command-line provider to the value the kit generates.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider unset <name> <key>
```

| Argument | Meaning |
| --- | --- |
| `name` | An enabled CLI provider. |
| `key` | The setting. One of: `timeout_seconds`, `auth_check`, `auth_args`. |

Example:

```sh
arhugula provider unset claude_code timeout_seconds
```

### `arhugula provider ollama-host`

Set the address of the Ollama server.

The server must answer at the address, or nothing changes.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider ollama-host <url>
```

| Argument | Meaning |
| --- | --- |
| `url` | The server address, for example http://127.0.0.1:11434. |

Example:

```sh
arhugula provider ollama-host http://127.0.0.1:11434
```

### `arhugula provider key set`

Store a hosted API provider's key in the macOS keychain.

You type the key at a hidden prompt. It is never an argument and never in a file.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider key set <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The hosted API provider. One of: `anthropic`, `openai`. |

Example:

```sh
arhugula provider key set anthropic
```

### `arhugula provider key delete`

Remove a hosted API provider's key from the macOS keychain.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula provider key delete <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The hosted API provider. One of: `anthropic`, `openai`. |

Example:

```sh
arhugula provider key delete anthropic
```


## routing

Choose which provider and model serve which work.

### `arhugula routing show`

Show the fallback chain, bindings, overrides and retry policies.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing show
```

Example:

```sh
arhugula routing show
```

### `arhugula routing chain set`

Choose the default provider and, optionally, the fallback.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing chain set <primary> [--fallback FALLBACK]
```

| Argument | Meaning |
| --- | --- |
| `primary` | The default, as `provider` or `provider:model`. |
| `--fallback` | The fallback, as `provider`, `provider:model` or `none`. |

Example:

```sh
arhugula routing chain set claude_code:sonnet --fallback ollama
```

### `arhugula routing model set`

Change the model a provider runs.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing model set <provider> <model>
```

| Argument | Meaning |
| --- | --- |
| `provider` | An enabled provider. |
| `model` | The model name as the provider knows it. |

Example:

```sh
arhugula routing model set ollama llama3.1:8b
```

### `arhugula routing role bind`

Bind a role to a provider and model, for example a reviewer on another model family.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing role bind <role> <binding>
```

| Argument | Meaning |
| --- | --- |
| `role` | The role name. |
| `binding` | `provider` or `provider:model`. |

Example:

```sh
arhugula routing role bind reviewer ollama:llama3.1:8b
```

### `arhugula routing role unbind`

Remove a role's binding.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing role unbind <role>
```

| Argument | Meaning |
| --- | --- |
| `role` | The role name. |

Example:

```sh
arhugula routing role unbind reviewer
```

### `arhugula routing workload override`

Route one workload class to a provider and model.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing workload override <workload> <binding>
```

| Argument | Meaning |
| --- | --- |
| `workload` | The workload class. One of: `pipeline-automation`, `software-engineering`, `research`, `content-creation`. |
| `binding` | `provider` or `provider:model`. |

Example:

```sh
arhugula routing workload override research ollama
```

### `arhugula routing workload clear`

Remove a workload class's override.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing workload clear <workload>
```

| Argument | Meaning |
| --- | --- |
| `workload` | The workload class. One of: `pipeline-automation`, `software-engineering`, `research`, `content-creation`. |

Example:

```sh
arhugula routing workload clear research
```

### `arhugula routing retry set`

Set a retry policy under a key.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing retry set <key> --max-attempts MAX_ATTEMPTS [--backoff BACKOFF] [--jitter JITTER]
```

| Argument | Meaning |
| --- | --- |
| `key` | The policy key. |
| `--max-attempts` | Attempts before the fallback chain takes over. |
| `--backoff` | The backoff strategy (default: full-jitter). |
| `--jitter` | The jitter token (default: full). |

Example:

```sh
arhugula routing retry set my_tool --max-attempts 3
```

### `arhugula routing retry clear`

Remove a retry policy.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula routing retry clear <key>
```

| Argument | Meaning |
| --- | --- |
| `key` | The policy key. |

Example:

```sh
arhugula routing retry clear my_tool
```


## feature

Switch named configuration features on and off.

### `arhugula feature list`

List every named feature and whether it is on.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula feature list
```

Example:

```sh
arhugula feature list
```

### `arhugula feature show`

Show what a feature does and the exact TOML it merges.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula feature show <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The feature. |

Example:

```sh
arhugula feature show deadlines
```

### `arhugula feature enable`

Switch a feature on in every generated config.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula feature enable <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The feature. |

Example:

```sh
arhugula feature enable data-flow
```

### `arhugula feature disable`

Switch a feature off.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula feature disable <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The feature. |

Example:

```sh
arhugula feature disable data-flow
```


## config

Show the generated config and set any runtime key.

### `arhugula config show`

Print a generated config, or the settings your verbs have stored.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula config show [--project NAME] [--overlay]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The project whose config to print (default: the current project). With --overlay: the project whose stored settings to print (default: the deployment-wide ones). |
| `--overlay` | Print only the stored settings, as JSON. |

Example:

```sh
arhugula config show
```

### `arhugula config set`

Set any runtime config key.

This reaches every knob the runtime has, including those no other verb names. The runtime's own loader must accept the result, or nothing changes.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula config set <key> <value> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `key` | The key under [runtime], dotted for nested tables. |
| `value` | The value, written as TOML: 120, true, "text", ["a", "b"]. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula config set step_dispatch_timeout_seconds 120
```

### `arhugula config unset`

Remove a setting you stored with `config set` or another verb.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula config unset <key> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `key` | The key under [runtime], dotted for nested tables. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula config unset step_dispatch_timeout_seconds
```

### `arhugula config keys`

List every runtime config key at the installed pin.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula config keys
```

Example:

```sh
arhugula config keys
```


## policy

Set what an approval gate may approve on its own.

### `arhugula policy show`

Show what an approval gate approves without asking.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula policy show
```

Example:

```sh
arhugula policy show
```

### `arhugula policy set`

Change what an approval gate approves without asking.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula policy set <setting> <state>
```

| Argument | Meaning |
| --- | --- |
| `setting` | Which floor. One of: `solo-floor-auto`, `local-mutation-floor-auto`. |
| `state` | On or off. One of: `on`, `off`. |

Example:

```sh
arhugula policy set solo-floor-auto off
```


## mcp

Connect Model Context Protocol (MCP) tool servers.

### `arhugula mcp list`

List the configured MCP clients.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula mcp list
```

Example:

```sh
arhugula mcp list
```

### `arhugula mcp add`

Connect an MCP tool server.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula mcp add <name> --url URL [--transport TRANSPORT] [--trust TRUST] [--blast-radius BLAST_RADIUS] [--auth-secret-name AUTH_SECRET_NAME]
```

| Argument | Meaning |
| --- | --- |
| `name` | A name for the client. |
| `--url` | The server URL, or for stdio the command to run. |
| `--transport` | How the runtime reaches it (default: streamable_http_l3). One of: `stdio`, `streamable_http_l0`, `streamable_http_l1`, `streamable_http_l2`, `streamable_http_l3`. |
| `--trust` | The trust level (default: L3_ALLOW_WITH_AUDIT). One of: `L0_REFUSE_REMOTE`, `L1_SIGNED_PINNED`, `L2_SANDBOX_ALL`, `L3_ALLOW_WITH_AUDIT`. |
| `--blast-radius` | The most its tools can change (default: READ_ONLY). One of: `READ_ONLY`, `LOCAL_MUTATION`, `EXTERNAL_REVERSIBLE`, `EXTERNAL_IRREVERSIBLE`. |
| `--auth-secret-name` | The keyring entry that holds its credential. |

Example:

```sh
arhugula mcp add docs --url http://127.0.0.1:8931/mcp
```

### `arhugula mcp remove`

Remove an MCP client.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula mcp remove <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The client. |

Example:

```sh
arhugula mcp remove docs
```

### `arhugula mcp test`

Connect to an MCP server and list its tools.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula mcp test <name>
```

| Argument | Meaning |
| --- | --- |
| `name` | The client. |

Example:

```sh
arhugula mcp test docs
```


## prompt

Author and select versioned prompts.

### `arhugula prompt list`

List authored prompt versions and where each is used.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula prompt list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt list
```

### `arhugula prompt author`

Author a prompt version from a text file.

A version is identified by the sha256 of its text. The first version authored becomes active.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula prompt author <label> --file FILE [--activate] [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `label` | A label for this version, for example v2. |
| `--file` | The text file that holds the prompt. |
| `--activate` | Make it the active version. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt author v1 --file prompts/system.md
```

### `arhugula prompt activate`

Make an authored version the active prompt.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula prompt activate <version> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `version` | A version's label, or the start of its sha. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt activate v2
```

### `arhugula prompt select`

Use an authored version for one workload class.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula prompt select <workload> <version> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `workload` | The workload class. One of: `pipeline-automation`, `software-engineering`, `research`, `content-creation`. |
| `version` | A version's label, or the start of its sha. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt select research v2
```

### `arhugula prompt approve`

Record an authored version as approved.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula prompt approve <version> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `version` | A version's label, or the start of its sha. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt approve v2
```

### `arhugula prompt diff`

Show the text difference between two authored versions.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula prompt diff <first> <second> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `first` | A version's label or sha prefix. |
| `second` | A version's label or sha prefix. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula prompt diff v1 v2
```


## skill

Manage the skills agents can load.

### `arhugula skill list`

List the skills that load from the current project.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula skill list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula skill list
```

### `arhugula skill add`

Copy a skill's two files into the current project's skills directory.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula skill add <source> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `source` | A directory holding `<name>.skill.json` and `<name>.SKILL.md`. |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula skill add ~/skills/haiku
```

### `arhugula skill validate`

Load a skills directory through the runtime's loader.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula skill validate <directory> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `directory` | The directory to check (default: the current project's). |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula skill validate
```

### `arhugula skill hook set`

Choose the hook that decides which skills a run activates.

The runtime accepts a hook only as a Python object, which a config file cannot carry. With a hook set, `arhugula run` starts the runtime's own CLI with the hook attached.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula skill hook set <hook>
```

| Argument | Meaning |
| --- | --- |
| `hook` | `module:Class`, or `every` to activate every loaded skill. |

Example:

```sh
arhugula skill hook set every
```

### `arhugula skill hook clear`

Remove the skill-activation hook.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula skill hook clear
```

Example:

```sh
arhugula skill hook clear
```


## validator

Bind validators to workflow steps.

### `arhugula validator list`

List the validators bound to workflow steps.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula validator list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula validator list
```

### `arhugula validator bind`

Bind a validator class to a step id.

The class is imported and constructed before the binding is stored, so a bad class is refused here.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula validator bind <step> <class_name> [--param PARAM] [--pythonpath PYTHONPATH] [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `step` | The step id the validator checks. |
| `class_name` | The class, as `module:Class`. |
| `--param` | A constructor parameter as key=value; repeat for several. |
| `--pythonpath` | A directory to import the module from (default: the project's validators/). |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula validator bind review-step my_validators:MaxChars --param max_chars=200
```

### `arhugula validator unbind`

Remove the validator from a step.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula validator unbind <step> [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `step` | The step id. |
| `--project` | Apply to this project's config only (default: every config of the deployment). |

Example:

```sh
arhugula validator unbind review-step
```

### `arhugula validator test`

Import and construct every bound validator. No provider is called.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula validator test [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula validator test
```


## pause

Durable pause and resume, and its journals.

### `arhugula pause enable`

Turn durable pause and resume on.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula pause enable
```

Example:

```sh
arhugula pause enable
```

### `arhugula pause disable`

Turn durable pause and resume off.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula pause disable
```

Example:

```sh
arhugula pause disable
```

### `arhugula pause list`

List the pause journals the runtime finds.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula pause list [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula pause list
```

### `arhugula pause adopt`

Adopt legacy untenanted pause journals into the project's tenant.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula pause adopt [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula pause adopt --project my-service
```

### `arhugula pause dispose`

Report, or with --delete remove, orphaned legacy pause journals.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula pause dispose [--project NAME] [--delete] [--acknowledge-discarding-recoverable-state]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--delete` | Really remove; without it nothing is removed. |
| `--acknowledge-discarding-recoverable-state` | Proceed although an adoption could still recover some journals. |

Example:

```sh
arhugula pause dispose
```


## webhook

Deliver pause notifications to a URL.

### `arhugula webhook set`

Deliver pause notifications to a URL.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula webhook set <url> [--id ID] [--timeout TIMEOUT]
```

| Argument | Meaning |
| --- | --- |
| `url` | The endpoint that receives the notification. |
| `--id` | A name for the webhook (default: local-approval). |
| `--timeout` | Seconds to wait for the endpoint, 1 to 5 (default: 3). |

Example:

```sh
arhugula webhook set http://127.0.0.1:8723/hitl
```

### `arhugula webhook clear`

Stop delivering pause notifications.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula webhook clear
```

Example:

```sh
arhugula webhook clear
```


## audit

Sign and verify the audit ledger.

### `arhugula audit keygen`

Create the local Ed25519 signing key.

The runtime ships no key generator. The key is never overwritten.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula audit keygen
```

Example:

```sh
arhugula audit keygen
```

### `arhugula audit enable`

Sign every audit entry with the local key.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula audit enable
```

Example:

```sh
arhugula audit enable
```

### `arhugula audit disable`

Stop signing new audit entries.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula audit disable
```

Example:

```sh
arhugula audit disable
```

### `arhugula audit status`

Show the signing backend, the key files and each ledger's audit entries.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula audit status
```

Example:

```sh
arhugula audit status
```

### `arhugula audit verify`

Verify a project's audit ledger with the runtime's inspector.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula audit verify [--project NAME] [--last-n LAST_N] [--signatures]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--last-n` | How many recent entries to print (default: 5). |
| `--signatures` | Require the full check (signatures and cutover record); refuse a ledger that cannot have it. |

Example:

```sh
arhugula audit verify --signatures
```

### `arhugula audit migrate-sidecar`

Run the runtime's one-time audit sidecar migration on a project's ledger.

Needed only for a ledger written before the audit sidecar existed.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula audit migrate-sidecar [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula audit migrate-sidecar
```


## isolation

Sandboxed tool execution.

### `arhugula isolation show`

Show which isolation tiers are in use.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula isolation show
```

Example:

```sh
arhugula isolation show
```

### `arhugula isolation enable`

Enable tier 3: tools run under gVisor in the Lima virtual machine.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula isolation enable <tier>
```

| Argument | Meaning |
| --- | --- |
| `tier` | The tier to enable. One of: `tier-3`. |

Example:

```sh
arhugula isolation enable tier-3
```

### `arhugula isolation attach`

Give one of your MCP clients a tier-3 sandbox.

The runner reads one MCP request as JSON on stdin and writes one MCP result as JSON on stdout.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula isolation attach <client> --image IMAGE --command COMMAND
```

| Argument | Meaning |
| --- | --- |
| `client` | The MCP client. |
| `--image` | The container image that holds the tool runner. |
| `--command` | The in-container runner, as a JSON array. |

Example:

```sh
arhugula isolation attach files --image python:3.12-alpine --command '["python","/runner.py"]'
```

### `arhugula isolation disable`

Disable tier 3 and remove its drivers.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula isolation disable
```

Example:

```sh
arhugula isolation disable
```


## daemon

Run the harness as a long-lived service.

### `arhugula daemon start`

Start the harness daemon for a project.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula daemon start [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula daemon start
```

### `arhugula daemon stop`

Ask a project's daemon to drain and exit.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula daemon stop [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula daemon stop
```

### `arhugula daemon status`

Show which projects have a running daemon.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula daemon status
```

Example:

```sh
arhugula daemon status
```

### `arhugula daemon expose`

Print how to reach a project's daemon.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula daemon expose [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |

Example:

```sh
arhugula daemon expose
```


## memory

Review and manage what the harness remembers.

### `arhugula memory status`

Show where a project's memory lives and how much it holds.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula memory status [--project NAME] [--operator OPERATOR]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |

Example:

```sh
arhugula memory status
```

### `arhugula memory review`

Walk through captured turns and propose, approve or deny memories.

Every decision is made through the runtime's operator tool and is decided at most once.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula memory review [--project NAME] [--operator OPERATOR] [--limit LIMIT]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--limit` | How many captured turns to walk through (default: 10). |

Example:

```sh
arhugula memory review
```

### `arhugula memory export`

Write a project's memory to an archive.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula memory export [--project NAME] [--output OUTPUT]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--output` | The archive to write (default: backups/memory-<project>-<time>.tar.gz). |

Example:

```sh
arhugula memory export
```

### `arhugula memory operations`

Print the memory-operation ledger.

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory operations [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory operations
```

### `arhugula memory inspect`

Print one memory record.

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory inspect [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory inspect <memory-id> --run-id <run-id>
```

### `arhugula memory propose`

Propose a memory from captured evidence.

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory propose [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory propose <source-id> --kind fact --statement "The team deploys on Fridays." --run-id <run-id>
```

### `arhugula memory approve`

Activate a proposal.

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory approve [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory approve <proposal-id> --source <source-id> --injection-policy prompt_packet_allowed --run-id <run-id>
```

### `arhugula memory deny`

Deny a proposal.

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory deny [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory deny <proposal-id> --source <source-id> --reason "not true" --run-id <run-id>
```

### `arhugula memory redact`

Redact a record (a dry run unless --apply).

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory redact [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory redact <memory-id> --reason "contains a secret" --apply
```

### `arhugula memory tombstone`

Tombstone a record (a dry run unless --apply).

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory tombstone [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory tombstone <memory-id> --reason "obsolete" --apply
```

### `arhugula memory expire`

Expire a record (a dry run unless --apply).

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory expire [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory expire <memory-id> --reason "out of date" --apply
```

### `arhugula memory migrate`

Migrate legacy filesystem callback memory (a dry run unless --apply).

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory migrate [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory migrate --run-id <run-id> <legacy-root> /memories/notes.md --migration-id m1
```

### `arhugula memory compact`

Record compaction candidate dispositions (a dry run unless --apply).

Arguments the kit does not name go to the runtime's memory operator unchanged. docs/memory.md lists each one.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula memory compact [--project NAME] [--operator OPERATOR] [--run-id RUN_ID]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project to act on (default: the current project; `default` for the deployment default). |
| `--operator` | The name recorded on the operation (default: your login name). |
| `--run-id` | The run that owns run-keyed records. |

Example:

```sh
arhugula memory compact --run-id <run-id> c1 --source <ids> --summary "merged duplicates"
```


## observability

The trace stack: collector, Tempo and Grafana.

### `arhugula observability vm create`

Create the deployment's own Lima virtual machine with Docker Engine, Compose and gVisor.

The virtual machine lives under `<home>/lima` and is built for this machine's processor. It sees only the Compose project and the run logs, read-only. It is the deployment's only Docker engine; Docker Desktop is not used. Allow 5 to 10 minutes.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability vm create
```

Example:

```sh
arhugula observability vm create
```

### `arhugula observability vm use`

Use a Lima instance you already have instead of the kit's VM.

The instance must be built for this machine's processor. It must also show `<home>/observability` and `<home>/logs` at the same paths as on the host; `arhugula observability up` checks that and refuses when it cannot see them.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability vm use <instance>
```

| Argument | Meaning |
| --- | --- |
| `instance` | The instance, as `<lima-home>::<instance>`. |

Example:

```sh
arhugula observability vm use ~/.lima::default
```

### `arhugula observability vm status`

Show the VM, and the Docker engine, Compose and gVisor inside it.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability vm status
```

Example:

```sh
arhugula observability vm status
```

### `arhugula observability vm delete`

Delete the kit's VM. Without --yes it only says what it would delete.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability vm delete [--yes]
```

| Argument | Meaning |
| --- | --- |
| `--yes` | Really delete. |

Example:

```sh
arhugula observability vm delete
```

### `arhugula observability up`

Start the VM and the trace stack: collector, Tempo and Grafana.

Renders the Compose project from the pinned upstream files and the kit's dashboards and alert rules. Starts the virtual machine, creating the kit's own if it does not exist. Starts the stack and waits until Grafana, Tempo and the trace endpoint answer on loopback.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability up
```

Example:

```sh
arhugula observability up
```

### `arhugula observability down`

Stop the trace stack and turn the tier off. Stored traces and Grafana data are kept.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability down [--stop-vm] [--delete-data]
```

| Argument | Meaning |
| --- | --- |
| `--stop-vm` | Also stop the VM. |
| `--delete-data` | Also delete the stored traces and Grafana data. |

Example:

```sh
arhugula observability down --stop-vm
```

### `arhugula observability status`

Show the VM, the containers, the loopback ports and the newest trace.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula observability status
```

Example:

```sh
arhugula observability status
```


## trace

Browse and export traces from the local span store.

### `arhugula trace list`

List the most recent traces in the local span store.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula trace list [--limit N]
```

| Argument | Meaning |
| --- | --- |
| `--limit` | How many traces. |

Example:

```sh
arhugula trace list
```

### `arhugula trace browse`

Open the runtime's terminal trace browser on the local span store.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula trace browse
```

Example:

```sh
arhugula trace browse
```

### `arhugula trace export`

Write spans from the local span store as JSON lines.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula trace export [--trace-id ID] [--out FILE]
```

| Argument | Meaning |
| --- | --- |
| `--trace-id` | Only this trace. |
| `--out` | Write to this file instead of the terminal. |

Example:

```sh
arhugula trace export --out traces.jsonl
```


## collector

The local span store the runtime writes.

### `arhugula collector status`

Show the local span store: where it is, how much it holds, who writes it.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula collector status
```

Example:

```sh
arhugula collector status
```

### `arhugula collector bridge start`

Explain why no span-store bridge is needed at this pin.

Kept so that earlier instructions still lead somewhere. The runtime writes the span store itself.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula collector bridge start
```

Example:

```sh
arhugula collector bridge start
```

### `arhugula collector bridge stop`

Explain why no span-store bridge is needed at this pin.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula collector bridge stop
```

Example:

```sh
arhugula collector bridge stop
```


## logs

Read the deployment's run logs.

### `arhugula logs`

Show a run log: the newest one, a named one, or the list.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula logs <name> [--list] [--lines N] [--collected]
```

| Argument | Meaning |
| --- | --- |
| `name` | A log file name from `arhugula logs --list` (default: the newest). |
| `--list` | List the log files. |
| `--lines` | How many lines from the end. |
| `--collected` | Show what the collector's logs pipeline has written. |

Example:

```sh
arhugula logs --list
```


## eval

The holdout evaluation loop and drift checks.

### `arhugula eval sample`

Draw a holdout set of traces from the local span store.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula eval sample [--primitive PRIMITIVE] [--count N] [--seed SEED] [--replace]
```

| Argument | Meaning |
| --- | --- |
| `--primitive` | Which holdout primitive. One of: `routing_accuracy_holdout`, `sandbox_tier_routing_accuracy`. |
| `--count` | How many traces to draw. |
| `--seed` | The sampling seed; the same seed draws the same set. |
| `--replace` | Draw a new set; the earlier set, its reviews and its assertion files are moved aside. |

Example:

```sh
arhugula eval sample --count 5
```

### `arhugula eval review`

Review each sampled trace and type its category. No model is called.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula eval review [--primitive PRIMITIVE]
```

| Argument | Meaning |
| --- | --- |
| `--primitive` | Which holdout primitive. One of: `routing_accuracy_holdout`, `sandbox_tier_routing_accuracy`. |

Example:

```sh
arhugula eval review
```

### `arhugula eval scaffold`

Write one assertion file per reviewed trace, for you to fill in.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula eval scaffold [--primitive PRIMITIVE]
```

| Argument | Meaning |
| --- | --- |
| `--primitive` | Which holdout primitive. One of: `routing_accuracy_holdout`, `sandbox_tier_routing_accuracy`. |

Example:

```sh
arhugula eval scaffold
```

### `arhugula eval status`

Count sampled and reviewed traces and run every assertion file.

Exits 1 when an assertion fails or cannot run.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula eval status
```

Example:

```sh
arhugula eval status
```

### `arhugula eval report`

Summarize the review categories and assertion results.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula eval report [--json]
```

| Argument | Meaning |
| --- | --- |
| `--json` | Print JSON. |

Example:

```sh
arhugula eval report
```

### `arhugula eval drift show`

Compare an alignment-floor primitive with its threshold.

Exits 1 when a primitive has drifted below its threshold.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula eval drift show <primitive> [--judge-value VALUE]
```

| Argument | Meaning |
| --- | --- |
| `primitive` | The primitive (default: every one with a threshold). One of: `cache_hit_rate_alignment_floor`, `routing_accuracy_holdout`, `sandbox_tier_routing_accuracy`, `judge_human_cohens_kappa`. |
| `--judge-value` | Your own measured value, for a primitive spans cannot give. |

Example:

```sh
arhugula eval drift show cache_hit_rate_alignment_floor
```

### `arhugula eval drift set-threshold`

Set the threshold and observation window of an alignment-floor primitive.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula eval drift set-threshold <primitive> <value> [--window-kind WINDOW_KIND] [--window-size N]
```

| Argument | Meaning |
| --- | --- |
| `primitive` | The primitive. One of: `cache_hit_rate_alignment_floor`, `routing_accuracy_holdout`, `sandbox_tier_routing_accuracy`, `judge_human_cohens_kappa`. |
| `value` | The threshold value. |
| `--window-kind` | A time window in seconds or a count of samples. One of: `TIME_WINDOW`, `SAMPLE_WINDOW`. |
| `--window-size` | Seconds, or samples. |

Example:

```sh
arhugula eval drift set-threshold cache_hit_rate_alignment_floor 0.5
```


## state

Inspect, back up and restore the state root.

### `arhugula state status`

Show the state root, its size, and each project's ledger.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula state status
```

Example:

```sh
arhugula state status
```

### `arhugula state backup`

Write the state root and the answers file to one archive.

Stop the daemon first so the archive is consistent.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula state backup [--output OUTPUT]
```

| Argument | Meaning |
| --- | --- |
| `--output` | The archive to write (default: backups/state-<time>.tar.gz). |

Example:

```sh
arhugula state backup
```

### `arhugula state restore`

Replace the state root with one from a backup archive.

The current state root is moved aside, not deleted. The runtime verifies the restored root.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula state restore <archive>
```

| Argument | Meaning |
| --- | --- |
| `archive` | An archive written by `state backup`. |

Example:

```sh
arhugula state restore backups/state-20261115T101500.tar.gz
```

### `arhugula state adopt`

Have the runtime verify the state root again, for example after a move.

Source: runtime (drives a capability of the harness runtime).

```text
arhugula state adopt
```

Example:

```sh
arhugula state adopt
```

### `arhugula state archive-legacy`

Move a project's leftover checkout-local harness state into backups/.

The runtime refuses a project with such state (legacy-state-present) and never moves it itself.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula state archive-legacy <project_path>
```

| Argument | Meaning |
| --- | --- |
| `project_path` | The project repository that holds the leftover state. |

Example:

```sh
arhugula state archive-legacy ~/code/my-service
```


## agent

Context files for agent CLIs that operate this deployment.

### `arhugula agent context install`

Write the harness section into a project's CLAUDE.md and AGENTS.md.

The section sits between two marker comments, so running the verb again replaces it and leaves the rest of each file alone.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula agent context install [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project whose files get the section (default: the current project). |

Example:

```sh
arhugula agent context install --project my-project
```

### `arhugula agent context show`

Print the section that `agent context install` would write.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula agent context show [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project whose files get the section (default: the current project). |

Example:

```sh
arhugula agent context show
```

### `arhugula agent context remove`

Remove the harness section from a project's CLAUDE.md and AGENTS.md.

Source: kit (kit extension: added by this kit, not part of upstream).

```text
arhugula agent context remove [--project NAME]
```

| Argument | Meaning |
| --- | --- |
| `--project` | The attached project whose files get the section (default: the current project). |

Example:

```sh
arhugula agent context remove
```
