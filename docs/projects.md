# Attach your projects

This page is for the operator who installed the harness and for the workflow author who works in a repository.
After reading it, you can attach a repository to your deployment, run a workflow on it, and find its config, ledger and memory.

You need an installed deployment first: see the [installation guide](install.md).
The run on this page uses Ollama and the model `llama3.2:3b`: see [the dependencies](install.md#dependencies).

## On this page

- [How one install serves many repositories](#how-one-install-serves-many-repositories)
- [Attach a repository](#attach-a-repository)
- [Check what you attached](#check-what-you-attached)
- [Run a workflow on the project](#run-a-workflow-on-the-project)
- [Know what the harness writes in your repository](#know-what-the-harness-writes-in-your-repository)
- [Choose the project name](#choose-the-project-name)
- [Keep your manifests in the project](#keep-your-manifests-in-the-project)
- [Tell your agent CLI about the harness](#tell-your-agent-cli-about-the-harness)
- [Switch, inspect and detach projects](#switch-inspect-and-detach-projects)
- [Sources](#sources)

## How one install serves many repositories

You install the harness once, in the *home*: the directory of your deployment, written `<home>` on these pages.
A *project* is a repository that you attach to that deployment under a name.
The harness is not copied into the project.

Each project gets its own generated config, its own ledger, its own memory and its own tenant id.
All of them stay in the home, so a project's repository holds no run history.
The table shows where each part lives for a project named `<project>` at `<project-path>`.

| Part | Where it lives | Who writes it |
| --- | --- | --- |
| Generated config | `<home>/config/projects/<project>.toml` | `arhugula` verbs; do not edit it |
| State ledger | `<home>/state/projects/<project>/state-ledger/state.jsonl` | the runtime, on each run |
| Memory | `<home>/state/projects/<project>/memory/` | the runtime |
| Your manifests | `<project-path>/workflows/` | you |
| Working files | `<project-path>/.harness/` | the runtime |
| Skills | `<project-path>/.agents/skills/` | `arhugula skill add` |

A deployment also has a *deployment default*: the config that serves runs when no project is chosen.
Its repository is the upstream checkout, and its ledger is `<home>/state/state-ledger/state.jsonl`.
On the command line, the name `default` means the deployment default.

## Attach a repository

One command attaches a repository.
In it, `<project-path>` is the repository and `<project>` is the name you give it.

<!-- witness -->
```sh
arhugula project add <project-path> --name <project>
```

The command does these steps in order:

1. **Checks the path.** It must be a directory. If it is not, the command stops with exit code 3.
2. **Checks for leftover state.** A repository that holds harness state from an earlier checkout-local config is refused with exit code 3. The message names the fix: `arhugula state archive-legacy <project-path>`.
3. **Notes a plain directory.** A directory that is not a git checkout is accepted, and the command prints a note.
4. **Checks the name.** A name that another attached project already has is refused with exit code 3. So is a name that breaks the rules in [Choose the project name](#choose-the-project-name).
5. **Generates the config.** It writes `<home>/config/projects/<project>.toml` and regenerates the other configs. The runtime's own loader must accept every one. If the loader refuses, the command stops with exit code 4 and changes nothing.
6. **Sets the current project.** When no project is current, the new project becomes the current project. Otherwise the current project stays as it is.
7. **Reports.** It prints the config file, the state directory, the tenant id, the current project and a first run to try.

Three options change what the command does:

| Option | What it does |
| --- | --- |
| `--gitignore` | Adds the line `.harness/` to the project's `.gitignore`, with a comment above it. It adds nothing when the file already ignores `.harness/`. |
| `--agent-context` | Writes the harness section into the project's `CLAUDE.md` and `AGENTS.md`. See [Tell your agent CLI about the harness](#tell-your-agent-cli-about-the-harness). |
| `--workload <class>` | Binds one workload class; repeat it for several. Without it, the project binds the workload classes of the deployment. |

Without `--gitignore`, the command tells you that the harness writes working files under `.harness/`.
Pass the option unless your repository already ignores that directory.

## Check what you attached

List the attached projects.
A `*` marks the current project.

<!-- witness -->
```sh
arhugula project list
```

Output for one project named `demo`:

```text
   name  path            workload classes
*  demo  <project-path>  pipeline-automation,software-engineering,research,content-creation
```

Show where one project's files live:

<!-- witness -->
```sh
arhugula project show <project>
```

Output for the project `demo`:

```text
name:        demo
repository:  <project-path>
config:      <home>/config/projects/demo.toml
state:       <home>/state/projects/demo
ledger:      <home>/state/projects/demo/state-ledger/state.jsonl
tenant id:   demo
workloads:   pipeline-automation, software-engineering, research, content-creation
```

## Run a workflow on the project

Run the smallest upstream example on the project.
It sends one short prompt to the local Ollama model, so it costs nothing.

<!-- witness -->
```sh
arhugula run ollama-first.toml --project <project> --provider ollama
```

The run prints progress lines and ends with three result lines.
The hash differs on every run.

```text
override:  every step dispatches first to ollama/llama3.2:3b; the config's fallback chain applies if that candidate fails
...
status:    completed
workflow:  example-ollama-first
ledger:    908a011ae8a390f8409d9506a677ee20cefa9a91d1c206f04b6f3925fa5d1eb3
```

`--project` chooses the project for one command.
Without it, most verbs act on the current project.
The exceptions are in [Choose where a change applies](prompts-skills-validators.md#choose-where-a-change-applies).
`--provider ollama` sends every step of this run to Ollama first: see [Choose providers and routing](providers.md).

## Know what the harness writes in your repository

The first run on a project writes working files into the repository (*witnessed*).

| Path in the project | What it holds |
| --- | --- |
| `.harness/onboarding/prompts/` | the prompt store that the runtime reads |
| `.harness/onboarding/routing-manifest/` | the routing manifest that the runtime writes when a run starts |
| `.harness/index.json` | the runtime's index |
| `.agents/skills/` | the skills of this project |

Follow two rules for these paths:

- **Leave `.harness/` alone.** Do not edit it and do not commit it. `--gitignore` adds the ignore line for you.
- **Add skills with the verb.** `arhugula skill add <dir>` copies a skill into `.agents/skills/`: see the [page on prompts, skills and validators](prompts-skills-validators.md).

The ledger and the memory never go into the repository.
They stay in `<home>/state/projects/<project>/`, so deleting or re-cloning the repository loses no run history.

## Choose the project name

The project name is also the project's *tenant id*.
The generated config carries it, and the project's state directory is named after it.

| Rule | Detail |
| --- | --- |
| Allowed characters | lowercase letters, digits and hyphens |
| First character | a lowercase letter or a digit |
| Length | at most 63 characters |
| Reserved names | `default` and `harness` |
| Default name | the directory name in lowercase, with each run of other characters turned into one hyphen, and no hyphen at either end |

`default` is reserved because it addresses the deployment default on the command line.
`harness` is reserved because it is the name of the deployment default's config file.
If your directory has a reserved name, attach it under another name with `--name`.

## Keep your manifests in the project

Put a project's workflow manifests in `<project-path>/workflows/`.
`arhugula workflow new` writes there, and `arhugula workflow list` reads there.

When you name a manifest, the command looks for it in these places, in order:

1. the path as you typed it
2. the project's repository
3. the project's `workflows/` directory
4. the upstream checkout
5. the upstream `examples/` directory

So `arhugula run my-flow.toml --project <project>` finds `<project-path>/workflows/my-flow.toml`.
The same lookup finds the upstream examples by name, as in the run above.

Only manifests have a fixed directory.
Prompts, skills and validators each have their own verb: see the [page on prompts, skills and validators](prompts-skills-validators.md).
To write a manifest, read [Write and run workflows](workflows.md).

## Tell your agent CLI about the harness

An agent CLI such as Claude Code or Codex reads `CLAUDE.md` or `AGENTS.md` when you open it in a repository.
The kit can write a section into both files, so that the agent knows the project is attached and how to drive the harness (*kit extension*).

| To do this | Run |
| --- | --- |
| Print the section without writing it | `arhugula agent context show --project <project>` |
| Write or refresh the section | `arhugula agent context install --project <project>` |
| Take the section out | `arhugula agent context remove --project <project>` |

The home needs no such section: `init` writes an `AGENTS.md` and a `CLAUDE.md` there that point to the kit's own files, as the [agents page](agents.md) explains.

The section sits between two marker comments, `<!-- arhugula-harness:begin -->` and `<!-- arhugula-harness:end -->`.
`install` replaces only the text between the markers and leaves the rest of each file alone.
`remove` deletes a file only when the section was all it held.

The section names the project and gives the full path of the `arhugula` command.
It lists the verbs that list, validate and run workflows, and the verbs that show recent runs and run logs.
It also tells the agent that approval gates belong to a person, and that `.harness/` is not to be edited.

This section does not reach the agents inside a workflow.
Those agents are isolated provider calls and read no `CLAUDE.md` or `AGENTS.md`: see the [authoring page](authoring.md).

## Switch, inspect and detach projects

| To do this | Run |
| --- | --- |
| List the attached projects | `arhugula project list` |
| Make a project the current one | `arhugula project use <project>` |
| Go back to the deployment default | `arhugula project use default` |
| Show a project's paths | `arhugula project show <project>` |
| Show the deployment default's paths | `arhugula project show default` |
| Detach a project | `arhugula project remove <project>` |

`arhugula project remove` detaches the project and removes its generated config.
It keeps the ledger and the memory in `<home>/state/projects/<project>/`.
Delete that directory yourself when you no longer need them.

The command does not touch the repository.
If you installed the agent section, run `arhugula agent context remove --project <project>` before you detach, because that verb works only on an attached project.

Every flag of these verbs is in the [command reference](reference/cli.md#project).

## Sources

Kit modules:

- `lib/arhugula_kit/verbs_project.py`
- `lib/arhugula_kit/spec.py`
- `lib/arhugula_kit/render.py`
- `lib/arhugula_kit/layout.py`
- `lib/arhugula_kit/preflight.py`
- `lib/arhugula_kit/agentctx.py` and `lib/arhugula_kit/verbs_agent.py`
- `lib/arhugula_kit/common.py`
- `templates/project-agent-context.md.tmpl`

Upstream documents, relative to the home:

- `upstream/examples/README.md`
- `upstream/docs/how-to-operate-runtime.md`
- `upstream/docs/how-to-deploy.md`
