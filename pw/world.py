"""The ground under a battle, built once per map from the tiles in assets/terrain/<theme>/:
ground.png and water.png repeat like wallpaper, road.png is a strip repeated along each straight road, road_diagonal.png
is one diagonal road (mirrored for the other direction), bridge.png sits on each bridge, and decor.png (trees etc.) and
rock.png are scattered where nothing else is. blocked.png (a forest, mountains...) fills the gap between neighbouring
outposts that aren't linked: it isn't part of the ground picture, the battlefield draws it over the outposts' pads
(see obstacles)."""
import math
import random
import pygame

from .data import STEP_X, STEP_Y
from .gfx import image, has_image, THEMES, C

KINDS = ['bunker', 'town', 'watchtower', 'town', 'bunker', 'watchtower', 'town']
# road_diagonal.png is made for this zoom (k = .4): one diagonal step between outposts is DIAGONAL_STEP pixels, and the
# picture leaves DIAGONAL_MARGIN pixels around it (the road starts and ends under the outposts' pads). It is pasted as it
# is at every zoom: the angle between diagonal neighbours never changes, only the distance, so the road always runs
# through both outposts; on bigger or smaller maps its ends just reach a few pixels less or further (under the pads).
DIAGONAL_STEP = (round(STEP_X * .4), round(STEP_Y * .4))
DIAGONAL_MARGIN = 10


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


def obstacles(m, k):
    """What blocks the way between two neighbouring outposts with no road or river between them (a forest,
    mountains...), so it's clear why nobody, not even a helicopter, can get from one to the other.
    A list of (picture, where in the world picture)."""
    if not has_image(f'terrain/{m.theme}/blocked.png'):
        return []
    wall = image(f'terrain/{m.theme}/blocked.png')
    at = {(n.col, n.row): i for i, n in enumerate(m.nodes)}
    linked = {frozenset((e.a, e.b)) for e in m.links}
    out = []
    for (c, r), i in at.items():
        for j in (at.get((c + 1, r)), at.get((c, r + 1))):              # the outpost to the right, and the one below
            if j is not None and frozenset((i, j)) not in linked:
                a, b = m.nodes[i], m.nodes[j]
                out.append((wall, wall.get_rect(midbottom=(round((a.x + b.x) / 2 * k), round((a.y + b.y) / 2 * k) + 6))))
    return out


def diagonal_road(m, k, a, b):
    """The theme's road_diagonal.png for the diagonal road from outpost a to b (mirrored if it goes down-left), and
    where it goes: centred between them, pixel for pixel (stretching pixel art makes it ragged). None if the theme has no
    such picture."""
    if not has_image(f'terrain/{m.theme}/road_diagonal.png'):
        return None
    img = image(f'terrain/{m.theme}/road_diagonal.png')
    if (b.x - a.x) * (b.y - a.y) < 0:
        img = pygame.transform.flip(img, True, False)
    return img, img.get_rect(center=(round((a.x + b.x) / 2 * k), round((a.y + b.y) / 2 * k)))


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
    wet = pygame.Surface((w, h), pygame.SRCALPHA)          # where scenery mustn't stand: water and shores
    roads = pygame.Surface((w, h), pygame.SRCALPHA)        # and what it mustn't cover at all
    if m.theme == 'beach':     # sea everywhere, an island around each outpost, sand along the roads between them
        world.blit(tiled((w, h), tile('water')), (0, 0))
        land = pygame.Surface((w, h), pygame.SRCALPHA)
        dry = pygame.Surface((w, h), pygame.SRCALPHA)      # the land minus its shoreline
        for n in nodes:
            pygame.draw.circle(land, white, (sc(n.x), sc(n.y)), sc(84))
            pygame.draw.circle(dry, white, (sc(n.x), sc(n.y)), sc(72))
        for e in links:
            if e.kind == 'road' and not e.bridge:
                a, b = (sc(nodes[e.a].x), sc(nodes[e.a].y)), (sc(nodes[e.b].x), sc(nodes[e.b].y))
                thick_line(land, white, a, b, sc(130))
                thick_line(dry, white, a, b, sc(110))
        world.blit(cut_out(tile('ground'), land), (0, 0))
        wet.fill(white)
        wet.blit(dry, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
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
            thick_line(wet, white, (sc(x1), sc(y1)), (sc(x2), sc(y2)), sc(64) + 6)
        world.blit(cut_out(tile('water'), river), (0, 0))

    # roads (the strip turned to follow each road), bridges, and dotted markers on river links
    road = tile('road')
    for e in links:
        a, b = nodes[e.a], nodes[e.b]
        length = math.hypot(b.x - a.x, b.y - a.y) * k
        angle = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        center = (sc((a.x + b.x) / 2), sc((a.y + b.y) / 2))
        if e.kind == 'road':
            thick_line(roads, white, (sc(a.x), sc(a.y)), (sc(b.x), sc(b.y)), road.get_height() + 4)
            drawn = diagonal_road(m, k, a, b) if a.x != b.x and a.y != b.y else None
            if drawn:                                   # a diagonal road: the theme's own picture of one
                world.blit(*drawn)
            else:
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

    # the forests / mountains between unlinked outposts are drawn by the battlefield, over the pads; just keep the
    # scenery below off them
    for wall, spot in obstacles(m, k):
        roads.blit(pygame.mask.from_surface(wall).to_surface(setcolor=white, unsetcolor=(0, 0, 0, 0)), spot)

    # scenery, scattered where it won't cover outposts or roads, standing on dry land (same spots every time for a
    # map). The lower half of a tree or rock (its trunk or base) must be on land, though leaves may lean over a shore.
    rnd = random.Random(len(m.name) * 977 + len(nodes) * 31)
    wet, roads = pygame.mask.from_surface(wet), pygame.mask.from_surface(roads)
    taken = []

    def free_spots(count, near_node, gap, img, foot):
        out, shape = [], pygame.mask.from_surface(img)
        half = img.get_height() // 2
        base = pygame.mask.from_surface(img.subsurface((0, half, img.get_width(), img.get_height() - half)))
        for _ in range(count * 60):
            if len(out) >= count:
                break
            x, y = 10 + rnd.random() * (m.w - 20), 10 + rnd.random() * (m.h - 20)
            if any(math.hypot(n.x - x, n.y - y) < near_node for n in nodes):
                continue
            if any(math.hypot(p[0] - x, p[1] - y) < gap for p in out + taken):
                continue
            at = (round(x * k - img.get_width() / 2), round((y + foot) * k - img.get_height()))
            if roads.overlap(shape, at) or wet.overlap(base, (at[0], at[1] + half)):
                continue
            out.append((x, y, at))
        return out

    snug = 26 if m.theme == 'beach' else 0     # beach land is only a ring around each outpost: let scenery come closer
    for part, count, near, gap, foot in (('decor', m.w * m.h // 52000, 95, 70, 22), ('rock', m.w * m.h // 90000, 90, 60, 11)):
        img = tile(part)
        spots = free_spots(count, near - snug, gap, img, foot)
        taken.extend((x, y) for x, y, _ in spots)
        for x, y, at in spots:
            world.blit(img, at)
    return world
