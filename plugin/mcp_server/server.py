# -*- coding: utf-8 -*-
"""
Model Context Protocol (MCP) Server for STE Slicer tools.

Registers and executes tool handlers for:
- analyze_mesh_geometry
- select_print_mode_and_profile
- modify_scene_and_parameters
- run_slicing_and_generate_gcode
- validate_and_export_artifacts
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
from typing import Any, Dict, List, Optional, Union

from plugin.utils.logger import STEPluginLogger, get_logger
from plugin.utils.exceptions import (
    MCPToolExecutionError,
    ToolArgumentError,
    format_exception_for_llm,
)

logger = get_logger("MCPServer")


class BaseMCPTool(object):
    """
    Абстрактный базовый класс инструмента Model Context Protocol (MCP).
    """
    name = ""
    description = ""
    parameters_schema = {}  # type: Dict[str, Any]

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        raise NotImplementedError("Subclasses must implement execute()")


class MCPServer(object):
    """
    MCP Server managing registration, JSON Schema generation, and execution of slicer tools.
    """

    def __init__(self, dispatcher=None, event_listener=None, settings_mgr=None):
        # type: (Optional[Any], Optional[Any], Optional[Any]) -> None
        self._dispatcher = dispatcher
        self._event_listener = event_listener
        self._settings_mgr = settings_mgr
        self._tools = {}  # type: Dict[str, BaseMCPTool]
        self._handlers = {}  # type: Dict[str, Dict[str, Any]]

        self._register_target_tools()

    def register_tool(self, tool_instance_or_name=None, description=None, parameters=None, handler=None, **kwargs):
        # type: (Union[BaseMCPTool, str, None], Optional[str], Optional[Dict[str, Any]], Optional[Any], Any) -> None
        """
        Регистрирует инструмент MCP как экземпляр BaseMCPTool либо через (name, description, params, handler).
        """
        tool_instance = kwargs.get("tool_instance")
        if tool_instance_or_name is not None and isinstance(tool_instance_or_name, BaseMCPTool):
            tool_instance = tool_instance_or_name

        if isinstance(tool_instance, BaseMCPTool):
            tool = tool_instance
            self._tools[tool.name] = tool
            self._handlers[tool.name] = {
                "schema": {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema
                    }
                },
                "handler": lambda args: tool.execute(**args)
            }
        else:
            name = str(kwargs.get("name") or tool_instance_or_name or "")
            desc = description or kwargs.get("description", "")
            params = parameters or kwargs.get("parameters", {"type": "object", "properties": {}})
            h = handler or kwargs.get("handler") or (lambda args: {"status": "success"})

            self._handlers[name] = {
                "schema": {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": desc,
                        "parameters": params
                    }
                },
                "handler": h
            }

    def get_tools_schema(self):
        # type: () -> List[Dict[str, Any]]
        """Возвращает массив спецификаций инструментов в формате OpenAI/MCP."""
        return [tool_info["schema"] for tool_info in self._handlers.values()]

    def call_tool(self, tool_name, raw_arguments):
        # type: (str, Union[str, Dict[str, Any]]) -> Dict[str, Any]
        """
        Парсит аргументы, валидирует их и исполняет инструмент MCP с замером времени и аудитом.
        """
        import time
        start_t = time.time()

        if tool_name == "run_slicing_and_export" and "run_slicing_and_generate_gcode" in self._handlers:
            tool_name = "run_slicing_and_generate_gcode"

        if tool_name not in self._handlers:
            err = "Unknown tool: '{0}'. Available tools: {1}".format(
                tool_name, list(self._handlers.keys())
            )
            logger.error(err)
            return {"status": "error", "error": err}

        # Парсинг аргументов
        if isinstance(raw_arguments, str):
            try:
                args = json.loads(raw_arguments) if raw_arguments.strip() else {}
            except Exception as e:
                err_msg = "Invalid JSON arguments for tool '{0}': {1}".format(tool_name, e)
                logger.error(err_msg)
                return {"status": "error", "error": err_msg}
        elif isinstance(raw_arguments, dict):
            args = raw_arguments
        else:
            args = {}

        handler = self._handlers[tool_name]["handler"]
        try:
            result = handler(args)
            if not isinstance(result, dict):
                result = {"status": "success", "result": result}
        except BaseException as exc:
            logger.exception("Error executing tool '%s': %s", tool_name, exc)
            result = format_exception_for_llm(exc)

        duration_ms = int((time.time() - start_t) * 1000)
        try:
            STEPluginLogger.log_mcp_call(tool_name, args, result, duration_ms)
        except Exception:
            pass

        return result

    def _register_target_tools(self):
        # type: () -> None
        """Регистрирует 4 основных MCP-инструмента и валидатор артефактов."""
        # 1. Анализ геометрии
        try:
            from plugin.mcp_server.tools.geometry_tool import GeometryAnalysisTool
            self.register_tool(GeometryAnalysisTool())
        except Exception as e:
            logger.warning("Failed to register GeometryAnalysisTool: %s", e)

        # 2. Выбор режима и профиля
        try:
            from plugin.mcp_server.tools.profile_mode_tool import ProfileAndModeTool
            self.register_tool(ProfileAndModeTool())
        except Exception as e:
            logger.warning("Failed to register ProfileAndModeTool: %s", e)

        # 3. Трансформация сцены и параметры
        try:
            from plugin.mcp_server.tools.scene_transform_tool import SceneTransformTool
            self.register_tool(SceneTransformTool())
        except Exception as e:
            logger.warning("Failed to register SceneTransformTool: %s", e)

        # 4. Запуск слайсинга и сохранение G-кода
        try:
            from plugin.mcp_server.tools.slicing_export_tool import SlicingAndExportTool
            slice_tool = SlicingAndExportTool(
                event_listener=self._event_listener,
                settings_mgr=self._settings_mgr
            )
            self.register_tool(slice_tool)

        except Exception as e:
            logger.warning("Failed to register SlicingAndExportTool: %s", e)

        # 5. Инструмент валидации и экспорта артефактов (validate_and_export_artifacts)
        self.register_tool(
            name="validate_and_export_artifacts",
            description="Проверяет целостность нарезки, сверяет параметры с ограничениями и сохраняет results/<model_name>/.",
            parameters={
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "Имя модели для создания папки results/<model_name>/."
                    },
                    "user_constraints": {
                        "type": "object",
                        "description": "Словарь ограничений пользователя (например, support_enable: false)."
                    }
                },
                "required": ["model_name"]
            },
            handler=self._validate_and_export_handler
        )

    def _validate_and_export_handler(self, args):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        model_name = args.get("model_name", "test_model")
        user_constraints = args.get("user_constraints", {})

        from plugin.utils.artifact_exporter import ArtifactExporter
        results_root = "results"
        if self._settings_mgr and hasattr(self._settings_mgr, "get_results_root_dir"):
            try:
                results_root = self._settings_mgr.get_results_root_dir()
            except Exception:
                pass

        exporter = ArtifactExporter(results_root=results_root, dispatcher=self._dispatcher)
        report = exporter.verify_model_dir(model_name)

        return {
            "status": "success",
            "validation_passed": report.get("passed", True),
            "checks_report": report.get("checks", []),
            "errors": report.get("errors", []),
            "warnings": report.get("warnings", []),
            "model_name": model_name,
            "message": "Валидация артефактов модели '{0}' завершена.".format(model_name)
        }


__all__ = ["BaseMCPTool", "MCPServer"]
