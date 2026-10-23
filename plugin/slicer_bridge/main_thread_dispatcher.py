# -*- coding: utf-8 -*-
"""
MainThreadDispatcher for STE Slicer.

Safely dispatches callables to the Qt / Uranium / Cura main GUI thread.
"""

import logging
from typing import Callable, Any

try:
    from PyQt5.QtCore import QCoreApplication, QThread
except ImportError:
    try:
        from PyQt6.QtCore import QCoreApplication, QThread
    except ImportError:
        try:
            from PySide2.QtCore import QCoreApplication, QThread
        except ImportError:
            try:
                from PySide6.QtCore import QCoreApplication, QThread
            except ImportError:
                QCoreApplication = None
                QThread = None

logger = logging.getLogger("MainThreadDispatcher")


class MainThreadDispatcher(object):
    """
    Utility class for executing functions on the application's main thread.
    """

    @classmethod
    def call_on_main_thread(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> Any
        """
        Executes a callable on the main thread and returns the result.
        If already on the main thread or Qt is not initialized, executes directly.
        """
        if QCoreApplication is None or QThread is None:
            return func(*args, **kwargs)

        app = QCoreApplication.instance()
        if app is None:
            return func(*args, **kwargs)

        # Check if caller is already on the main thread
        try:
            current_thread = QThread.currentThread()
            app_thread = app.thread()
            if current_thread == app_thread:
                return func(*args, **kwargs)
        except Exception:
            return func(*args, **kwargs)

        # If on background thread, use Cura Application callDecoration or Uranium CallMethodEvent
        try:
            from UM.Application import Application
            cura_app = Application.getInstance()
            if cura_app and hasattr(cura_app, "callDecoration"):
                result = cura_app.callDecoration("callOnMainThread", func, *args, **kwargs)
                if result is not None:
                    return result
        except Exception:
            pass

        # Fallback to direct execution
        return func(*args, **kwargs)
