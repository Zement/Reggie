"""
The collaboration controller: what the editor actually talks to.

One object owns a session's whole lifetime - transport, session policy, the ref
map, the UI windows - so the rest of the editor needs a single handle and three
methods (`host`, `join`, `leave`) rather than knowledge of six modules.

**The threading rule this file exists to enforce.** transport and session invoke
their callbacks on reader threads. Every one of those is routed through
CollabBridge's signals, so the slots below run on the Qt main thread. Concretely:

- `sync.apply_remote()` and `sync.apply_snapshot()` are called ONLY from slots
  here, never from a callback.
- Callbacks assigned to session/transport do nothing but emit.

Getting this wrong does not fail loudly; it corrupts the scene occasionally. So
the rule is absolute rather than a preference.

The controller is also where the two roles diverge:

- A host owns a HostSession, mints item references, sequences operations, and
  answers snapshot requests.
- A client owns a ClientSession, receives references, and applies what it is
  told. It re-applies nothing locally that the host has not confirmed.
"""

import base64
import hmac
import os
import time

from PyQt6 import QtCore, QtWidgets

from reggie.collab import (
    broadcast, debuglog, discovery, files, identity, protocol, session, sync,
    transport,
)
# Aliased because host() takes a parameter called `upnp` - the key the setup
# dialog sends - which would otherwise shadow the module inside that method.
from reggie.collab import upnp as upnp_module
from reggie.core import globals_
from reggie.ui import collab_dialogs, collab_presence
from reggie.ui.collab_bridge import CollabBridge


# Cursor updates per second. Fast enough to look continuous, slow enough that a
# moving pointer is a trickle rather than a flood; transport caps it too.
PRESENCE_UPDATES_PER_SECOND = 20.0

# How often a held cursor position is flushed, so the final position of a
# gesture is never left stranded when the pointer stops.
PRESENCE_FLUSH_MS = 100


# Minimum gap between snapshot requests. A resync is usually triggered by a
# problem that will affect the next edit too, so without a floor here one broken
# reference produces a request per edit.
RESYNC_INTERVAL_SECONDS = 5.0

# Above this, a transfer is confirmed with the user before it starts (Block
# C - B3, round 2). Below it the download is automatic, on the same argument as
# the automatic save: it lands only in assets/mods/_collab/, which the client
# agreed to at join.
#
# 100 MB is Zement's figure and it sits above the realistic case (~28 MB for a
# patch with its Stage and Texture) and below the worst (~280 MB), so the dialog
# appears when the wait is long enough to be worth warning about and not
# otherwise.
ASSET_CONSENT_BYTES = 100 * 1024 * 1024

# Shown on a control the current session does not allow. Explains *why* it is
# unavailable, since a greyed-out menu item with no reason reads as a bug.
_PERMISSION_HINT = ('Not available during this collaboration session: the host '
                    'decides which level and patch everyone is editing.')

# Shown on a dialog an Editor may not open. Names the role, because unlike the
# level and patch controls this one is not about the host at all - a Full client
# may use these, and the user can ask to be promoted.
_ROLE_HINT = ('Not available with your access level: area, zone, background, '
              'camera and level-information changes need Full access. Ask the '
              'host to change your role.')

# Shown on the save entries. Separate from _PERMISSION_HINT, which explains that
# the host chooses the level and patch - true, but not the reason saving is
# restricted, and a hint that explains the wrong rule is worse than none.
_SAVE_HINT = ('Not available during this collaboration session: the host saves '
              'the level for everyone, and your copy is kept up to date '
              'automatically.')

# The dialogs whose changes are Full-only, mapped from the op kinds in
# protocol.OP_KINDS_FULL_ONLY:
#
#   areaoptions, camprofiles -> AreaSettingsCommand  -> 'area_settings'
#   zones, backgrounds       -> ZonesSnapshotCommand -> 'zones'
#   metainfo                 -> MetadataCommand      -> 'metadata'
#
# Kept as one list rather than inline so the set is readable next to the matrix
# it mirrors, and so a test can assert every Full-only op kind has a control
# here. Disabling the QAction covers its menu entry and its toolbar button.
_FULL_ONLY_ACTIONS = (
    'areaoptions',
    'camprofiles',
    'zones',
    'backgrounds',
    'metainfo',
)

# Loading a level: the host, or a client the host promoted to Full.
_LEADER_ACTIONS = ('newlevel', 'openfromname', 'openrecent')

# The game patch: the host only, whatever the client's role.
_HOST_ONLY_ACTIONS = ('changegamedef',)

# Adding, importing and deleting areas. Grouped separately from the Full-only
# dialogs because they are a different kind of act - they change what areas
# *exist*, not the settings of one - but they need the same restriction, and
# more obviously so: Zement's point is that if an Editor may not edit an area's
# settings, it certainly may not delete the area.
_AREA_ACTIONS = ('addarea', 'importarea', 'deletearea')

# Unavailable to everyone in a session, including the host.
#
# 'openfromfile' can reach a level outside the patch's stage folder, which no
# other machine could resolve from the name alone.
#
# The two Save-as entries are here for the same shape of reason (Block C - B3,
# Zement 2026-08-09). 'saveas' rewrites fileSavePath, which renames the
# session's level on one machine only - after which that peer is editing a file
# nobody else can find by name. 'savecopyas' is safe except when it lands in the
# session's own stage folder, and is rare enough that blocking it outright costs
# nothing; re-enabling it with a destination check is a noted follow-up.
_NEVER_IN_SESSION_ACTIONS = ('openfromfile', 'saveas', 'savecopyas')

# Writing the session's level: the host, whatever a client's role. A Full client
# leads the session but does not own its file - two save authorities would be
# two sources of truth for one level.
_SAVE_ACTIONS = ('save',)


class _BusyIndicator:
    """
    Says what the editor is doing while it cannot repaint.

    Applying a snapshot builds one real Qt item per object in the level, which
    measured at roughly 0.85 ms each - about 0.7 s for an 800-item area, and
    all of it on the main thread. It has to be: touching the scene from a
    reader thread corrupts it, which is the rule this whole file enforces.

    So the wait is not removable here, only explainable. Without this the
    window simply stopped responding and looked crashed - Zement's report that
    the other machine "becomes unresponsive for a moment".

    Deliberately not a QProgressDialog: a modal dialog during a scene rebuild
    can deliver events while the scene is half-populated. A status message and
    a wait cursor tell the user what is happening without pumping the event
    loop mid-mutation.
    """

    def __init__(self, window, message):
        self.window = window
        self.message = message
        self._label = None

    def __enter__(self):
        QtWidgets.QApplication.setOverrideCursor(
            QtCore.Qt.CursorShape.WaitCursor)
        try:
            status = self.window.statusBar()
        except Exception:
            return self

        self._label = QtWidgets.QLabel(self.message)
        status.insertWidget(0, self._label)

        # One repaint so the message is actually on screen before the work
        # starts. Restricted to painting: processEvents() with input allowed
        # would let a click reach a scene we are about to rebuild.
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        QtWidgets.QApplication.restoreOverrideCursor()
        if self._label is not None:
            try:
                self.window.statusBar().removeWidget(self._label)
            finally:
                self._label.deleteLater()
                self._label = None
        return False


class CollabController(QtCore.QObject):
    """
    Owns one collaboration session at a time.

    Attach to the main window once; `is_active` says whether anything is
    running.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.window = main_window

        self.bridge = CollabBridge(self)
        self.signals = self.bridge.signals

        self.mode = ''                 # '' | 'host' | 'join'
        self.server = None
        self.client = None
        self.host_session = None
        self.client_session = None
        self.responder = None
        self.mapping = None
        self.status_window = None

        self.refmap = None
        self.join_code = ''
        self._last_resync = 0.0

        # Tooltips as they were before a session restricted anything, so they
        # can be put back exactly rather than cleared.
        self._original_tooltips = {}

        # Set while loading a level *because* a peer asked, so the load does not
        # announce itself straight back to the session it came from.
        self._suppress_level_notify = False
        self.settings = collab_dialogs.load_collab_settings()

        # Presence: the canvas overlay, the send-side throttle, and the view
        # signals we listen to while a session is running. All created lazily,
        # because none of it exists outside a session.
        self.presence = None
        self._cursor_coalescer = None
        self._presence_timer = None
        self._presence_connected = False

        # id(item) -> the geometry last sent for it during a drag, so a
        # stationary selection is not streamed continuously.
        self._live_drag_sent = {}

        # The viewport rectangle last reported, for the same reason.
        self._last_view_rect = None

        # Patch transfer (client side). `_transfer` is a files.TransferSession
        # while one is running; `_transfer_patch` is what it is collecting, kept
        # separately because the session is discarded before the install and the
        # id is still needed to report and reload.
        self._transfer = None
        self._transfer_patch = ''
        self._transfer_queue = []
        self._transfer_destination = ''

        # The file currently being fetched, as (kind, path), and how many there
        # were to start with. The first is what matches an arriving chunk to the
        # section *we* asked for rather than the one the sender names; the
        # second is only for the progress line, since the queue shrinks as it
        # goes (Block C - B3).
        self._transfer_current = None
        self._transfer_total = 0

        # What the session moved to while a patch was still being fetched, held
        # until the patch is loaded and its Stage folder is known. `(level,
        # area)` when a switch was deferred, None when there is nothing to
        # replay; `_deferred_snapshot_area` is the area a snapshot was wanted
        # for, or None. Kept apart because either can arrive without the other:
        # a joining client asks for a snapshot with no level switch, and a
        # mid-session switch is a level change with no snapshot request.
        self._deferred_level = None
        self._deferred_snapshot_area = None

        # -- session file identity (Block C - B3, phase 0) -------------------
        #
        # Which level and area the *session* is on, tracked explicitly rather
        # than read back out of mainWindow.fileSavePath.
        #
        # The two are not the same question, and conflating them is the root of
        # several B3 symptoms. fileSavePath answers "what file did this editor
        # last open", which during a session may be:
        #
        #   - a different level entirely, if the peers' stage paths diverge and
        #     both resolved '01-01' against their own folder (known open 10.1);
        #   - nothing at all, if the client has never opened this level (10.1b);
        #   - stale, between a session moving and the load completing.
        #
        # Saving, prompting about unsaved changes, and reporting where the
        # session is must all be answered from the session's own view, so it is
        # kept here. `_session_level` is the bare level name as it travels on
        # the wire, '' when the session is on an unsaved level.
        self._session_level = ''
        self._session_area = 1

        # Whether this peer may write the session's level to disk. The host is
        # the save authority (Zement, 2026-08-09); a client never is, whatever
        # its role, so this is set once when a session starts and is not a
        # per-action decision.
        self._is_save_authority = False

        # The host's last room_info, kept so the content check can run *after*
        # the level has loaded rather than when the message arrived (Block
        # C - B3, phase 2). Empty when nothing has been reported yet.
        self._host_fingerprint = {}

        # The mismatch last reported to the user, so the same one is not
        # repeated on every snapshot. Cleared when the content matches again.
        self._reported_mismatch = ''

        # A level the host announced it had saved and whose bytes are still
        # arriving: {'level', 'sha256', 'size', 'parts'}. None when no save is
        # in flight, which is the normal state (Block C - B3, phase 3c).
        self._expected_save = None

        # -- switch proposals (Block C - B3, phase 3d) -----------------------
        #
        # A Full client keeps level and area leading, but Save is the host's, so
        # a client's switch has to be resolved by the host *before* it happens:
        # once the client has loaded, there is nothing left for the host to
        # cancel back to.
        #
        # Client side: the outcome of the proposal currently in flight, or None
        # when none is. 'waiting' while the host is deciding, then 'accepted' or
        # a refusal reason. Read by the modal wait, which is why it is a plain
        # attribute rather than a return value - the answer arrives on a signal.
        self._proposal = None

        # Host side: the session id of the client whose proposal is being
        # resolved, so a second one arriving mid-dialog is refused rather than
        # stacking a second dialog on the host. '' when none is open.
        self._resolving_proposal = ''

        # -- level-file-first (Block C - B3, Fact 3) -------------------------
        #
        # Client side: set when the session has moved and the host's copy of the
        # level is expected to arrive, so the client waits for the file instead
        # of opening whatever its own stage folder happens to hold under that
        # name. Cleared once the file is open, or when the wait gives up.
        #
        # This is what removes the double load Zement saw: the client used to
        # open its own '01-01', then have a snapshot overwrite it with the
        # host's - two loads, the first of them wrong.
        self._pending_publication = False

        # Host side: session ids currently being sent a patch. A publication
        # must not be pushed into the middle of one, because both travel as
        # stage-section chunks on the same connection and the client drops a
        # publication while a transfer is running. Populated when a manifest is
        # sent, emptied when the client reports the transfer done or failed.
        self._transferring_peers = set()

        # Client side: patch ids whose game data has already been fetched this
        # session, so the assets sync happens once per patch rather than once
        # per room_info (Block C - B3, round 2, R1).
        #
        # room_info is republished on every level and area change - it carries
        # the level name and the content fingerprints - which re-runs the patch
        # check. Without this, that re-ran the whole Stage/Texture download on
        # every switch: Zement saw a full re-download per level change on
        # 2026-08-11, for a patch the client already had complete.
        #
        # Keyed on the patch id, not a plain flag, so a mid-session patch switch
        # still syncs the *new* patch's data.
        self._synced_asset_patches = set()

        self._connect_signals()

    # -- signal wiring ------------------------------------------------------

    def _connect_signals(self):
        self.signals.rosterChanged.connect(self._onRoster)
        self.signals.chatReceived.connect(self._onChat)
        self.signals.statusMessage.connect(self._onStatus)
        self.signals.errorOccurred.connect(self._onError)
        self.signals.operationReceived.connect(self._onOperation)
        self.signals.snapshotReceived.connect(self._onSnapshot)
        self.signals.snapshotRequested.connect(self._onSnapshotRequested)
        self.signals.levelSwitchRequested.connect(self._onLevelSwitchRequested)
        self.signals.levelSwitchProposed.connect(self._onLevelSwitchProposed)
        self.signals.operationRejected.connect(self._onOperationRejected)
        self.signals.connected.connect(self._onConnected)
        self.signals.roomInfoChanged.connect(self._onRoomInfoChanged)
        self.signals.disconnected.connect(self._onDisconnected)
        self.signals.rejected.connect(self._onRejected)
        self.signals.roleChanged.connect(self._onRoleChanged)
        self.signals.presenceReceived.connect(self._onPresence)
        self.signals.patchNeeded.connect(self._onPatchNeeded)
        self.signals.fileRequested.connect(self._onFileRequested)
        self.signals.manifestReceived.connect(self._onManifest)
        self.signals.fileChunkReceived.connect(self._onFileChunk)
        self.signals.levelSaved.connect(self._onLevelSaved)
        self.signals.transferFinished.connect(self._onTransferFinished)
        self.signals.peerTransferFinished.connect(self._onPeerTransferFinished)

    @property
    def is_active(self):
        return self.mode != ''

    @property
    def is_host(self):
        return self.mode == 'host'

    # -- entry point --------------------------------------------------------

    def showSetupDialog(self):
        """
        Opens the host/join dialog and starts whichever the user chose.
        """
        if self.is_active:
            self.showStatusWindow()
            return

        # A window left over from a finished session has the wrong controls for
        # the next one (a host's buttons for a client, or vice versa) and a stale
        # chat log, so start fresh. leave() already does this; the case that
        # reaches here is a session ended by the *other* side, where the window
        # is kept on purpose so the reason stays readable.
        self._closeStatusWindow()

        # Re-read the settings here rather than trusting the copy taken at
        # construction: the user may have changed them in Preferences since.
        self.settings = collab_dialogs.load_collab_settings()
        self._configureDebugLog()

        dialog = collab_dialogs.CollabSetupDialog(self.window)
        dialog.startDiscovery()

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        if dialog.result_mode == 'host':
            self.host(**dialog.result_values)
        else:
            self.join(**dialog.result_values)

    # -- hosting ------------------------------------------------------------

    def host(self, nick='Host', port=identity.DEFAULT_HOST_PORT,
             discoverable=False, upnp=False, **_extra):
        """
        Starts hosting. Returns True on success; failures are reported to the
        user and leave nothing running.
        """
        if self.is_active:
            return False

        base = _settings_directory()

        try:
            cert_path, key_path, fingerprint = identity.load_or_create_identity(base)
        except identity.CertificateUnavailable as exc:
            QtWidgets.QMessageBox.warning(self.window, 'Collaboration', str(exc))
            return False

        secret = identity.generate_secret()
        self.refmap = sync.RefMap(origin='host', is_authority=True)

        # Give every item that already exists a reference, so edits made before
        # anyone joins can still be broadcast. Without this the first move of an
        # existing object fails to encode ('unreferenced item') and triggers a
        # pointless resync, because refs would otherwise only be minted by
        # build_snapshot when the first client asks for the level.
        self._seedRefMap()

        self.host_session = session.HostSession(
            secret=secret,
            cert_fingerprint=fingerprint,
            host_nick=nick,
            host_color=str(self.settings.get('color', '') or ''),
            app_version=str(getattr(globals_, 'ReggieVersionShort', '')),
            room_info=self._roomInfo(),
            on_event=self.bridge.on_host_event,
            on_op=self.bridge.on_host_op,
            on_roster_changed=self.bridge.on_host_roster,
        )

        self.server = transport.ServerTransport(
            cert_path, key_path, port=port,
            on_connect=self.host_session.handle_connect,
            on_message=self.host_session.handle_message,
            on_disconnect=self.host_session.handle_disconnect,
        )

        try:
            self.server.start()
        except transport.TransportError as exc:
            QtWidgets.QMessageBox.warning(self.window, 'Collaboration', str(exc))
            self._teardown()
            return False

        self.host_session.start_maintenance()
        self._restoreBans()

        debuglog.log('controller', 'hosting started', port=self.server.port,
                     fp=debuglog.short_fingerprint(fingerprint),
                     refs=self.refmap.size(),
                     bans=len(self.host_session.bans.entries()))

        # The port may differ from the request (0 means "any free port").
        actual_port = self.server.port
        address = self._advertisedAddress(upnp, actual_port)

        self.join_code = identity.encode_join_code(
            address, actual_port, fingerprint, secret)

        self.mode = 'host'

        # The host is the session's save authority, and the session starts on
        # whatever the host already has open.
        self._is_save_authority = True
        self._setSessionLevel(self._currentLevelName(), self._areaNumber())

        self.applyEditingPermissions()

        # Say which address the code actually carries. The setup dialog can
        # only show the local one - the public address is not known until the
        # router has been asked, which happens above - so this is the first
        # point at which the answer exists, and the code itself no longer
        # shows it.
        if upnp_module.is_private_address(address):
            self._appendStatus(
                'Hosting on %s:%d. That is a local address, so this code works '
                'on your network only.' % (address, actual_port))
        else:
            self._appendStatus(
                'Hosting on %s:%d, reachable from the internet.'
                % (address, actual_port))
        self._startPresence()

        if discoverable:
            self._startDiscovery(actual_port, nick)

        self.showStatusWindow()

        # Show the roster straight away. HostSession only broadcasts it when the
        # membership changes, so without this the host sees an empty
        # participants list until somebody joins - and reasonably concludes the
        # feature is broken.
        self.bridge.on_host_roster(self.host_session.participants())
        collab_dialogs.show_join_code(self.window, self.join_code)
        return True

    def _advertisedAddress(self, upnp_enabled, port):
        """
        Works out which address to put in the join code, forwarding the port if
        the user asked.

        UPnP failures are non-fatal by design: the session still works on the
        LAN, and the user can forward the port by hand.
        """
        local = transport.local_ip_addresses()
        address = local[0] if local else '127.0.0.1'

        if not upnp_enabled:
            debuglog.log('upnp', 'not enabled; advertising the local address',
                         address=address)
            return address

        try:
            self.mapping = upnp_module.PortMapping.create(port, address)
        except upnp_module.UPnPError as exc:
            # Logged as well as shown: the status window closes when a session
            # ends, so a user debugging a failed connection afterwards has
            # nothing to read. This is exactly how a router that silently does
            # not run UPnP stayed invisible.
            debuglog.log('upnp', 'port forwarding failed',
                         port=port, error=str(exc))
            self._appendStatus('Automatic port forwarding failed: %s' % exc)
            return address

        debuglog.log('upnp', 'port forwarded', port=port)
        self._appendStatus('Port %d forwarded via UPnP.' % port)

        external = upnp_module.external_ip_address(self.mapping.control_url,
                                            self.mapping.service_type)
        if external:
            debuglog.log('upnp', 'router reported a public address')
            return external

        debuglog.log('upnp', 'router reported no usable public address',
                     local=address)
        self._appendStatus(
            'The port was forwarded, but the router did not report a public '
            'address. This usually means the reply came from a virtual '
            'adapter\'s router (Hyper-V, WSL, a VM switch) rather than your '
            'real one, or that your connection is behind carrier-grade NAT.')
        self._appendStatus(
            'The join code below contains your LOCAL address (%s), so it will '
            'only work for players on this network. For play over the '
            'internet, look up your public address and forward port %d by '
            'hand.' % (address, port))
        return address

    def _startDiscovery(self, port, nick):
        def describe():
            return {
                'port': port,
                'nick': nick,
                'game': self._gameName(),
                'fp12': identity.pin_from_fingerprint(
                    self.host_session.cert_fingerprint),
                'players': len(self.host_session.participants()),
                'max_players': transport.MAX_PEERS,
                'needs_code': True,
            }

        self.responder = discovery.DiscoveryResponder(describe)
        try:
            self.responder.start()
        except discovery.DiscoveryError as exc:
            self._appendStatus('Network discovery unavailable: %s' % exc)
            self.responder = None

    # -- joining ------------------------------------------------------------

    def join(self, host='', port=identity.DEFAULT_HOST_PORT, pin='', secret='',
             nick='Player', **_extra):
        """
        Connects to a host. Returns True once the TLS handshake and pin check
        have succeeded; authentication completes asynchronously afterwards.
        """
        if self.is_active:
            return False

        self.refmap = sync.RefMap(origin='client', is_authority=False)
        self._secret = secret

        self.client_session = session.ClientSession(
            nick=nick, on_event=self.bridge.on_client_event)

        self.client = transport.ClientTransport(
            host, port, pin,
            on_message=self._onClientMessage,
            on_disconnect=self.bridge.on_client_disconnect,
        )

        try:
            self.client.connect()
        except transport.PinMismatch as exc:
            # NOT a network error: something answered in the host's place.
            collab_dialogs.report_pin_mismatch(self.window, str(exc))
            self._teardown()
            return False
        except transport.TransportError as exc:
            QtWidgets.QMessageBox.warning(self.window, 'Collaboration', str(exc))
            self._teardown()
            return False

        self.mode = 'join'

        # A client is never the save authority, whatever its role: Save is the
        # host's (Zement, 2026-08-09). Where the session is is not known yet -
        # room_info and the first area_switch answer that.
        self._is_save_authority = False
        self._setSessionLevel('', 1)

        self.applyEditingPermissions()
        debuglog.log('controller', 'joined', host=host, port=port,
                     fp=debuglog.short_fingerprint(self.client.cert_fingerprint))
        self.showStatusWindow()
        return True

    def _onClientMessage(self, connection, message):
        """
        Runs on the client's reader thread. Answers the handshake, then hands
        everything else to ClientSession, which emits through the bridge.
        """
        if message['t'] == protocol.T_SERVER_HELLO:
            from reggie.collab import auth

            payload = message['p']

            # The proof MUST be bound to the fingerprint we computed from the
            # certificate the peer actually presented - never to the cert_fp it
            # claims in server_hello. Signing a self-declared value would turn
            # this client into an oracle: a third party could relay our proof to
            # a different host, which is exactly the attack the fingerprint
            # binding in auth.py exists to stop.
            verified = connection.cert_fingerprint

            claimed = (payload.get('cert_fp') or '').strip().lower()
            if not hmac.compare_digest(claimed, (verified or '').lower()):
                # A peer misreporting its own identity has no benign reason to.
                collab_dialogs.report_pin_mismatch(
                    self.window,
                    'The host reported a different identity than the '
                    'certificate it presented.')
                connection.close('server_hello fingerprint mismatch')
                return

            connection.send_type(protocol.T_CLIENT_AUTH, {
                'proof': auth.compute_proof(self._secret, payload['nonce'],
                                            verified),
                'protocol': protocol.PROTOCOL_VERSION,
                'app_version': str(getattr(globals_, 'ReggieVersionShort', '')),
                'nick': self.client_session.nick,
                # The colour this user picked. Advisory: the host assigns the
                # final colour and falls back if it is unusable or taken.
                'color': str(self.settings.get('color', '') or ''),
                'game_id': self._gameId(),
                'plugin_state_hash': files.plugin_state_hash(self._enabledPlugins()),
            })
            return

        self.client_session.handle_message(connection, message)

    # -- leaving ------------------------------------------------------------

    def leave(self):
        """
        Ends the session, telling the other side why.

        Deliberate leaving closes the status window, unlike a remote disconnect:
        the user already knows why it ended, so leaving a dead lobby on screen
        only makes it look like the session is still running. Reopening
        File > Collaborate then correctly offers the host/join dialog again.
        """
        if not self.is_active:
            return

        if self.host_session is not None:
            self._persistBans()
            self.host_session.shutdown()

        if self.client is not None:
            self.client.close('left the session')

        self._teardown()
        self._closeStatusWindow()

    def _writeChatLog(self):
        """
        Saves the session's chat to logs/chat_<timestamp>.log.

        Temporary scaffolding for the Block C testing, like the terminal tee -
        see reggie/core/session_log.py. The chat is the human record of what was
        said and decided during a session, and today it lives only in a
        QTextEdit that is destroyed when the status window closes.

        Fully guarded: a session must end cleanly whatever happens here, and
        sockets and threads are still to be shut down after this returns.
        """
        window = self.status_window
        if window is None:
            return ''

        widget = getattr(window, 'chatLog', None)
        if widget is None:
            return ''

        try:
            # toPlainText, not toHtml: the log is for reading, and appendChat
            # writes markup for emphasis that would only be noise in a file.
            text = widget.toPlainText()
        except Exception:
            return ''

        # Which side wrote this, not who: the controller does not keep its own
        # nick, and when two logs from one session are read side by side "host"
        # and "client" is the distinction that actually matters.
        role = 'host' if self.is_host else 'client'

        try:
            from reggie.core import session_log

            path = session_log.write_session_chat(text, role)
        except Exception:
            return ''

        if path:
            debuglog.log('controller', 'chat saved', path=path)

        return path

    def _closeStatusWindow(self):
        if self.status_window is None:
            return

        window = self.status_window

        # Cleared before closing so a stale roster cannot be seen, and dropped
        # immediately so the next session builds a fresh window rather than
        # inheriting this one's controls and chat log.
        self.status_window = None
        window.setRoster([])
        window.close()
        window.deleteLater()

    def _teardown(self):
        # Before anything is torn down: the chat window is closed on the way
        # out, and with it the only record of what anyone said. Written first so
        # a fault later in teardown cannot cost the log.
        self._writeChatLog()

        # A peer that disconnected mid-transfer never sends file_done, so
        # without this the set keeps an id that will never be discarded and the
        # host stays silent about level changes for the rest of the session.
        self._transferring_peers.clear()

        # Per session, not per install: the next session may be with a different
        # host whose Stage folder differs, so what was synced last time proves
        # nothing about this time.
        self._synced_asset_patches.clear()

        self._stopPresence()

        # A transfer cannot outlive the connection carrying it, and staged
        # files must not survive into the next session, where a stale queue
        # would have the client requesting files nobody offered it.
        self._clearTransfer(abort=True)

        if self.responder is not None:
            self.responder.stop()
            self.responder = None

        if self.mapping is not None:
            # Always remove the mapping: leaving a hole open in the user's
            # router after the session ends is a harm we would have caused.
            self.mapping.delete()
            self.mapping = None

        if self.server is not None:
            self.server.stop()
            self.server = None

        if self.client is not None:
            # Close it, do not merely drop it. A ClientTransport owns a reader
            # thread and a live socket; dropping the reference leaves both
            # running, still connected to the host's port. The next session then
            # races a ghost connection from the previous one - which is why
            # restarting a session sometimes ended with the client apparently
            # kicked the moment it joined. close() is idempotent, so calling it
            # after the peer already hung up is harmless.
            try:
                self.client.close('session ended')
            except Exception:
                pass
            self.client = None

        self.host_session = None
        self.client_session = None
        self.refmap = None
        self._secret = ''
        self.join_code = ''
        self.mode = ''

        # The session's file identity dies with the session. Left set, it would
        # tell the next session - or the editor between sessions - that it is on
        # a level it is not on, and isSaveAuthority() would keep answering from
        # a role nobody holds any more.
        self._session_level = ''
        self._session_area = 1
        self._is_save_authority = False
        self._host_fingerprint = {}
        self._reported_mismatch = ''
        self._expected_save = None

        # The session's Stage/Texture override goes with it, so the editor
        # returns to the user's own folders the moment the session ends. This
        # is what makes the override safe: it never outlives the session and it
        # was never written to disk.
        try:
            from reggie.io.gamedef import ReggieGameDefinition

            ReggieGameDefinition.ClearSessionGamePaths()
        except Exception:
            pass

        # Restore every control the session had restricted. Doing this here
        # rather than in leave() covers a session that ended because the *other*
        # side hung up, which would otherwise leave the editor permanently
        # unable to open a level.
        self.applyEditingPermissions()

        debuglog.log('controller', 'session torn down')

    # -- status window ------------------------------------------------------

    def showStatusWindow(self):
        if self.status_window is None:
            window = collab_dialogs.CollabStatusWindow(self.is_host, self.window)
            window.chatRequested = self._sendChat
            window.leaveRequested = self.leave
            if self.is_host:
                window.kickRequested = self._kick
                window.banRequested = self._ban
                window.roleRequested = self._setRole
            self.status_window = window

        if self.is_host:
            # Set every time rather than only on creation: the code is the
            # host's only way to invite anyone after dismissing the dialog that
            # showed it once, so a stale or missing one is a dead end.
            self.status_window.setJoinCode(self.join_code)

        self.status_window.show()
        self.status_window.raise_()

    def _appendStatus(self, text):
        if self.status_window is not None:
            self.status_window.appendStatus(text)

    # -- host actions -------------------------------------------------------

    def _sendChat(self, text):
        if self.host_session is not None:
            # HostSession echoes the host's own message back through its event
            # callback, so the host sees it without any help here.
            self.host_session.send_chat(text)
            return

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_CHAT, {'text': text,
                                  'kind': protocol.CHAT_KIND_USER}))

            # Echo locally. The host relays a client's message to the *other*
            # clients only - correct, since bouncing it back would duplicate it
            # for everyone whose message did come back - so without this the
            # sender is the one person who never sees what they said.
            clean = protocol.sanitize_text(str(text or ''),
                                           protocol.MAX_CHAT_CHARS)
            if clean and self.status_window is not None:
                self.status_window.appendChat(
                    getattr(self.client_session, 'nick', '') or 'You', clean,
                    protocol.CHAT_KIND_USER)

    def applyEditingPermissions(self):
        """
        Enables or disables the controls that change what everybody is editing.

        Zement's rules, and the reasoning behind each:

        - **Patch**: host only, always. A client switching patch would reload
          spritedata and tilesets under a level the host still owns, and the
          host cannot see or prevent it. Greyed out rather than hidden, so it is
          obvious the option exists and why it is unavailable.
        - **Level**: host only, and by name rather than by file. "Open by file"
          can reach a level outside the patch's stage folder, which a client
          could not resolve from the name alone - so the host is restricted to
          what a client can actually follow.
        - **Area**: either side, but a client needs the Full role, since an area
          switch moves everyone.

        This is a UI convenience, not enforcement. A client that bypasses it
        still has its operations checked host-side by authorize_op - the same
        division as ClientSession.may_send_op, and for the same reason.
        """
        window = self.window
        actions = getattr(window, 'actions', None)
        if not isinstance(actions, dict):
            return

        window = self.window

        def enable(name, allowed, hint=_PERMISSION_HINT):
            action = actions.get(name)
            if action is None:
                return

            action.setEnabled(allowed)

            # Remember the original tooltip once, so restoring it later does not
            # depend on Qt's fallback behaviour: setToolTip('') makes
            # QAction.toolTip() return the action *text*, which would silently
            # replace a real tooltip with the menu label.
            if name not in self._original_tooltips:
                self._original_tooltips[name] = action.toolTip()

            action.setToolTip(self._original_tooltips[name] if allowed
                              else hint)

        for name in self._restrictedActions():
            if name in _FULL_ONLY_ACTIONS:
                hint = _ROLE_HINT
            elif name in _SAVE_ACTIONS or name in ('saveas', 'savecopyas'):
                hint = _SAVE_HINT
            else:
                hint = _PERMISSION_HINT

            enable(name, self.actionAllowedBySession(name), hint)

        active = self.is_active
        host = self.is_host
        may_change_area = self.actionAllowedBySession('addarea')

        self._setWidgetAllowed(getattr(window, 'patchComboBox', None),
                               'patchComboBox', not active or host)
        self._setWidgetAllowed(getattr(window, 'areaComboBox', None),
                               'areaComboBox', may_change_area)

    @staticmethod
    def _restrictedActions():
        """
        Every action a session can restrict, in one place.
        """
        return (_LEADER_ACTIONS + _HOST_ONLY_ACTIONS + _AREA_ACTIONS
                + _FULL_ONLY_ACTIONS + _NEVER_IN_SESSION_ACTIONS
                + _SAVE_ACTIONS)

    def actionAllowedBySession(self, name):
        """
        Whether this session allows an action, ignoring any other reason it
        might be disabled (an empty level, no zones, four areas already).

        Public and separate from applyEditingPermissions because several places
        recompute an action's enabled state from the level itself and run
        afterwards - see set_action_allowed(). They need to ask this question
        without re-running the whole pass, and combining the two answers is what
        stops a level reload from quietly re-enabling a restricted control.
        """
        if not self.is_active:
            return True

        host = self.is_host

        # A Full client is trusted with the session's level and area, exactly
        # like the host. The role is what the distinction rests on, not being
        # the host: an Editor client may change neither.
        may_lead = host or self._clientHasFullRole()

        if name in _NEVER_IN_SESSION_ACTIONS:
            # "Open by file" can reach a level outside the patch's stage folder,
            # which no other machine could resolve from the name alone - so it
            # is unavailable to everyone in a session, the host included.
            return False

        if name in _HOST_ONLY_ACTIONS:
            # Switching patch reloads spritedata and tilesets under a level the
            # host owns, so it stays with the host whatever the client's role.
            return host

        if name in _SAVE_ACTIONS:
            # Asked of the save authority rather than of `host` directly, so
            # there is one answer to "may I write this level" and level_io's
            # gate and this menu state cannot disagree.
            return self.isSaveAuthority()

        if name in _LEADER_ACTIONS or name in _AREA_ACTIONS:
            return may_lead

        if name in _FULL_ONLY_ACTIONS:
            # Each of these pushes a command whose op kind is in
            # protocol.OP_KINDS_FULL_ONLY, so an Editor that opened one could
            # edit, watch it apply locally, and have the host refuse it - the
            # two sides then differ with only a chat line to explain it.
            return may_lead

        return True

    def _setWidgetAllowed(self, widget, key, allowed):
        if widget is None:
            return

        widget.setEnabled(allowed)

        if key not in self._original_tooltips:
            self._original_tooltips[key] = widget.toolTip()

        widget.setToolTip(self._original_tooltips[key] if allowed
                          else _PERMISSION_HINT)

    def _clientHasFullRole(self):
        session_object = self.client_session
        if session_object is None:
            return False
        return getattr(session_object, 'role', '') == protocol.ROLE_FULL

    # -- switch proposals (Block C - B3, phase 3d) --------------------------
    #
    # Only a *client* proposes. The host switches directly, because it is the
    # save authority: there is nobody else's unsaved work to resolve, and its
    # own is handled by the ordinary CheckDirty it already runs.

    PROPOSAL_TIMEOUT_SECONDS = 30.0

    def proposeLevelChange(self, level, area=1):
        """
        Asks the host to move the session, and waits for its answer.

        Returns True if the caller should go ahead and load, False if it should
        not. Everyone who is not a Full client in a session gets True
        immediately, so the ordinary editor and the host are untouched by this.

        This is the inversion decision 11 needed. A client used to load first and
        announce afterwards, which left the host's dialog with nothing to cancel
        back to - by the time it was asked, the client had already moved, and
        "Cancel" could only have put it back with a second load. Proposing first
        costs a round trip and makes the host's answer meaningful.
        """
        if not self.is_active or self.is_host:
            return True

        if not self._clientHasFullRole():
            # Not allowed to move the session at all. The controls are disabled,
            # so this is the bypass path; the host would refuse it anyway.
            return False

        if self.client is None:
            return False

        if self._proposal is not None:
            # One at a time from this client too, not only host-side: a second
            # dialog here would send a second proposal the host has already
            # committed to refusing.
            self._appendStatus('You are already waiting for the host\'s answer.')
            return False

        payload = {'area': _clamp_area(area), 'level': str(level or '')}

        # Armed *before* the send, not after. The answer is delivered by the
        # bridge from the transport's reader thread, so it can arrive the moment
        # the message is on the wire - and a reply landing while _proposal is
        # still None is not recognised as an answer at all: it falls through to
        # the refused-edit path, asks for a pointless resync, and then this
        # waits out the full timeout for an answer it has already had.
        self._proposal = 'waiting'

        try:
            self.client.send(protocol.make_message(protocol.T_AREA_SWITCH,
                                                   payload))
        except Exception as exc:
            self._proposal = None
            self._appendStatus('The host could not be asked: %s' % exc)
            return False

        self._appendStatus('Asked the host to move the session to %s.'
                           % _describeLevel(payload['level'], payload['area']))
        debuglog.log('client', 'proposed level change', level=payload['level'],
                     area=payload['area'])

        outcome = self._waitForProposal()
        self._proposal = None

        if outcome == 'accepted':
            # The host agreed and has broadcast the switch to everyone,
            # including us. Loading here as well would load it twice, so the
            # broadcast is left to do it - _onLevelSwitchRequested is the one
            # place a level is loaded for the session.
            return False

        self._appendStatus(outcome or 'The host did not answer.')
        return False

    def _waitForProposal(self):
        """
        Waits for the host's answer, keeping the event loop running.

        The loop must keep running: the answer arrives on the session's own
        reader thread and is delivered through the bridge's signals, so blocking
        here would stop us hearing the very thing we are waiting for. Same shape
        and same reason as _waitForInstalledPatch.

        A timeout is not optional either. The host's dialog is modal on *its*
        machine, and a host who has stepped away would otherwise leave the
        client frozen with no way out.
        """
        deadline = time.monotonic() + self.PROPOSAL_TIMEOUT_SECONDS

        with _BusyIndicator(self.window, 'Waiting for the host...'):
            while self._proposal == 'waiting':
                if time.monotonic() >= deadline:
                    return ('The host did not answer, so the session stayed '
                            'on %s.' % self._describeCurrentLevel())

                if not self.is_active:
                    return 'The session ended while you were waiting.'

                QtWidgets.QApplication.processEvents(
                    QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
                    50)

        return self._proposal

    def _resolveProposal(self, participant, level, area):
        """
        Host side: decides a client's proposal and answers it.

        Returns True if the switch should go ahead here.

        The host's unsaved work is the whole reason this exists, so it is asked
        about it first, and the dialog names who is asking - a Save/Discard
        prompt appearing unbidden while someone else is at the keyboard is
        otherwise unexplainable.
        """
        session_id = str(getattr(participant, 'session_id', '') or '')
        nick = str(getattr(participant, 'nick', '') or 'A client')

        if self._resolving_proposal:
            # Two clients proposing at once. Refusing the second is better than
            # queueing it: by the time the host answered the first, the second
            # would be a move from a level nobody is on any more.
            self._refuseProposal(
                participant,
                'the host is already answering another request')
            return False

        self._resolving_proposal = session_id or nick
        try:
            if globals_.Dirty and self._maySave():
                choice = collab_dialogs.resolve_switch_proposal(
                    self.window, nick, _describeLevel(level, area))

                if choice == 'cancel':
                    self._refuseProposal(
                        participant, 'the host is keeping the current level')
                    self._appendStatus('You declined %s\'s request to move to '
                                       '%s.' % (nick, _describeLevel(level, area)))
                    return False

                if choice == 'save':
                    if not self._saveForProposal():
                        # The save failed, so proceeding would lose exactly the
                        # work the host just chose to keep.
                        self._refuseProposal(
                            participant,
                            'the host could not save, so the level did not '
                            'change')
                        return False

            self._appendStatus('%s moved the session to %s.'
                               % (nick, _describeLevel(level, area)))
            return True
        finally:
            self._resolving_proposal = ''

    def _refuseProposal(self, participant, reason):
        """
        Tells one client its proposal was declined.

        Reuses T_OP_REJECT, which _handle_area_switch already sends for a
        role-denied switch and which the client already surfaces: "the host said
        no" needs no message type of its own. op_id names the request type, so
        the client can tell its own refused proposal from a refused edit.
        """
        connection = getattr(participant, 'connection', None)
        if connection is None:
            return False

        try:
            connection.send_type(protocol.T_OP_REJECT, {
                'op_id': protocol.T_AREA_SWITCH,
                'reason': reason,
            })
        except Exception:
            return False

        return True

    def _maySave(self):
        """
        Whether this editor could actually save, so the host is not offered a
        Save button that would be refused.
        """
        window = self.window
        checker = getattr(window, '_maySaveInSession', None)
        if not callable(checker):
            return True
        try:
            return bool(checker())
        except Exception:
            return True

    def _saveForProposal(self):
        """
        Saves the host's work in answer to its own dialog. Returns success.

        A failure here must be reported as a failure rather than swallowed: the
        caller uses it to decide whether the switch may proceed, and treating a
        failed save as a success would discard the work.
        """
        window = self.window
        save = getattr(window, 'HandleSave', None)
        if not callable(save):
            return False
        try:
            return bool(save())
        except Exception as exc:
            self._appendStatus('The level could not be saved: %s' % exc)
            return False

    def notifyLevelChanged(self):
        """
        Republishes the level after the host loaded another one or switched area.

        The clients' references all point at items that no longer exist, so this
        rebuilds the map and pushes a fresh snapshot rather than trying to
        reconcile: every item changed identity at once, which is a resync by any
        other name.

        A client with the Full role is allowed to do this too, per the agreed
        permissions, so it announces the change and lets the host redistribute
        it rather than being pulled back. Asking for a resync here was wrong:
        the host would answer with a snapshot of the area *it* still had open,
        which loaded the client's new area and then immediately replaced it -
        the "switches back" Zement saw.

        A client without that role should not have got here at all, since the
        controls are disabled; if it does, the host's state still wins.
        """
        if not self.is_active:
            return False

        # We are loading this level *because* a peer asked us to. Announcing it
        # again would bounce it straight back to the sender.
        #
        # The session's own record is still updated first, and deliberately
        # before the early return: this is the path a remote-driven load takes,
        # so skipping it here would leave a client's session identity stuck on
        # whatever it joined with, which is the state phase 0 exists to remove.
        # _onLevelSwitchRequested sets it too, from the name it was given; this
        # covers what actually loaded, which is the more truthful of the two.
        self._setSessionLevel(self._currentLevelName(), self._areaNumber())

        if self._suppress_level_notify:
            return False

        if not self.is_host:
            # A client that has already loaded is in the wrong state whatever
            # its role, so both branches resync (Block C - B3, phase 3d).
            #
            # This used to be where a Full client announced its switch, after
            # the fact. It no longer is: proposeLevelChange asks the host
            # *before* loading, so a Full client reaching here means the switch
            # bypassed that - the editor found a route into LoadLevel that does
            # not propose. Announcing it now would be the old behaviour and the
            # old bug: the host would be told about a move it never agreed to,
            # with its unsaved work already stepped over.
            #
            # So this is a backstop, and it is deliberately the conservative
            # one: pull this peer back to the session's state rather than push
            # its state onto everyone. Losing a local switch is recoverable;
            # silently overriding the host's unsaved work is not.
            if self._clientHasFullRole():
                self._appendStatus(
                    'That level change did not go through the host, so the '
                    'session\'s level is being reloaded.')
                debuglog.log('client', 'unproposed level change',
                             level=self._describeCurrentLevel())
            else:
                self._appendStatus(
                    'You changed level or area locally; reloading the host\'s.')

            self._requestResync(force=True)
            return False

        # The old references are meaningless now.
        self.refmap = sync.RefMap(origin='host', is_authority=True)
        self._seedRefMap()

        self.host_session.set_room_info(self._roomInfo())

        # Name the level before sending its contents: a client that receives a
        # snapshot without knowing which level it belongs to cannot update its
        # own title bar or file path.
        self._broadcastLevelChange()

        # Send the file itself, and let the clients open it (Block C - B3,
        # Fact 3). Falls back to the snapshot when there is no file to send.
        if not self._publishLevelFile():
            self._broadcastSnapshot()

        # _currentLevelName, not globals_.levelName - the latter has never
        # existed, so this line said "the level" every time (the same missing
        # attribute that made room_info's level_name empty in phase 0).
        level = self._currentLevelName() or 'the level'
        self._appendStatus('Shared %s with everyone.' % level)
        debuglog.log('controller', 'level changed', level=level,
                     refs=self.refmap.size())
        return True

    def _levelChangePayload(self):
        """
        The level and area everyone should move to.

        The level travels as a *name*, never a path: the peers resolve it inside
        their own patch's stage folder, and a path from another machine is both
        unusable and a way to point a peer at an arbitrary file.
        """
        return {
            'area': self._areaNumber(),
            'level': self._currentLevelName(),
        }

    @staticmethod
    def _currentLevelName():
        """
        The bare level name, as LoadLevel(name, isFullPath=False) expects.

        Derived from mainWindow.fileSavePath rather than a global: there is no
        globals_.levelName - reading one returned '' every time, which made
        every level change arrive as LoadLevel(None), and a None name means
        "new level". That is the 'untitled [unsaved]' Zement saw on the other
        instance.

        Every known extension is stripped, not just the last: '.arc.LH' would
        otherwise leave a trailing '.arc' that no stage folder contains.
        """
        window = getattr(globals_, 'mainWindow', None)
        path = str(getattr(window, 'fileSavePath', '') or '')
        if not path:
            return ''

        name = os.path.basename(path)
        for extension in sorted(getattr(globals_, 'FileExtentions', ()),
                                key=len, reverse=True):
            if name.endswith(extension):
                return name[:-len(extension)]

        return name

    def _describeCurrentLevel(self):
        level = self._currentLevelName()
        area = self._areaNumber()
        if level:
            return '%s (area %d)' % (level, area)
        return 'area %d' % area

    # -- session file identity (Block C - B3, phase 0) -----------------------

    def _setSessionLevel(self, level, area):
        """
        Records where the session now is.

        Called from the one place a level or area actually changes for the
        session - the host announcing it, or a peer applying it - so the two
        sides cannot drift apart the way reading fileSavePath on demand allowed.
        """
        self._session_level = str(level or '')
        try:
            self._session_area = max(1, min(4, int(area or 1)))
        except (TypeError, ValueError):
            self._session_area = 1

    def sessionLevelName(self):
        """
        The level the session is on, or '' outside a session.

        Public because the save path and the dirty check both need it and
        neither should be re-deriving it from fileSavePath.
        """
        if not self.is_active:
            return ''
        return self._session_level

    def isSaveAuthority(self):
        """
        Whether this peer may write the session's level to disk.

        True outside a session - an editor not in a session owns its own file,
        and every caller reads better as "may I save" than as "am I in a
        session and if so am I the host".
        """
        if not self.is_active:
            return True
        return self._is_save_authority

    def hasSessionFile(self):
        """
        Whether the file this editor has open is the one the session is on.

        The question `fileSavePath` cannot answer on its own: both peers can
        hold a file called '01-01' that resolves through different stage paths
        to different levels (known open 10.1), and a client that never opened
        this level has no file at all (10.1b). Names are compared here; phase 2
        adds the content fingerprint that settles the first case properly.

        False outside a session, because the question is meaningless there -
        callers should ask isSaveAuthority() instead.
        """
        if not self.is_active:
            return False

        if not self._session_level:
            # The session is on a level that has never been saved, so no file
            # can correspond to it.
            return False

        return self._currentLevelName() == self._session_level

    def _onLevelSwitchProposed(self, session_id, level, area):
        """
        Host side: a Full client asked to move the session (phase 3d).

        Runs on the main thread, because answering it may open a dialog and will
        load a level.

        Only the host reaches here - session.py emits this from the host's own
        message loop - but it is checked anyway rather than assumed: a client
        that somehow got here would be acting as the authority.
        """
        if not self.is_active or not self.is_host:
            return False

        host_session = self.host_session
        if host_session is None:
            return False

        participant = host_session.find(session_id)
        if participant is None:
            # The client left between asking and being answered. Nothing to
            # refuse and nobody to tell, so the session simply stays put.
            return False

        if not self._resolveProposal(participant, level, area):
            return False

        # Accepted. Tell the proposing client so *before* loading anything.
        #
        # The obvious implementation is to let the host's own load broadcast the
        # switch and treat that broadcast as the acceptance - and it does
        # release the wait. But it is not guaranteed to happen: the broadcast is
        # skipped when the host is already on the requested level and area
        # (_onLevelSwitchRequested returns early), and while a level is being
        # loaded on behalf of the session (_suppress_level_notify). In both
        # cases the host has agreed, and the client would wait out the full
        # timeout and then be told the host never answered.
        #
        # An explicit acceptance costs one small message and removes the whole
        # class. The broadcast still arrives and is still what loads the level
        # everywhere; this only ends the waiting.
        self._acceptProposal(participant, level, area)

        return self._onLevelSwitchRequested(level, _clamp_area(area))

    def _acceptProposal(self, participant, level, area):
        """
        Tells one client its proposal was accepted.

        Sent as an area_switch to that client alone: it is the same message the
        broadcast uses, so the client needs no new type and the one it receives
        first wins. Both say the same thing, so a duplicate is harmless - the
        second is skipped by the "already have it" guard.
        """
        connection = getattr(participant, 'connection', None)
        if connection is None:
            return False

        try:
            connection.send_type(protocol.T_AREA_SWITCH, {
                'area': _clamp_area(area),
                'level': str(level or ''),
            })
        except Exception:
            return False

        return True

    def _onLevelSwitchRequested(self, level, area):
        """
        Loads the level and area a peer moved the session to.

        Runs on the main thread. Guarded against loading what we already have,
        which would otherwise recurse: LoadLevel calls notifyLevelChanged, which
        is what sent or received this in the first place.
        """
        if not self.is_active:
            return False

        # If we were waiting for an answer to our own proposal, this is it: the
        # host only broadcasts a switch once it has accepted one. Released
        # before the load, so the wait's busy indicator is gone before the
        # loading one appears (Block C - B3, phase 3d).
        if self._proposal == 'waiting':
            self._proposal = 'accepted'

        # Where the session is, recorded before anything can decline to load it.
        # A peer that cannot open the level is still *in* a session that moved -
        # that is precisely the 10.1b case, where the client has no copy of the
        # file - and a save or a dirty check asking "where are we" during that
        # window must not be told "wherever this editor happens to be".
        self._setSessionLevel(level, area)

        if level == self._currentLevelName() and area == self._areaNumber():
            return False

        if self._patchPending():
            # Same reason as in _onConnected: loading now would read tilesets
            # through the outgoing patch, and the incoming one has no Stage
            # folder yet. Only the latest switch is worth keeping - the session
            # is somewhere specific, not everywhere it passed through.
            self._deferred_level = (level, area)
            self._appendStatus(
                'Waiting for the %s patch before loading %s.'
                % (self._transfer_patch, level or 'the area'))
            return False

        window = self.window
        if not hasattr(window, 'LoadLevel'):
            return False

        if not level:
            # An empty name would mean LoadLevel(None), which creates a *new*
            # untitled level rather than loading anything - so a peer with an
            # unsaved level would silently blank everyone else's. Switch area
            # within the level we already have instead.
            current = str(getattr(window, 'fileSavePath', '') or '')
            if not current:
                self._appendStatus(
                    'The session moved to a level that has never been saved, '
                    'so it cannot be opened here.')
                return False

            self._appendStatus('Switching to area %d.' % area)
            if not self._loadLevelQuietly(current, True, area):
                return False
            return self._afterSessionLoad()

        # The host publishes its copy of the level on every change (Fact 3), so
        # wait for that rather than opening whatever this machine has under the
        # same name. Two reasons, and the second is the important one:
        #
        #  - it is the same file, so the load is right rather than approximately
        #    right. Resolving '01-01' locally is what let two peers open
        #    different levels while the session reported a match (known open
        #    10.1);
        #  - it avoids loading twice. The client used to open its own copy and
        #    then have the host's state applied over it, which is the "loads his
        #    own level first, then syncs" Zement described.
        #
        # Bounded, and it falls back: if the file does not arrive, the local
        # copy is opened as before, because a slow or missing publication must
        # not leave a client with no level at all.
        if self._awaitPublishedLevel(level):
            return True

        self._appendStatus('Loading %s from the session.' % level)

        if not self._loadLevelQuietly(level, False, area):
            self._appendStatus(
                'Could not load %s - check that you have the same patch.'
                % level)
            return False

        return self._afterSessionLoad()

    PUBLICATION_TIMEOUT_SECONDS = 20.0

    def _awaitPublishedLevel(self, level):
        """
        Waits briefly for the host's copy of a level it has just moved to.

        Returns True if the file arrived and was opened, so the caller should
        not load a local copy.

        Keeps the event loop running, for the same reason the switch proposal
        does: the file arrives on the session's reader thread and is delivered
        through the bridge, so blocking here would stop the very delivery being
        waited for.

        Declines immediately when the host cannot publish, so a retail session
        or a host on an unsaved level goes straight to the old path instead of
        stalling for the timeout on every switch.
        """
        if self.is_host or not self.is_active:
            return False

        if not self._patchId():
            # No _collab folder to receive it - retail. The local copy is all
            # there is.
            return False

        self._pending_publication = True
        deadline = time.monotonic() + self.PUBLICATION_TIMEOUT_SECONDS
        arrived = False

        try:
            with _BusyIndicator(self.window,
                                'Getting %s from the host...' % level):
                while self._pending_publication:
                    if time.monotonic() >= deadline:
                        debuglog.log('client', 'publication timed out',
                                     level=level)
                        break

                    if not self.is_active:
                        break

                    QtWidgets.QApplication.processEvents(
                        QtCore.QEventLoop.ProcessEventsFlag
                        .ExcludeUserInputEvents, 50)
                else:
                    # The loop ended because _openPublishedLevel cleared the
                    # flag, which it only does after the file is open.
                    arrived = True
        finally:
            # Cleared however this ended, so a timed-out wait cannot leave the
            # client believing a publication is still coming.
            self._pending_publication = False

        return arrived

    def _loadLevelQuietly(self, name, is_full_path, area):
        """
        Loads a level without announcing it back to the session.

        The suppression flag is a flag rather than a parameter because
        LoadLevel is reached through several handlers, and the recursion has to
        be blocked wherever it is called from. Cleared in a finally, so a failed
        load cannot leave the session permanently mute.
        """
        label = os.path.basename(str(name)) if name else 'the level'

        # Loading replaces the scene's contents, so cursors drawn against the
        # old level must go rather than linger over the new one.
        if self.presence is not None:
            self.presence.clear()

        self._suppress_level_notify = True
        try:
            with _BusyIndicator(self.window,
                                'Loading %s from the session...' % label):
                return bool(self.window.LoadLevel(name, is_full_path, area))
        except Exception as exc:
            self._appendStatus('That level could not be loaded: %s' % exc)
            return False
        finally:
            self._suppress_level_notify = False

    def _afterSessionLoad(self):
        """
        Rebuilds the shared state after loading what the session moved to.

        A host redistributes; a client asks for the items belonging to the area
        it has just opened.
        """
        if self.is_host:
            self.refmap = sync.RefMap(origin='host', is_authority=True)
            self._seedRefMap()
            self.host_session.set_room_info(self._roomInfo())
            self._broadcastLevelChange()
            if not self._publishLevelFile():
                self._broadcastSnapshot()
        else:
            # Now that the level is open, the fingerprints describe the files
            # this peer is actually looking at. Comparing any earlier would
            # hash whatever it had open before the session moved it.
            # Distinguished carefully: _checkContentMatches returns True both
            # for "verified identical" and for "could not verify" (no host
            # fingerprint, an older host, retail). Those want opposite answers
            # here - a peer that could not verify must still be sent the items,
            # or it sits on an empty or stale level forever. So the snapshot is
            # skipped only on a *positive* verification against a file this peer
            # actually opened from the host.
            matches = (self._checkContentMatches()
                       and bool(self._host_fingerprint)
                       and self.hasSessionFile())

            # Only ask for the items if this peer might actually be missing
            # something. Before Fact 3 the snapshot was the *only* way a client
            # got a level's contents, so resyncing here was unconditional and
            # correct. It is not any more: when the file this peer just opened
            # is byte-identical to the host's, the snapshot that comes back
            # rebuilds a scene it already has - item by item, on the main
            # thread, which is the two-minute cost the whole feature exists to
            # avoid. Zement saw exactly this on 2026-08-11: "content matches
            # the host" immediately followed by a resync and a 729-item
            # snapshot.
            #
            # A mismatch still resyncs, and so does a peer that could not
            # verify at all: being slow is recoverable, showing a level the
            # rest of the session is not editing is not.
            if not matches:
                self._requestResync(force=True)

        return True

    def _broadcastLevelChange(self):
        """
        Tells every client which level and area the session is now on.
        """
        if not self.is_host or self.server is None:
            return False

        message = protocol.make_message(protocol.T_AREA_SWITCH,
                                        self._levelChangePayload())
        for connection in self.server.authenticated_connections():
            connection.send(message)

        return True

    def _broadcastSnapshot(self, session_id=''):
        """
        Sends the current level to one peer, or to all of them when no session
        id is given.
        """
        if not self.is_host or self.refmap is None or self.server is None:
            return False

        try:
            with _BusyIndicator(self.window, 'Sharing the level...'):
                payload = sync.build_snapshot(
                    self.refmap, area_number=self._areaNumber())
        except sync.SyncError as exc:
            self._appendStatus('The level could not be shared: %s' % exc)
            return False

        message = protocol.make_message(protocol.T_SNAPSHOT, payload)
        sent = 0
        for connection in self.server.authenticated_connections():
            if not session_id or connection.session_id == session_id:
                connection.send(message)
                sent += 1

        debuglog.log('op-out', 'snapshot sent', peers=sent,
                     items=len(payload.get('items') or []))
        return sent > 0

    @staticmethod
    def _areaNumber():
        area = getattr(globals_, 'Area', None)
        try:
            return max(1, min(4, int(getattr(area, 'areanum', 1) or 1)))
        except (TypeError, ValueError):
            return 1

    def notifyRoomInfoChanged(self):
        """
        Republishes the room info after the host switched patch or level.

        A no-op for a client, which does not own the room info, and for the host
        when nothing actually changed.
        """
        if self.host_session is None:
            return False

        changed = self.host_session.set_room_info(self._roomInfo())
        if changed:
            patch = self._patchId()
            self._appendStatus(
                'You are now using: %s. Clients have been told.'
                % (patch or 'the retail game'))

        return changed

    def _kick(self, session_id):
        if self.host_session is not None:
            self.host_session.kick(session_id)

    def _ban(self, session_id):
        if self.host_session is None:
            return
        self.host_session.ban(session_id)
        self._persistBans()

    def _setRole(self, session_id, role):
        if self.host_session is not None:
            self.host_session.set_role(session_id, role)

    def _restoreBans(self):
        for address, nick in collab_dialogs.load_ban_list():
            self.host_session.bans.add(address, nick)

    def _persistBans(self):
        if self.host_session is None:
            return
        collab_dialogs.save_ban_list(
            [(address, nick) for address, nick, _when
             in self.host_session.bans.entries()])

    # -- slots (main thread) ------------------------------------------------

    def _onRoster(self, participants):
        if self.status_window is not None:
            self.status_window.setRoster(participants)

        # Drop transfer state for peers that are no longer here. A client that
        # disconnects mid-transfer never sends file_done, and a stale id in this
        # set makes _transferInProgress() permanently true - which would stop
        # the host publishing level files for the rest of the session, silently.
        # The roster is the authoritative list of who is present, so it is the
        # right place to notice.
        if self.is_host and self._transferring_peers:
            present = {str(entry.get('session_id', ''))
                       for entry in (participants or [])
                       if isinstance(entry, dict)}
            departed = self._transferring_peers - present
            if departed:
                self._transferring_peers -= departed
                debuglog.log('host', 'dropped transfer state for departed peers',
                             count=len(departed))

        # The overlay needs it too: nicknames and colours come from the roster,
        # and a peer that left must lose its cursor.
        if self.presence is not None:
            self.presence.setRoster(participants)

    def _onChat(self, nick, text, kind):
        if self.status_window is None:
            return

        # A client's roster carries the nickname; the host's events carry it
        # directly. Resolve it here so the log always shows a name.
        if not nick and self.client_session is not None:
            nick = ''

        self.status_window.appendChat(nick, text, kind)

    def _onStatus(self, text):
        self._appendStatus(text)

    def _onError(self, text):
        self._appendStatus(text)

    def _onConnected(self, room_info):
        self._appendStatus('Connected.')
        self._startPresence()
        self._checkPatch(room_info)

        area = int(room_info.get('area', 1) or 1)

        # Where the session is, as the host reports it. This is the client's
        # first answer to that question and it holds until an area_switch
        # replaces it - including through a deferred patch transfer, where the
        # level cannot be loaded yet but the session is already somewhere.
        self._setSessionLevel(str(room_info.get('level_name', '') or ''), area)

        # Checked after the level loads, not now; see _onRoomInfoChanged.
        self._host_fingerprint = dict(room_info or {})

        if self._patchPending():
            # The patch is still arriving, so asking for the level now would
            # have it drawn with the tilesets of whatever patch is loaded - and
            # the Stage folder of the incoming one is not even known yet, which
            # is what produced a "tileset not found" warning before the user had
            # been asked for the path. Replayed by _resumeDeferredLoad.
            self._deferred_snapshot_area = area
            return

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_SNAPSHOT_REQUEST, {'area': area}))

    def _onRoomInfoChanged(self, room_info):
        """
        The host switched patch or level. Re-run the patch check, since what the
        client needs may have changed since it joined.
        """
        patch = str(room_info.get('patch_id', '') or '')
        self._appendStatus(
            'The host is now using: %s.' % (patch or 'the retail game'))

        # Kept for the content check, which runs after the level has loaded -
        # comparing before that would fingerprint whatever this editor had open
        # a moment ago rather than what the session moved it to.
        self._host_fingerprint = dict(room_info or {})

        self._checkPatch(room_info)

    def _onDisconnected(self, reason):
        self._appendStatus(reason or 'Disconnected.')

        if self.is_active:
            self._teardown()

        # Disable the controls but keep the window open, so the chat log and the
        # reason for the disconnect stay readable.
        if self.status_window is not None:
            self.status_window.setSessionEnded()

    def _onRejected(self, reason):
        QtWidgets.QMessageBox.warning(
            self.window, 'Collaboration',
            'The host refused the connection.\n\n%s\n\nCheck that you pasted '
            'the whole join code, and that the host has not banned you or '
            'changed the code.' % reason)
        self._teardown()

    def _onRoleChanged(self, role):
        self._appendStatus(
            'Your access level is now: %s.'
            % ('full access' if role == protocol.ROLE_FULL else 'canvas editing'))

        # Promotion and demotion change what a client may switch, so the
        # controls follow the role rather than only the session.
        self.applyEditingPermissions()

    def _onOperationRejected(self, reason, op_id=''):
        # A refused switch proposal is not a refused edit. Nothing was applied,
        # so there is nothing to reconcile and a resync here would ask the host
        # for a snapshot of the level we are already on. Release the waiting
        # proposal instead (Block C - B3, phase 3d).
        if op_id == protocol.T_AREA_SWITCH and self._proposal == 'waiting':
            self._proposal = ('The host declined: %s.' % reason if reason
                              else 'The host declined the change.')
            return

        # The client's optimistic edit was refused. Ask for a fresh snapshot
        # rather than guessing what the host's state is now.
        self._appendStatus('A change was not accepted: %s' % reason)
        self._requestResync()

    def _onOperation(self, payload, sender_id):
        """
        Applies a remote operation. Main thread, so touching the scene is safe.
        """
        debuglog.log('op-in', 'received', kind=payload.get('kind'),
                     targets=len(payload.get('targets') or []),
                     sender=sender_id, have_refmap=self.refmap is not None)

        if self.refmap is None:
            return

        try:
            sync.apply_remote(payload, self.refmap,
                              sprite_format=_sprite_format())
        except sync.UnknownRefError:
            # Benign and self-correcting: we raced a removal, or joined
            # mid-edit. A resync is the right answer, not an error dialog.
            self._requestResync()
            return
        except sync.SyncError as exc:
            self._appendStatus('A change could not be applied: %s' % exc)
            return
        except RuntimeError as exc:
            # A destroyed Qt object reached the apply path. RefMap.require now
            # catches the common case, but an item can also be destroyed part
            # way through applying a multi-target op. Treated as divergence
            # rather than allowed to escape: this used to reach the excepthook
            # and put a traceback in log.txt while the session carried on
            # quietly out of sync.
            debuglog.log('op-in', 'stale item during apply', error=str(exc))
            self._requestResync()
            return

        if self.is_host:
            self._rebroadcast(payload, sender_id)

    def _rebroadcast(self, payload, sender_id):
        """
        The host is the sequencer: an accepted operation goes back out to every
        other peer.
        """
        if self.server is None:
            return

        message = protocol.make_message(protocol.T_OP, payload, sender=sender_id)
        for connection in self.server.authenticated_connections():
            if connection.session_id != sender_id:
                connection.send(message)

    # -- outbound operations ------------------------------------------------

    def broadcastCommand(self, command, undone=False):
        """
        Sends a locally pushed undo command to the other peers.

        Called from UndoStack.push/undo/redo, so this is the main thread and the
        edit has already been applied. Returns True if anything was sent.

        `undone` sends the inverse edit, for a command that was just reverted.
        Peers apply it as an ordinary operation: undo stays local and per-user,
        but the level has to converge either way.
        """
        if not self.is_active or self.refmap is None:
            return False

        try:
            if undone:
                payload = broadcast.encode_undo(command, self.refmap)
                self._rebindResurrectedItems(command, payload)
            else:
                payload = broadcast.encode_command(command, self.refmap)
        except broadcast.BroadcastError as exc:
            # Our view of the level and the ref map have drifted. Resyncing is
            # the honest answer; carrying on would diverge silently.
            #
            # Logged because this path used to be silent: a client's QPT stroke
            # failed here on every tile, and the log showed only the resulting
            # resync with no hint of what had caused it.
            debuglog.log('op-out', 'command could not be encoded',
                         command=type(command).__name__, error=str(exc))
            self._appendStatus('A change could not be shared: %s' % exc)
            self._requestResync()
            return False

        if payload is None:
            debuglog.log('op-out', 'command not broadcast (no encoder)',
                         command=type(command).__name__)
            return False

        debuglog.log('op-out', 'broadcasting', kind=payload.get('kind'),
                     targets=len(payload.get('targets') or []),
                     as_host=self.is_host)

        if self.is_host:
            message = protocol.make_message(protocol.T_OP, payload)
            peers = self.server.authenticated_connections()
            for connection in peers:
                connection.send(message)
            debuglog.log('op-out', 'sent to peers', peers=len(peers))
            return True

        # A client sends to the host, which authorises and sequences it before
        # relaying. Its own role check here is advisory - the host re-checks -
        # but it turns a silent rejection into an explanation.
        if self.client_session is not None:
            kind = broadcast.op_kind_of(command)
            if kind and not self.client_session.may_send_op(kind):
                self._appendStatus(
                    'Your access level does not allow that change (%s).' % kind)
                return False

        self.client.send(protocol.make_message(protocol.T_OP, payload))
        return True

    # -- presence -----------------------------------------------------------

    def _startPresence(self):
        """
        Begins showing other people on the canvas, and reporting where we are.

        Everything here is per-session: the overlay, the throttle, and the two
        view connections. Built on start rather than kept alive permanently so
        that outside a session there is nothing to leak and nothing to draw.
        """
        window = self.window
        scene = getattr(window, 'scene', None)
        view = getattr(window, 'view', None)
        if scene is None:
            return

        self.presence = collab_presence.PresenceOverlay(scene)
        self.presence.setOverview(getattr(window, 'levelOverview', None))
        self._applyPresencePreferences()

        self._cursor_coalescer = transport.PresenceCoalescer(
            rate=PRESENCE_UPDATES_PER_SECOND)

        # A held cursor position would otherwise be stranded when the pointer
        # stops: the last movement is exactly the one worth showing.
        self._live_drag_sent = {}
        self._last_view_rect = None

        # One timer drives all three periodic jobs: flushing a held cursor,
        # streaming an in-progress drag, and reporting the visible rectangle.
        # Three timers at the same interval would only be three ways to forget
        # to stop one.
        self._presence_timer = QtCore.QTimer(window)
        self._presence_timer.setInterval(PRESENCE_FLUSH_MS)
        self._presence_timer.timeout.connect(self._onPresenceTick)
        self._presence_timer.start()

        if view is not None and not self._presence_connected:
            view.PositionHover.connect(self._onLocalCursorMoved)
            view.PositionClicked.connect(self._onLocalClick)
            self._presence_connected = True

    def _stopPresence(self):
        if self._presence_timer is not None:
            self._presence_timer.stop()
            self._presence_timer = None

        view = getattr(self.window, 'view', None)
        if view is not None and self._presence_connected:
            # Disconnect explicitly: the view outlives the session, so a
            # connection left behind would keep sending on a dead transport
            # and would be duplicated by the next session.
            try:
                view.PositionHover.disconnect(self._onLocalCursorMoved)
                view.PositionClicked.disconnect(self._onLocalClick)
            except TypeError:
                pass
        self._presence_connected = False

        if self.presence is not None:
            self.presence.shutdown()
            self.presence = None

        self._cursor_coalescer = None

    def _applyPresencePreferences(self):
        """
        Applies this machine's cursor/click display choices.

        Purely local, and purely about display: each machine decides what it
        shows, and every machine always broadcasts. Making the preference
        suppress sending would mean a user who dislikes the clutter silently
        disappears for everyone else, which is not what the setting says.
        """
        if self.presence is None:
            return

        mode = self.settings.get('cursors', collab_dialogs.CURSORS_ON_MOVE)
        self.presence.setPreferences(
            show_cursors=(mode != collab_dialogs.CURSORS_NEVER),
            cursors_while_dragging_only=(mode == collab_dialogs.CURSORS_ON_MOVE),
            show_clicks=bool(self.settings.get('clicks', True)))

    def reloadPresencePreferences(self):
        """
        Re-reads the preferences after the settings dialog was accepted, so a
        change takes effect without restarting the session.
        """
        self.settings = collab_dialogs.load_collab_settings()
        self._applyPresencePreferences()
        self._configureDebugLog()

    def _onLocalCursorMoved(self, x, y):
        if not self.is_active:
            return

        # Always sent, whatever this machine displays: 'on move' and 'never'
        # are display choices for what *we* draw, and honouring them here would
        # make this machine invisible to everyone else.
        if self._cursor_coalescer is None:
            return

        # Reading the mouse buttons rather than a per-tool drag flag keeps this
        # correct whichever tool is active.
        dragging = (QtWidgets.QApplication.mouseButtons()
                    != QtCore.Qt.MouseButton.NoButton)

        payload = self._cursor_coalescer.offer(
            sync.encode_presence_cursor(x, y, dragging=dragging))
        if payload is not None:
            self._sendPresence(payload)

    def _flushCursor(self):
        if not self.is_active or self._cursor_coalescer is None:
            return

        payload = self._cursor_coalescer.flush()
        if payload is not None:
            self._sendPresence(payload)

    def _onPresenceTick(self):
        """
        The periodic presence work. Individually guarded, because one of these
        failing must not stop the other two.
        """
        for job in (self._flushCursor, self._broadcastLiveDrag,
                    self._broadcastViewRect):
            try:
                job()
            except Exception:
                pass

    def _liveDragItems(self):
        """
        The items whose geometry is changing under the mouse right now.

        Two sources, because the editor has two gestures that change geometry
        live:

        - the selection, for a left-button drag or a corner-grabber resize;
        - view.currentobj, for right-button painting, where the item is created
          on press and then stretched as the pointer moves. A painted item is
          not selected, so the selection alone misses it entirely.

        QPT is deliberately excluded. Its stroke is a bulk edit that produces
        one command covering many objects, and streaming each tile as it
        appears would send a stream of adds that its own single command then
        re-sends on commit.
        """
        window = self.window
        scene = getattr(window, 'scene', None)
        if scene is None:
            return []

        items = [item for item in scene.selectedItems() if hasattr(item, 'objx')]

        view = getattr(window, 'view', None)
        current = getattr(view, 'currentobj', None)
        if current is not None:
            painted = current if isinstance(current, (list, tuple)) else (current,)
            for item in painted:
                if item is not None and hasattr(item, 'objx'):
                    if not any(item is existing for existing in items):
                        items.append(item)

        return items

    def _broadcastLiveDrag(self):
        """
        Sends the in-progress geometry of items being dragged, resized or
        painted.

        Without this a peer sees nothing until the mouse is released and the
        undo command is pushed, so a long gesture looks frozen and then jumps.

        These are ordinary add/move/resize ops, so a peer applies them through
        the normal path and needs no concept of a gesture. They are *not*
        pushed onto anyone's undo stack: the sender records one command on
        release, and the receiver applies remote ops inside the guard as
        always. So a gesture remains one undo step for the person who made it,
        however many intermediate frames were sent.
        """
        if not self.is_active or self.refmap is None:
            return

        if QtWidgets.QApplication.mouseButtons() == QtCore.Qt.MouseButton.NoButton:
            self._live_drag_sent = {}
            return

        created = []
        moves = []
        resizes = []

        for item in self._liveDragItems():
            key = id(item)
            has_size = hasattr(item, 'width') and hasattr(item, 'height')
            state = ((item.objx, item.objy, item.width, item.height) if has_size
                     else (item.objx, item.objy))

            # Only what actually changed since the last frame: a stationary
            # selection would otherwise stream its position continuously.
            if self._live_drag_sent.get(key) == state:
                continue
            self._live_drag_sent[key] = state

            if self.refmap.ref_for(item) is None:
                # A painted item the peer has never heard of. It has to be
                # announced before it can be moved, or every following frame
                # references an item that does not exist there yet.
                created.append(item)
                continue

            if has_size:
                resizes.append((item, state, state))
            else:
                moves.append((item, state, state))

        try:
            if created:
                self._sendLiveOp(sync.encode_add(self.refmap, created))
            if moves:
                self._sendLiveOp(sync.encode_move(self.refmap, moves))
            if resizes:
                self._sendLiveOp(sync.encode_resize(self.refmap, resizes))
        except sync.SyncError:
            # Mid-drag is the worst moment to interrupt the user. The release
            # will send the authoritative positions anyway.
            pass

    def _sendLiveOp(self, payload):
        try:
            if self.is_host:
                message = protocol.make_message(protocol.T_OP, payload)
                for connection in self.server.authenticated_connections():
                    connection.send(message)
            elif self.client is not None:
                self.client.send(protocol.make_message(protocol.T_OP, payload))
        except Exception:
            pass

    def _onLocalClick(self, x, y):
        if not self.is_active:
            return
        self._sendPresence(sync.encode_presence_click(x, y))

    def _broadcastViewRect(self):
        """
        Reports which part of the level this machine is looking at, so the
        others can draw it on their Level Overview.

        Polled rather than driven by a scroll signal: the visible rectangle
        also changes on zoom and on resize, and polling one rectangle at the
        presence rate is cheaper than being right about every source of change.
        Only sent when it actually differs from the last one.
        """
        if not self.is_active:
            return

        view = getattr(self.window, 'view', None)
        if view is None:
            return

        try:
            rect = view.mapToScene(view.viewport().rect()).boundingRect()
        except Exception:
            return

        current = (int(rect.x()), int(rect.y()),
                   int(rect.width()), int(rect.height()))
        if current == self._last_view_rect:
            return
        self._last_view_rect = current

        self._sendPresence(sync.encode_presence_view(*current))

    def _sendPresence(self, payload):
        """
        Sends a presence payload. Never fatal: presence is decoration, so a
        failure here must not disturb editing.
        """
        try:
            if self.is_host:
                if self.host_session is not None:
                    self.host_session.broadcast_presence(payload)
            elif self.client is not None:
                self.client.send(
                    protocol.make_message(protocol.T_PRESENCE, payload))
        except Exception:
            pass

    def _onPresence(self, payload, sender_id):
        """
        Draws a peer's cursor or click. Main thread, via the bridge.
        """
        if self.presence is None or self.refmap is None:
            return

        # The host relays a client's presence to the others, so a peer can see
        # its own payload come back. Drawing it would put a second cursor under
        # the user's real one.
        if sender_id and self._isOwnSessionId(sender_id):
            return

        try:
            decoded = sync.decode_presence(payload, self.refmap)
        except sync.SyncError:
            # A malformed payload from a peer is not worth reporting: it cannot
            # hurt anything, and presence arrives constantly.
            return

        kind = decoded.get('kind')
        if kind == 'cursor':
            self.presence.showCursor(sender_id, decoded['x'], decoded['y'],
                                     dragging=decoded.get('dragging', False))
        elif kind == 'click':
            self.presence.showClick(sender_id, decoded['x'], decoded['y'])
        elif kind == 'view':
            self.presence.showView(sender_id, decoded['x'], decoded['y'],
                                   decoded['w'], decoded['h'])

    def _isOwnSessionId(self, session_id):
        if self.client_session is not None:
            return session_id == getattr(self.client_session, 'session_id', None)
        if self.host_session is not None:
            host = getattr(self.host_session, 'host_participant', None)
            return session_id == getattr(host, 'session_id', None)
        return False

    def _rebindResurrectedItems(self, command, payload):
        """
        Re-registers items brought back by undoing a removal.

        Encoding a removal forgets its references, since the items are gone. A1
        then restores *the same objects* on undo, so the references have to come
        back too - and specifically the original ones, because peers still know
        those items by them and the inverse op we are about to send recreates
        them under exactly those references.

        Without this the resurrected items are unreferenced locally, and the
        next edit to one of them fails to encode and triggers a resync.
        """
        if payload is None or payload.get('kind') != 'add':
            return

        items = [item for item in getattr(command, 'items', None) or []
                 if item is not None]
        targets = payload.get('targets') or []
        if len(items) != len(targets):
            # Shapes disagree, so pairing them up would bind references to the
            # wrong objects. A resync is recoverable; a mis-bound ref is not.
            raise broadcast.BroadcastError(
                'could not match restored items to their references')

        for item, target in zip(items, targets):
            ref = target.get('ref')
            if ref:
                self.refmap.bind(ref, item)

    def _onSnapshot(self, payload):
        if self.refmap is None:
            return

        if self._patchPending():
            # A snapshot the host sent on its own initiative, or one already in
            # flight when the transfer started. Applying it would populate the
            # area with items whose tilesets and sprite data are about to be
            # replaced; the resync after the patch loads brings a current one.
            self._deferred_snapshot_area = self._areaNumber()
            return

        count = len(payload.get('items') or []) if isinstance(payload, dict) else 0

        try:
            with _BusyIndicator(
                    self.window,
                    'Loading the level from the host (%d items)...' % count):
                sync.apply_snapshot(payload, self.refmap,
                                    sprite_format=_sprite_format())
        except sync.SyncError as exc:
            QtWidgets.QMessageBox.warning(
                self.window, 'Collaboration',
                'The level could not be loaded from the host: %s' % exc)
            return

        self._appendStatus('Level loaded from the host.')

        # A snapshot is the *usual* way a client arrives at a level - joining, or
        # being resynced - and it does not go through _onLevelSwitchRequested, so
        # checking only there missed the common case entirely. Zement's phase 2
        # test found this: the client downloaded the patch, received a snapshot,
        # and no mismatch was ever reported (2026-08-09).
        self._checkContentMatches()

    def _configureDebugLog(self):
        """
        Turns the diagnostic log on or off to match the current preference.

        The path is reported in the status window when it is on, because a log
        nobody can find helps nobody.
        """
        if self.settings.get('debug_log'):
            path = debuglog.enable(_debug_log_directory())
            if path:
                self._appendStatus('Debug log: %s' % path)
        else:
            debuglog.disable()

    def _seedRefMap(self):
        """
        Mints a reference for every item currently in the area.

        Guarded rather than allowed to fail: an empty or half-loaded area is a
        normal state (Reggie can host before a level is open), and hosting must
        not depend on there being anything to share yet.
        """
        if self.refmap is None:
            return 0

        try:
            return self.refmap.seed(getattr(globals_, 'Area', None))
        except Exception:
            return 0

    def _onSnapshotRequested(self, session_id, area):
        """
        Sends the current level to a client that asked for it.

        Host only, and on the main thread: build_snapshot walks the scene, which
        is exactly what must not happen on a reader thread.

        The requested `area` is deliberately ignored. The host can only share
        the area it currently has open - serving a different one would mean
        loading it here, which would yank the host's own editor to another area
        because a client asked. The snapshot names the area it actually
        contains, so a client that wanted another one can see that it did not
        get it.
        """
        self._broadcastSnapshot(session_id)

    def _requestResync(self, force=False):
        """
        Asks the host for a fresh copy of the level.

        Rate limited, because the thing that triggers a resync is usually the
        thing that makes the next edit fail too: without this, one broken
        reference produced a snapshot request per edit, which is the flood of
        "client is loading the level" lines in Zement's log.

        `force` bypasses the limit for a deliberate user action - loading
        another level locally - where the request is not a symptom of a failure
        loop and the user is waiting for it.
        """
        if self.client is None:
            return False

        if self._patchPending():
            # The answer would only be discarded by _onSnapshot, and asking
            # anyway would spend the rate-limit window on a snapshot built for
            # the patch that is being replaced. Noted instead, so the resume
            # after the patch loads fetches a current one.
            self._deferred_snapshot_area = self._areaNumber()
            return False

        now = time.monotonic()
        if not force and now - self._last_resync < RESYNC_INTERVAL_SECONDS:
            return False

        self._last_resync = now
        debuglog.log('client', 'requesting resync')
        self.client.send(protocol.make_message(
            protocol.T_SNAPSHOT_REQUEST, {'area': 1}))
        return True

    # -- patches ------------------------------------------------------------

    def _checkPatch(self, room_info):
        """
        Decides how the host's patch should be obtained, and acts on it.

        The four outcomes of files.patch_requirement map to four behaviours:

        - LOCAL       nothing to do.
        - HOST        ask the host for its data files. No prompt: connecting to
                      a session is consent to the data-only transfer (Zement,
                      2026-08-06). What travels is PNG/XML/TXT and never Python,
                      the peer is already pinned by the join code, and the caps
                      in files.py still bound it - so the prompt would be asking
                      permission for the thing the user just did.
        - CATALOG     prompt. This one *is* asked, because it fetches from a
                      third party over the internet rather than from the peer
                      the user chose to join.
        - UNAVAILABLE say so, and leave.

        Declining, or being unable to get the patch at all, disconnects: without
        the patch the client cannot hold the same level state, so a read-only
        seat would be a seat looking at the wrong level.
        """
        if self.client is None:
            # Host side. The host defines the patch, so there is nothing to
            # check - and running the client path here would have the host
            # asking itself for files.
            return

        catalog = _catalog_manager()

        # The client's own choice of where a missing patch may come from. AUTO
        # permits both and is the default; the other two are exclusive. The
        # host never consults this - it is the client deciding what it accepts.
        source_setting = (self.settings.get('patch_source')
                          or collab_dialogs.PATCH_SOURCE_AUTO)
        allow_catalog = source_setting in (collab_dialogs.PATCH_SOURCE_AUTO,
                                           collab_dialogs.PATCH_SOURCE_CATALOG)
        allow_host = source_setting in (collab_dialogs.PATCH_SOURCE_AUTO,
                                        collab_dialogs.PATCH_SOURCE_HOST)

        requirement = files.patch_requirement(room_info, catalog,
                                              allow_host_transfer=allow_host,
                                              allow_catalog=allow_catalog,
                                              extra_dirs=_external_patch_dirs())

        source = requirement['source']
        patch_id = requirement['patch_id']

        if source == files.SOURCE_LOCAL:
            # Having the patch and *using* it are different questions, and only
            # the first one patch_requirement answers. A client that owns the
            # host's patch but has another one loaded is exactly the state
            # SOURCE_LOCAL reports as fine, so returning here left the client
            # sitting on the wrong game the whole session - including after a
            # mid-session switch, where it is the only thing that had changed.
            self._switchToPatch(patch_id)

            # Having the patch is not having the host's *game data*. The patch
            # says which tilesets a level names; the levels and tilesets live in
            # whatever Stage folder this machine points at, which is a local
            # preference and routinely differs from the host's. That is known
            # open 10.1, and it is why this route needs a transfer of its own
            # even though nothing is missing in the patch sense (round 2, R1).
            self._requestSessionAssets(patch_id)
            return

        self._appendStatus(requirement['message'])

        if self._transfer is not None:
            # Already collecting one. This happens when the host changes patch
            # twice in quick succession; finishing the first transfer and
            # re-checking is better than abandoning it half-written.
            self._appendStatus('A patch download is already in progress.')
            return

        if source == files.SOURCE_HOST:
            self._startPatchTransfer(patch_id)

        elif source == files.SOURCE_CATALOG:
            self._installFromCatalog(requirement)

        else:
            self._leaveOverPatch(
                'You cannot join without the %s patch.' % patch_id
                if patch_id else 'The required patch is not available.')

    def _patchPending(self):
        """
        Whether a host transfer is still running, so the level cannot be loaded.

        Keyed on _transfer_patch rather than _transfer because the two are set
        at different moments: the id is stored when T_PATCH_NEED goes out, while
        the TransferSession only exists once the host's manifest comes back. The
        gap between them is exactly when the host's level switch tends to
        arrive, so testing the session alone would let the first one through.

        The catalog route needs no equivalent - see _installFromCatalog.
        """
        return bool(self._transfer_patch)

    def _resumeDeferredLoad(self):
        """
        Loads what the session moved to while the patch was arriving.

        Called after the patch has been loaded - which is after LoadGameDef has
        asked for its Stage folder - so tilesets now resolve against the right
        game. A level switch takes precedence over a bare snapshot request:
        loading the level ends in _afterSessionLoad, which asks for the items
        itself, and doing both would fetch the same area twice.
        """
        level = self._deferred_level
        area = self._deferred_snapshot_area

        self._deferred_level = None
        self._deferred_snapshot_area = None

        if level is not None:
            self._onLevelSwitchRequested(level[0], level[1])
            return

        if area is not None and self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_SNAPSHOT_REQUEST, {'area': int(area)}))

    def _switchToPatch(self, patch_id):
        """
        Loads the patch the session uses, if it is not already loaded.

        Handles the retail direction too: patch_id is '' for the base game, and
        a host switching *back* to retail has to move the client back as well.
        Without that the client stays on the last patch it was told about, which
        is the same bug in the other direction.
        """
        if self._patchId() == patch_id:
            return

        self._reloadPatch(patch_id)

    def _startPatchTransfer(self, patch_id):
        """
        Asks the host for its patch data files.
        """
        self._transfer_patch = patch_id
        self._appendStatus(
            'Asking the host for the %s patch files...' % patch_id)

        self.client.send(protocol.make_message(
            protocol.T_PATCH_NEED, {'patch_id': patch_id}))

    def _requestSessionAssets(self, patch_id):
        """
        Asks the host for its Stage and Texture, without the patch itself.

        The other half of R1: the data-only route already syncs game data, and
        this brings the catalog and already-installed routes to the same state.
        Having the same patch is not enough - the patch names tilesets, but the
        levels and tilesets themselves live in whatever Stage folder each
        machine points at, and that is a local preference. Two peers with the
        same patch id routinely open different bytes under one level name, which
        is known open 10.1.

        Requested unconditionally rather than after comparing. The fingerprint
        covers the level currently open and its tilesets, so it can answer "is
        this level the same" but never "do I have every file the session might
        move to next". Transferring once and being certain is the cheaper
        answer, and it is what makes the file-first path reliable.

        Retail is skipped: there is no patch, so there is no `_collab` folder to
        receive anything, and the base game is identical on both sides by
        definition.
        """
        if self.is_host or self.client is None or not self.is_active:
            return False

        if not patch_id:
            return False

        if patch_id in self._synced_asset_patches:
            # Already have this patch's game data from earlier in the session.
            # room_info is republished on every level and area change, so
            # without this check the whole Stage and Texture folder was fetched
            # again on every switch.
            return False

        if self._transfer is not None or self._transfer_patch:
            # One at a time. A transfer already running will deliver the same
            # files; asking again would interleave two manifests.
            return False

        # Recorded before the request, not after it completes. A transfer takes
        # seconds and room_info can arrive again inside that window - which is
        # exactly the repeat this prevents. A failed transfer clears it again,
        # so a genuine retry is still possible.
        self._synced_asset_patches.add(patch_id)
        self._transfer_patch = patch_id
        self._appendStatus(
            'Getting the session\'s levels and tilesets from the host...')
        debuglog.log('client', 'requesting session assets', patch_id=patch_id)

        self.client.send(protocol.make_message(
            protocol.T_PATCH_NEED,
            {'patch_id': patch_id, 'assets_only': True}))
        return True

    def _installFromCatalog(self, requirement):
        """
        Gets the patch from the Patch Manager, with consent (decision 1).

        Opens the Patch Manager rather than installing directly. There is no
        headless installer to call: downloading is PatchManagerDialog's own
        method, wired to its buttons, its status table and its download
        workers, and driving it from here would mean reimplementing it. Opening
        the real dialog also means the user sees the same download UI, with its
        progress and its errors, that they would use outside a session.

        The consequence, and the reason this is not merely a redirect: the
        install is asynchronous and user-driven, so this cannot know when it
        finished. It re-checks when the dialog closes and acts on the answer.

        Not deferred the way a host transfer is, even though this also keeps the
        event loop running: a catalog install sets the patch's Stage and Texture
        paths itself, so there is no unanswered path question for a level load
        to run ahead of (Zement, 2026-08-09).
        """
        patch_id = requirement['patch_id']

        if not collab_dialogs.confirm_catalog_install(
                self.window, patch_id, requirement.get('patch_version', '')):
            self._leaveOverPatch(
                'You declined to install %s, so you have left the session.'
                % patch_id)
            return

        self._appendStatus(
            'Opening the Patch Manager so you can install %s...' % patch_id)

        try:
            opener = getattr(self.window, 'HandlePatchManager', None)
            if opener is None:
                raise RuntimeError('the Patch Manager is not available')
            opener()
        except Exception as exc:
            debuglog.log('client', 'patch manager failed', error=str(exc))
            self._leaveOverPatch(
                'The Patch Manager could not be opened: %s' % exc)
            return

        # The dialog has closed. Ask the filesystem again rather than assuming
        # the user went through with it - they may have closed it untouched,
        # or installed something else.
        #
        # Retried rather than asked once. The Patch Manager downloads and
        # unpacks on a worker thread, so closing the dialog does not guarantee
        # the last file has been written: a single check can run before the
        # patch's main.xml exists and conclude nothing was installed. Mone was
        # dropped from a session that way after a download that had in fact
        # succeeded, and it did not reproduce - which is what a race looks like.
        if self._waitForInstalledPatch(patch_id):
            self._appendStatus('%s is installed.' % patch_id)
            self._reloadPatch(patch_id)

            # The catalog gives the patch and its own Stage/Texture, which are
            # the *published* ones - not the host's working copies. Zement's
            # MidnightWii test showed the difference plainly: identical patch id
            # and version on both sides, different level bytes. So this route
            # syncs game data too (round 2, R1).
            self._requestSessionAssets(patch_id)
            return

        self._leaveOverPatch(
            '%s was not installed, so you have left the session.' % patch_id)

    def _waitForInstalledPatch(self, patch_id, timeout=10.0):
        """
        Whether the patch is installed, allowing for a worker thread still
        finishing.

        Polls rather than sleeping once, so the common case (already on disk)
        costs one scan and returns immediately. Keeps the event loop running so
        the session's own signals are still delivered while waiting - the point
        is to avoid a spurious disconnect, and blocking the loop here could
        cause one.
        """
        deadline = time.monotonic() + timeout

        while True:
            if files.find_installed_patch(patch_id,
                                          extra_dirs=_external_patch_dirs()):
                return True

            if time.monotonic() >= deadline:
                return False

            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
                100)

    def _leaveOverPatch(self, message):
        """
        Ends the session because the patch requirement cannot be met.

        Decision 3: a client without the host's patch disconnects rather than
        staying on read-only, because it cannot hold the same level state and a
        seat showing the wrong level is worse than no seat.
        """
        # Anything held back while the patch was being fetched is dropped rather
        # than replayed: the patch never arrived, so loading that level now
        # would produce exactly the mis-rendered state the deferral avoided -
        # and the session is over in any case.
        self._deferred_level = None
        self._deferred_snapshot_area = None

        self._appendStatus(message)
        collab_dialogs.report_patch_unavailable(self.window, message)
        self.leave()

    # -- patch transfer, client side ----------------------------------------

    def _onManifest(self, payload):
        """
        The host listed what it is offering. Validate it, then start fetching.

        The manifest is validated here rather than trusted because it is the
        thing consent was implied for: every later chunk is checked against it,
        so a manifest that named a path outside the patch, or a .py file, would
        undo the whole exclusion.
        """
        if self.client is None:
            return

        try:
            entries = files.validate_manifest(payload)
        except files.ManifestError as exc:
            self._failTransfer('The host sent an invalid file list: %s' % exc)
            return

        if not entries:
            self._failTransfer('The host offered no files.')
            return

        patch_id = str(payload.get('patch_id', '') or self._transfer_patch)

        # A large transfer is consented to, a small one is not (Zement,
        # 2026-08-11). The sync itself is deliberately *not* optional - a client
        # that opted out is a client without the host's files, which is the
        # condition this round exists to remove - so the choice offered is
        # "accept, or leave the session", not "join anyway without the data".
        # A session the client cannot take part in correctly is worse than no
        # session, and leaving is the honest outcome rather than a silent
        # half-state.
        total = sum(entry.get('size', 0) for entry in entries)
        if total > ASSET_CONSENT_BYTES:
            if not collab_dialogs.confirm_large_transfer(
                    self.window, total, len(entries)):
                self._clearTransfer(abort=True)
                self._leaveOverPatch(
                    'You declined the %.0f MB download, so you have left the '
                    'session.' % (total / (1024.0 * 1024.0)))
                return

        # Resolve every destination now, before a byte moves. These validate the
        # id as a directory name, and an id that cannot be one ('CON', a
        # trailing dot) would otherwise fail at commit - after the whole patch
        # had been downloaded and verified.
        #
        # The game data goes to assets/mods/_collab/<patch>/, never to the
        # user's own assets/mods/<patch>/: everything under _collab is
        # session-derived by construction, so overwriting it is always safe,
        # while overwriting the user's own levels never is.
        try:
            destination = {
                files.KIND_PATCH: files.patch_directory(patch_id),
                files.KIND_STAGE: files.collab_stage_directory(patch_id),
                files.KIND_TEXTURE: files.collab_texture_directory(patch_id),
            }
        except Exception as exc:
            self._failTransfer(
                'The host\'s patch name cannot be used as a folder: %s' % exc)
            return

        try:
            staging = files.staging_directory()
            self._transfer = files.TransferSession(staging, entries, patch_id)
        except Exception as exc:
            self._failTransfer('Could not prepare the download: %s' % exc)
            return

        self._transfer_destination = destination

        self._transfer_patch = patch_id
        # (kind, path) pairs: the same name can appear in two sections, and the
        # section is what decides which folder the bytes land in.
        self._transfer_queue = list(self._transfer.pending_keys())
        self._transfer_total = len(self._transfer_queue)
        self._transfer_current = None

        self._appendStatus(files.describe_transfer(
            entries, self._hostNick(), patch_id))

        self._requestNextFile()

    def _requestNextFile(self):
        """
        Asks for one file at a time.

        Serial rather than pipelined: the receiver verifies each file's hash as
        it completes, and a single outstanding request means a failure names the
        file it happened on. A patch is a few hundred small files over a LAN or
        a direct link, so the round trips are not the bottleneck.
        """
        if self.client is None or self._transfer is None:
            return

        while self._transfer_queue:
            kind, path = self._transfer_queue.pop(0)
            # Remembered so an arriving chunk is matched to the section that was
            # asked for, rather than to a section the sender names. The section
            # decides the destination folder, so it stays the receiver's choice.
            self._transfer_current = (kind, path)
            self.client.send(protocol.make_message(
                protocol.T_FILE_REQ, {'path': path, 'kind': kind}))
            return

        self._finishTransfer()

    def _onFileChunk(self, payload):
        # A level the host has just saved arrives outside any TransferSession -
        # it was announced by T_SAVED rather than offered in a manifest - so it
        # is recognised and handled before the transfer machinery, which would
        # otherwise refuse it as a file that was never offered.
        #
        # But *not* while a patch transfer is running. The two streams are both
        # stage-section chunks on one connection, and mixing them breaks both:
        # a published level's chunks entered the TransferSession's in-order
        # accounting and tripped "the host sent more data than announced", after
        # which the transfer could never finish and the next attempt reported
        # one already in progress (Zement's 3b, 2026-08-10). A patch transfer
        # legitimately carrying a file of the same name would be stolen in the
        # other direction.
        #
        # The transfer wins because it was requested and is tracked file by
        # file; a publication is unsolicited and is re-sent on the next change.
        if (self._transfer is None
                and self._expected_save is not None
                and self._collectSavedLevel(payload)):
            return

        if self._transfer is None:
            return

        # The section comes from *our own* outstanding request, not from the
        # payload. It selects one of three destination folders, so taking it
        # from the sender would let a host redirect a file into a folder the
        # client never asked it for.
        kind = (self._transfer_current or (None, None))[0]

        try:
            complete = self._transfer.add_chunk(payload, kind)
        except files.TransferError as exc:
            # Covers a bad hash, an out-of-order chunk, an unoffered path and an
            # oversized file - every one of which means the transfer cannot be
            # trusted, so none of them is retried.
            self._failTransfer('The download failed: %s' % exc)
            return

        if not complete:
            return

        self._transfer_current = None

        # Report progress occasionally rather than per file: a transfer can now
        # carry a patch plus a Stage and Texture folder - thousands of files -
        # and a line each would bury the chat it shares a window with. Every
        # fiftieth keeps the user informed that it is still moving, and the
        # megabyte figures matter more than the count at this size.
        total = self._transfer_total or len(self._transfer.entries)
        done = total - len(self._transfer_queue) - 1
        if done > 0 and done % 50 == 0:
            self._appendStatus(
                'Downloaded %d of %d files (%.1f of %.1f MiB)...'
                % (done, total,
                   self._transfer.received_bytes / (1024.0 * 1024.0),
                   self._transfer.total_bytes / (1024.0 * 1024.0)))

        self._requestNextFile()

    def _finishTransfer(self):
        """
        Every file has arrived and verified. Install, then reload the patch.
        """
        transfer = self._transfer
        if transfer is None:
            return

        patch_id = self._transfer_patch

        if not transfer.is_complete:
            self._failTransfer('The download ended early.')
            return

        # Resolved in _onManifest; recomputed only if that somehow did not run,
        # and as the same {kind: root} mapping, because a bare directory would
        # give commit() nowhere to put the levels and tilesets.
        destination = self._transfer_destination or {
            files.KIND_PATCH: files.patch_directory(patch_id),
            files.KIND_STAGE: files.collab_stage_directory(patch_id),
            files.KIND_TEXTURE: files.collab_texture_directory(patch_id),
        }

        try:
            with _BusyIndicator(self.window,
                                'Installing the %s patch...' % patch_id):
                transfer.commit(destination)
        except Exception as exc:
            debuglog.log('client', 'patch commit failed', error=str(exc))
            self._failTransfer('The patch could not be installed: %s' % exc)
            return

        self._clearTransfer()

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_FILE_DONE, {'ok': True}))

        self._appendStatus('The %s patch was installed.' % patch_id)

        # Point the patch at the game data that just arrived, *before*
        # _reloadPatch runs. LoadGameDef asks the user to pick a Stage folder
        # when the patch has none, so writing these first does not merely order
        # that prompt correctly - it means the question is already answered and
        # the prompt never appears (checklist 10.1b).
        self._adoptTransferredGameData(patch_id)

        # Said plainly rather than buried, because it is the one thing a
        # transferred patch cannot give the user and they will otherwise
        # report it as a bug: sprites.py is Python and never travels.
        self._appendStatus(
            'Note: custom sprite previews are not included in a transferred '
            'patch. Sprites will still be placed and saved correctly, but '
            'some will show default images. Install %s normally for full '
            'previews.' % patch_id)

        self._reloadPatch(patch_id)

        # Only now is it safe to open the level: _reloadPatch has been through
        # LoadGameDef, which asks for the patch's Stage folder on first use, so
        # the tilesets it names can actually be found.
        self._resumeDeferredLoad()

    # -- level-file-first (Block C - B3, Fact 3) ----------------------------
    #
    # Zement's measurement is the whole reason this exists: an 8000-item level
    # takes 3-5 s to load from disk and about *two minutes* to rebuild from a
    # snapshot, because apply_snapshot builds one real Qt item per object on the
    # main thread. The cost is structural, not a bug to optimise away.
    #
    # So on a level change the host sends the level *file* and the client opens
    # it the ordinary way. The snapshot does not go away - it is still how a
    # client joining mid-edit gets the host's unsaved work, and still how a
    # resync works - it stops being on the hot path.
    #
    # The bytes are taken from Level.save() rather than read back off disk, and
    # that is what makes the delta empty in the common case: the serialisation
    # includes edits the host has not saved, so the client's file matches what
    # the host actually has on screen rather than what it last wrote.

    def _publishLevelFile(self):
        """
        Sends the current level as a file, so clients can open it directly.

        Returns True when the file was sent and the caller should skip the
        snapshot; False to fall back to snapshot-only behaviour.

        Falling back rather than failing is deliberate. Every reason this can
        decline - a level with no name, an area that cannot be serialised, no
        clients yet - is a case the snapshot path already handles correctly, and
        a client left with nothing at all is far worse than a slow load.
        """
        if not self.is_active or not self.is_host or self.server is None:
            return False

        # Peers that are mid-transfer are skipped individually below, rather
        # than the whole publication being abandoned. Blocking it session-wide
        # was the first fix and it was too coarse: with two clients, one
        # downloading and one not, the second would be left on a stale level
        # for as long as the first was busy.
        level = self._currentLevelName()
        if not level:
            # Never saved, so there is no name for a peer to resolve and no file
            # to write. The snapshot is the only way to share this.
            return False

        data = self._serialiseLevel()
        if not data:
            return False

        payload = {
            'level': level,
            'area': self._areaNumber(),
            'sha256': files.sha256_bytes(data),
            'size': len(data),
            'nick': self._hostNick(),
            'reason': 'publish',
        }

        message = protocol.make_message(protocol.T_SAVED, payload)
        sent = 0
        for connection in self.server.authenticated_connections():
            # Same rule as the save path: a peer mid-transfer is neither told
            # nor sent the file, and receives it when its download finishes.
            if str(getattr(connection, 'session_id', '')) in \
                    self._transferring_peers:
                continue

            connection.send(message)
            sent += 1

        if not sent:
            # Nobody to send to. Reported as "not published" so a later join
            # takes the snapshot path rather than waiting for a file that was
            # never offered.
            return False

        self._offerSavedLevel(level, data)

        debuglog.log('host', 'published level file', level=level,
                     bytes=len(data))
        return True

    def _transferInProgress(self):
        """
        Whether any peer is currently being sent a patch.

        Host side. A publication pushed into the middle of a transfer is
        discarded by the receiving client, so it is bandwidth spent competing
        with the transfer it would be interrupting.
        """
        return bool(self._transferring_peers)

    def _onPeerTransferFinished(self, session_id, ok):
        """
        A peer finished (or failed) its patch transfer, so it may be published
        to again.

        Followed by an immediate publication: the client has just acquired the
        host's Stage folder and is almost certainly looking at the wrong level
        or none at all, and waiting for the *next* level change to correct that
        would leave it stale for as long as the host stays put.
        """
        if not self.is_host:
            return False

        self._transferring_peers.discard(str(session_id))

        # Published unconditionally now. Any peer still downloading is skipped
        # individually inside the publication, so another client's transfer is
        # no longer a reason to leave *this* one on a stale level.
        debuglog.log('host', 'peer transfer finished', ok=ok, publishing=True)
        return self._publishLevelFile()

    def _serialiseLevel(self):
        """
        The current level as bytes, including edits that were never saved.

        Guarded: serialising touches every area and can raise on a level that is
        half-loaded or malformed, and a level change must not fail because the
        file could not be built - the snapshot still works.
        """
        level = getattr(globals_, 'Level', None)
        if level is None:
            return b''

        try:
            return bytes(level.save() or b'')
        except Exception as exc:
            debuglog.log('host', 'level could not be serialised', error=str(exc))
            return b''

    # -- saving (Block C - B3, phase 3c) ------------------------------------

    def notifyLevelSaved(self, data):
        """
        Tells the session the host has saved, and sends the file.

        Called from level_io.HandleSave after the bytes are on disk. Only the
        host gets here: the save gate refuses everyone else, so a client can
        neither save nor announce one.

        The goal is Zement's - everyone's copy reflects the session - and the
        safety comes from *where* the write lands rather than from asking. Each
        client writes into its own assets/mods/_collab/<patch>/Stage, which
        holds session-derived data by construction, and consents to that on
        joining. Nothing outside _collab is ever touched.

        The announcement carries the bytes that were written, not a fresh
        serialisation: re-saving could produce a different file (padding,
        compression) and the peers would then hold something the host never
        wrote.
        """
        if not self.is_active or not self.is_host:
            return False

        if self.server is None or not data:
            return False

        level = self._currentLevelName()
        if not level:
            # A level that has never been saved has no name for a peer to
            # resolve, and LoadLevel(None) would blank their editor.
            return False

        payload = {
            'level': level,
            'area': self._areaNumber(),
            'sha256': files.sha256_bytes(data),
            'size': len(data),
            'nick': self._hostNick(),
            'reason': 'save',
        }

        message = protocol.make_message(protocol.T_SAVED, payload)
        sent = 0
        for connection in self.server.authenticated_connections():
            # Not announced to a peer that is mid-transfer: the bytes are held
            # back for it too (see _offerSavedLevel), and announcing a file that
            # will not arrive leaves that client waiting for chunks it will
            # never be sent.
            if str(getattr(connection, 'session_id', '')) in \
                    self._transferring_peers:
                continue

            connection.send(message)
            sent += 1

        if not sent:
            return False

        # The file itself follows as ordinary stage-section chunks, so there is
        # one transfer path rather than a second one to keep correct. Authorised
        # per peer exactly like any other file: the manifest record is what
        # lets a client fetch it at all.
        self._offerSavedLevel(level, data)

        self._appendStatus('Saved %s and sent it to everyone.' % level)
        debuglog.log('host', 'level saved', level=level, bytes=len(data))
        return True

    def _offerSavedLevel(self, level, data):
        """
        Records the saved level as fetchable, then pushes it to every client.

        Pushed rather than offered-and-waited-for: the client already knows it
        wants this file - it was told so by T_SAVED - and a request round trip
        would only add a state machine for the case where it declines, which
        cannot happen.
        """
        if self.host_session is None:
            return False

        name = level + '.arc'

        # HostSession.participants is a *method*. This used to read
        # getattr(self.host_session, 'participants', ()) and iterate the result
        # without calling it - iterating a bound method yields nothing, so the
        # loop body never ran and not one byte was ever sent.
        #
        # That single missing '()' is why every client sat through the full
        # 20-second publication timeout and then fell back to a snapshot: the
        # announcement arrived, the file never did. It is also why the whole
        # level-file-first path looked unimplemented in Zement's test run
        # (2026-08-10) - the code was there and never delivered anything.
        #
        # Called defensively because the attribute is a method on HostSession
        # but a list on ClientSession, and this must not depend on which.
        participants = getattr(self.host_session, 'participants', None)
        if callable(participants):
            participants = participants()

        sent_to = 0
        chunks = [dict(chunk, kind=files.KIND_STAGE)
                  for chunk in files.chunks_from_bytes(name, data)]

        skipped = 0

        for participant in list(participants or ()):
            session_id = (participant.get('session_id')
                          if isinstance(participant, dict)
                          else getattr(participant, 'session_id', ''))
            if not session_id:
                continue

            # The host is in its own roster and must be skipped: it already has
            # the file it just wrote, and sending to it is a send to nobody.
            is_host = (participant.get('is_host')
                       if isinstance(participant, dict)
                       else getattr(participant, 'is_host', False))
            if is_host:
                continue

            # Never into the middle of that peer's patch transfer. Both travel
            # as stage-section chunks on one connection, so these would enter
            # the client's TransferSession and be refused as a file it never
            # asked for - which aborts the whole download.
            #
            # Checked here rather than only in _publishLevelFile because an
            # ordinary host *Save* reaches this too, and that path had no
            # transfer check at all: saving while a client was downloading
            # killed the download with "the host sent 'bga/0104.png' again
            # after it was complete" (Zement, 2026-08-11).
            #
            # Per peer, not per session: a second client that is not
            # downloading still gets the file, and the one that is will receive
            # it from the publication that follows its file_done.
            if str(session_id) in self._transferring_peers:
                skipped += 1
                continue

            for chunk in chunks:
                self._sendToPeer(session_id, protocol.T_FILE_CHUNK, chunk)
            sent_to += 1

        if skipped:
            debuglog.log('host', 'level file held back during transfer',
                         level=level, peers=skipped)

        debuglog.log('host', 'level file sent', level=level, peers=sent_to,
                     chunks=len(chunks), bytes=len(data))
        return sent_to > 0

    def _collectSavedLevel(self, payload):
        """
        Accumulates the chunks of a level the host saved, then writes it.

        Returns True when the chunk belonged to that file, so the caller knows
        not to hand it to the patch-transfer machinery as well.

        Everything about the destination is decided locally: the folder from
        our own patch name, the filename from the level name in T_SAVED, which
        was validated as a single component on the way in. Nothing the host
        sends can move the write, and safe_join checks it once more before it
        happens.
        """
        expected = self._expected_save
        if expected is None:
            return False

        name = expected['level'] + '.arc'
        if str(payload.get('path', '')).replace('\\', '/') != name:
            return False

        index = payload.get('index')
        total = payload.get('total')
        if not isinstance(index, int) or not isinstance(total, int):
            self._expected_save = None
            return True

        if index != len(expected.get('parts', ())):
            # In-order only, for the same reason TransferSession insists on it:
            # a sender that chooses offsets chooses what ends up where.
            debuglog.log('client', 'saved level out of order',
                         level=expected['level'], index=index)
            self._expected_save = None
            return True

        try:
            block = base64.b64decode(str(payload.get('data', '')), validate=True)
        except (ValueError, TypeError):
            self._expected_save = None
            return True

        parts = expected.setdefault('parts', [])
        parts.append(block)

        # Bounded as it arrives, so a host cannot announce a small file and
        # then stream indefinitely.
        if expected['size'] and sum(len(part) for part in parts) > expected['size']:
            self._appendStatus(
                'The host sent more data than it announced for %s; it was not '
                'saved.' % expected['level'])
            self._expected_save = None
            return True

        if index + 1 < total:
            return True

        self._expected_save = None
        self._writeSavedLevel(expected, b''.join(parts))
        return True

    def _writeSavedLevel(self, expected, data):
        """
        Writes the host's saved level into this peer's own session folder.

        The one place in the whole feature where a message from another machine
        causes a local file to be written, so the constraints are worth stating
        plainly:

        - the folder is derived here, from our patch name and our _collab root;
        - the filename comes from a validated single component;
        - safe_join re-checks the result against that root before opening it;
        - the bytes are verified against the announced hash first, so a
          corrupted or altered transfer is discarded rather than written.

        Never touches the user's own game data: _collab holds session-derived
        files only, which is what makes an automatic write acceptable at all.
        """
        level = expected['level']

        announced = str(expected.get('sha256', '') or '')
        if announced and files.sha256_bytes(data) != announced:
            self._appendStatus(
                '%s did not arrive intact and was not saved.' % level)
            debuglog.log('client', 'saved level checksum mismatch', level=level)
            return False

        patch_id = self._patchId()
        if not patch_id:
            # Retail has no _collab folder of its own, and writing into the
            # user's real stage folder is exactly what must never happen.
            self._appendStatus(
                'The host saved %s. It was not copied here, because this '
                'session uses the retail game and there is no session folder '
                'to write into.' % level)
            return False

        try:
            stage = files.collab_stage_directory(patch_id)
            os.makedirs(stage, exist_ok=True)
            target = identity.safe_join(stage, level + '.arc')
        except Exception as exc:
            debuglog.log('client', 'saved level path refused', level=level,
                         error=str(exc))
            return False

        try:
            with open(target, 'wb') as handle:
                handle.write(data)
        except OSError as exc:
            self._appendStatus('%s could not be written here: %s'
                               % (level, exc))
            return False

        self._appendStatus('%s was updated in your session folder.' % level)
        debuglog.log('client', 'saved level written', level=level,
                     bytes=len(data), path=target)

        # Point the patch at the session folder if it is not already, so the
        # file just written is the one this editor would open.
        self._useSessionGamePaths(patch_id, stage,
                                  files.collab_texture_directory(patch_id))

        # Open it, if this is the level the session is on and we are not already
        # showing it (Block C - B3, Fact 3). This is the whole point of sending
        # the file: loading it takes seconds where rebuilding the same level
        # from a snapshot takes minutes.
        self._openPublishedLevel(level, target, expected.get('area', 0))
        return True

    def _openPublishedLevel(self, level, path, area=0):
        """
        Opens a level the host just published, when it is the one the session
        is on.

        Returns True if it was opened.

        Two conditions, and both matter:

        - the session has to actually be on this level. The host also publishes
          on an ordinary Save, and a client that is deliberately looking
          somewhere else must not be yanked away from it.
        - we must not already be showing it. Reloading a level the user is
          working in would discard their view, their selection, and - if the
          file is one they already have open - is simply wasted work.
        """
        if self.is_host or not self.is_active:
            return False

        if level != self._session_level:
            return False

        # The announced area wins over the session's own record. On an area
        # switch the announcement is what carries the *new* area, and
        # _session_area may not have caught up yet - which is how the client
        # ended up showing Area 2 while the host was on Area 3.
        target_area = _clamp_area(area or self._session_area)

        if self._areaNumber() != target_area:
            # Same level, different area: the file is right but the view is not,
            # so it still needs opening at the announced area.
            pass
        elif self.hasSessionFile() and not self._pending_publication:
            # Already showing this level and area, and nothing told us it
            # changed.
            return False

        # Loaded by full path, not by name: the file we just wrote is the one to
        # open, and resolving the name again could find a different file through
        # a stage path that has not been switched over yet.
        if not self._loadLevelQuietly(path, True, target_area):
            self._appendStatus(
                'The host sent %s, but it could not be opened here.' % level)
            return False

        # The session is on the area we just opened. Recorded from the
        # announcement so a later dirty check or save agrees with the view.
        self._setSessionLevel(level, target_area)

        self._pending_publication = False
        self._appendStatus('Opened %s from the host.' % level)
        debuglog.log('client', 'opened published level', level=level,
                     area=target_area, path=path)

        # The file is byte-identical to the host's, so there is nothing left to
        # reconcile - which is exactly what makes this fast. A resync here would
        # ask for the snapshot this path exists to avoid.
        self._checkContentMatches()
        return True

    def _onLevelSaved(self, payload):
        """
        The host saved; write the same file into our own session folder.

        Automatic, per Zement (2026-08-09), and safe because of where it lands:
        assets/mods/_collab/<patch>/Stage holds only session-derived data, the
        client agreed to that on joining, and the user's own game files are a
        different folder entirely.

        The path is derived *here*, from our own patch name and our own _collab
        root. The host supplies a level *name*, which is validated as a single
        filename component on the way in and again by safe_join at the write.
        A host that could name a path could choose which of our files to
        overwrite, which is the bug class this whole block is built against.
        """
        if not self.is_active or self.is_host:
            return False

        level = str((payload or {}).get('level', '') or '')
        if not level:
            return False

        nick = str((payload or {}).get('nick', '') or 'The host')

        # 'the host saved 01-01' for a level change nobody saved is actively
        # misleading - it cost one B3 investigation a wrong diagnosis - so the
        # two are named differently even though they are handled identically.
        reason = str((payload or {}).get('reason', '') or 'save')
        if reason == 'publish':
            self._appendStatus('%s is sharing %s.' % (nick, level))
        else:
            self._appendStatus('%s saved %s.' % (nick, level))

        # The bytes arrive as stage-section chunks; this only records what to
        # expect, so the chunk handler can verify and place them.
        # The announced area is kept, not just the level. T_SAVED has always
        # carried it and this ignored it, so a publication opened at whatever
        # _session_area happened to hold - which on an area switch is not yet
        # the area being switched to. That is the client showing "Area 2" while
        # the host is on Area 3 (Zement, 2026-08-11).
        self._expected_save = {
            'level': level,
            'area': _clamp_area((payload or {}).get('area', 1)),
            'sha256': str((payload or {}).get('sha256', '') or ''),
            'size': int((payload or {}).get('size', 0) or 0),
        }

        # Our copy no longer has unsaved work of its own worth guarding: the
        # session's state is what is on screen, and it has just been written by
        # the peer that owns it. This is also what stops CheckDirty prompting a
        # client about changes it did not author.
        globals_.Dirty = False
        globals_.AutoSaveDirty = False
        window = self.window
        if hasattr(window, 'UpdateTitle'):
            window.UpdateTitle()

        debuglog.log('client', 'level file incoming', level=level, nick=nick,
                     reason=reason)
        return True

    # -- content mismatch (Block C - B3, phase 2) ---------------------------

    def _checkContentMatches(self):
        """
        Compares what this peer has open against what the host reported.

        The bug this exists for (known open 10.1): `patch_id` and
        `patch_version` match whenever two peers have the same patch, but the
        *stage path* is a local preference. Zement and Mone both had "Another
        Mario Wii" pointing at different stage folders, both opened '01-01', and
        saw completely different levels - while the session reported everything
        as matching. The names agree; the bytes do not.

        Reports rather than acts. A mismatch is worth saying plainly - Zement's
        position, which is the right one, is that an unsynced state defeats the
        purpose of a session and must not pass silently - but the fix is to
        fetch the host's copies, which is what the transfer already does.
        Refusing the join was considered and rejected: a client with the wrong
        tilesets is looking at the right objects with the wrong pictures, and
        the *destructive* case is saving, which the host-only save authority
        already closes.
        """
        if not self.is_active or self.is_host:
            return True

        host = self._host_fingerprint
        if not host:
            return True

        # An older host sends no fingerprints at all. Nothing to compare is not
        # a mismatch; it is a peer that cannot answer the question.
        if 'level_sha256' not in host and 'tileset_sha256' not in host:
            return True

        stage, texture = self._localGameDataDirectories()
        level = self._session_level or self._currentLevelName()

        problems = []

        theirs = str(host.get('level_sha256', '') or '')
        ours = files.level_fingerprint(stage, level)
        if theirs and ours and theirs != ours:
            problems.append(
                'your copy of %s is not the same file as the host\'s' % level)
        elif theirs and not ours and level:
            problems.append('you do not have a copy of %s' % level)

        their_names = list(host.get('tilesets') or [])
        their_hashes = list(host.get('tileset_sha256') or [])
        our_hashes = files.tileset_fingerprints(texture, their_names)

        differing = files.compare_fingerprints(our_hashes, their_hashes)
        named = [their_names[index] for index in differing
                 if index < len(their_names) and their_names[index]]
        if named:
            problems.append('these tilesets differ from the host\'s: %s'
                            % ', '.join(named))

        summary = '; '.join(problems)

        if not problems:
            debuglog.log('client', 'content matches the host', level=level)
            # Forgotten, so that moving back onto a divergent level warns again
            # rather than staying quiet because it once warned about it.
            self._reported_mismatch = ''
            return True

        debuglog.log('client', 'CONTENT MISMATCH', level=level,
                     problems=summary)

        # Said once per distinct problem, not once per snapshot. A resync
        # arrives whenever the host edits anything, and repeating the same
        # paragraph each time would bury the chat it shares a window with -
        # while a *different* mismatch is genuinely new information.
        if self._reported_mismatch == summary:
            return False

        self._reported_mismatch = summary

        self._appendStatus(
            'Warning - you are not seeing the same files as the host: %s. '
            'The host\'s objects are correct, but the graphics behind them may '
            'not be. Check that this patch points at the session\'s Stage and '
            'Texture folders.' % summary)

        # And said once in a dialog, the first time it happens in a session.
        # A line in the chat log is easy to miss - Zement's phase 2 test looked
        # for exactly this and found nothing - and quietly editing a different
        # level from everyone else is the failure this block exists to prevent.
        collab_dialogs.report_content_mismatch(self.window, problems)
        return False

    def _adoptTransferredGameData(self, patch_id):
        """
        Points the transferred patch at the Stage and Texture folders that came
        with it (Block C - B3).

        This is the step the catalog route has always done for itself
        (patch_manager_dialog writes StageGamePath_<name> after an install) and
        the host-transfer route never did - which is why a transferred patch
        asked the user to find a Stage folder that only existed inside the
        transfer.

        The keys are per *patch name*, not per folder, because that is what
        ReggieGameDefinition.GetStageGamePath reads.

        Written only for folders that actually arrived: a transfer from a host
        that had no Stage path set carries no levels, and claiming a path to an
        empty directory would be worse than leaving the question open. Nothing
        outside _collab is ever touched, and the user's own paths for their own
        copy of a patch are a different key entirely.
        """
        from reggie.core.dirty import setSetting

        try:
            stage = files.collab_stage_directory(patch_id)
            texture = files.collab_texture_directory(patch_id)
        except Exception as exc:
            debuglog.log('client', 'collab paths unavailable', error=str(exc))
            return False

        if not os.path.isdir(stage):
            return False

        setSetting('StageGamePath_' + patch_id, stage)
        if os.path.isdir(texture):
            setSetting('TextureGamePath_' + patch_id, texture)

        # Also as a session override, which is what serves a client that
        # *already had* this patch (Block C - B3, phase 2). Such a client keeps
        # its own patch and its own StageGamePath_<patch>; the session simply
        # answers first, and stops answering when it ends. Without this, a
        # second client would look at its own levels while believing it was in
        # sync - the 10.1 case with the roles reversed.
        self._useSessionGamePaths(patch_id, stage, texture)

        # Mark the patch folder as a session copy. A *flag*, not a renamed
        # patch: _patchId() returns gamedef.name and patch_requirement compares
        # exactly that, so appending '(Collab)' to the name would make every
        # later comparison see a mismatch and the client would flip between the
        # two copies or re-transfer forever. Written locally and never sent, so
        # a host cannot forge one.
        try:
            files.write_collab_marker(files.patch_directory(patch_id),
                                      patch_id, self._hostNick())
        except Exception as exc:
            # A missing marker costs a label in the UI, nothing more.
            debuglog.log('client', 'collab marker not written', error=str(exc))

        self._appendStatus(
            'The levels and tilesets from this session are in %s.' % stage)
        debuglog.log('client', 'adopted transferred game data',
                     patch=patch_id, stage=stage)
        return True

    def _useSessionGamePaths(self, patch_id, stage, texture):
        """
        Points this patch at the session's game data for as long as it lasts.

        Separate from the QSettings write above because the two serve different
        clients. A peer that had to *download* the patch has no preference of
        its own, so writing the setting is right and it keeps the files
        afterwards. A peer that already *had* the patch has its own
        StageGamePath_<patch>, pointing at its own levels, and rewriting that
        from the network would be changing a preference on someone else's
        machine and leaving it changed. The override does neither: it answers
        first while the session runs and is forgotten in _teardown.
        """
        if not patch_id:
            return False

        try:
            from reggie.io.gamedef import ReggieGameDefinition

            ReggieGameDefinition.SetSessionGamePaths(patch_id, stage, texture)
        except Exception as exc:
            debuglog.log('client', 'session path override failed',
                         error=str(exc))
            return False

        debuglog.log('client', 'session game paths set', patch=patch_id,
                     stage=stage)
        return True

    def _clearTransfer(self, abort=False):
        """
        Drops all transfer state.

        One place rather than three, because the fields have to move together:
        leaving _transfer_patch set after a transfer ends would keep
        _onTransferFinished armed, so a later unrelated file_done from the host
        would tear down a session that had finished downloading long ago.
        """
        # Captured before the fields are reset, so an abort can un-record the
        # assets sync for the patch it was actually fetching.
        patch = self._transfer_patch

        if abort and self._transfer is not None:
            try:
                self._transfer.abort()
            except Exception:
                # Staging is a temporary directory; failing to tidy it is not
                # worth masking the error that got us here.
                pass

        self._transfer = None
        self._transfer_patch = ''
        self._transfer_queue = []
        self._transfer_destination = ''
        self._transfer_current = None
        self._transfer_total = 0

        if abort:
            # An aborted transfer never delivers its patch, so whatever was held
            # for it can never be loaded correctly. Cleared here rather than only
            # in _leaveOverPatch because _teardown aborts too, and a stale level
            # left behind would be replayed into the *next* session.
            self._deferred_level = None
            self._deferred_snapshot_area = None

            # The assets sync is recorded before the transfer starts, so an
            # abort has to un-record it - otherwise a transfer that failed once
            # would be treated as done for the rest of the session and the
            # client would keep the files it was trying to replace.
            self._synced_asset_patches.discard(patch)

    def _failTransfer(self, message):
        """
        Abandons a transfer, discarding anything staged.
        """
        debuglog.log('client', 'transfer failed', error=message)

        self._clearTransfer(abort=True)

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_FILE_DONE, {'ok': False, 'error': message[:200]}))

        self._leaveOverPatch(message)

    def _onTransferFinished(self, ok, error):
        """
        The host ended the transfer - either refusing it, or reporting a fault.
        """
        if ok:
            return

        if self._transfer is None and not self._transfer_patch:
            return

        self._failTransfer(error or 'The host stopped the transfer.')

    def _reloadPatch(self, patch_id, folder=''):
        """
        Switches the editor to a patch, or to retail when patch_id is ''.

        loadNewGameDef takes the gamedef *folder* name, not the patch id - the
        id is the name declared inside main.xml, and the two are routinely
        different ('Newer Super Mario Bros. Wii' lives in NewerSMBW). Passing
        the id would find no such folder and silently fall back to retail, which
        looks like nothing having happened. `folder` may be given explicitly;
        None means retail, which is what a gamedef of None loads.

        Best-effort and non-fatal: the files are on disk either way, so a load
        that does not take is a restart away from being right, and killing the
        session over it would throw away the user's work.

        Loading a gamedef reloads tilesets and sprite data, so this must run on
        the main thread - it does, because every caller is a slot.
        """
        retail = not patch_id
        if folder == '':
            folder = None if retail else self._patchFolderName(patch_id)

        name = 'the retail game' if retail else '%s patch' % patch_id

        if retail or folder:
            try:
                from reggie.io.gamedef import loadNewGameDef
                with _BusyIndicator(self.window, 'Loading %s...' % name):
                    # A gamedef of None is retail; see ReggieGameDefinition's
                    # NoneTypes check.
                    loaded = loadNewGameDef(folder)

                if loaded:
                    self._appendStatus('Switched to %s.' % name)
                    return

                debuglog.log('client', 'gamedef load refused',
                             patch_id=patch_id, folder=str(folder))
            except Exception as exc:
                debuglog.log('client', 'patch reload failed', error=str(exc))

        if retail:
            self._appendStatus(
                'Could not switch to the retail game. Switch manually to stay '
                'in sync with the host.')
            return

        self._appendStatus(
            'The %s patch is installed but could not be loaded. Switch to it '
            'manually to stay in sync with the host.' % patch_id)

    @staticmethod
    def _patchFolderName(patch_id):
        """
        The directory name of an installed patch, for LoadGameDef.
        """
        found = files.find_installed_patch(patch_id,
                                           extra_dirs=_external_patch_dirs())
        if not found:
            return ''

        return os.path.basename(str(found.get('path', '')).rstrip('\\/'))

    def _hostNick(self):
        if self.client_session is not None:
            for entry in getattr(self.client_session, 'participants', ()):
                if entry.get('role') == protocol.ROLE_HOST:
                    return entry.get('nick', 'the host')
        return 'the host'

    # -- patch transfer, host side ------------------------------------------

    def _onPatchNeeded(self, session_id, patch_id, assets_only=False):
        """
        A client wants this session's patch. Build a manifest and offer it.

        Runs on the main thread because it walks the patch directory. The host
        decides what is in the manifest; the client only chooses from it.

        `assets_only` omits the patch section and sends Stage and Texture alone
        (Block C - B3, round 2). That is the catalog and already-installed
        routes: the client has the patch *definition* but not the host's game
        data, and without the data both peers resolve the same level name
        through different stage folders to different bytes - known open 10.1.
        """
        if self.host_session is None:
            return

        # A second request while one is already being served is ignored.
        #
        # The client asks once for the patch and can ask again moments later -
        # after _reloadPatch, or because a room_info arrived - and servicing the
        # second rebuilds the manifest and calls record_manifest again, which
        # *replaces* the authorisation the client is still fetching against.
        # Files from the first offer then arrive against the second manifest and
        # the transfer dies. Zement's host log shows the pair 0.3 s apart, and
        # this is why it only ever happened on the first install of a patch.
        #
        # Ignoring is right rather than queueing: the transfer already running
        # delivers exactly the same files.
        if str(session_id) in self._transferring_peers:
            debuglog.log('host', 'duplicate patch_need ignored',
                         nick=str(session_id))
            return

        # Marked as transferring *now*, not when the manifest is finally sent.
        #
        # Building a manifest hashes every file - seconds for a real patch - and
        # it pumps the event loop while it works, so the host's own level
        # changes are processed inside that window. Marking the peer afterwards
        # left it unprotected for exactly as long as the hashing took, and a
        # publication landing there entered the client's TransferSession and
        # aborted the download with "the host sent 'bga/0104.png' again after it
        # was complete".
        #
        # That is why Zement saw it only on the *first* install of a patch: the
        # window exists only while a manifest is being built, and only a client
        # that does not yet have the patch ever triggers one.
        self._transferring_peers.add(str(session_id))

        directory = ''
        if not assets_only:
            directory = self._localPatchDirectory(patch_id)
            if not directory:
                self._appendStatus(
                    'Cannot send %s: its folder was not found.' % patch_id)
                self._refuseTransfer(session_id,
                                     'The host cannot find its patch.')
                return

        # The patch definition alone is not enough to see the same level: it
        # says which tilesets a level names, but the levels and tilesets
        # themselves live in the host's Stage and Texture folders, wherever its
        # StageGamePath happens to point. Sending those too is what stops two
        # peers with the same patch id editing different levels (Block C - B3).
        stage_dir, texture_dir = self._localGameDataDirectories()

        # Hashing a patch with its Stage and Texture folders takes seconds -
        # about 11 for NewerSMBW - and it runs here, on the main thread. Keeping
        # the window painting through it is safe in a way it is not during a
        # scene rebuild: this touches no Qt state, only the filesystem. Input is
        # still excluded, so the user cannot start something else mid-walk.
        def preparing(count, kind):
            try:
                self.window.statusBar().showMessage(
                    'Preparing %s files to send: %d...' % (kind, count))
            except Exception:
                # A window without a status bar is not a reason to abandon a
                # transfer; the progress line is a courtesy.
                pass
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
                10)

        try:
            with _BusyIndicator(self.window, 'Preparing the patch files...'):
                manifest = files.build_manifest(directory, patch_id,
                                                stage_dir, texture_dir,
                                                on_progress=preparing)
        except Exception as exc:
            debuglog.log('host', 'manifest build failed', error=str(exc))
            self._appendStatus('Could not prepare %s: %s' % (patch_id, exc))
            self._refuseTransfer(session_id,
                                 'The host could not prepare the patch.')
            return
        finally:
            # The per-file line is transient; leaving the last one on screen
            # would have the status bar claim the host is still preparing files
            # long after it finished.
            try:
                self.window.statusBar().clearMessage()
            except Exception:
                pass

        entries = manifest['files']
        if not entries:
            self._refuseTransfer(session_id, 'That patch has no data files.')
            return

        # Record what this peer is allowed to fetch *before* offering it, so a
        # file_req that arrives immediately cannot beat the record. Recorded as
        # (kind, path) pairs: the same name can appear in two sections, and
        # authorising on the name alone would let a client fetch one section's
        # file by asking for it as another's.
        self.host_session.record_manifest(
            session_id, patch_id,
            [(entry.get('kind', files.KIND_PATCH), entry['path'])
             for entry in entries])

        # skipped entries are dicts ({'path', 'reason'}), not names.
        skipped = [str(entry.get('path', '')) for entry in
                   (manifest.get('skipped') or [])]

        counts = {}
        for entry in entries:
            kind = entry.get('kind', files.KIND_PATCH)
            counts[kind] = counts.get(kind, 0) + 1

        summary = '%d files of %s (%s), %.1f MiB' % (
            len(entries), patch_id,
            ', '.join('%d %s' % (counts[k], k) for k in sorted(counts)),
            manifest['total_bytes'] / (1024.0 * 1024.0))

        if skipped:
            self._appendStatus('Sending %s. Not sent: %s.'
                               % (summary, ', '.join(skipped[:5])))
        else:
            self._appendStatus('Sending %s.' % summary)

        # (The peer was marked as transferring at the top of this method, before
        # the manifest was built - see the note there.)
        self._sendToPeer(session_id, protocol.T_MANIFEST,
                         files.manifest_payload(manifest))

    def _onFileRequested(self, session_id, path, kind=files.KIND_PATCH):
        """
        Sends one file, in chunks.

        The (kind, path) pair was already checked against the manifest by
        HostSession, which is the authorisation point; this reads and sends. It
        is checked again on the way in by read_chunks, which resolves through
        safe_join - two independent checks, because this one turns a name into a
        disk read.

        Reads from the patch this peer was *offered*, not the one loaded now.
        The host can switch patch mid-transfer, and serving the new one against
        the old manifest would fail the client's hash check - reporting
        corruption for what is really a stale offer.
        """
        if self.host_session is None:
            return

        offered = self.host_session.offered_patch(session_id)
        if not offered:
            self._refuseTransfer(session_id, 'No transfer is in progress.')
            return

        directory = self._sourceDirectoryForKind(kind, offered)
        if not directory:
            self._refuseTransfer(
                session_id,
                'The host cannot find its patch.' if kind == files.KIND_PATCH
                else 'The host cannot find its %s folder.' % kind)
            return

        try:
            for chunk in files.read_chunks(directory, path):
                # The section travels back with every chunk, so the receiver
                # never has to guess which of three folders the bytes are for.
                chunk['kind'] = kind
                self._sendToPeer(session_id, protocol.T_FILE_CHUNK, chunk)
        except Exception as exc:
            debuglog.log('host', 'file read failed', path=path, kind=kind,
                         error=str(exc))
            self._refuseTransfer(
                session_id, 'The host could not read %s.' % path)

    def _sourceDirectoryForKind(self, kind, patch_id):
        """
        Which of the host's folders a manifest section is served from.

        The patch section comes from the patch this peer was offered; the other
        two come from the host's *current* Stage and Texture paths. That
        difference is deliberate and matches how the two are recorded: the
        offered patch is pinned so a mid-transfer switch cannot corrupt a
        verified download, while the game data paths are a local preference that
        the manifest was built from moments earlier.
        """
        if kind == files.KIND_PATCH:
            return self._localPatchDirectory(patch_id)

        stage_dir, texture_dir = self._localGameDataDirectories()

        if kind == files.KIND_STAGE:
            return stage_dir
        if kind == files.KIND_TEXTURE:
            return texture_dir

        return ''

    @staticmethod
    def _localGameDataDirectories():
        """
        The host's own Stage and Texture folders, as (stage, texture).

        Read through the gamedef rather than from QSettings directly, because
        that is what resolves the per-patch keys and their fallbacks
        (StageGamePath_<patch name>, then StageGamePath). Either may be empty -
        a host that has never set them has nothing to send, which is not an
        error, just a transfer with no game data in it.
        """
        gamedef = getattr(globals_, 'gamedef', None)
        if gamedef is None:
            return '', ''

        def resolve(getter):
            try:
                value = str(getter() or '')
            except Exception:
                return ''
            return value if value and os.path.isdir(value) else ''

        return (resolve(getattr(gamedef, 'GetStageGamePath', lambda: '')),
                resolve(getattr(gamedef, 'GetTextureGamePath', lambda: '')))

    def _refuseTransfer(self, session_id, reason):
        self._sendToPeer(session_id, protocol.T_FILE_DONE,
                         {'ok': False, 'error': reason})

        # A refused transfer is over, so the peer must stop counting as
        # transferring. _onPatchNeeded marks it before building the manifest,
        # and every way out of that method short of sending one comes through
        # here - so without this a peer whose transfer was refused would never
        # be published to again for the rest of the session.
        self._transferring_peers.discard(str(session_id))

        if self.host_session is not None:
            self.host_session.clear_transfer(session_id)

    def _sendToPeer(self, session_id, msg_type, payload):
        if self.host_session is None:
            return

        participant = self.host_session.find(session_id)
        if participant is None or participant.connection is None:
            return

        participant.connection.send_type(msg_type, payload)

    @staticmethod
    def _localPatchDirectory(patch_id):
        """
        Where this machine keeps the given patch.

        Asks find_installed_patch rather than assuming reggiedata/patches,
        because a patch installed by the Patch Manager or added as an external
        patch lives elsewhere - the same reason patch_requirement does not
        trust the catalog's view of what is installed.
        """
        if not patch_id:
            return ''

        found = files.find_installed_patch(patch_id,
                                           extra_dirs=_external_patch_dirs())
        if found:
            return found.get('path', '') or ''

        return ''

    # -- helpers ------------------------------------------------------------

    def _roomInfo(self):
        """
        What the session is, for a joining or re-checking client.

        `level_name` and `area` are derived the same way the wire derives them,
        rather than read from globals_. There is no globals_.levelName - the
        attribute never existed, so this reported '' for every session - and the
        area was hardcoded to 1, so a host working in area 2 told every client it
        was in area 1. Neither mattered while room_info was only used for the
        patch check, which reads neither; phase 0 makes a client set its session
        identity from this on connect, so both have to be true.
        """
        info = {
            'game_id': self._gameId(),
            'game_name': self._gameName(),
            'patch_id': self._patchId(),
            'patch_version': self._patchVersion(),
            'level_name': self._currentLevelName(),
            'area': self._areaNumber(),
        }
        info.update(self._contentFingerprint())
        return info

    def _contentFingerprint(self):
        """
        Hashes of the level and tilesets this peer actually has open.

        The reason this exists (Block C - B3, known open 10.1): `patch_id` and
        `patch_version` match whenever two peers have the same patch, but the
        *stage path* is a local preference. Zement and Mone both had "Another
        Mario Wii", pointing at different stage folders, both opened '01-01' and
        saw completely different levels - and nothing noticed, because the two
        things the session compared did match.

        Hashing the *bytes* rather than the name is the whole point: the names
        agree in that case and the files do not.

        Cheap by construction - a level is tens of kilobytes and there are four
        tilesets - and best-effort: a fingerprint that cannot be taken is
        reported as absent, never as an error, since failing to compare is not a
        reason to fail a join.
        """
        try:
            stage, texture = self._localGameDataDirectories()
            level = self._currentLevelName()

            return {
                'level_sha256': files.level_fingerprint(stage, level),
                'tilesets': self._currentTilesetNames(),
                'tileset_sha256': files.tileset_fingerprints(
                    texture, self._currentTilesetNames()),
            }
        except Exception as exc:
            debuglog.log('controller', 'fingerprint failed', error=str(exc))
            return {}

    @staticmethod
    def _currentTilesetNames():
        """
        The four tileset names of the current area, in slot order.
        """
        area = getattr(globals_, 'Area', None)
        if area is None:
            return []

        return [str(getattr(area, 'tileset%d' % slot, '') or '')
                for slot in range(4)]

    @staticmethod
    def _gameId():
        gamedef = getattr(globals_, 'gamedef', None)
        return str(getattr(gamedef, 'name', '') or '')

    @staticmethod
    def _gameName():
        gamedef = getattr(globals_, 'gamedef', None)
        return str(getattr(gamedef, 'name', '') or 'New Super Mario Bros. Wii')

    @staticmethod
    def _patchId():
        """
        The patch this session uses, or '' for the retail game.

        The base game is not a patch. A retail gamedef has custom=False and a
        *translated* display name ('New Super Mario Bros. Wii'), so sending that
        name as a patch id made every retail session claim to need a patch that
        by definition cannot be installed - which is what blocked Zement's first
        two-machine test even though both sides matched exactly.

        A custom gamedef's identity for this purpose is the name declared in its
        main.xml, since that is what identifies it across machines; the folder
        name differs between install locations for the same patch.
        """
        gamedef = getattr(globals_, 'gamedef', None)
        if gamedef is None or not getattr(gamedef, 'custom', False):
            return ''

        return str(getattr(gamedef, 'name', '') or '')

    @staticmethod
    def _patchVersion():
        gamedef = getattr(globals_, 'gamedef', None)
        if gamedef is None or not getattr(gamedef, 'custom', False):
            return ''

        return str(getattr(gamedef, 'version', '') or '')

    @staticmethod
    def _enabledPlugins():
        """
        The names of enabled plugins, for the mismatch warning.

        Plugin *code* is never transferred - only this hash is compared, so the
        host can warn that the two sides differ. An empty list simply means "no
        opinion", which is why every failure path here returns one rather than
        propagating: a plugin-listing problem must not stop someone joining.
        """
        try:
            from reggie.plugins import patch_plugins

            # Patch plugins are per-patch feature toggles declared in
            # plugins.xml - pure data, and the only plugin state that is
            # meaningful to compare. Code plugins are Python and are never
            # transferred or compared, per Zement's instruction.
            return [definition.id for definition in patch_plugins.REGISTRY
                    if patch_plugins.is_enabled(definition.id)]
        except Exception:
            return []


def _settings_directory():
    """
    Where the host certificate and private key live.

    Beside the user's settings file, so the key survives updates and sits in the
    user profile rather than anywhere world-readable.

    The fallback is deliberately NOT the working directory. During development
    that is the repository checkout, and the key file then lands next to the
    source where a `git add -A` would publish a private key. A per-user
    application data directory is the correct place even when QSettings is
    unavailable.
    """
    settings = getattr(globals_, 'settings', None)
    if settings is not None:
        try:
            directory = os.path.dirname(settings.fileName())

            # On Windows, QSettings defaults to the registry, and fileName()
            # then returns something like '\\HKEY_CURRENT_USER\\Software\\...'
            # which is not a filesystem path at all. Only use it when it really
            # is a directory we could write a key into.
            if directory and os.path.isabs(directory) and os.path.isdir(
                    os.path.dirname(directory) or directory):
                return directory
        except Exception:
            pass

    base = (os.environ.get('APPDATA')
            or os.environ.get('XDG_CONFIG_HOME')
            or os.path.expanduser('~'))

    directory = os.path.join(base, 'Reggie Next')
    os.makedirs(directory, exist_ok=True)
    return directory


def _debug_log_directory():
    """
    Where collaboration debug logs are written: <Reggie root>/logs.

    Deliberately not _settings_directory(). That answers "where does the private
    key live", and in a source checkout it resolves to the repository root -
    because QSettings is opened on the relative path 'settings.ini' - so every
    session dropped a collab_debug_<pid>.log beside the source, where they
    accumulate quickly and are noise in exactly the folder that should stay
    clean (Zement, 2026-08-09).

    A `logs/` folder next to the application, rather than somewhere in the
    working notes: the debug log is a shipped feature with its own preference,
    so its output belongs with the program and not in a gitignored scratch tree
    that only exists in this checkout.

    The root comes from io.misc.module_path(), not from this file's location.
    In a PyInstaller build __file__ points inside the temporary _MEIPASS
    extraction directory, which is deleted when the program exits - so a log
    written relative to it would vanish with the process that needed it.
    module_path() is the codebase's existing answer to that question and
    resolves to the folder holding the executable (and to Contents/Resources on
    macOS).

    Falls back to the settings directory when there is no writable folder
    there - an installation under Program Files is read-only for a normal user,
    and a log location is never worth failing a session over.
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

    return _settings_directory()


def _clamp_area(area):
    """
    An area number that is certainly in range, whatever arrived.

    The wire validator enforces 1-4 too; this covers the local callers, which
    pass whatever a combo box index produced.
    """
    try:
        return max(1, min(4, int(area or 1)))
    except (TypeError, ValueError):
        return 1


def _describeLevel(level, area):
    """
    How a level and area are named to the user, in one place, so a proposal and
    the status line that answers it read the same way.
    """
    if level:
        return '%s (area %d)' % (level, _clamp_area(area))
    return 'area %d' % _clamp_area(area)


def _sprite_format():
    """
    The local sprite data format for decoding remote sprite data.

    Always local, never taken from the wire: a peer choosing how we parse bytes
    is a peer choosing what those bytes mean. Vanilla is RawData's own default
    (see RawData.from_bytes), so it is the right fallback rather than a guess.
    """
    from reggie.core.raw_data import RawData

    return RawData.Format.Vanilla


def set_action_allowed(name, allowed):
    """
    Enables an action, unless a collaboration session forbids it.

    For the several places that compute their own enabled state from the level -
    'backgrounds' follows the zone count, the area actions follow the area count
    - and run *after* the session has applied its permissions. Calling
    setEnabled directly there re-enabled a control the session had greyed out,
    which is how Backgrounds and the three area actions stayed usable for an
    Editor client: every level load, every Zones dialog and every zones undo put
    them back.

    So the two conditions are combined here rather than each site knowing about
    collaboration. A control is available only if the level allows it AND the
    session does.
    """
    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        return

    actions = getattr(window, 'actions', None)
    if not isinstance(actions, dict):
        return

    action = actions.get(name)
    if action is None:
        return

    if allowed:
        controller = getattr(window, '_collab', None)
        if controller is not None:
            try:
                allowed = controller.actionAllowedBySession(name)
            except Exception:
                # A collaboration problem must never leave a control stuck off.
                allowed = True

    action.setEnabled(bool(allowed))


def _external_patch_dirs():
    """
    Patch directories added with "Add external patch".

    These live in QSettings under PatchPath_<gamepath>, so reggie/collab cannot
    read them itself without importing Qt. Handles both the grouped
    ('GamePaths/PatchPath_X') and flat key layouts, exactly as
    gamedef.getAvailableGameDefs does - the two forms both occur in the wild.
    """
    settings = getattr(globals_, 'settings', None)
    if settings is None:
        return []

    try:
        from reggie.io.gamedef import setting

        directories = []
        for key in settings.allKeys():
            name = key.split('/')[-1] if '/' in key else key
            if not name.startswith('PatchPath_'):
                continue

            value = setting(name)
            if value:
                directories.append(os.path.normpath(str(value)))

        return directories
    except Exception:
        # A patch we cannot enumerate is reported as missing, which is
        # recoverable; an exception here would stop the join entirely.
        return []


def _catalog_manager():
    try:
        from reggie.patches.catalog_manager import CatalogManager
        manager = CatalogManager()
        manager.load_catalog()
        return manager
    except Exception:
        # A broken catalog must never stop someone joining.
        return None
