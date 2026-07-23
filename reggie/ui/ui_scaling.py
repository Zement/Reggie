"""
UI Scaling Manager for Reggie Next
Provides dynamic UI and font scaling for better accessibility on various display sizes
"""

from PyQt6 import QtCore, QtGui, QtWidgets
from reggie.core import globals_
from reggie.core.dirty import setting, setSetting


class ScalingManager:
    """
    Manages UI scaling for the entire application.
    Provides separate control for widget scaling and font scaling.
    """
    
    # Default scale factors
    DEFAULT_UI_SCALE = 1.0
    DEFAULT_FONT_SCALE = 1.0
    
    # Scale factor ranges
    MIN_UI_SCALE = 0.5
    MAX_UI_SCALE = 3.0
    MIN_FONT_SCALE = 0.5
    MAX_FONT_SCALE = 3.0
    
    def __init__(self):
        """Initialize the scaling manager"""
        self.ui_scale = self.DEFAULT_UI_SCALE
        self.font_scale = self.DEFAULT_FONT_SCALE
        self._base_font_size = None
        
    def loadSettings(self):
        """Load scaling settings from persistent storage"""
        self.ui_scale = setting('UIScale', self.DEFAULT_UI_SCALE)
        self.font_scale = setting('FontScale', self.DEFAULT_FONT_SCALE)
        
        # Ensure values are within valid range
        self.ui_scale = max(self.MIN_UI_SCALE, min(self.MAX_UI_SCALE, self.ui_scale))
        self.font_scale = max(self.MIN_FONT_SCALE, min(self.MAX_FONT_SCALE, self.font_scale))
        
    def saveSettings(self):
        """Save scaling settings to persistent storage"""
        setSetting('UIScale', self.ui_scale)
        setSetting('FontScale', self.font_scale)
        
    def setUIScale(self, scale):
        """Set the UI scale factor"""
        self.ui_scale = max(self.MIN_UI_SCALE, min(self.MAX_UI_SCALE, scale))
        
    def setFontScale(self, scale):
        """Set the font scale factor"""
        self.font_scale = max(self.MIN_FONT_SCALE, min(self.MAX_FONT_SCALE, scale))
        
    def getUIScale(self):
        """Get the current UI scale factor"""
        return self.ui_scale
        
    def getFontScale(self):
        """Get the current font scale factor"""
        return self.font_scale
        
    def _getBaseFontSize(self):
        """Get the base font size from the application"""
        if self._base_font_size is None:
            if globals_.app:
                self._base_font_size = globals_.app.font().pointSize()
                if self._base_font_size <= 0:
                    self._base_font_size = 9  # Fallback default
            else:
                self._base_font_size = 9
        return self._base_font_size
        
    def generateScalingStyleSheet(self):
        """
        Generate a QSS stylesheet that applies the current scaling factors.
        
        For themes without stylesheets (like Classic), only font scaling is applied
        to avoid adding unwanted padding/margins to the native style.
        For themes with stylesheets, both font and widget scaling are applied.
        """
        # Check if theme has a stylesheet
        has_theme_stylesheet = bool(hasattr(globals_, 'theme') and 
                                    globals_.theme and 
                                    globals_.theme.styleSheet)
        
        base_font_size = self._getBaseFontSize()
        scaled_font_size = base_font_size * self.font_scale
        
        # For Classic theme (no stylesheet), apply minimal scaling
        # Only scale font and icon sizes - avoid padding/margins that break native style
        if not has_theme_stylesheet:
            # Calculate scaled icon size for Classic theme
            icon_size = int(16 * self.ui_scale)
            
            return f"""
                /* Minimal scaling for Classic theme (native style) */
                * {{
                    font-size: {scaled_font_size:.1f}pt;
                }}
                
                /* Scale checkbox/radio indicators */
                QCheckBox::indicator, QRadioButton::indicator {{
                    width: {icon_size}px;
                    height: {icon_size}px;
                }}
            """
        
        # For themes with stylesheets, apply full widget scaling
        # Calculate scaled dimensions
        padding_base = 4
        margin_base = 2
        spacing_base = 6
        icon_size_base = 16
        button_height_base = 24
        spinbox_height_base = 22
        
        # Apply UI scale
        padding = int(padding_base * self.ui_scale)
        margin = int(margin_base * self.ui_scale)
        spacing = int(spacing_base * self.ui_scale)
        icon_size = int(icon_size_base * self.ui_scale)
        button_height = int(button_height_base * self.ui_scale)
        spinbox_height = int(spinbox_height_base * self.ui_scale)
        
        # Build the full stylesheet with widget scaling
        stylesheet = f"""
            /* Global font scaling */
            * {{
                font-size: {scaled_font_size:.1f}pt;
            }}
            
            /* Widget padding and margins */
            QPushButton {{
                padding: {padding}px {padding * 2}px;
                min-height: {button_height}px;
            }}
            
            /* Toolbar buttons need specific sizing to scale properly */
            QToolBar QToolButton {{
                padding: {max(1, padding // 2)}px;
                margin: 0px;
                min-width: {icon_size + padding}px;
                min-height: {icon_size + padding}px;
                max-width: {icon_size + padding * 2}px;
                max-height: {icon_size + padding * 2}px;
            }}
            
            /* Toolbar comboboxes (Area selector, Patch selector) */
            QToolBar QComboBox {{
                padding: {max(1, padding // 2)}px;
                margin: 0px;
                min-height: {icon_size + padding}px;
                max-height: {icon_size + padding * 2}px;
            }}
            
            /* Regular tool buttons outside toolbars */
            QToolButton {{
                padding: {padding}px {padding * 2}px;
                min-height: {button_height}px;
            }}
            
            QComboBox {{
                padding: {padding}px;
                min-height: {spinbox_height}px;
            }}
            
            QSpinBox, QDoubleSpinBox {{
                padding: {padding}px;
                min-height: {spinbox_height}px;
            }}
            
            QLineEdit {{
                padding: {padding}px;
                min-height: {spinbox_height}px;
            }}
            
            QTextEdit, QPlainTextEdit {{
                padding: {padding}px;
            }}
            
            QGroupBox {{
                padding: {padding * 2}px;
                margin-top: {int(scaled_font_size * 1.5)}px;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 {padding}px;
            }}
            
            QTabWidget::pane {{
                padding: {padding}px;
            }}
            
            QTabBar::tab {{
                padding: {padding}px {padding * 2}px;
                min-height: {button_height}px;
            }}
            
            QListWidget, QTreeWidget, QTableWidget {{
                padding: {margin}px;
            }}
            
            QListWidget::item, QTreeWidget::item {{
                padding: {padding}px;
                min-height: {int(scaled_font_size * 1.5)}px;
            }}
            
            QCheckBox, QRadioButton {{
                spacing: {spacing}px;
            }}
            
            QCheckBox::indicator, QRadioButton::indicator {{
                width: {icon_size}px;
                height: {icon_size}px;
            }}
            
            /* QToolBar styling removed - causes double margins with toolbar widgets */
            
            QMenuBar {{
                padding: {margin}px;
            }}
            
            QMenuBar::item {{
                padding: {padding}px {padding * 2}px;
            }}
            
            QMenu {{
                padding: {margin}px;
            }}
            
            QMenu::item {{
                padding: {padding}px {padding * 4}px;
            }}
            
            QStatusBar {{
                padding: {margin}px;
            }}
            
            QDockWidget {{
                titlebar-close-icon: url(none);
                titlebar-normal-icon: url(none);
            }}
            
            QDockWidget::title {{
                padding: {padding}px;
            }}
        """
        
        return stylesheet
        
    def applyScaling(self):
        """
        Apply the current scaling factors to the application.
        
        For Classic theme (no stylesheet): Only font scaling via QApplication.setFont()
        For styled themes: Font scaling via QSS + widget scaling via QSS
        
        This approach avoids aggressive widget refresh which causes toolbar issues.
        """
        if not globals_.app:
            return
        
        # Check if theme has a stylesheet
        has_theme_stylesheet = bool(hasattr(globals_, 'theme') and 
                                    globals_.theme and 
                                    globals_.theme.styleSheet)
        
        # Update the base font size for the application
        # This works for ALL themes including Classic
        base_font_size = self._getBaseFontSize()
        scaled_font_size = base_font_size * self.font_scale
        
        app_font = globals_.app.font()
        app_font.setPointSizeF(scaled_font_size)
        globals_.app.setFont(app_font)
        
        # Update toolbar icon sizes on the main window
        # This is critical for proper toolbar scaling
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
            scaled_icon_size = int(16 * self.ui_scale)
            icon_size = QtCore.QSize(scaled_icon_size, scaled_icon_size)
            globals_.mainWindow.setIconSize(icon_size)
            
            # Also update any toolbars directly
            for toolbar in globals_.mainWindow.findChildren(QtWidgets.QToolBar):
                toolbar.setIconSize(icon_size)
        
        # Store the scaling stylesheet in the theme object so SetAppStyle can use it
        # This works for both Classic (minimal QSS) and styled themes (full QSS)
        if hasattr(globals_, 'theme') and globals_.theme:
            globals_.theme._scaling_qss = self.generateScalingStyleSheet()
        
        # Re-apply the app style with skip_style_reset=True to preserve toolbar margins
        # The style itself doesn't need to change, only the stylesheet
        from reggie.ui.ui import SetAppStyle
        SetAppStyle(skip_style_reset=True)
        
    def resetToDefaults(self):
        """Reset scaling to default values"""
        self.ui_scale = self.DEFAULT_UI_SCALE
        self.font_scale = self.DEFAULT_FONT_SCALE


class ScalingDialog(QtWidgets.QDialog):
    """
    Non-modal dialog for adjusting UI and font scaling with live preview.
    Uses debounced scaling to keep slider responsive while preventing UI freezing.
    """
    
    def __init__(self, parent=None):
        """Initialize the scaling dialog"""
        super().__init__(parent)
        
        self.scalingManager = globals_.scalingManager
        
        # Store original values for cancel/reset
        self.original_ui_scale = self.scalingManager.getUIScale()
        self.original_font_scale = self.scalingManager.getFontScale()
        
        # Debounce timer for smooth slider updates
        self.scaling_timer = QtCore.QTimer(self)
        self.scaling_timer.setSingleShot(True)
        self.scaling_timer.timeout.connect(self.applyDeferredScaling)
        self.debounce_delay = 700  # ms delay before applying scaling
        
        # Track pending scale values
        self.pending_ui_scale = None
        self.pending_font_scale = None
        
        self.setupUI()
        self.setWindowTitle("UI Scaling Settings")
        self.setModal(False)  # Non-modal for live preview
        
        # Update sliders to current values and enable states
        self.updateSlidersFromManager()
        self.updateSliderStates()
        
    def setupUI(self):
        """Set up the dialog UI"""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Description
        desc_label = QtWidgets.QLabel(
            "Adjust the UI scaling and font size to improve readability.\n"
            "Changes are applied immediately for preview."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Working indicator
        self.working_label = QtWidgets.QLabel("")
        self.working_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        layout.addWidget(self.working_label)
        
        layout.addSpacing(10)
        
        # UI Scale slider
        ui_scale_group = QtWidgets.QGroupBox("Widget Scale")
        ui_scale_layout = QtWidgets.QVBoxLayout(ui_scale_group)
        
        ui_scale_desc = QtWidgets.QLabel(
            "Scales buttons, icons, spacing, and other UI elements."
        )
        ui_scale_desc.setWordWrap(True)
        ui_scale_layout.addWidget(ui_scale_desc)
        
        ui_slider_layout = QtWidgets.QHBoxLayout()
        ui_slider_layout.addWidget(QtWidgets.QLabel("50%"))
        
        self.ui_scale_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.ui_scale_slider.setMinimum(int(ScalingManager.MIN_UI_SCALE * 100))
        self.ui_scale_slider.setMaximum(int(ScalingManager.MAX_UI_SCALE * 100))
        self.ui_scale_slider.setValue(int(self.scalingManager.getUIScale() * 100))
        self.ui_scale_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.ui_scale_slider.setTickInterval(25)
        self.ui_scale_slider.valueChanged.connect(self.onUIScaleChanged)
        ui_slider_layout.addWidget(self.ui_scale_slider)
        
        ui_slider_layout.addWidget(QtWidgets.QLabel("300%"))
        
        self.ui_scale_value_label = QtWidgets.QLabel("100%")
        self.ui_scale_value_label.setMinimumWidth(50)
        self.ui_scale_value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        ui_slider_layout.addWidget(self.ui_scale_value_label)
        
        ui_scale_layout.addLayout(ui_slider_layout)
        layout.addWidget(ui_scale_group)
        
        # Font Scale slider
        font_scale_group = QtWidgets.QGroupBox("Font Scale")
        font_scale_layout = QtWidgets.QVBoxLayout(font_scale_group)
        
        font_scale_desc = QtWidgets.QLabel(
            "Scales all text sizes independently from UI elements."
        )
        font_scale_desc.setWordWrap(True)
        font_scale_layout.addWidget(font_scale_desc)
        
        font_slider_layout = QtWidgets.QHBoxLayout()
        font_slider_layout.addWidget(QtWidgets.QLabel("50%"))
        
        self.font_scale_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.font_scale_slider.setMinimum(int(ScalingManager.MIN_FONT_SCALE * 100))
        self.font_scale_slider.setMaximum(int(ScalingManager.MAX_FONT_SCALE * 100))
        self.font_scale_slider.setValue(int(self.scalingManager.getFontScale() * 100))
        self.font_scale_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.font_scale_slider.setTickInterval(25)
        self.font_scale_slider.valueChanged.connect(self.onFontScaleChanged)
        font_slider_layout.addWidget(self.font_scale_slider)
        
        font_slider_layout.addWidget(QtWidgets.QLabel("300%"))
        
        self.font_scale_value_label = QtWidgets.QLabel("100%")
        self.font_scale_value_label.setMinimumWidth(50)
        self.font_scale_value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font_slider_layout.addWidget(self.font_scale_value_label)
        
        font_scale_layout.addLayout(font_slider_layout)
        layout.addWidget(font_scale_group)
        
        layout.addSpacing(10)
        
        # Preview note
        preview_note = QtWidgets.QLabel(
            "💡 Tip: Changes are applied immediately. "
            "Close this dialog to keep the changes, or click Reset to restore defaults."
        )
        preview_note.setWordWrap(True)
        preview_note.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        layout.addWidget(preview_note)
        
        layout.addSpacing(10)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        reset_button = QtWidgets.QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self.onResetClicked)
        button_layout.addWidget(reset_button)
        
        button_layout.addStretch()
        
        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.clicked.connect(self.onCancelClicked)
        button_layout.addWidget(cancel_button)
        
        ok_button = QtWidgets.QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.onOKClicked)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        self.setMinimumWidth(500)
        
    def updateSlidersFromManager(self):
        """Update slider positions from the scaling manager"""
        ui_value = int(self.scalingManager.getUIScale() * 100)
        font_value = int(self.scalingManager.getFontScale() * 100)
        
        self.ui_scale_slider.setValue(ui_value)
        self.font_scale_slider.setValue(font_value)
        
        # Update labels to match
        self.ui_scale_value_label.setText(f"{ui_value}%")
        self.font_scale_value_label.setText(f"{font_value}%")
    
    def updateSliderStates(self):
        """Update slider states - widget scaling now works for all themes"""
        # Widget scaling is now enabled for all themes
        # Classic theme uses minimal QSS (icons only)
        # Styled themes use full QSS (padding, margins, etc.)
        pass  # No need to disable anything
        
    def onUIScaleChanged(self, value):
        """Handle UI scale slider change - updates label and schedules deferred scaling"""
        # Update label immediately for responsive feedback
        self.ui_scale_value_label.setText(f"{value}%")
        
        # Store pending scale value
        self.pending_ui_scale = value / 100.0
        
        # Show working indicator and restart timer
        self.working_label.setText("⏳ Applying scaling...")
        self.scaling_timer.stop()
        self.scaling_timer.start(self.debounce_delay)
        
    def onFontScaleChanged(self, value):
        """Handle font scale slider change - updates label and schedules deferred scaling"""
        # Update label immediately for responsive feedback
        self.font_scale_value_label.setText(f"{value}%")
        
        # Store pending scale value
        self.pending_font_scale = value / 100.0
        
        # Show working indicator and restart timer
        self.working_label.setText("⏳ Applying scaling...")
        self.scaling_timer.stop()
        self.scaling_timer.start(self.debounce_delay)
    
    def applyDeferredScaling(self):
        """Apply pending scaling changes (called after debounce delay)"""
        # Apply any pending scale changes
        if self.pending_ui_scale is not None:
            self.scalingManager.setUIScale(self.pending_ui_scale)
            self.pending_ui_scale = None
            
        if self.pending_font_scale is not None:
            self.scalingManager.setFontScale(self.pending_font_scale)
            self.pending_font_scale = None
        
        # Apply the scaling
        self.scalingManager.applyScaling()
        
        # Clear working indicator
        self.working_label.setText("")
        
    def onResetClicked(self):
        """Reset to default scaling"""
        self.working_label.setText("⏳ Applying scaling...")
        QtCore.QCoreApplication.processEvents()  # Show label immediately
        self.scalingManager.resetToDefaults()
        self.updateSlidersFromManager()
        self.scalingManager.applyScaling()
        self.working_label.setText("")
        
    def onCancelClicked(self):
        """Cancel changes and restore original values only if they changed"""
        current_ui = self.scalingManager.getUIScale()
        current_font = self.scalingManager.getFontScale()
        
        # Only restore and apply if values actually changed
        if current_ui != self.original_ui_scale or current_font != self.original_font_scale:
            self.working_label.setText("⏳ Applying scaling...")
            QtCore.QCoreApplication.processEvents()  # Show label immediately
            self.scalingManager.setUIScale(self.original_ui_scale)
            self.scalingManager.setFontScale(self.original_font_scale)
            self.scalingManager.applyScaling()
        
        self.reject()
        
    def onOKClicked(self):
        """Accept changes and save settings"""
        self.scalingManager.saveSettings()
        self.accept()
        
    def closeEvent(self, event):
        """Handle dialog close - save settings"""
        self.scalingManager.saveSettings()
        super().closeEvent(event)
