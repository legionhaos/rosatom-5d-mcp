# -*- coding: utf-8 -*-
"""
Viewport Camera & Screenshot Manager for STE Slicer.

Manages 3D scene camera angles (isometric view, focus on model)
and captures screenshots for LLM multimodal analysis and competition deliverables.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
from typing import Any, Optional

try:
    from PyQt5.QtCore import QObject
    from PyQt5.QtGui import QImage, QGuiApplication, QPixmap
except ImportError:
    try:
        from PyQt6.QtCore import QObject
        from PyQt6.QtGui import QImage, QGuiApplication, QPixmap
    except ImportError:
        try:
            from PySide2.QtCore import QObject
            from PySide2.QtGui import QImage, QGuiApplication, QPixmap
        except ImportError:
            try:
                from PySide6.QtCore import QObject
                from PySide6.QtGui import QImage, QGuiApplication, QPixmap
            except ImportError:
                class QObject(object):
                    pass
                QImage = None
                QGuiApplication = None
                QPixmap = None

from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher, run_in_main_thread

logger = logging.getLogger("ViewportCameraManager")


class ViewportCameraManager(object):
    """
    Управление ракурсом 3D-камеры и фиксация скриншотов рабочего стола и чата.
    """

    def __init__(self, application=None):
        # type: (Optional[Any]) -> None
        self._application = application

    def _get_app(self):
        if self._application is not None:
            return self._application
        try:
            from cura.CuraApplication import CuraApplication
            return CuraApplication.getInstance()
        except Exception:
            return None

    @run_in_main_thread
    def focus_on_build_plate(self, view_angle="3d_isometric"):
        # type: (str) -> None
        """
        Выставляет наглядный изометрический ракурс камеры на платформе построения.
        """
        app = self._get_app()
        if app is None:
            return

        try:
            controller = app.getController()
            if not controller:
                return
            scene = controller.getScene()
            if not scene:
                return

            camera = scene.getActiveCamera()
            if not camera:
                return

            # В Uranium камера настраивается через setPosition и lookAt
            if hasattr(camera, "setPosition") and hasattr(camera, "lookAt"):
                from UM.Math.Vector import Vector
                if view_angle == "3d_isometric":
                    # Стандартная изометрия под 45 градусов
                    camera.setPosition(Vector(200.0, 260.0, 300.0))
                    camera.lookAt(Vector(0.0, 50.0, 0.0))
                elif view_angle == "top":
                    camera.setPosition(Vector(0.0, 450.0, 0.0))
                    camera.lookAt(Vector(0.0, 0.0, 0.0))
                elif view_angle == "front":
                    camera.setPosition(Vector(0.0, 50.0, 400.0))
                    camera.lookAt(Vector(0.0, 50.0, 0.0))

            logger.info("Camera view adjusted to '%s'", view_angle)
        except Exception as e:
            logger.debug("focus_on_build_plate non-critical notice: %s", e)

    @run_in_main_thread
    def focus_on_node(self, node):
        # type: (Any) -> None
        """Фокусирует камеру на конкретном объекте сцены."""
        app = self._get_app()
        if app is None or node is None:
            return
        try:
            controller = app.getController()
            camera_tool = controller.getTool("CameraTool") if controller else None
            if camera_tool and hasattr(camera_tool, "zoomToNodes"):
                camera_tool.zoomToNodes([node])
            else:
                self.focus_on_build_plate()
        except Exception as e:
            logger.debug("focus_on_node fallback: %s", e)
            self.focus_on_build_plate()

    @run_in_main_thread
    def capture_window_screenshot(self, target_window, save_path):
        # type: (Any, str) -> str
        """
        Делает скриншот окна (QQuickWindow или виджета) и сохраняет в save_path.
        """
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

        # 1. Попытка через grabWindow (QQuickWindow)
        if target_window is not None and hasattr(target_window, "grabWindow"):
            try:
                image = target_window.grabWindow()
                if image is not None and not image.isNull():
                    image.save(save_path, "PNG")
                    logger.info("Screenshot saved via grabWindow: %s", save_path)
                    return save_path
            except Exception as e:
                logger.warning("grabWindow failed: %s", e)

        # 2. Попытка через QScreen.grabWindow (активное окно рабочего стола)
        if QGuiApplication is not None:
            try:
                screen = QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if pixmap and not pixmap.isNull():
                        pixmap.save(save_path, "PNG")
                        logger.info("Screenshot saved via primaryScreen: %s", save_path)
                        return save_path
            except Exception as e:
                logger.warning("primaryScreen grab failed: %s", e)

        # 3. Резервный пустой PNG 1x1 если нет графической подсистемы
        try:
            if QImage is not None:
                img = QImage(640, 480, QImage.Format_RGB32)
                img.fill(0xFFFFFF)
                img.save(save_path, "PNG")
                return save_path
        except Exception:
            pass

        return save_path

    def capture_viewport_screenshot(self, save_path):
        # type: (str) -> str
        """Снимок 3D-сцены слайсера."""
        app = self._get_app()
        main_window = None
        if app and hasattr(app, "getMainWindow"):
            main_window = app.getMainWindow()
        return self.capture_window_screenshot(main_window, save_path)


__all__ = ["ViewportCameraManager"]
