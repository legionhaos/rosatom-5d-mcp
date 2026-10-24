# -*- coding: utf-8 -*-
"""
MainThreadDispatcher for STE Slicer.

Provides 100% thread-safe execution of Cura/Uranium API and Qt GUI operations
from background threads (such as AgentWorker QThread).
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import logging
import sys
import threading
from typing import Any, Callable, Optional, TypeVar

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


def is_main_thread():
    # type: () -> bool
    """Проверяет, выполняется ли текущий код в главном GUI-потоке Qt/Python."""
    if QCoreApplication is not None:
        app = QCoreApplication.instance()
        if app is not None and QThread is not None:
            try:
                return QThread.currentThread() == app.thread()
            except Exception:
                pass
    if hasattr(threading, "main_thread"):
        return threading.current_thread() is threading.main_thread()
    return isinstance(threading.current_thread(), threading._MainThread)


class MainThreadDispatcher(object):
    """
    Диспетчер потокобезопасного выполнения функций в основном потоке GUI STE Slicer/Cura.
    Поддерживает как статический вызов (MainThreadDispatcher.run_sync),
    так и вызов через экземпляр (dispatcher.execute_sync).
    """

    def __init__(self, timeout=30.0):
        # type: (float) -> None
        self.default_timeout = float(timeout)

    @classmethod
    def execute_sync(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> Any
        """
        Ставит функцию func в очередь главного потока GUI через CuraApplication.callLater(),
        блокирует вызывающий рабочий поток до завершения и возвращает результат либо
        пробрасывает возникшее исключение.
        """
        timeout = kwargs.pop("timeout", 30.0)

        # Если уже в главном потоке или Qt не запущен — вызываем напрямую
        if is_main_thread():
            return func(*args, **kwargs)

        app = None
        try:
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
        except Exception:
            try:
                from UM.Application import Application
                app = Application.getInstance()
            except Exception:
                app = None

        if app is None or not hasattr(app, "callLater"):
            # Вне слайсера (юнит-тесты) вызываем напрямую
            return func(*args, **kwargs)

        result_box = [None]
        error_box = [None]
        done_event = threading.Event()

        def _worker():
            try:
                result_box[0] = func(*args, **kwargs)
            except BaseException as e:
                error_box[0] = e
            finally:
                done_event.set()

        try:
            app.callLater(_worker)
        except Exception as e:
            logger.warning("app.callLater failed: %s; executing directly.", e)
            return func(*args, **kwargs)

        finished = done_event.wait(timeout=timeout)
        if not finished:
            raise TimeoutError(
                "MainThreadDispatcher timed out after {0}s waiting for {1}".format(
                    timeout, getattr(func, "__name__", str(func))
                )
            )

        if error_box[0] is not None:
            raise error_box[0]

        return result_box[0]

    @classmethod
    def execute_async(cls, func, *args, **kwargs):
        # type: (Callable[..., None], Any, Any) -> None
        """Неблокирующая постановка вызова функции в очередь главного потока."""
        if is_main_thread():
            func(*args, **kwargs)
            return

        app = None
        try:
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
        except Exception:
            try:
                from UM.Application import Application
                app = Application.getInstance()
            except Exception:
                app = None

        if app is not None and hasattr(app, "callLater"):
            app.callLater(lambda: func(*args, **kwargs))
        else:
            func(*args, **kwargs)

    # Совместимость со всеми вызовами в проекте:
    run_sync = execute_sync
    call_on_main_thread = execute_sync


def run_in_main_thread(func):
    """Декоратор для автоматического выполнения метода в главном потоке."""
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        return MainThreadDispatcher.execute_sync(func, *args, **kwargs)
    return _wrapper


__all__ = ["MainThreadDispatcher", "run_in_main_thread", "is_main_thread"]
