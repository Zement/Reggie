"""
Collaboration UI: setup dialog, status window with chat, and the settings tab.

Deliberately minimalistic and Qt-native. Zement's instruction for this phase was
that the next block reshuffles and redesigns the UI, so anything elaborate here
would be thrown away. That means: stock widgets, stock layouts, no stylesheets, no
custom painting, no icons beyond what the editor already ships. The behaviour is
what has to be right; the appearance is explicitly temporary.

Three widgets:

    CollabSetupDialog   host or join, join code, LAN discovery, UPnP
    CollabStatusWindow  roster, chat, host controls (kick/ban/role)
    CollabSettingsTab   nickname, colour, presence display, patch source, bans

The security-relevant part of a UI like this is what it *tells* the user, so a few
things are load-bearing rather than cosmetic:

- A certificate pin mismatch is presented as possible interception, not as a
  network error. Those two need different reactions from the user.
- The patch transfer prompt names the host, the patch, the file count and the
  total size, and states that only data files are accepted.
- Bans are labelled as address-based and easily evaded, so nobody relies on one
  for safety.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.collab import discovery, identity, protocol, session, upnp
from reggie.core import globals_
from reggie.core.dirty import setSetting, setting


# Presence display preferences (spec section 5.2). These are LOCAL display
# choices; they never affect the sending side's rate limiting.
CURSORS_ALWAYS = 'always'
CURSORS_ON_MOVE = 'onmove'
CURSORS_NEVER = 'never'

# Where a client may get a patch it does not have. Read on the CLIENT only -
# the host never consults it, because it is the client deciding what it is
# willing to accept.
#
# PATCH_SOURCE_AUTO is the default and the sensible behaviour: try the catalog,
# fall back to the host. The original two values read as a preference order but
# behaved as an exclusive choice, so picking "From the Patch Manager" silently
# forbade the host transfer entirely - which is how Zement's first data-only
# test was refused with a message blaming the host.
PATCH_SOURCE_AUTO = 'auto'
PATCH_SOURCE_CATALOG = 'catalog'
PATCH_SOURCE_HOST = 'host'

DEFAULT_NICK = 'Player'


def _ignore(*_args, **_kwargs):
    """
    Default for the status window's callbacks, so an unwired action does nothing
    rather than raising inside a button handler.
    """


def _tr(numcode, *replacements):
    """
    Fetches a string from the 'Collab' translation section, falling back to the
    English literal if the section is missing.

    The fallback exists because a user running an older translation file should
    get readable English rather than a raw key, which is what a missing lookup
    would otherwise produce.
    """
    try:
        text = globals_.trans.string('Collab', numcode, *replacements)
    except Exception:
        return _FALLBACKS.get(numcode, '')

    if not text:
        return _FALLBACKS.get(numcode, '')

    return text


_FALLBACKS = {
    0: 'Collaboration',
    1: 'Host a session',
    2: 'Join a session',
    3: 'Join code',
    4: 'Nickname',
    5: 'Make this session discoverable on my network',
    6: 'Forward the port automatically (UPnP)',
    7: 'Sessions found on your network',
    8: 'Start hosting',
    9: 'Join',
    10: 'Participants',
    11: 'Chat',
    12: 'Send',
    13: 'Change role',
    14: 'Remove from session',
    15: 'Ban address',
    16: 'Banned addresses',
    17: 'Remove ban',
    18: 'Show other users\' cursors',
    19: 'Show other users\' clicks',
    20: 'Get a missing patch (as a client)',
    21: 'Nickname colour',
    22: 'Always',
    23: 'Only while moving items',
    24: 'Never',
    25: 'Only from the Patch Manager',
    26: 'Only from the host (data files only)',
    27: 'Patch Manager, then the host (recommended)',
    # D-d.5's two log tabs. 11 ('Chat') names the tab holding what people typed;
    # 28 names the one holding everything in arrival order, which is what gets
    # saved as the session's record.
    28: 'Activity',
}


# ---------------------------------------------------------------------------
# Settings access
# ---------------------------------------------------------------------------

def load_collab_settings():
    """
    Reads the collaboration preferences, with defaults matching the spec.
    """
    return {
        'nick': str(setting('CollabNick', '') or '') or DEFAULT_NICK,
        'color': str(setting('CollabColor', '') or '')
                 or session.DEFAULT_NICK_COLORS[0],
        'cursors': str(setting('CollabCursors', '') or '') or CURSORS_ON_MOVE,
        'clicks': bool(setting('CollabClicks', True)),
        'patch_source': _patch_source_setting(),
        # Both default to on: the common case is hosting for someone, and both
        # only ever take effect while hosting. Discovery answers LAN probes by
        # unicast and carries no secret; UPnP is what makes a join code usable
        # over the internet at all, and its mapping is leased and removed when
        # the session ends. A host who wants neither can still turn them off,
        # and that choice is remembered.
        'discoverable': _default_true_setting('CollabDiscoverable'),
        'upnp': _default_true_setting('CollabUPnP'),
        'port': int(setting('CollabPort', identity.DEFAULT_HOST_PORT) or
                    identity.DEFAULT_HOST_PORT),
        'debug_log': bool(setting('CollabDebugLog', False)),
        'firewall_prompt': bool(setting('CollabFirewallPrompt', True)),
    }


def _patch_source_setting():
    """
    The stored patch source, migrating the value the old two-way choice wrote.

    'catalog' used to be the default and meant "prefer the catalog", but it was
    read as an exclusive choice and forbade a host transfer even for a patch the
    catalog does not have. Anyone who never touched the setting therefore has
    'catalog' stored while having chosen nothing, so it is migrated to AUTO,
    which is what that default was meant to mean. A deliberate choice is kept:
    it is only distinguishable from the default by having been written since,
    which is why the migration is one-way and the new values are never rewritten.
    """
    stored = str(setting('CollabPatchSource', '') or '')

    if stored == PATCH_SOURCE_CATALOG and not setting('CollabPatchSourceV2', False):
        return PATCH_SOURCE_AUTO

    return stored or PATCH_SOURCE_AUTO


def _default_true_setting(key):
    """
    A boolean preference whose default changed from off to on.

    A stored False is ambiguous: it is what the old default wrote for everyone
    who never touched the control, and also what a deliberate "off" writes. The
    save side stamps <key>V2 once the user has been through the new dialog, so
    only an unstamped False is treated as the old default and flipped.
    """
    if not setting(key + 'V2', False):
        return True

    return bool(setting(key, True))


def save_collab_settings(values):
    setSetting('CollabNick', values.get('nick', DEFAULT_NICK))
    setSetting('CollabColor', values.get('color', ''))
    setSetting('CollabCursors', values.get('cursors', CURSORS_ON_MOVE))
    setSetting('CollabClicks', bool(values.get('clicks', True)))
    setSetting('CollabPatchSource', values.get('patch_source',
                                               PATCH_SOURCE_AUTO))
    # Marks the stored value as written by the three-way control, so a
    # deliberate "Only from the Patch Manager" is never migrated to AUTO.
    setSetting('CollabPatchSourceV2', True)
    setSetting('CollabDiscoverable', bool(values.get('discoverable', True)))
    setSetting('CollabUPnP', bool(values.get('upnp', True)))
    # Stamps both as written by the current dialog, so a deliberate "off" is
    # never mistaken for the old default and flipped back on.
    setSetting('CollabDiscoverableV2', True)
    setSetting('CollabUPnPV2', True)
    setSetting('CollabPort', int(values.get('port', identity.DEFAULT_HOST_PORT)))
    setSetting('CollabDebugLog', bool(values.get('debug_log', False)))
    setSetting('CollabFirewallPrompt',
               bool(values.get('firewall_prompt', True)))


def load_ban_list():
    """
    Bans persist across sessions, so a banned peer cannot simply wait for a
    restart. Stored as 'ip|nick' lines, since QSettings handles plain strings far
    more predictably across platforms than nested structures.
    """
    raw = setting('CollabBans', '') or ''
    entries = []

    for line in str(raw).split('\n'):
        line = line.strip()
        if not line:
            continue
        address, _, nick = line.partition('|')
        address = address.strip()
        if address:
            entries.append((address, nick.strip()))

    return entries


def save_ban_list(entries):
    setSetting('CollabBans', '\n'.join(
        '%s|%s' % (address, nick) for address, nick in entries))


# ---------------------------------------------------------------------------
# Setup dialog
# ---------------------------------------------------------------------------

class CollabSetupDialog(QtWidgets.QDialog):
    """
    Host or join a session.

    Two tabs rather than a mode switch, because the two paths share almost no
    fields: hosting produces a join code, joining consumes one.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_tr(0))

        self.settings = load_collab_settings()
        self.result_mode = None      # 'host' | 'join'
        self.result_values = {}

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._buildHostTab(), _tr(1))
        self.tabs.addTab(self._buildJoinTab(), _tr(2))

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._handleAccept)
        self.buttons.rejected.connect(self.reject)
        self.tabs.currentChanged.connect(self._updateOkText)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.tabs)
        layout.addWidget(self.buttons)
        self.setLayout(layout)

        self.browser = None
        self._updateOkText()
        self._checkHostingPossible()

    # -- host tab -----------------------------------------------------------

    def _buildHostTab(self):
        widget = QtWidgets.QWidget()

        self.hostNick = QtWidgets.QLineEdit(self.settings['nick'])
        self.hostNick.setMaxLength(protocol.MAX_NICK_CHARS)

        self.hostPort = QtWidgets.QSpinBox()
        self.hostPort.setRange(1024, 65535)
        self.hostPort.setValue(self.settings['port'])

        self.hostDiscoverable = QtWidgets.QCheckBox(_tr(5))
        self.hostDiscoverable.setChecked(self.settings['discoverable'])

        self.hostUPnP = QtWidgets.QCheckBox(_tr(6))
        self.hostUPnP.setChecked(self.settings['upnp'])

        self.hostWarning = QtWidgets.QLabel()
        self.hostWarning.setWordWrap(True)
        self.hostWarning.setVisible(False)

        addresses = QtWidgets.QLabel(self._describeAddresses())
        addresses.setWordWrap(True)

        layout = QtWidgets.QFormLayout()
        layout.addRow(_tr(4), self.hostNick)
        layout.addRow('Port', self.hostPort)
        layout.addRow(self.hostDiscoverable)
        layout.addRow(self.hostUPnP)
        layout.addRow(addresses)
        layout.addRow(self.hostWarning)
        widget.setLayout(layout)

        return widget

    @staticmethod
    def _describeAddresses():
        """
        The address peers on this network would use.

        Deliberately says *on this network*: the public address is not known
        until hosting starts and the router has been asked, so naming this one
        "your address" invites the reading that it is the one to share. Zement
        hit exactly that confusion - a join code correctly carrying the public
        address, next to a dialog still showing 192.168.1.100.
        """
        from reggie.collab import transport

        try:
            addresses = transport.local_ip_addresses()
        except Exception:
            addresses = []

        if not addresses:
            return 'Your address on this network could not be determined.'

        # The first entry comes from the routing table - the address this
        # machine would actually use to reach the internet - and the rest are
        # other adapters. Saying which is which matters on a machine with
        # virtual adapters, where the list is long and only one entry is the
        # real one; presenting four addresses as equals invites the reader to
        # guess, and to conclude the wrong one was chosen.
        primary = addresses[0]
        others = addresses[1:]

        text = 'Your address on this network: %s' % primary
        if others:
            text += '\nOther adapters on this machine: %s' % ', '.join(others)

        return (text + '\nFor play over the internet the join code will use '
                'your public address instead, once the router has been asked.')

    def _checkHostingPossible(self):
        """
        Hosting needs a certificate backend; joining does not. Saying so up front
        beats letting the user configure a session and fail at the last step.
        """
        if identity.generation_backend() is not None:
            return

        self.hostWarning.setText(
            'Hosting is unavailable: creating the security certificate needs '
            'either the "cryptography" Python package or the "openssl" program. '
            'You can still join a session hosted by someone else.')
        self.hostWarning.setVisible(True)

    # -- join tab -----------------------------------------------------------

    def _buildJoinTab(self):
        widget = QtWidgets.QWidget()

        self.joinNick = QtWidgets.QLineEdit(self.settings['nick'])
        self.joinNick.setMaxLength(protocol.MAX_NICK_CHARS)

        self.joinCode = QtWidgets.QLineEdit()
        self.joinCode.setPlaceholderText('%s:host:port:...' % identity.JOIN_CODE_TAG)
        self.joinCode.textChanged.connect(self._validateCode)

        self.joinCodeStatus = QtWidgets.QLabel()
        self.joinCodeStatus.setWordWrap(True)

        self.discoveryList = QtWidgets.QListWidget()
        self.discoveryList.setMaximumHeight(120)
        self.discoveryList.itemDoubleClicked.connect(self._useDiscovered)

        self.discoveryStatus = QtWidgets.QLabel('Looking for sessions...')
        self.discoveryStatus.setWordWrap(True)

        layout = QtWidgets.QFormLayout()
        layout.addRow(_tr(4), self.joinNick)
        layout.addRow(_tr(3), self.joinCode)
        layout.addRow(self.joinCodeStatus)
        layout.addRow(QtWidgets.QLabel(_tr(7)))
        layout.addRow(self.discoveryList)
        layout.addRow(self.discoveryStatus)
        widget.setLayout(layout)

        return widget

    def _validateCode(self, text):
        """
        Live feedback while typing, because a join code is long and hand-copied.
        """
        text = text.strip()
        if not text:
            self.joinCodeStatus.setText('')
            return

        try:
            parsed = identity.decode_join_code(text)
        except identity.JoinCodeError as exc:
            self.joinCodeStatus.setText('Not a valid join code: %s' % exc)
            return

        self.joinCodeStatus.setText(
            'Will connect to %s on port %d.' % (parsed['host'], parsed['port']))

    def _useDiscovered(self, item):
        """
        A discovered session still needs the full code: discovery deliberately
        carries no secret. Filling in the address is all we can honestly do.
        """
        offer = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        address = offer.get('address', '')
        port = offer.get('port', identity.DEFAULT_HOST_PORT)

        self.joinCodeStatus.setText(
            'Found %s at %s:%d. Paste the join code they gave you - a '
            'discovered session still needs it.'
            % (offer.get('nick', 'a session'), address, port))

    # -- discovery ----------------------------------------------------------

    def startDiscovery(self):
        """
        Begins browsing the LAN. Separate from __init__ so a caller (or a test)
        can open the dialog without touching the network.
        """
        if self.browser is not None:
            return

        self._pending = []
        self.browser = discovery.DiscoveryBrowser(self._onOffer, interval=3.0)

        # The browser thread cannot touch widgets, so offers are queued and drained
        # by a timer on the main thread.
        self._drainTimer = QtCore.QTimer(self)
        self._drainTimer.timeout.connect(self._drainOffers)
        self._drainTimer.start(500)

        try:
            self.browser.start()
        except Exception as exc:
            self.discoveryStatus.setText('Network discovery unavailable: %s' % exc)
            self.browser = None

    def _onOffer(self, offer):
        # Runs on the browser thread: only append, never touch a widget.
        self._pending.append(offer)

    def _drainOffers(self):
        if not self._pending:
            if self.browser is not None and self.browser.last_error:
                self.discoveryStatus.setText(
                    'Network discovery: %s' % self.browser.last_error)
            return

        pending, self._pending = self._pending, []

        for offer in pending:
            key = '%s:%d' % (offer.get('address', ''), offer.get('port', 0))

            existing = None
            for row in range(self.discoveryList.count()):
                item = self.discoveryList.item(row)
                if item is not None and item.data(
                        QtCore.Qt.ItemDataRole.UserRole + 1) == key:
                    existing = item
                    break

            label = '%s - %s (%d/%d)' % (
                offer.get('nick', '?') or '?',
                offer.get('game', 'unknown game') or 'unknown game',
                offer.get('players', 0), offer.get('max_players', 0))

            item = existing or QtWidgets.QListWidgetItem()
            item.setText(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, offer)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, key)

            if existing is None:
                self.discoveryList.addItem(item)

        self.discoveryStatus.setText(
            '%d session(s) found. Double-click one to see its address.'
            % self.discoveryList.count())

    def stopDiscovery(self):
        timer = getattr(self, '_drainTimer', None)
        if timer is not None:
            timer.stop()

        if self.browser is not None:
            self.browser.stop()
            self.browser = None

    def closeEvent(self, event):
        self.stopDiscovery()
        super().closeEvent(event)

    def reject(self):
        self.stopDiscovery()
        super().reject()

    # -- accept -------------------------------------------------------------

    def _updateOkText(self):
        button = self.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if button is not None:
            button.setText(_tr(8) if self.tabs.currentIndex() == 0 else _tr(9))

    def collectResult(self):
        """
        Validates the current tab and fills in result_mode/result_values.

        Returns '' on success, or an error message for the caller to show. Kept
        separate from _handleAccept so the validation can be exercised without a
        modal dialog - a QMessageBox blocks forever under an offscreen platform,
        which would make this untestable.
        """
        if self.tabs.currentIndex() == 0:
            if identity.generation_backend() is None:
                return self.hostWarning.text()

            self.result_mode = 'host'
            self.result_values = {
                'nick': self.hostNick.text().strip() or DEFAULT_NICK,
                'port': self.hostPort.value(),
                'discoverable': self.hostDiscoverable.isChecked(),
                'upnp': self.hostUPnP.isChecked(),
            }
            self._rememberPreferences()
            return ''

        try:
            parsed = identity.decode_join_code(self.joinCode.text().strip())
        except identity.JoinCodeError as exc:
            return 'That join code cannot be used: %s' % exc

        self.result_mode = 'join'
        self.result_values = {
            'nick': self.joinNick.text().strip() or DEFAULT_NICK,
            'host': parsed['host'],
            'port': parsed['port'],
            'pin': parsed['pin'],
            'secret': parsed['secret'],
        }
        self._rememberPreferences()
        return ''

    def _rememberPreferences(self):
        """
        Persists the nickname, and the host options when hosting, so the next
        session starts from what the user chose last time.

        Called from collectResult rather than _handleAccept: persisting is part
        of accepting a valid result, not of dismissing the dialog.
        """
        values = load_collab_settings()
        values['nick'] = self.result_values['nick']

        if self.result_mode == 'host':
            values['port'] = self.result_values['port']
            values['discoverable'] = self.result_values['discoverable']
            values['upnp'] = self.result_values['upnp']

        save_collab_settings(values)

    def _handleAccept(self):
        error = self.collectResult()
        if error:
            QtWidgets.QMessageBox.warning(self, _tr(0), error)
            return

        self.stopDiscovery()
        self.accept()


# ---------------------------------------------------------------------------
# Status window
# ---------------------------------------------------------------------------

class CollabStatusWindow(QtWidgets.QDialog):
    """
    The session's roster and chat, plus the host's controls.

    Non-modal, so the user can keep editing with it open. Host controls are
    created only for a host - a client has nothing to enforce with, so offering
    the buttons would be a lie about who decides.
    """

    def __init__(self, is_host, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_tr(0))
        self.is_host = bool(is_host)

        # Callbacks the controller installs. Declared as no-op callables rather
        # than None so a missing wiring is a silent no-op instead of a crash in
        # a button handler, and so the attribute type is stable.
        self.kickRequested = _ignore
        self.banRequested = _ignore
        self.roleRequested = _ignore
        self.chatRequested = _ignore
        self.leaveRequested = _ignore

        self._join_code = ''

        # Presence (Block C - B3): who is busy, and the participants list to
        # rebuild from. Kept apart because they arrive in different messages -
        # a roster carries no busy state and a presence message carries no
        # roster - and the list has to be redrawn from both.
        self._busy = {}
        self._roster_entries = []

        self.roster = QtWidgets.QListWidget()

        # No minimum width since D-d.5. It was 200 for a 560px dialog; in a
        # ~260px sidebar slice a floor that size forces a horizontal scrollbar
        # on the whole column. The roster elides instead, and the busy detail
        # that would be cut off is in the tooltip.
        self.roster.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.roster.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Two views of one conversation (D-d.5, Zement's brief 2026-09-02).
        # `chatLog` holds **everything**, in arrival order; `userLog` holds only
        # what people typed. The split is presentation - the distinction it
        # splits on is already carried and already trustworthy, since the host
        # stamps `kind` on every message and a client cannot forge it.
        #
        # The complete log is the one kept under the old name, deliberately.
        # `_writeChatLog` reads `window.chatLog.toPlainText()` to save the
        # session's record, and a split that quietly made that name mean "the
        # half without the status messages" would lose half of what happened
        # from every saved log, with nothing to notice it by.
        self.chatLog = QtWidgets.QTextEdit()
        self.chatLog.setReadOnly(True)

        self.userLog = QtWidgets.QTextEdit()
        self.userLog.setReadOnly(True)

        self.logTabs = QtWidgets.QTabWidget()
        self.logTabs.addTab(self.userLog, _tr(11))
        self.logTabs.addTab(self.chatLog, _tr(28))
        self.logTabs.setDocumentMode(True)

        # Titles without the unread marker, to put back when a tab is read.
        self._tabTitles = [self.logTabs.tabText(0), self.logTabs.tabText(1)]
        self._unread = [False, False]
        self.logTabs.currentChanged.connect(self._markTabRead)

        self.chatEntry = QtWidgets.QLineEdit()
        self.chatEntry.setMaxLength(protocol.MAX_CHAT_CHARS)
        self.chatEntry.returnPressed.connect(self._sendChat)

        sendButton = QtWidgets.QPushButton(_tr(12))
        sendButton.clicked.connect(self._sendChat)

        entryRow = QtWidgets.QHBoxLayout()
        entryRow.addWidget(self.chatEntry)
        entryRow.addWidget(sendButton)

        chatColumn = QtWidgets.QVBoxLayout()
        chatColumn.setContentsMargins(0, 0, 0, 0)
        chatColumn.addWidget(self.logTabs)
        chatColumn.addLayout(entryRow)

        rosterColumn = QtWidgets.QVBoxLayout()
        rosterColumn.setContentsMargins(0, 0, 0, 0)
        rosterColumn.addWidget(QtWidgets.QLabel(_tr(10)))
        rosterColumn.addWidget(self.roster)

        if self.is_host:
            self.roleButton = QtWidgets.QPushButton(_tr(13))
            self.roleButton.clicked.connect(self._changeRole)
            self.kickButton = QtWidgets.QPushButton(_tr(14))
            self.kickButton.clicked.connect(self._kick)
            self.banButton = QtWidgets.QPushButton(_tr(15))
            self.banButton.clicked.connect(self._ban)

            # One row rather than three stacked buttons (D-d.5). Stacked, the
            # host controls took three rows of a ~260px column before the chat
            # began; across, they are the width of a word each. They act on the
            # roster selection, so they belong against the roster either way.
            hostRow = QtWidgets.QHBoxLayout()
            hostRow.setContentsMargins(0, 0, 0, 0)
            for button in (self.roleButton, self.kickButton, self.banButton):
                # Or the three at their natural widths overflow a narrow column
                # and force a horizontal scrollbar on the whole sidebar.
                button.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Ignored,
                    QtWidgets.QSizePolicy.Policy.Fixed)
                hostRow.addWidget(button)

            rosterColumn.addLayout(hostRow)

            self.roster.currentRowChanged.connect(self._updateHostButtons)
            self._updateHostButtons(-1)

        # Session-level actions, separated from the per-participant controls
        # above because they act on the session rather than on whoever happens
        # to be selected.
        sessionRow = QtWidgets.QHBoxLayout()
        sessionRow.setContentsMargins(0, 0, 0, 0)

        if self.is_host:
            # The join code is otherwise unrecoverable: it is shown once when
            # hosting starts, and a host who dismissed that dialog without
            # copying it had no way to invite anybody afterwards.
            self.copyCodeButton = QtWidgets.QPushButton('Copy join code')
            self.copyCodeButton.clicked.connect(self._copyJoinCode)
            self.copyCodeButton.setEnabled(False)
            self.copyCodeButton.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Fixed)
            sessionRow.addWidget(self.copyCodeButton)

        self.leaveButton = QtWidgets.QPushButton(
            'End session' if self.is_host else 'Leave session')
        self.leaveButton.clicked.connect(self._leave)
        self.leaveButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                       QtWidgets.QSizePolicy.Policy.Fixed)
        sessionRow.addWidget(self.leaveButton)

        rosterColumn.addLayout(sessionRow)

        # Stacked, not side by side (Zement, 2026-09-02: "this is the only real
        # UI change needed"). The two columns were written for a 560px dialog;
        # in a ~260px sidebar slice they gave roughly 85px of roster beside
        # 175px of chat, and neither is usable at that width. Stacked, each gets
        # the full width and the user divides the height.
        #
        # A splitter rather than a plain layout, so that division is the user's:
        # a session with eight participants wants a tall roster, one with two
        # wants none of it. The sidebar section it sits in is itself in a
        # splitter, which is the same bargain one level up.
        rosterPane = QtWidgets.QWidget()
        rosterPane.setLayout(rosterColumn)

        chatPane = QtWidgets.QWidget()
        chatPane.setLayout(chatColumn)

        self.split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.split.addWidget(rosterPane)
        self.split.addWidget(chatPane)

        # The chat takes the slack: it is the part that grows without limit,
        # and a roster of three names does not want half the panel.
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.split)

        self.setLayout(layout)

        # Still a usable free-floating dialog: a session can start before the
        # shell exists, and the suites drive it with no sidebar at all.
        self.resize(360, 480)

        # In a QDialog every QPushButton is auto-default, so Enter activates
        # whichever button holds focus as well as sending the chat line. That
        # made pressing Enter after clicking "Change role" (or with focus on
        # "Leave session") disconnect the user mid-sentence - Zement watched
        # testers kick themselves this way.
        #
        # Done in one sweep over the children rather than per button, so a
        # control added later cannot quietly reintroduce it.
        for button in self.findChildren(QtWidgets.QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

        # Enter in the chat box now has exactly one meaning. Send is wired to
        # returnPressed, not made the default button: a default button would
        # fire whenever the dialog has focus anywhere, including in the roster.
        self.chatEntry.setFocus()

    # -- updates ------------------------------------------------------------

    def setRoster(self, participants):
        """
        Replaces the roster. Called from a bridge signal, so on the main thread.
        """
        previous = self._selectedSessionId()
        self.roster.clear()

        # Kept, because this rebuilds the list wholesale: the participants a
        # roster message carries say nothing about who is busy, so without this
        # the next roster broadcast would silently clear every busy marker.
        # Same shape as `previous` above, for the same reason.
        self._roster_entries = list(participants or [])

        for entry in participants:
            nick = entry.get('nick', '?')
            role = entry.get('role', '')

            label = nick
            if role == protocol.ROLE_HOST:
                label += ' (host)'
            elif role == protocol.ROLE_FULL:
                label += ' (full)'

            if not entry.get('app_version_ok', True):
                # A version mismatch is allowed but the user should know, since
                # the shared-plugins assumption depends on matching versions.
                label += ' - different Reggie version'

            session_id = str(entry.get('session_id', '') or '')

            # What this participant is doing, if anything (Block C - B3,
            # presence). The status bar names only one peer and collapses to a
            # count past that, so this is where the per-peer detail lives - and
            # it is the only place two simultaneous downloads can both be read.
            busy = self._busy.get(session_id)
            if busy:
                detail = str(busy.get('detail') or '').strip()
                if detail:
                    label += ' - %s' % detail

            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole,
                         entry.get('session_id', ''))

            # The role rides along so the host controls can tell a participant
            # apart from the host itself. Parsing it back out of the label would
            # break the moment the label is translated.
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, role)

            color = entry.get('color', '')
            if color:
                item.setForeground(QtGui.QColor(color))

            if busy:
                # Italic rather than a colour: the foreground is already the
                # peer's own identifying colour, and overwriting it to say
                # "busy" would trade a permanent fact for a temporary one.
                font = item.font()
                font.setItalic(True)
                item.setFont(font)

            self.roster.addItem(item)

            if entry.get('session_id') == previous:
                self.roster.setCurrentItem(item)

    def setBusyPeers(self, busy):
        """
        Records who is busy and redraws the roster (Block C - B3, presence).

        Held here rather than read from the controller, because the roster is
        rebuilt from a participants list that does not carry it.
        """
        busy = dict(busy or {})
        if busy == self._busy:
            # Presence arrives constantly - a download reports twice a second -
            # and rebuilding the list on every message would fight the user's
            # selection and scroll position for no visible change.
            return

        self._busy = busy
        self.setRoster(self._roster_entries)

    def appendChat(self, nick, text, kind=protocol.CHAT_KIND_USER):
        """
        Appends a chat line. System notices are visually distinct from user
        messages - the host stamps `kind`, and a client cannot forge it, so this
        distinction is trustworthy rather than decorative.

        Since D-d.5 it also decides *which tab* the line lands in. Everything
        goes to the full log; only what a person typed goes to the Chat tab.
        """
        if kind == protocol.CHAT_KIND_SYSTEM:
            self._append(self.chatLog, '<i>%s</i>' % _escape(text), 1)
            return

        if nick:
            line = '<b>%s:</b> %s' % (_escape(nick), _escape(text))
        else:
            line = _escape(text)

        self._append(self.userLog, line, 0)
        self._append(self.chatLog, line, 1)

    def appendStatus(self, text):
        """A local notice - not from the session, so the full log only."""
        self._append(self.chatLog, '<i>%s</i>' % _escape(text), 1)

    def _append(self, widget, html, tab):
        """Write one line, and mark its tab unread if it is not the one showing.

        Without the marker a status message arriving while the user is reading
        chat is invisible - the case Zement's brief called out when it asked for
        the tabs (2026-09-02).
        """
        widget.append(html)

        if self.logTabs.currentIndex() == tab:
            return

        if not self._unread[tab]:
            self._unread[tab] = True
            self.logTabs.setTabText(tab, self._tabTitles[tab] + ' *')

    def _markTabRead(self, index):
        if not (0 <= index < len(self._unread)):
            return

        if self._unread[index]:
            self._unread[index] = False
            self.logTabs.setTabText(index, self._tabTitles[index])

    # -- host actions -------------------------------------------------------

    def _selectedSessionId(self):
        item = self.roster.currentItem()
        if item is None:
            return ''
        return item.data(QtCore.Qt.ItemDataRole.UserRole) or ''

    def _selectedRole(self):
        item = self.roster.currentItem()
        if item is None:
            return ''
        return item.data(QtCore.Qt.ItemDataRole.UserRole + 1) or ''

    def _updateHostButtons(self, _row=-1):
        """
        None of the per-participant controls apply to the host itself.

        Promoting the host is meaningless - it already has every permission -
        and kicking or banning it would mean ending the session by disconnecting
        oneself, and adding one's own address to the ban list. Greyed out rather
        than silently ignored, so the reason is visible before the click.
        """
        selectable = (bool(self._selectedSessionId())
                      and self._selectedRole() != protocol.ROLE_HOST)

        for button in (self.roleButton, self.kickButton, self.banButton):
            button.setEnabled(selectable)

    def _sendChat(self):
        text = self.chatEntry.text().strip()
        if not text:
            return
        self.chatEntry.clear()
        self.chatRequested(text)

    def _changeRole(self):
        session_id = self._selectedSessionId()
        if not session_id:
            return

        choice, ok = QtWidgets.QInputDialog.getItem(
            self, _tr(13),
            'Role:',
            ['Canvas editing only', 'Full access (including dialogs)'],
            0, False)

        if not ok:
            return

        self.roleRequested(
            session_id,
            protocol.ROLE_FULL if choice.startswith('Full') else protocol.ROLE_EDITOR)

    def _leave(self):
        """
        Ends the session. A host is asked to confirm, because ending it
        disconnects everyone else; a client leaving affects only themselves, so
        it happens immediately.
        """
        if self.is_host:
            confirmed = QtWidgets.QMessageBox.question(
                self, _tr(0),
                'End the session for everyone?\n\n'
                'All participants will be disconnected. Your level stays as it '
                'is, and nothing is saved automatically.',
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No)

            if confirmed != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        self.leaveRequested()
        self.setSessionEnded()

    def setSessionEnded(self):
        """
        Puts the window into a finished state: the session is over, but the chat
        log stays readable rather than vanishing.
        """
        self.chatEntry.setEnabled(False)
        self.leaveButton.setEnabled(False)

        if self.is_host:
            for button in (self.roleButton, self.kickButton, self.banButton,
                           self.copyCodeButton):
                button.setEnabled(False)

    def setJoinCode(self, join_code):
        """
        Gives the window the code to copy. Host only.

        Held here rather than fetched on demand so the window has no reference
        to the session, and so the button can be disabled until there is
        actually something to copy.
        """
        self._join_code = str(join_code or '')
        if self.is_host:
            self.copyCodeButton.setEnabled(bool(self._join_code))

    def _copyJoinCode(self):
        code = getattr(self, '_join_code', '')
        if not code:
            return

        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is None:
            return

        clipboard.setText(code)
        # Confirmed in the chat log rather than a dialog: copying is a small
        # action and a modal box for it would be in the way.
        self.appendStatus('Join code copied to the clipboard.')

    def _kick(self):
        session_id = self._selectedSessionId()
        if not session_id:
            return
        self.kickRequested(session_id)

    def _ban(self):
        session_id = self._selectedSessionId()
        if not session_id:
            return

        confirmed = QtWidgets.QMessageBox.question(
            self, _tr(15),
            'Ban this participant?\n\n'
            'Bans apply to their network address only. Someone on a new address '
            'is treated as a new participant, so a ban stops a casual rejoin '
            'rather than a determined one. The join code is the real gate - '
            'change it if you need to lock the session down.',
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No)

        if confirmed == QtWidgets.QMessageBox.StandardButton.Yes:
            self.banRequested(session_id)


def _escape(text):
    """
    Escapes text for the rich-text chat log.

    protocol.sanitize_text has already stripped control characters, but the log
    is HTML, so markup must be escaped here too - otherwise a chat message could
    inject formatting or a link into someone else's window.
    """
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------

class CollabSettingsTab(QtWidgets.QWidget):
    """
    The Collaboration tab for the Preferences dialog.

    Follows the pattern of the other tabs in misc.py: an `info` string, a form
    layout, values read on construction and applied by the caller.
    """

    info = ('Settings for collaborative editing: your appearance to others, '
            'what you see of them, and where game patches come from.')

    def __init__(self, parent=None):
        super().__init__(parent)

        values = load_collab_settings()

        self.nick = QtWidgets.QLineEdit(values['nick'])
        self.nick.setMaxLength(protocol.MAX_NICK_CHARS)

        self.color = QtWidgets.QComboBox()
        for index, color in enumerate(session.DEFAULT_NICK_COLORS):
            self.color.addItem(_colorSwatch(color), color, color)
            if color == values['color']:
                self.color.setCurrentIndex(index)

        self.cursors = QtWidgets.QComboBox()
        self.cursors.addItem(_tr(22), CURSORS_ALWAYS)
        self.cursors.addItem(_tr(23), CURSORS_ON_MOVE)
        self.cursors.addItem(_tr(24), CURSORS_NEVER)
        self.cursors.setCurrentIndex(
            max(0, self.cursors.findData(values['cursors'])))

        self.clicks = QtWidgets.QCheckBox(_tr(19))
        self.clicks.setChecked(values['clicks'])

        self.patchSource = QtWidgets.QComboBox()
        self.patchSource.addItem(_tr(27), PATCH_SOURCE_AUTO)
        self.patchSource.addItem(_tr(25), PATCH_SOURCE_CATALOG)
        self.patchSource.addItem(_tr(26), PATCH_SOURCE_HOST)
        self.patchSource.setCurrentIndex(
            max(0, self.patchSource.findData(values['patch_source'])))

        patchHint = QtWidgets.QLabel(
            'This is your own choice as a client - it has no effect while you '
            'are hosting. The Patch Manager is preferred where it has the '
            'patch: its files come from the catalog rather than from another '
            'player, and installing from it is asked for separately. A host '
            'transfer runs without asking - joining a session is the consent - '
            'and never accepts program code, so custom sprite previews are not '
            'included.\n\n'
            'While you are in a session, the levels and tilesets it uses are '
            'kept in assets/mods/_collab, and files there may be created or '
            'replaced by the session - including when the host saves. Your own '
            'game folders are never written to.')
        patchHint.setWordWrap(True)

        self.banList = QtWidgets.QListWidget()
        self.banList.setMaximumHeight(90)
        self._reloadBans()

        removeBan = QtWidgets.QPushButton(_tr(17))
        removeBan.clicked.connect(self._removeBan)

        layout = QtWidgets.QFormLayout()
        layout.addRow(_tr(4), self.nick)
        layout.addRow(_tr(21), self.color)
        layout.addRow(_tr(18), self.cursors)
        layout.addRow(self.clicks)
        layout.addRow(_tr(20), self.patchSource)
        layout.addRow(patchHint)
        layout.addRow(_tr(16), self.banList)
        layout.addRow(removeBan)

        self.firewallPrompt = QtWidgets.QCheckBox(
            'Ask the firewall for permission at startup')
        self.firewallPrompt.setChecked(
            bool(values.get('firewall_prompt', True)))
        self.firewallPrompt.setToolTip(
            'Briefly listens on the collaboration port when Reggie starts, so '
            'Windows asks for firewall permission then rather than in the '
            'middle of hosting a session. Never creates a firewall rule '
            'itself - the prompt is yours to answer.')
        layout.addRow(self.firewallPrompt)

        self.debugLog = QtWidgets.QCheckBox('Write a collaboration debug log')
        self.debugLog.setChecked(bool(values.get('debug_log', False)))
        self.debugLog.setToolTip(
            'Records connections, operations and disconnects to a file, for '
            'diagnosing problems. Contains nicknames and level activity, but '
            'never the join code, session secret or authentication data.')
        layout.addRow(self.debugLog)

        self.setLayout(layout)

    def _reloadBans(self):
        self.banList.clear()
        for address, nick in load_ban_list():
            label = '%s (%s)' % (address, nick) if nick else address
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, address)
            self.banList.addItem(item)

    def _removeBan(self):
        item = self.banList.currentItem()
        if item is None:
            return

        address = item.data(QtCore.Qt.ItemDataRole.UserRole)
        save_ban_list([(existing, nick) for existing, nick in load_ban_list()
                       if existing != address])
        self._reloadBans()

    def values(self):
        """
        The chosen settings, for the caller to persist on OK.
        """
        return {
            'nick': self.nick.text().strip() or DEFAULT_NICK,
            'color': self.color.currentData() or session.DEFAULT_NICK_COLORS[0],
            'cursors': self.cursors.currentData() or CURSORS_ON_MOVE,
            'clicks': self.clicks.isChecked(),
            'patch_source': self.patchSource.currentData() or PATCH_SOURCE_AUTO,
            'debug_log': self.debugLog.isChecked(),
            'firewall_prompt': self.firewallPrompt.isChecked(),
        }

    def apply(self):
        values = load_collab_settings()
        values.update(self.values())
        save_collab_settings(values)

        # A running session must pick the display choices up now. Otherwise
        # turning cursors off appears to do nothing until the session is
        # restarted, which reads as a broken setting.
        window = getattr(globals_, 'mainWindow', None)
        controller = getattr(window, '_collab', None)
        if controller is not None:
            try:
                controller.reloadPresencePreferences()
            except Exception:
                pass


def _colorSwatch(color, size=12):
    """
    A plain filled square for the colour combo box. Hand-drawn because the editor
    ships no colour swatch icons, and one pixmap is cheaper than adding assets
    that the next block's redesign would replace anyway.
    """
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtGui.QColor(color))
    return QtGui.QIcon(pixmap)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _exec_with_pointer(box):
    """
    Shows a modal without inheriting a wait cursor.

    Qt's override cursor is application-wide, so a dialog opened from inside a
    _BusyIndicator - and every prompt in a session can be, because those waits
    run processEvents and deliver the message that raises the prompt - shows
    the hourglass for its whole lifetime. The user is being asked a question
    while the editor claims to be busy, and the answer is what it is waiting
    for. Zement reported exactly that on the catalog route: the prompt, and
    then the Patch Manager, both busy for ten seconds or more (2026-08-11).

    Pushing an arrow on top for the dialog's lifetime is Qt's own idiom for
    this - the stack is restored exactly as it was, so an outer wait keeps its
    cursor afterwards. Applied even when nothing is overridden, which is
    harmless: push and pop are symmetrical either way.
    """
    QtWidgets.QApplication.setOverrideCursor(
        QtCore.Qt.CursorShape.ArrowCursor)
    try:
        return box.exec()
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


def confirm_catalog_install(parent, patch_id, patch_version=''):
    """
    The consent prompt before installing a patch from the Patch Manager catalog.

    Asked here and not for a host transfer, because the two are different acts.
    Accepting data files from the host means trusting a peer already
    authenticated by the pinned join code, which joining the session already
    expressed - so that route runs unprompted (Zement, 2026-08-06). Installing
    from the catalog reaches out to a *third party* the user has not vouched for
    in this session, over the internet, and writes an unpacked archive - so it
    is asked for explicitly even though it is the more "official" route.

    Declining ends the session (the client cannot hold the same level state
    without the patch), and the prompt says so rather than letting the
    disconnect look like a fault.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(_tr(0))
    box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    box.setText('Install the %s patch?' % patch_id)
    box.setInformativeText(
        'This session uses %s%s, which you do not have. It can be downloaded '
        'and installed from the Patch Manager.\n\n'
        'If you decline, you will leave the session.'
        % (patch_id,
           (' version %s' % patch_version) if patch_version else ''))
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes
                           | QtWidgets.QMessageBox.StandardButton.No)
    box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

    return _exec_with_pointer(box) == QtWidgets.QMessageBox.StandardButton.Yes


def report_patch_unavailable(parent, message):
    """
    Reports that the session's patch could not be obtained, so the session ended.

    Shown as information rather than a warning: declining an install is a
    legitimate choice, not a fault, and the common path to here is the user
    having just clicked No.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(_tr(0))
    box.setIcon(QtWidgets.QMessageBox.Icon.Information)
    box.setText('You have left the session.')
    box.setInformativeText(message)
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    _exec_with_pointer(box)


# report_content_mismatch was here, and is deliberately gone (round 2, R4).
#
# It was written when a mismatch meant "your Stage path differs from the host's"
# - the common case at the time, and one the user had to go and fix, so a modal
# was justified. R1 removed that reason to exist: the session transfers its
# Stage and Texture into _collab on every join route now, so both peers read
# files that came from the same place.
#
# What remains is a transfer that went wrong: rare, not the user's doing, and
# answered by re-syncing rather than by reading about folder layout. That is a
# status line, which is what _checkContentMatches writes. The dialog also fired
# on peers that were working perfectly - a level received from the host was
# compared against a fingerprint captured at join, which the host had edited
# past - so it interrupted correct sessions to report a non-problem.
#
# Left as a note rather than silently removed, because "why is there no longer a
# dialog for this" is a reasonable question to ask of this file later.


def confirm_large_transfer(parent, total_bytes, file_count):
    """
    Asks before starting a large game-data download (Block C - B3, round 2).
    Returns True to proceed.

    The download itself is not optional, and the wording has to be honest about
    that: a client without the host's levels and tilesets cannot see what
    everyone else sees, which is the whole problem this round removes. So the
    choice is "download, or leave" rather than "download, or carry on without
    it" - the second would produce exactly the desynced session the transfer
    exists to prevent.

    Only shown above ASSET_CONSENT_BYTES. A small transfer is automatic, because
    it lands in assets/mods/_collab/ and the client consented to that at join;
    the dialog exists for the case where the *wait* is worth warning about.
    """
    megabytes = total_bytes / (1024.0 * 1024.0)

    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle('Download the session\'s game data?')
    box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    box.setText('This session needs %.0f MB of levels and tilesets from the '
                'host.' % megabytes)
    box.setInformativeText(
        '%d files will be downloaded into assets/mods/_collab/, so none of '
        'your own game data is touched.\n\n'
        'This is what lets you see exactly what the host sees. If you decline, '
        'you will leave the session - taking part without these files would '
        'mean editing levels that look different on every machine.'
        % file_count)

    download = box.addButton('Download',
                             QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    box.addButton('Leave the session',
                  QtWidgets.QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(download)

    _exec_with_pointer(box)

    # Compared by identity rather than by standard button, because both are
    # custom buttons here. Anything other than Download - including the dialog
    # being closed - means the transfer does not start.
    return box.clickedButton() is download


def resolve_switch_proposal(parent, nick, destination):
    """
    Asks the host what to do about its unsaved work before a client's switch
    (Block C - B3, phase 3d). Returns 'save', 'discard', or 'cancel'.

    Shown only when the host actually has unsaved changes, so it is not a
    permission prompt - the client is allowed to do this. It is the host's own
    Save/Discard/Cancel, asked at the moment someone else's action would
    otherwise discard the work.

    Naming who asked is the point of having a dialog of its own rather than
    reusing CheckDirty's: a Save prompt appearing with nobody at the keyboard is
    alarming and unexplainable, and the host needs to know the move is coming
    from a person, not a fault.

    Cancel is the default. The safe answer when the host is not sure - or is not
    really reading - is the one that keeps their work and keeps the session
    where it is; both other answers are recoverable from, but a mis-clicked
    Discard is not.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle('Move the session?')
    box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    box.setText('%s wants to move the session to %s.' % (nick, destination))
    box.setInformativeText(
        'You have unsaved changes to the level that is open now.\n\n'
        'Save keeps them and then moves. Discard moves without keeping them. '
        'Cancel stays on this level and tells %s the request was declined.'
        % nick)
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Save
                           | QtWidgets.QMessageBox.StandardButton.Discard
                           | QtWidgets.QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)

    answer = _exec_with_pointer(box)

    if answer == QtWidgets.QMessageBox.StandardButton.Save:
        return 'save'
    if answer == QtWidgets.QMessageBox.StandardButton.Discard:
        return 'discard'

    # Anything else - including the window being closed - is a cancel. A dialog
    # dismissed without an answer must not be read as consent to discard.
    return 'cancel'


def resolve_join_publication(parent, nick):
    """
    Asks the host what to do about its unsaved work when someone joins
    (Block C - B3, round 2, R2). Returns 'save' or 'discard'.

    **The question is only whether to write to disk.** Both answers send the
    same thing: the level as it is on the host's screen, unsaved edits included.
    That is not what the first wording of this dialog said, and Zement caught it
    by testing both answers and finding they synced identically (2026-08-11).

    The reason is worth stating, because it is easy to assume otherwise:
    _publishLevelFile serialises from `Level.save()` - memory, not disk - so a
    peer always receives the host's current work. There is no code path here
    that sends the on-disk file, and adding one would be worse: the joining
    client would start from a level the host is not looking at.

    So "Discard" is a poor name for what the button does, and the labels say
    what actually happens instead. Kept as the Save/Discard *roles* underneath
    because Qt gives those the right placement and keyboard handling, and
    because the return values are what the caller already switches on.

    **There is deliberately no Cancel.** The joining client is waiting for a
    level file and both answers produce one; a third "do nothing" would leave
    the new peer with no level at all, which is the state R2 exists to remove.
    Zement's first instinct was Save / Discard / Cancel-terminates-session, and
    on reflection neither of us wanted a session killed by a dialog nobody asked
    for.

    Escape and the title-bar X both return Rejected from a QMessageBox, so
    omitting Cancel is not enough on its own - the dialog would still be
    dismissable into exactly the state that must not happen. The
    do-not-save answer is therefore installed as the escape button, and it is
    the safe default: nothing is lost either way, since the host keeps its work
    on screen and the peer gets it regardless.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle('Someone joined the session')
    box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    box.setText('%s joined, and you have unsaved changes.' % nick)
    box.setInformativeText(
        'They will be sent the level exactly as you see it now, including '
        'those changes, whichever you choose.\n\n'
        'The only question is whether to write them to disk at the same time.')

    save = box.addButton('Save to disk too',
                         QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    discard = box.addButton('Just send it',
                            QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(save)

    # Escape and the window's close button now mean Discard rather than
    # "no answer". Without this the dialog returns Rejected and the caller
    # cannot tell a deliberate Discard from a dismissal.
    box.setEscapeButton(discard)

    _exec_with_pointer(box)

    # Compared by identity, and Save has to be the *positive* test: anything
    # else - Discard, Escape, the title bar - is a discard. Reading it the other
    # way round would turn an unexpected result into a save the host never asked
    # for.
    return 'save' if box.clickedButton() is save else 'discard'


def report_pin_mismatch(parent, message):
    """
    Reports a certificate pin mismatch.

    Deliberately NOT phrased as a connection error: a pin mismatch means
    something answered in the host's place, or the host's identity changed. The
    user's correct response - ask for a fresh code, out of band - is different
    from what they would do about a network failure, so the wording has to make
    that clear.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle('Host identity does not match')
    box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    box.setText('This host could not be verified.')
    box.setInformativeText(
        '%s\n\nNothing was sent to it. Ask the host for a fresh join code '
        'through a channel you trust, and do not reuse the old one.' % message)
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    _exec_with_pointer(box)


def show_join_code(parent, join_code):
    """
    Shows the join code with a copy button. It is long, so retyping it is not a
    reasonable expectation.
    """
    display = identity.format_join_code_for_display(join_code)

    # Whether this code can work outside the local network. A private address
    # in a join code is the single most confusing failure this feature has:
    # everything reports success, the code looks perfectly valid, and the peer
    # gets a bare timeout or connection-refused with no hint of the cause.
    # Better to say so here, while the host still has the code in front of them.
    reach = ''
    try:
        parsed = identity.decode_join_code(join_code)
        host = parsed.get('host', '')
        if host and upnp.is_private_address(host):
            reach = (
                '\n\nNote: this code contains %s, a local network address. It '
                'works for people on your own network, but NOT over the '
                'internet - they would see a timeout or a refused connection.'
                '\n\nFor internet play the router has to forward port %d to '
                'this computer. Enable UPnP in the collaboration settings, or '
                'forward the port by hand and share your public address.'
                % (host, int(parsed.get('port', 0))))
    except Exception:
        # Never let a display nicety stop the host seeing their own code.
        reach = ''

    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(_tr(0))
    box.setIcon(QtWidgets.QMessageBox.Icon.Information)
    box.setText('Your session is running.')
    box.setInformativeText(
        'Send this join code to the people you want to invite. It contains the '
        'session password, so share it only with them:\n\n%s%s' % (display, reach))

    copyButton = box.addButton('Copy join code',
                               QtWidgets.QMessageBox.ButtonRole.ActionRole)
    box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)

    # Copying is what the dialog is for, and it is what the user almost always
    # wants next - dismissing without copying means retyping a long code.
    box.setDefaultButton(copyButton)
    _exec_with_pointer(box)

    if box.clickedButton() is copyButton:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(join_code)
            return True

    return False
