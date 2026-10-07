"""Original line icons, drawn at high resolution and shared by all controls."""
from PIL import Image, ImageDraw, ImageTk


def icon_image(name, color='#334155', size=20):
    scale = 4
    im = Image.new('RGBA', (24*scale, 24*scale))
    d = ImageDraw.Draw(im)
    def line(points, width=1.8):
        d.line([(round(x*scale), round(y*scale)) for x, y in points], fill=color, width=round(width*scale), joint='curve')
    def rect(box, radius=2):
        d.rounded_rectangle(tuple(round(n*scale) for n in box), radius=radius*scale, outline=color, width=7)
    if name == 'app':
        d.rounded_rectangle((0, 0, 96, 96), radius=22, fill='#111317')
        d.rounded_rectangle((16, 22, 79, 77), radius=8, fill='#ffb261')
        d.rounded_rectangle((23, 17, 84, 67), radius=8, fill='#eff1f4')
        d.rounded_rectangle((31, 28, 48, 48), radius=4, fill='#ffb261')
        d.line([(56, 32), (74, 32)], fill='#111317', width=5)
        d.line([(56, 42), (70, 42)], fill='#111317', width=5)
        d.line([(32, 57), (74, 57)], fill='#ffb261', width=4)
    elif name == 'settings':
        for y, x in [(6, 8), (12, 16), (18, 10)]:
            line([(3, y), (21, y)])
            d.ellipse(((x-2)*scale, (y-2)*scale, (x+2)*scale, (y+2)*scale), fill=color)
    elif name == 'center':
        rect((7, 7, 17, 17), 1)
        line([(12, 2), (12, 6)]); line([(12, 18), (12, 22)])
        line([(2, 12), (6, 12)]); line([(18, 12), (22, 12)])
    elif name == 'flip':
        line([(12, 3), (12, 21)], 1)
        line([(8, 6), (3, 18), (8, 18), (8, 6)])
        line([(16, 6), (21, 18), (16, 18), (16, 6)])
    elif name == 'rotate':
        d.arc((4*scale, 4*scale, 20*scale, 20*scale), 25, 300, fill=color, width=7)
        line([(18, 3), (18, 8), (13, 7)])
    elif name in ('up', 'down'):
        pts = [(6, 13), (12, 7), (18, 13)]
        line([(x, 24-y if name == 'down' else y) for x, y in pts])
    elif name in ('image', 'card'):
        rect((3, 5, 21, 19))
        if name == 'image':
            line([(4, 17), (9, 11), (13, 15), (16, 12), (20, 17)])
            d.ellipse((15*scale, 8*scale, 17*scale, 10*scale), fill=color)
        else:
            line([(7, 10), (10, 10)]); line([(7, 14), (17, 14)])
    elif name == 'save':
        rect((4, 3, 20, 21)); rect((8, 3, 16, 9), 0); rect((8, 14, 16, 21), 0)
    elif name == 'folder':
        line([(3, 20), (3, 5), (10, 5), (12, 8), (21, 8), (21, 20), (3, 20)])
    elif name == 'text':
        line([(5, 6), (19, 6)]); line([(12, 6), (12, 20)]); line([(8, 20), (16, 20)])
    elif name == 'plus':
        line([(5, 12), (19, 12)]); line([(12, 5), (12, 19)])
    elif name == 'minus': line([(5, 12), (19, 12)])
    elif name == 'check': line([(4, 12), (10, 18), (20, 6)])
    elif name == 'delete':
        line([(5, 7), (19, 7)]); line([(9, 4), (15, 4)]); rect((7, 7, 17, 21), 1)
        line([(10, 11), (10, 17)]); line([(14, 11), (14, 17)])
    elif name in ('next', 'back'):
        pts = [(9, 5), (16, 12), (9, 19)]
        line([(24-x if name == 'back' else x, y) for x, y in pts])
    elif name in ('undo', 'redo', 'refresh'):
        pts = [(4, 10), (13, 10), (19, 13), (19, 18), (15, 21)]
        if name == 'redo': pts = [(24-x, y) for x, y in pts]
        line(pts)
        pts = [(9, 5), (4, 10), (9, 15)]
        line([(24-x if name == 'redo' else x, y) for x, y in pts])
    elif name == 'download':
        line([(12, 3), (12, 16)]); line([(7, 11), (12, 16), (17, 11)]); line([(4, 17), (4, 21), (20, 21), (20, 17)])
    elif name in ('edit', 'crop'):
        line([(5, 19), (7, 13), (17, 3), (21, 7), (11, 17), (5, 19)])
        line([(14, 6), (18, 10)])
    elif name == 'layers':
        line([(3, 8), (12, 3), (21, 8), (12, 13), (3, 8)])
        line([(3, 12), (12, 17), (21, 12)]); line([(3, 16), (12, 21), (21, 16)])
    elif name == 'search':
        d.ellipse((4*scale, 3*scale, 16*scale, 15*scale), outline=color, width=7)
        line([(14, 14), (21, 21)])
    else:
        # A small sparkle represents cleanup and correction actions.
        line([(12, 3), (14, 10), (21, 12), (14, 14), (12, 21), (10, 14), (3, 12), (10, 10), (12, 3)])
    return im.resize((size, size), Image.Resampling.LANCZOS)


class Icons:
    def __init__(self):
        self.cache = {}

    def get(self, name, light=False, size=20):
        key = (name, light, size)
        if key not in self.cache:
            self.cache[key] = ImageTk.PhotoImage(icon_image(name, '#111317' if light else '#d8dee8', size))
        return self.cache[key]
