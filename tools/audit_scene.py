"""Run with Blender -b result.blend --python tools/audit_scene.py -- metadata.json config.json."""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
meta = json.loads(Path(args[0]).read_text(encoding="utf-8"))
config = json.loads(Path(args[1]).read_text(encoding="utf-8"))
terrain = bpy.data.objects["Terrain"]
for polygon in terrain.data.polygons:
    if polygon.material_index != 0:
        continue
    for loop_index in polygon.loop_indices:
        loop = terrain.data.loops[loop_index]
        vertex = terrain.data.vertices[loop.vertex_index]
        uv = terrain.data.uv_layers.active.data[loop_index].uv
        assert abs(uv.x - (vertex.co.x + 0.5)) < 1e-5
        assert abs(uv.y - (vertex.co.y + 0.5)) < 1e-5
mesh = bmesh.new()
mesh.from_mesh(terrain.data)
non_manifold = sum(not edge.is_manifold for edge in mesh.edges)
mesh.free()
expected_ratio = meta["width"] / meta["height"]
observed_ratio = terrain.dimensions.x / terrain.dimensions.y
assert abs(observed_ratio / expected_ratio - 1) < 1e-5
assert non_manifold == 0, f"non-manifold edges: {non_manifold}"
top_vertices = [v.co.z for v in terrain.data.vertices if v.co.z > -0.019]
relief = max(top_vertices) - min(top_vertices)
expected_relief = config["height_strength"] * 0.98
assert abs(relief / expected_relief - 1) < 0.04, (relief, expected_relief)
sun = bpy.data.objects["Sun"]
towards_sun = sun.rotation_euler.to_matrix() @ Vector((0, 0, 1))
az = math.degrees(math.atan2(towards_sun.x, towards_sun.y)) % 360
el = math.degrees(math.asin(towards_sun.z))
assert abs(az - config["sun_azimuth"]) < 0.001
assert abs(el - config["sun_elevation"]) < 0.001
height_image = bpy.data.images["Normalized DEM"]
assert height_image.packed_file is not None
assert ("White Ground" in bpy.data.objects) != config["transparent_background"]
report = {"blend": bpy.data.filepath, "dimensions": list(terrain.dimensions),
          "ratio_expected": expected_ratio, "ratio_observed": observed_ratio,
          "non_manifold_edges": non_manifold, "top_relief": relief,
          "expected_top_relief": expected_relief, "sun_azimuth": az, "sun_elevation": el,
          "height_texture_packed": True, "film_transparent": bpy.context.scene.render.film_transparent,
          "uv_east_north_orientation": "passed: +U=+X east, +V=+Y grid north",
          "floor_present": "White Ground" in bpy.data.objects}
Path(bpy.data.filepath).with_suffix(".audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
