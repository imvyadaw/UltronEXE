"""
Assistant
=========
The top-level runtime object: holds the live state for one Ultron
session (the LLM client, the slash-command processor, the optional
voice/STT stack, and the toggleable modes - UI orb / typed text input /
silent replies - that can be flipped at runtime by voice command
without restarting the app) and owns the single `handle_command()` path
every input mode (typed, voice-typed, hands-free wake-word) routes
through.

This used to be defined inline in main.py as `UltronRuntime`. It moved
here so it has a stable import path other front-ends (plugins, a future
core.debug_console session, tests) can use without importing main.py
itself (which also parses CLI args and starts I/O loops on import-time
side effects would be the wrong thing to pull in just to get the
runtime class). `UltronRuntime` is kept below as an alias so any code
or comments still referring to that name keep working.

main.py stays the entry point: it still does argument parsing, prints
the banner, and picks which run_* loop to start - it just imports
`Assistant` from here instead of defining it.
"""

import re
import sys
import threading
import time
import os
from typing import Optional

from core.events import get_event_bus
from core.logger import get_logger
from core import perf_trace

logger = get_logger("ultron.assistant")

# Speaking a long answer word-for-word out loud was the other big source of
# "Ultron is slow" - a 19-line answer with a bunch of bullet points could
# take minutes for TTS to read line-by-line, during which Ultron can't hear
# the next wake word. speak_reply() below now speaks a SHORT, prose-only
# summary of the answer while the complete answer (lists, code, everything)
# still gets printed to the console/UI as before - nothing is lost on
# screen, it just isn't all read aloud word-for-word.
SPEAK_MAX_CHARS = 700

# Lines that are clearly "detail", not something you'd say out loud:
# bullets, numbered list items, markdown headings, code fences, table rows.
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*•‣]|\d+[.)]|#{1,6}\s|```|\|.*\|)\s*")

# Raw URLs (image links, video links, source links, ...) that show up in a
# reply's text - TTS has no concept of a link, so left in, these get read
# aloud character-by-character/segment-by-segment ("aitch tee tee pee ess
# colon slash slash...") instead of being skipped like any other on-screen
# detail. Matches bare http(s) links and markdown-style [text](url) links -
# for the latter, only the url part is dropped, the visible text stays.
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://\S+?)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")


def _strip_urls(text: str) -> str:
    """Drop links from text meant to be spoken. Markdown links keep their
    visible label (e.g. "[Khesari Lal Yadav's photo](https://...)" ->
    "Khesari Lal Yadav's photo"); bare URLs are removed outright. Returns
    (cleaned_text, urls_removed) so the caller can decide whether to add a
    "check the screen" note."""
    urls_removed = False

    def _md_sub(m):
        nonlocal urls_removed
        urls_removed = True
        return m.group(1)

    text = _MD_LINK_RE.sub(_md_sub, text)
    if _BARE_URL_RE.search(text):
        urls_removed = True
        text = _BARE_URL_RE.sub("", text)
    # Clean up leftover punctuation/whitespace a removed URL can leave
    # behind, e.g. "here: ." or "watch it:  ".
    text = re.sub(r"[:\-]\s*(?=[.\n]|$)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), urls_removed


def _strip_list_lines(text: str) -> str:
    """Drop bullet/numbered/heading/code lines, keeping only the prose
    paragraphs - those are almost always where the actual conversational
    answer lives; the list underneath is supporting detail meant to be
    *read*, not narrated line-by-line."""
    kept = [ln for ln in text.splitlines() if ln.strip() and not _LIST_LINE_RE.match(ln)]
    return "\n".join(kept).strip()


def _count_list_items(text: str) -> int:
    return sum(1 for ln in text.splitlines() if _LIST_LINE_RE.match(ln))


def _trim_to_sentences(text: str, max_chars: int) -> str:
    """Cut at the last sentence boundary at or before max_chars rather than
    mid-word, so the spoken reply is still a coherent (just shorter)
    answer."""
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    out = ""
    for s in sentences:
        if out and len(out) + len(s) + 1 > max_chars:
            break
        out = f"{out} {s}".strip()
    return out or text[:max_chars]


def _spoken_version(text: str) -> str:
    """Turn a full (possibly long, possibly list-heavy) reply into a short,
    natural line to speak aloud - the smart replacement for just reading
    everything on screen word-for-word:

    1. Strip bullets/numbered items/headings/code - keep only prose.
    2. Trim that prose to a handful of sentences (SPEAK_MAX_CHARS).
    3. If the reply was mostly a list with little/no prose (e.g. "here are
       5 apps you have"), don't read the items out - say how many there
       are and point at the screen instead.
    4. If real content got left out of the spoken version, add a short
       heads-up so the user knows to check the screen for the rest.

    Also strips any stray '*' characters before speaking - the LLM is
    instructed never to emit them, but this is a defensive backstop so a
    slip-up never gets spoken aloud as a literal "asterisk" or garbled
    symbol.
    """
    text = text.strip()
    if not text:
        return text

    prose = _strip_list_lines(text)
    list_items = _count_list_items(text)

    if not prose and list_items:
        # Answer is basically just a list/table - summarize instead of
        # reading every line.
        return f"I've got {list_items} items for you, Sir - full list's on screen."

    prose, urls_removed = _strip_urls(prose or text)

    spoken = _trim_to_sentences(prose, SPEAK_MAX_CHARS)

    was_trimmed = len(spoken) < len(prose)
    if list_items or was_trimmed or urls_removed:
        spoken = spoken.rstrip(". ") + ". The rest is on screen, Sir."

    spoken = spoken.replace("*", "").replace("  ", " ")
    return spoken.strip()


def _strip_asterisks(text: str) -> str:
    """Defensive backstop: remove every '*' character from a reply before
    it's shown on screen or spoken. The system prompt already instructs
    the LLM to never emit asterisks, but this guarantees it - the user
    should never see or hear a stray '*' in any Ultron answer, no matter
    which code path produced the text (LLM, local command, intent router)."""
    if not text:
        return text
    return re.sub(r"\*+", "", text).replace("  ", " ").strip()


class C:
    """ANSI colour codes shared by the assistant runtime and main.py's
    CLI output, so both print in the same style."""

    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


class Assistant:
    """Holds the live state for one Ultron session: the LLM client, the
    slash-command processor, the optional voice/STT stack, and the
    toggleable modes (UI orb / typed text input / silent replies) that can
    be flipped at runtime by voice command without restarting the app."""

    def __init__(self, client, processor):
        self.client = client
        self.processor = processor
        self.processor.set_reset_callback(client.clear_history)

        # Phase (bridge-wiring fix): serializes concurrent handle_message()
        # calls from UI surfaces (mobile API / web_ui) - see handle_message
        # docstring below for why this exists.
        import threading as _threading

        self._handle_message_lock = _threading.Lock()

        self.voice = None  # set by whichever run_* mode needs TTS
        self.stt = None
        self.detector = None

        self.ui_enabled = False
        self.text_mode_enabled = False
        self.silent_mode = False
        self._text_thread = None

        # Phase 19.1-20.6 intelligence layer (world state, intent
        # prediction, goals, confidence, knowledge graph, proactive/
        # predictive, adaptive performance, self-healing) - best-effort:
        # a checkout without intelligence_bridge/ or database/ still
        # runs exactly as it did before Phase 19, this just goes quiet.
        # See _intel_log_turn()/_intel_record_call() below for where
        # it's actually invoked from the real conversation path.
        try:
            from intelligence import get_intelligence_core

            self.intelligence = get_intelligence_core()
            logger.info("[assistant] intelligence layer connected: %s", self.intelligence.is_available())
        except Exception:
            logger.exception("[assistant] intelligence layer unavailable - continuing without it")
            self.intelligence = None

        # Phase 18.1 observer layer (consciousness + personality). This is
        # deliberately NOT a router: the 6-tier pipeline in
        # _handle_command_inner() below still decides everything about
        # *how* a turn is handled, exactly as before. consciousness only
        # watches (push_focus/pop_focus/note_outcome around each turn) so
        # "what is Ultron doing right now" becomes answerable (see
        # ai/local_router.py's status query), and personality.speak() is
        # used only for the handful of Ultron-initiated lines that already
        # have a matching tone_manager phrase category (background task
        # results, proactive threshold alerts) - never for wrapping the
        # LLM's own free-form answers, since personality.speak() picks a
        # canned line per category rather than rewriting arbitrary text.
        # Best-effort: a checkout without PHASE_18_1_CORE_FOUNDATION/ or
        # proactive/ still runs exactly as it did before this layer
        # existed, this just goes quiet. See docs/PHASE18_INTEGRATION_MAP.md
        # for the full reasoning behind keeping this observational-only.
        try:
            from core.consciousness_p18 import get_consciousness
            from core.personality import get_personality

            self.consciousness = get_consciousness()
            self.personality = get_personality()
            logger.info("[assistant] Phase 18 observer layer connected (consciousness + personality)")
        except Exception:
            logger.exception("[assistant] Phase 18 observer layer unavailable - continuing without it")
            self.consciousness = None
            self.personality = None

        # Phase 18 goal-decision layer (decision_maker -> autonomous_executor).
        # Gated behind ULTRON_AUTONOMY_ENABLED (.env) - defaults to OFF, on
        # request, because this is the one piece of Phase 18 that can
        # actually take independent action (autonomous_executor calls real
        # tools) rather than just observe. Bounded even when on:
        #   - only ever triggered by explicit "goal: ..."/"handle X end to
        #     end"/"X khud se kar do" phrasing (intent_resolver.GOAL_PATTERNS)
        #     - ordinary chat never reaches this, see _route_turn()'s tier
        #     3.55 below.
        #   - autonomous_executor itself caps total tool calls per goal at
        #     MAX_TOTAL_STEPS=40 and retries per sub-goal at
        #     MAX_SUBGOAL_ATTEMPTS=2 (PHASE_17_2's autonomous_executor.py) -
        #     it can't run forever or silently keep retrying past that.
        #   - low consciousness confidence + a short/ambiguous goal routes
        #     to "clarify" (one question back) instead of guessing.
        # See docs/PHASE18_INTEGRATION_MAP.md and docs/TASK5_AUTONOMY_NOTES.md.
        self.decision_maker = None
        if os.getenv("ULTRON_AUTONOMY_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from core.decision_maker import get_decision_maker

                self.decision_maker = get_decision_maker()
                logger.info("[assistant] Phase 18 autonomy layer ENABLED (decision_maker -> autonomous_executor)")
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_AUTONOMY_ENABLED was set but decision_maker failed to load - staying off"
                )
                self.decision_maker = None
        else:
            logger.info("[assistant] Phase 18 autonomy layer OFF (set ULTRON_AUTONOMY_ENABLED=true in .env to enable)")

        # Full Phase 25 proactive engine (predictor/suggester/automatic_actions/
        # disruption_guard), gated behind ULTRON_PROACTIVE_ENABLED (.env) -
        # defaults to OFF, same opt-in convention as ULTRON_AUTONOMY_ENABLED
        # above, because this is the layer that lets Ultron speak up AND
        # (for whitelisted, low-risk, auto_eligible actions only) act
        # without being asked. Safe even when on: automatic_actions.py's
        # whitelist starts EMPTY (a suggestion pattern being learned is not
        # the same as being trusted to act on unattended - the user opts
        # each action_name in explicitly), every auto-run still passes
        # through core/action_pipeline.py's own permission gate with
        # confirmed=False, and disruption_guard.py enforces the same DND/
        # quiet-hours/in-call rules for suggestions and auto-actions alike.
        # Falls back to the old narrow threshold_alerts-only trigger when
        # the flag is off or the full engine fails to import, so a
        # checkout missing proactive/'s newer modules still runs exactly
        # as it did before this wiring.
        self.proactive_engine = None
        if os.getenv("ULTRON_PROACTIVE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from proactive.engine import get_proactive_engine

                self.proactive_engine = get_proactive_engine()
                self.proactive_engine.start(speak_callback=self.speak_reply)
                logger.info(
                    "[assistant] Phase 25 proactive engine ENABLED "
                    "(predictor/suggester/automatic_actions/disruption_guard)"
                )
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_PROACTIVE_ENABLED was set but the full "
                    "proactive engine failed to load - falling back to threshold_alerts only"
                )
                self.proactive_engine = None
        else:
            logger.info(
                "[assistant] Phase 25 proactive engine OFF "
                "(set ULTRON_PROACTIVE_ENABLED=true in .env to enable) - "
                "running narrow threshold_alerts trigger only"
            )

        if self.proactive_engine is None:
            # One proactive trigger, minimally wired: threshold_alerts (CPU/
            # RAM/disk/battery/network crossing a line) polled on its own
            # daemon thread and surfaced through the existing notification
            # tool (ui.notifications.notify) plus speak_reply, using
            # personality.speak() for phrasing where available.
            # Best-effort/daemon: never blocks startup, never raises into the
            # main loop, dies with the process like every other background
            # thread in this class (_text_input_loop, intel-log-turn).
            self._start_proactive_alerts()

        # Deep-audit fix, item #4 (background-subsystem batch): self_healing/,
        # learning_engine/, ultron_shield/ were fully implemented but never
        # imported anywhere - see docs on the Phase 30 audit. All three are
        # observational/protective with no new-network-surface and no
        # ability to act beyond Ultron's own process, so they're wired
        # best-effort and always-on, same as the intelligence/consciousness
        # layers above: a checkout missing one of these packages still runs
        # exactly as before, this just goes quiet.
        self.self_healing = None
        try:
            from self_healing.health_monitor import HealthMonitor
            from self_healing.auto_recovery import AutoRecovery

            monitor = HealthMonitor()
            recovery = AutoRecovery()
            monitor.on_alert(recovery.handle_alert)
            monitor.start(interval_seconds=300.0)
            self.self_healing = {"monitor": monitor, "recovery": recovery}
            logger.info("[assistant] self_healing layer connected (health_monitor + auto_recovery)")
        except Exception:
            logger.exception("[assistant] self_healing layer unavailable - continuing without it")

        self.learning_engine = None
        try:
            from learning_engine.feedback_collector import FeedbackCollector
            from learning_engine.user_adaptation import UserAdaptationEngine

            self.learning_engine = {
                "feedback": FeedbackCollector(),
                "adaptation": UserAdaptationEngine(),
            }
            logger.info("[assistant] learning_engine layer connected (feedback_collector + user_adaptation)")
        except Exception:
            logger.exception("[assistant] learning_engine layer unavailable - continuing without it")

        self.shield = None
        try:
            from ultron_shield.privacy_filter import PrivacyFilter
            from ultron_shield.audit_logger import AuditLogger

            self.shield = {"privacy_filter": PrivacyFilter(), "audit_log": AuditLogger()}
            self.shield["audit_log"].record("startup", "Ultron session started", actor="system")
            logger.info("[assistant] ultron_shield layer connected (privacy_filter + audit_logger)")
        except Exception:
            logger.exception("[assistant] ultron_shield layer unavailable - continuing without it")

        # P1: Mission Persistence Engine, Tool-Chain Optimizer, Capability
        # Isolation. Same best-effort/always-on wiring as self_healing/
        # learning_engine/ultron_shield above - a checkout missing one of
        # these still runs exactly as before, this just goes quiet.
        # startup_brief() is checked once here so a resumable mission from
        # a previous session surfaces immediately instead of needing the
        # user to remember to ask.
        self.mission_manager = None
        self.mission_startup_brief = None
        try:
            from intelligence.mission_engine import get_mission_manager

            self.mission_manager = get_mission_manager()
            self.mission_startup_brief = self.mission_manager.startup_brief()
            logger.info("[assistant] mission_engine connected (mission persistence + auto-resume)")
        except Exception:
            logger.exception("[assistant] mission_engine unavailable - continuing without it")

        self.tool_chain_optimizer = None
        try:
            from ai.tool_chain_optimizer import get_tool_chain_optimizer

            self.tool_chain_optimizer = get_tool_chain_optimizer()
            logger.info("[assistant] tool_chain_optimizer connected")
        except Exception:
            logger.exception("[assistant] tool_chain_optimizer unavailable - continuing without it")

        # ULTRON Advanced Autonomy Fabric: a composition layer that joins
        # world-state, persistent missions, research/knowledge, experience
        # learning and sandbox-first evolution. It adds no bypass around
        # the existing action/permission pipeline.
        self.advanced_autonomy = None
        if os.getenv("ULTRON_ADVANCED_AUTONOMY_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from intelligence.ultron_advanced import get_advanced_autonomy

                self.advanced_autonomy = get_advanced_autonomy()
                logger.info(
                    "[assistant] ULTRON Advanced Autonomy Fabric connected: %s",
                    self.advanced_autonomy.status()["lifecycle"],
                )
            except Exception:
                logger.exception("[assistant] advanced autonomy fabric unavailable - continuing without it")

        # Autonomous internet learning: periodically research a topic
        # (curated queue + knowledge_os stale facts) and store findings
        # into knowledge_os. Off by default - the Advanced Autonomy
        # Fabric's research()/learn_outcome() plumbing existed with no
        # caller until this scheduler. Manual control (autolearn_start/
        # stop/now tools) works regardless of this flag; this flag only
        # decides whether it auto-starts at boot.
        if self.advanced_autonomy is not None and os.getenv(
            "ULTRON_LEARN_FROM_INTERNET", "false"
        ).strip().lower() in ("1", "true", "yes", "on"):
            try:
                from intelligence.ultron_advanced.autonomous_learning import get_autonomous_learning_scheduler

                interval_hours = float(os.getenv("ULTRON_LEARN_INTERVAL_HOURS", "6"))
                get_autonomous_learning_scheduler().start(interval_seconds=interval_hours * 3600)
                logger.info(f"[assistant] autonomous internet learning enabled, interval={interval_hours}h")
            except Exception:
                logger.exception("[assistant] autonomous internet learning failed to start - continuing without it")

        # Financial intelligence: recurring stock/crypto price watcher
        # (finance/market_watcher.py) for threshold alerts. Off by
        # default - manual control (market_check_now / market_watch_add)
        # works regardless of this flag; it only decides whether the
        # recurring schedule auto-starts at boot. Expense tracking and
        # budgets (finance/expense_tracker.py, finance/budget_manager.py)
        # have no background component and need no gate.
        if os.getenv("ULTRON_MARKET_WATCH_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from finance.market_watcher import get_market_watcher

                interval_minutes = float(os.getenv("ULTRON_MARKET_WATCH_INTERVAL_MINUTES", "30"))
                get_market_watcher().start(interval_seconds=interval_minutes * 60)
                logger.info(f"[assistant] market watcher enabled, interval={interval_minutes}m")
            except Exception:
                logger.exception("[assistant] market watcher failed to start - continuing without it")

        self.capability_isolation = None
        try:
            from security.capability_isolation import get_capability_isolation

            self.capability_isolation = get_capability_isolation()
            logger.info(
                "[assistant] capability_isolation connected (active profile: %s)",
                self.capability_isolation.get_active_profile(),
            )
        except Exception:
            logger.exception("[assistant] capability_isolation unavailable - continuing without it")

        # P2: Evidence Ledger & Confidence Tracking, Failure Pattern
        # Learning Engine. Same best-effort/always-on wiring as the P1
        # block above.
        self.evidence_ledger = None
        try:
            from intelligence.evidence_ledger import get_evidence_ledger

            self.evidence_ledger = get_evidence_ledger()
            logger.info("[assistant] evidence_ledger connected")
        except Exception:
            logger.exception("[assistant] evidence_ledger unavailable - continuing without it")

        self.failure_pattern_engine = None
        try:
            from learning_engine.failure_pattern_engine import get_failure_pattern_engine

            self.failure_pattern_engine = get_failure_pattern_engine()
            logger.info("[assistant] failure_pattern_engine connected")
        except Exception:
            logger.exception("[assistant] failure_pattern_engine unavailable - continuing without it")

        # Phase 30 follow-up: intelligence/conversation_layer/ (Phase 20)
        # was fully built - turn-by-turn history, emotional tone detection -
        # but its own docstring says "nothing in Phase 1-19.9 imports from
        # here"; it was never actually connected to the live chat loop.
        # reference_resolver.py is new this pass (see its own docstring) -
        # the one piece ("wahi"/"ye"/"kal wala"/"it"/"that" resolution)
        # that didn't already exist anywhere.
        #
        # Deliberately does NOT rewrite user_input before it reaches
        # _route_turn()'s 6 tiers below: tiers 1-3 (control commands,
        # slash commands, local_router's exact system-command patterns)
        # are literal pattern matches with no conversation awareness, and
        # splicing resolved-reference text into them risks breaking exact
        # matching - a new bug, not a fix. So this only *records* turn
        # history and *computes* resolution/tone (self._last_reference /
        # self._last_user_tone, logged every turn) for anything downstream
        # that wants it, same restraint as the personality-lead-in
        # comment above about never rewriting the LLM's own free-form text.
        self.conversation_layer = None
        self._session_id = None
        self._current_user_turn_id = None
        self._last_user_input = ""
        self._last_reference = None
        self._last_user_tone = None
        try:
            import uuid
            from intelligence.conversation_layer.turn_manager import get_turn_manager
            from intelligence.conversation_layer.reference_resolver import get_reference_resolver
            from intelligence.conversation_layer.emotional_tone import get_emotional_tone

            self._session_id = str(uuid.uuid4())
            self.conversation_layer = {
                "turns": get_turn_manager(),
                "references": get_reference_resolver(self._session_id),
                "tone": get_emotional_tone(),
            }
            logger.info(
                "[assistant] conversation_layer connected (turn history + reference resolution + tone detection)"
            )
        except Exception:
            logger.exception("[assistant] conversation_layer unavailable - continuing without it")
            self.conversation_layer = None

        # Deep-audit fix, item #4 (gated background-subsystem batch):
        # voice_intelligence/ (changes the core voice loop - barge-in),
        # computer_vision/ (can click/act on screen), deep_os_integration/
        # (global input hooks, driver/registry access), cross_device/
        # (opens a websocket server on the local network) are real
        # capability upgrades with reach beyond a single tool call, so each
        # gets its own env flag, off by default - same convention as
        # ULTRON_AUTONOMY_ENABLED / ULTRON_ORCHESTRATOR_ENABLED above.
        def _flag(name: str) -> bool:
            return os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "on")

        self.voice_intelligence = None
        if _flag("ULTRON_VOICE_INTELLIGENCE_ENABLED"):
            try:
                from voice_intelligence.full_duplex_engine import FullDuplexEngine

                self.voice_intelligence = FullDuplexEngine()
                logger.info("[assistant] voice_intelligence ENABLED (full_duplex_engine)")
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_VOICE_INTELLIGENCE_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] voice_intelligence OFF (set ULTRON_VOICE_INTELLIGENCE_ENABLED=true in .env to enable)"
            )

        self.computer_vision = None
        if _flag("ULTRON_COMPUTER_VISION_ENABLED"):
            try:
                from computer_vision.visual_automator import VisualAutomator

                self.computer_vision = VisualAutomator()
                logger.info("[assistant] computer_vision ENABLED (visual_automator)")
            except Exception:
                logger.exception("[assistant] ULTRON_COMPUTER_VISION_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] computer_vision OFF (set ULTRON_COMPUTER_VISION_ENABLED=true in .env to enable)")

        self.deep_os = None
        if _flag("ULTRON_DEEP_OS_INTEGRATION_ENABLED"):
            try:
                from deep_os_integration.process_inspector import ProcessInspector
                from deep_os_integration.network_monitor import NetworkMonitor
                from deep_os_integration.filesystem_watcher import FilesystemWatcher

                # Deliberately NOT starting global_hook_manager or
                # driver_controller here even when this flag is on - a
                # global input hook is a meaningfully different risk than
                # process/network/filesystem observation and deserves its
                # own explicit opt-in, not a bundled one. Start them by
                # hand from deep_os_integration.global_hook_manager /
                # driver_controller if you specifically need them.
                self.deep_os = {
                    "process_inspector": ProcessInspector(),
                    "network_monitor": NetworkMonitor(),
                    "filesystem_watcher": FilesystemWatcher(),
                }
                logger.info(
                    "[assistant] deep_os_integration ENABLED (process/network/filesystem only - "
                    "global_hook_manager and driver_controller stay opt-in by hand)"
                )
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_DEEP_OS_INTEGRATION_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] deep_os_integration OFF (set ULTRON_DEEP_OS_INTEGRATION_ENABLED=true in .env to enable)"
            )

        self.cross_device = None
        if _flag("ULTRON_CROSS_DEVICE_ENABLED"):
            try:
                from cross_device.runtime import get_cross_device

                self.cross_device = get_cross_device()
                logger.info(
                    "[assistant] cross_device ENABLED (device_manager + remote_controller + "
                    "CompanionAPI on :%s + CompanionWebSocketServer on :%s)",
                    self.cross_device["api"].port,
                    self.cross_device["ws_server"].port,
                )
            except Exception:
                logger.exception("[assistant] ULTRON_CROSS_DEVICE_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] cross_device OFF (set ULTRON_CROSS_DEVICE_ENABLED=true in .env to enable)")

        # Full-OS-integration follow-up batch: same convention as the four
        # blocks above (own env flag, off by default, failure never blocks
        # startup). networking/'s raw SSH/FTP clients are still deliberately
        # left out entirely - see ai/phase30_gated_tools.py's docstring for
        # why that one stays hand-wired only.
        self.quantum_dashboard = None
        if _flag("ULTRON_QUANTUM_DASHBOARD_ENABLED"):
            try:
                from quantum_dashboard import RealTimeMetrics, UsageAnalytics

                self.quantum_dashboard = {"metrics": RealTimeMetrics(), "usage": UsageAnalytics()}
                logger.info(
                    "[assistant] quantum_dashboard ENABLED (real_time_metrics + usage_analytics; "
                    "cognitive_load_monitor is Windows-only and stays opt-in by hand)"
                )
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_QUANTUM_DASHBOARD_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] quantum_dashboard OFF (set ULTRON_QUANTUM_DASHBOARD_ENABLED=true in .env to enable)"
            )

        self.ultron_shield = None
        if _flag("ULTRON_SHIELD_ENABLED"):
            try:
                from ultron_shield import BehaviorBiometrics, IntrusionDetector, PrivacyFilter, AuditLogger

                self.ultron_shield = {
                    "biometrics": BehaviorBiometrics(),
                    "intrusion_detector": IntrusionDetector(),
                    "privacy_filter": PrivacyFilter(),
                    "audit_logger": AuditLogger(),
                }
                logger.info(
                    "[assistant] ultron_shield ENABLED (biometrics/intrusion_detector/privacy_filter/"
                    "audit_logger; secure_enclave and sandbox_executor stay opt-in by hand)"
                )
            except Exception:
                logger.exception("[assistant] ULTRON_SHIELD_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] ultron_shield OFF (set ULTRON_SHIELD_ENABLED=true in .env to enable)")

        self.predictive_engine = None
        if _flag("ULTRON_PREDICTIVE_ENGINE_ENABLED"):
            try:
                from predictive_engine import BehaviorModeler, NextActionPredictor, ScheduleAnticipator, AnomalyDetector

                modeler = BehaviorModeler()
                self.predictive_engine = {
                    "behavior_modeler": modeler,
                    "next_action_predictor": NextActionPredictor(modeler),
                    "schedule_anticipator": ScheduleAnticipator(modeler),
                    "anomaly_detector": AnomalyDetector(modeler),
                }
                logger.info(
                    "[assistant] predictive_engine ENABLED (behavior_modeler/next_action_predictor/"
                    "schedule_anticipator/anomaly_detector)"
                )
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_PREDICTIVE_ENGINE_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] predictive_engine OFF (set ULTRON_PREDICTIVE_ENGINE_ENABLED=true in .env to enable)"
            )

        self.self_healing = None
        if _flag("ULTRON_SELF_HEALING_ENABLED"):
            try:
                from self_healing import HealthMonitor, CrashAnalyzer, AutoRecovery, DependencyChecker

                self.self_healing = {
                    "health_monitor": HealthMonitor(),
                    "crash_analyzer": CrashAnalyzer(),
                    "auto_recovery": AutoRecovery(),
                    "dependency_checker": DependencyChecker(),
                }
                logger.info(
                    "[assistant] self_healing ENABLED (health_monitor/crash_analyzer/auto_recovery/"
                    "dependency_checker; only ever acts on Ultron's own process, never anything else)"
                )
            except Exception:
                logger.exception("[assistant] ULTRON_SELF_HEALING_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] self_healing OFF (set ULTRON_SELF_HEALING_ENABLED=true in .env to enable)")

        self.skill_creator = None
        if _flag("ULTRON_SKILL_CREATOR_ENABLED"):
            try:
                from skill_creator import (
                    SkillCodeGenerator,
                    SandboxTester,
                    SkillValidator,
                    AutoDeployer,
                    SkillMarketplace,
                )

                deployer = AutoDeployer()
                self.skill_creator = {
                    "generator": SkillCodeGenerator(),
                    "sandbox_tester": SandboxTester(),
                    "validator": SkillValidator(),
                    "deployer": deployer,
                    "marketplace": SkillMarketplace(deployer),
                }
                logger.info(
                    "[assistant] skill_creator ENABLED (generate -> sandbox-test -> validate -> deploy "
                    "pipeline; marketplace installs still require your explicit confirmation each time)"
                )
            except Exception:
                logger.exception("[assistant] ULTRON_SKILL_CREATOR_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] skill_creator OFF (set ULTRON_SKILL_CREATOR_ENABLED=true in .env to enable)")

        self.multi_agent_swarm = None
        if _flag("ULTRON_MULTI_AGENT_SWARM_ENABLED"):
            try:
                from multi_agent_swarm import get_orchestrator

                self.multi_agent_swarm = {"orchestrator": get_orchestrator()}
                logger.info(
                    "[assistant] multi_agent_swarm ENABLED (agent_orchestrator - splits/reviews "
                    "requests across the specialist agents)"
                )
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_MULTI_AGENT_SWARM_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] multi_agent_swarm OFF (set ULTRON_MULTI_AGENT_SWARM_ENABLED=true in .env to enable)"
            )

        self.adaptive_ui = None
        if _flag("ULTRON_ADAPTIVE_UI_ENABLED"):
            try:
                from adaptive_ui.generative_ui_builder import build_panel
                from adaptive_ui.context_aware_dashboard import ContextAwareDashboard

                self.adaptive_ui = {
                    "build_panel": build_panel,
                    "context_aware_dashboard": ContextAwareDashboard(),
                }
                logger.info(
                    "[assistant] adaptive_ui ENABLED (generative_ui_builder + context_aware_dashboard; "
                    "gesture_controller needs computer_vision's gesture recognizer and stays opt-in by hand)"
                )
            except Exception:
                logger.exception("[assistant] ULTRON_ADAPTIVE_UI_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] adaptive_ui OFF (set ULTRON_ADAPTIVE_UI_ENABLED=true in .env to enable)")

        # Standalone cognitive layer (intelligence/decision_engine.py,
        # goal_planner.py, intent_analyzer.py, reasoning_engine.py,
        # self_critique.py, verification_engine.py, model_trainer.py) -
        # separate from intelligence.conversation_layer used above. Was
        # never imported anywhere. Same convention as the blocks above.
        self.cognitive_layer = None
        if _flag("ULTRON_COGNITIVE_LAYER_ENABLED"):
            try:
                from intelligence.decision_engine import DecisionEngine
                from intelligence.goal_planner import GoalPlanner
                from intelligence.intent_analyzer import IntentAnalyzer
                from intelligence.reasoning_engine import CognitiveReasoningEngine
                from intelligence.self_critique import SelfCritique
                from intelligence.verification_engine import ReasoningVerificationEngine
                from intelligence.model_trainer import ModelTrainer

                self.cognitive_layer = {
                    "decision_engine": DecisionEngine(),
                    "goal_planner": GoalPlanner(),
                    "intent_analyzer": IntentAnalyzer(),
                    "reasoning_engine": CognitiveReasoningEngine(),
                    "self_critique": SelfCritique(),
                    "verification_engine": ReasoningVerificationEngine(),
                    "model_trainer": ModelTrainer(),
                }
                logger.info(
                    "[assistant] cognitive_layer ENABLED (decision_engine/goal_planner/intent_analyzer/"
                    "reasoning_engine/self_critique/verification_engine/model_trainer)"
                )
            except Exception:
                logger.exception("[assistant] ULTRON_COGNITIVE_LAYER_ENABLED was set but failed to load - staying off")
        else:
            logger.info("[assistant] cognitive_layer OFF (set ULTRON_COGNITIVE_LAYER_ENABLED=true in .env to enable)")

        # Specialist agents/*.py (coder, browser_agent, vision_agent,
        # windows_agent, memory_agent, automation_agent) - distinct from
        # multi_agent_swarm's own internal agent concept above, which
        # never touches this package. Were never imported anywhere.
        self.specialist_agents = None
        if _flag("ULTRON_SPECIALIST_AGENTS_ENABLED"):
            try:
                from agents.coder import get_coder
                from agents.browser_agent import BrowserAgent
                from agents.vision_agent import VisionAgent
                from agents.windows_agent import WindowsAgent
                from agents.memory_agent import MemoryAgent
                from agents.automation_agent import AutomationAgent

                self.specialist_agents = {
                    "coder": get_coder(),
                    "browser": BrowserAgent(),
                    "vision": VisionAgent(),
                    "windows": WindowsAgent(),
                    "memory": MemoryAgent(),
                    "automation": AutomationAgent(),
                }
                logger.info("[assistant] specialist_agents ENABLED (coder/browser/vision/windows/memory/automation)")
            except Exception:
                logger.exception(
                    "[assistant] ULTRON_SPECIALIST_AGENTS_ENABLED was set but failed to load - staying off"
                )
        else:
            logger.info(
                "[assistant] specialist_agents OFF (set ULTRON_SPECIALIST_AGENTS_ENABLED=true in .env to enable)"
            )

        # Background tasks (core.task_queue, driven by core.intent_router's
        # "... in the background" handling) finish off the main input loop,
        # so announce them here instead of leaving the result unspoken.
        bus = get_event_bus()
        bus.subscribe("task_completed", self._on_background_task_done)
        bus.subscribe("task_failed", self._on_background_task_done)
        bus.subscribe("response_ready", self._on_conversation_response_ready)

        # Deep-scan auto-wiring: every previously-unwired module found in
        # the audit gets loaded here. Safe modules (no shell/registry/
        # network/credential/hook footprint) load by default; unsafe
        # modules (real system-control power) only load if the user has
        # explicitly opted in via ULTRON_UNSAFE_MODULES_ENABLED=true in
        # .env - each flag controlled independently, each module loaded
        # in its own try/except so nothing here can block startup.
        self.full_registry = None
        try:
            from core.full_module_registry import wire_all_modules

            self.full_registry = wire_all_modules()
        except Exception:
            logger.exception("[assistant] full_module_registry failed to load - continuing without it")

    def _on_conversation_response_ready(self, text: str = "", **kwargs):
        """Closes out conversation_layer/learning_engine bookkeeping for
        this turn. Subscribed to 'response_ready', which every one of
        _route_turn's 6 reply paths already emits - so this needs no
        changes to _route_turn itself, same reasoning as
        _on_background_task_done above."""
        if self.conversation_layer is not None and self._session_id is not None:
            try:
                from intelligence.conversation_layer.turn_manager import SPEAKER_ASSISTANT, TURN_TYPE_TEXT

                turns = self.conversation_layer["turns"]
                if self._current_user_turn_id is not None:
                    turns.end_turn(self._current_user_turn_id, text=self._last_user_input or "")
                    self._current_user_turn_id = None
                reply_turn = turns.start_turn(self._session_id, SPEAKER_ASSISTANT, TURN_TYPE_TEXT)
                turns.end_turn(reply_turn["turn_id"], text=text or "")
            except Exception:
                logger.exception("[assistant] conversation_layer turn-close failed")

        if self.learning_engine is not None:
            try:
                # Rough proxies, not a real NLU signal - a long question
                # doesn't necessarily mean a long answer is wanted, this
                # is deliberately a weak EMA-smoothed nudge (see
                # learning_engine/user_adaptation.py's own docstring on
                # why one interaction never swings the profile far).
                user_text = self._last_user_input or ""
                word_count = len(user_text.split())
                verbosity_signal = min(1.0, word_count / 30.0)
                formal_markers = sum(
                    1 for w in ("please", "kindly", "would you", "could you", "aap", "sir") if w in user_text.lower()
                )
                formality_signal = min(1.0, 0.35 + 0.15 * formal_markers)
                self.learning_engine["adaptation"].observe("verbosity", verbosity_signal)
                self.learning_engine["adaptation"].observe("formality", formality_signal)
            except Exception:
                logger.exception("[assistant] learning_engine.observe failed")

    def _on_background_task_done(self, task_id: str, label: str, result=None, error=None):
        detail = f"Background task '{label}' failed: {error}" if error else f"Background task '{label}' is done."
        text = self._personality_lead_in("general_concern" if error else "general_ack", detail)
        print(f"\n{C.BLUE}ULTRON:{C.RESET} {text}")
        self.speak_reply(text)
        self._note_outcome(satisfied=not error, detail=label if error else "")

    # -- Phase 18.1 observer layer helpers --------------------------------
    def _personality_lead_in(self, category: str, detail: str) -> str:
        """Prefix `detail` with a short personality-flavored lead-in line
        for `category` when the observer layer is available, otherwise
        just return `detail` unchanged - this is purely cosmetic, never
        required for correctness, so any failure here is swallowed and
        the caller still gets its message."""
        if self.personality is None:
            return detail
        try:
            lead_in = self.personality.speak(category)["text"]
            return f"{lead_in} {detail}"
        except Exception:
            logger.exception("[assistant] personality.speak failed - using plain text")
            return detail

    def _note_outcome(self, satisfied: bool, detail: str = ""):
        """Best-effort report of a turn's/task's outcome back to
        consciousness.py's trailing confidence score. Never raises."""
        if self.consciousness is None:
            return
        try:
            self.consciousness.note_outcome(satisfied, detail=detail)
        except Exception:
            logger.exception("[assistant] consciousness.note_outcome failed")
        if self.advanced_autonomy is not None:
            try:
                self.advanced_autonomy.learn_outcome(
                    action_name="conversation_turn",
                    success=satisfied,
                    context={"detail": detail},
                    error=None if satisfied else (detail or "turn not satisfied"),
                )
            except Exception:
                logger.exception("[assistant] advanced autonomy outcome learning failed")

    def _response_for_decision(self, decision: dict) -> str:
        """Turn a decision_maker.decide_and_execute() result into the text
        actually shown/spoken to the user. Mirrors
        core.brain_p18.Ultron._response_for_goal_outcome,
        reimplemented here (rather than calling get_ultron()) so this
        doesn't also re-run Ultron.think()'s own redundant "delegate"
        branch - _route_turn() already owns that fallthrough."""
        route = decision["route"]
        if route == "clarify":
            return (
                decision.get("clarify_question")
                or f"Could you say a bit more about what you mean by \"{decision.get('goal', 'that')}\"?"
            )

        outcome = decision.get("outcome", {})
        goal = decision.get("goal", "")
        if "error" in outcome:
            return self._personality_lead_in("general_concern", f"I ran into trouble on \"{goal}\": {outcome['error']}")
        if outcome.get("satisfied"):
            return self._personality_lead_in("general_ack", f'Done - "{goal}" looks achieved.')
        reason = outcome.get("stopped_reason") or "couldn't fully confirm it worked"
        return self._personality_lead_in("general_concern", f'I made progress on "{goal}" but {reason}.')

    def _start_proactive_alerts(self, poll_seconds: float = 60.0):
        try:
            from proactive.triggers.threshold_alerts import get_threshold_alerts
            from ui.notifications import notify
        except Exception:
            logger.info("[assistant] proactive threshold alerts unavailable - continuing without them")
            return

        alerts = get_threshold_alerts()

        def _loop():
            while True:
                try:
                    for event in alerts.check():
                        category = event["category"]
                        kwargs = event.get("kwargs", {})
                        if self.personality is not None:
                            phrase = self.personality.speak(category, **kwargs)
                        else:
                            from proactive.personality.tone_manager import get_tone_manager

                            phrase = get_tone_manager().get_phrase(category, **kwargs)
                        notify(
                            title=category.replace("_", " ").title(),
                            message=phrase["text"],
                            level=phrase["level"],
                            source="proactive.threshold_alerts",
                        )
                        print(f"\n{C.YELLOW}ULTRON (proactive):{C.RESET} {phrase['text']}")
                        self.speak_reply(phrase["text"])
                except Exception:
                    logger.exception("[assistant] proactive threshold alert tick failed")
                time.sleep(poll_seconds)

        threading.Thread(target=_loop, daemon=True, name="proactive-threshold-alerts").start()
        logger.info("[assistant] proactive threshold alerts started (poll every %ss)", poll_seconds)

    # -- Phase 19.1-20.6 intelligence layer hooks -------------------------
    def _intel_log_turn(self, user_input: str):
        """Fire-and-forget: run the full intelligence pipeline (world
        state capture, intent classification, confidence scoring,
        knowledge lookup, goal planning, proactive/predictive checks)
        for this turn and persist it to database/*.db. Runs in a
        background thread so an unavailable or slow intelligence layer
        never adds latency to the actual reply - this is purely for
        world-state/history tracking, never gates what Ultron says."""
        if self.intelligence is None:
            return

        def _run():
            try:
                # Advanced autonomy keeps a fresh world snapshot alongside
                # the existing intelligence turn log. This is observation
                # only; it never executes an action from the background.
                if self.advanced_autonomy is not None:
                    self.advanced_autonomy.observe(reason="conversation_turn")
                self.intelligence.process_turn(user_input)
            except Exception:
                logger.exception("[assistant] intelligence.process_turn failed")

        threading.Thread(target=_run, daemon=True, name="intel-log-turn").start()

    def _intel_record_call(
        self, operation: str, provider: str, latency_ms: float, success: bool = True, error: Optional[str] = None
    ):
        """Best-effort: report a real AI provider call's outcome back to
        the intelligence layer - feeds adaptive_performance (routing/
        caching decisions) and, on failure, self_healing (diagnosis).
        Never raises, never blocks the reply."""
        if self.intelligence is None:
            return
        try:
            self.intelligence.record_provider_call(operation, provider, latency_ms, success=success, error=error)
        except Exception:
            logger.exception("[assistant] intelligence.record_provider_call failed")

    # -- speaking --------------------------------------------------------
    def speak_reply(self, text: str):
        """Speak `text` unless voice isn't set up for this mode, or the
        user has toggled silent mode on. Only a trimmed, sentence-complete
        version is actually spoken (see _spoken_version/SPEAK_MAX_CHARS) -
        the full text is still what gets printed to the console/UI by the
        caller, this only shortens what comes out of the speakers."""
        if not text or self.voice is None or self.silent_mode:
            return
        bus = get_event_bus()
        bus.emit("speaking_start")
        self.voice.speak(_spoken_version(text))
        bus.emit("speaking_end")

    # -- "normal" tier of the complexity pipeline -------------------------
    def _handle_fast_tier(self, user_input: str) -> bool:
        """ai/complexity_router.py's "normal" tier: a small, tool-free
        model whose reply is streamed straight into TTS as it generates,
        instead of waiting for the full text like the strong-model path
        below does. The terminal print is now streamed the same way -
        each chunk hits stdout the instant it's generated, alongside
        (not after) speech, instead of the old behaviour of only
        printing once the whole reply had already been spoken. Only
        used for turns the complexity router judged unlikely to need a
        tool at all.

        Returns True once something was actually said/printed for this
        turn. Returns False - having said nothing - if the fast tier
        produced no text whatsoever (fast tier unavailable: offline,
        AI_MODE=local, or Groq not configured; or a stream that failed
        before yielding anything), so the caller falls straight through
        to the exact same full pipeline it would have used before this
        tier existed. A stream that starts producing text and then fails
        partway is accepted as a partial answer rather than falling
        through a second time, since replaying the same turn on the full
        model at that point would speak the answer twice.
        """
        if not hasattr(self.client, "chat_fast_stream"):
            return False

        bus = get_event_bus()
        chunks = []
        first = True

        def _tee():
            nonlocal first
            try:
                for piece in self.client.chat_fast_stream(user_input):
                    if piece:
                        if first:
                            perf_trace.mark("T5_first_output")
                            first = False
                            # Live streaming print starts here, in step
                            # with the first chunk TTS also receives -
                            # this is genuinely raw model output (no
                            # _strip_asterisks pass), the same trade-off
                            # every token-streamed terminal UI makes, so
                            # a literal "**" can flash by mid-stream.
                            print(f"\n{C.BLUE}ULTRON:{C.RESET} ", end="", flush=True)
                        chunks.append(piece)
                        print(piece, end="", flush=True)
                        yield piece
            except Exception as e:
                logger.info("Fast-tier stream interrupted: %s", e)

        bus.emit("thinking_start", text=user_input)
        perf_trace.mark("T4_request_start")

        if self.voice is not None and not self.silent_mode:
            bus.emit("speaking_start")
            self.voice.speak_stream(_tee())
            bus.emit("speaking_end")
        else:
            for _ in _tee():
                pass

        response = "".join(chunks).strip()
        if not response:
            return False

        print()  # close out the streamed line before anything else logs
        response = _strip_asterisks(response)
        bus.emit("response_ready", text=response)
        return True

    # -- mode toggles (driven by voice command or CLI flags) -------------
    def enable_ui(self):
        if self.ui_enabled:
            return
        self.ui_enabled = True
        try:
            from ui.orb.orb import open_orb

            open_orb()
            print(f"{C.CYAN}UI mode on - voice orb opened.{C.RESET}")
        except Exception as e:
            print(f"{C.YELLOW}UI unavailable: {e}{C.RESET}")

    def disable_ui(self):
        if not self.ui_enabled:
            return
        self.ui_enabled = False
        try:
            from ui.orb.orb import close_orb

            close_orb()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.assistant.disable_ui")
        print(f"{C.CYAN}UI mode off.{C.RESET}")

    def open_dashboard(self):
        """Open the live web dashboard (CPU/RAM + real-time conversation
        feed) in the default browser - see ui/web_dashboard/app.py. Safe
        to call repeatedly: the server only actually starts once, later
        calls just (re)open the browser tab.

        Passes `self` through so the dashboard's command box (typed
        commands from the browser, not just voice/tray) can call this
        same live Assistant's handle_command() - the one already holding
        conversation history/context - instead of building a second,
        disconnected instance."""
        try:
            from ui.web_dashboard.app import start_dashboard

            start_dashboard(assistant=self)
            print(f"{C.CYAN}Dashboard opened in your browser.{C.RESET}")
        except Exception as e:
            print(f"{C.YELLOW}Dashboard unavailable: {e}{C.RESET}")

    def enable_text_mode(self):
        if self.text_mode_enabled:
            return
        self.text_mode_enabled = True
        print(f"{C.CYAN}Text mode on - you can now type commands too (Enter to send).{C.RESET}")
        if self._text_thread is None or not self._text_thread.is_alive():
            self._text_thread = threading.Thread(target=self._text_input_loop, daemon=True)
            self._text_thread.start()

    def disable_text_mode(self):
        if not self.text_mode_enabled:
            return
        self.text_mode_enabled = False
        print(f"{C.CYAN}Text mode off.{C.RESET}")

    def _text_input_loop(self):
        """Background stdin reader for typed input, active only while
        text_mode_enabled is True. Runs alongside the wake-word mic loop
        on the main thread - stdin and the microphone don't contend."""
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                return
            if not self.text_mode_enabled:
                continue
            line = line.strip()
            if line:
                print(f"{C.GREEN}You (typed):{C.RESET} {line}")
                self.handle_command(line)

    def _apply_action(self, action: str):
        if action == "ui_on":
            self.enable_ui()
        elif action == "ui_off":
            self.disable_ui()
        elif action == "dashboard_on":
            self.open_dashboard()
        elif action == "text_on":
            self.enable_text_mode()
        elif action == "text_off":
            self.disable_text_mode()
        elif action == "silent_on":
            self.silent_mode = True
            print(f"{C.CYAN}Silent mode on - I'll reply in text only.{C.RESET}")
        elif action == "silent_off":
            self.silent_mode = False
            print(f"{C.CYAN}Silent mode off.{C.RESET}")
            self.speak_reply("Voice responses are back on, Sir.")
        elif action == "stop":
            if self.voice:
                self.voice.stop()
            print(f"{C.DIM}[stopped]{C.RESET}")
        elif action == "auto_safe_on":
            from core.control_mode import set_safe_control_override

            set_safe_control_override(True)
            print(
                f"{C.CYAN}Auto mode on - non-destructive actions run without asking for the rest of this session.{C.RESET}"
            )
            self.speak_reply(
                "Auto mode on, Sir. I'll go ahead with the everyday stuff myself now - "
                "opening apps, adjusting settings, that kind of thing. Anything destructive, "
                "like deleting something or shutting the PC down, I'll still check with you first."
            )
        elif action == "auto_safe_off":
            from core.control_mode import set_safe_control_override

            set_safe_control_override(False)
            print(f"{C.CYAN}Auto mode off - back to asking/learning-based trust as usual.{C.RESET}")
            self.speak_reply("Auto mode off, Sir. Back to normal.")

    # -- the single place every mode routes user input through -----------
    def handle_message(self, text: str, session_id: str | None = None) -> str:
        """UI-facing entry point (ui/bridge.py -> mobile API / web_ui /
        voice_ui). handle_command() below is built for the interactive
        console loop: it prints and speaks the reply as a side effect and
        returns None, which is fine for run_text()/run_listen() but useless
        to a caller (like a Flask route) that needs the reply *text* back
        to put in a JSON response.

        Rather than touch _route_turn()'s several return points (6-tier
        pipeline, each ending in its own print/speak call), this hooks the
        one thing already common to every one of them: the
        "response_ready" event_bus emission that happens right before each
        print/speak. _route_turn() emits on the *legacy* bus
        (core.events.get_event_bus - see the module-level import at the
        top of this file), not core.event_bus's newer one, so this
        subscribes to that same legacy bus - subscribing to the wrong one
        silently misses every emission instead of erroring, which is
        exactly the bug an earlier version of this method had.

        The lock serializes concurrent calls on this one Assistant
        instance so two overlapping requests (e.g. two quick mobile taps)
        can't capture each other's reply text. Flask's dev server is
        single-process here, so this is enough for the "dev/stopgap" use
        this bridge already documents itself as - a real multi-worker
        deployment would need one Assistant per worker or a queue instead.
        """
        from core.events import get_event_bus

        captured: list[str] = []

        def _capture(text: str = "", **_kwargs):
            captured.append(text)

        with self._handle_message_lock:
            bus = get_event_bus()
            bus.subscribe("response_ready", _capture)
            try:
                self.handle_command(text)
            finally:
                # core.events.EventBus (the legacy bus _route_turn actually
                # emits on) has no unsubscribe() method - only subscribe()/
                # emit() (see core/events.py). Removing directly from its
                # internal _subscribers list is the only way to avoid
                # leaving a dead _capture closure attached forever (a new
                # one gets added on every handle_message() call otherwise -
                # a real leak for a long-running mobile-API process).
                handlers = bus._subscribers.get("response_ready", [])
                if _capture in handlers:
                    handlers.remove(_capture)

        if captured:
            return captured[-1]
        # No response_ready fired - e.g. a control command with no reply
        # text, or the "exit/quit/bye" branch (which calls sys.exit()
        # before this would ever return anyway).
        return "(no reply text was generated for that command)"

    def get_history(self, session_id: str | None = None) -> list[dict]:
        """UI-facing history read (ui/bridge.py). Delegates to the LLM
        client's own history - core.brain.get_brain() returns an AIRouter,
        and AIRouter.get_history()/.clear_history() are the existing
        single-session conversation log (see core/brain.py). session_id
        is accepted for interface-compatibility with bridge.py's
        multi-session stub but is not itself used to key separate
        histories - this Assistant, like the console/voice modes it was
        built for, holds one ongoing conversation, not one per session_id.
        """
        get_hist = getattr(self.client, "get_history", None)
        if callable(get_hist):
            try:
                return get_hist()
            except Exception:
                logger.exception("[assistant] client.get_history() failed")
        return []

    def handle_command(self, user_input: str):
        # Local imports (not module-level) to avoid a circular import:
        # ai.local_router pulls in core.executor, and core.intent_router
        # is a core/ sibling - both are safe as function-local imports
        # here since core/assistant.py itself must stay importable from
        # core/startup.py and core/debug_console.py without pulling in
        # everything those modules touch.
        from ai import local_router
        from core import intent_router

        if not user_input:
            return

        # ensure_turn(), not start_turn(): run_listen's on_wake already
        # started a turn (T0/T1/T2) for voice input by the time this
        # runs - only start a fresh one here for callers that reach
        # handle_command() directly (typed/text mode, UI, tests) without
        # ever going through the wake-word path.
        perf_trace.ensure_turn()
        try:
            self._handle_command_inner(user_input, local_router, intent_router)
        finally:
            perf_trace.mark("T7_done")
            perf_trace.summary()

    def _handle_command_inner(self, user_input: str, local_router, intent_router):
        # Phase 19.1-20.6 intelligence layer: log this turn (world state,
        # intent, confidence, knowledge, goals, proactive/predictive) in
        # the background - see _intel_log_turn(). Every real user turn
        # reaching handle_command() goes through here, control-command
        # toggles and slash-commands included, so world_state/conversation
        # history reflect everything asked, not just Groq round-trips.
        self._intel_log_turn(user_input)

        # Normalize away a leading wake-word address ("hi ultron", "hey
        # ultron", "ultron,", ...) once, up front, for every downstream
        # consumer (control commands, local_router, intent_router,
        # complexity_router, and the actual LLM call/history). Voice mode
        # (run_listen's on_wake) already only ever hands this function the
        # *remainder* after the wake word - this just gives typed input
        # (run_text/run_voice_typed) the same clean behavior, so someone
        # typing "hi ultron, cpu kitna use ho raha hai" out of habit gets
        # treated identically to just typing "cpu kitna use ho raha hai"
        # instead of the leading "hi" risking being misread as the whole
        # message being casual chat.
        user_input = local_router.strip_wake_prefix(user_input)

        # Phase 30 follow-up: record this turn + compute reference
        # resolution/tone (see the conversation_layer block in __init__
        # for why this only computes/logs rather than rewriting
        # user_input). Best-effort, never blocks routing.
        self._last_user_input = user_input
        if self.conversation_layer is not None and self._session_id is not None:
            try:
                from intelligence.conversation_layer.turn_manager import SPEAKER_USER, TURN_TYPE_TEXT

                turn = self.conversation_layer["turns"].start_turn(self._session_id, SPEAKER_USER, TURN_TYPE_TEXT)
                self._current_user_turn_id = turn["turn_id"]

                ref = self.conversation_layer["references"].resolve(user_input)
                self._last_reference = ref
                if ref.referenced:
                    logger.info(
                        "[assistant] reference resolved (confidence=%.2f): %r -> %r",
                        ref.confidence,
                        user_input,
                        ref.resolved_text,
                    )

                self._last_user_tone = self.conversation_layer["tone"].detect(user_input)
            except Exception:
                logger.exception("[assistant] conversation_layer turn-start/reference-resolve failed - continuing")

        if self.consciousness is not None:
            try:
                self.consciousness.push_focus(user_input, source="user_turn")
            except Exception:
                logger.exception("[assistant] consciousness.push_focus failed")
        try:
            self._route_turn(user_input, local_router, intent_router)
        finally:
            if self.consciousness is not None:
                try:
                    self.consciousness.pop_focus()
                except Exception:
                    logger.exception("[assistant] consciousness.pop_focus failed")

    def _route_turn(self, user_input: str, local_router, intent_router):
        """The 6-tier routing pipeline itself - unchanged from before the
        Phase 18 observer layer, just pulled into its own method so
        _handle_command_inner() can wrap it in a single push_focus/
        pop_focus pair above without duplicating that wrapping at every
        one of this method's several return points."""
        if user_input.strip().lower() in ("exit", "quit", "bye"):
            goodbye = "Goodbye, Sir."
            print(f"\n{C.BLUE}ULTRON:{C.RESET} {goodbye}")
            self.speak_reply(goodbye)
            if self.detector:
                self.detector.stop()
            from core.shutdown import graceful_shutdown

            graceful_shutdown(self)
            sys.exit(0)

        # 1) Control commands - mode toggles / interrupt. Never touches the
        #    LLM; these change how Ultron itself behaves.
        action = local_router.check_control_command(user_input)
        if action:
            self._apply_action(action)
            self._note_outcome(satisfied=True)
            return

        # 2) Slash commands (/help, /reset, /time, ...). Only actually a
        #    command if it starts with '/' - otherwise plain sentences
        #    that happen to start with a command word (e.g. "open notepad",
        #    "search for cats") would get swallowed here instead of
        #    reaching the smart router / LLM below.
        is_cmd, cmd_response = (
            self.processor.process(user_input) if self.processor.is_command(user_input) else (False, None)
        )
        if is_cmd:
            if cmd_response:
                cmd_response = _strip_asterisks(cmd_response)
                print(f"\n{C.BLUE}ULTRON:{C.RESET} {cmd_response}")
                self.speak_reply(cmd_response)
            self._note_outcome(satisfied=True)
            return

        # 3) Smart router: simple, unambiguous system commands answered
        #    locally (no Groq round-trip) - time/date/volume/open app/etc.
        local_result = local_router.route_system_command(user_input)
        if local_result and local_result.handled_locally:
            # Simple tier: decision and execution are the same call
            # here (route_system_command both decides *and* runs the
            # command), so T3/T4/T5 all land at this one instant -
            # accurately reflecting that there's no separate AI step on
            # this path at all.
            perf_trace.mark("T3_decision")
            perf_trace.mark("T4_request_start")
            perf_trace.mark("T5_first_output")
            local_result.response = _strip_asterisks(local_result.response)
            print(f"\n{C.BLUE}ULTRON:{C.RESET} {local_result.response}")
            get_event_bus().emit("response_ready", text=local_result.response)
            self.speak_reply(local_result.response)
            self._note_outcome(satisfied=True)
            return

        # 4) Everything else - real questions, multi-step tasks, anything
        #    needing reasoning or tool-chaining - goes to Groq.
        bus = get_event_bus()

        def on_tool(name, args):
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            print(f"\n{C.MAGENTA}[tool] {name}({args_str}){C.RESET}")
            bus.emit("tool_executed", name=name, args_str=args_str)

        # 3.5) Intent router: named workflows ("run my morning routine"),
        #      background tasks ("... in the background"), and background
        #      task status/listing are handled here without a blocking
        #      Groq round-trip on the main thread. Anything it doesn't
        #      recognize falls straight through to step 4 unchanged.
        #      classify() (as opposed to route()) is side-effect-free, so
        #      it's safe to peek at here before deciding whether the
        #      complexity router even gets a turn below. route() also
        #      checks the user's own custom voice-command shortcuts
        #      (voice/voice_commands.py) before its built-in patterns, so
        #      that has to be peeked at too (via the non-executing
        #      .match(), not .execute_if_matched()) or a registered
        #      shortcut could get silently answered by the fast tier
        #      instead of actually running.
        structural = intent_router.classify(user_input)
        has_voice_command = False
        try:
            from voice.voice_commands import get_voice_command_registry

            has_voice_command = get_voice_command_registry().match(user_input) is not None
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.assistant._route_turn")
        if structural.intent == "chat" and not has_voice_command:
            # 3.55) Phase 18 goal-decision layer (off by default - see
            #       ULTRON_AUTONOMY_ENABLED in Assistant.__init__). Only
            #       ever triggered by explicit "goal: ..."/"handle X end
            #       to end"/"X khud se kar do" phrasing
            #       (intent_resolver.GOAL_PATTERNS) - decision_maker.decide()
            #       internally re-runs the same classification this tier's
            #       `structural` already used and returns "delegate" for
            #       anything that isn't that narrow phrasing, so ordinary
            #       chat always falls straight through to 3.6/4 below
            #       exactly as it did before this layer existed.
            if self.decision_maker is not None:
                # Phase 30: same GOAL-shaped requests decision_maker already
                # detects can now optionally go to core/orchestrator.py's
                # fuller plan->execute->verify->heal->approve loop instead
                # of cognitive_core.autonomous_executor - but only for the
                # "goal_full" (multi-step) route, and only when explicitly
                # opted into via ULTRON_ORCHESTRATOR_ENABLED, so default
                # behavior for anyone not on this flag is byte-for-byte
                # the same as before this block existed. decide() itself
                # is documented side-effect-free (see its own docstring),
                # so peeking at the route here before deciding which
                # executor to hand the goal to is safe to do without
                # duplicating any of decide_and_execute's bookkeeping.
                # Deep-audit fix: default flipped false->true now that
                # core/workflow_engine.py routes every step through
                # ai.tool_runtime.execute_tool_from_dict's ActionPipeline
                # gate (see that file's fix) - the reason this was off by
                # default (autonomous steps could bypass permission
                # checks) no longer applies. Still overridable via env
                # var for anyone who wants it off.
                orchestrator_enabled = os.getenv("ULTRON_ORCHESTRATOR_ENABLED", "true").lower() == "true"
                decision = None
                if orchestrator_enabled:
                    try:
                        peek = self.decision_maker.decide(user_input)
                    except Exception:
                        logger.exception(
                            "[assistant] decision_maker.decide (orchestrator peek) failed - falling through"
                        )
                        peek = None
                    if peek is not None and peek["route"] == "goal_full":
                        try:
                            from core.orchestrator import get_orchestrator

                            if self.consciousness is not None:
                                self.consciousness.push_focus(peek["goal"], source="orchestrator")
                            try:
                                run_result = get_orchestrator().run_goal(peek["goal"], source="user")
                            finally:
                                if self.consciousness is not None:
                                    self.consciousness.pop_focus()
                            self._note_outcome(
                                satisfied=run_result.get("success", False),
                                detail=peek["goal"] if not run_result.get("success") else "",
                            )
                            decision = {"route": "goal_orchestrated", "goal": peek["goal"], "outcome": run_result}
                        except Exception:
                            logger.exception(
                                "[assistant] orchestrator.run_goal failed - falling through to decision_maker"
                            )
                            decision = None

                if decision is not None and decision["route"] == "goal_orchestrated":
                    outcome = decision["outcome"]
                    step_count = outcome.get("steps_run", 0)
                    if outcome.get("success"):
                        response = f"Done, Sir. Completed the goal in {step_count} step(s)."
                    else:
                        response = (
                            f"I got partway through, Sir - {step_count} step(s) run, "
                            f"but couldn't fully finish: {peek['goal']}."
                        )
                    print(f"\n{C.BLUE}ULTRON:{C.RESET} {response}")
                    bus_ref = get_event_bus()
                    bus_ref.emit("response_ready", text=response)
                    self.speak_reply(response)
                    return

                try:
                    if decision is None:
                        decision = self.decision_maker.decide_and_execute(user_input)
                except Exception:
                    logger.exception(
                        "[assistant] decision_maker.decide_and_execute failed - falling through to normal pipeline"
                    )
                    decision = None
                if decision is not None and decision["route"] != "delegate":
                    perf_trace.mark("T3_decision")
                    perf_trace.mark("T4_request_start")
                    perf_trace.mark("T5_first_output")
                    response = _strip_asterisks(self._response_for_decision(decision))
                    print(f"\n{C.BLUE}ULTRON:{C.RESET} {response}")
                    bus.emit("response_ready", text=response)
                    self.speak_reply(response)
                    if decision["route"] != "clarify":
                        self._note_outcome(
                            satisfied=decision.get("outcome", {}).get("satisfied", False),
                            detail=decision.get("goal", ""),
                        )
                    return

            # 3.6) Complexity router ("normal" tier): quick, tool-free
            #      turns get answered by a small fast-streamed model
            #      instead of the full tool-calling loop below. Anything
            #      it can't confidently call "normal", or that produces no
            #      usable reply, falls straight through to step 4 exactly
            #      as if this tier didn't exist.
            from ai import complexity_router

            if complexity_router.classify(user_input) == "normal":
                perf_trace.mark("T3_decision")
                if self._handle_fast_tier(user_input):
                    self._note_outcome(satisfied=True)
                    return
                # Fast tier attempted and produced nothing - falling
                # through to the full pipeline below. T3/T4/T5 marks
                # from that abandoned attempt (set inside
                # _handle_fast_tier) are left as-is rather than
                # overwritten, since mark() only records a stage's
                # first occurrence per turn; this is a known minor
                # inaccuracy on this rare fallback path only, not the
                # common case.

        intent_result = intent_router.route(user_input, chat_fn=lambda goal: self.client.chat_with_tools(goal, on_tool))
        if intent_result.handled_locally:
            perf_trace.mark("T3_decision")
            perf_trace.mark("T4_request_start")
            perf_trace.mark("T5_first_output")
            intent_result.response = _strip_asterisks(intent_result.response)
            print(f"\n{C.BLUE}ULTRON:{C.RESET} {intent_result.response}")
            bus.emit("response_ready", text=intent_result.response)
            self.speak_reply(intent_result.response)
            self._note_outcome(satisfied=True)
            return

        perf_trace.mark("T3_decision")
        bus.emit("thinking_start", text=user_input)
        perf_trace.mark("T4_request_start")
        _t0 = time.time()
        _err_before = getattr(self.client, "last_error", None)
        response = self.client.chat_with_tools(user_input, on_tool)
        # chat_with_tools() never raises (see ai/ai_router.py) - it
        # reports failures via self.client.last_error/mode instead, so
        # success/failure here is inferred from whether a *new* error
        # appeared during this call, not from an exception.
        _err_after = getattr(self.client, "last_error", None)
        _call_failed = _err_after is not None and _err_after != _err_before
        self._intel_record_call(
            "chat_with_tools",
            getattr(self.client, "mode", "unknown"),
            (time.time() - _t0) * 1000,
            success=not _call_failed,
            error=_err_after if _call_failed else None,
        )
        # chat_with_tools() is not token-streamed today (unlike the fast
        # tier) - T5 therefore lands at the same instant the full reply
        # became available, not a true first-token time. That gap is
        # exactly what a future "stream the strong model too" chunk
        # would close; this mark still correctly shows today's real
        # latency, it just doesn't yet show early partial output.
        perf_trace.mark("T5_first_output")
        response = _strip_asterisks(response)
        bus.emit("response_ready", text=response)
        print(f"\n{C.BLUE}ULTRON:{C.RESET} {response}")
        self.speak_reply(response)
        self._note_outcome(satisfied=not _call_failed, detail=_err_after if _call_failed else "")

    # -- run modes ---------------------------------------------------------
    def run_text(self):
        """Text-only: no mic, no TTS. `python main.py --text`."""
        print(f"\n{C.BLUE}ULTRON:{C.RESET} Good day, Sir. How may I help you?")
        while True:
            try:
                user_input = input(f"\n{C.GREEN}You:{C.RESET} ").strip()
                if not user_input:
                    continue
                self.handle_command(user_input)
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n{C.BLUE}ULTRON:{C.RESET} Goodbye, Sir.\n")
                break
            except Exception as e:
                print(f"\n{C.RED}Error: {e}{C.RESET}")

    def run_voice_typed(self):
        """Legacy 'voice mode': typed input, spoken output.
        `python main.py --voice`."""
        try:
            from voice import get_voice

            self.voice = get_voice()
        except Exception as e:
            import traceback

            print(f"{C.RED}Voice unavailable: {e}{C.RESET}")
            traceback.print_exc()
            self.run_text()
            return

        greeting = "Good day, Sir    How may I help you?"
        print(f"\n{C.BLUE}ULTRON:{C.RESET} {greeting}")
        self.speak_reply(greeting)
        print(f"\n{C.CYAN}Voice mode active. Type your commands.{C.RESET}")

        while True:
            try:
                user_input = input(f"\n{C.GREEN}You:{C.RESET} ").strip()
                if not user_input:
                    continue
                self.handle_command(user_input)
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n{C.BLUE}ULTRON:{C.RESET} Goodbye, Sir.\n")
                break
            except Exception as e:
                print(f"\n{C.RED}Error: {e}{C.RESET}")

    # Saying one of these while in the post-reply follow-up window ends
    # the conversation early and drops back to wake-word-only listening,
    # instead of waiting out the full FOLLOWUP_LISTEN_TIMEOUT.
    _SLEEP_PHRASES = (
        "go to sleep",
        "stop listening",
        "that's all",
        "thats all",
        "never mind",
        "nevermind",
        "that'll be all",
        "thats all for now",
    )

    def run_listen(self):
        """Default mode: hands-free. Wake word ('Ultron') is always
        listening; after it fires, Ultron listens for the command and
        replies by voice. After replying, it keeps listening directly
        for follow-up commands (no wake word needed) for a short window
        - see FOLLOWUP_LISTEN_TIMEOUT - before going back to wake-word-
        only listening. `python main.py` (no flags)."""
        try:
            from voice import get_voice, get_stt, get_wakeword_detector

            self.voice = get_voice()
            self.stt = get_stt()
            self.detector = get_wakeword_detector()
        except Exception as e:
            print(f"{C.RED}Microphone/STT unavailable ({e}). Falling back to typed voice mode.{C.RESET}")
            self.run_voice_typed()
            return

        greeting = "Good day, Sir. Say 'Ultron' whenever you need me."
        print(f"\n{C.BLUE}ULTRON:{C.RESET} {greeting}")
        self.speak_reply(greeting)
        print(
            f"\n{C.CYAN}Listening for the wake word 'Ultron'... (Ctrl+C to quit){C.RESET}\n"
            f'{C.DIM}Say "UI mode on" for the voice orb, "text mode on" to also type, '
            f'"silent mode on" for text-only replies, "stop" to interrupt speech.{C.RESET}'
        )

        def run_one_command(command: str, *, from_wake: bool):
            if from_wake:
                # Wake word + command spoken together, e.g. "Ultron, open
                # Chrome" - the wake-word detector's own STT already
                # transcribed this as part of catching the wake word, so
                # there's no separate STT step here: T1 and T2 land at
                # the same instant as T0, which is real, not a bug (see
                # core/perf_trace.py's module docstring).
                perf_trace.mark("T1_stt_start")
                perf_trace.mark("T2_stt_done")
            print(f"{C.GREEN}You:{C.RESET} {command}")
            self.handle_command(command)

        def listen_for_followups():
            """After answering, stay in listening mode - no 'Ultron'
            required - so a full back-and-forth doesn't need the wake
            word re-said before every single command. Falls back to
            wake-word-only listening after FOLLOWUP_LISTEN_TIMEOUT of
            silence, or if the user explicitly ends the conversation."""
            from config import FOLLOWUP_LISTEN_TIMEOUT

            while True:
                print(
                    f"{C.CYAN}(still listening - say your next command, "
                    f"or stay quiet to go back to wake-word mode){C.RESET}"
                )
                perf_trace.start_turn()
                perf_trace.mark("T1_stt_start")
                try:
                    command = self.stt.transcribe_from_mic(timeout=FOLLOWUP_LISTEN_TIMEOUT)
                except Exception as e:
                    # Same reasoning as the wake-triggered capture below:
                    # a transient mic/STT hiccup here must not kill the
                    # follow-up loop (or the outer wake-word loop).
                    logger.warning("STT capture failed: %s", e)
                    command = None
                perf_trace.mark("T2_stt_done")

                if not command:
                    print(f"{C.DIM}(no follow-up heard - back to wake-word mode){C.RESET}")
                    perf_trace.mark("T7_done")
                    perf_trace.summary()
                    return

                if command.strip().lower() in self._SLEEP_PHRASES:
                    self.speak_reply("Of course, Sir. Just say my name when you need me.")
                    return

                run_one_command(command, from_wake=False)
                # loop again - stay in follow-up mode after each reply

        def on_wake(remainder: str):
            perf_trace.start_turn()  # T0 - genuine turn start, wake word just fired
            get_event_bus().emit("wake_detected")
            print(f"\n{C.GREEN}[wake word heard]{C.RESET}")
            if remainder:
                run_one_command(remainder, from_wake=True)
            else:
                # Just the wake word - prompt for the actual command.
                # The "Yes, Sir?" prompt is spoken first and would
                # otherwise pollute T6 (first TTS audio) with its own
                # playback instead of the real answer's - so the turn is
                # restarted right as real listening begins. T0 for this
                # path is therefore "ready to hear the actual command",
                # not the wake word itself; that's the number actually
                # useful for measuring command latency.
                self.speak_reply("Yes, Sir?")
                print(f"{C.CYAN}Listening for your command...{C.RESET}")
                perf_trace.start_turn()
                perf_trace.mark("T1_stt_start")
                try:
                    command = self.stt.transcribe_from_mic()
                except Exception as e:
                    # A3: mic/STT can raise mid-session (device unplugged,
                    # driver hiccup, transient network drop for the cloud
                    # engine) - this used to be unguarded, which killed the
                    # whole listen_loop (and therefore voice mode) on a
                    # single bad capture instead of just missing one turn.
                    logger.warning("STT capture failed: %s", e)
                    command = None
                perf_trace.mark("T2_stt_done")
                if command:
                    run_one_command(command, from_wake=False)
                else:
                    print(f"{C.DIM}(didn't catch that){C.RESET}")
                    perf_trace.mark("T7_done")
                    perf_trace.summary()
                    return

            # A command was just answered (either path above) - stay
            # listening for follow-ups instead of requiring "Ultron"
            # again for every single command.
            listen_for_followups()

        try:
            self.detector.listen_loop(on_wake)
        except KeyboardInterrupt:
            print(f"\n\n{C.BLUE}ULTRON:{C.RESET} Goodbye, Sir.\n")


# Back-compat alias - this class used to live in main.py as UltronRuntime.
UltronRuntime = Assistant


def get_assistant(client=None, processor=None) -> Assistant:
    """Convenience factory for callers that don't already have a client
    and processor handy (e.g. core.debug_console). Builds the default
    Groq-backed brain and slash-command processor if not given."""
    if client is None:
        from core.brain import get_brain

        client = get_brain()
    if processor is None:
        from skills.ai.commands import get_command_processor

        processor = get_command_processor()
    return Assistant(client, processor)
