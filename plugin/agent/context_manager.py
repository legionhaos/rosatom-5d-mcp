# -*- coding: utf-8 -*-
"""
Conversation Context Manager and Slicer State Collector for STE Slicer.

This module manages the dialogue history for the LLM agent, handles multimodal
attachments (converting images to Base64 data URLs via QImage and injecting 3D model
file references into structured context), and captures live state snapshots of STE Slicer
(loaded models, rotations, active 3D/5D mode, material, and slicing parameters) via
MainThreadDispatcher.
"""

import base64
import json
import logging
import math
import os
import sys
from typing import Dict, Any, List, Optional, Tuple, Union

# Try to import project logger if available, otherwise use standard logging
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger("ConversationContextManager")

# Dynamic import of Qt QImage for image compression and Base64 conversion
try:
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import QByteArray, QBuffer, QIODevice, Qt
except ImportError:
    try:
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt
    except ImportError:
        try:
            from PySide2.QtGui import QImage
            from PySide2.QtCore import QByteArray, QBuffer, QIODevice, Qt
        except ImportError:
            try:
                from PySide6.QtGui import QImage
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
            except ImportError:
                QImage = None
                QBuffer = None
                QIODevice = None
                Qt = None

# Slicer bridge MainThreadDispatcher import
try:
    from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
except ImportError:
    MainThreadDispatcher = None


# Supported file extensions
MODEL_EXTENSIONS = {".stl", ".3mf", ".obj", ".step", ".stp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def encode_image_to_base64(image_path, max_side_px=1024):
    # type: (str, int) -> str
    """
    Compresses an image file using QImage (keeping aspect ratio with maximum side
    constrained to max_side_px) and returns its Base64-encoded string representation.

    If Qt is not available in the environment, falls back to direct Base64 encoding.

    Args:
        image_path: Absolute or relative path to the image file.
        max_side_px: Maximum width or height of the image in pixels (default: 1024).

    Returns:
        str: Base64-encoded string.

    Raises:
        FileNotFoundError: If the specified image_path does not exist.
    """
    if not os.path.isfile(image_path):
        raise IOError("Image file not found: {0}".format(image_path))

    # 1. Try QImage scaling and encoding if Qt is available
    if QImage is not None and QBuffer is not None and QIODevice is not None and Qt is not None:
        try:
            qimg = QImage(image_path)
            if not qimg.isNull():
                orig_w = qimg.width()
                orig_h = qimg.height()

                # Scale down if either dimension exceeds max_side_px
                if orig_w > max_side_px or orig_h > max_side_px:
                    qimg = qimg.scaled(
                        max_side_px,
                        max_side_px,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )

                buf = QBuffer()
                buf.open(QIODevice.WriteOnly)

                ext = os.path.splitext(image_path)[1].lower()
                fmt = "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
                qimg.save(buf, fmt)

                byte_data = buf.data()
                # Convert QByteArray to base64 string
                if hasattr(byte_data, "toBase64"):
                    return bytes(byte_data.toBase64()).decode("utf-8")
                else:
                    return base64.b64encode(bytes(byte_data)).decode("utf-8")
        except Exception as e:
            logger.debug("QImage encoding failed for '%s': %s. Using standard base64 fallback.", image_path, e)

    # 2. Fallback: Direct binary read and standard library base64 encoding
    with open(image_path, "rb") as f:
        raw_bytes = f.read()
    return base64.b64encode(raw_bytes).decode("utf-8")


class ConversationContextManager(object):
    """
    Manages the multi-turn dialogue history, multimodal content (text, 3D models,
    and Base64-encoded images), and collects active STE Slicer state snapshots.
    """

    def __init__(self, application=None):
        # type: (Optional[Any]) -> None
        """Initializes empty message history and attached models tracking."""
        self._application_override = application
        self.messages = []  # type: List[Dict[str, Any]]
        self.attached_models = []  # type: List[str]
        self._mock_snapshot = None  # type: Optional[Dict[str, Any]]

    def add_user_turn(self, text, attachments=None):
        # type: (str, Optional[List[str]]) -> Dict[str, Any]
        """
        Processes a user turn with optional file attachments.

        Separates attachments into:
        - 3D models (.stl, .3mf, .obj, .step, .stp): Appends their file paths into
          a structured context block within the text.
        - Images (.png, .jpg, etc.): Encodes to Base64 and formats into OpenAI
          multimodal image_url objects (data:image/png;base64,...).

        Args:
            text: User input message string.
            attachments: Optional list of file paths attached to the message.

        Returns:
            Dict[str, Any]: Formatted user message dictionary.
        """
        user_text = (text or "").strip()
        files = attachments or []

        model_files = []  # type: List[str]
        image_files = []  # type: List[str]
        other_files = []  # type: List[str]

        for file_path in files:
            if not file_path:
                continue
            ext = os.path.splitext(file_path)[1].lower()
            if ext in MODEL_EXTENSIONS:
                model_files.append(file_path)
                if file_path not in self.attached_models:
                    self.attached_models.append(file_path)
            elif ext in IMAGE_EXTENSIONS:
                image_files.append(file_path)
            else:
                other_files.append(file_path)

        # Build text with structured 3D models block
        text_parts = []
        if user_text:
            text_parts.append(user_text)

        if model_files:
            model_block = ["\n[Прикрепленные 3D-модели для анализа и печати]:"]
            for m in model_files:
                basename = os.path.basename(m)
                model_block.append("- {0} (путь: {1})".format(basename, m))
            text_parts.append("\n".join(model_block))

        if other_files:
            other_block = ["\n[Прикрепленные файлы]:"]
            for of in other_files:
                other_block.append("- {0}".format(of))
            text_parts.append("\n".join(other_block))

        full_text = "\n\n".join(text_parts).strip()
        if not full_text and image_files:
            full_text = "Анализ прикрепленных графических материалов / эскизов."

        # If there are images, build multimodal content array
        if image_files:
            content = [
                {
                    "type": "text",
                    "text": full_text
                }
            ]
            for img_path in image_files:
                try:
                    b64_str = encode_image_to_base64(img_path)
                    ext = os.path.splitext(img_path)[1].lower()
                    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                    data_url = "data:{0};base64,{1}".format(mime, b64_str)
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    })
                except Exception as e:
                    logger.warning("Failed to encode image '%s': %s", img_path, e)
                    content.append({
                        "type": "text",
                        "text": "[Ошибка загрузки изображения {0}: {1}]".format(os.path.basename(img_path), str(e))
                    })
        else:
            content = full_text

        user_message = {
            "role": "user",
            "content": content
        }
        self.messages.append(user_message)
        return user_message

    def add_assistant_tool_calls(self, content, tool_calls):
        # type: (Optional[str], List[Any]) -> None
        """
        Saves the assistant's response requesting tool executions.

        Args:
            content: Optional assistant thought/text string.
            tool_calls: List of tool calls (either dicts or ToolCallItem objects).
        """
        formatted_calls = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                # Standard OpenAI tool_call dict or flat dict
                if "type" in tc and "function" in tc:
                    formatted_calls.append(tc)
                elif "name" in tc:
                    call_id = tc.get("id") or "call_unknown"
                    args = tc.get("arguments") or tc.get("arguments_json") or "{}"
                    if isinstance(args, (dict, list)):
                        args = json.dumps(args, ensure_ascii=False)
                    formatted_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": str(args)
                        }
                    })
            elif hasattr(tc, "id") and hasattr(tc, "name") and hasattr(tc, "arguments_json"):
                # NamedTuple ToolCallItem from llm_client
                formatted_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments_json
                    }
                })

        assistant_message = {
            "role": "assistant",
            "content": content,
            "tool_calls": formatted_calls
        }
        self.messages.append(assistant_message)

    def add_assistant_message(self, content):
        # type: (Optional[str]) -> None
        """Saves a standard assistant text response."""
        self.messages.append({
            "role": "assistant",
            "content": content
        })

    def add_tool_result(self, tool_call_id, tool_name, result_payload):
        # type: (str, str, Any) -> None
        """
        Adds the result of an MCP tool execution (role: "tool").

        Args:
            tool_call_id: Identifier of the tool call being answered.
            tool_name: Name of the executed tool.
            result_payload: Result object, dictionary, or string.
        """
        if isinstance(result_payload, (dict, list)):
            content_str = json.dumps(result_payload, ensure_ascii=False)
        else:
            content_str = str(result_payload) if result_payload is not None else "{}"

        tool_message = {
            "role": "tool",
            "tool_call_id": str(tool_call_id),
            "name": str(tool_name),
            "content": content_str
        }
        self.messages.append(tool_message)

    def capture_slicer_snapshot(self):
        # type: () -> Dict[str, Any]
        """
        Queries CuraApplication via MainThreadDispatcher and returns a compact
        JSON-compatible snapshot of loaded models, rotations, active mode (3D/5D),
        material, and key slicing parameters.

        Returns:
            Dict[str, Any]: Slicer state dictionary.
        """
        # If MainThreadDispatcher is available, execute on the main thread
        if MainThreadDispatcher is not None:
            try:
                return MainThreadDispatcher.call_on_main_thread(
                    self._query_cura_state, self._application_override
                )
            except Exception as e:
                logger.warning("Main-thread scene snapshot failed: %s", e)
                return self._build_fallback_snapshot()

        return self._query_cura_state(self._application_override)

    def _query_cura_state(self, app=None):
        # type: (Optional[Any]) -> Dict[str, Any]
        """Internal method querying live CuraApplication instance."""
        if app is None:
            for mod_name in ("steslicer.SteSlicerApplication", "UM.Application", "cura.CuraApplication"):
                try:
                    mod = __import__(mod_name, fromlist=["SteSlicerApplication", "Application", "CuraApplication"])
                    for attr in ("SteSlicerApplication", "Application", "CuraApplication"):
                        cls_ = getattr(mod, attr, None)
                        if cls_ and hasattr(cls_, "getInstance"):
                            inst = cls_.getInstance()
                            if inst:
                                app = inst
                                break
                    if app:
                        break
                except Exception:
                    pass
            if app is None:
                try:
                    import sys
                    for mod_name in ("steslicer.SteSlicerApplication", "UM.Application", "cura.CuraApplication"):
                        if mod_name in sys.modules:
                            mod = sys.modules[mod_name]
                            for attr in ("SteSlicerApplication", "Application", "CuraApplication"):
                                cls_ = getattr(mod, attr, None)
                                if cls_ and hasattr(cls_, "getInstance"):
                                    inst = cls_.getInstance()
                                    if inst:
                                        app = inst
                                        break
                        if app:
                            break
                except Exception:
                    app = None

        # If live CuraApplication is not available (e.g. in tests/headless), return mock or fallback
        if app is None:
            if self._mock_snapshot is not None:
                return dict(self._mock_snapshot)
            return self._build_fallback_snapshot()

        # Query live scene models. Cura nodes may be nested under group nodes,
        # so include descendants rather than only the root's immediate children.
        models = []  # type: List[Dict[str, Any]]
        try:
            scene = app.getController().getScene()
            root = scene.getRoot()
            children = []
            pending = list(root.getChildren() if hasattr(root, 'getChildren') else [])
            seen = set()
            while pending:
                node = pending.pop(0)
                node_key = id(node)
                if node_key in seen:
                    continue
                seen.add(node_key)
                children.append(node)
                pending.extend(getattr(node, 'getChildren', lambda: [])() or [])
            if not children and hasattr(root, 'getAllChildren'):
                children = root.getAllChildren() or []
            for child in children:
                try:
                    mesh_getter = getattr(child, "getMeshData", None)
                    if not callable(mesh_getter) or mesh_getter() is None:
                        continue

                    # Ignore convex hull preview nodes and helper meshes
                    if type(child).__name__ == "ConvexHullNode" or hasattr(child, "getHull"):
                        continue

                    # Skip explicitly non-printing meshes and nested mesh components;
                    # valid models can have no name or lack Cura's isSliceable decoration.
                    if hasattr(child, "callDecoration"):
                        try:
                            if child.callDecoration("isNonPrintingMesh"):
                                continue
                        except Exception:
                            pass
                    parent = getattr(child, "getParent", lambda: None)()
                    parent_mesh_getter = getattr(parent, "getMeshData", None) if parent is not None else None
                    if callable(parent_mesh_getter) and parent_mesh_getter() is not None:
                        continue

                    try:
                        node_name = child.getName() if hasattr(child, "getName") else ""
                    except Exception:
                        node_name = ""

                    node_id = str(child.getId()) if hasattr(child, "getId") else "node"

                    # Position: in 3D printing convention: X=x, Y=z (depth), Z=y (height)
                    pos = [0.0, 0.0, 0.0]
                    if hasattr(child, "getPosition"):
                        p = child.getPosition()
                        px = float(p.x() if callable(getattr(p, "x", None)) else getattr(p, "x", 0.0))
                        py = float(p.z() if callable(getattr(p, "z", None)) else getattr(p, "z", 0.0))
                        pz = float(p.y() if callable(getattr(p, "y", None)) else getattr(p, "y", 0.0))
                        pos = [round(px, 2), round(py, 2), round(pz, 2)]

                    # Rotation
                    rot = [0.0, 0.0, 0.0]
                    if hasattr(child, "getOrientation"):
                        rot = list(self._quaternion_to_euler_degrees(child.getOrientation()))

                    # Dimensions: in 3D printing convention: X=width, Y=depth, Z=height
                    dims = [0.0, 0.0, 0.0]
                    if hasattr(child, "getBoundingBox"):
                        bbox = child.getBoundingBox()
                        if bbox:
                            w = float(bbox.width() if callable(getattr(bbox, "width", None)) else getattr(bbox, "width", 0.0))
                            d = float(bbox.depth() if callable(getattr(bbox, "depth", None)) else getattr(bbox, "depth", 0.0))
                            h = float(bbox.height() if callable(getattr(bbox, "height", None)) else getattr(bbox, "height", 0.0))
                            dims = [round(w, 2), round(d, 2), round(h, 2)]

                    models.append({
                        "id": node_id,
                        "name": node_name or "Model",
                        "dimensions_mm": dims,
                        "position": pos,
                        "rotation_deg": rot
                    })
                except Exception as child_err:
                    logger.debug("Failed to inspect scene child node: %s", child_err)
        except Exception as e:
            logger.debug("Failed to query live Cura scene: %s", e)

        # Query global container stack settings
        printer_info = {
            "model": "Stereotech 520 V2",
            "kinematics": "5D Multi-Axis (3 Linear + 2 Rotary C/B)",
            "nozzle_diameter_mm": 0.4
        }
        current_mode = ""
        current_material = ""
        current_profile = ""
        available_materials = []
        available_profiles = []
        key_params = {}

        try:
            registry = app.getContainerRegistry() if hasattr(app, "getContainerRegistry") else None
            if registry is None:
                try:
                    from UM.Settings.ContainerRegistry import ContainerRegistry
                    registry = ContainerRegistry.getInstance()
                except Exception:
                    pass

            unique = {}
            if registry is not None:
                # 1. Parse materials from registry
                for finder_name in ("findInstanceContainersMetadata", "findContainersMetadata"):
                    finder = getattr(registry, finder_name, None)
                    if finder:
                        try:
                            found_md = finder(type="material") or []
                            for md in found_md:
                                if isinstance(md, dict) and md.get("name"):
                                    name = str(md.get("name") or "")
                                    cid = str(md.get("id") or "")
                                    mat_type = str(md.get("material") or "")
                                    if name and not name.lower().startswith("empty") and not cid.lower().startswith("empty"):
                                        unique[cid or name] = {
                                            "name": name,
                                            "id": cid,
                                            "material": mat_type
                                        }
                        except Exception:
                            pass

                for finder_name in ("findInstanceContainers", "findContainers"):
                    finder = getattr(registry, finder_name, None)
                    if finder:
                        try:
                            found = finder(type="material") or []
                            for cont in found:
                                name = str(getattr(cont, "getName", lambda: "")() or "")
                                cid = str(getattr(cont, "getId", lambda: "")() or "")
                                mat_type = str(getattr(cont, "getMetaDataEntry", lambda k, d="": "")("material", "") or "")
                                if name and not name.lower().startswith("empty") and (cid or name) not in unique:
                                    unique[cid or name] = {"name": name, "id": cid, "material": mat_type}
                        except Exception:
                            pass

                # 2. Parse quality profiles from registry
                for finder_name in ("findInstanceContainersMetadata", "findContainersMetadata"):
                    finder = getattr(registry, finder_name, None)
                    if finder:
                        try:
                            found_md = finder(type="quality") or []
                            for md in found_md:
                                if isinstance(md, dict) and md.get("name"):
                                    pname = str(md.get("name") or "")
                                    pid = str(md.get("id") or "")
                                    if pname and not pname.lower().startswith("empty"):
                                        if not any(p.get("id") == pid for p in available_profiles):
                                            available_profiles.append({"name": pname, "id": pid})
                        except Exception:
                            pass

            manager_getter = getattr(app, "getMaterialManager", None)
            if manager_getter:
                try:
                    mgr = manager_getter()
                    if mgr and hasattr(mgr, "_material_group_map"):
                        for group in mgr._material_group_map.values():
                            root = getattr(group, "root_material_node", None)
                            cont = root.getContainer() if root and hasattr(root, "getContainer") else None
                            if cont:
                                name = str(getattr(cont, "getName", lambda: "")() or "")
                                cid = str(getattr(cont, "getId", lambda: "")() or "")
                                if name and not name.lower().startswith("empty") and (cid or name) not in unique:
                                    unique[cid or name] = {"name": name, "id": cid}
                except Exception:
                    pass

            if not unique:
                fallback_defaults = [
                    ("Generic CFF PA", "generic_cffpa", "CFF PA"),
                    ("Generic PETG", "generic_petg_175", "PETG"),
                    ("Generic PLA", "generic_pla_175", "PLA"),
                    ("Generic ABS", "generic_abs_175", "ABS"),
                    ("Generic TPU 95A", "generic_tpu_175", "TPU"),
                    ("Generic Nylon", "generic_nylon_175", "Nylon"),
                ]
                for n, cid, m in fallback_defaults:
                    unique[cid] = {"name": n, "id": cid, "material": m}

            material_meta_map = {
                "cff": {"temp_nozzle": 265, "temp_bed": 70, "fan": 0, "aliases": ["PA6-CF", "Carbon Nylon", "PA-CF", "CFF PA"]},
                "petg": {"temp_nozzle": 235, "temp_bed": 75, "fan": 40, "aliases": ["PETG", "Generic PETG"]},
                "pla": {"temp_nozzle": 205, "temp_bed": 60, "fan": 100, "aliases": ["PLA", "Generic PLA"]},
                "abs": {"temp_nozzle": 240, "temp_bed": 100, "fan": 0, "aliases": ["ABS", "Generic ABS"]},
                "tpu": {"temp_nozzle": 225, "temp_bed": 60, "fan": 20, "aliases": ["TPU", "Flex", "TPU 95A"]},
                "nylon": {"temp_nozzle": 250, "temp_bed": 80, "fan": 0, "aliases": ["Nylon", "PA12", "PA6"]},
                "pc": {"temp_nozzle": 280, "temp_bed": 110, "fan": 0, "aliases": ["PC", "Polycarbonate"]},
                "asa": {"temp_nozzle": 250, "temp_bed": 100, "fan": 10, "aliases": ["ASA"]},
            }
            enriched = []
            for item in unique.values():
                mat_key = (str(item.get("material") or "") + " " + str(item.get("name") or "")).lower()
                meta = None
                for k, v in material_meta_map.items():
                    if k in mat_key:
                        meta = v
                        break
                entry = dict(item)
                if meta:
                    entry["recommended_temp_nozzle"] = meta["temp_nozzle"]
                    entry["recommended_temp_bed"] = meta["temp_bed"]
                    entry["recommended_fan"] = meta["fan"]
                    entry["aliases"] = meta["aliases"]
                enriched.append(entry)
            available_materials = enriched

            if not available_profiles:
                available_profiles = [
                    {"name": "Normal (0.2 mm)", "id": "normal"},
                    {"name": "Fast (0.2 mm)", "id": "fast"},
                    {"name": "Draft (0.3 mm)", "id": "draft"},
                    {"name": "High (0.15 mm)", "id": "high"}
                ]

            stack = app.getGlobalContainerStack() if hasattr(app, "getGlobalContainerStack") else None
            if stack:
                if hasattr(stack, "getName"):
                    printer_info["model"] = stack.getName()

                if hasattr(stack, "material") and stack.material:
                    current_material = stack.material.getName()
                if not current_material or current_material.lower() in ("empty_material", "empty", "none", ""):
                    extruders = getattr(stack, "extruders", {})
                    if isinstance(extruders, dict):
                        for ext in extruders.values():
                            if hasattr(ext, "material") and ext.material:
                                mname = str(getattr(ext.material, "getName", lambda: "")() or "")
                                if mname and not mname.lower().startswith("empty"):
                                    current_material = mname
                                    break
                quality = getattr(stack, "quality", None)
                if quality is not None and hasattr(quality, "getName"):
                    current_profile = str(quality.getName())

                mode_val = stack.getProperty("ste_print_mode", "value")
                if not mode_val or mode_val not in ("5D", "3D"):
                    mode_val = stack.getProperty("printing_mode", "value")
                    if mode_val == "classic":
                        mode_val = "3D"
                    elif mode_val in ("cylindrical_full", "spiral_5d", "5D"):
                        mode_val = "5D"
                if mode_val in ("5D", "3D"):
                    current_mode = mode_val

                lh = stack.getProperty("layer_height", "value")
                if lh is not None:
                    key_params["layer_height_mm"] = float(lh)

                walls = stack.getProperty("wall_line_count", "value")
                if walls is not None:
                    key_params["wall_line_count"] = int(walls)

                infill = stack.getProperty("infill_sparse_density", "value")
                if infill is not None:
                    key_params["infill_density_pct"] = float(infill)

                temp = stack.getProperty("material_print_temperature", "value")
                if temp is not None:
                    key_params["print_temperature_c"] = float(temp)

                bed = stack.getProperty("material_bed_temperature", "value")
                if bed is not None:
                    key_params["bed_temperature_c"] = float(bed)

                fan = stack.getProperty("cool_fan_speed", "value")
                if fan is not None:
                    key_params["fan_speed_pct"] = float(fan)

                supp = stack.getProperty("support_enable", "value")
                if supp is not None:
                    key_params["support_enabled"] = bool(supp)
        except Exception as e:
            logger.debug("Failed to query Cura container stack: %s", e)

        return {
            "printer": printer_info,
            "loaded_models": models,
            "current_mode": current_mode,
            "current_material": current_material,
            "current_profile": current_profile,
            "available_materials": available_materials,
            "available_profiles": available_profiles,
            "key_parameters": key_params
        }

    def _build_fallback_snapshot(self):
        # type: () -> Dict[str, Any]
        """Builds a realistic fallback snapshot when CuraApplication is not active."""
        models = []
        for idx, path in enumerate(self.attached_models, start=1):
            models.append({
                "id": "mesh_{0:02d}".format(idx),
                "name": os.path.basename(path),
                "path": path,
                "dimensions_mm": [60.0, 60.0, 25.0],
                "position": [0.0, 0.0, 0.0],
                "rotation_deg": [0.0, 0.0, 0.0]
            })

        return {
            "printer": {
                "model": "Stereotech 530 Hybrid",
                "kinematics": "5D Multi-Axis (3 Linear + 2 Rotary C/B)",
                "nozzle_diameter_mm": 0.4,
                "max_build_volume_mm": [250, 250, 250]
            },
            "loaded_models": models,
            "current_mode": "3D",
            "current_material": "Generic PETG",
            "current_profile": "Standard",
            "available_materials": [
                {"name": "Generic CFF PA", "id": "generic_cffpa", "material": "CFF PA", "recommended_temp_nozzle": 265, "recommended_temp_bed": 70, "aliases": ["PA6-CF", "Carbon Nylon", "PA-CF", "CFF PA"]},
                {"name": "Generic PETG", "id": "generic_petg_175", "material": "PETG", "recommended_temp_nozzle": 235, "recommended_temp_bed": 75, "aliases": ["PETG"]},
                {"name": "Generic PLA", "id": "generic_pla_175", "material": "PLA", "recommended_temp_nozzle": 205, "recommended_temp_bed": 60, "aliases": ["PLA"]},
                {"name": "Generic ABS", "id": "generic_abs_175", "material": "ABS", "recommended_temp_nozzle": 240, "recommended_temp_bed": 100, "aliases": ["ABS"]},
                {"name": "Generic TPU 95A", "id": "generic_tpu_175", "material": "TPU", "recommended_temp_nozzle": 225, "recommended_temp_bed": 60, "aliases": ["TPU", "Flex"]},
            ],
            "available_profiles": [
                {"name": "Normal (0.2 mm)", "id": "normal"},
                {"name": "Fast (0.2 mm)", "id": "fast"},
                {"name": "Draft (0.3 mm)", "id": "draft"},
                {"name": "High (0.15 mm)", "id": "high"}
            ],
            "key_parameters": {}
        }

    @staticmethod
    def _quaternion_to_euler_degrees(q):
        # type: (Any) -> Tuple[float, float, float]
        """Converts a Quaternion object to Euler angles (rx, ry, rz) in degrees."""
        if hasattr(q, "toEulerAngles"):
            try:
                angles = q.toEulerAngles()
                ax = float(angles.x() if callable(getattr(angles, "x", None)) else getattr(angles, "x", 0.0))
                ay = float(angles.y() if callable(getattr(angles, "y", None)) else getattr(angles, "y", 0.0))
                az = float(angles.z() if callable(getattr(angles, "z", None)) else getattr(angles, "z", 0.0))
                return round(ax, 2), round(ay, 2), round(az, 2)
            except Exception:
                pass
        if hasattr(q, "toEuler"):
            try:
                angles = q.toEuler()
                return round(float(angles[0]), 2), round(float(angles[1]), 2), round(float(angles[2]), 2)
            except Exception:
                pass

        try:
            x = float(q.x() if callable(getattr(q, "x", None)) else getattr(q, "x", 0.0))
            y = float(q.y() if callable(getattr(q, "y", None)) else getattr(q, "y", 0.0))
            z = float(q.z() if callable(getattr(q, "z", None)) else getattr(q, "z", 0.0))
            w = float(q.w() if callable(getattr(q, "w", None)) else getattr(q, "w", 1.0))

            # Roll (X-axis)
            sinr_cosp = 2.0 * (w * x + y * z)
            cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
            roll = math.atan2(sinr_cosp, cosr_cosp)

            # Pitch (Y-axis)
            sinp = 2.0 * (w * y - z * x)
            if abs(sinp) >= 1.0:
                pitch = math.copysign(math.pi / 2.0, sinp)
            else:
                pitch = math.asin(sinp)

            # Yaw (Z-axis)
            siny_cosp = 2.0 * (w * z + x * y)
            cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
            yaw = math.atan2(siny_cosp, cosy_cosp)

            return (
                round(math.degrees(roll), 2),
                round(math.degrees(pitch), 2),
                round(math.degrees(yaw), 2)
            )
        except Exception:
            return (0.0, 0.0, 0.0)

    def build_messages_payload(self, system_prompt):
        # type: (str) -> List[Dict[str, Any]]
        """
        Assembles the complete messages array for the OpenAI Chat Completions API.

        Prepends the system prompt and includes all recorded dialogue turns.

        Args:
            system_prompt: System prompt text.

        Returns:
            List[Dict[str, Any]]: Full payload ready for chat_completion().
        """
        payload = []
        if system_prompt:
            payload.append({
                "role": "system",
                "content": system_prompt
            })

        for msg in self.messages:
            payload.append(dict(msg))

        return payload

    def get_messages(self):
        # type: () -> List[Dict[str, Any]]
        """Returns a copy of the current message history."""
        return [dict(m) for m in self.messages]

    def get_attached_models(self):
        # type: () -> List[str]
        """Returns the list of 3D model paths attached during the session."""
        return list(self.attached_models)

    def set_slicer_snapshot(self, snapshot):
        # type: (Optional[Dict[str, Any]]) -> None
        """Allows injecting or mocking the slicer state snapshot."""
        self._mock_snapshot = snapshot

    def clear(self):
        # type: () -> None
        """Clears all conversation turns and attached models."""
        self.messages = []
        self.attached_models = []
        self._mock_snapshot = None
        logger.debug("Conversation context cleared.")
