from pathlib import Path
import tempfile
import numpy as np
from PIL import Image, ImageDraw
import trimesh

from cardforge.core.project import Project, TextLayer
from cardforge.core.geometry import export_base_stl, make_face_blank, import_hueforge_models, normalize_face_meshes
from cardforge.core.hueforge import export_hueforge_package
from cardforge.core.image_processing import auto_correct_file, manual_correct_file, compose_editable_layers
from cardforge.core.ocr import OCRCandidate, remove_ocr_text, candidates_to_text_layers, backend_status
from cardforge.core.logo import extract_logo, remove_logo_region, suggest_logo_regions


def main():
    td = Path(tempfile.mkdtemp(prefix="cardforge_test_"))

    # Synthetic photographed card with visible perspective.
    photo = Image.new("RGB", (1300, 900), "#454545")
    d = ImageDraw.Draw(photo)
    quad = [(190, 180), (1110, 130), (1160, 690), (150, 750)]
    d.polygon(quad, fill="white")
    d.rectangle((290, 255, 620, 350), fill="#e6e6e6")
    d.text((300, 300), "CARDFORGE 4D", fill="black")
    d.text((300, 380), "FACE DOWN + NFC", fill="#bb2222")
    d.rectangle((860, 260, 1030, 420), fill="#cf3326")
    src = td / "photo.png"
    photo.save(src)

    corrected = td / "auto.png"
    auto_correct_file(src, corrected)
    assert corrected.exists() and corrected.stat().st_size > 0

    manual = td / "manual.png"
    manual_correct_file(src, manual, quad)
    mimg = Image.open(manual)
    ratio = mimg.width / mimg.height
    assert abs(ratio - (88.9/50.8)) < 0.01

    p = Project(name="Smoke Test", source_image=str(src), corrected_image=str(manual))
    p.texts.append(TextLayer(text="Editable Name", x_mm=35, y_mm=12, size_pt=14))
    edited = compose_editable_layers(Image.open(manual), p.geometry.card_width_mm, p.geometry.card_height_mm, p.texts, p.logo)
    assert edited.size == mimg.size

    # OCR helper path is testable even if RapidOCR isn't installed in this Linux runner.
    candidate = OCRCandidate(
        text="TEST NAME", confidence=0.93,
        box_px=[[200, 200], [650, 200], [650, 260], [200, 260]],
        x_mm=25.0, y_mm=30.0, size_pt=14, color="#111111"
    )
    layers = candidates_to_text_layers([candidate], TextLayer)
    assert len(layers) == 1 and layers[0].ocr_confidence > 0.9
    cleaned = remove_ocr_text(mimg, [candidate])
    cleaned_path = td / "ocr_clean.png"
    cleaned.save(cleaned_path)
    assert cleaned_path.stat().st_size > 0
    backend_status()  # availability is environment-specific; call must never crash.

    # Logo extraction / clean-plate helpers.
    logo_path = td / "extracted_logo.png"
    extract_logo(mimg, ((1100, 150), (1500, 500)), logo_path)
    assert logo_path.exists() and Image.open(logo_path).mode == "RGBA"
    logo_clean = remove_logo_region(mimg, ((1100, 150), (1500, 500)))
    logo_clean.save(td / "logo_clean.png")
    suggested = suggest_logo_regions(mimg, [candidate.box_px], max_results=5)
    assert isinstance(suggested, list)

    base_path = td / "base.stl"
    export_base_stl(base_path, p.geometry, p.nfc)
    base = trimesh.load_mesh(base_path, force="mesh")
    assert np.allclose(base.extents[:2], [88.9, 50.8], atol=0.05)
    assert base.is_watertight

    face = make_face_blank(p.geometry, p.hueforge.face_target_thickness_mm)
    face_path = td / "flatforge_color1.stl"
    face.export(face_path)
    imported = import_hueforge_models(face_path)
    normalized = normalize_face_meshes(imported, p.geometry)
    assert len(normalized) == 1
    assert abs(normalized[0].extents[2] - face.extents[2]) < 1e-6

    scene_3mf = td / "hueforge_face.3mf"
    data = trimesh.Scene([face.copy(), face.copy()]).export(file_type="3mf")
    if isinstance(data, str):
        data = data.encode("utf-8")
    scene_3mf.write_bytes(data)
    imported_3mf = import_hueforge_models(scene_3mf)
    assert len(imported_3mf) >= 1

    hf = td / "hueforge"
    export_hueforge_package(edited, p, hf)
    for f in [
        base_path,
        hf / "CardForge_HueForge_Source.png",
        hf / "CardForge_4Filament_Preview.png",
        hf / "CardForge_HueForge_Handoff.json",
        hf / "README_HUEFORGE.txt",
    ]:
        assert f.exists() and f.stat().st_size > 0, f

    # Portable .cardforge project must carry transient image/logo assets.
    p.cleaned_image = str(cleaned_path)
    p.logo.path = str(logo_path)
    bundle = p.save_bundle(td / "portable.cardforge")
    p2 = Project.load_bundle(bundle, td / "portable_extract")
    assert Path(p2.source_image).exists()
    assert Path(p2.corrected_image).exists()
    assert Path(p2.cleaned_image).exists()
    assert Path(p2.logo.path).exists()

    print("CARDFORGE 0.6 SMOKE TEST PASSED")
    print(td)


if __name__ == "__main__":
    main()
