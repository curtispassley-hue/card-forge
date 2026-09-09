from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from .fonts import default_font
from PIL import Image, ImageDraw, ImageFont


CARD_RATIO = 88.9 / 50.8


def order_points(pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([
        pts[np.argmin(s)],       # top-left
        pts[np.argmin(d)],       # top-right
        pts[np.argmax(s)],       # bottom-right
        pts[np.argmax(d)],       # bottom-left
    ], dtype=np.float32)


def detect_card_quad(image_bgr: np.ndarray) -> np.ndarray | None:
    """Find the largest plausible 4-corner business-card contour in a photo."""
    h, w = image_bgr.shape[:2]
    scale = min(1.0, 1600.0 / max(h, w))
    small = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 45, 45)

    # Combine an edge detector with adaptive thresholding; cards photographed on
    # dark or bright tables can otherwise be missed by a single method.
    edges = cv2.Canny(gray, 45, 150)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 7)
    combo = cv2.bitwise_or(edges, cv2.Canny(thresh, 40, 120))
    combo = cv2.morphologyEx(combo, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)

    contours, _ = cv2.findContours(combo, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    img_area = small.shape[0] * small.shape[1]
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < img_area * 0.06:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.018 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        pts = approx.reshape(4, 2).astype(np.float32)
        rect = cv2.minAreaRect(pts)
        rw, rh = rect[1]
        if rw <= 0 or rh <= 0:
            continue
        ratio = max(rw, rh) / min(rw, rh)
        ratio_score = max(0.0, 1.0 - min(abs(ratio - CARD_RATIO) / CARD_RATIO, 1.0))
        # Favor large contours but still reward business-card-ish proportions.
        score = area * (0.60 + 0.40 * ratio_score)
        candidates.append((score, pts / scale))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return order_points(candidates[0][1])


def warp_card(image_bgr: np.ndarray, quad: np.ndarray, width_px: int = 1600,
              ratio: float = CARD_RATIO) -> np.ndarray:
    quad = order_points(quad)
    height_px = int(round(width_px / ratio))
    dst = np.array([
        [0, 0], [width_px - 1, 0], [width_px - 1, height_px - 1], [0, height_px - 1]
    ], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(image_bgr, m, (width_px, height_px), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def centered_card_crop(image_bgr: np.ndarray, width_px: int = 1600,
                       ratio: float = CARD_RATIO) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    current = w / h
    if current > ratio:
        new_w = int(round(h * ratio))
        x = max(0, (w - new_w) // 2)
        crop = image_bgr[:, x:x + new_w]
    else:
        new_h = int(round(w / ratio))
        y = max(0, (h - new_h) // 2)
        crop = image_bgr[y:y + new_h, :]
    return cv2.resize(crop, (width_px, int(round(width_px / ratio))), interpolation=cv2.INTER_CUBIC)


def auto_correct_file(src: str | Path, dst: str | Path, width_px: int = 1600) -> bool:
    image = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {src}")
    quad = detect_card_quad(image)
    if quad is None:
        corrected = centered_card_crop(image, width_px=width_px)
        detected = False
    else:
        corrected = warp_card(image, quad, width_px=width_px)
        detected = True
    cv2.imwrite(str(dst), corrected)
    return detected


def manual_correct_file(src: str | Path, dst: str | Path, quad, width_px: int = 1600) -> None:
    image = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {src}")
    pts = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    corrected = warp_card(image, pts, width_px=width_px)
    cv2.imwrite(str(dst), corrected)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def nearest_palette_preview(image: Image.Image, palette_hex: list[str]) -> Image.Image:
    """Preview only: map pixels to nearest of the user's four physical filament colors."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.int32)
    pal = np.array([hex_to_rgb(c) for c in palette_hex], dtype=np.int32)
    out = np.empty(rgb.shape, dtype=np.uint8)
    for start in range(0, rgb.shape[0], 64):
        rows = rgb[start:start+64]
        diff = rows[:, :, None, :] - pal[None, None, :, :]
        idx = np.argmin(np.sum(diff * diff, axis=3), axis=2)
        out[start:start+64] = pal[idx].astype(np.uint8)
    return Image.fromarray(out, "RGB")


def fit_card_image(im: Image.Image, ratio: float = CARD_RATIO, width_px: int = 1600) -> Image.Image:
    im = im.convert("RGB")
    current = im.width / im.height
    if abs(current - ratio) > 0.001:
        if current > ratio:
            nw = int(round(im.height * ratio))
            x = (im.width - nw) // 2
            im = im.crop((x, 0, x + nw, im.height))
        else:
            nh = int(round(im.width / ratio))
            y = (im.height - nh) // 2
            im = im.crop((0, y, im.width, y + nh))
    return im.resize((width_px, int(round(width_px / ratio))), Image.Resampling.LANCZOS)


def compose_editable_layers(base: Image.Image, width_mm: float, height_mm: float, texts, logo) -> Image.Image:
    out = base.convert("RGBA")
    draw = ImageDraw.Draw(out)
    ppm = out.width / width_mm

    for layer in texts:
        if not getattr(layer, "enabled", True) or not layer.text:
            continue
        px = max(8, int(round(layer.size_pt * 25.4 / 72 * ppm)))
        try:
            font = ImageFont.truetype(layer.font_path, px) if layer.font_path else ImageFont.truetype(default_font(), px)
        except Exception:
            font = ImageFont.load_default(size=px)
        x = int(round(layer.x_mm * ppm))
        y = int(round(out.height - layer.y_mm * ppm))
        draw.text((x, y), layer.text, font=font, fill=layer.color, anchor="mm")

    if logo and getattr(logo, "enabled", True) and logo.path and Path(logo.path).exists():
        try:
            lg = Image.open(logo.path).convert("RGBA")
            target_w = max(8, int(round(logo.width_mm * ppm)))
            target_h = max(8, int(round(lg.height * target_w / lg.width)))
            lg = lg.resize((target_w, target_h), Image.Resampling.LANCZOS)
            if logo.opacity < 255:
                alpha = lg.getchannel("A").point(lambda p: int(p * logo.opacity / 255))
                lg.putalpha(alpha)
            x = int(round(logo.x_mm * ppm - target_w / 2))
            y = int(round(out.height - logo.y_mm * ppm - target_h / 2))
            out.alpha_composite(lg, (x, y))
        except Exception:
            pass
    return out.convert("RGB")
