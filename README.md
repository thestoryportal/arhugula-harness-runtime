# Arhugula Harness runtime kit

This page is for anyone who wants to install the Arhugula Harness on a Mac and run workflows with it.
After reading it you can install a deployment, recognize a successful first run, and find the page for your next task.
It describes the kit at the upstream commit named in the file `PIN`.

If you are an agent CLI such as Claude Code or Codex, read [AGENTS.md](AGENTS.md) first.

## Contents

- [What the harness is](#what-the-harness-is)
- [What this kit is](#what-this-kit-is)
- [What a deployment can do](#what-a-deployment-can-do)
- [What you need first](#what-you-need-first)
- [Install it and run the first workflows](#install-it-and-run-the-first-workflows)
- [Check a deployment at any time](#check-a-deployment-at-any-time)
- [What the pin is and what witnessed means](#what-the-pin-is-and-what-witnessed-means)
- [Three decisions shape the deployment](#three-decisions-shape-the-deployment)
- [Find the page for your task](#find-the-page-for-your-task)
- [Sources](#sources)

## What the harness is

The Arhugula Harness is a runtime that runs workflows of large language model (LLM) calls.
A workflow has several steps and can use several agents.
You describe a workflow in a TOML file called a manifest.
The runtime sends each step to a provider, which is a model service such as Claude Code or Ollama.
It checks the results, asks you before a risky tool call, and records what happened.

The harness is a separate upstream project, `thestoryportal/arhugula-harness`.

## What this kit is

This kit installs the harness on a Mac and operates it.
It adds everything that happens before the first run, and everything that changes the configuration afterwards.

You get two commands.
`init` asks its questions, checks the machine, installs the harness and proves it with short runs.
`arhugula` does everything after that.
The kit also brings an optional trace stack with dashboards, in its own small virtual machine (VM), and these pages.

## What a deployment can do

Three markers, always in italics, tell you how far to trust a statement:

- ***witnessed*:** it ran on the kit's development machine, and its output was kept as evidence.
- ***kit extension*:** this kit adds it. It is not part of the upstream harness.
- ***upstream limit*:** it does not exist, or does not work, at the pinned upstream commit.

[Known gaps](docs/reference/known-gaps.md) lists the upstream limits, the kit extensions, and the platform and provider limits in one place.

### Providers

- **Six providers:** Claude Code, Codex and Antigravity run through your own signed-in command-line tool. Ollama runs local models. The Anthropic API and the OpenAI API are paid, hosted services. You can also add a command of your own with `arhugula provider add` (*witnessed* with the stand-in `examples/providers/echo-provider`).
- **Keys stay out of files:** `arhugula provider key set <name>` stores an API key in the macOS keychain. No key is written to a TOML file.
- **One command checks sign-in:** `arhugula provider check` asks each enabled provider's own tool whether it is installed and signed in.
- **Subscription calls carry no price:** a call through a signed-in command-line tool writes no cost entry (*upstream limit*, by design).
- **Models come from each tool's own list:** `arhugula provider models` shows what your sign-in offers. `provider check` and `doctor` report a model that a tool no longer offers.
- **Codex serves a run at this pin:** three runs with `--provider codex` were each served by Codex, with no error (*witnessed*). When the provider you name fails, the fallback serves the step and the run prints a `served by` line.

Details: [providers](docs/providers.md).

### Routing

- **One routing rule:** the config's first fallback chain serves every step; `--provider` (and `--model`) override it for one run; a manifest's own model binding does not select the provider. A more specific setting wins over the chain: a per-step `model_binding` in a manifest, a workload override or a role binding. See [How routing picks a provider](docs/providers.md#how-routing-picks-a-provider).
- **A model and a thinking level, where you want them:** one table gives the exact command or manifest line. It covers one step or sub-agent, one role, one kind of work, the default and one run. See [Choose a model and a thinking level](docs/providers.md#choose-a-model-and-a-thinking-level). Claude Code and Codex take a level as `<model>@<level>`, for example `sonnet@high` (*kit extension*).
- **A fallback provider:** when the default provider fails, the chain's fallback provider takes the step.
- **Finer routing by verb:** `arhugula routing` sets the chain, a provider's model, a binding for a role or a workload class, and retry policies.

Details: [providers](docs/providers.md) and [configure](docs/configure.md).

### Topologies and multi-agent execution

- **Six topologies ship:** single-threaded-linear, parallelization, orchestrator-workers, evaluator-optimizer, hierarchical-delegation and decentralized-handoff. Upstream has an example of each, and `arhugula workflow list` shows them.
- **A manifest from a topology:** `arhugula workflow new <topology> --name <name>` writes a manifest that loads in the runtime (*kit extension*).
- **Isolated agent steps:** each agent step is one short provider call. It has no session and a scrubbed environment. With Claude Code and Codex it also has no tools of its own. Antigravity keeps its own tools and starts in the project's repository: see [What each call can see](docs/providers.md#what-each-call-can-see).
- **One process, no multiplexer:** the agents of a topology run concurrently inside one process. No terminal multiplexer is involved.
- **No plans from replies:** the runtime does not build a worker plan from a lead model's reply (*upstream limit*; upstream issue: see known-gaps).

Details: [workflows](docs/workflows.md).

### Approval gates

- **A gate asks you:** a gated tool call stops and asks at your terminal: `answer (approve | edit | reject | respond | hold | cancel):`.
- **Policy decides what asks:** `arhugula policy show` lists what a gate approves without asking, and `arhugula policy set` changes it.
- **Approve and hold work:** `approve` ended in `status: completed`. `hold` ended in `status: paused`, and `arhugula gate approve <manifest>` then completed the run (*witnessed*).
- **Hold needs two settings:** `arhugula pause enable` and `arhugula webhook set <url>`.
- **No terminal, no approval:** a run without a terminal rejects its gate (*upstream limit*).

Details: [operate](docs/operate.md) and [workflows](docs/workflows.md).

### Validators

- **A check per step:** `arhugula validator bind <step-id> <module:Class>` binds your validator class to a step.
- **A test without providers:** `arhugula validator test` imports and constructs every bound validator. It calls no provider.
- **A bad class is refused:** the runtime refuses to start when a binding names a class it cannot import (*witnessed* by `arhugula doctor --self-test`).
- **Two examples ship:** `MaxCharsValidator` and `AskAPersonValidator` in `examples/validators/example_validators.py`.

Details: [prompts, skills and validators](docs/prompts-skills-validators.md).

### Prompts and skills

- **Versioned prompts:** `arhugula prompt author <label> --file <file>` authors a prompt version from any text file. Other `prompt` verbs activate, select, approve and compare versions.
- **Unauthored versions are refused:** the runtime refuses a prompt selection that names a version nobody authored (*witnessed* by `arhugula doctor --self-test`).
- **Skills per project:** `arhugula skill add <dir>` copies a skill into `<project-path>/.agents/skills/`.
- **A hook activates skills:** upstream needs a Python hook object, which a TOML file cannot carry (*upstream limit*). `arhugula skill hook set` supplies it (*kit extension*).

Details: [authoring](docs/authoring.md) and [prompts, skills and validators](docs/prompts-skills-validators.md).

### Memory

- **On by default:** each project keeps its own memory under `<home>/state/projects/<project>/memory`.
- **Two access modes:** a memory packet added to each prompt, or the packet plus memory tools that the agent can call.
- **You review first:** a captured memory becomes reusable only after your decision, and each proposal is decided at most once.
- **Verbs for the lifecycle:** `arhugula memory status`, `review` and `export` are *kit extensions*. The other `memory` verbs drive upstream's operator tool.

Details: [memory](docs/memory.md).

### MCP tools

- **Tool servers by verb:** `arhugula mcp add` connects a Model Context Protocol (MCP) tool server with a trust level and a blast radius. `arhugula mcp test` lists its tools. A `stdio` server needs isolation tier 3 and the virtual machine: see [Give your own MCP client a sandbox](docs/security-and-isolation.md#give-your-own-mcp-client-a-sandbox). It also fails every run while an HTTP client is configured: see [stdio and HTTP MCP clients together](docs/troubleshooting.md#cancellederror-cancelled-via-cancel-scope-stdio-and-http-mcp-clients-together).
- **An example server:** `examples/mcp/notes_server.py` offers the tools `notes.read` and `notes.write`.
- **A daemon with a limit:** `arhugula daemon start` runs the harness as a service. Its own MCP endpoint is a Unix socket, which MCP clients such as Claude Code cannot connect to (*upstream limit*). `arhugula daemon expose` prints the working alternative.

Details: [configure](docs/configure.md) and [operate](docs/operate.md).

### Pause and resume

- **A pause that survives:** with `arhugula pause enable`, a paused run survives the end of its process.
- **Resume with a decision:** `arhugula resume <manifest> --decision approve` continues the latest pause of that workflow.
- **The list overstates:** the pause-journal list is an upper bound, not an inventory of open pauses (*upstream limit*).

Details: [operate](docs/operate.md).

### Audit signing

- **Signed audit entries:** `arhugula audit keygen` creates two local keys (*kit extension*), and `arhugula audit enable` signs every new audit entry.
- **Full verification:** a ledger that is signed from its first entry verifies in full with `arhugula audit verify --signatures` (*witnessed*).
- **Unsigned history stays unsigned:** a ledger that began unsigned keeps hash-chain verification only (*upstream limit*). Authoring a cutover record over it with upstream's `harness migrate-audit-sidecar --author` was tried. Verification then fails with `signature-invalid` on the unsigned entries (*witnessed*).
- **Sign from the start:** choose audit signing at init, and every ledger is signed from its first entry. Init then creates both keys itself.

Details: [security and isolation](docs/security-and-isolation.md).

### Observability

- **A local span store:** the runtime writes every run's spans to `<home>/state/observability/spans.sqlite`. `arhugula trace list` reads it.
- **An optional trace stack:** the OpenTelemetry Collector, Tempo and Grafana run in the kit's VM, on loopback ports only.
- **Dashboards and alerts:** seven Grafana dashboards, seven alert rules and a logs pipeline come provisioned (*kit extension*).
- **Two gaps in spans:** spans carry no finish reason, and no span exists per step (*upstream limit*).

Details: [observability](docs/observability.md).

### Evaluation

- **Checks inside every run:** validators, approval gates, retry and fallback, deadlines and prompt-version approval need no setup.
- **A holdout loop:** `arhugula eval sample`, `review`, `scaffold`, `status` and `report` take you from sampled traces to assertions that run. No model judges anything.
- **Drift against a threshold:** `arhugula eval drift set-threshold` stores a threshold in the kit, because the runtime has no setting for it (*upstream limit*).
- **No judge, no scores:** a general evaluation judge and a scored suite do not exist (*upstream limit*; upstream issue: see known-gaps).

Details: [evaluation](docs/evaluation.md).

### Isolation

- **Sandboxed tool calls:** `arhugula isolation enable tier-3` runs MCP tool calls under gVisor inside the kit's VM (*witnessed*).
- **Other tiers:** tier 1, the host process, is the default. Tiers 2 and 4 are outside this deployment.
- **Untested hardware:** the kit is witnessed on Apple silicon. Intel Macs are untested.

Details: [security and isolation](docs/security-and-isolation.md).

## What you need first

You need a Mac and a terminal. Assume nothing else is installed: init checks every item and guides you through each missing one.

- **Always:** macOS 13 or later, the Xcode Command Line Tools, git, uv, and CPython 3.12 managed by uv.
- **At least one provider:** Ollama with a pulled model, or a signed-in Claude Code, Codex or Antigravity command-line tool.
- **For the trace stack and tier 3:** Lima.
- **Optional:** Homebrew, the suggested way to install the others.
- **Disk space:** about 3 GiB, or 12 GiB with the VM.

The [dependencies section of the install page](docs/install.md#dependencies) gives the purpose, the check and the setup command for each one.

Init installs little by itself. It offers to run a setup command only when that is one safe command and its installer is already on the machine.
Init never installs Homebrew or a provider's command-line tool, and it never runs the setup command of the VM row. You run those commands yourself.

On a Mac with nothing installed, init therefore stops at the dependency `At least one usable provider` until you set one provider up.
Ollama is the provider that needs no account.

## Install it and run the first workflows

The deployment lives in one directory, the *home*. These pages write it as `<home>`.
The commands below use the default home, `~/arhugula`. Any plain directory outside a git checkout works: put your own path in its place.

1. Clone the kit into the home:

   ```sh
   git clone https://github.com/thestoryportal/arhugula-harness-runtime.git ~/arhugula/kit
   ```

   On a Mac without `git`, this first use of `git` opens Apple's dialog that installs the Command Line Tools. Finish the installation there, then run the clone again.

2. Run init in a terminal:

   ```sh
   ~/arhugula/kit/init
   ```

3. Answer what init asks. Press Enter to accept the default that each prompt shows.

4. When init stops because a dependency is missing, set that dependency up with the command that init shows. Then run init again.

5. Make the command available with the two `export PATH=...` lines that init prints last: one for this terminal, one for new terminals.

If you cloned the kit somewhere else, init clones it into `<home>/kit` and continues from there.

### What the first install downloads

The first install takes longer than a later one, because it downloads these parts:

- **The harness source:** a clone of the upstream repository.
- **The Python dependencies:** the packages of the harness.
- **The Ollama model:** about 2 GB, when you use Ollama with the model that init proposes.
- **The VM:** 5 to 10 minutes the first time, when you answer `kit` at question 11. `kit` is the default when Lima is installed. Init creates that VM only when 12 GiB are free.

With every download in the cache, the install itself takes about a minute.

### What init asks, in order

Init first checks the dependencies and shows the setup command for each missing one. Where init may run that command, it asks first and runs it only after you type yes. Then it asks up to 14 questions:

1. The deployment home directory.
2. Which providers to make available.
3. The default provider for workflows.
4. The fallback provider for when the default fails.
5. The Ollama model, when you selected Ollama.
6. The Ollama host address, only when Ollama does not answer at its default address.
7. A project repository to attach now, or none.
8. The workload classes to bind.
9. The features to enable now: memory, durable pause, data flow between steps, audit signing, offline embedding routing.
10. The memory access mode, when memory is on.
11. The observability tier: the kit's own VM, a Lima instance you already have, or none.
12. Isolation tier 3, when you chose a VM.
13. Backup or restore locations that can reach the state root.
14. Whether to run the smoke workflows now.

The [install page](docs/install.md) shows every prompt with its default and its reason.

### What success looks like

Init ends with short test runs, the smoke runs. This output is from a real init (*witnessed*):

```text
Smoke runs:
  primary route (claude_code): exit 0, status: completed
  Ollama route: exit 0, status: completed
  project demo: exit 0, status: completed
```

Each line that ends in `status: completed` is one workflow that ran from start to finish:

- **The primary route:** a run on your default provider. It always runs.
- **The Ollama route:** a run on Ollama. It appears when you selected Ollama and another provider is the default.
- **The project line:** a run in an attached project. It appears when a project is attached. Here the project is named `demo`.

If a smoke run does not complete, init stops with exit code 1 and names `arhugula doctor` as the next step.

After the smoke runs, init prints where the deployment is and what to do next:

```text
The deployment is ready.
  home:    <home>
  command: <home>/bin/arhugula
  use it in this terminal:      export PATH="<home>/bin:$PATH"
  keep it for new terminals:    echo 'export PATH="<home>/bin:$PATH"' >> ~/.zshrc
  run a workflow:               arhugula run ollama-first.toml --provider ollama
  attach your own repository:   arhugula project add <path-to-a-repository>
```

Read the last four lines like this:

- **Use it in this terminal:** paste the first `export` line, and `arhugula` works in the terminal that you have open.
- **Keep it for new terminals:** paste the `echo` line once. It adds the same line to `~/.zshrc`, the file that every new terminal reads.
- **Run a workflow:** a first run that works on your deployment. With Ollama selected it is the line shown here. Without Ollama it is `arhugula run minimal.toml`, on your default provider.
- **Attach your own repository:** `arhugula project add` makes a repository of yours a project of this deployment.

`arhugula --version` prints the kit version and the upstream pin.

## Check a deployment at any time

These two commands change nothing. `doctor` repeats the dependency list and the preflight checks. `status` shows the newest ledger entries.

<!-- witness -->
```sh
arhugula doctor
arhugula status
```

The [install page](docs/install.md#check-a-deployment-with-doctor) shows the output of `doctor`.

## What the pin is and what witnessed means

**The pin** is one upstream commit, and the file `PIN` holds its 40-character id.
Init installs the harness at exactly that commit.
It builds the seven harness packages, exports two lock files with hashes, and runs upstream's own packaging gate on the build.
Then it installs the result into a private environment under `<home>/env`.

Every statement on these pages describes that commit.
`arhugula upgrade --pin <sha>` moves the deployment to another commit: see [upgrade](docs/upgrade.md).

***Witnessed*** means that the behaviour ran on the kit's development machine, an Apple silicon Mac, at the pin.
The output of that run was kept as evidence, and the excerpts on these pages are pasted from it.
A statement without the marker comes from the code or from upstream's documents, and has not been run end to end.

You can repeat part of the evidence on your own machine:

- **Refusals:** `arhugula doctor --self-test` breaks one precondition at a time and expects the matching refusal.
- **Documented commands:** `<home>/kit/bin/witness.sh <home> --list` lists every command block that these pages mark as runnable. Without `--list`, the script runs them.

## Three decisions shape the deployment

### The home is one self-contained directory

Everything that the kit installs, generates and stores lives under `<home>`: the kit, the harness source, its Python environment, the configuration, the state and the logs.
The install writes nothing outside the home, except the download caches that uv and Lima keep in their own directories.
The home is a plain directory outside every git checkout, and `arhugula relocate <new-home>` moves it whole.
An attached project receives only working files, under `.harness/` and `.agents/skills/`.

Three things stay outside the home because they belong to the machine: the dependencies, the provider sign-ins, and API keys in the macOS keychain.

### The only Docker engine is inside the kit's Lima VM

The trace stack and the tier 3 sandbox need a Docker engine.
The kit creates its own Lima VM under `<home>/lima`, built for the machine's processor, with Docker Engine, Docker Compose and gVisor inside.
**Docker Desktop is not required and is never used.**
The VM sees only `<home>/observability` and `<home>/logs`, and both are read-only for it.
If you answer `n` at the observability question, init creates no VM, and runs still work.

### Codex is offered, and never proposed as the default

Init offers Codex with your ChatGPT subscription sign-in, `codex login`, as the way to use it.
With an API key instead, every Codex call is a paid call.
Init never proposes Codex as the default provider when you selected another provider.
The reason is upstream's own marking: the Codex profile is HELD, because the CLI's filesystem read exposure is an untested boundary.

## Find the page for your task

| Page | What it covers |
| --- | --- |
| [Concepts](docs/concepts.md) | The mental model: the home, projects, workflows, routing, state, gates, memory and traces. |
| [Install](docs/install.md) | Dependencies, every init question and preflight check, re-run modes, relocate and uninstall. |
| [Operate](docs/operate.md) | Day-to-day work: runs, status, gates, resume, the daemon, logs, state backups and exit codes. |
| [Troubleshooting](docs/troubleshooting.md) | Failure messages, with the cause and the fix for each. |
| [Projects](docs/projects.md) | Attaching a repository, and what the harness writes into it. |
| [Providers](docs/providers.md) | Each provider: sign-in, enabling, and routing between providers. |
| [Workflows](docs/workflows.md) | The manifest, the six topologies, gates in a workflow, and how agents execute. |
| [Authoring](docs/authoring.md) | What an agent inside a workflow sees, and how to write for it. |
| [Prompts, skills and validators](docs/prompts-skills-validators.md) | The verbs that manage prompt versions, skills and validator bindings. |
| [Configure](docs/configure.md) | The generated config, every named feature, and the verbs that set each key. |
| [Memory](docs/memory.md) | What memory stores, how you review it, and the memory verbs. |
| [Observability](docs/observability.md) | The local span store, the VM, the trace stack, dashboards, alerts and logs. |
| [Evaluation](docs/evaluation.md) | Checks inside a run, the holdout loop and drift checks. |
| [Security and isolation](docs/security-and-isolation.md) | Secrets, audit signing, gate policy, MCP trust and the isolation tiers. |
| [Agents](docs/agents.md) | How an agent CLI installs and operates the deployment for you. |
| [Upgrade](docs/upgrade.md) | Moving to another pin, and rolling back. |
| [Known gaps](docs/reference/known-gaps.md) | Upstream limits, kit extensions and platform limits. |
| [Command reference](docs/reference/cli.md) | Every verb, its arguments and one example. The program generates this page. |
| [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) | Instructions that an agent CLI reads before it acts in the kit. |
| [Changelog](CHANGELOG.md) | Kit versions and the upstream pin of each. |

## Sources

This page was checked against these kit files:

- **Init and install:** `init`, `bin/install.sh`, `lib/arhugula_kit/initflow.py`, `lib/arhugula_kit/questions.py`, `lib/arhugula_kit/dependencies.py`.
- **Layout and lifecycle:** `lib/arhugula_kit/layout.py`, `lib/arhugula_kit/verbs_lifecycle.py`, `lib/arhugula_kit/witness.py`.
- **Features:** `lib/arhugula_kit/providers.py`, `lib/arhugula_kit/verbs_run.py`, `fragments/`, `examples/`, `docs/reference/cli.md`.

It was checked against these upstream documents, with paths relative to the home:

- **Runtime flow:** `upstream/docs/architecture.md`.
- **Operation:** `upstream/docs/how-to-operate-runtime.md`.
- **Memory:** `upstream/docs/memory-layer-readme.md`.
- **The trace stack:** `upstream/deploy/self-hosted-local/README.md`.
