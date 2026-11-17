"""Makes the starter pictures for the battle screen's phase feedback, in assets/ui/. Run once:  py tools/make_ui.py
(it overwrites the files, so don't run it after replacing them with your own art - or pass names to make just those:
py tools/make_ui.py target arrow_head)

  cursor.png            the white corners around the outpost you're on (the battlefield cursor). A strip of square
                        frames (here 2: tight, then wide) that the game flips between to make it pulse; drawn centred
                        8 pixels above the middle of the outpost, like the target below.
  target.png            the red target cursor while choosing what to attack. A strip of square frames (here 2) that
                        the game flips between to make it pulse; drawn centred on the enemy outpost.
  target_off.png        the same cursor over something you can't attack (also a strip of square frames, here 1).
  parachute_green.png   the canopy and cords above a soldier dropping in (one per side: parachute_tan.png).
                        The bottom-middle of the picture is where the cords meet the soldier's head.
  dust.png              the puff when a soldier lands: a strip of square frames played left to right (bottom row = ground).
  arrow_body.png        the march arrow's body as a SLICE ACROSS it: the left column, top to bottom, is
                        outline / fill / outline. The game sweeps that slice along the road (round at the bends),
                        so only the colours and thickness matter. Make it as tall as you want the arrow to be thick.
  arrow_head.png        the arrowhead, pointing RIGHT; its right edge is the tip. The game turns it to face up, down
                        or left (quarter turns only, so the pixels never get mangled).
  arrow_head_diagonal.png  the arrowhead on a diagonal road, pointing DOWN-RIGHT along it; its bottom-right corner is
                        the tip. The game flips it for the other three diagonal directions.
  arrow_start.png       the dot where the arrow starts (centred on the outpost the group leaves).
  sky.png               the sky behind the battle scenes, 320x186: everything above the ground. Any size works (it is
                        stretched to fit). A map theme can have its own: assets/terrain/<theme>/sky.png.
  cloud1.png ...        clouds drifting slowly across the battle sky, one picture each. Every cloud*.png in assets/ui
                        is used (add cloud4.png and it shows up too; delete them all for a clear sky).

And in each map theme's folder, assets/terrain/<theme>/:
  blocked.png           what stands between two neighbouring outposts that have no road or river between them (nobody
                        can cross, not even helicopters): a forest on grass, mountains on desert and snow, boulders on
                        the beach. Its bottom middle sits just below the middle of the gap; about 34x30 fits the gap.
  road_diagonal.png     one diagonal road, going DOWN-RIGHT from one outpost to the next (the game mirrors it for
                        roads going down-left). 88x80: the road starts 10 pixels in from the top-left corner (the
                        centre of the upper outpost) and ends 10 pixels in from the bottom-right corner (the centre of
                        the lower one); its ends are hidden under the outposts. It is pasted pixel for pixel (never
                        stretched): on maps drawn a little bigger or smaller the ends reach a few pixels less or
                        further, so paint the road on out into the margin. This recipe draws the theme's road.png
                        turned at the angle, as the game used to; paint over it for a cleaner diagonal.
"""
import math
import os
import sys

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pw.gfx import C, SIDES, SIDE_FILE        # noqa: E402  (colours from data/style.json)
from pw.data import STEP_X, STEP_Y            # noqa: E402  (spacing of outposts: the angle of diagonal roads)
from pw.world import DIAGONAL_STEP, DIAGONAL_MARGIN, tiled     # noqa: E402  (the size of road_diagonal.png)

OUT = os.path.join(ROOT, 'assets', 'ui')
INK, CLEAR = C['ink'], (0, 0, 0, 0)


def surface(w, h):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(CLEAR)
    return s


def target_frame(s, ox, col, r):
    """A ring with four ticks across it and a dot in the middle, centred in a 44x44 frame starting at x = ox."""
    x, y = ox + 22, 22
    for rr, c in ((r + 1, INK), (r, col), (r - 1, col), (r - 2, INK)):
        pygame.draw.circle(s, c, (x, y), rr, 1)
    pygame.draw.circle(s, INK, (x, y), 4)
    pygame.draw.circle(s, col, (x, y), 3)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        a = (x + dx * (r - 5), y + dy * (r - 5))
        b = (x + dx * (r + 5), y + dy * (r + 5))
        pygame.draw.line(s, INK, a, b, 4)
        pygame.draw.line(s, col, a, b, 2)


def cursor():
    """2 square frames of 38x38: white corner brackets with a dark line under each, the second 1 pixel wider all round
    (the same picture the game used to draw itself)."""
    s = surface(76, 38)
    for f in range(2):
        x0, x1, y0, y1 = f * 38 + 2 - f, f * 38 + 35 + f, 2 - f, 36 + f
        for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            s.fill(C['white'], (min(cx, cx + dx * 4), cy, 5, 1))
            s.fill(C['white'], (cx, min(cy, cy + dy * 4), 1, 5))
            s.fill(C['ink'], (min(cx, cx + dx * 4), cy + dy, 5, 1))
    return s


def target():
    s = surface(88, 44)
    target_frame(s, 0, C['phase_target'], 14)
    target_frame(s, 44, C['phase_target'], 15)
    return s


def target_off():
    s = surface(44, 44)
    target_frame(s, 0, C['grey'], 14)
    return s


def parachute(side):
    """A white dome with two stripes in the side's colour, and two cords meeting at the bottom middle."""
    w, h, cw, ch = 24, 17, 11, 7
    s = surface(w, h)
    cx, top = 12, 1
    pygame.draw.ellipse(s, INK, (cx - cw - 1, top - 1, cw * 2 + 2, ch * 2 + 2))
    pygame.draw.ellipse(s, C['white'], (cx - cw, top, cw * 2, ch * 2))
    for k in (-1, 1):
        pygame.draw.line(s, SIDES[side]['main'], (cx + k * cw // 2, top + 1), (cx + k * cw // 2, top + ch), 2)
    s.fill(CLEAR, (0, top + ch, w, h))                       # keep only the top half: a dome
    pygame.draw.line(s, INK, (cx - cw - 1, top + ch - 1), (cx + cw, top + ch - 1))
    for sx in (cx - cw, cx + cw - 1):
        pygame.draw.line(s, INK, (sx, top + ch), (cx, h - 1))
    return s


def dust():
    """4 square frames of a puff spreading out and fading (each 36x36; the ground is the bottom row)."""
    fw, fh, n = 36, 36, 4
    s = surface(fw * n, fh)
    for f in range(n):
        k = f / (n - 1)
        a = round(230 * (1 - k * .85))
        for dx in (-6, 0, 6):
            cx, cy = f * fw + fw / 2 + dx * (1 + k), fh - 3 - k * 4
            rx, ry = round(3 + k * 3), round(2 + k * 2)
            pygame.draw.ellipse(s, (196, 170, 128, a), (cx - rx, cy - ry, rx * 2 + 1, ry * 2 + 1))
    return s


def arrow_body():
    """8 tall: 2 outline, 4 fill, 2 outline (8 wide just so it's easy to see in a paint program)."""
    s = surface(8, 8)
    for y, c in enumerate([INK, INK, C['phase_march'], C['phase_march'], C['phase_march'], C['phase_march'], INK, INK]):
        s.fill(c, (0, y, 8, 1))
    return s


def arrow_head():
    w, h = 14, 19
    s = surface(w, h)
    m = h // 2
    pygame.draw.polygon(s, INK, [(w - 1, m), (0, 0), (0, h - 1)])
    pygame.draw.polygon(s, C['phase_march'], [(w - 4, m), (2, 3), (2, h - 4)])
    return s


def arrow_head_diagonal():
    """The same arrowhead as arrow_head (11 long, 19 wide, 1-pixel outline) but along a diagonal road, pointing
    down-right, with the tip in the bottom-right corner."""
    a = math.atan2(STEP_Y, STEP_X)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    pts = [(0, 0), (-ux * 11 + nx * 9, -uy * 11 + ny * 9), (-ux * 11 - nx * 9, -uy * 11 - ny * 9)]
    x0, y0 = min(x for x, _ in pts), min(y for _, y in pts)
    pts = [(round(x - x0), round(y - y0)) for x, y in pts]
    s = surface(max(x for x, _ in pts) + 1, max(y for _, y in pts) + 1)
    pygame.draw.polygon(s, C['phase_march'], pts)
    pygame.draw.polygon(s, INK, pts, 1)
    return s


def arrow_start():
    s = surface(9, 9)
    pygame.draw.circle(s, INK, (4, 4), 4)
    pygame.draw.circle(s, C['phase_march'], (4, 4), 3)
    return s


def sky():
    """A sunny sky: deep blue at the top fading to pale near the horizon, in pixel-art bands (with a dithered row
    between them)."""
    w, h = 320, 186
    top, bottom = pygame.Color('#3a7fd6'), pygame.Color('#cdeeff')
    s = surface(w, h)
    bands = 9
    for y in range(h):
        k = y / (h - 1)
        b = min(bands - 1, int(k * bands))
        col = top.lerp(bottom, b / (bands - 1))
        nxt = top.lerp(bottom, min(bands - 1, b + 1) / (bands - 1))
        edge = int((y + 1) / (h - 1) * bands) != b and b < bands - 1      # last row of a band: checkerboard into the next
        for x in range(w):
            s.set_at((x, y), nxt if edge and (x + y) % 2 else col)
    return s


def cloud(puffs, w, h):
    """A puffy white cloud from a few circles (x, y, r), shaded light blue underneath with a soft outline."""
    s = surface(w, h)
    for x, y, r in puffs:
        pygame.draw.circle(s, C['white'], (x, y), r)
    pygame.draw.rect(s, C['white'], (puffs[0][0], h - 6, puffs[-1][0] - puffs[0][0], 5))
    shade, line = pygame.Color('#d4e9fb'), pygame.Color('#9cc4e8')
    m = pygame.mask.from_surface(s)
    for y in range(h):
        for x in range(w):
            if m.get_at((x, y)) and y >= h * .62:
                s.set_at((x, y), shade)
    for p in m.outline():
        s.set_at(p, line)
    return s


def tree(s, cx, by, r, leaf, shade, light):
    """A round leafy tree standing at (cx, by): a short trunk, the crown shaded at the bottom right."""
    s.fill(pygame.Color('#6b4a2b'), (cx - 1, by - 3, 2, 3))
    cy = by - 2 - r
    pygame.draw.circle(s, shade, (cx, cy), r)
    pygame.draw.circle(s, leaf, (cx - 1, cy - 1), r - 1)
    pygame.draw.circle(s, light, (cx - r // 3 - 1, cy - r // 3 - 1), max(1, r // 3))


def pine(s, cx, by, h, leaf, shade):
    """A small pine tree standing at (cx, by)."""
    s.fill(pygame.Color('#6b4a2b'), (cx - 1, by - 2, 2, 2))
    pygame.draw.polygon(s, shade, [(cx, by - h), (cx + h // 2, by - 2), (cx, by - 2)])
    pygame.draw.polygon(s, leaf, [(cx, by - h), (cx - h // 2, by - 2), (cx, by - 2)])


def mountain(s, cx, by, half, h, lit, shade, cap=None, cap_shade=None):
    """A peak standing on (cx, by): the left face lit, the right face in shadow, and an optional snowcap."""
    top, ridge = (cx, by - h), (cx + half // 5, by)
    pygame.draw.polygon(s, lit, [(cx - half, by), top, ridge])
    pygame.draw.polygon(s, shade, [top, (cx + half, by), ridge])
    if cap:
        k = .38                                                          # how far down the snow reaches
        left, right = (cx - half * k, by - h * (1 - k)), (cx + half * k, by - h * (1 - k))
        mid = (cx + half // 5 * k, by - h * (1 - k))
        teeth = [left, (cx - half * k / 2, by - h * (1 - k) + 2), mid]     # a ragged bottom edge
        pygame.draw.polygon(s, cap, [top] + teeth)
        pygame.draw.polygon(s, cap_shade, [top, mid, (cx + half * k / 2, by - h * (1 - k) + 2), right])


def boulder(s, cx, cy, rx, ry, lit, shade, light):
    pygame.draw.ellipse(s, shade, (cx - rx, cy - ry, rx * 2, ry * 2))
    pygame.draw.ellipse(s, lit, (cx - rx, cy - ry, rx * 2 - 2, ry * 2 - 2))
    pygame.draw.ellipse(s, light, (cx - rx + 2, cy - ry + 1, max(2, rx // 2), max(2, ry // 2)))


def blocked(theme):
    """34x30: what fills the gap between two outposts with no road or river between them."""
    s = surface(34, 30)
    col = pygame.Color
    if theme == 'grass':                                   # a forest: a back row of darker trees, two in front
        for x in (7, 17, 27):
            tree(s, x, 21, 7, col('#3d7327'), col('#2f5a22'), col('#4a8a2c'))
        for x in (12, 23):
            tree(s, x, 30, 7, col('#4a8a2c'), col('#2f5a22'), col('#5e9e38'))
    elif theme == 'snow':                                  # snowy mountains with a pine at the foot
        mountain(s, 20, 29, 14, 26, col('#a8aa9c'), col('#76786c'), col('#ffffff'), col('#d6e6f2'))
        mountain(s, 9, 30, 9, 16, col('#a8aa9c'), col('#76786c'), col('#ffffff'), col('#d6e6f2'))
        pine(s, 29, 30, 9, col('#4a8a2c'), col('#2f5a22'))
    elif theme == 'desert':                                # red rock mountains
        mountain(s, 20, 29, 14, 24, col('#c07a45'), col('#8e5236'))
        mountain(s, 9, 30, 9, 15, col('#d08c55'), col('#9c5c38'))
        mountain(s, 29, 30, 5, 9, col('#d08c55'), col('#9c5c38'))
    else:                                                  # beach: a pile of boulders
        for cx, cy, rx, ry in ((17, 17, 10, 8), (8, 23, 7, 6), (26, 23, 7, 6), (17, 26, 6, 4)):
            boulder(s, cx, cy, rx, ry, col('#a8aa9c'), col('#76786c'), col('#c4c6ba'))
    return s


def road_diagonal(theme):
    """The theme's road.png turned to run corner to corner (as straight-road strips used to be drawn on diagonals)."""
    road = pygame.image.load(os.path.join(ROOT, 'assets', 'terrain', theme, 'road.png'))
    (w, h), m = DIAGONAL_STEP, DIAGONAL_MARGIN
    s = surface(w + 2 * m, h + 2 * m)
    strip = tiled((math.ceil(math.hypot(w, h)), road.get_height()), road)
    turned = pygame.transform.rotate(strip, -math.degrees(math.atan2(h, w)))
    s.blit(turned, turned.get_rect(center=(m + w / 2, m + h / 2)))
    return s


RECIPES = {'cursor': cursor, 'target': target, 'target_off': target_off, 'dust': dust,
           'arrow_body': arrow_body, 'arrow_head': arrow_head, 'arrow_head_diagonal': arrow_head_diagonal,
           'arrow_start': arrow_start, 'sky': sky,
           'cloud1': lambda: cloud([(10, 14, 7), (20, 9, 9), (31, 11, 8), (40, 15, 6)], 48, 22),
           'cloud2': lambda: cloud([(8, 10, 6), (17, 7, 7), (27, 10, 6)], 35, 17),
           'cloud3': lambda: cloud([(10, 17, 8), (22, 11, 10), (35, 9, 9), (47, 13, 8), (56, 18, 6)], 64, 25)}
THEMES = ('grass', 'desert', 'beach', 'snow')
WHERE = {}                                     # recipes saved in a theme's folder instead of assets/ui
for _theme in THEMES:
    RECIPES['blocked_' + _theme] = lambda theme=_theme: blocked(theme)
    RECIPES['road_diagonal_' + _theme] = lambda theme=_theme: road_diagonal(theme)
    for _part in ('blocked', 'road_diagonal'):
        WHERE[f'{_part}_{_theme}'] = os.path.join(ROOT, 'assets', 'terrain', _theme, _part + '.png')
for _side in range(2):
    RECIPES['parachute_' + SIDE_FILE[_side]] = lambda side=_side: parachute(side)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name in sys.argv[1:] or RECIPES:
        img = RECIPES[name]()
        pygame.image.save(img, WHERE.get(name, os.path.join(OUT, name + '.png')))
        print(f'{name + ".png":22s} {img.get_width()}x{img.get_height()}')
