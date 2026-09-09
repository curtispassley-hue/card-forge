from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

from .ocr import inpaint_regions


def normalize_rect(rect_px, image_size):
    (x0, y0), (x1, y1) = rect_px
    w, h = image_size
    xa, xb = sorted((int(round(x0)), int(round(x1))))
    ya, yb = sorted((int(round(y0)), int(round(y1))))
    xa = max(0, min(w - 1, xa)); xb = max(1, min(w, xb))
    ya = max(0, min(h - 1, ya)); yb = max(1, min(h, yb))
    return xa, ya, xb, yb


def extract_logo(image: Image.Image, rect_px, output_path: str | Path,
                 background_threshold: float = 34.0) -> Path:
    """Extract a selected logo rectangle and make near-background pixels transparent.

    The background estimate comes from the crop border. This works especially
    well for common business-card logos printed on a mostly solid local field.
    Users can always replace the result with an original PNG/SVG-derived image.
    """
    image = image.convert("RGB")
    xa, ya, xb, yb = normalize_rect(rect_px, image.size)
    crop = np.asarray(image)[ya:yb, xa:xb].copy()
    if crop.size == 0:
        raise ValueError("Selected logo rectangle is empty")

    border = np.concatenate([
        crop[0, :, :], crop[-1, :, :], crop[:, 0, :], crop[:, -1, :]
    ], axis=0).astype(np.float32)
    bg = np.median(border, axis=0)

    diff = np.linalg.norm(crop.astype(np.float32) - bg[None, None, :], axis=2)
    alpha = np.clip((diff - background_threshold * 0.45) / max(1.0, background_threshold * 0.55) * 255, 0, 255).astype(np.uint8)

    # Keep edges but suppress isolated speckles.
    alpha = cv2.medianBlur(alpha, 3)
    rgba = np.dstack([crop, alpha])
    out = Image.fromarray(rgba, "RGBA")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)
    return path


def remove_logo_region(image: Image.Image, rect_px) -> Image.Image:
    xa, ya, xb, yb = normalize_rect(rect_px, image.size)
    poly = [[xa, ya], [xb, ya], [xb, yb], [xa, yb]]
    return inpaint_regions(image, [poly], grow_px=2, radius=4.0)


def suggest_logo_regions(image: Image.Image, exclude_polygons=None, max_results: int = 5):
    """Heuristically rank logo-like rectangular regions on a business card.

    This is deliberately an assistant rather than semantic AI segmentation.
    It works best for compact logos/marks with edges or color contrast and tries
    to avoid regions already identified as OCR text.
    """
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 140)

    # Color variation catches flat colored marks that may have weak grayscale edges.
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    local = cv2.Laplacian(lab[:, :, 1], cv2.CV_32F)
    color_edge = (np.abs(local) > 3.5).astype(np.uint8) * 255
    mask = cv2.bitwise_or(edges, color_edge)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    card_area = float(w * h)
    exclude_polygons = exclude_polygons or []

    def overlap_fraction(rect, poly):
        x, y, rw, rh = rect
        rx0, ry0, rx1, ry1 = x, y, x+rw, y+rh
        pts = np.asarray(poly, dtype=float).reshape(-1, 2)
        px0, py0 = pts[:,0].min(), pts[:,1].min()
        px1, py1 = pts[:,0].max(), pts[:,1].max()
        ix0, iy0 = max(rx0, px0), max(ry0, py0)
        ix1, iy1 = min(rx1, px1), min(ry1, py1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        return float((ix1-ix0)*(iy1-iy0)) / max(1.0, rw*rh)

    ranked = []
    for c in contours:
        x, y, rw, rh = cv2.boundingRect(c)
        area = rw * rh
        frac = area / card_area
        if frac < 0.006 or frac > 0.32:
            continue
        aspect = rw / max(1.0, rh)
        if aspect < 0.18 or aspect > 5.5:
            continue

        text_overlap = max([overlap_fraction((x,y,rw,rh), p) for p in exclude_polygons] or [0.0])
        if text_overlap > 0.55:
            continue

        roi = mask[y:y+rh, x:x+rw]
        density = float(np.count_nonzero(roi)) / max(1, roi.size)
        center_x = (x + rw/2) / w
        center_y = (y + rh/2) / h
        # Many logos sit toward a side/top; give a small bonus without assuming it.
        side_bonus = 1.0 + 0.12 * max(abs(center_x-0.5)*2, abs(center_y-0.5)*2)
        compactness = min(rw, rh) / max(rw, rh)
        score = frac**0.45 * (0.45 + density) * (0.65 + compactness) * side_bonus * (1.0 - text_overlap)
        ranked.append((score, ((float(x), float(y)), (float(x+rw), float(y+rh)))))

    ranked.sort(key=lambda z: z[0], reverse=True)
    return [rect for _, rect in ranked[:max_results]]
