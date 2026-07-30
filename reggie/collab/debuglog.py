"""
Diagnostic logging for collaboration sessions (Block C - B1).

Exists because the interesting collaboration bugs are the ones that happen on
somebody else's machine, once every few tries, between two processes. Reading a
log beats reproducing that by description.

Off by default. When enabled it writes one line per event to a file in the
user's application data directory, with a monotonic timestamp so the ordering
of two processes' logs can be compared even though their wall clocks differ.

Never logs anything secret: not the session secret, not the join code, not the
authentication proof or nonce. Certificate fingerprints are truncated, which is
enough to tell two hosts apart without publishing the identity a pin is built
on. This matters because the natural thing for a user to do with a log is paste
it into a chat window.
"""

import os
import threading
import time


_lock = threading.Lock()
_handle = None
_path = ''
_enabled = False
_start = time.monotonic()

MAX_BYTES = 4 * 1024 * 1024


def is_enabled():
    return _enabled


def log_path():
    return _path


def enable(directory, filename=''):
    """
    Starts logging to `directory`/`filename`. Returns the path, or '' on
    failure - logging must never be the reason a session cannot start.

    The default filename carries the process id, because the common case is two
    Reggie instances on one machine and a shared file interleaves them: their
    timestamps are monotonic per process, so the merged ordering is misleading
    exactly where it matters. One file per process keeps each timeline honest.
    """
    global _handle, _path, _enabled, _start

    disable()

    if not filename:
        filename = 'collab_debug_%d.log' % os.getpid()

    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, filename)

        # Truncate a log that has grown without bound rather than rotating:
        # this is a debugging aid, and the recent past is the useful part.
        if os.path.isfile(path) and os.path.getsize(path) > MAX_BYTES:
            os.remove(path)

        handle = open(path, 'a', encoding='utf-8', errors='replace')
    except Exception:
        return ''

    with _lock:
        _handle = handle
        _path = path
        _enabled = True
        _start = time.monotonic()

    log('session', 'logging started', pid=os.getpid(),
        at=time.strftime('%Y-%m-%d %H:%M:%S'))
    return path


def disable():
    global _handle, _enabled

    with _lock:
        handle = _handle
        _handle = None
        _enabled = False

    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def log(category, message, **fields):
    """
    Writes one event. Safe to call from any thread and when disabled.

    Field values are stringified and truncated: a log line must not become a
    dump of a level's contents.
    """
    if not _enabled:
        return

    parts = ['%8.3f' % (time.monotonic() - _start),
             '%-10s' % str(category)[:10],
             str(message)]

    for name in sorted(fields):
        value = fields[name]
        text = str(value)
        if len(text) > 120:
            text = text[:117] + '...'
        parts.append('%s=%s' % (name, text))

    line = ' '.join(parts) + '\n'

    with _lock:
        handle = _handle
        if handle is None:
            return
        try:
            handle.write(line)
            handle.flush()      # a crash must not cost the last lines
        except Exception:
            pass


def short_fingerprint(fingerprint):
    """
    A fingerprint prefix, for telling hosts apart in a log without recording the
    value a certificate pin is derived from.
    """
    text = str(fingerprint or '')
    return text[:12] + '...' if len(text) > 12 else text
