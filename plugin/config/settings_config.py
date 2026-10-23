# -*- coding: utf-8 -*-
"""
Settings and configuration models for STE Slicer plugin.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

from plugin.agent.llm_client import LLMConnectionConfig

logger = logging.getLogger("PluginSettingsManager")


class PluginSettingsManager(object):
    """
    Manages persistent configuration for the STE Slicer plugin,
    including LLM connection credentials, endpoint URLs, and slicing defaults.
    """

    DEFAULT_CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "plugin_settings.json"
    )

    def __init__(self, config_path=None, llm_config=None):
        # type: (Optional[str], Optional[LLMConnectionConfig]) -> None
        self.config_path = str(config_path or self.DEFAULT_CONFIG_PATH)
        self.settings = {}  # type: Dict[str, Any]

        if llm_config is not None:
            self.llm_config = llm_config
        else:
            self.llm_config = LLMConnectionConfig()

        self._client = None  # type: Optional[Any]
        self.load()

    def get_llm_config(self):
        # type: () -> LLMConnectionConfig
        """Returns the active LLM connection configuration."""
        return self.llm_config

    def get_llm_client(self):
        # type: () -> Any
        """Returns or lazily creates an OpenAICompatibleClient instance."""
        if self._client is None:
            from plugin.agent.llm_client import OpenAICompatibleClient
            self._client = OpenAICompatibleClient(self.llm_config)
        return self._client

    def set_llm_config(self, config):
        # type: (LLMConnectionConfig) -> None
        """Updates the LLM connection configuration and resets client."""
        self.llm_config = config
        self._client = None
        self.settings["base_url"] = config.base_url
        self.settings["api_key"] = config.api_key
        self.settings["model"] = config.model
        self.settings["timeout"] = config.timeout
        self.settings["verify_ssl"] = config.verify_ssl

    def get(self, key, default=None):
        # type: (str, Any) -> Any
        """Gets a configuration parameter by key."""
        return self.settings.get(key, default)

    def set(self, key, value):
        # type: (str, Any) -> None
        """Sets a configuration parameter by key."""
        self.settings[key] = value

    def load(self, path=None):
        # type: (Optional[str]) -> bool
        """Loads configuration from JSON file."""
        target_path = path or self.config_path
        if os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.settings = data
                    self.llm_config = LLMConnectionConfig(
                        base_url=data.get("base_url", self.llm_config.base_url),
                        api_key=data.get("api_key", self.llm_config.api_key),
                        model=data.get("model", self.llm_config.model),
                        timeout=data.get("timeout", self.llm_config.timeout),
                        verify_ssl=data.get("verify_ssl", self.llm_config.verify_ssl),
                        max_retries=data.get("max_retries", self.llm_config.max_retries),
                        retry_delay=data.get("retry_delay", self.llm_config.retry_delay),
                    )
                    self._client = None
                    return True
            except Exception as e:
                logger.warning("Failed to load settings from '%s': %s", target_path, e)
        return False

    def save(self, path=None):
        # type: (Optional[str]) -> bool
        """Saves configuration to JSON file."""
        target_path = path or self.config_path
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            self.settings.update(self.llm_config.to_dict())
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error("Failed to save settings to '%s': %s", target_path, e)
            return False


__all__ = ["LLMConnectionConfig", "PluginSettingsManager"]
