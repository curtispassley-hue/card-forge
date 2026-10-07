import tempfile
import unittest
from pathlib import Path
import numpy as np
import trimesh
from cardforge.core.project import Project, TextLayer
from cardforge.core.templates import create_template
from cardforge.core.products import build_product, export_product, load_model, model_surfaces, choose_surface, validate_product


class ProductTests(unittest.TestCase):
    def test_lightbox_solids_do_not_overlap_and_lid_is_printable(self):
        with tempfile.TemporaryDirectory() as td:
            p=create_template('Desktop lightbox')
            parts,accessories=build_product(p)
            self.assertIn('Translucent diffuser',[x['name'] for x in parts])
            self.assertTrue(all(x['mesh'].is_watertight and x['mesh'].is_winding_consistent and x['mesh'].volume>0 for x in parts+accessories))
            shell=next(x['mesh'] for x in parts if x['name']=='Lightbox shell')
            lid=next(x['mesh'] for x in parts if x['name']=='Removable back')
            panel=trimesh.util.concatenate([x['mesh'] for x in parts if x['name'] not in ('Lightbox shell','Removable back')])
            for a,b in ((shell,lid),(shell,panel),(lid,panel)):
                intersection=trimesh.boolean.intersection([a,b],engine='manifold')
                self.assertLess(abs(intersection.volume) if len(intersection.faces) else 0,.01)
            self.assertAlmostEqual(shell.extents[2],p.product.depth_mm,places=4)
            self.assertAlmostEqual(shell.extents[0],p.geometry.card_width_mm,places=3)
            out=export_product(p,td,'My sign')
            self.assertTrue((out/'My_sign_Assembly.3mf').exists())
            self.assertTrue((out/'Print_Parts'/'My_sign_Artwork.3mf').exists())
            rear=trimesh.load_mesh(next((out/'Print_Parts').glob('*_Removable_back.stl')))
            self.assertAlmostEqual(rear.bounds[0,2],0,places=5)
            self.assertAlmostEqual(rear.extents[2],p.product.backing_mm+3,places=4)
            self.assertTrue((out/'Print_Parts'/'Desktop_cradle.stl').exists())
            loaded=Project.load_bundle(out/'My_sign.cardforge',Path(td)/'loaded')
            self.assertEqual(loaded.product.kind,'lightbox')
            self.assertEqual(loaded.product.led_width_mm,8)

    def test_ellipse_wall_art_and_cable_sides_remain_closed(self):
        p=create_template('Wall art');p.product.outline='ellipse'
        parts,_=build_product(p)
        self.assertTrue(all(x['mesh'].is_watertight for x in parts))
        self.assertEqual(parts[-1]['name'],'Plaque backing')
        p=create_template('Wall lightbox');p.product.outline='ellipse'
        for side in ('left','right','bottom'):
            p.product.cable_side=side
            parts,_=build_product(p)
            self.assertTrue(all(x['mesh'].is_watertight for x in parts),side)

    def test_imported_tilted_surface_preserves_target_and_aligns_artwork(self):
        with tempfile.TemporaryDirectory() as td:
            mesh=trimesh.creation.box(extents=(70,50,20))
            mesh.apply_transform(trimesh.transformations.rotation_matrix(.4,[1,1,0]))
            mesh.apply_translation([50,50,30])
            file=Path(td)/'target.stl';mesh.export(file)
            loaded=load_model(file);surfaces=model_surfaces(loaded)
            self.assertEqual(len(surfaces),6)
            p=Project(texts=[TextLayer(text='TEST')])
            s=choose_surface(p,file,'mm',0)
            parts,_=build_product(p)
            np.testing.assert_allclose(parts[0]['mesh'].bounds,loaded.bounds,atol=1e-6)
            inverse=np.linalg.inv(np.asarray(s['transform']))
            artwork=trimesh.util.concatenate([x['mesh'] for x in parts[1:]])
            artwork.apply_transform(inverse)
            self.assertAlmostEqual(artwork.bounds[0,2],p.product.surface_gap_mm,places=5)
            self.assertAlmostEqual(artwork.bounds[1,2],p.face.thickness_mm+p.product.surface_gap_mm,places=5)
            original=trimesh.boolean.intersection([parts[0]['mesh'],parts[-1]['mesh']],engine='manifold')
            self.assertLess(abs(original.volume) if len(original.faces) else 0,.001)
            saved=p.save_bundle(Path(td)/'placed.cardforge');file.unlink()
            restored=Project.load_bundle(saved,Path(td)/'unpacked')
            self.assertTrue(Path(restored.product.model_path).exists())
            self.assertEqual(restored.product.surface_transform,p.product.surface_transform)
            self.assertTrue(build_product(restored)[0])

    def test_invalid_models_and_lighting_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'open.stl'
            mesh=trimesh.creation.box();mesh.update_faces(np.arange(len(mesh.faces)-1));mesh.export(file)
            with self.assertRaises(ValueError): load_model(file)
            file=Path(td)/'sphere.stl';trimesh.creation.icosphere(subdivisions=2,radius=30).export(file)
            p=Project()
            with self.assertRaisesRegex(ValueError,'flat surface'): choose_surface(p,file,'mm',0)
        p=create_template('Desktop lightbox');p.product.depth_mm=15
        with self.assertRaisesRegex(ValueError,'rear lid'): validate_product(p)
        p.product.depth_mm=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'): validate_product(p)

    def test_diffuser_gets_a_distinct_material_slot_in_face_only_export(self):
        import zipfile
        from lxml import etree
        from cardforge.core.face import export_face
        from cardforge.core.colors import export_palette
        p=create_template('Desktop lightbox');p.product.diffuser_color='#AABBCC'
        self.assertIn('#AABBCC',export_palette(p))
        with tempfile.TemporaryDirectory() as td:
            out=export_face(p,td,output_name='Diffuser')
            with zipfile.ZipFile(out/'Diffuser_Face.3mf') as z:
                root=etree.fromstring(z.read('Metadata/model_settings.config'))
            nodes=root.findall('.//part')
            diffuser=next(n for n in nodes if n.find("metadata[@key='name']").get('value')=='Translucent diffuser')
            extruder=diffuser.xpath('./*[local-name()="metadata"][@key="extruder"]')[0]
            self.assertEqual(int(extruder.get('value')),export_palette(p).index('#AABBCC')+1)
        p.product.body_color='red'
        with self.assertRaisesRegex(ValueError,'RRGGBB'): validate_product(p)

    def test_mesh_preview_preserves_readable_complete_front_artwork(self):
        from cardforge.product_ui import mesh_preview
        from cardforge.core.face import face_preview
        from PIL import Image
        p=create_template('Desktop lightbox');parts,_=build_product(p)
        rendered=np.array(mesh_preview(parts,600,400,yaw=0,pitch=0,face_down=True))
        # At this aspect ratio the 150x100 shell occupies 510x340 pixels.
        # Compare only the inset face; discard the black outer shell rim.
        x0,y0=45,30
        fw=p.geometry.card_width_mm-2*(p.geometry.face_border_mm+p.geometry.face_clearance_mm)
        fh=p.geometry.card_height_mm-2*(p.geometry.face_border_mm+p.geometry.face_clearance_mm)
        inset=round((p.geometry.face_border_mm+p.geometry.face_clearance_mm)*3.4)
        face=rendered[y0+inset:370-inset,x0+inset:555-inset]
        expected=np.array(face_preview(p).resize((face.shape[1],face.shape[0]),Image.Resampling.NEAREST))
        # Center excludes the rounded rim; a mirrored or partly hidden text
        # yields low agreement. This catches the former triangle painter bug.
        crop=(slice(face.shape[0]//3,face.shape[0]*2//3),slice(face.shape[1]//5,face.shape[1]*4//5))
        actual=(face[crop]<80).all(2);wanted=(expected[crop]<80).all(2)
        self.assertGreater((actual&wanted).sum()/max(1,(actual|wanted).sum()),.9)

    def test_old_project_defaults_to_card_and_missing_assets_do_not_save(self):
        old=Project.from_dict({'format_version':'0.4.0'})
        self.assertEqual(old.product.kind,'nfc_card')
        old.logo.path='missing.png'
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'old.cardforge'
            with self.assertRaisesRegex(ValueError,'missing'): old.save_bundle(file)
            self.assertFalse(file.exists())


if __name__=='__main__': unittest.main()
