#!/usr/bin/env python3
"""CAD / Parasolid ``.x_t`` 导入（对齐 cabdecoding：pskernel facet_2）。

将 Cradle ``pskernel.dll`` 的 ``PK_PART_receive`` + ``PK_TOPOL_facet_2``
剖分结果转为可显示的 ``TessPart`` 列表，供 GUI Draw Window 预览。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import ps_facet2_nodes as _ps_facet2
except Exception:  # pragma: no cover
    _ps_facet2 = None

try:
    import ps_tessellate as _ps_go
except Exception:  # pragma: no cover
    _ps_go = None


XT_SUFFIXES = {".x_t", ".xmt_txt"}


@dataclass
class ImportedBody:
    """单个导入体：显示网格 + PK tag。"""

    name: str
    tag: int
    tess: object  # ps_facet2_nodes.TessPart


def offline_available() -> bool:
    """**离线** CAD 能力：Cradle 安装内的 pskernel.dll 在位。

    只依赖安装目录，**不需要宿主进程、也不需要许可**（2026-09-13 实测：
    许可地址置死后仍可 PK_PART_receive + 剖分）。X_T 剖分 / 原生几何造型
    （geometry_ops）走这条判据。
    """
    return _ps_facet2 is not None and _ps_facet2.available()


def host_available() -> dict:
    """**宿主** CAD 能力：STEP / CATIA 等格式经宿主 OpenCadFile 转换时需要。

    返回 dict(ok, installed, running, gui_ready, hint, error)；探测出错时降级为
    ok=False + error 文本，**不抛异常**（GUI 灰显判断必须无副作用）。

    与 offline_available 的区别正是审计 §13.1 的边界：只装 Cradle 但无许可/
    未启动宿主时，离线能力可用而宿主导入不可用——旧代码只查 pskernel 在位，
    会让 GUI 误报"CAD 可用"。
    """
    out: dict = {"ok": False, "installed": False, "running": False,
                 "gui_ready": False, "hint": "", "error": None}
    try:
        from automation import host_pipeline
        st = host_pipeline.host_status()
        out["installed"] = bool(st.get("installed"))
        out["running"] = bool(st.get("running_pids"))
        out["gui_ready"] = bool(st.get("gui_ready"))
        out["hint"] = st.get("hint", "") or ""
        out["ok"] = out["installed"] and out["running"]
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def available() -> bool:
    """向后兼容旧名 —— 等价于 offline_available。"""
    return offline_available()


def import_xt_bytes(raw: bytes, *, adaptive: bool = True,
                    default_name: str = "Part",
                    **kw) -> list[ImportedBody]:
    """Receive 文本 ``.x_t`` 并剖分每个 body。"""
    if not available():
        raise RuntimeError(
            "Cradle pskernel.dll not found; set CRADLE_PROGRAMS to "
            r"...\CradleCFD*\Programs_x64")
    sess = _ps_facet2._get_session()
    tags = sess.receive_xt(raw)
    out: list[ImportedBody] = []
    for tag in tags:
        part = None
        if adaptive:
            try:
                part = sess.facet_body_adaptive(tag, **kw)
            except Exception:
                part = None
        if part is None or not getattr(part, "triangles", np.empty(0)).size:
            try:
                part = sess.facet_body(tag, **kw)
            except Exception:
                part = None
        if part is None or not part.triangles.size:
            # GO fallback（与 cab_gui._tessellate_members 一致）
            try:
                part = sess.facet_go(tag, **{
                    k: v for k, v in kw.items()
                    if k in ("facet_tol", "facet_angle_deg")})
            except Exception:
                part = None
        if part is None or not part.triangles.size:
            continue
        try:
            part.vertices = sess.body_vertices(tag)
        except Exception:
            part.vertices = None
        out.append(ImportedBody(
            name=(part.name or "").strip() or default_name,
            tag=int(tag), tess=part))
    if not out and _ps_go is not None and _ps_go.available():
        # 独立 GO 模块回退（仅当 facet2 路径未产出网格时）
        for part in _ps_go.tessellate_xt(raw, **{
                k: v for k, v in kw.items()
                if k in ("facet_tol", "facet_angle_deg")}):
            if not part.triangles.size:
                continue
            out.append(ImportedBody(
                name=(part.name or "").strip() or default_name,
                tag=int(getattr(part, "tag", 0)), tess=part))
    # 无意义 PK 名（单字母等）→ 文件 stem / stem_N
    usable = 0
    for i, body in enumerate(out):
        name = (body.name or "").strip()
        if len(name) < 2 or (name.isalpha() and len(name) <= 2):
            usable += 1
            name = (default_name if len(out) == 1
                    else f"{default_name}_{usable}")
            body.name = name
            body.tess.name = name
    return out


def import_xt_file(path: str | Path, **kw) -> list[ImportedBody]:
    path = Path(path)
    return import_xt_bytes(
        path.read_bytes(), default_name=path.stem, **kw)


def import_file(path: str | Path, **kw) -> list[ImportedBody]:
    """按扩展名导入（当前支持 ``.x_t`` / ``.xmt_txt``）。"""
    path = Path(path)
    suf = path.suffix.lower()
    if suf in XT_SUFFIXES:
        return import_xt_file(path, **kw)
    raise ValueError(f"unsupported geometry format: {suf}")
