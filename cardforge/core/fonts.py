from pathlib import Path

FONT_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'

def bundled_fonts():
    return {p.stem.replace('-', ' '): str(p) for p in sorted(FONT_ROOT.glob('*/*.ttf'))}

def default_font():
    choices=bundled_fonts()
    return choices.get('Lato Regular') or next(iter(choices.values()), 'arial.ttf')
