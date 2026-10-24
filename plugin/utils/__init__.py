# -*- coding: utf-8 -*-
"""
Utils package for STE Slicer AI Assistant (root alias).
"""

try:
    from plugin.utils.logger import STEPluginLogger, get_logger, mask_secrets
    from plugin.utils.exceptions import (
        STEPluginError,
        ConfigError,
        LLMConnectionError,
        LLMResponseError,
        MCPToolExecutionError,
        ToolArgumentError,
        MeshLoadError,
        SceneError,
        ProfileNotFoundError,
        SlicingFailedError,
        SlicingTimeoutError,
        ArtifactExportError,
        ArtifactValidationError,
        format_exception_for_llm,
        format_exception_for_user,
    )
    from plugin.utils.artifact_exporter import ArtifactExporter
except ImportError:
    from .logger import STEPluginLogger, get_logger, mask_secrets
    from .exceptions import (
        STEPluginError,
        ConfigError,
        LLMConnectionError,
        LLMResponseError,
        MCPToolExecutionError,
        ToolArgumentError,
        MeshLoadError,
        SceneError,
        ProfileNotFoundError,
        SlicingFailedError,
        SlicingTimeoutError,
        ArtifactExportError,
        ArtifactValidationError,
        format_exception_for_llm,
        format_exception_for_user,
    )
    from .artifact_exporter import ArtifactExporter

__all__ = [
    "STEPluginLogger",
    "get_logger",
    "mask_secrets",
    "STEPluginError",
    "ConfigError",
    "LLMConnectionError",
    "LLMResponseError",
    "MCPToolExecutionError",
    "ToolArgumentError",
    "MeshLoadError",
    "SceneError",
    "ProfileNotFoundError",
    "SlicingFailedError",
    "SlicingTimeoutError",
    "ArtifactExportError",
    "ArtifactValidationError",
    "format_exception_for_llm",
    "format_exception_for_user",
    "ArtifactExporter",
]
