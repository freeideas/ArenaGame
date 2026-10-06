"""The server as a browser sees it: pages, /api/summary, the realm card and a short WebSocket game."""

import os
import tempfile

os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="arena-test-")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from arena_server.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_welcome_page_and_static_rules(client):
    r = client.get("/welcome/")
    assert r.status_code == 200 and "<html" in r.text.lower()
    r = client.get("/welcome", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "welcome/"
    assert client.get("/welcome/README.md").status_code == 404
    assert client.get("/shared/map.json").json()["name"] == "Driftyard"


def test_summary(client):
    s = client.get("/api/summary").json()
    assert set(s) == {"now", "playing", "bots", "round"}
    assert set(s["round"]) == {"phase", "ends", "scores"}


def test_realm_card(client):
    card = client.get("/endlessmind-card.json").json()
    assert card["name"] == "Endless Arena" and card["description"] and card["tags"]


def until(ws, test, limit=200):
    for _ in range(limit):
        m = ws.receive_json()
        if test(m):
            return m
    raise AssertionError("message never came")


def test_websocket_game(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"t": "hello", "guest": None})
        hello = until(ws, lambda m: m["t"] == "hello")
        assert len(hello["guest"]) == 32 and hello["player"] is None and hello["name"]
        me = hello["id"]
        ws.send_json({"t": "join"})
        spawn = until(ws, lambda m: m["t"] == "spawn")
        assert spawn["hp"] == 100 and spawn["weapons"] == [1] and spawn["w"] == 1
        x, y, z = spawn["x"], spawn["y"], spawn["z"]
        ws.send_json({"t": "at", "x": x, "y": y, "z": z, "yaw": 0, "pitch": 0, "vx": 0, "vy": 0, "vz": 0,
                      "ground": True, "seq": 1})
        ws.send_json({"t": "fire", "w": 1, "ox": x, "oy": y + 1.6, "oz": z, "dx": 0, "dy": 0, "dz": -1, "hit": None})
        state = until(ws, lambda m: m["t"] == "state" and any(e["e"] == "shot" for e in m["events"]))
        assert any(p["id"] == me for p in state["players"])
        assert sum(1 for p in state["players"] if p["bot"]) <= 2
        s = client.get("/api/summary").json()
        assert s["playing"] == 1
