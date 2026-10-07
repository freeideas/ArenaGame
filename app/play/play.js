// The play page's main module: loads the map, moves your own player with motion.js every frame,
// reads the keys and mouse, fires (doing its own hit test for instant-hit weapons), talks to the
// server through net.js, draws through view.js and fills the HUD through hud.js.
// The rules are in ../../specs/game.md and the messages in ../../specs/protocol.md.
// Opened as play/?local it runs with no server: your own player on the map, for trying movement.

import { step, newState, PLAYER_HALF, PLAYER_HEIGHT } from "./motion.js";
import { createView } from "./view.js";
import { connect } from "./net.js";
import * as hud from "./hud.js";

const LOCAL = new URLSearchParams(location.search).has("local");
const EYE = 1.6;
const DELAY = 0.1;        // others and shells are drawn this many seconds in the past
const MAX_STEP = 0.05;    // longest single motion step; longer frames are split
const SEND_EVERY = 0.05;  // `at` 20 times a second
const SWITCH_TIME = 0.3;
const RESPAWN_WAIT = 2;
const PITCH_LIMIT = 89 * Math.PI / 180;
const LOOK_SPEED = 0.0022; // radians per pixel of mouse movement
const KEY_LOOK_YAW = 2.4;   // radians per second when an arrow key is held
const KEY_LOOK_PITCH = 1.6;
const WEAPON = {
  1: { every: 1 / 8, range: 60, spread: 2 * Math.PI / 180 },
  2: { every: 0.8, range: 200, spread: 0 },
  3: { every: 1.5, range: 200, spread: 0 },
};
const HOW_TEXT = { blaster: "Blaster", launcher: "Launcher", beam: "Beam" };

const map = await (await fetch("../shared/map.json")).json();
const canvas = document.getElementById("view");
const view = createView(canvas, map);
const solids = [...map.boxes, ...map.pads];
const clock = () => performance.now() / 1000;

// --- game state ----------------------------------------------------------------------------------

const me = { id: null, name: "", player: null };
let joined = false;   // in the arena (Play pressed and the server agreed)
let wantJoin = false; // Play pressed; send join as soon as the connection is ready
let alive = false;
let deadAt = 0;
let deathText = "";
let body = null;      // motion.js state of your own player
let yaw = 0, pitch = 0;
let hp = 100, armor = 0, weapons = [1], ammo = {}, w = 1;
let readyAt = 0;      // when the weapon may fire next (fire rate and switching)
let seq = 0, lastSent = 0;
/** @type {{t: number, players: any[], shells: any[]}[]} */
let states = [];
let latest = null;     // the last state message
let offset = null;     // local clock minus server clock, in seconds
let round = { phase: "play", ends: null, scores: [], limit: 20 };
let winner = "";
let localDeaths = 0;
const names = new Map();
const nameOf = (id) => (id === me.id ? me.name || "You" : names.get(id) || "someone");

// --- the connection ------------------------------------------------------------------------------

let net = null;
if (LOCAL) {
  me.id = "local";
  me.name = "You";
  hud.cover(true, me.name, true, "Local test mode: no server, nobody else here.");
} else {
  hud.cover(true, "", false, "Connecting...");
  net = connect({ message: receive, status: connection });
}
const send = (m) => net?.send(m);

function connection(s) {
  if (s.up) hud.net(null);
  else {
    hud.net(`Lost the connection. Trying again in ${s.wait} s...`);
    if (joined) wantJoin = true; // come back into the arena after reconnecting
    joined = false;
    alive = false;
    states = [];
  }
}

function receive(m) {
  const now = clock();
  switch (m.t) {
    case "hello":
      me.id = m.id;
      me.name = m.name;
      me.player = m.player ?? null;
      if (m.map_version != null && m.map_version !== map.version) hud.toast("The map has changed. Reload the page.");
      if (wantJoin) join();
      else hud.cover(true, me.name, !me.player, me.player ? "Your Endless Mind name." : "");
      break;
    case "spawn":
      joined = true;
      wantJoin = false;
      alive = true;
      body = newState(m.x, m.y, m.z);
      yaw = m.yaw ?? 0;
      pitch = 0;
      mine(m);
      readyAt = now;
      hud.cover(false);
      hud.death(false);
      break;
    case "you":
      mine(m);
      break;
    case "push":
      if (body) {
        body.vx += m.vx; body.vy += m.vy; body.vz += m.vz;
        if (m.vy > 0) body.ground = false;
      }
      break;
    case "snap":
      if (body) Object.assign(body, { x: m.x, y: m.y, z: m.z, vx: 0, vy: 0, vz: 0, pad: -1 });
      break;
    case "die":
      die(m.by, m.how);
      if (body && m.x != null) Object.assign(body, { x: m.x, y: m.y, z: m.z });
      break;
    case "state":
      takeState(m, now);
      break;
    case "round":
      if (m.phase === "over" && round.phase !== "over") {
        const top = [...(m.scores || [])].sort((a, b) => b.frags - a.frags || a.deaths - b.deaths)[0];
        winner = top ? (top.id === me.id ? "You" : top.name) : "";
      }
      if (m.phase !== "over") winner = "";
      round = { phase: m.phase, ends: m.ends ?? null, scores: m.scores || [], limit: m.limit ?? 20 };
      for (const p of round.scores) names.set(p.id, p.name);
      break;
    case "ping":
      send({ t: "pong", c: m.c });
      break;
    case "error":
      hud.toast(m.text || "Something went wrong.");
      break;
  }
}

/** Your own numbers from a spawn or you message. */
function mine(m) {
  if (m.hp != null) hp = m.hp;
  if (m.armor != null) armor = m.armor;
  if (m.weapons) weapons = m.weapons.map(Number);
  if (m.ammo) ammo = Object.fromEntries(Object.entries(m.ammo).map(([k, v]) => [Number(k), v]));
  if (m.w != null && m.w !== w) {
    w = m.w;
    readyAt = Math.max(readyAt, clock() + SWITCH_TIME);
  }
  hud.vitals(hp, armor);
  hud.arms(weapons, w, ammo);
}

function die(by, how) {
  alive = false;
  deadAt = clock();
  if (how === "void") deathText = by && by !== me.id ? `${nameOf(by)} knocked you into the void` : "You fell into the void";
  else if (how === "self" || by === me.id || (!by && how === "launcher")) deathText = "Your own shell got you";
  else deathText = by ? `${nameOf(by)} got you with the ${HOW_TEXT[how] || "weapon"}` : "You died";
  hud.hideBody();
}

function takeState(m, now) {
  const t = typeof m.now === "number" ? m.now : m.tick / 30;
  const sample = now - t;
  // The smallest gap seen is the one with the least network delay; let it creep up slowly so a
  // drifting clock cannot leave us far behind.
  offset = offset === null || sample < offset ? sample : offset + (sample - offset) * 0.002;
  const others = (m.players || []).filter((p) => p.id !== me.id);
  for (const p of m.players || []) names.set(p.id, p.name);
  states.push({ t, players: others, shells: m.shells || [] });
  while (states.length > 30) states.shift();
  latest = m;
  for (const e of m.events || []) {
    if (e.e === "frag") hud.feed(e, nameOf, me.id);
    else if (e.e === "shot") {
      if (e.by !== me.id) view.addShot([e.ox, e.oy, e.oz], [e.hx, e.hy, e.hz], e.w);
      else if (e.hit) hud.hitFlash();
    } else if (e.e === "boom") view.addBoom(e.x, e.y, e.z);
  }
  // If the server shows us dead without a die message (for example after reconnecting), follow it.
  const self = (m.players || []).find((p) => p.id === me.id);
  if (self && self.dead && alive) die(null, "");
}

const serverNow = () => (offset === null ? null : clock() - offset);

// --- others, shown DELAY seconds in the past ---------------------------------------------------

function lerpAngle(a, b, k) {
  let d = (b - a) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d < -Math.PI) d += 2 * Math.PI;
  return a + d * k;
}

/** Players and shells as they were DELAY seconds ago, sliding between the two states around then. */
function seen() {
  const sn = serverNow();
  if (!states.length || sn === null) return { players: [], shells: [] };
  const at = sn - DELAY;
  let i = states.length - 1;
  while (i > 0 && states[i - 1].t > at) i--;
  const b = states[i], a = states[i - 1] ?? b;
  const k = b.t === a.t ? 1 : Math.min(1, Math.max(0, (at - a.t) / (b.t - a.t)));
  const mix = (p, q) => p + (q - p) * k;
  const before = new Map(a.players.map((p) => [p.id, p]));
  const shellsBefore = new Map(a.shells.map((s) => [s.id, s]));
  return {
    players: b.players.map((p) => {
      const q = before.get(p.id);
      if (!q || q.dead !== p.dead) return p;
      return { ...p, x: mix(q.x, p.x), y: mix(q.y, p.y), z: mix(q.z, p.z), yaw: lerpAngle(q.yaw, p.yaw, k), pitch: mix(q.pitch, p.pitch) };
    }),
    // A shell new in b is drawn from b; one gone from b (exploded) is gone.
    shells: b.shells.map((s) => {
      const q = shellsBefore.get(s.id);
      return q ? { ...s, x: mix(q.x, s.x), y: mix(q.y, s.y), z: mix(q.z, s.z) } : s;
    }),
  };
}
let shown = { players: [], shells: [] }; // what was drawn this frame: the hit test uses it

// --- hit tests -----------------------------------------------------------------------------------

/** Distance along the ray (o, unit d) to the nearest map box, or Infinity. */
function rayBoxes(o, d) {
  let best = Infinity;
  for (const s of solids) {
    let t0 = 0, t1 = Infinity;
    let ok = true;
    for (let a = 0; a < 3 && ok; a++) {
      if (Math.abs(d[a]) < 1e-12) {
        if (o[a] < s.min[a] || o[a] > s.max[a]) ok = false;
      } else {
        let ta = (s.min[a] - o[a]) / d[a], tb = (s.max[a] - o[a]) / d[a];
        if (ta > tb) [ta, tb] = [tb, ta];
        t0 = Math.max(t0, ta);
        t1 = Math.min(t1, tb);
        if (t0 > t1) ok = false;
      }
    }
    if (ok && t0 < best) best = t0;
  }
  return best;
}

/** Distance along the ray to a player's upright cylinder (feet at p), or Infinity. */
function rayCylinder(o, d, p) {
  const r = PLAYER_HALF, bottom = p.y, top = p.y + PLAYER_HEIGHT;
  let best = Infinity;
  const ox = o[0] - p.x, oz = o[2] - p.z;
  const A = d[0] * d[0] + d[2] * d[2];
  if (A > 1e-12) {
    const B = 2 * (ox * d[0] + oz * d[2]);
    const C = ox * ox + oz * oz - r * r;
    const disc = B * B - 4 * A * C;
    if (disc >= 0) {
      const t = (-B - Math.sqrt(disc)) / (2 * A);
      const y = o[1] + d[1] * t;
      if (t >= 0 && y >= bottom && y <= top) best = t;
    }
  }
  if (Math.abs(d[1]) > 1e-12) {
    for (const cap of [bottom, top]) {
      const t = (cap - o[1]) / d[1];
      if (t < 0 || t >= best) continue;
      const x = ox + d[0] * t, z = oz + d[2] * t;
      if (x * x + z * z <= r * r) best = t;
    }
  }
  return best;
}

/** What an instant-hit shot strikes: {id, t} for the nearest player before any box, else {id: null, t}. */
function traceShot(o, d, range) {
  const wall = Math.min(range, rayBoxes(o, d));
  let hit = { id: null, t: wall };
  for (const p of shown.players) {
    if (p.dead) continue;
    const t = rayCylinder(o, d, p);
    if (t < hit.t) hit = { id: p.id, t };
  }
  return hit;
}

// --- firing and weapons --------------------------------------------------------------------------

function aim() {
  const c = Math.cos(pitch);
  return [-Math.sin(yaw) * c, Math.sin(pitch), -Math.cos(yaw) * c];
}

/** Turn d by a random angle up to `spread` radians. */
function scatter(d, spread) {
  if (!spread) return d;
  const helper = Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (v) => { const l = Math.hypot(...v); return v.map((x) => x / l); };
  const u = norm(cross(d, helper)), v = cross(d, u);
  const angle = spread * Math.sqrt(Math.random()), turn = Math.random() * 2 * Math.PI;
  const s = Math.sin(angle), c = Math.cos(angle);
  return norm(d.map((x, i) => x * c + (u[i] * Math.cos(turn) + v[i] * Math.sin(turn)) * s));
}

/** Fire the held weapon if it is ready; true if it fired. */
function fire() {
  const now = clock();
  if (!alive || !body || round.phase === "over" || now < readyAt) return false;
  if (w !== 1 && !((ammo[w] ?? 0) > 0)) {
    hud.toast(`The ${hud.WEAPON_NAMES[w]} is empty.`);
    readyAt = now + 0.5;
    return false;
  }
  const spec = WEAPON[w];
  readyAt = now + spec.every;
  const o = [body.x, body.y + EYE, body.z];
  const d = scatter(aim(), spec.spread);
  view.kick();
  let hit = null;
  if (w === 2) {
    if (LOCAL) { // no server to fly the shell: burst where it would land
      const t = rayBoxes(o, d);
      if (t < spec.range) view.addBoom(o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t);
    }
  } else {
    const result = traceShot(o, d, spec.range);
    hit = result.id;
    // Start the drawn line at the tip of the weapon shown below and right of the eyes.
    const f = aim(), right = [Math.cos(yaw), 0, -Math.sin(yaw)];
    const tip = o.map((x, i) => x + f[i] * 0.85 + right[i] * 0.2 - (i === 1 ? 0.17 : 0));
    view.addShot(tip, o.map((x, i) => x + d[i] * result.t), w);
    if (hit) hud.hitFlash();
  }
  if (w !== 1) {
    ammo[w] = (ammo[w] ?? 1) - 1;
    hud.arms(weapons, w, ammo);
  }
  const r3 = (x) => Math.round(x * 1000) / 1000;
  send({ t: "fire", w, ox: r3(o[0]), oy: r3(o[1]), oz: r3(o[2]), dx: d[0], dy: d[1], dz: d[2], hit });
  return true;
}

function choose(n) {
  if (!alive || n === w || !weapons.includes(n)) return;
  w = n;
  readyAt = Math.max(readyAt, clock() + SWITCH_TIME);
  send({ t: "weapon", w });
  hud.arms(weapons, w, ammo);
}

// --- joining, respawning, local mode -------------------------------------------------------------

function join() {
  if (LOCAL) {
    localSpawn();
    return;
  }
  wantJoin = true;
  if (me.id && send({ t: "join" })) hud.cover(true, me.name, !me.player, "Joining...");
}

function localSpawn() {
  const s = map.spawns[Math.floor(Math.random() * map.spawns.length)];
  receive({ t: "spawn", x: s.at[0], y: s.at[1], z: s.at[2], yaw: s.yaw, hp: 100, armor: 0, weapons: [1, 2, 3], ammo: { 2: 25, 3: 20 }, w: 1 });
}

function respawn() {
  if (alive || !joined || clock() - deadAt < RESPAWN_WAIT) return;
  if (LOCAL) localSpawn();
  else send({ t: "respawn" });
}

hud.onPlay((name) => {
  if (name && name.length <= 24 && name !== me.name && !me.player) {
    me.name = name;
    send({ t: "name", name });
  }
  canvas.requestPointerLock?.()?.catch?.(() => {});
  join();
});

// --- keys and mouse ------------------------------------------------------------------------------

const keys = new Set();
let tabHeld = false;
let mouseDown = false, pressPending = false;
const locked = () => document.pointerLockElement === canvas;
const typing = () => document.activeElement?.tagName === "INPUT";

addEventListener("keydown", (e) => {
  if (typing()) return;
  if (e.code === "Tab") { e.preventDefault(); tabHeld = true; return; }
  if (["Space", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) e.preventDefault();
  if (e.code === "Enter" && !keys.has("Enter")) {
    if (joined && !alive) { respawn(); return; }
    pressPending = true;
  }
  keys.add(e.code);
  const n = { Digit1: 1, Digit2: 2, Digit3: 3, Numpad1: 1, Numpad2: 2, Numpad3: 3 }[e.code];
  if (n) choose(n);
});
addEventListener("keyup", (e) => {
  if (e.code === "Tab") tabHeld = false;
  if (e.code === "Enter" && !mouseDown) pressPending = false;
  keys.delete(e.code);
});
addEventListener("blur", () => { keys.clear(); tabHeld = false; mouseDown = false; });

canvas.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  if (joined && !alive) { respawn(); return; }
  if (!locked()) { canvas.requestPointerLock?.()?.catch?.(() => {}); return; }
  mouseDown = true;
  pressPending = true;
});
addEventListener("mouseup", (e) => { if (e.button === 0) { mouseDown = false; pressPending = false; } });
addEventListener("mousemove", (e) => {
  if (!locked()) return;
  yaw -= e.movementX * LOOK_SPEED;
  pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch - e.movementY * LOOK_SPEED));
});
addEventListener("wheel", (e) => {
  if (!alive || !e.deltaY) return;
  const held = [...weapons].sort();
  const i = held.indexOf(w);
  choose(held[(i + (e.deltaY > 0 ? 1 : -1) + held.length) % held.length]);
}, { passive: true });
document.addEventListener("pointerlockchange", () => { if (!locked()) { mouseDown = false; pressPending = false; } });

function input() {
  const k = (...codes) => codes.some((c) => keys.has(c));
  return {
    forward: (k("KeyW") ? 1 : 0) - (k("KeyS") ? 1 : 0),
    right: (k("KeyD") ? 1 : 0) - (k("KeyA") ? 1 : 0),
    jump: k("Space"),
    yaw,
  };
}

// --- every frame ---------------------------------------------------------------------------------

let last = performance.now();
let hudAt = 0;
function frame(t) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.5, Math.max(0, (t - last) / 1000));
  last = t;
  const now = clock();
  const over = round.phase === "over";

  // Arrow keys look, like a mouse that moves at a steady rate.
  if (!typing()) {
    const kx = (keys.has("ArrowRight") ? 1 : 0) - (keys.has("ArrowLeft") ? 1 : 0);
    const ky = (keys.has("ArrowUp") ? 1 : 0) - (keys.has("ArrowDown") ? 1 : 0);
    yaw -= kx * KEY_LOOK_YAW * dt;
    pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch + ky * KEY_LOOK_PITCH * dt));
  }

  if (alive && body && !over) {
    const steps = Math.ceil(dt / MAX_STEP) || 1;
    const move = input();
    for (let i = 0; i < steps; i++) {
      body = step(body, move, dt / steps, map);
      if (body.fell && LOCAL) { localDeaths++; die(null, "void"); break; }
    }
    if ((mouseDown || keys.has("Enter")) && (w === 1 || pressPending) && fire()) pressPending = false;
  }

  if (alive && body && now - lastSent >= SEND_EVERY) {
    lastSent = now;
    const r3 = (x) => Math.round(x * 1000) / 1000;
    send({ t: "at", x: r3(body.x), y: r3(body.y), z: r3(body.z), yaw: r3(yaw), pitch: r3(pitch),
      vx: r3(body.vx), vy: r3(body.vy), vz: r3(body.vz), ground: body.ground, seq: ++seq });
  }

  shown = seen();
  let eye;
  if (body && joined) eye = { x: body.x, y: body.y + EYE, z: body.z, yaw, pitch };
  else {
    // Not in the arena yet: circle slowly around the map, looking at its middle.
    const a = now * 0.05, x = Math.sin(a) * 48, z = Math.cos(a) * 48, y = 22;
    eye = { x, y, z, yaw: Math.atan2(x, z), pitch: -Math.atan2(y - 4, 48) };
  }
  view.draw({ eye, players: shown.players, shells: shown.shells, items: latest?.items ?? null, weapon: alive ? w : null });

  if (now - hudAt > 0.1) {
    hudAt = now;
    const sn = serverNow();
    const players = LOCAL ? [{ id: me.id, name: me.name, bot: false, frags: 0, deaths: localDeaths, ping: 0 }]
      : latest?.players ?? round.scores;
    hud.roundLine(round.ends != null && sn != null ? round.ends - sn : null, round.phase, joined ? players : [], me.id);
    hud.board(tabHeld || over, players, me.id, over ? winner : "",
      over ? "The next round starts soon." : `First to ${round.limit} frags.`);
    hud.death(joined && !alive, deathText, now - deadAt >= RESPAWN_WAIT);
    hud.lockHint(joined && alive && !locked() && !over);
  }
}
requestAnimationFrame(frame);

// A handle for trying things from the console or a browser test. Moving yourself with it while
// connected is pointless: the server checks every move and snaps you back.
{
  window.arena = {
    get body() { return body; },
    get alive() { return alive; },
    get view() { return { yaw, pitch }; },
    get others() { return shown.players; },
    place(x, y, z, faceYaw = yaw) { body = newState(x, y, z); yaw = faceYaw; },
    look(newYaw, newPitch = 0) { yaw = newYaw; pitch = newPitch; },
    fire,
    receive,
    trace: () => traceShot([body.x, body.y + EYE, body.z], aim(), 200),
  };
}
