# -*- coding: utf-8 -*-
"""
Иерархия исключений плагина и конвертеры ошибок.

Идея: любая ошибка внутри MCP-инструмента превращается в структурированный JSON
(format_exception_for_llm), который возвращается модели как результат tool-вызова,
чтобы агент мог САМ исправиться (повернуть/уменьшить модель, сменить параметр, повторить).
Для пользователя есть отдельный человекочитаемый вариант (format_exception_for_user).
Совместимо с Python 3.5.
"""
from typing import Any, Dict, Optional


class STEPluginError(Exception):
    """Базовое исключение плагина."""
    error_type = "PLUGIN_ERROR"
    recoverable = False
    default_hint = "Сообщите пользователю об ошибке и остановите выполнение."

    def __init__(self, message="", hint=None, details=None):
        # type: (str, Optional[str], Optional[Dict[str, Any]]) -> None
        super(STEPluginError, self).__init__(message)
        self.message = message or self.__class__.__name__
        self.hint = hint or self.default_hint
        self.details = details or {}


class ConfigError(STEPluginError):
    """Неверные/отсутствующие настройки плагина (URL, ключ, пути)."""
    error_type = "CONFIG_ERROR"
    default_hint = "Откройте «Настройки LLM API» и проверьте URL, ключ и название модели."


class LLMConnectionError(STEPluginError):
    """Нет связи с LLM: неверный URL, невалидный ключ, тайм-аут, 4xx/5xx."""
    error_type = "LLM_CONNECTION_ERROR"
    default_hint = "Проверьте API URL / API Key и доступность сервера LLM."

    def __init__(self, message="", status_code=None, **kwargs):
        super(LLMConnectionError, self).__init__(message, **kwargs)
        self.status_code = status_code
        if status_code is not None:
            self.details["status_code"] = status_code


class LLMResponseError(STEPluginError):
    """LLM вернула непарсируемый/некорректный ответ (битый JSON в tool_calls и т.п.)."""
    error_type = "LLM_RESPONSE_ERROR"
    recoverable = True
    default_hint = "Повторите запрос; при повторе ошибки упростите формулировку."


class MCPToolExecutionError(STEPluginError):
    """Базовая ошибка выполнения MCP-инструмента."""
    error_type = "TOOL_EXECUTION_ERROR"
    recoverable = True
    default_hint = "Проверьте аргументы вызова и повторите попытку."

    def __init__(self, message="", tool_name=None, **kwargs):
        super(MCPToolExecutionError, self).__init__(message, **kwargs)
        self.tool_name = tool_name
        if tool_name:
            self.details["tool_name"] = tool_name


class ToolArgumentError(MCPToolExecutionError):
    """Аргументы инструмента не прошли валидацию по JSON Schema."""
    error_type = "INVALID_ARGUMENTS"
    default_hint = "Исправьте аргументы согласно JSON Schema инструмента и вызовите его снова."


class MeshLoadError(STEPluginError):
    """Файл STL/3MF/OBJ повреждён, пуст или не найден."""
    error_type = "MESH_LOAD_ERROR"
    recoverable = False
    default_hint = "Попросите пользователя проверить файл и загрузить модель заново."


class SceneError(MCPToolExecutionError):
    """Ошибка работы со сценой (узел не найден, не удалось повернуть/расставить)."""
    error_type = "SCENE_ERROR"
    default_hint = "Вызовите analyze_mesh_geometry, чтобы получить актуальный node_id."


class ProfileNotFoundError(MCPToolExecutionError):
    """Запрошенный материал/профиль/режим 3D-5D отсутствует в дистрибутиве."""
    error_type = "PROFILE_NOT_FOUND"
    default_hint = ("Запросите список доступных конфигураций (list_available_configurations) "
                    "и выберите из него.")


class SlicingFailedError(STEPluginError):
    """Сбой слайсинга в CuraEngine."""
    error_type = "SLICING_FAILED"
    recoverable = True
    default_hint = ("Проверьте, что модель помещается на стол и лежит на платформе; "
                    "при необходимости уменьшите масштаб, смените ориентацию или параметры.")


class SlicingTimeoutError(SlicingFailedError):
    """CuraEngine не завершил нарезку за отведённое время."""
    error_type = "SLICING_TIMEOUT"
    default_hint = "Упростите настройки (больше высота слоя, меньше заполнение) или увеличьте timeout_sec."


class ArtifactExportError(STEPluginError):
    """Не удалось сохранить project.3mf / result.gcode / скриншот."""
    error_type = "ARTIFACT_EXPORT_ERROR"
    recoverable = True
    default_hint = "Проверьте права на запись в папку results/ и повторите экспорт."


class ArtifactValidationError(STEPluginError):
    """Артефакты сохранены, но не прошли валидацию (битый 3MF, пустой G-code)."""
    error_type = "ARTIFACT_VALIDATION_ERROR"
    recoverable = True
    default_hint = "Перезапустите слайсинг и повторите экспорт."


# --------------------------------------------------------------------------- #
# Конвертеры
# --------------------------------------------------------------------------- #

def _classify_builtin(exc):
    """Подбирает (error_type, recoverable, hint) для не-плагинных исключений."""
    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND", False, "Файл не найден: проверьте путь, который передал пользователь."
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED", False, "Нет прав доступа к файлу/папке."
    if isinstance(exc, TimeoutError):
        return "TIMEOUT", True, "Операция не уложилась в тайм-аут; повторите или упростите задачу."
    if isinstance(exc, (KeyError, ValueError, TypeError)):
        return "INVALID_ARGUMENTS", True, "Проверьте названия и типы параметров (в т.ч. ключей настроек Cura)."
    return "UNEXPECTED_ERROR", False, "Непредвиденная ошибка: сообщите о ней пользователю."


def format_exception_for_llm(exc):
    # type: (BaseException) -> Dict[str, Any]
    """Исключение -> JSON для role:"tool": {"status":"ERROR","error_type",...,"recoverable_hint"}."""
    if isinstance(exc, STEPluginError):
        payload = {
            "status": "ERROR",
            "error_type": exc.error_type,
            "message": exc.message,
            "recoverable": exc.recoverable,
            "recoverable_hint": exc.hint,
        }
        if exc.details:
            payload["details"] = exc.details
        return payload
    error_type, recoverable, hint = _classify_builtin(exc)
    return {
        "status": "ERROR",
        "error_type": error_type,
        "message": "%s: %s" % (exc.__class__.__name__, exc),
        "recoverable": recoverable,
        "recoverable_hint": hint,
    }


def format_exception_for_user(exc):
    # type: (BaseException) -> str
    """Короткое сообщение для чата (без трассировки)."""
    if isinstance(exc, STEPluginError):
        return "%s\n💡 %s" % (exc.message, exc.hint)
    _, _, hint = _classify_builtin(exc)
    return "Произошла ошибка: %s\n💡 %s" % (exc, hint)