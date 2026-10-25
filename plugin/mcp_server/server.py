# -*- coding: utf-8 -*-
import json
import logging
import traceback
from typing import Dict, Any, List, Optional, Union

try:
    import jsonschema
except ImportError:
    jsonschema = None

try:
    from plugin.utils.logger import get_logger
    logger = get_logger("MCPServer")
except Exception:
    logger = logging.getLogger("MCPServer")


class BaseMCPTool(object):
    name = ""
    description = ""
    parameters_schema = {}  # type: Dict[str, Any]

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        raise NotImplementedError


class MCPServer(object):

    def __init__(self, settings_mgr=None, event_listener=None, camera_manager=None, dispatcher=None, application=None):
        # type: (Any, Any, Any, Any) -> None
        self._handlers = {}  # type: Dict[str, Any]
        self._settings_mgr = settings_mgr
        self._event_listener = event_listener
        self._camera_manager = camera_manager
        self._dispatcher = dispatcher
        self._application = application
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
                logger.exception("Invalid JSON arguments for MCP tool '%s'.", tool_name)
                return {"status": "error", "error": "Invalid JSON arguments: {0}".format(e), "traceback": traceback.format_exc()}
            if not isinstance(args, dict):
                err = "MCP tool arguments must be a JSON object."
                logger.error("Invalid argument shape for MCP tool '%s': %s", tool_name, type(args).__name__)
                return {"status": "error", "error": err}
        elif isinstance(arguments_json, dict):
            args = arguments_json
        else:
            return {"status": "error", "error": "MCP tool arguments must be a JSON object or JSON string."}

        schema = self._handlers[tool_name]["schema"].get("function", {}).get("parameters", {})
        validation_error = self._validate_arguments(args, schema)
        if validation_error:
            return {"status": "error", "error": "Invalid arguments: {0}".format(validation_error)}

        handler = self._handlers[tool_name]["handler"]
        try:
            return handler(args)
        except Exception as e:
            logger.exception("Error executing tool '%s': %s", tool_name, e)
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

    @staticmethod
    def _validate_arguments(args, schema):
        # type: (Dict[str, Any], Dict[str, Any]) -> Optional[str]
        if jsonschema is not None:
            try:
                jsonschema.validate(args, schema)
            except jsonschema.ValidationError as exc:
                return exc.message
            except jsonschema.SchemaError as exc:
                logger.error("Invalid registered MCP schema: %s", exc)
                return "Tool schema is invalid."
            return None

        if schema.get("type") == "object" and not isinstance(args, dict):
            return "arguments must be an object"
        if schema.get("additionalProperties") is False:
            unexpected = set(args) - set(schema.get("properties", {}))
            if unexpected:
                return "unexpected propert{0} {1}".format("y" if len(unexpected) == 1 else "ies", sorted(unexpected))
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in args:
                return "missing required property '{0}'".format(key)
        for key, value in args.items():
            spec = properties.get(key)
            if spec is None:
                if schema.get("additionalProperties") is False:
                    return "unexpected property '{0}'".format(key)
                continue
            expected = spec.get("type")
            if expected == "array" and not isinstance(value, list):
                return "property '{0}' must be an array".format(key)
            if expected == "object" and not isinstance(value, dict):
                return "property '{0}' must be an object".format(key)
            if expected == "string" and not isinstance(value, str):
                return "property '{0}' must be a string".format(key)
            if expected == "boolean" and not isinstance(value, bool):
                return "property '{0}' must be a boolean".format(key)
            if expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                return "property '{0}' must be a number".format(key)
            if expected == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
                return "property '{0}' must be an integer".format(key)
            if "enum" in spec and value not in spec["enum"]:
                return "property '{0}' must be one of {1}".format(key, spec["enum"])
            if "minimum" in spec and isinstance(value, (int, float)) and value < spec["minimum"]:
                return "property '{0}' must be >= {1}".format(key, spec["minimum"])
            if "maximum" in spec and isinstance(value, (int, float)) and value > spec["maximum"]:
                return "property '{0}' must be <= {1}".format(key, spec["maximum"])
            if "minItems" in spec and isinstance(value, list) and len(value) < spec["minItems"]:
                return "property '{0}' has too few items".format(key)
            if "maxItems" in spec and isinstance(value, list) and len(value) > spec["maxItems"]:
                return "property '{0}' has too many items".format(key)
            item_schema = spec.get("items", {})
            if isinstance(value, list) and item_schema.get("type"):
                item_type = item_schema["type"]
                for item in value:
                    valid = {
                        "string": lambda v: isinstance(v, str),
                        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
                        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                        "boolean": lambda v: isinstance(v, bool),
                        "object": lambda v: isinstance(v, dict),
                        "array": lambda v: isinstance(v, list),
                    }.get(item_type, lambda v: True)(item)
                    if not valid:
                        return "items in property '{0}' must be {1}".format(key, item_type)
        return None

    def _register_default_tools(self):
        # type: () -> None
        from plugin.mcp_server.tools.geometry_tool import GeometryAnalysisTool
        from plugin.mcp_server.tools.scene_transform_tool import SceneTransformTool
        from plugin.mcp_server.tools.profile_mode_tool import ProfileModeTool
        from plugin.mcp_server.tools.slicing_export_tool import SlicingTool, ValidateExportTool

        for tool in (
            GeometryAnalysisTool(dispatcher=self._dispatcher, application=self._application),
            ProfileModeTool(settings_mgr=self._settings_mgr),
            SceneTransformTool(),
            SlicingTool(event_listener=self._event_listener),
            ValidateExportTool(settings_mgr=self._settings_mgr,
                               camera_manager=self._camera_manager,
                               dispatcher=self._dispatcher),
        ):
            self.register_tool_instance(tool)


__all__ = ["MCPServer", "BaseMCPTool"]
