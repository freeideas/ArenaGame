# play/

The game itself. The rules are in [../../specs/game.md](../../specs/game.md) and the messages in [../../specs/protocol.md](../../specs/protocol.md). Plain ES modules, no build step; the only library is three.js from `../vendor/`.

| File         | What it does                                                                                   |
| ------------ | ---------------------------------------------------------------------------------------------- |
| `index.html` | The 3D canvas, the HUD elements, the scoreboard, the "you died" overlay and the Play card       |
| `play.css`   | Styles, on top of `../shared/base.css`                                                         |
| `play.js`    | Loads the map, moves you every frame, keys and mouse, firing and hit tests, server messages     |
| `motion.js`  | The movement rules; the same code as `server/arena_server/motion.py` (tests compare the two)    |
| `view.js`    | The three.js scene: map, pads, pickups drawn as what they are, players, shots, sky, held gun |
| `net.js`     | The WebSocket at the site's `/ws`, hello with the stored guest ID, reconnecting with a wait     |
| `hud.js`     | The HUD as plain DOM: health, armor, weapons, kill feed, clock, scores, overlays               |
| `sound.js`   | Sound effects (Web Audio): loads `../shared/sounds/` once, places sounds in 3D, M mutes        |

How it works:

- Your own player is moved here with `motion.js` every animation frame (frames longer than 0.05 s are split), and its position goes to the server as `at` 20 times a second. `push` adds to your velocity; `snap` puts you back where the server last agreed.
- Other players and shells are drawn 100 ms in the past, sliding between the two `state` messages around that moment. The server's `now` in each state is turned into local time by the smallest gap seen.
- Instant-hit weapons (Blaster, Beam) are tested here: a ray from your eyes against the upright cylinders of the players as they are drawn, nearest first, stopped by map boxes. The player hit goes in the `fire` message; the server checks it. Launcher shells are flown by the server.
- The guest ID is kept in `localStorage` under `arena-guest`.
- Surfaces use the textures in `../shared/textures/`, chosen per box by `material` in the map (see [../../specs/map.md](../../specs/map.md)). One sun casts shadows; add `?plain` to the page address (or `&plain` after `?local`) to turn shadows off on a weak machine.
- Weapons are Kenney's Blaster Kit models from `../shared/models/` (Blaster `blaster-h` with its palette turned light blue, Launcher `blaster-k`, Beam `blaster-f`); the Launcher and Beam pickups reuse them, and Shells and Charges use the kit's `clip-large` and `clip-small`, tinted. The one you hold is drawn in its own small scene after the world, with the depth cleared, so it never pokes into walls.
- Sounds: `sound.js` makes its AudioContext on the first click or key press (browsers block audio before that). Sounds with a place use a PannerNode; the listener follows the camera every frame. Footsteps and landings come from your own movement, the rest from your own actions and the `state` events (shot, boom, take, pad, frag) and new shells.

Trying it without a server: serve `app/` with any static file server (for example `deno run -A jsr:@std/http/file-server app --port 8781`) and open `http://localhost:8781/play/?local`. You get your own player on the map with all three weapons; pads and jumps work, falling off shows the death overlay, and shots are drawn but hit nobody.

`window.arena` is a small handle for browser tests and the console: `body`, `alive`, `view`, `others`, `place(x, y, z, yaw)`, `look(yaw, pitch)`, `fire()`, `trace()`, `receive(message)`, `sounds` (how many sound files have been decoded; 0 until the first click or key press, since browsers allow audio only after one). While connected, moving yourself with it only earns a `snap`.
