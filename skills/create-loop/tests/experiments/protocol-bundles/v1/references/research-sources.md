# Reference Material: `create-loop` Skill — `loop.plan` DAG + Evidence Gates

This report covers task graphs, multi-agent coordination, evidence gates, and state machines for agent execution. Every entry has a source URL and a one-line "filesystem-only mapping" note so the pattern can be lifted directly into `loop.plan` (no database required, no broker required — every reference below has a JSON-on-disk equivalent).

---

## 0. Two Cross-Cutting Primary Sources (Read These First)

These two papers are **directly about this design problem** and synthesize the four areas below into a single framework. They should be cited in `loop_plan_spec.md` itself, not buried in supporting docs.

### 0.1 **Graph Harness (Structured Graph Harness / SGH)** — Scheduler-Theoretic Agent Execution
- **Idea**: Formalizes the agent loop as a *single-ready-unit, non-deterministic scheduler* and proposes a structured graph-based alternative. Three commitments: (1) execution plan is an **immutable commitment** for a plan version, (2) **planning / execution / recovery are three independent layers** with well-defined interfaces, (3) recovery follows a **strict escalation protocol** (`{local_retry, local_patch, replan}` — bounded, never infinite). Execution system is a tuple `E = (S, U, P, O, Δ)`; ready-set cardinality `|U(S)|` and policy explicitness are the two axes to optimize.
- **Source**: <https://arxiv.org/abs/2604.11378> (April 2026) · PDF: <https://www.arxiv.org/pdf/2604.11378>
- **Filesystem mapping**: The plan is a versioned JSON file; once `version` is set, `Δ` (state transitions) only mutates `state.json`, never `plan.json`. The escalation ladder is a small enum on each node contract: `retry → patch → replan → escalate`.

### 0.2 **From Model Scaling to System Scaling: Scaling the Harness in Agentic AI**
- **Idea**: Defines the harness as six components — `R` (reasoner), `M` (memory), `C` (context constructor), `S` (skill/sub-agent router), `O` (orchestration loop), `G` (verification & governance). Performance is decomposed as a function of these. "Dynamic skill routing is the analogue of scheduling in operating systems… making post-condition checking a first-class component of each skill specification." Skill quality × verification quality is the tradeoff, not either alone.
- **Source**: <https://arxiv.org/html/2605.26112>
- **Filesystem mapping**: Map each component to a folder — `R=llm_call.json`, `M=memory/`, `C=context/`, `S=skills/<skill>.contract.json`, `O=loop.runner`, `G=evidence/<node_id>.gate.json`. Every skill spec gets a `post_condition` block.

---

## 1. Task Graphs / DAG Workflow Engines

The foundation of `loop.plan` is "DAG of nodes with real artifact dependencies." Each system below contributes one specific idea.

### 1.1 **Apache Airflow — Dynamic Task Mapping**
- **Idea**: A DAG declares structure at parse time, but `task.expand()` and `task.expand_kwargs()` **defer the cardinality of a downstream task to runtime** — the scheduler materializes N task instances only after the upstream XCom returns. Combines `.partial(...)` (static args) with `.expand(...)` (mapped args). Can be applied to a `@task_group` (subgraph expansion) and to a list of dicts. This is the "recursive subgraph generation" pattern: a node in the DAG yields N child plans and the scheduler materializes them.
- **Sources**:
  - Dynamic Task Mapping: <https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/dynamic-task-mapping.html>
  - Task SDK dynamic mapping: <https://airflow.apache.org/docs/task-sdk/stable/dynamic-task-mapping.html>
  - Source: `airflow/models/expandinput.py` — <https://airflow.apache.org/docs/apache-airflow/2.5.3/_modules/airflow/models/expandinput.html>
- **Filesystem mapping**: A `loop.plan` node can carry `kind: "mapper"` with `expand.input_ref: "<upstream_node_id>.output"`. The loop runner reads the upstream output JSON array, deep-copies the node template, emits N materialized child plans under `evidence/<parent>/<index>/plan.json`, then links them by `parent_ref` to the mapper node.

### 1.2 **Prefect 3 — `.submit()` / `.map()` + Task Runners + Subflows**
- **Idea**: Three concentric layers — *tasks* (atomic, cached, retried, transactional), *flows* (composable, schedulable, persistable), *subflows* (recursive composition with isolated task runners). `.submit()` returns a `PrefectFuture`; `.map()` iterates an iterable; `wait_for=[]` declares non-data ordering dependencies. Concurrency is *pluggable* (`ThreadPoolTaskRunner`, `ProcessPoolTaskRunner`, `DaskTaskRunner`, `RayTaskRunner`). Subflows create a **fresh task runner** on entry and tear it down on exit, so nested flows can't deadlock the parent.
- **Sources**:
  - Tasks: <https://docs.prefect.io/v3/concepts/tasks>
  - Flows: <https://docs.prefect.io/v3/concepts/flows>
  - Task runners: <https://docs.prefect.io/v3/concepts/task-runners>
  - Run concurrently: <https://docs.prefect.io/v3/how-to-guides/workflows/run-work-concurrently>
- **Filesystem mapping**: A `loop.plan` is a flow. Each node has `concurrency: "serial" | "concurrent:thread:N" | "concurrent:process:N"`. Subflows are plans that reference other plans by path. The runner writes a `PrefectFuture`-shaped record to `state/<run_id>/<node_id>.future.json` (status + task_run_id — local file here, just the file itself).

### 1.3 **Dagster — Dynamic Graphs, `DynamicOut` / `map` / `collect`**
- **Idea**: An op annotated `out=DynamicOut()` `yield`s `DynamicOutput(value, mapping_key)` objects. Downstream ops cannot consume the dynamic output directly — they must call `.map(callable)` (clone the op per mapping_key, **fan-out** with dependency edges) or `.collect()` (single op receives list of all values, **fan-in**). The mapping_key becomes a unique identifier for each cloned op. Partitions are orthogonal: `daily_partitioned_config` × `static_partitioned_config` × `dynamic_partitioned_config` allow expressing "run this subgraph 5 times on these 5 keys."
- **Sources**:
  - Dynamic graphs: <https://docs.dagster.io/guides/build/ops/dynamic-graphs>
  - Op graphs: <https://docs.dagster.io/guides/build/ops/graphs>
  - Partitioning ops: <https://docs.dagster.io/guides/build/partitions-and-backfills/partitioning-ops>
  - Graph-backed assets: <https://docs.dagster.io/guides/build/assets/graph-backed-assets>
- **Filesystem mapping**: `DynamicOutput(value, mapping_key)` is the `Evidence { value, key, parent_node }` record. A `loop.plan` node of `kind: "dynamic"` carries a list of mapping_keys up front (static) or reads them from an upstream `evidence/<id>/values.json` at runtime. The loop runner materializes child plans to `evidence/<node_id>/<mapping_key>/plan.fragment.json`.

### 1.4 **Argo Workflows — `dag` / `dependencies` / `withParam` / `depends`**
- **Idea**: Workflows are a `templates` list. A template is a `DAGTemplate` (explicit `dependencies: [A, B]` on each task) or a `StepsTemplate` (nested list of lists — outer = sequential, inner = parallel). Dynamic fan-out via `withParam: "{{steps.gen.outputs.result}}"` reads a runtime JSON array and spawns one step instance per item. `failFast: true` by default; set `false` to keep independent branches alive. Enhanced `depends` supports boolean expressions: `depends: "(task-2.Succeeded || task-2.Skipped) && !task-3.Failed"`. Synchronization via mutex/semaphore/parallelism-limit caps concurrency globally or per-template.
- **Sources**:
  - DAG: <https://argo-workflows.readthedocs.io/en/stable/walk-through/dag/>
  - Steps: <https://argo-workflows.readthedocs.io/en/stable/walk-through/steps/>
  - Enhanced depends: <https://argo-workflows.readthedocs.io/en/latest/enhanced-depends-logic/>
  - Synchronization: <https://argo-workflows.readthedocs.io/en/latest/synchronization/>
- **Filesystem mapping**: `dependencies: [A, B]` becomes `requires: ["<node_id>"]` in `loop.plan`; the runner topologically sorts the node list and only schedules a node when every entry in `requires` is in `state.COMPLETED`. `depends` boolean expressions become a small `gate` DSL evaluated against the node's evidence file. `parallelism: 5` becomes a `concurrency_limit` on the plan.

### 1.5 **GNU Make — Dependency = Real Artifact (mtime), Topological Walk**
- **Idea**: The dependency graph is **derived from the filesystem**, not declared abstractly: `report.pdf: report.tex data.csv` means *the existence + freshness of `report.pdf` is a function of `report.tex` and `data.csv`*. Make parses the makefile, builds the dep graph, topologically walks it (DFS-based, with cycle detection via an `updating` bit on each `file`), and only re-runs a rule if the target is missing or any prerequisite is newer. Intermediate files are deleted at the end. The dual notion of **declared dependencies** vs **actual dependencies** is the basis of Bazel's correctness story.
- **Sources**:
  - `remake.c` (the dependency engine): <https://github.com/lindenb/make/blob/30843dea3a17f84b7456f68d75e5cd6bd5c5e11b/remake.c>
  - fuchsia tree: <https://fuchsia.googlesource.com/third_party/make/+/a174e2f83b9ae3c60968fb200b4b367f4109e8ce/remake.c>
  - Algorithmic analysis: <https://ramsayleung.github.io/en/post/2022/topological_sorting/>
- **Filesystem mapping**: This is the **purest** filesystem mapping — `make` already is one. A `loop.plan` node declares its artifact by path (`produces: "out/feature.json"`) and lists its `requires` as paths (`requires_artifact: ["in/data.csv"]`). The runner does the equivalent of `stat -c %Y` and skips re-running if `produces.mtime > max(requires.mtime)` and the gate evidence file already exists. **Make's "dep is an actual file" is the moat against habitual-order-only DAGs.**

### 1.6 **Bazel — Action Graph, Declared vs Actual, `aquery`**
- **Idea**: Bazel separates three graphs: the **target graph** (from `BUILD` files, declared deps), the **configured target graph** (post-analysis, with select() resolved), and the **action graph** (post-analysis, bipartite: `Action` ↔ `Artifact`, where each Action is `Artifact → Artifact` and has a `getKey()` whose change invalidates the action). For correct builds, **actual-deps ⊆ declared-deps** — Bazel flags missing declared deps. `bazel aquery` exposes the action graph for inspection; `bazel query` for declared deps. The action key is the cache invalidator: change a compiler flag → action key changes → rebuild.
- **Sources**:
  - Action Graph Query: <https://bazel.build/query/aquery>
  - Introducing aquery: <https://blog.bazel.build/2019/02/15/introducing-aquery.html>
  - Dependencies: <https://github.com/bazelbuild/bazel/blob/master/site/en/concepts/dependencies.md>
  - Query guide: <https://bazel.build/versions/9.1.0/query/guide>
- **Filesystem mapping**: Every `loop.plan` node contract has a `cache_key: "<hash(inputs+prompt+model+config)>"` field. Before running, the runner computes the key, checks if `evidence/<node_id>/<cache_key>/output.json` already exists, and skips. This is how resumability across crashed runs is achieved without a database.

---

## 2. Multi-Agent Orchestration

`loop.plan` is single-process / single-runner, but the *nodes* of the plan can be sub-agents, and `branching_parallelism.md` needs to know which coordination pattern to use when.

### 2.1 **LangGraph — `StateGraph`, Edge Vocabulary, Subgraphs, `Send`**
- **Idea**: The single most important reference. LangGraph models an agent as a `StateGraph` with a typed state schema (a `TypedDict` with **reducers** like `Annotated[list, operator.add]` for fan-in accumulation), nodes that return state updates, and four edge types:
  - `add_edge(src, dst)` — fixed, deterministic
  - `add_conditional_edges(src, path_fn, path_map=...)` — state-driven routing (returns node name or `END`)
  - `Command(update={...}, goto=...)` — node returns state update + next node in one value
  - `Send(node_name, state_payload)` — **dynamic parallel fan-out**: a routing function returns a list of `Send` objects, LangGraph runs them all in a single **superstep** and waits for every branch before the next superstep
  - **Subgraphs**: a node's `state` can be a private `TypedDict`; the parent and subgraph communicate only at the boundary, giving you **context isolation**
  - **Persistence + interrupts**: a `checkpointer` snapshots state at every superstep, so a graph can pause, persist, and resume — the foundation of long-running agents
- **Sources**:
  - Graph API overview: <https://docs.langchain.com/oss/python/langgraph/graph-api>
  - Use the graph API: <https://docs.langchain.com/oss/python/langgraph/use-graph-api>
  - `add_conditional_edges` reference: <https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges>
  - LangGraph skills repo: <https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/langgraph-fundamentals/SKILL.md>
- **Filesystem mapping**: This is *almost* a perfect 1:1. The `loop.plan` is the StateGraph definition. `State` becomes `state.json` per run. `add_edge` → `requires: [a]`. `add_conditional_edges(path_fn=...)` → a node with `kind: "branch"` and a `path_fn_ref: "skills/branch/score.py"`. `Command` → a node's return is `{update: <state patch>, goto: <next_node>}` written to `evidence/<node_id>/return.json`. `Send` → a `kind: "fanout"` node whose `expand` references a prior node's output. **The four edge types are the section headers of `branching_parallelism.md`.**

### 2.2 **LangGraph Supervisor — Hierarchical via Tool-Based Handoffs**
- **Idea**: `create_supervisor([agent_a, agent_b], model=llm, tools=[...])` returns a `StateGraph` where each worker is a compiled subgraph and the supervisor is an LLM that decides which to call next via **`create_handoff_tool(agent_name=...)`** — a tool whose return value is a `Command(goto=agent_name, graph=Command.PARENT, update={...})`. The handoff tool can carry a structured `task_description: str` injected into the worker's state. Default behavior appends `(AIMessage, ToolMessage)` handoff pairs to message history; opt-out via `add_handoff_messages=False`.
- **Sources**:
  - Source repo: <https://github.com/langchain-ai/langgraph-supervisor-py>
  - API reference: <https://reference.langchain.com/python/langgraph-supervisor/supervisor/create_supervisor>
- **Filesystem mapping**: A `kind: "supervisor"` node in `loop.plan` lists `workers: [<plan_id_1>, <plan_id_2>]`, `model: "<model_ref>"`, and `tools: [handoff_<worker>.json]`. The handoff is persisted to `evidence/<node_id>/handoffs/<worker_id>.json` with the full state patch — this is "agent produced structured handoff, not free-form prose."

### 2.3 **LangGraph Swarm — Peer-to-Peer Handoffs, Active-Agent Router**
- **Idea**: No supervisor. Each agent has a handoff tool that transitions to another agent, and the swarm tracks the **last active agent** in `state.active_agent` (a required field on `SwarmState` — extending `MessagesState` with `active_agent: str | None`). `add_active_agent_router(...)` wires the next-step resolution: if no handoff tool was called, route back to the default active agent. Validates at runtime that the state schema contains `active_agent`.
- **Sources**:
  - Source repo: <https://github.com/langchain-ai/langgraph-swarm-py>
  - API: <https://reference.langchain.com/python/langgraph-swarm>
- **Filesystem mapping**: A `kind: "swarm"` plan; `state.json` has an `active_agent` field; each node's handoff writes `evidence/<node_id>/<ts>/active_agent.txt` and the runner uses it to dispatch the next node. The "router" is a tiny `swarm_router.py` that reads `state.json` and writes `next_node.json`.

### 2.4 **OpenAI Swarm / Agents SDK — Handoffs and "Agents as Tools"**
- **Idea**: The original Swarm cookbook crystallized "a handoff is an agent returning an `Agent` from a tool call." The successor **OpenAI Agents SDK** codifies two orthogonal ownership patterns: **handoffs** (specialist takes over the conversation — `triage.handoffs = [billing_agent, refund_agent]`) and **agents as tools** (manager keeps ownership and calls `specialist_tool` to get structured output). The SDK also ships `nest_handoff_history=True` to collapse transcript into a single summary message at the handoff boundary. Swarm README is now archived; Agents SDK is the production target.
- **Sources**:
  - Agents SDK handoffs: <https://openai.github.io/openai-agents-python/handoffs/>
  - Orchestration guide: <https://developers.openai.com/api/docs/guides/agents/orchestration>
  - Swarm cookbook: <https://developers.openai.com/cookbook/examples/orchestrating_agents>
  - Swarm GitHub: <https://github.com/openai/swarm>
- **Filesystem mapping**: The two patterns become two `loop.plan` node kinds. `kind: "handoff"` = control transfer (write full state to `evidence/<node_id>/handoff.json`, runner stops current plan and starts the target plan from checkpoint). `kind: "delegate"` = nested call (current plan waits, target plan runs to completion, return value is structured output merged into state).

### 2.5 **CrewAI — Flows + Crews, Sequential/Hierarchical Process**
- **Idea**: Two abstractions stacked. A **Flow** owns `state` and `@start()` / `@listen()` decorators declare the DAG (which steps listen for which events, including external triggers). A **Crew** is a group of role-specialized `Agent`s collaborating on `Task`s with a `Process.sequential` or `Process.hierarchical` (manager agent) execution model. Tasks have explicit `context: [other_task_names]` to declare output dependencies. `allow_delegation=True` on an agent auto-registers `ask_question` / `delegate_work` tools. `guardrail` + `guardrail_max_retries` enforce validation on each task output.
- **Sources**:
  - Crews: <https://docs.crewai.com/en/concepts/crews>
  - Tasks: <https://docs.crewai.com/en/concepts/tasks>
  - Collaboration: <https://docs.crewai.com/en/concepts/collaboration>
  - Introduction (Flows vs Crews): <https://docs.crewai.com/en/introduction>
- **Filesystem mapping**: A `kind: "flow"` plan; each `@start`/`@listen` step is a node with `trigger: "<previous_node>.completed"`. Tasks are sub-nodes with `context: [<task_id>]` which becomes a precondition on the parent step.

### 2.6 **AutoGen — GroupChat, SelectorGroupChat, Nested Chats**
- **Idea**: `GroupChat` is a *single thread* shared by all participants; a `GroupChatManager` agent uses an LLM to select the next speaker (`speaker_selection_method: "auto" | "round_robin" | "random" | "manual"`). `SelectorGroupChat` is the same shape with model-based selection. **Nested chats** let you "package a workflow as a single agent" — when an agent receives a message matching a trigger, it runs a sequential chat queue and returns the summary. `register_nested_chats(chat_queue=[...], trigger=fn)` is the API. Useful for: workflows that should be reusable as a node inside a larger workflow.
- **Sources**:
  - Group chat (current): <https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/design-patterns/group-chat.html>
  - SelectorGroupChat: <https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html>
  - Conversation patterns: <https://microsoft.github.io/autogen/0.2/docs/tutorial/conversation-patterns/>
- **Filesystem mapping**: `kind: "group_chat"` plan with `participants: [agent_a, agent_b]`, `selector: {method: "auto" | "round_robin", model: "..."}`. The next-speaker decision is written to `evidence/<node_id>/next_speaker.json` for inspection (this is the "policy explicitness" the SGH paper pushes for).

### 2.7 **Anthropic Multi-Agent Research System — Orchestrator-Worker in Production**
- **Idea**: The cleanest production write-up of the orchestrator-worker pattern. A `LeadResearcher` agent plans the work, saves the plan to memory, then **spawns 3–5 subagents in parallel**, each with: (1) a self-contained task description, (2) an output format, (3) a tool list, (4) clear "done" boundaries. Each subagent uses 3+ tools in parallel inside its own context window and returns a *condensed* summary, not a long chat. The lead reconciles, decides if more research is needed, either spawns another wave or moves on. **Result: 90.2% improvement over single-agent Opus 4 on research evals, 90% time reduction, ~15x token cost.** Critical design rule: each subagent must be *truly independent* (doesn't see other subagents, can't coordinate mid-task) — otherwise the parallel speedup collapses into expensive serial.
- **Source**: <https://www.anthropic.com/engineering/multi-agent-research-system>
- **Filesystem mapping**: `kind: "orchestrator_worker"` plan; the orchestrator node emits a `plan_subgraph.json` with N entries; the runner spawns N child processes (or N async tasks in a worker pool, given the filesystem-only constraint) and writes each child's output to `evidence/orchestrator/<i>/return.json`. The "isolation boundary" is enforced by giving each child its own working directory under `runs/<run_id>/<orchestrator>/<i>/` so context cannot leak.

### 2.8 **LangGraph Map-Reduce with `Send` API**
- **Idea**: The canonical implementation of fan-out / fan-in in LangGraph. A node returns a list of `Send` objects, one per item, each carrying `(target_node_name, per_branch_state)`. LangGraph runs all branches in parallel within a single superstep, accumulates results via a `Annotated[list, operator.add]` reducer on the fan-in node's input, and only moves to the next superstep when every branch has returned. `defer=True` on a fan-in node defers its execution until all pending tasks across asymmetric branch lengths are done.
- **Sources**:
  - Graph API overview (`Send` section): <https://docs.langchain.com/oss/python/langgraph/graph-api>
  - Map-reduce walkthrough: <https://machinelearningplus.com/gen-ai/langgraph-map-reduce-parallel-execution/>
  - Trade-offs: <https://aipractitioner.substack.com/p/scaling-langgraph-agents-parallelization>
- **Filesystem mapping**: A `kind: "map"` plan node; the routing function is a small script that reads `evidence/<upstream>/values.json` and emits a list of partial plans to `evidence/<map>/dispatches/<i>.json`. The fan-in node is `kind: "reduce"` with `reducer: "concat" | "merge" | "vote"` — applied to the N `return.json` files.

---

## 3. Verification / Evidence Gates

This is the heart of `loop.plan`'s "evidence gates" concept. Each entry below is a distinct verification mechanism with a different cost / strength profile.

### 3.1 **LLM-as-a-Judge — Zheng et al. 2023**
- **Idea**: Strong LLMs (GPT-4) can match both controlled and crowdsourced human preferences at **>80% agreement**, the same as human-human agreement. The MT-bench and Chatbot Arena paper establishes that LLM judges are a "scalable and explainable way to approximate human preferences." Documented biases: **position bias** (prefer first option), **verbosity bias** (prefer longer answers), **self-enhancement bias** (prefer own outputs), **limited reasoning ability** (struggle on multi-step math/logic). Mitigations: swap positions, control length, reference a known-good baseline, restrict judge to a rubric.
- **Source**: <https://arxiv.org/abs/2306.05685> (NeurIPS 2023)
- **Filesystem mapping**: A `kind: "judge"` gate node in `loop.plan` carries `rubric: "rubrics/<gate>.md"`, `model: "<model_ref>"`, `aggregation: "mean" | "majority" | "weighted"`. The judge reads the upstream node's `return.json` and writes `score: 0..1` + `rationale: str` to `evidence/<gate>/verdict.json`. The `node.contract.schema.json` should require a `gate: { kind, threshold, rubric }` block on every node.

### 3.2 **Self-Consistency — Wang et al. 2022**
- **Idea**: Sample K diverse reasoning paths for a problem (high temperature), then **marginalize** (majority vote on the final answer, or aggregate rationales). Works because complex problems admit many valid reasoning paths that all converge on the same correct answer; disagreement is a signal of low confidence. Strong gains on GSM8K (+17.9%), SVAMP (+11%), AQuA (+12.2%), StrategyQA (+6.4%), ARC (+3.9%). Also provides *calibration* — the agreement rate among K samples is an honest uncertainty estimate.
- **Source**: <https://arxiv.org/abs/2203.11171>
- **Filesystem mapping**: A `kind: "self_consistency"` gate; the runner samples K times (K written to `state.json` for the gate), each sample written to `evidence/<gate>/samples/<i>.json`; an aggregator node reduces to `evidence/<gate>/majority.json`. This is a "fan-out + vote" inside a single evidence-gate node — the simplest non-trivial verification pattern.

### 3.3 **Tree of Thoughts — Yao et al. 2023**
- **Idea**: Generalizes CoT from a linear chain to a search tree. At each step, generate K candidate "thoughts" (coherent text units, not single tokens), **evaluate** each via an LLM (or a heuristic), keep the top B, then recurse. BFS or DFS with backtracking. On Game of 24, GPT-4 + CoT = 4% success, ToT = 74%. The "thought" abstraction is what makes it different from repeated sampling — each node in the search tree is a *partial plan*, evaluated against a goal, with the option to backtrack.
- **Source**: <https://arxiv.org/abs/2305.10601> (NeurIPS 2023 oral) · Code: <https://github.com/princeton-nlp/tree-of-thought-llm>
- **Filesystem mapping**: A `kind: "tree_of_thoughts"` gate; the runner builds a tree of `evidence/<gate>/tree/<depth>/<branch>.json` (each leaf has a `score` and `state`); the highest-scoring complete path is `evidence/<gate>/best.json`. This is a "sub-plan" in `loop.plan` vocabulary: a node that itself contains a small DAG of thought-eval-expand steps, with an inner budget.

### 3.4 **Reflexion — Shinn et al. 2023**
- **Idea**: Reinforce language agents not by weight updates but by **linguistic self-reflection**. After each trial, the agent reflects verbally on the failure, stores the reflection in an **episodic memory buffer**, and the next trial uses the accumulated reflections as additional context. Strategies: `NONE`, `LAST_ATTEMPT`, `REFLEXION`, `LAST_ATTEMPT_AND_REFLEXION`. Reflexion achieves **91% pass@1 on HumanEval** vs. GPT-4's prior 80%. The key is that the *reflection model* is itself an LLM call — the agent "explains to itself" what went wrong, and the explanation is more informative than a scalar reward.
- **Sources**:
  - Paper: <https://arxiv.org/abs/2303.11366> (NeurIPS 2023)
  - Code: <https://github.com/noahshinn/reflexion>
- **Filesystem mapping**: A `kind: "reflexion_loop"` node carries `max_trials: N`, `reflection_model: "..."`. After each trial, the runner writes `evidence/<node_id>/trial_<i>/output.json` and `evidence/<node_id>/trial_<i>/reflection.json`. The next trial's prompt is constructed by concatenating the last K reflections. This is "subgraph recursion" in `loop.plan` terms.

### 3.5 **Anthropic Evaluator-Optimizer Pattern (Building Effective Agents)**
- **Idea**: One LLM generates, a *separate* LLM evaluates against explicit criteria, generator iterates on the feedback. Use when "LLM responses can be demonstrably improved when a human articulates their feedback" AND "the LLM can provide such feedback." This is the production-grade generator-verifier separation. Anthropic also ships the **orchestrator-worker**, **prompt chaining**, **routing**, and **parallelization** patterns here — the canonical "agent building blocks" reference.
- **Source**: <https://www.anthropic.com/research/building-effective-agents>
- **Filesystem mapping**: A `kind: "evaluator_optimizer"` gate is a two-node subgraph: `generator` + `evaluator`. Evaluator writes `evidence/<eval>/feedback.json` (structured, with pass/fail per criterion, not free-form "looks good"). Generator retries with the feedback as additional context. The `eval-protocol` style spec (each criterion is `{name, rubric, threshold}`) is the `gate.rubric` field.

### 3.6 **Process Reward Models (PRMs) — Step-Level Verifiers**
- **Idea**: A judge that scores *each step* of a reasoning trajectory, not just the final answer. Two recent variants: **ThinkPRM** (long chain-of-thought verifier, fine-tuned on 1% of process labels, outperforms LLM-as-Judge and discriminative PRMs under best-of-N), **GenPRM** (generative verifier with explicit CoT + code verification before scoring; 1.5B GenPRM outperforms GPT-4o on ProcessBench). The conceptual shift: a *step* is a node in a small DAG, and the verifier can be applied at each node (every edge is an evidence gate).
- **Sources**:
  - ThinkPRM: <https://arxiv.org/abs/2504.16828>
  - PRM survey: <https://arxiv.org/html/2510.08049v3>
- **Filesystem mapping**: A `kind: "step_verifier"` gate; for each step in a multi-step node's output, the runner calls a PRM and writes a per-step score. **This is the most important pattern for `evidence_gates.md`** — it means *every* intermediate output in a long node gets its own gate, not just the final result.

### 3.7 **CodeAct — Tests as Evidence via Sandboxed Execution**
- **Idea**: Instead of one tool call at a time, give the model a single `execute_code` tool backed by a sandbox. The model writes a short Python program that calls the same tools via `call_tool(...)`; the sandbox runs the program once, returns the consolidated result. The result is *itself* a test artifact — wrap the call with assertions and inspect the trace. Microsoft Agent Framework reports ~50% latency cut and >60% token reduction vs. the model-tool-model-tool loop.
- **Sources**:
  - Microsoft Agent Framework: <https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/>
  - CodeAct overview: <https://learn.microsoft.com/en-us/agent-framework/agents/code_act>
  - LlamaIndex CodeAct: <https://developers.llamaindex.ai/python/examples/agent/code_act_agent/>
- **Filesystem mapping**: A `kind: "codeact"` node in `loop.plan` has `sandbox: { fs_root: "<dir>", allow_network: bool, timeout: <sec> }`; the LLM writes a script to `evidence/<node_id>/program.py`, the runner executes it in a chroot/namespace, and the assertion results go to `evidence/<node_id>/test_results.json`. **This is the "the evidence is the test result" pattern** — strongest signal-to-noise ratio of any gate because it's deterministic.

### 3.8 **Eval-Driven / TDD-Style Agent Development**
- **Idea**: Treat evals as the test suite. Before writing the agent, write evals that define the desired behavior. The agent is built to pass them. New features / model swaps run the eval suite as a regression check. This is the workflow that `claude-eval` (`PASSED/FAILED` per criterion), `tdd-guardian-for-claude` (coverage + mutation gates pre-commit), and `claude-code-tdd-workflow` (planner / implementer / verifier in separate context windows with file-system boundaries) all implement. The Anthropic harness design post makes the same point: the **evaluator is structural, not optional**.
- **Sources**:
  - Anthropic harness design: <https://www.anthropic.com/engineering/harness-design-long-running-apps>
  - Anthropic long-running harness: <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
  - Effective tools for agents: <https://www.anthropic.com/engineering/writing-tools-for-agents>
  - TDD Guardian: <https://github.com/xiaolai/tdd-guardian-for-claude>
  - TDD workflow plugin: <https://github.com/hugo-bluecorn/claude-code-tdd-workflow>
  - Automated TDD pipeline: <https://github.com/elasticLove1/claude-code-tdd>
- **Filesystem mapping**: The runner's "test suite" is the `evals/<plan>.eval.yaml` file — a list of `{gate_id, kind, threshold}`. Before any node runs in a new run, the runner validates that all referenced gates still exist and pass on a fixture. **This is what makes `loop.plan` not just executable but verifiable.**

### 3.9 **Structured Cognitive Loop (SCL) — Separate Cognition, Memory, Control**
- **Idea**: LLM handles cognition, memory is external (in this design: files), execution is guided by a lightweight controller inside a goal-directed loop. Intermediate results are *recorded and verified* before actions are taken. SCL achieves 86.3% task success vs. 70.5–76.8% for ReAct/LangChain baselines on travel planning, email drafting, and constrained image generation. The "separation of process grounding from sub-task solving" is the design principle.
- **Source**: <https://arxiv.org/pdf/2510.05107>
- **Filesystem mapping**: Maps cleanly to the three layers — `R` (LLM call node) / `M` (`state.json` + `memory/`) / `O` (the loop runner itself). The SCL paper's evaluation is direct support for "explicit gates are better than implicit ones" as a claim in `loop_plan_spec.md`.

---

## 4. State Machines for Agents

`loop.plan` needs an internal status enum. The systems below show what the enum, transitions, and guards should look like.

### 4.1 **StateFlow — Formal FSM for LLM Workflows (arXiv 2403.11322)**
- **Idea**: Models LLM workflows as FSMs. The formal model is a sextuple `(S, s0, F, δ, Γ, Ω)`: states `S`, initial state `s0`, terminal states `F`, transition function `δ: S × Γ* → S` (operates on the *context history*, not a single token), output alphabet `Γ` (prompts `P`, LLM responses `C`, tool/environment feedback `O`), output functions `Ω` (LLM, tool call, or static prompter). Two transition kinds: **static string matching** (fast, deterministic, e.g. tool returns "Error" → `Error` state) and **LLM-decided** (flexible, costly, "given current output and task state, which state to transition to?"). Max-turns counter prevents infinite loops.
- **Source**: <https://arxiv.org/html/2403.11322v1> · <https://openreview.net/pdf?id=CZAs3WFw5r>
- **Filesystem mapping**: `S` = node's `status` enum. `δ` = gate conditions evaluated against `evidence/<node>/<output>.json`. `Γ*` = the cumulative `state.json`. Use this paper to justify the FSM framing in `evidence_gates.md` and to anchor the schema for `state.status` in `node.contract.schema.json`.

### 4.2 **FSM-agent-flow — TDD/OKR-Driven FSM for LLM Apps**
- **Idea**: Each state declares an **objective** and a list of **key results** — equivalent to a test suite. The state is entered, the LLM runs, the key results are checked before advancing. Failed states retry with the validator's feedback. Transitions are not just linear: conditional dict-based routing (`{output_key: target_state}`), bidirectional flows, retry loops. **No global singletons**; tools are scoped per state. Roughly maps to the gate-per-node contract.
- **Source**: <https://github.com/NewJerseyStyle/FSM-agent-flow>
- **Filesystem mapping**: A `kind: "fsm"` plan; each state node has `objective: str`, `key_results: [{id, kind, rubric, threshold}]`, `on_fail: {retry: N, goto: <state>}`. The runner evaluates key results against `evidence/<state>/output.json` and refuses to advance if any key result fails.

### 4.3 **Microsoft UFO — 7-State AgentStatus Enum**
- **Idea**: A clean production reference. The `HostAgentStatus` enum has exactly 7 values: `CONTINUE, FINISH, FAIL, ERROR, PENDING, CONFIRM, SCREENSHOT`. The transition table is explicit: from `CONTINUE` you can go to `FINISH, FAIL, ERROR, PENDING, CONFIRM, AppAgent.CONTINUE`; from `FINISH/FAIL/ERROR` you go nowhere (terminal); from `PENDING` you can go to `CONTINUE` or `FAIL` on timeout. Some transitions are LLM-controlled (the agent's response sets `Status: "ASSIGN"`), others are system-controlled (AppAgent return → back to `CONTINUE`). `PENDING` and `CONFIRM` are explicit waiting states for human-in-the-loop.
- **Source**: <https://github.com/microsoft/UFO/blob/main/documents/docs/infrastructure/agents/design/state.md>
- **Filesystem mapping**: A literal `status` enum in the schema. Add `BLOCKED` (gate failed) and `ESCALATED` (recovery layer gave up) for the escalation protocol. The transition table becomes a JSON Schema `enum` + a validator function.

### 4.4 **Production Agent State Machines — Hossain 2026**
- **Idea**: The most explicit "FSMs beat free-form" argument. Defines: finite states (e.g. `FETCHING_CONTEXT, ANALYZING, POSTING_COMMENTS, SUMMARIZING, COMPLETED, FAILED`), transitions (event → target state, with optional **guards** that read from persistent context, not in-memory), actions per state that are *idempotent* (safe to re-enter on retry). Critical property: **"given the current state and an input event, there is exactly one next state"** — this is what makes "where did this run fail?" answerable from the filesystem. The guard `[retries < 3]` is the key mechanism that converts the "infinite retry" failure mode into bounded deterministic behavior.
- **Source**: <https://mdsanwarhossain.me/blog-ai-agent-state-machines.html>
- **Filesystem mapping**: `state.json` is the persistent context. Guards read counters from `state.json` (not from in-process memory), so a runner crash and restart doesn't reset the retry budget. **This is a load-bearing pattern — `node.contract.schema.json` should require a `retry_policy: {max, on: "status==FAILED"}` block on every node.**

### 4.5 **FSMs and Statecharts for AI Agent Orchestration — Zylos 2026**
- **Idea**: Extends Hossain to statecharts (hierarchical FSMs). The big insight: **separate process grounding (state transitions, progress tracking, lifecycle management) from sub-task solving (the actual work done within each state).** Process grounding is deterministic and inspectable — you can draw the diagram, enumerate all paths, reason about termination. Sub-task solving is where the LLM's non-determinism lives, safely contained within well-defined state boundaries. History pseudo-states inside composite states allow suspend/resume without losing the sub-state position.
- **Source**: <https://zylos.ai/research/2026-04-02-finite-state-machines-statecharts-ai-agent-orchestration>
- **Filesystem mapping**: The "composite state" is a sub-plan (a `loop.plan` referenced by path). The history pseudo-state is `state.json` snapshotting the last active sub-state at suspend time. Cite this for the rationale of *composable* `loop.plan` files.

### 4.6 **fsm_agent_fw — Ultra-Lightweight FSM Framework**
- **Idea**: Pure FSM with three transition patterns — **deterministic one-way** (workflows), **conditional** (LLM picks next from `fsm.get_next_states()`), **autonomous** (LLM free-navigates within FSM-defined phases). The FSM is the "map" (boundaries), the LLM is the "driver" (path). Prompt always displays "Current State" and "Available Transition Options" so the model can't drift.
- **Source**: <https://github.com/shuent/fsm_agent_fw>
- **Filesystem mapping**: Direct — the `loop.plan` is the FSM definition, the LLM call is the transition function, and `state.json` carries `current_state` and `available_transitions`. The `state_transition` tool is a special tool the LLM can call; the runner validates the call against the allowed transitions.

### 4.7 **fsm_llm — 2-Pass Architecture with JsonLogic Transitions**
- **Idea**: Two-pass per turn: Pass 1 extracts data and evaluates transitions (deterministic JsonLogic rules or LLM classification), Pass 2 generates the response *after* the transition (so the response always reflects the correct state). States with empty `response_instructions` skip Pass 2 — useful for intermediate agent states in tool-use loops where a second LLM call is not needed.
- **Source**: <https://github.com/NikolasMarkou/fsm_llm>
- **Filesystem mapping**: The two-pass split maps to the two-phase runner: (1) gate evaluation against `evidence/<node>/output.json` → transition to next state, (2) response generation. JsonLogic transitions are a great fit for filesystem-only because the rules are pure data: `evidence/<node>/transitions.json` is just `{when: "status == 'DONE'", goto: "next"}`.

### 4.8 **Anthropic Long-Running Agent Harness — Context Resets as State Transitions**
- **Idea**: For long-running agents, the harness uses an **initializer agent** (first session sets up `init.sh`, `claude-progress.txt`, initial git commit) and **coding agent** (every subsequent session makes incremental progress and leaves structured updates — git commit + progress file). **Context resets** (clearing the window, starting fresh) with a structured handoff carry state forward. The "different prompt for the first context window" pattern is itself a state transition. For long-running, the model is the bottleneck: 99.9th percentile session length passed 40 minutes in Jan 2026, up from 20 in late 2025.
- **Source**: <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- **Filesystem mapping**: The `runs/<run_id>/progress.json` is the Anthropic progress file; `init.sh` is `plans/<plan>/init.py`. A context reset = runner stops, persists `state.json`, exits. Next invocation reads `state.json` and resumes from the next ready node. **This is the pattern that makes `loop.plan` work across hours or days.**

### 4.9 **Anthropic Managed Agents — Decoupling Brain / Hands / Session**
- **Idea**: The harness lives *outside* the sandbox. The model (brain) calls the container (hands) via `execute(name, input) → string` — the container is cattle, not a pet. The **session** is a durable event log, not a state object. The brain queries the session with `getEvents()` to reconstruct context. Context management (transformations, compaction) is the harness's job; the session's job is just to be durable and sliceable. **Implication for `loop.plan`**: the "session" is the `runs/<run_id>/events.jsonl` file (append-only, never edited). The runner is the only writer. The LLM never touches the file directly; it sees a windowed view reconstructed by the runner.
- **Source**: <https://www.anthropic.com/engineering/managed-agents>
- **Filesystem mapping**: A `runs/<run_id>/events.jsonl` file with one event per line (state transitions, gate results, LLM calls, tool calls). The runner is the only writer. The LLM never touches the file directly; it sees a windowed view reconstructed by the runner.

---

## 5. Direct Mapping to `loop.plan` Schema Fields

This is the synthesis — each `loop.plan` field, with the source it lifts from.

| `loop.plan` / `node.contract` field | Source(s) | Purpose |
|---|---|---|
| `nodes[].id` | §1.1 Airflow, §1.4 Argo | Unique node identifier |
| `nodes[].kind` | §1.1 Airflow, §1.3 Dagster, §2.1 LangGraph | `"task"`, `"branch"`, `"map"`, `"reduce"`, `"judge"`, `"fsm"`, `"orchestrator_worker"`, `"handoff"`, `"delegate"`, `"group_chat"`, `"self_consistency"`, `"tree_of_thoughts"`, `"reflexion_loop"`, `"evaluator_optimizer"`, `"codeact"`, `"step_verifier"` |
| `nodes[].produces` (artifact path) | §1.5 Make | Filesystem artifact (with mtime-based cache key) |
| `nodes[].requires` (artifact paths) | §1.5 Make, §1.6 Bazel | Real artifact dependency, not habitual order |
| `nodes[].expand.input_ref` | §1.1 Airflow, §1.3 Dagster | Runtime fan-out cardinality |
| `nodes[].concurrency` | §1.2 Prefect, §1.4 Argo | Pluggable runner, with parallelism limit |
| `nodes[].status` enum | §4.3 UFO, §4.4 Hossain | `PENDING, READY, RUNNING, COMPLETED, FAILED, BLOCKED, ESCALATED` |
| `nodes[].gate` | §3.1 LLM-as-Judge, §3.2 Self-Consistency, §3.6 PRM, §3.7 CodeAct, §3.8 TDD | Evidence gate: `{kind, rubric_ref, threshold, model, aggregation}` |
| `nodes[].retry_policy` | §0.1 Graph Harness, §4.4 Hossain | `{max, on: "status==FAILED", escalation: "replan | escalate"}` |
| `nodes[].cache_key` | §1.6 Bazel | Skip re-run if cache hit (action graph key) |
| `nodes[].subgraph_ref` | §1.1 Airflow, §2.1 LangGraph | Path to another `loop.plan` (recursive DAG) |
| `nodes[].isolation.dir` | §2.7 Anthropic, §2.1 LangGraph | Per-subagent working dir; no context leak |
| `nodes[].sandbox` | §3.7 CodeAct | `{fs_root, allow_network, timeout}` for code-execution nodes |
| `plan.version` (immutable) | §0.1 Graph Harness | Once set, the plan cannot be mutated within a run |
| `plan.layers` (planning / execution / recovery) | §0.1 Graph Harness | Three independent concerns with narrow interfaces |
| `plan.escalation` | §0.1 Graph Harness, §1.4 Argo `depends` | `{local_retry, local_patch, replan, escalate}` ladder |
| `plan.parallelism_limit` | §1.4 Argo, §1.2 Prefect | Global cap on concurrent nodes |
| `state.status` (per run) | §4 all | Current FSM state |
| `state.history` (events.jsonl) | §4.9 Managed Agents | Append-only event log; only runner writes |
| `state.context` (Γ*) | §4.1 StateFlow | Accumulated context history for transition function |

---

## 6. Recommended Reading Order for `create-loop` Implementation

1. **§0.1 Graph Harness** (the design rationale for the three commitments)
2. **§0.2 System Scaling** (the six-component decomposition)
3. **§1.5 Make + §1.6 Bazel** (the "dep is an artifact" foundation)
4. **§2.1 LangGraph edge vocabulary** (the edge model — `add_edge`, `add_conditional_edges`, `Command`, `Send`)
5. **§4.3 UFO + §4.4 Hossain** (the state enum and guard pattern)
6. **§3.1 LLM-as-Judge + §3.7 CodeAct + §3.6 PRMs** (the three evidence-gate kinds, in increasing strength)
7. **§2.7 Anthropic orchestrator-worker** (the parallel-pattern model)
8. **§4.9 Managed Agents + §4.8 long-running harness** (the "survives hours/days" foundation)

Then for `branching_parallelism.md`, prioritize §2.1, §2.2, §2.3, §2.4, §2.7, §2.8.
For `evidence_gates.md`, prioritize §3.1, §3.2, §3.3, §3.4, §3.6, §3.7, §3.8.

---

## 7. One Document to Read Tonight

If only one piece can be read, read **§0.1 (Graph Harness, arXiv 2604.11378)** in full. It is the academic version of exactly what `create-loop` is building, and the references in its bibliography will pull you into the rest of this list organically. The escalation invariant (Proposition 6.4) and the three-layer separation (Planner / Runtime / Recovery) are directly importable into `loop_plan_spec.md`.
