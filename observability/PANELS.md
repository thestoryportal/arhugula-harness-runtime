# Arhugula dashboards and alert rules: panel index

Generated from the same definition as the files in `kit/observability/dashboards/` and `kit/observability/alerting/`.

- Data source for every panel and rule: Tempo (`uid: tempo`).
- `$namespace` is the dashboard variable "Project" (values of the resource attribute `service.namespace`; "All" is the regular expression `.*`).
- Panel kinds: *stat* and *bar gauge* run the query as a TraceQL metrics instant query; *time series* runs it as a range query; *table* runs it as a TraceQL search and lists the matching spans; *text* has no query.
- Default time range of every dashboard: last 6 hours. The stack keeps traces for 24 hours, so no panel can look further back than that.

## Arhugula · LLM calls

File `genai.json`, uid `arhugula-genai`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | LLM calls | stat | How many LLM calls ran in the selected time range? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| count_over_time()` |
| 3 | Failed LLM calls | stat | How many LLM calls ended with an error status? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && status = error } \| count_over_time()` |
| 4 | Input tokens | stat | How many input tokens did providers report? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.gen_ai.usage.input_tokens != nil } \| sum_over_time(span.gen_ai.usage.input_tokens)` |
| 5 | Output tokens | stat | How many output tokens did providers report? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.gen_ai.usage.output_tokens != nil } \| sum_over_time(span.gen_ai.usage.output_tokens)` |
| 6 | Call rate by provider | time series | How many LLM calls per second went to each provider? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| rate() by (span.gen_ai.provider.name)` |
| 7 | Call rate by model | time series | How many LLM calls per second went to each model? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| rate() by (span.gen_ai.request.model)` |
| 8 | Latency p50 and p95 by provider | time series | How long does an LLM call take on each provider (median and 95th percentile of span duration)? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| quantile_over_time(duration, .5, .95) by (span.gen_ai.provider.name)` |
| 9 | Latency p50 and p95 by model | time series | How long does an LLM call take on each model (median and 95th percentile of span duration)? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| quantile_over_time(duration, .5, .95) by (span.gen_ai.request.model)` |
| 10 | Input tokens by model | time series | How many provider-reported input tokens did each model consume over time? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.gen_ai.usage.input_tokens != nil } \| sum_over_time(span.gen_ai.usage.input_tokens) by (span.gen_ai.request.model)` |
| 11 | Output tokens by model | time series | How many provider-reported output tokens did each model produce over time? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.gen_ai.usage.output_tokens != nil } \| sum_over_time(span.gen_ai.usage.output_tokens) by (span.gen_ai.request.model)` |
| 12 | CLI-reported input tokens (subscription routes) | time series | How many input tokens did subscription CLI routes report as usage evidence? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.external_cli.usage.input_tokens != nil } \| sum_over_time(span.external_cli.usage.input_tokens) by (span.gen_ai.provider.name)` |
| 13 | CLI-reported output tokens (subscription routes) | time series | How many output tokens did subscription CLI routes report as usage evidence? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.external_cli.usage.output_tokens != nil } \| sum_over_time(span.external_cli.usage.output_tokens) by (span.gen_ai.provider.name)` |
| 14 | Provider mix | bar gauge | Which share of LLM calls went to each provider? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| count_over_time() by (span.gen_ai.provider.name)` |
| 15 | Model mix | bar gauge | Which share of LLM calls went to each model? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| count_over_time() by (span.gen_ai.request.model)` |
| 16 | Calls by routing layer | bar gauge | Which routing layer chose the model for each call? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.routing.layer != nil } \| count_over_time() by (span.routing.layer)` |
| 17 | Failed calls by model | time series | Which models produce failed calls, and when? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && status = error } \| count_over_time() by (span.gen_ai.request.model)` |
| 18 | Failed subscription CLI calls | time series | Which subscription CLI routes exited with a non-zero exit code? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.external_cli.exit_code != 0 } \| count_over_time() by (span.external_cli.provider.kind)` |
| 19 | Finish reasons | text | Why is there no finish-reason panel? | (no query) |
| 20 | Recent LLM calls | table | Which LLM calls ran most recently, and with what provider, model, tokens and status? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| select(span.gen_ai.provider.name, span.gen_ai.request.model, span.routing.layer, span.gen_ai.usage.input_tokens, span.gen_ai.usage.output_tokens, status)` |
| 21 | Recent failed LLM calls | table | Which LLM calls failed most recently? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && status = error } \| select(span.gen_ai.provider.name, span.gen_ai.request.model, span.routing.binding_rationale, statusMessage)` |

## Arhugula · Routing and resilience

File `routing-resilience.json`, uid `arhugula-routing-resilience`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | LLM attempts | stat | How many LLM dispatch attempts ran? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" } \| count_over_time()` |
| 3 | Retried attempts | stat | How many attempts were a second or later try? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.attempt_number > 1 } \| count_over_time()` |
| 4 | Exhausted fallback chains | stat | How many dispatches ran out of candidates? | `{ resource.service.namespace =~ "$namespace" && event:name = "fallback.exhausted" } \| count_over_time()` |
| 5 | Breakers opened | stat | How many times did a circuit breaker open? | `{ resource.service.namespace =~ "$namespace" && event:name = "breaker.tripped" && event.harness.breaker.to_state = "open" } \| count_over_time()` |
| 6 | Attempts by terminal outcome | time series | How did LLM attempts end (success, retry, max-attempts, fail-fast, escalate, …)? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.terminal != nil } \| count_over_time() by (span.retry.terminal)` |
| 7 | Attempts by attempt number | time series | How many attempts were first, second or later tries? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" } \| count_over_time() by (span.retry.attempt_number)` |
| 8 | Failed attempts by fail class | time series | Which fail class did failed LLM attempts carry? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.fail_class != nil } \| count_over_time() by (span.retry.fail_class)` |
| 9 | Failed attempts by cause | bar gauge | What caused failed LLM attempts (classified cause or exception class)? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.cause_attribution != nil } \| count_over_time() by (span.retry.cause_attribution)` |
| 10 | Tool attempts by terminal outcome | time series | How did tool dispatch attempts end? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.tool_retry_attempt" && span.retry.terminal != nil } \| count_over_time() by (span.retry.terminal)` |
| 11 | Breaker charge waived | time series | How often was a failure not charged to the breaker, and why? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.breaker_waived.reason != nil } \| count_over_time() by (span.retry.breaker_waived.reason)` |
| 12 | Dispatches by fallback chain length | bar gauge | How many candidates did the fallback chain hold for each dispatch? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_breaker_fallback" } \| count_over_time() by (span.fallback.chain_length)` |
| 13 | fallback.triggered events | time series | When did the capability pre-check skip a candidate, and for what cause? | `{ resource.service.namespace =~ "$namespace" && event:name = "fallback.triggered" } \| count_over_time() by (event.fallback.cause)` |
| 14 | fallback.exhausted events | time series | When did a dispatch run out of candidates, and for what cause? | `{ resource.service.namespace =~ "$namespace" && event:name = "fallback.exhausted" } \| count_over_time() by (event.fallback.exhaustion_cause)` |
| 15 | Exhaustion by last failure class | bar gauge | What was the last failure before a fallback chain was exhausted? | `{ resource.service.namespace =~ "$namespace" && event:name = "fallback.exhausted" } \| count_over_time() by (event.fallback.last_failure_class)` |
| 16 | retry.skipped events | time series | When was a candidate skipped because its breaker was open or on trial? | `{ resource.service.namespace =~ "$namespace" && event:name = "retry.skipped" } \| count_over_time() by (event.retry.skipped.reason)` |
| 17 | breaker.tripped events by new state | time series | When did a breaker change state, and to which state (open, half_open, closed)? | `{ resource.service.namespace =~ "$namespace" && event:name = "breaker.tripped" } \| count_over_time() by (event.harness.breaker.to_state)` |
| 18 | Breaker openings by cause | bar gauge | Why did breakers open (rate limit, auth failure, 5xx streak, capability shortfall)? | `{ resource.service.namespace =~ "$namespace" && event:name = "breaker.tripped" && event.harness.breaker.to_state = "open" } \| count_over_time() by (event.harness.breaker.cause)` |
| 19 | tool_retry.exhausted events | time series | When did a tool dispatch use up its attempts? | `{ resource.service.namespace =~ "$namespace" && event:name = "tool_retry.exhausted" } \| count_over_time() by (event.tool_retry.last_failure_class)` |
| 20 | Timeout signals | text | Where do timeouts show up? | (no query) |
| 21 | HITL gate timeouts | time series | When did a human gate time out, and which degradation mode applied? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.timed_out" } \| count_over_time() by (span.hitl.timeout.degradation_mode_applied)` |
| 22 | Tool invocation timeouts | time series | When did a tool call time out in the sandbox? | `{ resource.service.namespace =~ "$namespace" && name = "sandbox.violation" && span.mcp.fail.class = "timeout" } \| count_over_time()` |
| 23 | Provider attempts ending retry or max-attempts | time series | When did provider calls fail transiently (including provider timeouts)? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && (span.retry.terminal = "retry" \|\| span.retry.terminal = "max-attempts") } \| count_over_time() by (span.retry.terminal)` |
| 24 | Spans that ended with an error | time series | Which spans did an exception leave, and when? | `{ resource.service.namespace =~ "$namespace" && status = error } \| count_over_time() by (name)` |
| 25 | Recent failed workflow runs | table | Which workflow runs failed most recently, and with what fail class? | `{ resource.service.namespace =~ "$namespace" && name = "workflow.envelope" && span.workflow.outcome = "failed" } \| select(span.workflow.id, span.workflow.run_id, span.workflow.fail_class, span.workflow.topology_pattern)` |
| 26 | Recent attempts that did not succeed | table | Which attempts ended in something other than success? | `{ resource.service.namespace =~ "$namespace" && name = "harness.runtime.retry_attempt" && span.retry.terminal != "success" } \| select(span.retry.attempt_number, span.retry.terminal, span.retry.cause_attribution, span.retry.fail_class, span.retry.delay_ms)` |
| 27 | Recent exhausted fallback chains | table | Which dispatches ran out of candidates most recently, and why? | `{ resource.service.namespace =~ "$namespace" && event:name = "fallback.exhausted" } \| select(span.fallback.chain_length, event.fallback.exhaustion_cause, event.fallback.last_failure_class, event.fallback.last_failure_detail)` |

## Arhugula · Human-in-the-loop gates

File `hitl.json`, uid `arhugula-hitl`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | Gate evaluations | stat | How many gate evaluations ran? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.gate.evaluated" } \| count_over_time()` |
| 3 | Invocations opened | stat | How many times was a human asked? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.opened" } \| count_over_time()` |
| 4 | Invocations answered | stat | How many human gates got an answer? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" } \| count_over_time()` |
| 5 | Invocations timed out | stat | How many human gates timed out? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.timed_out" } \| count_over_time()` |
| 6 | Gate evaluations by level | time series | At which gate level (auto, ask, deny) were gates evaluated? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.gate.evaluated" } \| count_over_time() by (span.hitl.gate.level)` |
| 7 | Gate evaluations by human requirement | bar gauge | How many gate evaluations required a human? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.gate.evaluated" } \| count_over_time() by (span.hitl.gate.required)` |
| 8 | Gate evaluations by persona tier | bar gauge | Which persona tier were gates evaluated for? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.gate.evaluated" } \| count_over_time() by (span.hitl.gate.persona_tier)` |
| 9 | Invocations opened by placement | time series | Where in the workflow was a human asked (pre-action, sub-agent boundary, validator escalation)? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.opened" } \| count_over_time() by (span.hitl.invocation.placement)` |
| 10 | Responses by class | time series | How did operators answer (approve, edit, reject, respond)? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" } \| count_over_time() by (span.hitl.response.class)` |
| 11 | Response latency p50 and p95 | time series | How long did operators take to answer (milliseconds)? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" && span.hitl.response.latency_ms >= 0.0 } \| quantile_over_time(span.hitl.response.latency_ms, .5, .95)` |
| 12 | Slow responses (over 60 s) | stat | How many answers took longer than one minute? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" && span.hitl.response.latency_ms > 60000.0 } \| count_over_time()` |
| 13 | Responses by ingress | bar gauge | Through which channel did answers arrive? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" } \| count_over_time() by (span.hitl.response.ingress)` |
| 14 | Timeouts by degradation mode | time series | What did the harness do when a gate timed out (fail-closed, fail-open, escalate)? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.timed_out" } \| count_over_time() by (span.hitl.timeout.degradation_mode_applied)` |
| 15 | Operator-burden evaluations by decision | time series | How often did the operator-burden check ask to degrade? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.operator_burden.evaluated" } \| count_over_time() by (span.hitl.operator_burden.degrade)` |
| 16 | Operator-burden cumulative invocations | time series | How high did the cumulative invocation count get, per persona tier? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.operator_burden.evaluated" && span.hitl.operator_burden.cumulative_invocations >= 0 } \| max_over_time(span.hitl.operator_burden.cumulative_invocations) by (span.hitl.operator_burden.persona_tier)` |
| 17 | Policy overrides refused | time series | On which spans was a policy override refused? | `{ resource.service.namespace =~ "$namespace" && span.sandbox.fail.class = "policy_override" } \| count_over_time() by (name)` |
| 18 | Webhook delivery attempts by status | time series | Which HTTP status did gate webhook attempts get? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.webhook.attempt" } \| count_over_time() by (span.webhook.status_code)` |
| 19 | Pauses by reason | time series | Why were workflows paused (for example a pending human gate)? | `{ resource.service.namespace =~ "$namespace" && name = "pause.captured" } \| count_over_time() by (span.pause.reason)` |
| 20 | Recent gate invocations | table | Which gates were opened most recently, at which level and placement? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.opened" } \| select(span.hitl.gate.level, span.hitl.invocation.placement, span.hitl.invocation.handoff_context_size_bytes, span.hitl.invocation.audit_ledger_entry_id)` |
| 21 | Recent answers and timeouts | table | Which gates were answered or timed out most recently? | `{ resource.service.namespace =~ "$namespace" && (name = "hitl.invocation.responded" \|\| name = "hitl.invocation.timed_out") } \| select(span.hitl.response.class, span.hitl.response.latency_ms, span.hitl.response.ingress, span.hitl.timeout.duration_ms, span.hitl.timeout.degradation_mode_applied)` |

## Arhugula · Validators

File `validators.json`, uid `arhugula-validators`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | Validator checks | stat | How many validator checks ran? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" } \| count_over_time()` |
| 3 | Checks that did not pass | stat | How many validator checks ended in something other than pass? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.outcome != "pass" } \| count_over_time()` |
| 4 | Permanent failures | stat | How many validator checks failed permanently? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.outcome = "permanent_fail" } \| count_over_time()` |
| 5 | Escalations | stat | How many validator failures were escalated to a human? | `{ resource.service.namespace =~ "$namespace" && name = "validator.escalation" } \| count_over_time()` |
| 6 | Outcomes | time series | How did validator checks end over time (pass, revalidate, escalate, permanent_fail, operator_burden_exceeded)? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" } \| count_over_time() by (span.validator.outcome)` |
| 7 | Outcomes per step | bar gauge | Which steps pass or fail validation? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" } \| count_over_time() by (span.step.id, span.validator.outcome)` |
| 8 | Fail classes | time series | Which fail classes occur (schema violation, semantic inconsistency, safety policy, …)? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.fail.class != nil } \| count_over_time() by (span.validator.fail.class)` |
| 9 | Next action after a failed check | bar gauge | What did the harness do next after a failed check (retry, escalate, abort)? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.fail.next_action != nil } \| count_over_time() by (span.validator.fail.next_action)` |
| 10 | Checks that owe an escalation | time series | When did a failed check require a human escalation? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.fail.escalation_owed = true } \| count_over_time()` |
| 11 | Escalations by fail class | time series | Which fail classes get escalated to a human? | `{ resource.service.namespace =~ "$namespace" && name = "validator.escalation" } \| count_over_time() by (span.validator.fail.class)` |
| 12 | Escalations per step | bar gauge | Which steps escalate to a human? | `{ resource.service.namespace =~ "$namespace" && name = "validator.escalation" } \| count_over_time() by (span.step.id)` |
| 13 | Revalidations converted to permanent failure | time series | When did a revalidate outcome turn into a permanent failure? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.revalidation.terminal_conversion = "permanent_fail" } \| count_over_time()` |
| 14 | Cumulative burden count per step | time series | How high did the cumulative validator burden count get on each step? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.burden_count_cumulative >= 0 } \| max_over_time(span.validator.burden_count_cumulative) by (span.step.id)` |
| 15 | Recent checks that did not pass | table | Which validator checks failed most recently, on which step and with what class? | `{ resource.service.namespace =~ "$namespace" && name = "validator.evaluate" && span.validator.outcome != "pass" } \| select(span.step.id, span.validator.outcome, span.validator.fail.class, span.validator.fail.next_action, span.validator.fail.escalation_owed)` |
| 16 | Recent escalations | table | Which validator failures were escalated most recently? | `{ resource.service.namespace =~ "$namespace" && name = "validator.escalation" } \| select(span.step.id, span.validator.outcome, span.validator.fail.class)` |

## Arhugula · Cost

File `cost.json`, uid `arhugula-cost`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | Subscription CLI routes show no cost | text | Why do subscription CLI calls show no cost? | (no query) |
| 3 | Attributed cost | stat | How much cost was attributed in the selected time range? | `{ resource.service.namespace =~ "$namespace" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number)` |
| 4 | Spans with a cost | stat | How many LLM and tool calls carry a cost attribute? | `{ resource.service.namespace =~ "$namespace" && span.cost.attributed_number != nil } \| count_over_time()` |
| 5 | LLM calls in total | stat | How many LLM calls ran, priced or not (compare with the priced count)? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| count_over_time()` |
| 6 | Tool calls with a cost | stat | How many tool calls carry a cost attribute? | `{ resource.service.namespace =~ "$namespace" && name = "tool.dispatch" && span.cost.attributed_number != nil } \| count_over_time()` |
| 7 | Attributed cost over time | time series | How did attributed cost develop over time? | `{ resource.service.namespace =~ "$namespace" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number)` |
| 8 | Cost by provider | time series | Which provider accounts for the cost? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number) by (span.gen_ai.provider.name)` |
| 9 | Cost by model | time series | Which model accounts for the cost? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number) by (span.gen_ai.request.model)` |
| 10 | Total cost by provider and model | bar gauge | What is the total cost of each provider and model pair? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number) by (span.gen_ai.provider.name, span.gen_ai.request.model)` |
| 11 | Total cost by workflow | bar gauge | Which workflow accounts for the LLM cost? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number) by (span.gen_ai.conversation.id)` |
| 12 | Tool cost by tool | time series | Which tools account for tool-call cost? | `{ resource.service.namespace =~ "$namespace" && name = "tool.dispatch" && span.cost.attributed_number != nil } \| sum_over_time(span.cost.attributed_number) by (span.tool.contract.name)` |
| 13 | Priced and unpriced LLM calls by provider | time series | How many LLM calls did each provider handle (providers missing from the cost panels are unpriced)? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" } \| count_over_time() by (span.gen_ai.provider.name)` |
| 14 | Priced input tokens by provider | time series | How many input tokens went into the cost calculation? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil && span.gen_ai.usage.input_tokens != nil } \| sum_over_time(span.gen_ai.usage.input_tokens) by (span.gen_ai.provider.name)` |
| 15 | Priced output tokens by provider | time series | How many output tokens went into the cost calculation? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.cost.attributed_number != nil && span.gen_ai.usage.output_tokens != nil } \| sum_over_time(span.gen_ai.usage.output_tokens) by (span.gen_ai.provider.name)` |
| 16 | Recent calls with a cost | table | Which calls were priced most recently, and at what cost? | `{ resource.service.namespace =~ "$namespace" && span.cost.attributed_number != nil } \| select(span.cost.attributed_decimal, span.gen_ai.provider.name, span.gen_ai.request.model, span.gen_ai.usage.input_tokens, span.gen_ai.usage.output_tokens, span.tool.contract.name)` |

## Arhugula · Memory

File `memory.json`, uid `arhugula-memory`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | Memory operations | stat | How many memory operations ran? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" } \| count_over_time()` |
| 3 | Operations with a failure class | stat | How many memory operations carry a failure class? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.failure_class != nil } \| count_over_time()` |
| 4 | Denials | stat | How many memory operations were denials? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.operation.name = "denial" } \| count_over_time()` |
| 5 | Memory tool calls | stat | How many times did a model call a memory tool? | `{ resource.service.namespace =~ "$namespace" && name = "memory.tool_call" } \| count_over_time()` |
| 6 | Operations by name | time series | Which memory operations ran over time? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" } \| count_over_time() by (span.memory.operation.name)` |
| 7 | Operations by kind | bar gauge | Which kinds of memory operation ran? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.operation.kind != nil } \| count_over_time() by (span.memory.operation.kind)` |
| 8 | Operations by access mode | bar gauge | Through which access mode did memory reach the model? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.access_mode != nil } \| count_over_time() by (span.memory.access_mode)` |
| 9 | Operations by policy decision | time series | What did the memory policy decide (allowed, denied, a denial reason, …)? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.policy.decision != nil } \| count_over_time() by (span.memory.policy.decision)` |
| 10 | Failures by class | time series | Which failure classes occur on memory operations? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.failure_class != nil } \| count_over_time() by (span.memory.failure_class)` |
| 11 | Denials by reason | time series | Why were memory operations denied? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.operation.name = "denial" } \| count_over_time() by (span.memory.policy.decision)` |
| 12 | Degraded serves by reason | time series | When was memory served in a degraded way, and why? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.degraded_serve = true } \| count_over_time() by (span.memory.degraded_serve.reason)` |
| 13 | Records by operation | time series | How many memory records did each operation involve? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.record_count != nil } \| sum_over_time(span.memory.record_count) by (span.memory.operation.name)` |
| 14 | Operations by tier | bar gauge | Which memory tier did operations touch? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.tier != nil } \| count_over_time() by (span.memory.tier)` |
| 15 | Operations by provider | bar gauge | For which provider did memory operations run? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.provider != nil } \| count_over_time() by (span.memory.provider)` |
| 16 | Bytes read | time series | How many bytes did the native memory tool read, per backend? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.bytes_read != nil } \| sum_over_time(span.memory.bytes_read) by (span.memory.backend)` |
| 17 | Bytes written | time series | How many bytes did the native memory tool write, per backend? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.bytes_written != nil } \| sum_over_time(span.memory.bytes_written) by (span.memory.backend)` |
| 18 | Memory tool calls by tool | time series | Which memory tools did models call? | `{ resource.service.namespace =~ "$namespace" && name = "memory.tool_call" } \| count_over_time() by (span.memory.tool.name)` |
| 19 | Memory tool calls by policy decision | time series | Were memory tool calls allowed, denied or failed? | `{ resource.service.namespace =~ "$namespace" && name = "memory.tool_call" && span.memory.policy.decision != nil } \| count_over_time() by (span.memory.policy.decision)` |
| 20 | Memory tool call failures by class | time series | Which failure classes occur on memory tool calls? | `{ resource.service.namespace =~ "$namespace" && name = "memory.tool_call" && span.memory.failure_class != nil } \| count_over_time() by (span.memory.failure_class)` |
| 21 | Unserved memory tool calls | time series | How many memory tool calls did the harness leave unserved? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.unserved_tool_call.count != nil } \| sum_over_time(span.memory.unserved_tool_call.count) by (span.memory.unserved_tool_call.reason)` |
| 22 | Recent failures and denials | table | Which memory operations failed or were denied most recently? | `{ resource.service.namespace =~ "$namespace" && name = "memory.operation" && span.memory.failure_class != nil } \| select(span.memory.operation.name, span.memory.operation.kind, span.memory.failure_class, span.memory.policy.decision, span.memory.access_mode, span.memory.provider, span.memory.model)` |
| 23 | Recent memory tool calls | table | Which memory tool calls ran most recently? | `{ resource.service.namespace =~ "$namespace" && name = "memory.tool_call" } \| select(span.memory.tool.name, span.memory.policy.decision, span.memory.record_count, span.memory.failure_class, span.memory.provider, span.memory.model)` |

## Arhugula · Evaluation

File `evaluation.json`, uid `arhugula-evaluation`.

| # | Panel title | Kind | Question it answers | TraceQL |
|---|---|---|---|---|
| 1 | About this dashboard | text | Explains what this dashboard or section shows. | (no query) |
| 2 | Primitive 1 · expected_hitl_invocations_per_session | text | What do the primitive 1 panels show? | (no query) |
| 3 | Answered human gates | stat | How many human gates were answered (the counter behind primitive 1)? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" } \| count_over_time()` |
| 4 | Workflow runs | stat | How many workflow runs (sessions) ran, to divide the counters by? | `{ resource.service.namespace =~ "$namespace" && name = "workflow.envelope" } \| count_over_time()` |
| 5 | Answered human gates over time | time series | When were human gates answered, and how? | `{ resource.service.namespace =~ "$namespace" && name = "hitl.invocation.responded" } \| count_over_time() by (span.hitl.response.class)` |
| 6 | Primitive 2 · expected_sandbox_violations_per_session | text | What do the primitive 2 panels show? | (no query) |
| 7 | Sandbox violations | stat | How many sandbox violations occurred (the counter behind primitive 2)? | `{ resource.service.namespace =~ "$namespace" && name = "sandbox.violation" } \| count_over_time()` |
| 8 | Sandbox violations by fail class | bar gauge | Which sandbox fail classes occurred? | `{ resource.service.namespace =~ "$namespace" && name = "sandbox.violation" } \| count_over_time() by (span.sandbox.fail.class)` |
| 9 | Sandbox violations over time | time series | When did sandbox violations occur, and of which MCP fail class? | `{ resource.service.namespace =~ "$namespace" && name = "sandbox.violation" } \| count_over_time() by (span.mcp.fail.class)` |
| 10 | Primitive 3 · sandbox_tier_routing_accuracy | text | Why is there no panel for primitive 3? | (no query) |
| 11 | Primitive 5 · routing_accuracy_holdout | text | Why is there no panel for primitive 5? | (no query) |
| 12 | Primitive 4 · cache_hit_rate_alignment_floor | text | What do the primitive 4 panels show? | (no query) |
| 13 | Cache read input tokens | stat | How many input tokens were read from the Anthropic prompt cache? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.anthropic.cache_read_input_tokens != nil } \| sum_over_time(span.anthropic.cache_read_input_tokens)` |
| 14 | Cache creation input tokens | stat | How many input tokens were written to the Anthropic prompt cache? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.anthropic.cache_creation_input_tokens != nil } \| sum_over_time(span.anthropic.cache_creation_input_tokens)` |
| 15 | Cache read input tokens by model | time series | How did cache reads develop over time, per model? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.anthropic.cache_read_input_tokens != nil } \| sum_over_time(span.anthropic.cache_read_input_tokens) by (span.gen_ai.request.model)` |
| 16 | Cache creation input tokens by model | time series | How did cache writes develop over time, per model? | `{ resource.service.namespace =~ "$namespace" && name =~ "chat .*" && span.anthropic.cache_creation_input_tokens != nil } \| sum_over_time(span.anthropic.cache_creation_input_tokens) by (span.gen_ai.request.model)` |
| 17 | Evaluation score spans and drift events | text | Why can the score and drift panels be empty? | (no query) |
| 18 | Evaluation scores by primitive | time series | What average score did each evaluation primitive record? | `{ resource.service.namespace =~ "$namespace" && name =~ "eval .*" && span.eval.value >= 0.0 } \| avg_over_time(span.eval.value) by (span.eval.primitive)` |
| 19 | Drift events | stat | How many alignment-floor drift events were recorded? | `{ resource.service.namespace =~ "$namespace" && event:name = "gen_ai.eval.alignment_floor.drift_detected" } \| count_over_time()` |
| 20 | Drift events by primitive | time series | Which primitive fell below its alignment floor, and when? | `{ resource.service.namespace =~ "$namespace" && event:name = "gen_ai.eval.alignment_floor.drift_detected" } \| count_over_time() by (event.gen_ai.eval.primitive)` |
| 21 | Recent drift events | table | Which drift events were recorded most recently, with what value against what threshold? | `{ resource.service.namespace =~ "$namespace" && event:name = "gen_ai.eval.alignment_floor.drift_detected" } \| select(event.gen_ai.eval.primitive, event.gen_ai.eval.alignment_floor.current, event.gen_ai.eval.alignment_floor.threshold, event.gen_ai.eval.alignment_floor.observation_window)` |

## Alert rules

File `arhugula-rules.yaml`, rule group `arhugula-harness`, folder "Arhugula Harness", evaluated every minute. Each rule fires as soon as its condition holds (`for: 0s`), treats "no series" as healthy, and goes to Grafana's default contact point.

| Rule (uid) | Condition | TraceQL (instant query) | Window | Threshold | Where the threshold came from |
|---|---|---|---|---|---|
| Arhugula · Workflow run failed (`arhugula-workflow-failed`) | count of failed workflow runs in the last 10 minutes, per project and workflow | `{ name = "workflow.envelope" && span.workflow.outcome = "failed" } \| count_over_time() by (resource.service.namespace, span.workflow.id)` | last 10 minutes | > 0 | Kit default (any failure). The reference states no threshold for failed runs. |
| Arhugula · Fallback chain exhausted (`arhugula-fallback-exhausted`) | count of spans carrying a fallback.exhausted event in the last 10 minutes, per project | `{ event:name = "fallback.exhausted" } \| count_over_time() by (resource.service.namespace)` | last 10 minutes | > 0 | Kit default (any event). The reference states no threshold; the event itself marks a dispatch with no candidate left (reference 5.3). |
| Arhugula · Circuit breaker opened (`arhugula-breaker-opened`) | count of spans carrying a breaker.tripped event whose new state is open in the last 10 minutes, per project | `{ event:name = "breaker.tripped" && event.harness.breaker.to_state = "open" } \| count_over_time() by (resource.service.namespace)` | last 10 minutes | > 0 | Kit default (any opening). The reference states no threshold; it states that breaker.tripped is written for every state transition, so the rule filters on to_state = open (reference 5.3). |
| Arhugula · Human gate timed out (`arhugula-hitl-timeout`) | count of hitl.invocation.timed_out spans in the last 10 minutes, per project | `{ name = "hitl.invocation.timed_out" } \| count_over_time() by (resource.service.namespace)` | last 10 minutes | > 0 | Kit default (any timeout). The reference states no threshold for gate timeouts. |
| Arhugula · Validator failed permanently (`arhugula-validator-permanent-fail`) | count of validator.evaluate spans with outcome permanent_fail in the last 10 minutes, per project | `{ name = "validator.evaluate" && span.validator.outcome = "permanent_fail" } \| count_over_time() by (resource.service.namespace)` | last 10 minutes | > 0 | Kit default (any permanent failure). The reference states no threshold; permanence is read from validator.outcome because validator.fail.permanence is never written (reference 5.5). |
| Arhugula · Attributed cost above threshold (`arhugula-cost-threshold`) | sum of attributed cost (US dollars) in the last hour, per project | `{ span.cost.attributed_number > 0.0 } \| sum_over_time(span.cost.attributed_number) by (resource.service.namespace)` | last 60 minutes | > 1 | Kit default (1 US dollar per hour per project). Reference section 8 states rates but no budget threshold. |
| Arhugula · Alignment-floor drift detected (`arhugula-alignment-floor-drift`) | count of spans carrying a gen_ai.eval.alignment_floor.drift_detected event in the last 10 minutes, per project | `{ event:name = "gen_ai.eval.alignment_floor.drift_detected" } \| count_over_time() by (resource.service.namespace)` | last 10 minutes | > 0 | Reference 7.2: the harness emits the event only when current value < the operator's threshold_value, so any event is a breach. The floor itself has no default in code; the operator sets it. |
