"""Executed by Blender: build a terrain scene from aligned height/color maps."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    base = path.parent.resolve()
    for key in ("height_map", "color_map", "output"):
        value = Path(config[key]).expanduser()
        config[key] = str((base / value).resolve() if not value.is_absolute() else value.resolve())
    return config


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.textures, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for item in list(datablocks):
            if item.users == 0:
                datablocks.remove(item)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_terrain(config: dict) -> bpy.types.Object:
    subdivisions = max(2, int(config.get("subdivisions", 256)))
    size = float(config.get("terrain_size", 10.0))
    strength = float(config.get("height_strength", 1.8))

    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=subdivisions,
        y_subdivisions=subdivisions,
        size=size,
        location=(0.0, 0.0, 0.0),
    )
    terrain = bpy.context.object
    terrain.name = "Terrain"

    height_image = bpy.data.images.load(config["height_map"], check_existing=True)
    height_image.colorspace_settings.name = "Non-Color"
    texture = bpy.data.textures.new("HeightMap", type="IMAGE")
    texture.image = height_image

    modifier = terrain.modifiers.new("DEM Displacement", type="DISPLACE")
    modifier.texture = texture
    modifier.texture_coords = "UV"
    modifier.mid_level = 0.0
    modifier.strength = strength

    material = bpy.data.materials.new("Terrain Color")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    color = nodes.new("ShaderNodeTexImage")
    color.image = bpy.data.images.load(config["color_map"], check_existing=True)
    color.interpolation = "Linear"
    links.new(color.outputs["Color"], shader.inputs["Base Color"])
    links.new(color.outputs["Alpha"], shader.inputs["Alpha"])
    shader.inputs["Roughness"].default_value = 0.82
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    terrain.data.materials.append(material)
    return terrain


def create_ground(config: dict) -> None:
    size = float(config.get("terrain_size", 10.0))
    bpy.ops.mesh.primitive_plane_add(size=size * 2.8, location=(0.0, 0.0, -0.08))
    ground = bpy.context.object
    ground.name = "White Ground"
    material = bpy.data.materials.new("Ground Material")
    material.diffuse_color = (0.96, 0.96, 0.96, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.96, 0.96, 0.96, 1.0)
    principled.inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(material)


def create_sun(config: dict) -> None:
    azimuth = math.radians(float(config.get("sun_azimuth", 315.0)))
    elevation = math.radians(float(config.get("sun_elevation", 35.0)))
    direction = Vector((
        math.sin(azimuth) * math.cos(elevation),
        math.cos(azimuth) * math.cos(elevation),
        math.sin(elevation),
    ))
    data = bpy.data.lights.new("Sun", type="SUN")
    data.energy = float(config.get("sun_energy", 3.0))
    data.angle = math.radians(4.0)
    sun = bpy.data.objects.new("Sun", data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_camera(config: dict) -> None:
    size = float(config.get("terrain_size", 10.0))
    azimuth = math.radians(float(config.get("camera_azimuth", 225.0)))
    elevation = math.radians(float(config.get("camera_elevation", 42.0)))
    distance = size * 1.55
    camera_data = bpy.data.cameras.new("Camera")
    camera_data.type = str(config.get("camera", "ORTHO")).upper()
    if camera_data.type == "ORTHO":
        camera_data.ortho_scale = size * 1.32
    else:
        camera_data.lens = 58
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (
        distance * math.sin(azimuth) * math.cos(elevation),
        distance * math.cos(azimuth) * math.cos(elevation),
        distance * math.sin(elevation),
    )
    look_at(camera, Vector((0.0, 0.0, float(config.get("height_strength", 1.8)) * 0.25)))
    bpy.context.scene.camera = camera


def configure_render(config: dict) -> None:
    scene = bpy.context.scene
    engine = str(config.get("engine", "BLENDER_EEVEE_NEXT"))
    scene.render.engine = engine
    width, height = config.get("resolution", [1600, 1600])
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = bool(config.get("transparent_background", False))
    scene.render.filepath = config["output"]
    if engine == "CYCLES":
        scene.cycles.samples = int(config.get("samples", 64))
        scene.cycles.use_denoising = True
    else:
        scene.render.image_settings.color_mode = "RGBA"

    scene.world.color = (0.96, 0.96, 0.96)
    scene.view_settings.look = "AgX - Medium High Contrast"


def main() -> None:
    args = parse_args()
    config = load_config(args.config.resolve())
    Path(config["output"]).parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    create_terrain(config)
    create_ground(config)
    create_sun(config)
    create_camera(config)
    configure_render(config)
    if config.get("save_blend", True):
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(config["output"]).with_suffix(".blend")))
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()

