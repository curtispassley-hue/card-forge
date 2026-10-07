"""Stable artwork assignments, independent background, reversible color mode."""
import numpy as np
from PIL import ImageColor

DEFAULT_PALETTE = ['#111111', '#FFFFFF', '#D92D20', '#F4C430']
GRAY_PALETTE = ['#111111', '#666666', '#BBBBBB', '#FFFFFF']


def effective_palette(project):
    return list(GRAY_PALETTE if project.editor.grayscale_artwork else project.hueforge.palette)


def nearest_slot(color, reference):
    rgb = np.array(ImageColor.getrgb(color)[:3], dtype=float)
    pal = np.array([ImageColor.getrgb(c)[:3] for c in reference], dtype=float)
    return int(np.argmin(((pal-rgb)**2).sum(axis=1)))


def text_color(layer, project):
    slot = layer.filament_slot
    if slot is None:
        slot = nearest_slot(layer.color, project.hueforge.mapping_palette)
    if not 0 <= slot < 4:
        raise ValueError('Artwork filament assignment must be 1–4.')
    return effective_palette(project)[slot]


def export_palette(project):
    # The fifth DESIGN control can share a physical spool with artwork.
    colors = effective_palette(project)
    background = project.face.background_color.upper()
    ImageColor.getrgb(background)
    if background not in [c.upper() for c in colors]: colors.append(background)
    if project.product.kind == "lightbox":
        diffuser = project.product.diffuser_color.upper()
        ImageColor.getrgb(diffuser)
        if diffuser not in [c.upper() for c in colors]: colors.append(diffuser)
    return colors
