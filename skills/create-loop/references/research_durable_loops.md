Task Result

Task ID: bg_88058241
Description: Research durable execution + agentic loops
Duration: 3m 43s
Session ID: ses_0e1b131dcffeL6qmBwsrGKUNy8

---

The user wants me to research and gather authoritative reference material on durable execution runtimes, agentic loops, and checkpoint/recovery mechanisms. This is a TYPE D (Comprehensive) research request that requires:

1. Documentation discovery (Phase 0.5) for the libraries/frameworks involved
2. Parallel execution of multiple search and fetch tools
3. Citable sources with URLs

Let me classify this and plan my approach:

**Classification: TYPE D (Comprehensive)**
- The request spans 3 distinct areas
- Each area requires deep dives into specific mechanisms
- Needs multiple authoritative sources
- The user explicitly wants "exhaustive on mechanisms, terse on prose"

**Approach:**
1. Start with parallel searches across the 3 areas
2. For each library/framework, get official docs
3. Look for engineering blogs and source code where relevant
4. Synthesize into a structured markdown report

Let me plan parallel calls:

**Area 1: Durable Execution Runtimes**
- Temporal: official docs, core mechanism
- DBOS: docs, durability model
- Restate: docs, deterministic execution
- AWS Step Functions: docs, state machines
- Azure Durable Functions: docs, orchestration

**Area 2: Agentic Loops**
- Anthropic engineering blog
- Cognition AI (Devin)
- Agent loop patterns

**Area 3: Checkpoint & Recovery**
- LangGraph checkpointing
- Thread state, checkpointers
- Recovery patterns

Let me start with broad parallel searches, then drill down with targeted doc fetches and grep_app searches for specific mechanisms.

I'll do this in waves:
- Wave 1: Broad web searches + context7 lookups for each area
- Wave 2: Targeted doc fetches based on what we find
- Wave 3: Source code/grep for specific implementation details

Let me kick off Wave 1 with many parallel calls.

I'll research these three areas systematically. Let me start with parallel broad searches to discover the authoritative sources, then drill down.

Excellent! I've got a wealth of detailed material. Let me now run the next wave of focused searches to fill in remaining gaps - particularly:
1. Temporal workflow versioning, signals, queries
2. AWS Step Functions state machine patterns
3. Anthropic's specific guidance on context management, compaction
4. LangGraph durable execution / DurableGraph
5. Idempotency keys, distributed locks

Let me also get a few more authoritative source URLs to verify and complete the picture.

I have a strong foundation. Now let me drill into the remaining gaps: Temporal versioning/queries, Step Functions state machine patterns, Anthropic's context compaction, and LangGraph's durable execution.

I have a very comprehensive set of sources. Let me also quickly check a few additional important things:
1. Restate durable agents specifically
2. Temporal Continue-As-New (for long-running loops)
3. Anthropic's handoff / structured note-taking

Then I'll synthesize. Let me also check for a few specific high-signal source pages to ensure my citations are accurate.

Let me get a few final authoritative sources to complete the picture.

I have a comprehensive set of authoritative sources. Now I have enough to synthesize the report. Let me update the todo list and produce the final structured markdown report.

Key sources I've collected:

**Durable Execution Runtimes:**
- Temporal architecture: github.com/temporalio/temporal/blob/main/docs/architecture/README.md
- Temporal Event History: docs.temporal.io/workflow-execution/event
- Temporal Worker Versioning: docs.temporal.io/production-deployment/worker-deployments/worker-versioning
- Temporal Continue-As-New: docs.temporal.io/workflow-execution/continue-as-new
- Temporal Saga: temporal.io/blog/compensating-actions-part-of-a-complete-breakfast-with-sagas
- Temporal Saga API: github.com/temporalio/sdk-java/.../Saga.java
- DBOS Architecture: docs.dbos.dev/architecture
- DBOS transactional: dbos.dev/blog/durable-code-execution-vs-transactional-execution
- DBOS Outbox: docs.dbos.dev/python/examples/outbox
- Restate what-is-durable-execution: restate.dev/what-is-durable-execution
- Restate Key Concepts: docs.restate.dev/foundations/key-concepts
- Restate Durable Steps: docs.restate.dev/develop/ts/durable-steps
- Restate Request Lifecycle: docs.restate.dev/guides/request-lifecycle
- AWS ASL Spec: states-language.net
- AWS Step Functions Workflow Type: docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html
- AWS Saga Pattern: docs.aws.amazon.com/prescriptive-guidance/latest/patterns/implement-the-serverless-saga-pattern-by-using-aws-step-functions.html
- Azure Durable Functions: learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations
- Azure Storage Provider: learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-azure-storage-provider
- Azure durabletask: github.com/Azure/durabletask

**Agentic Loops:**
- Anthropic Building Effective Agents: anthropic.com/research/building-effective-agents
- Anthropic Effective Harnesses: anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic Harness design: anthropic.com/engineering/harness-design-long-running-apps
- Anthropic Managed Agents: anthropic.com/engineering/managed-agents
- Anthropic Multi-Agent Research: anthropic.com/engineering/multi-agent-research-system
- Anthropic Context Engineering: anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Context Management: anthropic.com/news/context-management
- Cognition Devin CLI: cognition.ai/blog/devin-for-terminal
- Cognition Sonnet 4.5: cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges
- Cognition Manage Devins: cognition.ai/blog/devin-can-now-manage-devins
- Cognition Fusion: cognition.com/blog/devin-fusion
- ReAct paper: arxiv.org/pdf/2210.03629 / react-lm.github.io

**Checkpoint & Recovery:**
- LangGraph Persistence: docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Checkpointers: docs.langchain.com/oss/javascript/langgraph/checkpointers
- LangGraph Interrupts: docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph PostgresSaver: langchain-ai-langgraph-40.mintlify.app/api/checkpointing/postgres
- LangGraph Human-in-the-Loop: docs.langchain.com/oss/python/langchain/human-in-the-loop
- LangGraph Command/Send: docs.langchain.com/oss/python/langgraph/use-graph-api
- LangGraph Handoffs: docs.langchain.com/oss/python/langchain/multi-agent/handoffs
- LangGraph Subgraphs: docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangChain Context Engineering: langchain.com/blog/context-engineering-for-agents
- Saga original: cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf
- Stripe Idempotency: docs.stripe.com/api/idempotent_requests, stripe.com/blog/idempotency

Now let me synthesize this into a structured, terse markdown report focused on the 3 areas requested. The user wants:
- Name
- One-paragraph core idea
- Source URL
- One-line note on filesystem-only mapping

Let me update todos and write the report.

I have enough authoritative material. Let me update todos and synthesize the final report.

# Reference Research: Durable Execution, Agentic Loops & Checkpoint/Recovery

> Compiled for the `create-loop` skill. Three areas, every mechanism cited. "FS map" column = how a mechanism ports to a filesystem-only, no-runtime environment (since `create-loop` runs over an LLM agent, not a Temporal cluster or Postgres).

---

## 1. Durable Execution Runtimes

### 1.1 Temporal — Event-Sourced Workflows with Deterministic Replay

| | |
|---|---|
| **Core idea** | A workflow is a pure function whose progress is recorded as an append-only **Event History** on the server. On crash, a worker re-runs the workflow code; the SDK matches each *Command* the code emits against the recorded *Events*. Commands for already-completed steps are skipped, their prior result is returned; the workflow "catches up" to the failure point and resumes. Workflow code must be **deterministic**; all non-determinism (I/O, time, randomness) lives in **Activities**, which the server schedules, retries, and heartbeats independently. |
| **Source** | https://docs.temporal.io/workflow-execution/event (Event History), https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md (architecture), https://docs.temporal.io/encyclopedia/event-history/event-history-typescript (replay walkthrough) |
| **FS map** | Append-only `events.jsonl` log per run + a `state.json` derived from the log. The agent "replays" by re-reading the log and skipping steps whose outcomes are recorded. Activities become shell-out to tools; deterministic guarantee becomes "don't call anything whose output isn't in the log." |

**Key sub-mechanisms:**

- **Event History** — Linear, append-only log of `HistoryEvent`s. Server-side source of truth. Warning at 10,240 events, **terminated at 51,200 events or 50 MB**.
  Source: https://docs.temporal.io/workflow-execution/event
  *FS map:* `events/<run-id>.jsonl`, one event per line. Size cap enforced by a "Continue" threshold (see below).

- **Command vs Event duality** — Worker emits `Command`s (e.g. `ScheduleActivityTask`); server converts them into `Event`s. Replay = re-run code, compare new Commands vs existing Events.
  Source: https://docs.temporal.io/encyclopedia/event-history
  *FS map:* Agent's "plan" output = Commands. Recorder translates to log entries.

- **Workflow vs Activity split** — Workflow = deterministic orchestration (must be replayable). Activity = non-deterministic side effect, runs on the worker but is recorded as a task in history.
  Source: https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md
  *FS map:* "Deterministic" = the LLM *plan* generation step (the next action choice). "Activity" = tool execution (file write, shell, API call).

- **Determinism constraints** — All Workflow API calls produce Commands: timers, activity scheduling, child workflows, signals, versioning markers, side effects. Adding/removing/reordering these = non-determinism on replay.
  Source: https://docs.temporal.io/workflow-definition
  *FS map:* Plan steps must be tagged with stable IDs so re-planning after crash produces the same sequence.

- **Continue-As-New** — Atomically close the current run, start a new run with the **same Workflow ID** and a fresh Event History. State (as input) is passed across. Lets a workflow run forever; called "stackless recursion."
  Source: https://docs.temporal.io/workflow-execution/continue-as-new
  *FS map:* When `events.jsonl` exceeds threshold, archive the log and start a new "phase" file with the current state as the input. The new phase is "the same loop" by run-id.

- **Worker Versioning** — Tag workers with a `buildId`; declare Workflows as `Pinned` (stays on its build) or `Auto-Upgrade` (rolls forward to the latest). Equivalent to blue/green deploy of long-running workflows.
  Source: https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning
  *FS map:* Pin a loop to a particular `AGENTS.md` / prompt version via a manifest; `Auto-Upgrade` reads "latest at next Continue-As-New."

- **Versioning with Patching** — `patched("change-id")` inserts a feature-flag-like marker into the Event History. Old replays still see the old code path; new replays see the new one. Eventually replaced by `deprecatePatch`.
  Source: https://docs.temporal.io/develop/typescript/workflows/versioning
  *FS map:* Conditional branches in the plan keyed by a "schema version" recorded in the log.

- **Saga / Compensation** — `Saga.addCompensation(fn, ...args)` registers a rollback. On error, all registered compensations run. Java SDK has it built in; TS/Python/Go use the try/catch + `compensations.unshift()` pattern.
  Source: https://temporal.io/blog/compensating-actions-part-of-a-complete-breakfast-with-sagas, https://github.com/temporalio/sdk-java/blob/master/temporal-sdk/src/main/java/io/temporal/workflow/Saga.java
  *FS map:* Each plan step is paired with an "undo" instruction (delete file, revert spec, drop commit). On failure, the orchestrator walks the undo list in reverse.

- **Reset** — `WorkflowExecution.reset` truncates history at a chosen point (`WorkflowTaskStarted`/`Completed`/etc.) and starts a new run with that prefix, preserving Workflow ID. Used to fix non-determinism post-deploy.
  Source: https://docs.temporal.io/workflow-execution/event (Reset subsection)
  *FS map:* "Truncate `events.jsonl` at the last good checkpoint and resume from there." Manual but identical effect.

- **Side Effect / Mutable Side Effect** — `Workflow.sideEffect(fn)` runs a non-deterministic function once, records the result in history, returns the recorded result on replay.
  Source: https://docs.temporal.io/workflow-execution/event (Side Effect subsection)
  *FS map:* "Compute the value once, write it to the log, return it from the log on re-plan." Used for UUIDs, current time, anything the planner would otherwise re-roll.

---

### 1.2 DBOS — Postgres as the Workflow Engine

| | |
|---|---|
| **Core idea** | A lightweight Python/TS **library** (no separate server) that turns Postgres into a durable workflow engine. Every `@Workflow()` call and every step is **checkpointed as a row in a Postgres table**. On crash, the app restarts, queries Postgres for `PENDING` workflows, replays each from the start, but before each step checks the checkpoint table — if the step's result is already there, it returns the stored value without re-running. Steps are assumed idempotent; transactional steps (`@Transaction`) execute the step body *inside* the same DB transaction that writes the checkpoint, giving exactly-once. |
| **Source** | https://docs.dbos.dev/architecture, https://docs.dbos.dev/concepts/durability, https://www.dbos.dev/blog/durable-code-execution-vs-transactional-execution |
| **FS map** | Direct port: every step's result becomes a row in a `checkpoints/<run-id>/<step>.json` file. Replay = read file, return contents. No server needed. |

**Key sub-mechanisms:**

- **Step checkpointing** — One DB write per step (input → execute → write result). Plus two workflow-level writes (start + end). Total: ~3 writes per step. Idempotency = "safe to retry from the last checkpoint."
  Source: https://docs.dbos.dev/architecture
  *FS map:* `fsync` after every step result. Append-only per-step file.

- **Workflow-level transactions** — `transactional=True` wraps all `@Transaction` steps in a single top-level Postgres transaction with savepoints. All-or-nothing across steps; rolls back if workflow fails.
  Source: https://github.com/DBOS-project/dbos-transact-py
  *FS map:* A "phase" directory: each step is a file under `phases/<id>/`; the phase is committed by an atomic rename of the directory. Failure leaves old names in place.

- **Three execution primitives** — `@Workflow` (orchestrator, deterministic control flow), `@Transaction` (DB-backed step, exactly-once via same-tx checkpoint), `@Communicator` (external call, at-least-once, must be idempotent).
  Source: https://www.dbos.dev/blog/durable-code-execution-vs-transactional-execution
  *FS map:* Three step types with three different commit semantics: (1) LLM-plan, (2) write-to-disk-state, (3) shell-out-to-world.

- **Workflow ID = idempotency key** — Setting `SetWorkflowID("order-123-payment")` and calling the workflow returns the cached result. Single-flight, "once-and-only-once" start guarantee.
  Source: https://docs.dbos.dev/architecture (Workflow isolation section)
  *FS map:* The run directory is the idempotency key. Re-running a loop with the same `task_id` resumes, doesn't re-start.

- **Transactional Outbox replacement** — A workflow that writes to a DB *and* sends a message is atomic by construction: the DB write is in a `@Transaction`, the message send is the next step; if crash between them, recovery re-sends. No explicit outbox table needed.
  Source: https://docs.dbos.dev/python/examples/outbox
  *FS map:* "After the file write, the next step is to enqueue / post the notification." Resumption replays from the queued notification.

- **Conductor (closed source)** — Detects dead application servers via a websocket; reassigns their workflows. The community DBOS works on a single Postgres database; Conductor adds multi-node leadership.
  Source: https://docs.dbos.dev/architecture
  *FS map:* Optional. The filesystem model only has one "node" — the agent session — so recovery is a single-process problem.

---

### 1.3 Restate — Single Binary, Journal-of-Operations

| | |
|---|---|
| **Core idea** | Restate is a single Rust binary that acts as a **reverse-proxy + journal store** in front of your services. Every `ctx.run(...)`, `ctx.sleep(...)`, `ctx.call(...)`, `ctx.send(...)` is recorded as a journal entry *before* its result is returned. On crash, the SDK replays the journal: previously-completed entries return their stored result instantly, and the handler resumes at the last unfinished entry. Like Temporal but the journal lives in a single binary you embed next to your service rather than a separate cluster. |
| **Source** | https://www.restate.dev/what-is-durable-execution, https://docs.restate.dev/foundations/key-concepts, https://docs.restate.dev/guides/request-lifecycle |
| **FS map** | Each handler invocation is a directory; `journal.ndjson` records every `ctx.run` invocation and result. The "proxy" model becomes the agent's tool router — the recorder is invoked between every tool call. |

**Key sub-mechanisms:**

- **Journal-of-operations** — Operations recorded in arrival order: service calls, state updates, timers, sleeps, external effects. Replay = re-execute the handler; for each `ctx` op, check if the journal has a result, if so return it.
  Source: https://www.restate.dev/what-is-durable-execution
  *FS map:* Equivalent to a "replay log" the agent consults before each tool call.

- **Single binary, single-writer** — Restate server is a single Rust process (or HA cluster). Services are stateless. The server keeps K/V state and execution log; requests carry state to the handler. This is what makes FaaS durable.
  Source: https://docs.restate.dev/foundations/key-concepts (Stateless services)
  *FS map:* The "server" becomes the orchestrator process itself. State is passed in as the initial prompt context.

- **Immutable deployment versioning** — Each deploy gets a unique endpoint; Restate routes retries to the original endpoint. In-flight invocations stay pinned. Equivalent to Temporal's Worker Versioning but enforcement happens at the proxy.
  Source: https://docs.restate.dev/services/versioning
  *FS map:* Pin a loop iteration to a specific `AGENTS.md` snapshot; new iterations use the new snapshot.

- **Journal mismatch error (RT0016)** — Replay produced a different journal than the original (non-determinism or in-place code change). For FaaS / K8s, the fix is "pause + resume on a new deployment."
  Source: https://docs.restate.dev/services/versioning
  *FS map:* Equivalent to a planner emitting a step the log doesn't have. Recover by truncating at the last good entry and resuming.

- **Deterministic randoms / time** — `restate.random()` and `restate.now()` are seeded by the invocation ID → same on replay.
  Source: https://docs.restate.dev/develop/ts/durable-steps
  *FS map:* Derive all "random" / "time" values from a seed stored in the first journal entry.

- **Inactivity timeout** — If no new journal entry arrives for 1 min, invocation is suspended. Configurable for long LLM calls.
  Source: https://docs.restate.dev/develop/ts/durable-steps
  *FS map:* A "liveness ping" requirement: the recorder must write at least one entry per timeout window.

- **Durable Promise / Timer / Awaitable** — `ctx.sleep(d)`, `ctx.awakeable()`, `ctx.run()` survive process restarts. Sleeps can be **months**; no process held open.
  Source: https://docs.restate.dev/foundations/key-concepts
  *FS map:* A scheduled "wake" entry in the journal. The next agent session finds the entry and re-invokes the loop.

---

### 1.4 AWS Step Functions — Declarative State Machine (ASL)

| | |
|---|---|
| **Core idea** | A workflow is a **declarative JSON state machine** written in the Amazon States Language (ASL). The service is the runtime: it reads the ASL, executes the current state, persists the result, and transitions to the next. **Standard Workflows** have exactly-once semantics and 1-year max duration (priced per state transition); **Express Workflows** are at-least-once / at-most-once with 5-min cap (priced per duration+memory). State types: `Task`, `Choice`, `Parallel`, `Map`, `Pass`, `Wait`, `Succeed`, `Fail`. Tasks run on Lambda or 200+ AWS service integrations. |
| **Source** | https://states-language.net (spec), https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html, https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html |
| **FS map** | The state machine JSON is a literal `workflow.asl.json` file. Each state is a node in an agent plan; transition is a `goto` in the plan output. Standard= deterministic order, Express= any order with retries. |

**Key sub-mechanisms:**

- **State types** — `Task` (do work), `Choice` (data-driven branching), `Parallel` (fan-out, fixed branches), `Map` (fan-out over input array, up to 10k parallel children in Distributed mode), `Wait` (pause by `Seconds`/`Timestamp`), `Pass` (no-op / transform), `Succeed`/`Fail` (terminal).
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/statemachine-structure.html
  *FS map:* Each = a node kind in the plan DSL. `Map` = "for each item in array, run this sub-plan and aggregate."

- **Retries with exponential backoff + jitter** — `Retry: [{ErrorEquals, IntervalSeconds, MaxAttempts, BackoffRate, JitterStrategy}]`. Walked in order; first match wins.
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html
  *FS map:* The loop's retry policy: `backoff = base * 2^attempt ± jitter`, `max_attempts = N`.

- **Catch / Saga compensation** — `Catch: [{ErrorEquals, Next, ResultPath}]`. On unhandled error, transitions to a fallback state. Compensation pattern: each Task has a paired "undo" Task in the `Catch`.
  Source: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/implement-the-serverless-saga-pattern-by-using-aws-step-functions.html
  *FS map:* Each plan step is paired with an undo step; the `Catch` field says "if this step fails, run these undo steps in reverse order."

- **`ResultPath` / `OutputPath` / `Parameters` / `ResultSelector`** — Control how state input + state result + state output are merged into the JSON document passed to the next state. JSONata or JSONPath query language.
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/statemachine-structure.html
  *FS map:* The data-shape contract between steps. State = the prompt context. Each step's output is merged into the context for the next.

- **`WaitForTaskToken` (callback pattern)** — `.waitForTaskToken` integration pauses the execution until an external system calls `SendTaskSuccess` with the token. Standard Workflows only.
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html
  *FS map:* "Human approval" / "external webhook" — the loop writes a `pending:<token>` entry to disk and the next session finds it.

- **Standard vs Express (exactly-once vs at-least-once)** — Standard uses a full execution history (90-day retention) for replay-based recovery; Express is in-memory, faster, but tolerates re-execution. **Hard quota: 25,000 history entries per execution.**
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html
  *FS map:* Standard=full event log, Express=in-memory session. The 25k cap is the "Continue-As-New" trigger analog.

- **Nested workflows / `Map` Distributed mode** — A `Map` state in Distributed mode spawns each iteration as a child workflow with its own history. Defeats the 25k cap.
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html
  *FS map:* "Sub-task directory" — each iteration gets its own event log; parent's history stays small.

- **Express Synchronous** — `StartSyncExecution` blocks the caller, returns the result inline, 60s max. For "real-time" workflows.
  Source: https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html
  *FS map:* "Run a sub-plan inline within the current session" — same agent call.

---

### 1.5 Azure Durable Functions — Event-Sourced Orchestrator on Azure Storage

| | |
|---|---|
| **Core idea** | An **orchestrator function** (a normal async function) is checkpointed at every `await` into a History table on Azure Storage / MSSQL / Netherite. The framework records the event (`TaskScheduled`, `TaskCompleted`, `TimerCreated`, etc.) and can unload the orchestrator from memory. On resume, the entire orchestrator function **re-executes from the start**; for each `await`, the framework checks the history and returns the recorded result if found. Activities are non-deterministic; the orchestrator is deterministic. History limits force a `ContinueAsNew` to reset the log. |
| **Source** | https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations, https://github.com/Azure/durabletask/blob/main/docs/concepts/replay-and-durability.md, https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-azure-storage-provider |
| **FS map** | Identical pattern to Temporal: re-execute plan, skip steps with recorded results, resume. The "storage provider" is just a file. |

**Key sub-mechanisms:**

- **History table** — `History<hub>` Azure Table, partition key = orchestration instance ID. One row per event. Loaded by range query on resume.
  Source: https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-azure-storage-provider
  *FS map:* `<run-id>/history.jsonl`, append-only. Read on resume.

- **Replay** — Orchestrator function is re-executed from `OrchestratorStarted` to the latest `TaskCompleted`/`TimerFired`. Local variables are *rebuilt* during replay — they aren't stored.
  Source: https://github.com/Azure/durabletask/blob/main/docs/concepts/replay-and-durability.md
  *FS map:* Plan re-runs each session; non-deterministic state comes from history reads.

- **`IsReplaying` flag** — `IDurableOrchestrationContext.IsReplaying` is `true` during replay, `false` on first execution. Use to suppress non-idempotent side effects like logging.
  Source: https://github.com/Azure/azure-functions-durable-extension/blob/182cb5e9/src/WebJobs.Extensions.DurableTask/ContextInterfaces/IDurableOrchestrationContext.cs
  *FS map:* The agent's "is this a fresh attempt or recovery?" check. Used to gate non-idempotent tool calls.

- **`ContinueAsNew(input)`** — Restart with a fresh history, optional new input. Identical to Temporal's mechanism. Recommended for long-running orchestrations to bound history size.
  Source: https://github.com/Azure/durabletask/blob/main/docs/concepts/replay-and-durability.md
  *FS map:* Same as Temporal — archive the log, start a new phase with the current state as input.

- **At-least-once activity execution** — Activities can be retried after crash. The runtime guarantees *at-least-once*; idempotency is the developer's job.
  Source: https://learn.microsoft.com/en-us/azure/azure-functions/durable/programming-model-overview
  *FS map:* Tool calls must be designed "safe to retry" — uses idempotency keys (see §1.6).

- **Extended sessions / instance cache** — Keep mid-execution orchestrator in memory across work items to avoid full replay. Tunable. Default = aggressive replay (helpful for detecting non-determinism during dev).
  Source: https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-perf-and-scale
  *FS map:* Optional optimization — the agent doesn't unload between turns if the model is fast enough.

- **Durable timer / external event** — `context.CreateTimer(...)` (durable: survives process death) and `WaitForExternalEvent` (waits for client to raise an event). Backing store = control queue.
  Source: https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations
  *FS map:* A "pending timer" entry in the journal. The next session sees it and re-arms.

- **Durable Entities** — Stateful objects with operations. Each entity has its own history. `SignalEntity` is the message.
  Source: https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-entities
  *FS map:* Long-lived keyed state machine. Maps cleanly to "per-task spec file" with an event log per task.

---

### 1.6 Idempotency Keys (cross-cutting primitive)

| | |
|---|---|
| **Core idea** | A client-supplied unique string attached to a mutating request. The server caches `(key → response)` for ≥24h; retried requests with the same key return the cached response (success *or* error). On insert: `INSERT ... ON CONFLICT DO NOTHING` to atomically claim; concurrent retries see the claim and either wait or get `409`. Stripe popularized; now IETF draft. |
| **Source** | https://docs.stripe.com/api/idempotent_requests, https://stripe.com/blog/idempotency, https://sujeet.pro/articles/stripe-idempotency-reliability |
| **FS map** | A file `idempotency/<key>.json` containing the recorded response. Created by `open(..., O_CREAT|O_EXCL, 0644)` — POSIX guarantees atomic claim. |

**Key design choices:**

- **Errors are replayed** — first failure is cached, retried request gets the same 4xx. Forces clients to mint a fresh key to actually retry. Stripe v2: attempts re-execution before returning a new outcome.
- **Scope per (account, route, key)** — never global; prevents tenant collision.
- **Hash incoming params vs cached** — same hash → replay; different hash → `422` (client bug, surfaces loudly).
- **Side effects outside the idempotent section** — enqueue/email in a separate phase; a crash between "do it" and "mark done" must not double-fire.

---

### 1.7 Saga Pattern (foundational, from the 1987 paper)

| | |
|---|---|
| **Core idea** | A long-lived transaction is broken into a sequence of sub-transactions `T1, T2, …, Tn`, each with a corresponding **compensating transaction** `C1, C2, …, Cn`. If `Tj` fails, run `Cj-1, …, C1` in reverse. Compensations are *semantic* undo (not state restore) — they don't guarantee returning to the exact pre-Tj state. Either the full forward sequence or the partial-forward + reverse-compensation sequence runs. |
| **Source** | García-Molina & Salem, "Sagas" (1987), https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf, https://dl.acm.org/doi/10.1145/38713.38742 |
| **FS map** | Each step has an "undo" instruction. The orchestrator keeps a stack of completed steps; on failure, pops and runs the inverse. No DB-level rollback needed. |

---

## 2. Agentic Loops / Long-Running Agents

### 2.1 The ReAct Pattern — Reason, Act, Observe (loop primitive)

| | |
|---|---|
| **Core idea** | An agent's trajectory interleaves **Thought** (verbal reasoning) with **Action** (tool call) and **Observation** (tool result). Reasoning helps the model induce, track, and update action plans; actions let it ground reasoning in external data. This is the canonical "loop" — every agent framework inherits it. |
| **Source** | Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models," ICLR 2023 — https://react-lm.github.io, https://arxiv.org/pdf/2210.03629, https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/ |
| **FS map** | A loop over three file types: `thought.md` (reasoning), `action.json` (tool call), `observation.txt` (result). Each iteration writes the next one. |

---

### 2.2 "Building Effective Agents" (Anthropic, 2024)

| | |
|---|---|
| **Core idea** | The most successful agent implementations use **simple, composable patterns** (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, agents) rather than complex frameworks. Agents = "LLMs using tools based on environmental feedback in a loop." Three principles: (1) maintain simplicity, (2) prioritize transparency in planning, (3) carefully craft the agent-computer interface (tool documentation = the ACI). Stopping conditions (max iterations) are required. |
| **Source** | https://www.anthropic.com/research/building-effective-agents, https://www.anthropic.com/engineering/building-effective-agents |
| **FS map** | "Simple patterns over frameworks" → `create-loop` should be a *thin* shell, not a framework. Tools = first-class docs. `AGENTS.md` is the ACI. |

---

### 2.3 "Effective Harnesses for Long-Running Agents" (Anthropic, 2025)

| | |
|---|---|
| **Core idea** | Two-agent design: an **initializer agent** (first session only) writes `init.sh`, `claude-progress.txt`, an initial `git commit`, and a *full feature spec* (200+ features for a non-trivial app) into the environment. A **coding agent** (every subsequent session) picks up *one feature*, implements it, commits, and writes a progress note. **One feature at a time** is the key — it defeats the agent's "one-shot everything" failure mode. `git` is the version control of state; `claude-progress.txt` is the human-readable log. |
| **Source** | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| **FS map** | Direct port: `init.sh` + `task.md` (the spec) + `.loop/progress.md` (the log) + `.loop/state.json` (the machine-readable state). The loop *itself* is the harness. |

**Key mechanisms from this post:**

- **Initializer vs worker agent** — Initializer's prompt differs from worker's; it sets up the environment, doesn't do tasks. Worker's prompt is "pick the next feature, do it, commit, update progress."
- **Full feature spec up front** — Prevents the agent from declaring "done" prematurely. Spec lives in a file, not in context.
- **One feature per session** — Granularity prevents scope creep and makes progress measurable.
- **Git as state + git revert as recovery** — Each feature is a commit; the next session can `git log` to see what was done and `git revert` to undo bad changes.
- **Progress file as cross-session memory** — Plain text log, append-only, both human and agent readable.

---

### 2.4 "Harness Design for Long-Running Application Development" (Anthropic, 2025)

| | |
|---|---|
| **Core idea** | Generator-evaluator architecture (GAN-inspired) for multi-hour app generation. Generator implements features; evaluator (separate agent, adversarial) tests with Playwright MCP and grades with a rubric. **Sprint decomposition** (one feature per sprint) was critical on Opus 4.5; became optional on 4.6 as model capability grew. Self-evaluation is a trap; adversarial evaluators work better. Generators should "take minimal actions, delegate to a sidekick" (fusion model) for cost. |
| **Source** | https://www.anthropic.com/engineering/harness-design-long-running-apps |
| **FS map** | Two agents, separate prompts: `generator.md` and `evaluator.md`. Files mediate communication (generator writes spec/plan, evaluator reads, writes verdict). |

---

### 2.5 "Scaling Managed Agents: Decoupling the Brain from the Hands" (Anthropic, 2025)

| | |
|---|---|
| **Core idea** | Three interfaces: **session** (append-only log of events), **harness** (the loop that calls the model and routes tool calls), **sandbox** (the execution env). The session is **outside** the harness — if the harness crashes, a new one boots with `wake(sessionId)`, calls `getSession(id)` to recover the event log, and resumes from the last event. Sandboxes become **cattle**: if a container dies, the harness catches the failure as a tool-call error and re-initializes. No nursing failed containers. |
| **Source** | https://www.anthropic.com/engineering/managed-agents |
| **FS map** | The session log is `.loop/session-<id>.jsonl`. The harness is the loop driver. Sandbox = the worktree. Crash of the harness means the next `create-loop` invocation reads the session log and resumes. |

**Key primitive: `wake(sessionId)` / `getSession(id)` / `emitEvent(id, event)`** — minimal API for "resume an interrupted agent session from a durable log."

---

### 2.6 "Effective Context Engineering for AI Agents" (Anthropic, 2025)

| | |
|---|---|
| **Core idea** | Three techniques to extend agent coherence beyond a single context window: (1) **compaction** — summarize the window when it nears the limit, restart with the summary, lossy by design; (2) **structured note-taking / agentic memory** — agent writes persistent notes outside the window (e.g. `NOTES.md`), reads them back later, low overhead; (3) **multi-agent** — main agent coordinates, sub-agents do focused work and return 1–2k token structured summaries. |
| **Source** | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents, https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools |
| **FS map** | Compaction = a `compaction.md` file in `.loop/`. Note-taking = any `*.md` in the worktree the agent writes/reads. Multi-agent = sub-task directories with their own summaries. |

**Specific design notes:**
- Compaction is a *whole-transcript* operation — flattens user/assistant/tool messages, even prior compaction blocks, into one summary.
- Anthropic's `compact_20260112` API block has a token threshold (min 50k, default 150k) and `pause_after_compaction` to let you inject extra context.
- "Maximizing recall, then improving precision" is the tuning advice.
- Memory tool: persistent file directory, agent reads/writes/deletes via `view`/`create`/`str_replace`/`delete`/`rename` tools.

---

### 2.7 "How We Built Our Multi-Agent Research System" (Anthropic, 2025)

| | |
|---|---|
| **Core idea** | Orchestrator-worker pattern for research. LeadResearcher writes its plan to **Memory** before context exceeds 200k tokens. Spawns 3–5 parallel Subagents, each with a **fixed output schema** (summary, key findings, confidence score, items-to-verify). Each subagent uses 10k–50k tokens internally, returns 1k–2k. Lead synthesizes, decides to spawn more or finalize. CitationAgent last. Beat single-agent Opus 4 by 90.2% on internal eval. **3x parallel tool calls** by subagents. |
| **Source** | https://www.anthropic.com/engineering/multi-agent-research-system |
| **FS map** | Subagents = subdirectories with `task.md` (input) and `result.json` (schema-enforced output). Lead reads only the result, not the subagent's internal trace. Schema validation is mandatory. |

---

### 2.8 Devin / Cognition — Production Agent Patterns

| | |
|---|---|
| **Core idea** | Cognition's "Agent Patterns Catalog" entry on Devin documents the practical primitives. Session = long-running multi-hour task inside a VM with shell/IDE/browser as first-class tools. **Sleep/wake** mechanic: session pauses when idle, resumes when messaged. **ACUs** (Agent Compute Units) meter each step class (planning/context/execution/browser/code) — explicit step budget. **Knowledge store** = cross-session memory, auto-populated from READMEs and `AGENTS.md` / `CLAUDE.md` style files, retrieved per session by a trigger. |
| **Source** | https://www.agentpatternscatalog.org/compositions/devin/, https://cognition.ai/blog/devin-for-terminal, https://cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges |
| **FS map** | Session = `.loop/session-<id>/`. Sleep = exit with `state.json` describing how to resume. ACU = a per-loop-step cost model in `AGENTS.md`. Knowledge = `AGENTS.md` + auto-scanned READMEs. |

**Key sub-mechanisms from Cognition:**

- **Sonnet 4.5 is "context-aware"** — proactively summarizes itself as it nears the limit. This shapes token-budget planning.
- **Filesystem as memory** — model writes `CHANGELOG.md`, `SUMMARY.md` to disk without prompting. Externalizes state.
- **Sonnet 4.5 runs parallel bash commands and parallel file reads** — "actions per context window" is a real metric.
- **"Context anxiety"** — models become cautious near their perceived limit. The solution is **context reset** (fresh agent with structured handoff), not compaction (compaction doesn't cure coherence drift).
- **Devin manages Devins** — main session = coordinator, breaks task into pieces, each runs in own VM, each reports back. Pattern = "context accumulation degrades each subtask; clean slate per subtask is better."
- **Fusion / Sidekick** — two parallel agents (frontier + cost-effective), persistent cached contexts, model-switch during compaction = "free" model upgrade.
- **Handoff to cloud** — local session packages git context (`repo`, `branch`, `git diff HEAD` truncated 100kB) into the cloud session prompt. The `club-cog/devin-handoff` repo is the reference implementation.
  Source: https://github.com/club-cog/devin-handoff
  *FS map:* `git rev-parse` + `git diff HEAD` is the canonical "context bundle" for resuming a session on a fresh agent.

---

### 2.9 "Context Engineering for Agents" (LangChain, 2025)

| | |
|---|---|
| **Core idea** | Four strategies: **write** (save context outside the window — Notes, scratchpads), **select** (pull relevant context in — RAG, memory tools), **compress** (summarize/trim — auto-compact at 95% like Claude Code, summarization nodes at specific points), **isolate** (split context across agents — sub-agents with focused tasks). All four are first-class in LangGraph. |
| **Source** | https://www.langchain.com/blog/context-engineering-for-agents |
| **FS map** | Write=file I/O, Select=grep the worktree, Compress=`compact_20260112` analog, Isolate=spawn a sub-task dir. |

---

## 3. Checkpoint & Recovery

### 3.1 LangGraph — Thread State, Checkpointers, Interrupts, Human-in-the-Loop

| | |
|---|---|
| **Core idea** | LangGraph's persistence layer has two systems: **Checkpointers** (thread-scoped, short-term, per-step `StateSnapshot` + per-node `pending_writes`) and **Stores** (cross-thread, long-term K/V). Compile a graph with a checkpointer and every super-step is snapshotted to a thread identified by `thread_id`. Three durability modes: `sync` (before next step), `async` (background), `exit` (only at end). Replay = re-run from a `checkpoint_id`; nodes *before* the checkpoint are skipped, nodes *after* re-execute including LLM/API calls. |
| **Source** | https://docs.langchain.com/oss/python/langgraph/persistence, https://docs.langchain.com/oss/javascript/langgraph/checkpointers, https://reference.langchain.com/python/langgraph/checkpoints, https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py |
| **FS map** | `checkpoints/<thread_id>/<step>.json` + `pending/<thread_id>/<node>.json` files. SQLite checkpointer is one DB file. Postgres checkpointer is one schema. The "FS map" is literally how `SqliteSaver` is implemented. |

**Sub-mechanisms:**

- **Thread ID = primary key** — `config={"configurable": {"thread_id": "user-123"}}` is the only way to load/save state. No thread_id = no checkpointing.
  Source: https://docs.langchain.com/oss/javascript/langgraph/checkpointers
  *FS map:* The run directory name.

- **Per-superstep checkpoint + per-node pending writes** — At each super-step boundary, a full `StateSnapshot` is committed. During the super-step, each node's writes go to a `checkpoint_writes` table as tasks. If a node fails mid-superstep, the successful node's writes are already durable — no re-run on resume.
  Source: https://docs.langchain.com/oss/javascript/langgraph/checkpointers
  *FS map:* "Super-step" = one agent turn. Per-node writes = per-tool-call files. Atomic commit at the end of the turn.

- **`interrupt()` function** — Raises an exception that propagates to the runtime; runtime saves state, returns the payload to the caller via `__interrupt__` (or `stream.interrupts`), waits indefinitely. On resume, the node is *re-executed from the start*; any code before the `interrupt()` runs again (but the result is reused, not re-fetched).
  Source: https://docs.langchain.com/oss/python/langgraph/interrupts, https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt
  *FS map:* "Write a `pending:<token>` file, exit the session. The next session finds it, validates, then continues."

- **`Command` (state update + routing in one)** — `Command(update={...}, goto=..., resume=..., graph=Command.PARENT)`. The key for multi-agent handoff: subgraph → parent via `Command.PARENT`.
  Source: https://docs.langchain.com/oss/python/langgraph/graph-api, https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/types.py
  *FS map:* "Update state file, then `goto:` the next node name" — single atomic write that controls routing.

- **`Send` (map-reduce)** — `Send(node_name, state)` returned from a conditional edge to invoke a node with custom state. Lets you fan out dynamically.
  Source: https://docs.langchain.com/oss/python/langgraph/use-graph-api
  *FS map:* "For each item, write a sub-task file and a routing instruction."

- **Time travel / replay** — `graph.invoke(input, config={"configurable": {"thread_id": ..., "checkpoint_id": ...}})` re-runs from a historical checkpoint. Nodes *before* the checkpoint skip; nodes *after* re-execute.
  Source: https://docs.langchain.com/oss/javascript/langgraph/checkpointers
  *FS map:* "Restore from `<run>/step-N.json`, re-plan from there."

- **`HumanInTheLoopMiddleware` (LangChain v1)** — `interrupt_on={"write_file": True, "execute_sql": {"allowed_decisions": ["approve", "reject"]}}`. Pauses on tool call, waits for human decision, resumes with `Command(resume=...)`.
  Source: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
  *FS map:* Per-tool "needs approval?" flag in `AGENTS.md`. Pause = write a `pending-approval:<tool>:<args-hash>` file.

- **Multi-agent handoff** — Subagent returns a `ToolMessage` with a *handoff pair* (`AIMessage` + `ToolMessage` for the tool call) when handing off to the parent. Don't pass the full subagent message history — it's noise.
  Source: https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs
  *FS map:* Handoff artifact = a small JSON file (`{"summary", "findings", "confidence", "verify_before_using"}`) — Anthropic's exact 4-field schema.

- **Subgraph state** — Subgraphs either (a) share state keys with parent (use `add_node` with compiled subgraph), or (b) have different schemas (wrap in a node that maps parent state ↔ subgraph state). Stateful subgraphs inherit the parent's checkpointer.
  Source: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
  *FS map:* (a) sub-task dir uses same `state.json`; (b) wrapper script does the read/transform/write dance.

- **`update_state` / `bulk_update_state`** — Inject state externally, "as if" a node had produced it. Useful for human edits between agent runs.
  Source: https://langchain-ai-langgraph-40.mintlify.app/concepts/checkpointing
  *FS map:* Manually edit `state.json` between sessions; the next run reads it as if the prior node had produced it.

- **Checkpoint namespaces for subgraphs** — LangGraph assigns namespaces by call order. Wrap each subagent in its own `StateGraph` with a unique node name for a stable namespace.
  Source: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
  *FS map:* Sub-task dirs keyed by stable node name, not call order.

---

### 3.2 Manual State Updates Between Sessions (the agent pattern)

| | |
|---|---|
| **Core idea** | When an agent session ends, the user (or a cron, or an external event) can inspect and edit the state. The next session reads the edited state and continues. This is `update_state` made human. **The state file is the contract** between human and agent. |
| **Source** | https://langchain-ai-langgraph-40.mintlify.app/concepts/checkpointing |
| **FS map** | The loop's `.loop/state.json` is editable in any text editor. The next `create-loop` invocation reads it as the "current state" and continues. |

---

### 3.3 "Why every agent handoff corrupts your context" (Wire, 2026)

| | |
|---|---|
| **Core idea** | Compression in handoffs reliably drops five categories: (1) *what was done*, (2) *why* (the reasoning, not just the decision), (3) *what was tried and didn't work*, (4) *assumptions made*, (5) *confidence level*. The fix: **structured handoff schemas** with explicit fields for each. Anthropic's research system schema (summary / findings / confidence / verify-before-using) is the production reference. |
| **Source** | https://usewire.io/blog/why-every-agent-handoff-corrupts-your-context/ |
| **FS map** | Every handoff between sub-tasks writes a JSON file with those four required fields. Schema validation is non-optional. |

---

## Cross-Cutting Mechanism Summary (for spec encoding)

| Mechanism | Sources | Mapped primitive in `create-loop` |
|---|---|---|
| **Event-sourced append-only log** | Temporal, Durable Functions, Restate | `.loop/session-<id>/events.jsonl` |
| **Deterministic replay** | Temporal, Durable Functions, Restate | Re-run plan; check log before each tool call |
| **Workflow / Activity split** | Temporal, Restate, DBOS | Plan step (deterministic) vs tool call (effect) |
| **Workflow ID as idempotency key** | DBOS, Stripe | `<run-id>/` directory = single-flight start |
| **Continue-As-New / phase rollover** | Temporal, Durable Functions | When `events.jsonl` > N, archive + start new phase |
| **Saga compensations** | García-Molina, Temporal Saga, Step Functions Catch | Each step has paired `undo:` instruction in the plan |
| **Retries with backoff + jitter** | Step Functions, Temporal, Stripe | `backoff = base * 2^attempt ± jitter`, max N |
| **Idempotency keys** | Stripe | `<idempotency-key>.json` created via `O_CREAT\|O_EXCL` |
| **Worker Versioning / Pinned deploys** | Temporal, Restate | Pin loop to `AGENTS.md` hash; roll forward at phase rollover |
| **History-table checkpointing** | Durable Functions, LangGraph | `state.json` derived from the event log |
| **`thread_id` as resume key** | LangGraph | The loop's `run-id` |
| **`interrupt()` / human-in-the-loop** | LangGraph, Temporal signals | `pending-approval:<token>` file in `.loop/` |
| **Command(update=, goto=)** | LangGraph | Atomic state-file write + routing decision |
| **Compaction** | Anthropic, LangChain | `.loop/compaction-<N>.md` summary file |
| **Structured note-taking** | Anthropic | `NOTES.md`, `progress.md` written by the agent |
| **Multi-agent handoff schema** | Anthropic Research, Wire | `result.json` with 4 fixed fields |
| **Sub-agent with clean context** | Anthropic Managed Agents, Cognition | Sub-task dir, fresh prompt, summary-only handoff back |
| **`wake(sessionId)` / `getSession(id)`** | Anthropic Managed Agents | The `create-loop` entry point reads `.loop/state.json` |
| **Handoff: git diff + repo + branch** | Cognition `devin-handoff` | Canonical "context bundle" for cross-session resume |
| **`isReplaying` guard** | Durable Functions | Check if state is fresh before logging/external side effects |
| **Saga compensations = undo stack** | García-Molina | Compensations array in `.loop/state.json`, run in reverse on failure |

---

## Suggested Reading Order for Spec Authors

1. **Foundations** — García-Molina saga paper + Anthropic "Building Effective Agents" + ReAct paper. (30 min total)
2. **Persistence primitives** — Temporal Event History + LangGraph Persistence. (45 min)
3. **Long-running agents** — Anthropic "Effective Harnesses" + "Context Engineering" + "Managed Agents." (60 min)
4. **Cross-system comparison** — Restate "What is durable execution" + DBOS architecture + Step Functions Standard vs Express. (45 min)
5. **Production patterns** — Cognition Devin Sonnet 4.5 lessons + Anthropic Multi-Agent Research. (60 min)

Total: ~4 hours to have the full landscape internalized before writing the spec.

**Report delivered.** Three areas covered, every mechanism has:

- Name + one-paragraph core idea
- Source URL(s) (often 2–3 per major mechanism)
- One-line "FS map" — how it ports to a filesystem-only, no-runtime environment

**Coverage at a glance:**

- **§1 Durable execution**: Temporal (event history, replay, versioning, Continue-As-New, saga, side effect), DBOS (steps, transactions, communicators, outbox), Restate (journal, immutable deploys, durable promises), Step Functions (ASL, Standard vs Express, state types, retries, catch), Durable Functions (history table, replay, IsReplaying, entities), plus cross-cutting idempotency keys and the original García-Molina saga paper.
- **§2 Agentic loops**: ReAct (Yao et al.), Anthropic's full agent-engineering corpus (Building Effective Agents, Effective Harnesses, Harness Design, Managed Agents, Context Engineering, Multi-Agent Research), and Cognition's Devin (session/sleep/wake, ACUs, knowledge store, Fusion, handoff-to-cloud).
- **§3 Checkpoint & recovery**: LangGraph's full persistence model (thread ID, per-superstep + per-node writes, `interrupt()`, `Command`/`Send`, time travel, HITL middleware, handoff schemas, subgraph namespaces) + the Wire post on handoff corruption.

The closing cross-cutting table maps ~20 mechanisms to filesystem primitives you can encode directly into `concepts.md` / `recovery_protocol.md` / `state_model.md`.