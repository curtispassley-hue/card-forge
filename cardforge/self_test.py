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
    from cardforge.core.face import export_face
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
        # Multiple PNGs use the real file picker action and editable controls.
        icon = td/'Badge.png'
        badge = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(badge).ellipse((10, 10, 90, 90), fill='#D92D20')
        badge.save(icon)
        emblem = td/'Emblem.png'
        badge.save(emblem)
        with patch('cardforge.gui.filedialog.askopenfilenames', return_value=(str(icon), str(emblem))):
            app.load_elements()
        assert len(app.project.elements) == 2
        app.element_w.set(10)
        app.element_name.set('My badge')
        app.apply_element()
        assert app.project.elements[0].width_mm == 10 and app.project.elements[0].name == 'My badge'
        app.undo()
        assert app.project.elements[0].width_mm == 12
        app.redo()
        assert app.project.elements[0].width_mm == 10
        app.grayscale_palette()
        assert app.project.editor.grayscale_artwork
        app.undo()
        assert not app.project.editor.grayscale_artwork
        target = td/'face-output'
        target.mkdir()
        notices = []
        # Drive the actual export modal, including destination and package name.
        def choose_output(name):
            app.output_name_var.set(name)
            app.output_dir_var.set(str(target))
            import tkinter as tk
            def visit(widget):
                for child in widget.winfo_children():
                    if isinstance(child, __import__('tkinter.ttk', fromlist=['Button']).Button) and child.cget('text') == 'Export files':
                        child.invoke()
                        return True
                    if visit(child): return True
                return False
            for child in app.winfo_children():
                if isinstance(child, tk.Toplevel) and visit(child): return
            errors.append('Export dialog button was not found')
        with patch('cardforge.gui.filedialog.askdirectory', return_value=str(target)), \
             patch('cardforge.gui.messagebox.showinfo', side_effect=lambda *a: notices.append(a)), \
             patch('cardforge.gui.messagebox.showerror', side_effect=lambda *a: errors.append(a)):
            app.after(50, lambda: choose_output('SampleFace'))
            app.export_face_files()
            assert app.busy
            ticks = 0
            deadline = time.monotonic() + 30
            while app.busy and time.monotonic() < deadline:
                app.update()
                ticks += 1
                time.sleep(0.01)
            assert not app.busy and ticks > 1 and notices, (ticks, notices, errors)
        face_output = target/'SampleFace'
        assert (face_output/'SampleFace_Face.3mf').exists()
        assert (face_output/'SampleFace_Parts.json').exists()
        assert (face_output/'Aligned_STLs').is_dir()
        with patch('cardforge.gui.filedialog.askdirectory', return_value=str(target)), \
             patch('cardforge.gui.messagebox.showinfo', side_effect=lambda *a: notices.append(a)), \
             patch('cardforge.gui.messagebox.showerror', side_effect=lambda *a: errors.append(a)):
            app.after(50, lambda: choose_output('SampleLogo'))
            app.export_logo_stl()
            deadline = time.monotonic() + 30
            while app.busy and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert not app.busy and (target/'SampleLogo'/'SampleLogo_Logo.3mf').exists()
        portable_images = app.project.save_bundle(td/'images.cardforge')
        assert len(Project.load_bundle(portable_images, td/'loaded-images').elements) == 2
        # A complete design without a reference photo, through GUI save/open.
        app.start_template('Business card')
        assert app.project.source_image == '' and len(app.project.texts) == 4
        app.update()
        assert app.canvas_views['design']['view_w'] > 0
        portable = td/'scratch.cardforge'
        with patch('cardforge.gui.filedialog.asksaveasfilename', return_value=str(portable)):
            assert app.save_project()
        app.new_project()
        with patch('cardforge.gui.filedialog.askopenfilename', return_value=str(portable)):
            app.open_project()
        assert len(app.project.texts) == 4 and not app.project.source_image
        app.text_list.selection_set(0)
        app.refresh_design_preview()
        assert app.text_list.curselection() == (0,)
        app.duplicate_text()
        assert len(app.project.texts) == 5
        app.undo()
        assert len(app.project.texts) == 4
        app.text_dialog(0)
        app.update()
        # The self-test intentionally keeps the root withdrawn.  Tk therefore
        # reports a dialog as not viewable even though it was created and owns
        # the input grab; inspect the actual child window instead.
        import tkinter as tk
        modals = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
        assert modals and modals[0].grab_current() is not None
        modal = modals[0]
        modal.destroy()
        scratch_output = export_face(app.project, td/'scratch-export', include_base=True)
        assert (scratch_output/'CardForge_NFC_Base.stl').exists()
        app.destroy()
        assert not errors, errors
        return {'passed': True, 'multiple_png_controls': True, 'named_export_dialog': True, 'grayscale_undo': True, 'portable_image_layers': True, 'scratch_templates': True, 'scratch_save_open_export': True, 'text_dialog': True, 'offline_ocr': recognized, 'geometry': 'watertight, oriented', 'project_roundtrip': True, 'gui_startup': True, 'direct_face_export': True, 'logo_stl_export': True, 'undo_redo': True, 'logo_controls': True, 'step_navigation': True, 'responsive_face_export': True}
