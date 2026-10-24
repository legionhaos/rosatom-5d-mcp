# -*- coding: utf-8 -*-
"""
OpenAI-compatible LLM client without external dependencies.

This module provides a lightweight, resilient client for interacting with any
OpenAI-compatible Chat Completions API using only the Python standard library
(urllib.request, json, ssl, etc.).

Features:
- Full compatibility with OpenAI Chat Completions API (tools and tool_calls).
- Automatic retry logic with exponential backoff on HTTP 429, 502, 503, 504.
- Fallback parser for extracting tool/function calls embedded in text messages
  (markdown JSON code blocks, XML-style tags, raw JSON).
- Connection diagnostics method for UI settings validation (/models and /chat/completions).
- Python 3.5+ compatibility (no external libraries, standard library only).
"""

import ast
import json
import logging
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import NamedTuple, Optional, List, Dict, Any, Tuple, Union

# Try to import project logger if available, otherwise use standard logging
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger("OpenAICompatibleClient")


# =====================================================================
# Data Structures
# =====================================================================

ToolCallItem = NamedTuple("ToolCallItem", [
    ("id", str),
    ("name", str),
    ("arguments_json", str)
])

LLMResponse = NamedTuple("LLMResponse", [
    ("content", Optional[str]),
    ("tool_calls", List[ToolCallItem]),
    ("finish_reason", str),
    ("usage", Dict[str, int])
])


# =====================================================================
# Exceptions
# =====================================================================

class LLMClientError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLMConnectionError(LLMClientError):
    """Raised when a network connection to the LLM API fails."""
    pass


class LLMTimeoutError(LLMClientError):
    """Raised when an LLM API request times out."""
    pass


class LLMResponseError(LLMClientError):
    """Raised when the LLM API returns an HTTP error status code."""
    def __init__(self, message, status_code=None, response_body=None):
        super(LLMResponseError, self).__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class LLMRateLimitError(LLMResponseError):
    """Raised when the rate limit (HTTP 429) is exceeded after all retries."""
    pass


class LLMParseError(LLMClientError):
    """Raised when an API response cannot be decoded as valid JSON."""
    pass


# =====================================================================
# Connection Configuration
# =====================================================================

class LLMConnectionConfig(object):
    """
    Configuration parameters for connecting to an OpenAI-compatible LLM service.

    Attributes:
        base_url: Base URL of the API (e.g. 'https://api.openai.com/v1').
        api_key: Secret API key for Authorization header.
        model: Target model identifier (e.g. 'gpt-4o', 'llama-3', 'qwen-2.5').
        timeout: Timeout in seconds for HTTP requests.
        verify_ssl: Whether to verify SSL/TLS certificates.
        max_retries: Number of automatic retry attempts on retryable HTTP errors.
        retry_delay: Initial delay in seconds before exponential backoff retries.
    """

    def __init__(self,
                 base_url="https://api.openai.com/v1",
                 api_key="",
                 model="gpt-3.5-turbo",
                 timeout=60.0,
                 verify_ssl=True,
                 max_retries=3,
                 retry_delay=1.0):
        # type: (str, str, str, float, bool, int, float) -> None
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = float(timeout) if timeout is not None else 60.0
        self.verify_ssl = bool(verify_ssl)
        self.max_retries = int(max_retries) if max_retries is not None else 3
        self.retry_delay = float(retry_delay) if retry_delay is not None else 1.0

    def to_dict(self):
        # type: () -> Dict[str, Any]
        return {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "timeout": self.timeout,
            "verify_ssl": self.verify_ssl,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay
        }

    def __repr__(self):
        masked_key = (self.api_key[:4] + "..." + self.api_key[-4:]) if len(self.api_key) > 8 else "***"
        return (
            "LLMConnectionConfig(base_url='{0}', model='{1}', api_key='{2}', "
            "timeout={3}, verify_ssl={4}, max_retries={5})"
        ).format(
            self.base_url, self.model, masked_key, self.timeout, self.verify_ssl, self.max_retries
        )


# =====================================================================
# Fallback Tool Call Parser
# =====================================================================

class FallbackToolCallParser(object):
    """
    Extracts function/tool calls from unstructured text messages.

    Used when an LLM model does not support native OpenAI tool_calls or
    returns function calls directly in the text body (e.g. markdown code blocks,
    XML tags, or JSON objects).
    """

    TAG_PATTERNS = [
        re.compile(r'<tool_call>([\s\S]*?)</tool_call>', re.IGNORECASE),
        re.compile(r'<function_call>([\s\S]*?)</function_call>', re.IGNORECASE),
        re.compile(r'<tool>([\s\S]*?)</tool>', re.IGNORECASE),
        re.compile(r'\[TOOL_CALLS?\]([\s\S]*?)\[/TOOL_CALLS?\]', re.IGNORECASE),
    ]

    FUNCTION_TAG_PATTERN = re.compile(
        r'<function=([a-zA-Z0-9_\-\.]+)>([\s\S]*?)</function>',
        re.IGNORECASE
    )

    MARKDOWN_CODE_PATTERN = re.compile(
        r'```(?:json)?\s*([\s\S]*?)\s*```',
        re.IGNORECASE
    )

    def parse(self, content, expected_tools=None):
        # type: (Optional[str], Optional[List[Dict[str, Any]]]) -> Tuple[List[ToolCallItem], Optional[str]]
        """
        Parses text content to identify and extract embedded tool calls.

        Args:
            content: Raw assistant message content string.
            expected_tools: Optional list of tool definitions supplied in the request.

        Returns:
            Tuple of (list_of_tool_calls, cleaned_content).
            cleaned_content is None if the entire message consisted of tool calls.
        """
        if not content or not content.strip():
            return [], content

        expected_names = set()
        if expected_tools:
            for t in expected_tools:
                if isinstance(t, dict):
                    fn = t.get("function")
                    if isinstance(fn, dict) and "name" in fn:
                        expected_names.add(fn["name"])
                    elif "name" in t:
                        expected_names.add(t["name"])

        tool_calls = []  # type: List[ToolCallItem]
        spans_to_remove = []  # type: List[Tuple[int, int]]

        # 1. Check Hermes / Nous format: <function=tool_name>arguments</function>
        for match in self.FUNCTION_TAG_PATTERN.finditer(content):
            fn_name = match.group(1).strip()
            raw_args = match.group(2).strip()
            args_json = self._normalize_arguments_json(raw_args)
            call_id = "call_" + uuid.uuid4().hex[:8]
            tool_calls.append(ToolCallItem(id=call_id, name=fn_name, arguments_json=args_json))
            spans_to_remove.append(match.span())

        # 2. Check XML / tag-based wrappers (<tool_call>...</tool_call>)
        for pattern in self.TAG_PATTERNS:
            for match in pattern.finditer(content):
                tag_body = match.group(1).strip()
                extracted = self._try_parse_json_payload(tag_body, expected_names)
                if extracted:
                    tool_calls.extend(extracted)
                    spans_to_remove.append(match.span())

        # 3. Check Markdown code blocks (```json ... ```)
        for match in self.MARKDOWN_CODE_PATTERN.finditer(content):
            start, end = match.span()
            if any(s <= start and end <= e for s, e in spans_to_remove):
                continue
            block_body = match.group(1).strip()
            extracted = self._try_parse_json_payload(block_body, expected_names)
            if extracted:
                tool_calls.extend(extracted)
                spans_to_remove.append((start, end))

        # 4. Check if the entire content is a raw JSON tool call
        if not tool_calls:
            extracted = self._try_parse_json_payload(content.strip(), expected_names)
            if extracted:
                tool_calls.extend(extracted)
                return tool_calls, None

        # 5. Check for embedded balanced JSON objects in free-form text
        if not tool_calls:
            embedded = self._find_embedded_json(content, expected_names)
            if embedded:
                for item, (start, end) in embedded:
                    tool_calls.append(item)
                    spans_to_remove.append((start, end))

        if tool_calls and spans_to_remove:
            spans_to_remove.sort(key=lambda s: s[0], reverse=True)
            text_chars = list(content)
            for s, e in spans_to_remove:
                del text_chars[s:e]
            remaining = "".join(text_chars).strip()
            cleaned_content = remaining if remaining else None
        else:
            cleaned_content = content

        return tool_calls, cleaned_content

    def _normalize_arguments_json(self, raw_args):
        # type: (Any) -> str
        """Normalizes any argument representation into a valid JSON string."""
        if raw_args is None:
            return "{}"
        if isinstance(raw_args, (dict, list)):
            return json.dumps(raw_args, ensure_ascii=False)
        if isinstance(raw_args, str):
            trimmed = raw_args.strip()
            if not trimmed:
                return "{}"
            try:
                parsed = json.loads(trimmed)
                return json.dumps(parsed, ensure_ascii=False)
            except Exception:
                try:
                    # Tolerant fallback for Python literal dicts or single quotes
                    parsed = ast.literal_eval(trimmed)
                    return json.dumps(parsed, ensure_ascii=False)
                except Exception:
                    return json.dumps({"input": trimmed}, ensure_ascii=False)
        return json.dumps(raw_args, ensure_ascii=False)

    def _try_parse_json_payload(self, text, expected_names):
        # type: (str, set) -> List[ToolCallItem]
        """Attempts to parse JSON text into one or more ToolCallItem objects."""
        if not text:
            return []
        data = None
        try:
            data = json.loads(text)
        except Exception:
            try:
                # Lenient parser for Python-style dicts / single quotes
                data = ast.literal_eval(text)
            except Exception:
                return []

        results = []
        if isinstance(data, list):
            for item in data:
                tc = self._dict_to_tool_call(item, expected_names)
                if tc:
                    results.append(tc)
        elif isinstance(data, dict):
            if "tool_calls" in data and isinstance(data["tool_calls"], list):
                for item in data["tool_calls"]:
                    tc = self._dict_to_tool_call(item, expected_names)
                    if tc:
                        results.append(tc)
            else:
                tc = self._dict_to_tool_call(data, expected_names)
                if tc:
                    results.append(tc)
        return results

    def _dict_to_tool_call(self, d, expected_names):
        # type: (Any, set) -> Optional[ToolCallItem]
        """Extracts tool name and arguments from a parsed dictionary."""
        if not isinstance(d, dict):
            return None

        # Standard OpenAI function call format: {"type": "function", "function": {"name": ..., "arguments": ...}}
        if d.get("type") == "function" and isinstance(d.get("function"), dict):
            fn = d["function"]
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            call_id = str(d.get("id") or ("call_" + uuid.uuid4().hex[:8]))
            return ToolCallItem(id=call_id, name=name, arguments_json=self._normalize_arguments_json(raw_args))

        # Format: {"function": {"name": ..., "arguments": ...}}
        if isinstance(d.get("function"), dict):
            fn = d["function"]
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            call_id = str(d.get("id") or ("call_" + uuid.uuid4().hex[:8]))
            return ToolCallItem(id=call_id, name=name, arguments_json=self._normalize_arguments_json(raw_args))

        # Format: {"name": ..., "arguments": ...} / {"tool": ..., "parameters": ...} / {"action": ..., "action_input": ...}
        name = None
        for key in ("name", "tool", "action", "function", "tool_name"):
            if key in d and isinstance(d[key], str):
                name = d[key]
                break

        if not name:
            return None

        args = None
        has_args_key = False
        for key in ("arguments", "parameters", "args", "action_input", "tool_args", "input", "params"):
            if key in d:
                args = d[key]
                has_args_key = True
                break

        # If no explicit arguments key, check whether this is clearly a tool invocation
        if not has_args_key:
            if expected_names and name in expected_names:
                args = {}
            elif any(k in d for k in ("tool", "action", "function")):
                args = {}
            else:
                return None

        call_id = str(d.get("id")) if d.get("id") else ("call_" + uuid.uuid4().hex[:8])
        args_json = self._normalize_arguments_json(args)
        return ToolCallItem(id=call_id, name=name, arguments_json=args_json)

    def _find_embedded_json(self, text, expected_names):
        # type: (str, set) -> List[Tuple[ToolCallItem, Tuple[int, int]]]
        """Finds top-level balanced JSON objects within free-form text."""
        candidates = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] in '{[':
                start_char = text[i]
                end_char = '}' if start_char == '{' else ']'
                depth = 0
                in_str = False
                escape = False
                start_idx = i
                for j in range(i, n):
                    c = text[j]
                    if escape:
                        escape = False
                        continue
                    if c == '\\':
                        escape = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if not in_str:
                        if c == start_char:
                            depth += 1
                        elif c == end_char:
                            depth -= 1
                            if depth == 0:
                                substr = text[start_idx:j + 1]
                                parsed_items = self._try_parse_json_payload(substr, expected_names)
                                if parsed_items:
                                    for item in parsed_items:
                                        candidates.append((item, (start_idx, j + 1)))
                                i = j
                                break
            i += 1
        return candidates


# =====================================================================
# Main Client Class
# =====================================================================

class OpenAICompatibleClient(object):
    """
    Lightweight client for OpenAI-compatible LLM Chat Completions API.

    Uses only Python standard library modules (urllib, json, ssl).
    Supports tools/tool_calls, automatic retries with exponential backoff on
    HTTP 429, 502, 503, 504, text tool call fallback parsing, and connection testing.
    """

    RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

    def __init__(self, config):
        # type: ("LLMConnectionConfig") -> None
        """
        Initializes the client with connection parameters.

        Args:
            config: An instance of LLMConnectionConfig or duck-typed object / dict
                    with base_url, api_key, model, timeout, verify_ssl, max_retries, retry_delay.
        """
        self.config = config

        if isinstance(config, dict):
            raw_url = config.get("base_url") or config.get("api_url") or ""
            self.api_key = str(config.get("api_key") or "").strip()
            self.model = str(config.get("model") or config.get("model_name") or "").strip()
            self.timeout = float(config.get("timeout") or config.get("timeout_sec") or 60.0)
            self.verify_ssl = bool(config.get("verify_ssl", True))
            self.max_retries = int(config.get("max_retries", 3))
            self.retry_delay = float(config.get("retry_delay", 1.0))
        else:
            raw_url = getattr(config, "base_url", None) or getattr(config, "api_url", "")
            self.api_key = str(getattr(config, "api_key", "")).strip()
            self.model = str(getattr(config, "model", None) or getattr(config, "model_name", "")).strip()
            self.timeout = float(getattr(config, "timeout", None) or getattr(config, "timeout_sec", 60.0))
            self.verify_ssl = bool(getattr(config, "verify_ssl", True))
            self.max_retries = int(getattr(config, "max_retries", 3))
            self.retry_delay = float(getattr(config, "retry_delay", 1.0))

        # Normalize URL: strip trailing slash and redundant suffixes if user provided full endpoint
        clean_url = str(raw_url or "").strip().rstrip("/")
        if clean_url.endswith("/chat/completions"):
            clean_url = clean_url[:-len("/chat/completions")].rstrip("/")
        elif clean_url.endswith("/models"):
            clean_url = clean_url[:-len("/models")].rstrip("/")

        self.api_url = clean_url
        self.base_url = clean_url

        # SSL Context setup
        if self.verify_ssl:
            self._ssl_context = ssl.create_default_context()
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ssl_context = ctx

        self.fallback_parser = FallbackToolCallParser()
        self.logger = logger

    def chat_completion(self,
                        messages,  # type: List[Dict[str, Any]]
                        tools=None,  # type: Optional[List[Dict[str, Any]]]
                        tool_choice="auto",  # type: Union[str, Dict[str, Any]]
                        model=None,  # type: Optional[str]
                        temperature=None,  # type: Optional[float]
                        max_tokens=None,  # type: Optional[int]
                        **kwargs  # type: Any
                        ):
        # type: (...) -> LLMResponse
        """
        Executes an HTTP POST request to {api_url}/chat/completions.

        Supports automatic retries on HTTP 429 / 502 / 503 / 504 and parses the response.

        Args:
            messages: List of OpenAI-format message dictionaries.
            tools: Optional list of tools formatted according to OpenAI specification.
            tool_choice: Mode for tool selection ("auto", "none", "required", or specific function).
            model: Optional override for the target model.
            temperature: Optional sampling temperature.
            max_tokens: Optional maximum completion tokens.
            **kwargs: Extra parameters passed directly into the JSON request payload.

        Returns:
            LLMResponse NamedTuple containing content, tool_calls, finish_reason, and usage.
        """
        target_model = model or self.model or "default-model"
        payload = {
            "model": target_model,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        if temperature is not None:
            payload["temperature"] = temperature

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v

        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = "{0}/chat/completions".format(self.api_url)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "STE-5D-Slicer-LLMClient/1.0",
            "Content-Length": str(len(payload_bytes)),
        }
        if self.api_key:
            if self.api_key.lower().startswith("bearer "):
                headers["Authorization"] = self.api_key
            else:
                headers["Authorization"] = "Bearer " + self.api_key

        last_error = None
        max_attempts = max(1, self.max_retries + 1)

        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
                ctx = self._ssl_context if url.lower().startswith("https") else None
                resp = urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
                resp_bytes = resp.read()
                raw_response = json.loads(resp_bytes.decode("utf-8"))
                return self._parse_chat_response(raw_response, expected_tools=tools)

            except urllib.error.HTTPError as e:
                last_error = e
                status_code = getattr(e, "code", None)
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if status_code in self.RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    retry_after = self._get_retry_after(e.headers)
                    if retry_after is not None and retry_after > 0:
                        sleep_time = min(retry_after, 60.0)
                    else:
                        sleep_time = self.retry_delay * (2 ** attempt)

                    self.logger.warning(
                        "HTTP %s on %s. Retrying in %.2fs (attempt %d/%d)...",
                        status_code, url, sleep_time, attempt + 1, self.max_retries
                    )
                    time.sleep(sleep_time)
                    continue

                err_msg = self._extract_error_message(err_body) or str(e)
                if status_code == 429:
                    raise LLMRateLimitError(
                        "Rate limit exceeded (HTTP 429): {0}".format(err_msg),
                        status_code=429,
                        response_body=err_body
                    )
                raise LLMResponseError(
                    "HTTP {0} error: {1}".format(status_code, err_msg),
                    status_code=status_code,
                    response_body=err_body
                )

            except urllib.error.URLError as e:
                last_error = e
                reason = getattr(e, "reason", None)
                is_timeout = isinstance(reason, socket.timeout) or "timed out" in str(reason).lower()

                if attempt < self.max_retries:
                    sleep_time = self.retry_delay * (2 ** attempt)
                    self.logger.warning(
                        "Network error (%s) on %s. Retrying in %.2fs (attempt %d/%d)...",
                        reason, url, sleep_time, attempt + 1, self.max_retries
                    )
                    time.sleep(sleep_time)
                    continue

                if is_timeout:
                    raise LLMTimeoutError("Request to {0} timed out after {1}s: {2}".format(url, self.timeout, reason))
                raise LLMConnectionError("Connection to {0} failed: {1}".format(url, reason))

            except (ValueError, TypeError) as e:
                raise LLMParseError("Failed to parse JSON response from LLM: {0}".format(str(e)))

        if isinstance(last_error, Exception):
            raise last_error
        raise LLMClientError("Chat completion request failed after {0} attempts.".format(max_attempts))

    def test_connection(self):
        # type: () -> Tuple[bool, str]
        """
        Checks the availability of the LLM endpoint for SettingsDialog.qml.

        First attempts to query GET {api_url}/models. If that endpoint returns
        404, 405, or 501, it falls back to a minimal POST {api_url}/chat/completions.

        Returns:
            Tuple[bool, str]: (success_flag, user_facing_status_message).
        """
        if not self.api_url:
            return False, "Не указан базовый URL API (Base URL)."

        test_timeout = min(self.timeout, 10.0)

        # 1. Try GET /models
        models_url = "{0}/models".format(self.api_url)
        headers = {
            "Accept": "application/json",
            "User-Agent": "STE-5D-Slicer-LLMClient/1.0",
        }
        if self.api_key:
            if self.api_key.lower().startswith("bearer "):
                headers["Authorization"] = self.api_key
            else:
                headers["Authorization"] = "Bearer " + self.api_key

        ctx = self._ssl_context if models_url.lower().startswith("https") else None
        try:
            req = urllib.request.Request(models_url, headers=headers, method="GET")
            resp = urllib.request.urlopen(req, timeout=test_timeout, context=ctx)
            raw = json.loads(resp.read().decode("utf-8"))
            data = raw.get("data")
            if isinstance(data, list):
                model_ids = [m.get("id") for m in data if isinstance(m, dict) and "id" in m]
                if self.model and self.model in model_ids:
                    return True, "Подключение успешно! Найдена настроенная модель: '{0}'.".format(self.model)
                elif model_ids:
                    return True, "Подключение успешно! Доступно моделей: {0}.".format(len(model_ids))
            return True, "Подключение успешно! Эндпоинт /models доступен."

        except urllib.error.HTTPError as e:
            # 404/405/501 indicates /models is not implemented or disabled; fallback to /chat/completions
            if e.code in (404, 405, 501):
                return self._test_chat_completion_endpoint(test_timeout)
            return False, self._format_http_error(e)

        except ssl.SSLError as e:
            return False, (
                "Ошибка SSL-сертификата: {0}. Если используется внутренний или "
                "самоподписанный сертификат, отключите проверку SSL в настройках."
            ).format(str(e))

        except urllib.error.URLError as e:
            reason = getattr(e, "reason", "")
            if "timed out" in str(reason).lower():
                return False, "Превышено время ожидания ответа сервера ({0}с): {1}".format(test_timeout, reason)
            return False, "Не удалось подключиться к серверу ({0}): {1}".format(self.api_url, reason)

        except Exception as e:
            return False, "Ошибка при проверке подключения: {0}".format(str(e))

    def _test_chat_completion_endpoint(self, timeout):
        # type: (float) -> Tuple[bool, str]
        """Fallback check sending a minimal 1-token POST to /chat/completions."""
        chat_url = "{0}/chat/completions".format(self.api_url)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "STE-5D-Slicer-LLMClient/1.0",
        }
        if self.api_key:
            if self.api_key.lower().startswith("bearer "):
                headers["Authorization"] = self.api_key
            else:
                headers["Authorization"] = "Bearer " + self.api_key

        test_payload = {
            "model": self.model or "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        data_bytes = json.dumps(test_payload).encode("utf-8")
        headers["Content-Length"] = str(len(data_bytes))

        ctx = self._ssl_context if chat_url.lower().startswith("https") else None
        try:
            req = urllib.request.Request(chat_url, data=data_bytes, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=timeout, context=ctx)
            return True, "Подключение успешно! (Проверено через эндпоинт /chat/completions)"
        except urllib.error.HTTPError as e:
            return False, self._format_http_error(e)
        except Exception as e:
            return False, "Ошибка при проверке /chat/completions: {0}".format(str(e))

    def get_available_models(self):
        # type: () -> List[str]
        """
        Fetches the list of available model IDs from the /models endpoint.

        Returns:
            List of model ID strings, or an empty list if /models is unavailable.
        """
        models_url = "{0}/models".format(self.api_url)
        headers = {
            "Accept": "application/json",
            "User-Agent": "STE-5D-Slicer-LLMClient/1.0",
        }
        if self.api_key:
            if self.api_key.lower().startswith("bearer "):
                headers["Authorization"] = self.api_key
            else:
                headers["Authorization"] = "Bearer " + self.api_key

        ctx = self._ssl_context if models_url.lower().startswith("https") else None
        try:
            req = urllib.request.Request(models_url, headers=headers, method="GET")
            resp = urllib.request.urlopen(req, timeout=min(self.timeout, 10.0), context=ctx)
            raw = json.loads(resp.read().decode("utf-8"))
            data = raw.get("data")
            if isinstance(data, list):
                return [m["id"] for m in data if isinstance(m, dict) and "id" in m]
            return []
        except Exception:
            return []

    def _parse_chat_response(self, raw_response, expected_tools=None):
        # type: (Dict[str, Any], Optional[List[Dict[str, Any]]]) -> LLMResponse
        """Parses raw JSON response from /chat/completions into LLMResponse."""
        choices = raw_response.get("choices")
        if choices and isinstance(choices, list) and len(choices) > 0:
            first_choice = choices[0]
            message = first_choice.get("message") or {}
            content = message.get("content")
            finish_reason = first_choice.get("finish_reason") or "stop"
            raw_tool_calls = message.get("tool_calls")
        else:
            message = raw_response.get("message") or {}
            content = message.get("content") or raw_response.get("content") or raw_response.get("text")
            finish_reason = raw_response.get("finish_reason") or "stop"
            raw_tool_calls = message.get("tool_calls") or raw_response.get("tool_calls")

        raw_usage = raw_response.get("usage") or {}
        usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
        }

        # 1. Parse native OpenAI tool_calls
        tool_calls = []  # type: List[ToolCallItem]
        if raw_tool_calls and isinstance(raw_tool_calls, list):
            for tc in raw_tool_calls:
                parsed = self._parse_native_tool_call(tc)
                if parsed:
                    tool_calls.append(parsed)

        # 2. Fallback parser if native tool_calls are absent
        if not tool_calls and content:
            fallback_calls, cleaned_content = self.fallback_parser.parse(
                content, expected_tools=expected_tools
            )
            if fallback_calls:
                tool_calls = fallback_calls
                content = cleaned_content
                if finish_reason in ("stop", "", None):
                    finish_reason = "tool_calls"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage
        )

    def _parse_native_tool_call(self, tc):
        # type: (Any) -> Optional[ToolCallItem]
        """Converts an OpenAI tool_call dict into a ToolCallItem."""
        if not isinstance(tc, dict):
            return None
        call_id = tc.get("id") or ("call_" + uuid.uuid4().hex[:8])
        fn = tc.get("function")
        if isinstance(fn, dict):
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
        else:
            name = tc.get("name", "")
            raw_args = tc.get("arguments", "{}")

        if isinstance(raw_args, (dict, list)):
            args_json = json.dumps(raw_args, ensure_ascii=False)
        elif isinstance(raw_args, str):
            args_json = raw_args.strip() or "{}"
        else:
            args_json = json.dumps(raw_args, ensure_ascii=False) if raw_args is not None else "{}"

        return ToolCallItem(id=call_id, name=name, arguments_json=args_json)

    def _get_retry_after(self, headers):
        # type: (Any) -> Optional[float]
        """Extracts seconds from HTTP Retry-After header if present."""
        if not headers:
            return None
        val = headers.get("Retry-After")
        if val:
            try:
                return float(val)
            except ValueError:
                pass
        return None

    def _extract_error_message(self, body_text):
        # type: (str) -> Optional[str]
        """Extracts error message from JSON error response if possible."""
        if not body_text:
            return None
        try:
            d = json.loads(body_text)
            if isinstance(d, dict):
                err = d.get("error")
                if isinstance(err, dict) and "message" in err:
                    return str(err["message"])
                elif isinstance(err, str):
                    return err
                elif "message" in d:
                    return str(d["message"])
        except Exception:
            pass
        return body_text[:200]

    def _format_http_error(self, e):
        # type: (urllib.error.HTTPError) -> str
        """Formats user-friendly Russian status message for SettingsDialog.qml."""
        code = getattr(e, "code", 0)
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = self._extract_error_message(err_body)

        if code == 401:
            return "Ошибка авторизации (401 Unauthorized): Неверный API-ключ."
        elif code == 403:
            return "Доступ запрещен (403 Forbidden): Недостаточно прав или неверный API-ключ."
        elif code == 404:
            return "Эндпоинт не найден (404 Not Found): Проверьте правильность URL '{0}'.".format(self.api_url)
        elif code == 429:
            return "Превышен лимит запросов (429 Too Many Requests): Попробуйте позже."
        elif code == 500:
            return "Внутренняя ошибка сервера модели (500 Internal Server Error)."
        elif code in (502, 503, 504):
            return "Сервер модели временно недоступен ({0} {1}).".format(code, e.reason)

        if msg:
            return "Ошибка HTTP {0}: {1}".format(code, msg)
        return "Ошибка HTTP {0}: {1}".format(code, e.reason)
