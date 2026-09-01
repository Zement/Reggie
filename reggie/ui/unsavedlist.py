"""The unsaved-levels list: every open file with work not yet on disk.

Block D-d, phase D-d.3c. Specified in `BLOCK_D_STATE_MODEL.md` §6.5 (Zement,
2026-08-26), "in the spirit of VS Code's Source Control view":

    A level appears when *any* of its areas has unsaved changes.
    The section is hidden entirely when nothing is unsaved.
    Entries can be saved individually, or all at once.
    In a collab session this is the host's list.

**The unit is the file, not the area** - `Level_NSMBW.save()` serialises every
area in one pass, so a level with two dirty areas is one entry and one save
(§6.4). `SessionManager.dirty_files()` returns exactly that set, which is why
this widget does no counting of its own.

**Labels match the tab bar, not the tree.** The directory listing could give a
catalog name ("Yoshi's Island" rather than `01-01`), and deliberately does not:
this list sits beside the tabs and the user reads the two together, so an entry
that named the same file differently would cost more than it explained. The
full path is the tooltip, and an unsaved new level shows the same "Untitled"
its tab does.
"""

import os

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_


def dirty_paths():
    """The open files with unsaved work, or an empty list.

    Guarded: this is reached from ``UpdateTitle``, which runs constantly and on
    paths with no session manager at all - boot, the headless suites, and the
    pre-session load path.

    A new level appears here as ``None``, which is its honest path. That is why
    nothing downstream may treat a path as an identity - see `dirty_entries`.
    """
    manager = globals_.get_session_manager()
    if manager is None:
        return []

    try:
        return list(manager.dirty_files())
    except Exception:
        return []


def dirty_entries():
    """``(path, session)`` for every file with unsaved work.

    The session is the row's identity, and the path is only its name. **A path
    cannot be the identity here** because a new level has none: two unsaved
    levels both answer `None`, and `sessions_for(None)` finds neither, since
    `_handles` is keyed by path and unsaved handles are not in it (D-d.3b).

    That was measured, not guessed: a New Level appeared in the list correctly
    and then could not be saved from it, and Save All returned False without
    touching the *other* files. Carrying a session per row fixes both, and
    costs nothing for a saved file - the session is simply the way back to the
    handle when the path is not one.

    One session per entry, not all of them: saving is per file, so any session
    on the level will do, and the first is the one whose tab has been open
    longest.
    """
    manager = globals_.get_session_manager()
    if manager is None:
        return []

    try:
        sessions = list(manager.sessions)
    except Exception:
        return []

    entries = []
    seen = []

    for session in sessions:
        if not session.dirty:
            continue

        # By *handle*, not by path: that is what "one entry per file" means
        # when the file has no name yet, and it is exactly the handle-sharing
        # rule from S6.4 - two areas of one level share a handle and so are one
        # row.
        handle = getattr(session, 'handle', None)
        key = handle if handle is not None else session
        if key in seen:
            continue

        seen.append(key)
        entries.append((session.file_path, session))

    # Named files sorted by path, so the order matches `dirty_files()`; unsaved
    # ones after them, in the order they were opened. `None` cannot be compared
    # to a string, so the two groups are sorted apart rather than together.
    named = sorted((e for e in entries if e[0] is not None), key=lambda e: e[0])
    unnamed = [e for e in entries if e[0] is None]
    return named + unnamed


def label_for(path):
    """What one entry is called. See the module docstring on why this is the
    tab's name rather than the catalog's."""
    if not path:
        return globals_.trans.string('WindowTitle', 0)

    name = os.path.splitext(os.path.basename(path))[0]
    return name or globals_.trans.string('WindowTitle', 0)


class UnsavedLevelsWidget(QtWidgets.QWidget):
    """A list of dirty files, with save-one and save-all.

    A list rather than a tree because the unit of saving is the level and there
    is nothing to nest under it, and because this section exists only while
    there is unsaved work - it is usually absent and never long.

    No per-row save button: that means a delegate or a cell widget per row, and
    double-click already means "act on this" in the directory listing right
    above. The same gesture doing the same kind of thing is worth more here than
    a button would be.
    """

    def __init__(self, window=None, parent=None):
        super().__init__(parent)

        self.win = window

        self.list = QtWidgets.QListWidget(self)
        self.list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.list.itemActivated.connect(self._handleActivated)
        self.list.itemDoubleClicked.connect(self._handleActivated)

        self.saveAllButton = QtWidgets.QPushButton(self)
        self.saveAllButton.clicked.connect(self._handleSaveAll)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.saveAllButton, 0)

        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.saveAllButton.setText(globals_.trans.string('MenuItems', 152))
        self.list.setToolTip(globals_.trans.string('MenuItems', 153))

    # -- contents --------------------------------------------------------

    def paths(self):
        """The paths currently listed, in the order shown. ``None`` for a level
        that has never been saved."""
        return [self.list.item(row).data(QtCore.Qt.ItemDataRole.UserRole)[0]
                for row in range(self.list.count())]

    def sessions(self):
        """The session behind each row, in the order shown."""
        return [self.list.item(row).data(QtCore.Qt.ItemDataRole.UserRole)[1]
                for row in range(self.list.count())]

    def refresh(self):
        """Rebuild from the manager. Returns whether anything is unsaved.

        The return value is what decides whether the *section* exists, so the
        caller does not have to ask the manager a second time and cannot end up
        with a section disagreeing with its own contents.

        Rebuilt wholesale rather than diffed: the list is at most a handful of
        rows, and a diff would have to preserve a selection that means nothing
        here - there is no state in a row beyond the path it names.
        """
        entries = dirty_entries()

        # The selection is not worth keeping (nothing acts on it but a
        # double-click, which carries its own item), but the scroll position is
        # cheap to keep and jumping to the top on every keystroke's SetDirty
        # would be visible.
        scroll = self.list.verticalScrollBar().value()

        self.list.clear()

        for path, session in entries:
            item = QtWidgets.QListWidgetItem(label_for(path))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, (path, session))
            item.setToolTip(path or globals_.trans.string('MenuItems', 155))
            self.list.addItem(item)

        self.list.verticalScrollBar().setValue(scroll)
        self.saveAllButton.setEnabled(bool(entries))

        return bool(entries)

    # -- acting ----------------------------------------------------------

    def _handleActivated(self, item):
        if item is None or self.win is None:
            return False

        path, session = item.data(QtCore.Qt.ItemDataRole.UserRole)
        return bool(self.win.SaveLevelFile(path, session))

    def _handleSaveAll(self):
        if self.win is None:
            return False

        return bool(self.win.SaveAllDirtyLevels())
