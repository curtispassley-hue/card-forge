"""Object controls and actual mesh previews in the shared desktop workspace."""
import copy
import math
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
import numpy as np
from .core.products import KINDS, validate_product, build_product, load_model, model_surfaces, choose_surface


def mesh_preview(parts, width, height, yaw=30, pitch=55, highlighted=None, face_down=False, background=None):
    """Software depth buffer: rear triangles never paint over nearer artwork."""
    from PIL import Image, ImageColor
    if not parts: return background.copy() if background is not None else Image.new('RGB',(width,height),'#dce4ed')
    ratio=min(1,800/width,600/height)
    rw,rh=max(100,round(width*ratio)),max(100,round(height*ratio))
    yaw,pitch=map(math.radians,(yaw,pitch))
    rz=np.array([[math.cos(yaw),-math.sin(yaw),0],[math.sin(yaw),math.cos(yaw),0],[0,0,1]])
    rx=np.array([[1,0,0],[0,math.cos(pitch),-math.sin(pitch)],[0,math.sin(pitch),math.cos(pitch)]])
    rotation=rx@rz@(np.diag([-1.,1.,-1.]) if face_down else np.eye(3))
    points=np.vstack([p['mesh'].vertices for p in parts]);center=(points.min(0)+points.max(0))/2
    projected=(points-center)@rotation.T
    bounds=np.array([projected.min(0),projected.max(0)])
    scale=min((rw-60*ratio)/max(1,bounds[1,0]-bounds[0,0]),(rh-60*ratio)/max(1,bounds[1,1]-bounds[0,1]))
    if background is None:
        pixels=np.empty((rh,rw,3),dtype='uint8');pixels[:]=ImageColor.getrgb('#dce4ed')
    else: pixels=np.asarray(background.resize((rw,rh),Image.Resampling.LANCZOS)).copy()
    depth=np.full((rh,rw),-np.inf)
    for part in parts:
        mesh=part['mesh'];xyz=(mesh.vertices-center)@rotation.T
        normals=mesh.face_normals@rotation.T
        rgb=np.array(ImageColor.getrgb(part['color'])[:3])
        # Viewer looks along -Z; a proper 180-degree rotation makes the
        # face-down manufacturing assembly readable from its artwork side.
        for index in np.flatnonzero(normals[:,2]>1e-9):
            tri=xyz[mesh.faces[index]].copy()
            tri[:,0]=rw/2+tri[:,0]*scale;tri[:,1]=rh/2-tri[:,1]*scale
            x0,y0=np.maximum(0,np.floor(tri[:,:2].min(0)).astype(int))
            x1,y1=np.minimum([rw-1,rh-1],np.ceil(tri[:,:2].max(0)).astype(int))
            if x1<x0 or y1<y0: continue
            a,b,c=tri
            denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator)<1e-10: continue
            xs=np.arange(x0,x1+1)[None,:]+.5;ys=np.arange(y0,y1+1)[:,None]+.5
            wa=((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/denominator
            wb=((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/denominator
            wc=1-wa-wb
            z=wa*a[2]+wb*b[2]+wc*c[2]
            old=depth[y0:y1+1,x0:x1+1]
            visible=(wa>=-1e-8)&(wb>=-1e-8)&(wc>=-1e-8)&(z>old)
            if not visible.any(): continue
            color=np.array(ImageColor.getrgb('#F4C430')) if highlighted is not None and index in highlighted else rgb
            shade=.65+.35*normals[index,2]
            pixels[y0:y1+1,x0:x1+1][visible]=np.clip(color*shade,0,255).astype('uint8')
            old[visible]=z[visible]
    return Image.fromarray(pixels).resize((width,height),Image.Resampling.LANCZOS)


def draw_meshes(canvas, parts, yaw=30, pitch=55, highlighted=None, face_down=False):
    from PIL import ImageTk
    canvas.delete('all')
    if not parts: return
    width,height=max(100,canvas.winfo_width()),max(100,canvas.winfo_height())
    from .theme import studio_backdrop, MUTED
    canvas.image_ref=ImageTk.PhotoImage(mesh_preview(parts,width,height,yaw,pitch,highlighted,face_down,studio_backdrop(width,height)))
    canvas.create_image(0,0,anchor='nw',image=canvas.image_ref)
    canvas.create_text(12,12,anchor='nw',text='Assembly preview • drag to rotate',fill=MUTED,font=('Segoe UI',10,'bold'))


class ProductControls:
    def export_allowed(self):
        from .licensing import license_status
        status=license_status(self.licensing_config)
        if status['active']: return True
        messagebox.showinfo('CardForge license',status['message']+'\n\nYour projects remain editable and can be saved.');self.license_dialog();return False

    def license_dialog(self):
        from .licensing import license_status,device_code,activate_license,deactivate_license
        win=tk.Toplevel(self);win.title('License & support');win.geometry('660x430');win.transient(self);win.grab_set()
        panel=ttk.Frame(win,padding=20);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='CardForge Studio',style='Title.TLabel').pack(anchor='w')
        status=tk.StringVar(value=license_status(self.licensing_config)['message'])
        ttk.Label(panel,textvariable=status,wraplength=600).pack(anchor='w',pady=16)
        ttk.Label(panel,text='Support: '+self.licensing_config['support_email'],style='Muted.TLabel').pack(anchor='w')
        ttk.Label(panel,text='Device code',style='Step.TLabel').pack(anchor='w',pady=(18,6))
        device=tk.StringVar(value=device_code());ttk.Entry(panel,textvariable=device,state='readonly',width=44).pack(anchor='w')
        def copy_code(): self.clipboard_clear();self.clipboard_append(device.get());status.set('Device code copied. Send it with your purchase details to request a license.')
        self._button(panel,'Copy device code',copy_code,'layers').pack(anchor='w',pady=6)
        if self.licensing_config['edition']=='commercial':
            def activate():
                path=filedialog.askopenfilename(parent=win,filetypes=[('CardForge license','*.json')])
                if not path: return
                try:
                    activate_license(path,self.licensing_config);status.set(license_status(self.licensing_config)['message'])
                except (ValueError,OSError) as exc: status.set(str(exc))
            self._button(panel,'Activate license file',activate,'check','Accent.TButton').pack(anchor='w',pady=6)
            def deactivate():
                if messagebox.askyesno('Deactivate this computer?','Remove the installed license from this computer? Your projects remain saved.',parent=win):
                    deactivate_license();status.set('License removed from this computer. Keep your purchased license file for recovery.')
            self._button(panel,'Deactivate on this computer',deactivate).pack(anchor='w')
        else:
            ttk.Label(panel,text='This release candidate has unrestricted exports for testing. Paid activation is enabled only in a publisher-configured commercial build.',wraplength=600,style='Muted.TLabel').pack(anchor='w',pady=12)
        self._button(panel,'Close',win.destroy,'back').pack(side='bottom',anchor='e')

    def object_settings(self):
        self.set_phase('setup')

    def save_lighting_profile(self,values,name):
        import json
        from pathlib import Path
        data={'format':'cardforge-lighting-1','name':name.get()}
        try:
            for (section,key),var in values.items():
                if key.startswith('led_') or key in ('depth_mm','cable_diameter_mm'): data[key]=float(var.get())
            if not np.isfinite([v for v in data.values() if isinstance(v,float)]).all(): raise ValueError('Use finite dimensions.')
        except ValueError as exc: messagebox.showerror('Lighting profile',str(exc));return
        path=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('Lighting profile','*.json')])
        if path: Path(path).write_text(json.dumps(data,indent=2),encoding='utf-8')

    def load_lighting_profile(self,values,name):
        import json
        from pathlib import Path
        path=filedialog.askopenfilename(filetypes=[('Lighting profile','*.json')])
        if not path: return
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            if data.get('format')!='cardforge-lighting-1': raise ValueError('Choose a CardForge lighting profile.')
            for (section,key),var in values.items():
                if key in data and (key.startswith('led_') or key in ('depth_mm','cable_diameter_mm')): var.set(float(data[key]))
            name.set(data.get('name','Custom dimensions — unverified'))
        except (ValueError,OSError) as exc: messagebox.showerror('Lighting profile',str(exc))

    def import_stl_target(self):
        if self.busy: return
        path=filedialog.askopenfilename(title='Choose a solid STL with a flat surface',filetypes=[('STL model','*.stl')])
        if not path: return
        def read():
            mesh=load_model(path);return mesh,model_surfaces(mesh)
        self._background('Reading flat surfaces…',read,
                         lambda result: self.surface_dialog(path,result[0],result[1]))

    def surface_dialog(self,path,mesh,surfaces):
        win=tk.Toplevel(self);win.title('Choose the artwork surface');win.geometry('980x700');win.transient(self);win.grab_set()
        panel=ttk.Frame(win,padding=16);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Place artwork on a flat surface',style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel,text='A separate panel will be aligned to this surface for attachment. Units and original model placement are preserved.',wraplength=900,style='Muted.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(panel);row.pack(fill='x')
        units=tk.StringVar(value='mm');selected=tk.IntVar(value=0)
        ttk.Label(row,text='STL units').pack(side='left',padx=(0,8))
        unit_choice=ttk.Combobox(row,textvariable=units,values=['mm','cm','inch'],state='readonly',width=8);unit_choice.pack(side='left')
        label=tk.StringVar();choice=ttk.Combobox(row,textvariable=label,state='readonly',width=60);choice.pack(side='right')
        canvas=tk.Canvas(panel,bg='#dce4ed',highlightthickness=0);canvas.pack(fill='both',expand=True,pady=12)
        error=tk.StringVar();ttk.Label(panel,textvariable=error,foreground='#b42318').pack(anchor='w')
        state={'mesh':mesh,'surfaces':surfaces,'yaw':30,'pitch':55}
        def draw(*_):
            index=max(0,choice.current());selected.set(index)
            if state['surfaces']: draw_meshes(canvas,[{'mesh':state['mesh'],'color':'#7790A6'}],state['yaw'],state['pitch'],set(state['surfaces'][index]['faces']))
        def populate():
            choice.configure(values=[f'{i+1}. {s["width"]:.1f} × {s["height"]:.1f} mm — normal {np.round(s["normal"],2).tolist()}' for i,s in enumerate(state['surfaces'])]);
            if state['surfaces']: choice.current(0);draw()
            else: error.set('No large flat surface at these units. Check the STL units; curved wrapping is not supported.')
        def change_units(*_):
            try:
                new=load_model(path,units.get()); found=model_surfaces(new)
                if not found: raise ValueError('No sufficiently large flat surface was found.')
                state['mesh'],state['surfaces']=new,found;populate();error.set('')
            except ValueError as exc: error.set(str(exc))
        unit_choice.bind('<<ComboboxSelected>>',change_units);choice.bind('<<ComboboxSelected>>',draw);canvas.bind('<Configure>',draw)
        def press(event): state['origin']=(event.x,event.y,state['yaw'],state['pitch'])
        def drag(event):
            x,y,yaw,pitch=state['origin'];state['yaw']=yaw+(event.x-x)*.5;state['pitch']=pitch+(event.y-y)*.5;draw()
        canvas.bind('<ButtonPress-1>',press);canvas.bind('<B1-Motion>',drag)
        footer=ttk.Frame(panel);footer.pack(fill='x')
        self._button(footer,'Cancel',win.destroy,'back').pack(side='left')
        def apply():
            candidate=copy.deepcopy(self.project)
            try: choose_surface(candidate,path,units.get(),selected.get());validate_product(candidate)
            except ValueError as exc: error.set(str(exc));return
            self._remember();self.project=candidate;self.project.name='STL artwork';self.selected=None;win.destroy()
            self.sync_ui_from_project();self.refresh_design_preview();self.status.set('Flat surface ready. Add artwork, then export the aligned panel and model.')
        self._button(footer,'Use this surface',apply,'check','Accent.TButton').pack(side='right')
        populate()

    def show_object_preview(self):
        if not self.editing_ready() or not self.commit_selected() or not self.commit_setup(): return
        if self.busy: return
        if self.object_preview_var.get():
            self.object_preview_var.set(False);self.refresh_design_preview();return
        self._sync_edits();snapshot=copy.deepcopy(self.project)
        def ready(result):
            self.object_preview_parts=result[0]
            if self.project.product.kind=='nfc_card':
                base=copy.deepcopy(result[1][0])
                base['mesh'].apply_transform(np.diag([-1.,1.,-1.,1.]))
                base['mesh'].apply_translation([2*self.project.geometry.card_width_mm+12,0,0]);self.object_preview_parts.append(base)
            self.object_preview_var.set(True);self.draw_object_preview()
        self._background('Building assembly preview…',lambda: build_product(snapshot),ready)

    def draw_object_preview(self):
        draw_meshes(self.design_canvas,self.object_preview_parts,self.object_yaw,self.object_pitch,face_down=self.project.product.kind!='stl_panel')

    def product_report(self):
        p=self.project.product;errors=[]
        try: validate_product(self.project)
        except ValueError as exc: errors.append(str(exc))
        text='CARDFORGE OBJECT CHECKS\n\n'+KINDS.get(p.kind,'Unknown object')+'\n\n'
        text+='Blocking issues:\n'+('\n'.join(errors) if errors else 'Dimension checks passed. Solids are validated during export.')
        from .core.colors import export_palette
        colors=export_palette(self.project)
        if p.body_color.upper() not in [c.upper() for c in colors]: colors.append(p.body_color)
        text+='\n\nConfigured filament colors: '+str(len(set(c.upper() for c in colors)))
        if len(set(c.upper() for c in colors))>4: text+=' — remap/share spools for a four-spool A1 setup. Separate body parts may be printed separately.'
        text+='\n\nInspect small artwork, filament count and every part in the slicer. Export includes separate print parts and an assembled model.'
        if p.kind=='lightbox': text+='\n\nUse translucent face/diffuser and opaque shell/back. Test fit coupons, wire clearance, light distribution and temperature with your lighting kit. Strip dimensions are editable; no specific kit is certified.'
        if p.kind=='stl_panel': text+='\n\nArtwork is a separate attached panel on a selected flat surface. Curved wrapping and carved inlays are not included.'
        if p.mounting=='desktop': text+='\n\nTest cradle fit and stability. Round outlines may require additional support.'
        self.check_text.delete('1.0',tk.END);self.check_text.insert('1.0',text)
