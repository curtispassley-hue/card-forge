"""Shared image transforms for the editor and printable geometry."""
import math
import numpy as np
from PIL import Image, ImageOps
from .colors import DEFAULT_PALETTE, GRAY_PALETTE, nearest_slot


def source_slots(layer, grayscale=False, reference=None):
    """Classify source pixels once against stable reference colors, then apply paint."""
    with Image.open(layer.path) as source:
        im = source.convert('RGBA')
    gray = grayscale or layer.grayscale
    if gray:
        luminance = im.convert('L')
        im = Image.merge('RGBA', (luminance, luminance, luminance, im.getchannel('A')))
    reference = reference or DEFAULT_PALETTE
    from PIL import ImageColor
    pal = np.asarray([ImageColor.getrgb(c)[:3] for c in (GRAY_PALETTE if grayscale else reference)], dtype=np.int32)
    pixels = np.asarray(im)
    slots = np.empty(pixels.shape[:2], dtype=np.uint8)
    for start in range(0, im.height, 64):
        diff = pixels[start:start+64,:,:3].astype(np.int32)[:,:,None,:]-pal
        slots[start:start+64] = np.argmin((diff*diff).sum(axis=3), axis=2)+1
    if layer.paint_slots_path:
        with Image.open(layer.paint_slots_path) as raw: painted = np.asarray(raw.convert('L'))
        if painted.shape != slots.shape or painted.max() > 4:
            raise ValueError('Image paint map is invalid or has mismatched dimensions.')
        slots[painted > 0] = painted[painted > 0]
    slot = layer.filament_slot
    if slot is None and layer.tint_color: slot = nearest_slot(layer.tint_color, reference)
    if slot is not None:
        if not 0 <= slot < 4: raise ValueError('Choose an artwork filament from 1–4.')
        slots[:] = slot+1
    # Transparent RGB is arbitrary. Extend the nearest visible assignment into
    # it so antialiasing cannot introduce a black fringe at the silhouette.
    transparent = pixels[:,:,3] == 0
    if transparent.any() and not transparent.all():
        from scipy.ndimage import distance_transform_edt
        nearest = distance_transform_edt(transparent, return_distances=False, return_indices=True)
        slots[transparent] = slots[tuple(nearest[:,transparent])]
    return im, Image.fromarray(slots)


def render_slot_layer(layer, ppm_x, ppm_y=None, grayscale=False, reference=None):
    _, slots = source_slots(layer, grayscale, reference)
    return _transform(slots, layer, ppm_x, ppm_y, nearest=True)


def _transform(im, layer, ppm_x, ppm_y=None, nearest=False):
    ppm_y = ppm_x if ppm_y is None else ppm_y
    width, height = image_size_mm(layer)
    if not all(math.isfinite(v) for v in (width, height, layer.rotation_deg, layer.opacity)):
        raise ValueError('Image dimensions, rotation and opacity must be valid numbers.')
    if not .5 <= width <= 256 or not .05 <= height <= 256:
        raise ValueError('Image width must be 0.5–256 mm and height must be 0.05–256 mm.')
    ppm = max(ppm_x, ppm_y)
    size = (max(1, round(width*ppm)), max(1, round(height*ppm)))
    if size[0]*size[1] > 20_000_000: raise ValueError('Image element is too large.')
    im = im.resize(size, Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS)
    if layer.flip_x: im = ImageOps.mirror(im)
    if layer.flip_y: im = ImageOps.flip(im)
    if layer.rotation_deg % 360:
        im = im.rotate(layer.rotation_deg % 360, resample=Image.Resampling.NEAREST if nearest else Image.Resampling.BICUBIC, expand=True)
    final_size = (max(1, round(im.width*ppm_x/ppm)), max(1, round(im.height*ppm_y/ppm)))
    if final_size != im.size: im = im.resize(final_size, Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS)
    return im


def image_size_mm(layer):
    with Image.open(layer.path) as im:
        ratio = im.height / im.width
    return layer.width_mm, (layer.height_mm if layer.height_mm is not None else layer.width_mm * ratio)


def render_image_layer(layer, ppm_x, ppm_y=None, grayscale=False, palette=None, reference=None):
    """Preserve alpha and apply dimensions, reflections and counterclockwise rotation."""
    with Image.open(layer.path) as source:
        im = source.convert('RGBA')
    if palette is not None:
        from PIL import ImageColor
        _, slots = source_slots(layer, grayscale, reference)
        rgb = np.asarray([ImageColor.getrgb(c)[:3] for c in palette], dtype=np.uint8)[np.asarray(slots)-1]
        colored = Image.fromarray(rgb).convert('RGBA')
        colored.putalpha(im.getchannel('A'))
        im = _transform(colored, layer, ppm_x, ppm_y)
        opacity = min(255, max(0, layer.opacity))
        if opacity < 255: im.putalpha(im.getchannel('A').point(lambda a: round(a*opacity/255)))
        return im
    if grayscale or layer.grayscale:
        gray = im.convert('L')
        im = Image.merge('RGBA', (gray, gray, gray, im.getchannel('A')))
    if layer.tint_color:
        tint = Image.new('RGBA', im.size, layer.tint_color)
        tint.putalpha(im.getchannel('A'))
        im = tint
    im = _transform(im, layer, ppm_x, ppm_y)
    opacity = min(255, max(0, layer.opacity))
    if opacity < 255:
        im.putalpha(im.getchannel('A').point(lambda a: round(a*opacity/255)))
    return im
