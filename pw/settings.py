"""Your settings, kept in settings.json next to main.py (delete that file to go back to the defaults)."""
import json
import os

from .data import ROOT
from . import sound

PATH = os.path.join(ROOT, 'settings.json')
DEFAULTS = {
    'mode': 'cpu',          # cpu = you vs the CPU, hot = two players on one keyboard
    'cpu': 'hard',          # normal / hard
    'fog': 'off',           # off / fog / blackout
    'timer': 0,             # seconds per turn, 0 = no timer
    'anim': 'full',         # battle scenes: full / fast / off
    'record': False,        # save battles to recordings/ (see recordings.py)
    'sound': True, 'sfx_volume': 7,
    'music': True, 'music_volume': 5,
    'fullscreen': False,
    'map': '',              # the last map played
}
S = dict(DEFAULTS)


def load():
    try:
        with open(PATH, encoding='utf-8') as f:
            S.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    apply_sound()


def save():
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(S, f, indent=1)
    apply_sound()


def apply_sound():
    sound.enabled['sfx'], sound.volume['sfx'] = S['sound'], S['sfx_volume'] / 10
    sound.enabled['music'], sound.volume['music'] = S['music'], S['music_volume'] / 10
    sound.set_music_volume()
