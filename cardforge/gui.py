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

from .core.project import Project, TextLayer
from .core.face import export_face
from .core.fonts import bundled_fonts, default_font
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


VERSION = "0.6 Alpha"
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
        self.geometry("1320x860")
        self.minsize(1120, 740)

        self.project = Project()
        self.flatforge_meshes = []
        self.tempdir = Path(tempfile.mkdtemp(prefix="CardForge4D_"))
        self.status = tk.StringVar(value="Load a business-card photo to begin.")

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
        self._style()
        self._build_menu()
        self._build_ui()
        self.sync_ui_from_project()
        self.bind('<Control-z>', lambda e: self.undo())
        self.bind('<Control-y>', lambda e: self.redo())
        self.tabs.bind('<<NotebookTabChanged>>', self._step_changed)
        self._step_changed()

    def report_callback_exception(self, exc, value, tb):
        messagebox.showerror("CardForge", str(value))

    def _style(self):
        self.configure(bg='#f3f5f8')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f3f5f8', foreground='#243247')
        style.configure('TButton', padding=(10, 7))
        style.configure('Accent.TButton', background='#245edb', foreground='white')
        style.map('Accent.TButton', background=[('active', '#1b4bb1')])
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
        style.configure('Muted.TLabel', foreground='#64748b')
        style.configure('TNotebook.Tab', padding=(16, 10))
        style.configure('TLabelframe', padding=8)

    def _scroll_panel(self, parent):
        shell = ttk.Frame(parent, width=310)
        shell.pack(side='left', fill='y', padx=(0, 12))
        canvas = tk.Canvas(shell, width=300, highlightthickness=0, bg='#f3f5f8')
        bar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=bar.set)
        inner = ttk.Frame(canvas, padding=(0, 0, 10, 8))
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        # The existing callers pack the panel; the canvas owns this inner frame.
        inner.pack = lambda *a, **k: None
        return inner

    def _step_changed(self, event=None):
        if not hasattr(self, 'step_label'):
            return
        i = self.tabs.index(self.tabs.select())
        self.step_label.configure(text=f'Step {i+1} of 5')
        self.back_button.configure(state='disabled' if i == 0 else 'normal')
        self.next_button.configure(state='disabled' if i == 4 else 'normal')
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
        if self.busy or not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())

    def redo(self):
        if self.busy or not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())

    def scale_logo(self, factor):
        self.logo_w.set(max(0.5, min(self.project.geometry.card_width_mm, self.project.logo.width_mm * factor)))
        self.apply_logo()

    def clean_logo_background(self):
        if not self.project.logo.path:
            messagebox.showinfo('CardForge', 'Load or extract a logo first.')
            return
        out = self.tempdir / (uuid.uuid4().hex + '_transparent_logo.png')
        with Image.open(self.project.logo.path) as im:
            remove_logo_background(im, float(self.bg_tolerance.get())).save(out)
        self.project.logo.path = str(out)
        self.refresh_design_preview()
        self.status.set('Logo background removed. Undo restores the original.')

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
            self.status.set('Export complete.' if ok else 'Export failed; see the error message.')
            if ok:
                done(result)
            else:
                messagebox.showerror('CardForge export', result)
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
        fm.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=fm)
        self.config(menu=menu)

    def _build_ui(self):
        header = ttk.Frame(self, padding=(18, 12))
        header.pack(fill='x')
        ttk.Label(header, text='CardForge 4D', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='PHOTO  /  DESIGN  /  PRINT', style='Muted.TLabel').pack(side='left', padx=20)
        self.undo_button = ttk.Button(header, text='Undo', command=self.undo)
        self.undo_button.pack(side='right', padx=4)
        self.redo_button = ttk.Button(header, text='Redo', command=self.redo)
        self.redo_button.pack(side='right', padx=4)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self.source_tab = ttk.Frame(self.tabs, padding=10)
        self.design_tab = ttk.Frame(self.tabs, padding=10)
        self.hf_tab = ttk.Frame(self.tabs, padding=10)
        self.assembly_tab = ttk.Frame(self.tabs, padding=10)
        self.check_tab = ttk.Frame(self.tabs, padding=10)

        self.tabs.add(self.source_tab, text="1  Photo")
        self.tabs.add(self.design_tab, text="2  Edit")
        self.tabs.add(self.hf_tab, text="3  Face / Colors")
        self.tabs.add(self.assembly_tab, text="4  NFC / Assembly")
        self.tabs.add(self.check_tab, text="5  Printability")

        self._source_ui()
        self._design_ui()
        self._face_ui()
        self._assembly_ui()
        self._check_ui()

        nav = ttk.Frame(self, padding=(18, 8))
        nav.pack(fill='x')
        self.back_button = ttk.Button(nav, text='Back', command=lambda: self.navigate(-1))
        self.back_button.pack(side='left')
        self.step_label = ttk.Label(nav, style='Muted.TLabel')
        self.step_label.pack(side='left', padx=16)
        self.next_button = ttk.Button(nav, text='Next', style='Accent.TButton', command=lambda: self.navigate(1))
        self.next_button.pack(side='right')
        self.progress = ttk.Progressbar(self, mode='indeterminate')
        self.progress.pack(fill='x', padx=18)
        ttk.Label(self, textvariable=self.status, anchor='w', padding=(18, 8)).pack(fill='x')

    def _source_ui(self):
        controls = ttk.Frame(self.source_tab)
        controls.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(controls, text="Business-card photo", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Button(controls, text="Load Photo...", command=self.load_photo).pack(fill="x", pady=(12, 4))
        ttk.Button(controls, text="Auto Perspective Correct", command=self.auto_correct).pack(fill="x", pady=4)
        ttk.Separator(controls).pack(fill="x", pady=8)
        ttk.Button(controls, text="Manual 4-Corner Mode", command=self.start_manual_corners).pack(fill="x", pady=3)
        ttk.Button(controls, text="Apply Manual Corners", command=self.apply_manual_corners).pack(fill="x", pady=3)
        ttk.Button(controls, text="Reset Corner Points", command=self.reset_manual_corners).pack(fill="x", pady=3)
        ttk.Separator(controls).pack(fill="x", pady=8)
        ttk.Button(controls, text="Use Centered Crop", command=self.use_original).pack(fill="x", pady=3)
        ttk.Label(
            controls,
            text=("Manual mode: click the four visible card corners in any order. "
                  "CardForge will reorder them and perspective-warp the image to business-card proportions."),
            wraplength=285, justify="left"
        ).pack(anchor="w", pady=12)
        self.manual_label = ttk.Label(controls, text="Manual points: 0 / 4")
        self.manual_label.pack(anchor="w")

        self.source_canvas = tk.Canvas(self.source_tab, bg="#242424", highlightthickness=0)
        self.source_canvas.pack(side="right", fill="both", expand=True)
        self.source_canvas.bind("<Button-1>", self.source_canvas_click)

    def _design_ui(self):
        left = self._scroll_panel(self.design_tab)
        left.pack(side="left", fill="y", padx=(0, 10))
        right = ttk.Frame(self.design_tab)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="Editable layers", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.text_list = tk.Listbox(left, width=34, height=6)
        self.text_list.pack(fill="x", pady=(10, 4))
        ttk.Button(left, text="Add Text Layer", command=self.add_text).pack(fill="x", pady=2)
        ttk.Button(left, text="Edit Selected Text", command=self.edit_selected_text).pack(fill="x", pady=2)
        ttk.Button(left, text="Delete Selected Text", command=self.delete_text).pack(fill="x", pady=2)
        ttk.Button(left, text="Scan Text (Offline OCR)", command=self.run_ocr).pack(fill="x", pady=(8, 2))
        ttk.Button(left, text="Restore Photo Background", command=self.restore_photo_background).pack(fill="x", pady=2)
        self.ocr_status_var = tk.StringVar(value="OCR backend not checked")
        ttk.Label(left, textvariable=self.ocr_status_var, wraplength=285, justify="left").pack(anchor="w", pady=(4, 2))

        ttk.Separator(left).pack(fill="x", pady=10)
        ttk.Label(left, text="Logo").pack(anchor="w")
        ttk.Button(left, text="Load / Replace Logo...", command=self.load_logo).pack(fill="x", pady=2)
        ttk.Button(left, text="Auto Find Logo Candidate", command=self.auto_find_logo).pack(fill="x", pady=2)
        ttk.Button(left, text="Extract Logo From Card", command=self.start_logo_selection).pack(fill="x", pady=2)
        self.logo_x = tk.DoubleVar()
        self.logo_y = tk.DoubleVar()
        self.logo_w = tk.DoubleVar()
        for label, var in [("Logo X mm", self.logo_x), ("Logo Y mm", self.logo_y), ("Logo width mm", self.logo_w)]:
            self._field(left, label, var)
        ttk.Button(left, text="Apply Logo Position / Size", command=self.apply_logo).pack(fill="x", pady=4)
        scale_row = ttk.Frame(left)
        scale_row.pack(fill='x')
        ttk.Button(scale_row, text='Smaller −', command=lambda: self.scale_logo(0.9)).pack(side='left', expand=True, fill='x')
        ttk.Button(scale_row, text='Larger +', command=lambda: self.scale_logo(1.1)).pack(side='left', expand=True, fill='x')
        self.bg_tolerance = tk.DoubleVar(value=34)
        self._field(left, 'Background tolerance', self.bg_tolerance)
        ttk.Button(left, text='Remove Logo Background', command=self.clean_logo_background).pack(fill='x', pady=4)
        ttk.Label(left, text='Best for a plain background. Undo restores the original.', wraplength=260, style='Muted.TLabel').pack(anchor='w')

        ttk.Separator(left).pack(fill="x", pady=10)
        self.snap_var = tk.DoubleVar(value=0.25)
        self.show_nfc_var = tk.BooleanVar(value=True)
        self._field(left, "Drag snap mm", self.snap_var)
        ttk.Checkbutton(left, text="Show NFC guide", variable=self.show_nfc_var,
                        command=self.refresh_design_preview).pack(anchor="w", pady=4)
        ttk.Label(
            left,
            text=("OCR can remove detected photographed text and recreate it as editable layers. "
                  "Use Extract Logo From Card, then drag text or the logo directly on the preview."),
            wraplength=285, justify="left"
        ).pack(anchor="w", pady=10)

        self.design_canvas = tk.Canvas(right, bg="#242424", highlightthickness=0)
        self.design_canvas.pack(fill="both", expand=True)
        self.design_canvas.bind("<ButtonPress-1>", self.design_press)
        self.design_canvas.bind("<B1-Motion>", self.design_drag)
        self.design_canvas.bind("<ButtonRelease-1>", self.design_release)
        ttk.Button(right, text="Refresh Edited Preview", command=self.refresh_design_preview).pack(anchor="e", pady=(8, 0))

    def _face_ui(self):
        left = ttk.Frame(self.hf_tab)
        left.pack(side="left", fill="y", padx=(0, 12))
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

        ttk.Button(left, text='Preview Face', command=self.refresh_face_preview).pack(fill='x', pady=4)
        ttk.Label(left, text='Thirty bundled OFL fonts are available when editing text.', wraplength=300, style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
        ttk.Button(left, text='Choose Background Color', command=self.pick_face_background).pack(fill='x', pady=4)
        ttk.Button(left, text='Export Face 3MF + STLs…', command=self.export_face_files).pack(fill='x', pady=4)
        ttk.Label(right, text='Front layers: flush text and logo inlays. Back layers: a continuous solid sheet. Both sides are flat. Assign colors to named parts in Bambu Studio.', wraplength=680, font=('Segoe UI', 11)).pack(anchor='nw')
        ttk.Label(right, text='The photo is a layout reference. Scan/retype text and extract or load your logo to create printable elements. No HueForge step is required.', wraplength=680).pack(anchor='nw', pady=8)

        self.hf_preview_canvas = tk.Canvas(right, height=360, bg="#242424", highlightthickness=0)
        self.hf_preview_canvas.pack(fill="x", expand=False, pady=(12, 8))
        self.hf_info = tk.Text(right, height=12, wrap="word")
        self.hf_info.pack(fill="both", expand=True)
        self._set_hf_info("Ready to generate the face directly from editable text and logo layers.")

    def _assembly_ui(self):
        left = self._scroll_panel(self.assembly_tab)
        left.pack(side="left", fill="y", padx=(0, 12))
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
        ttk.Button(left, text="Apply Dimensions", command=self.apply_geometry).pack(fill="x", pady=3)
        ttk.Button(left, text="Export NFC Base STL...", command=self.export_base).pack(fill="x", pady=3)
        ttk.Button(left, text="Export Thin Face Blank STL...", command=self.export_face_blank).pack(fill="x", pady=3)
        ttk.Button(left, text="Export Complete Assembly Folder...", command=self.export_assembly).pack(fill="x", pady=3)

        top = ttk.Frame(right)
        top.pack(fill="x")
        self.yaw_var = tk.DoubleVar(value=-28)
        self.pitch_var = tk.DoubleVar(value=22)
        ttk.Label(top, text="3D assembly preview", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, text="Yaw").pack(side="left", padx=(24, 4))
        ttk.Scale(top, from_=-70, to=70, variable=self.yaw_var, command=lambda _=None: self.draw_3d_preview()).pack(side="left", fill="x", expand=True)
        ttk.Label(top, text="Pitch").pack(side="left", padx=(12, 4))
        ttk.Scale(top, from_=-10, to=70, variable=self.pitch_var, command=lambda _=None: self.draw_3d_preview()).pack(side="left", fill="x", expand=True)

        self.preview3d = tk.Canvas(right, bg="#242424", highlightthickness=0)
        self.preview3d.pack(fill="both", expand=True, pady=(8, 0))
        self.preview3d.bind("<Configure>", lambda e: self.draw_3d_preview())

    def _check_ui(self):
        top = ttk.Frame(self.check_tab)
        top.pack(fill="x")
        ttk.Label(top, text="Printability report", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top, text="Run Checks", command=self.run_checks).pack(side="right")
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
            self.show_image_on_canvas(Image.open(self.project.source_image), self.source_canvas, "source")
            self.redraw_manual_points()

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
        return self.analysis_image()

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
        )

    def show_image_on_canvas(self, image, canvas, key):
        image = image.convert("RGB")
        canvas.update_idletasks()
        cw = max(120, canvas.winfo_width() - 20)
        ch = max(120, canvas.winfo_height() - 20)
        scale = min(cw / image.width, ch / image.height)
        vw = max(1, int(image.width * scale))
        vh = max(1, int(image.height * scale))
        view = image.resize((vw, vh), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(view)
        x0 = (canvas.winfo_width() - vw) / 2
        y0 = (canvas.winfo_height() - vh) / 2
        canvas.delete("all")
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
                              outline="white", dash=(4, 3), width=2, tags="guide")
                c.create_text(center[0], center[1], text="NFC", fill="white", tags="guide")

        # Centers make drag targets discoverable without obscuring the art.
        for i, t in enumerate(self.project.texts):
            p = self.card_mm_to_canvas(t.x_mm, t.y_mm)
            if p:
                c.create_rectangle(p[0]-4, p[1]-4, p[0]+4, p[1]+4,
                                   outline="#00e5ff", width=2, tags="guide")
        if self.project.logo.path:
            p = self.card_mm_to_canvas(self.project.logo.x_mm, self.project.logo.y_mm)
            if p:
                c.create_oval(p[0]-5, p[1]-5, p[0]+5, p[1]+5,
                              outline="#ffdc5e", width=2, tags="guide")

    def refresh_text_list(self):
        self.text_list.delete(0, tk.END)
        for i, t in enumerate(self.project.texts):
            self.text_list.insert(tk.END, f"{i+1}. {t.text[:25]}" + (f"  OCR {t.ocr_confidence*100:.0f}%" if getattr(t, "ocr_confidence", 0) else ""))

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
        win = tk.Toplevel(self)
        win.title("Text Layer")
        win.geometry("560x650")
        win.transient(self)
        layer = self.project.texts[index] if index is not None else TextLayer()
        vars_ = {
            "text": tk.StringVar(value=layer.text),
            "x": tk.DoubleVar(value=layer.x_mm),
            "y": tk.DoubleVar(value=layer.y_mm),
            "size": tk.IntVar(value=layer.size_pt),
            "font": tk.StringVar(value=layer.font_path),
            "color": tk.StringVar(value=layer.color),
        }
        for label, key in [("Text", "text"), ("X mm", "x"), ("Y mm", "y"), ("Size pt", "size"), ("TTF/OTF font", "font"), ("Color", "color")]:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(7, 0))
            row = ttk.Frame(win); row.pack(fill="x", padx=10)
            ttk.Entry(row, textvariable=vars_[key]).pack(side="left", fill="x", expand=True)
            if key == "font":
                ttk.Button(row, text="Browse", command=lambda: self.pick_font(vars_["font"])).pack(side="right", padx=(4, 0))
            if key == "color":
                ttk.Button(row, text="Pick", command=lambda: self.pick_text_color(vars_["color"])).pack(side="right", padx=(4, 0))

        choices = bundled_fonts()
        ttk.Label(win, text=f'Bundled fonts ({len(choices)})').pack(anchor='w', padx=10, pady=(10, 0))
        chosen = tk.StringVar()
        fonts = ttk.Combobox(win, state='readonly', values=list(choices), textvariable=chosen)
        fonts.pack(fill='x', padx=10)
        fonts.bind('<<ComboboxSelected>>', lambda e: vars_['font'].set(choices[chosen.get()]))
        for name, path in choices.items():
            if path == (layer.font_path or default_font()):
                chosen.set(name)
        sample = ttk.Label(win)
        sample.pack(fill='x', padx=10, pady=10)
        def preview(*args):
            try:
                font = ImageFont.truetype(vars_['font'].get() or default_font(), min(60, max(8, int(vars_['size'].get())*2)))
                im = Image.new('RGB', (520, 85), 'white')
                ImageDraw.Draw(im).text((12, 42), vars_['text'].get() or 'CardForge — Sample Aa 123', font=font, fill=vars_['color'].get(), anchor='lm')
                sample.photo = ImageTk.PhotoImage(im)
                sample.configure(image=sample.photo)
            except (ValueError, OSError, tk.TclError):
                pass
        for key in ('font', 'text', 'size', 'color'):
            vars_[key].trace_add('write', preview)
        preview()

        def save():
            self._remember()
            new = TextLayer(
                vars_["text"].get(), float(vars_["x"].get()), float(vars_["y"].get()),
                int(vars_["size"].get()), vars_["font"].get() or default_font(), vars_["color"].get()
            )
            if index is None:
                self.project.texts.append(new)
            else:
                self.project.texts[index] = new
            win.destroy()
            self.refresh_design_preview()

        ttk.Button(win, text="Save", command=save).pack(fill="x", padx=10, pady=12)

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
            self.project.logo.path = p
            self.refresh_design_preview()

    def apply_logo(self):
        self.project.logo.x_mm = float(self.logo_x.get())
        self.project.logo.y_mm = float(self.logo_y.get())
        self.project.logo.width_mm = max(0.5, float(self.logo_w.get()))
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
        p = self.canvas_to_card_mm(event.x, event.y)
        if p is None:
            return
        x, y = p
        candidates = []
        for i, t in enumerate(self.project.texts):
            # Approximate hit box from font em-height and character count.
            em = max(1.0, t.size_pt * 25.4 / 72.0)
            half_w = max(2.0, len(t.text) * em * 0.26)
            half_h = max(1.5, em * 0.65)
            if abs(x - t.x_mm) <= half_w and abs(y - t.y_mm) <= half_h:
                candidates.append((math.hypot(x-t.x_mm, y-t.y_mm), ("text", i)))
        if self.project.logo.path:
            try:
                im = Image.open(self.project.logo.path)
                h_mm = self.project.logo.width_mm * im.height / max(1, im.width)
            except Exception:
                h_mm = self.project.logo.width_mm
            if abs(x-self.project.logo.x_mm) <= self.project.logo.width_mm/2 and abs(y-self.project.logo.y_mm) <= h_mm/2:
                candidates.append((math.hypot(x-self.project.logo.x_mm, y-self.project.logo.y_mm), ("logo", 0)))
        if candidates:
            self._remember()
            candidates.sort(key=lambda z: z[0])
            self.drag_target = candidates[0][1]
            self.dragging = True

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
        self.dragging = False
        self.drag_target = None

    # ---------- OCR / LOGO EXTRACTION ----------
    def refresh_ocr_status(self):
        ok, text = backend_status()
        if hasattr(self, "ocr_status_var"):
            self.ocr_status_var.set(("Ready: " if ok else "Not ready: ") + text)
        return ok

    def run_ocr(self):
        im = self.analysis_image()
        if im is None:
            messagebox.showinfo("CardForge", "Load and correct a business-card photo first.")
            return
        ok, text = backend_status()
        self.refresh_ocr_status()
        if not ok:
            messagebox.showwarning(
                "CardForge OCR",
                "The offline OCR engine is not installed in this source environment. "
                "The Windows release build installs and bundles RapidOCR + ONNX Runtime.\n\n" + text
            )
            return
        try:
            self.status.set("Scanning text with offline OCR...")
            self.update_idletasks()
            found = ocr_candidates(
                im, self.project.geometry.card_width_mm, self.project.geometry.card_height_mm
            )
            self.project.ocr_candidates = [c.to_dict() for c in found]
            self.project.ocr_backend = "RapidOCR / ONNX Runtime"

            # Replace the previous OCR-generated layers instead of duplicating them.
            self.project.texts = [t for t in self.project.texts if not getattr(t, "source_box_px", [])]
            self.project.texts.extend(candidates_to_text_layers(found, TextLayer))

            if self.project.editor.ocr_remove_original and found:
                cleaned = remove_ocr_text(im, found)
                out = self.tempdir / (uuid.uuid4().hex + "_ocr_cleaned_card.png")
                cleaned.save(out)
                self.project.cleaned_image = str(out)

            self.refresh_design_preview()
            low = sum(1 for c in found if c.confidence < 0.70)
            self.status.set(f"OCR created {len(found)} editable text layer(s); {low} are below 70% confidence.")
            messagebox.showinfo(
                "CardForge OCR",
                f"Detected {len(found)} text line(s). They are now editable text layers. "
                f"{low} line(s) are below 70% confidence and should be checked manually."
            )
        except Exception as e:
            messagebox.showerror("CardForge OCR", f"OCR failed:\n{e}")

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
            self.refresh_design_preview()
            self.status.set("Logo extracted to a transparent editable layer. Drag it or replace it with an original logo file.")
        except Exception as e:
            messagebox.showerror("CardForge Logo", f"Logo extraction failed:\n{e}")

    # ---------- HUEFORGE ----------
    def pick_filament_color(self, idx):
        c = colorchooser.askcolor(initialcolor=self.project.hueforge.palette[idx])
        if c[1]:
            self.project.hueforge.palette[idx] = c[1].upper()
            self.color_buttons[idx].configure(text=c[1].upper(), bg=c[1])
            self.refresh_face_preview()

    def sync_face_fields(self):
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
        im = Image.new('RGB', (1600, round(1600*g.card_height_mm/g.card_width_mm)), self.project.face.background_color)
        im = compose_editable_layers(im, g.card_width_mm, g.card_height_mm, self.project.texts, self.project.logo)
        self.show_image_on_canvas(im, self.hf_preview_canvas, 'face')
        self._set_hf_info(f'{len(self.project.texts)} text layer(s). Logo colors use the four-color palette.\nFront inlays: {self.project.face.front_depth_mm:.2f} mm\nSolid backing: {self.project.face.thickness_mm-self.project.face.front_depth_mm:.2f} mm\nExport produces named parts, ready to assign filaments in Bambu Studio.\nArtwork will be mirrored automatically for face-down printing.')

    def export_face_files(self):
        self._export_direct(False)

    def _export_direct(self, include_base):
        if self.busy:
            return
        self.sync_face_fields()
        self.apply_logo()
        self.apply_geometry()
        out = filedialog.askdirectory(title='Choose CardForge face output folder')
        if not out:
            return
        snapshot = copy.deepcopy(self.project)
        self._background('Generating flush face geometry…', lambda: export_face(snapshot, out, include_base),
                         lambda result: messagebox.showinfo('CardForge', f'Face files ready in:\n{result}\n\nOpen CardForge_Face.3mf in Bambu Studio and assign filament colors under Objects / Parts.'))

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
                      fill="white", font=("Segoe UI", 10))

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
        if not self.project.texts and not self.project.logo.path:
            warnings.append('No editable text or logo yet. Export will produce a blank face. Photos are references only.')
        else:
            ok.append('Text and logo will become flush front-layer inlays, with a solid backing.')
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

    def new_project(self):
        self.project = Project()
        self.flatforge_meshes = []
        self.manual_points = []
        self.manual_mode = False
        self.sync_ui_from_project()
        for canvas in [self.source_canvas, self.design_canvas, self.hf_preview_canvas]:
            canvas.delete("all")
        self._set_hf_info("Ready to generate the face directly from editable text and logo layers.")
        self.status.set("New project created.")

    def save_project(self):
        self.apply_logo(); self.apply_geometry(); self.sync_face_fields()
        p = filedialog.asksaveasfilename(
            defaultextension=".cardforge",
            filetypes=[("Portable CardForge Project", "*.cardforge"), ("Legacy JSON", "*.cardforge.json *.json")]
        )
        if p:
            if str(p).lower().endswith(".cardforge"):
                saved = self.project.save_bundle(p)
            else:
                self.project.save(p); saved = Path(p)
            self.status.set(f"Saved {Path(saved).name}")

    def open_project(self):
        p = filedialog.askopenfilename(
            filetypes=[("CardForge Project", "*.cardforge *.cardforge.json *.json"), ("All files", "*.*")]
        )
        if not p:
            return
        try:
            if str(p).lower().endswith(".cardforge"):
                extract_dir = self.tempdir / (Path(p).stem + "_assets")
                self.project = Project.load_bundle(p, extract_dir)
            else:
                self.project = Project.load(p)
            self.flatforge_meshes = []
            # Older project artwork is retained; imported HueForge meshes are no longer used.
            self.sync_ui_from_project()
            if self.project.source_image and Path(self.project.source_image).exists():
                shown = self.project.corrected_image if self.project.corrected_image and Path(self.project.corrected_image).exists() else self.project.source_image
                self.show_image_on_canvas(Image.open(shown), self.source_canvas, "source")
                self.refresh_design_preview()
                self.refresh_face_preview()
            self.status.set(f"Opened {Path(p).name}")
        except Exception as e:
            messagebox.showerror("CardForge", f"Could not open project:\n{e}")


def _undoable(method):
    @wraps(method)
    def call(self, *args, **kwargs):
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
              'scale_logo', 'run_ocr', 'restore_photo_background', 'finish_logo_selection',
              'pick_filament_color', 'apply_geometry', 'sync_face_fields',
              'new_project', 'open_project', '_import_hueforge_path'):
    setattr(CardForgeApp, _name, _undoable(getattr(CardForgeApp, _name)))


def main():
    app = CardForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
