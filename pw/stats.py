"""Battle stats, shown from the victory menu: a report card for both sides, then charts of how the battle went turn
by turn. The numbers come from the rules (Game.totals and Game.history), so they work for every kind of game.
After a battle against Hard there is one more page: what Hard has learned about you (learn.py)."""
import pygame

from . import learn
from .data import UNITS
from .menu import Pages
from .gfx import C, SIDES, SW, rect, text, text_width, wrap, blit, unit_image

# The report card: label, how to get the number from one side's totals (t) and history (h), and whether more is better.
REPORT = [
    ('DAMAGE DEALT', lambda t, h: t['damage'], True),
    ('DAMAGE TO ENEMY HQ', lambda t, h: t['hq_damage'], True),
    ('UNITS DESTROYED', lambda t, h: t['kills'], True),
    ('UNITS LOST', lambda t, h: t['lost'], False),
    ('SOLDIERS RECRUITED', lambda t, h: t['recruited'], True),
    ('VEHICLES BUILT', lambda t, h: t['built'], True),
    ('ATTACKS MADE', lambda t, h: t['attacks'], True),
    ('BIGGEST HIT', lambda t, h: t['biggest'], True),
    ('OUTPOSTS CAPTURED', lambda t, h: t['captured'], True),
    ('MOST OUTPOSTS HELD', lambda t, h: max(s['outposts'] for s in h), True),
    ('LARGEST ARMY', lambda t, h: max(s['units'] for s in h), True),
    ('STEPS MARCHED', lambda t, h: t['marched'], True),
]

# The charts: title, which snapshot number to plot, and a line explaining it.
CHARTS = [
    ('ARMY SIZE', 'units', 'Units on the board after each turn (no HQ).'),
    ('ARMY STRENGTH', 'strength', 'Hit points of all units: vehicles count a lot.'),
    ('TERRITORY', 'outposts', 'Outposts held after each turn.'),
    ('DAMAGE DEALT', 'damage', 'All damage dealt so far, return fire included.'),
    ('HQ HEALTH', 'hq', 'How much each HQ had left.'),
]

NICE = [1, 2, 5, 10, 15, 20, 25, 50, 75, 100, 150, 200, 250, 500, 1000, 2000, 5000]
CX, CY, CW, CH = 14, 30, 292, 150          # the chart panel


def ramp(t, length):
    return max(0, min(1, t / length))


class Stats(Pages):
    def __init__(self, app, game, on_exit):
        self.app, self.g, self.on_exit = app, game, on_exit
        self.page, self.opened = 0, None
        self.memory = getattr(game, 'learning', {}).get('memory')      # set after a battle against Hard
        self.pages = ['report'] + CHARTS + (['memory'] if self.memory else [])

    def page_changed(self):
        self.opened = None              # replay the page's animation

    def update(self, now, dt):
        if self.opened is None:
            self.opened = now

    def draw(self, surf, now):
        page = self.pages[self.page]
        self.frame(surf, {'report': 'BATTLE REPORT', 'memory': "HARD'S MEMORY"}.get(page) or page[0])
        t = now - (self.opened if self.opened is not None else now)
        if page == 'report':
            self.draw_report(surf, t)
        elif page == 'memory':
            self.draw_memory(surf)
        else:
            self.draw_chart(surf, page, t)

    # ------------------------------------------------------------------ report card
    def headline(self):
        g, w = self.g, self.g.winner
        turns = g.history[-1][0]
        if w is None:
            return 'NO WINNER', C['ink']
        if g.resigned:
            return f"{SIDES[1 - w]['name']} RESIGNED ON TURN {turns}", SIDES[w]['dark']
        return f"{SIDES[w]['name']} WINS IN {turns} TURNS", SIDES[w]['dark']

    def draw_report(self, surf, t):
        g = self.g
        line, color = self.headline()
        text(surf, line, SW / 2, 30, color, 1, 'c')
        cols = (222, 296)                               # right edges of the GREEN and TAN columns
        for p, x in enumerate(cols):
            text(surf, SIDES[p]['name'], x, 41, SIDES[p]['dark'], 1, 'r')
        rect(surf, 14, 49, SW - 28, 1, C['ink'])
        hist = [[s[p] for _, s in g.history] for p in (0, 1)]
        y = 52
        for k, (label, get, more_is_better) in enumerate(REPORT):
            if k % 2 == 0:
                rect(surf, 14, y - 2, SW - 28, 11, C['paper_dark'])
            text(surf, label, 18, y, C['ink'])
            vals = [get(g.totals[p], hist[p]) for p in (0, 1)]
            shown = [round(v * ramp(t - k * .05, .5)) for v in vals]      # numbers count up when the page opens
            best = None if vals[0] == vals[1] else (vals.index(max(vals)) if more_is_better else vals.index(min(vals)))
            for p, x in enumerate(cols):
                if p == best and t > k * .05 + .5:              # the better number gets a yellow badge
                    w = text_width(vals[p])
                    rect(surf, x - w - 3, y - 1, w + 5, 9, C['highlight'])
                text(surf, shown[p], x, y, C['ink'], 1, 'r')
            y += 11
        # the unit that did the most damage for each side
        text(surf, 'TOP UNIT', 18, y, C['ink'])
        for p, x in enumerate(cols):
            by = g.totals[p]['by_type']
            if not by or max(by.values()) == 0:
                text(surf, '-', x, y, C['ink'], 1, 'r')
                continue
            top = max(by, key=by.get)
            n = str(by[top])
            text(surf, n, x, y, C['ink'], 1, 'r')
            img = unit_image('icons', top, p)
            blit(surf, img, x - text_width(n) - 4 - img.get_width(), y + 7 - img.get_height())

    # ------------------------------------------------------------------ what Hard has learned (learn.py)
    def draw_memory(self, surf):
        mem, style = self.memory, self.g.learning['style']
        you = SIDES[self.g.learning['you']]
        text(surf, f"BATTLES VS HARD: {mem['games']}   YOU WON {mem['you_won']}, HARD WON {mem['games'] - mem['you_won']}",
             SW / 2, 30, C['ink'], 1, 'c')
        text(surf, 'HARD STYLE', 18, 44, C['dim'])
        text(surf, 'BEAT YOU', 222, 44, C['dim'], 1, 'r')
        text(surf, 'LOST', 296, 44, C['dim'], 1, 'r')
        rect(surf, 14, 52, SW - 28, 1, C['ink'])
        y = 56
        for name, rec in mem['styles'].items():
            if name == style:                                    # the style Hard played this battle
                rect(surf, 14, y - 2, SW - 28, 11, C['highlight'])
            text(surf, name + ('  (THIS BATTLE)' if name == style else ''), 18, y, C['ink'])
            text(surf, rec['won'], 222, y, C['ink'], 1, 'r')
            text(surf, rec['lost'], 296, y, C['ink'], 1, 'r')
            y += 11
        y += 6
        fav = learn.favourite(mem)
        if fav:
            text(surf, 'YOUR FAVOURITE VEHICLE:', 18, y, C['ink'])
            img = unit_image('icons', fav, self.g.learning['you'])
            blit(surf, img, 162, y + 7 - img.get_height())
            text(surf, UNITS[fav]['name'], 166 + img.get_width(), y, you['dark'])
            y += 11
        for line in wrap('Hard plays the styles that beat you more often, and expects the vehicles you like to build.', 48):
            text(surf, line, 18, y, C['dim'])
            y += 9

    # ------------------------------------------------------------------ charts
    def draw_chart(self, surf, page, t):
        _, key, caption = page          # (the title is drawn by the page frame)
        g = self.g
        turns = [turn for turn, _ in g.history]
        series = [[s[p][key] for _, s in g.history] for p in (0, 1)]
        rect(surf, CX - 1, CY - 1, CW + 2, CH + 2, C['ink'])
        rect(surf, CX, CY, CW, CH, C['background'])
        x0, x1, y0, y1 = CX + 30, CX + CW - 10, CY + 10, CY + CH - 16
        top = max([1] + series[0] + series[1])
        step = next((n for n in NICE if n * 4 >= top), NICE[-1])
        for k in range(5):                                       # grid lines and their numbers
            yy = round(y1 - (y1 - y0) * k / 4)
            rect(surf, x0, yy, x1 - x0 + 1, 1, C['olive_dark'] if k else C['dim'])
            text(surf, step * k, x0 - 4, yy - 3, C['grey'], 1, 'r')
        n = len(turns)
        xs = [x0 + (x1 - x0) * i / max(1, n - 1) for i in range(n)]
        for i in sorted({0, n // 2, n - 1}):                     # turn numbers along the bottom
            text(surf, turns[i], xs[i], y1 + 5, C['grey'], 1, 'c')
        shown = max(1, round(n * ramp(t, 1.2)))                  # the lines draw themselves in
        w = g.winner if g.winner is not None else 0
        for p in (1 - w, w):                                     # the winner's line on top
            pts = [(round(xs[i]), round(y1 - (y1 - y0) * series[p][i] / (step * 4))) for i in range(shown)]
            color = SIDES[p]['light']
            if len(pts) > 1:
                pygame.draw.lines(surf, color, False, pts, 2)
            rect(surf, pts[-1][0] - 1, pts[-1][1] - 1, 3, 3, color)
        # legend: each side's last value and its best
        y = CY + CH + 5
        for p, x in ((0, 18), (1, SW / 2 + 4)):
            rect(surf, x, y + 1, 6, 5, SIDES[p]['main'])
            rect(surf, x, y + 1, 6, 1, SIDES[p]['light'])
            text(surf, f"{SIDES[p]['name']} {series[p][-1]}  (BEST {max(series[p])})", x + 9, y, C['ink'])
        yy = y + 11
        for line in wrap(caption, 48):
            text(surf, line, 18, yy, C['dim'])
            yy += 9
