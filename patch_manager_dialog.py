import os
import sys

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from ui import GetIcon
import globals_
from dirty import setting, setSetting
from gamedef import ReggieGameDefinition, getAvailableGameDefs
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
        self.setMinimumHeight(500)
        
        # Get all available patches
        self.patches = self._get_all_patches()
        
        # Create UI
        mainLayout = QtWidgets.QVBoxLayout(self)
        
        # Info label
        infoLabel = QtWidgets.QLabel(
            'Manage folder paths and plugins for each game patch. Select a patch to view/edit its plugins.'
        )
        infoLabel.setWordWrap(True)
        infoLabel.setFixedHeight(30)
        mainLayout.addWidget(infoLabel)
        
        # Create splitter for table and plugin editor
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Table
        leftWidget = QtWidgets.QWidget()
        leftLayout = QtWidgets.QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Patch Name', 'Stage Folder', 'Texture Folder', 'Patch Directory', 'Actions'])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_patch_selected)
        
        # Populate table
        self._populate_table()
        
        leftLayout.addWidget(self.table)
        
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
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttonBox.rejected.connect(self.accept)
        mainLayout.addWidget(buttonBox)
        
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
        
        # Add all custom patches
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
            if not stage_path:
                stageItem.setForeground(QtGui.QBrush(QtGui.QColor(150, 150, 150)))
            self.table.setItem(row, 1, stageItem)
            
            # Texture folder
            textureItem = QtWidgets.QTableWidgetItem(texture_path if texture_path else '(Not set)')
            textureItem.setFlags(textureItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not texture_path:
                textureItem.setForeground(QtGui.QBrush(QtGui.QColor(150, 150, 150)))
            self.table.setItem(row, 2, textureItem)
            
            # Patch directory
            patchDirItem = QtWidgets.QTableWidgetItem(patch_dir)
            patchDirItem.setFlags(patchDirItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, patchDirItem)
            
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
            
            self.table.setCellWidget(row, 4, buttonWidget)
    
    def _browse_stage(self, row):
        """
        Browse for Stage folder
        """
        patch = self.patches[row]
        
        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        
        stage_path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            f"Select Stage Folder for {patch['name']}",
            '',
            dialog_options
        )
        
        if not stage_path:
            return
        
        stage_path = os.path.normpath(stage_path)
        
        # Check if this is a NewerSMBW folder or base game folder
        is_newer = self._is_newer_stage_folder(stage_path)
        is_base_expected = not patch['custom']
        
        # If mismatch, ask user
        if is_newer and is_base_expected:
            # User selected Newer folder for base game
            result = QtWidgets.QMessageBox.question(
                self,
                'Wrong Folder Type',
                f'The selected folder appears to be from Newer Super Mario Bros. Wii, not the base game.\n\n'
                f'Do you want to set this folder for Newer Super Mario Bros. Wii instead?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                # Find Newer patch and set it there
                for i, p in enumerate(self.patches):
                    if p['name'] == 'Newer Super Mario Bros. Wii':
                        row = i
                        patch = p
                        break
        
        elif not is_newer and not is_base_expected and patch['name'] == 'Newer Super Mario Bros. Wii':
            # User selected base game folder for Newer
            result = QtWidgets.QMessageBox.question(
                self,
                'Wrong Folder Type',
                f'The selected folder appears to be from the base game (New Super Mario Bros. Wii), not Newer Super Mario Bros. Wii.\n\n'
                f'Do you want to set this folder for the base game instead?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                # Find base game and set it there
                for i, p in enumerate(self.patches):
                    if not p['custom']:
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
        
        texture_path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            f"Select Texture Folder for {patch['name']}",
            '',
            dialog_options
        )
        
        if not texture_path:
            return
        
        texture_path = os.path.normpath(texture_path)
        
        # Check if this is a NewerSMBW folder or base game folder
        is_newer = self._is_newer_texture_folder(texture_path)
        is_base_expected = not patch['custom']
        
        # If mismatch, ask user
        if is_newer and is_base_expected:
            # User selected Newer folder for base game
            result = QtWidgets.QMessageBox.question(
                self,
                'Wrong Folder Type',
                f'The selected folder appears to be from Newer Super Mario Bros. Wii, not the base game.\n\n'
                f'Do you want to set this folder for Newer Super Mario Bros. Wii instead?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                # Find Newer patch and set it there
                for i, p in enumerate(self.patches):
                    if p['name'] == 'Newer Super Mario Bros. Wii':
                        row = i
                        patch = p
                        break
        
        elif not is_newer and not is_base_expected and patch['name'] == 'Newer Super Mario Bros. Wii':
            # User selected base game folder for Newer
            result = QtWidgets.QMessageBox.question(
                self,
                'Wrong Folder Type',
                f'The selected folder appears to be from the base game (New Super Mario Bros. Wii), not Newer Super Mario Bros. Wii.\n\n'
                f'Do you want to set this folder for the base game instead?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                # Find base game and set it there
                for i, p in enumerate(self.patches):
                    if not p['custom']:
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
    
    def _is_newer_stage_folder(self, path):
        """
        Check if the Stage folder is from Newer Super Mario Bros. Wii
        Returns True if it contains 10-01.arc or 10-01.arc.LH
        """
        return (os.path.isfile(os.path.join(path, '10-01.arc')) or 
                os.path.isfile(os.path.join(path, '10-01.arc.LH')))
    
    def _is_newer_texture_folder(self, path):
        """
        Check if the Texture folder is from Newer Super Mario Bros. Wii
        Returns True if it contains Cloudscape.arc or Cloudscape.arc.LH
        """
        return (os.path.isfile(os.path.join(path, 'Cloudscape.arc')) or 
                os.path.isfile(os.path.join(path, 'Cloudscape.arc.LH')))
    
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
