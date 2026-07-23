"""Stamp-palette handlers extracted from ``ReggieWindow`` (Phase 2 refactor).

Third extraction of the ``ReggieWindow`` breakup (see
_docs/plan/REFACTORING_ANALYSIS.md). Handlers for the stamp chooser in the
palette dock: add / remove / open-set / save-set / selection-changed /
name-edited.

Window state reached through ``self.win``: ``scene``, ``stampChooser``,
``stampRemoveBtn``, ``stampNameEdit``, and ``encodeObjects`` (a window method
belonging to the not-yet-extracted clipboard cluster). Controller-internal calls
(``handleStampSelectionChanged``) stay ``self.…``.

``Stamp`` is imported lazily inside the methods that need it — mirroring
``reggie.py``, which defers ``from sidelists import Stamp`` to avoid creating Qt
objects before the ``QApplication`` exists.

``ReggieWindow`` keeps thin delegators so the signal connections wired in
``SetupDocksAndPanels`` (``self.handleStampsAdd`` etc.) resolve unchanged.
"""

from PyQt6 import QtWidgets

from reggie.core import globals_
from reggie.core.levelitems import ObjectItem, SpriteItem


class StampController:
    """Owns the stamp-chooser palette interactions."""

    def __init__(self, win):
        self.win = win

    def handleStampsAdd(self):
        """
        Handles the "Add Stamp" btn being clicked
        """
        from reggie.ui.sidelists import Stamp

        # Create a ReggieClip
        selitems = self.win.scene.selectedItems()
        if not selitems: return
        clipboard_o = []
        clipboard_s = []
        ii = isinstance
        type_obj = ObjectItem
        type_spr = SpriteItem
        for obj in selitems:
            if ii(obj, type_obj):
                clipboard_o.append(obj)
            elif ii(obj, type_spr):
                clipboard_s.append(obj)
        RegClp = self.win.encodeObjects(clipboard_o, clipboard_s)

        # Create a Stamp
        self.win.stampChooser.addStamp(Stamp(RegClp, 'New Stamp'))

    def handleStampsRemove(self):
        """
        Handles the "Remove Stamp" btn being clicked
        """
        self.win.stampChooser.removeStamp(self.win.stampChooser.currentlySelectedStamp())
        self.handleStampSelectionChanged()

    def handleStampsOpen(self):
        """
        Handles the "Open Set..." btn being clicked
        """
        from reggie.ui.sidelists import Stamp

        filetypes = ''
        filetypes += globals_.trans.string('FileDlgs', 7) + ' (*.stamps);;'  # *.stamps
        filetypes += globals_.trans.string('FileDlgs', 2) + ' (*)'  # *
        fn = QtWidgets.QFileDialog.getOpenFileName(self.win, globals_.trans.string('FileDlgs', 6), '', filetypes)[0]
        if fn == '': return

        with open(fn, 'r', encoding='utf-8') as file:
            filedata = file.read()

        if not filedata.startswith('stamps\n------\n'): return

        filesplit = filedata.split('\n')[3:]
        for i in range(0, len(filesplit), 3):
            try:
                # Get data
                name = filesplit[i]
                rc = filesplit[i + 1]
            except IndexError:
                break

            self.win.stampChooser.addStamp(Stamp(rc, name))

    def handleStampsSave(self):
        """
        Handles the "Save Set As..." btn being clicked
        """
        filetypes = ''
        filetypes += globals_.trans.string('FileDlgs', 7) + ' (*.stamps);;'  # *.stamps
        filetypes += globals_.trans.string('FileDlgs', 2) + ' (*)'  # *
        fn = QtWidgets.QFileDialog.getSaveFileName(self.win, globals_.trans.string('FileDlgs', 3), '', filetypes)[0]
        if fn == '': return

        newdata = ''
        newdata += 'stamps\n'
        newdata += '------\n'

        for stampobj in self.win.stampChooser.model.items:
            newdata += '\n'
            newdata += stampobj.Name + '\n'
            newdata += stampobj.ReggieClip + '\n'

        with open(fn, 'w', encoding='utf-8') as f:
            f.write(newdata)

    def handleStampSelectionChanged(self):
        """
        Called when the stamp selection is changed
        """
        newStamp = self.win.stampChooser.currentlySelectedStamp()
        stampSelected = newStamp is not None
        self.win.stampRemoveBtn.setEnabled(stampSelected)
        self.win.stampNameEdit.setEnabled(stampSelected)

        newName = '' if not stampSelected else newStamp.Name
        self.win.stampNameEdit.setText(newName)

    def handleStampNameEdited(self):
        """
        Called when the user edits the name of the current stamp
        """
        stamp = self.win.stampChooser.currentlySelectedStamp()
        if not stamp:
            return

        text = self.win.stampNameEdit.text()
        stamp.Name = text
        stamp.update()

        # Try to get it to update!!! But fail. D:
        for i in range(3):
            self.win.stampChooser.updateGeometries()
            self.win.stampChooser.update(self.win.stampChooser.currentIndex())
            self.win.stampChooser.update()
            self.win.stampChooser.repaint()
