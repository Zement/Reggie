from PyQt6 import QtGui, QtWidgets, QtCore
from xml.etree import ElementTree
import os

from reggie.core import globals_
from reggie.core.dirty import setting

# Lazy QColor creation to avoid creating Qt objects before QApplication exists
_color_cache = {}

def _make_color(*args):
    """Create a QColor, caching the result"""
    key = args
    if key not in _color_cache:
        _color_cache[key] = QtGui.QColor(*args)
    return _color_cache[key]

def LoadTheme():
    """
    Loads the theme
    """
    globals_.theme = ReggieTheme(setting("Theme", "Classic"))

class ReggieTheme:
    """
    Class that represents a Reggie theme
    """

    def __init__(self, folder=None):
        """
        Initializes the theme
        """
        self.initAsClassic()
        if folder and folder != "Classic": self.initFromFolder(folder)

    def initAsClassic(self):
        """
        Initializes the theme as the hardcoded Classic theme
        """
        self.fileName = 'Classic'
        self.styleSheet = ''
        self.formatver = 1.0
        self.version = 1.0
        self.themeName = globals_.trans.string('Themes', 0)
        self.creator = globals_.trans.string('Themes', 1)
        self.description = globals_.trans.string('Themes', 2)
        self.iconCacheSm = {}
        self.iconCacheLg = {}
        self.style = None
        self.forceUiColor = False
        self.forceStyleSheet = False

        # Don't create colors dict yet - do it lazily
        self._colors = None

    def _init_colors(self):
        """Initialize colors lazily after QApplication is created"""
        if self._colors is not None:
            return
        
        # Add the colors (created lazily after QApplication is created)
        # Descriptions:
        self._colors = {
            'bg': _make_color(119, 136, 153),  # Main scene background fill
            'comment_fill': _make_color(220, 212, 135, 120),  # Unselected comment fill
            'comment_fill_s': _make_color(254, 240, 240, 240),  # Selected comment fill
            'comment_lines': _make_color(192, 192, 192, 120),  # Unselected comment lines
            'comment_lines_s': _make_color(220, 212, 135, 240),  # Selected comment lines
            'entrance_fill': _make_color(190, 0, 0, 120),  # Unselected entrance fill
            'entrance_fill_s': _make_color(190, 0, 0, 240),  # Selected entrance fill
            'entrance_lines': _make_color(0, 0, 0),  # Unselected entrance lines
            'entrance_lines_s': _make_color(255, 255, 255),  # Selected entrance lines
            'grid': _make_color(255, 255, 255, 100),  # Grid
            'location_fill': _make_color(114, 42, 188, 70),  # Unselected location fill
            'location_fill_s': _make_color(170, 128, 215, 100),  # Selected location fill
            'location_lines': _make_color(0, 0, 0),  # Unselected location lines
            'location_lines_s': _make_color(255, 255, 255),  # Selected location lines
            'location_text': _make_color(255, 255, 255),  # Location text
            'object_fill_s': _make_color(255, 255, 255, 64),  # Select object fill
            'object_lines_s': _make_color(255, 255, 255),  # Selected object lines
            'object_lines_r': _make_color(0, 148, 255),  # Clicked object corner
            'overview_entrance': _make_color(255, 0, 0),  # Overview entrance fill
            'overview_location_fill': _make_color(114, 42, 188, 50),  # Overview location fill
            'overview_location_lines': _make_color(0, 0, 0),  # Overview location lines
            'overview_object': _make_color(255, 255, 255),  # Overview object fill
            'overview_sprite': _make_color(0, 92, 196),  # Overview sprite fill
            'overview_viewbox': _make_color(0, 0, 255),  # Overview background fill
            'overview_zone_fill': _make_color(47, 79, 79, 120),  # Overview zone fill
            'overview_zone_lines': _make_color(0, 255, 255),  # Overview zone lines
            'overview_path': _make_color(6, 249, 20),  # Overview path fill
            'path_connector': _make_color(6, 249, 20),  # Path node connecting lines
            'path_fill': _make_color(6, 249, 20, 120),  # Unselected path node fill
            'path_fill_s': _make_color(6, 249, 20, 240),  # Selected path node fill
            'path_lines': _make_color(0, 0, 0),  # Unselected path node lines
            'path_lines_s': _make_color(255, 255, 255),  # Selected path node lines
            'smi': _make_color(255, 255, 255, 80),  # Sprite movement indicator
            'sprite_fill_s': _make_color(255, 255, 255, 64),  # Selected sprite w/ image fill
            'sprite_lines_s': _make_color(255, 255, 255),  # Selected sprite w/ image lines
            'spritebox_fill': _make_color(0, 92, 196, 120),  # Unselected sprite w/o image fill
            'spritebox_fill_s': _make_color(0, 92, 196, 240),  # Selected sprite w/o image fill
            'spritebox_lines': _make_color(0, 0, 0),  # Unselected sprite w/o image fill
            'spritebox_lines_s': _make_color(255, 255, 255),  # Selected sprite w/o image fill
            'zone_entrance_helper': _make_color(190, 0, 0, 120),  # Zone entrance-placement left border indicator
            'zone_lines': _make_color(145, 200, 255, 176),  # Zone lines
            'zone_corner': _make_color(255, 255, 255),  # Zone grabbers/corners
            'zone_dark_fill': _make_color(0, 0, 0, 48),  # Zone fill when dark
            'zone_text': _make_color(44, 64, 84),  # Zone text
        }

    @property
    def colors(self):
        """Lazy-load colors dictionary"""
        self._init_colors()
        return self._colors

    def initFromFolder(self, folder):
        """
        Initializes the theme from the folder
        """
        folder = os.path.join('reggiedata', 'themes', folder)

        try:
            fileList = os.listdir(folder)
        except FileNotFoundError:
            # Return if the theme cannot be found
            # (default theme is already inited)
            return

        # Create a XML ElementTree
        maintree = ElementTree.parse(os.path.join(folder, 'main.xml'))
        root = maintree.getroot()

        # Parse the attributes of the <theme> tag
        if not self.parseMainXMLHead(root):
            # The attributes are messed up
            return

        # Parse the other nodes
        for node in root:
            if node.tag.lower() == 'colors':
                if 'file' not in node.attrib: continue

                # Load the colors XML
                self.loadColorsXml(os.path.join(folder, node.attrib['file']))

            elif node.tag.lower() == 'qss':
                if 'file' not in node.attrib: continue

                # Load the style sheet
                self.loadStyleSheet(os.path.join(folder, node.attrib['file']))

            elif node.tag.lower() == 'icons':
                if not all(thing in node.attrib for thing in ['size', 'folder']): continue

                foldername = node.attrib['folder']
                big = node.attrib['size'].lower()[:2] == 'lg'
                cache = self.iconCacheLg if big else self.iconCacheSm

                # Load the icons
                for iconfilename in fileList:
                    iconname = iconfilename
                    if not iconname.startswith(foldername + os.sep): continue
                    iconname = iconname[len(foldername) + 1:]
                    if len(iconname) <= len('icon-.png'): continue
                    if not iconname.startswith('icon-') or not iconname.endswith('.png'): continue
                    iconname = iconname[len('icon-'): -len('.png')]

                    with open(os.path.join(folder, iconfilename), "rb") as inf:
                        icodata = inf.read()
                    pix = QtGui.QPixmap()
                    if not pix.loadFromData(icodata): continue
                    ico = QtGui.QIcon(pix)

                    cache[iconname] = ico

    def parseMainXMLHead(self, root):
        """
        Parses the main attributes of main.xml
        """
        MaxSupportedXMLVersion = 1.0
        self.styleSheet = ''

        # Check for required attributes
        if root.tag.lower() != 'theme': return False
        if 'format' in root.attrib:
            formatver = root.attrib['format']
            try:
                self.formatver = float(formatver)
            except ValueError:
                return False
        else:
            return False

        if self.formatver > MaxSupportedXMLVersion:
            return False

        if 'name' in root.attrib:
            self.themeName = root.attrib['name']
        else:
            return False

        # Check for optional attributes
        self.creator = root.get("creator", globals_.trans.string("Themes", 3))
        self.description = root.get("description", globals_.trans.string("Themes", 4))
        self.style = root.get("style")
        self.forceUiColor = root.get("forceUiColor", "false") == "true"
        self.forceStyleSheet = root.get("forceStyleSheet", "false") == "true"

        try:
            self.version = float(root.get("version", "1.0"))
        except ValueError:
            self.version = 1.0

        return True

    def loadColorsXml(self, file):
        """
        Loads a colors.xml file
        """
        try:
            tree = ElementTree.parse(file)
        except Exception:
            return

        root = tree.getroot()
        if root.tag.lower() != 'colors': return False

        colorDict = {}
        for colorNode in root:
            if colorNode.tag.lower() != 'color': continue
            if not all(thing in colorNode.attrib for thing in ['id', 'value']): continue

            colorval = colorNode.attrib['value']
            if colorval.startswith('#'): colorval = colorval[1:]
            a = 255
            try:
                if len(colorval) == 3:
                    # RGB
                    r = int(colorval[0], 16)
                    g = int(colorval[1], 16)
                    b = int(colorval[2], 16)
                elif len(colorval) == 4:
                    # RGBA
                    r = int(colorval[0], 16)
                    g = int(colorval[1], 16)
                    b = int(colorval[2], 16)
                    a = int(colorval[3], 16)
                elif len(colorval) == 6:
                    # RRGGBB
                    r = int(colorval[0:2], 16)
                    g = int(colorval[2:4], 16)
                    b = int(colorval[4:6], 16)
                elif len(colorval) == 8:
                    # RRGGBBAA
                    r = int(colorval[0:2], 16)
                    g = int(colorval[2:4], 16)
                    b = int(colorval[4:6], 16)
                    a = int(colorval[6:8], 16)
            except ValueError:
                continue
            colorobj = QtGui.QColor(r, g, b, a)
            colorDict[colorNode.attrib['id']] = colorobj

        # Merge dictionaries
        self.colors.update(colorDict)

    def loadStyleSheet(self, file):
        """
        Loads a style.qss file
        """
        with open(file, 'r', encoding='utf-8') as inf:
            style = inf.read()

        self.styleSheet = style

    def color(self, name):
        """
        Returns a color
        """
        try:
            return self.colors[name]

        except KeyError:
            return None

    def GetIcon(self, name, big=False):
        """
        Returns an icon
        """

        cache = self.iconCacheLg if big else self.iconCacheSm

        if name not in cache:
            # Always use PNG for QIcon - .icns files crash PyQt6 on macOS ARM64
            # The native dock icon is handled by the .icns in the app bundle
            path = os.path.join('reggiedata', 'ico', 'lg' if big else 'sm', 'icon-')
            path += name
            cache[name] = QtGui.QIcon(path)

        return cache[name]


class IconsOnlyTabBar(QtWidgets.QTabBar):
    """
    A QTabBar subclass that is designed to only display icons.

    On macOS Mojave (and probably other versions around there),
    QTabWidget tabs are way too wide when only displaying icons.
    This ultimately causes the Reggie palette itself to have a really
    high minimum width.

    This subclass limits tab widths to fix the problem.
    """
    def tabSizeHint(self, index):
        res = super(IconsOnlyTabBar, self).tabSizeHint(index)
        if globals_.app.style().metaObject().className() == 'QMacStyle':
            res.setWidth(res.height() * 2)
        return res

# Related functions
def SetAppStyle(styleKey='', skip_style_reset=False):
    """
    Set the application window color
    
    Args:
        styleKey: The style key to use (e.g. "Fusion")
        skip_style_reset: If True, skip recreating the style (for scaling updates only)
    """
    # Change the color if applicable
    if globals_.theme.color('ui') is not None and not globals_.theme.forceStyleSheet:
        globals_.app.setPalette(QtGui.QPalette(globals_.theme.color('ui')))

    # Change the style (skip if only updating scaling to preserve toolbar margins)
    if not skip_style_reset:
        if not styleKey: styleKey = setting('uiStyle', "Fusion")
        style = QtWidgets.QStyleFactory.create(styleKey)
        globals_.app.setStyle(style)

    # Build the complete stylesheet
    final_qss = ""
    
    # Apply the theme style sheet, if exists
    if globals_.theme.styleSheet:
        final_qss = globals_.theme.styleSheet

    # Manually set the background color if needed
    if globals_.theme.forceUiColor and not globals_.theme.forceStyleSheet:
        color = globals_.theme.color('ui').getRgb()
        bgColor = "#%02x%02x%02x" % tuple(map(lambda x: x // 2, color[:3]))
        bg_qss = """
            QListView, QTreeWidget, QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit, QPlainTextEdit{
                background-color: %s;
            }""" % bgColor
        final_qss = final_qss + "\n" + bg_qss if final_qss else bg_qss
    
    # Append scaling stylesheet if it exists
    if hasattr(globals_.theme, '_scaling_qss') and globals_.theme._scaling_qss:
        final_qss = final_qss + "\n" + globals_.theme._scaling_qss if final_qss else globals_.theme._scaling_qss

    # Fix disabled menubar items being nearly unreadable in some cases
    # (mainly in dark mode and/or when the UI color is overridden)
    disabled_qss = "QMenu::item:disabled{color: #646464;}"
    final_qss = final_qss + "\n" + disabled_qss if final_qss else disabled_qss

    # Apply the complete stylesheet
    if final_qss:
        globals_.app.setStyleSheet(final_qss)


def SetColorScheme():
    """
    Toggle the application-wide native light/dark color scheme, independent
    of the current theme.
    """
    if globals_.DarkMode:
        globals_.app.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Dark)
    else:
        globals_.app.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)


def GetIcon(name, big=False):
    """
    Helper function to grab a specific icon
    """
    return globals_.theme.GetIcon(name, big)


def createHorzLine():
    f = QtWidgets.QFrame()
    f.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)
    return f


def createVertLine():
    f = QtWidgets.QFrame()
    f.setFrameStyle(QtWidgets.QFrame.Shape.VLine | QtWidgets.QFrame.Shadow.Sunken)
    return f


def LoadNumberFont():
    """
    Creates a valid font we can use to display the item numbers
    """
    if globals_.NumberFont is not None: return

    # this is a really crappy method, but I can't think of any other way
    # normal Qt defines Q_WS_WIN and Q_WS_MAC but we don't have that here
    s = QtCore.QSysInfo()
    if hasattr(s, 'WindowsVersion'):
        globals_.NumberFont = QtGui.QFont('Tahoma', 7)
    elif hasattr(s, 'MacintoshVersion'):
        globals_.NumberFont = QtGui.QFont('Lucida Grande', 9)
    else:
        globals_.NumberFont = QtGui.QFont('Sans', 8)


def clipStr(text, idealWidth, font=None):
    """
    Returns a shortened string, or None if it need not be shortened
    """
    if font is None: font = QtGui.QFont()
    width = QtGui.QFontMetrics(font).horizontalAdvance(text)
    if width <= idealWidth: return None

    # note that Qt has a builtin function for this:
    # QFontMetricsF::elidedText(text, Qt.TextElideMode.ElideNone, idealWidth)
    while width > idealWidth:
        text = text[:-1]
        width = QtGui.QFontMetrics(font).horizontalAdvance(text)

    return text


class HexSpinBox(QtWidgets.QSpinBox):
    class HexValidator(QtGui.QValidator):
        def __init__(self, min, max):
            QtGui.QValidator.__init__(self)
            self.valid = set('0123456789abcdef')
            self.min = min
            self.max = max

        def validate(self, input, pos):
            try:
                input = str(input).lower()
            except Exception:
                return (self.State.Invalid, input, pos)
            valid = self.valid

            for char in input:
                if char not in valid:
                    return (self.State.Invalid, input, pos)

            try:
                value = int(input, 16)
            except ValueError:
                # If value == '' it raises ValueError
                return (self.State.Invalid, input, pos)

            if value < self.min or value > self.max:
                return (self.State.Intermediate, input, pos)

            return (self.State.Acceptable, input, pos)

    def __init__(self, format='%04X', *args):
        self.format = format
        QtWidgets.QSpinBox.__init__(self, *args)
        self.validator = self.HexValidator(self.minimum(), self.maximum())

    def setMinimum(self, value):
        self.validator.min = value
        QtWidgets.QSpinBox.setMinimum(self, value)

    def setMaximum(self, value):
        self.validator.max = value
        QtWidgets.QSpinBox.setMaximum(self, value)

    def setRange(self, min, max):
        self.validator.min = min
        self.validator.max = max
        QtWidgets.QSpinBox.setMinimum(self, min)
        QtWidgets.QSpinBox.setMaximum(self, max)

    def validate(self, text, pos):
        return self.validator.validate(text, pos)

    def textFromValue(self, value):
        return self.format % value

    def valueFromText(self, value):
        return int(str(value), 16)


class ListWidgetWithToolTipSignal(QtWidgets.QListWidget):
    """
    A QtWidgets.QListWidget that includes a signal that
    is emitted when a tooltip is about to be shown. Useful
    for making tooltips that update every time you show
    them.
    """
    toolTipAboutToShow = QtCore.pyqtSignal(QtWidgets.QListWidgetItem)

    def viewportEvent(self, e):
        """
        Handles viewport events
        """
        if e.type() == e.Type.ToolTip:
            item = self.itemFromIndex(self.indexAt(e.pos()))
            if item is not None:
                self.toolTipAboutToShow.emit(item)

        return super().viewportEvent(e)


# Key combinations that must never be rebound. OS-reserved combos would
# shadow window management; the bare keys are claimed by the Quick Paint
# Tool's raw key hook (see reggie/plugins/quickpaint/reggie_hook.py).
OS_RESERVED_KEYBINDS = ('Alt+F4', 'Alt+Tab', 'Ctrl+Esc')
QPT_RESERVED_KEYBINDS = ('Q', 'S', 'C', 'E', 'F', 'D', 'F1', 'F2', 'F3', 'Esc')


class KeybindLineEdit(QtWidgets.QKeySequenceEdit):
    """
    A wrapper for QtWidgets.QKeySequenceEdit
    """
    def __init__(self, keySequence=None, name=str, siblings=None):
        QtWidgets.QKeySequenceEdit.__init__(self, keySequence)
        self.name = name

        # Every KeybindLineEdit in the same editor, so a newly entered sequence
        # can be checked against the others. A duplicate makes both shortcuts
        # ambiguous, and Qt responds by firing neither - which is how the
        # shipped Ctrl+Shift+S collision between "Save As" and "Shift Items"
        # made both look broken.
        self.siblings = siblings if siblings is not None else []

        # Only record one sequence input
        self.setMaximumSequenceLength(1)

        self.setClearButtonEnabled(True)

        # Set placeholder text on the QLineEdit
        lineEdit = self.findChild(QtWidgets.QLineEdit, "qt_keysequenceedit_lineedit")
        if lineEdit: lineEdit.setPlaceholderText(globals_.trans.string('PrefsDlg', 60)) # No keybind set

        # Reject reserved combos as they are entered
        self.keySequenceChanged.connect(self._validateSequence)

    def _validateSequence(self, keySequence):
        """
        Clears the entered sequence if it is reserved by the OS or the
        Quick Paint Tool, and tells the user why
        """
        seq_str = keySequence.toString()
        if not seq_str:
            return

        if seq_str in OS_RESERVED_KEYBINDS:
            message = globals_.trans.string('PrefsDlg', 69)
        elif seq_str in QPT_RESERVED_KEYBINDS:
            message = globals_.trans.string('PrefsDlg', 70)
        else:
            clash = self._findClash(seq_str)
            if clash is None:
                return
            message = ('%s is already used by "%s". A shortcut assigned twice '
                       'makes both ambiguous, and neither will fire.'
                       % (seq_str, clash))

        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)
        QtWidgets.QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)

    def _findClash(self, seq_str):
        """
        Returns the display label of a sibling already bound to seq_str, or None.
        """
        for other in self.siblings:
            if other is self:
                continue
            if other.keySequence().toString() != seq_str:
                continue
            return getattr(other, 'label', None) or other.name
        return None

    def keyPressEvent(self, event):
        """
        Clears the current keybind if Delete or Backspace is pressed, and
        records numpad keys as numpad keys.
        """
        key = event.key()

        if key in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            QtWidgets.QKeySequenceEdit.keyPressEvent(self, event)
            self.clear()
            return

        # QKeySequenceEdit drops KeypadModifier: typing numpad-1 records plain
        # '1', identical to the top row. That makes the shipped Num+1..Num+9
        # hotbar defaults impossible to re-enter, and silently rewrites one to
        # the top-row key if a user retypes it. Qt is otherwise fine with them
        # - QKeySequence('Num+1') round-trips, and an action bound to it fires
        # only on the numpad - so the sequence is built here instead.
        modifiers = event.modifiers()
        if modifiers & QtCore.Qt.KeyboardModifier.KeypadModifier:
            # Bare modifier presses have no sequence of their own.
            if key in (QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift,
                       QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Meta):
                return

            combined = key
            for flag in (QtCore.Qt.KeyboardModifier.ControlModifier,
                         QtCore.Qt.KeyboardModifier.ShiftModifier,
                         QtCore.Qt.KeyboardModifier.AltModifier,
                         QtCore.Qt.KeyboardModifier.MetaModifier,
                         QtCore.Qt.KeyboardModifier.KeypadModifier):
                if modifiers & flag:
                    combined |= flag.value

            self.setKeySequence(QtGui.QKeySequence(combined))
            event.accept()
            return

        QtWidgets.QKeySequenceEdit.keyPressEvent(self, event)
