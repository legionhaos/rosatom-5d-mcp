# -*- coding: utf-8 -*-
"""
SlicerEventListener for STE Slicer.

Monitors scene events, model loading, active printer/mode/material changes,
and synchronizes asynchronous CuraEngine slicing progress with MCP tools.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import threading
from typing import Any, Callable, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal
except ImportError:
    try:
        from PyQt6.QtCore import QObject, pyqtSignal
    except ImportError:
        try:
            from PySide2.QtCore import QObject, Signal as pyqtSignal
        except ImportError:
            try:
                from PySide6.QtCore import QObject, Signal as pyqtSignal
            except ImportError:
                class QObject(object):
                    def __init__(self, parent=None):
                        self.parent = parent

                def pyqtSignal(*types):
                    return None

logger = logging.getLogger("SlicerEventListener")


class SlicerEventListener(QObject):
    """
    Слушатель событий ядра STE Slicer / Cura 3.6.
    Синхронизирует асинхронный C++ движок CuraEngine с синхронными вызовами MCP-тулов.
    """

    modelLoaded = pyqtSignal(str) if pyqtSignal is not None else None
    sceneModified = pyqtSignal() if pyqtSignal is not None else None
    slicingFinishedSignal = pyqtSignal() if pyqtSignal is not None else None

    def __init__(self, application=None, parent=None):
        # type: (Optional[Any], Optional[Any]) -> None
        super(SlicerEventListener, self).__init__(parent)
        self._application = application
        self.slicing_completed_event = threading.Event()
        self._is_slicing = False
        self._attached = False

        if self._application is None:
            try:
                from cura.CuraApplication import CuraApplication
                self._application = CuraApplication.getInstance()
            except Exception:
                self._application = None

        if self._application is not None:
            self.attach_signals()

    def attach_signals(self):
        # type: () -> None
        """Подписывается на сигналы сцены, бэкенда и менеджера машины."""
        if self._attached or self._application is None:
            return

        try:
            # 1. Сцена: добавление / удаление / трансформация объектов
            controller = self._application.getController()
            if controller:
                scene = controller.getScene()
                if scene and hasattr(scene, "sceneChanged"):
                    scene.sceneChanged.connect(self._on_scene_changed)

            # 2. Окончание загрузки файла
            if hasattr(self._application, "fileCompleted"):
                self._application.fileCompleted.connect(self._on_file_completed)
            elif hasattr(self._application, "fileLoaded"):
                self._application.fileLoaded.connect(self._on_file_completed)

            # 3. Смена глобального контейнера / принтера / режима 3D-5D
            try:
                from cura.Settings.CuraContainerRegistry import CuraContainerRegistry
                registry = CuraContainerRegistry.getInstance()
                if hasattr(registry, "containerAdded"):
                    pass
            except Exception:
                pass

            machine_mgr = None
            try:
                machine_mgr = self._application.getMachineManager()
            except Exception:
                pass

            if machine_mgr and hasattr(machine_mgr, "globalContainerChanged"):
                machine_mgr.globalContainerChanged.connect(self._on_machine_changed)

            # 4. Бэкенд слайсера CuraEngine
            backend = None
            try:
                backend = self._application.getBackend()
            except Exception:
                pass

            if backend:
                if hasattr(backend, "slicingFinished"):
                    backend.slicingFinished.connect(self._on_slicing_finished)
                if hasattr(backend, "backendStateChange"):
                    backend.backendStateChange.connect(self._on_backend_state_change)

            self._attached = True
            logger.info("SlicerEventListener successfully attached to Cura signals.")
        except Exception as e:
            logger.warning("Could not attach all SlicerEventListener signals: %s", e)

    def _on_scene_changed(self, source=None):
        # type: (Optional[Any]) -> None
        """Отслеживает изменение нод на сцене."""
        logger.debug("Scene changed: %s", source)
        if self.sceneModified is not None and hasattr(self.sceneModified, "emit"):
            try:
                self.sceneModified.emit()
            except Exception:
                pass

    def _on_file_completed(self, file_path=""):
        # type: (str) -> None
        """Вызывается при загрузке новой модели на рабочий стол."""
        logger.info("File loaded into scene: %s", file_path)
        if self.modelLoaded is not None and hasattr(self.modelLoaded, "emit"):
            try:
                self.modelLoaded.emit(str(file_path))
            except Exception:
                pass

    def _on_machine_changed(self):
        # type: () -> None
        logger.debug("Global container / machine configuration changed.")

    def _on_backend_state_change(self, state=None):
        # type: (Optional[Any]) -> None
        logger.debug("Backend state changed: %s", state)

    def _on_slicing_finished(self, *args, **kwargs):
        # type: (Any, Any) -> None
        """Сигнализирует о завершении генерации G-code в CuraEngine."""
        logger.info("CuraEngine slicingFinished signal received.")
        self._is_slicing = False
        self.slicing_completed_event.set()
        if self.slicingFinishedSignal is not None and hasattr(self.slicingFinishedSignal, "emit"):
            try:
                self.slicingFinishedSignal.emit()
            except Exception:
                pass

    def reset_slicing_event(self):
        # type: () -> None
        """Сбрасывает флаг готовности слайсинга перед запуском новой нарезки."""
        self._is_slicing = True
        self.slicing_completed_event.clear()

    def wait_for_slicing(self, timeout_sec=90.0):
        # type: (float) -> bool
        """
        Блокирует вызывающий поток (MCP tool) до завершения слайсинга.

        Returns:
            bool: True если слайсинг успешно завершился вовремя, иначе False (тайм-аут).
        """
        finished = self.slicing_completed_event.wait(timeout=float(timeout_sec))
        self._is_slicing = False
        return finished


__all__ = ["SlicerEventListener"]
