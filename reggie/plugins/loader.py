"""Generalized boot-guard for optional *code* plugins (e.g. Quick Paint Tool).

Two different things are called "plugins" in Reggie; don't confuse them:

* **Patch plugins** — per-patch feature toggles declared in ``plugins.xml`` and
  checked with :func:`reggie.plugins.patch_plugins.is_enabled`. Pure data.
* **Code plugins** — optional Python subsystems under ``reggie/plugins/`` that
  ship hook callables and *may fail to import* (missing dep, broken build), so
  the editor must degrade gracefully rather than crash. Quick Paint Tool is the
  first; this module is for these.

The established QPT pattern (see :mod:`reggie.ui.qpt_boot`) was: a module-level
``AVAILABLE`` flag (True until an import failure flips it False), an
``INITIALIZED`` flag, a ``functions`` payload imported *after* the QApplication
exists, all wrapped in try/except. :class:`CodePlugin` captures exactly that so a
second code plugin is a few lines instead of a re-implementation.

Contract (matches the current QPT boot exactly):
* Construct with a name and a zero-arg ``loader`` that returns the hook payload
  (usually a dict of callables). Do the actual ``from reggie.plugins.<x> import …``
  *inside* the loader so it runs post-QApplication.
* Call :meth:`load` once during boot. On success ``available`` stays True and
  ``payload`` holds the loader's return; on any exception ``available`` becomes
  False, ``payload`` stays None, and the traceback is printed (non-fatal).
* Guard feature code with ``if plugin.available and not plugin.initialized: …``
  then set ``plugin.initialized = True`` after wiring the UI — same flags as
  before, just owned by this object.
"""

import traceback


class CodePlugin:
    """Boot-guard wrapper for one optional code plugin."""

    def __init__(self, name, loader):
        self.name = name
        self._loader = loader
        self.available = True     # until an import/init failure proves otherwise
        self.initialized = False  # set by the caller once the plugin's UI is wired
        self.payload = None       # loader() return value (e.g. dict of hook callables)

    def load(self):
        """Run the loader post-QApplication. Never raises; sets availability."""
        if self.payload is not None:
            return self.payload
        try:
            self.payload = self._loader()
            print(f"[BOOT] ✓ {self.name} loaded")
        except Exception as e:  # noqa: BLE001 — plugin failure must never crash boot
            print(f"[BOOT] Warning: could not load {self.name}: {e}")
            traceback.print_exc()
            self.available = False
            self.payload = None
        return self.payload
