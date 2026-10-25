# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import traceback
from typing import Any, Dict, Optional

try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        name = ""
        description = ""
        parameters_schema = {}  # type: Dict[str, Any]

        def execute(self, **kwargs):
            # type: (**Any) -> Dict[str, Any]
            raise NotImplementedError

try:
    from utils.exceptions import (
        STEPluginError,
        SceneError,
        ProfileNotFoundError,
        format_exception_for_llm,
    )
except (ImportError, AttributeError):
    class STEPluginError(Exception):
        def __init__(self, message, code="STE_PLUGIN_ERROR", details=None):
            super(STEPluginError, self).__init__(message)
            self.code = code
            self.details = details or {}
            self.message = message

    class SceneError(STEPluginError):
        def __init__(self, message, details=None):
            super(SceneError, self).__init__(message, code="SCENE_ERROR", details=details)

    class ProfileNotFoundError(STEPluginError):
        def __init__(self, message, details=None):
            super(ProfileNotFoundError, self).__init__(message, code="PROFILE_NOT_FOUND", details=details)

    def format_exception_for_llm(exc):
        # type: (BaseException) -> Dict[str, Any]
        return {
            "status": "ERROR",
            "error_code": getattr(exc, "code", type(exc).__name__),
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "traceback": traceback.format_exc(),
        }

try:
    from plugin.slicer_bridge.main_thread_dispatcher import MainThreadDispatcher
except (ImportError, AttributeError):
    class MainThreadDispatcher(object):
        @staticmethod
        def run_sync(func, *args, **kwargs):
            return func(*args, **kwargs)


_DOMAIN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "domain_knowledge_3d5d.json"
)


class ProfileModeTool(BaseMCPTool):

    name = "select_print_mode_and_profile"
    description = (
        "Выбор режима печати (5D Multi-Axis или 3D Planar), активация материала "
        "филамента и базового профиля качества в STE Slicer на основе базы знаний Stereotech."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["5D", "3D"],
                "description": "Режим печати: '5D' (многоосевая) или '3D' (планарная трехосевая)."
            },
            "material": {
                "type": "string",
                "description": "Имя материала из STE Slicer. Поддерживаются точные имена и алиасы: PA6-CF = Carbon Nylon = Carbon Fiber Nylon; также PLA, PETG, ABS, TPU, PA12, ASA."
            },
            "profile": {
                "type": "string",
                "description": "Опциональное имя профиля качества для активации."
            }
        },
        "required": ["mode"]
    }

    def __init__(self, settings_mgr=None):
        # type: (Any) -> None
        self._settings_mgr = settings_mgr
        self._domain = self._load_domain_knowledge()

    def _load_domain_knowledge(self):
        # type: () -> Dict[str, Any]
        try:
            import io
            with io.open(_DOMAIN_FILE, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _resolve_application(self):
        # type: () -> Any
        app = None
        for mod_name in ("steslicer.SteSlicerApplication", "UM.Application", "cura.CuraApplication"):
            try:
                mod = __import__(mod_name, fromlist=["SteSlicerApplication", "Application", "CuraApplication"])
                for attr in ("SteSlicerApplication", "Application", "CuraApplication"):
                    cls_ = getattr(mod, attr, None)
                    if cls_ and hasattr(cls_, "getInstance"):
                        inst = cls_.getInstance()
                        if inst:
                            app = inst
                            break
                if app:
                    break
            except Exception:
                pass
        if app is None:
            try:
                import sys
                for mod_name in ("steslicer.SteSlicerApplication", "UM.Application", "cura.CuraApplication"):
                    if mod_name in sys.modules:
                        mod = sys.modules[mod_name]
                        for attr in ("SteSlicerApplication", "Application", "CuraApplication"):
                            cls_ = getattr(mod, attr, None)
                            if cls_ and hasattr(cls_, "getInstance"):
                                inst = cls_.getInstance()
                                if inst:
                                    app = inst
                                    break
                    if app:
                        break
            except Exception:
                pass
        return app

    def _recommend_mode(self, features=None, part_role=None, support_preference=None):
        # type: (Optional[list], Optional[str], Optional[str]) -> tuple
        feats = set(features or [])
        if "rotational" in feats or part_role == "structural" or support_preference == "avoid":
            return ("5D", "Режим 5D Multi-Axis выбран на основе анализа геометрии и требований к прочности.")
        if ("simple_prismatic" in feats or "flat_base" in feats) and (part_role == "prototype" or support_preference == "acceptable"):
            return ("3D", "Режим 3D Planar выбран: деталь призматическая с плоским основанием.")
        if not feats and not part_role and not support_preference:
            return (None, "Недостаточно данных для выбора режима. Пожалуйста, укажите режим (3D или 5D) или опишите деталь.")
        return (None, "Пожалуйста, укажите требуемый режим печати (3D или 5D).")

    def _match_material_profiles(self, material_name):
        # type: (str) -> list
        app = self._resolve_application()
        if not app:
            return []
        registry = self._get_container_registry(app)
        if not registry:
            return []
        return self._find_material_containers(app, None, material_name)

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        try:
            mode = kwargs.get("mode")
            material = kwargs.get("material")
            profile = kwargs.get("profile")
            available_materials = kwargs.get("available_materials")

            if mode == "AUTO" or not mode:
                rec_mode, reason = self._recommend_mode(
                    kwargs.get("features"),
                    kwargs.get("part_role"),
                    kwargs.get("support_preference")
                )
                if not rec_mode:
                    return {
                        "status": "NEEDS_CLARIFICATION",
                        "mode": None,
                        "applied_material": None,
                        "applied_profile": None,
                        "material_spec": None,
                        "warnings": [reason],
                        "error": reason
                    }
                mode = rec_mode

            if mode not in ("5D", "3D"):
                raise STEPluginError(
                    "Недопустимый режим печати '{0}'. Разрешены '5D' или '3D'.".format(mode)
                )

            if available_materials is not None and material:
                req_norm = self._normalize_material_name(material)
                matched = False
                for item in available_materials:
                    item_name = item.get("name", "") if isinstance(item, dict) else str(item)
                    item_id = item.get("id", "") if isinstance(item, dict) else ""
                    item_mat = item.get("material", "") if isinstance(item, dict) else ""
                    if (req_norm == self._normalize_material_name(item_name) or
                        (item_id and req_norm == self._normalize_material_name(item_id)) or
                        (item_mat and req_norm == self._normalize_material_name(item_mat))):
                        matched = True
                        break
                if not matched:
                    return {
                        "status": "NEEDS_CLARIFICATION",
                        "mode": mode,
                        "applied_material": None,
                        "applied_profile": None,
                        "material_spec": None,
                        "warnings": ["Материал '{0}' недоступен в текущей конфигурации.".format(material)],
                        "error": "Материал '{0}' недоступен.".format(material)
                    }

            result = MainThreadDispatcher.run_sync(
                self._apply_mode_and_profile, mode, material, profile
            )

            material_spec = self._lookup_material_spec(material) if material else None
            mode_spec = self._lookup_mode_spec(mode)

            warnings = result.get("warnings", [])
            material_not_applied = bool(material and not result.get("applied_material"))
            profile_not_applied = bool(profile and not result.get("applied_profile"))
            mode_ok = result.get("mode_ok", True)

            response = {
                "status": "ERROR" if (material_not_applied or profile_not_applied or not mode_ok) else "SUCCESS",
                "mode": mode,
                "applied_material": result.get("applied_material"),
                "applied_profile": result.get("applied_profile"),
                "material_spec": material_spec if result.get("applied_material") else None,
                "warnings": warnings,
                "error": "; ".join(warnings) if (material_not_applied or profile_not_applied or not mode_ok) else ""
            }
            return response
        except Exception as exc:
            return format_exception_for_llm(exc)

    def _lookup_mode_spec(self, mode):
        # type: (str) -> Dict[str, Any]
        rules = self._domain.get("mode_selection_rules", {})
        return rules.get(mode, {})

    def _lookup_material_spec(self, material):
        # type: (str) -> Optional[Dict[str, Any]]
        catalog = self._domain.get("materials_catalog", {})
        if not material:
            return None
        if material in catalog:
            return catalog[material]
        upper = material.upper()
        for key, spec in catalog.items():
            if key.upper() == upper:
                return spec
        norm = self._normalize_material_name(material)
        if norm == "pa6-cf":
            return catalog.get("PA6-CF")
        for key, spec in catalog.items():
            if self._normalize_material_name(key) == norm:
                return spec
        mat_profiles = self._domain.get("material_profiles", {})
        for key, spec in mat_profiles.items():
            if isinstance(spec, dict):
                sname = str(spec.get("name", "")).lower()
                smat = str(spec.get("material", "")).lower()
                if material.lower() in sname or material.lower() in smat:
                    return spec
        return None

    def _apply_mode_and_profile(self, mode, material, profile):
        # type: (str, Optional[str], Optional[str]) -> Dict[str, Any]
        warnings = []
        app = self._resolve_application()
        if not app:
            raise SceneError("CuraApplication не инициализировано.")

        global_stack = app.getGlobalContainerStack()
        if not global_stack:
            raise SceneError("Отсутствует активный принтер / GlobalStack.")

        mode_ok = self._set_print_mode(global_stack, mode, warnings)

        applied_material = None
        if material:
            applied_material = self._activate_material(app, global_stack, material, warnings)

        applied_profile = None
        if profile:
            applied_profile = self._activate_quality_profile(app, global_stack, profile, warnings)

        return {
            "applied_material": applied_material,
            "applied_profile": applied_profile,
            "warnings": warnings,
            "mode_ok": mode_ok
        }

    def _set_print_mode(self, global_stack, mode, warnings):
        # type: (Any, str, list) -> bool
        user_container = self._get_user_changes_container(global_stack)
        if user_container is None:
            warnings.append("Не найден контейнер userChanges GlobalStack для записи режима печати.")
            return False

        try:
            user_container.setProperty("ste_print_mode", "value", mode)
            if hasattr(global_stack, "propertyChanged"):
                global_stack.propertyChanged.emit("ste_print_mode", "value")
        except Exception as exc:
            warnings.append("Не удалось записать ste_print_mode='{0}': {1}".format(mode, exc))

        try:
            val = "classic" if mode == "3D" else "cylindrical_full"
            user_container.setProperty("printing_mode", "value", val)
            if hasattr(global_stack, "propertyChanged"):
                global_stack.propertyChanged.emit("printing_mode", "value")
        except Exception:
            pass

        try:
            confirmed_ste = global_stack.getProperty("ste_print_mode", "value")
        except Exception:
            confirmed_ste = None
        try:
            confirmed_pr = global_stack.getProperty("printing_mode", "value")
        except Exception:
            confirmed_pr = None

        expected_pr = "cylindrical_full" if mode == "5D" else "classic"
        if confirmed_ste == mode or confirmed_pr == expected_pr:
            return True

        warnings.append("Режим печати '{0}' не подтвердился в свойствах стека.".format(mode))
        return False

    def _activate_material(self, app, global_stack, material, warnings):
        # type: (Any, Any, str, list) -> Optional[str]
        machine_manager = self._get_machine_manager(app)

        containers = self._find_material_containers(app, global_stack, material)
        if not containers:
            raise ProfileNotFoundError(
                "Материал '{0}' не найден в библиотеке материалов STE Slicer.".format(material),
                details={"requested_material": material}
            )

        target_container = containers[0]
        container_id = str(getattr(target_container, "getId", lambda: "")())

        if machine_manager is not None and hasattr(machine_manager, "setMaterial") and hasattr(target_container, "getContainer"):
            try:
                extruder = self._get_extruder_stack(global_stack)
                position = str(getattr(extruder, "getMetaDataEntry", lambda k, d=None: "0")("position", "0"))
                machine_manager.setMaterial(position, target_container)
                return str(getattr(target_container, "getName", lambda: container_id)())
            except Exception:
                pass

        extruder = self._get_extruder_stack(global_stack)
        if extruder is not None and hasattr(extruder, "material"):
            try:
                extruder.material = target_container
                return str(getattr(target_container, "getName", lambda: container_id)())
            except Exception as exc:
                warnings.append("Прямое назначение material в ExtruderStack не удалось: {0}".format(exc))

        warnings.append("Не удалось активировать материал '{0}'.".format(material))
        return None

    def _activate_quality_profile(self, app, global_stack, profile, warnings):
        # type: (Any, Any, str, list) -> Optional[str]
        machine_manager = self._get_machine_manager(app)

        quality_container = self._find_quality_container(app, global_stack, profile)
        if quality_container is None:
            # Check if this is a known conceptual preset (e.g. 5D_structural, 3D_standard)
            conceptual_profiles = self._domain.get("slicing_profiles", {})
            if profile in conceptual_profiles or any(k.lower() == str(profile).lower() for k in conceptual_profiles):
                # Ensure a base quality profile (like 'normal') is active in the stack
                for base_name in ("normal", "draft", "fast"):
                    base_container = self._find_quality_container(app, global_stack, base_name)
                    if base_container:
                        try:
                            if machine_manager is not None and hasattr(machine_manager, "setQualityGroup"):
                                machine_manager.setQualityGroup(base_container)
                            elif global_stack is not None and hasattr(global_stack, "quality"):
                                global_stack.quality = base_container
                        except Exception:
                            pass
                        break
                # Accept conceptual profile preset successfully
                return profile

            warnings.append("Профиль качества '{0}' не найден в библиотеке слайсера, оставлен текущий.".format(profile))
            return None

        qid = str(getattr(quality_container, "getId", lambda: "")())

        if machine_manager is not None and hasattr(machine_manager, "setQualityGroup"):
            try:
                machine_manager.setQualityGroup(quality_container)
                return str(getattr(quality_container, "getName", lambda: qid)())
            except Exception:
                pass

        if global_stack is not None and hasattr(global_stack, "quality"):
            try:
                global_stack.quality = quality_container
                return str(getattr(quality_container, "getName", lambda: qid)())
            except Exception as exc:
                warnings.append("Назначение профиля качества не удалось: {0}".format(exc))

        return str(getattr(quality_container, "getName", lambda: qid)())

    def _get_machine_manager(self, app):
        # type: (Any) -> Any
        getter = getattr(app, "getMachineManager", None)
        if getter is not None:
            try:
                return getter()
            except Exception:
                return None
        return getattr(app, "machineManager", None)

    def _get_extruder_stack(self, global_stack):
        # type: (Any) -> Any
        extruders = getattr(global_stack, "extruders", None)
        if extruders:
            if isinstance(extruders, dict) and len(extruders) > 0:
                return extruders.get("0") or next(iter(extruders.values()))
            if isinstance(extruders, (list, tuple)) and len(extruders) > 0:
                return extruders[0]
        return None

    def _find_material_containers(self, app, global_stack, material):
        # type: (Any, Any, str) -> list
        registry = self._get_container_registry(app)
        if registry is None:
            return []

        candidates = []
        finders = []
        if hasattr(registry, "findInstanceContainers"):
            finders.append(registry.findInstanceContainers)
        if hasattr(registry, "findContainers"):
            finders.append(registry.findContainers)

        for finder in finders:
            for query in ({"type": "material", "name": material},
                          {"type": "material", "id": material},
                          {"type": "material", "material": material}):
                try:
                    found = finder(**query)
                except Exception:
                    found = None
                if found:
                    candidates.extend(found)
            if candidates:
                return candidates

        # Search metadata for lazy-loaded materials in Uranium/STE Slicer
        meta_finders = []
        if hasattr(registry, "findInstanceContainersMetadata"):
            meta_finders.append(registry.findInstanceContainersMetadata)
        if hasattr(registry, "findContainersMetadata"):
            meta_finders.append(registry.findContainersMetadata)

        all_metadata = []
        for mfinder in meta_finders:
            try:
                md_list = mfinder(type="material") or []
                if md_list:
                    all_metadata.extend(md_list)
                    break
            except Exception:
                pass

        matched_id = None
        requested = self._normalize_material_name(material)
        for md in all_metadata:
            if not isinstance(md, dict):
                continue
            name = str(md.get("name") or "")
            cid = str(md.get("id") or "")
            mat_type = str(md.get("material") or "")
            norm_name = self._normalize_material_name(name)
            norm_id = self._normalize_material_name(cid)
            norm_mat = self._normalize_material_name(mat_type)

            if requested in (norm_name, norm_id, norm_mat):
                matched_id = cid
                break
            if (norm_name and (requested in norm_name or norm_name in requested)) or \
               (norm_mat and (requested in norm_mat or norm_mat in requested)) or \
               (norm_id and (requested in norm_id or norm_id in requested)):
                matched_id = cid
                break

        if matched_id:
            for finder in finders:
                try:
                    found = finder(id=matched_id)
                    if found:
                        return found
                except Exception:
                    pass
            # Try base file ID if matched_id contains machine suffix
            if "_" in matched_id:
                parts = matched_id.split("_")
                for sub_len in (2, 1):
                    base_id = "_".join(parts[:sub_len])
                    for finder in finders:
                        try:
                            found = finder(id=base_id)
                            if found:
                                return found
                        except Exception:
                            pass

        if not candidates:
            for finder in finders:
                try:
                    all_materials = finder(type="material")
                except Exception:
                    all_materials = []
                requested = self._normalize_material_name(material)
                for cont in all_materials or []:
                    name = str(getattr(cont, "getName", lambda: "")())
                    cid = str(getattr(cont, "getId", lambda: "")())
                    mat_entry = str(getattr(cont, "getMetaDataEntry", lambda k, d=None: "")("material", "") or "")
                    cand_name = self._normalize_material_name(name)
                    cand_id = self._normalize_material_name(cid)
                    cand_mat = self._normalize_material_name(mat_entry)
                    if requested in (cand_name, cand_id, cand_mat) or \
                       (cand_name and (requested in cand_name or cand_name in requested)) or \
                       (cand_mat and (requested in cand_mat or cand_mat in requested)) or \
                       (cand_id and (requested in cand_id or cand_id in requested)):
                        candidates.append(cont)
                if candidates:
                    break

        return candidates

    @staticmethod
    def _normalize_material_name(value):
        """Normalize aliases and vendor naming before matching material containers."""
        text = str(value or "").lower().replace("_", " ").replace("-", " ")
        # Map all carbon-fiber nylon aliases to pa6-cf
        for alias in (
            "generic cff pa", "generic cffpa", "generic carbon nylon",
            "carbon fiber nylon", "carbon-fiber nylon", "carbon nylon",
            "polyamide 6 cf", "polyamide6 cf", "pa6 cf", "pa 6 cf",
            "pa6cf", "pa cf", "pa-cf", "pacf", "cff pa", "cffpa", "cff"
        ):
            text = text.replace(alias, "pa6-cf")
        text = text.replace(" ", "")
        return "".join(ch for ch in text if ch.isalnum() or ch == "-")

    def _find_quality_container(self, app, global_stack, profile):
        # type: (Any, Any, str) -> Any
        registry = self._get_container_registry(app)
        if registry is None:
            return None

        finders = []
        if hasattr(registry, "findInstanceContainers"):
            finders.append(registry.findInstanceContainers)
        if hasattr(registry, "findContainers"):
            finders.append(registry.findContainers)

        for finder in finders:
            for query in ({"type": "quality", "name": profile},
                          {"type": "quality", "id": profile},
                          {"type": "quality_changes", "name": profile}):
                try:
                    found = finder(**query)
                except Exception:
                    found = None
                if found:
                    return found[0]
        return None

    def _get_container_registry(self, app):
        # type: (Any) -> Any
        getter = getattr(app, "getContainerRegistry", None)
        if getter is not None:
            try:
                return getter()
            except Exception:
                pass
        try:
            from UM.Settings.ContainerRegistry import ContainerRegistry
            return ContainerRegistry.getInstance()
        except Exception:
            return None

    def _get_user_changes_container(self, stack):
        # type: (Any) -> Any
        if hasattr(stack, "userChanges") and stack.userChanges is not None:
            return stack.userChanges
        if hasattr(stack, "userChangesContainer") and stack.userChangesContainer is not None:
            return stack.userChangesContainer
        if hasattr(stack, "getContainerCount") and hasattr(stack, "getContainer"):
            for idx in range(stack.getContainerCount()):
                container = stack.getContainer(idx)
                if not container:
                    continue
                cid = str(getattr(container, "getId", lambda: "")()).lower()
                meta_type = str(getattr(container, "getMetaDataEntry", lambda k: "")("type")).lower()
                if "user" in cid or meta_type == "user":
                    return container
        if hasattr(stack, "getTop"):
            return stack.getTop()
        return None


__all__ = ["ProfileModeTool"]


ProfileAndModeTool = ProfileModeTool
__all__ = ["ProfileModeTool", "ProfileAndModeTool"]
