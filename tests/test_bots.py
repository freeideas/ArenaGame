"""Tests for the bots' brain (server/arena_server/bots.py), driven by game.tick with a made-up clock."""

import math
import random

import pytest

from arena_server import bots, motion
from arena_server import game as g
from arena_server.game import BEAM, BLASTER, LAUNCHER, Game

DT = 1 / 30


class Person:
    """A connection that never moves: a target for bots."""

    def __init__(self, game, id, now=0.0):
        self.p = game.join(id, id * 8, lambda m: None, now, name=id.upper())


def arena_with(monkeypatch, bots_wanted, people=0, seed=1):
    """A running round with this many bots and people (people enter first, bots come on the first tick)."""
    monkeypatch.setattr(g, "WANTED_BOTS", bots_wanted + people)
    game = Game(rng=random.Random(seed))
    persons = [Person(game, chr(ord("a") + i)).p for i in range(people)]
    if persons:
        for p in persons:
            game.enter(p, 0.0)
    else:
        game.start_round(0.0)
    for k in range(bots_wanted):
        game.tick(DT * (k + 1), DT)
    assert len(game.bots()) == bots_wanted
    return game, persons


def run(game, t, seconds, each=None):
    """Tick for `seconds`; `each(t)` after every tick may return True to stop early. Returns the time."""
    for _ in range(round(seconds / DT)):
        t += DT
        game.tick(t, DT)
        if each and each(t):
            break
    return t


def put(bot, x, y, z):
    """Move a bot to stand at (x, y, z) with a fresh brain."""
    bot.x, bot.y, bot.z = x, y, z
    bot.motion = motion.new_state(x, y, z)
    bot.motion["ground"] = True
    bot.brain = {}


def calls(game, monkeypatch):
    """Record every game.fire call as (player, weapon, origin, direction, claimed hit)."""
    log = []
    real = game.fire

    def fire(player, w, o, d, hit, now):
        log.append((player, w, o, d, hit))
        return real(player, w, o, d, hit, now)

    monkeypatch.setattr(game, "fire", fire)
    return log


def test_lone_bot_walks_to_a_weapon(monkeypatch):
    game, _ = arena_with(monkeypatch, 1, seed=5)
    bot = game.bots()[0]
    end = run(game, 2 * DT, 30, lambda t: LAUNCHER in bot.weapons or BEAM in bot.weapons)
    assert not bot.dead
    assert LAUNCHER in bot.weapons or BEAM in bot.weapons, "no weapon picked up in 30 s"
    assert end < 30


def test_bot_reaches_the_perch_by_two_pads(monkeypatch):
    game, _ = arena_with(monkeypatch, 1, seed=6)
    bot = game.bots()[0]
    put(bot, -13, 0, 0)
    perch = next(i for i, n in enumerate(game.map.nodes) if n["at"] == [-1.5, 14, 0])
    bot.brain["order"] = perch
    pads = []

    def watch(t):
        pads.extend(e for e in game.events if e["e"] == "pad" and e["by"] == bot.id)
        game.events.clear()
        return bot.y > 13.5 and bot.motion["ground"]

    run(game, DT, 40, watch)
    assert not bot.dead
    assert bot.y == pytest.approx(14, abs=0.4) and abs(bot.x) < 3 and abs(bot.z) < 3, "never stood on the perch"
    assert len(pads) >= 2


def test_bot_fires_at_an_enemy_in_the_open_and_hits(monkeypatch):
    game, (a,) = arena_with(monkeypatch, 1, people=1, seed=7)
    bot = game.bots()[0]
    put(bot, -7.5, 0, -2)
    a.x, a.y, a.z = 7.5, 0, -2
    bot.brain["order"] = bots.graph(game.map).nearest(game.map, -7.5, 0, -2)
    log = calls(game, monkeypatch)
    hurt = []
    real_damage = game.damage
    monkeypatch.setattr(game, "damage", lambda v, n, by, how, now, **k: hurt.append((v, by)) or real_damage(v, n, by, how, now, **k))
    first = []

    def keep_alive(t):
        a.hp = 100
        if log and not first:
            first.append(t)

    run(game, DT, 4, keep_alive)
    assert first and first[0] - DT <= 1.0, "no shot within 1 s"
    assert all(w == BLASTER for _, w, *_ in log)
    claimed = [c for c in log if c[4] == a.id]
    accepted = [h for h in hurt if h[0] is a and h[1] is bot]
    assert len(claimed) >= len(log) / 4, f"{len(claimed)} hits claimed of {len(log)} shots at 15 m"
    assert len(accepted) >= len(claimed) / 2, f"server took {len(accepted)} of {len(claimed)} claimed hits"


def test_bot_never_fires_through_a_box(monkeypatch):
    game, (a,) = arena_with(monkeypatch, 1, people=1, seed=8)
    bot = game.bots()[0]
    put(bot, 0, 0, 0)
    bot.weapons = {BLASTER, LAUNCHER, BEAM}
    bot.ammo = {LAUNCHER: 20, BEAM: 20}
    bot.brain["order"] = bots.graph(game.map).nearest(game.map, 0, 0, 0)
    a.x, a.y, a.z = 0, 14, 0     # on the perch, straight above: the perch is in the way
    log = calls(game, monkeypatch)
    run(game, DT, 5)
    assert not bot.dead and math.hypot(bot.x, bot.z) < 1
    assert log == []
    # Step onto the open deck beside the perch and the same bot fires.
    a.x, a.y, a.z = -8, 0, -8
    run(game, DT, 2)
    assert log, "a bot with a clear line should fire"
    for _, _, o, _, _ in log:
        assert any(game.map.segment_hit(o, (a.x, a.y + h, a.z)) is None for h in (0.2, 1.0, 1.6))


def test_two_bots_fight_until_a_frag(monkeypatch):
    game, _ = arena_with(monkeypatch, 2, seed=9)
    frags = []

    def watch(t):
        frags.extend(e for e in game.events if e["e"] == "frag")
        game.events.clear()
        return any(e["by"] for e in frags)

    end = run(game, DT, 90, watch)
    assert any(e["by"] for e in frags), "no frag in 90 s"
    assert end < 90
