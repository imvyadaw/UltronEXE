#!/usr/bin/env python3
"""
settings_panel.py - Simple settings menu for ULTRON.

Run this instead of hand-editing .env. Lets you:
  1. Set/update your Groq API key (the only required key)
  2. Turn optional features on/off (voice intelligence, computer vision,
     autonomy, cross-device, etc.)
  3. See a summary of what's currently configured

Safe to run any time - it only ever edits your local .env file, never
touches the rest of the codebase. Re-run it whenever you want to change
something instead of digging through .env by hand.

Usage:
    python settings_panel.py
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"

# Feature toggles shown in the menu: (env var name, human label, default)
FEATURE_FLAGS = [
    ("ULTRON_AUTONOMY_ENABLED", "Autonomy (Ultron can act on its own without asking each time)", "false"),
    ("ULTRON_ORCHESTRATOR_ENABLED", "Task orchestrator (multi-step task planning)", "true"),
    ("ULTRON_DEVICES_ENABLED", "Smart home / device control", "false"),
    ("ULTRON_AUTONOMOUS_WEB_ENABLED", "Autonomous web browsing (fills forms, navigates sites)", "false"),
    ("ULTRON_VOICE_INTELLIGENCE_ENABLED", "Advanced voice features (emotion, interrupts, diarization)", "true"),
    ("ULTRON_COMPUTER_VISION_ENABLED", "Computer vision (screen understanding, OCR)", "false"),
    ("ULTRON_DEEP_OS_INTEGRATION_ENABLED", "Deep OS integration (registry, window hooks)", "false"),
    ("ULTRON_CROSS_DEVICE_ENABLED", "Cross-device sync (companion app, clipboard sharing)", "false"),
]


def read_env():
    """Read .env into a dict, preserving nothing fancy - simple KEY=VALUE lines."""
    values = {}
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            print("Created .env from .env.example")
        else:
            ENV_PATH.write_text("", encoding="utf-8")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def write_env_value(key, value):
    """Set KEY=value in .env, adding the line if it doesn't exist yet."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def mask_key(value):
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "..." + value[-4:]


def show_summary(env):
    print("\n" + "=" * 50)
    print("  CURRENT SETTINGS")
    print("=" * 50)
    print(f"  Groq API key: {mask_key(env.get('GROQ_API_KEY', ''))}")
    print()
    print("  Feature toggles:")
    for key, label, default in FEATURE_FLAGS:
        current = env.get(key, "") or default
        state = "ON " if current.lower() in ("true", "1", "yes") else "OFF"
        print(f"    [{state}] {label}")
    print("=" * 50 + "\n")


def set_api_key(env):
    print("\nGet a free key at: https://console.groq.com  (sign up -> API Keys)")
    current = env.get("GROQ_API_KEY", "")
    if current:
        print(f"Current key: {mask_key(current)}")
    new_key = input("Paste new GROQ_API_KEY (Enter to keep current, or type 'clear' to remove): ").strip()
    if new_key.lower() == "clear":
        write_env_value("GROQ_API_KEY", "")
        print("Cleared.")
    elif new_key:
        write_env_value("GROQ_API_KEY", new_key)
        print("Saved.")
    else:
        print("Kept existing value.")


def toggle_features(env):
    print()
    for i, (key, label, default) in enumerate(FEATURE_FLAGS, 1):
        current = env.get(key, "") or default
        state = "ON" if current.lower() in ("true", "1", "yes") else "OFF"
        print(f"  {i}. [{state}] {label}")
    print("  0. Back to main menu")
    choice = input("\nEnter a number to toggle it on/off: ").strip()
    if choice == "0" or not choice:
        return
    try:
        idx = int(choice) - 1
        key, label, default = FEATURE_FLAGS[idx]
    except (ValueError, IndexError):
        print("Not a valid option.")
        return
    current = (env.get(key, "") or default).lower() in ("true", "1", "yes")
    new_val = "false" if current else "true"
    write_env_value(key, new_val)
    print(f"{label} -> {'ON' if new_val == 'true' else 'OFF'}")


def main():
    while True:
        env = read_env()
        show_summary(env)
        print("What do you want to do?")
        print("  1. Set / update Groq API key")
        print("  2. Turn features on/off")
        print("  3. Refresh view")
        print("  4. Exit")
        choice = input("> ").strip()
        if choice == "1":
            set_api_key(env)
        elif choice == "2":
            toggle_features(read_env())
        elif choice == "3":
            continue
        elif choice == "4":
            print("Done. Run 'python main.py --text' to start ULTRON.")
            sys.exit(0)
        else:
            print("Not a valid option.")


if __name__ == "__main__":
    main()
