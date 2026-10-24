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
import tempfile
import time

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
    connectionCheckFinished = pyqtSignal(bool, str)
    screenshotRequested = pyqtSignal()
    exportRequested = pyqtSignal(str)

    connectedChanged = pyqtSignal()
    printerChanged = pyqtSignal()
    printModeChanged = pyqtSignal()
    materialChanged = pyqtSignal()
    modelCountChanged = pyqtSignal()
    busyChanged = pyqtSignal()
    slicingProgressChanged = pyqtSignal()
    printResultChanged = pyqtSignal()
    previewChanged = pyqtSignal()
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
        self._preview_counter = 0
        self._preview_path = ""
        self._rendering_preview = False
        self._preview_timer = None
        if QTimer is not None:
            # Scene changes arrive in bursts (load, rotate, scale), so the
            # snapshot is debounced instead of being rendered on every event.
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(600)
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

    @pyqtProperty(int, notify=slicingProgressChanged)
    def slicingProgress(self):
        return self._slicing_progress

    @pyqtProperty(str, notify=printResultChanged)
    def printTime(self):
        return self._print_time

    @pyqtProperty(str, notify=printResultChanged)
    def materialUsage(self):
        return self._material_usage

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
        """Connect optional AgentWorker signals without requiring a concrete backend."""
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
            # Асинхронный backend завершит задачу через onAgentResponse().
            if result is not None:
                self.onAgentResponse(result)
        except Exception as exc:
            self._fail("Не удалось отправить запрос агенту: {0}".format(exc))

    @pyqtSlot(str)
    def addAttachment(self, path):
        path = (path or "").replace("file:///", "")
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

    def _scene_nodes(self):
        try:
            from UM.Application import Application
            from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
            root = Application.getInstance().getController().getScene().getRoot()
        except Exception:
            return []
        nodes = []
        for node in DepthFirstIterator(root):
            try:
                if node.callDecoration("isSliceable") and node.getMeshData() is not None:
                    nodes.append(node)
            except Exception:
                pass
        return nodes

    def _describe_models(self, nodes):
        parts = []
        for node in nodes[:3]:
            name = node.getName() if hasattr(node, "getName") else "model"
            try:
                box = node.getBoundingBox()
                parts.append("{0} · {1:.0f}×{2:.0f}×{3:.0f} мм".format(name, box.width, box.depth, box.height))
            except Exception:
                parts.append(name)
        if len(nodes) > 3:
            parts.append("и ещё {0}".format(len(nodes) - 3))
        return "\n".join(parts)

    def _set_preview(self, url, message, info):
        self._preview_url = url
        self._preview_message = message
        self._model_info = info
        self.previewChanged.emit()

    def _remove_snapshot_cameras(self):
        # Snapshot.snapshot() parents a temporary camera to the scene root and
        # never removes it; repeated previews would otherwise accumulate them.
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
            self._set_preview("", "Загрузите модель на стол STE Slicer", "")
            return
        info = self._describe_models(nodes)
        self._rendering_preview = True
        try:
            try:
                from steslicer.Snapshot import Snapshot
            except ImportError:
                from cura.Snapshot import Snapshot
            try:
                image = Snapshot.snapshot(width=640, height=480)
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
            # Two alternating file names force QML to reload the image.
            self._set_preview(url, "", info)
        except Exception as exc:
            self._set_preview("", "Превью недоступно: {0}".format(exc), info)
        finally:
            self._rendering_preview = False

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
        if self._settings is not None:
            if hasattr(self._settings, "save_llm_config") and base_url and api_key and model:
                try:
                    self._settings.save_llm_config(base_url, api_key, model)
                except Exception:
                    pass
            setter = getattr(self._settings, "set", None)
            if setter is not None:
                setter("llm_base_url", base_url)
                setter("llm_api_key", api_key)
                setter("llm_model", model)
        if self._agent is not None:
            configure = getattr(self._agent, "configure", None)
            if configure is not None:
                configure(base_url, api_key, model)
        self.settingsSaved.emit()

    @pyqtSlot(str, str, str)
    def checkConnection(self, base_url, api_key, model):
        """Ask the injected agent to validate provider settings."""
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
    def exportResult(self, model_name):
        self.exportRequested.emit(model_name or "model")
        if self._slicer is not None:
            exporter = getattr(self._slicer, "export_result", None)
            if exporter is not None:
                exporter(model_name or "model")

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
        if "material" in res_dict:
            self.setMaterial(str(res_dict["material"]))
        result_text = json.dumps(result or {}, ensure_ascii=False, indent=2) if not isinstance(result, str) else result
        row = self._active_tools.pop(tool_name, -1)
        self._tools.finish_call(row, status.lower(), result_text, duration_ms)
        self._messages.update_tool(tool_name, status.lower(), result_text, duration_ms)
        self.toolFinished.emit(tool_name, status)
        self.messageAdded.emit()

    @pyqtSlot(object)
    def onAgentResponse(self, response):
        text = response if isinstance(response, str) else (response.get("text") or response.get("content") or "")
        summary = response.get("summary") if isinstance(response, dict) else {}
        if summary and isinstance(summary, dict):
            if "mode" in summary:
                self.setPrintMode(str(summary["mode"]))
            if "material" in summary:
                self.setMaterial(str(summary["material"]))
            if "print_time" in summary or "print_time_formatted" in summary:
                self.setPrintResult(str(summary.get("print_time_formatted") or summary.get("print_time")),
                                   str(summary.get("material_weight_g") or summary.get("material_usage") or ""))
        if text:
            self._messages.append_assistant(text, self._now())
            self.responseReady.emit(text)
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
        self._material_usage = material_usage
        self.printResultChanged.emit()


    # Спецификационные алиасы методов из архитектурного плана:
    sendMessage = sendPrompt
    attachFile = addAttachment
    saveApiSettings = saveSettings
    exportSubmissionPackage = exportResult


ChatViewController = ChatController
__all__ = ["ChatController", "ChatViewController"]
