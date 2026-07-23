"""Patch-facing compatibility shim — ``sprites_common`` lives at ``reggie.core.sprites_common``.

**This shim is PERMANENT, not temporary scaffolding.** Game-patch ``sprites.py``
files (e.g. ``reggiedata/patches/NewerSMBW/sprites.py``) are user content loaded
by path and do ``import sprites_common as common``. We cannot rewrite their
imports, so the top-level ``sprites_common`` name must keep resolving. It aliases
``sys.modules`` to the real module so patch code and internal code share the
*same* object.

(All of Reggie's own code imports ``from reggie.core import sprites_common``
directly; this shim exists solely for the game-patch sprite-image API. See
_docs/plan/DIRECTORY_STRUCTURE.md.)
"""

import sys

from reggie.core import sprites_common as _real

sys.modules[__name__] = _real
