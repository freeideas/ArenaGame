// The 3D scene, drawn with three.js (../vendor/): the map's boxes and pads, the pickups, other
// players, shells, shot lines, explosions and scorch marks, under a night sky, with the weapon held
// in front of you. The weapons are Kenney's CC0 Blaster Kit models in ../shared/models/, also shown
// in other players' hands. Surfaces use the CC0 photo textures in ../shared/textures/ (color, normal
// and roughness maps), lit by one shadow-casting sun. `?plain` in the page address turns shadows off
// for weak machines. Coordinates are the game's own: metres, y up, yaw 0 looking toward -z and
// increasing to the left, exactly as three.js turns a camera.

import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";

const EYE = 1.6;
const SHOT_LIFE = 0.4; // seconds a shot line takes to fade
const BOOM_LIFE = 0.3;
const BOOM_SIZE = 3.5; // the Launcher's splash radius
const SCORCH_LIFE = 20; // seconds a scorch mark takes to fade
const SCORCH_MAX = 40;
const TILE = 2; // metres one texture image covers
const TEXTURES = "../shared/textures/";
const PLAIN = new URLSearchParams(location.search).has("plain");
// How shiny each surface is (metalness) and how much to darken it (shade, 1 unchanged).
const SURFACE = {
  plates: { metalness: 0.3 },
  steel: { metalness: 0.35 },
  grate: { metalness: 0.3 },
  rust: { metalness: 0.1 },
  concrete: { metalness: 0, shade: 0.55 }, // the photo is pale; darken it to sit with the metals
  painted: { metalness: 0.2 },
};
const TINT = 0.3; // how much a box color tints its texture (0 none, 1 full)

// How each pickup looks: a shape, a color and a size.
const ITEM_LOOK = {
  health: { shape: "box", color: 0x5ee08a, size: 0.35 },
  bighealth: { shape: "box", color: 0x2cff7a, size: 0.6 },
  shard: { shape: "tetra", color: 0x8fd8ff, size: 0.3 },
  armor: { shape: "ico", color: 0x3aa8ff, size: 0.45 },
  launcher: { shape: "cyl", color: 0xff8a3d, size: 0.5 },
  beam: { shape: "long", color: 0xd36bff, size: 0.6 },
  shells: { shape: "box", color: 0xff8a3d, size: 0.28 },
  charges: { shape: "box", color: 0xd36bff, size: 0.28 },
};
const WEAPON_COLOR = { 1: 0x7fd7ff, 2: 0xff8a3d, 3: 0xd36bff };
// Which model each weapon uses, how long it is held in view and in others' hands (metres), and a
// hue turn for its palette so it matches WEAPON_COLOR (the Blaster's red model becomes light blue).
const GUNS = {
  1: { file: "blaster-h", held: 0.25, worn: 0.5, hue: 190 },
  2: { file: "blaster-k", held: 0.3, worn: 0.55, hue: 0 },
  3: { file: "blaster-f", held: 0.52, worn: 0.85, hue: 0 },
};
const MODELS = "../shared/models/";
const HELD_AT = [0.16, -0.15, -0.46]; // the held gun's middle, in camera space
const KICK_TIME = 0.14; // seconds the recoil takes to settle
const FLASH_TIME = 0.06;
const SWITCH_TIME = 0.25;
const PERSON_COLOR = 0x9ad1ff;
const BOT_COLOR = 0xff9a5a;

const loader = new THREE.TextureLoader();
/** @type {Map<string, {map: THREE.Texture, normalMap: THREE.Texture, roughnessMap: THREE.Texture}>} */
const surfaceCache = new Map();
let anisotropy = 1;

/** The color, normal and roughness images of one surface in ../shared/textures/, loaded once. */
function surfaceTextures(name) {
  let s = surfaceCache.get(name);
  if (!s) {
    const load = (kind, srgb) => {
      const t = loader.load(`${TEXTURES}${name}_${kind}.jpg`);
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = anisotropy;
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      return t;
    };
    s = { map: load("color", true), normalMap: load("normal", false), roughnessMap: load("rough", false) };
    surfaceCache.set(name, s);
  }
  return s;
}

/** A lit, textured material for the named surface, tinted a little toward `tint`. */
function surfaceMaterial(name, tint, amount = TINT) {
  const known = SURFACE[name] ? name : "steel";
  const color = new THREE.Color(0xffffff);
  if (tint != null) color.lerp(new THREE.Color(tint), amount);
  color.multiplyScalar(SURFACE[known].shade ?? 1);
  return new THREE.MeshStandardMaterial({ ...surfaceTextures(known), color, metalness: SURFACE[known].metalness, roughness: 1 });
}

/** Scale a box's texture coordinates so one image covers TILE metres on every face. */
function tileUVs(geometry, sx, sy, sz) {
  const uv = geometry.attributes.uv;
  const faces = [[sz, sy], [sz, sy], [sx, sz], [sx, sz], [sx, sy], [sx, sy]]; // +x -x +y -y +z -z
  for (let i = 0; i < uv.count; i++) {
    const [du, dv] = faces[Math.floor(i / 4)];
    uv.setXY(i, uv.getX(i) * du / TILE, uv.getY(i) * dv / TILE);
  }
  uv.needsUpdate = true;
}

/** A canvas drawn by `paint(g, size)` as a texture. */
function canvasTexture(size, paint) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  paint(c.getContext("2d"), size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** The pad emblem: a ring with two chevrons pointing up the image (the way the pad throws you). */
function emblemTexture() {
  return canvasTexture(256, (g, n) => {
    g.strokeStyle = "#fff";
    g.lineCap = g.lineJoin = "round";
    g.shadowColor = "#fff";
    g.shadowBlur = 10;
    g.lineWidth = 12;
    g.beginPath();
    g.arc(n / 2, n / 2, n * 0.42, 0, Math.PI * 2);
    g.stroke();
    g.lineWidth = 18;
    for (const y of [0.42, 0.62]) {
      g.beginPath();
      g.moveTo(n * 0.3, n * (y + 0.12));
      g.lineTo(n * 0.5, n * (y - 0.08));
      g.lineTo(n * 0.7, n * (y + 0.12));
      g.stroke();
    }
  });
}

/** A plain ring, for the wave that runs outward from each pad. */
function ringTexture() {
  return canvasTexture(128, (g, n) => {
    g.strokeStyle = "#fff";
    g.shadowColor = "#fff";
    g.shadowBlur = 6;
    g.lineWidth = 6;
    g.beginPath();
    g.arc(n / 2, n / 2, n * 0.44, 0, Math.PI * 2);
    g.stroke();
  });
}

/** A soft, ragged dark blot for scorch marks. */
function scorchTexture() {
  return canvasTexture(128, (g, n) => {
    const blot = (x, y, r, a) => {
      const grad = g.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, `rgba(8,6,5,${a})`);
      grad.addColorStop(0.6, `rgba(12,9,7,${a * 0.6})`);
      grad.addColorStop(1, "rgba(15,12,10,0)");
      g.fillStyle = grad;
      g.beginPath();
      g.arc(x, y, r, 0, Math.PI * 2);
      g.fill();
    };
    blot(n / 2, n / 2, n * 0.45, 0.8);
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2 + Math.random() * 0.5, d = n * (0.18 + Math.random() * 0.12);
      blot(n / 2 + Math.cos(a) * d, n / 2 + Math.sin(a) * d, n * (0.08 + Math.random() * 0.1), 0.5);
    }
  });
}

function itemGeometry(look) {
  const s = look.size;
  if (look.shape === "tetra") return new THREE.TetrahedronGeometry(s);
  if (look.shape === "ico") return new THREE.IcosahedronGeometry(s * 0.7, 0);
  if (look.shape === "cyl") return new THREE.CylinderGeometry(s * 0.3, s * 0.3, s * 1.4, 7).rotateZ(Math.PI / 2);
  if (look.shape === "long") return new THREE.BoxGeometry(s * 2, s * 0.25, s * 0.25);
  return new THREE.BoxGeometry(s, s, s);
}

/** A name floating over another player, as a sprite with canvas text. */
function makeLabel(text, color) {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 64;
  const g = c.getContext("2d");
  g.font = "bold 30px system-ui, sans-serif";
  g.textAlign = "center";
  g.lineWidth = 6;
  g.strokeStyle = "#000a";
  g.strokeText(text, 128, 42);
  g.fillStyle = color;
  g.fillText(text, 128, 42);
  const texture = new THREE.CanvasTexture(c);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false, fog: false }));
  sprite.scale.set(1.8, 0.45, 1);
  sprite.position.y = 2.25;
  return sprite;
}

/**
 * The worn paint image turned grey (the photo is blue paint with rust), so a tint shows true:
 * shared by every player, drawn once the photo has loaded.
 */
let greyPaint = null;
function greyPaintTexture() {
  if (greyPaint) return greyPaint;
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  greyPaint = new THREE.CanvasTexture(c);
  greyPaint.colorSpace = THREE.SRGBColorSpace;
  greyPaint.wrapS = greyPaint.wrapT = THREE.RepeatWrapping;
  const img = new Image();
  img.onload = () => {
    const g = c.getContext("2d");
    g.filter = "grayscale(1) brightness(3.2) contrast(0.45)";
    g.drawImage(img, 0, 0, 512, 512);
    greyPaint.needsUpdate = true;
  };
  img.src = `${TEXTURES}painted_color.jpg`;
  return greyPaint;
}

/** A player: a painted-metal cylinder body, a sphere head and a visor showing which way they face. */
/**
 * One weapon model, loaded once: centred, scaled to 1 m long, pointing along -z, with the middle of
 * its muzzle (the frontmost points) noted in `userData.muzzle` (the same 1 m scale).
 * @type {Record<number, THREE.Group>}
 */
const gunModels = {};
const gunsReady = new Promise((resolve) => {
  const loader = new GLTFLoader();
  let left = Object.keys(GUNS).length;
  const done = () => { if (--left === 0) resolve(); };
  for (const [w, spec] of Object.entries(GUNS)) {
    loader.load(`${MODELS}${spec.file}.glb`, (gltf) => {
      const model = gltf.scene;
      model.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3());
      // The muzzle: the average height of the points within 3% of the front.
      let sum = 0, n = 0;
      const v = new THREE.Vector3();
      model.traverse((o) => {
        if (!o.isMesh) return;
        const pos = o.geometry.attributes.position;
        for (let i = 0; i < pos.count; i++) {
          v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
          if (v.z < box.min.z + size.z * 0.03) { sum += v.y; n++; }
        }
        o.userData.shared = true; // geometry and material are shared by every copy: never dispose
        if (spec.hue && o.material.map) o.material = hueTurned(o.material, spec.hue);
      });
      model.position.copy(mid).negate();
      const g = new THREE.Group();
      g.add(model);
      g.scale.setScalar(1 / size.z);
      g.userData.muzzle = new THREE.Vector3(0, ((n ? sum / n : mid.y) - mid.y) / size.z, -0.5);
      gunModels[w] = g;
      done();
    }, undefined, (e) => { console.error(`Could not load ${spec.file}.glb:`, e); done(); });
  }
});

/** A copy of a material whose palette image has its hue turned by `degrees`. */
function hueTurned(material, degrees) {
  const src = material.map, img = src.image;
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const g = c.getContext("2d");
  g.filter = `hue-rotate(${degrees}deg) saturate(0.8) brightness(1.15)`;
  g.drawImage(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  for (const k of ["flipY", "wrapS", "wrapT", "magFilter", "minFilter", "colorSpace", "channel"]) t[k] = src[k];
  const m = material.clone();
  m.map = t;
  return m;
}

/** A copy of weapon w's model `length` metres long, or null if it is not loaded. */
function gunCopy(w, length) {
  const base = gunModels[w];
  if (!base) return null;
  const g = base.clone();
  g.scale.multiplyScalar(length);
  g.userData.muzzle = base.userData.muzzle.clone().multiplyScalar(length);
  return g;
}

/** The gun a figure holds: the model for weapon w, or a plain box until the models have loaded. */
function figureGun(w) {
  const gun = gunCopy(w, (GUNS[w] || GUNS[1]).worn);
  if (gun) {
    gun.traverse((o) => { if (o.isMesh) o.castShadow = true; });
    return gun;
  }
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.6), surfaceMaterial("steel", 0x333a4a, 0.6));
  box.castShadow = true;
  return box;
}

function makeFigure(bot) {
  const skin = surfaceMaterial("painted", bot ? BOT_COLOR : PERSON_COLOR, 1);
  skin.map = greyPaintTexture();
  const figure = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.4, 1.3, 16), skin);
  body.position.y = 0.65;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.26, 16, 10), skin);
  head.position.y = 1.55;
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.1, 0.12),
    new THREE.MeshStandardMaterial({ color: 0x10131f, metalness: 0.8, roughness: 0.15 }));
  visor.position.set(0, 1.6, -0.22);
  for (const m of [body, head, visor]) m.castShadow = true;
  // The hand: a holder at the right side that tilts with the player's pitch; the gun goes in it.
  const hand = new THREE.Group();
  hand.position.set(0.34, 1.2, -0.25);
  figure.add(body, head, visor, hand);
  return { figure, hand };
}

/** Make the scene in `canvas` for the parsed map.json. */
export function createView(canvas, map) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  renderer.shadowMap.enabled = !PLAIN;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x04050c);
  scene.fog = new THREE.FogExp2(0x05060d, 0.009);
  const camera = new THREE.PerspectiveCamera(80, 1, 0.05, 2000);
  camera.rotation.order = "YXZ";
  scene.add(camera);

  // The night sky: one equirectangular photo as the background and as soft light and reflections.
  const sky = loader.load(`${TEXTURES}sky.jpg`);
  sky.mapping = THREE.EquirectangularReflectionMapping;
  sky.colorSpace = THREE.SRGBColorSpace;
  scene.background = sky;
  scene.environment = sky;
  scene.environmentIntensity = 1;

  scene.add(new THREE.AmbientLight(0x8090c0, 0.4));
  scene.add(new THREE.HemisphereLight(0xb8c8ff, 0x3a3050, 0.9));
  const sun = new THREE.DirectionalLight(0xfff0dc, 3.2);
  sun.position.set(30, 60, 20);
  scene.add(sun, sun.target);
  if (!PLAIN) {
    // Fit the sun's shadow camera around the whole map (x and z -35..35, y -12..16).
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.04;
    const view = new THREE.Matrix4().lookAt(sun.position, sun.target.position, new THREE.Vector3(0, 1, 0));
    view.setPosition(sun.position).invert();
    const lo = new THREE.Vector3(Infinity, Infinity, Infinity), hi = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
    for (const x of [-35, 35]) for (const y of [-12, 16]) for (const z of [-35, 35]) {
      const p = new THREE.Vector3(x, y, z).applyMatrix4(view);
      lo.min(p);
      hi.max(p);
    }
    const c = sun.shadow.camera;
    c.left = lo.x; c.right = hi.x; c.bottom = lo.y; c.top = hi.y;
    c.near = Math.max(0.1, -hi.z - 1); c.far = -lo.z + 1;
    c.updateProjectionMatrix();
  }

  // The map: every box textured by its "material" (top, bottom, four sides), with faint edges.
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 });
  function addBox(b, material) {
    const sx = b.max[0] - b.min[0], sy = b.max[1] - b.min[1], sz = b.max[2] - b.min[2];
    const geometry = new THREE.BoxGeometry(sx, sy, sz);
    tileUVs(geometry, sx, sy, sz);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial));
    scene.add(mesh);
    return mesh;
  }
  for (const b of map.boxes) {
    const m = b.material || {};
    const top = surfaceMaterial(m.top || "steel", b.color);
    const side = surfaceMaterial(m.side || "steel", b.color);
    const bottom = m.bottom ? surfaceMaterial(m.bottom, b.color) : side;
    addBox(b, [side, side, top, bottom, side, side]); // +x -x +y -y +z -z
  }

  // Pads: glowing boxes with an emblem on top pointing the way they throw you, and a ring wave.
  const emblem = emblemTexture(), ring = ringTexture();
  const glow = (texture, color) => new THREE.MeshBasicMaterial({ map: texture, color, transparent: true,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false, fog: false });
  const pads = map.pads.map((p) => {
    const color = new THREE.Color(p.color || "#ffd23f");
    const material = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.35), emissive: color, emissiveIntensity: 0.3, roughness: 0.5, metalness: 0.2 });
    addBox(p, material);
    const size = Math.min(p.max[0] - p.min[0], p.max[2] - p.min[2]);
    const plane = new THREE.PlaneGeometry(size, size).rotateX(-Math.PI / 2);
    const mark = new THREE.Mesh(plane, glow(emblem, color));
    mark.position.set((p.min[0] + p.max[0]) / 2, p.max[1] + 0.012, (p.min[2] + p.max[2]) / 2);
    if (p.launch[0] || p.launch[2]) mark.rotation.y = Math.atan2(-p.launch[0], -p.launch[2]);
    const wave = new THREE.Mesh(plane, glow(ring, color));
    wave.position.copy(mark.position).y += 0.004;
    scene.add(mark, wave);
    return { material, mark, wave };
  });

  // Pickups: small spinning shapes, hidden while taken.
  const items = map.items.map((item, i) => {
    const look = ITEM_LOOK[item.type] || ITEM_LOOK.health;
    const color = new THREE.Color(look.color);
    const mesh = new THREE.Mesh(itemGeometry(look),
      new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.45, roughness: 0.35, metalness: 0.3, flatShading: true }));
    mesh.position.set(item.at[0], item.at[1] + 0.8, item.at[2]);
    mesh.rotation.y = i;
    mesh.castShadow = true;
    scene.add(mesh);
    return mesh;
  });

  // The held weapon, at the lower right of the view. It has its own small scene and camera, drawn
  // after the world with the depth cleared, so it never pokes into walls.
  const heldScene = new THREE.Scene();
  heldScene.environment = sky;
  heldScene.environmentIntensity = 0.6;
  heldScene.add(new THREE.HemisphereLight(0xc8d4ff, 0x40384f, 1.4));
  const heldSun = new THREE.DirectionalLight(0xfff0dc, 2.2);
  heldSun.position.set(0.6, 1, 0.4);
  heldScene.add(heldSun);
  const heldCamera = new THREE.PerspectiveCamera(60, 1, 0.01, 10);
  const heldRig = new THREE.Group(); // moved for recoil and switching; the gun sits inside it
  heldScene.add(heldRig);
  /** @type {Record<number, THREE.Group>} */
  const heldGuns = {};
  let heldW = null, kickAt = -1, switchAt = -1;
  // The muzzle flash: a soft additive star at the muzzle, and a light that brightens the gun.
  const flash = new THREE.Sprite(new THREE.SpriteMaterial({ map: canvasTexture(64, (g, n) => {
    const grad = g.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.25, "rgba(255,240,200,0.9)");
    grad.addColorStop(1, "rgba(255,200,120,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, n, n);
  }), blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, toneMapped: false, transparent: true }));
  flash.visible = false;
  const flashLight = new THREE.PointLight(0xffd8a0, 0, 1.2, 2);
  heldScene.add(flash, flashLight);
  gunsReady.then(() => {
    for (const w of Object.keys(GUNS)) heldGuns[w] = gunCopy(Number(w), GUNS[w].held);
  });

  /** @type {Map<string, {figure: THREE.Group, label: THREE.Sprite | null, name: string, bot: boolean}>} */
  const figures = new Map();
  /** @type {Map<string, THREE.Group>} */
  const shellMeshes = new Map();
  const shellGeometry = new THREE.SphereGeometry(0.16, 8, 6);
  const shellMaterial = new THREE.MeshBasicMaterial({ color: 0xffd28a });
  const trailMaterial = new THREE.MeshBasicMaterial({ color: 0xff8a3d, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false });
  const trailGeometry = new THREE.CylinderGeometry(0.12, 0.02, 1.6, 6).translate(0, -0.8, 0); // tip at the shell, tail behind

  /** @type {{obj: THREE.Object3D, born: number, life: number, kind: string}[]} */
  const effects = [];
  const boomGeometry = new THREE.SphereGeometry(1, 16, 10);
  const UP = new THREE.Vector3(0, 1, 0);

  // Scorch marks: flat dark blots on the top surface under each explosion.
  const scorchGeometry = new THREE.PlaneGeometry(2.6, 2.6).rotateX(-Math.PI / 2);
  const scorchMap = scorchTexture();
  /** @type {{mesh: THREE.Mesh, born: number}[]} */
  const scorches = [];

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const pr = renderer.getPixelRatio();
    if (canvas.width !== Math.floor(w * pr) || canvas.height !== Math.floor(h * pr)) {
      renderer.setSize(w, h, false);
      camera.aspect = heldCamera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
      heldCamera.updateProjectionMatrix();
    }
  }

  /** A shot from o to h, w being the weapon (1 Blaster, 3 Beam). */
  function addShot(o, h, w) {
    const now = performance.now() / 1000;
    const from = new THREE.Vector3(o[0], o[1], o[2]), to = new THREE.Vector3(h[0], h[1], h[2]);
    const length = from.distanceTo(to);
    // A rod from o to h: thin and pale for the Blaster; bright and thick, with a glow, for the Beam.
    const rod = (radius, color, opacity) => new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, 6),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
    const obj = new THREE.Group();
    if (w === 3) obj.add(rod(0.025, 0xffffff, 1), rod(0.07, 0xd36bff, 0.55));
    else obj.add(rod(0.012, 0xbfeaff, 0.8));
    obj.position.copy(from).add(to).multiplyScalar(0.5);
    if (length > 0) obj.quaternion.setFromUnitVectors(UP, to.clone().sub(from).normalize());
    scene.add(obj);
    effects.push({ obj, born: now, life: SHOT_LIFE, kind: "shot" });
  }

  /** Leave a scorch mark on the highest top surface at most 3 m below (x, y, z), if there is one. */
  function addScorch(x, y, z) {
    let top = -Infinity;
    for (const b of map.boxes) {
      if (x < b.min[0] || x > b.max[0] || z < b.min[2] || z > b.max[2]) continue;
      if (b.max[1] <= y + 0.2 && y - b.max[1] <= 3 && b.max[1] > top) top = b.max[1];
    }
    if (top === -Infinity) return;
    const mesh = new THREE.Mesh(scorchGeometry, new THREE.MeshBasicMaterial({ map: scorchMap, transparent: true, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    mesh.position.set(x, top + 0.008, z);
    mesh.rotation.y = Math.random() * Math.PI * 2;
    mesh.scale.setScalar(0.8 + Math.random() * 0.4);
    mesh.renderOrder = 1;
    scene.add(mesh);
    scorches.push({ mesh, born: performance.now() / 1000 });
    while (scorches.length > SCORCH_MAX) dropScorch(0);
  }

  function dropScorch(i) {
    const [s] = scorches.splice(i, 1);
    scene.remove(s.mesh);
    s.mesh.material.dispose();
  }

  function addBoom(x, y, z) {
    const obj = new THREE.Mesh(boomGeometry, new THREE.MeshBasicMaterial({ color: 0xffa040, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending, depthWrite: false }));
    obj.position.set(x, y, z);
    obj.scale.setScalar(0.3);
    scene.add(obj);
    effects.push({ obj, born: performance.now() / 1000, life: BOOM_LIFE, kind: "boom" });
    addScorch(x, y, z);
  }

  function disposeTree(obj) {
    obj.traverse((o) => {
      if (o.userData.shared) return;
      if (o.geometry && o.geometry !== boomGeometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }

  function updateEffects(now) {
    for (let i = effects.length - 1; i >= 0; i--) {
      const e = effects[i];
      const k = (now - e.born) / e.life;
      if (k >= 1) {
        scene.remove(e.obj);
        disposeTree(e.obj);
        effects.splice(i, 1);
        continue;
      }
      if (e.kind === "boom") {
        e.obj.scale.setScalar(0.3 + (BOOM_SIZE - 0.3) * Math.sqrt(k));
        e.obj.material.opacity = 0.7 * (1 - k);
      } else {
        e.obj.traverse((o) => { if (o.material) o.material.opacity = (o.userData.base ??= o.material.opacity) * (1 - k); });
      }
    }
    for (let i = scorches.length - 1; i >= 0; i--) {
      const k = (now - scorches[i].born) / SCORCH_LIFE;
      if (k >= 1) dropScorch(i);
      else scorches[i].mesh.material.opacity = k < 0.5 ? 1 : 2 * (1 - k);
    }
  }

  function updatePlayers(people) {
    const here = new Set();
    for (const p of people) {
      if (p.dead) continue;
      here.add(p.id);
      let f = figures.get(p.id);
      if (!f || f.bot !== !!p.bot) {
        if (f) { scene.remove(f.figure); disposeTree(f.figure); }
        const made = makeFigure(!!p.bot);
        f = { figure: made.figure, hand: made.hand, gun: null, gunW: null, gunReal: false, label: null, name: "", bot: !!p.bot };
        scene.add(f.figure);
        figures.set(p.id, f);
      }
      const pw = GUNS[p.w] ? p.w : 1;
      if (f.gunW !== pw || (!f.gunReal && gunModels[pw])) {
        if (f.gun) { f.hand.remove(f.gun); disposeTree(f.gun); }
        f.gun = figureGun(pw);
        f.gunW = pw;
        f.gunReal = !!gunModels[pw];
        f.hand.add(f.gun);
      }
      f.hand.rotation.x = p.pitch || 0;
      if (f.name !== p.name) {
        if (f.label) { f.figure.remove(f.label); disposeTree(f.label); }
        f.label = makeLabel(p.bot ? `${p.name} (bot)` : p.name, p.bot ? "#ffc39a" : "#e6ecff");
        f.figure.add(f.label);
        f.name = p.name;
      }
      f.figure.position.set(p.x, p.y, p.z);
      f.figure.rotation.y = p.yaw || 0;
    }
    for (const [id, f] of figures) {
      if (!here.has(id)) {
        scene.remove(f.figure);
        disposeTree(f.figure);
        figures.delete(id);
      }
    }
  }

  function updateShells(shells) {
    const here = new Set();
    for (const s of shells) {
      here.add(s.id);
      let g = shellMeshes.get(s.id);
      if (!g) {
        g = new THREE.Group();
        g.add(new THREE.Mesh(shellGeometry, shellMaterial), new THREE.Mesh(trailGeometry, trailMaterial));
        scene.add(g);
        shellMeshes.set(s.id, g);
      }
      g.position.set(s.x, s.y, s.z);
      const d = new THREE.Vector3(s.dx, s.dy, s.dz);
      if (d.lengthSq() > 0) g.quaternion.setFromUnitVectors(UP, d.normalize());
    }
    for (const [id, g] of shellMeshes) {
      if (!here.has(id)) { scene.remove(g); shellMeshes.delete(id); }
    }
  }

  /**
   * Draw one frame.
   * @param {object} f
   * @param {{x:number,y:number,z:number,yaw:number,pitch:number}} f.eye where the camera is (the eyes) and looks
   * @param {any[]} f.players others to draw (already moved to the moment shown)
   * @param {any[]} f.shells shells in flight
   * @param {number[] | null} f.items 1 for each item there, 0 for each taken; null shows them all
   * @param {number | null} f.weapon the held weapon to show, or null for none
   */
  function draw(f) {
    resize();
    const now = performance.now() / 1000;
    camera.position.set(f.eye.x, f.eye.y, f.eye.z);
    camera.rotation.set(f.eye.pitch, f.eye.yaw, 0);
    drawHeld(f.weapon, now);
    const beat = 0.5 + 0.5 * Math.sin(now * 4);
    const wave = (now * 0.8) % 1; // the ring runs outward and fades, once every 1.25 s
    for (const p of pads) {
      p.material.emissiveIntensity = 0.12 + 0.3 * beat;
      p.mark.material.opacity = 0.55 + 0.45 * beat;
      p.wave.scale.setScalar(0.35 + 0.75 * wave);
      p.wave.material.opacity = 0.9 * (1 - wave);
    }
    items.forEach((mesh, i) => {
      mesh.visible = !f.items || !!f.items[i];
      mesh.rotation.y = now * 1.6 + i;
      mesh.position.y = map.items[i].at[1] + 0.8 + Math.sin(now * 2 + i) * 0.08;
    });
    updatePlayers(f.players);
    updateShells(f.shells);
    updateEffects(now);
    renderer.autoClear = false;
    renderer.clear();
    renderer.render(scene, camera);
    if (heldRig.visible) {
      renderer.clearDepth();
      renderer.render(heldScene, heldCamera);
    }
  }

  /** Place the held gun for weapon w (null hides it): recoil after a shot, and a lift after a switch. */
  function drawHeld(w, now) {
    const gun = w != null ? heldGuns[w] : null;
    heldRig.visible = !!gun;
    if (w !== heldW) {
      for (const g of Object.values(heldGuns)) heldRig.remove(g);
      if (gun) heldRig.add(gun);
      if (heldW != null && w != null) switchAt = now;
      heldW = gun ? w : null;
    }
    if (!gun) { flash.visible = false; flashLight.intensity = 0; return; }
    const k = Math.max(0, 1 - (now - kickAt) / KICK_TIME) ** 2; // 1 just after a shot, easing to 0
    const lift = Math.max(0, 1 - (now - switchAt) / SWITCH_TIME) ** 2;
    heldRig.position.set(HELD_AT[0], HELD_AT[1] - 0.18 * lift, HELD_AT[2] + 0.06 * k);
    heldRig.rotation.set(0.12 * k - 0.6 * lift, 0.04, 0); // turned a little toward the crosshair
    const lit = now - kickAt < FLASH_TIME;
    flash.visible = lit;
    flashLight.intensity = lit ? 2.5 : 0;
    if (lit) {
      heldRig.updateMatrixWorld(true);
      const at = gun.userData.muzzle.clone().add(new THREE.Vector3(0, 0, -0.03)).applyMatrix4(heldRig.matrixWorld);
      flash.position.copy(at);
      flash.material.color.setHex(WEAPON_COLOR[w] || 0xffffff).lerp(new THREE.Color(0xffffff), 0.5);
      flash.material.rotation = Math.random() * Math.PI;
      flash.scale.setScalar(w === 1 ? 0.09 : 0.14);
      flashLight.position.copy(at);
    }
  }

  /** Where the held gun's muzzle is in the world (for starting shot lines there). */
  function muzzle() {
    const gun = heldW != null ? heldGuns[heldW] : null;
    const local = gun ? gun.userData.muzzle.clone().add(new THREE.Vector3(...HELD_AT)) : new THREE.Vector3(0.2, -0.17, -0.85);
    camera.updateMatrixWorld();
    // The held camera has a narrower view than the world camera; move the point so it lands on the
    // same spot of the screen.
    const scale = Math.tan((camera.fov * Math.PI) / 360) / Math.tan((heldCamera.fov * Math.PI) / 360);
    local.x *= scale;
    local.y *= scale;
    return camera.localToWorld(local).toArray();
  }

  return { draw, addShot, addBoom, muzzle, kick: () => { kickAt = performance.now() / 1000; }, EYE };
}
