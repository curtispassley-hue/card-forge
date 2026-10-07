"""Offline studio theme and original decorative graphics, never used by exports."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw
from tkinter import ttk

BG = '#111317'
PANEL = '#1a1d23'
CONTROL = '#252931'
LINE = '#343a44'
TEXT = '#eff1f4'
MUTED = '#b0b8c5'
ACCENT = '#ffb261'


def apply_theme(app):
    app.configure(bg=BG)
    for widget in ('Toplevel', 'Frame', 'Canvas', 'Text', 'Listbox', 'Menu'):
        app.option_add(f'*{widget}.background', PANEL)
    for widget in ('Text', 'Listbox', 'Menu'):
        app.option_add(f'*{widget}.foreground', TEXT)
        app.option_add(f'*{widget}.selectBackground', LINE)
    app.option_add('*Text.insertBackground', ACCENT)
    app.option_add('*Menu.activeBackground', LINE)
    app.option_add('*Menu.activeForeground', ACCENT)
    app.option_add('*Menu.relief', 'flat')
    app.option_add('*Menu.borderWidth', 0)
    app.option_add('*TCombobox*Listbox.background', CONTROL)
    app.option_add('*TCombobox*Listbox.foreground', TEXT)
    s = ttk.Style(app); s.theme_use('clam')
    s.configure('.', font=('Segoe UI', 10), background=PANEL, foreground=TEXT,
                bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, focuscolor=ACCENT)
    s.configure('TFrame', background=PANEL)
    s.configure('Chrome.TFrame', background=BG)
    s.configure('TLabel', background=PANEL, foreground=TEXT)
    s.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
    s.configure('Step.TLabel', font=('Segoe UI', 9, 'bold'), foreground=ACCENT)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('TButton', padding=(9, 7), relief='flat', borderwidth=0, background=CONTROL)
    for name, bg, fg, active in [('Secondary', CONTROL, TEXT, LINE),
                               ('Accent', ACCENT, BG, '#ffc58b'),
                               ('Danger', '#39272b', '#ffb4b4', '#513036'),
                               ('Phase', BG, MUTED, CONTROL),
                               ('ActivePhase', CONTROL, ACCENT, LINE)]:
        s.configure(name+'.TButton', background=bg, foreground=fg, padding=(10, 8),
                    relief='flat', borderwidth=0, font=('Segoe UI', 10, 'bold'))
        s.map(name+'.TButton', background=[('disabled', CONTROL), ('active', active)],
              foreground=[('disabled', '#717985')])
    for name in ('TEntry', 'TSpinbox', 'TCombobox'):
        s.configure(name, padding=5, fieldbackground=CONTROL, foreground=TEXT,
                    insertcolor=ACCENT, arrowcolor=MUTED, bordercolor=LINE)
        s.map(name, fieldbackground=[('readonly', CONTROL), ('disabled', PANEL)],
              foreground=[('readonly', TEXT), ('disabled', MUTED)],
              bordercolor=[('focus', ACCENT)])
    s.configure('TCheckbutton', background=PANEL, indicatorbackground=CONTROL, indicatorforeground=ACCENT)
    s.map('TCheckbutton', background=[('active', PANEL)], indicatorbackground=[('selected', ACCENT)])
    s.configure('TRadiobutton', background=PANEL, indicatorbackground=CONTROL, indicatorforeground=ACCENT)
    s.map('TRadiobutton', background=[('active', PANEL)])
    s.configure('TSeparator', background=LINE)
    s.configure('Treeview', rowheight=38, background=PANEL, fieldbackground=PANEL, foreground=TEXT, borderwidth=0)
    s.map('Treeview', background=[('selected', CONTROL)], foreground=[('selected', ACCENT)])
    s.configure('TScrollbar', troughcolor=PANEL, background=LINE, arrowcolor=MUTED, borderwidth=0)
    s.map('TScrollbar', background=[('active', '#535b68')])
    s.configure('TScale', troughcolor=CONTROL, background=ACCENT)
    s.configure('TProgressbar', troughcolor=BG, background=ACCENT, borderwidth=0, thickness=3)
    s.configure('TLabelframe', background=PANEL, bordercolor=LINE)
    s.configure('TLabelframe.Label', background=PANEL, foreground=MUTED)


@lru_cache(maxsize=3)
def studio_backdrop(width, height):
    """Quiet contour lines and a geometric CF mark behind the editing canvas."""
    im = Image.new('RGB', (width, height), BG); d = ImageDraw.Draw(im)
    for band in range(12):
        points = []
        for x in range(-30, width+31, 12):
            y = height*.8 + band*19 + math.sin(x/max(140,width*.22)+band*.10)*height*.14
            points.append((x, y))
        d.line(points, fill='#25272c' if band%3 == 0 else '#1c1f24', width=1)
    # Two card silhouettes in the upper corner, deliberately very low contrast.
    for offset in (0, 18, 36):
        x, y = width-230+offset, -32+offset
        d.rounded_rectangle((x,y,x+190,y+124), radius=18, outline='#27272b', width=1)
    x, y = 26, height-94
    d.polygon([(x+20,y),(x+40,y+12),(x+40,y+36),(x+20,y+48),(x,y+36),(x,y+12)], outline='#43372b')
    d.line([(x+28,y+15),(x+12,y+15),(x+12,y+33),(x+28,y+33)], fill='#43372b', width=2)
    d.line([(x+20,y+24),(x+29,y+24)], fill='#43372b', width=2)
    return im


def brand(canvas):
    canvas.create_polygon(25,3,46,15,46,39,25,51,4,39,4,15, fill='#32281f', outline=ACCENT)
    canvas.create_line(32,18,17,18,17,35,32,35, fill=ACCENT, width=2)
    canvas.create_line(25,26,33,26, fill=ACCENT, width=2)


def template_art(kind, size=(204,64)):
    im=Image.new('RGB',(204,64),BG); d=ImageDraw.Draw(im)
    if kind=='lightbox':
        d.rounded_rectangle((63,8,143,53),radius=9,fill='#29221d',outline=ACCENT,width=2)
        d.line((77,57,130,57),fill=MUTED,width=2)
        d.line((101,52,101,57),fill=MUTED,width=2)
    elif kind=='wall_art':
        d.rounded_rectangle((58,8,146,56),radius=4,outline=MUTED,width=2)
        d.polygon([(66,45),(88,24),(105,42),(118,29),(138,45)],fill='#443327',outline=ACCENT)
    elif kind=='stl_panel':
        d.polygon([(78,9),(129,18),(142,45),(91,54),(64,34)],outline=MUTED)
        d.polygon([(79,17),(119,24),(119,40),(79,33)],fill='#443327',outline=ACCENT)
    else:
        d.rounded_rectangle((58,9,147,55),radius=8,outline=MUTED,width=2)
        d.ellipse((70,20,91,41),outline=ACCENT,width=2)
        d.line((102,25,135,25),fill=MUTED,width=2); d.line((102,34,125,34),fill=MUTED,width=2)
    return im.resize(size, Image.Resampling.LANCZOS)
