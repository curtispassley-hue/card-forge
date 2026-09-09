from __future__ import annotations
from pathlib import Path
import json
from PIL import Image, ImageDraw
from .image_processing import nearest_palette_preview
from .geometry import face_target_dimensions, import_hueforge_models, normalize_face_meshes


def export_hueforge_package(image: Image.Image, project, output_dir: str | Path) -> Path:
    """Create a HueForge handoff folder with full-color art and physical metadata."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    source_path = out / "CardForge_HueForge_Source.png"
    preview_path = out / "CardForge_4Filament_Preview.png"
    guide_path = out / "CardForge_NFC_Guide.png"
    metadata_path = out / "CardForge_HueForge_Handoff.json"
    readme_path = out / "README_HUEFORGE.txt"

    image.save(source_path)
    nearest_palette_preview(image, project.hueforge.palette).save(preview_path)

    guide = image.copy().convert("RGB")
    d = ImageDraw.Draw(guide)
    x = int(round(project.nfc.x_mm / project.geometry.card_width_mm * guide.width))
    y = int(round((1 - project.nfc.y_mm / project.geometry.card_height_mm) * guide.height))
    r = int(round(project.nfc.diameter_mm / project.geometry.card_width_mm * guide.width / 2))
    d.ellipse((x-r, y-r, x+r, y+r), outline="white", width=max(2, guide.width // 600))
    d.text((10, 10), "NFC placement guide only - use the separate source image in HueForge", fill="white")
    guide.save(guide_path)

    fw, fh = face_target_dimensions(project.geometry)
    meta = {
        "cardforge_version": "0.4.0",
        "workflow": "CardForge -> HueForge/FlatForge -> CardForge assembly",
        "face_down": bool(project.hueforge.face_down),
        "finished_card_mm": [project.geometry.card_width_mm, project.geometry.card_height_mm],
        "target_face_insert_mm": [fw, fh],
        "target_face_thickness_mm": project.hueforge.face_target_thickness_mm,
        "transparent_cap_mm": project.hueforge.transparent_cap_mm,
        "four_filaments": [
            {"slot": i+1, "name": project.hueforge.filament_names[i], "display_color": project.hueforge.palette[i]}
            for i in range(4)
        ],
        "nfc": {
            "preset": project.nfc.preset_name,
            "diameter_mm": project.nfc.diameter_mm,
            "thickness_mm": project.nfc.thickness_mm,
            "x_mm": project.nfc.x_mm,
            "y_mm": project.nfc.y_mm,
        },
        "critical_note": "Preserve Z/layer heights from HueForge. CardForge normalizes imported geometry only in X/Y."
    }
    metadata_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    readme_path.write_text(
        "CARDFORGE -> HUEFORGE / FLATFORGE HANDOFF\n\n"
        "1. Open CardForge_HueForge_Source.png in HueForge.\n"
        "2. Configure the same four actual filaments shown in CardForge_HueForge_Handoff.json.\n"
        "3. Tune HueForge optical blending / transmission settings.\n"
        "4. For the face-down workflow, export the aligned FlatForge STL set, or a supported multi-volume 3MF.\n"
        "5. Back in CardForge, import the STL folder or 3MF.\n"
        "6. CardForge preserves Z and only normalizes XY to the face insert footprint.\n"
        "7. Print the face face-down, print the NFC base separately, then fit or glue the face into the recess.\n\n"
        "CardForge_4Filament_Preview.png is only a nearest-color preview. HueForge is the authoritative optical-blending stage.\n",
        encoding="utf-8"
    )
    return out


def import_hueforge_path(path: str | Path, project):
    meshes = import_hueforge_models(path)
    return normalize_face_meshes(meshes, project.geometry)


def import_flatforge_folder(folder: str | Path, project):
    # Compatibility wrapper.
    return import_hueforge_path(folder, project)
