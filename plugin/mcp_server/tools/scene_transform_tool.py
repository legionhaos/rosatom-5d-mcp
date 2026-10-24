# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import math
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        """Fallback base class for MCP tools."""
        name = ""
        description = ""
        parameters_schema = {}  # type: Dict[str, Any]

        def execute(self, **kwargs):
            # type: (**Any) -> Dict[str, Any]
            raise NotImplementedError

try:
    from utils.exceptions import (
        STEPluginError,
        MeshError,
        SceneError,
        ParameterError,
        format_exception_for_llm,
    )
except (ImportError, AttributeError):
    class STEPluginError(Exception):
        """Base exception for STE Slicer plugin."""
        def __init__(self, message, code="STE_PLUGIN_ERROR", details=None):
            super(STEPluginError, self).__init__(message)
            self.code = code
            self.details = details or {}
            self.message = message

    class MeshError(STEPluginError):
        def __init__(self, message, details=None):
            super(MeshError, self).__init__(message, code="MESH_ERROR", details=details)

    class SceneError(STEPluginError):
        def __init__(self, message, details=None):
            super(SceneError, self).__init__(message, code="SCENE_ERROR", details=details)

    class ParameterError(STEPluginError):
        def __init__(self, message, details=None):
            super(ParameterError, self).__init__(message, code="PARAMETER_ERROR", details=details)

    def format_exception_for_llm(exc):
        # type: (BaseException) -> Dict[str, Any]
        return {
            "status": "ERROR",
            "error_code": getattr(exc, "code", type(exc).__name__),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc(),
        }

try:
    from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
except (ImportError, AttributeError):
    class MainThreadDispatcher(object):
        """Main thread GUI dispatcher for Cura/Qt."""
        @staticmethod
        def run_sync(func, *args, **kwargs):
            try:
                import threading
                from cura.CuraApplication import CuraApplication
                app = CuraApplication.getInstance()
                if app and threading.current_thread() is not threading.main_thread():
                    result_box = [None]
                    error_box = [None]
                    event = threading.Event()

                    def _wrapper():
                        try:
                            result_box[0] = func(*args, **kwargs)
                        except Exception as e:
                            error_box[0] = e
                        finally:
                            event.set()

                    app.callLater(_wrapper)
                    event.wait(timeout=30.0)
                    if error_box[0] is not None:
                        raise error_box[0]
                    return result_box[0]
            except (ImportError, AttributeError):
                pass
            return func(*args, **kwargs)


class SceneTransformTool(BaseMCPTool):
    """MCP tool for spatial scene transformations and slicer stack parameter modifications."""

    name = "modify_scene_and_parameters"
    description = (
        "Applies spatial transformations (rotation, build plate drop, arrangement) "
        "and sets slicing parameters in GlobalStack and ExtruderStack userChanges."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Identifier or name of the SceneNode on the scene."
            },
            "file_path": {
                "type": "string",
                "description": "Path to the 3D model file if loading is required prior to transformation."
            },
            "rotation_euler_deg": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Rotation angles [rx, ry, rz] in degrees in print coordinate space (Z-up)."
            },
            "position_xy_mm": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Target center coordinates [x, y] in mm on the build plate."
            },
            "scale_factor": {
                "type": "number",
                "description": "Uniform scale factor (e.g. 1.0 = 100%, 1.5 = 150%)."
            },
            "auto_arrange_on_plate": {
                "type": "boolean",
                "description": "Automatically arrange node on the build plate and drop to Z=0.",
                "default": True
            },
            "supports_enabled": {
                "type": "boolean",
                "description": "Direct toggle for support generation (support_enable setting)."
            },
            "print_parameters": {
                "type": "object",
                "description": "Key-value dictionary of slicing settings to override in container stacks."
            }
        },
        "required": []
    }

    _SETTING_TYPES = {
        "support_enable": bool,
        "support_type": str,
        "support_angle": float,
        "layer_height": float,
        "layer_height_0": float,
        "wall_line_count": int,
        "wall_thickness": float,
        "top_bottom_thickness": float,
        "top_thickness": float,
        "bottom_thickness": float,
        "top_layers": int,
        "bottom_layers": int,
        "infill_sparse_density": float,
        "infill_pattern": str,
        "infill_line_distance": float,
        "material_print_temperature": float,
        "material_print_temperature_layer_0": float,
        "material_bed_temperature": float,
        "material_bed_temperature_layer_0": float,
        "speed_print": float,
        "speed_infill": float,
        "speed_wall": float,
        "speed_travel": float,
        "retraction_enable": bool,
        "retraction_amount": float,
        "retraction_speed": float,
        "cool_fan_speed": float,
        "cool_fan_speed_0": float,
        "adhesion_type": str,
        "brim_width": float,
        "skirt_line_count": int,
    }

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        """Execute node transformations and write parameter overrides."""
        try:
            node_id = kwargs.get("node_id")
            file_path = kwargs.get("file_path")
            rotation_euler_deg = kwargs.get("rotation_euler_deg")
            position_xy_mm = kwargs.get("position_xy_mm")
            scale_factor = kwargs.get("scale_factor")
            auto_arrange_on_plate = kwargs.get("auto_arrange_on_plate", True)
            supports_enabled = kwargs.get("supports_enabled")
            print_parameters = kwargs.get("print_parameters") or {}

            warnings = []  # type: List[str]

            result = MainThreadDispatcher.run_sync(
                self._apply_transforms_and_settings,
                node_id=node_id,
                file_path=file_path,
                rotation_euler_deg=rotation_euler_deg,
                position_xy_mm=position_xy_mm,
                scale_factor=scale_factor,
                auto_arrange_on_plate=auto_arrange_on_plate,
                supports_enabled=supports_enabled,
                print_parameters=print_parameters,
                warnings=warnings
            )

            return result

        except STEPluginError as exc:
            return format_exception_for_llm(exc)
        except Exception as exc:
            return format_exception_for_llm(exc)

    def _apply_transforms_and_settings(
        self,
        node_id,
        file_path,
        rotation_euler_deg,
        position_xy_mm,
        scale_factor,
        auto_arrange_on_plate,
        supports_enabled,
        print_parameters,
        warnings
    ):
        """Internal transformation pipeline executed synchronously on the Qt main thread."""
        try:
            from cura.CuraApplication import CuraApplication
        except ImportError:
            CuraApplication = None
        from UM.Math.Quaternion import Quaternion
        from UM.Math.Vector import Vector

        app = None
        try:
            from UM.Application import Application
            app = Application.getInstance()
        except Exception:
            pass
        if app is None and CuraApplication is not None:
            try:
                app = CuraApplication.getInstance()
            except Exception as exc:
                raise SceneError("Не удалось получить экземпляр приложения: {0}".format(exc))
        if not app:
            raise SceneError("Приложение слайсера не инициализировано.")

        scene = app.getController().getScene()
        if not scene:
            raise SceneError("Scene controller is unavailable.")

        node = self._resolve_node(app, scene, file_path, node_id)
        if node is None:
            raise SceneError(
                "Target scene node was not found.",
                details={"node_id": node_id, "file_path": file_path}
            )

        applied_scale = None
        if scale_factor is not None:
            factor = float(scale_factor)
            if factor <= 0.0:
                raise STEPluginError("Scale factor must be strictly greater than 0.")
            current_scale = node.getScale()
            node.setScale(Vector(current_scale.x * factor, current_scale.y * factor, current_scale.z * factor))
            applied_scale = factor

        applied_rotation = None
        if rotation_euler_deg is not None:
            if not isinstance(rotation_euler_deg, (list, tuple)) or len(rotation_euler_deg) != 3:
                raise STEPluginError("Parameter rotation_euler_deg must contain 3 numbers [rx, ry, rz].")

            rx = float(rotation_euler_deg[0])
            ry = float(rotation_euler_deg[1])
            rz = float(rotation_euler_deg[2])

            qx = Quaternion.fromAngleAxis(math.radians(-rx), Vector(1, 0, 0))
            qy = Quaternion.fromAngleAxis(math.radians(-ry), Vector(0, 0, 1))
            qz = Quaternion.fromAngleAxis(math.radians(-rz), Vector(0, 1, 0))

            rot_quat = qz * qy * qx
            current_orient = node.getOrientation()
            node.setOrientation(rot_quat * current_orient)
            applied_rotation = [rx, ry, rz]

        self._drop_node_to_build_plate(node)

        applied_position = None
        if position_xy_mm is not None:
            if not isinstance(position_xy_mm, (list, tuple)) or len(position_xy_mm) != 2:
                raise STEPluginError("Parameter position_xy_mm must contain 2 coordinates [x, y].")
            target_x = float(position_xy_mm[0])
            target_y = float(position_xy_mm[1])

            bbox = node.getBoundingBox()
            if bbox is not None:
                cx = (bbox.left + bbox.right) / 2.0
                cz = (bbox.front + bbox.back) / 2.0
                current_pos = node.getPosition()
                node.setPosition(Vector(
                    current_pos.x + (target_x - cx),
                    current_pos.y,
                    current_pos.z + (target_y - cz)
                ))
            else:
                current_pos = node.getPosition()
                node.setPosition(Vector(target_x, current_pos.y, target_y))

            self._drop_node_to_build_plate(node)
            applied_position = [target_x, target_y]

        elif auto_arrange_on_plate:
            arranged = self._arrange_node(app, scene, node)
            if not arranged:
                self._center_node_on_plate(node)
                warnings.append("Module cura.Arranging.Arrange unavailable; centered on plate.")
            self._drop_node_to_build_plate(node)

        final_uranium_pos = node.getPosition()
        world_position_print = [
            round(final_uranium_pos.x, 3),
            round(final_uranium_pos.z, 3),
            round(final_uranium_pos.y, 3)
        ]

        if supports_enabled is not None:
            print_parameters["support_enable"] = bool(supports_enabled)

        applied_overrides = {}
        if print_parameters:
            applied_overrides = self._apply_slicer_parameters(app, print_parameters, warnings)

        resolved_id = str(getattr(node, "getId", lambda: getattr(node, "getName", lambda: "unknown"))())
        resolved_name = str(getattr(node, "getName", lambda: "Scene_Mesh")())

        return {
            "status": "SUCCESS",
            "node_id": resolved_id,
            "node_name": resolved_name,
            "applied_rotation_euler_deg": applied_rotation,
            "applied_scale_factor": applied_scale,
            "applied_position_xy_mm": applied_position,
            "world_position_mm": world_position_print,
            "applied_overrides": applied_overrides,
            "warnings": warnings
        }

    def _drop_node_to_build_plate(self, node):
        """Align bottom boundary of node bounding box with build plate Y=0."""
        from UM.Math.Vector import Vector
        bbox = node.getBoundingBox()
        if bbox is not None:
            delta_y = -bbox.bottom
            current_pos = node.getPosition()
            node.setPosition(Vector(current_pos.x, current_pos.y + delta_y, current_pos.z))

    def _center_node_on_plate(self, node):
        """Center the bounding box center in the Uranium build plate plane (X and Z)."""
        from UM.Math.Vector import Vector
        bbox = node.getBoundingBox()
        if bbox is not None:
            cx = (bbox.left + bbox.right) / 2.0
            cz = (bbox.front + bbox.back) / 2.0
            current_pos = node.getPosition()
            node.setPosition(Vector(current_pos.x - cx, current_pos.y, current_pos.z - cz))

    def _arrange_node(self, app, scene, target_node):
        """Execute Cura arrange algorithm if available."""
        try:
            from cura.Arranging.Arrange import Arrange
            all_mesh_nodes = [
                n for n in scene.getRoot().getAllChildren()
                if hasattr(n, "getMeshData") and n.getMeshData() is not None
            ]
            if not all_mesh_nodes:
                return False

            if hasattr(Arrange, "arrange"):
                Arrange.arrange(all_mesh_nodes, scene.getRoot())
                return True
            elif hasattr(Arrange, "create"):
                arranger = Arrange.create(scene_root=scene.getRoot(), fixed_nodes=[])
                from cura.Arranging.ShapeArray import ShapeArray
                shape = ShapeArray.fromNode(target_node, min_offset=5)
                if shape is not None:
                    arranger.findNodePlacement(target_node, shape)
                    return True
        except Exception:
            pass
        return False

    def _resolve_node(self, app, scene, file_path, node_id):
        """Retrieve SceneNode by identifier or import from file."""
        if node_id:
            found = self._find_node_by_id(scene.getRoot(), str(node_id))
            if found:
                return found

        if file_path:
            if not os.path.exists(file_path):
                raise MeshError("File not found: {}".format(file_path))
            handler = app.getMeshFileHandler()
            reader = getattr(handler, "read", None) if handler is not None else None
            if reader is not None:
                loaded = reader(file_path)
                if loaded:
                    if isinstance(loaded, list) and len(loaded) > 0:
                        return loaded[0]
                    return loaded
            children = [c for c in scene.getRoot().getAllChildren() if hasattr(c, "getMeshData") and c.getMeshData()]
            if children:
                return children[-1]

        for child in scene.getRoot().getAllChildren():
            if hasattr(child, "getMeshData") and child.getMeshData():
                return child
        return None

    def _find_node_by_id(self, parent_node, target_id):
        """Recursively locate node by ID or name."""
        if str(getattr(parent_node, "getId", lambda: "")()) == target_id:
            return parent_node
        if str(getattr(parent_node, "getName", lambda: "")()) == target_id:
            return parent_node

        for child in parent_node.getAllChildren():
            res = self._find_node_by_id(child, target_id)
            if res:
                return res
        return None

    def _apply_slicer_parameters(self, app, print_parameters, warnings):
        """Validate, cast, and persist parameter values into container stack userChanges."""
        global_stack = app.getGlobalContainerStack()
        if not global_stack:
            raise SceneError("Active GlobalStack is missing.")

        extruder_stack = None
        extruders = getattr(global_stack, "extruders", None)
        if extruders:
            if isinstance(extruders, dict) and len(extruders) > 0:
                extruder_stack = extruders.get("0") or next(iter(extruders.values()))
            elif isinstance(extruders, (list, tuple)) and len(extruders) > 0:
                extruder_stack = extruders[0]

        applied_report = {}

        extruder_specific_keys = {
            "material_print_temperature",
            "material_print_temperature_layer_0",
            "retraction_enable",
            "retraction_amount",
            "retraction_speed",
            "cool_fan_speed",
            "cool_fan_speed_0",
            "wall_line_count",
            "wall_thickness",
            "top_bottom_thickness",
            "top_thickness",
            "bottom_thickness",
            "infill_sparse_density",
            "infill_pattern",
            "speed_print",
            "layer_height"
        }

        for key, raw_value in print_parameters.items():
            if key not in self._SETTING_TYPES:
                warnings.append("Parameter '{}' not in supported whitelist; skipped.".format(key))
                continue

            expected_type = self._SETTING_TYPES[key]
            try:
                if expected_type is bool:
                    if isinstance(raw_value, str):
                        typed_value = raw_value.strip().lower() in ("true", "1", "yes", "on")
                    else:
                        typed_value = bool(raw_value)
                elif expected_type is int:
                    typed_value = int(round(float(raw_value)))
                elif expected_type is float:
                    typed_value = float(raw_value)
                else:
                    typed_value = str(raw_value)
            except (ValueError, TypeError) as cast_err:
                warnings.append("Type cast failure for '{}': {}. Skipped.".format(key, cast_err))
                continue

            is_per_extruder = False
            try:
                is_per_extruder = bool(global_stack.getProperty(key, "settable_per_extruder"))
            except Exception:
                pass

            target_stack = global_stack
            stack_name = "GlobalStack"

            if (is_per_extruder or key in extruder_specific_keys) and extruder_stack is not None:
                target_stack = extruder_stack
                stack_name = "ExtruderStack[0]"

            user_container = self._get_user_changes_container(target_stack)
            if not user_container:
                warnings.append("userChanges container not found in {} for '{}'.".format(stack_name, key))
                continue

            try:
                old_val = target_stack.getProperty(key, "value")
            except Exception:
                old_val = None

            try:
                user_container.setProperty(key, "value", typed_value)
                if hasattr(target_stack, "propertyChanged"):
                    target_stack.propertyChanged.emit(key, "value")
            except Exception as e:
                warnings.append("Failed writing {}.{} = {}: {}".format(stack_name, key, typed_value, str(e)))
                continue

            try:
                verified_new_val = target_stack.getProperty(key, "value")
            except Exception:
                verified_new_val = typed_value

            applied_report[key] = {
                "old": self._serialize_value(old_val),
                "new": self._serialize_value(verified_new_val),
                "target_stack": stack_name
            }

        return applied_report

    def _get_user_changes_container(self, stack):
        """Retrieve stack userChanges container instance."""
        if hasattr(stack, "userChanges") and stack.userChanges is not None:
            return stack.userChanges

        if hasattr(stack, "userChangesContainer") and stack.userChangesContainer is not None:
            return stack.userChangesContainer

        if hasattr(stack, "getContainerCount") and hasattr(stack, "getContainer"):
            for idx in range(stack.getContainerCount()):
                container = stack.getContainer(idx)
                if not container:
                    continue
                cid = str(getattr(container, "getId", lambda: "")()).lower()
                meta_type = str(getattr(container, "getMetaDataEntry", lambda k: "")("type")).lower()
                if "user" in cid or meta_type == "user":
                    return container

        if hasattr(stack, "getTop"):
            return stack.getTop()

        return None

    @staticmethod
    def _serialize_value(val):
        """Serialize configuration value to JSON-compatible data type."""
        if val is None or isinstance(val, (int, float, bool, str)):
            return val
        if hasattr(val, "value"):
            return val.value
        return str(val)
