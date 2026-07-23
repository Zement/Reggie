"""File-I/O orchestration extracted from ``ReggieWindow`` (Phase 2).

New-level / open / save / save-as / save-copy plus the level loaders
(``LoadLevel``, ``newLevel``, ``LoadLevel_NSMBW``). ~400 lines. All module-level
names this needs are top-level imports in reggie.py, so they're imported here at
module top (no lazy imports).

``ReggieWindow`` keeps thin delegators (with exact signatures) because these are
QAction targets referenced from ``MenuBuilder`` (``self.win.HandleSave`` etc.)
AND ``LoadLevel`` is called cross-module via ``globals_.mainWindow.LoadLevel``
(``misc.py``). Controller-internal calls (``self.LoadLevel``, ``self.HandleSaveAs``,
``self.newLevel``, ``self.LoadLevel_NSMBW``) stay ``self.…``.
"""

import os

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_
from libs import lh, lz77
from reggie.core.dirty import setSetting, SetDirty
from reggie.io.misc import IsNSMBLevel, LoadLevelNames, ChooseLevelNameDialog
from reggie.core.level import Level_NSMBW


class LevelIO:
    """Owns level file open/save and the load pipeline."""

    def __init__(self, win):
        self.win = win

    def HandleNewLevel(self):
        """
        Create a new level
        """
        if self.win.CheckDirty(): return
        self.win.LoadLevel(None, False, 1)
    def HandleOpenFromName(self):
        """
        Open a level using the level picker
        """
        if self.win.CheckDirty(): return

        LoadLevelNames()
        dlg = ChooseLevelNameDialog()
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.win.LoadLevel(dlg.currentlevel, False, 1)
    def HandleOpenFromFile(self):
        """
        Open a level using the filename
        """
        if self.win.CheckDirty(): return

        filetypes = ''
        filetypes += globals_.trans.string('FileDlgs', 9) + ' (*.arc *.arc.LH *.arc.LZ);;'   # *.arc, *arc.LH, *.arc.LZ
        filetypes += globals_.trans.string('FileDlgs', 1) + ' (*.arc);;'            # *.arc
        filetypes += globals_.trans.string('FileDlgs', 5) + ' (*.arc.LH);;'         # *.arc.LH
        filetypes += globals_.trans.string('FileDlgs', 10) + ' (*.arc.LZ);;'         # *.arc.LZ
        filetypes += globals_.trans.string('FileDlgs', 2) + ' (*)'                  # *
        fn = QtWidgets.QFileDialog.getOpenFileName(self.win, globals_.trans.string('FileDlgs', 0), '', filetypes)[0]
        if fn == '': return
        self.win.LoadLevel(str(fn), True, 1)
    def HandleSave(self):
        """
        Save a level back to the archive. Returns whether saving was successful.
        """
        if not self.win.fileSavePath or self.win.fileSavePath.endswith('.arc.LH'):
            # Delegate save to HandleSaveAs function
            return self.win.HandleSaveAs()

        data = globals_.Level.save()

        # maybe need to compress the data
        if self.win.fileSavePath.endswith(".arc.LZ"):
            compressed = lz77.CompressLZ77(data)

            if compressed is None:
                # Error during compression
                QtWidgets.QMessageBox.warning(None,
                    globals_.trans.string('Err_Save', 0),
                    globals_.trans.string('Err_Save', 3, '[file-size]', len(data))
                )

                # Delegate to HandleSaveAs
                return self.win.HandleSaveAs()

            data = compressed

        # maybe pad with null bytes
        if globals_.EnablePadding:
            pad_length = globals_.PaddingLength - len(data)

            if pad_length < 0:
                # err: orig data is longer than padding data
                QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Save', 0), globals_.trans.string('Err_Save', 2, '[orig-len]', len(data), '[pad-len]', globals_.PaddingLength))
                return False

            data += bytes(pad_length)

        try:
            with open(self.win.fileSavePath, 'wb') as f:
                f.write(data)
        except IOError as e:
            QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Save', 0),
                                          globals_.trans.string('Err_Save', 1, '[err1]', e.args[0], '[err2]', e.args[1]))
            return False

        globals_.Dirty = False
        globals_.AutoSaveDirty = False
        self.win.UpdateTitle()

        setSetting('AutoSaveFilePath', self.win.fileSavePath)
        setSetting('AutoSaveFileData', 'x')
        return True
    def HandleSaveAs(self, copy = False):
        """
        Save a level back to the archive, with a new filename. Returns whether
        saving was successful.
        """
        fn = QtWidgets.QFileDialog.getSaveFileName(self.win,
            globals_.trans.string('FileDlgs', 8 if copy else 3),
            '',
            globals_.trans.string('FileDlgs', 1) + ' (*' + '.arc' + ');;' +
            globals_.trans.string('FileDlgs', 10) + ' (*' + '.arc.LZ'+ ');;' +
            globals_.trans.string('FileDlgs', 2) + ' (*)'
        )[0]

        if fn == '':  # No filename given - abort
            return False

        if not copy:
            globals_.AutoSaveDirty = False
            globals_.Dirty = False

            self.win.fileSavePath = fn
            self.win.fileTitle = os.path.basename(fn)

        data = globals_.Level.save()

        # maybe need to compress the data
        if fn.endswith(".arc.LZ"):
            compressed = lz77.CompressLZ77(data)

            if compressed is None:
                # Error during compression
                QtWidgets.QMessageBox.warning(None,
                    globals_.trans.string('Err_Save', 0),
                    globals_.trans.string('Err_Save', 3, '[file-size]', len(data))
                )

                return False

            data = compressed

        # maybe pad with null bytes
        if globals_.EnablePadding:
            pad_length = globals_.PaddingLength - len(data)

            if pad_length < 0:
                # err: orig data is longer than padding data
                QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Save', 0), globals_.trans.string('Err_Save', 2, '[orig-len]', len(data), '[pad-len]', globals_.PaddingLength))
                return False

            data += bytes(pad_length)

        with open(fn, 'wb') as f:
            f.write(data)

        if not copy:
            setSetting('AutoSaveFilePath', fn)
            setSetting('AutoSaveFileData', 'x')

            self.win.UpdateTitle()
            self.win.RecentMenu.AddToList(self.win.fileSavePath)

        return True
    def HandleSaveCopyAs(self):
        """
        Save a level back to the archive, with a new filename, but does not store this filename
        """
        self.win.HandleSaveAs(True)
    def LoadLevel(self, name, isFullPath, areaNum):
        """
        Load a level from NSMBW into the editor.
        """
        new = name is None
        same = False

        if not new:
            checknames = []
            if isFullPath:
                checknames = [name]
            else:
                for ext in globals_.FileExtentions:
                    checknames.append(os.path.join(globals_.gamedef.GetStageGamePath(), name + ext))

            for checkname in checknames:
                if os.path.isfile(checkname):
                    break
            else:
                QtWidgets.QMessageBox.warning(self.win, 'Reggie!',
                                              globals_.trans.string('Err_CantFindLevel', 0, '[name]', checkname),
                                              QtWidgets.QMessageBox.StandardButton.Ok)
                return False

            if not IsNSMBLevel(checkname):
                QtWidgets.QMessageBox.warning(self.win, 'Reggie!', globals_.trans.string('Err_InvalidLevel', 0),
                                              QtWidgets.QMessageBox.StandardButton.Ok)
                return False

            name = checkname
            same = name == self.win.fileSavePath  # Just an area change
            
            # If we just discarded changes, force a full reload even if it's the same level
            if hasattr(self.win, 'justDiscardedChanges') and self.win.justDiscardedChanges:
                same = False
                self.win.justDiscardedChanges = False

        # Get the file path, if possible
        if new:
            # Set the filepath variables
            self.win.fileSavePath = None
            self.win.fileTitle = 'untitled'

        elif not same:

            # Get the data
            if not globals_.RestoredFromAutoSave:

                # Set the filepath variables
                self.win.fileSavePath = name
                self.win.fileTitle = os.path.basename(self.win.fileSavePath)

                # Open the file
                with open(self.win.fileSavePath, 'rb') as fileobj:
                    levelData = fileobj.read()

                # Decompress, if needed
                if (levelData[0] & 0xF0) == 0x40:  # If LH-compressed
                    try:
                        levelData = lh.UncompressLH(levelData)
                    except IndexError:
                        QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Decompress', 0),
                                                      globals_.trans.string('Err_Decompress', 1, '[file]', name))
                        return False
                elif not levelData.startswith(b"U\xAA8-"):  # If LZ-compressed
                    try:
                        levelData = lz77.UncompressLZ77(levelData)
                    except IndexError:
                        QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Decompress', 0),
                                                      globals_.trans.string('Err_Decompress', 2, '[file]', name))
                        return False

            else:
                # Auto-saved level. Check if there's a path associated with it:

                if globals_.AutoSavePath == 'None':
                    self.win.fileSavePath = None
                    self.win.fileTitle = globals_.trans.string('WindowTitle', 0)
                else:
                    self.win.fileSavePath = globals_.AutoSavePath
                    self.win.fileTitle = os.path.basename(name)

                # Get the level data
                levelData = globals_.AutoSaveData
                SetDirty(noautosave=True)

                # Turn off the autosave flag
                globals_.RestoredFromAutoSave = False

        # Turn the dirty flag off, and keep it that way
        globals_.Dirty = False
        globals_.DirtyOverride += 1

        # First, clear out the existing level.
        self.win.scene.clearSelection()
        self.win.CurrentSelection = []
        self.win.scene.clear()

        # Clear out all level-thing lists
        for thingList in (self.win.spriteList, self.win.entranceList, self.win.locationList, self.win.pathList, self.win.commentList):
            thingList.clear()
            thingList.selectionModel().setCurrentIndex(QtCore.QModelIndex(), QtCore.QItemSelectionModel.SelectionFlag.Clear)

        # Reset these here, because if they are set after
        # creating the objects, they use the old values.
        globals_.CurrentLayer = 1
        globals_.Layer0Shown = True
        globals_.Layer1Shown = True
        globals_.Layer2Shown = True

        # Also enable things that use 'True' by default
        globals_.SpritesShown = True
        globals_.LocationsShown = True
        globals_.PathsShown = True
        globals_.CommentsShown = True

        # Prevent things from snapping when they're created
        globals_.OverrideSnapping = True

        # Load the actual level
        if new:
            self.win.newLevel()
        elif not same:
            self.win.LoadLevel_NSMBW(levelData, areaNum)
        else:
            # We have already loaded this area's data - it's stored as
            # AbstractAreas in the Level. This means we do not have to open and
            # optionally decompress the level file. Hence, we can just relay
            # this to the level.
            globals_.Level.changeArea(areaNum)
            self.win.ResetPalette()

        # Fill up the area list
        self.win.areaComboBox.clear()

        for area in globals_.Level.areas:
            self.win.areaComboBox.addItem(globals_.trans.string('AreaCombobox', 0, '[num]', area.areanum))

        self.win.areaComboBox.setCurrentIndex(areaNum - 1)

        # Update patch combo box
        self.win.updatePatchComboBox()

        # Refresh object layouts
        for layer in globals_.Area.layers:
            for obj in layer:
                obj.updateObjCache()

        for sprite in globals_.Area.sprites:
            sprite.UpdateDynamicSizing()
            sprite.ImageObj.positionChanged()

        # Scroll to the initial entrance
        startEntID = globals_.Area.startEntrance
        startEnt = None
        for ent in globals_.Area.entrances:
            if ent.entid == startEntID:
                self.win.view.centerOn(ent)
                break
        else:
            self.win.view.centerOn(0, 0)

        self.win.ZoomTo(100.0)

        # Reset some editor things
        self.win.actions['showlay0'].setChecked(True)
        self.win.actions['showlay1'].setChecked(True)
        self.win.actions['showlay2'].setChecked(True)
        self.win.actions['showsprites'].setChecked(True)
        self.win.actions['showlocations'].setChecked(True)
        self.win.actions['showpaths'].setChecked(True)
        self.win.actions['showcomments'].setChecked(True)
        self.win.actions['addarea'].setEnabled(len(globals_.Level.areas) < 4)
        self.win.actions['importarea'].setEnabled(len(globals_.Level.areas) < 4)
        self.win.actions['deletearea'].setEnabled(len(globals_.Level.areas) > 1)
        self.win.actions['backgrounds'].setEnabled(len(globals_.Area.zones) > 0)

        # Turn snapping back on
        globals_.OverrideSnapping = False

        # Turn the dirty flag off
        globals_.DirtyOverride -= 1
        self.win.UpdateTitle()

        # Update UI things
        self.win.scene.update()

        self.win.levelOverview.Reset()
        self.win.levelOverview.update()

        if new:
            SetDirty()

        elif not same:
            # Add the path to Recent Files
            self.win.RecentMenu.AddToList(self.win.fileSavePath)

        # Reset Quick Paint Tool when level/area changes
        if hasattr(self.win, 'qpt_palette') and self.win.qpt_palette is not None:
            try:
                self.win.qpt_palette.reset()
            except Exception as e:
                print(f"[QPT] Warning: Could not reset QPT: {e}")

        # If we got this far, everything worked! Return True.
        return True
    def newLevel(self):
        # Create the new level object
        globals_.Level = Level_NSMBW()

        # Load it
        globals_.Level.new()

        # Prepare the object picker
        self.win.objUseLayer1.setChecked(True)

        self.win.objPicker.LoadFromTilesets()

        self.win.objAllTab.setCurrentIndex(0)
        self.win.objAllTab.setTabEnabled(0, True)
        self.win.objAllTab.setTabEnabled(1, False)
        self.win.objAllTab.setTabEnabled(2, False)
        self.win.objAllTab.setTabEnabled(3, False)

        # Reset Quick Paint Tool for new level
        if hasattr(self.win, 'qpt_palette') and self.win.qpt_palette is not None:
            try:
                self.win.qpt_palette.reset()
            except Exception as e:
                print(f"[QPT] Warning: Could not reset QPT: {e}")
    def LoadLevel_NSMBW(self, levelData, areaNum):
        """
        Performs all level-loading tasks specific to New Super Mario Bros. Wii levels.
        Do not call this directly - use LoadLevel instead!
        """
        # Create the new level object
        globals_.Level = Level_NSMBW()

        # Load it
        if not globals_.Level.load(levelData, areaNum):
            raise Exception

        # Check for unknown sprite IDs and show warning icon in status bar
        if hasattr(globals_.Area, 'unknown_sprite_ids') and globals_.Area.unknown_sprite_ids:
            sprite_ids = sorted(globals_.Area.unknown_sprite_ids)
            if len(sprite_ids) == 1:
                msg = globals_.trans.string('Err_UnknownSprite', 0, '[id]', str(sprite_ids[0]))
            else:
                msg = globals_.trans.string('Err_UnknownSprite', 1, '[ids]', ', '.join(map(str, sprite_ids)))
            self.win.AddWarningIcon(msg)

        self.win.ResetPalette()
