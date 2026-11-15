# Operate the deployment day to day

This page is for the operator of an installed deployment.
After reading it you can run workflows, answer approval gates, pause and resume a run, and use the daemon.
You can also read logs and traces, back up the state root, and read every exit code.
If a command here fails, look up its message in [troubleshooting](troubleshooting.md). If the deployment is not installed yet, start with [install](install.md).

Every command is `arhugula <verb>`. When `arhugula` is not on your `PATH`, run `<home>/bin/arhugula`. The full list of verbs and flags is in the [command reference](reference/cli.md).

## Contents

- [Run a workflow](#run-a-workflow)
- [Check what ran](#check-what-ran)
- [Answer an approval gate at the terminal](#answer-an-approval-gate-at-the-terminal)
- [Put a gate on hold and answer it later](#put-a-gate-on-hold-and-answer-it-later)
- [Run workflows through the daemon](#run-workflows-through-the-daemon)
- [Read a run log](#read-a-run-log)
- [Read traces](#read-traces)
- [Look after the state root](#look-after-the-state-root)
- [Read an exit code](#read-an-exit-code)
- [Expect trace-export retry lines when the observability tier is off](#expect-trace-export-retry-lines-when-the-observability-tier-is-off)
- [Stop these before an upgrade or a relocate](#stop-these-before-an-upgrade-or-a-relocate)
- [Sources](#sources)

## Run a workflow

A workflow is described by a manifest, which is a TOML file. Run one with:

```sh
arhugula run <manifest> [--project <project>] [--provider <name>] [--model <name>] [--daemon] [--json]
```

| Flag | What it does |
| --- | --- |
| `--project <project>` | Runs against that attached project. Without it, the run uses the current project. The name `default` means the deployment's own default config. |
| `--provider <name>` | Sends every step to that enabled provider, for this run only. Without `--model`, the run uses the model that the deployment configured for that provider. |
| `--model <name>` | Sends every step to that model, for this run only. |
| `--daemon` | Sends the run to the running daemon. See [Run workflows through the daemon](#run-workflows-through-the-daemon). |
| `--json` | Prints the full result as JSON, with each step's reply. |

The config's first fallback chain serves every step; `--provider` and `--model` override it for one run; a manifest's own model binding does not select the provider.
One manifest setting is the exception: a `model_binding` in `per_step_overrides` sends its step to the provider it names. See [How routing picks a provider](providers.md#how-routing-picks-a-provider).
To change the chain itself, see [providers](providers.md).

### How a manifest name is found

You can type a path or only a file name. `arhugula run` looks in these places, in this order, and uses the first file it finds:

1. The path as you typed it, from the directory you are in.
2. The project's repository.
3. The project's `workflows/` directory.
4. The upstream checkout, `<home>/upstream`.
5. Upstream's examples, `<home>/upstream/examples`.

`arhugula workflow list` shows the manifests of the current project and of upstream's examples.

### What a run prints

This run used the local Ollama provider (*witnessed*). The lines marked `INFO` are the runtime's progress on standard error. The last three lines are the result.

```text
override:  every step dispatches first to ollama/llama3.2:3b; the config's fallback chain applies if that candidate fails
[11/14/26 21:38:08] INFO     HTTP Request: GET                   _client.py:1740
                             http://127.0.0.1:11434/api/tags
                             "HTTP/1.1 200 OK"
...
status:    completed
workflow:  example-ollama-first
ledger:    042bb28f065c0f886b1a7bb4c33f0ed805e7543174ae7cd6b2accb80cab2fe58
```

- **`override:`** appears only with `--provider` or `--model`. It names where every step goes first. A provider that fails still falls back along the config's chain.
- **`status:`** is `completed`, `failed`, `paused`, `drained` or `partial`. `drained` means that the run limit ended the run. `partial` means that a fan-out run finished although at least one branch failed.
- **`ledger:`** is the hash of the newest audit entry in the project's state ledger after the run. An audit entry is one whose action id starts with `audit:`. This hash is not the `head_hash` that `arhugula status` shows, which belongs to the newest entry of any kind.

A subscription CLI provider (`claude_code`, `codex`, `gemini`, `antigravity`) is never priced. So a run on one writes no cost entry (*upstream limit*, by design).
It writes no audit entry either, so its `ledger:` hash is the same as before the run.
Its step entries are still written, and `arhugula status` shows them (*witnessed*).
Upstream issue #1743 covers the missing cost and audit entries.

## Check what ran

`arhugula status` shows the newest entries of the current project's state ledger. It also lists the pause journals.

<!-- witness -->
```sh
arhugula status
```

With `--last 3`, it printed this on the development deployment:

```text
harness-inspect — read-only summary
  ledger:        <home>/state/projects/demo/state-ledger/state.jsonl
  total_entries: 62
  head_hash:     bd7511f595c8ba20fd0613eadbf3119ad617042f3a0ad10bb87468eafd18fc8a

Last 3 entries:
...
  - action_id=workflow:example-ollama-first:step:0 actor=agent/harness-runtime ts=2026-11-15T04:36:12.545021+00:00 response_hash=bd7511f595c8ba20…
...
```

- **`--last <n>`** sets how many entries to show. The default is 10.
- **`--json`** prints the summary as JSON.
- **`--project <project>`** shows another project's ledger.

Before a project's first run, `status` says that no run has been recorded yet and exits 0.

## Answer an approval gate at the terminal

An approval gate is a point where the runtime stops and asks a person before it goes on. The runtime's messages call it a `HITL` gate, for "human in the loop".

By default the solo-developer policy approves read-only tool calls without asking. To have the gate ask you, turn that setting off:

```sh
arhugula policy set solo-floor-auto off
```

`arhugula policy show` prints the current settings. The policy itself is explained in [security and isolation](security-and-isolation.md).

When a run reaches a gate, it prints the step, the payload and its hash, then waits for one answer. This is the kit's example `examples/workflows/gated-tool.toml`, answered with `approve` (*witnessed*). Its setup is in [workflows](workflows.md).

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

| Answer | Result |
| --- | --- |
| `approve` | The gated step runs once. |
| `edit <JSON object>` | The step runs once with that object as its payload. |
| `reject [reason]` | The step does not run. |
| `respond <text>` | Your text goes to the gate. |
| `hold` | The run pauses so that you can answer later. It needs durable pause and a webhook: see the next section. |
| `cancel` | The gate ends and the step does not run. |

The gate asks only when the run has a terminal. A run with no terminal rejects the gate with `noninteractive: no operator terminal` (*upstream limit*). An answer the gate does not recognise also rejects it.
If you stay silent, the gate waits for its configured timeout, or for 900 seconds when none is set.

The wait is part of the step, so the step deadline and the run limit apply to it too: 30 and 60 seconds unless set.
So at default settings you must answer within 30 seconds, and the 900 seconds are not reached.
A gate of the same example that was answered `approve` after 45 seconds ended the run with exit code 1 (*witnessed*):

```text
status:    failed
workflow:  example-gated-tool
ledger:    6911de13d839b9d5ae23f8a8a899110fb7176664e815062e4c2c93b24c91840f
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class='step-failure: RT-FAIL-STEP-DISPATCH-TIMEOUT: step dispatch exceeded 30.0s bound'
```

Raise both before a run whose gate may wait longer: see `step_dispatch_timeout_seconds` and `drain_timeout_seconds` in [the capability matrix](configure.md#capability-matrix).
`arhugula policy set <setting> off` prints a note with the same deadline.

## Put a gate on hold and answer it later

Answering `hold` pauses the run and writes it to a pause journal. The process exits, and you answer the gate later with another command. This is called a durable pause.

`hold` needs two things. Without either one, the runtime rejects the gate.

1. Turn durable pause on:

   ```sh
   arhugula pause enable
   ```

2. Give the runtime a URL to notify when a run goes on hold:

   ```sh
   arhugula webhook set http://127.0.0.1:18766/hook
   ```

### Try it with the example receiver

The kit ships a small receiver, `examples/webhook/receiver.py` (*kit extension*). It records every notification in `received.jsonl` beside itself. A real receiver would notify a person.

Start it in a second terminal, on the port you gave `webhook set`:

```sh
<home>/env/bin/python <home>/kit/examples/webhook/receiver.py 18766
```

Then run the gated workflow in the first terminal and answer `hold` (*witnessed*). The run posts the notification, prints `status: paused` and exits with code 5.

```sh
arhugula run <home>/kit/examples/workflows/gated-tool.toml
```

```text
answer (approve | edit | reject | respond | hold | cancel): hold
                    INFO     HTTP Request: POST                  _client.py:1740
                             http://127.0.0.1:18766/hook
                             "HTTP/1.0 200 OK"
...
status:    paused
workflow:  example-gated-tool
ledger:    d4c22b1154ba0ed613b4d66a489ee1b3a7e6fda5179e5eec303f14b3b32aa421
```

The receiver recorded this notification (*witnessed*):

```text
{"path": "/hook", "body": "{\"approval_id\":\"workflow:example-gated-tool:step:0\",\"idempotency_key\":\"hitl:workflow:example-gated-tool:step:0:pre-action\",\"gate_evaluation_ref\":\"workflow:example-gated-tool:step:0\",\"payload_body\":{\"escalation_reason\":\"operator_hold\",\"parent_step_id\":\"write-note\",\"fail_class\":null,\"fail_detail_hash\":null,\"proposed_response_palette\":[\"approve\",\"edit\",\"reject\",\"respond\"]}}"}
```

### List the held gates

<!-- witness -->
```sh
arhugula gate list
```

```text
1 pause journal(s). Each MAY hold an outstanding pause:
  {"classification": "not-attributable", "file": "eb240bbf7cc7d52025e41e94d639ba8486c17c6861568beabe4a7b2dbd9beb80.jsonl", "identity_actionable": false, "latest_record_digest": "fd65c54f8d0d397f5f73d961b1d0292b887379ae63355568bdbb971418843c39", "record_count": 1, "workflow_id": "example-gated-tool"}

upstream limit: the journal records no pause-resolved marker, so this list is an upper bound, not an inventory of outstanding pauses.
answer one with:  arhugula gate approve <manifest>   or   arhugula gate deny <manifest> --reason <text>
```

The list is an upper bound (*upstream limit*). A journal stays in the list after its pause was answered, because the runtime writes no marker when a pause ends. When no journal exists, the command says that no workflow is paused.

### Approve or deny a held gate

Pass the same manifest that the paused run used.

```sh
arhugula gate approve <manifest>
arhugula gate deny <manifest> --reason "<text>"
```

Approving the held gate of the example continued the run to the end (*witnessed*):

```sh
arhugula gate approve <home>/kit/examples/workflows/gated-tool.toml
```

```text
...
status:    completed
workflow:  example-gated-tool
ledger:    dd4c2a54fdcfced7716e5b437dd35fa153b75e41edb95356a8433c47f140a1db
```

The verb that rejects a held gate is `gate deny`. The word `reject` is an answer at the prompt and a value of `arhugula resume --decision`.

### Resume with another decision

`arhugula resume` continues the latest durable pause of a workflow. Use it when the answer is `edit` or `respond`, which the two `gate` verbs do not cover.

```sh
arhugula resume <manifest> --decision approve
arhugula resume <manifest> --decision edit --edited-proposal '<JSON object>'
arhugula resume <manifest> --decision respond --response-text "<text>"
arhugula resume <manifest> --decision reject --reason "<text>"
```

The runtime sets three rules:

- Only the latest pause of a workflow can be resumed.
- A new run cancels the pause. If you start the same workflow again with `arhugula run`, the earlier pause can no longer be resumed. So resume a paused workflow; do not run it again.
- A refused resume starts nothing. It exits 6, or 7 when the runtime refuses the resume claim, and prints `resume refused:` with the reason.

## Run workflows through the daemon

The daemon is one long-lived runtime process for a project. It loads the config once and serves runs until you stop it.
So after any command that changes configuration, run `arhugula daemon stop` and then `arhugula daemon start`. Until then the daemon serves runs with the earlier config.

```sh
arhugula daemon start [--project <project>]
arhugula run <manifest> --daemon
arhugula daemon stop [--project <project>]
```

- **`daemon start`** waits up to 60 seconds for the daemon to open its socket. It prints the process id, the socket and the log file.
- **`daemon stop`** asks the daemon to finish its work and exit.
- The daemon's files are `<home>/run/<project>.sock`, `<home>/run/<project>.pid` and `<home>/logs/daemon-<project>.log`. For the deployment default, the name is `default`.
- A gate still asks in your terminal. The daemon keeps the result and the audit record.
- A long run is limited by the client's wait of one hour. After that the client exits with code 4 and `RT-FAIL-CLI-DAEMON-RESULT`. That does not prove that the daemon cancelled the run.

See which projects have a running daemon:

<!-- witness -->
```sh
arhugula daemon status
```

```text
project             daemon       socket
deployment default  not running  -
demo                not running  -
```

### Reach the daemon from an agent CLI

The daemon serves the Model Context Protocol (MCP) over a Unix socket. MCP clients such as Claude Code connect over stdio or a network port, so they cannot use that socket (*upstream limit*). `arhugula daemon expose` prints the alternative that works (*kit extension*):

<!-- witness -->
```sh
arhugula daemon expose
```

```text
daemon for demo: not running; start it with `arhugula daemon start`
MCP endpoint (streamable HTTP over a Unix socket): <home>/run/demo.sock
tool: run_workflow(workflow_id)

An agent CLI in the project reaches the harness most simply through this command:
  <home>/bin/arhugula run <manifest> --project demo --daemon

Upstream limit: MCP clients such as Claude Code connect over stdio or TCP HTTP, not a Unix
socket, so `claude mcp add` cannot point at this endpoint directly at this pin.
```

More on agent CLIs is in [agents](agents.md).

## Read a run log

Every `run` and `resume` writes a log file under `<home>/logs/` (*kit extension*). The log holds the runtime's command line, everything the run wrote to standard error, and a last line `exit: <code>`. The result lines on standard output are not in the log.
A run log can quote prompts and tool output. So the kit creates each one with mode 0600: only you can read it.

List the log files, newest first:

<!-- witness -->
```sh
arhugula logs --list
```

```text
written              bytes   file
2026-11-14 21:36:12  1340    run-demo-20261114T213609-33249.log
2026-11-14 21:32:10  1340    run-demo-20261114T213206-31233.log
2026-11-14 21:12:11  2620    install-env.log
...

directory: <home>/logs
```

| Command | What it shows |
| --- | --- |
| `arhugula logs` | The last 60 lines of the newest log. |
| `arhugula logs <file>` | A named log. Take the name from `logs --list`. |
| `arhugula logs --lines <n>` | That many lines from the end. |
| `arhugula logs --collected` | What the collector's logs pipeline has written. It needs the observability stack: see [observability](observability.md). |

`arhugula logs` takes no `--project`. The name of a run log starts with `run-` or `resume-` and the project name, so the list tells you which project a log belongs to. For the deployment default, the name is `default`.

## Read traces

The runtime writes every run's spans to a local span store, `<home>/state/observability/spans.sqlite`. It does so whether or not the observability stack is up.

<!-- witness -->
```sh
arhugula trace list
```

```text
started              took   spans  workflow              status  trace id
2026-11-14 21:36:12  0.1 s  11     example-ollama-first  ok      8a6be66335912d11d4593a0d9f35d278
2026-11-14 21:32:09  0.7 s  11     example-ollama-first  ok      807ca5f2e1101786c5900be851d8205c
2026-11-14 21:16:33  0.0 s  9      example-ollama-first  error   e0088d4b5d569264200b45c7b0498464
...
```

| Command | What it does |
| --- | --- |
| `arhugula trace list [--limit <n>]` | Lists the newest traces. The default is 20. *Kit extension*. |
| `arhugula trace browse` | Opens the runtime's trace browser. It needs a terminal. |
| `arhugula trace export [--trace-id <id>] [--out <file>]` | Writes spans as JSON lines, one span per line. *Kit extension*. |

Before the first run there is no span store, and these verbs exit 3 and say so. Dashboards and Tempo are covered in [observability](observability.md).

## Look after the state root

The state root is `<home>/state`. It holds every project's ledger and memory, the pause journals and the local span store.

### See what the state root holds

<!-- witness -->
```sh
arhugula state status
```

```text
state root:        <home>/state  (verified by the runtime)
size:              1.3 MiB
pause-journal:     <home>/state/pause-journal  (16 files)
span store:        <home>/state/observability/spans.sqlite  (871 spans in 59 traces)

project             ledger entries  memory  state directory
deployment default  156             yes     <home>/state
demo                62              yes     <home>/state/projects/demo
```

### Back up the state root

Stop the daemon first, so that the archive is consistent. Then:

```sh
arhugula daemon stop
arhugula state backup
```

The archive holds the state root and the answers file `config/init-answers.json`. It does not hold the keys under `<home>/keys` or the secrets under `<home>/secrets`, so back those up separately.

The archive goes to `<home>/backups/state-<time>.tar.gz`. `--output <file>` writes it elsewhere.
Only you can read the archive, from its first byte: the kit creates it with mode 0600. The directory `<home>/backups` has mode 0700.

### Restore a backup

```sh
arhugula daemon stop
arhugula state restore <archive>
```

Restore refuses while a daemon runs. It moves the current state root aside to `<home>/state.before-restore-<time>` and extracts the archive. Then the runtime verifies the restored root.
If any step fails, the earlier state root is put back. Delete the copy that was moved aside when you are sure of the restore.

The pause journals are in the state root, so a restore replaces them with the journals of the archive.
A gate that you put on hold after the backup is then not in the restored state root.
So answer the gates on hold before you restore: `arhugula gate list` shows them.

### Have the runtime verify the state root again

```sh
arhugula state adopt
```

`state adopt` changes nothing. The runtime verifies the state root and resolves the pause-journal directory, and the verb prints both paths. Use it when you want that proof, for example after a move.

### Move a project's leftover state out of the way

An earlier setup may have kept harness state inside a project's checkout, under `<project-path>/.harness/`. The runtime refuses such a project with `legacy-state-present` and never moves the state itself.

```sh
arhugula state archive-legacy <project-path>
```

The verb moves that state into `<home>/backups/legacy-<name>-<time>/` (*kit extension*). Nothing is deleted.

## Read an exit code

These are the kit's exit codes:

<!-- BEGIN GENERATED: exit-codes -->
| Code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | A workflow did not complete, an evaluation assertion failed, or a drift check found drift. A pass-through verb returns the runtime tool's own exit code instead. |
| 2 | The command line was wrong: unknown verb, missing argument, bad value. |
| 3 | A precondition you can fix: a failed preflight check, a missing answer, an unknown project or name, a tool that is not installed. |
| 4 | The installed runtime refused: for example a config its loader does not accept. Nothing was changed. |
| 5 | An external tool failed: uv, git, limactl, docker or a provider CLI. |
| 6 | The kit's own invariant broke, or a self-test case did not refuse. Please file an issue. |
<!-- END GENERATED: exit-codes -->

Exit code 5 has two meanings. It is the kit's code for an external tool that failed. It is also the runtime's own code for a run put on hold at a gate, which prints `status: paused`.

`run`, `resume`, `gate approve` and `gate deny` return the runtime's own exit code. Read it with this table:

| Code | After `run` or `resume` it means |
| --- | --- |
| 0 | The workflow completed. |
| 1 | The workflow failed. The `detail:` line names the cause. |
| 2 | The manifest did not load, or an option was wrong. |
| 3 | The runtime's loader refused the config. |
| 4 | The runtime could not start, or the daemon could not be reached or gave no result. |
| 5 | The workflow is paused. Continue it with `gate approve`, `gate deny` or `resume`. |
| 6 | The resume was refused before the workflow started. |
| 7 | The runtime refused the resume claim. |

So code 6 after `resume` is a refused resume, not a kit defect.

The kit can still refuse before the runtime starts, and then the kit's table applies. For example, a manifest name that is not found exits 3 with `no workflow manifest named`.

## Expect trace-export retry lines when the observability tier is off

The runtime always sends its traces to the loopback endpoint `127.0.0.1:4317`. It uses the OpenTelemetry Protocol, written `OTLP`, so these are often called the `OTLP` retry lines.
When the observability tier is off, nothing listens at that endpoint. Each run then prints a few lines like these on standard error:

```text
                    WARNING  Transient error                     exporter.py:474
                             StatusCode.UNAVAILABLE encountered
                             while exporting traces to
                             127.0.0.1:4317, retrying in 0.83s.
...
[11/14/26 19:27:25] ERROR    Failed to export traces to          exporter.py:466
                             127.0.0.1:4317, error code:
                             StatusCode.UNAVAILABLE
exit: 0
```

These lines are not a failure of the run: this run exited 0. The traces sent to the endpoint are dropped. The local span store, the ledgers and the audit entries still accumulate.
To stop the lines, start the stack with `arhugula observability up`: see [observability](observability.md).

## Stop these before an upgrade or a relocate

Some verbs replace the environment or move the home. They refuse with exit code 3 while something still runs from it.

| Before you run | Stop | With |
| --- | --- | --- |
| `arhugula upgrade` (any form) | every daemon | `arhugula daemon stop --project <project>` |
| `arhugula relocate <new-home>` | every daemon, the observability stack and the VM | `arhugula daemon stop --project <project>`, then `arhugula observability down --stop-vm` |
| `arhugula uninstall --yes` | every daemon, the observability stack and the VM | the same two commands |
| `arhugula state restore <archive>` | every daemon | `arhugula daemon stop --project <project>` |
| `arhugula state backup` | every daemon (advised, not enforced) | `arhugula daemon stop --project <project>` |

`arhugula daemon status` shows which daemons run. After a relocate the trace stack stays down; start it again with `arhugula observability up`.
The upgrade itself is described in [upgrade](upgrade.md). The flags of `relocate` are in the [command reference](reference/cli.md).

## Sources

Kit modules, under `<home>/kit`:

- `lib/arhugula_kit/verbs_run.py`: `run`, `resume`, `gate`, `status`.
- `lib/arhugula_kit/common.py`: how a manifest name is found, and the run log.
- `lib/arhugula_kit/verbs_authoring.py`: `pause`, `webhook`, `daemon`.
- `lib/arhugula_kit/daemon.py`: the daemon's socket, pidfile and log.
- `lib/arhugula_kit/verbs_observability.py`: `logs`, `trace`.
- `lib/arhugula_kit/verbs_state.py`: `state`.
- `lib/arhugula_kit/verbs_lifecycle.py`: what `upgrade`, `relocate` and `uninstall` refuse.
- `lib/arhugula_kit/errors.py`: the exit codes.
- `lib/arhugula_kit/preflight.py`: check P13, the trace endpoint.
- `examples/webhook/receiver.py` and `examples/workflows/gated-tool.toml`.

Upstream documents, under `<home>/upstream`:

- `docs/how-to-operate-runtime.md`: runs, gate answers, resume, the daemon, the runtime's exit codes.
