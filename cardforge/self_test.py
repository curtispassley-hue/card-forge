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
        app = CardForgeApp(recovery_enabled=False)
        errors = []
        app.report_callback_exception = lambda *args: errors.append(str(args))
        app.geometry('1180x760')
        app.update()
        assert app.design_canvas.winfo_width() >= 400
        # Buttons must retain visible labels at the minimum supported size.
        from tkinter import ttk
        def check_layout(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and child.winfo_ismapped():
                    assert child.winfo_width()+5 >= child.winfo_reqwidth(), child.cget('text')
                check_layout(child)
        check_layout(app)
        app.geometry('1180x660');app.update();check_layout(app)
        assert app.background_button.winfo_rooty()+app.background_button.winfo_height()<=app.winfo_rooty()+app.winfo_height()
        app.geometry('1180x760');app.update()
        app.withdraw()
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
        assert not hasattr(app, 'tabs')
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
        app.inspector_vars['width'].set(10)
        app.inspector_vars['name'].set('My badge')
        assert app.commit_selected('width')
        assert app.project.elements[0].width_mm == 10 and app.project.elements[0].name == 'My badge'
        app.undo()
        assert app.project.elements[0].width_mm == 18
        app.redo()
        assert app.project.elements[0].width_mm == 10
        app.rotate_selected(90)
        assert app.project.elements[0].rotation_deg == 90
        app.undo()
        assert app.project.elements[0].rotation_deg == 0
        app.flip_selected('flip_x')
        assert app.project.elements[0].flip_x
        app.aspect_var.set(False)
        app.commit_selected('lock')
        app.inspector_vars['height'].set(6)
        assert app.commit_selected('height')
        assert app.project.elements[0].height_mm == 6
        app.duplicate_selected()
        assert len(app.project.elements) == 3
        app.reorder_selected(-1)
        assert app.selected == ('element', 1)
        app.delete_selected()
        assert len(app.project.elements) == 2
        app.undo()
        assert len(app.project.elements) == 3
        app.select_layer('element', 1)
        app.delete_selected()
        app.select_layer('element', 0)
        # Resize through the same canvas handlers as the corner handles.
        from types import SimpleNamespace
        app.refresh_design_preview()
        hx, hy = app.resize_handles[2]
        origin = app.card_mm_to_canvas(app.project.elements[0].x_mm, app.project.elements[0].y_mm)
        app.design_press(SimpleNamespace(x=hx, y=hy))
        app.design_drag(SimpleNamespace(x=origin[0]+(hx-origin[0])*1.5, y=origin[1]+(hy-origin[1])*1.5))
        app.design_release(SimpleNamespace(x=hx, y=hy))
        assert app.project.elements[0].width_mm > 14
        app.undo()
        assert abs(app.project.elements[0].width_mm-10) < .01
        app.print_view_var.set(True)
        app.refresh_design_preview()
        app.print_view_var.set(False)
        app.grayscale_palette()
        assert app.project.editor.grayscale_artwork
        app.undo()
        assert not app.project.editor.grayscale_artwork
        # The workshop edits a copy until Apply and exports numbered paint assignments.
        app.select_layer('element', 0)
        previous_path = app.project.elements[0].path
        app.open_image_workshop()
        workshop = app.image_workshop
        app.update()
        workshop.editor.select_region((50,50),0)
        workshop.editor.fill(slot=4)
        workshop.cutoff.set(90)
        workshop.apply()
        painted_path = app.project.elements[0].path
        assert painted_path != previous_path and Path(app.project.elements[0].paint_slots_path).exists()
        assert app.project.elements[0].alpha_cutoff == 90
        app.undo(); assert app.project.elements[0].path == previous_path
        app.redo(); assert app.project.elements[0].path == painted_path
        app.open_image_workshop()
        workshop = app.image_workshop
        workshop.reset_image(); workshop.cancel()
        assert app.project.elements[0].path == painted_path
        saved_palette = list(app.project.hueforge.palette)
        saved_background = app.project.face.background_color
        app.grayscale_palette()
        assert app.mode_button.cget('text') == 'Restore color'
        assert app.project.hueforge.palette == saved_palette
        app.grayscale_palette()
        assert not app.project.editor.grayscale_artwork
        assert app.project.hueforge.palette == saved_palette
        with patch('cardforge.gui.colorchooser.askcolor', return_value=((0,170,255),'#00AAFF')):
            app.pick_filament_color(1)
        assert app.project.hueforge.palette[1] == '#00AAFF'
        assert app.project.face.background_color == saved_background
        app.undo(); assert app.project.hueforge.palette == saved_palette
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
        app.select_layer('text', 0)
        app.refresh_design_preview()
        assert app.selected == ('text', 0)
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
        modal = app.grab_current()
        assert isinstance(modal, tk.Toplevel)
        modal.destroy()
        scratch_output = export_face(app.project, td/'scratch-export', include_base=True)
        assert (scratch_output/'CardForge_NFC_Base.stl').exists()
        # Exercise the new controls in the actual GUI and native solid engine.
        from cardforge.core.products import export_product, load_model, model_surfaces
        def click_named(widget, label):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and child.cget('text')==label:
                    child.invoke(); return True
                if click_named(child,label): return True
            return False
        app.start_template('Desktop lightbox')
        app.object_settings(); app.update()
        assert click_named(app.grab_current(),'Apply settings')
        assert app.grab_current() is None
        assert app.project.product.kind=='lightbox'
        app.show_object_preview()
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:
            app.update();time.sleep(.01)
        app.update()
        assert not app.busy and app.object_preview_var.get()
        assert len(app.design_canvas.find_all())==2
        app.show_object_preview();assert not app.object_preview_var.get()
        with patch('cardforge.gui.messagebox.showinfo',side_effect=lambda *a: notices.append(a)), \
             patch('cardforge.gui.messagebox.showerror',side_effect=lambda *a: errors.append(a)):
            app.after(50,lambda: choose_output('Lightbox'))
            app._export_direct(True)
            deadline=time.monotonic()+30
            while app.busy and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            assert not app.busy and (target/'Lightbox'/'Lightbox_Assembly.3mf').exists()
        app.start_template('Wall art')
        assert (export_product(app.project,td,'Plaque')/'Print_Parts'/'Plaque_Artwork.3mf').exists()
        mesh=trimesh.creation.box(extents=(70,50,15))
        mesh_path=td/'target.stl';mesh.export(mesh_path)
        target_mesh=load_model(mesh_path)
        app.surface_dialog(mesh_path,target_mesh,model_surfaces(target_mesh));app.update()
        assert click_named(app.grab_current(),'Use this surface')
        assert app.project.product.kind=='stl_panel'
        assert (export_product(app.project,td,'Attached')/'Attached_Assembly.3mf').exists()
        app.license_dialog();app.update()
        assert click_named(app.grab_current(),'Close')
        with patch('cardforge.licensing.license_status',return_value={'active':False,'message':'Activate to export'}), \
             patch('cardforge.product_ui.messagebox.showinfo'),patch.object(app,'license_dialog'):
            assert not app.export_allowed()
        recovery=td/'Recovery.cardforge'
        app.recovery_enabled=True
        with patch.object(app,'recovery_path',return_value=recovery):
            app.project.name='Recovery test'
            app.autosave();app._autosave_thread.join(10)
            assert not app._autosave_thread.is_alive() and recovery.exists()
            assert Project.load_bundle(recovery,td/'recover-assets').name=='Recovery test'
            app.clear_recovery();assert not recovery.exists()
        app.recovery_enabled=False
        app.destroy()
        assert not errors, errors
        return {'passed': True, 'lightbox_gui_and_export':True, 'wall_art_export':True, 'flat_stl_placement':True, 'object_settings':True, 'actual_mesh_preview':True, 'license_support_panel':True, 'commercial_export_gate':True, 'idle_project_recovery':True, 'small_screen_palette':True, 'paint_apply_cancel_undo': True, 'reversible_grayscale': True, 'independent_background': True, 'single_workspace': True, 'resize_handles': True, 'image_transforms': True, 'layer_ordering': True, 'multiple_png_controls': True, 'named_export_dialog': True, 'grayscale_undo': True, 'portable_image_layers': True, 'scratch_templates': True, 'scratch_save_open_export': True, 'text_dialog': True, 'offline_ocr': recognized, 'geometry': 'watertight, oriented', 'project_roundtrip': True, 'gui_startup': True, 'direct_face_export': True, 'logo_stl_export': True, 'undo_redo': True, 'logo_controls': True, 'responsive_face_export': True}
