"""Single-workspace desktop editor and selected-layer inspector."""
from dataclasses import asdict
from pathlib import Path
import copy
import math
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk
from .core.project import LogoLayer
from .core.artwork import image_size_mm
from .core.face import face_preview
from .core.logo import remove_logo_background
from .core.templates import TEMPLATES
from .core.fonts import default_font
from .core.colors import effective_palette


class StudioWorkspace:
    def _style(self):
        self.configure(bg='#eef2f6')
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', font=('Segoe UI', 10), background='#eef2f6', foreground='#203149')
        s.configure('TButton', padding=(10, 7), relief='flat')
        s.configure('Secondary.TButton', background='#e2e9f1', foreground='#24364f', padding=(10, 7), borderwidth=0)
        s.map('Secondary.TButton', background=[('active', '#cddce9')])
        s.configure('Accent.TButton', background='#087f8c', foreground='white', padding=(12, 8), borderwidth=0, font=('Segoe UI', 10, 'bold'))
        s.map('Accent.TButton', background=[('active', '#056570'), ('disabled', '#8eafb2')])
        s.configure('Danger.TButton', background='#fbe9e8', foreground='#9d3333', padding=(10, 7))
        s.configure('Title.TLabel', font=('Segoe UI', 19, 'bold'))
        s.configure('Step.TLabel', font=('Segoe UI', 9, 'bold'), foreground='#087f8c')
        s.configure('Muted.TLabel', foreground='#65768a')
        s.configure('TEntry', padding=6, fieldbackground='white', bordercolor='#cbd5e1')
        s.configure('TSpinbox', padding=5, fieldbackground='white', bordercolor='#cbd5e1')
        s.configure('TCombobox', padding=5, fieldbackground='white')
        s.configure('Section.TLabelframe', padding=10, relief='solid', borderwidth=1)
        s.configure('Section.TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        s.configure('Treeview', rowheight=36, font=('Segoe UI', 10), background='white', fieldbackground='white', borderwidth=0)
        s.map('Treeview', background=[('selected', '#d5eef0')], foreground=[('selected', '#075560')])

    def _tool_window(self, title, geometry):
        win = tk.Toplevel(self)
        win.withdraw()
        win.title(title)
        win.geometry(geometry)
        win.transient(self)
        win.protocol('WM_DELETE_WINDOW', win.withdraw)
        panel = ttk.Frame(win, padding=16)
        panel.pack(fill='both', expand=True)
        return win, panel

    def _build_ui(self):
        self.selected = None
        self._inspector_sync = False
        self._inspector_baseline = None
        self._canvas_job = None
        self._resize_handle = None
        self.zoom_var = tk.DoubleVar(value=1)
        self.print_view_var = tk.BooleanVar(value=False)
        self.object_preview_var = tk.BooleanVar(value=False)
        self.inspector_error = tk.StringVar()
        self.document_var = tk.StringVar(value='Untitled card')
        self.snap_var = tk.DoubleVar(value=.25)
        self.show_nfc_var = tk.BooleanVar(value=False)
        self.grayscale_var = tk.BooleanVar(value=False)
        self.face_thickness = tk.DoubleVar()
        self.transparent_cap = tk.DoubleVar()
        self.output_name_var = tk.StringVar(value='My_Card')
        self.output_dir_var = tk.StringVar()
        # These variables retain compatibility with photo extraction / old projects.
        self.logo_x, self.logo_y, self.logo_w = tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        self.logo_opacity = tk.DoubleVar(value=100)
        self.logo_enabled_var = tk.BooleanVar(value=True)
        self.bg_tolerance = tk.DoubleVar(value=34)
        self.ocr_status_var = tk.StringVar()

        header = tk.Frame(self, bg='#132439', padx=18, pady=13)
        header.pack(fill='x')
        tk.Label(header, text='CARDFORGE', bg='#132439', fg='white', font=('Segoe UI', 19, 'bold')).pack(side='left')
        tk.Label(header, text='STUDIO  /  1.0 RC', bg='#132439', fg='#8bb7c3', font=('Segoe UI', 9, 'bold')).pack(side='left', padx=18)
        self._button(header, 'Export object', self.export_assembly, 'download', 'Accent.TButton').pack(side='right', padx=(8, 0))
        self._button(header, 'Save project', self.save_project, 'save').pack(side='right', padx=(8, 0))
        self._button(header, 'Open', self.open_project, 'folder').pack(side='right')
        self._button(header, 'License', self.license_dialog, 'settings').pack(side='right',padx=6)

        toolbar = ttk.Frame(self, padding=(16, 10)); toolbar.pack(fill='x')
        new = ttk.Menubutton(toolbar, text='New project ▾', style='Secondary.TButton')
        menu = tk.Menu(new, tearoff=False)
        for name in TEMPLATES:
            menu.add_command(label=name, command=lambda n=name: self.start_template(n))
        menu.add_separator()
        menu.add_command(label='Artwork on imported STL…', command=self.import_stl_target)
        new.configure(menu=menu); new.pack(side='left', padx=(0, 8))
        self._button(toolbar, 'Add image', self.load_elements, 'image').pack(side='left', padx=(0, 6))
        self._button(toolbar, 'Add text', self.add_text, 'text').pack(side='left')
        self._button(toolbar, 'Undo', self.undo, 'undo').pack(side='left', padx=(20, 6))
        self._button(toolbar, 'Redo', self.redo, 'redo').pack(side='left')
        self._button(toolbar, 'Object settings', self.object_settings, 'settings').pack(side='right')
        self._button(toolbar, 'Photo tools', lambda: self.show_tool('photo'), 'crop').pack(side='right', padx=6)

        body = ttk.Frame(self, padding=(14, 0, 14, 0)); body.pack(fill='both', expand=True)
        layers = ttk.Frame(body, width=212, padding=(0, 6, 12, 0)); layers.pack(side='left', fill='y')
        layers.pack_propagate(False)
        ttk.Label(layers, text='LAYERS', style='Step.TLabel').pack(anchor='w', pady=(0, 7))
        ttk.Label(layers, text='Select an item to edit it.', style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        self.layer_tree = ttk.Treeview(layers, show='tree', selectmode='browse')
        self.layer_tree.column('#0', width=190, stretch=True)
        self.layer_tree.pack(fill='both', expand=True)
        self.layer_tree.tag_configure('hidden', foreground='#92a1b0')
        self.layer_tree.bind('<<TreeviewSelect>>', self._tree_selected)
        self.layer_tree.bind('<Double-1>', lambda e: self.edit_selected_text() if self.selected and self.selected[0] == 'text' else None)
        row = ttk.Frame(layers); row.pack(fill='x', pady=(8, 4))
        self._button(row, 'Duplicate', self.duplicate_selected, 'layers').pack(side='left', fill='x', expand=True)
        self._button(row, 'Delete', self.delete_selected, 'delete', 'Danger.TButton').pack(side='right', padx=(4, 0))
        row = ttk.Frame(layers); row.pack(fill='x', pady=4)
        self._button(row, 'Forward', lambda: self.reorder_selected(1), 'up').pack(side='left', expand=True, fill='x')
        self._button(row, 'Backward', lambda: self.reorder_selected(-1), 'down').pack(side='right', expand=True, fill='x', padx=(4, 0))
        ttk.Label(layers, text='Top layers appear in front.\nImages sit above text.', style='Muted.TLabel').pack(anchor='w', pady=8)

        inspector_shell = ttk.Frame(body, width=282)
        inspector_shell.pack(side='right', fill='y', padx=(12, 0))
        self._build_inspector(inspector_shell)
        center = ttk.Frame(body); center.pack(fill='both', expand=True)
        top = ttk.Frame(center, padding=(8, 6)); top.pack(fill='x')
        ttk.Label(top, textvariable=self.document_var, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self._button(top,'2D / 3D',self.show_object_preview,'layers').pack(side='right',padx=(8,0))
        ttk.Checkbutton(top, text='Print colors', variable=self.print_view_var, command=self.refresh_design_preview).pack(side='right')
        stage = ttk.Frame(center); stage.pack(fill='both', expand=True)
        self.design_canvas = tk.Canvas(stage, bg='#dce4ed', highlightthickness=0, cursor='arrow')
        vertical = ttk.Scrollbar(stage, orient='vertical', command=self.design_canvas.yview)
        horizontal = ttk.Scrollbar(center, orient='horizontal', command=self.design_canvas.xview)
        vertical.pack(side='right', fill='y'); self.design_canvas.pack(fill='both', expand=True)
        horizontal.pack(fill='x')
        self.design_canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        for event, handler in [('<ButtonPress-1>', self.design_press), ('<B1-Motion>', self.design_drag), ('<ButtonRelease-1>', self.design_release)]:
            self.design_canvas.bind(event, handler)
        self.design_canvas.bind('<Configure>', self._schedule_canvas)
        self.design_canvas.bind('<ButtonPress-2>', lambda e: self.design_canvas.scan_mark(e.x, e.y))
        self.design_canvas.bind('<B2-Motion>', lambda e: self.design_canvas.scan_dragto(e.x, e.y, gain=1))
        self.design_canvas.bind('<Delete>', lambda e: self.delete_selected())
        for key, dx, dy in [('Left', -1, 0), ('Right', 1, 0), ('Up', 0, 1), ('Down', 0, -1)]:
            self.design_canvas.bind('<'+key+'>', lambda e, x=dx, y=dy: self.nudge_selected(x, y, bool(e.state & 1)))
        bottom = ttk.Frame(center, padding=(6, 8)); bottom.pack(fill='x')
        ttk.Checkbutton(bottom, text='NFC guide', variable=self.show_nfc_var, command=self.refresh_design_preview).pack(side='left')
        ttk.Label(bottom, text='Snap mm', style='Muted.TLabel').pack(side='left', padx=(8, 4))
        ttk.Entry(bottom, textvariable=self.snap_var, width=5).pack(side='left')
        self._button(bottom, 'Fit', self.fit_canvas, 'search').pack(side='right')
        ttk.Scale(bottom, from_=.6, to=2.5, variable=self.zoom_var, command=self._schedule_canvas, length=100).pack(side='right', padx=6)
        self.canvas_hint = ttk.Label(center, text='Drag to move • Corner handles resize • Arrow keys nudge • Middle-drag pans', style='Muted.TLabel', wraplength=500)
        self.canvas_hint.pack(anchor='w', pady=(0, 8))

        palette = ttk.Frame(self, padding=(18, 10)); palette.pack(fill='x')
        ttk.Label(palette, text='FILAMENTS', style='Step.TLabel').pack(side='left', padx=(0, 12))
        self.color_buttons, self.filament_name_vars = [], []
        for i in range(4):
            v = tk.StringVar(); self.filament_name_vars.append(v)
            b = tk.Button(palette, text=str(i+1), width=8, relief='flat', bd=0, padx=5, pady=6,
                          command=lambda index=i: self.pick_filament_color(index))
            b.pack(side='left', padx=(0, 5)); self.color_buttons.append(b)
        self.background_button = tk.Button(palette, text='5  Background', relief='flat', bd=0, padx=8, pady=6, command=self.pick_face_background)
        self.background_button.pack(side='left', padx=(6, 8))
        self.mode_button = self._button(palette, 'Grayscale', self.grayscale_palette)
        self.mode_button.pack(side='left')
        self._button(palette, 'Reset colors', self.reset_filaments).pack(side='left', padx=4)
        self._button(palette, 'Print checks', lambda: self.show_tool('checks'), 'check').pack(side='right')
        self._button(palette, 'Face only', self.export_face_files, 'download').pack(side='right', padx=6)
        self.progress = ttk.Progressbar(self, mode='indeterminate'); self.progress.pack(fill='x', padx=18)
        ttk.Label(self, textvariable=self.status, padding=(18, 6), style='Muted.TLabel').pack(fill='x')

        self.photo_window, self.source_tab = self._tool_window('Photo import & tracing', '1100x730')
        self._source_ui()
        self.card_window, self.assembly_tab = self._tool_window('Card dimensions & NFC pocket', '1050x750')
        face = ttk.LabelFrame(self.assembly_tab, text='Flush face layers', padding=8)
        face.pack(fill='x', pady=(0, 12))
        self._field(face, 'Total face thickness (mm)', self.face_thickness)
        self._field(face, 'Front color depth (mm)', self.transparent_cap)
        self._assembly_ui()
        self.check_window, self.check_tab = self._tool_window('Printability checks', '850x650')
        self._check_ui()
        self.hf_preview_canvas = self.design_canvas

    def _build_inspector(self, shell):
        canvas = tk.Canvas(shell, width=276, bg='#eef2f6', highlightthickness=0)
        bar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        bar.pack(side='right', fill='y'); canvas.pack(fill='both', expand=True)
        panel = ttk.Frame(canvas, padding=(8, 6, 10, 10))
        item = canvas.create_window(0, 0, window=panel, anchor='nw')
        panel.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        def wheel(e):
            w = e.widget
            while w is not None:
                if w == shell:
                    canvas.yview_scroll(-int(e.delta/120), 'units'); break
                w = getattr(w, 'master', None)
        self.bind('<MouseWheel>', wheel, add='+')
        ttk.Label(panel, text='SELECTED ITEM', style='Step.TLabel').pack(anchor='w', pady=(0, 8))
        self.selected_name_var = tk.StringVar(value='Select an image or text')
        ttk.Label(panel, textvariable=self.selected_name_var, font=('Segoe UI', 13, 'bold'), wraplength=240).pack(anchor='w', pady=(0, 12))
        self.inspector_content = ttk.Frame(panel)
        self.inspector_vars = {k: tk.StringVar() for k in ('name', 'x', 'y', 'width', 'height', 'rotation')}
        self.aspect_var, self.visible_var = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.image_gray_var = tk.BooleanVar(value=False)
        self._inspect_field(self.inspector_content, 'Name', 'name', numeric=False)
        self._inspect_field(self.inspector_content, 'Center X · mm', 'x')
        self._inspect_field(self.inspector_content, 'Center Y · mm', 'y')
        ttk.Checkbutton(self.inspector_content, text='Visible in print', variable=self.visible_var, command=self.commit_selected).pack(anchor='w', pady=6)
        self.image_inspector = ttk.Frame(self.inspector_content)
        ttk.Separator(self.image_inspector).pack(fill='x', pady=10)
        ttk.Label(self.image_inspector, text='SIZE & TRANSFORM', style='Step.TLabel').pack(anchor='w', pady=(0, 6))
        self._inspect_field(self.image_inspector, 'Width · mm', 'width')
        self._inspect_field(self.image_inspector, 'Height · mm', 'height')
        ttk.Checkbutton(self.image_inspector, text='Lock proportions', variable=self.aspect_var,
                        command=lambda: self.commit_selected('lock')).pack(anchor='w', pady=6)
        row = ttk.Frame(self.image_inspector); row.pack(fill='x', pady=4)
        self._button(row, '− 10%', lambda: self.scale_selected(.9)).pack(side='left', expand=True, fill='x', padx=(0, 3))
        self._button(row, '+ 10%', lambda: self.scale_selected(1.1)).pack(side='right', expand=True, fill='x', padx=(3, 0))
        self._inspect_field(self.image_inspector, 'Rotation · degrees', 'rotation')
        row = ttk.Frame(self.image_inspector); row.pack(fill='x', pady=4)
        self._button(row, '↶ 90°', lambda: self.rotate_selected(90), 'rotate').pack(side='left', expand=True, fill='x')
        self._button(row, '↷ 90°', lambda: self.rotate_selected(-90), 'rotate').pack(side='right', expand=True, fill='x', padx=(4, 0))
        row = ttk.Frame(self.image_inspector); row.pack(fill='x', pady=4)
        self._button(row, 'Flip H', lambda: self.flip_selected('flip_x'), 'flip').pack(side='left', expand=True, fill='x')
        self._button(row, 'Flip V', lambda: self.flip_selected('flip_y'), 'flip').pack(side='right', expand=True, fill='x', padx=(4, 0))
        self._button(self.image_inspector, 'Center on card', self.center_selected, 'center').pack(fill='x', pady=4)
        ttk.Separator(self.image_inspector).pack(fill='x', pady=10)
        ttk.Label(self.image_inspector, text='IMAGE CLEANUP', style='Step.TLabel').pack(anchor='w', pady=(0, 6))
        self._field(self.image_inspector, 'Tolerance', self.bg_tolerance)
        self._button(self.image_inspector, 'Paint & refine image', self.open_image_workshop, 'sparkle', 'Accent.TButton').pack(fill='x', pady=4)
        self._button(self.image_inspector, 'Remove background', self.clean_selected_background, 'sparkle').pack(fill='x', pady=4)
        self._button(self.image_inspector, 'Trim transparent edges', self.trim_selected, 'crop').pack(fill='x', pady=4)
        ttk.Checkbutton(self.image_inspector, text='Grayscale this image', variable=self.image_gray_var,
                        command=self.commit_selected).pack(anchor='w', pady=6)
        ttk.Label(self.image_inspector, text='Recolor silhouette', style='Muted.TLabel').pack(anchor='w')
        row = ttk.Frame(self.image_inspector); row.pack(fill='x', pady=4)
        self.tint_buttons = []
        for i in range(4):
            b = tk.Button(row, text=str(i+1), width=3, relief='flat', command=lambda n=i: self.tint_selected(n))
            b.pack(side='left', padx=2); self.tint_buttons.append(b)
        self._button(row, 'Original', lambda: self.tint_selected(None)).pack(side='right')
        self._button(self.image_inspector, 'Export image parts', self.export_logo_stl, 'download').pack(fill='x', pady=8)
        self.text_inspector = ttk.Frame(self.inspector_content)
        self._button(self.text_inspector, 'Edit text & font', self.edit_selected_text, 'text', 'Accent.TButton').pack(fill='x', pady=10)
        ttk.Label(panel, textvariable=self.inspector_error, foreground='#b42318', wraplength=240).pack(anchor='w', pady=8)

    def _inspect_field(self, parent, label, key, numeric=True):
        row = ttk.Frame(parent); row.pack(fill='x', pady=4)
        ttk.Label(row, text=label).pack(side='left')
        if numeric:
            control = ttk.Spinbox(row, textvariable=self.inspector_vars[key], width=10, from_=-360, to=360,
                                 increment=.5, command=lambda k=key: self.commit_selected(k))
        else:
            control = ttk.Entry(row, textvariable=self.inspector_vars[key], width=18)
        control.pack(side='right')
        control.bind('<Return>', lambda e, k=key: self.commit_selected(k))
        control.bind('<FocusOut>', lambda e, k=key: self.commit_selected(k))

    def _source_ui(self):
        controls = self._scroll_panel(self.source_tab)
        ttk.Label(controls, text='Trace a card photo', font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=12)
        ttk.Label(controls, text='Optional: use a photo as a reference, then turn its text and logo into editable layers.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=(0, 12))
        for label, cmd, icon in [('Load photo', self.load_photo, 'image'), ('Auto-correct perspective', self.auto_correct, 'sparkle'),
            ('Mark four corners', self.start_manual_corners, 'crop'), ('Apply marked corners', self.apply_manual_corners, 'check'),
            ('Use centered crop', self.use_original, 'crop'), ('Scan text offline', self.run_ocr, 'text'),
            ('Extract logo on canvas', self.begin_photo_extraction, 'image'), ('Restore reference', self.restore_photo_background, 'undo')]:
            self._button(controls, label, cmd, icon).pack(fill='x', pady=4)
        self.manual_label = ttk.Label(controls, text='Manual points: 0 / 4'); self.manual_label.pack(anchor='w', pady=8)
        ttk.Label(controls, textvariable=self.ocr_status_var, wraplength=280, style='Muted.TLabel').pack(anchor='w')
        self._button(controls, 'Return to design', self.photo_window.withdraw, 'back').pack(fill='x', pady=16)
        self.source_canvas = tk.Canvas(self.source_tab, bg='#dce4ed', highlightthickness=0)
        self.source_canvas.pack(fill='both', expand=True)
        self.source_canvas.bind('<Button-1>', self.source_canvas_click)

    def show_tool(self, name):
        if self.busy:
            return
        win = {'photo': self.photo_window, 'card': self.card_window, 'checks': self.check_window}[name]
        win.deiconify(); win.lift()
        if name == 'photo': self.after_idle(self.show_source_original)
        elif name == 'card': self.after_idle(self.draw_3d_preview)
        else: self.run_checks()

    def begin_photo_extraction(self):
        if not self.project.source_image:
            messagebox.showinfo('CardForge', 'Load a reference photo first.'); return
        self.photo_window.withdraw()
        self.print_view_var.set(False)
        self.refresh_design_preview()
        self.start_logo_selection()

    def selected_layer(self):
        if not self.selected:
            return None
        kind, index = self.selected
        try:
            return self.project.texts[index] if kind == 'text' else self.project.logo if kind == 'logo' else self.project.elements[index]
        except IndexError:
            return None

    def select_layer(self, kind=None, index=0):
        self.selected = (kind, index) if kind else None
        self.refresh_layers()
        self.sync_inspector()
        self.draw_editor_guides()

    def _tree_selected(self, event=None):
        selection = self.layer_tree.selection()
        if selection:
            kind, index = selection[0].split(':')
            new = (kind, int(index))
            if new != self.selected:
                self.selected = new
                self.sync_inspector(); self.draw_editor_guides()

    def refresh_layers(self):
        rows = [('element', i, e) for i, e in reversed(list(enumerate(self.project.elements)))]
        if self.project.logo.path:
            rows.append(('logo', 0, self.project.logo))
        rows += [('text', i, t) for i, t in reversed(list(enumerate(self.project.texts)))]
        wanted = [f'{kind}:{i}' for kind, i, _ in rows]
        for iid in self.layer_tree.get_children():
            if iid not in wanted: self.layer_tree.delete(iid)
        for position, (kind, i, layer) in enumerate(rows):
            iid = f'{kind}:{i}'
            options = dict(text='  '+(layer.text if kind == 'text' else layer.name)[:28],
                           image=self.icons.get('text' if kind == 'text' else 'image'), tags=() if layer.enabled else ('hidden',))
            if self.layer_tree.exists(iid): self.layer_tree.item(iid, **options)
            else: self.layer_tree.insert('', 'end', iid=iid, **options)
            self.layer_tree.move(iid, '', position)
        iid = f'{self.selected[0]}:{self.selected[1]}' if self.selected else ''
        if iid in wanted:
            self.layer_tree.selection_set(iid)
        else:
            self.selected = None
            self.layer_tree.selection_remove(*self.layer_tree.selection())

    def refresh_text_list(self):
        self.refresh_layers()

    def sync_inspector(self):
        self._inspector_sync = True
        try:
            layer = self.selected_layer()
            self.inspector_error.set('')
            if layer is None:
                self._inspector_baseline = None
                self.selected_name_var.set('Select an image or text')
                self.inspector_content.pack_forget()
                return
            self.inspector_content.pack(fill='x')
            is_text = self.selected[0] == 'text'
            name = layer.text if is_text else layer.name
            self.selected_name_var.set('Text' if is_text else 'Image · '+name[:22])
            values = dict(name=name, x=layer.x_mm, y=layer.y_mm)
            self.visible_var.set(layer.enabled)
            self.image_inspector.pack_forget(); self.text_inspector.pack_forget()
            if is_text:
                self.text_inspector.pack(fill='x')
            else:
                try: width, height = image_size_mm(layer)
                except OSError: width, height = layer.width_mm, layer.height_mm or layer.width_mm
                values.update(width=width, height=height, rotation=layer.rotation_deg)
                self.aspect_var.set(layer.lock_aspect)
                self.image_gray_var.set(layer.grayscale)
                self.image_inspector.pack(fill='x')
            for key, value in values.items():
                self.inspector_vars[key].set(value if isinstance(value, str) else f'{value:.3f}'.rstrip('0').rstrip('.'))
            self._inspector_baseline = self._inspector_values()
        finally:
            self._inspector_sync = False

    def _inspector_values(self):
        return ({k: v.get() for k, v in self.inspector_vars.items()}, self.aspect_var.get(),
                self.visible_var.get(), self.image_gray_var.get())

    def commit_selected(self, changed=None):
        if self._inspector_sync or self.busy:
            return True
        layer = self.selected_layer()
        if layer is None:
            return True
        values = self._inspector_values()
        if values == self._inspector_baseline:
            return True
        if changed is None and self._inspector_baseline:
            baseline = self._inspector_baseline[0]
            if values[0]['width'] != baseline['width']: changed = 'width'
            elif values[0]['height'] != baseline['height']: changed = 'height'
        updated = copy.deepcopy(layer)
        try:
            updated.x_mm = float(self.inspector_vars['x'].get())
            updated.y_mm = float(self.inspector_vars['y'].get())
            if not all(math.isfinite(v) for v in (updated.x_mm, updated.y_mm)):
                raise ValueError('Enter valid positions.')
            name = self.inspector_vars['name'].get().strip()
            if not name: raise ValueError('Enter a name or text.')
            updated.enabled = self.visible_var.get()
            if self.selected[0] == 'text':
                updated.text = name
            else:
                updated.name = name
                width, height = float(self.inspector_vars['width'].get()), float(self.inspector_vars['height'].get())
                old_w, old_h = image_size_mm(layer)
                if self.aspect_var.get():
                    if changed == 'height': width = height*old_w/old_h
                    elif changed == 'width': height = width*old_h/old_w
                angle = float(self.inspector_vars['rotation'].get())
                if not all(math.isfinite(v) for v in (width, height, angle)) or not .5 <= width <= 256 or not .05 <= height <= 256:
                    raise ValueError('Width: 0.5–256 mm. Height: 0.05–256 mm.')
                updated.width_mm, updated.height_mm = width, height
                updated.rotation_deg = angle % 360
                updated.lock_aspect = self.aspect_var.get()
                updated.grayscale = self.image_gray_var.get()
        except (ValueError, OSError, tk.TclError) as exc:
            self.inspector_error.set(str(exc)); return False
        if asdict(updated) != asdict(layer):
            self._remember()
            layer.__dict__.update(updated.__dict__)
            if self.selected[0] == 'logo': self._sync_logo_vars()
            self.refresh_design_preview()
        self.sync_inspector()
        return True

    def _edit_image(self, edit):
        if self.busy or not self.commit_selected(): return
        layer = self.selected_layer()
        if layer is None or self.selected[0] == 'text': return
        candidate = copy.deepcopy(layer)
        edit(candidate)
        if asdict(candidate) != asdict(layer):
            self._remember(); layer.__dict__.update(candidate.__dict__)
            if self.selected[0] == 'logo': self._sync_logo_vars()
            self.sync_inspector(); self.refresh_design_preview()

    def scale_selected(self, factor):
        def change(layer):
            width, height = image_size_mm(layer)
            actual = min(factor, 256/width, 256/height)
            actual = max(actual, .5/width, .05/height)
            layer.width_mm, layer.height_mm = width*actual, height*actual
        self._edit_image(change)

    def rotate_selected(self, angle):
        self._edit_image(lambda e: setattr(e, 'rotation_deg', (e.rotation_deg+angle) % 360))

    def flip_selected(self, axis):
        self._edit_image(lambda e: setattr(e, axis, not getattr(e, axis)))

    def tint_selected(self, slot):
        def change(layer):
            layer.filament_slot = slot
            layer.tint_color = ''
        self._edit_image(change)

    def open_image_workshop(self):
        if self.busy or not self.commit_selected(): return
        layer = self.selected_layer()
        if layer is None or self.selected[0] == 'text': return
        from .paint import ImageWorkshop
        self.image_workshop = ImageWorkshop(self, layer)

    def center_selected(self):
        layer = self.selected_layer()
        if layer is None or self.busy: return
        self.inspector_vars['x'].set(self.project.geometry.card_width_mm/2)
        self.inspector_vars['y'].set(self.project.geometry.card_height_mm/2)
        self.commit_selected()

    def clean_selected_background(self):
        def clean(layer):
            out = self.tempdir / (uuid.uuid4().hex+'_clean.png')
            with Image.open(layer.path) as im: remove_logo_background(im, float(self.bg_tolerance.get())).save(out)
            if not layer.edit_source_path: layer.edit_source_path = layer.path
            layer.path = str(out)
        self._edit_image(clean)

    def trim_selected(self):
        def trim(layer):
            with Image.open(layer.path) as raw: im = raw.convert('RGBA')
            bounds = im.getchannel('A').getbbox()
            if not bounds: raise ValueError('The image is fully transparent.')
            if bounds == (0, 0, *im.size): return
            width, height = image_size_mm(layer)
            out = self.tempdir / (uuid.uuid4().hex+'_trim.png')
            im.crop(bounds).save(out)
            for attr in ('paint_slots_path', 'edit_source_path'):
                path = getattr(layer, attr)
                if path:
                    dest = self.tempdir / (uuid.uuid4().hex+'_'+attr+'.png')
                    with Image.open(path) as raw: raw.crop(bounds).save(dest)
                    setattr(layer, attr, str(dest))
            # Keep width; explicit height follows the new pixel aspect ratio.
            layer.height_mm = width*(bounds[3]-bounds[1])/(bounds[2]-bounds[0])
            layer.path = str(out)
        self._edit_image(trim)

    def load_elements(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(title='Add images — select one or more PNGs',
                    filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp'), ('PNG', '*.png')])
        if not paths: return
        for path in paths:
            with Image.open(path) as im: im.verify()
        self._remember()
        g = self.project.geometry
        for i, path in enumerate(paths):
            self.project.elements.append(LogoLayer(name=Path(path).stem, path=str(path), width_mm=min(18, g.card_width_mm/3),
                x_mm=g.card_width_mm/2+(i%3-1)*8, y_mm=g.card_height_mm/2))
        self.select_layer('element', len(self.project.elements)-len(paths))
        self.refresh_design_preview()
        self.status.set('Image added. Set its size in the inspector or drag a corner handle.')

    def duplicate_selected(self):
        if self.busy or not self.commit_selected(): return
        layer = self.selected_layer()
        if layer is None: return
        self._remember()
        duplicate = copy.deepcopy(layer)
        duplicate.x_mm = min(self.project.geometry.card_width_mm, duplicate.x_mm+3)
        duplicate.y_mm = max(0, duplicate.y_mm-3)
        if self.selected[0] == 'text':
            self.project.texts.append(duplicate); self.selected = ('text', len(self.project.texts)-1)
        else:
            duplicate.name += ' copy'
            self.project.elements.append(duplicate); self.selected = ('element', len(self.project.elements)-1)
        self.sync_inspector(); self.refresh_design_preview()

    def delete_selected(self):
        if self.busy or not self.selected_layer(): return
        self._remember()
        kind, i = self.selected
        if kind == 'text': del self.project.texts[i]
        elif kind == 'logo': self.project.logo = LogoLayer(); self._sync_logo_vars()
        else: del self.project.elements[i]
        self.selected = None
        self.sync_inspector(); self.refresh_design_preview()

    def reorder_selected(self, direction):
        if self.busy or not self.selected_layer(): return
        kind, i = self.selected
        if kind == 'logo':
            if direction < 0 or not self.project.elements: return
            self._remember()
            self.project.elements.insert(1, self.project.logo)
            self.project.logo = LogoLayer(); self._sync_logo_vars(); self.selected = ('element', 1)
        else:
            items = self.project.texts if kind == 'text' else self.project.elements
            j = i+direction
            if not 0 <= j < len(items): return
            self._remember(); items[i], items[j] = items[j], items[i]; self.selected = (kind, j)
        self.sync_inspector(); self.refresh_design_preview()

    def nudge_selected(self, dx, dy, large=False):
        if self.busy or not self.selected_layer(): return
        step = max(.01, float(self.snap_var.get()))*(10 if large else 1)
        layer = self.selected_layer()
        self.inspector_vars['x'].set(layer.x_mm+dx*step)
        self.inspector_vars['y'].set(layer.y_mm+dy*step)
        self.commit_selected()

    def edit_selected_text(self):
        if self.selected and self.selected[0] == 'text': self.text_dialog(self.selected[1])

    def duplicate_text(self):
        self.duplicate_selected()

    def delete_text(self):
        self.delete_selected()

    def _sync_logo_vars(self):
        e = self.project.logo
        for var, value in [(self.logo_x, e.x_mm), (self.logo_y, e.y_mm), (self.logo_w, e.width_mm),
                           (self.logo_opacity, e.opacity/2.55), (self.logo_enabled_var, e.enabled)]: var.set(value)

    def sync_ui_from_project(self):
        g, n, h = self.project.geometry, self.project.nfc, self.project.hueforge
        for key in ['card_width_mm', 'card_height_mm', 'corner_radius_mm', 'base_thickness_mm', 'face_recess_depth_mm', 'face_border_mm', 'face_clearance_mm']:
            self.vars[key].set(getattr(g, key))
        for key in ['diameter_mm', 'thickness_mm', 'clearance_mm', 'x_mm', 'y_mm']:
            self.vars['nfc_'+key].set(getattr(n, key))
        self.nfc_preset.set(n.preset_name)
        self._sync_logo_vars()
        self.object_preview_var.set(False)
        self.object_preview_parts=[]
        self.snap_var.set(self.project.editor.snap_mm)
        self.show_nfc_var.set(self.project.editor.show_nfc_guide)
        self.grayscale_var.set(self.project.editor.grayscale_artwork)
        self.face_thickness.set(self.project.face.thickness_mm)
        self.transparent_cap.set(self.project.face.front_depth_mm)
        for i, color in enumerate(effective_palette(self.project)):
            self.filament_name_vars[i].set(h.filament_names[i])
            ink = 'white' if sum(int(color[k:k+2], 16) for k in (1, 3, 5)) < 400 else '#203149'
            self.color_buttons[i].configure(text=f'{i+1}   {color}', bg=color, fg=ink, activebackground=color)
            self.tint_buttons[i].configure(bg=color, fg=ink)
        bg = self.project.face.background_color
        ink = 'white' if sum(int(bg[k:k+2],16) for k in (1,3,5)) < 400 else '#203149'
        self.background_button.configure(bg=bg, fg=ink, activebackground=bg)
        self.mode_button.configure(text='Restore color' if self.project.editor.grayscale_artwork else 'Grayscale')
        self.refresh_layers(); self.sync_inspector(); self.refresh_ocr_status(); self.run_checks()

    def _schedule_canvas(self, event=None):
        if self._canvas_job is not None: self.after_cancel(self._canvas_job)
        self._canvas_job = self.after(80, self.refresh_design_preview)

    def fit_canvas(self):
        self.zoom_var.set(1)
        self.design_canvas.xview_moveto(0); self.design_canvas.yview_moveto(0)
        self.refresh_design_preview()

    def refresh_design_preview(self):
        if not hasattr(self, 'design_canvas'): return
        if self.object_preview_var.get(): self.draw_object_preview();return
        if self._canvas_job is not None:
            self.after_cancel(self._canvas_job); self._canvas_job = None
        im = face_preview(self.project) if self.print_view_var.get() else self.composite_image()
        # Print preview is inset; place it on the full card so selection stays aligned.
        if self.print_view_var.get():
            from .core.geometry import face_target_dimensions
            fw, fh = face_target_dimensions(self.project.geometry)
            g = self.project.geometry
            ppm = 1600/g.card_width_mm
            board = Image.new('RGB', (1600, round(g.card_height_mm*ppm)), '#d3dce6')
            im = im.resize((round(fw*ppm), round(fh*ppm)))
            board.paste(im, ((board.width-im.width)//2, (board.height-im.height)//2)); im = board
        if self.project.product.kind!='nfc_card':
            from .core.products import panel_outline
            from .core.geometry import face_target_dimensions
            g=self.project.geometry;fw,fh=face_target_dimensions(g)
            shape=panel_outline(self.project,fw,fh)
            inset=g.face_border_mm+g.face_clearance_mm
            sx,sy=im.width/g.card_width_mm,im.height/g.card_height_mm
            mask=Image.new('L',im.size);draw=ImageDraw.Draw(mask)
            def coords(ring): return [((x+inset)*sx,(g.card_height_mm-y-inset)*sy) for x,y in ring.coords]
            draw.polygon(coords(shape.exterior),fill=255)
            for ring in shape.interiors: draw.polygon(coords(ring),fill=0)
            board=Image.new('RGB',im.size,'#cbd7e4');board.paste(im,(0,0),mask);im=board
        canvas = self.design_canvas
        cw, ch = max(220, canvas.winfo_width()), max(220, canvas.winfo_height())
        scale = min((cw-72)/im.width, (ch-90)/im.height)*float(self.zoom_var.get())
        vw, vh = max(1, round(im.width*scale)), max(1, round(im.height*scale))
        sw, sh = max(cw, vw+80), max(ch, vh+90)
        x0, y0 = (sw-vw)/2, (sh-vh)/2
        canvas.delete('all')
        for x in range(16, sw, 24):
            for y in range(16, sh, 24): canvas.create_oval(x, y, x+1, y+1, outline='#b7c7d7')
        canvas.create_rectangle(x0+5, y0+7, x0+vw+5, y0+vh+7, fill='#bdcbd9', outline='')
        photo = ImageTk.PhotoImage(im.resize((vw, vh), Image.Resampling.LANCZOS))
        canvas.create_image(x0, y0, anchor='nw', image=photo); canvas.image_ref = photo
        g = self.project.geometry
        canvas.create_text(x0+vw/2, y0-20, text=f'{g.card_width_mm:g} × {g.card_height_mm:g} mm', fill='#50677f', font=('Segoe UI', 10))
        canvas.configure(scrollregion=(0, 0, sw, sh))
        self.canvas_views['design'] = dict(x0=x0, y0=y0, scale=vw/im.width, image_w=im.width, image_h=im.height, view_w=vw, view_h=vh)
        self.document_var.set(self.project.name + (' •' if asdict(self.project) != self._saved_data else ''))
        self.refresh_layers(); self.draw_editor_guides()

    def refresh_face_preview(self):
        self.sync_face_fields()
        self.refresh_design_preview()

    def _set_hf_info(self, text):
        self.status.set(text.split('\n')[0])

    def _event_mm(self, event):
        c = self.design_canvas
        v = self.canvas_views.get('design')
        if not v: return None
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        g = self.project.geometry
        return (x-v['x0'])/v['view_w']*g.card_width_mm, (1-(y-v['y0'])/v['view_h'])*g.card_height_mm

    def _layer_bounds(self, kind, layer):
        if kind == 'text':
            font = ImageFont.truetype(layer.font_path or default_font(), max(1, round(layer.size_pt*25.4/72*12)))
            bbox = font.getbbox(layer.text, anchor='mm')
            return max(.5, (bbox[2]-bbox[0])/12), max(.5, (bbox[3]-bbox[1])/12), 0
        width, height = image_size_mm(layer)
        return width, height, math.radians(layer.rotation_deg)

    def draw_editor_guides(self):
        if self.object_preview_var.get(): return
        c = self.design_canvas; c.delete('guide')
        self.resize_handles = []
        v = self.canvas_views.get('design')
        if not v: return
        if self.show_nfc_var.get() and self.project.product.kind == 'nfc_card':
            x, y = self.card_mm_to_canvas(self.project.nfc.x_mm, self.project.nfc.y_mm)
            r = self.project.nfc.diameter_mm/2/self.project.geometry.card_width_mm*v['view_w']
            c.create_oval(x-r, y-r, x+r, y+r, outline='#778ea5', dash=(5, 4), tags='guide')
        layer = self.selected_layer()
        if layer is None: return
        try: width, height, angle = self._layer_bounds(self.selected[0], layer)
        except OSError: return
        points = []
        for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            dx, dy = sx*width/2, sy*height/2
            x = layer.x_mm+dx*math.cos(angle)-dy*math.sin(angle)
            y = layer.y_mm+dx*math.sin(angle)+dy*math.cos(angle)
            points.append(self.card_mm_to_canvas(x, y))
        c.create_polygon(*[z for p in points for z in p], outline='#008f9c', fill='', width=2, dash=(5, 2), tags='guide')
        if self.selected[0] != 'text':
            for x, y in points:
                c.create_rectangle(x-5, y-5, x+5, y+5, fill='white', outline='#008f9c', width=2, tags='guide')
                self.resize_handles.append((x, y))

    def design_press(self, event):
        if self.busy: return
        if self.object_preview_var.get():
            self._object_drag=(event.x,event.y,self.object_yaw,self.object_pitch);return
        self.design_canvas.focus_set()
        p = self._event_mm(event)
        if p is None: return
        if self.logo_select_mode:
            self.logo_select_start = (p[0]/self.project.geometry.card_width_mm*1600,
                                      (1-p[1]/self.project.geometry.card_height_mm)*self.base_image().height)
            self.logo_select_rect = self.design_canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#008f9c', width=2)
            return
        cx, cy = self.design_canvas.canvasx(event.x), self.design_canvas.canvasy(event.y)
        handle = any(abs(cx-x) <= 9 and abs(cy-y) <= 9 for x, y in self.resize_handles)
        if handle and self.selected_layer():
            self.drag_target = self.selected; self._resize_handle = True
        else:
            rows = [('element', i, e) for i, e in reversed(list(enumerate(self.project.elements)))]
            rows += [('logo', 0, self.project.logo)] + [('text', i, e) for i, e in reversed(list(enumerate(self.project.texts)))]
            hit = None
            for kind, i, layer in rows:
                if not layer.enabled or (kind != 'text' and not layer.path): continue
                try: w, h, angle = self._layer_bounds(kind, layer)
                except OSError: continue
                dx, dy = p[0]-layer.x_mm, p[1]-layer.y_mm
                u, v = dx*math.cos(angle)+dy*math.sin(angle), -dx*math.sin(angle)+dy*math.cos(angle)
                if abs(u) <= w/2+.4 and abs(v) <= h/2+.4:
                    hit = (kind, i); break
            self.select_layer(*(hit or (None, 0)))
            self.drag_target = hit; self._resize_handle = False
        layer = self.selected_layer()
        if layer is not None:
            self._drag_before = self._snapshot()
            self._drag_origin = (p, copy.deepcopy(layer))
            self.dragging = True

    def design_drag(self, event):
        if self.object_preview_var.get():
            x,y,yaw,pitch=self._object_drag
            self.object_yaw=yaw+(event.x-x)*.5;self.object_pitch=pitch+(event.y-y)*.5
            self.draw_object_preview();return
        p = self._event_mm(event)
        if p is None or self.busy: return
        if self.logo_select_mode and self.logo_select_start:
            v = self.canvas_views['design']
            sx = v['x0']+self.logo_select_start[0]*v['scale']
            sy = v['y0']+self.logo_select_start[1]*v['scale']
            self.design_canvas.coords(self.logo_select_rect, sx, sy, self.design_canvas.canvasx(event.x), self.design_canvas.canvasy(event.y)); return
        if not self.dragging or not self.drag_target: return
        layer = self.selected_layer()
        start, original = self._drag_origin
        if self._resize_handle:
            width, height, angle = self._layer_bounds(self.selected[0], original)
            dx, dy = p[0]-layer.x_mm, p[1]-layer.y_mm
            w = max(.5, min(256, 2*abs(dx*math.cos(angle)+dy*math.sin(angle))))
            h = max(.05, min(256, 2*abs(-dx*math.sin(angle)+dy*math.cos(angle))))
            if layer.lock_aspect:
                factor = min(max(w/width, h/height), 256/width, 256/height)
                w, h = width*factor, height*factor
            layer.width_mm, layer.height_mm = w, h
        else:
            snap = max(.01, float(self.snap_var.get()))
            g = self.project.geometry
            layer.x_mm = min(g.card_width_mm, max(0, round((original.x_mm+p[0]-start[0])/snap)*snap))
            layer.y_mm = min(g.card_height_mm, max(0, round((original.y_mm+p[1]-start[1])/snap)*snap))
        if self.selected[0] == 'logo': self._sync_logo_vars()
        self.sync_inspector(); self.refresh_design_preview()

    def design_release(self, event):
        if self.object_preview_var.get(): return
        if self.logo_select_mode and self.logo_select_start:
            p = self._event_mm(event)
            start = self.logo_select_start
            self.logo_select_mode = False; self.logo_select_start = None
            if p:
                im = self.base_image()
                self.finish_logo_selection(start, (p[0]/self.project.geometry.card_width_mm*im.width, (1-p[1]/self.project.geometry.card_height_mm)*im.height))
                self.select_layer('logo')
            return
        if self.dragging and asdict(self._drag_before[0]) != asdict(self.project):
            self.undo_stack.append(self._drag_before); self.undo_stack = self.undo_stack[-40:]; self.redo_stack.clear()
        self.dragging = False; self.drag_target = None; self._resize_handle = False
