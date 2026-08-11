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
    levelSaved = QtCore.pyqtSignal(dict)          # the host saved the level
    # session id, area, want_file. want_file asks for the level *file* rather
    # than a rebuilt snapshot - the client's way of saying it is ready to
    # receive one, which is why the join publication is answered here rather
    # than pushed at 'join' (Block C - B3, round 2, R2).
    snapshotRequested = QtCore.pyqtSignal(str, int, bool)
    levelSwitchRequested = QtCore.pyqtSignal(str, int)  # level name, area

    # A Full client is *asking* the host to move the session (Block C - B3,
    # phase 3d). Separate from levelSwitchRequested, which means "the session
    # has moved, load it": this one has not been decided yet, and the host has
    # to know who asked in order to answer them. session id, level, area.
    levelSwitchProposed = QtCore.pyqtSignal(str, str, int)
    # reason, op_id. op_id names *what* was refused: an operation id for a
    # refused edit, or the message type for a refused request. A refused switch
    # proposal has to be distinguishable from a refused edit, because the two
    # want opposite responses - an edit was applied optimistically and needs a
    # resync, a proposal was never applied and needs the waiting caller
    # released (Block C - B3, phase 3d).
    operationRejected = QtCore.pyqtSignal(str, str)

    # Patch transfer. Host side: a peer needs the patch, or wants one file of
    # it. Client side: the manifest arrived, a chunk arrived, the host finished.
    # session id, patch id, assets_only. assets_only is True when the client has
    # the patch already and wants only the host's Stage and Texture (Block C -
    # B3, round 2).
    patchNeeded = QtCore.pyqtSignal(str, str, bool)
    fileRequested = QtCore.pyqtSignal(str, str, str)   # session id, path, kind

    # Host side: a client reported its transfer finished (or failed). The host
    # holds level publications back while a peer is mid-transfer, so it needs to
    # know when that ends. session id, ok.
    peerTransferFinished = QtCore.pyqtSignal(str, bool)

    # Host side: a peer finished loading a level the host published (R3). The
    # host holds edits back until every peer has this, so that nobody is edited
    # around while their scene is still being built.
    # session id, level, ok.
    peerLevelLoaded = QtCore.pyqtSignal(str, str, bool)
    manifestReceived = QtCore.pyqtSignal(dict)
    fileChunkReceived = QtCore.pyqtSignal(dict)
    transferFinished = QtCore.pyqtSignal(bool, str)    # ok, error

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

            # The host has to answer this, or the client sits on an empty level
            # forever. Building the snapshot reads the scene, so it must happen
            # on the main thread - hence a signal rather than a direct call.
            self.signals.snapshotRequested.emit(
                getattr(participant, 'session_id', ''),
                int(data.get('area', 1) or 1),
                bool(data.get('want_file', False)))

        elif kind == 'area_switch':
            # A client is *asking*; the host decides (Block C - B3, phase 3d).
            # This used to load straight away, which is why the host's unsaved
            # work could be walked over by a client's switch. Answering it
            # touches the editor and may open a dialog, so it must reach the
            # main thread before anything happens.
            self.signals.statusMessage.emit(
                '%s asked to change the level or area.' % nick)
            self.signals.levelSwitchProposed.emit(
                str(getattr(participant, 'session_id', '') or ''),
                str(data.get('level', '') or ''),
                int(data.get('area', 1) or 1))

        elif kind == 'op_error':
            self.signals.errorOccurred.emit(
                'A change from %s could not be applied: %s'
                % (nick, data.get('error', '')))

        elif kind == 'patch_need':
            # Building a manifest walks the patch directory, so it belongs on
            # the main thread with the rest of the file work - the same reason
            # snapshot_request is a signal rather than a direct call.
            assets_only = bool(data.get('assets_only', False))

            self.signals.statusMessage.emit(
                '%s needs the %s game data.' % (nick, data.get('patch_id', ''))
                if assets_only
                else '%s needs the %s patch.' % (nick,
                                                 data.get('patch_id', '')))
            self.signals.patchNeeded.emit(
                getattr(participant, 'session_id', ''),
                str(data.get('patch_id', '') or ''),
                assets_only)

        elif kind == 'file_req':
            self.signals.fileRequested.emit(
                getattr(participant, 'session_id', ''),
                str(data.get('path', '') or ''),
                str(data.get('kind', '') or 'patch'))

        elif kind == 'file_denied':
            # A peer asking for something outside its manifest. Shown, not
            # hidden: it is either a bug or a probe, and both are worth seeing.
            self.signals.statusMessage.emit(
                '%s asked for a file that was not offered (%s).'
                % (nick, data.get('path', '')))

        elif kind == 'level_loaded':
            # The peer has the level open and is safe to edit around again (R3).
            ok = bool(data.get('ok', True))
            if not ok:
                self.signals.statusMessage.emit(
                    '%s could not open %s and is still on the previous level.'
                    % (nick, data.get('level', 'the level')))

            self.signals.peerLevelLoaded.emit(
                str(getattr(participant, 'session_id', '') or ''),
                str(data.get('level', '') or ''), ok)

        elif kind == 'file_done':
            ok = bool(data.get('ok', True))
            if ok:
                self.signals.statusMessage.emit(
                    '%s finished downloading the patch.' % nick)
            else:
                self.signals.statusMessage.emit(
                    "%s could not download the patch: %s"
                    % (nick, data.get('error', 'unknown error')))

            # Either way this peer is no longer mid-transfer, so the host can
            # resume publishing levels to it. Emitted on failure too: a
            # transfer that failed is still over, and holding publications back
            # for a peer that will never report success would silence it for
            # the rest of the session.
            self.signals.peerTransferFinished.emit(
                str(getattr(participant, 'session_id', '') or ''), ok)

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
                data.get('reason', 'The host rejected a change.'),
                str(data.get('op_id', '') or ''))

        elif kind == protocol.T_AREA_SWITCH:
            # The host moved everyone. Same signal as the host-side request, so
            # the controller has one place that loads a level.
            self.signals.levelSwitchRequested.emit(
                str((data or {}).get('level', '') or ''),
                int((data or {}).get('area', 1) or 1))

        elif kind == protocol.T_OP:
            self.signals.operationReceived.emit(dict(data or {}), '')

        elif kind == 'presence':
            # ClientSession gives presence its own event so the sender survives
            # (see its handle_message). Keyed on 'presence' rather than
            # T_PRESENCE because it no longer falls through the generic branch
            # that emits raw message types.
            self.signals.presenceReceived.emit(
                dict((data or {}).get('payload') or {}),
                str((data or {}).get('sender', '') or ''))

        elif kind == protocol.T_SNAPSHOT:
            self.signals.snapshotReceived.emit(dict(data or {}))

        elif kind == 'manifest':
            self.signals.manifestReceived.emit(dict(data or {}))

        elif kind == 'file_chunk':
            self.signals.fileChunkReceived.emit(dict(data or {}))

        elif kind == 'saved':
            self.signals.levelSaved.emit(dict(data or {}))

        elif kind == 'file_done':
            # Sent by the host both to refuse a transfer and to end one, so the
            # 'ok' flag is what distinguishes them, not the arrival.
            self.signals.transferFinished.emit(
                bool((data or {}).get('ok', True)),
                str((data or {}).get('error', '') or ''))

    def on_client_disconnect(self, connection, reason):
        self.signals.disconnected.emit(reason or 'The connection closed.')
