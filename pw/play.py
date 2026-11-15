"""The battle screen: shows the battlefield, takes your keys, runs the CPU, plays marches and battle scenes.

Things that take time (a CPU turn, a march, a battle scene) are written as generators ("scripts"): they yield a number
of seconds to wait, or something with a done(now) method (a March, a CutIn), and carry on when it is finished.
"""
import math
import pygame

from . import ai, sound, learn
from .stats import Stats
from .data import UNITS, ORDER
from .rules import Game, can_hit, damage_range, flies
from .field import Field, March, Drop
from .cutin import CutIn
from .menu import Menu
from .gfx import C, SIDES, SW, SH, rect, text, text_width, blit, portrait, unit_image
from .settings import S, save

TOP, BOTTOM = 13, 40
VIEW_Y, VIEW_H = TOP, SH - TOP - BOTTOM


def name(t):
    return UNITS[t]['name'].upper()


def avg(t):
    return sum(UNITS[t]['damage']) / 2


PHASE_NAMES = {'gather': 'GATHER', 'march': 'MARCH', 'attack': 'ATTACK', 'over': 'GAME OVER'}
BANNER_SECONDS = 1.4


def pausing(menu):
    """Mark a menu as one that pauses the battle while it's open (PAUSED and its RESIGN / QUIT questions)."""
    menu.pauses = True
    return menu


class Landed:
    """Something a script can wait for: every reinforcement still in the air has landed."""
    def __init__(self, field):
        self.field = field

    def done(self, now):
        return all(d.landed(now) for d in self.field.drops)


class Play:
    def __init__(self, app, m, settings):
        """settings: mode ('cpu', 'hot' = two players, 'watch' = CPU vs CPU), cpu ('normal'/'hard'), fog, timer, anim."""
        self.app, self.settings = app, settings
        mode = settings['mode']
        self.bots = [mode == 'watch', mode in ('cpu', 'watch')]
        self.levels = [settings['cpu'], settings['cpu']]
        self.speed = {'full': 1, 'fast': .5, 'off': 0}[settings['anim']]
        self.now = 0
        self.g = Game(m, settings['fog'])
        self.k = max(.36, min(.44, min((SW - 8) / m.w, (VIEW_H - 6) / m.h)))
        self.field = Field(self.g, self.k)
        self.cur, self.mode, self.menu = self.g.hq[0], 'cursor', None
        self.viewer = 0                     # whose eyes the screen shows in two-player fog
        self.script, self.wait = None, None
        self.banner = self.cutin = None
        self.pass_screen = False
        self.camera = None
        self.moods = [None, None]
        self.time_left = 0
        self.ended = False
        self.memory = None
        self.paused_total, self.paused_at = 0, None   # the battle's clock stops while the PAUSED menu is open
        if mode == 'cpu' and settings['cpu'] == 'hard':      # Hard learns from games against you (learn.py)
            you = self.human_side()
            self.memory = learn.load()
            self.g.learning = {'you': you, 'style': learn.pick_style(self.memory)}
            self.g.styles = [None, None]
            self.g.styles[1 - you] = self.g.learning['style']
            habits = learn.habits(self.memory)
            self.g.habits = {you: habits} if habits else {}
        sound.music('battle')
        self.turn_started()

    # ------------------------------------------------------------------ helpers
    def bot(self, p=None):
        return self.bots[self.g.cur if p is None else p]

    def human_side(self):
        if self.bots[0] != self.bots[1]:
            return 1 if self.bots[0] else 0
        return self.g.cur

    def viewer_side(self):
        """Whose sight the screen shows (None = everything)."""
        g = self.g
        if not g.fog or g.phase == 'over' or all(self.bots):
            return None
        if self.bots[1]:
            return 0
        if self.bots[0]:
            return 1
        return self.viewer

    def seen_by(self, i):
        v = self.viewer_side()
        return v is None or i in self.g.sight(v)

    def pause(self, seconds):
        return seconds * self.speed

    def say_banner(self, title, color, sub=None):
        """The big splash that slides across the screen (it never stops you from playing)."""
        self.banner = (title, color, sub, self.now, self.g.cur)

    def phase_color(self):
        """The colour of what you're doing right now: gold = gather/buy, blue = march, orange = attack (choosing
        where to attack from), red = choosing the target."""
        mode, phase = self.mode, self.g.phase
        if mode == 'pick_buy':
            return C['phase_gather']
        if mode == 'pick_dest':
            return C['phase_march']
        if mode == 'pick_target':
            return C['phase_target']
        return C.get('phase_' + phase, C['highlight'])

    def turn_banner(self):
        g, p = self.g, self.g.cur
        who = f"{SIDES[p]['name']} TURN {g.turn}"
        solo = self.bots[0] != self.bots[1]           # you against the CPU: say whose turn it is in plain words
        if self.bot(p):
            if solo:
                self.say_banner("CPU'S TURN", SIDES[p]['light'], f'{who} · WATCH ITS MOVES')
            else:
                self.say_banner(who, SIDES[p]['light'])
        else:
            n = g.to_place
            self.say_banner('REINFORCEMENTS', C['phase_gather'],
                            f"{'YOUR TURN' if solo else who} · PLACE {n} SOLDIER{'' if n == 1 else 'S'}")
        sound.play('turn_' + SIDES[p]['name'].lower())

    def drop(self, i):
        """Show the soldier just placed at outpost i parachuting in (it lands with the 'place' sound)."""
        unit = self.g.units[i][-1]
        if self.speed and self.seen_by(i):
            self.field.drops.append(Drop(i, unit, .65 if self.speed == 1 else .35, self.now))
        elif self.seen_by(i):
            sound.play('place')

    def set_mood(self, p, mood, seconds=2.4):
        self.moods[p] = (mood, self.now + seconds)

    def mood_of(self, p):
        g = self.g
        if g.phase == 'over':
            return 'happy' if g.winner == p else 'sad'
        if self.moods[p] and self.moods[p][1] > self.now:
            return self.moods[p][0]
        q = g.hq_unit(p)
        if q and q.hp < 35:
            return 'hurt'
        return 'focus' if g.cur == p and g.phase != 'gather' else 'happy'

    def look(self, i):
        """Move the cursor to where the CPU acts, when watching CPU vs CPU."""
        if self.seen_by(i) and all(self.bots):
            self.cur = i

    # ------------------------------------------------------------------ turns
    def turn_started(self):
        g, p = self.g, self.g.cur
        if not (self.bot(p) and not self.bot(1 - p)):
            self.cur = g.hq[p]
        self.mode, self.menu = 'cursor', None
        self.time_left = self.settings['timer']
        if g.fog and not any(self.bots):
            self.pass_screen = True
        else:
            self.turn_banner()
        if self.bot(p):
            self.run(self.cpu_turn())
        elif not self.pass_screen:
            self.after_gather()

    def end_turn(self):
        self.menu = None
        self.g.end_turn()
        self.turn_started()

    def after_gather(self):
        if self.g.phase == 'gather' and self.g.to_place <= 0 and not self.bot():
            self.run(self.buy_step())

    def buy_step(self):
        yield Landed(self.field)             # let the last soldiers touch down first
        self.say_banner('BUILD A VEHICLE?', C['phase_gather'], 'OPTIONAL · ONE PER TURN')
        self.open_buy()

    def to_march(self):
        if self.g.turn == 1:
            self.to_attack()
            return
        self.g.begin_march()
        self.mode, self.menu = 'cursor', None
        self.say_banner('MARCH', C['phase_march'], 'STEP 2 OF 3 · ONE GROUP, ONE MOVE')
        sound.play('march_phase')

    def to_attack(self):
        if self.g.phase != 'attack':
            self.g.skip_march()
        self.mode, self.menu = 'cursor', None
        if not self.bot():
            if self.g.turn == 1:          # first turn is deploy only: nothing left to do, so the turn ends
                self.end_turn()
            else:
                self.say_banner('ATTACK!', C['phase_attack'], 'STEP 3 OF 3 · PICK WHERE TO ATTACK FROM')
                sound.play('attack_phase')

    def game_over(self):
        w = self.g.winner
        self.ended = True
        solo = self.bots[0] != self.bots[1]
        sound.play('defeat' if solo and w != self.human_side() else 'victory')
        sound.music('victory', loop=False)
        if self.memory is not None:
            learn.record(self.memory, self.g, self.g.learning['you'], self.g.learning['style'])
            learn.save(self.memory)
            self.g.learning['memory'] = self.memory
        self.menu = self.over_menu()

    def over_menu(self, sel=0):
        w = self.g.winner
        m = Menu(f"{SIDES[w]['name']} WINS!", [
            {'l': 'BATTLE STATS', 'f': self.show_stats},
            {'l': 'PLAY AGAIN', 'f': self.app.play_again},
            {'l': 'MAIN MENU', 'f': self.app.main_menu}],
            sub=f"{SIDES[1 - w]['name']} RESIGNED" if self.g.resigned else None, win=w)
        m.sel = sel
        return m

    def show_stats(self):
        def back():
            self.app.scene = self
            self.menu = self.over_menu(sel=1)          # back on the victory menu, on PLAY AGAIN
        self.app.scene = Stats(self.app, self.g, back)

    def resign(self, p):
        self.script = self.wait = self.cutin = None
        self.field.march = None
        self.g.end_game(1 - p, resigned=True)
        self.game_over()

    # ------------------------------------------------------------------ scripts (things that take time)
    def run(self, script):
        self.script, self.wait = script, None

    def battle_time(self, now):
        """The real clock minus the time spent paused (frozen while paused)."""
        return (self.paused_at if self.paused_at is not None else now) - self.paused_total

    def update(self, now, dt):
        if self.menu is not None and getattr(self.menu, 'pauses', False):
            if self.paused_at is None:
                self.paused_at = now
            return                                # nothing moves: CPU, marches, battle scenes, the turn timer
        if self.paused_at is not None:
            self.paused_total += now - self.paused_at
            self.paused_at = None
        now = self.battle_time(now)
        self.now = now
        while self.script:
            w = self.wait
            if isinstance(w, (int, float)) and now < w:
                break
            if hasattr(w, 'done') and not w.done(now):
                break
            script = self.script
            try:
                y = next(script)
            except StopIteration:
                if self.script is script:     # (it may have started the next turn's script itself)
                    self.script = None
                continue
            if self.script is not script:     # a new script took over while this one ran
                continue
            self.wait = now + y if isinstance(y, (int, float)) else y
        for d in self.field.drops:
            if not d.heard and d.landed(now):
                d.heard = True
                sound.play('place')
        g = self.g
        if g.phase == 'over' and not self.ended and not self.cutin:
            self.game_over()
        if self.settings['timer'] and g.phase != 'over' and not self.bot() and not self.pass_screen and not self.script:
            before = math.ceil(self.time_left)
            self.time_left -= dt
            left = max(0, math.ceil(self.time_left))
            if left < before and 0 < left <= 10:
                sound.play('tick_last' if left <= 3 else 'tick')
            if self.time_left <= 0:
                sound.play('time_up')
                self.menu = None
                g.time_up()
                self.turn_started()

    def cpu_turn(self):
        yield .5
        actions, result = ai.turn(self.g, self.levels[self.g.cur]), None
        while True:
            try:
                action = actions.send(result)
            except StopIteration:
                break
            result = yield from self.perform(action)
            if self.g.phase == 'over':
                return
            if action[0] == 'end_gather':
                yield Landed(self.field)          # its reinforcements touch down before it moves on
            if action[0] in ('march', 'skip_march', 'end_gather'):
                yield self.pause(.25 if action[0] != 'end_gather' else .2)
        self.end_turn()

    def perform(self, action):
        """Carry out one action, with animation. Returns what the rules return (a Fight for attacks)."""
        g, kind = self.g, action[0]
        if kind == 'place':
            g.place(action[1])
            self.look(action[1])
            self.drop(action[1])
            yield self.pause(.16)
        elif kind == 'buy':
            g.buy(*action[1:])
            self.set_mood(g.cur, 'happy', 1.6)
            sound.play('buy')
            yield self.pause(.2)
        elif kind == 'march':
            src, path, ids = action[1:]
            self.look(src)
            yield self.pause(.2)
            yield from self.walk(src, path, ids)
        elif kind == 'fight':
            a, b, x, y = action[1:]
            self.look(b)
            yield self.pause(.12)
            return (yield from self.fight(a, b, x, y))
        elif kind == 'move_in':
            yield from self.walk(action[1], [action[1], action[2]], action[3], move_in=True)
        else:
            return g.do(action)

    def walk(self, src, path, ids, move_in=False):
        g, dst = self.g, path[-1]
        units = [u for u in g.units[src] if u.id in ids]
        free = g.owner(dst) is None
        see = self.seen_by(src) or self.seen_by(dst)
        if see and self.speed:
            m = March(path, units, .17 if self.speed < 1 else .3, self.now)
            self.field.march = m
            kind = 'heli' if all(flies(u.type) for u in units) else 'soldier' if all(u.type == 'soldier' for u in units) else 'vehicle'
            gap = {'soldier': .15, 'vehicle': .17, 'heli': .095}[kind]
            while not m.done(self.now):
                sound.play('step_' + kind)
                yield gap
            self.field.march = None
        if move_in:
            g.move_in(src, dst, ids)
        else:
            g.march(src, path, ids)
        if see and (free or move_in) and self.seen_by(dst):
            sound.play('capture')

    def fight(self, a, b, x, y):
        g = self.g
        see = self.seen_by(a) or self.seen_by(b)
        f = g.fight(a, b, x, y)
        self.fight_moods(f)
        if see and self.speed:
            self.cutin = CutIn(f, self.now, .25 if self.speed < 1 else 1)     # Fast: about a quarter of the full length
            yield self.cutin
            self.cutin = None
        elif see:
            sound.play('shot_' + x.type)
            yield .25
            sound.play('destroyed' if x.hp <= 0 or y.hp <= 0 else 'hit')
        if see and not g.units[b] and y.type != 'hq':
            sound.play('cleared')
        return f

    def fight_moods(self, f):
        x, y = f.attacker, f.target
        killed, lost = y.hp <= 0, f.fired_back and x.hp <= 0
        if killed and y.type != 'hq':
            self.set_mood(x.side, 'happy')
            self.set_mood(y.side, 'sad')
        elif lost:
            self.set_mood(x.side, 'sad')
            self.set_mood(y.side, 'happy')
        elif y.type == 'hq' and f.dealt > 0:
            self.set_mood(x.side, 'happy')
            self.set_mood(y.side, 'angry')
        else:
            self.set_mood(y.side, 'hurt' if f.dealt > 0 else 'happy')
            self.set_mood(x.side, 'hurt' if f.fired_back and f.taken >= f.dealt else 'happy')

    def human_march(self, src, path, ids):
        yield from self.walk(src, path, ids)
        self.to_attack()

    def human_fight(self, a, b, x, y):
        p = self.g.cur
        f = yield from self.fight(a, b, x, y)
        if f.result == 'over' or self.g.phase == 'over':
            return
        if f.result == 'cleared':
            self.mode = 'cursor'                  # nothing left to target there
            self.menu = self.move_in_menu(a, b)
        elif self.g.units[a] and self.g.units[b] and b in self.g.targets(p, a):
            self.menu = self.fight_menu(a, b)
        elif self.g.units[a] and self.g.targets(p, a):      # can't hit b again, but another enemy is in reach
            self.cur = self.g.targets(p, a)[0]
        else:
            self.mode, self.cur = 'cursor', a if self.g.units[a] else self.cur

    def human_move_in(self, a, b, ids):
        yield from self.walk(a, [a, b], ids, move_in=True)
        self.mode = 'cursor'

    # ------------------------------------------------------------------ menus
    def turn_items(self):
        """The things you can do with your turn right now (buy, skip the march, end the turn)."""
        g = self.g
        items = []
        if g.phase == 'gather' and g.to_place == 0:
            items.append({'l': 'BUY / NEXT', 'f': self.open_buy})
        if g.phase == 'march':
            items.append({'l': 'SKIP MARCH', 'f': self.to_attack})
        items.append({'l': 'END TURN', 'f': self.end_turn})
        return items

    def open_pause(self):
        """ESC on the map: resume, your turn's actions (skip march, end turn...), resign or quit."""
        sound.play('open')
        self.mode = 'cursor'
        busy = self.script is not None or self.bot()      # CPU's turn or something animating: only pause options
        items = [{'l': 'RESUME', 'f': lambda: None}]
        if not busy:
            items += self.turn_items()
        items += self.sound_items()
        items += [{'l': 'RESIGN', 'f': self.ask_resign},
                  {'l': 'QUIT TO MENU', 'f': lambda: setattr(self, 'menu', pausing(Menu('QUIT THIS BATTLE?', [
                      {'l': 'NO, KEEP PLAYING', 'f': lambda: None}, {'l': 'YES, QUIT', 'f': self.app.main_menu}])))}]
        self.menu = pausing(Menu('PAUSED', items))

    def sound_items(self):
        """Music and effects volume, and battle-scene speed, changed with LEFT/RIGHT without leaving the battle
        (saved like the Options screen). Turning a volume up also switches that sound back on."""
        def volume(label, key, on):
            def adj(d):
                S[key] = max(0, min(10, S[key] + d))
                S[on] = S[key] > 0
                save()
            return {'l': label, 'val': lambda: f"◀ {S[key] if S[on] else 'OFF'} ▶", 'adj': adj}

        def scenes(d):
            options = ['full', 'fast', 'off']
            S['anim'] = options[(options.index(S['anim']) + d) % 3]
            save()
            self.settings['anim'] = S['anim']
            self.speed = {'full': 1, 'fast': .5, 'off': 0}[S['anim']]
        return [volume('MUSIC VOLUME', 'music_volume', 'music'), volume('EFFECTS VOLUME', 'sfx_volume', 'sound'),
                {'l': 'BATTLE SCENES', 'val': lambda: f"◀ {S['anim'].upper()} ▶", 'adj': scenes}]

    def ask_resign(self):
        p = self.human_side()
        self.mode = 'cursor'
        self.menu = pausing(Menu(f"{SIDES[p]['name']}: RESIGN?", [
            {'l': 'NO, KEEP FIGHTING', 'f': lambda: None},
            {'l': f"YES, {SIDES[p]['name']} GIVES UP", 'f': lambda: self.resign(p) if self.g.phase != 'over' else None}],
            sub=f"{SIDES[1 - p]['name']} WILL WIN"))

    def open_buy(self):
        g, p = self.g, self.g.cur

        def can(t):
            return not g.bought and any(g.count(i, 'soldier') >= UNITS[t]['cost'] for i in g.mine(p))

        def choose(t):
            self.mode, self.buy_type, self.menu = 'pick_buy', t, None
            spots = [i for i in g.mine(p) if g.count(i, 'soldier') >= UNITS[t]['cost']]
            if spots:
                self.cur = spots[0]

        items = [{'l': name(t), 'r': f"{UNITS[t]['cost']} SOLDIERS", 'icon': t, 'side': p, 'dis': not can(t), 'f': lambda t=t: choose(t)}
                 for t in ORDER if UNITS[t]['cost'] > 0]
        items.append({'l': 'DONE: END TURN' if g.turn == 1 else 'NEXT: MARCH', 'f': self.to_march})
        self.menu = Menu('BUY ONE VEHICLE?', items, sub='SPEND SOLDIERS ON ONE OUTPOST')

    def unit_groups(self, units):
        """Units grouped by (type, HP, already fired this turn) - units in one group are interchangeable.
        Returns the groups and their keys in menu order: by type, ready first, healthiest first."""
        groups = {}
        for u in units:
            if u.type != 'hq':
                groups.setdefault((u.type, u.hp, u.id in self.g.used), []).append(u)
        return groups, sorted(groups, key=lambda k: (ORDER.index(k[0]), k[2], -k[1]))

    def group_from(self, i, counts):
        """The units at outpost i picked in a WHO MARCHES? menu (counts: group key -> how many)."""
        groups, keys = self.unit_groups(self.g.units[i])
        return [u for k in keys for u in groups[k][:counts.get(k, 0)]]

    def counter(self, k, counts, most):
        """A menu row choosing how many units of group k (type, HP, fired) to send."""
        t, hp, fired = k

        def adj(d):
            counts[k] = max(0, min(most, counts[k] + d))
        return {'l': f"{name(t)} {hp}HP{' (FIRED)' if fired else ''}", 'icon': t, 'side': self.g.cur,
                'val': lambda: f'◀ {counts[k]}/{most} ▶', 'adj': adj}

    def group_menu(self, i, counts=None):
        groups, keys = self.unit_groups(self.g.units[i])
        if counts is None:
            counts = {k: len(groups[k]) for k in keys}

        def go():
            if not self.group_from(i, counts):
                sound.play('error')
                self.menu = self.group_menu(i, counts)
                return
            self.mode, self.src, self.counts, self.menu = 'pick_dest', i, counts, None

        items = [self.counter(k, counts, len(groups[k])) for k in keys]
        items += [{'l': 'MOVE ▶', 'f': go}, {'l': 'CANCEL', 'f': lambda: None}]
        return Menu('WHO MARCHES?', items, sub='◀ ▶ CHANGE HOW MANY', wide=True)

    def fight_menu(self, a, b):
        g = self.g
        ready = lambda: [x for x in g.units[a] if x.id not in g.used and any(can_hit(x.type, y.type) for y in g.units[b])]
        st = {'a': 0, 't': 0}
        attacker = lambda: ready()[st['a'] % len(ready())] if ready() else None
        targets = lambda x: [y for y in g.units[b] if can_hit(x.type, y.type)] if x else []
        target = lambda: (targets(attacker()) or [None])[st['t'] % max(1, len(targets(attacker())))]
        r = ready()
        if r:      # start with the strongest attacker and its weakest target
            st['a'] = max(range(len(r)), key=lambda k: (avg(r[k].type), -k))
            ts = targets(r[st['a']])
            st['t'] = min(range(len(ts)), key=lambda k: (ts[k].hp, k))

        def odds():
            x, y = attacker(), target()
            if not x or not y:
                return ''
            lo, hi = damage_range(x.type, y.type)
            back = can_hit(y.type, x.type)
            take = '-'.join(map(str, damage_range(y.type, x.type))) if back else '0'
            return f"DEAL {lo}-{hi}  TAKE {take}{'  AA!' if UNITS[x.type].get('bonus_vs', {}).get(y.type) else ''}"

        def fire():
            x, y = attacker(), target()
            if x and y:
                self.run(self.human_fight(a, b, x, y))

        def adj_attacker(d):
            st['a'] = (st['a'] + d) % max(1, len(ready()))
            st['t'] = 0

        items = [{'l': 'ATTACKER', 'val': lambda: f"◀ {name(attacker().type)} {attacker().hp}HP ▶" if attacker() else '-', 'adj': adj_attacker},
                 {'l': 'TARGET', 'val': lambda: f"◀ {name(target().type)} {target().hp}HP ▶" if target() else '-',
                  'adj': lambda d: st.update(t=(st['t'] + d) % max(1, len(targets(attacker()))))},
                 {'l': '', 'info': True, 'val': odds},
                 {'l': 'FIRE!', 'col': C['red'], 'f': fire},
                 {'l': 'BACK', 'f': lambda: None}]          # back to choosing the target
        m = Menu('ATTACK!', items, pair=(a, b))
        m.sel = 3
        return m

    def move_in_menu(self, a, b, counts=None):
        """Pick who moves in. Units are grouped by type, health and whether they already fired this turn,
        so you choose e.g. the healthy soldiers and leave the hurt ones behind."""
        groups, keys = self.unit_groups(self.g.move_in_choices(a, b))
        if counts is None:      # start with half the soldiers (or one unit), ready and healthy ones first
            counts = {k: 0 for k in keys}
            pool = [k for k in keys if k[0] == 'soldier'] or keys[:1]
            want = math.ceil(sum(len(groups[k]) for k in pool) / 2) if pool[0][0] == 'soldier' else 1
            for k in pool:
                counts[k] = min(want, len(groups[k]))
                want -= counts[k]

        def go():
            ids = [u.id for k in keys for u in groups[k][:counts[k]]]
            if not ids:
                sound.play('error')
                self.menu = self.move_in_menu(a, b, counts)
                return
            self.run(self.human_move_in(a, b, ids))

        def look():
            self.mode, self.peek = 'peek', (a, b, counts)

        items = [self.counter(k, counts, len(groups[k])) for k in keys]
        items += [{'l': 'MOVE IN', 'f': go}, {'l': 'LOOK AROUND FIRST', 'f': look},
                  {'l': 'STAY PUT', 'f': lambda: setattr(self, 'mode', 'cursor')}]
        m = Menu('OUTPOST CLEARED!', items, sub='MOVE IN FOR FREE?  ◀ ▶ HOW MANY', wide=True, pair=(a, b))
        m.on_back = look                 # ESC hides it to look at the map too: only STAY PUT gives up moving in
        return m

    # ------------------------------------------------------------------ keys
    def key(self, k):
        g = self.g
        if self.cutin:
            if k in 'eb':
                self.cutin.skipped = True
            return
        if self.pass_screen:
            if k == 'e':
                self.pass_screen = False
                self.viewer = g.cur
                self.turn_banner()
                self.after_gather()
            return
        if self.menu:
            m, it = self.menu, self.menu.items[self.menu.sel]
            if k in 'ud':
                m.move(-1 if k == 'u' else 1)
                sound.play('cursor')
            elif k in 'lr' and it.get('adj'):
                it['adj'](-1 if k == 'l' else 1)
                sound.play('adjust')
            elif k == 'b' and g.phase != 'over':
                sound.play('back')
                if getattr(m, 'on_back', None):
                    self.menu = None
                    m.on_back()
                elif m.pair and self.mode == 'pick_target':
                    self.menu = None               # attack menu: back to choosing the target
                else:
                    self.menu, self.mode = None, 'cursor'
            elif k == 'e':
                if it.get('dis') or it.get('info'):
                    sound.play('error')
                    return
                if it.get('adj') and not it.get('f'):      # a setting or a counter: ENTER steps it like RIGHT
                    it['adj'](1)
                    sound.play('adjust')
                    return
                sound.play('select')
                self.menu = None
                if it.get('f'):
                    it['f']()
            return
        if g.phase == 'over':
            return
        busy = self.script is not None or self.bot()
        if k == 'b' and busy:
            self.open_pause()
            return
        if busy:
            return
        if self.mode == 'peek' and k in 'eb':          # done looking: back to the move-in choice, as you left it
            a, b, counts = self.peek
            self.mode, self.cur = 'cursor', b
            self.menu = self.move_in_menu(a, b, counts)
            sound.play('select' if k == 'e' else 'back')
            return
        if k in 'udlr':
            j = self.node_toward(k)
            if j is not None:
                self.cur = j
                sound.play('map_cursor')
            return
        if k == 'b':
            if self.mode != 'cursor':
                if self.mode == 'pick_target':
                    self.cur = self.src            # back to the outpost you were attacking from
                self.mode = 'cursor'
                sound.play('back')
            else:
                self.open_pause()
            return
        if k == 'e':
            self.enter()

    def enter(self):
        g, p, i, mode = self.g, self.g.cur, self.cur, self.mode
        if mode == 'pick_buy':
            if g.owner(i) == p and g.count(i, 'soldier') >= UNITS[self.buy_type]['cost']:
                g.buy(i, self.buy_type)
                self.set_mood(p, 'happy', 1.6)
                sound.play('buy')
                self.to_march()
            else:
                sound.play('back')
                self.mode = 'cursor'
                self.open_buy()
        elif mode == 'pick_dest':
            group = self.group_from(self.src, self.counts)
            dests = g.destinations(p, self.src, group)
            self.mode = 'cursor'
            if i in dests:
                self.run(self.human_march(self.src, dests[i], [u.id for u in group]))
            else:
                sound.play('back')
        elif mode == 'pick_target':
            if i in g.targets(p, self.src):
                self.menu = self.fight_menu(self.src, i)
                sound.play('select')
            else:                              # can't hit that one: stay in target picking (ESC backs out)
                sound.play('error')
        elif g.phase == 'gather':
            if g.to_place > 0:
                if g.can_place(p, i):
                    g.place(i)
                    self.drop(i)
                    self.after_gather()
                else:
                    sound.play('error')
            else:
                self.open_buy()
        elif g.phase == 'march':
            if g.owner(i) == p and g.movable(i):
                self.menu = self.group_menu(i)
                sound.play('select')
            else:
                sound.play('error')
        elif g.phase == 'attack':
            targets = g.targets(p, i) if g.turn > 1 and g.owner(i) == p else []
            if targets:
                self.mode, self.src = 'pick_target', i
                self.cur = targets[0]          # the cursor jumps onto an enemy and becomes a red target; you pick
                sound.play('select')           # which one to hit (even if there is only one), ESC goes back
            else:
                sound.play('error')

    def node_toward(self, d):
        """The outpost the cursor should jump to when pressing an arrow."""
        nodes, here = self.g.map.nodes, self.g.map.nodes[self.cur]
        v = self.viewer_side()
        vis = self.g.sight(v) if self.g.blackout and v is not None else None
        best, score = None, 1e9
        for i, n in enumerate(nodes):
            if i == self.cur or (vis is not None and i not in vis):
                continue
            dx, dy = n.x - here.x, n.y - here.y
            along, side = {'l': (-dx, abs(dy)), 'r': (dx, abs(dy)), 'u': (-dy, abs(dx)), 'd': (dy, abs(dx))}[d]
            if along > 10 and along + side * 2.2 < score:
                best, score = i, along + side * 2.2
        return best

    # ------------------------------------------------------------------ drawing
    def highlights(self):
        g, p, h = self.g, self.g.cur, set()
        if self.bot() or self.script or self.pass_screen or g.phase == 'over' or (self.menu and not self.menu.pair):
            return h
        if self.menu and self.mode != 'pick_target':        # OUTPOST CLEARED!: just the two outposts it's about
            return set(self.menu.pair)
        for i in range(len(g.units)):
            if self.mode == 'pick_buy':
                if g.owner(i) == p and g.count(i, 'soldier') >= UNITS[self.buy_type]['cost']:
                    h.add(i)
            elif self.mode == 'pick_target':
                if i in g.targets(p, self.src):
                    h.add(i)
            elif self.mode == 'cursor':
                if (g.phase == 'gather' and g.to_place > 0 and g.can_place(p, i)) or \
                   (g.phase == 'march' and g.owner(i) == p and g.movable(i)) or \
                   (g.phase == 'attack' and g.turn > 1 and g.owner(i) == p and g.targets(p, i)):
                    h.add(i)
        if self.mode == 'pick_dest':
            h |= set(g.destinations(p, self.src, self.group_from(self.src, self.counts)))
        if self.mode == 'peek' and not self.menu:
            h |= set(self.peek[:2])
        if self.menu and self.menu.pair:
            h |= set(self.menu.pair)
        return h

    def cam(self):
        """Follows the cursor. With an attack or move-in pop-up open it looks at the two outposts instead and keeps
        them in the top part of the view, so the pop-up can sit below them (menu_align)."""
        nodes = self.g.map.nodes
        x, y, frac = nodes[self.cur].x, nodes[self.cur].y, .5
        if self.menu and self.menu.pair:
            a, b = (nodes[i] for i in self.menu.pair)
            x, y, frac = (a.x + b.x) / 2, (a.y + b.y) / 2, .3
        ww, wh = self.field.world.get_size()
        tx = (ww - SW) / 2 if ww <= SW else max(0, min(ww - SW, x * self.k - SW / 2))
        ty = (wh - VIEW_H) / 2 if wh <= VIEW_H else max(0, min(wh - VIEW_H, y * self.k - VIEW_H * frac))
        self.cam_goal = (tx, ty)
        if self.camera is None:
            self.camera = [tx, ty]
        self.camera[0] += (tx - self.camera[0]) * .25
        self.camera[1] += (ty - self.camera[1]) * .25
        return round(self.camera[0]), round(self.camera[1]) - VIEW_Y

    def menu_spot(self):
        """Where a pop-up goes: centred, or for one about two outposts (attack, move in), wherever along the edges
        of the view it covers the least of them, so you can still see both."""
        if not self.menu.pair:
            return None
        w, h = self.menu.size()
        boxes = []                                           # each outpost and the units standing on it, on screen
        for i in self.menu.pair:
            n = self.g.map.nodes[i]
            x, y = n.x * self.k - self.cam_goal[0], n.y * self.k - self.cam_goal[1] + VIEW_Y   # once the camera arrives
            boxes.append(pygame.Rect(round(x - 24), round(y - 26), 48, 44))
        best = None
        for k, (mx, my) in enumerate((mx, my) for my in (VIEW_Y + VIEW_H - h - 3, VIEW_Y + 3)
                                     for mx in ((SW - w) // 2, SW - w - 3, 3)):
            r = pygame.Rect(mx, my, w, h)
            cover = sum(r.clip(bx).width * r.clip(bx).height for bx in boxes)
            if best is None or cover < best[0]:
                best = (cover, (mx, my))
        return best[1]

    def draw(self, surf, now):
        now = self.battle_time(now)                  # animations freeze while paused
        g = self.g
        surf.fill(C['background'])
        v = self.viewer_side()
        vis = g.sight(v) if v is not None else None
        cam = self.cam()
        mine = not self.script and not self.bot() and not self.pass_screen and g.phase != 'over'   # your move
        show_cursor = self.cur if not self.script and not self.bot() else None
        style = 'normal'
        if self.mode == 'pick_target' and mine:
            style = 'target' if self.cur in g.targets(g.cur, self.src) else 'no_target'
        self.field.draw(surf, cam, now, vis, g.blackout, self.highlights(), show_cursor, self.phase_color(), style)
        if mine and self.mode == 'pick_dest':                  # the arrow from the marching group to the cursor
            dests = g.destinations(g.cur, self.src, self.group_from(self.src, self.counts))
            if self.cur in dests:
                self.field.draw_route(surf, cam, dests[self.cur])
        if mine and self.mode == 'cursor' and not self.menu and g.phase == 'gather' and g.to_place > 0                 and g.can_place(g.cur, self.cur):                # the next reinforcement, waiting to drop here
            self.field.draw_ghost(surf, cam, self.cur, g.cur, now)
        if self.bot() and not all(self.bots) and g.phase != 'over':
            self.draw_cpu_playing(surf, now)
        self.draw_top(surf, now, vis)
        self.draw_info(surf, vis)
        if self.banner:
            if now - self.banner[3] > BANNER_SECONDS:
                self.banner = None
            else:
                self.draw_banner(surf, now)
        if self.menu:
            self.menu.draw(surf, VIEW_Y, VIEW_H, SIDES[self.menu.win if self.menu.win is not None else 0], self.menu_spot())
            if self.menu.win is not None:
                w = self.menu.win
                portrait(surf, w, 'happy', 4, VIEW_Y + 40)
                portrait(surf, 1 - w, 'sad', SW - 60, VIEW_Y + 40)
                for side, cx in ((w, 32), (1 - w, SW - 32)):
                    for k, word in enumerate(SIDES[side]['commander'].split(' ')):
                        text(surf, word, cx, VIEW_Y + 101 + k * 9, C['white'], 1, 'c', C['ink'])
        if self.pass_screen:
            self.draw_pass(surf, now)
        if self.cutin:
            self.cutin.draw(surf, now)

    def draw_banner(self, surf, now):
        """The phase splash: a band in the playing side's colours opens, big letters (in the phase's colour) slide in
        from the right, wait, and slide out left. With a menu open it sits at the top of the view so it doesn't hide
        the menu."""
        title, col, sub, t0, side = self.banner
        s = SIDES[side]
        t = now - t0
        h = 32 if sub else 24
        band = h * min(1, t / .1, max(0, (BANNER_SECONDS - t) / .12))      # opens, then closes
        mid = VIEW_Y + 4 + h / 2 if self.menu else VIEW_Y + VIEW_H / 2
        y0 = round(mid - band / 2)
        if band < 1:
            return
        fill = pygame.Color(s['dark'])
        fill.a = 235
        rect(surf, 0, y0, SW, round(band), fill)
        for y in (y0, y0 + round(band) - 3):           # edges: the side's colour with a thin line of the phase's
            rect(surf, 0, y, SW, 3, s['main'])
            rect(surf, 0, y + (2 if y == y0 else 0), SW, 1, col)
        ease = lambda k: 1 - (1 - max(0, min(1, k))) ** 3
        x = SW / 2 + (1 - ease(t / .22)) * SW - ease((t - (BANNER_SECONDS - .3)) / .3) * SW
        top = round(mid - h / 2)
        surf.set_clip(pygame.Rect(0, y0 + 2, SW, max(0, round(band) - 4)))
        text(surf, title, x, top + 5, col, 2, 'c', C['ink'])
        if sub:
            text(surf, sub, x + (1 - ease((t - .06) / .22)) * SW * .5, top + 22, C['white'], 1, 'c')
        surf.set_clip(None)

    def draw_cpu_playing(self, surf, now):
        """While the CPU plays: a thin frame in its colour around the battlefield and a small tab under the top bar,
        so it's always clear it isn't your turn (small, so you can still watch its moves)."""
        s = SIDES[self.g.cur]
        y0, y1 = VIEW_Y, VIEW_Y + VIEW_H
        for x, y, w, h in ((0, y0, SW, 2), (0, y1 - 2, SW, 2), (0, y0, 2, VIEW_H), (SW - 2, y0, 2, VIEW_H)):
            rect(surf, x, y, w, h, s['main'])
        dots = '.' * (int(now * 3) % 3 + 1)
        label = f"{s['name']} (CPU) IS PLAYING"
        w = text_width(label + '...') + 10
        x = round((SW - w) / 2)
        rect(surf, x, y0, w, 12, C['ink'])
        rect(surf, x + 1, y0, w - 2, 11, s['dark'])
        text(surf, label + dots, x + 5, y0 + 2, s['light'])

    def draw_top(self, surf, now, vis):
        g, p = self.g, self.g.cur
        rect(surf, 0, 0, SW, TOP, C['olive'])
        rect(surf, 0, TOP - 1, SW, 1, C['olive_dark'])
        blit(surf, unit_image('icons', 'soldier', p), 3, 1)
        text(surf, SIDES[p]['name'], 14, 3, SIDES[p]['main'], 1, 'l', C['ink'])
        text(surf, f'T{g.turn}', 56, 3, C['white'])
        phase = PHASE_NAMES[g.phase]                          # the phase as a tag in its colour
        x = 56 + text_width(f'T{g.turn}') + 5
        col = C['grey'] if g.phase == 'over' else self.phase_color()     # turns red while choosing a target
        rect(surf, x - 2, 1, text_width(phase) + 4, TOP - 3, col)
        text(surf, phase, x, 3, C['ink'])
        if g.phase == 'gather' and g.to_place > 0:
            text(surf, f'PLACE {g.to_place}', x + text_width(phase) + 6, 3, C['white'])
        if self.settings['timer'] and not self.bot() and g.phase != 'over':
            left = max(0, math.ceil(self.time_left))
            rect(surf, SW - 34, 1, 33, 11, C['red'] if left <= 10 and int(now / .26) % 2 else C['ink'])
            text(surf, f'{left}S', SW - 4, 3, C['white'], 1, 'r')
        else:
            enemy = g.hq_unit(1 - p)
            known = vis is None or g.hq[1 - p] in vis
            text(surf, f"ENEMY HQ {enemy.hp if enemy and known else '?'}", SW - 3, 3, SIDES[1 - p]['main'], 1, 'r', C['ink'])

    def draw_info(self, surf, vis):
        g, y0, i = self.g, SH - BOTTOM, self.cur
        rect(surf, 0, y0, SW, BOTTOM, C['paper'])
        rect(surf, 0, y0, SW, 1, C['ink'])
        rect(surf, 0, y0 + 1, SW, 1, C['paper_dark'])
        n, seen = g.map.nodes[i], vis is None or i in vis
        side, kind = (g.owner(i) if seen else None), self.field.kinds[i]
        title = f"{SIDES[n.hq]['name']} HQ" if kind == 'hq' else 'BARRACKS (+1 SOLDIER)' if n.barracks else kind.upper()
        text(surf, title, 4, y0 + 4, SIDES[n.hq]['dark'] if kind == 'hq' else C['ink'])
        if kind != 'hq':
            text(surf, ('EMPTY' if seen else 'UNKNOWN') if side is None else SIDES[side]['name'], 4 + text_width(title) + 6, y0 + 4,
                 C['grey'] if side is None else SIDES[side]['dark'])
        if seen:
            x = 4
            for t in ORDER + ['hq']:
                grp = [u for u in g.units[i] if u.type == t]
                if not grp:
                    continue
                if t == 'hq':
                    text(surf, f'HP {grp[0].hp}', SW - 44, y0 + 4, C['ink'], 1, 'r')
                    continue
                img = unit_image('icons', t, grp[0].side)
                blit(surf, img, x, y0 + 24 - img.get_height())
                text(surf, len(grp), x + img.get_width() + 1, y0 + 17, C['ink'])
                x += img.get_width() + text_width(len(grp)) + 4
        text(surf, self.hint(), 4, y0 + 30, C['dim'])
        portrait(surf, g.cur, self.mood_of(g.cur), SW - 37, y0 + 3, hud=True)

    def hint(self):
        g, p, i, mode = self.g, self.g.cur, self.cur, self.mode
        if g.phase == 'over':
            return ''
        if self.bot():
            return f"{SIDES[p]['name']} IS ON THE MOVE..."
        if self.script:
            return ''
        if mode == 'peek':
            return 'LOOKING AROUND · ENTER/ESC: BACK TO MOVE IN'
        if mode == 'pick_buy':
            return f"ENTER: BUILD {name(self.buy_type)} HERE ({UNITS[self.buy_type]['cost']} SOLDIERS)"
        if mode == 'pick_dest':
            ok = i in g.destinations(p, self.src, self.group_from(self.src, self.counts))
            return 'ENTER: MARCH HERE' if ok else 'ENTER ON ANY OTHER OUTPOST: CANCEL'
        if mode == 'pick_target':
            return 'ENTER: ATTACK THIS OUTPOST' if i in g.targets(p, self.src) else "CAN'T ATTACK THIS ONE · ESC: BACK"
        if g.phase == 'gather':
            if g.to_place > 0:
                return f'ENTER: PLACE SOLDIER ({g.to_place} LEFT)' if g.can_place(p, i) else 'PLACE ON YOUR OUTPOSTS OR NEXT TO THEM'
            return 'ENTER: BUY MENU'
        if g.phase == 'march':
            return 'ENTER: CHOOSE WHO MARCHES' if g.owner(i) == p and g.movable(i) else 'ESC: MENU (SKIP MARCH / END TURN)'
        if g.turn == 1:
            return 'FIRST TURN: DEPLOY ONLY · ESC: END TURN'
        return 'ENTER: ATTACK FROM HERE' if g.owner(i) == p and g.targets(p, i) else 'ESC: MENU (END TURN)'

    def draw_pass(self, surf, now):
        p = self.g.cur
        surf.fill(pygame.Color('#0b0d08'))
        portrait(surf, p, 'focus', SW // 2 - 28, 40)
        text(surf, SIDES[p]['commander'], SW / 2, 102, SIDES[p]['light'], 1, 'c')
        text(surf, f"{SIDES[p]['name']}'S TURN", SW / 2, 115, SIDES[p]['main'], 2, 'c')
        text(surf, 'FOG OF WAR IS ON.', SW / 2, 145, C['white'], 1, 'c')
        text(surf, f"HAND THE CONTROLS TO {SIDES[p]['name']}.", SW / 2, 157, C['white'], 1, 'c')
        if int(now / .5) % 2:
            text(surf, 'PRESS ENTER', SW / 2, 185, C['highlight'], 1, 'c')
