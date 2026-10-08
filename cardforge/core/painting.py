"""Pixel editing with independent connected selections and numbered paint slots."""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def selection_outline(image, mask):
    """One viewport-pixel black/white border; selected interior colors stay exact."""
    mask = np.asarray(mask, dtype=bool)
    border = mask & ~ndimage.binary_erosion(mask)
    out = np.array(image.convert('RGBA'))
    yy, xx = np.indices(mask.shape)
    white = ((xx+yy)//5)%2 == 0
    out[border & white] = (255,255,255,255)
    out[border & ~white] = (0,0,0,255)
    return Image.fromarray(out)


class PixelEditor:
    def __init__(self, image, slots=None, original=None):
        self.image = image.convert('RGBA')
        self.original = (original or image).convert('RGBA').resize(self.image.size)
        self.slots = slots.convert('L') if slots is not None else Image.new('L', self.image.size)
        if self.slots.size != self.image.size: raise ValueError('Paint map does not match the image dimensions.')
        if np.asarray(self.slots).max() > 4: raise ValueError('Paint map contains an invalid filament slot.')
        self.selection = None
        self.undo_stack, self.redo_stack = [], []

    def snapshot(self):
        return self.image.copy(), self.slots.copy(), None if self.selection is None else self.selection.copy()

    def remember(self):
        self.undo_stack.append(self.snapshot()); self.undo_stack = self.undo_stack[-max(2, min(20, 128_000_000//(self.image.width*self.image.height*6))):]; self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot()); self.image, self.slots, self.selection = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot()); self.image, self.slots, self.selection = self.redo_stack.pop()

    def preview(self, palette):
        out = np.array(self.image)
        slots = np.asarray(self.slots)
        from PIL import ImageColor
        for i, color in enumerate(palette, 1): out[slots == i, :3] = ImageColor.getrgb(color)[:3]
        return Image.fromarray(out)

    def select_region(self, point, tolerance=30, contiguous=True, palette=None, source='original', operation='replace'):
        x, y = map(int, point)
        if not (0 <= x < self.image.width and 0 <= y < self.image.height): return
        self.remember()
        # Repainting must not merge adjacent, originally different objects just
        # because they now use the same spool. Original pixels travel in projects.
        current = np.asarray(self.image)
        if source == 'original':
            arr = np.asarray(self.original).astype(np.int16)
        elif source == 'display':
            arr = np.asarray(self.preview(palette) if palette else self.image).astype(np.int16)
        else: raise ValueError('Choose original regions or displayed colors.')
        alpha = current[:,:,3]
        added = np.asarray(self.original)[:,:,3] == 0
        if source == 'original' and added[y,x] and alpha[y,x]:
            arr = current.astype(np.int16)
        distance = np.max(np.abs(arr[:,:,:3]-arr[y,x,:3]), axis=2)
        match = (distance <= tolerance) & (alpha > 0) if alpha[y,x] else alpha == 0
        if source == 'original' and added[y,x] and alpha[y,x]: match &= added
        if contiguous:
            labels, _ = ndimage.label(match)
            label = labels[y,x]
            match = labels == label if label else np.zeros(match.shape, dtype=bool)
        if operation == 'replace' or self.selection is None: self.selection = match
        elif operation == 'add': self.selection |= match
        elif operation == 'subtract': self.selection &= ~match
        else: raise ValueError('Choose replace, add or subtract selection.')

    def refine(self, action, pixels=1):
        if self.selection is None: return
        self.remember()
        if action == 'grow': self.selection = ndimage.binary_dilation(self.selection, iterations=pixels)
        elif action == 'shrink': self.selection = ndimage.binary_erosion(self.selection, iterations=pixels)
        elif action == 'smooth': self.selection = ndimage.gaussian_filter(self.selection.astype(float), .8) >= .5
        else: raise ValueError('Unknown edge adjustment.')

    def apply_mask(self, mask, tool, slot=1):
        mask = np.asarray(mask, dtype=bool)
        if self.selection is not None: mask = mask & self.selection
        arr, slots = np.array(self.image), np.array(self.slots)
        if tool == 'paint':
            if not 1 <= slot <= 4: raise ValueError('Choose a paint filament from 1–4.')
            slots[mask] = slot; arr[mask,3] = 255
        elif tool == 'erase': slots[mask] = 0; arr[mask,3] = 0
        elif tool == 'restore': slots[mask] = 0; arr[mask] = np.asarray(self.original)[mask]
        else: raise ValueError('Unknown paint tool.')
        self.image, self.slots = Image.fromarray(arr), Image.fromarray(slots)

    def fill(self, tool='paint', slot=1):
        if self.selection is None: raise ValueError('Select a region first with the Wand tool.')
        self.remember()
        alpha = np.asarray(self.image)[:,:,3].copy()
        self.apply_mask(self.selection, tool, slot)
        if tool == 'paint':
            # Filling a shape preserves its antialiased edge; growing a selection
            # can still create opaque new pixels outside the original outline.
            arr = np.array(self.image)
            existing = self.selection & (alpha > 0)
            arr[existing,3] = alpha[existing]
            self.image = Image.fromarray(arr)

    def stroke(self, start, end, size, tool='paint', slot=1):
        mask = Image.new('L', self.image.size)
        draw = ImageDraw.Draw(mask)
        width = max(1, int(size)); r = max(0, (width-1)/2)
        draw.line([start, end], fill=255, width=width)
        for x, y in (start, end): draw.ellipse((x-r, y-r, x+r, y+r), fill=255)
        self.apply_mask(np.asarray(mask)>0, tool, slot)
