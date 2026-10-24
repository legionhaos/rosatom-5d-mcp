# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import threading
from typing import Any, Optional

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
                    def __init__(self, *args, **kwargs):
                        pass

                class _Sig(object):
                    def __init__(self, *a, **k):
                        self._slots = []

                    def __get__(self, inst, owner):
                        return self

                    def connect(self, slot):
                        self._slots.append(slot)

                    def emit(self, *a):
                        for s in list(self._slots):
                            try:
                                s(*a)
                            except Exception:
                                pass

                def pyqtSignal(*a, **k):
                    return _Sig()

logger = logging.getLogger("SlicerEventListener")


class SlicerEventListener(QObject):

    sceneChangedSignal = pyqtSignal(object)
    slicingFinishedSignal = pyqtSignal()
    slicingFailedSignal = pyqtSignal(str)

    def __init__(self, application=None, parent=None):
        # type: (Any, Any) -> None
        super(SlicerEventListener, self).__init__(parent)
        self._app = application
        self._slicing_done = threading.Event()
        self._last_backend_state = None
        self._attached = False

    def _application(self):
        if self._app is not None:
            return self._app
        try:
            from cura.CuraApplication import CuraApplication
            self._app = CuraApplication.getInstance()
        except Exception:
            self._app = None
        return self._app

    def attach_signals(self):
        # type: () -> bool
        if self._attached:
            return True

        app = self._application()
        if app is None:
            logger.warning("SlicerEventListener: CuraApplication недоступно, сигналы не подключены.")
            return False

        try:
            controller = app.getController()
            scene = controller.getScene() if controller else None
            if scene is not None and hasattr(scene, "sceneChanged"):
                scene.sceneChanged.connect(self._on_scene_changed)
        except Exception as exc:
            logger.warning("Не удалось подключить sceneChanged: %s", exc)

        try:
            backend = app.getBackend()
            if backend is not None and hasattr(backend, "backendStateChange"):
                backend.backendStateChange.connect(self._on_backend_state_change)
            if backend is not None and hasattr(backend, "slicingCancelled"):
                backend.slicingCancelled.connect(self._on_slicing_cancelled)
        except Exception as exc:
            logger.warning("Не удалось подключить сигналы backend: %s", exc)

        self._attached = True
        return True

    def _on_scene_changed(self, source=None):
        # type: (Any) -> None
        try:
            self.sceneChangedSignal.emit(source)
        except Exception:
            pass

    def _on_backend_state_change(self, state):
        # type: (Any) -> None
        self._last_backend_state = state
        done_state = self._resolve_done_state()
        error_state = self._resolve_error_state()

        if done_state is not None and state == done_state:
            self._on_slicing_finished()
        elif error_state is not None and state == error_state:
            self._on_slicing_failed("Backend перешёл в состояние ошибки.")

    def _resolve_done_state(self):
        try:
            from UM.Backend.Backend import BackendState
            return BackendState.Done
        except Exception:
            return None

    def _resolve_error_state(self):
        try:
            from UM.Backend.Backend import BackendState
            return BackendState.Error
        except Exception:
            return None

    def _on_slicing_finished(self, backend=None):
        # type: (Any) -> None
        self._slicing_done.set()
        try:
            self.slicingFinishedSignal.emit()
        except Exception:
            pass

    def _on_slicing_failed(self, message):
        # type: (str) -> None
        self._slicing_done.set()
        try:
            self.slicingFailedSignal.emit(str(message))
        except Exception:
            pass

    def _on_slicing_cancelled(self):
        # type: () -> None
        self._slicing_done.set()

    def reset(self):
        # type: () -> None
        self._slicing_done.clear()

    def wait_for_slicing(self, timeout_sec=90.0):
        # type: (float) -> bool
        return self._slicing_done.wait(timeout=timeout_sec)


__all__ = ["SlicerEventListener"]
