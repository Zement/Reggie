"""
Handshake authentication: nonce, key derivation, proof, and failure lockout.

The room secret never crosses the wire. Instead:

    K     = scrypt(secret, salt=cert_fp, n=2**14, r=8, p=1, dklen=32)
    proof = HMAC-SHA256(K, b"reggie-collab-v1" || nonce || cert_fp)

Three properties this buys us, all of which the slivaPiva fork lacks entirely
(its "password" only obfuscated the host code in a lobby listing and was never
checked on connect):

- A passive observer of a handshake learns nothing reusable: the proof is bound
  to a per-connection nonce, so replaying it fails.
- Binding the proof to the certificate fingerprint means a proof captured from
  one host cannot be replayed to another. An attacker who relays a handshake to
  a different host produces a proof over the wrong fingerprint.
- scrypt makes offline brute force of a short secret expensive, which matters
  because the secret is human-transferable and therefore short.

All comparisons use hmac.compare_digest. Failures are reported to the peer
uniformly, so an unauthenticated caller cannot distinguish a wrong secret from a
ban or a version mismatch.
"""

import hashlib
import hmac
import secrets
import time


# Domain separation string. Changing this invalidates every existing join code,
# which is exactly what we want if the scheme itself ever changes.
PROOF_CONTEXT = b'reggie-collab-v1'

NONCE_BYTES = 32

# scrypt parameters. n=2**14 with r=8 needs ~16 MiB and a few tens of
# milliseconds: negligible for one handshake, punishing for bulk guessing.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
# hashlib.scrypt enforces maxmem; 0 means "use the OpenSSL default", which is
# too small for the parameters above, so request explicitly.
SCRYPT_MAXMEM = 64 * 1024 * 1024

# Lockout policy (spec section 5.3).
MAX_AUTH_FAILURES = 5
FAILURE_WINDOW_SECONDS = 60.0
LOCKOUT_SECONDS = 15 * 60.0

# Uniform failure text sent to peers. Never leaks which check failed.
GENERIC_AUTH_FAILURE = 'Authentication failed.'


class AuthError(Exception):
    """
    Raised for a failed or malformed authentication attempt. The text is for
    logs only; peers always receive GENERIC_AUTH_FAILURE.
    """


def generate_nonce():
    """
    A fresh per-connection server nonce, as lowercase hex.
    """
    return secrets.token_bytes(NONCE_BYTES).hex()


def derive_key(secret, cert_fingerprint_hex):
    """
    Derives the HMAC key from the room secret, salted with the host's
    certificate fingerprint.

    Salting with the fingerprint means the same secret used by two different
    hosts produces different keys, so a proof is never portable between hosts.
    """
    if not isinstance(secret, str) or not secret:
        raise AuthError('secret must be a non-empty string')
    if not isinstance(cert_fingerprint_hex, str) or not cert_fingerprint_hex:
        raise AuthError('certificate fingerprint must be a non-empty string')

    # Normalise the secret the same way the join code parser does, so a
    # lowercase or dash-chunked entry authenticates identically.
    normalised = secret.strip().replace('-', '').replace(' ', '').upper()

    return hashlib.scrypt(
        normalised.encode('utf-8'),
        salt=cert_fingerprint_hex.strip().lower().encode('ascii', 'strict'),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )


def compute_proof(secret, nonce_hex, cert_fingerprint_hex):
    """
    Computes the client's authentication proof, as lowercase hex.
    """
    if not isinstance(nonce_hex, str) or not nonce_hex:
        raise AuthError('nonce must be a non-empty string')

    try:
        nonce = bytes.fromhex(nonce_hex)
    except ValueError:
        raise AuthError('nonce is not valid hex')

    if len(nonce) != NONCE_BYTES:
        raise AuthError('nonce must be %d bytes' % NONCE_BYTES)

    key = derive_key(secret, cert_fingerprint_hex)
    fingerprint = cert_fingerprint_hex.strip().lower().encode('ascii', 'strict')

    return hmac.new(key, PROOF_CONTEXT + nonce + fingerprint, hashlib.sha256).hexdigest()


def verify_proof(proof_hex, secret, nonce_hex, cert_fingerprint_hex):
    """
    Constant-time verification of a client proof. Returns True/False and never
    raises for a merely wrong proof, so callers cannot accidentally leak the
    reason through differing exception paths.
    """
    if not isinstance(proof_hex, str) or not proof_hex:
        return False

    try:
        expected = compute_proof(secret, nonce_hex, cert_fingerprint_hex)
    except AuthError:
        return False

    return hmac.compare_digest(proof_hex.strip().lower(), expected)


class FailureTracker:
    """
    Per-IP authentication failure tracking with a sliding window and lockout.

    Deliberately keyed on IP only: at handshake time there is no authenticated
    identity to key on, and an unauthenticated peer must not be able to cause
    another peer to be locked out. The clock is injectable for tests.
    """

    def __init__(self,
                 max_failures=MAX_AUTH_FAILURES,
                 window_seconds=FAILURE_WINDOW_SECONDS,
                 lockout_seconds=LOCKOUT_SECONDS,
                 clock=time.monotonic):
        self.max_failures = int(max_failures)
        self.window_seconds = float(window_seconds)
        self.lockout_seconds = float(lockout_seconds)
        self._clock = clock
        self._failures = {}   # ip -> [timestamps]
        self._locked = {}     # ip -> unlock timestamp

    def is_locked(self, ip):
        """
        Whether this IP is currently locked out. Expired locks are cleared.
        """
        key = self._normalise(ip)
        unlock_at = self._locked.get(key)
        if unlock_at is None:
            return False

        if self._clock() >= unlock_at:
            self._locked.pop(key, None)
            self._failures.pop(key, None)
            return False

        return True

    def seconds_remaining(self, ip):
        key = self._normalise(ip)
        unlock_at = self._locked.get(key)
        if unlock_at is None:
            return 0.0
        return max(0.0, unlock_at - self._clock())

    def record_failure(self, ip):
        """
        Records a failed attempt. Returns True if this attempt triggered a
        lockout.
        """
        key = self._normalise(ip)
        now = self._clock()

        timestamps = [t for t in self._failures.get(key, ())
                      if now - t <= self.window_seconds]
        timestamps.append(now)
        self._failures[key] = timestamps

        if len(timestamps) >= self.max_failures:
            self._locked[key] = now + self.lockout_seconds
            self._failures.pop(key, None)
            return True

        return False

    def record_success(self, ip):
        """
        Clears the failure history for an IP after a successful handshake.
        """
        key = self._normalise(ip)
        self._failures.pop(key, None)
        self._locked.pop(key, None)

    def reset(self):
        self._failures.clear()
        self._locked.clear()

    @staticmethod
    def _normalise(ip):
        text = str(ip or '').strip().lower()
        # Treat IPv4-mapped IPv6 as the same peer as its IPv4 form.
        if text.startswith('::ffff:'):
            text = text[7:]
        return text


def check_version(client_protocol, server_protocol):
    """
    Whether a client's protocol version is acceptable. Mismatches are fatal
    (unlike app_version mismatches, which only warn) because the wire format
    would be ambiguous.
    """
    try:
        return int(client_protocol) == int(server_protocol)
    except (TypeError, ValueError):
        return False
