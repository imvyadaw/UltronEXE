#!/usr/bin/env python3
import argparse, json, sys
from activation.ultron_boot import UltronBoot
from security.kill_switch import KillSwitch
from orchestration.ultron_orchestrator import UltronOrchestrator


def main():
    p = argparse.ArgumentParser(description="ULTRON -> ULTRON autonomous AI")
    p.add_argument("goal", nargs="?")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--shutdown", action="store_true")
    a = p.parse_args()
    k = KillSwitch()
    if a.shutdown:
        k.activate("CLI emergency shutdown")
        print("ULTRON kill switch activated.")
        return 0
    if k.active():
        print("ULTRON disabled by kill switch.")
        return 2
    boot = UltronBoot().start()
    if a.status or not a.goal:
        print(json.dumps(boot, indent=2))
        return 0 if boot["healthy"] else 1
    if not boot["healthy"]:
        print(json.dumps(boot, indent=2))
        return 1
    r = UltronOrchestrator().run(a.goal, quick=a.quick)
    print(json.dumps(r, indent=2, default=str))
    return 0 if r["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
