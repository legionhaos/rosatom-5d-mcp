# -*- coding: utf-8 -*-
"""
Экспорт и валидация артефактов прогона: results/<model_name>/{project.3mf, result.gcode, chat_N.png}.

Работа с Cura API выполняется в ГЛАВНОМ потоке Qt: передайте dispatcher (MainThreadDispatcher
с методом execute_sync(func, timeout=...)), если вызываете экспорт из фонового потока агента.
Все импорты UM/cura — ленивые, поэтому validate_* и prepare_model_dir работают и вне слайсера.
"""
import glob
import os
import re
import zipfile
from typing import Any, Callable, Dict, List, Optional

from .exceptions import (ArtifactExportError, ArtifactValidationError, SlicingFailedError)
from .logger import STEPluginLogger

PROJECT_FILE = "project.3mf"
GCODE_FILE = "result.gcode"
SCREENSHOT_PATTERN = "chat_%d.png"

_RE_NOZZLE_TEMP = re.compile(r"^\s*M10[49]\b", re.M)
_RE_BED_TEMP = re.compile(r"^\s*M(140|190)\b", re.M)
_RE_EXTRUSION = re.compile(r"^\s*G[01]\b[^;\n]*\bE-?\d", re.M)
_RE_MULTIAXIS = re.compile(r"^\s*G[01]\b[^;\n]*\s[ABCUV]-?\d", re.M)
_RE_LAYER_COUNT = re.compile(r"^;LAYER_COUNT:(\d+)", re.M)


def sanitize_model_name(model_name):
    # type: (str) -> str
    """Имя папки: без путевых символов; пробелы -> _ ; не пустое."""
    name = re.sub(r"[^\w\-.]+", "_", (model_name or "").strip(), flags=re.UNICODE).strip("._")
    if not name:
        raise ArtifactExportError("Пустое имя модели для папки results/")
    return name


class ArtifactExporter(object):
    """Формирует и проверяет структуру results/<model_name>/."""

    def __init__(self, results_root, dispatcher=None):
        # type: (str, Any) -> None
        self._root = os.path.abspath(results_root)
        self._dispatcher = dispatcher

    # ------------------------------ утилиты ------------------------------- #
    def _on_main(self, func, *args):
        if self._dispatcher is not None:
            return self._dispatcher.execute_sync(func, *args)
        return func(*args)

    @staticmethod
    def _get_application():
        for mod_name in ("steslicer.SteSlicerApplication", "cura.CuraApplication", "UM.Application"):
            try:
                mod = __import__(mod_name, fromlist=["SteSlicerApplication", "CuraApplication", "Application"])
                for attr in ("SteSlicerApplication", "CuraApplication", "Application"):
                    cls_ = getattr(mod, attr, None)
                    if cls_ and hasattr(cls_, "getInstance"):
                        inst = cls_.getInstance()
                        if inst:
                            return inst
            except Exception:
                pass
        return None

    def prepare_model_dir(self, model_name):
        # type: (str) -> str
        """Создаёт (если нужно) и возвращает results/<model_name>/."""
        path = os.path.join(self._root, sanitize_model_name(model_name))
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise ArtifactExportError("Не удалось создать папку %s: %s" % (path, e))
        return path

    def list_models(self):
        # type: () -> List[str]
        if not os.path.isdir(self._root):
            return []
        return sorted(d for d in os.listdir(self._root)
                      if not d.startswith(".") and os.path.isdir(os.path.join(self._root, d)))

    @staticmethod
    def _active_build_plate(app):
        try:
            return int(app.getMultiBuildPlateModel().activeBuildPlate)
        except Exception:
            return 0

    # ------------------------------ запись -------------------------------- #
    def save_3mf_project(self, output_path):
        # type: (str) -> bool
        """Сериализует сцену + стеки настроек (режим 3D/5D, материал, overrides) в project.3mf.
        Возвращает True, иначе бросает ArtifactExportError."""
        def _write():
            from UM.Mesh.MeshWriter import MeshWriter
            app = self._get_application()
            writer = app.getWorkspaceFileHandler().getWriter("3MFWriter")
            if writer is None:
                raise ArtifactExportError("Writer '3MFWriter' (проект) не найден в STE Slicer")
            nodes = [n for n in app.getController().getScene().getRoot().getChildren()
                     if n.callDecoration("isSliceable")]
            tmp = output_path + ".part"
            with open(tmp, "wb") as stream:
                ok = writer.write(stream, nodes, MeshWriter.OutputMode.BinaryMode)
            if not ok:
                raise ArtifactExportError("3MFWriter вернул ошибку: %s" % writer.getInformation())
            os.replace(tmp, output_path)
            return True

        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            result = self._on_main(_write)
            STEPluginLogger.info("project.3mf сохранён: %s" % output_path, tag="EXPORT")
            return bool(result)
        except ArtifactExportError:
            raise
        except Exception as e:
            raise ArtifactExportError("Не удалось сохранить 3MF: %s" % e)

    def save_gcode_result(self, output_path):
        # type: (str) -> bool
        """Пишет G-code из scene.gcode_dict[active_build_plate] в result.gcode (UTF-8)."""
        def _collect():
            app = self._get_application()
            scene = app.getController().getScene()
            gcode_list = getattr(scene, "gcode_dict", {}).get(self._active_build_plate(app))
            return list(gcode_list) if gcode_list else None

        try:
            gcode_list = self._on_main(_collect)
        except Exception as e:
            raise ArtifactExportError("Не удалось получить G-code из сцены: %s" % e)
        if not gcode_list:
            raise SlicingFailedError("G-code отсутствует: слайсинг не выполнен или завершился ошибкой.")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            tmp = output_path + ".part"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                for chunk in gcode_list:  # элементы уже содержат переводы строк
                    f.write(chunk)
            os.replace(tmp, output_path)
        except (OSError, IOError) as e:
            raise ArtifactExportError("Не удалось записать G-code: %s" % e)
        STEPluginLogger.info("result.gcode сохранён: %s" % output_path, tag="EXPORT")
        return True

    def save_chat_screenshot(self, window, model_dir):
        # type: (Any, str) -> str
        """Скриншот окна (QQuickWindow/QWindow) в chat_N.png со следующим свободным N."""
        existing = glob.glob(os.path.join(model_dir, "chat_*.png"))
        used = set()
        for item in existing:
            match = re.search(r"chat_(\d+)\.png$", os.path.basename(item))
            if match:
                used.add(int(match.group(1)))
        index = 1
        while index in used:
            index += 1
        path = os.path.join(model_dir, SCREENSHOT_PATTERN % index)

        def _grab():
            image = window.grabWindow()
            if image is None or image.isNull() or not image.save(path, "PNG"):
                raise ArtifactExportError("Не удалось сохранить скриншот окна")
            return path

        return self._on_main(_grab)

    # ----------------------------- валидация ------------------------------ #
    @staticmethod
    def _check(checks, name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def validate_gcode_and_3mf(self, path_3mf, path_gcode):
        # type: (str, str) -> Dict[str, Any]
        """Проверяет целостность артефактов. Возвращает
        {"passed", "errors", "warnings", "checks", "gcode_stats"}. Не бросает исключений."""
        checks, errors, warnings, stats = [], [], [], {}

        # ---- 3MF ----
        try:
            if not os.path.isfile(path_3mf):
                errors.append("project.3mf не найден")
            elif not zipfile.is_zipfile(path_3mf):
                errors.append("project.3mf не является ZIP/OPC-контейнером")
            else:
                with zipfile.ZipFile(path_3mf) as zf:
                    bad = zf.testzip()
                    names = zf.namelist()
                if bad:
                    errors.append("Повреждён элемент архива 3MF: %s" % bad)
                has_model = any(n.lower() == "3d/3dmodel.model" for n in names)
                self._check(checks, "3mf:3D/3dmodel.model", has_model)
                if not has_model:
                    errors.append("В 3MF нет 3D/3dmodel.model")
                has_cura = any(n.startswith("Cura/") for n in names)
                self._check(checks, "3mf:Cura settings", has_cura)
                if not has_cura:
                    warnings.append("В 3MF не найдены настройки Cura/*.cfg (возможно, сохранена только геометрия)")
                stats["3mf_entries"] = len(names)
        except Exception as e:
            errors.append("Ошибка чтения 3MF: %s" % e)

        # ---- G-code ----
        try:
            if not os.path.isfile(path_gcode):
                errors.append("result.gcode не найден")
            else:
                size = os.path.getsize(path_gcode)
                stats["gcode_size_bytes"] = size
                if size <= 1024:
                    errors.append("result.gcode слишком мал (%d байт)" % size)
                with open(path_gcode, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                self._check(checks, "gcode:size>1KB", size > 1024, "%d bytes" % size)
                if not _RE_NOZZLE_TEMP.search(text):
                    errors.append("В G-code нет команд нагрева сопла (M104/M109)")
                if not _RE_BED_TEMP.search(text):
                    warnings.append("В G-code нет команд нагрева стола (M140/M190)")
                extrusions = len(_RE_EXTRUSION.findall(text))
                stats["extrusion_moves"] = extrusions
                self._check(checks, "gcode:extrusion", extrusions > 0, "%d moves" % extrusions)
                if extrusions == 0:
                    errors.append("В G-code нет движений с экструзией (G1 ... E...)")
                stats["has_multi_axis_moves"] = bool(_RE_MULTIAXIS.search(text))
                m = _RE_LAYER_COUNT.search(text)
                if m:
                    stats["layer_count"] = int(m.group(1))
                tail = text[-3000:]
                complete = bool(re.search(r"M104\s+S0|M84|M140\s+S0|;End of Gcode|;SETTING_3", tail))
                self._check(checks, "gcode:not truncated", complete)
                if not complete:
                    warnings.append("Конец G-code не похож на финальный скрипт — файл мог оборваться")
        except Exception as e:
            errors.append("Ошибка чтения G-code: %s" % e)

        return {"passed": not errors, "errors": errors, "warnings": warnings,
                "checks": checks, "gcode_stats": stats}

    def verify_model_dir(self, model_name, require_screenshot=False):
        # type: (str, bool) -> Dict[str, Any]
        """Проверка результатов; screenshot требуется только по явному запросу."""
        d = os.path.join(self._root, sanitize_model_name(model_name))
        report = self.validate_gcode_and_3mf(os.path.join(d, PROJECT_FILE), os.path.join(d, GCODE_FILE))
        if require_screenshot and not glob.glob(os.path.join(d, "chat_*.png")):
            report["errors"].append("Нет ни одного скриншота chat_*.png")
            report["passed"] = False
        return report

    # ------------------------------ сборка -------------------------------- #
    def export_all_for_model(self, model_name, chat_window=None, validate=True, target_dir=None):
        # type: (str, Any, bool, Optional[str]) -> Dict[str, Any]
        """Полный экспорт: папка + project.3mf + result.gcode (+ chat_N.png) + валидация.

        Возвращает {"directory","project_3mf","result_gcode","chat_screenshot","validation"}.
        Если validate=True и проверка не пройдена — бросает ArtifactValidationError
        (с отчётом в details), чтобы агент мог перезапустить слайсинг."""
        if target_dir:
            model_dir = os.path.abspath(target_dir)
            try:
                os.makedirs(model_dir, exist_ok=True)
            except OSError as e:
                raise ArtifactExportError("Не удалось создать папку %s: %s" % (model_dir, e))
        else:
            model_dir = self.prepare_model_dir(model_name)
        path_3mf = os.path.join(model_dir, PROJECT_FILE)
        path_gcode = os.path.join(model_dir, GCODE_FILE)

        self.save_gcode_result(path_gcode)
        self.save_3mf_project(path_3mf)

        screenshot = None
        if chat_window is not None:
            try:
                screenshot = self.save_chat_screenshot(chat_window, model_dir)
            except Exception as e:  # скриншот не должен валить весь экспорт
                STEPluginLogger.warning("Скриншот не сохранён: %s" % e, tag="EXPORT")

        result = {"directory": model_dir, "project_3mf": path_3mf, "result_gcode": path_gcode,
                  "chat_screenshot": screenshot, "validation": None}
        if validate:
            report = self.validate_gcode_and_3mf(path_3mf, path_gcode)
            result["validation"] = report
            for w in report["warnings"]:
                STEPluginLogger.warning(w, tag="EXPORT")
            if not report["passed"]:
                raise ArtifactValidationError(
                    "Артефакты не прошли проверку: " + "; ".join(report["errors"]),
                    details={"report": report})
        STEPluginLogger.info("Экспорт %s завершён: %s" % (model_name, model_dir), tag="EXPORT")
        return result