# Choose providers and routing

This page is for the operator.
After reading it, you can sign in to each provider, check it, and decide which provider and model serve which step.

A *provider* is a source of model replies: a signed-in command-line tool, the local Ollama server, or a hosted API.
Nothing here is installed for you: see [the dependencies](install.md#dependencies) for what each provider needs.

## On this page

- [The providers](#the-providers)
- [How the runtime calls a command-line provider](#how-the-runtime-calls-a-command-line-provider)
- [Sign in and check each provider](#sign-in-and-check-each-provider)
- [Know the Codex caveats](#know-the-codex-caveats)
- [Use Antigravity where Gemini refuses your account](#use-antigravity-where-gemini-refuses-your-account)
- [Run local models with Ollama](#run-local-models-with-ollama)
- [Use a hosted API with a key in the keychain](#use-a-hosted-api-with-a-key-in-the-keychain)
- [Enable, disable and tune a provider](#enable-disable-and-tune-a-provider)
- [How routing picks a provider](#how-routing-picks-a-provider)
- [Change the routing](#change-the-routing)
- [Review with a second model](#review-with-a-second-model)
- [Know what a run costs](#know-what-a-run-costs)
- [Sources](#sources)

## The providers

The runtime can dispatch to seven providers.
The program generates this table from its own catalogue.

<!-- BEGIN GENERATED: providers -->
| Name | Provider | Reached through | Default model | Install | Sign in |
| --- | --- | --- | --- | --- | --- |
| `claude_code` | Claude Code CLI | its command-line tool, signed in by you | `sonnet` | `curl -fsSL https://claude.ai/install.sh \| bash`<br>`brew install --cask claude-code` | `claude` |
| `ollama` | Ollama (local models) | the local Ollama server | `llama3.2:3b` | `brew install ollama` | `brew services start ollama` |
| `codex` | Codex CLI | its command-line tool, signed in by you | `gpt-5` | `brew install --cask codex`<br>`npm install -g @openai/codex` | `codex login` |
| `gemini` | Gemini CLI | its command-line tool, signed in by you | `gemini-2.5-flash` | `brew install gemini-cli`<br>`npm install -g @google/gemini-cli` | `gemini` |
| `antigravity` | Antigravity CLI (agy) | its command-line tool, signed in by you | `Gemini 3.5 Flash (Low)` | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` | `agy` |
| `anthropic` | Anthropic API (key in the keyring; paid) | a hosted API, with a key in the macOS keychain | `claude-haiku-4-5` | nothing to install | `arhugula provider key set anthropic` |
| `openai` | OpenAI API (key in the keyring; paid) | a hosted API, with a key in the macOS keychain | `gpt-4o` | nothing to install | `arhugula provider key set openai` |
<!-- END GENERATED: providers -->

List the providers of your deployment, with the role, model and state of each:

<!-- witness -->
```sh
arhugula provider list
```

Output from a deployment with five providers enabled:

```text
provider     role      model                   access  state
claude_code  default   sonnet                  cli     ready
ollama       fallback  llama3.2:3b             ollama  ready
codex        enabled   gpt-5                   cli     ready
gemini       enabled   gemini-2.5-flash        cli     unverified
antigravity  enabled   Gemini 3.5 Flash (Low)  cli     ready
anthropic    -         -                       sdk     not-signed-in
openai       -         -                       sdk     not-signed-in
```

The `role` column has four values:

- **`default`:** the provider that serves every step unless you route otherwise.
- **`fallback`:** the provider the runtime tries when the default fails.
- **`enabled`:** a provider you can route to or name with `--provider`.
- **`-`:** a provider that is not enabled.

## How the runtime calls a command-line provider

The four command-line providers are tools that you sign in to yourself: Claude Code, Codex, Gemini and Antigravity.
For each step, the runtime starts the tool once in *print mode*: the tool reads one prompt, prints one reply and exits.
The runtime never runs a shell, and it never reads or stores the tool's sign-in tokens.

Each call starts fresh, so an agent step has no session and no memory of earlier calls.
The Claude Code and Codex calls also switch off the tool's own tools.
The Antigravity and Gemini calls do not: read the note under each before you route work to them.
The exact command lines follow.
In them, `<model>` is the routed model and `<prompt>` is the step's prompt.

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

### Antigravity

```text
agy --print <prompt> --model <model> --print-timeout <seconds>s --sandbox
```

The prompt is an argument.
`<seconds>` is the provider's call timeout, 120 by default.
`--sandbox` is the only restriction on this command line; `agy --help` describes it as "a sandbox with terminal restrictions".
No flag switches off the Antigravity tool's own tools (*upstream limit*).

### Gemini

```text
gemini --skip-trust -m <model> -p <prompt>
```

The prompt is an argument.
`--skip-trust` makes the Gemini tool trust the directory it runs in, which is your project's repository.
No flag restricts the Gemini tool's own tools (*upstream limit*).

### What each call can see

| Provider | Working directory of the call | Environment of the call |
| --- | --- | --- |
| `claude_code` | a new, empty directory under `/tmp`, removed after the call | an allow-list only: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_*`, `TZ`, `TMPDIR`, the `XDG_*` directories, `CLAUDE_CONFIG_DIR`, and the proxy and certificate variables |
| `codex` | a new, empty directory under `/tmp`, removed after the call | yours, without the five credential variables |
| `antigravity` | the working directory of the run; the kit starts a run in the project's repository | yours, without the five credential variables |
| `gemini` | the working directory of the run; the kit starts a run in the project's repository | yours, without the five credential variables |

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
ollama (fallback): ready
    reachable at http://127.0.0.1:11434; 10 models pulled
codex (enabled): ready
    codex-cli 0.169.0; Logged in using ChatGPT
    command: /opt/homebrew/bin/codex
    note: Upstream marks the Codex profile HELD: the CLI's filesystem read exposure is an untested boundary. Sign in with `codex login` to use your ChatGPT subscription; an API key makes every call a paid call. Codex is never the default primary.
gemini (enabled): unverified
    0.66.0; this CLI offers no sign-in check, so the first run is the check
    command: /opt/homebrew/bin/gemini
    note: The Gemini CLI refuses individual Google accounts at this release and points to Antigravity. The runtime dispatches correctly; the CLI itself declines.
antigravity (enabled): ready
    1.5.9; signed in (`agy models` answers)
    command: ~/.local/bin/agy
...
```

`arhugula provider check --all` also checks the providers that are not enabled.
The command reads only; it changes nothing.
It exits with code 3 when the default or the fallback provider is not usable, and it prints a `fix:` line for each problem.

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
| `gemini` | the tool's `--version` | `unverified` when the tool answers, `unreachable` when it does not |
| `ollama` | the server's model list | `ready` with the number of pulled models, `unreachable`, or `model-missing` when the configured model is not pulled |
| `anthropic`, `openai` | a lookup of the key in the macOS keychain | `paid-route` when the key is there, `not-signed-in` when it is not |

The runtime makes its own sign-in check when a run starts, for three tools.
It runs `claude auth status --json`, `codex login status` and `agy models`.
It makes no such check for Gemini.

## Know the Codex caveats

Read these before you route work to Codex.

- **Subscription sign-in is the default.** Sign in with `codex login` to use your ChatGPT subscription.
- **An API key makes every call a paid call.** When Codex has an API key configured, `arhugula provider check` reports `paid-route`. The fix it prints is `codex logout`, then `codex login`.
- **Upstream marks the profile HELD.** The Codex tool's filesystem read exposure is a boundary that upstream has not enforced or tested (*upstream limit*). The read-only sandbox and the disabled tools above are what the runtime sets; they are not a tested guarantee.
- **`init` does not propose Codex as the default.** When you selected another provider, `init` proposes that one. You can still choose Codex with `arhugula routing chain set codex`, and the command prints this caveat first.

## Use Antigravity where Gemini refuses your account

At this release, the Gemini command-line tool refuses individual Google accounts and points you to Antigravity.
The runtime dispatches to the Gemini tool correctly; the tool itself declines the call.

Antigravity is the other Google tool, and its command is `agy`.
The kit looks for `agy` on your `PATH`, then in `~/.local/bin` and `~/.gemini/bin`.
Start `agy` once to sign in, then enable it:

```sh
arhugula provider enable antigravity
```

`arhugula provider check` tests the Antigravity sign-in with `agy models`, as the runtime does, and reports `ready` or `not-signed-in`.
The Gemini tool offers no sign-in check, so Gemini shows as `unverified` and its first run is the real check.

## Run local models with Ollama

Ollama serves models on your own machine, so a run on it costs nothing and needs no account.
The runtime calls the Ollama server over HTTP, by default at `http://127.0.0.1:11434`.

The default model is `llama3.2:3b`, and the upstream examples name it.
Pull a model before you route to it:

```sh
ollama pull llama3.2:3b
```

| To do this | Run |
| --- | --- |
| See the models you have pulled | `ollama list` |
| Change the model that the `ollama` provider runs | `arhugula routing model set ollama <model>` |
| Check that the server answers and the model is pulled | `arhugula provider check` |

When the configured model is not pulled, the check reports `model-missing` and prints the fix `ollama pull <model>`.
When the server does not answer, the check reports `unreachable` and prints the fix `ollama serve`.

## Use a hosted API with a key in the keychain

Two providers are hosted APIs that bill each call: `anthropic` and `openai`.
Each needs an API key, and the key lives only in the macOS keychain.
No key is ever written to a config file of the deployment.

Store the key first.
You type it at a hidden prompt, so it is never an argument and never in your shell history.

```sh
arhugula provider key set anthropic
```

Then enable the provider:

```sh
arhugula provider enable anthropic
```

| Provider | Keychain service | Keychain entry | Default model |
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
| Enable it with a model of your choice | `arhugula provider enable <name> --model <model>` |
| Enable it with an executable that is not on `PATH` | `arhugula provider enable <name> --command <absolute-path>` |
| Disable a provider | `arhugula provider disable <name>` |
| Change one setting of a command-line provider | `arhugula provider set <name> <key> <value>` |
| Remove your value for that setting | `arhugula provider unset <name> <key>` |

An enabled provider is available to routing and to `--provider`.
You cannot disable the default or the fallback provider: change the chain first, as [Change the routing](#change-the-routing) shows.

`arhugula provider set` works on the four command-line providers, once enabled.
It takes six keys, and three of them change nothing for these providers:

| Key | Meaning | Value | Takes effect on |
| --- | --- | --- | --- |
| `timeout_seconds` | how long one call, or one sign-in check, may take | a number of seconds; the kit sets 120 | all four |
| `auth_check` | whether the runtime checks sign-in when a run starts | `true` or `false` | all four; `gemini` also needs `auth_args` |
| `auth_args` | the arguments of the sign-in check | a JSON list of strings | `gemini` only, with `auth_check` set to `true` |
| `args` | the arguments of a generic command's call | a JSON list of strings | none of the four |
| `response_format` | how a generic command answers | `text`, `json` or `jsonl` | none of the four |
| `prompt_transport` | how a generic command gets the prompt | `stdin` or `arg` | none of the four |

The runtime builds the command line of each of the four providers itself, as [How the runtime calls a command-line provider](#how-the-runtime-calls-a-command-line-provider) shows.
It reads `args`, `response_format` and `prompt_transport` only for its generic-command kind of provider, which the kit does not generate (*upstream limit*).
The runtime's loader still accepts the three keys, so the verb succeeds and the calls stay the same.

`arhugula provider unset` removes your value, and the kit's own value applies again.
The kit sets `timeout_seconds` to 120, and it sets `auth_check` to `true` for Claude Code, Codex and Antigravity and to `false` for Gemini.

For example, give Claude Code five minutes for each call:

```sh
arhugula provider set claude_code timeout_seconds 300
```

Every one of these verbs regenerates the configs.
The runtime's own loader must accept the result, or the verb stops with exit code 4 and changes nothing.

## How routing picks a provider

The config's first fallback chain serves every step; `--provider` (and `--model`) override it for one run; a manifest's own model binding does not select the provider.

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
- **`--provider` brings its own model.** The kit pairs `--provider` with the model that your deployment configured for that provider, and `--model` overrides it.

An override that fails still falls back along the chain.
So a `completed` status does not prove that the provider you named served the run: read the `override:` line and the run's log.

When more than one setting applies to a step, the runtime takes the most specific one.
Upstream states the order as `per-step > per-workload > per-role > routed > default`:

1. a per-step override, which is also what `--provider` and `--model` set
2. a per-workload override
3. a per-role binding
4. a routed choice, which exists only while the `embedding-routing` feature is on
5. the default, which is the first fallback chain

## Change the routing

Each binding takes `<provider>` or `<provider>:<model>`.
The provider must be enabled; if it is not, the verb stops with exit code 3 and names the fix.

| To do this | Run |
| --- | --- |
| Show the routing | `arhugula routing show` |
| Choose the default provider | `arhugula routing chain set <binding>` |
| Choose the default and the fallback | `arhugula routing chain set <binding> --fallback <binding>` |
| Remove the fallback | `arhugula routing chain set <binding> --fallback none` |
| Change the model that a provider runs | `arhugula routing model set <provider> <model>` |
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

## Know what a run costs

The four command-line providers use your subscription sign-in, and the runtime never prices them.
A run on `claude_code`, `codex`, `gemini` or `antigravity` writes no cost entry.
The ledger head hash that such a run reports is the same as before the run (*upstream limit*, by design).

| Provider | What a call costs you |
| --- | --- |
| `claude_code`, `codex`, `gemini`, `antigravity` | part of your subscription's allowance; the runtime records no price |
| `codex` with an API key | a billed call; `arhugula provider check` reports `paid-route` |
| `ollama` | nothing; the run result reports a cost of `0.0` |
| `anthropic`, `openai` | a billed call |

To see what a run recorded, read the [observability page](observability.md).

## Sources

Kit modules:

- `lib/arhugula_kit/providers.py`
- `lib/arhugula_kit/verbs_config.py`
- `lib/arhugula_kit/render.py`
- `lib/arhugula_kit/questions.py`
- `lib/arhugula_kit/docgen.py`

Upstream sources, relative to the home:

- `upstream/harness-runtime/src/harness_runtime/lifecycle/external_cli_provider.py`
- `upstream/harness-runtime/src/harness_runtime/cli/app.py`
- `upstream/harness-cp/src/harness_cp/per_role_catalog.py`
- `upstream/harness-cp/src/harness_cp/workflow_manifest_entry.py`
- `upstream/docs/how-to-operate-runtime.md`
- `upstream/docs/how-to-deploy.md`
- `upstream/examples/README.md`
