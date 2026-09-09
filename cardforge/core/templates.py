"""Original starter layouts. All text remains editable; no photo is required."""
from .project import Project, TextLayer
from .fonts import default_font

TEMPLATES = {
    'Blank card': 'A clean canvas for your logo and text.',
    'Business card': 'Name, role and contact details beside your logo.',
    'Membership card': 'A title, member name and member number.',
}


def create_template(name='Blank card'):
    if name not in TEMPLATES:
        raise ValueError('Unknown card template.')
    p = Project(name=name)
    p.logo.x_mm, p.logo.y_mm, p.logo.width_mm = 18, 27, 22
    font = default_font()
    def text(value, x, y, size, color='#111111'):
        return TextLayer(value, x, y, size, font, color)
    if name == 'Business card':
        p.texts = [text('YOUR NAME', 58, 35, 10), text('Your role / company', 58, 27, 6),
                   text('hello@example.com', 58, 17, 6), text('555 0100', 58, 11, 6)]
    elif name == 'Membership card':
        p.texts = [text('MEMBER', 55, 37, 14, '#D92D20'), text('YOUR NAME', 55, 25, 9),
                   text('No. 0001', 55, 14, 7)]
    return p
