"""
router.intent_router
=====================
Public-facing alias for core.intent_router, which is where the actual
WORKFLOW / BACKGROUND / TASK_STATUS / CHAT classification logic lives
(it stays in core/ because it dispatches into core.workflow_engine and
core.task_queue, both core/ modules - moving the classifier itself into
router/ would make core/ import from router/ and router/ import from
core/ at the same time). Import from here when you just want "the
router package's view of intent routing" without needing to know the
implementation lives one folder over.
"""

