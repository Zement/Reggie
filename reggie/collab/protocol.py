"""
Wire protocol for collaboration: framing, message schemas and validation.

This module is pure logic: no sockets, no Qt, no globals. Everything here is
driven by bytes in and bytes out so it can be unit-tested headlessly.

Framing (inside the TLS stream):

    uint32 big-endian length | UTF-8 JSON body

The length is checked against MAX_FRAME_BYTES *before* any buffer is allocated,
so a hostile peer cannot make us reserve memory by lying about the size.

Envelope:

    {"v": 1, "t": "<type>", "id": "<uuid4>", "seq": <int>,
     "from": "<session_id>", "p": {...}}

Validation order (spec section 4.2), enforced by validate_message():

    version known -> type known -> required keys present with correct primitive
    types -> per-type bounds -> (caller then checks role permission)

Unknown message types and unknown extra keys are treated differently on
purpose: an unknown *type* is a protocol error the caller should count (so a
flood trips the rate limiter), while unknown extra *keys* inside a known type
are ignored, so a newer minor version can add fields without breaking older
peers.
"""

import json
import struct
import uuid


# Protocol version. Bump only for incompatible changes; additive fields do not
# need a bump (see the note about unknown keys above).
PROTOCOL_VERSION = 1

# Framing limits (spec section 5.3).
FRAME_HEADER_BYTES = 4
MAX_FRAME_BYTES = 4 * 1024 * 1024  # 4 MiB

# Field limits (spec section 5.3).
MAX_CHAT_CHARS = 500
MAX_NICK_CHARS = 32
MAX_SESSION_ID_CHARS = 64
MAX_STRING_CHARS = 4096      # generic cap for any other free-form string
MAX_LIST_ITEMS = 4096        # generic cap for any list payload
MAX_OP_TARGETS = 2048

# File transfer limits (spec section 4.4).
#
# Raised from 256 to 1024 in phase 6 after measuring the real patches in
# reggiedata/patches: NewerSMBW is 535 transferable files (~9.4 MiB) and
# NSMBWerPlus is 468, almost all small PNGs. 256 would have rejected both, which
# is exactly the growth Zement predicted when he asked to keep 256 "for now".
#
# The byte cap is the meaningful limit and stays at 64 MiB: it bounds what a peer
# can make us store, whereas the file count only bounds bookkeeping.
MAX_MANIFEST_FILES = 1024
MAX_MANIFEST_TOTAL_BYTES = 64 * 1024 * 1024  # 64 MiB
MAX_CHUNK_BYTES = 256 * 1024                 # 256 KiB of raw bytes per chunk


class ProtocolError(Exception):
    """
    Raised for anything wrong with a frame or message. The message text is safe
    to log but must never be echoed to an unauthenticated peer verbatim (it can
    describe internal expectations).
    """


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

def encode_frame(message):
    """
    Serialises a message dict to a length-prefixed frame.
    """
    try:
        body = json.dumps(message, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ProtocolError('message is not JSON-serialisable: %s' % exc)

    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError('outgoing frame too large: %d bytes' % len(body))

    return struct.pack('!I', len(body)) + body


def decode_frame_body(body):
    """
    Parses a frame body (JSON) into a dict. Does not validate the envelope;
    call validate_message() for that.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise ProtocolError('frame body must be bytes')

    try:
        text = bytes(body).decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ProtocolError('frame body is not valid UTF-8: %s' % exc)

    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise ProtocolError('frame body is not valid JSON: %s' % exc)

    if not isinstance(parsed, dict):
        raise ProtocolError('frame body must be a JSON object')

    return parsed


class FrameReader:
    """
    Incremental frame reader. Feed it whatever bytes arrive; it yields complete
    frame bodies. Enforces MAX_FRAME_BYTES before allocating anything.

    Usage:
        reader = FrameReader()
        for body in reader.feed(chunk):
            message = validate_message(decode_frame_body(body))
    """

    def __init__(self, max_frame_bytes=MAX_FRAME_BYTES):
        self.max_frame_bytes = int(max_frame_bytes)
        self._buffer = bytearray()
        self._expected = None  # payload length once the header is known

    def feed(self, data):
        """
        Adds received bytes and returns a list of complete frame bodies.
        Raises ProtocolError on an oversized frame (the caller must then
        disconnect: the stream can no longer be trusted to be in sync).
        """
        if data:
            self._buffer.extend(data)

        bodies = []
        while True:
            if self._expected is None:
                if len(self._buffer) < FRAME_HEADER_BYTES:
                    break

                (length,) = struct.unpack('!I', bytes(self._buffer[:FRAME_HEADER_BYTES]))

                # Check the advertised length BEFORE trusting or reserving it.
                if length > self.max_frame_bytes:
                    raise ProtocolError(
                        'frame length %d exceeds cap %d' % (length, self.max_frame_bytes))

                del self._buffer[:FRAME_HEADER_BYTES]
                self._expected = length

            if len(self._buffer) < self._expected:
                break

            bodies.append(bytes(self._buffer[:self._expected]))
            del self._buffer[:self._expected]
            self._expected = None

        return bodies


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

# Session / control
T_SERVER_HELLO = 'server_hello'
T_CLIENT_AUTH = 'client_auth'
T_AUTH_OK = 'auth_ok'
T_AUTH_FAILED = 'auth_failed'
T_ROSTER = 'roster'
T_ROLE_CHANGED = 'role_changed'
T_KICK = 'kick'
T_BANNED = 'banned'
T_CHAT = 'chat'
T_PING = 'ping'
T_PONG = 'pong'
T_BYE = 'bye'

# Level state
T_SNAPSHOT_REQUEST = 'snapshot_request'
T_SNAPSHOT = 'snapshot'
T_OP = 'op'
T_OP_REJECT = 'op_reject'
T_AREA_SWITCH = 'area_switch'
T_PRESENCE = 'presence'

# Patch / tileset sync
T_ROOM_INFO = 'room_info'
T_PATCH_NEED = 'patch_need'
T_MANIFEST = 'manifest'
T_FILE_REQ = 'file_req'
T_FILE_CHUNK = 'file_chunk'
T_FILE_DONE = 'file_done'

# Roles (spec section 5.1). Ordered least to most privileged.
CHAT_KIND_USER = 'user'
CHAT_KIND_SYSTEM = 'system'
CHAT_KINDS = (CHAT_KIND_USER, CHAT_KIND_SYSTEM)

ROLE_EDITOR = 'editor'
ROLE_FULL = 'full'
ROLE_HOST = 'host'
ROLES = (ROLE_EDITOR, ROLE_FULL, ROLE_HOST)

# Operation kinds, mapped from the A1 undo command classes.
OP_KINDS_EDITOR = frozenset({
    'move', 'add', 'remove', 'property', 'resize',
    'path_data', 'path_setting', 'path_order',
})
OP_KINDS_FULL_ONLY = frozenset({
    'zones', 'area_settings', 'metadata',
})
OP_KINDS = OP_KINDS_EDITOR | OP_KINDS_FULL_ONLY

# Which role may send which message type. The host is the authority and this
# table is consulted host-side; clients use it only for UX.
_CLIENT_SENDABLE = frozenset({
    T_CLIENT_AUTH, T_CHAT, T_PING, T_PONG, T_BYE,
    T_SNAPSHOT_REQUEST, T_OP, T_PRESENCE,
    T_PATCH_NEED, T_FILE_REQ, T_FILE_DONE,
})
_HOST_SENDABLE = frozenset({
    T_SERVER_HELLO, T_AUTH_OK, T_AUTH_FAILED, T_ROSTER, T_ROLE_CHANGED,
    T_KICK, T_BANNED, T_CHAT, T_PING, T_PONG, T_BYE,
    T_SNAPSHOT, T_OP, T_OP_REJECT, T_AREA_SWITCH, T_PRESENCE,
    T_ROOM_INFO, T_MANIFEST, T_FILE_CHUNK,
})

KNOWN_TYPES = _CLIENT_SENDABLE | _HOST_SENDABLE


def client_may_send(msg_type):
    """
    Whether a connected client is allowed to send this message type at all
    (independent of role; see op_allowed_for_role for per-op checks).
    """
    return msg_type in _CLIENT_SENDABLE


def host_may_send(msg_type):
    return msg_type in _HOST_SENDABLE


def op_allowed_for_role(kind, role):
    """
    Host-side authorisation for a level operation, per the spec's role matrix.
    Unknown kinds are denied (fail closed).
    """
    if kind not in OP_KINDS:
        return False
    if role == ROLE_HOST:
        return True
    if role == ROLE_FULL:
        return True  # Full may send every op kind, including dialog ops
    if role == ROLE_EDITOR:
        return kind in OP_KINDS_EDITOR
    return False


# ---------------------------------------------------------------------------
# Field validation helpers
# ---------------------------------------------------------------------------

def _require(condition, detail):
    if not condition:
        raise ProtocolError(detail)


def _get_str(payload, key, max_chars=MAX_STRING_CHARS, required=True, default=''):
    if key not in payload:
        _require(not required, 'missing string field %r' % key)
        return default

    value = payload[key]
    # bool is an int subclass but is never a valid string; reject non-str hard.
    _require(isinstance(value, str), 'field %r must be a string' % key)
    _require(len(value) <= max_chars,
             'field %r exceeds %d characters' % (key, max_chars))
    return value


def _get_int(payload, key, minimum=None, maximum=None, required=True, default=0):
    if key not in payload:
        _require(not required, 'missing integer field %r' % key)
        return default

    value = payload[key]
    # Reject bool explicitly: isinstance(True, int) is True in Python.
    _require(isinstance(value, int) and not isinstance(value, bool),
             'field %r must be an integer' % key)
    if minimum is not None:
        _require(value >= minimum, 'field %r must be >= %d' % (key, minimum))
    if maximum is not None:
        _require(value <= maximum, 'field %r must be <= %d' % (key, maximum))
    return value


def _get_bool(payload, key, required=True, default=False):
    if key not in payload:
        _require(not required, 'missing boolean field %r' % key)
        return default

    value = payload[key]
    _require(isinstance(value, bool), 'field %r must be a boolean' % key)
    return value


def _get_dict(payload, key, required=True):
    if key not in payload:
        _require(not required, 'missing object field %r' % key)
        return {}

    value = payload[key]
    _require(isinstance(value, dict), 'field %r must be an object' % key)
    return value


def _get_list(payload, key, max_items=MAX_LIST_ITEMS, required=True):
    if key not in payload:
        _require(not required, 'missing list field %r' % key)
        return []

    value = payload[key]
    _require(isinstance(value, list), 'field %r must be a list' % key)
    _require(len(value) <= max_items,
             'field %r exceeds %d items' % (key, max_items))
    return value


def sanitize_text(text, max_chars):
    """
    Strips control characters (except plain spaces) and truncates. Used for any
    peer-supplied text that will be shown in our UI: nicknames and chat.

    Removing C0/C1 controls also removes newlines and, importantly, prevents a
    peer from injecting terminal escape sequences into logs.
    """
    if not isinstance(text, str):
        return ''

    cleaned = ''.join(
        ch for ch in text
        if (ch == ' ' or (ch.isprintable() and not ch.isspace()))
    )
    return cleaned[:max_chars].strip()


def is_valid_hex(value, length=None):
    """
    Whether a string is lowercase-or-uppercase hex of an optional exact length.
    """
    if not isinstance(value, str):
        return False
    if length is not None and len(value) != length:
        return False
    if not value:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Per-type payload validators
# ---------------------------------------------------------------------------

def _v_server_hello(p):
    return {
        'nonce': _hex_field(p, 'nonce', 64),
        'protocol': _get_int(p, 'protocol', minimum=0, maximum=1 << 30),
        'app_version': _get_str(p, 'app_version', 64, required=False),
        'host_nick': sanitize_text(_get_str(p, 'host_nick', MAX_NICK_CHARS, required=False),
                                   MAX_NICK_CHARS),
        'cert_fp': _hex_field(p, 'cert_fp', 64),
    }


def _v_client_auth(p):
    return {
        'proof': _hex_field(p, 'proof', 64),
        'protocol': _get_int(p, 'protocol', minimum=0, maximum=1 << 30),
        'app_version': _get_str(p, 'app_version', 64, required=False),
        'nick': sanitize_text(_get_str(p, 'nick', MAX_NICK_CHARS, required=False),
                              MAX_NICK_CHARS),
        'game_id': _get_str(p, 'game_id', 128, required=False),
        'plugin_state_hash': _get_str(p, 'plugin_state_hash', 64, required=False),
    }


def _v_auth_ok(p):
    return {
        'session_id': _get_str(p, 'session_id', MAX_SESSION_ID_CHARS),
        'role': _role_field(p, 'role'),
        'roster': _get_list(p, 'roster', 64, required=False),
        'room_info': _get_dict(p, 'room_info', required=False),
    }


def _v_auth_failed(p):
    # Deliberately opaque: the host must not tell an unauthenticated peer
    # whether it was a bad secret, a ban, or a version mismatch.
    return {'reason': _get_str(p, 'reason', 200, required=False)}


def _v_roster(p):
    participants = _get_list(p, 'participants', 64)
    out = []
    for entry in participants:
        _require(isinstance(entry, dict), 'roster entries must be objects')
        out.append({
            'session_id': _get_str(entry, 'session_id', MAX_SESSION_ID_CHARS),
            'nick': sanitize_text(_get_str(entry, 'nick', MAX_NICK_CHARS, required=False),
                                  MAX_NICK_CHARS),
            'color': _get_str(entry, 'color', 16, required=False),
            'role': _role_field(entry, 'role'),
            'app_version_ok': _get_bool(entry, 'app_version_ok', required=False, default=True),
        })
    return {'participants': out}


def _v_role_changed(p):
    return {
        'session_id': _get_str(p, 'session_id', MAX_SESSION_ID_CHARS),
        'role': _role_field(p, 'role'),
    }


def _v_kick(p):
    return {'reason': _get_str(p, 'reason', 200, required=False)}


def _v_banned(p):
    return {'reason': _get_str(p, 'reason', 200, required=False)}


def _v_chat(p):
    text = sanitize_text(_get_str(p, 'text', MAX_CHAT_CHARS), MAX_CHAT_CHARS)
    _require(text != '', 'chat text must not be empty after sanitising')

    # 'kind' distinguishes a peer's message from a notice the host generated
    # (joins, kicks, rate-limit warnings). It is validated here but the host
    # OVERWRITES it on relay - a client claiming kind='system' must not be able
    # to render text that looks like it came from the host itself.
    kind = _get_str(p, 'kind', 16, required=False, default=CHAT_KIND_USER)
    if kind not in CHAT_KINDS:
        kind = CHAT_KIND_USER

    return {'text': text, 'kind': kind}


def _v_ping(p):
    return {'t_send': _get_int(p, 't_send', minimum=0, required=False)}


def _v_pong(p):
    return {'t_send': _get_int(p, 't_send', minimum=0, required=False)}


def _v_bye(p):
    return {'reason': _get_str(p, 'reason', 200, required=False)}


def _v_snapshot_request(p):
    return {'area': _get_int(p, 'area', minimum=1, maximum=4, required=False, default=1)}


def _v_snapshot(p):
    return {
        'area': _get_int(p, 'area', minimum=1, maximum=4),
        'rev': _get_int(p, 'rev', minimum=0),
        'state': _get_dict(p, 'state'),
    }


# Zones are the one op whose before/after is a *list* (one attribute dict per
# zone, positionally). A1's snapshot_zones() is keyed on live zone objects, which
# cannot cross a network, so only the attribute dicts travel - see
# sync.encode_zones. Rather than loosen the dict check for every other op, the
# list shape is validated explicitly here.
MAX_ZONES = 16


def _v_op(p):
    kind = _get_str(p, 'kind', 64)
    _require(kind in OP_KINDS, 'unknown op kind %r' % kind)

    common = {
        'kind': kind,
        'targets': _get_list(p, 'targets', MAX_OP_TARGETS, required=False),
        'base': _get_int(p, 'base', minimum=0, required=False),
        'text': _get_str(p, 'text', 200, required=False),
    }

    if kind == 'zones':
        before = _get_list(p, 'before', MAX_ZONES, required=False)
        after = _get_list(p, 'after', MAX_ZONES, required=False)
        for state in (before, after):
            for entry in state:
                _require(isinstance(entry, dict),
                         'each zone snapshot entry must be an object')
                _require(len(entry) <= 64, 'a zone entry has too many fields')
        common['before'] = before
        common['after'] = after
    else:
        common['before'] = _get_dict(p, 'before', required=False)
        common['after'] = _get_dict(p, 'after', required=False)

    return common


def _v_op_reject(p):
    return {
        'op_id': _get_str(p, 'op_id', 64),
        'reason': _get_str(p, 'reason', 200, required=False),
        'rev': _get_int(p, 'rev', minimum=0, required=False),
    }


def _v_area_switch(p):
    return {'area': _get_int(p, 'area', minimum=1, maximum=4)}


def _v_presence(p):
    kind = _get_str(p, 'kind', 16)
    _require(kind in ('cursor', 'click', 'selection'), 'unknown presence kind %r' % kind)
    return {
        'kind': kind,
        'x': _get_int(p, 'x', minimum=-(1 << 24), maximum=1 << 24, required=False),
        'y': _get_int(p, 'y', minimum=-(1 << 24), maximum=1 << 24, required=False),
        'refs': _get_list(p, 'refs', 512, required=False),
    }


def _v_room_info(p):
    return {
        'game_id': _get_str(p, 'game_id', 128, required=False),
        'game_name': _get_str(p, 'game_name', 200, required=False),
        'patch_id': _get_str(p, 'patch_id', 128, required=False),
        'patch_version': _get_str(p, 'patch_version', 64, required=False),
        'catalog_hash': _get_str(p, 'catalog_hash', 64, required=False),
        'in_catalog': _get_bool(p, 'in_catalog', required=False),
        'level_name': _get_str(p, 'level_name', 200, required=False),
        'area': _get_int(p, 'area', minimum=1, maximum=4, required=False, default=1),
    }


def _v_patch_need(p):
    return {
        'patch_id': _get_str(p, 'patch_id', 128, required=False),
        'reason': _get_str(p, 'reason', 200, required=False),
    }


def _v_manifest(p):
    entries = _get_list(p, 'files', MAX_MANIFEST_FILES)
    total = 0
    out = []
    for entry in entries:
        _require(isinstance(entry, dict), 'manifest entries must be objects')
        size = _get_int(entry, 'size', minimum=0, maximum=MAX_MANIFEST_TOTAL_BYTES)
        total += size
        _require(total <= MAX_MANIFEST_TOTAL_BYTES,
                 'manifest exceeds %d total bytes' % MAX_MANIFEST_TOTAL_BYTES)
        sha = _get_str(entry, 'sha256', 64)
        _require(is_valid_hex(sha, 64), 'manifest sha256 must be 64 hex characters')
        out.append({
            'path': _get_str(entry, 'path', 512),
            'size': size,
            'sha256': sha,
        })
    return {'files': out, 'patch_id': _get_str(p, 'patch_id', 128, required=False)}


def _v_file_req(p):
    return {'path': _get_str(p, 'path', 512)}


def _v_file_chunk(p):
    data = _get_str(p, 'data', MAX_CHUNK_BYTES * 2)  # base64 expands ~4/3
    total = _get_int(p, 'total', minimum=1, maximum=1 << 20)
    index = _get_int(p, 'index', minimum=0, maximum=1 << 20)
    _require(index < total, 'chunk index must be < total')
    return {
        'path': _get_str(p, 'path', 512),
        'index': index,
        'total': total,
        'data': data,
    }


def _v_file_done(p):
    return {
        'ok': _get_bool(p, 'ok', required=False, default=True),
        'error': _get_str(p, 'error', 200, required=False),
    }


def _hex_field(payload, key, length):
    value = _get_str(payload, key, length)
    _require(is_valid_hex(value, length),
             'field %r must be %d hex characters' % (key, length))
    return value


def _role_field(payload, key):
    value = _get_str(payload, key, 16)
    _require(value in ROLES, 'field %r must be one of %s' % (key, ', '.join(ROLES)))
    return value


_VALIDATORS = {
    T_SERVER_HELLO: _v_server_hello,
    T_CLIENT_AUTH: _v_client_auth,
    T_AUTH_OK: _v_auth_ok,
    T_AUTH_FAILED: _v_auth_failed,
    T_ROSTER: _v_roster,
    T_ROLE_CHANGED: _v_role_changed,
    T_KICK: _v_kick,
    T_BANNED: _v_banned,
    T_CHAT: _v_chat,
    T_PING: _v_ping,
    T_PONG: _v_pong,
    T_BYE: _v_bye,
    T_SNAPSHOT_REQUEST: _v_snapshot_request,
    T_SNAPSHOT: _v_snapshot,
    T_OP: _v_op,
    T_OP_REJECT: _v_op_reject,
    T_AREA_SWITCH: _v_area_switch,
    T_PRESENCE: _v_presence,
    T_ROOM_INFO: _v_room_info,
    T_PATCH_NEED: _v_patch_need,
    T_MANIFEST: _v_manifest,
    T_FILE_REQ: _v_file_req,
    T_FILE_CHUNK: _v_file_chunk,
    T_FILE_DONE: _v_file_done,
}


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

def make_message(msg_type, payload=None, sender='', seq=0, msg_id=None):
    """
    Builds an envelope. Does not validate; use validate_message() on receipt.
    """
    return {
        'v': PROTOCOL_VERSION,
        't': str(msg_type),
        'id': str(msg_id or uuid.uuid4().hex),
        'seq': int(seq),
        'from': str(sender),
        'p': dict(payload or {}),
    }


def validate_message(message):
    """
    Validates an envelope and its payload, returning a normalised copy whose
    payload contains only known, bounds-checked fields.

    Raises ProtocolError for anything malformed. The caller decides what to do
    (drop and count, or disconnect); this function never raises anything else,
    which is what makes it safe to call on hostile input.
    """
    if not isinstance(message, dict):
        raise ProtocolError('message must be an object')

    version = _get_int(message, 'v', minimum=0, maximum=1 << 30)
    if version != PROTOCOL_VERSION:
        raise ProtocolError('unsupported protocol version %d' % version)

    msg_type = _get_str(message, 't', 64)
    if msg_type not in KNOWN_TYPES:
        raise ProtocolError('unknown message type %r' % msg_type)

    msg_id = _get_str(message, 'id', 64, required=False)
    seq = _get_int(message, 'seq', minimum=0, maximum=1 << 62, required=False)
    sender = _get_str(message, 'from', MAX_SESSION_ID_CHARS, required=False)
    payload = _get_dict(message, 'p', required=False)

    validator = _VALIDATORS[msg_type]
    clean_payload = validator(payload)

    return {
        'v': version,
        't': msg_type,
        'id': msg_id,
        'seq': seq,
        'from': sender,
        'p': clean_payload,
    }
