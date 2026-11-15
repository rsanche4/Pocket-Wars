"""The map generator: makes a ready-to-play map from a few settings (MAP EDITOR > + RANDOM MAP).

Maps are built the way the editor's MIRROR makes them: every change is copied to the opposite spot, turned around,
so both armies always get the same map. Step by step, on a full grid of roads:
  1. HQs on the left and right edges.          5. creeks: single river links here and there.
  2. holes: a few outposts taken out.           6. gaps: roads taken out, for winding paths.
  3. rivers: lines of river across the map,     7. diagonal roads.
  4. ... with bridges wherever needed to cross. 8. barracks, mostly towards the middle.
After every change the map must still be fair to play (see playable()), or that change is undone.
"""
import random

from .data import parse_map, map_problems, reachable

OPTIONS = {
    'size': ['SMALL', 'MEDIUM', 'LARGE', 'HUGE'],
    'theme': ['RANDOM', 'GRASS', 'DESERT', 'BEACH', 'SNOW'],
    'rivers': ['NONE', 'FEW', 'MANY'],
    'roads': ['FULL', 'GAPS', 'WINDING'],
    'barracks': ['FEW', 'SOME', 'MANY'],
    'diagonals': ['OFF', 'SOME'],
}
DEFAULTS = {'size': 'MEDIUM', 'theme': 'RANDOM', 'rivers': 'FEW', 'roads': 'GAPS', 'barracks': 'SOME', 'diagonals': 'SOME'}
SIZES = {'SMALL': [(4, 3), (5, 3), (6, 2)], 'MEDIUM': [(6, 4), (5, 5), (7, 3)],
         'LARGE': [(7, 5), (8, 4), (6, 6)], 'HUGE': [(8, 6), (9, 6), (9, 7)]}        # (outposts across, down)
WORDS = {
    'grass': (['OAK', 'MEADOW', 'CLOVER', 'FERN', 'GREEN', 'HAZEL'], ['VALLEY', 'RIDGE', 'FIELDS', 'CROSSING', 'HOLLOW', 'PASS']),
    'desert': (['DUNE', 'SAND', 'SUN', 'DUST', 'MESA', 'CANYON'], ['FLATS', 'PASS', 'RIDGE', 'WASTES', 'BASIN', 'TRAIL']),
    'beach': (['CORAL', 'TIDE', 'SHELL', 'REEF', 'PALM', 'GULL'], ['BAY', 'COVE', 'ISLES', 'SHORE', 'KEYS', 'LAGOON']),
    'snow': (['FROST', 'ICE', 'SNOW', 'PINE', 'WINTER', 'POLAR'], ['PEAK', 'PASS', 'FIELDS', 'RIDGE', 'HOLLOW', 'DRIFT']),
}


def generate(settings, seed, taken=()):
    """A new map as {'name', 'theme', 'blurb', 'art'}. The same settings and seed always give the same map.
    taken = names already in use (the new name won't clash)."""
    s = {**DEFAULTS, **settings}
    rng = random.Random(seed)
    theme = rng.choice(list(WORDS)) if s['theme'] == 'RANDOM' else s['theme'].lower()
    art = None
    for _ in range(60):                                  # nearly always the first try
        art = Builder(s, rng).build()
        if art:
            break
    art = art or fallback(s)
    first, second = WORDS[theme]
    name, taken = f'{rng.choice(first)} {rng.choice(second)}', {t.upper() for t in taken}
    base, n = name, 2
    while name in taken:
        name, n = f'{base} {n}', n + 1
    text = ''.join(art)
    blurb = (f"Made by the map generator: {text.count('G')} barracks, {text.count('=')} "
             f"bridge{'' if text.count('=') == 1 else 's'} and {text.count('~')} river crossings.")
    return {'name': name, 'theme': theme, 'blurb': blurb, 'art': art}


def fallback(s):
    """A plain grid of roads (only if every try failed, which shouldn't happen)."""
    cols, rows = SIZES[s['size']][0]
    w, h = cols * 2 - 1, rows * 2 - 1
    art = [[('o' if r % 2 == 0 and c % 2 == 0 else '-' if r % 2 == 0 else '|' if c % 2 == 0 else ' ') for c in range(w)] for r in range(h)]
    mid = (rows - 1) // 2 * 2
    art[mid][0], art[h - 1 - mid][w - 1] = 'H', 'h'
    return [''.join(r).rstrip() for r in art]


class Builder:
    def __init__(self, s, rng):
        self.s, self.rng = s, rng
        self.cols, self.rows = rng.choice(SIZES[s['size']])
        self.w, self.h = self.cols * 2 - 1, self.rows * 2 - 1
        self.art = [[('o' if r % 2 == 0 and c % 2 == 0 else '-' if r % 2 == 0 else '|' if c % 2 == 0 else ' ')
                     for c in range(self.w)] for r in range(self.h)]
        self.islands_ok = s['rivers'] == 'MANY'           # with lots of rivers, a few outposts may be helicopter-only

    # ---------- the grid ----------
    def mirror(self, y, x):
        return self.h - 1 - y, self.w - 1 - x

    def first_half(self, y, x):
        my, mx = self.mirror(y, x)
        return y * self.w + x <= my * self.w + mx

    def put(self, y, x, ch):
        """Change one spot and its mirror (an HQ becomes the other side's HQ)."""
        self.art[y][x] = ch
        my, mx = self.mirror(y, x)
        self.art[my][mx] = {'H': 'h', 'h': 'H'}.get(ch, ch)

    def outposts(self):
        return [(y, x) for y in range(0, self.h, 2) for x in range(0, self.w, 2) if self.art[y][x] != ' ']

    def links(self, kinds=('-', '|')):
        """Link spots (across and down) holding one of these characters."""
        return [(y, x) for y in range(self.h) for x in range(self.w)
                if (y + x) % 2 == 1 and self.art[y][x] in kinds]

    def ends(self, y, x):
        return ((y, x - 1), (y, x + 1)) if y % 2 == 0 else ((y - 1, x), (y + 1, x))

    def save(self):
        return [r[:] for r in self.art]

    def as_map(self):
        return parse_map({'name': '', 'art': [''.join(r) for r in self.art]})

    def playable(self):
        """Both HQs, joined by roads (so ground armies can meet); every outpost joined to the rest; HQs not
        next door to each other."""
        m = self.as_map()
        if map_problems(m):
            return False
        green = next(i for i, n in enumerate(m.nodes) if n.hq == 0)
        tan = next(i for i, n in enumerate(m.nodes) if n.hq == 1)
        by_road = reachable(m, green, roads_only=True)
        if tan not in by_road or len(reachable(m, green, roads_only=False)) < len(m.nodes):
            return False
        if not self.islands_ok and len(by_road) < len(m.nodes):
            return False
        return road_steps(m, green, tan) >= max(3, self.cols // 2 + 1)

    def attempt(self, change):
        """Make a change; undo it if the map stops being playable."""
        before = self.save()
        change()
        if self.playable():
            return True
        self.art = before
        return False

    # ---------- the steps ----------
    def build(self):
        s, rng = self.s, self.rng
        rows = list(range(0, self.h, 2))
        mid = [r for r in rows if abs(r - (self.h - 1) / 2) <= self.h / 4] or rows
        self.put(rng.choice(mid), 0, 'H')
        if not self.playable():
            return None
        size = self.cols * self.rows
        holes = {'FULL': 0, 'GAPS': int(size >= 30 and rng.random() < .5), 'WINDING': 1 + (size >= 35)}[s['roads']]
        self.holes(holes)
        rivers = {'NONE': 0, 'FEW': 1, 'MANY': 2}[s['rivers']] + (s['rivers'] == 'MANY' and size >= 35)
        for _ in range(rivers):
            self.river()
        creeks = {'NONE': 0, 'FEW': rng.randint(0, 1) + size // 40, 'MANY': rng.randint(1, 3) + size // 30}[s['rivers']]
        self.creeks(creeks)
        self.gaps({'FULL': 0, 'GAPS': .1, 'WINDING': .22}[s['roads']])
        if s['diagonals'] == 'SOME':
            self.diagonals(1 + (size >= 35))
        self.barracks({'FEW': 1, 'SOME': 2, 'MANY': 3}[s['barracks']] + (s['barracks'] != 'FEW' and size >= 30))
        if not self.playable():
            return None
        return [''.join(r).rstrip() for r in self.art]

    def holes(self, n):
        spots = [(y, x) for y, x in self.outposts() if self.first_half(y, x) and self.art[y][x] == 'o' and 0 < x < self.w - 1]
        self.rng.shuffle(spots)
        for y, x in spots:
            if n <= 0:
                break

            def dig(y=y, x=x):
                self.put(y, x, ' ')
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if (dy or dx) and 0 <= y + dy < self.h and 0 <= x + dx < self.w:
                            self.put(y + dy, x + dx, ' ')
            n -= self.attempt(dig)

    def river(self):
        """A line of river from the top edge to the bottom, wandering sideways, then bridges where it must be crossed."""
        rng, cols = self.rng, self.cols
        if cols < 3:
            return
        gaps = list(range(1, cols - 2)) or list(range(cols - 1))     # between column g and g + 1 (not hugging an HQ)
        g = rng.choice(gaps)
        before = self.save()
        path = []
        for r in range(self.rows):
            path.append(g)
            if rng.random() < .2:                      # now and then the river bends
                g = max(0, min(cols - 2, g + rng.choice((-1, 1))))
        for r, g in enumerate(path):
            if self.art[r * 2][g * 2 + 1] != ' ':
                self.put(r * 2, g * 2 + 1, '~')
            if r + 1 < len(path) and path[r + 1] != g:          # the river turns: it runs down between two rows
                a, b = sorted((g, path[r + 1]))
                for c in range(a + 1, b + 1):
                    if self.art[r * 2 + 1][c * 2] != ' ':
                        self.put(r * 2 + 1, c * 2, '~')
        self.bridge(before)

    def bridge(self, before):
        """Turn river links into bridges until the map works again (and sometimes one more, for choice)."""
        tries = 0
        while not self.playable() and tries < 30:
            tries += 1
            crossings = self.links(('~',))
            if not crossings:
                break
            m = self.as_map()
            green = next(i for i, n in enumerate(m.nodes) if n.hq == 0)
            near = reachable(m, green, roads_only=True)
            self.rng.shuffle(crossings)
            for y, x in crossings:                       # a river link with road on one side only joins new land
                a, b = self.ends(y, x)
                ia, ib = self.node_at(m, a), self.node_at(m, b)
                if ia is not None and ib is not None and (ia in near) != (ib in near):
                    self.put(y, x, '=')
                    break
            else:
                y, x = crossings[0]
                self.put(y, x, '=')
        if not self.playable():
            self.art = before                            # couldn't make it work: no river this time
            return
        if self.rng.random() < .5:
            crossings = [c for c in self.links(('~',)) if c[0] % 2 == 0]
            if crossings:
                self.put(*self.rng.choice(crossings), '=')

    def node_at(self, m, spot):
        y, x = spot
        return next((i for i, n in enumerate(m.nodes) if (n.row, n.col) == (y // 2, x // 2)), None)

    def creeks(self, n):
        spots = [s for s in self.links() if self.first_half(*s)]
        self.rng.shuffle(spots)
        for y, x in spots:
            if n <= 0:
                break
            n -= self.attempt(lambda y=y, x=x: self.put(y, x, '~'))

    def gaps(self, chance):
        spots = [s for s in self.links() if self.first_half(*s)]
        self.rng.shuffle(spots)
        for y, x in spots:
            if self.rng.random() < chance and not self.touches_hq(y, x):
                self.attempt(lambda y=y, x=x: self.put(y, x, ' '))

    def touches_hq(self, y, x):
        return any(self.art[a][b] in 'Hh' for a, b in self.ends(y, x))

    def diagonals(self, n):
        """n diagonal shortcuts per side (an X counts as one)."""
        spots = [(y, x) for y in range(1, self.h, 2) for x in range(1, self.w, 2) if self.first_half(y, x)]
        self.rng.shuffle(spots)
        for y, x in spots:
            if n <= 0:
                break
            ok = lambda a, b: self.art[a][b] != ' '
            back = ok(y - 1, x - 1) and ok(y + 1, x + 1)          # '\'
            fwd = ok(y - 1, x + 1) and ok(y + 1, x - 1)           # '/'
            choice = [c for c, good in (('\\', back), ('/', fwd), ('X', back and fwd)) if good]
            if choice:
                n -= self.attempt(lambda y=y, x=x, c=self.rng.choice(choice): self.put(y, x, c))

    def barracks(self, n):
        """n barracks per side on plain outposts, more likely towards the middle and away from the HQs."""
        spots = [(y, x) for y, x in self.outposts() if self.first_half(y, x) and self.art[y][x] == 'o']
        by_hq = lambda y, x: any(self.art[a][b] in 'Hh' for a, b in near(y, x, self.h, self.w))
        for _ in range(n):
            if not spots:
                break
            weights = [(1 + x) * (.2 if by_hq(y, x) else 1) for y, x in spots]
            y, x = self.rng.choices(spots, weights)[0]
            spots.remove((y, x))
            self.put(y, x, 'G')


def near(y, x, h, w):
    """The outpost spots one road away (across, down or diagonal)."""
    return [(y + dy, x + dx) for dy in (-2, 0, 2) for dx in (-2, 0, 2) if (dy or dx) and 0 <= y + dy < h and 0 <= x + dx < w]


def road_steps(m, a, b):
    """How many road links an army walks from outpost a to b (a big number if it can't)."""
    adj = {i: [] for i in range(len(m.nodes))}
    for e in m.links:
        if e.kind == 'road':
            adj[e.a].append(e.b)
            adj[e.b].append(e.a)
    dist, todo = {a: 0}, [a]
    for i in todo:
        for j in adj[i]:
            if j not in dist:
                dist[j] = dist[i] + 1
                todo.append(j)
    return dist.get(b, 99)
