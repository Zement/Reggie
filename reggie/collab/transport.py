"""
TLS transport: server, client, framed connections and rate limiters.

This module owns sockets and threads and nothing else. It deliberately knows
nothing about rosters, roles, level operations or Qt:

- It hands complete, schema-validated messages to a callback.
- It enforces the *transport-level* limits from spec section 5.3 (frame size,
  handshake timeout, concurrent unauthenticated sockets, per-peer message
  rates).
- It refuses to deliver anything before the handshake has completed.

Everything role- and content-related belongs to session.py (phase 4). Keeping
that split is what lets the authorisation decisions live in exactly one place.

Threading model, chosen for predictability over cleverness:

    ServerTransport   1 accept thread + 1 reader thread per connection
    ClientTransport   1 reader thread
    Connection        1 writer thread draining a bounded queue

A bounded send queue matters: without it, a peer that stops reading would make
us buffer without limit until the process dies. When the queue is full we drop
the connection rather than grow, which is the same policy as exceeding a rate
limit.

Callbacks are invoked from reader threads. The UI layer (phase 7) must marshal
them onto the Qt main thread; this module never touches Qt so it stays testable
headlessly over a real loopback TLS socket.

Security notes specific to this file:

- The client verifies the certificate fingerprint against the pin from the join
  code *itself*, with `check_hostname=False` and `verify_mode=CERT_NONE`. That
  looks alarming out of context, so to be explicit: standard CA validation is
  meaningless for a self-signed peer identified by IP, and turning it off
  without a replacement would be the real bug. The pin check in
  `_verify_pinned_certificate` is that replacement, it runs before a single
  application byte is exchanged, and a failure closes the socket.
- TLS 1.2 is the floor and 1.3 is negotiated when both ends support it. We do
  not require 1.3 outright only because it would break on older OpenSSL builds;
  the pin, not the version, is what carries the identity guarantee.
- Handshake data is read under a timeout with a byte budget, so an unauthenticated
  peer cannot hold a slot open or stream us unbounded data before authenticating.
"""

import os
import queue
import socket
import ssl
import threading
import time

from reggie.collab import debuglog, protocol
from reggie.collab.identity import (
    DEFAULT_HOST_PORT,
    fingerprint_from_der,
    fingerprint_matches_pin,
)


# Transport limits (spec section 5.3).
HANDSHAKE_TIMEOUT_SECONDS = 10.0
MAX_UNAUTHENTICATED_SOCKETS = 8
MAX_PEERS = 8

# Bytes an unauthenticated peer may send before it is cut off. Generous next to
# a handshake (a few hundred bytes) and tiny next to a memory problem.
MAX_HANDSHAKE_BYTES = 64 * 1024

# Outbound queue depth per connection. A snapshot burst plus chunks fits; a peer
# that has stopped reading does not.
SEND_QUEUE_DEPTH = 512

# Per-peer message rates (spec section 5.3).
OPS_PER_SECOND = 100.0
OPS_BURST = 300.0
CHAT_PER_SECOND = 5.0
CHAT_BURST = 10.0
PRESENCE_PER_SECOND = 40.0     # receive-side cap; send side coalesces to 20/s
PRESENCE_BURST = 80.0
CONTROL_PER_SECOND = 20.0
CONTROL_BURST = 60.0

# Liveness.
PING_INTERVAL_SECONDS = 15.0
PEER_TIMEOUT_SECONDS = 60.0

# How long a reader blocks before re-checking the stop flag.
_READ_TIMEOUT_SECONDS = 0.5


class TransportError(Exception):
    """
    Raised for connection setup failures. Messages are user-facing.
    """


class PinMismatch(TransportError):
    """
    The host's certificate did not match the fingerprint in the join code.

    This is the MITM signal and must never be presented as a routine network
    error: it means something answered on the host's behalf.
    """


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    Standard token bucket: `rate` tokens/second, capped at `burst`.

    Chosen over a fixed window because level editing is naturally bursty - a
    drag releases a batch of ops at once - and a fixed window would reject the
    tail of a legitimate burst that a bucket absorbs.
    """

    def __init__(self, rate, burst, clock=time.monotonic):
        self.rate = float(rate)
        self.burst = float(burst)
        self._clock = clock
        self._tokens = float(burst)
        self._last = clock()

    def consume(self, count=1):
        """
        Takes `count` tokens if available. Returns True if allowed.
        """
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now

        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)

        if self._tokens >= count:
            self._tokens -= count
            return True

        return False

    @property
    def tokens(self):
        return self._tokens


class MessageRateLimiter:
    """
    Per-peer rate limiting by message class, with the spec's two-strike policy:
    the first violation warns, the second disconnects.

    Grouping by class rather than per-type keeps chat flooding from eating an
    editing budget and vice versa.
    """

    def __init__(self, clock=time.monotonic):
        self._buckets = {
            'op': TokenBucket(OPS_PER_SECOND, OPS_BURST, clock),
            'chat': TokenBucket(CHAT_PER_SECOND, CHAT_BURST, clock),
            'presence': TokenBucket(PRESENCE_PER_SECOND, PRESENCE_BURST, clock),
            'control': TokenBucket(CONTROL_PER_SECOND, CONTROL_BURST, clock),
        }
        self.warnings = 0

    @staticmethod
    def classify(msg_type):
        if msg_type == protocol.T_OP:
            return 'op'
        if msg_type == protocol.T_CHAT:
            return 'chat'
        if msg_type == protocol.T_PRESENCE:
            return 'presence'
        return 'control'

    def check(self, msg_type):
        """
        Returns 'ok', 'warn' or 'disconnect'.
        """
        bucket = self._buckets[self.classify(msg_type)]

        if bucket.consume():
            return 'ok'

        self.warnings += 1
        return 'warn' if self.warnings == 1 else 'disconnect'


class PresenceCoalescer:
    """
    Send-side presence throttle: at most `rate` updates per second, keeping only
    the newest pending position.

    Coalescing rather than dropping is what makes a cursor look smooth on the
    far end - the last known position is always the one that gets sent.
    """

    # Repeated float addition makes an exact interval comparison unreliable:
    # advancing a clock by 0.05 twenty times does not land on 1.0. Without this
    # tolerance a cursor update can be held for a whole extra interval, which is
    # visible as stutter.
    _EPSILON = 1e-9

    def __init__(self, rate=20.0, clock=time.monotonic):
        self.interval = 1.0 / float(rate)
        self._clock = clock
        # None, not 0.0: the first offer must always send, and a clock whose
        # origin is not zero (time.monotonic, or an injected test clock) would
        # otherwise make the comparison meaningless.
        self._last_sent = None
        self._pending = None

    def _due(self, now):
        return (self._last_sent is None
                or now - self._last_sent >= self.interval - self._EPSILON)

    def offer(self, payload):
        """
        Submits a presence payload. Returns the payload to send now, or None if
        it should be held.
        """
        self._pending = payload
        now = self._clock()

        if self._due(now):
            self._last_sent = now
            out, self._pending = self._pending, None
            return out

        return None

    def flush(self):
        """
        Returns a held payload once the interval has elapsed, else None. Call
        from a timer so a final cursor position is never left stranded.
        """
        if self._pending is None:
            return None

        now = self._clock()
        if not self._due(now):
            return None

        self._last_sent = now
        out, self._pending = self._pending, None
        return out


# ---------------------------------------------------------------------------
# TLS contexts
# ---------------------------------------------------------------------------

def make_server_context(cert_path, key_path):
    """
    Server-side TLS context for the host's self-signed certificate.

    No client certificates: clients authenticate with the HMAC proof over the
    room secret, which is the mechanism the user actually controls.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_NONE

    try:
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    except (ssl.SSLError, OSError) as exc:
        raise TransportError('Could not load the collaboration certificate: %s' % exc)

    return context


def make_client_context():
    """
    Client-side TLS context for a pinned self-signed peer.

    `check_hostname` and CA verification are off *because* we pin: see the
    module docstring. `_verify_pinned_certificate` supplies the identity check.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _verify_pinned_certificate(tls_socket, pin):
    """
    Compares the peer certificate's SHA-256 against the join code's pin.

    Returns the full fingerprint (needed as the scrypt salt), or raises
    PinMismatch. Called immediately after the handshake, before any application
    data is read or written.
    """
    der = tls_socket.getpeercert(binary_form=True)
    if not der:
        raise PinMismatch('The host did not present a certificate.')

    fingerprint = fingerprint_from_der(der)

    if not fingerprint_matches_pin(fingerprint, pin):
        raise PinMismatch(
            'The host\'s identity does not match the join code. Someone may be '
            'intercepting the connection, or the host regenerated its '
            'certificate - ask for a fresh join code.'
        )

    return fingerprint


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class Connection:
    """
    One framed, message-oriented TLS connection.

    Owns a reader thread (decoding frames, validating messages, rate limiting)
    and a writer thread (draining a bounded queue). Both stop when `close()` is
    called or either side fails; `on_closed` fires exactly once.

    `authenticated` gates delivery: until the owner sets it, only handshake
    types are accepted, and the byte budget applies.
    """

    def __init__(self, sock, peer_address, is_server_side,
                 on_message=None, on_closed=None, name=''):
        self._socket = sock
        self.peer_address = peer_address
        self.is_server_side = bool(is_server_side)
        self.name = name or (peer_address[0] if peer_address else '?')

        self.on_message = on_message
        self.on_closed = on_closed

        self.session_id = ''
        self.role = ''
        self.nick = ''
        self.authenticated = False
        self.cert_fingerprint = ''

        self.connected_at = time.monotonic()
        self.last_received_at = self.connected_at
        self.latency_ms = 0.0

        self._reader = protocol.FrameReader()
        self._limiter = MessageRateLimiter()
        self._send_queue = queue.Queue(maxsize=SEND_QUEUE_DEPTH)
        self._stop = threading.Event()
        self._closed_once = threading.Event()
        self._close_lock = threading.Lock()
        self._close_reason = ''
        self._handshake_bytes = 0
        self._threads = []

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        for target, suffix in ((self._read_loop, 'reader'), (self._write_loop, 'writer')):
            thread = threading.Thread(
                target=target,
                name='collab-%s-%s' % (suffix, self.name),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def close_after_flush(self, reason='', timeout=2.0):
        """
        Sends everything already queued, then closes.

        Needed because several protocol steps are "send a reason, then hang up"
        - auth_failed, kick, banned, bye. A plain close() races the writer
        thread and the peer would see an unexplained disconnect instead of the
        reason, which is the difference between "wrong join code" and "the
        network broke" in the UI.

        Bounded: a peer that will not read cannot delay our shutdown past
        `timeout`.
        """
        if self._stop.is_set():
            return

        deadline = time.monotonic() + float(timeout)
        while not self._send_queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)

        # The queue being empty means the writer has taken the frame, not
        # necessarily that sendall() has returned; give it a moment to finish.
        time.sleep(0.05)

        self.close(reason)

    def close(self, reason=''):
        """
        Idempotent. Safe to call from any thread, including a reader callback.

        Closes immediately, discarding anything still queued. Use
        close_after_flush() when the peer needs to receive a final message.
        """
        if self._stop.is_set():
            return

        self._close_reason = reason or self._close_reason
        self._stop.set()

        debuglog.log('conn', 'closing', peer=self.peer_address,
                     reason=self._close_reason,
                     authenticated=getattr(self, 'authenticated', False),
                     nick=getattr(self, 'nick', ''))

        # Report the closure before tearing the socket down. The reader and
        # writer threads both call _fire_closed() from their finally blocks, and
        # closing the socket is what wakes them - so tearing down first would let
        # a thread fire the callback with an empty reason and win the
        # _closed_once race, losing the real cause. Observers would then see a
        # peer vanish from connections() with no explanation.
        self._fire_closed()

        # Unblock the writer, which is parked on queue.get().
        try:
            self._send_queue.put_nowait(None)
        except queue.Full:
            pass

        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Already dead, or never fully connected. Either way, closing next
            # is what matters.
            pass

        try:
            self._socket.close()
        except OSError:
            pass

    def _fire_closed(self):
        """
        Invokes on_closed exactly once, whichever thread gets here first.
        """
        with self._close_lock:
            if self._closed_once.is_set():
                return
            self._closed_once.set()

        if self.on_closed is not None:
            try:
                self.on_closed(self, self._close_reason)
            except Exception:
                # A faulty callback must not leave the connection half-torn-down.
                pass

    @property
    def is_open(self):
        return not self._stop.is_set()

    @property
    def close_reason(self):
        return self._close_reason

    def join(self, timeout=2.0):
        """
        Waits for the reader and writer threads to finish. Tests use this to
        assert a clean shutdown.
        """
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)

    # -- sending ------------------------------------------------------------

    def send(self, message):
        """
        Queues a message. Returns False if the connection is closing or the
        queue is full (which closes the connection: a peer that will not read
        is not a peer we can buffer for).
        """
        if self._stop.is_set():
            return False

        try:
            frame = protocol.encode_frame(message)
        except protocol.ProtocolError:
            # Our own bug, not the peer's. Drop rather than kill the session.
            return False

        try:
            self._send_queue.put_nowait(frame)
            return True
        except queue.Full:
            self.close('send queue overflow')
            return False

    def send_type(self, msg_type, payload=None, sender='', seq=0):
        return self.send(protocol.make_message(msg_type, payload, sender=sender, seq=seq))

    def _write_loop(self):
        try:
            while not self._stop.is_set():
                try:
                    frame = self._send_queue.get(timeout=_READ_TIMEOUT_SECONDS)
                except queue.Empty:
                    continue

                if frame is None:          # close sentinel
                    break

                try:
                    self._socket.sendall(frame)
                except (OSError, ssl.SSLError) as exc:
                    self.close('write failed: %s' % exc)
                    break
        finally:
            self._fire_closed()

    # -- receiving ----------------------------------------------------------

    def _read_loop(self):
        try:
            while not self._stop.is_set():
                try:
                    chunk = self._socket.recv(65536)
                except socket.timeout:
                    if self._handshake_expired():
                        self.close('handshake timed out')
                        break
                    continue
                except (OSError, ssl.SSLError) as exc:
                    self.close('read failed: %s' % exc)
                    break

                if not chunk:
                    self.close('peer disconnected')
                    break

                if not self.authenticated:
                    self._handshake_bytes += len(chunk)
                    if self._handshake_bytes > MAX_HANDSHAKE_BYTES:
                        self.close('too much data before authentication')
                        break

                if not self._consume(chunk):
                    break

                self.last_received_at = time.monotonic()
        finally:
            self._fire_closed()

    def _handshake_expired(self):
        return (not self.authenticated
                and time.monotonic() - self.connected_at > HANDSHAKE_TIMEOUT_SECONDS)

    def _consume(self, chunk):
        """
        Feeds bytes through framing, validation and rate limiting, dispatching
        each accepted message. Returns False if the connection was closed.
        """
        try:
            bodies = self._reader.feed(chunk)
        except protocol.ProtocolError as exc:
            # Oversized frame: the stream is no longer trustworthy, since we
            # cannot know where the next frame starts.
            self.close('framing error: %s' % exc)
            return False

        for body in bodies:
            try:
                message = protocol.validate_message(protocol.decode_frame_body(body))
            except protocol.ProtocolError:
                # Malformed or unknown: drop, but charge it against the rate
                # limit so a flood of junk still trips the limiter.
                verdict = self._limiter.check('')
                if verdict == 'disconnect':
                    self.close('too many invalid messages')
                    return False
                continue

            msg_type = message['t']

            if not self._direction_allowed(msg_type):
                self.close('message type %r not allowed from this peer' % msg_type)
                return False

            if not self.authenticated and not self._handshake_allowed(msg_type):
                self.close('message type %r before authentication' % msg_type)
                return False

            verdict = self._limiter.check(msg_type)
            if verdict == 'disconnect':
                self.close('rate limit exceeded')
                return False
            if verdict == 'warn':
                self.send_type(protocol.T_CHAT, {
                    'text': 'You are sending messages too quickly; slow down.',
                    'kind': 'system',
                })
                continue

            if self.on_message is not None:
                try:
                    self.on_message(self, message)
                except Exception as exc:
                    # A handler bug must not silently wedge the reader.
                    self.close('handler error: %s' % exc)
                    return False

            if self._stop.is_set():
                return False

        return True

    def _direction_allowed(self, msg_type):
        """
        A host never accepts host-only types, and a client never accepts
        client-only types. Cheap, and it removes a whole class of confusion
        attack (a client claiming to be the sequencer, say).
        """
        if self.is_server_side:
            return protocol.client_may_send(msg_type)
        return protocol.host_may_send(msg_type)

    @staticmethod
    def _handshake_allowed(msg_type):
        return msg_type in (
            protocol.T_SERVER_HELLO,
            protocol.T_CLIENT_AUTH,
            protocol.T_AUTH_OK,
            protocol.T_AUTH_FAILED,
            protocol.T_BYE,
        )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ServerTransport:
    """
    Accepts TLS connections and hands each one to the owner as a Connection.

    Enforces the two admission limits before any TLS work happens - concurrent
    unauthenticated sockets and total peers - so a flood costs us an accept and
    a close, not a handshake.

    Callbacks (all from the accept or reader threads):
        on_connect(connection)              a TLS peer arrived, not yet authed
        on_message(connection, message)     validated message
        on_disconnect(connection, reason)
    """

    def __init__(self, cert_path, key_path, port=DEFAULT_HOST_PORT, bind_host='',
                 max_peers=MAX_PEERS,
                 on_connect=None, on_message=None, on_disconnect=None):
        self.cert_path = cert_path
        self.key_path = key_path
        self.port = int(port)
        self.bind_host = bind_host
        self.max_peers = int(max_peers)

        self.on_connect = on_connect
        self.on_message = on_message
        self.on_disconnect = on_disconnect

        self._context = None
        self._listener = None
        self._accept_thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._connections = []

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        """
        Binds, listens and starts accepting. Raises TransportError with a
        user-facing message on failure (port in use is the common one).
        """
        self._context = make_server_context(self.cert_path, self.key_path)

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # No SO_REUSEADDR on Windows: there it implies SO_REUSEPORT semantics
        # and would let a second process silently steal the port.
        if os.name != 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            listener.bind((self.bind_host, self.port))
            listener.listen(16)
        except OSError as exc:
            listener.close()
            raise TransportError(
                'Could not listen on port %d: %s' % (self.port, exc))

        listener.settimeout(_READ_TIMEOUT_SECONDS)
        self._listener = listener

        # Port 0 means "any free port"; report the real one.
        self.port = listener.getsockname()[1]

        self._accept_thread = threading.Thread(
            target=self._accept_loop, name='collab-accept', daemon=True)
        self._accept_thread.start()

    def stop(self, reason='host closed the session'):
        self._stop.set()

        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass

        for connection in self.connections():
            connection.close(reason)

        if self._accept_thread is not None:
            self._accept_thread.join(2.0)

    # -- state --------------------------------------------------------------

    def connections(self):
        with self._lock:
            return list(self._connections)

    def authenticated_connections(self):
        return [c for c in self.connections() if c.authenticated]

    def _unauthenticated_count(self):
        return sum(1 for c in self.connections() if not c.authenticated)

    def broadcast(self, message, exclude=None):
        """
        Sends to every authenticated peer, optionally skipping one.
        """
        for connection in self.authenticated_connections():
            if connection is not exclude:
                connection.send(message)

    # -- accepting ----------------------------------------------------------

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                raw, address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break   # listener closed

            if self._stop.is_set():
                self._discard(raw)
                break

            # Admission control before TLS: rejecting early is what keeps a
            # flood cheap for us and expensive for the attacker.
            if self._unauthenticated_count() >= MAX_UNAUTHENTICATED_SOCKETS:
                self._discard(raw)
                continue

            if len(self.authenticated_connections()) >= self.max_peers:
                self._discard(raw)
                continue

            threading.Thread(
                target=self._handshake,
                args=(raw, address),
                name='collab-tls-%s' % (address[0] if address else '?'),
                daemon=True,
            ).start()

    @staticmethod
    def _discard(raw):
        try:
            raw.close()
        except OSError:
            pass

    def _handshake(self, raw, address):
        """
        Wraps an accepted socket in TLS on its own thread, so a stalled or
        hostile handshake cannot block the accept loop.
        """
        raw.settimeout(HANDSHAKE_TIMEOUT_SECONDS)

        try:
            tls = self._context.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            # Port scan, wrong protocol, or a client that gave up. Not
            # noteworthy: a listening port gets this routinely.
            self._discard(raw)
            return

        tls.settimeout(_READ_TIMEOUT_SECONDS)

        connection = Connection(
            tls, address, is_server_side=True,
            on_message=self.on_message,
            on_closed=self._handle_closed,
        )

        with self._lock:
            self._connections.append(connection)

        connection.start()

        if self.on_connect is not None:
            try:
                self.on_connect(connection)
            except Exception as exc:
                connection.close('connect handler error: %s' % exc)

    def _handle_closed(self, connection, reason):
        # Notify *before* removing from the list. If the order were reversed,
        # an observer that waits for connections() to drain and then reads the
        # disconnect state would see a window where the peer is gone from the
        # roster but its departure has not been reported - which is exactly the
        # sequence session.py will rely on for roster updates in phase 4.
        if self.on_disconnect is not None:
            try:
                self.on_disconnect(connection, reason)
            except Exception:
                pass

        with self._lock:
            if connection in self._connections:
                self._connections.remove(connection)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientTransport:
    """
    Connects to a host over TLS and verifies the certificate pin.

    `connect()` returns only after the pin has been checked, so a caller holding
    a ClientTransport whose `connection` is open is talking to the host named by
    the join code - or to nobody.
    """

    def __init__(self, host, port, pin, on_message=None, on_disconnect=None,
                 timeout=10.0):
        self.host = str(host)
        self.port = int(port)
        self.pin = str(pin)
        self.timeout = float(timeout)

        self.on_message = on_message
        self.on_disconnect = on_disconnect

        self.connection = None
        self.cert_fingerprint = ''

    def connect(self):
        """
        Performs the TCP connect, the TLS handshake and the pin check, then
        starts the reader. Returns the Connection.

        Raises PinMismatch if the certificate does not match the join code, or
        TransportError for an ordinary connection failure. Callers must present
        those two very differently to the user.
        """
        try:
            raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise TransportError('Could not reach %s on port %d: %s'
                                 % (self.host, self.port, exc))

        context = make_client_context()

        try:
            tls = context.wrap_socket(raw, server_hostname=None)
        except (ssl.SSLError, OSError) as exc:
            try:
                raw.close()
            except OSError:
                pass
            raise TransportError('Secure connection to the host failed: %s' % exc)

        try:
            self.cert_fingerprint = _verify_pinned_certificate(tls, self.pin)
        except PinMismatch:
            # Close before anything is sent: the peer must learn nothing, not
            # even that we were willing to speak.
            try:
                tls.close()
            except OSError:
                pass
            raise

        tls.settimeout(_READ_TIMEOUT_SECONDS)

        connection = Connection(
            tls, (self.host, self.port), is_server_side=False,
            on_message=self.on_message,
            on_closed=self._handle_closed,
            name=self.host,
        )
        connection.cert_fingerprint = self.cert_fingerprint

        self.connection = connection
        connection.start()
        return connection

    def close(self, reason='left the session'):
        if self.connection is not None:
            self.connection.close(reason)

    def send(self, message):
        if self.connection is None:
            return False
        return self.connection.send(message)

    def _handle_closed(self, connection, reason):
        if self.on_disconnect is not None:
            try:
                self.on_disconnect(connection, reason)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Local addresses
# ---------------------------------------------------------------------------

def local_ip_addresses():
    """
    Best-effort list of this machine's LAN addresses, for showing the host which
    address to share.

    The UDP-connect trick asks the routing table which source address would be
    used to reach the internet; no packet is sent. Loopback is excluded because
    it is never useful in a join code.
    """
    found = []

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('203.0.113.1', 9))   # RFC 5737 documentation range
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found:
                found.append(address)
    except OSError:
        pass

    return [a for a in found if a and not a.startswith('127.')]
