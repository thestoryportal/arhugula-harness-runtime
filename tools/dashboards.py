"""The kit's Grafana dashboards, alert rules and panel index, from one definition.

    python3 tools/dashboards.py write     rewrite observability/dashboards/*.json,
                                          observability/alerting/arhugula-rules.yaml and
                                          observability/PANELS.md
    python3 tools/dashboards.py check     exit 1 when any of those files is stale

Every panel is one call below: its title, the question it answers and its TraceQL query.
The JSON files Grafana loads, the alert-rule YAML and the panel index are all rendered
from those calls, so the three cannot disagree. Change a panel here, run `write`, then
`arhugula observability up` to load it. Use only span names and attribute keys the
runtime emits; a query on a key that does not exist shows "No data" for ever.
"""
import json, sys, os

KIT_OBSERVABILITY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "observability")
OUT_DASH = os.path.join(KIT_OBSERVABILITY, "dashboards")
OUT_ALERT = os.path.join(KIT_OBSERVABILITY, "alerting")
OUT_INDEX = os.path.join(KIT_OBSERVABILITY, "PANELS.md")

DS = {"type": "tempo", "uid": "tempo"}
NS = 'resource.service.namespace =~ "$namespace"'
RANGE_NOTE = "The stack keeps traces for 24 hours, so no panel can look further back than that."

def q(body, pipe=None):
    """A TraceQL query scoped to the selected project."""
    s = '{ ' + NS + ' && ' + body + ' }'
    return s + (' | ' + pipe if pipe else '')

def _base(kind, title, desc, w, h):
    return {"type": kind, "title": title, "description": desc, "datasource": DS, "_w": w, "_h": h}

def text(title, content, w=24, h=4, desc=None):
    p = _base("text", title, desc or "Explains what this dashboard or section shows.", w, h)
    p["options"] = {"mode": "markdown", "content": content}
    p["_query"] = None
    return p

def _target(query, **kw):
    t = {"refId": "A", "datasource": DS, "queryType": "traceql", "query": query, "filters": [], "limit": 20, "tableType": "traces"}
    t.update(kw)
    return t

NEUTRAL = [{"color": "blue", "value": None}]
BAD = [{"color": "green", "value": None}, {"color": "red", "value": 1}]

def stat(title, desc, query, unit="short", bad=False, w=6, h=4, decimals=None):
    p = _base("stat", title, desc, w, h)
    p["targets"] = [_target(query, metricsQueryType="instant")]
    p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "value", "graphMode": "none", "justifyMode": "auto", "orientation": "auto", "textMode": "auto"}
    d = {"unit": unit, "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": BAD if bad else NEUTRAL}}
    if decimals is not None: d["decimals"] = decimals
    p["fieldConfig"] = {"defaults": d, "overrides": []}
    p["_query"] = query; p["_kind"] = "instant"
    return p

def bars(title, desc, query, unit="short", w=8, h=7, decimals=None):
    p = _base("bargauge", title, desc, w, h)
    p["targets"] = [_target(query, metricsQueryType="instant")]
    p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True, "valueMode": "color",
                    "namePlacement": "auto", "sizing": "auto", "minVizHeight": 16, "minVizWidth": 8, "maxVizHeight": 300,
                    "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []}}
    d = {"unit": unit, "min": 0, "color": {"mode": "palette-classic"}, "thresholds": {"mode": "absolute", "steps": NEUTRAL}}
    if decimals is not None: d["decimals"] = decimals
    p["fieldConfig"] = {"defaults": d, "overrides": []}
    p["_query"] = query; p["_kind"] = "instant"
    return p

def ts(title, desc, query, unit="short", style="bars", w=12, h=8, decimals=None):
    p = _base("timeseries", title, desc, w, h)
    p["targets"] = [_target(query, metricsQueryType="range")]
    custom = {"drawStyle": style, "lineWidth": 1, "fillOpacity": 60 if style == "bars" else 10,
              "showPoints": "auto", "pointSize": 5, "spanNulls": False, "axisPlacement": "auto",
              "stacking": {"mode": "normal" if style == "bars" else "none", "group": "A"}}
    d = {"unit": unit, "min": 0, "color": {"mode": "palette-classic"}, "custom": custom}
    if decimals is not None: d["decimals"] = decimals
    p["fieldConfig"] = {"defaults": d, "overrides": []}
    p["options"] = {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom", "calcs": []},
                    "tooltip": {"mode": "multi", "sort": "desc"}}
    p["_query"] = query; p["_kind"] = "range"
    return p

def table(title, desc, query, w=24, h=9, limit=50):
    p = _base("table", title, desc, w, h)
    p["targets"] = [_target(query, tableType="spans", limit=limit, spss=10)]
    p["options"] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False, "reducer": ["sum"], "countRows": False, "fields": ""}}
    p["fieldConfig"] = {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}}, "overrides": []}
    p["_query"] = query; p["_kind"] = "search"
    return p

CHAT = 'name =~ "chat .*"'
ATT = 'name = "harness.runtime.retry_attempt"'
RBF = 'name = "harness.runtime.retry_breaker_fallback"'
MEM = 'name = "memory.operation"'
VAL = 'name = "validator.evaluate"'

DASHBOARDS = []

# ---------------------------------------------------------------- genai
DASHBOARDS.append(dict(file="genai.json", uid="arhugula-genai", title="Arhugula · LLM calls", panels=[
    text("About this dashboard",
         "**Answers:** how many LLM calls ran, how fast, on which provider and model, how many tokens they used, and which calls failed.\n\n"
         "**Data comes from:** every workflow step that dispatches to a model. Each dispatch writes one `chat <model>` span. "
         "Runs on any provider produce data; token counts appear only for API-metered providers and Ollama, "
         "while subscription CLI routes (`claude_code`, `codex`, `gemini`, `antigravity`) report tokens as `external_cli.usage.*` evidence instead.\n\n" + RANGE_NOTE, h=6),
    stat("LLM calls", "How many LLM calls ran in the selected time range?", q(CHAT, 'count_over_time()')),
    stat("Failed LLM calls", "How many LLM calls ended with an error status?", q(CHAT + ' && status = error', 'count_over_time()'), bad=True),
    stat("Input tokens", "How many input tokens did providers report?", q(CHAT + ' && span.gen_ai.usage.input_tokens != nil', 'sum_over_time(span.gen_ai.usage.input_tokens)')),
    stat("Output tokens", "How many output tokens did providers report?", q(CHAT + ' && span.gen_ai.usage.output_tokens != nil', 'sum_over_time(span.gen_ai.usage.output_tokens)')),
    ts("Call rate by provider", "How many LLM calls per second went to each provider?", q(CHAT, 'rate() by (span.gen_ai.provider.name)'), unit="reqps", style="line"),
    ts("Call rate by model", "How many LLM calls per second went to each model?", q(CHAT, 'rate() by (span.gen_ai.request.model)'), unit="reqps", style="line"),
    ts("Latency p50 and p95 by provider", "How long does an LLM call take on each provider (median and 95th percentile of span duration)?", q(CHAT, 'quantile_over_time(duration, .5, .95) by (span.gen_ai.provider.name)'), unit="s", style="line"),
    ts("Latency p50 and p95 by model", "How long does an LLM call take on each model (median and 95th percentile of span duration)?", q(CHAT, 'quantile_over_time(duration, .5, .95) by (span.gen_ai.request.model)'), unit="s", style="line"),
    ts("Input tokens by model", "How many provider-reported input tokens did each model consume over time?", q(CHAT + ' && span.gen_ai.usage.input_tokens != nil', 'sum_over_time(span.gen_ai.usage.input_tokens) by (span.gen_ai.request.model)')),
    ts("Output tokens by model", "How many provider-reported output tokens did each model produce over time?", q(CHAT + ' && span.gen_ai.usage.output_tokens != nil', 'sum_over_time(span.gen_ai.usage.output_tokens) by (span.gen_ai.request.model)')),
    ts("CLI-reported input tokens (subscription routes)", "How many input tokens did subscription CLI routes report as usage evidence?", q(CHAT + ' && span.external_cli.usage.input_tokens != nil', 'sum_over_time(span.external_cli.usage.input_tokens) by (span.gen_ai.provider.name)')),
    ts("CLI-reported output tokens (subscription routes)", "How many output tokens did subscription CLI routes report as usage evidence?", q(CHAT + ' && span.external_cli.usage.output_tokens != nil', 'sum_over_time(span.external_cli.usage.output_tokens) by (span.gen_ai.provider.name)')),
    bars("Provider mix", "Which share of LLM calls went to each provider?", q(CHAT, 'count_over_time() by (span.gen_ai.provider.name)')),
    bars("Model mix", "Which share of LLM calls went to each model?", q(CHAT, 'count_over_time() by (span.gen_ai.request.model)')),
    bars("Calls by routing layer", "Which routing layer chose the model for each call?", q(CHAT + ' && span.routing.layer != nil', 'count_over_time() by (span.routing.layer)')),
    ts("Failed calls by model", "Which models produce failed calls, and when?", q(CHAT + ' && status = error', 'count_over_time() by (span.gen_ai.request.model)')),
    ts("Failed subscription CLI calls", "Which subscription CLI routes exited with a non-zero exit code?", q(CHAT + ' && span.external_cli.exit_code != 0', 'count_over_time() by (span.external_cli.provider.kind)')),
    text("Finish reasons",
         "**Finish reasons are not available.** The harness declares `gen_ai.response.finish_reasons` but never writes it to a span, "
         "so no panel can show why a model stopped. A failed call is visible only as an error status on its `chat <model>` span.", w=24, h=3,
         desc="Why is there no finish-reason panel?"),
    table("Recent LLM calls", "Which LLM calls ran most recently, and with what provider, model, tokens and status?",
          q(CHAT, 'select(span.gen_ai.provider.name, span.gen_ai.request.model, span.routing.layer, span.gen_ai.usage.input_tokens, span.gen_ai.usage.output_tokens, status)')),
    table("Recent failed LLM calls", "Which LLM calls failed most recently?",
          q(CHAT + ' && status = error', 'select(span.gen_ai.provider.name, span.gen_ai.request.model, span.routing.binding_rationale, statusMessage)')),
]))

# ---------------------------------------------------------------- routing-resilience
DASHBOARDS.append(dict(file="routing-resilience.json", uid="arhugula-routing-resilience", title="Arhugula · Routing and resilience", panels=[
    text("About this dashboard",
         "**Answers:** how often a dispatch had to retry, how each attempt ended, when the fallback chain was used or exhausted, "
         "when a circuit breaker changed state, and where timeouts showed up.\n\n"
         "**Data comes from:** every LLM step (one `harness.runtime.retry_breaker_fallback` span with one `harness.runtime.retry_attempt` span per attempt) "
         "and every tool step (`harness.runtime.retry_tool_dispatch` and `harness.runtime.tool_retry_attempt`). "
         "Fallback and breaker facts are span *events* on those spans, so they appear only when a run meets a failing or unavailable model.\n\n" + RANGE_NOTE, h=6),
    stat("LLM attempts", "How many LLM dispatch attempts ran?", q(ATT, 'count_over_time()')),
    stat("Retried attempts", "How many attempts were a second or later try?", q(ATT + ' && span.retry.attempt_number > 1', 'count_over_time()'), bad=True),
    stat("Exhausted fallback chains", "How many dispatches ran out of candidates?", q('event:name = "fallback.exhausted"', 'count_over_time()'), bad=True),
    stat("Breakers opened", "How many times did a circuit breaker open?", q('event:name = "breaker.tripped" && event.harness.breaker.to_state = "open"', 'count_over_time()'), bad=True),
    ts("Attempts by terminal outcome", "How did LLM attempts end (success, retry, max-attempts, fail-fast, escalate, …)?", q(ATT + ' && span.retry.terminal != nil', 'count_over_time() by (span.retry.terminal)')),
    ts("Attempts by attempt number", "How many attempts were first, second or later tries?", q(ATT, 'count_over_time() by (span.retry.attempt_number)')),
    ts("Failed attempts by fail class", "Which fail class did failed LLM attempts carry?", q(ATT + ' && span.retry.fail_class != nil', 'count_over_time() by (span.retry.fail_class)')),
    bars("Failed attempts by cause", "What caused failed LLM attempts (classified cause or exception class)?", q(ATT + ' && span.retry.cause_attribution != nil', 'count_over_time() by (span.retry.cause_attribution)'), w=12, h=8),
    ts("Tool attempts by terminal outcome", "How did tool dispatch attempts end?", q('name = "harness.runtime.tool_retry_attempt" && span.retry.terminal != nil', 'count_over_time() by (span.retry.terminal)')),
    ts("Breaker charge waived", "How often was a failure not charged to the breaker, and why?", q(ATT + ' && span.retry.breaker_waived.reason != nil', 'count_over_time() by (span.retry.breaker_waived.reason)')),
    bars("Dispatches by fallback chain length", "How many candidates did the fallback chain hold for each dispatch?", q(RBF, 'count_over_time() by (span.fallback.chain_length)')),
    ts("fallback.triggered events", "When did the capability pre-check skip a candidate, and for what cause?", q('event:name = "fallback.triggered"', 'count_over_time() by (event.fallback.cause)'), w=8),
    ts("fallback.exhausted events", "When did a dispatch run out of candidates, and for what cause?", q('event:name = "fallback.exhausted"', 'count_over_time() by (event.fallback.exhaustion_cause)'), w=8),
    bars("Exhaustion by last failure class", "What was the last failure before a fallback chain was exhausted?", q('event:name = "fallback.exhausted"', 'count_over_time() by (event.fallback.last_failure_class)')),
    ts("retry.skipped events", "When was a candidate skipped because its breaker was open or on trial?", q('event:name = "retry.skipped"', 'count_over_time() by (event.retry.skipped.reason)'), w=8),
    ts("breaker.tripped events by new state", "When did a breaker change state, and to which state (open, half_open, closed)?", q('event:name = "breaker.tripped"', 'count_over_time() by (event.harness.breaker.to_state)'), w=8),
    bars("Breaker openings by cause", "Why did breakers open (rate limit, auth failure, 5xx streak, capability shortfall)?", q('event:name = "breaker.tripped" && event.harness.breaker.to_state = "open"', 'count_over_time() by (event.harness.breaker.cause)')),
    ts("tool_retry.exhausted events", "When did a tool dispatch use up its attempts?", q('event:name = "tool_retry.exhausted"', 'count_over_time() by (event.tool_retry.last_failure_class)'), w=8),
    text("Timeout signals",
         "**No span carries a deadline or timeout attribute.** A timeout is visible only through the four signals below: "
         "a HITL gate timeout span, a tool timeout on `sandbox.violation`, a provider attempt that ended `retry` or `max-attempts`, "
         "and an error status on the span an exception left. The failed-run table shows the free-text `workflow.fail_class` of each failed run.", w=24, h=3,
         desc="Where do timeouts show up?"),
    ts("HITL gate timeouts", "When did a human gate time out, and which degradation mode applied?", q('name = "hitl.invocation.timed_out"', 'count_over_time() by (span.hitl.timeout.degradation_mode_applied)'), w=6),
    ts("Tool invocation timeouts", "When did a tool call time out in the sandbox?", q('name = "sandbox.violation" && span.mcp.fail.class = "timeout"', 'count_over_time()'), w=6),
    ts("Provider attempts ending retry or max-attempts", "When did provider calls fail transiently (including provider timeouts)?", q(ATT + ' && (span.retry.terminal = "retry" || span.retry.terminal = "max-attempts")', 'count_over_time() by (span.retry.terminal)'), w=6),
    ts("Spans that ended with an error", "Which spans did an exception leave, and when?", q('status = error', 'count_over_time() by (name)'), w=6),
    table("Recent failed workflow runs", "Which workflow runs failed most recently, and with what fail class?",
          q('name = "workflow.envelope" && span.workflow.outcome = "failed"', 'select(span.workflow.id, span.workflow.run_id, span.workflow.fail_class, span.workflow.topology_pattern)')),
    table("Recent attempts that did not succeed", "Which attempts ended in something other than success?",
          q(ATT + ' && span.retry.terminal != "success"', 'select(span.retry.attempt_number, span.retry.terminal, span.retry.cause_attribution, span.retry.fail_class, span.retry.delay_ms)')),
    table("Recent exhausted fallback chains", "Which dispatches ran out of candidates most recently, and why?",
          q('event:name = "fallback.exhausted"', 'select(span.fallback.chain_length, event.fallback.exhaustion_cause, event.fallback.last_failure_class, event.fallback.last_failure_detail)')),
]))

# ---------------------------------------------------------------- hitl
DASHBOARDS.append(dict(file="hitl.json", uid="arhugula-hitl", title="Arhugula · Human-in-the-loop gates", panels=[
    text("About this dashboard",
         "**Answers:** how often a human gate was evaluated and at which level, how many invocations were opened, answered or timed out, "
         "how operators answered and how quickly, and whether the operator-burden check asked to degrade.\n\n"
         "**Data comes from:** workflows whose steps or tools carry a gate level of `ask` or `deny`, sub-agent boundaries with a gate, "
         "and validator escalations. Workflows with no gate produce no data here, and every panel then shows \"No data\".\n\n" + RANGE_NOTE, h=6),
    stat("Gate evaluations", "How many gate evaluations ran?", q('name = "hitl.gate.evaluated"', 'count_over_time()')),
    stat("Invocations opened", "How many times was a human asked?", q('name = "hitl.invocation.opened"', 'count_over_time()')),
    stat("Invocations answered", "How many human gates got an answer?", q('name = "hitl.invocation.responded"', 'count_over_time()')),
    stat("Invocations timed out", "How many human gates timed out?", q('name = "hitl.invocation.timed_out"', 'count_over_time()'), bad=True),
    ts("Gate evaluations by level", "At which gate level (auto, ask, deny) were gates evaluated?", q('name = "hitl.gate.evaluated"', 'count_over_time() by (span.hitl.gate.level)')),
    bars("Gate evaluations by human requirement", "How many gate evaluations required a human?", q('name = "hitl.gate.evaluated"', 'count_over_time() by (span.hitl.gate.required)'), w=6, h=8),
    bars("Gate evaluations by persona tier", "Which persona tier were gates evaluated for?", q('name = "hitl.gate.evaluated"', 'count_over_time() by (span.hitl.gate.persona_tier)'), w=6, h=8),
    ts("Invocations opened by placement", "Where in the workflow was a human asked (pre-action, sub-agent boundary, validator escalation)?", q('name = "hitl.invocation.opened"', 'count_over_time() by (span.hitl.invocation.placement)')),
    ts("Responses by class", "How did operators answer (approve, edit, reject, respond)?", q('name = "hitl.invocation.responded"', 'count_over_time() by (span.hitl.response.class)')),
    ts("Response latency p50 and p95", "How long did operators take to answer (milliseconds)?", q('name = "hitl.invocation.responded" && span.hitl.response.latency_ms >= 0.0', 'quantile_over_time(span.hitl.response.latency_ms, .5, .95)'), unit="ms", style="line"),
    stat("Slow responses (over 60 s)", "How many answers took longer than one minute?", q('name = "hitl.invocation.responded" && span.hitl.response.latency_ms > 60000.0', 'count_over_time()'), w=6, h=8),
    bars("Responses by ingress", "Through which channel did answers arrive?", q('name = "hitl.invocation.responded"', 'count_over_time() by (span.hitl.response.ingress)'), w=6, h=8),
    ts("Timeouts by degradation mode", "What did the harness do when a gate timed out (fail-closed, fail-open, escalate)?", q('name = "hitl.invocation.timed_out"', 'count_over_time() by (span.hitl.timeout.degradation_mode_applied)')),
    ts("Operator-burden evaluations by decision", "How often did the operator-burden check ask to degrade?", q('name = "hitl.operator_burden.evaluated"', 'count_over_time() by (span.hitl.operator_burden.degrade)')),
    ts("Operator-burden cumulative invocations", "How high did the cumulative invocation count get, per persona tier?", q('name = "hitl.operator_burden.evaluated" && span.hitl.operator_burden.cumulative_invocations >= 0', 'max_over_time(span.hitl.operator_burden.cumulative_invocations) by (span.hitl.operator_burden.persona_tier)'), style="line"),
    ts("Policy overrides refused", "On which spans was a policy override refused?", q('span.sandbox.fail.class = "policy_override"', 'count_over_time() by (name)')),
    ts("Webhook delivery attempts by status", "Which HTTP status did gate webhook attempts get?", q('name = "hitl.webhook.attempt"', 'count_over_time() by (span.webhook.status_code)')),
    ts("Pauses by reason", "Why were workflows paused (for example a pending human gate)?", q('name = "pause.captured"', 'count_over_time() by (span.pause.reason)')),
    table("Recent gate invocations", "Which gates were opened most recently, at which level and placement?",
          q('name = "hitl.invocation.opened"', 'select(span.hitl.gate.level, span.hitl.invocation.placement, span.hitl.invocation.handoff_context_size_bytes, span.hitl.invocation.audit_ledger_entry_id)')),
    table("Recent answers and timeouts", "Which gates were answered or timed out most recently?",
          q('(name = "hitl.invocation.responded" || name = "hitl.invocation.timed_out")', 'select(span.hitl.response.class, span.hitl.response.latency_ms, span.hitl.response.ingress, span.hitl.timeout.duration_ms, span.hitl.timeout.degradation_mode_applied)')),
]))

# ---------------------------------------------------------------- validators
DASHBOARDS.append(dict(file="validators.json", uid="arhugula-validators", title="Arhugula · Validators", panels=[
    text("About this dashboard",
         "**Answers:** how validator checks ended, which steps fail validation, which fail classes occur, and how often a failure was escalated to a human.\n\n"
         "**Data comes from:** workflows whose steps declare a validator. Each check writes one `validator.evaluate` span; "
         "an escalation also writes a `validator.escalation` span. Workflows with no validator produce no data here.\n\n"
         "A permanent failure is `validator.outcome = permanent_fail`. The attribute `validator.fail.permanence` is never written, so no panel uses it.\n\n" + RANGE_NOTE, h=7),
    stat("Validator checks", "How many validator checks ran?", q(VAL, 'count_over_time()')),
    stat("Checks that did not pass", "How many validator checks ended in something other than pass?", q(VAL + ' && span.validator.outcome != "pass"', 'count_over_time()'), bad=True),
    stat("Permanent failures", "How many validator checks failed permanently?", q(VAL + ' && span.validator.outcome = "permanent_fail"', 'count_over_time()'), bad=True),
    stat("Escalations", "How many validator failures were escalated to a human?", q('name = "validator.escalation"', 'count_over_time()'), bad=True),
    ts("Outcomes", "How did validator checks end over time (pass, revalidate, escalate, permanent_fail, operator_burden_exceeded)?", q(VAL, 'count_over_time() by (span.validator.outcome)')),
    bars("Outcomes per step", "Which steps pass or fail validation?", q(VAL, 'count_over_time() by (span.step.id, span.validator.outcome)'), w=12, h=8),
    ts("Fail classes", "Which fail classes occur (schema violation, semantic inconsistency, safety policy, …)?", q(VAL + ' && span.validator.fail.class != nil', 'count_over_time() by (span.validator.fail.class)')),
    bars("Next action after a failed check", "What did the harness do next after a failed check (retry, escalate, abort)?", q(VAL + ' && span.validator.fail.next_action != nil', 'count_over_time() by (span.validator.fail.next_action)'), w=12, h=8),
    ts("Checks that owe an escalation", "When did a failed check require a human escalation?", q(VAL + ' && span.validator.fail.escalation_owed = true', 'count_over_time()')),
    ts("Escalations by fail class", "Which fail classes get escalated to a human?", q('name = "validator.escalation"', 'count_over_time() by (span.validator.fail.class)')),
    bars("Escalations per step", "Which steps escalate to a human?", q('name = "validator.escalation"', 'count_over_time() by (span.step.id)'), w=12, h=8),
    ts("Revalidations converted to permanent failure", "When did a revalidate outcome turn into a permanent failure?", q(VAL + ' && span.validator.revalidation.terminal_conversion = "permanent_fail"', 'count_over_time()')),
    ts("Cumulative burden count per step", "How high did the cumulative validator burden count get on each step?", q(VAL + ' && span.validator.burden_count_cumulative >= 0', 'max_over_time(span.validator.burden_count_cumulative) by (span.step.id)'), style="line", w=24),
    table("Recent checks that did not pass", "Which validator checks failed most recently, on which step and with what class?",
          q(VAL + ' && span.validator.outcome != "pass"', 'select(span.step.id, span.validator.outcome, span.validator.fail.class, span.validator.fail.next_action, span.validator.fail.escalation_owed)')),
    table("Recent escalations", "Which validator failures were escalated most recently?",
          q('name = "validator.escalation"', 'select(span.step.id, span.validator.outcome, span.validator.fail.class)')),
]))

# ---------------------------------------------------------------- cost
COST = 'span.cost.attributed_number != nil'
DASHBOARDS.append(dict(file="cost.json", uid="arhugula-cost", title="Arhugula · Cost", panels=[
    text("About this dashboard",
         "**Answers:** how much cost (US dollars) the harness attributed to LLM calls and tool calls, over time and by provider, model and workflow.\n\n"
         "**Data comes from:** LLM calls on priced providers (`anthropic`, `openai`, and `ollama` at a rate of zero) and tool calls. "
         "The harness writes cost as text in `cost.attributed_decimal`; the kit's collector copies it into the number `cost.attributed_number`, which these panels sum. "
         "Rates come from the harness rate table, whose defaults are placeholders for the operator to override.\n\n" + RANGE_NOTE, h=6, w=12),
    text("Subscription CLI routes show no cost",
         "**Subscription CLI routes are never priced, by design.** Calls through `claude_code`, `codex`, `gemini` and `antigravity` have no rate-table row: "
         "their usage is kept as evidence (`external_cli.usage.*`) and no cost attribute is written. They therefore add nothing to any panel here. "
         "This is expected and does not mean the calls were free of charge under your subscription.\n\n"
         "Local Ollama calls are priced at a rate of zero, so they appear with a cost of 0.", h=6, w=12,
         desc="Why do subscription CLI calls show no cost?"),
    stat("Attributed cost", "How much cost was attributed in the selected time range?", q(COST, 'sum_over_time(span.cost.attributed_number)'), unit="currencyUSD", decimals=4),
    stat("Spans with a cost", "How many LLM and tool calls carry a cost attribute?", q(COST, 'count_over_time()')),
    stat("LLM calls in total", "How many LLM calls ran, priced or not (compare with the priced count)?", q(CHAT, 'count_over_time()')),
    stat("Tool calls with a cost", "How many tool calls carry a cost attribute?", q('name = "tool.dispatch" && ' + COST, 'count_over_time()')),
    ts("Attributed cost over time", "How did attributed cost develop over time?", q(COST, 'sum_over_time(span.cost.attributed_number)'), unit="currencyUSD", decimals=4, w=24),
    ts("Cost by provider", "Which provider accounts for the cost?", q(CHAT + ' && ' + COST, 'sum_over_time(span.cost.attributed_number) by (span.gen_ai.provider.name)'), unit="currencyUSD", decimals=4),
    ts("Cost by model", "Which model accounts for the cost?", q(CHAT + ' && ' + COST, 'sum_over_time(span.cost.attributed_number) by (span.gen_ai.request.model)'), unit="currencyUSD", decimals=4),
    bars("Total cost by provider and model", "What is the total cost of each provider and model pair?", q(CHAT + ' && ' + COST, 'sum_over_time(span.cost.attributed_number) by (span.gen_ai.provider.name, span.gen_ai.request.model)'), unit="currencyUSD", decimals=4, w=12, h=8),
    bars("Total cost by workflow", "Which workflow accounts for the LLM cost?", q(CHAT + ' && ' + COST, 'sum_over_time(span.cost.attributed_number) by (span.gen_ai.conversation.id)'), unit="currencyUSD", decimals=4, w=12, h=8),
    ts("Tool cost by tool", "Which tools account for tool-call cost?", q('name = "tool.dispatch" && ' + COST, 'sum_over_time(span.cost.attributed_number) by (span.tool.contract.name)'), unit="currencyUSD", decimals=4),
    ts("Priced and unpriced LLM calls by provider", "How many LLM calls did each provider handle (providers missing from the cost panels are unpriced)?", q(CHAT, 'count_over_time() by (span.gen_ai.provider.name)')),
    ts("Priced input tokens by provider", "How many input tokens went into the cost calculation?", q(CHAT + ' && ' + COST + ' && span.gen_ai.usage.input_tokens != nil', 'sum_over_time(span.gen_ai.usage.input_tokens) by (span.gen_ai.provider.name)')),
    ts("Priced output tokens by provider", "How many output tokens went into the cost calculation?", q(CHAT + ' && ' + COST + ' && span.gen_ai.usage.output_tokens != nil', 'sum_over_time(span.gen_ai.usage.output_tokens) by (span.gen_ai.provider.name)')),
    table("Recent calls with a cost", "Which calls were priced most recently, and at what cost?",
          q(COST, 'select(span.cost.attributed_decimal, span.gen_ai.provider.name, span.gen_ai.request.model, span.gen_ai.usage.input_tokens, span.gen_ai.usage.output_tokens, span.tool.contract.name)')),
]))

# ---------------------------------------------------------------- memory
MTC = 'name = "memory.tool_call"'
DASHBOARDS.append(dict(file="memory.json", uid="arhugula-memory", title="Arhugula · Memory", panels=[
    text("About this dashboard",
         "**Answers:** which memory operations ran, which failed or were denied, how many records and bytes they moved, and how models used the memory tools.\n\n"
         "**Data comes from:** every LLM step of a workflow run with memory configured (retrieval, ranking, packet assembly, injection, capture, denial), "
         "the Anthropic native memory tool (the only source of byte counts), and the standard memory tools (`memory.tool_call` spans, written when a model calls a memory tool).\n\n"
         "A failure class does not always mean an error: `retrieval_empty_result` and `policy_denial` appear on operations that completed normally.\n\n" + RANGE_NOTE, h=7),
    stat("Memory operations", "How many memory operations ran?", q(MEM, 'count_over_time()')),
    stat("Operations with a failure class", "How many memory operations carry a failure class?", q(MEM + ' && span.memory.failure_class != nil', 'count_over_time()'), bad=True),
    stat("Denials", "How many memory operations were denials?", q(MEM + ' && span.memory.operation.name = "denial"', 'count_over_time()'), bad=True),
    stat("Memory tool calls", "How many times did a model call a memory tool?", q(MTC, 'count_over_time()')),
    ts("Operations by name", "Which memory operations ran over time?", q(MEM, 'count_over_time() by (span.memory.operation.name)')),
    bars("Operations by kind", "Which kinds of memory operation ran?", q(MEM + ' && span.memory.operation.kind != nil', 'count_over_time() by (span.memory.operation.kind)'), w=6, h=8),
    bars("Operations by access mode", "Through which access mode did memory reach the model?", q(MEM + ' && span.memory.access_mode != nil', 'count_over_time() by (span.memory.access_mode)'), w=6, h=8),
    ts("Operations by policy decision", "What did the memory policy decide (allowed, denied, a denial reason, …)?", q(MEM + ' && span.memory.policy.decision != nil', 'count_over_time() by (span.memory.policy.decision)')),
    ts("Failures by class", "Which failure classes occur on memory operations?", q(MEM + ' && span.memory.failure_class != nil', 'count_over_time() by (span.memory.failure_class)')),
    ts("Denials by reason", "Why were memory operations denied?", q(MEM + ' && span.memory.operation.name = "denial"', 'count_over_time() by (span.memory.policy.decision)')),
    ts("Degraded serves by reason", "When was memory served in a degraded way, and why?", q(MEM + ' && span.memory.degraded_serve = true', 'count_over_time() by (span.memory.degraded_serve.reason)')),
    ts("Records by operation", "How many memory records did each operation involve?", q(MEM + ' && span.memory.record_count != nil', 'sum_over_time(span.memory.record_count) by (span.memory.operation.name)')),
    bars("Operations by tier", "Which memory tier did operations touch?", q(MEM + ' && span.memory.tier != nil', 'count_over_time() by (span.memory.tier)'), w=6, h=8),
    bars("Operations by provider", "For which provider did memory operations run?", q(MEM + ' && span.memory.provider != nil', 'count_over_time() by (span.memory.provider)'), w=6, h=8),
    ts("Bytes read", "How many bytes did the native memory tool read, per backend?", q(MEM + ' && span.memory.bytes_read != nil', 'sum_over_time(span.memory.bytes_read) by (span.memory.backend)'), unit="bytes"),
    ts("Bytes written", "How many bytes did the native memory tool write, per backend?", q(MEM + ' && span.memory.bytes_written != nil', 'sum_over_time(span.memory.bytes_written) by (span.memory.backend)'), unit="bytes"),
    ts("Memory tool calls by tool", "Which memory tools did models call?", q(MTC, 'count_over_time() by (span.memory.tool.name)')),
    ts("Memory tool calls by policy decision", "Were memory tool calls allowed, denied or failed?", q(MTC + ' && span.memory.policy.decision != nil', 'count_over_time() by (span.memory.policy.decision)')),
    ts("Memory tool call failures by class", "Which failure classes occur on memory tool calls?", q(MTC + ' && span.memory.failure_class != nil', 'count_over_time() by (span.memory.failure_class)')),
    ts("Unserved memory tool calls", "How many memory tool calls did the harness leave unserved?", q(MEM + ' && span.memory.unserved_tool_call.count != nil', 'sum_over_time(span.memory.unserved_tool_call.count) by (span.memory.unserved_tool_call.reason)')),
    table("Recent failures and denials", "Which memory operations failed or were denied most recently?",
          q(MEM + ' && span.memory.failure_class != nil', 'select(span.memory.operation.name, span.memory.operation.kind, span.memory.failure_class, span.memory.policy.decision, span.memory.access_mode, span.memory.provider, span.memory.model)')),
    table("Recent memory tool calls", "Which memory tool calls ran most recently?",
          q(MTC, 'select(span.memory.tool.name, span.memory.policy.decision, span.memory.record_count, span.memory.failure_class, span.memory.provider, span.memory.model)')),
]))

# ---------------------------------------------------------------- evaluation
DRIFT = 'event:name = "gen_ai.eval.alignment_floor.drift_detected"'
DASHBOARDS.append(dict(file="evaluation.json", uid="arhugula-evaluation", title="Arhugula · Evaluation", panels=[
    text("About this dashboard",
         "**Answers:** what the traces can show about the five operator-burden evaluation primitives, and whether an alignment-floor drift event was recorded.\n\n"
         "**Data comes from:** primitive 1 needs workflows with human gates; primitive 2 needs tool steps that fail in the sandbox; primitive 4 needs calls to the `anthropic` provider with prompt caching. "
         "Primitives 3 and 5 are judged on a holdout set and are not in traces at all. "
         "In this version no normal run writes an evaluation score span or a drift event, so those panels show \"No data\" until an evaluation job emits them.\n\n" + RANGE_NOTE, h=6),
    text("Primitive 1 · expected_hitl_invocations_per_session",
         "Counts answered human gates (`hitl.invocation.responded`). Divide by the number of workflow runs to get the per-session figure; "
         "the declared roll-up dimensions `agent_role` and `workload_class` are not on these spans, so no panel splits by them.", w=24, h=3,
         desc="What do the primitive 1 panels show?"),
    stat("Answered human gates", "How many human gates were answered (the counter behind primitive 1)?", q('name = "hitl.invocation.responded"', 'count_over_time()'), w=6, h=6),
    stat("Workflow runs", "How many workflow runs (sessions) ran, to divide the counters by?", q('name = "workflow.envelope"', 'count_over_time()'), w=6, h=6),
    ts("Answered human gates over time", "When were human gates answered, and how?", q('name = "hitl.invocation.responded"', 'count_over_time() by (span.hitl.response.class)'), h=6),
    text("Primitive 2 · expected_sandbox_violations_per_session",
         "Counts `sandbox.violation` spans. Divide by the number of workflow runs to get the per-session figure. "
         "The declared roll-up dimensions `sandbox_tier` and `blast_radius_tier` are not on the violation span; the panel splits by fail class instead.", w=24, h=3,
         desc="What do the primitive 2 panels show?"),
    stat("Sandbox violations", "How many sandbox violations occurred (the counter behind primitive 2)?", q('name = "sandbox.violation"', 'count_over_time()'), bad=True, w=6, h=6),
    bars("Sandbox violations by fail class", "Which sandbox fail classes occurred?", q('name = "sandbox.violation"', 'count_over_time() by (span.sandbox.fail.class)'), w=6, h=6),
    ts("Sandbox violations over time", "When did sandbox violations occur, and of which MCP fail class?", q('name = "sandbox.violation"', 'count_over_time() by (span.mcp.fail.class)'), h=6),
    text("Primitive 3 · sandbox_tier_routing_accuracy",
         "**Not derivable from spans.** This primitive is a holdout judgement (`HOLDOUT_META_JUDGE_RATIO`): a reviewer or judge decides whether each tool call ran at the right sandbox tier. "
         "No span carries that verdict. Use `arhugula eval status` to run the holdout assertions and see the result.", w=12, h=4,
         desc="Why is there no panel for primitive 3?"),
    text("Primitive 5 · routing_accuracy_holdout",
         "**Not derivable from spans.** This primitive is a holdout judgement (`HOLDOUT_META_JUDGE_RATIO`): a reviewer or judge decides whether each call was routed to the right model. "
         "No span carries that verdict. Use `arhugula eval status` to run the holdout assertions and see the result.", w=12, h=4,
         desc="Why is there no panel for primitive 5?"),
    text("Primitive 4 · cache_hit_rate_alignment_floor",
         "Formula: `anthropic.cache_read_input_tokens / (anthropic.cache_read_input_tokens + anthropic.cache_creation_input_tokens)`. "
         "TraceQL cannot divide two sums, so the two inputs are shown side by side; divide the first by the sum of both. "
         "Only calls to the `anthropic` provider write these attributes. `arhugula eval drift show` reports the computed rate against your threshold.", w=24, h=3,
         desc="What do the primitive 4 panels show?"),
    stat("Cache read input tokens", "How many input tokens were read from the Anthropic prompt cache?", q(CHAT + ' && span.anthropic.cache_read_input_tokens != nil', 'sum_over_time(span.anthropic.cache_read_input_tokens)'), w=6, h=6),
    stat("Cache creation input tokens", "How many input tokens were written to the Anthropic prompt cache?", q(CHAT + ' && span.anthropic.cache_creation_input_tokens != nil', 'sum_over_time(span.anthropic.cache_creation_input_tokens)'), w=6, h=6),
    ts("Cache read input tokens by model", "How did cache reads develop over time, per model?", q(CHAT + ' && span.anthropic.cache_read_input_tokens != nil', 'sum_over_time(span.anthropic.cache_read_input_tokens) by (span.gen_ai.request.model)'), w=6, h=6),
    ts("Cache creation input tokens by model", "How did cache writes develop over time, per model?", q(CHAT + ' && span.anthropic.cache_creation_input_tokens != nil', 'sum_over_time(span.anthropic.cache_creation_input_tokens) by (span.gen_ai.request.model)'), w=6, h=6),
    text("Evaluation score spans and drift events",
         "An evaluation job can write one `eval <primitive>` span per score and one `gen_ai.eval.alignment_floor.drift_detected` span event when a value falls below the operator's threshold. "
         "No normal workflow run writes either, so these panels stay empty unless such a job runs. "
         "`arhugula eval drift show` is the supported way to see drift results; `arhugula eval status` covers the holdout loop.", w=24, h=3,
         desc="Why can the score and drift panels be empty?"),
    ts("Evaluation scores by primitive", "What average score did each evaluation primitive record?", q('name =~ "eval .*" && span.eval.value >= 0.0', 'avg_over_time(span.eval.value) by (span.eval.primitive)'), style="line", h=7),
    stat("Drift events", "How many alignment-floor drift events were recorded?", q(DRIFT, 'count_over_time()'), bad=True, w=4, h=7),
    ts("Drift events by primitive", "Which primitive fell below its alignment floor, and when?", q(DRIFT, 'count_over_time() by (event.gen_ai.eval.primitive)'), w=8, h=7),
    table("Recent drift events", "Which drift events were recorded most recently, with what value against what threshold?",
          q(DRIFT, 'select(event.gen_ai.eval.primitive, event.gen_ai.eval.alignment_floor.current, event.gen_ai.eval.alignment_floor.threshold, event.gen_ai.eval.alignment_floor.observation_window)'), h=7),
]))

VARIABLE = {
    "name": "namespace", "label": "Project", "type": "query", "datasource": DS,
    "description": "The project (resource attribute service.namespace) whose traces the panels read.",
    "query": {"refId": "TempoDatasourceVariableQueryEditor-VariableQuery", "type": 1, "label": "service.namespace"},
    "definition": "", "refresh": 2, "sort": 1, "multi": False, "includeAll": True, "allValue": ".*",
    "current": {"selected": True, "text": "All", "value": "$__all"}, "options": [], "regex": "", "hide": 0,
}

def layout(panels):
    out = []; x = y = rowh = 0
    for i, p in enumerate(panels, start=1):
        p = dict(p); w = p.pop("_w"); h = p.pop("_h")
        if x + w > 24: x = 0; y += rowh; rowh = 0
        p["id"] = i; p["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        x += w; rowh = max(rowh, h)
        if x >= 24: x = 0; y += rowh; rowh = 0
        for k in [k for k in p if k.startswith("_")]: p.pop(k)
        if p["type"] == "text": p.pop("datasource")
        out.append(p)
    return out

def dashboard(d):
    return {
        "uid": d["uid"], "title": d["title"], "tags": ["arhugula"], "schemaVersion": 41, "version": 1,
        "editable": False, "graphTooltip": 1, "timezone": "browser", "refresh": "1m",
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": [VARIABLE]},
        "annotations": {"list": []},
        "links": [{"type": "dashboards", "tags": ["arhugula"], "title": "Arhugula dashboards", "asDropdown": True, "includeVars": True, "keepTime": True, "icon": "external link", "targetBlank": False}],
        "panels": layout(d["panels"]),
    }

# ---------------------------------------------------------------- alert rules
KIT_DEFAULT = "Kit default: the reference states no threshold for this signal. Tune the threshold and the window to your deployment."
ALERTS = [
    dict(uid="arhugula-workflow-failed", title="Arhugula · Workflow run failed", severity="warning", window=600, op="gt", threshold=0,
         query='{ name = "workflow.envelope" && span.workflow.outcome = "failed" } | count_over_time() by (resource.service.namespace, span.workflow.id)',
         summary="A workflow run ended with outcome failed.",
         description="At least one workflow.envelope span with workflow.outcome = failed in the last 10 minutes. Open the Routing and resilience dashboard, table \"Recent failed workflow runs\", for the fail class.",
         condition="count of failed workflow runs in the last 10 minutes, per project and workflow",
         source="Kit default (any failure). The reference states no threshold for failed runs.",
         note=KIT_DEFAULT),
    dict(uid="arhugula-fallback-exhausted", title="Arhugula · Fallback chain exhausted", severity="critical", window=600, op="gt", threshold=0,
         query='{ event:name = "fallback.exhausted" } | count_over_time() by (resource.service.namespace)',
         summary="An LLM dispatch ran out of fallback candidates.",
         description="At least one fallback.exhausted span event in the last 10 minutes: every candidate in the chain failed or was skipped. Open the Routing and resilience dashboard for the last failure class.",
         condition="count of spans carrying a fallback.exhausted event in the last 10 minutes, per project",
         source="Kit default (any event). The reference states no threshold; the event itself marks a dispatch with no candidate left (reference 5.3).",
         note=KIT_DEFAULT),
    dict(uid="arhugula-breaker-opened", title="Arhugula · Circuit breaker opened", severity="warning", window=600, op="gt", threshold=0,
         query='{ event:name = "breaker.tripped" && event.harness.breaker.to_state = "open" } | count_over_time() by (resource.service.namespace)',
         summary="A provider or model circuit breaker opened.",
         description="At least one breaker.tripped span event with to_state = open in the last 10 minutes. The event is also written for recovery transitions; this rule counts openings only.",
         condition="count of spans carrying a breaker.tripped event whose new state is open in the last 10 minutes, per project",
         source="Kit default (any opening). The reference states no threshold; it states that breaker.tripped is written for every state transition, so the rule filters on to_state = open (reference 5.3).",
         note=KIT_DEFAULT),
    dict(uid="arhugula-hitl-timeout", title="Arhugula · Human gate timed out", severity="warning", window=600, op="gt", threshold=0,
         query='{ name = "hitl.invocation.timed_out" } | count_over_time() by (resource.service.namespace)',
         summary="A human-in-the-loop gate timed out without an answer.",
         description="At least one hitl.invocation.timed_out span in the last 10 minutes. Open the Human-in-the-loop gates dashboard for the degradation mode that was applied.",
         condition="count of hitl.invocation.timed_out spans in the last 10 minutes, per project",
         source="Kit default (any timeout). The reference states no threshold for gate timeouts.",
         note=KIT_DEFAULT),
    dict(uid="arhugula-validator-permanent-fail", title="Arhugula · Validator failed permanently", severity="warning", window=600, op="gt", threshold=0,
         query='{ name = "validator.evaluate" && span.validator.outcome = "permanent_fail" } | count_over_time() by (resource.service.namespace)',
         summary="A validator check ended in a permanent failure.",
         description="At least one validator.evaluate span with validator.outcome = permanent_fail in the last 10 minutes. Open the Validators dashboard for the step and fail class.",
         condition="count of validator.evaluate spans with outcome permanent_fail in the last 10 minutes, per project",
         source="Kit default (any permanent failure). The reference states no threshold; permanence is read from validator.outcome because validator.fail.permanence is never written (reference 5.5).",
         note=KIT_DEFAULT),
    dict(uid="arhugula-cost-threshold", title="Arhugula · Attributed cost above threshold", severity="warning", window=3600, op="gt", threshold=1,
         query='{ span.cost.attributed_number > 0.0 } | sum_over_time(span.cost.attributed_number) by (resource.service.namespace)',
         summary="Attributed cost in the last hour is above 1 US dollar.",
         description="The sum of cost.attributed_number over the last hour is above 1 US dollar for one project. Subscription CLI routes are never priced and do not count. Open the Cost dashboard for the provider and model.",
         condition="sum of attributed cost (US dollars) in the last hour, per project",
         source="Kit default (1 US dollar per hour per project). Reference section 8 states rates but no budget threshold.",
         note=KIT_DEFAULT),
    dict(uid="arhugula-alignment-floor-drift", title="Arhugula · Alignment-floor drift detected", severity="warning", window=600, op="gt", threshold=0,
         query='{ event:name = "gen_ai.eval.alignment_floor.drift_detected" } | count_over_time() by (resource.service.namespace)',
         summary="An evaluation primitive fell below its alignment floor.",
         description="At least one gen_ai.eval.alignment_floor.drift_detected span event in the last 10 minutes. The harness writes the event only when the current value is below the threshold the operator configured. Run `arhugula eval drift show` for the values.",
         condition="count of spans carrying a gen_ai.eval.alignment_floor.drift_detected event in the last 10 minutes, per project",
         source="Reference 7.2: the harness emits the event only when current value < the operator's threshold_value, so any event is a breach. The floor itself has no default in code; the operator sets it.",
         note="The drift threshold itself is the operator's alignment-floor setting, not a value in this rule; this rule fires on any drift event."),
]

def y(s):
    return json.dumps(s, ensure_ascii=False)

def alert_yaml():
    L = ["# Alert rules for the Arhugula Harness (kit extension).",
         "#",
         "# Grafana unified alerting, provisioned from this file. Every rule runs one TraceQL metrics",
         "# query against the Tempo data source as an instant query, reduces it to one number per",
         "# series and compares it with a threshold. A rule with no matching span returns no series;",
         "# that state is treated as healthy (noDataState: OK).",
         "#",
         "# No contact point is declared here: alerts go to Grafana's default contact point, which",
         "# sends nothing outside this machine until the operator configures it.",
         "apiVersion: 1",
         "",
         "groups:",
         "  - orgId: 1",
         "    name: arhugula-harness",
         "    folder: Arhugula Harness",
         "    interval: 1m",
         "    rules:"]
    for a in ALERTS:
        L += [
            f"      - uid: {a['uid']}",
            f"        title: {y(a['title'])}",
            "        condition: C",
            "        data:",
            "          - refId: A",
            "            queryType: traceql",
            "            datasourceUid: tempo",
            "            relativeTimeRange:",
            f"              from: {a['window']}",
            "              to: 0",
            "            model:",
            "              refId: A",
            "              datasource:",
            "                type: tempo",
            "                uid: tempo",
            "              queryType: traceql",
            "              metricsQueryType: instant",
            f"              query: {y(a['query'])}",
            "              tableType: traces",
            "              limit: 20",
            "              intervalMs: 60000",
            "              maxDataPoints: 43200",
            "          - refId: B",
            "            datasourceUid: __expr__",
            "            relativeTimeRange:",
            "              from: 0",
            "              to: 0",
            "            model:",
            "              refId: B",
            "              type: reduce",
            "              datasource:",
            "                type: __expr__",
            "                uid: __expr__",
            "              expression: A",
            "              reducer: last",
            "              settings:",
            "                mode: dropNN",
            "          - refId: C",
            "            datasourceUid: __expr__",
            "            relativeTimeRange:",
            "              from: 0",
            "              to: 0",
            "            model:",
            "              refId: C",
            "              type: threshold",
            "              datasource:",
            "                type: __expr__",
            "                uid: __expr__",
            "              expression: B",
            "              conditions:",
            "                - evaluator:",
            f"                    type: {a['op']}",
            "                    params:",
            f"                      - {a['threshold']}",
            "        noDataState: OK",
            "        execErrState: Error",
            "        for: 0s",
            "        isPaused: false",
            "        labels:",
            f"          severity: {a['severity']}",
            "          source: arhugula-kit",
            "        annotations:",
            f"          summary: {y(a['summary'])}",
            f"          description: {y(a['description'])}",
            f"          threshold_source: {y(a['source'])}",
            f"          tuning: {y(a['note'])}",
        ]
    return "\n".join(L) + "\n"

def cell(s):
    return s.replace("|", "\\|").replace("\n", " ")

def index_md():
    L = ["# Arhugula dashboards and alert rules: panel index", "",
         "Generated from the same definition as the files in `kit/observability/dashboards/` and `kit/observability/alerting/`.",
         "",
         "- Data source for every panel and rule: Tempo (`uid: tempo`).",
         "- `$namespace` is the dashboard variable \"Project\" (values of the resource attribute `service.namespace`; \"All\" is the regular expression `.*`).",
         "- Panel kinds: *stat* and *bar gauge* run the query as a TraceQL metrics instant query; *time series* runs it as a range query; *table* runs it as a TraceQL search and lists the matching spans; *text* has no query.",
         "- Default time range of every dashboard: last 6 hours. The stack keeps traces for 24 hours, so no panel can look further back than that.", ""]
    for d in DASHBOARDS:
        L += [f"## {d['title']}", "", f"File `{d['file']}`, uid `{d['uid']}`.", "",
              "| # | Panel title | Kind | Question it answers | TraceQL |", "|---|---|---|---|---|"]
        kinds = {"stat": "stat", "bargauge": "bar gauge", "timeseries": "time series", "table": "table", "text": "text"}
        for i, p in enumerate(d["panels"], start=1):
            query = f"`{cell(p['_query'])}`" if p["_query"] else "(no query)"
            L.append(f"| {i} | {cell(p['title'])} | {kinds[p['type']]} | {cell(p['description'])} | {query} |")
        L.append("")
    L += ["## Alert rules", "", "File `arhugula-rules.yaml`, rule group `arhugula-harness`, folder \"Arhugula Harness\", evaluated every minute. "
          "Each rule fires as soon as its condition holds (`for: 0s`), treats \"no series\" as healthy, and goes to Grafana's default contact point.", "",
          "| Rule (uid) | Condition | TraceQL (instant query) | Window | Threshold | Where the threshold came from |", "|---|---|---|---|---|---|"]
    for a in ALERTS:
        win = f"last {a['window'] // 60} minutes"
        L.append(f"| {cell(a['title'])} (`{a['uid']}`) | {cell(a['condition'])} | `{cell(a['query'])}` | {win} | > {a['threshold']} | {cell(a['source'])} |")
    L.append("")
    return "\n".join(L)

def rendered():
    """Every generated file, mapped to the text it should hold."""
    files = {
        os.path.join(OUT_DASH, d["file"]): json.dumps(dashboard(d), indent=2, ensure_ascii=False) + "\n"
        for d in DASHBOARDS
    }
    files[os.path.join(OUT_ALERT, "arhugula-rules.yaml")] = alert_yaml()
    files[OUT_INDEX] = index_md()
    return files


def main(argv):
    mode = argv[0] if argv else ""
    if mode not in ("write", "check"):
        print(__doc__)
        return 2
    stale = []
    for path, text in rendered().items():
        current = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
        if current != text:
            stale.append(path)
            if mode == "write":
                with open(path, "w", encoding="utf-8") as out:
                    out.write(text)
    if mode == "check" and stale:
        print("stale (run `python3 tools/dashboards.py write`):", *stale, sep="\n  ", file=sys.stderr)
        return 1
    print(f"{len(DASHBOARDS)} dashboards, {len(ALERTS)} alert rules and the panel index:",
          f"{len(stale)} file(s) rewritten" if mode == "write" else "current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
