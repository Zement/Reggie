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
from reggie.core.levelitems import ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem, Path
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

    def CopyOrCut(self, cutAction):
        """
        Copies or cuts the selected items (objects, sprites, entrances,
        locations and path nodes)
        """
        selitems = self.win.scene.selectedItems()
        if cutAction:
            self.win.SelectionUpdateFlag = True
            self.win.scene.clearSelection()

        if selitems:
            clipboard_o = []
            clipboard_s = []
            clipboard_e = []
            clipboard_l = []
            clipboard_p = []
            ii = isinstance

            to_be_deleted = []
            for obj in selitems:
                if ii(obj, ObjectItem):
                    clipboard_o.append(obj)
                elif ii(obj, SpriteItem):
                    clipboard_s.append(obj)
                elif ii(obj, EntranceItem):
                    clipboard_e.append(obj)
                elif ii(obj, LocationItem):
                    clipboard_l.append(obj)
                elif ii(obj, PathItem):
                    clipboard_p.append(obj)
                else:
                    continue

                if cutAction:
                    to_be_deleted.append(obj)

            if clipboard_o or clipboard_s or clipboard_e or clipboard_l or clipboard_p:
                if cutAction:
                    SetDirty()
                    self.win.actions['cut'].setEnabled(False)
                self.win.actions['paste'].setEnabled(True)
                self.win.clipboard = self.encodeObjects(clipboard_o, clipboard_s, clipboard_e, clipboard_l, clipboard_p)
                self.win.systemClipboard.setText(self.win.clipboard)

            if to_be_deleted:
                from reggie.core import undo
                self.win.undoStack.push(
                    undo.RemoveItemsCommand(to_be_deleted, text='Cut'))

        if cutAction:
            self.win.levelOverview.update()
            self.win.SelectionUpdateFlag = False
            self.win.ChangeSelectionHandler()

    def Cut(self):
        """
        Cuts the selected items
        """
        self.CopyOrCut(True)

    def Copy(self):
        """
        Copies the selected items
        """
        self.CopyOrCut(False)

    def Paste(self):
        """
        Paste the selected items
        """
        if self.win.clipboard is not None:
            created = self.placeEncodedObjects(self.win.clipboard)

            if created:
                from reggie.core import undo
                self.win.undoStack.push(
                    undo.AddItemsCommand(created, text='Paste', already_applied=True))

    def encodeObjects(self, clipboard_o, clipboard_s, clipboard_e=None, clipboard_l=None, clipboard_p=None):
        """
        Encode a set of level items into a string
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

        # Entrances
        if clipboard_e is not None:
            for item in clipboard_e:
                convclip.append('2:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d' % (
                item.objx, item.objy, item.entid, item.destarea, item.destentrance, item.enttype, item.entzone,
                item.entsettings, item.entlayer, item.entpath, item.leave_level, item.cpdirection))

        # Locations
        if clipboard_l is not None:
            for item in clipboard_l:
                convclip.append('3:%d:%d:%d:%d:%d' % (
                item.id, item.objx, item.objy, item.width, item.height))

        # Path Nodes
        if clipboard_p is not None:
            clipboard_p.sort(key=lambda x: (x.pathid, x.nodeid))

            currPathID = None
            for item in clipboard_p:
                # Get parent path
                path = None
                for p in globals_.Area.paths:
                    if item.pathid == p._id:
                        path = p
                        break

                # Append a path object when the path changes
                if currPathID != item.pathid and path is not None:
                    convclip.append('4:%d:%d' % (path._id, path._loops))
                    currPathID = item.pathid

                if path is not None:
                    x, y, speed, accel, delay = path.get_node_data(item.nodeid)
                    convclip.append('5:%d:%d:%d:%d:%f:%f:%d' % (
                    item.pathid, item.nodeid, x, y, speed, accel, delay))

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

        layers, sprites, entrances, locations, paths, path_nodes = self.getEncodedObjects(encoded)

        # Find the bounding box of all created objects
        bounding = QtCore.QRectF()

        for spr in sprites:
            bounding |= spr.LevelRect

        for layer in layers:
            for obj in layer:
                bounding |= obj.LevelRect

        for ent in entrances:
            bounding |= ent.LevelRect

        for loc in locations:
            bounding |= loc.LevelRect

        for node in path_nodes:
            bounding |= node.LevelRect

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

        for item in entrances:
            item.setPos((item.objx + xpixeloffset) * 1.5, (item.objy + ypixeloffset) * 1.5)
            item.UpdateRects()
            if select: item.setSelected(True)

        for item in locations:
            item.setPos((item.objx + xpixeloffset) * 1.5, (item.objy + ypixeloffset) * 1.5)
            item.UpdateRects()
            if select: item.setSelected(True)

        for item in path_nodes:
            item.setPos((item.objx + xpixeloffset) * 1.5, (item.objy + ypixeloffset) * 1.5)
            if select: item.setSelected(True)

        globals_.OverrideSnapping = False

        self.win.levelOverview.update()
        SetDirty()
        self.win.SelectionUpdateFlag = False
        self.win.ChangeSelectionHandler()

        # Combine everything that was added
        added = sprites + entrances + locations + paths + path_nodes
        for layer in layers:
            added += layer

        return added

    def getEncodedObjects(self, encoded):
        """
        Create the objects from a ReggieClip
        """

        layers = ([], [], [])
        sprites = []
        entrances = []
        locations = []
        paths = []
        path_nodes = []

        if not (encoded.startswith('ReggieClip|') and encoded.endswith('|%')):
            return layers, sprites, entrances, locations, paths, path_nodes

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

                elif split[0] == '2':
                    # entrance
                    if len(split) != 13: continue

                    objx = int(split[1])
                    objy = int(split[2])
                    entID = int(split[3])
                    destArea = int(split[4])
                    destEnt = int(split[5])
                    entType = int(split[6])
                    zone = int(split[7])
                    settings = int(split[8])
                    layer = int(split[9])
                    path = int(split[10])
                    exitLvl = int(split[11])
                    cPipeDir = int(split[12])

                    # Sanity check data
                    if destArea < 0 or destArea > 4: continue
                    if destEnt < 0 or destEnt > 255: continue
                    if entType < 0 or entType >= len(globals_.EntranceTypeNames): continue
                    if layer < 0 or layer > 2: continue
                    if path < 0 or path > 255: continue
                    if cPipeDir < 0 or cPipeDir > 3: continue

                    newitem = self.win.CreateEntrance(objx, objy, entID, allow_dupe_id=True)
                    if newitem is None: continue

                    # Set entrance data
                    newitem.destarea = destArea
                    newitem.destentrance = destEnt
                    newitem.enttype = entType
                    newitem.entzone = zone
                    newitem.entsettings = settings
                    newitem.entlayer = layer
                    newitem.entpath = path
                    newitem.leave_level = exitLvl != 0
                    newitem.cpdirection = cPipeDir

                    # Update it
                    newitem.TypeChange()
                    newitem.UpdateTooltip()
                    newitem.UpdateListItem(True)

                    entrances.append(newitem)

                elif split[0] == '3':
                    # location
                    if len(split) != 6: continue

                    locID = int(split[1])
                    objx = int(split[2])
                    objy = int(split[3])
                    width = int(split[4])
                    height = int(split[5])

                    newitem = self.win.CreateLocation(objx, objy, width, height, locID)
                    if newitem is None: continue
                    locations.append(newitem)

                elif split[0] == '4':
                    # path
                    if len(split) != 3: continue

                    pathID = int(split[1])
                    loops = int(split[2])

                    path = Path(pathID, globals_.mainWindow.scene, loops)
                    globals_.Area.paths.append(path)
                    paths.append(path)

                elif split[0] == '5':
                    # path node
                    if len(split) != 8: continue

                    pathID = int(split[1])
                    nodeID = int(split[2])
                    objx = int(split[3])
                    objy = int(split[4])
                    speed = float(split[5])
                    accel = float(split[6])
                    delay = int(split[7])

                    # Make sure the clip has the parent path
                    if paths:
                        path = paths[0]
                        for p in paths:
                            if pathID == p._id:
                                path = p
                                break

                        node = path.add_node(objx, objy, speed, accel, delay, nodeID)
                        path_nodes.append(node)

            except ValueError:
                # an int() probably failed somewhere
                pass

        self.win.spriteList.endBatchAdd()

        return layers, sprites, entrances, locations, paths, path_nodes
