# -*- coding: utf-8 -*-
import functools
import logging
import threading
from typing import Any, Callable

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

try:
    from plugin.utils.logger import get_logger
    logger = get_logger("MainThreadDispatcher")
except Exception:
    logger = logging.getLogger("MainThreadDispatcher")

_DEFAULT_TIMEOUT_SEC = 30.0


class MainThreadDispatcher(object):

    @classmethod
    def _application(cls):
        try:
            from UM.Application import Application
            app = Application.getInstance()
            if app is not None:
                return app
        except Exception:
            pass
        try:
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
            if app is not None:
                return app
        except Exception:
            pass
        return None

    @classmethod
    def is_main_thread(cls):
        # type: () -> bool
        if QCoreApplication is None or QThread is None:
            return True
        app = QCoreApplication.instance()
        if app is None:
            return True
        try:
            return QThread.currentThread() == app.thread()
        except Exception:
            return True

    @classmethod
    def _post_to_main_thread(cls, func):
        # type: (Callable[[], Any]) -> bool
        app = cls._application()
        if app is None:
            return False
        try:
            from UM.Application import Application
            from UM.Event import CallFunctionEvent
            event = CallFunctionEvent(func, (), {})
            Application.getInstance().functionEvent(event)
            return True
        except Exception:
            pass
        poster = getattr(app, "callLater", None)
        if poster is not None:
            try:
                poster(func)
                return True
            except Exception:
                pass
        return False

    @classmethod
    def execute_sync(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> Any
        timeout = kwargs.pop("timeout", _DEFAULT_TIMEOUT_SEC)

        if cls.is_main_thread():
            return func(*args, **kwargs)

        result_box = [None]
        error_box = [None]
        done = threading.Event()

        def _runner():
            try:
                result_box[0] = func(*args, **kwargs)
            except BaseException as exc:
                error_box[0] = exc
            finally:
                done.set()

        if not cls._post_to_main_thread(_runner):
            logger.error("Cannot dispatch '%s' to GUI thread: application/event loop unavailable.",
                         getattr(func, "__name__", repr(func)))
            raise RuntimeError("Не удалось передать операцию в главный поток Cura: приложение недоступно.")

        if not done.wait(timeout):
            raise TimeoutError(
                "Операция в главном потоке GUI не завершилась за {0} с.".format(timeout)
            )

        if error_box[0] is not None:
            raise error_box[0]
        return result_box[0]

    @classmethod
    def run_sync(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> Any
        return cls.execute_sync(func, *args, **kwargs)

    @classmethod
    def call_on_main_thread(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> Any
        return cls.execute_sync(func, *args, **kwargs)

    @classmethod
    def execute_async(cls, func, *args, **kwargs):
        # type: (Callable[..., Any], Any, Any) -> bool
        if cls.is_main_thread():
            try:
                func(*args, **kwargs)
                return True
            except Exception as exc:
                logger.exception("execute_async direct call failed: %s", exc)
                return False

        def _runner():
            try:
                func(*args, **kwargs)
            except Exception as exc:
                logger.exception("execute_async main-thread call failed: %s", exc)

        return cls._post_to_main_thread(_runner)


def run_in_main_thread(timeout=_DEFAULT_TIMEOUT_SEC):
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            return MainThreadDispatcher.execute_sync(func, *args, timeout=timeout, **kwargs)
        return _wrapper

    if callable(timeout):
        _target = timeout
        timeout = _DEFAULT_TIMEOUT_SEC
        return _decorator(_target)
    return _decorator


__all__ = ["MainThreadDispatcher", "run_in_main_thread"]
