"""
Provoking the Windows firewall prompt at boot (Block C - B1).

The problem this solves, in Zement's words: the Patch Manager fails on the run
that first triggers the firewall dialog, and works on the next run once a rule
exists. The same trap is waiting for collaboration, where the failure would be
harder to diagnose because a blocked *inbound* connection just looks like a
peer that never arrives.

Windows shows its prompt when a program first listens on a socket, not when it
connects out. So the trigger is simply to bind and listen briefly at startup,
while the user is looking at a window that has just opened and a prompt is
expected, rather than in the middle of hosting a session.

What this deliberately does NOT do:

- It does not add, modify or delete firewall rules. Writing a rule needs
  administrator rights, and a level editor that asks for elevation at boot -
  or worse, quietly punches a hole - is not something a user should have to
  trust. The prompt lets the user decide, which is the correct model.
- It does not block startup. The listen happens on a daemon thread and the
  socket is closed immediately; if anything fails, the editor carries on.
- It does not accept connections. The socket listens for a moment and closes
  without ever calling accept(), so nothing can connect during the trigger.
- It does nothing at all on Linux and macOS, where no such prompt exists.
  (macOS has its own application firewall, but it prompts on first listen too,
  and this same code path is harmless there if it is ever enabled.)

The trigger binds the collaboration port so the rule Windows creates covers
the port collaboration will actually use.
"""

import os
import socket
import threading

from reggie.collab import debuglog


# How long to hold the listening socket open. Long enough for Windows to notice
# the listen and raise its prompt, short enough to be invisible.
_LISTEN_SECONDS = 0.35


def is_supported():
    """
    Whether provoking a firewall prompt makes sense on this platform.
    """
    return os.name == 'nt'


def trigger(port, bind_host='0.0.0.0', blocking=False):
    """
    Briefly listens on `port` so the OS firewall prompts the user now.

    Returns immediately by default, doing the work on a daemon thread: a
    firewall prompt is modal to the user, not to us, and blocking startup on it
    would freeze the editor behind a dialog the user may not have noticed.

    Returns the thread when non-blocking, or True/False for the blocking form.
    """
    if not is_supported():
        return False

    if blocking:
        return _listen_briefly(port, bind_host)

    thread = threading.Thread(
        target=_listen_briefly, args=(port, bind_host),
        name='collab-firewall-trigger', daemon=True)
    thread.start()
    return thread


def _listen_briefly(port, bind_host):
    """
    Binds, listens, waits, closes. Never accepts a connection.
    """
    listener = None
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # No SO_REUSEADDR, matching ServerTransport: on Windows it implies
        # SO_REUSEPORT semantics and would let this trigger quietly share a
        # port with something else already using it.
        listener.bind((bind_host, int(port)))
        listener.listen(1)

        debuglog.log('firewall', 'listening to provoke the prompt', port=port)

        # A plain sleep, not an accept(): we want the listening state to exist
        # for a moment, not to talk to anybody.
        threading.Event().wait(_LISTEN_SECONDS)
        return True
    except OSError as exc:
        # The port being in use is the common and harmless case - another Reggie
        # is hosting, which means a rule already exists anyway.
        debuglog.log('firewall', 'trigger skipped', port=port, error=str(exc))
        return False
    finally:
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
