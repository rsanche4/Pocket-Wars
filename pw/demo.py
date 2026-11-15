"""Make-believe battles drawn with the real battlefield code: the title screen backdrop and How to Play pictures."""
import math
import random
import pygame

from .data import ORDER, UNITS, parse_map
from .rules import Game, flies
from .field import Field, March
from .gfx import THEMES, C, rect, ellipse, text


def empty_game(m):
    """A Game on map m with nobody on the board yet."""
    g = Game(m)
    g.units = [[] for _ in m.nodes]
    g.next_id = 1
    return g


def put(g, i, side, t, n=1, hp=None):
    for _ in range(n):
        g.add(i, side, t)
        if hp is not None:
            g.units[i][-1].hp = hp() if callable(hp) else hp


def mid_battle(g):
    """Fill the board like a battle in progress: each side holds the ground nearer its HQ, the front line is busiest."""
    n = len(g.units)

    def steps(start):
        d, todo = {start: 0}, [start]
        while todo:
            a = todo.pop(0)
            for b in g.adj[a]:
                if b not in d:
                    d[b] = d[a] + 1
                    todo.append(b)
        return d

    d0, d1 = steps(g.hq[0]), steps(g.hq[1])
    side = []
    for i in range(n):
        diff = d1.get(i, 99) - d0.get(i, 99)
        if i in g.hq:
            side.append(g.hq.index(i))
        elif diff >= 1:
            side.append(0 if random.random() < .8 else None)
        elif diff <= -1:
            side.append(1 if random.random() < .8 else None)
        else:
            side.append(random.choice((0, 1)) if random.random() < .6 else None)
    hurt = lambda t: lambda: max(1, round(UNITS[t]['hp'] * (.35 + random.random() * .65)))
    for i, s in enumerate(side):
        if s is None:
            continue
        front = any(side[j] == 1 - s for j in g.adj[i])
        if i == g.hq[s]:
            put(g, i, s, 'hq', hp=random.randint(55, 100))
        put(g, i, s, 'soldier', 1 + random.randrange(4 if front else 2), hurt('soldier'))
        if front and random.random() < .55:
            t = random.choice(('tank', 'halftrack'))
            put(g, i, s, t, hp=hurt(t))
        if random.random() < (.25 if front else .1):
            put(g, i, s, 'helicopter', hp=hurt('helicopter'))


class LiveBattle:
    """A battle that plays itself a little: groups march now and then, the front line trades fire, the view pans."""
    def __init__(self, m, k, now):
        self.g = empty_game(m)
        mid_battle(self.g)
        self.field = Field(self.g, k)
        self.k, self.start = k, now
        self.next_march = self.next_shot = now + 1
        self.shots = []

    def tick(self, now):
        g, f = self.g, self.field
        if f.march and f.march.done(now):
            a, b = f.march.path
            g.units[a] = [u for u in g.units[a] if u not in f.march.units]
            g.units[b] += f.march.units
            f.march = None
        if not f.march and now > self.next_march:
            self.next_march = now + .9 + random.random() * 1.7
            options = []
            for a in range(len(g.units)):
                side, movers = g.owner(a), g.movable(a)
                if side is None or len(movers) < 2:
                    continue
                for b in g.adj[a]:
                    if g.owner(b) not in (None, side):
                        continue
                    for t in ORDER:
                        grp = [u for u in movers if u.type == t and (g.road(a, b) or flies(t))]
                        if grp and len(grp) < len(movers):
                            options.append((a, b, grp[:random.randint(1, min(2, len(grp)))]))
            if options:
                a, b, grp = random.choice(options)
                f.march = March([a, b], grp, .52 if flies(grp[0].type) else .76, now)
        if now > self.next_shot:
            self.next_shot = now + .5 + random.random() * 1.5
            pairs = [(a, b) for a in range(len(g.units)) if g.owner(a) is not None for b in g.adj[a] if g.owner(b) == 1 - g.owner(a)]
            if pairs:
                self.shots.append((*random.choice(pairs), now))
        self.shots = [s for s in self.shots if now - s[2] < .7]

    def camera(self, now, w, h):
        """Pans slowly back and forth across the map."""
        ww, wh = self.field.world.get_size()
        t = now - self.start
        ax, ay = (ww - w) / 2, (wh - h) / 2
        return round(ax + ax * math.sin(t * .06) if ww > w else ax), round(ay + ay * math.sin(t * .045 + 1.2) if wh > h else ay)

    def draw(self, surf, now, w, h):
        self.tick(now)
        cam = self.camera(now, w, h)
        self.field.draw(surf, cam, now)
        nodes = self.g.map.nodes
        for a, b, t0 in self.shots:          # tracer, then a burst on the target
            t = (now - t0) / .7
            ax, ay = nodes[a].x * self.k - cam[0], nodes[a].y * self.k - cam[1] - 8
            bx, by = nodes[b].x * self.k - cam[0], nodes[b].y * self.k - cam[1] - 8
            if t < .35:
                q = t / .35
                rect(surf, ax + (bx - ax) * q - 1, ay + (by - ay) * q - 1, 3, 2, pygame.Color('#fff3a0'))
                ellipse(surf, ax, ay, 2, 2, pygame.Color('#ffd23a'))
            else:
                r = round(2 + (t - .35) * 14)
                ellipse(surf, bx, by, r, r, pygame.Color(255, 170, 40, 204))
                ellipse(surf, bx, by, round(r * .5), round(r * .5), pygame.Color('#fff3a0'))


def big_maps(maps):
    """Built-in maps large enough to fill the title screen."""
    return [m for m in maps if not m.custom and m.w * .46 >= 380 and m.h * .46 >= 280]


def title_battle(maps, now, avoid=None):
    pool = [m for m in big_maps(maps) if m is not avoid] or [m for m in maps if not m.custom]
    m = random.choice(pool)
    return LiveBattle(m, max(.42, 380 / m.w, 280 / m.h), now)


# ---------------------------------------------------------------- small scenes for How to Play
class Scene:
    """A tiny hand-made battle: art (like a map file), units to place, and extras to show."""
    def __init__(self, name, theme, art, k, units, labels=(), link_labels=(), glow=(), cursor=None, loop=None, lift=6):
        self.g = empty_game(parse_map({'name': name, 'theme': theme, 'art': art}))
        at = lambda c, r: next(i for i, n in enumerate(self.g.map.nodes) if n.col == c and n.row == r)
        for (c, r), side, t, count, *hp in units:
            put(self.g, at(c, r), side, t, count, hp[0] if hp else None)
        self.field = Field(self.g, k)
        self.k, self.lift = k, lift
        self.labels = [(at(*cr), s, col) for cr, s, col in labels]
        self.link_labels = [(at(*a), at(*b), s) for a, b, s in link_labels]
        self.glow = {at(*cr) for cr in glow}
        self.cursor = at(*cursor) if cursor else None
        self.loop = loop and (loop[0], [at(*cr) for cr in loop[1]], loop[2])   # (unit type, path, rest seconds)
        self.next, self.walked = 0, None

    def tick(self, now):
        """Replays a march: the group walks the path, waits, then pops back to the start."""
        if not self.loop or now < self.next:
            return
        t, path, rest = self.loop
        f, g, a, b = self.field, self.g, path[0], path[-1]
        if f.march:
            if f.march.done(now):
                g.units[a] = [u for u in g.units[a] if u not in f.march.units]
                g.units[b] += f.march.units
                self.walked, f.march, self.next = f.march.units, None, now + rest
        elif self.walked:
            g.units[b] = [u for u in g.units[b] if u not in self.walked]
            g.units[a] += self.walked
            self.walked, self.next = None, now + .7
        else:
            grp = [u for u in g.units[a] if u.type == t][:1 if t == 'soldier' else None]
            if grp:
                f.march = March(path, grp, .42, now)

    def draw(self, surf, now, w, h, fog_side=None, blackout=False):
        self.tick(now)
        xs = [n.x * self.k for n in self.g.map.nodes]
        ys = [n.y * self.k for n in self.g.map.nodes]
        cam = round((min(xs) + max(xs)) / 2 - w / 2), round((min(ys) + max(ys)) / 2 - h / 2 - self.lift)
        surf.fill(THEMES[self.g.map.theme]['base'])
        vis = self.g.sight(fog_side) if fog_side is not None else None
        self.field.draw(surf, cam, now, vis, blackout, self.glow, self.cursor)
        pos = lambda i: self.field.screen_pos(i, cam)
        for i, s, col in self.labels:
            x, y = pos(i)
            text(surf, s, x, y + 10, col, 1, 'c', C['ink'])
        for a, b, s in self.link_labels:
            (x1, y1), (x2, y2) = pos(a), pos(b)
            text(surf, s, (x1 + x2) / 2, (y1 + y2) / 2 + 12, C['white'], 1, 'c', C['ink'])
