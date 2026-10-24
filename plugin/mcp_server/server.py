# -*- coding: utf-8 -*-
import json
import logging
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger("MCPServer")


class BaseMCPTool(object):
    name = ""
    description = ""
    parameters_schema = {}  # type: Dict[str, Any]

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        raise NotImplementedError


class MCPServer(object):

    def __init__(self, settings_mgr=None, event_listener=None, camera_manager=None, dispatcher=None):
        # type: (Any, Any, Any, Any) -> None
        self._handlers = {}  # type: Dict[str, Any]
        self._settings_mgr = settings_mgr
        self._event_listener = event_listener
        self._camera_manager = camera_manager
        self._dispatcher = dispatcher
        self._register_default_tools()

    def register_tool(self, name, description, parameters, handler):
        # type: (str, str, Dict[str, Any], Any) -> None
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

    def register_tool_instance(self, tool):
        # type: (BaseMCPTool) -> None
        def _handler(args, _tool=tool):
            return _tool.execute(**(args or {}))

        self.register_tool(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters_schema or {"type": "object", "properties": {}},
            handler=_handler
        )

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
        from plugin.mcp_server.tools.geometry_tool import GeometryAnalysisTool
        from plugin.mcp_server.tools.scene_transform_tool import SceneTransformTool
        from plugin.mcp_server.tools.profile_mode_tool import ProfileModeTool
        from plugin.mcp_server.tools.slicing_export_tool import SlicingTool, ValidateExportTool

        for tool in (
            GeometryAnalysisTool(),
            ProfileModeTool(settings_mgr=self._settings_mgr),
            SceneTransformTool(),
            SlicingTool(event_listener=self._event_listener),
            ValidateExportTool(settings_mgr=self._settings_mgr,
                               camera_manager=self._camera_manager,
                               dispatcher=self._dispatcher),
        ):
            self.register_tool_instance(tool)


__all__ = ["MCPServer", "BaseMCPTool"]
