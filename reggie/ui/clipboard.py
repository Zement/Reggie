"""Clipboard / cut-copy-paste handlers extracted from ``ReggieWindow`` (Phase 2).

Fourth extraction of the ``ReggieWindow`` breakup (see
_docs/plan/REFACTORING_ANALYSIS.md). Covers cut/copy/paste, the ReggieClip
encode/decode/place routines, and the system-clipboard watcher.

Window state reached through ``self.win``: ``SelectionUpdateFlag``, ``scene``,
``actions``, ``clipboard``, ``systemClipboard``, ``levelOverview``,
``ZoomLevel``, ``view``, ``spriteList`` plus window methods this cluster calls
that live elsewhere on the window — ``ChangeSelectionHandler``, ``CreateObject``,
``CreateSprite``. Controller-internal calls (``encodeObjects``,
``getEncodedObjects``, ``placeEncodedObjects``) stay ``self.…``.

``placeEncodedObjects`` and ``getEncodedObjects`` are also called by other
modules via ``globals_.mainWindow.<name>(...)`` (``misc2.py``, ``sidelists.py``);
those resolve through the window's thin delegators, which keep the exact
signatures (``select``/``xOverride``/``yOverride``).
"""

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import SetDirty
from reggie.core.levelitems import ObjectItem, SpriteItem
from reggie.core.raw_data import RawData


class ClipboardController:
    """Owns cut/copy/paste and ReggieClip (de)serialization."""

    def __init__(self, win):
        self.win = win

    def TrackClipboardUpdates(self):
        """
        Catches systemwide clipboard updates
        """
        if globals_.Initializing: return
        clip = self.win.systemClipboard.text()
        if clip is not None and clip != '':
            clip = str(clip).strip()

            if clip.startswith('ReggieClip|') and clip.endswith('|%'):
                self.win.clipboard = clip.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')

                self.win.actions['paste'].setEnabled(True)
            else:
                self.win.clipboard = None
                self.win.actions['paste'].setEnabled(False)

    def Cut(self):
        """
        Cuts the selected items
        """
        self.win.SelectionUpdateFlag = True
        selitems = self.win.scene.selectedItems()
        self.win.scene.clearSelection()

        if selitems:
            clipboard_o = []
            clipboard_s = []
            ii = isinstance
            type_obj = ObjectItem
            type_spr = SpriteItem

            to_be_deleted = []
            for obj in selitems:
                if ii(obj, type_obj):
                    to_be_deleted.append(obj)
                    clipboard_o.append(obj)
                elif ii(obj, type_spr):
                    to_be_deleted.append(obj)
                    clipboard_s.append(obj)

            if clipboard_o or clipboard_s:
                SetDirty()
                self.win.actions['cut'].setEnabled(False)
                self.win.actions['paste'].setEnabled(True)
                self.win.clipboard = self.encodeObjects(clipboard_o, clipboard_s)
                self.win.systemClipboard.setText(self.win.clipboard)

            for obj in to_be_deleted:
                obj.delete()
                obj.setSelected(False)
                self.win.scene.removeItem(obj)

        self.win.levelOverview.update()
        self.win.SelectionUpdateFlag = False
        self.win.ChangeSelectionHandler()

    def Copy(self):
        """
        Copies the selected items
        """
        selitems = self.win.scene.selectedItems()
        if selitems:
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

            if clipboard_o or clipboard_s:
                self.win.actions['paste'].setEnabled(True)
                self.win.clipboard = self.encodeObjects(clipboard_o, clipboard_s)
                self.win.systemClipboard.setText(self.win.clipboard)

    def Paste(self):
        """
        Paste the selected items
        """
        if self.win.clipboard is not None:
            self.placeEncodedObjects(self.win.clipboard)

    def encodeObjects(self, clipboard_o, clipboard_s):
        """
        Encode a set of objects and sprites into a string
        """
        convclip = ['ReggieClip']

        # get objects
        clipboard_o.sort(key=lambda x: x.zValue())

        for item in clipboard_o:
            convclip.append('0:%d:%d:%d:%d:%d:%d:%d' % (
            item.tileset, item.type, item.layer, item.objx, item.objy, item.width, item.height))

        globals_.Area.spriteSettings = []
        for sprite in globals_.Area.sprites:
            sprite: SpriteItem # type hint

            if sprite.spritedata.format == RawData.Format.Extended:
                sprite.spritedata.original = sprite.spritedata[0:2] + len(globals_.Area.spriteSettings).to_bytes(4, 'big') + sprite.spritedata[6:]
                globals_.Area.spriteSettings.append(sprite.spritedata.blocks)

        # get sprites
        for item in clipboard_s:
            data = item.spritedata

            is_extended = globals_.Sprites[item.type].extendedSettings
            extended_id = int.from_bytes(data[2:6], 'big')
            extended_settings = globals_.Area.spriteSettings[extended_id] if is_extended else []
            extended_string = ':' if len(extended_settings) > 0 else ''
            for block in extended_settings:
                extended_string += block.hex()

            clip_string = '1:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d' % (item.type, item.objx, item.objy, data[0], data[1], data[2], data[3], data[4], data[5], data[7])
            convclip.append(clip_string + extended_string)

        convclip.append('%')
        return '|'.join(convclip)

    def placeEncodedObjects(self, encoded, select=True, xOverride=None, yOverride=None):
        """
        Decode and place a set of objects
        """
        self.win.SelectionUpdateFlag = True
        self.win.scene.clearSelection()
        added = []

        # Remove leading and trailing whitespace
        encoded = encoded.strip()

        if not (encoded.startswith('ReggieClip|') and encoded.endswith('|%')):
            self.win.SelectionUpdateFlag = False
            return added

        clip = encoded.split('|')

        if len(clip) > 300 + 2:
            result = QtWidgets.QMessageBox.warning(self.win, 'Reggie', globals_.trans.string('MainWindow', 1),
                                                   QtWidgets.QMessageBox.StandardButton.Yes, QtWidgets.QMessageBox.StandardButton.No)
            if result == QtWidgets.QMessageBox.StandardButton.No:
                self.win.SelectionUpdateFlag = False
                return added

        globals_.OverrideSnapping = True

        layers, sprites = self.getEncodedObjects(encoded)

        # Find the bounding box of all created objects
        bounding = QtCore.QRectF()

        for spr in sprites:
            bounding |= spr.LevelRect

        for layer in layers:
            for obj in layer:
                bounding |= obj.LevelRect

        x1, y1, width, height = bounding.getRect()

        # now center everything
        zoomscaler = self.win.ZoomLevel / 100
        viewportx = (self.win.view.XScrollBar.value() / zoomscaler) / 24
        viewporty = (self.win.view.YScrollBar.value() / zoomscaler) / 24
        viewportwidth = (self.win.view.width() / zoomscaler) / 24
        viewportheight = (self.win.view.height() / zoomscaler) / 24

        # tiles
        if xOverride is None:
            xoffset = int(0 - x1 + viewportx + ((viewportwidth / 2) - (width / 2)))
            xpixeloffset = xoffset * 16
        else:
            xoffset = int(0 - x1 + (xOverride / 16) - (width / 2))
            xpixeloffset = xoffset * 16
        if yOverride is None:
            yoffset = int(0 - y1 + viewporty + ((viewportheight / 2) - (height / 2)))
            ypixeloffset = yoffset * 16
        else:
            yoffset = int(0 - y1 + (yOverride / 16) - (height / 2))
            ypixeloffset = yoffset * 16

        # Center and select everything
        for item in sprites:
            item.setNewObjPos(item.objx + xpixeloffset, item.objy + ypixeloffset)
            item.UpdateRects()
            if select: item.setSelected(True)

        for layer in layers:
            for item in layer:
                item.setPos((item.objx + xoffset) * 24, (item.objy + yoffset) * 24)
                item.UpdateRects()
                if select: item.setSelected(True)

        globals_.OverrideSnapping = False

        self.win.levelOverview.update()
        SetDirty()
        self.win.SelectionUpdateFlag = False
        self.win.ChangeSelectionHandler()

        # Combine the sprites and layers
        added = sprites
        for layer in layers:
            added += layer

        return added

    def getEncodedObjects(self, encoded):
        """
        Create the objects from a ReggieClip
        """

        layers = ([], [], [])
        sprites = []

        if not (encoded.startswith('ReggieClip|') and encoded.endswith('|%')):
            return layers, sprites

        clip = encoded[11:-2].split('|')

        self.win.spriteList.prepareBatchAdd()
        for item in clip:

            try:
                # Check to see whether it's an object or sprite
                # and add it to the correct stack
                split = item.split(':')
                if split[0] == '0':
                    # object
                    if len(split) != 8: continue

                    tileset = int(split[1])
                    type = int(split[2])
                    layer = int(split[3])
                    objx = int(split[4])
                    objy = int(split[5])
                    width = int(split[6])
                    height = int(split[7])

                    # basic sanity checks
                    if tileset < 0 or tileset > 3: continue
                    if type < 0 or type > 255: continue
                    if layer < 0 or layer > 2: continue
                    if objx < 0 or objx > 1023: continue
                    if objy < 0 or objy > 511: continue
                    if width < 1 or width > 1023: continue
                    if height < 1 or height > 511: continue

                    newitem = self.win.CreateObject(tileset, type, layer, objx, objy, width, height)  # , add_to_scene = False)

                    layers[layer].append(newitem)

                elif split[0] == '1':
                    # sprite
                    if 11 <= len(split) <= 12:
                        is_extended = True if len(split) == 12 else False
                        extended_settings = [bytes.fromhex(split[11][i:i+8]) for i in range(0, len(split[11]), 8)] if is_extended else []

                        objx = int(split[2])
                        objy = int(split[3])
                        data = bytes(map(int, [split[4], split[5], split[6], split[7], split[8], split[9], '0', split[10]]))

                        newitem = self.win.CreateSprite(
                            objx,
                            objy,
                            int(split[1]),
                            RawData(
                                data,
                                *extended_settings,
                                format = RawData.Format.Extended if is_extended else RawData.Format.Vanilla
                            )
                        )
                        sprites.append(newitem)

            except ValueError:
                # an int() probably failed somewhere
                pass

        self.win.spriteList.endBatchAdd()

        return layers, sprites
