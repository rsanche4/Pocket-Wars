"""How to Play: pages of a picture plus text (text in data/howto.json). Most pictures are little battles drawn by the
real game code; put assets/howto/<picture>.png (292x100) to show your own picture for a page instead."""
import math
import pygame

from . import sound
from .data import UNITS, load_json
from .rules import Unit, Fight, can_hit, damage_range
from .demo import Scene
from . import editor
from .cutin import CutIn
from .menu import Pages
from .gfx import C, SIDES, SW, SH, rect, text, text_width, wrap, blit, image, has_image, portrait, unit_image

PAGES = load_json('data', 'howto.json')['pages']
PW, PH = 292, 100           # picture size
GREEN, TAN = 0, 1


def make_scenes():
    return {
        'goal': Scene('goal', 'grass', ['H-o-o-h'], .32,
                      [((0, 0), GREEN, 'hq', 1), ((0, 0), GREEN, 'halftrack', 1), ((0, 0), GREEN, 'soldier', 2), ((1, 0), GREEN, 'soldier', 2),
                       ((2, 0), TAN, 'tank', 1), ((2, 0), TAN, 'soldier', 1), ((3, 0), TAN, 'hq', 1, 38), ((3, 0), TAN, 'soldier', 1)],
                      labels=[((0, 0), 'YOUR HQ', SIDES[0]['light']), ((3, 0), 'ENEMY HQ', SIDES[1]['light'])]),
        'outposts': Scene('outposts', 'desert', ['H-o-o-o-h'], .3,
                          [((0, 0), GREEN, 'hq', 1), ((0, 0), GREEN, 'soldier', 1), ((1, 0), GREEN, 'soldier', 2),
                           ((3, 0), TAN, 'soldier', 1), ((3, 0), TAN, 'halftrack', 1), ((4, 0), TAN, 'hq', 1)],
                          labels=[((1, 0), 'YOURS', SIDES[0]['light']), ((2, 0), 'EMPTY', C['white']), ((3, 0), 'ENEMY', SIDES[1]['light'])],
                          loop=('soldier', [(1, 0), (2, 0)], 1.6)),
        'gather': Scene('gather', 'grass', ['o-H-o~o', '  |', '  o'], .3,
                        [((0, 0), GREEN, 'soldier', 1), ((1, 0), GREEN, 'hq', 1), ((1, 0), GREEN, 'soldier', 2), ((3, 0), TAN, 'soldier', 2)],
                        glow=[(0, 0), (1, 0), (2, 0), (1, 1)], cursor=(2, 0), lift=10),
        'march': Scene('march', 'snow', ['H-o-o-o~o'], .28,
                       [((0, 0), GREEN, 'hq', 1), ((0, 0), GREEN, 'soldier', 1), ((1, 0), GREEN, 'halftrack', 1), ((1, 0), GREEN, 'soldier', 2),
                        ((4, 0), TAN, 'soldier', 2), ((4, 0), TAN, 'tank', 1)],
                       glow=[(2, 0), (3, 0)], cursor=(3, 0), loop=('halftrack', [(1, 0), (2, 0), (3, 0)], 1.3)),
        'terrain': Scene('terrain', 'grass', ['G-o~o=o'], .32,
                         [((0, 0), GREEN, 'soldier', 2), ((1, 0), GREEN, 'tank', 1), ((2, 0), GREEN, 'helicopter', 1)],
                         link_labels=[((0, 0), (1, 0), 'ROAD'), ((1, 0), (2, 0), 'RIVER'), ((2, 0), (3, 0), 'BRIDGE')], lift=2),
        'fog': Scene('fog', 'grass', ['H-o-o-o'], .22,
                     [((0, 0), GREEN, 'hq', 1), ((0, 0), GREEN, 'soldier', 1), ((1, 0), GREEN, 'soldier', 2),
                      ((2, 0), TAN, 'soldier', 1), ((3, 0), TAN, 'tank', 1), ((3, 0), TAN, 'soldier', 1)]),
    }


BATTLES = [('tank', 'soldier', 11, 3), ('helicopter', 'tank', 8, 0), ('halftrack', 'helicopter', 10, 6)]


class HowTo(Pages):
    def __init__(self, app, pages=None, on_exit=None):
        self.app, self.page = app, 0
        self.pages = pages or PAGES
        self.on_exit = on_exit or app.title
        self.scenes = make_scenes()
        self.panel = pygame.Surface((PW, PH))
        self.screen320 = pygame.Surface((SW, SH))      # for pictures cropped from a full screen (the battle scene)
        self.battle, self.battle_n = None, 0
        sound.music('title')

    def draw(self, surf, now):
        page = self.pages[self.page]
        self.frame(surf, page['title'])
        rect(surf, 12, 28, PW + 4, PH + 4, C['ink'])
        rect(surf, 13, 29, PW + 2, PH + 2, C['paper_dark'])
        self.panel.fill(C['background'])
        self.picture(page['picture'], now)
        surf.blit(self.panel, (14, 30))
        y = 30 + PH + 7
        for para in page['text']:
            for line in wrap(para, 48):
                text(surf, line, 16, y, C['ink'])
                y += 9
            y += 4

    # ---------------------------------------------------------------- pictures
    def picture(self, key, now):
        p = self.panel
        if has_image(f'howto/{key}.png'):
            p.blit(pygame.transform.scale(image(f'howto/{key}.png'), (PW, PH)), (0, 0))
        elif key == 'fog':
            half = (PW - 2) // 2
            for x, dark in ((0, False), (half + 2, True)):
                part = pygame.Surface((half, PH))
                self.scenes['fog'].draw(part, now, half, PH, fog_side=GREEN, blackout=dark)
                p.blit(part, (x, 0))
            rect(p, half, 0, 2, PH, C['ink'])
            for s, x in (('FOG', 3), ('BLACKOUT', half + 5)):
                rect(p, x - 1, 2, len(s) * 6 + 3, 10, pygame.Color(10, 12, 7, 204))
                text(p, s, x + 1, 4, C['highlight'])
        elif key in editor.DEMOS:
            editor.draw_demo(key, p, now)
        elif key in self.scenes:
            self.scenes[key].draw(p, now, PW, PH)
        elif key == 'tips':
            self.app.backdrop.live(now).draw(p, now, PW, PH)
        else:
            getattr(self, 'pic_' + key, self.pic_missing)(p, now)

    def pic_missing(self, p, now):
        text(p, 'NO PICTURE', PW / 2, PH / 2 - 3, C['grey'], 1, 'c')

    def pic_battle(self, p, now):
        """The real battle scene, drawn full size and cropped: tank vs soldier, helicopter vs tank, half-track vs helicopter."""
        if not self.battle or self.battle.done(now):
            a, t, dealt, taken = BATTLES[self.battle_n % len(BATTLES)]
            self.battle_n += 1
            x, y = Unit(0, GREEN, a, UNITS[a]['hp']), Unit(0, TAN, t, UNITS[t]['hp'])
            self.battle = CutIn(Fight(x, y, dealt, taken, taken > 0, x.hp, y.hp, 'ok'), now + .3, silent=True)
        self.screen320.fill(C['background'])
        self.battle.draw(self.screen320, now)
        p.blit(self.screen320, (0, 0), (14, 72, PW, PH))

    def pic_buy(self, p, now):
        p.fill(C['olive_dark'])
        rect(p, 0, 70, PW, PH - 70, C['olive'])
        rect(p, 0, 70, PW, 1, SIDES[0]['main'])
        vehicles = [t for t in UNITS if UNITS[t]['cost'] > 0]
        for k, t in enumerate(vehicles):
            cx, cost = round(PW / 6 + k * PW / 3), UNITS[t]['cost']
            for j in range(cost):
                blit(p, unit_image('icons', 'soldier', GREEN), cx - (cost * 9 - 1) // 2 + j * 9, 5)
            text(p, '▼', cx, 20, C['highlight'], 1, 'c')
            img = unit_image('battle', t, GREEN)
            bob = round(math.sin(now * 5)) if UNITS[t].get('flies') else 0
            blit(p, img, cx - img.get_width() // 2, 70 - img.get_height() + bob)
            text(p, UNITS[t]['name'], cx, 75, C['white'], 1, 'c', C['ink'])
            text(p, f'{cost} SOLDIERS', cx, 86, C['highlight'], 1, 'c', C['ink'])

    def pic_matchups(self, p, now):
        p.fill(C['olive_dark'])
        rows = [('tank', 'helicopter', '×', "CAN'T HIT IT", C['red']), ('helicopter', 'tank', '▶', 'NO RETURN FIRE', C['highlight']),
                ('halftrack', 'helicopter', '▶', '1.5x DAMAGE', C['highlight'])]
        for k, (a, b, sym, label, col) in enumerate(rows):
            y = 3 + k * 32
            rect(p, 4, y, PW - 8, 29, pygame.Color(0, 0, 0, 72))
            ia, ib = unit_image('map', a, GREEN), unit_image('map', b, TAN)
            bob = lambda t: round(math.sin(now * 5 + k)) if UNITS[t].get('flies') else 0
            blit(p, ia, 34 - ia.get_width() // 2, y + 23 - ia.get_height() + bob(a))
            text(p, sym, 70, y + 11, col, 1, 'c', C['ink'])
            blit(p, ib, 106 - ib.get_width() // 2, y + 23 - ib.get_height() + bob(b))
            text(p, f"{UNITS[a]['name']} VS {UNITS[b]['name']}", 138, y + 6, C['white'], 1, 'l', C['ink'])
            text(p, label, 138, y + 17, col, 1, 'l', C['ink'])

    def pic_units(self, p, now):
        p.fill(C['paper'])
        rect(p, 0, 0, PW, 12, C['olive'])
        cols = [('HP', 132), ('DMG', 168), ('MOVE', 206), ('SIGHT', 244), ('COST', 284)]
        text(p, 'UNIT', 30, 3, C['white'])
        for label, x in cols:
            text(p, label, x, 3, C['white'], 1, 'r')
        for k, t in enumerate(UNITS):
            u, y = UNITS[t], 13 + k * 17
            if k % 2:
                rect(p, 0, y, PW, 17, C['paper_dark'])
            img = unit_image('icons', t, GREEN)              # the HQ too: units/icons/hq_green.png
            blit(p, img, 13 - img.get_width() // 2, y + 14 - img.get_height())
            text(p, u['name'], 30, y + 5, C['ink'])
            values = [u['hp'], '{}-{}'.format(*u['damage']), '-' if t == 'hq' else f"{u['move']} FLY" if u.get('flies') else u['move'],
                      u['sight'], 'FREE' if t == 'soldier' else '-' if t == 'hq' else u['cost']]
            for v, (_, x) in zip(values, cols):
                text(p, v, x, y + 5, C['ink'], 1, 'r')

    def pic_damage(self, p, now):
        """Who hurts whom: average damage of one shot, and shots needed to destroy the target. Worked out from data/units.json."""
        p.fill(C['paper'])
        types = list(UNITS)
        col_w, label_w, top, row_h = 55, 17, 13, 17

        def icon(t, x, y):
            img = unit_image('icons', t, GREEN)
            blit(p, img, x - img.get_width() // 2, y + 12 - img.get_height())

        rect(p, 0, 0, PW, top, C['paper_dark'])
        rect(p, 0, top - 1, PW, 1, C['ink'])
        for k, t in enumerate(types):                     # column headings: the targets
            icon(t, label_w + k * col_w + col_w // 2, 0)
        for r, a in enumerate(types):                     # one row per attacker
            y = top + r * row_h
            if r % 2:
                rect(p, 0, y, PW, row_h, C['paper_dark'])
            icon(a, label_w // 2 + 1, y + 2)
            for k, t in enumerate(types):
                cx = label_w + k * col_w + col_w // 2
                if not can_hit(a, t):
                    text(p, "CAN'T HIT", cx, y + 5, C['red'], 1, 'c')
                    continue
                lo, hi = damage_range(a, t)
                avg = (lo + hi) / 2
                shots = math.ceil(UNITS[t]['hp'] / avg)
                if UNITS[a].get('bonus_vs', {}).get(t):
                    rect(p, cx - col_w // 2 + 1, y, col_w - 2, row_h, C['highlight'])
                dmg, hits = f'{avg:g}', f'×{shots}'                # e.g. 8.5 ×3 = 8.5 damage a shot, 3 hits to destroy
                x = cx - (text_width(dmg) + 5 + text_width(hits)) // 2
                text(p, dmg, x, y + 5, C['ink'])
                text(p, hits, x + text_width(dmg) + 5, y + 5, C['dim'])

    def pic_controls(self, p, now):
        """The keys, pressing one after another. Each key is an image: assets/ui/keys/<key>.png and <key>_pressed.png."""
        p.fill(C['olive_dark'])
        down = int(now / .45) % 9

        def key(name, x, y, pressed):
            p.blit(image(f"ui/keys/{name}{'_pressed' if pressed else ''}.png"), (x, y))
        key('up', 38, 8, down == 0)
        key('left', 16, 26, down == 3)
        key('down', 38, 26, down == 2)
        key('right', 60, 26, down == 1)
        text(p, 'MOVE', 48, 50, C['highlight'], 1, 'c', C['ink'])
        key('enter', 114, 8, down in (5, 6))
        text(p, 'SELECT', 148, 50, C['highlight'], 1, 'c', C['ink'])
        text(p, 'OR Z / SPACE', 148, 61, C['paper_dark'], 1, 'c')
        key('esc', 216, 16, down == 7)
        text(p, 'BACK', 236, 50, C['highlight'], 1, 'c', C['ink'])
        text(p, 'OR X', 236, 61, C['paper_dark'], 1, 'c')
        text(p, 'LEFT/RIGHT CHANGE VALUES IN MENUS', PW / 2, 82, C['white'], 1, 'c', C['ink'])

    def pic_commanders(self, p, now):
        p.fill(C['olive_dark'])
        moods = ['focus', 'happy', 'hurt', 'angry', 'sad']
        for k, mood in enumerate(moods):
            x = (PW - (len(moods) - 1) * 46 - 34) // 2 + k * 46      # centred row of small portraits
            portrait(p, GREEN, mood, x, 6, hud=True)
            portrait(p, TAN, mood, x, 48, hud=True)
            text(p, mood, x + 17, 88, C['paper_dark'], 1, 'c')
