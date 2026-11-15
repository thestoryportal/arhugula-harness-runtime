# Write what a workflow's agents do

This page is for a person or an agent who writes what the agents of a workflow do: step payloads, prompts, skills and validators.
After reading it you can copy the kit's example files, change them, and test each one without calling a provider.

It applies to the upstream commit named in the kit's `PIN` file.

Other pages cover the neighbouring tasks:

- **Manifests and topologies:** read [Run and write workflows](workflows.md) for the whole manifest and the six topologies.
- **Lifecycle commands:** read [Manage prompts, skills and validators](prompts-skills-validators.md) to list, approve, compare and remove what you write here.
- **Runtime settings:** read [Configure the runtime](configure.md) for every setting behind these commands.

## On this page

- [What an agent in a workflow sees](#what-an-agent-in-a-workflow-sees)
- [Why `CLAUDE.md` and `AGENTS.md` do not reach the agent](#why-claudemd-and-agentsmd-do-not-reach-the-agent)
- [Write a step payload for your provider family](#write-a-step-payload-for-your-provider-family)
- [Write a prompt version and select it](#write-a-prompt-version-and-select-it)
- [Write a skill](#write-a-skill)
- [Write a validator class](#write-a-validator-class)
- [Test your work without calling a provider](#test-your-work-without-calling-a-provider)
- [Sources](#sources)

## What an agent in a workflow sees

An agent in a workflow is one model call for one step.
The runtime builds the whole input of that call from the sources in this table, and from nothing else.

| Source | What it adds to the call | Where you write it |
| --- | --- | --- |
| The manifest's messages | The messages of the step, as you wrote them | `[steps.step_payload]` in the manifest |
| The active prompt version | The system prompt | A text file, stored with `arhugula prompt author` |
| Each activated skill | The skill's text, added to the system prompt after the prompt version | Two files in the project's `.agents/skills/` directory |
| The memory packet | A short read-only summary of what the harness remembers, added after the skills | Nothing: the runtime writes it when memory is on ([Memory](memory.md)) |
| The previous step's output | One extra user message that starts with `Upstream step output:` | Nothing: the runtime adds it when the feature `data-flow` is on |

A command-line provider receives all of this as one text.
The text has one part per source, each part starts with its role, and a blank line separates the parts:

```text
system:
<the active prompt version, then the skills, then the memory packet>

user:
<the content of your first message>
```

When the previous step's output is present, its `user:` part comes after the `system:` part and before your own messages.

## Why `CLAUDE.md` and `AGENTS.md` do not reach the agent

The runtime never sends a `CLAUDE.md` or `AGENTS.md` file from your project to an agent in a workflow.
Each step is one isolated provider call that starts, answers once and ends.
The call continues no earlier session.
For Claude Code and Codex, the runtime also switches the program's own tools off.

The table shows how the runtime starts each provider.
It comes from the arguments in `upstream/harness-runtime/src/harness_runtime/lifecycle/external_cli_provider.py`.

| Provider | How the runtime starts the call | Working directory of the call |
| --- | --- | --- |
| `claude_code` | `--print --no-session-persistence --safe-mode --strict-mcp-config --tools ""`, with the prompt on standard input | A new empty directory, removed after the call |
| `codex` | `exec --ephemeral --sandbox read-only --ignore-user-config`, with its tool features switched off and the prompt on standard input | A new empty directory, removed after the call |
| `gemini` | `--skip-trust -m <model> -p <prompt>` | The project repository |
| `antigravity` | `--print <prompt> --model <model> --print-timeout <duration> --sandbox` | The project repository |
| `ollama`, `anthropic`, `openai` | One API request that carries the messages | None: no file is read |

The runtime also reduces the environment of each command-line call.
Claude Code receives a short fixed list of variables, such as `PATH` and `HOME`.
The other command-line providers receive your environment without the provider API keys.

The runtime passes no context file to the Gemini CLI or to Antigravity.
Those two calls start in the project repository, because the runtime does not move them.
The kit has not tested whether either program reads a file from that directory by itself.

So write everything an agent must know into the manifest's messages, a prompt version or a skill.
Your `CLAUDE.md` and `AGENTS.md` files still guide an agent CLI that you run yourself in the project: see [Work with agent CLIs](agents.md).

## Write a step payload for your provider family

A step payload has three keys: `messages`, `tools` and `params`.
The runtime hands `params` to the provider's own call, so its shape depends on the provider family that serves the step.

Compare the two smallest upstream examples.
This is the step of `upstream/examples/minimal.toml`, written for the Anthropic API:

```toml
[[steps]]
step_id = "s1"
step_kind = "inference-step"

[steps.step_payload]
messages = [{ role = "user", content = "Reply with the single word: ok" }]
tools = []
params = { max_tokens = 8 }
```

This is the step of `upstream/examples/ollama-first.toml`, written for Ollama:

```toml
[[steps]]
step_id = "ask-local-model"
step_kind = "inference-step"

[steps.step_payload]
messages = [{ role = "user", content = "Reply with the single word: OK" }]
tools = []
params = { options = { num_predict = 8 } }
```

Use this table to choose the shape of `params`.

| Provider family | Providers | Shape of `params` |
| --- | --- | --- |
| Hosted API | `anthropic`, `openai` | `{ max_tokens = <number> }`. The Anthropic API requires `max_tokens`. |
| Ollama | `ollama` | `{ options = { num_predict = <number> } }`. The keys go to Ollama's chat call. |
| Command-line | `claude_code`, `codex`, `gemini`, `antigravity` | Not used: the call sends text only. Keep `tools = []`, because the runtime refuses a command-line step that lists tools. |

Three rules decide which shape you need:

- **Routing rule:** the config's first fallback chain serves every step; `--provider` (and `--model`) override it for one run; a manifest's own model binding does not select the provider.
- **Write for that provider:** run `arhugula routing show` to see the chain, then write `params` for the family at its head.
- **Keep one system prompt:** when a prompt version is active, leave the system prompt out of the payload. The runtime fails the step with `RT-FAIL-PROMPT-INJECTION-CONFLICT` when it finds two.

To start a manifest, let the kit derive one for your default provider (*kit extension*):

```sh
arhugula workflow new single-threaded-linear --name my-first
```

The command writes `<project-path>/workflows/my-first.toml` with `params` in the shape of your default provider's family.
Then edit the messages.

## Write a prompt version and select it

A prompt version is a text that the runtime uses as the system prompt.
You write the text in any file; a project has no fixed prompts directory.
The kit stores the text in the configuration when you author it.

1. Copy an example to a file of your own, for example `<project-path>/system-prompt.md`, and change it. The kit ships two: `<home>/kit/examples/prompts/terse-v1.md` and `terse-v2.md`. Each holds one line, for example:

   ```text
   You are a terse assistant. Reply in UPPERCASE ENGLISH only.
   ```

2. Author the version under a label of your choice:

   ```sh
   arhugula prompt author v1 --file <project-path>/system-prompt.md --project <project>
   ```

3. Author a changed text under a second label when you need one. The first version you author becomes the active one. A later version stays inactive until you activate it:

   ```sh
   arhugula prompt activate v2 --project <project>
   ```

4. To use a version for one workload class only, select it for that class:

   ```sh
   arhugula prompt select research v2 --project <project>
   ```

The workload class of a workflow is the `workload_class` line of its manifest.
A selection for that class wins over the active version.
[Manage prompts, skills and validators](prompts-skills-validators.md#manage-prompt-versions) explains versions, selection and approval in full.

## Write a skill

A skill is a named text that the runtime adds to the system prompt when a hook activates it.
A skill is two files with the same name.

| File | Content |
| --- | --- |
| `<name>.skill.json` | One JSON object that describes the skill |
| `<name>.SKILL.md` | The text the agent receives |

The kit's example is in `<home>/kit/examples/skills/`.
This is `haiku.skill.json`:

```json
{"skill_id": "haiku", "name": "Skill haiku", "description": "Answer as a three-line haiku.", "version": "1.0"}
```

This is `haiku.SKILL.md`:

```markdown
# haiku

Whatever the user asks, answer ONLY as a three-line haiku and end with the word 'haiku'.
```

To write your own skill:

1. Copy both files to a directory of your own and rename them, keeping the two endings.
2. Change `skill_id`, `name` and `description` in the JSON file, and write your text in the Markdown file.
3. Copy the skill into the project (*kit extension*). The command copies both files to `<project-path>/.agents/skills/` and has the runtime load them:

   ```sh
   arhugula skill add <your-skill-directory> --project <project>
   ```

### Activate skills with a hook

A loaded skill does nothing until a hook activates it.
The hook is a Python object that the runtime asks, before each model call, which skills to add.

*Upstream limit:* the runtime accepts the hook only as a Python object on its configuration, and a TOML file cannot carry one.
*Kit extension:* `arhugula skill hook set` stores the hook's name, and `arhugula run` then starts the runtime with that hook attached.
Everything else in the run, including gates and exit codes, stays the runtime's own.
A run that you send to a daemon with `--daemon` does not get the hook, because the kit starts the daemon without it.

To activate every loaded skill before each model call, use the hook the kit ships:

```sh
arhugula skill hook set every
```

To choose skills yourself, write a class with the same two methods.
This is the kit's hook, from `lib/arhugula_kit/skillhooks.py`, shown without its type hints:

```python
class EverySkill:
    """Activate every loaded skill before each model call, and none at workflow start."""

    def select_for_workflow_init(self, loaded_skills, workflow_id):
        return []

    def select_for_llm_dispatch(self, loaded_skills, workflow_id, step_index):
        return list(loaded_skills)
```

`loaded_skills` holds the ids of the loaded skills, and each method returns the ids to activate.
The runtime fails the step when a method returns an id that is not loaded, or the same id twice.

Save your class in `<project-path>/skills/`, for example as `my_hooks.py`, and name it as `module:Class`:

```sh
arhugula skill hook set my_hooks:OnlyHaiku
```

One hook serves the whole deployment.
Remove it with `arhugula skill hook clear`.

## Write a validator class

A validator is a Python class that checks the result of one step after the step ran.
Copy `<home>/kit/examples/validators/example_validators.py` to `<project-path>/validators/` and change it.

The runtime uses your class in two steps:

1. **It builds the object once:** it calls `YourClass(**params)` with the parameters of the binding.
2. **It checks each result:** after the step, it calls `await validator.validate(step, step_result, step_context=...)`.

This is the first example class, which fails a reply that is too long:

```python
class MaxCharsValidator:
    """PASS when the reply has at most `max_chars` characters; otherwise PERMANENT_FAIL."""

    def __init__(self, *, max_chars: int) -> None:
        self.max_chars = int(max_chars)

    async def validate(self, step: Any, step_result: Any, *, step_context: Any) -> ValidatorResult:
        if len(reply_text(step_result).strip()) <= self.max_chars:
            return ValidatorResult(outcome=ValidatorOutcome.PASS)
        return ValidatorResult(
            outcome=ValidatorOutcome.PERMANENT_FAIL, fail_class=ValidatorFailClass.SCHEMA_VIOLATION
        )
```

The example file also holds the imports and the helper `reply_text`, which reads the reply from both reply shapes the providers return.

`validate` returns a `ValidatorResult` with one of three outcomes.

| Outcome | What the workflow does | What you return |
| --- | --- | --- |
| `PASS` | It goes on. | `ValidatorResult(outcome=ValidatorOutcome.PASS)` |
| `PERMANENT_FAIL` | It stops, and the run fails with `CP-FAIL-VALIDATOR-PERMANENT`. | The outcome and a `fail_class` |
| `ESCALATE` | It stops at an approval gate, and a person decides. | The outcome, a `fail_class` and an `escalation_brief` |

The second example class, `AskAPersonValidator`, shows how to build the `escalation_brief`.
Upstream's outcome type also defines `REVALIDATE` and `OPERATOR_BURDEN_EXCEEDED`; the kit's examples do not use them.

Bind your class to the id of the step it checks:

```sh
arhugula validator bind ask-local-model example_validators:MaxCharsValidator --param max_chars=200 --project <project>
```

The command imports and builds the class before it stores the binding, so it refuses a class that cannot be used.
Three details matter when you bind:

- **Parameters are typed:** each `--param key=value` is read as JSON when it parses, so `200` is a number and `true` is a boolean. Any other value is a string.
- **One validator per step:** a second binding for the same step id replaces the first.
- **Modules load from the project:** the runtime imports from `<project-path>/validators/`. For a module elsewhere, add `--pythonpath <directory>`.

## Test your work without calling a provider

Three commands check your files through the runtime's own loaders.
None of them calls a provider, so they cost nothing.

| You wrote | Command | What a pass proves |
| --- | --- | --- |
| A manifest | `arhugula workflow validate <manifest>` | The runtime's loader accepts the manifest. |
| A skill | `arhugula skill validate <directory>` | Every skill in the directory loads in the runtime. |
| A validator binding | `arhugula validator test` | Every bound class imports, builds with its parameters and has an `async def validate` method. |

Check a manifest.
The command names the file, the topology, the workload class and each step:

<!-- witness -->
```sh
arhugula workflow validate ollama-first.toml --project <project>
```

```text
<home>/upstream/examples/ollama-first.toml loads.
  workflow id:   example-ollama-first
  topology:      single-threaded-linear
  workload:      pipeline-automation
  step:          ask-local-model (inference-step)
```

A manifest the loader refuses ends the command with exit code 4 and the loader's reason.
The command also warns when the project does not use the workload class of the manifest.

Check a skills directory before you add it.
Without a directory, the command checks the skills of the current project:

<!-- witness -->
```sh
arhugula skill validate <home>/kit/examples/skills
```

```text
<home>/kit/examples/skills: 1 skill(s) load in the runtime
  haiku (24 tokens)
```

Check every validator the project binds (*kit extension*).
A class that would fail when a run starts ends the command with exit code 3:

<!-- witness -->
```sh
arhugula validator test --project <project>
```

A project that binds no validator answers:

```text
<project> binds no validator.
```

A prompt version needs no test command: `arhugula prompt author` refuses an empty file, a text that is already authored and a label that is already used.
When all checks pass, run the workflow as [Run and write workflows](workflows.md) describes.

## Sources

Kit modules, relative to `<home>/kit`:

- `lib/arhugula_kit/verbs_authoring.py`
- `lib/arhugula_kit/verbs_run.py`
- `lib/arhugula_kit/hookrun.py`
- `lib/arhugula_kit/skillhooks.py`
- `lib/arhugula_kit/workflows.py`
- `examples/prompts/`, `examples/skills/`, `examples/validators/example_validators.py`
- `docs/reference/cli.md`

Upstream files, relative to `<home>`:

- `upstream/harness-runtime/src/harness_runtime/lifecycle/external_cli_provider.py`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/llm_dispatch.py`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/prompt_selection.py`
- `upstream/harness-cp/src/harness_cp/validator_framework_types.py`
- `upstream/examples/minimal.toml`
- `upstream/examples/ollama-first.toml`
- `upstream/docs/memory-layer-readme.md`
