from collections import Counter, defaultdict
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dem_terrain_studio.blender.terrain_mesh import build_terrain_mesh


class TerrainMeshTests(unittest.TestCase):
    def check_mask(self, mask, width, height):
        mesh = build_terrain_mesh([0.5] * len(mask), mask, width, height, max(width, height), 2)
        edges = Counter()
        directed = Counter()
        links = defaultdict(list)
        for face in mesh.faces:
            for a, b in zip(face, face[1:] + face[:1]):
                edges[tuple(sorted((a, b)))] += 1
                directed[a, b] += 1
            for i, v in enumerate(face):
                links[v].append((face[i - 1], face[(i + 1) % len(face)]))
        self.assertTrue(all(count == 2 for count in edges.values()))
        self.assertTrue(all(directed[a, b] == directed[b, a] == 1 for a, b in edges))
        # An edge check alone misses corner pinches: every vertex link must be
        # one connected cycle, including diagonal-only contacts and narrow necks.
        for pairs in links.values():
            graph = defaultdict(set)
            for a, b in pairs:
                graph[a].add(b)
                graph[b].add(a)
            self.assertTrue(all(len(neighbours) == 2 for neighbours in graph.values()))
            visited = {next(iter(graph))}
            pending = list(visited)
            while pending:
                for v in graph[pending.pop()]:
                    if v not in visited:
                        visited.add(v)
                        pending.append(v)
            self.assertEqual(len(visited), len(graph))
        self.assertEqual(mesh.retained_cells, sum(mask))
        self.assertEqual(mesh.top_faces, 2 * sum(mask))
        for face in mesh.faces[:mesh.top_faces]:
            x = sum(mesh.vertices[i][0] for i in face) / 3 + 0.5
            y = sum(mesh.vertices[i][1] for i in face) / 3 + 0.5
            self.assertTrue(mask[min(height - 1, int(y * height)) * width + min(width - 1, int(x * width))])
        volume = 0
        for face in mesh.faces:
            a = mesh.vertices[face[0]]
            for i in range(1, len(face) - 1):
                b, c = mesh.vertices[face[i]], mesh.vertices[face[i + 1]]
                volume += (a[0] * (b[1]*c[2]-b[2]*c[1])
                           - a[1] * (b[0]*c[2]-b[2]*c[0])
                           + a[2] * (b[0]*c[1]-b[1]*c[0])) / 6
        self.assertAlmostEqual(volume, sum(mask) / (width * height) * 1.02, places=10)
        return mesh

    def test_all_nonempty_3x3_masks(self):
        for bits in range(1, 512):
            with self.subTest(bits=bits):
                self.check_mask([(bits >> i) & 1 for i in range(9)], 3, 3)

    def test_multiple_holes_islands_and_random_masks(self):
        rng = random.Random(7531)
        for _ in range(64):
            self.check_mask([rng.randrange(2) for _ in range(64)], 8, 8)

    def test_ring_has_genus_one(self):
        mesh = self.check_mask([1,1,1,1,0,1,1,1,1], 3, 3)
        edges = {tuple(sorted((a,b))) for face in mesh.faces for a,b in zip(face, face[1:]+face[:1])}
        self.assertEqual(len(mesh.vertices) - len(edges) + len(mesh.faces), 0)

    def test_nodata_height_never_contributes_to_boundary(self):
        heights = [0.25, -9999, -9999, 0.75]
        mesh = build_terrain_mesh(heights, [1,0,0,1], 2, 2, 2, 2)
        self.assertEqual(sorted(set(z for x,y,z in mesh.vertices)), [-0.02, 0.5, 1.5])

    def test_empty_or_nonfinite_inputs_fail(self):
        for heights, mask in (([0.5]*4, [0]*4), ([math.nan]*4, [1]*4)):
            with self.assertRaises(ValueError):
                build_terrain_mesh(heights, mask, 2, 2, 2, 1)

    def test_empty_at_coarse_resolution_fails(self):
        with self.assertRaisesRegex(ValueError, "increase subdivisions"):
            build_terrain_mesh([0.5]*100, [1]+[0]*99, 10, 10, 2, 1)


if __name__ == "__main__":
    unittest.main()
