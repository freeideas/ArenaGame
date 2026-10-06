"""The map, loaded from app/shared/map.json, and plain geometry questions about it.

The browser reads the same JSON file. Everything solid is an axis-aligned box:
the map's boxes and its launch pads (pads are thin boxes on a platform's top).
A player, for collision, is a box 0.8 m wide, 1.8 m tall and 0.8 m deep with
the feet at its position.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MAP_PATH = Path(__file__).resolve().parents[2] / "app" / "shared" / "map.json"

PLAYER_HALF = 0.4    # half the player's width and depth
PLAYER_HEIGHT = 1.8
SKIN = 1e-6          # touching is not overlapping; this absorbs rounding


@dataclass(frozen=True)
class Box:
    """A solid box from the map's "boxes" list."""
    min: tuple[float, float, float]
    max: tuple[float, float, float]
    color: str = ""
    name: str = ""


@dataclass(frozen=True)
class Pad:
    """A launch pad: solid like a box, and sets a player's velocity to `launch`."""
    min: tuple[float, float, float]
    max: tuple[float, float, float]
    launch: tuple[float, float, float]
    to: tuple[float, float, float]
    color: str = ""


class MapData:
    """One loaded map. `solids` is boxes then pads, in file order (motion relies on that order)."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.name: str = raw["name"]
        self.version: int = raw["version"]
        self.physics: dict = dict(raw["physics"])
        self.boxes = [Box(tuple(b["min"]), tuple(b["max"]), b.get("color", ""), b.get("name", "")) for b in raw["boxes"]]
        self.pads = [Pad(tuple(p["min"]), tuple(p["max"]), tuple(p["launch"]), tuple(p["to"]), p.get("color", "")) for p in raw["pads"]]
        self.solids: list[Box | Pad] = [*self.boxes, *self.pads]
        self.spawns: list[dict] = raw["spawns"]
        self.items: list[dict] = raw["items"]
        self.waypoints: dict = raw["waypoints"]
        self.nodes: list[dict] = raw["waypoints"]["nodes"]
        self.edges: list[dict] = raw["waypoints"]["edges"]

    def player_overlaps(self, x: float, y: float, z: float) -> bool:
        """True if a player with feet at (x, y, z) overlaps any box or pad."""
        return any(player_overlaps_solid(x, y, z, s) for s in self.solids)

    def segment_hit(self, a, b) -> tuple[float, float, float] | None:
        """First point where the segment from a to b enters a box or pad, or None.

        For shells and line of sight. A segment starting inside a solid hits at a.
        """
        best = None
        for s in self.solids:
            t = _segment_box(a, b, s.min, s.max)
            if t is not None and (best is None or t < best):
                best = t
        if best is None:
            return None
        return tuple(a[i] + (b[i] - a[i]) * best for i in range(3))

    def surface_under(self, x: float, y: float, z: float, above: float = 0.3) -> Box | Pad | None:
        """The solid with the highest top at or below y + `above` whose footprint holds (x, z).

        Use the result's max[1] as the height of the surface. None means void below.
        """
        best = None
        for s in self.solids:
            if s.min[0] <= x <= s.max[0] and s.min[2] <= z <= s.max[2] and s.max[1] <= y + above:
                if best is None or s.max[1] > best.max[1]:
                    best = s
        return best


def player_overlaps_solid(x: float, y: float, z: float, s) -> bool:
    """True if a player box with feet at (x, y, z) overlaps solid s (with min and max)."""
    return (x - PLAYER_HALF < s.max[0] - SKIN and x + PLAYER_HALF > s.min[0] + SKIN
            and y < s.max[1] - SKIN and y + PLAYER_HEIGHT > s.min[1] + SKIN
            and z - PLAYER_HALF < s.max[2] - SKIN and z + PLAYER_HALF > s.min[2] + SKIN)


def _segment_box(a, b, lo, hi) -> float | None:
    """Fraction 0..1 along a->b where the segment first touches box lo..hi, or None (slab method)."""
    t0, t1 = 0.0, 1.0
    for i in range(3):
        d = b[i] - a[i]
        if d == 0.0:
            if a[i] < lo[i] or a[i] > hi[i]:
                return None
            continue
        u = (lo[i] - a[i]) / d
        v = (hi[i] - a[i]) / d
        if u > v:
            u, v = v, u
        t0 = max(t0, u)
        t1 = min(t1, v)
        if t0 > t1:
            return None
    return t0


def load_map(path: Path | str = MAP_PATH) -> MapData:
    """Read a map JSON file."""
    with open(path, encoding="utf-8") as f:
        return MapData(json.load(f))


MAP = load_map()
