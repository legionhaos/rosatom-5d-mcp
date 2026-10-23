# -*- coding: utf-8 -*-
"""
Agent Worker Thread for STE Slicer.

Executes the full LLM communication cycle and MCP tool invocations in a dedicated
Qt background worker thread (QThread) so that the STE Slicer UI remains completely
responsive and smooth during network requests, 5D slicing calculations, and geometry analysis.
"""

import json
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple, Union

# Try to import project logger if available, otherwise use standard logging
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger("AgentWorker")

# Qt QThread and pyqtSignal imports with dynamic fallback for non-Qt environments
try:
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal
    except ImportError:
        try:
            from PySide2.QtCore import QThread, Signal as pyqtSignal
        except ImportError:
            try:
                from PySide6.QtCore import QThread, Signal as pyqtSignal
            except ImportError:
                # Standalone fallback implementation for environments without Qt bindings installed
                class _FallbackSignalDescriptor(object):
                    def __init__(self, *types):
                        self.types = types

                    def __get__(self, instance, owner):
                        if instance is None:
                            return self
                        if not hasattr(instance, "_signals_map"):
                            instance._signals_map = {}
                        if self not in instance._signals_map:
                            instance._signals_map[self] = _FallbackBoundSignal(self.types)
                        return instance._signals_map[self]

                class _FallbackBoundSignal(object):
                    def __init__(self, types):
                        self.types = types
                        self._slots = []

                    def connect(self, slot):
                        if slot not in self._slots:
                            self._slots.append(slot)

                    def disconnect(self, slot):
                        if slot in self._slots:
                            self._slots.remove(slot)

                    def emit(self, *args):
                        for slot in list(self._slots):
                            try:
                                slot(*args)
                            except Exception as e:
                                logger.error("Exception in signal slot %s: %s", slot, e)

                class _FallbackQThread(object):
                    def __init__(self, parent=None):
                        self.parent = parent
                        self._thread = None
                        self._is_running = False

                    def start(self):
                        self._is_running = True
                        self._thread = threading.Thread(target=self._run_wrapper)
                        self._thread.daemon = True
                        self._thread.start()

                    def _run_wrapper(self):
                        try:
                            self.run()
                        finally:
                            self._is_running = False

                    def run(self):
                        pass

                    def wait(self, timeout=None):
                        if self._thread and self._thread.is_alive():
                            # timeout in QThread wait() is milliseconds; convert to seconds if provided
                            secs = (timeout / 1000.0) if timeout is not None else None
                            self._thread.join(secs)

                    def isRunning(self):
                        return self._is_running

                QThread = _FallbackQThread
                pyqtSignal = _FallbackSignalDescriptor


class AgentWorker(QThread):
    """
    Dedicated QThread worker executing the agent reasoning loop and MCP tool calls.

    Signals:
        toolCallStarted(call_id, tool_name, args_json): Emitted when an MCP tool invocation begins.
        toolCallFinished(call_id, status, summary, duration_ms): Emitted when a tool call finishes.
        finalAnswerReceived(markdown_answer, summary_card_dict): Emitted upon completion of the request.
        workerError(error_message): Emitted if an unhandled error occurs during execution.
    """

    toolCallStarted = pyqtSignal(str, str, str)
    toolCallFinished = pyqtSignal(str, str, str, int)
    finalAnswerReceived = pyqtSignal(str, dict)
    workerError = pyqtSignal(str)

    def __init__(self, orchestrator=None, parent=None):
        # type: (Any, Any) -> None
        """
        Initializes the agent worker thread.

        Args:
            orchestrator: Optional AgentOrchestrator instance to process requests.
            parent: Optional QObject parent.
        """
        super(AgentWorker, self).__init__(parent)
        self.orchestrator = orchestrator
        self.user_prompt = ""
        self.attachment_paths = []  # type: List[str]
        self._is_cancelled = False
        self._final_answer_emitted = False

    def set_task(self, user_prompt, attachment_paths=None):
        # type: (str, Optional[List[str]]) -> None
        """
        Sets the user request and file attachments prior to starting the thread.

        Args:
            user_prompt: User instruction text.
            attachment_paths: List of file paths (3D models, images, etc.).
        """
        self.user_prompt = str(user_prompt or "")
        self.attachment_paths = list(attachment_paths) if attachment_paths else []
        self._is_cancelled = False
        self._final_answer_emitted = False
        logger.debug(
            "AgentWorker task configured: prompt='%s', %d attachments",
            self.user_prompt[:60],
            len(self.attachment_paths)
        )

    def set_orchestrator(self, orchestrator):
        # type: (Any) -> None
        """Sets or replaces the orchestrator instance."""
        self.orchestrator = orchestrator

    def cancel(self):
        # type: () -> None
        """Flags the worker thread for cancellation."""
        self._is_cancelled = True
        logger.info("AgentWorker cancellation requested.")

    stop = cancel

    @property
    def is_cancelled(self):
        # type: () -> bool
        """Returns True if task cancellation has been requested."""
        return self._is_cancelled

    def run(self):
        # type: () -> None
        """
        Main execution method run in the background QThread.

        Invokes self.orchestrator.process_user_request(...) with self as callbacks
        and catches any unhandled exceptions to prevent crashing the host process.
        """
        logger.info(
            "AgentWorker thread started. Executing task: '%s' (%d attachments)",
            self.user_prompt[:80],
            len(self.attachment_paths)
        )

        # Lazy creation of orchestrator if not provided
        if self.orchestrator is None:
            try:
                from plugin.agent.orchestrator import AgentOrchestrator
                self.orchestrator = AgentOrchestrator()
            except Exception as e:
                err_msg = "AgentWorker error: No orchestrator provided and cannot create default: {0}".format(str(e))
                logger.error(err_msg)
                self.workerError.emit(err_msg)
                return

        try:
            result = self.orchestrator.process_user_request(
                self.user_prompt,
                self.attachment_paths,
                callbacks=self
            )

            # If not already emitted via callback, emit the final answer
            if result is not None and not self._final_answer_emitted:
                if isinstance(result, tuple) and len(result) == 2:
                    markdown_answer, summary_card = result
                    self.on_final_answer_received(markdown_answer, summary_card)
                elif isinstance(result, str):
                    self.on_final_answer_received(result, {})
                elif isinstance(result, dict):
                    content = result.get("content") or result.get("markdown") or str(result)
                    summary = result.get("summary") or result.get("summary_card") or {}
                    self.on_final_answer_received(content, summary)

            logger.info("AgentWorker thread finished processing successfully.")

        except Exception as e:
            logger.exception("AgentWorker encountered an unhandled exception: %s", e)
            self.workerError.emit(str(e))

    # -----------------------------------------------------------------
    # Callback Interface (invoked by orchestrator during execution)
    # -----------------------------------------------------------------

    def on_tool_call_started(self, call_id, tool_name, args_json):
        # type: (str, str, Any) -> None
        """
        Callback emitted when an MCP tool call begins execution.

        Args:
            call_id: Unique tool call identifier.
            tool_name: Name of the MCP tool being called.
            args_json: Arguments as JSON string or dict.
        """
        if isinstance(args_json, (dict, list)):
            args_str = json.dumps(args_json, ensure_ascii=False)
        else:
            args_str = str(args_json or "{}")

        logger.debug("Tool call started: %s (%s)", tool_name, call_id)
        self.toolCallStarted.emit(str(call_id), str(tool_name), args_str)

    tool_call_started = on_tool_call_started

    def on_tool_call_finished(self, call_id, status, summary, duration_ms):
        # type: (str, str, str, int) -> None
        """
        Callback emitted when an MCP tool call finishes execution.

        Args:
            call_id: Unique tool call identifier.
            status: Status string (e.g. 'ok', 'error', 'success').
            summary: Brief human-readable summary of the execution outcome.
            duration_ms: Execution duration in milliseconds.
        """
        logger.debug("Tool call finished: %s [%s] in %dms: %s", call_id, status, duration_ms, summary)
        self.toolCallFinished.emit(str(call_id), str(status), str(summary), int(duration_ms))

    tool_call_finished = on_tool_call_finished

    def on_final_answer_received(self, markdown_answer, summary_card_dict):
        # type: (str, Any) -> None
        """
        Callback emitted when the final engineering answer and summary card are ready.

        Args:
            markdown_answer: Formatted Markdown text of the response.
            summary_card_dict: Dictionary with key metrics (mode, print_time, material_weight, etc.).
        """
        self._final_answer_emitted = True
        summary = dict(summary_card_dict) if isinstance(summary_card_dict, dict) else {}
        logger.info("Final answer received (%d chars)", len(markdown_answer or ""))
        self.finalAnswerReceived.emit(str(markdown_answer or ""), summary)

    final_answer_received = on_final_answer_received

    def on_error(self, error_message):
        # type: (str) -> None
        """
        Callback emitted when an error occurs during processing.

        Args:
            error_message: Error description string.
        """
        logger.error("AgentWorker error callback: %s", error_message)
        self.workerError.emit(str(error_message))

    worker_error = on_error
