"""Shared image transforms for the editor and printable geometry."""
import math
from PIL import Image, ImageOps


def image_size_mm(layer):
    with Image.open(layer.path) as im:
        ratio = im.height / im.width
    return layer.width_mm, (layer.height_mm if layer.height_mm is not None else layer.width_mm * ratio)


def render_image_layer(layer, ppm_x, ppm_y=None, grayscale=False):
    """Preserve alpha and apply dimensions, reflections and counterclockwise rotation."""
    ppm_y = ppm_x if ppm_y is None else ppm_y
    width, height = image_size_mm(layer)
    if not all(math.isfinite(v) for v in (width, height, layer.rotation_deg, layer.opacity)):
        raise ValueError('Image dimensions, rotation and opacity must be valid numbers.')
    if not .5 <= width <= 256 or not .05 <= height <= 256:
        raise ValueError('Image width must be 0.5–256 mm and height must be 0.05–256 mm.')
    # Rotate at isotropic scale, then account for the output raster's rounding.
    ppm = max(ppm_x, ppm_y)
    size = (max(1, round(width*ppm)), max(1, round(height*ppm)))
    if size[0]*size[1] > 20_000_000:
        raise ValueError('Image element is too large.')
    with Image.open(layer.path) as source:
        im = source.convert('RGBA')
    if grayscale or layer.grayscale:
        gray = im.convert('L')
        im = Image.merge('RGBA', (gray, gray, gray, im.getchannel('A')))
    if layer.tint_color:
        tint = Image.new('RGBA', im.size, layer.tint_color)
        tint.putalpha(im.getchannel('A'))
        im = tint
    im = im.resize(size, Image.Resampling.LANCZOS)
    if layer.flip_x:
        im = ImageOps.mirror(im)
    if layer.flip_y:
        im = ImageOps.flip(im)
    if layer.rotation_deg % 360:
        im = im.rotate(layer.rotation_deg % 360, resample=Image.Resampling.BICUBIC, expand=True)
    final_size = (max(1, round(im.width*ppm_x/ppm)), max(1, round(im.height*ppm_y/ppm)))
    if final_size != im.size:
        im = im.resize(final_size, Image.Resampling.LANCZOS)
    opacity = min(255, max(0, layer.opacity))
    if opacity < 255:
        im.putalpha(im.getchannel('A').point(lambda a: round(a*opacity/255)))
    return im
