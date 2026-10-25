# «Оптика» theme page change: a camera flies after a laser beam across an optical table —
# mirrors in kinematic mounts, a lens telescope, a periscope, a beam splitter, a focusing lens —
# and the beam ends in the lens of the camera (white flash). Rendered to frames, encoded by
# optic-film.sh into web/public/film/optic-{portrait,landscape}.mp4.
# Run: blender -b --factory-startup --python optic-film.blender.py -- <out_dir> <portrait|landscape> [frames|stills] [samples]
import bpy, math, os, sys
from mathutils import Vector, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "."
ASPECT = argv[1] if len(argv) > 1 else "portrait"
MODE = argv[2] if len(argv) > 2 else "stills"
SAMPLES = int(argv[3]) if len(argv) > 3 else 64
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "..", "src", "ui", "logo-lassard.svg")

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
FPS, F_END = 30, 54
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, F_END


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def bsdf_of(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def mat(name, hexc, metal=0.0, rough=0.4, coat=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = bsdf_of(m)
    b.inputs["Base Color"].default_value = (*srgb(hexc), 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(hexc), 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


ANOD = mat("Anodised graphite", "#2b2c33", 0.85, 0.32)
RED = mat("Red anodised", "#dd191c", 0.7, 0.3)
STEEL = mat("Steel", "#d9dce1", 1.0, 0.18)
WHITE = mat("Laser body", "#f3f4f6", 0.0, 0.28, coat=0.6)
MIRROR = mat("Mirror", "#ffffff", 1.0, 0.015)
LEDRED = mat("LED", "#ff2a1a", 0.0, 0.3, emit=25.0)

GLASS = bpy.data.materials.new("Glass")
GLASS.use_nodes = True
g = bsdf_of(GLASS)
g.inputs["Base Color"].default_value = (0.96, 0.99, 1.0, 1)
g.inputs["Roughness"].default_value = 0.0
g.inputs["IOR"].default_value = 1.52
g.inputs["Transmission Weight"].default_value = 1.0
g.inputs["Coat Weight"].default_value = 0.0

# Beam splitter coating: half glass, half mirror.
COATING = bpy.data.materials.new("Splitter coating")
COATING.use_nodes = True
nt = COATING.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
o_ = nt.nodes.new("ShaderNodeOutputMaterial")
mx = nt.nodes.new("ShaderNodeMixShader")
gl = nt.nodes.new("ShaderNodeBsdfGlossy")
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
gl.inputs["Roughness"].default_value = 0.02
gl.inputs["Color"].default_value = (1.0, 0.75, 0.75, 1)
mx.inputs["Fac"].default_value = 0.45
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(gl.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], o_.inputs["Surface"])


def table_material():
    # Light satin table top with the M6 hole grid at 25 mm.
    m = bpy.data.materials.new("Optical table")
    m.use_nodes = True
    t = m.node_tree
    b = bsdf_of(m)
    b.inputs["Base Color"].default_value = (*srgb("#e8eaee"), 1)
    b.inputs["Roughness"].default_value = 0.42
    b.inputs["Metallic"].default_value = 0.35
    tc = t.nodes.new("ShaderNodeTexCoord")
    sc_ = t.nodes.new("ShaderNodeVectorMath"); sc_.operation = "SCALE"; sc_.inputs["Scale"].default_value = 40.0
    fr = t.nodes.new("ShaderNodeVectorMath"); fr.operation = "FRACTION"
    sub = t.nodes.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    cmb = t.nodes.new("ShaderNodeCombineXYZ")
    ln = t.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"
    rmp = t.nodes.new("ShaderNodeMapRange")
    rmp.inputs["From Min"].default_value = 0.16
    rmp.inputs["From Max"].default_value = 0.2
    rmp.inputs["To Min"].default_value = 0.0
    rmp.inputs["To Max"].default_value = 1.0
    hole = t.nodes.new("ShaderNodeMix"); hole.data_type = "RGBA"
    hole.inputs["A"].default_value = (*srgb("#8e9199"), 1)
    hole.inputs["B"].default_value = (*srgb("#e8eaee"), 1)
    rough = t.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.8
    rough.inputs["To Max"].default_value = 0.42
    t.links.new(tc.outputs["Object"], sc_.inputs[0])
    t.links.new(sc_.outputs[0], fr.inputs[0])
    t.links.new(fr.outputs[0], sub.inputs[0])
    t.links.new(sub.outputs[0], sep.inputs[0])
    t.links.new(sep.outputs["X"], cmb.inputs["X"])
    t.links.new(sep.outputs["Y"], cmb.inputs["Y"])
    t.links.new(cmb.outputs[0], ln.inputs[0])
    t.links.new(ln.outputs["Value"], rmp.inputs["Value"])
    t.links.new(rmp.outputs["Result"], hole.inputs["Factor"])
    t.links.new(hole.outputs["Result"], b.inputs["Base Color"])
    t.links.new(rmp.outputs["Result"], rough.inputs["Value"])
    t.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    return m


def beam_material(name, strength, edge_soft):
    """Emission tube cut at the beam head: object property 'reveal' (0..1 along the tube)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        t.nodes.remove(n)
    out = t.nodes.new("ShaderNodeOutputMaterial")
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.035, 0.02, 1)
    tr = t.nodes.new("ShaderNodeBsdfTransparent")
    mix = t.nodes.new("ShaderNodeMixShader")
    gen = t.nodes.new("ShaderNodeTexCoord")
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    attr = t.nodes.new("ShaderNodeAttribute"); attr.attribute_type = "OBJECT"; attr.attribute_name = "reveal"
    cut = t.nodes.new("ShaderNodeMath"); cut.operation = "LESS_THAN"
    lw = t.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = edge_soft
    inv = t.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    pw = t.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 2.0
    fac = t.nodes.new("ShaderNodeMath"); fac.operation = "MULTIPLY"
    st = t.nodes.new("ShaderNodeMath"); st.operation = "MULTIPLY"; st.inputs[1].default_value = strength
    t.links.new(gen.outputs["Generated"], sep.inputs[0])
    t.links.new(sep.outputs["Z"], cut.inputs[0])
    t.links.new(attr.outputs["Fac"], cut.inputs[1])
    t.links.new(lw.outputs["Facing"], inv.inputs[1])
    t.links.new(inv.outputs[0], pw.inputs[0])
    t.links.new(pw.outputs[0], fac.inputs[0])
    t.links.new(cut.outputs[0], fac.inputs[1])
    t.links.new(fac.outputs[0], st.inputs[0])
    t.links.new(st.outputs[0], em.inputs["Strength"])
    t.links.new(fac.outputs[0], mix.inputs["Fac"])
    t.links.new(tr.outputs[0], mix.inputs[1])
    t.links.new(em.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


CORE = beam_material("Beam core", 220.0, 0.15)
HALO = beam_material("Beam halo", 3.5, 0.6)


def obj_finish(o, m, bevel=0.0, smooth=True):
    o.data.materials.append(m)
    if bevel:
        b = o.modifiers.new("Bevel", "BEVEL")
        b.width = bevel
        b.segments = 3
        b.limit_method = "ANGLE"
    if smooth:
        try:
            o.data.shade_smooth() if hasattr(o.data, "shade_smooth") else None
            bpy.ops.object.select_all(action="DESELECT")
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
        except Exception:
            pass
    return o


def box(size, loc, m, bevel=0.002, rot=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.scale = size
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    return obj_finish(o, m, bevel)


def cyl(r, h, loc, m, axis=Vector((0, 0, 1)), verts=48, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc)
    o = bpy.context.object
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized())
    bpy.ops.object.transform_apply(rotation=True)
    return obj_finish(o, m, bevel)


def post(x, y, top):
    """Steel post in a graphite post holder on a clamping fork."""
    holder_h = min(0.06, top * 0.45)
    cyl(0.0125, holder_h, (x, y, holder_h / 2), ANOD, verts=40, bevel=0.0015)
    cyl(0.006, top - holder_h + 0.004, (x, y, holder_h + (top - holder_h) / 2), STEEL, verts=24)
    box((0.07, 0.026, 0.009), (x, y, 0.0045), ANOD, 0.002)
    cyl(0.0055, 0.004, (x + 0.024, y, 0.011), STEEL, verts=20)
    cyl(0.0055, 0.004, (x - 0.024, y, 0.011), STEEL, verts=20)


def frame_quat(normal):
    """Rotation taking local +Z to the normal, local +Y as close to world up as possible."""
    n = Vector(normal).normalized()
    up = Vector((0, 0, 1)) if abs(n.z) < 0.95 else Vector((0, 1, 0))
    x = up.cross(n).normalized()
    y = n.cross(x)
    from mathutils import Matrix
    return Matrix((x, y, n)).transposed().to_quaternion()


def mirror_mount(p, normal):
    q = frame_quat(normal)
    p = Vector(p)
    L = lambda v: p + q @ Vector(v)
    cyl(0.0127, 0.006, L((0, 0, 0.001)), MIRROR, axis=q @ Vector((0, 0, 1)), verts=64, bevel=0.0006)
    cyl(0.0152, 0.004, L((0, 0, -0.003)), ANOD, axis=q @ Vector((0, 0, 1)), verts=64)
    box((0.05, 0.05, 0.011), L((0, 0, -0.0105)), ANOD, 0.0025, rot=q)
    box((0.05, 0.05, 0.009), L((0, 0, -0.024)), ANOD, 0.0025, rot=q)
    for kx, ky in ((0.017, 0.017), (-0.017, -0.017)):
        cyl(0.0042, 0.024, L((kx, ky, -0.04)), STEEL, axis=q @ Vector((0, 0, 1)), verts=24)
        cyl(0.0065, 0.012, L((kx, ky, -0.056)), RED, axis=q @ Vector((0, 0, 1)), verts=32, bevel=0.001)
    bottom = min(L((x, y, z)).z for x in (-0.025, 0.025) for y in (-0.025, 0.025) for z in (-0.005, -0.028))
    post(p.x, p.y, bottom + 0.002)


def lens_mount(p, axis, flat=0.28):
    p, axis = Vector(p), Vector(axis).normalized()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0127, segments=64, ring_count=32, location=p)
    lens = bpy.context.object
    lens.scale = (1, 1, flat)
    lens.rotation_mode = "QUATERNION"
    lens.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis)
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    obj_finish(lens, GLASS)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0155, minor_radius=0.0042, major_segments=64, minor_segments=16, location=p)
    ring = bpy.context.object
    ring.scale = (1, 1, 1.4)
    ring.rotation_mode = "QUATERNION"
    ring.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis)
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    obj_finish(ring, ANOD)
    cyl(0.003, 0.012, p + Vector((0, 0, 0.0205)), RED, verts=20)
    post(p.x, p.y, p.z - 0.018)


# --- scene geometry -------------------------------------------------------------------------
H, H2 = 0.08, 0.22
P = {
    "src": Vector((0.0, 0.0, H)),
    "m1": Vector((0.32, 0.0, H)),
    "m2": Vector((0.32, 0.44, H)),
    "m3": Vector((0.32, 0.44, H2)),
    "bs": Vector((0.12, 0.44, H2)),
    "l3": Vector((-0.04, 0.44, H2)),
    "m4": Vector((-0.20, 0.44, H2)),
}
L1, L2 = Vector((0.32, 0.13, H)), Vector((0.32, 0.29, H))
FOCUS = (L1 + L2) / 2
CAM_END = Vector((-0.20, 0.20, H2 + 0.003))   # M4 sends the beam here: into the camera.
DET = Vector((0.12, 0.62, H2))

bpy.ops.mesh.primitive_plane_add(size=1, location=(0.1, 0.5, 0))
tbl = bpy.context.object
tbl.scale = (5.0, 4.0, 1)
bpy.ops.object.transform_apply(scale=True)
tbl.data.materials.append(table_material())

# Laser source: white body, red band, LASSARD logo on the side, aperture with a steel ring.
box((0.34, 0.085, 0.075), (-0.17, 0, H), WHITE, 0.008)
box((0.341, 0.086, 0.012), (-0.17, 0, H + 0.022), RED, 0.003)
box((0.3, 0.06, 0.04), (-0.17, 0, 0.02), ANOD, 0.004)
cyl(0.016, 0.02, (0.005, 0, H), STEEL, axis=(1, 0, 0), verts=64, bevel=0.001)
cyl(0.0105, 0.022, (0.006, 0, H), ANOD, axis=(1, 0, 0), verts=48)
cyl(0.003, 0.003, (-0.04, -0.0435, H - 0.02), LEDRED, axis=(0, 1, 0), verts=20)
for k in range(6):
    box((0.004, 0.0035, 0.03), (-0.30 + k * 0.009, -0.043, H - 0.008), ANOD, 0.0008)
try:
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=LOGO)
    curves = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    if curves:
        for c in curves:
            c.data.extrude = 0.00018
        bpy.ops.object.select_all(action="DESELECT")
        for c in curves:
            c.select_set(True)
        bpy.context.view_layer.objects.active = curves[0]
        bpy.ops.object.join()
        logo = bpy.context.object
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        w = logo.dimensions.x
        k = 0.17 / w
        logo.scale = (k, k, k)
        logo.rotation_euler = (math.pi / 2, 0, 0)
        logo.location = (-0.15, -0.0432, H - 0.002)
        logo.data.materials.clear()
        logo.data.materials.append(mat("Logo", "#dd191c", 0.0, 0.35))
except Exception as e:
    print("logo skipped", e)

mirror_mount(P["m1"], (Vector((-1, 0, 0)) + Vector((0, 1, 0))))
mirror_mount(P["m2"], (Vector((0, -1, 0)) + Vector((0, 0, 1))))
mirror_mount(P["m3"], (Vector((0, 0, -1)) + Vector((-1, 0, 0))))
mirror_mount(P["m4"], (Vector((1, 0, 0)) + Vector((0, -1, 0))))
lens_mount(L1, (0, 1, 0))
lens_mount(L2, (0, 1, 0))
lens_mount(P["l3"], (1, 0, 0), flat=0.36)

# Beam splitter cube on a platform.
box((0.0254, 0.0254, 0.0254), P["bs"], GLASS, 0.0006)
bpy.ops.mesh.primitive_plane_add(size=0.0352, location=P["bs"])
pl = bpy.context.object
pl.scale = (1, 0.72, 1)
pl.rotation_euler = (math.pi / 2, 0, math.radians(45))
bpy.ops.object.transform_apply(scale=True, rotation=True)
pl.data.materials.append(COATING)
box((0.036, 0.036, 0.006), P["bs"] - Vector((0, 0, 0.0157)), ANOD, 0.0015)
post(P["bs"].x, P["bs"].y, P["bs"].z - 0.019)

# Photodiode detector: graphite can, its face glows when the split beam arrives.
cyl(0.014, 0.03, DET + Vector((0, 0.012, 0)), ANOD, axis=(0, 1, 0), verts=48, bevel=0.0012)
DET_FACE = mat("Detector face", "#ff2a1a", 0.0, 0.3, emit=0.0)
cyl(0.0065, 0.002, DET - Vector((0, 0.0035, 0)), DET_FACE, axis=(0, 1, 0), verts=32)
post(DET.x, DET.y + 0.012, DET.z - 0.014)

# A few out-of-path parts: depth for the bokeh.
for (x, y) in ((0.6, 0.2), (-0.12, 0.16), (0.55, 0.75), (-0.45, 0.7), (0.15, -0.25), (0.6, -0.2), (0.12, 0.2)):
    mirror_mount((x, y, H), (math.cos(x * 7), math.sin(y * 5), 0))

# --- beam -----------------------------------------------------------------------------------
# Path of the beam head: (from, to, radius at from, radius at to).
R = 0.0016
SEGS = [
    (P["src"] + Vector((0.016, 0, 0)), P["m1"], R, R),
    (P["m1"], L1, R, R),
    (L1, FOCUS, R, 0.00025),
    (FOCUS, L2, 0.00025, R * 1.25),
    (L2, P["m2"], R * 1.25, R * 1.25),
    (P["m2"], P["m3"], R * 1.25, R * 1.25),
    (P["m3"], P["bs"], R * 1.25, R * 1.25),
    (P["bs"], P["l3"], R * 1.25, R * 1.25),
    (P["l3"], P["m4"], R * 1.25, R * 0.35),
    (P["m4"], CAM_END + Vector((0, 0.02, 0)), R * 0.35, R * 1.6),
]
starts, acc = [], 0.0
for a, b, *_ in SEGS:
    starts.append(acc)
    acc += (b - a).length
TOTAL = acc
SPLIT_AT = starts[7]          # the beam splitter
HEAD_KEYS = [(4, 0.0), (13, starts[1]), (17, starts[2]), (20, starts[4]), (24, starts[5]), (28, starts[6]),
             (33, starts[7]), (37, starts[8]), (41, starts[9]), (46, TOTAL)]
SPLIT_LEN = (DET - P["bs"]).length


# Beam head arrival (frame, distance) at each optic: the camera shots are keyed to these.


def head_d(f):
    """Distance of the beam head along the path at frame f; ends in the camera lens on f 46."""
    keys = HEAD_KEYS
    if f <= keys[0][0]:
        return 0.0
    for (f0, d0), (f1, d1) in zip(keys, keys[1:]):
        if f <= f1:
            t = (f - f0) / (f1 - f0)
            return d0 + (d1 - d0) * t
    return keys[-1][1]


def at(d):
    d = min(max(d, 0.0), TOTAL)
    for (a, b, *_), s in zip(SEGS, starts):
        L = (b - a).length
        if d <= s + L + 1e-9:
            return a + (b - a) * ((d - s) / L)
    return SEGS[-1][1]


def tube(a, b, r0, r1, m, scale):
    ax = b - a
    bpy.ops.mesh.primitive_cone_add(radius1=r0 * scale, radius2=r1 * scale, depth=ax.length, vertices=32, location=(a + b) / 2)
    o = bpy.context.object
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(ax.normalized())
    o.data.materials.append(m)
    o.visible_shadow = False
    o.visible_diffuse = False
    o.visible_glossy = True
    o.visible_transmission = True
    o["reveal"] = 0.0
    return o


beam_objs = []
for (a, b, r0, r1), s in zip(SEGS, starts):
    L = (b - a).length
    for m, k in ((CORE, 1.0), (HALO, 3.6)):
        o = tube(a, b, r0, r1, m, k)
        beam_objs.append((o, s, L))
split = []
for m, k in ((CORE, 0.8), (HALO, 3.0)):
    o = tube(P["bs"], DET - Vector((0, 0.005, 0)), R, R, m, k)
    split.append(o)

# Head: a bright point light with the beam (red pool on the table) + flash lights at the optics.
bpy.ops.object.light_add(type="POINT", location=P["src"])
head = bpy.context.object
head.data.color = (1.0, 0.1, 0.06)
head.data.shadow_soft_size = 0.004
hits = []
for key in ("m1", "m2", "m3", "bs", "l3", "m4"):
    bpy.ops.object.light_add(type="POINT", location=P[key])
    li = bpy.context.object
    li.data.color = (1.0, 0.12, 0.08)
    li.data.shadow_soft_size = 0.01
    hits.append((li, key))
L1L = (L1, starts[2]); L2L = (L2, starts[4])

LOGO_AT = Vector((-0.15, -0.043, H - 0.002))
smooth01 = lambda t: (lambda u: u * u * (3 - 2 * u))(min(max(t, 0.0), 1.0))
# Focus target for the depth of field.
focus = bpy.data.objects.new("Focus", None)
sc.collection.objects.link(focus)

# --- camera ---------------------------------------------------------------------------------
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cd = cam.data
cd.lens = 24 if ASPECT == "portrait" else 30
cd.sensor_width = 36
cd.clip_start = 0.003
cd.dof.use_dof = True
cd.dof.focus_object = focus
cd.dof.aperture_fstop = 6.3
cd.dof.aperture_blades = 7


# Shots: (frame, camera position, look-at point, roll). Each one frames the optic the beam
# reaches next; Catmull-Rom between them gives one continuous move.
V = Vector
SHOTS_A = [
    (0, V((-0.175, -0.28, 0.112)), V((-0.148, 0.0, 0.072)), 0.0),       # the laser: logo, aperture
    (8, V((0.02, -0.06, 0.112)), V((0.25, 0.0, 0.08)), 0.04),        # behind the beam, M1 ahead
    (14, V((0.235, -0.065, 0.118)), V((0.32, 0.11, 0.08)), -0.1),    # round M1, the telescope ahead
    (19, V((0.352, 0.075, 0.108)), V((0.32, 0.31, 0.085)), 0.0),     # between L1 and L2: the focus
    (24, V((0.365, 0.3, 0.1)), V((0.32, 0.44, 0.17)), 0.07),         # M2 sends the beam up
    (29, V((0.245, 0.37, 0.19)), V((0.33, 0.44, 0.222)), 0.06),        # up the periscope to M3
    (34, V((0.255, 0.58, 0.278)), V((0.08, 0.45, 0.22)), -0.08),      # the splitter, the detector lights
    (39, V((0.0, 0.395, 0.245)), V((-0.2, 0.44, 0.22)), 0.0),        # through L3 to M4
    (44, V((-0.17, 0.27, 0.226)), V((-0.2, 0.44, 0.22)), 0.05),      # in front of M4
    (54, V((-0.2, 0.212, 0.223)), V((-0.2, 0.44, 0.22)), 0.0),       # the beam enters the lens
]
# Variant B, crane: high over the table, the whole optical path lights up below while the camera
# slides sideways and comes down to the last mirror.
SHOTS_B = [
    (0, V((0.3, -0.2, 0.8)), V((0.08, 0.26, 0.0)), 0.18),
    (12, V((0.18, -0.12, 0.7)), V((0.07, 0.27, 0.02)), 0.1),
    (22, V((0.02, -0.03, 0.56)), V((0.08, 0.31, 0.05)), 0.0),
    (30, V((-0.1, 0.06, 0.43)), V((0.02, 0.4, 0.15)), -0.08),
    (37, V((-0.08, 0.12, 0.33)), V((-0.12, 0.42, 0.21)), -0.04),
    (43, V((-0.17, 0.2, 0.26)), V((-0.2, 0.44, 0.22)), 0.0),
    (54, V((-0.2, 0.212, 0.223)), V((-0.2, 0.44, 0.22)), 0.0),
]
# Variant C, macro orbit: close on the first mirror, then an arc round the telescope, a rise
# with the periscope and a side slide along the upper line.
SHOTS_C = [
    (0, V((0.255, 0.06, 0.1)), V((0.32, 0.0, 0.08)), -0.06),
    (10, V((0.268, 0.05, 0.096)), V((0.32, 0.0, 0.08)), -0.03),
    (17, V((0.375, 0.04, 0.095)), V((0.32, 0.16, 0.08)), 0.08),
    (22, V((0.38, 0.22, 0.088)), V((0.32, 0.3, 0.08)), 0.12),
    (27, V((0.41, 0.36, 0.17)), V((0.32, 0.44, 0.2)), 0.04),
    (33, V((0.25, 0.34, 0.26)), V((0.12, 0.44, 0.22)), -0.1),
    (39, V((0.02, 0.35, 0.235)), V((-0.2, 0.44, 0.22)), -0.04),
    (44, V((-0.17, 0.27, 0.226)), V((-0.2, 0.44, 0.22)), 0.05),
    (54, V((-0.2, 0.212, 0.223)), V((-0.2, 0.44, 0.22)), 0.0),
]
VARIANT = os.environ.get("VARIANT", "a")
SHOTS = {"a": SHOTS_A, "b": SHOTS_B, "c": SHOTS_C}[VARIANT]


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def cam_pose(f):
    f = min(max(f, 0), F_END)
    i = max(k for k in range(len(SHOTS) - 1) if SHOTS[k][0] <= f) if f < SHOTS[-1][0] else len(SHOTS) - 2
    s0, s1 = SHOTS[max(i - 1, 0)], SHOTS[i]
    s2, s3 = SHOTS[i + 1], SHOTS[min(i + 2, len(SHOTS) - 1)]
    t = (f - s1[0]) / (s2[0] - s1[0])
    pos = catmull(s0[1], s1[1], s2[1], s3[1], t)
    tgt = catmull(s0[2], s1[2], s2[2], s3[2], t)
    roll = catmull(s0[3], s1[3], s2[3], s3[3], t)
    return pos, tgt, roll


UP = [Vector((0, 0, 1))]


def look(pos, tgt, roll=0.0):
    from mathutils import Matrix
    zc = (pos - tgt).normalized()
    up = UP[0]
    x = up.cross(zc)
    if x.length < 1e-4:
        x = Vector((1, 0, 0)).cross(zc)
    x.normalize()
    y = zc.cross(x)
    UP[0] = Vector((0, 0, 1))
    q = Matrix((x, y, zc)).transposed().to_quaternion()
    return q @ Quaternion((0, 0, 1), roll)


cam.rotation_mode = "QUATERNION"
prev_q = None
for f in range(0, F_END + 1):
    pos, tgt, roll = cam_pose(f)
    d = head_d(f)
    cam.location = pos
    q = look(pos, tgt, roll)
    if prev_q is not None and prev_q.dot(q) < 0:
        q.negate()
    prev_q = q.copy()
    cam.rotation_quaternion = q
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_quaternion", frame=f)
    focus.location = (LOGO_AT.lerp(at(d), smooth01((f - 2) / 6.0)) if VARIANT == "a" else at(d)) if f < 40 else P["m4"].lerp(CAM_END, 0.3)
    focus.keyframe_insert("location", frame=f)
    for o, s, L in beam_objs:
        o["reveal"] = min(max((d - s) / L, 0.0), 1.0)
        o.keyframe_insert('["reveal"]', frame=f)
    for o in split:
        o["reveal"] = min(max((d - SPLIT_AT) / SPLIT_LEN, 0.0), 1.0)
        o.keyframe_insert('["reveal"]', frame=f)
    head.location = at(d)
    head.data.energy = 0.0 if d <= 0.001 or f > 46 else 0.8
    head.keyframe_insert("location", frame=f)
    head.data.keyframe_insert("energy", frame=f)
    for li, key in hits:
        idx = {"m1": 1, "m2": 5, "m3": 6, "bs": 7, "l3": 8, "m4": 9}[key]
        dt = d - starts[idx]
        li.data.energy = 0.0 if dt < 0 else 0.12 + 1.2 * math.exp(-dt * 14.0)
        li.data.keyframe_insert("energy", frame=f)
    DET_FACE.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = (
        0.0 if d < SPLIT_AT + SPLIT_LEN else 18.0)
    DET_FACE.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
    # White flash at the end: the beam enters the lens.
    sc.view_settings.exposure = 0.0 if f < 45 else min(9.0, ((f - 45) / 6.0) ** 1.6 * 9.0)
    sc.view_settings.keyframe_insert("exposure", frame=f)

for o in list(bpy.data.objects):
    ad = o.animation_data
    for holder in (o, getattr(o, "data", None)):
        a = getattr(holder, "animation_data", None)
        if a and a.action:
            try:
                for fc in a.action.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
            except AttributeError:
                pass

# --- light & world --------------------------------------------------------------------------
world = bpy.data.worlds.new("Studio")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (*srgb("#e6e9ee"), 1)
bg.inputs[1].default_value = 0.55
wn = world.node_tree
cam_bg = wn.nodes.new("ShaderNodeBackground")
cam_bg.inputs[0].default_value = (*srgb("#f1f3f6"), 1)
cam_bg.inputs[1].default_value = 2.2
lp = wn.nodes.new("ShaderNodeLightPath")
wmix = wn.nodes.new("ShaderNodeMixShader")
wout = next(n for n in wn.nodes if n.type == "OUTPUT_WORLD")
wn.links.new(lp.outputs["Is Camera Ray"], wmix.inputs["Fac"])
wn.links.new(bg.outputs[0], wmix.inputs[1])
wn.links.new(cam_bg.outputs[0], wmix.inputs[2])
wn.links.new(wmix.outputs[0], wout.inputs["Surface"])
sc.world = world
for name, loc, size, energy in (
    ("Softbox top", (0.1, 0.3, 1.6), 2.0, 160),
    ("Softbox left", (-1.4, -0.6, 0.8), 1.5, 45),
    ("Softbox right", (1.6, 1.0, 0.9), 1.5, 35),
):
    li = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    li.data.size = size
    li.data.energy = energy
    li.location = loc
    li.rotation_mode = "QUATERNION"
    li.rotation_quaternion = (Vector((0.1, 0.3, 0)) - Vector(loc)).to_track_quat("-Z", "Y")
    sc.collection.objects.link(li)

# --- render ---------------------------------------------------------------------------------
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = dev
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = dv.type == dev
        sc.cycles.device = "GPU"
        break
    except TypeError:
        continue
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 10
sc.cycles.transmission_bounces = 10
sc.cycles.transparent_max_bounces = 16
sc.cycles.caustics_reflective = False
sc.cycles.caustics_refractive = False
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.25
sc.view_settings.view_transform = "AgX"
try:
    sc.view_settings.look = os.environ.get("LOOK", "AgX - Punchy")
except TypeError:
    pass
if ASPECT == "portrait":
    sc.render.resolution_x, sc.render.resolution_y = 720, 1280
else:
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"

# Compositor: bloom around the beam, slight lens dispersion.
sc.render.use_compositing = True
ng = bpy.data.node_groups.new("Film comp", "CompositorNodeTree")
ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
out = ng.nodes.new("NodeGroupOutput")
glare = ng.nodes.new("CompositorNodeGlare")
for c in ("Bloom", "BLOOM", "Fog Glow"):
    try:
        glare.inputs["Type"].default_value = c
        break
    except (TypeError, KeyError, ValueError):
        continue
for name, val in (("Threshold", 1.2), ("Strength", 0.5), ("Size", 0.6), ("Saturation", 1.0)):
    if name in glare.inputs:
        glare.inputs[name].default_value = val
lens = ng.nodes.new("CompositorNodeLensdist")
for name, val in (("Distortion", -0.012), ("Dispersion", 0.018)):
    if name in lens.inputs:
        lens.inputs[name].default_value = val
if "Fit" in lens.inputs:
    lens.inputs["Fit"].default_value = True
ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
ng.links.new(glare.outputs["Image"], lens.inputs["Image"])
ng.links.new(lens.outputs["Image"], out.inputs["Image"])
sc.compositing_node_group = ng

os.makedirs(OUT, exist_ok=True)
if MODE == "stills":
    for f in [int(x) for x in os.environ.get("STILLS", "0,8,14,20,26,32,38,44").split(",")]:
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"still-{ASPECT}-{f:02d}.png")
        bpy.ops.render.render(write_still=True)
elif MODE == "frames":
    sc.render.filepath = os.path.join(OUT, f"{ASPECT}-")
    bpy.ops.render.render(animation=True)
elif MODE.startswith("blend"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "optic-film.blend"))
print("DONE", ASPECT, MODE, "path", round(TOTAL, 3))
