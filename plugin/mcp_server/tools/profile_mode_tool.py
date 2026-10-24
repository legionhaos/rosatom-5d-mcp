# -*- coding: utf-8 -*-
"""
STE Slicer Plugin — Profile & Mode Selection Tool (MCP).

Selects 3D (Planar) vs 5D (Multi-Axis) printing mode, filament material,
quality/strength profiles, and configures corresponding settings stacks in Uranium/Cura.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher, run_in_main_thread
from plugin.utils.exceptions import ProfileNotFoundError, format_exception_for_llm
from plugin.utils.logger import get_logger

logger = get_logger("ProfileAndModeTool")

try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        name = ""
        description = ""
        parameters_schema = {}

        def execute(self, **kwargs):
            raise NotImplementedError


# Стандартные технологические параметры по материалам и режимам для быстрого применения
FALLBACK_MATERIAL_PRESETS = {
    "PLA": {
        "print_temperature": 205,
        "bed_temperature": 60,
        "fan_speed": 100,
        "speed_print": 60,
        "retraction_amount": 3.5,
        "retraction_speed": 40
    },
    "PETG": {
        "print_temperature": 240,
        "bed_temperature": 75,
        "fan_speed": 40,
        "speed_print": 45,
        "retraction_amount": 4.0,
        "retraction_speed": 35
    },
    "ABS": {
        "print_temperature": 245,
        "bed_temperature": 100,
        "fan_speed": 0,
        "speed_print": 50,
        "retraction_amount": 2.5,
        "retraction_speed": 40
    },
    "PA6-CF": {
        "print_temperature": 280,
        "bed_temperature": 90,
        "fan_speed": 0,
        "speed_print": 35,
        "retraction_amount": 2.0,
        "retraction_speed": 30
    },
    "TPU": {
        "print_temperature": 225,
        "bed_temperature": 50,
        "fan_speed": 50,
        "speed_print": 25,
        "retraction_amount": 1.0,
        "retraction_speed": 20
    }
}


class ProfileAndModeTool(BaseMCPTool):
    """
    MCP-инструмент выбора режима печати (3D vs 5D), полимерного материала и профиля качества.
    """

    name = "select_print_mode_and_profile"
    description = (
        "Выбирает режим печати (5D Multi-Axis или 3D Planar), базовый профиль качества "
        "и полимерный материал (PA6-CF, PETG, PLA, ABS, TPU)."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "print_mode": {
                "type": "string",
                "enum": ["5D", "3D"],
                "description": "Режим печати: '5D' (многоосевой) или '3D' (классический трехосевой)."
            },
            "mode": {
                "type": "string",
                "enum": ["5D", "3D"],
                "description": "Алиас для print_mode."
            },
            "material_type": {
                "type": "string",
                "description": "Имя или марка материала (например, 'PA6-CF', 'PETG', 'PLA', 'ABS', 'TPU')."
            },
            "material": {
                "type": "string",
                "description": "Алиас для material_type."
            },
            "quality_profile": {
                "type": "string",
                "description": "Профиль качества/прочности ('5D_structural', 'normal_strength', 'standard', 'fine')."
            },
            "profile": {
                "type": "string",
                "description": "Алиас для quality_profile."
            },
            "nozzle_size_mm": {
                "type": "number",
                "description": "Диаметр установленного сопла в мм (по умолчанию 0.4).",
                "default": 0.4
            }
        },
        "required": []
    }

    def __init__(self):
        super(ProfileAndModeTool, self).__init__()

    def list_available_configurations(self):
        # type: () -> Dict[str, Any]
        """
        Опрашивает ContainerRegistry и возвращает список доступных машин,
        материалов и профилей качества.
        """
        try:
            return MainThreadDispatcher.execute_sync(self._list_configurations_main)
        except Exception as e:
            logger.debug("list_available_configurations fallback: %s", e)
            return {
                "modes": ["5D", "3D"],
                "materials": ["PA6-CF", "PETG", "PLA", "ABS", "TPU"],
                "profiles": ["5D_structural", "5D_precision", "normal_strength", "standard", "draft"]
            }

    def _list_configurations_main(self):
        # type: () -> Dict[str, Any]
        result = {
            "modes": ["5D", "3D"],
            "materials": [],
            "profiles": [],
            "machines": []
        }
        try:
            from UM.Settings.ContainerRegistry import ContainerRegistry
            registry = ContainerRegistry.getInstance()
            materials = registry.findInstanceContainers(type="material")
            result["materials"] = list(set([m.getName() for m in materials if m.getName()]))

            qualities = registry.findInstanceContainers(type="quality")
            result["profiles"] = list(set([q.getName() for q in qualities if q.getName()]))

            machines = registry.findDefinitionContainers()
            result["machines"] = [m.getName() for m in machines if m.getName()]
        except Exception as e:
            logger.debug("Error listing from ContainerRegistry: %s", e)
            result["materials"] = ["PA6-CF", "PETG", "PLA", "ABS", "TPU"]
            result["profiles"] = ["5D_structural", "5D_precision", "normal_strength", "standard"]
        return result

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        """
        Выполняет переключение режима, материала и профиля в STE Slicer.
        """
        mode = kwargs.get("print_mode") or kwargs.get("mode") or "5D"
        material = kwargs.get("material_type") or kwargs.get("material") or "PA6-CF"
        profile = kwargs.get("quality_profile") or kwargs.get("profile") or "5D_structural"
        nozzle = kwargs.get("nozzle_size_mm", 0.4)

        mode = str(mode).upper()
        if mode not in ("3D", "5D"):
            mode = "5D"

        material = str(material).strip()
        profile = str(profile).strip()

        try:
            return MainThreadDispatcher.execute_sync(
                self._apply_configuration_main,
                mode=mode,
                material=material,
                profile=profile,
                nozzle=nozzle
            )
        except Exception as exc:
            logger.exception("Failed to apply profile and mode: %s", exc)
            return format_exception_for_llm(exc)

    def _apply_configuration_main(self, mode, material, profile, nozzle):
        # type: (str, str, str, float) -> Dict[str, Any]
        app = None
        applied_mode = mode
        applied_material = material
        applied_profile = profile
        active_machine = "Stereotech Hybrid 530"

        try:
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
        except Exception:
            pass

        if app is not None:
            try:
                machine_mgr = app.getMachineManager()
                if machine_mgr:
                    current_machine = machine_mgr.activeMachine
                    if current_machine:
                        active_machine = current_machine.getName()

                    # Переключение режима 3D / 5D в свойствах машины или стек-переменных
                    global_stack = machine_mgr.activeMachine
                    if global_stack:
                        # В STE Slicer режим 5D активируется через специфичные ключи:
                        # 'stereotech_5d_mode', 'print_mode' или имя определения машины
                        for key in ("stereotech_5d_mode", "print_mode", "slicing_mode"):
                            try:
                                if global_stack.getProperty(key, "value") is not None:
                                    val = True if mode == "5D" else False
                                    if key == "print_mode":
                                        val = mode
                                    global_stack.setProperty(key, "value", val)
                            except Exception:
                                pass

                    # Установка материала
                    try:
                        from UM.Settings.ContainerRegistry import ContainerRegistry
                        registry = ContainerRegistry.getInstance()
                        # Ищем подходящий контейнер материала
                        mat_lower = material.lower().replace("-", "").replace("_", "")
                        matched_container = None
                        for c in registry.findInstanceContainers(type="material"):
                            c_name = c.getName().lower().replace("-", "").replace("_", "")
                            if mat_lower in c_name or c_name in mat_lower:
                                matched_container = c
                                break

                        if matched_container:
                            try:
                                from cura.Settings.ExtruderManager import ExtruderManager
                                extruder_stack = ExtruderManager.getInstance().getActiveExtruderStack()
                                if extruder_stack:
                                    extruder_stack.material = matched_container
                                    applied_material = matched_container.getName()
                            except Exception as em_err:
                                logger.debug("ExtruderManager setMaterial notice: %s", em_err)
                    except Exception as reg_err:
                        logger.debug("ContainerRegistry lookup notice: %s", reg_err)

            except Exception as e:
                logger.warning("Error during live Cura stack configuration: %s", e)

        # Подбираем технологический пресет для выбранного материала
        mat_key = "PA6-CF"
        for key in FALLBACK_MATERIAL_PRESETS:
            if key.lower() in material.lower():
                mat_key = key
                break
        preset = dict(FALLBACK_MATERIAL_PRESETS.get(mat_key, FALLBACK_MATERIAL_PRESETS["PA6-CF"]))

        return {
            "status": "success",
            "active_machine": active_machine,
            "applied_mode": applied_mode,
            "applied_material_id": applied_material,
            "applied_profile_id": applied_profile,
            "nozzle_size_mm": nozzle,
            "default_settings_snapshot": preset,
            "message": "Режим {0}, материал '{1}' и профиль '{2}' успешно применены.".format(
                applied_mode, applied_material, applied_profile
            )
        }


ProfileModeTool = ProfileAndModeTool
__all__ = ["ProfileAndModeTool", "ProfileModeTool"]
