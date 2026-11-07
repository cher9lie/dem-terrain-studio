"""Closed raster-mask terrain blocks, independent of Blender and third parties.

Each retained grid cell has a top, a matching bottom, and walls on exposed
edges. Corner-only contacts use separate vertices to keep each fan manifold.
Mask sampling is nearest-neighbour at cell centres; sub-cell features can vanish.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Sequence


@dataclass
class TerrainMesh:
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, ...]]
    uv: list[tuple[float, float]]
    top_faces: int
    retained_cells: int
    grid_size: tuple[int, int]


def build_terrain_mesh(heights: Sequence[float], valid: Sequence[int], width: int,
                       height: int, subdivisions: int, strength: float) -> TerrainMesh:
    if width < 2 or height < 2 or len(heights) != width * height or len(valid) != width * height:
        raise ValueError("Height and mask arrays must match an image of at least 2x2.")
    if not 2 <= subdivisions <= 1024 or not math.isfinite(strength) or strength < 0:
        raise ValueError("Invalid mesh subdivisions or height strength.")
    nx = min(width, max(2, round(subdivisions * width / max(width, height))))
    ny = min(height, max(2, round(subdivisions * height / max(width, height))))
    cells: dict[tuple[int, int], float] = {}
    for y in range(ny):
        sy = min(height - 1, int((y + 0.5) * height / ny))
        for x in range(nx):
            sx = min(width - 1, int((x + 0.5) * width / nx))
            index = sy * width + sx
            if valid[index]:
                value = float(heights[index])
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Valid encoded heights must be finite and nonnegative.")
                cells[x, y] = value * strength
    if not cells:
        raise ValueError("No valid cells at this mesh resolution; increase subdivisions.")

    vertices: list[tuple[float, float, float]] = []
    uv: list[tuple[float, float]] = []
    # Key includes the local connected fan, so diagonal components never weld.
    corner_ids: dict[tuple[int, int, tuple[tuple[int, int], ...]], int] = {}

    def corner(cx: int, cy: int, owner: tuple[int, int]) -> int:
        neighbours = {(x, y) for x in (cx - 1, cx) for y in (cy - 1, cy) if (x, y) in cells}
        fan = {owner}
        pending = [owner]
        while pending:
            x, y = pending.pop()
            for other in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if other in neighbours and other not in fan:
                    fan.add(other)
                    pending.append(other)
        key = (cx, cy, tuple(sorted(fan)))
        if key not in corner_ids:
            corner_ids[key] = len(vertices)
            z = sum(cells[cell] for cell in sorted(fan)) / len(fan)
            vertices.append((cx / nx - 0.5, cy / ny - 0.5, z))
            uv.append((cx / nx, cy / ny))
        return corner_ids[key]

    faces: list[tuple[int, ...]] = []
    for x, y in cells:
        owner = (x, y)
        a, b, c, d = (corner(x, y, owner), corner(x + 1, y, owner),
                       corner(x + 1, y + 1, owner), corner(x, y + 1, owner))
        faces.extend(((a, b, c), (a, c, d)))
    top_faces = len(faces)
    top_vertices = len(vertices)
    vertices.extend((x, y, -0.02) for x, y, _z in vertices[:top_vertices])
    uv.extend(uv[:top_vertices])
    boundary: Counter = Counter()
    directed: dict[tuple[int, int], tuple[int, int]] = {}
    for face in faces[:top_faces]:
        faces.append(tuple(index + top_vertices for index in reversed(face)))
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            boundary[edge] += 1
            directed[edge] = (a, b)
    for edge, count in boundary.items():
        if count == 1:
            a, b = directed[edge]
            faces.append((b, a, a + top_vertices, b + top_vertices))
    return TerrainMesh(vertices, faces, uv, top_faces, len(cells), (nx, ny))
