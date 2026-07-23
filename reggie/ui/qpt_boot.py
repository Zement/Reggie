"""Quick Paint Tool boot state — the first *code plugin* (see
:mod:`reggie.plugins.loader`).

QPT ships hook callables that may fail to import, so it must load post-QApplication
and degrade gracefully. This module is the thin QPT-specific adapter over the
generalized :class:`reggie.plugins.loader.CodePlugin`: it defines *what* to import
and mirrors the resulting dict onto ``globals_.qpt_functions`` (which the
quickpaint package reads), while the availability/initialized/try-except
machinery lives in the loader.

Public interface (unchanged for callers): the module-level ``qpt`` object exposes
``qpt.available`` / ``qpt.initialized`` / ``qpt.payload`` (the hook dict), and
``load()`` populates it. ``window.py`` guards QPT init with
``if qpt.available and not qpt.initialized and qpt.payload`` and sets
``qpt.initialized = True`` after wiring the palette tab.

See _docs/plan/REFACTORING_ANALYSIS.md (Phase 2, boot sequence) and
_docs/plan/DIRECTORY_STRUCTURE.md.
"""

from reggie.plugins.loader import CodePlugin


def _load_qpt_functions():
    """Import the QPT hook callables and return them as a dict.

    Runs inside CodePlugin.load() (post-QApplication). Also stores the dict on
    ``globals_.qpt_functions`` for the quickpaint UI code that reads it there.
    """
    from reggie.plugins.quickpaint.reggie_hook import (
        initialize_qpt,
        handle_qpt_mouse_press,
        handle_qpt_mouse_move,
        handle_qpt_mouse_release,
        handle_qpt_key_press,
        update_qpt_outline,
        get_tile_type,
        show_hotkey_overlay,
        hide_hotkey_overlay,
    )
    from reggie.plugins.quickpaint.reggie_hook import _get_qpt_hook
    functions = {
        'initialize': initialize_qpt,
        'press': handle_qpt_mouse_press,
        'move': handle_qpt_mouse_move,
        'release': handle_qpt_mouse_release,
        'key_press': handle_qpt_key_press,
        'get_hook': _get_qpt_hook,
        'update_outline': update_qpt_outline,
        'get_tile_type': get_tile_type,
        'show_overlay': show_hotkey_overlay,
        'hide_overlay': hide_hotkey_overlay,
    }
    # Store in globals_ so the quickpaint package can access it.
    from reggie.core import globals_
    globals_.qpt_functions = functions
    return functions


# The single QPT code-plugin instance the rest of the editor talks to.
qpt = CodePlugin('Quick Paint Tool', _load_qpt_functions)


def load():
    """Load QPT hooks post-QApplication (idempotent, never raises)."""
    qpt.load()
