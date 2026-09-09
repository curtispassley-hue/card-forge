from __future__ import annotations
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import box, Point, Polygon
from shapely.ops import triangulate


def rounded_rect(w: float, h: float, r: float, inset: float = 0.0):
    w2, h2 = w - 2 * inset, h - 2 * inset
    if w2 <= 0 or h2 <= 0:
        raise ValueError("Inset is larger than the rectangle")
    rr = min(r, w2 / 2 - 1e-3, h2 / 2 - 1e-3)
    return box(inset + rr, inset + rr, inset + w2 - rr, inset + h2 - rr).buffer(rr, resolution=24)


def _mesh_merge(meshes):
    meshes = [m for m in meshes if m is not None and len(m.vertices)]
    if not meshes:
        return None
    return meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)


def extrude(poly, z0: float, z1: float):
    """Dependency-light polygon extrusion that handles holes without boolean engines."""
    if poly is None or poly.is_empty or z1 <= z0:
        return None
    geoms = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
    pieces = []

    for geom in geoms:
        if geom.is_empty or geom.area <= 0:
            continue
        verts, faces, lookup = [], [], {}

        def vi(x, y, z):
            key = (round(float(x), 6), round(float(y), 6), round(float(z), 6))
            if key not in lookup:
                lookup[key] = len(verts)
                verts.append([float(x), float(y), float(z)])
            return lookup[key]

        for tri in triangulate(geom):
            # Delaunay triangulation may cover holes; representative point filter keeps only interior faces.
            if not geom.covers(tri):
                continue
            c = list(tri.exterior.coords)[:-1]
            if len(c) != 3:
                continue
            t = [vi(x, y, z1) for x, y in c]
            b = [vi(x, y, z0) for x, y in c]
            faces.append(t)
            faces.append([b[2], b[1], b[0]])

        for ring in [geom.exterior] + list(geom.interiors):
            c = list(ring.coords)
            for i in range(len(c) - 1):
                x1, y1 = c[i]
                x2, y2 = c[i + 1]
                a0 = vi(x1, y1, z0)
                a1 = vi(x2, y2, z0)
                b0 = vi(x1, y1, z1)
                b1 = vi(x2, y2, z1)
                faces.extend(([a0, a1, b1], [a0, b1, b0]))

        if verts and faces:
            pieces.append(trimesh.Trimesh(vertices=np.asarray(verts), faces=np.asarray(faces), process=False))

    mesh = _mesh_merge(pieces)
    if mesh is not None:
        mesh.fix_normals()
    return mesh


def _signed_area2(coords):
    a = 0.0
    for i in range(len(coords)):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % len(coords)]
        a += x1 * y2 - x2 * y1
    return a


def build_nfc_base(geometry, nfc) -> trimesh.Trimesh:
    """Create a single stepped, watertight NFC base mesh.

    The solid is modeled as three top-height zones rather than concatenating
    overlapping closed prisms. This avoids coplanar/internal faces in STL files.
    """
    w, h = geometry.card_width_mm, geometry.card_height_mm
    base_t = float(geometry.base_thickness_mm)
    validate_geometry(geometry, nfc)
    face_depth = float(geometry.face_recess_depth_mm)
    nfc_depth = face_depth + float(nfc.thickness_mm + nfc.clearance_mm)

    outer = rounded_rect(w, h, geometry.corner_radius_mm, inset=0)
    face_pocket = rounded_rect(
        w, h,
        max(0.3, geometry.corner_radius_mm - geometry.face_border_mm),
        inset=geometry.face_border_mm,
    )
    nfc_circle = Point(nfc.x_mm, nfc.y_mm).buffer(
        nfc.diameter_mm / 2 + nfc.clearance_mm / 2,
        resolution=64,
    )
    nfc_region = face_pocket.intersection(nfc_circle)

    floor_z = base_t - nfc_depth
    face_floor_z = base_t - face_depth

    rim_region = outer.difference(face_pocket)
    face_region = face_pocket.difference(nfc_region)

    verts, faces, lookup = [], [], {}

    def vi(x, y, z):
        key = (round(float(x), 6), round(float(y), 6), round(float(z), 6))
        if key not in lookup:
            lookup[key] = len(verts)
            verts.append([float(x), float(y), float(z)])
        return lookup[key]

    def add_horizontal(poly, z, upward=True):
        geoms = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
        for geom in geoms:
            if geom.is_empty or geom.area <= 0:
                continue
            for tri in triangulate(geom):
                if not geom.covers(tri):
                    continue
                c = list(tri.exterior.coords)[:-1]
                if len(c) != 3:
                    continue
                ids = [vi(x, y, z) for x, y in c]
                # Ensure predictable orientation, though watertightness only needs paired edges.
                if _signed_area2(c) < 0:
                    ids = [ids[0], ids[2], ids[1]]
                if upward:
                    faces.append(ids)
                else:
                    faces.append([ids[0], ids[2], ids[1]])

    def add_wall(ring, z_low, z_high):
        c = list(ring.coords)
        for i in range(len(c) - 1):
            x1, y1 = c[i]
            x2, y2 = c[i + 1]
            a0 = vi(x1, y1, z_low)
            a1 = vi(x2, y2, z_low)
            b0 = vi(x1, y1, z_high)
            b1 = vi(x2, y2, z_high)
            faces.append([a0, a1, b1])
            faces.append([a0, b1, b0])

    # Bottom and the three top zones tile the full card footprint exactly.
    add_horizontal(outer, 0.0, upward=False)
    add_horizontal(rim_region, base_t, upward=True)
    add_horizontal(face_region, face_floor_z, upward=True)
    if not nfc_region.is_empty:
        add_horizontal(nfc_region, floor_z, upward=True)

    # Vertical boundaries between height zones.
    add_wall(outer.exterior, 0.0, base_t)
    add_wall(face_pocket.exterior, face_floor_z, base_t)
    if not nfc_region.is_empty:
        # If the NFC circle is fully inside the face pocket, this is exactly the circular step.
        geoms = list(nfc_region.geoms) if hasattr(nfc_region, "geoms") else [nfc_region]
        for geom in geoms:
            add_wall(geom.exterior, floor_z, face_floor_z)

    mesh = trimesh.Trimesh(
        vertices=np.asarray(verts, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        process=True,
    )
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    return mesh


def export_base_stl(path: str | Path, geometry, nfc) -> Path:
    mesh = build_nfc_base(geometry, nfc)
    if mesh is None:
        raise RuntimeError("Base mesh generation failed")
    path = Path(path)
    mesh.export(path, file_type="stl")
    return path


def face_target_dimensions(geometry) -> tuple[float, float]:
    border = geometry.face_border_mm + geometry.face_clearance_mm
    return geometry.card_width_mm - 2 * border, geometry.card_height_mm - 2 * border


def make_face_blank(geometry, thickness_mm: float) -> trimesh.Trimesh:
    """Thin rectangular face carrier matching the base recess; useful when HueForge output isn't imported yet."""
    fw, fh = face_target_dimensions(geometry)
    r = max(0.25, geometry.corner_radius_mm - geometry.face_border_mm - geometry.face_clearance_mm)
    poly = rounded_rect(fw, fh, r, inset=0)
    return extrude(poly, 0.0, thickness_mm)


def import_hueforge_models(folder_or_file: str | Path) -> list[trimesh.Trimesh]:
    """Import FlatForge/HueForge STL or 3MF geometry.

    3MF may contain multiple volumes; each volume is returned as a separate mesh.
    """
    p = Path(folder_or_file)
    if p.is_file():
        files = [p]
    else:
        files = sorted(list(p.glob("*.stl")) + list(p.glob("*.3mf")))

    result = []
    for f in files:
        try:
            loaded = trimesh.load(f, process=False, force="scene")
            if isinstance(loaded, trimesh.Trimesh):
                meshes = [loaded]
            elif isinstance(loaded, trimesh.Scene):
                meshes = []
                for node in loaded.graph.nodes_geometry:
                    transform, name = loaded.graph[node]
                    m = loaded.geometry[name].copy()
                    m.apply_transform(transform)
                    meshes.append(m)
            else:
                meshes = []

            for idx, m in enumerate(meshes, start=1):
                if len(m.vertices):
                    suffix = f"#{idx}" if len(meshes) > 1 else ""
                    m.metadata["source_name"] = f.name + suffix
                    result.append(m)
        except Exception:
            continue
    return result


# Backwards-compatible name used by 0.2 projects.
def import_hueforge_stls(folder_or_file: str | Path) -> list[trimesh.Trimesh]:
    return import_hueforge_models(folder_or_file)


def normalize_face_meshes(meshes: list[trimesh.Trimesh], geometry) -> list[trimesh.Trimesh]:
    """Scale imported HueForge/FlatForge STLs in XY to the face recess while preserving Z/layer heights."""
    if not meshes:
        return []
    combined = trimesh.util.concatenate([m.copy() for m in meshes])
    minv, maxv = combined.bounds
    sx = maxv[0] - minv[0]
    sy = maxv[1] - minv[1]
    if sx <= 0 or sy <= 0:
        return []
    tw, th = face_target_dimensions(geometry)
    scale = min(tw / sx, th / sy)
    out = []
    for m in meshes:
        c = m.copy()
        c.apply_translation([-minv[0], -minv[1], -minv[2]])
        mat = np.eye(4)
        mat[0, 0] = scale
        mat[1, 1] = scale
        # IMPORTANT: never scale Z; HueForge color blending depends on exact layer heights.
        c.apply_transform(mat)
        out.append(c)
    return out


def validate_geometry(g, n):
    values = [g.card_width_mm, g.card_height_mm, g.corner_radius_mm,
              g.base_thickness_mm, g.face_recess_depth_mm, g.face_border_mm,
              g.face_clearance_mm, n.diameter_mm, n.thickness_mm,
              n.clearance_mm, n.x_mm, n.y_mm]
    if not np.isfinite(values).all():
        raise ValueError("Dimensions must be finite numbers.")
    if min(g.card_width_mm, g.card_height_mm, g.base_thickness_mm,
           g.face_recess_depth_mm, g.face_border_mm, n.diameter_mm, n.thickness_mm) <= 0:
        raise ValueError("Card, recess, border and tag dimensions must be positive.")
    if min(g.corner_radius_mm, g.face_clearance_mm, n.clearance_mm) < 0:
        raise ValueError("Radius and clearances cannot be negative.")
    if min(face_target_dimensions(g)) <= 0:
        raise ValueError("Border and clearance leave no space for the face.")
    floor = g.base_thickness_mm - g.face_recess_depth_mm - n.thickness_mm - n.clearance_mm
    if floor < 0.35 - 1e-8:
        raise ValueError(f"Only {floor:.2f} mm remains below the NFC pocket; increase base thickness (minimum floor 0.35 mm).")
    pocket = rounded_rect(g.card_width_mm, g.card_height_mm,
                          max(0.3, g.corner_radius_mm - g.face_border_mm), g.face_border_mm)
    tag = Point(n.x_mm, n.y_mm).buffer((n.diameter_mm + n.clearance_mm) / 2, resolution=64)
    if not pocket.contains(tag) or pocket.boundary.distance(tag) < 0.1:
        raise ValueError("NFC pocket must fit completely inside the face recess with at least 0.1 mm separation.")
