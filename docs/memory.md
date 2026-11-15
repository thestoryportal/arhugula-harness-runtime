# Memory

This page is for the operator who decides what the harness remembers, and for the workflow author who relies on it.
After reading it you can check what a project has stored, promote a captured turn to long-term memory, and remove a record.

Memory needs no extra software.
If a command here reports a missing tool, see [the dependency list in the install guide](install.md#dependencies).
[The command reference](reference/cli.md) lists the flags the kit reads.
The flags the runtime's operator tool reads are in [Every memory verb](#every-memory-verb).

## Contents

- [What the harness remembers](#what-the-harness-remembers)
- [How memory reaches a model](#how-memory-reaches-a-model)
- [Where a project's memory lives](#where-a-projects-memory-lives)
- [Check what a project has stored](#check-what-a-project-has-stored)
- [Promote a captured turn to long-term memory](#promote-a-captured-turn-to-long-term-memory)
- [Remove or retire a record](#remove-or-retire-a-record)
- [Every memory verb](#every-memory-verb)
- [Switch the memory features](#switch-the-memory-features)
- [Limits](#limits)
- [Sources](#sources)

## What the harness remembers

Memory is a project notebook that the harness keeps on disk and reads back on later runs.
It is on by default: `init` question 9 offers the feature `memory`, and Enter accepts it.

Every record is typed and carries its scope and its origin.
The harness keeps three tiers of records and one ledger.

| Tier | What it holds | How a record gets there |
| --- | --- | --- |
| Episodic | One record per run and one per completed turn | The runtime captures it during every run |
| Semantic | Facts, preferences, decisions, conventions, failure lessons, research notes | You approve a proposal |
| Procedural | Snapshots of how to do things, and promoted updates | You approve a proposal, with the feature `memory-procedural` on |

The ledger is the memory-operation ledger.
It records every capture, retrieval, injection, promotion decision and removal, and each entry carries the hash of the entry before it.

The stored records are the one authority.
The retrieval index is built from them and the runtime rebuilds it when it is missing or stale.

## How memory reaches a model

The runtime picks one access mode for each model call, in this priority order:

1. **Memory tools.** The model calls `memory.*` tools to look things up. This needs a provider that supports tool calls, and a policy that allows it.
2. **The prompt packet.** The runtime adds a small, read-only summary of retrieved records to the prompt. The packet stays within a token budget, 1200 tokens by default.
3. **Provider-native memory.** The provider's own remote memory API. The runtime uses it only when you turn on the feature `memory-native`.
4. **No memory access.** This applies when policy or capability denies every other mode.

`init` question 10 asks which modes you want.
It appears only when memory is enabled.

| Answer | What it turns on |
| --- | --- |
| `packet` | A memory packet is added to each prompt |
| `packet+tools` (default) | The packet, plus memory tools the agent can call |

Before any record reaches a model, the runtime filters by policy.
It checks scope, provider family, workflow, redaction state, tombstone state and retention state before it ranks anything.

## Where a project's memory lives

Each project has its own memory root under the state root:

```text
<home>/state/projects/<project>/memory/
  episodic/runs/          one directory per run
  semantic/               facts/ preferences/ decisions/ conventions/ failures/ research/
                          index.jsonl, the retrieval index
  procedural/             snapshots/ promoted/
  durable/                memory_ops.jsonl, the memory-operation ledger
```

Each project's generated config names its own memory root, so projects do not share memory.
`arhugula state status` shows, for each project, whether its memory root exists.

The deployment default has a memory root too, at `<home>/state/memory`.
Name it with `--project default`.

## Check what a project has stored

`arhugula memory status` is a *kit extension*.
It shows the memory root, the access modes, a count of records for each kind, and a summary of the ledger.

<!-- witness -->
```sh
arhugula memory status --project <project>
```

This is the output for the project `demo` on the development deployment (*witnessed*):

```text
project:        demo
memory root:    <home>/state/projects/demo/memory
prompt packet:  on (budget 1200 tokens)
memory tools:   on
native memory:  off

kind                  records
episodic runs         14
semantic facts        0
semantic preferences  0
semantic decisions    0
semantic conventions  0
semantic failures     0
semantic research     0
procedural snapshots  0
procedural promoted   0

operation ledger: 61 entries (capture 29, inject 15, retrieve 17)
```

Read it this way:

- **Episodic runs 14.** Fourteen runs wrote memory for this project.
- **Every semantic count 0.** Nobody has proposed a memory yet, so nothing is long-term memory.
- **The ledger line.** The runtime captured records 29 times, looked up memory 17 times, and recorded 15 injection decisions.

Before the first run of a project, the same command prints `no run has written memory yet.` in place of the table.

### Read the ledger

`arhugula memory operations` prints the whole ledger as one JSON list.

```sh
arhugula memory operations --project <project>
```

This is one entry from the development deployment, trimmed (*witnessed*).
The runtime wrote it when a run started.

```text
  {
    "action_id": "capture:run_start:mem:episodic:episodic_run:bf1d2eb488ef03f197e07f2421c0bfeb288d23d7becb3e26683b7ece6bde83ba",
    "actor": {
      "actor_class": "agent",
      "actor_id": "harness-runtime"
    },
    ...
    "memory_refs": [
      "mem:episodic:episodic_run:bf1d2eb488ef03f197e07f2421c0bfeb288d23d7becb3e26683b7ece6bde83ba"
    ],
    "model": "llama3.2:3b",
    "operation_kind": "capture",
    "operation_projection": "none",
    "policy_ref": "policy:automatic-local-memory",
    "prior_event_hash": "08d8d2f5dfaba72406585fc937cef647b9e08437834aa6ffc3f061fdb393b587",
    ...
    "provider": "ollama",
    ...
    "response_hash": "0d0b1882a10ea7acb98e177ae8c41d5b40c3d9a2bddb6c7949972dfeb5f09dd5",
    ...
    "run_id": "a38001c12e8afae9027f7d2d8f1fa3a193a57a61de66dfcad05af17313050f48",
    "step_id": null,
    "timestamp": "2026-11-15T02:27:17.764969+00:00"
  },
```

Three fields matter for the next task:

- **`memory_refs`** names the records the operation touched. A record ID has the form `mem:<tier>:<kind>:<hash>`.
- **`run_id`** names the run that owns the record. You pass it as `--run-id` when you inspect or propose from that record.
- **`prior_event_hash`** equals the `response_hash` of the entry before it. That chain shows whether anyone altered the ledger.

## Promote a captured turn to long-term memory

The runtime treats a captured turn as evidence.
Promotion is review-bound: nothing a model wrote can reach a later prompt until you approve it.

Each proposal is decided at most once.
After you approve or deny a proposal, the runtime refuses a second decision on it.

### Use the guided review

`arhugula memory review` is a *kit extension*.
It walks through the captured turns, newest first, and asks you what to do with each.
Run it in a terminal, because it asks questions.

```sh
arhugula memory review --project <project>
```

For each captured turn it prints the record and then asks, in this order:

1. **Propose, skip or quit.** The prompt is `[p]ropose a memory from this turn, [s]kip, [q]uit`. Enter skips.
2. **The kind.** Choose one of `convention`, `decision`, `fact`, `failure_learning`, `procedural_update`, `research`. Enter chooses `fact`.
3. **The statement.** Type one sentence the harness should remember.
4. **The decision.** The prompt is `[a]pprove now, [d]eny, [l]eave it proposed`. Enter approves.
5. **How it may be used.** This is asked only when you approve. Enter chooses `prompt_packet_allowed`.

If you deny, the review asks for a reason.
It ends with a line such as `review done: 1 proposed, 1 approved.`

The answer to step 5 is the record's injection policy.

| Injection policy | Meaning |
| --- | --- |
| `never` | The record is stored and never given to a model |
| `retrieval_only` | The record can be retrieved, and is not added to a prompt |
| `prompt_packet_allowed` | The record may appear in the prompt packet |
| `tool_allowed` | The record may be returned by a memory tool |
| `native_allowed` | The record may be sent to provider-native memory |

The runtime stores a proposal as one record and the decision on it as a second record.
`arhugula memory status` counts both under the semantic kind, or under `procedural snapshots` for a `procedural_update`.
On later runs the runtime can retrieve the record and, if its injection policy allows, place it in the prompt packet.

### Do the same steps one verb at a time

An agent or a script cannot answer the guided review.
Use the single verbs.
They are the runtime's own operator tool, and each prints one JSON document.

1. Find a captured turn in the ledger: an entry whose `memory_refs` holds an ID with `episodic_turn`. That ID is the `<source-id>` in the steps below. Note the entry's `run_id` as well.
2. Read the record:

   ```sh
   arhugula memory inspect <source-id> --project <project> --run-id <run-id>
   ```

3. Propose a memory from it. The reply carries the proposal's `memory_id`, which is the `<proposal-id>` in step 4.

   ```sh
   arhugula memory propose <source-id> --project <project> --run-id <run-id> --kind fact --statement "The team deploys on Fridays."
   ```

4. Approve it, or deny it with a reason:

   ```sh
   arhugula memory approve <proposal-id> --project <project> --run-id <run-id> --source <source-id> --injection-policy prompt_packet_allowed
   ```

   ```sh
   arhugula memory deny <proposal-id> --project <project> --run-id <run-id> --source <source-id> --reason "not true"
   ```

The kit reads `--project`, `--operator` and `--run-id` itself.
Every other argument goes to the runtime's operator tool unchanged.

The operator tool refuses in these cases and writes nothing:

- **The proposal was already decided.** The runtime allows one decision for each proposal.
- **The source does not match.** The proposal was not made from the source you named, or the source's scope changed.
- **The policy forbids it.** For example, a `procedural_update` proposal while the feature `memory-procedural` is off.

The kit reports such a refusal with the tool's own text.

## Remove or retire a record

Three verbs take a record out of use.
Each one is a dry run unless you add `--apply`, and each needs `--reason`.

| Verb | Use it when |
| --- | --- |
| `arhugula memory redact` | The record's content must go, for example because it holds a secret |
| `arhugula memory tombstone` | The record is obsolete and must never be used again |
| `arhugula memory expire` | The record has passed its retention period |

Check first, then apply:

```sh
arhugula memory redact <memory-id> --project <project> --run-id <run-id> --reason "contains a secret"
arhugula memory redact <memory-id> --project <project> --run-id <run-id> --reason "contains a secret" --apply
```

The dry run prints `"applied": false` and the record's current state.
With `--apply`, the reply prints `"applied": true` and the new state.

A redacted or tombstoned record stays in the ledger, so you can audit it.
The runtime excludes it from retrieval, from the prompt packet and from memory tools.
None of the three verbs deletes a file silently: each is a recorded memory operation.

`--replacement-summary <text>` is optional on all three verbs.

`--run-id` is required for an episodic record, because the runtime stores it under its run.
You can leave it out for a semantic or procedural record.

## Every memory verb

`arhugula memory status`, `review` and `export` are *kit extensions*.
The other ten verbs pass your arguments to the runtime's operator tool.

Every verb accepts `--project <project>`.
Every verb except `export` accepts `--operator <name>`, the name recorded on the operation; the default is your login name.
The ten runtime verbs accept `--run-id <run-id>`, the run that owns a record.

| Verb | What it does | Changes memory |
| --- | --- | --- |
| `arhugula memory status` | Shows the memory root, the access modes, record counts and a ledger summary | No |
| `arhugula memory review [--limit N]` | Walks through captured turns so you can propose, approve or deny. The default limit is 10 turns | Yes, through your answers |
| `arhugula memory export [--output <file>]` | Writes the memory root to an archive with mode 0600. The default is `<home>/backups/memory-<project>-<time>.tar.gz` | No |
| `arhugula memory operations` | Prints the memory-operation ledger | No |
| `arhugula memory inspect <memory-id>` | Prints one record, including a redacted one | No |
| `arhugula memory propose <source-id> --kind <kind> --statement <text> [--confidence low\|medium\|high]` | Proposes a memory from captured evidence. The default confidence is `medium` | Yes |
| `arhugula memory approve <proposal-id> --source <source-id> --injection-policy <policy> [--rationale <text>]` | Activates a proposal | Yes |
| `arhugula memory deny <proposal-id> --source <source-id> --reason <text>` | Denies a proposal | Yes |
| `arhugula memory redact <memory-id> --reason <text> [--apply]` | Redacts a record's content | Only with `--apply` |
| `arhugula memory tombstone <memory-id> --reason <text> [--apply]` | Tombstones a record | Only with `--apply` |
| `arhugula memory expire <memory-id> --reason <text> [--apply]` | Expires a record for retention | Only with `--apply` |
| `arhugula memory migrate <legacy-root> <path>... --migration-id <id> [--visibility <v>] [--apply]` | Reads memory files from an older `/memories/...` layout and reports them. With `--apply` it writes them to the memory root. It needs `--run-id` | Only with `--apply` |
| `arhugula memory compact <compaction-id> --source <source-id> --summary <text> [--disposition <candidate-id> <disposition> <rationale>] [--apply]` | Lists the candidates that compacting the sources would produce. With `--apply` it records your disposition for each. It needs `--run-id` | Only with `--apply` |

For `migrate`, `--visibility` is one of `private` (default), `project`, `workflow`, `tenant`, `public`.

For `compact`, repeat `--source` for each source and `--disposition` for each candidate.
A disposition is one of `discard`, `keep_episodic`, `promote`, `queue`.
`--promoted-to <candidate-id> <memory-id>` names the record a promoted candidate went to.

## Switch the memory features

Four named features control memory.
`arhugula feature show <name>` prints what a feature does and the TOML it merges.

```sh
arhugula feature show memory
```

```text
memory: Memory
state:  on
needs:  nothing

The harness captures run events and turns, and adds a memory packet to each prompt. Promotion to long-term memory waits for your review (`arhugula memory review`).

It merges this into every generated config:

[runtime.memory]
enabled = true
root_path = "{{TARGET_STATE}}/memory"
```

| Feature | What it changes | Needs |
| --- | --- | --- |
| `memory` | Turns memory on, with a memory root for each project | Nothing |
| `memory-native` | Allows a provider's own remote memory API as well. Memory then also lives with that provider | `memory`, and a provider that offers a memory API (the Anthropic API provider) |
| `memory-encrypted` | The Memory tool stores its files encrypted at rest instead of as plain files | `memory` |
| `memory-procedural` | Reviewed proposals target procedural memory (how to do things) instead of semantic memory (facts and decisions) | `memory` |

Turn a feature on or off with `arhugula feature enable <name>` and `arhugula feature disable <name>`.
[Configure the deployment](configure.md) explains features and the full list.

With memory off, every memory verb refuses and prints the fix: `arhugula feature enable memory`.

## Limits

- **Preferences cannot be proposed here.** The operator tool does not accept `preference` proposals, so `semantic preferences` stays at 0 through this path.
- **Scope cannot be widened.** A proposal takes the scope of its source. There is no override.
- **One kind of target at a time.** With `memory-procedural` off, the policy permits semantic proposals. With it on, the policy permits procedural proposals.
- **A decision is final.** The runtime refuses a second decision on the same proposal.
- **Native memory is remote.** With `memory-native` on, memory also lives with the provider. It stays the last choice in the priority order.
- **The record counts are file counts.** `arhugula memory status` counts entries on disk for each kind. It does not check their state, so a proposal, an approval and a denial each count as one.
- **Memory is not source control.** It helps agents carry context across runs. Keep decisions that matter in your repository as well.

## Sources

Kit modules:

- `kit/lib/arhugula_kit/verbs_memory.py`
- `kit/lib/arhugula_kit/questions.py` (questions 9 and 10)
- `kit/lib/arhugula_kit/render.py`
- `kit/fragments/memory.toml`, `memory-native.toml`, `memory-encrypted.toml`, `memory-procedural.toml`

Upstream documents and code:

- `upstream/docs/memory-layer-readme.md`
- `upstream/docs/memory-substrate.md`
- `upstream/harness-runtime/src/harness_runtime/admin/memory_operator.py`
- `upstream/harness-runtime/src/harness_runtime/memory_promotion.py`
