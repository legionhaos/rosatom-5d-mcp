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
        self._target = None
        self._distance = 350.0
        self._yaw = -45.0
        self._pitch = 35.264

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
        return MainThreadDispatcher.run_sync(self._focus_impl, "3d_isometric")

    def _focus_impl(self, view_angle):
        # type: (str) -> bool
        from UM.Math.Vector import Vector

        app = self._application()
        if app is None:
            return False

        controller = app.getController()
        if controller is None:
            return False

        scene = controller.getScene()
        camera = scene.getActiveCamera() if scene else None
        if camera is None:
            return False

        target, radius = self._scene_target_and_radius(scene)
        self._target = target
        presets = {
            "3d_isometric": (-45.0, 35.264),
            "isometric_alt": (45.0, 35.264),
            "front": (0.0, 16.0),
            "back": (180.0, 16.0),
            "top": (0.0, 88.0),
            "right": (90.0, 16.0),
            "left": (-90.0, 16.0),
        }
        self._yaw, self._pitch = presets.get(view_angle, presets["3d_isometric"])
        self._distance = radius * (3.6 if view_angle in ("front", "back", "right", "left") else 2.7)
        self._distance = max(90.0, min(1600.0, self._distance))

        try:
            self._set_camera_pose(camera, Vector, self._target, self._distance, self._yaw, self._pitch)
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
        scene = controller.getScene() if controller else None
        camera = scene.getActiveCamera() if scene else None
        if camera is None:
            return False
        try:
            from UM.Math.Vector import Vector
            self._ensure_camera_state(scene, camera)
            self._distance = max(50.0, min(1800.0, self._distance * float(factor)))
            self._set_camera_pose(camera, Vector, self._target, self._distance, self._yaw, self._pitch)
            return True
        except Exception as exc:
            logger.warning("zoom failed: %s", exc)
            return False

    def pan(self, delta_x, delta_y):
        return MainThreadDispatcher.run_sync(self._pan_impl, delta_x, delta_y)

    def _pan_impl(self, delta_x, delta_y):
        app = self._application()
        if app is None:
            return False
        controller = app.getController()
        scene = controller.getScene() if controller else None
        camera = scene.getActiveCamera() if scene else None
        if camera is None:
            return False
        try:
            from UM.Math.Vector import Vector
            import math
            self._ensure_camera_state(scene, camera)
            yaw = math.radians(self._yaw)
            right = (math.cos(yaw), 0.0, -math.sin(yaw))
            up = (-math.sin(yaw) * math.sin(math.radians(self._pitch)),
                  math.cos(math.radians(self._pitch)),
                  -math.cos(yaw) * math.sin(math.radians(self._pitch)))
            scale = self._distance * 0.0025
            self._target = Vector(
                self._target.x - (right[0] * float(delta_x) + up[0] * float(delta_y)) * scale,
                self._target.y - (right[1] * float(delta_x) + up[1] * float(delta_y)) * scale,
                self._target.z - (right[2] * float(delta_x) + up[2] * float(delta_y)) * scale)
            self._set_camera_pose(camera, Vector, self._target, self._distance, self._yaw, self._pitch)
            return True
        except Exception as exc:
            logger.warning("pan failed: %s", exc)
            return False

    def fit(self):
        return MainThreadDispatcher.run_sync(self._fit_impl)

    def _fit_impl(self):
        self._target = None
        return self._focus_impl("3d_isometric")

    def _ensure_camera_state(self, scene, camera):
        if self._target is None:
            self._target, radius = self._scene_target_and_radius(scene)
            pos = camera.getPosition()
            dx, dy, dz = pos.x - self._target.x, pos.y - self._target.y, pos.z - self._target.z
            import math
            distance = math.sqrt(dx * dx + dy * dy + dz * dz)
            self._distance = distance if distance > 1.0 else radius * 2.7
            self._yaw = math.degrees(math.atan2(dx, dz))
            self._pitch = math.degrees(math.asin(max(-0.99, min(0.99, dy / self._distance))))

    @staticmethod
    def _scene_target_and_radius(scene):
        from UM.Math.Vector import Vector
        nodes = scene.getRoot().getAllChildren() if scene and hasattr(scene.getRoot(), "getAllChildren") else []
        for node in nodes:
            if not hasattr(node, "getMeshData") or node.getMeshData() is None:
                continue
            if type(node).__name__.lower().find("grid") >= 0 or type(node).__name__.lower().find("buildplate") >= 0:
                continue
            if hasattr(node, "callDecoration"):
                try:
                    if node.callDecoration("isNonPrintingMesh"):
                        continue
                except Exception:
                    pass
            box = getattr(node, "getBoundingBox", lambda: None)()
            if box is None:
                continue
            try:
                width = ViewportCameraManager._number(box, "width")
                depth = ViewportCameraManager._number(box, "depth")
                height = ViewportCameraManager._number(box, "height")
                center = Vector(
                    (ViewportCameraManager._number(box, "left") + ViewportCameraManager._number(box, "right")) / 2.0,
                    (ViewportCameraManager._number(box, "bottom") + ViewportCameraManager._number(box, "top")) / 2.0,
                    (ViewportCameraManager._number(box, "front") + ViewportCameraManager._number(box, "back")) / 2.0)
                radius = max(35.0, math.sqrt(width * width + depth * depth + height * height) * 0.5)
                return center, radius
            except Exception:
                pass
        return Vector(0, 0, 0), 90.0

    @staticmethod
    def _number(obj, name):
        value = getattr(obj, name, 0.0)
        return float(value() if callable(value) else value)

    @staticmethod
    def _set_camera_pose(camera, vector_type, target, distance, yaw_deg, pitch_deg):
        import math
        yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
        horizontal = distance * math.cos(pitch)
        camera_position = vector_type(
            target.x + horizontal * math.sin(yaw),
            target.y + distance * math.sin(pitch),
            target.z + horizontal * math.cos(yaw))
        camera.setPosition(camera_position)
        if hasattr(camera, "lookAt"):
            camera.lookAt(target)
        else:
            camera.setViewCenter(target)

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
        scene = controller.getScene()
        camera = scene.getActiveCamera() if scene else None
        if camera is None:
            return False
        try:
            from UM.Math.Vector import Vector
            self._ensure_camera_state(scene, camera)
            self._yaw += float(delta_yaw_deg)
            self._pitch = max(-85.0, min(85.0, self._pitch + float(delta_pitch_deg)))
            self._set_camera_pose(camera, Vector, self._target, self._distance, self._yaw, self._pitch)
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
