# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("ViewportCameraManager")

try:
    from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
except (ImportError, AttributeError):
    class MainThreadDispatcher(object):
        @staticmethod
        def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)


class ViewportCameraManager(object):

    def __init__(self, application=None):
        # type: (Any) -> None
        self._app = application
        self._chat_window = None

    def _application(self):
        if self._app is not None:
            return self._app
        try:
            from cura.CuraApplication import CuraApplication
            self._app = CuraApplication.getInstance()
        except Exception:
            self._app = None
        return self._app

    def set_chat_window(self, window):
        # type: (Any) -> None
        self._chat_window = window

    def get_chat_window(self):
        # type: () -> Any
        return self._chat_window

    def focus_on_build_plate(self, view_angle="3d_isometric"):
        # type: (str) -> bool
        return MainThreadDispatcher.run_sync(self._focus_impl, view_angle)

    def _focus_impl(self, view_angle):
        # type: (str) -> bool
        from UM.Math.Vector import Vector

        app = self._application()
        if app is None:
            return False

        controller = app.getController()
        if controller is None:
            return False

        camera = controller.getScene().getActiveCamera() if controller.getScene() else None
        if camera is None:
            return False

        presets = {
            "3d_isometric": Vector(-250, 250, 250),
            "front": Vector(0, 100, 350),
            "top": Vector(0, 400, 1),
            "right": Vector(350, 100, 0),
        }
        target = presets.get(view_angle, presets["3d_isometric"])

        try:
            camera.setPosition(target)
            if hasattr(camera, "lookAt"):
                camera.lookAt(Vector(0, 0, 0))
            return True
        except Exception as exc:
            logger.warning("focus_on_build_plate failed: %s", exc)
            return False

    def capture_window_screenshot(self, target_qquick_window, save_path):
        # type: (Any, str) -> Optional[str]
        return MainThreadDispatcher.run_sync(
            self._capture_impl, target_qquick_window, save_path
        )

    def _capture_impl(self, target_qquick_window, save_path):
        # type: (Any, str) -> Optional[str]
        window = target_qquick_window or self._chat_window
        if window is None:
            return None

        grabber = getattr(window, "grabWindow", None)
        if grabber is None:
            return None

        try:
            directory = os.path.dirname(os.path.abspath(save_path))
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)

            image = grabber()
            if image is None:
                return None
            saved = image.save(save_path)
            if saved:
                return save_path
            return None
        except Exception as exc:
            logger.warning("capture_window_screenshot failed: %s", exc)
            return None


__all__ = ["ViewportCameraManager"]
