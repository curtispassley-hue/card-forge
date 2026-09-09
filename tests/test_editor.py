import unittest
import numpy as np
from PIL import Image, ImageDraw
from cardforge.core.logo import remove_logo_background
from cardforge.core.image_processing import nearest_palette_preview, hex_to_rgb

class EditorTests(unittest.TestCase):
    def test_remove_background_keeps_logo_and_alpha(self):
        im = Image.new('RGBA', (80, 80), 'white')
        ImageDraw.Draw(im).rectangle((20, 20, 60, 60), fill=(255, 0, 0, 128))
        result = remove_logo_background(im)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((40, 40)), (255, 0, 0, 128))
        self.assertEqual(im.getpixel((0, 0))[3], 255)

    def test_palette_matches_reference_across_chunks(self):
        arr = np.random.default_rng(9).integers(0, 256, (137, 91, 3), dtype=np.uint8)
        colors = ['#111111', '#ffffff', '#bb3322', '#ffd440']
        pal = np.array([hex_to_rgb(c) for c in colors], dtype=np.int32)
        diff = arr.astype(np.int32)[:, :, None, :] - pal
        expected = pal[np.argmin(np.sum(diff*diff, axis=3), axis=2)].astype(np.uint8)
        np.testing.assert_array_equal(np.array(nearest_palette_preview(Image.fromarray(arr), colors)), expected)
