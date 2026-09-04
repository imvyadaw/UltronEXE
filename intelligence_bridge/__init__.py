"""
Intelligence Bridge (Phase 20.4)
=============================
Single facade tying together all 13 subsystem bridges that make up
ULTRON's "intelligence" layer, the same role phase16_bridge.py played
for Phase 17.1's CORE_INTEGRATION - one place a caller can reach for
any of them without hunting down 13 separate import paths, while each
underlying bridge still works fine used directly.

    world_state_bridge.py      - what's true right now (active app,
                                  presence, open documents, etc)
    intent_bridge.py           - deeper intent understanding, above
                                  core.intent_router's fast classifier
    goal_bridge.py              - goal planning/decomposition/execution
    verification_bridge.py     - was a result/goal actually achieved
    healing_bridge.py           - diagnosing and auto-repairing errors
    skill_learning_bridge.py   - which skills/tools work for what
    knowledge_bridge.py        - stored facts / knowledge-base recall
    confidence_bridge.py       - how sure ULTRON should be in an answer
    answer_reader_bridge.py    - pulling a short answer out of a
                                  longer source
    conversation_bridge.py     - conversation history/context
    proactive_bridge.py        - intelligence.proactive_intelligence
                                  (Phase 20.1) - whether to speak up
    predictive_bridge.py       - intelligence.predictive_preparation
                                  (Phase 20.2) - what to have ready
    performance_bridge.py      - intelligence.adaptive_performance
                                  (Phase 20.3) - making calls fast

Every one of the 13 was written without its underlying subsystem's
source in hand except performance_bridge.py's (adaptive_performance/
shipped alongside this phase) - see _bridge_utils.py for how the other
12 resolve their target defensively by name/keyword instead of a hard
import, and degrade to a harmless no-op (is_available() == False)
rather than raising if that target isn't present in a given checkout.
That means this whole package is safe to import and wire in anywhere,
today, regardless of exactly which earlier intelligence/ phases a
given checkout already has.

Usage:
    from intelligence_bridge import get_intelligence_bridge

    ib = get_intelligence_bridge()
    print(ib.status())                 # availability of all 13 at a glance
    if ib.performance.is_available():
        plan = ib.performance.plan_call("chat_completion", cache_key=prompt_hash)

Each bridge is also importable/usable on its own without going through
this facade:

    from intelligence_bridge.performance_bridge import get_performance_bridge

Purely additive - nothing in Phase 1-20 imports from here, and this
package does not modify anything it bridges to.
"""

from intelligence_bridge.world_state_bridge import WorldStateBridge, get_world_state_bridge
from intelligence_bridge.intent_bridge import IntentBridge, get_intent_bridge
from intelligence_bridge.goal_bridge import GoalBridge, get_goal_bridge
from intelligence_bridge.verification_bridge import VerificationBridge, get_verification_bridge
from intelligence_bridge.healing_bridge import HealingBridge, get_healing_bridge
from intelligence_bridge.skill_learning_bridge import SkillLearningBridge, get_skill_learning_bridge
from intelligence_bridge.knowledge_bridge import KnowledgeBridge, get_knowledge_bridge
from intelligence_bridge.confidence_bridge import ConfidenceBridge, get_confidence_bridge
from intelligence_bridge.answer_reader_bridge import AnswerReaderBridge, get_answer_reader_bridge
from intelligence_bridge.conversation_bridge import ConversationBridge, get_conversation_bridge
from intelligence_bridge.proactive_bridge import ProactiveBridge, get_proactive_bridge
from intelligence_bridge.predictive_bridge import PredictiveBridge, get_predictive_bridge
from intelligence_bridge.performance_bridge import PerformanceBridge, get_performance_bridge

__all__ = [
    "IntelligenceBridge",
    "get_intelligence_bridge",
    "WorldStateBridge",
    "get_world_state_bridge",
    "IntentBridge",
    "get_intent_bridge",
    "GoalBridge",
    "get_goal_bridge",
    "VerificationBridge",
    "get_verification_bridge",
    "HealingBridge",
    "get_healing_bridge",
    "SkillLearningBridge",
    "get_skill_learning_bridge",
    "KnowledgeBridge",
    "get_knowledge_bridge",
    "ConfidenceBridge",
    "get_confidence_bridge",
    "AnswerReaderBridge",
    "get_answer_reader_bridge",
    "ConversationBridge",
    "get_conversation_bridge",
    "ProactiveBridge",
    "get_proactive_bridge",
    "PredictiveBridge",
    "get_predictive_bridge",
    "PerformanceBridge",
    "get_performance_bridge",
]


class IntelligenceBridge:
    """Ties all 13 subsystem bridges together behind one object. Each
    is built lazily on first access (not at IntelligenceBridge()
    construction time) so importing this facade never pays the cost -
    or risk - of resolving all 13 underlying subsystems unless a
    caller actually asks for one."""

    def __init__(self):
        self._bridges = {}

    def _get(self, name, getter):
        if name not in self._bridges:
            self._bridges[name] = getter()
        return self._bridges[name]

    @property
    def world_state(self) -> WorldStateBridge:
        return self._get("world_state", get_world_state_bridge)

    @property
    def intent(self) -> IntentBridge:
        return self._get("intent", get_intent_bridge)

    @property
    def goal(self) -> GoalBridge:
        return self._get("goal", get_goal_bridge)

    @property
    def verification(self) -> VerificationBridge:
        return self._get("verification", get_verification_bridge)

    @property
    def healing(self) -> HealingBridge:
        return self._get("healing", get_healing_bridge)

    @property
    def skill_learning(self) -> SkillLearningBridge:
        return self._get("skill_learning", get_skill_learning_bridge)

    @property
    def knowledge(self) -> KnowledgeBridge:
        return self._get("knowledge", get_knowledge_bridge)

    @property
    def confidence(self) -> ConfidenceBridge:
        return self._get("confidence", get_confidence_bridge)

    @property
    def answer_reader(self) -> AnswerReaderBridge:
        return self._get("answer_reader", get_answer_reader_bridge)

    @property
    def conversation(self) -> ConversationBridge:
        return self._get("conversation", get_conversation_bridge)

    @property
    def proactive(self) -> ProactiveBridge:
        return self._get("proactive", get_proactive_bridge)

    @property
    def predictive(self) -> PredictiveBridge:
        return self._get("predictive", get_predictive_bridge)

    @property
    def performance(self) -> PerformanceBridge:
        return self._get("performance", get_performance_bridge)

    def status(self) -> dict:
        """Availability snapshot of all 13 bridges in one call - each
        access here also builds+caches that bridge if it hasn't been
        touched yet this process, same as accessing the property directly."""
        return {
            name: bridge.status()
            for name, bridge in (
                ("world_state", self.world_state),
                ("intent", self.intent),
                ("goal", self.goal),
                ("verification", self.verification),
                ("healing", self.healing),
                ("skill_learning", self.skill_learning),
                ("knowledge", self.knowledge),
                ("confidence", self.confidence),
                ("answer_reader", self.answer_reader),
                ("conversation", self.conversation),
                ("proactive", self.proactive),
                ("predictive", self.predictive),
                ("performance", self.performance),
            )
        }


_facade_instance = None


def get_intelligence_bridge() -> IntelligenceBridge:
    """Process-wide IntelligenceBridge facade singleton."""
    global _facade_instance
    if _facade_instance is None:
        _facade_instance = IntelligenceBridge()
    return _facade_instance
