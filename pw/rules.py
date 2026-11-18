"""The rules of Pocket Wars: the state of one battle and every move a player can make. No drawing, no sound.

A turn has three steps:
  gather  - get 1 soldier (+1 per barracks held) and place them; then you may build one vehicle
  march   - move one group from one outpost (Green's very first turn skips march and attack)
  attack  - every unit may attack once, at an enemy outpost next door
An outpost belongs to whoever has units on it. Destroy the enemy HQ to win.
"""
import math
import random
from dataclasses import dataclass

from .data import UNITS


def js_round(x):
    """Round halves up (10.5 -> 11), like the original game did. Python's round() would give 10."""
    return math.floor(x + 0.5)


def flies(t):
    return UNITS[t].get('flies', False)


def can_hit(t, target):
    return target not in UNITS[t].get('cannot_hit', [])


def damage_range(t, target):
    lo, hi = UNITS[t]['damage']
    bonus = UNITS[t].get('bonus_vs', {}).get(target)
    if bonus:
        lo, hi = js_round(lo * bonus), js_round(hi * bonus)
    return lo, hi


@dataclass
class Unit:
    id: int
    side: int          # 0 = Green, 1 = Tan
    type: str          # a key of data/units.json
    hp: int


def encode_move(action, result=None):
    """A move as plain data (for the network and for recordings): units become their ids, and a fight carries its
    roll (taken from result, the Fight it produced)."""
    if action[0] == 'fight':
        a, b, x, y = action[1:5]
        return ['fight', a, b, x.id, y.id] + ([[result.dealt, result.taken]] if result else [])
    return list(action)


@dataclass
class Fight:
    """What happened in one attack (the screen uses it to play the battle scene)."""
    attacker: Unit
    target: Unit
    dealt: int
    taken: int
    fired_back: bool
    attacker_hp: int   # hit points before the shots
    target_hp: int
    result: str        # 'ok', 'cleared' (outpost emptied, you may move in) or 'over' (an HQ fell)


class Game:
    def __init__(self, m, fog='off'):
        self.map = m
        n = len(m.nodes)
        self.adj = [[] for _ in range(n)]
        self.kind = {}
        for e in m.links:
            self.adj[e.a].append(e.b)
            self.adj[e.b].append(e.a)
            self.kind[e.a, e.b] = self.kind[e.b, e.a] = e.kind
        self.units = [[] for _ in range(n)]
        self.hq = [next((i for i, nd in enumerate(m.nodes) if nd.hq == p), -1) for p in (0, 1)]   # -1: no HQ (picture-only boards)
        self.fog = fog != 'off'
        self.blackout = fog == 'blackout'
        self.seen = [set(), set()]      # blackout: outposts each side has ever seen
        self.cur = 0
        self.turn = 0
        self.phase = 'gather'
        self.to_place = 0
        self.bought = False
        self.used = set()               # ids of units that attacked this turn
        self.cleared = None             # (a, b): the last attack from a emptied b, so units at a may move in
        self.winner = None
        self.resigned = False
        self.next_id = [1, 1]           # each side numbers its own units (Green's ids are even, Tan's odd), so an online
                                        # guest can name its new units the same way the host does
        self.totals = [new_totals(), new_totals()]     # running counts for the end-of-battle stats
        self.history = []               # a snapshot of both sides after every turn (see snapshot())
        for p in (0, 1):
            if self.hq[p] >= 0:
                self.add(self.hq[p], p, 'hq')
                self.add(self.hq[p], p, 'halftrack')
        self.snapshot()
        self.start_turn()

    # ---------- looking at the board ----------
    def owner(self, i):
        return self.units[i][0].side if self.units[i] else None

    def mine(self, p):
        return [i for i in range(len(self.units)) if self.owner(i) == p]

    def count(self, i, t):
        return sum(1 for u in self.units[i] if u.type == t)

    def road(self, a, b):
        return self.kind.get((a, b)) == 'road'

    def movable(self, i):
        return [u for u in self.units[i] if u.type != 'hq']

    def hq_unit(self, p):
        return next((u for u in self.units[self.hq[p]] if u.type == 'hq' and u.side == p), None) if self.hq[p] >= 0 else None

    def vehicles(self, p, t, visible=None):
        return sum(1 for i, us in enumerate(self.units) if visible is None or i in visible for u in us if u.side == p and u.type == t)

    def sight(self, p):
        """Outposts side p can see: each of its outposts sees as far as its best-sighted unit there."""
        seen = set()
        for i in self.mine(p):
            reach = max([1] + [UNITS[u.type]['sight'] for u in self.units[i]])
            local, frontier = {i}, [i]
            seen.add(i)
            for _ in range(reach):
                nxt = []
                for a in frontier:
                    for b in self.adj[a]:
                        if b not in local:
                            local.add(b)
                            seen.add(b)
                            nxt.append(b)
                frontier = nxt
        return seen

    def snapshot(self):
        """Remember how both sides stand right now (taken at the start and after every turn)."""
        def side(p):
            army = [u for us in self.units for u in us if u.side == p and u.type != 'hq']
            q, held = self.hq_unit(p), self.mine(p)
            return {'units': len(army), 'strength': sum(u.hp for u in army), 'outposts': len(held),
                    'barracks': sum(1 for i in held if self.map.nodes[i].barracks),
                    'damage': self.totals[p]['damage'], 'hq': q.hp if q else 0}
        self.history.append((self.turn, [side(0), side(1)]))

    def note_capture(self, i, p):
        if self.owner(i) != p:
            self.totals[p]['captured'] += 1

    def update_seen(self):
        if self.blackout:
            for p in (0, 1):
                self.seen[p] |= self.sight(p)

    def can_place(self, p, i):
        o = self.owner(i)
        if o == p:
            return True
        if o is not None:
            return False
        return any(self.owner(j) == p and self.road(i, j) for j in self.adj[i])

    def destinations(self, p, src, group):
        """{outpost: path} this group can march to. Ground units need roads and can't pass enemy outposts;
        a group of only flying units goes anywhere but can't land on the enemy. Fog: only outposts you can see."""
        if not group:
            return {}
        ok = lambda j: self.owner(j) in (None, p)
        air = all(flies(u.type) for u in group)
        steps = min(UNITS[u.type]['move'] for u in group)
        out, frontier = {}, [(src, [src])]
        for _ in range(steps):
            nxt = []
            for a, path in frontier:
                for b in self.adj[a]:
                    if b in path or (not air and (not self.road(a, b) or not ok(b))):
                        continue
                    if ok(b) and b not in out:
                        out[b] = path + [b]
                    nxt.append((b, path + [b]))
            frontier = nxt
        out.pop(src, None)
        if self.fog:
            vis = self.sight(p)
            out = {k: v for k, v in out.items() if k in vis}
        return out

    def targets(self, p, a):
        """Enemy outposts next to a that one of a's unused units can shoot."""
        return [b for b in self.adj[a] if self.owner(b) == 1 - p and
                any(x.id not in self.used and any(can_hit(x.type, y.type) for y in self.units[b]) for x in self.units[a])]

    # ---------- changing the board ----------
    def add(self, i, p, t):
        self.units[i].append(Unit(self.next_id[p] * 2 + p, p, t, UNITS[t]['hp']))
        self.next_id[p] += 1

    def take(self, i, ids):
        out = [u for u in self.units[i] if u.id in ids]
        self.units[i] = [u for u in self.units[i] if u.id not in ids]
        return out

    def start_turn(self):
        self.turn += 1
        p = self.cur
        barracks = sum(1 for i, nd in enumerate(self.map.nodes) if nd.barracks and self.owner(i) == p)
        self.phase, self.bought, self.used, self.cleared = 'gather', False, set(), None
        self.to_place = 1 + barracks
        self.update_seen()

    def place(self, i):
        self.note_capture(i, self.cur)
        self.add(i, self.cur, 'soldier')
        self.to_place -= 1
        self.totals[self.cur]['recruited'] += 1

    def buy(self, i, t):
        """Build one vehicle at outpost i, paid with soldiers standing there: the most hurt ones pay first (the
        vehicle is new either way, so the healthiest soldiers stay on)."""
        soldiers = sorted((u for u in self.units[i] if u.type == 'soldier'), key=lambda u: u.hp)
        pay = {u.id for u in soldiers[:UNITS[t]['cost']]}
        self.units[i] = [u for u in self.units[i] if u.id not in pay]
        self.add(i, self.cur, t)
        self.bought = True
        self.totals[self.cur]['built'] += 1
        self.totals[self.cur]['by_build'][t] = self.totals[self.cur]['by_build'].get(t, 0) + 1

    def begin_march(self):
        self.phase = 'march'

    def march(self, src, path, ids):
        self.note_capture(path[-1], self.cur)
        self.totals[self.cur]['marched'] += len(path) - 1
        moving = self.take(src, ids)
        self.units[path[-1]] += moving
        self.phase = 'attack'
        return moving

    def skip_march(self):
        self.phase = 'attack'

    def fight(self, a, b, x, y, dice=None):
        """Unit x (at a) attacks unit y (at b). Both shoot at once; damage is random within each unit's range.
        dice = (dealt, taken) already rolled (online, the host rolls and the guest's copy uses the same numbers)."""
        lo, hi = damage_range(x.type, y.type)
        back = can_hit(y.type, x.type)
        if dice:
            dealt, taken = dice
        else:
            dealt = random.randint(lo, hi)
            taken = random.randint(*damage_range(y.type, x.type)) if back else 0
        hx, hy = x.hp, y.hp
        self.used.add(x.id)
        y.hp -= dealt
        x.hp -= taken
        self.count_fight(x, y, min(dealt, hy), min(taken, hx))
        self.units[a] = [u for u in self.units[a] if u.hp > 0]
        self.units[b] = [u for u in self.units[b] if u.hp > 0]
        result = 'ok'
        for u in (x, y):
            if u.type == 'hq' and u.hp <= 0:
                self.end_game(1 - u.side)
                result = 'over'
                break
        if result == 'ok' and not self.units[b] and self.units[a] and self.move_in_choices(a, b):
            result = 'cleared'
        self.cleared = (a, b) if result == 'cleared' else None
        return Fight(x, y, dealt, taken, back, hx, hy, result)

    def count_fight(self, x, y, dealt, taken):
        """Add one attack to the stats. dealt/taken only count hit points that were really there to lose."""
        tx, ty = self.totals[x.side], self.totals[y.side]
        tx['attacks'] += 1
        for t, shooter, victim, hurt in ((tx, x, y, dealt), (ty, y, x, taken)):
            t['damage'] += hurt
            t['by_type'][shooter.type] = t['by_type'].get(shooter.type, 0) + hurt
            t['biggest'] = max(t['biggest'], hurt)
            if victim.type == 'hq':
                t['hq_damage'] += hurt
            elif victim.hp <= 0:
                t['kills'] += 1
                self.totals[victim.side]['lost'] += 1

    def move_in_choices(self, a, b):
        """Units at a that may move into the outpost b they just emptied (across a river, only flyers)."""
        return [u for u in self.movable(a) if flies(u.type) or self.road(a, b)]

    def move_in(self, a, b, ids):
        self.note_capture(b, self.cur)
        self.cleared = None
        moving = self.take(a, ids)
        self.units[b] += moving
        return moving

    def end_turn(self):
        self.snapshot()
        self.cur = 1 - self.cur
        self.start_turn()

    def end_game(self, winner, resigned=False):
        self.phase, self.winner, self.resigned = 'over', winner, resigned
        self.snapshot()

    def time_up(self):
        self.to_place = 0
        self.end_turn()

    def do(self, action):
        """Carry out one move: ('place', i), ('buy', i, type), ('end_gather',), ('begin_march',),
        ('march', src, path, ids), ('skip_march',), ('fight', a, b, x, y[, dice]), ('move_in', a, b, ids),
        ('end_turn',), ('time_up',) or ('resign', side). Returns what the rules return (a Fight for attacks)."""
        kind, *args = action
        if kind == 'end_gather':
            self.to_place = 0
            return None
        if kind == 'resign':
            return self.end_game(1 - args[0], resigned=True)
        return getattr(self, kind)(*args)

    def legal(self, action):
        """Is this move allowed right now for the side whose turn it is? (The online host checks every move its
        guest sends.) Fights name units by id here: ('fight', a, b, x_id, y_id)."""
        p, n, ph = self.cur, len(self.units), self.phase
        kind, *args = action
        ok_spot = lambda i: isinstance(i, int) and 0 <= i < n
        try:
            if ph == 'over':
                return False
            if kind == 'place':
                return ph == 'gather' and self.to_place > 0 and ok_spot(args[0]) and self.can_place(p, args[0])
            if kind == 'end_gather':
                return ph == 'gather'
            if kind == 'buy':
                i, t = args
                return (ph == 'gather' and not self.bought and ok_spot(i) and self.owner(i) == p and t in UNITS
                        and UNITS[t]['cost'] > 0 and self.count(i, 'soldier') >= UNITS[t]['cost'])
            if kind == 'begin_march':
                return ph == 'gather' and self.turn > 1
            if kind == 'skip_march':
                return ph in ('gather', 'march')
            if kind == 'march':
                src, path, ids = args
                group = [u for u in self.movable(src) if u.id in set(ids)] if ok_spot(src) and self.owner(src) == p else []
                return ph == 'march' and len(group) == len(set(ids)) > 0 and path[-1] in self.destinations(p, src, group)
            if kind == 'fight':
                a, b, xid, yid = args
                x = next((u for u in self.units[a] if u.id == xid), None) if ok_spot(a) else None
                y = next((u for u in self.units[b] if u.id == yid), None) if ok_spot(b) else None
                return (ph == 'attack' and self.turn > 1 and b in self.adj[a] and x is not None and y is not None and
                        x.side == p and y.side == 1 - p and x.id not in self.used and can_hit(x.type, y.type))
            if kind == 'move_in':
                a, b, ids = args
                can = {u.id for u in self.move_in_choices(a, b)} if self.cleared == (a, b) else set()
                return ph == 'attack' and bool(ids) and set(ids) <= can
            if kind in ('end_turn', 'time_up'):
                return True
        except (TypeError, ValueError, IndexError, KeyError):
            return False
        return False

    def decode_move(self, move):
        """A move from encode_move, with its units turned back into this board's own (None if they aren't here)."""
        kind, *args = move
        if kind == 'fight':
            a, b, xid, yid, *roll = args
            x = next((u for u in self.units[a] if u.id == xid), None)
            y = next((u for u in self.units[b] if u.id == yid), None)
            return ('fight', a, b, x, y, tuple(roll[0]) if roll else None) if x and y else None
        return tuple(move)

    # ---------- online: the board as one side may see it ----------
    def to_wire(self, viewer=None, full=False):
        """The board as plain data (for the online guest). viewer = the side it's for: with fog it only holds the
        units at outposts that side can see. full=True: everything, stats included (sent when the battle is over)."""
        see = set(range(len(self.units))) if full or not self.fog or viewer is None else self.sight(viewer)
        units = [[[u.id, u.side, u.type, u.hp] for u in us] if i in see else [] for i, us in enumerate(self.units)]
        shown = {u[0] for us in units for u in us}
        out = {'units': units, 'turn': self.turn, 'cur': self.cur, 'phase': self.phase, 'to_place': self.to_place,
               'bought': self.bought, 'used': sorted(self.used & shown), 'winner': self.winner, 'resigned': self.resigned,
               'cleared': self.cleared,      # (the other side's unit count stays private)
               'next_id': [n if full or viewer in (None, k) else 0 for k, n in enumerate(self.next_id)]}
        if self.blackout and viewer is not None:
            out['seen'] = sorted(self.seen[viewer])
        if full:
            out['totals'], out['history'] = self.totals, self.history
        return out

    def from_wire(self, d, viewer):
        """Take the board from to_wire (the guest's copy). Units already on the board stay the same objects."""
        old = {u.id: u for us in self.units for u in us}
        self.units = []
        for us in d['units']:
            row = []
            for uid, side, t, hp in us:
                u = old.get(uid) or Unit(uid, side, t, hp)
                u.side, u.type, u.hp = side, t, hp
                row.append(u)
            self.units.append(row)
        self.turn, self.cur, self.phase, self.to_place = d['turn'], d['cur'], d['phase'], d['to_place']
        self.bought, self.used, self.winner, self.resigned = d['bought'], set(d['used']), d['winner'], d['resigned']
        self.cleared = tuple(d['cleared']) if d['cleared'] else None
        self.next_id = list(d['next_id'])
        if 'seen' in d:
            self.seen[viewer] = set(d['seen'])
        if 'totals' in d:
            self.totals, self.history = d['totals'], [(t, sides) for t, sides in d['history']]


def new_totals():
    """One side's running counts for the end-of-battle stats."""
    return {'recruited': 0, 'built': 0, 'attacks': 0, 'damage': 0, 'hq_damage': 0, 'kills': 0, 'lost': 0,
            'biggest': 0, 'captured': 0, 'marched': 0, 'by_type': {}, 'by_build': {}}

