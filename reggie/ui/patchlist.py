"""The Game Patches page in sidebar slice 2 (Block D-d, phase D-d.1).

The brief's slice-2 content for the Game Patches rail entry: the installed
patches as a list, the loaded one shown bold, and a button below that opens the
Patch Manager as a tab in the master container.

It is the **third view** on `PatchListModel`, alongside the toolbar combo box
and the Change Game menu - which is the point of deferred item **f7**. Nothing
here reads the patches directory itself; a control that did is how the two
existing lists came to disagree.
"""

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_
from reggie.ui.patchmodel import patch_model


class PatchListWidget(QtWidgets.QWidget):
    """A list of installed patches, plus the Patch Manager button."""

    def __init__(self, window, parent=None):
        super().__init__(parent)

        self.win = window

        self.list = QtWidgets.QListWidget(self)
        self.list.setAlternatingRowColors(True)
        self.list.itemActivated.connect(self._handleActivated)

        self.manageButton = QtWidgets.QPushButton(self)
        self.manageButton.clicked.connect(self._handleManage)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.manageButton, 0)

        self.retranslate()

        # The one refresh this widget does itself: at construction there may be
        # no loaded model yet, and nothing else is going to fill it before the
        # sidebar is shown. Every later refresh comes from RefreshPatchSelector.
        patch_model().refresh()
        self.refresh()

    def retranslate(self):
        self.manageButton.setText(globals_.trans.string('MenuItems', 145))

    # -- contents --------------------------------------------------------

    def refresh(self):
        """Rebuild the list from the shared model.

        Called on construction and from ``RefreshPatchSelector``, so this page
        changes with the other two views rather than going stale the moment the
        patch is switched from the toolbar.

        Reads the model rather than refreshing it, for the same reason
        ``updatePatchComboBox`` does: the refresh belongs to
        ``RefreshPatchSelector``, once, for all three views.
        """
        model = patch_model()

        current = model.current_folder()

        blocked = self.list.blockSignals(True)
        try:
            self.list.clear()

            for entry in model.entries:
                item = QtWidgets.QListWidgetItem(entry.name, self.list)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, entry.folder)

                if entry.description:
                    item.setToolTip(entry.description)

                if entry.folder == current:
                    # Bold for the loaded patch, per the brief. The same signal
                    # the tree uses for a loaded level in D-d.2, so the two
                    # halves of the sidebar say "loaded" the same way.
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    self.list.setCurrentItem(item)
        finally:
            self.list.blockSignals(blocked)

    # -- actions ---------------------------------------------------------

    def _handleActivated(self, item):
        """Switch to the double-clicked patch.

        Routed through ``window.SwitchPatch`` rather than calling
        ``loadNewGameDef`` here: that method settles unsaved work first, puts
        every patch control back in step afterwards, and opens the new patch's
        first level. Reimplementing any of that would be a second, subtly
        different way to switch patch - which is what D-d.1b just finished
        removing.
        """
        if item is None:
            return

        folder = item.data(QtCore.Qt.ItemDataRole.UserRole)

        window = self.win or globals_.mainWindow
        if window is None:
            return

        if folder == patch_model().current_folder():
            # Already loaded. Switching to it would still tear the level down
            # and reload it, which is a surprising amount of work for a
            # double-click on the row that is already bold.
            return

        window.SwitchPatch(folder)

    def _handleManage(self):
        """Open the Patch Manager - a tool tab in the master container."""
        window = self.win or globals_.mainWindow
        if window is None:
            return

        window.HandlePatchManager()
        self.refresh()
