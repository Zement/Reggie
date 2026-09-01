import os
import re
import sys
import importlib
import functools
from xml.etree import ElementTree as etree

from PyQt6 import QtWidgets, QtCore, QtGui

from reggie.io.misc import LoadSpriteData, LoadSpriteListData, LoadSpriteCategories, LoadBgANames, LoadBgBNames, LoadObjDescriptions, LoadTilesetNames, LoadTilesetInfo, LoadEntranceNames, LoadMusicInfo, LoadZoneThemes
from reggie.core.dirty import setting, setSetting
# Safe at module level: patchmodel imports only globals_ and dirty, and this
# module already imports from reggie.ui above.
from reggie.ui.patchmodel import patch_model

from reggie.core import globals_
from reggie.core import spritelib as SLib
import reggie.sprites as sprites

# GameDefViewer and GameDefMenu were removed in Block D-d, phase D-d.1b.
#
# They were the `File -> Change Game` menu: a patch list plus an info panel at
# the top. That menu is gone - a patch is reached from the sidebar's Game
# Patches page or from the Patch Manager - and D-d deliberately removes entry
# points rather than adding a third one.
#
# The info panel was the one part worth keeping, since the Patch Manager had no
# equivalent. It lives on as `PatchInfoPanel` in
# reggie/patches/patch_manager_dialog.py, with one change: it describes the
# *selected* patch rather than the loaded one, which is what a manager wants.
#
# `add_reggie_patch` went with the menu; the Patch Manager's own
# "Add Patch Folder" button (`_add_patch_folder`) does the same job.


def _ensurePatchModuleAliases():
    """
    Makes the bare module names a patch's sprites.py imports resolvable.

    A game patch's sprites.py is user content we cannot rewrite, and it does
    `import spritelib as SLib` / `import sprites_common as common`. Those
    modules live at reggie.core.<name>, so the names only resolve because
    something has put them in sys.modules under their bare form.

    From a source checkout the shims at the repository root did that, since the
    checkout directory is on sys.path. A PyInstaller build has no such entry -
    module_path() only sets the working directory - so the import failed there
    and every patch with a custom sprites.py fell back to the base game.

    Aliased rather than re-imported: patch code and Reggie's own code must share
    the *same* module object, or SLib.ImageCache in a patch would be a different
    dictionary from the one the editor reads.

    Best-effort per name. A missing optional module should cost that one import,
    not the whole patch load.
    """
    for name in ('spritelib', 'sprites_common'):
        if name in sys.modules:
            continue

        try:
            sys.modules[name] = importlib.import_module('reggie.core.' + name)
        except ImportError as exc:
            print('[GAMEDEF] could not alias %r for patch sprites: %s'
                  % (name, exc))


class ReggieGameDefinition:
    """
    A class that defines a NSMBW hack: songs, tilesets, sprites, etc.
    """

    # Gamedef File - has 2 values: name (str) and patch (bool)
    class GameDefinitionFile:
        """
        A class that defines a filepath, and some options
        """

        def __init__(self, path, patch):
            """
            Initializes the GameDefinitionFile
            """
            self.path = path
            self.patch = patch

    def __init__(self, name=None, custom_path=None):
        """
        Initializes the ReggieGameDefinition
        custom_path: Optional custom path to the patch folder (from settings)
        """
        self.InitAsEmpty()

        # Try to init it from name if possible
        NoneTypes = (None, 'None', 0, '', True, False)
        if name in NoneTypes:
            return

        # If the named patch is no longer present, fall back to the retail
        # gamedef and forget the missing LastGameDef instead of crashing.
        result = self.InitFromName(name, custom_path)
        if not result:
            self.InitAsEmpty()
            setSetting('LastGameDef', None)

    def InitAsEmpty(self):
        """
        Sets all properties to their default values
        """
        gdf = self.GameDefinitionFile

        self.custom = False
        self.base = None  # gamedef to use as a base
        self.gamepath = None
        self.name = globals_.trans.string('Gamedefs', 13)  # 'New Super Mario Bros. Wii'
        self.description = globals_.trans.string('Gamedefs', 14)  # 'A new Mario adventure!<br>' and the date
        self.version = '2'

        self.sprites = sprites
        self.plugins = {}  # Dictionary of enabled plugins

        self.files = {
            'bga': gdf(os.path.join('reggiedata', 'bga.txt'), False),
            'bgb': gdf(os.path.join('reggiedata', 'bgb.txt'), False),
            'entrancetypes': gdf(os.path.join('reggiedata', 'entrancetypes.txt'), False),
            'levelnames': gdf(os.path.join('reggiedata', 'levelnames.xml'), False),
            'music': gdf(os.path.join('reggiedata', 'music.txt'), False),
            'spritecategories': gdf(os.path.join('reggiedata', 'spritecategories.xml'), False),
            'spritedata': gdf(os.path.join('reggiedata', 'spritedata.xml'), False),
            'spritelistdata': gdf(os.path.join('reggiedata', 'spritelistdata.txt'), False),
            'tilesetinfo': gdf(os.path.join('reggiedata', 'tilesetinfo.xml'), False),
            'tilesets': gdf(os.path.join('reggiedata', 'tilesets.xml'), False),
            'ts1_descriptions': gdf(os.path.join('reggiedata', 'ts1_descriptions.txt'), False),
            'zonethemes': gdf(os.path.join('reggiedata', 'zonethemes.txt'), False),
        }
        self.folders = {
            'bga': gdf(None, False),
            'bgb': gdf(None, False),
            'sprites': gdf(None, False),
            'external': gdf(None, False),
        }

    def InitFromName(self, name, custom_path=None):
        """
        Attempts to open/load a Game Definition from a name string. Just loads
        the name and description to avoid referring to other game definitions.
        custom_path: Optional custom path to the patch folder (from settings)
        """
        self.custom = True
        name = str(name)
        self.gamepath = name
        self.custom_patch_path = custom_path  # Store custom path if provided

        # Determine the path to main.xml
        if custom_path:
            path = os.path.join(custom_path, "main.xml")
        else:
            path = os.path.join("reggiedata", "patches", name, "main.xml")
            
            # Check if there's a custom path in settings
            custom_setting_path = setting('PatchPath_' + name)
            if custom_setting_path and os.path.isfile(os.path.join(custom_setting_path, "main.xml")):
                path = os.path.join(custom_setting_path, "main.xml")
                self.custom_patch_path = custom_setting_path

        try:
            tree = etree.parse(path)
        except FileNotFoundError:
            return False
        root = tree.getroot()

        # Add the attributes of root: name, description and version.
        # base is added in __init2__, only when needed.
        self.name = root.get('name')

        if self.name is None:
            raise ValueError("Game definition XML %r has no 'name' attribute on the root node." % path)

        default = globals_.trans.string('Gamedefs', 15)
        self.description = root.get('description', default).replace('[', '<').replace(']', '>')
        self.version = root.get('version')
        return True

    def __init2__(self):
        """
        Finishes up initialisation of custom gamedefs. This avoids infinite
        recursion with gamedefs referring to other gamedefs.
        """
        if not self.custom:
            return

        # Use custom path if available, otherwise use default patches directory
        if hasattr(self, 'custom_patch_path') and self.custom_patch_path:
            addpath = self.custom_patch_path
            path = os.path.join(addpath, "main.xml")
        else:
            # Check settings for custom path
            custom_setting_path = setting('PatchPath_' + self.gamepath)
            if custom_setting_path and os.path.isfile(os.path.join(custom_setting_path, "main.xml")):
                addpath = custom_setting_path
                self.custom_patch_path = custom_setting_path
                path = os.path.join(addpath, "main.xml")
            else:
                addpath = os.path.join("reggiedata", "patches", self.gamepath)
                path = os.path.join(addpath, "main.xml")

        try:
            tree = etree.parse(path)
        except FileNotFoundError:
            return
        root = tree.getroot()

        self.base = None
        if 'base' in root.attrib:
            self.base = FindGameDef(root.attrib['base'], self.gamepath)
        else:
            self.base = ReggieGameDefinition()

        # Parse the nodes
        # addpath is already set above
        for node in root:
            n = node.tag.lower()
            if n not in ('file', 'folder'):
                continue

            patch = node.get('patch', 'true').lower() == 'true'

            game = node.get('game')
            if game is None:
                path = os.path.join(addpath, node.get('path'))
            elif game == globals_.trans.string('Gamedefs', 13):  # 'New Super Mario Bros. Wii'
                path = os.path.join('reggiedata', node.get('path'))
            else:
                def_ = FindGameDef(game, self.gamepath)
                path = os.path.join('reggiedata', 'patches', def_.gamepath, node.get('path'))

            dict_type = self.files if n == 'file' else self.folders  # self.files or self.folders
            dict_type[node.get('name')] = self.GameDefinitionFile(path, patch)

        # Get rid of the XML stuff
        del tree, root

        # Load plugins.xml if it exists
        self.LoadPlugins(addpath)

        # Load sprites.py if provided
        if 'sprites' in self.files:
            print(f"[DEBUG] Loading sprites.py from: {self.files['sprites'].path}")

            # Converted before it is read, on every patch load rather than once
            # behind a prompt (NSMBW-Community f2de79d). A patch fixed by an
            # older version of the converter still benefits when a substitution
            # is added later, and the question the old dialog asked - "should I
            # upgrade this?" - was not one the user could answer usefully: the
            # only alternative to converting is a patch that does not load.
            #
            # Safe to repeat because ConvertSpritesModule is idempotent and the
            # file is only rewritten when something actually changes.
            FixSpritesModule(self.files['sprites'].path)

            with open(self.files['sprites'].path, 'r', encoding='utf-8') as f:
                filedata = f.read()

            # The bare names a patch's sprites.py imports, registered before it
            # runs. These modules live at reggie.core.<name>, and the shims at
            # the repository root only resolve because the source checkout puts
            # its own directory on sys.path - a frozen build does not, so every
            # patch with a custom sprites.py failed there with
            # "No module named 'spritelib'" while working perfectly from source
            # (Zement, NSMBWerPlus, v4.9.1-30).
            #
            # Registered here rather than at boot because this is the one place
            # that is on *both* paths: the initial load and every later patch
            # change. sys.modules entries are process-wide and idempotent, so
            # repeating this on each gamedef load costs nothing.
            _ensurePatchModuleAliases()

            # https://stackoverflow.com/a/53080237 with modifications
            spec = importlib.util.spec_from_loader(self.name + "->sprites", loader=None)
            new_module = importlib.util.module_from_spec(spec)

            exec(filedata, new_module.__dict__)
            
            # Assign the loaded module to self.sprites
            self.sprites = new_module

    def LoadPlugins(self, addpath):
        """
        Loads plugins from plugins.xml if it exists, creates default if missing
        """
        plugins_path = os.path.join(addpath, "plugins.xml")
        
        # Start with base plugins if we have a base
        if self.base is not None and hasattr(self.base, 'plugins'):
            self.plugins = self.base.plugins.copy()
        else:
            self.plugins = {}
        
        # Load patch-specific plugins if plugins.xml exists
        if os.path.isfile(plugins_path):
            try:
                tree = etree.parse(plugins_path)
                root = tree.getroot()
                
                for plugin in root.findall('plugin'):
                    name = plugin.get('name')
                    enabled = plugin.get('enabled', 'false').lower() == 'true'
                    
                    if enabled:
                        # Check if plugin has parameters
                        params = {}
                        for param in plugin.findall('param'):
                            param_name = param.get('name')
                            param_value = param.get('value')
                            params[param_name] = param_value
                        
                        self.plugins[name] = params if params else True
                    elif name in self.plugins:
                        # Plugin explicitly disabled, remove from inherited plugins
                        del self.plugins[name]
                
                del tree, root
            except Exception as e:
                # If plugins.xml is malformed, create default
                print(f"Warning: Failed to load plugins.xml: {e}")
                self.CreateDefaultPluginsXML(plugins_path)
        else:
            # Create default plugins.xml if it doesn't exist
            self.CreateDefaultPluginsXML(plugins_path)
    
    def CreateDefaultPluginsXML(self, plugins_path):
        """
        Creates a default plugins.xml file with all plugins disabled
        """
        try:
            # Only create for custom patches (not base game)
            if not self.custom:
                return
            
            # All available plugins come from the single registry so this XML and
            # the Patch Manager UI can never drift apart. See
            # reggie/plugins/patch_plugins.py.
            from reggie.plugins.patch_plugins import REGISTRY as available_plugins

            # Create XML structure
            root = etree.Element('plugins')
            root.text = '\n  '
            root.tail = '\n'

            for i, plugin_def in enumerate(available_plugins):
                # Add comment
                comment = etree.Comment(f' {plugin_def.display_name} ')
                comment.tail = '\n  '
                root.append(comment)

                # Add plugin element
                plugin = etree.SubElement(root, 'plugin')
                plugin.set('name', plugin_def.id)
                plugin.set('enabled', 'false')
                plugin.tail = '\n  ' if i < len(available_plugins) - 1 else '\n'

                # Add parameters if any
                if plugin_def.params:
                    plugin.text = '\n    '
                    for j, param in enumerate(plugin_def.params):
                        param_elem = etree.SubElement(plugin, 'param')
                        param_elem.set('name', param.name)
                        param_elem.set('value', param.default)
                        param_elem.tail = '\n    ' if j < len(plugin_def.params) - 1 else '\n  '
            
            # Write to file with proper formatting
            tree = etree.ElementTree(root)
            # Indent the XML manually since standard ElementTree doesn't support pretty_print
            self._indent_xml(root)
            tree.write(plugins_path, encoding='utf-8', xml_declaration=True)
            print(f"Created default plugins.xml at {plugins_path}")
        except Exception as e:
            print(f"Warning: Failed to create default plugins.xml: {e}")
    
    def _indent_xml(self, elem, level=0):
        """
        Helper to indent XML for pretty printing (since standard ElementTree doesn't support it)
        """
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent

    def bgFile(self, name, layer):
        """
        Returns the folder to a bg image. Layer must be 'a' or 'b'
        """
        # Name will be of the format '0000.png'
        fallback = os.path.join('reggiedata', 'bg' + layer, name)
        filename = os.path.join('bg' + layer, name)

        # See if it was defined specifically
        if filename in self.files:
            path = self.files[filename].path
            if os.path.isfile(path): return path

        # See if it's in one of self.folders
        if self.folders['bg%s' % layer].path is not None:
            trypath = os.path.join(self.folders['bg%s' % layer].path, name)
            if os.path.isfile(trypath): return trypath

        # If there's a base, return self.base.bgFile
        if self.base is not None:
            return self.base.bgFile(name, layer)

        # If not, return fallback
        return fallback

    def externalFile(self, name):
        """
        Returns the filename to the external xml.
        """
        # Name is of the format 'something.xml'
        filename = os.path.join('external', name)
        fallback = os.path.join('reggiedata', filename)

        # check if it's in self.files
        if filename in self.files:
            path = self.files[filename].path
            if os.path.isfile(path):
                return path

        # check if it's in self.folders
        if self.folders['external'].path is not None:
            path = os.path.join(self.folders['external'].path, name)
            if os.path.isfile(path):
                return path

        # No luck so far. If we have a base, use that
        if self.base is not None:
            return self.base.externalFile(name)

        # Use the fallback
        return fallback

    # A collaboration session's game data, as {patch name: (stage, texture)}.
    #
    # Class-level rather than per-instance, and deliberately so: loading a patch
    # builds a *new* ReggieGameDefinition, so an override stored on an instance
    # would be lost the moment the session switched patch - which is exactly
    # when it is needed. Keyed on the patch name for the same reason the
    # QSettings keys are.
    #
    # This is how a session points at transferred levels without touching the
    # user's own preferences (Block C - B3). The user's StageGamePath_<patch>
    # keeps whatever it always had; the session simply answers first, and stops
    # answering when it ends. Nothing here is ever written to disk.
    _sessionGamePaths = {}

    # The key a retail session's game data is stored under (Block C - B3, R6).
    #
    # Retail needs a key of its own because it has no patch id, and it must not
    # be `self.name`: a retail gamedef's name is trans.string('Gamedefs', 13),
    # a *translated* display string, so keying on it would work in English and
    # silently fail in any other language. It is also the exact confusion
    # _patchId() exists to avoid - a retail session claiming to need a patch
    # named after the base game.
    #
    # A sentinel that cannot collide with a patch name: a patch id comes from
    # the `name` attribute of a main.xml root node, and no real one looks like
    # this.
    RETAIL_SESSION_KEY = '\x00retail'

    @classmethod
    def SetSessionGamePaths(cls, patch_name, stage, texture):
        """
        Points a patch at a session's copy of its game data, for as long as the
        session lasts. Both paths may be empty to record only one of them.

        An empty `patch_name` means the retail game, which is stored under
        RETAIL_SESSION_KEY rather than under '' - so that a caller passing an
        empty string by mistake cannot silently claim the retail slot.
        """
        key = str(patch_name) or cls.RETAIL_SESSION_KEY
        cls._sessionGamePaths[key] = (str(stage or ''), str(texture or ''))

    @classmethod
    def ClearSessionGamePaths(cls):
        """
        Forgets every session override. Called when a session ends, so the
        editor goes back to the user's own folders.
        """
        cls._sessionGamePaths.clear()

    def _sessionPath(self, index):
        """
        The session's stage (0) or texture (1) path for this gamedef, or ''.

        Retail is included (R6). It used to be excluded on the reasoning that
        the base game is not a patch and has no per-patch key to shadow - true
        as far as it goes, but it meant a retail session could not receive the
        host's levels at all, so every retail join fell back to a snapshot and
        the host froze waiting for an acknowledgement that could not come.

        The override is still session-scoped and never written to disk, which is
        what makes it safe here: the user's own StageGamePath keeps whatever it
        always had, and a retail session simply answers first until it ends.
        That matters more for retail than for a patch, because editing the base
        game's folders in place is discouraged - Zement's position, 2026-08-11 -
        and this guarantees a session never does.
        """
        key = self.name if self.custom else self.RETAIL_SESSION_KEY

        paths = ReggieGameDefinition._sessionGamePaths.get(key)
        if not paths:
            return ''

        path = paths[index]
        # Verified rather than trusted: a session copy can be deleted between
        # joining and loading, and silently returning a path to nothing would
        # look like the missing-tileset bug this block exists to remove.
        return path if path and os.path.isdir(path) else ''

    def GetTextureGamePath(self):
        """
        Returns the texture game path
        """
        session = self._sessionPath(1)
        if session:
            return session

        if not self.custom:
            return setting('TextureGamePath')

        name = 'TextureGamePath_' + self.name
        setname = setting(name)

        # Use the default if there are no settings for this yet
        if setname is None:
            return setting('TextureGamePath')
        else:
            return str(setname)

    def SetTextureGamePath(self, path):
        """
        Sets the texture game path
        """
        if not self.custom:
            setSetting('TextureGamePath', path)
        else:
            name = 'TextureGamePath_' + self.name
            setSetting(name, path)

    def GetStageGamePath(self):
        """
        Returns the stage game path
        """
        session = self._sessionPath(0)
        if session:
            return session

        if not self.custom:
            return setting('StageGamePath')

        name = 'StageGamePath_' + self.name
        setname = setting(name)

        # Use the default if there are no settings for this yet
        if setname is None:
            return setting('StageGamePath')
        else:
            return str(setname)

    def SetStageGamePath(self, path):
        """
        Sets the stage game path
        """
        if not self.custom:
            setSetting('StageGamePath', path)
        else:
            name = 'StageGamePath_' + self.name
            setSetting(name, path)

    def GetTexturePaths(self):
        """
        Returns the texture game paths of this globals_.gamedef and its bases

        The session's own Texture folder is appended last, so it wins: tiles.py
        searches these in reverse. Without it a session's tilesets were not on
        the search path at all (Block C - B3, R6) - which worked for a
        transferred patch only because the install also writes
        TextureGamePath_<patch>, and did not work for retail at all, since
        retail has no such key to write.
        """
        session = self._sessionPath(1)

        if not self.custom:
            # Same rule as below: an unset path would truncate the search in
            # tiles.py rather than simply contributing nothing, and a retail
            # session appends after it.
            paths = []
            base_path = setting('TextureGamePath')
            if base_path:
                paths.append(base_path)
            if session:
                paths.append(session)
            return paths

        stg = setting('TextureGamePath_' + self.name)

        if self.base is not None:
            paths = self.base.GetTexturePaths()
        else:
            # Same rule again: seeding the list with an unset retail path puts
            # a None at the front, and anything appended after it is then
            # unreachable.
            retail_path = setting('TextureGamePath')
            paths = [retail_path] if retail_path else []

        # Only if it is actually set.
        #
        # tiles.py searches this list in reverse and stops dead at the first
        # None ("if path is None: break"), so an unset entry does not merely
        # contribute nothing - it truncates the search. That was harmless while
        # the unset entry could only be last; appending a session path after it
        # (R6) put it in the middle, and every patch built on another patch
        # broke: Another Mario Wii declares base="Newer Super Mario Bros. Wii",
        # the client had no TextureGamePath_Newer... key, and the resulting
        # None hid retail's folder behind it. Every tileset the patch inherits
        # rather than ships - Pa1_nohara, Pa2_doukutu, Pa3_rail - was reported
        # missing, while Pa0_jyotyu, which the patch does ship, loaded fine
        # (Zement, 2026-08-11).
        #
        # Dropping it is right rather than keeping a placeholder: the list is a
        # search path, and a directory nobody configured is not a place to
        # look. The break in tiles.py is left alone - it is load-bearing for
        # callers that pass an explicit None - but nothing here feeds it one
        # any more.
        if stg:
            paths.append(stg)

        # After the patch's own path, so a session copy shadows it rather than
        # being shadowed by it.
        if session:
            paths.append(session)

        return paths

    def GetLastLevel(self):
        """
        Returns the last loaded level
        """
        if not self.custom:
            return setting('LastLevel')

        name = 'LastLevel_' + self.name
        stg = setting(name)

        # Use the default if there are no settings for this yet
        if stg is None:
            return setting('LastLevel')

        return stg

    def SetLastLevel(self, path):
        """
        Sets the last loaded level
        """
        if path in {None, 'None', 'none', True, 'True', 'true', False, 'False', 'false', 0, 1, ''}:
            return

        if not self.custom:
            setSetting('LastLevel', path)
        else:
            name = 'LastLevel_' + self.name
            setSetting(name, path)

    def recursiveFiles(self, name, is_folder=False):
        """
        Checks each base of this globals_.gamedef and returns a list of successive file paths
        """
        if is_folder:
            entry = self.folders[name]
        else:
            entry = self.files[name]

        if self.base is None or not entry.patch:
            # We don't have a base to fall back to, so we need to provide the
            # file ourselves.
            was_patch = False

            if entry.path is None:
                current_list = []
                names = []
            else:
                current_list = [entry.path]
                names = [self.name]

        else:
            # We do have a base to fall back to - we know that the last step
            # came from a patch, so we set 'was_patch' to True and we set 'isPatch'
            # in the recursive call to False - it doesn't matter whether the
            # previous recursive step was a patch or not.
            was_patch = True
            current_list, _, names = self.base.recursiveFiles(name, is_folder)

            if entry.path is not None:
                # We have something to add to the base
                current_list.append(entry.path)
                names.append(self.name)

        return current_list, was_patch, names

    def file(self, name):
        """
        Returns a file by recursively checking successive globals_.gamedef bases
        """
        if name not in self.files: return

        if self.files[name].path is not None:
            return self.files[name].path
        else:
            if self.base is None: return
            return self.base.file(name)  # it can recursively check its base, too

    def getImageClasses(self):
        """
        Gets all image classes
        """
        if not self.custom:
            return self.sprites.ImageClasses

        if self.base is not None:
            images = dict(self.base.getImageClasses())
        else:
            images = {}

        if hasattr(self.sprites, 'ImageClasses'):
            images.update(self.sprites.ImageClasses)
        return images


def cleanupOrphanedPatchPaths():
    """
    Remove PatchPath_ and other game path settings from settings.ini that point to non-existent patches.
    This prevents errors when patches are deleted manually outside Reggie.
    Also handles URL-encoded patch names (e.g., NSMBWer%2B -> NSMBWer+) and @Invalid() entries.
    """
    from reggie.core.dirty import setSetting
    from urllib.parse import unquote
    
    patches_dir = os.path.join('reggiedata', 'patches')
    orphaned_keys = []
    
    # Prefixes to check for patch-related settings
    path_prefixes = ['PatchPath_', 'StageGamePath_', 'TextureGamePath_', 'LastLevel_']
    
    # Check all patch-related settings
    all_keys = globals_.settings.allKeys()
    for key in all_keys:
        # Handle both grouped (GamePaths/PatchPath_X) and flat (PatchPath_X) keys
        key_name = key.split('/')[-1] if '/' in key else key
        
        # Check if this is a patch-related setting
        for prefix in path_prefixes:
            if key_name.startswith(prefix):
                # Extract patch name (may be URL-encoded)
                patch_name_encoded = key_name[len(prefix):]
                patch_name = unquote(patch_name_encoded)  # Decode URL encoding
                patch_path = setting(key_name)  # Use setting() which handles groups
                
                # Check for @Invalid() entries or empty settings
                if not patch_path or str(patch_path) == '@Invalid()':
                    orphaned_keys.append((key_name, patch_path))
                elif patch_path:
                    # Normalize the path to handle different slash conventions
                    patch_path = os.path.normpath(str(patch_path))
                    
                    # For LastLevel_, just check if the file exists
                    if prefix == 'LastLevel_':
                        if not os.path.isfile(patch_path):
                            orphaned_keys.append((key_name, patch_path))
                    # For path settings, check if the directory exists
                    elif not os.path.exists(patch_path):
                        # Path doesn't exist - mark for removal
                        orphaned_keys.append((key_name, patch_path))
                    elif prefix == 'PatchPath_':
                        # For PatchPath_, also check if main.xml exists
                        if not os.path.isfile(os.path.join(patch_path, 'main.xml')):
                            # Also check if it exists in the patches directory (redundant setting)
                            patches_dir_path = os.path.join(patches_dir, patch_name)
                            if not os.path.isfile(os.path.join(patches_dir_path, 'main.xml')):
                                # Orphaned path - mark for removal
                                orphaned_keys.append((key_name, patch_path))
                
                break  # Found a matching prefix, no need to check others
    
    # Remove orphaned settings
    for key_name, path in orphaned_keys:
        setSetting(key_name, None)
    
    return len(orphaned_keys)


def getAvailableGameDefs():
    game_defs = []
    patches_dir = os.path.join('reggiedata', 'patches')

    # Add patches from the patches directory
    if os.path.exists(patches_dir):
        folders = os.listdir(patches_dir)
        for folder in folders:
            if not os.path.isfile(os.path.join(patches_dir, folder, 'main.xml')): 
                continue

            def_ = ReggieGameDefinition(folder)
            if def_.custom:
                game_defs.append((def_.name, folder))
    
    # Add patches from custom paths stored in settings
    all_keys = globals_.settings.allKeys()
    for key in all_keys:
        # Handle both grouped (GamePaths/PatchPath_X) and flat (PatchPath_X) keys
        key_name = key.split('/')[-1] if '/' in key else key
        
        if key_name.startswith('PatchPath_'):
            patch_name = key_name[10:]  # Remove 'PatchPath_' prefix
            patch_path = setting(key_name)  # Use setting() which handles groups
            
            if patch_path:
                # Normalize the path to handle different slash conventions
                patch_path = os.path.normpath(patch_path)
                
                if os.path.isfile(os.path.join(patch_path, 'main.xml')):
                    # Check if not already added from patches directory
                    if not any(folder == patch_name for _, folder in game_defs):
                        try:
                            def_ = ReggieGameDefinition(patch_name, custom_path=patch_path)
                            if def_.custom:
                                game_defs.append((def_.name, patch_name))
                        except Exception as e:
                            # Skip invalid patches but log the error for debugging
                            print(f"Failed to load patch {patch_name} from {patch_path}: {e}")
                            pass

    # Alphabetize them, and then add the default
    game_defs.sort()

    return [None] + [folder for _, folder in game_defs]


def loadNewGameDef(def_):
    """
    Loads ReggieGameDefinition def_, and displays a progress dialog
    """
    dlg = QtWidgets.QProgressDialog()
    dlg.setAutoClose(True)
    btn = QtWidgets.QPushButton('Cancel')
    btn.setEnabled(False)
    dlg.setCancelButton(btn)
    dlg.show()
    dlg.setValue(0)

    res = LoadGameDef(def_, dlg)

    dlg.setValue(100)
    return res

# Game Definitions
def LoadGameDef(name=None, dlg=None):
    """
    Loads a game definition
    """
    if dlg: dlg.setMaximum(7)

    # Put the whole thing into a try-except clause
    # to catch whatever errors may happen
    try:
        sprite_images_enabled = False
        if globals_.mainWindow is not None and hasattr(globals_.mainWindow, 'sprPicker'):
            sprite_images_enabled = globals_.mainWindow.sprPicker.show_sprite_images
            if sprite_images_enabled:
                globals_.mainWindow.sprPicker.show_sprite_images = False

        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 1))  # Loading game patch...

        # Clear any existing warning icons when changing patches
        if globals_.mainWindow is not None:
            for icon in list(globals_.mainWindow.warningIcons):
                globals_.mainWindow.RemoveWarningIcon(icon)

        globals_.gamedef = ReggieGameDefinition(name)
        globals_.gamedef.__init2__()

        if globals_.gamedef.custom and (setting('StageGamePath_' + globals_.gamedef.name) is None):
            # First-time usage of this globals_.gamedef. Have the
            # user pick a stage folder so we can load stages
            # and tilesets from there.
            #
            # **Every abort below has to leave the editor able to run.** The
            # three `return False`s here skip the rest of this function, which
            # is where the data files the UI treats as always-present get
            # loaded - `ObjDesc` above all, which starts as None and is filled
            # nowhere else. The palette then does `i in globals_.ObjDesc` and
            # dies with "argument of type 'NoneType' is not iterable" before
            # the window is even up, so the only way out is deleting
            # settings.ini (Zement, 2026-09-01, on a ReggieCopy whose patch had
            # no Stage path yet).
            #
            # Loaded before the prompt rather than in each abort: there is
            # nothing patch-specific about it - `ts1_descriptions` is retail
            # data - and doing it once here cannot be forgotten by a fourth
            # abort added later.
            LoadObjDescriptions()

            pressed_button = QtWidgets.QMessageBox.information(None,
                globals_.trans.string('Gamedefs', 2),
                globals_.trans.string('Gamedefs', 3, '[game]', globals_.gamedef.name),
                QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel
            )

            if pressed_button == QtWidgets.QMessageBox.StandardButton.Cancel:
                return False

            if globals_.mainWindow is None:
                # This check avoids an error because globals_.mainWindow is None
                # when first loading the editor. Returning False here avoids a
                # loop where the user cannot open the editor because the program
                # closes after returning the error.
                return False

            result = globals_.mainWindow.HandleChangeGamePath(True)

            if result:
                msg_ids = (6, 7)
            else:
                msg_ids = (4, 5)

            QtWidgets.QMessageBox.information(None,
                globals_.trans.string('Gamedefs', msg_ids[0]),
                globals_.trans.string('Gamedefs', msg_ids[1], '[game]', globals_.gamedef.name),
                QtWidgets.QMessageBox.StandardButton.Ok
            )

            if not result:
                # If the user refused to select a game path, abort the patch
                # switching process.
                return False

        if dlg: dlg.setValue(1)

        # Load spritedata.xml and spritecategories.xml
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 8))  # Loading sprite data...

        LoadSpriteData()
        LoadSpriteListData(True)
        LoadSpriteCategories(True)

        # Reload all of the spritedata ID types in the area
        # Fixes bugs related to these being outdated when switching game patches
        if globals_.Area is not None:
            globals_.Area.InitialiseIdTypes()

        if globals_.mainWindow is not None:
            globals_.mainWindow.spriteViewPicker.clear()

            for cat in globals_.SpriteCategories:
                globals_.mainWindow.spriteViewPicker.addItem(cat[0])

            globals_.mainWindow.sprPicker.LoadItems()  # Reloads the sprite picker list items
            globals_.mainWindow.spriteViewPicker.setCurrentIndex(0)  # Sets the sprite picker to category 0 (enemies)
            globals_.mainWindow.spriteDataEditor.setSprite(globals_.mainWindow.spriteDataEditor.spritetype,
                                                  True)  # Reloads the sprite data editor fields

        if dlg: dlg.setValue(2)

        # Load BgA/BgB names
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 9))  # Loading background names...

        LoadBgANames(True)
        LoadBgBNames(True)
        LoadZoneThemes(True)
        LoadMusicInfo(True)  # reloads the music names

        if dlg: dlg.setValue(3)

        # Reload tilesets
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 10))  # Reloading tilesets...

        LoadObjDescriptions(True)  # reloads ts1_descriptions

        # The level still open belongs to the game being unloaded, so its
        # tilesets are about to be looked up under the *incoming* game's paths.
        # Whatever is missing there is missing from a level that is on its way
        # out - R5 replaces it immediately after - so the modal would report a
        # state the user never sees. Restored in a finally: a suppression left
        # on would hide a genuine missing tileset for the rest of the run.
        previous_suppression = globals_.SuppressMissingTilesetWarnings
        globals_.SuppressMissingTilesetWarnings = True
        try:
            if globals_.mainWindow is not None:
                globals_.mainWindow.ReloadTilesets(True)
        finally:
            globals_.SuppressMissingTilesetWarnings = previous_suppression

        LoadTilesetNames(True)  # reloads tileset names
        LoadTilesetInfo(True)  # reloads tileset info

        if dlg: dlg.setValue(4)

        # Load sprites.py
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 11))  # Loading sprite image data...

        # Always load the sprites folders so the correct sprite images can be
        # loaded when Reggie is started. This avoids loading all sprite images
        # again and also simplifies the sprite image code.
        SLib.SpritesFolders = globals_.gamedef.recursiveFiles('sprites', is_folder=True)[0]

        if globals_.Area is not None:
            SLib.ImageCache.clear()
            SLib.SpriteImagesLoaded.clear()
            sprites.LoadBasics()

            spriteClasses = globals_.gamedef.getImageClasses()

            for s in globals_.Area.sprites:
                if s.type in SLib.SpriteImagesLoaded: continue
                if s.type not in spriteClasses: continue

                spriteClasses[s.type].loadImages()

                SLib.SpriteImagesLoaded.add(s.type)

            for s in globals_.Area.sprites:
                if s.type in spriteClasses:
                    s.setImageObj(spriteClasses[s.type])
                else:
                    s.setImageObj(SLib.SpriteImage)
            
            # Recalculate unknown sprite IDs based on current patch's sprite definitions
            unknown_sprite_ids = set()
            for sprite in globals_.Area.sprites:
                if sprite.type >= globals_.NumSprites or globals_.Sprites[sprite.type] is None:
                    unknown_sprite_ids.add(sprite.type)
            
            # Update the Area's unknown_sprite_ids
            globals_.Area.unknown_sprite_ids = unknown_sprite_ids
            
            # Check for unknown sprite IDs and show warning icon in status bar
            if unknown_sprite_ids:
                sprite_ids = sorted(unknown_sprite_ids)
                if globals_.mainWindow is not None:
                    if len(sprite_ids) == 1:
                        msg = globals_.trans.string('Err_UnknownSprite', 0, '[id]', str(sprite_ids[0]))
                    else:
                        msg = globals_.trans.string('Err_UnknownSprite', 1, '[ids]', ', '.join(map(str, sprite_ids)))
                    globals_.mainWindow.AddWarningIcon(msg)

        if dlg: dlg.setValue(5)

        # Reload the sprite-picker text
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 12))  # Applying sprite image data...
        if globals_.Area is not None:
            for spr in globals_.Area.sprites:
                spr.UpdateListItem()  # Reloads the sprite-picker text
        if dlg: dlg.setValue(6)

        # Load entrance names
        if dlg: dlg.setLabelText(globals_.trans.string('Gamedefs', 16))  # Loading entrance names...
        LoadEntranceNames(True)
        
        # Reload the entrance editor to update entrance types and images
        if globals_.mainWindow is not None and hasattr(globals_.mainWindow, 'entranceEditor'):
            globals_.mainWindow.entranceEditor.reloadEntranceTypes()
        
        # Update all entrance items in the current area to use new images
        if globals_.Area is not None:
            for ent in globals_.Area.entrances:
                ent.update()  # Redraws the entrance with new images
                ent.UpdateListItem()  # Updates the list item text
        
        if dlg: dlg.setValue(7)

    except Exception as e:
        if dlg: dlg.setValue(7)
        
        if sprite_images_enabled and globals_.mainWindow is not None and hasattr(globals_.mainWindow, 'sprPicker'):
            globals_.mainWindow.sprPicker.show_sprite_images = True
        
        # If we were trying to load a specific patch and it failed, show a message
        # and fall back to the base game
        if name is not None:
            QtWidgets.QMessageBox.warning(
                None,
                'Patch Not Found',
                f'The patch "{name}" could not be loaded.\n\n'
                f'Error: {str(e)}\n\n'
                f'Reggie will load the base game (New Super Mario Bros. Wii) instead.',
                QtWidgets.QMessageBox.StandardButton.Ok
            )
            # Try to load the base game instead
            return LoadGameDef(None, dlg)
        else:
            # We failed to load even the base game, this is a critical error
            raise


    if dlg: setSetting('LastGameDef', name)

    if sprite_images_enabled and globals_.mainWindow is not None and hasattr(globals_.mainWindow, 'sprPicker'):
        globals_.mainWindow.sprPicker.show_sprite_images = True

    # Show the patch that is actually loaded. The combo box reads LastGameDef,
    # and until D-d.1b only the patch combo box refreshed it - so every other route
    # into a patch change (a collaboration client following its host, a level
    # load, a failed load falling back to retail) left the box naming the
    # previous patch. Doing it here rather than at each call site means the
    # control cannot disagree with the loaded gamedef whoever changed it.
    RefreshPatchSelector()

    # Tell a running collaboration session that the patch changed, so joined
    # clients can re-check whether they still have what the host is using. Only
    # on the success path: announcing a patch we failed to load would be a lie.
    NotifyCollabGameDefChanged()

    return True


def RefreshPatchSelector():
    """
    Re-syncs the controls that name the loaded patch.

    Since D-d.1b that is one control - the sidebar's Game Patches page - plus
    the shared model behind it. The toolbar combo box and the Change Game menu
    are both gone; a patch is switched from the sidebar or the Patch Manager.
    The function stays because it is the seam every patch-switching route
    already calls, and because the Patch Manager adds and removes patches
    without going through a switch at all.
    """
    window = getattr(globals_, 'mainWindow', None)
    if window is None:
        return

    # Re-read the shared list once, here, rather than letting each view refresh
    # it: two refreshes would hit the disk twice for one switch, and a view that
    # refreshed the model *after* another had read it could show a different
    # set - the disagreement f7 exists to end.
    patch_model().refresh()

    # The sidebar's Game Patches page (D-d.1). Guarded: the page is only there
    # once the sidebar is built, and a patch switch must not fail because a
    # piece of chrome could not be updated.
    patch_list = getattr(window, 'patchListWidget', None)
    if patch_list is not None:
        try:
            patch_list.refresh()
        except Exception:
            pass

    # The directory listing lists a *patch's* levels, so a patch switch means a
    # different Stage folder entirely - a full rebuild, not a repaint (D-d.2).
    refresh_tree = getattr(window, 'RefreshDirectoryListing', None)
    if refresh_tree is not None:
        try:
            refresh_tree(rebuild=True)
        except Exception:
            pass


def NotifyCollabGameDefChanged():
    """
    Pushes the new patch to collaboration clients, if a session is hosting.

    Isolated and fully guarded because it runs at the end of patch switching,
    which must succeed whether or not collaboration is available: a networking
    problem here would otherwise look like a broken patch.
    """
    window = getattr(globals_, 'mainWindow', None)

    # _collab is created lazily by HandleCollaborate, so None here is the normal
    # case: the user has never opened the collaboration dialog.
    controller = getattr(window, '_collab', None)
    if controller is None:
        return

    try:
        controller.notifyRoomInfoChanged()
    except Exception:
        pass

@functools.lru_cache(maxsize=None)
def FindGameDef(name, skip=None):
    """
    Helper function to find a game def with a specific name.
    Skip will be skipped
    """
    patches_path = os.path.join('reggiedata', 'patches')

    for folder in os.listdir(patches_path):
        if folder == skip:
            continue

        def_ = ReggieGameDefinition(folder)

        if def_.name != name:  # Not the one we're looking for, so stop loading.
            continue

        def_.__init2__()
        return def_


# PyQt5 -> PyQt6 substitutions for a patch's sprites.py, as regexes rather
# than plain strings.
#
# Every pattern is written so that an *already converted* file matches nothing,
# which is what makes running this on every patch load safe. Plain string
# replacement is not: 'Qt.Align' is a substring of the 'Qt.AlignmentFlag.Align'
# it produces, so each pass would add another 'AlignmentFlag.' and the file
# would rot a little further every time a patch was selected. The same trap
# applies to the transformation and aspect-ratio names, where the original
# unqualified patterns also matched inside their own output.
#
# Adapted from NSMBW-Community's f2de79d (Mandy, 2026-07-27), which moved the
# converter onto every patch load and qualified two of the patterns with 'Qt.'.
# The negative lookaheads here are the remaining half of that: 'Qt.Align' still
# matched its own output in that version.
_SPRITES_PYQT6_RULES = (
    (r'QPainter\.(?!RenderHint\.)Antialiasing',
     'QPainter.RenderHint.Antialiasing'),
    (r'Qt\.(?!TransformationMode\.)SmoothTransformation',
     'Qt.TransformationMode.SmoothTransformation'),
    (r'Qt\.(?!AspectRatioMode\.)IgnoreAspectRatio',
     'Qt.AspectRatioMode.IgnoreAspectRatio'),

    # The parenthesis skips instances that are already QPointF.
    (r'QPoint\(', 'QPointF('),

    (r'Qt\.(?!GlobalColor\.)transparent', 'Qt.GlobalColor.transparent'),
    (r'Qt\.(?!AlignmentFlag\.)Align', 'Qt.AlignmentFlag.Align'),
)


def ConvertSpritesModule(text):
    """
    Returns `text` with the known PyQt5 idioms rewritten for PyQt6.

    Pure: takes source, returns source. Kept separate from the file handling so
    it can be reasoned about and tested without touching a user's patch.

    Idempotent by construction - converting twice gives the same result as
    converting once - which is the property that lets the caller run it on
    every patch load rather than once behind a prompt.
    """
    text = text.replace('PyQt5', 'PyQt6')

    for pattern, replacement in _SPRITES_PYQT6_RULES:
        text = re.sub(pattern, replacement, text)

    return text


def FixSpritesModule(filename):
    """
    Rewrites a patch's sprites.py for PyQt6, in place, if anything needs it.

    Run on every patch load rather than once behind a prompt (NSMBW-Community
    f2de79d, agreed in the community): a patch fixed by an older version of this
    converter still benefits when new substitutions are added, and the user has
    no way to answer "should I upgrade this?" usefully anyway.

    No backup is kept, which is deliberate and was the community's decision -
    the previous sprites_old.py accumulated beside the patch and was never read
    back by anything.

    The file is only written when the conversion actually changes something, so
    an already-converted patch is left alone entirely: no rewrite, no modified
    timestamp, and nothing to undo if the user has the file open elsewhere.

    Never fatal. A patch that cannot be converted is still loaded as it is - it
    may well work - and a read-only file is a perfectly ordinary thing to
    encounter.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            original = f.read()

        converted = ConvertSpritesModule(original)

        if converted == original:
            return False

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(converted)

        print('[GAMEDEF] converted %s for PyQt6' % filename)
        return True
    except Exception as error:
        # Reported rather than raised: the load continues with whatever is on
        # disk, which is the same position we were in before trying.
        print(f"Sprite Upgrader -- Exception occurred: {error}")
        return False
