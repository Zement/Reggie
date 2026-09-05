"""The directory listing: a tree over patch -> level -> area -> tileset.

Block D-d, phase D-d.2. Read-only; opening a level from a node is D-d.3.

**The disk is the source of truth, and `levelnames.xml` only names and groups
it** (Zement, 2026-08-31). That inverts what the editor did before: the level
picker (`ChooseLevelNameDialog`) was built entirely from the catalog and could
not see the Stage folder at all, so a level that existed on disk but was absent
from the XML was invisible - which is most of a work-in-progress mod, and all of
one that ships no `levelnames.xml`.

So every `.arc` under the patch's Stage folder appears. The catalog decides
where it sits and what it is called:

    NAMED    - a file the catalog names   -> its category, its display name
    UNNAMED  - a file the catalog does not -> shown by its filename

There is no "listed but missing" state, and that is not an oversight: a patch
reaches this tree by being *installed*, and installed means Stage and Texture
are on disk - a catalog download included. Nothing to dim.

**Lazy where it is expensive, eager where it is not.** Measured 2026-08-31:

    listing the Stage folder      ~0.5 ms   for 213 files
    reading one level's areas     11-44 ms  per file

Reading a level's area count means decompressing the whole `.arc` and parsing
its U8 header, and MidnightWii's 213 levels would cost **9.4 seconds** if the
tree did that up front. So areas are read when a level node is expanded, and
cached per file (invalidated by mtime). The folder listing, being free, happens
when the patch node is built.

Tilesets are free by comparison and need no scan of their own: an area's four
slots are `Area.tileset0..3`, and their display names come from
`globals_.TilesetNames`, which `LoadTilesetNames()` already builds per slot with
the base-chain cascade applied. Levels are *not* inherited between patches -
tilesets are (Zement, 2026-08-31) - which is why a patch node has no ancestors
above it.
"""

import os

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setting


#: Node kinds. Plain strings rather than an enum: they end up in Qt data roles
#: and in test assertions, and a string is readable in both.
PATCH = 'patch'
CATEGORY = 'category'
LEVEL = 'level'
AREA = 'area'
TILESET = 'tileset'

#: Whether a level's name came from the catalog.
NAMED = 'named'
UNNAMED = 'unnamed'

#: The category unnamed levels are collected under, when grouping is on.
UNLISTED_KEY = '\x00unlisted'


def group_unlisted():
    """Whether unnamed levels are grouped under one "Unlisted" category.

    On by default. Off gives one flat, sorted list of every `.arc` with the
    catalog's grouping ignored - which is the mode for a mod with no
    `levelnames.xml`, or a badly incomplete one. Zement, 2026-08-31: the two
    modes together are what make the sorting feature-complete.
    """
    value = setting('TreeGroupUnlisted', True)

    # QSettings round-trips booleans as strings.
    if isinstance(value, str):
        return value.lower() not in ('false', '0', 'none', '')

    return bool(value)


class TreeNode:
    """One row. Deliberately dumb - the model does the work."""

    __slots__ = ('kind', 'label', 'parent', 'children', 'file_path',
                 'file_name', 'provenance', 'area_num', 'slot', 'tileset_name',
                 '_loaded')

    def __init__(self, kind, label, parent=None):
        self.kind = kind
        self.label = label
        self.parent = parent
        self.children = []

        #: LEVEL: the resolved path on disk. AREA/TILESET: their level's path.
        self.file_path = None
        #: LEVEL: the name LoadLevel(name, False, ...) wants - '01-01', with no
        #: extension. NOT the display name, and not the full path.
        self.file_name = None
        self.provenance = None
        self.area_num = None
        self.slot = None
        self.tileset_name = None

        #: Whether the expensive children have been read. Only levels have any.
        self._loaded = kind != LEVEL

        if parent is not None:
            parent.children.append(self)

    @property
    def row(self):
        if self.parent is None:
            return 0
        return self.parent.children.index(self)

    def __repr__(self):
        return '<TreeNode %s %r>' % (self.kind, self.label)


class AreaCache:
    """How many areas each level file has, keyed by path.

    Worth a class of its own because the number is expensive to get (11-44 ms:
    decompress the archive, parse the U8 header) and cheap to keep. Entries are
    invalidated by mtime and size, so a level saved from the editor - or edited
    by anything else - is re-read rather than trusted.
    """

    def __init__(self):
        self._entries = {}      # path -> (mtime, size, [area numbers])

    def clear(self):
        self._entries.clear()

    def invalidate(self, path):
        self._entries.pop(path, None)

    def areas(self, path):
        """{area number: (tileset0..3)} for this file. Empty if unreadable.

        Never raises. A level whose archive is corrupt, whose compression this
        build cannot decode, or which vanished between the listing and the
        expansion, must show as a level with no areas rather than taking the
        sidebar down - and eleven of MidnightWii's files already fail to
        decompress, so this is a measured case, not a defensive one.
        """
        try:
            stat = os.stat(path)
            stamp = (stat.st_mtime, stat.st_size)
        except OSError:
            self._entries.pop(path, None)
            return {}

        cached = self._entries.get(path)
        if cached is not None and cached[0] == stamp[0] and cached[1] == stamp[1]:
            return cached[2]

        areas = _read_areas(path)
        self._entries[path] = (stamp[0], stamp[1], areas)
        return areas


def _read_areas(path):
    """What a level file holds: {area number: (tileset0..3)}.

    Deliberately does NOT construct a `Level_NSMBW`: that parses every block of
    every area and builds the sprite objects, which is the whole level load.
    Everything the tree needs is much shallower - the area *count* is one
    `courseN.bin` per area in the U8 file table, and the four tileset names are
    block 1 of each course file, four fixed 32-byte strings.
    """
    from libs import lh, lz77
    from reggie.core import archive

    try:
        with open(path, 'rb') as f:
            data = f.read()

        if not data:
            return {}

        if (data[0] & 0xF0) == 0x40:
            data = lh.UncompressLH(data)
        elif not data.startswith(b"U\xAA8-"):
            data = lz77.UncompressLZ77(data)

        arc = archive.U8.load(data)
    except Exception:
        # Every failure is the same answer: a level whose areas cannot be read.
        # Broad because the decoders raise IndexError, the archive raises
        # ValueError, and a truncated file raises whatever struct feels like -
        # and eleven of MidnightWii's files really do fail to decompress, so
        # this is a measured case rather than a defensive one.
        return {}

    areas = {}
    for name, value in arc.files:
        if value is None:
            continue

        name = name.replace('\\', '/').split('/')[-1]

        # 'courseN.bin' is exactly 11 characters; the layer files are
        # 'courseN_bgdatLM.bin' and are not areas.
        if not name.startswith('course') or not name.endswith('.bin'):
            continue
        if len(name) != 11:
            continue

        try:
            number = int(name[6])
        except ValueError:
            continue

        if 0 < number < 5 and number not in areas:
            areas[number] = _read_tileset_names(value)

    return areas


def _read_tileset_names(course):
    """The four tileset names in a course file's block 1.

    The block table is the same one `AbstractParsedArea.LoadBlocks` walks: an
    8-byte (offset, size) pair per block, block 1 first. Read directly rather
    than through that class because constructing an Area to learn four strings
    would parse every block and build every sprite in it.
    """
    import struct

    try:
        offset, size = struct.unpack_from('>II', course, 0)
        if size < 128:
            return ('', '', '', '')

        raw = struct.unpack_from('>32s32s32s32s', course, offset)
    except Exception:
        return ('', '', '', '')

    return tuple(part.strip(b'\0').decode('latin-1', 'replace') for part in raw)


def catalog_names():
    """The catalog as {file name: (display name, category path)}.

    Flattens the nested tuple tree `LoadLevelNames` builds, because the tree
    needs the lookup in the other direction: it starts from a file on disk and
    asks what the catalog calls it.

    The category path is a tuple, so a level nested two categories deep keeps
    both - the retail list is 'World 1' -> '01-01', but a patch may go deeper.
    """
    from reggie.io.misc import LoadLevelNames

    try:
        LoadLevelNames()
    except Exception:
        return {}

    names = {}

    def walk(items, path):
        for entry in items or ():
            try:
                label, value = entry
            except (TypeError, ValueError):
                continue

            if isinstance(value, str):
                # A level: ('World 1-1', '01-01')
                names.setdefault(value, (label, path))
            else:
                walk(value, path + (label,))

    walk(globals_.LevelNames, ())
    return names


def stage_files():
    """Every level file in the loaded patch's Stage folder.

    Returns {file name without extension: full path}. Free compared with
    reading any of them - measured at ~0.5 ms for 213 files - so this runs
    whenever the patch node is built rather than being deferred.
    """
    try:
        stage = globals_.gamedef.GetStageGamePath()
    except Exception:
        return {}

    if not stage or not os.path.isdir(stage):
        return {}

    found = {}
    try:
        entries = os.listdir(stage)
    except OSError:
        return {}

    for entry in entries:
        for ext in globals_.FileExtentions:
            if not entry.endswith(ext):
                continue

            name = entry[:-len(ext)]

            # First extension wins, in FileExtentions order - the same
            # precedence LoadLevel applies when it tries each in turn, so the
            # tree cannot offer a file the loader would not pick.
            found.setdefault(name, os.path.join(stage, entry))
            break

    return found


def tileset_names_for(slot):
    """{file name: display name} for one tileset slot, base chain included.

    Reads `globals_.TilesetNames`, which `LoadTilesetNames` already builds as
    four per-slot lists with `CascadeTilesetNames_Category` applied - so the
    inheritance work is done and this only has to flatten it. Zement measured
    that cascade at ~0.3% of a level load, which is why the tree can afford to
    do this eagerly when an area is expanded.
    """
    names = {}

    try:
        entries = globals_.TilesetNames[slot][0]
    except (TypeError, IndexError, KeyError):
        return names

    def walk(items):
        for entry in items or ():
            try:
                first, second = entry
            except (TypeError, ValueError):
                continue

            if isinstance(second, str):
                # A tileset: (file name, display name)
                names.setdefault(first, second)
            else:
                walk(second)

    walk(entries)
    return names


class LevelTreeModel(QtCore.QAbstractItemModel):
    """patch -> level -> area -> tileset, over what is actually on disk.

    A custom model rather than a `QTreeWidget` because of the three things the
    Block D evaluation picked it for and a widget cannot give: lazy expansion
    (`canFetchMore`/`fetchMore`), bold-for-loaded through `Qt.FontRole`, and
    per-node icons through `Qt.DecorationRole`.
    """

    def __init__(self, window=None, parent=None):
        super().__init__(parent)

        self.win = window
        self._cache = AreaCache()
        self._root = TreeNode(PATCH, '')

        self.refresh()

    # -- building --------------------------------------------------------

    def refresh(self):
        """Rebuild from the loaded patch. Keeps the area cache.

        The cache survives on purpose: it is keyed by path and validated by
        mtime, so a patch switch and back does not pay the 11-44 ms per level
        again for files that have not changed.
        """
        self.beginResetModel()
        try:
            self._root = self._buildRoot()
        finally:
            self.endResetModel()

    def _buildRoot(self):
        root = TreeNode(PATCH, '')

        try:
            patch_label = globals_.gamedef.name
        except Exception:
            patch_label = ''

        patch = TreeNode(PATCH, patch_label or '', root)

        files = stage_files()
        catalog = catalog_names()
        grouped = group_unlisted()

        # {category path: node}, built on demand so a category with no files on
        # disk never appears. That is the inversion in practice: the catalog
        # cannot conjure a row, it can only name one.
        categories = {}

        def category_for(path):
            if not path:
                return patch

            node = categories.get(path)
            if node is not None:
                return node

            parent = category_for(path[:-1])
            node = TreeNode(CATEGORY, path[-1], parent)
            categories[path] = node
            return node

        unlisted = None

        for name in sorted(files, key=lambda n: n.lower()):
            entry = catalog.get(name)

            if entry is not None:
                label, category_path = entry
                provenance = NAMED
                parent = category_for(category_path) if grouped else patch
            else:
                label = name
                provenance = UNNAMED

                if grouped:
                    if unlisted is None:
                        unlisted = TreeNode(
                            CATEGORY,
                            globals_.trans.string('MenuItems', 147),
                            patch)
                    parent = unlisted
                else:
                    parent = patch

            level = TreeNode(LEVEL, label, parent)
            level.file_path = files[name]
            level.file_name = name
            level.provenance = provenance

        if not grouped:
            # Flat mode: one sorted list, the catalog's grouping ignored. The
            # files were sorted by *file name* above, which is the right key
            # here only when nothing was renamed by the catalog.
            patch.children.sort(key=lambda n: (n.label or '').lower())

        return root

    def _fetchAreas(self, node):
        """Read one level's areas, and give each its four tileset slots.

        The tilesets are built here rather than lazily on the area node: they
        come out of the same read, and the cascaded name list they are labelled
        from is already in memory. Deferring them would save nothing and add a
        second lazy path to get wrong.
        """
        node._loaded = True

        areas = self._cache.areas(node.file_path)
        if not areas:
            return

        # One lookup per slot for the whole level, not per area.
        slot_names = [tileset_names_for(slot) for slot in range(4)]

        for number in sorted(areas):
            area = TreeNode(AREA, globals_.trans.string(
                'AreaCombobox', 0, '[num]', number), node)
            area.file_path = node.file_path
            area.file_name = node.file_name
            area.area_num = number

            for slot, file_name in enumerate(areas[number]):
                if file_name:
                    label = globals_.trans.string(
                        'MenuItems', 148, '[num]', slot,
                        '[name]', slot_names[slot].get(file_name, file_name))
                else:
                    # Empty slots are shown and marked, because "this area uses
                    # three tilesets" is information (plan §3.1b).
                    label = globals_.trans.string('MenuItems', 149,
                                                  '[num]', slot)

                tileset = TreeNode(TILESET, label, area)
                tileset.file_path = node.file_path
                tileset.area_num = number
                tileset.slot = slot
                tileset.tileset_name = file_name or None

    # -- Qt model interface ----------------------------------------------

    def nodeFor(self, index):
        """The TreeNode behind an index, or the invisible root."""
        if index.isValid():
            node = index.internalPointer()
            if node is not None:
                return node
        return self._root

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()

        node = self.nodeFor(parent)
        if row >= len(node.children):
            return QtCore.QModelIndex()

        return self.createIndex(row, column, node.children[row])

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()

        node = index.internalPointer()
        if node is None or node.parent is None or node.parent is self._root:
            return QtCore.QModelIndex()

        return self.createIndex(node.parent.row, 0, node.parent)

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.column() > 0:
            return 0
        return len(self.nodeFor(parent).children)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 1

    # -- lazy expansion --------------------------------------------------

    def canFetchMore(self, parent):
        node = self.nodeFor(parent)
        return node.kind == LEVEL and not node._loaded

    def fetchMore(self, parent):
        node = self.nodeFor(parent)
        if node.kind != LEVEL or node._loaded:
            return

        before = len(node.children)
        self._fetchAreas(node)
        added = len(node.children) - before

        if added <= 0:
            return

        # The rows were appended by _fetchAreas before begin/endInsertRows could
        # wrap them, so they are handed to Qt here: detach them, announce the
        # insert, put them back. Simpler than threading the model's signals
        # through the builder, and the window is one statement wide.
        rows = node.children[before:]
        del node.children[before:]

        self.beginInsertRows(parent, before, before + added - 1)
        node.children.extend(rows)
        self.endInsertRows()

    def hasChildren(self, parent=QtCore.QModelIndex()):
        node = self.nodeFor(parent)

        # A level claims children before they are read, so the expander arrow
        # is there to click. Without it there is nothing to trigger fetchMore
        # and every level looks empty - which is the trap in a lazy model.
        if node.kind == LEVEL and not node._loaded:
            return True

        return bool(node.children)

    # -- presentation ----------------------------------------------------

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        node = index.internalPointer()
        if node is None:
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return node.label

        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return node.file_path or node.label

        if role == QtCore.Qt.ItemDataRole.UserRole:
            return node

        if role == QtCore.Qt.ItemDataRole.FontRole:
            if self._isLoaded(node):
                font = QtGui.QFont()
                font.setBold(True)
                return font
            return None

        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            return self._icon(node)

        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags

        flags = (QtCore.Qt.ItemFlag.ItemIsEnabled
                 | QtCore.Qt.ItemFlag.ItemIsSelectable)

        node = index.internalPointer()
        if node is not None and node.kind in (LEVEL, AREA) and self._readOnly():
            # A collab client may not open levels at will - the host decides -
            # so the tree looks unavailable rather than only refusing on click
            # (plan §3.1a). Enabled is cleared, which is what greys the row.
            flags &= ~QtCore.Qt.ItemFlag.ItemIsEnabled

        return flags

    def _readOnly(self):
        """Whether this editor may not open levels itself.

        True only for a *client* in a collaboration session. Guarded, because
        the tree must render with no collab layer at all - which is how every
        headless test and every ordinary launch runs it.

        **The attribute is `_collab`, not `collab`** (fixed 2026-09-01). It was
        `collab` here, which no window has ever had, so this returned False for
        everyone and a client's tree was never greyed out - Zement, testing as a
        client: "the color of the levels and areas in the tree does not look
        different to me." The `getattr(..., None)` guard below turned a typo
        into a permanent silent False rather than an AttributeError, which is
        the standing hazard of a broad guard: it hides the mistake it was
        written to tolerate. Hence the assertion in test_level_tree that the
        attribute exists at all.
        """
        window = self.win or getattr(globals_, 'mainWindow', None)
        controller = getattr(window, '_collab', None)
        if controller is None:
            return False

        try:
            return bool(controller.is_active) and not bool(controller.is_host)
        except Exception:
            return False

    def _isLoaded(self, node):
        """Whether this node has an open editor session behind it.

        Bold-for-loaded, per the brief. A level is bold when *any* of its areas
        is open, an area when that area is.
        """
        manager = globals_.get_session_manager()
        if manager is None or node.file_path is None:
            return False

        try:
            sessions = manager.sessions_for(node.file_path)
        except Exception:
            return False

        if not sessions:
            return False

        if node.kind == LEVEL:
            return True

        if node.kind == AREA:
            return any(s.area_num == node.area_num for s in sessions)

        return False

    def _icon(self, node):
        from reggie.ui.ui import GetIcon

        try:
            if node.kind == PATCH:
                return GetIcon('game')
            if node.kind == CATEGORY:
                return GetIcon('folderpath')
            if node.kind == LEVEL:
                return GetIcon('open')
            if node.kind == AREA:
                return GetIcon('area')
            if node.kind == TILESET:
                return GetIcon('objects')
        except Exception:
            # No theme loaded - the model still has to build.
            return None

        return None

    # -- keeping in step -------------------------------------------------

    def refreshLoadedMarks(self):
        """Repaint after a session opens or closes, without rebuilding.

        Only the font changes, so the whole tree is announced as changed rather
        than each affected row hunted down - one repaint of a few hundred rows
        is cheaper than walking them to find out which few to announce.
        """
        top = self.index(0, 0, QtCore.QModelIndex())
        if not top.isValid():
            return

        self.dataChanged.emit(
            top,
            self.index(self.rowCount() - 1, 0, QtCore.QModelIndex()),
            [QtCore.Qt.ItemDataRole.FontRole])

    def invalidateFile(self, path):
        """Forget a level's cached area list - it was saved, or replaced."""
        self._cache.invalidate(path)


class LevelTreeWidget(QtWidgets.QWidget):
    """The Directory Listing section in sidebar slice 2 (D-d.2).

    The tree, plus the one control that belongs beside it: the toggle deciding
    whether unnamed levels are grouped under "Unlisted" or the whole thing is
    one flat sorted list.

    Read-only in this phase. Activating a node opens a session in D-d.3, which
    is why `activated` is exposed but nothing here connects it.
    """

    def __init__(self, window=None, parent=None):
        super().__init__(parent)

        self.win = window

        self.model = LevelTreeModel(window, self)

        self.view = QtWidgets.QTreeView(self)
        self.view.setModel(self.model)
        self.view.setHeaderHidden(True)
        self.view.setIndentation(14)
        self.view.setUniformRowHeights(True)
        self.view.setExpandsOnDoubleClick(False)
        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        self.groupBox = QtWidgets.QCheckBox(self)
        self.groupBox.setChecked(group_unlisted())
        self.groupBox.toggled.connect(self._handleGroupToggled)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.groupBox, 0)

        self.retranslate()
        self.expandPatch()

    def retranslate(self):
        self.groupBox.setText(globals_.trans.string('MenuItems', 150))
        self.groupBox.setToolTip(globals_.trans.string('MenuItems', 151))

    @property
    def activated(self):
        """The view's activation signal - D-d.3 connects it."""
        return self.view.activated

    def expandPatch(self):
        """Open the patch node, so the levels are visible without a click.

        Only the patch: expanding a level is what costs 11-44 ms, and doing it
        for every level is the 9.4 seconds this design exists to avoid.
        """
        root = self.model.index(0, 0, QtCore.QModelIndex())
        if root.isValid():
            self.view.expand(root)

    # -- remembering what was open ---------------------------------------
    #
    # A context section is destroyed and re-created every time the user
    # switches away and back, so a tree that kept its state only in the widget
    # would come back fully collapsed and scrolled to the top - which is what
    # it did (Zement, 2026-09-01: "When I change from Directory Listing to Game
    # Patches and back, the tree is back to its default view, with all nodes
    # contracted").
    #
    # Keeping the widget alive instead was the other option, and was rejected:
    # it would make the directory listing the one section that is special, and
    # the same problem would return for the next section with state. Saving and
    # restoring is a few lines here and nothing anywhere else.
    #
    # Keyed by *label path* rather than by index. A QModelIndex is invalid the
    # moment the model resets, and a row number means a different node once a
    # patch switch changes the list - the labels are what the user was actually
    # looking at.

    def captureState(self):
        """What is expanded, what is selected, and where the view is scrolled."""
        expanded = []

        def walk(parent):
            for row in range(self.model.rowCount(parent)):
                index = self.model.index(row, 0, parent)
                if not self.view.isExpanded(index):
                    continue
                expanded.append(self._pathFor(index))
                walk(index)

        walk(QtCore.QModelIndex())

        current = self.view.currentIndex()
        return {
            'expanded': expanded,
            'current': self._pathFor(current) if current.isValid() else None,
            'scroll': self.view.verticalScrollBar().value(),
        }

    def applyState(self, state):
        """Put back what ``captureState`` recorded. Silent when it cannot.

        Anything that has since disappeared - a level deleted, or a patch
        switch that replaced the whole list - is simply skipped, so a stale
        state degrades to the default view rather than failing.
        """
        if not state:
            return

        for path in state.get('expanded') or ():
            index = self._indexFor(path)
            if index is not None and index.isValid():
                # Expanding is what triggers `fetchMore`, so a level restored
                # this way pays its 11-44 ms exactly as it did the first time -
                # and only for the levels that were actually open.
                self.view.expand(index)

        current = state.get('current')
        if current:
            index = self._indexFor(current)
            if index is not None and index.isValid():
                self.view.setCurrentIndex(index)

        # After the expansions, or the scrollbar's range is still the collapsed
        # tree's and the value is clamped to it.
        scroll = state.get('scroll')
        if scroll:
            self.view.verticalScrollBar().setValue(int(scroll))

    def _pathFor(self, index):
        """The chain of labels from the root down to ``index``."""
        path = []
        while index.isValid():
            node = index.internalPointer()
            path.append(node.label if node is not None else '')
            index = index.parent()
        return tuple(reversed(path))

    def _indexFor(self, path):
        """The index at ``path``, or None if it is no longer there.

        Walks down one node at a time. A **level** has to be fetched before its
        areas can be looked at: a level's children are read lazily, so until
        then `rowCount` is 0 and the walk cannot see into it.

        That is why area nodes alone were not restored (Zement, 2026-09-01:
        "*Area* nodes are not remembered whether they are collapsed or
        expanded... those are the only exception"). Expanding the *view* is not
        enough either - Qt posts `fetchMore` to the event loop, so the rows are
        still not there when the next step of this walk runs. The model is
        asked directly instead.

        The laziness is not lost: only levels actually on the path are fetched,
        which is exactly the set the user had open. A path that names nothing
        stops at the first missing label, having fetched only its ancestors.
        """
        index = QtCore.QModelIndex()

        for label in path:
            if self.model.canFetchMore(index):
                self.model.fetchMore(index)

            found = None
            for row in range(self.model.rowCount(index)):
                candidate = self.model.index(row, 0, index)
                node = candidate.internalPointer()
                if node is not None and node.label == label:
                    found = candidate
                    break

            if found is None:
                return None
            index = found

        return index

    def refresh(self):
        """Rebuild for the loaded patch, and re-open the patch node."""
        state = self.captureState()
        self.model.refresh()
        self.expandPatch()
        self.applyState(state)

    def refreshLoadedMarks(self):
        self.model.refreshLoadedMarks()

    def _handleGroupToggled(self, checked):
        from reggie.core.dirty import setSetting

        setSetting('TreeGroupUnlisted', bool(checked))
        self.refresh()

