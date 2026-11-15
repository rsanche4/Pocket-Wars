"""Hard CPU's memory of you, kept in learned.json next to main.py (delete it, or use Options, to make Hard forget).

After every finished Player vs Hard CPU battle it remembers two things:
  - which of its styles (data/ai.json "styles") beat you, so it plays those more and more;
  - which vehicles you build and how often, so it expects them (even in fog) and counters them early.
Picking a style is a weighted draw (Thompson sampling): styles that beat you come up more, the others still now and
then, so if you change how you play, Hard notices.
"""
import json
import os
import random

from .data import ROOT
from .ai import STYLES

PATH = os.path.join(ROOT, 'learned.json')
VEHICLES = ['halftrack', 'tank', 'helicopter']


def blank():
    return {'games': 0, 'you_won': 0,
            'styles': {name: {'won': 0, 'lost': 0} for name in STYLES},
            'you': {'turns': 0, 'built': {t: 0 for t in VEHICLES}}}


def load():
    """The memory from learned.json (a fresh one if the file is missing or broken)."""
    mem = blank()
    try:
        with open(PATH, encoding='utf-8') as f:
            saved = json.load(f)
        mem['games'], mem['you_won'] = saved['games'], saved['you_won']
        for name, rec in saved['styles'].items():
            if name in mem['styles']:
                mem['styles'][name].update(rec)
        mem['you']['turns'] = saved['you']['turns']
        mem['you']['built'].update(saved['you']['built'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return mem


def save(mem):
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(mem, f, indent=1)


def forget():
    if os.path.exists(PATH):
        os.remove(PATH)


def pick_style(mem):
    """Each style draws a random 'chance of beating you' from its record; the highest draw plays."""
    draw = {name: random.betavariate(1 + r['won'], 1 + r['lost']) for name, r in mem['styles'].items()}
    return max(draw, key=draw.get)


def habits(mem):
    """What Hard expects from you, or None before your first battle. rate = chance you build a vehicle on a turn,
    mix = how your vehicles split between the types (evened out a little while Hard knows little)."""
    you = mem['you']
    if not mem['games'] or not you['turns']:
        return None
    built = sum(you['built'].values())
    mix = {t: (you['built'][t] + 1) / (built + len(VEHICLES)) for t in VEHICLES}
    return {'rate': min(1, (built + 1) / (you['turns'] + 2)), 'mix': mix}


def record(mem, game, you, style):
    """Add a finished battle: `you` = your side, `style` = the style Hard played."""
    won = game.winner == you
    mem['games'] += 1
    mem['you_won'] += won
    mem['styles'].setdefault(style, {'won': 0, 'lost': 0})['lost' if won else 'won'] += 1
    mem['you']['turns'] += sum(1 for k in range(1, game.turn + 1) if (k - 1) % 2 == you)     # Green plays odd turns
    for t, n in game.totals[you]['by_build'].items():
        mem['you']['built'][t] = mem['you']['built'].get(t, 0) + n


def favourite(mem):
    """The vehicle you build most, or None."""
    built = mem['you']['built']
    return max(built, key=built.get) if sum(built.values()) else None
