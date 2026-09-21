"""Author the game's local USD scene and procedural material textures."""
from pathlib import Path
import itertools
import math

import numpy as np
from PIL import Image, ImageDraw
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdRender, UsdShade, Vt

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets3d"
COLORS = {"I": (65, 206, 232), "O": (247, 191, 68), "T": (159, 111, 232),
          "J": (77, 128, 227), "L": (245, 128, 61), "S": (141, 209, 88), "Z": (229, 82, 117)}
BLOCK_COUNT = 216  # 200 settled, four active, twelve preview blocks.
GHOST_COUNT, SPARK_COUNT, BEAM_COUNT = 4, 80, 24


def textures():
    ASSETS.mkdir(exist_ok=True)
    rng = np.random.default_rng(41)
    n = 256
    y, x = np.mgrid[:n, :n]
    grain = rng.normal(0, 0.008, (n, n)) + 0.007 * np.sin(y * 1.7)
    # Subtle machined grain, an inset rim, and two small corner markings.
    shade = np.ones((n, n)) + grain
    border = np.minimum.reduce([x, y, n - 1 - x, n - 1 - y])
    shade[border < 12] *= 0.68
    shade[(border >= 12) & (border < 15)] *= 1.1
    for kind, color in COLORS.items():
        pixels = np.clip(shade[:, :, None] * color, 0, 255).astype(np.uint8)
        img = Image.fromarray(pixels)
        draw = ImageDraw.Draw(img)
        marker = tuple(int(v * .65) for v in color)
        draw.line((30, 32, 56, 32), fill=marker, width=3)
        draw.line((30, 32, 30, 43), fill=marker, width=3)
        draw.line((202, 222, 224, 222), fill=marker, width=3)
        img.save(ASSETS / f"alloy-{kind}.png")
    rough = np.clip(89 + rng.normal(0, 2.5, (n, n)), 0, 255).astype(np.uint8)
    Image.fromarray(rough).save(ASSETS / "roughness.png")


def bevel_faces(half=.46, bevel=.065):
    """Six panels, twelve chamfers and eight clipped corners, outward wound."""
    inner = half - bevel
    faces = []
    for axis in range(3):
        other = [a for a in range(3) if a != axis]
        for sign in (-1, 1):
            face = []
            for u, v in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
                p = [0., 0., 0.]
                p[axis], p[other[0]], p[other[1]] = sign * half, u * inner, v * inner
                face.append(p)
            faces.append(face)
    for a, b in itertools.combinations(range(3), 2):
        c = 3 - a - b
        for sa, sb in itertools.product((-1, 1), repeat=2):
            face = []
            for first, end in [(True, -1), (False, -1), (False, 1), (True, 1)]:
                p = [0., 0., 0.]
                p[a], p[b], p[c] = sa*(half if first else inner), sb*(inner if first else half), end*inner
                face.append(p)
            faces.append(face)
    for sx, sy, sz in itertools.product((-1, 1), repeat=3):
        faces.append([[sx*half, sy*inner, sz*inner], [sx*inner, sy*half, sz*inner], [sx*inner, sy*inner, sz*half]])
    for face in faces:
        normal = np.cross(np.subtract(face[1], face[0]), np.subtract(face[2], face[0]))
        if np.dot(normal, np.mean(face, axis=0)) < 0:
            face.reverse()
    return faces


def create_mesh(stage, path, faces, material, position=(0, 0, 0), scale=(1, 1, 1)):
    mesh = UsdGeom.Mesh.Define(stage, path)
    points, counts, indices, normals, uv = [], [], [], [], []
    for face in faces:
        normal = np.cross(np.subtract(face[1], face[0]), np.subtract(face[2], face[0]))
        normal /= np.linalg.norm(normal)
        indices.extend(range(len(points), len(points) + len(face)))
        points.extend(face)
        counts.append(len(face))
        normals.extend([tuple(normal)] * len(face))
        uv.extend([(0, 0), (1, 0), (1, 1), (0, 1)][:len(face)])
    mesh.CreatePointsAttr(Vt.Vec3fArray(points))
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr("none")
    mesh.CreateNormalsAttr(Vt.Vec3fArray(normals))
    mesh.SetNormalsInterpolation("vertex")
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex").Set(Vt.Vec2fArray(uv))
    mat = Gf.Matrix4d(1)
    mat.SetScale(Gf.Vec3d(*scale))
    mat.SetTranslateOnly(Gf.Vec3d(*position))
    mesh.AddTransformOp().Set(mat)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


def material(stage, name, color, metallic=0., roughness=.35, emission=(0, 0, 0), texture=None):
    mat = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
    shader = UsdShade.Shader.Define(stage, f"{mat.GetPath()}/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emission))
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    if texture:
        st = UsdShade.Shader.Define(stage, f"{mat.GetPath()}/UV")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        tex = UsdShade.Shader.Define(stage, f"{mat.GetPath()}/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture))
        tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        shader.GetInput("diffuseColor").ConnectToSource(tex.ConnectableAPI(), "rgb")
        rough = UsdShade.Shader.Define(stage, f"{mat.GetPath()}/Grain")
        rough.CreateIdAttr("UsdUVTexture")
        rough.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("roughness.png"))
        rough.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        rough.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        shader.GetInput("roughness").ConnectToSource(rough.ConnectableAPI(), "r")
    return mat


def create_scene(width=1000, height=900):
    textures()
    stage = Usd.Stage.CreateNew(str(ASSETS / "board.usda"))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    mats = {k: material(stage, k, tuple((v/255)**2.2 for v in color), .28, texture=f"alloy-{k}.png") for k, color in COLORS.items()}
    mats["Frame"] = material(stage, "Frame", (.042, .058, .078), .75, .24)
    mats["Board"] = material(stage, "Board", (.006, .011, .018), .05, .58)
    mats["Floor"] = material(stage, "Floor", (.015, .022, .031), .48, .24)
    mats["Grid"] = material(stage, "Grid", (.023, .046, .056), .1, .45, (.012, .024, .03))
    mats["Cyan"] = material(stage, "Cyan", (.1, .5, .65), .25, .22, (.18, 1.3, 1.8))
    mats["Gold"] = material(stage, "Gold", (.8, .3, .05), .2, .25, (2.5, .75, .15))
    mats["Ghost"] = material(stage, "Ghost", (.15, .32, .38), .1, .45, (.1, .48, .64))
    cube = bevel_faces()
    def box(name, p, s, mat="Frame"):
        return create_mesh(stage, f"/World/Set/{name}", cube, mats[mat], p, tuple(v/.92 for v in s))
    box("Backplate", (0, 10, -.67), (10.5, 20.5, .34), "Board")
    for side in (-1, 1):
        suffix = "Left" if side < 0 else "Right"
        box(suffix, (side*5.3, 10, -.05), (.42, 20.85, 1.4))
        box(suffix+"Light", (side*5.055, 10, .27), (.045, 20.25, .045), "Cyan")
    box("Foot", (0, -.34, -.05), (11.1, .64, 1.8))
    box("Header", (0, 20.4, -.26), (11.1, .5, 1.15))
    box("LowerLight", (0, -.19, .84), (9.7, .035, .03), "Cyan")
    for x in range(1, 10):
        box(f"Column{x}", (x-5, 10, -.487), (.012, 20, .006), "Grid")
    for y in range(1, 20):
        box(f"Row{y}", (0, y, -.487), (10, .012, .006), "Grid")
    box("Plinth", (0, -.83, -.25), (13.2, .4, 3.4))
    box("Floor", (0, -1.08, 0), (150, .1, 150), "Floor")
    box("Backdrop", (0, 24, -15), (150, 70, .2), "Board")
    for x in range(-30, 31, 3):
        box(f"FloorX{x+30}", (x, -1.02, 0), (.013, .004, 100), "Grid")
    for z in range(-30, 31, 3):
        box(f"FloorZ{z+30}", (0, -1.02, z), (100, .004, .013), "Grid")
    for i in range(BLOCK_COUNT):
        # Reference each material at ingestion so its texture graph is registered
        # before runtime material:binding changes select it.
        create_mesh(stage, f"/World/Blocks/B{i:03}", cube, mats[list(COLORS)[i % 7]], (0, -100-i, 0))
    # A wireframe cube, assembled from twelve narrow rectangular prisms.
    wire = []
    for axis in range(3):
        other = [a for a in range(3) if a != axis]
        for a, b in itertools.product((-1, 1), repeat=2):
            scale = np.array([.026, .026, .026]); scale[axis] = .96
            center = np.zeros(3); center[other[0]]=a*.48; center[other[1]]=b*.48
            wire.extend([(np.asarray(face)*scale/.92+center).tolist() for face in cube])
    for i in range(GHOST_COUNT):
        create_mesh(stage, f"/World/Ghosts/G{i}", wire, mats["Ghost"], (0, -400-i, 0))
    for i in range(SPARK_COUNT):
        create_mesh(stage, f"/World/Sparks/S{i:03}", cube, mats["Gold" if i%3 else "Cyan"], (0, -500-i, 0))
    for i in range(BEAM_COUNT):
        create_mesh(stage, f"/World/Beams/E{i:02}", cube, mats["Cyan"], (0, -700-i, 0))
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    eye, target = Gf.Vec3d(7, 15, 39), Gf.Vec3d(0, 10, 0)
    camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 1, 0)).GetInverse())
    camera.CreateFocalLengthAttr(40)
    camera.CreateVerticalApertureAttr(24)
    camera.CreateHorizontalApertureAttr(24 * width / height)
    camera.CreateClippingRangeAttr(Gf.Vec2f(.1, 300))
    for name, pos, target, color, intensity, size in [
        ("Key", (-8, 22, 13), (0, 10, 0), (0.8, .91, 1), 16000, (8, 10)),
        ("Warm", (10, 10, 8), (0, 8, 0), (1, .8, .65), 9000, (5, 14)),
        ("Rim", (-7, 13, 1), (0, 10, 0), (.24, .65, 1), 16000, (3, 16))]:
        light = UsdLux.RectLight.Define(stage, f"/World/Lights/{name}")
        light.CreateColorAttr(Gf.Vec3f(*color))
        light.CreateIntensityAttr(intensity)
        light.CreateWidthAttr(size[0]); light.CreateHeightAttr(size[1])
        light.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*pos), Gf.Vec3d(*target), Gf.Vec3d(0, 1, 0)).GetInverse())
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Ambient")
    dome.CreateColorAttr(Gf.Vec3f(.25, .36, .5))
    dome.CreateIntensityAttr(140)
    sun = UsdLux.DistantLight.Define(stage, "/World/Lights/Softbox")
    sun.CreateColorAttr(Gf.Vec3f(.88, .95, 1))
    sun.CreateIntensityAttr(500)
    sun.CreateAngleAttr(18)
    sun.AddRotateXYZOp().Set(Gf.Vec3f(-18, -25, 0))
    product = UsdRender.Product.Define(stage, "/Render/Game")
    product.CreateCameraRel().SetTargets([camera.GetPath()])
    product.CreateResolutionAttr(Gf.Vec2i(width, height))
    product.GetPrim().SetMetadata("apiSchemas", Sdf.TokenListOp.CreateExplicit(["OmniRtxDebugSettingsAPI_1", "OmniRtxPostBloomPhysicalAPI_1"]))
    product.GetPrim().CreateAttribute("omni:rtx:rendermode", Sdf.ValueTypeNames.Token).Set("RealTimePathTracing")
    product.GetPrim().CreateAttribute("omni:rtx:rtpt:maxBounces", Sdf.ValueTypeNames.UInt).Set(3)
    product.GetPrim().CreateAttribute("omni:rtx:post:bloom:enabled", Sdf.ValueTypeNames.Bool).Set(True)
    product.GetPrim().CreateAttribute("omni:rtx:post:bloom:scale", Sdf.ValueTypeNames.Float).Set(.08)
    product.GetPrim().CreateAttribute("omni:rtx:post:bloom:cutoff", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(.9, .9, .9))
    product.GetPrim().CreateAttribute("omni:rtx:post:bloom:apertureShapeCircular", Sdf.ValueTypeNames.Bool).Set(True)
    var = UsdRender.Var.Define(stage, "/Render/Game/LdrColor")
    var.CreateSourceNameAttr("LdrColor")
    product.CreateOrderedVarsRel().SetTargets([var.GetPath()])
    stage.GetRootLayer().Save()
    return ASSETS / "board.usda"


if __name__ == "__main__":
    print(create_scene())
