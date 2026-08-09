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

        self.roster = QtWidgets.QListWidget()
        self.roster.setMinimumWidth(200)

        self.chatLog = QtWidgets.QTextEdit()
        self.chatLog.setReadOnly(True)

        self.chatEntry = QtWidgets.QLineEdit()
        self.chatEntry.setMaxLength(protocol.MAX_CHAT_CHARS)
        self.chatEntry.returnPressed.connect(self._sendChat)

        sendButton = QtWidgets.QPushButton(_tr(12))
        sendButton.clicked.connect(self._sendChat)

        entryRow = QtWidgets.QHBoxLayout()
        entryRow.addWidget(self.chatEntry)
        entryRow.addWidget(sendButton)

        chatColumn = QtWidgets.QVBoxLayout()
        chatColumn.addWidget(QtWidgets.QLabel(_tr(11)))
        chatColumn.addWidget(self.chatLog)
        chatColumn.addLayout(entryRow)

        rosterColumn = QtWidgets.QVBoxLayout()
        rosterColumn.addWidget(QtWidgets.QLabel(_tr(10)))
        rosterColumn.addWidget(self.roster)

        if self.is_host:
            self.roleButton = QtWidgets.QPushButton(_tr(13))
            self.roleButton.clicked.connect(self._changeRole)
            self.kickButton = QtWidgets.QPushButton(_tr(14))
            self.kickButton.clicked.connect(self._kick)
            self.banButton = QtWidgets.QPushButton(_tr(15))
            self.banButton.clicked.connect(self._ban)

            rosterColumn.addWidget(self.roleButton)
            rosterColumn.addWidget(self.kickButton)
            rosterColumn.addWidget(self.banButton)

            self.roster.currentRowChanged.connect(self._updateHostButtons)
            self._updateHostButtons(-1)

        # Session-level actions, separated from the per-participant controls
        # above because they act on the session rather than on whoever happens
        # to be selected.
        rosterColumn.addSpacing(8)

        if self.is_host:
            # The join code is otherwise unrecoverable: it is shown once when
            # hosting starts, and a host who dismissed that dialog without
            # copying it had no way to invite anybody afterwards.
            self.copyCodeButton = QtWidgets.QPushButton('Copy join code')
            self.copyCodeButton.clicked.connect(self._copyJoinCode)
            self.copyCodeButton.setEnabled(False)
            rosterColumn.addWidget(self.copyCodeButton)

        self.leaveButton = QtWidgets.QPushButton(
            'End session' if self.is_host else 'Leave session')
        self.leaveButton.clicked.connect(self._leave)
        rosterColumn.addWidget(self.leaveButton)

        columns = QtWidgets.QHBoxLayout()
        columns.addLayout(rosterColumn, 1)
        columns.addLayout(chatColumn, 2)

        self.setLayout(columns)
        self.resize(560, 320)

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

            self.roster.addItem(item)

            if entry.get('session_id') == previous:
                self.roster.setCurrentItem(item)

    def appendChat(self, nick, text, kind=protocol.CHAT_KIND_USER):
        """
        Appends a chat line. System notices are visually distinct from user
        messages - the host stamps `kind`, and a client cannot forge it, so this
        distinction is trustworthy rather than decorative.
        """
        if kind == protocol.CHAT_KIND_SYSTEM:
            self.chatLog.append('<i>%s</i>' % _escape(text))
        elif nick:
            self.chatLog.append('<b>%s:</b> %s' % (_escape(nick), _escape(text)))
        else:
            self.chatLog.append(_escape(text))

    def appendStatus(self, text):
        self.chatLog.append('<i>%s</i>' % _escape(text))

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
            'included.')
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

    return box.exec() == QtWidgets.QMessageBox.StandardButton.Yes


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
    box.exec()


def report_content_mismatch(parent, problems):
    """
    Reports that this peer's files are not the host's (Block C - B3).

    A dialog rather than only a chat line, and this is the reason: the session
    reports everything as matching whenever the patch id and version agree, so a
    user with a divergent stage path has *no other signal at all* that they are
    looking at a different level. Zement's phase 2 test went looking for exactly
    this warning and found nothing, because the check had not run on the path a
    joining client actually takes.

    A warning, not an error: nothing is broken and no work is lost. The host's
    objects are correct and the client's edits still apply to them; what differs
    is the graphics behind them. The user can carry on if they choose to.

    Shown once per distinct mismatch per session - the caller keeps that state,
    because a resync arrives whenever the host edits anything and a dialog per
    snapshot would be unusable.
    """
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle('Different files from the host')
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setText('You are not seeing the same files as the host.')
    box.setInformativeText(
        'The session is using the same game patch, but your copies of these '
        'differ:\n\n  %s\n\n'
        'The host\'s objects are correct, and your edits will apply to them, '
        'but the graphics behind them may not match what everyone else sees.\n\n'
        'This usually means the patch points at a different Stage or Texture '
        'folder on your machine than it does on the host\'s.'
        % '\n  '.join(str(problem) for problem in (problems or ())))
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    box.exec()


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
    box.exec()


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
    box.exec()

    if box.clickedButton() is copyButton:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(join_code)
            return True

    return False
