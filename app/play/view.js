// The 3D scene, drawn with three.js (../vendor/): the map's boxes and pads, the pickups, other
// players, shells, shot lines, explosions, a star field and a simple weapon held in front of you.
// Flat-shaded and plain on purpose (specs/game.md). Coordinates are the game's own: metres,
// y up, yaw 0 looking toward -z and increasing to the left, exactly as three.js turns a camera.

import * as THREE from "../vendor/three.module.min.js";

const EYE = 1.6;
const SHOT_LIFE = 0.4; // seconds a shot line takes to fade
const BOOM_LIFE = 0.3;
const BOOM_SIZE = 3.5; // the Launcher's splash radius

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
const PERSON_COLOR = 0x9ad1ff;
const BOT_COLOR = 0xff9a5a;

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
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
  sprite.scale.set(1.8, 0.45, 1);
  sprite.position.y = 2.25;
  return sprite;
}

/** A player: a cylinder body, a sphere head and a visor showing which way they face. */
function makeFigure(bot) {
  const color = bot ? BOT_COLOR : PERSON_COLOR;
  const skin = new THREE.MeshLambertMaterial({ color, flatShading: true });
  const figure = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.4, 1.3, 10), skin);
  body.position.y = 0.65;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.26, 10, 7), skin);
  head.position.y = 1.55;
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.1, 0.12), new THREE.MeshBasicMaterial({ color: 0x10131f }));
  visor.position.set(0, 1.6, -0.22);
  const gun = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.6), new THREE.MeshLambertMaterial({ color: 0x333a4a }));
  gun.position.set(0.32, 1.15, -0.3);
  figure.add(body, head, visor, gun);
  return figure;
}

/** Make the scene in `canvas` for the parsed map.json. */
export function createView(canvas, map) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x04050c);
  const camera = new THREE.PerspectiveCamera(80, 1, 0.05, 2000);
  camera.rotation.order = "YXZ";
  scene.add(camera);

  scene.add(new THREE.AmbientLight(0x8090c0, 0.9));
  scene.add(new THREE.HemisphereLight(0xb8c8ff, 0x4a3a66, 0.8));
  const sun = new THREE.DirectionalLight(0xfff2dd, 2.2);
  sun.position.set(30, 60, 20);
  scene.add(sun);

  // Stars: points scattered on a far sphere.
  {
    const n = 1800;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, r = Math.sqrt(1 - u * u);
      pos.set([r * Math.cos(a) * 900, u * 900, r * Math.sin(a) * 900], i * 3);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    scene.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xdfe6ff, size: 1.6, sizeAttenuation: false, fog: false })));
  }

  // The map: every box and pad, flat colored, with faint edges so shapes read clearly.
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35 });
  function addBox(b, material) {
    const sx = b.max[0] - b.min[0], sy = b.max[1] - b.min[1], sz = b.max[2] - b.min[2];
    const geometry = new THREE.BoxGeometry(sx, sy, sz);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2);
    mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial));
    scene.add(mesh);
    return mesh;
  }
  for (const b of map.boxes) addBox(b, new THREE.MeshLambertMaterial({ color: b.color || "#667", flatShading: true }));
  const padMaterials = map.pads.map((p) => {
    const color = new THREE.Color(p.color || "#ffd23f");
    const material = new THREE.MeshLambertMaterial({ color, emissive: color, emissiveIntensity: 0.5, flatShading: true });
    addBox(p, material);
    return material;
  });

  // Pickups: small spinning shapes, hidden while taken.
  const items = map.items.map((item, i) => {
    const look = ITEM_LOOK[item.type] || ITEM_LOOK.health;
    const color = new THREE.Color(look.color);
    const mesh = new THREE.Mesh(itemGeometry(look),
      new THREE.MeshLambertMaterial({ color, emissive: color, emissiveIntensity: 0.35, flatShading: true }));
    mesh.position.set(item.at[0], item.at[1] + 0.8, item.at[2]);
    mesh.rotation.y = i;
    scene.add(mesh);
    return mesh;
  });

  // A simple weapon held at the lower right of the view.
  const held = new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.045, 0.4), new THREE.MeshLambertMaterial({ color: WEAPON_COLOR[1] }));
  held.position.set(0.2, -0.17, -0.62);
  camera.add(held);
  let heldKick = 0;

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

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const pr = renderer.getPixelRatio();
    if (canvas.width !== Math.floor(w * pr) || canvas.height !== Math.floor(h * pr)) {
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
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

  function addBoom(x, y, z) {
    const obj = new THREE.Mesh(boomGeometry, new THREE.MeshBasicMaterial({ color: 0xffa040, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending, depthWrite: false }));
    obj.position.set(x, y, z);
    obj.scale.setScalar(0.3);
    scene.add(obj);
    effects.push({ obj, born: performance.now() / 1000, life: BOOM_LIFE, kind: "boom" });
  }

  function disposeTree(obj) {
    obj.traverse((o) => {
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
  }

  function updatePlayers(people) {
    const here = new Set();
    for (const p of people) {
      if (p.dead) continue;
      here.add(p.id);
      let f = figures.get(p.id);
      if (!f || f.bot !== !!p.bot) {
        if (f) { scene.remove(f.figure); disposeTree(f.figure); }
        f = { figure: makeFigure(!!p.bot), label: null, name: "", bot: !!p.bot };
        scene.add(f.figure);
        figures.set(p.id, f);
      }
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
    held.visible = f.weapon != null;
    if (f.weapon != null) held.material.color.setHex(WEAPON_COLOR[f.weapon] || 0xffffff);
    heldKick = Math.max(0, heldKick - 0.01);
    held.position.z = -0.62 + heldKick;
    const pulse = 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(now * 4));
    for (const m of padMaterials) m.emissiveIntensity = pulse;
    items.forEach((mesh, i) => {
      mesh.visible = !f.items || !!f.items[i];
      mesh.rotation.y = now * 1.6 + i;
      mesh.position.y = map.items[i].at[1] + 0.8 + Math.sin(now * 2 + i) * 0.08;
    });
    updatePlayers(f.players);
    updateShells(f.shells);
    updateEffects(now);
    renderer.render(scene, camera);
  }

  return { draw, addShot, addBoom, kick: () => { heldKick = 0.06; }, EYE };
}
