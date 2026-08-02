#!/usr/bin/env python3
"""PPH 3D 可视化的 VTK 几何构建器（不依赖 Qt，可离屏测试）。

把仓库已有解析结果转换为 ``vtkPolyData`` + actor：

- :func:`mdl_mesh` — ``MdlModel`` 面片几何（按 frid / csid 着色）；
- :func:`oct_leaves` — ``OctModel`` 叶子包围盒（按深度着色，可限深/限量）；
- :func:`gph_boundary_mesh` / :func:`gph_faces_mesh` — GPH 面（边界或含内部）；
- :func:`plane_from_abcd` / :func:`cut_polydata` / :func:`clip_polydata` —
  体网格 / 几何剖切（对齐 scFLOWpre Cross Section View）。

统一通过 :func:`polydata_actor` 生成 actor；离屏渲染走
``vtkWin32OpenGLRenderWindow + SetOffScreenRendering(1)``。
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def _to_vtk(points: np.ndarray):
    from vtk.util.numpy_support import numpy_to_vtk

    return numpy_to_vtk(np.ascontiguousarray(points, dtype=np.float32))


def _add_polygons(pd, polys, cells, offsets, scalars=None):
    """把变长多边形（CSR 布局）写入 vtkPolyData。

    ``cells``：顶点索引连接表；``offsets``：每面起点（len+1）。
    ``scalars`` 为每面标量（写入 cell data "scalars"）。
    """
    import vtk

    if scalars is not None:
        cell_scalars = np.asarray(scalars)
        sarr = _to_vtk(cell_scalars.astype(np.float64).reshape(-1, 1))
        sarr.SetName("scalars")
        pd.GetCellData().SetScalars(sarr)
    for i in range(len(offsets) - 1):
        ids = cells[offsets[i]:offsets[i + 1]]
        if len(ids) < 3:
            continue
        poly = vtk.vtkPolygon()
        poly.GetPointIds().SetNumberOfIds(len(ids))
        for k, v in enumerate(ids):
            poly.GetPointIds().SetId(k, int(v))
        polys.InsertNextCell(poly)
    return polys


def mdl_mesh(model, color_by: str = "frid",
             max_faces: int = 500_000,
             face_mask: Optional[np.ndarray] = None) -> "vtkPolyData":
    """MdlModel → vtkPolyData（cell scalars = frid 或 csid 侧 id）。

    ``face_mask``：布尔数组（长度 n_faces），只保留选中的面
    （用于"仅显示选中体/区域/面"）。
    """
    import vtk

    if model.xyz.size == 0 or model.n_faces == 0:
        return vtk.vtkPolyData()
    pd = vtk.vtkPolyData()
    pd.SetPoints(vtk.vtkPoints())
    pd.GetPoints().SetData(_to_vtk(model.xyz))
    polys = vtk.vtkCellArray()
    n = min(model.n_faces, max_faces)
    if face_mask is not None:
        idx = np.flatnonzero(np.asarray(face_mask)[: model.n_faces])
        if idx.size > max_faces:
            idx = idx[:max_faces]
        if idx.size == 0:
            return pd
        n = idx.size
        offsets = np.concatenate(
            [[0], np.cumsum(model.npe[idx])]).astype(np.int64)
        conn = np.concatenate([
            model.conn[model.face_offsets[i]:model.face_offsets[i + 1]]
            for i in idx])
        if color_by == "csid":
            _, b2 = model.csid
            scalars = b2[idx].astype(np.float64) if b2.size else None
        else:
            scalars = model.frid[idx].astype(np.float64)
        _add_polygons(pd, polys, conn, offsets,
                      scalars=scalars if scalars is not None
                      else np.zeros(n, dtype=np.float64))
        pd.SetPolys(polys)
        pd.GetCellData().SetActiveScalars("scalars")
        return pd
    if color_by == "csid":
        _, b2 = model.csid
        scalars = b2[:n].astype(np.float64) if b2.size else None
    else:
        scalars = model.frid[:n].astype(np.float64)
    if scalars is None:
        scalars = np.zeros(n, dtype=np.float64)
    _add_polygons(pd, polys, model.conn[: int(model.face_offsets[n])],
                  model.face_offsets[: n + 1], scalars=scalars)
    pd.SetPolys(polys)
    pd.GetCellData().SetActiveScalars("scalars")
    return pd


def oct_leaves(oct_model, max_leaves: int = 50_000,
               max_depth: Optional[int] = None) -> "vtkPolyData":
    """OctModel 叶子包围盒 → vtkPolyData（cell scalars = 深度）。

    叶子过多时按深度优先截断（先保留最深层，超出 ``max_leaves`` 停止）。
    """
    import vtk

    pd = vtk.vtkPolyData()
    pd.SetPoints(vtk.vtkPoints())
    polys = vtk.vtkCellArray()
    pts = vtk.vtkPoints()
    pts.SetDataTypeToFloat()
    boxes: list[tuple] = []
    count = 0
    for (mn, mx, depth) in oct_model.iter_leaves():
        if max_depth is not None and depth > max_depth:
            continue
        boxes.append((mn, mx, depth))
        count += 1
        if count >= max_leaves:
            break
    if not boxes:
        return pd
    npts = len(boxes) * 8
    points = np.empty((npts, 3), dtype=np.float32)
    for i, (mn, mx, depth) in enumerate(boxes):
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        base = i * 8
        points[base] = (x0, y0, z0)
        points[base + 1] = (x1, y0, z0)
        points[base + 2] = (x1, y1, z0)
        points[base + 3] = (x0, y1, z0)
        points[base + 4] = (x0, y0, z1)
        points[base + 5] = (x1, y0, z1)
        points[base + 6] = (x1, y1, z1)
        points[base + 7] = (x0, y1, z1)
    pts.SetData(_to_vtk(points))
    pd.SetPoints(pts)
    quads = [
        (0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    for i in range(len(boxes)):
        base = i * 8
        for q in quads:
            quad = vtk.vtkQuad()
            for k, v in enumerate(q):
                quad.GetPointIds().SetId(k, base + v)
            polys.InsertNextCell(quad)
    pd.SetPolys(polys)
    sc = np.empty(len(boxes), dtype=np.float64)
    for i, (_, _, d) in enumerate(boxes):
        sc[i] = d
    sarr = _to_vtk(sc.reshape(-1, 1))
    sarr.SetName("scalars")
    pd.GetCellData().SetScalars(sarr)
    return pd


def gph_boundary_mesh(mesh: dict, max_faces: int = 200_000) -> "vtkPolyData":
    """gphstats.parse_mesh → 边界面 vtkPolyData（cell scalars = owner）。"""
    return gph_faces_mesh(mesh, max_faces=max_faces, boundary_only=True)


def gph_faces_mesh(mesh: dict, max_faces: int = 200_000,
                   boundary_only: bool = False,
                   face_scalars: Optional[np.ndarray] = None) -> "vtkPolyData":
    """GPH 面 → vtkPolyData。

    ``boundary_only``：仅边界面；否则含内部面（供体网格剖切）。
    ``face_scalars``：每面标量（如闭体 cvol）；缺省用 owner。
    """
    import vtk

    pd = vtk.vtkPolyData()
    if not mesh or mesh["vertices"].size == 0:
        return pd
    pd.SetPoints(vtk.vtkPoints())
    pd.GetPoints().SetData(_to_vtk(mesh["vertices"]))
    polys = vtk.vtkCellArray()
    if boundary_only:
        mask = mesh["boundary_mask"]
        idx = np.flatnonzero(mask)[:max_faces]
    else:
        n = min(int(mesh["n_faces"]), max_faces)
        idx = np.arange(n, dtype=np.int64)
    if idx.size == 0:
        return pd
    offsets = np.concatenate(
        [[0], np.cumsum(mesh["npe"][idx])]).astype(np.int64)
    conn = np.concatenate([
        mesh["conn"][mesh["face_offsets"][i]:mesh["face_offsets"][i + 1]]
        for i in idx])
    if face_scalars is not None:
        scalars = np.asarray(face_scalars)[idx].astype(np.float64)
    else:
        scalars = mesh["owner"][idx].astype(np.float64)
    _add_polygons(pd, polys, conn, offsets, scalars=scalars)
    pd.SetPolys(polys)
    return pd


def plane_from_abcd(a: float, b: float, c: float, d: float):
    """Ax+By+Cz=D → vtkPlane（法向归一化，原点取平面上一点）。"""
    import vtk

    abc = np.array([a, b, c], dtype=np.float64)
    abc_norm = float(np.linalg.norm(abc))
    if abc_norm < 1e-12:
        abc = np.array([1.0, 0.0, 0.0])
        abc_norm = 1.0
    unit = abc / abc_norm
    origin = [0.0, 0.0, 0.0]
    axis = int(np.argmax(np.abs(abc)))
    if abs(abc[axis]) > 1e-12:
        origin[axis] = float(d) / float(abc[axis])
    plane = vtk.vtkPlane()
    plane.SetOrigin(*origin)
    plane.SetNormal(float(unit[0]), float(unit[1]), float(unit[2]))
    return plane


def plane_from_axis_frac(bounds, axis: str, frac: float):
    """包围盒轴向分数位置 → vtkPlane（法向为轴正方向）。"""
    import vtk

    axes = {"X": 0, "Y": 1, "Z": 2}
    ai = axes[axis.upper()]
    origin = [(bounds[0] + bounds[1]) * 0.5,
              (bounds[2] + bounds[3]) * 0.5,
              (bounds[4] + bounds[5]) * 0.5]
    lo, hi = bounds[ai * 2], bounds[ai * 2 + 1]
    origin[ai] = lo + float(frac) * (hi - lo)
    normal = [0.0, 0.0, 0.0]
    normal[ai] = 1.0
    plane = vtk.vtkPlane()
    plane.SetOrigin(*origin)
    plane.SetNormal(*normal)
    return plane


def cut_polydata(pd, plane) -> "vtkPolyData":
    """vtkCutter：剖切面与 polydata 相交（截面线/面）。"""
    import vtk

    cutter = vtk.vtkCutter()
    cutter.SetInputData(pd)
    cutter.SetCutFunction(plane)
    cutter.GenerateCutScalarsOff()
    cutter.Update()
    return cutter.GetOutput()


def clip_polydata(pd, plane, inside_out: bool = False) -> "vtkPolyData":
    """vtkClipPolyData：保留平面一侧（``inside_out`` 取反）。"""
    import vtk

    clip = vtk.vtkClipPolyData()
    clip.SetInputData(pd)
    clip.SetClipFunction(plane)
    clip.SetInsideOut(1 if inside_out else 0)
    clip.GenerateClippedOutputOff()
    clip.Update()
    return clip.GetOutput()


def preset_colors(n: int) -> list[tuple[float, float, float]]:
    """按索引生成可区分的 RGB 0..1 颜色。"""
    base = [
        (0.90, 0.30, 0.25), (0.25, 0.62, 0.90), (0.28, 0.82, 0.38),
        (0.95, 0.72, 0.15), (0.62, 0.35, 0.85), (0.10, 0.75, 0.75),
        (0.95, 0.48, 0.62), (0.55, 0.45, 0.35),
    ]
    out = []
    for i in range(max(n, 0)):
        out.append(base[i % len(base)])
    return out


def polydata_actor(pd, scalar_range: Optional[tuple[float, float]] = None,
                   opacity: float = 1.0, wireframe: bool = False,
                   color: Optional[tuple[float, float, float]] = None,
                   discrete: bool = False,
                   annotations: Optional[dict] = None) -> "vtkActor":
    """生成 vtkActor：有 cell scalars 时按彩虹 LUT 着色。"""
    import vtk

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    if pd.GetCellData().GetScalars() is not None:
        rng = scalar_range if scalar_range is not None else \
            pd.GetCellData().GetScalars().GetRange()
        lut = _make_lut(rng, discrete=discrete, annotations=annotations)
        mapper.SetLookupTable(lut)
        mapper.SetScalarRange(rng[0], rng[1])
        mapper.ScalarVisibilityOn()
    else:
        mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetOpacity(opacity)
    if color is not None:
        actor.GetProperty().SetColor(*color)
    if wireframe:
        actor.GetProperty().SetRepresentationToWireframe()
    return actor


def _make_lut(rng: tuple[float, float], discrete: bool = False,
              annotations: Optional[dict] = None) -> "vtkLookupTable":
    """分类 LUT（区域/深度等离散标量）或连续彩虹 LUT。"""
    import vtk

    lut = vtk.vtkLookupTable()
    if discrete:
        values = sorted({int(v) for v in annotations} if annotations
                        else range(int(rng[0]), int(rng[1]) + 1))
        lo, hi = min(values), max(values)
        if lo == hi:      # 单值区间（如 box frid 全 0）规范化，避免退化
            hi = lo + 1
        lut.SetNumberOfTableValues(len(values))
        lut.SetRange(lo, hi)
        colors = preset_colors(len(values))
        for i, v in enumerate(values):
            lut.SetTableValue(i, *colors[i], 1.0)
            if annotations and v in annotations:
                lut.SetAnnotation(v, annotations[v])
        lut.Build()
        return lut
    lut.SetHueRange(0.0, 0.9)
    lut.SetNumberOfTableValues(256)
    lut.SetRange(rng[0], rng[1])
    lut.Build()
    return lut


def edges_actor(pd, color: tuple[float, float, float] = (0.10, 0.10, 0.14),
                opacity: float = 0.65, line_width: float = 1.0) -> "vtkActor":
    """网格线叠加：vtkExtractEdges 提取多边形边，以暗色线条渲染。"""
    import vtk

    ext = vtk.vtkExtractEdges()
    ext.SetInputData(pd)
    ext.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(ext.GetOutputPort())
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetOpacity(opacity)
    actor.GetProperty().SetLineWidth(line_width)
    actor.GetProperty().SetAmbient(1.0)
    actor.GetProperty().SetDiffuse(0.0)
    return actor


def scalar_bar_actor(title: str, lut, num_labels: int = 5) -> "vtkScalarBarActor":
    """色标/图例条（放在视口右侧）。"""
    import vtk

    bar = vtk.vtkScalarBarActor()
    bar.SetTitle(title)
    bar.SetLookupTable(lut)
    bar.SetNumberOfLabels(num_labels)
    bar.SetMaximumWidthInPixels(90)
    bar.SetMaximumHeightInPixels(220)
    bar.SetTextPad(4)
    bar.GetLabelTextProperty().SetFontSize(10)
    bar.GetTitleTextProperty().SetFontSize(11)
    bar.GetTitleTextProperty().SetJustificationToCentered()
    bar.SetDrawAnnotations(True)
    bar.SetDrawFrame(True)
    bar.SetAnnotationTextScaling(False)
    bar.GetAnnotationTextProperty().SetFontSize(11)
    bar.GetAnnotationTextProperty().SetJustificationToCentered()
    return bar


def axes_actor(length: float = 1.0) -> "vtkAxesActor":
    """带 XYZ 标签的坐标轴（供方向指示器使用）。"""
    import vtk

    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(length, length, length)
    axes.SetShaftTypeToCylinder()
    axes.SetCylinderRadius(0.02 * length)
    axes.SetConeRadius(0.08 * length)
    axes.AxisLabelsOn()
    return axes


def orientation_marker_widget(interactor, size_frac: float = 0.16):
    """右上角坐标方向指示器（不参与相机包围盒）。"""
    import vtk

    widget = vtk.vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes_actor())
    widget.SetInteractor(interactor)
    widget.SetViewport(1.0 - size_frac, 1.0 - size_frac, 1.0, 1.0)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


def make_renderer(actors, background: tuple[float, float, float] = (0.92, 0.92, 0.93)):
    """组装 renderer（渐变背景 + 相机自动包围所有 actor）。"""
    import vtk

    ren = vtk.vtkRenderer()
    ren.SetBackground(*background)
    ren.SetBackground2(0.72, 0.78, 0.90)
    ren.GradientBackgroundOn()
    for a in actors:
        if a is not None:
            ren.AddActor(a)
    ren.ResetCamera()
    return ren


def render_offscreen(actors, size: tuple[int, int] = (640, 480)) -> bool:
    """离屏渲染冒烟测试：成功返回 True。"""
    import vtk
    from vtkmodules.vtkRenderingOpenGL2 import vtkWin32OpenGLRenderWindow

    ren = make_renderer(actors)
    rw = vtkWin32OpenGLRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(*size)
    rw.AddRenderer(ren)
    iren = vtk.vtkRenderWindowInteractor()
    iren.SetRenderWindow(rw)
    rw.Render()
    ok = int(rw.GetOffScreenRendering()) == 1
    iren.TerminateApp()
    rw.Finalize()
    return ok
