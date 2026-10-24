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
            "isometric_alt": Vector(250, 250, 250),
            "front": Vector(0, 100, 350),
            "back": Vector(0, 100, -350),
            "top": Vector(0, 420, 1),
            "right": Vector(350, 100, 0),
            "left": Vector(-350, 100, 0),
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

    def zoom(self, factor):
        # type: (float) -> bool
        return MainThreadDispatcher.run_sync(self._zoom_impl, factor)

    def _zoom_impl(self, factor):
        # type: (float) -> bool
        app = self._application()
        if app is None:
            return False
        controller = app.getController()
        if controller is None:
            return False
        camera = controller.getScene().getActiveCamera() if controller.getScene() else None
        if camera is None:
            return False
        try:
            from UM.Math.Vector import Vector
            import math
            pos = camera.getPosition()
            dist = math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z)
            new_dist = max(90.0, min(950.0, dist * float(factor)))
            ratio = new_dist / (dist if dist > 0 else 1.0)
            camera.setPosition(Vector(pos.x * ratio, pos.y * ratio, pos.z * ratio))
            if hasattr(camera, "lookAt"):
                camera.lookAt(Vector(0, 0, 0))
            return True
        except Exception as exc:
            logger.warning("zoom failed: %s", exc)
            return False

    def orbit(self, delta_yaw_deg, delta_pitch_deg):
        # type: (float, float) -> bool
        return MainThreadDispatcher.run_sync(self._orbit_impl, delta_yaw_deg, delta_pitch_deg)

    def _orbit_impl(self, delta_yaw_deg, delta_pitch_deg):
        # type: (float, float) -> bool
        app = self._application()
        if app is None:
            return False
        controller = app.getController()
        if controller is None:
            return False
        camera = controller.getScene().getActiveCamera() if controller.getScene() else None
        if camera is None:
            return False
        try:
            from UM.Math.Vector import Vector
            import math
            pos = camera.getPosition()
            r = math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z)
            if r < 10.0:
                r = 350.0
            yaw = math.atan2(pos.x, pos.z)
            pitch = math.asin(max(-0.99, min(0.99, pos.y / r)))

            yaw += math.radians(float(delta_yaw_deg))
            pitch = max(math.radians(5.0), min(math.radians(85.0), pitch + math.radians(float(delta_pitch_deg))))

            y = r * math.sin(pitch)
            xz = r * math.cos(pitch)
            x = xz * math.sin(yaw)
            z = xz * math.cos(yaw)

            camera.setPosition(Vector(x, y, z))
            if hasattr(camera, "lookAt"):
                camera.lookAt(Vector(0, 0, 0))
            return True
        except Exception as exc:
            logger.warning("orbit failed: %s", exc)
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
