import tempfile
import unittest
from pathlib import Path
import numpy as np
import trimesh
from cardforge.core.project import Project
from cardforge.core.geometry import build_nfc_base, import_hueforge_models, normalize_face_meshes, make_face_blank


class RegressionTests(unittest.TestCase):
    def test_face_solid(self):
        mesh = make_face_blank(Project().geometry, 0.8)
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_winding_consistent)
        self.assertGreater(mesh.volume, 0)

    def test_nfc_depth_and_solid(self):
        p = Project()
        m = build_nfc_base(p.geometry, p.nfc)
        self.assertTrue(m.is_watertight)
        self.assertTrue(m.is_winding_consistent)
        self.assertGreater(m.volume, 0)
        expected = p.geometry.base_thickness_mm - p.geometry.face_recess_depth_mm - p.nfc.thickness_mm - p.nfc.clearance_mm
        self.assertTrue(np.isclose(m.vertices[:, 2], expected).any())
        p.nfc.x_mm = 0
        with self.assertRaises(ValueError):
            build_nfc_base(p.geometry, p.nfc)

    def test_3mf_placements_and_portable_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            scene = trimesh.Scene()
            for x in (0, 12):
                matrix = np.eye(4)
                matrix[:3, 3] = [x, 0, 0.4]
                scene.add_geometry(trimesh.creation.box([10, 8, 0.8]), transform=matrix)
            src = td/'face.3mf'
            src.write_bytes(scene.export(file_type='3mf'))
            meshes = import_hueforge_models(src)
            self.assertEqual(len(meshes), 2)
            self.assertAlmostEqual(trimesh.util.concatenate(meshes).extents[0], 22)
            normalized = normalize_face_meshes(meshes, Project().geometry)
            self.assertAlmostEqual(normalized[0].extents[2], 0.8)
            p = Project(hueforge_import_path=str(src))
            bundle = p.save_bundle(td/'portable.cardforge')
            src.unlink()
            restored = Project.load_bundle(bundle)
            self.assertEqual(len(import_hueforge_models(restored.hueforge_import_path)), 2)


if __name__ == '__main__':
    unittest.main()
