# -*- mode: python ; coding: utf-8 -*-
"""
Ultron PyInstaller spec
=======================
Build with:  build_exe.bat   (or:  pyinstaller build_exe.spec)

WHY A CUSTOM SPEC (not just `pyinstaller main.py`):
- core/full_module_registry.py loads ~290 modules dynamically via
  importlib.import_module() (string paths in SAFE_MODULES/UNSAFE_MODULES).
  PyInstaller's static analysis can't see these, so a plain build would
  silently drop them and crash at runtime with ModuleNotFoundError the
  first time wire_all_modules() runs. Fix: collect_submodules() on every
  first-party top-level package below, which walks and bundles every
  .py file in each package whether or not it's statically imported.
- Non-.py data (skill prompts, config templates, assets) needs explicit
  `datas` entries - PyInstaller doesn't bundle those on its own.

ONEDIR, not ONEFILE:
  Ultron writes to storage/, database/, logs/ at runtime and expects
  BASE_DIR (config.py: Path(__file__).resolve().parent) to be a stable,
  writable location next to the exe. Onefile mode extracts to a fresh
  temp folder on every launch (breaks persistence, slower startup,
  more likely to trip antivirus). Onedir keeps everything in one
  folder you can zip/move as a unit - use that.

BEFORE BUILDING:
  - Run this ON Windows (PyInstaller cross-compiling from Linux/Mac to
    a Windows .exe is not supported).
  - pip install -r requirements.txt -r requirements-windows.txt pyinstaller
  - Delete/empty database/*.db and storage/sqlite/*.db first if you
    don't want your current conversation history baked into the build.
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Every first-party top-level package - collect_submodules() bundles
# every module inside each one, catching full_module_registry.py's
# ~290 dynamically-imported modules that static analysis would miss.
FIRST_PARTY_PACKAGES = [
    "actions", "adaptive_ui", "advanced_memory", "advanced_personality",
    "agents", "ai", "ai_supercharger", "approval", "apps", "automation",
    "autonomous_web", "autonomy", "browser", "certification", "cognitive_core",
    "command", "computer_vision", "connect", "conversation", "core",
    "core_integration", "cross_device", "database", "decision_engine_2.0",
    "deep_os_integration", "deep_verification", "devices", "display", "ears",
    "empathy_engine", "entertainment_engine", "execution", "eyes",
    "files", "hardening", "heal", "home", "integration", "intelligence",
    "intelligence_bridge", "ultron_shield", "knowledge_base",
    "language_generation", "learn", "learning", "learning_engine", "memory",
    "modules", "monitoring", "mouth", "multi_agent_swarm", "networking",
    "penetration_testing", "perception", "planning", "plugins", "predict",
    "predictive_engine", "predictive_mind", "proactive", "quantum_dashboard",
    "reasoning", "router", "safety", "scenarios", "scheduler", "search",
    "security", "self_healing", "skill_creator", "skills", "stability",
    "storage", "system_control", "translation_engine", "ui", "utils",
    "verification", "verification_engine", "vision", "voice",
    "voice_intelligence", "windows",
]

hiddenimports = []
datas = [
    (".env.example", "."),
    ("config.py", "."),
]
for pkg in FIRST_PARTY_PACKAGES:
    if os.path.isdir(pkg):
        hiddenimports += collect_submodules(pkg)
        datas += collect_data_files(pkg, include_py_files=False)

# Third-party libraries known to need explicit help with PyInstaller
# (C-extension / dynamic-plugin loaders that static analysis misses).
for pkg in [
    "pycaw", "comtypes", "cv2", "onnxruntime", "vosk", "faster_whisper",
    "edge_tts", "pygame", "speech_recognition", "openwakeword",
]:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass  # optional dep not installed - skip, matches the codebase's own fail-soft convention

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "testing"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ultron",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX compression trips more antivirus heuristics than it's worth here
    console=True,  # Ultron is a CLI/voice app - keep the console window
    icon=None,  # put a path to a .ico here if you have one, e.g. "assets/ultron.ico"
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Ultron",
)
