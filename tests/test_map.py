"""Checks on app/shared/map.json (Driftyard), as listed in specs/map.md under Tests."""

import math
from collections import deque

from arena_server.mapdata import MAP, PLAYER_HALF

ITEM_TYPES = {"health", "bighealth", "shard", "armor", "launcher", "beam", "shells", "charges"}
HOWS = {"walk", "jump", "pad"}


def standing_on(at):
    """The solid whose top the point stands on (feet within 0.3 m above it, inside its footprint), or None."""
    x, y, z = at
    s = MAP.surface_under(x, y, z, above=0.0)
    if s is not None and y - s.max[1] <= 0.3:
        return s
    return None


def test_shape():
    assert MAP.name == "Driftyard"
    for k in ("gravity", "run", "ground_accel", "friction", "air_accel", "air_cap", "jump", "step", "kill_y"):
        assert k in MAP.physics
    assert 8 <= len(MAP.spawns) <= 10
    assert {i["type"] for i in MAP.items} == ITEM_TYPES
    for b in MAP.boxes:
        assert all(b.min[i] < b.max[i] for i in range(3)), b.name
    for p in MAP.pads:
        assert abs(p.max[1] - p.min[1] - 0.3) < 1e-9
        assert any(b.max[1] == p.min[1] for b in MAP.boxes), "pad must sit on a platform's top"


def test_everything_stands_on_something():
    for kind, points in (("spawn", [s["at"] for s in MAP.spawns]), ("item", [i["at"] for i in MAP.items]),
                         ("node", [n["at"] for n in MAP.nodes])):
        for n, at in enumerate(points):
            assert standing_on(at) is not None, f"{kind} {n} at {at} stands on nothing"
            if kind != "node":
                assert standing_on(at) not in MAP.pads, f"{kind} {n} at {at} is on a pad"
            assert not MAP.player_overlaps(*at), f"{kind} {n} at {at} is inside something"


def pad_flight(pad, dt=0.002):
    """Fly from the pad's centre with no steering. Returns (time, position, solid hit) at the first contact."""
    x = (pad.min[0] + pad.max[0]) / 2
    y = pad.max[1]
    z = (pad.min[2] + pad.max[2]) / 2
    vx, vy, vz = pad.launch
    g = MAP.physics["gravity"]
    t = 0.0
    while t < 10:
        t += dt
        px, py, pz = x + vx * t, y + vy * t - 0.5 * g * t * t, z + vz * t
        for s in MAP.solids:
            if s is not pad and _overlap(px, py, pz, s):
                return t, (px, py, pz, vy - g * t), s
    return None


def _overlap(x, y, z, s):
    return (x - PLAYER_HALF < s.max[0] and x + PLAYER_HALF > s.min[0] and y < s.max[1] and y + 1.8 > s.min[1]
            and z - PLAYER_HALF < s.max[2] and z + PLAYER_HALF > s.min[2])


def test_pad_flights_land_on_target():
    for n, pad in enumerate(MAP.pads):
        target = standing_on(pad.to)
        assert target is not None and target not in MAP.pads, f"pad {n}: `to` is not on a platform"
        source = standing_on([(pad.min[0] + pad.max[0]) / 2, pad.min[1], (pad.min[2] + pad.max[2]) / 2])
        assert source is not target, f"pad {n} goes nowhere"
        flight = pad_flight(pad)
        assert flight is not None, f"pad {n} never lands"
        t, (x, y, z, vy), hit = flight
        assert hit is target, f"pad {n} hits {getattr(hit, 'name', 'a pad')} first"
        assert vy < 0 and target.max[1] - y < 0.1, f"pad {n} hits the side of its target, not the top"
        assert target.min[0] + 1 <= x <= target.max[0] - 1 and target.min[2] + 1 <= z <= target.max[2] - 1, \
            f"pad {n} lands at {x:.2f}, {z:.2f}, less than 1 m inside {target.name}"
        assert math.dist((x, z), (pad.to[0], pad.to[2])) < 1.5, f"pad {n} lands far from its `to`"


def running_jump_reach(rise):
    """Horizontal distance a running jump covers while rising by `rise` (negative: dropping), or None."""
    p = MAP.physics
    disc = p["jump"] ** 2 - 2 * p["gravity"] * rise
    if disc < 0:
        return None
    t = (p["jump"] + math.sqrt(disc)) / p["gravity"]
    return p["run"] * t


def test_pads_are_the_only_way():
    """No running jump crosses from a pad's platform to its target platform."""
    for n, pad in enumerate(MAP.pads):
        source = standing_on([(pad.min[0] + pad.max[0]) / 2, pad.min[1], (pad.min[2] + pad.max[2]) / 2])
        target = standing_on(pad.to)
        reach = running_jump_reach(target.max[1] - source.max[1])
        if reach is None:
            continue
        gx = max(0.0, target.min[0] - source.max[0], source.min[0] - target.max[0])
        gz = max(0.0, target.min[2] - source.max[2], source.min[2] - target.max[2])
        gap = math.hypot(gx, gz)
        if gap == 0 and target.max[1] < source.max[1]:
            continue  # the target is straight below (the perch over the main deck): dropping is meant to work
        assert gap > 6, f"pad {n}: gap only {gap:.1f} m"
        assert gap > reach + 2 * PLAYER_HALF, f"pad {n}: a running jump of {reach:.1f} m crosses the {gap:.1f} m gap"


def test_edges():
    for e in MAP.edges:
        assert e["how"] in HOWS
        assert 0 <= e["from"] < len(MAP.nodes) and 0 <= e["to"] < len(MAP.nodes)
        a, b = MAP.nodes[e["from"]]["at"], MAP.nodes[e["to"]]["at"]
        if e["how"] == "jump":
            reach = running_jump_reach(b[1] - a[1])
            assert reach is not None and math.dist((a[0], a[2]), (b[0], b[2])) <= reach, f"jump edge {e} too far"
        if e["how"] == "pad":
            pads = [p for p in MAP.pads if p.min[0] <= a[0] <= p.max[0] and p.min[2] <= a[2] <= p.max[2]
                    and abs(a[1] - p.max[1]) < 0.01]
            assert pads, f"pad edge {e} does not start on a pad"
            assert standing_on(b) is standing_on(pads[0].to), f"pad edge {e} ends off the pad's target"


def test_every_platform_has_nodes():
    on = {id(standing_on(n["at"])) for n in MAP.nodes}
    for b in MAP.boxes:
        assert id(b) in on, f"{b.name} has no waypoint"


def test_graph_connected():
    """Every node can reach every other node, following edges in their direction."""
    n = len(MAP.nodes)
    fwd = [[] for _ in range(n)]
    back = [[] for _ in range(n)]
    for e in MAP.edges:
        fwd[e["from"]].append(e["to"])
        back[e["to"]].append(e["from"])
    for links in (fwd, back):
        seen = {0}
        todo = deque([0])
        while todo:
            for j in links[todo.popleft()]:
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
        assert len(seen) == n, f"nodes not reached: {sorted(set(range(n)) - seen)}"
