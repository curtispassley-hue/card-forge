from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import copy
import json
import tempfile
import zipfile


@dataclass
class TextLayer:
    text: str = ""
    x_mm: float = 44.45
    y_mm: float = 25.4
    size_pt: int = 16
    font_path: str = ""
    color: str = "#111111"
    enabled: bool = True
    ocr_confidence: float = 0.0
    source_box_px: list[list[float]] = field(default_factory=list)


@dataclass
class LogoLayer:
    name: str = "Logo"
    path: str = ""
    x_mm: float = 20.0
    y_mm: float = 25.4
    width_mm: float = 18.0
    opacity: int = 255
    enabled: bool = True
    source_rect_px: list[list[float]] = field(default_factory=list)


@dataclass
class NFCSettings:
    preset_name: str = "25 mm sticker"
    diameter_mm: float = 25.0
    thickness_mm: float = 0.8
    clearance_mm: float = 0.25
    x_mm: float = 72.0
    y_mm: float = 25.4


@dataclass
class GeometrySettings:
    card_width_mm: float = 88.9
    card_height_mm: float = 50.8
    corner_radius_mm: float = 3.0
    base_thickness_mm: float = 2.6
    face_recess_depth_mm: float = 0.85
    face_border_mm: float = 0.55
    face_clearance_mm: float = 0.15


@dataclass
class HueForgeSettings:
    face_down: bool = True
    face_target_thickness_mm: float = 0.80
    transparent_cap_mm: float = 0.20
    palette: list[str] = field(default_factory=lambda: ["#111111", "#FFFFFF", "#D92D20", "#F4C430"])
    filament_names: list[str] = field(default_factory=lambda: ["Black", "White", "Red", "Gold"])


@dataclass
class EditorSettings:
    snap_mm: float = 0.25
    show_nfc_guide: bool = True
    auto_fit_source: bool = True
    ocr_remove_original: bool = True
    grayscale_artwork: bool = False


@dataclass
class FaceSettings:
    thickness_mm: float = 0.8
    front_depth_mm: float = 0.4
    background_color: str = "#FFFFFF"


@dataclass
class Project:
    format_version: str = "0.7.0"
    name: str = "Untitled Card"
    source_image: str = ""
    corrected_image: str = ""
    cleaned_image: str = ""
    hueforge_import_path: str = ""
    manual_corners: list[list[float]] = field(default_factory=list)
    ocr_candidates: list[dict] = field(default_factory=list)
    ocr_backend: str = ""
    geometry: GeometrySettings = field(default_factory=GeometrySettings)
    nfc: NFCSettings = field(default_factory=NFCSettings)
    hueforge: HueForgeSettings = field(default_factory=HueForgeSettings)
    editor: EditorSettings = field(default_factory=EditorSettings)
    texts: list[TextLayer] = field(default_factory=list)
    logo: LogoLayer = field(default_factory=LogoLayer)
    # Additional raster image elements. The legacy ``logo`` field is
    # retained as the first element so projects from 0.4–0.7 remain portable.
    elements: list[LogoLayer] = field(default_factory=list)
    face: FaceSettings = field(default_factory=FaceSettings)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        data = copy.deepcopy(data)
        data["geometry"] = GeometrySettings(**data.get("geometry", {}))
        data["nfc"] = NFCSettings(**data.get("nfc", {}))
        data["hueforge"] = HueForgeSettings(**data.get("hueforge", {}))
        data["editor"] = EditorSettings(**data.get("editor", {}))
        data["face"] = FaceSettings(**data.get("face", {}))
        data["texts"] = [TextLayer(**x) for x in data.get("texts", [])]
        data["logo"] = LogoLayer(**data.get("logo", {}))
        data["elements"] = [LogoLayer(**x) for x in data.get("elements", [])]
        data.setdefault("format_version", "0.2.0")
        data.setdefault("manual_corners", [])
        data.setdefault("cleaned_image", "")
        data.setdefault("ocr_candidates", [])
        data.setdefault("ocr_backend", "")
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save_bundle(self, path: str | Path) -> Path:
        """Save project + current image/logo assets in a portable .cardforge ZIP.

        This fixes a weakness in early alphas where corrected/cleaned images
        lived only in a temporary directory and could disappear after restart.
        """
        path = Path(path)
        if path.suffix.lower() != ".cardforge":
            path = path.with_suffix(".cardforge")

        data = asdict(self)
        asset_map = {}
        used = set()

        def bundle_asset(value: str, role: str):
            if not value:
                return value
            p = Path(value)
            if not p.exists() or not p.is_file():
                return value
            base = p.name
            name = f"{role}_{base}"
            n = 2
            while name.lower() in used:
                name = f"{role}_{n}_{base}"
                n += 1
            used.add(name.lower())
            asset_map[f"assets/{name}"] = p
            return f"bundle://assets/{name}"

        for key in ("source_image", "corrected_image", "cleaned_image"):
            data[key] = bundle_asset(data.get(key, ""), key)
        data["logo"]["path"] = bundle_asset(data.get("logo", {}).get("path", ""), "logo")
        for i, element in enumerate(data.get("elements", [])):
            element["path"] = bundle_asset(element.get("path", ""), f"element_{i}")
        for i, layer in enumerate(data["texts"]):
            layer["font_path"] = bundle_asset(layer.get("font_path", ""), f"font_{i}")
        imported = Path(self.hueforge_import_path) if self.hueforge_import_path else None
        if imported and imported.is_file():
            data["hueforge_import_path"] = bundle_asset(str(imported), "hueforge")
        elif imported and imported.is_dir():
            for model in imported.iterdir():
                if model.is_file() and model.suffix.lower() in (".stl", ".3mf"):
                    asset_map[f"assets/hueforge/{model.name}"] = model
            data["hueforge_import_path"] = "bundle://assets/hueforge"

        import os
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix='.cardforge_', suffix='.tmp', dir=path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('project.json', json.dumps(data, indent=2))
                for arc, src in asset_map.items():
                    z.write(src, arcname=arc)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
        return path

    @classmethod
    def load_bundle(cls, path: str | Path, extract_dir: str | Path | None = None) -> "Project":
        path = Path(path)
        if extract_dir is None:
            extract_dir = Path(tempfile.mkdtemp(prefix="CardForgeProject_"))
        extract_dir = Path(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(path, "r") as z:
            root = extract_dir.resolve()
            for item in z.infolist():
                if not (root / item.filename).resolve().is_relative_to(root):
                    raise ValueError("Project contains an unsafe asset path.")
            z.extractall(extract_dir)

        data = json.loads((extract_dir / "project.json").read_text(encoding="utf-8"))

        def resolve(value: str):
            if isinstance(value, str) and value.startswith("bundle://"):
                target = (extract_dir / value[len("bundle://"):]).resolve()
                if not target.is_relative_to(extract_dir.resolve()):
                    raise ValueError("Project asset points outside the project.")
                return str(target)
            return value

        for key in ("source_image", "corrected_image", "cleaned_image", "hueforge_import_path"):
            data[key] = resolve(data.get(key, ""))
        for layer in data.get("texts", []):
            layer["font_path"] = resolve(layer.get("font_path", ""))
        if "logo" in data:
            data["logo"]["path"] = resolve(data["logo"].get("path", ""))
        for element in data.get("elements", []):
            element["path"] = resolve(element.get("path", ""))
        return cls.from_dict(data)
