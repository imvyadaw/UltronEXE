"""
Decision engine 2.0
=====================
NOTE ON THIS PACKAGE'S NAME: this folder is intentionally named
"decision_engine_2.0" (matching the requested tree exactly), but a
literal "." in a package/folder name is not valid in a Python
`import` statement (there is no valid module named "0"). Nothing in
this codebase can do `import decision_engine_2.0` or
`from decision_engine_2.0 import x` - that line would raise
SyntaxError. Both files inside are therefore self-contained (no
imports from each other or from a package __init__) and are wired
into the tool-calling loop by ai/decision_tools.py using
importlib.util.spec_from_file_location against their exact file
paths, the same workaround used for
entertainment_engine/movie_suggester_2.0.py.

This __init__.py exists only so the folder matches the requested
tree; it deliberately contains no code, since nothing can reach it
via a normal import.
"""
