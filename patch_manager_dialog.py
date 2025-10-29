import os
import sys

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from ui import GetIcon
import globals_
from dirty import setting, setSetting
from gamedef import ReggieGameDefinition, getAvailableGameDefs
from misc import validateFolderForPatch
from catalog_manager import CatalogManager
from download_manager import DownloadManager, github_folder_to_zip_url, extract_folder_name_from_url
from xml.etree import ElementTree as etree


class PatchManagerDialog(QtWidgets.QDialog):
    """
    Dialog for managing game patches and their folder paths
    """
    
    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        self.setWindowTitle('Patch Manager')
        self.setWindowIcon(GetIcon('game'))
        self.setMinimumWidth(1200)
        self.setMinimumHeight(700)
        
        # Enable native window controls (minimize, maximize, close)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        
        # Clean up orphaned patch paths before loading patches
        from gamedef import cleanupOrphanedPatchPaths
        cleanupOrphanedPatchPaths()
        
        # Initialize managers
        self.catalog_manager = CatalogManager()
        self.download_manager = DownloadManager()
        
        # Track catalog status
        self.catalog_status = {}  # {patch_name: status}
        
        # Track scanned Riivolution mods (temporary, cleared on close)
        self.scanned_riiv_mods = []
        
        # Track temp directories for reuse and cleanup
        self.temp_dirs = {}  # {zip_url: temp_dir_path}
        
        # Track active download thread for cancellation
        self.active_download_thread = None
        self.active_download_button = None  # Track which button initiated download
        
        # Load catalog
        catalog_loaded, catalog_error = self.catalog_manager.load_catalog()
        catalog_entries = self.catalog_manager.get_all_entries()
        print(f"[PatchManager] Catalog loaded: {catalog_loaded}, Entries: {len(catalog_entries)}")
        if catalog_error:
            print(f"[PatchManager] Catalog load warning: {catalog_error}")
        
        # Get all available patches
        self.patches = self._get_all_patches()
        
        # Create UI
        mainLayout = QtWidgets.QVBoxLayout(self)
        
        # Info label
        infoLabel = QtWidgets.QLabel(
            'Manage folder paths and plugins for each game patch. Select a patch to view/edit its plugins.<br><font color="orange"><b>Patch Manager Catalog Beta:</b> Updated to support Horizon mod database. Post problems to Discord.</font>'
        )
        infoLabel.setWordWrap(True)
        infoLabel.setFixedHeight(40)
        mainLayout.addWidget(infoLabel)
        
        # Create splitter for table and plugin editor
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Split into Installed and Catalog
        leftWidget = QtWidgets.QWidget()
        leftLayout = QtWidgets.QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        
        # Create vertical splitter for installed/catalog
        leftSplitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        
        # Top: Installed patches
        installedWidget = QtWidgets.QWidget()
        installedLayout = QtWidgets.QVBoxLayout(installedWidget)
        installedLayout.setContentsMargins(0, 0, 0, 0)
        
        installedLabel = QtWidgets.QLabel('<b>Installed Patches</b>')
        installedLayout.addWidget(installedLabel)
        
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['Patch Name', 'Stage Folder', 'Texture Folder', 'Patch Directory', '🐬', 'Actions', ''])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        
        # Set tooltip for Dolphin column
        self.table.horizontalHeaderItem(4).setToolTip('Indicates if this is a full mod installed to Riivolution folder')
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_patch_selected)
        
        # Populate table
        self._populate_table()
        
        installedLayout.addWidget(self.table)
        
        # Bottom: Catalog
        catalogWidget = QtWidgets.QWidget()
        catalogLayout = QtWidgets.QVBoxLayout(catalogWidget)
        catalogLayout.setContentsMargins(0, 0, 0, 0)
        
        catalogHeaderLayout = QtWidgets.QHBoxLayout()
        catalogLabel = QtWidgets.QLabel('<b>Available Patches (Catalog)</b>')
        catalogHeaderLayout.addWidget(catalogLabel)
        
        # Download status label
        self.downloadStatusLabel = QtWidgets.QLabel('')
        self.downloadStatusLabel.setStyleSheet('color: #4A90E2; font-weight: bold;')
        catalogHeaderLayout.addWidget(self.downloadStatusLabel)
        
        catalogHeaderLayout.addStretch()
        
        refreshBtn = QtWidgets.QPushButton('Refresh Catalog')
        refreshBtn.clicked.connect(self._refresh_catalog)
        catalogHeaderLayout.addWidget(refreshBtn)
        
        catalogLayout.addLayout(catalogHeaderLayout)
        
        # Dolphin Riivolution Root path setting
        dolphinPathLayout = QtWidgets.QHBoxLayout()
        dolphinPathLabel = QtWidgets.QLabel('Dolphin Riivolution Root:')
        dolphinPathLayout.addWidget(dolphinPathLabel)
        
        self.dolphinPathEdit = QtWidgets.QLineEdit()
        self.dolphinPathEdit.setReadOnly(True)
        dolphin_path = setting('DolphinRiivolutionRoot', '')
        self.dolphinPathEdit.setText(dolphin_path)
        dolphinPathLayout.addWidget(self.dolphinPathEdit)
        
        dolphinBrowseBtn = QtWidgets.QPushButton('Browse...')
        dolphinBrowseBtn.clicked.connect(self._browse_dolphin_path)
        dolphinPathLayout.addWidget(dolphinBrowseBtn)
        
        catalogLayout.addLayout(dolphinPathLayout)
        
        self.catalogTable = QtWidgets.QTableWidget()
        self.catalogTable.setColumnCount(5)
        self.catalogTable.setHorizontalHeaderLabels(['Name', 'Version', 'Author', 'Description', 'Actions'])
        self.catalogTable.horizontalHeader().setStretchLastSection(False)
        self.catalogTable.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.catalogTable.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.catalogTable.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.catalogTable.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.catalogTable.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.catalogTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.catalogTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Populate catalog
        self._populate_catalog()
        
        catalogLayout.addWidget(self.catalogTable)
        
        # Add to splitter
        leftSplitter.addWidget(installedWidget)
        leftSplitter.addWidget(catalogWidget)
        leftSplitter.setStretchFactor(0, 1)
        leftSplitter.setStretchFactor(1, 1)
        
        leftLayout.addWidget(leftSplitter)
        
        # Right side: Plugin editor
        rightWidget = QtWidgets.QWidget()
        rightLayout = QtWidgets.QVBoxLayout(rightWidget)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        
        pluginLabel = QtWidgets.QLabel('<b>Plugins</b>')
        rightLayout.addWidget(pluginLabel)
        
        self.pluginScrollArea = QtWidgets.QScrollArea()
        self.pluginScrollArea.setWidgetResizable(True)
        self.pluginScrollArea.setMinimumWidth(300)
        
        self.pluginContainer = QtWidgets.QWidget()
        self.pluginLayout = QtWidgets.QVBoxLayout(self.pluginContainer)
        self.pluginLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.noSelectionLabel = QtWidgets.QLabel('Select a patch to view/edit plugins')
        self.noSelectionLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pluginLayout.addWidget(self.noSelectionLabel)
        
        self.pluginScrollArea.setWidget(self.pluginContainer)
        rightLayout.addWidget(self.pluginScrollArea)
        
        # Add widgets to splitter
        splitter.addWidget(leftWidget)
        splitter.addWidget(rightWidget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        mainLayout.addWidget(splitter)
        
        # Button box
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.buttonBox.rejected.connect(self.accept)
        
        # Add "Scan Riivolution Folder" button to the left of Close
        self.scanRiivBtn = QtWidgets.QPushButton('Scan Riivolution Folder')
        self.scanRiivBtn.clicked.connect(self._scan_riivolution_folder)
        self.buttonBox.addButton(self.scanRiivBtn, QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        
        # Add "Add Patch Folder" button to the left of Close
        self.addPatchBtn = QtWidgets.QPushButton('Add Patch Folder')
        self.addPatchBtn.clicked.connect(self._add_patch_folder)
        self.buttonBox.addButton(self.addPatchBtn, QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        
        # Add "Cancel Download" button (initially hidden)
        self.cancelDownloadBtn = QtWidgets.QPushButton('Cancel Download')
        self.cancelDownloadBtn.clicked.connect(self._cancel_download)
        self.cancelDownloadBtn.setVisible(False)
        self.buttonBox.addButton(self.cancelDownloadBtn, QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        
        mainLayout.addWidget(self.buttonBox)
        
        # Track plugin widgets
        self.plugin_widgets = {}
    
    def _get_all_patches(self):
        """
        Get all available patches including base game
        """
        patches = []
        
        # Add base game
        patches.append({
            'name': 'New Super Mario Bros. Wii',
            'folder': None,
            'custom': False,
            'custom_path': None
        })
        
        # Add all custom patches from reggiedata/patches and custom paths
        game_defs = getAvailableGameDefs()
        for folder in game_defs:
            if folder is None:
                continue
            
            try:
                # Check if there's a custom path for this patch
                custom_path = setting('PatchPath_' + folder)
                
                if custom_path:
                    gamedef = ReggieGameDefinition(folder, custom_path=custom_path)
                else:
                    gamedef = ReggieGameDefinition(folder)
                
                patches.append({
                    'name': gamedef.name,
                    'folder': folder,
                    'custom': True,
                    'custom_path': custom_path
                })
            except Exception as e:
                print(f"Failed to load patch {folder}: {e}")
        
        return patches
    
    def _populate_table(self):
        """
        Populate the table with patch information
        """
        self.table.setRowCount(len(self.patches))
        
        for row, patch in enumerate(self.patches):
            # Patch name
            nameItem = QtWidgets.QTableWidgetItem(patch['name'])
            nameItem.setFlags(nameItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, nameItem)
            
            # Get folder paths
            if patch['custom']:
                stage_path = setting('StageGamePath_' + patch['name'])
                texture_path = setting('TextureGamePath_' + patch['name'])
                patch_dir = patch['custom_path'] if patch['custom_path'] else os.path.join('reggiedata', 'patches', patch['folder'])
            else:
                stage_path = setting('StageGamePath')
                texture_path = setting('TextureGamePath')
                patch_dir = 'reggiedata'
            
            # Stage folder
            stageItem = QtWidgets.QTableWidgetItem(stage_path if stage_path else '(Not set)')
            stageItem.setFlags(stageItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if stage_path:
                stageItem.setToolTip(stage_path)  # Full path on hover
            else:
                stageItem.setForeground(QtGui.QBrush(QtGui.QColor(150, 150, 150)))
            self.table.setItem(row, 1, stageItem)
            
            # Texture folder
            textureItem = QtWidgets.QTableWidgetItem(texture_path if texture_path else '(Not set)')
            textureItem.setFlags(textureItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if texture_path:
                textureItem.setToolTip(texture_path)  # Full path on hover
            else:
                textureItem.setForeground(QtGui.QBrush(QtGui.QColor(150, 150, 150)))
            self.table.setItem(row, 2, textureItem)
            
            # Patch directory
            patchDirItem = QtWidgets.QTableWidgetItem(patch_dir)
            patchDirItem.setFlags(patchDirItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            patchDirItem.setToolTip(patch_dir)  # Full path on hover
            self.table.setItem(row, 3, patchDirItem)
            
            # Dolphin icon (check if this is a full mod in Riivolution)
            dolphin_path = setting('DolphinRiivolutionRoot', '')
            is_full_mod = False
            if dolphin_path and stage_path:
                # Check if stage path is inside Dolphin Riivolution folder
                stage_path_norm = os.path.normpath(stage_path)
                dolphin_path_norm = os.path.normpath(dolphin_path)
                if stage_path_norm.startswith(dolphin_path_norm):
                    is_full_mod = True
            
            dolphinItem = QtWidgets.QTableWidgetItem('🐬' if is_full_mod else '')
            dolphinItem.setFlags(dolphinItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            dolphinItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_full_mod:
                dolphinItem.setToolTip('Full mod installed to Riivolution folder')
            self.table.setItem(row, 4, dolphinItem)
            
            # Action buttons
            buttonWidget = QtWidgets.QWidget()
            buttonLayout = QtWidgets.QHBoxLayout(buttonWidget)
            buttonLayout.setContentsMargins(4, 2, 4, 2)
            buttonLayout.setSpacing(4)
            
            # Browse Stage button
            stageBtn = QtWidgets.QPushButton('Browse Stage')
            stageBtn.clicked.connect(lambda checked, r=row: self._browse_stage(r))
            buttonLayout.addWidget(stageBtn)
            
            # Browse Texture button
            textureBtn = QtWidgets.QPushButton('Browse Texture')
            textureBtn.clicked.connect(lambda checked, r=row: self._browse_texture(r))
            buttonLayout.addWidget(textureBtn)
            
            self.table.setCellWidget(row, 5, buttonWidget)
            
            # Remove button (X icon) - skip for base game
            if patch['custom']:
                removeBtn = QtWidgets.QPushButton('✖')
                removeBtn.setMaximumWidth(30)
                removeBtn.setToolTip('Remove this patch')
                removeBtn.clicked.connect(lambda checked, r=row: self._remove_patch(r))
                self.table.setCellWidget(row, 6, removeBtn)
    
    def _remove_patch(self, row):
        """
        Remove a patch from the system
        
        Args:
            row: Row index in the patches table
        """
        patch = self.patches[row]
        patch_name = patch['name']
        
        # Don't allow removing base game
        if not patch['custom']:
            QtWidgets.QMessageBox.warning(self, 'Cannot Remove', 'Cannot remove the base game.')
            return
        
        # Confirmation dialog
        reply = QtWidgets.QMessageBox.question(
            self,
            'Remove Patch',
            f'Are you sure you want to remove "{patch_name}"?\n\n'
            f'This will:\n'
            f'- Delete the patch folder\n'
            f'- Remove all settings for this patch\n'
            f'- Remove it from the Change Game menu\n\n'
            f'This action cannot be undone.',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel
        )
        
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        
        try:
            import shutil
            
            # Only delete patch folder if it's in the default reggiedata/patches location
            # Don't delete external patch folders
            if patch['folder'] and not patch.get('custom_path'):
                patch_dir = os.path.join('reggiedata', 'patches', patch['folder'])
                if os.path.exists(patch_dir):
                    shutil.rmtree(patch_dir)
            
            # Remove all settings for this patch
            # Remove StageGamePath
            setting_key = 'StageGamePath_' + patch_name
            if setting(setting_key):
                setSetting(setting_key, None)
            
            # Remove TextureGamePath
            setting_key = 'TextureGamePath_' + patch_name
            if setting(setting_key):
                setSetting(setting_key, None)
            
            # Remove PatchPath (for external patches) - uses folder name, not patch name
            if patch['folder']:
                setting_key = 'PatchPath_' + patch['folder']
                if setting(setting_key):
                    setSetting(setting_key, None)
            
            # Reload patches list
            self.patches = self._get_all_patches()
            self._populate_table()
            
            # Refresh the main window's GameDefMenu
            if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
                if hasattr(globals_.mainWindow, 'GameDefMenu'):
                    globals_.mainWindow.GameDefMenu.refreshMenu()
            
            QtWidgets.QMessageBox.information(self, 'Patch Removed', 
                f'"{patch_name}" has been removed successfully.')
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Removal Failed', 
                f'Failed to remove patch: {str(e)}')
    
    def _browse_stage(self, row):
        """
        Browse for Stage folder
        """
        patch = self.patches[row]
        
        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        
        from misc import getExistingDirectoryWithSidebar
        stage_path = getExistingDirectoryWithSidebar(
            self,
            f"Select Stage Folder for {patch['name']}",
            '',
            dialog_options
        )
        
        if not stage_path:
            return
        
        stage_path = os.path.normpath(stage_path)
        
        # Validate folder type and potentially switch patches
        validated_path, validated_patch_name = validateFolderForPatch(
            stage_path, True, patch['name'], self
        )
        
        # If patch name changed, find the correct patch
        if validated_patch_name != patch['name']:
            for i, p in enumerate(self.patches):
                if p['name'] == validated_patch_name:
                    row = i
                    patch = p
                    break
        
        # Set the stage path
        if patch['custom']:
            setSetting('StageGamePath_' + patch['name'], stage_path)
        else:
            setSetting('StageGamePath', stage_path)
        
        # Auto-detect texture path
        texture_path = os.path.join(stage_path, 'Texture')
        if os.path.isdir(texture_path):
            if patch['custom']:
                setSetting('TextureGamePath_' + patch['name'], texture_path)
            else:
                setSetting('TextureGamePath', texture_path)
        
        # Refresh table
        self._populate_table()
    
    def _browse_texture(self, row):
        """
        Browse for Texture folder
        """
        patch = self.patches[row]
        
        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        
        from misc import getExistingDirectoryWithSidebar
        texture_path = getExistingDirectoryWithSidebar(
            self,
            f"Select Texture Folder for {patch['name']}",
            '',
            dialog_options
        )
        
        if not texture_path:
            return
        
        texture_path = os.path.normpath(texture_path)
        
        # Validate folder type and potentially switch patches
        validated_path, validated_patch_name = validateFolderForPatch(
            texture_path, False, patch['name'], self
        )
        
        # If patch name changed, find the correct patch
        if validated_patch_name != patch['name']:
            for i, p in enumerate(self.patches):
                if p['name'] == validated_patch_name:
                    row = i
                    patch = p
                    break
        
        # Set the texture path
        if patch['custom']:
            setSetting('TextureGamePath_' + patch['name'], texture_path)
        else:
            setSetting('TextureGamePath', texture_path)
        
        # Refresh table
        self._populate_table()
    
    def _on_patch_selected(self):
        """
        Called when a patch is selected in the table
        """
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_plugin_editor()
            return
        
        row = selected_rows[0].row()
        patch = self.patches[row]
        
        self._load_plugin_editor(patch)
    
    def _clear_plugin_editor(self):
        """
        Clear the plugin editor pane
        """
        # Remove all widgets except the no selection label
        while self.pluginLayout.count() > 0:
            item = self.pluginLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.noSelectionLabel = QtWidgets.QLabel('Select a patch to view/edit plugins')
        self.noSelectionLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pluginLayout.addWidget(self.noSelectionLabel)
        
        self.plugin_widgets = {}
    
    def _load_plugin_editor(self, patch):
        """
        Load the plugin editor for the selected patch
        """
        # Clear existing widgets
        while self.pluginLayout.count() > 0:
            item = self.pluginLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.plugin_widgets = {}
        
        # Base game doesn't have plugins
        if not patch['custom']:
            label = QtWidgets.QLabel('The base game does not support plugins.')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pluginLayout.addWidget(label)
            return
        
        # Get plugins path
        patch_dir = patch['custom_path'] if patch['custom_path'] else os.path.join('reggiedata', 'patches', patch['folder'])
        plugins_path = os.path.join(patch_dir, 'plugins.xml')
        
        # Load existing plugins or create default
        plugins = self._load_plugins_from_file(plugins_path)
        
        # Define available plugins with their parameters
        available_plugins = [
            {
                'id': 'connected_pipe_exit',
                'name': 'Connected Pipe Exit Direction',
                'description': 'Enables the connected pipe exit direction option',
                'params': []
            },
            {
                'id': 'special_event_sprite',
                'name': 'Custom Special Event Sprite ID',
                'description': 'Use a custom sprite ID for the Special Event sprite',
                'params': [
                    {'name': 'sprite_name', 'label': 'Sprite Name', 'default': 'Special Event'}
                ]
            }
        ]
        
        # Create UI for each plugin
        for plugin_def in available_plugins:
            plugin_id = plugin_def['id']
            plugin_data = plugins.get(plugin_id, {'enabled': False, 'params': {}})
            
            # Create group box for plugin
            groupBox = QtWidgets.QGroupBox(plugin_def['name'])
            groupLayout = QtWidgets.QVBoxLayout()
            
            # Checkbox to enable/disable
            checkbox = QtWidgets.QCheckBox('Enabled')
            checkbox.setChecked(plugin_data['enabled'])
            checkbox.stateChanged.connect(lambda state, pid=plugin_id: self._on_plugin_toggled(pid, state, patch, plugins_path))
            groupLayout.addWidget(checkbox)
            
            # Description
            desc = QtWidgets.QLabel(plugin_def['description'])
            desc.setWordWrap(True)
            desc.setStyleSheet('color: gray; font-size: 9pt;')
            groupLayout.addWidget(desc)
            
            # Parameters (if any)
            param_widgets = {}
            if plugin_def['params']:
                paramLayout = QtWidgets.QFormLayout()
                for param in plugin_def['params']:
                    param_name = param['name']
                    param_value = plugin_data['params'].get(param_name, param['default'])
                    
                    lineEdit = QtWidgets.QLineEdit(param_value)
                    lineEdit.setEnabled(plugin_data['enabled'])
                    lineEdit.textChanged.connect(lambda text, pid=plugin_id, pname=param_name: 
                                                self._on_param_changed(pid, pname, text, patch, plugins_path))
                    paramLayout.addRow(param['label'] + ':', lineEdit)
                    param_widgets[param_name] = lineEdit
                
                groupLayout.addLayout(paramLayout)
            
            groupBox.setLayout(groupLayout)
            self.pluginLayout.addWidget(groupBox)
            
            # Store widgets for later access
            self.plugin_widgets[plugin_id] = {
                'checkbox': checkbox,
                'params': param_widgets
            }
    
    def _load_plugins_from_file(self, plugins_path):
        """
        Load plugins from plugins.xml file
        """
        plugins = {}
        
        if not os.path.isfile(plugins_path):
            return plugins
        
        try:
            tree = etree.parse(plugins_path)
            root = tree.getroot()
            
            for plugin in root.findall('plugin'):
                name = plugin.get('name')
                enabled = plugin.get('enabled', 'false').lower() == 'true'
                
                params = {}
                for param in plugin.findall('param'):
                    param_name = param.get('name')
                    param_value = param.get('value', '')
                    params[param_name] = param_value
                
                plugins[name] = {
                    'enabled': enabled,
                    'params': params
                }
        except Exception as e:
            print(f"Failed to load plugins.xml: {e}")
        
        return plugins
    
    def _on_plugin_toggled(self, plugin_id, state, patch, plugins_path):
        """
        Called when a plugin checkbox is toggled
        """
        enabled = state == Qt.CheckState.Checked.value
        
        # Enable/disable parameter widgets
        if plugin_id in self.plugin_widgets:
            for param_widget in self.plugin_widgets[plugin_id]['params'].values():
                param_widget.setEnabled(enabled)
        
        # Save to file
        self._save_plugins_to_file(patch, plugins_path)
    
    def _on_param_changed(self, plugin_id, param_name, value, patch, plugins_path):
        """
        Called when a parameter value changes
        """
        # Save to file
        self._save_plugins_to_file(patch, plugins_path)
    
    def _save_plugins_to_file(self, patch, plugins_path):
        """
        Save current plugin settings to plugins.xml
        """
        # Build plugin data from widgets
        plugins_data = {}
        
        for plugin_id, widgets in self.plugin_widgets.items():
            enabled = widgets['checkbox'].isChecked()
            params = {}
            for param_name, param_widget in widgets['params'].items():
                params[param_name] = param_widget.text()
            
            plugins_data[plugin_id] = {
                'enabled': enabled,
                'params': params
            }
        
        # Define plugin metadata
        plugin_metadata = {
            'connected_pipe_exit': 'Connected Pipe Exit Direction',
            'special_event_sprite': 'Custom Special Event Sprite ID'
        }
        
        # Create XML structure
        root = etree.Element('plugins')
        root.text = '\n  '
        root.tail = '\n'
        
        for i, (plugin_id, data) in enumerate(plugins_data.items()):
            # Add comment
            comment = etree.Comment(f' {plugin_metadata.get(plugin_id, plugin_id)} ')
            comment.tail = '\n  '
            root.append(comment)
            
            # Add plugin element
            plugin = etree.SubElement(root, 'plugin')
            plugin.set('name', plugin_id)
            plugin.set('enabled', 'true' if data['enabled'] else 'false')
            plugin.tail = '\n  ' if i < len(plugins_data) - 1 else '\n'
            
            # Add parameters
            if data['params']:
                plugin.text = '\n    '
                for j, (param_name, param_value) in enumerate(data['params'].items()):
                    param = etree.SubElement(plugin, 'param')
                    param.set('name', param_name)
                    param.set('value', param_value)
                    param.tail = '\n    ' if j < len(data['params']) - 1 else '\n  '
        
        # Write to file
        try:
            tree = etree.ElementTree(root)
            self._indent_xml(root)
            tree.write(plugins_path, encoding='utf-8', xml_declaration=True)
        except Exception as e:
            print(f"Failed to save plugins.xml: {e}")
    
    def _indent_xml(self, elem, level=0):
        """
        Helper to indent XML for pretty printing
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
    
    def _populate_catalog(self):
        """
        Populate the catalog table with available patches
        """
        # Combine scanned Riivolution mods and catalog entries
        entries = self.catalog_manager.get_all_entries()
        total_rows = len(self.scanned_riiv_mods) + len(entries)
        self.catalogTable.setRowCount(total_rows)
        
        current_row = 0
        
        # First, add scanned Riivolution mods at the top
        for riiv_mod in self.scanned_riiv_mods:
            # Name
            nameItem = QtWidgets.QTableWidgetItem(riiv_mod['name'])
            nameItem.setFlags(nameItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            nameItem.setBackground(QtGui.QBrush(QtGui.QColor(70, 130, 180, 50)))  # Light blue background
            self.catalogTable.setItem(current_row, 0, nameItem)
            
            # Version
            versionItem = QtWidgets.QTableWidgetItem('(Scanned)')
            versionItem.setFlags(versionItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            versionItem.setBackground(QtGui.QBrush(QtGui.QColor(70, 130, 180, 50)))
            self.catalogTable.setItem(current_row, 1, versionItem)
            
            # Author
            authorItem = QtWidgets.QTableWidgetItem('Riivolution')
            authorItem.setFlags(authorItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            authorItem.setBackground(QtGui.QBrush(QtGui.QColor(70, 130, 180, 50)))
            self.catalogTable.setItem(current_row, 2, authorItem)
            
            # Description
            descItem = QtWidgets.QTableWidgetItem(f'Found in Riivolution folder: {riiv_mod["root_folder"]}')
            descItem.setFlags(descItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            descItem.setBackground(QtGui.QBrush(QtGui.QColor(70, 130, 180, 50)))
            self.catalogTable.setItem(current_row, 3, descItem)
            
            # Import button
            buttonWidget = QtWidgets.QWidget()
            buttonLayout = QtWidgets.QHBoxLayout(buttonWidget)
            buttonLayout.setContentsMargins(4, 2, 4, 2)
            buttonLayout.setSpacing(4)
            
            importBtn = QtWidgets.QPushButton('Import')
            importBtn.clicked.connect(lambda checked, mod=riiv_mod: self._import_riiv_mod(mod))
            buttonLayout.addWidget(importBtn)
            
            self.catalogTable.setCellWidget(current_row, 4, buttonWidget)
            current_row += 1
        
        # Then add regular catalog entries
        for row, entry in enumerate(entries, start=current_row):
            # Name
            nameItem = QtWidgets.QTableWidgetItem(entry.get('name', ''))
            nameItem.setFlags(nameItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.catalogTable.setItem(row, 0, nameItem)
            
            # Version
            versionItem = QtWidgets.QTableWidgetItem(entry.get('version', ''))
            versionItem.setFlags(versionItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.catalogTable.setItem(row, 1, versionItem)
            
            # Author
            authorItem = QtWidgets.QTableWidgetItem(entry.get('author', ''))
            authorItem.setFlags(authorItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.catalogTable.setItem(row, 2, authorItem)
            
            # Description
            descItem = QtWidgets.QTableWidgetItem(entry.get('description', ''))
            descItem.setFlags(descItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.catalogTable.setItem(row, 3, descItem)
            
            # Actions
            buttonWidget = QtWidgets.QWidget()
            buttonLayout = QtWidgets.QHBoxLayout(buttonWidget)
            buttonLayout.setContentsMargins(4, 2, 4, 2)
            buttonLayout.setSpacing(4)
            
            # Download button - shows status or download option
            status = self._get_download_status(entry.get('name', ''), entry.get('version', ''))
            
            if status == 'Download' or status == 'Update Available':
                # Determine button text
                btn_prefix = 'Update' if status == 'Update Available' else 'Download'
                
                # Check if Dolphin path is set
                dolphin_path = setting('DolphinRiivolutionRoot', '')
                has_dolphin_path = bool(dolphin_path and os.path.isdir(dolphin_path))
                
                # Check if full mod is already installed (Stage path in Riivolution folder)
                patch_name = entry.get('name', '')
                stage_path = setting('StageGamePath_' + patch_name)
                is_full_mod_installed = False
                if dolphin_path and stage_path:
                    stage_path_norm = os.path.normpath(stage_path)
                    dolphin_path_norm = os.path.normpath(dolphin_path)
                    if stage_path_norm.startswith(dolphin_path_norm):
                        is_full_mod_installed = True
                
                # Show method selection if fullMod is available
                if entry.get('fullMod'):
                    # Method 2: Full mod download (disabled if no Dolphin path or already up to date)
                    fullModBtn = QtWidgets.QPushButton(f'{btn_prefix} (Full)')
                    fullModBtn.clicked.connect(lambda checked, e=entry, btn=fullModBtn: self._download_patch(e, method=2, button=btn))
                    
                    # Enable only if: Dolphin path set AND (new download OR update available)
                    # Disable if full mod is already installed and no update is available
                    should_enable_full = has_dolphin_path and not (is_full_mod_installed and status != 'Update Available')
                    fullModBtn.setEnabled(should_enable_full)
                    
                    if not has_dolphin_path:
                        fullModBtn.setToolTip('Set Dolphin Riivolution Root path to enable')
                    elif is_full_mod_installed and status != 'Update Available':
                        fullModBtn.setToolTip('Full mod already up to date')
                    
                    buttonLayout.addWidget(fullModBtn)
                    
                    # Method 1: Individual folders (disabled if full mod is installed)
                    method1Btn = QtWidgets.QPushButton(f'{btn_prefix} (Stage/Texture)')
                    method1Btn.clicked.connect(lambda checked, e=entry, btn=method1Btn: self._download_patch(e, method=1, button=btn))
                    method1Btn.setEnabled(not is_full_mod_installed)
                    if is_full_mod_installed:
                        method1Btn.setToolTip('Full mod already installed - Parts download not needed')
                    buttonLayout.addWidget(method1Btn)
                else:
                    # Only Method 1 available
                    downloadBtn = QtWidgets.QPushButton(btn_prefix)
                    downloadBtn.clicked.connect(lambda checked, e=entry, btn=downloadBtn: self._download_patch(e, method=1, button=btn))
                    buttonLayout.addWidget(downloadBtn)
            else:
                # Show status button (Downloading, Installed, etc.)
                statusBtn = QtWidgets.QPushButton(status)
                statusBtn.setEnabled(False)
                buttonLayout.addWidget(statusBtn)
            
            self.catalogTable.setCellWidget(row, 4, buttonWidget)
    
    def _refresh_catalog(self):
        """
        Refresh the catalog from remote
        """
        success, error_msg = self.catalog_manager.load_catalog(force_remote=True)
        entries = self.catalog_manager.get_all_entries()
        
        if success and not error_msg:
            # Successfully fetched from remote
            self._populate_catalog()
            QtWidgets.QMessageBox.information(
                self, 
                'Catalog Refreshed', 
                f'Catalog has been updated successfully.\n\nFound {len(entries)} catalog entries.'
            )
        elif success and error_msg:
            # Loaded from cache but remote fetch failed
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(
                self, 
                'Using Cached Catalog', 
                f'Failed to fetch latest catalog:\n{error_msg}\n\nUsing cached version with {len(entries)} entries.'
            )
        else:
            # Complete failure
            QtWidgets.QMessageBox.critical(
                self, 
                'Catalog Load Failed', 
                f'Failed to load catalog:\n{error_msg}\n\nNo catalog entries available.'
            )
    
    def _scan_riivolution_folder(self):
        """
        Scan Riivolution folder for installed mods (recursively searches for riivolution folders)
        """
        self.scanned_riiv_mods = []
        
        dolphin_path = setting('DolphinRiivolutionRoot', '')
        if not dolphin_path or not os.path.isdir(dolphin_path):
            QtWidgets.QMessageBox.warning(self, 'No Dolphin Path', 
                'Please set the Dolphin Riivolution Root path first.')
            return
        
        import re
        
        # Find all 'riivolution' folders recursively (up to 5 levels deep)
        riiv_xml_dirs = []
        try:
            for root, dirs, files in os.walk(dolphin_path):
                # Calculate depth
                depth = root[len(dolphin_path):].count(os.sep)
                if depth > 5:
                    # Don't go deeper than 5 levels
                    dirs[:] = []
                    continue
                
                if 'riivolution' in dirs:
                    riiv_xml_dirs.append(os.path.join(root, 'riivolution'))
        except Exception as e:
            print(f"Failed to walk Riivolution directory: {e}")
            return
        
        if not riiv_xml_dirs:
            QtWidgets.QMessageBox.information(self, 'No XMLs Found', 
                'No riivolution folders found in the Dolphin Riivolution Root.')
            return
        
        print(f"Found {len(riiv_xml_dirs)} riivolution folder(s) to scan")
        
        # Scan all found riivolution directories
        for riiv_xml_dir in riiv_xml_dirs:
            print(f"Scanning: {riiv_xml_dir}")
            # Calculate base path for nested XMLs (parent of riivolution folder)
            base_path = os.path.dirname(riiv_xml_dir)
            
            try:
                for filename in os.listdir(riiv_xml_dir):
                    if not filename.endswith('.xml'):
                        continue
                    
                    xml_path = os.path.join(riiv_xml_dir, filename)
                    
                    try:
                        with open(xml_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                        
                        # Try to extract root folder name
                        root_match = re.search(r'root="\/([^"]+)"', xml_content)
                        root_folder = None
                        mod_dir = None
                        
                        if root_match:
                            # Standard root attribute - relative to base_path for nested XMLs
                            root_folder = root_match.group(1)
                            mod_dir = os.path.join(base_path, root_folder)
                            print(f"  Found root attribute: {root_folder}")
                        else:
                            # Check for disc="/" pattern (no root attribute)
                            # Try with leading slash: external="/folder"
                            disc_root_match = re.search(r'<folder[^>]+external="\/([^"\/]+)"[^>]+disc="\/"[^>]*>', xml_content)
                            if disc_root_match:
                                root_folder = disc_root_match.group(1)
                                mod_dir = os.path.join(base_path, root_folder)
                                print(f"  Found disc='/' with leading slash: {root_folder}")
                            else:
                                # Try without leading slash: external="folder"
                                disc_root_match = re.search(r'<folder[^>]+external="([^"\/]+)"[^>]+disc="\/"[^>]*>', xml_content)
                                if disc_root_match:
                                    root_folder = disc_root_match.group(1)
                                    mod_dir = os.path.join(base_path, root_folder)
                                    print(f"  Found disc='/' without leading slash: {root_folder}")
                        
                        if not root_folder or not mod_dir:
                            print(f"  No root folder found in {filename}")
                            continue
                        
                        # Check if mod directory exists
                        if not os.path.isdir(mod_dir):
                            print(f"  Mod directory does not exist: {mod_dir}")
                            continue
                        
                        # Extract Stage folder - handle multiple patterns
                        stage_folder = None
                        # Pattern 1: Simple external name: external="Stage"
                        stage_match = re.search(r'<folder[^>]+external="([^"\/]+)"[^>]+disc="/Stage/?"[^>]*>', xml_content)
                        if stage_match:
                            stage_folder = stage_match.group(1)
                        else:
                            # Pattern 2: Full path: external="/root/Stage/" or external="/root/Stage"
                            stage_match = re.search(r'<folder[^>]+external="\/[^"]*?([^"\/]+)\/?Stage\/?[^"]*"[^>]+disc="/Stage/?[^"]*"[^>]*>', xml_content)
                            if stage_match:
                                # Extract the path relative to root
                                full_external = re.search(r'external="([^"]+)"[^>]+disc="/Stage/?[^"]*"', xml_content)
                                if full_external:
                                    ext_path = full_external.group(1).strip('/')
                                    # Remove leading root folder if present
                                    if ext_path.startswith(root_folder + '/'):
                                        stage_folder = ext_path[len(root_folder)+1:]
                                    else:
                                        stage_folder = ext_path
                        
                        # Extract Texture folder - handle multiple patterns
                        texture_folder = None
                        # Pattern 1: Simple external name: external="Texture"
                        texture_match = re.search(r'<folder[^>]+external="([^"\/]+)"[^>]+disc="/Stage/Texture/?"[^>]*>', xml_content)
                        if texture_match:
                            texture_folder = texture_match.group(1)
                        else:
                            # Pattern 2: Full path: external="/root/Stage/Texture/"
                            full_external = re.search(r'external="([^"]+)"[^>]+disc="/Stage/Texture/?[^"]*"', xml_content)
                            if full_external:
                                ext_path = full_external.group(1).strip('/')
                                # Remove leading root folder if present
                                if ext_path.startswith(root_folder + '/'):
                                    texture_folder = ext_path[len(root_folder)+1:]
                                else:
                                    texture_folder = ext_path
                        
                        # Verify Stage folder exists
                        stage_path = os.path.join(mod_dir, stage_folder) if stage_folder else None
                        if not stage_path or not os.path.isdir(stage_path):
                            print(f"  Stage folder not found: {stage_path}")
                            continue
                        
                        # Verify Texture folder exists (if specified)
                        texture_path = None
                        if texture_folder:
                            texture_path = os.path.join(mod_dir, texture_folder)
                            if not os.path.isdir(texture_path):
                                texture_path = None
                        
                        # Extract mod name from section name in Riivolution XML
                        mod_name = None
                        
                        # Always use <section name="..."> for patch name
                        name_match = re.search(r'<section[^>]+name="([^"]+)"', xml_content)
                        if name_match:
                            mod_name = name_match.group(1)
                            print(f"  Found patch name in <section>: {mod_name}")
                        else:
                            print(f"  Warning: No <section name=\"...\"> found in {filename}")
                            continue
                        
                        # Check if already added (avoid duplicates)
                        if any(mod['name'] == mod_name and mod['root_folder'] == root_folder for mod in self.scanned_riiv_mods):
                            print(f"  Skipping duplicate: {mod_name}")
                            continue
                        
                        # Add to scanned mods list
                        self.scanned_riiv_mods.append({
                            'name': mod_name,
                            'root_folder': root_folder,
                            'stage_path': stage_path,
                            'texture_path': texture_path,
                            'xml_path': xml_path,
                            'mod_dir': mod_dir
                        })
                        
                        print(f"✓ Found Riivolution mod: {mod_name} (root: {root_folder}, Stage: {stage_folder}, Texture: {texture_folder or 'N/A'})")
                        
                    except Exception as e:
                        print(f"Failed to parse {filename}: {e}")
                        import traceback
                        traceback.print_exc()
            
            except Exception as e:
                print(f"Failed to scan {riiv_xml_dir}: {e}")
        
        # Refresh catalog to show scanned mods
        if self.scanned_riiv_mods:
            self._populate_catalog()
            QtWidgets.QMessageBox.information(self, 'Scan Complete', 
                f'Found {len(self.scanned_riiv_mods)} Riivolution mod(s).')
        else:
            QtWidgets.QMessageBox.information(self, 'No Mods Found', 
                'No valid Riivolution mods found in the scanned folders.')
    
    def _import_riiv_mod(self, riiv_mod: dict):
        """
        Import a scanned Riivolution mod
        
        Args:
            riiv_mod: Dictionary with mod information from scan
        """
        mod_name = riiv_mod['name']
        
        # Check if patch already exists
        patch_folder_name = riiv_mod['root_folder']
        patch_dir = os.path.join('reggiedata', 'patches', patch_folder_name)
        
        if os.path.exists(patch_dir):
            QtWidgets.QMessageBox.warning(self, 'Already Exists', 
                f'A patch with this name already exists:\n{patch_folder_name}')
            return
        
        try:
            # Create patch directory
            os.makedirs(patch_dir, exist_ok=True)
            
            # Create main.xml with base="Newer Super Mario Bros. Wii"
            main_xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<game base="Newer Super Mario Bros. Wii" name="{mod_name}" version="0.1" description="Based on [i]Newer Super Mario Bros. Wii.[/i]" />
'''
            
            main_xml_path = os.path.join(patch_dir, 'main.xml')
            with open(main_xml_path, 'w', encoding='utf-8') as f:
                f.write(main_xml_content)
            
            # Update settings with Stage and Texture paths
            setSetting('StageGamePath_' + mod_name, riiv_mod['stage_path'])
            if riiv_mod['texture_path']:
                setSetting('TextureGamePath_' + mod_name, riiv_mod['texture_path'])
            
            # Reload patches list
            self.patches = self._get_all_patches()
            self._populate_table()
            
            # Refresh the main window's GameDefMenu
            if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
                if hasattr(globals_.mainWindow, 'GameDefMenu'):
                    globals_.mainWindow.GameDefMenu.refreshMenu()
            
            # Remove from scanned mods list
            self.scanned_riiv_mods.remove(riiv_mod)
            self._populate_catalog()
            
            QtWidgets.QMessageBox.information(self, 'Import Complete', 
                f'{mod_name} has been imported successfully!\n\n'
                f'Patch created in: {patch_dir}\n'
                f'Stage path: {riiv_mod["stage_path"]}\n'
                f'Texture path: {riiv_mod["texture_path"] if riiv_mod["texture_path"] else "N/A"}')
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Import Failed', f'Failed to import mod: {str(e)}')
    
    def _browse_dolphin_path(self):
        """
        Browse for Dolphin Riivolution Root directory
        """
        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        
        from misc import getExistingDirectoryWithSidebar
        dolphin_path = getExistingDirectoryWithSidebar(
            self,
            'Select Dolphin Riivolution Root Directory',
            '',
            dialog_options
        )
        
        if dolphin_path:
            dolphin_path = os.path.normpath(dolphin_path)
            self.dolphinPathEdit.setText(dolphin_path)
            setSetting('DolphinRiivolutionRoot', dolphin_path)
            
            # Refresh catalog to update button states
            self._populate_catalog()
    
    def _add_patch_folder(self):
        """
        Add a custom patch folder
        """
        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        
        from misc import getExistingDirectoryWithSidebar
        patch_path = getExistingDirectoryWithSidebar(
            self,
            'Select Reggie Patch Folder',
            '',
            dialog_options
        )
        
        if not patch_path:
            return
        
        patch_path = os.path.normpath(patch_path)
        patch_name = os.path.basename(patch_path)
        
        # Verify that main.xml exists in the selected folder
        if not os.path.isfile(os.path.join(patch_path, 'main.xml')):
            QtWidgets.QMessageBox.warning(self, 'Invalid Patch', 
                'The selected folder does not contain a valid Reggie patch (main.xml not found).')
            return
        
        # Check if a patch with this name already exists in patches directory
        patches_dir_path = os.path.join(os.getcwd(), 'reggiedata', 'patches', patch_name)
        if os.path.exists(patches_dir_path):
            QtWidgets.QMessageBox.warning(self, 'Error', 
                f'A patch with this name already exists in the patches directory:\n{patch_name}')
            return
        
        # Check if already configured in settings - if so, ask to update
        existing_path = setting('PatchPath_' + patch_name)
        if existing_path:
            reply = QtWidgets.QMessageBox.question(
                self,
                'Update Patch Path',
                f'A patch with this name is already configured:\n{patch_name}\n\n'
                f'Current path: {existing_path}\n'
                f'New path: {patch_path}\n\n'
                f'Do you want to update the patch path?\n'
                f'(Stage and Texture paths will be kept as-is)',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel
            )
            
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        
        # Save the patch path to settings (update or create)
        setSetting('PatchPath_' + patch_name, patch_path)
        
        # Refresh patches list and table
        self.patches = self._get_all_patches()
        self._populate_table()
        
        # Refresh the main window's GameDefMenu
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
            if hasattr(globals_.mainWindow, 'GameDefMenu'):
                globals_.mainWindow.GameDefMenu.refreshMenu()
        
        QtWidgets.QMessageBox.information(self, 'Patch Added', 
            f'Patch "{patch_name}" has been added successfully!')
    
    def _get_download_status(self, patch_name: str, catalog_version: str = None) -> str:
        """
        Get the download status for a catalog entry
        
        Args:
            patch_name: Name of the patch
            catalog_version: Version from catalog (optional)
        
        Returns:
            Status string for button text
        """
        # Check custom status first (Downloading, Error, etc.)
        if patch_name in self.catalog_status:
            return self.catalog_status[patch_name]
        
        # Check if installed
        if self.catalog_manager.is_patch_installed(patch_name):
            # Check for updates if catalog version is provided
            if catalog_version:
                installed_version = self.catalog_manager.get_installed_patch_version(patch_name)
                if installed_version:
                    comparison = self.catalog_manager.compare_versions(installed_version, catalog_version)
                    if comparison < 0:
                        return 'Update Available'
                    elif comparison == 0:
                        return 'Up to Date'
                    else:
                        return 'Newer Installed'
            return 'Installed'
        
        return 'Download'
    
    def _download_patch(self, entry: dict, method: int = 1, button=None):
        """
        Download and install a patch from the catalog
        
        Args:
            entry: Catalog entry dictionary
            method: Download method (1=Stage/Texture/Patch, 2=Full mod)
            button: The button that initiated the download (for progress updates)
        """
        patch_name = entry.get('name', '')
        
        # Store the button for progress updates
        self.active_download_button = button
        self.active_download_patch_name = patch_name  # Store patch name for status display
        if button:
            self.original_button_text = button.text()
        
        # Check if already installed
        if self.catalog_manager.is_patch_installed(patch_name):
            QtWidgets.QMessageBox.information(self, 'Already Installed', f'{patch_name} is already installed.')
            return
        
        # Show confirmation dialog for Method 2 (Full mod)
        if method == 2:
            reply = QtWidgets.QMessageBox.question(
                self,
                'Download Full Mod',
                f'This will download the full mod to your Riivolution folder, and can be used in Dolphin.\n\n'
                f'The download might be quite large.\n\n'
                f'Do you want to proceed?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel
            )
            
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        
        # Validate entry based on method
        if method == 1:
            is_valid, error = self.catalog_manager.validate_entry(entry)
            if not is_valid:
                QtWidgets.QMessageBox.warning(self, 'Invalid Entry', f'Cannot download: {error}')
                return
        elif method == 2:
            if not entry.get('fullMod'):
                QtWidgets.QMessageBox.warning(self, 'Invalid Entry', 'Full mod URL not available.')
                return
        
        # Update status
        self.catalog_status[patch_name] = 'Downloading'
        self._populate_catalog()
        
        # Start download process
        if method == 1:
            self._download_method1(entry)
        elif method == 2:
            self._download_method2(entry)
    
    def _download_method1(self, entry: dict):
        """
        Download using Method 1: Stage/Texture/Patch folders separately
        
        Args:
            entry: Catalog entry dictionary
        """
        patch_name = entry.get('name', '')
        stage_path = entry.get('stage', '')
        texture_path = entry.get('texture', '')
        patch_path = entry.get('patch', '')
        
        # Get the base ZIP URL from the new 'url' field
        base_zip_url = entry.get('url', '')
        
        # For backward compatibility: if no 'url' field, try old format
        if not base_zip_url:
            # Extract ZIP filename from any full URL in the entry (for backward compatibility)
            zip_file = entry.get('zipFile', None)
            if not zip_file:
                # Try to extract from stage URL if it's a full URL
                if stage_path and 'sourceforge.net' in stage_path:
                    import re
                    match = re.search(r'/patches/([^/]+\.zip)/', stage_path)
                    if match:
                        zip_file = match.group(1)
            
            # Parse URLs to get ZIP download URL and subfolder paths (old format)
            stage_zip_url, stage_subfolder = github_folder_to_zip_url(stage_path, zip_file)
            texture_zip_url, texture_subfolder = github_folder_to_zip_url(texture_path, zip_file) if texture_path else (None, None)
            patch_zip_url, patch_subfolder = github_folder_to_zip_url(patch_path, zip_file) if patch_path else (None, None)
        else:
            # New format: combine base URL with relative paths
            stage_zip_url = base_zip_url
            stage_subfolder = stage_path.lstrip('/')
            texture_zip_url = base_zip_url if texture_path else None
            texture_subfolder = texture_path.lstrip('/') if texture_path else None
            patch_zip_url = base_zip_url if patch_path else None
            patch_subfolder = patch_path.lstrip('/') if patch_path else None
        
        # Extract patch folder name from path (or use patch name if no path)
        patch_folder_name = extract_folder_name_from_url(patch_path) if patch_path else None
        if not patch_folder_name:
            patch_folder_name = patch_name.replace(' ', '')
        
        # Reuse temp directory if already downloaded, otherwise create new one
        import tempfile
        if stage_zip_url in self.temp_dirs and os.path.exists(self.temp_dirs[stage_zip_url]):
            temp_dir = self.temp_dirs[stage_zip_url]
            print(f"[_download_method1] Reusing temp dir: {temp_dir}")
        else:
            temp_dir = tempfile.mkdtemp(prefix='reggie_download_')
            self.temp_dirs[stage_zip_url] = temp_dir
            print(f"[_download_method1] Created new temp dir: {temp_dir}")
        
        if not stage_zip_url:
            self.catalog_status[patch_name] = 'Error'
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(self, 'Invalid URLs', 'Stage URL is not valid.')
            return
        
        print(f"[_download_method1] Final URLs:")
        print(f"  stage_zip_url: {stage_zip_url}")
        print(f"  stage_subfolder: {stage_subfolder}")
        print(f"  texture_zip_url: {texture_zip_url}")
        print(f"  texture_subfolder: {texture_subfolder}")
        
        # Download the repo ZIP (stage and patch might be from same repo)
        repo_zip = os.path.join(temp_dir, 'repo.zip')
        
        # Check if already downloaded
        if os.path.exists(repo_zip):
            print(f"[_download_method1] ZIP already exists, skipping download: {repo_zip}")
            # Directly install from existing ZIP
            self._install_patch_files(entry, repo_zip, temp_dir, stage_subfolder, texture_subfolder, patch_subfolder, patch_folder_name)
        else:
            print(f"[_download_method1] Downloading to: {repo_zip}")
            
            # Set UI to downloading state
            self._set_download_ui_state(True)
            self.downloadStatusLabel.setText(f"📥 Starting download of {patch_name}...")
            
            def on_repo_downloaded(success, message):
                self._set_download_ui_state(False)
                self.active_download_thread = None
                
                if not success:
                    self.catalog_status[patch_name] = 'Error'
                    self._populate_catalog()
                    QtWidgets.QMessageBox.warning(self, 'Download Failed', f'Failed to download: {message}')
                    return
                
                # Extract and install
                self._install_patch_files(entry, repo_zip, temp_dir, stage_subfolder, texture_subfolder, patch_subfolder, patch_folder_name)
            
            # Start download (use stage URL as they're likely from same repo)
            self.active_download_thread = self.download_manager.download_file(stage_zip_url, repo_zip, on_repo_downloaded)
            
            # Connect progress signal
            self.active_download_thread.progress.connect(self._update_download_progress)
    
    def _download_method2(self, entry: dict):
        """
        Download using Method 2: Full mod to Riivolution folder
        
        Args:
            entry: Catalog entry dictionary
        """
        patch_name = entry.get('name', '')
        fullmod_path = entry.get('fullMod', '')
        riiv_xml_path = entry.get('fullModRiivolution', '')
        
        # Get the base ZIP URL from the new 'url' field
        base_zip_url = entry.get('url', '')
        
        # For backward compatibility: if no 'url' field, try old format
        if not base_zip_url:
            # Extract ZIP filename from any full URL in the entry (for backward compatibility)
            zip_file = entry.get('zipFile', None)
            if not zip_file:
                # Try to extract from fullmod URL if it's a full URL
                if fullmod_path and 'sourceforge.net' in fullmod_path:
                    import re
                    match = re.search(r'/patches/([^/]+\.zip)/', fullmod_path)
                    if match:
                        zip_file = match.group(1)
            
            # Parse URL to get ZIP download URL and subfolder path (old format)
            fullmod_zip_url, fullmod_subfolder = github_folder_to_zip_url(fullmod_path, zip_file)
            riiv_xml_url = riiv_xml_path
        else:
            # New format: combine base URL with relative paths
            fullmod_zip_url = base_zip_url
            fullmod_subfolder = fullmod_path.lstrip('/')
            riiv_xml_url = base_zip_url if riiv_xml_path else None
            riiv_xml_subfolder = riiv_xml_path.lstrip('/') if riiv_xml_path else None
        
        # Get Dolphin path
        dolphin_path = setting('DolphinRiivolutionRoot', '')
        if not dolphin_path or not os.path.isdir(dolphin_path):
            self.catalog_status[patch_name] = 'Error'
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(self, 'No Dolphin Path', 'Dolphin Riivolution Root path is not set.')
            return
        
        # Reuse temp directory if already downloaded, otherwise create new one
        import tempfile
        if fullmod_zip_url in self.temp_dirs and os.path.exists(self.temp_dirs[fullmod_zip_url]):
            temp_dir = self.temp_dirs[fullmod_zip_url]
            print(f"[_download_method2] Reusing temp dir: {temp_dir}")
        else:
            temp_dir = tempfile.mkdtemp(prefix='reggie_download_')
            self.temp_dirs[fullmod_zip_url] = temp_dir
            print(f"[_download_method2] Created new temp dir: {temp_dir}")
        
        if not fullmod_zip_url:
            self.catalog_status[patch_name] = 'Error'
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(self, 'Invalid URL', 'Full mod URL is not valid.')
            return
        
        # Download the repo ZIP
        repo_zip = os.path.join(temp_dir, 'fullmod.zip')
        
        # Check if already downloaded
        if os.path.exists(repo_zip):
            print(f"[_download_method2] ZIP already exists, skipping download: {repo_zip}")
            # Directly install from existing ZIP
            xml_subfolder = riiv_xml_subfolder if base_zip_url else None
            self._install_fullmod(entry, repo_zip, temp_dir, fullmod_subfolder, dolphin_path, riiv_xml_url, xml_subfolder)
        else:
            print(f"[_download_method2] Downloading to: {repo_zip}")
            
            # Set UI to downloading state
            self._set_download_ui_state(True)
            self.downloadStatusLabel.setText(f"📥 Starting download of {patch_name}...")
            
            def on_fullmod_downloaded(success, message):
                self._set_download_ui_state(False)
                self.active_download_thread = None
                
                if not success:
                    self.catalog_status[patch_name] = 'Error'
                    self._populate_catalog()
                    QtWidgets.QMessageBox.warning(self, 'Download Failed', f'Failed to download: {message}')
                    return
                
                # Extract entire mod to Riivolution folder
                # For new format, pass riiv_xml_subfolder; for old format, it will be None
                xml_subfolder = riiv_xml_subfolder if base_zip_url else None
                self._install_fullmod(entry, repo_zip, temp_dir, fullmod_subfolder, dolphin_path, riiv_xml_url, xml_subfolder)
            
            # Start download
            self.active_download_thread = self.download_manager.download_file(fullmod_zip_url, repo_zip, on_fullmod_downloaded)
            
            # Connect progress signal
            self.active_download_thread.progress.connect(self._update_download_progress)
    
    def _install_fullmod(self, entry: dict, repo_zip: str, temp_dir: str, fullmod_subfolder: str, dolphin_path: str, riiv_xml_url: str, riiv_xml_subfolder: str = None):
        """
        Install full mod to Riivolution folder (Method 2)
        
        Args:
            entry: Catalog entry dictionary
            repo_zip: Path to downloaded repo zip
            temp_dir: Temporary directory
            fullmod_subfolder: Subfolder path in the ZIP
            dolphin_path: Dolphin Riivolution Root path
            riiv_xml_url: URL to Riivolution XML file
        """
        patch_name = entry.get('name', '')
        patch_url = entry.get('patch', '')
        
        try:
            import zipfile
            import shutil
            import urllib.request
            import re
            
            # Step 1: Download and parse Riivolution XML to get root folder name and paths
            riiv_root_name = None
            stage_folder = None
            texture_folder = None
            xml_dest = None
            
            if riiv_xml_url:
                # Create riivolution subdirectory
                riiv_xml_dir = os.path.join(dolphin_path, 'riivolution')
                os.makedirs(riiv_xml_dir, exist_ok=True)
                
                # Extract XML filename
                if riiv_xml_subfolder:
                    # New format: extract from ZIP using subfolder path
                    xml_filename = os.path.basename(riiv_xml_subfolder)
                    xml_dest = os.path.join(riiv_xml_dir, xml_filename)
                    
                    # Extract XML from ZIP
                    repo_root = os.path.join(temp_dir, 'extracted')
                    with zipfile.ZipFile(repo_zip, 'r') as zip_ref:
                        zip_ref.extractall(repo_root)
                    
                    xml_source = os.path.join(repo_root, riiv_xml_subfolder)
                    if os.path.exists(xml_source):
                        shutil.copy2(xml_source, xml_dest)
                        print(f"XML extracted from ZIP: {xml_dest}")
                    else:
                        print(f"WARNING: XML not found in ZIP at: {riiv_xml_subfolder}")
                else:
                    # Old format: download XML separately
                    xml_filename = extract_folder_name_from_url(riiv_xml_url)
                    if not xml_filename:
                        xml_filename = 'riivolution.xml'
                    
                    xml_dest = os.path.join(riiv_xml_dir, xml_filename)
                    try:
                        # Normalize URL (convert relative paths to full Sourceforge URLs)
                        from download_manager import normalize_catalog_url
                        raw_xml_url = normalize_catalog_url(riiv_xml_url, None)
                        
                        # Convert Sourceforge URL to direct download URL if needed
                        if 'sourceforge.net' in raw_xml_url and not raw_xml_url.endswith('/download'):
                            # Ensure we have the direct download URL
                            if raw_xml_url.endswith('.xml'):
                                raw_xml_url = raw_xml_url + '/download'
                        
                        print(f"Downloading XML from: {raw_xml_url}")
                        print(f"Saving to: {xml_dest}")
                        urllib.request.urlretrieve(raw_xml_url, xml_dest)
                        print(f"XML downloaded successfully")
                    except Exception as e:
                        print(f"Failed to download XML: {e}")
                
                # Parse XML to extract root folder name and Stage/Texture paths (both formats)
                if xml_dest and os.path.exists(xml_dest):
                    try:
                        with open(xml_dest, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                            
                            # Search for root="/ pattern
                            match = re.search(r'root="\/([^"]+)"', xml_content)
                            if match:
                                riiv_root_name = match.group(1)
                                print(f"Extracted root folder name: {riiv_root_name}")
                            
                            # Search for Stage folder: <folder external="..." disc="/Stage/..." or disc="/Stage">
                            stage_match = re.search(r'<folder[^>]+external="([^"]+)"[^>]+disc="/Stage"[^>]*>', xml_content)
                            if stage_match:
                                stage_folder = stage_match.group(1)
                                print(f"Extracted Stage folder: {stage_folder}")
                            
                            # Search for Texture folder: <folder external="..." disc="/Stage/Texture">
                            texture_match = re.search(r'<folder[^>]+external="([^"]+)"[^>]+disc="/Stage/Texture"[^>]*>', xml_content)
                            if texture_match:
                                texture_folder = texture_match.group(1)
                                print(f"Extracted Texture folder: {texture_folder}")
                    except Exception as xml_error:
                        print(f"Warning: Failed to parse Riivolution XML: {xml_error}")
                        import traceback
                        traceback.print_exc()
            
            # Fallback to patch name if we couldn't extract from XML
            if not riiv_root_name:
                riiv_root_name = patch_name.replace(' ', '')
                print(f"Using fallback root folder name: {riiv_root_name}")
            
            # Step 2: Extract the entire ZIP to temp
            extract_dir = os.path.join(temp_dir, 'extracted')
            with zipfile.ZipFile(repo_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # For Sourceforge ZIPs, files are extracted directly without a wrapper folder
            # The subfolder path already points to the correct location within the ZIP
            repo_root = extract_dir
            
            # Navigate to the fullmod subfolder
            fullmod_root = os.path.join(repo_root, fullmod_subfolder) if fullmod_subfolder else repo_root
            
            if not os.path.exists(fullmod_root):
                raise Exception(f'Full mod folder not found: {fullmod_subfolder}')
            
            # Step 3: Copy entire mod folder to Riivolution using extracted root name
            riiv_mod_dir = os.path.join(dolphin_path, riiv_root_name)
            os.makedirs(riiv_mod_dir, exist_ok=True)
            
            for item in os.listdir(fullmod_root):
                src = os.path.join(fullmod_root, item)
                dst = os.path.join(riiv_mod_dir, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            
            # Step 4: Update Stage/Texture paths in settings
            # First try paths extracted from XML, then fall back to common folder names
            if stage_folder:
                stage_path = os.path.join(riiv_mod_dir, stage_folder)
                if os.path.isdir(stage_path):
                    setSetting('StageGamePath_' + patch_name, stage_path)
                    print(f"Set Stage path from XML: {stage_path}")
            else:
                # Try common folder names: Stage, Stages, stage
                for folder_name in ['Stage', 'Stages', 'stage']:
                    stage_path = os.path.join(riiv_mod_dir, folder_name)
                    if os.path.isdir(stage_path):
                        setSetting('StageGamePath_' + patch_name, stage_path)
                        print(f"Set Stage path (fallback): {stage_path}")
                        break
            
            if texture_folder:
                texture_path = os.path.join(riiv_mod_dir, texture_folder)
                if os.path.isdir(texture_path):
                    setSetting('TextureGamePath_' + patch_name, texture_path)
                    print(f"Set Texture path from XML: {texture_path}")
            else:
                # Try common folder names: Stage/Texture, Texture, Tilesets
                for folder_path in ['Stage/Texture', 'Texture', 'Tilesets', 'Stage/Tilesets']:
                    texture_path = os.path.join(riiv_mod_dir, folder_path)
                    if os.path.isdir(texture_path):
                        setSetting('TextureGamePath_' + patch_name, texture_path)
                        print(f"Set Texture path (fallback): {texture_path}")
                        break
            
            # Step 5: Install patch files if available
            if patch_url:
                # Extract patch folder name from URL
                patch_folder_name = extract_folder_name_from_url(patch_url)
                if not patch_folder_name:
                    patch_folder_name = patch_name.replace(' ', '')
                
                # Download and install patch files
                patch_zip_url, patch_subfolder = github_folder_to_zip_url(patch_url)
                if patch_zip_url:
                    patch_zip = os.path.join(temp_dir, 'patch.zip')
                    
                    try:
                        urllib.request.urlretrieve(patch_zip_url, patch_zip)
                        
                        # Extract patch ZIP
                        patch_extract_dir = os.path.join(temp_dir, 'patch_extracted')
                        with zipfile.ZipFile(patch_zip, 'r') as zip_ref:
                            zip_ref.extractall(patch_extract_dir)
                        
                        # For Sourceforge ZIPs, files are extracted directly
                        patch_repo_root = patch_extract_dir
                        
                        # Copy patch files
                        patch_source = os.path.join(patch_repo_root, patch_subfolder)
                        patch_dir = os.path.join('reggiedata', 'patches', patch_folder_name)
                        os.makedirs(patch_dir, exist_ok=True)
                        
                        if os.path.exists(patch_source):
                            for item in os.listdir(patch_source):
                                src = os.path.join(patch_source, item)
                                dst = os.path.join(patch_dir, item)
                                if os.path.isdir(src):
                                    if os.path.exists(dst):
                                        shutil.rmtree(dst)
                                    shutil.copytree(src, dst)
                                else:
                                    shutil.copy2(src, dst)
                    except Exception as patch_error:
                        print(f"Warning: Failed to download patch files: {patch_error}")
            else:
                # No patch URL - create basic main.xml
                patch_folder_name = patch_name.replace(' ', '')
                patch_dir = os.path.join('reggiedata', 'patches', patch_folder_name)
                os.makedirs(patch_dir, exist_ok=True)
                
                main_xml_path = os.path.join(patch_dir, 'main.xml')
                if not os.path.exists(main_xml_path):
                    self._create_basic_patch(patch_name, patch_dir, entry)
            
            # Reload patches list
            self.patches = self._get_all_patches()
            
            # Refresh the main window's GameDefMenu
            if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
                if hasattr(globals_.mainWindow, 'GameDefMenu'):
                    globals_.mainWindow.GameDefMenu.refreshMenu()
            
            # Update status
            self.catalog_status[patch_name] = 'Installed'
            self._populate_catalog()
            self._populate_table()
            
            # Temp directory will be cleaned up when Patch Manager closes
            print(f"[_install_fullmod] Installation complete, temp dir will be cleaned on exit: {temp_dir}")
            
            QtWidgets.QMessageBox.information(self, 'Installation Complete', 
                f'{patch_name} has been installed!\n\n'
                f'Riivolution mod: {riiv_mod_dir}\n'
                f'Riivolution XML: {xml_dest if xml_dest else "N/A"}')
            
        except Exception as e:
            self.catalog_status[patch_name] = 'Error'
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(self, 'Installation Failed', f'Failed to install: {str(e)}')
    
    def _install_patch_files(self, entry: dict, repo_zip: str, temp_dir: str, stage_subfolder: str, texture_subfolder: str, patch_subfolder: str, patch_folder_name: str):
        """
        Install downloaded patch files (Method 1)
        
        Args:
            entry: Catalog entry dictionary
            repo_zip: Path to downloaded repo zip
            temp_dir: Temporary directory
            stage_subfolder: Subfolder path for stage files in the ZIP
            texture_subfolder: Subfolder path for texture files in the ZIP
            patch_subfolder: Subfolder path for patch files in the ZIP
            patch_folder_name: Name for the patch folder (from URL)
        """
        patch_name = entry.get('name', '')
        
        try:
            import zipfile
            import shutil
            
            # Extract the entire ZIP to temp
            extract_dir = os.path.join(temp_dir, 'extracted')
            with zipfile.ZipFile(repo_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # For Sourceforge ZIPs, files are extracted directly without a wrapper folder
            # The subfolder path already points to the correct location within the ZIP
            repo_root = extract_dir
            
            # Create target directories using mod name for assets, folder name for patch
            mod_dir = os.path.join('assets', 'mods', patch_name)
            stage_dir = os.path.join(mod_dir, 'Stage')
            texture_dir = os.path.join(mod_dir, 'Texture')
            patch_dir = os.path.join('reggiedata', 'patches', patch_folder_name)
            
            os.makedirs(stage_dir, exist_ok=True)
            os.makedirs(texture_dir, exist_ok=True)
            os.makedirs(patch_dir, exist_ok=True)
            
            # Copy stage files
            stage_source = os.path.join(repo_root, stage_subfolder)
            print(f"[_install_patch_files] Stage source: {stage_source}")
            print(f"[_install_patch_files] Stage source exists: {os.path.exists(stage_source)}")
            if os.path.exists(stage_source):
                items = os.listdir(stage_source)
                print(f"[_install_patch_files] Stage items found: {len(items)}")
                for item in items:
                    src = os.path.join(stage_source, item)
                    dst = os.path.join(stage_dir, item)
                    print(f"[_install_patch_files] Copying stage: {item}")
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            else:
                print(f"[_install_patch_files] WARNING: Stage source does not exist!")
            
            # Copy texture files (if different from stage)
            if texture_subfolder and texture_subfolder != stage_subfolder:
                texture_source = os.path.join(repo_root, texture_subfolder)
                if os.path.exists(texture_source):
                    for item in os.listdir(texture_source):
                        src = os.path.join(texture_source, item)
                        dst = os.path.join(texture_dir, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
            else:
                # Texture is inside Stage folder
                texture_source = os.path.join(stage_dir, 'Texture')
                if os.path.exists(texture_source):
                    setSetting('TextureGamePath_' + patch_name, texture_source)
            
            # Copy patch files (entire folder contents) if patch subfolder exists
            if patch_subfolder:
                patch_source = os.path.join(repo_root, patch_subfolder)
                if os.path.exists(patch_source):
                    for item in os.listdir(patch_source):
                        src = os.path.join(patch_source, item)
                        dst = os.path.join(patch_dir, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
            else:
                # No patch URL - create basic main.xml
                main_xml_path = os.path.join(patch_dir, 'main.xml')
                if not os.path.exists(main_xml_path):
                    self._create_basic_patch(patch_name, patch_dir, entry)
            
            # Update settings
            setSetting('StageGamePath_' + patch_name, stage_dir)
            if texture_subfolder and texture_subfolder != stage_subfolder:
                setSetting('TextureGamePath_' + patch_name, texture_dir)
            
            # Reload patches list to include the newly installed patch
            self.patches = self._get_all_patches()
            
            # Refresh the main window's GameDefMenu to show the new patch
            if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
                if hasattr(globals_.mainWindow, 'GameDefMenu'):
                    globals_.mainWindow.GameDefMenu.refreshMenu()
            
            # Update status
            self.catalog_status[patch_name] = 'Installed'
            self._populate_catalog()
            self._populate_table()
            
            # Temp directory will be cleaned up when Patch Manager closes
            print(f"[_install_patch_files] Installation complete, temp dir will be cleaned on exit: {temp_dir}")
            
            QtWidgets.QMessageBox.information(self, 'Installation Complete', f'{patch_name} has been installed successfully!')
            
        except Exception as e:
            self.catalog_status[patch_name] = 'Error'
            self._populate_catalog()
            QtWidgets.QMessageBox.warning(self, 'Installation Failed', f'Failed to install: {str(e)}')
    
    def _create_basic_patch(self, patch_name: str, patch_dir: str, entry: dict):
        """
        Create a basic main.xml for a patch
        
        Args:
            patch_name: Name of the patch
            patch_dir: Directory for the patch
            entry: Catalog entry (for metadata)
        """
        main_xml_path = os.path.join(patch_dir, 'main.xml')
        
        # Determine base game from entry
        base_game_value = entry.get('baseGame', '')
        if not base_game_value:
            # Default to Newer
            base_game = 'Newer Super Mario Bros. Wii'
        elif base_game_value.lower() == 'newer':
            base_game = 'Newer Super Mario Bros. Wii'
        elif base_game_value.lower() == 'base':
            base_game = 'New Super Mario Bros. Wii'
        else:
            # Custom value
            base_game = base_game_value
        
        # Create XML
        root = etree.Element('game')
        root.set('base', base_game)
        root.set('name', patch_name)
        root.set('version', entry.get('version', '1.0'))
        root.set('description', entry.get('description', ''))
        
        # Write to file
        tree = etree.ElementTree(root)
        tree.write(main_xml_path, encoding='utf-8', xml_declaration=True)
    
    def _cancel_download(self):
        """Cancel the active download"""
        if self.active_download_thread:
            print("[PatchManager] Cancelling download...")
            self.download_manager.cancel_download(self.active_download_thread)
            self.active_download_thread = None
            self._set_download_ui_state(False)
            QtWidgets.QMessageBox.information(self, 'Download Cancelled', 'The download has been cancelled.')
    
    def _update_download_progress(self, percent: int):
        """
        Update the download progress display
        
        Args:
            percent: Progress percentage (0-100)
        """
        # Update status label (always visible)
        patch_name = getattr(self, 'active_download_patch_name', 'Patch')
        self.downloadStatusLabel.setText(f"📥 Downloading {patch_name}... {percent}%")
        
        # Also update button if it still exists
        if self.active_download_button:
            try:
                # Check if button still exists (might be deleted if table refreshed)
                self.active_download_button.setText(f"Downloading... {percent}%")
                self.active_download_button.setEnabled(False)  # Gray out during download
            except RuntimeError:
                # Button was deleted, clear reference
                self.active_download_button = None
    
    def _reset_download_button(self):
        """Reset the download button to its original text"""
        # Clear status label
        self.downloadStatusLabel.setText('')
        
        # Reset button if it exists
        if self.active_download_button and hasattr(self, 'original_button_text'):
            try:
                self.active_download_button.setText(self.original_button_text)
                self.active_download_button.setEnabled(True)  # Re-enable button
            except RuntimeError:
                # Button was deleted, just clear reference
                pass
            self.active_download_button = None
    
    def _set_download_ui_state(self, downloading: bool):
        """
        Enable/disable UI elements during download
        
        Args:
            downloading: True if download is in progress, False otherwise
        """
        # Disable/enable bottom buttons
        self.scanRiivBtn.setEnabled(not downloading)
        self.addPatchBtn.setEnabled(not downloading)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setEnabled(not downloading)
        
        # Show/hide cancel button
        self.cancelDownloadBtn.setVisible(downloading)
        
        # Reset button if download is finished
        if not downloading:
            self._reset_download_button()
    
    def _cleanup_temp_dirs(self):
        """Clean up all temp directories"""
        import shutil
        if not self.temp_dirs:
            return
            
        print(f"[PatchManager] Cleaning up {len(self.temp_dirs)} temp directories...")
        for zip_url, temp_dir in list(self.temp_dirs.items()):
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    print(f"[PatchManager] Deleted temp dir: {temp_dir}")
                except Exception as e:
                    print(f"[PatchManager] Failed to delete temp dir {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def accept(self):
        """Override accept to clean up temp directories before closing"""
        self._cleanup_temp_dirs()
        super().accept()
    
    def reject(self):
        """Override reject to clean up temp directories before closing"""
        self._cleanup_temp_dirs()
        super().reject()
    
    def closeEvent(self, event):
        """Clean up temp directories when dialog closes"""
        self._cleanup_temp_dirs()
        event.accept()
