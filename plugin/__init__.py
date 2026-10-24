# -*- coding: utf-8 -*-
"""
STE AI 3D/5D Print Assistant plugin for STE Slicer (Cura 3.6 / Uranium).

Entry point for Uranium PluginRegistry:
- getMetaData(): returns plugin metadata dictionary.
- register(app): initializes and returns the STEAIExtension instance.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
import types

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# Когда плагин загружается в STE Slicer под именем STEAIAssistant (или любым другим),
# регистрируем модуль 'plugin' в sys.modules, чтобы все внутренние вызовы
# (from plugin.xxx import yyy) прозрачно находили компоненты внутри этой папки.
if "plugin" not in sys.modules:
    plugin_mod = types.ModuleType("plugin")
    plugin_mod.__path__ = [_current_dir]
    plugin_mod.__file__ = os.path.join(_current_dir, "__init__.py")
    sys.modules["plugin"] = plugin_mod
elif hasattr(sys.modules["plugin"], "__path__") and _current_dir not in sys.modules["plugin"].__path__:
    sys.modules["plugin"].__path__.insert(0, _current_dir)

# Относительный импорт главного класса расширения
from .slicer_bridge.extension import STEAIExtension


def getMetaData():
    # type: () -> dict
    """
    Метаданные плагина. Метаданные автоматически считываются Uranium из plugin.json.
    """
    return {}


def register(app):
    # type: (object) -> dict
    """
    Главная точка инициализации расширения в Uranium/STE Slicer.

    Args:
        app: Экземпляр SteSlicerApplication / CuraApplication.

    Returns:
        dict: Словарь с зарегистрированным расширением {"extension": STEAIExtension(app)}.
    """
    return {
        "extension": STEAIExtension(application=app)
    }


__all__ = ["getMetaData", "register", "STEAIExtension"]
