"""
LAN discovery over UDP broadcast.

A host may advertise that a session exists; a client may ask who is out there.
Both messages are plaintext JSON on port 45922 and **carry no secret**, which is
the property that makes broadcasting safe at all:

    probe  {"t":"reggie-collab-probe","proto":1}
    offer  {"t":"reggie-collab-offer","proto":1,"port":45923,"nick":"...",
            "game":"...","fp12":"...","players":2,"max_players":4,
            "needs_code":true}

Discovery makes a session *findable*, never joinable. The join code - which
carries the room secret - still has to travel out of band. So the worst a
listener on the same LAN learns is that Zementblock is editing a level, which is
not worth protecting; and an attacker cannot use an offer to get in.

This is a deliberate departure from the audited fork, which published sessions
into Dolphin's live public lobby (`lobby.dolphin-emu.org`) and used
`stun.dolphin-emu.org` for traversal. We use no external service at all: LAN
broadcast plus a code the user shares themselves.

Design notes:

- The host answers probes *unicast* to the prober rather than broadcasting a
  reply, so an offer only ever reaches someone who asked.
- Advertising is opt-in (spec section 3.1). `DiscoveryResponder` is not started
  unless the user ticks the box.
- `fp12` is included so a discovered entry can be matched against a join code
  the user pastes afterwards, catching "you typed the code for the other host".
- Both sides bound every field and ignore anything malformed. A UDP port is
  sprayed by all sorts of things; unparsable traffic is normal, not exceptional.
"""

import json
import socket
import threading
import time

from reggie.collab.identity import DEFAULT_DISCOVERY_PORT, DEFAULT_HOST_PORT
from reggie.collab.protocol import (
    MAX_NICK_CHARS,
    PROTOCOL_VERSION,
    sanitize_text,
)


PROBE_TYPE = 'reggie-collab-probe'
OFFER_TYPE = 'reggie-collab-offer'

# Discovery datagrams are a few hundred bytes; this is generous and still far
# below anything that could pressure memory.
MAX_DATAGRAM_BYTES = 2048

# Field caps for received offers.
MAX_GAME_CHARS = 96
MAX_FP12_CHARS = 32

BROADCAST_ADDRESS = '255.255.255.255'

DEFAULT_PROBE_TIMEOUT = 2.0
_SOCKET_TIMEOUT = 0.5


class DiscoveryError(Exception):
    """
    Raised when a discovery socket cannot be set up. User-facing.
    """


# ---------------------------------------------------------------------------
# Encoding / decoding
# ---------------------------------------------------------------------------

def encode_probe():
    return json.dumps({'t': PROBE_TYPE, 'proto': PROTOCOL_VERSION},
                      separators=(',', ':')).encode('utf-8')


def encode_offer(port, nick='', game='', fp12='', players=1, max_players=4,
                 needs_code=True):
    payload = {
        't': OFFER_TYPE,
        'proto': PROTOCOL_VERSION,
        'port': int(port),
        'nick': sanitize_text(str(nick or ''), MAX_NICK_CHARS),
        'game': sanitize_text(str(game or ''), MAX_GAME_CHARS),
        'fp12': str(fp12 or '')[:MAX_FP12_CHARS],
        'players': int(players),
        'max_players': int(max_players),
        'needs_code': bool(needs_code),
    }
    return json.dumps(payload, separators=(',', ':')).encode('utf-8')


def decode_datagram(data):
    """
    Parses a discovery datagram into a dict, or returns None if it is not one of
    ours or is malformed in any way.

    Returning None rather than raising is intentional: a broadcast port receives
    unrelated traffic constantly, and treating that as an error condition would
    turn normal network noise into log spam.
    """
    if not data or len(data) > MAX_DATAGRAM_BYTES:
        return None

    try:
        parsed = json.loads(bytes(data).decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    kind = parsed.get('t')
    if kind not in (PROBE_TYPE, OFFER_TYPE):
        return None

    try:
        proto = int(parsed.get('proto', -1))
    except (TypeError, ValueError):
        return None

    # Bools are ints in Python; a JSON `true` here is a malformed version.
    if isinstance(parsed.get('proto'), bool) or proto != PROTOCOL_VERSION:
        return None

    if kind == PROBE_TYPE:
        return {'t': PROBE_TYPE, 'proto': proto}

    return _decode_offer(parsed, proto)


def _decode_offer(parsed, proto):
    try:
        port = int(parsed.get('port', 0))
    except (TypeError, ValueError):
        return None

    if isinstance(parsed.get('port'), bool) or not (1 <= port <= 65535):
        return None

    def clean_int(key, default, low, high):
        try:
            value = int(parsed.get(key, default))
        except (TypeError, ValueError):
            return default
        if isinstance(parsed.get(key), bool):
            return default
        return max(low, min(high, value))

    return {
        't': OFFER_TYPE,
        'proto': proto,
        'port': port,
        'nick': sanitize_text(str(parsed.get('nick', ''))[:MAX_NICK_CHARS], MAX_NICK_CHARS),
        'game': sanitize_text(str(parsed.get('game', ''))[:MAX_GAME_CHARS], MAX_GAME_CHARS),
        'fp12': str(parsed.get('fp12', ''))[:MAX_FP12_CHARS],
        'players': clean_int('players', 0, 0, 64),
        'max_players': clean_int('max_players', 0, 0, 64),
        'needs_code': bool(parsed.get('needs_code', True)),
    }


# ---------------------------------------------------------------------------
# Host side
# ---------------------------------------------------------------------------

class DiscoveryResponder:
    """
    Answers probes on the LAN while a session is being hosted.

    Opt-in: the caller starts this only when the user has ticked "make this
    session discoverable on my network". Not started means not discoverable.

    `describe` is a callable returning the current offer fields, so the reply
    reflects live state (player count especially) rather than a stale snapshot
    taken at start-up.
    """

    def __init__(self, describe, port=DEFAULT_DISCOVERY_PORT):
        self.describe = describe
        self.port = int(port)
        self._socket = None
        self._thread = None
        self._stop = threading.Event()
        self.replies_sent = 0

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(('', self.port))
        except OSError as exc:
            sock.close()
            raise DiscoveryError(
                'Could not listen for network discovery on port %d: %s'
                % (self.port, exc))

        sock.settimeout(_SOCKET_TIMEOUT)
        self._socket = sock
        self._stop.clear()

        self._thread = threading.Thread(
            target=self._serve_loop, name='collab-discovery-responder', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _serve_loop(self):
        while not self._stop.is_set():
            try:
                data, sender = self._socket.recvfrom(MAX_DATAGRAM_BYTES)
            except socket.timeout:
                continue
            except OSError:
                break

            message = decode_datagram(data)
            if message is None or message['t'] != PROBE_TYPE:
                continue

            try:
                fields = dict(self.describe() or {})
            except Exception:
                continue

            fields.setdefault('port', DEFAULT_HOST_PORT)

            try:
                reply = encode_offer(**fields)
            except (TypeError, ValueError):
                continue

            try:
                # Unicast: only the peer that asked gets the answer.
                self._socket.sendto(reply, sender)
                self.replies_sent += 1
            except OSError:
                continue


# ---------------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------------

def probe_lan(timeout=DEFAULT_PROBE_TIMEOUT, port=DEFAULT_DISCOVERY_PORT):
    """
    Broadcasts one probe and collects offers until `timeout` elapses.

    Returns a list of offer dicts with an added 'address' key. Deduplicated by
    (address, port), keeping the newest, since a host with several interfaces can
    answer more than once.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        sock.bind(('', 0))
    except OSError as exc:
        sock.close()
        raise DiscoveryError('Could not open a discovery socket: %s' % exc)

    sock.settimeout(_SOCKET_TIMEOUT)
    found = {}

    try:
        try:
            sock.sendto(encode_probe(), (BROADCAST_ADDRESS, int(port)))
        except OSError as exc:
            raise DiscoveryError('Could not broadcast on your network: %s' % exc)

        deadline = time.monotonic() + float(timeout)

        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(MAX_DATAGRAM_BYTES)
            except socket.timeout:
                continue
            except OSError:
                break

            offer = decode_datagram(data)
            if offer is None or offer['t'] != OFFER_TYPE:
                continue

            offer['address'] = sender[0]
            found[(sender[0], offer['port'])] = offer
    finally:
        try:
            sock.close()
        except OSError:
            pass

    return list(found.values())


class DiscoveryBrowser:
    """
    Repeatedly probes the LAN on a background thread and reports offers via a
    callback, for a setup dialog that updates while it is open.

    `on_offer` is called from the browser thread; the UI layer must marshal it
    onto the Qt main thread.
    """

    def __init__(self, on_offer, interval=3.0, port=DEFAULT_DISCOVERY_PORT):
        self.on_offer = on_offer
        self.interval = float(interval)
        self.port = int(port)
        self._thread = None
        self._stop = threading.Event()
        self.last_error = ''

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._browse_loop, name='collab-discovery-browser', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(DEFAULT_PROBE_TIMEOUT + 1.0)
            self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _browse_loop(self):
        while not self._stop.is_set():
            try:
                offers = probe_lan(timeout=DEFAULT_PROBE_TIMEOUT, port=self.port)
            except DiscoveryError as exc:
                # Typically a firewall block. Record it for the dialog to show
                # instead of leaving an empty list unexplained.
                self.last_error = str(exc)
                offers = []

            for offer in offers:
                if self._stop.is_set():
                    return
                try:
                    self.on_offer(offer)
                except Exception:
                    pass

            self._stop.wait(self.interval)
