"""
Agent communication
====================
In-process message bus between specialist_agents/*.py instances -
core/events.py's EventBus is a fire-and-forget pub/sub for the whole
assistant (UI, plugins, agents alike) with no per-subscriber inbox and
no history; this is narrower and swarm-specific: every agent gets its
own inbox queue.Queue it can poll or block on, direct agent-to-agent
sends are distinguishable from broadcasts, and every message is
persisted through swarm_memory.py's log_message() so
agent_orchestrator.py (or a human debugging it later) can replay what
the swarm said to itself during a run.

Doesn't replace core/events.py - agent_orchestrator.py may still use
that bus to announce swarm-level milestones ("swarm:task_completed")
to the rest of Ultron; this one is for agent<->agent chatter that
never needs to leave the swarm.
"""

import queue
import time
from threading import Lock
from typing import Dict, List, Optional

from multi_agent_swarm.swarm_memory import get_swarm_memory


class AgentBus:
    """Per-agent inboxes plus broadcast, backed by swarm_memory.py's log."""

    def __init__(self):
        self._inboxes: Dict[str, "queue.Queue[Dict]"] = {}
        self._lock = Lock()

    def subscribe(self, agent_name: str) -> Dict:
        """Register `agent_name` to receive messages. Idempotent - safe
        to call again if an agent is re-instantiated mid-session."""
        with self._lock:
            self._inboxes.setdefault(agent_name, queue.Queue())
        return {"subscribed": agent_name}

    def send(self, from_agent: str, to_agent: str, content: Dict) -> Dict:
        """Direct message to one agent's inbox. Auto-subscribes the
        recipient if it hasn't called subscribe() yet, so senders don't
        need to know delivery order."""
        with self._lock:
            self._inboxes.setdefault(to_agent, queue.Queue())
            self._inboxes[to_agent].put({"from": from_agent, "content": content, "sent_at": time.time()})
        get_swarm_memory().log_message(from_agent, to_agent, content)
        return {"delivered_to": to_agent}

    def broadcast(self, from_agent: str, content: Dict) -> Dict:
        """Send to every currently-subscribed agent except the sender."""
        with self._lock:
            recipients = [name for name in self._inboxes if name != from_agent]
            for name in recipients:
                self._inboxes[name].put({"from": from_agent, "content": content, "sent_at": time.time()})
        get_swarm_memory().log_message(from_agent, "*", content)
        return {"delivered_to": recipients}

    def receive(self, agent_name: str, block: bool = False, timeout: float = 1.0) -> Optional[Dict]:
        """Pop the oldest waiting message for `agent_name`, or None if its
        inbox is empty and `block` is False. With `block=True`, waits up
        to `timeout` seconds before giving up."""
        with self._lock:
            inbox = self._inboxes.setdefault(agent_name, queue.Queue())
        try:
            return inbox.get(block=block, timeout=timeout if block else None)
        except queue.Empty:
            return None

    def inbox_size(self, agent_name: str) -> int:
        with self._lock:
            inbox = self._inboxes.get(agent_name)
        return inbox.qsize() if inbox else 0

    def subscribed_agents(self) -> List[str]:
        with self._lock:
            return sorted(self._inboxes.keys())


_bus: Optional[AgentBus] = None


def get_agent_bus() -> AgentBus:
    """Process-wide singleton, same pattern as core.events.get_event_bus()."""
    global _bus
    if _bus is None:
        _bus = AgentBus()
    return _bus
