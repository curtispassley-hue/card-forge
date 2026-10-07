"""Original starter layouts. All text remains editable; no photo is required."""
from .project import Project, TextLayer
from .fonts import default_font

TEMPLATES = {
    'Blank card': 'A clean canvas for your logo and text.',
    'Business card': 'Name, role and contact details beside your logo.',
    'Membership card': 'A title, member name and member number.',
    'Wall art': 'A plaque with editable artwork and a separate backing.',
    'Desktop lightbox': 'Artwork panel, shell, removable back and cradle.',
    'Wall lightbox': 'Illuminated artwork with mounting holes in the back.',
}


def create_template(name='Blank card'):
    if name not in TEMPLATES:
        raise ValueError('Unknown card template.')
    p = Project(name=name)
    p.logo.x_mm, p.logo.y_mm, p.logo.width_mm = 18, 27, 22
    font = default_font()
    def text(value, x, y, size, color='#111111'):
        return TextLayer(value, x, y, size, font, color)
    if name in ('Wall art', 'Desktop lightbox', 'Wall lightbox'):
        p.product.kind = 'wall_art' if name == 'Wall art' else 'lightbox'
        p.product.mounting = 'desktop' if name == 'Desktop lightbox' else 'wall'
        p.geometry.card_width_mm, p.geometry.card_height_mm = 150, 100
        p.geometry.face_border_mm, p.geometry.face_clearance_mm = 2, .25
        p.geometry.corner_radius_mm = 6
        p.face.thickness_mm = 1.2 if p.product.kind == 'lightbox' else .8
        p.geometry.face_recess_depth_mm = p.face.thickness_mm
        p.logo.x_mm,p.logo.y_mm,p.logo.width_mm = 75,50,50
        p.product.led_width_mm = 8
        p.product.led_setback_mm = 12
        p.product.depth_mm = 30
        p.name = name
        p.texts = [text('YOUR DESIGN',75,50,24)]
        p.editor.show_nfc_guide = False
    elif name == 'Business card':
        p.texts = [text('YOUR NAME', 58, 35, 10), text('Your role / company', 58, 27, 6),
                   text('hello@example.com', 58, 17, 6), text('555 0100', 58, 11, 6)]
    elif name == 'Membership card':
        p.texts = [text('MEMBER', 55, 37, 14, '#D92D20'), text('YOUR NAME', 55, 25, 9),
                   text('No. 0001', 55, 14, 7)]
    return p
