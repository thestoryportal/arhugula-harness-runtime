# Fix a failure by its message

This page is for the operator who has a failure message on the screen.
After reading an entry you know what the message means, how to fix it, and which command would have caught it earlier.
Search this page for a few words of your message. For how to run things when nothing is wrong, read [operate](operate.md).

## Contents

- [Read a refusal before you act](#read-a-refusal-before-you-act)
- [Init and dependencies](#init-and-dependencies)
- [Preflight checks](#preflight-checks)
- [The state root and the first run](#the-state-root-and-the-first-run)
- [Failed runs](#failed-runs)
- [Gates and resume](#gates-and-resume)
- [Configuration changes](#configuration-changes)
- [Providers](#providers)
- [The virtual machine and the trace stack](#the-virtual-machine-and-the-trace-stack)
- [Audit verification](#audit-verification)
- [The daemon](#the-daemon)
- [Upgrade and rollback](#upgrade-and-rollback)
- [Sources](#sources)

## Read a refusal before you act

Failures come from two places, and each has its own shape.

- **The kit** prints one message and, where there is one, the fix:

  ```text
  arhugula: <message>
    fix: <command>
  ```

- **The runtime** prints a line that starts with a fail class such as `RT-FAIL-BOOTSTRAP:`. When a workflow fails, it prints a `failure:` line and a `detail:` line instead.

Each entry below has four parts: the message as printed, the cause, the fix, and the command that prevents it.
An entry says *witnessed* when the failure was produced on the development machine and recorded. Every other message was read in the code that prints it.

Three commands help with every failure:

| Command | What it tells you |
| --- | --- |
| `arhugula doctor` | Runs every dependency and preflight check again. It changes nothing. |
| `arhugula doctor --self-test` | Breaks one precondition at a time and shows that each refusal fires. Its runs use their own tenant, ledger and span store, and they send no trace to the collector. It leaves the deployment as it was. |
| `arhugula logs` | Shows the newest run's log, with the runtime's own error lines. |

Here is a refusal you can produce safely. The manifest does not exist, so the kit refuses with exit code 3 and changes nothing.

<!-- witness: exit=3 -->
```sh
arhugula run no-such.toml
```

```text
arhugula: no workflow manifest named 'no-such.toml'. Looked in:
  <current-directory>/no-such.toml
  <project-path>/no-such.toml
  <project-path>/workflows/no-such.toml
  <home>/upstream/no-such.toml
  <home>/upstream/examples/no-such.toml
  fix: arhugula workflow list
```

Exit codes are explained in [operate](operate.md#read-an-exit-code).

## Init and dependencies

### A required dependency is missing

Before init can start at all, it needs `uv` and CPython 3.12:

```text
init: uv is not installed.
...
init: uv is still not on PATH. Install it, open a new terminal, and run init again.
```

Later, the dependency stage stops on any required dependency that is still missing:

```text
arhugula: init cannot continue until these are in place: D5 uv
  fix: follow the `set it up` lines above, then run init again
```

- **Cause:** a tool that the deployment needs is not installed. Init installs nothing on its own. It offers to run a setup command only when that step is one safe command and its installer is on the machine. It never installs Homebrew or a provider CLI.
- **Fix:** run the `set it up` command that init printed above the message, then run init again. Every dependency and its setup command is listed in [install](install.md#dependencies).
- **Prevent:** `<home>/kit/init --questions-json` lists every dependency and whether it is ready, without changing anything. It runs on `uv` and CPython 3.12 itself, so without those two it prints the first message above.
- **Status:** *witnessed* in `doctor --self-test`, for `uv` and for the Xcode Command Line Tools.

A missing optional dependency, such as Lima or Ollama, does not stop init. Init prints the same guide and goes on.
One required row depends on the optional ones: `At least one usable provider`. On a Mac with no provider set up, init stops at that row until one provider is installed and signed in. Ollama is the one that needs no account.

## Preflight checks

Preflight is the set of checks P1 to P18. Init runs most of them before it writes anything. It runs P9 after the install, and P11, P12 and P18 after it has written the configs. `arhugula doctor` runs them all again at any time. The full table is in [install](install.md).

A failed check prints one line and its fix. Then init stops:

```text
  FAIL  P3  CPython 3.12 is available through uv: uv has no CPython 3.12
          fix: uv python install 3.12
arhugula: preflight failed; nothing was written:
  P3 CPython 3.12 is available through uv: uv has no CPython 3.12
  fix: P3: uv python install 3.12
```

The second message says how far init got. For P9 it reads `preflight failed; the environment is installed; no configuration was generated`. For P11, P12 and P18 it reads `preflight failed; the configuration was generated but the deployment is not verified`. Under `doctor` it reads `preflight failed; doctor changes nothing`. All of them exit with code 3.

The checks below have a short answer. Checks with a longer story have their own entry further down this page.

| Check | Message | Cause | Fix | Prevent |
| --- | --- | --- | --- | --- |
| P2 | `` `uv` is not on PATH `` | `uv` is not installed. P2 reports missing Xcode Command Line Tools or a missing `git` the same way, each with its own message and setup command. | `brew install uv` | `arhugula doctor` |
| P3 | `uv has no CPython 3.12` | uv has not downloaded that Python. | `uv python install 3.12` (init offers to run it) | `arhugula doctor` |
| P4 | `<n> GiB free under <home>; the install needs 3 GiB` | The volume is nearly full. When init is about to create the VM, the message ends `the install and the new virtual machine need 12 GiB`. | Free space on that volume, or choose another home. | `arhugula doctor` |
| P8 | `<home>/state must be yours with mode 0700 (it is <mode>)` | The group or other users have access to the state root, or another user owns it. | `chmod 700 <home>/state`. When another user owns the directory, `chmod` does not help: choose another home. | `arhugula doctor` |
| P15 | `isolation tier 3 needs a virtual machine` | Tier 3 is on and no VM is chosen. | `arhugula observability vm create`, or answer `kit` at question 11 | `arhugula isolation show` |
| P16 | `<home>/keys must be mode 0700` | Other users can read the key directory. | `chmod 700 <home>/keys` | `arhugula doctor` |
| P17 | `the embedding model is not in place at <home>/models/bge-small-en-v1.5 (with its SHA256SUMS)` | Offline embedding routing is on and the model files are missing. | Follow `Offline embedding routing` in [configure](configure.md), then run init again. | `arhugula doctor` |

P2, P3, P15, P16 and P17 are *witnessed* in `doctor --self-test`. P4 is not exercised there, because a full disk cannot be simulated safely.
The self-test marks a case that it does not exercise with `--`, and its last line counts both kinds (*witnessed*):

```text
22 guard rail(s) refused as expected. 4 could not be exercised here; the lines marked -- say why.
```

## The state root and the first run

The state root is `<home>/state`. The runtime checks where it is and what it holds before it accepts it.

### `inside-checkout`: the home is inside a git checkout

```text
  FAIL  P5  the home is outside every git checkout: the home <home> is inside the git checkout at <path>; the runtime refuses a state root with a checkout above it (inside-checkout)
          fix: choose a home outside every git checkout
```

`arhugula relocate` refuses the same way:

```text
arhugula: <new-home> would be inside the git checkout at <path>; the runtime refuses a state root there (inside-checkout)
```

- **Cause:** a directory above the home is a git repository. The runtime refuses a state root that has a git checkout above it.
- **Fix:** choose a home that has no git checkout above it.
- **Prevent:** check P5 runs before init writes anything, so nothing needs undoing.
- **Status:** *witnessed* in `doctor --self-test`.

P5 also fails when the home holds a git checkout other than `kit` and `upstream`. Then the fix is an empty directory as the home.

### `marker-missing`: the state root holds files the runtime did not stamp

```text
  FAIL  P8  the state root can be created safely: <home>/state holds files but no state-root marker; the runtime will not adopt someone else's data (marker-missing)
          fix: move those files away, or choose another home
```

- **Cause:** `<home>/state` already holds files, and the runtime's marker file, `.arhugula-state-root`, is not among them. The runtime stamps a state root only when it is empty. The check cannot tell whose files they are: it fails the same way when the marker was removed from this deployment's own state root.
- **Fix:** move those files out of `<home>/state`, or choose another home. Move them; do not delete them, because they may be your own ledgers and paused runs. To bring back state that you saved with `arhugula state backup`, use `arhugula state restore <archive>` after init.
- **Prevent:** create nothing under `<home>/state` by hand. `arhugula state status` shows that the runtime verified the root.
- **Status:** *witnessed* in `doctor --self-test`.

### `legacy-state-present`: a project carries state from an earlier setup

```text
  FAIL  P10 the project has no leftover harness state: the project holds harness state from a checkout-local config, which the runtime refuses once state lives in the home (legacy-state-present): <project-path>/.harness/memory
          fix: arhugula state archive-legacy <project-path>
```

- **Cause:** an earlier setup kept a ledger or memory inside the project, under `<project-path>/.harness/`. This deployment keeps all state in the home, and the runtime refuses a project that has both.
- **Fix:** `arhugula state archive-legacy <project-path>`. It moves the leftover state into `<home>/backups/` and deletes nothing.
- **Prevent:** `arhugula project add <project-path>` makes the same check before it attaches a project.
- **Status:** *witnessed* in `doctor --self-test`.

### The first step never runs: the pause-journal root is unresolved

A fresh run exits 1, and its last error line contains one of these:

```text
the fresh run's pause-journal root resolution, placement or supersession append failed and its workflow body did not run: pause-journal root unresolved (unbound): no installation-state document declares a pause-journal root (Runtime spec v1.137 Rule B3)
```

```text
... pause-journal root unresolved (missing): the declared pause-journal root is not an existing directory (Runtime spec v1.137 Rule B3)
```

Upstream's name for this failure is `FreshRunAdmissionError`. The line names no path.

- **Cause:** every fresh run records itself in the pause-journal directory before its first step, whether or not durable pause is on. The runtime finds that directory through the installation-state document, `<home>/env/etc/arhugula/installation-state.json`. With `(unbound)` the document is missing. With `(missing)` the directory it names, `<home>/state/pause-journal`, does not exist.
- **Fix:** run `<home>/kit/init --reverify`. It writes the document again and creates the directory. Then stop and start any daemon, because a daemon reads the document only when it starts.
- **Prevent:** change the environment only through `arhugula upgrade` and `arhugula relocate`. Both write the document again. Check P18 in `arhugula doctor` proves that the root resolves. When it does not, P18 prints `the pause-journal root does not resolve (<cause>)` with the fix `arhugula init --reverify`. `arhugula init --reverify` and `<home>/kit/init --reverify` do the same.
- **Status:** not witnessed on a deployment. The self-test does not exercise P18, because breaking the document would break the real environment.

The same line can name other causes:

- `(malformed)` or `(conflicting)`: the document itself is wrong. The same fix writes it again.
- `state-root placement refused (...)`: the state root itself is refused. Run `arhugula state adopt` and read its message.
- `the pause journal's cross-process lock timed out`: another process held the workflow's journal. Wait until no other run or resume of that workflow is going, then run again. If that workflow is paused at a gate, resume it instead: a new run replaces the pause.

## Failed runs

A failed workflow exits 1 and prints two lines on standard error. The `detail:` line carries the fail class that the entries below are named after.

```text
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class="..."
```

A run that cannot start exits 4 and prints one line that starts with `RT-FAIL-BOOTSTRAP:`.

### `RT-FAIL-FALLBACK-EXHAUSTED`: every provider in the chain failed

The self-test prints the start of the line:

```text
  ok    exhausted fallback chain [the only provider in the chain serves a model that does not exist]
        exit 1: detail:    workflow execution returned status='failed' with fail_class="step-failure: RetryBreakerFallbackExhaustedError: RT-FAIL-FALLBACK-EXHAUSTED: 
```

The full message continues like this:

```text
RT-FAIL-FALLBACK-EXHAUSTED: fallback chain exhausted after candidate <provider>:<model> (chain traversal complete); last failure: <detail>
```

- **Cause:** a step went to each provider of the fallback chain in turn, and each one failed. Common reasons are a provider that is signed out, a model name that does not exist, and an Ollama server that is not running.
- **Fix:** read the text after `last failure:`. Run `arhugula provider check` to see each provider's state, and `arhugula routing show` to see the chain. Then fix the provider or change the chain: see [providers](providers.md).
- **Prevent:** `arhugula provider check` before a long run. `arhugula doctor` includes the same checks.
- **Status:** *witnessed* in `doctor --self-test`.

### `RT-FAIL-STEP-DISPATCH-TIMEOUT`: a step ran past its deadline

```text
  ok    step deadline [a step may take 10 milliseconds and a model call takes longer]
        exit 1: detail:    workflow execution returned status='failed' with fail_class='step-failure: RT-FAIL-STEP-DISPATCH-TIMEOUT: step dispatch exceeded 0.01s boun
```

- **Cause:** one step took longer than the per-step deadline, `step_dispatch_timeout_seconds`. Slow local models are the usual reason. A wait at an approval gate counts too (*upstream limit*, upstream issue 1759). The kit sets the deadline to 960 seconds, and a gate waits at most 900 seconds, so a gate fails the run only when you lowered the deadline. With the runtime's own default of 30 seconds, a gate answered after 45 seconds failed its run with `step dispatch exceeded 30.0s bound` (*witnessed*).
- **Fix:** raise the deadline. `arhugula config set step_dispatch_timeout_seconds <seconds>` sets any value, and `arhugula config unset step_dispatch_timeout_seconds` returns the kit's 960 seconds. The feature `deadlines`, when on, lowers the deadline to 120 seconds for runs with no gate. Switch it off with `arhugula feature disable deadlines` before a run that has a gate.
- **Prevent:** `arhugula feature list` shows whether `deadlines` is on. Without it, the deadline is 960 seconds. Raise it before you run a workflow on a slow model.
- **Status:** *witnessed* in `doctor --self-test`.

### `RT-FAIL-VALIDATOR-STAGE-MATERIALIZE`: a validator class cannot be loaded

```text
  ok    bad validator class [a validator binding names a class that cannot be imported]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage OD (5): ValidatorFrameworkStageMaterializeError: RT-FAIL-VALIDATOR-STAGE-MATERIALIZE: validator 'arhugula
```

The message ends in one of three ways:

| The message ends with | Cause |
| --- | --- |
| `did not resolve: ...` | The module or the class cannot be imported. |
| `raised <error> during construction (params values are not echoed)` | The class was found, and its constructor failed with the bound parameters. |
| `does not satisfy the Validator Protocol (an async validate(step, step_result, *, step_context))` | The class has no `async` method `validate` with that signature. |

- **Cause:** a validator bound to a step cannot be built when the runtime starts. So no step runs.
- **Fix:** correct the class or its parameters, or remove the binding with `arhugula validator unbind <step>`. `arhugula validator list` shows every binding.
- **Prevent:** `arhugula validator bind` imports and constructs the class before it stores the binding. `arhugula validator test` does the same for every binding, without calling a provider. See [prompts, skills and validators](prompts-skills-validators.md).
- **Status:** *witnessed* in `doctor --self-test`.

### `CP-FAIL-VALIDATOR-PERMANENT`: a validator rejected a step's result

This line comes from a run log:

```text
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class="CP-FAIL-VALIDATOR-PERMANENT: validator returned PERMANENT_FAIL at step_id='ask-local-model'"
```

- **Cause:** the validator bound to that step judged the result a permanent failure. The validator worked as written; the run stops by design.
- **Fix:** run again with `--json` to read the step's reply. Then change the prompt, the model or the validator's parameters.
- **Prevent:** nothing prevents a validator from failing a result; that is its job. `arhugula validator list` shows which steps have one.
- **Status:** pasted from a run log of the development deployment. It is not in a named evidence file.

### `RT-FAIL-PROMPT-SELECTION-UNAUTHORED`: a selected prompt version does not exist

```text
  ok    unauthored prompt version [the prompt selection names a version nobody authored]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage PREAMBLE (0): PromptSelectionUnauthoredError: RT-FAIL-PROMPT-SELECTION-UNAUTHORED: prompt-selection bindi
```

The full message continues like this:

```text
RT-FAIL-PROMPT-SELECTION-UNAUTHORED: prompt-selection binding names version_sha='<sha>' which is not an authored member of the PromptManifest.versions store; fail-loud (a version must be authored in the store before it can be selected)
```

- **Cause:** the configuration selects a prompt version by its hash, and no authored version has that hash.
- **Fix:** `arhugula prompt list` shows the authored versions. Author the missing one with `arhugula prompt author <label> --file <file>`, or select an existing one with `arhugula prompt select <workload> <version>`.
- **Prevent:** select versions with `arhugula prompt select`. It looks the version up among the authored ones before it stores the selection.
- **Status:** *witnessed* in `doctor --self-test`.

### `CancelledError: Cancelled via cancel scope`: stdio and HTTP MCP clients together

The run serves its tool calls. Then it prints a Python traceback where the `status:` line belongs, and it exits 1. The traceback ends with:

```text
asyncio.exceptions.CancelledError: Cancelled via cancel scope 10f0f7410 by <Task pending name='Task-1' coro=<run() running at <home>/env/lib/python3.12/site-packages/harness_runtime/api.py:859> cb=[_run_until_complete_cb() at .../lib/python3.12/asyncio/base_events.py:181]>
```

- **Cause:** the configuration holds a stdio MCP client and an HTTP MCP client at the same time. One example is isolation tier 3's `sandbox-echo`, a stdio client, together with a client added by `arhugula mcp add <name> --url <url>`. The runtime fails while it shuts its MCP clients down when the run ends (*upstream limit*). Every run fails this way, even a workflow that uses only one of the two clients. With either client alone, the same workflow ends `status: completed`.
- **Fix:** keep one kind of client configured at a time. `arhugula mcp list` shows which clients are configured and the transport of each. `arhugula isolation disable` removes the tier-3 stdio client. `arhugula mcp remove <name>` removes one client by name.
- **Prevent:** run `arhugula mcp list` before you turn tier 3 on or add a client.
- **Status:** *witnessed* on `arhugula run`, for a workflow that uses both clients and for one that uses only the stdio client. The same error was seen on `hold` and on `resume` in an earlier session; that transcript was not kept. The upstream issue reference is in [known gaps](reference/known-gaps.md).

### Messages explained on other pages

These four messages have their explanation on the page of the feature that raises them.

| Message | Cause | Read |
| --- | --- | --- |
| `SandboxDriverUnavailableError: resolved sandbox tier 'tier-2-container' requires an execution driver`, after `RT-FAIL-BOOTSTRAP` | An MCP client resolves to a sandbox tier that has no driver on this deployment, for example a URL client declared `LOCAL_MUTATION`. The runtime refuses every run at its start, with exit code 4 (*witnessed*). Fix: `arhugula mcp remove <name>`. | [Declare how far you trust an MCP server](security-and-isolation.md#declare-how-far-you-trust-an-mcp-server) |
| `RT-FAIL-PROMPT-INJECTION-CONFLICT` | A step payload carries a system prompt while a prompt version is active. | [Write a step payload for your provider family](authoring.md#write-a-step-payload-for-your-provider-family) |
| `RT-FAIL-PROMPT-VERSION-UNAPPROVED` | The selected prompt version is not on the approved list of a deployment that requires approval. | [Approve a version](prompts-skills-validators.md#approve-a-version) |
| `RT-FAIL-CLI-DAEMON-RESULT` | The client of a daemon run got no result, for example after its wait of one hour. | [Run workflows through the daemon](operate.md#run-workflows-through-the-daemon) |

## Gates and resume

How gates, `hold` and resume work is in [operate](operate.md#answer-an-approval-gate-at-the-terminal).

### `RT-FAIL-HITL-GATE-REJECTED` with `noninteractive: no operator terminal`

```text
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class="step-failure: RT-FAIL-HITL-GATE-REJECTED: operator rejected HITL gate at placement='pre-action': 'noninteractive: no operator terminal'"
```

- **Cause:** the run reached an approval gate and had no terminal to ask in. That happens in a pipe, a scheduled job, or the shell of an agent CLI. A gate without a terminal is rejected (*upstream limit*).
- **Fix:** run the workflow in your own terminal and answer the gate there.
- **Prevent:** `arhugula policy show` tells you which tool calls a gate approves without asking. Everything else needs a person at a terminal.
- **Status:** *witnessed* on the runtime's own `harness run`, in a run recorded before the kit wrapped it. Through `arhugula run` the same line is in a run log of the development deployment, not in a named evidence file.

### `RT-FAIL-HITL-GATE-REJECTED` with `hold unavailable: no durable pause binding`

```text
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class="step-failure: RT-FAIL-HITL-GATE-REJECTED: operator rejected HITL gate at placement='pre-action': 'hold unavailable: no durable pause binding'"
```

- **Cause:** you answered `hold`, and the runtime had no durable pause to hold the run in. So it rejected the gate.
- **Fix:** turn durable pause on and set a webhook, then run the workflow again:

  ```sh
  arhugula pause enable
  arhugula webhook set <url>
  ```

- **Prevent:** `arhugula feature list` shows whether `durable-pause` is on. `arhugula pause enable` reminds you when no webhook is set.
- **Status:** pasted from a run log of the development deployment. The working `hold` is *witnessed*.

### `RT-FAIL-RESUME-HANDLE-UNKNOWN`: there is no pause to resume

```text
resume refused: kind="handle" fail_class="RT-FAIL-RESUME-HANDLE-UNKNOWN" cause="absent" retryable=false indeterminate=true
```

The command exits 6. Here that is the runtime's code for a refused resume, not the kit's code for a defect.

- **Cause:** with `cause="absent"`, no durable pause is journalled for that workflow in that project. Either it never paused, or the run ended in a rejection instead of a pause, or the pause belongs to another project than the one you named.
- **Fix:** `arhugula gate list` shows the pause journals of one project; add `--project <project>` for another. If the workflow is in no project's list, start it again with `arhugula run`. If it is listed, or `cause` is `empty-journal`, `read-error`, `corrupt-latest` or `workflow-mismatch`, a journal exists. Then do not start the workflow again, because a new run replaces the pause. Check the manifest and the project you gave to `resume` first.
- **Prevent:** before you answer `hold`, check that durable pause and a webhook are set. After a run prints `status: paused`, do not run the same workflow again: a new run makes the pause impossible to resume.
- **Status:** pasted from a run log of the development deployment. It is not in a named evidence file.

A resume can be refused for other reasons. The `kind` in the same line names each one, for example `pause-record-superseded` or `protocol-not-bound`.

## Configuration changes

### `RT-FAIL-CLI-CONFIG-LOAD`: the runtime's loader refuses a config

A verb that changes configuration prints:

```text
arhugula: the runtime refuses the new config for <project> (RT-FAIL-CLI-CONFIG-LOAD): <the loader's message>
Nothing was changed.
```

Check P11 prints the same refusal for a file that is already in place:

```text
  FAIL  P11 the generated configs load in the runtime: the runtime refuses <home>/config/harness.toml (RT-FAIL-CLI-CONFIG-LOAD): <the loader's message>
```

- **Cause, for a verb:** the value you gave produces a config that the runtime's own loader does not accept. The verb exits 4. The answers file and every generated config stay as they were.
- **Cause, for P11:** a generated `.toml` file under `<home>/config` was edited by hand.
- **Fix, for a verb:** read the loader's message; it names the field. Run the verb again with a valid value. `arhugula config keys` lists the keys.
- **Fix, for P11:** run `<home>/kit/init --reverify`. It generates every config again from the answers file. If the same refusal comes back, no hand edit caused it: the kit generated a config that the runtime refuses. That is a kit defect; please report it with the message.
- **Prevent:** change configuration only through verbs. Each verb has the loader accept the result before it writes anything.
- **Status:** P11 is *witnessed* in `doctor --self-test`.

### `another arhugula command is changing this deployment's configuration`

```text
arhugula: another `arhugula` command is changing this deployment's configuration
  fix: wait for it to finish, then run this command again
```

- **Cause:** two commands tried to change the configuration at the same moment. The kit lets one through and refuses the other with exit code 3, so the two changes cannot mix.
- **Fix:** wait for the first command to finish, then run yours again.
- **Prevent:** run configuration verbs one at a time. This matters most when an agent CLI and you work on the same deployment.
- **Status:** read in the code; not witnessed.

## Providers

`arhugula provider check` prints each enabled provider's state and, where there is one, the fix. Setup for every provider is in [providers](providers.md).

### A provider CLI is signed out

```text
  FAIL  P6  each selected CLI provider is installed, signed in and offers its models: Claude Code CLI: not-signed-in (<version>; `claude auth status` reports not signed in)
          fix: run `claude` once and sign in
```

- **Cause:** the default or the fallback provider's CLI is missing or signed out. For any other selected provider the same finding is a warning.
- **Fix:** sign in with the provider's own command. For Codex it is `codex login`.
- **Prevent:** `arhugula provider check`.
- **Status:** the failed check is *witnessed* in `doctor --self-test`, with a simulated sign-out. The text in parentheses was read in the code; the self-test prints `signed out (simulated)` there.

### Another provider served a run that names a provider

A run with `--provider <name>` ends in `status: completed`, and it prints one more line after `ledger:`.
The line goes to standard error, so `--json` output stays clean (*witnessed*):

```text
served by claude_code/sonnet, not by ollama/no-such-model:1b: ollama failed (TypeError: AsyncClient.chat() got an unexpected keyword argument 'max_tokens')
```

- **Cause:** the provider you named failed, and the fallback served the step. Read the text after `failed (` to see why.
- **Fix:** repair the provider that failed, then run again. `arhugula provider check` shows each provider's sign-in and models.
- **Prevent:** read the `served by` line of every run that names a provider with `--provider`. A run with no such line was served by the provider you named.
- **Older pin:** a deployment installed before pin `2e1ba1f7` refuses Codex's start-up notice "Code Mode is unavailable because code-mode host is disabled" as an unrecognised item. The fallback then serves every Codex run. Run `arhugula upgrade`.
- **Status:** *witnessed* in a run on the development deployment.

### A stored model is no longer offered

`arhugula provider check` and `doctor` print the models you made available, and the models the tool no longer offers:

```text
codex (enabled): ready
    codex-cli 0.169.0; Logged in using ChatGPT
    models: gpt-6.1-sol@low, gpt-5 (default gpt-6.1-sol@low)
    not offered: Codex CLI: this sign-in does not offer the model `gpt-5`. It offers: gpt-6.1-sol, gpt-6-astra, gpt-6.1-terra, gpt-6-sol, gpt-6-luna, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
    fix: arhugula provider enable codex --model gpt-6.1-sol@low
arhugula: 2 model(s) named here are not offered by the provider's own tool
  fix: follow the `fix:` lines above, or `arhugula routing chain set <provider>`
```

- **Cause:** model names change with the release of a tool and with your account, and a name you stored earlier is gone. The kit never replaces such a model silently. Check P6 of `doctor` warns for it, and fails when the default or fallback provider's default model is gone.
- **Fix:** run the `fix:` line. It makes the models you name available, and the first is the default. `arhugula provider models <name>` lists what the sign-in offers.
- **Prevent:** `arhugula provider check` after a tool updates.
- **Status:** *witnessed* on the development deployment, with a hand-edited answers file.

### Codex is signed in with an API key (a paid route)

`arhugula provider check` reports the provider as `paid-route`, with:

```text
<version>; API key configured: every call is billed
```

- **Cause:** the Codex CLI holds an API key. Every call is then billed per call, not covered by your ChatGPT subscription. The provider still works.
- **Fix:** run `codex logout`, then `codex login`, and sign in with your ChatGPT account.
- **Prevent:** `arhugula provider check` after any change to the Codex sign-in.
- **Status:** read in the code; not witnessed.

### An Ollama model is not pulled

Preflight prints:

```text
  FAIL  P7  Ollama answers and has the model: Ollama answers at <host> but the model <model> is not pulled
          fix: ollama pull <model>
```

`arhugula provider check` prints `reachable at <host>; model <model> is not pulled`.

- **Cause:** the Ollama server runs, and the configured model is not on the machine. A run that depends on it fails with `RT-FAIL-FALLBACK-EXHAUSTED`.
- **Fix:** `ollama pull <model>`. Init offers to run it.
- **Prevent:** `arhugula provider check`. P7 fails only when the default or the fallback provider is Ollama; otherwise it warns.
- **Status:** the failed run is *witnessed* in `doctor --self-test`, with a model that does not exist.

### Ollama does not answer

```text
  FAIL  P7  Ollama answers and has the model: no answer from Ollama at <host>
          fix: ollama serve
```

`arhugula provider check` prints `no answer from <host>` and the fix ``start it with `ollama serve` ``.

- **Cause:** no Ollama server listens at the configured address. The default is `http://127.0.0.1:11434`.
- **Fix:** start the server with `ollama serve`.
- **Prevent:** `arhugula provider check`.
- **Status:** *witnessed* in `doctor --self-test`.

## The virtual machine and the trace stack

The trace stack runs inside a Lima virtual machine (VM). `arhugula observability status` shows the VM, the containers and the ports. Background is in [observability](observability.md).

### The VM is stopped

```text
arhugula: the Lima instance <instance> is stopped
  fix: arhugula observability up
```

- **Cause:** a verb needed the Docker engine inside the VM, for example `arhugula logs --collected`, and the VM is not running.
- **Fix:** `arhugula observability up`. It starts the VM and the stack.
- **Prevent:** `arhugula observability status` shows the VM's state. While the VM is stopped, runs still work; they print the trace-export retry lines described in [operate](operate.md#expect-trace-export-retry-lines-when-the-observability-tier-is-off).
- **Status:** read in the code; not witnessed.

### A port of the stack is already in use

`arhugula observability up` prints:

```text
arhugula: loopback port(s) already in use by something else: Grafana 3000
  fix: find the owner with `lsof -nP -iTCP -sTCP:LISTEN` and stop it
```

Check P14 prints:

```text
  FAIL  P14 the virtual machine and its Docker engine: loopback port(s) [3000] are in use though the virtual machine is not running, so something else holds them
          fix: find the owner with `lsof -nP -iTCP -sTCP:LISTEN` and stop it
```

- **Cause:** another program listens on one of the stack's loopback ports: 3000 (Grafana), 3200 (Tempo), 4317 (`OTLP gRPC`) or 4318 (`OTLP HTTP`).
- **Fix:** find the program with `lsof -nP -iTCP -sTCP:LISTEN` and stop it. Then run `arhugula observability up` again.
- **Prevent:** `arhugula doctor` runs P14.
- **Status:** read in the code; not witnessed.

### A Lima instance was built for another processor type

At question 11, init does not offer such an instance and says why:

```text
Not offered: the Lima instance <instance> holds a x86_64 guest. This machine is aarch64, so Lima could only run it by emulation, which is many times slower.
```

A verb that is pointed at such an instance refuses:

```text
arhugula: the Lima instance <instance> holds a x86_64 guest and this machine is aarch64. Lima can only run it by emulating the other CPU, which needs an extra package and is many times slower, so the kit does not use it
  fix: use the kit's own VM, which is built for this machine: `arhugula observability vm create`. To run the other instance anyway, install Lima's extra guest agents (`brew install lima-additional-guestagents`) and start it yourself
```

- **Cause:** the instance holds a guest for a processor type other than the Mac's own. Lima could run it only by emulation.
- **Fix:** `arhugula observability vm create` creates the kit's own VM, built for the machine's processor.
- **Prevent:** answer `kit` at question 11.
- **Status:** read in the code; not witnessed.

### The home path is too long for the VM's sockets

Check P14 prints:

```text
  FAIL  P14 the virtual machine and its Docker engine: the home's path is <n> character(s) too long for the virtual machine: macOS limits a socket path to 104 bytes and Lima keeps its sockets under <home>/lima/arhugula
          fix: choose a home with a shorter path
```

`arhugula observability vm create` and `arhugula relocate` refuse for the same reason, each in its own words:

```text
arhugula: <new-home> is too long a path for the virtual machine: macOS limits a socket path to 104 bytes and Lima keeps its sockets under the home
  fix: choose a new home with a shorter path
```

- **Cause:** Lima keeps Unix sockets under `<home>/lima`, and macOS limits a socket path to 104 bytes. A long home path leaves too little room.
- **Fix:** choose a home with a shorter path. For a deployment that already exists, move it with `arhugula relocate <new-home>`.
- **Prevent:** P14 runs before init creates the VM, so nothing needs undoing.
- **Status:** read in the code; not witnessed.

### Tempo metric panels are empty right after a restart

There is no message. The Grafana panels that plot metrics show no data.

- **Cause:** after Tempo restarts, its metrics generator has nothing to plot until a new span arrives. This is a limit of Tempo, not of the harness.
- **Fix:** run any workflow, for example `arhugula run ollama-first.toml --provider ollama`. The panels fill from that run on.
- **Prevent:** nothing prevents it. Expect it whenever Tempo has restarted.
- **Status:** a limit of Tempo, listed in [known gaps](reference/known-gaps.md).

## Audit verification

### A ledger that began unsigned: `UNVERIFIED`, no cutover record, `signature-invalid`

`arhugula audit verify` runs the full check, signatures included, on every ledger that has a cutover record and a key map. The flag `--signatures` only requires that check.
So `arhugula audit verify --signatures` refuses a ledger that began unsigned:

```text
arhugula: <project> has no cutover record (<state-directory>/state-ledger/audit-cutover-record.json). The runtime writes it at the first run of a ledger while signing is on; a ledger that began unsigned has none and cannot be signature-verified
  fix: check the hash chain with `arhugula audit verify`; turn signing on before a project's first run to have it verify in full
```

`<state-directory>` is the project's row in the `state directory` column of `arhugula state status`.

`arhugula audit status` shows which ledgers this applies to (*witnessed*). While signing is off, the last column reads `hash chain only: signing is off` instead.

```text
project             audit entries  verifies
deployment default  37             hash chain only: it began unsigned
demo                13             hash chain only: it began unsigned
```

After a verification, the kit explains the inspector's exit code in one line:

```text
harness-inspect exit 3: UNVERIFIED: the inspector lacked an input it needs; its message above names it
```

```text
harness-inspect exit 4: verification ran and FAILED; the message above names the entry
```

- **Cause:** a ledger that held entries before signing was turned on keeps those unsigned entries for ever. An unsigned entry never verifies (*upstream limit*); the runtime's name for that failure is `signature-invalid`. Such a ledger also has no cutover record, which is the signed note of where signing began.
  Writing a cutover record over such a ledger afterwards does not repair it. Upstream's `harness migrate-audit-sidecar --author` writes one, and verification then fails with `signature-invalid` on the unsigned entries (*witnessed*).
- **Fix:** verify the hash chain with `arhugula audit verify`, without `--signatures`. That check still proves that no entry was changed or removed. Do not author a cutover record for such a ledger: `audit verify` then always runs the full check, and that check fails. A project that you attach after signing is on verifies in full.
- **Prevent:** turn signing on at init (feature `s`), or run `arhugula audit keygen` and `arhugula audit enable` before a project's first run. See [security and isolation](security-and-isolation.md).
- **Status:** the status table is *witnessed*, and so is the `signature-invalid` failure after `--author`. The refusal and the two exit-code lines were read in the code.

If the message is `there is no key map at <home>/keys/signing-key-map.json`, run `arhugula audit keygen`.

## The daemon

### A stale daemon: the pidfile is there and the process is gone

`arhugula run <manifest> --daemon` exits 4 with:

```text
RT-FAIL-CLI-DAEMON-CONNECTION: socket path <home>/run/<project>.sock does not exist (daemon not running?)
```

- **Cause:** no daemon serves that project. Either none was started, or the daemon's process ended and left its pidfile behind.
- **Fix:** `arhugula daemon start`. It removes a leftover socket file and starts a new daemon. If the daemon exits at once, the message shows the last lines of `<home>/logs/daemon-<project>.log`.
- **Prevent:** `arhugula daemon status` before you send a run. It counts a daemon as running only when its process is alive and its socket exists.
- **Status:** read in the code; not witnessed.

### A running daemon blocks another verb

```text
arhugula: a harness daemon is running (pid <pid>); stop it before you upgrade
  fix: arhugula daemon stop
```

- **Cause:** `upgrade`, `relocate`, `uninstall` and `state restore` replace or move what the daemon runs from. They refuse with exit code 3 while one runs.
- **Fix:** `arhugula daemon stop --project <project>` for each project that `arhugula daemon status` shows as running.
- **Prevent:** follow the table in [operate](operate.md#stop-these-before-an-upgrade-or-a-relocate).
- **Status:** read in the code; not witnessed.

`arhugula daemon start` on a project whose daemon already runs prints `the daemon for <project> is already running (pid <pid>)`. Nothing is wrong: use the running one.

## Upgrade and rollback

The upgrade, its steps and the install's exit codes are in [upgrade](upgrade.md).

### `there is no complete earlier environment`: nothing to roll back to

```text
arhugula: there is no complete earlier environment at <home>/env.rollback to return to
  fix: arhugula upgrade --pin <sha> installs any commit again
```

- **Cause:** `arhugula upgrade --rollback` found no earlier environment that holds its commit record, `<home>/env.rollback/.arhugula-pin`. No upgrade or rebuild has finished on this deployment yet, or the copy was removed. The rollback exits 3 and changes nothing. A failed or interrupted install is not the cause: it keeps the rollback copy.
- **Fix:** name the commit that you want: `arhugula upgrade --pin <sha>`.
- **Prevent:** `cat <home>/env.rollback/.arhugula-pin` prints the commit that a rollback returns to. When that file is missing, there is nothing to return to.
- **Status:** read in the code; not witnessed.

### `the environment does not hold the harness wheels just built`

```text
install: the environment does not hold the harness wheels just built in <home>/dist
install: the earlier environment is back in place at <home>/env
```

- **Cause:** the install compared the hash of every installed harness file with the wheel it had just built, and a file differed. The install ends with exit code 78. The lines above the message name up to five files that differ.
- **Fix:** the earlier environment is back in place, so runs work as before. Read `<home>/logs/install-env.log`, then run `arhugula upgrade --reinstall`. If it stops again, report the file names that the install printed.
- **Prevent:** after an upgrade by an earlier kit version, run `arhugula upgrade --reinstall` once: that version could install the earlier commit's files. [Rebuild at the same pin](upgrade.md#rebuild-at-the-same-pin) explains why.
- **Status:** read in the code (`bin/install.sh`); the mismatch itself was not provoked. The cause that this check closes, an upgrade that left the old code in the environment, was *witnessed*.

## Sources

Kit modules, under `<home>/kit`:

- `init` and `lib/arhugula_kit/dependencies.py`: the dependency messages.
- `lib/arhugula_kit/preflight.py`: every preflight message and fix.
- `lib/arhugula_kit/selftest.py`: what `doctor --self-test` breaks and expects.
- `lib/arhugula_kit/deploy.py`: the config refusal and the configuration lock.
- `lib/arhugula_kit/providers.py`: provider states, notes and fixes.
- `lib/arhugula_kit/vm.py`, `lib/arhugula_kit/observability.py`, `lib/arhugula_kit/questions.py`: the VM and stack messages.
- `lib/arhugula_kit/verbs_authoring.py`: the audit messages.
- `lib/arhugula_kit/daemon.py`, `lib/arhugula_kit/verbs_lifecycle.py`: the daemon messages and the rollback refusal.
- `lib/arhugula_kit/common.py`: the manifest lookup.

Upstream documents and sources, under `<home>/upstream`:

- `docs/how-to-operate-runtime.md`: the pause-journal root, resume refusals, exit codes.
- `harness-runtime/src/harness_runtime/lifecycle/root_resume_admission.py`: `FreshRunAdmissionError`.
- `harness-runtime/src/harness_runtime/lifecycle/retry_breaker_fallback.py`: `RT-FAIL-FALLBACK-EXHAUSTED`.
- `harness-runtime/src/harness_runtime/bootstrap/factories/validator_framework_factory.py`: `RT-FAIL-VALIDATOR-STAGE-MATERIALIZE`.
- `harness-runtime/src/harness_runtime/lifecycle/prompt_selection.py`: `RT-FAIL-PROMPT-SELECTION-UNAUTHORED`.
- `harness-runtime/src/harness_runtime/lifecycle/operator_input.py` and `hitl_gate_composer.py`: the two gate rejections.
- `harness-runtime/src/harness_runtime/cli/app.py`: the daemon connection failure.
- `harness-runtime/src/harness_runtime/lifecycle/mcp_client_host.py`: the MCP client shutdown that raises `CancelledError`.
