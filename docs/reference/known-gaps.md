# Known gaps

This page is for a reviewer or maintainer who judges the deployment.
After reading it you know what the upstream harness lacks at the pinned commit, what the kit adds on top of upstream, and what the platform limits.
You also know which behaviours of the kit are accepted as they are.
Each item names its evidence or its place in the code.

This page describes kit version 0.1.0 at the upstream commit in the file `PIN`.
For the history of versions and pins, read [the changelog](../../CHANGELOG.md).
For how to work around a limit, follow the link to the page that covers the feature.

Five terms recur:

- ***upstream limit*:** the feature does not exist, or does not work, at the pinned upstream commit.
- ***kit extension*:** the kit adds the feature; it is not part of the upstream harness.
- ***witnessed*:** it ran on the development machine and the evidence exists.
- **MCP:** the Model Context Protocol (MCP), which tool servers speak.
- **CLI:** a command-line interface (CLI), such as Claude Code or Codex.

Paths that start with `upstream/` or `kit/` are relative to the deployment home, `<home>`.
Upstream package sources are under `upstream/<package>/src/`; the tables give the path from the package name.

## Contents

- [Upstream limits at the pin](#upstream-limits-at-the-pin)
- [Kit extensions](#kit-extensions)
- [Kit behaviours that stay as they are](#kit-behaviours-that-stay-as-they-are)
- [Platform and provider limits](#platform-and-provider-limits)
- [Reported upstream](#reported-upstream)
- [Sources](#sources)

## Upstream limits at the pin

Every item in this section is an *upstream limit*.
The kit does not hide any of them.
Where the kit offers a way around one, the table says so.

### Workflows and gates

| Limit | What you see | Evidence |
| --- | --- | --- |
| A lead-directed worker plan is not built from a model reply. | In the orchestrator and hierarchical examples the lead runs as its own step. Its output neither chooses nor reaches the workers. | `upstream/examples/README.md`, the paragraph "What these topology examples do not show yet"; `harness-cp/src/harness_cp/worker_plan.py` |
| A gate without a terminal is rejected. | A run with no terminal answers a gate with `noninteractive: no operator terminal`. | `harness-runtime/src/harness_runtime/lifecycle/operator_input.py`, `NONINTERACTIVE_REASON` |
| At default settings a gate must be answered within 30 seconds. | The wait at a gate is part of its step. The step deadline is 30 seconds and the run limit is 60 seconds unless set, so the gate's own wait of 900 seconds is not reached. A gate answered after 45 seconds ended the run `status: failed` with `RT-FAIL-STEP-DISPATCH-TIMEOUT: step dispatch exceeded 30.0s bound` (*witnessed*). Raise both with `arhugula config set step_dispatch_timeout_seconds <seconds>` and `arhugula config set drain_timeout_seconds <seconds>`. | `harness-runtime/src/harness_runtime/lifecycle/sync_dispatcher_facade.py`, `result_timeout_seconds`; `kit/lib/arhugula_kit/verbs_config.py`, `_policy_set` |
| The answer `hold` needs durable pause and a webhook. | Without both, the gate rejects `hold` with `hold unavailable: no durable pause binding`. Set them with `arhugula pause enable` and `arhugula webhook set <url>`. | `harness-runtime/src/harness_runtime/lifecycle/hitl_gate_composer.py`, `joint_binding_present`; `kit/lib/arhugula_kit/verbs_authoring.py`, `_pause_enable`; *witnessed* with both set |
| The pause-journal list is an upper bound. | `arhugula gate list` can show a journal whose pause is already answered. The journal records no marker for a resolved pause. | `harness-runtime/src/harness_runtime/admin/pause_journal_enumeration.py`, `UPPER_BOUND_DISCLAIMER`; `kit/lib/arhugula_kit/verbs_run.py`, the message of the gate list |
| The daemon's MCP endpoint is a Unix socket. | MCP clients such as Claude Code connect over stdio or TCP, so they cannot reach it. `arhugula daemon expose` prints the working alternative. | `harness --help`: "FastMCP server, Unix-socket transport"; `kit/lib/arhugula_kit/verbs_authoring.py`, `_daemon_expose` |
| Skill activation needs a Python hook object. | A TOML file cannot carry the hook. The kit passes one with `arhugula skill hook set` (*kit extension*). | `harness-runtime/src/harness_runtime/lifecycle/skill_activation.py`, `SkillActivationHookConfig`; `kit/lib/arhugula_kit/hookrun.py`; `kit/lib/arhugula_kit/skillhooks.py` |
| Managed-agents steps are bound only on a managed-cloud deployment. | This deployment is `local-development`, so the feature `managed-agents` has no effect here. | `harness-runtime/src/harness_runtime/bootstrap/factories/managed_agents_dispatcher_factory.py`, the surface gate; `kit/lib/arhugula_kit/render.py`, `deployment_surface` |
| A step's `params` are not translated between provider families. | The runtime merges `params` unchanged into the call of the provider that serves the step. A command-line provider does not read them. When a fallback or a more specific binding sends the step to another family, that provider gets keys written for the first family. What each provider does with such keys was not witnessed. | `harness-runtime/src/harness_runtime/lifecycle/llm_dispatch.py`: `kwargs.update(payload.params)` in `_payload_to_anthropic_kwargs`, `_payload_to_openai_kwargs` and `_payload_to_ollama_kwargs`; `lifecycle/external_cli_provider.py` does not read `params` |

### Evaluation

| Limit | What you see | Evidence |
| --- | --- | --- |
| There is no eval judge and no scored suite. | The runtime has no `eval` command. The holdout loop of the kit asks a person and calls no model. | `harness --help` lists no eval command; `offline_judge` is only declared, in `harness-od/src/harness_od/eval_vs_runtime_gate.py` |
| Drift thresholds have no runtime setting. | The kit stores the threshold itself (*kit extension*). Only `cache_hit_rate_alignment_floor` is computed from spans. | `upstream/docs/how-to-operate-runtime.md`: "no config field and no command at this release"; `kit/lib/arhugula_kit/bridge.py`, `drift_check` |
| The drift alert rule stays silent. | The rule "Alignment-floor drift detected" watches for the span event `gen_ai.eval.alignment_floor.drift_detected`. No caller in the runtime emits that event, and `arhugula eval drift show` computes drift itself and emits no span event. Use `arhugula eval drift show` as the working check. | `kit/observability/alerting/arhugula-rules.yaml`, the query of `arhugula-alignment-floor-drift`; `harness-od/src/harness_od/alignment_floor_drift_algorithm.py`, `run_drift_check`, the only caller of `emit_drift_event`; `kit/lib/arhugula_kit/bridge.py`, `drift_check` |
| Nothing runs the drift check for you. | No run computes drift during or after itself. Run `arhugula eval drift show` yourself, or from a scheduled job. | `harness-od/src/harness_od/alignment_floor_drift_algorithm.py`, `run_drift_check`; a search of the upstream packages finds no caller |
| Roll-up dimensions are declared and never read. | No panel splits an evaluation primitive by role or session. | `harness-od/src/harness_od/operator_burden_eval_primitives.py`, `rollup_dimensions`; a search of the upstream packages finds no code that reads the field |

### Traces and cost

| Limit | What you see | Evidence |
| --- | --- | --- |
| Finish reasons are not in spans. | No dashboard can show why a model call stopped. | `harness-od/src/harness_od/otel_genai_base.py` declares `gen_ai.response.finish_reasons`; a search of the upstream packages finds no place that sets it on a span |
| Cost is a text attribute. | `cost.attributed_decimal` is a string, so a trace backend cannot sum it. The kit's collector adds the numeric copy `cost.attributed_number` (*kit extension*). | `harness-od/src/harness_od/cost_record_otel_serializer.py`; `kit/observability/stack/otel-collector.yaml` |
| There is no span for a step. | A trace shows model calls and tool calls. A step appears only as the attribute `step.id` on some spans. | `harness-runtime/src/harness_runtime/lifecycle/runtime_tool_dispatcher.py`, `ATTR_STEP_ID`; the validator panels in [the panel index](../../observability/PANELS.md) group by `span.step.id` |
| `sampling_mode` in the configuration changes nothing. | The runtime resolves the value and discards it. | `harness-runtime/src/harness_runtime/lifecycle/tracer_provider.py`: `_ = resolve_sampling_mode(...)` |
| Subscription CLI calls are never priced. | Calls through `claude_code`, `codex`, `gemini` and `antigravity` write no cost entry and no audit entry. A run on one still writes its step entries to the state ledger (*witnessed*). The `ledger:` line of a run prints the hash of the newest audit entry, so that hash stays unchanged. Leaving the calls unpriced is by design. Upstream issue #1743 covers the missing cost and audit entries. | `harness-od/src/harness_od/rate_table_v1.py`: "no row on purpose"; `harness-runtime/src/harness_runtime/cli/app.py`, `_emit_run_result`; `harness-runtime/src/harness_runtime/lifecycle/audit_writer.py`, `read_all` |

### Audit and isolation

| Limit | What you see | Evidence |
| --- | --- | --- |
| A ledger that began unsigned cannot be signature-verified. | Its first entries carry no signature and it has no cutover record. `arhugula audit verify --signatures` refuses it and names the reason. The hash chain still verifies. Upstream's `harness migrate-audit-sidecar --author` writes a cutover record for older entries. It was tried on such a ledger, and verification then fails with `signature-invalid` on the unsigned entries (*witnessed*). | `kit/lib/arhugula_kit/verbs_authoring.py`, `_audit_verify`; `kit/lib/arhugula_kit/render.py`, `with_new_cutover_ledgers`; `harness-runtime/src/harness_runtime/admin/record_migration.py` |
| Upstream ships no key generator. | The kit adds `arhugula audit keygen` (*kit extension*). | a search of the upstream packages, documents and tools finds key generation in test files only |
| There is no key rotation. | The keys are unencrypted files, and one fixed key signs for the life of a ledger. | `harness-runtime/src/harness_runtime/config/local_ed25519_signing_backend.py`: "does not provide rotation by key period"; `kit/lib/arhugula_kit/bridge.py`, `NoEncryption` |
| The Codex profile is marked HELD. | Upstream has not tested how much of the filesystem the Codex CLI can read. `init` proposes Codex as the default provider only when it is the only provider selected. | `upstream/docs/how-to-deploy.md`, the row for `omarchy.codex.toml.example`; `kit/lib/arhugula_kit/providers.py`; `kit/lib/arhugula_kit/questions.py`, `_default_primary` |
| A `stdio` MCP client and an HTTP MCP client do not work together. | An example is tier 3's `sandbox-echo` together with a client added by `arhugula mcp add`. With both kinds configured, every run serves its tool calls and then ends in `asyncio.exceptions.CancelledError: Cancelled via cancel scope ...` while the runtime shuts its MCP clients down. The exit code is 1. This also hits a workflow that uses only one of the two clients. With either client alone the same workflow ends `status: completed`. The same error was seen on `hold` and on `resume` in an earlier session; that was not captured again. Keep one kind configured at a time: run `arhugula isolation disable`, or `arhugula mcp remove <name>`. | *witnessed* on the development deployment, with transcripts kept; `harness-runtime/src/harness_runtime/lifecycle/mcp_client_host.py`, `MCPClientHost.shutdown` |

Read [security and isolation](../security-and-isolation.md) for what signing and the sandbox do and do not protect.

## Kit extensions

Everything in this section is a *kit extension*: upstream does not ship it.
A reviewer who compares the deployment with upstream should expect none of it there.

The kit adds everything before the first run and everything that edits configuration.
Upstream's own `harness` command has eight subcommands: `run`, `resume`, `daemon`, `inspect`, `shutdown`, `migrate-audit-sidecar`, `adopt-pause-journals` and `dispose-pause-journals`.
[The command reference](cli.md) marks every verb as `runtime` or `kit`, so use it for the complete list.

| Extension | What it adds | Place in the code |
| --- | --- | --- |
| `init` and the dependency stage | Checks each dependency, explains it and shows the setup command. Offers to run that command when it is one safe command and its installer is present. Then checks again. | `kit/lib/arhugula_kit/initflow.py`; `kit/lib/arhugula_kit/dependencies.py` |
| The virtual machine | The kit's own Lima machine with Docker Engine, Compose and gVisor. | `kit/lib/arhugula_kit/vm.py`; `kit/observability/lima/arhugula.yaml.tmpl` |
| Dashboards | Seven Grafana dashboards. | `kit/observability/dashboards/`; `kit/tools/dashboards.py` |
| Alert rules | Seven Grafana alert rules. | `kit/observability/alerting/arhugula-rules.yaml` |
| The logs pipeline | The collector reads the run logs and writes them to a file. `arhugula logs --collected` reads that file. No logs backend is installed. | `kit/observability/stack/otel-collector.yaml` |
| The numeric cost copy | The attribute `cost.attributed_number`. | `kit/observability/stack/otel-collector.yaml` |
| TraceQL metrics | Tempo's local-blocks processor, which upstream's file does not enable. | `kit/observability/stack/tempo.addendum.yaml` |
| Generated configuration and named features | The kit writes every config file the runtime reads, and merges the named features into it. | `kit/lib/arhugula_kit/render.py`; `kit/fragments/` |
| Run logs | Every `run` and `resume` writes a log file under `<home>/logs/`. | `kit/lib/arhugula_kit/common.py` |
| `arhugula workflow new` | Creates a manifest for a topology, derived from upstream's example for it. | `kit/lib/arhugula_kit/verbs_run.py` |
| `arhugula memory status`, `review`, `export` | Operator views over the runtime's memory. | `kit/lib/arhugula_kit/verbs_memory.py` |
| `arhugula eval status`, `report` | Run the holdout assertions and report on them. | `kit/lib/arhugula_kit/verbs_observability.py` |
| The drift-threshold store | `arhugula eval drift set-threshold` keeps the threshold in the answers file. | `kit/lib/arhugula_kit/verbs_observability.py`; `kit/lib/arhugula_kit/bridge.py` |
| `arhugula trace list`, `export` | Read the local span store. | `kit/lib/arhugula_kit/verbs_observability.py` |
| `arhugula doctor --self-test` | Proves on your machine that the checks and the runtime refuse what they should. | `kit/lib/arhugula_kit/selftest.py` |
| `arhugula audit keygen`, `status` | Create the two signing keys and show the signing state. | `kit/lib/arhugula_kit/verbs_authoring.py` |
| `arhugula skill hook` | Passes a skill-activation hook to the runtime. | `kit/lib/arhugula_kit/hookrun.py` |
| `arhugula agent context` | The harness section for a project's `CLAUDE.md` and `AGENTS.md`. | `kit/lib/arhugula_kit/agentctx.py` |
| `arhugula state backup`, `restore` | One archive of the state root and the answers file. | `kit/lib/arhugula_kit/verbs_state.py` |
| The examples | Prompts, a skill, validators, an MCP server, a gated workflow and a webhook receiver. | `kit/examples/` |

The kit copies upstream's Compose project for the trace stack unchanged from the pin.
The kit's additions sit beside it, in `kit/observability/stack/`.

## Kit behaviours that stay as they are

These behaviours of the kit's own verbs are known and accepted.
This version does not change them.

| Behaviour | What you see | Place in the code |
| --- | --- | --- |
| Verb groups have different default scopes. | The `prompt` verbs and `validator list`, `bind` and `unbind` act on every config of the deployment unless you pass `--project <project>`. The verbs `skill list`, `add` and `validate`, and `validator test`, act on the current project. | `kit/lib/arhugula_kit/verbs_authoring.py`, the verb list; `kit/lib/arhugula_kit/verbs_config.py`, `SCOPE_ARG`; `kit/lib/arhugula_kit/common.py`, `PROJECT_ARG` |
| `arhugula memory review` shows a turn again. | It does not skip a turn that you already proposed a memory from. With the feature `memory-procedural` on, the review stops at the first refusal of the runtime. | `kit/lib/arhugula_kit/verbs_memory.py`, `_review` and `_capture` |
| The help of a runtime memory verb shows the kit's flags only. | `arhugula memory <verb> --help` lists `--project`, `--operator` and `--run-id` for each memory verb that [the command reference](cli.md) marks `runtime`. [Memory](../memory.md) lists the runtime's own arguments. | `kit/lib/arhugula_kit/verbs_memory.py`, `_tool_verb` |
| `arhugula validator unbind` of the last binding removes more than the binding. | It drops the whole `validator_framework_config` table of that scope. | `kit/lib/arhugula_kit/verbs_authoring.py`, `_validator_unbind` |
| No verb removes a `--pythonpath`. | `arhugula validator bind --pythonpath <dir>` adds the directory to the import path of every run. It stays there after you unbind the validator. | `kit/lib/arhugula_kit/verbs_authoring.py`, `_validator_bind`; `kit/lib/arhugula_kit/spec.py`, `python_paths` |
| No verb stores the credential of an MCP server. | `arhugula mcp add --auth-secret-name <entry>` only names the keychain entry, and `arhugula provider key set` stores the keys of `anthropic` and `openai` only. Create the entry yourself: [Keep secrets out of TOML](../configure.md#keep-secrets-out-of-toml) shows the command. | `kit/lib/arhugula_kit/verbs_config.py`, `_mcp_add` and `_provider_key_set`; `harness-runtime/src/harness_runtime/bootstrap/factories/mcp_client_host_factory.py`, `resolve_bootstrap_value`; `harness-runtime/src/harness_runtime/config/provider_secrets.py`, `keyring.get_password` |
| `arhugula state restore` replaces the pause journals. | The pause journals are in the state root, at `<home>/state/pause-journal`. A restore puts the journals of the archive in their place, so a gate put on hold after the backup is not in the restored state root. An upgrade and a rollback do not touch the state root, and a relocate moves it whole. Resuming a gate on hold after any of the four was not witnessed. Answer the gates on hold first: `arhugula gate list` shows them. | `kit/lib/arhugula_kit/layout.py`, `pause_journal`; `kit/lib/arhugula_kit/verbs_state.py`, `_restore`; `kit/lib/arhugula_kit/verbs_lifecycle.py`, `_upgrade` and `_relocate` |
| After `arhugula relocate`, the rollback copy belongs to the earlier home. | The move rebuilds the environment and keeps the one it replaces at `<home>/env.rollback`. That copy was built at the earlier path, and its scripts carry that path. A rollback to it was not tried, so do not roll back to it. | `kit/lib/arhugula_kit/verbs_lifecycle.py`, `_relocate`; `kit/bin/install.sh`, the step "environment" |

## Platform and provider limits

| Limit | What it means | Evidence |
| --- | --- | --- |
| Intel Macs are untested. | The kit is witnessed on Apple silicon only. `init` says so on an Intel Mac and continues. | `kit/lib/arhugula_kit/dependencies.py`, the macOS check |
| Isolation tiers 2 and 4 are out of scope. | The deployment provides tier 1 and tier 3. A tool call that resolves to tier 2 or tier 4 has no driver. | `kit/lib/arhugula_kit/isolation.py`; `arhugula isolation show` |
| An HTTP tool server that changes local files cannot be declared honestly and run. | The runtime gives every tool of a client the blast radius that you declared for the client. A remote client at trust level `L1_SIGNED_PINNED` or `L3_ALLOW_WITH_AUDIT`, declared `--blast-radius LOCAL_MUTATION`, resolves to tier 2. The deployment has no tier 2 driver, and `arhugula isolation attach` refuses a client that is not `stdio`. So while the client is configured, the runtime refuses every run at its start, not only the tool call, with exit code 4 (*witnessed* at `L3_ALLOW_WITH_AUDIT`). The message is `RT-FAIL-BOOTSTRAP: bootstrap failed at stage LOOP_INIT (6): SandboxDriverUnavailableError: resolved sandbox tier 'tier-2-container' requires an execution driver`. `arhugula mcp remove <name>` ends the refusal. Declared `READ_ONLY`, the same client runs at tier 1, and a gate treats its tools as read-only. | `kit/lib/arhugula_kit/verbs_config.py`, `_mcp_add`; `harness-as/src/harness_as/blast_radius_floor.py`; `harness-as/src/harness_as/sandbox_tier_floor.py`; `harness-runtime/src/harness_runtime/bootstrap/factories/mcp_client_host_factory.py`, `default_blast_radius`; `harness-runtime/src/harness_runtime/bootstrap/factories/runtime_tool_dispatcher_factory.py`, `_select_tool_execution_driver`; `kit/lib/arhugula_kit/isolation.py`, `attach` |
| A Lima instance built for another CPU is not used. | The kit refuses it and offers its own machine, because emulation is many times slower. | `kit/lib/arhugula_kit/vm.py`, `emulation_refusal` |
| The Gemini CLI refuses individual Google accounts. | The CLI points to Antigravity. The runtime dispatches correctly; the CLI itself declines. | `kit/lib/arhugula_kit/providers.py`, the caveat of `gemini` |
| Tempo metrics are empty after a restart. | After Tempo restarts, metric panels stay empty until the next run writes a span. The cause is Tempo's metrics generator, not the harness. | observed on the development deployment; see [observability](../observability.md) |
| An API key in the environment is also read. | When the keychain has no entry for an API-key provider, the runtime reads `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` from the environment. This is upstream's default backend. Unset the variable to make the keychain the only source. | `harness-runtime/src/harness_runtime/config/provider_secrets.py`, `_KEYRING_TO_ENV_VAR` |
| Gemini and Antigravity calls run in the project directory with their own tools on. | The runtime starts both CLIs in the directory it runs in, which is the project's directory. It passes no flag that switches their tools off; Antigravity gets `--sandbox` only. Claude Code and Codex run in a new empty directory with their tools off. | `harness-runtime/src/harness_runtime/lifecycle/external_cli_provider.py`; see [how provider calls are isolated](../security-and-isolation.md#how-provider-calls-are-isolated) |
| Docker Desktop is never used. | The only Docker engine is the one inside the virtual machine. Without a virtual machine there is no trace stack and no tier 3. | `kit/lib/arhugula_kit/vm.py`, `engine` |

## Reported upstream

Three limits are reported to the upstream repository, `thestoryportal/arhugula-harness`.

- **The lead-directed worker plan.** Upstream issue: (number added when filed)
- **The eval judge or scored suite.** Upstream issue: (number added when filed)
- **A `stdio` and an HTTP MCP client together.** Upstream issue: (number added when filed)

## Sources

Kit modules, under `<home>/kit/`:

- `lib/arhugula_kit/verbs_authoring.py`, `verbs_run.py`, `verbs_observability.py`, `verbs_memory.py`, `verbs_state.py`
- `lib/arhugula_kit/render.py`, `bridge.py`, `hookrun.py`, `skillhooks.py`, `providers.py`, `questions.py`, `common.py`, `dependencies.py`, `vm.py`, `isolation.py`, `verbs_config.py`, `spec.py`
- `observability/stack/otel-collector.yaml`, `observability/stack/tempo.addendum.yaml`, `observability/PANELS.md`, `observability/alerting/arhugula-rules.yaml`
- `docs/reference/cli.md`

Upstream, under `<home>/upstream/`:

- `docs/how-to-operate-runtime.md`
- `docs/how-to-deploy.md`
- `examples/README.md`
- `deploy/self-hosted-local/README.md`
- `harness-cp/src/harness_cp/worker_plan.py`
- `harness-od/src/harness_od/otel_genai_base.py`, `cost_record_otel_serializer.py`, `rate_table_v1.py`, `eval_vs_runtime_gate.py`, `alignment_floor_drift_algorithm.py`, `operator_burden_eval_primitives.py`
- `harness-runtime/src/harness_runtime/lifecycle/tracer_provider.py`, `operator_input.py`, `hitl_gate_composer.py`, `skill_activation.py`, `runtime_tool_dispatcher.py`, `mcp_client_host.py`, `external_cli_provider.py`
- `harness-runtime/src/harness_runtime/admin/pause_journal_enumeration.py`, `record_migration.py`
- `harness-runtime/src/harness_runtime/config/local_ed25519_signing_backend.py`, `provider_secrets.py`
- `harness-runtime/src/harness_runtime/bootstrap/factories/managed_agents_dispatcher_factory.py`

Two reference documents of the development workspace were also used: the observability reference and the configuration reference.
They are not part of this repository.
