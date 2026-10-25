# Fibre-laser gantry engraver of the start-page hero (web/src/home/laser-machine.glb).
# Headless: blender -b -P web/scripts/laser-machine.blender.py -- web/src/home
# In a live Blender: exec this file with OUT set; it rebuilds only the "LaserMachine" collection.
#
# Units are the hero scene's world units. Blender is Z-up; the glTF exporter writes +Y up, so
# Blender (x, y, z) is scene (x, z, -y). Three root nodes, the scene moves two of them:
#   Frame  — static rails on the pedestal top (scene y = -0.05) at x = ±RAIL_X;
#   Bridge — moves along scene z (Bridge.z = head.z + BRIDGE_DZ); its origin is the scene origin;
#   Head   — moves in x/z; origin at the lens exit, the head and its carriage above it.
# Materials follow the LASSARD graver-portal model of the team (linear base colours).
import bpy, math, os, sys
from mathutils import Vector

RAIL_X = 1.06
BRIDGE_DZ = -0.27
LENS_Y = 0.3
BRIDGE_Y = LENS_Y + 0.5
TOP = -0.05  # pedestal top

if "--" in sys.argv:
    OUT = sys.argv[sys.argv.index("--") + 1]
else:
    OUT = globals().get("OUT", ".")
PREVIEW = globals().get("PREVIEW", False)

if bpy.app.background:
    bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def collection(name):
    c = bpy.data.collections.get(name)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    else:
        c = bpy.data.collections.new(name)
        scene.collection.children.link(c)
    return c


COL = collection("LaserMachine")
# Meshes of a previous run keep the root names; free them so the new roots get them.
for me in list(bpy.data.meshes):
    if me.users == 0:
        bpy.data.meshes.remove(me)


def mat(name, rgb, metal, rough, emit=0.0):
    # Own "Hero …" names: in a live Blender with another file open, never change its materials.
    name = "Hero " + name
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = emit
    return m


WHITE = mat("LASSARD warm white powder-coated steel", (0.888, 0.888, 0.871), 0.32, 0.36)
GRAPHITE = mat("LASSARD graphite", (0.011, 0.014, 0.019), 0.35, 0.42)
RED = mat("LASSARD signal red", (0.68, 0.010, 0.014), 0.25, 0.33, 0.35)
STEEL = mat("stainless steel", (0.479, 0.509, 0.527), 0.9, 0.22)
ALU = mat("brushed anodized aluminium", (0.62, 0.64, 0.66), 0.82, 0.31)
RUBBER = mat("black rubber", (0.006, 0.007, 0.008), 0.02, 0.83)
GLASS = mat("lens glass", (0.005, 0.012, 0.019), 0.18, 0.05)
LED = mat("status LED", (1.0, 0.05, 0.03), 0.0, 0.3, 14.0)

parts = {"Frame": [], "Bridge": [], "Head": []}


def keep(root, o, m, bevel=0.0, segs=2):
    o.data.materials.append(m)
    if bevel:
        b = o.modifiers.new("Bevel", "BEVEL")
        b.width, b.segments, b.limit_method = bevel, segs, "ANGLE"
    for c in o.users_collection:
        c.objects.unlink(o)
    COL.objects.link(o)
    parts[root].append(o)
    return o


def box(root, size, loc, m, bevel=0.0, segs=2, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    return keep(root, o, m, bevel, segs)


def cyl(root, r, depth, loc, m, verts=32, axis="Z", bevel=0.0):
    rot = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.object
    bpy.ops.object.transform_apply(rotation=True)
    return keep(root, o, m, bevel, 2)


def tube(root, pts, r, m):
    cu = bpy.data.curves.new("Tube", "CURVE")
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution = "3D", r, 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new("Tube", cu)
    COL.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.object
    o.data.materials.append(m)
    parts[root].append(o)
    return o


def chain(root, start, n, step=0.03, axis=Vector((1, 0, 0)), width=0.06, height=0.022):
    """Energy chain: black links with graphite side straps along a straight run."""
    for k in range(n):
        c = Vector(start) + axis * (k * step)
        box(root, (step * 0.86, width, height), c, RUBBER)
        for s in (-1, 1):
            box(root, (step * 0.7, 0.004, height * 1.25), c + Vector((0, s * (width / 2 + 0.002), 0)), GRAPHITE)


def chain_loop(root, centre, radius, n, width=0.06):
    """Half loop of links in the x–z plane, from the top run down to the bottom run (+x side)."""
    for k in range(n + 1):
        a = math.pi / 2 - math.pi * k / n
        c = Vector(centre) + Vector((math.cos(a) * radius, 0, math.sin(a) * radius))
        box(root, (0.026, width, 0.022), c, RUBBER, rot=(0, -a + math.pi / 2, 0))


# ---------------------------------------------------------------- Frame (static)
for s in (-1, 1):
    x = s * RAIL_X
    box("Frame", (0.09, 1.56, 0.036), (x, 0.2, TOP + 0.018), WHITE, 0.004)
    box("Frame", (0.002, 1.54, 0.007), (x + s * 0.0451, 0.2, TOP + 0.018), GRAPHITE)  # T-slot
    box("Frame", (0.026, 1.5, 0.02), (x, 0.2, TOP + 0.046), STEEL, 0.002)  # linear guide
    for g in (-1, 1):
        box("Frame", (0.0016, 1.5, 0.004), (x + g * 0.0131, 0.2, TOP + 0.046), GRAPHITE)
    for k in range(15):
        cyl("Frame", 0.0045, 0.002, (x, -0.5 + k * 0.1, TOP + 0.0562), GRAPHITE, 12)
    for e in (-1, 1):
        y = 0.2 + e * 0.79
        box("Frame", (0.1, 0.03, 0.055), (x, y, TOP + 0.0275), GRAPHITE, 0.003)
        cyl("Frame", 0.009, 0.012, (x, y - e * 0.021, TOP + 0.03), RED, 16, "Y")
# Cable tray along the right rail with the fixed run of the y-axis chain.
tx = RAIL_X + 0.1
box("Frame", (0.07, 1.5, 0.004), (tx, 0.2, TOP + 0.002), WHITE)
for g in (-1, 1):
    box("Frame", (0.004, 1.5, 0.032), (tx + g * 0.033, 0.2, TOP + 0.016), WHITE, 0.001)
chain("Frame", (tx, -0.45, TOP + 0.016), 46, axis=Vector((0, 1, 0)), width=0.05, height=0.02)

# ---------------------------------------------------------------- Bridge (moves along z)
for s in (-1, 1):
    x = s * RAIL_X
    box("Bridge", (0.06, 0.13, 0.03), (x, 0, TOP + 0.071), GRAPHITE, 0.003)  # carriage block
    for e in (-1, 1):
        box("Bridge", (0.058, 0.004, 0.022), (x, e * 0.067, TOP + 0.069), RED)
    box("Bridge", (0.13, 0.22, 0.02), (x, 0, TOP + 0.096), GRAPHITE, 0.003)  # foot plate
    for bx in (-0.045, 0.045):
        for by in (-0.085, 0.085):
            cyl("Bridge", 0.006, 0.004, (x + bx, by, TOP + 0.108), STEEL, 12)
    h = BRIDGE_Y - (TOP + 0.106)
    box("Bridge", (0.09, 0.14, h), (x, 0, TOP + 0.106 + h / 2), WHITE, 0.008, 3)  # column
    box("Bridge", (0.03, 0.002, h - 0.12), (x, -0.0705, TOP + 0.106 + h / 2), GRAPHITE)
    # Y-axis servo on the outer side of the column.
    mx = x + s * 0.085
    box("Bridge", (0.065, 0.065, 0.075), (mx, 0, TOP + 0.16), GRAPHITE, 0.004)
    box("Bridge", (0.067, 0.067, 0.012), (mx, 0, TOP + 0.204), STEEL, 0.002)
    cyl("Bridge", 0.012, 0.02, (mx, 0, TOP + 0.22), STEEL, 16)
    box("Bridge", (0.03, 0.002, 0.02), (mx, -0.0335, TOP + 0.16), RED)
# Beam: white extrusion with T-slots, graphite X track with polished rails, red stripe.
box("Bridge", (2.26, 0.13, 0.11), (0, 0, BRIDGE_Y), WHITE, 0.008, 3)
for g in (-1, 1):
    box("Bridge", (2.2, 0.006, 0.002), (0, g * 0.03, BRIDGE_Y + 0.0551), GRAPHITE)
    box("Bridge", (2.2, 0.002, 0.006), (0, 0.0651, BRIDGE_Y + g * 0.025), GRAPHITE)
    box("Bridge", (0.012, 0.136, 0.116), (g * 1.136, 0, BRIDGE_Y), GRAPHITE, 0.002)
box("Bridge", (2.12, 0.02, 0.06), (0, -0.075, BRIDGE_Y + 0.01), GRAPHITE, 0.003)
for g in (-1, 1):
    box("Bridge", (2.1, 0.008, 0.01), (0, -0.088, BRIDGE_Y + 0.01 + g * 0.02), STEEL, 0.001)
box("Bridge", (2.12, 0.002, 0.012), (0, -0.0655, BRIDGE_Y - 0.038), RED)
# X-axis servo on the right end cap.
box("Bridge", (0.075, 0.07, 0.07), (1.185, 0, BRIDGE_Y), GRAPHITE, 0.004)
box("Bridge", (0.012, 0.072, 0.072), (1.227, 0, BRIDGE_Y), STEEL, 0.002)
# Fixed run of the X chain on top of the beam, in a graphite channel.
box("Bridge", (2.06, 0.074, 0.01), (0, 0.01, BRIDGE_Y + 0.06), GRAPHITE, 0.002)
chain("Bridge", (-1.0, 0.01, BRIDGE_Y + 0.076), 67)

# ---------------------------------------------------------------- Head (origin at the lens exit)
cyl("Head", 0.068, 0.1, (0, 0, 0.05), GRAPHITE, 48, bevel=0.002)  # F-theta lens
for k in range(36):
    a = k / 36 * math.tau
    box("Head", (0.006, 0.006, 0.042), (math.cos(a) * 0.0695, math.sin(a) * 0.0695, 0.058), STEEL, rot=(0, 0, a))
cyl("Head", 0.072, 0.012, (0, 0, 0.106), RED, 48, bevel=0.001)
cyl("Head", 0.08, 0.02, (0, 0, 0.122), STEEL, 48, bevel=0.002)
cyl("Head", 0.058, 0.004, (0, 0, 0.002), GRAPHITE, 48)
cyl("Head", 0.05, 0.002, (0, 0, 0.0005), GLASS, 48)
# Galvo housing: white body, graphite top and optical face, fins, label, LED, screws.
box("Head", (0.34, 0.25, 0.19), (0, 0, 0.227), WHITE, 0.014, 3)
box("Head", (0.32, 0.23, 0.016), (0, 0, 0.329), ALU, 0.004)
for k in range(6):
    box("Head", (0.12, 0.008, 0.003), (-0.05, -0.06 + k * 0.024, 0.3375), GRAPHITE, 0.001)  # vents
box("Head", (0.342, 0.252, 0.003), (0, 0, 0.29), GRAPHITE)  # panel seam
box("Head", (0.22, 0.004, 0.13), (-0.02, -0.126, 0.227), GRAPHITE, 0.002)
box("Head", (0.12, 0.002, 0.032), (-0.03, -0.1285, 0.255), STEEL)
box("Head", (0.09, 0.002, 0.007), (-0.045, -0.1285, 0.204), RED)
cyl("Head", 0.008, 0.004, (0.06, -0.128, 0.27), LED, 16, "Y")
cyl("Head", 0.012, 0.002, (0.06, -0.1265, 0.27), STEEL, 16, "Y")
for sx in (-0.115, 0.075):
    for sz in (0.172, 0.282):
        cyl("Head", 0.004, 0.003, (sx, -0.1285, sz), STEEL, 12, "Y")
for k in range(8):
    box("Head", (0.022, 0.006, 0.15), (-0.181, -0.09 + k * 0.0257, 0.227), GRAPHITE, 0.001)
# Collimator on the right side with its gland and strain relief.
cyl("Head", 0.036, 0.022, (0.181, 0, 0.26), GRAPHITE, 32, "X", 0.002)
cyl("Head", 0.031, 0.13, (0.257, 0, 0.26), STEEL, 32, "X", 0.002)
cyl("Head", 0.034, 0.012, (0.325, 0, 0.26), RED, 32, "X")
cyl("Head", 0.019, 0.04, (0.35, 0, 0.26), RUBBER, 24, "X")
# Z slide and X carriage: the head hangs on the bridge track (track front at y = 0.185).
box("Head", (0.16, 0.03, 0.36), (0, 0.142, 0.33), GRAPHITE, 0.004)
for gx in (-0.06, 0.06):
    cyl("Head", 0.006, 0.22, (gx, 0.124, 0.34), STEEL, 16)
box("Head", (0.26, 0.055, 0.2), (0, 0.157, 0.5), WHITE, 0.008, 3)
box("Head", (0.2, 0.004, 0.012), (0, 0.1285, 0.47), RED)
for bx in (-0.09, 0.09):
    for bz in (0.43, 0.57):
        cyl("Head", 0.005, 0.003, (bx, 0.129, bz), STEEL, 12, "Y")
# Moving end of the X chain: an arm over the beam, the top run and the loop down to the beam.
top_z = BRIDGE_Y + 0.076 - LENS_Y + 0.1
box("Head", (0.07, 0.014, top_z - 0.6), (0, 0.137, (0.6 + top_z) / 2), GRAPHITE, 0.002)  # riser
box("Head", (0.07, 0.15, 0.014), (0, 0.205, top_z - 0.018), GRAPHITE, 0.002)  # arm over the beam
chain("Head", (0.03, 0.27, top_z), 10)
chain_loop("Head", (0.33, 0.27, top_z - 0.05), 0.05, 7)
# Fibre: from the collimator up into the chain arm — never hanging in the air.
tube("Head", [(0.37, 0, 0.26), (0.4, 0.05, 0.36), (0.25, 0.17, 0.56), (0.06, 0.24, top_z - 0.005)], 0.011, RUBBER)

# ---------------------------------------------------------------- join, export
roots = {}
for name, objs in parts.items():
    for o in objs:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        for mdf in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=mdf.name)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    j = bpy.context.object
    j.name = j.data.name = name
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32))
    except Exception:
        bpy.ops.object.shade_smooth()
    scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    roots[name] = j
    print(name, "TRIS", sum(len(p.vertices) - 2 for p in j.data.polygons))

bpy.ops.object.select_all(action="DESELECT")
for o in roots.values():
    o.select_set(True)
os.makedirs(OUT, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "laser-machine.glb"), export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_texcoords=False)
print("EXPORTED", os.path.join(OUT, "laser-machine.glb"))

# Preview pose (live Blender only): bridge at scene z = BRIDGE_DZ, head over the plate.
if PREVIEW:
    roots["Bridge"].location = (0, -BRIDGE_DZ, 0)
    roots["Head"].location = (0.35, 0, LENS_Y)
