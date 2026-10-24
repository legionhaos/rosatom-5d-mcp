# -*- coding: utf-8 -*-
"""
STEAIExtension for STE Slicer (Cura 3.6 / Uranium).

Main extension class integrating the AI Assistant into the slicer lifecycle,
registering menu items, creating QML dialogs, and wiring the agent architecture.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import sys
from typing import Any, Optional

# Безопасный импорт Uranium Extension
try:
    from UM.Extension import Extension
except ImportError:
    class Extension(object):
        """Резервный базовый класс Extension вне Uranium."""
        def __init__(self):
            self._menu_items = []

        def addMenuItem(self, name, callback):
            self._menu_items.append((name, callback))

from plugin.config.settings_config import PluginSettingsManager
from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher, run_in_main_thread
from plugin.slicer_bridge.event_listener import SlicerEventListener
from plugin.slicer_bridge.camera_and_viewport import ViewportCameraManager
from plugin.mcp_server.server import MCPServer
from plugin.agent.orchestrator import AgentOrchestrator
from plugin.agent.worker import AgentWorker
from plugin.ui.chat_controller import ChatController
from plugin.utils.logger import STEPluginLogger, get_logger

logger = get_logger("STEAIExtension")


class STEAIExtension(Extension):
    """
    Главный класс расширения STE AI Assistant для STE Slicer.
    """

    def __init__(self, application=None):
        # type: (Optional[Any]) -> None
        super(STEAIExtension, self).__init__()
        self._application = application
        self._chat_window = None
        self._settings_dialog = None

        logger.info("Initializing STEAIExtension...")

        # 1. Диспетчер и настройки
        self.dispatcher = MainThreadDispatcher()
        self.settings_mgr = PluginSettingsManager(application=application)

        # 2. Слушатель событий слайсера и камера
        self.event_listener = SlicerEventListener(application=application)
        self.camera_manager = ViewportCameraManager(application=application)

        # 3. Сервер MCP-инструментов
        self.mcp_server = MCPServer(
            dispatcher=self.dispatcher,
            event_listener=self.event_listener,
            settings_mgr=self.settings_mgr
        )

        # 4. Оркестратор и фоновый воркер агента
        self.orchestrator = AgentOrchestrator(
            settings_mgr=self.settings_mgr,
            mcp_server=self.mcp_server
        )
        self.worker = AgentWorker(orchestrator=self.orchestrator)

        # 5. Контроллер интерфейса (связка QML <-> Agent)
        self.chat_controller = ChatController(
            agent_backend=self.worker,
            slicer_bridge=self,
            settings_store=self.settings_mgr
        )

        # 6. Регистрация пунктов меню STE Slicer
        try:
            self.addMenuItem("Открыть ИИ-чат", self.showChatWindow)
            self.addMenuItem("Настройки LLM API", self.showSettingsDialog)
            logger.info("Menu items registered: 'Открыть ИИ-чат', 'Настройки LLM API'")
        except Exception as e:
            logger.warning("Could not register menu items: %s", e)

        # Подписка на готовность приложения
        self._register_application_init_hook()

    def _register_application_init_hook(self):
        """Хук инициализации приложения для автоматического открытия чата."""
        app = self._get_app()
        if app and hasattr(app, "applicationInitialized"):
            try:
                app.applicationInitialized.connect(self.onApplicationInitialized)
            except Exception:
                pass

    def _get_app(self):
        if self._application is not None:
            return self._application
        try:
            from cura.CuraApplication import CuraApplication
            return CuraApplication.getInstance()
        except Exception:
            try:
                from UM.Application import Application
                return Application.getInstance()
            except Exception:
                return None

    def onApplicationInitialized(self):
        # type: () -> None
        """Вызывается после полной загрузки всех подсистем STE Slicer."""
        logger.info("CuraApplication initialized. STE AI Assistant is ready.")
        try:
            self.event_listener.attach_signals()
        except Exception as e:
            logger.debug("onApplicationInitialized notice: %s", e)

    @run_in_main_thread
    def showChatWindow(self):
        # type: () -> None
        """Создает и отображает главное окно ИИ-чата (ChatWindow.qml)."""
        logger.info("Opening AI Chat window...")
        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qml_path = os.path.join(plugin_root, "ui", "qml", "ChatWindow.qml")

        if not os.path.isfile(qml_path):
            logger.error("ChatWindow.qml not found at: %s", qml_path)
            return

        app = self._get_app()
        if app and hasattr(app, "createQmlComponent"):
            try:
                if self._chat_window is None:
                    self._chat_window = app.createQmlComponent(
                        qml_path,
                        {"controller": self.chat_controller}
                    )
                if self._chat_window and hasattr(self._chat_window, "show"):
                    self._chat_window.show()
                return
            except Exception as e:
                logger.warning("createQmlComponent failed: %s; trying QQuickView fallback.", e)

        # Fallback для запуска окна через PyQt5 QQuickView
        try:
            from PyQt5.QtQuick import QQuickView
            from PyQt5.QtCore import QUrl
            if self._chat_window is None:
                view = QQuickView()
                view.setTitle("STE AI 3D/5D Print Assistant")
                view.rootContext().setContextProperty("controller", self.chat_controller)
                view.setSource(QUrl.fromLocalFile(qml_path))
                view.setResizeMode(QQuickView.SizeRootObjectToView)
                self._chat_window = view
            self._chat_window.show()
        except Exception as e:
            logger.error("Could not display ChatWindow: %s", e)

    @run_in_main_thread
    def showSettingsDialog(self):
        # type: () -> None
        """Открывает модальное окно настроек LLM API."""
        logger.info("Opening LLM Settings dialog...")
        if self._chat_window is not None:
            self.showChatWindow()
            return

        plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qml_path = os.path.join(plugin_root, "ui", "qml", "SettingsDialog.qml")

        app = self._get_app()
        if app and hasattr(app, "createQmlComponent"):
            try:
                if self._settings_dialog is None:
                    self._settings_dialog = app.createQmlComponent(
                        qml_path,
                        {"controller": self.chat_controller}
                    )
                if self._settings_dialog and hasattr(self._settings_dialog, "show"):
                    self._settings_dialog.show()
                return
            except Exception as e:
                logger.debug("Settings createQmlComponent notice: %s", e)

        self.showChatWindow()

    def export_result(self, model_name="model"):
        # type: (str) -> None
        """Слот вызова экспорта из контроллера."""
        from plugin.utils.artifact_exporter import ArtifactExporter
        results_root = self.settings_mgr.get_results_root_dir()
        exporter = ArtifactExporter(results_root=results_root, dispatcher=self.dispatcher)
        try:
            exporter.export_all_for_model(model_name=model_name, chat_window=self._chat_window)
            logger.info("Results exported successfully for '%s'", model_name)
        except Exception as e:
            logger.exception("Error exporting results for '%s': %s", model_name, e)


__all__ = ["STEAIExtension"]
