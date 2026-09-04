"""
Penetration testing (DEFENSIVE ONLY)
=======================================
vulnerability_scanner.py performs passive/read-only checks against a
host the caller controls or is otherwise authorized to test: TLS
certificate validity, missing HTTP security headers, and which common
TCP ports respond to a plain connect() (no packet crafting, no banner-
grabbing exploitation, no service-version fingerprinting beyond a
successful/failed connect).

This package deliberately contains NO exploit code, NO payload
generation, and NO automated attack chaining - see
vulnerability_scanner.py's own docstring for the explicit boundary and
why every scan requires the caller to state they're authorized to
test the target.
"""

from penetration_testing.vulnerability_scanner import scan_target

__all__ = ["scan_target"]
