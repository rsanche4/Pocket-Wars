"""Menu screens: choose a battlefield, battle setup, and options."""
import pygame

from . import sound, learn
from .data import map_problems
from .gfx import C, SIDES, SW, SH, THEMES, rect, box, text, wrap
from .settings import S, save


def cycle(options, value, d):
    i = options.index(value) if value in options else 0
    return options[(i + d) % len(options)]


def mini_map(surf, m, x, y, w, h):
    """A small plan of a map: roads, rivers, bridges, outposts, barracks and HQs."""
    t = THEMES[m.theme]
    rect(surf, x, y, w, h, t['base'])
    s = min((w - 8) / m.w, (h - 8) / m.h)
    ox, oy = x + (w - m.w * s) / 2, y + (h - m.h * s) / 2
    at = lambda n: (round(ox + n.x * s), round(oy + n.y * s))
    for e in m.links:
        a, b = at(m.nodes[e.a]), at(m.nodes[e.b])
        if e.kind == 'road':
            pygame.draw.line(surf, t['road'], a, b, 2)
        else:
            for k in range(0, 10):                      # dotted river link
                if k % 2 == 0:
                    pygame.draw.line(surf, t['water'], (a[0] + (b[0] - a[0]) * k / 10, a[1] + (b[1] - a[1]) * k / 10),
                                     (a[0] + (b[0] - a[0]) * (k + 1) / 10, a[1] + (b[1] - a[1]) * (k + 1) / 10))
        if e.bridge:
            rect(surf, (a[0] + b[0]) / 2 - 1, (a[1] + b[1]) / 2 - 1, 3, 3, pygame.Color('#7a5230'))
    for n in m.nodes:
        nx, ny = at(n)
        if n.hq >= 0:
            rect(surf, nx - 3, ny - 3, 7, 7, C['ink'])
            rect(surf, nx - 2, ny - 2, 5, 5, SIDES[n.hq]['main'])
        elif n.barracks:
            rect(surf, nx - 2, ny - 2, 5, 5, pygame.Color('#8a5a00'))
            rect(surf, nx - 1, ny - 1, 3, 3, C['highlight'])
        else:
            rect(surf, nx - 1, ny - 1, 3, 3, C['ink'])
            rect(surf, nx, ny, 1, 1, C['white'])


class ChooseMap:
    def __init__(self, app):
        self.app = app
        names = [m.path for m in app.maps]
        self.sel = names.index(S['map']) if S['map'] in names else 0
        sound.music('title')

    def key(self, k):
        maps = self.app.maps
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % (len(maps) + 1)
            sound.play('cursor')
        elif k == 'b':
            sound.play('back')
            self.app.title()
        elif k == 'e':
            if self.sel == len(maps):
                sound.play('select')
                self.app.title()
            elif map_problems(maps[self.sel]):
                sound.play('error')
            else:
                sound.play('select')
                S['map'] = maps[self.sel].path
                save()
                self.app.setup()

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        maps, rows = self.app.maps, len(self.app.maps) + 1
        surf.fill(C['olive_dark'])
        rect(surf, 0, 0, SW, 16, C['olive'])
        text(surf, 'CHOOSE A BATTLEFIELD', SW / 2, 5, C['highlight'], 1, 'c', C['ink'])
        shown = 14
        top = max(0, min(rows - shown, self.sel - 6))
        box(surf, 4, 20, 104, shown * 13 + 6)
        for k in range(min(shown, rows - top)):
            i, y = top + k, 24 + k * 13
            on = i == self.sel
            if on:
                rect(surf, 7, y - 1, 98, 11, C['highlight'])
            label = '< BACK' if i == len(maps) else maps[i].name
            text(surf, label[:16], 10, y + 1, C['ink'] if on else C['olive_dark'])
        if self.sel == len(maps):
            box(surf, 112, 20, 204, 126)
            text(surf, 'BACK TO TITLE', 214, 80, C['ink'], 1, 'c')
            return
        m = maps[self.sel]
        box(surf, 112, 20, 204, 126)
        mini_map(surf, m, 115, 23, 198, 120)
        box(surf, 112, 150, 204, 86)
        text(surf, m.name, 118, 155, C['ink'])
        n = len(m.nodes)
        text(surf, 'LARGE' if n >= 24 else 'MEDIUM' if n >= 15 else 'SMALL', SW - 10, 155, C['dim'], 1, 'r')
        problem = map_problems(m)
        blurb = f"CAN'T BE PLAYED YET: {problem[0]}. FIX IT IN THE MAP EDITOR." if problem else m.blurb
        for k, line in enumerate(wrap(blurb, 32)[:4]):
            text(surf, line, 118, 167 + k * 9, C['red'] if problem else C['dim'])
        bridges = sum(e.bridge for e in m.links)
        text(surf, f'{n} OUTPOSTS · {sum(x.barracks for x in m.nodes)} BARRACKS', 118, 207, C['ink'])
        text(surf, f"{sum(e.kind == 'river' for e in m.links)} RIVER CROSSINGS · {bridges} BRIDGE{'' if bridges == 1 else 'S'}", 118, 217, C['ink'])


class ListScreen:
    """A box of settings over the title backdrop: UP/DOWN pick, LEFT/RIGHT change, ENTER does."""
    title_text, sub = '', None

    def __init__(self, app):
        self.app, self.sel = app, 0
        sound.music('title')

    def items(self):
        return []

    def back(self):
        self.app.title()

    def key(self, k):
        items = self.items()
        it = items[self.sel]
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(items)
            sound.play('cursor')
        elif k in 'lr' and it.get('adj'):
            it['adj'](-1 if k == 'l' else 1)
            save()
            sound.play('adjust')
        elif k == 'e':
            if it.get('f'):
                sound.play('select')
                it['f']()
            elif it.get('adj'):
                it['adj'](1)
                save()
                sound.play('adjust')
        elif k == 'b':
            sound.play('back')
            self.back()

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        self.app.backdrop.draw(surf, now, pygame.Color(12, 15, 8, 140))
        items = self.items()
        self.sel = min(self.sel, len(items) - 1)
        w, h = 240, len(items) * 14 + 34
        x, y = (SW - w) // 2, (SH - h) // 2
        box(surf, x, y, w, h)
        rect(surf, x + 2, y + 2, w - 4, 14, C['olive'])
        text(surf, self.title_text, SW / 2, y + 5, C['white'], 1, 'c', C['ink'])
        for k, it in enumerate(items):
            yy = y + 22 + k * 14
            if k == self.sel:
                rect(surf, x + 3, yy - 2, w - 6, 12, C['highlight'])
            text(surf, it['l'], x + 10, yy, C['ink'])
            if it.get('val'):
                text(surf, it['val'](), x + w - 8, yy, C['ink'], 1, 'r')
        if self.sub:
            text(surf, self.sub, SW / 2, y + h + 6, C['white'], 1, 'c', C['ink'])


def choice(label, key, options, names=None):
    """A setting that cycles through options with LEFT/RIGHT."""
    names = names or {}
    return {'l': label, 'val': lambda: f"◀ {names.get(S[key], str(S[key]).upper())} ▶",
            'adj': lambda d: S.__setitem__(key, cycle(options, S[key], d))}


class Setup(ListScreen):
    sub = 'LEFT/RIGHT TO CHANGE'

    def __init__(self, app):
        super().__init__(app)
        self.title_text = app.chosen_map().name.upper()
        self.sel = len(self.items()) - 2          # start on START BATTLE!

    def items(self):
        out = [choice('MODE', 'mode', ['cpu', 'hot'], {'cpu': 'PLAYER VS CPU', 'hot': 'PLAYER VS PLAYER'})]
        if S['mode'] == 'cpu':
            out.append(choice('CPU LEVEL', 'cpu', ['normal', 'hard']))
        out += [choice('FOG OF WAR', 'fog', ['off', 'fog', 'blackout']),
                choice('TURN TIMER', 'timer', [0, 30, 60, 90], {0: 'OFF', 30: '30S', 60: '60S', 90: '90S'}),
                choice('BATTLE SCENES', 'anim', ['full', 'fast', 'off']),
                {'l': 'START BATTLE!', 'f': self.app.start_battle},
                {'l': 'BACK', 'f': self.back}]
        return out

    def back(self):
        self.app.choose_map(S['mode'])


class Options(ListScreen):
    title_text = 'OPTIONS'

    def __init__(self, app):
        super().__init__(app)
        self.remembered = learn.load()['games']      # battles Hard remembers against you (learn.py)
        self.erase_armed = False

    def key(self, k):
        if k != 'e':
            self.erase_armed = False                 # moving away cancels "ENTER AGAIN TO ERASE"
        super().key(k)

    def items(self):
        flip = lambda key: {'l': key[0], 'val': lambda: '◀ ON ▶' if S[key[1]] else '◀ OFF ▶', 'adj': lambda d: S.__setitem__(key[1], not S[key[1]])}
        volume = lambda label, key: {'l': label, 'val': lambda: f'◀ {S[key]} ▶', 'adj': lambda d: S.__setitem__(key, max(0, min(10, S[key] + d)))}

        def toggle_full(d):
            S['fullscreen'] = not S['fullscreen']
            self.app.apply_fullscreen()

        def memory():
            if self.erase_armed:
                return 'ENTER AGAIN TO ERASE'
            n = self.remembered
            return f"{n} BATTLE{'' if n == 1 else 'S'}" if n else 'EMPTY'

        def erase():                        # ENTER once arms it, ENTER again makes Hard forget
            if self.erase_armed:
                learn.forget()
                self.remembered = 0
            self.erase_armed = not self.erase_armed
        return [flip(('SOUND EFFECTS', 'sound')), volume('EFFECTS VOLUME', 'sfx_volume'),
                flip(('MUSIC', 'music')), volume('MUSIC VOLUME', 'music_volume'),
                choice('BATTLE SCENES', 'anim', ['full', 'fast', 'off']),
                {'l': 'FULL SCREEN', 'val': lambda: '◀ ON ▶' if S['fullscreen'] else '◀ OFF ▶', 'adj': toggle_full},
                {'l': "HARD'S MEMORY", 'val': memory, 'f': erase},
                {'l': 'BACK', 'f': self.back}]
