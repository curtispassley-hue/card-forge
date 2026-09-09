"""Flush, disjoint front inlays and a continuous back, printed artwork-side down."""
from pathlib import Path
import json
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
from shapely import affinity, constrained_delaunay_triangles
from .geometry import rounded_rect, face_target_dimensions, export_base_stl
from .image_processing import fit_card_image, hex_to_rgb
from .fonts import default_font
import trimesh


def prism(poly, z0, z1, _retry=False):
    """Constrained caps preserve concave outlines and letter counters exactly."""
    meshes = []
    for geom in getattr(poly, 'geoms', [poly]):
        if not isinstance(geom, Polygon) or geom.is_empty or geom.area < 1e-9:
            continue
        verts, faces, lookup = [], [], {}
        def v(x, y, z):
            key = (round(x, 8), round(y, 8), round(z, 8))
            if key not in lookup:
                lookup[key] = len(verts)
                verts.append(key)
            return lookup[key]
        for tri in constrained_delaunay_triangles(geom).geoms:
            c = list(tri.exterior.coords)[:3]
            faces.append([v(x, y, z0) for x, y in c])
            faces.append([v(x, y, z1) for x, y in c])
        for ring in [geom.exterior, *geom.interiors]:
            for (x, y), (xx, yy) in zip(ring.coords[:-1], ring.coords[1:]):
                a,b,c,d = v(x,y,z0),v(xx,yy,z0),v(xx,yy,z1),v(x,y,z1)
                faces.extend([[a,b,c],[a,c,d]])
        mesh = trimesh.Trimesh(verts, faces, process=True)
        mesh.fix_normals()
        if not mesh.is_watertight or not mesh.is_winding_consistent:
            # Raster logos can leave a one-pixel zig-zag around a counter or
            # a retraced collinear edge.  Shapely keeps that outline valid,
            # but the triangulated cap can then contain one four-way edge.
            # Remove only that sub-pixel noise and retry; this keeps the
            # intended letter/logo silhouette while producing a closed STL.
            if not _retry:
                # Most cases are fixed by the first tolerance; the larger
                # fallbacks handle a heavily antialiased logo without making
                # the normal text path coarser.
                for tolerance in (0.05, 0.08, 0.12):
                    cleaned = geom.simplify(tolerance, preserve_topology=True)
                    if not isinstance(cleaned, Polygon) or cleaned.is_empty or cleaned.area <= 1e-9:
                        continue
                    if cleaned.equals_exact(geom, 1e-9):
                        continue
                    try:
                        retry = prism(cleaned, z0, z1, _retry=True)
                    except ValueError:
                        continue
                    if retry is not None and retry.is_watertight and retry.is_winding_consistent:
                        meshes.append(retry)
                        break
                else:
                    raise ValueError('A face outline could not form a closed solid. Try a simpler logo or larger text.')
                continue
            raise ValueError('A face outline could not form a closed solid. Try a simpler logo or larger text.')
        meshes.append(mesh)
    return trimesh.util.concatenate(meshes) if meshes else None


def mask_polygon(mask, fw, fh):
    """Union pixel runs, retaining holes and complementary boundaries."""
    mask = np.asarray(mask, dtype=bool)
    h,w = mask.shape
    runs = []
    # Merge equal runs vertically before union to keep flat regions inexpensive.
    active = {}
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        current = set(zip(edges[::2], edges[1::2]))
        for key in list(active):
            if key not in current:
                start = active.pop(key)
                runs.append(box(key[0]*fw/w, (h-y)*fh/h, key[1]*fw/w, (h-start)*fh/h))
        for key in current:
            active.setdefault(key, y)
    for key, start in active.items():
        runs.append(box(key[0]*fw/w, 0, key[1]*fw/w, (h-start)*fh/h))
    if not runs:
        return Polygon()
    # Simplify each region once before computing the complementary background.
    return unary_union(runs).simplify(min(fw/w, fh/h)*0.25, preserve_topology=True)


def build_face(project):
    g, settings = project.geometry, project.face
    total, depth = float(settings.thickness_mm), float(settings.front_depth_mm)
    if not np.isfinite([total, depth]).all() or depth < 0.2 or total-depth < 0.2:
        raise ValueError('Use at least 0.2 mm of front color and 0.2 mm of solid backing.')
    if total > g.face_recess_depth_mm + 0.001:
        raise ValueError('Face thickness exceeds the recess depth. Increase the recess or reduce face thickness.')
    fw, fh = face_target_dimensions(g)
    if min(fw,fh) <= 0 or max(g.card_width_mm,g.card_height_mm)>256:
        raise ValueError('Face dimensions must fit the Bambu A1 plate.')
    ppm = 12.0  # 0.083 mm sampling, finer than a standard 0.4 mm nozzle.
    w,h = max(1,round(fw*ppm)),max(1,round(fh*ppm))
    sx,sy = w/fw,h/fh
    inset = g.face_border_mm + g.face_clearance_mm
    footprint = rounded_rect(fw,fh,max(0.25,g.corner_radius_mm-inset))
    masks = []
    for i, layer in enumerate(project.texts):
        if not layer.enabled or not layer.text.strip():
            continue
        mask = Image.new('L',(w,h))
        font = ImageFont.truetype(layer.font_path or default_font(), max(1,round(layer.size_pt*25.4/72*sx)))
        ImageDraw.Draw(mask).text(((layer.x_mm-inset)*sx, (fh-layer.y_mm+inset)*sy),
                                 layer.text,font=font,fill=255,anchor='mm')
        masks.append((f'Text {i+1} - {layer.text[:32]}', layer.color, np.array(mask)>=128))
    logo = project.logo
    if logo.enabled and logo.path:
        with Image.open(logo.path) as raw:
            im=raw.convert('RGBA')
        width=max(1,round(logo.width_mm*sx))
        height=max(1,round(im.height*width/im.width))
        if width*height > 20_000_000:
            raise ValueError('Logo size is too large.')
        im=im.resize((width,height),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(w,h))
        canvas.alpha_composite(im,(round((logo.x_mm-inset)*sx-width/2),round((fh-logo.y_mm+inset)*sy-height/2)))
        pixels=np.array(canvas)
        alpha=pixels[:,:,3].astype(float)*logo.opacity/255>=128
        pal=np.array([hex_to_rgb(c) for c in project.hueforge.palette],dtype=np.int32)
        indices=np.zeros((h,w),dtype=np.uint8)
        for start in range(0,h,64):
            diff=pixels[start:start+64,:,:3].astype(np.int32)[:,:,None,:]-pal
            indices[start:start+64]=np.argmin((diff*diff).sum(axis=3),axis=2)
        for i,color in enumerate(project.hueforge.palette):
            masks.append((f'Logo - color {i+1}',color,alpha & (indices==i)))
    covered=Polygon()
    regions=[]
    # Logo is above text, later text is above earlier text, matching the editor.
    for name,color,mask in reversed(masks):
        region=mask_polygon(mask,fw,fh).intersection(footprint).difference(covered)
        if region.is_empty:
            continue
        covered=covered.union(region)
        regions.append((name,color,region))
    regions.reverse()
    regions.insert(0,('Background',settings.background_color,footprint.difference(covered)))
    parts=[]
    for name,color,poly in regions:
        # Mirror X: artwork becomes readable when the bed-side face is turned over.
        poly=affinity.scale(poly,xfact=-1,yfact=1,origin=(fw/2,fh/2))
        mesh=prism(poly,0,depth)
        if mesh is not None:
            parts.append({'name':name,'color':color,'mesh':mesh,'polygon':poly,'z0':0,'z1':depth})
    parts.append({'name':'Solid backing','color':settings.background_color,
                  'mesh':prism(footprint,depth,total),'polygon':footprint,'z0':depth,'z1':total})
    expected=footprint.area*total
    # A raster edge can be simplified by a few hundredths of a millimeter
    # when repairing a retraced pixel boundary.  Keep the check strict enough
    # to catch missing regions while allowing that bounded repair tolerance.
    if not np.isclose(sum(x['mesh'].volume for x in parts), expected, rtol=2e-5, atol=0.05):
        raise ValueError('Face solids failed the volume check.')
    return parts


def export_3mf(parts, path, palette=None, assembly_name='CardForge flush face'):
    ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    ET.register_namespace('',ns)
    def tag(n): return '{'+ns+'}'+n
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    ET.SubElement(model,tag('metadata'),{'name':'Application'}).text='CardForge 4D'
    resources=ET.SubElement(model,tag('resources'))
    # Map the four user-selected colors to Bambu's filament slots.  A part
    # index is not a filament index: a face can contain many text/logo parts
    # that intentionally share one of the four colors.
    slot_by_color = {str(c).upper(): i + 1 for i, c in enumerate(palette or [])}
    for i,part in enumerate(parts,1):
        obj=ET.SubElement(resources,tag('object'),{'id':str(i),'type':'model','name':part['name']})
        mesh=ET.SubElement(obj,tag('mesh'))
        vs=ET.SubElement(mesh,tag('vertices'))
        for xyz in part['mesh'].vertices:
            ET.SubElement(vs,tag('vertex'),dict(zip(('x','y','z'),[format(v,'.9g') for v in xyz])))
        ts=ET.SubElement(mesh,tag('triangles'))
        for tri in part['mesh'].faces:
            ET.SubElement(ts,tag('triangle'),dict(zip(('v1','v2','v3'),map(str,tri))))
    rootid=len(parts)+1
    root=ET.SubElement(resources,tag('object'),{'id':str(rootid),'type':'model','name':assembly_name})
    components=ET.SubElement(root,tag('components'))
    for i in range(1,rootid):
        ET.SubElement(components,tag('component'),{'objectid':str(i)})
    ET.SubElement(ET.SubElement(model,tag('build')),tag('item'),{'objectid':str(rootid)})
    config=ET.Element('config')
    obj=ET.SubElement(config,'object',{'id':str(rootid)})
    ET.SubElement(obj,'metadata',{'key':'name','value':assembly_name})
    for i,part in enumerate(parts,1):
        node=ET.SubElement(obj,'part',{'id':str(i),'subtype':'normal_part'})
        ET.SubElement(node,'metadata',{'key':'name','value':part['name']})
        ET.SubElement(node,'metadata',{'key':'extruder','value':str(slot_by_color.get(str(part['color']).upper(), 1))})
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Default Extension="config" ContentType="application/xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
        z.writestr('Metadata/model_settings.config',ET.tostring(config,encoding='utf-8',xml_declaration=True))


def export_face(project, output, include_base=False):
    parts=build_face(project)
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    export_3mf(parts,out/'CardForge_Face.3mf', project.hueforge.palette)
    stls=out/'Aligned_STLs'
    stls.mkdir(exist_ok=True)
    info=[]
    import re
    for i,part in enumerate(parts,1):
        name=f'{i:02d}_'+re.sub(r'[^A-Za-z0-9_-]+','_',part['name'])+'.stl'
        part['mesh'].export(stls/name)
        info.append({'part':part['name'],'suggested_color':part['color'],'stl':name})
    if include_base:
        export_base_stl(out/'CardForge_NFC_Base.stl',project.geometry,project.nfc)
    project.save_bundle(out/'CardForge_Project.cardforge')
    (out/'Parts.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    (out/'PRINT_README.txt').write_text('''CARDFORGE FLUSH FACE
Open CardForge_Face.3mf as a model in Bambu Studio. The face is one assembly with named parts. Assign filaments in Objects/Parts. If using STLs, select ALL Aligned_STLs files together and answer Yes to loading as a single object with multiple parts. Do not auto-arrange individual parts or drop the backing to the bed.

The model is already artwork-side down and mirrored correctly. Do not mirror or flip it again. Both exterior faces are flat. Text/logo occupy only the first front layers; Solid backing starts above them. Use a layer height and first layer that divide the front depth (default: two 0.2 mm front layers and two 0.2 mm backing layers). Assign the background and backing the same filament if desired.

Photos are layout references. Only editable text and the extracted/replacement logo become inlay geometry. Remove the logo background before export. Transparent/antialiased edges are thresholded; logo colors map to the four selected palette colors. Fine features still require a slicer preview and test print.

Print the NFC base separately, install the tag and test-fit the face before gluing. No HueForge software is needed.
''',encoding='utf-8')
    return out


def build_logo_parts(project):
    """Build only the visible logo inlay parts for a standalone logo export.

    The same rasterisation, palette quantisation, mirroring, and outline repair
    used by the complete face are retained.  This keeps a logo-only STL aligned
    with the face export while omitting the card background and backing sheet.
    """
    logo = project.logo
    if not logo.enabled or not logo.path:
        raise ValueError('Load or extract a logo before creating logo geometry.')
    if not Path(logo.path).exists():
        raise ValueError(f'Logo file was not found: {logo.path}')
    parts = [part for part in build_face(project) if part['name'].startswith('Logo -')]
    if not parts:
        raise ValueError('No visible logo pixels were found. Increase the logo size or use a less transparent image.')
    return parts


def export_logo(project, output):
    """Export standalone logo geometry as a named 3MF and aligned STLs."""
    parts = build_logo_parts(project)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    export_3mf(parts, out / 'CardForge_Logo.3mf', project.hueforge.palette, 'CardForge standalone logo')
    stls = out / 'Logo_STLs'
    stls.mkdir(exist_ok=True)
    info = []
    import re
    for i, part in enumerate(parts, 1):
        name = f'{i:02d}_' + re.sub(r'[^A-Za-z0-9_-]+', '_', part['name']) + '.stl'
        part['mesh'].export(stls / name)
        info.append({'part': part['name'], 'suggested_color': part['color'], 'stl': name})
    combined = trimesh.util.concatenate([part['mesh'] for part in parts])
    combined.export(out / 'CardForge_Logo.stl')
    (out / 'Logo_Parts.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    (out / 'LOGO_README.txt').write_text('''CARDFORGE STANDALONE LOGO

CardForge_Logo.3mf contains the logo as named, separate color parts. Assign
filaments under Objects / Parts in Bambu Studio. Logo_STLs contains the same
parts aligned to one origin; load all files together as one multipart object.
CardForge_Logo.stl is a combined single-color copy for quick inspection.

The logo is mirrored for artwork-side-down printing and occupies the selected
front inlay depth. It has a flat top and bottom so it can be placed on the
CardForge face or used as a separate insert. Inspect the slicer preview before
printing small details.
''', encoding='utf-8')
    return out
