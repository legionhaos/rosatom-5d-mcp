# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
except ImportError:
    try:
        from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
    except ImportError:
        try:
            from PySide2.QtCore import QObject, Signal as pyqtSignal, Slot as pyqtSlot
        except ImportError:
            from PySide6.QtCore import QObject, Signal as pyqtSignal, Slot as pyqtSlot

try:
    from UM.Extension import Extension
except ImportError:
    class Extension(object):
        def __init__(self):
            self._menu_items = []

        def addMenuItem(self, name, function):
            self._menu_items.append((name, function))

logger = logging.getLogger("STEAIExtension")

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_QML_DIR = os.path.join(_PLUGIN_DIR, "ui", "qml")


class AgentBackendAdapter(QObject):

    stepStarted = pyqtSignal(str, str)
    toolCallStarted = pyqtSignal(str, str, object)
    toolCallFinished = pyqtSignal(str, str, object, int)
    responseReady = pyqtSignal(object)
    taskFailed = pyqtSignal(str)

    def __init__(self, worker, settings_mgr=None, orchestrator=None, parent=None):
        # type: (Any, Any, Any, Any) -> None
        super(AgentBackendAdapter, self).__init__(parent)
        self._worker = worker
        self._settings_mgr = settings_mgr
        self._orchestrator = orchestrator
        self._call_names = {}  # type: Dict[str, str]
        self._connect_worker()

    def _connect_worker(self):
        if self._worker is None:
            return
        try:
            self._worker.toolCallStarted.connect(self._on_tool_started)
            self._worker.toolCallFinished.connect(self._on_tool_finished)
            self._worker.finalAnswerReceived.connect(self._on_final_answer)
            self._worker.workerError.connect(self._on_worker_error)
        except (TypeError, RuntimeError, AttributeError) as exc:
            logger.warning("Не удалось подключить сигналы AgentWorker: %s", exc)

    def send_prompt(self, text, attachments=None):
        # type: (str, Optional[List[str]]) -> None
        if self._worker is None:
            self.taskFailed.emit("AgentWorker недоступен.")
            return
        paths = list(attachments or [])
        try:
            if self._worker.isRunning():
                self.taskFailed.emit("Агент уже обрабатывает запрос.")
                return
        except Exception:
            pass
        self.stepStarted.emit("Запуск", "Агент начал обработку запроса.")
        self._worker.set_task(text, paths)
        self._worker.start()

    def cancel(self):
        if self._worker is not None:
            cancel = getattr(self._worker, "cancel", None)
            if cancel is not None:
                cancel()

    def configure(self, base_url, api_key, model):
        # type: (str, str, str) -> None
        if self._settings_mgr is not None:
            self._settings_mgr.save_llm_config(base_url, api_key, model)
        if self._orchestrator is not None:
            rebuild = getattr(self._orchestrator, "reload_llm_client", None)
            if rebuild is not None:
                rebuild()

    def check_connection(self, base_url, api_key, model):
        # type: (str, str, str) -> bool
        try:
            from plugin.agent.llm_client import OpenAICompatibleClient, LLMConnectionConfig
        except ImportError:
            from ..agent.llm_client import OpenAICompatibleClient, LLMConnectionConfig

        config = LLMConnectionConfig(
            api_url=base_url,
            api_key=api_key,
            model_name=model,
            timeout_sec=10,
            temperature=0.1,
        )
        client = OpenAICompatibleClient(config)
        ok, message = client.test_connection()
        if not ok:
            self.taskFailed.emit(message)
        return ok

    def _on_tool_started(self, call_id, tool_name, args_json):
        self._call_names[str(call_id)] = str(tool_name)
        try:
            arguments = json.loads(args_json) if args_json else {}
        except (ValueError, TypeError):
            arguments = {"raw": str(args_json)}
        self.toolCallStarted.emit(str(tool_name), str(call_id), arguments)

    def _on_tool_finished(self, call_id, status, summary, duration_ms):
        tool_name = self._call_names.pop(str(call_id), str(call_id))
        self.toolCallFinished.emit(str(tool_name), str(status), summary, int(duration_ms))

    def _on_final_answer(self, markdown_answer, summary_card):
        payload = {"text": markdown_answer or "", "summary": dict(summary_card or {})}
        self.responseReady.emit(payload)

    def _on_worker_error(self, message):
        self.taskFailed.emit(str(message))


class STEAIExtension(Extension):

    def __init__(self):
        super(STEAIExtension, self).__init__()

        self._chat_view = None
        self._settings_view = None

        self._dispatcher = None
        self._settings_mgr = None
        self._event_listener = None
        self._camera_manager = None
        self._mcp_server = None
        self._orchestrator = None
        self._worker = None
        self._adapter = None
        self._controller = None

        self._build_components()

        self.addMenuItem("Открыть ИИ-чат", self.showChatWindow)
        self.addMenuItem("Настройки LLM API", self.showSettingsDialog)

        self._register_application_hook()

    def _application(self):
        try:
            from cura.CuraApplication import CuraApplication
            return CuraApplication.getInstance()
        except Exception:
            try:
                from UM.Application import Application
                return Application.getInstance()
            except Exception:
                return None

    def _build_components(self):
        app = self._application()

        try:
            from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
            self._dispatcher = MainThreadDispatcher
        except Exception as exc:
            logger.error("Не удалось загрузить MainThreadDispatcher: %s", exc)

        try:
            from plugin.config.settings_config import PluginSettingsManager
            self._settings_mgr = PluginSettingsManager(app)
        except Exception as exc:
            logger.error("Не удалось создать PluginSettingsManager: %s", exc)

        try:
            from plugin.slicer_bridge.event_listener import SlicerEventListener
            self._event_listener = SlicerEventListener(app)
        except Exception as exc:
            logger.error("Не удалось создать SlicerEventListener: %s", exc)

        try:
            from plugin.slicer_bridge.camera_and_viewport import ViewportCameraManager
            self._camera_manager = ViewportCameraManager(app)
        except Exception as exc:
            logger.error("Не удалось создать ViewportCameraManager: %s", exc)

        try:
            from plugin.mcp_server.server import MCPServer
            self._mcp_server = MCPServer(
                settings_mgr=self._settings_mgr,
                event_listener=self._event_listener,
                camera_manager=self._camera_manager,
                dispatcher=self._dispatcher,
            )
        except Exception as exc:
            logger.error("Не удалось создать MCPServer: %s", exc)

        try:
            from plugin.agent.orchestrator import AgentOrchestrator
            self._orchestrator = AgentOrchestrator(
                settings_mgr=self._settings_mgr,
                mcp_server=self._mcp_server,
            )
        except Exception as exc:
            logger.error("Не удалось создать AgentOrchestrator: %s", exc)

        try:
            from plugin.agent.worker import AgentWorker
            self._worker = AgentWorker(orchestrator=self._orchestrator)
        except Exception as exc:
            logger.error("Не удалось создать AgentWorker: %s", exc)

        try:
            self._adapter = AgentBackendAdapter(
                self._worker,
                settings_mgr=self._settings_mgr,
                orchestrator=self._orchestrator,
            )
        except Exception as exc:
            logger.error("Не удалось создать AgentBackendAdapter: %s", exc)

        try:
            from plugin.ui.chat_controller import ChatController
            self._controller = ChatController(
                agent_backend=self._adapter,
                slicer_bridge=self._camera_manager,
                settings_store=None,
            )
        except Exception as exc:
            logger.error("Не удалось создать ChatController: %s", exc)

    def _register_application_hook(self):
        app = self._application()
        if app is None:
            return
        try:
            if hasattr(app, "pluginsLoaded"):
                app.pluginsLoaded.connect(self.onApplicationInitialized)
            elif hasattr(app, "initializationFinished"):
                app.initializationFinished.connect(self.onApplicationInitialized)
        except Exception as exc:
            logger.warning("Не удалось подключить хук инициализации: %s", exc)

    def onApplicationInitialized(self):
        if self._event_listener is not None:
            attach = getattr(self._event_listener, "attach_signals", None)
            if attach is not None:
                attach()

    def _create_qml_component(self, file_name):
        app = self._application()
        if app is None:
            return None
        creator = getattr(app, "createQmlComponent", None)
        if creator is None:
            return None
        path = os.path.join(_QML_DIR, file_name)
        context = {"controller": self._controller, "manager": self}
        try:
            return creator(path, context)
        except Exception as exc:
            logger.error("Не удалось создать QML компонент %s: %s", file_name, exc)
            return None

    def showChatWindow(self):
        if self._chat_view is None:
            self._chat_view = self._create_qml_component("ChatWindow.qml")
        if self._chat_view is None:
            return
        if self._camera_manager is not None:
            self._camera_manager.set_chat_window(self._chat_view)
        self._chat_view.show()

    def showSettingsDialog(self):
        if self._settings_view is None:
            self._settings_view = self._create_qml_component("SettingsDialog.qml")
        if self._settings_view is None:
            return
        self._settings_view.show()


__all__ = ["STEAIExtension", "AgentBackendAdapter"]
