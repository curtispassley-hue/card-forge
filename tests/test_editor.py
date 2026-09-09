import unittest
import numpy as np
import json
import zipfile
from pathlib import Path
import tempfile
from PIL import Image, ImageDraw
from cardforge.core.logo import remove_logo_background
from cardforge.core.image_processing import nearest_palette_preview, hex_to_rgb
from cardforge.core.project import Project, TextLayer
from cardforge.core.face import build_face, export_face
from cardforge.core.fonts import bundled_fonts

class EditorTests(unittest.TestCase):
    def test_bundled_font_library(self):
        self.assertGreaterEqual(len(bundled_fonts()), 30)
        self.assertTrue(all(Path(path).exists() for path in bundled_fonts().values()))

    def test_direct_face_has_named_flush_parts_and_flat_exteriors(self):
        p = Project(texts=[TextLayer(text='CARD', x_mm=24, y_mm=25, size_pt=16, color='#111111')])
        parts = build_face(p)
        self.assertGreaterEqual(len(parts), 3)
        self.assertEqual(parts[0]['name'], 'Background')
        self.assertEqual(parts[-1]['name'], 'Solid backing')
        for part in parts:
            self.assertTrue(part['mesh'].is_watertight)
            self.assertTrue(part['mesh'].is_winding_consistent)
        with tempfile.TemporaryDirectory() as td:
            out = export_face(p, Path(td), include_base=True)
            self.assertTrue((out/'CardForge_Face.3mf').exists())
            self.assertTrue((out/'CardForge_NFC_Base.stl').exists())
            data = json.loads((out/'Parts.json').read_text())
            self.assertEqual(data[0]['part'], 'Background')
            with zipfile.ZipFile(out/'CardForge_Face.3mf') as z:
                self.assertIn('3D/3dmodel.model', z.namelist())
                self.assertIn('Metadata/model_settings.config', z.namelist())
                config = z.read('Metadata/model_settings.config').decode()
                self.assertIn('Solid backing', config)
                self.assertIn('key="extruder"', config)
                import re
                extruders = [int(x) for x in re.findall(r'key="extruder" value="(\d+)"', config)]
                self.assertTrue(extruders)
                self.assertTrue(all(1 <= x <= 4 for x in extruders))

    def test_raster_logo_repairs_small_counter_edges(self):
        with tempfile.TemporaryDirectory() as td:
            logo = Path(td) / 'logo.png'
            im = Image.new('RGB', (1000, 220), 'white')
            ImageDraw.Draw(im).text((40, 70), 'CARDFORGE TEST 123', fill='black')
            im.save(logo)
            p = Project()
            p.logo.path = str(logo)
            p.logo.width_mm = 19.8
            parts = build_face(p)
            self.assertTrue(all(x['mesh'].is_watertight for x in parts))

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
