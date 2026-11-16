"""The battle cut-in: the screen splits, GREEN always on the left, TAN always on the right.

The scene is outdoors: a sky with drifting clouds above, and below it the battlefield's own ground (grass, sand or
snow, from the map's theme), with the road the units stand on, or the river between them if they fight across one.
The commanders' faces and HP bars sit at the top; the units stand on the ground near the bottom.

Pictures it uses (all swappable): assets/ui/sky.png (or assets/terrain/<theme>/sky.png for one theme),
assets/ui/cloud*.png (every one found drifts by), and the map theme's ground.png, road.png, water.png and bridge.png.

It opens with both halves sliding together, then each commander sliding in from its side with its unit's name and
HP bar. Then it plays in three beats (lengths in data/style.json, "battle_scene_seconds"):
  before  - both units wait, bobbing in place; the commanders look focused
  attack  - shots fly, hits land, HP drains, damage pops up, the commanders react, a destroyed unit fades away
  after   - everything holds so you can take it in
"""
import math
import os
import pygame

from .data import UNITS, ROOT
from .gfx import (C, STYLE, THEMES, SW, SH, rect, ellipse, text, hp_bar, portrait, image, has_image, unit_image,
                  SIDE_FILE)
from .world import tiled
from . import sound

BEATS = STYLE.get('battle_scene_seconds', {'before': 2, 'attack': 2, 'after': 2})
BEFORE, ATTACK, AFTER = BEATS['before'], BEATS['attack'], BEATS['after']
LENGTH = BEFORE + ATTACK + AFTER          # seconds at full speed
FIRE = BEFORE                             # when the shots leave
HIT = FIRE + .3                           # when they land
PORTRAIT, BAR = 56, 78                    # commander face size; HP bar width (kept clear of the seam in the middle)
HUD_Y = 16                                # top of the faces and HP bars
HORIZON = 186                             # sky above, ground below
FEET = 206                                # where the units stand (on the road, when there is one)
COMMANDERS_IN = .2                        # when the commanders start sliding in (seconds into the scene)
LIFT = 28                                 # how high helicopters fly above their shadow
SEAM_TOP, SEAM_BOTTOM = SW / 2 + 16, SW / 2 - 16     # the slanted line between the halves, at the top and bottom


def ramp(t, start, length):
    """0 before start, rising to 1 over `length` seconds, then 1."""
    return max(0, min(1, (t - start) / length))


def overshoot(k):
    """0 -> 1 easing that swings a little past 1 and settles back (a springy arrival)."""
    k -= 1
    return 1 + 2 * k ** 3 + k ** 2


def seam_x(y):
    return SEAM_TOP + (SEAM_BOTTOM - SEAM_TOP) * y / SH


def sky_image(theme):
    for path in (f'terrain/{theme}/sky.png', 'ui/sky.png'):
        if has_image(path):
            img = image(path)
            return img if img.get_size() == (SW, HORIZON) else pygame.transform.scale(img, (SW, HORIZON))
    s = pygame.Surface((SW, HORIZON))
    s.fill(pygame.Color('#8cc8f0'))
    return s


def clouds():
    folder = os.path.join(ROOT, 'assets', 'ui')
    names = sorted(n for n in os.listdir(folder) if n.lower().startswith('cloud') and n.lower().endswith('.png'))
    return [image('ui/' + n) for n in names]


_halves = {}


def half_shape(is_left):
    """White where one half of the split screen is."""
    if is_left not in _halves:
        shape = pygame.Surface((SW, SH), pygame.SRCALPHA)
        pts = [(0, 0), (SEAM_TOP, 0), (SEAM_BOTTOM, SH), (0, SH)] if is_left else [(SEAM_TOP, 0), (SW, 0), (SW, SH), (SEAM_BOTTOM, SH)]
        pygame.draw.polygon(shape, (255, 255, 255, 255), pts)
        _halves[is_left] = shape
    return _halves[is_left]


class CutIn:
    def __init__(self, fight, now, speed=1.0, silent=False, theme='grass', link='road'):
        """speed < 1 plays it faster (Fast battle scenes); silent = no sounds (How to Play pictures).
        theme = the map's look; link = what lies between the two outposts: 'road', 'river' or 'bridge'."""
        self.f, self.start, self.speed, self.silent = fight, now, speed, silent
        self.theme = theme if has_image(f'terrain/{theme}/ground.png') else 'grass'
        self.link = link
        self.skipped = False
        self.fired = self.exploded = False
        self.swap = fight.attacker.side == 1          # GREEN always stands on the left, TAN on the right
        self.images = [self.art(fight.attacker), self.art(fight.target)]
        self.clouds = clouds()
        self.back = self.backdrop()
        self.water = tiled((SW, SH - HORIZON), image(f'terrain/{self.theme}/water.png')) if link in ('river', 'bridge') else None

    def done(self, now):
        return self.skipped or (now - self.start) / self.speed > LENGTH

    @staticmethod
    def art(u):
        """Drawn as it is in the folder (not mirrored): tan pictures should already face left."""
        if u.type == 'hq':
            return image(f'buildings/hq_big_{SIDE_FILE[u.side]}.png')
        img = unit_image('battle', u.type, u.side)
        return pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))

    def backdrop(self):
        """The still picture behind both halves: the sky, then the map theme's ground, and the road."""
        s = pygame.Surface((SW, SH), pygame.SRCALPHA)
        s.blit(sky_image(self.theme), (0, 0))
        s.blit(tiled((SW, SH - HORIZON), image(f'terrain/{self.theme}/ground.png')), (0, HORIZON))
        rect(s, 0, HORIZON, SW, 2, pygame.Color(0, 0, 0, 70))             # the horizon line
        if self.link in ('road', 'bridge'):
            road = self.road()
            s.blit(tiled((SW, road.get_height()), road), (0, self.road_y()))
        return s

    def road(self):
        return image(f'terrain/{self.theme}/road.png')

    def road_y(self):
        """Top of the road strip: the units' feet rest on it, a few pixels above its bottom edge."""
        return FEET - self.road().get_height() + 4

    def draw(self, surf, now):
        f = self.f
        x, y = f.attacker, f.target
        t = (now - self.start) / self.speed
        slide = ramp(t, 0, .25)
        left, right = round(-SW / 2 * (1 - slide)), round(SW / 2 * (1 - slide))
        # the intro: once the halves are in, each commander (face, unit name and HP bar) slides in from its own side
        enter = overshoot(ramp(t, COMMANDERS_IN, .45))
        hud_l = round(-(6 + PORTRAIT + 6 + BAR + 24) * (1 - enter))
        hud_r = -hud_l
        self.draw_half(surf, left, True, now)
        self.draw_half(surf, right, False, now)
        if self.water:
            self.draw_river(surf, left)

        # Spots below are written as if the attacker stood on the left; at() mirrors them when TAN attacks.
        at = (lambda px, w=0: SW - px - w) if self.swap else (lambda px, w=0: px)
        xo, yo = (right, left) if self.swap else (left, right)   # how far each unit's half has slid in
        ax, ay = at(80) + xo, at(240) + yo                         # where the attacker / target stand

        drain = ramp(t, HIT, .6)                       # HP bars drain after the hit
        hx = round(f.attacker_hp - min(f.attacker_hp, f.taken) * drain)
        hy = round(f.target_hp - min(f.target_hp, f.dealt) * drain)
        x_dead, y_dead = f.attacker_hp - f.taken <= 0, f.target_hp - f.dealt <= 0
        recoil = -3 * (1 - ramp(t, FIRE, .15)) if t >= FIRE else 0
        recoil = -recoil if self.swap else recoil      # kick back away from the target
        shake = lambda: round(math.sin(t * 90) * 2) if HIT <= t < HIT + .3 else 0
        self.draw_unit(surf, 0, x, ax + recoil + (shake() if f.fired_back else 0), x_dead, t, phase=0)
        self.draw_unit(surf, 1, y, ay + shake(), y_dead, t, phase=1.7)
        for u, hp in ((x, hx), (y, hy)):               # each commander's face sits right beside its unit's HP bar
            if u.side == 0:
                self.draw_info(surf, u, hp, 6 + PORTRAIT + 6 + hud_l, 'l')
            else:
                self.draw_info(surf, u, hp, SW - 6 - PORTRAIT - 6 + hud_r, 'r')
        if t < min(.9, BEFORE):
            text(surf, 'VS', SW / 2, FEET - 80, C['white'], 2, 'c', C['ink'])

        if FIRE <= t < HIT:                            # shots fly
            if not self.fired:
                self.fired = True
                if not self.silent:
                    sound.play('shot_' + x.type)
            p = ramp(t, FIRE, HIT - FIRE)                  # each shot flies from the shooter's middle to the other's
            y0, y1 = self.aim_y(0), self.aim_y(1)
            rect(surf, at(110 + p * 90, 16), round(y0 - 4 + (y1 - y0) * p), 16, 3, pygame.Color('#fff3a0'))
            ellipse(surf, at(122), y0 - 4, 6, 6, pygame.Color('#ffd23a'))
            if f.fired_back:
                rect(surf, at(210 - p * 90 - 16, 16), round(y1 + 4 + (y0 - y1) * p), 16, 3, pygame.Color('#fff3a0'))
                ellipse(surf, at(198), y1 + 4, 6, 6, pygame.Color('#ffd23a'))
        if HIT <= t < HIT + .35:                       # explosions
            if not self.exploded:
                self.exploded = True
                if not self.silent:
                    sound.play('destroyed' if x_dead or y_dead else 'hit')
                    if y.type == 'hq' and f.dealt > 0:
                        sound.play('hq_hit')
            r = round(4 + (t - HIT) * 60)
            for cx, cy, show in ((ay, self.aim_y(1), True), (ax, self.aim_y(0), f.fired_back)):
                if show:
                    ellipse(surf, cx, cy, r, r, pygame.Color(255, 170, 40, 217))
                    ellipse(surf, cx, cy, round(r * .55), round(r * .55), pygame.Color('#fff3a0'))
        reacted = t >= HIT + .05
        if reacted:                                    # damage numbers rise, then stay
            up = 10 * ramp(t, HIT, .35)
            text(surf, f'-{f.dealt}', ay, self.number_y(1) - up, C['highlight'], 2, 'c', C['ink'])
            if f.fired_back:
                text(surf, f'-{f.taken}', ax, self.number_y(0) - up, C['highlight'], 2, 'c', C['ink'])
            else:
                text(surf, f"{UNITS[y.type]['name']}s can't hit {UNITS[x.type]['name']}s", SW / 2, FEET + 20, C['white'], 1, 'c', C['ink'])
            if UNITS[x.type].get('bonus_vs', {}).get(y.type):
                text(surf, 'ANTI-AIR!' if UNITS[y.type].get('flies') else 'BONUS DAMAGE!', SW / 2, HUD_Y + 66, C['highlight'], 1, 'c', C['ink'])
        if t >= HIT + .5:
            if y_dead:
                text(surf, 'DESTROYED!', ay, FEET + 8, C['red'], 1, 'c', C['ink'])
            if x_dead:
                text(surf, 'DESTROYED!', ax, FEET + 8, C['red'], 1, 'c', C['ink'])

        def mood(mine_dead, theirs_dead, is_hq, took, dealt):
            if not reacted:
                return 'focus'
            return 'sad' if mine_dead else 'happy' if theirs_dead else 'angry' if is_hq and took > 0 else 'hurt' if took > dealt else 'happy'
        faces = {x.side: mood(x_dead, y_dead and y.type != 'hq', False, f.taken, f.dealt),
                 y.side: mood(y_dead and y.type != 'hq', x_dead, y.type == 'hq', f.dealt, f.taken)}
        # the moment the faces change (as the HP drains), they hop and flash so the eye catches them
        pop = math.sin(math.pi * ramp(t, HIT + .05, .3)) if reacted else 0
        for side, px in ((0, 6 + hud_l), (1, SW - 6 - PORTRAIT + hud_r)):
            py = HUD_Y - round(4 * pop)
            if 0 < pop:
                rect(surf, px - 4, py - 4, PORTRAIT + 8, PORTRAIT + 8, C['white'])
            portrait(surf, side, faces[side], px, py)
        text(surf, 'ENTER: SKIP', SW - 5, SH - 10, pygame.Color(255, 255, 255, 180), 1, 'r', C['ink'])

    def draw_half(self, surf, dx, is_left, now):
        """One half of the split screen (sky, clouds, ground), slid dx pixels while it comes in."""
        half = self.back.copy()
        for k, img in enumerate(self.clouds):          # every cloud drifts right at its own speed, then comes round again
            w = img.get_width()
            cx = (k * 113 + now * (4 + 3 * (k % 3))) % (SW + w) - w
            half.blit(img, (round(cx), 26 + k * 37 % 104))
        half.blit(half_shape(is_left), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(half, (dx, 0))

    def draw_river(self, surf, dx):
        """The river between the two outposts, running along the seam in the ground (with a bridge if there is one)."""
        band = 22
        top, bottom = seam_x(HORIZON) + dx, seam_x(SH) + dx
        pts = [(top - band, 0), (top + band, 0), (bottom + band, SH - HORIZON), (bottom - band, SH - HORIZON)]
        shape = pygame.Surface(self.water.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(shape, (255, 255, 255, 255), pts)
        water = self.water.copy()
        water.blit(shape, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(water, (0, HORIZON))
        edge = THEMES[self.theme]['water_edge']
        for k in (-1, 1):
            pygame.draw.line(surf, edge, (top + k * band, HORIZON + 1), (bottom + k * band, SH), 3)
        if self.link == 'bridge':
            br = image(f'terrain/{self.theme}/bridge.png')
            road_mid = self.road_y() + self.road().get_height() / 2
            surf.blit(br, br.get_rect(center=(round(seam_x(road_mid) + dx), round(road_mid))))

    def bottom_y(self, which):
        """Where the bottom of a unit's picture is (0 = attacker, 1 = target): on the ground, or up in the air for a
        helicopter."""
        u = self.f.attacker if which == 0 else self.f.target
        return FEET - (LIFT if UNITS[u.type].get('flies') else 0)

    def aim_y(self, which):
        """Where shots leave from and hit: low on a ground unit, the middle of a helicopter up in the air."""
        if self.bottom_y(which) < FEET:
            return round(self.bottom_y(which) - self.images[which].get_height() / 2)
        return FEET - 40

    def number_y(self, which):
        """Where a unit's damage number pops up: at the usual height, or just above a helicopter flying high."""
        return min(FEET - 94, self.bottom_y(which) - self.images[which].get_height() - 16)

    def draw_unit(self, surf, which, u, cx, dies, t, phase):
        """A unit standing on the ground with its shadow (helicopters hover above theirs). Alive: it bobs gently in
        place (flyers bob more). Destroyed: after the hit it sinks a little and fades to see-through, and stays."""
        img = self.images[which]
        w, h = img.get_size()
        fading = ramp(t, HIT + .2, .8) if dies else 0
        flies = self.bottom_y(which) < FEET
        if fading:
            img = img.copy()
            img.set_alpha(round(255 * (1 - .8 * fading)))
            bob = 12 * fading
        else:
            bob = round(math.sin(t * 2 * math.pi * .9 + phase) * (2 if flies else 1)) if u.type != 'hq' else 0
        if u.type != 'hq':
            sw = round(w * (.32 if flies else .42) * (1 - .7 * fading))
            ellipse(surf, cx, FEET - 1, sw, 3, pygame.Color(0, 0, 0, round(80 * (1 - fading))))
        surf.blit(img, (round(cx - w / 2), round(self.bottom_y(which) - h + bob)))

    def draw_info(self, surf, u, hp, x, align):
        """The unit's name, HP bar and HP, next to its commander's face (x = the edge nearest the face)."""
        text(surf, UNITS[u.type]['name'], x, HUD_Y + 6, C['white'], 1, align, C['ink'])
        bx = x if align == 'l' else x - BAR
        rect(surf, bx, HUD_Y + 18, BAR, 9, C['ink'])
        hp_bar(surf, bx + 1, HUD_Y + 19, BAR - 2, hp / UNITS[u.type]['hp'], 7)
        text(surf, f"{hp}/{UNITS[u.type]['hp']} HP", x, HUD_Y + 31, C['white'], 1, align, C['ink'])
