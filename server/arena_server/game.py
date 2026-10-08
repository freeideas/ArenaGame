"""The rules of Endless Arena, kept free of networking so tests can drive them with a made-up clock.

One arena, one round at a time. app.py calls `tick(now, dt)` 30 times a second and `broadcast(now)`
20 times a second, and calls `join`, `enter`, `report_at`, `fire`, `switch_weapon`, `respawn`,
`rename`, `pong` and `leave` as messages arrive. Every message to a player goes through the `send`
function given to `join`; bots get a `send` that does nothing.

Browsers move their own players and report where they are; the server checks each report (see
specs/protocol.md, Checking moves), flies the shells, decides every hit and runs the round. Bots are
moved here with the same movement rules (motion.py), steered by bots.think.

The rules are in specs/game.md. Every weapon, pickup and timing number is in the tables just below.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from endlessmind import tidy_name as realm_tidy

from . import bots, motion
from .mapdata import MAP, PLAYER_HALF, PLAYER_HEIGHT, MapData

# --- Tuning: every weapon and pickup number ------------------------------------------------------

BLASTER, LAUNCHER, BEAM = 1, 2, 3
WEAPONS = {
    # cooldown: seconds between shots; spread is drawn by the browser, the server only checks the aim.
    BLASTER: {"name": "blaster", "hitscan": True, "damage": 8, "cooldown": 1 / 8, "range": 60, "spread": 2,
              "push": 0, "ammo_max": None},
    LAUNCHER: {"name": "launcher", "hitscan": False, "damage": 90, "cooldown": 0.8, "speed": 24, "life": 4,
               "splash": 90, "radius": 3.5, "push": 14, "lift": 3, "ammo_max": 25},
    BEAM: {"name": "beam", "hitscan": True, "damage": 85, "cooldown": 1.5, "range": 200, "push": 4,
           "ammo_max": 20},
}
ITEMS = {
    # health/armor: amount and the most it can bring you to; weapon: the weapon and ammo; ammo: for which weapon.
    "health": {"health": 25, "upto": 100, "respawn": 20},
    "bighealth": {"health": 100, "upto": 200, "respawn": 35},
    "shard": {"armor": 25, "upto": 200, "respawn": 25},
    "armor": {"armor": 75, "upto": 200, "respawn": 30},
    "launcher": {"weapon": LAUNCHER, "ammo": 10, "respawn": 20},
    "beam": {"weapon": BEAM, "ammo": 10, "respawn": 25},
    "shells": {"ammo_for": LAUNCHER, "ammo": 5, "respawn": 20},
    "charges": {"ammo_for": BEAM, "ammo": 5, "respawn": 20},
}
START_HEALTH = 100
MAX_HEALTH = 200
MAX_ARMOR = 200
DECAY_ABOVE = 100        # health and armor above this lose 1 per second
ARMOR_SHARE = 2 / 3      # armor takes this share of damage while it lasts
SELF_SPLASH = 0.5        # the shooter takes this share of their own splash damage
SWITCH_TIME = 0.3        # seconds to change weapon
FIRE_SLACK = 0.08        # a shot may arrive this early, for network jitter
AIM_TOLERANCE = 6        # degrees between the reported aim and the target, for instant hits
RANGE_SLACK = 1.0        # metres past a weapon's range an instant hit may still count
ORIGIN_SLACK = 2.0       # metres a shot's reported origin may be from the shooter's eyes
SHELL_ARM = 0.1          # a shell can hit its own shooter after this many seconds of flight
EYE = 1.6
PICKUP_REACH = 1.0       # metres across, from the item's point to the feet
PICKUP_HEIGHT = 1.5      # metres up or down, from the item's point to the feet
RESPAWN_DELAY = 2.0
VOID_CREDIT = 4.0        # seconds after being hurt that a fall still credits the attacker
FRAG_LIMIT = 20
ROUND_SECONDS = 8 * 60
OVER_SECONDS = 8
WANTED_BOTS = 3          # bots wanted = max(0, WANTED_BOTS - people fighting)
FIGHTING_GRACE = 15.0    # a dead person still counts as fighting this long, so dying does not add a bot
BOT_HEALTH = 1           # bots die to any hit, and health and armor pickups do nothing for them
ARENA_MAX = 16
NAME_MAX = 24
SAVE_EVERY = 5.0         # seconds between writes of the lasting store
PING_EVERY = 2.0
SILENT_LIMIT = 30.0      # a connection that sends nothing for this long is dropped
MILESTONES = (100, 500)  # lifetime frags; after 500, every 500

# Checking moves (specs/protocol.md)
MOVE_SLACK = 1.25        # the allowance builds at this times the run speed
MOVE_SAVE = 9.0          # metres of allowance that can be saved up: a one-second browser stall while running
FAST_SECONDS = 2.0       # a pad launch or push raises the speed cap for this long
VERTICAL_EXTRA = 20.0    # vertical speed cap: the fastest pad's upward speed plus this

HOW = {BLASTER: "blaster", LAUNCHER: "launcher", BEAM: "beam"}


# --- Geometry ------------------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def segment_cylinder(a, b, cx, cz, y0, y1, r=PLAYER_HALF) -> float | None:
    """Fraction 0..1 along a->b where the segment first touches the upright cylinder at (cx, cz),
    radius r, from y0 to y1; None if it misses. A segment starting inside hits at 0."""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    fx, fz = a[0] - cx, a[2] - cz
    lo, hi = 0.0, 1.0
    qa = dx * dx + dz * dz
    qc = fx * fx + fz * fz - r * r
    if qa < 1e-12:
        if qc > 0:
            return None
    else:
        qb = 2 * (fx * dx + fz * dz)
        disc = qb * qb - 4 * qa * qc
        if disc < 0:
            return None
        s = math.sqrt(disc)
        lo, hi = max(lo, (-qb - s) / (2 * qa)), min(hi, (-qb + s) / (2 * qa))
    if abs(dy) < 1e-12:
        if not (y0 <= a[1] <= y1):
            return None
    else:
        u, v = (y0 - a[1]) / dy, (y1 - a[1]) / dy
        if u > v:
            u, v = v, u
        lo, hi = max(lo, u), min(hi, v)
    return lo if lo <= hi else None


def axis_point(o, d, x, y, z):
    """The point on a player's upright axis (feet at x, y, z) closest to the ray from o along unit d,
    kept a little inside the body so it is never on the floor."""
    w = (o[0] - x, o[1] - y, o[2] - z)
    b = d[1]
    denom = 1 - b * b
    if denom < 1e-9:
        s = w[1]
    else:
        s = (w[1] - b * _dot(d, w)) / denom
    s = min(PLAYER_HEIGHT - 0.1, max(0.1, s))
    return (x, y + s, z)


def aim_from(yaw: float, pitch: float):
    """The unit direction for a yaw and pitch (yaw 0 looks toward -z, positive turns left)."""
    cp = math.cos(pitch)
    return (-math.sin(yaw) * cp, math.sin(pitch), -math.cos(yaw) * cp)


# --- Players -------------------------------------------------------------------------------------

def _nothing(_message: dict) -> None:
    pass


@dataclass
class Player:
    id: str
    name: str
    send: Callable[[dict], None] = _nothing
    bot: bool = False
    guest: str | None = None      # the browser's lasting guest ID
    account: str | None = None    # the Endless Mind player ID when signed in
    in_arena: bool = False
    dead: bool = True
    died_at: float = -1e9
    ready_at: float = -1e9        # when a click may bring the player back
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    hp: int = START_HEALTH
    armor: int = 0
    weapons: set = field(default_factory=lambda: {BLASTER})
    ammo: dict = field(default_factory=lambda: {LAUNCHER: 0, BEAM: 0})
    w: int = BLASTER
    ready: float = 0.0            # when the next shot may be fired
    decay: float = 0.0            # seconds of decay saved up (health and armor above 100)
    frags: int = 0
    deaths: int = 0
    ping: int = 0
    heard: float = 0.0    # when the browser last sent anything
    bye: str | None = None  # set when the server is done with this connection, with the reason
    hurt_by: str | None = None    # who damaged this player last, and when
    hurt_at: float = -1e9
    # Checking a person's moves
    seq: int = -1
    at_time: float = 0.0
    budget: float = 0.0
    vbudget: float = 0.0
    fast_until: float = -1e9
    fast_speed: float = 0.0       # horizontal speed of recent launches and pushes
    fast_vy: float = 0.0
    on_pad: int = -1
    # A bot's movement state (motion.py) and whatever its brain keeps
    motion: dict | None = None
    brain: dict = field(default_factory=dict)

    @property
    def eye(self):
        return (self.x, self.y + EYE, self.z)

    def numbers(self) -> dict:
        return {"hp": self.hp, "armor": self.armor, "ammo": {str(k): v for k, v in self.ammo.items()},
                "weapons": sorted(self.weapons), "w": self.w}


@dataclass
class Shell:
    id: int
    x: float
    y: float
    z: float
    d: tuple
    by: Player
    born: float


class Store:
    """What lasts between runs of the server: each signed-in player's lifetime frags, and the names
    guests chose. app.py's FileStore writes them to files."""

    def __init__(self) -> None:
        self.players: dict[str, dict] = {}
        self.guests: dict[str, dict] = {}

    def saved(self) -> None:
        """Called after changes (at most every SAVE_EVERY seconds); app.py replaces this with writing files."""


# --- The game ------------------------------------------------------------------------------------

class Game:
    def __init__(self, store: Store | None = None, map: MapData = MAP, rng: random.Random | None = None,
                 on_record: Callable[[str, str, dict], None] | None = None) -> None:
        self.store = store or Store()
        self.map = map
        self.rng = rng or random.Random()
        self.on_record = on_record or (lambda player, text, data: None)
        self.players: dict[str, Player] = {}   # every connection and every bot
        self.shells: list[Shell] = []
        self.events: list[dict] = []
        self.items_back: list[float] = [0.0] * len(map.items)   # when each item is there again (0: now)
        self.phase = "play"
        self.ends: float | None = None          # None while nobody is in the arena
        self.tick_count = 0
        self.now = 0.0
        self.next_shell = 1
        self.next_bot = 1
        self.dirty = False
        self.saved_at = 0.0
        self.pinged_at = -1e9
        self.max_pad_vy = max((p.launch[1] for p in map.pads), default=0.0)

    # --- who is here ---------------------------------------------------------------------------

    def arena(self) -> list[Player]:
        return [p for p in self.players.values() if p.in_arena]

    def people(self) -> list[Player]:
        return [p for p in self.players.values() if p.in_arena and not p.bot]

    def bots(self) -> list[Player]:
        return [p for p in self.players.values() if p.in_arena and p.bot]

    def scores(self, ping: bool = False) -> list[dict]:
        rows = sorted(self.arena(), key=lambda p: (-p.frags, p.deaths, p.name))
        return [{"id": p.id, "name": p.name, "bot": p.bot, "frags": p.frags, "deaths": p.deaths,
                 **({"ping": p.ping} if ping else {})} for p in rows]

    # --- connections -----------------------------------------------------------------------------

    def join(self, id: str, guest: str, send: Callable[[dict], None], now: float,
             account: str | None = None, name: str | None = None) -> Player:
        """A browser said hello. `account` is the signed-in Endless Mind player, with `name` their
        name; guests get the name they chose before, or `name`."""
        chosen = (self.store.guests.get(guest) or {}).get("name") if not account else None
        # One identity, one seat: an older connection with the same account or guest ID (another tab,
        # or a socket whose closing never reached us) is dropped, so nobody appears twice.
        for old in list(self.players.values()):
            if old.bot or old.bye:
                continue
            if (account and old.account == account) or (not account and old.guest == guest):
                self.drop(old, "You joined from another tab or window, so this one is done.")
        player = Player(id, chosen or name or "Guest", send, guest=guest, account=account)
        player.heard = now
        self.players[id] = player
        send({"t": "hello", "id": id, "guest": guest, "name": player.name, "player": account,
              "map_version": self.map.version})
        if self.ends is not None:
            send(self.round_message())
        return player

    def drop(self, player: Player, why: str) -> None:
        """Tell a browser we are done with it and take its player out; the socket closes after `bye`."""
        player.bye = why
        player.send({"t": "bye", "text": why})
        self.leave(player)

    def heard_from(self, player: Player, now: float) -> None:
        player.heard = now

    def leave(self, player: Player) -> None:
        self.players.pop(player.id, None)
        player.in_arena = False
        if not self.people():
            # Nobody left to play with: the bots go and the arena sleeps until someone enters.
            for b in self.bots():
                self.players.pop(b.id, None)
            self.shells.clear()
            self.events.clear()
            self.phase, self.ends = "play", None

    def enter(self, player: Player, now: float) -> None:
        """Play pressed: into the arena, dead at a spawn point until the first click (the scores and keys show)."""
        if player.in_arena:
            return
        if len(self.arena()) >= ARENA_MAX:
            player.send({"t": "error", "text": "The arena is full right now. Try again in a minute."})
            return
        first = not self.people()
        player.in_arena = True
        player.frags = player.deaths = 0
        if first:
            self.start_round(now)
        else:
            self.spawn(player, now)
            player.send(self.round_message())
        self.step_out(player, now, "start")

    def rename(self, player: Player, name: object) -> None:
        if player.account:
            player.send({"t": "error", "text": "Your name comes from your Endless Mind sign-in."})
            return
        tidy = tidy_name(name)
        if not tidy:
            player.send({"t": "error", "text": "A name needs 1 to 24 letters or other characters."})
            return
        player.name = tidy
        if player.guest:
            self.store.guests[player.guest] = {"name": tidy}
            self.dirty = True

    def pong(self, player: Player, c: object, now: float) -> None:
        if isinstance(c, (int, float)) and 0 <= now - c < 30:
            player.ping = round((now - c) * 1000)

    # --- spawning --------------------------------------------------------------------------------

    def pick_spawn(self, player: Player) -> dict:
        """The spawn farthest from any living enemy, chosen at random among the best three."""
        enemies = [p for p in self.arena() if p is not player and not p.dead]

        def room(s):
            x, y, z = s["at"]
            return min((math.dist((x, y, z), (e.x, e.y, e.z)) for e in enemies), default=0.0)

        best = sorted(self.map.spawns, key=room, reverse=True)[:3]
        return self.rng.choice(best)

    def spawn(self, player: Player, now: float) -> None:
        s = self.pick_spawn(player)
        player.x, player.y, player.z = (float(v) for v in s["at"])
        player.yaw, player.pitch = float(s.get("yaw", 0.0)), 0.0
        player.dead = False
        player.hp, player.armor, player.decay = (BOT_HEALTH if player.bot else START_HEALTH), 0, 0.0
        player.weapons, player.ammo, player.w = {BLASTER}, {LAUNCHER: 0, BEAM: 0}, BLASTER
        player.ready = now
        player.hurt_by, player.hurt_at = None, -1e9
        player.at_time, player.budget, player.vbudget = now, MOVE_SAVE, MOVE_SAVE
        player.fast_until, player.fast_speed, player.fast_vy, player.on_pad = -1e9, 0.0, 0.0, -1
        if player.bot:
            player.motion = motion.new_state(player.x, player.y, player.z)
            player.brain = {}
        player.send({"t": "spawn", "x": player.x, "y": player.y, "z": player.z, "yaw": player.yaw,
                     **player.numbers()})

    def respawn(self, player: Player, now: float) -> None:
        """Click while dead: 2 s after a death, at once after stepping out."""
        if player.in_arena and player.dead and self.phase == "play" and now >= player.ready_at:
            self.spawn(player, now)

    def step_out(self, player: Player, now: float, how: str) -> None:
        """Dead without a death counted and with no credit to anyone: at the start, or Esc pressed (`out`).
        The player stays where they were and may come back with a click at once."""
        if not player.in_arena or player.dead:
            return
        player.dead, player.died_at, player.ready_at, player.hp = True, now, now, 0
        player.send({"t": "die", "by": None, "how": how, "x": player.x, "y": player.y, "z": player.z})

    # --- moves -----------------------------------------------------------------------------------

    def report_at(self, player: Player, m: dict, now: float) -> None:
        """A browser says where its player is: accept it, or send `snap` back to the last accepted spot."""
        if not player.in_arena or player.dead or self.phase != "play" or player.bot:
            return
        try:
            x, y, z = float(m["x"]), float(m["y"]), float(m["z"])
            yaw, pitch = float(m.get("yaw", 0.0)), float(m.get("pitch", 0.0))
            seq = int(m.get("seq", 0))
        except (KeyError, TypeError, ValueError):
            return
        if not all(math.isfinite(v) for v in (x, y, z, yaw, pitch)):
            return self.snap(player)
        if seq <= player.seq:
            return
        player.seq = seq
        if y < self.map.physics["kill_y"]:
            player.x, player.y, player.z = x, y, z
            return self.void(player, now)
        elapsed = max(0.0, now - player.at_time)
        player.at_time = now
        near = self.near_pad(player.x, player.y, player.z)
        if near is None:
            near = self.near_pad(x, y, z)
        if near is not None:
            launch = self.map.pads[near].launch
            self.fast(player, math.hypot(launch[0], launch[2]), launch[1], now, add=False)
        run = self.map.physics["run"]
        cap = MOVE_SLACK * run
        vcap = self.max_pad_vy + VERTICAL_EXTRA
        if now < player.fast_until:
            cap = max(cap, player.fast_speed + run)
            vcap += player.fast_vy
        player.budget = min(player.budget + cap * elapsed, max(MOVE_SAVE, cap * 0.25))
        player.vbudget = min(player.vbudget + vcap * elapsed, max(MOVE_SAVE, vcap * 0.25))
        horizontal = math.hypot(x - player.x, z - player.z)
        vertical = abs(y - player.y)
        if horizontal > player.budget + 0.05 or vertical > player.vbudget + 0.05 or self.map.player_overlaps(x, y, z):
            return self.snap(player)
        player.budget -= horizontal
        player.vbudget -= vertical
        player.x, player.y, player.z, player.yaw = x, y, z, yaw
        player.pitch = max(-1.56, min(1.56, pitch))
        pad = self.on_pad(x, y, z)
        if pad >= 0 and pad != player.on_pad:
            self.events.append({"e": "pad", "by": player.id})
        player.on_pad = pad

    def snap(self, player: Player) -> None:
        player.send({"t": "snap", "x": player.x, "y": player.y, "z": player.z})

    def on_pad(self, x, y, z) -> int:
        for i, pad in enumerate(self.map.pads):
            if pad.min[0] <= x <= pad.max[0] and pad.min[2] <= z <= pad.max[2] and pad.max[1] - 0.01 <= y <= pad.max[1] + motion.PAD_REACH:
                return i
        return -1

    def near_pad(self, x, y, z) -> int | None:
        """A pad within a metre sideways and a little below to three metres above these feet: the
        player may have been launched between two reports."""
        for i, pad in enumerate(self.map.pads):
            if (pad.min[0] - 1 <= x <= pad.max[0] + 1 and pad.min[2] - 1 <= z <= pad.max[2] + 1
                    and pad.max[1] - 0.5 <= y <= pad.max[1] + 3):
                return i
        return None

    def fast(self, player: Player, speed: float, vy: float, now: float, add: bool = True) -> None:
        """A launch or push the server knows about: raise this player's speed cap for a while."""
        if add and now < player.fast_until:
            player.fast_speed = min(60.0, player.fast_speed + speed)
            player.fast_vy = min(60.0, player.fast_vy + max(0.0, vy))
        else:
            player.fast_speed = max(speed, player.fast_speed if now < player.fast_until else 0.0)
            player.fast_vy = max(max(0.0, vy), player.fast_vy if now < player.fast_until else 0.0)
        player.fast_until = now + FAST_SECONDS

    def push(self, player: Player, v, now: float) -> None:
        """Knockback: add v to the player's velocity."""
        if player.bot and player.motion is not None:
            s = player.motion
            s["vx"], s["vy"], s["vz"] = s["vx"] + v[0], s["vy"] + v[1], s["vz"] + v[2]
            if v[1] > 0:
                s["ground"] = False
        else:
            player.send({"t": "push", "vx": round(v[0], 3), "vy": round(v[1], 3), "vz": round(v[2], 3)})
        self.fast(player, math.hypot(v[0], v[2]), v[1], now)

    # --- weapons ---------------------------------------------------------------------------------

    def switch_weapon(self, player: Player, w: object, now: float) -> None:
        if player.dead or w not in player.weapons or w == player.w:
            return
        player.w = w
        player.ready = max(player.ready, now + SWITCH_TIME)
        player.send({"t": "you", **player.numbers()})

    def fire(self, player: Player, w: object, o, d, hit: str | None, now: float) -> None:
        """Fired weapon w from o along d; `hit` is the player an instant-hit weapon struck, or None."""
        if not player.in_arena or player.dead or self.phase != "play" or w != player.w or w not in player.weapons:
            return
        try:
            o = tuple(float(v) for v in o)
            d = tuple(float(v) for v in d)
        except (TypeError, ValueError):
            return
        if len(o) != 3 or len(d) != 3 or not all(math.isfinite(v) for v in (*o, *d)):
            return
        n = _len(d)
        if n < 1e-6:
            return
        d = (d[0] / n, d[1] / n, d[2] / n)
        if math.dist(o, player.eye) > ORIGIN_SLACK:
            o = player.eye
        spec = WEAPONS[w]
        if now < player.ready - FIRE_SLACK:
            return
        if spec["ammo_max"] is not None:
            if player.ammo[w] <= 0:
                return
            player.ammo[w] -= 1
            player.send({"t": "you", **player.numbers()})
        player.ready = max(player.ready, now) + spec["cooldown"]
        if not spec["hitscan"]:
            self.shells.append(Shell(self.next_shell, *o, d, player, now))
            self.next_shell += 1
            return
        target = self.players.get(hit) if isinstance(hit, str) else None
        point = self.check_hit(player, w, o, d, target)
        if point is None:
            end = tuple(o[i] + d[i] * spec["range"] for i in range(3))
            stop = self.map.segment_hit(o, end)
            end = stop or end
        else:
            end = point
        self.events.append({"e": "shot", "by": player.id, "w": w, "ox": round(o[0], 3), "oy": round(o[1], 3),
                            "oz": round(o[2], 3), "hx": round(end[0], 3), "hy": round(end[1], 3), "hz": round(end[2], 3)})
        if point is not None:
            if spec["push"]:
                self.push(target, tuple(v * spec["push"] for v in d), now)
            self.damage(target, spec["damage"], player, HOW[w], now)

    def check_hit(self, shooter: Player, w: int, o, d, target: Player | None):
        """Believe a claimed instant hit only if the target is alive, in range, within AIM_TOLERANCE
        degrees of the aim (plus the body's width) and not behind a map box. Returns the hit point or None."""
        if target is None or target is shooter or not target.in_arena or target.dead:
            return None
        q = axis_point(o, d, target.x, target.y, target.z)
        to = _sub(q, o)
        dist = _len(to)
        if dist > WEAPONS[w]["range"] + RANGE_SLACK:
            return None
        if dist > 1e-6:
            cos = max(-1.0, min(1.0, _dot(d, to) / dist))
            allowed = math.radians(AIM_TOLERANCE) + math.atan2(PLAYER_HALF, dist)
            if math.acos(cos) > allowed:
                return None
        block = self.map.segment_hit(o, q)
        if block is not None and math.dist(block, q) > PLAYER_HALF + 0.05:
            return None
        return q

    def ray_target(self, shooter: Player, o, d, reach: float) -> Player | None:
        """The first living player the ray from o along unit d meets within reach, if no map box is in
        the way: for bots, which do the browser's hit test themselves."""
        end = tuple(o[i] + d[i] * reach for i in range(3))
        wall = self.map.segment_hit(o, end)
        limit = math.dist(o, wall) / reach if wall else 1.0
        best, best_t = None, limit
        for p in self.arena():
            if p is shooter or p.dead:
                continue
            t = segment_cylinder(o, end, p.x, p.z, p.y, p.y + PLAYER_HEIGHT)
            if t is not None and t <= best_t:
                best, best_t = p, t
        return best

    def move_shells(self, now: float, dt: float) -> None:
        for shell in list(self.shells):
            spec = WEAPONS[LAUNCHER]
            a = (shell.x, shell.y, shell.z)
            b = tuple(a[i] + shell.d[i] * spec["speed"] * dt for i in range(3))
            best_t, victim = None, None
            wall = self.map.segment_hit(a, b)
            if wall is not None:
                seg = math.dist(a, b)
                best_t = math.dist(a, wall) / seg if seg > 0 else 0.0
            for p in self.arena():
                if p.dead or (p is shell.by and now - shell.born < SHELL_ARM):
                    continue
                t = segment_cylinder(a, b, p.x, p.z, p.y, p.y + PLAYER_HEIGHT)
                if t is not None and (best_t is None or t < best_t):
                    best_t, victim = t, p
            if best_t is not None:
                at = tuple(a[i] + (b[i] - a[i]) * best_t - shell.d[i] * 0.05 for i in range(3))
                self.explode(shell, at, victim, now)
            elif now - shell.born >= spec["life"]:
                self.explode(shell, b, None, now)
            else:
                shell.x, shell.y, shell.z = b

    def explode(self, shell: Shell, at, direct: Player | None, now: float) -> None:
        if shell in self.shells:
            self.shells.remove(shell)
        spec = WEAPONS[LAUNCHER]
        self.events.append({"e": "boom", "x": round(at[0], 3), "y": round(at[1], 3), "z": round(at[2], 3)})
        shooter = shell.by if shell.by.id in self.players else None
        hurt: list[tuple[Player, int]] = []
        if direct is not None:
            self.push(direct, knockback(at, direct, 1.0), now)
            hurt.append((direct, spec["damage"]))
        for p in self.arena():
            if p.dead or p is direct:
                continue
            f = splash_factor(at, p)
            if f <= 0 or not self.in_sight(at, p):
                continue
            self.push(p, knockback(at, p, f), now)
            amount = round(spec["splash"] * f)
            if p is shell.by:
                amount = round(amount * SELF_SPLASH)
            hurt.append((p, amount))
        for p, amount in hurt:
            self.damage(p, amount, shooter, "launcher", now, shell_owner=shell.by)

    def in_sight(self, at, p: Player) -> bool:
        """Splash reaches a player if a straight line reaches their feet, middle or head."""
        for h in (0.2, PLAYER_HEIGHT / 2, PLAYER_HEIGHT - 0.2):
            if self.map.segment_hit(at, (p.x, p.y + h, p.z)) is None:
                return True
        return False

    # --- damage and death ------------------------------------------------------------------------

    def damage(self, victim: Player, amount: int, by: Player | None, how: str, now: float,
               shell_owner: Player | None = None) -> None:
        if victim.dead or amount <= 0 or self.phase != "play":
            return
        if victim.armor > 0:
            soak = min(victim.armor, round(amount * ARMOR_SHARE))
            victim.armor -= soak
            amount -= soak
        victim.hp -= amount
        if by is not None and by is not victim:
            victim.hurt_by, victim.hurt_at = by.id, now
        victim.send({"t": "you", **victim.numbers()})
        if victim.hp <= 0:
            if shell_owner is victim:
                self.kill(victim, victim, "self", now)
            else:
                self.kill(victim, by, how, now)

    def void(self, player: Player, now: float) -> None:
        """Fell below kill_y: the frag goes to whoever hurt them in the last 4 s, else it costs a point."""
        by = self.players.get(player.hurt_by) if player.hurt_by else None
        if by is None or not by.in_arena or now - player.hurt_at > VOID_CREDIT:
            by = None
        self.kill(player, by, "void", now)

    def kill(self, victim: Player, by: Player | None, how: str, now: float) -> None:
        if victim.dead:
            return
        victim.dead, victim.died_at, victim.ready_at, victim.hp = True, now, now + RESPAWN_DELAY, min(victim.hp, 0)
        victim.deaths += 1
        if by is victim or (by is None and how == "void"):
            by = None  # killing yourself counts for nobody
        elif by is not None:
            by.frags += 1
            if by.account:
                self.count_frag(by.account)
        self.events.append({"e": "frag", "by": by.id if by else None, "of": victim.id, "how": how})
        victim.send({"t": "die", "by": by.id if by else None, "how": how,
                     "x": victim.x, "y": victim.y, "z": victim.z})
        if by is not None and by.frags >= FRAG_LIMIT:
            self.end_round(now)

    def count_frag(self, account: str) -> None:
        row = self.store.players.setdefault(account, {"frags": 0})
        row["frags"] = total = row.get("frags", 0) + 1
        self.dirty = True
        if total in MILESTONES or (total > MILESTONES[-1] and total % MILESTONES[-1] == 0):
            self.on_record(account, f"Reached {total} frags in Endless Arena.", {"frags": total})

    # --- pickups and decay -----------------------------------------------------------------------

    def items_here(self, now: float) -> list[int]:
        return [1 if now >= t else 0 for t in self.items_back]

    def pickups(self, now: float) -> None:
        for i, item in enumerate(self.map.items):
            if now < self.items_back[i]:
                continue
            ix, iy, iz = item["at"]
            for p in self.arena():
                if p.dead or math.hypot(p.x - ix, p.z - iz) > PICKUP_REACH or abs(p.y - iy) > PICKUP_HEIGHT:
                    continue
                if self.give(p, item["type"]):
                    self.items_back[i] = now + ITEMS[item["type"]]["respawn"]
                    self.events.append({"e": "take", "by": p.id, "item": i})
                    p.send({"t": "you", **p.numbers()})
                    break

    @staticmethod
    def give(p: Player, kind: str) -> bool:
        """Give player p what item `kind` gives; False (nothing taken) if it would give nothing."""
        spec = ITEMS[kind]
        if p.bot and ("health" in spec or "armor" in spec):
            return False
        if "health" in spec:
            if p.hp >= spec["upto"]:
                return False
            p.hp = min(spec["upto"], p.hp + spec["health"])
        elif "armor" in spec:
            if p.armor >= spec["upto"]:
                return False
            p.armor = min(spec["upto"], p.armor + spec["armor"])
        elif "weapon" in spec:
            w = spec["weapon"]
            most = WEAPONS[w]["ammo_max"]
            if w in p.weapons and p.ammo[w] >= most:
                return False
            p.weapons.add(w)
            p.ammo[w] = min(most, p.ammo[w] + spec["ammo"])
        else:
            w = spec["ammo_for"]
            most = WEAPONS[w]["ammo_max"]
            if p.ammo[w] >= most:
                return False
            p.ammo[w] = min(most, p.ammo[w] + spec["ammo"])
        return True

    def decay(self, dt: float) -> None:
        for p in self.arena():
            if p.dead or (p.hp <= DECAY_ABOVE and p.armor <= DECAY_ABOVE):
                p.decay = 0.0
                continue
            p.decay += dt
            changed = False
            while p.decay >= 1.0:
                p.decay -= 1.0
                if p.hp > DECAY_ABOVE:
                    p.hp -= 1
                    changed = True
                if p.armor > DECAY_ABOVE:
                    p.armor -= 1
                    changed = True
            if changed:
                p.send({"t": "you", **p.numbers()})

    # --- bots ------------------------------------------------------------------------------------

    def fighting(self) -> list[Player]:
        """People who are alive, or died less than FIGHTING_GRACE seconds ago. Someone who stays dead
        and watches does not count, so the bots keep the arena busy for whoever is still playing."""
        return [p for p in self.people() if not p.dead or self.now - p.died_at < FIGHTING_GRACE]

    def wanted_bots(self) -> int:
        return max(0, WANTED_BOTS - len(self.fighting()))

    def keep_bots(self, now: float) -> None:
        """If fewer bots are alive than wanted, respawn a dead one (once its 2 s are up) or add one."""
        mine = self.bots()
        if sum(1 for b in mine if not b.dead) >= self.wanted_bots():
            return
        dead = [b for b in mine if b.dead]
        if dead:
            b = min(dead, key=lambda b: b.died_at)
            if now - b.died_at >= RESPAWN_DELAY:
                self.spawn(b, now)
            return
        if len(self.arena()) >= ARENA_MAX:
            return
        taken = {p.name for p in self.players.values()}
        b = Player(f"b{self.next_bot}", bots.pick_name(taken, self.rng), bot=True, in_arena=True)
        self.next_bot += 1
        self.players[b.id] = b
        self.spawn(b, now)

    def move_bots(self, now: float, dt: float) -> None:
        for b in self.bots():
            if b.dead or b.motion is None:
                continue
            inp = bots.think(b, self, self.map, dt) or {}
            s = motion.step(b.motion, {**inp, "yaw": b.yaw}, dt, self.map)
            b.motion = s
            b.x, b.y, b.z = s["x"], s["y"], s["z"]
            if s["launched"]:
                self.events.append({"e": "pad", "by": b.id})
            if s["fell"]:
                self.void(b, now)

    # --- the round -------------------------------------------------------------------------------

    def round_message(self) -> dict:
        return {"t": "round", "phase": self.phase, "ends": self.ends, "scores": self.scores(ping=True),
                "limit": FRAG_LIMIT}

    def start_round(self, now: float) -> None:
        """A new round: scores, pickups and positions reset; bots who stayed dead are dropped."""
        self.phase, self.ends = "play", now + ROUND_SECONDS
        self.shells.clear()
        self.items_back = [0.0] * len(self.map.items)
        for b in self.bots():
            if b.dead:
                self.players.pop(b.id, None)
        everyone = self.arena()
        for p in everyone:
            p.frags = p.deaths = 0
            p.dead = True
        for p in everyone:
            self.spawn(p, now)
        self.send_all(self.round_message())

    def end_round(self, now: float) -> None:
        if self.phase != "play":
            return
        self.phase, self.ends = "over", now + OVER_SECONDS
        self.shells.clear()
        people = self.people()
        rows = sorted(self.arena(), key=lambda p: (-p.frags, p.deaths))
        if len(people) >= 2 and rows:
            top = rows[0]
            tied = len(rows) > 1 and (rows[1].frags, rows[1].deaths) == (top.frags, top.deaths)
            if top.account and not tied:
                self.on_record(top.account, f"Won a round of Endless Arena with {top.frags} frags against "
                               f"{len(rows) - 1} others.", {"frags": top.frags, "people": len(people)})
        self.send_all(self.round_message())

    # --- time passing ----------------------------------------------------------------------------

    def tick(self, now: float, dt: float) -> None:
        self.now = now
        self.tick_count += 1
        for p in list(self.players.values()):
            if not p.bot and not p.bye and now - p.heard > SILENT_LIMIT:
                self.drop(p, "Nothing came from your browser for 30 seconds, so this connection is done.")
        if self.dirty and now - self.saved_at >= SAVE_EVERY:
            self.flush(now)
        if self.ends is None:
            return
        if self.phase == "over":
            if now >= self.ends:
                self.start_round(now)
            return
        if now >= self.ends:
            self.end_round(now)
            return
        self.keep_bots(now)
        self.decay(dt)
        self.move_bots(now, dt)
        self.move_shells(now, dt)
        self.pickups(now)

    def flush(self, now: float = 0.0) -> None:
        self.dirty = False
        self.saved_at = now
        self.store.saved()

    def send_all(self, message: dict) -> None:
        for p in list(self.players.values()):
            if not p.bot:
                p.send(message)

    def broadcast(self, now: float) -> None:
        """The `state` message to every connection, and a `ping` every PING_EVERY seconds."""
        if now - self.pinged_at >= PING_EVERY:
            self.pinged_at = now
            self.send_all({"t": "ping", "c": now})
        if self.ends is None:
            self.events.clear()
            return
        r = lambda v: round(v, 3)  # noqa: E731
        state = {
            "t": "state", "tick": self.tick_count, "now": r(now),
            "players": [{"id": p.id, "name": p.name, "bot": p.bot, "x": r(p.x), "y": r(p.y), "z": r(p.z),
                         "yaw": r(p.yaw), "pitch": r(p.pitch), "w": p.w, "dead": p.dead, "hp": p.hp,
                         "armor": p.armor, "frags": p.frags, "deaths": p.deaths, "ping": p.ping}
                        for p in self.arena()],
            "shells": [{"id": s.id, "x": r(s.x), "y": r(s.y), "z": r(s.z), "dx": r(s.d[0]), "dy": r(s.d[1]),
                        "dz": r(s.d[2]), "by": s.by.id} for s in self.shells],
            "items": self.items_here(now),
            "events": self.events,
        }
        self.events = []
        self.send_all(state)

    def summary(self) -> dict:
        """For the welcome page."""
        return {"now": round(self.now, 3), "playing": len(self.people()), "bots": len(self.bots()),
                "round": {"phase": self.phase, "ends": self.ends, "scores": self.scores()}}


# --- helpers -------------------------------------------------------------------------------------

def splash_factor(at, p: Player) -> float:
    """1 at the explosion, falling to 0 at the splash radius, measured to the nearest point of the body."""
    radius = WEAPONS[LAUNCHER]["radius"]
    cy = min(p.y + PLAYER_HEIGHT, max(p.y, at[1]))
    gap = max(0.0, math.hypot(at[0] - p.x, at[2] - p.z) - PLAYER_HALF)
    dist = math.hypot(gap, at[1] - cy)
    return max(0.0, 1.0 - dist / radius)


def knockback(at, p: Player, f: float):
    """The push for a player at splash factor f: away from the explosion, plus some lift."""
    spec = WEAPONS[LAUNCHER]
    away = _sub((p.x, p.y + PLAYER_HEIGHT / 2, p.z), at)
    n = _len(away)
    away = (0.0, 1.0, 0.0) if n < 1e-6 else (away[0] / n, away[1] / n, away[2] / n)
    return (away[0] * spec["push"] * f, away[1] * spec["push"] * f + spec["lift"] * f, away[2] * spec["push"] * f)


def tidy_name(name: object) -> str:
    """A shown name, tidied as Endless Mind tidies names, then cut to NAME_MAX characters."""
    return realm_tidy(name)[:NAME_MAX].strip()
