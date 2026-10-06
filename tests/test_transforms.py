import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from cardforge.core.project import Project, LogoLayer
from cardforge.core.artwork import render_image_layer
from cardforge.core.face import build_face, artwork_masks


class TransformTests(unittest.TestCase):
    def test_rotation_reflection_and_dimensions_match_print_masks(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'asymmetric.png'
            im = Image.new('RGBA', (160, 80))
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, 45, 79), fill='#111111')
            d.rectangle((0, 55, 159, 79), fill='#111111')
            im.save(path)
            layer = LogoLayer(path=str(path), width_mm=20, height_mm=10, x_mm=35, y_mm=25)
            normal = render_image_layer(layer, 12)
            layer.flip_x = True
            reflected = render_image_layer(layer, 12)
            np.testing.assert_array_equal(reflected, ImageOps.mirror(normal))
            layer.rotation_deg = 90
            rotated = render_image_layer(layer, 12)
            self.assertEqual(rotated.size, (120, 240))
            np.testing.assert_array_equal(rotated, reflected.transpose(Image.Transpose.ROTATE_90))
            layer.rotation_deg = 33
            p = Project(elements=[layer])
            masks, _, size, _, _ = artwork_masks(p)
            footprint = np.any(np.stack([mask for _, _, mask in masks]), axis=0)
            self.assertTrue(footprint.any())
            parts = build_face(p)
            self.assertTrue(all(x['mesh'].is_watertight and x['mesh'].volume > 0 for x in parts))
            expected_volume = parts[-1]['polygon'].area*p.face.thickness_mm
            self.assertAlmostEqual(sum(x['mesh'].volume for x in parts), expected_volume, delta=expected_volume*.0001)
            for part in parts[1:-1]:
                self.assertAlmostEqual(part['mesh'].bounds[0][2], 0)
                self.assertAlmostEqual(part['mesh'].bounds[1][2], p.face.front_depth_mm)
            p.save_bundle(Path(td)/'transformed.cardforge')
            restored = Project.load_bundle(Path(td)/'transformed.cardforge', Path(td)/'unpacked')
            self.assertTrue(restored.elements[0].flip_x)
            self.assertEqual(restored.elements[0].rotation_deg, 33)
            self.assertEqual(restored.elements[0].height_mm, 10)

    def test_tint_and_grayscale_preserve_transparency_and_validate_sizes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'image.png'
            Image.new('RGBA', (30, 20), (220, 40, 90, 128)).save(path)
            layer = LogoLayer(path=str(path), width_mm=3, grayscale=True)
            gray = np.array(render_image_layer(layer, 10))
            np.testing.assert_array_equal(gray[:,:,0], gray[:,:,1])
            self.assertTrue(np.all(gray[:,:,3] == 128))
            layer.tint_color = '#00FF00'
            tinted = np.array(render_image_layer(layer, 10))
            self.assertTrue(np.all(tinted[:,:,1] == 255))
            self.assertTrue(np.all(tinted[:,:,3] == 128))
            layer.height_mm = -2
            with self.assertRaises(ValueError): render_image_layer(layer, 10)


if __name__ == '__main__': unittest.main()
