"""
Turning local undo commands into operations for the network (Block C - B1).

This is the outbound half of the bridge whose inbound half is sync.apply_remote.
Phase 5 built every encoder this needs and tested them against A1's own data
shapes; what was missing was anything that actually called them, so local edits
never left the machine.

The design follows from one decision made in A1 and one made here:

- A1's UndoStack.push() is the single point every local edit passes through.
  Hooking there means a new command type is broadcast the moment it is pushed,
  with no per-call-site wiring to forget. It also means the broadcast happens
  after the edit is known-good, rather than from an event handler that might
  still be cancelled.

- _ApplyGuard already distinguishes a local edit from a remote one. A remote op
  is applied inside the guard, and pushes nothing onto the stack, so it cannot
  reach this module and echo back to its sender.

Deliberately NOT sent: undo and redo. Undo is local and per-user - the settled
A1 decision - so a user undoing their own change broadcasts the resulting edit
as a fresh operation, not as an instruction for other peers to undo. That falls
out of the design rather than needing a special case: UndoStack.undo() does not
call push().

Qt-free, like the rest of reggie/collab: it receives command objects and returns
payload dicts, and knows nothing about widgets or threads.
"""

from reggie.collab import protocol, sync


class BroadcastError(Exception):
    """
    A command could not be encoded for the network.

    Never fatal to the local edit: the edit has already happened and is correct
    locally. The caller reports it and carries on, because a peer that missed an
    op can resync, whereas a local edit undone by a network problem is data loss.
    """


def encode_command(command, refmap):
    """
    Encodes one undo command as an op payload, or returns None if the command is
    not something that travels.

    Returning None rather than raising is the common case, not an error: bulk
    session wrappers and any future local-only command simply have nothing to
    say to other peers.
    """
    if command is None or refmap is None:
        return None

    name = type(command).__name__
    handler = _HANDLERS.get(name)
    if handler is None:
        return None

    try:
        return handler(command, refmap)
    except sync.SyncError as exc:
        # An unreferenced item is the usual cause, and it means our view of the
        # level has drifted from the map. Surfaced as BroadcastError so the
        # caller can ask for a resync instead of silently diverging.
        raise BroadcastError(str(exc)) from exc


def _move(command, refmap):
    if not command.entries:
        return None
    return sync.encode_move(refmap, command.entries)


def _resize(command, refmap):
    if not command.entries:
        return None
    return sync.encode_resize(refmap, command.entries)


def _add(command, refmap):
    if not command.items:
        return None
    return sync.encode_add(refmap, command.items)


def _remove(command, refmap):
    if not command.items:
        return None

    payload = sync.encode_remove(refmap, command.items)

    # Forget the items only after a successful encode: encode_remove needs the
    # references, and a failed encode must leave the map untouched so a resync
    # can still find them.
    for item in command.items:
        refmap.forget(item)

    return payload


def _property(command, refmap):
    # Only the fields that actually changed. A1 merges consecutive edits, so
    # `after` can carry untouched keys from the merged-away command, and sending
    # those would overwrite a concurrent edit by another user with a stale value.
    changed = getattr(command, 'changed_keys', None)
    if changed is None:
        before, after = command.before, command.after
    else:
        if not changed:
            return None
        before = {k: v for k, v in command.before.items() if k in changed}
        after = {k: v for k, v in command.after.items() if k in changed}

    return sync.encode_property(refmap, command.item, before, after)


def _area_settings(command, refmap):
    return sync.encode_dialog_op('area_settings', command.before, command.after)


def _metadata(command, refmap):
    return sync.encode_dialog_op('metadata', command.before, command.after)


def _zones(command, refmap):
    # ZonesSnapshotCommand names these *_state, unlike its sibling commands:
    # A1's zone snapshot is [(zone_object, {attrs})], not a plain {key: value}.
    return sync.encode_zones(command.before_state, command.after_state)


def _path_data(command, refmap):
    return sync.encode_path_data(refmap, command.node, command.before, command.after)


def _path_setting(command, refmap):
    return sync.encode_path_setting(refmap, command.node, command.setting,
                                    command.before, command.after)


def _path_order(command, refmap):
    return sync.encode_path_order(refmap, command.node,
                                  command.old_index, command.new_index)


# Keyed on class name rather than the class itself so this module does not
# import reggie.core.undo, which imports Qt.
_HANDLERS = {
    'MoveItemsCommand': _move,
    'ResizeItemsCommand': _resize,
    'AddItemsCommand': _add,
    'RemoveItemsCommand': _remove,
    'ChangePropertyCommand': _property,
    'AreaSettingsCommand': _area_settings,
    'MetadataCommand': _metadata,
    'ZonesSnapshotCommand': _zones,
    'PathNodeDataCommand': _path_data,
    'PathSettingCommand': _path_setting,
    'PathNodeOrderCommand': _path_order,
}


def op_kind_of(command):
    """
    The op kind a command would produce, without encoding it.

    Lets a caller check authorisation before doing the work - and, on a client,
    grey out an action it is not allowed to perform.
    """
    name = type(command).__name__
    return _COMMAND_KINDS.get(name)


_COMMAND_KINDS = {
    'MoveItemsCommand': 'move',
    'ResizeItemsCommand': 'resize',
    'AddItemsCommand': 'add',
    'RemoveItemsCommand': 'remove',
    'ChangePropertyCommand': 'property',
    'AreaSettingsCommand': 'area_settings',
    'MetadataCommand': 'metadata',
    'ZonesSnapshotCommand': 'zones',
    'PathNodeDataCommand': 'path_data',
    'PathSettingCommand': 'path_setting',
    'PathNodeOrderCommand': 'path_order',
}


def _assert_kinds_are_known():
    """
    Every kind this module can emit must be one the protocol knows, or the op
    would be rejected by the host's own validator after a user made an edit.
    """
    unknown = sorted(set(_COMMAND_KINDS.values()) - set(protocol.OP_KINDS))
    if unknown:
        raise AssertionError('unknown op kinds: %s' % ', '.join(unknown))

    missing = sorted(set(_COMMAND_KINDS) - set(_HANDLERS))
    if missing:
        raise AssertionError('commands without an encoder: %s' % ', '.join(missing))


_assert_kinds_are_known()
