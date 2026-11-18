"""
SmartEstate AI - Modern Luxury Villa (fictional showcase asset)
================================================================

Procedurally builds an original two-storey modern villa with the Blender
Python API, exports a web-ready GLB and renders presentation images.

The building is a fictional demo asset. It does not represent any real
property, address or listing.

Usage (Blender 4.2+ / 5.x, headless):

    blender --background --factory-startup --python create_model.py -- [options]

Options (after the "--"):
    --out DIR        output folder (default: folder of this script)
    --log FILE       also append log lines to FILE
    --tmp DIR        scratch folder for intermediate texture PNGs
                     (default: system temp)
    --samples N      Cycles samples for the renders (default 192)
    --res PCT        render resolution percentage (default 100)
    --skip-render    build + export only
    --validate       do NOT build; open a clean scene, re-import the GLB from
                     --out and print/write a validation report

Everything (geometry, procedural textures, materials) is generated here; no
external models or textures are downloaded.

Coordinate conventions (inside Blender): metres, Z up, front facade faces -Y.
The exported GLB is Y up (glTF / Three.js), front facade faces +Z in Three.js.
"""

import bpy
import bmesh
import math
import os
import sys
import json
import struct
import time
import random
import tempfile

import numpy as np
from mathutils import Vector, Matrix, noise

# ---------------------------------------------------------------------------
# Arguments / logging
# ---------------------------------------------------------------------------

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None, cast=str):
    if name in ARGV:
        i = ARGV.index(name)
        if i + 1 < len(ARGV):
            return cast(ARGV[i + 1])
    return default


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(_arg("--out", SCRIPT_DIR))
LOG_FILE = _arg("--log", None)
TMP_DIR = os.path.abspath(_arg("--tmp", os.path.join(tempfile.gettempdir(), "smartestate_villa_tex")))
SAMPLES = _arg("--samples", 192, int)
RES_PCT = _arg("--res", 100, int)
SKIP_RENDER = "--skip-render" in ARGV
VALIDATE_ONLY = "--validate" in ARGV

BLEND_PATH = os.path.join(OUT_DIR, "smartestate_modern_villa.blend")
GLB_PATH = os.path.join(OUT_DIR, "smartestate_modern_villa.glb")

T0 = time.time()


def log(*parts):
    msg = "[%7.1fs] " % (time.time() - T0) + " ".join(str(p) for p in parts)
    print(msg, flush=True)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")


EPS = 1e-4

# ---------------------------------------------------------------------------
# Procedural, tileable textures (numpy, FFT based -> seamless)
# ---------------------------------------------------------------------------


def srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def pnoise(n, sigma, rng, aniso=(1.0, 1.0)):
    """Periodic gaussian-filtered noise, zero mean / unit std. aniso=(su, sv)."""
    w = rng.standard_normal((n, n)).astype(np.float64)
    F = np.fft.rfft2(w)
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.rfftfreq(n)[None, :]
    sx, sy = sigma * aniso[0], sigma * aniso[1]
    g = np.exp(-2.0 * np.pi ** 2 * ((sx * fx) ** 2 + (sy * fy) ** 2))
    r = np.fft.irfft2(F * g, s=(n, n))
    r -= r.mean()
    r /= (r.std() + 1e-9)
    return r


def pblur(a, sigma):
    n = a.shape[0]
    F = np.fft.rfft2(a)
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.rfftfreq(n)[None, :]
    g = np.exp(-2.0 * np.pi ** 2 * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.fft.irfft2(F * g, s=a.shape)


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(h)
    ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    return np.stack([nx / ln, ny / ln, nz / ln], axis=-1) * 0.5 + 0.5


def save_image(name, rgb, non_color=False):
    """rgb: (n, n, 3) display-space values 0..1. Saved as PNG then packed."""
    os.makedirs(TMP_DIR, exist_ok=True)
    n = rgb.shape[0]
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((n, n, 1))], axis=-1).astype(np.float32)
    img = bpy.data.images.new(name + "_gen", n, n, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    path = os.path.join(TMP_DIR, name + ".png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    out = bpy.data.images.load(path)
    out.name = name
    if non_color:
        out.colorspace_settings.name = "Non-Color"
    out.pack()
    return out


def build_textures():
    rng = np.random.default_rng(20261117)
    T = {}
    n = 1024
    # --- Architectural concrete (shared normal, three albedo tints) -------
    low = 0.7 * pnoise(n, 70, rng) + 0.3 * pnoise(n, 28, rng)
    mid = pnoise(n, 6, rng)
    grain = pnoise(n, 0.8, rng)
    streak = pnoise(n, 10, rng, aniso=(0.25, 6.0))  # faint vertical weathering
    pores = (rng.random((n, n)) > 0.9982).astype(np.float64)
    pores = pblur(pores, 1.1)
    pores /= (pores.max() + 1e-9)
    shade = 1.0 + 0.045 * low + 0.02 * mid + 0.025 * grain + 0.018 * streak
    shade *= (1.0 - 0.32 * pores)
    tints = {
        "T_Concrete_White_Albedo": np.array([0.60, 0.595, 0.58]),
        "T_Concrete_LightGrey_Albedo": np.array([0.30, 0.305, 0.31]),
        "T_Concrete_Plinth_Albedo": np.array([0.075, 0.075, 0.08]),
    }
    for k, base in tints.items():
        hue = 1.0 + 0.012 * pnoise(n, 90, rng)[..., None] * np.array([1.0, 0.6, -0.4])
        T[k] = save_image(k, srgb(base[None, None, :] * shade[..., None] * hue))
    h = 0.35 * mid + 0.25 * grain + 0.15 * low - 2.2 * pores
    T["T_Concrete_Normal"] = save_image("T_Concrete_Normal", normal_from_height(h, 0.9), True)

    # --- Large-format stone paving: 0.6 x 1.2 m tiles, texture = 2.4 m ----
    yy, xx = np.mgrid[0:n, 0:n]
    tw, th, joint = n // 4, n // 2, 3
    tid = (xx // tw) + 7 * (yy // th)
    tone = rng.normal(0, 1, 64)[tid % 64]
    jmask = ((xx % tw) < joint) | ((yy % th) < joint)
    st = 1.0 + 0.035 * tone + 0.03 * pnoise(n, 18, rng) + 0.03 * pnoise(n, 1.2, rng)
    pav = np.array([0.23, 0.215, 0.195])[None, None, :] * st[..., None]
    pav[jmask] *= 0.45
    T["T_Paving_Albedo"] = save_image("T_Paving_Albedo", srgb(pav))
    hp = 0.3 * pnoise(n, 1.0, rng) + 0.3 * pnoise(n, 8, rng) - 3.0 * pblur(jmask.astype(float), 0.8)
    T["T_Paving_Normal"] = save_image("T_Paving_Normal", normal_from_height(hp, 0.8), True)

    # --- Wood (planks along U), 512 px = 2.4 m ----------------------------
    m = 512
    yy, xx = np.mgrid[0:m, 0:m]
    pw = 32
    plank = yy // pw
    offs = rng.integers(0, m, 64)
    seg = ((xx + offs[plank % 64]) // 256)
    pid = (plank * 3 + seg) % 97
    ptone = rng.normal(0, 1, 97)[pid]
    grain_w = pnoise(m, 2.0, rng, aniso=(18.0, 0.6))
    fine_w = pnoise(m, 0.7, rng, aniso=(6.0, 0.5))
    wj = ((yy % pw) < 1) | (((xx + offs[plank % 64]) % 256) < 1)
    wshade = 1.0 + 0.10 * ptone + 0.10 * grain_w + 0.05 * fine_w
    for k, base in (("T_Wood_Oak_Albedo", [0.30, 0.17, 0.085]), ("T_Wood_Dark_Albedo", [0.055, 0.033, 0.02])):
        w = np.array(base)[None, None, :] * wshade[..., None]
        w[wj] *= 0.4
        T[k] = save_image(k, srgb(w))

    # --- Lawn, 512 px = 3 m ------------------------------------------------
    patch = pnoise(m, 40, rng)
    gr = pnoise(m, 0.6, rng)
    lawn = np.stack([0.050 + 0.012 * patch + 0.010 * gr,
                     0.095 + 0.016 * patch + 0.022 * gr,
                     0.022 + 0.006 * patch + 0.006 * gr], axis=-1)
    T["T_Lawn_Albedo"] = save_image("T_Lawn_Albedo", srgb(lawn))
    T["T_Lawn_Normal"] = save_image("T_Lawn_Normal", normal_from_height(pnoise(m, 0.7, rng), 2.5), True)

    # --- Foliage clumps, 512 px = 1.5 m -----------------------------------
    clump = pnoise(m, 9.0, rng)
    leaf = pnoise(m, 1.0, rng)
    mixv = np.clip(0.5 + 0.35 * clump + 0.2 * leaf, 0, 1)[..., None]
    for k, dark, light in (("T_Foliage_A_Albedo", [0.018, 0.045, 0.012], [0.08, 0.14, 0.03]),
                           ("T_Foliage_B_Albedo", [0.035, 0.05, 0.025], [0.12, 0.14, 0.07])):
        T[k] = save_image(k, srgb(np.array(dark) * (1 - mixv) + np.array(light) * mixv))
    T["T_Foliage_Normal"] = save_image("T_Foliage_Normal", normal_from_height(1.2 * clump + 0.6 * leaf, 3.0), True)

    # --- Bark, 512 px = 1 m ------------------------------------------------
    bk = pnoise(m, 1.5, rng, aniso=(0.4, 8.0))
    bark = np.array([0.07, 0.058, 0.045])[None, None, :] * (1.0 + 0.25 * bk[..., None])
    T["T_Bark_Albedo"] = save_image("T_Bark_Albedo", srgb(bark))

    # --- Roof gravel, 512 px = 2 m -----------------------------------------
    g1 = pnoise(m, 1.6, rng)
    g2 = pnoise(m, 2.4, rng)
    stones = np.clip((g1 > 0.4) * 0.6 + (g2 > 0.6) * 0.4, 0, 1)
    gv = 0.16 + 0.07 * stones + 0.025 * pnoise(m, 0.6, rng)
    T["T_Gravel_Albedo"] = save_image("T_Gravel_Albedo", srgb(np.stack([gv, gv * 0.98, gv * 0.95], axis=-1)))

    # --- Water ripples normal, 512 px = 4 m -------------------------------
    wr = pnoise(m, 9, rng) + 0.4 * pnoise(m, 4, rng)
    T["T_Water_Normal"] = save_image("T_Water_Normal", normal_from_height(wr, 1.4), True)
    return T


# ---------------------------------------------------------------------------
# Materials (Principled BSDF only -> clean glTF PBR export)
# ---------------------------------------------------------------------------

def _set_in(node, names, value):
    for nm in names:
        if nm in node.inputs:
            node.inputs[nm].default_value = value
            return True
    return False


def make_material(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, albedo=None,
                  normal=None, nstrength=1.0, transmission=0.0, ior=1.45,
                  emission=None, estrength=0.0, coat=0.0, spec=0.5):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (0, 0)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set_in(b, ["Base Color"], (*color, 1.0))
    _set_in(b, ["Roughness"], rough)
    _set_in(b, ["Metallic"], metal)
    _set_in(b, ["IOR"], ior)
    _set_in(b, ["Specular IOR Level", "Specular"], spec)
    if transmission:
        _set_in(b, ["Transmission Weight", "Transmission"], transmission)
    if coat:
        _set_in(b, ["Coat Weight", "Clearcoat"], coat)
    if emission is not None:
        _set_in(b, ["Emission Color", "Emission"], (*emission, 1.0))
        _set_in(b, ["Emission Strength"], estrength)
    if albedo is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = albedo
        t.location = (-400, 200)
        t.interpolation = "Linear"
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    if normal is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = normal
        t.location = (-600, -300)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-250, -300)
        nm.inputs["Strength"].default_value = nstrength
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    mat.diffuse_color = (*color, 1.0)
    return mat


def build_materials(T):
    M = {}
    M["concrete_white"] = make_material("M_Concrete_Architectural_White", (0.60, 0.595, 0.58), 0.86,
                                        albedo=T["T_Concrete_White_Albedo"], normal=T["T_Concrete_Normal"], nstrength=0.45, spec=0.35)
    M["concrete_grey"] = make_material("M_Concrete_Architectural_LightGrey", (0.30, 0.305, 0.31), 0.84,
                                       albedo=T["T_Concrete_LightGrey_Albedo"], normal=T["T_Concrete_Normal"], nstrength=0.5, spec=0.35)
    M["concrete_plinth"] = make_material("M_Concrete_Plinth_Charcoal", (0.075, 0.075, 0.08), 0.82,
                                         albedo=T["T_Concrete_Plinth_Albedo"], normal=T["T_Concrete_Normal"], nstrength=0.6, spec=0.35)
    M["paving"] = make_material("M_Stone_Paving_Warm", (0.23, 0.215, 0.195), 0.72,
                                albedo=T["T_Paving_Albedo"], normal=T["T_Paving_Normal"], nstrength=0.6)
    M["plaster"] = make_material("M_Interior_Plaster_WarmWhite", (0.70, 0.66, 0.60), 0.9, spec=0.3)
    M["wood_oak"] = make_material("M_Wood_Oak", (0.30, 0.17, 0.085), 0.55, albedo=T["T_Wood_Oak_Albedo"])
    M["wood_dark"] = make_material("M_Wood_Smoked_Oak_Door", (0.055, 0.033, 0.02), 0.45, albedo=T["T_Wood_Dark_Albedo"])
    M["gravel"] = make_material("M_Roof_Gravel", (0.16, 0.157, 0.152), 0.95, albedo=T["T_Gravel_Albedo"],
                                normal=T["T_Concrete_Normal"], nstrength=1.0)
    M["alu"] = make_material("M_Aluminium_Anthracite", (0.035, 0.037, 0.04), 0.38, metal=0.85)
    M["glass"] = make_material("M_Glass_Clear_LowIron", (0.85, 0.92, 0.92), 0.02, transmission=1.0, ior=1.5, spec=0.5)
    M["water"] = make_material("M_Pool_Water", (0.30, 0.62, 0.66), 0.03, transmission=0.92, ior=1.33,
                               normal=T["T_Water_Normal"], nstrength=0.25)
    M["pool_tile"] = make_material("M_Pool_Tile_Aqua", (0.22, 0.46, 0.50), 0.3)
    M["lawn"] = make_material("M_Lawn", (0.05, 0.095, 0.022), 0.95, albedo=T["T_Lawn_Albedo"],
                              normal=T["T_Lawn_Normal"], nstrength=0.8, spec=0.3)
    M["foliage_a"] = make_material("M_Foliage_DeepGreen", (0.04, 0.08, 0.02), 0.75, albedo=T["T_Foliage_A_Albedo"],
                                   normal=T["T_Foliage_Normal"], nstrength=2.0, spec=0.4)
    M["foliage_b"] = make_material("M_Foliage_Olive", (0.07, 0.09, 0.045), 0.75, albedo=T["T_Foliage_B_Albedo"],
                                   normal=T["T_Foliage_Normal"], nstrength=2.0, spec=0.4)
    M["grass"] = make_material("M_Ornamental_Grass", (0.20, 0.22, 0.09), 0.7, spec=0.35)
    M["bark"] = make_material("M_Tree_Bark", (0.07, 0.058, 0.045), 0.9, albedo=T["T_Bark_Albedo"])
    M["soil"] = make_material("M_Planter_Mulch", (0.035, 0.025, 0.018), 1.0, normal=T["T_Foliage_Normal"], nstrength=0.8)
    M["pv"] = make_material("M_Solar_Panel", (0.012, 0.016, 0.03), 0.18, metal=0.3, coat=0.5)
    M["light_ext"] = make_material("M_Light_Warm_Exterior", (1.0, 0.85, 0.7), 0.3,
                                   emission=(1.0, 0.70, 0.42), estrength=14.0)
    M["light_int"] = make_material("M_Light_Warm_Interior", (1.0, 0.9, 0.8), 0.3,
                                   emission=(1.0, 0.76, 0.52), estrength=5.0)
    M["fabric"] = make_material("M_Fabric_Linen", (0.42, 0.39, 0.35), 0.95, spec=0.3)
    M["fabric_dark"] = make_material("M_Fabric_Charcoal", (0.05, 0.05, 0.055), 0.9, spec=0.3)
    M["lacquer"] = make_material("M_Lacquer_White", (0.72, 0.72, 0.70), 0.35)
    M["stone_top"] = make_material("M_Stone_Countertop", (0.55, 0.55, 0.53), 0.22)
    return M


# ---------------------------------------------------------------------------
# Mesh building helpers
# ---------------------------------------------------------------------------

BOX_FACES = {
    "-z": [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
    "+z": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    "-y": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    "+y": [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
    "-x": [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
    "+x": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
}


class MB:
    """Small bmesh builder that tracks material slots."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def mi(self, mat):
        if mat is None:
            return 0
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def box(self, mn, mx, mat=None, skip=()):
        lo = [min(a, b) for a, b in zip(mn, mx)]
        hi = [max(a, b) for a, b in zip(mn, mx)]
        cache = {}

        def V(t):
            if t not in cache:
                cache[t] = self.bm.verts.new((hi[0] if t[0] else lo[0], hi[1] if t[1] else lo[1], hi[2] if t[2] else lo[2]))
            return cache[t]

        idx = self.mi(mat)
        for key, quad in BOX_FACES.items():
            if key in skip:
                continue
            f = self.bm.faces.new([V(t) for t in quad])
            f.material_index = idx

    def prism(self, profile, axis, lo, hi, mat=None, drop=()):
        """Extrude a 2D polygon. axis 'x': profile=(y,z); 'y': (x,z); 'z': (x,y)."""
        def P(a, b, w):
            if axis == "x":
                return (w, a, b)
            if axis == "y":
                return (a, w, b)
            return (a, b, w)
        v0 = [self.bm.verts.new(P(a, b, lo)) for a, b in profile]
        v1 = [self.bm.verts.new(P(a, b, hi)) for a, b in profile]
        idx = self.mi(mat)
        new = [self.bm.faces.new(v0[::-1]), self.bm.faces.new(v1)]
        k = len(profile)
        for i in range(k):
            j = (i + 1) % k
            new.append(self.bm.faces.new([v0[i], v0[j], v1[j], v1[i]]))
        for f in new:
            f.material_index = idx
        bmesh.ops.recalc_face_normals(self.bm, faces=new)

    def cylinder(self, cx, cy, z0, z1, r, seg=12, mat=None, top=True, bottom=True, r_top=None):
        rt = r if r_top is None else r_top
        b = [self.bm.verts.new((cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z0)) for i in range(seg)]
        t = [self.bm.verts.new((cx + rt * math.cos(2 * math.pi * i / seg), cy + rt * math.sin(2 * math.pi * i / seg), z1)) for i in range(seg)]
        idx = self.mi(mat)
        faces = []
        for i in range(seg):
            j = (i + 1) % seg
            faces.append(self.bm.faces.new([b[i], b[j], t[j], t[i]]))
        if bottom:
            faces.append(self.bm.faces.new(b[::-1]))
        if top:
            faces.append(self.bm.faces.new(t))
        for f in faces:
            f.material_index = idx

    def quad(self, verts, mat=None):
        f = self.bm.faces.new([self.bm.verts.new(v) for v in verts])
        f.material_index = self.mi(mat)

    def to_object(self, name, coll, smooth=False):
        me = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        if smooth:
            for p in me.polygons:
                p.use_smooth = True
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        return obj


def box_obj(name, mn, mx, coll, mat=None):
    mb = MB()
    mb.box(mn, mx, mat)
    return mb.to_object(name, coll)


def apply_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    me.name = obj.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def boolean(obj, cutters, op="DIFFERENCE"):
    """Exact boolean against a list of operand objects, which are deleted."""
    if not cutters:
        return
    tmp = bpy.data.collections.new("TMP_Operands")
    bpy.context.scene.collection.children.link(tmp)
    for c in cutters:
        for uc in list(c.users_collection):
            uc.objects.unlink(c)
        tmp.objects.link(c)
    m = obj.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.operand_type = "COLLECTION"
    m.collection = tmp
    apply_mods(obj)
    for c in cutters:
        me = c.data
        bpy.data.objects.remove(c)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(tmp)


def with_bm(obj, fn):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    res = fn(bm)
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return res


def set_materials(obj, mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


def clean_mesh(bm, dissolve=True):
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges[:])
    if dissolve:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), use_dissolve_boundaries=False,
                                 verts=bm.verts[:], edges=bm.edges[:], delimit={"MATERIAL"})
    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_faces]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")


def box_uv(obj, tiles, default=4.0):
    """World-aligned box projection (objects are built in world space)."""
    def fn(bm):
        uv = bm.loops.layers.uv.verify()
        for f in bm.faces:
            t = tiles.get(f.material_index, default) if isinstance(tiles, dict) else tiles
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                c = lp.vert.co
                if ax == 0:
                    u, v = (c.y if n.x > 0 else -c.y), c.z
                elif ax == 1:
                    u, v = (-c.x if n.y > 0 else c.x), c.z
                else:
                    u, v = c.x, c.y
                lp[uv].uv = (u / t, v / t)
    with_bm(obj, fn)


def bevel(obj, width, segments=2, angle=35.0):
    for p in obj.data.polygons:
        p.use_smooth = True
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    m.harden_normals = True
    try:
        m.miter_outer = "MITER_ARC"
    except Exception:
        pass
    apply_mods(obj)


def in_box(c, b, e=1e-3):
    (x0, y0, z0), (x1, y1, z1) = b
    return (x0 - e <= c.x <= x1 + e) and (y0 - e <= c.y <= y1 + e) and (z0 - e <= c.z <= z1 + e)


# ---------------------------------------------------------------------------
# Design constants (design coordinates; recentred at the end)
# ---------------------------------------------------------------------------

FFL0 = 0.95          # ground floor finished level (top of podium)
SOFFIT1 = 4.15       # underside of first-floor slab
FFL1 = 4.45          # first floor finished level
PLINTH_TOP = 0.5     # landscaped platform level

U1_OUT = ((-10.0, -4.5, 4.15), (2.5, 4.5, 7.55))
U1_VOID = ((-9.4, -4.7, 4.45), (1.9, 4.2, 7.55))
U1_CAV = ((-9.4, -3.0, 4.45), (1.9, 4.2, 7.55))
U1_PLATE = ((-10.15, -4.65, 7.55), (2.5, 4.65, 7.85))
U1_PARAPET_OUT = ((-9.9, -4.4, 7.85), (2.25, 4.4, 8.15))
U1_PARAPET_IN = ((-9.7, -4.2, 7.80), (2.05, 4.2, 8.20))

U2_OUT = ((2.5, -2.0, 4.15), (7.8, 5.5, 7.35))
U2_CAV = ((2.8, -1.7, 4.45), (7.5, 5.2, 7.05))
U2_PARAPET_OUT = ((2.5, -2.0, 7.35), (7.8, 5.5, 7.6))
U2_PARAPET_IN = ((2.7, -1.8, 7.30), (7.6, 5.3, 7.65))

BLK_OUT = ((0.5, -2.0, 0.95), (7.0, 4.5, 4.15))
BLK_CAV = ((0.8, -1.7, 0.95), (6.7, 4.2, 4.15))
BLK_LINER = ((0.6, -2.0, 0.95), (2.7, -0.55, 4.15))
RECESS = ((0.9, -2.1, 0.9), (2.4, -0.85, 4.2))
RECESS_EXCL = ((0.9, -2.1, 0.9), (2.4, -0.6, 4.2))
DOOR_OPEN = ((1.0, -0.9, 0.9), (2.3, -0.5, 3.65))

PAVILION = ((-8.0, -3.0, 0.95), (0.5, 3.5, 4.15))

PLINTH = ((-16.2, -11.0, 0.0), (13.8, 12.0, PLINTH_TOP))
PODIUM = ((-9.0, -4.0, PLINTH_TOP), (7.4, 5.6, FFL0))
POOL = ((-8.5, 7.4, 0.1), (-1.0, 10.4, 0.6))
LAWN_H = 0.02
LAWNS = [
    ((-15.6, -10.4), (0.6, -5.6)),
    ((2.7, -10.4), (13.2, -5.6)),
    ((-15.6, -5.0), (-10.8, 11.4)),
    ((8.4, -5.0), (13.2, 6.6)),
    ((0.0, 7.4), (13.2, 11.4)),
]


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------

def build_structure(C, M):
    tmp = C["tmp"]
    # Upper cantilevered volume (U1) -----------------------------------
    u1 = box_obj("U1", *U1_OUT, tmp)
    boolean(u1, [
        box_obj("c", *U1_VOID, tmp),
        box_obj("c", (-10.2, -2.0, 4.45), (-9.3, 2.5, 7.55), tmp),   # west full-height window
        box_obj("c", (-9.0, 4.1, 5.0), (1.4, 4.6, 7.2), tmp),        # north ribbon window
        box_obj("c", (1.8, -2.85, 4.45), (2.6, -2.25, 7.55), tmp),   # east slot window
    ])
    ring = box_obj("ring", *U1_PARAPET_OUT, tmp)
    boolean(ring, [box_obj("c", *U1_PARAPET_IN, tmp)])
    boolean(u1, [box_obj("plate", *U1_PLATE, tmp), ring], op="UNION")

    # Upper offset volume (U2) ------------------------------------------
    u2 = box_obj("U2", *U2_OUT, tmp)
    boolean(u2, [
        box_obj("c", *U2_CAV, tmp),
        box_obj("c", (3.2, -2.1, 4.45), (7.2, -1.6, 7.05), tmp),     # south picture window
        box_obj("c", (7.4, 0.0, 5.2), (7.9, 4.5, 6.8), tmp),         # east ribbon
        box_obj("c", (3.0, 5.1, 4.45), (6.2, 5.6, 7.05), tmp),       # north window
    ])
    ring2 = box_obj("ring2", *U2_PARAPET_OUT, tmp)
    boolean(ring2, [box_obj("c", *U2_PARAPET_IN, tmp)])
    boolean(u2, [ring2], op="UNION")

    # Ground-floor solid block with recessed entrance ---------------------
    blk = box_obj("BLK", *BLK_OUT, tmp)
    boolean(blk, [box_obj("c", (0.8, -1.7, 0.9), (6.7, 4.2, 4.2), tmp)])
    boolean(blk, [box_obj("liner", *BLK_LINER, tmp)], op="UNION")
    boolean(blk, [
        box_obj("c", *RECESS, tmp),
        box_obj("c", *DOOR_OPEN, tmp),
        box_obj("c", (3.6, -2.1, 1.85), (6.6, -1.6, 3.75), tmp),      # kitchen window
        box_obj("c", (6.6, -0.5, 1.25), (7.1, 0.1, 3.75), tmp),       # east slots
        box_obj("c", (6.6, 1.0, 1.25), (7.1, 1.6, 3.75), tmp),
        box_obj("c", (6.6, 2.5, 1.25), (7.1, 3.1, 3.75), tmp),
        box_obj("c", (1.2, 4.1, 0.9), (6.3, 4.6, 3.85), tmp),         # garden sliding wall
    ])

    boolean(u1, [u2, blk], op="UNION")
    st = u1
    st.name = "Villa_Structure_Concrete"
    set_materials(st, [M["concrete_white"], M["concrete_grey"], M["plaster"], M["wood_oak"], M["gravel"]])
    CW, CG, PL, WD, GR = range(5)

    def fn(bm):
        clean_mesh(bm, dissolve=False)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        # split U1 faces at the balcony glass line so inside/outside can differ
        sub = [f for f in bm.faces if in_box(f.calc_center_median(), ((-9.45, -4.8, 4.4), (1.95, 4.3, 7.6)), 0)]
        geom = list({v for f in sub for v in f.verts}) + list({e for f in sub for e in f.edges}) + sub
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, -3.0, 0), plane_no=(0, 1, 0), dist=1e-5)
        bm.faces.ensure_lookup_table()
        # remove hidden faces sitting on the podium (block wall undersides)
        dead = [f for f in bm.faces if f.normal.z < -0.9 and abs(f.calc_center_median().z - FFL0) < 1e-3]
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        for f in bm.faces:
            c = f.calc_center_median()
            n = f.normal
            interior = in_box(c, U1_CAV) or in_box(c, U2_CAV) or (in_box(c, BLK_CAV) and not in_box(c, RECESS_EXCL))
            if interior:
                f.material_index = WD if n.z > 0.7 else PL
                continue
            if n.z > 0.9 and abs(c.z - 7.85) < 1e-3 and in_box(c, U1_PARAPET_IN, 0):
                f.material_index = GR
            elif n.z > 0.9 and abs(c.z - 7.35) < 1e-3 and in_box(c, U2_PARAPET_IN, 0):
                f.material_index = GR
            elif n.z > 0.9 and abs(c.z - FFL1) < 1e-3 and c.y < -3.0:
                f.material_index = WD   # balcony deck
            elif c.z < SOFFIT1 - 1e-3 or c.x > 2.5 + 1e-3 or (abs(c.x - 2.5) < 1e-3 and n.x < -0.5):
                f.material_index = CG
            else:
                f.material_index = CW
        clean_mesh(bm, dissolve=True)
    with_bm(st, fn)
    box_uv(st, {CW: 4.0, CG: 4.0, PL: 4.0, WD: 2.4, GR: 2.0})
    bevel(st, 0.012, 2, 40)
    move_to(st, C["structure"])
    return st


def build_platform(C, M):
    tmp = C["tmp"]
    pl = box_obj("PL", *PLINTH, tmp)
    ops = [box_obj("podium", *PODIUM, tmp)]
    # entrance steps: plinth -> podium (3 x 150 mm)
    mb = MB()
    mb.prism([(-5.2, 0.5), (-4.0, 0.5), (-4.0, 0.95), (-4.4, 0.95), (-4.4, 0.8), (-4.8, 0.8), (-4.8, 0.65), (-5.2, 0.65)],
             "x", 0.6, 2.7)
    ops.append(mb.to_object("steps_entry", tmp))
    # garden steps: podium -> pool deck
    mb = MB()
    mb.prism([(5.6, 0.5), (6.8, 0.5), (6.8, 0.65), (6.4, 0.65), (6.4, 0.8), (6.0, 0.8), (6.0, 0.95), (5.6, 0.95)],
             "x", -5.5, -3.0)
    ops.append(mb.to_object("steps_garden", tmp))
    # site steps: ground -> platform
    s = 0.5 / 3
    mb = MB()
    mb.prism([(-12.0, 0.0), (-11.0, 0.0), (-11.0, 0.5), (-11.333, 0.5), (-11.333, 2 * s), (-11.667, 2 * s),
              (-11.667, s), (-12.0, s)], "x", 0.6, 2.7)
    ops.append(mb.to_object("steps_site", tmp))
    for i, (a, b) in enumerate(LAWNS):
        ops.append(box_obj("lawn%d" % i, (a[0], a[1], PLINTH_TOP), (b[0], b[1], PLINTH_TOP + LAWN_H), tmp))
    boolean(pl, ops, op="UNION")
    boolean(pl, [box_obj("pool", *POOL, tmp)])
    pl.name = "Site_Platform_Terraces_Pool"
    set_materials(pl, [M["paving"], M["concrete_plinth"], M["lawn"], M["pool_tile"]])
    PV, CD, LW, PT = range(4)

    def fn(bm):
        clean_mesh(bm, dissolve=False)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        dead = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < 1e-3]
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        for f in bm.faces:
            c, n = f.calc_center_median(), f.normal
            if in_box(c, ((POOL[0][0], POOL[0][1], POOL[0][2]), (POOL[1][0], POOL[1][1], PLINTH_TOP - 1e-3)), 1e-3):
                f.material_index = PT
            elif PLINTH_TOP + 1e-4 < c.z <= PLINTH_TOP + LAWN_H + 1e-3 and any(
                    a[0] - 1e-3 <= c.x <= b[0] + 1e-3 and a[1] - 1e-3 <= c.y <= b[1] + 1e-3 for a, b in LAWNS):
                f.material_index = LW
            elif n.z > 0.9:
                f.material_index = PV
            else:
                f.material_index = CD
        clean_mesh(bm, dissolve=True)
    with_bm(pl, fn)
    box_uv(pl, {PV: 2.4, CD: 4.0, LW: 3.0, PT: 1.0})
    move_to(pl, C["landscape"])

    # pool water surface
    mb = MB()
    x0, y0 = POOL[0][0], POOL[0][1]
    x1, y1 = POOL[1][0], POOL[1][1]
    mb.quad([(x0, y0, 0.44), (x1, y0, 0.44), (x1, y1, 0.44), (x0, y1, 0.44)], M["water"])
    w = mb.to_object("Pool_Water_Surface", C["landscape"])
    box_uv(w, 4.0)
    return pl


def build_planter(C, M, name, mn, mx, inset=0.07, depth=0.12):
    tmp = C["tmp"]
    p = box_obj(name, mn, mx, tmp)
    boolean(p, [box_obj("c", (mn[0] + inset, mn[1] + inset, mx[2] - depth), (mx[0] - inset, mx[1] - inset, mx[2] + 0.1), tmp)])
    set_materials(p, [M["concrete_grey"], M["soil"]])

    def fn(bm):
        dead = [f for f in bm.faces if f.normal.z < -0.9 and abs(f.calc_center_median().z - mn[2]) < 1e-3]
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        for f in bm.faces:
            c = f.calc_center_median()
            f.material_index = 1 if (f.normal.z > 0.9 and c.z < mx[2] - 0.01) else 0
        clean_mesh(bm)
    with_bm(p, fn)
    box_uv(p, {0: 4.0, 1: 1.5})
    bevel(p, 0.006, 2, 40)
    move_to(p, C["landscape"])
    return p


# ---------------------------------------------------------------------------
# Glazing, frames, door, railing
# ---------------------------------------------------------------------------

def glazing(fr, gl, M, axis, c, u0, u1, z0, z1, bays=1, contact=("top", "bottom", "left", "right"),
            fw=0.06, fd=0.10, mw=0.05):
    """Aluminium frame + double-face glass panes in a vertical plane.
    axis='y': plane normal Y, runs along X (u = x, c = y).  axis='x': u = y, c = x."""
    def B(mbld, ua, ub, da, db, za, zb, mat, skip_local=()):
        mp = {"-u": "-x", "+u": "+x", "-d": "-y", "+d": "+y"} if axis == "y" else \
             {"-u": "-y", "+u": "+y", "-d": "-x", "+d": "+x"}
        skip = [mp.get(s, s) for s in skip_local]
        if axis == "y":
            mbld.box((ua, da, za), (ub, db, zb), mat, skip)
        else:
            mbld.box((da, ua, za), (db, ub, zb), mat, skip)

    d0, d1 = c - fd / 2, c + fd / 2
    ends = (["-u"] if "left" in contact else []) + (["+u"] if "right" in contact else [])
    B(fr, u0, u1, d0, d1, z0, z0 + fw, M["alu"], ends + (["-z"] if "bottom" in contact else []))
    B(fr, u0, u1, d0, d1, z1 - fw, z1, M["alu"], ends + (["+z"] if "top" in contact else []))
    B(fr, u0, u0 + fw, d0, d1, z0 + fw, z1 - fw, M["alu"], ["-z", "+z"] + (["-u"] if "left" in contact else []))
    B(fr, u1 - fw, u1, d0, d1, z0 + fw, z1 - fw, M["alu"], ["-z", "+z"] + (["+u"] if "right" in contact else []))
    a, b = u0 + fw, u1 - fw
    bw = (b - a - (bays - 1) * mw) / bays
    for i in range(bays):
        ua = a + i * (bw + mw)
        ub = ua + bw
        if i < bays - 1:
            B(fr, ub, ub + mw, d0 + 0.01, d1 - 0.01, z0 + fw, z1 - fw, M["alu"], ["-z", "+z"])
        B(gl, ua, ub, c - 0.006, c + 0.006, z0 + fw, z1 - fw, M["glass"], ["-u", "+u", "-z", "+z"])


def build_glazing(C, M):
    G = C["glazing"]
    specs = [
        # name, axis, c, u0, u1, z0, z1, bays, contact
        ("Pavilion_South", "y", -3.0, -8.05, 0.55, FFL0, SOFFIT1, 5, ("top", "bottom")),
        ("Pavilion_West", "x", -8.0, -2.95, 3.45, FFL0, SOFFIT1, 4, ("top", "bottom")),
        ("Pavilion_North", "y", 3.5, -8.05, 0.5, FFL0, SOFFIT1, 5, ("top", "bottom", "right")),
        ("Pavilion_East", "x", 0.5, -2.95, -2.0, FFL0, SOFFIT1, 1, ("top", "bottom")),
        ("Upper_Balcony_Wall", "y", -3.0, -9.4, 1.9, FFL1, 7.55, 6, None),
        ("Upper_West_Window", "x", -9.7, -2.0, 2.5, FFL1, 7.55, 3, None),
        ("Upper_North_Ribbon", "y", 4.35, -9.0, 1.4, 5.0, 7.2, 6, None),
        ("Upper_East_Slot", "x", 2.2, -2.85, -2.25, FFL1, 7.55, 1, None),
        ("Upper2_South_Picture", "y", -1.85, 3.2, 7.2, FFL1, 7.05, 3, None),
        ("Upper2_East_Ribbon", "x", 7.65, 0.0, 4.5, 5.2, 6.8, 3, None),
        ("Upper2_North_Window", "y", 5.35, 3.0, 6.2, FFL1, 7.05, 2, None),
        ("Ground_Kitchen_South", "y", -1.85, 3.6, 6.6, 1.85, 3.75, 2, None),
        ("Ground_Garden_Sliding", "y", 4.35, 1.2, 6.3, FFL0, 3.85, 4, None),
    ]
    for nm, ax, c, u0, u1, z0, z1, bays, contact in specs:
        fr, gl = MB(), MB()
        glazing(fr, gl, M, ax, c, u0, u1, z0, z1, bays,
                contact if contact is not None else ("top", "bottom", "left", "right"))
        fr.to_object("Frame_" + nm, G)
        gl.to_object("Glass_" + nm, G)
    fr, gl = MB(), MB()
    for y0, y1 in ((-0.5, 0.1), (1.0, 1.6), (2.5, 3.1)):
        glazing(fr, gl, M, "x", 6.85, y0, y1, 1.25, 3.75, 1)
    fr.to_object("Frame_Ground_East_Slots", G)
    gl.to_object("Glass_Ground_East_Slots", G)

    # Vertical aluminium fins in front of the U2 picture window
    fins = MB()
    for k in range(1, 6):
        x = 3.2 + k * (4.0 / 6.0)
        fins.box((x - 0.025, -2.35, FFL1), (x + 0.025, -1.96, 7.05), M["alu"])
    fins.to_object("Upper2_Vertical_Fins", C["details"])

    # Balcony glass balustrade with recessed base channel and slim handrail
    rail, rg = MB(), MB()
    rail.box((-9.4, -4.45, FFL1), (1.9, -4.33, FFL1 + 0.12), M["alu"], ["-x", "+x", "-z"])
    rail.box((-9.4, -4.42, 5.52), (1.9, -4.36, 5.56), M["alu"], ["-x", "+x"])
    n = 5
    span = 11.3
    for i in range(n):
        xa = -9.4 + i * span / n + (0.0 if i == 0 else 0.006)
        xb = -9.4 + (i + 1) * span / n - (0.0 if i == n - 1 else 0.006)
        rg.box((xa, -4.397, FFL1 + 0.12), (xb, -4.383, 5.52), M["glass"], ["-z", "+z"])
    rail.to_object("Balcony_Railing_Aluminium", C["details"])
    rg.to_object("Balcony_Railing_Glass", C["details"])

    # Entrance pivot door, side light and frame
    d = MB()
    y0, y1 = -0.75, -0.65
    d.box((1.0, y0, FFL0), (1.06, y1, 3.65), M["alu"], ["-x", "-z", "+z"])
    d.box((2.24, y0, FFL0), (2.30, y1, 3.65), M["alu"], ["+x", "-z", "+z"])
    d.box((1.0, y0, 3.59), (2.30, y1, 3.65), M["alu"], ["+z", "-x", "+x"])
    d.box((2.0, y0, FFL0), (2.05, y1, 3.59), M["alu"], ["-z", "+z"])
    d.box((1.08, -0.74, FFL0), (1.98, -0.66, 3.57), M["wood_dark"], ["-z"])
    d.box((1.82, -0.86, 1.55), (1.85, -0.83, 2.85), M["alu"])
    for zz in (1.62, 2.76):
        d.box((1.826, -0.83, zz), (1.844, -0.74, zz + 0.03), M["alu"], ["+y"])
    door = d.to_object("Entrance_Pivot_Door", C["details"])
    box_uv(door, 2.4)
    g = MB()
    g.box((2.05, -0.706, FFL0), (2.24, -0.694, 3.59), M["glass"], ["-x", "+x", "-z", "+z"])
    g.to_object("Glass_Entrance_Sidelight", C["glazing"])


# ---------------------------------------------------------------------------
# Lighting fixtures (emissive geometry only; no light objects exported)
# ---------------------------------------------------------------------------

def build_fixtures(C, M):
    ext = MB()
    z = SOFFIT1
    pts = []
    pts += [(x, -3.8) for x in (-9.2, -7.4, -5.6, -3.8, -2.0, -0.2)]
    pts += [(1.65, -3.3), (1.65, -1.45)]
    pts += [(-9.0, y) for y in (-2.0, 0.0, 2.0)]
    pts += [(x, 4.0) for x in (-8.8, -6.4, -4.0, -1.6)]
    pts += [(7.4, y) for y in (-1.2, 0.8, 2.8, 4.8)]
    pts += [(x, 5.0) for x in (3.4, 5.2)]
    for x, y in pts:
        ext.cylinder(x, y, z - 0.012, z, 0.065, 12, M["light_ext"], top=False)
    ext.box((-9.3, -4.36, 7.538), (1.8, -4.31, 7.55), M["light_ext"], ["+z"])     # balcony LED line
    ext.box((0.95, -1.0, z - 0.012), (2.35, -0.95, z), M["light_ext"], ["+z"])     # door wall-washer
    # pool lights
    for x in (-6.5, -3.0):
        ext.box((x - 0.15, 7.4, 0.24), (x + 0.15, 7.408, 0.32), M["light_ext"], ["-y"])
    ext.to_object("Lighting_Exterior_Emissive", C["lighting"])

    b = MB()
    for x in (0.35, 2.95):
        for y in (-10.0, -8.2, -6.4):
            b.box((x - 0.07, y - 0.07, PLINTH_TOP), (x + 0.07, y + 0.07, 1.25), M["alu"], ["-z"])
            side = 0.07 if x < 1.6 else -0.07
            b.box((x + side - (0.004 if side < 0 else 0), y - 0.05, 1.12),
                  (x + side + (0.004 if side > 0 else 0), y + 0.05, 1.18), M["light_ext"],
                  ["-x"] if side > 0 else ["+x"])
    b.to_object("Landscape_Path_Bollards", C["lighting"])

    it = MB()
    for y in (-1.5, 0.25, 2.0):
        it.box((-7.4, y - 0.03, SOFFIT1 - 0.01), (-0.2, y + 0.03, SOFFIT1), M["light_int"], ["+z"])
    for y in (0.0, 2.5):
        it.box((-9.0, y - 0.03, 7.54), (1.5, y + 0.03, 7.55), M["light_int"], ["+z"])
    it.box((5.1 - 0.03, -1.2, 7.04), (5.1 + 0.03, 4.8, 7.05), M["light_int"], ["+z"])
    for y in (0.5, 3.0):
        it.box((3.0, y - 0.03, SOFFIT1 - 0.01), (6.4, y + 0.03, SOFFIT1), M["light_int"], ["+z"])
    it.to_object("Lighting_Interior_Emissive", C["lighting"])


# ---------------------------------------------------------------------------
# Interior & exterior furniture (simple, low poly, readable through glass)
# ---------------------------------------------------------------------------

def build_furniture(C, M):
    f = MB()
    z = FFL0
    # L sofa
    f.box((-6.8, -0.2, z), (-3.6, 0.7, z + 0.42), M["fabric"], ["-z"])
    f.box((-6.8, 0.7, z), (-3.6, 0.95, z + 0.82), M["fabric"], ["-z"])
    f.box((-6.8, -1.6, z), (-5.9, -0.2, z + 0.42), M["fabric"], ["-z", "+y"])
    f.box((-5.3, -1.5, z), (-4.1, -0.8, z + 0.34), M["stone_top"], ["-z"])
    # dining
    f.box((-2.6, 0.6, z + 0.72), (-0.6, 1.6, z + 0.77), M["wood_oak"])
    for x in (-2.5, -0.75):
        f.box((x, 0.75, z), (x + 0.05, 1.45, z + 0.72), M["wood_oak"], ["-z", "+z"])
    for x in (-2.3, -1.6, -0.9):
        for y, s in ((0.15, -1), (2.05, 1)):
            f.box((x - 0.22, y - 0.22, z), (x + 0.22, y + 0.22, z + 0.46), M["fabric_dark"], ["-z"])
            yb = y + s * 0.22
            f.box((x - 0.22, min(yb, yb + s * 0.06), z + 0.46), (x + 0.22, max(yb, yb + s * 0.06), z + 0.9),
                  M["fabric_dark"], ["-z"])
    # kitchen island
    f.box((2.7, 1.7, z), (5.3, 2.4, z + 0.88), M["lacquer"], ["-z", "+z"])
    f.box((2.62, 1.62, z + 0.88), (5.38, 2.48, z + 0.93), M["stone_top"])
    # bedroom (U1)
    z1 = FFL1
    f.box((-7.5, 0.8, z1), (-5.3, 3.0, z1 + 0.48), M["fabric"], ["-z", "+y"])
    f.box((-7.6, 3.0, z1), (-5.2, 3.15, z1 + 1.2), M["wood_oak"], ["-z"])
    # study (U2)
    f.box((4.0, 2.0, z1 + 0.73), (6.2, 2.7, z1 + 0.77), M["wood_oak"])
    for x in (4.05, 6.1):
        f.box((x, 2.05, z1), (x + 0.05, 2.65, z1 + 0.73), M["alu"], ["-z", "+z"])
    f.box((4.6, 1.2, z1), (5.3, 1.8, z1 + 0.45), M["fabric_dark"], ["-z"])
    # balcony lounge chairs
    for x in (-7.8, -6.6):
        f.box((x, -4.2, z1), (x + 0.75, -3.45, z1 + 0.38), M["lacquer"], ["-z"])
    ob = f.to_object("Interior_Furniture", C["interior"])
    box_uv(ob, 2.4)

    # Pool loungers (exterior)
    lg = MB()
    for x in (-10.4, -9.5):
        lg.box((x, 7.6, PLINTH_TOP), (x + 0.7, 9.6, PLINTH_TOP + 0.3), M["lacquer"], ["-z"])
        lg.box((x + 0.04, 7.64, PLINTH_TOP + 0.3), (x + 0.66, 9.0, PLINTH_TOP + 0.38), M["fabric"], ["-z"])
        lg.prism([(9.0, PLINTH_TOP + 0.3), (9.56, PLINTH_TOP + 0.3), (9.56, PLINTH_TOP + 0.36), (9.2, PLINTH_TOP + 0.85),
                  (9.05, PLINTH_TOP + 0.85)], "x", x + 0.04, x + 0.66, M["fabric"])
    lg.to_object("Exterior_Pool_Loungers", C["landscape"])

    # rooftop: louvred plant enclosure + solar array
    r = MB()
    r.box((-3.0, 0.6, 7.85), (-0.6, 1.8, 8.55), M["alu"], ["-z"])
    pv = MB()
    for i in range(5):
        y0 = -1.2 + i * 1.25
        pv.prism([(y0, 7.35), (y0 + 1.05, 7.35), (y0 + 1.05, 7.58), (y0, 7.43)], "x", 3.1, 7.2, M["pv"])
    r.to_object("Roof_Plant_Enclosure", C["details"])
    pvo = pv.to_object("Roof_Solar_Array", C["details"])
    # the array sits directly on the roof: drop its hidden underside
    with_bm(pvo, lambda bm: bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.9], context="FACES"))


# ---------------------------------------------------------------------------
# Vegetation
# ---------------------------------------------------------------------------

def blob(name, spheres, coll, mat, seed, voxel=0.12, target=2400, amp=0.18, subdiv=3, freq=1.3):
    bm = bmesh.new()
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    for c, r in spheres:
        res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r, matrix=Matrix.Translation(c))
        for v in res["verts"]:
            d = (v.co - Vector(c))
            dn = d.normalized()
            k = noise.noise(v.co * freq + off) * 0.6 + noise.noise(v.co * freq * 2.4 + off) * 0.4
            v.co += dn * (amp * r * k)
            v.co.z -= max(0.0, -d.z) * 0.25   # slightly flattened underside
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    m = obj.modifiers.new("Remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    apply_mods(obj)
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if tris > target:
        m = obj.modifiers.new("Decimate", "DECIMATE")
        m.ratio = target / tris
        apply_mods(obj)
    # re-assign material (remesh keeps slot 0)
    set_materials(obj, [mat])
    for p in obj.data.polygons:
        p.use_smooth = True
    box_uv(obj, 1.5)
    return obj


def tree(C, M, name, x, y, h, crown, seed, kind="A"):
    rnd = random.Random(seed)
    base = PLINTH_TOP + LAWN_H
    tr = MB()
    lean = Vector((rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), 0))
    top = Vector((x, y, base + h * 0.62)) + lean
    tr.cylinder(x, y, base - 0.05, base + h * 0.45, 0.17 if kind == "A" else 0.13, 9, M["bark"],
                top=True, bottom=False, r_top=0.11 if kind == "A" else 0.09)
    # branches
    bm = tr.bm
    for k in range(3 if kind == "A" else 2):
        a = rnd.uniform(0, 2 * math.pi)
        z0 = base + h * rnd.uniform(0.32, 0.42)
        p0 = Vector((x, y, z0))
        p1 = Vector((x + math.cos(a) * crown * 0.45, y + math.sin(a) * crown * 0.45, base + h * rnd.uniform(0.62, 0.72)))
        axis = (p1 - p0)
        L = axis.length
        q = axis.to_track_quat("Z", "Y")
        mtx = Matrix.Translation(p0) @ q.to_matrix().to_4x4()
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.075, radius2=0.035, depth=L,
                                    matrix=mtx @ Matrix.Translation((0, 0, L / 2)))
        for f in {f for v in res["verts"] for f in v.link_faces}:
            f.material_index = tr.mi(M["bark"])
    trunk = tr.to_object("Tree_%s_Trunk" % name, C["vegetation"], smooth=True)
    box_uv(trunk, 1.0)
    spheres = []
    cz = base + h * (0.68 if kind == "A" else 0.64)
    rx = crown * (1.0 if kind == "A" else 0.8)
    rz = h * (0.24 if kind == "A" else 0.30)
    n = 48 if kind == "A" else 38
    tries = 0
    while len(spheres) < n and tries < 2000:
        tries += 1
        p = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
        if p.length > 1.0:
            continue
        r = crown * rnd.uniform(0.15, 0.26) * (1.15 - 0.35 * p.length)
        spheres.append(((x + lean.x + p.x * rx * 0.85, y + lean.y + p.y * rx * 0.85, cz + p.z * rz), r))
    blob("Tree_%s_Canopy" % name, spheres, C["vegetation"], M["foliage_a"] if kind == "A" else M["foliage_b"],
         seed, voxel=0.075, target=6500 if kind == "A" else 5200, amp=0.55, subdiv=2, freq=4.2)


def shrub(C, M, name, x, y, r, seed, base=PLINTH_TOP + LAWN_H, mat=None):
    rnd = random.Random(seed)
    sp = []
    for i in range(4):
        a = rnd.uniform(0, 2 * math.pi)
        d = r * rnd.uniform(0.1, 0.45)
        rr = r * rnd.uniform(0.55, 0.8)
        sp.append(((x + math.cos(a) * d, y + math.sin(a) * d, base + rr * 0.75), rr))
    return blob("Shrub_" + name, sp, C["vegetation"], mat or M["foliage_a"], seed, voxel=0.06, target=900, amp=0.22, subdiv=2)


def grass_clump(mb, M, x, y, base, seed, h=0.65, blades=40, spread=0.17):
    rnd = random.Random(seed)
    for _ in range(blades):
        a = rnd.uniform(0, 2 * math.pi)
        rr = spread * math.sqrt(rnd.random())
        px, py = x + math.cos(a) * rr, y + math.sin(a) * rr
        hh = h * rnd.uniform(0.6, 1.1)
        lean_dir = Vector((math.cos(a), math.sin(a), 0)) * rnd.uniform(0.15, 0.45)
        side = Vector((-math.sin(a + 1.2), math.cos(a + 1.2), 0))
        w0 = 0.018
        pts = []
        for t in (0.0, 0.35, 0.7):
            c = Vector((px, py, base - 0.02)) + Vector((0, 0, hh * t)) + lean_dir * (hh * t * t)
            w = w0 * (1 - t * 0.8)
            pts.append((c - side * w, c + side * w))
        tip = Vector((px, py, base - 0.02)) + Vector((0, 0, hh)) + lean_dir * hh
        vs = [(mb.bm.verts.new(l), mb.bm.verts.new(r)) for l, r in pts]
        vt = mb.bm.verts.new(tip)
        idx = mb.mi(M["grass"])
        for i in range(2):
            f = mb.bm.faces.new([vs[i][0], vs[i][1], vs[i + 1][1], vs[i + 1][0]])
            f.material_index = idx
        f = mb.bm.faces.new([vs[2][0], vs[2][1], vt])
        f.material_index = idx


def build_vegetation(C, M):
    tree(C, M, "WestGarden", -14.0, 6.2, 5.0, 1.7, 11, "B")
    tree(C, M, "FrontEast", 11.0, -8.0, 6.2, 2.3, 23, "B")
    tree(C, M, "RearWest", -13.4, 10.0, 5.8, 2.2, 37, "B")
    tree(C, M, "RearEast", 10.8, 9.6, 7.0, 2.7, 41, "A")
    tree(C, M, "East", 11.8, 2.6, 5.4, 2.0, 53, "B")
    lawn_z = PLINTH_TOP + LAWN_H
    shrubs = [(-12.4, -3.2, 0.75), (-12.0, -1.6, 0.6), (-12.8, 4.6, 0.8), (-12.1, 6.0, 0.55),
              (10.0, -3.6, 0.7), (9.8, 5.6, 0.65), (3.0, 10.4, 0.8), (6.6, 10.9, 0.6), (-14.6, -9.6, 0.55), (-13.3, -8.7, 0.8), (-11.6, -9.9, 0.5),
              (12.5, -9.8, 0.6)]
    for i, (x, y, r) in enumerate(shrubs):
        shrub(C, M, "%02d" % (i + 1), x, y, r, 100 + i, lawn_z, M["foliage_a"] if i % 2 else M["foliage_b"])
    gb = MB()
    k = 0
    # front planter (top 0.95, soil at 0.83)
    for i in range(9):
        grass_clump(gb, M, -7.6 + i * 0.72, -5.1 + (0.08 if i % 2 else -0.08), 0.83, 300 + i)
    # podium planter by the entrance (top 1.40, soil 1.28)
    for i in range(4):
        grass_clump(gb, M, 3.8 + i * 0.8, -3.1, 1.28, 400 + i, h=0.55)
    shrub(C, M, "Entrance", 6.2, -3.1, 0.42, 77, 1.28, M["foliage_a"])
    # lawn accents around trees and the pool
    for (x, y, s) in ((-12.0, -7.0, 1), (-14.0, -7.2, 2), (10.0, -7.0, 3), (12.0, -6.8, 4), (-12.4, 9.0, 5),
                      (9.6, 8.6, 6), (11.8, 8.8, 7), (1.0, 8.2, 8), (1.6, 8.9, 9), (-12.2, 2.4, 10)):
        grass_clump(gb, M, x, y, lawn_z, 500 + s, h=0.7)
        k += 1
    gb.to_object("Vegetation_Ornamental_Grasses", C["vegetation"])
    # indoor plant
    pot = MB()
    pot.cylinder(-7.45, -2.45, FFL0, FFL0 + 0.55, 0.24, 16, M["concrete_plinth"], bottom=False, r_top=0.26)
    box_uv(pot.to_object("Interior_Planter_Pot", C["interior"]), 4.0)
    shrub(C, M, "Interior_Plant", -7.45, -2.45, 0.4, 88, FFL0 + 0.5, M["foliage_a"])


# ---------------------------------------------------------------------------
# Scene organisation
# ---------------------------------------------------------------------------

def move_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def make_collections():
    sc = bpy.context.scene.collection
    root = bpy.data.collections.new("SmartEstate_Villa")
    sc.children.link(root)
    C = {"root": root}
    for key, nm in (("structure", "01_Structure"), ("glazing", "02_Glazing"), ("details", "03_Architectural_Details"),
                    ("interior", "04_Interior"), ("landscape", "05_Landscape"), ("vegetation", "06_Vegetation"),
                    ("lighting", "07_Lighting_Fixtures")):
        c = bpy.data.collections.new(nm)
        root.children.link(c)
        C[key] = c
    C["tmp"] = bpy.data.collections.new("TMP_Build")
    sc.children.link(C["tmp"])
    return C


def villa_objects(C):
    out = []
    for key in ("structure", "glazing", "details", "interior", "landscape", "vegetation", "lighting"):
        out += list(C[key].objects)
    return out


def finalize(C):
    objs = villa_objects(C)
    st = bpy.data.objects["Villa_Structure_Concrete"]
    xs = [v.co.x for v in st.data.vertices]
    ys = [v.co.y for v in st.data.vertices]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    T = Matrix.Translation((-cx, -cy, 0.0))
    for o in objs:
        o.data.transform(T)
        o.data.update()
    root = bpy.data.objects.new("SmartEstate_Modern_Villa", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 2.0
    C["root"].objects.link(root)
    for o in objs:
        o.parent = root
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_world = Matrix.Identity(4)
    bpy.data.collections.remove(C["tmp"])
    log("recentred by", (round(-cx, 3), round(-cy, 3)))
    return root, (cx, cy)


def mesh_report(objs):
    rep = {"objects": len(objs), "triangles": 0, "per_object": {}, "issues": []}
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        tris = len(me.loop_triangles)
        rep["triangles"] += tris
        bm = bmesh.new()
        bm.from_mesh(me)
        inconsistent = 0
        boundary = 0
        nonman = 0
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 1:
                boundary += 1
            elif len(lf) == 2:
                v0, v1 = e.verts
                same = 0
                for f in lf:
                    for lp in f.loops:
                        if lp.edge == e:
                            same += 1 if lp.vert == v0 else -1
                if same != 0:
                    inconsistent += 1
            elif len(lf) > 2:
                nonman += 1
        degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        loose = sum(1 for v in bm.verts if not v.link_faces)
        vol = bm.calc_volume(signed=True) if boundary == 0 and nonman == 0 else None
        bm.free()
        empty_slots = sum(1 for m in me.materials if m is None)
        used = {p.material_index for p in me.polygons}
        unused_slots = [i for i in range(len(me.materials)) if i not in used]
        rep["per_object"][o.name] = {"tris": tris, "boundary_edges": boundary, "inconsistent_normals": inconsistent,
                                     "nonmanifold_edges": nonman, "degenerate": degenerate, "loose_verts": loose,
                                     "signed_volume": None if vol is None else round(vol, 3),
                                     "materials": [m.name for m in me.materials if m]}
        if inconsistent or degenerate or loose or empty_slots or (vol is not None and vol < 0):
            rep["issues"].append((o.name, inconsistent, degenerate, loose, empty_slots, vol))
        if unused_slots:
            rep["issues"].append((o.name, "unused material slots", unused_slots))
        if o.modifiers:
            rep["issues"].append((o.name, "modifiers present"))
        if any(abs(a - b) > 1e-6 for a, b in zip(sum((list(r) for r in o.matrix_world), []),
                                                    sum((list(r) for r in Matrix.Identity(4)), []))):
            rep["issues"].append((o.name, "non-identity transform"))
    return rep


def fix_unused_slots(objs):
    for o in objs:
        me = o.data
        used = sorted({p.material_index for p in me.polygons})
        if len(used) == len(me.materials):
            continue
        remap = {old: new for new, old in enumerate(used)}
        mats = [me.materials[i] for i in used]
        for p in me.polygons:
            p.material_index = remap[p.material_index]
        me.materials.clear()
        for m in mats:
            me.materials.append(m)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_glb(C, root):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in villa_objects(C) + [root]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=GLB_PATH, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_cameras=False, export_lights=False, export_materials="EXPORT", export_image_format="JPEG",
              export_image_quality=88, export_texcoords=True, export_normals=True, export_tangents=False,
              export_extras=False, export_animations=False, export_skins=False, export_morph=False,
              export_draco_mesh_compression_enable=False, export_attributes=False,
              export_copyright="SmartEstate AI - original procedural demo asset (fictional property)")
    kw = {k: v for k, v in kw.items() if k in props or k == "filepath"}
    bpy.ops.export_scene.gltf(**kw)
    log("GLB exported:", GLB_PATH, "%.2f MB" % (os.path.getsize(GLB_PATH) / 1048576))


# ---------------------------------------------------------------------------
# Presentation scene: studio, lights, cameras, renders
# ---------------------------------------------------------------------------

def setup_gpu(scene):
    scene.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = t
            except Exception:
                continue
            try:
                prefs.refresh_devices()
            except Exception:
                prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == t]
            if devs:
                for d in prefs.devices:
                    d.use = d.type == t
                scene.cycles.device = "GPU"
                log("Cycles device:", t, [d.name for d in devs])
                return
    except Exception as e:
        log("GPU setup failed, using CPU:", e)
    scene.cycles.device = "CPU"


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def build_presentation():
    scene = bpy.context.scene
    pres = bpy.data.collections.new("Presentation_Studio")
    scene.collection.children.link(pres)

    # Studio ground with a soft radial falloff into the charcoal background
    mat = bpy.data.materials.new("M_Studio_Floor_Charcoal")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "LENGTH"
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 16.0
    mr.inputs["From Max"].default_value = 60.0
    mr.inputs["To Min"].default_value = 0.0
    mr.inputs["To Max"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (0.014, 0.0145, 0.016, 1)
    mix.inputs[7].default_value = (0.0025, 0.0026, 0.003, 1)
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    nt.links.new(comb.outputs[0], vm.inputs[0])
    nt.links.new(vm.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], mix.inputs[0])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    _set_in(b, ["Specular IOR Level", "Specular"], 0.3)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    mb = MB()
    mb.cylinder(0, 0, -0.002, -0.002, 160.0, 64, mat, top=True, bottom=False)
    # remove the zero-height side faces of the disc
    ground = mb.to_object("Studio_Ground_ContactShadow", pres)
    def fn(bm):
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-6], context="FACES")
        clean_mesh(bm, dissolve=False)
    with_bm(ground, fn)

    # World: charcoal backdrop for camera rays, soft grey sky for lighting
    w = bpy.data.worlds.new("W_Studio_Charcoal")
    scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    wt = w.node_tree
    wt.nodes.clear()
    wo = wt.nodes.new("ShaderNodeOutputWorld")
    bg_cam = wt.nodes.new("ShaderNodeBackground")
    bg_cam.inputs["Color"].default_value = (0.0075, 0.0078, 0.0088, 1)
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_light = wt.nodes.new("ShaderNodeBackground")
    bg_light.inputs["Color"].default_value = (0.55, 0.58, 0.63, 1)
    bg_light.inputs["Strength"].default_value = 0.32
    lp = wt.nodes.new("ShaderNodeLightPath")
    ms = wt.nodes.new("ShaderNodeMixShader")
    wt.links.new(lp.outputs["Is Camera Ray"], ms.inputs[0])
    wt.links.new(bg_light.outputs[0], ms.inputs[1])
    wt.links.new(bg_cam.outputs[0], ms.inputs[2])
    wt.links.new(ms.outputs[0], wo.inputs["Surface"])

    # Three-point light rig (rotated per shot so the key always rakes the facade)
    rig = bpy.data.objects.new("Light_Rig", None)
    pres.objects.link(rig)

    def add_light(name, kind, energy, color, loc, size=None, angle=None):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if size is not None:
            ld.shape = "RECTANGLE"
            ld.size = size
            ld.size_y = size * 0.6
        if angle is not None:
            ld.angle = math.radians(angle)
        lo = bpy.data.objects.new(name, ld)
        pres.objects.link(lo)
        lo.location = loc
        look_at(lo, (0, 0, 3))
        lo.parent = rig
        return lo

    # rig local frame: camera looks from -Y
    add_light("Key_Sun", "SUN", 3.0, (1.0, 0.93, 0.84), (-22, -26, 26), angle=3.5)
    add_light("Fill_Area", "AREA", 26000, (0.80, 0.87, 1.0), (30, -22, 10), size=24)
    add_light("Rim_Area", "AREA", 42000, (1.0, 0.95, 0.9), (6, 34, 20), size=18)

    def cam(name, loc, target, lens=40, ortho=None, shift_y=0.0):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.5
        cd.clip_end = 600
        cd.shift_y = shift_y
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = ortho
        co = bpy.data.objects.new(name, cd)
        pres.objects.link(co)
        co.location = loc
        look_at(co, target)
        return co

    cams = {
        "hero": cam("CAM_Hero_ThreeQuarter_Persp", (-27.0, -33.0, 10.5), (0.0, -0.5, 3.0), 38),
        "front": cam("CAM_Front_Persp", (0.0, -47.0, 4.2), (0.0, 0.0, 4.2), 46, shift_y=0.06),
        "rear": cam("CAM_Rear_Persp", (0.0, 47.0, 4.2), (0.0, 0.0, 4.2), 46, shift_y=0.06),
        "side": cam("CAM_Side_West_Persp", (-46.0, 0.0, 4.2), (0.0, 0.0, 4.2), 50, shift_y=0.06),
    }
    cam("CAM_ThreeQuarter_Ortho", (-40.0, -40.0, 30.0), (0.0, 0.0, 2.0), ortho=40.0)
    cam("CAM_Front_Ortho", (0.0, -60.0, 4.0), (0.0, 0.0, 4.0), ortho=34.0)
    scene.camera = cams["hero"]
    return cams, rig


def render_all(cams, rig):
    scene = bpy.context.scene
    setup_gpu(scene)
    cy = scene.cycles
    cy.samples = SAMPLES
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.015
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    cy.max_bounces = 10
    cy.transmission_bounces = 10
    cy.glossy_bounces = 6
    cy.diffuse_bounces = 4
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.sample_clamp_indirect = 8.0
    r = scene.render
    r.resolution_x, r.resolution_y = 1920, 1080
    r.resolution_percentage = RES_PCT
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    vs = scene.view_settings
    try:
        vs.view_transform = "AgX"
        for lk in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Base Contrast"):
            try:
                vs.look = lk
                break
            except Exception:
                continue
    except Exception:
        pass
    vs.exposure = -0.65
    shots = [("hero", "hero_render.png", -35.0), ("front", "front_render.png", 0.0),
             ("rear", "rear_render.png", 180.0), ("side", "side_render.png", -90.0)]
    for key, fn, rot in shots:
        rig.rotation_euler = (0, 0, math.radians(rot))
        scene.camera = cams[key]
        r.filepath = os.path.join(OUT_DIR, fn)
        t = time.time()
        bpy.ops.render.render(write_still=True)
        log("rendered", fn, "%.0fs" % (time.time() - t))
    rig.rotation_euler = (0, 0, math.radians(-35.0))
    scene.camera = cams["hero"]


# ---------------------------------------------------------------------------
# Validation of the exported GLB (clean scene re-import + raw glTF parse)
# ---------------------------------------------------------------------------

def parse_glb(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, ver, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF", "not a GLB"
    clen, ctype = struct.unpack_from("<II", data, 12)
    js = json.loads(data[20:20 + clen].decode("utf-8"))
    mins = [1e9] * 3
    maxs = [-1e9] * 3
    tris = 0
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            acc = js["accessors"][prim["attributes"]["POSITION"]]
            for i in range(3):
                mins[i] = min(mins[i], acc["min"][i])
                maxs[i] = max(maxs[i], acc["max"][i])
            if "indices" in prim:
                tris += js["accessors"][prim["indices"]]["count"] // 3
    nodes = js.get("nodes", [])
    non_identity = [n.get("name") for n in nodes if any(k in n for k in ("translation", "rotation", "scale", "matrix"))]
    return {
        "glb_version": ver, "bytes": length, "generator": js["asset"].get("generator"),
        "extensionsUsed": js.get("extensionsUsed", []), "nodes": len(nodes), "meshes": len(js.get("meshes", [])),
        "materials": len(js.get("materials", [])), "textures": len(js.get("textures", [])),
        "images": [(im.get("name"), im.get("mimeType"), "bufferView" in im) for im in js.get("images", [])],
        "cameras": len(js.get("cameras", [])), "has_lights": "KHR_lights_punctual" in js.get("extensionsUsed", []),
        "triangles": tris, "bbox_min_yup": [round(v, 4) for v in mins], "bbox_max_yup": [round(v, 4) for v in maxs],
        "nodes_with_transform": non_identity,
        "scene_roots": [nodes[i].get("name") for i in js["scenes"][js.get("scene", 0)]["nodes"]],
    }


def validate():
    log("=== VALIDATION: clean scene re-import of", GLB_PATH)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    raw = parse_glb(GLB_PATH)
    bpy.ops.import_scene.gltf(filepath=GLB_PATH)
    objs = list(bpy.context.scene.objects)
    meshes = [o for o in objs if o.type == "MESH"]
    kinds = sorted({o.type for o in objs})
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    tris = 0
    for o in meshes:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    mats = sorted({m.name for o in meshes for m in o.data.materials if m})
    tex = {}
    for m in bpy.data.materials:
        if m.node_tree:
            imgs = [n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
            if imgs:
                tex[m.name] = imgs
    images = [(i.name, i.size[0], i.size[1], bool(i.packed_file) or i.source) for i in bpy.data.images]
    st =next((o for o in meshes if o.name.startswith("Villa_Structure")), None)
    st_center = None
    if st:
        xs = [(st.matrix_world @ v.co).x for v in st.data.vertices]
        ys = [(st.matrix_world @ v.co).y for v in st.data.vertices]
        st_center = (round((min(xs) + max(xs)) / 2, 4), round((min(ys) + max(ys)) / 2, 4), round(min((st.matrix_world @ v.co).z for v in st.data.vertices), 4))
    root = [o for o in objs if o.parent is None]
    report = {
        "file_size_mb": round(os.path.getsize(GLB_PATH) / 1048576, 3),
        "object_types": kinds,
        "mesh_objects": len(meshes),
        "triangles_reimported": tris,
        "bbox_min_zup": [round(v, 3) for v in mn], "bbox_max_zup": [round(v, 3) for v in mx],
        "dimensions_m": [round(v, 3) for v in (mx - mn)],
        "structure_center_xy_and_base_z": st_center,
        "roots": [(o.name, o.type, [round(v, 4) for v in o.location]) for o in root],
        "materials": mats, "material_textures": tex, "images": images,
        "glb_json": raw,
    }
    # basic pass/fail gates
    gates = {
        "no_cameras_or_lights": raw["cameras"] == 0 and not raw["has_lights"] and "CAMERA" not in kinds and "LIGHT" not in kinds,
        "under_15mb": report["file_size_mb"] < 15.0,
        "tri_budget_30k_100k": 30000 <= tris <= 100000,
        "y_up_ground_at_zero": abs(raw["bbox_min_yup"][1]) < 1e-3,
        "textures_embedded": len(raw["images"]) > 0 and all(i[2] for i in raw["images"]),
        "materials_present": len(mats) >= 15,
        "pivot_at_building_centre": st_center is not None and abs(st_center[0]) < 0.01 and abs(st_center[1]) < 0.01,
    }
    report["gates"] = gates
    log(json.dumps(report, indent=1, default=str))
    if LOG_FILE:
        with open(os.path.splitext(LOG_FILE)[0] + "_validation.json", "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, default=str)
    log("ALL GATES PASSED" if all(gates.values()) else "GATES FAILED: %s" % [k for k, v in gates.items() if not v])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if VALIDATE_ONLY:
        validate()
        return
    log("Blender", bpy.app.version_string, "-> building villa into", OUT_DIR)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    T = build_textures()
    log("textures:", len(T))
    M = build_materials(T)
    C = make_collections()
    build_structure(C, M)
    log("structure done")
    build_platform(C, M)
    build_planter(C, M, "Planter_Front_Terrace", (-8.0, -5.45, PLINTH_TOP), (-1.5, -4.75, 0.95))
    build_planter(C, M, "Planter_Entrance_Podium", (3.4, -3.6, FFL0), (6.6, -2.6, 1.40))
    log("platform done")
    build_glazing(C, M)
    build_fixtures(C, M)
    build_furniture(C, M)
    log("details done")
    build_vegetation(C, M)
    log("vegetation done")
    objs = villa_objects(C)
    fix_unused_slots(objs)
    root, offset = finalize(C)
    rep = mesh_report(objs)
    log("mesh objects:", rep["objects"], "triangles:", rep["triangles"])
    for k, v in sorted(rep["per_object"].items()):
        log("  %-40s tris=%6d boundary=%5d inconsistent=%d nonman=%d degen=%d vol=%s" % (
            k, v["tris"], v["boundary_edges"], v["inconsistent_normals"], v["nonmanifold_edges"], v["degenerate"], v["signed_volume"]))
    log("issues:", rep["issues"] or "none")
    # purge anything unused (cutters, temp images, orphan meshes)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    export_glb(C, root)
    cams, rig = build_presentation()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    log("blend saved")
    if not SKIP_RENDER:
        render_all(cams, rig)
        bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("FATAL\n" + traceback.format_exc())
        raise
