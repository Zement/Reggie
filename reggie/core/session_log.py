"""
Temporary session logging: a copy of the terminal output on disk.

**This is scaffolding, not architecture.** It exists so the Block C
collaboration testing is diagnosable, and it is meant to be deleted when the
universal logging block replaces the ~500 scattered print() calls with a real
`logging` setup, a verbosity preference and an in-app viewer. Two reasons it is
worth having in the meantime:

- a frozen build has no terminal at all, so every one of those print() calls is
  invisible in exactly the builds that are hardest to debug;
- a terminal that has scrolled, or been closed, takes the evidence with it -
  which is what happened with the shutdown crash, where the useful output was
  gone by the time anyone looked.

Deliberately small: it tees stdout and stderr to a file and does nothing else.
No levels, no formatting, no configuration. Anything more would be building the
thing it is standing in for.
"""

import os
import sys
import time


# The active tees, so writing can be turned off again and the file closed.
_tees = []


def log_directory():
    """
    Where logs go: <application root>/logs.

    The root comes from io.misc.module_path() rather than this file's location,
    because in a PyInstaller build __file__ points inside the temporary _MEIPASS
    extraction directory, which is deleted when the program exits - a log
    written relative to it would vanish with the process that needed it.

    Returns '' when no writable directory can be found. A log location is never
    worth failing a launch over.
    """
    try:
        from reggie.io.misc import module_path

        root = module_path() or os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..'))

        directory = os.path.join(root, 'logs')
        os.makedirs(directory, exist_ok=True)

        # Confirmed writable rather than assumed: makedirs succeeds on an
        # existing read-only folder, and discovering that at the first write
        # would lose the log silently.
        if os.access(directory, os.W_OK):
            return directory
    except Exception:
        pass

    return ''


class _Tee(object):
    """
    Writes to the original stream and to the log file.

    Never lets a logging problem break the program it is logging: a failed write
    to the file is dropped, and the real stream is always written first so that
    output is not lost to a logging fault.
    """

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle

    def write(self, text):
        # The real stream first, so console output survives whatever the file
        # does. In a frozen build stdout can be None, hence the guard.
        if self._stream is not None:
            try:
                self._stream.write(text)
            except Exception:
                pass

        try:
            self._handle.write(text)
        except Exception:
            pass

        return len(text) if text else 0

    def flush(self):
        for target in (self._stream, self._handle):
            if target is None:
                continue
            try:
                target.flush()
            except Exception:
                pass

    def isatty(self):
        # Asked by code deciding whether to emit colour. Answering for the real
        # stream keeps that decision the same as it would be without the tee.
        try:
            return bool(self._stream is not None and self._stream.isatty())
        except Exception:
            return False

    def fileno(self):
        # Some libraries want a real descriptor. Give them the console's, not
        # the log's, so a subprocess inherits what it would have inherited.
        if self._stream is None:
            raise OSError('no file descriptor')
        return self._stream.fileno()

    def __getattr__(self, name):
        # Anything else (encoding, errors, buffer, ...) comes from the real
        # stream, so this stays a stand-in rather than a partial reimplementation.
        return getattr(self._stream, name)


def start(filename='terminal.log'):
    """
    Starts copying stdout and stderr to logs/<filename>.

    Returns the path being written to, or '' if logging could not start.
    Idempotent: calling it twice does not stack two tees.
    """
    if _tees:
        return _tees[0][0]

    directory = log_directory()
    if not directory:
        return ''

    path = os.path.join(directory, filename)

    try:
        # Appended rather than truncated, so a crash-and-restart cycle keeps the
        # run that crashed - which is usually the interesting one. Line buffered
        # so a hard crash still leaves everything written up to that point.
        handle = open(path, 'a', buffering=1, encoding='utf-8', errors='replace')
    except Exception:
        return ''

    try:
        handle.write('\n===== Reggie started %s =====\n'
                     % time.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass

    for name in ('stdout', 'stderr'):
        original = getattr(sys, name, None)
        try:
            setattr(sys, name, _Tee(original, handle))
            _tees.append((path, name, original, handle))
        except Exception:
            pass

    return path if _tees else ''


def stop():
    """
    Restores the original streams and closes the file.

    Safe to call when nothing was started.
    """
    handle = None

    while _tees:
        _path, name, original, handle = _tees.pop()
        try:
            setattr(sys, name, original)
        except Exception:
            pass

    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def write_session_chat(lines, role=''):
    """
    Writes a collaboration session's chat to its own dated file.

    Separate from the terminal log on purpose: the chat is the human record of
    what people said and decided during a session, and burying it in a stream of
    boot diagnostics makes it unreadable. Returns the path written, or ''.

    `lines` is the chat as plain text - the caller converts, because only it
    knows whether it holds a widget, a list, or markup. `role` is 'host' or
    'client', which is what distinguishes two logs of the same session.
    """
    text = lines if isinstance(lines, str) else '\n'.join(str(l) for l in lines)
    if not text.strip():
        # An empty chat is not worth a file; a session where nobody spoke would
        # otherwise leave a trail of empty logs.
        return ''

    directory = log_directory()
    if not directory:
        return ''

    stamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    name = 'chat_%s.log' % stamp
    path = os.path.join(directory, name)

    try:
        with open(path, 'w', encoding='utf-8', errors='replace') as handle:
            handle.write('Reggie collaboration chat\n')
            handle.write('Session ended %s\n'
                         % time.strftime('%Y-%m-%d %H:%M:%S'))
            if role:
                handle.write('Logged by the %s\n' % role)
            handle.write('\n')
            handle.write(text)
            if not text.endswith('\n'):
                handle.write('\n')
    except Exception:
        return ''

    return path
