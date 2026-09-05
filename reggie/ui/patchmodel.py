"""One list of installed game patches, for every control that shows them.

Block D-d, phase D-d.1 - the deferred item **f7**.

Two controls named the installed patches, and they could disagree:

- the toolbar combo box (``window.updatePatchComboBox``) honoured the
  ``PatchPath_<name>`` settings key, so a patch installed outside
  ``reggiedata/patches`` was constructed from its real location;
- the Change Game menu (``GameDefMenu.refreshMenu``) called
  ``ReggieGameDefinition(folder)`` with no ``custom_path``, so the same patch was
  constructed from a folder that is not there - falling back to the retail
  gamedef, and, because ``ReggieGameDefinition.__init__`` clears
  ``LastGameDef`` when a named patch cannot be found, **silently forgetting
  which patch was loaded**.

They also differed in what they filtered (the combo box dropped anything whose
``custom`` flag was False; the menu showed it), and both rebuilt every
``ReggieGameDefinition`` from disk on every refresh - the menu twice, since
``refreshMenu`` ends by calling ``RefreshPatchSelector``.

This module is the one source both now read. ``3aaecb0`` added
``RefreshPatchSelector()`` as the seam for exactly this: one model, several
views.

**The folder name is never the patch id.** ``PatchEntry.folder`` is the key used
for ``LastGameDef``, ``PatchPath_``/``TextureGamePath_`` lookups and
``ReggieGameDefinition(name=...)``; ``PatchEntry.name`` is the display name out
of the patch's own ``main.xml``. They are routinely different and must not be
swapped.

**Retail is not a patch.** It is the ``folder is None`` entry, and it is carried
here as a first-class row so the views stop special-casing it three separate
times.
"""

import os

from reggie.core import globals_
from reggie.core.dirty import setting


class PatchEntry:
    """One row: retail, or an installed game patch.

    Deliberately a plain object rather than the ``ReggieGameDefinition`` itself.
    A gamedef is a heavy thing to hold - it carries file tables, sprite modules
    and a base chain - and a list of patches wants only what it takes to *name*
    one and *load* it later.
    """

    __slots__ = ('folder', 'name', 'description', 'custom_path')

    def __init__(self, folder, name, description='', custom_path=None):
        #: The patch id: the folder name under ``reggiedata/patches``, or the
        #: name a ``PatchPath_`` key was registered under. ``None`` for retail.
        self.folder = folder
        #: Display name, from the patch's ``main.xml``.
        self.name = name
        self.description = description
        #: Where the patch actually lives, when it is not under
        #: ``reggiedata/patches``. ``None`` means the default location.
        self.custom_path = custom_path

    @property
    def is_retail(self):
        """Whether this row is the base game rather than a patch."""
        return self.folder is None

    def gamedef(self):
        """Build a ``ReggieGameDefinition`` for this row.

        The reason this lives on the entry: it is the one place that knows a
        custom path has to be passed along. Every caller that built its own
        gamedef straight from a folder name is how the two lists came to
        disagree.
        """
        from reggie.io.gamedef import ReggieGameDefinition

        if self.folder is None:
            return ReggieGameDefinition()

        return ReggieGameDefinition(self.folder, custom_path=self.custom_path)

    def __eq__(self, other):
        if not isinstance(other, PatchEntry):
            return NotImplemented
        return self.folder == other.folder

    def __hash__(self):
        return hash(self.folder)

    def __repr__(self):
        return '<PatchEntry %r name=%r%s>' % (
            self.folder, self.name, ' custom' if self.custom_path else '')


class PatchListModel:
    """The installed patches, and which one is loaded.

    Not a ``QAbstractItemModel``: the three views here are a combo box, a menu
    and (in D-d.2) a tree section, none of which is a Qt view over a model. It
    is a plain list with a refresh, which is what "one source of truth" needs to
    mean at this size. The tree gets its own item model in D-d.2 and will read
    *this* for its patch nodes.
    """

    def __init__(self):
        self._entries = []
        self._loaded = False

    # -- reading ---------------------------------------------------------

    @property
    def entries(self):
        """Every row, retail first, then patches alphabetically by display name.

        Loads on first access so constructing the model costs nothing at boot;
        ``refresh()`` is what re-reads the disk afterwards.
        """
        if not self._loaded:
            self.refresh()
        return list(self._entries)

    @property
    def patches(self):
        """The rows that are actual patches - retail excluded."""
        return [entry for entry in self.entries if not entry.is_retail]

    def find(self, folder):
        """The row for a patch id, or None. ``find(None)`` is the retail row."""
        for entry in self.entries:
            if entry.folder == folder:
                return entry
        return None

    def current_folder(self):
        """The loaded patch's id, straight from settings.

        Read rather than cached: the setting is written by ``loadNewGameDef``
        and by the collab layer, and a cached copy here would be one more thing
        that can fall out of step - which is the whole complaint f7 records.
        """
        folder = setting('LastGameDef')

        # Settings round-trip some values as strings; 'None' is not a patch id.
        if folder in (None, 'None', '', 0, False):
            return None

        return folder

    def current(self):
        """The loaded patch's row, falling back to retail.

        The fallback matters: ``LastGameDef`` can name a patch that has since
        been deleted, and a view that cannot find its row must still show
        something truthful.
        """
        return self.find(self.current_folder()) or self.find(None)

    # -- refreshing ------------------------------------------------------

    def refresh(self):
        """Re-read the installed patches from disk and settings.

        Every failure to construct a patch is skipped rather than raised: an
        unreadable patch must not stop the others being listed, which is the one
        behaviour worth keeping from the combo box's bare ``except``.
        """
        from reggie.io.gamedef import getAvailableGameDefs, ReggieGameDefinition

        entries = [PatchEntry(None, _retail_name(), _retail_description())]

        try:
            folders = getAvailableGameDefs()
        except Exception:
            folders = [None]

        rows = []
        for folder in folders:
            if folder is None:
                continue

            custom_path = setting('PatchPath_' + folder) or None

            # Normalised the way getAvailableGameDefs normalises it before its
            # own isfile() check. It throws its normalised copy away, so
            # without this the path reaches ReggieGameDefinition with whatever
            # slash convention it was saved under - which differs by how the
            # patch was added (the folder picker, a collab install, or a hand
            # edit of settings.ini).
            if custom_path:
                custom_path = os.path.normpath(custom_path)

            try:
                def_ = ReggieGameDefinition(folder, custom_path=custom_path)
            except Exception:
                continue

            # A gamedef that did not load reports custom=False and wears the
            # retail name, so listing it would put a second
            # "New Super Mario Bros. Wii" in the list. The combo box filtered
            # on this; the menu did not.
            if not def_.custom:
                continue

            rows.append(PatchEntry(folder, def_.name,
                                   getattr(def_, 'description', '') or '',
                                   custom_path))

        # By display name, which is what the user reads. getAvailableGameDefs
        # sorts by (name, folder) internally but then discards the names, so the
        # order it returns is only correct while name and folder agree.
        rows.sort(key=lambda entry: (entry.name or '').lower())

        entries.extend(rows)

        self._entries = entries
        self._loaded = True

        return entries


def _retail_name():
    """'New Super Mario Bros. Wii', translated."""
    try:
        return globals_.trans.string('Gamedefs', 13)
    except Exception:
        # Before the translation is loaded - the headless suites reach here.
        return 'New Super Mario Bros. Wii'


def _retail_description():
    try:
        return globals_.trans.string('Gamedefs', 14)
    except Exception:
        return ''


#: The process-wide model. One list, so the views cannot disagree.
_model = None


def patch_model():
    """The shared ``PatchListModel``, built on first use."""
    global _model

    if _model is None:
        _model = PatchListModel()

    return _model
