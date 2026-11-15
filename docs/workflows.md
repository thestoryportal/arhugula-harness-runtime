# Write and run workflows

This page is for the workflow author, human or agent.
After reading it, you can read a manifest field by field, choose a topology, create a manifest, check it and run it.

A *workflow* is a set of steps that the harness runs for you.
A *manifest* is the file that describes one workflow, written in Tom's Obvious Minimal Language (TOML).
The commands on this page use a project: attach one first, as the [projects page](projects.md) shows.
The runs use Ollama and the model `llama3.2:3b`: see [the dependencies](install.md#dependencies).

## On this page

- [How a workflow runs](#how-a-workflow-runs)
- [Read a manifest field by field](#read-a-manifest-field-by-field)
- [Choose one of the six topologies](#choose-one-of-the-six-topologies)
- [Pass one step's output to the next](#pass-one-steps-output-to-the-next)
- [Create a manifest](#create-a-manifest)
- [Check a manifest](#check-a-manifest)
- [Run a manifest](#run-a-manifest)
- [Put an approval gate in a workflow](#put-an-approval-gate-in-a-workflow)
- [Run the gated example](#run-the-gated-example)
- [Upstream limit: a lead does not direct its workers](#upstream-limit-a-lead-does-not-direct-its-workers)
- [Sources](#sources)

## How a workflow runs

One command starts one process, and that process runs the whole workflow.
That is the multi-agent execution model:

- **One process runs everything.** `arhugula run` starts the runtime once. The runtime's workflow driver runs every step, in the order the topology sets.
- **Branches run at the same time.** Parallel branches, an orchestrator's workers and a hierarchy's children run concurrently inside that one process.
- **Each agent step is one isolated provider call.** The call is short-lived. A command-line provider gets no session and a scrubbed environment. Claude Code and Codex also get no tools of their own; Antigravity keeps its own and starts in the project's repository: see [What each call can see](providers.md#what-each-call-can-see). The [providers page](providers.md#how-the-runtime-calls-a-command-line-provider) shows the exact command lines.
- **No terminal multiplexer is involved.** The harness opens no panes and no windows. You watch one command in one terminal.
- **A reviewer is a role in a topology.** The evaluator of an evaluator-optimizer workflow reviews the generator. The synthesis step of an orchestrator-workers workflow combines the workers. To review with another model, route that step: see [Review with a second model](providers.md#review-with-a-second-model).

Agents change nothing in the world by themselves, with one exception.
A step that Antigravity serves, as the default or as the fallback, runs that tool with its own tools on, and no gate covers them (*upstream limit*).
Every other step acts only through the harness: a tool step calls a tool server, and an approval gate can stand in front of that call.

```mermaid
flowchart TD
  R["arhugula run: one process"] --> D["Workflow driver"]
  D --> A["Agent step A"]
  D --> B["Agent step B"]
  A --> PA["Isolated provider call"]
  B --> PB["Isolated provider call"]
  PA --> J["Join the branches"]
  PB --> J
  D --> T["Tool step"]
  T --> G{"Approval gate"}
  G --> M["Tool server"]
  J --> L["State ledger"]
  M --> L
```

The diagram shows one run.
The command starts one process, and its workflow driver starts two agent steps at the same time.
Each agent step makes its own isolated provider call, and the driver joins the two results.
A tool step passes an approval gate before it reaches its tool server.
Every step's result ends in the project's state ledger, whichever provider served it.

A run on a subscription provider writes no cost entry and no audit entry: see [Know what a run costs](providers.md#know-what-a-run-costs).

## Read a manifest field by field

A manifest has four parts: a version line, a `[workflow]` table, a `[default_model_binding]` table and one `[[steps]]` entry for each step.
This is the smallest upstream example, `ollama-first.toml`, without its comments:

```toml
version = 1

[workflow]
workflow_id = "example-ollama-first"
workload_class = "pipeline-automation"
persona_tier = "solo-developer"
engine_class = "pure-pattern-no-engine"
topology_pattern = "single-threaded-linear"
layer_budgets = []
hitl_placements = []
per_step_overrides = {}
fallback_chain = { primary = { provider = "ollama", model = "llama3.2:3b", family = "local_open_weight" }, same_family = [], cross_family = [] }

[default_model_binding]
provider = "ollama"
model = "llama3.2:3b"

[[steps]]
step_id = "ask-local-model"
step_kind = "inference-step"

[steps.step_payload]
messages = [{ role = "user", content = "Reply with the single word: OK" }]
tools = []
params = { options = { num_predict = 8 } }
```

The loader refuses a field it does not know, so keep the field names exactly.

### The version line

`version = 1` is the manifest format.
It is the only version the loader accepts.

### The `[workflow]` table

| Field | Meaning | Values |
| --- | --- | --- |
| `workflow_id` | The workflow's name. A run reports it, and a paused run is resumed by it. | any text |
| `workload_class` | The kind of work. The project's config must bind this class. | `pipeline-automation`, `software-engineering`, `research`, `content-creation` |
| `persona_tier` | Who operates the workflow. It sets the floor for approval gates, and the [auto-approve policy](security-and-isolation.md#set-what-a-gate-approves-without-asking) applies only at `solo-developer`. It is separate from the deployment's `persona_tier` setting, which decides trace sampling, trace redaction and prompt-version approval; the runtime does not compare the two. | `solo-developer`, `team-binding`, `multi-tenant-compliance` |
| `engine_class` | How the run is executed. Every upstream example uses `pure-pattern-no-engine`, which runs the steps inline. | `pure-pattern-no-engine`, `event-sourced-replay`, `save-point-checkpoint`, `reconciler-loop`, `WAL-segment` |
| `topology_pattern` | How the steps relate. | the six in [Choose one of the six topologies](#choose-one-of-the-six-topologies) |
| `layer_budgets` | Time budgets for the routing layers. Every upstream example leaves the list empty. | a list |
| `hitl_placements` | The approval gates of the workflow. | a list; see [Put an approval gate in a workflow](#put-an-approval-gate-in-a-workflow) |
| `per_step_overrides` | Settings for single steps, keyed by step id. | a table; see below |
| `fallback_chain` | A provider chain written in the manifest. It is a label: it does not choose the provider. | `primary`, `same_family`, `cross_family` |
| `worker_selection` | Who chooses an orchestrator's workers. Optional. | `declared-pool` (the default), `lead-plan` |

The routing rule decides which provider serves a step.
The config's first fallback chain serves every step; `--provider` (and `--model`) override it for one run; a manifest's own model binding does not select the provider.
A more specific setting wins over the chain: a per-step `model_binding`, described below, a workload override or a role binding.
The [providers page](providers.md#how-routing-picks-a-provider) explains the rule and that order.

To choose a model for one step or sub-agent, write its `model_binding` here.
Other places exist: [Choose a model and a thinking level](providers.md#choose-a-model-and-a-thinking-level) lists them with the exact command or manifest line.

`arhugula workflow validate` prints each step's binding and a note when its provider is not enabled.

The loader accepts five more optional fields in this table: `entry_version`, `default_gate_level`, `fanout_timeout_disposition`, `concurrent_cache_warmup` and `sub_agent_briefs`.
No upstream example sets them.

### The `per_step_overrides` table

Each entry is keyed by a step id and repeats that id in `step_id`.
All other fields are optional.

| Field | What it overrides for that step |
| --- | --- |
| `model_binding` | the provider and model, as `{ provider = "...", model = "..." }` |
| `agent_role` | the role the step runs under |
| `prompt_version_sha` | the prompt version that the step receives |
| `engine_class` | the engine class |
| `hitl_placement` | an approval gate for the step |
| `removed_placements` | approval gates that the step drops; only `sub-agent-boundary` can be dropped |

A `model_binding` here is the one manifest setting that does select a provider.

The example `examples/workflows/two-agents.toml` binds step one to `claude_code` with `haiku@low` and step two to `codex` with `gpt-6.1-sol@medium`.
A run of it completed, and its two model-call spans named exactly those models (*witnessed*).
[Choose a model and a thinking level](providers.md#choose-a-model-and-a-thinking-level) shows how to make the models available first.

### The `[default_model_binding]` table

It holds a `provider` and a `model`.
Like `fallback_chain`, it does not choose the provider.
One run flag reads it: `--model` alone keeps this provider.

### The `[[steps]]` entries

Each step has three fields.

| Field | Meaning |
| --- | --- |
| `step_id` | The step's name. It must be unique in the manifest. |
| `step_kind` | What the step does. |
| `step_payload` | The step's input. Its shape depends on the step kind. |

The examples on this page use four of the seven step kinds.

| Step kind | What it does | Payload |
| --- | --- | --- |
| `inference-step` | Sends messages to a model. | `messages`, `tools`, `params` |
| `tool-step` | Calls one tool of a connected tool server. | `tool_id`, `tool_args` |
| `sub-agent-dispatch` | Runs a child workflow. | `child_workflow_id`, `child_manifest_entry`, `child_steps`, `brief` |
| `post-join-synthesis` | Combines the outputs of the branches after they join. It takes no tools. | `messages`, `params` |

The loader also knows `declarative-step`, `HITL-step` and `managed-agents`.
No upstream example uses them.

In an inference step, `params` has the shape that the provider reads.
Ollama reads `options.num_predict` for the reply length; the other providers read `max_tokens`.
Every inference step needs a `params` table, even an empty one (`params = {}`).
Without it the workflow loads and `workflow validate` passes, but the run fails with `RT-FAIL-PAYLOAD-SHAPE ... params Field required` (*witnessed*).

## Choose one of the six topologies

A *topology* is the pattern that relates the steps.
Upstream ships one example for each topology.
List them, together with the manifests of your project:

<!-- witness -->
```sh
arhugula workflow list
```

Output from a deployment with no project manifests:

```text
where              file                                 workflow id                             topology                 notes
upstream examples  minimal.toml                         example-minimal                         single-threaded-linear   1 steps, pipeline-automation
upstream examples  ollama-decentralized-handoff.toml    example-ollama-decentralized-handoff    decentralized-handoff    3 steps, pipeline-automation
upstream examples  ollama-evaluator-optimizer.toml      example-ollama-evaluator-optimizer      evaluator-optimizer      2 steps, content-creation
upstream examples  ollama-first.toml                    example-ollama-first                    single-threaded-linear   1 steps, pipeline-automation
upstream examples  ollama-hierarchical-delegation.toml  example-ollama-hierarchical-delegation  hierarchical-delegation  4 steps, research
upstream examples  ollama-orchestrator-workers.toml     example-ollama-orchestrator-workers     orchestrator-workers     4 steps, research
upstream examples  ollama-parallelization.toml          example-ollama-parallelization          parallelization          2 steps, research
```

| Topology | Upstream example | What the example shows |
| --- | --- | --- |
| `single-threaded-linear` | `ollama-first.toml` | One inference step. Steps run one after another. |
| `decentralized-handoff` | `ollama-decentralized-handoff.toml` | Three stages: draft, review, finalize. One stage owns the work at a time, and each stage acts on the output of the stage before it. |
| `parallelization` | `ollama-parallelization.toml` | Two peer branches. They run at the same time, the driver joins them, and it folds the results in branch order. |
| `orchestrator-workers` | `ollama-orchestrator-workers.toml` | A lead step runs first. Two workers then run at the same time. A synthesis step receives the worker outputs and writes the result. |
| `hierarchical-delegation` | `ollama-hierarchical-delegation.toml` | Orchestrator-workers, applied twice. The root lead has a direct worker and a child workflow with its own lead and two workers. A parent has at most three direct children; a fourth is refused. |
| `evaluator-optimizer` | `ollama-evaluator-optimizer.toml` | A generator writes a tagline and an evaluator judges it. The driver repeats both until the evaluator accepts or three rounds have run. |

Before you copy one of these examples, note three things.

- **The handoff and the evaluator examples need data flow.** Without it, a later step never sees the earlier output: see [Pass one step's output to the next](#pass-one-steps-output-to-the-next).
- **The evaluator must reply with one exact object.** The reply is `{"accepted": true or false, "feedback": "..."}` and nothing else. Any other reply fails the run.
- **`completed` does not mean accepted.** An evaluator-optimizer run that reaches three rounds still ends `completed`. The text output does not show the verdict; `--json` prints the full result.

`minimal.toml` is a seventh file, not a seventh topology.
It is a single step that names the hosted Anthropic model.

## Pass one step's output to the next

By default, a step does not receive the output of the step before it.
The feature `data-flow` changes that: each step then receives the most recently recorded step output.

Read what the feature does and whether it is on:

```sh
arhugula feature show data-flow
```

```text
data-flow: Inter-step data flow
state:  off
needs:  nothing

Each step receives the most recently recorded step output. Handoff and evaluator-optimizer workflows need it; peer branches of a parallel workflow are not meant to consume it.

It merges this into every generated config:

[runtime]
inter_step_data_flow = true
```

Switch it on for every config of the deployment:

```sh
arhugula feature enable data-flow
```

| Topology | Do you need `data-flow`? |
| --- | --- |
| `decentralized-handoff` | Yes. Each stage works on the output of the stage before it. |
| `evaluator-optimizer` | Yes. The evaluator must see the draft, and the generator must see the feedback. |
| `parallelization` | No. Peer branches are not meant to read each other. |
| `orchestrator-workers`, `hierarchical-delegation` | No. The synthesis step receives the worker outputs without it. |
| `single-threaded-linear` | Only when a later step must read an earlier one. |

## Create a manifest

`arhugula workflow new` writes a starting manifest for a topology (*kit extension*).
It derives the manifest from the upstream example for that topology, so the file has the shape that your installed runtime loads.

<!-- witness -->
```sh
arhugula workflow new parallelization --name fanout --project <project>
```

The command writes `<project-path>/workflows/fanout.toml` and checks that it loads.
It then prints the topology, the number of steps and the workload class.

The command makes three changes to the upstream example:

- **It sets the workflow id.** The id is the `--name` you gave.
- **It rewrites the bindings.** Every provider and model in the file becomes your deployment's default provider and its model.
- **It reshapes the step parameters.** For a default provider other than Ollama, `options.num_predict` becomes `max_tokens`.

Then edit the steps and their messages, and keep the field names.

| Option | What it does |
| --- | --- |
| `--name <name>` | Sets the workflow id and the file name. Required. |
| `--project <project>` | Chooses the project. Without it, the command uses the current project. |
| `--output <file>` | Writes to that file, not to the project's `workflows/` directory. |

The command refuses, with exit code 3, when the file already exists.
It also refuses when no project is current and you gave no `--output`.

## Check a manifest

`arhugula workflow validate` loads a manifest through the runtime's own loader.
It calls no provider, so it costs nothing and you can run it after every edit.

<!-- witness -->
```sh
arhugula workflow validate fanout.toml --project <project>
```

```text
<project-path>/workflows/fanout.toml loads.
  workflow id:   fanout
  topology:      parallelization
  workload:      research
  step:          branch-overview (inference-step)
  step:          branch-risks (inference-step)
```

When the manifest does not load, the command exits with code 4 and prints the loader's reason.
This is the message for a topology name that does not exist:

```text
arhugula: <file> does not load (RT-FAIL-CLI-MANIFEST-ENUM-VALUE): invalid enum value at 'workflow.topology_pattern': Input should be 'single-threaded-linear', 'orchestrator-workers', 'decentralized-handoff', 'hierarchical-delegation', 'evaluator-optimizer' or 'parallelization'
```

The command also prints a warning when the project does not bind the manifest's workload class.
Such a run would fail when it starts.

## Run a manifest

Run the manifest you created, on Ollama:

<!-- witness -->
```sh
arhugula run fanout.toml --project <project> --provider ollama
```

A run prints an `override:` line when you pass `--provider` or `--model`, then its progress, then three result lines:

```text
status:    completed
workflow:  fanout
ledger:    <64-character hash>
```

`arhugula workflow run` is the same command as `arhugula run`.

| Flag | What it does |
| --- | --- |
| `--project <project>` | Chooses the project. Without it, the run uses the current project. |
| `--provider <provider>` | Sends every step of this run to this enabled provider first, with the model that your deployment configured for it. |
| `--model <model>` | Sends every step of this run to this model. With `--provider`, it overrides that provider's configured model. |
| `--json` | Prints the full result as JSON, with each step's reply. Text mode does not print replies. |
| `--daemon` | Sends the run to the running daemon. |

The `override:` line names the provider and the model that every step goes to first.
For this run it names `ollama/llama3.2:3b`, the model configured for Ollama, whatever model the manifest holds.

A provider that fails still falls back along the config's chain.
So `status: completed` does not prove that Ollama served the run.

The run's progress output is also written to a log file in `<home>/logs/`.
Read the newest one with `arhugula logs`.

## Put an approval gate in a workflow

An *approval gate* stops a run and asks a person before a step goes on.
Upstream calls this human-in-the-loop (HITL).
You declare gates in the manifest's `hitl_placements` list.

Each placement names a position.
There are three positions.

| Position | Where the gate stands |
| --- | --- |
| `pre-action` | before a tool call |
| `sub-agent-boundary` | at the handoff from a parent to a child workflow |
| `validator-escalation` | after a validator has failed and the retries are used up |

A placement has up to four fields.

| Field | Meaning |
| --- | --- |
| `position` | one of the three positions; required |
| `tool_filter` | for `pre-action`: the exact tool names that the gate covers; patterns are refused |
| `cascade_policy` | replaces the workload class's default cascade policy: `pause`, `proceed` or `cascade-cancel` |
| `timeout` | how long the gate waits for an answer, in milliseconds; without it, the gate waits 900 seconds. The kit sets the step deadline to 960 seconds and the run limit to 3600 seconds, so a gate can wait its full 900 seconds unless you lowered them: see [the capability matrix](configure.md#capability-matrix) |

A gate does not always ask.
The deployment's policy lets some calls pass without asking; see it with `arhugula policy show`:

```text
What an approval gate approves without asking (solo-developer persona):
  solo-floor-auto:            on   read-only tool calls at the solo floor
  local-mutation-floor-auto:  off  tool calls that change local files

With a setting off, the gate asks you in the terminal. A run without a terminal rejects the gate.
```

## Run the gated example

The kit ships a workflow with a gate, `examples/workflows/gated-tool.toml`, and a small tool server for it (*kit extension*).
The workflow has two tool steps.
A `pre-action` placement puts a gate in front of the tool `notes.write`; the tool `notes.read` has no gate.

The server speaks the Model Context Protocol (MCP), which is how the runtime reaches tools.
Its two tools are `notes.read`, which returns its argument, and `notes.write`, which appends its argument to a file beside the server.

Do these steps in order.

1. **Start the tool server.** Run it in a second terminal and leave it running. It listens on the loopback port you give.

   ```sh
   <home>/env/bin/python <home>/kit/examples/mcp/notes_server.py 18765
   ```

2. **Connect the server.** Give the client any name; this example uses `notes` and leaves `--blast-radius` at its default, `READ_ONLY`, although `notes.write` appends to a file. It does so because this deployment refuses every run while a URL client is declared `LOCAL_MUTATION`: see [known gaps](reference/known-gaps.md#platform-and-provider-limits). So the gate asks only because step 4 switches the policy off. Declare your own tool server honestly when it writes: read [Declare how far you trust an MCP server](security-and-isolation.md#declare-how-far-you-trust-an-mcp-server) first.

   ```sh
   arhugula mcp add notes --url http://127.0.0.1:18765/mcp
   ```

3. **Check the connection.** The command lists the two tools.

   ```sh
   arhugula mcp test notes
   ```

4. **Make the gate ask.** With this setting off, the gate asks you in the terminal.

   ```sh
   arhugula policy set solo-floor-auto off
   ```

5. **Run the workflow.** Run it in a terminal, because a run without a terminal rejects the gate.

   ```sh
   arhugula run <home>/kit/examples/workflows/gated-tool.toml
   ```

6. **Answer the gate.** The run stops at the first step and shows the call it is about to make. Type `approve` within 15 minutes: the gate waits 900 seconds, and the kit's step deadline is 960 seconds. After the step deadline the run fails with `RT-FAIL-STEP-DISPATCH-TIMEOUT`; [the capability matrix](configure.md#capability-matrix) shows how to change the deadline.

The prompt and the result of an approved run (*witnessed*), with the progress lines left out:

```text
HITL gate at pre-action
step: write-note (tool-step)
payload sha256: 87d1662069040e6133d8bd1e3f900cbb3d965a791268bbf896f2191d2e5538e8
payload: {"tool_args":{"value":"approved by a person"},"tool_id":"notes.write"}
answer (approve | edit | reject | respond | hold | cancel): approve
...
status:    completed
workflow:  example-gated-tool
ledger:    21b9f014c2e4e7d5b32c295e83f0660bde95e650eff0feef88ad4e565f2e253b
```

The second step, `read-note`, runs without asking, because no placement names its tool.

### What each answer does

| Answer | Result |
| --- | --- |
| `approve` | The step runs once. |
| `edit <JSON object>` | The step runs once, with that object as its payload. |
| `reject [reason]` | The step does not run. |
| `respond <text>` | The gate receives your text. |
| `hold` | The run pauses, and you answer later. |
| `cancel` | The gate ends, and the step does not run. |

An answer the gate does not know refuses the gate, and the step does not run.

### Hold a gate and answer it later

`hold` needs two things in place first: durable pause (`arhugula pause enable`) and a webhook (`arhugula webhook set <url>`).
A held run ends with `status: paused` and exit code 5, and the webhook receives a notification (*witnessed*).

Exit code 5 has two meanings.
From the runtime, it means a run on hold at a gate; from the kit, it means that an external tool failed.

| To do this | Run |
| --- | --- |
| List the runs that may be paused | `arhugula gate list` |
| Approve the held gate and continue | `arhugula gate approve <manifest>` |
| Reject the held gate | `arhugula gate deny <manifest> --reason <text>` |
| Answer with an edit or a response | `arhugula resume <manifest> --decision edit --edited-proposal <JSON>` |

To answer with a response, pass `--decision respond --response-text <text>`.

The list from `arhugula gate list` is an upper bound, not an inventory.
The pause journal records no marker when a pause is resolved (*upstream limit*).

### Put the deployment back

When you finish the example, undo the three changes:

```sh
arhugula policy set solo-floor-auto on
arhugula mcp remove notes
```

Then stop the tool server in its terminal.

## Upstream limit: a lead does not direct its workers

You might expect the lead of an orchestrator-workers workflow to choose its workers and brief them.
At the pinned upstream commit it does not (*upstream limit*).

- **The workers are the declared steps.** Every worker step in the manifest runs. The lead's reply does not select them or order them.
- **The workers do not receive the lead's reply.** The lead runs first and is recorded as its own step. Nothing else uses its reply.
- **The synthesis sees worker outputs only.** It does not receive the lead's reply either.

The same holds for `hierarchical-delegation`: the tree is the declared steps, and no step receives its lead's reply.

The manifest field for a lead-directed plan exists: `worker_selection = "lead-plan"`.
The loader accepts it on these two topologies.
But the runtime does not yet turn a model's reply into the worker plan that the field needs, so such a run has no plan to follow.
Keep the default, `declared-pool`, and write each worker's instructions in its own step.
The [known gaps page](reference/known-gaps.md) lists this limit with the others.

## Sources

Kit modules and files:

- `lib/arhugula_kit/verbs_run.py`
- `lib/arhugula_kit/workflows.py`
- `lib/arhugula_kit/common.py`
- `lib/arhugula_kit/verbs_config.py`
- `fragments/data-flow.toml`
- `examples/workflows/gated-tool.toml`
- `examples/workflows/two-agents.toml`
- `examples/mcp/notes_server.py`

Upstream sources, relative to the home:

- `upstream/examples/README.md` and `upstream/examples/*.toml`
- `upstream/docs/how-to-operate-runtime.md`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/workflow_manifest_loader.py`
- `upstream/harness-runtime/src/harness_runtime/cli/app.py`
- `upstream/harness-cp/src/harness_cp/workflow_manifest_entry.py`
- `upstream/harness-cp/src/harness_cp/hitl_placement.py`
- `upstream/harness-cp/src/harness_cp/workflow_driver_types.py`
- `upstream/harness-cp/src/harness_cp/topology_pattern.py`
