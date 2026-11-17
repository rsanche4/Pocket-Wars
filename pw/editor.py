"""The map editor and the list of your maps. Maps are saved as files in maps/ (see data.py for the format).

The map is edited as its text drawing (`art`), one character per spot: outposts on even rows and columns,
links between them, diagonals on odd rows and odd columns. ENTER cycles what is on a spot; HQs are moved by
picking them up. With MIRROR on, every change is copied to the opposite side, turned around.
"""
import math
import os
import random
import pygame

from . import sound
from .data import ROOT, parse_map, over_water, map_problems, reachable, save_map, default_of, reset_map, load_maps, \
    missing_defaults, restore_defaults
from .mapgen import generate, blank_art, OPTIONS, DEFAULTS
from .gfx import C, SIDES, SW, SH, THEMES, rect, box, text, ellipse, digits
from .menus import map_card

OUTPOST_CYCLE = [' ', 'o', 'G']
ACROSS_CYCLE, DOWN_CYCLE, DIAGONAL_CYCLE = [' ', '-', '~', '='], [' ', '|', '~', '='], [' ', '\\', '/', 'X']
NAMES = ['MY MAP', 'SKIRMISH', 'BLOCKADE', 'RIVER RUN', 'HILL FIGHT', 'SANDBOX', 'BACKYARD', 'OPERATION']
THEME_LIST = ['grass', 'desert', 'beach', 'snow']


def is_outpost(y, x):
    return y % 2 == 0 and x % 2 == 0


def side_name(ch):
    return 'GREEN' if ch == 'H' else 'TAN'


class Editor:
    def __init__(self, app, m=None, demo=False, art=None, mirror=True, at=(0, 0)):
        self.app, self.demo = app, demo
        rows = art or (m.art if m else blank_art(5, 3))
        width = max(len(r) for r in rows)
        self.art = [list(r.ljust(width)) for r in rows]
        self.name = m.name if m else f"MY MAP {free_number(app.maps if app else [], 'MY MAP')}"
        self.theme = m.theme if m else 'grass'
        self.path = m.path if m else ''           # its file in maps/ ('' until first saved)
        self.blurb = m.blurb if m else 'A custom battlefield.'
        self.mirror, (self.cy, self.cx) = mirror, at
        self.menu, self.menu_title, self.msel, self.msg, self.carry = None, '', 0, None, None
        self.fix_hq()
        self.saved = self.snapshot()
        if not demo:
            sound.music('title')

    # ---------- the grid ----------
    @property
    def w(self):
        return len(self.art[0])

    @property
    def h(self):
        return len(self.art)

    def mirror_of(self, y, x):
        return self.h - 1 - y, self.w - 1 - x

    def snd(self, name):
        if not self.demo:
            sound.play(name)

    def strings(self):
        return [''.join(r).rstrip() for r in self.art]

    def snapshot(self):
        return (self.name, self.theme, tuple(self.strings()))

    def as_map(self):
        return parse_map({'name': self.name, 'theme': self.theme, 'art': [''.join(r) for r in self.art]})

    def cycle(self):
        """ENTER on a spot: outposts go none / outpost / barracks, links go none / road / river / bridge.
        HQs are never part of a cycle: ENTER on one picks it up."""
        y, x = self.cy, self.cx
        cur = self.art[y][x]
        if is_outpost(y, x) and cur in 'Hh':
            self.pick()
            return
        options = OUTPOST_CYCLE if is_outpost(y, x) else ACROSS_CYCLE if y % 2 == 0 else DOWN_CYCLE if x % 2 == 0 else DIAGONAL_CYCLE
        new = options[(options.index(cur) + 1) % len(options) if cur in options else 1]
        self.art[y][x] = new
        my, mx = self.mirror_of(y, x)
        if self.mirror and (my, mx) != (y, x) and self.art[my][mx] not in 'Hh':
            self.art[my][mx] = new
        self.snd('place')

    def pick(self):
        self.carry = (self.art[self.cy][self.cx], self.cy, self.cx)
        self.msg = None
        self.snd('select')

    def drop(self):
        ch, oy, ox = self.carry
        y, x, other = self.cy, self.cx, 'h' if ch == 'H' else 'H'
        my, mx = self.mirror_of(y, x)
        if (y, x) == (oy, ox):
            self.carry = None
            self.snd('back')
            return
        problem = ('DROP IT ON AN OUTPOST SPOT' if not is_outpost(y, x) else
                   f'THAT IS THE {side_name(other)} HQ' if self.art[y][x] == other else
                   'THE CENTRE CANNOT BE AN HQ' if self.mirror and (my, mx) == (y, x) else None)
        if problem:
            self.msg = problem
            self.snd('error')
            return
        self.art[oy][ox], self.art[y][x] = 'o', ch
        if self.mirror:                 # the other HQ moves to the matching spot
            for r in self.art:
                for c in range(len(r)):
                    if r[c] == other:
                        r[c] = 'o'
            self.art[my][mx] = other
        self.carry = None
        self.snd('place')

    def fix_hq(self):
        """Always exactly one HQ per side."""
        spots = [(r, c) for r in range(0, self.h, 2) for c in range(0, self.w, 2)]
        for ch in 'Hh':
            for r, c in [s for s in spots if self.art[s[0]][s[1]] == ch][1:]:
                self.art[r][c] = 'o'
        find = lambda ch: next((s for s in spots if self.art[s[0]][s[1]] == ch), None)
        if not find('H'):
            t = find('h')
            m = t and self.mirror_of(*t)
            r, c = m if m and m != t else next(s for s in spots if self.art[s[0]][s[1]] != 'h')
            self.art[r][c] = 'H'
        if not find('h'):
            t = find('H')
            m = self.mirror_of(*t)
            r, c = m if m != t and self.art[m[0]][m[1]] != 'H' else next(s for s in reversed(spots) if self.art[s[0]][s[1]] != 'H')
            self.art[r][c] = 'h'

    def mirror_all(self):
        """Copy the first half onto the second, turned around."""
        for y in range(self.h):
            for x in range(self.w):
                my, mx = self.mirror_of(y, x)
                if my * self.w + mx > y * self.w + x:
                    ch = self.art[y][x]
                    self.art[my][mx] = 'h' if ch == 'H' else 'H' if ch == 'h' else ch
        self.fix_hq()

    def resize(self, dc, dr):
        cols, rows = (self.w + 1) // 2 + dc, (self.h + 1) // 2 + dr
        if not (3 <= cols <= 9 and 2 <= rows <= 7):
            self.snd('error')
            return
        new = [list(r) for r in blank_art(cols, rows)]
        for r in range(len(new)):
            for c in range(len(new[0])):
                if r < self.h and c < self.w:
                    new[r][c] = self.art[r][c]
                elif new[r][c] in 'Hh':
                    new[r][c] = 'o'
        self.art = new
        if self.mirror:
            self.mirror_all()
        self.fix_hq()
        self.cx, self.cy = min(self.cx, self.w - 1), min(self.cy, self.h - 1)

    def save(self):
        self.path = save_map(self.name, self.theme, self.strings(), self.path, self.blurb)
        self.saved = self.snapshot()
        problem = map_problems(self.as_map())
        self.msg = f'SAVED, BUT NOT PLAYABLE YET: {problem[0]}' if problem else 'SAVED: PLAY IT FROM CHOOSE A BATTLEFIELD'
        self.snd('save')

    # ---------- the menu ----------
    def open_menu(self):
        def rename(d):
            base = self.name.rsplit(' ', 1)
            number = base[1] if len(base) == 2 and base[1].isdigit() else '1'
            current = base[0] if base[0] in NAMES else NAMES[0]
            self.name = f'{NAMES[(NAMES.index(current) + d) % len(NAMES)]} {number}'

        def theme(d):
            self.theme = THEME_LIST[(THEME_LIST.index(self.theme) + d) % len(THEME_LIST)]

        def mirror(d):
            self.mirror = not self.mirror
            if self.mirror:
                self.mirror_all()

        reset = [{'l': 'RESET TO DEFAULT', 'f': self.ask_reset}] if default_of(self.path) else []    # built-in maps only
        self.show_menu('MAP EDITOR', [
            {'l': 'HOW IT WORKS', 'f': lambda: self.app.editor_help(self)},
            {'l': 'SAVE', 'f': self.save},
            {'l': 'WIDTH', 'val': lambda: f'◀ {(self.w + 1) // 2} ▶', 'adj': lambda d: self.resize(d, 0)},
            {'l': 'HEIGHT', 'val': lambda: f'◀ {(self.h + 1) // 2} ▶', 'adj': lambda d: self.resize(0, d)},
            {'l': 'THEME', 'val': lambda: f'◀ {self.theme.upper()} ▶', 'adj': theme},
            {'l': 'MIRROR EDITS', 'val': lambda: '◀ ON ▶' if self.mirror else '◀ OFF ▶', 'adj': mirror},
            {'l': 'NAME', 'val': lambda: f'◀ {self.name} ▶', 'adj': rename}] + reset + [
            {'l': 'DELETE MAP', 'dis': not self.path, 'f': self.ask_delete},
            {'l': 'EXIT EDITOR', 'f': self.leave},
            {'l': 'BACK TO MAP', 'f': lambda: None}])

    def show_menu(self, title, items):
        self.menu, self.menu_title, self.msel = items, title, 0

    def ask_reset(self):
        def reset():
            d = reset_map(self.path)
            width = max(len(r) for r in d['art'])
            self.art = [list(r.ljust(width)) for r in d['art']]
            self.name, self.theme, self.carry = d['name'], d.get('theme', 'grass'), None
            self.blurb = d.get('blurb', self.blurb)
            self.cy, self.cx = min(self.cy, self.h - 1), min(self.cx, self.w - 1)
            self.saved = self.snapshot()
            self.msg = 'BACK TO HOW IT CAME WITH THE GAME'
            self.snd('save')
        self.show_menu(f'RESET {self.name.upper()}?', [
            {'l': 'NO, KEEP MY CHANGES', 'f': lambda: None},
            {'l': 'YES, PUT THE ORIGINAL BACK', 'f': reset}])

    def ask_delete(self):
        def delete():
            os.remove(os.path.join(ROOT, self.path))
            self.app.map_editor()
        self.show_menu('DELETE THIS MAP?', [{'l': 'NO', 'f': lambda: None}, {'l': 'YES, DELETE IT', 'f': delete}])

    def leave(self):
        if self.snapshot() == self.saved:
            self.app.map_editor()
            return
        self.show_menu('LEAVE WITHOUT SAVING?', [
            {'l': 'SAVE AND EXIT', 'f': lambda: (self.save(), self.app.map_editor())},
            {'l': 'EXIT WITHOUT SAVING', 'f': self.app.map_editor},
            {'l': 'KEEP EDITING', 'f': lambda: None}])

    # ---------- keys ----------
    def key(self, k):
        if self.menu:
            items = self.menu
            it = items[self.msel]
            if k in 'ud':
                self.msel = (self.msel + (-1 if k == 'u' else 1)) % len(items)
                self.snd('cursor')
            elif k in 'lr' and it.get('adj'):
                it['adj'](-1 if k == 'l' else 1)
                self.snd('adjust')
            elif k == 'e':
                if it.get('dis'):
                    self.snd('error')
                elif not it.get('f') and it.get('adj'):
                    it['adj'](1)
                    self.snd('adjust')
                else:
                    self.snd('select')
                    self.menu = None
                    it['f']()
            elif k == 'b':
                self.menu = None
                self.snd('back')
            return
        self.msg = None
        if k == 'u':
            if self.cy == 0:
                if not self.carry:
                    self.cy = -1               # up from the top row: the MENU button
            elif self.cy > 0:
                self.cy -= 1
            self.snd('map_cursor')
        elif k == 'd' and self.cy < self.h - 1:
            self.cy += 1
            self.snd('map_cursor')
        elif k == 'l' and self.cy >= 0 and self.cx > 0:
            self.cx -= 1
            self.snd('map_cursor')
        elif k == 'r' and self.cy >= 0 and self.cx < self.w - 1:
            self.cx += 1
            self.snd('map_cursor')
        elif k == 'e':
            if self.carry:
                self.drop()
            elif self.cy < 0:
                self.open_menu()
                self.snd('open')
            else:
                self.cycle()
        elif k == 'b':
            if self.carry:
                self.carry = None
                self.snd('back')
            else:
                self.open_menu()
                self.snd('open')

    def update(self, now, dt):
        pass

    # ---------- drawing ----------
    def draw(self, surf, now):
        cols, rows = (self.w + 1) // 2, (self.h + 1) // 2
        th = THEMES[self.theme]
        surf.fill(C['olive_dark'])
        step = int(min(296 / max(1, cols - 1 + .6), 176 / max(1, rows - 1 + .8)))
        gw, gh = (cols - 1) * step, (rows - 1) * step
        ox, oy = round((SW - gw) / 2), round(34 + (176 - gh) / 2)
        ground = th['water'] if self.theme == 'beach' else th['base']
        rect(surf, ox - step / 2 + 2, oy - step / 2 + 6, gw + step - 4, gh + step - 12, ground)
        nx, ny = lambda c: ox + c * step, lambda r: oy + r * step
        blink = int(now / .25) % 2

        def line(x1, y1, x2, y2, ch):
            n = max(abs(x2 - x1), abs(y2 - y1))
            for k in range(n + 1):
                x, y = round(x1 + (x2 - x1) * k / n), round(y1 + (y2 - y1) * k / n)
                if ch == '~':
                    if k % 3 == 0:
                        rect(surf, x - 1, y - 1, 3, 3, th['water_edge'] if self.theme == 'beach' else th['water'])
                elif ch == '=':
                    rect(surf, x - 2, y - 2, 5, 5, pygame.Color('#6b4a2b'))
                    if k % 3 == 0:
                        rect(surf, x - 2, y - 2, 5, 1, pygame.Color('#c99a5c'))
                else:
                    rect(surf, x - 1, y - 1, 3, 3, th['road'])

        for y in range(self.h):
            for x in range(self.w):
                ch = self.art[y][x]
                if ch == ' ':
                    continue
                if y % 2 == 0 and x % 2 == 1:
                    line(nx((x - 1) // 2), ny(y // 2), nx((x + 1) // 2), ny(y // 2), ch)
                elif y % 2 == 1 and x % 2 == 0:
                    line(nx(x // 2), ny((y - 1) // 2), nx(x // 2), ny((y + 1) // 2), ch)
                elif y % 2 == 1:
                    if ch in '\\X':
                        line(nx((x - 1) // 2), ny((y - 1) // 2), nx((x + 1) // 2), ny((y + 1) // 2), '-')
                    if ch in '/X':
                        line(nx((x + 1) // 2), ny((y - 1) // 2), nx((x - 1) // 2), ny((y + 1) // 2), '-')

        def hq(px, py, side, alpha=255):
            layer = pygame.Surface((16, 12), pygame.SRCALPHA)
            ellipse(layer, 8, 6, 7, 5, C['ink'])
            ellipse(layer, 8, 6, 6, 4, SIDES[side]['main'])
            text(layer, 'HQ', 3, 3, C['white'])
            layer.set_alpha(alpha)
            surf.blit(layer, (px - 8, py - 6))

        for y in range(0, self.h, 2):
            for x in range(0, self.w, 2):
                ch, sx, sy = self.art[y][x], nx(x // 2), ny(y // 2)
                if ch == ' ':
                    rect(surf, sx - 1, sy - 1, 3, 3, pygame.Color(0, 0, 0, 90))
                elif ch in 'Hh':
                    hq(sx, sy, 0 if ch == 'H' else 1, 90 if self.carry and (self.carry[0] == ch or self.mirror) else 255)
                elif ch == 'G':
                    ellipse(surf, sx, sy, 7, 5, C['ink'])
                    ellipse(surf, sx, sy, 6, 4, pygame.Color('#d8c79e'))
                    digits(surf, '+1', sx - 3, sy - 2, C['ink'])
                else:
                    ellipse(surf, sx, sy, 5, 3, C['ink'])
                    ellipse(surf, sx, sy, 4, 2, C['paper'])

        if self.cy >= 0:               # the cursor: corners around the spot (an outpost, a link, or a diagonal)
            y, x = self.cy, self.cx
            cx = nx(x // 2) if x % 2 == 0 else (nx((x - 1) // 2) + nx((x + 1) // 2)) / 2
            cy = ny(y // 2) if y % 2 == 0 else (ny((y - 1) // 2) + ny((y + 1) // 2)) / 2
            s = 9 if blink else 8
            for ax, ay, dx, dy in ((cx - s, cy - s, 1, 1), (cx + s, cy - s, -1, 1), (cx - s, cy + s, 1, -1), (cx + s, cy + s, -1, -1)):
                rect(surf, min(ax, ax + dx * 3), ay, 4, 1, C['highlight'])
                rect(surf, ax, min(ay, ay + dy * 3), 1, 4, C['highlight'])
            if self.carry:             # the HQ you're carrying floats over the cursor; mirror shows where the other lands
                side = 0 if self.carry[0] == 'H' else 1
                if self.mirror and is_outpost(y, x) and self.mirror_of(y, x) != (y, x):
                    my, mx = self.mirror_of(y, x)
                    hq(nx(mx // 2), ny(my // 2), 1 - side, 128)
                ellipse(surf, cx, cy + 2, 6, 2, pygame.Color(0, 0, 0, 90))
                hq(cx, cy - 9 + round(math.sin(now / .16)), side)

        rect(surf, 0, 0, SW, 13, C['olive'])
        text(surf, f'MAP EDITOR · {self.name}', 4, 3, C['highlight'], 1, 'l', C['ink'])
        text(surf, f"{cols}x{rows}{' · MIRROR' if self.mirror else ''}", SW - 4, 3, C['white'], 1, 'r')
        on_menu = self.cy < 0
        box(surf, SW / 2 - 34, 15, 68, 13, C['highlight'] if on_menu else None)
        text(surf, 'MENU', SW / 2, 18, C['ink'], 1, 'c')
        if on_menu and blink:
            text(surf, '▶', SW / 2 - 28, 18, C['ink'])
        self.draw_help(surf)
        if self.menu:
            self.draw_menu(surf)

    def draw_help(self, surf):
        rect(surf, 0, SH - 22, SW, 22, C['paper'])
        rect(surf, 0, SH - 22, SW, 1, C['ink'])
        y, x = self.cy, self.cx
        if self.carry:
            what = f'CARRYING {side_name(self.carry[0])} HQ · ENTER: DROP IT HERE'
        elif y < 0:
            what = 'ENTER: MENU (HOW IT WORKS, SAVE...)'
        else:
            ch = self.art[y][x]
            if is_outpost(y, x):
                what = (f'{side_name(ch)} HQ · ENTER: PICK IT UP TO MOVE IT' if ch in 'Hh' else
                        f"OUTPOST: {'NONE' if ch == ' ' else 'OUTPOST' if ch == 'o' else 'BARRACKS'} · ENTER: CHANGE")
            elif y % 2 == 1 and x % 2 == 1:
                what = f"DIAGONAL: {'NONE' if ch == ' ' else 'BRIDGE' if over_water(self.art, y, x) else 'ROAD'} · ENTER: CHANGE"
            else:
                what = f"LINK: {'NONE' if ch == ' ' else 'RIVER' if ch == '~' else 'BRIDGE' if ch == '=' else 'ROAD'} · ENTER: CHANGE"
        text(surf, what, 4, SH - 19, C['ink'])
        m = self.as_map()
        problems = map_problems(m)
        if self.msg:
            line, col = self.msg, C['olive']
        elif self.carry:
            line, col = 'ESC: PUT IT BACK', C['dim']
        elif problems:
            line, col = '! ' + problems[0], C['red']
        else:
            h0, h1 = (next(i for i, n in enumerate(m.nodes) if n.hq == p) for p in (0, 1))
            line = 'READY TO PLAY' if h1 in reachable(m, h0, roads_only=True) else 'NOTE: ONLY HELICOPTERS CAN REACH THE ENEMY'
            col = C['dim']
        text(surf, line, 4, SH - 9, col)

    def draw_menu(self, surf):
        items, w = self.menu, 230
        h = len(items) * 12 + 26
        x, y = (SW - w) // 2, (SH - h) // 2
        box(surf, x, y, w, h)
        rect(surf, x + 2, y + 2, w - 4, 14, C['olive'])
        text(surf, self.menu_title, SW / 2, y + 5, C['white'], 1, 'c', C['ink'])
        for k, it in enumerate(items):
            yy = y + 21 + k * 12
            if k == self.msel:
                rect(surf, x + 3, yy - 2, w - 6, 11, C['highlight'])
            text(surf, it['l'], x + 10, yy, C['grey'] if it.get('dis') else C['ink'])
            if it.get('val'):
                text(surf, it['val'](), x + w - 8, yy, C['ink'], 1, 'r')



def free_number(maps, base):
    """The first number n with no map called '<base> n' yet (so a new map gets a name of its own)."""
    taken = {m.name.upper() for m in maps}
    n = 1
    while f'{base} {n}' in taken:
        n += 1
    return n


# ---------------------------------------------------------------- the list of your maps
class MapList:
    def __init__(self, app, sel=0, msg=None):
        self.app, self.sel, self.msg = app, sel, msg
        sound.music('title')

    def rows(self):
        """What the list shows: (label, kind, map). Kinds: new, generate, map, restore, back."""
        rows = [('+ NEW MAP', 'new', None), ('+ GENERATE MAP', 'generate', None)]
        rows += [(m.name, 'map', m) for m in self.app.maps]               # every map can be opened and edited
        if missing_defaults():
            rows.append(('RESTORE DELETED', 'restore', None))
        return rows + [('< BACK', 'back', None)]

    def key(self, k):
        rows = self.rows()
        self.sel = min(self.sel, len(rows) - 1)
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(rows)
            self.msg = None
            sound.play('cursor')
        elif k == 'b':
            sound.play('back')
            self.app.title()
        elif k == 'e':
            sound.play('select')
            _, kind, m = rows[self.sel]
            if kind == 'new':
                self.app.edit_map(None)
            elif kind == 'generate':
                self.app.scene = Generator(self.app)
            elif kind == 'map':
                self.app.edit_map(m)
            elif kind == 'restore':
                restore_defaults()
                self.app.maps = load_maps()
                self.msg = 'THE BUILT-IN MAPS ARE BACK'
                sound.play('save')
            else:
                self.app.title()

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        rows = self.rows()
        self.sel = min(self.sel, len(rows) - 1)
        surf.fill(C['olive_dark'])
        rect(surf, 0, 0, SW, 16, C['olive'])
        text(surf, 'MAP EDITOR', SW / 2, 5, C['highlight'], 1, 'c', C['ink'])
        shown = 13
        top = max(0, min(len(rows) - shown, self.sel - 6))
        box(surf, 4, 20, 124, shown * 13 + 6)
        for k in range(min(shown, len(rows) - top)):
            i, y = top + k, 24 + k * 13
            if i == self.sel:
                rect(surf, 7, y - 1, 118, 11, C['highlight'])
            text(surf, rows[i][0][:19], 10, y + 1, C['ink'] if i == self.sel else C['olive_dark'])
        box(surf, 132, 20, 184, 198)
        _, kind, m = rows[self.sel]
        if kind == 'map':                         # no picture here: you see the layout once you open it
            h = map_card(surf, m, 135, 26, 178)
            lines = ['ENTER: OPEN IT TO SEE IT', '', 'ITS FILE (SEND IT TO SHARE):', os.path.basename(m.path)[:28]]
            if default_of(m.path):
                lines[1:2] = ['', 'BUILT-IN: RESET TO DEFAULT', 'IS IN THE EDITOR MENU.', '']
            for k, line in enumerate(lines):
                text(surf, line, 224, 30 + h + k * 10, C['ink'] if k == 0 else C['olive'] if k == len(lines) - 1 else C['dim'], 1, 'c')
        elif kind == 'new':
            lines = ['BUILD YOUR OWN', 'BATTLEFIELD.', '', 'ARROWS: MOVE OVER', 'OUTPOSTS AND LINKS', 'ENTER: CHANGE THEM', '',
                     'ENTER ON AN HQ PICKS IT', 'UP SO YOU CAN MOVE IT.', '', 'NEW TO IT? OPEN THE MENU', '(UP FROM THE TOP ROW)',
                     'AND PICK HOW IT WORKS.', '', 'MAPS ARE SAVED IN MAPS.']
            for k, line in enumerate(lines):
                text(surf, line, 224, 30 + k * 12, C['ink'] if k < 2 else C['olive'] if 9 < k < 13 else C['dim'], 1, 'c')
        elif kind == 'generate':
            lines = ['LET THE GAME MAKE ONE.', '', 'PICK THE SIZE, THEME,', 'RIVERS, ROADS AND', 'BARRACKS, AND IT BUILDS',
                     'A FAIR, READY TO PLAY', 'MAP. REROLL UNTIL YOU', 'LIKE IT, THEN SAVE IT', 'OR TWEAK IT IN THE EDITOR.']
            for k, line in enumerate(lines):
                text(surf, line, 224, 40 + k * 12, C['ink'] if k == 0 else C['dim'], 1, 'c')
        elif kind == 'restore':
            lines = ['SOME MAPS THAT CAME WITH', 'THE GAME WERE DELETED.', '', 'ENTER: PUT THEM BACK.', '',
                     *[n[:-5].upper()[:24] for n in missing_defaults()[:8]]]
            for k, line in enumerate(lines):
                text(surf, line, 224, 34 + k * 12, C['ink'] if k == 3 else C['dim'], 1, 'c')
        else:
            text(surf, 'BACK TO TITLE', 224, 110, C['ink'], 1, 'c')
        if self.msg:
            rect(surf, 132, 222, 184, 14, C['ink'])
            text(surf, self.msg, 224, 226, C['highlight'], 1, 'c')


# ---------------------------------------------------------------- the map generator screen
class Generator:
    """Settings on the left, a live preview of the map they make on the right (see mapgen.py)."""
    LABELS = {'size': 'SIZE', 'theme': 'THEME', 'rivers': 'RIVERS', 'roads': 'ROADS', 'barracks': 'BARRACKS',
              'diagonals': 'DIAGONALS'}

    def __init__(self, app):
        self.app, self.sel = app, len(OPTIONS)            # start on REROLL
        if not hasattr(app, 'gen_settings'):              # the settings are remembered while the game is open
            app.gen_settings = dict(DEFAULTS)
        self.settings = app.gen_settings
        self.seed = random.randrange(1 << 30)
        self.make()

    def make(self):
        self.d = generate(self.settings, self.seed, [m.name for m in self.app.maps])
        self.m = parse_map(self.d)

    def items(self):
        rows = []
        for key, values in OPTIONS.items():
            def adj(d, key=key, values=values):
                self.settings[key] = values[(values.index(self.settings[key]) + d) % len(values)]
                self.make()
            rows.append({'l': self.LABELS[key], 'val': f'◀ {self.settings[key]} ▶', 'adj': adj})
        return rows + [{'l': 'REROLL', 'f': self.reroll}, {'l': 'EDIT IT', 'f': self.edit},
                       {'l': 'SAVE IT', 'f': self.save}, {'l': '< BACK', 'f': self.back}]

    def reroll(self):
        self.seed = random.randrange(1 << 30)
        self.make()

    def edit(self):
        e = Editor(self.app, self.m)
        e.saved = None                                    # not saved yet: leaving the editor will ask
        self.app.scene = e

    def save(self):
        path = save_map(self.d['name'], self.d['theme'], self.d['art'], blurb=self.d['blurb'])
        self.app.maps = load_maps()
        at = next((k for k, m in enumerate(self.app.maps) if m.path == path), 0)
        self.app.scene = MapList(self.app, sel=at + 2, msg='SAVED! READY TO PLAY')

    def back(self):
        self.app.scene = MapList(self.app, sel=1)

    def key(self, k):
        items = self.items()
        it = items[self.sel]
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(items)
            sound.play('cursor')
        elif k in 'lr' and it.get('adj'):
            it['adj'](-1 if k == 'l' else 1)
            sound.play('adjust')
        elif k == 'e':
            if it.get('adj'):
                it['adj'](1)
                sound.play('adjust')
            else:
                sound.play('save' if it['f'] == self.save else 'select')
                it['f']()
        elif k == 'b':
            sound.play('back')
            self.back()

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        surf.fill(C['olive_dark'])
        rect(surf, 0, 0, SW, 16, C['olive'])
        text(surf, 'GENERATE MAP', SW / 2, 5, C['highlight'], 1, 'c', C['ink'])
        items = self.items()
        box(surf, 4, 20, 146, len(items) * 13 + 14)
        y = 24
        for k, it in enumerate(items):
            if k == len(OPTIONS):
                y += 6                                   # a little gap between the settings and the buttons
            if k == self.sel:
                rect(surf, 7, y - 1, 140, 11, C['highlight'])
            col = C['ink'] if k == self.sel else C['olive_dark']
            text(surf, it['l'], 10, y + 1, col)
            if it.get('val'):
                text(surf, it['val'], 144, y + 1, col, 1, 'r')
            y += 13
        box(surf, 154, 20, 162, 198)                  # what the map is like, not what it looks like
        text(surf, self.d['name'], 235, 26, C['ink'], 1, 'c')
        h = map_card(surf, self.m, 157, 38, 156)
        tips = ['◀ ▶ CHANGE A SETTING', 'REROLL: ANOTHER MAP', 'EDIT IT: SEE AND TWEAK IT', 'SAVE IT: READY TO PLAY']
        for k, line in enumerate(tips):
            text(surf, line, 235, 46 + h + k * 10, C['olive'], 1, 'c')


# ---------------------------------------------------------------- demos for the guides (the real editor, scripted)
def at(y, x):
    def move(e):
        e.cy, e.cx = y, x
    return move


def cycle(e):
    e.cycle()


DEMO_ART = ['H-o-G-o=o', '|\\| ~ |\\|', 'o=o-G-o-h']
DEMOS = {      # picture name: (how to make the editor, the steps it plays, one every 0.8 s)
    'ed_grid': (lambda: dict(art=blank_art(5, 2)),
                [at(y, x) for y, x in ((0, 0), (0, 1), (0, 2), (1, 2), (1, 3), (2, 4), (2, 5), (2, 6), (1, 7), (0, 8))]),
    'ed_outposts': (lambda: dict(art=blank_art(5, 2), mirror=False, at=(0, 4)), [cycle, cycle, cycle]),
    'ed_links': (lambda: dict(art=blank_art(5, 2), mirror=False, at=(0, 3)),
                 [cycle, cycle, cycle, cycle, at(1, 3), cycle, cycle, cycle, cycle]),
    'ed_hq': (lambda: dict(art=blank_art(5, 2)), [cycle, at(0, 1), at(0, 2), at(1, 2), at(2, 2), lambda e: e.drop()]),
    'ed_mirror': (lambda: dict(art=blank_art(5, 2), at=(0, 2)), [cycle, at(1, 1), cycle, at(0, 3), cycle]),
    'ed_menu': (lambda: dict(art=DEMO_ART),
                [lambda e: e.open_menu(), lambda e: setattr(e, 'msel', 1), lambda e: setattr(e, 'msel', 2),
                 lambda e: setattr(e, 'msel', 3)]),
    'editor': (lambda: dict(art=DEMO_ART), [at(0, x) for x in range(9)]),
}
_runs, _screen = {}, []


def draw_demo(key, panel, now):
    """Play a guide demo into a 292x100 panel: the editor drawn full size, cropped to the grid."""
    make, steps = DEMOS[key]
    run = _runs.get(key)
    if not run or now - run['t'] > 4:
        run = _runs[key] = {'ed': Editor(None, demo=True, **make()), 'i': 0, 't': now}
    while now - run['t'] >= .8:
        run['t'] += .8
        if run['i'] < len(steps):
            steps[run['i']](run['ed'])
        run['i'] += 1
        if run['i'] > len(steps) + 2:
            run = _runs[key] = {'ed': Editor(None, demo=True, **make()), 'i': 0, 't': now}
            break
    if not _screen:
        _screen.append(pygame.Surface((SW, SH)))
    run['ed'].draw(_screen[0], now)
    panel.blit(_screen[0], (0, 0), (14, 68, panel.get_width(), panel.get_height()))
