// Fills the live box from the server's /api/summary every 5 seconds.
const $ = (id) => document.getElementById(id);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
let ends = null; // seconds of round left at the last fetch, and when we got it
let fetchedAt = 0;
let s_over = false;

function showTimer() {
  if (ends === null) { $("timer").textContent = ""; return; }
  const left = Math.max(0, Math.round(ends - (Date.now() - fetchedAt) / 1000));
  $("timer").textContent = `${s_over ? "Next round in" : "Round time left"}: ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
}

function cell(tr, text) {
  const td = document.createElement("td");
  td.textContent = text;
  tr.append(td);
  return td;
}

async function refresh() {
  try {
    const res = await fetch("../api/summary", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    const s = await res.json();
    const people = s.playing | 0;
    $("count").textContent = `In the arena now: ${plural(people, "person", "people")} and ${plural(s.bots | 0, "bot", "bots")}.`;
    const scores = (s.round && s.round.scores) || [];
    $("scores").querySelector("tbody").replaceChildren(...scores.map((p) => {
      const tr = document.createElement("tr");
      const name = cell(tr, p.name);
      if (p.bot) { const b = document.createElement("span"); b.className = "bot"; b.textContent = "bot"; name.append(b); }
      cell(tr, p.frags); cell(tr, p.deaths);
      return tr;
    }));
    $("scores").hidden = !scores.length;
    s_over = !!(s.round && s.round.phase === "over");
    ends = s.round && typeof s.round.ends === "number" && typeof s.now === "number" ? s.round.ends - s.now : null;
    fetchedAt = Date.now();
  } catch {
    $("count").textContent = "The arena is asleep right now. Press Play and it will wake up.";
    $("scores").hidden = true;
    ends = null;
  }
  showTimer();
}
refresh();
setInterval(refresh, 5000);
setInterval(showTimer, 1000);
