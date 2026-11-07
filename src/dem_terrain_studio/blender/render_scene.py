"""Build and render a terrain scene. This file is executed inside Blender."""

from __future__ import annotations

import argparse
import json
import math
import sys
from array import array
from collections import Counter
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    if "--" not in sys.argv:
        raise RuntimeError("缺少 Blender 脚本参数分隔符 --。")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)
    base = path.parent.resolve()
    for key in ("height_map", "color_map", "output", "_success_file"):
        if not config.get(key):
            continue
        value = Path(config[key]).expanduser()
        config[key] = str((base / value).resolve() if not value.is_absolute() else value.resolve())
    return config


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.materials,
        bpy.data.textures,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for item in list(datablocks):
            if item.users == 0:
                datablocks.remove(item)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _scaled_size(width: int, height: int, maximum: int) -> tuple[int, int]:
    if max(width, height) <= maximum:
        return width, height
    scale = maximum / max(width, height)
    return max(2, round(width * scale)), max(2, round(height * scale))


def _read_grayscale(image: bpy.types.Image) -> tuple[array, array]:
    width, height = image.size
    count = width * height
    raw = array("f", [0.0]) * len(image.pixels)
    image.pixels.foreach_get(raw)
    channels = len(raw) // count
    if channels not in (1, 2, 3, 4) or channels * count != len(raw):
        raise ValueError(f"无法识别 DEM 的像素通道布局: {len(raw)} 个值 / {count} 个像素。")
    gray = array("f", [0.0]) * count
    alpha = array("f", [1.0]) * count

    for pixel in range(count):
        offset = pixel * channels
        if channels <= 2:
            gray[pixel] = raw[offset]
            if channels == 2:
                alpha[pixel] = raw[offset + 1]
        else:
            if (channels == 3 or raw[offset + 3] > 0.001) and max(
                abs(raw[offset] - raw[offset + 1]), abs(raw[offset] - raw[offset + 2])
            ) > 1e-4:
                raise ValueError(
                    "DEM 的 RGB 波段不一致，不能混合为高程。请先用 tools/prepare_geodem.py "
                    "显式选择高程波段，或导出单波段灰度高程图。"
                )
            gray[pixel] = (
                0.2126 * raw[offset]
                + 0.7152 * raw[offset + 1]
                + 0.0722 * raw[offset + 2]
            )
            if channels >= 4:
                alpha[pixel] = raw[offset + 3]
    return gray, alpha


def _border_indices(width: int, height: int) -> list[int]:
    indices = list(range(width))
    if height > 1:
        indices.extend(range((height - 1) * width, height * width))
    if width > 1 and height > 2:
        for row in range(1, height - 1):
            indices.append(row * width)
            indices.append(row * width + width - 1)
    return indices


def _background_value(gray: array, alpha: array, width: int, height: int) -> float | None:
    opaque_border = [i for i in _border_indices(width, height) if alpha[i] > 0.001 and math.isfinite(gray[i])]
    if not opaque_border:
        return None
    quantized = Counter(round(gray[i], 4) for i in opaque_border)
    value, count = quantized.most_common(1)[0]
    if count / len(opaque_border) < 0.85:
        return None
    opaque_count = 0
    matching = 0
    for i, value_alpha in enumerate(alpha):
        if value_alpha > 0.001 and math.isfinite(gray[i]):
            opaque_count += 1
            if abs(gray[i] - value) <= 1e-4:
                matching += 1
    if opaque_count and matching / opaque_count > 0.995:
        return None
    return float(value)


def normalize_height_image(config: dict) -> tuple[bpy.types.Image, int, int, int, int]:
    source = bpy.data.images.load(config["height_map"], check_existing=False)
    source.colorspace_settings.name = "Non-Color"
    original_width, original_height = source.size
    if original_width < 2 or original_height < 2:
        raise ValueError("DEM 至少需要 2×2 个像素。")

    width, height = _scaled_size(original_width, original_height, int(config["max_texture_size"]))
    if (width, height) != (original_width, original_height):
        print(f"DEM 纹理过大，已从 {original_width}×{original_height} 缩小到 {width}×{height}。")
        source.scale(width, height)

    gray, alpha = _read_grayscale(source)
    background = (
        _background_value(gray, alpha, width, height)
        if config.get("detect_background", True)
        else None
    )
    tolerance = 1e-4
    valid = array("b", [0]) * (width * height)
    low = math.inf
    high = -math.inf
    valid_count = 0
    for index, value in enumerate(gray):
        is_valid = alpha[index] > 0.001 and math.isfinite(value)
        if is_valid and background is not None and abs(value - background) <= tolerance:
            is_valid = False
        if is_valid:
            valid[index] = 1
            valid_count += 1
            low = min(low, value)
            high = max(high, value)

    if valid_count == 0:
        raise ValueError("DEM 没有可用像素；请检查透明度、NoData 背景或图像内容。")
    config["_has_nodata"] = valid_count != width * height
    span = high - low
    if not math.isfinite(span):
        raise ValueError("DEM 包含无法处理的非有限高程值。")

    pixels = array("f", [0.0]) * (width * height * 4)
    for index, value in enumerate(gray):
        if valid[index]:
            normalized = 0.5 if span <= 1e-12 else min(1.0, max(0.0, (value - low) / span))
            encoded = 0.02 + normalized * 0.98
        else:
            encoded = 0.0
        offset = index * 4
        pixels[offset] = encoded
        pixels[offset + 1] = encoded
        pixels[offset + 2] = encoded
        pixels[offset + 3] = 1.0

    normalized_image = bpy.data.images.new(
        "Normalized DEM",
        width=width,
        height=height,
        alpha=True,
        float_buffer=True,
    )
    normalized_image.colorspace_settings.name = "Non-Color"
    normalized_image.pixels.foreach_set(pixels)
    normalized_image.update()
    print(
        f"DEM: {original_width}×{original_height}; 有效范围 {low:.6g}–{high:.6g}; "
        f"背景={'自动识别 ' + str(background) if background is not None else '未识别'}。"
    )
    return normalized_image, width, height, original_width, original_height


def _terrain_dimensions(config: dict, width: int, height: int) -> tuple[float, float]:
    longest = float(config["terrain_size"])
    if width >= height:
        return longest, longest * height / width
    return longest * width / height, longest


def create_terrain(config: dict) -> tuple[bpy.types.Object, float, float]:
    height_image, width, height, original_width, original_height = normalize_height_image(config)
    longest_subdivisions = int(config["subdivisions"])
    x_subdivisions = max(2, round(longest_subdivisions * width / max(width, height)))
    y_subdivisions = max(2, round(longest_subdivisions * height / max(width, height)))
    terrain_width, terrain_height = _terrain_dimensions(config, width, height)

    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=x_subdivisions,
        y_subdivisions=y_subdivisions,
        size=1.0,
        location=(0.0, 0.0, 0.0),
    )
    terrain = bpy.context.object
    terrain.name = "Terrain"
    terrain.scale = (terrain_width, terrain_height, 1.0)
    for polygon in terrain.data.polygons:
        polygon.use_smooth = True

    texture = bpy.data.textures.new("HeightMap", type="IMAGE")
    texture.image = height_image
    texture.extension = "EXTEND"
    modifier = terrain.modifiers.new("DEM Displacement", type="DISPLACE")
    modifier.texture = texture
    modifier.texture_coords = "UV"
    modifier.mid_level = 0.0
    modifier.strength = float(config["height_strength"])

    material = bpy.data.materials.new("Terrain Color")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    color = nodes.new("ShaderNodeTexImage")
    color.interpolation = "Linear"
    coordinates = nodes.new("ShaderNodeTexCoord")
    links.new(coordinates.outputs["UV"], color.inputs["Vector"])

    if config.get("color_map"):
        color_image = bpy.data.images.load(config["color_map"], check_existing=False)
        if tuple(color_image.size) != (original_width, original_height):
            raise ValueError(
                f"色带图尺寸 {color_image.size[0]}×{color_image.size[1]} 与 DEM "
                f"{original_width}×{original_height} 不一致。"
            )
        if tuple(color_image.size) != (width, height):
            color_image.scale(width, height)
        color.image = color_image
        links.new(color.outputs["Color"], shader.inputs["Base Color"])
    else:
        color.image = height_image
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "B_SPLINE"
        elements = ramp.color_ramp.elements
        elements[0].position = 0.0
        elements[0].color = (0.96, 0.96, 0.96, 1.0)
        elements[1].position = 0.019
        elements[1].color = (0.96, 0.96, 0.96, 1.0)
        for position, rgba in (
            (0.02, (0.08, 0.27, 0.45, 1.0)),
            (0.18, (0.12, 0.43, 0.45, 1.0)),
            (0.38, (0.35, 0.55, 0.30, 1.0)),
            (0.58, (0.72, 0.66, 0.30, 1.0)),
            (0.78, (0.57, 0.52, 0.45, 1.0)),
            (1.0, (0.82, 0.82, 0.80, 1.0)),
        ):
            element = elements.new(position)
            element.color = rgba
        links.new(color.outputs["Color"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], shader.inputs["Base Color"])

    if config["transparent_background"]:
        height_mask = nodes.new("ShaderNodeTexImage")
        height_mask.image = height_image
        height_mask.interpolation = "Closest"
        links.new(coordinates.outputs["UV"], height_mask.inputs["Vector"])
        visible = nodes.new("ShaderNodeMath")
        visible.operation = "GREATER_THAN"
        visible.inputs[1].default_value = 0.01
        links.new(height_mask.outputs["Color"], visible.inputs[0])
        links.new(visible.outputs[0], shader.inputs["Alpha"])
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "HASHED"

    shader.inputs["Roughness"].default_value = 0.82
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    terrain.data.materials.append(material)
    # Apply displacement before constructing a flat-bottomed rectangular block.
    # NoData masks still use the material; arbitrary province outlines need a
    # separate boundary mesh and are deliberately not claimed here.
    bpy.context.view_layer.objects.active = terrain
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    base_material = bpy.data.materials.new("Terrain Base Material")
    base_material.use_nodes = True
    base_shader = base_material.node_tree.nodes.get("Principled BSDF")
    base_shader.inputs["Base Color"].default_value = (0.34, 0.31, 0.26, 1.0)
    base_shader.inputs["Roughness"].default_value = 0.9
    terrain.data.materials.append(base_material)
    if not config["_has_nodata"]:
        mesh = bmesh.new()
        mesh.from_mesh(terrain.data)
        boundary = [edge for edge in mesh.edges if edge.is_boundary]
        extruded = bmesh.ops.extrude_edge_only(mesh, edges=boundary)["geom"]
        for item in extruded:
            if isinstance(item, bmesh.types.BMVert):
                item.co.z = -0.02
            elif isinstance(item, bmesh.types.BMFace):
                item.material_index = 1
        lower_edges = [edge for edge in mesh.edges if edge.is_boundary]
        for face in bmesh.ops.holes_fill(mesh, edges=lower_edges, sides=0)["faces"]:
            face.material_index = 1
        bmesh.ops.recalc_face_normals(mesh, faces=list(mesh.faces))
        mesh.to_mesh(terrain.data)
        mesh.free()
    # Pack generated/loaded textures so reopening the saved blend is portable.
    height_image.pack()
    if config.get("color_map"):
        color_image.pack()
    return terrain, terrain_width, terrain_height


def create_ground(config: dict, terrain_width: float, terrain_height: float) -> None:
    size = max(terrain_width, terrain_height) * 2.8
    ground_z = -max(0.04, float(config["height_strength"]) * 0.02)
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 0.0, ground_z))
    ground = bpy.context.object
    ground.name = "White Ground"
    material = bpy.data.materials.new("Ground Material")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.96, 0.96, 0.96, 1.0)
    principled.inputs["Roughness"].default_value = 0.9
    ground.data.materials.append(material)


def create_sun(config: dict) -> None:
    azimuth = math.radians(float(config["sun_azimuth"]))
    elevation = math.radians(float(config["sun_elevation"]))
    sun_position = Vector(
        (
            math.sin(azimuth) * math.cos(elevation),
            math.cos(azimuth) * math.cos(elevation),
            math.sin(elevation),
        )
    )
    data = bpy.data.lights.new("Sun", type="SUN")
    data.energy = float(config["sun_energy"])
    data.angle = math.radians(4.0)
    sun = bpy.data.objects.new("Sun", data)
    bpy.context.collection.objects.link(sun)
    sun.location = sun_position * 10.0
    look_at(sun, Vector((0.0, 0.0, 0.0)))


def create_camera(config: dict, terrain_width: float, terrain_height: float) -> None:
    size = max(terrain_width, terrain_height)
    azimuth = math.radians(float(config["camera_azimuth"]))
    elevation = math.radians(float(config["camera_elevation"]))
    distance = size * 1.8 + float(config["height_strength"])
    camera_data = bpy.data.cameras.new("Camera")
    camera_data.type = config["camera"]
    if camera_data.type == "ORTHO":
        camera_data.ortho_scale = size * 1.38 + float(config["height_strength"]) * 0.25
    else:
        camera_data.lens = 58
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (
        distance * math.sin(azimuth) * math.cos(elevation),
        distance * math.cos(azimuth) * math.cos(elevation),
        distance * math.sin(elevation),
    )
    look_at(camera, Vector((0.0, 0.0, float(config["height_strength"]) * 0.3)))
    bpy.context.scene.camera = camera


def configure_render(config: dict) -> None:
    scene = bpy.context.scene
    engine = config["engine"]
    if bpy.app.version >= (5, 0, 0) and engine == "BLENDER_EEVEE_NEXT":
        engine = "BLENDER_EEVEE"
    elif bpy.app.version < (5, 0, 0) and engine == "BLENDER_EEVEE":
        engine = "BLENDER_EEVEE_NEXT"
    scene.render.engine = engine
    width, height = config["resolution"]
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = config["transparent_background"]
    scene.render.filepath = config["output"]
    if engine == "CYCLES":
        scene.cycles.samples = config["samples"]
        scene.cycles.use_denoising = True

    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.96, 0.96, 0.96, 1.0)
    background.inputs["Strength"].default_value = 0.8
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.8


def write_success(config: dict) -> None:
    output = Path(config["output"])
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("渲染命令结束，但输出 PNG 不存在或为空。")
    success = Path(config["_success_file"])
    success.write_text(
        json.dumps({"output": str(output), "bytes": output.stat().st_size}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    config = load_config(args.config.resolve())
    Path(config["output"]).parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    _terrain, terrain_width, terrain_height = create_terrain(config)
    if not config["transparent_background"]:
        create_ground(config, terrain_width, terrain_height)
    create_sun(config)
    create_camera(config, terrain_width, terrain_height)
    configure_render(config)
    if config["save_blend"]:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(config["output"]).with_suffix(".blend")))
    bpy.ops.render.render(write_still=True)
    write_success(config)


if __name__ == "__main__":
    main()
