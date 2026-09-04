"""
router
======
Public routing-layer package. The actual classification/dispatch logic
for each stage lives where the modules it dispatches *to* already live,
to avoid import cycles (core.intent_router dispatches into
core.workflow_engine/core.task_queue, ai.ai_router dispatches into
ai.cloud_models/ai.local_models):

  router.intent_router   -> re-exports core.intent_router
  router.ai_router        -> re-exports ai.ai_router
  router.command_router   -> new: combines control-command / slash-command /
                              local-system-command matching (previously
                              inlined in core.assistant.Assistant.handle_command)
                              into one reusable entry point for other
                              front-ends (plugins, core.debug_console)
  router.skill_router      -> new: ranks skills/<domain>/ folders by keyword
                              match against a message, for callers that want
                              "which skill area is this" without importing
                              every skills/ submodule

Import from this package when you want "the routing layer" as one
namespace; import the underlying core/ai modules directly when you're
already inside core/ or ai/ and would otherwise create a circular import
by going through router/.
"""
