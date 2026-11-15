"""Loading the game's data files: unit stats, CPU settings and maps.

Maps are small JSON files: {"name", "theme", "blurb", "art"}. Built-in maps live in maps/, your own in my-maps/.
The "art" is a drawing made of text. Outposts sit on even rows and even columns; the characters between them are links:
    o outpost   G barracks (+1 soldier a turn)   H Green HQ   h Tan HQ   (space = nothing)
    - and |  road        ~ river (only helicopters cross)        = bridge
    / \\ X   diagonal roads (on odd rows and odd columns)
"""
import json
import os
import re
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPS_DIR = os.path.join(ROOT, 'maps')
MY_MAPS_DIR = os.path.join(ROOT, 'my-maps')


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
    custom: bool = False
    path: str = ''


def parse_map(d, custom=False, path=''):
    """Turn a map's text drawing into outposts (nodes) and the links between them."""
    art = d['art']
    rows, cols = len(art), max(len(r) for r in art)
    art = [r.ljust(cols) for r in art]
    m = Map(d['name'], d.get('theme', 'grass'), d.get('blurb', 'A custom battlefield.'), d['art'], custom=custom, path=path)
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
    """Built-in maps first (in file-name order), then everything in my-maps/. Broken files are skipped."""
    out = []
    os.makedirs(MY_MAPS_DIR, exist_ok=True)
    for folder, custom in ((MAPS_DIR, False), (MY_MAPS_DIR, True)):
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith('.json'):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, encoding='utf-8') as f:     # kept relative to the game folder, e.g. maps/01-boot-camp.json
                    out.append(parse_map(json.load(f), custom, relative(path)))
            except (OSError, ValueError, KeyError, TypeError) as e:
                print(f'Pocket Wars: skipped map {path}: {e}')
    return out


def save_my_map(name, theme, art, old_path=''):
    """Write a map into my-maps/ (that file is also what you share with friends). Returns its path."""
    os.makedirs(MY_MAPS_DIR, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'map'
    path = os.path.join(ROOT, old_path) if old_path else os.path.join(MY_MAPS_DIR, slug + '.json')
    n = 2
    while not old_path and os.path.exists(path):      # never overwrite another map (e.g. a friend's with the same name)
        path = os.path.join(MY_MAPS_DIR, f'{slug}-{n}.json')
        n += 1
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'theme': theme, 'blurb': 'A custom battlefield.', 'art': art}, f, indent=1)
        f.write('\n')
    return relative(path)


def relative(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')
