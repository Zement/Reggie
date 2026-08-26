"""Editor sessions - the state model behind one canvas tab (Block D).

Before this module, the editor could hold exactly one open area, in module-level
globals: ``globals_.Area``, ``globals_.Level``, ``globals_.Tiles`` and friends.
That is a single slot, so a tab bar cannot be built over it.

An :class:`EditorSession` is everything that must *not* be shared between two
open tabs. A :class:`LevelHandle` is everything that must be shared between two
tabs showing different areas of the same file. A :class:`SessionManager` owns
the set of sessions and which one is active.

Nothing here is wired into the editor yet; phase D-1 introduces the proxy that
makes ``globals_.Area`` resolve to the active session.

Why a handle sits between session and level
-------------------------------------------
Areas 1-4 of a level all live inside one ``.arc``, and ``Level_NSMBW.save()``
serialises *every* area from ``self.areas`` in one pass. So two sessions on
areas 1 and 2 of the same file must share a single ``Level_NSMBW``: if each
held its own copy, saving one would write that copy's idea of both areas and
silently drop the other tab's edits.

The handle is refcounted rather than owned by any one session, because the
order tabs close in must not decide which one keeps the level alive.
"""

import weakref


def open_level(level, file_path, area_num=1):
    """Replace the editor's open level with ``level``, as a session.

    Phase D-1 keeps the editor single-session: this closes whatever was open
    and opens one session on the new level, which reproduces the old
    ``globals_.Level = Level_NSMBW()`` behaviour exactly. Phase D-4 is where
    more than one may be open at a time.

    Returns the new session, or None when no manager is installed - the
    headless suites construct levels with no editor around them.
    """
    from reggie.core import globals_

    manager = globals_.get_session_manager()
    if manager is None:
        return None

    manager.close_all()

    # `level.areas` may still be empty here: Level_NSMBW.__init__ runs new()
    # before any area is populated, and load() fills them in afterwards. The
    # area is attached by set_current_area as loading proceeds.
    area = level.areas[area_num - 1] if len(level.areas) >= area_num else None

    return manager.open(level, file_path, area, area_num)


def set_current_area(area, area_num=None):
    """Point the active session - and spritelib - at ``area``.

    The one funnel for what used to be the pair

        globals_.Area = area
        SLib.Area = area

    written at each of the seven sites that changed the open area. spritelib
    keeps its *own* binding, which sprite rendering reads through, so a change
    that updates one and not the other makes sprites draw against the wrong
    area's data - a silent wrong-pixels bug rather than an exception. Funnelling
    both through here is what stops that pair drifting apart.

    Safe to call before a session manager exists: during boot, and in the
    headless test suites, ``Level_NSMBW`` is constructed with no session at all.
    """
    from reggie.core import globals_
    from reggie.core import spritelib as SLib

    SLib.Area = area

    manager = globals_.get_session_manager()
    if manager is None:
        return None

    session = manager.active
    if session is None:
        return None

    session.area = area
    if area_num is not None:
        session.area_num = area_num

    return session


class LevelHandle:
    """One open level file, shared by every session showing one of its areas.

    Holds the ``Level_NSMBW`` and the path it saves to. Sessions attach and
    detach; the level is released when the last one detaches.
    """

    def __init__(self, level, file_path):
        self.level = level
        self.file_path = file_path

        # Sessions are held weakly: the manager owns their lifetime, and a
        # strong set here would keep a closed tab's session alive.
        self._sessions = weakref.WeakSet()

    @property
    def refcount(self):
        return len(self._sessions)

    def attach(self, session):
        self._sessions.add(session)

    def detach(self, session):
        self._sessions.discard(session)
        return self.refcount

    def sessions(self):
        """The live sessions on this file, in no particular order."""
        return list(self._sessions)

    def __repr__(self):
        return '<LevelHandle %r refs=%d>' % (self.file_path, self.refcount)


class EditorSession:
    """One open area: the per-tab half of the editor's state.

    The level itself is *not* here - it lives on the shared :class:`LevelHandle`
    - but everything a tab must own privately is: its area, its scene and view,
    its undo stack, and its decoded tilesets.
    """

    def __init__(self, handle, area, area_num):
        self.handle = handle
        self.area = area
        self.area_num = area_num

        # Populated by later phases; declared here so the shape is visible in
        # one place rather than accreting attributes across the block.
        self.scene = None          # LevelScene            (phase D-3)
        self.view = None           # LevelViewWidget       (phase D-3)
        self.undo_stack = None     # UndoStack             (phase D-3)

        self.tiles = None          # 0x200*4 + overrides   (phase D-2)
        self.tileset_files = None  # the 4 slot paths      (phase D-2)
        self.object_defs = None    # ObjectDefinitions     (phase D-2)

        self.dirty = False

        # Bumped by the manager on every activation, so the tile-eviction pass
        # in phase D-2 can find the least recently used session without
        # needing a clock. Date.now-free by construction.
        self.last_active_serial = 0

        handle.attach(self)

    @property
    def level(self):
        """The shared level. Read through the handle so there is one owner."""
        return self.handle.level

    @property
    def file_path(self):
        return self.handle.file_path

    @property
    def has_tiles(self):
        """Whether this session is currently holding decoded tilesets."""
        return self.tiles is not None

    def release_tiles(self):
        """Drop decoded tilesets, keeping the level data and the scene.

        The memory-management half of the block: an idle tab gives back its
        tile arrays and re-decodes them when it is next activated. Cheap,
        because the tileset cache is keyed by resolved path.
        """
        self.tiles = None
        self.tileset_files = None
        self.object_defs = None

    def dispose(self):
        """Tear the session down and detach from the shared level.

        Returns the handle's remaining refcount, so the caller can tell whether
        the level itself should now be released.
        """
        self.release_tiles()
        self.scene = None
        self.view = None
        self.undo_stack = None
        return self.handle.detach(self)

    def __repr__(self):
        return '<EditorSession %r area=%d%s>' % (
            self.file_path, self.area_num, ' dirty' if self.dirty else '')


class SessionManager:
    """Owns the open sessions and which one is active.

    The active session is what ``globals_.Area`` and friends resolve to once
    phase D-1's proxy is in place. Nothing else in the editor should hold a
    long-lived reference to a session; ask the manager.
    """

    def __init__(self):
        self._sessions = []
        self._active = None
        self._handles = {}      # file_path -> LevelHandle
        self._serial = 0

    # -- queries ---------------------------------------------------------

    @property
    def active(self):
        return self._active

    @property
    def sessions(self):
        return list(self._sessions)

    def __len__(self):
        return len(self._sessions)

    def handle_for(self, file_path):
        """The open handle for a path, or None. Paths are the identity here."""
        return self._handles.get(file_path)

    def sessions_for(self, file_path):
        """Every open session showing an area of this file."""
        handle = self._handles.get(file_path)
        return handle.sessions() if handle is not None else []

    def find(self, file_path, area_num):
        """The session on this file and area, or None.

        Used to decide whether opening an area should raise an existing tab
        rather than making a second one for the same thing.
        """
        for session in self._sessions:
            if session.file_path == file_path and session.area_num == area_num:
                return session
        return None

    # -- mutation --------------------------------------------------------

    def open(self, level, file_path, area, area_num, activate=True):
        """Open an area as a new session, sharing the level if already open.

        Returns the existing session if this exact area is already open, so
        callers can use this as "show me this area" without checking first.
        """
        existing = self.find(file_path, area_num)
        if existing is not None:
            if activate:
                self.activate(existing)
            return existing

        handle = self._handles.get(file_path)
        if handle is None:
            handle = LevelHandle(level, file_path)
            self._handles[file_path] = handle

        session = EditorSession(handle, area, area_num)
        self._sessions.append(session)

        if activate or self._active is None:
            self.activate(session)

        return session

    def activate(self, session):
        """Make a session the active one. Returns the previously active one."""
        if session is not None and session not in self._sessions:
            raise ValueError('cannot activate a session this manager does not own')

        previous = self._active
        self._active = session

        if session is not None:
            self._serial += 1
            session.last_active_serial = self._serial

        return previous

    def close(self, session):
        """Close a session, releasing the level if it was the last on that file.

        Returns True if the underlying level was released.
        """
        if session not in self._sessions:
            raise ValueError('cannot close a session this manager does not own')

        self._sessions.remove(session)
        remaining = session.dispose()

        released = False
        if remaining == 0:
            self._handles.pop(session.file_path, None)
            released = True

        if self._active is session:
            # Fall back to the most recently active survivor, so closing a tab
            # lands somewhere predictable rather than on index 0.
            self._active = max(
                self._sessions,
                key=lambda s: s.last_active_serial,
                default=None,
            )

        return released

    def close_all(self):
        for session in list(self._sessions):
            self.close(session)

    # -- memory ----------------------------------------------------------

    def sessions_holding_tiles(self):
        return [s for s in self._sessions if s.has_tiles]

    def evict_tiles(self, keep=3):
        """Release decoded tilesets from all but the ``keep`` most recent.

        The active session is never evicted regardless of ``keep``.
        Returns the sessions that gave up their tiles.
        """
        holders = self.sessions_holding_tiles()
        if len(holders) <= keep:
            return []

        # Most recently active first; the active session sorts to the front by
        # construction, since activation bumps its serial.
        holders.sort(key=lambda s: s.last_active_serial, reverse=True)

        evicted = []
        for session in holders[keep:]:
            if session is self._active:
                continue
            session.release_tiles()
            evicted.append(session)

        return evicted

    # -- dirty / save ----------------------------------------------------

    def mark_dirty(self, session, dirty=True):
        session.dirty = dirty

    def dirty_files(self):
        """Paths with at least one unsaved session."""
        return sorted({s.file_path for s in self._sessions if s.dirty})

    def clear_dirty_for_file(self, file_path):
        """Clear dirty on every session sharing a file.

        Saving is per *file*: Level.save() serialises every area from the
        shared level in one pass, so a save from any tab persists all of them.
        Leaving the other tabs marked dirty would misreport that.
        """
        cleared = []
        for session in self.sessions_for(file_path):
            if session.dirty:
                session.dirty = False
                cleared.append(session)
        return cleared
