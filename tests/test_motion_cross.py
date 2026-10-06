"""The Python and JavaScript movement rules must agree: same inputs, same positions (within 1e-6)."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from arena_server.mapdata import MAP
from arena_server.motion import new_state, step

HERE = Path(__file__).resolve().parent
DENO = shutil.which("deno") or (str(Path.home() / ".local/bin/deno") if (Path.home() / ".local/bin/deno").exists() else None)


def scripted_inputs(n, seed):
    """A fixed, varied list of inputs: runs, turns, strafes and jumps, from a small number generator."""
    r = seed
    out = []
    inp = {"forward": 1, "right": 0, "jump": False, "yaw": 0.0}
    for i in range(n):
        if i % 20 == 0:
            r = (r * 1103515245 + 12345) % 2**31
            inp = {"forward": [1, 1, 1, 0, -1, 0.5][r % 6], "right": [0, 0, 1, -1, 0.3][(r >> 4) % 5],
                   "jump": (r >> 8) % 3 == 0, "yaw": ((r >> 12) % 628) / 100 - 3.14}
        out.append(dict(inp))
    return out


def scripts():
    # Run north from the main deck onto the north pad, fly to the island, then move about.
    north = [{"forward": 1, "yaw": 0.0}] * 120 + scripted_inputs(600, 7)
    # Wander the main deck at the server's tick rate, falling off somewhere maybe.
    deck = scripted_inputs(300, 99)
    # The east side deck: run onto the pillar pad.
    side = [{"forward": 1, "right": 0, "yaw": math.atan2(-(19 - 24), -(-2.5 - 2))}] * 60 + scripted_inputs(300, 3)
    # Run into the east pillar's wall from the side deck, slide along it, jump against it.
    wall = ([{"forward": 1, "yaw": -math.pi / 2}] * 60 + [{"forward": 1, "right": -0.5, "yaw": -math.pi / 2}] * 30
            + [{"forward": 1, "jump": True, "yaw": -math.pi / 2}] * 60)
    return [(1 / 60, new_state(0, 0, -3), north), (1 / 30, new_state(-6, 0.2, 4), deck), (1 / 60, new_state(24, -3, 2), side),
            (1 / 60, new_state(21, -3, 0), wall)]


@pytest.mark.skipif(DENO is None, reason="deno is not installed")
@pytest.mark.parametrize("which", range(4))
def test_python_and_javascript_agree(which, tmp_path):
    dt, start, inputs = scripts()[which]
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"dt": dt, "start": start, "inputs": inputs}))
    done = subprocess.run([DENO, "run", "--quiet", f"--allow-read={HERE.parent},{tmp_path}", str(HERE / "motion_helper.js"), str(path)],
                          capture_output=True, text=True, check=True, timeout=60)
    js = json.loads(done.stdout)
    s = start
    launches = 0
    for n, inp in enumerate(inputs):
        s = step(s, inp, dt, MAP)
        launches += s["launched"]
        for k in ("x", "y", "z", "vx", "vy", "vz"):
            assert abs(s[k] - js[n][k]) <= 1e-6, f"step {n}: {k} is {s[k]} in Python, {js[n][k]} in JavaScript"
        for k in ("ground", "pad", "launched", "fell"):
            assert s[k] == js[n][k], f"step {n}: {k} differs"
    if which in (0, 2):
        assert launches >= 1, "the script should use a pad"
