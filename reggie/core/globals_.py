Area = None
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
Dirty = False
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
Level = None
LevelNames = None
LocationsFrozen = False
LocationsShown = True
MusicInfo = None
NumberFont = None
NumSprites = 0
ObjDesc = None
ObjectDefinitions = None # 4 tilesets
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
ReggieVersionShort = 'v0.95.0-2'  # Fallback if git is not available (update manually with each release)
ResetDataWhenHiding = False
RestoredFromAutoSave = False
SettingsActions = None
SpriteCategories = None
SpriteImagesShown = True
SpriteListData = None
SpritesFrozen = False
SpritesShown = True
Sprites = None
Tiles = None # 0x200 tiles per tileset, plus 64 for each type of override
TilesetAnimTimer = None
TilesetFilesLoaded = [None, None, None, None]
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
