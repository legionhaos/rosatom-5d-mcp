# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import traceback
from typing import Any, Dict, Optional

try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        name = ""
        description = ""
        parameters_schema = {}  # type: Dict[str, Any]

        def execute(self, **kwargs):
            # type: (**Any) -> Dict[str, Any]
            raise NotImplementedError

try:
    from utils.exceptions import (
        STEPluginError,
        SceneError,
        SlicingFailedError,
        SlicingTimeoutError,
        ArtifactExportError,
        ArtifactValidationError,
        format_exception_for_llm,
    )
except (ImportError, AttributeError):
    class STEPluginError(Exception):
        def __init__(self, message, code="STE_PLUGIN_ERROR", details=None):
            super(STEPluginError, self).__init__(message)
            self.code = code
            self.details = details or {}
            self.message = message

    class SceneError(STEPluginError):
        def __init__(self, message, details=None):
            super(SceneError, self).__init__(message, code="SCENE_ERROR", details=details)

    class SlicingFailedError(STEPluginError):
        def __init__(self, message, details=None):
            super(SlicingFailedError, self).__init__(message, code="SLICING_FAILED", details=details)

    class SlicingTimeoutError(STEPluginError):
        def __init__(self, message, details=None):
            super(SlicingTimeoutError, self).__init__(message, code="SLICING_TIMEOUT", details=details)

    class ArtifactExportError(STEPluginError):
        def __init__(self, message, details=None):
            super(ArtifactExportError, self).__init__(message, code="ARTIFACT_EXPORT", details=details)

    class ArtifactValidationError(STEPluginError):
        def __init__(self, message, details=None):
            super(ArtifactValidationError, self).__init__(message, code="ARTIFACT_VALIDATION", details=details)

    def format_exception_for_llm(exc):
        # type: (BaseException) -> Dict[str, Any]
        return {
            "status": "ERROR",
            "error_code": getattr(exc, "code", type(exc).__name__),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc(),
        }

try:
    from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
except (ImportError, AttributeError):
    class MainThreadDispatcher(object):
        @staticmethod
        def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)

        @staticmethod
        def execute_sync(func, *args, **kwargs):
            return func(*args, **kwargs)


def _format_duration(seconds):
    # type: (float) -> str
    try:
        total = int(round(float(seconds)))
    except (ValueError, TypeError):
        return "0 мин"
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours > 0:
        return "{0} ч {1} мин".format(hours, minutes)
    return "{0} мин".format(minutes)


class SlicingTool(BaseMCPTool):

    name = "run_slicing_and_generate_gcode"
    description = (
        "Запуск слайсинга текущей сцены в STE Slicer, ожидание завершения бэкенда "
        "и сбор статистики печати (время, масса филамента, количество слоёв)."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "timeout_sec": {
                "type": "number",
                "description": "Максимальное время ожидания завершения слайсинга в секундах (по умолчанию 90)."
            }
        },
        "required": []
    }

    def __init__(self, event_listener=None):
        # type: (Any) -> None
        self._event_listener = event_listener

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        try:
            timeout_sec = float(kwargs.get("timeout_sec", 90.0))

            if self._event_listener is not None and hasattr(self._event_listener, "reset"):
                try:
                    self._event_listener.reset()
                except Exception:
                    pass

            MainThreadDispatcher.run_sync(self._trigger_slice)

            completed = True
            if self._event_listener is not None and hasattr(self._event_listener, "wait_for_slicing"):
                completed = self._event_listener.wait_for_slicing(timeout_sec=timeout_sec)

            if not completed:
                raise SlicingTimeoutError(
                    "Слайсинг не завершился за {0} с.".format(timeout_sec),
                    details={"timeout_sec": timeout_sec}
                )

            stats = MainThreadDispatcher.run_sync(self._collect_slice_stats)

            response = {
                "status": "SUCCESS",
                "slicing_result": "G-code generated",
            }
            response.update(stats)
            return response
        except Exception as exc:
            return format_exception_for_llm(exc)

    def _trigger_slice(self):
        from cura.CuraApplication import CuraApplication

        app = CuraApplication.getInstance()
        if not app:
            raise SceneError("CuraApplication не инициализировано.")

        backend = app.getBackend()
        if backend is None:
            raise SlicingFailedError("Backend слайсера недоступен.")

        if hasattr(backend, "forceSlice"):
            backend.forceSlice()
        elif hasattr(backend, "slice"):
            backend.slice()
        else:
            raise SlicingFailedError("Backend не поддерживает запуск слайсинга (нет forceSlice/slice).")

    def _collect_slice_stats(self):
        # type: () -> Dict[str, Any]
        from cura.CuraApplication import CuraApplication

        app = CuraApplication.getInstance()
        stats = {
            "print_time_sec": None,
            "print_time_formatted": None,
            "material_weight_g": None,
            "filament_length_m": None,
            "layer_count": None,
            "mode_used": None,
        }

        if not app:
            return stats

        try:
            print_information = getattr(app, "getPrintInformation", None)
            info = print_information() if print_information else getattr(app, "printInformation", None)
        except Exception:
            info = None

        if info is not None:
            seconds = self._extract_print_time(info)
            if seconds is not None:
                stats["print_time_sec"] = round(seconds, 1)
                stats["print_time_formatted"] = _format_duration(seconds)

            weights = getattr(info, "materialWeights", None)
            if weights:
                try:
                    stats["material_weight_g"] = round(sum(float(w) for w in weights), 2)
                except (ValueError, TypeError):
                    pass

            lengths = getattr(info, "materialLengths", None)
            if lengths:
                try:
                    stats["filament_length_m"] = round(sum(float(l) for l in lengths), 3)
                except (ValueError, TypeError):
                    pass

        try:
            stack = app.getGlobalContainerStack()
            if stack is not None:
                mode_val = stack.getProperty("ste_print_mode", "value")
                if mode_val in ("5D", "3D"):
                    stats["mode_used"] = mode_val
        except Exception:
            pass

        return stats

    def _extract_print_time(self, info):
        # type: (Any) -> Optional[float]
        times = getattr(info, "currentPrintTime", None)
        if times is None:
            return None
        getter = getattr(times, "getDisplayString", None)
        try:
            total = getattr(times, "getTotalSeconds", None)
            if total is not None:
                return float(total())
        except Exception:
            pass
        try:
            if isinstance(times, (int, float)):
                return float(times)
        except Exception:
            pass
        if getter is not None:
            return None
        return None


class ValidateExportTool(BaseMCPTool):

    name = "validate_and_export_artifacts"
    description = (
        "Сохранение проекта (.3mf), G-кода (result.gcode) и скриншота чата в "
        "results/<model_name>/, их валидация и возврат отчёта о корректности артефактов."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "model_name": {
                "type": "string",
                "description": "Имя модели/прогона для каталога результатов results/<model_name>/."
            },
            "validate": {
                "type": "boolean",
                "description": "Выполнять ли валидацию артефактов после экспорта (по умолчанию true)."
            }
        },
        "required": ["model_name"]
    }

    def __init__(self, settings_mgr=None, camera_manager=None, dispatcher=None):
        # type: (Any, Any, Any) -> None
        self._settings_mgr = settings_mgr
        self._camera_manager = camera_manager
        self._dispatcher = dispatcher

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        try:
            model_name = kwargs.get("model_name")
            validate = bool(kwargs.get("validate", True))

            if not model_name:
                raise ArtifactExportError("Не указано имя модели (model_name) для экспорта.")

            exporter = self._build_exporter()
            chat_window = self._resolve_chat_window()

            report = exporter.export_all_for_model(
                model_name,
                chat_window=chat_window,
                validate=validate
            )

            response = {"status": "SUCCESS"}
            response.update(report)
            return response
        except Exception as exc:
            return format_exception_for_llm(exc)

    def _build_exporter(self):
        from utils.artifact_exporter import ArtifactExporter

        results_root = None
        if self._settings_mgr is not None and hasattr(self._settings_mgr, "get_results_root_dir"):
            try:
                results_root = self._settings_mgr.get_results_root_dir()
            except Exception:
                results_root = None

        if not results_root:
            results_root = os.path.join(os.path.expanduser("~"), "STE_AI_results")

        dispatcher = self._dispatcher or MainThreadDispatcher
        return ArtifactExporter(results_root, dispatcher=dispatcher)

    def _resolve_chat_window(self):
        if self._camera_manager is None:
            return None
        getter = getattr(self._camera_manager, "get_chat_window", None)
        if getter is not None:
            try:
                return getter()
            except Exception:
                return None
        return getattr(self._camera_manager, "chat_window", None)


__all__ = ["SlicingTool", "ValidateExportTool"]
