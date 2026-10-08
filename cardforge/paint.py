"""Focused image workshop: connected selections, paint and reversible cleanup."""
import uuid
import tkinter as tk
from tkinter import ttk
import numpy as np
from PIL import Image, ImageTk, ImageDraw
from .core.painting import PixelEditor
from .core.colors import effective_palette


class ImageWorkshop(ttk.Frame):
    def __init__(self, app, layer):
        super().__init__(app.paint_host)
        self.pack(fill='both', expand=True)
        self.app, self.layer = app, layer
        with Image.open(layer.path) as raw: im = raw.convert('RGBA')
        original_size = im.size
        # Bounded working resolution and undo memory prevent huge imports freezing the UI.
        im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        self.resampled = im.size != original_size
        slots = None
        if layer.paint_slots_path:
            with Image.open(layer.paint_slots_path) as raw:
                if raw.size != original_size: raise ValueError('Paint map dimensions do not match this image.')
                slots = raw.convert('L').resize(im.size, Image.Resampling.NEAREST)
        with Image.open(layer.edit_source_path or layer.path) as raw:
            original = raw.convert('RGBA').resize(im.size, Image.Resampling.LANCZOS)
        self.editor = PixelEditor(im, slots, original)
        self.palette = effective_palette(app.project)
        self.tool = tk.StringVar(value='wand'); self.slot = tk.IntVar(value=1)
        self.tolerance = tk.IntVar(value=30); self.brush = tk.IntVar(value=8)
        self.contiguous = tk.BooleanVar(value=True)
        self.region_source = tk.StringVar(value='Original image regions')
        self.cutoff = tk.IntVar(value=layer.alpha_cutoff)
        self.edge_preview = tk.BooleanVar(value=False)
        self._fit_ready = False
        self.zoom = 1.; self.last_point = None; self._render_job = None
        self.status = tk.StringVar(value='Wand: click one image element, then choose a filament and Fill selection.')
        header = ttk.Frame(self, padding=14); header.pack(fill='x')
        ttk.Label(header, text='Paint colors & refine edges', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='Editing an image • Position and size stay on the object', style='Muted.TLabel').pack(side='right')
        footer = ttk.Frame(self, padding=12); footer.pack(side='bottom', fill='x')
        app._button(footer, 'Cancel painting', self.cancel, 'back').pack(side='left')
        app._button(footer, 'Done painting', self.apply, 'check', 'Accent.TButton').pack(side='right')
        ttk.Label(self, textvariable=self.status, padding=(14, 6), style='Muted.TLabel', wraplength=990).pack(side='bottom', fill='x')
        if self.resampled:
            ttk.Label(self, text=f'Working copy: {im.width} × {im.height} pixels. Original file is preserved.', style='Muted.TLabel').pack(side='bottom')
        body = ttk.Frame(self, padding=(14, 0)); body.pack(fill='both', expand=True)
        control_shell = ttk.Frame(body); control_shell.pack(side='right', fill='y', padx=(12,0))
        control_canvas = tk.Canvas(control_shell, width=232, bg='#1a1d23', highlightthickness=0)
        scroll = ttk.Scrollbar(control_shell, orient='vertical', command=control_canvas.yview)
        scroll.pack(side='right', fill='y'); control_canvas.pack(side='left', fill='y')
        controls = ttk.Frame(control_canvas, padding=(0,0,6,8))
        control_item = control_canvas.create_window(0,0,window=controls,anchor='nw')
        controls.bind('<Configure>',lambda e: control_canvas.configure(scrollregion=control_canvas.bbox('all')))
        control_canvas.bind('<Configure>',lambda e: control_canvas.itemconfigure(control_item,width=e.width))
        control_canvas.configure(yscrollcommand=scroll.set)
        def scroll_controls(event):
            widget = event.widget
            while widget is not None:
                if widget == control_shell:
                    control_canvas.yview_scroll(-int(event.delta/120),'units'); return
                widget = getattr(widget,'master',None)
        self.bind('<MouseWheel>',scroll_controls,add='+')
        ttk.Label(controls, text='TOOLS', style='Step.TLabel').pack(anchor='w', pady=(0, 6))
        tools = ttk.Frame(controls); tools.pack(fill='x')
        for i, (name, value) in enumerate([('Wand', 'wand'), ('Paint', 'paint'), ('Erase', 'erase'), ('Restore', 'restore')]):
            ttk.Radiobutton(tools, text=name, variable=self.tool, value=value).grid(row=i//2, column=i%2, sticky='w', padx=(0, 12), pady=5)
        ttk.Label(controls, text='Wand tolerance · 0–255').pack(anchor='w', pady=(10, 0))
        ttk.Spinbox(controls, from_=0, to=255, textvariable=self.tolerance, width=8).pack(anchor='w')
        ttk.Checkbutton(controls, text='Connected region only', variable=self.contiguous).pack(anchor='w', pady=6)
        ttk.Combobox(controls, textvariable=self.region_source, state='readonly',
                    values=['Original image regions', 'Displayed colors']).pack(fill='x', pady=4)
        ttk.Label(controls, text='Click a new part to replace selection.\nShift-click adds; Alt-click subtracts.',
                  style='Muted.TLabel', wraplength=220).pack(anchor='w', pady=(4, 8))
        ttk.Label(controls, text='Brush diameter · image pixels').pack(anchor='w')
        ttk.Spinbox(controls, from_=1, to=200, textvariable=self.brush, width=8).pack(anchor='w', pady=(0, 12))
        ttk.Label(controls, text='PAINT FILAMENT', style='Step.TLabel').pack(anchor='w')
        row = ttk.Frame(controls); row.pack(fill='x', pady=8)
        for i, color in enumerate(self.palette, 1):
            ink = 'white' if sum(int(color[k:k+2],16) for k in (1,3,5)) < 400 else '#203149'
            tk.Radiobutton(row, text=str(i), value=i, variable=self.slot, indicatoron=False, width=4,
                           bg=color, fg=ink, selectcolor=color, relief='raised', bd=3).pack(side='left', padx=2)
        app._button(controls, 'Fill selection', lambda: self.action(lambda: self.editor.fill('paint', self.slot.get())), 'layers', 'Accent.TButton').pack(fill='x', pady=3)
        row = ttk.Frame(controls); row.pack(fill='x', pady=3)
        app._button(row, 'Erase', lambda: self.action(lambda: self.editor.fill('erase'))).pack(side='left', expand=True, fill='x')
        app._button(row, 'Restore', lambda: self.action(lambda: self.editor.fill('restore'))).pack(side='right', expand=True, fill='x', padx=(4,0))
        row = ttk.Frame(controls); row.pack(fill='x',pady=3)
        app._button(row, 'Clear selection', self.clear_selection).pack(side='left',fill='x',expand=True)
        app._button(row, 'Invert', self.invert_selection).pack(side='right',fill='x',expand=True,padx=(4,0))
        ttk.Label(controls, text='REFINE SELECTION', style='Step.TLabel').pack(anchor='w', pady=(12, 5))
        row = ttk.Frame(controls); row.pack(fill='x')
        for label, action in [('Grow', 'grow'), ('Shrink', 'shrink'), ('Smooth', 'smooth')]:
            app._button(row, label, lambda a=action: self.action(lambda: self.editor.refine(a))).pack(side='left', expand=True, fill='x')
        ttk.Label(controls, text='Print edge threshold · 1–255').pack(anchor='w', pady=(12,0))
        ttk.Spinbox(controls, from_=1, to=255, textvariable=self.cutoff, width=8, command=self.render).pack(anchor='w')
        ttk.Checkbutton(controls, text='Show printable edge', variable=self.edge_preview, command=self.render).pack(anchor='w', pady=5)
        self.cutoff.trace_add('write', lambda *_: self.schedule_render())
        ttk.Label(controls, text='Lower threshold keeps soft edges.\nSelection limits brush strokes.\nRestore recovers original pixels.', style='Muted.TLabel').pack(anchor='w', pady=5)
        right = ttk.Frame(body); right.pack(fill='both', expand=True)
        bar = ttk.Frame(right); bar.pack(fill='x', pady=(0,8))
        app._button(bar, 'Undo', lambda: self.action(self.editor.undo), 'undo').pack(side='left')
        app._button(bar, 'Redo', lambda: self.action(self.editor.redo), 'redo').pack(side='left', padx=4)
        app._button(bar, 'Reset image', self.reset_image).pack(side='left')
        app._button(bar, '+', lambda: self.change_zoom(1.5)).pack(side='right')
        app._button(bar, '−', lambda: self.change_zoom(1/1.5)).pack(side='right', padx=4)
        app._button(bar, 'Fit', self.fit).pack(side='right')
        self.canvas = tk.Canvas(right, bg='#111317', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Escape>', lambda e: self.clear_selection())
        self.canvas.bind('<Configure>', lambda e: self.schedule_render() if self._fit_ready else self.after_idle(self.fit))
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', lambda e: setattr(self, 'last_point', None))
        self.canvas.bind('<MouseWheel>', lambda e: self.change_zoom(1.25 if e.delta > 0 else .8))
        self.canvas.bind('<ButtonPress-2>', self.pan_start)
        self.canvas.bind('<B2-Motion>', self.pan)
        ttk.Label(right, text='Wheel: zoom • Middle-drag: pan • Dotted outline: selection • Escape: clear', style='Muted.TLabel').pack(anchor='w', pady=6)
        self.bind('<Control-z>', lambda e: self.action(self.editor.undo))
        self.bind('<Control-y>', lambda e: self.action(self.editor.redo))
        self.bind('<Escape>', lambda e: self.clear_selection())
        self.update_idletasks(); self.fit()

    def valid_int(self, variable, minimum, maximum, label):
        try: value = variable.get()
        except tk.TclError: raise ValueError(f'{label}: enter a whole number from {minimum} to {maximum}.')
        if not minimum <= value <= maximum: raise ValueError(f'{label}: use {minimum}–{maximum}.')
        return value

    def action(self, callback):
        try:
            callback(); self.render()
            count = int(self.editor.selection.sum()) if self.editor.selection is not None else 0
            self.status.set(f'{count:,} selected pixels. Click a new part to replace selection; Done painting keeps your edits.')
        except (ValueError, tk.TclError) as exc: self.status.set(str(exc))

    def clear_selection(self):
        if self.editor.selection is not None:
            self.editor.remember(); self.editor.selection = None
        self.render(); self.status.set('Selection cleared. Brushes now work anywhere on the image.')

    def invert_selection(self):
        if self.editor.selection is None:
            self.status.set('Select a region with the Wand first.'); return
        self.editor.remember(); self.editor.selection = ~self.editor.selection; self.render()
        self.status.set('Selection inverted. Erase selection removes everything outside the previous selection.')

    def reset_image(self):
        self.editor.remember()
        self.editor.image = self.editor.original.copy()
        self.editor.slots = Image.new('L', self.editor.image.size)
        self.editor.selection = None; self.render()
        self.status.set('Original pixels restored. You can undo this reset.')

    def fit(self):
        c = self.canvas; im = self.editor.image
        if c.winfo_width() <= 100 or c.winfo_height() <= 100: return
        self._fit_ready = True
        self.zoom = min((max(100,c.winfo_width())-30)/im.width, (max(100,c.winfo_height())-30)/im.height)
        self.ox = (c.winfo_width()-im.width*self.zoom)/2
        self.oy = (c.winfo_height()-im.height*self.zoom)/2
        self.render()

    def change_zoom(self, factor):
        cx, cy = self.canvas.winfo_width()/2, self.canvas.winfo_height()/2
        new = min(32, max(.05, self.zoom*factor)); ratio = new/self.zoom
        self.ox, self.oy = cx+(self.ox-cx)*ratio, cy+(self.oy-cy)*ratio
        self.zoom = new; self.render()

    def pan_start(self, event): self.pan_origin = (event.x, event.y, self.ox, self.oy)

    def pan(self, event):
        x,y,ox,oy = self.pan_origin; self.ox, self.oy = ox+event.x-x, oy+event.y-y; self.render()

    def point(self, event): return ((event.x-self.ox)/self.zoom, (event.y-self.oy)/self.zoom)

    def press(self, event):
        try:
            point = self.point(event)
            if not (0 <= point[0] < self.editor.image.width and 0 <= point[1] < self.editor.image.height): return
            if self.tool.get() == 'wand':
                tolerance = self.valid_int(self.tolerance,0,255,'Tolerance')
                operation = 'subtract' if getattr(event, 'state', 0) & 8 else 'add' if getattr(event, 'state', 0) & 1 else 'replace'
                source = 'original' if self.region_source.get() == 'Original image regions' else 'display'
                self.action(lambda: self.editor.select_region(point,tolerance,self.contiguous.get(),self.palette,source,operation))
            else:
                self.valid_int(self.brush,1,200,'Brush diameter')
                self.editor.remember(); self.last_point = point
                self.drag(event)
        except ValueError as exc: self.status.set(str(exc))

    def drag(self, event):
        if self.last_point is None: return
        try:
            point = self.point(event)
            self.editor.stroke(self.last_point,point,self.valid_int(self.brush,1,200,'Brush diameter'),self.tool.get(),self.slot.get())
            self.last_point = point; self.schedule_render()
        except ValueError as exc: self.last_point = None; self.status.set(str(exc))

    def schedule_render(self):
        if self._render_job is None: self._render_job = self.after(30,self.render)

    def render(self):
        if self._render_job is not None: self.after_cancel(self._render_job); self._render_job = None
        if not hasattr(self,'ox'): return
        c = self.canvas; w,h = max(1,c.winfo_width()),max(1,c.winfo_height())
        # Transform only the viewport; even 3200% zoom never allocates a giant image.
        image = self.editor.preview(self.palette)
        if self.edge_preview.get():
            try: cutoff = self.valid_int(self.cutoff,1,255,'Edge threshold')
            except ValueError: return
            image.putalpha(image.getchannel('A').point(lambda a: 255 if a*self.layer.opacity/255 >= cutoff else 0))
        tile = image.transform((w,h),Image.Transform.AFFINE,(1/self.zoom,0,-self.ox/self.zoom,0,1/self.zoom,-self.oy/self.zoom),resample=Image.Resampling.NEAREST)
        check = Image.new('RGBA',(w,h),'#252931'); draw=ImageDraw.Draw(check)
        for y in range(0,h,16):
            for x in range(0,w,16):
                if (x//16+y//16)%2: draw.rectangle((x,y,x+15,y+15),fill='#343a44')
        check.alpha_composite(tile)
        if self.editor.selection is not None:
            from .core.painting import selection_outline
            mask = Image.fromarray(self.editor.selection.astype('uint8')*255).transform(
                (w,h), Image.Transform.AFFINE, (1/self.zoom,0,-self.ox/self.zoom,0,1/self.zoom,-self.oy/self.zoom),
                resample=Image.Resampling.NEAREST)
            check = selection_outline(check, np.asarray(mask)>0)
        self.photo = ImageTk.PhotoImage(check); c.delete('all'); c.create_image(0,0,anchor='nw',image=self.photo)

    def cancel(self):
        if self._render_job is not None: self.after_cancel(self._render_job)
        self.destroy()
        self.app.image_workshop = None
        self.app.paint_host.grid_remove()
        self.app.palette_panel.pack(before=self.app.progress, fill='x')
        self.app.after_idle(self.app.refresh_design_preview)

    def apply(self):
        try: cutoff = self.valid_int(self.cutoff,1,255,'Edge threshold')
        except ValueError as exc: self.status.set(str(exc)); return
        try:
            root = self.app.tempdir / uuid.uuid4().hex
            paths = [str(root)+suffix for suffix in ('_paint.png','_slots.png','_original.png')]
            for im,path in zip((self.editor.image,self.editor.slots,self.editor.original),paths): im.save(path)
        except OSError as exc: self.status.set(f'Could not save edits: {exc}'); return
        self.app._remember()
        self.layer.path,self.layer.paint_slots_path,self.layer.edit_source_path = paths
        self.layer.alpha_cutoff = cutoff
        self.layer.tint_color = ''; self.layer.filament_slot = None
        self.app.sync_inspector(); self.app.refresh_design_preview()
        self.app.status.set('Image edits applied. Undo on the card restores the previous image.')
        self.cancel()
