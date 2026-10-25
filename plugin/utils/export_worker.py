"""Background worker thread for asynchronous slicing and artifact export.

Executes slicing backend wait, 3MF serialization, G-code saving, and screenshot capture
in a separate thread to prevent freezing the Qt main GUI event loop.
"""

import logging
import os
import time

logger = logging.getLogger("ExportWorker")

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal
    except ImportError:
        try:
            from PySide2.QtCore import QThread, Signal as pyqtSignal
        except ImportError:
            try:
                from PySide6.QtCore import QThread, Signal as pyqtSignal
            except ImportError:
                import threading

                class _FallbackSignalDescriptor(object):
                    def __init__(self, *types):
                        self.types = types

                    def __get__(self, instance, owner):
                        if instance is None:
                            return self
                        if not hasattr(instance, "_signals_map"):
                            instance._signals_map = {}
                        if self not in instance._signals_map:
                            instance._signals_map[self] = _FallbackBoundSignal(self.types)
                        return instance._signals_map[self]

                class _FallbackBoundSignal(object):
                    def __init__(self, types):
                        self.types = types
                        self._slots = []

                    def connect(self, slot):
                        if slot not in self._slots:
                            self._slots.append(slot)

                    def disconnect(self, slot):
                        if slot in self._slots:
                            self._slots.remove(slot)

                    def emit(self, *args):
                        for slot in list(self._slots):
                            try:
                                slot(*args)
                            except Exception as e:
                                logger.error("Exception in signal slot %s: %s", slot, e)

                class QThread(object):
                    def __init__(self, parent=None):
                        self.parent = parent
                        self._thread = None
                        self._is_running = False

                    def start(self):
                        self._is_running = True
                        self._thread = threading.Thread(target=self._run_wrapper)
                        self._thread.daemon = True
                        self._thread.start()

                    def _run_wrapper(self):
                        try:
                            self.run()
                        finally:
                            self._is_running = False

                    def isRunning(self):
                        return self._is_running

                pyqtSignal = _FallbackSignalDescriptor


class ExportWorker(QThread):
    """Worker thread that executes background slicing and exports 3MF / G-code / screenshots."""

    progressChanged = pyqtSignal(str, str)
    exportFinished = pyqtSignal(bool, str, str)

    def __init__(self, target_dir, model_name="model_submission", mcp_server=None,
                 chat_window=None, dispatcher=None, timeout_sec=480, require_gcode=False, parent=None):
        super(ExportWorker, self).__init__(parent)
        self.target_dir = target_dir
        self.model_name = (model_name or "model_submission").strip()
        self.mcp_server = mcp_server
        self.chat_window = chat_window
        self.dispatcher = dispatcher
        self.timeout_sec = float(timeout_sec)
        self.require_gcode = bool(require_gcode)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    @property
    def is_cancelled(self):
        return self._is_cancelled

    def run(self):
        try:
            clean_dir = os.path.normpath(os.path.abspath(self.target_dir))
            os.makedirs(clean_dir, exist_ok=True)

            if self._is_cancelled:
                self.exportFinished.emit(False, "Экспорт отменён пользователем.", "")
                return

            # Если явно требуется генерация G-кода:
            if self.require_gcode:
                has_gcode = False
                def _check_gcode():
                    from plugin.utils.artifact_exporter import ArtifactExporter
                    app = ArtifactExporter._get_application()
                    if app is None or not hasattr(app, "getController"):
                        return False
                    backend = getattr(app, "getBackend", lambda: None)()
                    if backend is not None:
                        state = getattr(backend, "getState", lambda: None)()
                        state_name = str(getattr(state, "name", state)).lower()
                        if "processing" in state_name or "slicing" in state_name:
                            return False
                    scene = app.getController().getScene() if hasattr(app, "getController") else None
                    gcode_dict = getattr(scene, "gcode_dict", {}) if scene is not None else {}
                    if not gcode_dict:
                        return False
                    for gcode_list in gcode_dict.values():
                        if not gcode_list:
                            continue
                        for chunk in gcode_list:
                            chunk_str = str(chunk)
                            if ";TYPE:WALL-OUTER" in chunk_str or ";TYPE:WALL-INNER" in chunk_str or ";TYPE:FILL" in chunk_str or ";TYPE:SKIN" in chunk_str:
                                return True
                    return False

                try:
                    if self.dispatcher and hasattr(self.dispatcher, "execute_sync"):
                        has_gcode = bool(self.dispatcher.execute_sync(_check_gcode))
                    else:
                        has_gcode = bool(_check_gcode())
                except Exception as exc:
                    logger.warning("Could not check scene G-code: %s", exc)

                if not has_gcode:
                    if self.mcp_server is None:
                        raise RuntimeError("MCPServer недоступен для запуска нарезки.")

                    self.progressChanged.emit("Нарезка модели", "Запущен бэкенд слайсера, расчёт слоёв и G-кода…")
                    slicing_result = self.mcp_server.call_tool(
                        "run_slicing_and_generate_gcode",
                        {"timeout_sec": self.timeout_sec}
                    )
                    if isinstance(slicing_result, dict) and str(slicing_result.get("status", "")).lower() in ("error", "failed"):
                        err = slicing_result.get("error") or slicing_result.get("message") or "Слайсер не создал G-code."
                        raise RuntimeError(str(err))

            if self._is_cancelled:
                self.exportFinished.emit(False, "Экспорт отменён пользователем.", "")
                return

            # Экспорт: конвертируем project.3mf и сохраняем скриншот решения (+ gcode при наличии)
            self.progressChanged.emit("Сохранение артефактов", "Конвертируем project.3mf и делаем скриншот…")
            from plugin.utils.artifact_exporter import ArtifactExporter
            exporter = ArtifactExporter(clean_dir, dispatcher=self.dispatcher)
            report = exporter.export_all_for_model(
                self.model_name,
                chat_window=self.chat_window,
                validate=False,
                target_dir=clean_dir,
                require_gcode=self.require_gcode
            )

            export_dir = report.get("directory", clean_dir)
            screenshot_path = report.get("chat_screenshot")
            screenshot_name = os.path.basename(screenshot_path) if screenshot_path else "chat.png"

            if report.get("result_gcode"):
                msg = "Файлы project.3mf, {0} и result.gcode успешно сохранены в папку:\n{1}".format(screenshot_name, export_dir)
            else:
                msg = "Файлы project.3mf и {0} успешно сохранены в папку:\n{1}".format(screenshot_name, export_dir)

            self.progressChanged.emit("Готово", "Экспорт 3MF и скриншота успешно завершён.")
            self.exportFinished.emit(True, msg, export_dir)

        except Exception as exc:
            logger.exception("ExportWorker failed: %s", exc)
            self.exportFinished.emit(False, "Экспорт не выполнен: {0}".format(exc), "")
