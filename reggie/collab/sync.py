"""
Level synchronisation: item references, operation encoding, and remote apply.

This is the bridge between the A1 undo system and the collaboration wire
protocol. Three responsibilities:

1. **Item references.** A level item has no network-stable identity - its
   identity is the Python object, which is exactly what A1 relies on. So this
   module keeps a `ref <-> item` map in the collab layer. The reference is a
   `(origin, counter)` pair rendered as a short string.

   This is deliberately *not* an attribute on LevelEditorItem. The audited fork
   smuggled a `_collab_id` onto items, which quietly makes the collab layer part
   of every item's identity; A1's whole model is that a command holds direct
   object references, and weakening that to make networking convenient would
   trade a working undo for a working demo. The map lives here and dies with the
   session.

2. **Operation encoding.** An `op` is the wire form of an A1 undo command:
   move, add, remove, property, resize, path_*, and the dialog kinds. Encoding
   is explicit per kind rather than generic reflection, because a generic
   "serialise the object" would let a peer set attributes we never intended to
   expose.

3. **Applying remote operations.** Every remote apply runs inside A1's
   `_ApplyGuard`, via `apply_remote()`. That is what keeps remote work out of
   the local undo stack: the settled decision from A1 is that **undo stays local
   and per-user**. A peer's edit changes your level but never appears in your
   history, exactly as in Google Docs or Figma.

Threading: encode/decode are pure and safe anywhere. `apply_remote` touches Qt
scene objects and therefore MUST run on the Qt main thread - the UI layer in
phase 7 marshals it there. This module never imports Qt itself, so it stays
headless-testable; the item work happens through `reggie.core.undo` helpers,
which are imported lazily so a test can substitute them.

Security posture: every field of every incoming op is bounds-checked by
protocol.py before it arrives here, and `authorize_op` in session.py has already
approved the kind for the sender's role. What this module adds is *referential*
safety - an op naming an unknown item, or a value outside the level's own limits,
is refused rather than applied to whatever happens to be nearby.
"""

import threading

from reggie.collab import protocol


# Level coordinate limits. NSMBW levels are bounded well inside these; the point
# is to reject nonsense before it reaches a Qt scene, where an absurd coordinate
# turns into an unusable canvas rather than an exception.
MAX_COORD = 1 << 20
MIN_COORD = -(1 << 20)
MAX_DIMENSION = 1 << 16

# Caps for a snapshot, so a hostile or broken host cannot make a client allocate
# without bound. A real level is far below these.
MAX_SNAPSHOT_ITEMS = 20000
MAX_SPRITEDATA_BYTES = 1024

# Item kinds as they appear on the wire. Deliberately short strings, and
# deliberately a closed set: an unknown kind is refused, never guessed at.
KIND_OBJECT = 'object'
KIND_SPRITE = 'sprite'
KIND_ENTRANCE = 'entrance'
KIND_LOCATION = 'location'
KIND_PATH = 'path'
KIND_COMMENT = 'comment'
KIND_ZONE = 'zone'

ITEM_KINDS = (KIND_OBJECT, KIND_SPRITE, KIND_ENTRANCE, KIND_LOCATION,
              KIND_PATH, KIND_COMMENT, KIND_ZONE)


class SyncError(Exception):
    """
    Raised when an operation cannot be encoded or applied. Callers turn this
    into an `op_reject`; it is never fatal to the session.
    """


class UnknownRefError(SyncError):
    """
    An operation referenced an item this peer does not know about.

    Usually benign and self-correcting: the op raced a removal, or the peer
    joined mid-edit. The right response is op_reject plus a snapshot request,
    not a disconnect.
    """


# ---------------------------------------------------------------------------
# Reference map
# ---------------------------------------------------------------------------

class RefMap:
    """
    Bidirectional map between wire references and live level items.

    Keyed on `id(item)` rather than the item itself, because level items are Qt
    objects whose __eq__/__hash__ we do not control and must not depend on.
    Holding a strong reference to the item is intentional: A1's remove commands
    keep detached items alive inside the command, so an item absent from the
    scene may still be referenced by a later undo, and a weak map would drop it
    exactly when a peer's undo needs it.

    Both host and client keep one. Either may mint a reference for an item it
    just created, because a peer that cannot name its own new item cannot
    describe it to anybody - that is what stopped a client from painting. Refs
    carry the minting peer's `origin` as a prefix, so two peers creating items
    at the same moment cannot collide.

    `is_authority` is therefore not about minting. It marks the peer whose copy
    of the level wins a disagreement, which is what `seed` uses: rebuilding
    references for a whole area is the host redefining shared state, and a
    client doing it would silently renumber items the host already named.
    """

    def __init__(self, origin='host', is_authority=True):
        self.origin = str(origin)
        self.is_authority = bool(is_authority)
        self._counter = 0
        self._by_ref = {}        # ref -> item
        self._by_item = {}       # id(item) -> ref
        self._lock = threading.RLock()

    def mint(self, item):
        """
        Assigns a new reference to an item that this peer has just created.

        Allowed on a client: the reference is prefixed with this peer's origin,
        so it cannot collide with one the host assigned, and the host validates
        and relays it like any other. Without this a client could not broadcast
        an `add` at all - every painted tile failed to encode and triggered a
        resync, which then deleted the tiles the client had just painted.
        """
        if item is None:
            raise SyncError('cannot reference None')

        with self._lock:
            existing = self._by_item.get(id(item))
            if existing is not None:
                return existing

            self._counter += 1
            ref = '%s:%d' % (self.origin, self._counter)
            self._by_ref[ref] = item
            self._by_item[id(item)] = ref
            return ref

    def size(self):
        """
        How many items are referenced. For diagnostics only.
        """
        with self._lock:
            return len(self._by_ref)

    def seed(self, area):
        """
        Mints a reference for every item already in an area. Host only.

        Called when hosting starts, so that edits made before anyone joins can
        still be encoded. Without it, references would first be minted by
        build_snapshot - and a host who moved an existing object before the
        first client joined would produce an unreferenced-item error for an
        edit that is perfectly valid.

        Returns the number of items now referenced. Idempotent: mint() returns
        the existing reference for an item it already knows.

        Host only, and checked here rather than in mint(): naming one item you
        just created is every peer's business, but renaming a whole area is the
        authority redefining shared state. A client doing it would give new
        references to items the host has already named, so every later op for
        them would arrive with a reference the host cannot resolve.
        """
        if not self.is_authority:
            raise SyncError('only the host may seed references for an area')

        if area is None:
            return 0

        count = 0
        for group in _snapshot_groups(area):
            for item in group:
                if item is not None:
                    self.mint(item)
                    count += 1

        return count

    def bind(self, ref, item):
        """
        Records a host-assigned reference. Used by clients applying a snapshot or
        a remote add.
        """
        ref = str(ref)
        if not ref or item is None:
            raise SyncError('bind requires a reference and an item')

        with self._lock:
            # Rebinding a reference to a different item would silently redirect
            # every later op for it, so replace the mapping wholesale.
            previous = self._by_ref.get(ref)
            if previous is not None and previous is not item:
                self._by_item.pop(id(previous), None)

            self._by_ref[ref] = item
            self._by_item[id(item)] = ref

        return ref

    def ref_for(self, item):
        if item is None:
            return None
        with self._lock:
            return self._by_item.get(id(item))

    def item_for(self, ref):
        with self._lock:
            return self._by_ref.get(str(ref))

    def require(self, ref):
        """
        Looks up an item or raises UnknownRefError. Use on every incoming
        reference: the alternative is applying an edit to the wrong object.

        A reference whose item has been destroyed counts as unknown. The map
        holds strong references on purpose (an undo command may still need a
        detached item), so a Qt object destroyed underneath us leaves a live
        Python wrapper here - and every later op for it would raise
        RuntimeError deep inside the apply path rather than being handled as
        the ordinary "we are out of date" case that it is.
        """
        item = self.item_for(ref)
        if item is None:
            raise UnknownRefError('unknown item reference %r' % (ref,))

        # Only a *destroyed Qt object* counts as missing. An object with no
        # scene() at all is not a level item and is none of this method's
        # business - swallowing that would turn a malformed payload into a
        # resync instead of the validation error it should raise.
        scene = getattr(item, 'scene', None)
        if callable(scene):
            try:
                scene()
            except RuntimeError:
                self.forget_ref(str(ref))
                raise UnknownRefError(
                    'item reference %r no longer exists' % (ref,))

        return item

    def forget(self, item):
        with self._lock:
            ref = self._by_item.pop(id(item), None)
            if ref is not None:
                self._by_ref.pop(ref, None)
            return ref

    def forget_ref(self, ref):
        with self._lock:
            item = self._by_ref.pop(str(ref), None)
            if item is not None:
                self._by_item.pop(id(item), None)
            return item

    def clear(self):
        with self._lock:
            self._by_ref.clear()
            self._by_item.clear()

    def refs(self):
        with self._lock:
            return list(self._by_ref.keys())

    def __len__(self):
        with self._lock:
            return len(self._by_ref)


# ---------------------------------------------------------------------------
# Value validation
# ---------------------------------------------------------------------------

def check_coord(value, name='coordinate'):
    """
    Validates a level coordinate. Rejects bools explicitly: `isinstance(True,
    int)` is True in Python, and a JSON `true` reaching a position would place an
    item at x=1.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyncError('%s must be an integer' % name)
    if not (MIN_COORD <= value <= MAX_COORD):
        raise SyncError('%s %d is out of range' % (name, value))
    return value


def check_dimension(value, name='size'):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyncError('%s must be an integer' % name)
    if not (0 <= value <= MAX_DIMENSION):
        raise SyncError('%s %d is out of range' % (name, value))
    return value


def check_index(value, name='index', maximum=1 << 20):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyncError('%s must be an integer' % name)
    if not (0 <= value <= maximum):
        raise SyncError('%s %d is out of range' % (name, value))
    return value


def check_float(value, name='value', maximum=1 << 20):
    """
    Validates a real number from the wire (path node speed, acceleration).

    An int is accepted and widened, since JSON has no float/int distinction and
    a speed of exactly 1 arrives as an int. NaN and the infinities are refused
    explicitly: both compare False against every bound, so a plain range check
    would let them through and they poison every later calculation.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SyncError('%s must be a number' % name)

    number = float(value)
    if number != number or number in (float('inf'), float('-inf')):
        raise SyncError('%s must be a finite number' % name)

    if not (-maximum <= number <= maximum):
        raise SyncError('%s %r is out of range' % (name, number))

    return number


# ---------------------------------------------------------------------------
# Property values
# ---------------------------------------------------------------------------

def encode_value(value):
    """
    Encodes a property value for JSON.

    RawData (sprite data) is the only non-primitive that appears in A1's
    property snapshots, so it is handled explicitly rather than by pickling
    anything that happens to be there - pickle over a network is an RCE, and
    invariant 1 forbids it outright.
    """
    if value is None or isinstance(value, (bool, int, str, float)):
        return value

    if isinstance(value, (bytes, bytearray)):
        return {'__t': 'bytes', 'v': bytes(value).hex()}

    if isinstance(value, (list, tuple)):
        return [encode_value(entry) for entry in value]

    if isinstance(value, set):
        return {'__t': 'set', 'v': sorted(encode_value(e) for e in value)}

    # RawData: identified structurally so this module need not import Qt or the
    # level item modules.
    original = getattr(value, 'original', None)
    blocks = getattr(value, 'blocks', None)
    if original is not None and blocks is not None:
        return {
            '__t': 'rawdata',
            'original': bytes(original).hex(),
            'blocks': [bytes(block).hex() for block in blocks],
        }

    raise SyncError('cannot encode a value of type %s' % type(value).__name__)


def decode_value(encoded, sprite_format=None):
    """
    Decodes a value produced by encode_value.

    `sprite_format` supplies the Format object RawData needs; it is a local
    property of this build, never taken from the wire, because a peer choosing
    our sprite data format is a peer choosing how we parse bytes.
    """
    if encoded is None or isinstance(encoded, (bool, int, str, float)):
        return encoded

    if isinstance(encoded, list):
        return [decode_value(entry, sprite_format) for entry in encoded]

    if not isinstance(encoded, dict):
        raise SyncError('cannot decode value %r' % (encoded,))

    tag = encoded.get('__t')

    if tag == 'bytes':
        return _decode_hex(encoded.get('v', ''), MAX_SPRITEDATA_BYTES)

    if tag == 'set':
        return set(decode_value(entry, sprite_format)
                   for entry in encoded.get('v', []))

    if tag == 'rawdata':
        if sprite_format is None:
            raise SyncError('sprite data cannot be decoded without a format')

        from reggie.core.raw_data import RawData

        original = _decode_hex(encoded.get('original', ''), MAX_SPRITEDATA_BYTES)
        raw_blocks = encoded.get('blocks', [])
        if not isinstance(raw_blocks, list) or len(raw_blocks) > 64:
            raise SyncError('sprite data has too many blocks')

        blocks = [_decode_hex(block, MAX_SPRITEDATA_BYTES) for block in raw_blocks]
        return RawData(original, *blocks, format=sprite_format)

    raise SyncError('unknown encoded value type %r' % (tag,))


def _decode_hex(text, max_bytes):
    if not isinstance(text, str):
        raise SyncError('expected hex text')
    if len(text) > max_bytes * 2:
        raise SyncError('hex value is too long')
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise SyncError('value is not valid hex')


# ---------------------------------------------------------------------------
# Item description (for snapshots and add operations)
# ---------------------------------------------------------------------------

def item_kind(item):
    """
    The wire kind for a level item, or '' if it is not a syncable item.
    """
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, PathItem,
        CommentItem, ZoneItem,
    )

    # Order matters only in that every class here is distinct; checked
    # explicitly rather than by name so a subclass still maps correctly.
    for kind, cls in ((KIND_OBJECT, ObjectItem),
                      (KIND_SPRITE, SpriteItem),
                      (KIND_ENTRANCE, EntranceItem),
                      (KIND_LOCATION, LocationItem),
                      (KIND_PATH, PathItem),
                      (KIND_COMMENT, CommentItem),
                      (KIND_ZONE, ZoneItem)):
        if isinstance(item, cls):
            return kind

    return ''


def describe_item(item):
    """
    A complete-enough description to recreate an item on another peer.

    Only the constructor arguments plus A1's own property set: whatever
    `snapshot_properties` considers an item's properties is exactly what a
    property op can change, so using the same source keeps the two consistent.
    """
    from reggie.core import undo

    kind = item_kind(item)
    if not kind:
        raise SyncError('item type %s cannot be synchronised'
                        % type(item).__name__)

    description = {
        'kind': kind,
        'x': int(getattr(item, 'objx', 0)),
        'y': int(getattr(item, 'objy', 0)),
        'props': {name: encode_value(value)
                  for name, value in undo.snapshot_properties(item).items()},
    }

    if kind == KIND_OBJECT:
        description.update({
            'tileset': int(item.tileset),
            'type': int(item.type),
            'layer': int(item.layer),
            'w': int(item.width),
            'h': int(item.height),
        })
    elif kind == KIND_SPRITE:
        description['type'] = int(item.type)
    elif kind == KIND_LOCATION:
        description.update({
            'w': int(item.width),
            'h': int(item.height),
            'id': int(item.id),
        })
    elif kind == KIND_COMMENT:
        description['text'] = str(getattr(item, 'text', ''))
    elif kind == KIND_PATH:
        description.update({
            'pathid': int(item.pathid),
            'nodeid': int(item.nodeid),
        })

        # Per-node movement data, so a node recreated on the far side behaves
        # like the original rather than reverting to the defaults. It lives on
        # the parent Path, not the node, which is why it is read here.
        path = getattr(item, 'path', None)
        if path is not None:
            try:
                speed, accel, delay = path.get_data_for_node(int(item.nodeid))
                description.update({
                    'speed': float(speed),
                    'accel': float(accel),
                    'delay': int(delay),
                    'loops': bool(getattr(path, '_loops', False)),
                })
            except (AttributeError, IndexError, TypeError, ValueError):
                pass
    elif kind == KIND_ZONE:
        description['id'] = int(item.id)

    return description


def validate_description(description):
    """
    Bounds-checks an item description that arrived over the network, before
    anything is constructed from it.
    """
    if not isinstance(description, dict):
        raise SyncError('item description must be an object')

    kind = description.get('kind')
    if kind not in ITEM_KINDS:
        raise SyncError('unknown item kind %r' % (kind,))

    clean = {
        'kind': kind,
        'x': check_coord(description.get('x', 0), 'x'),
        'y': check_coord(description.get('y', 0), 'y'),
    }

    props = description.get('props', {})
    if not isinstance(props, dict):
        raise SyncError('item properties must be an object')
    if len(props) > 64:
        raise SyncError('item has too many properties')
    clean['props'] = props

    if kind == KIND_OBJECT:
        clean.update({
            'tileset': check_index(description.get('tileset', 0), 'tileset', 3),
            'type': check_index(description.get('type', 0), 'type', 1 << 16),
            'layer': check_index(description.get('layer', 0), 'layer', 2),
            'w': check_dimension(description.get('w', 1), 'width'),
            'h': check_dimension(description.get('h', 1), 'height'),
        })
    elif kind == KIND_SPRITE:
        clean['type'] = check_index(description.get('type', 0), 'sprite type', 1 << 12)
    elif kind == KIND_LOCATION:
        clean.update({
            'w': check_dimension(description.get('w', 1), 'width'),
            'h': check_dimension(description.get('h', 1), 'height'),
            'id': check_index(description.get('id', 0), 'location id', 255),
        })
    elif kind == KIND_COMMENT:
        text = description.get('text', '')
        if not isinstance(text, str):
            raise SyncError('comment text must be text')
        clean['text'] = protocol.sanitize_text(text, protocol.MAX_STRING_CHARS)
    elif kind == KIND_PATH:
        clean.update({
            'pathid': check_index(description.get('pathid', 0), 'path id', 255),
            'nodeid': check_index(description.get('nodeid', 0), 'node id', 4095),
            'speed': check_float(description.get('speed', 0.5), 'speed'),
            'accel': check_float(description.get('accel', 0.00498), 'accel'),
            'delay': check_index(description.get('delay', 0), 'delay', 1 << 16),
            'loops': bool(description.get('loops', False)),
        })
    elif kind == KIND_ZONE:
        clean['id'] = check_index(description.get('id', 0), 'zone id', 15)

    return clean


# ---------------------------------------------------------------------------
# Operation encoding
# ---------------------------------------------------------------------------

def encode_move(refmap, entries):
    """
    entries: [(item, (old_x, old_y), (new_x, new_y))] - the shape A1's
    MoveItemsCommand already uses, so a broadcast hook can pass its own data
    straight through.
    """
    targets = []
    for item, old, new in entries:
        ref = refmap.ref_for(item)
        if ref is None:
            raise SyncError('cannot broadcast a move for an unreferenced item')
        targets.append({
            'ref': ref,
            'before': {'x': int(old[0]), 'y': int(old[1])},
            'after': {'x': int(new[0]), 'y': int(new[1])},
        })

    return {'kind': 'move', 'targets': targets}


def encode_resize(refmap, entries):
    """
    entries: [(item, (old_x, old_y, old_w, old_h), (new_x, new_y, new_w, new_h))]
    """
    targets = []
    for item, old, new in entries:
        ref = refmap.ref_for(item)
        if ref is None:
            raise SyncError('cannot broadcast a resize for an unreferenced item')
        targets.append({
            'ref': ref,
            'before': {'x': int(old[0]), 'y': int(old[1]),
                       'w': int(old[2]), 'h': int(old[3])},
            'after': {'x': int(new[0]), 'y': int(new[1]),
                      'w': int(new[2]), 'h': int(new[3])},
        })

    return {'kind': 'resize', 'targets': targets}


def encode_add(refmap, items):
    """
    Encodes newly created items. The host mints a reference for each, so the
    same reference identifies the item on every peer from then on.
    """
    targets = []
    for item in items:
        targets.append({
            'ref': refmap.mint(item),
            'after': describe_item(item),
        })

    return {'kind': 'add', 'targets': targets}


def encode_remove(refmap, items):
    targets = []
    for item in items:
        ref = refmap.ref_for(item)
        if ref is None:
            raise SyncError('cannot broadcast a removal for an unreferenced item')
        targets.append({'ref': ref, 'before': describe_item(item)})

    return {'kind': 'remove', 'targets': targets}


def encode_property(refmap, item, before, after):
    """
    before/after: {attr: value} as produced by undo.snapshot_properties.
    """
    ref = refmap.ref_for(item)
    if ref is None:
        raise SyncError('cannot broadcast a property change for an unreferenced item')

    return {
        'kind': 'property',
        'targets': [{
            'ref': ref,
            'before': {name: encode_value(value) for name, value in before.items()},
            'after': {name: encode_value(value) for name, value in after.items()},
        }],
    }


def encode_dialog_op(kind, before, after):
    """
    Encodes a Full-only dialog operation (area_settings, metadata).

    These are `{key: value}` snapshots, matching A1's AreaSettingsCommand and
    MetadataCommand. Zones use encode_zones instead, because A1's zone snapshot
    is keyed on live object identity.
    """
    if kind not in protocol.OP_KINDS_FULL_ONLY:
        raise SyncError('%r is not a dialog operation' % (kind,))
    if kind == 'zones':
        raise SyncError('use encode_zones() for zone snapshots')

    return {
        'kind': kind,
        'targets': [],
        'before': _encode_snapshot(before),
        'after': _encode_snapshot(after),
    }


def encode_zones(before_state, after_state):
    """
    Encodes a zones change from A1's snapshot format.

    A1's `snapshot_zones()` returns `[(zone_object, {attr: value})]`. The object
    half cannot cross a network, so only the attribute dicts travel, positionally
    - index 0 is the first zone on both peers. That is sound because the zone
    *count* is not allowed to change remotely (see _apply_zones), so the ordering
    is stable for the lifetime of a synchronised edit.
    """
    def strip(state):
        entries = []
        for entry in state or ():
            # Accept both A1's (zone, values) pairs and bare dicts, so a caller
            # that already has plain attribute dicts need not fake a zone object.
            values = entry[1] if isinstance(entry, (tuple, list)) else entry
            if not isinstance(values, dict):
                raise SyncError('a zone snapshot entry must be a mapping')
            entries.append({str(k): encode_value(v) for k, v in values.items()})
        return entries

    return {
        'kind': 'zones',
        'targets': [],
        'before': strip(before_state),
        'after': strip(after_state),
    }


def _encode_snapshot(snapshot):
    if snapshot is None:
        return {}
    if not isinstance(snapshot, dict):
        raise SyncError('a snapshot must be a mapping')
    return {str(key): encode_value(value) for key, value in snapshot.items()}


# ---------------------------------------------------------------------------
# Applying remote operations
# ---------------------------------------------------------------------------

def apply_remote(op_payload, refmap, sprite_format=None, area=None):
    """
    Applies a remote operation to the local level.

    **Runs inside A1's _ApplyGuard**, so nothing it does is recorded in the local
    undo stack. That is the whole point: undo is local and per-user, and a peer's
    edit must never become an entry in your history that you could "undo" out
    from under them.

    Must be called on the Qt main thread. Returns a description of what changed,
    for the UI to report. Raises SyncError (or UnknownRefError) if the op cannot
    be applied; the caller answers with op_reject.
    """
    from reggie.core import undo

    kind = op_payload.get('kind', '')
    if kind not in protocol.OP_KINDS:
        raise SyncError('unknown operation kind %r' % (kind,))

    handler = _APPLIERS.get(kind)
    if handler is None:
        raise SyncError('operation kind %r cannot be applied yet' % (kind,))

    # The guard is what keeps this out of the local undo stack. Everything below
    # runs inside it, including item creation and deletion.
    with undo._ApplyGuard():
        result = handler(op_payload, refmap, sprite_format, area)
        _finish_mutation_if_possible()

    return result


def _finish_mutation_if_possible():
    """
    Calls A1's _finish_mutation(), tolerating the absence of a main window.

    _finish_mutation() reaches through globals_.mainWindow.scene, which is fine
    in the running editor but raises during headless use. Since it only refreshes
    the view and marks the level dirty, skipping it when there is no window is
    correct rather than merely convenient - and it means a validation failure
    surfaces as SyncError rather than an AttributeError from deep inside undo.
    """
    from reggie.core import globals_, undo

    window = getattr(globals_, 'mainWindow', None)
    if window is None or getattr(window, 'scene', None) is None:
        return

    undo._finish_mutation()


def _apply_move(payload, refmap, sprite_format, area):
    from reggie.core import undo

    moved = []
    for target in _targets(payload):
        item = refmap.require(target.get('ref'))
        after = target.get('after') or {}
        x = check_coord(after.get('x', 0), 'x')
        y = check_coord(after.get('y', 0), 'y')
        undo._apply_position(item, x, y)
        moved.append(item)

    return {'kind': 'move', 'items': moved}


def _apply_resize(payload, refmap, sprite_format, area):
    from reggie.core import undo

    resized = []
    for target in _targets(payload):
        item = refmap.require(target.get('ref'))
        after = target.get('after') or {}
        undo._apply_geometry(
            item,
            check_coord(after.get('x', 0), 'x'),
            check_coord(after.get('y', 0), 'y'),
            check_dimension(after.get('w', 1), 'width'),
            check_dimension(after.get('h', 1), 'height'),
        )
        resized.append(item)

    return {'kind': 'resize', 'items': resized}


def _apply_property(payload, refmap, sprite_format, area):
    from reggie.core import undo

    changed = []
    for target in _targets(payload):
        item = refmap.require(target.get('ref'))
        after = target.get('after') or {}

        if not isinstance(after, dict):
            raise SyncError('property values must be an object')

        # Only attributes A1 itself considers properties of this item may be
        # set. Without this an op could assign any attribute on the object -
        # including Qt internals - which is a remote-code-execution-adjacent
        # foothold, not merely a data bug.
        allowed = set(undo.snapshot_properties(item).keys())

        for name, encoded in after.items():
            if name not in allowed:
                raise SyncError('property %r is not editable on this item' % (name,))
            setattr(item, name, decode_value(encoded, sprite_format))

        undo._refresh_item(item)
        changed.append(item)

    return {'kind': 'property', 'items': changed}


def _apply_add(payload, refmap, sprite_format, area):
    created = []

    for target in _targets(payload):
        ref = target.get('ref')
        if not ref or not isinstance(ref, str):
            raise SyncError('an added item needs a reference')

        # Idempotent: a duplicated broadcast must not create a second item.
        if refmap.item_for(ref) is not None:
            continue

        description = validate_description(target.get('after'))
        item = create_item(description, sprite_format, area)
        refmap.bind(ref, item)
        created.append(item)

    return {'kind': 'add', 'items': created}


def _apply_remove(payload, refmap, sprite_format, area):
    from reggie.core import undo

    removed = []
    for target in _targets(payload):
        ref = target.get('ref')
        item = refmap.item_for(ref)

        # Already gone: accept silently. Remove is idempotent by nature, and
        # rejecting here would make two peers deleting the same item produce a
        # spurious conflict.
        if item is None:
            continue

        undo._detach_item(item)
        refmap.forget(item)
        removed.append(item)

    return {'kind': 'remove', 'items': removed}


def _apply_zones(payload, refmap, sprite_format, area):
    """
    Applies a remote zones change.

    A1's `snapshot_zones()` is `[(zone_object, {attrs})]` - keyed on live object
    identity, which cannot cross a network. So the wire form is a list of
    attribute dicts in zone order (see encode_zones), and applying means
    updating the existing zones in place.

    Zone *count* changes are applied too, so a peer adding or deleting a zone is
    reflected rather than refused. This was deferred in phase 5 on the grounds
    that building a ZoneItem needs the Zones dialog's own bookkeeping - which is
    true, and is why _create_zone goes through the editor's CreateZone factory
    instead of calling the constructor. Refusing was the safe placeholder; it
    left a client silently holding a different zone set from the host.
    """
    from reggie.core import globals_

    # Read the raw value: `or []` would silently turn a wrong-typed but falsy
    # value (an empty dict, say) into a valid empty list and skip the check.
    entries = payload.get('after')
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise SyncError('a zones snapshot must be a list')

    if len(entries) > protocol.MAX_ZONES:
        raise SyncError('a zones operation cannot contain more than %d zones'
                        % protocol.MAX_ZONES)

    # Every entry is validated before anything is created or destroyed, so a
    # malformed op cannot leave the zone set half-changed.
    for values in entries:
        if not isinstance(values, dict):
            raise SyncError('each zone entry must be an object')

    live = getattr(globals_.Area, 'zones', None)
    if not isinstance(live, list):
        raise SyncError('this level has no zone list')

    while len(live) > len(entries):
        _destroy_zone(live.pop())

    while len(live) < len(entries):
        created = _create_zone(len(live))
        if created is None:
            raise SyncError('a zone could not be created for this operation')
        live.append(created)

    zones = list(live)

    from reggie.core.undo import _ZONE_ATTRS

    allowed = set(_ZONE_ATTRS)

    for zone, values in zip(zones, entries):
        for name, value in values.items():
            if name not in allowed:
                raise SyncError('zone attribute %r is not editable' % (name,))
            if isinstance(value, bool) or isinstance(value, (int, float, str)):
                setattr(zone, name, value)
            else:
                raise SyncError('zone attribute %r has an unsupported value'
                                % (name,))

        zone.prepareGeometryChange()
        zone.UpdateRects()
        zone.setPos(zone.objx * 1.5, zone.objy * 1.5)
        zone.UpdateTitle()

    _refresh_after_zone_change(zones)

    return {'kind': 'zones', 'items': zones}


def _apply_area_settings(payload, refmap, sprite_format, area):
    """
    Applies a remote area-settings change (Area Options, camera profiles).

    Mirrors AreaSettingsCommand._apply, but only for attributes the host
    actually sent, and only names that already exist on the Area - so an op
    cannot introduce an arbitrary attribute.
    """
    from reggie.core import globals_

    snapshot = payload.get('after') or {}
    if not isinstance(snapshot, dict):
        raise SyncError('an area settings snapshot must be an object')
    if len(snapshot) > 64:
        raise SyncError('area settings snapshot is too large')

    target = area if area is not None else globals_.Area

    # An explicit allowlist, matching _ZONE_ATTRS and _METADATA_KEYS in the
    # sibling appliers. A `hasattr` gate would be weaker: dunders and any other
    # pre-existing attribute would pass it, so the set of writable names would
    # be "whatever the object happens to have" rather than "what the Area
    # Options dialog edits".
    allowed = AREA_SETTINGS_ATTRS

    tilesets_changed = False

    for name, encoded in snapshot.items():
        if name not in allowed:
            raise SyncError('area setting %r is not editable' % (name,))

        value = decode_value(encoded, sprite_format)

        if name in TILESET_ATTRS and getattr(target, name, None) != value:
            tilesets_changed = True

        setattr(target, name, value)

    # Setting the name is not loading the tileset. A1's AreaSettingsCommand
    # takes a refresh_tilesets flag and calls RefreshTilesetsFromArea(); this
    # applier only did the setattr, so a peer's tileset change showed the new
    # name in the Area Options dialog while the canvas kept drawing the old
    # tiles - which is exactly how Zement described it.
    #
    # Guarded on an actual change because the reload is expensive: it re-reads
    # up to four tileset archives and rebuilds the object picker, so doing it
    # for every unrelated area-settings op (a time limit, an entrance number)
    # would stall the editor for no reason.
    if tilesets_changed:
        _refresh_tilesets()

    return {'kind': 'area_settings', 'items': []}


# The subset of AREA_SETTINGS_ATTRS that names a tileset archive.
TILESET_ATTRS = frozenset({'tileset0', 'tileset1', 'tileset2', 'tileset3'})


def _refresh_tilesets():
    """
    Reloads the tilesets named by the Area and refreshes everything drawn from
    them.

    Best-effort: the names are already applied, so a failed reload leaves the
    level correct in the file and wrong on screen until the next load - which
    is much better than aborting a remote op that has already been accepted.
    """
    from reggie.core import globals_

    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        return

    refresh = getattr(window, 'RefreshTilesetsFromArea', None)
    if refresh is None:
        return

    try:
        refresh()
    except Exception:
        pass


# The area attributes the Area Options and camera dialogs can change.
#
# Mirrors ReggieWindow._AREA_SETTINGS_ATTRS. Duplicated rather than imported on
# purpose: this module must not import reggie.ui (it would drag Qt into a layer
# that is deliberately Qt-free and headless-testable), and an authorisation
# allowlist is exactly the kind of thing that should be readable in the file
# that enforces it. A test asserts the two lists stay in step.
AREA_SETTINGS_ATTRS = frozenset({
    'loaded_sprites', 'force_loaded_sprites', 'timeLimit', 'startEntrance',
    'toadHouseType', 'wrapFlag', 'creditsFlag', 'faceLeftFlag',
    'unkFlag1', 'unkFlag2', 'unkVal1', 'unkVal2',
    'tileset0', 'tileset1', 'tileset2', 'tileset3',
})


def _apply_metadata(payload, refmap, sprite_format, area):
    """
    Applies remote level-info strings. Restricted to A1's own key list so an op
    cannot write arbitrary metadata blocks.
    """
    from reggie.core import globals_
    from reggie.core.undo import _METADATA_KEYS

    snapshot = payload.get('after') or {}
    if not isinstance(snapshot, dict):
        raise SyncError('a metadata snapshot must be an object')

    for key, value in snapshot.items():
        if key not in _METADATA_KEYS:
            raise SyncError('unknown metadata key %r' % (key,))
        if not isinstance(value, str):
            raise SyncError('metadata %r must be text' % (key,))

        globals_.Area.Metadata.setStrData(
            key, protocol.sanitize_text(value, protocol.MAX_STRING_CHARS))

    return {'kind': 'metadata', 'items': []}


PATH_NODE_FIELDS = ('speed', 'accel', 'delay')


def _apply_path_data(payload, refmap, sprite_format, area):
    """
    Applies a remote path node data change (speed / accel / delay).

    Goes through `node.path.set_node_data()`, which is what A1's
    PathNodeDataCommand uses - writing the node's fields directly would skip the
    path's own bookkeeping.
    """
    from reggie.core import undo

    changed = []
    for target in _targets(payload):
        item = refmap.require(target.get('ref'))
        after = target.get('after') or {}

        if not isinstance(after, dict):
            raise SyncError('path node data must be an object')

        path = getattr(item, 'path', None)
        setter = getattr(path, 'set_node_data', None)
        if setter is None:
            raise SyncError('item is not a path node')

        values = {}
        for name, value in after.items():
            if name not in PATH_NODE_FIELDS:
                raise SyncError('unknown path node field %r' % (name,))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SyncError('path node field %r must be numeric' % (name,))
            values[name] = value

        if not values:
            continue

        setter(item, **values)
        undo._refresh_path_editor(item)
        changed.append(item)

    return {'kind': 'path_data', 'items': changed}


def encode_path_data(refmap, node, before, after):
    """
    Encodes a path node data change. before/after are A1's
    (speed, accel, delay) tuples.
    """
    ref = refmap.ref_for(node)
    if ref is None:
        raise SyncError('cannot broadcast path data for an unreferenced node')

    def as_fields(values):
        if isinstance(values, dict):
            return {k: v for k, v in values.items() if k in PATH_NODE_FIELDS}
        return dict(zip(PATH_NODE_FIELDS, values))

    return {
        'kind': 'path_data',
        'targets': [{
            'ref': ref,
            'before': as_fields(before),
            'after': as_fields(after),
        }],
    }


PATH_SETTINGS = ('loops', 'id')


def _apply_path_setting(payload, refmap, sprite_format, area):
    """
    Applies a whole-path setting change: 'loops' (bool) or 'id' (int).

    Mirrors A1's PathSettingCommand, using the path's own set_loops/set_id so the
    path bookkeeping stays consistent. The reference names a *node*, since that
    is what the ref map tracks; the path is reached through it.
    """
    from reggie.core import undo

    changed = []
    for target in _targets(payload):
        node = refmap.require(target.get('ref'))
        after = target.get('after') or {}

        if not isinstance(after, dict):
            raise SyncError('path setting must be an object')

        path = getattr(node, 'path', None)
        if path is None:
            raise SyncError('item is not a path node')

        for name, value in after.items():
            if name not in PATH_SETTINGS:
                raise SyncError('unknown path setting %r' % (name,))

            if name == 'loops':
                if not isinstance(value, bool):
                    raise SyncError('path "loops" must be true or false')
                path.set_loops(value)
            else:
                path.set_id(check_index(value, 'path id', 255))

        undo._refresh_path_editor(node)
        changed.append(node)

    return {'kind': 'path_setting', 'items': changed}


def _apply_path_order(payload, refmap, sprite_format, area):
    """
    Applies a node being moved to a different index within its path.
    """
    from reggie.core import undo

    changed = []
    for target in _targets(payload):
        node = refmap.require(target.get('ref'))
        after = target.get('after') or {}

        if not isinstance(after, dict):
            raise SyncError('path order must be an object')

        path = getattr(node, 'path', None)
        mover = getattr(path, 'move_node', None)
        if mover is None:
            raise SyncError('item is not a path node')

        index = check_index(after.get('index', 0), 'node index', 4095)
        mover(node, index)

        undo._refresh_path_editor(node)
        changed.append(node)

    return {'kind': 'path_order', 'items': changed}


def encode_path_setting(refmap, node, setting, before, after):
    if setting not in PATH_SETTINGS:
        raise SyncError('unknown path setting %r' % (setting,))

    ref = refmap.ref_for(node)
    if ref is None:
        raise SyncError('cannot broadcast a path setting for an unreferenced node')

    return {
        'kind': 'path_setting',
        'targets': [{
            'ref': ref,
            'before': {setting: before},
            'after': {setting: after},
        }],
    }


def encode_path_order(refmap, node, old_index, new_index):
    ref = refmap.ref_for(node)
    if ref is None:
        raise SyncError('cannot broadcast a node move for an unreferenced node')

    return {
        'kind': 'path_order',
        'targets': [{
            'ref': ref,
            'before': {'index': int(old_index)},
            'after': {'index': int(new_index)},
        }],
    }


def _targets(payload):
    targets = payload.get('targets')
    if not isinstance(targets, list):
        raise SyncError('operation targets must be a list')
    if len(targets) > protocol.MAX_OP_TARGETS:
        raise SyncError('operation has too many targets')

    for target in targets:
        if not isinstance(target, dict):
            raise SyncError('each operation target must be an object')

    return targets


_APPLIERS = {
    'move': _apply_move,
    'resize': _apply_resize,
    'property': _apply_property,
    'add': _apply_add,
    'remove': _apply_remove,
    'path_data': _apply_path_data,
    'path_setting': _apply_path_setting,
    'path_order': _apply_path_order,
    'zones': _apply_zones,
    'area_settings': _apply_area_settings,
    'metadata': _apply_metadata,
}


# ---------------------------------------------------------------------------
# Item creation
# ---------------------------------------------------------------------------

def create_item(description, sprite_format=None, area=None):
    """
    Creates a level item from a validated description and attaches it.

    `description` must already have been through validate_description: this
    function trusts its bounds, so calling it with raw wire data would defeat
    the checks.
    """
    from reggie.core import globals_
    from reggie.core.levelitems import (
        ObjectItem, SpriteItem, EntranceItem, LocationItem, CommentItem,
    )

    kind = description['kind']
    target_area = area if area is not None else globals_.Area

    if kind == KIND_OBJECT:
        item = ObjectItem(description['tileset'], description['type'],
                          description['layer'], description['x'], description['y'],
                          description['w'], description['h'], 0)
        target_area.layers[description['layer']].append(item)

    elif kind == KIND_SPRITE:
        from reggie.core.raw_data import RawData

        data = description['props'].get('spritedata')
        if data is not None:
            raw = decode_value(data, sprite_format)
        elif sprite_format is not None:
            raw = RawData(bytes(8), format=sprite_format)
        else:
            raise SyncError('a sprite needs sprite data or a format')

        item = SpriteItem(description['type'], description['x'],
                          description['y'], raw)
        target_area.sprites.append(item)

    elif kind == KIND_ENTRANCE:
        # Signature (levelitems.py:2522):
        #   (x, y, id, destarea, destentrance, type, zone, layer, path,
        #    settings, leave_level_val, cpd)
        # A1's property names differ from the parameter names, so map explicitly
        # rather than by position guesswork.
        props = description['props']
        item = EntranceItem(
            description['x'], description['y'],
            int(props.get('entid', 0)),
            int(props.get('destarea', 0)),
            int(props.get('destentrance', 0)),
            int(props.get('enttype', 0)),
            int(props.get('entzone', 0)),
            int(props.get('entlayer', 0)),
            int(props.get('entpath', 0)),
            int(props.get('entsettings', 0)),
            int(props.get('leave_level', 0)),
            int(props.get('cpdirection', 0)),
        )
        target_area.entrances.append(item)

    elif kind == KIND_LOCATION:
        item = LocationItem(description['x'], description['y'],
                            description['w'], description['h'],
                            description['id'])
        target_area.locations.append(item)

    elif kind == KIND_COMMENT:
        item = CommentItem(description['x'], description['y'],
                           description.get('text', ''))
        target_area.comments.append(item)

    elif kind == KIND_PATH:
        # Returns early: Path.add_node has already inserted the node into the
        # scene, the path and the side list, so the shared registration below
        # would add a second list row for one object.
        return _create_path_node(description, target_area)

    else:
        # A zone is created through its own dialog, which owns bookkeeping this
        # layer cannot reproduce (background sets, camera profiles, bounding
        # entries), so a bare 'add' for one is refused rather than half-handled.
        raise SyncError('remote creation of %r is not supported' % (kind,))

    _register_created_item(item, target_area)
    return item


def _ensure_list_item(item):
    """
    Builds the side-list row a remotely created item needs.

    The item classes set `listitem = None` and leave it to whoever creates the
    item to build the row - the editor's own CreateEntrance/CreateLocation do
    it right after construction. The collaboration path did not, so
    `_attach_item` added None to the list widget and the item existed on the
    canvas but never appeared in the Entrances, Locations or Comments panel.
    That is what testers saw: everyone's items drawn correctly, but each list
    showing only its owner's.

    Sprites are not here on purpose: SpriteList is a table, and _attach_item
    calls addSprite() rather than inserting a prebuilt row.
    """
    from reggie.core.levelitems import (
        EntranceItem, LocationItem, CommentItem, PathItem,
        ListWidgetItem_SortsByOther,
    )
    from PyQt6 import QtWidgets

    if getattr(item, 'listitem', None) is not None:
        return

    if isinstance(item, (EntranceItem, LocationItem, PathItem)):
        item.listitem = ListWidgetItem_SortsByOther(item)
    elif isinstance(item, CommentItem):
        # Comments sort by insertion, not by a key on the item, so a plain row
        # is what the editor builds for them too.
        item.listitem = QtWidgets.QListWidgetItem()


def _create_path_node(description, target_area):
    """
    Creates a path node from a remote 'add', reusing the editor's own routines.

    Refusing this was wrong rather than merely incomplete: drawing a path is an
    ordinary edit, and a client that drew one had every node rejected with
    "remote creation of 'path' is not supported" while the host kept them - so
    the two sides silently diverged, which is exactly what op sync exists to
    prevent.

    Everything goes through Path.add_node, which is the single place the editor
    itself creates a node (misc2.py's click handler calls it too). It owns the
    bookkeeping that makes a node work: renumbering later nodes, the side-list
    entry, the polyline item, and the scene insert. Constructing a PathItem here
    would reproduce a subset of that and drift from it.

    Returns the new node. Unlike the other kinds this one does NOT want
    _register_created_item afterwards - add_node has already placed it - which
    is why it is a separate function rather than another branch that falls
    through to the shared registration.
    """
    from reggie.core import globals_
    from reggie.core.levelitems import Path

    path_id = int(description['pathid'])
    node_id = int(description['nodeid'])

    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        raise SyncError('cannot create a path node without the editor')

    path = None
    for existing in target_area.paths:
        if int(getattr(existing, '_id', -1)) == path_id:
            path = existing
            break

    if path is None:
        path = Path(path_id, window.scene, bool(description.get('loops', False)))
        target_area.paths.append(path)

    # Clamp rather than refuse: the peer's node index is only a hint about
    # ordering, and an out-of-range one means the two sides briefly disagree
    # about the node count - a reason to append, not to drop the edit.
    index = max(0, min(node_id, len(path._nodes)))

    node = path.add_node(
        description['x'], description['y'],
        speed=float(description.get('speed', 0.5)),
        accel=float(description.get('accel', 0.00498)),
        delay=int(description.get('delay', 0)),
        index=index,
    )

    # add_node only wires this when add_to_list is used from the editor path;
    # without it a later drag of this node updates nothing else.
    node.positionChanged = window.HandlePathPosChange

    try:
        window.pathEditor.UpdatePathLength()
    except Exception:
        pass

    return node


def _register_created_item(item, area):
    """
    Puts a newly created item into the scene AND the editor's side lists.

    Adding it to the scene alone is not enough, and the difference is not
    cosmetic: the sprite list is a table whose rows carry the sprite object, and
    SpriteList.updateSprite() looks a sprite up with getRowFor(), which returns
    -1 when there is no row. The caller then does table.item(-1, column), gets
    None, and every property edit raises

        AttributeError: 'NoneType' object has no attribute 'setText'

    which is what Zement hit on sprites but not entrances - the entrance editor
    does not go through that table.

    Delegates to A1's _attach_item rather than repeating its per-type
    bookkeeping. That function already knows about id-type registration, comment
    text proxies, path node renumbering and z-order, and each of those is a
    separate way for a hand-rolled version to be subtly wrong.

    The item was appended to the area list by the caller, so it is removed again
    first: _attach_item inserts at a given index and would otherwise leave a
    second entry pointing at the same object.
    """
    from reggie.core import globals_, undo

    window = getattr(globals_, 'mainWindow', None)
    if window is None or getattr(window, 'scene', None) is None:
        # Headless: the area lists are the whole model, and the caller has
        # already updated them.
        return item

    _ensure_list_item(item)

    index = _remove_from_area_lists(item, area)

    try:
        undo._attach_item(item, {'index': index})
    except Exception:
        # Attachment is best-effort: an item visible but missing from a side
        # list is recoverable, whereas an exception here would abort the whole
        # snapshot and leave the level half-built.
        if item.scene() is None:
            window.scene.addItem(item)

    return item


def _remove_from_area_lists(item, area):
    """
    Takes an item back out of the area lists, returning the index it held.

    _attach_item owns insertion; this undoes the caller's append so the two do
    not both add it.
    """
    from reggie.core import globals_

    target = area if area is not None else getattr(globals_, 'Area', None)
    if target is None:
        return 0

    for name in ('sprites', 'entrances', 'locations', 'comments', 'paths'):
        group = getattr(target, name, None)
        if isinstance(group, list):
            for index, existing in enumerate(group):
                if existing is item:
                    del group[index]
                    return index

    layers = getattr(target, 'layers', None)
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, list):
                for index, existing in enumerate(layer):
                    if existing is item:
                        del layer[index]
                        return index

    return 0


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def build_snapshot(refmap, area=None, area_number=1):
    """
    Builds a full snapshot of an area for a joining peer.

    Host side: mints a reference for every item, so both peers agree on
    identities from the first frame.
    """
    from reggie.core import globals_

    target_area = area if area is not None else globals_.Area
    items = []

    for group in _snapshot_groups(target_area):
        for item in group:
            try:
                description = describe_item(item)
            except SyncError:
                # An item type we cannot describe is skipped rather than
                # aborting the whole snapshot; the peer simply will not see it,
                # which is recoverable, unlike a failed join.
                continue

            description['ref'] = refmap.mint(item)
            items.append(description)

            if len(items) > MAX_SNAPSHOT_ITEMS:
                raise SyncError('this level has too many items to synchronise')

    return {
        'area': int(area_number),
        'items': items,
        'total': len(items),
        'zones': _snapshot_zone_attrs(target_area),
        'tilesets': _snapshot_tilesets(target_area),
    }


def _snapshot_zone_attrs(area):
    """
    The zones' attributes, positionally.

    Only the attributes travel, not the zone objects: A1's snapshot_zones() is
    keyed on live objects, and a ZoneItem cannot be reconstructed from the wire
    without the Zones dialog's own bookkeeping. Sending them means a joining
    client sees the host's camera bounds, backgrounds and music rather than
    whatever its own file happened to contain.
    """
    from reggie.core.undo import _ZONE_ATTRS

    zones = getattr(area, 'zones', None)
    if not isinstance(zones, list):
        return []

    return [{attr: getattr(zone, attr) for attr in _ZONE_ATTRS
             if hasattr(zone, attr)}
            for zone in zones[:protocol.MAX_ZONES]]


def _snapshot_tilesets(area):
    """
    The four tileset names.

    Names only - the tileset *files* are never transferred here; the client
    loads its own copy by name, which is why both peers need the same patch.
    Without this a client that had another level open kept that level's
    tilesets, so every object rendered as the wrong graphic.
    """
    return [str(getattr(area, 'tileset%d' % slot, '') or '')
            for slot in range(4)]


def _snapshot_groups(area):
    return (
        list(getattr(area, 'layers', [[], [], []])[0]),
        list(getattr(area, 'layers', [[], [], []])[1]),
        list(getattr(area, 'layers', [[], [], []])[2]),
        list(getattr(area, 'sprites', [])),
        list(getattr(area, 'entrances', [])),
        list(getattr(area, 'locations', [])),
        list(getattr(area, 'comments', [])),
    )


def _apply_snapshot_tilesets(names, area=None):
    """
    Adopts the host's tileset names and reloads the object palettes.

    Without this a client that had a different level open kept that level's
    tilesets, so the host's objects rendered as whatever happened to occupy the
    same slots - Zement's 01-02 tilesets showing under 01-01's objects.

    Only the *names* cross the network; the files are loaded from the client's
    own copy of the patch, which is what the patch check exists to guarantee.
    """
    from reggie.core import globals_

    if not isinstance(names, list) or not names:
        return False

    target = area if area is not None else getattr(globals_, 'Area', None)
    if target is None:
        return False

    changed = False
    for slot, name in enumerate(names[:4]):
        # A tileset name is a filename component from a peer, so it goes through
        # the same validation as any other path fragment. An empty slot is legal
        # and means "no tileset".
        clean = str(name or '')
        if clean and not _is_safe_tileset_name(clean):
            raise SyncError('invalid tileset name %r' % (clean,))

        attribute = 'tileset%d' % slot
        if getattr(target, attribute, None) != clean:
            setattr(target, attribute, clean)
            changed = True

    if not changed:
        return False

    _reload_tilesets()
    return True


def _is_safe_tileset_name(name):
    """
    A tileset name must be a plain filename component.

    Rejects separators, traversal and null bytes: the name is handed to the
    tileset loader, which turns it into a path.
    """
    if len(name) > 64:
        return False
    if name != name.strip():
        return False

    for bad in ('/', '\\', '..', '\x00', ':'):
        if bad in name:
            return False

    return True


def _reload_tilesets():
    """
    Reloads the tilesets named on the area and refreshes everything drawn with
    them.

    Guarded: a missing tileset is a patch mismatch, which is reported elsewhere
    and must not abort the snapshot - the level is still worth showing.
    """
    from reggie.core import globals_

    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        return

    # ReloadTilesets reads the tileset names straight off globals_.Area, which
    # the caller has just replaced, and then does the whole job: loads each
    # tileset, refreshes the object picker, rebuilds every placed object's cache
    # and repaints. Calling it is strictly better than reimplementing that here.
    #
    # soft=False on purpose: "soft" skips reloading when the filepaths have not
    # changed, and the names have just changed under it, so the reload must be
    # forced.
    reload_tilesets = getattr(window, 'ReloadTilesets', None)
    if not callable(reload_tilesets):
        return

    try:
        reload_tilesets(False)
    except Exception:
        # A tileset the client does not have is a patch mismatch, reported by
        # the patch check rather than here. The level is still worth showing.
        pass


def _apply_snapshot_zones(zone_states, area=None):
    """
    Copies the host's zone attributes onto the client's zones.

    Positional, like every other zone operation here, and refused outright when
    the counts differ: creating or destroying a ZoneItem needs the Zones
    dialog's own bookkeeping, so a mismatch is reported rather than half-applied
    (see _apply_zones, which takes the same position).

    A count mismatch during a *snapshot* is not fatal to the snapshot: the items
    are still worth applying, and the user is better served by a level with the
    wrong camera bounds than by no level at all. So this returns False rather
    than raising.
    """
    from reggie.core import globals_
    from reggie.core.undo import _ZONE_ATTRS

    if not isinstance(zone_states, list):
        return False

    target = area if area is not None else getattr(globals_, 'Area', None)
    zones = getattr(target, 'zones', None) if target is not None else None
    if not isinstance(zones, list):
        return False

    if len(zone_states) > protocol.MAX_ZONES:
        raise SyncError('a snapshot cannot contain more than %d zones'
                        % protocol.MAX_ZONES)

    # Match the host's zone count before applying attributes. Previously a
    # mismatch was skipped entirely, which left a client holding the zones of
    # whatever level it had open - visibly wrong, and silently so.
    while len(zones) > len(zone_states):
        _destroy_zone(zones.pop())

    while len(zones) < len(zone_states):
        created = _create_zone(len(zones))
        if created is None:
            # Cannot build one here (no main window). Apply what we can to the
            # zones that do exist rather than failing the whole snapshot.
            break
        zones.append(created)

    allowed = set(_ZONE_ATTRS)

    for zone, state in zip(zones, zone_states):
        if not isinstance(state, dict):
            continue

        for attr, value in state.items():
            if attr not in allowed:
                # Same allowlist as _apply_zones: "whatever the peer sent" is
                # never an acceptable definition of what may be assigned.
                continue
            if isinstance(value, bool) or isinstance(value, (int, str)):
                setattr(zone, attr, value)

        try:
            zone.prepareGeometryChange()
            zone.UpdateRects()
            zone.setPos(zone.objx * 1.5, zone.objy * 1.5)
            zone.UpdateTitle()
            zone.update()
        except Exception:
            pass

    _refresh_after_zone_change(zones)
    return True


def _create_zone(index):
    """
    Builds a new ZoneItem for a snapshot, or None when there is no editor.

    Uses the editor's own CreateZone factory rather than calling ZoneItem
    directly. The constructor takes sixteen positional arguments plus three
    lookup-table arguments (boundings/bgA/bgB) whose only purpose is to find the
    values that _ZONE_ATTRS carries anyway - so building one by hand would mean
    reproducing a defaults table that already exists in exactly one place.

    add_to_scene=False because the caller owns the zones list; this only needs
    the object.
    """
    from reggie.core import globals_

    window = getattr(globals_, 'mainWindow', None)
    factory = getattr(window, 'CreateZone', None) if window is not None else None
    if not callable(factory):
        return None

    try:
        zone = factory(0, 0, id_=index + 1, add_to_scene=False)
    except Exception:
        return None

    if zone is not None and getattr(window, 'scene', None) is not None:
        try:
            window.scene.addItem(zone)
        except Exception:
            pass

    return zone


def _destroy_zone(zone):
    """
    Takes a zone the host no longer has out of the scene.

    The object itself is dropped: unlike an item removal, a zone that has gone
    from a snapshot is not held by an undo command on this peer, because remote
    work never enters the local stack.
    """
    from reggie.core import globals_

    window = getattr(globals_, 'mainWindow', None)
    if window is None or getattr(window, 'scene', None) is None:
        return

    try:
        window.scene.removeItem(zone)
    except Exception:
        pass


def _refresh_after_zone_change(zones):
    """
    Post-zone bookkeeping, mirroring ZonesSnapshotCommand._apply.

    Sprite images are anchored to zones, and the Backgrounds action is only
    meaningful when a zone exists - both go stale if a snapshot changes the zone
    set without saying so.
    """
    from reggie.core import globals_

    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        return

    area = getattr(globals_, 'Area', None)
    for sprite in getattr(area, 'sprites', []) or []:
        image = getattr(sprite, 'ImageObj', None)
        if image is not None:
            try:
                image.positionChanged()
            except Exception:
                pass

    # Through set_action_allowed, not setEnabled: Backgrounds is a Full-only
    # dialog, and this runs on the *receiving* side of a remote zone change. An
    # Editor client therefore re-enabled its own Backgrounds button every time
    # the host touched a zone - which is why it stayed available after the
    # other four sites were fixed.
    #
    # Imported inside the function, like the rest of this module's UI reach:
    # reggie/collab stays Qt-free at import time, and a test asserts it.
    try:
        from reggie.ui.collab_controller import set_action_allowed
        set_action_allowed('backgrounds', len(zones) > 0)
    except Exception:
        pass


def _clear_area_items(area=None):
    """
    Removes every item a snapshot is about to replace.

    Uses A1's own _detach_item so each item leaves the scene, the area lists and
    the side panels together - doing it by hand would strip the scene but leave
    the list widgets holding rows for items that no longer exist.

    Returns the number of items removed. Tolerates a missing main window, like
    _finish_mutation_if_possible, so this stays usable headlessly.
    """
    from reggie.core import globals_, undo

    target_area = area if area is not None else getattr(globals_, 'Area', None)
    if target_area is None:
        return 0

    window = getattr(globals_, 'mainWindow', None)
    removed = 0

    for group in _snapshot_groups(target_area):
        # _snapshot_groups already returns copies, so detaching while iterating
        # is safe even though _detach_item mutates the underlying lists.
        for item in group:
            if item is None:
                continue

            try:
                if window is not None:
                    undo._detach_item(item)
                else:
                    _detach_without_window(target_area, item)
                removed += 1
            except Exception:
                # One stubborn item must not abort the whole resync: the
                # alternative is a half-cleared level, which is worse than a
                # single leftover.
                continue

    return removed


def _detach_without_window(area, item):
    """
    Removes an item from the area lists only, for headless use.

    A1's _detach_item needs mainWindow for the scene and the side panels; when
    there is no window there is nothing to detach from but the lists.
    """
    for name in ('sprites', 'entrances', 'locations', 'comments', 'paths'):
        group = getattr(area, name, None)
        if isinstance(group, list) and item in group:
            group.remove(item)

    layers = getattr(area, 'layers', None)
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, list) and item in layer:
                layer.remove(item)


def apply_snapshot(snapshot, refmap, sprite_format=None, area=None):
    """
    Client side: replaces an area with a host snapshot.

    *Replaces*, which is the whole point: both peers normally have the same
    level file open, so the client already holds its own copy of every item. It
    previously only created, leaving the client with two of everything - one
    from its own file and one from the host - which is why a move looked like it
    cloned the item and left the original behind.

    The existing items must therefore go first. They are detached rather than
    reconciled, because the snapshot is the host's authoritative state and
    matching items up by position would guess at identities the host has already
    assigned.

    Runs inside the apply guard for the same reason as apply_remote - a snapshot
    is emphatically not a local edit, and must not land in the undo stack.
    """
    from reggie.core import undo

    if not isinstance(snapshot, dict):
        raise SyncError('a snapshot must be an object')

    items = snapshot.get('items')
    if not isinstance(items, list):
        raise SyncError('a snapshot must contain a list of items')
    if len(items) > MAX_SNAPSHOT_ITEMS:
        raise SyncError('snapshot contains too many items')

    created = []

    with undo._ApplyGuard():
        _apply_snapshot_tilesets(snapshot.get('tilesets'), area)
        _apply_snapshot_zones(snapshot.get('zones'), area)

        _clear_area_items(area)
        refmap.clear()

        for entry in items:
            description = validate_description(entry)
            ref = entry.get('ref') if isinstance(entry, dict) else None
            if not ref or not isinstance(ref, str):
                raise SyncError('every snapshot item needs a reference')

            item = create_item(description, sprite_format, area)
            refmap.bind(ref, item)
            created.append(item)

        _finish_mutation_if_possible()

    return created


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

def encode_presence_cursor(x, y, dragging=False):
    """
    `dragging` travels because the "cursors: only while moving items"
    preference describes the *sender's* activity but is applied by the
    receiver, which cannot otherwise know.
    """
    return {'kind': 'cursor', 'x': int(x), 'y': int(y),
            'dragging': bool(dragging)}


def encode_presence_click(x, y):
    return {'kind': 'click', 'x': int(x), 'y': int(y)}


def encode_presence_view(x, y, width, height):
    """
    The sender's visible rectangle in scene coordinates, for the Level
    Overview map.
    """
    return {'kind': 'view', 'x': int(x), 'y': int(y),
            'w': max(0, int(width)), 'h': max(0, int(height))}


def encode_presence_selection(refmap, items):
    refs = []
    for item in items:
        ref = refmap.ref_for(item)
        if ref is not None:
            refs.append(ref)
    return {'kind': 'selection', 'refs': refs[:512]}


def decode_presence(payload, refmap):
    """
    Turns a presence payload into something the canvas overlay can draw.

    Unknown references are dropped rather than refused: a selection that
    mentions an item we have not heard of yet is a normal race, and the rest of
    the payload is still useful.
    """
    kind = payload.get('kind')
    if kind not in ('cursor', 'click', 'selection', 'view'):
        raise SyncError('unknown presence kind %r' % (kind,))

    if kind == 'selection':
        refs = payload.get('refs') or []
        items = [refmap.item_for(ref) for ref in refs]
        return {'kind': kind, 'items': [item for item in items if item is not None]}

    decoded = {
        'kind': kind,
        'x': check_coord(payload.get('x', 0), 'x'),
        'y': check_coord(payload.get('y', 0), 'y'),
    }

    if kind == 'cursor':
        decoded['dragging'] = bool(payload.get('dragging'))
    elif kind == 'view':
        decoded['w'] = check_coord(payload.get('w', 0), 'w')
        decoded['h'] = check_coord(payload.get('h', 0), 'h')

    return decoded
