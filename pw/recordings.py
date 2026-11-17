"""Recordings: a battle saved as its map, its settings and every move (each fight with its dice), in recordings/.
Replaying the moves from the start rebuilds the battle exactly, so a file is small (tens of KB) and can be shared:
send it to a friend, who drops it in their recordings/ folder.

RECORD (in the battle setup) turns it on; the battle is saved when it ends, or when you quit it. Online, only the
host records (its game sees every move). RECORDINGS on the title lists them; Watch plays one back:
  arrows move the cursor over the map; ENTER jumps up to the playback bar: back a turn, back a phase, PLAY/STOP,
  next phase, next turn, and whose eyes you watch through (GREEN, TAN or ALL, when the battle had fog).
"""
import json
import os
import re
import subprocess
import sys
import time
import pygame

from . import sound, net
from .data import ROOT, parse_map
from .gfx import C, SIDES, SW, SH, rect, box, text, wrap, text_width, blit, unit_image
from .menu import Menu
from .play import Play, pausing, TOP, PHASE_NAMES
from .rules import Game, Unit
from .settings import S
from .stats import Stats

DIR = os.path.join(ROOT, 'recordings')
FORMAT = 1
MODES = {'cpu': 'VS CPU', 'hot': 'HOTSEAT', 'host': 'ONLINE', 'watch': 'CPU VS CPU'}


# ---------------------------------------------------------------------------------------------- saving and loading
def save(play):
    """Write the battle play has recorded; returns the file's path."""
    os.makedirs(DIR, exist_ok=True)
    g, s, m = play.g, play.settings, play.g.map
    players = {'cpu': ['YOU', f"CPU ({s.get('cpu', 'normal').upper()})"], 'hot': ['PLAYER 1', 'PLAYER 2'],
               'host': ['HOST', 'GUEST']}.get(s['mode'], ['CPU', 'CPU'])
    rec = {'format': FORMAT, 'game': net.game_id(), 'saved': time.strftime('%Y-%m-%d %H:%M'),
           'map': {'name': m.name, 'theme': m.theme, 'art': m.art, 'blurb': m.blurb},
           'mode': s['mode'], 'cpu': s.get('cpu'), 'fog': s['fog'], 'players': players,
           'turns': g.turn, 'winner': g.winner, 'resigned': g.resigned, 'moves': play.recording}
    name = re.sub(r'[^A-Za-z0-9 _-]', '', m.name).strip() or 'battle'
    path = os.path.join(DIR, f"{time.strftime('%Y-%m-%d %H-%M-%S')} {name}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rec, f, separators=(',', ':'))
    return path


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def listing():
    """[(path, recording, size in bytes)], newest first. Broken files are skipped."""
    out = []
    if os.path.isdir(DIR):
        for name in sorted(os.listdir(DIR), reverse=True):
            path = os.path.join(DIR, name)
            if name.lower().endswith('.json'):
                try:
                    rec = load(path)
                    if rec.get('format') == FORMAT and 'moves' in rec:
                        out.append((path, rec, os.path.getsize(path)))
                except (OSError, ValueError):
                    pass
    return out


def result_text(rec):
    w = rec.get('winner')
    if w is None:
        return 'UNFINISHED'
    loser = SIDES[1 - w]['name']
    return f"{SIDES[w]['name']} WON" + (f' ({loser} RESIGNED)' if rec.get('resigned') else '')


# ---------------------------------------------------------------------------------------------- the board at a moment
def snap(g):
    return {'units': [[(u.id, u.side, u.type, u.hp) for u in us] for us in g.units], 'turn': g.turn, 'cur': g.cur,
            'phase': g.phase, 'to_place': g.to_place, 'bought': g.bought, 'used': set(g.used), 'cleared': g.cleared,
            'winner': g.winner, 'resigned': g.resigned, 'next_id': list(g.next_id), 'seen': [set(g.seen[0]), set(g.seen[1])]}


def restore(g, s):
    g.units = [[Unit(*u) for u in us] for us in s['units']]
    g.turn, g.cur, g.phase, g.to_place, g.bought = s['turn'], s['cur'], s['phase'], s['to_place'], s['bought']
    g.used, g.cleared, g.winner, g.resigned = set(s['used']), s['cleared'], s['winner'], s['resigned']
    g.next_id, g.seen = list(s['next_id']), [set(s['seen'][0]), set(s['seen'][1])]


# ---------------------------------------------------------------------------------------------- the list
class RecordingList:
    """Every saved recording: ENTER on one to watch it (or delete it), or open the folder to share them."""
    def __init__(self, app, sel=0):
        self.app, self.items = app, listing()
        self.sel, self.menu = min(sel, len(self.items) + 1), None
        sound.music('title')

    def key(self, k):
        if self.menu:
            m = self.menu
            if k in 'ud':
                m.move(-1 if k == 'u' else 1)
                sound.play('cursor')
            elif k == 'b':
                self.menu = None
                sound.play('back')
            elif k == 'e':
                sound.play('select')
                self.menu = None
                m.items[m.sel]['f']()
            return
        rows = len(self.items) + 2
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % rows
            sound.play('cursor')
        elif k == 'b':
            sound.play('back')
            self.app.title()
        elif k == 'e':
            sound.play('select')
            if self.sel < len(self.items):
                path = self.items[self.sel][0]
                self.menu = Menu(os.path.basename(path)[:19].upper(), [
                    {'l': 'WATCH', 'f': lambda: self.app.watch(path)},
                    {'l': 'DELETE', 'f': lambda: self.ask_delete(path)},
                    {'l': 'CANCEL', 'f': lambda: None}])
            elif self.sel == len(self.items):
                os.makedirs(DIR, exist_ok=True)
                open_folder(DIR)
            else:
                self.app.title()

    def ask_delete(self, path):
        def delete():
            try:
                os.remove(path)
            except OSError:
                sound.play('error')
            self.items = listing()
            self.sel = min(self.sel, len(self.items) + 1)
        self.menu = Menu('DELETE THIS RECORDING?', [{'l': 'NO, KEEP IT', 'f': lambda: None},
                                                    {'l': 'YES, DELETE IT', 'f': delete}], sub="IT CAN'T BE UNDONE")

    def update(self, now, dt):
        pass

    def draw(self, surf, now):
        rows = [f"{rec['saved'][5:]} {rec['map']['name']}" for _, rec, _ in self.items] + ['OPEN FOLDER', '< BACK']
        surf.fill(C['olive_dark'])
        rect(surf, 0, 0, SW, 16, C['olive'])
        text(surf, 'RECORDINGS', SW / 2, 5, C['highlight'], 1, 'c', C['ink'])
        shown = 14
        top = max(0, min(len(rows) - shown, self.sel - 6))
        box(surf, 4, 20, 140, shown * 13 + 6)
        for k in range(min(shown, len(rows) - top)):
            i, y = top + k, 24 + k * 13
            if i == self.sel:
                rect(surf, 7, y - 1, 134, 11, C['highlight'])
            text(surf, rows[i][:22], 10, y + 1, C['ink'] if i == self.sel else C['olive_dark'])
        box(surf, 148, 20, 168, 216)
        x = 154
        if self.sel < len(self.items):
            path, rec, size = self.items[self.sel]
            lines = [(rec['map']['name'].upper(), C['ink']), (rec['saved'], C['dim']), ('', None),
                     (MODES.get(rec['mode'], rec['mode'].upper()) + (f" ({rec['cpu'].upper()})" if rec['mode'] == 'cpu' else ''),
                      C['ink']),
                     (f"GREEN: {rec['players'][0]}", SIDES[0]['dark']), (f"TAN: {rec['players'][1]}", SIDES[1]['dark']),
                     (f"FOG: {rec['fog'].upper()}", C['ink']), (f"TURNS: {rec['turns']}", C['ink']),
                     (result_text(rec), C['olive']), ('', None), (f'SIZE: {max(1, round(size / 1024))} KB', C['dim'])]
            if not net.same_stats(rec.get('game')):
                lines.append(('MADE WITH OTHER UNIT STATS:', C['red']))
                lines.append(('IT MAY NOT PLAY BACK RIGHT', C['red']))
            y = 26
            for line, col in lines:
                if line:
                    text(surf, line[:26], x, y, col)
                y += 11
            text(surf, 'ENTER: WATCH OR DELETE', x, 222, C['dim'])
        elif not self.items and self.sel == 0:
            for k, line in enumerate(wrap('NO RECORDINGS YET. TURN RECORD ON IN THE BATTLE SETUP, OR DROP A FRIEND\'S '
                                          'RECORDING FILE IN THE RECORDINGS FOLDER.', 26)):
                text(surf, line, x, 30 + k * 10, C['ink'])
        else:
            for k, line in enumerate(wrap('THE RECORDINGS FOLDER: SEND A FILE TO A FRIEND, OR DROP ONE OF THEIRS IN '
                                          'HERE TO WATCH IT.', 26)):
                text(surf, line, x, 30 + k * 10, C['ink'])
        if self.menu:
            self.menu.draw(surf, 0, SH, SIDES[0])


def open_folder(path):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])
    except OSError:
        sound.play('error')


# ---------------------------------------------------------------------------------------------- watching
BUTTONS = ['turn_back', 'back', 'play', 'next', 'turn_next', 'view']
SAYS = {'turn_back': 'BACK A WHOLE TURN', 'back': 'BACK ONE PHASE', 'next': 'NEXT PHASE', 'turn_next': 'NEXT TURN'}
VIEWS = ['green', 'tan', 'all']


class Watch(Play):
    """The battle screen, playing a recording. The battle is cut into phases (a side's gather, march or attack);
    each phase's board is worked out up front, so jumping anywhere is instant, and PLAY animates a phase's moves."""
    watching = True

    def __init__(self, app, rec):
        self.rec = rec
        self.view, self.focus, self.button = 'green', 'map', 2
        self.playing = False
        m = parse_map(rec['map'])
        super().__init__(app, m, {'mode': 'watch', 'cpu': 'normal', 'fog': rec['fog'], 'timer': 0, 'anim': S['anim']})
        self.moves = rec['moves']
        self.cut_up(m)                   # (sets phases and final)
        self.go(0, quiet=True)           # (sets at: the phase on screen)

    def cut_up(self, m):
        """Run the whole battle once, instantly, noting the board where each phase starts."""
        g = Game(m, self.rec['fog'])
        key = lambda: (g.turn, g.cur, g.phase)
        self.phases = [(snap(g), 0, key())]
        for k, move in enumerate(self.moves):
            action = g.decode_move(move)
            try:
                g.do(action)
            except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                self.moves = self.moves[:k]                   # a broken or mismatched recording: stop there
                break
            if key() != self.phases[-1][2]:
                self.phases.append((snap(g), k + 1, key()))
        if self.phases[-1][1] != len(self.moves):             # stopped part-way through a phase
            self.phases.append((snap(g), len(self.moves), key()))
        self.final = g

    def turn_started(self):          # (nothing starts by itself: the recording drives the battle)
        pass

    def viewer_side(self):
        if not self.g.fog or self.view == 'all':
            return None
        return VIEWS.index(self.view)

    # ------------------------------------------------------------------ moving through the recording
    def go(self, i, quiet=False):
        """Show the board at the start of phase i."""
        self.halt()
        self.at = max(0, min(len(self.phases) - 1, i))
        restore(self.g, self.phases[self.at][0])
        self.ended = False
        if self.menu and not self.menu.pauses:
            self.menu = None
        if not quiet and self.g.phase != 'over':
            self.phase_banner()

    def halt(self):
        """Stop anything moving (the board stays as it is)."""
        self.script = self.wait = self.cutin = self.before = None
        self.field.march = self.trail = None
        self.field.drops, self.banner = [], None
        self.playing = False

    def phase_banner(self):
        g = self.g
        self.say_banner(PHASE_NAMES[g.phase], C.get('phase_' + g.phase, C['highlight']),
                        f"{SIDES[g.cur]['name']} · TURN {g.turn}")

    def turn_of(self, i):
        return self.phases[i][2][0]

    def press(self, name):
        last = len(self.phases) - 1
        if name == 'play':
            if self.playing:
                self.halt()
            else:
                self.play_from(0 if self.at >= last else self.at)
        elif name == 'back':
            self.go(self.at - 1)
        elif name == 'next':
            self.go(self.at + 1)
        elif name == 'turn_back':
            start = self.at
            while start > 0 and self.turn_of(start - 1) == self.turn_of(self.at):
                start -= 1
            if start == self.at and start > 0:        # already at the start of this turn: the turn before
                start -= 1
                while start > 0 and self.turn_of(start - 1) == self.turn_of(self.at - 1):
                    start -= 1
            self.go(start)
        elif name == 'turn_next':
            i = self.at
            while i < last and self.turn_of(i) == self.turn_of(self.at):
                i += 1
            self.go(i)
        elif name == 'view':
            if self.g.fog:
                self.view = VIEWS[(VIEWS.index(self.view) + 1) % 3]
            else:
                sound.play('error')
                return
        sound.play('adjust' if name == 'view' else 'select')

    def play_from(self, i):
        self.go(i)
        self.run(self.playback())
        self.playing = True

    def playback(self):
        """PLAY: each phase in turn, its moves animated, with a moment to take it in."""
        while self.at < len(self.phases) - 1:
            yield 1.0
            start, end = self.phases[self.at][1], self.phases[self.at + 1][1]
            for move in self.moves[start:end]:
                action = self.g.decode_move(move)
                if action:
                    yield from self.perform(action)
            yield .5
            self.at += 1
            restore(self.g, self.phases[self.at][0])
            if self.g.phase != 'over':
                self.phase_banner()
        self.playing = False

    def game_over(self):             # the end of the recording
        self.ended = True
        self.playing = False
        self.menu = self.end_menu()

    def end_menu(self):
        w = self.final.winner
        return Menu(f"{SIDES[w]['name']} WINS!" if w is not None else 'END OF RECORDING', [
            {'l': 'BATTLE STATS', 'f': self.show_stats},
            {'l': 'WATCH AGAIN', 'f': lambda: self.play_from(0)},
            {'l': 'KEEP LOOKING', 'f': lambda: None},
            {'l': 'BACK TO RECORDINGS', 'f': self.app.recordings}],
            sub=result_text(self.rec) if w is None or self.final.resigned else None, win=w)

    def show_stats(self):
        def back():
            self.app.scene = self
        self.app.scene = Stats(self.app, self.final, back)

    def open_menu(self):
        self.menu = pausing(Menu('RECORDING', [
            {'l': 'RESUME', 'f': lambda: None},
            {'l': 'BATTLE STATS', 'f': self.show_stats},
            {'l': 'BACK TO RECORDINGS', 'f': self.app.recordings},
            {'l': 'MAIN MENU', 'f': self.app.main_menu}], sub='STATS SHOW THE WHOLE BATTLE'))

    # ------------------------------------------------------------------ keys
    def key(self, k):
        if self.menu or (self.cutin and self.focus == 'map'):      # (on the map, ENTER/ESC skip a battle scene)
            return super().key(k)
        if self.focus == 'bar':                                     # (the buttons work even during one)
            if k in 'lr':
                self.button = (self.button + (1 if k == 'r' else -1)) % len(BUTTONS)
                sound.play('cursor')
            elif k == 'e':
                self.press(BUTTONS[self.button])
            elif k in 'bdu':
                self.focus = 'map'
                sound.play('back')
            return
        if k in 'udlr':
            j = self.node_toward(k)
            if j is not None:
                self.cur = j
                sound.play('map_cursor')
        elif k == 'e':
            self.focus = 'bar'
            sound.play('select')
        elif k == 'b':
            sound.play('open')
            self.open_menu()

    def hint(self):
        if self.focus == 'bar':
            b = BUTTONS[self.button]
            if b == 'view' and not self.g.fog:
                return 'NO FOG IN THIS BATTLE: YOU SEE IT ALL'
            say = ('STOP' if self.playing else 'PLAY, PHASE BY PHASE') if b == 'play' else SAYS.get(b) or \
                'SEE AS GREEN, TAN OR ALL'
            return f'ENTER: {say} · ESC: MAP'
        return 'ARROWS: LOOK · ENTER: PLAYBACK · ESC: MENU'

    # ------------------------------------------------------------------ the playback bar (in place of the top bar)
    def draw_top(self, surf, now, vis):
        g, p = self.g, self.g.cur
        rect(surf, 0, 0, SW, TOP, C['olive'])
        rect(surf, 0, TOP - 1, SW, 1, C['olive_dark'])
        blit(surf, unit_image('icons', 'soldier', p), 3, 1)
        text(surf, f'T{g.turn}', 14, 3, SIDES[p]['main'], 1, 'l', C['ink'])
        phase = PHASE_NAMES[g.phase] if g.phase != 'over' else 'END'
        x = 14 + text_width(f'T{g.turn}') + 4
        tag = C['grey'] if g.phase == 'over' else C.get('phase_' + g.phase, C['highlight'])
        rect(surf, x - 2, 1, text_width(phase) + 4, TOP - 3, tag)
        text(surf, phase, x, 3, C['ink'])
        bx = 112
        for k, b in enumerate(BUTTONS[:5]):
            self.draw_button(surf, bx + k * 15, b, k == self.button and self.focus == 'bar', now)
        text(surf, f'{self.at + 1}/{len(self.phases)}', bx + 5 * 15 + 4, 3, C['white'], 1, 'l', C['ink'])
        label = {'green': 'SEE: GREEN', 'tan': 'SEE: TAN', 'all': 'SEE: ALL'}[self.view] if g.fog else 'NO FOG'
        w = text_width(label) + 6
        on = self.button == 5 and self.focus == 'bar'
        rect(surf, SW - w - 2, 1, w, TOP - 3, C['highlight'] if on else C['paper'])
        col = SIDES[VIEWS.index(self.view)]['dark'] if g.fog and self.view != 'all' else C['ink']
        text(surf, label, SW - w + 1, 3, col)

    def draw_button(self, surf, x, name, on, now):
        rect(surf, x, 1, 13, TOP - 3, C['highlight'] if on else C['paper'])
        ink, cy = C['ink'], 6
        tri = lambda tx, d: pygame.draw.polygon(surf, ink, [(tx, cy - 3), (tx, cy + 3), (tx + 3 * d, cy)])   # d: -1 left
        if name == 'play':
            if self.playing:
                rect(surf, x + 4, cy - 3, 5, 7, ink)
            else:
                pygame.draw.polygon(surf, ink, [(x + 4, cy - 3), (x + 4, cy + 3), (x + 9, cy)])
        elif name == 'back':
            tri(x + 8, -1)
        elif name == 'next':
            tri(x + 5, 1)
        elif name == 'turn_back':
            tri(x + 6, -1)
            tri(x + 10, -1)
        elif name == 'turn_next':
            tri(x + 3, 1)
            tri(x + 7, 1)
