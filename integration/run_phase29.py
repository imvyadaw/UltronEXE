"""
Phase 29 CLI entry point
==========================
    python -m integration.run_phase29            # full deploy check
    python -m integration.run_phase29 --pipeline # pipeline test only
    python -m integration.run_phase29 --perf     # perf optimizer only

Exit code is 0 on GO/PASS, 1 on NO-GO/FAIL, matching core/startup.py's
convention so this can be wired into a pre-deploy script or CI step
with a plain `&& echo shipped`.
"""

import sys


def main() -> int:
    args = sys.argv[1:]

    if "--pipeline" in args:
        from .pipeline_test import run_pipeline_test

        r = run_pipeline_test()
        print(r.summary())
        return 0 if r.ok else 1

    if "--perf" in args:
        from .perf_optimizer import run_perf_optimizer

        r = run_perf_optimizer()
        print(r.summary())
        return 0 if not r.slow_stages else 1

    from .deploy_check import run_deploy_check

    report = run_deploy_check()
    print(report.summary())
    return 0 if report.go else 1


if __name__ == "__main__":
    raise SystemExit(main())
