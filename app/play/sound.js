// Sound effects with the Web Audio API: the .ogg files in ../shared/sounds/ (see the README there),
// fetched once at load and decoded once audio is allowed. Browsers keep audio off until the person
// clicks or presses a key, so the AudioContext is made on the first such gesture (unlock()).
// A sound with `at` set is placed in the world with a PannerNode; the listener follows the camera
// (listen() every frame). M toggles mute, kept in localStorage under `arena-muted`.

const FILES = ["blaster", "blaster2", "launcher", "shell", "boom", "boom2", "beam", "hit", "pad", "pickup",
  "die", "land", "step0", "step1", "step2", "step3"];
const DIR = "../shared/sounds/";
const VOLUME = 0.5;
const MUTE_KEY = "arena-muted";

/** @type {AudioContext | null} */
let ctx = null;
let master = null;
/** @type {Map<string, AudioBuffer>} */
const buffers = new Map();
/** The raw bytes, fetched at once so decoding can start the moment audio is allowed. */
const raw = new Map(FILES.map((name) => [name, fetch(`${DIR}${name}.ogg`)
  .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.arrayBuffer(); })
  .catch((e) => { console.error(`sound: could not fetch ${name}.ogg:`, e); return null; })]));

let muted = false;
try { muted = localStorage.getItem(MUTE_KEY) === "1"; } catch { /* no storage: start with sound on */ }

/** Make (or wake) the AudioContext; call from a click or key press. Safe to call often. */
export function unlock() {
  if (!ctx) {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    ctx = new Context();
    master = ctx.createGain();
    master.gain.value = muted ? 0 : VOLUME;
    master.connect(ctx.destination);
    for (const [name, bytes] of raw) {
      bytes.then((b) => b && ctx.decodeAudioData(b))
        .then((buffer) => { if (buffer) buffers.set(name, buffer); })
        .catch((e) => console.error(`sound: could not decode ${name}.ogg:`, e));
    }
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
}
for (const type of ["pointerdown", "keydown"]) addEventListener(type, unlock, { capture: true });

/** How many sounds have been decoded (for tests). */
export const loaded = () => buffers.size;

export const isMuted = () => muted;

/** Turn sound off or on; returns true if now muted. */
export function toggleMute() {
  muted = !muted;
  try { localStorage.setItem(MUTE_KEY, muted ? "1" : "0"); } catch { /* not kept; fine */ }
  if (master) master.gain.setTargetAtTime(muted ? 0 : VOLUME, ctx.currentTime, 0.02);
  return muted;
}

/** Put the listener at the camera: position and the way it looks (yaw, pitch as in play.js). */
export function listen(x, y, z, yaw, pitch = 0) {
  if (!ctx) return;
  const l = ctx.listener, c = Math.cos(pitch);
  const f = [-Math.sin(yaw) * c, Math.sin(pitch), -Math.cos(yaw) * c];
  if (l.positionX) {
    const t = ctx.currentTime;
    l.positionX.setValueAtTime(x, t); l.positionY.setValueAtTime(y, t); l.positionZ.setValueAtTime(z, t);
    l.forwardX.setValueAtTime(f[0], t); l.forwardY.setValueAtTime(f[1], t); l.forwardZ.setValueAtTime(f[2], t);
    l.upX.setValueAtTime(0, t); l.upY.setValueAtTime(1, t); l.upZ.setValueAtTime(0, t);
  } else {
    l.setPosition(x, y, z);
    l.setOrientation(f[0], f[1], f[2], 0, 1, 0);
  }
}

function panner(at) {
  const p = ctx.createPanner();
  p.panningModel = "HRTF";
  p.distanceModel = "inverse";
  p.refDistance = 4;
  p.maxDistance = 120;
  p.rolloffFactor = 1;
  place(p, at);
  return p;
}

function place(p, at) {
  if (p.positionX) {
    const t = ctx.currentTime;
    p.positionX.setValueAtTime(at[0], t); p.positionY.setValueAtTime(at[1], t); p.positionZ.setValueAtTime(at[2], t);
  } else p.setPosition(at[0], at[1], at[2]);
}

/**
 * Play a sound once, or looped. `at` null means in your head; [x, y, z] places it in the world.
 * Returns a handle {move(at), stop()} (both do nothing if the sound could not play).
 * @param {string} name a file name from FILES, without .ogg
 * @param {{at?: number[] | null, gain?: number, rate?: number, loop?: boolean}} [o]
 */
export function play(name, o = {}) {
  const none = { move() {}, stop() {} };
  if (!ctx || ctx.state !== "running") return none;
  const buffer = buffers.get(name);
  if (!buffer) return none;
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.loop = !!o.loop;
  source.playbackRate.value = o.rate ?? 1;
  const gain = ctx.createGain();
  gain.gain.value = o.gain ?? 1;
  source.connect(gain);
  const pan = o.at ? panner(o.at) : null;
  if (pan) gain.connect(pan).connect(master);
  else gain.connect(master);
  source.start();
  let stopped = false;
  return {
    move(at) { if (pan && !stopped) place(pan, at); },
    stop() {
      if (stopped) return;
      stopped = true;
      gain.gain.setTargetAtTime(0, ctx.currentTime, 0.03);
      source.stop(ctx.currentTime + 0.15);
    },
  };
}

/** A number near 1, for varying a sound's speed a little each time. */
export const vary = (by = 0.06) => 1 + (Math.random() * 2 - 1) * by;
