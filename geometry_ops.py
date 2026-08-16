#!/usr/bin/env python3
"""geometry_ops — 原生几何编辑算子（pskernel / Parasolid V37 直调）。

P0-2: facet→B-rep 管线 ``triangles_to_brep``（移植 cabdecoding
      cab_ps_ops.py M39，链路见 docs/pskernel_user_guide.md §3/§5）：
      PK_PLANE_create → PK_BCURVE_create → PK_SPCURVE_create →
      PK_SURF_make_sheet_trimmed → PK_BODY_sew_bodies →
      PK_FACE_make_solid_bodies。
P0-3: create / modify facade——
      create: block / cylinder / sphere（PK_BODY_create_solid_*）
      modify: translate / rotate / scale / reflect / boolean / delete_faces
      面向 GUI（CreateParts/ModifyParts）的 ``execute_create_parts`` /
      ``execute_modify_parts``，产出 TessPart + x_t bytes 供写回 PPH。

单位约定：GUI 草稿长度按工程 UNIT（默认 m）记录；本模块统一换算为
米（Parasolid 会话单位）后再调内核。
"""

from __future__ import annotations

from ctypes import (
    POINTER, Structure, byref, cast, c_double, c_int, c_ubyte, c_void_p,
    memset, sizeof,
)
from typing import Optional

import numpy as np

try:
    import ps_facet2_nodes as _ps
except Exception:  # pragma: no cover
    _ps = None

# ---------------------------------------------------------------------------
# 单位换算（xenv UNIT.MODEL_LENGTH_UNIT → 米）
# ---------------------------------------------------------------------------
UNIT_TO_M = {"mm": 1e-3, "cm": 1e-2, "m": 1.0, "in": 0.0254,
             "millimeter": 1e-3, "centimeter": 1e-2, "meter": 1.0,
             "inch": 0.0254}


def unit_factor(unit: Optional[str]) -> float:
    return UNIT_TO_M.get((unit or "m").strip().lower(), 1.0)


def available() -> bool:
    return _ps is not None and _ps.available()


def session():
    """共享 pskernel 会话（首次调用引导会话 + FRU，见 user_guide §1）。"""
    if not available():
        raise RuntimeError(
            "Cradle pskernel.dll not found; set CRADLE_PROGRAMS to "
            r"...\CradleCFD*\Programs_x64")
    return _ps._get_session()


# ---------------------------------------------------------------------------
# 网格工具
# ---------------------------------------------------------------------------
def mesh_volume_m3(points, triangles) -> float:
    """闭合网格体积（有符号四面体求和取绝对值）。"""
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    if tris.size == 0:
        return 0.0
    a = pts[tris[:, 0]]
    b = pts[tris[:, 1]]
    c = pts[tris[:, 2]]
    return float(abs(float(
        np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0))


# ---------------------------------------------------------------------------
# P0-2: triangles → B-rep solid（经典 PK 链，无需 Convergent Modeling）
# ---------------------------------------------------------------------------
PK_FACE_heal_cap_c = 18081


class _SheetPlaneSf(Structure):
    """PK_PLANE_sf_t：9 doubles（point, normal, x_axis）。"""
    _fields_ = [("data", c_double * 9)]


class _SheetBcurveSf(Structure):
    """PK_BCURVE_sf_t（PK_LOGICAL_t = unsigned char）。"""
    _fields_ = [
        ("degree", c_int),
        ("n_vertices", c_int),
        ("vertex_dim", c_int),
        ("is_rational", c_ubyte),
        ("vertex", POINTER(c_double)),
        ("form", c_int),
        ("n_knots", c_int),
        ("knot_mult", POINTER(c_int)),
        ("knot", POINTER(c_double)),
        ("knot_type", c_int),
        ("is_periodic", c_ubyte),
        ("is_closed", c_ubyte),
        ("self_intersecting", c_ubyte),
    ]


class _SheetSpcurveSf(Structure):
    _fields_ = [("surf", c_int), ("curve", c_int)]


class _SheetInterval(Structure):
    _fields_ = [("value", c_double * 2)]


class _SheetTrimData(Structure):
    """PK_SURF_trim_data_t。"""
    _fields_ = [
        ("n_spcurves", c_int),
        ("spcurves", POINTER(c_int)),
        ("intervals", POINTER(_SheetInterval)),
        ("trim_loop", POINTER(c_int)),
        ("trim_set", POINTER(c_int)),
    ]


class _SheetTrimOpts(Structure):
    """PK_SURF_make_sheet_trimmed_o_t。"""
    _fields_ = [
        ("o_t_version", c_int),
        ("check_wires", c_ubyte),
        ("check_self_int", c_ubyte),
        ("check_loops", c_ubyte),
        ("nominal_geom", c_ubyte),
    ]


class _SheetSewOpts(Structure):
    """PK_BODY_sew_bodies_o_t（宽松尾部 pad）。"""
    _fields_ = [
        ("o_t_version", c_int),
        ("set_global_tolerance", c_ubyte),
        ("allow_disjoint_result", c_ubyte),
        ("treat_as_manifold", c_ubyte),
        ("prefered_body_type", c_int),
        ("duplicate_removal", c_int),
        ("number_of_iterations", c_int),
        ("iteration_bounds", POINTER(c_double)),
        ("_pad", c_int * 8),
    ]


def _sheet_declare(pk) -> None:
    """sheet 构建原型声明（每内核句柄一次）。"""
    pk.PK_PLANE_create.restype = c_int
    pk.PK_PLANE_create.argtypes = [POINTER(_SheetPlaneSf), POINTER(c_int)]
    pk.PK_BCURVE_create.restype = c_int
    pk.PK_BCURVE_create.argtypes = [POINTER(_SheetBcurveSf), POINTER(c_int)]
    pk.PK_SPCURVE_create.restype = c_int
    pk.PK_SPCURVE_create.argtypes = [POINTER(_SheetSpcurveSf), POINTER(c_int)]
    pk.PK_SURF_make_sheet_trimmed.restype = c_int
    pk.PK_SURF_make_sheet_trimmed.argtypes = [
        c_int, POINTER(_SheetTrimData), c_double, POINTER(_SheetTrimOpts),
        POINTER(c_int), POINTER(c_int)]
    pk.PK_BODY_sew_bodies.restype = c_int
    pk.PK_BODY_sew_bodies.argtypes = [
        c_int, POINTER(c_int), c_double, POINTER(_SheetSewOpts),
        POINTER(c_int), POINTER(c_void_p), POINTER(c_int), POINTER(c_void_p),
        POINTER(c_int), POINTER(c_void_p)]
    pk.PK_BODY_ask_faces.restype = c_int
    pk.PK_BODY_ask_faces.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
    pk.PK_FACE_make_solid_bodies.restype = c_int
    pk.PK_FACE_make_solid_bodies.argtypes = [
        c_int, POINTER(c_int), c_int, c_ubyte, POINTER(c_int),
        POINTER(c_void_p), POINTER(c_void_p)]


def _triangle_sheet(pk, a, b, c, precision=1e-6) -> int:
    """三角形 (a, b, c)（米）→ 一张裁剪平面 sheet body。"""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    c = np.asarray(c, dtype=np.float64)
    n = np.cross(b - a, c - a)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        raise ValueError("degenerate triangle")
    n = n / nn
    xax = (b - a) / float(np.linalg.norm(b - a))
    yax = np.cross(n, xax)
    sf = _SheetPlaneSf()
    sf.data[0:3] = a
    sf.data[3:6] = n
    sf.data[6:9] = xax
    plane = c_int(0)
    rc = pk.PK_PLANE_create(byref(sf), byref(plane))
    if rc != 0:
        raise RuntimeError(f"PK_PLANE_create failed: {rc}")
    corners = [a, b, c]
    uvs = [np.array([(p - a) @ xax, (p - a) @ yax]) for p in corners]
    spcs = []
    for e in range(3):
        p0 = uvs[e]
        p1 = uvs[(e + 1) % 3]
        verts = (c_double * 4)(p0[0], p0[1], p1[0], p1[1])
        kmult = (c_int * 2)(2, 2)
        knots = (c_double * 2)(0.0, 1.0)
        bsf = _SheetBcurveSf()
        memset(byref(bsf), 0, sizeof(bsf))
        bsf.degree = 1
        bsf.n_vertices = 2
        bsf.vertex_dim = 2
        bsf.vertex = verts
        bsf.form = 1
        bsf.n_knots = 2
        bsf.knot_mult = kmult
        bsf.knot = knots
        crv = c_int(0)
        r2 = pk.PK_BCURVE_create(byref(bsf), byref(crv))
        if r2 != 0:
            raise RuntimeError(f"PK_BCURVE_create failed: {r2}")
        ssf = _SheetSpcurveSf(plane.value, crv.value)
        spc = c_int(0)
        r3 = pk.PK_SPCURVE_create(byref(ssf), byref(spc))
        if r3 != 0:
            raise RuntimeError(f"PK_SPCURVE_create failed: {r3}")
        spcs.append(spc.value)
    spc_arr = (c_int * 3)(*spcs)
    ivs = (_SheetInterval * 3)(_SheetInterval((0.0, 1.0)),
                               _SheetInterval((0.0, 1.0)),
                               _SheetInterval((0.0, 1.0)))
    loops = (c_int * 3)(0, 0, 0)
    sets = (c_int * 3)(0, 0, 0)
    td = _SheetTrimData(3, spc_arr, ivs, loops, sets)
    sopts = _SheetTrimOpts()
    memset(byref(sopts), 0, sizeof(sopts))
    sopts.o_t_version = 1
    body = c_int(0)
    state = c_int(0)
    r4 = pk.PK_SURF_make_sheet_trimmed(plane.value, byref(td), precision,
                                       byref(sopts), byref(body),
                                       byref(state))
    if r4 != 0:
        raise RuntimeError(f"PK_SURF_make_sheet_trimmed failed: {r4}")
    return body.value


def triangles_to_brep(points, triangles, gap: float = 1e-4) -> list:
    """三角网格（米）→ solid body tag 列表（P0-2 管线）。

    每三角形一张裁剪平面 sheet → ``PK_BODY_sew_bodies`` 缝合 →
    ``PK_FACE_make_solid_bodies`` 成实体；开放面片被 heal-cap 成的
    零体积实体将被剔除。内核拒绝输入时抛 RuntimeError。
    """
    if not available():
        raise RuntimeError("pskernel not available")
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    if tris.size == 0:
        return []
    sess = session()
    pk = sess.pk
    pk.PK_SESSION_set_check_arguments.restype = c_int
    pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
    pk.PK_SESSION_set_check_arguments(0)
    _sheet_declare(pk)
    sheet_bodies = []
    for tri in tris:
        try:
            tag = _triangle_sheet(pk, pts[tri[0]], pts[tri[1]], pts[tri[2]])
            sheet_bodies.append(int(tag))
        except RuntimeError:
            continue  # 退化三角形等
    if not sheet_bodies:
        return []
    solids = []
    if len(sheet_bodies) == 1:
        sewn = sheet_bodies
    else:
        arr = (c_int * len(sheet_bodies))(*sheet_bodies)
        sewo = _SheetSewOpts()
        memset(byref(sewo), 0, sizeof(sewo))
        sewo.o_t_version = 1
        sewo.treat_as_manifold = 1
        n_sewn = c_int(0)
        sewn_p = c_void_p()
        n_un = c_int(0)
        un_p = c_void_p()
        n_prob = c_int(0)
        prob_p = c_void_p()
        r5 = pk.PK_BODY_sew_bodies(len(sheet_bodies), arr, gap,
                                   byref(sewo), byref(n_sewn), byref(sewn_p),
                                   byref(n_un), byref(un_p), byref(n_prob),
                                   byref(prob_p))
        if r5 != 0:
            raise RuntimeError(f"PK_BODY_sew_bodies failed: {r5}")
        if n_sewn.value == 0:
            return []
        sewn = [int(t) for t in
                cast(sewn_p, POINTER(c_int * n_sewn.value)).contents]
    for body_tag in sewn:
        nf = c_int(0)
        faces_p = c_void_p()
        rc = pk.PK_BODY_ask_faces(int(body_tag), byref(nf), byref(faces_p))
        if rc != 0 or nf.value == 0:
            continue
        farr = cast(faces_p, POINTER(c_int * nf.value)).contents
        n_sol = c_int(0)
        sols_p = c_void_p()
        checks_p = c_void_p()
        r6 = pk.PK_FACE_make_solid_bodies(
            nf.value, farr, PK_FACE_heal_cap_c, 0, byref(n_sol),
            byref(sols_p), byref(checks_p))
        if r6 != 0 or n_sol.value == 0:
            continue
        for tag in cast(sols_p, POINTER(c_int * n_sol.value)).contents:
            # 开放 sheet 被 cap 成零体积实体 → 剔除
            part = tessellate_body(int(tag))
            if part is not None and len(part.triangles):
                if mesh_volume_m3(part.points, part.triangles) < 1e-15:
                    continue
            solids.append(int(tag))
    return solids


# ---------------------------------------------------------------------------
# P0-3: create / modify 算子（薄封装 ps_facet2_nodes 会话方法）
# ---------------------------------------------------------------------------
def create_block(size_m, origin_m=(0.0, 0.0, 0.0)) -> int:
    return session().create_solid_block(size_m, origin_m)


def create_cylinder(radius_m: float, height_m: float,
                    bottom_m=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> int:
    return session().create_solid_cyl(radius_m, height_m, bottom_m, direction)


def create_sphere(radius_m: float, centre_m=(0.0, 0.0, 0.0)) -> int:
    return session().create_solid_sphere(radius_m, centre_m)


def translate_body(body: int, dx: float = 0.0, dy: float = 0.0,
                   dz: float = 0.0) -> None:
    session().transform_body(body, dx, dy, dz)


def rotate_body(body: int, *, axis=(0.0, 0.0, 1.0), angle_deg: float = 0.0,
                position=(0.0, 0.0, 0.0)) -> None:
    session().rotate_body(body, axis=axis, angle_deg=angle_deg,
                          position=position)


def scale_body(body: int, *, scale: float = 1.0,
               centre=(0.0, 0.0, 0.0)) -> None:
    if abs(float(scale) - 1.0) < 1e-15:
        return
    session().scale_body(body, scale=scale, centre=centre)


def reflect_body(body: int, *, normal=(1.0, 0.0, 0.0),
                 position=(0.0, 0.0, 0.0)) -> None:
    session().reflect_body(body, normal=normal, position=position)


def boolean(target: int, tools: list, op: str) -> list:
    """unite / subtract / intersect；tool bodies 被内核消耗。"""
    return session().body_boolean(target, tools, op)


def delete_faces(face_tags: list, *, heal: str = "cap") -> None:
    session().face_delete(face_tags, heal=heal)


def tessellate_body(tag: int, name: str = "") -> Optional[_ps.TessPart]:
    """剖分 body：adaptive → facet_2 → GO 兜底（与 cad_import 一致）。"""
    sess = session()
    part = None
    try:
        part = sess.facet_body_adaptive(tag)
    except Exception:
        part = None
    if part is None or not getattr(part, "triangles", np.empty(0)).size:
        try:
            part = sess.facet_body(tag)
        except Exception:
            part = None
    if part is None or not part.triangles.size:
        try:
            part = sess.facet_go(tag)
        except Exception:
            part = None
    if part is None or not part.triangles.size:
        return None
    if name:
        part.name = name
    return part


def transmit_body(tag: int) -> bytes:
    """body → x_t 文本 bytes（写回 PPH 工程成员，见 user_guide §2）。"""
    return session().transmit_part(tag)


# ---------------------------------------------------------------------------
# GUI 执行入口：CreateParts / ModifyParts 草稿 → 原生几何
# ---------------------------------------------------------------------------
def execute_create_parts(draft: dict, unit: Optional[str] = "m") -> dict:
    """CreateParts 草稿 → {name, tag, tess, xt, fluid}（单位→米）。

    支持 Cuboid / Cylinder / Sphere；Rectangle（sheet 件）暂走 VBS 宿主
    路径，本函数抛 NotImplementedError。
    """
    shape = draft.get("shape") or "Cuboid"
    k = unit_factor(unit)
    name = (draft.get("name") or shape).strip()
    sess = session()

    if shape == "Cuboid":
        pos = tuple(float(v) for v in draft.get("position") or (0, 0, 0))
        size = tuple(float(v) for v in draft.get("size") or (1, 1, 1))
        if any(s <= 0 for s in size):
            raise ValueError(f"Cuboid size must be positive: {size}")
        centre = tuple((pos[i] + size[i] * 0.5) * k for i in range(3))
        size_m = tuple(s * k for s in size)
        tag = sess.create_solid_block(size_m, centre)
    elif shape == "Cylinder":
        bot = tuple(float(v) for v in draft.get("bottom") or (0, 0, 0))
        h = float(draft.get("height") or 0.0)
        r = float(draft.get("radius") or 0.0)
        if h <= 0 or r <= 0:
            raise ValueError(f"Cylinder radius/height must be positive: {r}, {h}")
        direction = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0),
                     "Z": (0.0, 0.0, 1.0)}.get(
            str(draft.get("direction") or "Z").strip().upper()[:1],
            (0.0, 0.0, 1.0))
        tag = sess.create_solid_cyl(r * k, h * k, tuple(v * k for v in bot),
                                    direction)
    elif shape == "Sphere":
        c = tuple(float(v) for v in draft.get("center") or (0, 0, 0))
        r = float(draft.get("radius") or 0.0)
        if r <= 0:
            raise ValueError(f"Sphere radius must be positive: {r}")
        tag = sess.create_solid_sphere(r * k, tuple(v * k for v in c))
    else:
        raise NotImplementedError(
            f"shape {shape!r} 暂不支持原生创建（请走 scFLOWpre 宿主 VBS）")

    tess = tessellate_body(tag, name)
    if tess is None:
        raise RuntimeError(f"body {tag} tessellation failed")
    return {"name": name, "tag": tag, "tess": tess,
            "xt": transmit_body(tag), "fluid": bool(draft.get("fluid"))}


# ModifyParts 原生支持的 op → (kind, 参数键)
_MODIFY_NATIVE = {
    "unite_solids": ("boolean", "unite"),
    "remove_solid_overlap": ("boolean", "subtract"),
    "translate_copy": ("translate", None),
    "rotate_copy": ("rotate", None),
    "scale_copy": ("scale", None),
}


def execute_modify_parts(draft: dict, tag_by_name: dict,
                         unit: Optional[str] = "m") -> dict:
    """ModifyParts 草稿 → 原生执行（MVP：布尔 + 变换类）。

    ``tag_by_name``：part 名 → body tag（GUI 从已加载 CAD meshes 取）。
    返回 ``{op, changed: [name], removed: [name], added: [tess…],
    notes: [str]}``；不支持的 op 抛 NotImplementedError（GUI 回退 VBS）。
    注意：PK_BODY_copy 未导出，*_copy 类操作按“就地变换”执行并在
    notes 中注明（非复制语义）。
    """
    op = draft.get("op") or ""
    spec = _MODIFY_NATIVE.get(op)
    if spec is None:
        raise NotImplementedError(
            f"modify op {op!r} 暂不支持原生执行（请走 scFLOWpre 宿主 VBS）")
    kind, arg = spec
    parts = [p for p in (draft.get("parts") or [])
             if p in tag_by_name]
    missing = [p for p in (draft.get("parts") or [])
               if p not in tag_by_name]
    params = draft.get("params") or {}
    k = unit_factor(unit)
    notes: list[str] = []
    if missing:
        notes.append("无 body tag（未加载 CAD）: " + ", ".join(missing))
    if not parts:
        raise RuntimeError("没有可操作的已加载 body（先 Import CAD 或原生创建）")

    out = {"op": op, "changed": [], "removed": [], "added": [], "notes": notes}

    if kind == "boolean":
        if len(parts) < 2:
            raise RuntimeError(f"{op} 需要至少 2 个 part")
        target = tag_by_name[parts[0]]
        tools = [tag_by_name[p] for p in parts[1:]]
        results = boolean(target, tools, arg)
        if not results:
            raise RuntimeError(f"PK_BODY_boolean_2 produced no bodies")
        tess_list = []
        for i, tag in enumerate(results):
            nm = parts[0] if len(results) == 1 else f"{parts[0]}_{i + 1}"
            tess = tessellate_body(tag, nm)
            if tess is None:
                continue
            tess_list.append(tess)
            out["added"].append({"name": nm, "tag": tag, "tess": tess,
                                 "xt": transmit_body(tag)})
        if not tess_list:
            raise RuntimeError("boolean 结果剖分失败")
        # target + tools 均被内核消耗 → 全部计入 removed，由 added 替换
        out["changed"] = []
        out["removed"] = parts
        return out

    # 变换类（就地）
    for p in parts:
        tag = tag_by_name[p]
        if kind == "translate":
            d = tuple(float(v) for v in (params.get("distance") or (0, 0, 0)))
            translate_body(tag, *[v * k for v in d])
        elif kind == "rotate":
            c = tuple(float(v) * k for v in (params.get("center") or (0, 0, 0)))
            ax = str(params.get("axis") or "Z direction").strip().upper()[:1]
            axis = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0),
                    "Z": (0.0, 0.0, 1.0)}.get(ax, (0.0, 0.0, 1.0))
            rotate_body(tag, axis=axis,
                        angle_deg=float(params.get("angle") or 0.0),
                        position=c)
        elif kind == "scale":
            s = tuple(float(v) for v in (params.get("scale") or (1, 1, 1)))
            if abs(s[0] - s[1]) > 1e-12 or abs(s[1] - s[2]) > 1e-12:
                raise NotImplementedError(
                    "非等比缩放需 PK_TRANSF_create_unequal_scale（本内核"
                    "未导出），请走 scFLOWpre 宿主")
            c = tuple(float(v) * k for v in (params.get("center") or (0, 0, 0)))
            scale_body(tag, scale=s[0], centre=c)
        out["changed"].append(p)
    if op.endswith("_copy"):
        notes.append(f"{op}：PK_BODY_copy 未导出，已按就地变换执行（非复制）")
    return out
