"""Exercise the actual packaged runtime, including OCR with networking disabled."""
def run():
    import socket
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from PIL import Image, ImageDraw, ImageFont
    from cardforge.core.ocr import ocr_candidates
    from cardforge.core.project import Project
    from cardforge.core.geometry import build_nfc_base, make_face_blank, import_hueforge_models
    from cardforge.gui import CardForgeApp
    import trimesh
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        p = Project()
        base = build_nfc_base(p.geometry, p.nfc)
        assert base.is_watertight and base.is_winding_consistent and base.volume > 0
        face = make_face_blank(p.geometry, 0.8)
        model = td/'face.3mf'
        model.write_bytes(trimesh.Scene(face).export(file_type='3mf'))
        assert import_hueforge_models(model)
        p.hueforge_import_path = str(model)
        project = p.save_bundle(td/'test.cardforge')
        assert Path(Project.load_bundle(project).hueforge_import_path).exists()
        im = Image.new('RGB', (1000, 220), 'white')
        ImageDraw.Draw(im).text((40, 70), 'CARDFORGE TEST 123', font=ImageFont.truetype('arial.ttf', 60), fill='black')
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Offline self-test: network disabled')):
            lines = ocr_candidates(im, 88.9, 50.8)
        recognized = ' '.join(x.text for x in lines).upper()
        assert 'CARDFORGE' in recognized and '123' in recognized, recognized
        app = CardForgeApp()
        app.withdraw()
        errors = []
        app.report_callback_exception = lambda *args: errors.append(str(args))
        app.update()
        app.run_checks()
        app.destroy()
        assert not errors, errors
        return {'passed': True, 'offline_ocr': recognized, 'geometry': 'watertight, oriented', 'project_roundtrip': True, 'gui_startup': True, '3mf_import': True}
