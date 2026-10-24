#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка и установка плагина STE AI 3D/5D Print Assistant.

Команды:
    python setup.py install_plugin [--target PATH]     копирует plugin/ в папку plugins STE Slicer
    python setup.py check_results                      проверяет results/<model>/{project.3mf,result.gcode,chat_*.png}
    python setup.py package --team-name NAME           собирает NAME.zip (plugin/ + results/)

Скрипт самодостаточен: работает как с setuptools, так и без них (zero-dependency CLI).
"""

import glob
import os
import shutil
import sys
import zipfile

try:
    from setuptools import Command, setup
except ImportError:
    class Command(object):
        description = ""
        user_options = []
        boolean_options = []
        def __init__(self, *args, **kwargs):
            pass
    setup = None

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN_SRC = os.path.join(ROOT, "plugin")
RESULTS_DIR = os.path.join(ROOT, "results")
PLUGIN_FOLDER_NAME = "STEAIAssistant"  # имя папки внутри plugins/ (= id плагина в Uranium)
EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log")


def detect_ste_slicer_plugin_dir():
    """Пытается найти папку plugins установленного STE Slicer. Возвращает путь или None.

    Порядок: переменная окружения STE_SLICER_PLUGIN_DIR -> типичные пути пользователя ->
    папки установки.
    """
    env = os.environ.get("STE_SLICER_PLUGIN_DIR")
    if env and os.path.isdir(env):
        return env

    patterns = []
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows User Data (не требует прав администратора)
        patterns += [
            os.path.join(appdata, "steslicer", "*", "plugins"),
            os.path.join(appdata, "steslicer", "plugins"),
            os.path.join(appdata, "ste_slicer", "*", "plugins"),
            os.path.join(appdata, "ste_slicer", "plugins"),
            os.path.join(appdata, "STE Slicer", "*", "plugins"),
            os.path.join(appdata, "cura", "*", "plugins"),
        ]
    for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if pf:
            patterns += [
                os.path.join(pf, "Stereotech STE Slicer*", "plugins"),
                os.path.join(pf, "STE Slicer*", "plugins"),
                os.path.join(pf, "STE Slicer*", "lib", "cura", "plugins"),
            ]
    patterns += [  # Linux / macOS
        os.path.join(home, ".local", "share", "steslicer", "*", "plugins"),
        os.path.join(home, ".local", "share", "ste_slicer", "*", "plugins"),
        os.path.join(home, ".local", "share", "ste_slicer", "plugins"),
        os.path.join(home, "Library", "Application Support", "ste_slicer", "*", "plugins"),
        os.path.join(home, ".local", "share", "cura", "3.6", "plugins"),
        "/opt/ste-slicer*/plugins",
    ]
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            if os.path.isdir(candidate):
                return candidate
    return None


def _iter_files(base_dir):
    """Итератор (абсолютный_путь, относительный_путь) без мусора (__pycache__, *.pyc, *.log)."""
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.endswith(EXCLUDE_SUFFIXES):
                continue
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, base_dir)


def _verify_results(results_dir):
    """Проверяет results/<model>/: project.3mf, result.gcode (непустые) и >=1 chat_*.png.

    Возвращает (ok: bool, problems: list[str], models: list[str]).
    """
    problems, models = [], []
    if not os.path.isdir(results_dir):
        return False, ["Папка results/ не найдена: %s" % results_dir], models
    for name in sorted(os.listdir(results_dir)):
        model_dir = os.path.join(results_dir, name)
        if name.startswith(".") or not os.path.isdir(model_dir):
            continue
        models.append(name)
        for fname in ("project.3mf", "result.gcode"):
            path = os.path.join(model_dir, fname)
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                problems.append("%s: отсутствует или пуст %s" % (name, fname))
        if not glob.glob(os.path.join(model_dir, "chat_*.png")):
            problems.append("%s: нет ни одного скриншота chat_*.png" % name)
    if not models:
        problems.append("В results/ нет ни одной папки модели")
    return not problems, problems, models


class PluginInstaller(Command):
    """python setup.py install_plugin [--target PATH]"""
    description = "Копирует plugin/ в папку plugins дистрибутива STE Slicer"
    user_options = [("target=", "t", "Путь к папке plugins STE Slicer (иначе автопоиск)")]

    def initialize_options(self):
        self.target = None

    def finalize_options(self):
        if not self.target:
            self.target = detect_ste_slicer_plugin_dir()
        if not self.target:
            sys.exit("Не удалось найти папку plugins. Укажите --target или STE_SLICER_PLUGIN_DIR.")

    def run(self):
        if not self.target:
            self.finalize_options()
        dest = os.path.join(self.target, PLUGIN_FOLDER_NAME)
        os.makedirs(dest, exist_ok=True)
        # Удаляем старые скомпилированные .qmlc кэши, чтобы Qt пересобрал новые QML-файлы
        for r, _, fs in os.walk(dest):
            for f in fs:
                if f.endswith(".qmlc"):
                    try:
                        os.remove(os.path.join(r, f))
                    except Exception:
                        pass
        for root, dirs, files in os.walk(PLUGIN_SRC):
            rel_dir = os.path.relpath(root, PLUGIN_SRC)
            target_dir = os.path.join(dest, rel_dir) if rel_dir != "." else dest
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                if f.endswith((".pyc", ".log", ".qmlc")) or f == "__pycache__":
                    continue
                src_file = os.path.join(root, f)
                dst_file = os.path.join(target_dir, f)
                try:
                    shutil.copy2(src_file, dst_file)
                except Exception as exc:
                    print("Предупреждение: не удалось скопировать %s: %s" % (dst_file, exc))
        print("Плагин установлен: %s\nПерезапустите STE Slicer." % dest)


class SubmissionPackager(Command):
    """python setup.py package --team-name NAME [--output-dir DIR] [--skip-check]"""
    description = "Собирает <team_name>.zip (plugin/ + results/) для сдачи"
    user_options = [
        ("team-name=", "n", "Название команды (имя архива)"),
        ("output-dir=", "o", "Куда положить архив (по умолчанию корень проекта)"),
        ("skip-check", None, "Не проверять results/ перед упаковкой"),
    ]
    boolean_options = ["skip-check"]

    def initialize_options(self):
        self.team_name = None
        self.output_dir = ROOT
        self.skip_check = False

    def finalize_options(self):
        if not self.team_name:
            sys.exit("Укажите --team-name NAME")

    def verify_results_folder(self, results_dir):
        ok, problems, _ = _verify_results(results_dir)
        for p in problems:
            print("  [!] " + p)
        return ok

    def build_zip(self, team_name):
        zip_path = os.path.join(self.output_dir, team_name + ".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full, rel in _iter_files(PLUGIN_SRC):
                zf.write(full, os.path.join("plugin", rel))
            for full, rel in _iter_files(RESULTS_DIR):
                if os.path.basename(full) == ".gitkeep":
                    continue
                zf.write(full, os.path.join("results", rel))
        return zip_path

    def run(self):
        if not self.skip_check and not self.verify_results_folder(RESULTS_DIR):
            sys.exit("Проверка results/ не пройдена (или используйте --skip-check).")
        print("Готово: " + self.build_zip(self.team_name))


class CheckResults(Command):
    """python setup.py check_results"""
    description = "Проверяет структуру results/"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        ok, problems, models = _verify_results(RESULTS_DIR)
        print("Модели: %s" % (", ".join(models) or "-"))
        for p in problems:
            print("  [!] " + p)
        if not ok:
            sys.exit(1)
        print("OK: структура results/ корректна.")


def main_cli():
    import argparse
    parser = argparse.ArgumentParser(description="STE AI 3D/5D Print Assistant CLI")
    subparsers = parser.add_subparsers(dest="command")

    p_install = subparsers.add_parser("install_plugin", help="Установить плагин в STE Slicer")
    p_install.add_argument("-t", "--target", help="Путь к папке plugins STE Slicer")

    p_check = subparsers.add_parser("check_results", help="Проверить структуру папки results/")

    p_pkg = subparsers.add_parser("package", help="Собрать архив сдачи <team_name>.zip")
    p_pkg.add_argument("-n", "--team-name", required=True, help="Название команды")
    p_pkg.add_argument("-o", "--output-dir", default=ROOT, help="Куда сохранить архив")
    p_pkg.add_argument("--skip-check", action="store_true", help="Не проверять results/ перед упаковкой")

    args = parser.parse_args()

    if args.command == "install_plugin":
        cmd = PluginInstaller()
        cmd.initialize_options()
        cmd.target = args.target
        cmd.run()
    elif args.command == "check_results":
        cmd = CheckResults()
        cmd.run()
    elif args.command == "package":
        cmd = SubmissionPackager()
        cmd.initialize_options()
        cmd.team_name = args.team_name
        cmd.output_dir = args.output_dir
        cmd.skip_check = args.skip_check
        cmd.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    if setup is not None:
        try:
            setup(
                name="ste-ai-print-assistant",
                version="1.0.0",
                description="ИИ-ассистент подбора параметров FDM 3D/5D-печати для STE Slicer (Cura 3.6)",
                license="LGPLv3",
                packages=[],
                py_modules=[],
                cmdclass={
                    "install_plugin": PluginInstaller,
                    "package": SubmissionPackager,
                    "check_results": CheckResults,
                },
            )
        except SystemExit:
            raise
        except Exception:
            main_cli()
    else:
        main_cli()
