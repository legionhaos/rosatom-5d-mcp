# -*- coding: utf-8 -*-
"""
Централизованное логирование плагина. Один вызов пишет сразу в:
  1) UM.Logger слайсера (если запущены внутри STE Slicer);
  2) файл plugin/ste_ai_assistant.log (ротация; если папка read-only — в ~/.ste_ai_assistant/);
  3) подписчиков UI (add_ui_listener) — например, AgentLogDrawer.qml;
  4) отдельный JSONL-аудит MCP-вызовов (ste_ai_mcp_audit.jsonl).
Секреты (API-ключи, Bearer-токены) маскируются автоматически. Потокобезопасно.
"""
import json
import logging
import logging.handlers
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:  # внутри STE Slicer
    from UM.Logger import Logger as _UMLogger
except Exception:  # pragma: no cover - вне слайсера
    _UMLogger = None

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FALLBACK_DIR = os.path.join(os.path.expanduser("~"), ".ste_ai_assistant")
_LOG_NAME = "ste_ai_assistant.log"
_AUDIT_NAME = "ste_ai_mcp_audit.jsonl"

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"(?i)(\"?(?:api[_-]?key|authorization|token|password)\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1***"),
]
_SECRET_KEYS = ("api_key", "apikey", "authorization", "token", "password", "secret")
_MAX_AUDIT_CHARS = 4000


def mask_secrets(text):
    # type: (str) -> str
    """Заменяет ключи/токены в строке на ***."""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _sanitize(obj):
    """Рекурсивно маскирует значения секретных ключей в dict/list."""
    if isinstance(obj, dict):
        return {k: ("***" if str(k).lower() in _SECRET_KEYS else _sanitize(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, str):
        return mask_secrets(obj)
    return obj


class STEPluginLogger(object):
    """Статический логгер плагина: STEPluginLogger.info("...")."""

    _lock = threading.RLock()
    _file_logger = None   # type: Optional[logging.Logger]
    _log_dir = None       # type: Optional[str]
    _ui_listeners = []    # type: List[Callable[[str, str, str], None]]

    # ----------------------------- настройка ------------------------------ #
    @classmethod
    def set_log_dir(cls, path):
        # type: (str) -> None
        """Переопределить папку логов (например, results/ или временную)."""
        with cls._lock:
            cls._log_dir = path
            cls._file_logger = None  # пересоздастся при следующей записи

    @classmethod
    def get_log_dir(cls):
        # type: () -> str
        cls._ensure_file_logger()
        return cls._log_dir or _FALLBACK_DIR

    @classmethod
    def _ensure_file_logger(cls):
        with cls._lock:
            if cls._file_logger is not None:
                return cls._file_logger
            candidates = [cls._log_dir] if cls._log_dir else [_PLUGIN_DIR, _FALLBACK_DIR]
            logger = logging.getLogger("ste_ai_assistant")
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
            for h in list(logger.handlers):
                logger.removeHandler(h)
                h.close()
            for directory in candidates:
                try:
                    os.makedirs(directory, exist_ok=True)
                    handler = logging.handlers.RotatingFileHandler(
                        os.path.join(directory, _LOG_NAME), maxBytes=2 * 1024 * 1024,
                        backupCount=3, encoding="utf-8")
                    handler.setFormatter(logging.Formatter(
                        "%(asctime)s [%(levelname)s] %(name)s %(message)s", "%Y-%m-%d %H:%M:%S"))
                    logger.addHandler(handler)
                    cls._log_dir = directory
                    break
                except (OSError, IOError) as exc:
                    try:
                        print("STE AI logger cannot write to %s: %s" % (directory, exc))
                    except Exception:
                        pass
                    continue
            if not logger.handlers:
                try:
                    handler = logging.StreamHandler()
                    handler.setFormatter(logging.Formatter(
                        "%(asctime)s [%(levelname)s] %(name)s %(message)s", "%Y-%m-%d %H:%M:%S"))
                    logger.addHandler(handler)
                except Exception:
                    pass
            cls._file_logger = logger
            return logger

    # ------------------------------ UI-хуки ------------------------------- #
    @classmethod
    def add_ui_listener(cls, callback):
        # type: (Callable[[str, str, str], None]) -> None
        """callback(level, tag, message). ВНИМАНИЕ: вызывается из любого потока —
        в UI пробрасывайте через pyqtSignal."""
        with cls._lock:
            if callback not in cls._ui_listeners:
                cls._ui_listeners.append(callback)

    @classmethod
    def remove_ui_listener(cls, callback):
        with cls._lock:
            if callback in cls._ui_listeners:
                cls._ui_listeners.remove(callback)

    # ------------------------------ ядро ---------------------------------- #
    @classmethod
    def _emit(cls, level, tag, msg, exc_info=False):
        msg = mask_secrets(str(msg))
        line = "[%s] %s" % (tag, msg)
        traceback_text = ""
        if exc_info:
            import traceback
            traceback_text = mask_secrets(traceback.format_exc())
            if traceback_text.strip() == "NoneType: None":
                traceback_text = ""
            elif traceback_text:
                line += "\n" + traceback_text.rstrip()
        # 1) UM.Logger
        if _UMLogger is not None:
            try:
                if exc_info and level == "e":
                    _UMLogger.logException("e", line)
                else:
                    _UMLogger.log(level, line)
            except Exception:
                pass
        # 2) файл
        try:
            fl = cls._ensure_file_logger()
            py_level = {"d": logging.DEBUG, "i": logging.INFO, "w": logging.WARNING,
                        "e": logging.ERROR}.get(level, logging.INFO)
            fl.log(py_level, line)
        except Exception as exc:
            try:
                print("STE AI logger write failed: %s" % exc)
            except Exception:
                pass
        # 3) UI
        with cls._lock:
            listeners = list(cls._ui_listeners)
        for cb in listeners:
            try:
                cb(level, tag, msg)
            except Exception:
                pass

    @classmethod
    def debug(cls, msg, tag="STE_AI"):
        cls._emit("d", tag, msg)

    @classmethod
    def info(cls, msg, tag="STE_AI"):
        cls._emit("i", tag, msg)

    @classmethod
    def warning(cls, msg, tag="STE_AI"):
        cls._emit("w", tag, msg)

    @classmethod
    def error(cls, msg, exc_info=True, tag="STE_AI"):
        # type: (str, bool, str) -> None
        """exc_info=True — приложить трассировку текущего исключения."""
        cls._emit("e", tag, msg, exc_info=exc_info)

    @classmethod
    def exception(cls, msg, tag="STE_AI"):
        # type: (str, str) -> None
        """Записывает сообщение и traceback текущего исключения."""
        cls._emit("e", tag, msg, exc_info=True)

    # ------------------------------ аудит MCP ----------------------------- #
    @classmethod
    def log_mcp_call(cls, tool_name, args, result, duration_ms):
        # type: (str, Dict[str, Any], Dict[str, Any], int) -> None
        """Структурированная запись вызова MCP-инструмента (JSONL + обычный лог)."""
        status = result.get("status", "OK") if isinstance(result, dict) else "OK"
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tool": tool_name,
            "status": status,
            "duration_ms": int(duration_ms),
            "args": _sanitize(args),
            "result": _sanitize(result),
        }
        try:
            text = json.dumps(record, ensure_ascii=False, default=str)
            if len(text) > _MAX_AUDIT_CHARS:
                record["result"] = "<truncated: %d chars>" % len(text)
                text = json.dumps(record, ensure_ascii=False, default=str)
            with cls._lock:
                path = os.path.join(cls.get_log_dir(), _AUDIT_NAME)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
        except Exception as exc:
            cls.exception("MCP audit write failed: %s" % exc, tag="MCP_LOG")
        cls.info("MCP %s -> %s (%d ms)" % (tool_name, status, duration_ms), tag="MCP")
        if isinstance(result, dict) and str(status).lower() in ("error", "failed"):
            error_text = result.get("error") or result.get("message") or result
            cls.error("MCP %s failed: %s" % (tool_name, json.dumps(_sanitize(error_text), ensure_ascii=False, default=str)),
                      exc_info=False, tag="MCP")
            if result.get("traceback"):
                cls.error("MCP %s traceback:\n%s" % (tool_name, result["traceback"]),
                          exc_info=False, tag="MCP")


def get_logger(name=None):
    """Возвращает стандартный logging.Logger с автоинициализацией STEPluginLogger."""
    main_logger = STEPluginLogger._ensure_file_logger()
    logger_name = name or "ste_ai_assistant"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    if main_logger and not logger.handlers:
        for h in getattr(main_logger, "handlers", []):
            if h not in logger.handlers:
                logger.addHandler(h)
    return logger


__all__ = ["STEPluginLogger", "mask_secrets", "get_logger"]
