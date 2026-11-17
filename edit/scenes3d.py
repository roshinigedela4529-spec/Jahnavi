"""Procedural 3D scenes for the DMart Facts edit, rendered with Blender Cycles (bpy).

Usage: python3 scenes3d.py <scene> <outdir> [--test] [--frames N]
"""
import bpy, math, random, sys, os
from mathutils import Vector

FONT_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
FONT_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
FONT_RUPEE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FPS = 30
GREEN = (0.012, 0.28, 0.09)
_mats = {}


# ---------------------------------------------------------------- helpers
def reset(res=(1280, 720), samples=4):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()
    _meshes.clear()
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.05
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = FPS
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.use_overwrite = False
    sc.render.use_placeholder = True
    try:
        sc.view_settings.view_transform = 'AgX'
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        try:
            sc.view_settings.look = 'Medium High Contrast'
        except Exception:
            pass
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    sc.world = w
    return sc


def world_color(top, bottom=None, strength=1.0):
    w = bpy.context.scene.world
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    if bottom is None:
        bg.inputs[0].default_value = (*top, 1)
        bg.inputs[1].default_value = strength
        return
    # vertical gradient sky
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*bottom, 1)
    ramp.color_ramp.elements[1].position = 0.35
    ramp.color_ramp.elements[1].color = (*top, 1)
    nt.links.new(ramp.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength


def mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, emit=0.0, emit_color=None,
        coat=0.0, alpha=1.0, transmission=0.0):
    key = name
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if emit > 0:
        p.inputs["Emission Color"].default_value = (*(emit_color or color), 1)
        p.inputs["Emission Strength"].default_value = emit
    if coat:
        p.inputs["Coat Weight"].default_value = coat
    if transmission:
        p.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    _mats[key] = m
    return m


def _assign(ob, m):
    if m is not None:
        ob.data.materials.append(m)
    return ob


_meshes = {}


def _base_mesh(kind, verts=24, sub=2):
    """Unit primitives shared by many objects (linked data -> fast scene building)."""
    k = (kind, verts, sub)
    if k in _meshes:
        return _meshes[k]
    import bmesh
    bm = bmesh.new()
    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
    elif kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=1.0, radius2=1.0, depth=1.0)
    elif kind == "sphere":
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    me = bpy.data.meshes.new(f"base_{kind}_{verts}_{sub}")
    bm.to_mesh(me)
    bm.free()
    if kind != "cube":
        for p in me.polygons:
            p.use_smooth = True
        if kind == "cyl":  # flat caps
            for p in me.polygons:
                if abs(p.normal.z) > 0.9:
                    p.use_smooth = False
    me.materials.append(None)
    _meshes[k] = me
    return me


def _new_obj(me, loc, scale, m, rot=(0, 0, 0)):
    ob = bpy.data.objects.new("o", me)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.scale = scale
    ob.rotation_euler = rot
    ob.material_slots[0].link = 'OBJECT'
    ob.material_slots[0].material = m
    return ob


def box(loc, size, m=None, bevel=0.0, rot=(0, 0, 0)):
    if not bevel:
        return _new_obj(_base_mesh("cube"), loc, size, m, rot)
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.scale = size
    bpy.ops.object.transform_apply(scale=True)
    mod = ob.modifiers.new("bev", 'BEVEL')
    mod.width = bevel
    mod.segments = 2
    mod.limit_method = 'NONE'
    return _assign(ob, m)


def cyl(loc, r, depth, m=None, rot=(0, 0, 0), verts=24, smooth=True):
    return _new_obj(_base_mesh("cyl", verts), loc, (r, r, depth), m, rot)


def sphere(loc, r, m=None, sub=2):
    return _new_obj(_base_mesh("sphere", sub=sub), loc, (r, r, r), m)


def tube(p1, p2, r, m):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    ob = cyl((p1 + p2) / 2, r, d.length, m, verts=8)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = d.to_track_quat('Z', 'Y')
    return ob


def text3d(body, loc, size, m, extrude=0.1, bevel=0.01, font=FONT_BLACK, rot=(math.radians(90), 0, 0),
           align='CENTER', valign='CENTER'):
    cu = bpy.data.curves.new("txt", type='FONT')
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 2
    cu.align_x = align
    cu.align_y = valign
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    if m:
        cu.materials.append(m)
    return ob


def plane(loc, size, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.object
    ob.scale = (size[0], size[1], 1)
    return _assign(ob, m)


def sun(rot_deg, strength=3.0, color=(1, 0.95, 0.88), angle=2.0):
    bpy.ops.object.light_add(type='SUN', rotation=[math.radians(a) for a in rot_deg])
    l = bpy.context.object.data
    l.energy = strength
    l.color = color
    l.angle = math.radians(angle)
    return bpy.context.object


def area(loc, target, power, size=4, color=(1, 1, 1)):
    bpy.ops.object.light_add(type='AREA', location=loc)
    ob = bpy.context.object
    ob.data.energy = power
    ob.data.size = size
    ob.data.color = color
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob


def key(ob, attr, frame, value, interp=None):
    setattr(ob, attr, value)
    ob.keyframe_insert(data_path=attr, frame=frame)
    if interp and ob.animation_data and ob.animation_data.action:
        _set_interp(ob, interp)


def _set_interp(ob, interp):
    act = ob.animation_data.action
    curves = []
    try:
        curves = list(act.fcurves)
    except Exception:
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    curves += list(cb.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = interp


def camera(path, target_path, frames, lens=35, dof=None):
    """path/target_path: list of (frame, (x,y,z)). Smooth bezier camera move."""
    bpy.ops.object.empty_add(location=target_path[0][1])
    tgt = bpy.context.object
    bpy.ops.object.camera_add(location=path[0][1])
    cam = bpy.context.object
    cam.data.lens = lens
    cam.data.clip_end = 1000
    c = cam.constraints.new('TRACK_TO')
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    for f, p in path:
        key(cam, "location", f, p)
    for f, p in target_path:
        key(tgt, "location", f, p)
    if dof:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_object = tgt
        cam.data.dof.aperture_fstop = dof
    sc = bpy.context.scene
    sc.camera = cam
    sc.frame_start = 1
    sc.frame_end = frames
    return cam, tgt


def pop_in(ob, f0, dur=12, final=None, overshoot=1.12):
    final = tuple(final or ob.scale)
    key(ob, "scale", 1, (0.0001,) * 3)
    key(ob, "scale", max(f0, 2), (0.0001,) * 3)
    key(ob, "scale", f0 + int(dur * 0.65), tuple(s * overshoot for s in final))
    key(ob, "scale", f0 + dur, final)


def rise_in(ob, f0, dur=14):
    """Grow along z from the base (object origin must be at its base)."""
    s = tuple(ob.scale)
    key(ob, "scale", 1, (s[0], s[1], 0.0001))
    key(ob, "scale", max(f0, 2), (s[0], s[1], 0.0001))
    key(ob, "scale", f0 + int(dur * 0.7), (s[0], s[1], s[2] * 1.06))
    key(ob, "scale", f0 + dur, s)


def set_origin_base(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.context.scene.cursor.location = (ob.location.x, ob.location.y, min((ob.matrix_world @ Vector(v)).z for v in ob.bound_box))
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    ob.select_set(False)


def join(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return bpy.context.object


# ---------------------------------------------------------------- building blocks
PRODUCT_COLORS = [
    (0.85, 0.08, 0.06), (0.95, 0.55, 0.02), (0.95, 0.85, 0.1), (0.1, 0.5, 0.15), (0.05, 0.25, 0.7),
    (0.55, 0.1, 0.55), (0.9, 0.9, 0.88), (0.6, 0.3, 0.08), (0.02, 0.6, 0.6), (0.9, 0.3, 0.45),
    (0.15, 0.15, 0.18), (0.4, 0.75, 0.2), (0.75, 0.05, 0.2), (0.25, 0.45, 0.85),
]


def pmat(i, kind="box"):
    c = PRODUCT_COLORS[i % len(PRODUCT_COLORS)]
    if kind == "bottle":
        return mat(f"pb{i}", c, rough=0.12, coat=0.6)
    if kind == "can":
        return mat(f"pc{i}", c, rough=0.25, metal=0.6)
    return mat(f"pp{i}", c, rough=0.45)


def fill_shelf(x0, x1, y, z, depth, max_h, rng, facing=1):
    """Fill a shelf running along x from x0..x1 at depth center y, board top z."""
    x = x0 + 0.03
    objs = []
    while x < x1 - 0.1:
        kind = rng.choice(["box", "box", "bottle", "can", "box", "jar"])
        ci = rng.randrange(len(PRODUCT_COLORS))
        n = rng.randint(2, 5)
        if kind == "box":
            w = rng.uniform(0.18, 0.34); h = rng.uniform(0.2, min(0.42, max_h)); d = depth * 0.8
            for k in range(n):
                if x + w > x1:
                    break
                objs.append(box((x + w / 2, y, z + h / 2), (w * 0.94, d, h), pmat(ci)))
                objs.append(box((x + w / 2, y + facing * (d / 2 + 0.004), z + h * 0.5), (w * 0.8, 0.008, h * 0.38),
                                pmat((ci + 6) % len(PRODUCT_COLORS))))
                x += w
        elif kind in ("bottle", "jar", "can"):
            r = {"bottle": 0.045, "jar": 0.07, "can": 0.04}[kind]
            h = {"bottle": rng.uniform(0.26, 0.34), "jar": 0.16, "can": 0.12}[kind]
            h = min(h, max_h)
            for k in range(n + 1):
                if x + 2 * r > x1:
                    break
                for row in (-1, 1):
                    ob = cyl((x + r, y + row * depth * 0.22, z + h / 2), r, h,
                             pmat(ci, "bottle" if kind != "can" else "can"), verts=12)
                    objs.append(ob)
                    if kind == "bottle":
                        objs.append(cyl((x + r, y + row * depth * 0.22, z + h + 0.03), r * 0.4, 0.06,
                                        mat("cap", (0.9, 0.9, 0.9), 0.3), verts=8))
                x += 2 * r + 0.01
        x += rng.uniform(0.02, 0.08)
    return objs


def shelf_unit(cx, y0, y1, facing, rng, levels=5, height=2.3, depth=0.55, tags=True):
    """Shelf unit running along y (aisle direction) at x=cx; facing=+1 means products face +x."""
    metal = mat("shelfmetal", (0.75, 0.76, 0.78), 0.35, 0.6)
    back = mat("shelfback", (0.85, 0.86, 0.87), 0.6)
    tagm = mat("pricetag", (1.0, 0.82, 0.05), 0.4, emit=0.4)
    tagr = mat("pricetagred", (0.9, 0.05, 0.05), 0.4, emit=0.4)
    L = y1 - y0
    box((cx - facing * depth / 2, (y0 + y1) / 2, height / 2), (0.04, L, height), back)
    for y in [y0 + i * 1.5 for i in range(int(L / 1.5) + 1)]:
        box((cx - facing * depth / 2 + facing * 0.02, y, height / 2), (0.06, 0.05, height), metal)
    gap = (height - 0.15) / levels
    for i in range(levels):
        z = 0.12 + i * gap
        box((cx, (y0 + y1) / 2, z - 0.015), (depth, L, 0.03), metal)
        box((cx + facing * depth / 2, (y0 + y1) / 2, z - 0.02), (0.02, L, 0.06), metal)
        # products: rotate coordinate: fill along local axis, then map
        objs = fill_shelf(y0, y1, 0, 0, depth, gap - 0.06, rng, facing)
        for o in objs:
            lx, ly, lz = o.location
            o.location = (cx + ly, lx, z + lz)
            o.rotation_euler.z += math.radians(90)
        if tags:
            for y in [y0 + 0.6 + k * 1.2 for k in range(int(L / 1.2))]:
                box((cx + facing * (depth / 2 + 0.015), y, z - 0.02), (0.01, 0.12, 0.05),
                    tagm if rng.random() > 0.2 else tagr)


def supermarket_building(cx, cy, w=36, d=16, h=11, sign="DMart", glow=1.0):
    wall = mat("wall", (0.86, 0.86, 0.83), 0.6)
    glass = mat("glass", (0.03, 0.05, 0.07), 0.06, 0.8)
    inner = mat("interior", (1, 1, 1), 0.5, emit=1.6 * glow, emit_color=(1.0, 0.9, 0.75))
    green = mat("fascia", GREEN, 0.4)
    white = mat("signwhite", (1, 1, 1), 0.3, emit=2.5 * glow)
    trim = mat("trim", (0.2, 0.2, 0.22), 0.4, 0.5)
    box((cx, cy + d / 2, h / 2), (w, d, h), wall, bevel=0.05)
    box((cx, cy - 0.05, 2.7), (w * 0.82, 0.04, 4.6), mat('glasst', (0.9, 0.95, 1.0), 0.03, transmission=1.0))
    # warm lit interior behind the glass: back wall + shelf silhouettes
    box((cx, cy + 1.2, 2.7), (w * 0.82, 0.1, 4.6), inner)
    for i in range(10):
        x = cx - w * 0.38 + i * (w * 0.76 / 9)
        box((x, cy + 0.8, 1.1), (1.6, 0.5, 2.2), mat("shelfsil", (0.25, 0.22, 0.2), 0.7))
    for i in range(9):
        x = cx - w * 0.41 + i * (w * 0.82 / 8)
        box((cx * 0 + x, cy - 0.18, 2.7), (0.18, 0.1, 4.7), trim)
    box((cx, cy - 0.35, h - 1.7), (w + 0.6, 0.7, 3.2), green, bevel=0.05)
    box((cx, cy - 0.75, 5.3), (w * 0.5, 2.0, 0.3), trim)  # canopy
    if sign:
        text3d(sign, (cx, cy - 0.75, h - 1.75), 2.6, white, extrude=0.18, bevel=0.02)
    # roof parapet
    box((cx, cy + d / 2, h + 0.3), (w + 0.4, d + 0.4, 0.6), wall)


def car(x, y, color, rot=0):
    body = mat(f"car{color}", color, 0.15, 0.4, coat=1.0)
    win = mat("carglass", (0.02, 0.03, 0.04), 0.05, 0.2)
    tyre = mat("tyre", (0.02, 0.02, 0.02), 0.8)
    objs = [box((x, y, 0.65), (1.8, 4.2, 0.7), body, bevel=0.15),
            box((x, y + 0.2, 1.25), (1.6, 2.2, 0.6), win, bevel=0.15)]
    for dx in (-0.85, 0.85):
        for dy in (-1.3, 1.3):
            cyl((x + dx, y + dy, 0.35), 0.35, 0.25, tyre, rot=(0, math.radians(90), 0))
    for o in objs:
        o.rotation_euler.z = rot


def tree(x, y, s=1.0):
    trunk = mat("trunk", (0.25, 0.15, 0.08), 0.8)
    leaf = mat("leaf", (0.08, 0.3, 0.06), 0.7)
    cyl((x, y, 1.2 * s), 0.15 * s, 2.4 * s, trunk, verts=8)
    sphere((x, y, 3.0 * s), 1.4 * s, leaf, sub=2)
    sphere((x + 0.5 * s, y + 0.3 * s, 2.6 * s), 1.0 * s, leaf, sub=2)


def shopping_cart(x, y, rot=0, fill=True, rng=None):
    rng = rng or random.Random(3)
    chrome = mat("chrome", (0.9, 0.9, 0.92), 0.12, 1.0)
    red = mat("cartred", (0.75, 0.04, 0.03), 0.3, coat=0.5)
    blk = mat("tyre", (0.02, 0.02, 0.02), 0.8)
    parts = []
    L, W, z0, z1 = 0.9, 0.56, 0.55, 1.0
    # rails
    for z in [z0 + i * (z1 - z0) / 4 for i in range(5)]:
        pts = [(-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            parts.append(tube((a[0], a[1], z), (b[0], b[1], z), 0.009, chrome))
    for i in range(16):
        xx = -L / 2 + i * L / 15
        for yy in (-W / 2, W / 2):
            parts.append(tube((xx, yy, z0), (xx, yy, z1), 0.006, chrome))
        parts.append(tube((xx, -W / 2, z0), (xx, W / 2, z0), 0.006, chrome))
    for i in range(10):
        yy = -W / 2 + i * W / 9
        for xx in (-L / 2, L / 2):
            parts.append(tube((xx, yy, z0), (xx, yy, z1), 0.006, chrome))
    # chassis
    for yy in (-W / 2 + 0.05, W / 2 - 0.05):
        parts.append(tube((-L / 2, yy, z0), (-L / 2 - 0.05, yy, 0.12), 0.014, chrome))
        parts.append(tube((L / 2, yy, z0), (L / 2 - 0.1, yy, 0.12), 0.014, chrome))
        parts.append(tube((-L / 2 - 0.05, yy, 0.12), (L / 2 - 0.1, yy, 0.12), 0.014, chrome))
        parts.append(tube((-L / 2, yy, z1), (-L / 2 - 0.25, yy, z1 + 0.12), 0.012, chrome))
    handle = cyl((-L / 2 - 0.25, 0, z1 + 0.12), 0.025, W, red, rot=(math.radians(90), 0, 0))
    parts.append(handle)
    for xx in (-L / 2 - 0.05, L / 2 - 0.1):
        for yy in (-W / 2 + 0.05, W / 2 - 0.05):
            parts.append(cyl((xx, yy, 0.06), 0.06, 0.04, blk, rot=(math.radians(90), 0, 0)))
    if fill:
        for i in range(22):
            ci = rng.randrange(len(PRODUCT_COLORS))
            px = rng.uniform(-L / 2 + 0.12, L / 2 - 0.12)
            py = rng.uniform(-W / 2 + 0.1, W / 2 - 0.1)
            pz = z0 + 0.1 + rng.uniform(0, 0.3)
            k = rng.random()
            if k < 0.45:
                ob = box((px, py, pz), (rng.uniform(0.12, 0.24), rng.uniform(0.08, 0.18), rng.uniform(0.15, 0.3)),
                         pmat(ci))
                ob.rotation_euler = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, 3))
            elif k < 0.7:
                ob = cyl((px, py, pz + 0.05), 0.045, 0.3, pmat(ci, "bottle"), verts=12)
                ob.rotation_euler = (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0)
            else:
                fc = rng.choice([(1.0, 0.45, 0.02), (0.85, 0.05, 0.03), (0.4, 0.75, 0.1), (0.95, 0.85, 0.1)])
                ob = sphere((px, py, pz), 0.05, mat(f"fruit{fc}", fc, 0.35), sub=2)
            parts.append(ob)
    for p in parts:
        p.location = Vector((x, y, 0)) + _rotz(p.location, rot)
        if p.rotation_mode == 'QUATERNION':
            from mathutils import Quaternion
            p.rotation_quaternion = Quaternion((0, 0, 1), rot) @ p.rotation_quaternion
        else:
            p.rotation_euler.z += rot
    return parts


def _rotz(v, a):
    return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a), v.z))


def parent_all(objs, name="grp"):
    bpy.ops.object.empty_add(location=(0, 0, 0))
    e = bpy.context.object
    e.name = name
    for o in objs:
        o.parent = e
    return e


# ---------------------------------------------------------------- scenes
def sc_exterior():
    reset()
    world_color((0.35, 0.55, 0.95), (0.95, 0.7, 0.45), 0.9)
    sun((62, 0, -35), 4.0, (1, 0.85, 0.65))
    plane((0, 0, 0), (400, 400), mat("asphalt", (0.06, 0.06, 0.065), 0.75))
    box((0, -3, 0.08), (60, 6, 0.16), mat("sidewalk", (0.55, 0.53, 0.5), 0.8))
    supermarket_building(0, 0)
    line = mat("paint", (0.9, 0.9, 0.85), 0.6)
    for i in range(-8, 9):
        box((i * 3.2, -14, 0.01), (0.12, 5.5, 0.02), line)
        box((i * 3.2, -24, 0.01), (0.12, 5.5, 0.02), line)
    rng = random.Random(7)
    cols = [(0.7, 0.05, 0.05), (0.9, 0.9, 0.9), (0.05, 0.1, 0.3), (0.1, 0.1, 0.1), (0.6, 0.6, 0.62), (0.8, 0.5, 0.05)]
    for i, slot in enumerate([-6, -4, -1, 1, 3, 6, -3, 4]):
        car(slot * 3.2 + 1.6, -14 if i < 6 else -24, cols[i % len(cols)], rot=0)
    for x in (-26, -20, 20, 26):
        tree(x, -7, 1.1)
    for x in (-12, 12):
        cyl((x, -8, 3), 0.08, 6, mat("pole", (0.2, 0.2, 0.2), 0.4, 0.8))
    for i in range(4):
        shopping_cart(-4 + i * 0.35, -4.5, rot=math.radians(90), fill=False)
    camera([(1, (-16, -50, 2.0)), (210, (-7, -30, 4.2))],
           [(1, (0, 0, 5.5)), (210, (0, 0, 7.5))], 210, lens=30)


def sc_twin():
    reset()
    world_color((0.3, 0.5, 0.9), (0.9, 0.75, 0.55), 0.9)
    sun((55, 0, 40), 4.0, (1, 0.9, 0.75))
    plane((0, 0, 0), (500, 500), mat("grass", (0.12, 0.25, 0.06), 0.9))
    box((0, -12, 0.03), (300, 8, 0.06), mat("asphalt", (0.06, 0.06, 0.065), 0.75))
    for cx in (-24, 24):
        box((cx, 2, 0.04), (44, 30, 0.08), mat("lot", (0.12, 0.12, 0.13), 0.8))
        supermarket_building(cx, 0, w=30, d=14, h=10)
    for x in (-50, -45, 0, 45, 50):
        tree(x, -5, 1.2)
    camera([(1, (-40, -60, 30)), (120, (10, -58, 22))],
           [(1, (0, 2, 3)), (120, (2, 2, 5))], 120, lens=30)


def sc_growth():
    reset()
    world_color((0.005, 0.01, 0.025), None, 1.0)
    plane((0, 0, 0), (400, 400), mat("navyfloor", (0.01, 0.02, 0.04), 0.25, 0.3))
    gl = mat("gridline", (0.1, 1.0, 0.5), 0.5, emit=1.2, emit_color=(0.1, 1.0, 0.45))
    for i in range(-12, 13):
        box((i * 4, 0, 0.005), (0.03, 100, 0.01), gl)
        box((0, i * 4, 0.005), (100, 0.03, 0.01), gl)
    wall = mat("wall", (0.86, 0.86, 0.83), 0.6)
    green = mat("fascia", GREEN, 0.4)
    win = mat("glass", (0.95, 0.75, 0.45), 0.08, emit=2.0, emit_color=(1.0, 0.78, 0.5))
    rng = random.Random(11)
    cells = [(i, j) for i in range(-5, 6) for j in range(-4, 5)]
    cells.sort(key=lambda c: math.hypot(*c) + rng.uniform(0, 1.5))
    for n, (i, j) in enumerate(cells[:70]):
        x, y = i * 4 + 2, j * 4 + 2
        h = rng.uniform(1.0, 2.4)
        parts = [box((x, y, h / 2), (2.6, 2.0, h), wall),
                 box((x, y - 1.02, h * 0.4), (2.0, 0.05, h * 0.45), win),
                 box((x, y - 0.05, h + 0.12), (2.75, 2.15, 0.25), green)]
        bpy.ops.object.empty_add(location=(x, y, 0))
        ob = bpy.context.object
        for p in parts:
            p.parent = ob
            p.location = p.location - Vector((x, y, 0))
        f0 = 6 + int(n * 3.2)
        pop_in(ob, f0, 12, final=(1, 1, 1))
        # beacon light
        if n % 4 == 0:
            s = sphere((x, y, h + 0.45), 0.05, mat("beacon", (1, 0.8, 0.2), 0.3, emit=4.0))
            pop_in(s, f0 + 6, 8, final=(1, 1, 1))
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 30))
    bpy.context.object.data.energy = 9000
    bpy.context.object.data.size = 40
    camera([(1, (-6, -32, 14)), (270, (22, -26, 24))],
           [(1, (0, 0, 0)), (270, (0, 2, 0))], 270, lens=30)


def sc_money():
    reset()
    world_color((0.02, 0.05, 0.03), None, 1.0)
    plane((0, 0, 0), (200, 200), mat("darkfloor", (0.02, 0.04, 0.03), 0.18, 0.2))
    gold = mat("gold", (1.0, 0.72, 0.25), 0.22, 1.0)
    edge = mat("goldedge", (0.85, 0.55, 0.15), 0.35, 1.0)
    rng = random.Random(5)
    heights = [6, 9, 11, 14, 18, 22, 27, 33]
    for si, nh in enumerate(heights):
        x = (si - 3.5) * 1.25
        for k in range(nh):
            z = 0.05 + k * 0.1
            c = cyl((x + rng.uniform(-0.012, 0.012), rng.uniform(-0.012, 0.012), z), 0.5, 0.092,
                    gold, verts=40)
            f0 = 4 + si * 9 + k * 2
            key(c, "location", 1, (c.location.x, c.location.y, z + 6))
            key(c, "location", f0, (c.location.x, c.location.y, z + 6))
            key(c, "location", f0 + 8, (c.location.x, c.location.y, z))
            c.hide_render = False
            pop_in(c, f0 - 1, 4, final=(1, 1, 1), overshoot=1.0)
    note = mat("note", (0.55, 0.62, 0.45), 0.6)
    for i in range(10):
        b = box((rng.uniform(-6, 6), rng.uniform(-3.5, -1.2), 0.01 + i * 0.004), (1.6, 0.75, 0.006), note)
        b.rotation_euler.z = rng.uniform(-0.6, 0.6)
    area((-6, -6, 8), (0, 0, 1), 1500, 6, (1, 0.95, 0.85))
    area((8, 2, 5), (0, 0, 1.5), 900, 4, (0.6, 0.9, 1.0))
    area((0, 6, 3), (0, 0, 1), 600, 8)
    camera([(1, (-8.5, -11, 1.6)), (180, (5.5, -11.5, 4.0))],
           [(1, (-2, 0, 0.8)), (180, (2.5, 0, 2.2))], 180, lens=40, dof=4.0)


def sc_three():
    reset()
    world_color((0.01, 0.02, 0.015), None, 1.0)
    plane((0, 0, 0), (200, 200), mat("darkfloor", (0.02, 0.04, 0.03), 0.18, 0.2))
    green = mat("blockgreen", (0.02, 0.32, 0.1), 0.3, coat=0.6)
    white = mat("numwhite", (1, 1, 1), 0.2, emit=1.5)
    gold = mat("gold", (1.0, 0.72, 0.25), 0.22, 1.0)
    for i in range(3):
        x = (i - 1) * 3.2
        b = box((x, 0, 1.4), (2.6, 2.6, 2.8), green, bevel=0.12)
        t = text3d(str(i + 1), (x, -1.32, 1.4), 2.0, white, extrude=0.08)
        b.location.z = 1.4
        f0 = 10 + i * 22
        for ob, dy in ((b, 0.0), (t, -1.32)):
            for f, z in ((1, 14), (f0, 14), (f0 + 12, 1.25), (f0 + 16, 1.45), (f0 + 20, 1.4)):
                key(ob, "location", f, (x, dy, z))
    bar = box((0, -1.5, 0.05), (10, 0.06, 0.06), gold)
    area((-5, -7, 9), (0, 0, 1), 2200, 6)
    area((6, -3, 4), (0, 0, 1.5), 800, 3, (0.7, 1, 0.8))
    area((0, 6, 6), (0, 0, 1), 1500, 10, (0.3, 1.0, 0.5))
    camera([(1, (-3, -15, 4.8)), (255, (1.5, -12.5, 3.0))],
           [(1, (0, 0, 1.6)), (255, (0, 0, 1.4))], 255, lens=35)


def _aisle_scene(rng):
    world_color((0.9, 0.9, 0.9), None, 0.3)
    plane((0, 15, 0), (12, 60), mat("floor", (0.75, 0.74, 0.72), 0.12))
    plane((0, 15, 4.6), (12, 60), mat("ceiling", (0.9, 0.9, 0.9), 0.8), rot=(math.radians(180), 0, 0))
    for cx, fac in ((-1.6, 1), (1.6, -1)):
        shelf_unit(cx, 0, 30, fac, rng)
    lightm = mat("ceilinglight", (1, 1, 1), 0.5, emit=6.0, emit_color=(1, 0.96, 0.9))
    for y in range(1, 30, 3):
        box((0, y, 4.55), (0.4, 2.2, 0.05), lightm)
        box((-3.4, y, 4.55), (0.4, 2.2, 0.05), lightm)
        box((3.4, y, 4.55), (0.4, 2.2, 0.05), lightm)
    green = mat("fascia", GREEN, 0.4)
    white = mat("signwhite", (1, 1, 1), 0.3, emit=2.5)
    for y, label in ((8, "GROCERY"), (20, "HOUSEHOLD")):
        box((0, y, 3.6), (2.6, 0.08, 0.6), green, bevel=0.02)
        text3d(label, (0, y - 0.06, 3.6), 0.32, white, extrude=0.01, font=FONT_BOLD)
    box((0, 31, 2.3), (12, 0.2, 4.6), mat("endwall", (0.85, 0.85, 0.82), 0.7))
    box((0, 30.85, 3.6), (6, 0.1, 0.9), green)
    text3d("DMart", (0, 30.78, 3.6), 0.6, white, extrude=0.02)


def sc_aisleA():
    reset()
    rng = random.Random(21)
    _aisle_scene(rng)
    camera([(1, (0.1, -2.5, 1.65)), (285, (-0.1, 9.0, 1.55))],
           [(1, (0, 12, 1.4)), (285, (0.2, 24, 1.3))], 285, lens=28)


def sc_aisleB():
    reset()
    rng = random.Random(21)
    _aisle_scene(rng)
    shopping_cart(0.2, 9.5, rot=math.radians(80), rng=random.Random(9))
    camera([(1, (0.7, 3.0, 0.75)), (285, (0.6, 8.6, 1.05))],
           [(1, (-1.5, 6.0, 0.9)), (285, (-0.1, 10.2, 0.8))], 285, lens=32, dof=2.8)


def sc_cart():
    reset()
    world_color((0.02, 0.03, 0.025), None, 1.0)
    plane((0, 0, 0), (60, 60), mat("studiofloor", (0.05, 0.08, 0.06), 0.2, 0.1))
    bg = mat("studiobg", GREEN, 0.8, emit=0.25)
    box((0, 6, 3), (30, 0.2, 10), bg)
    parts = shopping_cart(0, 0, 0, rng=random.Random(4))
    g = parent_all(parts, "cart")
    key(g, "rotation_euler", 1, (0, 0, math.radians(-35)))
    key(g, "rotation_euler", 300, (0, 0, math.radians(55)))
    area((-2.5, -3, 3.5), (0, 0, 0.7), 220, 2.5)
    area((3, -1.5, 2), (0, 0, 0.7), 110, 2, (1.0, 0.85, 0.7))
    area((0, 3, 3), (0, 0, 0.8), 260, 3, (0.6, 1.0, 0.7))
    camera([(1, (0, -3.4, 1.7)), (300, (0.2, -2.6, 1.35))],
           [(1, (0, 0, 0.7)), (300, (0, 0, 0.75))], 300, lens=40, dof=5.6)


def sc_owned():
    reset()
    world_color((0.3, 0.5, 0.9), (0.95, 0.75, 0.55), 0.9)
    sun((50, 0, -50), 4.0, (1, 0.9, 0.75))
    plane((0, 0, 0), (400, 400), mat("grass", (0.12, 0.25, 0.06), 0.9))
    box((0, 4, 0.04), (46, 30, 0.08), mat("lot", (0.12, 0.12, 0.13), 0.8))
    supermarket_building(0, 0, w=30, d=14, h=10)
    fence = mat("fence", (0.9, 0.9, 0.9), 0.5)
    for x in range(-23, 24, 2):
        cyl((x, -11, 0.5), 0.05, 1.0, fence, verts=6)
    box((0, -11, 0.9), (46, 0.06, 0.06), fence)
    gold = mat("gold", (1.0, 0.72, 0.25), 0.22, 1.0)
    t = text3d("90%", (20, -9, 0.1), 7.5, gold, extrude=0.8, bevel=0.08, valign='BOTTOM')
    t.rotation_euler = (math.radians(90), 0, math.radians(-12))
    rise_in(t, 20, 18)
    for x in (-30, -26, 30):
        tree(x, -6, 1.2)
    camera([(1, (-26, -48, 9)), (300, (12, -46, 6))],
           [(1, (4, 0, 5)), (300, (10, 0, 5))], 300, lens=32)


def sc_warehouse():
    reset()
    world_color((0.6, 0.65, 0.7), None, 0.2)
    plane((0, 20, 0), (60, 80), mat("concrete", (0.42, 0.42, 0.4), 0.55))
    up = mat("rackblue", (0.05, 0.2, 0.6), 0.4, 0.4)
    beam = mat("rackorange", (0.95, 0.35, 0.02), 0.4, 0.3)
    wood = mat("pallet", (0.55, 0.38, 0.2), 0.8)
    card = [mat(f"card{i}", c, 0.85) for i, c in enumerate([(0.55, 0.38, 0.2), (0.62, 0.45, 0.25), (0.48, 0.32, 0.17)])]
    wrap = mat("wrap", (0.8, 0.85, 0.9), 0.15, transmission=0.0, coat=1.0)
    rng = random.Random(8)
    for rx in (-6, -2.2, 2.2, 6):
        for k in range(13):
            y = k * 2.8
            for dx in (-0.55, 0.55):
                box((rx + dx, y, 4.5), (0.1, 0.1, 9), up)
        for lvl in range(4):
            z = 0.15 + lvl * 2.2
            for dx in (-0.55, 0.55):
                box((rx + dx, 16.8, z + 0.1), (0.08, 33.6, 0.15), beam)
            for k in range(12):
                y = k * 2.8 + 1.4
                if rng.random() < 0.12:
                    continue
                box((rx, y, z + 0.25), (1.1, 1.2, 0.14), wood)
                h = rng.uniform(0.9, 1.6)
                for bx in (-0.27, 0.27):
                    for by in (-0.3, 0.3):
                        nb = int(h / 0.45)
                        for bz in range(nb):
                            box((rx + bx, y + by, z + 0.32 + 0.22 + bz * 0.45), (0.52, 0.58, 0.44),
                                rng.choice(card))
    # truck at dock
    trailer = mat("trailer", (0.92, 0.92, 0.9), 0.4, coat=0.5)
    green = mat("fascia", GREEN, 0.4)
    box((0, 42, 2.2), (2.6, 10, 3.0), trailer, bevel=0.05)
    box((0, 42, 1.4), (2.62, 10.02, 0.5), green)
    lightm = mat("whlight", (1, 1, 1), 0.5, emit=8.0)
    for y in range(0, 40, 5):
        for x in (-4, 0, 4):
            box((x, y, 10.5), (0.5, 2.5, 0.05), lightm)
    # forklift-ish
    yel = mat("forklift", (1, 0.75, 0.05), 0.4, coat=0.5)
    box((0, 27, 0.7), (1.1, 2.0, 1.0), yel, bevel=0.08)
    box((0, 26.6, 1.6), (1.0, 1.0, 0.9), mat("carglass", (0.02, 0.03, 0.04), 0.05, 0.2), bevel=0.05)
    box((0, 25.6, 1.4), (0.8, 0.1, 2.4), mat("pole", (0.2, 0.2, 0.2), 0.4, 0.8))
    area((0, 20, 10), (0, 20, 0), 8000, 20, (1, 0.97, 0.9))
    camera([(1, (0.2, -4, 6.5)), (300, (0.0, 9, 2.6))],
           [(1, (0, 10, 2.5)), (300, (0, 22, 2.2))], 300, lens=26)


def sc_podium():
    reset()
    world_color((0.005, 0.01, 0.008), None, 1.0)
    plane((0, 0, 0), (200, 200), mat("darkfloor", (0.02, 0.04, 0.03), 0.18, 0.2))
    white = mat("podiumwhite", (0.9, 0.9, 0.9), 0.25, coat=0.6)
    green = mat("blockgreen", (0.02, 0.32, 0.1), 0.3, coat=0.6)
    gold = mat("gold", (1.0, 0.72, 0.25), 0.22, 1.0)
    p1 = box((0, 0, 1.5), (2.4, 2.4, 3.0), green, bevel=0.08)
    box((-2.5, 0, 1.0), (2.4, 2.4, 2.0), white, bevel=0.08)
    box((2.5, 0, 0.7), (2.4, 2.4, 1.4), white, bevel=0.08)
    t = text3d("#1", (0, 0, 3.0), 2.4, gold, extrude=0.25, bevel=0.04, valign='BOTTOM')
    rise_in(t, 205, 18)
    text3d("DMart", (0, -1.22, 1.6), 0.6, mat("signwhite", (1, 1, 1), 0.3, emit=2.5), extrude=0.03)
    rng = random.Random(2)
    cm = [mat(f"conf{i}", c, 0.4, emit=0.3) for i, c in enumerate(
        [(1, 0.75, 0.1), (0.1, 0.8, 0.3), (1, 1, 1), (0.9, 0.1, 0.2), (0.2, 0.5, 1)])]
    for i in range(160):
        x, y = rng.uniform(-6, 6), rng.uniform(-3, 3)
        c = box((x, y, 9), (0.12, 0.06, 0.005), rng.choice(cm))
        f0 = rng.randint(1, 120)
        key(c, "location", 1, (x, y, 9 + rng.uniform(0, 3)))
        key(c, "location", f0, (x, y, 9 + rng.uniform(0, 3)))
        key(c, "location", f0 + 180, (x + rng.uniform(-1, 1), y + rng.uniform(-1, 1), -0.2))
        key(c, "rotation_euler", 1, (0, 0, 0))
        key(c, "rotation_euler", f0 + 180, (rng.uniform(5, 20), rng.uniform(5, 20), rng.uniform(0, 6)))
    bpy.ops.object.light_add(type='SPOT', location=(0, -2, 10))
    sp = bpy.context.object
    sp.data.energy = 6000
    sp.data.spot_size = math.radians(40)
    sp.rotation_euler = (math.radians(12), 0, 0)
    area((-6, -6, 5), (0, 0, 2), 900, 4, (0.6, 1.0, 0.7))
    area((6, -6, 5), (0, 0, 2), 900, 4, (1.0, 0.85, 0.6))
    camera([(1, (-4, -13, 2.0)), (285, (3, -10.5, 4.2))],
           [(1, (0, 0, 2.6)), (285, (0, 0, 3.4))], 285, lens=35)


def sc_studiobg():
    reset(res=(1920, 1080), samples=48)
    rng = random.Random(21)
    _aisle_scene(rng)
    camera([(1, (0.0, 1.5, 1.6))], [(1, (0, 20, 1.5))], 1, lens=24, dof=1.2)
    bpy.context.scene.camera.data.dof.focus_distance = 0.5


SCENES = {k[3:]: v for k, v in globals().items() if k.startswith("sc_")}

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    name, out = argv[0], argv[1]
    SCENES[name]()
    sc = bpy.context.scene
    os.makedirs(out, exist_ok=True)
    sc.render.filepath = os.path.join(out, "f_")
    if "--frames" in argv:
        fr = [int(x) for x in argv[argv.index("--frames") + 1].split(",")]
        for f in fr:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(out, f"test_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    elif name == "studiobg":
        sc.render.filepath = os.path.join(out, "studiobg.png")
        bpy.ops.render.render(write_still=True)
    else:
        sc.frame_step = 2  # rendered at 15 fps, motion-interpolated to 30 fps afterwards
        bpy.ops.render.render(animation=True)
