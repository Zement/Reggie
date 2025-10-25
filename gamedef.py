import os
import sys
import importlib
import functools
from xml.etree import ElementTree as etree

from PyQt6 import QtWidgets, QtCore, QtGui

from ui import GetIcon, createVertLine
from misc import LoadSpriteData, LoadSpriteListData, LoadSpriteCategories, LoadBgANames, LoadBgBNames, LoadObjDescriptions, LoadTilesetNames, LoadTilesetInfo, LoadEntranceNames, LoadMusicInfo, LoadZoneThemes
from dirty import setting, setSetting
from dialogs import SpriteUpgradeDialog

import globals_
import spritelib as SLib
import sprites

class GameDefViewer(QtWidgets.QWidget):
    """
    Widget which displays basic info about the current game definition
    """

    def __init__(self):
        """
        Initializes the widget
        """
        QtWidgets.QWidget.__init__(self)
        self.imgLabel = QtWidgets.QLabel()
        self.imgLabel.setToolTip(globals_.trans.string('Gamedefs', 0))
        self.imgLabel.setPixmap(GetIcon('sprites', False).pixmap(16, 16))
        self.versionLabel = QtWidgets.QLabel()
        self.titleLabel = QtWidgets.QLabel()
        self.descLabel = QtWidgets.QLabel()
        self.descLabel.setWordWrap(True)
        self.descLabel.setMinimumHeight(40)

        # Make layouts
        left = QtWidgets.QVBoxLayout()
        left.addWidget(self.imgLabel)
        left.addWidget(self.versionLabel)
        left.addStretch(1)
        right = QtWidgets.QVBoxLayout()
        right.addWidget(self.titleLabel)
        right.addWidget(self.descLabel)
        right.addStretch(1)
        main = QtWidgets.QHBoxLayout()
        main.addLayout(left)
        main.addWidget(createVertLine())
        main.addLayout(right)
        main.setStretch(2, 1)
        self.setLayout(main)
        self.setMaximumWidth(256 + 64)

        self.updateLabels()

    def updateLabels(self):
        """
        Updates all labels
        """
        sprite_folders = globals_.gamedef.recursiveFiles('sprites', is_folder=True)[0]

        if not globals_.gamedef.custom or sprite_folders:
            img = GetIcon('sprites', False).pixmap(16, 16)
        else:
            img = QtGui.QPixmap(16, 16)
            img.fill(QtGui.QColor(0, 0, 0, 0))

        ver = '' if globals_.gamedef.version is None else '<i><p style="font-size:10px;">v%s</p></i>' % str(globals_.gamedef.version)
        title = '<b>%s</b>' % str(globals_.gamedef.name)
        desc = str(globals_.gamedef.description)

        self.imgLabel.setPixmap(img)
        self.versionLabel.setText(ver)
        self.titleLabel.setText(title)
        self.descLabel.setText(desc)


class GameDefMenu(QtWidgets.QMenu):
    """
    A menu which lets the user pick gamedefs
    """
    gameChanged = QtCore.pyqtSignal()
    update_flag = False


    def add_reggie_patch(self):
        def select_reggie_patch_folder():
            src_path = QtWidgets.QFileDialog.getExistingDirectory(None, "Select Reggie Patch Folder ...")
            return src_path

        def restart_reggie_info():
            # Warn the user that they may need to restart
            QtWidgets.QMessageBox.warning(None, globals_.trans.string('PrefsDlg', 0), globals_.trans.string('PrefsDlg', 30))

        # Select the patch folder
        patch_path = select_reggie_patch_folder()
        if patch_path == "":
            return

        patch_path = os.path.normpath(patch_path)
        patch_name = os.path.basename(patch_path)
        
        # Verify that main.xml exists in the selected folder
        if not os.path.isfile(os.path.join(patch_path, 'main.xml')):
            QtWidgets.QMessageBox.warning(None, 'Invalid Patch', 
                f'The selected folder does not contain a valid Reggie patch (main.xml not found).')
            return
        
        # Check if a patch with this name already exists (in patches dir or settings)
        patches_dir_path = os.path.join(os.getcwd(), 'reggiedata', 'patches', patch_name)
        if os.path.exists(patches_dir_path):
            QtWidgets.QMessageBox.warning(None, 'Error', 
                f'A patch with this name already exists in the patches directory:\n{patch_name}')
            return
        
        # Check if already configured in settings
        existing_path = setting('PatchPath_' + patch_name)
        if existing_path:
            QtWidgets.QMessageBox.warning(None, 'Error', 
                f'A patch with this name is already configured:\n{patch_name}\nPath: {existing_path}')
            return
        
        # Save the patch path to settings
        # setSetting will automatically normalize the path format
        setSetting('PatchPath_' + patch_name, patch_path)
        
        # Refresh the menu to show the new patch
        self.refreshMenu()
        self.gameChanged.emit()


    def __init__(self):
        """
        Creates and initializes the menu
        """
        QtWidgets.QMenu.__init__(self)

        # Add the gamedef viewer widget
        self.currentView = GameDefViewer()
        self.currentView.setMinimumHeight(100)
        self.gameChanged.connect(self.currentView.updateLabels)

        v = QtWidgets.QWidgetAction(self)
        v.setDefaultWidget(self.currentView)
        self.addAction(v)
        self.addSeparator()

        # Add entries for each gamedef
        self.GameDefs = getAvailableGameDefs()

        self.actGroup = QtGui.QActionGroup(self)
        loadedDef = setting('LastGameDef')
        for folder in self.GameDefs:
            def_ = ReggieGameDefinition(folder)

            act = QtGui.QAction(self)
            act.setText(def_.name)
            act.setToolTip(def_.description)
            act.setData(folder)
            act.setActionGroup(self.actGroup)
            act.setCheckable(True)
            act.setChecked(folder == loadedDef)
            act.toggled.connect(self.handleGameDefClicked)

            self.addAction(act)

        # add button
        self.addSeparator()

        act = QtGui.QAction(self)
        act.setText(globals_.trans.string('Gamedefs', 19))
        act.setToolTip(globals_.trans.string('Gamedefs', 20))
        act.setActionGroup(self.actGroup)
        act.setCheckable(False)
        act.setChecked(False)
        act.triggered.connect(self.add_reggie_patch)

        self.addAction(act)


    def handleGameDefClicked(self, checked):
        """
        Handles the user clicking a gamedef
        """
        if not checked or self.update_flag: return

        name = self.actGroup.checkedAction().data()
        success = loadNewGameDef(name)
        if success:
            self.gameChanged.emit()
            return

        # Setting the new gamedef failed for some reason, so load back the old
        # game def.
        real_gamedef = setting('LastGameDef')
        success = loadNewGameDef(real_gamedef)
        if not success:
            raise Exception("Restoring the previous game def (%r) failed after failing to load new game def (%r)" % (real_gamedef, name))

        self.update_flag = True
        for act in self.actGroup.actions():
            act.setChecked(act.data() == real_gamedef)
        self.update_flag = False
    
    def refreshMenu(self):
        """
        Refresh the menu to show newly added patches
        """
        # Clear existing patch actions (but keep the viewer and add button)
        for act in self.actGroup.actions():
            self.removeAction(act)
            self.actGroup.removeAction(act)
        
        # Reload game defs
        self.GameDefs = getAvailableGameDefs()
        
        # Re-add entries for each gamedef
        loadedDef = setting('LastGameDef')
        for folder in self.GameDefs:
            def_ = ReggieGameDefinition(folder)
            
            act = QtGui.QAction(self)
            act.setText(def_.name)
            act.setToolTip(def_.description)
            act.setData(folder)
            act.setActionGroup(self.actGroup)
            act.setCheckable(True)
            act.setChecked(folder == loadedDef)
            act.toggled.connect(self.handleGameDefClicked)
            
            # Insert before the separator and "Add" button
            actions = self.actions()
            if len(actions) >= 3:  # viewer, separator, patches..., separator, add button
                self.insertAction(actions[-2], act)  # Insert before last separator

        # Also refresh the main window's patch combo box if it exists
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
            if hasattr(globals_.mainWindow, 'updatePatchComboBox'):
                globals_.mainWindow.updatePatchComboBox()


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

        try:
            self.InitFromName(name, custom_path)
        except Exception:
            self.InitAsEmpty()
            raise

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
        
        tree = etree.parse(path)
        root = tree.getroot()

        # Add the attributes of root: name, description and version.
        # base is added in __init2__, only when needed.
        self.name = root.get('name')

        if self.name is None:
            raise ValueError("Game definition XML %r has no 'name' attribute on the root node." % path)

        default = globals_.trans.string('Gamedefs', 15)
        self.description = root.get('description', default).replace('[', '<').replace(']', '>')
        self.version = root.get('version')

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
            
        tree = etree.parse(path)
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
            with open(self.files['sprites'].path, 'r', encoding='utf-8') as f:
                filedata = f.read()
            
            # Check if the file uses PyQt5 and prompt the user to upgrade it
            if filedata.find("PyQt5") != -1:
                result = SpriteUpgradeDialog().exec()
                if result == QtWidgets.QDialog.DialogCode.Accepted:
                    UpgradeSpritesFile(self.files['sprites'].path, self.gamepath)

                    # Reload the file since we just changed it
                    with open(self.files['sprites'].path, 'r', encoding='utf-8') as f:
                        filedata = f.read()

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
            
            # Define all available plugins with their parameters
            available_plugins = [
                {
                    'name': 'connected_pipe_exit',
                    'desc': 'Connected Pipe Exit Direction',
                    'params': []
                },
                {
                    'name': 'special_event_sprite',
                    'desc': 'Custom Special Event Sprite ID',
                    'params': [
                        {'name': 'sprite_name', 'value': 'Special Event'}
                    ]
                },
            ]
            
            # Create XML structure
            root = etree.Element('plugins')
            root.text = '\n  '
            root.tail = '\n'
            
            for i, plugin_def in enumerate(available_plugins):
                # Add comment
                comment = etree.Comment(f' {plugin_def["desc"]} ')
                comment.tail = '\n  '
                root.append(comment)
                
                # Add plugin element
                plugin = etree.SubElement(root, 'plugin')
                plugin.set('name', plugin_def['name'])
                plugin.set('enabled', 'false')
                plugin.tail = '\n  ' if i < len(available_plugins) - 1 else '\n'
                
                # Add parameters if any
                if plugin_def['params']:
                    plugin.text = '\n    '
                    for j, param in enumerate(plugin_def['params']):
                        param_elem = etree.SubElement(plugin, 'param')
                        param_elem.set('name', param['name'])
                        param_elem.set('value', param['value'])
                        param_elem.tail = '\n    ' if j < len(plugin_def['params']) - 1 else '\n  '
            
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

    def GetTextureGamePath(self):
        """
        Returns the texture game path
        """
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
        """
        paths = [setting('TextureGamePath')]

        if not self.custom:
            return paths

        stg = setting('TextureGamePath_' + self.name)

        if self.base is not None:
            paths = self.base.GetTexturePaths()

        paths.append(stg)

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

        # Load the globals_.gamedef
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
            # and tilesets from there
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
        if globals_.mainWindow is not None:
            globals_.mainWindow.ReloadTilesets(True)
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
        if dlg: dlg.setValue(7)

    except Exception as e:
        # Something went wrong loading the patch
        if dlg: dlg.setValue(7)  # autocloses it
        
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


    # Success!
    if dlg: setSetting('LastGameDef', name)
    return True

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


def UpgradeSpritesFile(filename, folderpath):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            orig_data = f.read()

        # First off, change the import
        new_data = orig_data.replace("PyQt5", "PyQt6")

        # Replacement time
        strings = [
            ("QPainter.Antialiasing", "QPainter.RenderHint.Antialiasing"),
            ("SmoothTransformation",  "TransformationMode.SmoothTransformation"),
            ("IgnoreAspectRatio",     "AspectRatioMode.IgnoreAspectRatio"),
            ("QPoint(",               "QPointF("), # Parenthesis to skip existing instances of QPointF
            ("Qt.transparent",        "Qt.GlobalColor.transparent"),
            ("Qt.Align",              "Qt.AlignmentFlag.Align"),
        ]
        for old, new in strings:
            #print(f"Replacing '{old}' with '{new}'")
            new_data = new_data.replace(old, new)

        # Update the file
        with open(filename, 'w') as fileOut:
            fileOut.write(new_data)

        # Now backup the old file
        with open(os.path.join("reggiedata", "patches", folderpath, "sprites_old.py"), 'w') as fileOrig:
            fileOrig.write(orig_data)

    except Exception as error:
        print(f"Sprite Upgrader -- Exception occurred: {error}")
