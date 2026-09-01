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
from reggie.core import session
from libs import lh, lz77
from reggie.core.dirty import setSetting, SetDirty
from reggie.io.misc import IsNSMBLevel, LoadLevelNames, ChooseLevelNameDialog
from reggie.core.level import Level_NSMBW
from reggie.ui.collab_controller import set_action_allowed


class LevelIO:
    """Owns level file open/save and the load pipeline."""

    def __init__(self, win):
        self.win = win

    def _refuseSaveInSession(self, what):
        """
        Blocks a save the running session does not permit (Block C - B3).

        Returns True when the caller must stop. The gate lives here rather than
        only on the QAction because disabling a menu item does not disable the
        function: HandleSave is reached from CheckDirty (window.py) and from
        several internal callers - closing the editor, restoring an autosave,
        switching level - none of which go through the menu.

        The rules, per Zement (2026-08-09):

        - **Save**: the host only. A Full client leads the session but does not
          own its file; two save authorities would be two sources of truth.
        - **Save as...**: nobody, the host included. It rewrites fileSavePath,
          which renames the session's level on one machine only - after which
          that peer is editing a file no one else can resolve by name. Same
          reasoning that already put "open by file" out of reach in a session.
        - **Save a copy as...**: nobody, for now. It is safe except when the
          target lands in the session's own stage folder, it is rarely used, and
          re-enabling it later with a destination check is cheap.
        """
        controller = getattr(self.win, '_collab', None)
        if controller is None:
            return False

        try:
            if not controller.is_active:
                return False
            allowed = bool(controller.isSaveAuthority())
        except Exception:
            # A broken controller must not stop someone saving their own work.
            return False

        if allowed and what == 'save':
            return False

        if what == 'save':
            message = ('Only the host can save the level during a '
                       'collaboration session.')
        elif what == 'saveas':
            message = ('"Save as" is not available during a collaboration '
                       'session: it would rename the level on your machine '
                       'only, and the other participants could no longer find '
                       'it.')
        else:
            message = ('"Save a copy as" is not available during a '
                       'collaboration session.')

        QtWidgets.QMessageBox.information(
            self.win, 'Collaboration', message)
        return True

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
            # In a session, a client asks the host first and the host's
            # broadcast is what actually loads it (Block C - B3, phase 3d).
            # Outside one, and for the host, this is True immediately.
            if not self._ProposeCollabSwitch(dlg.currentlevel, 1):
                return

            self.win.LoadLevel(dlg.currentlevel, False, 1)

    def _ClearDirtyForSavedFile(self, file_path):
        """Mark every area of a just-saved file as clean.

        Since Block D-c, `globals_.Dirty` is per session, so assigning it False
        would only clear the tab that happened to be in front. Saving is per
        *file* - Level.save() serialises every area in one pass - so every
        session sharing that path is now clean, and leaving the others marked
        would put a `*` on tabs whose work is safely on disk.

        Note what this does NOT do: rebind the sessions to a new path on Save
        As. They keep the path they were opened under, which is a pre-existing
        gap (the handle is keyed by path in the manager) and not one a dirty
        marker should be reaching into. Recorded in DEFERRED_ITEMS.md.

        Falls back to the plain assignment when there is no manager, which is
        how the headless suites and the pre-session path run.
        """
        manager = globals_.get_session_manager()
        if manager is None:
            globals_.Dirty = False
            return

        manager.clear_dirty_for_file(file_path)

        # The active session may be on another file entirely (Save As from a
        # tab, with other files open), so clear it explicitly too.
        globals_.Dirty = False

    def _ProposeCollabSwitch(self, level, area):
        """
        Whether this editor may load a level itself, or has handed the decision
        to the host (Block C - B3, phase 3d).

        Returns True when the caller should go ahead - which is every case
        outside a session, so the ordinary editor is unaffected.

        Guarded and lazy like the other collab hooks here, but note the
        *difference* in what a failure means: those report something that has
        already happened, so swallowing an error is right. This one asks
        permission, and an error means the answer is unknown. Loading anyway
        would be the pre-3d behaviour - moving the session without the host's
        consent - so an unknown answer allows the load only when there is
        demonstrably no session to consult.
        """
        controller = getattr(self.win, '_collab', None)
        if controller is None:
            return True

        try:
            if not controller.is_active:
                return True
            return bool(controller.proposeLevelChange(level, area))
        except Exception:
            # A broken controller must not stop a lone user opening a level;
            # is_active having raised means we cannot even tell if there is a
            # session, and the editor being unusable is the worse failure.
            return True
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
        if self._refuseSaveInSession('save'):
            return False

        if not self.win.fileSavePath or self.win.fileSavePath.endswith('.arc.LH'):
            # Delegate save to HandleSaveAs function. Flagged as coming from
            # Save so the session gate is not applied twice - see HandleSaveAs.
            return self.HandleSaveAs(_from_save=True)

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
                return self.HandleSaveAs(_from_save=True)

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

        # Saving is per *file*: Level.save() serialises every area in one pass,
        # so a save from any tab persists all of them and leaving the other tabs
        # marked dirty would misreport that. Assigning globals_.Dirty would only
        # clear the active session's flag.
        self._ClearDirtyForSavedFile(self.win.fileSavePath)
        globals_.AutoSaveDirty = False
        self.win.UpdateTitle()

        setSetting('AutoSaveFilePath', self.win.fileSavePath)
        setSetting('AutoSaveFileData', 'x')

        # Saving resets the undo history (Block C - A1)
        self.win.undoStack.clear()

        # Tell the session, so the other participants end up with the same file
        # on disk (Block C - B3). Only the host reaches this - the gate above
        # is what makes that true - and the announcement carries the bytes that
        # were just written, not a re-serialisation.
        self._NotifyCollabSaved(data)
        return True

    def _NotifyCollabSaved(self, data):
        """
        Publishes a save to the collaboration session.

        Guarded and lazy for the same reason as _NotifyCollabLevelChanged: a
        networking problem must never turn a successful save into a failure. The
        file is already on disk by the time this runs.
        """
        controller = getattr(self.win, '_collab', None)
        if controller is None:
            return

        try:
            controller.notifyLevelSaved(data)
        except Exception:
            pass

    def HandleSaveAs(self, copy = False, _from_save = False):
        """
        Save a level back to the archive, with a new filename. Returns whether
        saving was successful.

        `_from_save` is set when HandleSave delegated here because there is no
        path to save to yet. That call has already been through the session
        gate, so re-running it would refuse a save the host is entitled to and
        show a second dialog for one refusal.
        """
        if not _from_save and self._refuseSaveInSession(
                'savecopyas' if copy else 'saveas'):
            return False

        fn = QtWidgets.QFileDialog.getSaveFileName(self.win,
            globals_.trans.string('FileDlgs', 8 if copy else 3),
            '',
            globals_.trans.string('FileDlgs', 1) + ' (*' + '.arc' + ');;' +
            globals_.trans.string('FileDlgs', 10) + ' (*' + '.arc.LZ'+ ');;' +
            globals_.trans.string('FileDlgs', 2) + ' (*)'
        )[0]

        if fn == '':  # No filename given - abort
            return False

        # Kept across the reassignment below, because the sessions are still
        # keyed under it and the rename after a successful write needs both
        # ends. Only meaningful when `copy` is False - a copy deliberately
        # leaves the editor on the file it had open.
        previous_path = self.win.fileSavePath

        if not copy:
            globals_.AutoSaveDirty = False
            # Save As writes every area too - see _ClearDirtyForSavedFile. The
            # path it clears is the one the sessions still carry, which is the
            # old one: fileSavePath is only reassigned on the next line.
            self._ClearDirtyForSavedFile(self.win.fileSavePath)

            self.win.fileSavePath = fn
            if globals_.UseFullFilepath:
                self.win.fileTitle = fn
            else:
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
            # The sessions are still keyed under the old path (Block D-d.3).
            # A handle is keyed by path, so without this the manager believes
            # they are on a file the editor is no longer editing: opening the
            # *new* path would build a second handle over bytes already open -
            # two undo stacks over one file - and opening the old one would
            # find sessions for a file that may not exist any more.
            #
            # After the write, not before: a rename recorded for a save that
            # then failed would leave the manager describing something that
            # never happened.
            self._RebindSessionsTo(previous_path, fn)

            setSetting('AutoSaveFilePath', fn)
            setSetting('AutoSaveFileData', 'x')

            self.win.UpdateTitle()
            self.win.RecentMenu.AddToList(self.win.fileSavePath)

            # Saving resets the undo history (Block C - A1)
            self.win.undoStack.clear()

        return True

    def _RebindSessionsTo(self, old_path, new_path):
        """Move every session on ``old_path`` to ``new_path``. True if moved.

        Save As leaves the editor working on the new file, so the manager has
        to agree. Guarded rather than assumed: there is no manager in the
        headless suites, and a refusal is a real answer here - the manager
        declines when the new path is *already* open, because merging would
        give one file two handles' worth of undo history and picking one to
        discard would silently drop a user's edits.

        A refusal is reported rather than raised. The bytes are on disk either
        way, and losing a save because the bookkeeping could not be tidied is
        the worse outcome; the sessions simply keep the path they had, which is
        the pre-D-d.3 behaviour.

        **`win.fileSavePath` must already be the new path when this runs.** The
        two are one fact - which file the editor is working on - kept in two
        places, and a rename applied to only one of them is worse than no
        rename at all: the manager then holds sessions under a path the window
        does not know about, so opening that file again finds no handle, loads
        it a second time, and builds fresh scene items over a level whose old
        items are still live ("wrapped C/C++ object of type ObjectItem has been
        deleted"). HandleSaveAs assigns fileSavePath before the write and calls
        this after it, so the order holds there.
        """
        manager = globals_.get_session_manager()
        if manager is None:
            return False

        try:
            return bool(manager.rename_file(old_path, new_path))
        except Exception:
            return False
    def HandleSaveCopyAs(self):
        """
        Save a level back to the archive, with a new filename, but does not store this filename
        """
        self.win.HandleSaveAs(True)
    def LoadLevel(self, name, isFullPath, areaNum, add=False):
        """
        Load a level from NSMBW into the editor.

        ``add`` opens the level **alongside** whatever is already open rather
        than replacing it (D-d.3b). The directory listing passes it; every
        other caller replaces, which is what File -> Open, New Level and a
        patch switch all mean.
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
            # "Just an area change" - but only if that level is still open.
            # fileSavePath survives every session being closed, so on its own it
            # would send a genuine re-open down the area-change branch, where
            # globals_.Level is None and there is nothing to change the area of.
            #
            # What "same" has to mean is *"is this file the one currently in
            # front, with its level still loaded"* - because the branch it
            # guards changes area within `globals_.Level`, and that is the
            # active session's level.
            #
            # Both halves matter since D-d.3b, and each has drawn blood:
            #
            # - Comparing against `win.fileSavePath` (a property resolving
            #   through the process-wide manager) let a *second* ReggieWindow
            #   booting while the first one's sessions were open read the first
            #   window's path, take this branch, and rebuild its palette from
            #   the other window's scene items - "wrapped C/C++ object of type
            #   ObjectItem has been deleted".
            # - Comparing against `win._fileSavePath` alone is stale the other
            #   way: activation moves the file in front without assigning it,
            #   so opening a *different* file after switching tabs took this
            #   branch and changed the area of whatever was active instead.
            #
            # Asking the active session is the question itself, with no cached
            # answer to go stale. Falls back to the window's own value when
            # there is no manager, which is how the pre-session path runs.
            # The second-window case needs one more condition: the manager is
            # process-wide, so a window that has not loaded anything yet must
            # not adopt another window's session. `_fileSavePath` is per window
            # and is None until this window loads something, which is exactly
            # that test.
            manager = globals_.get_session_manager()
            active = manager.active if manager is not None else None
            current_path = (active.file_path if active is not None
                            else self.win._fileSavePath)

            same = (name == current_path
                    and self.win._fileSavePath is not None
                    and getattr(globals_, 'Level', None) is not None)
            
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

                # Set the filepath variables.
                #
                # Read back from `name`, not from `win.fileSavePath` (D-d.3b).
                # That is a property resolving through the *active* session now,
                # and the session for this file does not exist yet - so until it
                # does, reading it answers with the file this load is replacing
                # or joining, and this block would open the wrong archive.
                self.win.fileSavePath = name
                if globals_.UseFullFilepath:
                    self.win.fileTitle = name
                else:
                    self.win.fileTitle = os.path.basename(name)

                # Open the file
                with open(name, 'rb') as fileobj:
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
                    if globals_.UseFullFilepath:
                        self.win.fileTitle = self.win.fileSavePath
                    else:
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
        #
        # **Not when adding a file** (D-d.3b). Since D-c.1 each session owns its
        # scene, so `win.scene` is the *active* session's - and while this was
        # only ever reached after close_all() had emptied the manager, the scene
        # being cleared was about to be discarded anyway. Adding a second file
        # makes that no longer true: clearing here would destroy the first
        # file's items while its sessions are still live, which is the "wrapped
        # C/C++ object of type ObjectItem has been deleted" crash by another
        # route. The new session arrives with an empty scene of its own, so
        # there is nothing to clear for it either.
        if not add:
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
            # `name` rather than win.fileSavePath, for the reason above: the
            # session that would answer for this file does not exist yet.
            self.win.LoadLevel_NSMBW(levelData, areaNum, add=add,
                                     file_path=name if not new else None)
        else:
            # We have already loaded this area's data - it's stored as
            # AbstractAreas in the Level. This means we do not have to open and
            # optionally decompress the level file.
            #
            # Prefer a session over Level.changeArea() (Block D, phase D-4):
            # changeArea unloads the outgoing area, and Area.unload() discards
            # its parsed data without serialising, so any unsaved edit in it is
            # lost. open_area keeps it live in its own session instead. The
            # changeArea fallback stays for the case where no manager is
            # installed, which is how the headless suites run.
            if session.open_area(areaNum) is None:
                globals_.Level.changeArea(areaNum)

            self.win.ResetPalette()

        # Fill up the area list
        self.win.areaComboBox.clear()

        for area in globals_.Level.areas:
            self.win.areaComboBox.addItem(globals_.trans.string('AreaCombobox', 0, '[num]', area.areanum))

        self.win.areaComboBox.setCurrentIndex(areaNum - 1)

        # Put the patch controls in step. Was `updatePatchComboBox()`; the
        # combo box went in D-d.1b and this is the seam every patch view shares.
        from reggie.io.gamedef import RefreshPatchSelector
        RefreshPatchSelector()

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
        # Through set_action_allowed, not setEnabled: a collaboration session
        # may forbid these regardless of what the level allows, and this runs
        # after the session has applied its permissions. Setting them directly
        # here is what re-enabled Backgrounds and the area actions for an Editor
        # client on every level load.
        set_action_allowed('addarea', len(globals_.Level.areas) < 4)
        set_action_allowed('importarea', len(globals_.Level.areas) < 4)
        set_action_allowed('deletearea', len(globals_.Level.areas) > 1)
        set_action_allowed('backgrounds', len(globals_.Area.zones) > 0)

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

        # The undo history refers to items of the previous level/area, so
        # reset it (Block C - A1: history resets on level load & area switch)
        self.win.undoStack.clear()

        # Tell a running collaboration session, for the same reason the undo
        # stack is cleared: every peer's view now refers to a different level or
        # area. A host re-publishes the room info and pushes a fresh snapshot;
        # without this the clients kept editing the previous level and neither
        # side was told (Block C - B1).
        self._NotifyCollabLevelChanged()

        # If we got this far, everything worked! Return True.
        return True

    def _NotifyCollabLevelChanged(self):
        """
        Republishes the level to collaboration peers after a load or area
        switch.

        Fully guarded and lazy: the collab package is only imported when a
        session exists, and a networking problem must never turn a successful
        level load into a failure.
        """
        controller = getattr(self.win, '_collab', None)
        if controller is None:
            return

        try:
            controller.notifyLevelChanged()
        except Exception:
            pass
    def newLevel(self):
        # Create the new level object, and the session that owns it. Opening
        # the session first means globals_.Level resolves while new() runs.
        level = Level_NSMBW()

        # `_fileSavePath`, not the property (D-d.3b). LoadLevel has already set
        # it to None for a new level, but the property resolves through the
        # *active* session - which is still the previous file until this call
        # replaces it. Reading the property here gave the new empty level the
        # old level's path, so it was no longer "untitled" and a later load of
        # that same path took the cheap area-change route instead of reloading.
        session.open_level(level, self.win._fileSavePath, 1)

        # Load it
        level.new()

        # Prepare the object picker
        self.win.objUseLayer1.setChecked(True)

        self.win.objPicker.LoadFromTilesets()

        self.win.objAllTab.setCurrentIndex(0)
        self.win.objAllTab.setTabEnabled(0, True)
        self.win.objAllTab.setTabEnabled(1, False)
        self.win.objAllTab.setTabEnabled(2, False)
        self.win.objAllTab.setTabEnabled(3, False)

        self.win.actions['swapobjectstypes'].setEnabled(True)
        self.win.actions['swapobjectstilesets'].setEnabled(True)

        # Reset Quick Paint Tool for new level
        if hasattr(self.win, 'qpt_palette') and self.win.qpt_palette is not None:
            try:
                self.win.qpt_palette.reset()
            except Exception as e:
                print(f"[QPT] Warning: Could not reset QPT: {e}")
    def LoadLevel_NSMBW(self, levelData, areaNum, add=False, file_path=None):
        """
        Performs all level-loading tasks specific to New Super Mario Bros. Wii levels.
        Do not call this directly - use LoadLevel instead!

        ``add`` opens the level alongside what is open rather than replacing it
        (D-d.3b). ``file_path`` names the file being loaded; it must be passed
        when adding, because `win.fileSavePath` is now a property resolving
        through the *active* session - which is still the previous file until
        the new session exists.
        """
        path = self.win.fileSavePath if file_path is None else file_path

        if add:
            # **The session first, then the level** (D-d.3b).
            #
            # `Level_NSMBW()` runs new(), which publishes its default area
            # through `set_current_area` - and that writes to whichever session
            # is *active*. With open_level that was harmless: close_all() had
            # already emptied the manager, so there was nothing to write over.
            # Adding a file leaves the previous session active, so constructing
            # the level first stamped area 1 over it - measured: two tabs both
            # claiming "01-01: 1" after opening a second file, when one of them
            # was area 2.
            #
            # Opening an empty session first gives those writes somewhere of
            # their own to land. The same ordering `open_area` uses, for the
            # same reason.
            session.add_level(None, path, areaNum)
            level = Level_NSMBW()

            # The session was opened with no level, because the level could not
            # exist yet. Bind them now that it does.
            manager = globals_.get_session_manager()
            if manager is not None and manager.active is not None:
                manager.active.handle.level = level
        else:
            # Create the new level object, and the session that owns it
            level = Level_NSMBW()
            session.open_level(level, path, areaNum)

        # Load it
        if not level.load(levelData, areaNum):
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
