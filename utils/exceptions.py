# -*- coding: utf-8 -*-
"""
Common project exceptions.
"""

from plugin.agent.llm_client import (
    LLMClientError,
    LLMConnectionError,
    LLMTimeoutError,
    LLMResponseError,
    LLMRateLimitError,
    LLMParseError,
)

__all__ = [
    "LLMClientError",
    "LLMConnectionError",
    "LLMTimeoutError",
    "LLMResponseError",
    "LLMRateLimitError",
    "LLMParseError",
]
