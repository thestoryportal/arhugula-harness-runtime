# Choose providers and routing

This page is for the operator.
After reading it, you can sign in to each provider and check it.
You can also choose the model and thinking level for one step, one role, one kind of work, the default or one run.

A *provider* is a source of model replies: a signed-in command-line tool, the local Ollama server, or a hosted API.
Nothing here is installed for you: see [the dependencies](install.md#dependencies) for what each provider needs.

## On this page

- [The providers](#the-providers)
- [How the runtime calls a command-line provider](#how-the-runtime-calls-a-command-line-provider)
- [Sign in and check each provider](#sign-in-and-check-each-provider)
- [Know the Codex caveats](#know-the-codex-caveats)
- [Use Antigravity](#use-antigravity)
- [Run local models with Ollama](#run-local-models-with-ollama)
- [Use a hosted API with a key in the keychain](#use-a-hosted-api-with-a-key-in-the-keychain)
- [Enable, disable and tune a provider](#enable-disable-and-tune-a-provider)
- [How routing picks a provider](#how-routing-picks-a-provider)
- [Change the routing](#change-the-routing)
- [Choose a model and a thinking level](#choose-a-model-and-a-thinking-level)
- [Add your own provider](#add-your-own-provider)
- [Run an agent that acts with its own tools](#run-an-agent-that-acts-with-its-own-tools)
- [Review with a second model](#review-with-a-second-model)
- [Know what a run costs](#know-what-a-run-costs)
- [Sources](#sources)

## The providers

The runtime can dispatch to six providers of the kit's catalogue, and to any command you add yourself.
The kit does not offer the Gemini CLI: Google deprecated it, and Antigravity (`agy`) is the Google command-line provider.
The program generates this table from its own catalogue.

<!-- BEGIN GENERATED: providers -->
| Name | Provider | Reached through | Models | Thinking level | Install | Sign in |
| --- | --- | --- | --- | --- | --- | --- |
| `claude_code` | Claude Code CLI | its command-line tool, signed in by you | any name it knows, unchecked; init proposes `sonnet` | `<model>@<level>`: low, medium, high, xhigh, max | `curl -fsSL https://claude.ai/install.sh \| bash`<br>`brew install --cask claude-code` | `claude` |
| `ollama` | Ollama (local models) | the local Ollama server | the models you have pulled (`ollama list`); init proposes `llama3.2:3b` | its thinking is set per step, in the step's `params` in a workflow manifest (see docs/workflows.md) | `brew install ollama` | `brew services start ollama` |
| `codex` | Codex CLI | its command-line tool, signed in by you | the ones its own tool lists for your sign-in (`codex debug models`); init proposes the first | `<model>@<level>`: the levels its tool lists for the model | `brew install --cask codex`<br>`npm install -g @openai/codex` | `codex login` |
| `antigravity` | Antigravity CLI (agy) | its command-line tool, signed in by you | the ones its own tool lists for your sign-in (`agy models`); init proposes the first | its thinking level is part of the model, so choose the model id that carries the level you want (`arhugula provider models antigravity` lists them) | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` | `agy` |
| `anthropic` | Anthropic API (key in the keyring; paid) | a hosted API, with a key in the macOS keychain | any name it knows, unchecked; init proposes `claude-haiku-4-5` | its thinking is set per step, in the step's `params` in a workflow manifest (see docs/workflows.md) | nothing to install | `arhugula provider key set anthropic` |
| `openai` | OpenAI API (key in the keyring; paid) | a hosted API, with a key in the macOS keychain | any name it knows, unchecked; init proposes `gpt-4o` | its thinking is set per step, in the step's `params` in a workflow manifest (see docs/workflows.md) | nothing to install | `arhugula provider key set openai` |
<!-- END GENERATED: providers -->

List the providers of your deployment, with the role, model and state of each:

<!-- witness -->
```sh
arhugula provider list
```

Output from a deployment with four providers enabled:

```text
provider     role      models (first = default)       access  state
claude_code  default   sonnet, haiku@low              cli     ready
ollama       fallback  llama3.2:3b                    ollama  ready
codex        enabled   gpt-6.1-sol@low, gpt-5.6-luna  cli     ready
antigravity  enabled   gemini-3.8-flash-low           cli     ready
anthropic    -         -                              sdk     not-signed-in
openai       -         -                              sdk     not-signed-in

models and thinking levels in detail: arhugula provider models
```

Model names change with the release of each tool and with your account.
So the names above are only an example: `arhugula provider models` shows what your sign-in offers.
The `@low` after a model is a thinking level, and [Choose a model and a thinking level](#choose-a-model-and-a-thinking-level) explains it.

The `role` column has four values:

- **`default`:** the provider that serves every step unless you route otherwise.
- **`fallback`:** the provider the runtime tries when the default fails.
- **`enabled`:** a provider you can route to or name with `--provider`.
- **`-`:** a provider that is not enabled.

## How the runtime calls a command-line provider

The three built-in command-line providers are tools that you sign in to yourself: Claude Code, Codex and Antigravity.
For each step, the runtime starts the tool once in *print mode*: the tool reads one prompt, prints one reply and exits.
The runtime never runs a shell, and it never reads or stores the tool's sign-in tokens.

Each call starts fresh, so an agent step has no session and no memory of earlier calls.
The Claude Code and Codex calls also switch off the tool's own tools.
The Antigravity call does not: read the note under it before you route work to it.
The exact command lines follow.
In them, `<model>` is the routed model and `<prompt>` is the step's prompt.

All three providers take and return text only, so the runtime refuses a step that lists tools for them: see [Choose how a step uses a tool](workflows.md#choose-how-a-step-uses-a-tool).

For Claude Code and Codex, the command the runtime starts is a small script that the kit generates: `<home>/bin/provider-claude_code` or `<home>/bin/provider-codex` (*kit extension*).
The script turns a model written `<model>@<level>` into the tool's own model and thinking-level options, and it passes every other argument through unchanged.
The kit removes from `<home>/bin` only the wrapper files it generated itself; a `provider-*` file of your own stays.
The command lines below are what the tool itself receives.

### Claude Code

```text
claude --print --output-format json --input-format text --no-session-persistence
       --safe-mode --strict-mcp-config --tools "" --permission-mode dontAsk
       --permission-prompts none --model <model>
```

The prompt goes in on standard input.
`--tools ""` gives the model no tools, and `--no-session-persistence` keeps no session.
`--strict-mcp-config` loads none of your Model Context Protocol (MCP) tool servers.

### Codex

```text
codex exec --json --ephemeral --skip-git-repo-check --sandbox read-only
      --ignore-user-config
      --disable shell_tool --disable unified_exec --disable code_mode_host
      --disable apps --disable plugins --disable remote_plugin
      --disable browser_use --disable view_image --disable computer_use
      --disable image_generation --disable multi_agent --disable skill_search
      --disable tool_suggest --disable in_app_browser
      --disable in_app_local_automation --disable hooks
      -c web_search="disabled" -m <model> -
```

The prompt goes in on standard input; the final `-` tells Codex to read it there.
The call ignores your Codex configuration, runs in a read-only sandbox and switches off every tool entry point by name.
From upstream commit `2e1ba1f764be27601441936692da2b6c30d61f7c` on, the runtime accepts Codex's reply.
Three runs with `--provider codex` at that commit were each served by Codex, and the model-call spans named `gpt-6.1-sol@low`, `gpt-6.1-sol@high` and `gpt-5.6-luna` with no error (*witnessed*).

### Antigravity

```text
agy --print <prompt> --model <model> --print-timeout <seconds>s --sandbox
```

The prompt is an argument.
`<seconds>` is the provider's call timeout, 120 by default.
`--sandbox` is the only restriction on this command line; `agy --help` describes it as "a sandbox with terminal restrictions".
No flag switches off the Antigravity tool's own tools (*upstream limit*).
Whether `--print --sandbox` runs those tools is not established, because no call was made to find out.

### What each call can see

| Provider | Working directory of the call | Environment of the call |
| --- | --- | --- |
| `claude_code` | a new, empty directory under `/tmp`, removed after the call | an allow-list only: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_*`, `TZ`, `TMPDIR`, the `XDG_*` directories, `CLAUDE_CONFIG_DIR`, and the proxy and certificate variables |
| `codex` | a new, empty directory under `/tmp`, removed after the call | yours, without the five credential variables |
| `antigravity` | the working directory of the run; the kit starts a run in the project's repository | yours, without the five credential variables |

The five credential variables are `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` and `GOOGLE_APPLICATION_CREDENTIALS`.
The runtime removes them because a tool that finds an API key uses it instead of your subscription sign-in.
That would turn a subscription call into a paid call without telling you.

None of this is a sandbox: each tool runs as your user.
The security page lists [what this isolation does not do](security-and-isolation.md#how-provider-calls-are-isolated).

## Sign in and check each provider

Sign in to each command-line tool yourself, in your terminal.
The table in [The providers](#the-providers) gives the sign-in command of each.

Then ask each enabled provider's own tool for its state:

```sh
arhugula provider check
```

Part of the output from a deployment where Claude Code is the default:

```text
claude_code (default): ready
    2.1.325 (Claude Code); signed in (claude.ai)
    command: ~/.local/bin/claude
    models: sonnet, haiku@low (default sonnet)
    note: Claude Code CLI gave no model list here, so these names could not be checked
ollama (fallback): ready
    reachable at http://127.0.0.1:11434; 10 models pulled
    models: llama3.2:3b (default llama3.2:3b)
codex (enabled): ready
    codex-cli 0.169.0; Logged in using ChatGPT
    command: /opt/homebrew/bin/codex
    models: gpt-6.1-sol@low, gpt-5.6-luna (default gpt-6.1-sol@low)
    note: Upstream marks the Codex profile HELD: the CLI's filesystem read exposure is an untested boundary. Sign in with `codex login` to use your ChatGPT subscription; an API key makes every call a paid call. Init does not propose Codex as the default provider when you selected another one.
antigravity (enabled): ready
    1.5.9; signed in (`agy models` answers)
    command: ~/.local/bin/agy
    models: gemini-3.8-flash-low (default gemini-3.8-flash-low)
```

Each provider's `models:` line shows the models you made available, and the default is the first one.

`arhugula provider check --all` also checks the providers that are not enabled.
The command reads only; it changes nothing.
It exits with code 3 when the default or the fallback provider is not usable, or when a stored model is no longer offered.
It prints a `fix:` line for each problem.

### What each state means

| State | Meaning | What to do |
| --- | --- | --- |
| `ready` | The tool is installed and signed in, or the server answers. | Nothing. |
| `paid-route` | The provider works, and every call is billed. | Accept it, or follow the `fix:` line to use a subscription. |
| `unverified` | The tool is installed, and it offers no sign-in check. | Run one workflow on it; the first run is the check. |
| `not-signed-in` | The tool is not signed in, or the API key is not stored. | Follow the `fix:` line. |
| `model-missing` | The Ollama server answers, but the configured model is not pulled. | Pull the model with the command in the `fix:` line. |
| `not-installed` | The tool is not on your `PATH`. | Install it with the command in the `fix:` line, then sign in. |
| `unreachable` | The server or the tool gave no answer. | Follow the `fix:` line. |

### How the check asks each provider

| Provider | What the check runs | What it reports |
| --- | --- | --- |
| `claude_code` | `claude auth status --json` | `ready` with the sign-in method, or `not-signed-in` with the fix "run `claude` once and sign in" |
| `codex` | `codex login status` | `ready`, `paid-route` when an API key is configured, or `not-signed-in` with the fix "run `codex login`" |
| `antigravity` | `agy models` | `ready` when the tool lists its models, or `not-signed-in` with the fix "run `agy` once and sign in" |
| `ollama` | the server's model list | `ready` with the number of pulled models, `unreachable`, or `model-missing` when the configured model is not pulled |
| `anthropic`, `openai` | a lookup of the key in the macOS keychain | `paid-route` when the key is there, `not-signed-in` when it is not |

The runtime makes its own sign-in check when a run starts, for the same three tools.
It runs `claude auth status --json`, `codex login status` and `agy models`.

## Know the Codex caveats

Read these before you route work to Codex.

- **Subscription sign-in is the default.** Sign in with `codex login` to use your ChatGPT subscription.
- **An API key makes every call a paid call.** When Codex has an API key configured, `arhugula provider check` reports `paid-route`. The fix it prints is `codex logout`, then `codex login`.
- **Upstream marks the profile HELD.** The Codex tool's filesystem read exposure is a boundary that upstream has not enforced or tested (*upstream limit*). The read-only sandbox and the disabled tools above are what the runtime sets; they are not a tested guarantee.
- **`init` does not propose Codex as the default.** When you selected another provider, `init` proposes that one. You can still choose Codex with `arhugula routing chain set codex`, and the command prints this caveat first.

## Use Antigravity

Antigravity is Google's command-line provider, and its command is `agy`.
The kit looks for `agy` on your `PATH`, then in `~/.local/bin` and `~/.gemini/bin`.
Start `agy` once to sign in, then enable it:

```sh
arhugula provider enable antigravity
```

`arhugula provider check` tests the Antigravity sign-in with `agy models`, as the runtime does, and reports `ready` or `not-signed-in`.
Its models are the ids that `agy models` lists, and each id carries its thinking level, for example `gemini-3.8-flash-low` (*witnessed*).
To change the level, make another id available, then choose it: `arhugula provider enable antigravity --model gemini-3.8-flash-high`, then `arhugula routing model set antigravity gemini-3.8-flash-high`.

## Run local models with Ollama

Ollama serves models on your own machine, so a run on it costs nothing and needs no account.
The runtime calls the Ollama server over HTTP, by default at `http://127.0.0.1:11434`.

At question 5, init proposes `llama3.2:3b`, and it offers to pull it when it is not pulled. The upstream examples name it.
Pull a model before you route to it:

```sh
ollama pull llama3.2:3b
```

| To do this | Run |
| --- | --- |
| See the models you have pulled | `ollama list` |
| See the models you made available to the kit | `arhugula provider models ollama` |
| Change the model that the `ollama` provider runs | `arhugula routing model set ollama <model>` |
| Set the address of the Ollama server | `arhugula provider ollama-host <url>` |
| Check that the server answers and the model is pulled | `arhugula provider check` |

When the configured model is not pulled, the check reports `model-missing` and prints the fix `ollama pull <model>`.
When the server does not answer, the check reports `unreachable` and prints the fix `ollama serve`.

`arhugula provider ollama-host` changes the address only when a server answers there.
When none answers, it stops with exit code 3 and the message `no Ollama server answers at <url>`, and nothing changes.

## Use a hosted API with a key in the keychain

Two providers are hosted APIs that bill each call: `anthropic` and `openai`.
Each needs an API key, and the kit stores the key only in the macOS keychain.
No key is ever written to a config file of the deployment.
When the keychain has no entry, the runtime also reads `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` from the environment of the run: [known gaps](reference/known-gaps.md) lists this.

Store the key first.
You type it at a hidden prompt, so it is never an argument and never in your shell history.

```sh
arhugula provider key set anthropic
```

Then enable the provider:

```sh
arhugula provider enable anthropic
```

| Provider | Keychain service | Keychain entry | Model init proposes |
| --- | --- | --- | --- |
| `anthropic` | `harness` | `anthropic_key` | `claude-haiku-4-5` |
| `openai` | `harness` | `openai_key` | `gpt-4o` |

With the key stored, `arhugula provider check` reports `paid-route` for the provider.
Remove a key with `arhugula provider key delete <name>`.

## Enable, disable and tune a provider

| To do this | Run |
| --- | --- |
| List every provider | `arhugula provider list` |
| Check the enabled providers | `arhugula provider check` |
| Enable a provider | `arhugula provider enable <name>` |
| Show the models each provider offers and the thinking levels | `arhugula provider models [<name>]` |
| Enable it with models of your choice; the first is the default | `arhugula provider enable <name> --model <model> [--model <model2>]` |
| Enable it with an executable that is not on `PATH` | `arhugula provider enable <name> --command <absolute-path>` |
| Disable a provider | `arhugula provider disable <name>` |
| Add or remove your own provider | `arhugula provider add <name> ...`, `arhugula provider remove <name>`: see [Add your own provider](#add-your-own-provider) |
| Change one setting of a command-line provider | `arhugula provider set <name> <key> <value>` |
| Remove your value for that setting | `arhugula provider unset <name> <key>` |

An enabled provider is available to routing and to `--provider`.
You cannot disable the default or the fallback provider: change the chain first, as [Change the routing](#change-the-routing) shows.

`provider disable`, `provider remove` and `provider enable --model` also refuse while a routing rule still names the provider, or a model that the change would drop.
For example, the message is `routing still binds to codex: role reviewer -> codex/gpt-5.6-luna`, and the fix is `arhugula routing role unbind reviewer first`.
For a workload class, the fix is `arhugula routing workload clear <class> first`.

`--command` takes the absolute path of an executable file.
The kit refuses a path that is not one, and it refuses its own wrapper `<home>/bin/provider-<name>`, because that wrapper would run itself.

A command stored as a bare name is looked up on `PATH`.
The kit refuses a name that is not on `PATH`.
The message is ``the command `<name>` set for <provider> is not on PATH``.
The fix is `arhugula provider enable <provider> --command <absolute-path-to-<command>>`.

`arhugula provider set` works on the three built-in command-line providers, once enabled.
It takes two keys:

| Key | Meaning | Value |
| --- | --- | --- |
| `timeout_seconds` | how long one call, or one sign-in check, may take | a number of seconds; the kit sets 120 |
| `auth_check` | whether the runtime checks sign-in when a run starts | `true` or `false` |

The runtime builds the command line of each of the three providers itself, as [How the runtime calls a command-line provider](#how-the-runtime-calls-a-command-line-provider) shows.
So the verb accepts no other key.

`arhugula provider unset` removes your value, and the kit's own value applies again.
It prints, for example, `claude_code: timeout_seconds is back to the value the kit generates`.
The kit sets `timeout_seconds` to 120, and it sets `auth_check` to `true`.

For example, give Claude Code twenty minutes for each call:

```sh
arhugula provider set claude_code timeout_seconds 1200
```

Two more limits bound the same call, and each applies on its own.
The step deadline `step_dispatch_timeout_seconds` bounds one whole step: the kit sets 960 seconds (*kit extension*).
The run limit `drain_timeout_seconds` bounds the whole run: the kit sets 3600 seconds (*kit extension*).
So a call gets its twenty minutes only when both are longer, and the step deadline of 960 seconds is shorter. Raise it, and the run limit with it, for example:

```sh
arhugula config set step_dispatch_timeout_seconds 1260
arhugula config set drain_timeout_seconds 3660
```

[The capability matrix](configure.md#capability-matrix) describes both keys.

Every one of these verbs regenerates the configs.
The runtime's own loader must accept the result, or the verb stops with exit code 4 and changes nothing.

## How routing picks a provider

The config's first fallback chain serves every step; `--provider` (and `--model`) override it for one run; a manifest's own model binding does not select the provider.
One manifest setting is the exception: a `model_binding` in `per_step_overrides` sends its step to the provider it names. See [Override one step in the manifest](#override-one-step-in-the-manifest).

A *fallback chain* is a default provider and model, followed by the fallbacks that the runtime tries when the default fails.
See the chain and everything bound over it:

<!-- witness -->
```sh
arhugula routing show
```

Output from a deployment with Claude Code as the default and Ollama as the fallback:

```text
The first fallback chain serves every step unless a run passes --provider.
  default:        claude_code/sonnet
  fallback:       ollama/llama3.2:3b  (cross family)

per-role bindings:
per-workload overrides:
retry policies:

embedding routing: off
```

The rule has these consequences:

- **A manifest's binding is a label.** The `default_model_binding` and `fallback_chain` tables in a manifest do not choose the provider. A manifest that names Ollama still runs on your default provider.
- **`--provider` is for one run.** `arhugula run <manifest> --provider ollama` sends every step of that run to Ollama first. The run prints an `override:` line that names the provider and model.
- **`--provider` brings its own model.** The kit pairs `--provider` with the default model that your deployment configured for that provider, and `--model` overrides it. The kit checks `--model` against the provider's own list and refuses a name it does not offer.

An override that fails still falls back along the chain.
`--provider` puts its provider in front of the whole chain, so a failed override falls back to the chain's default and then to its fallback.
So a `completed` status does not prove that the provider you named served the run.

When the provider you named failed and the fallback served the step, the run prints one more line after `ledger:`.
It names the provider and model that served, and why the one you named failed.
The line goes to standard error, so `--json` output stays clean.
This example is from a run with `--provider ollama --model no-such-model:1b` (*witnessed*):

```text
served by claude_code/sonnet, not by ollama/no-such-model:1b: ollama failed (TypeError: AsyncClient.chat() got an unexpected keyword argument 'max_tokens')
```

No such line means the provider you named served every step.

When more than one setting applies to a step, the runtime takes the most specific one.
Upstream states the order as `per-step > per-workload > per-role > routed > default`:

1. a per-step override, which is also what `--provider` and `--model` set
2. a per-workload override
3. a per-role binding
4. a routed choice, which exists only while the `embedding-routing` feature is on
5. the default, which is the first fallback chain

## Change the routing

Each binding takes `<provider>` or `<provider>:<model>`.
The provider must be enabled, and the model must be one you made available for it; if not, the verb stops with exit code 3 and names the fix.
For example, `routing model set claude_code opus` stops and prints `fix: arhugula provider enable claude_code --model sonnet --model haiku@low --model opus` (*witnessed*).

| To do this | Run |
| --- | --- |
| Show the routing | `arhugula routing show` |
| Choose the default provider | `arhugula routing chain set <binding>` |
| Choose the default and the fallback | `arhugula routing chain set <binding> --fallback <binding>` |
| Remove the fallback | `arhugula routing chain set <binding> --fallback none` |
| Change the model that a provider runs | `arhugula routing model set <provider> <model>[@<level>]` |
| Bind a role to a provider and model | `arhugula routing role bind <role> <binding>` |
| Remove a role's binding | `arhugula routing role unbind <role>` |
| Route one workload class | `arhugula routing workload override <class> <binding>` |
| Remove a workload class's override | `arhugula routing workload clear <class>` |
| Set a retry policy for a tool | `arhugula routing retry set <tool> --max-attempts <n>` |
| Remove a retry policy | `arhugula routing retry clear <tool>` |

Notes on these verbs:

- **The fallback is a different provider.** `routing chain set` refuses a fallback that equals the default. When you omit `--fallback`, the current fallback stays.
- **The chain records the model family.** `routing show` labels a fallback `same family` or `cross family`, by comparing its model family with the default's.
- **A workload class is one of four.** They are `pipeline-automation`, `software-engineering`, `research` and `content-creation`. Each manifest names its class.
- **A retry policy belongs to a tool name.** `--max-attempts` is the number of attempts before the fallback chain takes over. `--backoff` defaults to `full-jitter` and `--jitter` to `full`.

For example, make Claude Code the default with Ollama behind it:

```sh
arhugula routing chain set claude_code:sonnet --fallback ollama
```

## Choose a model and a thinking level

A *thinking level* says how much a model reasons before it answers.
Model names change with the release of each tool and with your account.
So the kit never fixes one: `arhugula provider models` shows what your sign-in offers, and the kit takes those names from each tool's own list.
A stored model that the tool no longer offers is reported by `arhugula provider check` and by `doctor` (check P6), with the command that repairs it.
The kit never replaces such a model silently (*witnessed*).

Make a model available first, and name every model you want kept; the first is the provider's default:

```sh
arhugula provider enable claude_code --model sonnet --model haiku@low
```

Then choose where it applies.
Pick the row that matches your task:

| You want a model for | Run, or write | Notes |
| --- | --- | --- |
| One step or one sub-agent. Workers, reviewers and the children of a topology are steps. | In the workflow file: `per_step_overrides = { "<step-id>" = { step_id = "<step-id>", model_binding = { provider = "<provider>", model = "<model>" } } }` | The most specific setting (*witnessed*, with a thinking level on each of two steps). See [Override one step in the manifest](#override-one-step-in-the-manifest). |
| One kind of work (a workload class) | `arhugula routing workload override <class> <provider>:<model>` | The classes are listed under [Change the routing](#change-the-routing). |
| One agent role | `arhugula routing role bind <role> <provider>:<model>` | A worker's role is its step id. |
| The deployment default and fallback | `arhugula routing chain set <provider>:<model> --fallback <provider>:<model>` | `arhugula routing model set <provider> <model>` changes only the model. Init question 5 sets the models at the start. |
| One run | `arhugula run <manifest> --provider <provider> --model <model>` | Only this run. |

The most specific setting wins: a step, then a workload class, then a role, then the default chain.
[How routing picks a provider](#how-routing-picks-a-provider) states the full order, and [the workflows page](workflows.md#the-per_step_overrides-table) describes the manifest field.

How you write the thinking level depends on the provider:

| Provider | Where the level goes | Example |
| --- | --- | --- |
| `claude_code` | after the model, as `<model>@<level>`: low, medium, high, xhigh or max (*kit extension*) | `sonnet@high` |
| `codex` | after the model, as `<model>@<level>`; the levels differ by model, and `arhugula provider models codex` lists them (*kit extension*) | `gpt-6.1-sol@low` |
| `antigravity` | inside the model id | `gemini-3.8-flash-low` |
| `anthropic`, `openai`, `ollama` | in the `params` of one step in the manifest; no deployment-wide or routing-level setting exists (*upstream limit*) | see [the workflows page](workflows.md#the-steps-entries) |

With no level, the tool uses its own default.
The kit refuses `@level` on `antigravity`, `anthropic`, `openai` and `ollama`.
It also refuses a level on a listed model that has no levels, and a model or level that holds a space or starts with `-`.
In the levels column of `arhugula provider models`, a listed model without levels shows `none`.
For example (*witnessed*):

```text
arhugula: Ollama (local models) takes no `@level` on a model (got `llama3.2:3b@high`): its thinking is set per step, in the step's `params` in a workflow manifest (see docs/workflows.md)
  fix: arhugula provider models ollama
```

The level reaches the tool as its own option.
A run on `--model haiku@low` made the Claude CLI receive `--model haiku --effort low` (*witnessed*).
A run on `gpt-6.1-sol@low` made the Codex CLI receive `-m gpt-6.1-sol -c 'model_reasoning_effort="low"'` (*witnessed*).
Moving the default with `arhugula routing model set claude_code haiku@high` made the next plain run use `haiku@high` (*witnessed*).

## Add your own provider

A custom provider is any command that reads a prompt and prints a reply.
The runtime runs it through its `generic-command` kind: the command, then the arguments you give, with the prompt on standard input.
The kit ships a stand-in for trying this, `examples/providers/echo-provider`: it calls no model and prints one fixed, marked reply.
Add it:

```sh
arhugula provider add local_echo --command <home>/kit/examples/providers/echo-provider '--args=--model {model}' --auth-args=--version --model echo-1
```

Write a value that starts with `-` as `--args=...`, with the equals sign; otherwise the parser reads it as an option (*witnessed*).
`{model}` becomes the step's model.
The provider is enabled at once and behaves like a built-in one in `provider`, `routing` and `--provider`:

```sh
arhugula run minimal.toml --provider local_echo
```

Remove it with `arhugula provider remove local_echo`.
You cannot remove the default or the fallback provider: change the chain first.
`arhugula provider add --help` lists the other options, such as `--prompt-transport` and `--response-format`.
A custom command receives only `{model}` and `{prompt}`, so put a thinking option in its `--args`.

A custom provider is a text provider like the built-in command-line ones: a step that lists tools is refused for it.
The command itself can still be an agent that acts: see [Run an agent that acts with its own tools](#run-an-agent-that-acts-with-its-own-tools).

The same route reaches an OpenAI-compatible server (LM Studio, vLLM, OpenRouter) through a command of yours, because the runtime has no setting for such an endpoint (*upstream limit*).

## Run an agent that acts with its own tools

This section is for the operator who wants a subscription agent, such as Claude Code, to edit files, run commands or use its own tool servers inside a workflow step.
After reading it you can add such an agent as a custom provider, run a step on it, and say what controls it.
Read the trade first: this route removes the harness's gates and records.

### Know why the built-in providers cannot act

The built-in providers do not let an agent act on its own decision, except possibly Antigravity.
This table shows how each one is held back:

| Provider | How its tools are controlled | Working directory |
| --- | --- | --- |
| `claude_code` | Switched off with `--tools ""`, together with `--permission-mode dontAsk` and `--permission-prompts none`. | A new empty directory under `/tmp`, removed after the call. |
| `codex` | `--sandbox read-only`, every tool entry point switched off with `--disable`, and `-c web_search="disabled"`. The runtime also refuses a `command_execution`, `mcp_tool_call`, `file_change`, `web_search` or unknown item in Codex's output, with the message "tool use is not supported on this route". | A new empty directory under `/tmp`, removed after the call. |
| `antigravity` | `--sandbox` only. No flag switches its tools off, and the runtime refuses nothing after the call. Whether `--print --sandbox` runs its own tools is not established. | The directory the run starts in, which is the project's repository. |

The arguments of these three providers are fixed in the runtime's code.
`arhugula provider set` changes only `timeout_seconds` and `auth_check`, so you cannot loosen a built-in provider.
A custom provider is the way to run an agent that acts.

### Know the trade before you add an agent

An agent behind a custom provider acts, and the harness does not control how.

- **The harness sees the step and its reply, and nothing else.** It does not see, gate, sandbox or record the single tool calls that the agent makes. No gate asks you, and no span or audit entry records them (read in the code, not run).
- **The agent's own permission settings are the only control.** They are the CLI's permission mode, its allowed-tools and disallowed-tools options, and its own MCP configuration. These options belong to the CLI: read its help, for example `claude --help`.
- **The agent runs in the project directory, as you.** The runtime starts the command in the directory it runs in, which is the project's repository. The command uses the tool's own sign-in, which is yours. The harness adds no sandbox.
- **A mode that skips every permission check gives the agent your full access to the project directory.** The Claude Code help describes `--dangerously-skip-permissions` as "Bypass all permission checks" and recommends it "only for sandboxes with no internet access". Treat the permission mode `bypassPermissions` with the same care.

### Add the agent and run a step on it

Do these steps in order.
The run writes a file into your project, so use a project whose files you can restore.

1. **Add the agent as a provider.** The command that follows adds Claude Code with the permission mode `acceptEdits`. `$(command -v claude)` supplies the absolute path that `--command` needs, and `--args=` carries the arguments in one string. `{model}` becomes the step's model.

   ```sh
   arhugula provider add claude_agent --command "$(command -v claude)" --args='--print --model {model} --permission-mode acceptEdits --output-format text' --model sonnet --family anthropic
   ```

   The command answered (*witnessed*):

   ```text
   added and enabled claude_agent; models: sonnet (default sonnet).
   check it:   arhugula provider check
   try it:     arhugula run minimal.toml --provider claude_agent
   ```

2. **Copy the example workflow into the project.** The step of `examples/workflows/agent-acts.toml` asks the agent to create a file named `agent-proof.txt` with one line in it.

   ```sh
   cp <home>/kit/examples/workflows/agent-acts.toml <project-path>/workflows/
   ```

3. **Run it on the new provider.** Pass `--provider`, because the manifest's own chain is a label and does not choose the provider.

   ```sh
   arhugula run agent-acts.toml --project <project> --provider claude_agent
   ```

4. **Check the result.** The file that the agent made is in your project directory.

   ```sh
   cat <project-path>/agent-proof.txt
   ```

The run printed this (*witnessed*):

```text
override:  every step dispatches first to claude_agent/sonnet; the config's fallback chain applies if that candidate fails
status:    completed
```

The step completed, and the model-call span names `claude_agent`.
The file existed in the project directory afterwards, and it held the line `written by an agent` (*witnessed*).
The step must list no tools, as the example does with `tools = []`, because a custom provider is a text provider.
The agent uses its own tools instead.

### Set what the agent may do

The options of the agent are the CLI's own, so read its help for your version.
These names come from `claude --help`:

| Option | What the help says |
| --- | --- |
| `--permission-mode <mode>` | The permission mode for the session. The choices are `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk` and `plan`. |
| `--allowedTools`, `--allowed-tools <tools...>` | A comma or space separated list of tool names to allow. |
| `--disallowedTools`, `--disallowed-tools <tools...>` | A comma or space separated list of tool names to deny. |
| `--tools <tools...>` | The list of available tools from the built-in set. `""` disables all tools. |
| `--mcp-config <configs...>` | Loads MCP servers from JSON files or strings. |

Put the options you choose in the provider's `--args`.
Only Claude Code was run this way.
For another agent CLI, the same route applies, and nothing on this page was run for it.

## Review with a second model

A review is worth more when another model does it.
The harness has no separate reviewer feature: a reviewer is a step, and routing sends that step to another provider.
You have two ways to do it.

### Bind the reviewer's role

Bind a role to a provider for the whole deployment:

```sh
arhugula routing role bind <role> ollama:llama3.2:3b
```

In the fan-out topologies, each worker step runs under a role named after its step id.
So to bind a worker, use its step id as `<role>`.
A manifest can also give any step a role, with `agent_role` in that step's `per_step_overrides` entry.

### Override one step in the manifest

Name the model for one step in the manifest's `per_step_overrides` table:

```toml
per_step_overrides = { "evaluate-tagline" = { step_id = "evaluate-tagline", model_binding = { provider = "ollama", model = "llama3.2:3b" } } }
```

A per-step override is the most specific setting, so it wins over the chain.
This is the one manifest setting that does select a provider.
The [workflows page](workflows.md) explains every field of a manifest.

The example `examples/workflows/two-agents.toml` binds step one to `claude_code` with `haiku@low` and step two to `codex` with `gpt-6.1-sol@medium`.
Both steps ran, and the two model-call spans named exactly those models (*witnessed*).
Make both models available first, as the comments in the file show.

## Know what a run costs

The three built-in command-line providers use your subscription sign-in, and the runtime never prices them.
A run on `claude_code`, `codex` or `antigravity` writes no cost entry.
Leaving these calls unpriced is by design (*upstream limit*).

Such a run still writes its step entries to the project's state ledger, and it writes no audit entry (*witnessed*).
The `ledger:` line of a run prints the hash of the newest audit entry, so that hash is the same as before the run.
`arhugula status` shows the head hash of the whole ledger, and that hash changes.
Upstream issue #1743 covers the missing cost and audit entries.

| Provider | What a call costs you |
| --- | --- |
| `claude_code`, `codex`, `antigravity` | part of your subscription's allowance; the runtime records no price |
| `codex` with an API key | a billed call; `arhugula provider check` reports `paid-route` |
| `ollama` | nothing; the run result reports a cost of `0.0` |
| `anthropic`, `openai` | a billed call |

To see what a run recorded, read the [observability page](observability.md).

## Sources

Kit modules:

- `lib/arhugula_kit/providers.py`
- `lib/arhugula_kit/modelwrap.py`
- `lib/arhugula_kit/servedby.py`
- `examples/providers/echo-provider`
- `examples/workflows/two-agents.toml`
- `examples/workflows/agent-acts.toml`
- `lib/arhugula_kit/verbs_config.py`
- `lib/arhugula_kit/render.py`
- `lib/arhugula_kit/questions.py`
- `lib/arhugula_kit/docgen.py`

Upstream sources, relative to the home:

- `upstream/harness-runtime/src/harness_runtime/lifecycle/external_cli_provider.py`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/llm_dispatch.py`: the text-only refusal of a step that lists tools
- `upstream/harness-runtime/src/harness_runtime/cli/app.py`
- `upstream/harness-cp/src/harness_cp/per_role_catalog.py`
- `upstream/harness-cp/src/harness_cp/workflow_manifest_entry.py`
- `upstream/docs/how-to-operate-runtime.md`
- `upstream/docs/how-to-deploy.md`
- `upstream/examples/README.md`

The options of Claude Code in [Set what the agent may do](#set-what-the-agent-may-do) come from its own help, `claude --help`.
