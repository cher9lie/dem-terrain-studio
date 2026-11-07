"""Blender -b scene.blend --python tools/audit_masked_scene.py -- config.json."""
from array import array
from collections import defaultdict
import json
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

path = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
config = json.loads(path.read_text(encoding="utf-8"))
terrain = bpy.data.objects["Terrain"]
data = terrain.data
mesh = bmesh.new()
mesh.from_mesh(data)
non_manifold = sum(not e.is_manifold for e in mesh.edges)
bad_vertices = sum(not v.is_manifold for v in mesh.verts)
volume = mesh.calc_volume(signed=True)
mesh.free()
assert non_manifold == bad_vertices == 0, (non_manifold, bad_vertices)
assert volume > 0
source = bpy.data.images.load(str((path.parent / config["height_map"]).resolve()), check_existing=False)
source.colorspace_settings.name = "Non-Color"
width, height = source.size
pixels = array("f", [0.0]) * len(source.pixels)
source.pixels.foreach_get(pixels)
nx, ny = terrain["grid_size"]
expected = set()
for y in range(ny):
    for x in range(nx):
        sx, sy = int((x + 0.5) * width / nx), int((y + 0.5) * height / ny)
        if pixels[(sy * width + sx) * 4 + 3] > 0.001:
            expected.add((x,y))
bvh = BVHTree.FromPolygons([v.co for v in data.vertices], [p.vertices[:] for p in data.polygons])
for y in range(ny):
    for x in range(nx):
        result = bvh.ray_cast(Vector(((x + 0.5)/nx - 0.5, (y + 0.5)/ny - 0.5, 10001)), Vector((0,0,-1)))
        assert (result[0] is not None) == ((x,y) in expected), (x,y)

components = 0
remaining = expected.copy()
while remaining:
    components += 1
    pending = [remaining.pop()]
    while pending:
        x,y = pending.pop()
        for cell in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if cell in remaining:
                remaining.remove(cell)
                pending.append(cell)
chi = len(data.vertices) - len(data.edges) + len(data.polygons)
holes = components - chi // 2
assert chi % 2 == 0 and holes >= 0
metadata_path = path.parent / "metadata.json"
if metadata_path.exists() and nx == width and ny == height:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if "source_mask_components" in metadata:
        assert components == metadata["source_mask_components"]
        assert holes == metadata["source_mask_holes"]
assert terrain["retained_cells"] == len(expected)
assert sum(p.material_index == 0 for p in data.polygons) == 2 * len(expected)
assert bool(bpy.context.scene.render.film_transparent) == config["transparent_background"]
assert ("White Ground" in bpy.data.objects) != config["transparent_background"]
assert bpy.data.images["Normalized DEM"].packed_file is not None
report = {"non_manifold_edges":non_manifold,"non_manifold_vertices":bad_vertices,
          "volume_local":volume,"grid_size":[nx,ny],"retained_cells":len(expected),
          "closed_components":components,"through_holes":holes,"euler_characteristic":chi,
          "ray_tests":nx*ny,"ray_mask_match":True,"film_transparent":config["transparent_background"]}
Path(bpy.data.filepath).with_suffix(".mask-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
