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

from PyQt6 import QtCore, QtGui

from reggie.core import globals_
from reggie.core.dirty import SetDirty


# Merge ids for QUndoCommand.id() (-1 = never merges)
MOVE_COMMAND_ID = 1
PROPERTY_COMMAND_ID = 2
PATH_DATA_COMMAND_ID = 3


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
        # Captured before the stack moves: afterwards `command(index())` is a
        # different command, and on an empty stack there is nothing to read.
        command = self.command(self.index() - 1) if self.index() > 0 else None

        with _ApplyGuard():
            super().undo()

        # Undo is local and per-user, but the *level* must still converge, so
        # the peer is told about the resulting edit. See broadcast.encode_undo:
        # this is "the item moved back to there", not "undo your last step".
        _broadcast_command(command, undone=True)

    def redo(self):
        command = self.command(self.index()) if self.index() < self.count() else None

        with _ApplyGuard():
            super().redo()

        _broadcast_command(command)

    def push(self, cmd):
        with _ApplyGuard():
            super().push(cmd)

        # Broadcast after the command has been applied, so a peer never hears
        # about an edit that failed locally. Outside the guard because the guard
        # is what marks an edit as *remote*, and this one is ours.
        #
        # Every local edit funnels through here, which is why the collaboration
        # hook lives at this one point rather than at each call site: a command
        # type added later is broadcast without anyone remembering to wire it.
        # Remote edits are applied inside the guard and never pushed, so they
        # cannot reach this line and echo back to their sender.
        _broadcast_command(cmd)


def _broadcast_command(cmd, undone=False):
    """
    Hands a command to a running collaboration session.

    `undone` sends the inverse edit instead of the forward one, for a command
    that has just been reverted.

    Fully guarded: the edit has already been applied locally and is correct, so
    a collaboration problem must never surface as a failed edit. A peer that
    misses an operation can resync; a local edit rolled back by a network error
    is data loss.
    """
    if cmd is None:
        return

    window = getattr(globals_, 'mainWindow', None)
    controller = getattr(window, '_collab', None)
    if controller is None:
        return

    try:
        controller.broadcastCommand(cmd, undone=undone)
    except Exception:
        pass


###############################################################################
# Item helpers: labels, position application, detach/attach
###############################################################################

def _tr(numcode, *replacements):
    """
    Fetches a string from the 'Undo' translation section.
    """
    return globals_.trans.string('Undo', numcode, *replacements)


def _item_label(item):
    """
    A short human-readable description of a level item, for command texts.
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem,
        CommentItem, ZoneItem,
    )

    if isinstance(item, ObjectItem):
        return _tr(10, '[ts]', item.tileset, '[type]', item.type)
    if isinstance(item, SpriteItem):
        return _tr(11, '[id]', item.type)
    if isinstance(item, EntranceItem):
        return _tr(12, '[id]', item.entid)
    if isinstance(item, LocationItem):
        return _tr(13, '[id]', item.id)
    if isinstance(item, PathItem):
        return _tr(14, '[path]', item.pathid, '[node]', item.nodeid)
    if isinstance(item, CommentItem):
        return _tr(15)
    if isinstance(item, ZoneItem):
        return _tr(16, '[id]', item.id + 1)
    return _tr(17)


def _items_label(items):
    """
    A label for a group of items: the single item's label, or a count.
    """
    if len(items) == 1:
        return _item_label(items[0])
    return _tr(18, '[n]', len(items))


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
                text = _tr(20, '[what]', _item_label(item), '[x]', new[0], '[y]', new[1])
            else:
                text = _tr(21, '[what]', _items_label(items))
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
            text = _tr(22, '[what]', _items_label(self.items))
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

    Alternatively, pass `precaptured` = [(item, detach_ctx), ...] for items a
    caller already detached itself (bulk edit sessions); the first redo() is
    then skipped.
    """

    def __init__(self, items, text=None, precaptured=None):
        super().__init__()
        if precaptured is not None:
            self._contexts = list(precaptured)
            self.items = [item for item, ctx in self._contexts]
            self._skip_first_redo = True
        else:
            self.items = [item for item in items if item is not None]
            self._contexts = None
            self._skip_first_redo = False

        if text is None:
            text = _tr(23, '[what]', _items_label(self.items))
        self.setText(text)

    def undo(self):
        with _ApplyGuard():
            for item, ctx in reversed(self._contexts):
                _attach_item(item, ctx)
            _finish_mutation()

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        with _ApplyGuard():
            self._contexts = []
            for item in _deletion_order(self.items):
                self._contexts.append((item, _detach_item(item)))
            _finish_mutation()
            globals_.mainWindow.ChangeSelectionHandler()


###############################################################################
# Property edits (Round 2)
###############################################################################

def _property_attrs(item):
    """
    The attributes that define an item's editable properties (not geometry,
    except for locations where the editor panel edits geometry directly).
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, CommentItem,
    )

    if isinstance(item, ObjectItem):
        return ('tileset', 'type')
    if isinstance(item, SpriteItem):
        return ('type', 'spritedata')
    if isinstance(item, EntranceItem):
        return ('entid', 'destarea', 'destentrance', 'enttype', 'entzone',
                'entlayer', 'entpath', 'cpdirection', 'entsettings',
                'leave_level')
    if isinstance(item, LocationItem):
        return ('objx', 'objy', 'width', 'height', 'id')
    if isinstance(item, CommentItem):
        return ('text',)
    return ()


def _copy_value(value):
    """
    Snapshot-copies a property value (RawData is mutable and reused by the
    sprite editor, so it must be copied).
    """
    copy = getattr(value, 'copy', None)
    if copy is not None and not isinstance(value, (bytes, str)):
        return copy()
    return value


def _values_equal(a, b):
    """
    Compares two property values. RawData has no __eq__, so compare its parts.
    """
    from reggie.core.raw_data import RawData

    if isinstance(a, RawData) and isinstance(b, RawData):
        return (a.original == b.original and a.blocks == b.blocks
                and a.format == b.format)
    return a == b


def snapshot_properties(item):
    """
    Returns a {attr: copied value} snapshot of the item's properties.
    """
    return {attr: _copy_value(getattr(item, attr)) for attr in _property_attrs(item)}


def _refresh_item(item):
    """
    Refreshes an item's visuals, tooltip, list entry and (if it is being
    edited) its editor panel, after its properties or geometry changed.
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, CommentItem,
    )

    mw = globals_.mainWindow

    if isinstance(item, ObjectItem):
        item.updateObjCache()
        item.UpdateRects()
        item.update()

    elif isinstance(item, SpriteItem):
        # SetType refreshes name, tooltip, sprite image and list item
        item.SetType(item.type)
        item.UpdateDynamicSizing()
        mw.spriteList.updateSprite(item)
        item.update()

        editor = getattr(mw, 'spriteDataEditor', None)
        if editor is not None and mw.selObj is item:
            editor.setSprite(item.type, initial_data=item.spritedata)

    elif isinstance(item, EntranceItem):
        item.TypeChange()
        item.UpdateTooltip()
        item.UpdateListItem()
        item.update()

        editor = getattr(mw, 'entranceEditor', None)
        if editor is not None and editor.ent is item:
            editor.ent = None  # bypass the same-object early return
            editor.setEntrance(item)

    elif isinstance(item, LocationItem):
        item.autoPosChange = True
        try:
            item.setPos(int(item.objx * 1.5), int(item.objy * 1.5))
        finally:
            item.autoPosChange = False
        item.UpdateTitle()
        item.UpdateRects()
        item.UpdateListItem()
        item.update()

        editor = getattr(mw, 'locationEditor', None)
        if editor is not None and editor.loc is item:
            editor.setLocation(item)

    elif isinstance(item, CommentItem):
        # Push the (possibly undone) text back into the in-scene text editor.
        # Its textChanged handler is a recording site, but recording is
        # blocked while commands run, so this does not echo.
        if item.TextEdit.toPlainText() != item.text:
            item.TextEdit.setPlainText(item.text)
        item.UpdateTooltip()
        item.UpdateListItem()
        item.update()
        mw.SaveComments()

    mw.scene.update()


class ChangePropertyCommand(QtGui.QUndoCommand):
    """
    One property-edit step on a single item (editor panel spinbox, checkbox,
    sprite data field, comment text...). Consecutive edits to the same fields
    of the same item merge into one step, so spinbox scrubbing and typing
    stay one entry each.
    """

    def __init__(self, item, before, after, text=None, already_applied=True):
        super().__init__()
        self.item = item
        self.before = before
        self.after = after
        self.changed_keys = frozenset(
            k for k in before if not _values_equal(before[k], after.get(k)))
        self._skip_first_redo = bool(already_applied)

        if text is None:
            text = _tr(25, '[what]', _item_label(item))
        self.setText(text)

    def id(self):
        return PROPERTY_COMMAND_ID

    def mergeWith(self, other):
        if not isinstance(other, ChangePropertyCommand):
            return False
        if other.item is not self.item or other.changed_keys != self.changed_keys:
            return False

        self.after = other.after
        self.setText(other.text())
        return True

    def undo(self):
        with _ApplyGuard():
            for attr, value in self.before.items():
                setattr(self.item, attr, _copy_value(value))
            _refresh_item(self.item)
            _finish_mutation()

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        with _ApplyGuard():
            for attr, value in self.after.items():
                setattr(self.item, attr, _copy_value(value))
            _refresh_item(self.item)
            _finish_mutation()


class record_property_edit:
    """
    Context manager for recording a property edit at a call site:

        with record_property_edit(item):
            item.destarea = 3

    Snapshots the item's properties around the body and pushes a merged
    ChangePropertyCommand if anything changed. No-op while commands run.
    """

    def __init__(self, item, text=None):
        self.item = item
        self.text = text

    def __enter__(self):
        self.active = self.item is not None and not is_recording_blocked()
        self.before = snapshot_properties(self.item) if self.active else None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None or not self.active:
            return False

        after = snapshot_properties(self.item)
        changed = any(not _values_equal(self.before[k], after[k]) for k in after)
        if changed:
            globals_.mainWindow.undoStack.push(ChangePropertyCommand(
                self.item, self.before, after, text=self.text))
        return False


###############################################################################
# Geometry (move + resize) edits (Round 2)
###############################################################################

def _apply_geometry(item, x, y, w, h):
    """
    Applies position and (if given) size to an item.
    """
    from reggie.core.levelitems import ObjectItem, LocationItem, ZoneItem

    if isinstance(item, ZoneItem):
        # Mirrors ZoneItem.mouseMoveEvent's grabber-resize application
        old_rect = QtCore.QRectF(item.x(), item.y(), item.width * 1.5, item.height * 1.5)

        item.objx, item.objy = x, y
        if w is not None:
            item.width, item.height = w, h

        item.UpdateRects()
        item.setPos(int(x * 1.5), int(y * 1.5))

        new_rect = QtCore.QRectF(item.x(), item.y(), item.width * 1.5, item.height * 1.5)
        update_rect = old_rect.united(new_rect)
        update_rect += QtCore.QMarginsF(-3, -3, 3, 3)

        globals_.mainWindow.scene.update(update_rect)
        globals_.mainWindow.levelOverview.update()

        for spr in globals_.Area.sprites:
            spr.ImageObj.positionChanged()

    elif isinstance(item, ObjectItem):
        oldBR = item.getFullRect()

        item.objx, item.objy = x, y
        if w is not None:
            item.width, item.height = w, h
            item.updateObjCache()
        item.setPos(x * 24, y * 24)
        item.UpdateRects()
        item.update()

        globals_.mainWindow.scene.update(oldBR)
        globals_.mainWindow.scene.update(item.getFullRect())
        globals_.mainWindow.levelOverview.update()

    elif isinstance(item, LocationItem):
        item.objx, item.objy = x, y
        if w is not None:
            item.width, item.height = w, h

        item.autoPosChange = True
        try:
            item.setPos(int(x * 1.5), int(y * 1.5))
        finally:
            item.autoPosChange = False
        item.UpdateRects()
        item.update()
        globals_.mainWindow.levelOverview.update()

        editor = getattr(globals_.mainWindow, 'locationEditor', None)
        if editor is not None and editor.loc is item:
            editor.setLocation(item)

    else:
        _apply_position(item, x, y)


class ResizeItemsCommand(QtGui.QUndoCommand):
    """
    One resize gesture (objects / locations): position and size change
    together, because corner drags move the origin too.
    """

    def __init__(self, entries, already_applied=True, text=None):
        """
        entries: list of (item, (old_x, old_y, old_w, old_h),
                                (new_x, new_y, new_w, new_h))
        """
        super().__init__()
        self.entries = list(entries)
        self._skip_first_redo = bool(already_applied)

        if text is None:
            text = _tr(24, '[what]', _items_label([e[0] for e in self.entries]))
        self.setText(text)

    def undo(self):
        with _ApplyGuard():
            for item, old, new in reversed(self.entries):
                _apply_geometry(item, *old)
            _finish_mutation()

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        with _ApplyGuard():
            for item, old, new in self.entries:
                _apply_geometry(item, *new)
            _finish_mutation()


###############################################################################
# Path data edits (Round 2)
###############################################################################

def _refresh_path_editor(node):
    """
    Refreshes the path editor panel if it is editing the given node.
    """
    editor = getattr(globals_.mainWindow, 'pathEditor', None)
    if editor is not None and editor.path_node is node:
        editor.path_node = None  # bypass the same-object early return
        editor.setPath(node)


class PathNodeDataCommand(QtGui.QUndoCommand):
    """
    Speed/accel/delay change of a single path node. Consecutive edits to the
    same node merge (spinbox scrubbing).
    """

    def __init__(self, node, before, after, already_applied=True):
        """
        before/after: (speed, accel, delay) tuples
        """
        super().__init__()
        self.node = node
        self.before = before
        self.after = after
        self._skip_first_redo = bool(already_applied)
        self.setText(_tr(25, '[what]', _item_label(node)))

    def id(self):
        return PATH_DATA_COMMAND_ID

    def mergeWith(self, other):
        if not isinstance(other, PathNodeDataCommand) or other.node is not self.node:
            return False
        self.after = other.after
        return True

    def _apply(self, values):
        speed, accel, delay = values
        self.node.path.set_node_data(self.node, speed=speed, accel=accel, delay=delay)
        _refresh_path_editor(self.node)
        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.before)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.after)


class PathSettingCommand(QtGui.QUndoCommand):
    """
    A whole-path setting change: 'loops' (bool) or 'id' (int).
    """

    def __init__(self, path, setting, before, after, node=None, already_applied=True):
        super().__init__()
        self.path = path
        self.setting = setting
        self.before = before
        self.after = after
        self.node = node  # panel refresh anchor
        self._skip_first_redo = bool(already_applied)
        self.setText(_tr(39, '[id]', path._id if setting != 'id' else before,
                         '[setting]', setting))

    def _apply(self, value):
        if self.setting == 'loops':
            self.path.set_loops(bool(value))
        else:
            self.path.set_id(int(value))
        if self.node is not None:
            _refresh_path_editor(self.node)
        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.before)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.after)


class PathNodeOrderCommand(QtGui.QUndoCommand):
    """
    A node being moved to a different index within its path.
    """

    def __init__(self, node, old_index, new_index, already_applied=True):
        super().__init__()
        self.node = node
        self.old_index = old_index
        self.new_index = new_index
        self._skip_first_redo = bool(already_applied)
        self.setText(_tr(38, '[id]', node.pathid))

    def _apply(self, index):
        self.node.path.move_node(self.node, index)
        _refresh_path_editor(self.node)
        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.old_index)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.new_index)


###############################################################################
# Bulk edit sessions (Round 3) — used by the Quick Paint Tool
###############################################################################
#
# QPT strokes, fills and erases mutate many objects across several code paths
# (including timer-deferred deletions). A bulk session collects every object
# created or removed between begin_bulk_edit()/end_bulk_edit() and pushes ONE
# undo step at the end. Creations are reported by ReggieWindow.CreateObject
# (via notify_item_created); removals must go through bulk_remove_object().
# Sessions are reentrant; nothing is pushed for empty sessions.

_bulk_session = None


class _BulkSession:
    def __init__(self, text):
        self.text = text
        self.depth = 1
        self.created = []
        self.removed = []  # (item, detach_ctx)


def begin_bulk_edit(text):
    """
    Opens (or nests into) a bulk edit session.
    """
    global _bulk_session

    if is_recording_blocked():
        return

    if _bulk_session is not None:
        _bulk_session.depth += 1
        return

    _bulk_session = _BulkSession(text)


def end_bulk_edit():
    """
    Closes a bulk edit session; the outermost close pushes the collected
    changes as a single undo step.
    """
    global _bulk_session

    session = _bulk_session
    if session is None:
        return

    session.depth -= 1
    if session.depth > 0:
        return

    _bulk_session = None

    # Items created AND removed within the same session are a net no-op
    removed_items = [item for item, ctx in session.removed]
    created = [item for item in session.created
               if item is not None and item.scene() is not None]
    removed = [(item, ctx) for item, ctx in session.removed
               if not any(item is c for c in session.created)]

    created = [item for item in created
               if not any(item is r for r in removed_items)]

    stack = globals_.mainWindow.undoStack
    if created and removed:
        stack.beginMacro(session.text)
        try:
            stack.push(RemoveItemsCommand(None, text=session.text, precaptured=removed))
            stack.push(AddItemsCommand(created, text=session.text, already_applied=True))
        finally:
            stack.endMacro()
    elif created:
        stack.push(AddItemsCommand(created, text=session.text, already_applied=True))
    elif removed:
        stack.push(RemoveItemsCommand(None, text=session.text, precaptured=removed))


class bulk_edit_session:
    """
    Context-manager form of begin_bulk_edit()/end_bulk_edit().
    """

    def __init__(self, text):
        self.text = text

    def __enter__(self):
        begin_bulk_edit(self.text)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        end_bulk_edit()
        return False


def notify_item_created(item):
    """
    Reports a freshly created level item. Only recorded while a bulk edit
    session is open (normal interactive flows record via their own commands).
    """
    if _bulk_session is not None and not is_recording_blocked() and item is not None:
        _bulk_session.created.append(item)


def record_created_item(item, text=None):
    """
    Records an item created outside any command as its own undo command.

    For the creation paths that build an item directly rather than through a
    command: a Ctrl+drag clone, and the sprite editor's "place this sprite"
    buttons. Each was absent from the history entirely, so it could not be
    undone - and for the clone the drag that followed recorded a *move of the
    original*, a different object, which made the duplicate look recorded when
    it was not.

    That absence also hid these items from collaboration, which builds its
    operations from pushed commands: a peer saw the original move and never
    heard that a second item existed.

    A bulk edit session takes precedence: it is already collecting created
    items and will push one command for the whole stroke.
    """
    if item is None or is_recording_blocked():
        return

    if _bulk_session is not None:
        _bulk_session.created.append(item)
        return

    window = getattr(globals_, 'mainWindow', None)
    stack = getattr(window, 'undoStack', None)
    if stack is None:
        return

    stack.push(AddItemsCommand([item], text=text, already_applied=True))


def bulk_remove_object(item):
    """
    Detaches a level item from the scene and all bookkeeping lists (the
    undo-aware replacement for `item.delete(); scene.removeItem(item)` in
    bulk code paths). Recorded if a bulk edit session is open.
    """
    ctx = _detach_item(item)

    if _bulk_session is not None and not is_recording_blocked():
        _bulk_session.removed.append((item, ctx))


###############################################################################
# Modal dialog snapshots (Round 3)
###############################################################################

def _copy_area_value(value):
    if isinstance(value, set):
        return set(value)
    if isinstance(value, list):
        import copy
        return copy.deepcopy(value)
    return value


class AreaSettingsCommand(QtGui.QUndoCommand):
    """
    A change to area-level settings (Area Options dialog, camera profiles):
    before/after {attr: value} snapshots of globals_.Area attributes.
    If tilesets are among the changed attributes, the tileset UI is reloaded.
    """

    def __init__(self, before, after, text, refresh_tilesets=False, already_applied=True):
        super().__init__()
        self.before = {k: _copy_area_value(v) for k, v in before.items()}
        self.after = {k: _copy_area_value(v) for k, v in after.items()}
        self.refresh_tilesets = refresh_tilesets
        self._skip_first_redo = bool(already_applied)
        self.setText(text)

    def _apply(self, values):
        for attr, value in values.items():
            setattr(globals_.Area, attr, _copy_area_value(value))

        if self.refresh_tilesets:
            globals_.mainWindow.RefreshTilesetsFromArea()

        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.before)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.after)


# Every ZoneItem attribute the Zones and Backgrounds dialogs can change
_ZONE_ATTRS = (
    'objx', 'objy', 'width', 'height', 'modeldark', 'terraindark', 'id',
    'cammode', 'camzoom', 'camtrack', 'visibility', 'music', 'sfxmod',
    'mpcamzoomadjust',
    'yupperbound', 'ylowerbound', 'yupperbound2', 'ylowerbound2',
    'yupperbound3', 'ylowerbound3',
    'XscrollA', 'YscrollA', 'XpositionA', 'YpositionA',
    'bg1A', 'bg2A', 'bg3A', 'ZoomA',
    'XscrollB', 'YscrollB', 'XpositionB', 'YpositionB',
    'bg1B', 'bg2B', 'bg3B', 'ZoomB',
)


def snapshot_zones():
    """
    Captures the current zone set as [(zone_object, {attr: value})].
    """
    return [(z, {attr: getattr(z, attr) for attr in _ZONE_ATTRS})
            for z in globals_.Area.zones]


class ZonesSnapshotCommand(QtGui.QUndoCommand):
    """
    A change to the area's zones (Zones or Backgrounds dialog): the whole zone
    set is snapshotted before/after; zone objects stay alive inside the
    command, so added/removed zones round-trip with identity intact.
    """

    def __init__(self, before_state, after_state, text, already_applied=True):
        super().__init__()
        self.before_state = before_state
        self.after_state = after_state
        self._skip_first_redo = bool(already_applied)
        self.setText(text)

    @staticmethod
    def _apply(state):
        from reggie.core.levelitems import ZoneItem

        mw = globals_.mainWindow

        for item in mw.scene.items():
            if isinstance(item, ZoneItem):
                mw.scene.removeItem(item)

        globals_.Area.zones = []

        for z, values in state:
            for attr, value in values.items():
                setattr(z, attr, value)

            globals_.Area.zones.append(z)
            mw.scene.addItem(z)

            z.prepareGeometryChange()
            z.UpdateRects()
            z.setPos(z.objx * 1.5, z.objy * 1.5)
            z.UpdateTitle()

        for spr in globals_.Area.sprites:
            spr.ImageObj.positionChanged()

        mw.actions['backgrounds'].setEnabled(len(globals_.Area.zones) > 0)
        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.before_state)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.after_state)


_METADATA_KEYS = ('Title', 'Author', 'Group', 'Website')


def snapshot_metadata():
    """
    Captures the level-info metadata strings.
    """
    return {key: globals_.Area.Metadata.strData(key) or ''
            for key in _METADATA_KEYS}


class MetadataCommand(QtGui.QUndoCommand):
    """
    A change to the level information (Metadata) strings.
    """

    def __init__(self, before, after, text, already_applied=True):
        super().__init__()
        self.before = dict(before)
        self.after = dict(after)
        self._skip_first_redo = bool(already_applied)
        self.setText(text)

    def _apply(self, values):
        for key, value in values.items():
            globals_.Area.Metadata.setStrData(key, value)
        _finish_mutation()

    def undo(self):
        with _ApplyGuard():
            self._apply(self.before)

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        with _ApplyGuard():
            self._apply(self.after)


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
