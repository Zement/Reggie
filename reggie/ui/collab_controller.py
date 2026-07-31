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

import hmac
import os
import time

from PyQt6 import QtCore, QtWidgets

from reggie.collab import (
    broadcast, debuglog, discovery, files, identity, protocol, session, sync,
    transport, upnp,
)
from reggie.core import globals_
from reggie.ui import collab_dialogs
from reggie.ui.collab_bridge import CollabBridge


# Minimum gap between snapshot requests. A resync is usually triggered by a
# problem that will affect the next edit too, so without a floor here one broken
# reference produces a request per edit.
RESYNC_INTERVAL_SECONDS = 5.0

# Shown on a control the current session does not allow. Explains *why* it is
# unavailable, since a greyed-out menu item with no reason reads as a bug.
_PERMISSION_HINT = ('Not available during this collaboration session: the host '
                    'decides which level and patch everyone is editing.')


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
        self.signals.operationRejected.connect(self._onOperationRejected)
        self.signals.connected.connect(self._onConnected)
        self.signals.roomInfoChanged.connect(self._onRoomInfoChanged)
        self.signals.disconnected.connect(self._onDisconnected)
        self.signals.rejected.connect(self._onRejected)
        self.signals.roleChanged.connect(self._onRoleChanged)

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
             discoverable=False, upnp_enabled=False, **_extra):
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
        address = self._advertisedAddress(upnp_enabled, actual_port)

        self.join_code = identity.encode_join_code(
            address, actual_port, fingerprint, secret)

        self.mode = 'host'
        self.applyEditingPermissions()

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
            return address

        try:
            self.mapping = upnp.PortMapping.create(port, address)
        except upnp.UPnPError as exc:
            self._appendStatus('Automatic port forwarding failed: %s' % exc)
            return address

        self._appendStatus('Port %d forwarded via UPnP.' % port)

        external = upnp.external_ip_address(self.mapping.control_url,
                                            self.mapping.service_type)
        if external:
            return external

        self._appendStatus(
            'The router did not report a usable public address; the join code '
            'uses your local address, which only works on this network.')
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

        self.status_window.show()
        self.status_window.raise_()

    def _appendStatus(self, text):
        if self.status_window is not None:
            self.status_window.appendStatus(text)

    # -- host actions -------------------------------------------------------

    def _sendChat(self, text):
        if self.host_session is not None:
            self.host_session.send_chat(text)
            return

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_CHAT, {'text': text,
                                  'kind': protocol.CHAT_KIND_USER}))

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

        active = self.is_active
        host = self.is_host

        # A Full client is trusted with the session's level and area, exactly
        # like the host. The role is what the distinction rests on, not being
        # the host: an Editor client may change neither.
        may_lead = (not active) or host or self._clientHasFullRole()
        may_change_area = may_lead

        def enable(name, allowed):
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
                              else _PERMISSION_HINT)

        # Level loading: anyone trusted to lead, and only by name. "Open by
        # file" stays disabled for everybody in a session, including the host,
        # because a path outside the patch's stage folder cannot be resolved
        # from a name on another machine.
        enable('newlevel', may_lead)
        enable('openfromname', may_lead)
        enable('openfromfile', not active)
        enable('openrecent', may_lead)

        # Game patch: host only, whatever the client's role. Switching patch
        # reloads spritedata and tilesets under a level the host owns.
        enable('changegamedef', not active or host)

        self._setWidgetAllowed(getattr(window, 'patchComboBox', None),
                               'patchComboBox', not active or host)
        self._setWidgetAllowed(getattr(window, 'areaComboBox', None),
                               'areaComboBox', may_change_area)

        for name in ('addarea', 'importarea', 'deletearea'):
            enable(name, may_change_area)

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
        if self._suppress_level_notify:
            return False

        if not self.is_host:
            if not self._clientHasFullRole():
                self._appendStatus(
                    'You changed level or area locally; reloading the host\'s.')
                self._requestResync(force=True)
                return False

            # Tell the host what to switch everyone to. The host owns
            # redistribution, so this asks rather than broadcasts.
            self.client.send(protocol.make_message(
                protocol.T_AREA_SWITCH, self._levelChangePayload()))

            self._appendStatus('Asked the host to switch to %s.'
                               % self._describeCurrentLevel())
            debuglog.log('client', 'requested level change',
                         level=self._describeCurrentLevel())
            return True

        # The old references are meaningless now.
        self.refmap = sync.RefMap(origin='host', is_authority=True)
        self._seedRefMap()

        self.host_session.set_room_info(self._roomInfo())

        # Name the level before sending its contents: a client that receives a
        # snapshot without knowing which level it belongs to cannot update its
        # own title bar or file path.
        self._broadcastLevelChange()
        self._broadcastSnapshot()

        level = str(getattr(globals_, 'levelName', '') or 'the level')
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

    def _onLevelSwitchRequested(self, level, area):
        """
        Loads the level and area a peer moved the session to.

        Runs on the main thread. Guarded against loading what we already have,
        which would otherwise recurse: LoadLevel calls notifyLevelChanged, which
        is what sent or received this in the first place.
        """
        if not self.is_active:
            return False

        if level == self._currentLevelName() and area == self._areaNumber():
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

        self._appendStatus('Loading %s from the session.' % level)

        if not self._loadLevelQuietly(level, False, area):
            self._appendStatus(
                'Could not load %s - check that you have the same patch.'
                % level)
            return False

        return self._afterSessionLoad()

    def _loadLevelQuietly(self, name, is_full_path, area):
        """
        Loads a level without announcing it back to the session.

        The suppression flag is a flag rather than a parameter because
        LoadLevel is reached through several handlers, and the recursion has to
        be blocked wherever it is called from. Cleared in a finally, so a failed
        load cannot leave the session permanently mute.
        """
        label = os.path.basename(str(name)) if name else 'the level'
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
            self._broadcastSnapshot()
        else:
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
        self._checkPatch(room_info)

        if self.client is not None:
            self.client.send(protocol.make_message(
                protocol.T_SNAPSHOT_REQUEST,
                {'area': int(room_info.get('area', 1) or 1)}))

    def _onRoomInfoChanged(self, room_info):
        """
        The host switched patch or level. Re-run the patch check, since what the
        client needs may have changed since it joined.
        """
        patch = str(room_info.get('patch_id', '') or '')
        self._appendStatus(
            'The host is now using: %s.' % (patch or 'the retail game'))
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

    def _onOperationRejected(self, reason):
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

    def broadcastCommand(self, command):
        """
        Sends a locally pushed undo command to the other peers.

        Called from UndoStack.push, so this is the main thread and the edit has
        already been applied. Returns True if anything was sent.
        """
        if not self.is_active or self.refmap is None:
            return False

        try:
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

    def _onSnapshot(self, payload):
        if self.refmap is None:
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

    def _configureDebugLog(self):
        """
        Turns the diagnostic log on or off to match the current preference.

        The path is reported in the status window when it is on, because a log
        nobody can find helps nobody.
        """
        if self.settings.get('debug_log'):
            path = debuglog.enable(_settings_directory())
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
        Decides how the host's patch should be obtained, and tells the user.

        Only reports here. Actually installing from the Patch Manager, or
        accepting a host transfer, is driven by the user from the status window -
        a join must not silently start downloading things.
        """
        catalog = _catalog_manager()
        allow_host = (self.settings.get('patch_source')
                      == collab_dialogs.PATCH_SOURCE_HOST)

        requirement = files.patch_requirement(room_info, catalog,
                                              allow_host_transfer=allow_host,
                                              extra_dirs=_external_patch_dirs())

        if requirement['source'] != files.SOURCE_LOCAL:
            self._appendStatus(requirement['message'])

    # -- helpers ------------------------------------------------------------

    def _roomInfo(self):
        return {
            'game_id': self._gameId(),
            'game_name': self._gameName(),
            'patch_id': self._patchId(),
            'patch_version': self._patchVersion(),
            'level_name': str(getattr(globals_, 'levelName', '') or ''),
            'area': 1,
        }

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


def _sprite_format():
    """
    The local sprite data format for decoding remote sprite data.

    Always local, never taken from the wire: a peer choosing how we parse bytes
    is a peer choosing what those bytes mean. Vanilla is RawData's own default
    (see RawData.from_bytes), so it is the right fallback rather than a guess.
    """
    from reggie.core.raw_data import RawData

    return RawData.Format.Vanilla


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
