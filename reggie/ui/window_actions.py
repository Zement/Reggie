"""Standalone window action handlers extracted from ``ReggieWindow``.

First extraction of the Phase 2 ``ReggieWindow`` breakup (see
_docs/plan/REFACTORING_ANALYSIS.md). These four handlers were chosen as the
pilot because they are the *least* coupled code in the class: measured across
the whole window, they touch **zero** ``self.<window-state>`` attributes and
nothing else in the window calls into them. They are pure dialog / help-page
poppers, so moving them cannot change window behaviour.

Pattern (the one the rest of Phase 2 follows): a plain controller object that
holds a reference to the window (``self.win``) and is composed onto it — *not*
a mixin, *not* inheritance. ``ReggieWindow`` keeps thin delegator methods so
that existing action wiring (``createMenubar`` connects ``QAction`` triggers
to ``self.AboutBox`` etc.) resolves unchanged.

Because these particular bodies never read window state, they are transplanted
verbatim; the ``self.win`` handle is available for handlers extracted later
that do need it.
"""

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_
from reggie.ui.dialogs import AboutDialog, MetaInfoDialog
from reggie.core.dirty import SetDirty
from reggie.io.misc import module_path


class WindowActions:
    """Dialog- and help-related actions for the main editor window."""

    def __init__(self, win):
        self.win = win

    def AboutBox(self):
        """
        Shows the about box
        """
        AboutDialog().exec()

    def HandleInfo(self):
        """
        Records the Level Meta Information
        """
        if globals_.Area.areanum == 1:
            dlg = MetaInfoDialog()
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                globals_.Area.Metadata.setStrData('Title', dlg.levelName.text())
                globals_.Area.Metadata.setStrData('Author', dlg.Author.text())
                globals_.Area.Metadata.setStrData('Group', dlg.Group.text())
                globals_.Area.Metadata.setStrData('Website', dlg.Website.text())

                SetDirty()
                return
        else:
            dlg = QtWidgets.QMessageBox()
            dlg.setText(globals_.trans.string('InfoDlg', 14))
            dlg.exec()

    def HelpBox(self):
        """
        Shows the help box
        """
        mod_path = module_path()

        file_path = os.path.join('reggiedata', 'help', 'index.html')
        if mod_path is None:
            file_path = os.path.join(os.getcwd(), file_path)
        else:
            file_path = os.path.join(mod_path, file_path)

        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(file_path))

    def TipBox(self):
        """
        Reggie Next Tips and Commands
        """
        mod_path = module_path()

        file_path = os.path.join('reggiedata', 'help', 'tips.html')
        if mod_path is None:
            file_path = os.path.join(os.getcwd(), file_path)
        else:
            file_path = os.path.join(mod_path, file_path)

        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(file_path))
