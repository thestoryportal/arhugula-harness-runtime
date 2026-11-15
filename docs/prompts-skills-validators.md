# Manage prompts, skills and validators

This page is for a workflow author or an operator who manages prompt versions, skills and validators in a deployment.
After reading it you can author, select, approve and compare prompt versions, add skills and activate them, bind validators to steps, and recognise the three refusals the runtime gives.

It applies to the upstream commit named in the kit's `PIN` file.

To write the files these commands work on, read [Write what a workflow's agents do](authoring.md) first.
[The command reference](reference/cli.md) lists every argument of every command.

## On this page

- [Choose where a change applies](#choose-where-a-change-applies)
- [Manage prompt versions](#manage-prompt-versions)
- [Manage skills](#manage-skills)
- [Manage validators](#manage-validators)
- [Recognise the three refusals](#recognise-the-three-refusals)
- [Sources](#sources)

## Choose where a change applies

Every command on this page that changes a setting edits the answers file and regenerates the configs.
The runtime's own loader must accept the result, or nothing changes: see [How configuration changes](configure.md#how-configuration-changes).
The one exception is `arhugula skill add`, which copies files into the project and changes no setting.

The option `--project <project>` decides which config a command acts on.
Its meaning when you leave it out differs between the command groups.

| Commands | With `--project <project>` | Without `--project` |
| --- | --- | --- |
| `prompt` (all six), `validator list`, `validator bind`, `validator unbind` | That project's config only | Every config of the deployment |
| `skill list`, `skill add`, `skill validate`, `validator test` | That project | The current project |
| `skill hook set`, `skill hook clear` | Not accepted | The whole deployment |

A list that a project stores replaces the deployment's list of the same name; the two do not merge.
So keep all prompt versions of a project in one place: author them all with `--project <project>`, or all without it.
The same holds for validator bindings.

The examples below use `--project <project>` throughout.

## Manage prompt versions

A prompt version is a text the runtime uses as the system prompt.
The runtime identifies a version by the sha256 of its text, so the same text is always the same version.
You also give each version a label, such as `v1`, to name it in commands.
Every command that takes a version accepts its label or the first characters of its sha.

| Command | What it does |
| --- | --- |
| `arhugula prompt list` | Lists the authored versions and where each is used. |
| `arhugula prompt author <label> --file <file>` | Stores the text of a file as a new version. Add `--activate` to make it the active one. |
| `arhugula prompt activate <version>` | Makes an authored version the active one. |
| `arhugula prompt select <workload> <version>` | Uses an authored version for one workload class. |
| `arhugula prompt approve <version>` | Adds a version to the approval list. |
| `arhugula prompt diff <first> <second>` | Shows the text difference between two versions (*kit extension*). |

### Author two versions and compare them

Author the kit's first example text.
The command prints the full sha, and it makes this version active because it is the first one:

<!-- witness -->
```sh
arhugula prompt author v1 --file <home>/kit/examples/prompts/terse-v1.md --project <project>
```

Author the second example text.
It stays inactive until you activate or select it:

<!-- witness -->
```sh
arhugula prompt author v2 --file <home>/kit/examples/prompts/terse-v2.md --project <project>
```

The command refuses a text that is already authored and a label that is already used, both with exit code 3.
No `prompt` command removes a version.
To remove every authored version of a project, run `arhugula config unset prompt_manifest --project <project>`.
Remove the project's selections first, as the next section shows, because a selection must not outlive its version.

List the versions:

<!-- witness -->
```sh
arhugula prompt list --project <project>
```

This is the list on the development deployment, where `v2` is also approved and selected for one workload class:

```text
label  sha                             selected for         content
v1     aec1955b25d7  active            -                    You are a terse assistant. Reply in UPPERCASE ENGL
v2     afde1dfeed55          approved  pipeline-automation  You are a terse assistant. Reply in lowercase Engl
```

Compare the two versions:

<!-- witness -->
```sh
arhugula prompt diff v1 v2 --project <project>
```

```text
--- v1 aec1955b25d7
+++ v2 afde1dfeed55
@@ -1 +1 @@
-You are a terse assistant. Reply in UPPERCASE ENGLISH only.
+You are a terse assistant. Reply in lowercase English only, in one sentence.
```

### Select a version for a workload class

The active version is the system prompt of every workflow, unless a selection says otherwise.
A selection names the version for one workload class.
The four workload classes are `pipeline-automation`, `software-engineering`, `research` and `content-creation`.

```sh
arhugula prompt select pipeline-automation v2 --project <project>
```

A workflow whose manifest says `workload_class = "pipeline-automation"` then receives `v2`.
Every other workflow still receives the active version.

`arhugula prompt select` accepts only an authored version.
A selection can still name a version that a config does not hold, in two ways.
You stored the selection with `arhugula config set`.
Or you selected a version for the whole deployment, and a project stores its own list of versions without that one.
The runtime refuses such a selection when a run of that workload class starts: see [Recognise the three refusals](#recognise-the-three-refusals).

To remove the selections of a project, run `arhugula config unset prompt_selection_manifest --project <project>`.

### Approve a version

The approval list holds the versions an operator has approved.
`arhugula prompt approve <version>` adds a version to it.

```sh
arhugula prompt approve v2 --project <project>
```

The runtime reads the list only at a persona that requires approval, and it takes that persona from the deployment's config, not from a workflow file's `persona_tier`.
In this kit that is the team persona, which the feature `persona-team` switches on.
A deployment with the default solo-developer persona runs a selected version without approval.
With the team persona, the runtime refuses a selected version that is not on the list, with `RT-FAIL-PROMPT-VERSION-UNAPPROVED`.
The development deployment has not run that refusal.

### Tune the prompt cache

Two named features tune the prompt cache of the Anthropic API provider.
They change nothing for the subscription command-line providers, which manage their own cache.

| Feature | What it switches on |
| --- | --- |
| `prompt-cache` | The one-hour cache tier for the `research` workload class, and a cache warm-up at start |
| `prompt-cache-keepalive` | A ping every 240 seconds that keeps the cache warm while a daemon runs |

See what a feature merges into the configs before you switch it on:

<!-- witness -->
```sh
arhugula feature show prompt-cache
```

```text
prompt-cache: Anthropic prompt cache tuning
state:  off
needs:  the Anthropic API provider: arhugula provider enable anthropic, then arhugula provider key set anthropic

Uses the one-hour prompt cache tier for the research workload and pre-warms the cache at start. It affects only the Anthropic API provider; subscription CLIs manage their own cache.

It merges this into every generated config:

[runtime]
prompt_cache_long_ttl_workloads = ["research"]
prompt_cache_boot_prewarm = true
prompt_cache_prewarm_model = "claude-haiku-4-5"
```

Switch a feature on with `arhugula feature enable <name>`: see [Switch named features on and off](configure.md#switch-named-features-on-and-off).

## Manage skills

A skill is two files, `<name>.skill.json` and `<name>.SKILL.md`.
The runtime loads the skills of a project from `<project-path>/.agents/skills/`.

| Command | What it does |
| --- | --- |
| `arhugula skill list` | Lists the skills that load from the project, and names the activation hook. |
| `arhugula skill add <source>` | Copies each skill in a directory into the project's skills directory (*kit extension*). |
| `arhugula skill validate <directory>` | Loads a directory through the runtime's loader. Without a directory, it checks the project's. |
| `arhugula skill hook set <hook>` | Chooses the hook that activates skills in a run (*kit extension*). |
| `arhugula skill hook clear` | Removes the hook (*kit extension*). |

Add the kit's example skill to the project:

<!-- witness -->
```sh
arhugula skill add <home>/kit/examples/skills --project <project>
```

The command copies every pair of files in the directory.
It refuses a directory that holds no `.skill.json` file, a `.skill.json` file without its `.SKILL.md` file, and a file that already exists in the project.
It checks every pair before it copies the first file, so a refusal copies nothing.
Each refusal ends with exit code 3.

List the skills of the project:

<!-- witness -->
```sh
arhugula skill list --project <project>
```

This is the list on the development deployment:

```text
<project-path>/.agents/skills: 1 skill(s) load in the runtime
skill  content sha   tokens
haiku  feefb22c0308  24

activation hook: none: no skill is activated in a run
```

### Activate skills in a run

Look at the last line of the list: a loaded skill reaches no agent until a hook activates it.

*Upstream limit:* the runtime accepts the hook only as a Python object, which a TOML file cannot carry.
*Kit extension:* `arhugula skill hook set` stores the hook's name, and `arhugula run` attaches the hook when it starts the runtime.
`arhugula daemon start` attaches it too, so a run that you send with `--daemon` gets the same skills.

| Command | Result |
| --- | --- |
| `arhugula skill hook set every` | Every loaded skill is added before each model call. |
| `arhugula skill hook set <module:Class>` | Your own class decides. [Activate skills with a hook](authoring.md#activate-skills-with-a-hook) shows how to write one. |
| `arhugula skill hook clear` | No skill is activated. |

One hook serves the whole deployment, so these commands take no `--project`.
`arhugula skill hook set` imports and builds the class before it stores the name.
It refuses a class it cannot import or build, with exit code 3, and stores nothing.

## Manage validators

A validator is a Python class that checks the result of one step.
A binding ties one class, with its parameters, to one step id.

| Command | What it does |
| --- | --- |
| `arhugula validator list` | Lists the bindings: step, class and parameters. |
| `arhugula validator bind <step> <module:Class>` | Binds a class to a step id. Add `--param key=value` for each parameter and `--pythonpath <directory>` for a module outside the project's `validators/` directory. |
| `arhugula validator unbind <step>` | Removes the binding of a step. |
| `arhugula validator test` | Imports and builds every bound class without calling a provider (*kit extension*). |

### Know the three outcomes

A validator returns one of three outcomes after its step ran.

| Outcome | What happens to the run |
| --- | --- |
| `PASS` | The workflow goes on. |
| `PERMANENT_FAIL` | The workflow stops. The run fails with `CP-FAIL-VALIDATOR-PERMANENT` and exit code 1. |
| `ESCALATE` | The workflow stops at an approval gate, and a person decides. |

An escalation always opens an approval gate.
A gate asks for an answer at the terminal, and a run without a terminal rejects a gate.
[Run and write workflows](workflows.md) describes the answers a gate accepts.
The example class `AskAPersonValidator` escalates every result, so you can use it to try a gate.
The development deployment has not run an escalation.

Upstream's outcome type also defines `REVALIDATE` and `OPERATOR_BURDEN_EXCEEDED`.
The kit's examples do not use them, and the development deployment has not run them.

### Bind a validator, watch it fail a run, and unbind it

Bind the kit's example class to the step of upstream's `ollama-first.toml`.
The limit of one character makes the validator fail any real reply:

<!-- witness -->
```sh
arhugula validator bind ask-local-model example_validators:MaxCharsValidator --param max_chars=1 --pythonpath <home>/kit/examples/validators --project <project>
```

The command imports and builds the class before it stores the binding.
It refuses a class it cannot import or build, with exit code 3, and stores nothing.
The directory you pass with `--pythonpath` stays on the deployment's import path after you unbind, and no command removes it.

Check the binding without calling a provider:

<!-- witness -->
```sh
arhugula validator test --project <project>
```

The command prints one `ok` line for each bound class that imports, builds and has an `async def validate` method.
It prints a `FAIL` line and ends with exit code 3 for a class that would stop a run at its start.

Run the workflow on the local Ollama provider, which must be enabled: see [Run local models with Ollama](providers.md#run-local-models-with-ollama).
This run must fail: the model answers, and the validator rejects the answer (*witnessed*).

<!-- witness: exit=1 -->
```sh
arhugula run ollama-first.toml --project <project> --provider ollama
```

The run ends with these two lines and exit code 1:

```text
failure:   RT-FAIL-WORKFLOW
detail:    workflow execution returned status='failed' with fail_class="CP-FAIL-VALIDATOR-PERMANENT: validator returned PERMANENT_FAIL at step_id='ask-local-model'"
```

Remove the binding, so that later runs of this step pass again:

<!-- witness -->
```sh
arhugula validator unbind ask-local-model --project <project>
```

When you unbind the last binding of a scope, the command removes that scope's whole `validator_framework_config` table.
Any other setting you stored in that table with `arhugula config set` goes with it.
[The known gaps page](reference/known-gaps.md) lists the limits of the kit's commands.

## Recognise the three refusals

Each code in this table was *witnessed* on the development deployment.
`arhugula doctor --self-test` proves the first two again on your own machine, in a scratch directory.
It needs the Ollama provider, and reports the two cases as not exercised without it.

| Code | What caused it | When it appears | Exit code of `arhugula run` |
| --- | --- | --- | --- |
| `RT-FAIL-PROMPT-SELECTION-UNAUTHORED` | The prompt selection for the run's workload class names a version nobody authored. | When the run starts, before any provider is called | 4 |
| `RT-FAIL-VALIDATOR-STAGE-MATERIALIZE` | A validator binding names a class the runtime cannot import. | When the run starts, before any provider is called | 4 |
| `CP-FAIL-VALIDATOR-PERMANENT` | A validator returned `PERMANENT_FAIL`. | After the step ran | 1 |

The first two arrive inside a start-up failure, which the runtime reports as `RT-FAIL-BOOTSTRAP`.
These are the lines of the self-test, cut where the self-test cuts them:

```text
  ok    bad validator class [a validator binding names a class that cannot be imported]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage OD (5): ValidatorFrameworkStageMaterializeError: RT-FAIL-VALIDATOR-STAGE-MATERIALIZE: validator 'arhugula
  ok    unauthored prompt version [the prompt selection names a version nobody authored]
        exit 4: RT-FAIL-BOOTSTRAP: bootstrap failed at stage PREAMBLE (0): PromptSelectionUnauthoredError: RT-FAIL-PROMPT-SELECTION-UNAUTHORED: prompt-selection bindi
```

The kit's own commands stop both mistakes earlier.
`arhugula prompt select` accepts only an authored version, and `arhugula validator bind` refuses a class it cannot import.
You meet the two start-up refusals only after a change the commands could not check.
Two examples are a selection stored with `arhugula config set`, and a validator module that was deleted after you bound it.

To fix a refusal:

- For an unauthored selection, author the missing text with `arhugula prompt author`, or select an authored version with `arhugula prompt select`.
- For a class that cannot be imported, run `arhugula validator test` to see the reason, then restore the module or run `arhugula validator unbind <step>`.
- When a validator failed the run, the validator did its work. Change the step, the prompt or the validator's parameters, and run again.

[Troubleshooting](troubleshooting.md) covers the other failures of a run.

## Sources

Kit modules, relative to `<home>/kit`:

- `lib/arhugula_kit/verbs_authoring.py`
- `lib/arhugula_kit/verbs_config.py`
- `lib/arhugula_kit/overlay.py`
- `lib/arhugula_kit/render.py`
- `lib/arhugula_kit/selftest.py`
- `lib/arhugula_kit/hookrun.py`
- `lib/arhugula_kit/skillhooks.py`
- `fragments/prompt-cache.toml`, `fragments/prompt-cache-keepalive.toml`, `fragments/persona-team.toml`
- `examples/prompts/`, `examples/skills/`, `examples/validators/example_validators.py`
- `docs/reference/cli.md`

Upstream files, relative to `<home>`:

- `upstream/harness-runtime/src/harness_runtime/lifecycle/prompt_selection.py`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/llm_dispatch.py`
- `upstream/harness-runtime/src/harness_runtime/lifecycle/validator_escalation_composer.py`
- `upstream/harness-cp/src/harness_cp/validator_framework_types.py`
- `upstream/examples/ollama-first.toml`
