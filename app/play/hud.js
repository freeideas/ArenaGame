// The HUD: plain DOM over the 3D view (index.html holds the elements, play.css the looks).
// Health, armor, weapon and ammo, the weapon row, the kill feed, the round clock with your frags
// and place, the "you died" overlay, the scoreboard, the Play card and the connection notice.
// It only shows what play.js hands it; it keeps no game state of its own beyond what is on screen.

const $ = (id) => document.getElementById(id);
export const WEAPON_NAMES = { 1: "Blaster", 2: "Launcher", 3: "Beam" };
const HOW_WORDS = { blaster: "blasted", launcher: "shelled", beam: "beamed", void: "knocked into the void", self: "killed" };

function ordinal(n) {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return n + s;
}

function span(text, cls) {
  const s = document.createElement("span");
  s.textContent = text;
  if (cls) s.className = cls;
  return s;
}

export function vitals(hp, armor) {
  $("vitals").hidden = false;
  $("hp").textContent = Math.max(0, Math.round(hp));
  $("armor").textContent = Math.max(0, Math.round(armor));
  $("hp").parentElement.classList.toggle("low", hp <= 25);
}

/** Current weapon, its ammo, and which of the three you hold. */
export function arms(weapons, w, ammo) {
  $("arms").hidden = false;
  $("wname").textContent = WEAPON_NAMES[w] || "";
  $("ammo").textContent = w === 1 ? "" : String(ammo?.[w] ?? 0);
  for (const li of $("slots").children) {
    const n = Number(li.dataset.w);
    li.classList.toggle("have", weapons.includes(n));
    li.classList.toggle("now", n === w);
  }
}

export function hideBody() {
  $("vitals").hidden = true;
  $("arms").hidden = true;
}

/** A kill feed line from a frag event; names(id) gives a shown name. Keeps the last 5, fading. */
export function feed(event, names, me) {
  const li = document.createElement("li");
  const who = (id) => span(names(id), id === me ? "me" : "");
  if (!event.by || event.by === event.of) {
    // Nobody else to credit: a fall, or their own shell (the server sends by null for both).
    const what = event.how === "void" ? "fell into the void" : event.how === "launcher" || event.how === "self" ? "blew themself up" : "died";
    li.append(who(event.of), span(what, "how"));
  } else {
    li.append(who(event.by), span(HOW_WORDS[event.how] || "fragged", "how"), who(event.of));
  }
  const list = $("feed");
  list.append(li);
  while (list.children.length > 5) list.firstElementChild.remove();
  setTimeout(() => li.classList.add("old"), 6000);
  setTimeout(() => li.remove(), 7200);
}

/** The round clock (seconds left, or null) and your frags and place among `players`. */
export function roundLine(left, phase, players, me) {
  if (left == null) $("clock").textContent = "";
  else {
    const s = Math.max(0, Math.ceil(left));
    $("clock").textContent = `${phase === "over" ? "Next round " : ""}${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
  const ranked = rank(players);
  const i = ranked.findIndex((p) => p.id === me);
  $("score").textContent = i < 0 ? "" : `${ranked[i].frags} frags, ${ordinal(i + 1)} of ${ranked.length}`;
}

function rank(players) {
  return [...players].sort((a, b) => b.frags - a.frags || a.deaths - b.deaths || String(a.name).localeCompare(b.name));
}

/** The scoreboard: shown when `show`; `winner` names the round's winner between rounds. */
export function board(show, players, me, winner, note) {
  $("board").hidden = !show;
  if (!show) return;
  $("winner").textContent = winner ? `${winner} wins the round` : "";
  $("boardnote").textContent = note || "";
  $("board").querySelector("tbody").replaceChildren(...rank(players).map((p, i) => {
    const tr = document.createElement("tr");
    if (p.id === me) tr.className = "me";
    const cells = [i + 1, p.name, p.frags, p.deaths, p.bot ? "" : p.ping ?? ""];
    cells.forEach((text, k) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (k === 1 && p.bot) td.append(span("bot", "bot"));
      tr.append(td);
    });
    return tr;
  }));
}

export function death(show, text, canRespawn) {
  $("death").hidden = !show;
  if (!show) return;
  $("deathtext").textContent = text;
  $("respawn").hidden = !canRespawn;
}

/** The Play card. `editable` is false for signed-in players, whose name comes from Endless Mind. */
export function cover(show, name, editable, note) {
  $("cover").hidden = !show;
  if (!show) return;
  const input = $("name");
  if (document.activeElement !== input) input.value = name || "";
  input.disabled = !editable;
  $("namenote").textContent = note || "";
}

export const coverName = () => $("name").value.trim();

export function onPlay(handler) {
  $("playform").addEventListener("submit", (event) => {
    event.preventDefault();
    handler(coverName());
  });
}

/** The connection notice: null hides it. */
export function net(text) {
  $("net").hidden = !text;
  $("net").textContent = text || "";
}

let toastTimer = 0;
export function toast(text) {
  $("toast").hidden = false;
  $("toast").textContent = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500);
}

export function lockHint(show) {
  $("lockhint").hidden = !show;
}

let hitTimer = 0;
export function hitFlash() {
  const c = $("crosshair");
  c.classList.add("hit");
  clearTimeout(hitTimer);
  hitTimer = setTimeout(() => c.classList.remove("hit"), 120);
}
