"""CPU players. They follow the same rules and see only what fog allows.

turn(game, level) is a generator: it yields one action at a time (see Game.do) and receives the result back,
so the game screen can animate each action and tests can run thousands of games without any drawing.

Normal CPU: simple rules of thumb.
Hard CPU:   scores every move (weights in data/ai.json), thinks ahead on private copies of the board, plays one of
            several styles, and against you uses what it has learned about you (learn.py).
"""
import random

from .data import UNITS, AI
from .rules import Game, Unit, new_totals, flies, can_hit, damage_range

W = AI['weights']          # Hard CPU tuning (data/ai.json)
VALUE = AI['value']


def avg(t):
    lo, hi = UNITS[t]['damage']
    return (lo + hi) / 2


def cost(t):
    return UNITS[t]['cost']


def power(g, i):
    return sum(avg(u.type) for u in g.units[i])


def bfs(g, seeds, ground=False):
    """Steps from the nearest seed to every outpost (99 = can't get there)."""
    d = {s: 0 for s in seeds}
    todo = list(seeds)
    while todo:
        a = todo.pop(0)
        for b in g.adj[a]:
            if b not in d and (not ground or g.road(a, b)):
                d[b] = d[a] + 1
                todo.append(b)
    return lambda i: d.get(i, 99)


def home_dist(g, p):
    return bfs(g, [g.hq[p]])


def enemy_dist(g, p, ground):
    """Distance to the enemy HQ. In blackout, before finding it, head for the far edge of what has been explored."""
    g.update_seen()
    seeds = [g.hq[1 - p]]
    if g.blackout and g.hq[1 - p] not in g.seen[p]:
        seen, home = g.seen[p], home_dist(g, p)
        edge = [i for i in seen if any(j not in seen for j in g.adj[i])]
        if edge:
            far = max(home(i) for i in edge)
            seeds = [i for i in edge if home(i) >= far - 1]
    return bfs(g, seeds, ground)


def best(items, key):
    """The item with the lowest key; ties are broken at random."""
    return min(items, key=lambda i: (key(i), random.random()))


def visible(g, p):
    return g.sight(p) if g.fog else None


# ===================================================================== Normal CPU
def want(g, p):
    vs = visible(g, p)
    if g.vehicles(1 - p, 'tank', vs) > g.vehicles(p, 'helicopter'):
        return 'helicopter'
    if g.vehicles(1 - p, 'helicopter', vs) > g.vehicles(p, 'halftrack') + g.vehicles(p, 'tank'):
        return 'halftrack'
    return ['tank', 'helicopter', 'halftrack'][g.turn // 2 % 3]


def normal_place(g, p):
    spots = [i for i in range(len(g.units)) if g.can_place(p, i)]
    if not spots:
        return None
    if random.random() < .1:
        return random.choice(spots)
    free_barracks = [i for i in spots if g.owner(i) is None and g.map.nodes[i].barracks]
    if free_barracks:
        return best(free_barracks, home_dist(g, p))
    hq = g.hq[p]
    if sum(power(g, j) for j in g.adj[hq] if g.owner(j) == 1 - p) > 12:
        return hq
    w = want(g, p)
    if w and g.count(hq, 'soldier') < cost(w):
        return hq
    front = [i for i in g.mine(p) if any(g.owner(j) == 1 - p for j in g.adj[i])]
    if front:
        return best(front, lambda i: power(g, i) - .6 * sum(power(g, j) for j in g.adj[i] if g.owner(j) == 1 - p))
    d = enemy_dist(g, p, True)
    return best(spots, lambda i: (d(i), -power(g, i)))


def normal_buy(g, p):
    w = want(g, p)
    d = enemy_dist(g, p, True)
    spots = [i for i in g.mine(p) if g.count(i, 'soldier') >= cost(w)]
    return (best(spots, d), w) if spots else None


def normal_march(g, p):
    m, dg, da, w, hq = g.mine(p), enemy_dist(g, p, True), enemy_dist(g, p, False), want(g, p), g.hq[p]

    def spare(a):          # keep enough soldiers at the HQ to pay for the next vehicle
        mv = g.movable(a)
        if a == hq and w:
            return [x for x in mv if x.type != 'soldier'] + [x for x in mv if x.type == 'soldier'][cost(w):]
        return mv

    if random.random() < .1:
        sources = [i for i in m if spare(i)]
        if sources:
            a = random.choice(sources)
            ds = list(g.destinations(p, a, spare(a)).items())
            if ds:
                return a, random.choice(ds)[1], spare(a)
    home = home_dist(g, p)
    for want_air in (True, False):          # grab free barracks, flyers first
        pick = None
        for a in m:
            for x in spare(a):
                if flies(x.type) != want_air:
                    continue
                for b, path in g.destinations(p, a, [x]).items():
                    if g.map.nodes[b].barracks and g.owner(b) is None and (not g.blackout or b in g.seen[p]):
                        k = home(b) + random.random() * .5
                        if pick is None or k < pick[0]:
                            pick = (k, a, path, x)
        if pick:
            return pick[1], pick[2], [pick[3]]
    helis = [a for a in m if any(x.type == 'helicopter' for x in g.units[a]) and da(a) > 1]
    if helis:
        a = min(helis, key=da)
        hs = [x for x in g.units[a] if x.type == 'helicopter']
        ds = [(b, path) for b, path in g.destinations(p, a, hs).items() if da(b) < da(a)]
        if ds:
            return a, best(ds, lambda bp: da(bp[0]))[1], hs
    rear = [a for a in m if not any(g.owner(j) == 1 - p and g.road(a, j) for j in g.adj[a])]
    rear.sort(key=lambda a: (-sum(x.hp for x in spare(a)), random.random()))
    for a in rear:
        group = [x for x in spare(a) if x.type != 'helicopter']
        if group:
            ds = [(b, path) for b, path in g.destinations(p, a, group).items() if dg(b) < dg(a)]
            if ds:
                return a, best(ds, lambda bp: dg(bp[0]))[1], group
    for a in sorted(m, key=lambda a: -g.count(a, 'soldier')):
        soldiers = [x for x in spare(a) if x.type == 'soldier']
        if len(soldiers) >= 2:
            ds = [(b, path) for b, path in g.destinations(p, a, soldiers[:1]).items() if g.owner(b) is None]
            if ds:
                return a, best(ds, lambda bp: dg(bp[0]))[1], soldiers[:1]
    return None


def value(t):
    return (1 if t == 'soldier' else 30 if t == 'hq' else cost(t)) / UNITS[t]['hp']


def normal_score(g, a, b, x, y):
    lo, hi = damage_range(x.type, y.type)
    dealt = min((lo + hi) / 2, y.hp)
    back = sum(damage_range(y.type, x.type)) / 2 if can_hit(y.type, x.type) else 0
    taken = min(back, x.hp)
    v = dealt * value(y.type) - taken * value(x.type)
    if y.hp <= lo:
        v += .1 * value(y.type) * UNITS[y.type]['hp']
    if y.type == 'hq':
        v += dealt * .5
    if x.type == 'hq':
        v -= taken * .2
    return v


def normal_turn(g, p):
    while g.to_place > 0:
        i = normal_place(g, p)
        if i is None:
            break
        yield 'place', i
    yield ('end_gather',)
    b = normal_buy(g, p)
    if b:
        yield ('buy',) + b
    mv = None if g.turn == 1 else normal_march(g, p)
    yield ('march', mv[0], mv[1], [u.id for u in mv[2]]) if mv else ('skip_march',)
    if g.turn == 1:
        return
    for _ in range(300):
        if g.phase != 'attack':
            break
        opts = [(normal_score(g, a, b, x, y) + (random.random() - .5) * .3, a, b, x, y) for a, b, x, y in attack_options(g, p)]
        if not opts:
            break
        s, a, b, x, y = max(opts, key=lambda o: o[0])
        if s < 0:
            break
        fight = yield 'fight', a, b, x, y
        if g.phase == 'over':
            return
        if fight.result == 'cleared':
            can = g.move_in_choices(a, b)
            yield 'move_in', a, b, [u.id for u in can[:max(1, len(can) // 2)]]


def attack_options(g, p):
    return [(a, b, x, y) for a in g.mine(p) for b in g.adj[a] if g.owner(b) == 1 - p
            for x in g.units[a] if x.id not in g.used for y in g.units[b] if can_hit(x.type, y.type)]


# ===================================================================== Hard CPU (same rules and sight, smarter choices)
def p_kill(lo, hi, hp):
    if hp <= lo:
        return 1
    if hp > hi:
        return 0
    return (hi - hp + 1) / (hi - lo + 1)


def expected_damage(lo, hi, hp):
    return sum(min(d, hp) for d in range(lo, hi + 1)) / (hi - lo + 1)


def can_see(g, p):
    vs = visible(g, p)
    return lambda i: vs is None or i in vs


def threat_map(g, p):
    """How much enemy firepower could reach each outpost next turn."""
    see, th = can_see(g, p), [0] * len(g.units)
    for j in range(len(g.units)):
        if g.owner(j) != 1 - p or not see(j):
            continue
        for u in g.units[j]:
            air = flies(u.type)
            reach = 1 if u.type == 'hq' else 4 if air else UNITS[u.type]['move'] + 1
            d, todo = {j: 0}, [j]
            while todo:
                x = todo.pop(0)
                if d[x] >= reach:
                    continue
                for y in g.adj[x]:
                    if y not in d:
                        d[y] = d[x] + 1
                        todo.append(y)
            for k, dd in d.items():
                if dd:
                    th[k] += avg(u.type) * (1 if dd == 1 else .7 if air else .45)
    return th


def attack_score(g, a, b, x, y, lethal):
    lo, hi = damage_range(x.type, y.type)
    pk, dealt = p_kill(lo, hi, y.hp), expected_damage(lo, hi, y.hp)
    if y.type == 'hq':
        gain = dealt * W['hqHit'] * (4 if lethal else 1) + pk * 1000
    else:
        gain = pk * VALUE[y.type] + (1 - pk) * dealt / UNITS[y.type]['hp'] * VALUE[y.type] * W['chip']
    loss = 0
    if can_hit(y.type, x.type):
        l2, h2 = damage_range(y.type, x.type)
        pd, bd = p_kill(l2, h2, x.hp), expected_damage(l2, h2, x.hp)
        if x.type == 'hq':
            loss = bd * .05 * W['ownHQ']
        else:
            loss = pd * VALUE[x.type] + (1 - pd) * bd / UNITS[x.type]['hp'] * VALUE[x.type] * W['chip']
    if y.type != 'hq' and len(g.units[b]) == 1:
        enemy_of_a = g.cur if g.owner(a) is None else 1 - g.owner(a)
        gain += pk * W['clear'] * (2 if g.map.nodes[b].barracks else 1) * (1.5 if g.hq[enemy_of_a] in g.adj[b] else 1)
    return gain - loss * W['risk']


def hard_want(g, p):
    """Vehicle types, most wanted first. Against a player it has learned about, Hard also expects the vehicles
    that player usually builds (so it counters them before seeing them)."""
    vs = visible(g, p)
    habits = getattr(g, 'habits', {}).get(1 - p)
    expect = (lambda t: habits['mix'].get(t, 0) * AI['learn_counter']) if habits else (lambda t: 0)
    e = lambda t: g.vehicles(1 - p, t, vs) + expect(t)
    m = lambda t: g.vehicles(p, t)
    score = {'halftrack': W['bJ'] + e('helicopter') - .4 * e('tank') - .25 * m('halftrack'),
             'tank': W['bT'] + .5 * e('halftrack') + .1 * e('soldier') - e('helicopter') - .25 * m('tank'),
             'helicopter': W['bH'] + .8 * e('tank') - .8 * e('halftrack') - .25 * m('helicopter')}
    return sorted(score, key=lambda t: (-score[t], random.random()))


def hp_at(g, i):
    return sum(u.hp for u in g.units[i])


def hard_stage(g, p, th):
    """The safe outpost closest to the enemy, where this turn's soldiers gather."""
    dg = enemy_dist(g, p, True)
    safe = [i for i in g.mine(p) if i == g.hq[p] or th[i] <= hp_at(g, i) * .8 + 6]
    return min(safe, key=lambda i: (dg(i), -g.count(i, 'soldier'))) if safe else g.hq[p]


def hard_place(g, p, th, plan):
    spots = [i for i in range(len(g.units)) if g.can_place(p, i)]
    if not spots:
        return None
    free_barracks = [i for i in spots if g.owner(i) is None and g.map.nodes[i].barracks]
    if free_barracks:
        return best(free_barracks, home_dist(g, p))
    hq = g.hq[p]
    q = g.hq_unit(p)
    if q and th[hq] > 14 and q.hp < 50 and g.count(hq, 'soldier') < 3:
        return hq
    if g.count(plan['stage'], 'soldier') < plan['need']:
        return plan['stage']
    pick = None
    for i in spots:
        if g.owner(i) != p:
            continue
        v = 0
        for j in g.adj[i]:
            if g.owner(j) == 1 - p:
                v = max(v, max([0] + [attack_score(g, i, j, Unit(0, p, 'soldier', 10), y, False) for y in g.units[j]]))
        v -= max(0, th[i] - hp_at(g, i)) * .02
        if pick is None or v > pick[0]:
            pick = (v, i)
    return pick[1] if pick and pick[0] > W['front'] else plan['stage']


def habit_buy(g, p, habits):
    """What a learned-about player would probably build now (used when Hard imagines their turn)."""
    if random.random() > habits['rate']:
        return None
    t = random.choices(list(habits['mix']), weights=list(habits['mix'].values()))[0]
    spots = [i for i in g.mine(p) if g.count(i, 'soldier') >= cost(t)]
    return (best(spots, enemy_dist(g, p, True)), t) if spots else None


def hard_buy(g, p):
    if g.bought:
        return None
    habits = getattr(g, 'habits', {}).get(p)
    if habits:
        return habit_buy(g, p, habits)
    dg, order = enemy_dist(g, p, True), hard_want(g, p)
    for t in order:
        spots = [i for i in g.mine(p) if g.count(i, 'soldier') >= cost(t)]
        if spots:
            return best(spots, dg), t
        if t == order[0] and W['keep'] > .5:
            return None
    return None


def hard_march(g, p, th, k=1):
    """The k best-looking marches by quick scoring, best first (each: score, src, path, group)."""
    dg, da, see = enemy_dist(g, p, True), enemy_dist(g, p, False), can_see(g, p)
    picks = []
    for a in g.mine(p):
        sp = g.movable(a)
        if not sp:
            continue
        groups = [sp, [x for x in sp if not flies(x.type)], [x for x in sp if flies(x.type)], [x for x in sp if x.type != 'soldier'],
                  [x for x in sp if x.type == 'soldier'], sp[:-1] if len(sp) > 1 else []]
        tried = set()
        for group in groups:
            key = frozenset(x.id for x in group)
            if not group or key in tried:
                continue
            tried.add(key)
            d = da if all(flies(x.type) for x in group) else dg
            pw = sum(avg(x.type) for x in group)
            hp = sum(x.hp for x in group)
            per_hp = sum(VALUE[x.type] for x in group) / max(1, hp)
            left = len(g.units[a]) - len(group)
            for b, path in g.destinations(p, a, group).items():
                sc = (d(a) - d(b)) * W['prog'] * pw / 5
                if g.map.nodes[b].barracks and g.owner(b) is None:
                    sc += W['bar']
                if g.hq[1 - p] in g.adj[b]:
                    sc += W['nearHQ'] * pw / 5
                ap = 0
                for j in g.adj[b]:
                    if g.owner(j) == 1 - p and see(j):
                        for x in group:
                            ap += max([0] + [attack_score(g, b, j, x, y, False) for y in g.units[j] if can_hit(x.type, y.type)])
                sc += ap * W['atkPot']
                defense = hp + hp_at(g, b)
                sc -= W['risk'] * min(th[b], hp) * per_hp * (1.2 if th[b] > defense * .6 else .5)
                sc += W['risk'] * min(th[a], hp) * per_hp * .4
                if left == 0 and g.map.nodes[a].barracks:
                    sc -= W['bar'] * .8
                picks.append((sc + random.random() * .05, a, path, group))
    picks.sort(key=lambda m: -m[0])
    return picks[:k]


def hard_turn(g, p, think=True):
    """think=False plays on quick scoring alone (used inside the look-ahead, for both sides' imagined turns)."""
    th = threat_map(g, p)
    order = hard_want(g, p)
    plan = {'stage': hard_stage(g, p, th), 'need': 0 if g.bought else cost(order[0])}
    if think and g.to_place > 0:
        for i in place_ahead(g, p, th, plan):
            yield 'place', i
    while g.to_place > 0:
        i = hard_place(g, p, th, plan)
        if i is None:
            break
        yield 'place', i
    yield ('end_gather',)
    if think and g.turn > 1:
        b, mv = look_ahead(g, p)                 # the buy and march are chosen together
        if b:
            yield ('buy',) + b
    else:
        b = hard_buy(g, p)
        if b:
            yield ('buy',) + b
        if g.turn == 1:                          # Green's first turn: no march, no attack
            yield ('skip_march',)
            return
        mv = next((m[1:] for m in hard_march(g, p, threat_map(g, p)) if m[0] > 0), None)
    yield ('march', mv[0], mv[1], [u.id for u in mv[2]]) if mv else ('skip_march',)
    yield from hard_attacks(g, p)


def hard_attacks(g, p):
    for _ in range(300):
        if g.phase != 'attack':
            break
        enemy_hq = g.hq_unit(1 - p)
        reach = sum(avg(x.type) for a in g.adj[g.hq[1 - p]] if g.owner(a) == p for x in g.units[a] if x.id not in g.used)
        lethal = bool(enemy_hq) and reach >= enemy_hq.hp * W['lethal']
        opts = [(attack_score(g, a, b, x, y, lethal), a, b, x, y) for a, b, x, y in attack_options(g, p)]
        if not opts:
            break
        s, a, b, x, y = max(opts, key=lambda o: o[0])
        if s < W['thresh']:
            break
        fight = yield 'fight', a, b, x, y
        if g.phase == 'over':
            return
        if fight.result == 'cleared':
            can = sorted(g.move_in_choices(a, b), key=lambda u: -VALUE[u.type])
            keep = 0 if a == g.hq[p] else 1
            yield 'move_in', a, b, [u.id for u in can[:max(1, len(can) - keep)]]


# ===================================================================== Hard CPU: thinking ahead
# Before placing soldiers, and again before buying and marching, Hard tries its most promising options on private
# copies of the board: it plays out the rest of its turn and the enemy's reply (both with the quick scoring above),
# a few times each because shots are random, and keeps the option that leaves it best off (evaluate()).
# The copies only hold enemy units Hard can see, so fog is respected. Settings: "look_ahead" and "eval" in ai.json.
LOOK = AI['look_ahead']
E = AI['eval']


def copy_game(g, p, full=False):
    """A private copy of the battle as side p sees it. full=True keeps hidden enemies too: use it only to work out
    which moves are allowed (the rules know who holds an outpost), never to judge how good a move is."""
    s = Game.__new__(Game)
    s.__dict__.update(g.__dict__)
    see = (lambda i: True) if full else can_see(g, p)
    s.units = [[Unit(u.id, u.side, u.type, u.hp) for u in us if u.side == p or see(i)] for i, us in enumerate(g.units)]
    s.seen = [set(g.seen[0]), set(g.seen[1])]
    s.used = set(g.used)
    s.next_id = list(g.next_id)
    s.history, s.totals = [], [new_totals(), new_totals()]
    return s


def run(s, actions):
    """Play a stream of actions on a game (or a copy) as fast as possible."""
    result = None
    try:
        while True:
            result = s.do(actions.send(result))
    except StopIteration:
        pass


def evaluate(s, p):
    """How good the board looks for side p (bigger is better)."""
    if s.phase == 'over':
        return 10000 if s.winner == p else -10000
    score = 0
    for side, sign in ((p, 1), (1 - p, -1)):
        q = s.hq_unit(side)
        score += sign * (q.hp if q else 0) * E['hq']
        mine = s.mine(side)
        score += sign * len(mine) * E['outpost']
        score += sign * sum(1 for i in mine if s.map.nodes[i].barracks) * E['barracks']
        for i in mine:
            for u in s.units[i]:
                if u.type != 'hq':                 # a hurt unit is still worth something
                    score += sign * VALUE[u.type] * (.4 + .6 * u.hp / UNITS[u.type]['hp']) * E['army']
    return score


def placement_plans(g, p, th, plan):
    """A few different ideas of where this turn's soldiers go, each as a list of outposts."""
    def front(s):
        mine = [i for i in s.mine(p) if any(s.owner(j) == 1 - p for j in s.adj[i])]
        return max(mine, key=lambda i: (sum(power(s, j) for j in s.adj[i] if s.owner(j) == 1 - p), -i)) if mine else None

    def spread(s):
        dg = enemy_dist(s, p, True)
        free = [i for i in range(len(s.units)) if s.owner(i) is None and s.can_place(p, i)]
        return min(free, key=lambda i: (dg(i), i)) if free else plan['stage']

    ideas = {'usual': lambda s: hard_place(s, p, th, plan), 'stage': lambda s: plan['stage'], 'front': front,
             'hq': lambda s: s.hq[p], 'spread': spread}
    plans = []
    for name in LOOK['placements']:
        s, seq = copy_game(g, p, full=True), []
        while s.to_place > 0:
            free_barracks = [i for i in range(len(s.units)) if s.owner(i) is None and s.map.nodes[i].barracks and s.can_place(p, i)]
            i = best(free_barracks, home_dist(s, p)) if free_barracks else ideas[name](s)
            if i is None or not s.can_place(p, i):
                break
            s.place(i)
            seq.append(i)
        if seq not in plans:
            plans.append(seq)
    return plans


def place_ahead(g, p, th, plan):
    """Pick the placement plan whose quick follow-up (rest of the turn, then the enemy's reply) looks best."""
    plans = placement_plans(g, p, th, plan)
    if len(plans) < 2:
        return plans[0] if plans else []
    best_seq, best_v = None, None
    for seq in plans:
        v = 0
        for _ in range(LOOK['tries']):
            s = copy_game(g, p)
            for i in seq:
                s.place(i)
            s.to_place = 0
            run(s, hard_turn(s, p, think=False))
            if s.phase != 'over':
                enemy_reply(s, p)
            v += evaluate(s, p)
        if best_v is None or v > best_v:
            best_seq, best_v = seq, v
    return best_seq


def buy_options(g, p):
    """Vehicles worth trying: the top few wanted types that can be paid for, and buying nothing."""
    if g.bought:
        return [None]
    dg, out = enemy_dist(g, p, True), []
    for t in hard_want(g, p):
        spots = [i for i in g.mine(p) if g.count(i, 'soldier') >= cost(t)]
        if spots and len(out) < LOOK['buys']:
            out.append((best(spots, dg), t))
    return out + [None]


def look_ahead(g, p):
    """Returns (buy, march): the best combination of the buys and marches tried (None = don't)."""
    best_plan, best_v = (None, None), None
    for b in buy_options(g, p):
        base = g
        if b:
            base = copy_game(g, p, full=True)
            base.buy(*b)
        options = [m[1:] for m in hard_march(base, p, threat_map(base, p), LOOK['marches'])] + [None]
        for mv in options:
            v = 0
            for _ in range(LOOK['tries']):
                s = copy_game(base, p)
                if mv:
                    s.march(mv[0], mv[1], [u.id for u in mv[2]])
                else:
                    s.skip_march()
                v += finish_and_reply(s, p)
            if best_v is None or v > best_v:
                best_plan, best_v = (b, mv), v
    return best_plan


def style_of(g, side):
    """The style a side's Hard plays (None = balanced; a human is imagined as balanced)."""
    return (getattr(g, 'styles', None) or [None, None])[side]


def enemy_reply(s, p):
    """The enemy's next turn on a copy, in the enemy's own style."""
    s.end_turn()
    use_style(style_of(s, 1 - p))
    run(s, hard_turn(s, 1 - p, think=False))
    use_style(style_of(s, p))


def finish_and_reply(s, p):
    """Play out the rest of p's attacks and the enemy's reply on a copy, then score it."""
    run(s, hard_attacks(s, p))
    if s.phase != 'over':
        enemy_reply(s, p)
    return evaluate(s, p)


# ===================================================================== Hard CPU: styles
STYLES = AI['styles']
BASE_W, BASE_E = dict(W), dict(E)


def use_style(name):
    """Switch Hard to one of the styles in data/ai.json (None = balanced)."""
    style = STYLES.get(name) or {}
    W.clear()
    W.update(BASE_W, **style.get('weights', {}))
    E.clear()
    E.update(BASE_E, **style.get('eval', {}))


def turn(g, level):
    """g.styles (optional) = the style each side's Hard plays; g.habits (optional) = {side: what Hard learned about
    that player}, set by the battle screen from learn.py."""
    if level != 'hard':
        return normal_turn(g, g.cur)
    use_style(style_of(g, g.cur))
    return hard_turn(g, g.cur)


def play_turn(g, level):
    """Run a whole CPU turn instantly (no animation)."""
    run(g, turn(g, level))
    if g.phase != 'over':
        g.end_turn()
