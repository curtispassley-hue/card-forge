"""Project-specific, offline illustrated printing and assembly instructions."""
from html import escape
from pathlib import Path


def assembly_diagram(kind):
    """Original schematic, deliberately labelled as an exploded view, not to scale."""
    pieces = {'lightbox': [('Artwork + diffuser', 110, '#ffb261'), ('Shell + front support lip', 290, '#7c8da0'), ('Removable rear back', 480, '#afbac8')],
              'wall_art': [('Artwork panel', 170, '#ffb261'), ('Plaque backing', 410, '#7c8da0')],
              'nfc_card': [('Printed face', 150, '#ffb261'), ('Base + NFC pocket', 410, '#7c8da0')],
              'stl_panel': [('Artwork panel', 150, '#ffb261'), ('Selected flat STL surface', 410, '#7c8da0')]}[kind]
    objects=[]
    for label,x,color in pieces:
        objects.append(f'<g><path d="M{x},80 l95,12 v150 l-95,-12 z" fill="{color}" fill-opacity=".18" stroke="{color}" stroke-width="3"/><path d="M{x+95},92 l12,-8 v150 l-12,8" fill="none" stroke="{color}"/><text x="{x+48}" y="280" text-anchor="middle">{escape(label)}</text></g>')
        if kind=='lightbox' and x==290:
            objects.append('<path d="M306,105 l60,8 v114 l-60,-8 z" fill="none" stroke="#7c8da0"/><path d="M312,112 l49,6 v94" fill="none" stroke="#ffdf83" stroke-width="3"/><text x="342" y="305" text-anchor="middle">LED strip inside walls</text>')
        if kind=='nfc_card' and x==410:
            objects.append('<ellipse cx="454" cy="164" rx="24" ry="27" fill="none" stroke="#ffdf83" stroke-dasharray="5 4"/><text x="454" y="169" text-anchor="middle">NFC</text>')
    for (_,x,_),(_,next_x,_) in zip(pieces,pieces[1:]):
        objects.append(f'<path d="M{x+115},163 H{next_x-15}" stroke="#afbac8" stroke-width="2" marker-end="url(#arrow)"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 690 340" role="img" aria-label="Exploded assembly schematic"><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#afbac8"/></marker></defs><rect width="690" height="340" rx="14" fill="#161b22"/><g font-family="Arial,sans-serif" font-size="13" fill="#eff1f4"><text x="24" y="30">Exploded view — not to scale. Join parts in the order shown.</text>'+''.join(objects)+'</g></svg>'


def write_assembly_guide(project, out, scope='complete', parts=None):
    p,g,f,n=project.product,project.geometry,project.face,project.nfc
    names={'lightbox':'Lightbox','wall_art':'Wall art','nfc_card':'NFC card','stl_panel':'STL artwork panel'}
    included={'complete':'Complete object','artwork':'Artwork panel only','structure':'Body / base parts only (no artwork)'}[scope]
    steps={
      'lightbox':[
        'Print the fit coupon socket and insert first. Try the insert without forcing it; adjust Fit per side and regenerate both panel and body if necessary.',
        'Print the artwork panel face-down as one multipart object, with its color parts aligned. Use translucent material for the diffuser and suitable light-transmitting artwork colors. The screen cannot predict illumination.',
        'Print the shell from Print_Parts with its front support lip on the build plate. Print the rear back from Print_Parts exterior-side down; its tongue should point upward. Print the desktop cradle separately if included.',
        'Dry-fit the artwork in front of the shell, against the front support lip. Inspect the *_Assembly.3mf file to see the placement. The artwork sits one panel thickness ahead of the shell, not inside the rear cover. Bond or otherwise secure it only after the fit and light-leak check.',
        f'Measure your LED kit and connector. Current profile: {p.lighting_name}. Strip width {p.led_width_mm:g} mm, thickness {p.led_thickness_mm:g} mm, cut interval {p.led_cut_mm:g} mm, front setback {p.led_setback_mm:g} mm. These editable measurements do not certify kit compatibility.',
        f'Route an adhesive-backed, externally powered low-voltage strip along the inside walls behind the artwork. Follow its own bend limits and marked cut points. Route the cable through the {p.cable_side} rear notch ({p.cable_diameter_mm:g} mm cable setting). Do not pinch or strain it. Check illumination and heat with the kit before final assembly.',
        'Fit the rear cover tongue into the shell after routing the cable. The clearance fit is not a latch; tape or suitable fasteners may be needed after testing. Keep the lighting accessible for service.',
        'For desktop use, seat the assembled body in the separate cradle and check tipping stability. For wall use, secure the rear mounting holes with hardware appropriate for the wall and weight; wall fasteners are not modelled.'
      ],
      'wall_art':[
        'Print the artwork panel face-down as one multipart object. Keep all color inlays and the backing sheet aligned.',
        'Print the separate plaque backing from Print_Parts flat-side down. Do not slice the assembled inspection model as a single fused part.',
        'Dry-fit the panel against the front of the plaque backing, artwork facing outward. Compare the assembly preview and check the perimeter before bonding with an adhesive suitable for your printed materials.',
        'For wall mounting, the backing has hanging holes. Choose suitable wall hardware for the finished weight. For desktop use, print the separate cradle and test the plaque fit and stability before display.'
      ],
      'nfc_card':[
        'Print the artwork face as one face-down multipart object. Both exterior faces are flat; lettering and image colors occupy only the first front layers.',
        f'Print the separate NFC base with its recess and tag pocket facing up. Measure the actual tag: this project uses diameter {n.diameter_mm:g} mm, thickness {n.thickness_mm:g} mm and clearance {n.clearance_mm:g} mm.',
        'Test-fit the tag in its pocket and check that it reads with your device. Dry-fit the face in the recess with the artwork facing outward. Do not force a tight fit.',
        'Install the tag, bond the face only after checking fit, and verify the NFC read again after assembly.'
      ],
      'stl_panel':[
        'Print the face-down artwork panel separately, keeping the named color parts aligned.',
        'The imported model retains its coordinates in the assembly inspection files. Print its independent STL from Print_Parts with an orientation and supports appropriate for that model.',
        f'The artwork attaches to the selected flat surface with a {p.surface_gap_mm:g} mm gap. This is a separate attached panel, not a carved recess or curved wrap. Check orientation against the assembly preview.',
        'Dry-fit and secure the artwork with a bond appropriate for the printed materials after verifying that other features and moving parts remain clear.'
      ]}[p.kind]
    if p.mounting!='desktop': steps=[s for s in steps if not s.startswith('For desktop use,') or p.kind=='lightbox']
    printing=[
        'In Bambu Studio, select your actual printer, nozzle, plate and material presets. A1 models here must fit its 256 × 256 mm build plate; check other printers against their own volume. These files contain models, not validated printer settings or ready-to-run G-code.',
        'When body parts are included, use their independent files in Print_Parts (or the separate NFC base STL). The assembly 3MF and Assembly_STLs are inspection references, not one combined print job. Arrange independent structural parts across plates as needed.',
        'When artwork is included, import the multipart *_Artwork.3mf or *_Face.3mf as a model and assign actual filaments in Objects / Parts. If using aligned artwork STLs, import the entire set as one multipart object; do not arrange or drop each inlay to the bed separately.',
        f'Artwork is already mirrored for printing face-down. Do not mirror it again. Front depth is {f.front_depth_mm:g} mm and total panel thickness is {f.thickness_mm:g} mm. Choose first-layer and subsequent layer heights that divide these depths, then inspect the layer transitions and tiny details.',
        'An A1 with AMS Lite holds four spools. Share/remap artwork and background colors when needed; body parts can be printed separately in their own material. Map the model assignments to the spools actually installed.',
        'Slice and review each plate. Test dimensional fit, small letters, mounting/cradle stability and any lighting temperatures before committing to a finished object.'
    ]
    warning='Only the selected package scope is included. Use parts from the same project and dimensions when completing the assembly; the diagram shows the full object even in a partial export.'
    files=sorted(str(x.relative_to(out)).replace('\\','/') for x in Path(out).rglob('*') if x.is_file())
    title=f'CardForge — {names[p.kind]} — {project.name}'
    text=title+'\n\nPackage: '+included+f'\nObject: {g.card_width_mm:g} × {g.card_height_mm:g} mm\n\n'+warning+'\n\nPRINTING IN BAMBU STUDIO\n\n'+'\n\n'.join(f'{i}. {s}' for i,s in enumerate(printing,1))+'\n\nASSEMBLY\n\n'+'\n\n'.join(f'{i}. {s}' for i,s in enumerate(steps,1))+'\n\nINCLUDED FILES\n'+'\n'.join(files)+'\n\nThis is an unverified physical design: slicer review and a test print are required.\n'
    (Path(out)/'ASSEMBLY_GUIDE.txt').write_text(text,encoding='utf-8')
    def listing(items):return '<ol>'+''.join('<li>'+escape(s)+'</li>' for s in items)+'</ol>'
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+escape(title)+'</title><style>body{font:16px/1.65 Arial,sans-serif;margin:35px auto;max-width:950px;padding:0 22px;color:#202630}h1,h2{line-height:1.3}li{padding:6px 0}svg{width:100%;max-width:800px}.note{background:#fff3df;border-left:4px solid #ba681e;padding:14px}code{overflow-wrap:anywhere}@media print{body{margin:0}h2,svg{break-inside:avoid}}</style><h1>'+escape(title)+'</h1><p>Package: <strong>'+included+'</strong> · '+f'{g.card_width_mm:g} × {g.card_height_mm:g} mm'+'</p><p class="note">'+escape(warning)+'</p>'+assembly_diagram(p.kind)+'<h2>Print in Bambu Studio</h2>'+listing(printing)+'<h2>Put your object together</h2>'+listing(steps)+'<h2>Included files</h2><ul>'+''.join('<li><code>'+escape(name)+'</code></li>' for name in files)+'</ul><p>This design needs a slicer review and physical test print. Lighting, adhesives and mounting hardware are not included or certified.</p><p>Printer references: <a href="https://bambulab.com/en/a1/tech-specs">Bambu A1 specifications</a> · <a href="https://us.store.bambulab.com/products/a1">A1 / AMS Lite FAQ</a>. The schematic and assembly sequence describe this project’s generated geometry.</p></html>'
    (Path(out)/'ASSEMBLY_GUIDE.html').write_text(html,encoding='utf-8')
