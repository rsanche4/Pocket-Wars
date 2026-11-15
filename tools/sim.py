"""Play CPU-vs-CPU games with no graphics and print who wins. Handy for checking maps are fair and the CPU still works.

    py tools/sim.py                      # 100 Normal-vs-Normal games on every map
    py tools/sim.py --games 300 --level hard --fog fog
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pw.data import load_maps          # noqa: E402
from pw.rules import Game              # noqa: E402
from pw.ai import play_turn            # noqa: E402

TURN_LIMIT = 400                       # after this many turns the game counts as a draw


def play(m, level, fog):
    g = Game(m, fog)
    while g.phase != 'over' and g.turn <= TURN_LIMIT:
        play_turn(g, level)
    return (g.winner if g.phase == 'over' else -1), g.turn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=100)
    ap.add_argument('--level', default='normal', choices=['normal', 'hard'])
    ap.add_argument('--fog', default='off', choices=['off', 'fog', 'blackout'])
    ap.add_argument('--map', default='', help='only maps whose name contains this')
    a = ap.parse_args()
    print(f'{a.games} games per map, {a.level} vs {a.level}, fog {a.fog}')
    print(f"{'map':14s} green%  tan%  draw  avg turns")
    start = time.time()
    for m in load_maps():
        if m.custom or a.map.lower() not in m.name.lower():
            continue
        res = [play(m, a.level, a.fog) for _ in range(a.games)]
        n = len(res)
        green = sum(w == 0 for w, _ in res) / n * 100
        tan = sum(w == 1 for w, _ in res) / n * 100
        draw = sum(w == -1 for w, _ in res)
        print(f'{m.name:14s} {green:5.1f} {tan:5.1f} {draw:5d}  {sum(t for _, t in res) / n:6.1f}')
    print(f'took {time.time() - start:.0f}s')


if __name__ == '__main__':
    main()
