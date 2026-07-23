"""Patch-facing compatibility shim — ``spritelib`` lives at ``reggie.core.spritelib``.

**This shim is PERMANENT, not temporary scaffolding.** Game-patch ``sprites.py``
files (e.g. ``reggiedata/patches/NewerSMBW/sprites.py``) are user content loaded
by path and do ``import spritelib as SLib``. We cannot rewrite their imports, so
the top-level ``spritelib`` name must keep resolving. It aliases ``sys.modules``
to the real module so patch code and internal code share the *same* object.

(All of Reggie's own code imports ``from reggie.core import spritelib`` directly;
this shim exists solely for the game-patch sprite-image API. See
_docs/plan/DIRECTORY_STRUCTURE.md.)
"""

import sys

from reggie.core import spritelib as _real

sys.modules[__name__] = _real
