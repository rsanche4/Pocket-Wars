"""The ground under a battle, built once per map from the tiles in assets/terrain/<theme>/:
ground.png and water.png repeat like wallpaper, road.png is a strip repeated along each road, bridge.png sits on each
bridge, and decor.png (trees etc.) and rock.png are scattered where nothing else is."""
import math
import random
import pygame

from .data import STEP_X, STEP_Y
from .gfx import image, THEMES, C

KINDS = ['bunker', 'town', 'watchtower', 'town', 'bunker', 'watchtower', 'town']


def outpost_kinds(m):
    """Which building stands on each outpost (just looks; every outpost plays the same)."""
    return ['hq' if n.hq >= 0 else 'barracks' if n.barracks else KINDS[(n.col * 3 + n.row * 5 + i) % 7] for i, n in enumerate(m.nodes)]


def tiled(size, tile):
    s = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(0, size[1], tile.get_height()):
        for x in range(0, size[0], tile.get_width()):
            s.blit(tile, (x, y))
    return s


def cut_out(tile, shape):
    """Tile pattern kept only where `shape` (white on transparent) is drawn."""
    s = tiled(shape.get_size(), tile)
    s.blit(shape, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def thick_line(s, color, a, b, width):
    """A line with round ends."""
    pygame.draw.line(s, color, a, b, width)
    for p in (a, b):
        pygame.draw.circle(s, color, p, width // 2)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def build_world(m, k):
    """The map's ground as one image, k = screen pixels per map unit."""
    w, h = math.ceil(m.w * k), math.ceil(m.h * k)
    tile = lambda part: image(f'terrain/{m.theme}/{part}.png')
    sc = lambda v: round(v * k)
    nodes, links = m.nodes, m.links
    white = (255, 255, 255, 255)

    # rivers cross the middle of river links and bridges, at right angles to them
    water = []
    for e in links:
        if e.kind == 'river' or e.bridge:
            a, b = nodes[e.a], nodes[e.b]
            mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
            water.append((mx, my - STEP_Y / 2 - 4, mx, my + STEP_Y / 2 + 4) if abs(a.y - b.y) < 1 else (mx - STEP_X / 2 - 4, my, mx + STEP_X / 2 + 4, my))

    world = pygame.Surface((w, h))
    if m.theme == 'beach':     # sea everywhere, an island around each outpost, sand along the roads between them
        world.blit(tiled((w, h), tile('water')), (0, 0))
        land = pygame.Surface((w, h), pygame.SRCALPHA)
        for n in nodes:
            pygame.draw.circle(land, white, (sc(n.x), sc(n.y)), sc(84))
        for e in links:
            if e.kind == 'road' and not e.bridge:
                thick_line(land, white, (sc(nodes[e.a].x), sc(nodes[e.a].y)), (sc(nodes[e.b].x), sc(nodes[e.b].y)), sc(130))
        world.blit(cut_out(tile('ground'), land), (0, 0))
        shore = pygame.Surface((w, h), pygame.SRCALPHA)
        for n in nodes:
            pygame.draw.circle(shore, C['shore'], (sc(n.x), sc(n.y)), sc(84), max(1, sc(10)))
        world.blit(shore, (0, 0))
    else:
        world.blit(tiled((w, h), tile('ground')), (0, 0))
        river = pygame.Surface((w, h), pygame.SRCALPHA)
        for x1, y1, x2, y2 in water:
            thick_line(world, THEMES[m.theme]['water_edge'], (sc(x1), sc(y1)), (sc(x2), sc(y2)), sc(64))
            thick_line(river, white, (sc(x1), sc(y1)), (sc(x2), sc(y2)), sc(48))
        world.blit(cut_out(tile('water'), river), (0, 0))

    # roads (the strip turned to follow each road), bridges, and dotted markers on river links
    road = tile('road')
    for e in links:
        a, b = nodes[e.a], nodes[e.b]
        length = math.hypot(b.x - a.x, b.y - a.y) * k
        angle = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        center = (sc((a.x + b.x) / 2), sc((a.y + b.y) / 2))
        if e.kind == 'road':
            strip = tiled((math.ceil(length), road.get_height()), road)
            turned = pygame.transform.rotate(strip, -angle)
            world.blit(turned, turned.get_rect(center=center))
            if e.bridge:
                br = pygame.transform.rotate(tile('bridge'), -round(angle / 90) * 90)
                world.blit(br, br.get_rect(center=center))
        else:
            n = round(math.hypot(b.x - a.x, b.y - a.y) / 26)
            marker = pygame.Surface((sc(10), sc(10)), pygame.SRCALPHA)
            marker.fill(C['river_marker'])
            for s in range(2, n - 1):
                x, y = a.x + (b.x - a.x) * s / n, a.y + (b.y - a.y) * s / n
                world.blit(marker, (sc(x - 5), sc(y - 5)))

    # scenery, scattered where it won't cover outposts, roads or water (same spots every time for a map)
    rnd = random.Random(len(m.name) * 977 + len(nodes) * 31)

    def free_spots(count, near_node, gap):
        out = []
        for _ in range(count * 60):
            if len(out) >= count:
                break
            x, y = 10 + rnd.random() * (m.w - 20), 10 + rnd.random() * (m.h - 20)
            if any(math.hypot(n.x - x, n.y - y) < near_node for n in nodes):
                continue
            if any(seg_dist(x, y, nodes[e.a].x, nodes[e.a].y, nodes[e.b].x, nodes[e.b].y) < 34 for e in links):
                continue
            if any(seg_dist(x, y, *wl) < 40 for wl in water) or any(math.hypot(p[0] - x, p[1] - y) < gap for p in out):
                continue
            out.append((x, y))
        return out

    for part, count, near, gap, foot in (('decor', m.w * m.h // 52000, 95, 70, 22), ('rock', m.w * m.h // 90000, 90, 60, 11)):
        img = tile(part)
        for x, y in free_spots(count, near, gap):
            world.blit(img, (round(x * k - img.get_width() / 2), round((y + foot) * k - img.get_height())))
    return world
