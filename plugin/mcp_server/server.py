# -*- coding: utf-8 -*-
"""
Model Context Protocol (MCP) Server for STE Slicer tools.

Registers and executes tool handlers for:
- analyze_mesh_geometry
- select_print_mode_and_profile
- modify_scene_and_parameters
- run_slicing_and_generate_gcode
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger("MCPServer")


class MCPServer(object):
    """
    MCP Server managing registration, schema generation, and execution of slicer tools.
    """

    def __init__(self):
        # type: () -> None
        self._handlers = {}  # type: Dict[str, Any]
        self._register_default_tools()

    def register_tool(self, name, description, parameters, handler):
        # type: (str, str, Dict[str, Any], Any) -> None
        """Registers a tool with its schema and handler function."""
        self._handlers[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            },
            "handler": handler
        }

    def get_tools_schema(self):
        # type: () -> List[Dict[str, Any]]
        """Returns the list of tool definitions formatted for OpenAI API."""
        return [tool_info["schema"] for tool_info in self._handlers.values()]

    def call_tool(self, tool_name, arguments_json):
        # type: (str, Union[str, Dict[str, Any]]) -> Dict[str, Any]
        """
        Executes a registered tool by name with provided JSON arguments.

        Args:
            tool_name: Registered name of the tool.
            arguments_json: Arguments as JSON string or parsed dictionary.

        Returns:
            Dict[str, Any]: Execution result payload.
        """
        if tool_name not in self._handlers:
            err = "Unknown tool: '{0}'. Available tools: {1}".format(
                tool_name, list(self._handlers.keys())
            )
            logger.error(err)
            return {"status": "error", "error": err}

        if isinstance(arguments_json, str):
            try:
                args = json.loads(arguments_json) if arguments_json.strip() else {}
            except Exception as e:
                return {"status": "error", "error": "Invalid JSON arguments: {0}".format(e)}
        elif isinstance(arguments_json, dict):
            args = arguments_json
        else:
            args = {}

        handler = self._handlers[tool_name]["handler"]
        try:
            return handler(args)
        except Exception as e:
            logger.exception("Error executing tool '%s': %s", tool_name, e)
            return {"status": "error", "error": str(e)}

    def _register_default_tools(self):
        # type: () -> None
        """Registers the 4 mandatory pipeline tools."""
        self.register_tool(
            name="analyze_mesh_geometry",
            description="Анализирует геометрические характеристики 3D-модели (габариты, объем, нависания, толщину стенок и ориентацию).",
            parameters={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "Идентификатор или имя модели в сцене."
                    },
                    "model_path": {
                        "type": "string",
                        "description": "Путь к файлу 3D-модели (.stl, .3mf, .obj)."
                    }
                }
            },
            handler=self._default_analyze_mesh
        )

        self.register_tool(
            name="select_print_mode_and_profile",
            description="Выбирает режим печати (5D Multi-Axis или 3D Planar), базовый профиль качества и материал.",
            parameters={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["5D", "3D"],
                        "description": "Режим печати: '5D' (многоосевая печать) или '3D' (классическая трехосевая)."
                    },
                    "profile": {
                        "type": "string",
                        "description": "Имя профиля качества (например, '5D_structural', '5D_precision', '3D_standard')."
                    },
                    "material": {
                        "type": "string",
                        "description": "Имя материала филамента (например, 'PA6-CF', 'PETG', 'PLA', 'ABS', 'TPU')."
                    }
                },
                "required": ["mode", "profile", "material"]
            },
            handler=self._default_select_profile
        )

        self.register_tool(
            name="modify_scene_and_parameters",
            description="Применяет углы поворота детали и настраивает технологические параметры нарезки (температуры, стенки, заполнение, обдув).",
            parameters={
                "type": "object",
                "properties": {
                    "rotation_deg": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Углы поворота детали [rx, ry, rz] в градусах."
                    },
                    "layer_height_mm": {
                        "type": "number",
                        "description": "Высота слоя в миллиметрах (например, 0.2)."
                    },
                    "wall_line_count": {
                        "type": "integer",
                        "description": "Количество контуров/периметров стенок."
                    },
                    "infill_density_pct": {
                        "type": "number",
                        "description": "Плотность заполнения в процентах (0-100)."
                    },
                    "infill_pattern": {
                        "type": "string",
                        "description": "Рисунок заполнения ('gyroid', 'cubic', 'grid')."
                    },
                    "print_temperature_c": {
                        "type": "number",
                        "description": "Температура сопла экструдера в градусах Цельсия."
                    },
                    "bed_temperature_c": {
                        "type": "number",
                        "description": "Температура подогреваемого стола в градусах Цельсия."
                    },
                    "fan_speed_pct": {
                        "type": "number",
                        "description": "Скорость вентилятора охлаждения в процентах (0-100)."
                    },
                    "support_enabled": {
                        "type": "boolean",
                        "description": "Включить генерацию поддержек (False для Support-Free в 5D)."
                    }
                }
            },
            handler=self._default_modify_scene
        )

        self.register_tool(
            name="run_slicing_and_generate_gcode",
            description="Запускает процесс слайсинга в STE Slicer, рассчитывает время печати, расход нити и формирует G-код.",
            parameters={
                "type": "object",
                "properties": {
                    "export_gcode_path": {
                        "type": "string",
                        "description": "Необязательный путь для сохранения сгенерированного файла G-кода."
                    }
                }
            },
            handler=self._default_run_slicing
        )

    def _default_analyze_mesh(self, args):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        return {
            "status": "success",
            "model_id": args.get("model_id", "mesh_01"),
            "dimensions_mm": [60.0, 60.0, 25.0],
            "volume_cm3": 45.2,
            "has_overhangs": True,
            "max_overhang_angle_deg": 65.0,
            "is_rotational_symmetry": True,
            "recommended_mode": "5D",
            "message": "Геометрия успешно проанализирована: деталь содержит нависания 65° и тела вращения, рекомендуется 5D."
        }

    def _default_select_profile(self, args):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        return {
            "status": "success",
            "mode": args.get("mode", "5D"),
            "profile": args.get("profile", "5D_structural"),
            "material": args.get("material", "PA6-CF"),
            "message": "Выбран режим {0}, профиль '{1}', материал '{2}'.".format(
                args.get("mode", "5D"), args.get("profile", "5D_structural"), args.get("material", "PA6-CF")
            )
        }

    def _default_modify_scene(self, args):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        return {
            "status": "success",
            "applied_rotation_deg": args.get("rotation_deg", [0.0, 0.0, 0.0]),
            "applied_parameters": {
                "layer_height_mm": args.get("layer_height_mm", 0.2),
                "wall_line_count": args.get("wall_line_count", 4),
                "infill_density_pct": args.get("infill_density_pct", 50),
                "infill_pattern": args.get("infill_pattern", "gyroid"),
                "print_temperature_c": args.get("print_temperature_c", 275),
                "bed_temperature_c": args.get("bed_temperature_c", 90),
                "fan_speed_pct": args.get("fan_speed_pct", 0),
                "support_enabled": args.get("support_enabled", False)
            },
            "message": "Параметры сцены и технологические настройки слайсера успешно применены."
        }

    def _default_run_slicing(self, args):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        return {
            "status": "success",
            "slicing_result": "G-code successfully generated",
            "print_time_sec": 4200,
            "print_time_formatted": "1 ч 10 мин",
            "material_weight_g": 52.4,
            "filament_length_m": 16.8,
            "layer_count": 125,
            "mode_used": "5D",
            "message": "Слайсинг успешно завершен. Сгенерирован 5D G-код: время 1ч 10м, масса 52.4 г."
        }


__all__ = ["MCPServer"]
