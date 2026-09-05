"""The Help section in sidebar slice 2 (Block D-d, phase D-d.2c).

Zement, 2026-09-01: "*Help* by the way should simply show the current Help file
menu contents as a tree in slice 2."

Taken literally, and that is the whole design: this reads the live
``QMenu`` the menu bar already built rather than listing the entries a second
time. An entry added to the Help menu appears here with nothing to update, and
one removed disappears - which is the only way two views of the same list stay
honest. The same reasoning as ``PatchListModel``: whichever list is *derived*
cannot disagree with the other.

Triggering a row triggers the action itself, so the entries keep their existing
behaviour (the About box, the readme, the tips) without this module knowing what
any of them do.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_


class HelpTreeWidget(QtWidgets.QWidget):
    """The Help menu, rendered as a slice-2 tree."""

    def __init__(self, window, parent=None):
        super().__init__(parent)

        self.win = window

        self.tree = QtWidgets.QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)

        # Activated rather than clicked: a single click selects, and Enter or a
        # double click runs it. The level tree behaves the same way, and a Help
        # entry that fired on a stray click while arrowing through the list
        # would be worse than one that needs confirming.
        self.tree.itemActivated.connect(self._handleActivated)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        self.refresh()

    # -- contents --------------------------------------------------------

    def refresh(self):
        """Rebuild the tree from the live Help menu.

        Safe to call when there is no menu bar yet - a headless test builds the
        sidebar before the menus in some suites, and an empty Help section is a
        better answer there than an exception.
        """
        self.tree.clear()

        menu = self._helpMenu()
        if menu is None:
            return

        self._fill(self.tree.invisibleRootItem(), menu)
        self.tree.expandAll()

    def _helpMenu(self):
        """The window's Help QMenu, or None.

        Read from ``win.menus``, the by-name registry Block D-c added so whole
        menus could be enabled as a group. Reaching into the menu bar's children
        and matching on the title would break in every language but English.
        """
        menus = getattr(self.win, 'menus', None)
        if not menus:
            return None
        return menus.get('help')

    def _fill(self, parent, menu):
        """Copy ``menu``'s actions under ``parent``, recursing into submenus."""
        for action in menu.actions():
            if action.isSeparator():
                continue

            submenu = action.menu()

            text = action.text().replace('&', '')
            item = QtWidgets.QTreeWidgetItem(parent, [text])
            item.setToolTip(0, action.toolTip().replace('&', ''))

            icon = action.icon()
            if icon is not None and not icon.isNull():
                item.setIcon(0, icon)

            if submenu is not None:
                # A submenu is a heading, not something to trigger. Bold, and
                # its children carry the actions.
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                self._fill(item, submenu)
                continue

            # The action itself, so triggering the row does whatever the menu
            # entry does. Stored on the item rather than looked up by text,
            # which would break under translation.
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, action)

            if not action.isEnabled():
                item.setDisabled(True)

    # -- activation ------------------------------------------------------

    def _handleActivated(self, item, _column):
        action = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if action is None:
            # A submenu heading. Fold or unfold it instead, which is what
            # activating a parent row means everywhere else.
            item.setExpanded(not item.isExpanded())
            return

        action.trigger()

    # -- translation -----------------------------------------------------

    def retranslate(self):
        """Rebuild, because every label here comes from the menu."""
        self.refresh()
