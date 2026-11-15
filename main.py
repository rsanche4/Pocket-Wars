"""Pocket Wars.  Run:  py main.py
Keys: ARROWS move, ENTER (or Z, SPACE) select, ESC (or X) back, F11 full screen.

The game is a set of screens (title, map choice, setup, options, how to play, battle). Each screen has
key(k), update(now, dt) and draw(surface, now); the App below switches between them.
"""
import pygame

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

from pw import settings                     # noqa: E402  (pygame must be started first)
from pw.settings import S                   # noqa: E402
from pw.gfx import SW, SH                   # noqa: E402
from pw.data import load_maps               # noqa: E402

WINDOW_SIZE = (640, 480)        # the window's size when the game opens (drag to resize, maximise, or F11 for full screen)

KEYS = {pygame.K_UP: 'u', pygame.K_DOWN: 'd', pygame.K_LEFT: 'l', pygame.K_RIGHT: 'r',
        pygame.K_RETURN: 'e', pygame.K_KP_ENTER: 'e', pygame.K_SPACE: 'e', pygame.K_z: 'e',
        pygame.K_ESCAPE: 'b', pygame.K_BACKSPACE: 'b', pygame.K_x: 'b'}


class App:
    def __init__(self):
        from pw.title import Backdrop
        settings.load()
        self.window = pygame.Window('Pocket Wars', WINDOW_SIZE, resizable=True, position=pygame.WINDOWPOS_CENTERED)
        self.window.get_surface()                     # (images can only be loaded once the window has a surface)
        self.screen = pygame.Surface((SW, SH))        # the game draws here at 320x240; show() scales it to the window
        self.apply_fullscreen()
        self.now = 0
        self.maps = load_maps()
        self.backdrop = Backdrop(self)
        self.scene = None
        self.running = True
        self.title(intro=True)

    # ---------- moving between screens ----------
    def title(self, intro=False):
        from pw.title import Title
        self.scene = Title(self, intro)

    def choose_map(self, mode):
        from pw.menus import ChooseMap
        S['mode'] = mode
        self.maps = load_maps()          # pick up maps added to maps/ while the game is open
        self.scene = ChooseMap(self)

    def chosen_map(self):
        return next((m for m in self.maps if m.path == S['map']), self.maps[0])

    def setup(self):
        from pw.menus import Setup
        self.scene = Setup(self)

    def options(self):
        from pw.menus import Options
        self.scene = Options(self)

    def how_to_play(self):
        from pw.howto import HowTo
        self.scene = HowTo(self)

    def map_editor(self):
        from pw.editor import MapList
        self.maps = load_maps()
        self.scene = MapList(self)

    def edit_map(self, m):
        from pw.editor import Editor
        self.scene = Editor(self, m)

    def editor_help(self, editor):
        from pw.howto import HowTo
        from pw.data import load_json
        self.scene = HowTo(self, load_json('data', 'editor_help.json')['pages'], on_exit=lambda: setattr(self, 'scene', editor))

    def start_battle(self):
        from pw.play import Play
        self.scene = Play(self, self.chosen_map(), dict(S))

    def play_again(self):
        self.start_battle()

    def main_menu(self):
        self.backdrop.new(self.now)      # a different battle behind the title each time you come back
        self.title()

    def quit(self):
        self.running = False

    def apply_fullscreen(self):
        if S['fullscreen']:
            self.window.set_fullscreen(True)          # True = at the desktop's own resolution
        else:
            self.window.set_windowed()

    def show(self):
        """Scale the 320x240 picture up to fill the window, keeping its shape (black bars fill any leftover space)."""
        out = self.window.get_surface()
        ww, wh = out.get_size()
        scale = min(ww / SW, wh / SH)
        w, h = round(SW * scale), round(SH * scale)
        out.fill((0, 0, 0))
        out.blit(pygame.transform.scale(self.screen, (w, h)), ((ww - w) // 2, (wh - h) // 2))
        self.window.flip()

    # ---------- the loop ----------
    def loop(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = clock.tick(60) / 1000
            self.now = pygame.time.get_ticks() / 1000
            for e in pygame.event.get():
                if e.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                    self.running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        S['fullscreen'] = not S['fullscreen']
                        self.apply_fullscreen()
                        settings.save()
                    elif e.key in KEYS:
                        self.scene.key(KEYS[e.key])
            self.scene.update(self.now, dt)
            self.scene.draw(self.screen, self.now)
            self.show()


if __name__ == '__main__':
    App().loop()
    pygame.quit()
