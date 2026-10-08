import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw
from cardforge.core.painting import PixelEditor
from cardforge.core.project import Project, LogoLayer, TextLayer
from cardforge.core.colors import effective_palette, text_color, export_palette
from cardforge.core.artwork import source_slots
from cardforge.core.face import artwork_masks, build_face, export_3mf, face_preview


def islands():
    im = Image.new('RGBA', (80, 40))
    d = ImageDraw.Draw(im)
    d.rectangle((5, 5, 24, 34), fill='#D92D20')
    d.rectangle((50, 5, 69, 34), fill='#D92D20')
    return im


class PaintTests(unittest.TestCase):
    def test_adjacent_regions_remain_independent_after_matching_filaments(self):
        im=Image.new('RGBA',(40,20),'#D92D20');ImageDraw.Draw(im).rectangle((20,0,39,19),fill='#0044AA')
        e=PixelEditor(im);palette=['#111111','#00FF00','#111111','#FFFFFF']
        e.select_region((5,5),0,True,palette);e.fill(slot=1)
        e.select_region((25,5),0,True,palette);e.fill(slot=1)
        # No clear-selection step. Matching displayed color must not join regions.
        e.select_region((25,5),0,True,palette)
        self.assertEqual(e.selection.sum(),400)
        e.fill(slot=4)
        self.assertEqual(e.slots.getpixel((5,5)),1)
        self.assertEqual(e.slots.getpixel((25,5)),4)
        e.undo();self.assertEqual(e.slots.getpixel((25,5)),1)
        e.select_region((5,5),0,True,palette,source='display')
        self.assertEqual(e.selection.sum(),800)  # Explicit displayed-color mode.

    def test_outline_preserves_selected_interior_color_and_modifiers(self):
        from cardforge.core.painting import selection_outline
        e=PixelEditor(islands());e.select_region((10,10),0)
        e.select_region((55,10),0,operation='add');self.assertEqual(e.selection.sum(),1200)
        e.select_region((10,10),0,operation='subtract');self.assertEqual(e.selection.sum(),600)
        e.select_region((10,10),0);self.assertFalse(e.selection[10,55])
        e.fill(slot=2);preview=e.preview(['#111111','#F4C430','#D92D20','#FFFFFF'])
        outlined=selection_outline(preview,e.selection)
        self.assertEqual(outlined.getpixel((10,10)),preview.getpixel((10,10)))
        self.assertIn(outlined.getpixel((5,5)),[(0,0,0,255),(255,255,255,255)])

    def test_connected_selection_paints_one_element_and_undo_restores(self):
        e = PixelEditor(islands())
        e.select_region((10,10),0,True)
        self.assertEqual(e.selection.sum(),600)
        e.fill(slot=2)
        self.assertEqual(e.slots.getpixel((10,10)),2)
        self.assertEqual(e.slots.getpixel((55,10)),0)
        self.assertEqual(e.preview(['#111111','#00FF00','#D92D20','#F4C430']).getpixel((10,10)),(0,255,0,255))
        e.undo(); self.assertEqual(e.slots.getpixel((10,10)),0)
        e.redo(); self.assertEqual(e.slots.getpixel((10,10)),2)
        e.select_region((55,10),0,False)  # Original colors: both islands.
        self.assertEqual(e.selection.sum(),1200)

    def test_edges_constrain_brush_and_restore_original_pixels(self):
        e = PixelEditor(islands())
        e.select_region((10,10),0)
        e.refine('shrink',2)
        count = e.selection.sum()
        self.assertLess(count,600)
        e.remember(); e.stroke((0,10),(79,10),5,'erase')
        self.assertEqual(e.image.getpixel((10,10))[3],0)
        self.assertEqual(e.image.getpixel((55,10))[3],255)
        e.fill('restore'); self.assertEqual(e.image.getpixel((10,10)),(217,45,32,255))
        e.refine('grow',3); self.assertGreater(e.selection.sum(),count)
        e.refine('smooth'); self.assertTrue(e.selection.any())
        e.selection = None; e.remember(); e.stroke((30,20),(45,20),3,'paint',4)
        self.assertEqual(e.slots.getpixel((35,20)),4)
        self.assertEqual(e.image.getpixel((35,20))[3],255)
        e.undo(); self.assertEqual(e.image.getpixel((35,20))[3],0)

    def test_slots_background_grayscale_and_portable_assets_are_independent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            e = PixelEditor(islands()); e.select_region((10,10),0); e.fill(slot=2)
            for name, im in [('image',e.image),('slots',e.slots),('original',e.original)]: im.save(root/(name+'.png'))
            layer = LogoLayer(path=str(root/'image.png'),paint_slots_path=str(root/'slots.png'),
                              edit_source_path=str(root/'original.png'),width_mm=16,rotation_deg=17)
            p = Project(elements=[layer],texts=[TextLayer(text='TEST',filament_slot=1)])
            p.face.background_color = '#00AABB'
            before = artwork_masks(p)[0]
            p.hueforge.palette[1] = '#5533FF'
            after = artwork_masks(p)[0]
            for a,b in zip(before,after): np.testing.assert_array_equal(a[2],b[2])
            self.assertEqual(text_color(p.texts[0],p),'#5533FF')
            self.assertEqual(p.face.background_color,'#00AABB')
            original_slots = np.asarray(source_slots(layer,reference=p.hueforge.mapping_palette)[1]).copy()
            palette = list(p.hueforge.palette)
            p.editor.grayscale_artwork = True
            self.assertEqual(p.hueforge.palette,palette)
            self.assertNotEqual(effective_palette(p),palette)
            p.editor.grayscale_artwork = False
            self.assertEqual(effective_palette(p),palette)
            np.testing.assert_array_equal(original_slots, source_slots(layer,reference=p.hueforge.mapping_palette)[1])
            saved = p.save_bundle(root/'painted.cardforge')
            for path in root.glob('*.png'): path.unlink()
            restored = Project.load_bundle(saved,root/'loaded')
            for attr in ('path','paint_slots_path','edit_source_path'): self.assertTrue(Path(getattr(restored.elements[0],attr)).exists())
            self.assertEqual(restored.texts[0].filament_slot,1)
            parts = build_face(restored)
            self.assertTrue(all(part['mesh'].is_watertight for part in parts))
            self.assertEqual(parts[0]['color'],'#00AABB'); self.assertEqual(parts[-1]['color'],'#00AABB')
            self.assertEqual(export_palette(restored)[4],'#00AABB')
            out = root/'face.3mf'; export_3mf(parts,out,export_palette(restored))
            with zipfile.ZipFile(out) as z:
                config = ET.fromstring(z.read('Metadata/model_settings.config'))
            background = config.find('object/part')
            self.assertEqual(background.find("metadata[@key='extruder']").attrib['value'],'5')
            preview = face_preview(restored)
            self.assertIn((0,170,187), list(preview.getdata()))

    def test_alpha_threshold_keeps_soft_edges_without_spurious_color(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'soft.png'
            im = Image.new('RGBA',(30,30)); d=ImageDraw.Draw(im)
            d.rectangle((3,3,26,26),fill=(217,45,32,100)); d.rectangle((10,10,19,19),fill=(217,45,32,255)); im.save(path)
            p = Project(elements=[LogoLayer(path=str(path),width_mm=10)])
            masks = artwork_masks(p)[0]
            high = sum(m.sum() for _,_,m in masks)
            self.assertEqual([c for _,c,m in masks if m.any()],['#D92D20'])
            p.elements[0].alpha_cutoff = 50
            low = sum(m.sum() for _,_,m in artwork_masks(p)[0])
            self.assertGreater(low,high)

    def test_legacy_custom_palette_is_the_mapping_reference(self):
        colors = ['#223344','#556677','#8899AA','#CCDDEE']
        p = Project.from_dict({'hueforge':{'palette':colors}})
        self.assertEqual(p.hueforge.mapping_palette,colors)
        p.hueforge.palette[0] = '#FF0000'
        self.assertEqual(p.hueforge.mapping_palette[0],'#223344')


if __name__ == '__main__': unittest.main()
