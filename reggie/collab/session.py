"""
Session management: roster, roles, kick/ban, chat relay, host-side authorisation.

This is where the collaboration feature's *policy* lives. transport.py decides
whether a peer may speak at all; this module decides what a peer is allowed to
do once it can. The split matters because it means every authorisation decision
is made in one file, on the host, and can be read in one sitting.

The central rule, from the spec's invariant 4: **every authorisation decision is
made host-side.** A client also knows the role matrix, but only so it can grey
out a menu item before the user clicks it. A client that lies about its role,
patches out its own checks, or sends an op it is not entitled to send gets an
`op_reject` and nothing else. Nothing in this module trusts a client's account of
its own permissions - `authorize_op` reads the role from the host's own roster
entry, never from the incoming message.

Two things deliberately do NOT live here:

- Applying operations to the level. That is sync.py (phase 5); this module only
  says yes or no and relays.
- Anything Qt. The host session runs on transport's threads and reports through
  callbacks, so the UI layer (phase 7) marshals to the main thread.

Ban policy is worth a note, because it is weaker than it looks. Bans are keyed on
IP, which is all we have: there are no accounts, and a peer's only other
identifier is a nickname it chose itself. An IP ban stops a casual rejoin and
nothing more - a determined peer on a new address is a new peer. That is an
accepted limit of a serverless design (spec section 1.2), not an oversight, and
the UI should not imply otherwise. The real protection is that joining needs the
join code at all, and the host can rotate it.
"""

import threading
import time
import uuid

from reggie.collab import auth, debuglog, protocol


# Nickname colours assigned in order, so two peers rarely collide. Chosen to stay
# legible against both the light and dark canvas.
DEFAULT_NICK_COLORS = (
    '#e6392f',   # red
    '#2f7fe6',   # blue
    '#2fb84a',   # green
    '#e69a2f',   # orange
    '#9a4fd6',   # purple
    '#2fc4c4',   # teal
    '#d64f9a',   # pink
    '#8a8f2f',   # olive
)

# How often the host pings idle peers and reaps unresponsive ones.
PING_INTERVAL_SECONDS = 15.0
PEER_TIMEOUT_SECONDS = 60.0
_MAINTENANCE_TICK_SECONDS = 1.0

# Reasons sent to peers. Short, and safe to show verbatim in a dialog.
REASON_KICKED = 'The host removed you from the session.'
REASON_BANNED = 'The host banned you from the session.'
REASON_HOST_LEFT = 'The host ended the session.'
REASON_TIMED_OUT = 'The connection timed out.'


class Participant:
    """
    One peer in the session, as the host sees it.

    `role` here is the authoritative value. A client's own idea of its role is
    advisory; this is what authorize_op consults.
    """

    def __init__(self, session_id, nick, color, role, connection=None,
                 app_version='', app_version_ok=True, game_id=''):
        self.session_id = session_id
        self.nick = nick
        self.color = color
        self.role = role
        self.connection = connection
        self.app_version = app_version
        self.app_version_ok = bool(app_version_ok)
        self.game_id = game_id

        self.joined_at = time.monotonic()
        self.last_seen = self.joined_at
        self.latency_ms = 0.0
        self.rejected_ops = 0

    @property
    def is_host(self):
        return self.role == protocol.ROLE_HOST

    @property
    def address(self):
        if self.connection is None or not self.connection.peer_address:
            return ''
        return self.connection.peer_address[0]

    def to_roster_entry(self):
        return {
            'session_id': self.session_id,
            'nick': self.nick,
            'color': self.color,
            'role': self.role,
            'app_version_ok': self.app_version_ok,
        }

    def __repr__(self):
        return '<Participant %s %r %s>' % (self.session_id, self.nick, self.role)


class BanList:
    """
    IP bans with optional nickname labels for display.

    Kept separate from the roster so it survives a peer disconnecting, and so the
    settings UI can list and remove entries without reaching into session state.
    """

    def __init__(self):
        self._entries = {}   # ip -> {'nick', 'when'}
        self._lock = threading.RLock()

    def add(self, ip, nick=''):
        key = self._normalise(ip)
        if not key:
            return False

        with self._lock:
            self._entries[key] = {'nick': nick, 'when': time.time()}
        return True

    def remove(self, ip):
        with self._lock:
            return self._entries.pop(self._normalise(ip), None) is not None

    def contains(self, ip):
        with self._lock:
            return self._normalise(ip) in self._entries

    def entries(self):
        """
        [(ip, nick, when)], newest first - the order a settings list wants.
        """
        with self._lock:
            items = [(ip, data['nick'], data['when'])
                     for ip, data in self._entries.items()]
        return sorted(items, key=lambda row: row[2], reverse=True)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def __len__(self):
        with self._lock:
            return len(self._entries)

    @staticmethod
    def _normalise(ip):
        text = str(ip or '').strip().lower()
        # Match FailureTracker: an IPv4-mapped IPv6 peer is the same peer.
        if text.startswith('::ffff:'):
            text = text[7:]
        return text


class HostSession:
    """
    The host's view of a collaboration session.

    Owns the roster and all policy. Wire it to a ServerTransport by routing the
    transport's three callbacks here:

        transport.on_connect    -> session.handle_connect
        transport.on_message    -> session.handle_message
        transport.on_disconnect -> session.handle_disconnect

    and supply `on_event` to receive things the UI should show (joins, chat,
    role changes) and `on_op` to receive operations that have already passed
    authorisation and should now be applied locally and rebroadcast.

    Threading: called from transport's reader threads plus one maintenance
    thread. All roster mutation is under `_lock`; callbacks are invoked outside
    it so a slow or re-entrant handler cannot deadlock the session.
    """

    def __init__(self, secret, cert_fingerprint, host_nick='Host',
                 app_version='', room_info=None, host_color='',
                 on_event=None, on_op=None, on_roster_changed=None):
        self.secret = secret
        self.cert_fingerprint = cert_fingerprint
        self.app_version = app_version
        self.room_info = dict(room_info or {})

        self.on_event = on_event
        self.on_op = on_op
        self.on_roster_changed = on_roster_changed

        self.bans = BanList()
        self.failures = auth.FailureTracker()

        self._lock = threading.RLock()
        self._participants = {}        # session_id -> Participant
        self._by_connection = {}       # id(connection) -> Participant
        self._nonces = {}              # id(connection) -> nonce
        self._transfers = {}           # session_id -> offered manifest state
        self._color_cursor = 0
        self._revision = 0

        # The host itself is a roster entry, so the UI can render one list and
        # authorize_op needs no special case for local edits.
        self.host_participant = Participant(
            session_id='host',
            nick=host_nick or 'Host',
            # The host picked a colour in its own preferences too, and expects
            # to be recognised by it like anybody else.
            color=str(host_color or '').strip() or DEFAULT_NICK_COLORS[0],
            role=protocol.ROLE_HOST,
            app_version=app_version,
        )
        self._participants['host'] = self.host_participant
        self._color_cursor = 1

        self._stop = threading.Event()
        self._maintenance = None

    # -- lifecycle ----------------------------------------------------------

    def start_maintenance(self):
        """
        Starts the ping/timeout thread. Separate from __init__ so tests can drive
        maintenance manually via tick().
        """
        self._stop.clear()
        self._maintenance = threading.Thread(
            target=self._maintenance_loop, name='collab-session', daemon=True)
        self._maintenance.start()

    def shutdown(self, reason=REASON_HOST_LEFT):
        """
        Tells every peer why, then stops. Uses close_after_flush so the message
        actually lands - a peer that just sees the socket drop cannot tell an
        intentional end from a crash.
        """
        self._stop.set()

        for participant in self.clients():
            connection = participant.connection
            if connection is None:
                continue
            connection.send_type(protocol.T_BYE, {'reason': reason})
            connection.close_after_flush('session ended')

        if self._maintenance is not None:
            self._maintenance.join(2.0)
            self._maintenance = None

    # -- roster -------------------------------------------------------------

    def participants(self):
        with self._lock:
            return list(self._participants.values())

    def clients(self):
        return [p for p in self.participants() if not p.is_host]

    def find(self, session_id):
        with self._lock:
            return self._participants.get(str(session_id))

    def roster_payload(self):
        return {'participants': [p.to_roster_entry() for p in self.participants()]}

    def broadcast_roster(self):
        message = protocol.make_message(protocol.T_ROSTER, self.roster_payload())
        for participant in self.clients():
            if participant.connection is not None:
                participant.connection.send(message)

        self._notify_roster()

    def _notify_roster(self):
        if self.on_roster_changed is not None:
            try:
                self.on_roster_changed(self.participants())
            except Exception:
                pass

    def set_room_info(self, room_info):
        """
        Replaces the room info and tells every client.

        Called when the host switches game patch or loads another level. Without
        this the clients keep the room info they were handed at join time, so a
        host changing patch mid-session left everyone silently mismatched -
        which is exactly the case the patch check exists to catch.

        Returns True if anything actually changed, so the caller can avoid
        logging a change that did not happen.
        """
        new_info = dict(room_info or {})

        with self._lock:
            if new_info == self.room_info:
                return False
            self.room_info = new_info

        message = protocol.make_message(protocol.T_ROOM_INFO, dict(new_info))
        for participant in self.clients():
            if participant.connection is not None:
                participant.connection.send(message)

        self._emit('room_info', {'room_info': dict(new_info)})
        return True

    def _next_color(self):
        with self._lock:
            color = DEFAULT_NICK_COLORS[self._color_cursor % len(DEFAULT_NICK_COLORS)]
            self._color_cursor += 1
        return color

    def _pick_color(self, requested):
        """
        Honours the colour a peer chose, falling back to the next unused one.

        The peer's own choice matters: it is how that person expects to be
        recognised, in the roster and on the canvas. It is only a preference
        though - an unusable value, or one already taken by somebody else,
        falls back rather than being refused, since a colour clash is a
        cosmetic problem and rejecting a join over one would not be.
        """
        requested = str(requested or '').strip()

        # A conservative shape check rather than a colour parse: this module is
        # deliberately Qt-free, and #rrggbb is what the picker produces.
        looks_like_a_colour = (
            len(requested) == 7
            and requested.startswith('#')
            and all(c in '0123456789abcdefABCDEF' for c in requested[1:]))

        if looks_like_a_colour:
            with self._lock:
                taken = {p.color.lower() for p in self._participants.values()}
            if requested.lower() not in taken:
                return requested

        return self._next_color()

    def _unique_nick(self, requested):
        """
        Ensures nicknames are distinct, since they are how users identify each
        other on the canvas. Duplicates get a numeric suffix rather than being
        rejected - being renamed to 'Zement (2)' is friendlier than being
        refused for a reason the user cannot see.
        """
        base = (requested or '').strip() or 'Guest'

        with self._lock:
            taken = {p.nick for p in self._participants.values()}

        if base not in taken:
            return base

        for index in range(2, 100):
            candidate = '%s (%d)' % (base, index)
            if candidate not in taken:
                return candidate

        return '%s (%s)' % (base, uuid.uuid4().hex[:4])

    # -- handshake ----------------------------------------------------------

    def handle_connect(self, connection):
        """
        A TLS peer arrived. Send the nonce, or refuse if it is banned or locked
        out. Refusals are uniform: an unauthenticated peer learns only that it
        failed.
        """
        ip = connection.peer_address[0] if connection.peer_address else ''

        banned = self.bans.contains(ip)
        locked = self.failures.is_locked(ip)
        debuglog.log('host', 'peer connected', ip=ip, banned=banned,
                     locked=locked)

        if banned or locked:
            debuglog.log('host', 'REFUSED before handshake', ip=ip,
                         banned=banned, locked=locked)
            connection.send_type(protocol.T_AUTH_FAILED,
                                 {'reason': auth.GENERIC_AUTH_FAILURE})
            connection.close_after_flush('refused before handshake')
            return

        nonce = auth.generate_nonce()
        with self._lock:
            self._nonces[id(connection)] = nonce

        connection.send_type(protocol.T_SERVER_HELLO, {
            'nonce': nonce,
            'protocol': protocol.PROTOCOL_VERSION,
            'app_version': self.app_version,
            'host_nick': self.host_participant.nick,
            'cert_fp': self.cert_fingerprint,
        })

    def _handle_client_auth(self, connection, message):
        payload = message['p']
        ip = connection.peer_address[0] if connection.peer_address else ''

        with self._lock:
            nonce = self._nonces.get(id(connection), '')

        # Re-check the ban here too: a peer could have been banned between the
        # TCP accept and this frame arriving.
        banned = self.bans.contains(ip) or self.failures.is_locked(ip)

        version_ok = auth.check_version(payload['protocol'], protocol.PROTOCOL_VERSION)

        proof_ok = bool(nonce) and auth.verify_proof(
            payload['proof'], self.secret, nonce, self.cert_fingerprint)

        debuglog.log('host', 'client_auth received', ip=ip,
                     nick=payload.get('nick', ''), have_nonce=bool(nonce),
                     proof_ok=proof_ok, version_ok=version_ok, banned=banned)

        if banned or not version_ok or not proof_ok:
            debuglog.log('host', 'AUTH REJECTED', ip=ip,
                         reason=('banned' if banned else
                                 'version' if not version_ok else
                                 'no nonce' if not nonce else 'bad proof'))
            if not banned and not proof_ok:
                # Only a bad proof counts toward lockout. Counting version
                # mismatches would let an honest peer on a stale build lock
                # itself out of a session it merely cannot join yet.
                self.failures.record_failure(ip)

            connection.send_type(protocol.T_AUTH_FAILED,
                                 {'reason': auth.GENERIC_AUTH_FAILURE})
            connection.close_after_flush('authentication failed')

            self._emit('auth_failed', {
                'address': ip,
                'version_mismatch': not version_ok,
                'banned': banned,
            })
            return

        # The nonce is single-use: consume it so a replay on the same socket
        # cannot re-authenticate.
        with self._lock:
            self._nonces.pop(id(connection), None)

        self.failures.record_success(ip)
        self._admit(connection, payload)

    def _admit(self, connection, payload):
        session_id = uuid.uuid4().hex[:16]

        # An app_version mismatch is allowed but flagged: the plugin-set
        # assumption in the spec depends on matching versions, so the user is
        # told rather than silently trusted.
        peer_version = payload.get('app_version', '')
        version_ok = (not self.app_version or not peer_version
                      or peer_version == self.app_version)

        participant = Participant(
            session_id=session_id,
            nick=self._unique_nick(payload.get('nick', '')),
            color=self._pick_color(payload.get('color', '')),
            role=protocol.ROLE_EDITOR,     # least privilege by default
            connection=connection,
            app_version=peer_version,
            app_version_ok=version_ok,
            game_id=payload.get('game_id', ''),
        )

        with self._lock:
            self._participants[session_id] = participant
            self._by_connection[id(connection)] = participant

        connection.authenticated = True
        connection.session_id = session_id
        connection.role = participant.role
        connection.nick = participant.nick

        connection.send_type(protocol.T_AUTH_OK, {
            'session_id': session_id,
            'role': participant.role,
            'roster': [p.to_roster_entry() for p in self.participants()],
            'room_info': dict(self.room_info),
        })

        # No T_ROOM_INFO here: auth_ok above already carried room_info, and a
        # second copy is indistinguishable from the host *changing* the
        # settings, so every client announced a change it had not seen.

        self.broadcast_roster()
        self.system_notice('%s joined.' % participant.nick)
        self._emit('join', {'participant': participant})

    # -- message routing ----------------------------------------------------

    def handle_message(self, connection, message):
        """
        Routes one validated message from a client.

        transport.py has already checked framing, schema, direction and rate;
        what remains is role- and state-dependent policy.
        """
        msg_type = message['t']

        if msg_type == protocol.T_CLIENT_AUTH:
            if connection.authenticated:
                # Re-authenticating on a live connection is not a thing.
                connection.close('duplicate authentication')
            else:
                self._handle_client_auth(connection, message)
            return

        participant = self._participant_for(connection)
        if participant is None:
            # Authenticated at the transport level but unknown here: the roster
            # is the authority, so refuse rather than guess.
            connection.close('unknown session')
            return

        participant.last_seen = time.monotonic()

        handler = {
            protocol.T_CHAT: self._handle_chat,
            protocol.T_PING: self._handle_ping,
            protocol.T_PONG: self._handle_pong,
            protocol.T_BYE: self._handle_bye,
            protocol.T_OP: self._handle_op,
            protocol.T_PRESENCE: self._handle_presence,
            protocol.T_SNAPSHOT_REQUEST: self._handle_snapshot_request,
            protocol.T_AREA_SWITCH: self._handle_area_switch,
            protocol.T_PATCH_NEED: self._handle_patch_need,
            protocol.T_FILE_REQ: self._handle_file_req,
            protocol.T_FILE_DONE: self._handle_file_done,
        }.get(msg_type)

        if handler is None:
            # A known type the host has no handler for. Report it so nothing is
            # silently swallowed.
            self._emit('unhandled', {'type': msg_type, 'participant': participant})
            return

        handler(participant, message)

    def _participant_for(self, connection):
        with self._lock:
            return self._by_connection.get(id(connection))

    # -- authorisation ------------------------------------------------------

    def authorize_op(self, participant, kind):
        """
        The single host-side authorisation decision for level operations.

        Reads the role from the host's own roster entry, never from the message,
        and delegates to the protocol table so the matrix lives in one place.
        Unknown kinds are denied.
        """
        if participant is None:
            return False
        return protocol.op_allowed_for_role(kind, participant.role)

    def _handle_op(self, participant, message):
        payload = message['p']
        kind = payload.get('kind', '')
        op_id = message.get('id', '')

        if not self.authorize_op(participant, kind):
            participant.rejected_ops += 1
            self._reject_op(participant, op_id,
                            'Your role does not allow that change.')
            self._emit('op_denied', {'participant': participant, 'kind': kind})
            return

        with self._lock:
            self._revision += 1
            revision = self._revision

        # sync.py applies and rebroadcasts; a False return means it refused
        # (stale base, unknown item ref) and the client must revert.
        accepted = True
        if self.on_op is not None:
            try:
                accepted = self.on_op(participant, message, revision) is not False
            except Exception as exc:
                accepted = False
                self._emit('op_error', {'participant': participant, 'error': str(exc)})

        if not accepted:
            self._reject_op(participant, op_id,
                            'That change conflicted with a newer edit.', revision)

    def _reject_op(self, participant, op_id, reason, revision=0):
        if participant.connection is None:
            return
        participant.connection.send_type(protocol.T_OP_REJECT, {
            'op_id': op_id,
            'reason': reason,
            'rev': revision,
        })

    # -- chat ---------------------------------------------------------------

    def _handle_chat(self, participant, message):
        text = message['p']['text']

        # The host stamps sender and kind. A client cannot forge either, so it
        # cannot post text that renders as a system notice or as another peer.
        relay = protocol.make_message(protocol.T_CHAT, {
            'text': text,
            'kind': protocol.CHAT_KIND_USER,
        }, sender=participant.session_id)

        for other in self.clients():
            if other is not participant and other.connection is not None:
                other.connection.send(relay)

        self._emit('chat', {
            'participant': participant,
            'text': text,
            'kind': protocol.CHAT_KIND_USER,
        })

    def send_chat(self, text):
        """
        Sends a chat message as the host.
        """
        clean = protocol.sanitize_text(str(text or ''), protocol.MAX_CHAT_CHARS)
        if not clean:
            return False

        message = protocol.make_message(protocol.T_CHAT, {
            'text': clean,
            'kind': protocol.CHAT_KIND_USER,
        }, sender=self.host_participant.session_id)

        for participant in self.clients():
            if participant.connection is not None:
                participant.connection.send(message)

        self._emit('chat', {
            'participant': self.host_participant,
            'text': clean,
            'kind': protocol.CHAT_KIND_USER,
        })
        return True

    def system_notice(self, text, echo_local=False):
        """
        Broadcasts a host-generated notice (joins, kicks, role changes).

        `echo_local` is off by default because every internal caller pairs this
        with a lifecycle event ('join', 'kick', ...) that the UI already turns
        into a log line. Echoing as well put every such notice in the host's log
        twice - the duplicate messages Zement saw in the first live test. The
        clients need the wire message because they see no lifecycle event; the
        host does not.
        """
        clean = protocol.sanitize_text(str(text or ''), protocol.MAX_CHAT_CHARS)
        if not clean:
            return

        message = protocol.make_message(protocol.T_CHAT, {
            'text': clean,
            'kind': protocol.CHAT_KIND_SYSTEM,
        }, sender='')

        for participant in self.clients():
            if participant.connection is not None:
                participant.connection.send(message)

        if echo_local:
            self._emit('chat', {
                'participant': None,
                'text': clean,
                'kind': protocol.CHAT_KIND_SYSTEM,
            })

    # -- presence -----------------------------------------------------------

    def _handle_presence(self, participant, message):
        """
        Relays presence to the other peers.

        Not authorised per-role: seeing where someone's cursor is is not a
        privilege, and both send and receive rates are already capped in
        transport.py. Display preferences ("cursors: never") are a local choice
        on the receiving side and deliberately do not suppress relaying.
        """
        relay = protocol.make_message(protocol.T_PRESENCE, message['p'],
                                      sender=participant.session_id)

        for other in self.clients():
            if other is not participant and other.connection is not None:
                other.connection.send(relay)

        self._emit('presence', {'participant': participant, 'payload': message['p']})

    def broadcast_presence(self, payload):
        """
        Sends the host's own presence to every client.
        """
        message = protocol.make_message(protocol.T_PRESENCE, payload,
                                        sender=self.host_participant.session_id)
        for participant in self.clients():
            if participant.connection is not None:
                participant.connection.send(message)

    # -- liveness -----------------------------------------------------------

    def _handle_ping(self, participant, message):
        if participant.connection is not None:
            participant.connection.send_type(
                protocol.T_PONG, {'t_send': message['p'].get('t_send', 0)})

    def _handle_pong(self, participant, message):
        sent = message['p'].get('t_send', 0)
        if not sent:
            return

        # t_send is the stamp *we* put in our ping and the peer echoed back, so
        # both ends of this subtraction are our own monotonic clock in ms.
        elapsed = time.monotonic() * 1000.0 - sent

        # A pong echoing a stamp we never sent (a peer that pinged first with
        # its own clock, or a hostile value) would otherwise show an absurd
        # latency. Two monotonic clocks share no origin, so anything outside a
        # plausible round trip is discarded rather than displayed.
        if 0.0 <= elapsed <= 60000.0:
            participant.latency_ms = elapsed
            if participant.connection is not None:
                participant.connection.latency_ms = elapsed

    def _handle_bye(self, participant, message):
        reason = message['p'].get('reason', '')
        if participant.connection is not None:
            participant.connection.close_after_flush('peer said goodbye')
        self._emit('bye', {'participant': participant, 'reason': reason})

    def _handle_area_switch(self, participant, message):
        """
        A client asking to move everyone to another level or area.

        Role-checked here rather than trusted from the UI, like every other
        client request: the greyed-out controls are a convenience, and a peer
        that ignores them must still be refused. Only Full may do this, because
        it moves every participant, not just the sender.

        The host does not act on it directly - it reports it, and the owner
        decides. That keeps the "load a level" decision on the main thread with
        the editor, where it belongs.
        """
        if participant.role != protocol.ROLE_FULL:
            connection = participant.connection
            if connection is not None:
                # op_id is required by the schema; an area switch has no
                # operation id, so it names the request type instead. Omitting
                # it would fail validation on the way out and the client would
                # be refused in silence.
                connection.send_type(protocol.T_OP_REJECT, {
                    'op_id': protocol.T_AREA_SWITCH,
                    'reason': 'your access level does not allow changing the '
                              'level or area',
                })
            self._emit('op_denied', {'participant': participant,
                                     'kind': protocol.T_AREA_SWITCH})
            return

        self._emit('area_switch', {
            'participant': participant,
            'area': message['p'].get('area', 1),
            'level': message['p'].get('level', ''),
        })

    def _handle_snapshot_request(self, participant, message):
        # sync.py builds and sends the snapshot; this module only reports the
        # request so the owner can service it. `want_file` asks for the level
        # file instead, which the owner also services - the choice between the
        # two is the controller's, not this module's.
        self._emit('snapshot_request', {
            'participant': participant,
            'area': message['p'].get('area', 1),
            'want_file': bool(message['p'].get('want_file', False)),
        })

    # -- patch transfer -----------------------------------------------------
    #
    # This module decides *whether* a file may be sent and to whom; it never
    # touches the filesystem. Building the manifest and reading chunks is
    # files.py, driven by the owner (the controller), exactly as ops are applied
    # by sync.py rather than here. Two reasons: reading a patch directory from a
    # transport reader thread would block the session's own message loop, and
    # keeping policy free of I/O is what makes it testable without a disk.
    #
    # The authorisation rule is a single sentence: a participant may fetch a
    # file only if that exact path is in the manifest the host sent *to that
    # participant*. Everything else follows from it - the sprites.py exclusion
    # holds because the manifest never lists it, and a path-traversal attempt
    # cannot match a manifest entry no matter how it is spelled.

    def offered_paths(self, session_id):
        """
        The (kind, path) pairs currently offered to one participant.

        Empty when no transfer is in flight, which is the fail-closed default:
        a file_req arriving before or after a manifest matches nothing.

        Pairs rather than bare paths since Block C - B3: a transfer carries the
        patch, the Stage folder and the Texture folder, and the same relative
        name can legitimately appear in more than one of them. Authorising on
        the name alone would let a client fetch a *stage* file by asking for it
        as a *patch* file, which is the wrong file from the wrong folder.
        """
        with self._lock:
            state = self._transfers.get(session_id)
            return frozenset(state['paths']) if state else frozenset()

    def offered_patch(self, session_id):
        """
        The patch id a participant's current offer was built from, or ''.

        Needed because the host can switch patch mid-transfer. Serving a later
        request from whatever patch is loaded *now* would send files that do not
        match the manifest the client is verifying against, so it would fail on
        a hash mismatch - a corruption error for what is really a stale offer.
        The sender reads from the patch it offered, and the offer is what ends.

        Callers must NOT test this for truthiness to decide whether an offer
        exists: a retail offer is a real offer whose patch id is '', which is
        indistinguishable here from "no offer at all". Use has_offer() for that
        question. See the note there.
        """
        with self._lock:
            state = self._transfers.get(session_id)
            return state['patch_id'] if state else ''

    def has_offer(self, session_id):
        """
        Whether a participant has an offer open at all.

        Separate from offered_patch because the two questions stopped having
        the same answer at R6. A retail session's offer carries patch_id '', so
        `if not offered_patch(...)` read it as "no transfer is in progress" and
        refused every file request the client made after the host switched back
        to retail - which the client, correctly, treats as fatal and leaves
        over. Zement's live test, 2026-08-11.

        Presence, not contents: an empty patch id is data about the offer, not
        the absence of one.
        """
        with self._lock:
            return session_id in self._transfers

    def record_manifest(self, session_id, patch_id, paths, roots=None):
        """
        Records what the host is offering a participant, so later file_reqs can
        be checked against it. Called by the owner after it builds a manifest.

        `paths` may be plain names or (kind, path) pairs; a plain name is taken
        as a patch file, which is what every manifest was before Block C - B3.
        Both are normalised to pairs here, so the authorisation check has one
        shape to compare against.

        `roots` is {kind: directory}: where each section was read from when the
        manifest was built. Recorded with the offer for the same reason the
        patch id is - the host can switch patch mid-transfer, and serving the
        rest of a download from wherever it points *now* sends files that do
        not match the manifest the client is verifying against.

        That was not hypothetical. Zement switched the session to retail while
        a client was downloading Another Mario Wii, and the stage and texture
        sections - which read the host's current paths rather than the offer's
        - started resolving against retail. 'Pa1_e3setsugen.arc' exists only in
        Another Mario Wii, so the host reported it could not read its own
        offered file and the client was disconnected over it (2026-08-11).

        Replaces any previous offer for that participant: a peer gets one
        transfer at a time, and a second manifest supersedes the first rather
        than widening what the first allowed.
        """
        offered = set()
        for item in (paths or ()):
            if isinstance(item, (tuple, list)) and len(item) == 2:
                offered.add((str(item[0]), str(item[1])))
            else:
                offered.add(('patch', str(item)))

        with self._lock:
            self._transfers[session_id] = {
                'patch_id': str(patch_id or ''),
                'paths': offered,
                'roots': {str(k): str(v) for k, v in (roots or {}).items()},
                'started': time.monotonic(),
                'sent': 0,
            }

    def offered_roots(self, session_id):
        """
        The directories a participant's offer was built from, as {kind: path}.

        Empty when there is no offer, or when it was recorded without them -
        the caller falls back to the host's current paths in that case, which
        is the pre-fix behaviour and correct as long as nothing switched.
        """
        with self._lock:
            state = self._transfers.get(session_id)
            return dict(state.get('roots') or {}) if state else {}

    def clear_transfer(self, session_id):
        with self._lock:
            return self._transfers.pop(session_id, None) is not None

    def _handle_patch_need(self, participant, message):
        """
        A client saying it does not have the host's patch.

        The client names the patch it wants, and that name is checked against
        the host's own rather than used: it selects, it does not address. If it
        addressed anything, a client could ask for a manifest of a directory the
        host never offered - which is the whole class of bug the fork had in
        _GetTilesetDownloadPath.
        """
        payload = message['p']
        wanted = str(payload.get('patch_id', '') or '')
        current = str(self.room_info.get('patch_id', '') or '')
        assets_only = bool(payload.get('assets_only', False))

        # A retail session has no patch, and used to refuse here outright. That
        # is right for a request for the *patch* - there is none to send - but
        # wrong for a request for the host's game data, which retail has like
        # any other session (R6). Its Stage folder can hold edited levels, which
        # is known open 10.1 reached from the other direction.
        if not current and not assets_only:
            self._refuse_transfer(participant,
                                  'This session does not use a patch.')
            return

        if wanted and wanted != current:
            # Not an error the user needs to see; it means the client is out of
            # date about which patch the session uses, and it will re-ask when
            # the room_info it has not processed yet arrives.
            self._refuse_transfer(
                participant,
                'This session uses %s, not %s.' % (current, wanted))
            return

        # `assets_only` was read above, because the retail check needs it: a
        # client that already has the patch - from the catalog, or already on
        # disk - still needs the host's Stage and Texture, or the two peers
        # resolve the same level name to different bytes (Block C - B3, round 2).

        debuglog.log('host', 'patch_need', nick=participant.nick,
                     patch_id=current, assets_only=assets_only)

        self._emit('patch_need', {
            'participant': participant,
            'patch_id': current,
            'assets_only': assets_only,
        })

    def _handle_file_req(self, participant, message):
        """
        A client asking for one file from the manifest it was sent.
        """
        path = str(message['p'].get('path', '') or '')
        # Defaulted to the patch section, so a client that predates B3 - whose
        # requests carry no kind - still matches the offers it was sent.
        kind = str(message['p'].get('kind', '') or 'patch')
        offered = self.offered_paths(participant.session_id)

        if (kind, path) not in offered:
            # Counted like a rejected op, so a peer probing for files shows up
            # in the roster rather than only in a log nobody reads.
            participant.rejected_ops += 1
            debuglog.log('host', 'file_req REFUSED', nick=participant.nick,
                         path=path, kind=kind, offered=len(offered))
            self._refuse_transfer(
                participant,
                'That file was not offered.' if offered else
                'No transfer is in progress.')
            self._emit('file_denied', {'participant': participant, 'path': path,
                                       'kind': kind})
            return

        with self._lock:
            state = self._transfers.get(participant.session_id)
            if state is not None:
                state['sent'] += 1

        self._emit('file_req', {'participant': participant, 'path': path,
                                'kind': kind})

    def _handle_file_done(self, participant, message):
        payload = message['p']
        ok = bool(payload.get('ok', True))
        error = str(payload.get('error', '') or '')
        level = str(payload.get('level', '') or '')

        if level:
            # A published level was loaded, not a patch downloaded (R3). The
            # peer has no transfer to clear, and clearing one anyway would
            # release an authorisation it is still fetching against - the same
            # class of bug as the duplicate patch_need.
            debuglog.log('host', 'level loaded', nick=participant.nick,
                         level=level, ok=ok)
            self._emit('level_loaded', {
                'participant': participant,
                'level': level,
                'ok': ok,
                'error': error,
            })
            return

        self.clear_transfer(participant.session_id)
        debuglog.log('host', 'file_done', nick=participant.nick, ok=ok,
                     error=error)

        self._emit('file_done', {
            'participant': participant,
            'ok': ok,
            'error': error,
        })

    def _refuse_transfer(self, participant, reason):
        """
        Ends a transfer attempt with a reason the client can show.

        Uses T_FILE_DONE rather than a bespoke type because that is already the
        "this transfer is over" message in both directions, and a client that
        has to handle one terminator instead of two cannot forget the second.
        """
        connection = participant.connection
        if connection is None:
            return
        connection.send_type(protocol.T_FILE_DONE, {'ok': False, 'error': reason})

    # -- host actions -------------------------------------------------------

    def set_role(self, session_id, role):
        """
        Changes a peer's role. Host-only by construction: nothing routes a
        client message here.
        """
        if role not in (protocol.ROLE_EDITOR, protocol.ROLE_FULL):
            return False

        participant = self.find(session_id)
        if participant is None or participant.is_host:
            return False

        if participant.role == role:
            return True

        participant.role = role
        if participant.connection is not None:
            participant.connection.role = role
            participant.connection.send_type(protocol.T_ROLE_CHANGED, {
                'session_id': session_id,
                'role': role,
            })

        self.broadcast_roster()
        self.system_notice('%s is now %s.' % (
            participant.nick,
            'a full editor' if role == protocol.ROLE_FULL else 'a canvas editor'))
        self._emit('role_changed', {'participant': participant, 'role': role})
        return True

    def kick(self, session_id, reason=REASON_KICKED):
        """
        Removes a peer. It may reconnect - use ban() to prevent that.
        """
        participant = self.find(session_id)
        if participant is None or participant.is_host:
            return False

        if participant.connection is not None:
            participant.connection.send_type(protocol.T_KICK, {'reason': reason})
            participant.connection.close_after_flush('kicked')

        self._remove(participant)
        self.system_notice('%s was removed from the session.' % participant.nick)
        self._emit('kick', {'participant': participant, 'reason': reason})
        return True

    def ban(self, session_id, reason=REASON_BANNED):
        """
        Bans a peer's IP and disconnects it.

        See the module docstring on how limited an IP ban is. Returns False if
        the peer has no usable address, so the UI can say the ban did not take
        rather than showing a ban that does nothing.
        """
        participant = self.find(session_id)
        if participant is None or participant.is_host:
            return False

        address = participant.address
        if not address:
            return False

        self.bans.add(address, participant.nick)

        if participant.connection is not None:
            participant.connection.send_type(protocol.T_BANNED, {'reason': reason})
            participant.connection.close_after_flush('banned')

        self._remove(participant)
        self.system_notice('%s was banned from the session.' % participant.nick)
        self._emit('ban', {'participant': participant, 'address': address})
        return True

    def unban(self, ip):
        return self.bans.remove(ip)

    # -- disconnect ---------------------------------------------------------

    def handle_disconnect(self, connection, reason):
        participant = self._participant_for(connection)

        with self._lock:
            self._nonces.pop(id(connection), None)

        if participant is None:
            return

        self._remove(participant)
        self.system_notice('%s left.' % participant.nick)
        self._emit('leave', {'participant': participant, 'reason': reason})

    def _remove(self, participant):
        with self._lock:
            self._participants.pop(participant.session_id, None)
            # A dropped peer's offer dies with it. Leaving it would let a
            # rejoining peer inherit an offer it never consented to, and session
            # ids are fresh per join so the entry could never be reclaimed.
            self._transfers.pop(participant.session_id, None)
            if participant.connection is not None:
                self._by_connection.pop(id(participant.connection), None)

        self.broadcast_roster()

    # -- maintenance --------------------------------------------------------

    def tick(self, now=None):
        """
        One maintenance pass: ping idle peers, drop unresponsive ones.

        Public and time-injectable so tests can exercise the timeout without
        waiting a real minute.
        """
        current = time.monotonic() if now is None else now

        for participant in self.clients():
            connection = participant.connection
            if connection is None:
                continue

            idle = current - participant.last_seen

            if idle > PEER_TIMEOUT_SECONDS:
                connection.send_type(protocol.T_BYE, {'reason': REASON_TIMED_OUT})
                connection.close_after_flush('timed out')
                self._remove(participant)
                self.system_notice('%s timed out.' % participant.nick)
                self._emit('timeout', {'participant': participant})
                continue

            if idle > PING_INTERVAL_SECONDS:
                connection.send_type(protocol.T_PING,
                                     {'t_send': int(current * 1000.0)})

    def _maintenance_loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # A maintenance failure must not kill liveness checking for the
                # rest of the session.
                pass
            self._stop.wait(_MAINTENANCE_TICK_SECONDS)

    # -- events -------------------------------------------------------------

    def _emit(self, kind, data):
        if self.on_event is None:
            return
        try:
            self.on_event(kind, data)
        except Exception:
            # UI handlers must never be able to break session handling.
            pass


class ClientSession:
    """
    The client's view: its own role, the roster, and chat history.

    Deliberately thin. The client mirrors the role matrix only to grey out menu
    items before the user clicks - `may_send_op` is a UX helper, and the comment
    on it says so, because a future reader must not mistake it for enforcement.
    The host re-checks everything.
    """

    def __init__(self, nick='Guest', on_event=None):
        self.nick = nick
        self.on_event = on_event

        self.session_id = ''
        self.role = protocol.ROLE_EDITOR
        self.participants = []      # roster entries as dicts
        self.room_info = {}
        self.connected = False
        self.close_reason = ''
        self.rejected = False

    def nick_for(self, session_id):
        """
        The nickname of a roster entry, or '' if it is not one we know.

        The roster is the only place a client learns who anyone is: chat and
        presence messages identify their sender by session id alone.
        """
        if not session_id:
            return ''

        for entry in self.participants:
            if entry.get('session_id') == session_id:
                return entry.get('nick', '') or ''

        return ''

    def handle_message(self, connection, message):
        """
        Applies a host message to local state. Returns the message type handled,
        so a caller can chain its own behaviour.
        """
        msg_type = message['t']
        payload = message['p']

        if msg_type == protocol.T_AUTH_OK:
            self.session_id = payload['session_id']
            self.role = payload['role']
            self.participants = list(payload.get('roster') or [])
            self.room_info = dict(payload.get('room_info') or {})
            self.connected = True
            connection.authenticated = True
            self._emit('connected', payload)

        elif msg_type == protocol.T_AUTH_FAILED:
            self.rejected = True
            self.close_reason = payload.get('reason', '')
            self._emit('rejected', payload)

        elif msg_type == protocol.T_ROSTER:
            self.participants = list(payload['participants'])
            self._emit('roster', payload)

        elif msg_type == protocol.T_ROLE_CHANGED:
            if payload['session_id'] == self.session_id:
                self.role = payload['role']
            self._emit('role_changed', payload)

        elif msg_type == protocol.T_ROOM_INFO:
            self.room_info = dict(payload)
            self._emit('room_info', payload)

        elif msg_type == protocol.T_CHAT:
            # The sender's id lives on the envelope, not in the payload, so
            # emitting the payload alone dropped it and the client had no way
            # to name who was speaking - every remote line, the host's
            # included, rendered without a nickname (Mone; reported by Zement
            # 2026-08-28). Resolved against the roster here, where the roster
            # actually lives.
            sender_id = str(message.get('from', '') or '')
            enriched = dict(payload)
            enriched['session_id'] = sender_id
            enriched['nick'] = self.nick_for(sender_id)
            self._emit('chat', enriched)

        elif msg_type in (protocol.T_KICK, protocol.T_BANNED):
            self.close_reason = payload.get('reason', '')
            self._emit('removed', {'type': msg_type, 'reason': self.close_reason})

        elif msg_type == protocol.T_BYE:
            self.close_reason = payload.get('reason', '')
            self._emit('bye', payload)

        elif msg_type == protocol.T_PING:
            connection.send_type(protocol.T_PONG,
                                 {'t_send': payload.get('t_send', 0)})

        elif msg_type == protocol.T_OP_REJECT:
            self._emit('op_reject', payload)

        elif msg_type == protocol.T_MANIFEST:
            # Named explicitly rather than left to the generic branch below,
            # because the three transfer messages have to arrive under stable
            # event names for the controller to drive a transfer at all. The
            # generic branch would emit them under their wire type, which works
            # by coincidence and breaks the moment a type is renamed.
            self._emit('manifest', payload)

        elif msg_type == protocol.T_FILE_CHUNK:
            self._emit('file_chunk', payload)

        elif msg_type == protocol.T_FILE_DONE:
            # The host also uses file_done to refuse a transfer, so this is not
            # only the success path.
            self._emit('file_done', payload)

        elif msg_type == protocol.T_SAVED:
            # The host saved the session's level; its bytes follow as ordinary
            # file_chunks. Named explicitly for the same reason as the transfer
            # messages above: the controller needs a stable event name.
            self._emit('saved', payload)

        elif msg_type == protocol.T_PRESENCE:
            # Presence needs its sender, and the generic branch below drops it:
            # the host relays every peer's presence through one connection, so
            # without 'from' a client cannot tell two peers apart and draws
            # them all as one cursor. It is carried alongside the payload
            # rather than merged into it, so a peer cannot claim to be someone
            # else by putting a 'from' in its own payload.
            self._emit('presence', {
                'payload': payload,
                'sender': str(message.get('from', '') or ''),
            })

        else:
            self._emit(msg_type, payload)

        return msg_type

    def may_send_op(self, kind):
        """
        UX ONLY. Mirrors the role matrix so the UI can disable a control before
        the user clicks it. This is not enforcement: the host re-checks every op
        in HostSession.authorize_op, and a client that bypasses this simply gets
        an op_reject.
        """
        return protocol.op_allowed_for_role(kind, self.role)

    def participant_by_id(self, session_id):
        for entry in self.participants:
            if entry.get('session_id') == session_id:
                return entry
        return None

    def _emit(self, kind, data):
        if self.on_event is None:
            return
        try:
            self.on_event(kind, data)
        except Exception:
            pass
