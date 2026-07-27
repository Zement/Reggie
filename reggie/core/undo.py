"""
Undo/redo for the level editor, built on Qt's native undo framework
(QtGui.QUndoStack / QtGui.QUndoCommand). Block C - A1 clean rebuild.

Design rules:
- Every user-visible level mutation is represented by a QUndoCommand pushed
  onto mainWindow.undoStack.
- Commands hold direct references to the LevelEditorItem objects they affect.
  An item removed from the level stays alive inside the command that removed
  it and is re-attached as the *same object* on undo, so item identity is
  stable across undo/redo cycles. There is no re-lookup by value.
- Interactive edits (drags, paint-placement) already happened by the time the
  command is created, so those commands are built with already_applied=True
  and skip their first redo().
- While the stack is executing commands, recording is blocked
  (is_recording_blocked()) so event handlers don't record echo commands.
- The stack is cleared on save, save-as, level load and area switch
  (see level_io.py), and the history size comes from the 'UndoLimit' setting.
"""

from PyQt6 import QtGui

from reggie.core import globals_
from reggie.core.dirty import SetDirty


# Merge ids for QUndoCommand.id() (-1 = never merges)
MOVE_COMMAND_ID = 1


_apply_depth = 0


class _ApplyGuard:
    """
    Context manager that marks command bodies as running, so call sites
    (drag recorders, editors, dialogs) don't record echo commands.
    """

    def __enter__(self):
        global _apply_depth
        _apply_depth += 1

    def __exit__(self, exc_type, exc_value, traceback):
        global _apply_depth
        _apply_depth -= 1


def is_recording_blocked():
    """
    Returns True while an undo command is being applied (or reverted). Call
    sites that record commands from event handlers must check this first.
    """
    return _apply_depth > 0


class UndoStack(QtGui.QUndoStack):
    """
    The level editor's undo stack. One instance lives on mainWindow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUndoLimit(getattr(globals_, 'UndoLimit', 500))

    def clear(self):
        """
        Clears the history (level load / area switch / save). Also re-applies
        the history limit setting, which Qt only allows on an empty stack.
        """
        super().clear()
        self.setUndoLimit(getattr(globals_, 'UndoLimit', 500))

    def undo(self):
        with _ApplyGuard():
            super().undo()

    def redo(self):
        with _ApplyGuard():
            super().redo()

    def push(self, cmd):
        with _ApplyGuard():
            super().push(cmd)


###############################################################################
# Item helpers: labels, position application, detach/attach
###############################################################################

def _item_label(item):
    """
    A short human-readable description of a level item, for command texts.
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem,
        CommentItem, ZoneItem,
    )

    if isinstance(item, ObjectItem):
        return 'object %d-%d' % (item.tileset, item.type)
    if isinstance(item, SpriteItem):
        return 'sprite %d' % item.type
    if isinstance(item, EntranceItem):
        return 'entrance %d' % item.entid
    if isinstance(item, LocationItem):
        return 'location %d' % item.id
    if isinstance(item, PathItem):
        return 'path %d node %d' % (item.pathid, item.nodeid)
    if isinstance(item, CommentItem):
        return 'comment'
    if isinstance(item, ZoneItem):
        return 'zone %d' % (item.id + 1)
    return 'item'


def _items_label(items):
    """
    A label for a group of items: the single item's label, or a count.
    """
    if len(items) == 1:
        return _item_label(items[0])
    return '%d items' % len(items)


def _apply_position(item, x, y):
    """
    Moves a level item to (x, y) in level coordinates, updating everything
    that depends on the position.
    """
    from reggie.core.levelitems import SpriteItem, ObjectItem, PathItem

    if isinstance(item, SpriteItem):
        # Sprites are weird so they handle this themselves
        item.setNewObjPos(x, y)

    elif isinstance(item, ObjectItem):
        # Objects use the objx and objy properties differently
        oldBR = item.getFullRect()

        item.objx, item.objy = x, y
        item.setPos(x * 24, y * 24)
        item.UpdateRects()

        newBR = item.getFullRect()

        globals_.mainWindow.scene.update(oldBR)
        globals_.mainWindow.scene.update(newBR)

    elif isinstance(item, PathItem):
        item.objx, item.objy = x, y
        item.setPos(x * 1.5, y * 1.5)

        # Update the path line
        item.path._line_item.update_path()

    else:
        # Everything else is normal
        item.objx, item.objy = x, y
        item.setPos(x * 1.5, y * 1.5)

    globals_.mainWindow.levelOverview.update()


def _sprite_register_idtypes(spr):
    """
    Re-registers a sprite's id-type values in Area.sprite_idtypes. Inverse of
    the bookkeeping done by Area.RemoveSprite().
    """
    if not (0 <= spr.type < globals_.NumSprites) or globals_.Sprites[spr.type] is None:
        return

    from reggie.ui.spriteeditor import SpriteEditorWidget

    decoder = SpriteEditorWidget.PropertyDecoder()
    sdef = globals_.Sprites[spr.type]

    for field in sdef.fields:
        if field[0] not in (1, 2):
            # Only values and lists can be idtypes
            continue

        idtype = field[-2]
        if idtype is None:
            continue

        value = decoder.retrieve(spr.spritedata, field[2])

        try:
            counter = globals_.Area.sprite_idtypes[idtype]
        except KeyError:
            globals_.Area.sprite_idtypes[idtype] = {value: 1}
            continue

        counter[value] = counter.get(value, 0) + 1


def _detach_item(item):
    """
    Removes a level item from the scene and all bookkeeping lists, and returns
    a context dict with everything needed to re-attach the same object later.
    The item object stays alive (owned by the calling command).
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem,
        CommentItem, ZoneItem,
    )

    mw = globals_.mainWindow
    ctx = {}

    item.setSelected(False)

    if isinstance(item, PathItem):
        path = item.path
        index = path.get_index(item)
        ctx['path'] = path
        ctx['index'] = index
        # Keep the NodeData object itself so speed/accel/delay survive
        ctx['node_data'] = path._node_data[index]

        was_last = path.remove_node(index)
        if was_last:
            globals_.Area.paths.remove(path)
        ctx['was_last'] = was_last

        mw.scene.removeItem(item)
        mw.pathEditor.UpdatePathLength()

    elif isinstance(item, ObjectItem):
        layer = globals_.Area.layers[item.layer]
        ctx['index'] = layer.index(item)
        item.delete()  # RemoveFromLayer + scene rect update
        mw.scene.removeItem(item)

    elif isinstance(item, SpriteItem):
        ctx['index'] = globals_.Area.sprites.index(item)
        item.delete()  # spriteList row + Area.RemoveSprite (idtype counters)
        mw.scene.removeItem(item)

    elif isinstance(item, EntranceItem):
        ctx['index'] = globals_.Area.entrances.index(item)
        item.delete()
        mw.scene.removeItem(item)

    elif isinstance(item, LocationItem):
        ctx['index'] = globals_.Area.locations.index(item)
        item.delete()
        mw.scene.removeItem(item)

    elif isinstance(item, CommentItem):
        ctx['index'] = globals_.Area.comments.index(item)
        item.delete()  # also removes the TextEditProxy and calls SaveComments
        mw.scene.removeItem(item)

    elif isinstance(item, ZoneItem):
        # Zones have no delete(); they are only removed via dialogs
        ctx['index'] = globals_.Area.zones.index(item)
        globals_.Area.zones.remove(item)
        mw.scene.removeItem(item)

    else:
        item.delete()
        mw.scene.removeItem(item)

    return ctx


def _attach_item(item, ctx):
    """
    Re-attaches a previously detached item (the same object) to the scene and
    all bookkeeping lists, using the context returned by _detach_item().
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem,
        CommentItem, ZoneItem,
    )

    mw = globals_.mainWindow
    index = ctx.get('index', None)

    if isinstance(item, PathItem):
        path = ctx['path']

        if ctx['was_last']:
            globals_.Area.paths.append(path)

        path._nodes.insert(index, item)
        path._node_data.insert(index, ctx['node_data'])

        mw.scene.addItem(item)
        mw.pathList.addItem(item.listitem)
        item.positionChanged = mw.HandlePathPosChange

        # Renumber this node and everything after it
        for new_id, later_node in enumerate(path._nodes[index:], index):
            later_node.update_id(new_id)

        if not path._has_line:
            mw.scene.addItem(path._line_item)
            path._has_line = True

        path._line_item.update_path()
        mw.pathEditor.UpdatePathLength()

    elif isinstance(item, ObjectItem):
        layer = globals_.Area.layers[item.layer]
        index = min(index, len(layer))
        layer.insert(index, item)

        # Inverse of Area.RemoveFromLayer: shift later objects back up
        for upd in layer[index + 1:]:
            upd.setZValue(upd.zValue() + 1)

        mw.scene.addItem(item)
        item.UpdateRects()
        item.update()

    elif isinstance(item, SpriteItem):
        index = min(index, len(globals_.Area.sprites))
        globals_.Area.sprites.insert(index, item)
        _sprite_register_idtypes(item)

        mw.spriteList.addSprite(item)
        mw.scene.addItem(item)
        item.UpdateListItem()

    elif isinstance(item, EntranceItem):
        index = min(index, len(globals_.Area.entrances))
        globals_.Area.entrances.insert(index, item)

        mw.entranceList.addItem(item.listitem)
        mw.scene.addItem(item)
        item.UpdateListItem()

    elif isinstance(item, LocationItem):
        index = min(index, len(globals_.Area.locations))
        globals_.Area.locations.insert(index, item)

        mw.locationList.addItem(item.listitem)
        mw.scene.addItem(item)
        item.UpdateListItem()

    elif isinstance(item, CommentItem):
        index = min(index, len(globals_.Area.comments))
        globals_.Area.comments.insert(index, item)

        mw.commentList.addItem(item.listitem)
        mw.scene.addItem(item)
        mw.scene.addItem(item.TextEditProxy)
        item.UpdateListItem()
        mw.SaveComments()

    elif isinstance(item, ZoneItem):
        index = min(index, len(globals_.Area.zones))
        globals_.Area.zones.insert(index, item)
        mw.scene.addItem(item)

    else:
        mw.scene.addItem(item)

    item.setVisible(True)


def _finish_mutation():
    """
    Shared post-mutation bookkeeping for all commands.
    """
    mw = globals_.mainWindow
    SetDirty()
    mw.scene.update()
    mw.levelOverview.update()


###############################################################################
# Commands
###############################################################################

class MoveItemsCommand(QtGui.QUndoCommand):
    """
    One user "move" step: one or more items moved from old to new positions.
    Created after an interactive drag already moved the items, so the first
    redo() is skipped.
    """

    def __init__(self, entries, already_applied=True, text=None):
        """
        entries: list of (item, (old_x, old_y), (new_x, new_y)) in level coords
        """
        super().__init__()
        self.entries = list(entries)
        self._skip_first_redo = bool(already_applied)

        if text is None:
            items = [e[0] for e in self.entries]
            if len(self.entries) == 1:
                item, old, new = self.entries[0]
                text = 'Move %s to (%d, %d)' % (_item_label(item), new[0], new[1])
            else:
                text = 'Move %s' % _items_label(items)
        self.setText(text)

    def id(self):
        return MOVE_COMMAND_ID

    def mergeWith(self, other):
        # Each drag/shift is its own step; never merge separate gestures.
        return False

    def undo(self):
        with _ApplyGuard():
            for item, old, new in reversed(self.entries):
                _apply_position(item, old[0], old[1])
            _finish_mutation()

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        with _ApplyGuard():
            for item, old, new in self.entries:
                _apply_position(item, new[0], new[1])
            _finish_mutation()


class AddItemsCommand(QtGui.QUndoCommand):
    """
    One or more items added to the level (painted, pasted, stamped...).
    The items already exist in the scene when the command is created, so the
    first redo() is skipped. On undo the items are detached but stay owned by
    this command; on redo the same objects are re-attached.
    """

    def __init__(self, items, text=None, already_applied=True):
        super().__init__()
        self.items = [item for item in items if item is not None]
        self._contexts = None
        self._skip_first_redo = bool(already_applied)

        if text is None:
            text = 'Add %s' % _items_label(self.items)
        self.setText(text)

    def undo(self):
        with _ApplyGuard():
            self._contexts = []
            for item in _deletion_order(self.items):
                self._contexts.append((item, _detach_item(item)))
            _finish_mutation()
            globals_.mainWindow.ChangeSelectionHandler()

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        with _ApplyGuard():
            # Re-attach in reverse detach order so stored indices are valid
            for item, ctx in reversed(self._contexts):
                _attach_item(item, ctx)
            _finish_mutation()


class RemoveItemsCommand(QtGui.QUndoCommand):
    """
    One or more items removed from the level. redo() performs the removal
    (this command is pushed *instead of* deleting inline); the removed items
    stay alive inside the command and are re-attached on undo.
    """

    def __init__(self, items, text=None):
        super().__init__()
        self.items = [item for item in items if item is not None]
        self._contexts = None

        if text is None:
            text = 'Delete %s' % _items_label(self.items)
        self.setText(text)

    def undo(self):
        with _ApplyGuard():
            for item, ctx in reversed(self._contexts):
                _attach_item(item, ctx)
            _finish_mutation()

    def redo(self):
        with _ApplyGuard():
            self._contexts = []
            for item in _deletion_order(self.items):
                self._contexts.append((item, _detach_item(item)))
            _finish_mutation()
            globals_.mainWindow.ChangeSelectionHandler()


def _deletion_order(items):
    """
    Returns the items in a safe deletion order: path nodes are deleted from
    the highest index to the lowest (per path), so earlier deletions don't
    shift the indices of later ones. Other items keep their given order.
    """
    from reggie.core.levelitems import PathItem

    nodes = [item for item in items if isinstance(item, PathItem)]
    others = [item for item in items if not isinstance(item, PathItem)]

    def node_key(node):
        try:
            return (node.path._id, node.path.get_index(node))
        except ValueError:
            return (node.path._id, -1)

    nodes.sort(key=node_key, reverse=True)
    return others + nodes
