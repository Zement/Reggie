# Area and Level are NOT declared here. They are proxied to the active editor
# session at the bottom of this module - see the block starting at
# "Session-backed globals". Declaring them would shadow the proxy, because
# module __getattr__ is only consulted when normal lookup fails.
AutoSaveData = b''
AutoSaveDirty = False
AutoSavePath = ''
BgANames = None
BgBNames = None
BoundsDrawn = False
CollisionsShown = False
CommentsFrozen = False
CommentsShown = True
CurrentLayer = 1
CurrentObject = -1
CurrentPaintType = 0
CurrentSprite = -1
# Dirty is NOT declared here - it is proxied to the active editor session, the
# same as Area and Level. See "Session-backed globals" at the bottom.
DirtyOverride = 0
DrawEntIndicators = False
EditActions = None
EnablePadding = False
EntranceTypeNames = None
EntranceImages = None
EntrancesFrozen = False
ErrMsg = ''
FileActions = None
FileExtentions = ('.arc', '.arc.LH', '.arc.LZ')
GridType = None
HideResetSpritedata = False
HelpActions = None
Initializing = None
InsertPathNode = False
UndoLimit = 500
Layer0Shown = True
Layer1Shown = True
Layer2Shown = True
LevelNames = None
LocationsFrozen = False
LocationsShown = True
MusicInfo = None
NumberFont = None
NumSprites = 0
ObjDesc = None
ObjectsFrozen = False
OverriddenTilesets = {
    "Pa0": set(),
    "no-Pa0": set(),
    "Flowers": set(),
    "Forest Flowers": set(),
    "Lines": set(),
    "Minigame Lines": set(),
    "Full Lines": set(),
    "Conveyors": set()
}
OverrideSnapping = False
Overrides = None # 320 tiles, this is put into Tiles usually
Overrides_safe = None
OVERRIDE_UNKNOWN = 0
PaddingLength = 0
PathsFrozen = False
PathsShown = True
PlaceObjectsAtFullSize = True
RealViewEnabled = False
# Reginald continues Reggie! Next; the credit line keeps the original authors
# deliberately, and the About box shows it verbatim.
# 64 char max (32 if non-ascii) - see the note at the ReggieInfo assignment in
# ui/window.py. Kept within budget even though nothing reads it today.
ReginaldID = 'Reginald by Treeki, Tempus and RoadrunnerWMC'
# Reginald restarts at 0.9x and reaches 1.0 when the last improvement block
# lands. This is compared against the ReginaldVersion key in settings.ini; see
# the guard in app.py, which resets rather than migrates a foreign file.
ReginaldVersionFloat = 0.95
# Version format: v[Major].[Minor].[Patch]-[MinorPatch]-[CommitID]
# MinorPatch increments with each commit for proper sorting
# Version is determined dynamically from git tags at runtime
#
# NOTE: this constant keeps its Reggie-era name on purpose. .github/workflows/
# build.yml greps for the literal string "ReggieVersionShort" in all four
# platform jobs and throws if it is absent, so renaming it here breaks every
# build. Rename the constant and the workflow greps together, or not at all.
ReggieVersionShort = 'v0.95.0-3'  # Fallback if git is not available (update manually with each release)
ResetDataWhenHiding = False
RestoredFromAutoSave = False
SettingsActions = None
SpriteCategories = None
SpriteImagesShown = True
SpriteListData = None
SpritesFrozen = False
SpritesShown = True
Sprites = None
# Tiles, TilesetFilesLoaded and ObjectDefinitions are NOT declared here -
# they are proxied to the active editor session, like Area and Level. See
# "Session-backed globals" at the bottom of this module.
TilesetAnimTimer = None
TilesetInfo = None
TilesetNames = None
TilesetsAnimating = False

# Withholds the "tileset not found" modal while a patch switch is in flight.
#
# During LoadGameDef the level still open belongs to the *outgoing* game, and
# its tilesets are looked up under the incoming game's paths. Switching to
# retail from a patch therefore warned about every tileset unique to that patch
# - retail has no base gamedef to fall back to, while a patch inherits retail
# and so happens to find them. The level is replaced moments later, so the
# warning is about a state the user never reaches.
#
# Set only around that switch, and always restored in a finally.
SuppressMissingTilesetWarnings = False
ViewActions = None
ZoneThemeValues = None
FirstStageFilename = None
UseFullFilepath = False
UseRoundedRectangles = True
DarkMode = False

FileKeybinds = None
EditKeybinds = None
ViewKeybinds = None
SettingsKeybinds = None
HelpKeybinds = None
HotbarKeybinds = None

app = None
firstLoad = True
gamedef = None
mainWindow = None
scalingManager = None
settings = None
theme = None
trans = None


########################################################################
# Session-backed globals (Block D)
########################################################################
#
# `Area` and `Level` used to be plain module attributes: one open area, one
# open level, editor-wide. Tabs need more than one, so they are now resolved
# through the active editor session instead.
#
# The shape of the problem is what makes this approach worth it: `Area` is read
# in ~338 places across 25 files, but written in only seven. Proxying the reads
# lets all 338 keep working untouched while the seven writers move onto the
# session manager.
#
# Two mechanics matter here, and both are easy to get wrong:
#
# 1. Module-level `__getattr__` (PEP 562) is consulted ONLY when normal
#    attribute lookup fails. So `Area` and `Level` must not be declared in this
#    module at all - see the note at the top where they used to be.
#
# 2. A single `globals_.Area = x` anywhere would create a real module attribute
#    and permanently shadow the proxy. Nothing would raise; area switching
#    would just quietly stop working. Rather than rely on nobody doing that,
#    the module class below refuses the assignment outright.

_session_manager = None

#: Names resolved from the active session rather than from this module.
#
# Area and Level are the level state; Tiles, TilesetFilesLoaded and
# ObjectDefinitions are the four tileset slots, which two open areas will
# usually want to fill differently.
#
# Only CreateTilesets() ever rebinds the three tileset names - everything else
# writes into them in place (Tiles[i] = ..., ObjectDefinitions[idx] = ...), and
# those writes land on whichever list the session owns, with no call-site
# changes needed.
_PROXIED_GLOBALS = ('Area', 'Level', 'Dirty',
                    'Tiles', 'TilesetFilesLoaded', 'ObjectDefinitions')

#: Proxied names that may still be assigned, routed to the active session.
#
# `Dirty` is the exception to the read-only rule, and deliberately so. The other
# proxied names are *state the session owns*, where an assignment could only
# mean "replace the session's contents" and is therefore a mistake. Dirty is a
# fact ABOUT the active session that six existing sites legitimately set - a
# save clears it, a load resets it, an edit sets it - so refusing the assignment
# would mean rewriting all six for no gain.
#
# Read-only is still the default for everything else: a writable proxy costs the
# guarantee that a stray assignment cannot silently disable area switching, and
# that is worth keeping wherever it can be kept.
_WRITABLE_PROXIED = ('Dirty',)

#: Test-only overrides, consulted before the session manager.
#
# The headless suites inject stub Area/Level objects to drive code paths that
# would otherwise need a whole loaded level. That is a legitimate need, but a
# plain assignment cannot serve it - it would shadow the proxy permanently for
# the rest of the process. `override_proxied` gives them an explicit, reversible
# way in, and keeps the plain assignment refused so production code cannot
# disable the proxy by accident.
_proxy_overrides = {}


def override_proxied(name, value):
    """TEST ONLY. Force `Area` or `Level` to a fixed value.

    Returns the previous override (or a sentinel meaning "none"), for restoring
    in a finally block. Pass `clear_override` semantics via `clear_proxied`.
    """
    if name not in _PROXIED_GLOBALS:
        raise ValueError('%r is not a session-backed global' % name)
    previous = _proxy_overrides.get(name, _NO_OVERRIDE)
    _proxy_overrides[name] = value
    return previous


def clear_proxied(name=None):
    """TEST ONLY. Drop one override, or all of them, restoring the proxy."""
    if name is None:
        _proxy_overrides.clear()
    else:
        _proxy_overrides.pop(name, None)


class _NoOverride:
    """Sentinel: distinguishes "overridden to None" from "not overridden"."""
    def __repr__(self):
        return '<no override>'


_NO_OVERRIDE = _NoOverride()


def set_session_manager(manager):
    """Install the SessionManager the proxied globals read from.

    Called once during boot. Passing None restores the pre-session behaviour,
    where `Area` and `Level` are simply None - which is what shutdown wants.
    """
    global _session_manager
    _session_manager = manager


def get_session_manager():
    return _session_manager


def _resolve_proxied(name):
    """Resolve `Area` / `Level` from the active session."""
    override = _proxy_overrides.get(name, _NO_OVERRIDE)
    if override is not _NO_OVERRIDE:
        return override

    # The tileset slots have a home even with no session: CreateTilesets() runs
    # from Area.__init__, which boot and the headless suites reach before any
    # session exists.
    _TILESET_ATTRS = {'Tiles': 'tiles',
                      'TilesetFilesLoaded': 'tileset_files',
                      'ObjectDefinitions': 'object_defs'}

    manager = _session_manager
    session = manager.active if manager is not None else None

    if session is None:
        if name in _TILESET_ATTRS:
            from reggie.core import session as _session_module
            return _session_module.fallback_tilesets(_TILESET_ATTRS[name])
        # False, not None: `Dirty` is asked as a boolean by every reader, and
        # the honest answer with nothing open is "no unsaved work".
        return False if name == 'Dirty' else None

    if name == 'Area':
        return session.area

    if name == 'Dirty':
        # Per area, which is the point. One shared flag meant an edit in any tab
        # marked them all, so the tab labels could not tell them apart and
        # CheckDirty prompted about areas the user had not touched.
        return session.dirty

    if name in _TILESET_ATTRS:
        value = getattr(session, _TILESET_ATTRS[name])
        # A session that gave up its tiles to the eviction pass has None here;
        # fall back rather than hand out None to indexing code.
        if value is None:
            from reggie.core import session as _session_module
            return _session_module.fallback_tilesets(_TILESET_ATTRS[name])
        return value

    # `Level` lives on the shared handle, not the session, because two tabs
    # showing different areas of one file must see the same Level object.
    return session.level


def _assign_proxied(name, value):
    """Write a writable proxied global through to the active session.

    Only `Dirty` today. A test override wins, so a suite that pinned the value
    is not fought by production code assigning it.

    With no session, the write is *remembered as an override* rather than
    dropped. That matters for the headless suites, which set `globals_.Dirty`
    to drive code that reads it - CheckDirty, the collab proposal dialog -
    without a level open. Dropping the write there would make the flag silently
    unsettable and those tests would assert against a value nothing could
    change. In the running editor there is always a session (Zement's rule that
    one area stays loaded), so this path is the test harness's, not the
    editor's.
    """
    if name in _proxy_overrides:
        _proxy_overrides[name] = value
        return

    manager = _session_manager
    session = manager.active if manager is not None else None

    if session is None:
        _proxy_overrides[name] = value
        return

    # A session exists, so it is the answer - drop any value stashed while none
    # did. Without this, one session-less write would shadow every real session
    # for the rest of the process, since overrides are consulted first.
    _proxy_overrides.pop(name, None)

    if name == 'Dirty':
        session.dirty = bool(value)


def _install_proxy():
    """Replace this module's class so the proxied names are read-only.

    Done as a function so the machinery is not left lying around as module
    attributes; the call below is the only thing that runs at import.
    """
    import sys
    import types

    class _SessionBackedGlobals(types.ModuleType):
        __slots__ = ()

        def __getattr__(self, name):
            # Reached only when normal lookup fails, i.e. exactly for the names
            # deliberately not declared in this module.
            if name in _PROXIED_GLOBALS:
                return _resolve_proxied(name)
            raise AttributeError(
                "module %r has no attribute %r" % (self.__name__, name)
            )

        def __setattr__(self, name, value):
            if name in _WRITABLE_PROXIED:
                _assign_proxied(name, value)
                return
            if name in _PROXIED_GLOBALS:
                raise AttributeError(
                    "globals_.%s is owned by the editor session and cannot be "
                    "assigned. Assigning it would shadow the session proxy and "
                    "silently break switching between open areas.\n"
                    "  Production code: open, close or activate a session via "
                    "globals_.get_session_manager().\n"
                    "  Tests: use globals_.override_proxied(%r, value) and "
                    "globals_.clear_proxied(%r)." % (name, name, name)
                )
            super().__setattr__(name, value)

    sys.modules[__name__].__class__ = _SessionBackedGlobals


_install_proxy()
