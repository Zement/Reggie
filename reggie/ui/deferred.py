"""Deferred (post-QApplication) imports shared across the editor.

Several modules can't be imported until a ``QApplication`` exists (importing them
creates Qt objects). Historically ``reggie.py``'s ``main()`` imported them and
injected the names into ``reggie``'s own module globals via ``global`` decls, so
``ReggieWindow`` methods could reference them as bare names. That only works while
those methods live in ``reggie.py`` — ``global`` binds to the *defining* module,
so it blocks moving ``main()`` or ``ReggieWindow`` elsewhere.

This module replaces that mechanism. Call :func:`load` once, right after the
``QApplication`` is created; it imports the deferred classes/functions and binds
them as attributes of *this* module. Any module can then use
``from reggie.ui import deferred`` and reach them as ``deferred.GameDefMenu``,
``deferred.GetIcon``, etc. — no namespace injection, works from anywhere.

See _docs/plan/REFACTORING_ANALYSIS.md (Phase 2, boot sequence) and
_docs/plan/DIRECTORY_STRUCTURE.md.
"""

# Names populated by load(). Declared here (as None) so static readers and
# ``deferred.X`` attribute access have something to bind to before load() runs.
GetIcon = None
SetAppStyle = None
ListWidgetWithToolTipSignal = None
LoadNumberFont = None
LoadTheme = None
IconsOnlyTabBar = None
GameDefMenu = None
LoadGameDef = None
PatchManagerDialog = None
BGDialog = None
ZonesDialog = None
AreaOptionsDialog = None
Stamp = None
StampChooserWidget = None
SpriteList = None
SpritePickerWidget = None
ObjectPickerWidget = None
LevelOverviewWidget = None
SpriteEditorWidget = None

_loaded = False


def load():
    """Import all deferred modules and bind their public names onto this module.

    Must be called after ``QApplication`` construction. Idempotent.
    """
    global _loaded
    if _loaded:
        return

    import sys as _sys
    mod = _sys.modules[__name__]

    from reggie.ui.ui import GetIcon, SetAppStyle, ListWidgetWithToolTipSignal, LoadNumberFont, LoadTheme, IconsOnlyTabBar
    from reggie.io.gamedef import GameDefMenu, LoadGameDef
    from reggie.patches.patch_manager_dialog import PatchManagerDialog
    from reggie.core.background import BGDialog
    from reggie.core.zones import ZonesDialog
    from reggie.core.area import AreaOptionsDialog
    from reggie.ui.sidelists import Stamp, StampChooserWidget, SpriteList, SpritePickerWidget, ObjectPickerWidget, LevelOverviewWidget
    from reggie.ui.spriteeditor import SpriteEditorWidget

    for name in (
        'GetIcon', 'SetAppStyle', 'ListWidgetWithToolTipSignal', 'LoadNumberFont', 'LoadTheme', 'IconsOnlyTabBar',
        'GameDefMenu', 'LoadGameDef', 'PatchManagerDialog', 'BGDialog', 'ZonesDialog', 'AreaOptionsDialog',
        'Stamp', 'StampChooserWidget', 'SpriteList', 'SpritePickerWidget', 'ObjectPickerWidget', 'LevelOverviewWidget',
        'SpriteEditorWidget',
    ):
        setattr(mod, name, locals()[name])

    _loaded = True
