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

from reggie.collab import auth, protocol


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
                 app_version='', room_info=None,
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
        self._color_cursor = 0
        self._revision = 0

        # The host itself is a roster entry, so the UI can render one list and
        # authorize_op needs no special case for local edits.
        self.host_participant = Participant(
            session_id='host',
            nick=host_nick or 'Host',
            color=DEFAULT_NICK_COLORS[0],
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

    def _next_color(self):
        with self._lock:
            color = DEFAULT_NICK_COLORS[self._color_cursor % len(DEFAULT_NICK_COLORS)]
            self._color_cursor += 1
        return color

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

        if self.bans.contains(ip) or self.failures.is_locked(ip):
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

        if banned or not version_ok or not proof_ok:
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
            color=self._next_color(),
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

        if self.room_info:
            connection.send_type(protocol.T_ROOM_INFO, dict(self.room_info))

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
        }.get(msg_type)

        if handler is None:
            # A known type with no host-side handler yet (patch_need, file_req,
            # file_done - phase 6). Report it so nothing is silently swallowed.
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

    def system_notice(self, text):
        """
        Broadcasts a host-generated notice (joins, kicks, role changes).
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

    def _handle_snapshot_request(self, participant, message):
        # sync.py builds and sends the snapshot; this module only reports the
        # request so the owner can service it.
        self._emit('snapshot_request', {
            'participant': participant,
            'area': message['p'].get('area', 1),
        })

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
            self._emit('chat', payload)

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
