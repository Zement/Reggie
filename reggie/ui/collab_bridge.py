"""
Qt bridge between the collaboration threads and the editor's main thread.

Everything in `reggie/collab/` is deliberately Qt-free, and its callbacks fire on
transport reader threads. Touching a QGraphicsScene or a widget from those threads
is undefined behaviour - in practice it either corrupts the scene or aborts the
process, and it does so intermittently, which is the worst kind of bug to chase.

This module is the single crossing point. It owns one QObject whose signals are
emitted from the worker threads; because the receiver lives on the main thread,
Qt queues the delivery automatically, so every slot runs on the main thread. Two
rules follow, and they are the whole contract:

1. Nothing in `reggie/collab/` may import Qt.
2. Nothing outside this module may touch the level, the scene, or a widget from a
   collab callback.

`sync.apply_remote()` in particular must only ever be called from a slot here.
"""

from PyQt6 import QtCore

from reggie.collab import protocol


class CollabSignals(QtCore.QObject):
    """
    Thread-safe fan-out from the collab layer to the UI.

    Emitted from reader threads, delivered on the main thread. Payloads are plain
    dicts and strings - never live level items - so nothing can be mutated in
    flight between the emit and the delivery.
    """

    # Session lifecycle
    connected = QtCore.pyqtSignal(dict)          # room_info
    roomInfoChanged = QtCore.pyqtSignal(dict)    # room_info, after a host change
    disconnected = QtCore.pyqtSignal(str)        # reason
    rejected = QtCore.pyqtSignal(str)            # reason
    hostingStarted = QtCore.pyqtSignal(str, int)  # join code, port
    hostingStopped = QtCore.pyqtSignal()

    # Roster and chat
    rosterChanged = QtCore.pyqtSignal(list)      # [participant dicts]
    chatReceived = QtCore.pyqtSignal(str, str, str)  # nick, text, kind
    roleChanged = QtCore.pyqtSignal(str)         # our new role

    # Level state
    operationReceived = QtCore.pyqtSignal(dict, str)   # op payload, sender id
    presenceReceived = QtCore.pyqtSignal(dict, str)    # presence payload, sender
    snapshotReceived = QtCore.pyqtSignal(dict)
    operationRejected = QtCore.pyqtSignal(str)         # reason

    # Anything worth showing in the status window that is not chat.
    statusMessage = QtCore.pyqtSignal(str)
    errorOccurred = QtCore.pyqtSignal(str)


class CollabBridge(QtCore.QObject):
    """
    Holds the signal object and translates collab-layer callbacks into signal
    emissions.

    Deliberately thin: it decides nothing. Policy lives in session.py (host side)
    and the controller (UI side); this only changes threads.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = CollabSignals()

    # -- host-side session events ------------------------------------------

    def on_host_event(self, kind, data):
        """
        Wired to HostSession.on_event. Runs on a reader thread.
        """
        participant = data.get('participant')
        nick = getattr(participant, 'nick', '') if participant is not None else ''

        if kind == 'chat':
            self.signals.chatReceived.emit(
                nick, data.get('text', ''),
                data.get('kind', protocol.CHAT_KIND_USER))

        elif kind == 'join':
            self.signals.statusMessage.emit('%s joined.' % nick)

        elif kind == 'leave':
            self.signals.statusMessage.emit('%s left.' % nick)

        elif kind == 'timeout':
            self.signals.statusMessage.emit('%s timed out.' % nick)

        elif kind == 'kick':
            self.signals.statusMessage.emit('%s was removed.' % nick)

        elif kind == 'ban':
            self.signals.statusMessage.emit('%s was banned.' % nick)

        elif kind == 'role_changed':
            self.signals.statusMessage.emit(
                '%s is now %s.' % (nick, data.get('role', '')))

        elif kind == 'op_denied':
            self.signals.statusMessage.emit(
                '%s tried to make a change their role does not allow (%s).'
                % (nick, data.get('kind', '')))

        elif kind == 'auth_failed':
            # Worth surfacing: repeated entries here are someone guessing.
            self.signals.statusMessage.emit(
                'A connection from %s was refused.' % (data.get('address', '?')))

        elif kind == 'presence':
            self.signals.presenceReceived.emit(
                dict(data.get('payload') or {}),
                getattr(participant, 'session_id', ''))

        elif kind == 'snapshot_request':
            self.signals.statusMessage.emit('%s is loading the level.' % nick)

        elif kind == 'op_error':
            self.signals.errorOccurred.emit(
                'A change from %s could not be applied: %s'
                % (nick, data.get('error', '')))

    def on_host_roster(self, participants):
        self.signals.rosterChanged.emit(
            [participant.to_roster_entry() for participant in participants])

    def on_host_op(self, participant, message, revision):
        """
        Wired to HostSession.on_op. Runs on a reader thread, so it may NOT apply
        the operation itself - it hands it to the main thread and optimistically
        accepts.

        The consequence is deliberate: a client op that turns out to be
        unapplicable is rejected a moment later by the controller rather than
        synchronously here. Applying level changes off the main thread to get a
        synchronous answer would trade a rare late rejection for intermittent
        scene corruption.
        """
        self.signals.operationReceived.emit(
            dict(message.get('p') or {}), getattr(participant, 'session_id', ''))
        return True

    # -- client-side session events ----------------------------------------

    def on_client_event(self, kind, data):
        """
        Wired to ClientSession.on_event. Runs on a reader thread.
        """
        if kind == 'connected':
            self.signals.connected.emit(dict(data.get('room_info') or {}))

            # auth_ok carries the roster, and the host does not broadcast another
            # one until membership changes. Without this the client shows an
            # empty participants list right after joining.
            roster = data.get('roster')
            if roster:
                self.signals.rosterChanged.emit(list(roster))

        elif kind == 'rejected':
            self.signals.rejected.emit(
                data.get('reason', 'The host refused the connection.'))

        elif kind == 'roster':
            self.signals.rosterChanged.emit(list(data.get('participants') or []))

        elif kind == 'chat':
            self.signals.chatReceived.emit(
                '', data.get('text', ''),
                data.get('kind', protocol.CHAT_KIND_USER))

        elif kind == 'role_changed':
            self.signals.roleChanged.emit(data.get('role', ''))

        elif kind == 'room_info':
            # Carries the payload, because the patch the host is using can
            # change mid-session and the client has to re-check it. A bare
            # notice would tell the user something changed without telling
            # anyone which patch is now required.
            self.signals.roomInfoChanged.emit(dict(data or {}))

        elif kind == 'removed':
            self.signals.disconnected.emit(
                data.get('reason', 'You were removed from the session.'))

        elif kind == 'bye':
            self.signals.disconnected.emit(
                data.get('reason', 'The host ended the session.'))

        elif kind == 'op_reject':
            self.signals.operationRejected.emit(
                data.get('reason', 'The host rejected a change.'))

        elif kind == protocol.T_OP:
            self.signals.operationReceived.emit(dict(data or {}), '')

        elif kind == protocol.T_PRESENCE:
            self.signals.presenceReceived.emit(dict(data or {}), '')

        elif kind == protocol.T_SNAPSHOT:
            self.signals.snapshotReceived.emit(dict(data or {}))

    def on_client_disconnect(self, connection, reason):
        self.signals.disconnected.emit(reason or 'The connection closed.')
