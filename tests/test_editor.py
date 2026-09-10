import unittest
import numpy as np
import json
import zipfile
from pathlib import Path
import tempfile
from PIL import Image, ImageDraw, ImageFont
from cardforge.core.logo import remove_logo_background
from cardforge.core.image_processing import nearest_palette_preview, hex_to_rgb, compose_editable_layers
from cardforge.core.project import Project, TextLayer, LogoLayer
from cardforge.core.face import build_face, export_face, export_logo, artwork_masks, _safe_stem
from cardforge.core.fonts import bundled_fonts

class EditorTests(unittest.TestCase):
    def test_multiple_images_portable_named_export_and_grayscale(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = Project()
            original = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            ImageDraw.Draw(original).ellipse((10, 10, 90, 90), fill='#D92D20')
            for name, x in [('Badge', 25), ('Emblem', 32), ('Hidden', 60)]:
                path = root / (name + '.png')
                original.save(path)
                p.elements.append(LogoLayer(name=name, path=str(path), x_mm=x, y_mm=25,
                                           width_mm=18, enabled=name != 'Hidden'))
            before = Path(p.elements[0].path).read_bytes()
            parts = build_face(p)
            names = [x['name'] for x in parts]
            self.assertTrue(any(n.startswith('Badge -') for n in names))
            self.assertTrue(any(n.startswith('Emblem -') for n in names))
            self.assertFalse(any(n.startswith('Hidden -') for n in names))
            self.assertTrue(all(x['mesh'].is_watertight and x['mesh'].is_winding_consistent for x in parts))
            # Overlapping images carve complementary regions; no double volume.
            expected = parts[-1]['polygon'].area * p.face.thickness_mm
            self.assertAlmostEqual(sum(x['mesh'].volume for x in parts), expected, delta=expected*.0001)
            p.editor.grayscale_artwork = True
            p.hueforge.palette = ['#111111', '#666666', '#BBBBBB', '#FFFFFF']
            masks, _, _, _, _ = artwork_masks(p)
            badge = [(c, m) for n, c, m in masks if n.startswith('Badge') and m.any()]
            self.assertEqual([c for c, _ in badge], ['#666666'])
            preview = np.asarray(compose_editable_layers(Image.new('RGB', (889, 508), 'white'),
                88.9, 50.8, p.texts, p.logo, p.elements, True))
            self.assertTrue(np.array_equal(preview[:,:,0], preview[:,:,1]))
            self.assertTrue(np.array_equal(preview[:,:,1], preview[:,:,2]))
            self.assertTrue(np.any(preview != 255))
            self.assertTrue(np.all(preview[0,0] == 255))
            self.assertEqual(Path(p.elements[0].path).read_bytes(), before)
            saved = p.save_bundle(root / 'portable.cardforge')
            for element in p.elements:
                Path(element.path).unlink()
            restored = Project.load_bundle(saved, root / 'restored')
            self.assertEqual([e.name for e in restored.elements], ['Badge', 'Emblem', 'Hidden'])
            self.assertTrue(all(Path(e.path).exists() for e in restored.elements))
            self.assertTrue(restored.editor.grayscale_artwork)
            self.assertFalse(restored.elements[-1].enabled)
            out = export_face(restored, root/'exports', True, 'My Card')
            self.assertEqual(out.name, 'My_Card')
            for name in ('My_Card_Face.3mf', 'My_Card_NFC_Base.stl', 'My_Card_Project.cardforge'):
                self.assertTrue((out/name).is_file(), name)
            self.assertIn('My_Card_Face.3mf', (out/'My_Card_PRINT_README.txt').read_text())
            original_3mf = (out/'My_Card_Face.3mf').read_bytes()
            again = export_face(restored, root/'exports', output_name='My Card')
            self.assertEqual(again.name, 'My_Card_2')
            self.assertEqual((out/'My_Card_Face.3mf').read_bytes(), original_3mf)
            logo = export_logo(restored, root/'exports', output_name='Icons')
            self.assertTrue((logo/'Icons_Logo.stl').is_file())
            self.assertTrue((logo/'Icons_Logo.3mf').is_file())

    def test_legacy_project_and_windows_export_names(self):
        p = Project.from_dict({'logo': {'path': 'old-logo.png'}, 'editor': {'snap_mm': .5}})
        self.assertEqual(p.logo.path, 'old-logo.png')
        self.assertEqual(p.elements, [])
        self.assertFalse(p.editor.grayscale_artwork)
        self.assertEqual(_safe_stem('../../CON'), '_CON')
        self.assertEqual(_safe_stem('LPT1.txt'), '_LPT1.txt')
        self.assertNotIn('/', _safe_stem('../My Card/'))

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

    def test_logo_with_narrow_raster_counters_forms_closed_solid(self):
        # Heavy display faces commonly create one-pixel backtracking edges
        # around counters after resizing. Keep this Windows-font regression
        # because it was the original user-facing export failure.
        font_path = Path('C:/Windows/Fonts/impact.ttf')
        if not font_path.exists():
            self.skipTest('Impact display font is not installed on this host')
        with tempfile.TemporaryDirectory() as td:
            logo = Path(td) / 'display-logo.png'
            im = Image.new('RGBA', (1000, 300), (0, 0, 0, 0))
            font = ImageFont.truetype(str(font_path), 120)
            ImageDraw.Draw(im).text((5, 150), 'A&W #$% 123', font=font,
                                    fill=(20, 20, 20, 255), anchor='lm', stroke_width=3)
            im.save(logo)
            p = Project()
            p.logo.path = str(logo)
            p.logo.width_mm = 40
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

    def test_standalone_logo_export_has_named_parts_and_stls(self):
        with tempfile.TemporaryDirectory() as td:
            logo = Path(td) / 'logo.png'
            im = Image.new('RGBA', (160, 100), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            draw.rectangle((12, 22, 68, 78), fill=(20, 20, 20, 255))
            draw.ellipse((88, 22, 144, 78), fill=(220, 40, 30, 255))
            im.save(logo)
            p = Project()
            p.logo.path = str(logo)
            p.logo.width_mm = 22
            out = export_logo(p, Path(td) / 'logo_out')
            self.assertTrue((out / 'CardForge_Logo.3mf').exists())
            self.assertTrue((out / 'CardForge_Logo.stl').exists())
            self.assertTrue((out / 'Logo_Parts.json').exists())
            stls = list((out / 'Logo_STLs').glob('*.stl'))
            self.assertGreaterEqual(len(stls), 2)
            self.assertTrue(all(__import__('trimesh').load(path, force='mesh').is_watertight for path in stls))
            data = json.loads((out / 'Logo_Parts.json').read_text())
            self.assertTrue(all(item['part'].startswith('Logo -') for item in data))
