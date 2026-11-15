# Evaluation

This page is for the operator who wants to know how well the harness decides, beyond whether a run finished.
After reading it you can tell the in-loop gates from out-of-loop evaluation, run the holdout loop end to end, and set a drift threshold.

Evaluation needs no extra software.
It reads the local span store, which every run writes; see [observability](observability.md).
For every flag of every verb, see [the command reference](reference/cli.md).

## Contents

- [Two kinds of checking](#two-kinds-of-checking)
- [Run the holdout loop](#run-the-holdout-loop)
- [Fill in an assertion file](#fill-in-an-assertion-file)
- [The five operator-burden primitives](#the-five-operator-burden-primitives)
- [Check for alignment-floor drift](#check-for-alignment-floor-drift)
- [What the evaluation dashboard shows](#what-the-evaluation-dashboard-shows)
- [What does not exist](#what-does-not-exist)
- [Sources](#sources)

## Two kinds of checking

The harness checks its work at two moments.
They differ in when the check runs and who decides.

| Question | In-loop gates | Out-of-loop evaluation |
| --- | --- | --- |
| When | During a run, before the run continues | After runs, on stored traces |
| Who decides | The runtime, or you at a gate prompt | You, by reviewing traces and writing assertions |
| Effect | Can stop, retry or reroute the run | Changes no run; it tells you how well the harness decides |
| Setup | Part of the workflow and the deployment's configuration; no separate step | You run the holdout loop yourself |

The in-loop gates are:

- **Validators.** A step's output is checked before the workflow moves on.
- **Approval floors.** A gated action waits for a person. The harness calls this human in the loop (HITL).
- **Retry and fallback.** A failed call is tried again, or sent to the next provider in the fallback chain.
- **Deadlines.** A step that runs too long is stopped.
- **Prompt-version approval.** A run refuses a selected prompt version that nobody authored. With the team persona, it also refuses one that nobody approved.

[Workflows](workflows.md) and [prompts, skills and validators](prompts-skills-validators.md) explain how to use each gate.
The rest of this page covers out-of-loop evaluation.

## Run the holdout loop

A holdout set is a sample of real traces that you set aside and judge by hand.
The holdout loop turns your judgements into assertions that you can run again later.
No step calls a model: upstream has no model judge, by design.

The loop has five steps.
Steps 1 to 3 drive the runtime's own tool, `harness-inspect`.
Steps 4 and 5 are *kit extensions*.

A holdout set belongs to one primitive, which names what you judge:

| Primitive | You judge |
| --- | --- |
| `routing_accuracy_holdout` (default) | Whether each call went to the right model |
| `sandbox_tier_routing_accuracy` | Whether each tool call ran at the right sandbox tier |

Add `--primitive <primitive>` to steps 1 to 3 to use the second one.

### Step 1: draw a sample

```sh
arhugula eval sample --count 3
```

The verb draws traces from the local span store and writes `holdout.json`.
The store must hold at least one run.
The default count is 10; if the store holds fewer traces, the verb draws them all.
The same `--seed` draws the same set from the same store; the default seed is 0.

The verb refuses if a holdout set already exists.
Add `--replace` to draw a new one.
`--replace` first moves the earlier set, its reviews and its assertion files aside, into `<primitive>.replaced-<time>` beside the primitive's directory.
The verb prints where they went, and `arhugula eval status` no longer counts or runs them.

### Step 2: review each trace

```sh
arhugula eval review
```

Run this in a terminal.
For each sampled trace, the tool prints the trace ID and its span count, then asks for a category and an optional note.
The category is your own word: choose a small set and keep to it.

To look at a trace before you answer, run `arhugula trace export --trace-id <trace-id>` in a second terminal.

This is a real review of three traces on the development deployment (*witnessed*).
The text after each `>` is what the operator typed.

```text
trace_id=9e001dee7b3c12423d23240bc4d234ac  spans=7  primitive=routing_accuracy_holdout
category> correct
notes (optional)> fine

trace_id=a942edee52df4a171399ca9f66186d63  spans=12  primitive=routing_accuracy_holdout
category> correct
notes (optional)> 

trace_id=0519269970ce3418b37660b302afea9e  spans=31  primitive=routing_accuracy_holdout
category> wrong-route
notes (optional)> went to the fallback

harness-inspect: review ledger at <home>/state/observability/evaluation/routing_accuracy_holdout/review-ledger.jsonl
```

An empty category skips the trace.
You can stop and run the verb again: it asks only about traces you have not categorized.

### Step 3: write the assertion files

```sh
arhugula eval scaffold
```

The verb writes one assertion file for each reviewed trace, into the directory `stubs`.
It never overwrites a file that exists, so a second run keeps the assertions you wrote.

### Step 4: fill in each assertion, then run them

[Fill in an assertion file](#fill-in-an-assertion-file) explains the editing.
Then run every assertion file:

<!-- witness -->
```sh
arhugula eval status
```

This is the output on the development deployment (*witnessed*).
One assertion passes, one fails on purpose, and one is not filled in yet.

```text
routing_accuracy_holdout: 3 sampled, 3 reviewed, 3 assertion file(s) (1 FAILED, 1 not filled in, 1 passed)
    test_holdout_a942edee52df4a171399ca9f66186d63.py: passed
    test_holdout_t0519269970ce3418b37660b302afea9e.py: FAILED: routed to the fallback
    test_holdout_t9e001dee7b3c12423d23240bc4d234ac.py: not filled in
sandbox_tier_routing_accuracy: 0 sampled, 0 reviewed, 0 assertion file(s)

files: <home>/state/observability/evaluation
The loop: eval sample -> eval review -> eval scaffold -> fill in each assertion -> eval status.
```

Each assertion file gets one of four results:

| Result | Meaning | Exit code of `arhugula eval status` |
| --- | --- | --- |
| `passed` | Every assertion in the file held | 0 |
| `not filled in` | The file still holds the scaffolded placeholder | 0 |
| `FAILED: <message>` | An assertion did not hold | 1 |
| `broken: <error>` | The file raised another error | 1 |

The run above exited with code 1, because one assertion failed.
With no failed and no broken file, the verb exits with code 0.

### Step 5: read the report

```sh
arhugula eval report
```

The report counts your review categories and repeats each assertion result (*witnessed*):

```text
## routing_accuracy_holdout
sampled 3, reviewed 3
category     traces
correct      2
wrong-route  1
assertion file                                     result
test_holdout_a942edee52df4a171399ca9f66186d63.py   passed
test_holdout_t0519269970ce3418b37660b302afea9e.py  FAILED: routed to the fallback
test_holdout_t9e001dee7b3c12423d23240bc4d234ac.py  not filled in

## sandbox_tier_routing_accuracy
sampled 0, reviewed 0
```

`arhugula eval report --json` prints the same facts as one JSON object, for a script or an agent.
The report always exits with code 0.

### Where the loop keeps its files

```text
<home>/state/observability/evaluation/<primitive>/
  holdout.json           the sampled trace IDs
  review-ledger.jsonl    one line for each reviewed trace
  stubs/                 one assertion file for each reviewed trace
```

The files belong to the deployment, not to one project.

## Fill in an assertion file

An assertion file is a small Python file with one function.
The function's docstring repeats your category and note, so you have the review in front of you.

This is a scaffolded file from the development deployment, before any edit:

```python
"""Holdout assertion stub — routing_accuracy_holdout, trace '9e001dee7b3c12423d23240bc4d234ac' (scaffolded, C-OD-17 §17.3 "automate" phase).

Tooling-generated. Operator-authored assertion required before this
test can pass — until then it fails loudly rather than silently
passing on an unauthored placeholder.
"""

from __future__ import annotations


def test_holdout_t9e001dee7b3c12423d23240bc4d234ac() -> None:
    """Category: 'correct'. Notes: 'fine'."""
    raise NotImplementedError(
        "operator-authored assertion pending for trace '9e001dee7b3c12423d23240bc4d234ac' (routing_accuracy_holdout)"
    )
```

To fill it in:

1. Open the file under `<home>/state/observability/evaluation/<primitive>/stubs/`.
2. Decide what "correct" means for this trace. For a routing judgement, that is usually which provider or model the call should have reached.
3. Replace the `raise NotImplementedError(...)` statement with one or more `assert` statements.
4. Give each `assert` a message. `arhugula eval status` prints it when the assertion fails.
5. Run `arhugula eval status`.

This is the filled-in function for the trace that the reviewer marked `wrong-route`.
The reviewer wrote the comparison by hand: the provider the trace shows, then the provider they expected.

```python
def test_holdout_t0519269970ce3418b37660b302afea9e() -> None:
    """Category: 'wrong-route'. Notes: 'went to the fallback'."""
    assert "ollama" == "claude_code", "routed to the fallback"
```

That assertion always fails, so `arhugula eval status` keeps reporting the wrong route.

Keep to these rules:

- **Keep the function name.** `arhugula eval status` runs every function whose name starts with `test_holdout_`.
- **Keep the file name.** It is `test_holdout_<trace-id>.py`. The tool puts a `t` before a trace ID that starts with a digit.
- **Raise only `AssertionError`.** Any other error shows as `broken`.
- **Call no model.** The file is your recorded judgement. Nothing in the loop asks a model to judge.

## The five operator-burden primitives

Upstream declares five evaluation primitives.
Each one measures how much the harness costs you in attention, or how well it routes.

| # | Primitive | What it measures | How it is computed |
| --- | --- | --- | --- |
| 1 | `expected_hitl_invocations_per_session` | How often a person is asked during a run | A count of `hitl.invocation.responded` spans |
| 2 | `expected_sandbox_violations_per_session` | How often a tool call breaks the sandbox | A count of `sandbox.violation` spans |
| 3 | `sandbox_tier_routing_accuracy` | Whether tool calls ran at the right sandbox tier | A holdout judgement: the holdout loop |
| 4 | `cache_hit_rate_alignment_floor` | The share of prompt-cache tokens that were reads | A ratio of two token counts on LLM call spans |
| 5 | `routing_accuracy_holdout` | Whether calls went to the right model | A holdout judgement: the holdout loop |

The formula of primitive 4 is cache-read input tokens divided by the sum of cache-read and cache-creation input tokens.
Only calls to the `anthropic` provider write those two counts.

Primitives 3 and 5 are the two that `arhugula eval sample` accepts.
No span carries a verdict for them, so only the holdout loop can measure them.

The declarations carry no threshold.
Thresholds belong to the drift check below.

## Check for alignment-floor drift

An alignment floor is the lowest value you accept for a primitive.
Drift means the current value fell below that floor.

Four primitives can have a floor:

| Primitive | Where the current value comes from |
| --- | --- |
| `cache_hit_rate_alignment_floor` | Computed from the local span store over the window |
| `routing_accuracy_holdout` | You pass it with `--judge-value` |
| `sandbox_tier_routing_accuracy` | You pass it with `--judge-value` |
| `judge_human_cohens_kappa` | You pass it with `--judge-value` |

### Set a threshold

```sh
arhugula eval drift set-threshold cache_hit_rate_alignment_floor 0.5
```

The window is the period the check looks at.

| Flag | Meaning | Default |
| --- | --- | --- |
| `--window-kind` | `TIME_WINDOW` for seconds, or `SAMPLE_WINDOW` for a count of the most recent spans | `TIME_WINDOW` |
| `--window-size` | The number of seconds, or of spans | `86400`, which is 24 hours |

The kit stores the threshold in the deployment's configuration.
The runtime has no setting for it at this pin (*upstream limit*), and upstream's code has no default value.

### Compare the current value with the threshold

```sh
arhugula eval drift show
```

With no primitive named, the verb checks every primitive that has a threshold.
This is the output on the development deployment, where two thresholds are set (*witnessed*):

```text
cache_hit_rate_alignment_floor: no data in the window (threshold 0.5)
routing_accuracy_holdout: cannot be computed from spans (routing_accuracy_holdout has no deterministic span-derived formula (C-OD-18 §18.1) — its current value must come from an operator/judge verdict, not be inferred from stored review data (eval-harness-refused-as-governance-gate)). Pass your own measured value with --judge-value.
```

The first line says `no data` because no run in the window called the `anthropic` provider with prompt caching.
The second line shows upstream's own refusal: the verb does not derive a routing score from your review ledger.

For a primitive that spans cannot give, pass the value you measured.
For example, if 2 of 3 reviewed traces were routed correctly:

```sh
arhugula eval drift show routing_accuracy_holdout --judge-value 0.67
```

Name the primitive when you pass `--judge-value`.
Without a name, the verb stops with exit code 2 and this message:

```text
--judge-value is your measurement of one primitive; name the primitive it belongs to
```

`--judge-value` never replaces a value that spans give.
For `cache_hit_rate_alignment_floor`, the verb reports the computed rate and ignores your value.

When a value is available, the verb prints the current value, the threshold, the window, and `DRIFT` or `within the floor`.
The rule is upstream's: drift when the current value is lower than the threshold.

| Outcome | Exit code |
| --- | --- |
| No primitive drifted, or no value was available | 0 |
| At least one primitive drifted | 1 |
| `--judge-value` names no primitive | 2 |
| The primitive has no threshold | 3, with the fix printed |

`arhugula eval drift show` writes no drift event to a trace.
Upstream's emitter needs a live span, which only a running workflow has.

## What the evaluation dashboard shows

The Grafana dashboard "Arhugula · Evaluation" shows what traces can tell about the five primitives.
It needs the observability tier; see [observability](observability.md).

| Section | Panels | Fills when |
| --- | --- | --- |
| Primitive 1 | Answered human gates, Workflow runs, Answered human gates over time | Workflows with human gates run |
| Primitive 2 | Sandbox violations, by fail class and over time | A tool step fails in the sandbox |
| Primitives 3 and 5 | Text only: a holdout judgement is not in any span | Never; use `arhugula eval status` |
| Primitive 4 | Cache read and cache creation input tokens, in total and by model | Calls to the `anthropic` provider use prompt caching |
| Scores and drift | Evaluation scores by primitive, Drift events, Drift events by primitive, Recent drift events | Never from a normal run |

Three facts explain the gaps:

- **Per-session figures need a division.** The dashboard shows the counter and the number of workflow runs side by side. Divide the first by the second.
- **The cache hit rate needs a division too.** TraceQL cannot divide two sums. `arhugula eval drift show` reports the computed rate.
- **No normal run writes a score span or a drift event.** Those panels, and the alert rule "Alignment-floor drift detected", stay silent at this pin (*upstream limit*).

[The panel index](../observability/PANELS.md) lists every panel with its query.

## What does not exist

- **No model judge.** Nothing grades an output with a model (*upstream limit*, by upstream's design). You are the judge in the holdout loop. (upstream issue: see known-gaps)
- **No scored suite.** There is no benchmark, no dataset runner and no score for each run (*upstream limit*). An assertion file passes or fails; it does not score.
- **No runtime setting for drift thresholds.** The kit, not the runtime, stores each threshold (*upstream limit*). Only `arhugula eval drift show` reads it.
- **No automatic drift check.** Nothing runs the drift check for you during or after a run (*upstream limit*). Run `arhugula eval drift show` yourself, or from a scheduled job.
- **No drift value for most primitives from spans.** Only `cache_hit_rate_alignment_floor` is computed. The other three need `--judge-value`.
- **No roll-up by role or session.** The dimensions that upstream declares for the primitives are not on the spans, so no panel splits by them (*upstream limit*).

[Known gaps](reference/known-gaps.md) lists every upstream limit in one place.

## Sources

Kit modules and files:

- `kit/lib/arhugula_kit/verbs_observability.py` (the `eval` verbs)
- `kit/lib/arhugula_kit/bridge.py` (`drift_check`)
- `kit/lib/arhugula_kit/layout.py`
- `kit/observability/dashboards/evaluation.json`, `kit/observability/PANELS.md`

Upstream code:

- `upstream/harness-runtime/src/harness_runtime/admin/inspect.py` (the holdout sample, review and scaffold)
- `upstream/harness-od/src/harness_od/holdout_assertion_scaffold.py`
- `upstream/harness-od/src/harness_od/operator_burden_eval_primitives.py`
- `upstream/harness-od/src/harness_od/alignment_floor_drift_detection.py`
- `upstream/harness-od/src/harness_od/alignment_floor_drift_algorithm.py`
