"""Movement rules for one player, in Python: used by the server for bots and to check moves.

app/play/motion.js is the same code in JavaScript for the browser. Keep the two in
step line by line: tests/test_motion_cross.py runs both and compares positions.
The rules are in specs/game.md under Movement; every number comes from the map's
"physics" block.

state: {x, y, z, vx, vy, vz, ground, pad, buffer}
  ground: standing on something; pad: index of the pad being stood on, or -1;
  buffer: seconds left on a remembered jump press.
input: {forward, right, jump, yaw}
  forward and right are -1..1 (back and left are negative); jump is True while pressed.
step() returns a new state with two extra keys: launched (a pad fired this step)
and fell (below kill_y).
"""

from __future__ import annotations

import math

from .mapdata import PLAYER_HALF, PLAYER_HEIGHT, SKIN, MapData, player_overlaps_solid

PAD_REACH = 0.1  # feet within this far above a pad's top count as standing on it


def new_state(x: float, y: float, z: float) -> dict:
    """A player standing still at (x, y, z)."""
    return {"x": x, "y": y, "z": z, "vx": 0.0, "vy": 0.0, "vz": 0.0, "ground": False, "pad": -1, "buffer": 0.0}


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _hits(x, y, z, solids) -> list:
    return [s for s in solids if player_overlaps_solid(x, y, z, s)]


def step(state: dict, inp: dict, dt: float, m: MapData) -> dict:
    """Advance one player by dt seconds. Pure: the given state is not changed."""
    p = m.physics
    solids = m.solids
    x, y, z = state["x"], state["y"], state["z"]
    vx, vy, vz = state["vx"], state["vy"], state["vz"]
    ground = state["ground"]
    buffer = p["jump_buffer"] if inp.get("jump") else max(0.0, state["buffer"] - dt)

    # Wished direction on the ground plane. Yaw 0 looks toward -z; positive turns left.
    f = _clamp(inp.get("forward", 0.0))
    r = _clamp(inp.get("right", 0.0))
    sy = math.sin(inp.get("yaw", 0.0))
    cy = math.cos(inp.get("yaw", 0.0))
    wx = -sy * f + cy * r
    wz = -cy * f - sy * r
    wlen = math.sqrt(wx * wx + wz * wz)
    if wlen > 1.0:
        wx = wx / wlen
        wz = wz / wlen
        wlen = 1.0

    if ground:
        # Move the horizontal velocity straight toward the wished velocity:
        # quickly when keys are held, by friction when they are not.
        tx = wx * p["run"]
        tz = wz * p["run"]
        rate = (p["ground_accel"] if wlen > 0.0 else p["friction"] * p["run"]) * dt
        dx = tx - vx
        dz = tz - vz
        d = math.sqrt(dx * dx + dz * dz)
        if d <= rate:
            vx = tx
            vz = tz
        else:
            vx = vx + dx / d * rate
            vz = vz + dz / d * rate
        if buffer > 0.0:
            vy = p["jump"]
            ground = False
            buffer = 0.0
    elif wlen > 0.0:
        # In the air: accelerate along the wished direction, but never past
        # air_cap measured along that direction (other speed is kept).
        ux = wx / wlen
        uz = wz / wlen
        add = p["air_cap"] * wlen - (vx * ux + vz * uz)
        if add > 0.0:
            a = min(p["air_accel"] * dt, add)
            vx = vx + ux * a
            vz = vz + uz * a

    # Gravity, integrated exactly over the step so the arc does not depend on dt.
    g = p["gravity"]
    dy = vy * dt - 0.5 * g * dt * dt
    vy = vy - g * dt

    # x axis, with step-up onto low things while on the ground.
    nx = x + vx * dt
    hit = _hits(nx, y, z, solids)
    if hit:
        top = max(s.max[1] for s in hit)
        if ground and top - y <= p["step"] and not _hits(nx, top, z, solids):
            y = top
        else:
            for s in hit:
                nx = min(nx, s.min[0] - PLAYER_HALF) if vx > 0.0 else max(nx, s.max[0] + PLAYER_HALF)
            if _hits(nx, y, z, solids):
                nx = x
            vx = 0.0
    x = nx

    # y axis: land on tops, bump heads on undersides.
    ny = y + dy
    hit = _hits(x, ny, z, solids)
    if hit:
        if dy <= 0.0:
            ny = max(s.max[1] for s in hit)
            ground = True
        else:
            ny = min(s.min[1] for s in hit) - PLAYER_HEIGHT
            ground = False
        if _hits(x, ny, z, solids):
            ny = y
        vy = 0.0
    else:
        ground = False
    y = ny

    # z axis, same as x.
    nz = z + vz * dt
    hit = _hits(x, y, nz, solids)
    if hit:
        top = max(s.max[1] for s in hit)
        if ground and top - y <= p["step"] and not _hits(x, top, nz, solids):
            y = top
        else:
            for s in hit:
                nz = min(nz, s.min[2] - PLAYER_HALF) if vz > 0.0 else max(nz, s.max[2] + PLAYER_HALF)
            if _hits(x, y, nz, solids):
                nz = z
            vz = 0.0
    z = nz

    # Launch pads fire once per touch: only when the player was not already on this pad.
    on_pad = -1
    launched = False
    for i, pad in enumerate(m.pads):
        if (pad.min[0] <= x <= pad.max[0] and pad.min[2] <= z <= pad.max[2]
                and pad.max[1] - SKIN <= y <= pad.max[1] + PAD_REACH):
            on_pad = i
            if state["pad"] != i:
                vx, vy, vz = pad.launch
                ground = False
                launched = True
            break

    return {"x": x, "y": y, "z": z, "vx": vx, "vy": vy, "vz": vz, "ground": ground, "pad": on_pad,
            "buffer": buffer, "launched": launched, "fell": y < p["kill_y"]}
