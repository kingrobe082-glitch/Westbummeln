"""Erzeugt die App-Icons (Funkgerät-Signet) als SVG und PNG/ICO nach static/icons/.

Nur ein Entwicklerwerkzeug, kein Teil der App: Pillow steht deshalb nicht in requirements.txt.

    pip install pillow
    python tools/make_icons.py

SVG und PNGs entstehen aus derselben Geometrie (Koordinaten auf einer 512er-Fläche), damit sie gleich aussehen.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / 'static' / 'icons'
BG = '#15263a'
SUPERSAMPLE = 4  # in vierfacher Größe zeichnen und verkleinern = glatte Kanten

# Funkgerät, um (DX, DY) verschoben, damit das Motiv mittig sitzt.
DX, DY = -40, 16
RECTS = [  # (x0, y0, x1, y1, Eckenradius, Farbe)
    (286 + DX, 96 + DY, 306 + DX, 190 + DY, 10, '#d9e4ef'),  # Antenne
    (176 + DX, 170 + DY, 336 + DX, 420 + DY, 28, '#e63731'),  # Gehäuse
    (200 + DX, 198 + DY, 312 + DX, 258 + DY, 10, '#ffd16e'),  # Display
    (204 + DX, 288 + DY, 308 + DX, 302 + DY, 7, '#8f211c'),  # Lautsprecher
    (204 + DX, 318 + DY, 308 + DX, 332 + DY, 7, '#8f211c'),
    (204 + DX, 348 + DY, 308 + DX, 362 + DY, 7, '#8f211c'),
]
WAVE_CENTER = (296 + DX, 110 + DY)
WAVES = [  # (Radius, Startwinkel, Endwinkel) – Grad, 0 = rechts, im Uhrzeigersinn
    (50, -30, 30), (85, -30, 30), (50, 150, 210), (85, 150, 210),
]
WAVE_WIDTH = 14
WAVE_COLOR = '#ffd16e'

# Varianten: (Hintergrund abgerundet?, Motiv-Skalierung). Maskable-Icons schneidet das System beliebig zu,
# das Motiv muss in den inneren Kreis (Radius 40 %) passen.
ANY = (True, 1.0)
MASKABLE = (False, 0.78)
APPLE = (False, 0.86)  # iOS rundet selbst ab und mag keine Transparenz


def transform(scale):
    """Funktion, die 512er-Koordinaten um die Mitte skaliert."""
    return lambda v: 256 + (v - 256) * scale


def draw_png(size, variant):
    rounded, scale = variant
    big = size * SUPERSAMPLE
    k = big / 512
    t = transform(scale)
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=96 * k if rounded else 0, fill=BG)
    for x0, y0, x1, y1, radius, color in RECTS:
        draw.rounded_rectangle((t(x0) * k, t(y0) * k, t(x1) * k, t(y1) * k), radius=radius * scale * k, fill=color)
    cx, cy = t(WAVE_CENTER[0]) * k, t(WAVE_CENTER[1]) * k
    width = WAVE_WIDTH * scale * k
    for radius, start, end in WAVES:
        outer = radius * scale * k + width / 2  # Pillow zeichnet die Linienbreite nach innen
        draw.arc((cx - outer, cy - outer, cx + outer, cy + outer), start, end, fill=WAVE_COLOR, width=round(width))
    return image.resize((size, size), Image.LANCZOS)


def svg(variant):
    rounded, scale = variant
    t = transform(scale)

    def num(value):
        return f'{value:.2f}'.rstrip('0').rstrip('.')

    parts = [f'<rect width="512" height="512" rx="{96 if rounded else 0}" fill="{BG}"/>']
    for x0, y0, x1, y1, radius, color in RECTS:
        parts.append(f'<rect x="{num(t(x0))}" y="{num(t(y0))}" width="{num((x1 - x0) * scale)}" '
                     f'height="{num((y1 - y0) * scale)}" rx="{num(radius * scale)}" fill="{color}"/>')
    cx, cy = t(WAVE_CENTER[0]), t(WAVE_CENTER[1])
    for radius, start, end in WAVES:
        r = radius * scale
        x0, y0 = cx + r * math.cos(math.radians(start)), cy + r * math.sin(math.radians(start))
        x1, y1 = cx + r * math.cos(math.radians(end)), cy + r * math.sin(math.radians(end))
        parts.append(f'<path d="M{num(x0)} {num(y0)}A{num(r)} {num(r)} 0 0 1 {num(x1)} {num(y1)}" fill="none" '
                     f'stroke="{WAVE_COLOR}" stroke-width="{num(WAVE_WIDTH * scale)}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
            '<title>Westbummeln Leitstelle</title>' + ''.join(parts) + '</svg>\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'icon.svg').write_text(svg(ANY), encoding='utf-8')
    draw_png(192, ANY).save(OUT / 'icon-192.png', optimize=True)
    draw_png(512, ANY).save(OUT / 'icon-512.png', optimize=True)
    draw_png(512, MASKABLE).save(OUT / 'icon-maskable-512.png', optimize=True)
    draw_png(180, APPLE).convert('RGB').save(OUT / 'apple-touch-icon.png', optimize=True)
    draw_png(256, ANY).save(OUT / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
    for path in sorted(OUT.iterdir()):
        print(f'{path.name}: {path.stat().st_size} Bytes')


if __name__ == '__main__':
    main()
