"""Sound effects and music, all played from files: assets/sfx/<name>.wav (or .ogg / .mp3) and assets/music/<name>.mp3.
A missing file is simply silent, so you can add or remove sounds freely."""
import os
import pygame

from .data import ROOT

volume = {'sfx': .7, 'music': .5}       # set from the options (see settings.py)
enabled = {'sfx': True, 'music': True}
_cache = {}
_music = {'name': None, 'loop': True, 'playing': None}


def _find(folder, name):
    for ext in ('.wav', '.ogg', '.mp3'):
        path = os.path.join(ROOT, 'assets', folder, name + ext)
        if os.path.exists(path):
            return path
    return None


def play(name):
    if not enabled['sfx'] or not pygame.mixer.get_init():
        return
    if name not in _cache:
        path = _find('sfx', name)
        _cache[name] = pygame.mixer.Sound(path) if path else None
    s = _cache[name]
    if s:
        s.set_volume(volume['sfx'])
        s.play()


def music(name, loop=True):
    """Ask for a track (title, battle, victory). If it's already playing it just keeps going."""
    _music['name'], _music['loop'] = name, loop
    _start()


def _start():
    if not pygame.mixer.get_init():
        return
    want = _music['name'] if enabled['music'] else None
    if want == _music['playing']:
        return
    pygame.mixer.music.stop()
    _music['playing'] = None
    path = want and _find('music', want)
    if path:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume['music'])
        pygame.mixer.music.play(-1 if _music['loop'] else 0)
        _music['playing'] = want


def set_music_volume():
    if pygame.mixer.get_init():
        pygame.mixer.music.set_volume(volume['music'])
    _start()
