# Known gaps

This page is for a reviewer or maintainer who judges the deployment.
After reading it you know what the upstream harness lacks at the pinned commit, what the kit adds on top of upstream, and what the platform limits.
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
| The answer `hold` needs durable pause and a webhook. | Without both, the gate rejects `hold` with `hold unavailable: no durable pause binding`. Set them with `arhugula pause enable` and `arhugula webhook set <url>`. | `harness-runtime/src/harness_runtime/lifecycle/hitl_gate_composer.py`, `joint_binding_present`; `kit/lib/arhugula_kit/verbs_authoring.py`, `_pause_enable`; *witnessed* with both set |
| The pause-journal list is an upper bound. | `arhugula gate list` can show a journal whose pause is already answered. The journal records no marker for a resolved pause. | `harness-runtime/src/harness_runtime/admin/pause_journal_enumeration.py`, `UPPER_BOUND_DISCLAIMER`; `kit/lib/arhugula_kit/verbs_run.py`, the message of the gate list |
| The daemon's MCP endpoint is a Unix socket. | MCP clients such as Claude Code connect over stdio or TCP, so they cannot reach it. `arhugula daemon expose` prints the working alternative. | `harness --help`: "FastMCP server, Unix-socket transport"; `kit/lib/arhugula_kit/verbs_authoring.py`, `_daemon_expose` |
| Skill activation needs a Python hook object. | A TOML file cannot carry the hook. The kit passes one with `arhugula skill hook set` (*kit extension*). | `harness-runtime/src/harness_runtime/lifecycle/skill_activation.py`, `SkillActivationHookConfig`; `kit/lib/arhugula_kit/hookrun.py`; `kit/lib/arhugula_kit/skillhooks.py` |
| Managed-agents steps are bound only on a managed-cloud deployment. | This deployment is `local-development`, so the feature `managed-agents` has no effect here. | `harness-runtime/src/harness_runtime/bootstrap/factories/managed_agents_dispatcher_factory.py`, the surface gate; `kit/lib/arhugula_kit/render.py`, `deployment_surface` |

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
| Subscription CLI calls are never priced. | Calls through `claude_code`, `codex`, `gemini` and `antigravity` write no cost entry. The reported ledger head hash stays unchanged. This is by design. | `harness-od/src/harness_od/rate_table_v1.py`: "no row on purpose" |

### Audit and isolation

| Limit | What you see | Evidence |
| --- | --- | --- |
| A ledger that began unsigned cannot be signature-verified. | Its first entries carry no signature and it has no cutover record. `arhugula audit verify --signatures` refuses it and names the reason. The hash chain still verifies. Upstream's `migrate-audit-sidecar --author` writes a cutover record for older entries; the kit does not drive that mode, and nobody has tried it on such a ledger. | `kit/lib/arhugula_kit/verbs_authoring.py`, `_audit_verify`; `kit/lib/arhugula_kit/render.py`, `with_new_cutover_ledgers`; `harness-runtime/src/harness_runtime/admin/record_migration.py` |
| Upstream ships no key generator. | The kit adds `arhugula audit keygen` (*kit extension*). | a search of the upstream packages, documents and tools finds key generation in test files only |
| There is no key rotation. | The keys are unencrypted files, and one fixed key signs for the life of a ledger. | `harness-runtime/src/harness_runtime/config/local_ed25519_signing_backend.py`: "does not provide rotation by key period"; `kit/lib/arhugula_kit/bridge.py`, `NoEncryption` |
| The Codex profile is marked HELD. | Upstream has not tested how much of the filesystem the Codex CLI can read. `init` proposes Codex as the primary provider only when it is the only provider selected. | `upstream/docs/how-to-deploy.md`, the row for `omarchy.codex.toml.example`; `kit/lib/arhugula_kit/providers.py`; `kit/lib/arhugula_kit/questions.py`, `_default_primary` |

Read [security and isolation](../security-and-isolation.md) for what signing and the sandbox do and do not protect.

## Kit extensions

Everything in this section is a *kit extension*: upstream does not ship it.
A reviewer who compares the deployment with upstream should expect none of it there.

The kit adds everything before the first run and everything that edits configuration.
Upstream's own `harness` command has eight subcommands: `run`, `resume`, `daemon`, `inspect`, `shutdown`, `migrate-audit-sidecar`, `adopt-pause-journals` and `dispose-pause-journals`.
[The command reference](cli.md) marks every verb as `runtime` or `kit`, so use it for the complete list.

| Extension | What it adds | Place in the code |
| --- | --- | --- |
| `init` and the dependency stage | Checks each dependency, explains it, offers the setup command and checks again. | `kit/lib/arhugula_kit/initflow.py`; `kit/lib/arhugula_kit/dependencies.py` |
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

## Platform and provider limits

| Limit | What it means | Evidence |
| --- | --- | --- |
| Intel Macs are untested. | The kit is witnessed on Apple silicon only. `init` says so on an Intel Mac and continues. | `kit/lib/arhugula_kit/dependencies.py`, the macOS check |
| Isolation tiers 2 and 4 are out of scope. | The deployment provides tier 1 and tier 3. A tool call that resolves to tier 2 or tier 4 has no driver. | `kit/lib/arhugula_kit/isolation.py`; `arhugula isolation show` |
| A Lima instance built for another CPU is not used. | The kit refuses it and offers its own machine, because emulation is many times slower. | `kit/lib/arhugula_kit/vm.py`, `emulation_refusal` |
| The Gemini CLI refuses individual Google accounts. | The CLI points to Antigravity. The runtime dispatches correctly; the CLI itself declines. | `kit/lib/arhugula_kit/providers.py`, the caveat of `gemini` |
| Tempo metrics are empty after a restart. | After Tempo restarts, metric panels stay empty until the next run writes a span. The cause is Tempo's metrics generator, not the harness. | observed on the development deployment; see [observability](../observability.md) |
| Docker Desktop is never used. | The only Docker engine is the one inside the virtual machine. Without a virtual machine there is no trace stack and no tier 3. | `kit/lib/arhugula_kit/vm.py`, `engine` |

## Reported upstream

Two limits are reported to the upstream repository, `thestoryportal/arhugula-harness`.

- **The lead-directed worker plan.** Upstream issue: (number added when filed)
- **The eval judge or scored suite.** Upstream issue: (number added when filed)

## Sources

Kit modules, under `<home>/kit/`:

- `lib/arhugula_kit/verbs_authoring.py`, `verbs_run.py`, `verbs_observability.py`, `verbs_memory.py`, `verbs_state.py`
- `lib/arhugula_kit/render.py`, `bridge.py`, `hookrun.py`, `skillhooks.py`, `providers.py`, `questions.py`, `common.py`, `dependencies.py`, `vm.py`, `isolation.py`
- `observability/stack/otel-collector.yaml`, `observability/stack/tempo.addendum.yaml`, `observability/PANELS.md`, `observability/alerting/arhugula-rules.yaml`
- `docs/reference/cli.md`

Upstream, under `<home>/upstream/`:

- `docs/how-to-operate-runtime.md`
- `docs/how-to-deploy.md`
- `examples/README.md`
- `deploy/self-hosted-local/README.md`
- `harness-cp/src/harness_cp/worker_plan.py`
- `harness-od/src/harness_od/otel_genai_base.py`, `cost_record_otel_serializer.py`, `rate_table_v1.py`, `eval_vs_runtime_gate.py`, `alignment_floor_drift_algorithm.py`, `operator_burden_eval_primitives.py`
- `harness-runtime/src/harness_runtime/lifecycle/tracer_provider.py`, `operator_input.py`, `hitl_gate_composer.py`, `skill_activation.py`, `runtime_tool_dispatcher.py`
- `harness-runtime/src/harness_runtime/admin/pause_journal_enumeration.py`, `record_migration.py`
- `harness-runtime/src/harness_runtime/config/local_ed25519_signing_backend.py`
- `harness-runtime/src/harness_runtime/bootstrap/factories/managed_agents_dispatcher_factory.py`

Two reference documents of the development workspace were also used: the observability reference and the configuration reference.
They are not part of this repository.
