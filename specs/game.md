# The game

Endless Arena is a free-for-all shooter for a handful of players at once, in a browser, on a small map of floating platforms hanging in space. Fall off and you die. Launch pads throw you between platforms. One weapon sits on the highest perch and rewards a steady aim at long range; another throws slow explosive shells that push whoever they hit, including you, which is how skilled players fly. The first version is plain and flat-shaded: the point is to get the movement, the weapons and the fights feeling right before anything is made pretty.

It is an original game in a well-worn genre (open-source games such as OpenArena, Xonotic and Warsow play the same way). Nothing here copies another game's map layout, names, art, sounds or text. Invented names only.

## Words used here

- **Player**: a person in a browser, or a **bot** (a computer-driven player). Both appear in the same lists, with bots marked.
- **Round**: one match. Ends at the frag limit or the time limit, then a short scoreboard, then a new round.
- **Frag**: one point, for killing another player. Killing yourself (falling, your own shell) counts for nobody: it is only a death.
- **Tick**: one step of the server's clock, 30 times a second.

## Space, units and the player

- Metres and seconds. `x` east, `y` up, `z` south (three.js's handedness: y is up). The map's centre is near the origin.
- A player is an upright cylinder, radius 0.4 m, height 1.8 m, feet at `y`, eyes at `y + 1.6`. Position is the feet. Aim is `yaw` (radians, 0 looking toward -z, increasing to the left as three.js does) and `pitch` (radians, positive up, clamped to about 89 degrees).
- Gravity 20 m/s² downward (a little floaty, on purpose). Falling below `y = -40` kills.

## Movement

Browsers move their own player (`app/play/motion.js`), so controls feel instant; the server checks the result. Both sides use the same numbers, from `app/shared/map.json` under `"physics"`, so neither side hard-codes them.

| Setting                     | Value     |
| --------------------------- | --------- |
| Run speed on the ground     | 9 m/s     |
| Ground acceleration         | 60 m/s²   |
| Ground friction (stop time) | about 0.2 s |
| Air acceleration            | 12 m/s²   |
| Air speed cap per direction | 9 m/s     |
| Jump                        | 7.5 m/s upward, from the ground only |
| Step up                     | up to 0.5 m without jumping |
| Gravity                     | 20 m/s²   |

Keys: W A S D move, the mouse or the arrow keys look (pointer lock for the mouse), left button or Enter fires, Space jumps, 1 2 3 or the wheel change weapon, Tab held shows the scores, F toggles full screen (pressing Play asks for it), M turns sound off or on (remembered in this browser), Esc steps out (see below). The dead view lists all of these keys. A jump pressed while in the air is remembered for 0.15 s so landing and jumping again feels natural.

**Collision** is against the map's boxes only: a player is an axis-aligned box 0.8 x 1.8 x 0.8 for this purpose. Resolve each axis separately: move in x, push out; move in y, push out (and note whether standing on something); move in z, push out. Players pass through each other.

**Launch pads** are boxes in the map with a `launch` velocity. Standing on one (feet within 0.1 m above its top and inside its footprint) sets the player's velocity to that vector at once. Each pad is built so that a player who does nothing lands on its target platform; the pad's `to` point is the aim and a test checks the flight.

**Knockback** is applied by the server (it decides hits), sent as an impulse the browser adds to its velocity.

## Weapons

Everyone spawns with the Blaster. The others are picked up. Switching takes 0.3 s. Damage is checked by the server.

| Weapon   | Fire                                               | Damage | Rate   | Ammo (pickup / max) |
| -------- | -------------------------------------------------- | ------ | ------ | ------------------- |
| Blaster  | Instant hit, 2 degrees of spread, range 60 m       | 8      | 8 per s | endless            |
| Launcher | Shell, 24 m/s, straight (no gravity), explodes on contact or after 4 s | 90 direct; splash up to 90 within 3.5 m falling to 0 at the edge | 1 per 0.8 s | 10 / 25 |
| Beam     | Instant hit, no spread, range 200 m, visible trail for 0.4 s | 85  | 1 per 1.5 s | 10 / 20 |

- Instant-hit weapons: the browser does the hit test against the players it sees (what you see is what you hit) and reports who it hit; the server believes it only if the claimed target is alive, within range, and within 6 degrees of the shooter's reported aim from the shooter's reported position, given the positions the server knows. Otherwise the shot is a miss.
- Shells are simulated by the server and drawn by browsers from the state messages. Hits are tested each tick against map boxes and player cylinders, including the shooter's own cylinder after the first 0.1 s of flight.
- Splash reaches a player only if a straight line from the explosion to their feet, middle or head is clear of map boxes. Distance for falloff is measured to the nearest point of the body.
- Knockback: a direct Launcher hit or splash pushes the victim away from the explosion at up to 14 m/s (scaled by splash falloff), with an extra 3 m/s upward so pushes lift. The shooter takes half damage from their own splash but full knockback. Beam hits push 4 m/s along the shot. Blaster hits do not push.
- Damage to a player with armor: armor takes two thirds and the player one third, until the armor is gone.

## Health, armor and pickups

Health 100 at spawn, at most 200; above 100 it decays by 1 per second down to 100. Armor 0 at spawn, at most 200, and above 100 it decays the same way.

| Pickup       | Gives                 | Respawns after |
| ------------ | --------------------- | -------------- |
| Health       | +25 health (to 100)   | 20 s           |
| Big health   | +100 health (to 200)  | 35 s           |
| Armor shard  | +25 armor (to 200)    | 25 s           |
| Armor        | +75 armor (to 200)    | 30 s           |
| Launcher     | the weapon, +10 shells | 20 s          |
| Beam         | the weapon, +10 charges | 25 s         |
| Shells       | +5 shells             | 20 s           |
| Charges      | +5 charges            | 20 s           |

Each pickup looks like what it is, bobbing and spinning over a glowing ring of its color, with its name shown above it within about 8 m: health is a white medkit with a red cross (Big health twice the size, with a green glow), armor is a blue metal shield with a star emblem (the shard smaller), the Launcher and Beam are the gun models themselves, and Shells and Charges are ammo clips, orange and purple.

A pickup is taken by walking into it (within 1 m of its point, feet within 1.5 m of its height). A pickup that would give nothing (full health, full ammo) is not taken.

## Spawning, dying and the round

- Pressing Play puts you in the arena dead: the dead view shows the scores and the keys, and a click or Enter goes in. Esc while fighting steps out the same way (the mouse is let go, you are dead, nobody scores a frag or a death) and a click goes back in at once.
- A dead player respawns by clicking, once 2 s have passed since death, at the spawn point farthest from any living enemy (with a little randomness among the top three). Bots respawn by the bot rule below.
- Falling into the void: if someone damaged you in the last 4 s, it is their frag; otherwise it counts for nobody. Your own shell killing you counts for nobody either; both are only deaths.
- Round: free-for-all, ends at 20 frags or 8 minutes, whichever first. Then 8 s of scoreboard (nobody moves or shoots, the page shows the standings), then everything resets: scores, pickups, positions.
- Scores show frags, deaths and ping, bots marked.

## Bots

A bot is a player the server drives. Bots exist so a lone player has a fight: with 1 person fighting there are 2 bots, with 2 people 1 bot, with 3 or more none. Precisely: wanted bots = max(0, 3 - people fighting), where a person counts as fighting while alive and for 15 s after dying; someone who stays dead and watches does not count, so five dead watchers and one live player still get 2 bots. Every tick, if living bots < wanted, one bot is added or a dead one respawned. A living bot is never removed because people joined: it simply does not respawn once living bots >= wanted. A bot who stays dead is dropped from the lists at the next round. When the last person leaves, the bots leave too and the arena sleeps (no round runs) until someone presses Play, which starts a fresh round.

Bots follow the map's waypoint graph (`"waypoints"`: nodes and edges, where an edge may be a walk, a jump across a gap, or a pad). Each tick a bot:

1. Picks a goal: the nearest visible enemy if it has a weapon better than the Blaster or ammo, otherwise the nearest useful pickup (a weapon it lacks, health when below 60, armor), otherwise a wander target.
2. Walks the graph toward the goal with the same movement rules as a person (it moves by the same `motion` code, in Python).
3. Shoots at a visible enemy with the best weapon it has: reaction delay 0.25 s, aim error up to 4 degrees that shrinks the longer the target stays visible, and with the Launcher it aims at the feet of a grounded target.

Bots have invented names from a fixed list (`server/arena_server/bots.py`). Bots are fragile: they spawn with 1 health and no armor, so any hit kills them, and health and armor pickups do nothing for them (they leave those alone). Their aim and movement are tuned so a new person can win by landing one shot before the bot does.

## Signing in and records

Guests play at once with a random name. Signing in with Endless Mind (QR code, `endlessmind/signin.js` from the realm library in `../EveryGame`) gives the player their own name and lets them claim records. Records offered: winning a round with at least 2 real players in it; reaching 100, 500 and every 500 frags after that in total here. The realm keeps its secret phrase and data in `data/` (`realm-secret.txt`, `realm-data.json`), and the server keeps each player's lifetime frags in `data/players.json` and the names guests chose in `data/guests.json`.

## Not in the first version

Music, touch controls, teams, more maps, spectating, chat. These come after the fights feel right.
