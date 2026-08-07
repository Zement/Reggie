"""
Patch and tileset synchronisation: manifests, chunking, staging, verification.

The problem this solves: a host is editing a level for a game patch, and a client
may not have that patch. Without it, the client sees wrong sprite images, wrong
tilesets and wrong level names - it cannot usefully collaborate.

Three ways to resolve it, in strict order of preference (spec section 4.4 and
Zement's clarifications):

1. **The client already has the patch.** Compare id and version locally; if it
   matches, nothing transfers. This is the common case and the cheapest.
2. **The Patch Manager can install it.** If the patch is in our own catalog, the
   client downloads it through the existing trusted `catalog_manager` /
   `download_manager` pipeline. The bytes come from the catalog's own source, not
   from a peer, so a malicious host cannot substitute content.
3. **Host transfer, as a consent-gated, data-only fallback.** Only for patches
   that are not in the catalog. The user is asked first, naming the host, the
   patch, the file count and the total size.

**What is never transferred, at all:**

- Any Python file. `sprites.py` is a real part of two shipped patches
  (NewerSMBW and NSMBWerPlus both have one), and transferring it would be
  handing a peer arbitrary code execution. The denylist blocks it, and this is
  not a limitation to work around later - it is the whole safety argument.
- Patch plugins and code plugins. Per Zement: both are Python, and both peers
  are assumed to ship the full plugin set for a given Reggie version, so only
  the *enable/disable state* (plain XML) is ever relevant.
- Archives (.zip, .7z, ...), which would smuggle any of the above past an
  extension check on the outer name.

The transfer path itself is written on the assumption that the sender is
hostile:

- Every path is validated by `identity.safe_join`, which rejects absolute paths,
  '..', null bytes, Windows reserved names and trailing dots, then confirms the
  resolved path is still under the staging root. This is the fork's actual bug
  (`_GetTilesetDownloadPath` wrote wherever a peer asked) and the reason staging
  exists at all.
- Files land in a staging directory and are only moved into place after **every**
  file's SHA-256 matches the manifest. A partial or tampered transfer leaves the
  real patch directory untouched.
- Sizes are checked against the manifest as bytes arrive, so a peer cannot
  announce 1 KiB and then stream indefinitely.

This module is pure logic plus filesystem work - no sockets, no Qt - so the whole
of the above is unit-testable, which is where it matters most.
"""

import base64
import hashlib
import os
import re
import shutil

from reggie.collab import identity, protocol


# Where received files are assembled before being accepted. Kept beside the
# patches directory so the final move is on the same filesystem and therefore
# atomic on both Windows and POSIX.
STAGING_DIRNAME = '_collab_staging'

PATCHES_RELATIVE_DIR = os.path.join('reggiedata', 'patches')

# Read/write in modest blocks: a patch is thousands of small PNGs, so this is
# never the bottleneck, and it keeps memory flat for the one large file.
HASH_CHUNK_BYTES = 64 * 1024

# Reasons a client reports in patch_need, for the host's status window.
NEED_MISSING = 'missing'
NEED_VERSION = 'version-mismatch'

# How a client resolved (or failed to resolve) a patch requirement.
SOURCE_LOCAL = 'local'
SOURCE_CATALOG = 'catalog'
SOURCE_HOST = 'host'
SOURCE_UNAVAILABLE = 'unavailable'


class TransferError(Exception):
    """
    Raised for any transfer problem. Messages are user-facing: a failed patch
    sync is something the user has to decide how to handle, so it must be
    explainable rather than a stack trace.
    """


class ManifestError(TransferError):
    """
    The manifest itself is unacceptable (too large, bad paths, forbidden types).
    Raised before a single byte is requested.
    """


class VerificationError(TransferError):
    """
    A received file did not match its manifest hash or size.

    Distinct from ManifestError because it means the transfer was corrupted or
    tampered with in flight, which is worth telling the user plainly.
    """


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path):
    """
    SHA-256 of a file on disk, as lowercase hex.

    Note this is SHA-256, while `catalog_manager.calculate_file_hash` uses MD5.
    That is deliberate: MD5 is adequate for spotting an accidentally corrupted
    catalog download, but a file arriving from an untrusted peer needs a hash
    that resists deliberate collisions.
    """
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(HASH_CHUNK_BYTES), b''):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


# ---------------------------------------------------------------------------
# Building a manifest (host side)
# ---------------------------------------------------------------------------

def build_manifest(patch_dir, patch_id=''):
    """
    Lists the transferable files in a patch directory.

    Skips anything the transfer policy forbids rather than failing, so a patch
    containing `sprites.py` still yields a usable manifest of its data files -
    and the caller can tell the user that the code part will not be sent.

    Returns {'patch_id', 'files': [{path, size, sha256}], 'skipped': [...],
             'total_bytes'}.
    """
    root = os.path.abspath(str(patch_dir))
    if not os.path.isdir(root):
        raise ManifestError('The patch folder %s does not exist.' % patch_dir)

    files = []
    skipped = []
    total = 0

    for directory, _subdirs, names in os.walk(root):
        for name in sorted(names):
            absolute = os.path.join(directory, name)
            relative = os.path.relpath(absolute, root).replace(os.sep, '/')

            # The same gate the receiver applies, run here so the host never
            # offers something the client would refuse - and so a patch's
            # sprites.py is visibly skipped rather than silently missing.
            try:
                identity.check_transfer_extension(relative)
            except identity.UnsafePathError as exc:
                skipped.append({'path': relative, 'reason': str(exc)})
                continue

            try:
                size = os.path.getsize(absolute)
            except OSError as exc:
                skipped.append({'path': relative, 'reason': str(exc)})
                continue

            total += size
            if total > protocol.MAX_MANIFEST_TOTAL_BYTES:
                raise ManifestError(
                    'This patch is too large to send (over %d MiB of data '
                    'files). The client should install it from the Patch '
                    'Manager instead.'
                    % (protocol.MAX_MANIFEST_TOTAL_BYTES // (1024 * 1024)))

            files.append({
                'path': relative,
                'size': size,
                'sha256': sha256_file(absolute),
            })

            if len(files) > protocol.MAX_MANIFEST_FILES:
                raise ManifestError(
                    'This patch has too many files to send (over %d). The '
                    'client should install it from the Patch Manager instead.'
                    % protocol.MAX_MANIFEST_FILES)

    return {
        'patch_id': str(patch_id),
        'files': files,
        'skipped': skipped,
        'total_bytes': total,
    }


def manifest_payload(manifest):
    """
    The wire form of a manifest: only the fields the protocol defines.

    'skipped' stays local - it is information for the host's own UI, and telling
    a peer which files we declined to send serves no purpose.
    """
    return {
        'patch_id': manifest.get('patch_id', ''),
        'files': [{'path': entry['path'],
                   'size': entry['size'],
                   'sha256': entry['sha256']}
                  for entry in manifest['files']],
    }


# ---------------------------------------------------------------------------
# Validating a manifest (client side)
# ---------------------------------------------------------------------------

def validate_manifest(payload, require_allowed_extension=True):
    """
    Checks an incoming manifest before anything is requested.

    protocol.py has already bounded the list length, the per-entry sizes, the
    running total and the hash format. What is added here is *path* safety and
    the extension policy, which protocol.py deliberately does not know about.

    Returns a normalised list of entries. Raises ManifestError, naming the
    offending path, so the user can see which file the host tried to send.
    """
    if not isinstance(payload, dict):
        raise ManifestError('The host sent a malformed file list.')

    entries = payload.get('files')
    if not isinstance(entries, list):
        raise ManifestError('The host sent a malformed file list.')

    if len(entries) > protocol.MAX_MANIFEST_FILES:
        raise ManifestError('The host offered too many files (%d).' % len(entries))

    seen = set()
    clean = []
    total = 0

    for entry in entries:
        if not isinstance(entry, dict):
            raise ManifestError('The host sent a malformed file entry.')

        path = entry.get('path')
        if not isinstance(path, str) or not path:
            raise ManifestError('The host sent a file with no name.')

        # Full path validation against a throwaway root: this rejects traversal,
        # absolute paths, reserved names and forbidden extensions now, rather
        # than at write time when a mistake would already have cost us.
        try:
            identity.safe_join('/staging', path,
                               require_allowed_extension=require_allowed_extension)
        except identity.UnsafePathError as exc:
            raise ManifestError('The host offered an unsafe file %r (%s).'
                                % (path, exc))

        normalised = path.replace('\\', '/')

        # Compared case-insensitively: Windows filesystems are case-insensitive,
        # so 'foo.png' and 'FOO.png' are one file on disk. Treating them as
        # distinct would let the second overwrite the first *after* it had been
        # verified, and then leave commit() half-finished when the vanished
        # source could not be moved.
        key = normalised.lower()
        if key in seen:
            raise ManifestError('The host listed %r twice.' % path)
        seen.add(key)

        size = entry.get('size')
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ManifestError('The host sent an invalid size for %r.' % path)

        total += size
        if total > protocol.MAX_MANIFEST_TOTAL_BYTES:
            raise ManifestError(
                'The host offered more than %d MiB of files.'
                % (protocol.MAX_MANIFEST_TOTAL_BYTES // (1024 * 1024)))

        sha = entry.get('sha256')
        if not protocol.is_valid_hex(sha, 64):
            raise ManifestError('The host sent an invalid checksum for %r.' % path)

        clean.append({'path': normalised, 'size': size,
                      'sha256': sha.lower()})

    return clean


def describe_transfer(entries, host_nick='the host', patch_id=''):
    """
    The one-line summary shown in the consent prompt.

    Deliberately concrete: who is sending, what, how many files and how big.
    A vague prompt trains users to click through it.
    """
    total = sum(entry['size'] for entry in entries)
    megabytes = total / (1024.0 * 1024.0)

    return ('%s wants to send you the game patch %r: %d files, %.1f MiB. '
            'Only data files are accepted - no program code.'
            % (host_nick, patch_id or 'unknown', len(entries), megabytes))


# ---------------------------------------------------------------------------
# Chunking (host side)
# ---------------------------------------------------------------------------

def chunk_count(size, chunk_bytes=protocol.MAX_CHUNK_BYTES):
    """
    How many chunks a file of `size` bytes needs. An empty file is one chunk, so
    the receiver still gets a frame for it and can complete the file.
    """
    if size <= 0:
        return 1
    return (size + chunk_bytes - 1) // chunk_bytes


def read_chunks(patch_dir, relative_path, chunk_bytes=protocol.MAX_CHUNK_BYTES):
    """
    Yields file_chunk payloads for one file.

    The path is validated against the patch directory even on the sending side:
    the request came from a peer, and a host serving `../../secrets.txt` because
    a client asked nicely is the same bug in the other direction.
    """
    absolute = identity.safe_join(patch_dir, relative_path)

    size = os.path.getsize(absolute)
    total = chunk_count(size, chunk_bytes)

    with open(absolute, 'rb') as handle:
        for index in range(total):
            data = handle.read(chunk_bytes)
            yield {
                'path': relative_path.replace('\\', '/'),
                'index': index,
                'total': total,
                'data': base64.b64encode(data).decode('ascii'),
            }


# ---------------------------------------------------------------------------
# Receiving (client side)
# ---------------------------------------------------------------------------

class TransferSession:
    """
    Receives a manifest's worth of files into a staging directory.

    The contract: nothing reaches the real patch directory until every file has
    been received and every hash matches. `commit()` is the only method that
    touches the destination, and it refuses to run while anything is outstanding.

    Usage:
        session = TransferSession(staging_root, entries, patch_id='NewerSMBW')
        for path in session.pending_paths():
            ... request it, then feed each chunk ...
            session.add_chunk(payload)
        session.commit(destination_dir)
    """

    def __init__(self, staging_root, entries, patch_id=''):
        self.staging_root = os.path.abspath(str(staging_root))
        self.patch_id = str(patch_id)
        self.entries = {entry['path']: dict(entry) for entry in entries}

        self._received = {}      # path -> bytes written
        self._handles = {}       # path -> open file handle
        self._expected = {}      # path -> chunk total, once known
        self._next_index = {}    # path -> next chunk index expected
        self._verified = set()
        self.failed = {}         # path -> reason

        os.makedirs(self.staging_root, exist_ok=True)

    # -- state --------------------------------------------------------------

    def pending_paths(self):
        return [path for path in self.entries if path not in self._verified]

    @property
    def is_complete(self):
        return not self.failed and len(self._verified) == len(self.entries)

    @property
    def total_bytes(self):
        return sum(entry['size'] for entry in self.entries.values())

    @property
    def received_bytes(self):
        return sum(self._received.values())

    def progress(self):
        total = self.total_bytes
        if total <= 0:
            return 1.0 if self.is_complete else 0.0
        return min(1.0, self.received_bytes / float(total))

    # -- receiving ----------------------------------------------------------

    def add_chunk(self, payload):
        """
        Accepts one file_chunk payload. Returns True when that file is complete
        and verified.

        Raises TransferError for anything the sender should not have sent: an
        unlisted path, a chunk out of order, more bytes than announced, or a
        hash mismatch. The caller should abort the transfer - a sender that got
        one of these wrong is not one to keep trusting.
        """
        path = str(payload.get('path', '')).replace('\\', '/')

        entry = self.entries.get(path)
        if entry is None:
            # Not in the manifest the user consented to. Refusing here is what
            # keeps consent meaningful.
            raise TransferError('The host sent a file that was not offered: %r'
                                % path)

        if path in self._verified:
            raise TransferError('The host sent %r again after it was complete.'
                                % path)

        index = payload.get('index')
        total = payload.get('total')
        if (isinstance(index, bool) or not isinstance(index, int)
                or isinstance(total, bool) or not isinstance(total, int)):
            raise TransferError('The host sent a malformed chunk for %r.' % path)

        known_total = self._expected.setdefault(path, total)
        if total != known_total:
            raise TransferError('The host changed the chunk count for %r.' % path)

        expected_index = self._next_index.get(path, 0)
        if index != expected_index:
            # In-order only. Out-of-order chunks would mean seeking in the
            # output file, and a sender that can choose offsets can write
            # arbitrary bytes at arbitrary positions.
            raise TransferError('The host sent chunk %d of %r out of order '
                                '(expected %d).' % (index, path, expected_index))

        try:
            data = base64.b64decode(str(payload.get('data', '')), validate=True)
        except (ValueError, TypeError):
            raise TransferError('The host sent unreadable data for %r.' % path)

        written = self._received.get(path, 0)
        if written + len(data) > entry['size']:
            raise TransferError(
                'The host sent more data than announced for %r '
                '(%d bytes, expected %d).'
                % (path, written + len(data), entry['size']))

        handle = self._handles.get(path)
        if handle is None:
            destination = identity.safe_join(self.staging_root, path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            handle = open(destination, 'wb')
            self._handles[path] = handle

        handle.write(data)
        self._received[path] = written + len(data)
        self._next_index[path] = index + 1

        if index + 1 < total:
            return False

        # Last chunk: close and verify.
        handle.close()
        self._handles.pop(path, None)
        self._verify(path, entry)
        return True

    def _verify(self, path, entry):
        destination = identity.safe_join(self.staging_root, path)

        actual_size = os.path.getsize(destination)
        if actual_size != entry['size']:
            self.failed[path] = 'size mismatch'
            raise VerificationError(
                '%r arrived with %d bytes but %d were announced.'
                % (path, actual_size, entry['size']))

        actual_hash = sha256_file(destination)
        if actual_hash != entry['sha256']:
            self.failed[path] = 'checksum mismatch'
            raise VerificationError(
                '%r failed its checksum. The file was corrupted or tampered '
                'with in transit.' % path)

        self._verified.add(path)

    # -- finishing ----------------------------------------------------------

    def commit(self, destination_dir):
        """
        Moves the verified files into place.

        Refuses unless every listed file is present and verified: a
        half-installed patch is worse than none, because the user would see
        wrong graphics with no obvious cause.
        """
        if self.failed:
            raise VerificationError(
                'Not installing the patch: %d file(s) failed verification.'
                % len(self.failed))

        if not self.is_complete:
            missing = len(self.entries) - len(self._verified)
            raise TransferError(
                'Not installing the patch: %d file(s) never arrived.' % missing)

        # A transferred patch must not claim to have files that were excluded.
        self._drop_untransferred_declarations()

        destination_root = os.path.abspath(str(destination_dir))
        os.makedirs(destination_root, exist_ok=True)

        moved = []
        for path in sorted(self.entries):
            source = identity.safe_join(self.staging_root, path)
            # Validate against the *destination* root too. The staging path was
            # already checked, but the destination is a different root and the
            # check is cheap.
            target = identity.safe_join(destination_root, path)

            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(source, target)
            moved.append(target)

        self.cleanup()
        return moved

    def _drop_untransferred_declarations(self):
        """
        Removes main.xml entries pointing at files the transfer excluded.

        Both shipped patches declare `<file name="sprites" path="sprites.py"/>`,
        and sprites.py is exactly what may never be transferred. main.xml itself
        *is* transferred, so without this the installed patch declares a file
        that is not there, and ReggieGameDefinition.InitFromName opens it
        unconditionally and raises FileNotFoundError - the patch then fails to
        load at all. That is the second error from Zement and Mone's test.

        Copying someone else's sprites.py instead was considered and rejected:
        it would execute one patch's drawing code under another patch's name,
        producing wrong sprite images with nothing on screen to explain why. A
        patch with no sprites.py is a patch whose sprites draw with default
        images, which is the documented and honest cost of a data-only transfer.

        Best-effort: a patch that cannot be rewritten is still installed, since
        the alternative is discarding a verified transfer over its manifest.
        """
        main_xml = self.entries.get('main.xml')
        if main_xml is None:
            return

        try:
            path = identity.safe_join(self.staging_root, 'main.xml')
        except identity.UnsafePathError:
            return

        try:
            with open(path, 'r', encoding='utf-8') as handle:
                text = handle.read()
        except OSError:
            return

        # Drop any <file> element whose path was not part of the transfer.
        # Regex rather than a parse-and-serialise, deliberately: main.xml is
        # hand-edited by patch authors, and rewriting it through ElementTree
        # would silently reformat comments, attribute order and whitespace.
        transferred = set(self.entries)

        def keep(match):
            element = match.group(0)
            declared = re.search(r'path\s*=\s*"([^"]*)"', element)
            if declared is None:
                return element

            relative = declared.group(1).replace('\\', '/').lstrip('./')
            if relative in transferred:
                return element

            # Only drop declarations we know were excluded on purpose. A
            # <file> naming something absent for another reason is left alone
            # rather than quietly deleted.
            try:
                identity.check_transfer_extension(relative)
            except identity.UnsafePathError:
                return ''

            return element

        updated = re.sub(r'<file\b[^>]*/>', keep, text)

        if updated == text:
            return

        try:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(updated)
        except OSError:
            return

        # The file changed, so its manifest hash no longer describes it. That is
        # correct and deliberate - verification has already happened, against
        # what the host sent - but the entry is updated so nothing later
        # re-checks it against a stale digest.
        entry = self.entries['main.xml']
        entry['sha256'] = sha256_bytes(updated.encode('utf-8'))
        entry['size'] = len(updated.encode('utf-8'))

    def abort(self):
        """
        Closes any open handles and discards everything staged. Safe to call
        twice, and safe to call from an error path.
        """
        for handle in list(self._handles.values()):
            try:
                handle.close()
            except OSError:
                pass
        self._handles.clear()
        self.cleanup()

    def cleanup(self):
        """
        Removes the staging directory. Never raises: failing to tidy up must not
        mask the error that led here.
        """
        try:
            if os.path.isdir(self.staging_root):
                shutil.rmtree(self.staging_root, ignore_errors=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Deciding how to satisfy a patch requirement (client side)
# ---------------------------------------------------------------------------

def patch_requirement(room_info, catalog=None, allow_host_transfer=True,
                      base_dir='', extra_dirs=(), allow_catalog=True):
    """
    Works out whether the client can join, and how the patch should be obtained.

    `room_info` is the host's room_info payload; `catalog` is a CatalogManager
    (or anything with the same three methods), passed in rather than constructed
    so this stays testable without touching the network.

    Whether a patch is *installed* is answered from the filesystem, by
    find_installed_patch, not from the catalog: CatalogManager searches only
    reggiedata/patches, so a patch installed by the Patch Manager into
    assets/mods, or added as an external patch, would be reported missing on a
    machine that has it. The catalog is still authoritative for the different
    question of whether a patch is *available* to install.

    Returns {'source', 'patch_id', 'patch_version', 'reason', 'message'}, where
    `source` is one of SOURCE_LOCAL / SOURCE_CATALOG / SOURCE_HOST /
    SOURCE_UNAVAILABLE. The preference order is the spec's: local, then the
    Patch Manager, then a consent-gated host transfer.

    `allow_catalog` and `allow_host_transfer` are the client's own permissions,
    and both default to True so the full preference order applies. They are
    separate flags rather than one choice because the three useful settings are
    "try both", "catalog only" and "host only" - with a single flag, choosing
    the catalog silently forbade the host transfer even when the patch was not
    in the catalog at all.
    """
    patch_id = str((room_info or {}).get('patch_id', '') or '')
    patch_version = str((room_info or {}).get('patch_version', '') or '')

    if not patch_id:
        return {
            'source': SOURCE_LOCAL,
            'patch_id': '',
            'patch_version': '',
            'reason': '',
            'message': 'This session uses the base game; no patch is needed.',
        }

    installed = False
    installed_version = None

    local = find_installed_patch(patch_id, base_dir, extra_dirs)
    if local is not None:
        installed = True
        installed_version = local.get('version') or None

    if not installed and catalog is not None:
        # Fall back to the catalog's own view. It searches fewer places, so it
        # can only ever add a patch this missed, never contradict one it found.
        try:
            installed = bool(catalog.is_patch_installed(patch_id))
            if installed:
                installed_version = catalog.get_installed_patch_version(patch_id)
        except Exception:
            # A broken catalog must not stop someone joining; fall through to
            # treating the patch as absent.
            installed = False

    if installed:
        if not patch_version or not installed_version:
            # One side does not report a version. Accept it: refusing a join over
            # an unknown version would block the common case where a patch simply
            # has no version field.
            return {
                'source': SOURCE_LOCAL,
                'patch_id': patch_id,
                'patch_version': patch_version,
                'reason': '',
                'message': 'You already have the %s patch.' % patch_id,
            }

        try:
            comparison = catalog.compare_versions(installed_version, patch_version)
        except Exception:
            comparison = 0

        if comparison == 0:
            return {
                'source': SOURCE_LOCAL,
                'patch_id': patch_id,
                'patch_version': patch_version,
                'reason': '',
                'message': 'You already have the %s patch (version %s).'
                           % (patch_id, installed_version),
            }

        # Version differs. Prefer the catalog, since it is the trusted source -
        # but only where the client's settings permit it.
        return {
            'source': (SOURCE_CATALOG
                       if (allow_catalog and _in_catalog(catalog, patch_id))
                       else (SOURCE_HOST if allow_host_transfer
                             else SOURCE_UNAVAILABLE)),
            'patch_id': patch_id,
            'patch_version': patch_version,
            'reason': NEED_VERSION,
            'message': ('You have %s version %s, but the host is using %s.'
                        % (patch_id, installed_version, patch_version)),
        }

    if allow_catalog and _in_catalog(catalog, patch_id):
        return {
            'source': SOURCE_CATALOG,
            'patch_id': patch_id,
            'patch_version': patch_version,
            'reason': NEED_MISSING,
            'message': ('The %s patch can be installed from the Patch Manager.'
                        % patch_id),
        }

    if allow_host_transfer:
        return {
            'source': SOURCE_HOST,
            'patch_id': patch_id,
            'patch_version': patch_version,
            'reason': NEED_MISSING,
            'message': ('You do not have the %s patch. The host can send its '
                        'data files, with your permission.' % patch_id),
        }

    # Nothing is permitted. Say which choice caused it rather than blaming the
    # host: the setting is the *client's*, and the first message here read as
    # though the host had refused something it was never asked.
    if allow_catalog:
        message = ('You do not have the %s patch, and it is not in the Patch '
                   'Manager catalog. To accept it from the host instead, '
                   'change "Get a missing patch" in Preferences.' % patch_id)
    else:
        message = ('You do not have the %s patch, and your settings do not '
                   'allow getting it. Change "Get a missing patch" in '
                   'Preferences.' % patch_id)

    return {
        'source': SOURCE_UNAVAILABLE,
        'patch_id': patch_id,
        'patch_version': patch_version,
        'reason': NEED_MISSING,
        'message': message,
    }


def _in_catalog(catalog, patch_id):
    if catalog is None:
        return False
    try:
        return catalog.get_entry_by_name(patch_id) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Plugin state (never plugin code)
# ---------------------------------------------------------------------------

def plugin_state_hash(enabled_names):
    """
    A stable hash of which plugins are enabled.

    Per Zement: plugin *code* is never transferred - both peers are assumed to
    ship the same plugins for a given Reggie version, so only the enable/disable
    state matters. The host compares this hash and warns on a mismatch; it never
    tries to reconcile it by sending anything.
    """
    names = sorted({str(name).strip() for name in (enabled_names or ()) if str(name).strip()})
    return sha256_bytes('\n'.join(names).encode('utf-8'))


# ---------------------------------------------------------------------------
# Finding an installed patch
# ---------------------------------------------------------------------------

# Reggie can have a patch installed in three different places, and a peer that
# has one in a place we do not search looks exactly like a peer that does not
# have it at all. That is not hypothetical: it is the bug Zement hit in the
# first live test, where two machines both running the retail game could not
# agree that they matched.
#
#   1. reggiedata/patches - the classic location.
#   2. assets/mods        - where the Patch Manager installs.
#   3. anywhere on disk   - "Add external patch", recorded in QSettings under
#                           PatchPath_<gamepath>.
#
# CatalogManager.get_installed_patches() only ever looks at (1), so it is not
# usable as the collab answer to "do I have this patch".
PATCH_SEARCH_DIRS = (
    os.path.join('reggiedata', 'patches'),
    os.path.join('assets', 'mods'),
)


def _read_patch_main_xml(main_xml):
    """
    The (name, version) a patch declares, or None if this is not a patch.

    Deliberately tolerant: a malformed main.xml somewhere in the search path
    must not stop a join, it just means that directory is not the patch we are
    looking for.
    """
    try:
        from xml.etree import ElementTree as etree

        root = etree.parse(main_xml).getroot()
    except Exception:
        return None

    name = root.get('name')
    if not name:
        return None

    return str(name), (root.get('version') or '')


def installed_patches(base_dir='', extra_dirs=()):
    """
    Every installed patch, as {name: {'path', 'version'}}.

    Keyed on the *name* declared in main.xml, never on the folder name. The two
    are not the same and cannot be made the same: the identical patch ships as
    'NewerSMBW' under reggiedata/patches and as 'Newer Super Mario Bros. Wii'
    under assets/mods, and an external patch can sit in a folder called
    anything at all. Only the declared name is a patch's identity.

    `extra_dirs` carries the external patch paths, which live in QSettings and
    therefore have to be passed in - this module stays Qt-free.

    Earlier search directories win, so a patch present in both directories
    resolves to reggiedata/patches, matching what CatalogManager reports.
    """
    found = {}

    roots = [os.path.join(str(base_dir), relative) if base_dir else relative
             for relative in PATCH_SEARCH_DIRS]

    for root in roots:
        if not os.path.isdir(root):
            continue

        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue

        for entry in entries:
            directory = os.path.join(root, entry)
            main_xml = os.path.join(directory, 'main.xml')
            if not os.path.isfile(main_xml):
                continue

            declared = _read_patch_main_xml(main_xml)
            if declared is None:
                continue

            name, version = declared
            found.setdefault(name, {'path': directory, 'version': version})

    # External patches are listed last so an explicitly installed copy takes
    # precedence over one the user merely pointed at.
    for directory in (extra_dirs or ()):
        if not directory:
            continue

        main_xml = os.path.join(str(directory), 'main.xml')
        if not os.path.isfile(main_xml):
            continue

        declared = _read_patch_main_xml(main_xml)
        if declared is None:
            continue

        name, version = declared
        found.setdefault(name, {'path': str(directory), 'version': version})

    return found


def find_installed_patch(patch_id, base_dir='', extra_dirs=()):
    """
    The installed patch declaring `patch_id`, or None.

    This is the collab answer to "do I have the host's patch", and it is
    deliberately not CatalogManager's, which searches one of the three
    locations.
    """
    if not patch_id:
        return None

    return installed_patches(base_dir, extra_dirs).get(str(patch_id))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def patches_directory(base_dir=''):
    return os.path.join(str(base_dir), PATCHES_RELATIVE_DIR) if base_dir \
        else PATCHES_RELATIVE_DIR


def folder_name_for_patch(patch_id):
    """
    A directory name for a patch id.

    A patch id is a *display name* from main.xml, not a filename, and the two
    are routinely different: 'New Super Mario Bros. Wii: The Prankster Comets'
    is an ordinary patch name and an impossible Windows directory name. Mone's
    transfer got as far as installing and then failed with WinError 267 for
    exactly that reason.

    The Patch Manager never had this problem because it takes its folder name
    from the repository URL and falls back to the name with spaces removed
    (patch_manager_dialog._download_method1). This is the equivalent for a
    transfer, where there is no URL to take.

    Characters Windows forbids are replaced rather than dropped, so two patches
    whose names differ only in punctuation cannot collapse onto one folder. The
    result is still validated as a single safe component, because sanitising is
    a convenience and safe_component is the guarantee.
    """
    # NOT stripped first: a trailing dot or space is one of the things this
    # function must refuse, and stripping would hide it from the check below.
    text = str(patch_id or '')
    if not text.strip():
        raise identity.UnsafePathError('empty patch id')

    # Refuse anything path-shaped BEFORE sanitising, rather than repairing it.
    # Sanitising first would quietly turn '../evil' into 'evil' and accept it -
    # rewriting hostile input into something valid instead of rejecting it,
    # which is the wrong instinct even where the result lands somewhere
    # harmless. A patch id is a display name, and one shaped like a path is not
    # a name whose intent we should be guessing.
    #
    # The line is drawn by *position*, which is what separates the two cases
    # this function has to serve. A colon inside a name is punctuation
    # ('NSMBW: The Prankster Comets') and is repaired; a colon in second place
    # is a drive letter ('C:x') and is refused. Likewise a trailing dot or
    # space, which Windows silently strips - repairing those would let two
    # different ids collapse onto one folder.
    if any(character in text for character in '/\\') or '..' in text:
        raise identity.UnsafePathError(
            'patch id %r looks like a path, not a name' % (patch_id,))

    if re.match(r'^[A-Za-z]:', text):
        raise identity.UnsafePathError(
            'patch id %r looks like a drive path, not a name' % (patch_id,))

    # Trailing dots and spaces are refused rather than trimmed. Windows strips
    # both silently, so repairing them would let two ids that differ only there
    # collapse onto one folder - and 'evil.py.' slipping past an extension check
    # is the classic form of that trick. Nothing legitimate is lost: no patch is
    # named with a trailing space.
    if text != text.rstrip(' .'):
        raise identity.UnsafePathError(
            'patch id %r ends with a dot or space' % (patch_id,))

    # Leading whitespace is only trimmed, since it cannot collide with anything
    # Windows does and a padded display name is ordinary sloppiness.
    text = text.lstrip()

    if '\x00' in text:
        raise identity.UnsafePathError('patch id contains a null byte')

    for character in ':*?"<>|':
        text = text.replace(character, '-')

    # Collapse runs and trim what Windows would silently strip anyway.
    text = re.sub(r'-{2,}', '-', text)
    text = text.strip(' .-')

    # Spaces are legal but awkward; the Patch Manager's own fallback removes
    # them, so a transferred patch lands with a folder shaped like a
    # manually installed one.
    text = text.replace(' ', '')

    if not text:
        raise identity.UnsafePathError(
            'patch id %r has no usable characters for a folder name'
            % (patch_id,))

    return identity.safe_component(text)


def patch_directory(patch_id, base_dir=''):
    """
    The directory a patch with this id should be installed into.

    The id is turned into a filename first (see folder_name_for_patch) and then
    validated - a patch id arrives from the network, so it is not a directory
    name until it has been both sanitised and checked.
    """
    return os.path.join(patches_directory(base_dir),
                        folder_name_for_patch(patch_id))


def staging_directory(base_dir=''):
    return os.path.join(patches_directory(base_dir), STAGING_DIRNAME)
