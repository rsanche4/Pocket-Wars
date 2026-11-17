"""The TUTORIAL: a battle on Boot Camp where the Green Commander teaches the game one step at a time (and the Tan
General butts in).

The words are in data/tutorial.json. This file decides WHEN each scene plays: always in the order of SCENES, each one
waiting for its moment (ready) and then for the screen to settle (no banner sliding, no battle scene, nothing marching
or falling). While someone talks the battle stands still and ENTER moves to the next line.

Until the hand-off it runs on rails, so every player sees the same lessons at the same moments:
  turn 1  place a soldier by the bridge, END TURN                       (Tan quietly sneaks a hurt soldier out)
  turn 3  place a soldier on a barracks, NEXT: MARCH, march the HQ's half-track across the bridge - Tan shows up -
          attack her lone soldier, move in or stay put, END TURN          (Tan's turn 4: she does nothing)
  turn 5  the HQ talk and the hand-off; from here it's a normal battle against the Normal CPU.
step() says what you may do right now (which outposts, which menu choices); the battle screen greys out the rest,
lights up the right outpost, puts the cursor on it and shows a hint.
"""
import pygame

from . import sound
from .data import load_json, parse_map
from .gfx import C, SIDES, SW, SH, rect, text, wrap, portrait, box

MAP = ('data', 'default-maps', '01-boot-camp.json')    # the original Boot Camp, so edits to your copy can't break it
SETTINGS = {'mode': 'cpu', 'cpu': 'normal', 'fog': 'fog', 'timer': 0, 'tutorial': True}
SCENES = ['briefing', 'reinforcements', 'deploy_only', 'over_to_tan', 'barracks', 'vehicles', 'march', 'march_done',
          'first_contact', 'attack', 'cleared', 'who_beats_who', 'hq', 'hand_off']
WHO = {'green': 0, 'tan': 1}
TYPE_SPEED = 55            # letters per second as a line types out
ROW = 39                   # letters per row in the box (4 rows)
BOX_Y = SH - 76            # the talk box runs from here to the bottom of the screen
# the outposts the lessons use, as (column, row) on Boot Camp's grid (Green's HQ is at (0, 1), Tan's at (3, 1))
SPOTS = {'bridge': (1, 1), 'barracks': (1, 0), 'across': (2, 1), 'bait': (2, 2), 'tan_start': (3, 2)}
BAIT_HP = 4                # Tan's lone soldier is already hurt, so the first attack always clears it
GATED = {'DONE: END TURN', 'NEXT: MARCH', 'END TURN', 'SKIP MARCH', 'BUY / NEXT', 'HALF-TRACK', 'TANK', 'HELICOPTER'}
GO_ON = {'MOVE ▶', 'FIRE!', 'MOVE IN'}         # where a lesson's march / attack / move-in menu starts its cursor
BUYING = {'NEXT: MARCH', 'BUY / NEXT', 'HALF-TRACK', 'TANK', 'HELICOPTER'}


def load_map():
    return parse_map(load_json(*MAP))


class Tutorial:
    def __init__(self, play):
        self.play = play
        self.words = load_json('data', 'tutorial.json')['scenes']
        self.played = {}           # scene -> the turn it played on
        self.pending = None        # a scene whose moment has come, waiting for the screen to settle
        self.talk = None           # the scene being spoken: id, line number, when the line started (real time)
        self.cleared = False       # you've wiped out Tan's lone soldier
        self.handed_off = False
        where = {(n.col, n.row): i for i, n in enumerate(play.g.map.nodes)}
        self.spot = {name: where[cr] for name, cr in SPOTS.items()}

    # ------------------------------------------------------------------ what the battle screen asks
    def busy(self):
        """Someone is talking, or about to: your keys wait (and the battle's scripts hold still)."""
        return self.talk is not None or self.pending is not None

    def quiet_banner(self):
        """The first REINFORCEMENTS banner waits until the briefing is over."""
        return 'briefing' not in self.played

    def saw_fight(self, f, b):
        """Called after every attack (the result is already decided)."""
        if f.attacker.side == 0 and not self.play.g.units[b] and f.target.type != 'hq':
            self.cleared = True

    def step(self):
        """What you may do right now, or None once you're free. Keys: place, march_from, march_to, attack_from,
        target (sets of outposts), items (menu choices from GATED you may pick) and hint (the bottom line)."""
        g, s = self.play.g, self.spot
        if self.handed_off or g.cur != 0 or g.phase == 'over':
            return None
        if g.turn == 1:
            if g.to_place:
                return {'place': {s['bridge']}, 'hint': 'ENTER: PLACE YOUR SOLDIER BY THE BRIDGE'}
            return {'items': {'DONE: END TURN', 'END TURN', 'BUY / NEXT'}, 'hint': 'ENTER: MENU · PICK DONE: END TURN'}
        if g.turn == 3 and g.phase == 'gather':
            if g.to_place:
                return {'place': {s['barracks']}, 'hint': 'ENTER: PLACE YOUR SOLDIER ON THE BARRACKS'}
            return {'items': BUYING, 'hint': 'ENTER: MENU · BUY, OR PICK NEXT: MARCH'}
        if g.turn == 3 and g.phase == 'march':
            return {'march_from': {g.hq[0]}, 'march_to': {s['across']},
                    'hint': {'cursor': 'ENTER ON OUR HQ: MARCH THE HALF-TRACK', 'pick_dest': 'ENTER: CROSS THE BRIDGE'}}
        if g.turn == 3 and not self.cleared:
            return {'attack_from': {s['across']}, 'target': {s['bait']},
                    'hint': {'cursor': 'ENTER: ATTACK FROM ACROSS THE BRIDGE', 'pick_target': 'ENTER: ATTACK HER LONE SOLDIER'}}
        if g.turn == 3 and 'who_beats_who' in self.played:
            return {'items': {'END TURN'}, 'hint': 'ESC: MENU · PICK END TURN'}
        return {}                         # in between (someone's about to talk): nothing to do yet

    def allows(self, kind, x):
        s = self.step()
        if s is None:
            return True
        if kind == 'item':
            return x not in GATED or x in s.get('items', ())
        return x in s.get(kind, ())

    def focus(self, kind, default):
        """Where the cursor should go for this part of the lesson."""
        s = self.step()
        return min(s[kind]) if s and s.get(kind) else default

    def hint(self, mode):
        s = self.step()
        h = s.get('hint') if s else None
        return h.get(mode) if isinstance(h, dict) else h if mode == 'cursor' else None

    def lock_menu(self, m):
        """Grey out the menu choices this part of the lesson doesn't use."""
        s = self.step()
        if s is None:
            return
        for it in m.items:
            if not self.allows('item', it.get('l')):
                it['dis'] = True
        usable = [k for k, it in enumerate(m.items) if not it.get('dis') and not it.get('info')]
        lesson = [k for k in usable if m.items[k].get('l') in set(s.get('items', ())) | GO_ON]
        if lesson:
            m.sel = lesson[0]                  # the cursor starts on what the lesson is asking for
        elif m.items[m.sel].get('dis') and usable:
            m.sel = usable[0]

    # ------------------------------------------------------------------ when scenes play
    def ready(self, sid):
        """Has scene sid's moment come? (Scenes chained to the one before just say True.)"""
        p, g = self.play, self.play.g
        yours = g.cur == 0
        if sid in ('briefing', 'first_contact', 'attack', 'hand_off'):
            return True
        if sid == 'reinforcements':
            return yours and g.phase == 'gather' and g.to_place > 0
        if sid == 'deploy_only':
            return yours and g.phase == 'gather' and g.to_place == 0
        if sid == 'over_to_tan':
            return g.cur == 1
        if sid == 'barracks':
            return yours and g.turn >= 3 and g.phase == 'gather' and g.to_place > 0
        if sid == 'vehicles':
            return yours and g.turn >= 3 and g.phase == 'gather' and g.to_place == 0
        if sid == 'march':
            return yours and g.phase == 'march'
        if sid == 'march_done':
            return yours and g.phase == 'attack'
        if sid == 'cleared':
            return self.cleared
        if sid == 'who_beats_who':        # once you've chosen to move in or stay put
            return not p.menu and not p.script and p.mode == 'cursor'
        if sid == 'hq':
            return yours and g.turn >= 5 and g.phase == 'gather'
        return False

    def settled(self, now):
        p = self.play
        return not p.banner and not p.cutin and not p.field.march and all(d.landed(now) for d in p.field.drops)

    def update(self, now):
        """Each frame (battle time): spot the next scene's moment, and start it once the screen has settled."""
        if self.talk or self.handed_off:
            return
        if self.play.g.phase == 'over':
            self.pending = None
            return
        if self.pending is None:
            nxt = next((s for s in SCENES if s not in self.played), None)
            if nxt and self.ready(nxt):
                self.pending = nxt
        if self.pending and self.settled(now):
            self.talk = {'id': self.pending, 'k': 0, 'start': None, 'cur': self.play.cur}
            self.pending = None
            sound.play('open')
            self.look()

    # ------------------------------------------------------------------ talking
    def line(self):
        return self.words[self.talk['id']]['lines'][self.talk['k']]

    def look(self):
        where = self.line().get('look')
        if where:
            self.play.cur = self.play.g.hq[1 if where == 'enemy_hq' else 0]

    def shown(self, now):
        """How many letters of the line have typed out so far."""
        start = self.talk['start']
        return 0 if start is None else int((now - start) * TYPE_SPEED)

    def key(self, now):
        """ENTER (or ESC): finish typing the line, or go on to the next one."""
        if self.shown(now) < len(self.line()['say']):
            self.talk['start'] = -1e9
            return
        sound.play('page')
        self.talk['k'] += 1
        self.talk['start'] = None
        if self.talk['k'] < len(self.words[self.talk['id']]['lines']):
            self.look()
            return
        sid, cur = self.talk['id'], self.talk['cur']
        self.talk = None
        self.played[sid] = self.play.g.turn
        if sid == 'briefing':
            self.play.turn_banner()
        elif sid == 'hand_off':
            self.handed_off = True
        for kind in ('place', 'march_from', 'attack_from'):      # the cursor goes to what you do next
            cur = self.focus(kind, cur)
        self.play.cur = cur

    def draw(self, surf, now):
        if not self.talk:
            return
        if self.talk['start'] is None:
            self.talk['start'] = now
        ln = self.line()
        side, mood = WHO[ln['who']], ln.get('mood', 'focus')
        s = SIDES[side]
        rect(surf, 0, 0, SW, SH, pygame.Color(0, 0, 0, 70))
        box(surf, 0, BOX_Y, SW, SH - BOX_Y, edge=s['dark'], inner=s['light'])
        px = 9 if side == 0 else SW - 65                  # Green talks from the left, Tan from the right
        tx = 72 if side == 0 else 10
        portrait(surf, side, mood, px, BOX_Y + 9)
        text(surf, s['commander'], tx, BOX_Y + 8, s['dark'])
        left = self.shown(now)
        for k, row in enumerate(wrap(ln['say'].upper(), ROW)[:4]):
            if left <= 0:
                break
            text(surf, row[:left], tx, BOX_Y + 21 + k * 10, C['ink'])
            left -= len(row) + 1
        if self.shown(now) >= len(ln['say']) and int(now / .4) % 2:
            text(surf, '▼', tx + ROW * 6 - 6, SH - 12, s['dark'])

    # ------------------------------------------------------------------ Tan, until the hand-off
    def tan_turn(self):
        """Tan's turns while the tutorial lasts (yields actions like ai.turn). Her first: a hurt soldier lands out of
        sight and walks to the barracks across the river from you, ready to be found. Her second: nothing (her
        reinforcements just stay home)."""
        g, s = self.play.g, self.spot
        if g.turn == 2:
            yield 'place', s['tan_start']
            bait = g.units[s['tan_start']][-1]
            bait.hp = BAIT_HP
        while g.to_place > 0:
            yield 'place', g.hq[1]
        yield ('end_gather',)
        if g.turn == 2:
            yield 'march', s['tan_start'], [s['tan_start'], s['bait']], [bait.id]
        else:
            yield ('skip_march',)
