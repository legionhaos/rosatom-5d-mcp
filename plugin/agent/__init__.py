# -*- coding: utf-8 -*-
"""
Agent package for 3D/5D slicer assistant.
"""

from plugin.agent.llm_client import (
    OpenAICompatibleClient,
    LLMResponse,
    ToolCallItem,
    LLMConnectionConfig,
    LLMClientError,
    LLMConnectionError,
    LLMTimeoutError,
    LLMResponseError,
    LLMRateLimitError,
    LLMParseError,
)
from plugin.agent.prompt_builder import SystemPromptBuilder
from plugin.agent.context_manager import (
    ConversationContextManager,
    encode_image_to_base64,
)
from plugin.agent.worker import AgentWorker
from plugin.agent.orchestrator import AgentOrchestrator

__all__ = [
    "OpenAICompatibleClient",
    "LLMResponse",
    "ToolCallItem",
    "LLMConnectionConfig",
    "LLMClientError",
    "LLMConnectionError",
    "LLMTimeoutError",
    "LLMResponseError",
    "LLMRateLimitError",
    "LLMParseError",
    "SystemPromptBuilder",
    "ConversationContextManager",
    "encode_image_to_base64",
    "AgentWorker",
    "AgentOrchestrator",
]
