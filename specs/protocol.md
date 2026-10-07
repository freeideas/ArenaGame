# Browser and server

The play page and the server talk over one WebSocket at `/ws` (relative to the site's root) in JSON messages, each with a type `t`. Positions are metres as in [map.md](map.md); angles are radians. Player IDs are short strings the server makes. The server sends a `state` message 20 times a second; it simulates at 30 ticks a second.

## From the browser

| Message                                              | When                                                                 |
| ---------------------------------------------------- | -------------------------------------------------------------------- |
| `{t: "hello", guest}`                                | First. `guest` is the stored guest ID (32 hex digits) or null        |
| `{t: "join"}`                                        | Play pressed: enter the arena (spawns at once)                       |
| `{t: "at", x, y, z, yaw, pitch, vx, vy, vz, ground, seq}` | Where the player is, 20 times a second while alive; `seq` counts up |
| `{t: "fire", w, ox, oy, oz, dx, dy, dz, hit}`        | Fired weapon `w` from `o` along unit direction `d`; `hit` is the player ID an instant-hit weapon struck, or null |
| `{t: "weapon", w}`                                   | Switch to weapon `w` (1 Blaster, 2 Launcher, 3 Beam)                 |
| `{t: "respawn"}`                                     | Click while dead and the 2 s have passed                             |
| `{t: "name", name}`                                  | Guest changed their shown name (1 to 24 characters, tidied by the server) |
| `{t: "pong", c}`                                     | Answer to the server's `ping`, sending its `c` back unchanged       |

The session cookie set by the realm library (sign-in) rides on the WebSocket handshake, so a signed-in player is known from the first message.

## From the server

| Message                                                   | Meaning                                                            |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| `{t: "hello", id, guest, name, player, map_version}`      | This connection's ID, the guest ID to store, the name shown, the Endless Mind player ID or null |
| `{t: "spawn", x, y, z, yaw, hp, armor, weapons, ammo, w}` | You are alive here, facing `yaw`, with these weapons (list of 1 2 3), ammo `{2: n, 3: n}` and current weapon |
| `{t: "you", hp, armor, ammo, weapons, w}`                 | Your own numbers changed (damage, pickup, switch)                  |
| `{t: "push", vx, vy, vz}`                                 | Add this to your velocity now (knockback)                          |
| `{t: "snap", x, y, z}`                                    | Your last `at` was impossible; you are here                        |
| `{t: "die", by, how, x, y, z}`                            | You died: `by` is a player ID or null, `how` is `blaster`, `launcher`, `beam`, `void` or `self` |
| `{t: "state", tick, players, shells, items, events}`      | 20 times a second; see below                                       |
| `{t: "round", phase, ends, scores, limit}`                | `phase` is `play` or `over`; `ends` is the server time (seconds) the phase ends; `scores` as in `state` |
| `{t: "error", text}`                                      | Something refused, in plain words                                  |
| `{t: "bye", text}`                                        | The server is done with this connection and closes it; the page does not reconnect. Sent when the same guest or account connects again (one identity, one seat) and when nothing arrived for 30 s |
| `{t: "ping", c}`                                          | Every 2 s; answer with `pong` at once. The round trip is your `ping` in the scores |

A `state` message has:

- `tick`: the server's tick number, and `now`: the server's clock in seconds (so browsers can draw others a fixed 100 ms in the past, sliding between the two states around that moment).
- `players`: every player in the arena as `[{id, name, bot, x, y, z, yaw, pitch, w, dead, hp, armor, frags, deaths, ping}]`. Dead players keep their last position.
- `shells`: every Launcher shell in flight as `[{id, x, y, z, dx, dy, dz, by}]`.
- `items`: for each item index in `map.json`, whether it is there to take: a list of 0 or 1.
- `events` since the last state: `{e: "frag", by, of, how}` (the kill feed), `{e: "shot", by, w, ox, oy, oz, hx, hy, hz}` (instant-hit shots to draw, with their end point), `{e: "boom", x, y, z}` (a shell exploded), `{e: "take", by, item}` (a pickup taken), `{e: "pad", by}` (someone used a pad; for a sound later).

A `round` message comes after `hello` while a round is running, on `join`, and whenever the phase changes. Ammo in `spawn` and `you` is keyed by weapon number as a string (`{"2": n, "3": n}`), as JSON objects must be.

## Checking shots

An instant hit counts if the claimed target is alive and in the arena, within the weapon's range plus 1 m, and the angle between the reported direction `d` and the line from `o` to the nearest point of the target's upright middle line is at most 6 degrees plus the angle the body's half-width (0.4 m) covers at that distance, and no map box lies on that line. An origin `o` more than 2 m from the shooter's eyes (as the server knows them) is replaced by the eyes. A shot is refused if the weapon is not the current one, has no ammo, or comes before its cooldown (0.08 s early is allowed, for network jitter); switching weapon adds 0.3 s.

## Checking moves

The server accepts an `at` only if, from the last accepted position and velocity, the move is one the movement rules allow: the horizontal distance is within what the run speed allows (an allowance that builds up at 1.25 times the run speed and saves at most 9 m, so a delayed message or a one-second browser stall can catch up; any pad launch or push the server knows about in the last 2 s raises the cap to that launch's speed plus the run speed), and the position does not lie inside a map box. A failed check sends `snap` to the last accepted position. The server does not simulate gravity for people; it trusts `y` within the same allowance using the vertical speed limit of the fastest pad plus 20 m/s. People who fall below `kill_y` die by `void` whatever they report.

Bots are moved by the server with the same rules in Python (`motion.py`), so they can never do what a person cannot.

## HTTP

- `GET /api/summary`: `{now, playing: n, bots: n, round: {phase, ends, scores}}` for the welcome page. `now` is the server's clock, so `ends - now` is the time left; `playing` counts people only; `scores` is `[{id, name, bot, frags, deaths}]`, best first; `ends` is null while nobody is in the arena.
- The realm library answers its own addresses (`endlessmind-card.json`, `join/<code>`, `endlessmind/...`); see `../EveryGame/realm/README.md`.
- Everything else is a file from `app/`: a directory serves its `index.html` (a request without the final slash is redirected to it), and `README.md` files are never served.
