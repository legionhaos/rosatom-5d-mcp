# -*- coding: utf-8 -*-
"""
STE AI 3D/5D Print Assistant plugin for STE Slicer (Cura 3.6 / Uranium).

Entry point for Uranium PluginRegistry:
- getMetaData(): returns plugin metadata dictionary.
- register(app): initializes and returns the STEAIExtension instance.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import sys
from typing import Any, Dict

# Гарантируем присутствие корня плагина и проекта в sys.path для надежности импортов
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from plugin.slicer_bridge.extension import STEAIExtension


def getMetaData():
    # type: () -> Dict[str, Any]
    """
    Возвращает словарь метаданных плагина для Uranium PluginRegistry.
    Если рядом лежит plugin.json, считывает информацию из него.
    """
    json_path = os.path.join(_current_dir, "plugin.json")
    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            pass

    return {
        "name": "STE AI 3D/5D Print Assistant",
        "author": "Hackathon Team",
        "version": "1.0.0",
        "description": "Интеллектуальный сервис автоподбора параметров FDM 3D/5D-печати с чат-ботом и MCP-инструментами",
        "api": 5,
        "supported_sdk_versions": ["4.0.0", "5.0.0", "6.0.0"],
        "plugin": {}
    }


def register(app):
    # type: (Any) -> Dict[str, Any]
    """
    Главная точка инициализации расширения в Uranium/Cura.

    Args:
        app: Экземпляр CuraApplication.

    Returns:
        Dict[str, Any]: Словарь зарегистрированных объектов расширения.
    """
    extension = STEAIExtension(application=app)
    return {
        "extension": extension
    }


__all__ = ["getMetaData", "register", "STEAIExtension"]
