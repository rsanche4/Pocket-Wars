"""Drawing a battle: the ground, outposts, buildings, units, fog and the cursor. Used by the game screen (and later
the title screen and How to Play, which draw battles of their own)."""
import math
import pygame

from .data import ORDER, UNITS
from .gfx import C, SIDES, SW, SH, rect, ellipse, ellipse_ring, blit, digits, hp_bar, text, unit_image, building_image, image, SIDE_FILE
from .world import build_world, outpost_kinds


_blackout = []


def blackout_layer():
    """The dark, dotted cover used in blackout fog (made once)."""
    if not _blackout:
        dark = pygame.Surface((SW, SH), pygame.SRCALPHA)
        dark.fill(C['blackout'])
        for y in range(0, SH, 2):
            for x in range((y // 2) % 2 * 2, SW, 4):
                dark.set_at((x, y), C['blackout_dots'])
        _blackout.append(dark)
    return _blackout[0]


class March:
    """A group walking along a path, outpost to outpost."""
    def __init__(self, path, units, seconds_per_step, now):
        self.path, self.units, self.start = path, units, now
        self.length = seconds_per_step * (len(path) - 1)

    def done(self, now):
        return now - self.start >= self.length

    def position(self, field, now):
        f = max(0, min(1, (now - self.start) / (self.length or 1))) * (len(self.path) - 1)
        i = min(int(f), len(self.path) - 2)
        a, b = field.g.map.nodes[self.path[i]], field.g.map.nodes[self.path[i + 1]]
        t = f - i
        return (a.x + (b.x - a.x) * t) * field.k, (a.y + (b.y - a.y) * t) * field.k


class Drop:
    """A reinforcement parachuting onto outpost i. Its unit is hidden from the outpost until it lands."""
    PUFF = .3

    def __init__(self, i, unit, seconds, now):
        self.i, self.unit, self.start, self.length = i, unit, now, seconds
        self.heard = False          # the landing sound has played

    def landed(self, now):
        return now - self.start >= self.length

    def gone(self, now):            # after landing, a short puff of dust
        return now - self.start >= self.length + self.PUFF


class Field:
    def __init__(self, game, k):
        self.g, self.k = game, k
        self.world = build_world(game.map, k)
        self.kinds = outpost_kinds(game.map)
        self.march = None              # a March being shown (its units are hidden from their outpost meanwhile)
        self.drops = []                # Drops (soldiers parachuting in) being shown

    def screen_pos(self, i, cam):
        n = self.g.map.nodes[i]
        return round(n.x * self.k - cam[0]), round(n.y * self.k - cam[1])

    def draw(self, surf, cam, now, vis=None, blackout=False, highlight=(), cursor=None, ring=None, cursor_style='normal'):
        """vis = outposts the viewer can see (None = everything). blackout hides the unseen ground too.
        ring = colour of the highlight rings (the current phase's colour). cursor_style: 'normal', 'target' (over an
        enemy you can attack) or 'no_target' (choosing a target, but not over one)."""
        g, nodes = self.g, self.g.map.nodes
        blink = int(now / .26) % 2
        surf.blit(self.world, (-cam[0], -cam[1]))
        if blackout and vis is not None:
            self.draw_blackout(surf, cam, vis)
        for i, n in enumerate(nodes):
            seen = vis is None or i in vis
            if blackout and not seen:
                continue
            x, y = self.screen_pos(i, cam)
            if not (-30 <= x <= SW + 30 and -30 <= y <= SH + 30):
                continue
            side = g.owner(i) if seen else (n.hq if n.hq >= 0 else None)
            kind = self.kinds[i]
            ellipse(surf, x, y + 3, 15, 5, pygame.Color(0, 0, 0, 90))
            ellipse(surf, x, y + 1, 14, 5, C['neutral_pad_dark'] if side is None else SIDES[side]['pad'])
            ellipse(surf, x, y, 14, 5, C['neutral_pad'] if side is None else SIDES[side]['light'])
            if i in highlight:
                ellipse_ring(surf, x, y, 17, 7, ring or C['highlight'], 0 if blink else 2)
                ellipse_ring(surf, x, y, 18, 8, ring or C['highlight'], 2 if blink else 0)
            b = building_image(kind, side)
            blit(surf, b, x - b.get_width() // 2, y - b.get_height() + 2, alpha=255 if seen or kind == 'hq' else 115)
            if side is not None and kind != 'hq':          # a little flag
                rect(surf, x + 11, y - 17, 1, 17, pygame.Color('#2b2620'))
                rect(surf, x + 12, y - 17, 6, 4, SIDES[side]['main'])
                rect(surf, x + 12, y - 13, 6, 1, SIDES[side]['dark'])
            if n.barracks:
                rect(surf, x - 18, y - 22, 11, 7, C['ink'])
                digits(surf, '+1', x - 17, y - 21, C['highlight'])
            if kind == 'hq' and seen:
                q = next((u for u in g.units[i] if u.type == 'hq'), None)
                if q:
                    rect(surf, x - 11, y - 31, 22, 4, C['ink'])
                    hp_bar(surf, x - 10, y - 30, 20, q.hp / UNITS['hq']['hp'], 2)
            if seen:
                self.draw_units(surf, i, x, y, side, now)
            elif kind != 'hq':                              # fog: a cloud with a question mark
                ellipse(surf, x, y - 6, 9, 6, C['fog_cloud'])
                ellipse(surf, x - 6, y - 3, 6, 4, pygame.Color('#dfe2e6'))
                ellipse(surf, x + 6, y - 3, 6, 4, pygame.Color('#f4f5f7'))
                text(surf, '?', x - 2, y - 9, pygame.Color('#7d848c'))
            if i == cursor and cursor_style == 'normal':
                self.draw_cursor(surf, x, y, blink)
        if self.march:
            self.draw_march(surf, cam, now)
        self.drops = [d for d in self.drops if not d.gone(now)]
        for d in self.drops:
            if vis is None or d.i in vis:
                self.draw_drop(surf, cam, now, d)
        if cursor is not None and cursor_style != 'normal':
            x, y = self.screen_pos(cursor, cam)
            self.draw_target(surf, x, y, now, cursor_style == 'target')

    def draw_blackout(self, surf, cam, vis):
        dark = blackout_layer().copy()
        clear = (0, 0, 0, 0)
        r = round(30 * self.k / .35)
        for i in vis:
            x, y = self.screen_pos(i, cam)
            pygame.draw.ellipse(dark, clear, (x - r * 1.15, y - r, r * 2.3, r * 2))
        for e in self.g.map.links:
            if e.a in vis and e.b in vis:
                pygame.draw.line(dark, clear, self.screen_pos(e.a, cam), self.screen_pos(e.b, cam), round(46 * self.k / .35))
        # the middle of a grid square: clear it when you can see at least 3 of its corner outposts (the clearings
        # above don't reach that far, which left black patches surrounded by outposts you can see)
        at = {(n.col, n.row): i for i, n in enumerate(self.g.map.nodes)}
        for c, r in {(c - dc, r - dr) for c, r in at for dc in (0, 1) for dr in (0, 1)}:     # every square touching one
            corners = [at.get(p) for p in ((c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1))]
            seen = [i for i in corners if i is not None and i in vis]
            if len(seen) >= 3:
                pygame.draw.polygon(dark, clear, [self.screen_pos(i, cam) for i in seen])
        surf.blit(dark, (0, 0))

    def draw_units(self, surf, i, x, y, side, now):
        g = self.g
        hidden = (self.march.units if self.march else []) + [d.unit for d in self.drops if not d.landed(now)]
        units = [u for u in g.units[i] if u.type != 'hq' and u not in hidden]
        groups = [[u for u in units if u.type == t] for t in ORDER]
        ground = [grp for grp in groups if grp and grp[0].type != 'helicopter']
        air = next((grp for grp in groups if grp and grp[0].type == 'helicopter'), None)

        def one(grp, gx, gy):
            t, s = grp[0].type, grp[0].side
            img = unit_image('map', t, s)
            w, h = img.get_size()
            used = g.phase == 'attack' and g.cur == s and all(u.id in g.used for u in grp)
            blit(surf, img, gx, gy, alpha=115 if used else 255)
            hp_bar(surf, gx + 1, gy + h + 1, w - 2, sum(u.hp for u in grp) / (len(grp) * UNITS[t]['hp']), 1)
            if len(grp) > 1:
                n = str(len(grp))
                rect(surf, gx + w - 3, gy - 3, len(n) * 4 + 2, 7, C['ink'])
                digits(surf, n, gx + w - 2, gy - 2, C['white'])

        total = sum(unit_image('map', grp[0].type, grp[0].side).get_width() for grp in ground) + len(ground) - 1
        gx = round(x - total / 2)
        for grp in ground:
            w, h = unit_image('map', grp[0].type, grp[0].side).get_size()
            ellipse(surf, gx + w / 2, y + 11, math.ceil(w / 2) + 1, 2, pygame.Color(0, 0, 0, 90))
            one(grp, gx, y + 12 - h)
            gx += w + 1
        if air:
            w, h = unit_image('map', 'helicopter', air[0].side).get_size()
            bob = round(math.sin(now * 5 + i))
            hx = round(x + 2 if ground else x - w / 2)
            ellipse(surf, hx + w / 2, y + 2, 7, 2, pygame.Color(0, 0, 0, 77))
            one(air, hx, y - 10 - h + bob)

    def draw_cursor(self, surf, x, y, blink):
        p = 1 if blink else 0
        x0, x1, y0, y1 = x - 17 - p, x + 16 + p, y - 25 - p, y + 9 + p
        for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            rect(surf, min(cx, cx + dx * 4), cy, 5, 1, C['white'])
            rect(surf, cx, min(cy, cy + dy * 4), 1, 5, C['white'])
            rect(surf, min(cx, cx + dx * 4), cy + dy, 5, 1, C['ink'])

    def draw_march(self, surf, cam, now):
        m = self.march
        x, y = m.position(self, now)
        x, y = x - cam[0], y - cam[1]
        t = next(t for t in ('helicopter', 'tank', 'halftrack', 'soldier') if any(u.type == t for u in m.units))
        side = m.units[0].side
        img = unit_image('map', t, side)
        w, h = img.get_size()
        ellipse(surf, x, y + 4, 9, 2, pygame.Color(0, 0, 0, 90))
        blit(surf, img, x - w / 2, y - h + 4)
        if len(m.units) > 1:
            rect(surf, x + w / 2 - 2, y - h, 9, 7, C['ink'])
            digits(surf, len(m.units), round(x + w / 2), round(y - h + 1), C['white'])

    # ---------- phase feedback: target cursor, march arrow, reinforcements ----------
    # All of these are pictures in assets/ui/ you can replace (tools/make_ui.py made the originals; see README).
    def draw_target(self, surf, x, y, now, ok):
        """The attack cursor centred on the enemy outpost: ui/target.png (it pulses through its frames), or
        ui/target_off.png when it's not over something you can attack."""
        img = image('ui/target.png' if ok else 'ui/target_off.png')
        f = frame(img, int(now / .26))
        blit(surf, f, x - f.get_width() / 2, y - 8 - f.get_height() / 2)

    def draw_route(self, surf, cam, path):
        """An Advance Wars style arrow along a march path. ui/arrow_body.png is a slice across the arrow (its left
        column, top to bottom), swept along the road. The head is ui/arrow_head.png (pointing right, turned a quarter
        at a time) on straight roads and ui/arrow_head_diagonal.png (pointing down-right, flipped) on diagonal ones."""
        pts = [self.screen_pos(i, cam) for i in path]
        if len(pts) < 2:
            return
        body, dot = image('ui/arrow_body.png'), image('ui/arrow_start.png')
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        d = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / d, (by - ay) / d
        tip = (bx - ux * 3, by - uy * 3)                 # the tip stops just short of the outpost's middle
        sx, sy = (bx > ax) - (bx < ax), (by > ay) - (by < ay)
        if sx and sy:                                    # diagonal: flip the down-right head; its tip is that corner
            head = pygame.transform.flip(image('ui/arrow_head_diagonal.png'), sx < 0, sy < 0)
            w, h = head.get_size()
            x0, y0 = tip[0] - (w - 1 if sx > 0 else 0), tip[1] - (h - 1 if sy > 0 else 0)
        else:                                            # straight: quarter turns of the right-pointing head
            right = image('ui/arrow_head.png')
            head = pygame.transform.rotate(right, 90 * round(math.degrees(math.atan2(-uy, ux)) / 90))
            w, h = head.get_size()
            cx, cy = tip[0] - ux * right.get_width() / 2, tip[1] - uy * right.get_width() / 2
            x0, y0 = cx - w / 2, cy - h / 2
        line = pts[:-1] + [(x0 + w / 2, y0 + h / 2)]      # the body runs into the middle of the head
        blit(surf, dot, pts[0][0] - dot.get_width() / 2, pts[0][1] - dot.get_height() / 2)
        slice_ = [body.get_at((0, r)) for r in range(body.get_height())]
        for k in range((len(slice_) + 1) // 2):          # outside layer first, then each layer inside it
            width, c = len(slice_) - 2 * k, slice_[k]
            if c.a:
                strip(surf, c, line, width)
        blit(surf, head, x0, y0)

    def draw_ghost(self, surf, cam, i, side, now):
        """A see-through soldier on a parachute hovering over outpost i: where the next reinforcement will land."""
        x, y = self.screen_pos(i, cam)
        kind = self.kinds[i]
        above = building_image(kind, self.g.owner(i)).get_height() + (8 if kind == 'hq' else 1)   # clear of the roof (and HQ bar)
        self.draw_chute(surf, x, y + 2 - above + round(math.sin(now * 4) * 2), side, 1, alpha=160)

    def draw_drop(self, surf, cam, now, d):
        """A soldier parachuting down from the top of the screen onto its outpost, then ui/dust.png plays."""
        x, y = self.screen_pos(d.i, cam)
        t = (now - d.start) / d.length
        land = y + 11                                      # where the soldiers' feet stand
        if t < 1:
            fall = 1 - (1 - t) ** 1.7                      # fast at first, gentle at the end
            yy = -4 + (land + 4) * fall
            sway = round(math.sin(t * 8 + d.i) * 4 * (1 - t))
            self.draw_chute(surf, x + sway, yy, d.unit.side, 1 if t < .8 else 1 - (t - .8) / .2 * .8)
        else:
            img = image('ui/dust.png')
            k = (now - d.start - d.length) / Drop.PUFF
            f = frame(img, min(frames(img) - 1, int(k * frames(img))))
            blit(surf, f, x - f.get_width() / 2, land + 1 - f.get_height())

    def draw_chute(self, surf, x, y, side, open_=1.0, alpha=255):
        """A soldier hanging under ui/parachute_<side>.png; (x, y) = the soldier's feet. open_ < 1 folds the canopy."""
        soldier = unit_image('map', 'soldier', side)
        chute = image(f'ui/parachute_{SIDE_FILE[side]}.png')
        if open_ < 1:
            chute = pygame.transform.scale(chute, (max(1, round(chute.get_width() * open_)), max(1, round(chute.get_height() * open_))))
        head = y - soldier.get_height()
        blit(surf, chute, x - chute.get_width() / 2, head + 4 - chute.get_height(), alpha)    # cords meet at the head
        blit(surf, soldier, x - soldier.get_width() // 2, head, alpha)


def strip(surf, color, line, width):
    """A band exactly `width` pixels thick along a line of points, rounded at the bends. (pygame's own thick lines
    get thinner and ragged at an angle, which made diagonal arrows look broken.)"""
    half = (width - 1) / 2
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        d = math.hypot(x2 - x1, y2 - y1)
        if d:
            nx, ny = -(y2 - y1) / d * half, (x2 - x1) / d * half
            pygame.draw.polygon(surf, color, [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])
    for x, y in line:
        pygame.draw.circle(surf, color, (round(x), round(y)), width / 2)


def frames(img):
    """How many square frames a strip picture has (a single picture is 1)."""
    return max(1, img.get_width() // img.get_height())


def frame(img, k):
    """Frame k of a strip of square frames, looping."""
    n = frames(img)
    w = img.get_width() // n
    return img.subsurface((k % n * w, 0, w, img.get_height()))
