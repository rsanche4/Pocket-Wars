"""Loading the game's data files: unit stats, CPU settings and maps.

Maps are small JSON files: {"name", "theme", "blurb", "art"}. Every map is a file in maps/, including the ones you make in the editor.
The "art" is a drawing made of text. Outposts sit on even rows and even columns; the characters between them are links:
    o outpost   G barracks (+1 soldier a turn)   H Green HQ   h Tan HQ   (space = nothing)
    - and |  road        ~ river (only helicopters cross)        = bridge
    / \\ X   diagonal roads (on odd rows and odd columns)
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPS_DIR = os.path.join(ROOT, 'maps')
DEFAULT_MAPS_DIR = os.path.join(ROOT, 'data', 'default-maps')     # untouched copies of the built-in maps


def load_json(*path):
    with open(os.path.join(ROOT, *path), encoding='utf-8') as f:
        return json.load(f)


UNITS = load_json('data', 'units.json')
ORDER = [t for t in UNITS if t != 'hq']          # unit types that can move, in display order
AI = load_json('data', 'ai.json')

# spacing of the map grid, in map units (the screen draws these scaled down)
STEP_X, STEP_Y, MARGIN_X, MARGIN_Y = 170, 150, 120, 110


@dataclass
class Node:
    x: int
    y: int
    barracks: bool
    hq: int            # 0 = Green HQ, 1 = Tan HQ, -1 = not an HQ
    col: int
    row: int


@dataclass
class Link:
    a: int
    b: int
    kind: str          # 'road' or 'river'
    bridge: bool = False


@dataclass
class Map:
    name: str
    theme: str
    blurb: str
    art: list
    nodes: list = field(default_factory=list)
    links: list = field(default_factory=list)
    w: int = 0
    h: int = 0
    path: str = ''


def parse_map(d, path=''):
    """Turn a map's text drawing into outposts (nodes) and the links between them."""
    art = d['art']
    rows, cols = len(art), max(len(r) for r in art)
    art = [r.ljust(cols) for r in art]
    m = Map(d['name'], d.get('theme', 'grass'), d.get('blurb', 'A custom battlefield.'), d['art'], path=path)
    index = {}
    for r in range(0, rows, 2):
        for c in range(0, cols, 2):
            ch = art[r][c]
            if ch in 'oGHh':
                index[(r // 2, c // 2)] = len(m.nodes)
                m.nodes.append(Node(MARGIN_X + c // 2 * STEP_X, MARGIN_Y + r // 2 * STEP_Y, ch == 'G',
                                    0 if ch == 'H' else 1 if ch == 'h' else -1, c // 2, r // 2))

    def link(p, q, ch):
        if p in index and q in index and ch in '-|~=/\\X':
            m.links.append(Link(index[p], index[q], 'river' if ch == '~' else 'road', ch == '='))

    for r in range(rows):
        for c in range(cols):
            ch = art[r][c]
            if r % 2 == 0 and c % 2 == 1:
                link((r // 2, c // 2), (r // 2, c // 2 + 1), ch)
            elif r % 2 == 1 and c % 2 == 0:
                link((r // 2, c // 2), (r // 2 + 1, c // 2), ch)
            elif r % 2 == 1 and c % 2 == 1:
                if ch in '\\X':
                    link((r // 2, c // 2), (r // 2 + 1, c // 2 + 1), '\\')
                if ch in '/X':
                    link((r // 2, c // 2 + 1), (r // 2 + 1, c // 2), '/')
    m.w = 2 * MARGIN_X + cols // 2 * STEP_X
    m.h = 2 * MARGIN_Y + rows // 2 * STEP_Y
    return m


def map_problems(m):
    """Reasons a map can't be played yet (empty list = playable)."""
    out = []
    greens = [i for i, n in enumerate(m.nodes) if n.hq == 0]
    tans = [i for i, n in enumerate(m.nodes) if n.hq == 1]
    if not greens:
        out.append('PLACE A GREEN HQ')
    if not tans:
        out.append('PLACE A TAN HQ')
    if len(greens) > 1 or len(tans) > 1:
        out.append('ONLY ONE HQ EACH')
    if greens and tans and tans[0] not in reachable(m, greens[0], roads_only=False):
        out.append('HQS ARE NOT CONNECTED')
    return out


def road_steps(m, a, b):
    """How many road links an army walks from outpost a to b (99 if it can't)."""
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


def map_info(m):
    """What a map is like, without showing it (so nobody learns the layout before a fog-of-war battle):
    for each of size, barracks, water, roads and HQ gap a level of 0-5 pips and a word, plus a few 'vibe' tags."""
    n = max(1, len(m.nodes))
    barracks = sum(x.barracks for x in m.nodes)
    rivers = sum(e.kind == 'river' for e in m.links)
    bridges = sum(e.bridge for e in m.links)
    roads = sum(e.kind == 'road' for e in m.links)
    shortcuts = sum({'/': 1, '\\': 1, 'X': 2}.get(ch, 0) for r, row in enumerate(m.art) for c, ch in enumerate(row) if r % 2 and c % 2)
    clamp = lambda v: max(0, min(5, round(v)))
    greens = [i for i, x in enumerate(m.nodes) if x.hq == 0]
    tans = [i for i, x in enumerate(m.nodes) if x.hq == 1]
    steps = road_steps(m, greens[0], tans[0]) if greens and tans else 99
    heli_only = n - len(reachable(m, greens[0], roads_only=True)) if greens else 0
    water = rivers / max(1, rivers + roads)
    open_ = roads / n
    size, size_pips = (('SMALL', 1) if n < 15 else ('MEDIUM', 2) if n < 24 else ('LARGE', 3) if n < 32 else
                       ('LARGE', 4) if n < 40 else ('HUGE', 5))
    wet = clamp(water * 12) if rivers else 0
    cols, rows_ = (max(len(r) for r in m.art) + 1) // 2, (len(m.art) + 1) // 2
    rows = [
        ('SIZE', size_pips, size),
        ('BARRACKS', clamp(barracks / n * 20), str(barracks)),
        ('WATER', max(wet, 1 if rivers else 0), ['NONE', 'A LITTLE', 'SOME', 'PLENTY', 'LOTS', 'LOTS'][max(wet, 1 if rivers else 0)]),
        ('ROADS', clamp((open_ - .9) * 6), 'TWISTY' if open_ < 1.25 else 'OPEN' if open_ < 1.6 else 'WIDE OPEN'),
        ('HQ GAP', clamp(steps - 2) if steps < 99 else 0,
         'NO ROAD' if steps == 99 else 'NEAR' if steps <= 4 else 'MIDDLE' if steps <= 6 else 'FAR'),
    ]
    tags = []
    if steps <= 4:
        tags.append('CLOSE QUARTERS')
    elif 8 <= steps < 99:
        tags.append('LONG MARCH')
    if barracks / n >= .2:
        tags.append('BARRACKS RACE')
    if water >= .25:
        tags.append('RIVER COUNTRY')
    if rivers >= 3 and 0 < bridges <= 2:
        tags.append('CHOKEPOINTS')
    if heli_only:
        tags.append('HELICOPTER ISLANDS')
    if shortcuts:
        tags.append('SHORTCUTS')
    if not rivers and open_ >= 1.4:
        tags.append('OPEN FIELD')
    if cols >= rows_ * 2.5:
        tags.append('LONG AND NARROW')
    return {'rows': rows, 'tags': tags[:3] or ['CLASSIC'], 'outposts': n}


def reachable(m, start, roads_only):
    adj = {i: [] for i in range(len(m.nodes))}
    for e in m.links:
        if e.kind == 'road' or not roads_only:
            adj[e.a].append(e.b)
            adj[e.b].append(e.a)
    seen, todo = {start}, [start]
    while todo:
        for b in adj[todo.pop()]:
            if b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def load_maps():
    """Every map in maps/, in file-name order. Broken files are skipped."""
    out = []
    os.makedirs(MAPS_DIR, exist_ok=True)
    for name in sorted(os.listdir(MAPS_DIR)):
        if not name.lower().endswith('.json'):
            continue
        path = os.path.join(MAPS_DIR, name)
        try:
            with open(path, encoding='utf-8') as f:     # kept relative to the game folder, e.g. maps/01-boot-camp.json
                out.append(parse_map(json.load(f), relative(path)))
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f'Pocket Wars: skipped map {path}: {e}')
    if not out and missing_defaults():       # every map was deleted: bring the built-in ones back (the game needs one)
        restore_defaults()
        return load_maps()
    return out


def default_of(path):
    """The untouched original of a built-in map (e.g. maps/01-boot-camp.json), or None for maps you made."""
    original = os.path.join(DEFAULT_MAPS_DIR, os.path.basename(path or ''))
    return original if path and os.path.isfile(original) else None


def reset_map(path):
    """Put a built-in map back the way it came with the game. Returns its contents."""
    shutil.copyfile(default_of(path), os.path.join(ROOT, path))
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return json.load(f)


def missing_defaults():
    """Built-in maps whose file was deleted from maps/."""
    return [n for n in sorted(os.listdir(DEFAULT_MAPS_DIR)) if n.endswith('.json') and not os.path.exists(os.path.join(MAPS_DIR, n))]


def restore_defaults():
    for n in missing_defaults():
        shutil.copyfile(os.path.join(DEFAULT_MAPS_DIR, n), os.path.join(MAPS_DIR, n))


def save_map(name, theme, art, old_path='', blurb='A custom battlefield.'):
    """Write a map into maps/ (that file is also what you share with friends). Returns its path.
    Saving over a map keeps anything else in its file (like a built-in map's blurb)."""
    os.makedirs(MAPS_DIR, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'map'
    path = os.path.join(ROOT, old_path) if old_path else os.path.join(MAPS_DIR, slug + '.json')
    n = 2
    while not old_path and os.path.exists(path):      # never overwrite another map (e.g. a friend's with the same name)
        path = os.path.join(MAPS_DIR, f'{slug}-{n}.json')
        n += 1
    d = {'name': name, 'theme': theme, 'blurb': blurb, 'art': art}
    try:
        with open(path, encoding='utf-8') as f:
            d = {**json.load(f), 'name': name, 'theme': theme, 'art': art}
    except (OSError, ValueError):
        pass
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
        f.write('\n')
    return relative(path)


def relative(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')
