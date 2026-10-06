# The map

One map for now, **Driftyard**, in `app/shared/map.json`, read unchanged by the browser (to draw it and move on it) and by the server (to check moves, fly shells, drive bots). It is an original layout: three tiers of floating platforms over a void, launch pads between them, and a long open sightline for the Beam.

## The layout

Everything is an axis-aligned box. Top surfaces are what players stand on; boxes are about 1 m thick so the underside is visible from below.

- **Lower tier (y = 0)**: the main deck, a wide rectangle about 32 x 20 m, with two short side decks 3 m lower reachable by a drop or a jump back up via pads. The Launcher and small health pickups live here. This is where most fighting happens.
- **Middle tier (y = 6)**: a north island and a south island (about 16 x 8 m each), separated from the main deck by gaps too wide to jump. Launch pads on the main deck's north and south edges throw you up to them, and pads on the islands throw you back. Each island holds a Launcher or ammo and an armor pickup. Two small pillars (4 x 4 m) east and west of the main deck at y = 6 hold armor shards, reachable by pads from the side decks.
- **Top tier (y = 14)**: one small perch (about 6 x 6 m) above the centre of the main deck, holding the Beam. Reached only by a pad on each island that throws you in a long arc over the void; whoever stands up there can see the whole map and is seen by the whole map. A pad on the perch throws you back to the main deck. Anyone who stands still up there is an easy Launcher target from below.
- **Big health** sits on a tiny exposed ledge at the far end of one side deck, so getting it means standing in the open.

The exact coordinates are in the JSON; the layout above is the intent. Change the JSON, not this list, when tuning distances. Keep every gap the pads cross wider than a jump (more than 6 m) so pads are the only way between tiers, and every pad flight must land its passenger on the target platform with a metre to spare when they do nothing in the air.

## map.json

```json
{
  "name": "Driftyard",
  "version": 1,
  "physics": { "gravity": 20, "run": 9, "ground_accel": 60, "friction": 5, "air_accel": 12, "air_cap": 9, "jump": 7.5, "step": 0.5, "jump_buffer": 0.15, "kill_y": -40 },
  "boxes":   [ { "min": [x, y, z], "max": [x, y, z], "color": "#5a6", "name": "main deck" } ],
  "pads":    [ { "min": [x, y, z], "max": [x, y, z], "launch": [vx, vy, vz], "to": [x, y, z], "color": "#fd4" } ],
  "spawns":  [ { "at": [x, y, z], "yaw": 0 } ],
  "items":   [ { "type": "health", "at": [x, y, z] } ],
  "waypoints": { "nodes": [ { "at": [x, y, z] } ], "edges": [ { "from": 0, "to": 1, "how": "walk" } ] }
}
```

- `boxes`: solid, drawn with the given flat color. Order does not matter.
- `pads`: also solid (a thin box on a platform). `launch` is the velocity set when stepped on (once per touch; it fires again only after the player leaves the pad); `to` is the point it is meant to land near, used by the test and by bots. Pads are drawn in their bright `color` and pulse.
- `physics.friction` is a rate: slowing on the ground is `friction` times `run` per second, so a runner stops in about 0.2 s. `jump_buffer` is how long a jump pressed in the air is remembered.
- Waypoint edges are one-way; put both directions in when both work. The gap between the islands and the main deck is 13 m because a drop from 6 m up carries about 11 m.
- `spawns`: feet position and facing.
- `items`: `type` is one of `health`, `bighealth`, `shard`, `armor`, `launcher`, `beam`, `shells`, `charges`. The pickup floats 0.8 m above `at` and spins.
- `waypoints`: for bots. Every platform has nodes near its corners and middle; `how` is `walk` (same surface or step), `jump` (a gap a running jump crosses), or `pad` (walk onto the pad at `from`; the node at `to` is on the landing platform).

## Tests

`tests/test_map.py` loads the JSON and checks: every spawn, item and waypoint node stands on a box or pad (feet within 0.3 m above a top surface, inside its footprint); every pad's `launch` from the pad's centre, under the map's gravity and with no steering, passes over the `to` point's platform at a height where it can land, and lands at least 1 m inside that platform's edges; every `jump` edge is crossable at run speed with one jump; the waypoint graph is connected.
