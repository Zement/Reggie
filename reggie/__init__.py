"""Reggie! Next — application package.

This package is the destination for the modularization effort described in
_docs/plan/DIRECTORY_STRUCTURE.md. Modules are migrated here from the flat
top-level layout one dependency-ordered group at a time; during the migration,
thin shim modules may remain at the repo root so that ``import <name>`` keeps
working for both internal code and game-patch ``sprites.py`` files.
"""
