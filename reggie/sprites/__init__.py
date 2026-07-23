"""Sprite image classes for Reggie! Next.

Public surface (kept stable — internal code AND game-patch ``sprites.py`` files
depend on it):

* ``ImageClasses`` — dict mapping sprite ID -> SpriteImage_* class.
* ``LoadBasics()`` — preloads common images (coins, blocks, characters, vines).
* every ``SpriteImage_*`` class, importable by name (e.g.
  ``from reggie.sprites import SpriteImage_LiquidOrFog``).

Migration status (see _docs/plan/DIRECTORY_STRUCTURE.md and
REFACTORING_ANALYSIS.md): the original ~9,000-line body is split by base class
into ``base.py`` (classes involved in intra-file inheritance + shared imports +
``LoadBasics``), ``static.py`` (SpriteImage_Static subclasses),
``static_multiple.py`` (SpriteImage_StaticMultiple subclasses) and ``dynamic.py``
(everything else). ``registry.py`` rebuilds ``ImageClasses`` from those modules.
This ``__init__`` re-exports the same public surface the flat ``sprites`` module
used to expose, so no caller had to change.
"""

# Re-export the whole sprite surface. ``import *`` is deliberate: it preserves
# the historical flat ``import sprites`` API — every SpriteImage_* class name,
# plus LoadBasics — exactly. base is imported first so subclass modules that did
# ``from reggie.sprites.base import *`` don't shadow anything unexpectedly.
from reggie.sprites.base import *              # noqa: F401,F403
from reggie.sprites.static import *            # noqa: F401,F403
from reggie.sprites.static_multiple import *   # noqa: F401,F403
from reggie.sprites.dynamic import *           # noqa: F401,F403

# Explicit re-bind of the named public surface (ImageClasses lives in registry;
# LoadBasics in base) so it's present regardless of ``import *`` resolution.
from reggie.sprites.base import LoadBasics      # noqa: F401
from reggie.sprites.registry import ImageClasses  # noqa: F401
