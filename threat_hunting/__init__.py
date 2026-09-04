"""
Threat hunting (DEFENSIVE ONLY)
==================================
malware_analyzer.py performs read-only reputation/heuristic checks:
local file hashing (SHA-256/MD5) with optional VirusTotal hash lookup
if VT_API_KEY is configured, plus a structural URL heuristic check
(no live fetch of the URL's content). This package contains NO
malware creation, obfuscation, or payload-generation code of any
kind, and never executes or opens a scanned file.
"""

from threat_hunting.malware_analyzer import hash_file, check_file_reputation, check_url_reputation

__all__ = ["hash_file", "check_file_reputation", "check_url_reputation"]
