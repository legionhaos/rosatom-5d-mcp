# -*- coding: utf-8 -*-
"""
STE Slicer Plugin — Geometry Analysis Tool (MCP).

Модуль анализа геометрии 3D-сетки в среде STE Slicer / Cura 3.6 / Uranium.
Вычисляет габариты, объем (метод знаковых тетраэдров), центр масс, свесы
и производит многокритериальную оценку ориентаций для 3D и 5D печати.

Zero-Dependency: использует только стандартную библиотеку Python, numpy,
модули Uranium (UM.*) и Cura (cura.*).
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import math
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Безопасный импорт контракта MCP и диспетчера
try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        """Резервный базовый класс инструмента MCP."""
        name = ""
        description = ""
        parameters_schema = {}  # type: Dict[str, Any]

        def execute(self, **kwargs):
            # type: (**Any) -> Dict[str, Any]
            raise NotImplementedError

try:
    from utils.exceptions import STEPluginError, MeshError, SceneError, format_exception_for_llm
except (ImportError, AttributeError):
    class STEPluginError(Exception):
        """Базовое исключение плагина STE Slicer."""
        def __init__(self, message, code="STE_PLUGIN_ERROR", details=None):
            super(STEPluginError, self).__init__(message)
            self.code = code
            self.details = details or {}
            self.message = message

    class MeshError(STEPluginError):
        def __init__(self, message, details=None):
            super(MeshError, self).__init__(message, code="MESH_ERROR", details=details)

    class SceneError(STEPluginError):
        def __init__(self, message, details=None):
            super(SceneError, self).__init__(message, code="SCENE_ERROR", details=details)

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
        """Диспетчер выполнения задач в основном потоке GUI Cura/Qt."""
        @staticmethod
        def run_sync(func, *args, **kwargs):
            try:
                import threading
                from cura.CuraApplication import CuraApplication
                app = CuraApplication.getInstance()
                if app and threading.current_thread() is not threading.main_thread():
                    result_box = [None]
                    error_box = [None]
                    event = threading.Event()

                    def _wrapper():
                        try:
                            result_box[0] = func(*args, **kwargs)
                        except Exception as e:
                            error_box[0] = e
                        finally:
                            event.set()

                    app.callLater(_wrapper)
                    event.wait(timeout=30.0)
                    if error_box[0] is not None:
                        raise error_box[0]
                    return result_box[0]
            except (ImportError, AttributeError):
                pass
            return func(*args, **kwargs)


class GeometryAnalysisTool(BaseMCPTool):
    """
    Инструмент анализа геометрических параметров 3D-модели и оценки
    стратегий печати 3D (планарная) vs 5D (многоосевая).
    """

    name = "analyze_mesh_geometry"
    description = (
        "Вычисление геометрических характеристик 3D-сетки (габариты, объем, "
        "центр масс, свесы) и оценка оптимальных ориентаций для 3D и 5D печати."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Абсолютный путь к файлу модели (STL, OBJ, 3MF) для загрузки на сцену."
            },
            "node_id": {
                "type": "string",
                "description": "Идентификатор или имя существующего объекта на сцене (SceneNode)."
            },
            "overhang_threshold_deg": {
                "type": "number",
                "description": "Критический угол нависания от горизонтали в градусах (по умолчанию 45.0).",
                "default": 45.0
            }
        },
        "required": []
    }

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        """
        Основной метод выполнения анализа геометрии.

        :param file_path: Опциональный путь к файлу.
        :param node_id: Опциональный ID ноды на сцене.
        :param overhang_threshold_deg: Пороговый угол свеса.
        :return: Словарь с результатами расчета и инженерными рекомендациями.
        """
        try:
            file_path = kwargs.get("file_path")
            node_id = kwargs.get("node_id")
            overhang_threshold_deg = float(kwargs.get("overhang_threshold_deg", 45.0))

            # 1. Извлечение геометрии и метаданных ноды целиком в главном потоке GUI
            mesh_data_bundle = MainThreadDispatcher.run_sync(
                self._resolve_and_extract_geometry, file_path, node_id
            )
            triangles, orig_normals, resolved_id, resolved_name = mesh_data_bundle

            if triangles is None or len(triangles) == 0:
                raise MeshError("Сетка объекта пуста или не содержит полигонов.")

            # 2. Векторизованные расчеты базовых характеристик
            bounding_box = self._compute_bounding_box(triangles)
            volume_mm3 = self._compute_signed_volume(triangles)
            center_of_mass = self._compute_center_of_mass(triangles)
            surface_area_mm2 = self._compute_surface_area(triangles)

            # 3. Анализ ориентаций для выбора 3D/5D
            candidates = self._evaluate_orientation_candidates(
                triangles,
                center_of_mass,
                overhang_threshold_deg
            )

            # Определение наилучшей ориентации
            best_candidate = candidates[0] if candidates else None

            # Сводка флагов
            requires_supports = best_candidate["requires_supports_in_3d"] if best_candidate else False
            is_5d_beneficial = best_candidate["is_5d_beneficial"] if best_candidate else False
            recommended_mode = best_candidate["recommended_mode"] if best_candidate else "3D"

            return {
                "status": "SUCCESS",
                "node_id": resolved_id,
                "node_name": resolved_name,
                "geometry_metrics": {
                    "bounding_box_mm": bounding_box,
                    "volume_mm3": round(volume_mm3, 3),
                    "surface_area_mm2": round(surface_area_mm2, 3),
                    "center_of_mass_mm": [
                        round(center_of_mass[0], 3),
                        round(center_of_mass[1], 3),
                        round(center_of_mass[2], 3)
                    ],
                    "triangles_count": int(len(triangles))
                },
                "overhang_evaluation": {
                    "overhang_threshold_deg": overhang_threshold_deg,
                    "requires_supports_in_3d": requires_supports,
                    "is_5d_beneficial": is_5d_beneficial,
                    "recommended_mode": recommended_mode
                },
                "best_orientation": best_candidate,
                "orientation_candidates": candidates
            }

        except STEPluginError as exc:
            return format_exception_for_llm(exc)
        except Exception as exc:
            return format_exception_for_llm(exc)

    # ----------------------------------------------------------------------
    #  Вспомогательные методы работы со сценой Cura/Uranium (GUI thread)
    # ----------------------------------------------------------------------

    def _resolve_and_extract_geometry(self, file_path=None, node_id=None):
        """
        Атомарное получение ноды, извлечение вершин и нормалей в главном потоке.
        Возвращает (triangles, normals, node_id_str, node_name_str).
        """
        node = self._resolve_scene_node(file_path, node_id)
        if node is None:
            raise SceneError(
                "Не удалось обнаружить или загрузить 3D-объект на сцену.",
                details={"file_path": file_path, "node_id": node_id}
            )

        resolved_id = str(getattr(node, "getId", lambda: getattr(node, "getName", lambda: "unknown"))())
        resolved_name = str(getattr(node, "getName", lambda: "Unnamed_Mesh")())

        triangles, normals = self._extract_mesh_triangles(node)
        return triangles, normals, resolved_id, resolved_name

    def _resolve_scene_node(self, file_path=None, node_id=None):
        """Поиск существующей ноды или чтение файла через MeshFileHandler."""
        from cura.CuraApplication import CuraApplication
        app = CuraApplication.getInstance()
        if not app:
            raise SceneError("Инстанс CuraApplication недоступен.")

        controller = app.getController()
        if not controller:
            raise SceneError("Контроллер сцены Cura недоступен.")
        scene = controller.getScene()
        if not scene:
            raise SceneError("Сцена Cura недоступна.")

        # Поиск по node_id или имени
        if node_id:
            node = self._find_node_by_id(scene.getRoot(), str(node_id))
            if node:
                return node

        # Загрузка через MeshFileHandler при наличии пути
        if file_path:
            if not os.path.exists(file_path):
                raise MeshError("Файл не найден по указанному пути: {}".format(file_path))

            mesh_file_handler = app.getMeshFileHandler()
            if not mesh_file_handler:
                raise SceneError("MeshFileHandler недоступен в текущей конфигурации приложения.")

            loaded = mesh_file_handler.read(file_path)
            if loaded:
                if isinstance(loaded, list) and len(loaded) > 0:
                    return loaded[0]
                return loaded

            children = [c for c in scene.getRoot().getAllChildren() if hasattr(c, "getMeshData") and c.getMeshData()]
            if children:
                return children[-1]

        # Иначе берем первую ноду с MeshData
        return self._find_first_mesh_node(scene.getRoot())

    def _find_node_by_id(self, parent_node, target_id):
        """Рекурсивный обход дерева нод сцены."""
        if str(getattr(parent_node, "getId", lambda: "")()) == target_id:
            return parent_node
        if str(getattr(parent_node, "getName", lambda: "")()) == target_id:
            return parent_node

        for child in parent_node.getAllChildren():
            found = self._find_node_by_id(child, target_id)
            if found:
                return found
        return None

    def _find_first_mesh_node(self, parent_node):
        """Поиск первой ноды с геометрическими данными MeshData."""
        for child in parent_node.getAllChildren():
            mesh_data = getattr(child, "getMeshData", lambda: None)()
            if mesh_data is not None and getattr(mesh_data, "getVertices", lambda: None)() is not None:
                return child
        return None

    def _extract_mesh_triangles(self, node):
        # type: (Any) -> Tuple[np.ndarray, np.ndarray]
        """
        Извлекает вершины и строит массив треугольников (M, 3, 3) в системе координат 3D-печати.

        Безопасно обрабатывает:
        - одномерный (flat) или двумерный массив вершин через .reshape((-1, 3))
        - одномерный или срезанный массив индексов граней
        - вырожденные нормали граней без RuntimeWarning деления на 0
        """
        mesh_data = node.getMeshData()
        if mesh_data is None:
            raise MeshError("SceneNode не содержит MeshData.")

        verts_raw = mesh_data.getVertices()
        if verts_raw is None or len(verts_raw) == 0:
            raise MeshError("MeshData объекта не содержит вершин.")

        # Гарантируем форму (N, 3) даже если getVertices() вернул одномерный плоский буфер (N*3,)
        vertices = np.asarray(verts_raw, dtype=np.float64).reshape((-1, 3))

        # Применяем мировую матрицу трансформации ноды при наличии
        world_transform = getattr(node, "getWorldTransformation", lambda: None)()
        if world_transform is not None and hasattr(world_transform, "getData"):
            mat4 = np.asarray(world_transform.getData(), dtype=np.float64).reshape((4, 4))
            homo_verts = np.hstack([vertices, np.ones((vertices.shape[0], 1), dtype=np.float64)])
            vertices = np.dot(homo_verts, mat4.T)[:, :3]

        # Конвертация осей Uranium (X, Y_up, Z_depth) -> 3D-печать (X, Y_depth, Z_height)
        vertices_print = np.zeros_like(vertices)
        vertices_print[:, 0] = vertices[:, 0]  # X_u -> X_p
        vertices_print[:, 1] = vertices[:, 2]  # Z_u -> Y_p (глубина)
        vertices_print[:, 2] = vertices[:, 1]  # Y_u -> Z_p (высота нарезки)

        # Формирование треугольников
        indices = mesh_data.getIndices()
        if indices is not None and len(indices) > 0:
            indices_flat = np.asarray(indices, dtype=np.int32).ravel()
            num_faces = len(indices_flat) // 3
            faces = indices_flat[:num_faces * 3].reshape(num_faces, 3)
            triangles = vertices_print[faces]  # Shape: (M, 3, 3)
        else:
            num_triangles = len(vertices_print) // 3
            triangles = vertices_print[:num_triangles * 3].reshape(num_triangles, 3, 3)

        # Вычисление нормалей граней с защитой от деления на 0
        e1 = triangles[:, 1, :] - triangles[:, 0, :]
        e2 = triangles[:, 2, :] - triangles[:, 0, :]
        cross_prod = np.cross(e1, e2)
        norm = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        safe_norm = np.where(norm > 1e-12, norm, 1.0)
        normals = np.where(norm > 1e-12, cross_prod / safe_norm, np.array([0.0, 0.0, 1.0]))

        return triangles, normals

    # ----------------------------------------------------------------------
    #  Векторизованные математические вычисления
    # ----------------------------------------------------------------------

    @staticmethod
    def _compute_bounding_box(triangles):
        # type: (np.ndarray) -> Dict[str, float]
        """Вычисление габаритов (dx, dy, dz) ориентированного меша в мм."""
        pts = triangles.reshape(-1, 3)
        min_p = np.min(pts, axis=0)
        max_p = np.max(pts, axis=0)
        dimensions = max_p - min_p
        return {
            "dx": round(float(dimensions[0]), 3),
            "dy": round(float(dimensions[1]), 3),
            "dz": round(float(dimensions[2]), 3),
            "min_z": round(float(min_p[2]), 3),
            "max_z": round(float(max_p[2]), 3)
        }

    @staticmethod
    def _compute_surface_area(triangles):
        # type: (np.ndarray) -> float
        """Суммарная площадь поверхности сетки."""
        e1 = triangles[:, 1, :] - triangles[:, 0, :]
        e2 = triangles[:, 2, :] - triangles[:, 0, :]
        cross_prod = np.cross(e1, e2)
        areas = 0.5 * np.linalg.norm(cross_prod, axis=1)
        return float(np.sum(areas))

    @staticmethod
    def _compute_signed_volume(triangles):
        # type: (np.ndarray) -> float
        """
        Точный объем закрытой 3D-сетки методом знаковых тетраэдров:
        V = 1/6 * |sum(v0 . (v1 x v2))|
        """
        v0 = triangles[:, 0, :]
        v1 = triangles[:, 1, :]
        v2 = triangles[:, 2, :]
        cross_v1_v2 = np.cross(v1, v2)
        signed_vols = np.einsum("ij,ij->i", v0, cross_v1_v2) / 6.0
        total_volume = float(np.abs(np.sum(signed_vols)))
        return total_volume

    @staticmethod
    def _compute_center_of_mass(triangles):
        # type: (np.ndarray) -> np.ndarray
        """
        Расчет центра масс сплошного тела на основе знаковых тетраэдров.
        Центроид тетраэдра: c = (v0 + v1 + v2) / 4.
        """
        v0 = triangles[:, 0, :]
        v1 = triangles[:, 1, :]
        v2 = triangles[:, 2, :]
        cross_v1_v2 = np.cross(v1, v2)
        signed_vols = np.einsum("ij,ij->i", v0, cross_v1_v2) / 6.0
        total_vol = np.sum(signed_vols)

        if abs(total_vol) < 1e-9:
            pts = triangles.reshape(-1, 3)
            return np.mean(pts, axis=0)

        centroids = (v0 + v1 + v2) / 4.0
        weighted_centroids = centroids * signed_vols[:, np.newaxis]
        com = np.sum(weighted_centroids, axis=0) / total_vol
        return com

    @staticmethod
    def _build_rotation_matrix(rx_deg, ry_deg, rz_deg):
        # type: (float, float, float) -> np.ndarray
        """Построение 3D матрицы поворота по углам Эйлера (X -> Y -> Z) в пространстве печати."""
        rad_x = math.radians(rx_deg)
        rad_y = math.radians(ry_deg)
        rad_z = math.radians(rz_deg)

        cx, sx = math.cos(rad_x), math.sin(rad_x)
        cy, sy = math.cos(rad_y), math.sin(rad_y)
        cz, sz = math.cos(rad_z), math.sin(rad_z)

        rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
        ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
        rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)

        return np.dot(rz, np.dot(ry, rx))

    # ----------------------------------------------------------------------
    #  Оценка ориентаций и триггеры 3D / 5D
    # ----------------------------------------------------------------------

    def _evaluate_orientation_candidates(self, triangles, orig_com, overhang_threshold_deg):
        # type: (np.ndarray, np.ndarray, float) -> List[Dict[str, Any]]
        """
        Векторизованная оценка пространственных ориентаций детали.
        Включает 6 ортогональных положений и диагональные углы 45°.
        """
        orientations_to_test = [
            {"label": "Оригинальная (исходная)", "rotation": [0.0, 0.0, 0.0]},
            {"label": "Поворот +90° по оси X", "rotation": [90.0, 0.0, 0.0]},
            {"label": "Поворот -90° по оси X", "rotation": [-90.0, 0.0, 0.0]},
            {"label": "Поворот +90° по оси Y", "rotation": [0.0, 90.0, 0.0]},
            {"label": "Поворот -90° по оси Y", "rotation": [0.0, -90.0, 0.0]},
            {"label": "Переворот 180° по оси X", "rotation": [180.0, 0.0, 0.0]},
            {"label": "Диагональ X 45°", "rotation": [45.0, 0.0, 0.0]},
            {"label": "Диагональ Y 45°", "rotation": [0.0, 45.0, 0.0]},
            {"label": "Диагональ X 45° / Y 45°", "rotation": [45.0, 45.0, 0.0]}
        ]

        e1 = triangles[:, 1, :] - triangles[:, 0, :]
        e2 = triangles[:, 2, :] - triangles[:, 0, :]
        cross_prod = np.cross(e1, e2)
        face_areas = 0.5 * np.linalg.norm(cross_prod, axis=1)
        total_surface_area = max(float(np.sum(face_areas)), 1e-6)

        results = []

        for candidate in orientations_to_test:
            rx, ry, rz = candidate["rotation"]
            rot_mat = self._build_rotation_matrix(rx, ry, rz)

            # Векторизованный поворот всех треугольников: (M, 3, 3)
            rot_triangles = np.einsum("ij,mkj->mki", rot_mat, triangles)

            # Векторизованные нормали с защитой от деления на 0
            rot_cross = np.cross(
                rot_triangles[:, 1, :] - rot_triangles[:, 0, :],
                rot_triangles[:, 2, :] - rot_triangles[:, 0, :]
            )
            norm = np.linalg.norm(rot_cross, axis=1, keepdims=True)
            safe_norm = np.where(norm > 1e-12, norm, 1.0)
            rot_normals = np.where(norm > 1e-12, rot_cross / safe_norm, np.array([0.0, 0.0, 1.0]))

            # Центр масс в повернутой системе
            rot_com = np.dot(rot_mat, orig_com)

            # Z-границы
            all_z = rot_triangles[:, :, 2]
            z_min = float(np.min(all_z))
            z_max = float(np.max(all_z))
            part_height = max(z_max - z_min, 1e-6)

            # Площадь контакта первого слоя: в пределах 0.20 мм от стола с нормалью строго вниз (< -0.85)
            centroids_z = np.mean(all_z, axis=1)
            is_near_bed = centroids_z <= (z_min + 0.20)
            is_facing_down = rot_normals[:, 2] < -0.85
            contact_mask = np.logical_and(is_near_bed, is_facing_down)
            contact_area_mm2 = float(np.sum(face_areas[contact_mask]))

            # Анализ свесов: нормали с отрицательной Z-составляющей (за исключением контакта со столом)
            nz = rot_normals[:, 2]
            downward_mask = nz < -1e-4
            overhang_eligible_mask = np.logical_and(downward_mask, ~contact_mask)

            overhang_angles_deg = np.zeros(len(nz), dtype=np.float64)
            if np.any(overhang_eligible_mask):
                clamped_nz = np.clip(-nz[overhang_eligible_mask], 0.0, 1.0)
                overhang_angles_deg[overhang_eligible_mask] = np.degrees(np.arcsin(clamped_nz))

            critical_overhang_mask = overhang_angles_deg > overhang_threshold_deg
            overhang_area_mm2 = float(np.sum(face_areas[critical_overhang_mask]))
            overhang_percentage = (overhang_area_mm2 / total_surface_area) * 100.0

            # Высота центра масс над столом
            com_height_above_bed = float(rot_com[2] - z_min)

            # Флаги принятия решений
            requires_supports_3d = overhang_percentage > 3.0
            is_5d_beneficial = (overhang_percentage > 12.0) or (
                overhang_percentage > 5.0 and com_height_above_bed > (0.5 * part_height)
            )

            rec_mode = "5D" if is_5d_beneficial else "3D"

            notes = []
            if overhang_percentage > 15.0:
                notes.append(
                    "Критическая доля свесов ({:.1f}% площади > {:.0f}°). "
                    "В 3D-режиме потребуется значительный объем поддержек. "
                    "Рекомендуется 5D-печать (наращивание без поддержек под углом).".format(
                        overhang_percentage, overhang_threshold_deg
                    )
                )
            elif overhang_percentage > 3.0:
                notes.append(
                    "Умеренное количество свесов ({:.1f}%). Возможна 3D-печать с базовыми "
                    "поддержками либо 5D для исключения постобработки.".format(overhang_percentage)
                )
            else:
                notes.append(
                    "Минимальные свесы ({:.1f}%). Идеально подходит для стандартного 3D-слайсинга.".format(
                        overhang_percentage
                    )
                )

            if contact_area_mm2 < 15.0:
                notes.append(
                    "Внимание: малая площадь контакта со столом ({:.1f} мм²). "
                    "Высокий риск отрыва детали — требуется кайма (Brim) или рафт.".format(contact_area_mm2)
                )
            else:
                notes.append(
                    "Надежная площадь контакта с платформой ({:.1f} мм²).".format(contact_area_mm2)
                )

            results.append({
                "label": candidate["label"],
                "rotation_euler_deg": [rx, ry, rz],
                "first_layer_contact_area_mm2": round(contact_area_mm2, 2),
                "overhang_area_mm2": round(overhang_area_mm2, 2),
                "overhang_percentage": round(overhang_percentage, 2),
                "center_of_mass_height_mm": round(com_height_above_bed, 2),
                "part_height_mm": round(part_height, 2),
                "requires_supports_in_3d": requires_supports_3d,
                "is_5d_beneficial": is_5d_beneficial,
                "recommended_mode": rec_mode,
                "engineering_note": " ".join(notes)
            })

        # Сортировка: минимизация площади свесов, максимизация опорной площади первого слоя
        results.sort(key=lambda item: (item["overhang_percentage"], -item["first_layer_contact_area_mm2"]))
        return results
