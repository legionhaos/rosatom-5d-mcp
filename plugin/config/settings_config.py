# -*- coding: utf-8 -*-
"""
Настройки плагина: API URL / Key / модель LLM, тайм-аут, температура, папка results/.

Хранилище: Preferences STE Slicer (ключи ste_ai_assistant/*), поэтому введённые жюри
URL и ключ сохраняются между перезапусками. Вне слайсера (тесты) — JSON-файл
~/.ste_ai_assistant/settings.json. Приоритет значений:
    сохранённое в UI  >  переменные окружения (STE_LLM_URL / STE_LLM_KEY / STE_LLM_MODEL)  >  дефолт.
"""
import json
import os
import threading
from collections import namedtuple
from typing import Any, Optional

from ..utils.exceptions import ConfigError

LLMConnectionConfig = namedtuple(
    "LLMConnectionConfig", ["api_url", "api_key", "model_name", "timeout_sec", "temperature"])

PREFIX = "ste_ai_assistant/"
DEFAULTS = {
    "api_url": "",
    "api_key": "",
    "model_name": "gpt-4o-mini",
    "timeout_sec": 120,
    "temperature": 0.1,
    "results_dir": "",
}
ENV_MAP = {"api_url": "STE_LLM_URL", "api_key": "STE_LLM_KEY", "model_name": "STE_LLM_MODEL",
           "results_dir": "STE_AI_RESULTS_DIR"}
_FALLBACK_FILE = os.path.join(os.path.expanduser("~"), ".ste_ai_assistant", "settings.json")


class PluginSettingsManager(object):
    """Единая точка доступа к настройкам плагина."""

    def __init__(self, application=None):
        # type: (Any) -> None
        self._lock = threading.RLock()
        self._app = application
        self._prefs = self._resolve_preferences(application)
        self._file_cache = None  # используется только без Preferences
        self._register_defaults()

    # ----------------------------- хранилище ------------------------------ #
    @staticmethod
    def _resolve_preferences(application):
        if application is not None and hasattr(application, "getPreferences"):
            try:
                return application.getPreferences()
            except Exception:
                pass
        try:
            from UM.Preferences import Preferences
            return Preferences.getInstance()
        except Exception:
            return None  # вне слайсера

    def _register_defaults(self):
        if self._prefs is None:
            return
        for key, value in DEFAULTS.items():
            self._prefs.addPreference(PREFIX + key, value)

    def _load_file(self):
        if self._file_cache is None:
            try:
                with open(_FALLBACK_FILE, "r", encoding="utf-8") as f:
                    self._file_cache = json.load(f)
            except (OSError, IOError, ValueError):
                self._file_cache = {}
        return self._file_cache

    def _get_raw(self, key):
        with self._lock:
            if self._prefs is not None:
                return self._prefs.getValue(PREFIX + key)
            return self._load_file().get(key, DEFAULTS[key])

    def _set_raw(self, key, value):
        with self._lock:
            if self._prefs is not None:
                self._prefs.setValue(PREFIX + key, value)
                return
            data = self._load_file()
            data[key] = value
            os.makedirs(os.path.dirname(_FALLBACK_FILE), exist_ok=True)
            with open(_FALLBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _get(self, key):
        """Сохранённое значение -> env -> дефолт."""
        value = self._get_raw(key)
        if value in (None, "") and key in ENV_MAP:
            value = os.environ.get(ENV_MAP[key], "")
        if value in (None, ""):
            value = DEFAULTS[key]
        return value

    def _flush(self):
        """Просим слайсер сохранить Preferences на диск сразу (а не при выходе)."""
        if self._app is not None and hasattr(self._app, "savePreferences"):
            try:
                self._app.savePreferences()
            except Exception:
                pass

    # ------------------------------ LLM ----------------------------------- #
    @staticmethod
    def _normalize_url(url):
        url = (url or "").strip().rstrip("/")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise ConfigError("API URL должен начинаться с http:// или https://")
        return url

    def get_llm_config(self):
        # type: () -> LLMConnectionConfig
        return LLMConnectionConfig(
            api_url=self._normalize_url(str(self._get("api_url"))),
            api_key=str(self._get("api_key")).strip(),
            model_name=str(self._get("model_name")).strip(),
            timeout_sec=int(self._get("timeout_sec")),
            temperature=float(self._get("temperature")),
        )

    def is_llm_configured(self):
        # type: () -> bool
        try:
            cfg = self.get_llm_config()
        except ConfigError:
            return False
        return bool(cfg.api_url and cfg.api_key and cfg.model_name)

    def save_llm_config(self, api_url, api_key, model_name, timeout_sec=None, temperature=None):
        # type: (str, str, str, Optional[int], Optional[float]) -> None
        url = self._normalize_url(api_url)
        if not url:
            raise ConfigError("Укажите API URL (например, https://host/v1)")
        if not (api_key or "").strip():
            raise ConfigError("Укажите API Key")
        if not (model_name or "").strip():
            raise ConfigError("Укажите название модели")
        self._set_raw("api_url", url)
        self._set_raw("api_key", api_key.strip())
        self._set_raw("model_name", model_name.strip())
        if timeout_sec is not None:
            self._set_raw("timeout_sec", int(timeout_sec))
        if temperature is not None:
            self._set_raw("temperature", float(temperature))
        self._flush()

    def get_masked_api_key(self):
        # type: () -> str
        """Для показа в UI: sk-ab…xyz."""
        key = self.get_llm_config().api_key
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "…" + key[-3:]

    # ---------------------------- results/ -------------------------------- #
    def get_results_root_dir(self):
        # type: () -> str
        """Корень для results/<model_name>/. По умолчанию ~/STE_AI_results
        (папка plugins бывает read-only). Перед сдачей копируйте содержимое в results/ архива."""
        path = str(self._get("results_dir")).strip()
        if not path:
            path = os.path.join(os.path.expanduser("~"), "STE_AI_results")
        return os.path.abspath(os.path.expanduser(path))

    def set_results_root_dir(self, path):
        # type: (str) -> None
        self._set_raw("results_dir", os.path.abspath(os.path.expanduser(path)))
        self._flush()
