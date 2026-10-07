"""The bots' brain. game.py decides how many bots there are and when they spawn; this file decides
what a living bot does each tick.

`think(bot, game, map, dt)` is called once per tick for every living bot. It may change `bot.yaw` and
`bot.pitch`, call `game.fire(...)` and `game.switch_weapon(...)` as a person's browser would, and keeps
everything it remembers in `bot.brain` (emptied at each spawn). It returns the movement input for
motion.step: {forward, right, jump}, each as in motion.py; game.py adds the bot's yaw and moves it.

How a bot plays (specs/game.md, Bots):

- Moving. The map's waypoint graph has nodes and one-way edges of three kinds: walk, jump (a gap a
  running jump crosses) and pad (walk onto the pad at the edge's start; it throws you to the end). A bot
  plans the shortest path by distance (Dijkstra) from the nearest node it can walk to, and follows it
  node by node. Walk edges: steer at the next node; if that node is lower (a drop), steer in the air so
  as to land on it. Jump edges: run at the node and press jump just before the ground ends, then steer
  in the air to land on it. Pad edges: walk onto the pad, then let go of the keys until landing, since
  the pad's throw already lands on the target and steering would spoil it. Thrown off its path (by a
  shell, or a pad it did not mean to touch), a bot does nothing in the air and replans from where it
  lands.
- Goal: the nearest visible enemy if it holds a Launcher or Beam with ammo; otherwise the nearest
  useful pickup by path length (a weapon it lacks or is low on, health below 60, armor); otherwise a
  wander point. Re-chosen twice a second.
- Shooting: the nearest visible enemy, after a reaction delay; aim error starts at up to 4 degrees and
  shrinks the longer the target stays in view; the Launcher aims at a grounded target's feet, leading
  it. Beam at long range, Launcher at mid range, Blaster close. A bot fires only along a clear line, only
  when the weapon is ready, and through `game.fire`, which checks everything a person's shot is checked
  for.

Tests and tools may set `bot.brain["order"] = node index` to send a bot to that node and keep it there.
"""

from __future__ import annotations

import heapq
import math
import random
import weakref

from . import game as rules

# Invented names, so no bot is mistaken for a real person or borrowed from another game.
NAMES = [
    "Brindlewick", "Corvessa", "Dunmore Flick", "Embrel", "Fizzwick", "Gorvane", "Halloway Pim", "Iskra Venn",
    "Jorvel", "Kestrin", "Lumbrick Fett", "Mopple", "Nimbra", "Ostrel", "Pellifer", "Quillon", "Raspen",
    "Snerkle", "Tavish Orr", "Ulmara", "Vexley", "Wobbleton", "Yarrow Kint", "Zelmo",
]

# --- Difficulty: one setting for now -------------------------------------------------------------
REACTION = 0.25        # seconds a target must be in view before the first shot
AIM_ERROR = 4.0        # degrees of aim error when a target first comes into view
AIM_SETTLE = 1.5       # seconds for the aim error to shrink to about a third
AIM_FLOOR = 0.6        # degrees of aim error that never goes away
AIM_WANDER = 0.35      # seconds between new directions of the aim error
LEAD = 0.8             # how much of a target's movement the Launcher leads (1 is perfect)
AIM_LAG = 0.1          # seconds the aim trails a moving target, so dodging works against bots
BEAM_RANGE = 25.0      # metres beyond which the Beam is preferred
LAUNCHER_MIN = 4.5     # metres under which the Launcher would hurt its shooter too
KEEP = {1: 8.0, 2: 11.0, 3: 22.0}   # stop closing in on a target at this distance, by weapon

# --- Movement ------------------------------------------------------------------------------------
ARRIVE = 0.75          # metres from a node that count as reaching it
GOAL_EVERY = 0.5       # seconds between goal choices
REPLAN_STUCK = 4.0     # seconds without reaching a node before replanning
GIVE_UP_STUCK = 8.0    # seconds without reaching a node before picking a new goal
DROP = 1.0             # a next node this much lower is a drop: steer in the air to land on it
JUMP_PROBE = 0.3       # press jump when the ground ends this far ahead
LEVEL = 0.6            # metres up or down that count as the same level when walking


def pick_name(taken: set[str], rng: random.Random) -> str:
    """A bot name nobody in the arena has; a numbered one if every name is in use."""
    free = [n for n in NAMES if n not in taken]
    if free:
        return rng.choice(free)
    n = 2
    while f"{NAMES[0]} {n}" in taken:
        n += 1
    return f"{NAMES[0]} {n}"


# --- The waypoint graph, worked out once per map ------------------------------------------------

class Graph:
    def __init__(self, m) -> None:
        self.at = [tuple(float(v) for v in n["at"]) for n in m.nodes]
        self.out: list[list[tuple[int, str, float]]] = [[] for _ in self.at]
        self.pad_nodes: set[int] = set()
        for e in m.edges:
            a, b, how = e["from"], e["to"], e["how"]
            self.out[a].append((b, how, math.dist(self.at[a], self.at[b])))
            if how == "pad":
                self.pad_nodes.add(a)
        self.plain = [i for i in range(len(self.at)) if i not in self.pad_nodes]
        self.item_node = [self.nearest(m, *item["at"]) for item in m.items]

    def nearest(self, m, x, y, z, walk_only: bool = True) -> int:
        """The nearest node (not a pad) a player at (x, y, z) can walk straight to; failing that, the
        nearest node not on a pad."""
        near = sorted(self.plain, key=lambda i: math.dist((x, y, z), self.at[i]))
        if walk_only:
            for i in near[:10]:
                if walkable(m, (x, y, z), self.at[i]):
                    return i
        return near[0]

    def dijkstra(self, start: int):
        """Shortest path lengths from `start` to every node, and each node's previous node."""
        dist = [math.inf] * len(self.at)
        prev = [-1] * len(self.at)
        dist[start] = 0.0
        heap = [(0.0, start)]
        while heap:
            d, a = heapq.heappop(heap)
            if d > dist[a]:
                continue
            for b, _how, cost in self.out[a]:
                if d + cost < dist[b]:
                    dist[b], prev[b] = d + cost, a
                    heapq.heappush(heap, (d + cost, b))
        return dist, prev

    def how(self, a: int, b: int) -> str:
        return next((h for n, h, _c in self.out[a] if n == b), "walk")


_graphs: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def graph(m) -> Graph:
    g = _graphs.get(m)
    if g is None:
        g = _graphs[m] = Graph(m)
    return g


# --- Geometry helpers ---------------------------------------------------------------------------

def ground_at(m, x, y, z) -> bool:
    """True if there is something to stand on at (x, z) within LEVEL of height y."""
    s = m.surface_under(x, y, z, above=LEVEL)
    return s is not None and s.max[1] >= y - LEVEL


def on_pad(m, x, y, z) -> bool:
    return any(p.min[0] - 0.4 <= x <= p.max[0] + 0.4 and p.min[2] - 0.4 <= z <= p.max[2] + 0.4
               and abs(p.max[1] - y) < 1.0 for p in m.pads)


def walkable(m, a, b) -> bool:
    """A straight walk from a to b stays on the same level, touches no pad on the way and meets no box."""
    if abs(a[1] - b[1]) > LEVEL:
        return False
    n = max(1, int(math.dist((a[0], a[2]), (b[0], b[2])) / 0.5))
    for k in range(n + 1):
        f = k / n
        x, y, z = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
        if not ground_at(m, x, y, z):
            return False
        if k < n and on_pad(m, x, y, z):
            return False
    return m.segment_hit((a[0], a[1] + 1.0, a[2]), (b[0], b[1] + 1.0, b[2])) is None


def safe_step(m, x, y, z, wx, wz) -> bool:
    """True if walking along unit (wx, wz) keeps ground under the next metre and avoids pads."""
    for d in (0.6, 1.2):
        px, pz = x + wx * d, z + wz * d
        if not ground_at(m, px, y, pz) or on_pad(m, px, y, pz):
            return False
    return True


def look(d) -> tuple[float, float]:
    """Yaw and pitch for a direction (yaw 0 looks toward -z, positive turns left)."""
    return math.atan2(-d[0], -d[2]), math.atan2(d[1], math.hypot(d[0], d[2]))


def unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (0.0, 0.0, -1.0) if n < 1e-9 else (v[0] / n, v[1] / n, v[2] / n)


def scatter(d, spread: float, rng: random.Random):
    """Turn unit d by a random angle up to `spread` radians, evenly over the disc (as the browser does)."""
    if not spread:
        return d
    helper = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = unit((d[1] * helper[2] - d[2] * helper[1], d[2] * helper[0] - d[0] * helper[2], d[0] * helper[1] - d[1] * helper[0]))
    v = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    angle, turn = spread * math.sqrt(rng.random()), rng.random() * 2 * math.pi
    s, c = math.sin(angle), math.cos(angle)
    return unit(tuple(d[i] * c + (u[i] * math.cos(turn) + v[i] * math.sin(turn)) * s for i in range(3)))


# --- Seeing -------------------------------------------------------------------------------------

def visible(m, eye, p) -> bool:
    """Some of player p's body (chest or head) can be seen from eye."""
    return any(m.segment_hit(eye, (p.x, p.y + h, p.z)) is None for h in (1.0, 1.6))


def sight(bot, game, m, now: float):
    """Track the enemies in view: their speed, and the nearest one. Returns it, or None."""
    brain = bot.brain
    seen = brain.setdefault("seen", {})     # id -> time it came into view
    track = brain.setdefault("track", {})   # id -> (time, x, y, z, vx, vy, vz)
    eye = bot.eye
    best, best_d = None, math.inf
    for p in game.arena():
        if p is bot or p.dead:
            seen.pop(p.id, None)
            continue
        old = track.get(p.id)
        if old and now > old[0]:
            dt = now - old[0]
            v = ((p.x - old[1]) / dt, (p.y - old[2]) / dt, (p.z - old[3]) / dt)
            if max(abs(c) for c in v) > 60:   # a respawn, not a move
                v = (0.0, 0.0, 0.0)
            v = tuple(0.5 * a + 0.5 * b for a, b in zip(v, old[4:]))
        else:
            v = (0.0, 0.0, 0.0)
        track[p.id] = (now, p.x, p.y, p.z, *v)
        d = math.dist(eye, (p.x, p.y + 1.0, p.z))
        if d > rules.WEAPONS[rules.BEAM]["range"] or not visible(m, eye, p):
            seen.pop(p.id, None)
            continue
        seen.setdefault(p.id, now)
        if d < best_d:
            best, best_d = p, d
    return best


# --- Goals and paths ----------------------------------------------------------------------------

def armed(bot) -> bool:
    return any(w in bot.weapons and bot.ammo.get(w, 0) > 0 for w in (rules.LAUNCHER, rules.BEAM))


def useful(bot, kind: str) -> bool:
    spec = rules.ITEMS[kind]
    if "health" in spec:
        return bot.hp < 60
    if "armor" in spec:
        return bot.armor < 150
    if "weapon" in spec:
        w = spec["weapon"]
        return w not in bot.weapons or bot.ammo[w] < 5
    w = spec["ammo_for"]
    return w in bot.weapons and bot.ammo[w] < 5


def choose_goal(bot, game, m, g: Graph, target, now: float):
    """(kind, node, point): where the bot wants to go now."""
    brain = bot.brain
    order = brain.get("order")
    if order is not None:
        return ("order", order, g.at[order])
    if target is not None and armed(bot):
        return ("enemy", g.nearest(m, target.x, target.y, target.z), (target.x, target.y, target.z))
    start = brain.get("start")
    if start is None:
        start = g.nearest(m, bot.x, bot.y, bot.z)
    dist, _prev = g.dijkstra(start)
    best, best_d = None, math.inf
    for i, item in enumerate(m.items):
        if now < game.items_back[i] or not useful(bot, item["type"]):
            continue
        d = dist[g.item_node[i]]
        if d < best_d:
            best, best_d = i, d
    if best is not None:
        item = m.items[best]
        return ("item", g.item_node[best], tuple(float(v) for v in item["at"]))
    old = brain.get("goal")
    if old and old[0] == "wander" and not brain.get("done"):
        return old
    node = game.rng.choice([i for i in g.plain if dist[i] < math.inf] or g.plain)
    return ("wander", node, g.at[node])


def plan(bot, m, g: Graph, goal_node: int) -> None:
    """A fresh path from the nearest walkable node to goal_node."""
    brain = bot.brain
    start = g.nearest(m, bot.x, bot.y, bot.z)
    brain["start"] = start
    dist, prev = g.dijkstra(start)
    path = []
    if dist[goal_node] < math.inf:
        n = goal_node
        while n != -1:
            path.append(n)
            n = prev[n]
        path.reverse()
    else:
        path = [start]
    brain["path"] = path
    brain["via"] = ["walk"] + [g.how(path[k - 1], path[k]) for k in range(1, len(path))]
    # Skip a first node that lies behind: go straight to the second when it can be walked to.
    while len(path) >= 2 and brain["via"][1] == "walk" and walkable(m, (bot.x, bot.y, bot.z), g.at[path[1]]):
        path.pop(0)
        brain["via"].pop(0)
        brain["via"][0] = "walk"
    brain["planned_for"] = goal_node


def reached(brain, now: float) -> None:
    brain["path"].pop(0)
    brain["via"].pop(0)
    brain["progress_at"] = brain["node_at"] = now


# --- Steering -----------------------------------------------------------------------------------

def land_on(s, x, y, z, target, gravity: float, run: float):
    """In the air: the horizontal wish that brings the body down on `target`."""
    rise = target[1] - y
    disc = s["vy"] * s["vy"] - 2 * gravity * rise
    if disc < 0:
        t = 0.3
    else:
        t = max(0.15, (s["vy"] + math.sqrt(disc)) / gravity)
    want_x, want_z = (target[0] - x) / t, (target[2] - z) / t
    sp = math.hypot(want_x, want_z)
    if sp > run:
        want_x, want_z = want_x / sp * run, want_z / sp * run
    wx, wz = want_x - s["vx"], want_z - s["vz"]
    n = math.hypot(wx, wz)
    if n < 0.3:
        return None
    return (wx / n, wz / n)


def move(bot, game, m, g: Graph, target, engaged: bool, now: float, dt: float):
    """The wished direction on the ground plane (unit x, z, or None) and whether to press jump."""
    brain = bot.brain
    s = bot.motion
    phys = m.physics
    x, y, z = bot.x, bot.y, bot.z
    ground = s["ground"]

    if s.get("launched"):
        brain["air"] = "pad"
        path = brain.get("path") or []
        if path and path[0] in g.pad_nodes:
            reached(brain, now)
    if not ground:
        # A push (shell or Beam) raises the bot's speed allowance: that is how a throw is told
        # from a step off an edge the bot took itself.
        pushed = now - (bot.fast_until - rules.FAST_SECONDS) < 0.3
        mode = brain.get("air")
        if mode is None or (pushed and mode == "plan"):
            mode = brain["air"] = "thrown" if pushed else "plan"
        if mode != "plan":
            return None, False   # thrown, or on a pad's arc: hands off until landing
        path = brain.get("path") or []
        if path and (brain["via"][0] == "jump" or g.at[path[0]][1] < y - DROP or brain.get("jumped")):
            spot = g.at[path[0]]
        else:
            # Stepped off an edge by mistake: come down on the nearest node below.
            below = [i for i in g.plain if g.at[i][1] < y - 0.5]
            if not below or ground_at(m, x, y, z):
                return None, False
            spot = g.at[min(below, key=lambda i: math.hypot(g.at[i][0] - x, g.at[i][2] - z) + 0.3 * (y - g.at[i][1]))]
        return land_on(s, x, y, z, spot, phys["gravity"], phys["run"]), False

    if brain.pop("air", None) is not None:
        # Landed: carry on if the next node is in reach, else replan from here.
        brain["jumped"] = False
        path = brain.get("path") or []
        if not path or not (walkable(m, (x, y, z), g.at[path[0]]) or close(x, y, z, g.at[path[0]])):
            brain["replan"] = True

    goal = brain.get("goal")
    if brain.pop("replan", False) or (goal and brain.get("planned_for") != goal[1]):
        if goal:
            plan(bot, m, g, goal[1])

    since = now - brain.setdefault("progress_at", now)
    if engaged:
        brain["progress_at"] = now
    elif since > GIVE_UP_STUCK:
        brain["done"] = True
        brain["goal_at"] = -1e9          # choose again next tick
        brain["progress_at"] = now
    elif since > REPLAN_STUCK and not brain.get("stuck_replan"):
        brain["stuck_replan"] = True
        if goal:
            plan(bot, m, g, goal[1])

    path = brain.get("path") or []
    while path and close(x, y, z, g.at[path[0]]) and path[0] not in g.pad_nodes:
        reached(brain, now)
        brain["stuck_replan"] = False
    # Hold ground and dodge when close enough to a target worth fighting.
    if engaged and target is not None and goal and goal[0] == "enemy":
        if math.dist((x, y, z), (target.x, target.y, target.z)) < KEEP.get(bot.w, 8.0):
            return strafe(bot, game, m, target, now), False
    if path:
        node = g.at[path[0]]
        wx, wz = node[0] - x, node[2] - z
        n = math.hypot(wx, wz)
        if n < 1e-6:
            return None, False
        wx, wz = wx / n, wz / n
        jump = False
        if brain["via"][0] == "jump" and not ground_at(m, x + wx * JUMP_PROBE, y, z + wz * JUMP_PROBE):
            jump = True
            brain["jumped"] = True
        return (wx, wz), jump
    # Path done: walk the last bit to the goal's own point.
    if goal:
        px, py, pz = goal[2]
        wx, wz = px - x, pz - z
        n = math.hypot(wx, wz)
        if n < 0.4 or abs(py - y) > 1.5:
            if n < 0.4 and not brain.get("done"):
                brain["node_at"] = now
            brain["done"] = True
            if goal[0] == "order":
                return None, False
            if engaged and target is not None:
                return strafe(bot, game, m, target, now), False
            return None, False
        wx, wz = wx / n, wz / n
        if safe_step(m, x, y, z, wx, wz) or n < 0.6:
            return (wx, wz), False
        brain["done"] = True
    return None, False


def close(x, y, z, node) -> bool:
    return math.hypot(node[0] - x, node[2] - z) < ARRIVE and abs(node[1] - y) < 1.0


def strafe(bot, game, m, target, now: float):
    """Side-step across the line to the target, changing side now and then, never off an edge."""
    brain = bot.brain
    if now >= brain.get("strafe_at", 0.0):
        brain["strafe"] = game.rng.choice((-1, 1))
        brain["strafe_at"] = now + 0.4 + game.rng.random() * 0.8
    side = brain.get("strafe", 1)
    tx, tz = target.x - bot.x, target.z - bot.z
    n = math.hypot(tx, tz) or 1.0
    tx, tz = tx / n, tz / n
    for sgn in (side, -side):
        wx, wz = -tz * sgn, tx * sgn
        if safe_step(m, bot.x, bot.y, bot.z, wx, wz):
            brain["strafe"] = sgn
            return (wx, wz)
    return None


# --- Shooting -----------------------------------------------------------------------------------

def pick_weapon(bot, dist: float) -> int | None:
    has = lambda w: w in bot.weapons and bot.ammo.get(w, 0) > 0  # noqa: E731
    if dist > BEAM_RANGE and has(rules.BEAM):
        return rules.BEAM
    if dist >= LAUNCHER_MIN and has(rules.LAUNCHER):
        return rules.LAUNCHER
    if dist <= rules.WEAPONS[rules.BLASTER]["range"]:
        return rules.BLASTER
    if has(rules.BEAM):
        return rules.BEAM
    return rules.LAUNCHER if has(rules.LAUNCHER) else None


def aim_and_fire(bot, game, m, target, now: float) -> bool:
    """Turn toward the target and fire when ready. Returns True if the bot is aiming at it."""
    brain = bot.brain
    if target is None or now - brain["seen"].get(target.id, now) < REACTION:
        return False
    eye = bot.eye
    chest = (target.x, target.y + 1.0, target.z)
    dist = math.dist(eye, chest)
    w = pick_weapon(bot, dist)
    if w is None:
        return False
    if w != bot.w:
        game.switch_weapon(bot, w, now)
    track = brain["track"].get(target.id)
    vx, vy, vz = track[4:] if track else (0.0, 0.0, 0.0)
    # Hands follow the eyes a little late: aim where the target was AIM_LAG ago, plus the
    # Launcher's lead for the shell's flight.
    ahead = -AIM_LAG
    if bot.w == rules.LAUNCHER:
        ahead += dist / rules.WEAPONS[rules.LAUNCHER]["speed"] * LEAD
    under = m.surface_under(target.x, target.y, target.z, above=0.05)
    grounded = under is not None and target.y - under.max[1] < 0.15
    px, pz = target.x + vx * ahead, target.z + vz * ahead
    py = target.y + (0.0 if grounded else vy * ahead)
    point = (px, py + 1.0, pz)
    if bot.w == rules.LAUNCHER and grounded and m.segment_hit(eye, (px, py + 0.2, pz)) is None:
        point = (px, py + 0.2, pz)
    if m.segment_hit(eye, point) is not None:
        point = chest
    clear = m.segment_hit(eye, point) is None
    # Aim error: up to AIM_ERROR degrees, shrinking the longer the target has been in view.
    held = now - brain["seen"][target.id]
    err = math.radians(max(AIM_FLOOR, AIM_ERROR * math.exp(-max(0.0, held - REACTION) / AIM_SETTLE)))
    if now >= brain.get("err_at", 0.0):
        a = game.rng.random() * 2 * math.pi
        brain["err_dir"] = (math.cos(a), math.sin(a))
        brain["err_at"] = now + AIM_WANDER
    ex, ey = brain["err_dir"]
    yaw, pitch = look(unit(tuple(point[i] - eye[i] for i in range(3))))
    bot.yaw = yaw + ex * err / max(0.2, math.cos(pitch))
    bot.pitch = max(-1.5, min(1.5, pitch + ey * err))
    if not clear or now < bot.ready:
        return True
    spec = rules.WEAPONS[bot.w]
    d = rules.aim_from(bot.yaw, bot.pitch)
    if bot.w == rules.BLASTER:
        d = scatter(d, math.radians(spec["spread"]), game.rng)
    if not spec["hitscan"]:
        # Never fire a shell into something close enough to hurt the shooter.
        stop = m.segment_hit(eye, tuple(eye[i] + d[i] * 6 for i in range(3)))
        if stop is not None or dist < LAUNCHER_MIN:
            return True
        game.fire(bot, bot.w, eye, d, None, now)
        return True
    hit = game.ray_target(bot, eye, d, spec["range"])
    game.fire(bot, bot.w, eye, d, hit.id if hit else None, now)
    return True


# --- Each tick ----------------------------------------------------------------------------------

def think(bot, game, map, dt: float) -> dict:
    """One tick of a bot's play: look, choose a goal, steer along the path, aim and fire."""
    m = map
    g = graph(m)
    now = game.now
    brain = bot.brain
    target = sight(bot, game, m, now)
    if now - brain.get("goal_at", -1e9) >= GOAL_EVERY or brain.get("done"):
        goal = choose_goal(bot, game, m, g, target, now)
        old = brain.get("goal")
        if old is None or old[1] != goal[1] or old[0] != goal[0]:
            brain["done"] = False
        brain["goal"] = goal
        brain["goal_at"] = now
    aiming = aim_and_fire(bot, game, m, target, now)
    wish, jump = move(bot, game, m, g, target, aiming, now, dt)
    if not aiming:
        if wish is not None:
            bot.yaw = math.atan2(-wish[0], -wish[1])
        bot.pitch = 0.0
        if armed(bot) and bot.w == rules.BLASTER:
            game.switch_weapon(bot, rules.LAUNCHER if bot.ammo.get(rules.LAUNCHER, 0) > 0 else rules.BEAM, now)
    if wish is None:
        return {"forward": 0.0, "right": 0.0, "jump": jump}
    wx, wz = wish
    sy, cy = math.sin(bot.yaw), math.cos(bot.yaw)
    return {"forward": -sy * wx - cy * wz, "right": cy * wx - sy * wz, "jump": jump}
