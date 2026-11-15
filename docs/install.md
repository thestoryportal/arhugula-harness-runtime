# Install a deployment

This page is for the operator who installs the Arhugula Harness on a Mac.
After reading it you can set up every dependency, answer each question that init asks, and read its checks.
You can also re-run init, check a deployment, move it, and remove it.
The page describes the kit at the upstream commit named in the file `PIN`.

For the shortest path, read the quick start on the [kit's front page](../README.md). For the ideas behind a deployment, read [concepts](concepts.md).

These pages write the deployment's directory, the *home*, as `<home>`. The default home is `~/arhugula`.

## Contents

- [Dependencies](#dependencies)
- [Start init](#start-init)
- [What init does, in order](#what-init-does-in-order)
- [Read the dependency stage](#read-the-dependency-stage)
- [Answer the questions](#answer-the-questions)
- [Read the preflight checks](#read-the-preflight-checks)
- [What init generates, and where](#what-init-generates-and-where)
- [Run init again](#run-init-again)
- [Check a deployment with doctor](#check-a-deployment-with-doctor)
- [Prove the refusals with the self-test](#prove-the-refusals-with-the-self-test)
- [Move the home with relocate](#move-the-home-with-relocate)
- [Remove the deployment with uninstall](#remove-the-deployment-with-uninstall)
- [Let an agent drive init](#let-an-agent-drive-init)
- [Sources](#sources)

## Dependencies

This list names everything that a deployment needs on the machine: what each item is for, how to check it, and how to set it up.
Init checks every item for you.
For a missing item, init shows the setup command.
You can set everything up by hand, before init or instead of its offers, with the commands shown here.

Init offers to run a setup command only in one case: the setup is one safe command, and its installer is already on the machine.
For example, init offers `brew install ollama` only when Homebrew is installed. It runs the command only after you agree.
Init never installs Homebrew or a provider's command-line tool, and it never runs the setup command of the VM entry. You run those commands yourself.

An item marked *required* stops init while it is missing. An item marked *optional* is needed only for the choice that its entry names.
The disk space entry is neither: it is marked *checked again later* and never stops init. Preflight check P4 decides, for the home that you choose.

Where an entry shows two commands, the word between them says how to read them. `Or:` means two ways to do the same thing, so run one. `Then:` means two steps, so run both in order.

<!-- BEGIN GENERATED: dependencies -->
### D1: macOS 13 or later

The kit is written for macOS, on Apple silicon or Intel.

- Needed for: every deployment (required).
- Check: `sw_vers -productVersion; uname -m`

### D2: Xcode Command Line Tools

Apple's developer tools. They provide git and the libraries other tools build on.

- Needed for: every deployment (required).
- Check: `xcode-select -p`
- Set it up:

  ```sh
  xcode-select --install
  ```

  A system window opens. Finish the installation there, then run init again.

### D3: git

Fetches the harness source at the pinned commit.

- Needed for: every deployment (required).
- Check: `git --version`
- Set it up:

  ```sh
  xcode-select --install
  ```

  Or:

  ```sh
  brew install git
  ```

### D4: Homebrew

A package installer. It is only the suggested way to install the tools below; each one also has its own installer.

- Needed for: the `brew install` commands in this list (optional).
- Check: `brew --version`
- Set it up:

  ```sh
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

  The installer asks for your password and prints two lines to add to your shell profile.

### D5: uv

Builds the harness and creates its private Python environment.

- Needed for: every deployment (required).
- Check: `uv --version`
- Set it up:

  ```sh
  brew install uv
  ```

  Or:

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### D6: CPython 3.12, managed by uv

The Python the harness runs on. uv keeps it apart from the system Python.

- Needed for: every deployment (required).
- Check: `uv python find 3.12`
- Set it up:

  ```sh
  uv python install 3.12
  ```

### D7: 3 GiB of free disk space

Init wants 3 GiB free before it installs, and 12 GiB when it also creates the virtual machine. The install itself takes about half a gigabyte; the virtual machine with its container images takes about 5.

- Needed for: every deployment; preflight check P4 checks the home you choose (checked again later).
- Check: `df -h ~`

### D8: Ollama

Runs open-weight models on this machine. It needs no account and no network once a model is pulled.

- Needed for: the provider `ollama` (optional).
- Check: `curl -s http://127.0.0.1:11434/api/tags`
- Set it up:

  ```sh
  brew install ollama
  ```

  Then:

  ```sh
  brew services start ollama
  ```

  Without Homebrew, install the app from https://ollama.com/download and open it; `ollama serve` starts the server in a terminal.

### D9: The Ollama model llama3.2:3b

The default local model (about 2 GB). Question 5 lets you choose another.

- Needed for: the provider `ollama` with its default model (optional).
- Check: `ollama list`
- Set it up:

  ```sh
  ollama pull llama3.2:3b
  ```

### D10: Claude Code CLI

Runs workflow steps through your own signed-in `claude`.

- Needed for: the provider `claude_code` (optional).
- Check: `claude --version`
- Set it up:

  ```sh
  curl -fsSL https://claude.ai/install.sh | bash
  ```

  Or:

  ```sh
  brew install --cask claude-code
  ```

  Sign in by running `claude`.

### D11: Codex CLI

Runs workflow steps through your own signed-in `codex`.

- Needed for: the provider `codex` (optional).
- Check: `codex --version`
- Set it up:

  ```sh
  brew install --cask codex
  ```

  Or:

  ```sh
  npm install -g @openai/codex
  ```

  Sign in by running `codex login`. Upstream marks the Codex profile HELD: the CLI's filesystem read exposure is an untested boundary. Sign in with `codex login` to use your ChatGPT subscription; an API key makes every call a paid call. Init does not propose Codex as the default provider when you selected another one.

### D12: Antigravity CLI (agy)

Runs workflow steps through your own signed-in `agy`.

- Needed for: the provider `antigravity` (optional).
- Check: `agy --version`
- Set it up:

  ```sh
  curl -fsSL https://antigravity.google/cli/install.sh | bash
  ```

  Sign in by running `agy`.

### D13: At least one usable provider

A workflow step is a call to a model. One provider above must be installed and signed in. Ollama is the one that needs no account: set up the Ollama row and its model row, and this one is met.

- Needed for: every deployment (required).

### D14: Lima

Runs the small Linux virtual machine that holds the deployment's only Docker engine. Docker Desktop is not used.

- Needed for: the observability tier and isolation tier 3 (optional).
- Check: `limactl --version`
- Set it up:

  ```sh
  brew install lima
  ```

  Without Homebrew, follow https://lima-vm.io/docs/installation/.

### D15: The kit's virtual machine: Docker Engine, Docker Compose and gVisor

Inside the Lima virtual machine, Docker Engine and Compose run the trace stack (collector, Tempo, Grafana). gVisor sandboxes tool calls at isolation tier 3. The kit installs all three when it creates the virtual machine.

- Needed for: the observability tier and isolation tier 3 (optional).
- Check: `arhugula observability vm status`
- Set it up:

  ```sh
  arhugula observability vm create
  ```

  During init, answering `kit` at question 11 does the same.
<!-- END GENERATED: dependencies -->

## Start init

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

If the clone is somewhere else, init clones the kit into `<home>/kit` after the first group of preflight checks, and continues from that copy.
The copy prints the dependency list and those checks once more. It does not ask the questions again.
The kit must sit at `<home>/kit`, because the kit finds its home as the directory that contains it.

Init first makes sure that two tools exist, because init itself runs on them: `uv`, and CPython 3.12 managed by uv.
When one is missing, init says what it is for and shows the setup command. It runs the command only when you type `y`.
If you decline, init stops with exit code 3 and changes nothing.

### What the first install downloads

The first install takes longer than a later one, because it downloads these parts:

- **The harness source:** a clone of the upstream repository.
- **The Python dependencies:** the packages of the harness, which uv keeps in its cache.
- **The Ollama model:** about 2 GB, when you use Ollama with its default model.
- **The VM:** 5 to 10 minutes the first time, when you answer `kit` at question 11. `kit` is the default when Lima is installed. Init creates that VM only when 12 GiB are free under the home.

With every download in the cache, the install itself takes about a minute.

### Start on a Mac with nothing installed

On such a Mac, init stops more than once, and each time it names what to set up. Set it up, then run init again.

1. **`uv` and CPython 3.12:** init offers to install both, as described above.
2. **A provider:** init stops in the dependency stage with this message, because no provider is set up yet:

   ```text
   init cannot continue until these are in place: D13 At least one usable provider
   ```

3. **The shortest way on:** set up Ollama, the one provider that needs no account. Install the app from https://ollama.com/download and open it, then pull the model:

   ```sh
   ollama pull llama3.2:3b
   ```

4. **Init again:** run `~/arhugula/kit/init` once more.

Lima is missing on such a Mac too, so the default at question 11 is `n` and init creates no VM. The [dependencies](#dependencies) list shows how to install Lima first if you want the trace stack.

## What init does, in order

Each stage either completes or stops init with the failure and its fix.

1. **Survey.** Init looks at the machine. It changes nothing.
2. **Dependency stage.** Init checks the 16 dependencies and explains each missing one. Where it may run the setup command, it offers to, and then checks again.
3. **Questions.** Init asks up to 14 questions.
4. **Preflight, machine.** Init runs the checks that need nothing installed. So far, nothing was written.
5. **Install.** Init fetches the harness at the pin and builds seven packages and two lock files with hashes. It runs upstream's packaging gate, then creates the environment. With a warm cache this takes about a minute.
6. **Preflight, installed.** Init runs the checks that need the environment.
7. **Generate.** Init writes every config, and the runtime's own loader must accept each one. Then the runtime stamps the state root.
8. **Preflight, generated.** Init checks the generated files.
9. **Observability stack.** When you chose the tier, init creates or starts the virtual machine (VM) and starts the trace stack.
10. **Isolation tier 3.** When you chose it, init sets up the sandbox for tool calls.
11. **Smoke runs.** Init runs one short workflow on the default provider. It runs a second one on Ollama when you selected Ollama and another provider is the default, and one more in the attached project.

Init ends with the home, the command path and four next steps:

```text
The deployment is ready.
  home:    <home>
  command: <home>/bin/arhugula
  use it in this terminal:      export PATH="<home>/bin:$PATH"
  keep it for new terminals:    echo 'export PATH="<home>/bin:$PATH"' >> ~/.zshrc
  run a workflow:               arhugula run ollama-first.toml --provider ollama
  attach your own repository:   arhugula project add <path-to-a-repository>
```

- **Use it in this terminal:** paste the first `export` line, and `arhugula` works in the terminal that you have open.
- **Keep it for new terminals:** paste the `echo` line once. It adds the same line to `~/.zshrc`.
- **Run a workflow:** a first run that works on your deployment. With Ollama selected it is the line shown here. Without Ollama it is `arhugula run minimal.toml`, on your default provider.
- **Attach your own repository:** `arhugula project add` makes a repository of yours a project of this deployment.

When init stops early, its exit code says why:

| Exit code | Why init stopped |
| --- | --- |
| 1 | A smoke run did not complete. |
| 3 | Something you can fix: a required dependency is missing, a preflight check failed, or an answer is missing. |
| 4 | The runtime refused a generated config. Nothing was changed. |
| 5 | An external tool failed, for example the install or a setup command. |

Exit code 5 has a second meaning elsewhere: a workflow run that is put on hold at a gate also ends with 5. That code comes from the runtime, and it never comes from init.

## Read the dependency stage

Init prints one line per dependency, numbered D1 to D15. This excerpt is from a real init (*witnessed*):

```text
Dependencies (what this deployment needs on the machine):
  ok       D1  macOS 13 or later: macOS 26.6.2 on Apple silicon
  ok       D2  Xcode Command Line Tools: /Library/Developer/CommandLineTools
  ok       D3  git: /usr/bin/git
...
  ok       D8  Ollama: answers at http://127.0.0.1:11434; 10 model(s) pulled
  ok       D9  The Ollama model llama3.2:3b: llama3.2:3b is pulled
  ok       D10 Claude Code CLI: ready: 2.1.325 (Claude Code); signed in (claude.ai)
...
  ok       D13 At least one usable provider: claude_code, ollama, codex, antigravity
  ok       D14 Lima: Lima 2.2.1
  ok       D15 The kit's virtual machine: Docker Engine, Docker Compose and gVisor: Docker 29.9.3, Compose 5.7.1, gVisor runsc
```

The first word of a line gives the state:

| Word | Meaning | What init does |
| --- | --- | --- |
| `ok` | The dependency is in place. | Goes on. |
| `absent` | An optional dependency is missing. | Prints its guide and goes on. |
| `MISSING` | A required dependency is missing. | Prints its guide. Init stops after the list if the dependency is still missing. |
| `low` | Less than 3 GiB of disk space is free. | Prints its guide and goes on. Preflight check P4 checks the space again, for the home that you choose. |

The guide for a missing dependency says what it is for and what needs it. It gives the setup command, any step after that, and the command to check by hand.

Where the setup is one safe command and its installer is on the machine, init asks ``Run `<command>` now? [y/N]``.
The command runs only when you type `y`. Init then checks the dependency again.
For Ollama, init asks about each of the two steps in turn.

When a required dependency is still missing after the list, init stops with exit code 3 and names it:

```text
init cannot continue until these are in place: D13 At least one usable provider
```

This is the message on a Mac where no provider is set up yet. Ollama is the provider that needs no account: set up the Ollama entry and its model entry, then run init again.

## Answer the questions

Init asks up to 14 questions, and skips a question that does not apply to your earlier answers.
Each prompt shows the question number, the options when there are any, notes, and the default in square brackets.

- **Accept a default:** press Enter.
- **Choose one option:** type the value shown in square brackets before the option.
- **Choose several options:** type their letters or numbers together, for example `co` or `1234`.
- **Recover from a slip:** when init cannot read an answer, it says why and asks the same question again.

These prompts are from a real init (*witnessed*):

```text
[3/14] Default provider for workflows?
      [claude_code] Claude Code CLI
      [ollama] Ollama (local models)
      [codex] Codex CLI
      [antigravity] Antigravity CLI (agy)
    answer [claude_code]: claude_code

[4/14] Fallback provider when the default fails?
      [ollama] Ollama (local models)
      [codex] Codex CLI
      [antigravity] Antigravity CLI (agy)
      [none] no fallback
    answer [ollama]: ollama

[5/14] Which models should each selected provider make available? Type <provider>=<model>,<model>, providers separated by `;`, or press Enter for the defaults.
      [claude_code] Claude Code CLI  (it lists no models, so any name it knows is accepted unchecked, for example sonnet, opus, haiku, fable. thinking levels, written <model>@<level>: low, medium, high, xhigh, max)
...
      note: Format: <provider>=<model>,<model>; <provider>=<model>. The first model named for a provider is its default; Enter keeps the default shown. A provider you do not name keeps its default. Add a thinking level as <model>@<level> where the provider has levels.
      note: Add or change models later: arhugula provider enable <provider> --model <model> [--model ...]
    answer [claude_code=sonnet@low; ollama=llama3.2:3b; codex=gpt-6.1-sol; antigravity=gemini-4-argon-medium]: claude_code=sonnet,haiku@low; codex=gpt-6.1-sol@low,gpt-5.6-luna; antigravity=gemini-3.8-flash-low
...
[8/14] Workload classes to bind? Type the numbers.
      [1] pipeline-automation
      [2] software-engineering
      [3] research
      [4] content-creation
    answer [1234]: 1234
```

Some questions need more than the prompt says:

- **Question 2, providers:** the note under the options explains the limits of Codex. Init never proposes Codex as the default provider when you selected another provider.
- **Question 5, models:** name the models each provider makes available, and put the one you want as default first. Add a thinking level as `<model>@<level>` for Claude Code and Codex. Init refuses a model or level with a space or a leading `-`, a level on a listed model without levels, and a provider named twice. For Ollama, init proposes `llama3.2:3b` and offers to pull it when it is not pulled.
  The lists come from each tool's own sign-in, so the names on your Mac differ from the ones above: [Choose a model and a thinking level](providers.md#choose-a-model-and-a-thinking-level) explains them.
- **Question 11, observability:** `kit` creates the kit's own VM under `<home>/lima`. Init creates it only when 12 GiB are free under the home. The first time takes 5 to 10 minutes, and about 1 minute when the image is cached. **Docker Desktop is not required and is never used.** A Lima instance that was built for another processor type is not offered, and the prompt says why.
- **Question 9, audit signing:** when you choose `s`, init creates both signing keys itself, before the first run. Every ledger is then signed from its first entry.

The list below gives every question as init prints it, with its default, the reason init asks, and when it is asked.

<!-- BEGIN GENERATED: questions -->
### Question 1: `home`

> Deployment home directory? Everything the harness installs and stores lives here.

- Default: `~/arhugula`, or the directory that already holds this kit clone as `kit/`.
- Why init asks: The location is yours to choose. It must not be inside a git checkout.
- Asked: always.

### Question 2: `providers`

> Which providers should be available? Type the letters of each one you want.

- Default: every command-line provider found installed and signed in, plus Ollama when it answers.
- Why init asks: Each selected provider is checked in preflight and written into the config.
- Asked: always.

### Question 3: `primary`

> Default provider for workflows?

- Default: Claude Code when selected, else Ollama, else the first selected provider; never Codex when another is selected.
- Why init asks: The first fallback chain serves every step unless a run overrides it.
- Asked: always.

### Question 4: `fallback`

> Fallback provider when the default fails?

- Default: Ollama when it is selected and is not the default provider; otherwise none.
- Why init asks: A second provider keeps a run going when the first one refuses.
- Asked: always.

### Question 5: `models`

> Which models should each selected provider make available? Type <provider>=<model>,<model>, providers separated by `;`, or press Enter for the defaults.

- Default: the first model each provider's own tool lists for your sign-in. Ollama: `llama3.2:3b` (init offers to pull it when it is not pulled). Where a tool lists none: `sonnet` for Claude Code, the catalogue's example model for a hosted API.
- Why init asks: Routing, workflows and `--model` can use only the models named here. The first one named for a provider is its default. Where a provider's tool lists its models (Codex, Antigravity, Ollama), init checks each name against that list.
- Asked: always.

### Question 6: `ollama_host`

> Ollama host URL?

- Default: `http://127.0.0.1:11434`.
- Why init asks: Asked only when Ollama does not answer at its default address.
- Asked: Ollama is selected and does not answer at the default address.

### Question 7: `project`

> Attach a project now? Give the path to a project repository, or press Enter to skip.

- Default: none.
- Why init asks: One install serves many projects. You can attach more later with `project add`.
- Asked: always.

### Question 8: `workloads`

> Workload classes to bind? Type the numbers.

- Default: all four.
- Why init asks: A workload class is the kind of work a workflow declares. A workflow runs only when its class is bound. The shipped examples and the daemon need all four, so keep all four unless you know you want fewer.
- Asked: always.

### Question 9: `features`

> Enable now? Type the letters, or `none`.

- Default: memory.
- Why init asks: Each stays switchable later with `feature enable` and `feature disable`.
- Asked: always.

### Question 10: `memory_mode`

> Memory access?

- Default: `packet+tools`.
- Why init asks: Both modes are witnessed. Tools let the agent look things up on its own.
- Asked: memory is enabled.

### Question 11: `observability`

> Set up the observability tier (collector, Tempo, Grafana)? Answer kit, n, or an existing instance shown below.

- Default: `kit` when Lima is installed, otherwise `n`.
- Why init asks: Traces, dashboards and alerts. Without it, traces stay in the local span store only.
- Asked: always.

### Question 12: `isolation_tier3`

> Enable isolation tier 3 (tools run under gVisor in the virtual machine)?

- Default: no.
- Why init asks: Tool calls from Model Context Protocol (MCP) clients run in a sandboxed container. Off by default.
- Asked: a virtual machine was chosen at question 11.

### Question 13: `forbidden_roots`

> Backup or restore locations that can reach the state root? Comma-separated paths, or press Enter for none.

- Default: none.
- Why init asks: A backup tool that restores old files over the state root would silently undo the harness's records. The runtime refuses a state root inside any location you list here. If you do not know of one, press Enter.
- Asked: always.

### Question 14: `smoke`

> Run the smoke workflows now?

- Default: yes.
- Why init asks: One short run on each route proves the deployment end to end: the default provider, Ollama when selected, and the attached project.
- Asked: always.
<!-- END GENERATED: questions -->

## Read the preflight checks

Preflight is a set of 18 checks, P1 to P18. Init runs them in three groups, each as early as it can:

| Group | When it runs | If a check fails |
| --- | --- | --- |
| machine | After the questions, before the install. | Nothing was written. |
| installed | After the install. | The environment is installed. No configuration was generated. |
| generated | After the configs are written. | The configuration was generated, but the deployment is not verified. |

This excerpt is from a real init (*witnessed*):

```text
Preflight (machine):
  ok    P1  macOS 26.6.2 on Apple silicon
...
  ok    P4  445 GiB free
  ok    P5  a plain directory, outside every git checkout
  ok    P6  every selected CLI provider is installed, signed in and offers the models named for it
  ok    P7  Ollama answers at http://127.0.0.1:11434; llama3.2:3b pulled
...
  skip  P16 the signing-key directory is usable: audit signing is off
  skip  P17 the offline embedding model is in place: offline embedding routing is off
```

The first word of a line gives the result:

| Word | Meaning |
| --- | --- |
| `ok` | The check passed. The line says what init found. |
| `warn` | Init goes on. The `fix:` line says what to do about it. |
| `skip` | The check does not apply to your answers. |
| `FAIL` | Init stops with exit code 3, and names every failed check with its fix. |

The table below lists every check, when it runs, when it fails, and what to do.

<!-- BEGIN GENERATED: preflight -->
| Check | What it checks | Runs | Fails when | What to do |
| --- | --- | --- | --- | --- |
| P1 | a supported macOS | always | the machine is not macOS 13 or later | none: the kit runs on macOS only |
| P2 | the developer tools, git and uv are installed | always | the Xcode Command Line Tools, `git` or `uv` is missing | `xcode-select --install`; `brew install uv` |
| P3 | CPython 3.12 is available through uv | always | uv has no CPython 3.12 | `uv python install 3.12` (init offers to run it) |
| P4 | enough free disk space under the home | always | less than 3 GiB is free, or less than 12 GiB when init is about to create the virtual machine | free space on that volume, or choose another home |
| P5 | the home is outside every git checkout | always | the home is inside a git checkout, or holds a checkout other than `kit` and `upstream` | choose a plain directory outside every git checkout |
| P6 | each selected CLI provider is installed, signed in and offers its models | always | the default or fallback provider's CLI is missing or signed out, or its sign-in no longer offers its default model (any other selected provider, or another of its models, is a warning) | install the CLI and sign in with its own command; for a model it no longer offers, the `arhugula provider enable` line the check prints, or answer question 5 again (`init --reconfigure`); `arhugula provider check` shows each |
| P7 | Ollama answers and has the models | Ollama is selected | Ollama does not answer, or the default Ollama model is not pulled, and the routing depends on Ollama | `ollama serve`; `ollama pull <model>` (init offers to run it) |
| P8 | the state root can be created safely | always | `<home>/state` holds files the runtime did not stamp, is not yours with mode 0700, or its parent is writable by others | the `chmod` line the check prints, or choose another home |
| P9 | the state root's filesystem is durable | always | the home is on a RAM disk, or the runtime cannot tell what filesystem it is on | choose a home on a local APFS volume |
| P10 | the project has no leftover harness state | a project is attached | the project holds a ledger or memory from an earlier setup that kept state inside the checkout | `arhugula state archive-legacy <project>` |
| P11 | the generated configs load in the runtime | always | the runtime's own loader refuses a generated config | the loader's message names the field; this is a kit defect if no verb of yours caused it |
| P12 | no placeholder is left in a generated file | always | a generated file still holds `{{...}}` or a `~` | a kit defect: file an issue with the file attached |
| P13 | the trace endpoint matches the observability answer | always | never fails; it warns when the tier is on and nothing listens on 127.0.0.1:4317 outside init, or when the tier is off and something does listen there | `arhugula observability up` |
| P14 | the virtual machine and its Docker engine | a VM is chosen | Lima is missing or older than 2.0; the home's path is too long for the VM's sockets; the chosen instance does not exist or was built for another CPU; the stack's ports are held by something else; or no Docker engine with Compose answers inside the running VM | `brew install lima`; answer `kit` at question 11; free the port the check names |
| P15 | gVisor for isolation tier 3 | tier 3 is on | tier 3 is on and no virtual machine is chosen, or the VM's Docker engine lists no `runsc` runtime | answer `kit` at question 11, or `arhugula observability vm create` |
| P16 | the signing-key directory is usable | audit signing is on | `<home>/keys` is readable by others or cannot be created | `chmod 700 <home>/keys` |
| P17 | the offline embedding model is in place | embedding routing is on | the model directory or its `SHA256SUMS` file is missing under `<home>/models` | follow `Offline embedding routing` in docs/configure.md |
| P18 | the pause-journal root resolves | always | the installation-state document names no existing pause-journal directory | `arhugula init --reverify` |
<!-- END GENERATED: preflight -->

## What init generates, and where

Init writes only under `<home>`. The tools that it drives keep their own download caches elsewhere: uv for packages, and Lima for the VM image.

| Path | What it is | Written by |
| --- | --- | --- |
| `<home>/upstream/` | The harness source at the pinned commit. | Install |
| `<home>/dist/` | Seven built packages, two lock files with hashes, and `SHA256SUMS`. | Install |
| `<home>/env/` | The private, non-editable Python environment of the harness. | Install |
| `<home>/logs/install-*.log` | The log of each install step. | Install |
| `<home>/config/init-answers.json` | Your answers: the one source of the configuration. | Generate |
| `<home>/config/harness.toml` | The config of the deployment default. | Generate |
| `<home>/config/projects/<project>.toml` | The config of one attached project. | Generate |
| `<home>/env/etc/arhugula/installation-state.json` | The document that names the pause-journal root for the runtime. | Generate |
| `<home>/state/` | The state root, stamped by the runtime, with `pause-journal/` inside. | Generate |
| `<home>/bin/arhugula` | The command, as a link to `<home>/kit/bin/arhugula`. | Generate |
| `<home>/AGENTS.md`, `<home>/CLAUDE.md` | Pointers to the kit's instructions, for an agent CLI opened in the home. | Generate |
| `<home>/run/`, `<home>/backups/` | Two working directories: one for the sockets and process files of a daemon, one for state backups. | Generate |
| `<home>/observability/` | The Compose project of the trace stack. | Observability stack |
| `<home>/secrets/grafana-admin-password` | The Grafana password. | Observability stack |
| `<home>/lima/` | The kit's own VM. | Observability stack |
| `<home>/bin/gvisor-docker` | The container command of the tier 3 sandbox. | Isolation tier 3 |

These rules protect the files:

- **Generated configs are not edited.** Each `*.toml` file starts with a header that says so. A verb changes your answers and generates the files again.
- **A change is all or nothing.** The kit renders the new configs aside and has the runtime's loader accept each one. Only then does it put them in place. A change that the runtime refuses leaves the deployment as it was.
- **No secret is in a config.** API keys live in the macOS keychain.

## Run init again

Init is safe to run again. It keeps the environment when it is already at the pin, and it regenerates every config.

When you run `<home>/kit/init` with no flag on an existing deployment, it asks one question after the dependency list:

```text
This deployment is already configured (<home>/config/init-answers.json).
    Keep its answers and only re-verify? [Y/n]:
```

Answer `y`, or press Enter, to check everything with your stored answers. Answer `n` to go through the questions again, with your stored answers as the defaults.

The flags choose a mode without that question:

| Command | What it does |
| --- | --- |
| `<home>/kit/init --reverify` | Keeps the stored answers and asks nothing. It checks, regenerates and verifies everything. |
| `<home>/kit/init --reconfigure` | Asks every question again, with your earlier answers as defaults. |
| `<home>/kit/init --answers <file>` | Replays an answers file. It refuses a missing answer with exit code 3. |
| `<home>/kit/init --yes` | Accepts every default without asking. |
| `<home>/kit/init --reinstall` | Rebuilds the environment even when it is already at the pin. Combine it with another mode. |
| `<home>/kit/init --smoke` | Runs only the smoke workflows. |
| `<home>/kit/init --questions-json` | Prints the dependencies and the questions as JSON, and changes nothing. |

These facts apply to the modes:

- **No offers without questions:** with `--answers`, `--yes` or `--reverify`, init does not offer to run a setup command. It reports a missing dependency with its setup command, and stops when the dependency is required.
- **Your other settings stay:** attached projects, and settings that you stored with verbs, survive a re-run unless an answers file names them.
- **Two spellings:** `arhugula init` takes the same flags. With `--reinstall` it hands over to `<home>/kit/init`, because that script runs outside the environment that it rebuilds.

To change one setting, a verb is usually shorter than `--reconfigure`: see [configure](configure.md).

## Check a deployment with doctor

`arhugula doctor` repeats the dependency list and all preflight checks against the current deployment. It changes nothing.

<!-- witness -->
```sh
arhugula doctor
```

This output is from a real run (*witnessed*), trimmed:

```text
Surveying this machine (nothing is changed)...

Dependencies:
  ok       D1  macOS 13 or later: macOS 26.6.2 on Apple silicon
...
  ok       D14 Lima: Lima 2.2.1
  ok       D15 The kit's virtual machine: Docker Engine, Docker Compose and gVisor: Docker 29.9.3, Compose 5.7.1, gVisor runsc

Preflight:
  ok    P1  macOS 26.6.2 on Apple silicon
...
  ok    P8  stamped by the runtime
  ok    P10 no attached project holds leftover harness state
  ok    P13 the trace endpoint is listening and the observability tier is on
...
  ok    P9  apfs
  ok    P11 2 generated config(s) load through the runtime's own loader
  ok    P12 no placeholder or `~` in any generated file
  ok    P18 the pause-journal root resolves to <home>/state/pause-journal

Every check passed or is a warning.
```

When a check fails, `doctor` exits with code 3. It names each failed check and prints its `fix:` line.

A second read-only check shows the newest entries of the ledger:

<!-- witness -->
```sh
arhugula status
```

## Prove the refusals with the self-test

A successful run does not show that the deployment refuses what it should.
`arhugula doctor --self-test` breaks one precondition at a time, and expects the matching refusal each time (*kit extension*).

```sh
arhugula doctor --self-test
```

It tests three groups:

- **Dependencies:** the guide appears for a missing tool. Init stops for a required one and goes on for an optional one.
- **Preflight:** each check fails, with its fix, when its precondition is broken.
- **Runtime:** four real runs that the runtime must refuse. They are a validator class that cannot be imported, a prompt version that nobody authored, an exhausted fallback chain, and a step deadline too short to meet.

The four runs use the Ollama provider, so they cost nothing. When Ollama is not enabled, the self-test says that it did not exercise them.

The self-test leaves your configuration, ledgers, memory and traces as they were.
It breaks values in memory and scratch files under `<home>/run/selftest`.
The four runs use their own tenant, their own ledger under `<home>/state/self-test` and their own span store, and they send no trace to the collector.
The self-test removes both directories afterwards.

This excerpt is from a real self-test (*witnessed*), trimmed. Long lines are cut by the program:

```text
dependencies:
  ok    missing required: uv [uv is not installed]
        guide printed with `brew install uv`; init stops
...
  ok    missing optional: Lima [Lima is not installed]
        guide printed with `brew install lima`; init goes on, because it is optional
...
preflight:
...
  ok    P2 [uv is not installed]
        FAIL: `uv` is not on PATH | fix: brew install uv
  ok    P3 [uv has no CPython 3.12]
        FAIL: uv has no CPython 3.12 | fix: uv python install 3.12
  --    P4
        not exercised: a full disk cannot be simulated safely; the check compares free space with the need
...
  ok    P7 [Ollama does not answer]
        FAIL: no answer from Ollama at http://127.0.0.1:9 | fix: ollama serve
...
  ok    P14 [a virtual machine is chosen and Lima is not installed]
        FAIL: `limactl` is not on PATH | fix: brew install lima
...
runtime:
  ok    bad validator class [a validator binding names a class that cannot be imported]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage OD (5): ValidatorFrameworkStageMaterializeError: RT-FAIL-VALIDATOR-STAGE-MATERIALIZE: validator 'arhugula
  ok    unauthored prompt version [the prompt selection names a version nobody authored]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage PREAMBLE (0): PromptSelectionUnauthoredError: RT-FAIL-PROMPT-SELECTION-UNAUTHORED: prompt-selection bindi
  ok    exhausted fallback chain [the only provider in the chain serves a model that does not exist]
        exit 1: detail:    workflow execution returned status='failed' with fail_class="step-failure: RetryBreakerFallbackExhaustedError: RT-FAIL-FALLBACK-EXHAUSTED: 
  ok    step deadline [a step may take 10 milliseconds and a model call takes longer]
        exit 1: detail:    workflow execution returned status='failed' with fail_class='step-failure: RT-FAIL-STEP-DISPATCH-TIMEOUT: step dispatch exceeded 0.01s boun

22 guard rail(s) refused as expected. 4 could not be exercised here; the lines marked -- say why.
```

Read each pair of lines like this:

- **`ok`:** the guard rail refused as expected. The text in square brackets says what was broken, and the second line shows the refusal.
- **`FAIL` as the first word:** a guard rail did not refuse. The self-test then exits with code 6. Please file an issue.
- **`--`:** the case was not exercised. Some cases cannot be broken safely on a real machine, for example a full disk. The second line then starts with `not exercised:` and gives the reason.

The last line counts both kinds. In the witnessed run, 22 guard rails refused as expected: 4 dependency cases, 14 preflight checks and the 4 runs. Another 4 preflight checks, P4, P9, P13 and P18, were not exercised.

P18 is one of them, because breaking it would break the deployment. If `arhugula doctor` ever reports P18 as failed, the fix is `arhugula init --reverify`.

## Move the home with relocate

`arhugula relocate <new-home>` moves the whole home to another directory. The move there and back is *witnessed*, with the VM, at about a minute each way.

1. Stop the daemon, if one runs:

   ```sh
   arhugula daemon stop
   ```

2. Stop the trace stack and the VM. This also turns the observability tier off:

   ```sh
   arhugula observability down --stop-vm
   ```

3. Move the home:

   ```sh
   arhugula relocate <new-home>
   ```

4. Change the `export PATH=...` line in your shell profile to `<new-home>/bin`.

5. If you use the observability tier, start it again:

   ```sh
   <new-home>/bin/arhugula observability up
   ```

6. Write the harness section again in each project that carries it. The section holds the path of the command, and `relocate` does not change a project's files:

   ```sh
   <new-home>/bin/arhugula agent context install --project <project>
   ```

   [Add the harness section to a project](agents.md#add-the-harness-section-to-a-project) describes the section.

After the move, `relocate` runs init from the new place with `--reverify --reinstall`.
That rebuilds the environment, because its scripts carry their own path. It also regenerates every config.
The runtime then verifies the state root at its new place. The smoke runs repeat when your answers include them.

The rebuild keeps the environment it replaces at `<new-home>/env.rollback`.
That copy was built for the earlier home, so do not roll back to it: see [Rebuild at the same pin](upgrade.md#rebuild-at-the-same-pin).

The move takes the state root with it, pause journals included.
Resuming a gate on hold after a move was not witnessed, so answer the gates on hold first: `arhugula gate list` shows them.

`relocate` refuses, and moves nothing, in these cases:

| Case | Exit code |
| --- | --- |
| The new home is the current home. | 2 |
| The new home exists and is not empty. | 3 |
| The new home would be inside a git checkout. | 3 |
| The parent directory of the new home does not exist. | 3 |
| A daemon, the VM or the trace stack is still running. | 3 |
| The new path is too long for the VM. macOS limits a socket path to 104 bytes, and Lima keeps its sockets under the home. | 3 |

## Remove the deployment with uninstall

`arhugula uninstall` only lists what it would remove. This output is from a real run (*witnessed*):

```text
This removes:
  <home>/env
  <home>/env.rollback
  <home>/dist
  <home>/upstream
  <home>/config
  <home>/run
  <home>/logs
  <home>/bin
  <home>/observability
  <home>/lima
  <home>/AGENTS.md
  <home>/CLAUDE.md
  (kept) <home>/state
  (kept) <home>/keys
  (kept) <home>/secrets
  (kept) <home>/backups
  (kept) <home>/kit  — the kit itself; delete <home> by hand when you are done

Nothing was removed. Run again with --yes to remove these.
```

To remove the deployment:

1. Remove each API key that you stored, with `arhugula provider key delete <name>`. The command goes away with the environment in step 4.
2. Stop the daemon, if one runs, with `arhugula daemon stop`.
3. Stop the trace stack and the VM with `arhugula observability down --stop-vm`.
4. Run the removal:

   ```sh
   arhugula uninstall --yes
   ```

5. Remove the `export PATH=...` line from your shell profile.
6. Delete `<home>` by hand when you no longer need the kit and what was kept.

Choose how much goes:

| Command | Removes | Keeps |
| --- | --- | --- |
| `arhugula uninstall --yes` | The environment, the harness source, the configs with your answers, the logs, the trace stack and the kit's VM. | The state root, keys, secrets, backups and the kit. |
| `arhugula uninstall --yes --delete-state` | All of the above, and the state root, keys, secrets and backups. | The kit. |

**Warning:** `--delete-state` deletes every ledger, all memory and the signing keys. Nothing can bring them back. Run `arhugula state backup` first and copy the archive out of `<home>`, because the backups go too.

Uninstall touches nothing outside the home.
The dependencies, your provider sign-ins and the working files in your projects stay.
API keys stay in the macOS keychain unless you removed them in step 1.

## Let an agent drive init

An agent CLI, such as Claude Code or Codex, can run init for you. It cannot type at init's prompts, so init has two modes for it:

1. `init --questions-json` prints one JSON object, `{"dependencies": [...], "questions": [...]}`. It changes nothing on the machine.
2. `init --answers <file>` replays a file of answers.

Between the two, the agent relays each missing dependency to you, asks you every question, and writes your answers to a file.
The answers are yours: the agent carries them and does not choose them.

The answers file has one key per question. The kit ships an example, `init-answers.example.json`:

```json
{
  "_about": "An EXAMPLE answers file for `init --answers`. Every path here is a placeholder: replace /absolute/path/to/... with real paths on your machine. `init --questions-json` prints the questions with the defaults computed for your machine. `models` names, per selected provider, the models it makes available; the first is its default, and `<model>@<level>` adds a thinking level where the provider has levels (Claude Code, Codex). A model a provider's own tool does not list for your sign-in is refused.",
  "home": "/absolute/path/to/arhugula",
  "providers": ["claude_code", "ollama"],
  "primary": "claude_code",
  "fallback": "ollama",
  "models": {"claude_code": ["sonnet", "opus@high"], "ollama": ["llama3.2:3b"]},
  "ollama_host": "http://127.0.0.1:11434",
  "project": "",
  "workloads": ["pipeline-automation", "software-engineering", "research", "content-creation"],
  "features": ["memory"],
  "memory_mode": "packet+tools",
  "observability": {"enabled": true, "engine": "kit", "lima_home": "", "instance": ""},
  "isolation_tier3": false,
  "forbidden_roots": [],
  "smoke": true
}
```

With an answers file, init behaves strictly:

- **No silent default:** a question that applies and has no answer stops init with exit code 3.
- **No placeholder:** init refuses a file that still holds `/absolute/path/to`.
- **No retired provider:** init refuses a file that names a provider the kit no longer offers, and its message says which entries to delete.
- **Old files still work:** a file in the earlier format, which named one model per provider, is migrated to `models`.
- **No install on its own:** for a missing dependency, init reports the dependency and its setup command. It stops when the dependency is required.

Keep the answers file outside the repository, because it holds paths of your machine.

The full protocol, with the lines an agent must not cross, is in [AGENTS.md](../AGENTS.md). The [agents page](agents.md) explains it for operators.

## Sources

This page was checked against these kit files:

- **Init:** `init`, `bin/install.sh`, `lib/arhugula_kit/initflow.py`, `init-answers.example.json`.
- **The generated parts:** `lib/arhugula_kit/dependencies.py`, `lib/arhugula_kit/questions.py`, `lib/arhugula_kit/preflight.py`, `lib/arhugula_kit/docgen.py`.
- **Generated files:** `lib/arhugula_kit/render.py`, `lib/arhugula_kit/deploy.py`, `lib/arhugula_kit/layout.py`.
- **Lifecycle verbs:** `lib/arhugula_kit/verbs_lifecycle.py`, `lib/arhugula_kit/selftest.py`, `lib/arhugula_kit/errors.py`.
- **The agent protocol:** `AGENTS.md`.

It was checked against these upstream documents, with paths relative to the home:

- **The state root and the pause-journal root:** `upstream/docs/how-to-operate-runtime.md`.
- **Deployment:** `upstream/docs/how-to-deploy.md`.
- **The trace stack:** `upstream/deploy/self-hosted-local/README.md`.
