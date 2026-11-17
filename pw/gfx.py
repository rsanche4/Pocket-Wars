"""Drawing helpers: the 320x240 screen, images from assets/, the pixel font, and a few simple shapes."""
import math
import os
import pygame

from .data import ROOT, load_json
from .lang import tr

SW, SH = 320, 240
STYLE = load_json('data', 'style.json')
FONT = load_json('data', 'font.json')
C = {k: pygame.Color(v) for k, v in STYLE['colors'].items()}
SIDES = [{k: pygame.Color(v) if isinstance(v, str) and v.startswith('#') else v for k, v in s.items()} for s in STYLE['sides']]
THEMES = {k: {n: pygame.Color(c) for n, c in t.items()} for k, t in STYLE['themes'].items()}
SIDE_FILE = ['green', 'tan']

_images, _missing = {}, set()


def image(path):
    """An image from assets/ (e.g. 'units/map/tank_green.png'). Missing files show as a magenta box."""
    if path not in _images:
        full = os.path.join(ROOT, 'assets', path)
        try:
            _images[path] = pygame.image.load(full).convert_alpha()
        except (FileNotFoundError, pygame.error):
            if path not in _missing:
                print('Pocket Wars: missing image', full)
                _missing.add(path)
            s = pygame.Surface((8, 8))
            s.fill((255, 0, 255))
            _images[path] = s
    return _images[path]


def has_image(path):
    return os.path.exists(os.path.join(ROOT, 'assets', path))


def unit_image(kind, t, side):
    """kind: 'map' (battlefield), 'battle' (cut-in scenes) or 'icons' (menus)."""
    return image(f'units/{kind}/{t}_{SIDE_FILE[side]}.png')


def building_image(kind, side):
    return image(f"buildings/{kind}_{'neutral' if side is None else SIDE_FILE[side]}.png")


def blit(surf, img, x, y, alpha=255):
    """Pictures are drawn exactly as they are in the folder (never mirrored), so each side's art should already face the right way."""
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surf.blit(img, (round(x), round(y)))


# ---------- pixel font (assets/ui/font.png, digits.png) ----------
_tinted, _texts = {}, {}


def _sheet(name, color):
    key = (name, tuple(color))
    if key not in _tinted:
        s = image(f'ui/{name}.png').copy()
        s.fill(color, special_flags=pygame.BLEND_RGBA_MULT)
        _tinted[key] = s
    return _tinted[key]


def text_width(s, scale=1):
    return len(tr(str(s).upper())) * 6 * scale - scale


def _render(s, color, scale):
    key = (s, tuple(color), scale)
    if key not in _texts:
        sheet, chars = _sheet('font', color), FONT['chars']
        out = pygame.Surface((max(1, len(s) * 6), 7), pygame.SRCALPHA)
        for i, ch in enumerate(s):
            n = chars.find(ch)
            if n < 0:
                n = chars.find('?')
            out.blit(sheet, (i * 6, 0), (n * 6, 0, 6, 7))
        if scale > 1:
            out = pygame.transform.scale(out, (out.get_width() * scale, 7 * scale))
        if len(_texts) > 1500:
            _texts.clear()
        _texts[key] = out
    return _texts[key]


def text(surf, s, x, y, color=None, scale=1, align='l', shadow=None):
    s = tr(str(s).upper())              # in the chosen language (lang.py)
    color = color or C['white']
    w = text_width(s, scale)
    x -= w // 2 if align == 'c' else w if align == 'r' else 0
    if shadow:
        surf.blit(_render(s, shadow, scale), (round(x) + scale, round(y) + scale))
    surf.blit(_render(s, color, scale), (round(x), round(y)))


def wrap(s, width):
    s = tr(str(s).upper())
    lines, line = [], ''
    for word in str(s).split(' '):
        if len((line + ' ' + word).strip()) > width:
            lines.append(line.strip())
            line = word
        else:
            line += ' ' + word
    if line.strip():
        lines.append(line.strip())
    return lines


def digits(surf, s, x, y, color):
    """The tiny 3x5 numbers used for unit counts."""
    sheet, chars = _sheet('digits', color), FONT['digits']
    for i, ch in enumerate(str(s)):
        n = chars.find(ch)
        surf.blit(sheet, (x + i * 4, y), ((n if n >= 0 else chars.find('?')) * 4, 0, 4, 5))


# ---------- shapes ----------
_see_through = {}


def rect(surf, x, y, w, h, color):
    r = pygame.Rect(round(x), round(y), round(w), round(h))
    if color.a == 255:
        surf.fill(color, r)
    elif r.w > 0 and r.h > 0:
        key = (r.size, tuple(color))
        if key not in _see_through:
            if len(_see_through) > 400:
                _see_through.clear()
            _see_through[key] = pygame.Surface(r.size, pygame.SRCALPHA)
            _see_through[key].fill(color)
        surf.blit(_see_through[key], r)


def ellipse(surf, cx, cy, rx, ry, color):
    """A filled pixel-art ellipse (row by row, so it looks the same as the original game)."""
    cx, cy = round(cx), round(cy)
    for dy in range(-ry, ry + 1):
        w = round(rx * max(0, 1 - dy * dy / ((ry + .5) ** 2)) ** .5)
        rect(surf, cx - w, cy + dy, w * 2 + 1, 1, color)


def ellipse_ring(surf, cx, cy, rx, ry, color, dash=0):
    """A one-pixel ellipse outline; dash > 0 leaves gaps (the blinking highlight)."""
    n = round(2 * math.pi * max(rx, ry))
    for k in range(n):
        if dash and ((k + dash) >> 2) % 2:
            continue
        a = k / n * 2 * math.pi
        surf.set_at((round(cx + rx * math.cos(a)), round(cy + ry * math.sin(a))), color)


def box(surf, x, y, w, h, fill=None, edge=None, inner=None):
    rect(surf, x, y, w, h, edge or C['ink'])
    rect(surf, x + 1, y + 1, w - 2, h - 2, inner or C['paper_dark'])
    rect(surf, x + 2, y + 2, w - 4, h - 4, fill or C['paper'])


def hp_bar(surf, x, y, w, frac, h=2):
    frac = max(0, min(1, frac))                  # never wider than the bar, whatever the numbers say
    rect(surf, x, y, w, h, C['ink'])
    col = pygame.Color('#6fb04a') if frac > .6 else pygame.Color('#f8b030') if frac > .3 else pygame.Color('#e0482c')
    rect(surf, x, y, max(1, round(w * frac)), h, col)


def portrait(surf, side, mood, x, y, hud=False, frame_part=None):
    """A commander's face in its frame. hud=True is the small 34px corner portrait.
    frame_part = (image, area) draws one frame of the title animation strip instead."""
    size = 34 if hud else 56
    s = SIDES[side]
    rect(surf, x - 2, y - 2, size + 4, size + 4, C['ink'])
    rect(surf, x - 1, y - 1, size + 2, size + 2, s['light'])
    rect(surf, x, y, size, size, s['portrait_bg'])
    for k in range(0, size, 3):
        rect(surf, x, y + k, size, 1, s['portrait_lines'])
    folder = 'green_commander' if side == 0 else 'tan_general'
    if frame_part:
        img = frame_part[0].subsurface(frame_part[1])
    else:
        name = f"{'hud_' if hud else ''}{mood}.png"
        if not has_image(f'commanders/{folder}/{name}'):          # a missing face falls back to happy
            name = f"{'hud_' if hud else ''}happy.png"
        img = image(f'commanders/{folder}/{name}')
    surf.blit(pygame.transform.scale(img, (size, size)) if img.get_size() != (size, size) else img, (x, y))
