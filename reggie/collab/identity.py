"""
Host identity and join codes.

Three responsibilities, all pure logic except for certificate generation:

1. The host's long-lived self-signed certificate and its SHA-256 fingerprint.
2. The join code that carries address, port, fingerprint pin and room secret.
3. Path and filename validation for anything that arrives over the network.

Why a self-signed certificate is enough here: the join code contains the first
12 bytes of the certificate's SHA-256, and the client pins that value before
trusting the connection. An attacker who intercepts the TCP session must
present a certificate whose fingerprint matches, which it cannot forge. So we
get confidentiality plus MITM detection with no certificate authority, no
server and no accounts - which is exactly the v1 scope Zement approved
(LAN + direct/UPnP, zero external services).

Certificate generation needs X.509 encoding, which the standard library cannot
do. Rather than adding `cryptography` as a packaged dependency for four build
platforms (the build currently ships only PyQt6 Core/Gui/Widgets and has no
requirements file), generation is pluggable:

    - `cryptography` if importable (best: pure Python, no subprocess)
    - the `openssl` binary if one is on PATH
    - otherwise raise CertificateUnavailable with an actionable message

Everything else in this module - fingerprints, join codes, path validation -
is standard library only and always available, so the whole security surface
stays unit-testable even where generation is not.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile


# Join code format tag. Lets us change the scheme later without ambiguity.
JOIN_CODE_TAG = 'REGGIE1'

# Bytes of the certificate SHA-256 that go into the join code. 12 bytes = 96
# bits, base32-encoded to 20 characters: far beyond collision-forging reach
# while staying short enough to retype.
FINGERPRINT_PIN_BYTES = 12

# Room secret length. 16 bytes = 128 bits of entropy, base32 to 26 characters.
SECRET_BYTES = 16

# Default ports (spec section 3). Unassigned by IANA, outside the ephemeral
# range so they are unlikely to collide with a transient socket.
DEFAULT_DISCOVERY_PORT = 45922
DEFAULT_HOST_PORT = 45923

CERT_FILENAME = 'collab_host_cert.pem'
KEY_FILENAME = 'collab_host_key.pem'

# Extensions that may be transferred (spec section 4.4). Data only.
ALLOWED_TRANSFER_EXTENSIONS = frozenset({
    '.arc', '.png', '.xml', '.txt', '.json', '.bin',
})

# Two-part extensions that may be transferred (Block C - B3).
#
# Levels and tilesets ship in three forms - 'x.arc', 'x.arc.LH' and 'x.arc.LZ',
# the latter two being LH/LZ-compressed archives (globals_.FileExtentions). They
# are the same data and carry the same (absence of) risk, so a transfer that
# carries Stage and Texture folders has to accept all three.
#
# Deliberately listed as *compound* extensions rather than adding '.lh' and
# '.lz' to the set above. check_transfer_extension only looks at the text after
# the final dot, so allowing bare '.lh' would also admit 'evil.py.lh' - the
# denylist would still catch that particular name, but the rule would then rest
# entirely on the denylist being exhaustive, which is the arrangement the
# two-gate design exists to avoid. Requiring the full '.arc.lh' keeps the
# allowlist meaningful on its own.
ALLOWED_COMPOUND_TRANSFER_EXTENSIONS = frozenset({
    '.arc.lh', '.arc.lz',
})

# Explicit denylist as a second gate, so an allowlist mistake is never the only
# thing standing between a peer and code execution. Anything Python, any native
# module, any script, any archive.
DENIED_TRANSFER_EXTENSIONS = frozenset({
    '.py', '.pyc', '.pyo', '.pyd', '.pyw', '.dll', '.so', '.dylib',
    '.exe', '.com', '.scr', '.msi', '.bat', '.cmd', '.ps1', '.psm1',
    '.sh', '.bash', '.zsh', '.vbs', '.js', '.jse', '.wsf', '.wsh',
    '.jar', '.lnk', '.reg', '.zip', '.7z', '.rar', '.tar', '.gz',
    '.bz2', '.xz', '.cab', '.iso',
})

# Windows reserved device names: creating these can hang or misbehave even when
# the path itself looks harmless.
_WINDOWS_RESERVED_NAMES = frozenset({
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
})

# Characters Windows rejects in a filename. '/' and '\\' are handled earlier as
# separators; these are the rest. Control characters are covered separately.
_WINDOWS_ILLEGAL_CHARACTERS = frozenset(':*?"<>|')

_BASE32_ALPHABET = re.compile(r'^[A-Z2-7]+$')


class CertificateUnavailable(Exception):
    """
    Raised when no certificate generation backend is available.
    """


class JoinCodeError(Exception):
    """
    Raised for a malformed or unparsable join code.
    """


class UnsafePathError(Exception):
    """
    Raised when a network-supplied path or filename fails validation.
    """


# ---------------------------------------------------------------------------
# Base32 helpers (no padding, case-insensitive on input)
# ---------------------------------------------------------------------------

def b32_encode(data):
    return base64.b32encode(bytes(data)).decode('ascii').rstrip('=')


def b32_decode(text):
    if not isinstance(text, str):
        raise ValueError('base32 input must be a string')

    cleaned = text.strip().replace('-', '').replace(' ', '').upper()
    if not cleaned or not _BASE32_ALPHABET.match(cleaned):
        raise ValueError('not valid base32')

    padding = '=' * (-len(cleaned) % 8)
    return base64.b32decode(cleaned + padding)


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------

def fingerprint_from_der(der_bytes):
    """
    Full SHA-256 fingerprint of a DER-encoded certificate, as lowercase hex.
    """
    return hashlib.sha256(bytes(der_bytes)).hexdigest()


def fingerprint_from_pem(pem_text):
    """
    Full SHA-256 fingerprint of a PEM certificate, as lowercase hex.
    """
    if isinstance(pem_text, bytes):
        pem_text = pem_text.decode('ascii', 'strict')
    return fingerprint_from_der(ssl.PEM_cert_to_DER_cert(pem_text))


def pin_from_fingerprint(fingerprint_hex):
    """
    The short, shareable form of a fingerprint: first FINGERPRINT_PIN_BYTES
    bytes, base32-encoded.
    """
    raw = bytes.fromhex(fingerprint_hex)
    return b32_encode(raw[:FINGERPRINT_PIN_BYTES])


def fingerprint_matches_pin(fingerprint_hex, pin):
    """
    Constant-time check that a full fingerprint starts with the pinned prefix.

    This is the MITM defence: called by the client immediately after the TLS
    handshake, before any secret or level data is exchanged.
    """
    try:
        expected = b32_decode(pin)
    except ValueError:
        return False

    if len(expected) != FINGERPRINT_PIN_BYTES:
        return False

    try:
        actual = bytes.fromhex(fingerprint_hex)
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(actual[:FINGERPRINT_PIN_BYTES], expected)


# ---------------------------------------------------------------------------
# Room secret
# ---------------------------------------------------------------------------

def generate_secret():
    """
    A fresh room secret (the part of the join code that authenticates a peer).
    """
    return b32_encode(secrets.token_bytes(SECRET_BYTES))


# ---------------------------------------------------------------------------
# Join codes
# ---------------------------------------------------------------------------

def encode_endpoint(host, port):
    """
    Packs host and port into one base32 field.

    **This is obfuscation, not protection, and the distinction matters.** The
    address is recoverable by anyone who decodes the field, and both peers can
    read each other's address off the socket the moment they connect. What it
    buys is that a join code pasted into a chat window or a screenshot does not
    put a bare public IP in front of everyone who happens to read it.

    Nothing security-relevant rests on this: the certificate pin and the
    session secret are the parts that matter, and both are unchanged.
    """
    host = str(host or '').strip()
    if not host or ':' in host:
        raise JoinCodeError('host must be a non-empty string without colons')

    port = int(port)
    if not (1 <= port <= 65535):
        raise JoinCodeError('port out of range')

    payload = host.encode('utf-8')
    if len(payload) > 255:
        raise JoinCodeError('host is too long for a join code')

    # port big-endian, then the host bytes. Length-prefixed so trailing base32
    # padding cannot be mistaken for part of the address.
    raw = bytes((len(payload),)) + port.to_bytes(2, 'big') + payload
    return b32_encode(raw)


def decode_endpoint(field):
    """
    Unpacks encode_endpoint(). Returns (host, port).
    """
    cleaned = str(field or '').strip().replace('-', '').replace(' ', '').upper()
    if not cleaned:
        raise JoinCodeError('join code is missing the address')

    try:
        raw = b32_decode(cleaned)
    except ValueError:
        raise JoinCodeError('join code address is not valid base32')

    if len(raw) < 4:
        raise JoinCodeError('join code address is too short')

    length = raw[0]
    port = int.from_bytes(raw[1:3], 'big')
    payload = raw[3:3 + length]

    if len(payload) != length:
        raise JoinCodeError('join code address is truncated')
    if not (1 <= port <= 65535):
        raise JoinCodeError('join code port is out of range')

    try:
        host = payload.decode('utf-8')
    except UnicodeDecodeError:
        raise JoinCodeError('join code address is not valid text')

    host = host.strip()
    if not host:
        raise JoinCodeError('join code is missing the host')

    return host, port


def encode_join_code(host, port, fingerprint_hex, secret):
    """
    Builds the join code string: REGGIE1:<endpoint>:<pin>:<secret>

    The endpoint packs host and port into one base32 field so the code does not
    display a bare IP address - see encode_endpoint for what that is and is not
    worth.
    """
    endpoint = encode_endpoint(host, port)

    pin = pin_from_fingerprint(fingerprint_hex)

    secret = str(secret or '').strip().upper()
    if not secret or not _BASE32_ALPHABET.match(secret):
        raise JoinCodeError('secret must be base32')

    return ':'.join((JOIN_CODE_TAG, endpoint, pin, secret))


def decode_join_code(code):
    """
    Parses a join code, tolerating whitespace, lowercase and display chunking.
    Returns {'host', 'port', 'pin', 'secret'}.

    Raises JoinCodeError with a user-facing message for anything malformed:
    this is typed/pasted by hand, so failures must be explainable.
    """
    if not isinstance(code, str):
        raise JoinCodeError('join code must be text')

    text = code.strip()
    if not text:
        raise JoinCodeError('join code is empty')

    parts = text.split(':')
    if len(parts) != 4:
        raise JoinCodeError('join code must have 4 colon-separated parts')

    tag, endpoint, pin, secret = parts

    if tag.strip().upper() != JOIN_CODE_TAG:
        raise JoinCodeError('unrecognised join code format')

    host, port = decode_endpoint(endpoint)

    pin = pin.strip().replace('-', '').replace(' ', '').upper()
    try:
        pin_raw = b32_decode(pin)
    except ValueError:
        raise JoinCodeError('join code fingerprint is not valid base32')

    if len(pin_raw) != FINGERPRINT_PIN_BYTES:
        raise JoinCodeError('join code fingerprint has the wrong length')

    secret = secret.strip().replace('-', '').replace(' ', '').upper()
    try:
        secret_raw = b32_decode(secret)
    except ValueError:
        raise JoinCodeError('join code secret is not valid base32')

    if len(secret_raw) != SECRET_BYTES:
        raise JoinCodeError('join code secret has the wrong length')

    return {'host': host, 'port': port, 'pin': pin, 'secret': secret}


def format_join_code_for_display(code, group=5):
    """
    Inserts dashes into the pin and secret so the code can be read aloud or
    retyped. decode_join_code() strips them again.
    """
    parts = str(code).split(':')

    def chunk(value):
        return '-'.join(value[i:i + group] for i in range(0, len(value), group))

    if len(parts) != 4:
        return code

    # tag:endpoint:pin:secret - every field after the tag is base32, so all
    # three are chunked for readability.
    parts[1] = chunk(parts[1])
    parts[2] = chunk(parts[2])
    parts[3] = chunk(parts[3])
    return ':'.join(parts)


# ---------------------------------------------------------------------------
# Certificate generation / loading
# ---------------------------------------------------------------------------

def certificate_paths(base_dir):
    return (os.path.join(base_dir, CERT_FILENAME),
            os.path.join(base_dir, KEY_FILENAME))


def generation_backend():
    """
    Which certificate backend is available: 'cryptography', 'openssl' or None.
    """
    try:
        import cryptography  # noqa: F401
        return 'cryptography'
    except ImportError:
        pass

    if shutil.which('openssl'):
        return 'openssl'

    return None


def generate_self_signed(cert_path, key_path, common_name='Reggie Next Collab'):
    """
    Generates a P-256 self-signed certificate valid for ~10 years and writes
    cert_path and key_path. Returns the full SHA-256 fingerprint.

    The certificate identifies the *host instance*, not a DNS name, so the
    subject is cosmetic; the fingerprint is what matters.
    """
    backend = generation_backend()

    if backend == 'cryptography':
        return _generate_with_cryptography(cert_path, key_path, common_name)
    if backend == 'openssl':
        return _generate_with_openssl(cert_path, key_path, common_name)

    raise CertificateUnavailable(
        'Cannot create the collaboration certificate: neither the '
        '"cryptography" Python package nor an "openssl" program is available. '
        'Install one of them to host a collaboration session. Joining a '
        'session does not require either.'
    )


def _generate_with_cryptography(cert_path, key_path, common_name):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    _write_private(key_path, key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    _write_private(cert_path, cert.public_bytes(serialization.Encoding.PEM))

    return fingerprint_from_der(cert.public_bytes(serialization.Encoding.DER))


def _generate_with_openssl(cert_path, key_path, common_name):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_key = os.path.join(tmp, 'key.pem')
        tmp_cert = os.path.join(tmp, 'cert.pem')

        command = [
            'openssl', 'req', '-x509', '-nodes',
            '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
            '-keyout', tmp_key, '-out', tmp_cert,
            '-days', '3650', '-sha256',
            '-subj', '/CN=%s' % common_name.replace('/', '-'),
        ]

        creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )

        if result.returncode != 0 or not os.path.isfile(tmp_cert):
            raise CertificateUnavailable(
                'openssl failed to create the collaboration certificate: %s'
                % result.stderr.decode('utf-8', 'replace').strip()[:400]
            )

        with open(tmp_key, 'rb') as handle:
            key_bytes = handle.read()
        with open(tmp_cert, 'rb') as handle:
            cert_bytes = handle.read()

    _write_private(key_path, key_bytes)
    _write_private(cert_path, cert_bytes)

    return fingerprint_from_pem(cert_bytes.decode('ascii', 'replace'))


def _write_private(path, data):
    """
    Writes a file containing key material with owner-only permissions where the
    platform supports it.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, 'wb') as handle:
        handle.write(data)

    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows without POSIX ACLs; the file still lives in the user profile.
        pass


def load_or_create_identity(base_dir, common_name='Reggie Next Collab'):
    """
    Returns (cert_path, key_path, fingerprint_hex), generating the certificate
    on first use. Raises CertificateUnavailable if generation is needed but no
    backend exists.
    """
    cert_path, key_path = certificate_paths(base_dir)

    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        with open(cert_path, 'r', encoding='ascii', errors='replace') as handle:
            pem = handle.read()
        return cert_path, key_path, fingerprint_from_pem(pem)

    fingerprint = generate_self_signed(cert_path, key_path, common_name)
    return cert_path, key_path, fingerprint


# ---------------------------------------------------------------------------
# Path validation for received files
# ---------------------------------------------------------------------------
#
# This is the exact class of bug the slivaPiva fork shipped: a network-supplied
# tileset name went straight into os.path.join() and then open(path, 'wb'), so a
# malicious host could write anywhere on disk. Every received path must go
# through safe_join(), and every received bare filename through
# safe_filename().

def _reject_traversal_components(relative_path):
    # Normalise separators first so 'a\\..\\b' is caught on POSIX too, where
    # a backslash is an ordinary filename character.
    unified = str(relative_path).replace('\\', '/')

    if not unified or unified.strip() == '':
        raise UnsafePathError('empty path')

    if unified.startswith('/'):
        raise UnsafePathError('absolute paths are not allowed')

    # Drive letters and UNC paths.
    if re.match(r'^[A-Za-z]:', unified) or unified.startswith('//'):
        raise UnsafePathError('absolute or UNC paths are not allowed')

    if '\x00' in unified:
        raise UnsafePathError('path contains a null byte')

    components = [part for part in unified.split('/') if part != '']
    if not components:
        raise UnsafePathError('path has no usable components')

    for part in components:
        if part == '.':
            raise UnsafePathError('path contains a "." component')
        if part == '..':
            raise UnsafePathError('path contains a ".." component')

        # Trailing dots/spaces are silently stripped by Windows, which lets
        # 'evil.py.' land as 'evil.py' after an extension check on '.py.'.
        if part != part.rstrip(' .'):
            raise UnsafePathError('path component has trailing dots or spaces')

        stem = part.split('.', 1)[0].lower()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise UnsafePathError('path uses the reserved name %r' % stem)

        # Characters Windows forbids in a filename. Rejected on every platform
        # so a manifest built on Linux cannot describe files a Windows peer is
        # unable to create - the transfer would otherwise verify every hash and
        # then fail at the last step, on the write.
        #
        # A colon is the one that bites in practice: 'NSMBW: The Prankster
        # Comets' is a perfectly ordinary patch name and an impossible Windows
        # directory name.
        illegal = set(part) & _WINDOWS_ILLEGAL_CHARACTERS
        if illegal:
            raise UnsafePathError(
                'path component contains characters that cannot be used in a '
                'filename: %s' % ' '.join(sorted(illegal)))

        if len(part) > 255:
            raise UnsafePathError('path component is too long')

    return components


def check_transfer_extension(relative_path):
    """
    Enforces the transfer extension policy: denylist first, then allowlist.
    Raises UnsafePathError if the file may not be transferred.
    """
    name = str(relative_path).replace('\\', '/').rsplit('/', 1)[-1]

    # Check every suffix, not just the last one: 'evil.py.arc' must not pass
    # merely because it ends in .arc.
    lowered = name.lower()
    for suffix in DENIED_TRANSFER_EXTENSIONS:
        if lowered.endswith(suffix) or ('%s.' % suffix) in lowered:
            raise UnsafePathError('file type %r may never be transferred' % suffix)

    # Two-part extensions first, so 'level.arc.lh' is recognised as a compressed
    # level rather than as the '.lh' its final dot suggests. The name must be
    # longer than the extension - a file called exactly '.arc.lh' has no stem and
    # is not a level.
    for compound in ALLOWED_COMPOUND_TRANSFER_EXTENSIONS:
        if lowered.endswith(compound) and len(lowered) > len(compound):
            return compound

    dot = lowered.rfind('.')
    extension = lowered[dot:] if dot > 0 else ''

    if extension not in ALLOWED_TRANSFER_EXTENSIONS:
        raise UnsafePathError(
            'file type %r is not in the transfer allowlist' % (extension or '(none)'))

    return extension


def safe_join(root, relative_path, require_allowed_extension=True):
    """
    Resolves a network-supplied relative path under `root` and returns an
    absolute path guaranteed to stay inside it.

    Raises UnsafePathError for absolute paths, '..' traversal, null bytes,
    reserved Windows names, trailing dots/spaces, disallowed extensions, or any
    result that escapes the root.
    """
    components = _reject_traversal_components(relative_path)

    if require_allowed_extension:
        check_transfer_extension(relative_path)

    root_abs = os.path.abspath(str(root))
    candidate = os.path.abspath(os.path.join(root_abs, *components))

    # The prefix check is the belt to the component check's braces: it also
    # catches anything the OS resolves differently than we expect.
    if candidate != root_abs and not candidate.startswith(root_abs + os.sep):
        raise UnsafePathError('resolved path escapes the target directory')

    if candidate == root_abs:
        raise UnsafePathError('path resolves to the target directory itself')

    return candidate


def safe_component(name):
    """
    Validates a bare *directory* name that arrived over the network, such as a
    patch id, and returns it unchanged.

    Separate from safe_filename() because a directory has no extension, so the
    transfer allowlist does not apply - but every other check does: no
    separators, no traversal, no null bytes, no Windows reserved names, no
    trailing dots or spaces.
    """
    text = str(name or '')
    if not text:
        raise UnsafePathError('empty name')

    if '/' in text or '\\' in text:
        raise UnsafePathError('name must not contain a path separator')

    components = _reject_traversal_components(text)
    if len(components) != 1:
        raise UnsafePathError('name must be a single component')

    return components[0]


def safe_filename(name, extension='.arc'):
    """
    Validates a bare filename (no directories) that arrived over the network,
    such as a tileset name, and returns it with the given extension.

    This is the specific hole in the fork: _GetTilesetDownloadPath() accepted
    any string. Here a name containing a separator or traversal is rejected
    outright.
    """
    text = str(name or '')
    if not text:
        raise UnsafePathError('empty filename')

    if '/' in text or '\\' in text:
        raise UnsafePathError('filename must not contain a path separator')

    components = _reject_traversal_components(text)
    if len(components) != 1:
        raise UnsafePathError('filename must be a single component')

    filename = components[0] + extension
    check_transfer_extension(filename)
    return filename
