"""Branded workspace: one preview, contextual setup/design/export controls."""
import copy
import math
from pathlib import Path
from dataclasses import asdict
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
from PIL import ImageTk
from . import theme
from .core.templates import TEMPLATES
from .core.project import TextLayer
from .core.fonts import bundled_fonts, default_font
from .core.colors import effective_palette


class StudioShell:
    def painting_active(self):
        return getattr(self, 'image_workshop', None) is not None and self.image_workshop.winfo_exists()

    def editing_ready(self):
        if self.painting_active():
            self.status.set('Choose Done painting to keep your image edits, or Cancel painting to discard them.')
            return False
        return not self.busy

    def build_workspace(self):
        self.phase = 'setup'; self.setup_values = {}; self.setup_combos = {}; self.setup_kind = None
        self.setup_error = tk.StringVar(); self.export_error = tk.StringVar()
        self.export_mode = tk.StringVar(value='Complete object')
        self.phase_caption = tk.StringVar()
        header=tk.Frame(self,bg=theme.BG,padx=18,pady=10);header.pack(fill='x')
        badge=tk.Canvas(header,width=52,height=54,bg=theme.BG,highlightthickness=0)
        badge.pack(side='left');theme.brand(badge)
        title=tk.Frame(header,bg=theme.BG);title.pack(side='left',padx=10)
        tk.Label(title,text='CARDFORGE',bg=theme.BG,fg=theme.TEXT,font=('Segoe UI',17,'bold')).pack(anchor='w')
        tk.Label(title,text='STUDIO  /  CREATE SOMETHING REAL',bg=theme.BG,fg=theme.MUTED,font=('Segoe UI',8)).pack(anchor='w')
        more=ttk.Menubutton(header,text='Menu',style='Secondary.TButton',menu=self.app_menu)
        more.pack(side='right',padx=(6,0))
        self._button(header,'Save project',self.save_project,'save').pack(side='right',padx=6)
        self._button(header,'Open',self.open_project,'folder').pack(side='right')
        phases=ttk.Frame(self,padding=(18,4,18,10));phases.pack(fill='x')
        self.phase_buttons={}
        for key,label in [('setup','1  Set up object'),('design','2  Design'),('export','3  Export')]:
            b=self._button(phases,label,lambda k=key:self.set_phase(k),style='Phase.TButton')
            b.pack(side='left',padx=(0,8));self.phase_buttons[key]=b
        self._button(phases,'Redo',self.redo,'redo').pack(side='right')
        self._button(phases,'Undo',self.undo,'undo').pack(side='right',padx=6)
        self.workspace=ttk.Frame(self,padding=(16,0,16,0));self.workspace.pack(fill='both',expand=True)
        self.workspace.columnconfigure(1,weight=1);self.workspace.rowconfigure(0,weight=1)
        self.left_shell=ttk.Frame(self.workspace,width=230);self.left_shell.grid(row=0,column=0,sticky='ns',padx=(0,12))
        self.left_shell.grid_propagate(False);self.left_shell.columnconfigure(0,weight=1);self.left_shell.rowconfigure(0,weight=1)
        self.left_panels={k:ttk.Frame(self.left_shell) for k in ('setup','design','export')}
        for p in self.left_panels.values():p.grid(row=0,column=0,sticky='nsew')
        self.right_shell=ttk.Frame(self.workspace,width=310);self.right_shell.grid(row=0,column=2,sticky='ns',padx=(12,0))
        self.right_shell.grid_propagate(False);self.right_shell.columnconfigure(0,weight=1);self.right_shell.rowconfigure(0,weight=1)
        self.right_panels={k:ttk.Frame(self.right_shell) for k in ('setup','design','export')}
        for p in self.right_panels.values():p.grid(row=0,column=0,sticky='nsew')
        self.build_template_panel(self.left_panels['setup'])
        layers=self.left_panels['design']
        ttk.Label(layers,text='ADD TO YOUR DESIGN',style='Step.TLabel').pack(anchor='w',pady=(8,10))
        self._button(layers,'Add image',self.load_elements,'image','Accent.TButton').pack(fill='x',pady=3)
        self._button(layers,'Add text',self.add_inline_text,'text').pack(fill='x',pady=3)
        self._button(layers,'Trace a photo / scan text',lambda:self.show_tool('photo'),'crop').pack(fill='x',pady=(3,12))
        ttk.Label(layers,text='ELEMENTS',style='Step.TLabel').pack(anchor='w',pady=8)
        self.layer_tree=ttk.Treeview(layers,show='tree',selectmode='browse');self.layer_tree.column('#0',width=210)
        self.layer_tree.pack(fill='both',expand=True);self.layer_tree.tag_configure('hidden',foreground='#727985')
        self.layer_tree.bind('<<TreeviewSelect>>',self._tree_selected)
        layer_footer=ttk.Frame(layers);layer_footer.pack(side='bottom',fill='x',before=self.layer_tree)
        row=ttk.Frame(layer_footer);row.pack(fill='x',pady=(8,4))
        self._button(row,'Duplicate',self.duplicate_selected,'layers').pack(side='left',expand=True,fill='x')
        self._button(row,'Delete',self.delete_selected,'delete','Danger.TButton').pack(side='right',padx=(4,0))
        row=ttk.Frame(layer_footer);row.pack(fill='x',pady=4)
        self._button(row,'Forward',lambda:self.reorder_selected(1),'up').pack(side='left',expand=True,fill='x')
        self._button(row,'Backward',lambda:self.reorder_selected(-1),'down').pack(side='right',expand=True,fill='x',padx=(4,0))
        ttk.Label(layer_footer,text='Top elements print in front.\nSelect one here or on the artwork.',style='Muted.TLabel').pack(anchor='w',pady=8)
        self._build_inspector(self.right_panels['design'])
        center=ttk.Frame(self.workspace);center.grid(row=0,column=1,sticky='nsew')
        top=ttk.Frame(center,padding=(10,8));top.pack(fill='x')
        ttk.Label(top,textvariable=self.document_var,font=('Segoe UI',11,'bold'),wraplength=210).pack(side='left')
        self._button(top,'Artwork / 3D',self.show_object_preview,'layers').pack(side='right')
        ttk.Checkbutton(top,text='Print colors',variable=self.print_view_var,command=self.refresh_design_preview).pack(side='right',padx=6)
        stage=ttk.Frame(center);stage.pack(fill='both',expand=True)
        self.design_canvas=tk.Canvas(stage,bg=theme.BG,highlightthickness=0)
        vertical=ttk.Scrollbar(stage,orient='vertical',command=self.design_canvas.yview);vertical.pack(side='right',fill='y')
        self.design_canvas.pack(fill='both',expand=True)
        horizontal=ttk.Scrollbar(center,orient='horizontal',command=self.design_canvas.xview);horizontal.pack(fill='x')
        self.design_canvas.configure(xscrollcommand=horizontal.set,yscrollcommand=vertical.set)
        for event,handler in [('<ButtonPress-1>',self.design_press),('<B1-Motion>',self.design_drag),('<ButtonRelease-1>',self.design_release),('<Configure>',self._schedule_canvas)]:self.design_canvas.bind(event,handler)
        self.design_canvas.bind('<ButtonPress-2>',lambda e:self.design_canvas.scan_mark(e.x,e.y))
        self.design_canvas.bind('<B2-Motion>',lambda e:self.design_canvas.scan_dragto(e.x,e.y,gain=1))
        self.design_canvas.bind('<Delete>',lambda e:self.delete_selected() if self.phase=='design' else None)
        for key,dx,dy in [('Left',-1,0),('Right',1,0),('Up',0,1),('Down',0,-1)]:
            self.design_canvas.bind('<'+key+'>',lambda e,x=dx,y=dy:self.nudge_selected(x,y,bool(e.state&1)) if self.phase=='design' else None)
        bottom=ttk.Frame(center,padding=(8,7));bottom.pack(fill='x')
        self.nfc_guide_control=ttk.Checkbutton(bottom,text='NFC guide',variable=self.show_nfc_var,command=self.refresh_design_preview)
        self.nfc_guide_control.pack(side='left')
        ttk.Label(bottom,text='Snap mm',style='Muted.TLabel').pack(side='left',padx=(6,4))
        ttk.Entry(bottom,textvariable=self.snap_var,width=5).pack(side='left')
        self._button(bottom,'Fit',self.fit_canvas,'search').pack(side='right')
        ttk.Scale(bottom,from_=.6,to=2.5,variable=self.zoom_var,command=self._schedule_canvas,length=90).pack(side='right',padx=6)
        self.canvas_hint=ttk.Label(center,textvariable=self.phase_caption,style='Muted.TLabel',wraplength=570)
        self.canvas_hint.pack(anchor='w',padx=8,pady=(0,7))
        # Painting replaces the workspace contents temporarily, within the same window.
        self.paint_host=ttk.Frame(self.workspace)
        palette=ttk.Frame(self,padding=(18,10));palette.pack(fill='x')
        ttk.Label(palette,text='ARTWORK COLORS',style='Step.TLabel').pack(side='left',padx=(0,10))
        self.color_buttons=[];self.filament_name_vars=[]
        for i in range(4):
            self.filament_name_vars.append(tk.StringVar())
            b=tk.Button(palette,width=8,relief='flat',bd=0,padx=5,pady=7,command=lambda n=i:self.pick_filament_color(n))
            b.pack(side='left',padx=(0,5));self.color_buttons.append(b)
        self.background_button=tk.Button(palette,text='Background',relief='flat',bd=0,padx=9,pady=7,command=self.pick_face_background)
        self.background_button.pack(side='left',padx=(10,8))
        self.mode_button=self._button(palette,'Grayscale',self.grayscale_palette);self.mode_button.pack(side='left')
        self._button(palette,'Reset colors',self.reset_filaments).pack(side='left',padx=6)
        ttk.Label(palette,text='Background is separate',style='Muted.TLabel').pack(side='right')
        self.palette_panel=palette
        self.progress=ttk.Progressbar(self,mode='indeterminate');self.progress.pack(fill='x',padx=18)
        ttk.Label(self,textvariable=self.status,padding=(18,6),style='Muted.TLabel').pack(fill='x')
        self.build_export_panel()

    def build_template_panel(self,panel):
        panel=self.scroll_context(panel)
        ttk.Label(panel,text='START WITH AN OBJECT',style='Step.TLabel').pack(anchor='w',pady=(8,10))
        self.template_images=[]
        for kind,label,name in [('nfc_card','NFC card','Blank card'),('wall_art','Wall art','Wall art'),('lightbox','Lightbox','Desktop lightbox'),('stl_panel','Artwork on an STL',None)]:
            image=ImageTk.PhotoImage(theme.template_art(kind, (170, 46)));self.template_images.append(image)
            b=ttk.Button(panel,text=label,image=image,compound='top',style='Secondary.TButton',
                         command=lambda n=name:self.choose_template(n))
            b.pack(fill='x',pady=4)
        ttk.Label(panel,text='A new object starts a new project. Save your design before switching.',wraplength=190,style='Muted.TLabel').pack(anchor='w',pady=10)
        menu_button=ttk.Menubutton(panel,text='More card templates',style='Secondary.TButton');menu=tk.Menu(menu_button,tearoff=False)
        for n in TEMPLATES:menu.add_command(label=n,command=lambda name=n:self.choose_template(name))
        menu_button.configure(menu=menu);menu_button.pack(fill='x')

    def choose_template(self,name):
        if not self.editing_ready():return
        if asdict(self.project)!=self._saved_data:
            answer=messagebox.askyesnocancel('Start a new object?','Save the current project before starting a new object?',parent=self)
            if answer is None or (answer and not self.save_project()):return
        if name:self.start_template(name)
        else:self.import_stl_target()

    def set_phase(self,phase,commit=True):
        if not self.editing_ready():return False
        if commit and (not self.commit_selected() or not self.commit_setup()):return False
        self.phase=phase
        for key,b in self.phase_buttons.items():b.configure(style='ActivePhase.TButton' if key==phase else 'Phase.TButton')
        self.left_panels[phase].tkraise();self.right_panels[phase].tkraise()
        self.phase_caption.set({'setup':'Set the object dimensions, then choose Design to add your artwork.',
                                'design':'Drag to move • Corner handles resize • Arrow keys nudge • Middle-drag pans',
                                'export':'Review the checks and choose where your print files will be saved.'}[phase])
        self.draw_editor_guides()
        if phase=='export':self.refresh_export_report()
        return True

    def scroll_context(self,parent):
        c=tk.Canvas(parent,bg=theme.PANEL,width=292,highlightthickness=0)
        bar=ttk.Scrollbar(parent,orient='vertical',command=c.yview);bar.pack(side='right',fill='y');c.pack(fill='both',expand=True)
        inner=ttk.Frame(c,padding=(10,8,12,14));item=c.create_window(0,0,window=inner,anchor='nw')
        c.configure(yscrollcommand=bar.set)
        inner.bind('<Configure>',lambda e:c.configure(scrollregion=c.bbox('all')))
        c.bind('<Configure>',lambda e:c.itemconfigure(item,width=e.width))
        def wheel(e):
            w=e.widget
            while w is not None:
                if w==parent:c.yview_scroll(-int(e.delta/120),'units');return
                w=getattr(w,'master',None)
        self.bind('<MouseWheel>',wheel,add='+')
        return inner

    def foldout(self,parent,title):
        frame=ttk.Frame(parent);frame.pack(fill='x',pady=(10,0))
        content=ttk.Frame(frame);opened=tk.BooleanVar(value=False)
        def toggle():
            opened.set(not opened.get());button.configure(text=('−  ' if opened.get() else '+  ')+title)
            if opened.get():content.pack(fill='x',pady=(6,0))
            else:content.pack_forget()
        button=self._button(frame,'+  '+title,toggle,'settings');button.pack(fill='x')
        return content

    def build_setup_panel(self):
        from .core.products import KINDS
        panel=self.right_panels['setup']
        if not hasattr(self,'setup_form'):self.setup_form=self.scroll_context(panel)
        for w in self.setup_form.winfo_children():w.destroy()
        self.setup_values={};self.setup_combos={};p=self.project;kind=p.product.kind;self.setup_kind=kind
        form=self.setup_form
        ttk.Label(form,text='OBJECT SETTINGS',style='Step.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(form,text=KINDS[kind],style='Title.TLabel').pack(anchor='w',pady=(0,6))
        ttk.Label(form,text='Dimensions in millimeters',style='Muted.TLabel').pack(anchor='w',pady=(0,12))
        def field(parent,label,section,key):
            var=tk.StringVar(value=str(getattr(getattr(p,section),key)));self.setup_values[section,key]=var
            self._field(parent,label,var)
        if kind!='stl_panel':
            field(form,'Width','geometry','card_width_mm');field(form,'Height','geometry','card_height_mm')
            field(form,'Corner radius','geometry','corner_radius_mm')
        field(form,'Panel thickness','face','thickness_mm');field(form,'Front color depth','face','front_depth_mm')
        def combo(parent,label,key,choices):
            ttk.Label(parent,text=label,style='Muted.TLabel').pack(anchor='w',pady=(9,3))
            var=tk.StringVar(value=getattr(p.product,key));self.setup_combos[key]=var
            ttk.Combobox(parent,textvariable=var,values=choices,state='readonly').pack(fill='x')
        if kind in ('wall_art','lightbox'):
            combo(form,'Shape','outline',['rectangle','ellipse']);combo(form,'Mounting','mounting',['desktop','wall','none'])
        if kind=='lightbox':field(form,'Body depth','product','depth_mm')
        advanced=self.foldout(form,'Fit & construction')
        if kind=='nfc_card':
            for label,key in [('Base thickness','base_thickness_mm'),('Face recess','face_recess_depth_mm'),('Border','face_border_mm'),('Fit per side','face_clearance_mm')]:field(advanced,label,'geometry',key)
            nfc=self.foldout(form,'NFC pocket')
            for label,key in [('Tag diameter','diameter_mm'),('Tag thickness','thickness_mm'),('Clearance','clearance_mm'),('Center X','x_mm'),('Center Y','y_mm')]:field(nfc,label,'nfc',key)
            ttk.Label(nfc,text='Measure the actual tag before printing.',wraplength=260,style='Muted.TLabel').pack(anchor='w',pady=8)
        elif kind=='stl_panel':
            field(advanced,'Attachment gap','product','surface_gap_mm')
            self._button(form,'Choose another STL surface',self.import_stl_target,'folder').pack(fill='x',pady=8)
        else:
            if kind=='wall_art':field(advanced,'Border','geometry','face_border_mm')
            for label,key in [('Back thickness','backing_mm'),('Wall thickness','wall_mm'),('Fit per side','fit_mm')]:field(advanced,label,'product',key)
            def color(key):
                if not self.commit_setup():return
                chosen=colorchooser.askcolor(initialcolor=getattr(self.project.product,key),parent=self)[1]
                if chosen:self._remember();setattr(self.project.product,key,chosen.upper());self.object_preview_parts=[];self.refresh_design_preview()
            self._button(advanced,'Body / stand color',lambda:color('body_color'),'layers').pack(fill='x',pady=5)
            if kind=='lightbox':
                self._button(advanced,'Diffuser color',lambda:color('diffuser_color'),'layers').pack(fill='x',pady=5)
                light=self.foldout(form,'Lighting dimensions')
                for label,key in [('Strip width','led_width_mm'),('Strip thickness','led_thickness_mm'),('Cut interval','led_cut_mm'),('Front setback','led_setback_mm'),('Cable diameter','cable_diameter_mm')]:field(light,label,'product',key)
                combo(light,'Cable exit','cable_side',['bottom','left','right'])
                self.lighting_profile_var=tk.StringVar(value=p.product.lighting_name)
                ttk.Label(light,text='Lighting profile',style='Muted.TLabel').pack(anchor='w',pady=(8,3))
                ttk.Entry(light,textvariable=self.lighting_profile_var).pack(fill='x')
                self._button(light,'Save profile',lambda:self.save_lighting_profile(self.setup_values,self.lighting_profile_var),'save').pack(fill='x',pady=4)
                self._button(light,'Load profile',lambda:self.load_lighting_profile(self.setup_values,self.lighting_profile_var),'folder').pack(fill='x',pady=4)
                ttk.Label(light,text='Measure your LED strip and connector. Print the fit coupons before a complete box.',wraplength=260,style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Label(form,textvariable=self.setup_error,foreground='#ffb4b4',wraplength=260).pack(anchor='w',pady=8)
        self._button(form,'Apply settings',self.commit_setup,'check').pack(fill='x',pady=4)
        self._button(form,'Design this object',lambda:self.set_phase('design'),'next','Accent.TButton').pack(fill='x',pady=4)
        self.setup_baseline=self.setup_state()

    def setup_state(self):
        return ({k:v.get() for k,v in self.setup_values.items()},{k:v.get() for k,v in self.setup_combos.items()},
                self.lighting_profile_var.get() if self.project.product.kind=='lightbox' else '')

    def sync_setup_fields(self):
        if self.setup_kind!=self.project.product.kind:self.build_setup_panel()
        for (section,key),v in self.setup_values.items():v.set(str(getattr(getattr(self.project,section),key)))
        for key,v in self.setup_combos.items():v.set(getattr(self.project.product,key))
        if self.project.product.kind=='lightbox':self.lighting_profile_var.set(self.project.product.lighting_name)
        self.setup_baseline=self.setup_state();self.setup_error.set('')
        if self.project.product.kind=='nfc_card':self.nfc_guide_control.pack(side='left',before=self.nfc_guide_control.master.winfo_children()[1])
        else:self.nfc_guide_control.pack_forget()

    def commit_setup(self):
        if not self.setup_values or self.setup_state()==self.setup_baseline:return True
        from .core.products import validate_product
        from .core.geometry import validate_geometry
        candidate=copy.deepcopy(self.project)
        try:
            for (section,key),v in self.setup_values.items():
                value=float(v.get())
                if not math.isfinite(value):raise ValueError('Enter finite dimensions.')
                setattr(getattr(candidate,section),key,value)
            for key,v in self.setup_combos.items():setattr(candidate.product,key,v.get())
            if candidate.product.kind=='lightbox':
                candidate.product.lighting_name=self.lighting_profile_var.get().strip() or 'Custom dimensions — unverified'
                candidate.geometry.face_border_mm=candidate.product.wall_mm;candidate.geometry.face_clearance_mm=candidate.product.fit_mm
            validate_product(candidate)
            if candidate.product.kind=='nfc_card':
                validate_geometry(candidate.geometry,candidate.nfc)
                if not .2<=candidate.face.front_depth_mm<=candidate.face.thickness_mm-.2:raise ValueError('Keep at least 0.2 mm of front color and 0.2 mm of backing.')
                if max(candidate.geometry.card_width_mm,candidate.geometry.card_height_mm)>256:raise ValueError('Object exceeds the 256 mm A1 plate.')
        except (ValueError,tk.TclError) as exc:self.setup_error.set(str(exc));return False
        self._remember();self.project=candidate;self.sync_ui_from_project();self.refresh_design_preview();return True

    def build_export_panel(self):
        left=self.left_panels['export']
        ttk.Label(left,text='BEFORE YOU PRINT',style='Step.TLabel').pack(anchor='w',pady=(8,10))
        ttk.Label(left,text='Open the 3MF as a model in Bambu Studio. Assign filament colors to the named parts, then inspect every layer.',wraplength=216,style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Label(left,text='Artwork prints face-down.\nFront and back stay flat.\nColor geometry is in the front layers.',wraplength=216).pack(anchor='w',pady=12)
        self._button(left,'Full printability report',lambda:self.show_tool('checks'),'check').pack(fill='x',pady=6)
        ttk.Label(left,text='Physical fit and lighting depend on your printer, material and hardware. Start with a test print.',wraplength=216,style='Muted.TLabel').pack(anchor='w',pady=12)
        panel=self.scroll_context(self.right_panels['export'])
        ttk.Label(panel,text='EXPORT YOUR DESIGN',style='Step.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Label(panel,text='Ready for the printer',font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(0,10))
        ttk.Label(panel,text='Package name',style='Muted.TLabel').pack(anchor='w',pady=3)
        ttk.Entry(panel,textvariable=self.output_name_var).pack(fill='x')
        ttk.Label(panel,text='Destination folder',style='Muted.TLabel').pack(anchor='w',pady=(10,3))
        ttk.Entry(panel,textvariable=self.output_dir_var).pack(fill='x')
        self._button(panel,'Choose folder',self.browse_output_folder,'folder').pack(fill='x',pady=5)
        ttk.Label(panel,text='Package',style='Muted.TLabel').pack(anchor='w',pady=(8,3))
        ttk.Combobox(panel,textvariable=self.export_mode,values=['Complete object','Artwork panel only','Body / base parts only','Images only'],state='readonly').pack(fill='x')
        self.export_mode.trace_add('write',lambda *_:self.refresh_export_report())
        self.export_summary=tk.StringVar();ttk.Label(panel,textvariable=self.export_summary,wraplength=264,style='Muted.TLabel').pack(anchor='w',pady=12)
        self.export_checks=tk.StringVar();ttk.Label(panel,textvariable=self.export_checks,wraplength=264).pack(anchor='w',pady=8)
        self._button(panel,'Review checks',lambda:self.show_tool('checks'),'check').pack(fill='x',pady=4)
        ttk.Label(panel,textvariable=self.export_error,foreground='#ffb4b4',wraplength=264).pack(anchor='w',pady=8)
        self.export_button=self._button(panel,'Export files',self.begin_export,'download','Accent.TButton');self.export_button.pack(fill='x',pady=4)
        self.export_completion=tk.StringVar()
        ttk.Label(panel,textvariable=self.export_completion,wraplength=264,style='Muted.TLabel').pack(anchor='w',pady=6)
        self.export_result_actions=ttk.Frame(panel)
        self._button(self.export_result_actions,'Open output folder',lambda:self.open_export_file(False),'folder').pack(fill='x',pady=3)
        self._button(self.export_result_actions,'Open assembly guide',lambda:self.open_export_file(True),'card').pack(fill='x',pady=3)
        ttk.Label(panel,text='A new named folder keeps your files together. Existing packages receive a numbered suffix.',wraplength=264,style='Muted.TLabel').pack(anchor='w',pady=8)

    def refresh_export_report(self):
        if not hasattr(self,'export_summary'):return
        mode=self.export_mode.get()
        self.export_summary.set({'Complete object':'Includes the assembled 3MF, printable parts, aligned artwork STLs and print / assembly guide.',
            'Artwork panel only':'Includes a multipart artwork 3MF, aligned color STLs, part names and print guide.',
            'Body / base parts only':'Includes the base or shell, back and accessories. No artwork geometry is generated. Print files and the illustrated assembly guide are included.',
            'Images only':'Includes separate image geometry in a multipart 3MF and aligned STL parts.'}[mode])
        colors=set(c.upper() for c in effective_palette(self.project));colors.add(self.project.face.background_color.upper())
        checks=''
        if hasattr(self,'check_text'):
            self.run_checks()
            report=self.check_text.get('1.0','end')
            marker='BLOCKING ISSUES\n' if self.project.product.kind=='nfc_card' else 'Blocking issues:\n'
            if marker in report: checks=report.split(marker,1)[1].split('\n\n',1)[0].strip()
        self.export_checks.set(checks+'\n\n'+f'{len(colors)} configured artwork / background colors.\n'+('A1 AMS Lite holds 4 spools: share a background color or plan a spool change.\n' if len(colors)>4 else '')+'Review the report and sliced layers before printing.')

    def show_export(self,mode):
        if self.set_phase('export'):
            self.export_mode.set(mode);self.export_error.set('')

    def begin_export(self):
        if not self.editing_ready() or not self.commit_selected() or not self.commit_setup():return
        if not self.export_allowed():return
        from .core.face import _safe_stem, export_face, export_logo
        from .core.products import export_product
        name=self.output_name_var.get().strip();folder=self.output_dir_var.get().strip()
        if not name:self.export_error.set('Enter a package name.');return
        if not folder or not Path(folder).expanduser().is_dir():self.export_error.set('Choose an existing destination folder.');return
        mode=self.export_mode.get()
        if mode=='Images only' and not any(e.path and e.enabled for e in [self.project.logo,*self.project.elements]):self.export_error.set('Add an image to export image geometry.');return
        self._sync_edits();snapshot=copy.deepcopy(self.project);name=_safe_stem(name);self.output_name_var.set(name)
        out=str(Path(folder).expanduser());self.output_dir_var.set(out);self.export_error.set('')
        def job():
            if mode=='Images only':return export_logo(snapshot,out,output_name=name)
            scope={'Complete object':'complete','Artwork panel only':'artwork','Body / base parts only':'structure'}[mode]
            return export_product(snapshot,out,output_name=name,scope=scope)
        def ready(result):
            self.status.set(f'Print files saved in {result}')
            self.last_export=Path(result)
            self.export_completion.set(f'Files ready: {result}\nYou can edit or export another package now.')
            self.export_result_actions.pack(fill='x',pady=8)
        self.export_completion.set('');self.export_result_actions.pack_forget()
        self._background('Building your print package…',job,ready,failed=lambda message:self.export_error.set(message))

    def open_export_file(self, guide=False):
        import os
        folder=getattr(self,'last_export',None)
        if folder is None:return
        file=folder/'ASSEMBLY_GUIDE.html' if guide else folder
        if guide and not file.exists():file=next(iter(folder.glob('*README.txt')),folder)
        try:os.startfile(str(file))
        except OSError as exc:self.export_error.set(str(exc))

    def add_inline_text(self):
        if not self.set_phase('design'):return
        self._remember();g=self.project.geometry
        self.project.texts.append(TextLayer('Your text',g.card_width_mm/2,g.card_height_mm/2,10,default_font()))
        self.select_layer('text',len(self.project.texts)-1);self.refresh_design_preview()

    def build_inline_text(self):
        p=self.text_inspector
        ttk.Label(p,text='TEXT & FONT',style='Step.TLabel').pack(anchor='w',pady=(10,8))
        self.font_choices=bundled_fonts()
        self.inspector_vars['font']=tk.StringVar();self.inspector_vars['size']=tk.StringVar()
        ttk.Label(p,text=f'Font · {len(self.font_choices)} included',style='Muted.TLabel').pack(anchor='w',pady=4)
        self.font_picker=ttk.Combobox(p,textvariable=self.inspector_vars['font'],values=list(self.font_choices),state='readonly')
        self.font_picker.pack(fill='x');self.font_picker.bind('<<ComboboxSelected>>',lambda e:self.commit_selected('font'))
        self._button(p,'Use a font file',self.browse_inline_font,'folder').pack(fill='x',pady=5)
        self._inspect_field(p,'Size · points','size')
        ttk.Label(p,text='Filament color',style='Muted.TLabel').pack(anchor='w',pady=(10,4))
        row=ttk.Frame(p);row.pack(fill='x');self.text_color_buttons=[]
        for i in range(4):
            b=tk.Button(row,text=str(i+1),width=4,relief='flat',command=lambda n=i:self.color_inline_text(n))
            b.pack(side='left',padx=4,pady=5);self.text_color_buttons.append(b)
        self._button(p,'Center on object',self.center_selected,'center').pack(fill='x',pady=6)
        ttk.Label(p,text='Edit the text above. Press Enter or leave a field to apply changes.',wraplength=260,style='Muted.TLabel').pack(anchor='w',pady=8)

    def browse_inline_font(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(filetypes=[('Fonts','*.ttf *.otf')])
        if path:
            self.font_choices[Path(path).stem]=path;self.font_picker.configure(values=list(self.font_choices))
            self.inspector_vars['font'].set(Path(path).stem);self.commit_selected('font')

    def color_inline_text(self,slot):
        if not self.commit_selected():return
        layer=self.selected_layer()
        if layer is None or self.selected[0]!='text':return
        if layer.filament_slot!=slot:
            self._remember();layer.filament_slot=slot;layer.color=effective_palette(self.project)[slot];self.refresh_design_preview()
