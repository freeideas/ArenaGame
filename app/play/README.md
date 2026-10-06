# play/

The game itself. The rules are in [../../specs/game.md](../../specs/game.md) and the messages in [../../specs/protocol.md](../../specs/protocol.md). Plain ES modules, no build step; the only library is three.js from `../vendor/`.

| File         | What it does                                                                                   |
| ------------ | ---------------------------------------------------------------------------------------------- |
| `index.html` | The 3D canvas, the HUD elements, the scoreboard, the "you died" overlay and the Play card       |
| `play.css`   | Styles, on top of `../shared/base.css`                                                         |
| `play.js`    | Loads the map, moves you every frame, keys and mouse, firing and hit tests, server messages     |
| `motion.js`  | The movement rules; the same code as `server/arena_server/motion.py` (tests compare the two)    |
| `view.js`    | The three.js scene: map, pads, pickups, other players, shells, shots, explosions, stars        |
| `net.js`     | The WebSocket at the site's `/ws`, hello with the stored guest ID, reconnecting with a wait     |
| `hud.js`     | The HUD as plain DOM: health, armor, weapons, kill feed, clock, scores, overlays               |

How it works:

- Your own player is moved here with `motion.js` every animation frame (frames longer than 0.05 s are split), and its position goes to the server as `at` 20 times a second. `push` adds to your velocity; `snap` puts you back where the server last agreed.
- Other players and shells are drawn 100 ms in the past, sliding between the two `state` messages around that moment. The server's `now` in each state is turned into local time by the smallest gap seen.
- Instant-hit weapons (Blaster, Beam) are tested here: a ray from your eyes against the upright cylinders of the players as they are drawn, nearest first, stopped by map boxes. The player hit goes in the `fire` message; the server checks it. Launcher shells are flown by the server.
- The guest ID is kept in `localStorage` under `arena-guest`.

Trying it without a server: serve `app/` with any static file server (for example `deno run -A jsr:@std/http/file-server app --port 8781`) and open `http://localhost:8781/play/?local`. You get your own player on the map with all three weapons; pads and jumps work, falling off shows the death overlay, and shots are drawn but hit nobody.

`window.arena` is a small handle for browser tests and the console: `body`, `alive`, `view`, `others`, `place(x, y, z, yaw)`, `look(yaw, pitch)`, `fire()`, `trace()`, `receive(message)`. While connected, moving yourself with it only earns a `snap`.
