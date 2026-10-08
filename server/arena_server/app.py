"""The Endless Arena server: one process that serves the pages and runs the game, forever.

  /             static files from app/: one subdirectory per page (app/README.md)
  /api/summary  who is playing and the round's scores, for the welcome page
  /ws           the game: one WebSocket (a lasting two-way connection) per player, specs/protocol.md
  endlessmind*, join/, claim/   the realm (sign-in with Endless Mind and records), answered by the
                realm library's middleware before the app sees the request

Settings, all optional, from the environment: PORT (8780), HOST (127.0.0.1), BASE (the public address,
http://localhost:8780/), DATA_ROOT (data/ in the repository: the realm's secret phrase and data, lifetime
frags and guests' chosen names, kept out of Git).
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from endlessmind import RealmMiddleware, open_realm
from endlessmind.names import ADJECTIVES, NOUNS
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .game import Game, Store

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
DATA_ROOT = Path(os.environ.get("DATA_ROOT", ROOT / "data"))
BASE = os.environ.get("BASE", "http://localhost:8780/")
TICK = 1 / 30
BROADCAST = 1 / 20
CACHE_PAGE = "public, max-age=300"
CACHE_VENDOR = "public, max-age=86400"
CARD = {
    "name": "Endless Arena",
    "description": "A fast free-for-all shooter on floating platforms in space: launch pads, a sniper perch, "
                   "and a long fall for whoever gets blasted off the edge.",
    "tags": ["shooter", "arena", "multiplayer", "3d"],
}

log = logging.getLogger("arena")


class FileStore(Store):
    """The Store, kept as JSON files in DATA_ROOT, written whole and swapped in so a crash never leaves half a file."""

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.players = self.read("players.json")
        self.guests = self.read("guests.json")

    def read(self, name: str) -> dict:
        try:
            return json.loads((self.folder / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def write(self, name: str, value: dict) -> None:
        part = self.folder / (name + ".part")
        part.write_text(json.dumps(value), encoding="utf-8")
        part.replace(self.folder / name)

    def saved(self) -> None:
        self.write("players.json", self.players)
        self.write("guests.json", self.guests)


def guest_name(guest: str) -> str:
    """A friendly starting name that stays the same for a guest ID, from Endless Mind's name words."""
    digest = hashlib.sha256(guest.encode()).digest()
    return f"{ADJECTIVES[digest[0] % len(ADJECTIVES)].capitalize()} {NOUNS[digest[1] % len(NOUNS)].capitalize()}"


DATA_ROOT.mkdir(parents=True, exist_ok=True)
realm = open_realm(BASE, CARD, secret_file=DATA_ROOT / "realm-secret.txt", data_file=DATA_ROOT / "realm-data.json")


def offer_record(player: str, text: str, data: dict) -> None:
    """Called by the game (inside the event loop) when a signed-in player earns a record."""
    async def offer() -> None:
        try:
            await realm.offer(player, [{"text": text, "data": data}])
        except Exception:
            log.exception("offering a record failed")

    asyncio.get_running_loop().create_task(offer())


game = Game(FileStore(DATA_ROOT), on_record=offer_record)


IDLE_PERIOD = 0.5  # with nobody connected there is nothing to simulate or send: wake rarely


async def every(period: float, step) -> None:
    """Call step(now, dt) every `period` seconds, on a fixed schedule so it does not drift. With
    nobody connected the loop wakes only every IDLE_PERIOD, so an empty arena costs almost nothing."""
    last = due = time.monotonic()
    while True:
        due += IDLE_PERIOD if not game.players else period
        await asyncio.sleep(max(0.0, due - time.monotonic()))
        now = time.monotonic()
        if now - due > 1.0 or not game.players:
            due = now  # fell far behind (the machine slept) or idle: start the schedule again
        try:
            step(now, min(now - last, 0.25))
        except Exception:
            log.exception("game step failed")
        last = now


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(every(TICK, game.tick)),
             asyncio.create_task(every(BROADCAST, lambda now, dt: game.broadcast(now)))]
    yield
    for task in tasks:
        task.cancel()
    game.flush(time.monotonic())


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RealmMiddleware, realm=realm)


@app.get("/api/summary")
def summary():
    return JSONResponse(game.summary(), headers={"Cache-Control": "no-store"})


def _numbers(message: dict, *keys: str) -> tuple[float, ...] | None:
    try:
        return tuple(float(message[k]) for k in keys)
    except (KeyError, TypeError, ValueError):
        return None


@app.websocket("/ws")
async def play(ws: WebSocket):
    """The browser first sends {"t": "hello", "guest": <its guest ID or null>}; see specs/protocol.md."""
    await ws.accept()
    outbox: asyncio.Queue = asyncio.Queue()
    player = None

    async def writer():
        while True:
            message = await outbox.get()
            await ws.send_text(json.dumps(message))
            if message.get("t") == "bye":
                await ws.close()
                return

    sending = asyncio.create_task(writer())
    try:
        while True:
            message = await ws.receive_json()
            if not isinstance(message, dict):
                continue
            now = time.monotonic()
            kind = message.get("t")
            if player is not None:
                if player.bye:
                    break
                game.heard_from(player, now)
            if player is None:
                if kind != "hello":
                    continue
                guest = message.get("guest")
                if not isinstance(guest, str) or not re.fullmatch(r"[0-9a-f]{32}", guest):
                    guest = secrets.token_hex(16)
                account = await realm.player(ws.scope)
                name = realm.player_name(account) if account else guest_name(guest)
                player = game.join(secrets.token_hex(4), guest, outbox.put_nowait, now, account=account, name=name)
            elif kind == "join":
                game.enter(player, now)
            elif kind == "at":
                game.report_at(player, message, now)
            elif kind == "fire":
                o, d = _numbers(message, "ox", "oy", "oz"), _numbers(message, "dx", "dy", "dz")
                if o and d:
                    game.fire(player, message.get("w"), o, d, message.get("hit"), now)
            elif kind == "weapon":
                game.switch_weapon(player, message.get("w"), now)
            elif kind == "respawn":
                game.respawn(player, now)
            elif kind == "out":
                game.step_out(player, now, "out")
            elif kind == "name":
                game.rename(player, message.get("name"))
            elif kind == "pong":
                game.pong(player, message.get("c"), now)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        sending.cancel()
        if player:
            game.leave(player)


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
def static(path: str):
    """Serve app/<path>; a directory serves its index.html (redirecting to the slash form first so
    page-relative URLs resolve inside the directory). README.md files are never served."""
    if ".." in path.split("/"):
        raise HTTPException(404)
    target = (APP_DIR / path) if path else APP_DIR
    try:
        target.resolve().relative_to(APP_DIR.resolve())
    except ValueError:
        raise HTTPException(404) from None
    if target.is_dir():
        if path and not path.endswith("/"):
            return RedirectResponse(url=f"{path.rsplit('/', 1)[-1]}/", status_code=301)
        target = target / "index.html"
    if not target.is_file() or target.name == "README.md":
        raise HTTPException(404)
    cache = CACHE_VENDOR if path.startswith("vendor/") else CACHE_PAGE
    return FileResponse(target, headers={"Cache-Control": cache})


def main() -> None:
    """The `arena-server` entry point (see deploy/arena.service)."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", 8780))
    log.info("listening host=%s port=%s base=%s data_root=%s", host, port, BASE, DATA_ROOT)
    uvicorn.run(app, host=host, port=port, proxy_headers=True)
