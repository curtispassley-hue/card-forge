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
        # Exercise real editor controls and keep the event loop alive during export.
        from unittest.mock import patch
        import time
        art = td/'source.png'
        im.save(art)
        logo = td/'logo.png'
        im.save(logo)
        app.project.source_image = str(art)
        app.project.logo.path = str(logo)
        width = app.project.logo.width_mm
        app.scale_logo(1.1)
        assert app.project.logo.width_mm > width
        app.undo()
        assert app.project.logo.width_mm == width
        app.redo()
        assert app.project.logo.width_mm > width
        app.clean_logo_background()
        cleaned = app.project.logo.path
        assert cleaned != str(logo)
        app.undo()
        assert app.project.logo.path == str(logo)
        app.navigate(1)
        assert app.tabs.index(app.tabs.select()) == 1
        app.navigate(-1)
        assert app.tabs.index(app.tabs.select()) == 0
        target = td/'handoff'
        notices = []
        with patch('cardforge.gui.filedialog.askdirectory', return_value=str(target)), \
             patch('cardforge.gui.messagebox.showinfo', side_effect=lambda *a: notices.append(a)), \
             patch('cardforge.gui.messagebox.showerror', side_effect=lambda *a: errors.append(a)):
            app.export_hueforge()
            assert app.busy
            ticks = 0
            deadline = time.monotonic() + 30
            while app.busy and time.monotonic() < deadline:
                app.update()
                ticks += 1
                time.sleep(0.01)
            assert not app.busy and ticks > 1 and notices, (ticks, notices)
        assert (target/'CardForge_HueForge_Source.png').exists()
        assert (target/'CardForge_4Filament_Preview.png').exists()
        app.destroy()
        assert not errors, errors
        return {'passed': True, 'offline_ocr': recognized, 'geometry': 'watertight, oriented', 'project_roundtrip': True, 'gui_startup': True, '3mf_import': True, 'undo_redo': True, 'logo_controls': True, 'step_navigation': True, 'responsive_hueforge_export': True}
