"""The battle cut-in: the screen splits, GREEN always on the left, TAN always on the right.

It plays in three beats (lengths in data/style.json, "battle_scene_seconds"):
  before  - both units wait, bobbing in place; the commanders look focused
  attack  - shots fly, hits land, HP drains, damage pops up, the commanders react, a destroyed unit fades away
  after   - everything holds so you can take it in
"""
import math
import pygame

from .data import UNITS
from .gfx import C, SIDES, STYLE, SW, SH, rect, ellipse, text, hp_bar, portrait, image, unit_image, SIDE_FILE
from . import sound

BEATS = STYLE.get('battle_scene_seconds', {'before': 2, 'attack': 2, 'after': 2})
BEFORE, ATTACK, AFTER = BEATS['before'], BEATS['attack'], BEATS['after']
LENGTH = BEFORE + ATTACK + AFTER          # seconds at full speed
FIRE = BEFORE                             # when the shots leave
HIT = FIRE + .3                           # when they land


def ramp(t, start, length):
    """0 before start, rising to 1 over `length` seconds, then 1."""
    return max(0, min(1, (t - start) / length))


class CutIn:
    def __init__(self, fight, now, speed=1.0, silent=False):
        """speed < 1 plays it faster (Fast battle scenes); silent = no sounds (How to Play pictures)."""
        self.f, self.start, self.speed, self.silent = fight, now, speed, silent
        self.skipped = False
        self.fired = self.exploded = False
        self.swap = fight.attacker.side == 1          # GREEN always stands on the left, TAN on the right
        self.images = [self.art(fight.attacker), self.art(fight.target)]

    def done(self, now):
        return self.skipped or (now - self.start) / self.speed > LENGTH

    @staticmethod
    def art(u):
        """Drawn as it is in the folder (not mirrored): tan pictures should already face left."""
        if u.type == 'hq':
            return image(f'buildings/hq_big_{SIDE_FILE[u.side]}.png')
        img = unit_image('battle', u.type, u.side)
        return pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))

    def draw(self, surf, now):
        f = self.f
        x, y = f.attacker, f.target
        t = (now - self.start) / self.speed
        slide = ramp(t, 0, .25)
        left, right = round(-SW / 2 * (1 - slide)), round(SW / 2 * (1 - slide))
        self.draw_half(surf, 0, left, True)
        self.draw_half(surf, 1, right, False)
        pygame.draw.line(surf, C['ink'], (SW / 2 + 16 + left, 0), (SW / 2 - 16 + left, SH), 4)   # the slanted seam between the halves

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
        for u, hp in ((x, hx), (y, hy)):
            if u.side == 0:
                self.draw_info(surf, u, hp, 10 + left, 'l')
            else:
                self.draw_info(surf, u, hp, SW - 10 + right, 'r')
        if t < min(.9, BEFORE):
            text(surf, 'VS', SW / 2, 100, C['white'], 2, 'c', C['ink'])

        if FIRE <= t < HIT:                            # shots fly
            if not self.fired:
                self.fired = True
                if not self.silent:
                    sound.play('shot_' + x.type)
            p = ramp(t, FIRE, HIT - FIRE)
            rect(surf, at(110 + p * 90, 16), 128, 16, 3, pygame.Color('#fff3a0'))
            ellipse(surf, at(122), 128, 6, 6, pygame.Color('#ffd23a'))
            if f.fired_back:
                rect(surf, at(210 - p * 90 - 16, 16), 136, 16, 3, pygame.Color('#fff3a0'))
                ellipse(surf, at(198), 136, 6, 6, pygame.Color('#ffd23a'))
        if HIT <= t < HIT + .35:                       # explosions
            if not self.exploded:
                self.exploded = True
                if not self.silent:
                    sound.play('destroyed' if x_dead or y_dead else 'hit')
                    if y.type == 'hq' and f.dealt > 0:
                        sound.play('hq_hit')
            r = round(4 + (t - HIT) * 60)
            for cx, show in ((ay, True), (ax, f.fired_back)):
                if show:
                    ellipse(surf, cx, 130, r, r, pygame.Color(255, 170, 40, 217))
                    ellipse(surf, cx, 130, round(r * .55), round(r * .55), pygame.Color('#fff3a0'))
        reacted = t >= HIT + .05
        if reacted:                                    # damage numbers rise, then stay
            up = 10 * ramp(t, HIT, .35)
            text(surf, f'-{f.dealt}', ay, 90 - up, C['highlight'], 2, 'c', C['ink'])
            if f.fired_back:
                text(surf, f'-{f.taken}', ax, 90 - up, C['highlight'], 2, 'c', C['ink'])
            else:
                text(surf, f"{UNITS[y.type]['name']}s can't hit {UNITS[x.type]['name']}s", SW / 2, 186, C['white'], 1, 'c', C['ink'])
            if UNITS[x.type].get('bonus_vs', {}).get(y.type):
                text(surf, 'ANTI-AIR!' if UNITS[y.type].get('flies') else 'BONUS DAMAGE!', SW / 2, 60, C['highlight'], 1, 'c', C['ink'])
        if t >= HIT + .5:
            if y_dead:
                text(surf, 'DESTROYED!', ay, 173, C['red'], 1, 'c', C['ink'])
            if x_dead:
                text(surf, 'DESTROYED!', ax, 173, C['red'], 1, 'c', C['ink'])

        def mood(mine_dead, theirs_dead, is_hq, took, dealt):
            if not reacted:
                return 'focus'
            return 'sad' if mine_dead else 'happy' if theirs_dead else 'angry' if is_hq and took > 0 else 'hurt' if took > dealt else 'happy'
        faces = {x.side: mood(x_dead, y_dead and y.type != 'hq', False, f.taken, f.dealt),
                 y.side: mood(y_dead and y.type != 'hq', x_dead, y.type == 'hq', f.dealt, f.taken)}
        portrait(surf, 0, faces[0], 6 + left, SH - 60)
        portrait(surf, 1, faces[1], SW - 62 + right, SH - 60)
        text(surf, 'ENTER: SKIP', SW / 2, SH - 10, pygame.Color(255, 255, 255, 180), 1, 'c')

    def draw_half(self, surf, side, dx, is_left):
        s = SIDES[side]
        half = pygame.Surface((SW, SH), pygame.SRCALPHA)
        half.fill(s['battle_bg'])
        for k in range(0, SH, 4):
            half.fill(s['battle_lines'], (0, k, SW, 1))
        half.fill(s['battle_ground'], (0, 170, SW, SH - 170))
        shape = pygame.Surface((SW, SH), pygame.SRCALPHA)
        pts = [(0, 0), (SW / 2 + 16, 0), (SW / 2 - 16, SH), (0, SH)] if is_left else [(SW / 2 + 16, 0), (SW, 0), (SW, SH), (SW / 2 - 16, SH)]
        pygame.draw.polygon(shape, (255, 255, 255, 255), pts)
        half.blit(shape, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(half, (dx, 0))

    def draw_unit(self, surf, which, u, cx, dies, t, phase):
        """A unit standing on its side of the screen. Alive: it bobs gently in place (flyers bob more).
        Destroyed: after the hit it sinks a little and fades to see-through, and stays like that."""
        img = self.images[which]
        w, h = img.get_size()
        fading = ramp(t, HIT + .2, .8) if dies else 0
        if fading:
            img = img.copy()
            img.set_alpha(round(255 * (1 - .8 * fading)))
            bob = 12 * fading
        else:
            bob = round(math.sin(t * 2 * math.pi * .9 + phase) * (2 if UNITS[u.type].get('flies') else 1)) if u.type != 'hq' else 0
        surf.blit(img, (round(cx - w / 2), round(170 - h + bob)))

    def draw_info(self, surf, u, hp, x, align):
        s = SIDES[u.side]
        text(surf, f"{s['name']} {UNITS[u.type]['name']}", x, 14, C['white'], 1, align, C['ink'])
        bx = x if align == 'l' else x - 110
        rect(surf, bx, 26, 110, 7, C['ink'])
        hp_bar(surf, bx + 1, 27, 108, hp / UNITS[u.type]['hp'], 5)
        text(surf, f"{hp}/{UNITS[u.type]['hp']} HP", x, 37, C['white'], 1, align, C['ink'])
