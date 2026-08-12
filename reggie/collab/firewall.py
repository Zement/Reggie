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
#
# Raised from 0.35 s (2026-08-12). At boot the window has only just been shown
# and the filtering engine is still settling, and a socket that is gone again
# within a third of a second can be classified without the dialog ever
# appearing. This runs on a daemon thread and blocks nothing, so a longer hold
# costs the user nothing at all.
_LISTEN_SECONDS = 1.5


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

    Listens on IPv4 **and**, where possible, IPv6 - which is the fix rather than
    a refinement. Binding 0.0.0.0 alone listens on IPv4 only, and Windows scopes
    its firewall decision per address family: on a current Windows 11 stack the
    v4-only listen can be classified without the dialog ever appearing. That is
    the symptom Zement reported - no prompt at boot, but one from the Patch
    Manager, which makes an outbound HTTPS request Windows always notices
    (2026-08-12).

    The IPv4 socket is opened *first* and its failure is what aborts the
    trigger, because that is the one ServerTransport itself binds
    (transport.py, AF_INET). A hosting Reggie therefore holds 0.0.0.0 and this
    correctly stands down - which matters, since on Windows a dual-stack '::'
    listener does **not** reserve the v4 wildcard, so leading with IPv6 would
    have let the trigger fire in the middle of somebody's session.

    IPv6 is strictly an addition: if it cannot be had, the trigger still does
    what it always did.
    """
    listeners = []
    families = []
    try:
        # No SO_REUSEADDR, matching ServerTransport: on Windows it implies
        # SO_REUSEPORT semantics and would let this trigger quietly share a
        # port with something else already using it.
        primary = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listeners.append(primary)
        primary.bind((bind_host or '0.0.0.0', int(port)))
        primary.listen(1)
        families.append('ipv4')

        # V6ONLY *on*, deliberately: the v4 wildcard is already bound above, and
        # a dual-stack socket would collide with it. This one covers v6 only.
        if bind_host in ('', '0.0.0.0'):
            try:
                secondary = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                listeners.append(secondary)
                secondary.setsockopt(socket.IPPROTO_IPV6,
                                     socket.IPV6_V6ONLY, 1)
                secondary.bind(('::', int(port)))
                secondary.listen(1)
                families.append('ipv6')
            except OSError as exc:
                # A host with IPv6 disabled by policy still gets its prompt.
                debuglog.log('firewall', 'ipv6 listen unavailable',
                             port=port, error=str(exc))

        # The families are logged because they are the whole difference between
        # a prompt appearing and not appearing. If this misbehaves again the log
        # says which sockets were actually opened rather than leaving it to be
        # guessed at.
        debuglog.log('firewall', 'listening to provoke the prompt', port=port,
                     families='+'.join(families), seconds=_LISTEN_SECONDS)

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
        for listener in listeners:
            try:
                listener.close()
            except OSError:
                pass
