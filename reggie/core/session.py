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


def _globals():
    """Deferred import: globals_ is imported by nearly everything."""
    from reggie.core import globals_
    return globals_


def open_level(level, file_path, area_num=1):
    """Replace the editor's open level with ``level``, as a session.

    Closes every open session and opens one on the new level. That is still the
    right behaviour after phase D-4: this is reached only when a *new*
    ``Level_NSMBW`` has been constructed - a new level, or a file read from disk
    - and every session open against the previous level refers to areas of a
    level object that is being replaced wholesale.

    Moving between areas of the level already open does not come through here;
    it goes to :func:`open_area`, which adds a session rather than replacing
    them. Opening several *files* at once is the UI block's concern, since it
    needs somewhere to show them.

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


def open_area(area_num):
    """Show another area of the level already open, as its own session.

    The counterpart to :func:`open_level` for a switch *within* a file. Returns
    the session showing that area - an existing one if it is already open, a new
    one on the same :class:`LevelHandle` otherwise - or None when there is no
    manager or no level open.

    This is what makes an area switch non-destructive. Before it, switching ran
    ``Level.changeArea()``, which calls ``Area.unload()`` on the outgoing area;
    ``unload()`` drops the parsed data without serialising, and ``Area.save()``
    then falls back to the raw archive bytes. So an edited area that was switched
    away from lost its edits, and the editor guarded against that by refusing to
    switch while dirty. Keeping both areas live removes the loss and the guard
    together.
    """
    from reggie.core import globals_

    manager = globals_.get_session_manager()
    if manager is None:
        return None

    current = manager.active
    if current is None:
        return None

    existing = manager.find(current.file_path, area_num)
    if existing is not None:
        manager.activate(existing)
        return existing

    level = current.level
    if level is None or len(level.areas) < area_num:
        return None

    area = level.areas[area_num - 1]

    # The session has to exist and be active *before* the area is loaded: an
    # area's load() builds its sprites, and a sprite image's findZone() reads
    # globals_.Area.zones while it is being constructed. That read resolves
    # through the active session, so a session opened afterwards would leave it
    # resolving to the outgoing area - the same ordering trap that made loading
    # a level with sprites raise in phase D-1.
    session = manager.open(level, current.file_path, area, area_num)

    if not area._is_loaded:
        area.load()
    elif session.tiles is None:
        # The area was already parsed - Add Area runs load_defaults(), and an
        # imported area arrives loaded - so area.load() is not called and never
        # builds this session's tilesets. Whatever loaded it did so against
        # whichever session was active at the time, whose slots those tiles went
        # into; the new session would otherwise hold none at all and render the
        # previous area's tiles or nothing.
        from reggie.core.tiles import CreateTilesets, LoadTileset

        CreateTilesets()
        for idx in range(4):
            name = getattr(area, 'tileset%d' % idx, '')
            if name:
                LoadTileset(idx, name)

    # Idle tabs give their decoded tiles back once enough have accumulated
    # (state-model plan §6.2). Here rather than inside activate(): a session is
    # activated the moment it is opened, before its tilesets have been loaded
    # into it, so sweeping there counts a half-built session as tile-less and
    # evicts a finished one to make room for it. Sweeping once the new session
    # is complete is both correct and the only point where the set actually
    # grows.
    manager.evict_tiles()

    return session


def set_current_tilesets(tiles, tileset_files, object_defs):
    """Install a fresh set of tileset slots on the active session.

    The counterpart to :func:`set_current_area` for the four tileset slots, and
    the only place they are rebound. Everything else in the editor writes into
    them in place, so those writes follow the session automatically.

    Like ``SLib.Area``, spritelib keeps its own ``SLib.Tiles`` binding that
    sprite rendering reads through, so it is re-pointed here rather than at the
    two ad-hoc sites it used to be set from.
    """
    from reggie.core import globals_
    from reggie.core import spritelib as SLib

    SLib.Tiles = tiles

    manager = globals_.get_session_manager()
    if manager is None:
        # No editor around this call - boot, or a headless suite. Fall back to
        # a module-level holder so the tileset code still has somewhere to
        # write; see _fallback_tilesets below.
        _fallback['tiles'] = tiles
        _fallback['tileset_files'] = tileset_files
        _fallback['object_defs'] = object_defs
        return None

    session = manager.active
    if session is None:
        _fallback['tiles'] = tiles
        _fallback['tileset_files'] = tileset_files
        _fallback['object_defs'] = object_defs
        return None

    session.tiles = tiles
    session.tileset_files = tileset_files
    session.object_defs = object_defs
    return session


#: Where the tileset slots live when there is no session yet.
#
# CreateTilesets() runs from Area.__init__, which the headless suites and the
# very first moments of boot reach before any session exists. Without this the
# slots would be None there and tile loading would fail on a NoneType index -
# a regression with no upside, since single-area behaviour must keep working
# unchanged throughout this block.
_fallback = {'tiles': None, 'tileset_files': None, 'object_defs': None}


def fallback_tilesets(name):
    return _fallback.get(name)


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

        # Built on first use, like the undo stack - see the scene/view
        # properties. Per session since D-c.1: before that one scene was shared
        # and emptied on every switch, which is what made an area change able to
        # destroy the outgoing area's items.
        self._scene = None         # LevelScene
        self._view = None          # LevelViewWidget
        self._undo_stack = None

        self.tiles = None          # 0x200*4 + overrides   (phase D-b.2)
        self.tileset_files = None  # the 4 slot paths      (phase D-b.2)
        self.object_defs = None    # ObjectDefinitions     (phase D-b.2)

        # What release_tiles() dropped, so restore_tiles() knows what to
        # rebuild. Empty until this session has actually been evicted once.
        self.released_tileset_names = None

        self.dirty = False

        # Bumped by the manager on every activation, so the tile-eviction pass
        # in phase D-2 can find the least recently used session without
        # needing a clock. Date.now-free by construction.
        self.last_active_serial = 0

        handle.attach(self)

    @property
    def undo_stack(self):
        """This session's undo history, created on first use.

        Per session rather than per file: undo is an editing history, and the
        unit of editing is the area. Two tabs on the same level therefore have
        separate histories, while sharing the level they save.

        Built lazily so that constructing a session - which the headless suites
        do freely - does not require a QApplication.
        """
        if self._undo_stack is None:
            from reggie.core.undo import UndoStack

            self._undo_stack = UndoStack()

            limit = getattr(_globals(), 'UndoLimit', None)
            if limit:
                self._undo_stack.setUndoLimit(limit)

        return self._undo_stack

    @property
    def has_undo_stack(self):
        """Whether a stack has actually been created, without creating one."""
        return self._undo_stack is not None

    @property
    def scene(self):
        """This session's canvas scene, created on first use.

        One scene per session, so an area's items live in their own scene for as
        long as the tab is open. Until D-c.1 a single window-owned scene was
        shared and emptied on every activation - which is why switching areas
        could destroy the outgoing area's items, and why the level overview then
        painted deleted ZoneItems.

        Lazy for the same reason the undo stack is: a session can be constructed
        headlessly, and building a QGraphicsScene needs a QApplication.
        """
        if self._scene is None:
            self._scene = self._build_canvas()[0]

        return self._scene

    @property
    def view(self):
        """This session's canvas view, created on first use with its scene."""
        if self._view is None:
            self._build_canvas()

        return self._view

    @property
    def has_canvas(self):
        """Whether a scene/view pair exists, without building one."""
        return self._scene is not None

    def _build_canvas(self):
        """Create this session's scene and view, wired to the main window.

        Both at once: a view is meaningless without its scene, and the signal
        wiring below is what the window used to do inline for the single shared
        pair. Returns (scene, view).
        """
        from PyQt6 import QtWidgets

        from reggie.io.misc2 import LevelScene, LevelViewWidget

        window = getattr(_globals(), 'mainWindow', None)

        scene = LevelScene(0, 0, 1024 * 24, 512 * 24, window)
        scene.setItemIndexMethod(
            QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)

        view = LevelViewWidget(scene, window)
        view.centerOn(0, 0)

        # Guarded: the headless suites build sessions with no window at all, and
        # a session that cannot be wired is still a usable scene container.
        if window is not None:
            scene.selectionChanged.connect(window.ChangeSelectionHandler)
            view.PositionHover.connect(window.PositionHovered)
            view.XScrollBar.valueChanged.connect(window.XScrollChange)
            view.YScrollBar.valueChanged.connect(window.YScrollChange)
            view.FrameSize.connect(window.HandleWindowSizeChange)

        self._scene = scene
        self._view = view

        return scene, view

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

        The slot *names* are remembered so the session can rebuild itself; only
        the decoded data goes. Without them a released session would not know
        what to reload.
        """
        if self.tileset_files is not None:
            self.released_tileset_names = list(self.tileset_files)

        self.tiles = None
        self.tileset_files = None
        self.object_defs = None

    def restore_tiles(self):
        """Rebuild the tilesets released by :meth:`release_tiles`.

        Called on activation. Returns True if anything was rebuilt. Kept here
        rather than in the manager so that a session is responsible for its own
        contents.
        """
        if self.tiles is not None:
            return False

        # Imported here: tiles.py imports this module, so a module-level import
        # would be circular.
        from reggie.core.tiles import CreateTilesets, LoadTileset

        CreateTilesets()

        for idx, arcname in enumerate(self.released_tileset_names or []):
            if not arcname:
                continue
            # The names recorded are resolved paths; LoadTileset wants the
            # tileset name, which the area still carries.
            name = getattr(self.area, 'tileset%d' % idx, '')
            if name:
                LoadTileset(idx, name)

        return True

    def dispose(self):
        """Tear the session down and detach from the shared level.

        Returns the handle's remaining refcount, so the caller can tell whether
        the level itself should now be released.
        """
        self.release_tiles()

        # Private attributes throughout, never the properties: scene, view and
        # undo_stack are all read-only and all *build* on access, so assigning
        # one would raise and reading one would construct the very object being
        # thrown away.
        if self._view is not None:
            # Take the canvas out of whatever is showing it before destroying
            # it, so the container is never left holding a widget that is being
            # deleted underneath it. Since D-c.2 that is a page in the master
            # tab widget; before it, the window's central widget. Both are
            # handled, because the headless suites build a window whose
            # container may not exist yet.
            window = getattr(_globals(), 'mainWindow', None)
            if window is not None:
                tabs = getattr(window, 'tabs', None)
                if tabs is not None:
                    index = tabs.indexOf(self._view)
                    if index != -1:
                        tabs.removeTab(index)
                elif window.centralWidget() is self._view:
                    window.takeCentralWidget()

            # The view holds the scene; dropping the reference is not enough
            # while Qt still has the widget parented to the window.
            self._view.setParent(None)
            self._view.deleteLater()
            self._view = None

        if self._scene is not None:
            # Items belong to the area, which outlives this session whenever the
            # level stays open. Detach rather than clear() - clear() would
            # delete them, which is D-b.4's lesson: the crash on switching back
            # to an edited area, and the path-node crash after it.
            #
            # Paths need one extra step. A path tracks whether its connecting
            # line is in a scene, and add_to_scene() re-adds the line only when
            # that flag is False - so detaching the line without clearing the
            # flag would bring the nodes back later with nothing joining them.
            for item in self._scene.items():
                path = getattr(item, '_path', None)
                if path is not None and hasattr(path, '_has_line'):
                    path._has_line = False

            for item in self._scene.items():
                self._scene.removeItem(item)

            self._scene.deleteLater()
            self._scene = None

        self._undo_stack = None
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

        # A session evicted by the memory pass rebuilds its tilesets here,
        # before anything can read them. Cheap: the archive bytes are still in
        # the tileset cache, so this is the decode only, not the decompression.
        if session is not None and session.tiles is None \
                and session.released_tileset_names:
            session.restore_tiles()

        # spritelib keeps its own bindings, which sprite rendering reads
        # through. If they are not moved with the session, sprites draw against
        # the previous area's data and its tiles - wrong pixels rather than an
        # exception, which is the hardest kind of bug to trace back to here.
        from reggie.core import spritelib as SLib

        SLib.Area = session.area if session is not None else None
        if session is not None and session.tiles is not None:
            SLib.Tiles = session.tiles

        # The undo/redo menu items follow the active session's stack. Guarded
        # because the manager exists before the window does during boot, and
        # the headless suites run with no window at all.
        window = getattr(_globals(), 'mainWindow', None)
        binder = getattr(window, 'BindUndoStack', None)
        if binder is not None and session is not None:
            binder(session.undo_stack)

        # ...and so does what is on screen. Here rather than only in
        # ReggieWindow.ActivateSession because activation happens through this
        # method from several paths that never reach the window's: opening a
        # file (boot, Open, New) goes open_level -> open() -> activate(), and
        # left the fallback canvas on display while self.scene already resolved
        # to the new session's - the level was loaded and invisible, in a view
        # that was never laid out. Making the swap part of what activation
        # *means* is what stops the next caller forgetting it.
        shower = getattr(window, 'ShowSessionCanvas', None)
        if shower is not None and session is not None:
            shower(session)

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

            # The closed session's canvas has just been destroyed, so the window
            # has no central widget until the survivor's is put up. Assigned
            # directly above rather than through activate(), because the state
            # bindings do not need moving again - only what is on screen does.
            window = getattr(_globals(), 'mainWindow', None)
            shower = getattr(window, 'ShowSessionCanvas', None)
            if shower is not None:
                shower(self._active)

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
