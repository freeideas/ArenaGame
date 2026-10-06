"""Tests for the rules in server/arena_server/game.py, driven with a made-up clock."""

import math
import random

import pytest

from arena_server import game as g
from arena_server.game import BEAM, BLASTER, LAUNCHER, Game, Shell


class Person:
    """A connection's messages, kept for checking."""

    def __init__(self, game, id, now=0.0):
        self.got = []
        self.p = game.join(id, id * 8, self.got.append, now, name=id.upper())

    def last(self, t):
        return next((m for m in reversed(self.got) if m["t"] == t), None)


def setup(n=2):
    game = Game(rng=random.Random(1))
    people = [Person(game, chr(ord("a") + i)) for i in range(n)]
    for person in people:
        game.enter(person.p, 0.0)
    return game, [person.p for person in people], people


def place(p, x, y, z, yaw=0.0):
    p.x, p.y, p.z, p.yaw = x, y, z, yaw


def aim(o, target):
    d = [target[i] - o[i] for i in range(3)]
    n = math.sqrt(sum(v * v for v in d))
    return tuple(v / n for v in d)


def turned(d, degrees):
    """d turned left about the vertical by `degrees`."""
    a = math.radians(degrees)
    return (d[0] * math.cos(a) + d[2] * math.sin(a), d[1], -d[0] * math.sin(a) + d[2] * math.cos(a))


# --- instant hits --------------------------------------------------------------------------------

def test_true_blaster_hit_is_believed():
    game, (a, b), _ = setup()
    place(a, 0, 0, 4)
    place(b, 0, 0, -4)
    d = aim(a.eye, (0, 1.0, -4))
    game.fire(a, BLASTER, a.eye, d, b.id, 1.0)
    assert b.hp == 100 - g.WEAPONS[BLASTER]["damage"]
    assert any(e["e"] == "shot" and e["by"] == a.id for e in game.events)


def test_wrong_angle_hit_is_refused():
    game, (a, b), _ = setup()
    place(a, 0, 0, 4)
    place(b, 0, 0, -4)
    d = turned(aim(a.eye, (0, 1.0, -4)), 20)
    game.fire(a, BLASTER, a.eye, d, b.id, 1.0)
    assert b.hp == 100


def test_hit_refused_out_of_range_dead_or_behind_a_box():
    game, (a, b), _ = setup()
    place(a, 0, 0, 4)
    place(b, 0, 0, -4)
    b.dead = True
    game.fire(a, BLASTER, a.eye, aim(a.eye, (0, 1, -4)), b.id, 1.0)
    b.dead = False
    place(a, 0, 0, 80)
    place(b, 0, 0, 10)
    game.fire(a, BLASTER, a.eye, aim(a.eye, (0, 1, 10)), b.id, 2.0)
    assert b.hp == 100
    # Standing under the main deck, the deck is in the way.
    place(a, 0, 0, 4)
    place(b, 0, -6, 4)
    game.fire(a, BLASTER, a.eye, aim(a.eye, (0, -5, 4)), b.id, 3.0)
    assert b.hp == 100


def test_cooldown_and_ammo():
    game, (a, b), people = setup()
    place(a, 0, 0, 4)
    place(b, 0, 0, -4)
    d = aim(a.eye, (0, 1.0, -4))
    game.fire(a, BLASTER, a.eye, d, b.id, 1.0)
    game.fire(a, BLASTER, a.eye, d, b.id, 1.01)  # too soon
    assert b.hp == 92
    a.weapons.add(BEAM)
    game.switch_weapon(a, BEAM, 2.0)
    game.fire(a, BEAM, a.eye, d, b.id, 2.5)      # no charges
    assert b.hp == 92
    a.ammo[BEAM] = 1
    game.fire(a, BEAM, a.eye, d, b.id, 2.5)
    assert b.hp == 92 - 85 and a.ammo[BEAM] == 0
    push = people[1].last("push")
    assert push["vz"] < 0  # pushed along the shot


# --- shells and splash ---------------------------------------------------------------------------

def test_splash_falls_off_and_pushes_away():
    game, (a, b, c), people = setup(3)
    place(a, 0, 0, 10)
    at = (0.0, 0.5, 0.0)
    place(b, 1.4, 0, 0)    # body 1 m from the blast
    place(c, -2.9, 0, 0)   # body 2.5 m from the blast
    game.explode(Shell(1, *at, (0, 0, -1), a, 0.0), at, None, 1.0)
    fb, fc = 1 - 1 / 3.5, 1 - 2.5 / 3.5
    assert b.hp == 100 - round(90 * fb)
    assert c.hp == 100 - round(90 * fc)
    pb, pc = people[1].last("push"), people[2].last("push")
    assert pb["vx"] > 0 and pc["vx"] < 0          # away from the blast, on each side
    assert pb["vy"] > 0 and pc["vy"] > 0          # with some lift
    assert math.hypot(pb["vx"], pb["vz"]) > math.hypot(pc["vx"], pc["vz"])
    assert a.hp == 100                            # too far to be hurt


def test_own_splash_half_damage_full_push():
    game, (a, b), people = setup()
    place(a, 0, 0, 0)
    place(b, 0, 0, -20)
    at = (0.0, 0.05, 0.0)
    game.explode(Shell(1, *at, (0, -1, 0), a, 0.0), at, None, 1.0)
    assert a.hp == 100 - round(90 * 0.5)
    push = people[0].last("push")
    assert push["vy"] == pytest.approx(14 + 3, abs=0.01)


def test_shell_flies_and_hits_directly():
    game, (a, b), _ = setup()
    a.weapons.add(LAUNCHER)
    a.ammo[LAUNCHER] = 5
    game.switch_weapon(a, LAUNCHER, 0.0)
    place(a, 0, 0, 4)
    place(b, 0, 0, -4)
    b.hp = 50
    game.fire(a, LAUNCHER, a.eye, aim(a.eye, (0, 0.9, -4)), None, 1.0)
    assert len(game.shells) == 1 and a.ammo[LAUNCHER] == 4
    t = 1.0
    while game.shells and t < 2:
        t += 1 / 30
        game.move_shells(t, 1 / 30)
    assert not game.shells
    assert b.dead and a.frags == 1 and a.hp == 100


def test_armor_takes_two_thirds():
    game, (a, b), _ = setup()
    b.armor = 100
    game.damage(b, 30, a, "blaster", 1.0)
    assert (b.hp, b.armor) == (90, 80)
    b.armor = 10
    game.damage(b, 30, a, "blaster", 1.0)
    assert (b.hp, b.armor) == (70, 0)


# --- dying ---------------------------------------------------------------------------------------

def test_void_credits_recent_attacker():
    game, (a, b), _ = setup()
    game.damage(b, 8, a, "blaster", 10.0)
    game.report_at(b, {"x": 0, "y": -50, "z": 0, "seq": 1}, 12.0)
    assert b.dead and a.frags == 1 and b.frags == 0


def test_void_without_credit_costs_a_point():
    game, (a, b), _ = setup()
    game.damage(b, 8, a, "blaster", 10.0)
    game.report_at(b, {"x": 0, "y": -50, "z": 0, "seq": 1}, 14.5)
    assert b.dead and a.frags == 0 and b.frags == -1
    assert game.events[-1] == {"e": "frag", "by": None, "of": b.id, "how": "void"}


def test_respawn_waits_two_seconds():
    game, (a, b), people = setup()
    game.kill(b, a, "blaster", 5.0)
    assert people[1].last("die")["by"] == a.id
    game.respawn(b, 6.0)
    assert b.dead
    game.respawn(b, 7.0)
    assert not b.dead and b.hp == 100 and b.weapons == {BLASTER}


# --- moves ---------------------------------------------------------------------------------------

def test_moves_checked():
    game, (a, _b), people = setup()
    place(a, 0, 0, 4)
    a.at_time, a.budget = 1.0, 0.0
    game.report_at(a, {"x": 0.4, "y": 0, "z": 4, "seq": 1}, 1.05)
    assert a.x == 0.4
    game.report_at(a, {"x": 5, "y": 0, "z": 4, "seq": 2}, 1.1)  # far too far
    assert a.x == 0.4 and people[0].last("snap") == {"t": "snap", "x": 0.4, "y": 0, "z": 4}
    game.report_at(a, {"x": 0.4, "y": -0.5, "z": 4, "seq": 3}, 1.15)  # inside the deck
    assert a.y == 0


# --- pickups -------------------------------------------------------------------------------------

def test_pickup_refused_when_full_and_taken_when_not():
    game, (a, _b), _ = setup()
    i = next(i for i, it in enumerate(game.map.items) if it["type"] == "health")
    x, y, z = game.map.items[i]["at"]
    place(a, x, y, z)
    game.pickups(1.0)
    assert a.hp == 100 and game.items_here(1.0)[i] == 1
    a.hp = 50
    game.pickups(1.0)
    assert a.hp == 75 and game.items_here(1.0)[i] == 0
    assert game.items_here(1.0 + 20)[i] == 1


def test_health_above_100_decays():
    game, (a, _b), _ = setup()
    a.hp, a.armor = 103, 101
    for _ in range(30 * 2 + 1):
        game.decay(1 / 30)
    assert (a.hp, a.armor) == (101, 100)


# --- the round -----------------------------------------------------------------------------------

def test_round_ends_at_frag_limit_and_resets():
    game, (a, b), people = setup()
    records = []
    game.on_record = lambda player, text, data: records.append((player, text))
    a.account = "acct"
    a.frags = g.FRAG_LIMIT - 1
    game.kill(b, a, "blaster", 50.0)
    assert game.phase == "over" and game.ends == 50.0 + g.OVER_SECONDS
    assert people[1].last("round")["phase"] == "over"
    assert records and records[0][0] == "acct"
    game.fire(a, BLASTER, a.eye, (0, 0, -1), None, 51.0)  # nobody shoots now
    assert not any(e["e"] == "shot" for e in game.events)
    game.tick(50.0 + g.OVER_SECONDS, 1 / 30)
    assert game.phase == "play" and a.frags == 0 and b.frags == 0 and not b.dead
    assert people[0].last("spawn") is not None


def test_round_ends_at_time_limit():
    game, _, _ = setup()
    game.tick(g.ROUND_SECONDS + 0.1, 1 / 30)
    assert game.phase == "over"


# --- bots ----------------------------------------------------------------------------------------

def run(game, start, seconds):
    t = start
    for _ in range(round(seconds * 30)):
        t += 1 / 30
        game.tick(t, 1 / 30)
    return t


def test_bot_count_follows_people():
    game = Game(rng=random.Random(2))
    a = Person(game, "a").p
    game.enter(a, 0.0)
    t = run(game, 0.0, 0.5)
    assert len(game.bots()) == 2
    b = Person(game, "b").p
    game.enter(b, t)
    t = run(game, t, 0.5)
    assert len(game.bots()) == 2, "living bots are never removed when people join"
    bot = game.bots()[0]
    game.kill(bot, a, "blaster", t)
    t = run(game, t, 3)
    assert bot.dead, "one bot is enough with two people"
    game.leave(b)
    t = run(game, t, 0.5)
    assert not bot.dead and len(game.bots()) == 2, "the dead bot comes back when a person leaves"
    game.enter(Person(game, "c").p, t)
    game.enter(Person(game, "d").p, t)
    for bot in game.bots():
        game.kill(bot, a, "blaster", t)
    t = run(game, t, 3)
    assert all(bot.dead for bot in game.bots())
    game.end_round(t)
    run(game, t, g.OVER_SECONDS + 0.1)
    assert game.bots() == [], "bots who stayed dead are dropped at the next round"


def test_bots_go_when_the_last_person_leaves():
    game = Game(rng=random.Random(3))
    a = Person(game, "a").p
    game.enter(a, 0.0)
    run(game, 0.0, 0.5)
    game.leave(a)
    assert game.players == {} and game.summary()["round"]["ends"] is None


def test_bot_faces_nearest_enemy():
    game = Game(rng=random.Random(4))
    a = Person(game, "a").p
    game.enter(a, 0.0)
    run(game, 0.0, 0.2)
    bot = game.bots()[0]
    d = g.aim_from(bot.yaw, bot.pitch)
    e = min((p for p in game.arena() if p is not bot), key=lambda p: math.dist((p.x, p.y, p.z), (bot.x, bot.y, bot.z)))
    to = aim((bot.x, bot.y, bot.z), (e.x, e.y, e.z))
    assert sum(d[i] * to[i] for i in range(3)) == pytest.approx(1, abs=1e-6)


def test_summary_shape():
    game, (a, b), _ = setup()
    a.frags = 3
    s = game.summary()
    assert s["playing"] == 2 and s["bots"] == 0 and s["round"]["phase"] == "play"
    assert s["round"]["scores"][0] == {"id": a.id, "name": "A", "bot": False, "frags": 3, "deaths": 0}
