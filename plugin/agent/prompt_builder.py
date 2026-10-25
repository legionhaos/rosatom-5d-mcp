# -*- coding: utf-8 -*-
"""
Dynamic System Prompt Builder for Stereotech STE Slicer Assistant.

This module provides the SystemPromptBuilder class, which compiles a comprehensive,
expert-level system prompt for an LLM acting as the Chief Additive Manufacturing
Technologist at Stereotech.

The prompt dynamically integrates:
- Domain knowledge for 5D (multi-axis) and 3D (planar) FDM printing (domain_knowledge_3d5d.json).
- Material technical parameters and slicing heuristics.
- Mandatory MCP tool pipeline sequence:
  analyze_mesh_geometry -> select_print_mode_and_profile -> modify_scene_and_parameters -> run_slicing_and_generate_gcode.
- Dynamic snapshot of the active STE Slicer scene (models, printer, available profiles/materials, active settings).
- Strict requirements for the final engineering response with in-depth justification of all chosen parameters.
"""

import json
import logging
import os
import sys
from typing import Dict, Any, List, Optional, Tuple, Union

# Try to import project logger if available, otherwise use standard logging
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger("SystemPromptBuilder")


class SystemPromptBuilder(object):
    """
    Builder responsible for generating the LLM System Prompt with embedded
    3D/5D additive manufacturing domain knowledge and active slicer state.
    """

    DEFAULT_KB_RELATIVE_PATH = os.path.join("plugin", "config", "domain_knowledge_3d5d.json")

    def __init__(self, knowledge_base_path=None):
        # type: (Optional[str]) -> None
        """
        Initializes the prompt builder and loads the 3D/5D domain knowledge base.

        Args:
            knowledge_base_path: Optional path to domain_knowledge_3d5d.json.
                                If None, resolves to the default config location.
        """
        if knowledge_base_path is None:
            knowledge_base_path = self._resolve_default_kb_path()

        self.knowledge_base_path = str(knowledge_base_path)
        self.knowledge_base = self._load_knowledge_base(self.knowledge_base_path)
        logger.info("SystemPromptBuilder initialized with knowledge base: %s", self.knowledge_base_path)

    @staticmethod
    def _resolve_default_kb_path():
        # type: () -> str
        """Resolves the absolute path to domain_knowledge_3d5d.json."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_dir = os.path.dirname(current_dir)
        candidate = os.path.join(plugin_dir, "config", "domain_knowledge_3d5d.json")
        if os.path.exists(candidate):
            return candidate

        # Workspace fallback
        workspace_candidate = os.path.abspath(os.path.join("plugin", "config", "domain_knowledge_3d5d.json"))
        return workspace_candidate

    def _load_knowledge_base(self, path):
        # type: (str) -> Dict[str, Any]
        """
        Loads the domain knowledge JSON file from disk with fallback to
        built-in defaults if the file is missing or corrupted.
        """
        if path and os.path.isfile(path) and os.path.getsize(path) > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
                logger.warning("Knowledge base JSON at '%s' is not a dictionary. Using fallback.", path)
            except Exception as e:
                logger.error("Failed to load knowledge base from '%s': %s. Using fallback.", path, str(e))

        logger.info("Using embedded default 3D/5D domain knowledge base.")
        return self._get_default_knowledge_base()

    def build_system_prompt(self, slicer_snapshot=None):
        # type: (Optional[Dict[str, Any]]) -> str
        """
        Compiles the complete System Prompt for the LLM agent.

        Args:
            slicer_snapshot: Dictionary representing the current state of STE Slicer
                             (loaded models, printer info, available profiles/materials, active settings).

        Returns:
            str: Full compiled system prompt.
        """
        snapshot = slicer_snapshot if isinstance(slicer_snapshot, dict) else {}

        sections = [
            self._render_header_and_role(),
            self._render_mandatory_pipeline(),
            self._render_image_analysis_guidelines(),
            self._render_domain_knowledge_rules(),
            self._render_materials_and_profiles(snapshot),
            self._render_slicer_snapshot(snapshot),
            self._render_final_response_requirements()
        ]

        return "\n\n".join(sections)

    # -----------------------------------------------------------------
    # Prompt Section Renderers
    # -----------------------------------------------------------------

    def _render_image_analysis_guidelines(self):
        # type: () -> str
        """Section: Guidelines for analyzing attached images, renders, and photo references."""
        return (
            "================================================================================\n"
            "АНАЛИЗ ПРИКРЕПЛЁННЫХ ИЗОБРАЖЕНИЙ (ФОТОГРАФИИ, РЕНДЕРЫ, ЭСКИЗЫ НАГРУЗОК)\n"
            "================================================================================\n"
            "Пользователь может прикреплять графические материалы: CAD-рендеры 3D-модели, фотографии\n"
            "реальных деталей, чертежи, схемы установки или эскизы действующих механических нагрузок.\n\n"
            "ПРАВИЛА И СТРАТЕГИЯ АНАЛИЗА ИЗОБРАЖЕНИЙ:\n"
            "1. ВИЗУАЛЬНАЯ ДИАГНОСТИКА ФОРМЫ И КОНСТРУКЦИИ:\n"
            "   - Внимательно изучите форму детали, тип узла (кронштейн, шестерня, патрубок, корпус, рычаг).\n"
            "   - Определите критические элементы: посадочные отверстия, тонкие стенки и рёбра жёсткости,\n"
            "     консоли, закругления, внутренние каналы.\n"
            "   - Оцените предполагаемые направления механических сил (растяжение, изгиб, кручение).\n\n"
            "2. СОПОСТАВЛЕНИЕ С 3D-МОДЕЛЬЮ В СЦЕНЕ (ЕСЛИ МОДЕЛЬ ЗАГРУЖЕНА НА СТОЛ):\n"
            "   - Сопоставьте ракурс и вид с рендера/фото с ориентацией модели на столе слайсера.\n"
            "   - Ориентируйте деталь так, чтобы траектории укладки волокон/слоёв (особенно в 5D CFF) совпадали\n"
            "     с направлениями растягивающих напряжений.\n"
            "   - Исключите расположение поддержек на ответственных поверхностях, видимых на рендере.\n\n"
            "3. АНАЛИЗ ПРИ ОТСУТСТВИИ 3D-МОДЕЛИ В СЦЕНЕ (ТОЛЬКО ИЗОБРАЖЕНИЕ / РЕНДЕР):\n"
            "   - Если 3D-модель ещё не импортирована, а предоставлен только рендер или фото:\n"
            "     проведите полный предварительный технологический расчёт прямо по изображению!\n"
            "   - Рекомендуйте режим печати: 5D (для фасонных/пространственных деталей, труб, винтов, необходимости\n"
            "     равнопрочности во всех направлениях без анизотропии) либо 3D (для простых плоских деталей).\n"
            "   - Подберите конструкционный материал (PA6-CF для высоких ударных и статических нагрузок, PETG для химстойкости,\n"
            "     TPU для демпфирования, PLA для быстрого прототипирования) и технологические параметры (сопло 0.4 мм,\n"
            "     высоту слоя 0.16–0.2 мм, 4–5 периметров, 50–70% гироидного заполнения).\n"
            "   - Опишите требования к CAD-модели и рекомендации конструктору перед слайсингом."
        )

    def _render_header_and_role(self):
        # type: () -> str
        """Section 1: Chief Additive Manufacturing Technologist role."""
        return (
            "================================================================================\n"
            "РОЛЬ И ПРОФЕССИОНАЛЬНАЯ КВАЛИФИКАЦИЯ (ROLE & EXPERTISE)\n"
            "================================================================================\n"
            "Вы — Главный технолог аддитивного производства компании Stereotech (ведущий эксперт\n"
            "по технологиям многоосевой 5D-печати и классической 3D-печати FDM/FFF в среде STE Slicer).\n\n"
            "Ваша миссия: провести полный технологический анализ загруженной 3D-модели, выбрать наилучший\n"
            "режим печати (3D или 5D), оптимизировать пространственную ориентацию детали с учетом действующих\n"
            "механических нагрузок и исключения поддержек, сконфигурировать технологические параметры нарезки\n"
            "и выполнить слайсинг, предоставив пользователю исчерпывающее инженерное обоснование каждого шага.\n\n"
            "Ваш стиль общения: строгий инженерный, терминологически точный, научно обоснованный.\n"
            "Каждое решение базируется на законах механики деформируемого твердого тела, физико-химических\n"
            "свойствах полимеров и кинематических преимуществах пятиосевой аддитивной технологии Stereotech."
        )

    def _render_mandatory_pipeline(self):
        # type: () -> str
        """Section 2: Mandatory MCP tool pipeline."""
        return (
            "================================================================================\n"
            "ОБЯЗАТЕЛЬНЫЙ КОНВЕЙЕР ВЫЗОВОВ MCP-ИНСТРУМЕНТОВ (TOOL PIPELINE)\n"
            "================================================================================\n"
            "Для выполнения задачи вы ОБЯЗАНЫ строго последовательно выполнить полный конвейер\n"
            "вызовов MCP-инструментов. Нарушение порядка вызовов или пропуск этапов СТРОГО ЗАПРЕЩЕНЫ:\n\n"
            "1. analyze_mesh_geometry\n"
            "   - ЦЕЛЬ: Получить точные геометрические характеристики модели из сцены.\n"
            "   - ВЫПОЛНЯЕМЫЕ ДЕЙСТВИЯ: Оценка габаритов (Bounding Box X, Y, Z), объема, площади поверхности,\n"
            "     минимальной толщины стенок, критических углов нависания (> 45-60°), наличия тел вращения\n"
            "     (осесимметричности), трубчатых полостей, консольных выступов и предполагаемых векторов механических нагрузок.\n\n"
            "2. select_print_mode_and_profile\n"
            "   - ЦЕЛЬ: Выбрать режим печати (5D или 3D) и активировать материал в STE Slicer.\n"
            "   - ВЫПОЛНЯЕМЫЕ ДЕЙСТВИЯ: Определение режима (\"5D\" для многоосевой прочности и исключения поддержек,\n"
            "     либо \"3D\" для простых плоских деталей) и выбор точного имени материала из списка доступных в слайсере\n"
            "     (например: \"CFF PA\", \"Generic PETG\", \"Generic PLA\").\n"
            "     Параметр profile опционален (например, \"normal\" или стратегия \"5D_structural\");\n"
            "     если доступных материалов нет, не утверждай, что материал применен — сообщи об этом.\n\n"
            "3. modify_scene_and_parameters\n"
            "   - ЦЕЛЬ: Задать технологические параметры нарезки и зафиксировать ориентацию детали.\n"
            "   - ВЫПОЛНЯЕМЫЕ ДЕЙСТВИЯ: \n"
            "     * ВНИМАНИЕ: Поворот и переворот детали в сцене СТРОГО ЗАПРЕЩЕНЫ. Сохраняй исходную пространственную ориентацию детали, заданную пользователем на столе (всегда передавай rotation_euler_deg=[0.0, 0.0, 0.0] или опусти этот параметр).\n"
            "     * Установка параметров слайсера в объекте print_parameters: layer_height (высота слоя, мм), "
            "wall_line_count (число стенок), infill_sparse_density (процент заполнения, %), "
            "infill_pattern (рисунок заполнения, например 'gyroid', 'grid'), "
            "material_print_temperature (температура сопла, °C), material_bed_temperature (температура стола, °C), "
            "cool_fan_speed (скорость обдува, %).\n"
            "     * supports_enabled: логическое значение (true/false) — отключи поддержки (false) для 5D-печати.\n"
            "   - ВАЖНО: Вызов modify_scene_and_parameters ОБЯЗАТЕЛЕН сразу после select_print_mode_and_profile! "
            "После вызова modify_scene_and_parameters автоматический конвейер инструментов завершён. "
            "Сразу переходи к формулированию полного инженерного отчета пользователю. "
            "НЕ вызывай инструменты генерации G-кода или слайсинга — слайсинг и экспорт запускаются пользователем вручную по кнопке «Экспорт» после ознакомления с твоими рекомендациями."
        )

    def _render_domain_knowledge_rules(self):
        # type: () -> str
        """Section 3: 5D vs 3D rules and orientation under load without supports."""
        kb = self.knowledge_base
        rules_5d = kb.get("mode_selection_rules", {}).get("5D", {})
        rules_3d = kb.get("mode_selection_rules", {}).get("3D", {})
        orient_rules = kb.get("orientation_rules", {})

        criteria_5d = "\n".join("   * {0}".format(c) for c in rules_5d.get("criteria", []))
        criteria_3d = "\n".join("   * {0}".format(c) for c in rules_3d.get("criteria", []))
        load_rules = "\n".join("   * {0}".format(r) for r in orient_rules.get("mechanical_load_alignment", []))
        support_rules = "\n".join("   * {0}".format(r) for r in orient_rules.get("support_free_rules", []))

        return (
            "================================================================================\n"
            "ПРАВИЛА ТЕХНОЛОГИИ STEREOTECH (5D VS 3D, НАГРУЗКИ И ПЕЧАТЬ БЕЗ ПОДДЕРЖЕК)\n"
            "================================================================================\n"
            "1. ВЫБОР РЕЖИМА: 5D Multi-Axis против 3D Planar\n"
            "   Пятиосевая печать (5D) использует 3 линейные оси (X, Y, Z) и 2 поворотные оси наклона и вращения\n"
            "   стола (оси B и C), формируя объемно-ориентированные криволинейные траектории.\n\n"
            "   КРИТЕРИИ ВЫБОРА РЕЖИМА 5D (Пятиосевая печать):\n{criteria_5d}\n\n"
            "   КРИТЕРИИ ВЫБОРА РЕЖИМА 3D (Традиционная печать):\n{criteria_3d}\n\n"
            "2. ОРИЕНТАЦИЯ ДЕТАЛИ ПОД МЕХАНИЧЕСКИЕ НАГРУЗКИ:\n"
            "   Экструдированная полимерная нить обладает анизотропией: прочность на растяжение вдоль волокна\n"
            "   в 2-4 раза превышает прочность межслойного сцепления (по оси Z в 3D печати).\n{load_rules}\n\n"
            "3. ПРИНЦИП ПЕЧАТИ БЕЗ ПОДДЕРЖЕК (SUPPORT-FREE):\n"
            "   Поддержки ухудшают качество поверхности, требуют трудоемкой механической постобработки и расходуют\n"
            "   до 30-50% лишнего материала. В технологии Stereotech 5D поддержки исключаются за счет кинематики:\n{support_rules}"
        ).format(
            criteria_5d=criteria_5d,
            criteria_3d=criteria_3d,
            load_rules=load_rules,
            support_rules=support_rules
        )

    def _render_materials_and_profiles(self, snapshot=None):
        # type: (Optional[Dict[str, Any]]) -> str
        """Section 4: Technical reference for materials and slicing profiles parsed from the slicer."""
        kb = self.knowledge_base
        heuristics = kb.get("parameter_heuristics", {})
        profiles = kb.get("slicing_profiles", {})

        avail_materials = []
        if isinstance(snapshot, dict):
            avail_materials = snapshot.get("available_materials") or []

        mat_lines = []
        if avail_materials:
            for m in avail_materials:
                name = m.get("name", "") if isinstance(m, dict) else str(m)
                t_nozzle = m.get("recommended_temp_nozzle") if isinstance(m, dict) else None
                t_bed = m.get("recommended_temp_bed") if isinstance(m, dict) else None
                fan = m.get("recommended_fan") if isinstance(m, dict) else None
                aliases = m.get("aliases") if isinstance(m, dict) else []

                extra = []
                if t_nozzle:
                    extra.append("сопло: ~{0}°C".format(t_nozzle))
                if t_bed:
                    extra.append("стол: ~{0}°C".format(t_bed))
                if fan is not None:
                    extra.append("обдув: {0}%".format(fan))
                extra_str = (" (" + ", ".join(extra) + ")") if extra else ""

                alias_str = (" [Синонимы: " + ", ".join(aliases) + "]") if aliases else ""
                mat_lines.append("   * \"{0}\"{extra}{aliases}".format(name, extra=extra_str, aliases=alias_str))
        else:
            mat_lines = [
                "   * \"CFF PA\" (сопло: ~265°C, стол: ~70°C, обдув: 0%) [Синонимы: PA6-CF, Carbon Nylon, PA-CF, Угленаполненный полиамид] — ОСНОВНОЙ ВЫБОР ДЛЯ 5D и силовых деталей",
                "   * \"Generic PETG\" (сопло: ~235°C, стол: ~75°C, обдув: 40%) [Синонимы: PETG] — Универсальный прочный материал",
                "   * \"Generic PLA\" (сопло: ~205°C, стол: ~60°C, обдув: 100%) [Синонимы: PLA] — Прототипирование, декоративные детали",
                "   * \"Generic ABS\" (сопло: ~240°C, стол: ~100°C, обдув: 0%) [Синонимы: ABS] — Термостойкие ударопрочные детали",
                "   * \"Generic TPU 95A\" (сопло: ~225°C, стол: ~60°C, обдув: 20%) [Синонимы: TPU, Flex] — Гибкие упругие изделия",
            ]

        prof_lines = []
        for prof_id, p in sorted(profiles.items()):
            prof_lines.append(
                "   * {name} [Режим: {mode}]:\n"
                "     Высота слоя: {lh} мм | Стенки: {walls} шт. | Заполнение: {infill}% ({pattern})\n"
                "     Назначение: {desc}".format(
                    name=p.get("name", prof_id),
                    mode=p.get("mode", "3D"),
                    lh=p.get("layer_height", 0.2),
                    walls=p.get("wall_line_count", 3),
                    infill=p.get("infill_density", 30),
                    pattern=p.get("infill_pattern", "gyroid"),
                    desc=p.get("description", "")
                )
            )

        return (
            "================================================================================\n"
            "СПРАВОЧНИК МАТЕРИАЛОВ И ТЕХНОЛОГИЧЕСКИХ ПАРАМЕТРОВ STE SLICER\n"
            "================================================================================\n"
            "1. ДОСТУПНЫЕ МАТЕРИАЛЫ В STE SLICER:\n"
            "   ВНИМАНИЕ: В select_print_mode_and_profile передавай параметр material СТРОГО\n"
            "   в виде одного из точных имен из списка ниже (например: material='CFF PA' или material='Generic PETG')!\n"
            "{materials_block}\n\n"
            "2. СТРАТЕГИИ ПОДБОРА ПАРАМЕТРОВ (применяются в modify_scene_and_parameters):\n{profiles_block}\n\n"
            "3. ТЕХНОЛОГИЧЕСКИЕ ПРАВИЛА ПОДБОРА ПАРАМЕТРОВ:\n"
            "   * СТЕНКИ (Wall Line Count): {h_walls}\n"
            "   * ПЛОТНОСТЬ И ПАТТЕРН ЗАПОЛНЕНИЯ: {h_infill}\n"
            "   * ПАТТЕРН GYROID: {h_gyroid}\n"
            "   * ОБДУВ (Fan Speed): {h_fan}\n"
            "   * МЕЖСЛОЙНАЯ ТЕМПЕРАТУРНАЯ ДИФФУЗИЯ: {h_temp}"
        ).format(
            materials_block="\n".join(mat_lines),
            profiles_block="\n".join(prof_lines),
            h_walls=heuristics.get("wall_lines", "Не менее 4-5 периметров для силовых конструкций."),
            h_infill=heuristics.get("infill_density", "40-70% для нагруженных деталей, Gyroid/Cubic."),
            h_gyroid=heuristics.get("infill_pattern", "Gyroid обеспечивает изотропную жесткость без наложений."),
            h_fan=heuristics.get("cooling_fan", "0% для полиамидов и композитов во избежание деламинации."),
            h_temp=heuristics.get("temperature_adhesion", "Повышение температуры на 5-10°C улучшает свариваемость слоев.")
        )

    def _render_slicer_snapshot(self, snapshot):
        # type: (Dict[str, Any]) -> str
        """Section 5: Dynamic state of STE Slicer (models, printer, profiles, settings)."""
        printer = snapshot.get("printer") or snapshot.get("machine") or {}
        models = (
            snapshot.get("loaded_models") or
            snapshot.get("models") or
            snapshot.get("scene_objects") or
            []
        )
        # Only list materials actually reported by the running slicer. The
        # knowledge catalog is technical reference, not evidence of installation.
        avail_materials = snapshot.get("available_materials") or snapshot.get("materials") or []
        avail_profiles = (
            snapshot.get("available_profiles") or
            snapshot.get("profiles") or
            list(self.knowledge_base.get("slicing_profiles", {}).keys())
        )
        current_settings = (
            snapshot.get("current_settings") or
            snapshot.get("active_settings") or
            snapshot.get("slicing_parameters") or
            {}
        )

        # 1. Printer representation
        if printer and isinstance(printer, dict):
            p_model = printer.get("model") or printer.get("name") or "Stereotech 520"
            p_kin = printer.get("kinematics") or "5D Multi-Axis (3 Linear + 2 Rotary C/B)"
            p_nozzle = printer.get("nozzle_diameter_mm") or printer.get("nozzle_diameter") or 0.4
            p_vol = printer.get("max_build_volume_mm") or printer.get("build_volume") or "[250, 250, 250]"
            printer_str = "- Модель принтера: {0}\n- Кинематика: {1}\n- Диаметр сопла: {2} мм\n- Рабочий объем: {3} мм".format(
                p_model, p_kin, p_nozzle, p_vol
            )
        else:
            printer_str = "- Модель принтера: Stereotech 520 Multi-Axis 5D/3D (диаметр сопла: 0.4 мм)"

        # 2. Models representation
        if models and isinstance(models, list):
            model_strs = []
            for idx, m in enumerate(models, start=1):
                if isinstance(m, dict):
                    m_name = m.get("name") or ("Model_" + str(idx))
                    dims = m.get("dimensions_mm") or m.get("dimensions") or m.get("size") or [0, 0, 0]
                    pos = m.get("position") or [0, 0, 0]
                    rot = m.get("rotation_deg") or m.get("rotation") or [0, 0, 0]
                    vol = m.get("volume_cm3") or m.get("volume")
                    overhangs = m.get("has_overhangs")
                    max_overhang = m.get("max_overhang_angle_deg")

                    info_parts = [
                        "  * Деталь #{0}: \"{1}\"".format(idx, m_name),
                        "    - Габариты (X, Y, Z): {0} x {1} x {2} мм".format(dims[0], dims[1], dims[2]),
                        "    - Положение в сцене: X={0}, Y={1}, Z={2}".format(pos[0], pos[1], pos[2]),
                        "    - Углы поворота: X={0}°, Y={1}°, Z={2}°".format(rot[0], rot[1], rot[2])
                    ]
                    if vol is not None:
                        info_parts.append("    - Объем модели: {0} см³".format(vol))
                    if overhangs is not None:
                        info_parts.append("    - Наличие нависаний: {0} (макс. угол: {1}°)".format(
                            "Да" if overhangs else "Нет", max_overhang if max_overhang is not None else "Н/Д"
                        ))
                    model_strs.append("\n".join(info_parts))
                else:
                    model_strs.append("  * Деталь #{0}: {1}".format(idx, str(m)))
            models_block = "\n".join(model_strs)
        else:
            models_block = "  (В текущей сцене нет загруженных деталей. Ожидается загрузка 3D-модели пользователем)"

        # 3. Available materials & profiles
        mat_str = ", ".join(m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in avail_materials) if avail_materials else "Generic PETG, Generic PLA, Generic ABS, Generic CFF PA (PA6-CF), Generic TPU 95A"
        prof_str = ", ".join(str(p) for p in avail_profiles) if avail_profiles else "5D_structural, 5D_precision, 3D_standard"

        # 4. Active settings
        if current_settings and isinstance(current_settings, dict):
            settings_lines = []
            for k, v in sorted(current_settings.items()):
                settings_lines.append("  - {0}: {1}".format(k, v))
            settings_block = "\n".join(settings_lines)
        else:
            settings_block = "  - (Используются параметры по умолчанию выбранного профиля)"

        return (
            "================================================================================\n"
            "ТЕКУЩЕЕ СОСТОЯНИЕ СЦЕНЫ И СЛАЙСЕРА (SLICER SNAPSHOT)\n"
            "================================================================================\n"
            "{printer_info}\n\n"
            "ЗАГРУЖЕННЫЕ 3D-МОДЕЛИ В СЦЕНЕ:\n"
            "{models_info}\n\n"
            "ДОСТУПНЫЕ МАТЕРИАЛЫ В ДИСТРИБУТИВЕ:\n"
            "  {materials_list}\n\n"
            "ДОСТУПНЫЕ ПРОФИЛИ СЛАЙСИНГА:\n"
            "  {profiles_list}\n\n"
            "АКТИВНЫЕ ПАРАМЕТРЫ СЛАЙСЕРА:\n"
            "{settings_info}"
        ).format(
            printer_info=printer_str,
            models_info=models_block,
            materials_list=mat_str,
            profiles_list=prof_str,
            settings_info=settings_block
        )

    def _render_final_response_requirements(self):
        # type: () -> str
        """Section 6: Explicit requirements for final technologist response."""
        return (
            "================================================================================\n"
            "ТРЕБОВАНИЯ К ФИНАЛЬНОМУ ОТВЕТУ ГЛАВНОГО ТЕХНОЛОГА (FINAL RESPONSE)\n"
            "================================================================================\n"
            "После того как инструмент run_slicing_and_generate_gcode успешно завершит нарезку модели,\n"
            "вы ОБЯЗАНЫ предоставить пользователю структурированный инженерный отчет, содержащий\n"
            "исчерпывающее техническое обоснование каждого принятого решения:\n\n"
            "1. ОБОСНОВАНИЕ ВЫБОРА РЕЖИМА ПЕЧАТИ (3D vs 5D):\n"
            "   - Детальный ответ, почему для данной детали и условий нагружения выбран режим 5D или 3D.\n"
            "   - Какие физические и механические преимущества это дает (например, непрерывность силовых\n"
            "     волокон, устранение анизотропии по оси Z, прирост прочности до 400%).\n\n"
            "2. ОБОСНОВАНИЕ ПРОСТРАНСТВЕННОЙ ОРИЕНТАЦИИ МОДЕЛИ:\n"
            "   - Почему деталь повернута именно под заданными углами (rx, ry, rz).\n"
            "   - Как ориентация увязывает направление главных механических напряжений с траекториями укладки филамента.\n"
            "   - Как выбранный угол поворота устраняет необходимость использования поддержек (Support-Free)\n"
            "     благодаря наклону стола по поворотной оси B.\n\n"
            "3. ОБОСНОВАНИЕ ТЕХНОЛОГИЧЕСКИХ ПАРАМЕТРОВ СЛАЙСИНГА:\n"
            "   - Температура сопла (print_temperature) и стола (bed_temperature): физико-химическое объяснение\n"
            "     (диффузия расплава, температура стеклования Tg, адгезия первого слоя, предотвращение деламинации).\n"
            "   - Обдув вентилятором (fan_speed): почему задан именно такой процент обдува (0% для предотвращения\n"
            "     усадки и микротрещин в композитах/нейлонах; 100% для застывания мостов в PLA; 30-50% в PETG).\n"
            "   - Количество периметров/стенок (wall_line_count): почему именно столько контуров требуется\n"
            "     для восприятия изгибающих и касательных напряжений в силовой оболочке детали.\n"
            "   - Заполнение (infill_density и infill_pattern): почему выбрана данная плотность и структура\n"
            "     (например, Gyroid для изотропной жесткости при кручении или Cubic для трехмерной прочности).\n"
            "   - Высота слоя (layer_height): баланс между точностью поверхности и монолитностью спекания.\n\n"
            "4. ИТОГИ СЛАЙСИНГА И РЕКОМЕНДАЦИИ ПО ИЗГОТОВЛЕНИЮ:\n"
            "   - Расчетное время печати и расход материала (граммы и метры).\n"
            "   - Технологические рекомендации оператору (предварительная сушка филамента, подготовка поверхности стола,\n"
            "     контроль первого слоя, условия остывания детали)."
        )

    # -----------------------------------------------------------------
    # Helper & Inspection Methods
    # -----------------------------------------------------------------

    def get_knowledge_base(self):
        # type: () -> Dict[str, Any]
        """Returns the loaded domain knowledge base dictionary."""
        return self.knowledge_base

    def get_available_materials(self):
        # type: () -> List[str]
        """Returns the list of material names defined in the knowledge base."""
        return list(self.knowledge_base.get("materials_catalog", {}).keys())

    def get_available_profiles(self):
        # type: () -> List[str]
        """Returns the list of profile names defined in the knowledge base."""
        return list(self.knowledge_base.get("slicing_profiles", {}).keys())

    def reload_knowledge_base(self, path=None):
        # type: (Optional[str]) -> None
        """Reloads the knowledge base from disk or a new path."""
        target_path = path or self.knowledge_base_path
        self.knowledge_base_path = str(target_path)
        self.knowledge_base = self._load_knowledge_base(self.knowledge_base_path)
        logger.info("Knowledge base reloaded from: %s", self.knowledge_base_path)

    # -----------------------------------------------------------------
    # Embedded Default Knowledge Base
    # -----------------------------------------------------------------

    @staticmethod
    def _get_default_knowledge_base():
        # type: () -> Dict[str, Any]
        """Provides a complete default 3D/5D domain knowledge dictionary."""
        return {
            "technology": {
                "name": "Stereotech STE Slicer 5D/3D Multi-Axis Additive Manufacturing",
                "description": "Пятиосевая FDM печать (3 линейные оси X, Y, Z + 2 поворотные оси B и C)."
            },
            "mode_selection_rules": {
                "5D": {
                    "criteria": [
                        "Деталь подвержена сложным пространственным механическим нагрузкам (изгиб, кручение, сдвиг).",
                        "Нависания под углом более 45-60 градусов, где требуется исключить поддержки.",
                        "Тела вращения: шестерни, шкивы, фланцы, крыльчатки, втулки, патрубки.",
                        "Требуется максимальная изотропия и прочность (до +400% по сравнению с 3D)."
                    ]
                },
                "3D": {
                    "criteria": [
                        "Простая призматическая геометрия с плоским основанием.",
                        "Нагрузки действуют строго в плоскости слоев или на сжатие вдоль Z.",
                        "Быстрое прототипирование и макетная печать.",
                        "Габариты превышают поворотный диапазон 5D стола."
                    ]
                }
            },
            "orientation_rules": {
                "mechanical_load_alignment": [
                    "Траектории нитей должны совпадать с линиями главных растягивающих и изгибающих сил.",
                    "В 5D ось вращения детали совмещается с поворотной осью стола C.",
                    "В 3D наиболее нагруженные элементы размещаются горизонтально в плоскости XY."
                ],
                "support_free_rules": [
                    "В 5D наклон стола по оси B сохраняет угол нормали поверхности к соплу близким к 90 градусам (печать без поддержек).",
                    "В 3D наибольшая плоская грань детали укладывается на стол для надежной адгезии."
                ]
            },
            "materials_catalog": {
                "PA6-CF": {
                    "name": "PA6-CF (Полиамид с углеволокном)",
                    "type": "Высокопрочный композит",
                    "nozzle_temp_recommended": 275,
                    "nozzle_temp_range": [260, 290],
                    "bed_temp_recommended": 90,
                    "bed_temp_range": [80, 100],
                    "fan_speed": 0,
                    "tensile_strength_mpa": 110,
                    "density_g_cm3": 1.18,
                    "features": "Экстремальная жесткость, прочность и термостойкость для 5D шестерен."
                },
                "PETG": {
                    "name": "PETG (Полиэтилентерефталат-гликоль)",
                    "type": "Конструкционный термопласт",
                    "nozzle_temp_recommended": 240,
                    "nozzle_temp_range": [230, 250],
                    "bed_temp_recommended": 75,
                    "bed_temp_range": [70, 85],
                    "fan_speed": 40,
                    "tensile_strength_mpa": 55,
                    "density_g_cm3": 1.27,
                    "features": "Высокая межслойная спекаемость, ударопрочность."
                },
                "PLA": {
                    "name": "PLA (Полилиактид)",
                    "type": "Термопласт общего назначения",
                    "nozzle_temp_recommended": 205,
                    "nozzle_temp_range": [190, 220],
                    "bed_temp_recommended": 60,
                    "bed_temp_range": [50, 65],
                    "fan_speed": 100,
                    "tensile_strength_mpa": 50,
                    "density_g_cm3": 1.24,
                    "features": "Минимальная усадка, простота печати."
                },
                "ABS": {
                    "name": "ABS",
                    "type": "Ударопрочный термопласт",
                    "nozzle_temp_recommended": 245,
                    "nozzle_temp_range": [235, 260],
                    "bed_temp_recommended": 100,
                    "bed_temp_range": [95, 110],
                    "fan_speed": 10,
                    "tensile_strength_mpa": 45,
                    "density_g_cm3": 1.05,
                    "features": "Термостойкость до 100°C."
                },
                "TPU": {
                    "name": "TPU / Flex",
                    "type": "Эластомер",
                    "nozzle_temp_recommended": 230,
                    "nozzle_temp_range": [215, 240],
                    "bed_temp_recommended": 45,
                    "bed_temp_range": [30, 60],
                    "fan_speed": 60,
                    "tensile_strength_mpa": 35,
                    "density_g_cm3": 1.21,
                    "features": "Гибкость, гашение вибраций."
                }
            },
            "slicing_profiles": {
                "5D_structural": {
                    "name": "5D Structural",
                    "mode": "5D",
                    "layer_height": 0.2,
                    "wall_line_count": 4,
                    "infill_density": 50,
                    "infill_pattern": "gyroid",
                    "description": "Максимальная пространственная прочность под нагрузки."
                },
                "5D_precision": {
                    "name": "5D Precision",
                    "mode": "5D",
                    "layer_height": 0.16,
                    "wall_line_count": 3,
                    "infill_density": 35,
                    "infill_pattern": "gyroid",
                    "description": "Высокая точность зубчатых зацеплений и патрубков."
                },
                "3D_standard": {
                    "name": "3D Standard",
                    "mode": "3D",
                    "layer_height": 0.2,
                    "wall_line_count": 3,
                    "infill_density": 25,
                    "infill_pattern": "cubic",
                    "description": "Сбалансированное качество и скорость."
                },
                "3D_heavy_duty": {
                    "name": "3D Heavy Duty",
                    "mode": "3D",
                    "layer_height": 0.2,
                    "wall_line_count": 5,
                    "infill_density": 60,
                    "infill_pattern": "gyroid",
                    "description": "Увеличенное количество стенок."
                }
            },
            "parameter_heuristics": {
                "wall_lines": "Стенки несут до 70-80% изгибных нагрузок. Для конструкционных деталей требуется 4-5 периметров.",
                "infill_density": "40-70% для нагруженных деталей, Gyroid/Cubic.",
                "infill_pattern": "Gyroid обеспечивает изотропную жесткость во всех трех направлениях.",
                "cooling_fan": "0% для полиамидов и углекомпозитов (PA, PA-CF) для предотвращения трещин.",
                "temperature_adhesion": "Повышение температуры сопла на 5-10°C улучшает сцепление слоев."
            }
        }
