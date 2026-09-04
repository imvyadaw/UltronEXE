# MULTI_AGENT_SWARM

A swarm of six specialist agents, a message bus between them, a task
delegator that decomposes and assigns work, a consensus engine for
cross-checked answers, a shared blackboard, and one orchestrator tying
it together. Nothing here re-implements what `agents/` or `skills/`
already do - four of six specialists wrap an existing module unchanged.

| File | Wraps | Adds |
|---|---|---|
| `specialist_agents/base_specialist.py` | `agents/base_agent.py` | `can_handle(task)` keyword scoring, uniform `handle(task)` entry point |
| `specialist_agents/code_agent.py` | `agents/coding_agent.py` (unchanged) | swarm task-in/dict-out shape |
| `specialist_agents/security_agent.py` | `agents/security_agent.py` (unchanged) | swarm task-in/dict-out shape |
| `specialist_agents/research_agent.py` | `skills/web/research.py` (unchanged) | lazy `AIRouter` injection, swarm shape |
| `specialist_agents/devops_agent.py` | `skills/windows/manager.py` (unchanged) | swarm shape over `.execute(action, **kwargs)` |
| `specialist_agents/data_analyst_agent.py` | `skills/data/processor.py` (unchanged) | swarm shape over `.execute(action, **kwargs)` |
| `specialist_agents/writer_agent.py` | nothing (new capability) | focused Groq drafting/summarizing/rewriting/outlining, same shape as `coding_agent.py` |
| `agent_communication.py` | nothing (new capability) | per-agent inbox `queue.Queue`, broadcast, delivery logged to `swarm_memory.py` |
| `task_delegation.py` | nothing (new capability) | offline `decompose()` (separator split + keyword type-guessing) and `assign()` (score + round-robin tie-break) |
| `consensus_engine.py` | nothing (new capability) | `reach_consensus()` over several agents' answers: majority / unanimous / weighted |
| `swarm_memory.py` | nothing (new capability) | SQLite: task log, key/value blackboard, message history |
| `agent_orchestrator.py` | all of the above + `PHASE_17_1_FOUNDATION`'s `phase16_bridge` | `handle_request()` (split+delegate), `run_swarm_review()` (same question to many, consensus) |

## Usage

```python
from PHASE_17_4_MULTI_AGENT.MULTI_AGENT_SWARM import get_orchestrator

swarm = get_orchestrator()

# Split a compound request across specialists, running independent
# subtasks concurrently by default:
result = swarm.handle_request(
    "Research the top 3 Python web frameworks, then write a short "
    "summary comparing them"
)
result["completed"]      # bool
result["subtasks"]       # list of {description, type, agent, result}

# Send the same question to several specialists and combine their
# answers instead of splitting the work:
review = swarm.run_swarm_review(
    "def run(cmd): return os.system(cmd)  # is this safe to expose as a tool?",
    agent_names=["code", "security"],
    strategy="unanimous",
)
review["consensus"]      # None if the two disagree, the shared verdict if not
review["dissenting"]     # who didn't agree, if not unanimous
```

```python
from PHASE_17_4_MULTI_AGENT.MULTI_AGENT_SWARM import get_swarm_memory

get_swarm_memory().recent_tasks(limit=10)     # what the swarm has been doing
get_swarm_memory().recent_messages(limit=20)  # what agents said to each other
```

## Safety properties

- **Additive only.** Same guarantee every Phase 17 package makes:
  nothing in `agents/`, `skills/`, `memory/`, `core/`, `ai/`, `main.py`,
  or any earlier Phase 17 package imports anything from here.
- **Bounded concurrency.** `handle_request()` and `run_swarm_review()`
  both cap parallel dispatch at `MAX_PARALLEL_AGENTS` (6, one per
  specialist) via a `ThreadPoolExecutor` - a compound request can't
  spawn unbounded threads no matter how many subtasks it decomposes into.
- **A missing specialist never takes the swarm down.** `handle_request()`
  reports "no specialist matched" per subtask rather than raising;
  `run_swarm_review()`'s consensus excludes any agent that errored
  rather than letting one bad result poison the vote.
- **Destructive actions still gated underneath.** `devops_agent.py` and
  `security_agent.py` call straight through to `core/permissions.py`'s
  `PermissionGate` exactly as they already did in `agents/` - this
  package adds coordination on top, it doesn't loosen that gate.
