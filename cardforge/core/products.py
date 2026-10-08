"""Object-specific solid geometry around the shared artwork panel."""
from pathlib import Path
import copy
import json
import math
import numpy as np
import trimesh
from PIL import ImageColor
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from .geometry import face_target_dimensions, rounded_rect

KINDS = {'nfc_card': 'NFC card', 'wall_art': 'Wall art', 'lightbox': 'Lightbox', 'stl_panel': 'Imported STL panel'}


def panel_outline(project, fw, fh):
    p = project.product
    if p.kind == 'stl_panel' and p.surface_outline:
        return Polygon(p.surface_outline, p.surface_holes)
    if p.outline == 'ellipse':
        return affinity.scale(Point(fw/2, fh/2).buffer(1, quad_segs=96), fw/2, fh/2, origin=(fw/2,fh/2))
    return rounded_rect(fw, fh, max(.25, project.geometry.corner_radius_mm-project.geometry.face_border_mm-project.geometry.face_clearance_mm))


def validate_product(project):
    p,g,f = project.product,project.geometry,project.face
    if p.kind not in KINDS: raise ValueError('Choose a supported project type.')
    if p.kind == 'nfc_card': return
    numbers = [g.card_width_mm,g.card_height_mm,g.face_border_mm,g.face_clearance_mm,g.corner_radius_mm,
               f.thickness_mm,f.front_depth_mm,p.backing_mm,p.wall_mm,p.depth_mm,p.fit_mm,
               p.led_width_mm,p.led_thickness_mm,p.led_cut_mm,p.led_setback_mm,p.cable_diameter_mm,p.surface_gap_mm]
    if not np.isfinite(numbers).all(): raise ValueError('All object dimensions must be finite numbers.')
    if not 12 <= min(g.card_width_mm,g.card_height_mm) or max(g.card_width_mm,g.card_height_mm)>256:
        raise ValueError('Object width and height must be 12–256 mm. Oversized tiling is not supported.')
    if min(g.face_border_mm,g.face_clearance_mm,g.corner_radius_mm)<0: raise ValueError('Border, clearance and corner radius cannot be negative.')
    if not 0.2 <= f.front_depth_mm or f.thickness_mm-f.front_depth_mm < .2:
        raise ValueError('Use at least 0.2 mm of artwork and 0.2 mm of backing/diffuser.')
    if not 0.8 <= p.backing_mm <= 10 or not 0.8 <= p.wall_mm <= 10 or not .05 <= p.fit_mm <= 1:
        raise ValueError('Back and walls: 0.8–10 mm. Fit clearance: 0.05–1 mm.')
    if p.outline not in ('rectangle','ellipse'): raise ValueError('Choose rectangle or ellipse.')
    if p.mounting not in ('desktop','wall','none'): raise ValueError('Choose desktop, wall or no mounting.')
    for color in (p.body_color,p.diffuser_color,f.background_color):
        if not isinstance(color,str) or len(color)!=7 or not color.startswith("#"):
            raise ValueError("Object colors must use #RRGGBB format.")
        ImageColor.getrgb(color)
    fw,fh=face_target_dimensions(g)
    if min(fw,fh) < 10: raise ValueError('The border leaves too little space for artwork.')
    if p.kind == 'lightbox':
        if not np.isclose(g.face_border_mm,p.wall_mm) or not np.isclose(g.face_clearance_mm,p.fit_mm):
            raise ValueError('Lightbox border and clearance must match wall thickness and fit. Apply Object settings to synchronize them.')
        if not 12 <= p.depth_mm <= 100: raise ValueError('Lightbox depth must be 12–100 mm.')
        if not 1 <= p.led_width_mm <= 30 or not .2 <= p.led_thickness_mm <= 8 or not 1 <= p.led_cut_mm <= 500:
            raise ValueError('Check the LED strip width, thickness and cut interval.')
        if p.cable_side not in ('bottom','left','right'): raise ValueError('Choose a cable exit side.')
        if not 2 <= p.cable_diameter_mm <= 15: raise ValueError('Cable opening must be 2–15 mm.')
        if p.led_setback_mm < f.thickness_mm+p.wall_mm+1:
            raise ValueError('Move the LED strip farther behind the artwork and front support lip.')
        if p.led_setback_mm+p.led_width_mm > p.depth_mm-p.backing_mm-4:
            raise ValueError('The LED strip overlaps the rear lid. Increase body depth or reduce strip setback/width.')
        if min(fw,fh) < 2*(p.wall_mm+p.led_thickness_mm+4):
            raise ValueError('The lightbox is too small for these walls and LED dimensions.')
    if p.kind == 'stl_panel':
        if not 0 <= p.surface_gap_mm <= 1: raise ValueError('Attachment gap must be 0–1 mm.')
        if not p.model_path or not Path(p.model_path).is_file(): raise ValueError('Import an STL and select a flat surface first.')
        if not p.surface_outline or not p.surface_transform: raise ValueError('Select a supported flat surface.')
        poly = Polygon(p.surface_outline,p.surface_holes)
        if not poly.is_valid or poly.is_empty: raise ValueError('Selected surface outline is invalid.')


def _solid(mesh):
    if mesh is None or not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError('Object geometry failed the closed-solid check. Adjust its dimensions.')
    return mesh


def _union(meshes):
    return _solid(trimesh.boolean.union(meshes,engine='manifold'))


def _difference(mesh, cutters):
    return _solid(trimesh.boolean.difference([mesh,*cutters],engine='manifold')) if cutters else _solid(mesh)


def _part(name,color,mesh): return {'name':name,'color':color,'mesh':_solid(mesh)}


def build_product(project, include_artwork=True):
    """Return face-down aligned construction parts and separately printable accessories."""
    from .face import build_face, prism
    validate_product(project)
    p,g,f = project.product,project.geometry,project.face
    parts = build_face(project) if include_artwork else []
    if p.kind == 'nfc_card':
        from .geometry import build_nfc_base
        return parts, [_part('NFC base',p.body_color,build_nfc_base(g,project.nfc))]
    fw,fh=face_target_dimensions(g)
    face = affinity.scale(panel_outline(project,fw,fh),xfact=-1,yfact=1,origin=(fw/2,fh/2))
    outer = face.buffer(g.face_border_mm+g.face_clearance_mm,quad_segs=24)
    accessories=[]
    if p.kind == 'wall_art':
        back=outer
        if p.mounting == 'wall':
            holes=[]
            for fraction in (.3,.7):
                x,y=fw*fraction,fh*.7
                hole=Point(x,y).buffer(4).union(box(x-2,y,x+2,y+6))
                if not outer.buffer(-2).covers(hole): raise ValueError('Plaque is too small for the hanging holes.')
                holes.append(hole)
            back=back.difference(unary_union(holes))
        parts.append(_part('Plaque backing',p.body_color,prism(back,f.thickness_mm,f.thickness_mm+p.backing_mm)))
    elif p.kind == 'lightbox':
        # The separate panel mounts against a bed-supported front lip. This
        # avoids hiding an unsupported horizontal shelf inside the shell STL.
        for part in parts: part['mesh'].apply_translation([0,0,-f.thickness_mm])
        cavity=face.buffer(p.fit_mm)
        outer=cavity.buffer(p.wall_mm)
        if max(outer.bounds[2]-outer.bounds[0],outer.bounds[3]-outer.bounds[1])>256:
            raise ValueError('The lightbox walls exceed the 256 mm plate. Reduce panel size or walls.')
        opening=face.buffer(-max(1.2,p.wall_mm))
        if opening.is_empty: raise ValueError('No room remains for the illuminated opening.')
        shell=prism(outer.difference(cavity),0,p.depth_mm)
        lip=prism(outer.difference(opening),0,p.wall_mm)
        shell=_union([shell,lip])
        # Open rear cable notch avoids a support-dependent horizontal bore.
        radius=(p.cable_diameter_mm+1)/2
        if p.cable_side == 'bottom': notch=box(fw/2-radius,-20,fw/2+radius,p.wall_mm+radius)
        elif p.cable_side == 'left': notch=box(-20,fh/2-radius,p.wall_mm+radius,fh/2+radius)
        else: notch=box(fw-p.wall_mm-radius,fh/2-radius,fw+20,fh/2+radius)
        shell=_difference(shell,[prism(notch,p.depth_mm-p.backing_mm-p.cable_diameter_mm,p.depth_mm+1)])
        lid_shape=face.difference(notch)
        if p.mounting == 'wall':
            holes=[]
            for fraction in (.3,.7):
                hole=Point(fw*fraction,fh*.7).buffer(2.25)
                if not lid_shape.buffer(-3).covers(hole): raise ValueError('Back is too small for mounting holes.')
                holes.append(hole)
            lid_shape=lid_shape.difference(unary_union(holes))
        lid=prism(lid_shape,p.depth_mm-p.backing_mm,p.depth_mm)
        # Rear tongue enters the cavity with the configured per-side clearance.
        tongue=face.difference(face.buffer(-p.wall_mm)).difference(notch)
        lid=_union([lid,prism(tongue,p.depth_mm-p.backing_mm-3,p.depth_mm-p.backing_mm+.1)])
        parts.extend([_part('Lightbox shell',p.body_color,shell),_part('Removable back',p.body_color,lid)])
        coupon=box(0,0,30,20).difference(box(5,5,25,20))
        accessories.extend([_part('Fit coupon socket',p.body_color,prism(coupon,0,5)),
                            _part('Fit coupon insert',p.body_color,prism(box(0,0,20-2*p.fit_mm,10),0,5))])
    elif p.kind == 'stl_panel':
        mesh=load_model(p.model_path,p.model_units)
        # Rotate face-down artwork onto the outward normal of the selected face.
        transform=np.asarray(p.surface_transform,dtype=float)
        if transform.shape != (4,4) or not np.isfinite(transform).all(): raise ValueError('Invalid surface placement.')
        # Flip the face-down panel so its backing begins at the attachment gap.
        flip=np.eye(4);flip[0,0]=-1;flip[2,2]=-1;flip[0,3]=fw;flip[2,3]=f.thickness_mm+p.surface_gap_mm
        for part in parts: part['mesh'].apply_transform(transform@flip)
        if parts:
            panel=trimesh.util.concatenate([part['mesh'] for part in parts])
            overlap=trimesh.boolean.intersection([mesh,panel],engine='manifold')
            if overlap is not None and len(overlap.faces) and overlap.volume>max(1e-5,panel.volume*1e-6):
                raise ValueError('The attached panel intersects another part of this STL. Choose an unobstructed flat surface.')
        parts.insert(0,_part('Imported model',p.body_color,mesh))
    if p.mounting == 'desktop' and p.kind in ('wall_art','lightbox'):
        depth=p.depth_mm+f.thickness_mm if p.kind=='lightbox' else f.thickness_mm+p.backing_mm
        width=min(65,fw*.65); margin=12; rail=4; height=12
        base=prism(box(0,0,width,depth+2*margin+2*p.fit_mm),0,4)
        front=prism(box(0,margin-rail,width,margin),3.9,height)
        rear=prism(box(0,margin+depth+2*p.fit_mm,width,margin+depth+2*p.fit_mm+rail),3.9,height)
        accessories.append(_part('Desktop cradle',p.body_color,_union([base,front,rear])))
    for part in parts+accessories: _solid(part['mesh'])
    return parts,accessories


def load_model(path,units='mm'):
    scale={'mm':1.,'cm':10.,'inch':25.4}.get(units)
    if scale is None: raise ValueError('Choose millimeters, centimeters or inches for the STL.')
    mesh=trimesh.load_mesh(path,process=True)
    if not isinstance(mesh,trimesh.Trimesh): raise ValueError('Import one STL solid.')
    if len(mesh.faces)>250_000: raise ValueError('This STL has over 250,000 triangles. Simplify a copy before importing.')
    mesh.apply_scale(scale)
    _solid(mesh)
    if not np.isfinite(mesh.vertices).all() or max(mesh.extents)>256: raise ValueError('Imported model must fit within 256 mm per axis after selecting units.')
    return mesh


def model_surfaces(mesh):
    """Connected coplanar patches, preserving holes and arbitrary plane orientation."""
    surfaces=[]
    for faces,normal,area in zip(mesh.facets,mesh.facets_normal,mesh.facets_area):
        if area < 100: continue
        n=np.asarray(normal); helper=np.array([0.,0.,1.]) if abs(n[2])<.9 else np.array([0.,1.,0.])
        u=np.cross(helper,n);u/=np.linalg.norm(u);v=np.cross(n,u)
        origin=mesh.vertices[mesh.faces[faces[0]][0]]
        points=mesh.triangles[faces]-origin
        local=np.stack([points@u,points@v],axis=-1)
        polygon=unary_union([Polygon(tri) for tri in local])
        if polygon.geom_type!='Polygon' or not polygon.is_valid: continue
        x0,y0,x1,y1=polygon.bounds
        if min(x1-x0,y1-y0)<10: continue
        polygon=affinity.translate(polygon,-x0,-y0)
        matrix=np.eye(4);matrix[:3,:3]=np.column_stack([u,v,n]);matrix[:3,3]=origin+u*x0+v*y0
        surfaces.append({'area':float(area),'normal':n.tolist(),'width':x1-x0,'height':y1-y0,
                         'outline':list(polygon.exterior.coords),'holes':[list(r.coords) for r in polygon.interiors],
                         'transform':matrix.tolist(),'faces':faces.tolist()})
    return sorted(surfaces,key=lambda s:-s['area'])


def choose_surface(project,path,units,index):
    surfaces=model_surfaces(load_model(path,units))
    if not surfaces: raise ValueError('No sufficiently large connected flat surface was found. Curved wrapping is not supported.')
    if not 0 <= index < len(surfaces): raise ValueError('Select a listed flat surface.')
    s=surfaces[index];p=project.product;g=project.geometry
    old_w,old_h=g.card_width_mm,g.card_height_mm
    factor=min(s['width']/old_w,s['height']/old_h)
    for layer in [*project.texts,project.logo,*project.elements]:
        layer.x_mm=layer.x_mm/old_w*s['width'];layer.y_mm=layer.y_mm/old_h*s['height']
        if hasattr(layer,'width_mm'):
            layer.width_mm=max(.5,min(256,layer.width_mm*factor))
            if layer.height_mm is not None: layer.height_mm=max(.05,min(256,layer.height_mm*factor))
        elif hasattr(layer,'size_pt'): layer.size_pt=max(1,min(144,round(layer.size_pt*factor)))
    p.kind='stl_panel';p.model_path=str(path);p.model_units=units;p.surface_index=index
    p.surface_outline=s['outline'];p.surface_holes=s['holes'];p.surface_transform=s['transform']
    g.card_width_mm=s['width'];g.card_height_mm=s['height'];g.face_border_mm=g.face_clearance_mm=0
    g.face_recess_depth_mm=project.face.thickness_mm
    p.mounting='none'
    return s


def export_product(project,output,output_name=None,scope='complete'):
    from .face import export_face,export_3mf,_export_folder,_safe_stem
    from .colors import export_palette
    from .guides import write_assembly_guide
    if scope not in ('complete','artwork','structure'): raise ValueError('Choose complete object, artwork or body parts.')
    if scope=='artwork' or (project.product.kind=='nfc_card' and scope=='complete'):
        out=export_face(project,output,scope=='complete',output_name)
        write_assembly_guide(project,out,scope)
        return out
    parts,accessories=build_product(project,include_artwork=scope!='structure')
    if project.product.kind=='nfc_card': parts,accessories=accessories,[]
    out=_export_folder(output,'CardForge_Object',output_name);stem=_safe_stem(output_name,'CardForge')
    palette=export_palette(project)
    for color in (project.product.body_color,project.product.diffuser_color):
        if color.upper() not in [c.upper() for c in palette]: palette.append(color)
    export_3mf(parts,out/(stem+'_Assembly.3mf'),palette,project.name)
    aligned=out/'Assembly_STLs';aligned.mkdir()
    printable=out/'Print_Parts';printable.mkdir()
    info=[]
    for i,part in enumerate(parts,1):
        file=f'{i:02d}_'+_safe_stem(part['name'])+'.stl'
        part['mesh'].export(aligned/file)
        # Preserve alignment in Assembly_STLs; each independent print file sits at Z=0.
        if part['name'] in ('Lightbox shell','Removable back','Plaque backing','Imported model','NFC base'):
            m=part['mesh'].copy()
            if part['name']=='Removable back': m.apply_transform(trimesh.transformations.rotation_matrix(math.pi,[1,0,0]))
            m.apply_translation(-m.bounds[0]);m.export(printable/file)
        info.append({'name':part['name'],'color':part['color'],'assembly_stl':file,'volume_mm3':float(part['mesh'].volume)})
    # A standalone panel remains face-down even when the assembled STL target is tilted.
    if scope!='structure':
        from .face import build_face
        panel_project=copy.deepcopy(project)
        export_3mf(build_face(panel_project),printable/(stem+'_Artwork.3mf'),palette,'Artwork — print face-down')
    for part in accessories:
        m=part['mesh'].copy();m.apply_translation(-m.bounds[0]);file=_safe_stem(part['name'])+'.stl';m.export(printable/file)
        info.append({'name':part['name'],'color':part['color'],'print_stl':file,'volume_mm3':float(m.volume)})
    project.save_bundle(out/(stem+'.cardforge'))
    (out/'Parts.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    (out/'Export_scope.txt').write_text(scope+'\n',encoding='utf-8')
    write_assembly_guide(project,out,scope,info)
    return out
