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

**A level that has never been saved is shown in red and skipped by Save All**
(Zement, 2026-09-01). It has no file name to write to, so saving it can only
stop and open the Save dialog - and a bulk action that asks a question per level
is not a bulk action, quite apart from one cancelled dialog abandoning every
file after it. Double-clicking such a row still saves it, through that dialog,
which is the only possible answer to "save a level with no name".
"""

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_


#: Rows for levels that have never been saved. Not a theme colour: adding a key
#: means touching every theme file, for one row in one list that is usually
#: empty. This red is mid-toned on purpose so it reads on a light and a dark
#: list alike, rather than the pure #f00 that vanishes on dark backgrounds.
UNSAVED_NEW_COLOR = '#d02020'


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
    """A list of dirty files, with buttons to save or discard them.

    A list rather than a tree because the unit of saving is the level and there
    is nothing to nest under it, and because this section exists only while
    there is unsaved work - it is usually absent and never long.

    **Four buttons in two rows** since D-d.3d, because the slice is narrow.
    Double-click still saves a row, but it is a shortcut now rather than the
    interface (Zement, 2026-09-01: "double-clicking a row to save the level is a
    bit difficult to discover, as it is not a common behavior"). Selection is
    `ExtendedSelection`, so Ctrl+Click and Shift+Click work the way they do in
    every other list.

    Save and Discard act on the **selection**; Save All and Discard All act on
    every row. Both bulk actions skip levels that have never been saved - see
    the module docstring for Save, and `DiscardLevelFile` for Discard.
    """

    def __init__(self, window=None, parent=None):
        super().__init__(parent)

        self.win = window

        self.list = QtWidgets.QListWidget(self)
        # Ctrl+Click and Shift+Click, "the industry standard for lists"
        # (Zement) - and what makes a Save button acting on a selection worth
        # having rather than a slower double-click.
        self.list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemActivated.connect(self._handleActivated)
        self.list.itemDoubleClicked.connect(self._handleActivated)
        self.list.itemSelectionChanged.connect(self._syncButtons)

        self.saveButton = QtWidgets.QPushButton(self)
        self.saveButton.clicked.connect(self._handleSaveSelected)
        self.saveAllButton = QtWidgets.QPushButton(self)
        self.saveAllButton.clicked.connect(self._handleSaveAll)
        self.discardButton = QtWidgets.QPushButton(self)
        self.discardButton.clicked.connect(self._handleDiscardSelected)
        self.discardAllButton = QtWidgets.QPushButton(self)
        self.discardAllButton.clicked.connect(self._handleDiscardAll)

        # Two rows of two. One row of four would put four labels into ~180px,
        # which is the minimum width of slice 2 - they would all elide to
        # nothing (Zement: "due to the small width of the slice, the buttons can
        # sort into two rows").
        buttons = QtWidgets.QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(2)
        buttons.addWidget(self.saveButton, 0, 0)
        buttons.addWidget(self.saveAllButton, 0, 1)
        buttons.addWidget(self.discardButton, 1, 0)
        buttons.addWidget(self.discardAllButton, 1, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons, 0)

        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.saveButton.setText(globals_.trans.string('MenuItems', 157))
        self.saveAllButton.setText(globals_.trans.string('MenuItems', 152))
        self.discardButton.setText(globals_.trans.string('MenuItems', 158))
        self.discardAllButton.setText(globals_.trans.string('MenuItems', 159))
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

    def selectedEntries(self):
        """``(path, session)`` for each selected row, in the order shown."""
        return [item.data(QtCore.Qt.ItemDataRole.UserRole)
                for item in self.list.selectedItems()]

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

            if path:
                item.setToolTip(path)
            else:
                # Red, and skipped by Save All (Zement, 2026-09-01). A level
                # that has never been saved has no file name to write to, so
                # bulk-saving it can only stop and ask - which is not what a
                # button called "Save All" should do. It stays double-clickable,
                # and that route opens the Save dialog as it should.
                item.setToolTip(globals_.trans.string('MenuItems', 155))
                item.setForeground(QtGui.QColor(UNSAVED_NEW_COLOR))

            self.list.addItem(item)

        self.list.verticalScrollBar().setValue(scroll)
        self._syncButtons()

        return bool(entries)

    def _syncButtons(self):
        """Enable each button only when it would actually do something.

        The two bulk buttons need a row that is *not* a never-saved level, since
        both bulk actions skip those - a button that provably does nothing
        should say so rather than appear to work. The two selection buttons need
        a selection, and the same exclusion for the same reason.
        """
        entries = [(self.list.item(row)
                    .data(QtCore.Qt.ItemDataRole.UserRole))
                   for row in range(self.list.count())]
        selected = self.selectedEntries()

        bulk = any(path for path, _session in entries)
        picked = any(path for path, _session in selected)

        self.saveAllButton.setEnabled(bulk)
        self.discardAllButton.setEnabled(bulk)
        self.saveButton.setEnabled(bool(selected))
        self.discardButton.setEnabled(picked)

        skip = globals_.trans.string('MenuItems', 156)
        self.saveAllButton.setToolTip('' if bulk else skip)
        self.discardAllButton.setToolTip('' if bulk else skip)

        # Save *is* available for a selected never-saved level - it opens the
        # Save dialog, which is exactly what such a level needs. Discard is not:
        # there is no file on disk to go back to.
        self.discardButton.setToolTip(
            '' if picked or not selected
            else globals_.trans.string('MenuItems', 160))

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

    def _handleSaveSelected(self):
        """Save every selected row, the active file last.

        Same rule as Save All, and for the same reason: the user should end on
        the tab they started on rather than on whichever row sorted last.
        Selecting nothing does nothing - the button is disabled for that.
        """
        if self.win is None:
            return False

        return bool(self.win.SaveLevelFiles(self.selectedEntries()))

    def _handleDiscardSelected(self):
        if self.win is None:
            return False

        return bool(self.win.DiscardLevelFiles(self.selectedEntries()))

    def _handleDiscardAll(self):
        if self.win is None:
            return False

        return bool(self.win.DiscardAllDirtyLevels())
