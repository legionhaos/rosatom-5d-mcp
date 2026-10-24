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

    def __init__(self):
        # type: () -> None
        """Initializes empty message history and attached models tracking."""
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
                return MainThreadDispatcher.call_on_main_thread(self._query_cura_state)
            except Exception as e:
                logger.debug("MainThreadDispatcher execution failed: %s. Using direct query.", e)

        return self._query_cura_state()

    def _query_cura_state(self):
        # type: () -> Dict[str, Any]
        """Internal method querying live CuraApplication instance."""
        app = None
        try:
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
        except Exception:
            try:
                import sys
                if "cura.CuraApplication" in sys.modules:
                    app = sys.modules["cura.CuraApplication"].CuraApplication.getInstance()
            except Exception:
                app = None

        # If live CuraApplication is not available (e.g. in tests/headless), return mock or fallback
        if app is None:
            if self._mock_snapshot is not None:
                return dict(self._mock_snapshot)
            return self._build_fallback_snapshot()

        # Query live scene models
        models = []  # type: List[Dict[str, Any]]
        try:
            scene = app.getController().getScene()
            root = scene.getRoot()
            for child in root.getChildren():
                if hasattr(child, "getMeshData") and child.getMeshData() is not None:
                    node_name = child.getName() if hasattr(child, "getName") else "Unnamed_Mesh"
                    node_id = str(child.getId()) if hasattr(child, "getId") else "node"

                    # Position
                    pos = [0.0, 0.0, 0.0]
                    if hasattr(child, "getPosition"):
                        p = child.getPosition()
                        pos = [round(float(p.x()), 2), round(float(p.y()), 2), round(float(p.z()), 2)]

                    # Rotation
                    rot = [0.0, 0.0, 0.0]
                    if hasattr(child, "getOrientation"):
                        rot = list(self._quaternion_to_euler_degrees(child.getOrientation()))

                    # Dimensions
                    dims = [0.0, 0.0, 0.0]
                    if hasattr(child, "getBoundingBox"):
                        bbox = child.getBoundingBox()
                        if bbox:
                            dims = [
                                round(float(bbox.width()), 2),
                                round(float(bbox.depth()), 2),
                                round(float(bbox.height()), 2)
                            ]

                    models.append({
                        "id": node_id,
                        "name": node_name,
                        "dimensions_mm": dims,
                        "position": pos,
                        "rotation_deg": rot
                    })
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
            if registry is not None:
                finder = getattr(registry, "findContainers", None) or getattr(registry, "findInstanceContainers", None)
                if finder is not None:
                    containers = finder(type="material") or []
                    available_materials = [str(c.getName()) for c in containers if hasattr(c, "getName")]
            stack = app.getGlobalContainerStack()
            if stack:
                if hasattr(stack, "getName"):
                    printer_info["model"] = stack.getName()

                if hasattr(stack, "material") and stack.material:
                    current_material = stack.material.getName()
                quality = getattr(stack, "quality", None)
                if quality is not None and hasattr(quality, "getName"):
                    current_profile = str(quality.getName())

                mode_val = stack.getProperty("ste_print_mode", "value")
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
                "model": "Stereotech 520 V2",
                "kinematics": "5D Multi-Axis (3 Linear + 2 Rotary C/B)",
                "nozzle_diameter_mm": 0.4,
                "max_build_volume_mm": [250, 250, 250]
            },
            "loaded_models": models,
            "current_mode": "",
            "current_material": "",
            "current_profile": "",
            "available_materials": [],
            "available_profiles": [],
            "key_parameters": {}
        }

    @staticmethod
    def _quaternion_to_euler_degrees(q):
        # type: (Any) -> Tuple[float, float, float]
        """Converts a Quaternion object to Euler angles (rx, ry, rz) in degrees."""
        if hasattr(q, "toEulerAngles"):
            angles = q.toEulerAngles()
            return round(float(angles.x()), 2), round(float(angles.y()), 2), round(float(angles.z()), 2)
        if hasattr(q, "toEuler"):
            angles = q.toEuler()
            return round(float(angles[0]), 2), round(float(angles[1]), 2), round(float(angles[2]), 2)

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
