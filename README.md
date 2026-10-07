# Endless Arena

A fast free-for-all shooter in the browser, on floating platforms hanging in space, at **<https://arena.endlessmind.com/>**. Fall off and you die. Launch pads throw you between platforms. Pick up the Beam on the top perch to snipe the whole map, or the Launcher to blast people off the edge and to fly. First to 20 frags wins the round.

Play alone and two bots fight you; with two people there is one bot; with three or more, none (bots already in the fight stay until they die). Guests play right away. Signing in with Endless Mind keeps your name and earns records for winning rounds and frag milestones.

It is an original game in a well-worn genre, built plain first: flat-shaded platforms and no textures, models, sound or music until the fights feel right. The map, names and art are our own.

## Controls

W A S D move, the mouse or the arrow keys look (click the page to capture the mouse), left button or Enter fires, Space jumps, 1 2 3 or the mouse wheel change weapon, Tab shows the scores. A computer with a keyboard is needed for now.

## How it is made

One Python program runs everything, forever: it serves the pages and keeps a WebSocket to every player, flies the shells, decides every hit, drives the bots, runs the rounds and signs records. Each browser moves its own player, so controls feel instant, and the server checks every move.

```text
app/
  welcome/     what the game is, Play, who is in the arena now
  play/        the game: three.js scene, movement, weapons, HUD, scores
  shared/      map.json (the map, read by browser and server), base styles
  vendor/      three.js, pinned (vendor/README.md)
server/arena_server/
  app.py       serving the pages, the realm, /api/summary, /ws, the clock that runs the game
  game.py      the rules: players, weapons, shells, pickups, deaths, rounds
  motion.py    movement rules in Python, for bots and for checking people's moves
  bots.py      the bots
  mapdata.py   loading map.json and collision against its boxes
specs/         the game, the map, the messages between browser and server, deployment
tests/         pytest for the server; the map test
deploy/        the systemd unit and the Caddy block
```

Start with [specs/game.md](specs/game.md), then [specs/map.md](specs/map.md) and [specs/protocol.md](specs/protocol.md). Deployment is in [specs/deployment.md](specs/deployment.md).

## Development

```sh
uv sync                        # needs ../EveryGame checked out beside this repo (realm-py)
uv run arena-server            # http://localhost:8780/  (PORT, HOST, BASE, DATA_ROOT change it)
uv run pytest
```

Plain HTML, CSS and ES modules; no build step. Files under `app/` are served as-is, and all URLs in pages are page-relative. Keep data and secrets in `data/`, outside `app/` and Git.
