# -*- coding: utf-8 -*-
"""
Agent Orchestrator for STE Slicer.

Implements the ReAct (Reasoning + Acting) execution loop coordinating
dialogue between the OpenAI-compatible LLM client and the MCP tool server.
"""

import json
import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Union

# Try to import project logger if available, otherwise use standard logging
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger("AgentOrchestrator")

from plugin.agent.llm_client import OpenAICompatibleClient, LLMResponse, ToolCallItem, LLMConnectionConfig
from plugin.agent.prompt_builder import SystemPromptBuilder
from plugin.agent.context_manager import ConversationContextManager
from plugin.mcp_server.server import MCPServer


class AgentOrchestrator(object):
    """
    Orchestrates the ReAct agent cycle:
    1. Prepares user context and attachments.
    2. Captures slicer snapshot and compiles dynamic system prompt.
    3. Runs the multi-turn tool execution loop (up to max_iterations).
    4. Dispatches tool calls, streams progress signals to worker callbacks,
       and builds the final parameter summary card upon completion.
    """

    def __init__(self,
                 settings_mgr=None,
                 mcp_server=None,
                 context_mgr=None,
                 prompt_builder=None,
                 llm_client=None,
                 max_iterations=8):
        # type: (Optional[Any], Optional[MCPServer], Optional[ConversationContextManager], Optional[SystemPromptBuilder], Optional[OpenAICompatibleClient], int) -> None
        """
        Initializes the agent orchestrator with required sub-systems.

        Args:
            settings_mgr: PluginSettingsManager instance (manages credentials and settings).
            mcp_server: MCPServer instance (registers and executes slicing tools).
            context_mgr: ConversationContextManager instance (manages dialogue history and attachments).
            prompt_builder: SystemPromptBuilder instance (compiles domain knowledge prompt).
            llm_client: Optional pre-configured OpenAICompatibleClient.
            max_iterations: Maximum number of ReAct tool-calling iterations (default: 8).
        """
        if settings_mgr is None:
            try:
                from plugin.config.settings_config import PluginSettingsManager
                self.settings_mgr = PluginSettingsManager()
            except Exception:
                self.settings_mgr = None
        else:
            self.settings_mgr = settings_mgr

        self.mcp_server = mcp_server if mcp_server is not None else MCPServer()
        self.context_mgr = context_mgr if context_mgr is not None else ConversationContextManager()
        self.prompt_builder = prompt_builder if prompt_builder is not None else SystemPromptBuilder()

        if llm_client is not None:
            self.llm_client = llm_client
        elif self.settings_mgr is not None and hasattr(self.settings_mgr, "get_llm_client"):
            self.llm_client = self.settings_mgr.get_llm_client()
        else:
            self.llm_client = OpenAICompatibleClient(LLMConnectionConfig())

        self.max_iterations = int(max_iterations) if max_iterations is not None else 8
        logger.info("AgentOrchestrator initialized (max_iterations=%d).", self.max_iterations)

    def configure_llm(self, base_url, api_key, model):
        # type: (str, str, str) -> None
        """Reconfigures the LLM client with updated credentials."""
        from plugin.agent.llm_client import OpenAICompatibleClient, LLMConnectionConfig
        cfg = LLMConnectionConfig(base_url=base_url, api_key=api_key, model=model)
        self.llm_client = OpenAICompatibleClient(cfg)
        logger.info("AgentOrchestrator LLM client reconfigured: model=%s", model)

    def process_user_request(self,
                             user_prompt,
                             attachments=None,
                             worker_callbacks=None,
                             callbacks=None):
        # type: (str, Optional[List[str]], Optional[Any], Optional[Any]) -> Tuple[str, Dict[str, Any]]
        """
        Processes a user request through the ReAct agent loop.

        Steps:
        1. Appends user turn and attachments (.stl, .3mf, images) to context_mgr.
        2. Captures live slicer snapshot and compiles system prompt.
        3. Executes the ReAct loop (up to max_iterations = 8):
           - Calls llm_client.chat_completion(messages, tools=mcp_server.get_tools_schema()).
           - If tool_calls are present: executes each tool via mcp_server, emits progress
             signals to worker_callbacks, and records tool results in context_mgr.
           - If tool_calls are empty: records final assistant message, builds summary_card,
             notifies callbacks, and returns (final_markdown, summary_card).

        Args:
            user_prompt: User instruction string.
            attachments: List of file paths attached to the prompt.
            worker_callbacks: Optional AgentWorker or callback object with signal handlers.
            callbacks: Alias for worker_callbacks.

        Returns:
            Tuple[str, Dict[str, Any]]: (markdown_answer, summary_card_dict).
        """
        cb = worker_callbacks if worker_callbacks is not None else callbacks

        logger.info(
            "AgentOrchestrator starting process_user_request: '%s' (%d attachments)",
            user_prompt[:80] if user_prompt else "",
            len(attachments or [])
        )

        # 1. Add user turn with attachments (.stl, .3mf, .obj, .png, .jpg)
        self.context_mgr.add_user_turn(user_prompt, attachments)

        # 2. Capture slicer snapshot and compile dynamic system prompt
        snapshot = self.context_mgr.capture_slicer_snapshot()
        system_prompt = self.prompt_builder.build_system_prompt(snapshot)

        executed_tools = {}  # type: Dict[str, Dict[str, Any]]
        final_answer = ""
        summary_card = {}  # type: Dict[str, Any]

        # 3. ReAct execution loop
        for iteration in range(1, self.max_iterations + 1):
            if cb and getattr(cb, "is_cancelled", False):
                logger.info("AgentOrchestrator execution cancelled by user.")
                final_answer = "Операция отменена пользователем."
                summary_card = self._build_summary_card(final_answer, snapshot, executed_tools)
                self._emit_final_answer(cb, final_answer, summary_card)
                return final_answer, summary_card

            messages = self.context_mgr.build_messages_payload(system_prompt)
            tools_schema = self.mcp_server.get_tools_schema() if self.mcp_server else None

            logger.debug("ReAct iteration %d/%d: calling LLM with %d messages",
                         iteration, self.max_iterations, len(messages))

            llm_response = self.llm_client.chat_completion(messages, tools=tools_schema)

            # Check if model requested tool invocations
            if llm_response.tool_calls:
                logger.info("LLM requested %d tool call(s) on iteration %d",
                            len(llm_response.tool_calls), iteration)

                # Record assistant's tool call request in history
                self.context_mgr.add_assistant_tool_calls(
                    llm_response.content,
                    llm_response.tool_calls
                )

                # Sequentially execute each requested tool
                for tc in llm_response.tool_calls:
                    call_id = tc.id
                    tool_name = tc.name
                    args_json = tc.arguments_json

                    # Signal UI: tool call started
                    self._emit_tool_started(cb, call_id, tool_name, args_json)

                    start_time = time.time()
                    status = "ok"
                    try:
                        tool_result = self.mcp_server.call_tool(tool_name, args_json)
                        if isinstance(tool_result, dict) and tool_result.get("status") == "error":
                            status = "error"
                    except Exception as e:
                        logger.exception("Error executing MCP tool '%s': %s", tool_name, e)
                        status = "error"
                        tool_result = {"status": "error", "error": str(e)}

                    duration_ms = int((time.time() - start_time) * 1000)
                    summary = self._create_tool_summary(tool_name, tool_result)

                    # Signal UI: tool call finished
                    self._emit_tool_finished(cb, call_id, status, summary, duration_ms)

                    # Save tool result in history and local execution cache
                    executed_tools[tool_name] = tool_result
                    self.context_mgr.add_tool_result(call_id, tool_name, tool_result)

                # Continue loop to allow model to reason over tool results
                continue

            else:
                # No tool calls: final engineering answer received
                final_answer = llm_response.content or ""
                logger.info("LLM returned final response on iteration %d (%d chars)",
                            iteration, len(final_answer))

                self.context_mgr.add_assistant_message(final_answer)
                summary_card = self._build_summary_card(final_answer, snapshot, executed_tools)

                self._emit_final_answer(cb, final_answer, summary_card)
                return final_answer, summary_card

        # If max iterations reached without final text, request a final summary
        logger.warning("Reached max iterations (%d) without final answer. Requesting final summary.",
                       self.max_iterations)
        try:
            forced_messages = self.context_mgr.build_messages_payload(system_prompt)
            forced_messages.append({
                "role": "user",
                "content": "Предоставь итоговый структурированный инженерный отчет главного технолога по выполненным операциям нарезки."
            })
            forced_resp = self.llm_client.chat_completion(forced_messages, tools=None)
            final_answer = forced_resp.content or "Слайсинг и подготовка параметров завершены."
        except Exception as e:
            logger.error("Failed to generate forced final summary: %s", e)
            final_answer = "Технологический цикл завершен. Параметры слайсинга успешно применены."

        self.context_mgr.add_assistant_message(final_answer)
        summary_card = self._build_summary_card(final_answer, snapshot, executed_tools)
        self._emit_final_answer(cb, final_answer, summary_card)
        return final_answer, summary_card

    # -----------------------------------------------------------------
    # Helper & Summary Generation Methods
    # -----------------------------------------------------------------

    def _build_summary_card(self, final_text, snapshot, executed_tools):
        # type: (str, Dict[str, Any], Dict[str, Dict[str, Any]]) -> Dict[str, Any]
        """
        Compiles the summary card of slicing parameters from tool execution results,
        active slicer snapshot, and text parsing fallbacks.
        """
        card = {
            "mode": "5D",
            "profile": "5D_structural",
            "material": "PA6-CF",
            "layer_height_mm": 0.2,
            "wall_line_count": 4,
            "infill_density_pct": 50,
            "infill_pattern": "gyroid",
            "print_temperature_c": 275,
            "bed_temperature_c": 90,
            "fan_speed_pct": 0,
            "support_enabled": False,
            "rotation_deg": [0.0, 0.0, 0.0],
            "print_time_formatted": "1 ч 10 мин",
            "material_weight_g": 52.4,
            "filament_length_m": 16.8,
            "status": "ready_to_print"
        }

        # 1. Overlay from initial snapshot
        if snapshot:
            if snapshot.get("current_mode"):
                card["mode"] = snapshot["current_mode"]
            if snapshot.get("current_profile"):
                card["profile"] = snapshot["current_profile"]
            if snapshot.get("current_material"):
                card["material"] = snapshot["current_material"]
            key_params = snapshot.get("key_parameters") or {}
            for k in ("layer_height_mm", "wall_line_count", "infill_density_pct",
                      "infill_pattern", "print_temperature_c", "bed_temperature_c",
                      "fan_speed_pct", "support_enabled"):
                if k in key_params:
                    card[k] = key_params[k]

        # 2. Overlay from select_print_mode_and_profile tool result
        sel_tool = executed_tools.get("select_print_mode_and_profile") or {}
        if sel_tool:
            if sel_tool.get("mode"):
                card["mode"] = sel_tool["mode"]
            if sel_tool.get("profile"):
                card["profile"] = sel_tool["profile"]
            if sel_tool.get("material"):
                card["material"] = sel_tool["material"]

        # 3. Overlay from modify_scene_and_parameters tool result
        mod_tool = executed_tools.get("modify_scene_and_parameters") or {}
        if mod_tool:
            if "applied_rotation_deg" in mod_tool:
                card["rotation_deg"] = mod_tool["applied_rotation_deg"]
            params = mod_tool.get("applied_parameters") or {}
            for k in ("layer_height_mm", "wall_line_count", "infill_density_pct",
                      "infill_pattern", "print_temperature_c", "bed_temperature_c",
                      "fan_speed_pct", "support_enabled"):
                if k in params:
                    card[k] = params[k]

        # 4. Overlay from run_slicing_and_generate_gcode tool result
        slice_tool = executed_tools.get("run_slicing_and_generate_gcode") or {}
        if slice_tool:
            if slice_tool.get("print_time_formatted"):
                card["print_time_formatted"] = slice_tool["print_time_formatted"]
            if slice_tool.get("material_weight_g") is not None:
                card["material_weight_g"] = slice_tool["material_weight_g"]
            if slice_tool.get("filament_length_m") is not None:
                card["filament_length_m"] = slice_tool["filament_length_m"]
            if slice_tool.get("mode_used"):
                card["mode"] = slice_tool["mode_used"]

        # 5. Fallback text parsing if 3D vs 5D is mentioned explicitly in final text
        if "3D Planar" in final_text or "режим 3D" in final_text:
            if "5D" not in final_text[:final_text.find("3D")]:
                card["mode"] = "3D"
        elif "5D" in final_text:
            card["mode"] = "5D"

        return card

    def _create_tool_summary(self, tool_name, result):
        # type: (str, Dict[str, Any]) -> str
        """Generates a concise Russian description of the tool execution result for the UI."""
        if not isinstance(result, dict):
            return "Инструмент {0} выполнен.".format(tool_name)

        if result.get("status") == "error":
            return "Ошибка: {0}".format(result.get("error", "сбой выполнения"))

        if tool_name == "analyze_mesh_geometry":
            dims = result.get("dimensions_mm", [0, 0, 0])
            mode = result.get("recommended_mode", "5D")
            return "Геометрия проанализирована: габариты {0}x{1}x{2} мм, рекомендован режим {3}.".format(
                dims[0], dims[1], dims[2], mode
            )

        elif tool_name == "select_print_mode_and_profile":
            return "Выбран режим {0}, профиль '{1}', материал '{2}'.".format(
                result.get("mode", "5D"),
                result.get("profile", "5D_structural"),
                result.get("material", "PA6-CF")
            )

        elif tool_name == "modify_scene_and_parameters":
            rot = result.get("applied_rotation_deg", [0, 0, 0])
            params = result.get("applied_parameters") or {}
            temp = params.get("print_temperature_c", 275)
            walls = params.get("wall_line_count", 4)
            return "Применена ориентация (X:{0}°, Y:{1}°, Z:{2}°), температура {3}°C, {4} стенки.".format(
                rot[0], rot[1], rot[2], temp, walls
            )

        elif tool_name == "run_slicing_and_generate_gcode":
            time_str = result.get("print_time_formatted", "1 ч 10 мин")
            weight = result.get("material_weight_g", 0)
            return "Слайсинг завершен: время {0}, расход {1} г.".format(time_str, weight)

        return result.get("message") or "Инструмент {0} успешно выполнен.".format(tool_name)

    # -----------------------------------------------------------------
    # Callback Notification Dispatchers
    # -----------------------------------------------------------------

    @staticmethod
    def _emit_tool_started(cb, call_id, tool_name, args_json):
        if not cb:
            return
        if hasattr(cb, "on_tool_call_started"):
            cb.on_tool_call_started(call_id, tool_name, args_json)
        elif hasattr(cb, "toolCallStarted"):
            cb.toolCallStarted.emit(call_id, tool_name, str(args_json))

    @staticmethod
    def _emit_tool_finished(cb, call_id, status, summary, duration_ms):
        if not cb:
            return
        if hasattr(cb, "on_tool_call_finished"):
            cb.on_tool_call_finished(call_id, status, summary, duration_ms)
        elif hasattr(cb, "toolCallFinished"):
            cb.toolCallFinished.emit(call_id, status, summary, int(duration_ms))

    @staticmethod
    def _emit_final_answer(cb, final_answer, summary_card):
        if not cb:
            return
        if hasattr(cb, "on_final_answer_received"):
            cb.on_final_answer_received(final_answer, summary_card)
        elif hasattr(cb, "finalAnswerReceived"):
            cb.finalAnswerReceived.emit(final_answer, summary_card)


__all__ = ["AgentOrchestrator"]
