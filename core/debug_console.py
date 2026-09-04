"""
Debug console
=============
Dev-only interactive REPL for poking at Ultron's live singletons
without going through the voice/text assistant loop - inspect
core.state_manager, fire an event on core.events' bus by hand, or run a
line of text through router.command_router / router.intent_router to
see how it would be classified.

Run directly: `python -m core.debug_console`. Never imported by
main.py or core.assistant - this is a standalone dev tool, not part of
the normal runtime boot path, so it can't accidentally end up on a
user-facing code path.
"""

import json

BANNER = """Ultron debug console. Commands:
  state                  - dump current state_manager contents
  set <key> <value>      - set a state_manager key (value parsed as JSON if possible)
  emit <event> [k=v ...] - emit an event on the shared bus
  route <text>           - run text through router.command_router, then router.intent_router
  skills <text>          - rank skills/ domains by keyword match against text
  online                 - check current internet status (forces a fresh check)
  startup                - re-run core.startup checks and print the report
  help                   - show this message
  exit                   - quit
"""


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _cmd_route(text: str) -> None:
    from router.command_router import route_command

    cmd_result = route_command(text)
    if cmd_result.handled:
        print(f"command_router: {cmd_result}")
        return
    print("command_router: not handled, would fall through to intent_router")

    from router.intent_router import route as intent_route

    intent_result = intent_route(text)
    print(f"intent_router: {intent_result}")


def _cmd_skills(text: str) -> None:
    from router.skill_router import select_skill

    ranked = select_skill(text)
    if not ranked:
        print("no skill domain matched")
        return
    for entry in ranked:
        print(f"  {entry['domain']:<15} score={entry['score']}")


def run() -> None:
    from core.events import get_event_bus
    from core.state_manager import get_state_manager

    print(BANNER)
    sm = get_state_manager()
    bus = get_event_bus()

    while True:
        try:
            line = input("ultron-debug> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            print(BANNER)
            continue

        if line == "state":
            print(json.dumps(sm.all(), indent=2, default=str))
            continue

        if line == "online":
            from core.internet_monitor import is_online

            print("online" if is_online(force=True) else "offline")
            continue

        if line == "startup":
            from core.startup import run_startup_checks

            run_startup_checks(verbose=True)
            continue

        if line.startswith("set "):
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                print("usage: set <key> <value>")
                continue
            _, key, raw_value = parts
            sm.set(key, _parse_value(raw_value))
            print(f"ok: {key} = {sm.get(key)!r}")
            continue

        if line.startswith("emit "):
            parts = line.split()
            event_name = parts[1] if len(parts) > 1 else ""
            if not event_name:
                print("usage: emit <event> [key=value ...]")
                continue
            payload = {}
            for kv in parts[2:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    payload[k] = _parse_value(v)
            bus.emit(event_name, **payload)
            print(f"emitted: {event_name} {payload}")
            continue

        if line.startswith("route "):
            _cmd_route(line[len("route ") :])
            continue

        if line.startswith("skills "):
            _cmd_skills(line[len("skills ") :])
            continue

        print(f"unknown command: {line!r} (type 'help')")


if __name__ == "__main__":
    run()
