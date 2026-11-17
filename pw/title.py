"""The title screen: a live, slightly blurred battle behind the title, the two commanders, and the main menu.
The first time it appears the title drops in, then the commanders slide in, then the menu fades up."""
import random
import pygame

from . import sound
from .demo import title_battle
from .gfx import C, SIDES, STYLE, SW, SH, rect, box, text, text_width, portrait, image, has_image
from .menu import Menu

FOLDERS = ['green_commander', 'tan_general']


class Backdrop:
    """The live battle behind the title and menus. new() swaps in a different random map.
    To show a fixed picture instead, save it as assets/ui/title_backdrop.png (320x240)."""
    def __init__(self, app):
        self.app, self.battle, self.fade = app, None, 0
        self.layer = pygame.Surface((SW, SH))

    def new(self, now):
        self.battle = title_battle(self.app.maps, now, self.battle and self.battle.g.map)
        self.fade = now

    def live(self, now):
        if not self.battle:
            self.new(now)
        return self.battle

    def draw(self, surf, now, dim=None, blur=True):
        if has_image('ui/title_backdrop.png'):
            surf.blit(pygame.transform.scale(image('ui/title_backdrop.png'), (SW, SH)), (0, 0))
        else:
            self.layer.fill(C['background'])
            self.live(now).draw(self.layer, now, SW, SH)
            surf.blit(pygame.transform.gaussian_blur(self.layer, 1) if blur else self.layer, (0, 0))
            fade = max(0, min(1, (now - self.fade) / .5))     # a new battle fades in over half a second
            if fade < 1:
                rect(surf, 0, 0, SW, SH, pygame.Color(10, 12, 7, round(255 * (1 - fade))))
        if dim:
            rect(surf, 0, 0, SW, SH, dim)


class Commander:
    """A commander on the title: a focused face that blinks now and then like a real person (every 2-6 seconds,
    sometimes twice in a row), and catches a shine. The other faces are kept for reactions in battle.
    If assets/commanders/<folder>/title.png exists (a strip of square frames) it plays that instead."""
    def __init__(self, side):
        self.side = side
        self.next_blink, self.blink_until, self.double = None, 0, 0     # first blink is timed on the first draw

    def draw(self, surf, x, y, now):
        folder = FOLDERS[self.side]
        if has_image(f'commanders/{folder}/title.png'):
            strip = image(f'commanders/{folder}/title.png')
            size = strip.get_height()
            frame = int(now * STYLE.get('title_anim_fps', 8)) % max(1, strip.get_width() // size)
            portrait(surf, self.side, 'happy', x, y, frame_part=(strip, (frame * size, 0, size, size)))
        else:
            if self.next_blink is None:
                self.next_blink = now + 1.2 + self.side * .9 + random.random() * 2
            if now > self.next_blink:
                self.blink_until, self.next_blink = now + .12, now + 2 + random.random() * 4
                if random.random() < .2:
                    self.double = now + .26              # a quick second blink
            if self.double and now > self.double:
                self.blink_until, self.double = now + .1, 0
            blinking = now < self.blink_until and has_image(f'commanders/{folder}/blink.png')
            portrait(surf, self.side, 'blink' if blinking else 'focus', x, y)
        shine = ((now + self.side * 3) % 7) / .6
        if shine < 1:                                    # a light glint sweeping across the frame
            glint = pygame.Surface((56, 56), pygame.SRCALPHA)
            s = round(shine * 96) - 20
            for r in range(56):
                glint.fill((255, 255, 255, 70), (s - r // 2, r, 5, 1))
            surf.blit(glint, (x, y))
        for k, word in enumerate(SIDES[self.side]['commander'].split(' ')):
            text(surf, word, x + 28, y + 62 + k * 9, SIDES[self.side]['light'], 1, 'c', C['ink'])


def ease(t):
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = max(0, min(1, t))
    return 1 + 2.7 * (t - 1) ** 3 + 1.7 * (t - 1) ** 2


def faded(surf, alpha, draw):
    """Draw something at partial opacity."""
    if alpha >= 1:
        draw(surf)
        return
    layer = pygame.Surface((SW, SH), pygame.SRCALPHA)
    draw(layer)
    layer.set_alpha(round(255 * max(0, alpha)))
    surf.blit(layer, (0, 0))


class Title:
    def __init__(self, app, intro=False):
        self.app = app
        self.items = [{'l': 'TUTORIAL', 'f': app.tutorial},
                      {'l': 'PLAYER VS CPU', 'f': lambda: app.choose_map('cpu')},
                      {'l': 'PLAYER VS PLAYER', 'f': lambda: app.choose_map('hot')},
                      {'l': 'MANUAL', 'f': app.how_to_play},
                      {'l': 'MAP EDITOR', 'f': app.map_editor},
                      {'l': 'OPTIONS', 'f': app.options}]
        self.sel = 0
        self.intro = None          # set to the start time on the first frame when playing the intro
        self.want_intro = intro
        self.slams = set()
        self.shake = -1
        self.quit_menu = None
        self.commanders = [Commander(0), Commander(1)]
        sound.music('title')

    def key(self, k):
        if self.intro is not None:           # any key skips the intro
            self.intro = None
            return
        if self.quit_menu:
            m = self.quit_menu
            if k in 'ud':
                m.move(-1 if k == 'u' else 1)
                sound.play('cursor')
            elif k == 'b':
                self.quit_menu = None
                sound.play('back')
            elif k == 'e':
                sound.play('select')
                self.quit_menu = None
                m.items[m.sel]['f']()
            return
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(self.items)
            sound.play('cursor')
        elif k == 'e':
            sound.play('select')
            self.items[self.sel]['f']()
        elif k == 'b':
            sound.play('open')
            self.quit_menu = Menu('QUIT POCKET WARS?', [{'l': 'NO', 'f': lambda: None}, {'l': 'YES, QUIT', 'f': self.app.quit}])

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        if self.want_intro:
            self.intro, self.want_intro = now, False
        e = 99 if self.intro is None else now - self.intro
        if e > 3.4:
            self.intro = None
        self.app.backdrop.draw(surf, now, pygame.Color(8, 10, 6, 56))
        if e < 1:
            rect(surf, 0, 0, SW, SH, pygame.Color(0, 0, 0, round(255 * (1 - ease(e)))))
        for name, at in (('slam1', .78), ('slam2', 1.08), ('shine', 2.25)):
            if e < 99 and e >= at and name not in self.slams:
                self.slams.add(name)
                sound.play('shine' if name == 'shine' else 'slam')
                if name != 'shine':
                    self.shake = now
        shake = round((random.random() - .5) * 4) if e < 99 and now - self.shake < .16 else 0

        faded(surf, ease((e - .3) / .5), lambda s: (rect(s, 0, 0, SW, 76, pygame.Color(14, 18, 9, 158)),
                                                    rect(s, 0, 76, SW, 1, pygame.Color(255, 224, 112, 90))))
        text(surf, 'POCKET', SW / 2 + shake, round(-30 + 40 * ease_back((e - .4) / .42)), C['white'], 3, 'c', C['ink'])
        text(surf, 'WARS', SW / 2 - shake, round(-30 + 68 * ease_back((e - .7) / .42)), C['highlight'], 3, 'c', C['ink'])

        def credit(s):
            words = "2026 RAFFY'S PLAYGROUND"
            x = round(SW / 2 - (text_width(words) + 10) / 2)
            mark = image('ui/copyright.png').copy()
            mark.fill(pygame.Color('#cfd8b8'), special_flags=pygame.BLEND_RGBA_MULT)
            s.blit(mark, (x, 64))
            text(s, words, x + 10, 64, pygame.Color('#cfd8b8'), 1, 'l', C['ink'])
        faded(surf, ease((e - 1.4) / .5), credit)

        slide = round((1 - ease((e - 1.7) / .6)) * 96)
        self.commanders[0].draw(surf, 18 - slide, 98, now)
        self.commanders[1].draw(surf, SW - 74 + slide, 98, now)

        appear = ease((e - 2.1) / .5)

        def menu_box(s):
            x, y = 96, 98 + round((1 - appear) * 10)       # lined up with the tops of the commanders' frames
            box(s, x, y, 128, len(self.items) * 13 + 10)
            for k, it in enumerate(self.items):
                on, yy = k == self.sel, y + 6 + k * 13
                if on:
                    rect(s, x + 3, yy - 2, 122, 11, C['highlight'])
                text(s, it['l'], x + 64, yy, C['ink'], 1, 'c')
                if on and int(now / .3) % 2:
                    text(s, '▶', x + 7, yy, C['ink'])
        faded(surf, appear, menu_box)

        def footer(s):
            rect(s, 0, SH - 12, SW, 12, pygame.Color(10, 12, 7, 199))
            text(s, 'ARROWS: MOVE   ENTER: SELECT   ESC: BACK', SW / 2, SH - 10, C['white'], 1, 'c')
        faded(surf, ease((e - 2.5) / .4), footer)
        if self.quit_menu:
            self.quit_menu.draw(surf, 0, SH, SIDES[0])
