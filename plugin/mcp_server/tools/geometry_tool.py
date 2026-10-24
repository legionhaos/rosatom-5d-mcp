# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import math
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    from plugin.mcp_server.server import BaseMCPTool
except (ImportError, AttributeError):
    class BaseMCPTool(object):
        """Fallback base class for MCP tools."""
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
        """Base exception for STE Slicer plugin."""
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
        """Main thread GUI dispatcher for Cura/Qt."""
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
    """MCP tool for mesh geometry analysis and 3D/5D print orientation assessment."""

    name = "analyze_mesh_geometry"
    description = (
        "Calculates 3D mesh geometry metrics (bounding box, volume, center of mass, "
        "overhangs) and evaluates optimal orientations for 3D and 5D printing."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the 3D model file (STL, OBJ, 3MF) to load onto the scene."
            },
            "node_id": {
                "type": "string",
                "description": "Identifier or name of an existing SceneNode on the scene."
            },
            "overhang_threshold_deg": {
                "type": "number",
                "description": "Critical overhang angle threshold in degrees from horizontal (default 45.0).",
                "default": 45.0
            }
        },
        "required": []
    }

    def execute(self, **kwargs):
        # type: (**Any) -> Dict[str, Any]
        """Execute geometric analysis and print strategy recommendation."""
        try:
            file_path = kwargs.get("file_path")
            node_id = kwargs.get("node_id")
            overhang_threshold_deg = float(kwargs.get("overhang_threshold_deg", 45.0))

            mesh_data_bundle = MainThreadDispatcher.run_sync(
                self._resolve_and_extract_geometry, file_path, node_id
            )
            triangles, orig_normals, resolved_id, resolved_name = mesh_data_bundle

            if triangles is None or len(triangles) == 0:
                raise MeshError("Mesh contains no geometry or vertices.")

            bounding_box = self._compute_bounding_box(triangles)
            volume_mm3 = self._compute_signed_volume(triangles)
            center_of_mass = self._compute_center_of_mass(triangles)
            surface_area_mm2 = self._compute_surface_area(triangles)

            candidates = self._evaluate_orientation_candidates(
                triangles,
                center_of_mass,
                overhang_threshold_deg
            )

            best_candidate = candidates[0] if candidates else None

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

    def _resolve_and_extract_geometry(self, file_path=None, node_id=None):
        """Extract node vertices and normals in the GUI thread."""
        node = self._resolve_scene_node(file_path, node_id)
        if node is None:
            raise SceneError(
                "Failed to find or load 3D object on scene.",
                details={"file_path": file_path, "node_id": node_id}
            )

        resolved_id = str(getattr(node, "getId", lambda: getattr(node, "getName", lambda: "unknown"))())
        resolved_name = str(getattr(node, "getName", lambda: "Unnamed_Mesh")())

        triangles, normals = self._extract_mesh_triangles(node)
        return triangles, normals, resolved_id, resolved_name

    def _resolve_scene_node(self, file_path=None, node_id=None):
        """Find existing scene node or load model file via MeshFileHandler."""
        from cura.CuraApplication import CuraApplication
        app = CuraApplication.getInstance()
        if not app:
            raise SceneError("CuraApplication instance is unavailable.")

        controller = app.getController()
        if not controller:
            raise SceneError("Cura scene controller is unavailable.")
        scene = controller.getScene()
        if not scene:
            raise SceneError("Cura scene is unavailable.")

        if node_id:
            node = self._find_node_by_id(scene.getRoot(), str(node_id))
            if node:
                return node

        if file_path:
            if not os.path.exists(file_path):
                raise MeshError("File not found at specified path: {}".format(file_path))

            mesh_file_handler = app.getMeshFileHandler()
            if not mesh_file_handler:
                raise SceneError("MeshFileHandler is unavailable.")

            loaded = mesh_file_handler.read(file_path)
            if loaded:
                if isinstance(loaded, list) and len(loaded) > 0:
                    return loaded[0]
                return loaded

            children = [c for c in scene.getRoot().getAllChildren() if hasattr(c, "getMeshData") and c.getMeshData()]
            if children:
                return children[-1]

        return self._find_first_mesh_node(scene.getRoot())

    def _find_node_by_id(self, parent_node, target_id):
        """Recursive traversal to find SceneNode by ID or name."""
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
        """Find first child node containing valid MeshData."""
        for child in parent_node.getAllChildren():
            mesh_data = getattr(child, "getMeshData", lambda: None)()
            if mesh_data is not None and getattr(mesh_data, "getVertices", lambda: None)() is not None:
                return child
        return None

    def _extract_mesh_triangles(self, node):
        # type: (Any) -> Tuple[np.ndarray, np.ndarray]
        """Extract and transform mesh vertices to print coordinate space."""
        mesh_data = node.getMeshData()
        if mesh_data is None:
            raise MeshError("SceneNode contains no MeshData.")

        verts_raw = mesh_data.getVertices()
        if verts_raw is None or len(verts_raw) == 0:
            raise MeshError("MeshData contains no vertices.")

        vertices = np.asarray(verts_raw, dtype=np.float64).reshape((-1, 3))

        world_transform = getattr(node, "getWorldTransformation", lambda: None)()
        if world_transform is not None and hasattr(world_transform, "getData"):
            mat4 = np.asarray(world_transform.getData(), dtype=np.float64).reshape((4, 4))
            homo_verts = np.hstack([vertices, np.ones((vertices.shape[0], 1), dtype=np.float64)])
            vertices = np.dot(homo_verts, mat4.T)[:, :3]

        vertices_print = np.zeros_like(vertices)
        vertices_print[:, 0] = vertices[:, 0]
        vertices_print[:, 1] = vertices[:, 2]
        vertices_print[:, 2] = vertices[:, 1]

        indices = mesh_data.getIndices()
        if indices is not None and len(indices) > 0:
            indices_flat = np.asarray(indices, dtype=np.int32).ravel()
            num_faces = len(indices_flat) // 3
            faces = indices_flat[:num_faces * 3].reshape(num_faces, 3)
            triangles = vertices_print[faces]
        else:
            num_triangles = len(vertices_print) // 3
            triangles = vertices_print[:num_triangles * 3].reshape(num_triangles, 3, 3)

        e1 = triangles[:, 1, :] - triangles[:, 0, :]
        e2 = triangles[:, 2, :] - triangles[:, 0, :]
        cross_prod = np.cross(e1, e2)
        norm = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        safe_norm = np.where(norm > 1e-12, norm, 1.0)
        normals = np.where(norm > 1e-12, cross_prod / safe_norm, np.array([0.0, 0.0, 1.0]))

        return triangles, normals

    @staticmethod
    def _compute_bounding_box(triangles):
        # type: (np.ndarray) -> Dict[str, float]
        """Calculate axis-aligned bounding box dimensions in mm."""
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
        """Calculate total surface area of triangles in mm2."""
        e1 = triangles[:, 1, :] - triangles[:, 0, :]
        e2 = triangles[:, 2, :] - triangles[:, 0, :]
        cross_prod = np.cross(e1, e2)
        areas = 0.5 * np.linalg.norm(cross_prod, axis=1)
        return float(np.sum(areas))

    @staticmethod
    def _compute_signed_volume(triangles):
        # type: (np.ndarray) -> float
        """Calculate closed mesh volume using the signed tetrahedron method."""
        v0 = triangles[:, 0, :]
        v1 = triangles[:, 1, :]
        v2 = triangles[:, 2, :]
        cross_v1_v2 = np.cross(v1, v2)
        signed_vols = np.einsum("ij,ij->i", v0, cross_v1_v2) / 6.0
        return float(np.abs(np.sum(signed_vols)))

    @staticmethod
    def _compute_center_of_mass(triangles):
        # type: (np.ndarray) -> np.ndarray
        """Calculate solid center of mass based on signed tetrahedra."""
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
        return np.sum(weighted_centroids, axis=0) / total_vol

    @staticmethod
    def _build_rotation_matrix(rx_deg, ry_deg, rz_deg):
        # type: (float, float, float) -> np.ndarray
        """Construct 3D rotation matrix for Euler angles (X -> Y -> Z)."""
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

    def _evaluate_orientation_candidates(self, triangles, orig_com, overhang_threshold_deg):
        # type: (np.ndarray, np.ndarray, float) -> List[Dict[str, Any]]
        """Vectorized evaluation of discrete spatial orientation candidates."""
        orientations_to_test = [
            {"label": "Original", "rotation": [0.0, 0.0, 0.0]},
            {"label": "Rotate +90 X", "rotation": [90.0, 0.0, 0.0]},
            {"label": "Rotate -90 X", "rotation": [-90.0, 0.0, 0.0]},
            {"label": "Rotate +90 Y", "rotation": [0.0, 90.0, 0.0]},
            {"label": "Rotate -90 Y", "rotation": [0.0, -90.0, 0.0]},
            {"label": "Invert 180 X", "rotation": [180.0, 0.0, 0.0]},
            {"label": "Diagonal 45 X", "rotation": [45.0, 0.0, 0.0]},
            {"label": "Diagonal 45 Y", "rotation": [0.0, 45.0, 0.0]},
            {"label": "Diagonal 45 X / 45 Y", "rotation": [45.0, 45.0, 0.0]}
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

            rot_triangles = np.einsum("ij,mkj->mki", rot_mat, triangles)

            rot_cross = np.cross(
                rot_triangles[:, 1, :] - rot_triangles[:, 0, :],
                rot_triangles[:, 2, :] - rot_triangles[:, 0, :]
            )
            norm = np.linalg.norm(rot_cross, axis=1, keepdims=True)
            safe_norm = np.where(norm > 1e-12, norm, 1.0)
            rot_normals = np.where(norm > 1e-12, rot_cross / safe_norm, np.array([0.0, 0.0, 1.0]))

            rot_com = np.dot(rot_mat, orig_com)

            all_z = rot_triangles[:, :, 2]
            z_min = float(np.min(all_z))
            z_max = float(np.max(all_z))
            part_height = max(z_max - z_min, 1e-6)

            centroids_z = np.mean(all_z, axis=1)
            is_near_bed = centroids_z <= (z_min + 0.20)
            is_facing_down = rot_normals[:, 2] < -0.85
            contact_mask = np.logical_and(is_near_bed, is_facing_down)
            contact_area_mm2 = float(np.sum(face_areas[contact_mask]))

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

            com_height_above_bed = float(rot_com[2] - z_min)

            requires_supports_3d = overhang_percentage > 3.0
            is_5d_beneficial = (overhang_percentage > 12.0) or (
                overhang_percentage > 5.0 and com_height_above_bed > (0.5 * part_height)
            )

            rec_mode = "5D" if is_5d_beneficial else "3D"

            notes = []
            if overhang_percentage > 15.0:
                notes.append("Critical overhangs: {:.1f}% area. 5D printing recommended.".format(overhang_percentage))
            elif overhang_percentage > 3.0:
                notes.append("Moderate overhangs: {:.1f}% area.".format(overhang_percentage))
            else:
                notes.append("Minimal overhangs: {:.1f}% area. Optimal for planar 3D slicing.".format(overhang_percentage))

            if contact_area_mm2 < 15.0:
                notes.append("Low bed contact area: {:.1f} mm2. Adhesion helper recommended.".format(contact_area_mm2))
            else:
                notes.append("Stable bed contact area: {:.1f} mm2.".format(contact_area_mm2))

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

        results.sort(key=lambda item: (item["overhang_percentage"], -item["first_layer_contact_area_mm2"]))
        return results
