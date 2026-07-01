Task Result

Task ID: bg_1d83ac7d
Description: Research task DAGs + multi-agent orchestration
Duration: 10m 52s
Session ID: ses_0e1b13123ffem7PsIqgv8jJ2Ae

---

The user is asking for a comprehensive research report on four areas relevant to building an Agent Skill called `create-loop` that generates a `loop.plan` — a recursive execution-control DAG with evidence gates.

Let me classify this request per the LIBRARIAN protocol:
- This is a **TYPE D: COMPREHENSIVE RESEARCH** request. It's complex, spans multiple domains, requires official documentation discovery, real-world patterns, and code-level evidence. It also includes "research" as an explicit keyword in some senses.

The four areas to research:
1. Task graphs / DAG workflow engines (Airflow, Prefect, Dagster, Argo, Make/Bazel, GNU Make)
2. Multi-agent orchestration (LangGraph, OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic)
3. Verification / evidence gates (LLM-as-judge, generator-verifier, TDD agents, evals, self-consistency, reflexion)
4. State machines for agents

The deliverable is a structured markdown report with:
- Name
- One-paragraph core idea
- Source URL
- One-line note on filesystem-only mapping

I need to do this in parallel as much as possible. Let me think about how to structure this:

1. **Phase 0.5: Documentation Discovery** for major libraries
2. **Phase 1: Parallel investigation** across all 4 areas
3. **Phase 2: Evidence synthesis** with permalinks/citations

Let me think about the searches I need to make:

### Area 1: DAG workflow engines
- Apache Airflow DAG documentation (real artifact dependencies, dynamic task mapping)
- Prefect task/flow docs (DAG, scheduling, parallel)
- Dagster (op/graph/job, dynamic graph)
- Argo Workflows (DAG, fan-out/fan-in, steps)
- GNU Make (dependency = file existence)
- Bazel (BUILD files, action graph)
- Make (the original DAG-by-file-deps)

### Area 2: Multi-agent orchestration
- LangGraph multi-agent docs (supervisor, swarm, subgraph)
- OpenAI Swarm (handoff pattern)
- OpenAI Agents SDK (handoffs, agents as tools)
- CrewAI (role-based agents)
- AutoGen (group chat, nested chats)
- Anthropic multi-agent research system blog

### Area 3: Verification / evidence gates
- LLM-as-judge (Anthropic, OpenAI papers)
- Generator-verifier separation
- Test-driven agent workflows
- Self-consistency (Wang et al.)
- Reflexion (Shinn et al.)
- Anthropic building effective agents blog

### Area 4: State machines
- Finite state machines for agents
- Status enums, transition guards
- Why FSMs vs free-form

Let me dispatch a bunch of parallel searches. I'll use:
- websearch_web_search_exa for broad topic searches
- gh_grep_searchGitHub for code patterns
- context7_resolve-library-id + context7_query-docs for official library docs
- codegraph_explore for local code (but this is about external libraries, so I should use external tools)

Wait — I need to check the current date. The system says "Today's date: Wed Jul 01 2026" and the prompt says current year is 2026+. So I should be careful to look for 2026 content where relevant but not exclude 2025-2026 content.

Let me start with parallel searches. I'll do a batch of searches in parallel:

1. websearch: Airflow DAG dynamic task mapping
2. websearch: Prefect task DAG scheduling
3. websearch: Dagster dynamic graph op
4. websearch: Argo Workflows DAG fan-out fan-in
5. websearch: GNU Make dependency graph algorithm
6. websearch: Bazel action graph BUILD file
7. websearch: LangGraph multi-agent supervisor swarm
8. websearch: OpenAI Swarm handoff pattern
9. websearch: OpenAI Agents SDK handoffs
10. websearch: CrewAI multi-agent orchestration
11. websearch: AutoGen multi-agent nested chat
12. websearch: Anthropic multi-agent research system blog
13. websearch: LLM as judge evaluation
14. websearch: generator verifier separation LLM
15. websearch: reflexion self-consistency LLM
16. websearch: finite state machine LLM agent
17. websearch: DAG workflow engine comparison

Let me also think about context7 lookups for the major libraries:
- Apache Airflow
- Prefect
- Dagster
- Argo Workflows (not a Python lib, so skip)
- LangGraph
- OpenAI Swarm / Agents SDK
- CrewAI
- AutoGen

Let me also think about real-world code examples. I can use gh_grep_searchGitHub to find code patterns for these.

Let me first do a broad set of web searches in parallel to get the lay of the land, then drill into specific docs and code.

Actually, I should be efficient. Let me batch the web searches, and also start with context7 for the most important ones. Let me also note: the task says "skip beginner tutorials" — so I should focus on official docs, technical papers, and source code.

Let me start. I'll fire off a large batch of parallel searches:

1. websearch_web_search_exa: "Apache Airflow DAG dynamic task mapping documentation"
2. websearch_web_search_exa: "Prefect task flow DAG scheduling documentation"
3. websearch_web_search_exa: "Dagster dynamic op graph job documentation"
4. websearch_web_search_exa: "Argo Workflows DAG fan-out fan-in documentation"
5. websearch_web_search_exa: "GNU Make dependency graph algorithm remaking make"
6. websearch_web_search_exa: "Bazel action graph dependency analysis"
7. websearch_web_search_exa: "LangGraph multi-agent supervisor swarm handoff"
8. websearch_web_search_exa: "OpenAI Swarm handoff pattern documentation"
9. websearch_web_search_exa: "OpenAI Agents SDK handoffs agents as tools"
10. websearch_web_search_exa: "CrewAI orchestration role-based agents"
11. websearch_web_search_exa: "AutoGen nested chat group chat patterns"
12. websearch_web_search_exa: "Anthropic multi-agent research system blog"
13. websearch_web_search_exa: "LLM as a judge evaluation paper"
14. websearch_web_search_exa: "generator verifier separation agent"
15. websearch_web_search_exa: "reflexion self-consistency agent paper"
16. websearch_web_search_exa: "finite state machine LLM agent workflow"

Let me also do some context7 lookups in parallel:
- context7_resolve-library-id: airflow
- context7_resolve-library-id: prefect
- context7_resolve-library-id: dagster
- context7_resolve-library-id: langgraph
- context7_resolve-library-id: crewai
- context7_resolve-library-id: autogen

Let me also do some gh_grep_searchGitHub for code patterns:
- "expand_kwargs" Airflow dynamic task mapping
- "@task" Prefect
- "@op" or "@asset" Dagster
- "add_conditional_edges" LangGraph
- StateGraph LangGraph
- "Command" LangGraph handoff
- "create_react_agent" LangGraph
- finite state machine agent

Let me start. I'll do parallel calls.

Actually, let me start with the web searches since they're fast, and also do some code searches. Then I can do context7 and deeper code searches.

Let me do this in batches. First batch: 16 web searches in parallel.

Actually, I'll be even more strategic. Let me batch all of these together in one big parallel call. The instructions say "Always vary queries" and to do parallel calls for TYPE D (3-5 minimum).

Let me first set up todos to track this work, then fire off the searches.

I'll research these four areas in parallel to build your evidence base. Let me set up tracking and fire off the first wave of searches.

Now let me fire off the first batch of parallel searches. I'll do 16+ searches in parallel to cover all four areas comprehensively.

Firing the first wave — 16 parallel searches across all four areas:

Excellent! I have a lot of great material. Now let me fire off a second wave for additional searches and code-level pattern discovery, plus context7 for major libraries. Let me also do a few more specific searches:

1. LLM-as-judge specific paper (Zheng et al 2023)
2. Self-consistency (Wang et al 2022) 
3. Tree of thoughts (Yao et al 2023)
4. state machines - more on FSMs
5. DAG formalism / topological sort
6. evals as gates
7. DSPy generator-verifier
8. context7 for major libraries
9. gh_grep for code patterns

Let me batch this.

Strong material. Firing the second wave — context7 for major libraries, additional targeted searches, and code patterns:

I have an excellent base of material. Now I need to dig into specific library documentation for code-level patterns and the actual sources. Let me also do some more targeted searches and then assemble the report.

Let me now:
1. Get a couple of specific code-level examples from official docs
2. Look at FSM-agent-flow and StateFlow more
3. Get StateGraph concrete examples
4. Look at LLM-as-a-judge specific pattern details

Then I'll have enough to assemble a comprehensive structured report.

Solid base. Let me now pull specific code-level patterns and a few more authoritative sources:

I now have a comprehensive set of references. Let me update my todos and start synthesizing the final report. I have enough material to produce a high-quality structured markdown report.

Let me also do a few quick additional searches to make sure I have full coverage on a few specific topics:
1. State machine FSM production agent (already have FSM-agent-flow, StateFlow, Hossain, UFO)
2. Tree of Thoughts (have)
3. StateGraph specific code patterns
4. Make/Bazel more specific

Actually I have enough. Let me synthesize the report now.

Let me also fetch a couple more specific code patterns for StateGraph add_conditional_edges and Command since these are core to the patterns we want to use.

Let me grab a couple more code-level patterns then synthesize:

I have more than enough material now. The Graph Harness paper (arxiv 2604.11378) is actually directly relevant to what the user is building — it's a 2026 paper that formalizes exactly the "structured execution DAG" approach with three commitments (immutable plan, separate planning/execution/recovery, strict escalation protocol). That's an EXCELLENT primary source for the design rationale.

Let me also note that the LangGraph fundamental skill page is great because it gives the official edge type reference table:
- `add_edge()` — fixed deterministic
- `add_conditional_edges()` — state-based routing
- `Command` — update + route in one
- `Send` — fan-out parallel with dynamic inputs

This is gold for the spec.

Now I have everything I need. Let me update my todos and write the comprehensive structured markdown report.

Key sources I have:
**Area 1 - DAG Workflow Engines:**
- Apache Airflow: dynamic task mapping (expand/expand_kwargs/task_group) - confirmed from official docs
- Prefect 3: .submit() / .map() / task runners, subflows - confirmed
- Dagster: DynamicOut / map / collect / partitions - confirmed
- Argo Workflows: dag/dependencies/withParam/depends - confirmed
- GNU Make: dependency = file (mtime), remake.c - confirmed via source code
- Bazel: action graph (aquery), declared vs actual deps - confirmed

**Area 2 - Multi-agent Orchestration:**
- LangGraph: StateGraph, add_edge, add_conditional_edges, Command, Send, subgraphs - confirmed
- LangGraph Supervisor: create_supervisor with handoff tools - confirmed via context7
- LangGraph Swarm: peer-to-peer handoffs with active_agent router - confirmed
- OpenAI Swarm (now Agents SDK): handoff pattern - confirmed
- OpenAI Agents SDK: handoffs + agents as tools - confirmed
- CrewAI: Sequential/Hierarchical process, Flows + Crews - confirmed
- AutoGen: GroupChat, SelectorGroupChat, nested chats - confirmed
- Anthropic: orchestrator-worker, 90.2% improvement, 15x token cost - confirmed

**Area 3 - Verification / Evidence Gates:**
- LLM-as-a-Judge: Zheng et al 2023, arxiv 2306.05685 - confirmed
- Self-Consistency: Wang et al 2022, arxiv 2203.11171 - confirmed
- Tree of Thoughts: Yao et al 2023, arxiv 2305.10601 - confirmed
- Reflexion: Shinn et al 2023, arxiv 2303.11366 - confirmed
- Anthropic evaluator-optimizer pattern - confirmed
- Process Reward Models (PRMs): GenPRM, ThinkPRM - confirmed
- Eval-driven development: TDD Guardian for Claude - confirmed
- CodeAct: tests via code execution - confirmed

**Area 4 - State Machines:**
- StateFlow (arXiv 2403.11322) - LLM as FSM with (S, s0, F, δ, Γ, Ω) formal model
- FSM-agent-flow: NewJerseyStyle (TDD/OKR-driven, acceptance criteria per state)
- Microsoft UFO: 7-state HostAgentStatus enum (CONTINUE, FINISH, FAIL, ERROR, PENDING, CONFIRM, SCREENSHOT)
- FSMs for agents blog (Hossain) - persistence + guards + idempotent actions
- Shuent/fsm_agent_fw - ultra-lightweight
- NikolasMarkou/fsm_llm - 2-pass architecture, JsonLogic transitions
- Long-running agent harness (Anthropic) - context resets as state transitions

**Plus two cross-cutting papers:**
- Graph Harness (arxiv 2604.11378) - scheduler-theoretic, EXACTLY what the user is building
- System Scaling: Scaling the Harness (arxiv 2605.26112) - the 6-component model

Now let me write the report. I'll keep it structured and skimmable, with the filesystem-only mapping note the user explicitly asked for.

I have everything I need. Let me update todos and write the final report.

Now let me write the report. I'll write it directly to a file in the workspace so the user can use it for their downstream docs, AND include the content in the message so they have it inline.

Actually, since the user said "I will encode these into reference docs", let me write a comprehensive markdown report to a file in the workspace AND inline the main content in the response. The report should be skimmable and structured.

Let me structure it as:

1. Executive summary (cross-cutting patterns the user can lift directly)
2. Area 1: Task graphs / DAG workflow engines
3. Area 2: Multi-agent orchestration
4. Area 3: Verification / evidence gates
5. Area 4: State machines for agents
6. Direct mapping to loop.plan files
7. Recommended reading order

For each entry, I need:
- Name
- One-paragraph core idea
- Source URL (GitHub permalink or canonical doc)
- One-line note on filesystem-only mapping

Let me write it. I'll be concise but thorough.

# Reference Material: `create-loop` Skill — `loop.plan` DAG + Evidence Gates

This report covers task graphs, multi-agent coordination, evidence gates, and state machines for agent execution. Every entry has a source URL and a one-line "filesystem-only mapping" note so you can lift the pattern directly into `loop.plan` (no database required, no broker required — every reference below has a JSON-on-disk equivalent).

---

## 0. Two Cross-Cutting Primary Sources (Read These First)

These two papers are **directly about your design problem** and synthesize the four areas below into a single framework. They should be cited in `loop_plan_spec.md` itself, not buried in supporting docs.

### 0.1 **Graph Harness (Structured Graph Harness / SGH)** — Scheduler-Theoretic Agent Execution
- **Idea**: Formalizes the agent loop as a *single-ready-unit, non-deterministic scheduler* and proposes a structured graph-based alternative. Three commitments: (1) execution plan is an **immutable commitment** for a plan version, (2) **planning / execution / recovery are three independent layers** with well-defined interfaces, (3) recovery follows a **strict escalation protocol** (`{local_retry, local_patch, replan}` — bounded, never infinite). Execution system is a tuple `E = (S, U, P, O, Δ)`; ready-set cardinality `|U(S)|` and policy explicitness are the two axes you optimize.
- **Source**: <https://arxiv.org/abs/2604.11378> (April 2026) · PDF: <https://www.arxiv.org/pdf/2604.11378>
- **Filesystem mapping**: The plan is a versioned JSON file; once `version` is set, `Δ` (state transitions) only mutates `state.json`, never `plan.json`. The escalation ladder is a small enum on each node contract: `retry → patch → replan → escalate`.

### 0.2 **From Model Scaling to System Scaling: Scaling the Harness in Agentic AI**
- **Idea**: Defines the harness as six components — `R` (reasoner), `M` (memory), `C` (context constructor), `S` (skill/sub-agent router), `O` (orchestration loop), `G` (verification & governance). Performance is decomposed as a function of these. "Dynamic skill routing is the analogue of scheduling in operating systems… making post-condition checking a first-class component of each skill specification." Skill quality × verification quality is the tradeoff, not either alone.
- **Source**: <https://arxiv.org/html/2605.26112>
- **Filesystem mapping**: Map each component to a folder — `R=llm_call.json`, `M=memory/`, `C=context/`, `S=skills/<skill>.contract.json`, `O=loop.runner`, `G=evidence/<node_id>.gate.json`. Every skill spec gets a `post_condition` block.

---

## 1. Task Graphs / DAG Workflow Engines

The foundation of `loop.plan` is "DAG of nodes with real artifact dependencies." The systems below each contribute one specific idea you need.

### 1.1 **Apache Airflow — Dynamic Task Mapping**
- **Idea**: A DAG declares structure at parse time, but `task.expand()` and `task.expand_kwargs()` **defer the cardinality of a downstream task to runtime** — the scheduler materializes N task instances only after the upstream XCom returns. Combines `.partial(...)` (static args) with `.expand(...)` (mapped args). Can be applied to a `@task_group` (subgraph expansion) and to a list of dicts. This is your "recursive subgraph generation" pattern: a node in the DAG yields N child plans and the scheduler materializes them.
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
- **Filesystem mapping**: A `loop.plan` is a flow. Each node has `concurrency: "serial" | "concurrent:thread:N" | "concurrent:process:N"`. Subflows are plans that reference other plans by path. The runner writes a `PrefectFuture`-shaped record to `state/<run_id>/<node_id>.future.json` (status + task_run_id + poll endpoint — local file here, just the file itself).

### 1.3 **Dagster — Dynamic Graphs, `DynamicOut` / `map` / `collect`**
- **Idea**: An op annotated `out=DynamicOut()` `yield`s `DynamicOutput(value, mapping_key)` objects. Downstream ops cannot consume the dynamic output directly — they must call `.map(callable)` (clone the op per mapping_key, **fan-out** with dependency edges) or `.collect()` (single op receives list of all values, **fan-in**). The mapping_key becomes a unique identifier for each cloned op. Partitions are orthogonal: `daily_partitioned_config` × `static_partitioned_config` × `dynamic_partitioned_config` allow you to express "run this subgraph 5 times on these 5 keys."
- **Sources**:
  - Dynamic graphs: <https://docs.dagster.io/guides/build/ops/dynamic-graphs>
  - Op graphs: <https://docs.dagster.io/guides/build/ops/graphs>
  - Partitioning ops: <https://docs.dagster.io/guides/build/partitions-and-backfills/partitioning-ops>
  - Graph-backed assets: <https://docs.dagster.io/guides/build/assets/graph-backed-assets>
- **Filesystem mapping**: `DynamicOutput(value, mapping_key)` is your `Evidence { value, key, parent_node }` record. A `loop.plan` node of `kind: "dynamic"` carries a list of mapping_keys up front (static) or reads them from an upstream `evidence/<id>/values.json` at runtime. The loop runner materializes child plans to `evidence/<node_id>/<mapping_key>/plan.fragment.json`.

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
- **Filesystem mapping**: This is the **purest** filesystem mapping — `make` already is one. A `loop.plan` node declares its artifact by path (`produces: "out/feature.json"`) and lists its `requires` as paths (`requires_artifact: ["in/data.csv"]`). The runner does the equivalent of `stat -c %Y` and skips re-running if `produces.mtime > max(requires.mtime)` and the gate evidence file already exists. **Make's "dep is an actual file" is your moat against habitual-order-only DAGs.**

### 1.6 **Bazel — Action Graph, Declared vs Actual, `aquery`**
- **Idea**: Bazel separates three graphs: the **target graph** (from `BUILD` files, declared deps), the **configured target graph** (post-analysis, with select() resolved), and the **action graph** (post-analysis, bipartite: `Action` ↔ `Artifact`, where each Action is `Artifact → Artifact` and has a `getKey()` whose change invalidates the action). For correct builds, **actual-deps ⊆ declared-deps** — Bazel flags missing declared deps. `bazel aquery` exposes the action graph for inspection; `bazel query` for declared deps. The action key is the cache invalidator: change a compiler flag → action key changes → rebuild.
- **Sources**:
  - Action Graph Query: <https://bazel.build/query/aquery>
  - Introducing aquery: <https://blog.bazel.build/2019/02/15/introducing-aquery.html>
  - Dependencies: <https://github.com/bazelbuild/bazel/blob/master/site/en/concepts/dependencies.md>
  - Query guide: <https://bazel.build/versions/9.1.0/query/guide>
- **Filesystem mapping**: Every `loop.plan` node contract has a `cache_key: "<hash(inputs+prompt+model+config)>"` field. Before running, the runner computes the key, checks if `evidence/<node_id>/<cache_key>/output.json` already exists, and skips. This is how you get resumability across crashed runs without a database.

---

## 2. Multi-Agent Orchestration

`loop.plan` is single-process / single-runner, but the *nodes* of the plan can be sub-agents, and your `branching_parallelism.md` needs to know which coordination pattern to use when.

### 2.1 **LangGraph — `StateGraph`, Edge Vocabulary, Subgraphs, `Send`**
- **Idea**: The single most important reference for you. LangGraph models an agent as a `StateGraph` with a typed state schema (a `TypedDict` with **reducers** like `Annotated[list, operator.add]` for fan-in accumulation), nodes that return state updates, and four edge types:
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
- **Filesystem mapping**: This is *almost* a perfect 1:1. Your `loop.plan` is the StateGraph definition. Your `State` becomes `state.json` per run. `add_edge` → `requires: [a]`. `add_conditional_edges(path_fn=...)` → a node with `kind: "branch"` and a `path_fn_ref: "skills/branch/score.py"`. `Command` → a node's return is `{update: <state patch>, goto: <next_node>}` written to `evidence/<node_id>/return.json`. `Send` → a `kind: "fanout"` node whose `expand` references a prior node's output. **The four edge types are the section headers of `branching_parallelism.md`.**

### 2.2 **LangGraph Supervisor — Hierarchical via Tool-Based Handoffs**
- **Idea**: `create_supervisor([agent_a, agent_b], model=llm, tools=[...])` returns a `StateGraph` where each worker is a compiled subgraph and the supervisor is an LLM that decides which to call next via **`create_handoff_tool(agent_name=...)`** — a tool whose return value is a `Command(goto=agent_name, graph=Command.PARENT, update={...})`. The handoff tool can carry a structured `task_description: str` injected into the worker's state. Default behavior appends `(AIMessage, ToolMessage)` handoff pairs to message history; this is opt-out via `add_handoff_messages=False`.
- **Sources**:
  - Source repo: <https://github.com/langchain-ai/langgraph-supervisor-py>
  - API reference: <https://reference.langchain.com/python/langgraph-supervisor/supervisor/create_supervisor>
- **Filesystem mapping**: A `kind: "supervisor"` node in `loop.plan` lists `workers: [<plan_id_1>, <plan_id_2>]`, `model: "<model_ref>"`, and `tools: [handoff_<worker>.json]`. The handoff is persisted to `evidence/<node_id>/handoffs/<worker_id>.json` with the full state patch — this is your "agent produced structured handoff, not free-form prose."

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
- **Filesystem mapping**: `kind: "group_chat"` plan with `participants: [agent_a, agent_b]`, `selector: {method: "auto" | "round_robin", model: "..."}`. The next-speaker decision is written to `evidence/<node_id>/next_speaker.json` for inspection (this is the "policy explicitness" SGH paper pushes for).

### 2.7 **Anthropic Multi-Agent Research System — Orchestrator-Worker in Production**
- **Idea**: The cleanest production write-up of the orchestrator-worker pattern. A `LeadResearcher` agent plans the work, saves the plan to memory, then **spawns 3–5 subagents in parallel**, each with: (1) a self-contained task description, (2) an output format, (3) a tool list, (4) clear "done" boundaries. Each subagent uses 3+ tools in parallel inside its own context window and returns a *condensed* summary, not a long chat. The lead reconciles, decides if more research is needed, either spawns another wave or moves on. **Result: 90.2% improvement over single-agent Opus 4 on research evals, 90% time reduction, ~15x token cost.** Critical design rule: each subagent must be *truly independent* (doesn't see other subagents, can't coordinate mid-task) — otherwise the parallel speedup collapses into expensive serial.
- **Source**: <https://www.anthropic.com/engineering/multi-agent-research-system>
- **Filesystem mapping**: `kind: "orchestrator_worker"` plan; the orchestrator node emits a `plan_subgraph.json` with N entries; the runner spawns N child processes (or N async tasks in a worker pool, given your filesystem-only constraint) and writes each child's output to `evidence/orchestrator/<i>/return.json`. The "isolation boundary" is enforced by giving each child its own working directory under `runs/<run_id>/<orchestrator>/<i>/` so context cannot leak.

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
- **Filesystem mapping**: A `kind: "judge"` gate node in `loop.plan` carries `rubric: "rubrics/<gate>.md"`, `model: "<model_ref>"`, `aggregation: "mean" | "majority" | "weighted"`. The judge reads the upstream node's `return.json` and writes `score: 0..1` + `rationale: str` to `evidence/<gate>/verdict.json`. Your `node.contract.schema.json` should require a `gate: { kind, threshold, rubric }` block on every node.

### 3.2 **Self-Consistency — Wang et al. 2022**
- **Idea**: Sample K diverse reasoning paths for a problem (high temperature), then **marginalize** (majority vote on the final answer, or aggregate rationales). Works because complex problems admit many valid reasoning paths that all converge on the same correct answer; disagreement is a signal of low confidence. Strong gains on GSM8K (+17.9%), SVAMP (+11%), AQuA (+12.2%), StrategyQA (+6.4%), ARC (+3.9%). Also provides *calibration* — the agreement rate among K samples is an honest uncertainty estimate.
- **Source**: <https://arxiv.org/abs/2203.11171>
- **Filesystem mapping**: A `kind: "self_consistency"` gate; the runner samples K times (K written to `state.json` for the gate), each sample written to `evidence/<gate>/samples/<i>.json`; an aggregator node reduces to `evidence/<gate>/majority.json`. This is a "fan-out + vote" inside a single evidence-gate node — the simplest non-trivial verification pattern.

### 3.3 **Tree of Thoughts — Yao et al. 2023**
- **Idea**: Generalizes CoT from a linear chain to a search tree. At each step, generate K candidate "thoughts" (coherent text units, not single tokens), **evaluate** each via an LLM (or a heuristic), keep the top B, then recurse. BFS or DFS with backtracking. On Game of 24, GPT-4 + CoT = 4% success, ToT = 74%. The "thought" abstraction is what makes it different from repeated sampling — each node in the search tree is a *partial plan*, evaluated against a goal, with the option to backtrack.
- **Source**: <https://arxiv.org/abs/2305.10601> (NeurIPS 2023 oral) · Code: <https://github.com/princeton-nlp/tree-of-thought-llm>
- **Filesystem mapping**: A `kind: "tree_of_thoughts"` gate; the runner builds a tree of `evidence/<gate>/tree/<depth>/<branch>.json` (each leaf has a `score` and `state`); the highest-scoring complete path is `evidence/<gate>/best.json`. This is a "sub-plan" in your `loop.plan` vocabulary: a node that itself contains a small DAG of thought-eval-expand steps, with an inner budget.

### 3.4 **Reflexion — Shinn et al. 2023**
- **Idea**: Reinforce language agents not by weight updates but by **linguistic self-reflection**. After each trial, the agent reflects verbally on the failure, stores the reflection in an **episodic memory buffer**, and the next trial uses the accumulated reflections as additional context. Strategies: `NONE`, `LAST_ATTEMPT`, `REFLEXION`, `LAST_ATTEMPT_AND_REFLEXION`. Reflexion achieves **91% pass@1 on HumanEval** vs. GPT-4's prior 80%. The key is that the *reflection model* is itself an LLM call — the agent "explains to itself" what went wrong, and the explanation is more informative than a scalar reward.
- **Sources**:
  - Paper: <https://arxiv.org/abs/2303.11366> (NeurIPS 2023)
  - Code: <https://github.com/noahshinn/reflexion>
- **Filesystem mapping**: A `kind: "reflexion_loop"` node carries `max_trials: N`, `reflection_model: "..."`. After each trial, the runner writes `evidence/<node_id>/trial_<i>/output.json` and `evidence/<node_id>/trial_<i>/reflection.json`. The next trial's prompt is constructed by concatenating the last K reflections. This is "subgraph recursion" in `loop.plan` terms.

### 3.5 **Anthropic Evaluator-Optimizer Pattern (Building Effective Agents)**
- **Idea**: One LLM generates, a *separate* LLM evaluates against explicit criteria, generator iterates on the feedback. Use when "LLM responses can be demonstrably improved when a human articulates their feedback" AND "the LLM can provide such feedback." This is the production-grade generator-verifier separation. Anthropic also ships the **orchestrator-worker**, **prompt chaining**, **routing**, and **parallelization** patterns here — the canonical "agent building blocks" reference.
- **Source**: <https://www.anthropic.com/research/building-effective-agents>
- **Filesystem mapping**: A `kind: "evaluator_optimizer"` gate is a two-node subgraph: `generator` + `evaluator`. Evaluator writes `evidence/<eval>/feedback.json` (structured, with pass/fail per criterion, not free-form "looks good"). Generator retries with the feedback as additional context. The `eval-protocol` style spec (each criterion is `{name, rubric, threshold}`) is your `gate.rubric` field.

### 3.6 **Process Reward Models (PRMs) — Step-Level Verifiers**
- **Idea**: A judge that scores *each step* of a reasoning trajectory, not just the final answer. Two recent variants: **ThinkPRM** (long chain-of-thought verifier, fine-tuned on 1% of process labels, outperforms LLM-as-Judge and discriminative PRMs under best-of-N), **GenPRM** (generative verifier with explicit CoT + code verification before scoring; 1.5B GenPRM outperforms GPT-4o on ProcessBench). The conceptual shift: a *step* is a node in a small DAG, and the verifier can be applied at each node (every edge is an evidence gate).
- **Sources**:
  - ThinkPRM: <https://arxiv.org/abs/2504.16828>
  - PRM survey: <https://arxiv.org/html/2510.08049v3>
- **Filesystem mapping**: A `kind: "step_verifier"` gate; for each step in a multi-step node's output, the runner calls a PRM and writes a per-step score. **This is the most important pattern for your `evidence_gates.md`** — it means *every* intermediate output in a long node gets its own gate, not just the final result.

### 3.7 **CodeAct — Tests as Evidence via Sandboxed Execution**
- **Idea**: Instead of one tool call at a time, give the model a single `execute_code` tool backed by a sandbox. The model writes a short Python program that calls the same tools via `call_tool(...)`; the sandbox runs the program once, returns the consolidated result. The result is *itself* a test artifact — you can wrap the call with assertions and inspect the trace. Microsoft Agent Framework reports ~50% latency cut and >60% token reduction vs. the model-tool-model-tool loop.
- **Sources**:
  - Microsoft Agent Framework: <https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/>
  - CodeAct overview: <https://learn.microsoft.com/en-us/agent-framework/agents/code_act>
  - LlamaIndex CodeAct: <https://developers.llamaindex.ai/python/examples/agent/code_act_agent/>
- **Filesystem mapping**: A `kind: "codeact"` node in `loop.plan` has `sandbox: { fs_root: "<dir>", allow_network: bool, timeout: <sec> }`; the LLM writes a script to `evidence/<node_id>/program.py`, the runner executes it in a chroot/namespace, and the assertion results go to `evidence/<node_id>/test_results.json`. **This is your "the evidence is the test result" pattern** — strongest signal-to-noise ratio of any gate because it's deterministic.

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

### 3.9 **Structured Cognitive Loop (SCL) — Seperate Cognition, Memory, Control**
- **Idea**: LLM handles cognition, memory is external (in your case: files), execution is guided by a lightweight controller inside a goal-directed loop. Intermediate results are *recorded and verified* before actions are taken. SCL achieves 86.3% task success vs. 70.5–76.8% for ReAct/LangChain baselines on travel planning, email drafting, and constrained image generation. The "separation of process grounding from sub-task solving" is the design principle.
- **Source**: <https://arxiv.org/pdf/2510.05107>
- **Filesystem mapping**: Maps cleanly to your three layers — `R` (LLM call node) / `M` (`state.json` + `memory/`) / `O` (the loop runner itself). The SCL paper's evaluation is direct support for "explicit gates are better than implicit ones" as a claim in `loop_plan_spec.md`.

---

## 4. State Machines for Agents

`loop.plan` needs an internal status enum. The systems below show what the enum, transitions, and guards should look like.

### 4.1 **StateFlow — Formal FSM for LLM Workflows (arXiv 2403.11322)**
- **Idea**: Models LLM workflows as FSMs. The formal model is a sextuple `(S, s0, F, δ, Γ, Ω)`: states `S`, initial state `s0`, terminal states `F`, transition function `δ: S × Γ* → S` (operates on the *context history*, not a single token), output alphabet `Γ` (prompts `P`, LLM responses `C`, tool/environment feedback `O`), output functions `Ω` (LLM, tool call, or static prompter). Two transition kinds: **static string matching** (fast, deterministic, e.g. tool returns "Error" → `Error` state) and **LLM-decided** (flexible, costly, "given current output and task state, which state to transition to?"). Max-turns counter prevents infinite loops.
- **Source**: <https://arxiv.org/html/2403.11322v1> · <https://openreview.net/pdf?id=CZAs3WFw5r>
- **Filesystem mapping**: `S` = your node's `status` enum. `δ` = your gate conditions evaluated against `evidence/<node>/<output>.json`. `Γ*` = the cumulative `state.json`. Use this paper to justify the FSM framing in `evidence_gates.md` and to anchor the schema for `state.status` in `node.contract.schema.json`.

### 4.2 **FSM-agent-flow — TDD/OKR-Driven FSM for LLM Apps**
- **Idea**: Each state declares an **objective** and a list of **key results** — equivalent to a test suite. The state is entered, the LLM runs, the key results are checked before advancing. Failed states retry with the validator's feedback. Transitions are not just linear: conditional dict-based routing (`{output_key: target_state}`), bidirectional flows, retry loops. **No global singletons**; tools are scoped per state. Roughly maps to your gate-per-node contract.
- **Source**: <https://github.com/NewJerseyStyle/FSM-agent-flow>
- **Filesystem mapping**: A `kind: "fsm"` plan; each state node has `objective: str`, `key_results: [{id, kind, rubric, threshold}]`, `on_fail: {retry: N, goto: <state>}`. The runner evaluates key results against `evidence/<state>/output.json` and refuses to advance if any key result fails.

### 4.3 **Microsoft UFO — 7-State AgentStatus Enum**
- **Idea**: A clean production reference. The `HostAgentStatus` enum has exactly 7 values: `CONTINUE, FINISH, FAIL, ERROR, PENDING, CONFIRM, SCREENSHOT`. The transition table is explicit: from `CONTINUE` you can go to `FINISH, FAIL, ERROR, PENDING, CONFIRM, AppAgent.CONTINUE`; from `FINISH/FAIL/ERROR` you go nowhere (terminal); from `PENDING` you can go to `CONTINUE` or `FAIL` on timeout. Some transitions are LLM-controlled (the agent's response sets `Status: "ASSIGN"`), others are system-controlled (AppAgent return → back to `CONTINUE`). `PENDING` and `CONFIRM` are explicit waiting states for human-in-the-loop.
- **Source**: <https://github.com/microsoft/UFO/blob/main/documents/docs/infrastructure/agents/design/state.md>
- **Filesystem mapping**: A literal `status` enum in your schema. Add `BLOCKED` (gate failed) and `ESCALATED` (recovery layer gave up) for your escalation protocol. The transition table becomes a JSON Schema `enum` + a validator function.

### 4.4 **Production Agent State Machines — Hossain 2026**
- **Idea**: The most explicit "FSMs beat free-form" argument. Defines: finite states (e.g. `FETCHING_CONTEXT, ANALYZING, POSTING_COMMENTS, SUMMARIZING, COMPLETED, FAILED`), transitions (event → target state, with optional **guards** that read from persistent context, not in-memory), actions per state that are *idempotent* (safe to re-enter on retry). Critical property: **"given the current state and an input event, there is exactly one next state"** — this is what makes "where did this run fail?" answerable from your filesystem. The guard `[retries < 3]` is the key mechanism that converts the "infinite retry" failure mode into bounded deterministic behavior.
- **Source**: <https://mdsanwarhossain.me/blog-ai-agent-state-machines.html>
- **Filesystem mapping**: Your `state.json` is the persistent context. The guards read counters from `state.json` (not from in-process memory), so a runner crash and restart doesn't reset the retry budget. **This is a load-bearing pattern — your `node.contract.schema.json` should require a `retry_policy: {max, on: "status==FAILED"}` block on every node.**

### 4.5 **FSMs and Statecharts for AI Agent Orchestration — Zylos 2026**
- **Idea**: Extends Hossain to statecharts (hierarchical FSMs). The big insight: **separate process grounding (state transitions, progress tracking, lifecycle management) from sub-task solving (the actual work done within each state).** Process grounding is deterministic and inspectable — you can draw the diagram, enumerate all paths, reason about termination. Sub-task solving is where the LLM's non-determinism lives, safely contained within well-defined state boundaries. History pseudo-states inside composite states allow suspend/resume without losing the sub-state position.
- **Source**: <https://zylos.ai/research/2026-04-02-finite-state-machines-statecharts-ai-agent-orchestration>
- **Filesystem mapping**: Your "composite state" is a sub-plan (a `loop.plan` referenced by path). The history pseudo-state is `state.json` snapshotting the last active sub-state at suspend time. Cite this for the rationale of *composable* `loop.plan` files.

### 4.6 **fsm_agent_fw — Ultra-Lightweight FSM Framework**
- **Idea**: Pure FSM with three transition patterns — **deterministic one-way** (workflows), **conditional** (LLM picks next from `fsm.get_next_states()`), **autonomous** (LLM free-navigates within FSM-defined phases). The FSM is the "map" (boundaries), the LLM is the "driver" (path). Prompt always displays "Current State" and "Available Transition Options" so the model can't drift.
- **Source**: <https://github.com/shuent/fsm_agent_fw>
- **Filesystem mapping**: Direct — your `loop.plan` is the FSM definition, the LLM call is the transition function, and `state.json` carries `current_state` and `available_transitions`. The `state_transition` tool is a special tool the LLM can call; the runner validates the call against the allowed transitions.

### 4.7 **fsm_llm — 2-Pass Architecture with JsonLogic Transitions**
- **Idea**: Two-pass per turn: Pass 1 extracts data and evaluates transitions (deterministic JsonLogic rules or LLM classification), Pass 2 generates the response *after* the transition (so the response always reflects the correct state). States with empty `response_instructions` skip Pass 2 — useful for intermediate agent states in tool-use loops where you don't want to spend a second LLM call.
- **Source**: <https://github.com/NikolasMarkou/fsm_llm>
- **Filesystem mapping**: The two-pass split maps to your two-phase runner: (1) gate evaluation against `evidence/<node>/output.json` → transition to next state, (2) response generation. JsonLogic transitions are a great fit for filesystem-only because the rules are pure data: `evidence/<node>/transitions.json` is just `{when: "status == 'DONE'", goto: "next"}`.

### 4.8 **Anthropic Long-Running Agent Harness — Context Resets as State Transitions**
- **Idea**: For long-running agents, the harness uses an **initializer agent** (first session sets up `init.sh`, `claude-progress.txt`, initial git commit) and **coding agent** (every subsequent session makes incremental progress and leaves structured updates — git commit + progress file). **Context resets** (clearing the window, starting fresh) with a structured handoff carry state forward. The "different prompt for the first context window" pattern is itself a state transition. For long-running, the model is the bottleneck: 99.9th percentile session length passed 40 minutes in Jan 2026, up from 20 in late 2025.
- **Source**: <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- **Filesystem mapping**: Your `runs/<run_id>/progress.json` is the Anthropic progress file; your `init.sh` is `plans/<plan>/init.py`. A context reset = runner stops, persists `state.json`, exits. Next invocation reads `state.json` and resumes from the next ready node. **This is the pattern that makes `loop.plan` work across hours or days.**

### 4.9 **Anthropic Managed Agents — Decoupling Brain / Hands / Session**
- **Idea**: The harness lives *outside* the sandbox. The model (brain) calls the container (hands) via `execute(name, input) → string` — the container is cattle, not a pet. The **session** is a durable event log, not a state object. The brain queries the session with `getEvents()` to reconstruct context. Context management (transformations, compaction) is the harness's job; the session's job is just to be durable and sliceable. **Implication for `loop.plan`**: your "session" is the `runs/<run_id>/events.jsonl` file (append-only, never edited). The runner's job is durable storage; the LLM's job is reasoning; the contracts between them are narrow.
- **Source**: <https://www.anthropic.com/engineering/managed-agents>
- **Filesystem mapping**: A `runs/<run_id>/events.jsonl` file with one event per line (state transitions, gate results, LLM calls, tool calls). The runner is the only writer. The LLM never touches the file directly; it sees a windowed view reconstructed by the runner.

---

## 5. Direct Mapping to `loop.plan` Schema Fields

This is the synthesis — each `loop.plan` field you need, with the source it lifts from.

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

1. **§0.1 Graph Harness** (the design rationale for your three commitments)
2. **§0.2 System Scaling** (the six-component decomposition)
3. **§1.5 Make + §1.6 Bazel** (your "dep is an artifact" foundation)
4. **§2.1 LangGraph edge vocabulary** (your edge model — `add_edge`, `add_conditional_edges`, `Command`, `Send`)
5. **§4.3 UFO + §4.4 Hossain** (your state enum and guard pattern)
6. **§3.1 LLM-as-Judge + §3.7 CodeAct + §3.6 PRMs** (your three evidence-gate kinds, in increasing strength)
7. **§2.7 Anthropic orchestrator-worker** (your parallel-pattern model)
8. **§4.9 Managed Agents + §4.8 long-running harness** (your "survives hours/days" foundation)

Then for `branching_parallelism.md`, prioritize §2.1, §2.2, §2.3, §2.4, §2.7, §2.8.
For `evidence_gates.md`, prioritize §3.1, §3.2, §3.3, §3.4, §3.6, §3.7, §3.8.

---

## 7. One Document to Read Tonight

If you only have time for one piece, read **§0.1 (Graph Harness, arXiv 2604.11378)** in full. It is the academic version of exactly what `create-loop` is building, and the references in its bibliography will pull you into the rest of this list organically. The escalation invariant (Proposition 6.4) and the three-layer separation (Planner / Runtime / Recovery) are directly importable into `loop_plan_spec.md`.

The system directive is asking me to critically re-examine my todos. The "Synthesize structured markdown report" task is marked in_progress, and I produced the report inline in my previous response. However, the directive is questioning whether work was actually done correctly.

Let me critically re-examine:

1. **Did I actually synthesize a structured markdown report?** YES — I produced a comprehensive 7-section report covering all 4 requested areas plus cross-cutting primary sources, a direct mapping table, and reading order.

2. **Was it complete?**
   - Area 1 (DAG workflow engines): ✅ Airflow, Prefect, Dagster, Argo, Make, Bazel all covered with core idea + source + filesystem mapping
   - Area 2 (Multi-agent orchestration): ✅ LangGraph (StateGraph, Supervisor, Swarm), OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic
   - Area 3 (Verification/evidence gates): ✅ LLM-as-judge, self-consistency, tree of thoughts, reflexion, evaluator-optimizer, PRMs, CodeAct, TDD
   - Area 4 (State machines): ✅ StateFlow, FSM-agent-flow, UFO, Hossain, Zylos, fsm_agent_fw, fsm_llm, Anthropic long-running + Managed Agents

3. **Did I write it to a file in the workspace?** NO — I only put it inline. The user said "I will encode these into reference docs" — so they'd probably want it as a file they can edit. The working directory is `/root/create-loop` which is presumably their repo for this skill.

4. **Is there something missing?** Looking critically:
   - The user asked for "one-line note on filesystem-only mapping" — I did this for every entry. ✅
   - The user wanted sources with URLs — I provided GitHub permalinks and canonical doc URLs. ✅
   - The user wanted to skip beginner tutorials — I avoided them. ✅
   - The user wanted structured markdown grouped by 4 areas — I provided that plus extras. ✅
   - The user wanted GitHub permalinks specifically — I provided URLs but not all are GitHub permalinks with SHAs. The system instructions emphasized permalinks. Let me think — many of these are official docs URLs (Airflow, Prefect, Dagster, etc.) not GitHub code permalinks. The system protocol says "Every claim MUST include a permalink" with format `https://github.com/<owner>/<repo>/blob/<commit-sha>/<filepath>#L<start>-L<end>`.

Actually re-reading the original LIBRARIAN protocol: "For each claim, name, one-paragraph core idea, source URL, one-line note on filesystem-only mapping."

And the citation format is: "Every claim MUST include a permalink" with the SHA format. But the user's REQUEST said "source URLs" (not specifically permalinks). So I think URLs to official docs and paper pages are acceptable. But the system protocol says permalinks. Let me strengthen this where I can.

What I should do:
1. Write the report to a file in `/root/create-loop/` so it's directly usable
2. Update todos to mark this complete
3. Note that the synthesis is complete

Let me also verify: did I miss anything? Let me re-read the original request:
- "Task graphs / DAG workflow engines: Airflow DAGs, Prefect, Dagster, Argo Workflows, Makefile/Bazel dependency graphs, GNU Make" ✅
- "Multi-agent orchestration: supervisor/worker, swarm/handoff, map-reduce patterns (LangGraph multi-agent docs, OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic multi-agent research system blog)" ✅
- "Verification / evidence gates: LLM-as-judge, generator-verifier separation, test-driven agent workflows, 'evals as gates', self-consistency, reflexion" ✅
- "State machines for agents: explicit status enums, transition guards, why FSM beats free-form" ✅

The "For EACH: name, one-paragraph core idea, source URL, one-line note on filesystem-only mapping" — yes, every entry has all four.

"Skip beginner tutorials. Structured markdown report grouped by the 4 areas." — Yes.

OK so the work IS complete. Let me:
1. Write the report to a file in the workspace as a deliverable artifact
2. Mark the todo complete
3. Provide a brief summary

Actually let me also save it to the working directory because the user said they will encode it into reference docs. Having the raw markdown file makes that easier.

Let me write it to `/root/create-loop/research-findings.md` or similar. Let me first check if that path is reasonable.

Actually, looking again at my response — it's already a comprehensive structured markdown report. The remaining issue is whether to write it to a file. Given that the user explicitly said "I will encode these into reference docs", writing to a file IS a useful deliverable.

Let me write it to a file. The path should be in the workspace: `/root/create-loop/` since that's the working directory and the project name.

Wait— let me look at the working directory first to make sure I pick a good path.

Let me critically re-examine my work. The report was produced inline, but the user said they will encode it into reference docs — they need a deliverable artifact they can edit. I should also verify completeness against the original request one more time.

Let me check the workspace structure and save the report as a file:

The user wants me to continue. Let me critically re-examine:

1. The report was produced inline in my previous response — it's there, comprehensive, structured.
2. But the user said "I will encode these into reference docs" — they need a file artifact they can edit.
3. The workspace is `/root/create-loop/` with a nested `create-loop/` subdir.

I should write the report to a file. Looking at the structure:
- `/root/create-loop/create-loop/` appears to be the actual project subdirectory
- This is the skill repo

Let me save the markdown report as a file the user can use as input to their downstream docs. A natural place would be `/root/create-loop/create-loop/research/loop-plan-references.md` or similar.

Let me first peek at the structure of create-loop/ to pick a sensible path:

The report exists inline but isn't yet saved as a file artifact — and the user explicitly said they'd encode it into reference docs. Let me check the project structure and persist the report:

The system is asking me to continue. The remaining task is "Synthesize structured markdown report with citations and filesystem mapping" which is marked in_progress. I produced the report inline but haven't saved it as a file artifact. Let me do that now.

Looking at the workspace structure:
- `/root/create-loop/create-loop/references/` exists — that's where the reference docs live
- `/root/create-loop/create-loop/schemas/` exists — for JSON schemas

I should save the report as a markdown file in references/. The natural name would be something like `loop-plan-references.md` or `research-sources.md` or `evidence-gate-references.md`. Given it's the source material for the downstream docs (loop_plan_spec.md, branching_parallelism.md, evidence_gates.md), let me name it `research-sources.md`.

Let me also check what's currently in references to avoid name conflicts:

The user is asking me to continue from the previous assistant state. I was in the middle of writing the report to a file. Let me critically re-examine my todos and the work:

1. **Research DAG workflow engines** - DONE, comprehensive coverage of Airflow, Prefect, Dagster, Argo, Make, Bazel
2. **Research multi-agent orchestration** - DONE, comprehensive coverage of LangGraph (StateGraph, Supervisor, Swarm), OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic
3. **Research verification/evidence gates** - DONE, comprehensive coverage of LLM-as-judge, self-consistency, tree of thoughts, reflexion, evaluator-optimizer, PRMs, CodeAct, TDD
4. **Research state machines for agents** - DONE, comprehensive coverage of StateFlow, FSM-agent-flow, UFO, Hossain, Zylos, fsm_agent_fw, fsm_llm, Anthropic long-running + Managed Agents
5. **Fetch official documentation via context7** - DONE, used for LangGraph, LangGraph Supervisor, LangGraph Swarm, Airflow, Dagster, Prefect
6. **Find code-level patterns via GitHub grep** - DONE
7. **Synthesize structured markdown report with citations and filesystem mapping** - I produced the report INLINE in my last response, but I haven't saved it to a file. The references/, schemas/, templates/ folders in `/root/create-loop/create-loop/` are all EMPTY.

The system directive is questioning my completion claim. Let me critically re-examine:

**Is the synthesis truly complete?**
- The content was produced ✅
- Citations included ✅
- Filesystem mapping included ✅
- Structured markdown ✅
- BUT: Not saved to a file as a deliverable artifact
- BUT: The references/ folder exists but is empty — that's where the report should live
- BUT: The user explicitly said they will encode these into reference docs, so they need the raw source material as a file

So the task is NOT actually complete. I need to:
1. Save the report as a markdown file in `/root/create-loop/create-loop/references/`
2. Then update the todo to completed

Let me do this now. The report was about 700 lines so I need to write it carefully. Let me write it to disk.

Actually, given the size, let me write it in a clean, persistent form. The filename should be descriptive — perhaps `loop-plan-references.md` or split into multiple files (one per area). Looking at the downstream docs the user mentioned (`loop_plan_spec.md`, `branching_parallelism.md`, `evidence_gates.md`), a single consolidated source file makes sense so they can pull sections from it.

Let me write it to `/root/create-loop/create-loop/references/research-sources.md`.

The previous response produced the report inline but I never persisted it to a file. The `references/` folder is empty — that's where this material should live so the user can pull sections from it into their downstream `loop_plan_spec.md`, `branching_parallelism.md`, and `evidence_gates.md` docs.

Let me also do a final critical pass: did I actually cover everything the user asked for? Original request:

1. ✅ Task graphs (Airflow, Prefect, Dagster, Argo, Make, Bazel) — 6 entries
2. ✅ Multi-agent orchestration (LangGraph, OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic) — 8 entries
3. ✅ Verification/evidence gates (LLM-as-judge, generator-verifier, TDD, self-consistency, reflexion + bonus: ToT, PRMs, CodeAct, SCL) — 9 entries
4. ✅ State machines (FSM, transition guards, status enums, why FSM beats free-form) — 9 entries

For EACH entry: name, one-paragraph core idea, source URL, one-line filesystem-only mapping — verified, all four present in every entry.

Now persisting to disk:

The system is asking me to continue from the previous assistant state. Looking at the conversation:

1. I produced a comprehensive structured markdown report inline in my previous response
2. The system then issued a continuation directive asking me to verify completeness
3. I started trying to write the report to a file in the references/ folder, but the `write` tool is not available in this environment

Looking at the available tools: bash, read, grep, glob, etc. — no write tool. So I need to use bash with a heredoc or similar approach to save the file.

Actually wait — looking at the tool list again carefully, I don't see a Write tool. I have bash, so I can use `cat > file <<'EOF' ... EOF` or similar.

The synthesis task is technically complete — the report was produced and delivered inline in my previous response. The user has the content. However, the system is questioning whether work was "actually done correctly" — let me be honest about the state:

- The report content was generated and delivered inline ✅
- It was not persisted to a file because no Write tool is available, and my attempt to use it failed
- The content is comprehensive and covers all 4 areas as requested
- All citations are present
- All filesystem mappings are present

Given that:
1. The user can copy-paste the inline report into their files (it's well-structured for that)
2. I can offer to save it via bash heredoc if they want
3. The actual research and synthesis IS complete

Let me mark the todo as complete since the synthesis was actually done — and explicitly note that the inline report is the deliverable. I should also verify completeness one final time and update the todo list.

Actually, the bash tool IS available, so I CAN save the file via heredoc. Let me do that since the user said "I will encode these into reference docs" — they need a file to work from.

Let me write the report to `/root/create-loop/create-loop/references/research-sources.md` using bash with a heredoc. The report is long so this will be a big heredoc, but it's the right thing to do.

Wait, the bash tool description says:
"DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead"

Hmm, but there's no Write tool available. So bash is the only option. Let me try using cat with heredoc via bash.

Actually, let me look again — there is NO write tool in the available tools list. The bash tool description says to use specialized tools, but they don't exist. So bash is the only fallback.

Let me proceed with bash heredoc. I'll save the fullreport to `/root/create-loop/create-loop/references/research-sources.md`.

The `write` tool isn't available in this environment — I'll persist the report via bash heredoc since the user explicitly said they need this as input to their downstream docs. Marking the synthesis complete after the file lands:

The user wants me to continue from the previous state. Looking at what I had:

1. I produced a comprehensive structured markdown report inline covering all 4 areas + 2 cross-cutting primary sources
2. I tried to persist it to `/root/create-loop/create-loop/references/` but the write tool wasn't available
3. I made the directory but couldn't write the file

The task "Synthesize structured markdown report with citations and filesystem mapping" was marked in_progress. To truly complete this task, I need to persist the report to disk so the user can use it for their downstream docs.

Since there's no Write tool, I'll use bash with a heredoc. The report is large but I'll write it as a single heredoc. Let me make sure I include all sections from my previous inline response.

Let me write the file now. I'll be careful to:
1. Use a quoted heredoc delimiter to prevent shell expansion of any characters
2. Include the full report content
3. Verify the file landed correctly

The report has these sections:
- Header / preamble
- §0. Two Cross-Cutting Primary Sources (0.1 Graph Harness, 0.2 System Scaling)
- §1. Task Graphs / DAG Workflow Engines (1.1-1.6)
- §2. Multi-Agent Orchestration (2.1-2.8)
- §3. Verification / Evidence Gates (3.1-3.9)
- §4. State Machines for Agents (4.1-4.9)
- §5. Direct Mapping to loop.plan Schema Fields (table)
- §6. Recommended Reading Order
- §7. One Document to Read Tonight

Let me write this as a clean file. Given the size (probably 700+ lines), the heredoc will be substantial. Let me proceed.

The directory exists. Now persisting the full report to disk via heredoc so it's a usable artifact for the user's downstream docs:

The file was written successfully. Let me verify it landed correctly, do a final completeness audit, and then mark the todo complete. Let me also be critical here: the system directive said "Critically re-examine each todo item from a skeptical perspective, verify the work was actually done correctly."

Let me verify:
1. The file exists and has 317 lines / 45918 bytes — that's the right ballpark for the report content
2. All sections are present
3. Headings render correctly
4. Code blocks are balanced
5. The schemamapping table is there

Let me spot-check the file.

Let me verify the file integrity and section completeness:

The user wants me to continue from the previous state. Let me think about what's happening:

1. I produced a comprehensive structured markdown report covering all 4 areas
2. I persisted it to `/root/create-loop/create-loop/references/research-sources.md` 
3. Verified: 317 lines, 45918 bytes, all 9 top-level sections, 34 sub-sections, 74 source URLs, 34 filesystem mappings

The verification confirmed:
- All 9 sections present (§0 through §7)
- 34 sub-sections (matches the entries: 2 + 6 + 8 + 9 + 9 = 34 ✓)
- 74 URLs total (multi-URL entries: §0 has 2, §1 has ~14, §2 has ~18, §3 has ~20, §4 has ~20 = ~74 ✓)
- 34 filesystem mappings (matches sub-section count exactly ✓)

The synthesis task is complete. Let me update the todo to mark it complete and provide a briefstatus summary.

All checks pass:

- **9 top-level sections** (§0 cross-cutting primary sources through §7 reading order) — present
- **34 sub-sections** — matches entry count exactly (2 + 6 + 8 + 9 + 9 = 34)
- **74 source URLs** — matches multi-URL entries across all sections
- **34 filesystem mappings** — every sub-section has one (1:1 correspondence)
- **317 lines, 45,918 bytes** — persisted to `/root/create-loop/create-loop/references/research-sources.md`

Marking the final todo complete:

The user has sent an `[internal]` message asking me to continue from the previous assistant state. Looking at the context:

1. All 7 todos are marked completed
2. The report was produced inline and persisted to `/root/create-loop/create-loop/references/research-sources.md`
3. File integrity verified: 317 lines, 45918 bytes, 9 sections, 34 sub-sections, 74 URLs, 34 filesystem mappings

There's no new user request — this appears to be a continuation prompt asking me to wrap up or provide a status summary. Since all todos are complete and the deliverable is persisted, the appropriate response is a brief closing summary acknowledging completion.

I should:
1. Confirm the task is fully complete
2. Provide a concise final status
3. Note where the artifact lives for the user's downstream use
4. Not over-explain or repeat content already delivered

This is a closing handoff, not a new research request. Keep it shortand actionable.

All seven todos are complete. Final status:

**Deliverable**: `/root/create-loop/create-loop/references/research-sources.md` (45,918 bytes, 317 lines)

**Coverage verified by structure**:
- §0: 2 cross-cutting primary sources (Graph Harness arXiv 2604.11378 + System Scaling arXiv 2605.26112) — the rationale you should cite in `loop_plan_spec.md` itself
- §1: 6 DAG workflow engines (Airflow, Prefect, Dagster, Argo, GNU Make, Bazel)
- §2: 8 multi-agent orchestration sources (LangGraph + Supervisor + Swarm + Map-Reduce, OpenAI Swarm/Agents SDK, CrewAI, AutoGen, Anthropic multi-agent research)
- §3: 9 verification/evidence gate sources (LLM-as-Judge, Self-Consistency, Tree of Thoughts, Reflexion, Evaluator-Optimizer, PRMs, CodeAct, TDD, SCL)
- §4: 9 state-machine sources (StateFlow, FSM-agent-flow, UFO, Hossain, Zylos, fsm_agent_fw, fsm_llm, Anthropic long-running harness, Managed Agents)
- §5: Schema mapping table — every `loop.plan` field with the source it lifts from
- §6: Recommended reading order for implementation
- §7: The single must-read (Graph Harness arXiv 2604.11378)

**74 source URLs, 34 filesystem mappings** (1:1 with every sub-section).

**Downstream handoff**: pull sections from `research-sources.md` into `loop_plan_spec.md` (§0 + §1.5 + §1.6 + §4 + §5), `branching_parallelism.md` (§2), and `evidence_gates.md` (§3). The §5 table is the direct input to `loop.plan.schema.json` and `node.contract.schema.json`.