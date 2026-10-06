"""The bots' brain. game.py decides how many bots there are and when they spawn; this file decides
what a living bot does each tick.

`think(bot, game, map, dt)` is called once per tick for every living bot. It may change `bot.yaw` and
`bot.pitch`, call `game.fire(...)` and `game.switch_weapon(...)` as a person's browser would, and keep
anything it likes in `bot.brain` (emptied at each spawn). It returns the movement input for motion.step:
{forward, right, jump}, each as in motion.py; game.py adds the bot's yaw and moves it.

For now a bot stands still where it spawned and turns to face the nearest living enemy. The real brain
(specs/game.md, Bots) comes later.
"""

from __future__ import annotations

import math
import random

# Invented names, so no bot is mistaken for a real person or borrowed from another game.
NAMES = [
    "Brindlewick", "Corvessa", "Dunmore Flick", "Embrel", "Fizzwick", "Gorvane", "Halloway Pim", "Iskra Venn",
    "Jorvel", "Kestrin", "Lumbrick Fett", "Mopple", "Nimbra", "Ostrel", "Pellifer", "Quillon", "Raspen",
    "Snerkle", "Tavish Orr", "Ulmara", "Vexley", "Wobbleton", "Yarrow Kint", "Zelmo",
]


def pick_name(taken: set[str], rng: random.Random) -> str:
    """A bot name nobody in the arena has; a numbered one if every name is in use."""
    free = [n for n in NAMES if n not in taken]
    if free:
        return rng.choice(free)
    n = 2
    while f"{NAMES[0]} {n}" in taken:
        n += 1
    return f"{NAMES[0]} {n}"


def think(bot, game, map, dt: float) -> dict:
    """Stand still and face the nearest living enemy."""
    enemies = [p for p in game.arena() if p is not bot and not p.dead]
    if enemies:
        e = min(enemies, key=lambda p: math.dist((p.x, p.y, p.z), (bot.x, bot.y, bot.z)))
        dx, dy, dz = e.x - bot.x, e.y - bot.y, e.z - bot.z
        bot.yaw = math.atan2(-dx, -dz)
        bot.pitch = math.atan2(dy, math.hypot(dx, dz))
    return {}
