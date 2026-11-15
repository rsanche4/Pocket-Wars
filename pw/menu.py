"""The pop-up menu box used during battles (commands, buy, attack...), and Pages, the base of page-by-page screens.

Each item is a dict:  l = label,  f = what ENTER does,  val = text on the right (a function),  adj = what LEFT/RIGHT
do (a function taking -1/+1),  dis = greyed out,  info = just text (can't be picked),  icon = unit type,  col = colour.
"""
from . import sound
from .gfx import C, SW, SH, rect, box, text, blit, unit_image


class Pages:
    """A screen of pages (How to Play, Battle Stats): LEFT/RIGHT flip, ENTER next (or done), ESC leaves.
    Subclasses set self.pages, self.page and self.on_exit, and draw a page's content after frame()."""
    def key(self, k):
        before = self.page
        if k in 'lu':
            self.page = max(0, self.page - 1)
        elif k in 'rd' or (k == 'e' and self.page < len(self.pages) - 1):
            self.page = min(len(self.pages) - 1, self.page + 1)
        elif k in 'eb':
            sound.play('select' if k == 'e' else 'back')
            self.on_exit()
            return
        if self.page != before:
            self.page_changed()
        sound.play('page' if self.page != before else 'error')

    def page_changed(self):
        pass

    def update(self, now, dt):
        pass

    def frame(self, surf, title):
        """The paper box, title bar and footer around a page."""
        surf.fill(C['olive_dark'])
        box(surf, 8, 8, SW - 16, SH - 16)
        rect(surf, 10, 10, SW - 20, 16, C['olive'])
        text(surf, title, SW / 2, 14, C['highlight'], 1, 'c', C['ink'])
        rect(surf, 10, SH - 26, SW - 20, 1, C['paper_dark'])
        text(surf, 'ESC: BACK', 16, SH - 21, C['dim'])
        text(surf, f'◀ {self.page + 1}/{len(self.pages)} ▶', SW / 2, SH - 21, C['dim'], 1, 'c')
        text(surf, 'ENTER: NEXT' if self.page < len(self.pages) - 1 else 'ENTER: DONE', SW - 16, SH - 21, C['olive'], 1, 'r')


class Menu:
    def __init__(self, title, items, sub=None, wide=False, pair=None, win=None):
        self.title, self.items, self.sub, self.wide, self.pair, self.win = title, items, sub, wide, pair, win
        pickable = [i for i, it in enumerate(items) if not it.get('dis') and not it.get('info')]
        self.sel = pickable[0] if pickable else 0

    def move(self, d):
        for _ in range(len(self.items)):
            self.sel = (self.sel + d) % len(self.items)
            if not self.items[self.sel].get('info'):
                break

    def size(self):
        rows = 12 if self.wide else 9
        return (236 if self.wide else 196), 26 + (9 if self.sub else 0) + min(len(self.items), rows) * 12 + 4

    def draw(self, surf, top, height, side, at=None):
        """Drawn centred in the area from `top`, `height` tall, or with its top-left corner at `at`."""
        w, row = (236 if self.wide else 196), 12
        items, rows = self.items, (12 if self.wide else 9)
        first = 0
        if len(items) > rows:
            first = max(0, min(len(items) - rows, self.sel - rows // 2))
        shown = items[first:first + rows]
        h = self.size()[1]
        x, y = at or (round((SW - w) / 2), round(top + (height - h) / 2))
        box(surf, x, y, w, h)
        rect(surf, x + 2, y + 2, w - 4, 14, side['main'] if self.win is not None else C['olive'])
        text(surf, self.title, x + w / 2, y + 5, C['white'], 1, 'c', C['ink'])
        yy = y + 20
        if self.sub:
            text(surf, self.sub, x + w / 2, yy, C['dim'], 1, 'c')
            yy += 9
        for k, it in enumerate(shown):
            on = first + k == self.sel and not it.get('info')
            color = C['grey'] if it.get('dis') else it.get('col') or C['ink']
            if on:
                rect(surf, x + 3, yy - 2, w - 6, row - 1, C['highlight'])
                text(surf, '▶', x + 6, yy, C['ink'])
            lx = x + 14
            if it.get('icon'):
                img = unit_image('icons', it['icon'], it.get('side', 0))
                blit(surf, img, lx, yy + 7 - img.get_height())
                lx += img.get_width() + 3
            if it.get('l'):
                text(surf, it['l'], lx, yy, color)
            val = it['val']() if it.get('val') else it.get('r')
            if val:
                text(surf, val, x + w - 6, yy, C['grey'] if it.get('dis') else C['ink'], 1, 'r')
            yy += row
        if first > 0:
            text(surf, '▲', x + w - 10, y + 20, C['dim'])
        if first + rows < len(items):
            text(surf, '▼', x + w - 10, y + h - 10, C['dim'])
