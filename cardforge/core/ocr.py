from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import math

import cv2
import numpy as np
from PIL import Image


@dataclass
class OCRCandidate:
    text: str
    confidence: float
    box_px: list[list[float]]
    x_mm: float
    y_mm: float
    size_pt: int
    color: str = "#111111"
    enabled: bool = True

    def to_dict(self):
        return asdict(self)


def backend_status() -> tuple[bool, str]:
    """Return whether the bundled/offline RapidOCR backend is importable.

    RapidOCR is loaded lazily so CardForge's non-OCR features still work if a
    source checkout is launched before optional OCR dependencies are installed.
    The Windows release build includes RapidOCR + ONNX Runtime.
    """
    try:
        from rapidocr import RapidOCR  # noqa: F401
        import onnxruntime  # noqa: F401
        return True, "RapidOCR + ONNX Runtime available"
    except Exception as exc:
        return False, f"Offline OCR unavailable: {exc}"


def _rapidocr_raw(image: Image.Image):
    from rapidocr import RapidOCR

    engine = RapidOCR()
    arr = np.asarray(image.convert("RGB"))
    result = engine(arr)

    # RapidOCR >=2 returns an object exposing boxes/txts/scores. Older builds
    # may return (result, elapsed) or a list of [box, text, score] rows. Handle
    # both so Windows builds remain tolerant of minor upstream API changes.
    if hasattr(result, "boxes") and hasattr(result, "txts"):
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None:
            return []
        if scores is None:
            scores = [1.0] * len(txts)
        return [(np.asarray(b, dtype=float), str(t), float(s)) for b, t, s in zip(boxes, txts, scores)]

    if isinstance(result, tuple) and len(result) >= 1:
        result = result[0]

    rows = []
    if result:
        for row in result:
            try:
                if len(row) >= 3:
                    rows.append((np.asarray(row[0], dtype=float), str(row[1]), float(row[2])))
            except Exception:
                continue
    return rows


def estimate_text_color(image: Image.Image, box_px: np.ndarray) -> str:
    """Estimate the ink color by comparing dark/colorful interior pixels.

    This is intentionally conservative: business cards often have white or
    textured backgrounds, so the estimate focuses on pixels that differ most
    from the local border median.
    """
    arr = np.asarray(image.convert("RGB"))
    pts = np.asarray(box_px, dtype=float)
    x0 = max(0, int(math.floor(pts[:, 0].min())))
    y0 = max(0, int(math.floor(pts[:, 1].min())))
    x1 = min(arr.shape[1], int(math.ceil(pts[:, 0].max())) + 1)
    y1 = min(arr.shape[0], int(math.ceil(pts[:, 1].max())) + 1)
    if x1 <= x0 or y1 <= y0:
        return "#111111"

    crop = arr[y0:y1, x0:x1]
    if crop.size == 0:
        return "#111111"

    # Border pixels approximate the local background.
    border = np.concatenate([
        crop[0, :, :], crop[-1, :, :], crop[:, 0, :], crop[:, -1, :]
    ], axis=0)
    bg = np.median(border.astype(np.float32), axis=0)
    flat = crop.reshape(-1, 3).astype(np.float32)
    dist = np.linalg.norm(flat - bg[None, :], axis=1)
    if len(dist) < 8:
        rgb = np.mean(flat, axis=0)
    else:
        cutoff = np.percentile(dist, 72)
        ink = flat[dist >= cutoff]
        rgb = np.median(ink, axis=0) if len(ink) else np.mean(flat, axis=0)
    rgb = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return "#{:02X}{:02X}{:02X}".format(*rgb.tolist())


def ocr_candidates(image: Image.Image, width_mm: float, height_mm: float,
                   min_confidence: float = 0.45) -> list[OCRCandidate]:
    rows = _rapidocr_raw(image)
    out: list[OCRCandidate] = []
    w_px, h_px = image.size

    for box, text, score in rows:
        text = (text or "").strip()
        if not text or float(score) < min_confidence:
            continue
        box = np.asarray(box, dtype=float).reshape(-1, 2)
        if len(box) < 4:
            continue

        cx = float(np.mean(box[:, 0]))
        cy = float(np.mean(box[:, 1]))
        x_mm = cx / max(1.0, w_px) * width_mm
        y_mm = (1.0 - cy / max(1.0, h_px)) * height_mm

        # Estimate line height from the two vertical-ish sides.
        side_lengths = [
            np.linalg.norm(box[(i + 1) % len(box)] - box[i])
            for i in range(len(box))
        ]
        side_lengths = sorted(float(v) for v in side_lengths if v > 0)
        short_px = float(np.median(side_lengths[:2])) if len(side_lengths) >= 2 else 20.0
        em_mm = max(1.0, short_px / max(1.0, h_px) * height_mm * 1.15)
        size_pt = int(np.clip(round(em_mm / 25.4 * 72.0), 5, 60))

        out.append(OCRCandidate(
            text=text,
            confidence=float(score),
            box_px=[[float(x), float(y)] for x, y in box],
            x_mm=x_mm,
            y_mm=y_mm,
            size_pt=size_pt,
            color=estimate_text_color(image, box),
        ))

    return out


def inpaint_regions(image: Image.Image, polygons_px: Iterable[Iterable[Iterable[float]]],
                    grow_px: int = 3, radius: float = 3.0) -> Image.Image:
    """Remove text/logo regions from the source image using OpenCV inpainting."""
    rgb = np.asarray(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mask = np.zeros(bgr.shape[:2], dtype=np.uint8)

    for poly in polygons_px:
        pts = np.asarray(poly, dtype=np.int32).reshape(-1, 2)
        if len(pts) >= 3:
            cv2.fillPoly(mask, [pts], 255)

    if grow_px > 0:
        k = int(max(1, grow_px))
        kernel = np.ones((k * 2 + 1, k * 2 + 1), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)

    if not np.any(mask):
        return image.convert("RGB")
    cleaned = cv2.inpaint(bgr, mask, float(radius), cv2.INPAINT_TELEA)
    cleaned = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)
    return Image.fromarray(cleaned, "RGB")


def remove_ocr_text(image: Image.Image, candidates: Iterable[OCRCandidate]) -> Image.Image:
    polys = [c.box_px for c in candidates if c.enabled and c.text]
    return inpaint_regions(image, polys, grow_px=2, radius=3.0)


def candidates_to_text_layers(candidates, TextLayerClass):
    layers = []
    for c in candidates:
        if not c.enabled or not c.text:
            continue
        layer = TextLayerClass(
            text=c.text,
            x_mm=float(c.x_mm),
            y_mm=float(c.y_mm),
            size_pt=int(c.size_pt),
            font_path="",
            color=c.color,
            enabled=True,
        )
        if hasattr(layer, "ocr_confidence"):
            layer.ocr_confidence = float(c.confidence)
        if hasattr(layer, "source_box_px"):
            layer.source_box_px = [list(p) for p in c.box_px]
        layers.append(layer)
    return layers
