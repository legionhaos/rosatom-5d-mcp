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
                "description": "Имя материала филамента (PLA, PETG, ABS, TPU, PA6-CF и т.д.)."
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
            with open(_DOMAIN_FILE, "r") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        try:
            mode = kwargs.get("mode")
            material = kwargs.get("material")
            profile = kwargs.get("profile")

            if mode not in ("5D", "3D"):
                raise STEPluginError(
                    "Недопустимый режим печати '{0}'. Разрешены '5D' или '3D'.".format(mode)
                )

            result = MainThreadDispatcher.run_sync(
                self._apply_mode_and_profile, mode, material, profile
            )

            material_spec = self._lookup_material_spec(material) if material else None
            mode_spec = self._lookup_mode_spec(mode)

            response = {
                "status": "SUCCESS",
                "mode": mode,
                "mode_info": mode_spec,
                "applied_material": result.get("applied_material"),
                "applied_profile": result.get("applied_profile"),
                "material_spec": material_spec,
                "warnings": result.get("warnings", [])
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
        return None

    def _apply_mode_and_profile(self, mode, material, profile):
        # type: (str, Optional[str], Optional[str]) -> Dict[str, Any]
        from cura.CuraApplication import CuraApplication

        warnings = []
        app = CuraApplication.getInstance()
        if not app:
            raise SceneError("CuraApplication не инициализировано.")

        global_stack = app.getGlobalContainerStack()
        if not global_stack:
            raise SceneError("Отсутствует активный принтер / GlobalStack.")

        self._set_print_mode(global_stack, mode, warnings)

        applied_material = None
        if material:
            applied_material = self._activate_material(app, global_stack, material, warnings)

        applied_profile = None
        if profile:
            applied_profile = self._activate_quality_profile(app, global_stack, profile, warnings)

        return {
            "applied_material": applied_material,
            "applied_profile": applied_profile,
            "warnings": warnings
        }

    def _set_print_mode(self, global_stack, mode, warnings):
        # type: (Any, str, list) -> None
        try:
            definition = global_stack.getProperty("ste_print_mode", "value")
        except Exception:
            definition = None

        user_container = self._get_user_changes_container(global_stack)
        if user_container is None:
            warnings.append("Не найден контейнер userChanges GlobalStack для записи режима печати.")
            return

        try:
            user_container.setProperty("ste_print_mode", "value", mode)
            if hasattr(global_stack, "propertyChanged"):
                global_stack.propertyChanged.emit("ste_print_mode", "value")
        except Exception as exc:
            warnings.append("Не удалось записать ste_print_mode='{0}': {1}".format(mode, exc))

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

        if machine_manager is not None and hasattr(machine_manager, "setMaterial"):
            try:
                extruder = self._get_extruder_stack(global_stack)
                position = str(getattr(extruder, "getMetaDataEntry", lambda k, d=None: "0")("position", "0"))
                machine_manager.setMaterial(position, target_container)
                return str(getattr(target_container, "getName", lambda: container_id)())
            except Exception as exc:
                warnings.append("MachineManager.setMaterial завершился ошибкой: {0}".format(exc))

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
            warnings.append("Профиль качества '{0}' не найден, пропущен.".format(profile))
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

        return None

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
                break

        if not candidates:
            for finder in finders:
                try:
                    all_materials = finder(type="material")
                except Exception:
                    all_materials = []
                upper = material.upper()
                for cont in all_materials or []:
                    name = str(getattr(cont, "getName", lambda: "")()).upper()
                    cid = str(getattr(cont, "getId", lambda: "")()).upper()
                    if upper in name or upper in cid:
                        candidates.append(cont)
                if candidates:
                    break

        return candidates

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
