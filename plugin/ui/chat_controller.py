"""QObject bridge between QML and the agent/slicer layers.

The controller intentionally does not implement an LLM or fake responses. The
agent backend is injected by the plugin bootstrap and may expose one of:
``send_prompt(text, attachments)``, ``submit_prompt(...)`` or
``handle_prompt(...)``. Backend signals can be connected by the plugin to the
public slots below, keeping QML independent from the agent implementation.
"""

import json
import mimetypes
import os
import subprocess
import tempfile
import time
import re
import logging

logger = logging.getLogger("ChatController")

try:
    from urllib.parse import unquote, urlparse
except ImportError:
    from urlparse import unquote, urlparse

try:
    from PyQt5.QtCore import QTimer, QUrl
except ImportError:
    QTimer = None
    QUrl = None

try:
    from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
except ImportError:
    try:
        from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
    except ImportError:
        try:
            from PySide2.QtCore import QObject, Property as pyqtProperty, Signal as pyqtSignal, Slot as pyqtSlot
        except ImportError:
            try:
                from PySide6.QtCore import QObject, Property as pyqtProperty, Signal as pyqtSignal, Slot as pyqtSlot
            except ImportError:
                class QObject(object):
                    def __init__(self, parent=None):
                        self.parent = parent

                def pyqtProperty(*args, **kwargs):
                    def _dec(f):
                        return property(f)
                    return _dec

                def pyqtSlot(*args, **kwargs):
                    def _dec(f):
                        return f
                    return _dec

                class pyqtSignal(object):
                    def __init__(self, *types):
                        self._slots = []
                    def emit(self, *args):
                        for s in list(self._slots):
                            try:
                                s(*args)
                            except Exception:
                                pass
                    def connect(self, slot):
                        if slot not in self._slots:
                            self._slots.append(slot)
                    def disconnect(self, slot):
                        if slot in self._slots:
                            self._slots.remove(slot)


from .message_models import AttachmentListModel, MessageListModel, ToolLogModel


class ChatController(QObject):
    messageAdded = pyqtSignal()
    taskStarted = pyqtSignal(str)
    taskFinished = pyqtSignal()
    toolStarted = pyqtSignal(str, str)
    toolFinished = pyqtSignal(str, str)
    responseReady = pyqtSignal(str)
    taskFailed = pyqtSignal(str)
    settingsSaved = pyqtSignal()
    settingsSaveFailed = pyqtSignal(str)
    connectionCheckFinished = pyqtSignal(bool, str)
    screenshotRequested = pyqtSignal()
    exportRequested = pyqtSignal(str)
    exportFinished = pyqtSignal(bool, str, str)
    parameterApplyFinished = pyqtSignal(bool, str)

    connectedChanged = pyqtSignal()
    printerChanged = pyqtSignal()
    printModeChanged = pyqtSignal()
    materialChanged = pyqtSignal()
    modelCountChanged = pyqtSignal()
    busyChanged = pyqtSignal()
    slicingProgressChanged = pyqtSignal()
    printResultChanged = pyqtSignal()
    previewChanged = pyqtSignal()
    recommendationChanged = pyqtSignal()
    cameraAngleChanged = pyqtSignal()
    _previewScheduled = pyqtSignal()

    def __init__(self, agent_backend=None, slicer_bridge=None, settings_store=None, extension=None, parent=None):
        super().__init__(parent)
        self._agent = agent_backend
        self._slicer = slicer_bridge
        self._settings = settings_store
        self._extension = extension
        self._messages = MessageListModel(self)
        self._attachments = AttachmentListModel(self)
        self._tools = ToolLogModel(self)
        self._busy = False
        self._connected = False
        self._printer = "Stereotech Hybrid 530 V5.2.4"
        self._print_mode = "3D"
        self._material = "Не выбран"
        self._model_count = 0
        self._slicing_progress = 0
        self._print_time = ""
        self._material_usage = ""
        self._active_tools = {}
        self._preview_url = ""
        self._preview_message = "Превью появится после загрузки модели"
        self._model_info = ""
        self._dimensions_text = ""
        self._current_angle = "3d_isometric"
        self._preview_counter = 0
        self._preview_path = ""
        self._rendering_preview = False
        self._preview_timer = None

        # Recommendation fields populated from summary_card
        self._profile_name = "Стандартный профиль"
        self._layer_height = "0.20 мм"
        self._wall_line_count = "4 линии"
        self._infill_density = "50%"
        self._infill_pattern = "Gyroid"
        self._print_temp = "250 °C"
        self._bed_temp = "85 °C"
        self._fan_speed = "0%"
        self._support_enabled = False
        self._support_text = "Отключены"
        self._rotation_deg = [0.0, 0.0, 0.0]
        self._last_recommendation = ""
        self._export_status = ""
        self._exported_directory = ""
        self._last_gcode_path = ""

        if QTimer is not None:
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(400)
            self._preview_timer.timeout.connect(self.refreshPreview)
            self._previewScheduled.connect(self._startPreviewTimer)
        self._connect_backend_signals()

    @pyqtProperty(QObject, constant=True)
    def messageModel(self):
        return self._messages

    @pyqtProperty(QObject, constant=True)
    def attachmentModel(self):
        return self._attachments

    @pyqtProperty(QObject, constant=True)
    def toolLogModel(self):
        return self._tools

    @pyqtSlot(result=str)
    def copyToolLog(self):
        lines = []
        for item in self._tools.items:
            lines.append("[{0}] {1} | {2} | {3} ms\nArgs: {4}\nResult: {5}".format(
                item.get("status", ""), item.get("toolName", ""), item.get("label", ""),
                item.get("durationMs", 0), item.get("arguments", ""), item.get("result", "")
            ))
        text = "\n\n".join(lines) or "Журнал вызовов пуст."
        try:
            from PyQt5.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(text)
        except ImportError:
            try:
                from PySide2.QtGui import QGuiApplication
                QGuiApplication.clipboard().setText(text)
            except Exception:
                pass
        except Exception:
            pass
        return text

    @pyqtProperty(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @pyqtProperty(bool, notify=connectedChanged)
    def connected(self):
        return self._connected

    @pyqtSlot(bool)
    def setConnected(self, value):
        val = bool(value)
        if self._connected != val:
            self._connected = val
            self.connectedChanged.emit()

    @pyqtProperty(str, notify=printerChanged)
    def printerName(self):
        return self._printer

    @pyqtProperty(str, notify=printModeChanged)
    def printMode(self):
        return self._print_mode

    @pyqtProperty(str, notify=materialChanged)
    def material(self):
        return self._material

    @pyqtProperty(int, notify=modelCountChanged)
    def modelCount(self):
        live = max(self._attached_model_count(), self._scene_model_count())
        if live != self._model_count:
            self._model_count = live
        return self._model_count

    @pyqtProperty(str, notify=previewChanged)
    def previewUrl(self):
        return self._preview_url

    @pyqtProperty(str, notify=previewChanged)
    def previewMessage(self):
        return self._preview_message

    @pyqtProperty(str, notify=previewChanged)
    def modelInfo(self):
        return self._model_info

    @pyqtProperty(str, notify=previewChanged)
    def dimensionsText(self):
        return self._dimensions_text

    @pyqtProperty(str, notify=cameraAngleChanged)
    def currentAngle(self):
        return self._current_angle

    @pyqtProperty(int, notify=slicingProgressChanged)
    def slicingProgress(self):
        return self._slicing_progress

    @pyqtProperty(str, notify=printResultChanged)
    def printTime(self):
        return self._print_time

    @pyqtProperty(str, notify=printResultChanged)
    def materialUsage(self):
        return self._material_usage

    @pyqtProperty(str, notify=recommendationChanged)
    def profileName(self):
        return self._profile_name

    @pyqtProperty(str, notify=recommendationChanged)
    def layerHeight(self):
        return self._layer_height

    @pyqtProperty(str, notify=recommendationChanged)
    def wallLineCount(self):
        return self._wall_line_count

    @pyqtProperty(str, notify=recommendationChanged)
    def infillDensity(self):
        return self._infill_density

    @pyqtProperty(str, notify=recommendationChanged)
    def infillPattern(self):
        return self._infill_pattern

    @pyqtProperty(str, notify=recommendationChanged)
    def printTemperature(self):
        return self._print_temp

    @pyqtProperty(str, notify=recommendationChanged)
    def bedTemperature(self):
        return self._bed_temp

    @pyqtProperty(bool, notify=recommendationChanged)
    def supportEnabled(self):
        return self._support_enabled

    @pyqtProperty(str, notify=recommendationChanged)
    def supportText(self):
        return self._support_text

    @pyqtProperty(str, notify=recommendationChanged)
    def rotationText(self):
        rot = self._rotation_deg
        if isinstance(rot, (list, tuple)) and len(rot) >= 3:
            return "X: {0:.0f}°, Y: {1:.0f}°, Z: {2:.0f}°".format(rot[0], rot[1], rot[2])
        return "Без поворота"

    @pyqtProperty(str, notify=recommendationChanged)
    def lastRecommendation(self):
        return self._last_recommendation

    @pyqtProperty(str, notify=recommendationChanged)
    def exportStatus(self):
        return self._export_status

    @pyqtProperty(str, notify=recommendationChanged)
    def exportedDirectory(self):
        return self._exported_directory

    @pyqtProperty(str, notify=recommendationChanged)
    def gcodePath(self):
        return self._last_gcode_path

    @pyqtProperty(str, notify=settingsSaved)
    def baseUrl(self):
        if self._settings is not None:
            return str(self._settings.get("api_url") or "")
        return ""

    @pyqtProperty(str, notify=settingsSaved)
    def apiKey(self):
        if self._settings is not None:
            return str(self._settings.get("api_key") or "")
        return ""

    @pyqtProperty(str, notify=settingsSaved)
    def modelName(self):
        if self._settings is not None:
            return str(self._settings.get("model_name") or "")
        return ""

    def _set_busy(self, value):
        value = bool(value)
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    def _now(self):
        return time.strftime("%H:%M:%S")

    def _connect_backend_signals(self):
        if self._agent is None:
            return
        signal_map = {
            "stepStarted": self.onAgentStepStarted,
            "toolCallStarted": self.onToolCallStarted,
            "toolCallFinished": self.onToolCallFinished,
            "responseReady": self.onAgentResponse,
            "taskFailed": self.onAgentError,
        }
        for name, slot in signal_map.items():
            signal = getattr(self._agent, name, None)
            if signal is not None and hasattr(signal, "connect"):
                try:
                    signal.connect(slot)
                except (TypeError, RuntimeError):
                    pass

    def _fail(self, message):
        self._set_busy(False)
        self._messages.append_system(message, self._now(), "error")
        self.taskFailed.emit(message)
        self.messageAdded.emit()

    @pyqtSlot()
    def applyRecommendation(self):
        """Apply the current recommendation directly to slicer without an LLM call."""
        def scalar(value, default):
            if isinstance(value, dict):
                value = value.get("new", value.get("value", default))
            return default if value is None else value

        def number(value, default, suffix=""):
            value = scalar(value, default)
            if isinstance(value, str):
                value = value.replace(suffix, "").strip()
            return float(value)

        try:
            payload = {
                "layer_height": number(self._layer_height, 0.2, "мм"),
                "infill_sparse_density": number(self._infill_density, 50, "%"),
                "wall_line_count": int(number(self._wall_line_count, 4, " линии")),
                "material_print_temperature": number(self._print_temp, 250, "°C"),
                "material_bed_temperature": number(self._bed_temp, 85, "°C"),
                "support_enable": bool(scalar(self._support_enabled, False)),
            }
        except (TypeError, ValueError) as exc:
            self._fail("Некорректное значение параметра: {0}".format(exc))
            return
        if self._agent is None:
            self._fail("Agent backend не подключён.")
            return
        apply_direct = getattr(self._agent, "apply_parameters", None)
        if apply_direct is None:
            self._fail("Прямое применение параметров недоступно в backend.")
            return
        try:
            ok, result = apply_direct(payload)
            if not ok:
                self._fail(str(result.get("error") or "Не удалось применить параметры."))
                return
            applied = result.get("applied_overrides") or {}
            normalized = {key: item.get("new", item.get("value")) if isinstance(item, dict) else item
                          for key, item in applied.items()}
            self._update_parameters_from_dict(normalized)
            self._messages.append_system("Параметры применены к STE Slicer. G-code не запускался.", self._now(), "ok")
            self.messageAdded.emit()
        except Exception as exc:
            self._fail("Не удалось применить параметры: {0}".format(exc))

    @pyqtSlot(str, str, str, str, str, bool)
    def applyParameters(self, layer_height, infill_density, wall_count, nozzle_temp, bed_temp, supports):
        """Apply editable profile fields through the existing MCP tool."""
        if self._agent is None or self._busy:
            return
        try:
            values = [float(layer_height), float(infill_density), float(wall_count), float(nozzle_temp), float(bed_temp)]
            if not 0.05 <= values[0] <= 2.0 or not 0 <= values[1] <= 100 or not 1 <= values[2] <= 20:
                raise ValueError("Проверьте высоту слоя, заполнение и число стенок.")
            if not 150 <= values[3] <= 350 or not 0 <= values[4] <= 150:
                raise ValueError("Проверьте температуры сопла и стола.")
        except (TypeError, ValueError) as exc:
            self._fail(str(exc))
            return
        payload = {
            "layer_height": float(layer_height),
            "infill_sparse_density": float(infill_density),
            "wall_line_count": int(float(wall_count)),
            "material_print_temperature": float(nozzle_temp),
            "material_bed_temperature": float(bed_temp),
            "support_enable": bool(supports)
        }
        direct_apply = getattr(self._agent, "apply_parameters", None)
        if direct_apply is not None:
            try:
                ok, result = direct_apply(payload)
                if ok:
                    applied = result.get("applied_overrides") or {}
                    normalized = {key: item.get("new", item.get("value")) if isinstance(item, dict) else item
                                  for key, item in applied.items()}
                    self._update_parameters_from_dict(normalized)
                    self._messages.append_system("Параметры применены к STE Slicer без запуска слайсинга.", self._now(), "ok")
                    self.messageAdded.emit()
                else:
                    self._fail(str(result.get("error") or "Не удалось применить параметры."))
            except Exception as exc:
                self._fail("Не удалось применить параметры: {0}".format(exc))
            return
        prompt = "Примени текущую рекомендацию к слайсеру. Не запускай слайсинг. " + json.dumps(payload, ensure_ascii=False)
        self.sendPrompt(prompt)

    @pyqtSlot(str)
    def sendPrompt(self, text):
        text = (text or "").strip()
        if not text or self._busy:
            return
        paths = self._attachments.paths()
        self._messages.append_user(text, self._now(), len(paths))
        self.messageAdded.emit()
        if self._agent is None:
            self._fail("Agent backend не подключён. Подключите AgentWorker при запуске плагина.")
            return
        self._set_busy(True)
        self.taskStarted.emit(text)
        try:
            method = getattr(self._agent, "send_prompt", None)
            if method is None:
                method = getattr(self._agent, "submit_prompt", None)
            if method is None:
                method = getattr(self._agent, "handle_prompt", None)
            if method is None:
                self._fail("Agent backend не предоставляет send_prompt().")
                return
            result = method(text, paths)
            if result is not None:
                self.onAgentResponse(result)
        except Exception as exc:
            self._fail("Не удалось отправить запрос агенту: {0}".format(exc))

    @pyqtSlot(str)
    def addAttachment(self, path):
        raw_path = str(path or "").strip()
        if raw_path.startswith("file:"):
            parsed = urlparse(raw_path)
            path = unquote(parsed.path or "")
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                path = "//{0}{1}".format(parsed.netloc, path)
            elif len(path) >= 3 and path[0] == "/" and path[2] == ":":
                path = path[1:]
        else:
            path = raw_path
        path = os.path.normpath(path)
        if not path or not os.path.isfile(path):
            self._fail("Файл не найден: {0}".format(path))
            return
        extension = os.path.splitext(path)[1].lower()
        model_extensions = (".stl", ".obj", ".3mf")
        image_extensions = (".jpg", ".jpeg", ".png")
        if extension not in model_extensions + image_extensions:
            self._fail("Формат не поддерживается: {0}".format(extension))
            return
        kind = "model" if extension in model_extensions else "image"
        size = os.path.getsize(path)
        size_text = "{0:.1f} KB".format(size / 1024.0) if size < 1024 * 1024 else "{0:.1f} MB".format(size / 1024.0 / 1024.0)
        self._attachments.append_file(os.path.basename(path), path, kind, size_text)
        self.refreshModelCount()
        self.modelCountChanged.emit()
        self.messageAdded.emit()
        self.refreshPreview()

    def _attached_model_count(self):
        return len([p for p in self._attachments.paths() if os.path.splitext(p)[1].lower() in (".stl", ".obj", ".3mf")])

    def _scene_model_count(self):
        return len(self._scene_nodes())

    def onSceneChanged(self, source=None, *args):
        if self._rendering_preview:
            return
        try:
            from UM.Scene.Camera import Camera
            if isinstance(source, Camera):
                return
        except Exception:
            pass
        self.refreshModelCount()
        self._previewScheduled.emit()

    def _startPreviewTimer(self):
        if self._preview_timer is not None:
            self._preview_timer.start()

    def _get_application_instance(self):
        app = None
        for mod_name in ("steslicer.SteSlicerApplication", "cura.CuraApplication", "UM.Application"):
            try:
                mod = __import__(mod_name, fromlist=["SteSlicerApplication", "CuraApplication", "Application"])
                for attr in ("SteSlicerApplication", "CuraApplication", "Application"):
                    cls_ = getattr(mod, attr, None)
                    if cls_ and hasattr(cls_, "getInstance"):
                        inst = cls_.getInstance()
                        if inst:
                            app = inst
                            break
            except Exception:
                pass
            if app is not None:
                break
        return app

    def _scene_nodes(self):
        try:
            app = self._get_application_instance()
            if app is None:
                return []
            controller = getattr(app, "getController", lambda: None)()
            scene = controller.getScene() if controller else None
            if scene is None:
                return []
            root = scene.getRoot()
            if root is None:
                return []

            all_nodes = root.getAllChildren() if hasattr(root, "getAllChildren") else getattr(root, "getChildren", lambda: [])()

            candidates = []
            for node in all_nodes:
                if not (hasattr(node, "getMeshData") and node.getMeshData() is not None):
                    continue
                node_type = type(node).__name__.lower()
                node_name = str(getattr(node, "getName", lambda: "")() or "").lower()
                helper_tokens = ("buildplate", "build_plate", "build plate", "grid", "convexhull", "convex_hull", "hull")
                if any(token in node_type or token in node_name for token in helper_tokens):
                    continue
                if hasattr(node, "getHull"):
                    continue
                if hasattr(node, "callDecoration"):
                    try:
                        if node.callDecoration("isNonPrintingMesh"):
                            continue
                    except Exception:
                        pass
                parent = getattr(node, "getParent", lambda: None)()
                if parent is not None and getattr(parent, "getMeshData", lambda: None)() is not None:
                    continue
                candidates.append(node)

            def _is_sliceable(n):
                if hasattr(n, "callDecoration") and n.callDecoration("isSliceable"):
                    return True
                p = getattr(n, "getParent", lambda: None)()
                if p and hasattr(p, "callDecoration") and p.callDecoration("isSliceable"):
                    return True
                return False

            sliceable = [n for n in candidates if _is_sliceable(n)]
            if sliceable:
                return sliceable

            named = [
                n for n in candidates
                if getattr(n, "getName", lambda: "")() and getattr(n, "getName", lambda: "")() not in ("", "Unnamed_Mesh")
            ]
            if named:
                return named

            return candidates
        except Exception:
            return []

    def _describe_models(self, nodes):
        parts = []
        dims_part = ""
        for node in nodes[:3]:
            name = node.getName() if hasattr(node, "getName") else "model"
            try:
                box = node.getBoundingBox()
                parts.append("{0} · {1:.0f}×{2:.0f}×{3:.0f} мм".format(name, box.width, box.depth, box.height))
                if not dims_part:
                    dims_part = "{0:.0f} × {1:.0f} × {2:.0f} мм".format(box.width, box.depth, box.height)
            except Exception:
                parts.append(name)
        if len(nodes) > 3:
            parts.append("и ещё {0}".format(len(nodes) - 3))
        self._dimensions_text = dims_part or ("Моделей на столе: {0}".format(len(nodes)) if nodes else "")
        return "\n".join(parts)

    def _set_preview(self, url, message, info):
        self._preview_url = url
        self._preview_message = message
        self._model_info = info
        self.previewChanged.emit()

    def _remove_snapshot_cameras(self):
        try:
            from UM.Application import Application
            from UM.Scene.Camera import Camera
            root = Application.getInstance().getController().getScene().getRoot()
            for child in list(root.getChildren()):
                if isinstance(child, Camera) and child.getName() == "snapshot":
                    root.removeChild(child)
        except Exception:
            pass

    @pyqtSlot()
    def refreshPreview(self):
        if self._rendering_preview:
            return
        nodes = self._scene_nodes()
        if not nodes:
            self._set_preview("", "Загрузите модель STL/3MF на стол STE Slicer", "")
            return
        info = self._describe_models(nodes)
        self._rendering_preview = True
        try:
            try:
                from steslicer.Snapshot import Snapshot
            except ImportError:
                from cura.Snapshot import Snapshot
            try:
                image = Snapshot.snapshot(width=720, height=540)
            except TypeError:
                image = Snapshot.snapshot()
            self._remove_snapshot_cameras()
            if image is None:
                self._set_preview("", "Не удалось построить превью", info)
                return
            self._preview_counter += 1
            path = os.path.join(tempfile.gettempdir(), "ste_ai_preview_{0}.png".format(self._preview_counter % 2))
            if not image.save(path):
                self._set_preview("", "Не удалось сохранить превью", info)
                return
            url = QUrl.fromLocalFile(path).toString() if QUrl is not None else "file:///" + path.replace("\\", "/")
            self._set_preview(url, "", info)
        except Exception as exc:
            self._set_preview("", "Превью недоступно: {0}".format(exc), info)
        finally:
            self._rendering_preview = False

    @pyqtSlot(str)
    def setCameraAngle(self, angle):
        angle = str(angle or "3d_isometric").strip()
        self._current_angle = angle
        self.cameraAngleChanged.emit()
        if self._slicer is not None and hasattr(self._slicer, "focus_on_build_plate"):
            try:
                self._slicer.focus_on_build_plate(angle)
            except Exception:
                pass
        self.refreshPreview()

    @pyqtSlot()
    def zoomIn(self):
        if self._slicer is not None and hasattr(self._slicer, "zoom"):
            try:
                self._slicer.zoom(0.8)
            except Exception:
                pass
        self.refreshPreview()

    @pyqtSlot()
    def zoomOut(self):
        if self._slicer is not None and hasattr(self._slicer, "zoom"):
            try:
                self._slicer.zoom(1.25)
            except Exception:
                pass
        self.refreshPreview()

    @pyqtSlot(float, float)
    def orbitCamera(self, delta_yaw, delta_pitch):
        if self._slicer is not None and hasattr(self._slicer, "orbit"):
            try:
                self._slicer.orbit(delta_yaw, delta_pitch)
            except Exception:
                pass
        self.refreshPreview()

    @pyqtSlot()
    def resetCamera(self):
        self.setCameraAngle("3d_isometric")

    @pyqtSlot()
    def refreshModelCount(self):
        value = max(self._attached_model_count(), self._scene_model_count())
        if value != self._model_count:
            self._model_count = value
            self.modelCountChanged.emit()

    @pyqtSlot(int)
    def removeAttachment(self, index):
        self._attachments.remove_at(index)
        self._model_count = self._attached_model_count()
        self.refreshModelCount()
        self.modelCountChanged.emit()

    @pyqtSlot()
    def clearConversation(self):
        if self._busy:
            return
        self._messages.clear()
        self._tools.clear()
        self._attachments.clear()
        self._model_count = 0
        self.refreshModelCount()
        self.modelCountChanged.emit()
        self.messageAdded.emit()

    @pyqtSlot()
    def cancelRequest(self):
        if self._agent is not None:
            cancel = getattr(self._agent, "cancel", None)
            if cancel is not None:
                try:
                    cancel()
                except Exception:
                    pass
        self._set_busy(False)
        self._messages.append_system("Запрос отменён пользователем.", self._now(), "cancelled")
        self.messageAdded.emit()

    @pyqtSlot()
    def openSettings(self):
        if self._extension is not None and hasattr(self._extension, "showSettingsDialog"):
            self._extension.showSettingsDialog()

    @pyqtSlot(str, str, str)
    def saveSettings(self, base_url, api_key, model):
        try:
            if self._settings is None:
                raise RuntimeError("Хранилище настроек недоступно.")
            if hasattr(self._settings, "save_llm_config"):
                self._settings.save_llm_config(base_url, api_key, model)
            else:
                self._settings.set("base_url", base_url)
                self._settings.set("api_key", api_key)
                self._settings.set("model", model)
            if self._settings.get("api_url") != str(base_url or "").strip().rstrip("/"):
                raise RuntimeError("Настройки не подтвердились после записи.")
            configure = getattr(self._agent, "configure", None) if self._agent is not None else None
            if configure is not None:
                configure(base_url, api_key, model)
            self.settingsSaved.emit()
        except Exception as exc:
            logger.exception("Failed to save LLM settings: %s", exc)
            self.settingsSaveFailed.emit(str(exc))
            self._fail("Не удалось сохранить настройки: {0}".format(exc))

    @pyqtSlot(str, str, str)
    def checkConnection(self, base_url, api_key, model):
        if self._agent is None:
            msg = "Agent backend не подключён: проверить соединение невозможно."
            self._fail(msg)
            self.connectionCheckFinished.emit(False, msg)
            return
        checker = getattr(self._agent, "check_connection", None)
        if checker is None:
            checker = getattr(self._agent, "checkConnection", None)
        if checker is None:
            msg = "Agent backend не предоставляет check_connection()."
            self._fail(msg)
            self.connectionCheckFinished.emit(False, msg)
            return
        try:
            res = checker(base_url, api_key, model)
            if isinstance(res, tuple):
                ok, msg = res[0], res[1]
            elif isinstance(res, bool):
                ok = res
                msg = "Соединение с LLM API проверено." if ok else "Не удалось подключиться к LLM API."
            else:
                ok, msg = bool(res), str(res)

            if not ok:
                self._fail(msg)
                self.connectionCheckFinished.emit(False, msg)
            else:
                self._messages.append_system(msg, self._now(), "ok")
                self.messageAdded.emit()
                self.connectionCheckFinished.emit(True, msg)
        except Exception as exc:
            err = "Ошибка проверки LLM API: {0}".format(exc)
            self._fail(err)
            self.connectionCheckFinished.emit(False, err)

    @pyqtSlot(str)
    def generateGcode(self, model_name):
        """Run the slicer's current slicing backend, then export generated files."""
        model_name = (model_name or "model_submission").strip()
        if self._busy:
            return
        slicer = getattr(self._agent, "_orchestrator", None) if self._agent is not None else None
        mcp = getattr(slicer, "mcp_server", None)
        if mcp is None:
            self._fail("MCPServer недоступен: не удалось запустить слайсинг.")
            return
        self._set_busy(True)
        try:
            result = mcp.call_tool("run_slicing_and_generate_gcode", {"timeout_sec": 180})
            if not isinstance(result, dict) or str(result.get("status", "")).lower() in ("error", "failed"):
                raise RuntimeError((result or {}).get("error", "Слайсер не создал G-code."))
            self._messages.append_system("G-code создан слайсером. Экспортирую проект…", self._now(), "ok")
            self._set_busy(False)
            self.exportResult(model_name)
        except Exception as exc:
            self._fail("Не удалось создать G-code: {0}".format(exc))
        finally:
            self._set_busy(False)

    @pyqtSlot(str)
    @pyqtSlot(str, str)
    def exportResultToFolder(self, folder_path, model_name="model_submission"):
        """Exports project.3mf and result.gcode directly to the specified folder.
        If the scene has not been sliced yet, runs slicing first."""
        if not folder_path:
            return

        clean_path = str(folder_path).strip()
        if clean_path.startswith("file:///"):
            clean_path = clean_path[8:]
        elif clean_path.startswith("file://"):
            clean_path = clean_path[7:]
        if os.name == "nt" and len(clean_path) >= 3 and clean_path[0] == "/" and clean_path[2] == ":":
            clean_path = clean_path[1:]
        clean_path = os.path.normpath(clean_path)

        if not os.path.exists(clean_path):
            try:
                os.makedirs(clean_path, exist_ok=True)
            except Exception as e:
                self._fail("Не удалось создать папку для экспорта: {0}".format(e))
                return

        model_name = (model_name or "model_submission").strip()
        self.exportRequested.emit(model_name)
        self._set_busy(True)

        try:
            from plugin.utils.artifact_exporter import ArtifactExporter
            from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher

            # Check if G-code is already available in the scene
            app = ArtifactExporter._get_application()
            scene = app.getController().getScene() if app is not None and hasattr(app, "getController") else None
            gcode_dict = getattr(scene, "gcode_dict", {}) if scene is not None else {}
            has_gcode = bool(gcode_dict and any(gcode_dict.values()))

            if not has_gcode:
                self._messages.append_system("Подготовка G-кода: выполняется нарезка сцены...", self._now(), "pending")
                self.messageAdded.emit()
                slicer = getattr(self._agent, "_orchestrator", None) if self._agent is not None else None
                mcp = getattr(slicer, "mcp_server", None)
                if mcp is not None:
                    res = mcp.call_tool("run_slicing_and_generate_gcode", {"timeout_sec": 180})
                    if isinstance(res, dict) and str(res.get("status", "")).lower() in ("error", "failed"):
                        err = res.get("message") or res.get("error") or "Ошибка слайсинга"
                        self._messages.append_system("Предупреждение: {0}".format(err), self._now(), "warning")

            chat_window = None
            if self._slicer is not None and hasattr(self._slicer, "get_chat_window"):
                chat_window = self._slicer.get_chat_window()
            elif self._extension is not None and hasattr(self._extension, "_chat_view"):
                chat_window = getattr(self._extension, "_chat_view", None)

            exporter = ArtifactExporter(clean_path, dispatcher=MainThreadDispatcher)
            report = exporter.export_all_for_model(model_name, chat_window=chat_window, validate=False, target_dir=clean_path)

            export_dir = report.get("directory", clean_path)
            self._last_gcode_path = report.get("result_gcode", os.path.join(export_dir, "result.gcode"))
            self._exported_directory = export_dir
            self._export_status = "Успешно экспортировано: " + os.path.basename(export_dir)
            msg = "Файлы project.3mf и result.gcode успешно экспортированы в папку:\n{0}".format(export_dir)
            self._messages.append_system(msg, self._now(), "ok")
            self.exportFinished.emit(True, msg, export_dir)
            self.recommendationChanged.emit()
            self.messageAdded.emit()

        except Exception as exc:
            err = "Экспорт не выполнен: {0}".format(exc)
            self._export_status = err
            self._fail(err)
            self.exportFinished.emit(False, err, "")
            self.recommendationChanged.emit()
        finally:
            self._set_busy(False)

    @pyqtSlot(str)
    def exportResult(self, model_name):
        model_name = (model_name or "model").strip()
        self.exportRequested.emit(model_name)
        try:
            from plugin.utils.artifact_exporter import ArtifactExporter
            from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher

            results_dir = os.environ.get("STE_AI_RESULTS_DIR")
            if not results_dir and self._settings is not None:
                results_dir = getattr(self._settings, "results_dir", None)
            if not results_dir:
                results_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "results"
                )

            chat_window = None
            if self._slicer is not None and hasattr(self._slicer, "get_chat_window"):
                chat_window = self._slicer.get_chat_window()
            elif self._extension is not None and hasattr(self._extension, "_chat_view"):
                chat_window = getattr(self._extension, "_chat_view", None)

            exporter = ArtifactExporter(results_dir, dispatcher=MainThreadDispatcher)
            report = exporter.export_all_for_model(model_name, chat_window=chat_window, validate=False)

            export_dir = report.get("directory", "")
            self._last_gcode_path = report.get("result_gcode", "")
            self._exported_directory = export_dir
            self._export_status = "Успешно экспортировано: " + os.path.basename(export_dir)
            msg = "Артефакты {0} успешно сохранены в results/".format(os.path.basename(export_dir))
            self._messages.append_system(msg, self._now(), "ok")
            self.exportFinished.emit(True, msg, export_dir)
            self.recommendationChanged.emit()
            self.messageAdded.emit()
        except Exception as exc:
            err = "Экспорт не выполнен: {0}".format(exc)
            self._export_status = err
            self.exportFinished.emit(False, err, "")
            self.recommendationChanged.emit()

    @pyqtSlot(str)
    def openFolder(self, path):
        target = path or self._exported_directory
        if not target:
            target = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "results")
        if target and os.path.exists(target):
            try:
                if os.name == "nt":
                    subprocess.Popen(["explorer", os.path.normpath(target)])
                else:
                    subprocess.Popen(["xdg-open", target])
            except Exception:
                try:
                    os.startfile(target)
                except Exception:
                    pass

    @pyqtSlot()
    def requestScreenshot(self):
        self.screenshotRequested.emit()

    # Slots for AgentWorker / SlicerIntegrationBridge signals.
    @pyqtSlot(str, str)
    def onAgentStepStarted(self, step, detail):
        self._messages.append_system("{0} {1}".format(step, detail).strip(), self._now(), "pending")
        self.messageAdded.emit()

    @pyqtSlot(str, str, object)
    def onToolCallStarted(self, tool_name, label, arguments=None):
        args_dict = arguments if isinstance(arguments, dict) else {}
        if isinstance(arguments, str):
            try:
                args_dict = json.loads(arguments)
            except Exception:
                args_dict = {}
        if "mode" in args_dict:
            self.setPrintMode(str(args_dict["mode"]))
        if "material" in args_dict:
            self.setMaterial(str(args_dict["material"]))
        args = json.dumps(args_dict or arguments or {}, ensure_ascii=False, indent=2)
        row = self._tools.append_call(tool_name, label, args, "pending")
        self._active_tools[tool_name] = row
        self._messages.append_tool(tool_name, label, args, "", "pending", 0)
        self.toolStarted.emit(tool_name, label)
        self.messageAdded.emit()

    @pyqtSlot(str, str, object, int)
    def onToolCallFinished(self, tool_name, status, result=None, duration_ms=0):
        res_dict = result if isinstance(result, dict) else {}
        if isinstance(result, str):
            try:
                res_dict = json.loads(result)
            except Exception:
                res_dict = {}
        if "print_time" in res_dict or "print_time_formatted" in res_dict:
            pt = str(res_dict.get("print_time_formatted") or res_dict.get("print_time") or "")
            mu = str(res_dict.get("material_weight_g") or res_dict.get("material_usage") or "")
            self.setPrintResult(pt, mu)
        if "mode" in res_dict:
            self.setPrintMode(str(res_dict["mode"]))
        if "material" in res_dict or "applied_material" in res_dict:
            self.setMaterial(str(res_dict.get("applied_material") or res_dict.get("material")))
        if "applied_parameters" in res_dict or "applied_overrides" in res_dict:
            self._update_parameters_from_dict(res_dict.get("applied_parameters") or res_dict.get("applied_overrides"))
        result_text = json.dumps(result or {}, ensure_ascii=False, indent=2) if not isinstance(result, str) else result
        row = self._active_tools.pop(tool_name, -1)
        self._tools.finish_call(row, status.lower(), result_text, duration_ms)
        self._messages.update_tool(tool_name, status.lower(), result_text, duration_ms)
        self.toolFinished.emit(tool_name, status)
        self.messageAdded.emit()

    @pyqtSlot(str, result=str)
    def renderMarkdown(self, text):
        return self._markdown_to_html(text)

    @staticmethod
    def _markdown_to_html(text):
        """Render safe, lightweight Markdown using Qt rich-text HTML."""
        import html

        lines = str(text or "").splitlines()
        rendered = []
        index = 0

        def inline(value):
            value = html.escape(value, quote=False)
            value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
            value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
            return re.sub(r"(^|[^*])\*([^*\n]+)\*(?!\*)", r"\1<i>\2</i>", value)

        while index < len(lines):
            line = lines[index]
            if "|" in line and index + 1 < len(lines) and re.match(
                    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1]):
                headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
                rendered.append('<table width="100%" cellspacing="0" cellpadding="4" style="border-collapse:collapse; table-layout:fixed;">')
                rendered.append("<tr>" + "".join(
                    '<th align="left" style="border:1px solid #cbd5e1;">{0}</th>'.format(inline(cell))
                    for cell in headers
                ) + "</tr>")
                index += 2
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                    cells = (cells + [""] * len(headers))[:len(headers)]
                    rendered.append("<tr>" + "".join(
                        '<td style="border:1px solid #cbd5e1; word-wrap:break-word;">{0}</td>'.format(inline(cell))
                        for cell in cells
                    ) + "</tr>")
                    index += 1
                rendered.append("</table>")
                continue

            escaped = inline(line)
            escaped = re.sub(r"^### (.+)$", r"<h3>\1</h3>", escaped)
            escaped = re.sub(r"^## (.+)$", r"<h2>\1</h2>", escaped)
            escaped = re.sub(r"^# (.+)$", r"<h1>\1</h1>", escaped)
            escaped = re.sub(r"^- (.+)$", r"• \1", escaped)
            rendered.append(escaped)
            index += 1

        return "<html><body><div style='width:100%; white-space:normal;'>" + "<br/>".join(rendered) + "</div></body></html>"

    def _update_parameters_from_dict(self, summary):
        if not summary or not isinstance(summary, dict):
            return

        def value(*keys):
            for key in keys:
                if key in summary:
                    item = summary[key]
                    if isinstance(item, dict):
                        item = item.get("new", item.get("value"))
                    if item is not None:
                        return item
            return None

        mode = value("mode")
        if mode is not None:
            self.setPrintMode(str(mode))
        material = value("applied_material", "material")
        if material:
            self.setMaterial(str(material))
        profile = value("applied_profile", "profile")
        if profile:
            self._profile_name = str(profile)
        layer_height = value("layer_height_mm", "layer_height")
        if isinstance(layer_height, dict):
            layer_height = layer_height.get("new", layer_height.get("value"))
        if layer_height is not None:
            self._layer_height = "{0:.2f} мм".format(float(layer_height))
        wall_count = value("wall_line_count")
        if isinstance(wall_count, dict):
            wall_count = wall_count.get("new", wall_count.get("value"))
        if wall_count is not None:
            self._wall_line_count = "{0} линии".format(wall_count)
        infill = value("infill_density_pct", "infill_sparse_density")
        if isinstance(infill, dict):
            infill = infill.get("new", infill.get("value"))
        if infill is not None:
            self._infill_density = "{0}%".format(infill)
        pattern = value("infill_pattern")
        if pattern is not None:
            self._infill_pattern = str(pattern).capitalize()
        nozzle_temp = value("print_temperature_c", "material_print_temperature")
        if isinstance(nozzle_temp, dict):
            nozzle_temp = nozzle_temp.get("new", nozzle_temp.get("value"))
        if nozzle_temp is not None:
            self._print_temp = "{0} °C".format(nozzle_temp)
        bed_temp = value("bed_temperature_c", "material_bed_temperature")
        if isinstance(bed_temp, dict):
            bed_temp = bed_temp.get("new", bed_temp.get("value"))
        if bed_temp is not None:
            self._bed_temp = "{0} °C".format(bed_temp)
        fan_speed = value("fan_speed_pct", "cool_fan_speed")
        if fan_speed is not None:
            self._fan_speed = "{0}%".format(fan_speed)
        supports = value("support_enabled", "support_enable")
        if supports is not None:
            self._support_enabled = bool(supports)
            self._support_text = "Включены" if self._support_enabled else "Отключены"
        rotation = value("rotation_deg", "applied_rotation_euler_deg")
        if rotation is not None:
            self._rotation_deg = rotation
        print_time = value("print_time_formatted", "print_time")
        if print_time is not None:
            self.setPrintResult(
                str(print_time),
                str(value("material_weight_g", "material_usage") or "")
            )
        self.recommendationChanged.emit()

    @pyqtSlot(object)
    def onAgentResponse(self, response):
        text = response if isinstance(response, str) else (response.get("text") or response.get("content") or "")
        summary = response.get("summary") if isinstance(response, dict) else {}
        self._update_parameters_from_dict(summary)
        if text:
            self._last_recommendation = self._markdown_to_html(text)
            self._messages.append_assistant(self._markdown_to_html(text), self._now())
            self.responseReady.emit(text)
            self.recommendationChanged.emit()
            self.messageAdded.emit()
        self._set_busy(False)
        self.taskFinished.emit()

    @pyqtSlot(str)
    def onAgentError(self, message):
        self._fail(message)

    @pyqtSlot(str)
    def setPrinterName(self, value):
        if self._printer != value:
            self._printer = value
            self.printerChanged.emit()

    @pyqtSlot(str)
    def setPrintMode(self, value):
        if self._print_mode != value:
            self._print_mode = value
            self.printModeChanged.emit()

    @pyqtSlot(str)
    def setMaterial(self, value):
        if self._material != value:
            self._material = value
            self.materialChanged.emit()

    @pyqtSlot(int)
    def setSlicingProgress(self, value):
        value = max(0, min(100, int(value)))
        if self._slicing_progress != value:
            self._slicing_progress = value
            self.slicingProgressChanged.emit()

    @pyqtSlot(str, str)
    def setPrintResult(self, print_time, material_usage):
        self._print_time = print_time
        if material_usage and not str(material_usage).endswith("г"):
            try:
                val = float(material_usage)
                material_usage = "{0:.1f} г".format(val)
            except ValueError:
                pass
        self._material_usage = material_usage
        self.printResultChanged.emit()

    # Aliases
    sendMessage = sendPrompt
    attachFile = addAttachment
    saveApiSettings = saveSettings
    exportSubmissionPackage = exportResult


ChatViewController = ChatController
__all__ = ["ChatController", "ChatViewController"]
