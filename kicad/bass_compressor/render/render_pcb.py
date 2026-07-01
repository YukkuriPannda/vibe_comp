import bpy
import math
import mathutils

GLB_PATH = r"D:\OtherProjects\vibe_comp\kicad\bass_compressor\render\bass_compressor.glb"
OUT_ANGLE = r"D:\OtherProjects\vibe_comp\kicad\bass_compressor\render\bass_compressor_render.png"
OUT_TOP = r"D:\OtherProjects\vibe_comp\kicad\bass_compressor\render\bass_compressor_render_top.png"

RES_X = 1920
RES_Y = 1080

# ---------------------------------------------------------------------------
# Scene setup
# ---------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.import_scene.gltf(filepath=GLB_PATH)

mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"Imported {len(mesh_objs)} mesh objects")

# ---------------------------------------------------------------------------
# Placeholders for parts KiCad's 3D library has no model for (Cherry MX key
# switch + keycap, and the panel-mount rotary pots/encoders) - these are rough
# stand-in primitives just to show something sitting at the right spot.
# ---------------------------------------------------------------------------
def make_placeholder_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    # node names are UI-locale-dependent (e.g. "プリンシプルBSDF" in Japanese) - match by type instead
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = color
    return mat


def add_placeholder_box(name, x, y, size_xyz_m, z_bottom, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z_bottom + size_xyz_m[2] / 2))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size_xyz_m
    obj.data.materials.append(make_placeholder_material(name + "Mat", color))
    return obj


def add_placeholder_cylinder(name, x, y, radius_m, height_m, z_bottom, color, roughness=0.5, metallic=0.0):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius_m, depth=height_m, location=(x, y, z_bottom + height_m / 2)
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(make_placeholder_material(name + "Mat", color, roughness, metallic))
    return obj


pcb_obj = next((o for o in mesh_objs if o.data and "PCB" in o.data.name.upper()), None)
if pcb_obj is None:
    print("WARNING: could not find PCB mesh object to anchor placeholders")
else:
    pcb_top_z = max((pcb_obj.matrix_world @ mathutils.Vector(c)).z for c in pcb_obj.bound_box)
    placeholders = []

    # SW1: Cherry MX key switch (housing) + keycap
    sw1_x, sw1_y = 132.54 / 1000.0, -172.42 / 1000.0
    placeholders.append(add_placeholder_box(
        "SW1_HousingPlaceholder", sw1_x, sw1_y, (0.0156, 0.0156, 0.0114), pcb_top_z, (0.05, 0.05, 0.05, 1.0)
    ))
    placeholders.append(add_placeholder_box(
        "SW1_KeycapPlaceholder", sw1_x, sw1_y, (0.018, 0.018, 0.010), pcb_top_z + 0.0114, (0.75, 0.1, 0.1, 1.0)
    ))

    # VR1 (Sustain) / VR2 (Level): PCB-mount rotary pots, each drawn as a
    # metal-can body + shaft + a knob cap so it reads as a finished control.
    for ref, x_mm, y_mm in (("VR1", 110.0, 72.1), ("VR2", 150.0, 72.0)):
        x, y = x_mm / 1000.0, -y_mm / 1000.0
        body = add_placeholder_cylinder(
            f"{ref}_BodyPlaceholder", x, y, 0.0048, 0.005, pcb_top_z, (0.6, 0.6, 0.62, 1.0),
            roughness=0.35, metallic=0.8,
        )
        shaft = add_placeholder_cylinder(
            f"{ref}_ShaftPlaceholder", x, y, 0.001, 0.015, pcb_top_z + 0.005, (0.75, 0.75, 0.77, 1.0),
            roughness=0.3, metallic=0.9,
        )
        knob = add_placeholder_cylinder(
            f"{ref}_KnobPlaceholder", x, y, 0.006, 0.012, pcb_top_z + 0.005 + 0.015, (0.05, 0.05, 0.05, 1.0),
        )
        placeholders += [body, shaft, knob]

    mesh_objs.extend(placeholders)
    bpy.context.view_layer.update()  # matrix_world/bound_box don't refresh until depsgraph updates
    print(f"Added {len(placeholders)} placeholder objects (SW1, VR1, VR2)")

# Combined world-space bounding box of the whole board+parts assembly.
min_co = mathutils.Vector((float('inf'),) * 3)
max_co = mathutils.Vector((float('-inf'),) * 3)
for obj in mesh_objs:
    for corner in obj.bound_box:
        world_co = obj.matrix_world @ mathutils.Vector(corner)
        for i in range(3):
            min_co[i] = min(min_co[i], world_co[i])
            max_co[i] = max(max_co[i], world_co[i])

size = max_co - min_co
center = (max_co + min_co) / 2
radius = size.length / 2.0
print("size:", size, "center:", center, "radius:", radius)

# ---------------------------------------------------------------------------
# Ground plane (simple neutral studio backdrop so the board doesn't float
# in a void)
# ---------------------------------------------------------------------------
plane_size = max(size.x, size.y) * 6.0
bpy.ops.mesh.primitive_plane_add(size=plane_size, location=(center.x, center.y, min_co.z - 0.0005))
plane = bpy.context.active_object
plane.name = "Backdrop"

def find_node(node_tree, node_type):
    for n in node_tree.nodes:
        if n.type == node_type:
            return n
    return None

plane_mat = bpy.data.materials.new("BackdropMat")
plane_mat.use_nodes = True
bsdf = find_node(plane_mat.node_tree, 'BSDF_PRINCIPLED')
bsdf.inputs["Base Color"].default_value = (0.14, 0.14, 0.15, 1.0)
bsdf.inputs["Roughness"].default_value = 0.85
for spec_name in ("Specular IOR Level", "Specular"):
    if spec_name in bsdf.inputs:
        bsdf.inputs[spec_name].default_value = 0.3
        break
plane.data.materials.append(plane_mat)

# ---------------------------------------------------------------------------
# World background (flat neutral color, no HDRI)
# ---------------------------------------------------------------------------
world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = find_node(world.node_tree, 'BACKGROUND')
bg.inputs[0].default_value = (0.22, 0.22, 0.24, 1.0)
bg.inputs[1].default_value = 0.15

# ---------------------------------------------------------------------------
# Helper: point an object at a target using a -Z-forward / Y-up convention
# (matches Blender cameras and lights)
# ---------------------------------------------------------------------------
def point_at(obj, target):
    direction = (target - obj.location)
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# ---------------------------------------------------------------------------
# Camera 1: angled "product photo" shot, looking down at the board from a
# corner, high enough / far enough to fit the whole 100x190mm board.
# ---------------------------------------------------------------------------
cam1_data = bpy.data.cameras.new("CamAngle")
cam1_data.lens_unit = 'FOV'
cam1_data.angle = math.radians(45)
cam1 = bpy.data.objects.new("CamAngle", cam1_data)
bpy.context.scene.collection.objects.link(cam1)

elevation = math.radians(42)
azimuth = math.radians(35)
distance = radius / math.sin(cam1_data.angle / 2.0) * 1.35

cam1.location = center + distance * mathutils.Vector((
    math.cos(azimuth) * math.cos(elevation),
    math.sin(azimuth) * math.cos(elevation),
    math.sin(elevation),
))
point_at(cam1, center)

# ---------------------------------------------------------------------------
# Camera 2: straight top-down orthographic view, rotated so the long axis
# of the board (Y, 190mm) maps to the wide (X) axis of a 1920x1080 frame.
# ---------------------------------------------------------------------------
cam2_data = bpy.data.cameras.new("CamTop")
cam2_data.type = 'ORTHO'
margin = 1.15
req_from_long = size.y * margin
req_from_short_scaled = size.x * margin * (RES_X / RES_Y)
cam2_data.ortho_scale = max(req_from_long, req_from_short_scaled)
cam2 = bpy.data.objects.new("CamTop", cam2_data)
bpy.context.scene.collection.objects.link(cam2)
cam2.location = (center.x, center.y, max_co.z + radius * 2.0)
cam2.rotation_euler = (0.0, 0.0, math.radians(90))

# ---------------------------------------------------------------------------
# 3-point lighting (area lights), sized/placed relative to the board so the
# setup scales sensibly for this ~0.1 x 0.19 m assembly.
# ---------------------------------------------------------------------------
def add_area_light(name, loc, target, power, size_m, color=(1.0, 1.0, 1.0)):
    data = bpy.data.lights.new(name, type='AREA')
    data.shape = 'RECTANGLE'
    data.size = size_m
    data.size_y = size_m
    data.energy = power
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    point_at(obj, target)
    return obj

key_dist = radius * 3.2
fill_dist = radius * 3.6
rim_dist = radius * 3.0

key_pos = center + key_dist * mathutils.Vector((
    math.cos(math.radians(-40)) * math.cos(math.radians(55)),
    math.sin(math.radians(-40)) * math.cos(math.radians(55)),
    math.sin(math.radians(55)),
))
fill_pos = center + fill_dist * mathutils.Vector((
    math.cos(math.radians(150)) * math.cos(math.radians(35)),
    math.sin(math.radians(150)) * math.cos(math.radians(35)),
    math.sin(math.radians(35)),
))
rim_pos = center + rim_dist * mathutils.Vector((
    math.cos(math.radians(-160)) * math.cos(math.radians(50)),
    math.sin(math.radians(-160)) * math.cos(math.radians(50)),
    math.sin(math.radians(50)),
))
top_pos = center + mathutils.Vector((0, 0, radius * 4.0))

add_area_light("KeyLight", key_pos, center, power=2.0, size_m=radius * 1.4)
add_area_light("FillLight", fill_pos, center, power=0.8, size_m=radius * 1.8, color=(0.95, 0.97, 1.0))
add_area_light("RimLight", rim_pos, center, power=1.0, size_m=radius * 1.2)
add_area_light("TopFill", top_pos, center, power=0.5, size_m=radius * 2.5)

# ---------------------------------------------------------------------------
# Render settings
# ---------------------------------------------------------------------------
scene = bpy.context.scene
available_engines = [e.identifier for e in bpy.types.RenderEngine.bl_rna.properties['bl_idname'].enum_items] if False else None

try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except TypeError:
    scene.render.engine = 'BLENDER_EEVEE'
print("Using render engine:", scene.render.engine)

scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

if hasattr(scene, "eevee"):
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 64
    if hasattr(scene.eevee, "use_gtao"):
        scene.eevee.use_gtao = True

scene.view_settings.view_transform = 'Standard'

# ---------------------------------------------------------------------------
# Render camera 1 (angled)
# ---------------------------------------------------------------------------
scene.camera = cam1
scene.render.filepath = OUT_ANGLE
bpy.ops.render.render(write_still=True)
print("Wrote", OUT_ANGLE)

# ---------------------------------------------------------------------------
# Render camera 2 (top-down)
# ---------------------------------------------------------------------------
scene.camera = cam2
scene.render.filepath = OUT_TOP
bpy.ops.render.render(write_still=True)
print("Wrote", OUT_TOP)

print("DONE")
