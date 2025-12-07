"""
Quick Paint Tool (QPT) - A smooth, intuitive terrain painting tool for Reggie.
"""

from .core.brush import SmartBrush
from .core.presets import PresetManager

__version__ = '1.0.0'
__all__ = [
    'SmartBrush',
    'PresetManager',
]
