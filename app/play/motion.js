// Movement rules for one player, in JavaScript: the browser moves its own player with this.
//
// server/arena_server/motion.py is the same code in Python (bots, checking moves).
// Keep the two in step line by line: tests/test_motion_cross.py runs both and
// compares positions. The rules are in specs/game.md under Movement; every number
// comes from the map's "physics" block (map is the parsed app/shared/map.json).
//
// state: {x, y, z, vx, vy, vz, ground, pad, buffer}
//   ground: standing on something; pad: index of the pad being stood on, or -1;
//   buffer: seconds left on a remembered jump press.
// input: {forward, right, jump, yaw}
//   forward and right are -1..1 (back and left are negative); jump is true while pressed.
// step() returns a new state with two extra keys: launched (a pad fired this step)
// and fell (below kill_y).

export const PLAYER_HALF = 0.4;
export const PLAYER_HEIGHT = 1.8;
const SKIN = 1e-6;      // touching is not overlapping; this absorbs rounding
const PAD_REACH = 0.1;  // feet within this far above a pad's top count as standing on it

// A player standing still at (x, y, z).
export function newState(x, y, z) {
  return { x, y, z, vx: 0, vy: 0, vz: 0, ground: false, pad: -1, buffer: 0 };
}

// Boxes then pads, in file order (the same order as the Python side). Cached per map.
const solidsCache = new WeakMap();
function solidsOf(map) {
  let s = solidsCache.get(map);
  if (!s) {
    s = [...map.boxes, ...map.pads];
    solidsCache.set(map, s);
  }
  return s;
}

function clamp(v) {
  return Math.max(-1, Math.min(1, v));
}

function overlaps(x, y, z, s) {
  return x - PLAYER_HALF < s.max[0] - SKIN && x + PLAYER_HALF > s.min[0] + SKIN
    && y < s.max[1] - SKIN && y + PLAYER_HEIGHT > s.min[1] + SKIN
    && z - PLAYER_HALF < s.max[2] - SKIN && z + PLAYER_HALF > s.min[2] + SKIN;
}

function hits(x, y, z, solids) {
  return solids.filter((s) => overlaps(x, y, z, s));
}

// True if a player with feet at (x, y, z) overlaps any box or pad.
export function playerOverlaps(x, y, z, map) {
  return solidsOf(map).some((s) => overlaps(x, y, z, s));
}

// Advance one player by dt seconds. Pure: the given state is not changed.
export function step(state, input, dt, map) {
  const p = map.physics;
  const solids = solidsOf(map);
  let { x, y, z, vx, vy, vz, ground } = state;
  let buffer = input.jump ? p.jump_buffer : Math.max(0, state.buffer - dt);

  // Wished direction on the ground plane. Yaw 0 looks toward -z; positive turns left.
  const f = clamp(input.forward ?? 0);
  const r = clamp(input.right ?? 0);
  const sy = Math.sin(input.yaw ?? 0);
  const cy = Math.cos(input.yaw ?? 0);
  let wx = -sy * f + cy * r;
  let wz = -cy * f - sy * r;
  let wlen = Math.sqrt(wx * wx + wz * wz);
  if (wlen > 1) {
    wx = wx / wlen;
    wz = wz / wlen;
    wlen = 1;
  }

  if (ground) {
    // Move the horizontal velocity straight toward the wished velocity:
    // quickly when keys are held, by friction when they are not.
    const tx = wx * p.run;
    const tz = wz * p.run;
    const rate = (wlen > 0 ? p.ground_accel : p.friction * p.run) * dt;
    const dx = tx - vx;
    const dz = tz - vz;
    const d = Math.sqrt(dx * dx + dz * dz);
    if (d <= rate) {
      vx = tx;
      vz = tz;
    } else {
      vx = vx + dx / d * rate;
      vz = vz + dz / d * rate;
    }
    if (buffer > 0) {
      vy = p.jump;
      ground = false;
      buffer = 0;
    }
  } else if (wlen > 0) {
    // In the air: accelerate along the wished direction, but never past
    // air_cap measured along that direction (other speed is kept).
    const ux = wx / wlen;
    const uz = wz / wlen;
    const add = p.air_cap * wlen - (vx * ux + vz * uz);
    if (add > 0) {
      const a = Math.min(p.air_accel * dt, add);
      vx = vx + ux * a;
      vz = vz + uz * a;
    }
  }

  // Gravity, integrated exactly over the step so the arc does not depend on dt.
  const g = p.gravity;
  const dy = vy * dt - 0.5 * g * dt * dt;
  vy = vy - g * dt;

  // x axis, with step-up onto low things while on the ground.
  let nx = x + vx * dt;
  let hit = hits(nx, y, z, solids);
  if (hit.length) {
    const top = Math.max(...hit.map((s) => s.max[1]));
    if (ground && top - y <= p.step && !hits(nx, top, z, solids).length) {
      y = top;
    } else {
      for (const s of hit) {
        nx = vx > 0 ? Math.min(nx, s.min[0] - PLAYER_HALF) : Math.max(nx, s.max[0] + PLAYER_HALF);
      }
      if (hits(nx, y, z, solids).length) nx = x;
      vx = 0;
    }
  }
  x = nx;

  // y axis: land on tops, bump heads on undersides.
  let ny = y + dy;
  hit = hits(x, ny, z, solids);
  if (hit.length) {
    if (dy <= 0) {
      ny = Math.max(...hit.map((s) => s.max[1]));
      ground = true;
    } else {
      ny = Math.min(...hit.map((s) => s.min[1])) - PLAYER_HEIGHT;
      ground = false;
    }
    if (hits(x, ny, z, solids).length) ny = y;
    vy = 0;
  } else {
    ground = false;
  }
  y = ny;

  // z axis, same as x.
  let nz = z + vz * dt;
  hit = hits(x, y, nz, solids);
  if (hit.length) {
    const top = Math.max(...hit.map((s) => s.max[1]));
    if (ground && top - y <= p.step && !hits(x, top, nz, solids).length) {
      y = top;
    } else {
      for (const s of hit) {
        nz = vz > 0 ? Math.min(nz, s.min[2] - PLAYER_HALF) : Math.max(nz, s.max[2] + PLAYER_HALF);
      }
      if (hits(x, y, nz, solids).length) nz = z;
      vz = 0;
    }
  }
  z = nz;

  // Launch pads fire once per touch: only when the player was not already on this pad.
  let onPad = -1;
  let launched = false;
  for (let i = 0; i < map.pads.length; i++) {
    const pad = map.pads[i];
    if (pad.min[0] <= x && x <= pad.max[0] && pad.min[2] <= z && z <= pad.max[2]
        && pad.max[1] - SKIN <= y && y <= pad.max[1] + PAD_REACH) {
      onPad = i;
      if (state.pad !== i) {
        [vx, vy, vz] = pad.launch;
        ground = false;
        launched = true;
      }
      break;
    }
  }

  return { x, y, z, vx, vy, vz, ground, pad: onPad, buffer, launched, fell: y < p.kill_y };
}
