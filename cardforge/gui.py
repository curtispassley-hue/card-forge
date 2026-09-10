from __future__ import annotations
import json
import copy
import queue
import threading
import uuid
from dataclasses import asdict
from functools import wraps
import math
import shutil
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw, ImageFont

from .core.project import Project, TextLayer, LogoLayer
from .core.face import export_face, export_logo, face_preview, palette_color
from .core.fonts import bundled_fonts, default_font
from .core.templates import TEMPLATES, create_template
from .icons import Icons
from .core.ocr import backend_status, ocr_candidates, remove_ocr_text, candidates_to_text_layers, OCRCandidate
from .core.logo import extract_logo, remove_logo_region, suggest_logo_regions, remove_logo_background
from .core.image_processing import (
    auto_correct_file,
    manual_correct_file,
    compose_editable_layers,
    fit_card_image,
    nearest_palette_preview,
)
from .core.geometry import export_base_stl, make_face_blank, face_target_dimensions, validate_geometry, normalize_face_meshes
from .core.hueforge import import_hueforge_path  # legacy reader for 0.4 projects


VERSION = "0.7.1 Preview"
NFC_PRESETS = {
    "20 mm sticker": (20.0, 0.60),
    "25 mm sticker": (25.0, 0.80),
    "30 mm sticker": (30.0, 0.80),
    "Custom": None,
}


class CardForgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"CardForge 4D {VERSION}")
        self.geometry("1280x850")
        self.minsize(1040, 720)

        self.project = Project()
        self.flatforge_meshes = []
        self.tempdir = Path(tempfile.mkdtemp(prefix="CardForge4D_"))
        self.status = tk.StringVar(value="Choose a template or open a saved project to begin.")

        self.canvas_views = {}
        self.manual_mode = False
        self.manual_points = []
        self.drag_target = None
        self.dragging = False
        self.logo_select_mode = False
        self.logo_select_start = None
        self.logo_select_rect = None
        self.preview_photos = {}

        self.undo_stack = []
        self.redo_stack = []
        self._action_depth = 0
        self.busy = False
        self.icons = Icons()
        self._saved_data = asdict(self.project)
        self._style()
        self._build_menu()
        self._build_ui()
        self.sync_ui_from_project()
        self.bind('<Control-z>', lambda e: self.undo())
        self.bind('<Control-y>', lambda e: self.redo())
        self.tabs.bind('<<NotebookTabChanged>>', self._step_changed)
        self._step_changed()
        self.protocol('WM_DELETE_WINDOW', self.close_project)
        self.bind('<Control-s>', lambda e: self.save_project())
        self.bind('<Control-o>', lambda e: self.open_project())
        self.bind('<Control-n>', lambda e: self.new_project())
        self.iconphoto(True, self.icons.get('card', size=64))
        self.after(100, self.show_source_original)

    def report_callback_exception(self, exc, value, tb):
        messagebox.showerror("CardForge", str(value))

    def _style(self):
        self.configure(bg='#f3f5f8')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f3f5f8', foreground='#243247')
        style.configure('TButton', padding=(10, 7), relief='flat')
        style.configure('Accent.TButton', background='#245edb', foreground='white', padding=(12, 8), font=('Segoe UI', 10, 'bold'))
        style.map('Accent.TButton', background=[('active', '#1b4bb1'), ('disabled', '#9bb4e8')])
        style.configure('Secondary.TButton', background='#e7edf7', foreground='#203451', padding=(10, 7))
        style.map('Secondary.TButton', background=[('active', '#d5e1f4')])
        style.configure('Danger.TButton', background='#fbe8e8', foreground='#9b2c2c', padding=(10, 7))
        style.map('Danger.TButton', background=[('active', '#f4d0d0')])
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
        style.configure('Step.TLabel', font=('Segoe UI', 10, 'bold'), foreground='#245edb')
        style.configure('Section.TLabelframe', background='#ffffff', borderwidth=1, relief='solid', padding=8)
        style.configure('Section.TLabelframe.Label', background='#ffffff', foreground='#1e3a5f', font=('Segoe UI', 11, 'bold'))
        style.configure('Muted.TLabel', foreground='#64748b')
        style.configure('TNotebook', borderwidth=0, tabmargins=(0, 0, 0, 6))
        style.configure('TNotebook.Tab', padding=(14, 10), background='#e3e9f2', font=('Segoe UI', 10, 'bold'))
        style.map('TNotebook.Tab', background=[('selected', '#ffffff')])
        style.configure('TEntry', padding=5, fieldbackground='#ffffff', bordercolor='#cbd5e1')
        style.configure('TCombobox', padding=5, fieldbackground='#ffffff')
        style.map('TNotebook.Tab', foreground=[('selected', '#245edb')])
        style.configure('TLabelframe', padding=8)

    def _button(self, parent, label, command, icon='', style='Secondary.TButton'):
        names = {'↶': 'undo', '↷': 'redo', '‹': 'back', '›': 'next', '▣': 'image',
                 '✓': 'check', '＋': 'plus', '−': 'minus', '×': 'delete', '⇩': 'download',
                 '✎': 'edit', '✂': 'crop', '⌕': 'search', '↺': 'undo', '↻': 'refresh',
                 '□': 'crop', '⌖': 'crop', '◉': 'layers'}
        if icon:
            image = self.icons.get(names.get(icon, icon), style == 'Accent.TButton')
            return ttk.Button(parent, text=label, command=command, style=style, image=image, compound='left')
        return ttk.Button(parent, text=label, command=command, style=style)

    def _scroll_panel(self, parent):
        shell = ttk.Frame(parent, width=340)
        shell.pack(side='left', fill='y', padx=(0, 12))
        canvas = tk.Canvas(shell, width=330, highlightthickness=0, bg='#f3f5f8')
        bar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=bar.set)
        inner = ttk.Frame(canvas, padding=(0, 0, 10, 8))
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        def wheel(event):
            widget = event.widget
            while widget is not None:
                if widget == shell:
                    canvas.yview_scroll(int(-event.delta / 120), 'units')
                    break
                widget = getattr(widget, 'master', None)
        self.bind('<MouseWheel>', wheel, add='+')
        return inner

    def _step_changed(self, event=None):
        if not hasattr(self, 'step_label'):
            return
        i = self.tabs.index(self.tabs.select())
        self.step_label.configure(text=f'Step {i+1} of 5')
        if i == 1:
            self.after_idle(self.refresh_design_preview)
        elif i == 2:
            self.after_idle(self.refresh_face_preview)
        elif i == 3:
            self.after_idle(self.draw_3d_preview)
        elif i == 4:
            self.run_checks()

    def navigate(self, delta):
        self.apply_logo()
        self.sync_face_fields()
        self.apply_geometry()
        self.tabs.select(max(0, min(4, self.tabs.index(self.tabs.select()) + delta)))

    def _snapshot(self):
        return (copy.deepcopy(self.project), list(self.flatforge_meshes))

    def _remember(self):
        self.undo_stack.append(self._snapshot())
        self.undo_stack = self.undo_stack[-40:]
        self.redo_stack.clear()

    def _restore(self, snapshot):
        self.project, self.flatforge_meshes = snapshot
        self.manual_mode = self.logo_select_mode = self.dragging = False
        self.manual_points = []
        self.sync_ui_from_project()
        for canvas in (self.source_canvas, self.design_canvas, self.hf_preview_canvas):
            canvas.delete('all')
        self.show_source_original()
        self.refresh_design_preview()
        self.status.set('Edit restored.')

    def undo(self):
        if self.busy or self.grab_current() is not None or not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())

    def redo(self):
        if self.busy or self.grab_current() is not None or not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())

    def scale_logo(self, factor):
        self.logo_w.set(max(0.5, min(self.project.geometry.card_width_mm, float(self.logo_w.get()) * factor)))
        self.apply_logo()

    def clean_logo_background(self):
        if not self.project.logo.path:
            messagebox.showinfo('CardForge', 'Load or extract a logo first.')
            return
        out = self.tempdir / (uuid.uuid4().hex + '_transparent_logo.png')
        with Image.open(self.project.logo.path) as im:
            remove_logo_background(im, float(self.bg_tolerance.get())).save(out)
        self.project.logo.path = str(out)
        self.project.logo.enabled = True
        self.logo_enabled_var.set(True)
        self.refresh_logo_preview()
        self.refresh_design_preview()
        self.status.set('Logo background removed. Undo restores the original.')

    def refresh_logo_preview(self):
        """Show a small checkerboard preview so transparency edits are obvious."""
        canvas = getattr(self, 'logo_preview_canvas', None)
        if canvas is None:
            return
        canvas.delete('all')
        path = self.project.logo.path
        if not path or not Path(path).exists():
            canvas.create_text(140, 62, text='Load or extract a logo', fill='#64748b')
            if hasattr(self, 'logo_file_var'):
                self.logo_file_var.set('No logo loaded')
            return
        try:
            with Image.open(path) as source:
                original_size = source.size
                logo = source.convert('RGBA')
            cw = max(120, int(canvas.winfo_width() or 278) - 8)
            ch = max(80, int(canvas.winfo_height() or 126) - 8)
            logo.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            board = Image.new('RGBA', (cw, ch), '#f5f7fb')
            draw = ImageDraw.Draw(board)
            tile = 12
            for y in range(0, ch, tile):
                for x in range(0, cw, tile):
                    if ((x // tile) + (y // tile)) % 2:
                        draw.rectangle((x, y, x + tile, y + tile), fill='#d9e1ec')
            board.alpha_composite(logo, ((cw - logo.width) // 2, (ch - logo.height) // 2))
            photo = ImageTk.PhotoImage(board.convert('RGB'))
            canvas.create_image(cw // 2 + 4, ch // 2 + 4, image=photo)
            canvas.image_ref = photo
            if hasattr(self, 'logo_file_var'):
                self.logo_file_var.set(f'{Path(path).name}  •  {original_size[0]} × {original_size[1]}px')
        except Exception as exc:
            canvas.create_text(140, 62, text='Logo preview unavailable', fill='#9b2c2c')
            if hasattr(self, 'logo_file_var'):
                self.logo_file_var.set(f'Could not preview logo: {exc}')

    def _background(self, label, work, done):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        self.progress.start(12)
        results = queue.Queue()
        def worker():
            try:
                results.put((True, work()))
            except Exception as exc:
                results.put((False, str(exc)))
        def poll():
            try:
                ok, result = results.get_nowait()
            except queue.Empty:
                self.after(60, poll)
                return
            self.busy = False
            self.progress.stop()
            self.status.set('Operation complete.' if ok else 'Operation failed; see the error message.')
            if ok:
                done(result)
            else:
                messagebox.showerror('CardForge', result)
        threading.Thread(target=worker, daemon=True).start()
        self.after(60, poll)

    # ---------- UI BUILD ----------
    def _build_menu(self):
        menu = tk.Menu(self)
        fm = tk.Menu(menu, tearoff=False)
        fm.add_command(label="New", command=self.new_project)
        fm.add_command(label="Open Project...", command=self.open_project)
        fm.add_command(label="Save Project...", command=self.save_project)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.close_project)
        menu.add_cascade(label="File", menu=fm)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label='Quick start / About', command=self.show_help)
        menu.add_cascade(label='Help', menu=help_menu)
        self.config(menu=menu)

    def _build_ui(self):
        header = ttk.Frame(self, padding=(18, 12))
        header.pack(fill='x')
        ttk.Label(header, text='CardForge 4D', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='DESIGN YOUR CARD.  PRINT IT IN COLOR.', style='Step.TLabel').pack(side='left', padx=20)
        self._button(header, 'Save', self.save_project, 'save', 'Accent.TButton').pack(side='right', padx=4)
        self._button(header, 'Open', self.open_project, 'folder').pack(side='right', padx=4)
        self.redo_button = self._button(header, 'Redo', self.redo, 'redo')
        self.redo_button.pack(side='right', padx=4)
        self.undo_button = self._button(header, 'Undo', self.undo, 'undo')
        self.undo_button.pack(side='right', padx=4)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self.source_tab = ttk.Frame(self.tabs, padding=10)
        self.design_tab = ttk.Frame(self.tabs, padding=10)
        self.hf_tab = ttk.Frame(self.tabs, padding=10)
        self.assembly_tab = ttk.Frame(self.tabs, padding=10)
        self.check_tab = ttk.Frame(self.tabs, padding=10)

        self.tabs.add(self.source_tab, text="1  Start")
        self.tabs.add(self.design_tab, text="2  Design")
        self.tabs.add(self.hf_tab, text="3  Colors & export")
        self.tabs.add(self.assembly_tab, text="4  Base & NFC")
        self.tabs.add(self.check_tab, text="5  Printability")

        self._source_ui()
        self._design_ui()
        self._face_ui()
        self._assembly_ui()
        self._check_ui()

        nav = ttk.Frame(self, padding=(18, 8))
        nav.pack(fill='x')
        self.step_label = ttk.Label(nav, style='Step.TLabel')
        self.step_label.pack(side='left')
        ttk.Label(nav, text='Choose a numbered tab above to change steps.', style='Muted.TLabel').pack(side='right')
        self.progress = ttk.Progressbar(self, mode='indeterminate')
        self.progress.pack(fill='x', padx=18)
        ttk.Label(self, textvariable=self.status, anchor='w', padding=(18, 8)).pack(fill='x')

    def _source_ui(self):
        controls = self._scroll_panel(self.source_tab)
        ttk.Label(controls, text='Make it yours.', font=('Segoe UI', 22, 'bold')).pack(anchor='w', pady=(4, 8))
        ttk.Label(controls, text='Start with a card template. Add your own logo, then type and position your text.',
                  style='Muted.TLabel', wraplength=290).pack(anchor='w', pady=(0, 16))
        for name, description in TEMPLATES.items():
            box = ttk.LabelFrame(controls, text=name, style='Section.TLabelframe')
            box.pack(fill='x', pady=(0, 10))
            ttk.Label(box, text=description, wraplength=270, style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
            self._button(box, 'Use '+name.lower(), lambda n=name: self.start_template(n), 'card',
                         'Accent.TButton' if name == 'Blank card' else 'Secondary.TButton').pack(fill='x')
        photo = ttk.LabelFrame(controls, text='Or start from a photo', style='Section.TLabelframe')
        photo.pack(fill='x', pady=(6, 8))
        self._button(photo, 'Load card photo', self.load_photo, 'image').pack(fill='x')
        self._button(photo, 'Auto-correct perspective', self.auto_correct, 'sparkle').pack(fill='x', pady=4)
        self._button(photo, 'Mark four corners', self.start_manual_corners, 'crop').pack(fill='x', pady=2)
        self._button(photo, 'Apply corners', self.apply_manual_corners, 'check').pack(fill='x', pady=2)
        self._button(photo, 'Reset corners', self.reset_manual_corners, 'undo').pack(fill='x', pady=2)
        self._button(photo, 'Use centered crop', self.use_original, 'crop').pack(fill='x', pady=2)
        self.manual_label = ttk.Label(photo, text='Manual points: 0 / 4')
        self.manual_label.pack(anchor='w', pady=4)
        preview = ttk.Frame(self.source_tab)
        preview.pack(fill='both', expand=True)
        ttk.Label(preview, text='YOUR NEXT CARD', style='Step.TLabel').pack(anchor='w', pady=(8, 6))
        ttk.Label(preview, text='88.9 × 50.8 mm  •  Rounded corners  •  Flush color face', style='Muted.TLabel').pack(anchor='w', pady=(0, 14))
        self.source_canvas = tk.Canvas(preview, bg='#dfe7f1', highlightthickness=0)
        self.source_canvas.pack(fill='both', expand=True)
        self.source_canvas.bind('<Button-1>', self.source_canvas_click)
        ttk.Label(preview, text='Photo-free templates work offline. Dimensions and the NFC pocket remain adjustable.',
                  wraplength=640, style='Muted.TLabel').pack(anchor='w', pady=12)

    def _design_ui(self):
        left = self._scroll_panel(self.design_tab)
        right = ttk.Frame(self.design_tab)
        right.pack(fill='both', expand=True)
        ttk.Label(left, text='Design studio', font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(0, 10))
        actions = ttk.Frame(left)
        actions.pack(fill='x', pady=(0, 10))
        self._button(actions, 'Add text', self.add_text, 'text', 'Accent.TButton').pack(side='left', fill='x', expand=True, padx=(0, 3))
        self._button(actions, 'Add images', self.load_elements, 'image').pack(side='left', fill='x', expand=True, padx=(3, 0))
        self.editor_tabs = ttk.Notebook(left)
        self.editor_tabs.pack(fill='both', expand=True)
        text_panel = ttk.Frame(self.editor_tabs, padding=(4, 10))
        logo_frame = ttk.Frame(self.editor_tabs, padding=(4, 10))
        photo = ttk.Frame(self.editor_tabs, padding=(4, 10))
        self.editor_tabs.add(text_panel, text='Text')
        self.editor_tabs.add(logo_frame, text='Logo')
        self.editor_tabs.add(photo, text='Photo')
        images_panel = ttk.Frame(self.editor_tabs, padding=(4, 10))
        self.editor_tabs.add(images_panel, text='Images')
        ttk.Label(text_panel, text='Double-click a layer to edit it.', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        self.text_list = tk.Listbox(text_panel, width=30, height=10, exportselection=False,
                                   bg='white', fg='#243247', selectbackground='#245edb',
                                   relief='flat', highlightthickness=1, highlightbackground='#cbd5e1', font=('Segoe UI', 11))
        self.text_list.pack(fill='x', pady=4)
        self.text_list.bind('<Double-Button-1>', lambda e: self.edit_selected_text())
        self._button(text_panel, 'Edit selected text', self.edit_selected_text, 'edit').pack(fill='x', pady=4)
        row = ttk.Frame(text_panel); row.pack(fill='x')
        self._button(row, 'Duplicate', self.duplicate_text, 'layers').pack(side='left', expand=True, fill='x', padx=(0, 3))
        self._button(row, 'Delete', self.delete_text, 'delete', 'Danger.TButton').pack(side='left', expand=True, fill='x', padx=(3, 0))
        ttk.Label(text_panel, text='Drag text on the card to move it.\nEach layer becomes a separate color part in Bambu Studio.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=14)
        self.logo_preview_canvas = tk.Canvas(logo_frame, height=100, width=278, bg='#e8edf4', highlightthickness=0)
        self.logo_preview_canvas.pack(fill='x', pady=(0, 6))
        self.logo_file_var = tk.StringVar(value='No logo loaded')
        ttk.Label(logo_frame, textvariable=self.logo_file_var, wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
        self._button(logo_frame, 'Replace image', self.load_logo, 'image').pack(fill='x', pady=2)
        self.logo_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(logo_frame, text='Include logo', variable=self.logo_enabled_var, command=self.apply_logo).pack(anchor='w', pady=6)
        self.logo_x, self.logo_y, self.logo_w = tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        for label, var in [('Center X (mm)', self.logo_x), ('Center Y (mm)', self.logo_y), ('Width (mm)', self.logo_w)]:
            self._field(logo_frame, label, var)
        self.logo_opacity = tk.DoubleVar(value=100)  # Legacy project opacity remains loadable.
        self._button(logo_frame, 'Apply size & position', self.apply_logo, 'check').pack(fill='x', pady=6)
        row = ttk.Frame(logo_frame); row.pack(fill='x')
        self._button(row, 'Smaller', lambda: self.scale_logo(.9), 'minus').pack(side='left', fill='x', expand=True, padx=(0, 3))
        self._button(row, 'Larger', lambda: self.scale_logo(1.1), 'plus').pack(side='left', fill='x', expand=True, padx=(3, 0))
        self.bg_tolerance = tk.DoubleVar(value=34)
        ttk.Separator(logo_frame).pack(fill='x', pady=10)
        self._field(logo_frame, 'Background tolerance', self.bg_tolerance)
        self._button(logo_frame, 'Remove background', self.clean_logo_background, 'sparkle').pack(fill='x', pady=4)
        self._button(logo_frame, 'Center logo on card', self.center_logo, 'card').pack(fill='x', pady=2)
        self._button(logo_frame, 'Export logo STL + 3MF', self.export_logo_stl, 'download', 'Accent.TButton').pack(fill='x', pady=6)
        ttk.Label(logo_frame, text='Transparent PNG works best. Undo restores any cleanup or position change.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=4)
        logo_frame = images_panel
        ttk.Label(logo_frame, text='Icons and emblems', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        ttk.Label(logo_frame, text='Select multiple PNGs at once. Drag them on the card or enter a size and position below.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=(2, 6))
        self.element_list = tk.Listbox(logo_frame, height=7, exportselection=False,
                                       bg='white', fg='#243247', selectbackground='#245edb',
                                       relief='flat', highlightthickness=1, highlightbackground='#cbd5e1')
        self.element_list.pack(fill='x', pady=(0, 5))
        self.element_list.bind('<<ListboxSelect>>', lambda e: self.select_element())
        row = ttk.Frame(logo_frame); row.pack(fill='x')
        self._button(row, 'Load PNGs', self.load_elements, 'image').pack(side='left', fill='x', expand=True, padx=(0, 3))
        self._button(row, 'Remove', self.remove_element, 'delete', 'Danger.TButton').pack(side='left', fill='x', expand=True, padx=(3, 0))
        self.element_x, self.element_y, self.element_w = tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        self.element_name = tk.StringVar()
        self.element_enabled = tk.BooleanVar(value=True)
        self._field(logo_frame, 'Element name', self.element_name)
        ttk.Checkbutton(logo_frame, text='Include this image', variable=self.element_enabled,
                        command=self.apply_element).pack(anchor='w', pady=6)
        for label, var in [('Element X (mm)', self.element_x), ('Element Y (mm)', self.element_y), ('Element width (mm)', self.element_w)]:
            self._field(logo_frame, label, var)
        row = ttk.Frame(logo_frame); row.pack(fill='x')
        self._button(row, 'Apply element', self.apply_element, 'check').pack(side='left', fill='x', expand=True, padx=(0, 3))
        self._button(row, 'Center element', self.center_element, 'card').pack(side='left', fill='x', expand=True, padx=(3, 0))
        self._field(logo_frame, 'Background tolerance', self.bg_tolerance)
        self._button(logo_frame, 'Remove background', self.clean_element_background, 'sparkle').pack(fill='x', pady=6)
        ttk.Label(logo_frame, text='The last image in the list is on top. Each visible image exports as named color parts. Undo restores edits.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=8)
        self._button(logo_frame, 'Export images STL + 3MF', self.export_logo_stl, 'download').pack(fill='x')
        ttk.Label(photo, text='A photo is a layout reference. Scan its text and extract its logo to create printable parts.',
                  wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        for label, cmd, icon in [('Scan text offline', self.run_ocr, 'search'), ('Find logo candidate', self.auto_find_logo, 'search'),
                                 ('Select logo area', self.start_logo_selection, 'crop'), ('Restore photo', self.restore_photo_background, 'undo')]:
            self._button(photo, label, cmd, icon).pack(fill='x', pady=4)
        self.ocr_status_var = tk.StringVar()
        ttk.Label(photo, textvariable=self.ocr_status_var, wraplength=280, style='Muted.TLabel').pack(anchor='w', pady=8)
        ttk.Label(right, text='CARD CANVAS', style='Step.TLabel').pack(anchor='w', pady=(4, 6))
        ttk.Label(right, text='Drag elements to arrange them. Check Colors & export for the printable view.', style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        self.design_canvas = tk.Canvas(right, bg='#dfe7f1', highlightthickness=0)
        self.design_canvas.pack(fill='both', expand=True)
        self.design_canvas.bind('<ButtonPress-1>', self.design_press)
        self.design_canvas.bind('<B1-Motion>', self.design_drag)
        self.design_canvas.bind('<ButtonRelease-1>', self.design_release)
        footer = ttk.Frame(right); footer.pack(fill='x', pady=10)
        self.snap_var = tk.DoubleVar(value=.25)
        self.show_nfc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(footer, text='NFC guide', variable=self.show_nfc_var, command=self.refresh_design_preview).pack(side='left')
        ttk.Label(footer, text='Snap (mm)').pack(side='left', padx=(16, 4))
        ttk.Entry(footer, textvariable=self.snap_var, width=6).pack(side='left')
        self._button(footer, 'Refresh', self.refresh_design_preview, 'refresh').pack(side='right')

    def _face_ui(self):
        left = self._scroll_panel(self.hf_tab)
        right = ttk.Frame(self.hf_tab)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="Flush face / colors", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(left, text="Use your four actual A1 / AMS Lite filaments.", wraplength=300).pack(anchor="w", pady=(8, 10))

        self.color_buttons = []
        self.filament_name_vars = []
        for i in range(4):
            frame = ttk.LabelFrame(left, text=f"Filament {i+1}", padding=6)
            frame.pack(fill="x", pady=4)
            name_var = tk.StringVar()
            self.filament_name_vars.append(name_var)
            ttk.Entry(frame, textvariable=name_var, width=20).pack(side="left", padx=(0, 6))
            btn = tk.Button(frame, width=11, command=lambda idx=i: self.pick_filament_color(idx))
            btn.pack(side="right")
            self.color_buttons.append(btn)

        self.face_thickness = tk.DoubleVar()
        self.transparent_cap = tk.DoubleVar()
        self._field(left, "Total face thickness mm", self.face_thickness)
        self._field(left, "Front color depth mm", self.transparent_cap)

        self._button(left, 'Preview Face', self.refresh_face_preview, '◉').pack(fill='x', pady=4)
        self.grayscale_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text='Grayscale source and image elements', variable=self.grayscale_var,
                        command=self.toggle_grayscale).pack(anchor='w', pady=(2, 6))
        self._button(left, 'Use four grayscale filaments', self.grayscale_palette, 'layers').pack(fill='x', pady=4)
        ttk.Label(left, text='Grayscale images still map to your chosen filaments. Use gray filament shades for a grayscale print.',
                  wraplength=290, style='Muted.TLabel').pack(anchor='w', pady=4)
        ttk.Label(left, text='Thirty bundled OFL fonts are available when editing text.', wraplength=300, style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
        self._button(left, 'Choose Background Color', self.pick_face_background, '●').pack(fill='x', pady=4)
        self._button(left, 'Export Face 3MF + STLs…', self.export_face_files, '⇩', 'Accent.TButton').pack(fill='x', pady=4)
        output = ttk.LabelFrame(left, text='Output files', style='Section.TLabelframe')
        output.pack(fill='x', pady=(10, 4))
        ttk.Label(output, text='Choose a folder and a package name before exporting. Existing names are kept safe with a _2 suffix.',
                  wraplength=300, style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
        self.output_name_var = tk.StringVar(value='My_Card')
        self.output_dir_var = tk.StringVar(value='')
        self._field(output, 'Package name', self.output_name_var)
        row = ttk.Frame(output); row.pack(fill='x', pady=2)
        ttk.Entry(row, textvariable=self.output_dir_var).pack(side='left', fill='x', expand=True)
        self._button(row, 'Browse', self.browse_output_folder, 'folder').pack(side='right', padx=(5, 0))
        ttk.Label(right, text='Front layers: flush text and logo inlays. Back layers: a continuous solid sheet. Both sides are flat. Assign colors to named parts in Bambu Studio.', wraplength=680, font=('Segoe UI', 11)).pack(anchor='nw')
        ttk.Label(right, text='The photo is a layout reference. Scan/retype text and extract or load your logo to create printable elements. No HueForge step is required.', wraplength=680).pack(anchor='nw', pady=8)

        self.hf_preview_canvas = tk.Canvas(right, height=360, bg="#dfe7f1", highlightthickness=0)
        self.hf_preview_canvas.pack(fill="x", expand=False, pady=(12, 8))
        self.hf_info = tk.Text(right, height=12, wrap="word")
        self.hf_info.pack(fill="both", expand=True)
        self._set_hf_info("Ready to generate the face directly from editable text and logo layers.")

    def _assembly_ui(self):
        left = self._scroll_panel(self.assembly_tab)
        right = ttk.Frame(self.assembly_tab)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="Two-piece card", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.vars = {}
        settings = [
            ("Card width mm", "card_width_mm"),
            ("Card height mm", "card_height_mm"),
            ("Corner radius mm", "corner_radius_mm"),
            ("Base thickness mm", "base_thickness_mm"),
            ("Face recess depth mm", "face_recess_depth_mm"),
            ("Face border mm", "face_border_mm"),
            ("Face clearance mm", "face_clearance_mm"),
        ]
        for label, key in settings:
            v = tk.DoubleVar(); self.vars[key] = v; self._field(left, label, v)

        ttk.Separator(left).pack(fill="x", pady=8)
        ttk.Label(left, text="NFC tag").pack(anchor="w")
        self.nfc_preset = tk.StringVar(value="25 mm sticker")
        preset = ttk.Combobox(left, textvariable=self.nfc_preset, state="readonly", values=list(NFC_PRESETS.keys()))
        preset.pack(fill="x", pady=3)
        preset.bind("<<ComboboxSelected>>", lambda e: self.apply_nfc_preset())

        for label, key in [
            ("Tag diameter mm", "nfc_diameter_mm"),
            ("Tag thickness mm", "nfc_thickness_mm"),
            ("Clearance mm", "nfc_clearance_mm"),
            ("Center X mm", "nfc_x_mm"),
            ("Center Y mm", "nfc_y_mm"),
        ]:
            v = tk.DoubleVar(); self.vars[key] = v; self._field(left, label, v)

        ttk.Label(left, text="Preset thicknesses are starting points—measure your actual tag.", wraplength=285).pack(anchor="w", pady=(2, 8))
        self._button(left, "Apply Dimensions", self.apply_geometry, '✓').pack(fill="x", pady=3)
        self._button(left, "Export NFC Base STL...", self.export_base, '⇩').pack(fill="x", pady=3)
        self._button(left, "Export Thin Face Blank STL...", self.export_face_blank, '⇩').pack(fill="x", pady=3)
        self._button(left, "Export Complete Assembly Folder...", self.export_assembly, '⇩', 'Accent.TButton').pack(fill="x", pady=3)

        top = ttk.Frame(right)
        top.pack(fill="x")
        self.yaw_var = tk.DoubleVar(value=-28)
        self.pitch_var = tk.DoubleVar(value=22)
        ttk.Label(top, text="3D assembly preview", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, text="Yaw").pack(side="left", padx=(24, 4))
        ttk.Scale(top, from_=-70, to=70, variable=self.yaw_var, command=lambda _=None: self.draw_3d_preview()).pack(side="left", fill="x", expand=True)
        ttk.Label(top, text="Pitch").pack(side="left", padx=(12, 4))
        ttk.Scale(top, from_=-10, to=70, variable=self.pitch_var, command=lambda _=None: self.draw_3d_preview()).pack(side="left", fill="x", expand=True)

        self.preview3d = tk.Canvas(right, bg="#dfe7f1", highlightthickness=0)
        self.preview3d.pack(fill="both", expand=True, pady=(8, 0))
        self.preview3d.bind("<Configure>", lambda e: self.draw_3d_preview())

    def _check_ui(self):
        top = ttk.Frame(self.check_tab)
        top.pack(fill="x")
        ttk.Label(top, text="Printability report", font=("Segoe UI", 16, "bold")).pack(side="left")
        self._button(top, "Run Checks", self.run_checks, '✓').pack(side="right")
        self.check_text = tk.Text(self.check_tab, wrap="word", font=("Consolas", 10))
        self.check_text.pack(fill="both", expand=True, pady=(10, 0))

    def _field(self, parent, label, var):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=var, width=11).pack(side="right")

    # ---------- SOURCE / PERSPECTIVE ----------
    def load_photo(self):
        p = filedialog.askopenfilename(
            title="Load business-card photo",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")]
        )
        if not p:
            return
        self.project.source_image = p
        self.project.corrected_image = ""
        self.project.cleaned_image = ""
        self.project.ocr_candidates = []
        self.project.manual_corners = []
        self.manual_points = []
        self.manual_mode = False
        self.show_source_original()
        self.refresh_design_preview()
        self.status.set(f"Loaded {Path(p).name}")

    def show_source_original(self):
        if self.project.source_image and Path(self.project.source_image).exists():
            self.show_image_on_canvas(Image.open(self.project.source_image), self.source_canvas, 'source')
        else:
            self.show_image_on_canvas(self.composite_image(), self.source_canvas, 'source')

    def auto_correct(self):
        if not self.project.source_image:
            messagebox.showinfo("CardForge", "Load a photo first.")
            return
        out = self.tempdir / (uuid.uuid4().hex + "_corrected_card.png")
        detected = auto_correct_file(self.project.source_image, out)
        self.project.corrected_image = str(out)
        self.project.cleaned_image = ""
        self.project.ocr_candidates = []
        self.manual_mode = False
        self.manual_points = []
        self.show_image_on_canvas(Image.open(out), self.source_canvas, "source")
        self.refresh_design_preview()
        self.status.set("Perspective corrected from detected corners." if detected else "No reliable rectangle detected; used centered business-card crop.")

    def use_original(self):
        if not self.project.source_image:
            return
        # "Use original" still center-crops to business-card proportions when it enters the editor.
        self.project.corrected_image = ""
        self.project.cleaned_image = ""
        self.project.ocr_candidates = []
        self.manual_mode = False
        self.manual_points = []
        self.show_source_original()
        self.refresh_design_preview()
        self.status.set("Using source photo with centered business-card crop in the editor.")

    def start_manual_corners(self):
        if not self.project.source_image:
            messagebox.showinfo("CardForge", "Load a photo first.")
            return
        self.manual_mode = True
        self.manual_points = []
        self.project.corrected_image = ""
        self.show_source_original()
        self.manual_label.configure(text="Manual points: 0 / 4")
        self.status.set("Manual corner mode: click the four card corners in any order.")

    def reset_manual_corners(self):
        self.manual_points = []
        self.project.manual_corners = []
        self.manual_label.configure(text="Manual points: 0 / 4")
        self.show_source_original()

    def source_canvas_click(self, event):
        if not self.manual_mode or len(self.manual_points) >= 4:
            return
        pt = self.canvas_to_image(event.x, event.y, "source")
        if pt is None:
            return
        self.manual_points.append([float(pt[0]), float(pt[1])])
        self.manual_label.configure(text=f"Manual points: {len(self.manual_points)} / 4")
        self.redraw_manual_points()
        if len(self.manual_points) == 4:
            self.status.set("Four corners selected. Click Apply Manual Corners.")

    def redraw_manual_points(self):
        c = self.source_canvas
        c.delete("manual")
        view = self.canvas_views.get("source")
        if not view:
            return
        canvas_pts = []
        for i, (x, y) in enumerate(self.manual_points):
            cx = view["x0"] + x * view["scale"]
            cy = view["y0"] + y * view["scale"]
            canvas_pts.append((cx, cy))
            r = 7
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="yellow", width=3, tags="manual")
            c.create_text(cx+12, cy-12, text=str(i+1), fill="yellow", font=("Segoe UI", 10, "bold"), tags="manual")
        if len(canvas_pts) > 1:
            flat = [v for p in canvas_pts for v in p]
            c.create_line(*flat, fill="yellow", width=2, tags="manual")

    def apply_manual_corners(self):
        if len(self.manual_points) != 4 or not self.project.source_image:
            messagebox.showinfo("CardForge", "Select exactly four card corners first.")
            return
        out = self.tempdir / (uuid.uuid4().hex + "_manual_corrected_card.png")
        manual_correct_file(self.project.source_image, out, self.manual_points)
        self.project.corrected_image = str(out)
        self.project.cleaned_image = ""
        self.project.ocr_candidates = []
        self.project.manual_corners = [list(p) for p in self.manual_points]
        self.manual_mode = False
        self.show_image_on_canvas(Image.open(out), self.source_canvas, "source")
        self.refresh_design_preview()
        self.status.set("Manual perspective correction applied.")

    # ---------- IMAGE / CANVAS HELPERS ----------
    def analysis_image(self):
        p = self.project.corrected_image or self.project.source_image
        if not p or not Path(p).exists():
            return None
        im = Image.open(p).convert("RGB")
        ratio = self.project.geometry.card_width_mm / self.project.geometry.card_height_mm
        return fit_card_image(im, ratio=ratio, width_px=1600)

    def base_image(self):
        p = self.project.cleaned_image if self.project.cleaned_image and Path(self.project.cleaned_image).exists() else None
        if p:
            im = Image.open(p).convert("RGB")
            ratio = self.project.geometry.card_width_mm / self.project.geometry.card_height_mm
            return fit_card_image(im, ratio=ratio, width_px=1600)
        im = self.analysis_image()
        if im is not None:
            return im
        g = self.project.geometry
        return Image.new('RGB', (1600, round(1600*g.card_height_mm/g.card_width_mm)), self.project.face.background_color)

    def composite_image(self):
        im = self.base_image()
        if im is None:
            return None
        return compose_editable_layers(
            im,
            self.project.geometry.card_width_mm,
            self.project.geometry.card_height_mm,
            self.project.texts,
            self.project.logo,
            self.project.elements,
            self.project.editor.grayscale_artwork,
        )

    def show_image_on_canvas(self, image, canvas, key):
        image = image.convert("RGB")
        canvas.update_idletasks()
        cw = max(120, canvas.winfo_width() - 64)
        ch = max(120, canvas.winfo_height() - 64)
        scale = min(cw / image.width, ch / image.height)
        vw = max(1, int(image.width * scale))
        vh = max(1, int(image.height * scale))
        view = image.resize((vw, vh), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(view)
        x0 = (canvas.winfo_width() - vw) / 2
        y0 = (canvas.winfo_height() - vh) / 2
        canvas.delete("all")
        canvas.create_rectangle(x0+5, y0+7, x0+vw+5, y0+vh+7, fill="#c1cedd", outline="")
        canvas.create_image(x0, y0, anchor="nw", image=photo)
        canvas.image_ref = photo
        self.preview_photos[key] = photo
        self.canvas_views[key] = {
            "x0": x0, "y0": y0, "scale": scale,
            "image_w": image.width, "image_h": image.height,
            "view_w": vw, "view_h": vh,
        }

    def canvas_to_image(self, cx, cy, key):
        v = self.canvas_views.get(key)
        if not v:
            return None
        x = (cx - v["x0"]) / v["scale"]
        y = (cy - v["y0"]) / v["scale"]
        if x < 0 or y < 0 or x >= v["image_w"] or y >= v["image_h"]:
            return None
        return x, y

    def canvas_to_card_mm(self, cx, cy):
        p = self.canvas_to_image(cx, cy, "design")
        if p is None:
            return None
        v = self.canvas_views["design"]
        x_mm = p[0] / v["image_w"] * self.project.geometry.card_width_mm
        y_mm = (1.0 - p[1] / v["image_h"]) * self.project.geometry.card_height_mm
        return x_mm, y_mm

    def card_mm_to_canvas(self, x_mm, y_mm):
        v = self.canvas_views.get("design")
        if not v:
            return None
        x = x_mm / self.project.geometry.card_width_mm * v["image_w"]
        y = (1.0 - y_mm / self.project.geometry.card_height_mm) * v["image_h"]
        return v["x0"] + x * v["scale"], v["y0"] + y * v["scale"]

    # ---------- EDITOR ----------
    def refresh_design_preview(self):
        im = self.composite_image()
        if im is None:
            return
        self.show_image_on_canvas(im, self.design_canvas, "design")
        self.refresh_text_list()
        self.refresh_element_list()
        self.draw_editor_guides()

    def draw_editor_guides(self):
        c = self.design_canvas
        c.delete("guide")
        if self.show_nfc_var.get():
            center = self.card_mm_to_canvas(self.project.nfc.x_mm, self.project.nfc.y_mm)
            if center:
                v = self.canvas_views["design"]
                r = (self.project.nfc.diameter_mm / self.project.geometry.card_width_mm * v["image_w"] / 2) * v["scale"]
                c.create_oval(center[0]-r, center[1]-r, center[0]+r, center[1]+r,
                              outline="#8294aa", dash=(4, 3), width=2, tags="guide")
                c.create_text(center[0], center[1], text="NFC pocket below face", fill="#8294aa", tags="guide")

        # Centers make drag targets discoverable without obscuring the art.
        for i, t in enumerate(self.project.texts):
            if not t.enabled:
                continue
            p = self.card_mm_to_canvas(t.x_mm, t.y_mm)
            if p:
                c.create_rectangle(p[0]-4, p[1]-4, p[0]+4, p[1]+4,
                                   outline="#00e5ff", width=2, tags="guide")
        for element in [self.project.logo, *self.project.elements]:
            if not element.path or not element.enabled:
                continue
            p = self.card_mm_to_canvas(element.x_mm, element.y_mm)
            if p:
                c.create_oval(p[0]-5, p[1]-5, p[0]+5, p[1]+5,
                              outline="#ffdc5e", width=2, tags="guide")

    def refresh_text_list(self):
        selected = self.text_list.curselection()
        self.text_list.delete(0, tk.END)
        for i, t in enumerate(self.project.texts):
            self.text_list.insert(tk.END, f"{i+1}. {t.text[:25]}" + (f"  OCR {t.ocr_confidence*100:.0f}%" if getattr(t, "ocr_confidence", 0) else ""))

        if selected and selected[0] < len(self.project.texts):
            self.text_list.selection_set(selected[0])

    def duplicate_text(self):
        sel = self.text_list.curselection()
        if sel:
            layer = copy.deepcopy(self.project.texts[sel[0]])
            layer.y_mm = max(1, layer.y_mm-5)
            self.project.texts.append(layer)
            self.refresh_design_preview()

    def center_logo(self):
        self.logo_x.set(self.project.geometry.card_width_mm/2)
        self.logo_y.set(self.project.geometry.card_height_mm/2)
        self.apply_logo()

    def add_text(self):
        self.text_dialog(None)

    def edit_selected_text(self):
        sel = self.text_list.curselection()
        if not sel:
            messagebox.showinfo("CardForge", "Select a text layer first.")
            return
        self.text_dialog(sel[0])

    def delete_text(self):
        sel = self.text_list.curselection()
        if sel:
            del self.project.texts[sel[0]]
            self.refresh_design_preview()

    def text_dialog(self, index):
        if self.busy:
            return
        win = tk.Toplevel(self)
        win.title('Edit text' if index is not None else 'Add text')
        win.geometry('560x570')
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        layer = copy.deepcopy(self.project.texts[index]) if index is not None else TextLayer(size_pt=10)
        panel = ttk.Frame(win, padding=20); panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Make your words stand out.', font=('Segoe UI', 17, 'bold')).pack(anchor='w', pady=(0, 12))
        value = tk.StringVar(value=layer.text)
        font_path = tk.StringVar(value=layer.font_path or default_font())
        size = tk.IntVar(value=layer.size_pt)
        x, y = tk.DoubleVar(value=layer.x_mm), tk.DoubleVar(value=layer.y_mm)
        enabled = tk.BooleanVar(value=layer.enabled)
        ttk.Label(panel, text='Text').pack(anchor='w')
        entry = ttk.Entry(panel, textvariable=value, font=('Segoe UI', 12))
        entry.pack(fill='x', pady=(4, 12)); entry.focus_set()
        choices = bundled_fonts()
        current_name = next((n for n, path in choices.items() if Path(path).name == Path(font_path.get()).name), 'Custom font')
        chosen = tk.StringVar(value=current_name)
        ttk.Label(panel, text=f'Font — {len(choices)} included styles').pack(anchor='w')
        row = ttk.Frame(panel); row.pack(fill='x', pady=(4, 10))
        picker = ttk.Combobox(row, values=list(choices), state='readonly', textvariable=chosen)
        picker.pack(side='left', fill='x', expand=True)
        picker.bind('<<ComboboxSelected>>', lambda e: font_path.set(choices[chosen.get()]))
        def custom_font():
            self.pick_font(font_path)
            chosen.set(Path(font_path.get()).stem)
        self._button(row, 'Browse', custom_font, 'folder').pack(side='right', padx=(6, 0))
        self._field(panel, 'Size (points)', size)
        self._field(panel, 'Center X (mm)', x)
        self._field(panel, 'Center Y (mm)', y)
        ttk.Label(panel, text='Filament color').pack(anchor='w', pady=(10, 4))
        palette = self.project.hueforge.palette
        matched = palette_color(layer.color, palette)
        slot = tk.IntVar(value=[c.upper() for c in palette].index(matched.upper()))
        row = ttk.Frame(panel); row.pack(fill='x')
        for i, color in enumerate(palette):
            tk.Radiobutton(row, text=str(i+1), value=i, variable=slot, bg=color, selectcolor=color,
                           fg='white' if sum(int(color[k:k+2], 16) for k in (1, 3, 5)) < 400 else '#111111',
                           indicatoron=False, width=8, relief='raised', borderwidth=2, padx=4, pady=7).pack(side='left', padx=(0, 5))
        sample = ttk.Label(panel); sample.pack(fill='x', pady=12)
        error = tk.StringVar()
        ttk.Label(panel, textvariable=error, foreground='#b42318', wraplength=500).pack(anchor='w')
        def preview(*_):
            try:
                font = ImageFont.truetype(font_path.get(), min(60, max(8, int(size.get())*2)))
                im = Image.new('RGB', (510, 72), 'white')
                ImageDraw.Draw(im).text((12, 36), value.get() or 'Sample Aa 123', font=font, fill=palette[slot.get()], anchor='lm')
                sample.photo = ImageTk.PhotoImage(im); sample.configure(image=sample.photo)
            except (ValueError, OSError, tk.TclError):
                pass
        for var in (value, font_path, size, slot): var.trace_add('write', preview)
        preview()
        ttk.Checkbutton(panel, text='Include this text in the print', variable=enabled).pack(anchor='w')
        def save():
            try:
                xx, yy, ss = float(x.get()), float(y.get()), int(size.get())
                if not value.get().strip(): raise ValueError('Enter some text first.')
                if not all(math.isfinite(n) for n in (xx, yy)) or not 1 <= ss <= 144:
                    raise ValueError('Use a size of 1–144 points and valid positions.')
                if not (0 <= xx <= self.project.geometry.card_width_mm and 0 <= yy <= self.project.geometry.card_height_mm):
                    raise ValueError('Place the text center within the card.')
                ImageFont.truetype(font_path.get(), ss)
            except (ValueError, OSError, tk.TclError) as exc:
                error.set(str(exc)); return
            layer.text, layer.x_mm, layer.y_mm, layer.size_pt = value.get(), xx, yy, ss
            layer.font_path, layer.color, layer.enabled = font_path.get(), palette[slot.get()], enabled.get()
            self._remember()
            if index is None: self.project.texts.append(layer)
            else: self.project.texts[index] = layer
            win.destroy()
            self.editor_tabs.select(0)
            self.refresh_design_preview()
            self.text_list.selection_clear(0, tk.END)
            self.text_list.selection_set(index if index is not None else len(self.project.texts)-1)
        footer = ttk.Frame(panel); footer.pack(side='bottom', fill='x', pady=(8, 0))
        self._button(footer, 'Cancel', win.destroy, 'back').pack(side='left')
        self._button(footer, 'Apply text', save, 'check', 'Accent.TButton').pack(side='right')
        win.bind('<Escape>', lambda e: win.destroy())

    def pick_font(self, var):
        p = filedialog.askopenfilename(filetypes=[("Fonts", "*.ttf *.otf"), ("All files", "*.*")])
        if p:
            var.set(p)

    def pick_text_color(self, var):
        c = colorchooser.askcolor(initialcolor=var.get())
        if c[1]:
            var.set(c[1])

    def load_logo(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if p:
            with Image.open(p) as candidate:
                candidate.verify()
            self.project.logo.path = p
            self.project.logo.name = Path(p).stem
            self.project.logo.opacity = 255
            self.logo_opacity.set(100)
            self.editor_tabs.select(1)
            self.project.logo.enabled = True
            self.logo_enabled_var.set(True)
            self.refresh_logo_preview()
            self.refresh_design_preview()
            self.status.set(f'Loaded logo: {Path(p).name}')

    def refresh_element_list(self):
        selected = self.element_list.curselection()
        self.element_list.delete(0, tk.END)
        for i, element in enumerate(self.project.elements):
            self.element_list.insert(tk.END, f'{i+1}. {element.name}' + ('' if element.enabled else ' (hidden)'))
        if self.project.elements:
            self.element_list.selection_set(min(selected[0] if selected else 0, len(self.project.elements)-1))

    def select_element(self):
        sel = self.element_list.curselection()
        if not sel or sel[0] >= len(self.project.elements):
            return
        element = self.project.elements[sel[0]]
        self.element_name.set(element.name)
        self.element_x.set(element.x_mm)
        self.element_y.set(element.y_mm)
        self.element_w.set(element.width_mm)
        self.element_enabled.set(element.enabled)

    def load_elements(self):
        paths = filedialog.askopenfilenames(title='Add icons and emblems — select one or more images',
                    filetypes=[('PNG images', '*.png'), ('Images', '*.png *.jpg *.jpeg *.webp *.bmp')])
        if not paths:
            return
        for path in paths:
            with Image.open(path) as candidate:
                candidate.verify()
        g = self.project.geometry
        for i, path in enumerate(paths):
            self.project.elements.append(LogoLayer(name=Path(path).stem, path=str(path),
                x_mm=g.card_width_mm/2 + (i % 3-1)*min(12, g.card_width_mm/4),
                y_mm=g.card_height_mm/2, width_mm=min(12, g.card_width_mm/3)))
        self.refresh_element_list()
        self.element_list.selection_clear(0, tk.END)
        self.element_list.selection_set(len(self.project.elements)-len(paths))
        self.select_element()
        self.editor_tabs.select(3)
        self.refresh_design_preview()
        self.status.set(f'Added {len(paths)} image(s). Select one to resize it, or drag it on the card.')

    def apply_element(self):
        sel = self.element_list.curselection()
        if not sel:
            return
        x, y, width = (float(v.get()) for v in (self.element_x, self.element_y, self.element_w))
        if not all(math.isfinite(v) for v in (x, y, width)) or not 0.5 <= width <= 256:
            raise ValueError('Image width must be 0.5–256 mm. Use valid numbers for its position.')
        element = self.project.elements[sel[0]]
        element.x_mm, element.y_mm, element.width_mm = x, y, width
        element.name = self.element_name.get().strip() or 'Image'
        element.enabled = self.element_enabled.get()
        self.refresh_design_preview()

    def remove_element(self):
        sel = self.element_list.curselection()
        if sel:
            del self.project.elements[sel[0]]
            self.refresh_element_list()
            self.select_element()
            self.refresh_design_preview()

    def center_element(self):
        self.element_x.set(self.project.geometry.card_width_mm/2)
        self.element_y.set(self.project.geometry.card_height_mm/2)
        self.apply_element()

    def clean_element_background(self):
        sel = self.element_list.curselection()
        if not sel:
            return
        self.apply_element()
        element = self.project.elements[sel[0]]
        out = self.tempdir / (uuid.uuid4().hex + '_transparent_element.png')
        with Image.open(element.path) as im:
            remove_logo_background(im, float(self.bg_tolerance.get())).save(out)
        element.path = str(out)
        self.refresh_design_preview()
        self.status.set('Image background removed. Undo restores the original.')

    def toggle_grayscale(self):
        self.project.editor.grayscale_artwork = self.grayscale_var.get()
        self.refresh_design_preview()
        self.refresh_face_preview()

    def grayscale_palette(self):
        self.project.hueforge.palette = ['#111111', '#666666', '#BBBBBB', '#FFFFFF']
        self.project.hueforge.filament_names = ['Black', 'Dark gray', 'Light gray', 'White']
        self.project.editor.grayscale_artwork = True
        self.sync_ui_from_project()
        self.refresh_design_preview()
        self.refresh_face_preview()

    def apply_logo(self):
        values = [float(v.get()) for v in (self.logo_x, self.logo_y, self.logo_w, self.logo_opacity)]
        if not all(math.isfinite(v) for v in values) or not 0.5 <= values[2] <= 256:
            raise ValueError('Logo width must be 0.5–256 mm. Use valid numbers for its position.')
        self.project.logo.x_mm = float(self.logo_x.get())
        self.project.logo.y_mm = float(self.logo_y.get())
        self.project.logo.width_mm = max(0.5, float(self.logo_w.get()))
        if hasattr(self, 'logo_opacity'):
            self.project.logo.opacity = int(round(max(0, min(100, float(self.logo_opacity.get()))) * 2.55))
        if hasattr(self, 'logo_enabled_var'):
            self.project.logo.enabled = bool(self.logo_enabled_var.get())
        self.refresh_logo_preview()
        self.refresh_design_preview()

    def design_press(self, event):
        if self.logo_select_mode:
            ip = self.canvas_to_image(event.x, event.y, "design")
            if ip is not None:
                self.logo_select_start = ip
                if self.logo_select_rect:
                    self.design_canvas.delete(self.logo_select_rect)
                self.logo_select_rect = self.design_canvas.create_rectangle(
                    event.x, event.y, event.x, event.y, outline="#ffdc5e", width=2, dash=(5, 3), tags="logo_select"
                )
            return
        if self.busy:
            return
        p = self.canvas_to_card_mm(event.x, event.y)
        if p is None:
            return
        x, y = p
        candidates = []
        for i, t in enumerate(self.project.texts):
            if not t.enabled:
                continue
            # Approximate hit box from font em-height and character count.
            em = max(1.0, t.size_pt * 25.4 / 72.0)
            half_w = max(2.0, len(t.text) * em * 0.26)
            half_h = max(1.5, em * 0.65)
            if abs(x - t.x_mm) <= half_w and abs(y - t.y_mm) <= half_h:
                candidates.append((math.hypot(x-t.x_mm, y-t.y_mm), ("text", i)))
        for kind, index, element in [('logo', 0, self.project.logo)] + [('element', i, e) for i, e in enumerate(self.project.elements)]:
            if not element.path or not element.enabled:
                continue
            try:
                with Image.open(element.path) as im:
                    h_mm = element.width_mm * im.height / max(1, im.width)
            except Exception:
                h_mm = element.width_mm
            if abs(x-element.x_mm) <= element.width_mm/2 and abs(y-element.y_mm) <= h_mm/2:
                candidates.append((math.hypot(x-element.x_mm, y-element.y_mm), (kind, index)))
        if candidates:
            self._drag_before = self._snapshot()
            candidates.sort(key=lambda z: z[0])
            self.drag_target = candidates[0][1]
            self.dragging = True
            if self.drag_target[0] == 'text':
                self.text_list.selection_clear(0, tk.END)
                self.text_list.selection_set(self.drag_target[1])
                self.editor_tabs.select(0)
            elif self.drag_target[0] == 'element':
                self.element_list.selection_clear(0, tk.END)
                self.element_list.selection_set(self.drag_target[1])
                self.select_element()
                self.editor_tabs.select(3)
            else:
                self.editor_tabs.select(1)

    def design_drag(self, event):
        if self.logo_select_mode and self.logo_select_start is not None:
            if self.logo_select_rect:
                v = self.canvas_views.get("design")
                if v:
                    sx = v["x0"] + self.logo_select_start[0] * v["scale"]
                    sy = v["y0"] + self.logo_select_start[1] * v["scale"]
                    self.design_canvas.coords(self.logo_select_rect, sx, sy, event.x, event.y)
            return
        if not self.dragging or not self.drag_target:
            return
        if self.busy:
            return
        p = self.canvas_to_card_mm(event.x, event.y)
        if p is None:
            return
        snap = max(0.01, float(self.snap_var.get()))
        x = round(p[0] / snap) * snap
        y = round(p[1] / snap) * snap
        x = min(max(0.0, x), self.project.geometry.card_width_mm)
        y = min(max(0.0, y), self.project.geometry.card_height_mm)
        if self.drag_target[0] == "text":
            t = self.project.texts[self.drag_target[1]]
            t.x_mm, t.y_mm = x, y
        elif self.drag_target[0] == 'element':
            element = self.project.elements[self.drag_target[1]]
            element.x_mm, element.y_mm = x, y
            self.element_x.set(x); self.element_y.set(y)
        else:
            self.project.logo.x_mm, self.project.logo.y_mm = x, y
            self.logo_x.set(x); self.logo_y.set(y)
        self.refresh_design_preview()

    def design_release(self, event):
        if self.logo_select_mode and self.logo_select_start is not None:
            end = self.canvas_to_image(event.x, event.y, "design")
            start = self.logo_select_start
            self.logo_select_mode = False
            self.logo_select_start = None
            if end is not None:
                self.finish_logo_selection(start, end)
            return
        if self.dragging and asdict(self._drag_before[0]) != asdict(self.project):
            self.undo_stack.append(self._drag_before)
            self.redo_stack.clear()
        self.dragging = False
        self.drag_target = None

    # ---------- OCR / LOGO EXTRACTION ----------
    def refresh_ocr_status(self):
        ok, text = backend_status()
        if hasattr(self, "ocr_status_var"):
            self.ocr_status_var.set(("Ready: " if ok else "Not ready: ") + text)
        return ok

    def run_ocr(self):
        if self.busy:
            return
        im = self.analysis_image()
        if im is None:
            messagebox.showinfo('CardForge', 'Load a card photo first, or use Add text to type your own.')
            return
        snapshot = copy.deepcopy(self.project)
        def work():
            found = ocr_candidates(im, snapshot.geometry.card_width_mm, snapshot.geometry.card_height_mm)
            cleaned = remove_ocr_text(im, found) if snapshot.editor.ocr_remove_original and found else None
            return found, cleaned
        def done(result):
            found, cleaned = result
            self._remember()
            self.project.ocr_candidates = [c.to_dict() for c in found]
            self.project.ocr_backend = 'RapidOCR / ONNX Runtime'
            self.project.texts = [t for t in self.project.texts if not t.source_box_px]
            self.project.texts.extend(candidates_to_text_layers(found, TextLayer))
            if cleaned is not None:
                out = self.tempdir / (uuid.uuid4().hex+'_ocr_cleaned.png')
                cleaned.save(out); self.project.cleaned_image = str(out)
            self.refresh_design_preview()
            self.editor_tabs.select(0)
            self.status.set(f'Scan created {len(found)} editable text layers. Review spelling and small details.')
        self._background('Scanning text offline…', work, done)

    def restore_photo_background(self):
        self.project.cleaned_image = ""
        self.refresh_design_preview()
        self.status.set("Restored the corrected/source photo background. Editable layers were kept.")

    def auto_find_logo(self):
        im = self.base_image()
        if im is None:
            messagebox.showinfo("CardForge", "Load a card image first.")
            return
        excludes = [c.get("box_px", []) for c in self.project.ocr_candidates if c.get("box_px")]
        regions = suggest_logo_regions(im, excludes, max_results=5)
        if not regions:
            messagebox.showinfo("CardForge Logo", "No strong logo candidate was found. Use Extract Logo From Card and drag a rectangle manually.")
            return
        start, end = regions[0]
        self._draw_logo_candidate(start, end)
        if messagebox.askyesno(
            "CardForge Logo",
            "CardForge highlighted its highest-ranked logo-like region. Extract this region as the editable logo?\n\nChoose No if the highlight is wrong, then use manual Extract Logo From Card."
        ):
            self.finish_logo_selection(start, end)
        else:
            self.design_canvas.delete("logo_candidate")
            self.status.set("Automatic logo suggestion rejected; use manual logo extraction if needed.")

    def _draw_logo_candidate(self, start, end):
        v = self.canvas_views.get("design")
        if not v:
            return
        x0 = v["x0"] + start[0] * v["scale"]
        y0 = v["y0"] + start[1] * v["scale"]
        x1 = v["x0"] + end[0] * v["scale"]
        y1 = v["y0"] + end[1] * v["scale"]
        self.design_canvas.delete("logo_candidate")
        self.design_canvas.create_rectangle(x0, y0, x1, y1, outline="#ffdc5e", width=3, dash=(6,3), tags="logo_candidate")

    def start_logo_selection(self):
        if self.base_image() is None:
            messagebox.showinfo("CardForge", "Load a card image first.")
            return
        self.logo_select_mode = True
        self.logo_select_start = None
        self.status.set("Logo extraction: drag a rectangle around the logo on the edited preview.")

    def finish_logo_selection(self, start, end):
        im = self.base_image()
        if im is None:
            return
        x0, y0 = start; x1, y1 = end
        if abs(x1-x0) < 8 or abs(y1-y0) < 8:
            self.status.set("Logo selection was too small.")
            return
        try:
            out = self.tempdir / (uuid.uuid4().hex + "_extracted_logo.png")
            extract_logo(im, (start, end), out)
            self.project.logo.path = str(out)
            self.project.logo.enabled = True
            self.project.logo.source_rect_px = [[float(x0), float(y0)], [float(x1), float(y1)]]

            xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
            self.project.logo.x_mm = ((xa+xb)/2) / im.width * self.project.geometry.card_width_mm
            self.project.logo.y_mm = (1 - ((ya+yb)/2) / im.height) * self.project.geometry.card_height_mm
            self.project.logo.width_mm = (xb-xa) / im.width * self.project.geometry.card_width_mm

            # Remove the photographed logo from the background so the extracted
            # logo becomes a genuinely editable layer rather than a duplicate.
            cleaned = remove_logo_region(im, (start, end))
            clean_path = self.tempdir / (uuid.uuid4().hex + "_logo_cleaned_card.png")
            cleaned.save(clean_path)
            self.project.cleaned_image = str(clean_path)

            self.logo_x.set(self.project.logo.x_mm)
            self.logo_y.set(self.project.logo.y_mm)
            self.logo_w.set(self.project.logo.width_mm)
            self.logo_enabled_var.set(True)
            self.refresh_logo_preview()
            self.refresh_design_preview()
            self.status.set("Logo extracted to a transparent editable layer. Drag it or replace it with an original logo file.")
        except Exception as e:
            messagebox.showerror("CardForge Logo", f"Logo extraction failed:\n{e}")

    # ---------- HUEFORGE ----------
    def pick_filament_color(self, idx):
        c = colorchooser.askcolor(initialcolor=self.project.hueforge.palette[idx])
        if c[1]:
            previous = self.project.hueforge.palette[idx].upper()
            for layer in self.project.texts:
                if layer.color.upper() == previous:
                    layer.color = c[1].upper()
            if self.project.face.background_color.upper() == previous:
                self.project.face.background_color = c[1].upper()
            self.project.hueforge.palette[idx] = c[1].upper()
            self.color_buttons[idx].configure(text=c[1].upper(), bg=c[1])
            self.refresh_face_preview()

    def sync_face_fields(self):
        values = [float(self.face_thickness.get()), float(self.transparent_cap.get())]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Use valid numbers for face and front layer thickness.')
        self.project.hueforge.filament_names = [v.get() for v in self.filament_name_vars]
        self.project.face.thickness_mm = float(self.face_thickness.get())
        self.project.face.front_depth_mm = float(self.transparent_cap.get())
        self.project.hueforge.face_target_thickness_mm = self.project.face.thickness_mm

    def pick_face_background(self):
        color = colorchooser.askcolor(initialcolor=self.project.face.background_color)[1]
        if color:
            self._remember()
            self.project.face.background_color = color
            self.refresh_face_preview()

    def refresh_face_preview(self):
        self.sync_face_fields()
        g = self.project.geometry
        im = face_preview(self.project)
        self.show_image_on_canvas(im, self.hf_preview_canvas, 'face')
        count = sum(bool(e.enabled and e.path) for e in [self.project.logo, *self.project.elements])
        self._set_hf_info(f'Printable view uses your four filament colors. Sub-pixel contacts are cleaned before cutting matching parts.\n\n{len(self.project.texts)} text layer(s), {count} visible image(s).\nFront inlays: {self.project.face.front_depth_mm:.2f} mm\nSolid backing: {self.project.face.thickness_mm-self.project.face.front_depth_mm:.2f} mm\nExport produces named parts, ready to assign filaments in Bambu Studio.\nArtwork will be mirrored automatically for face-down printing.')

    def export_face_files(self):
        self._export_direct(False)

    def export_logo_stl(self):
        """Create a standalone logo package without rebuilding the card base."""
        if self.busy:
            return
        if not any(e.path and e.enabled for e in [self.project.logo, *self.project.elements]):
            messagebox.showinfo('CardForge', 'Add an image or load a logo first.')
            return
        self._sync_edits()
        settings = self._output_settings('Export image geometry')
        if not settings:
            return
        out, name = settings
        snapshot = copy.deepcopy(self.project)
        self._background(
            'Creating logo geometry…',
            lambda: export_logo(snapshot, out, output_name=name),
            lambda result: messagebox.showinfo(
                'CardForge',
                f'Logo files ready in:\n{result}\n\n'
                'Open the Logo.3mf file for named color parts, or use Logo_STLs together as one multipart object.'
            ),
        )

    def _export_direct(self, include_base):
        if self.busy:
            return
        self._sync_edits()
        settings = self._output_settings('Export complete card' if include_base else 'Export card face')
        if not settings:
            return
        out, name = settings
        snapshot = copy.deepcopy(self.project)
        self._background('Generating flush face geometry…', lambda: export_face(snapshot, out, include_base, output_name=name),
                         lambda result: messagebox.showinfo('CardForge', f'Face files ready in:\n{result}\n\nOpen the Face.3mf file in Bambu Studio and assign filament colors under Objects / Parts.'))

    def browse_output_folder(self):
        current = self.output_dir_var.get().strip()
        folder = filedialog.askdirectory(title='Choose where to save your exports',
                                        initialdir=current if Path(current).is_dir() else None)
        if folder:
            self.output_dir_var.set(folder)

    def _output_settings(self, title):
        from .core.face import _safe_stem
        win = tk.Toplevel(self)
        win.title(title)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        panel = ttk.Frame(win, padding=22); panel.pack(fill='both', expand=True)
        ttk.Label(panel, text=title, font=('Segoe UI', 17, 'bold')).pack(anchor='w', pady=(0, 12))
        self._field(panel, 'Package name', self.output_name_var)
        ttk.Label(panel, text='Destination folder').pack(anchor='w', pady=(10, 4))
        row = ttk.Frame(panel); row.pack(fill='x')
        ttk.Entry(row, textvariable=self.output_dir_var, width=50).pack(side='left', fill='x', expand=True)
        self._button(row, 'Browse', self.browse_output_folder, 'folder').pack(side='left', padx=(6, 0))
        ttk.Label(panel, text='A new folder with this name will contain the 3MF, STL parts and instructions.\nIf it already exists, a numbered suffix keeps your earlier files safe.',
                  wraplength=510, style='Muted.TLabel').pack(anchor='w', pady=14)
        error = tk.StringVar()
        ttk.Label(panel, textvariable=error, foreground='#b42318', wraplength=510).pack(anchor='w')
        result = []
        def accept():
            name = self.output_name_var.get().strip()
            folder = self.output_dir_var.get().strip()
            if not name:
                error.set('Enter a package name.'); return
            if not folder:
                error.set('Choose a destination folder.'); return
            path = Path(folder).expanduser()
            if not path.is_dir():
                error.set('Choose an existing destination folder with Browse.'); return
            safe = _safe_stem(name)
            self.output_name_var.set(safe)
            self.output_dir_var.set(str(path))
            result.append((str(path), safe))
            win.destroy()
        footer = ttk.Frame(panel); footer.pack(fill='x', pady=(14, 0))
        self._button(footer, 'Cancel', win.destroy, 'back').pack(side='left')
        self._button(footer, 'Export files', accept, 'download', 'Accent.TButton').pack(side='right')
        win.bind('<Escape>', lambda e: win.destroy())
        win.bind('<Return>', lambda e: accept())
        self.wait_window(win)
        return result[0] if result else None

    def import_flatforge_folder(self):
        folder = filedialog.askdirectory(title="Select FlatForge STL folder")
        if folder:
            self._import_hueforge_path(folder)

    def import_hueforge_file(self):
        p = filedialog.askopenfilename(title="Import HueForge / FlatForge geometry",
                                       filetypes=[("3D models", "*.3mf *.stl"), ("All files", "*.*")])
        if p:
            self._import_hueforge_path(p)

    def _import_hueforge_path(self, path):
        self.apply_geometry()
        meshes = import_hueforge_path(path, self.project)
        if not meshes:
            messagebox.showwarning("CardForge", "No STL/3MF mesh volumes could be imported from that selection.")
            return
        self.flatforge_meshes = meshes
        self.project.hueforge_import_path = str(path)
        lines = [
            f"Imported {len(meshes)} mesh volume(s).",
            "",
            "XY was normalized to the face insert. Z/layer heights were preserved.",
            "",
        ]
        for m in meshes:
            lines.append(f"- {m.metadata.get('source_name','HueForge mesh')}  extents={m.extents.round(3).tolist()} mm")
        self._set_hf_info("\n".join(lines))
        self.status.set(f"Imported {len(meshes)} HueForge / FlatForge mesh volume(s).")
        self.run_checks()

    def _set_hf_info(self, text):
        self.hf_info.configure(state="normal")
        self.hf_info.delete("1.0", tk.END)
        self.hf_info.insert("1.0", text)
        self.hf_info.configure(state="disabled")

    def export_face_stls(self):
        if not self.flatforge_meshes:
            messagebox.showinfo("CardForge", "Import HueForge / FlatForge geometry first.")
            return
        out = filedialog.askdirectory(title="Export normalized face STL files")
        if not out:
            return
        out = Path(out)
        for i, m in enumerate(self.flatforge_meshes, 1):
            name = m.metadata.get("source_name", f"face_{i}.stl")
            safe = Path(name.split("#")[0]).stem + (f"_{i}" if len(self.flatforge_meshes) > 1 else "") + ".stl"
            m.export(out / safe, file_type="stl")
        messagebox.showinfo("CardForge", f"Exported {len(self.flatforge_meshes)} normalized face STL file(s).")

    # ---------- GEOMETRY / ASSEMBLY ----------
    def apply_nfc_preset(self):
        name = self.nfc_preset.get()
        preset = NFC_PRESETS.get(name)
        if preset:
            self.vars["nfc_diameter_mm"].set(preset[0])
            self.vars["nfc_thickness_mm"].set(preset[1])
            self.project.nfc.preset_name = name
            self.apply_geometry()

    def apply_geometry(self):
        values = {key: float(var.get()) for key, var in self.vars.items()}
        if not all(math.isfinite(v) for v in values.values()) or min(values['card_width_mm'], values['card_height_mm']) <= 0:
            raise ValueError('Card dimensions must be positive and all dimensions must be valid numbers.')
        if max(values['card_width_mm'], values['card_height_mm']) > 256:
            raise ValueError('Card dimensions must fit the 256 mm Bambu A1 plate.')
        if min(values['corner_radius_mm'], values['face_border_mm'], values['face_clearance_mm']) < 0:
            raise ValueError('Corner radius, border and clearance cannot be negative.')
        g = self.project.geometry
        n = self.project.nfc
        for key in ["card_width_mm", "card_height_mm", "corner_radius_mm", "base_thickness_mm", "face_recess_depth_mm", "face_border_mm", "face_clearance_mm"]:
            setattr(g, key, float(self.vars[key].get()))
        n.preset_name = self.nfc_preset.get()
        for key in ["diameter_mm", "thickness_mm", "clearance_mm", "x_mm", "y_mm"]:
            setattr(n, key, float(self.vars["nfc_"+key].get()))
        self.project.editor.snap_mm = max(0.01, float(self.snap_var.get()))
        self.project.editor.show_nfc_guide = bool(self.show_nfc_var.get())
        self.draw_3d_preview()
        self.run_checks()
        if self.flatforge_meshes:
            self.flatforge_meshes = normalize_face_meshes(self.flatforge_meshes, g)
        self.status.set("Geometry updated.")

    def export_base(self):
        self.apply_geometry()
        p = filedialog.asksaveasfilename(defaultextension=".stl", filetypes=[("STL", "*.stl")], initialfile="CardForge_NFC_Base.stl")
        if p:
            export_base_stl(p, self.project.geometry, self.project.nfc)
            messagebox.showinfo("CardForge", f"Base STL saved:\n{p}")

    def export_face_blank(self):
        self.apply_geometry(); self.sync_face_fields()
        p = filedialog.asksaveasfilename(defaultextension=".stl", filetypes=[("STL", "*.stl")], initialfile="CardForge_Face_Blank.stl")
        if p:
            m = make_face_blank(self.project.geometry, self.project.face.thickness_mm)
            m.export(p, file_type="stl")
            messagebox.showinfo("CardForge", f"Face blank STL saved:\n{p}")

    def export_assembly(self):
        self._export_direct(True)

    # ---------- 3D PREVIEW ----------
    def draw_3d_preview(self):
        if not hasattr(self, "preview3d"):
            return
        c = self.preview3d
        c.delete("all")
        W = max(300, c.winfo_width())
        H = max(260, c.winfo_height())
        g = self.project.geometry
        n = self.project.nfc
        yaw = math.radians(self.yaw_var.get())
        pitch = math.radians(self.pitch_var.get())

        # Scale Z visually for readability; dimensions label remains physical.
        z_visual = 9.0
        w, h, t = g.card_width_mm, g.card_height_mm, g.base_thickness_mm * z_visual
        face_z = (g.base_thickness_mm - g.face_recess_depth_mm) * z_visual

        def rot(p):
            x, y, z = p
            x -= w/2; y -= h/2
            cy, sy = math.cos(yaw), math.sin(yaw)
            cp, sp = math.cos(pitch), math.sin(pitch)
            x, y = x*cy - y*sy, x*sy + y*cy
            y, z = y*cp - z*sp, y*sp + z*cp
            return x, y, z

        corners = [(0,0,0),(w,0,0),(w,h,0),(0,h,0),(0,0,t),(w,0,t),(w,h,t),(0,h,t)]
        rc = [rot(p) for p in corners]
        maxspan = max(w, h, t, 1)
        scale = min(W*0.72/maxspan, H*0.68/maxspan)
        def proj(p):
            x,y,z = rot(p)
            return W/2 + x*scale, H/2 + y*scale - z*scale*0.15

        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        pc = [proj(p) for p in corners]
        for a,b in edges:
            c.create_line(*pc[a], *pc[b], fill="#d8d8d8", width=2)

        # Face insert footprint slightly inset, shown at recess floor / top area.
        inset = g.face_border_mm + g.face_clearance_mm
        face_pts = [(inset,inset,face_z),(w-inset,inset,face_z),(w-inset,h-inset,face_z),(inset,h-inset,face_z)]
        fp = [proj(p) for p in face_pts]
        c.create_polygon(*[v for p in fp for v in p], outline="#42d4ff", fill="#1f3d46", width=2)

        # NFC circle sampled on the recess floor.
        circ = []
        for i in range(48):
            a = 2*math.pi*i/48
            circ.append(proj((n.x_mm + math.cos(a)*n.diameter_mm/2,
                              n.y_mm + math.sin(a)*n.diameter_mm/2,
                              face_z - 0.2)))
        c.create_line(*[v for p in circ for v in p], *circ[0], fill="#ffd65a", width=2)
        center = proj((n.x_mm,n.y_mm,face_z))
        c.create_text(center[0], center[1], text="NFC", fill="#ffd65a", font=("Segoe UI", 9, "bold"))

        c.create_text(W/2, 22, text="Blue = flush face insert | Yellow = NFC pocket", fill="white", font=("Segoe UI", 11, "bold"))
        c.create_text(W/2, H-22, text=f"{g.card_width_mm:.1f} × {g.card_height_mm:.1f} mm | base {g.base_thickness_mm:.2f} mm | face {self.project.face.thickness_mm:.2f} mm",
                      fill="#334155", font=("Segoe UI", 10))

    # ---------- CHECKS / PROJECT ----------
    def run_checks(self):
        if not hasattr(self, "check_text"):
            return
        g, n, h = self.project.geometry, self.project.nfc, self.project.hueforge
        issues, warnings, ok = [], [], []

        if g.card_width_mm <= 0 or g.card_height_mm <= 0:
            issues.append("Card dimensions must be positive.")
        else:
            ok.append("Card dimensions are valid.")

        try:
            validate_geometry(g, n)
        except ValueError as exc:
            issues.append(str(exc))
        if max(g.card_width_mm, g.card_height_mm) > 256:
            issues.append("Card exceeds the Bambu A1 256 mm build plate.")
        pocket_depth = g.face_recess_depth_mm + n.thickness_mm + n.clearance_mm
        floor = g.base_thickness_mm - pocket_depth
        if floor < 0.35:
            issues.append(f"Only {floor:.2f} mm remains under the deepest pocket; increase base thickness.")
        elif floor < 0.60:
            warnings.append(f"NFC/base floor is thin at {floor:.2f} mm; test rigidity before production.")
        else:
            ok.append(f"NFC/base floor is {floor:.2f} mm thick.")

        if g.face_recess_depth_mm < self.project.face.thickness_mm:
            warnings.append(f"Face ({self.project.face.thickness_mm:.2f} mm) is thicker than recess ({g.face_recess_depth_mm:.2f} mm), so it will stand proud unless adjusted.")
        elif g.face_recess_depth_mm - self.project.face.thickness_mm > 0.25:
            warnings.append("Face recess is much deeper than the target face; the insert may sit noticeably below the rim.")
        else:
            ok.append("Face target thickness and recess depth are closely matched.")

        rr = n.diameter_mm/2 + n.clearance_mm/2
        edge = min(n.x_mm-rr, g.card_width_mm-(n.x_mm+rr), n.y_mm-rr, g.card_height_mm-(n.y_mm+rr))
        if edge < 0:
            issues.append("NFC pocket extends outside the card.")
        elif edge < 1.0:
            warnings.append(f"NFC edge wall is only {edge:.2f} mm; aim for roughly 1 mm or more.")
        else:
            ok.append(f"NFC pocket has {edge:.2f} mm minimum edge wall.")

        if self.project.face.thickness_mm < 0.35:
            warnings.append("Face is under 0.35 mm; first-layer consistency becomes critical.")
        else:
            ok.append("Face insert thickness is plausible for a thin face-down print.")

        if len(h.palette) != 4 or len(h.filament_names) != 4:
            issues.append("Exactly four filament slots are required.")
        else:
            ok.append("Four filament slots are configured.")

        # Practical small-text warning. Point size is not exact cap height, but useful as an early warning.
        for i, t in enumerate(self.project.texts, start=1):
            em_mm = t.size_pt * 25.4 / 72.0
            if em_mm < 1.8:
                warnings.append(f"Text layer {i} ('{t.text[:18]}') is about {em_mm:.2f} mm em-height; verify it survives a 0.4 mm nozzle and face-down first layer.")
        if self.project.logo.path and self.project.logo.width_mm < 4.0:
            warnings.append("Logo is under 4 mm wide; fine internal detail may disappear.")

        ocr_layers = [t for t in self.project.texts if getattr(t, "ocr_confidence", 0.0) > 0]
        low_ocr = [t for t in ocr_layers if t.ocr_confidence < 0.70]
        if ocr_layers:
            ok.append(f"{len(ocr_layers)} OCR-assisted editable text layer(s) are present.")
            if low_ocr:
                warnings.append(f"{len(low_ocr)} OCR line(s) are below 70% confidence; verify wording before export.")

        face = self.project.face
        if face.front_depth_mm < 0.2 or face.thickness_mm-face.front_depth_mm < 0.2:
            issues.append('Front color and solid backing must each be at least 0.2 mm thick.')
        if face.thickness_mm > g.face_recess_depth_mm:
            issues.append('Face is thicker than the base recess.')
        images = [e for e in [self.project.logo, *self.project.elements] if e.path and e.enabled]
        for element in images:
            if not Path(element.path).exists():
                issues.append(f'Image is missing: {element.name}. Reload it before exporting.')
            if element.width_mm < 4:
                warnings.append(f'{element.name} is under 4 mm wide; verify fine details in the slicer.')
        if not any(t.enabled and t.text.strip() for t in self.project.texts) and not images:
            warnings.append('No editable text or logo yet. Export will produce a blank face. Photos are references only.')
        else:
            ok.append(f'Text and {len(images)} image(s) will become flush front-layer inlays, with a solid backing.')
        warnings.append('Use matching first-layer / layer heights that divide the front depth. Inspect fine lettering in the slicer before printing.')

        text = "CARDFORGE 4D PRINTABILITY REPORT\n\n"
        text += "PASS\n" + ("\n".join("✓ " + x for x in ok) if ok else "None") + "\n\n"
        text += "WARNINGS\n" + ("\n".join("! " + x for x in warnings) if warnings else "None") + "\n\n"
        text += "BLOCKING ISSUES\n" + ("\n".join("X " + x for x in issues) if issues else "None detected by current checks.")
        self.check_text.delete("1.0", tk.END)
        self.check_text.insert("1.0", text)

    def sync_ui_from_project(self):
        g, n, h = self.project.geometry, self.project.nfc, self.project.hueforge
        if hasattr(self, "vars"):
            for key in ["card_width_mm", "card_height_mm", "corner_radius_mm", "base_thickness_mm", "face_recess_depth_mm", "face_border_mm", "face_clearance_mm"]:
                self.vars[key].set(getattr(g, key))
            for key in ["diameter_mm", "thickness_mm", "clearance_mm", "x_mm", "y_mm"]:
                self.vars["nfc_"+key].set(getattr(n, key))
        self.nfc_preset.set(n.preset_name if n.preset_name in NFC_PRESETS else "Custom")
        self.logo_x.set(self.project.logo.x_mm)
        self.logo_y.set(self.project.logo.y_mm)
        self.logo_w.set(self.project.logo.width_mm)
        self.logo_opacity.set(self.project.logo.opacity / 2.55)
        self.logo_enabled_var.set(self.project.logo.enabled)
        self.refresh_logo_preview()
        self.refresh_element_list()
        self.select_element()
        self.grayscale_var.set(self.project.editor.grayscale_artwork)
        self.snap_var.set(self.project.editor.snap_mm)
        self.show_nfc_var.set(self.project.editor.show_nfc_guide)
        self.face_thickness.set(self.project.face.thickness_mm)
        self.transparent_cap.set(self.project.face.front_depth_mm)
        for i in range(4):
            self.filament_name_vars[i].set(h.filament_names[i])
            self.color_buttons[i].configure(text=h.palette[i], bg=h.palette[i])
        self.refresh_text_list()
        self.refresh_ocr_status()
        self.draw_3d_preview()
        self.run_checks()

    def start_template(self, name):
        if self.busy:
            return
        self.project = create_template(name)
        self.flatforge_meshes = []
        self.manual_points = []
        self.manual_mode = False
        self.sync_ui_from_project()
        self.show_source_original()
        self.refresh_design_preview()
        self.tabs.select(1)
        self.status.set(name+' ready. Add your logo and double-click any text to edit. Undo restores the previous card.')

    def new_project(self):
        self.start_template('Blank card')
        self.tabs.select(0)

    def _sync_edits(self):
        self.apply_logo()
        self.apply_element()
        self.apply_geometry()
        self.sync_face_fields()
        self.project.editor.snap_mm = float(self.snap_var.get())
        self.project.editor.show_nfc_guide = self.show_nfc_var.get()

    def save_project(self):
        if self.busy:
            return False
        self._sync_edits()
        path = filedialog.asksaveasfilename(defaultextension='.cardforge', initialfile=self.project.name,
                                           filetypes=[('Portable CardForge Project', '*.cardforge')])
        if not path:
            return False
        saved = self.project.save_bundle(path)
        self._saved_data = asdict(self.project)
        self.status.set(f'Saved {saved.name}. Images and fonts are included.')
        return True

    def close_project(self):
        if self.busy:
            messagebox.showinfo('CardForge', 'Please wait for the current operation to finish before closing.')
            return
        self._sync_edits()
        if asdict(self.project) != self._saved_data:
            answer = messagebox.askyesnocancel('Save your card?', 'Save your changes before closing?')
            if answer is None or (answer and not self.save_project()):
                return
        self.destroy()

    def open_project(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('CardForge Project', '*.cardforge *.cardforge.json *.json')])
        if not path:
            return
        before = self._snapshot()
        try:
            loaded = (Project.load_bundle(path, self.tempdir / uuid.uuid4().hex) if path.lower().endswith('.cardforge')
                      else Project.load(path))
            self.project = loaded
            self.flatforge_meshes = []
            self.sync_ui_from_project()
            self.show_source_original()
            self.refresh_design_preview()
            self.tabs.select(1)
            self._saved_data = asdict(self.project)
            self.status.set(f'Opened {Path(path).name}. Undo restores the previous card.')
        except Exception as exc:
            self.project, self.flatforge_meshes = before
            self.sync_ui_from_project()
            messagebox.showerror('CardForge', f'Could not open project: {exc}')

    def show_help(self):
        messagebox.showinfo('CardForge 4D '+VERSION,
            '1. Start with a blank, business or membership card.\n'
            '2. Add images and text. Select multiple PNGs for icons and emblems; drag to position.\n'
            '3. Set four filament colors or use the grayscale preset. Preview and export the face.\n'
            '4. Adjust the NFC pocket and export the base separately, or export the complete assembly.\n'
            '5. Open the 3MF as a model in Bambu Studio. Inspect every layer before printing.\n\n'
            'The face prints artwork-side down with flat front and back. Colors occupy only the front layers.\n'
            'Save a .cardforge project to keep your editable design, fonts and images together.\n\n'
            'Choose the package name and destination each time you export. Use the numbered tabs to change steps.\n\n'
            'Ctrl+S Save   Ctrl+O Open   Ctrl+Z Undo   Ctrl+Y Redo\n'
            'This preview release still needs a slicer review and physical test print for each design.')


def _undoable(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        if self.busy:
            return
        outer = self._action_depth == 0
        before = self._snapshot() if outer else None
        self._action_depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._action_depth -= 1
            if outer and asdict(before[0]) != asdict(self.project):
                self.undo_stack.append(before)
                self.undo_stack = self.undo_stack[-40:]
                self.redo_stack.clear()
    return call

for _name in ('load_photo', 'auto_correct', 'use_original', 'apply_manual_corners',
              'delete_text', 'load_logo', 'apply_logo', 'clean_logo_background',
              'load_elements', 'apply_element', 'remove_element', 'center_element', 'clean_element_background',
              'toggle_grayscale', 'grayscale_palette',
              'scale_logo', 'run_ocr', 'restore_photo_background', 'finish_logo_selection',
              'pick_filament_color', 'apply_geometry', 'sync_face_fields',
              'new_project', 'open_project', '_import_hueforge_path', 'start_template', 'duplicate_text', 'center_logo'):
    setattr(CardForgeApp, _name, _undoable(getattr(CardForgeApp, _name)))


def main():
    app = CardForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
