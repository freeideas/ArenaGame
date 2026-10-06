"""Tests for the movement rules in server/arena_server/motion.py."""

import math

import pytest

from arena_server.mapdata import MAP, MapData
from arena_server.motion import new_state, step

DT = 1 / 60
EAST = -math.pi / 2  # yaw that looks toward +x


def test_map(extra_boxes=()):
    """A flat floor 40 x 40 m with its top at y = 0, plus any extra boxes, with Driftyard's physics."""
    boxes = [{"min": [-20, -1, -20], "max": [20, 0, 20], "name": "floor"}, *extra_boxes]
    return MapData({"name": "test", "version": 1, "physics": MAP.physics, "boxes": boxes, "pads": [],
                    "spawns": [], "items": [], "waypoints": {"nodes": [], "edges": []}})


test_map.__test__ = False  # a helper, not a test


def run(s, inp, seconds, m, dt=DT):
    for _ in range(round(seconds / dt)):
        s = step(s, inp, dt, m)
    return s


def settle(x, y, z, m):
    return run(new_state(x, y, z), {}, 0.5, m)


def test_settles_on_ground():
    s = settle(0, 0.5, 0, test_map())
    assert s["ground"] and s["y"] == 0 and s["vy"] == 0


def test_running_reaches_run_speed_and_stops():
    m = test_map()
    s = settle(-10, 0, 0, m)
    s = run(s, {"forward": 1, "yaw": EAST}, 0.5, m)
    assert s["vx"] == pytest.approx(MAP.physics["run"]) and abs(s["vz"]) < 1e-9
    assert s["x"] > -10 + 0.5 * 9 - 1 and s["y"] == 0 and s["ground"]
    s = run(s, {"yaw": EAST}, 0.21, m)
    assert s["vx"] == 0


def test_strafe_and_diagonal_are_not_faster():
    m = test_map()
    s = run(settle(0, 0, 0, m), {"forward": 1, "right": 1, "yaw": 0.3}, 1, m)
    assert math.hypot(s["vx"], s["vz"]) == pytest.approx(MAP.physics["run"])


def test_jump_height_and_landing():
    m = test_map()
    s = settle(0, 0, 0, m)
    s = step(s, {"jump": True}, DT, m)
    assert not s["ground"] and s["vy"] > 0
    top, t = 0.0, DT
    while not s["ground"]:
        s = step(s, {}, DT, m)
        top = max(top, s["y"])
        t += DT
    p = MAP.physics
    assert top == pytest.approx(p["jump"] ** 2 / (2 * p["gravity"]), abs=0.02)
    assert t == pytest.approx(2 * p["jump"] / p["gravity"], abs=2 * DT)
    assert s["y"] == 0


def test_no_jump_in_the_air_but_press_is_remembered():
    m = test_map()
    s = run(settle(0, 0, 0, m), {"jump": True}, DT, m)
    s = run(s, {}, 0.2, m)
    vy = s["vy"]
    s = step(s, {"jump": True}, DT, m)   # pressed in the air: no extra lift
    assert s["vy"] < vy
    while s["vy"] > -6:                 # come down until just before landing
        s = step(s, {}, DT, m)
    while not s["ground"] and s["y"] > 0.3:
        s = step(s, {}, DT, m)
    s = step(s, {"jump": True}, DT, m)  # pressed just before touching down
    for _ in range(10):
        s = step(s, {}, DT, m)
        if s["vy"] > 0:
            break
    assert s["vy"] > 0, "the remembered press should jump on landing"


def test_steps_up_low_ledge_but_not_high_one():
    low = {"min": [2, 0, -5], "max": [6, 0.45, 5], "name": "low"}
    m = test_map([low])
    s = run(settle(0, 0, 0, m), {"forward": 1, "yaw": EAST}, 0.6, m)
    assert s["x"] > 2.5 and s["y"] == pytest.approx(0.45) and s["ground"]

    high = {"min": [2, 0, -5], "max": [6, 0.7, 5], "name": "high"}
    m = test_map([high])
    s = run(settle(0, 0, 0, m), {"forward": 1, "yaw": EAST}, 0.6, m)
    assert s["x"] == pytest.approx(2 - 0.4) and s["y"] == 0


def test_wall_stops_player():
    wall = {"min": [3, 0, -5], "max": [4, 4, 5], "name": "wall"}
    m = test_map([wall])
    s = run(settle(0, 0, 0, m), {"forward": 1, "yaw": EAST}, 1, m)
    assert s["x"] == pytest.approx(3 - 0.4) and s["vx"] == 0
    s = run(s, {"forward": 1, "right": 1, "yaw": EAST}, 0.5, m)  # slides along it
    assert s["x"] == pytest.approx(3 - 0.4) and s["vz"] > 6


def test_ceiling_stops_jump():
    roof = {"min": [-5, 2.2, -5], "max": [5, 3, 5], "name": "roof"}
    m = test_map([roof])
    s = run(settle(0, 0, 0, m), {"jump": True}, DT, m)
    s = run(s, {}, 0.15, m)
    assert s["y"] <= 2.2 - 1.8 + 1e-9


def test_falls_off_edge_and_dies():
    m = test_map()
    s = run(settle(18, 0, 0, m), {"forward": 1, "yaw": EAST}, 0.5, m)
    assert not s["ground"] and s["y"] < 0
    for _ in range(600):
        s = step(s, {}, DT, m)
        if s["fell"]:
            break
    assert s["fell"] and s["y"] < MAP.physics["kill_y"]


@pytest.mark.parametrize("n", range(len(MAP.pads)))
def test_pad_launch_lands_where_the_map_says(n):
    pad = MAP.pads[n]
    s = new_state((pad.min[0] + pad.max[0]) / 2, pad.max[1], (pad.min[2] + pad.max[2]) / 2)
    s["ground"] = True
    s = step(s, {}, DT, MAP)
    assert s["launched"] and s["pad"] == n
    for _ in range(600):
        s = step(s, {}, DT, MAP)
        if s["ground"]:
            break
    assert s["ground"], "never landed"
    target = MAP.surface_under(*pad.to)
    assert MAP.surface_under(s["x"], s["y"], s["z"]) is target
    assert s["y"] == target.max[1]
    assert math.dist((s["x"], s["z"]), (pad.to[0], pad.to[2])) < 1.5


def test_pad_fires_once_per_touch():
    pad = {"min": [-1, 0, -1], "max": [1, 0.3, 1], "launch": [0, 1, 0], "to": [0, 0, 0]}
    m = MapData({**test_map().raw, "pads": [pad]})
    s = new_state(0, 0.3, 0)
    s["ground"] = True
    s = step(s, {}, DT, m)
    assert s["launched"]
    fired = 1
    for _ in range(120):  # a weak launch drops the player back on the pad: it must not fire again
        s = step(s, {}, DT, m)
        fired += s["launched"]
    assert fired == 1 and s["pad"] == 0 and s["ground"]
    s = run(s, {"forward": 1, "yaw": EAST}, 0.5, m)  # walk off, then back on: fires again
    assert s["pad"] == -1
    fired = 0
    for _ in range(60):
        s = step(s, {"forward": 1, "yaw": -EAST}, DT, m)
        fired += s["launched"]
    assert fired >= 1
