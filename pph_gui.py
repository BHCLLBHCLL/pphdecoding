#!/usr/bin/env python3
"""PPH 查看/修改 GUI —— 对齐 scFLOWpre 主界面排版（PyQt5 + VTK）。

布局参照 Cradle scFLOWpre（Manuals/scFLOW/HTML/Pre_eng）：

  Menu: File / Edit / Select / View / Condition / Execute / Option / Help
  Toolbars + 主工作区：
    Navigation | Tree + Property | Draw + Message

PPH 只读/轻量编辑能力映射到对应菜单与导航项。Prepare Parts /
Build Analysis Model 点击后弹出子窗口（对齐 scFLOWpre 对话框），
绑定 xenv/xml/prp；网格生成等执行步骤需在 scFLOWpre 中完成。

用法：``python pph_gui.py [项目.pph]``。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import (
    QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath,
    QPalette, QPen, QPixmap, QPolygon,
)
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QRubberBand, QSizePolicy, QSlider,
    QSplitter, QStackedWidget, QTabWidget, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

import nav_panels
import option_dialogs
import pph_parser
import pph_vtk
import pphwriter
import pphxml

# scFLOWpre / STpre Draw Window 视图键（Pre_eng Keyboard）：
#   X → YZ（+X）, Y → XZ（+Y）, Z → XY（+Z）；Shift+X/Y/Z 为对侧
#   F → Fit（仅 Draw 聚焦）；Ctrl+F 为窗口级 Fit
_VIEW_KEY_TO_PLANE = {"x": "yz", "y": "xz", "z": "xy"}


def plane_view_camera(plane: str, *, negative: bool = False
                      ) -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """正交平面视图的 camera (position, view_up)。"""
    sign = -1.0 if negative else 1.0
    p = (plane or "").lower()
    if p == "xy":
        return (0.0, 0.0, sign), (0.0, 1.0, 0.0)
    if p == "xz":
        return (0.0, sign, 0.0), (0.0, 0.0, 1.0)
    return (sign, 0.0, 0.0), (0.0, 0.0, 1.0)


def _voxel_params_dialog(parent) -> Optional["object"]:
    """自研 Voxel mesher 参数对话框（对齐 scFLOW Voxel 控制面）。"""
    from PyQt5.QtWidgets import (
        QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
        QSpinBox,
    )

    dlg = QDialog(parent)
    dlg.setWindowTitle("Voxel Fitting Mesh (Self Build)")
    form = QFormLayout(dlg)
    sp_init = QSpinBox()
    sp_init.setRange(1, 6)
    sp_init.setValue(2)
    sp_max = QSpinBox()
    sp_max.setRange(1, 7)
    sp_max.setValue(4)
    sp_cells = QSpinBox()
    sp_cells.setRange(10_000, 5_000_000)
    sp_cells.setSingleStep(50_000)
    sp_cells.setValue(500_000)
    chk_rough = QCheckBox("Use rough poly when voxel meshing")
    chk_rough.setChecked(True)
    chk_fit = QCheckBox("Fit block mesh to parts surface")
    chk_fit.setChecked(False)
    sp_ratio = QDoubleSpinBox()
    sp_ratio.setRange(0.05, 2.0)
    sp_ratio.setSingleStep(0.05)
    sp_ratio.setValue(0.5)
    sp_ratio.setDecimals(2)
    form.addRow("Initial octree depth (/axis):", sp_init)
    form.addRow("Max adaptive depth:", sp_max)
    form.addRow("Max cells:", sp_cells)
    form.addRow("", chk_rough)
    form.addRow("", chk_fit)
    form.addRow("Max fitting distance ratio:", sp_ratio)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    form.addRow(buttons)
    if dlg.exec_() != QDialog.Accepted:
        return None
    import voxmesh
    return voxmesh.VoxelMeshParams(
        initial_depth=sp_init.value(),
        max_depth=sp_max.value(),
        max_cells=sp_cells.value(),
        rough_poly=chk_rough.isChecked(),
        fit_to_surface=chk_fit.isChecked(),
        max_fit_distance_ratio=sp_ratio.value(),
    )


def _poly_params_dialog(parent) -> Optional["object"]:
    """自研多面体 mesher 参数对话框（seed + Lloyd/近壁层/特征保形）。"""
    from PyQt5.QtWidgets import (
        QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
        QGroupBox, QSpinBox,
    )

    dlg = QDialog(parent)
    dlg.setWindowTitle("Polyhedral Mesh (Self Build)")
    form = QFormLayout(dlg)
    sp_div = QSpinBox()
    sp_div.setRange(3, 40)
    sp_div.setValue(12)
    sp_stride = QSpinBox()
    sp_stride.setRange(1, 64)
    sp_stride.setValue(8)
    sp_cells = QSpinBox()
    sp_cells.setRange(1_000, 2_000_000)
    sp_cells.setSingleStep(50_000)
    sp_cells.setValue(200_000)
    chk_clip = QCheckBox("Clip boundary cells to parts surface")
    chk_clip.setChecked(True)
    form.addRow("Interior lattice divisions (/axis):", sp_div)
    form.addRow("Surface seed stride:", sp_stride)
    form.addRow("Max cells:", sp_cells)
    form.addRow("", chk_clip)

    gb_smooth = QGroupBox("Lloyd smoothing / near-wall layers")
    fs = QFormLayout(gb_smooth)
    sp_lloyd = QSpinBox()
    sp_lloyd.setRange(0, 20)
    sp_lloyd.setValue(2)
    sp_layers = QSpinBox()
    sp_layers.setRange(0, 8)
    sp_layers.setValue(0)
    sp_first = QDoubleSpinBox()
    sp_first.setRange(0.05, 1.0)
    sp_first.setSingleStep(0.05)
    sp_first.setValue(0.25)
    sp_growth = QDoubleSpinBox()
    sp_growth.setRange(1.05, 3.0)
    sp_growth.setSingleStep(0.1)
    sp_growth.setValue(1.4)
    fs.addRow("Lloyd iterations:", sp_lloyd)
    fs.addRow("Near-wall layers:", sp_layers)
    fs.addRow("First layer ratio:", sp_first)
    fs.addRow("Layer growth rate:", sp_growth)
    form.addRow(gb_smooth)

    chk_feat = QCheckBox("Preserve sharp features (VoroCrust-style seed pairs)")
    chk_feat.setChecked(True)
    sp_fang = QDoubleSpinBox()
    sp_fang.setRange(5.0, 120.0)
    sp_fang.setSingleStep(5.0)
    sp_fang.setValue(30.0)
    sp_fang.setSuffix(" deg")
    form.addRow("", chk_feat)
    form.addRow("Feature angle:", sp_fang)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    form.addRow(buttons)
    if dlg.exec_() != QDialog.Accepted:
        return None
    import polymesh
    return polymesh.PolyMeshParams(
        divisions=sp_div.value(),
        surface_stride=sp_stride.value(),
        max_cells=sp_cells.value(),
        clip_to_surface=chk_clip.isChecked(),
        lloyd_iterations=sp_lloyd.value(),
        n_wall_layers=sp_layers.value(),
        first_layer_ratio=sp_first.value(),
        layer_growth=sp_growth.value(),
        feature_preserve=chk_feat.isChecked(),
        feature_angle_deg=sp_fang.value(),
    )


def view_key_action(keysym: str, *, shift: bool = False
                    ) -> Optional[tuple]:
    """Draw Window 按键 → ``('plane', name, negative)`` 或 ``('fit',)``。"""
    sym = (keysym or "").lower()
    if sym == "f" and not shift:
        return ("fit",)
    plane = _VIEW_KEY_TO_PLANE.get(sym)
    if plane is not None:
        return ("plane", plane, bool(shift))
    return None

try:  # VTK 工厂注册：交互样式 / OpenGL2 后端
    import vtkmodules.vtkInteractionStyle  # noqa: F401
    import vtkmodules.vtkRenderingOpenGL2   # noqa: F401
except Exception:  # noqa: BLE001 - 离屏/无显示环境下不阻塞导入
    pass


# GPH 边界面若按文件序截断会整块缺壁（酷似剖切）；上限需覆盖常见大模型
DEFAULT_CAPS = {"mdl": 300_000, "oct": 40_000, "gph": 500_000}
DEFAULT_CAPS["ridge"] = DEFAULT_CAPS["mdl"]


@dataclass
class LayerRender:
    """一个 3D 图层的渲染结果。"""

    actor: object
    title: str
    annotations: Optional[dict] = None
    edges: bool = False  # 是否叠加网格线（仅体网格 GPH 默认开启）
    legend_entries: Optional[list[tuple[str, tuple]]] = None  # (标签, RGB)


def _member_group(name: str) -> str:
    """由成员名推导网格组名（如 meshinggroup1_part.mdl → meshinggroup1）。"""
    base = name.lower()
    for suffix in ("_part.mdl", "_ridge.mdl", ".gph", ".oct", ".mdl"):
        if base.endswith(suffix):
            return name[: -len(suffix)]
    return ""


def _fmt_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GiB"


def _closed_volume_id(text: str) -> Optional[int]:
    """``ClosedVolume3`` / ``MeshClosedVolume3`` → 3。"""
    import re
    m = re.match(r"(?:Mesh)?ClosedVolume(\d+)$", (text or "").strip(), re.I)
    return int(m.group(1)) if m else None


def _mesh_closed_volume_label(text: str) -> str:
    """XML ``ClosedVolume1`` → 树节点 ``MeshClosedVolume1``（对齐 Pre）。"""
    cid = _closed_volume_id(text)
    if cid is not None:
        return f"MeshClosedVolume{cid}"
    return text or "MeshClosedVolume"


def _extract_part_tree_meta(mx) -> tuple[dict, dict]:
    """从 main.xml 提取 Part Tree 用的 regions_meta 与按组零件列表。"""
    regions_meta: dict[str, list] = {
        "fluid": [], "face": [], "volume": [], "numerical": [],
        "cross_section": [], "special_face": [],
    }
    regs = mx.section("regions")
    if regs is not None:
        for fr in (regs.find("fluid").findall("region")
                   if regs.find("fluid") is not None else []):
            name = (fr.findtext("name") or "").strip() or "FluidRegion"
            prop = (fr.findtext("property") or "").strip()
            sparts = [((s.text or "").strip())
                      for s in fr.findall("spart") if (s.text or "").strip()]
            label = f"{prop} ({name})" if prop else name
            regions_meta["fluid"].append({
                "name": name, "property": prop, "label": label,
                "sparts": ", ".join(sparts),
            })
        for cat in ("face", "volume", "numerical", "cross_section",
                    "special_face"):
            node = regs.find(cat)
            if node is None:
                continue
            for r in node.findall("region"):
                name = (r.findtext("name") or "").strip()
                if not name:
                    continue
                regions_meta[cat].append({
                    "name": name, "frid": None, "group": "",
                })

    # 零件：meshinggroup → part + cvols_for_octmesh
    parts_by_group: dict[str, list] = {}
    parts = mx.section("parts")
    if parts is not None:
        for mg in parts.findall("meshinggroup"):
            sgs = (mg.findtext("sgs_name") or "").strip()
            # MeshingGroup_1 → meshinggroup1
            key = sgs.replace("MeshingGroup_", "meshinggroup").replace(
                " ", "").lower()
            if not key:
                key = "meshinggroup1"
            plist = []
            for part in mg.iter("part"):
                pname = (part.findtext("name") or "").strip()
                if not pname:
                    continue
                cvols = []
                cnode = part.find("cvols_for_octmesh")
                if cnode is not None:
                    for c in cnode.findall("cvol"):
                        t = (c.text or "").strip()
                        if t:
                            cvols.append(t)
                plist.append({"name": pname, "cvols": cvols})
            if plist:
                parts_by_group[key] = plist

    # 为 face 区域补 frid（按名称在任一 MDL 中匹配——调用方再填 group）
    return regions_meta, parts_by_group


def _gph_mesh(path: str) -> dict:
    """读取并解析 GPH 网格（供 3D 缓存）。"""
    import gphstats
    with gphstats.open_buffer(path) as data:
        return gphstats.parse_mesh(data)


class AppIcons:
    """轻量矢量图标（QPainter），供工具栏 / Navigation / Tree 使用。"""

    _cache: dict[tuple, QIcon] = {}

    @classmethod
    def get(cls, name: str, size: int = 20) -> QIcon:
        key = (name, size)
        if key not in cls._cache:
            cls._cache[key] = QIcon(cls._paint(name, size))
        return cls._cache[key]

    @classmethod
    def _paint(cls, name: str, size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = max(1, size // 10)
        r = QRectF(m, m, size - 2 * m, size - 2 * m)
        drawer = getattr(cls, f"_draw_{name}", None)
        if drawer:
            drawer(p, r, size)
        else:
            cls._draw_generic(p, r)
        p.end()
        return pm

    @staticmethod
    def _pen(color, w=1.6):
        pen = QPen(QColor(color))
        pen.setWidthF(w)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        return pen

    @classmethod
    def _draw_generic(cls, p, r, _s=0):
        p.setPen(cls._pen("#555"))
        p.setBrush(QBrush(QColor("#dde3ea")))
        p.drawRoundedRect(r, 3, 3)

    @classmethod
    def _draw_open(cls, p, r, _s):
        p.setPen(cls._pen("#2e75b6", 1.4))
        p.setBrush(QBrush(QColor("#f4c542")))
        tab = QRectF(r.left(), r.top(), r.width() * 0.45, r.height() * 0.28)
        p.drawRoundedRect(tab, 2, 2)
        body = QRectF(r.left(), r.top() + r.height() * 0.22,
                      r.width(), r.height() * 0.72)
        p.setBrush(QBrush(QColor("#ffd966")))
        p.drawRoundedRect(body, 2, 2)

    @classmethod
    def _draw_save(cls, p, r, _s):
        p.setPen(cls._pen("#1f4e79", 1.3))
        p.setBrush(QBrush(QColor("#5b9bd5")))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(QBrush(QColor("#fff")))
        slot = QRectF(r.left() + r.width() * 0.22, r.top(),
                      r.width() * 0.56, r.height() * 0.38)
        p.drawRect(slot)
        p.setBrush(QBrush(QColor("#eaf2fb")))
        label = QRectF(r.left() + r.width() * 0.18,
                       r.top() + r.height() * 0.48,
                       r.width() * 0.64, r.height() * 0.42)
        p.drawRoundedRect(label, 1, 1)

    @classmethod
    def _draw_reload(cls, p, r, _s):
        p.setPen(cls._pen("#2e7d32", 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(r.toRect(), 40 * 16, 280 * 16)
        cx, cy = r.center().x(), r.center().y()
        tip = QPolygon([
            QPoint(int(cx + r.width() * 0.42), int(cy - r.height() * 0.05)),
            QPoint(int(cx + r.width() * 0.18), int(cy - r.height() * 0.38)),
            QPoint(int(cx + r.width() * 0.48), int(cy - r.height() * 0.32)),
        ])
        p.setBrush(QBrush(QColor("#2e7d32")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)

    @classmethod
    def _draw_part(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.4))
        p.setBrush(QBrush(QColor("#90caf9")))
        pts = QPolygon([
            QPoint(int(r.left() + r.width() * 0.2), int(r.bottom())),
            QPoint(int(r.left() + r.width() * 0.5), int(r.top())),
            QPoint(int(r.right()), int(r.bottom() - r.height() * 0.15)),
            QPoint(int(r.left() + r.width() * 0.55),
                   int(r.bottom() - r.height() * 0.05)),
        ])
        p.drawPolygon(pts)

    @classmethod
    def _draw_octree(cls, p, r, _s):
        p.setPen(cls._pen("#6a1b9a", 1.2))
        p.setBrush(QBrush(QColor("#ce93d8")))
        # 四分方格示意八叉树
        x0, y0, w, h = r.left(), r.top(), r.width(), r.height()
        for i in range(2):
            for j in range(2):
                cell = QRectF(x0 + i * w * 0.5, y0 + j * h * 0.5,
                              w * 0.48, h * 0.48)
                p.drawRect(cell)
        # 右上再细分
        sub = QRectF(x0 + w * 0.5, y0, w * 0.24, h * 0.24)
        p.setBrush(QBrush(QColor("#ab47bc")))
        p.drawRect(sub)
        sub2 = QRectF(x0 + w * 0.74, y0, w * 0.24, h * 0.24)
        p.drawRect(sub2)

    @classmethod
    def _draw_mesh(cls, p, r, _s):
        p.setPen(cls._pen("#00838f", 1.2))
        p.setBrush(QBrush(QColor("#80deea")))
        p.drawEllipse(r)
        p.setPen(cls._pen("#006064", 1.0))
        cx, cy = r.center().x(), r.center().y()
        for ang in (0, 60, 120):
            import math
            a = math.radians(ang)
            x = cx + math.cos(a) * r.width() * 0.42
            y = cy + math.sin(a) * r.height() * 0.42
            p.drawLine(QPointF(cx, cy), QPointF(x, y))
        p.drawLine(QPoint(int(r.left() + 2), int(r.center().y())),
                   QPoint(int(r.right() - 2), int(r.center().y())))

    @classmethod
    def _draw_section(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.2))
        p.setBrush(QBrush(QColor("#b0bec5")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#c62828", 2.2))
        p.drawLine(QPoint(int(r.left()), int(r.top() + r.height() * 0.7)),
                   QPoint(int(r.right()), int(r.top() + r.height() * 0.3)))

    @classmethod
    def _draw_fit(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.6))
        p.setBrush(Qt.NoBrush)
        # 四角括号
        s = r.width() * 0.28
        corners = [
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ]
        for x, y, sx, sy in corners:
            p.drawLine(QPoint(int(x), int(y)),
                       QPoint(int(x + sx * s), int(y)))
            p.drawLine(QPoint(int(x), int(y)),
                       QPoint(int(x), int(y + sy * s)))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.drawEllipse(r.adjusted(r.width() * 0.28, r.height() * 0.28,
                                 -r.width() * 0.28, -r.height() * 0.28))

    @classmethod
    def _draw_show_all(cls, p, r, _s):
        p.setPen(cls._pen("#ef6c00", 1.3))
        p.setBrush(QBrush(QColor("#ffe0b2")))
        p.drawEllipse(r.adjusted(r.width() * 0.15, r.height() * 0.2,
                                 -r.width() * 0.15, -r.height() * 0.15))
        p.setBrush(QBrush(QColor("#fff")))
        eye = QRectF(r.center().x() - r.width() * 0.12,
                     r.center().y() - r.height() * 0.08,
                     r.width() * 0.24, r.height() * 0.24)
        p.drawEllipse(eye)
        p.setBrush(QBrush(QColor("#333")))
        p.drawEllipse(eye.adjusted(eye.width() * 0.3, eye.height() * 0.3,
                                   -eye.width() * 0.3, -eye.height() * 0.3))

    @classmethod
    def _draw_display(cls, p, r, _s):
        p.setPen(cls._pen("#5d4037", 1.2))
        p.setBrush(QBrush(QColor(100, 149, 237, 120)))
        p.drawEllipse(r)
        p.setBrush(QBrush(QColor("#5c6bc0")))
        p.drawEllipse(r.adjusted(r.width() * 0.35, r.height() * 0.35,
                                 -r.width() * 0.05, -r.height() * 0.05))

    @classmethod
    def _draw_folder(cls, p, r, _s):
        cls._draw_open(p, r, _s)

    @classmethod
    def _draw_group(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#bbdefb")))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(cls._pen("#0d47a1", 1.4))
        p.drawText(r.toRect(), Qt.AlignCenter, "G")

    @classmethod
    def _draw_body(cls, p, r, _s):
        # MeshClosedVolume：黄块（对齐 scFLOWpre）
        p.setPen(cls._pen("#c9a227", 1.2))
        p.setBrush(QBrush(QColor("#f6e59a")))
        p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 3, 3)

    @classmethod
    def _draw_region(cls, p, r, _s):
        p.setPen(cls._pen("#2e7d32", 1.3))
        p.setBrush(QBrush(QColor("#81c784")))
        # 菱形（Surface Region 项）
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width() * 0.42, r.height() * 0.42
        poly = QPolygon([
            QPoint(int(cx), int(cy - h)),
            QPoint(int(cx + w), int(cy)),
            QPoint(int(cx), int(cy + h)),
            QPoint(int(cx - w), int(cy)),
        ])
        p.drawPolygon(poly)

    @classmethod
    def _draw_fluid(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.3))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        y0 = r.center().y()
        path.moveTo(r.left() + 1, y0)
        w = r.width()
        path.cubicTo(r.left() + w * 0.25, y0 - r.height() * 0.25,
                     r.left() + w * 0.35, y0 + r.height() * 0.25,
                     r.left() + w * 0.5, y0)
        path.cubicTo(r.left() + w * 0.65, y0 - r.height() * 0.25,
                     r.left() + w * 0.75, y0 + r.height() * 0.25,
                     r.right() - 1, y0)
        p.drawPath(path)
        path2 = QPainterPath()
        y1 = y0 + r.height() * 0.22
        path2.moveTo(r.left() + 1, y1)
        path2.cubicTo(r.left() + w * 0.25, y1 - r.height() * 0.2,
                      r.left() + w * 0.35, y1 + r.height() * 0.2,
                      r.left() + w * 0.5, y1)
        path2.cubicTo(r.left() + w * 0.65, y1 - r.height() * 0.2,
                      r.left() + w * 0.75, y1 + r.height() * 0.2,
                      r.right() - 1, y1)
        p.drawPath(path2)

    @classmethod
    def _draw_project(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.2))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#263238", 1.0))
        for i in range(3):
            y = r.top() + r.height() * (0.28 + i * 0.22)
            p.drawLine(QPoint(int(r.left() + 3), int(y)),
                       QPoint(int(r.right() - 3), int(y)))

    @classmethod
    def _draw_script(cls, p, r, _s):
        p.setPen(cls._pen("#6a1b9a", 1.2))
        p.setBrush(QBrush(QColor("#e1bee7")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#4a148c", 1.5))
        p.setFont(QFont("Consolas", max(6, int(r.height() * 0.45))))
        p.drawText(r.toRect(), Qt.AlignCenter, "{}")

    @classmethod
    def _draw_xml(cls, p, r, _s):
        p.setPen(cls._pen("#bf360c", 1.2))
        p.setBrush(QBrush(QColor("#ffccbc")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#bf360c", 1.3))
        p.setFont(QFont("Consolas", max(6, int(r.height() * 0.4))))
        p.drawText(r.toRect(), Qt.AlignCenter, "<>")

    @classmethod
    def _draw_snapshot(cls, p, r, _s):
        p.setPen(cls._pen("#00695c", 1.2))
        p.setBrush(QBrush(QColor("#b2dfdb")))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(QBrush(QColor("#26a69a")))
        p.drawEllipse(r.adjusted(r.width() * 0.25, r.height() * 0.25,
                                 -r.width() * 0.25, -r.height() * 0.25))

    @classmethod
    def _draw_dashboard(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.1))
        colors = ["#ef5350", "#42a5f5", "#66bb6a", "#ffa726"]
        cells = [
            QRectF(r.left(), r.top(), r.width() * 0.48, r.height() * 0.48),
            QRectF(r.left() + r.width() * 0.52, r.top(),
                   r.width() * 0.48, r.height() * 0.48),
            QRectF(r.left(), r.top() + r.height() * 0.52,
                   r.width() * 0.48, r.height() * 0.48),
            QRectF(r.left() + r.width() * 0.52, r.top() + r.height() * 0.52,
                   r.width() * 0.48, r.height() * 0.48),
        ]
        for cell, c in zip(cells, colors):
            p.setBrush(QBrush(QColor(c)))
            p.drawRoundedRect(cell, 1, 1)

    @classmethod
    def _draw_nav_section(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#e3f2fd")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#0d47a1", 1.8))
        mid = r.center().y()
        p.drawLine(QPoint(int(r.left() + 3), int(mid)),
                   QPoint(int(r.right() - 3), int(mid)))
        p.drawLine(QPoint(int(r.center().x()), int(r.top() + 3)),
                   QPoint(int(r.center().x()), int(r.bottom() - 3)))

    @classmethod
    def _draw_param(cls, p, r, _s):
        p.setPen(cls._pen("#546e7a", 1.3))
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawEllipse(r)
        # 简易齿轮齿
        cx, cy = r.center().x(), r.center().y()
        import math
        for i in range(8):
            a = math.radians(i * 45)
            x1 = cx + math.cos(a) * r.width() * 0.28
            y1 = cy + math.sin(a) * r.height() * 0.28
            x2 = cx + math.cos(a) * r.width() * 0.48
            y2 = cy + math.sin(a) * r.height() * 0.48
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


# Navigation / Tree 节点 key → 图标名
NAV_ICONS = {
    "open": "open", "reload": "reload", "project": "project",
    "parts_control": "param", "import_part": "open",
    "create_parts": "part", "modify_parts": "part",
    "mesher_faceter": "mesh", "regions": "region",
    "non_solid": "part", "part_material": "project",
    "conditions": "xml",
    "specify_disc": "part", "overset_mesh": "octree",
    "wrap_octree": "octree", "wrap_param": "param",
    "begin_wrap": "show_all", "cancel_wrap": "show_all",
    "exec_wrap": "show_all", "retry_wrap": "show_all",
    "build_am": "octree", "oct_param": "octree",
    "mesh_param": "mesh", "execute": "show_all",
    "mdl": "part", "oct": "octree", "gph": "mesh",
    "snapshot": "snapshot",
    "view_part": "part", "view_octree": "octree", "view_mesh": "mesh",
    "view_section": "section", "view_show_all": "show_all",
    "xml": "xml", "js": "script", "dashboard": "dashboard", "save": "save",
}
NAV_SECTION_ICONS = {
    "Prepare Parts": "folder",
    "Data / Script": "script",
}

# Navigation 顶层节点：("section"|"leaf", label, key_or_children)
# leaf 的 key 为 str；section 的 children 为 list[tuple[label, key]]


class BarChart(QWidget):
    """横向条形图（QPainter 绘制，无第三方依赖）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, float, tuple]] = []
        self.unit = ""
        self.setMinimumHeight(160)

    def set_data(self, items, unit: str = "") -> None:
        self.items = items
        self.unit = unit
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802 - Qt 命名
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        if not self.items:
            p.drawText(self.rect(), Qt.AlignCenter, "无数据")
            return
        w = self.width()
        row_h = 22
        label_w = min(150, int(w * 0.35))
        vmax = max(v for _, v, _ in self.items) or 1
        for i, (label, value, color) in enumerate(self.items):
            y = 8 + i * row_h
            p.setPen(QColor(40, 40, 40))
            p.drawText(4, y + 14, label_w - 4, 16,
                       Qt.AlignRight | Qt.AlignVCenter, label)
            bar_w = int((w - label_w - 90) * value / vmax)
            p.fillRect(label_w + 6, y + 2, max(bar_w, 2), 16,
                       QColor(*[int(c * 255) for c in color]))
            p.setPen(QColor(60, 60, 60))
            p.drawText(label_w + 10 + bar_w, y + 14, 90, 16,
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{value:,.0f}{self.unit}")
        p.end()


class LegendPanel(QFrame):
    """Qt 图例面板：离散区域色块行 + 连续渐变条。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LegendPanel")
        self.setFixedWidth(180)
        self.setFrameShape(QFrame.StyledPanel)
        # 不用 WA_OpaquePaintEvent：与样式表冲突时最大化后整块变黑
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(255, 255, 255))
        pal.setColor(QPalette.Base, QColor(255, 255, 255))
        pal.setColor(QPalette.Button, QColor(255, 255, 255))
        self.setPalette(pal)
        self.setStyleSheet(
            "#LegendPanel { background-color: #ffffff;"
            " border: 1px solid #9a9a9a; }")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(6)
        self.setVisible(False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        # 强制白底，防止 VTK HWND 透出后显示为黑块
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        p.end()
        super().paintEvent(event)

    @staticmethod
    def _drain_layout(layout) -> None:
        """递归清空 layout（含嵌套 QHBoxLayout），避免图例叠加残留。"""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            child = item.layout()
            if child is not None:
                LegendPanel._drain_layout(child)

    def clear(self) -> None:
        self._drain_layout(self._layout)

    def set_layers(self, layers) -> None:
        self.clear()
        if not layers:
            self.setVisible(False)
            return
        for title, lut, entries in layers:
            self._layout.addWidget(QLabel(f"<b>{title}</b>", self))
            if entries:
                for label, rgb in entries:
                    row_w = QWidget(self)
                    row = QHBoxLayout(row_w)
                    row.setContentsMargins(0, 0, 0, 0)
                    swatch = QLabel(row_w)
                    swatch.setFixedSize(16, 16)
                    swatch.setStyleSheet(
                        f"background-color: rgb({int(rgb[0] * 255)},"
                        f"{int(rgb[1] * 255)},{int(rgb[2] * 255)});"
                        "border: 1px solid #888;")
                    row.addWidget(swatch)
                    row.addWidget(QLabel(label, row_w), 1)
                    self._layout.addWidget(row_w)
            elif lut is not None:
                row_w = QWidget(self)
                row = QHBoxLayout(row_w)
                row.setContentsMargins(0, 0, 0, 0)
                pm_label = QLabel(row_w)
                pm_label.setPixmap(self._gradient_pixmap(lut))
                row.addWidget(pm_label)
                rng = lut.GetRange()
                row.addWidget(
                    QLabel(f"{rng[1]:g} … {rng[0]:g}", row_w), 1)
                self._layout.addWidget(row_w)
            else:
                self._layout.addWidget(QLabel("—", self))
        self._layout.addStretch(1)
        self.setVisible(True)
        self.update()

    @staticmethod
    def _gradient_pixmap(lut, height: int = 120) -> QPixmap:
        pm = QPixmap(18, height)
        painter = QPainter(pm)
        n = max(lut.GetNumberOfTableValues(), 1)
        for y in range(height):
            idx = int((1 - y / max(height - 1, 1)) * (n - 1))
            c = lut.GetTableValue(idx)
            painter.setPen(QColor(int(c[0] * 255), int(c[1] * 255),
                                  int(c[2] * 255)))
            painter.drawLine(0, y, 17, y)
        painter.end()
        return pm


class PaneFrame(QFrame):
    """scFLOWpre 风格停靠窗格：标题栏 + 内容区。"""

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("PaneFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(24)
        bar.setAutoFillBackground(True)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 6, 0)
        self.title_label = QLabel(title, bar)
        self.title_label.setObjectName("PaneTitle")
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        lay.addWidget(bar)
        # 内容外包一层，避免 VTK 原生 HWND 画穿标题栏/邻窗
        host = QFrame(self)
        host.setObjectName("PaneBody")
        host.setAutoFillBackground(True)
        host.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(content, 1)
        lay.addWidget(host, 1)
        self._content = content

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class MessageWindow(QWidget):
    """Message Window：操作日志 / 提示 / 未实现功能说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(2, 2, 2, 2)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(2000)
        self.text.setPlaceholderText("Messages…")
        v.addWidget(self.text)

    def log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText(f"[{ts}] {level}: {msg}")
        self.text.verticalScrollBar().setValue(
            self.text.verticalScrollBar().maximum())

    def clear(self) -> None:
        self.text.clear()


class NavigationWindow(QWidget):
    """scFLOWpre Navigation Window：按预处理流程排列的功能入口。"""

    navigated = pyqtSignal(str)

    # 对齐 scFLOWpre Navigation；Open/Save/Reload/Draw 在工具栏
    # Parts Control 勾选项会动态插入（见 set_parts_control）
    # Prepare Parts 仅含前期零件准备项；其后多项与 Prepare Parts 同级（叶子）
    _PREPARE_BASE = [
        ("Parts Control", "parts_control"),
        ("Import Part File", "import_part"),
        ("Create Parts", "create_parts"),
        ("Modify Parts", "modify_parts"),
    ]
    # 与 Prepare Parts 同级的叶子（手册顺序）
    _PEER_LEAVES = [
        ("Mesher/Faceter Setting", "mesher_faceter"),
        ("Register Region", "regions"),
        ("Create Non-Solid Part", "non_solid"),
        ("Part Material", "part_material"),
        ("Conditions", "conditions"),
        ("Build Analysis Model", "build_am"),
        ("Octree Parameter", "oct_param"),
        ("Mesh Parameter", "mesh_param"),
        ("Execute", "execute"),
    ]
    _DATA_BASE = [
        ("Project Info (xenv/prp)", "project"),
        ("Project XML", "xml"),
        ("User Script (JS)", "js"),
        ("Snapshot / Parasolid", "snapshot"),
        ("Format Dashboard", "dashboard"),
    ]
    # Parts Control → 插入 Navigation 的条件项
    _PC_DISC = ("Specify Discontinuous Parts", "specify_disc")
    _PC_OVERSET = ("Overset Mesh", "overset_mesh")
    _PC_WRAP_PREPARE = [
        ("Wrapping Octree Parameter", "wrap_octree"),
        ("Wrapping Parameter", "wrap_param"),
    ]
    _PC_WRAP_EXECUTE = [
        ("Begin Wrapping", "begin_wrap"),
        ("Cancel Wrapping", "cancel_wrap"),
        ("Execute Wrapping", "exec_wrap"),
        ("Retry Wrapping", "retry_wrap"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self._parts_control = {
            "discontinuous": False, "overset": False, "wrapping": False}
        # scFLOWpre：仅 Polyhedral mesher 时显示 Build Analysis Model
        self._polyhedral_mesher = True
        self._show_bam_item = True
        self._show_mesher_item = True
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        self.file_label = QLabel("No project", self)
        self.file_label.setWordWrap(True)
        self.file_label.setObjectName("NavFileLabel")
        v.addWidget(self.file_label)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.setObjectName("NavTree")
        v.addWidget(self.tree, 1)
        self._rebuild_tree()

    def _nav_nodes(self) -> list[tuple]:
        """对齐 scFLOWpre：Prepare Parts 分组 + 同级叶子 + Data/Script。

        返回节点列表，每项为：
        - ``("section", title, [(label, key), ...])``
        - ``("leaf", label, key)``
        """
        pc = self._parts_control
        prepare: list[tuple[str, str]] = []
        for item in self._PREPARE_BASE:
            prepare.append(item)
            # Modify Parts 之后插入条件项（手册 Prepare Parts 顺序）
            if item[1] == "modify_parts":
                if pc.get("discontinuous"):
                    prepare.append(self._PC_DISC)
                if pc.get("overset"):
                    prepare.append(self._PC_OVERSET)
                if pc.get("wrapping"):
                    prepare.extend(self._PC_WRAP_PREPARE)

        nodes: list[tuple] = [("section", "Prepare Parts", prepare)]

        # Wrapping 执行项：手册在 Mesher/Faceter 之前、与 Prepare Parts 同级
        if pc.get("wrapping"):
            for label, key in self._PC_WRAP_EXECUTE:
                nodes.append(("leaf", label, key))

        for label, key in self._PEER_LEAVES:
            if key == "build_am" and (
                    not self._polyhedral_mesher or not self._show_bam_item):
                continue
            if key == "mesher_faceter" and not self._show_mesher_item:
                continue
            nodes.append(("leaf", label, key))

        nodes.append(("section", "Data / Script", list(self._DATA_BASE)))
        return nodes

    def _rebuild_tree(self) -> None:
        self.tree.clear()
        for kind, a, b in self._nav_nodes():
            if kind == "section":
                root = QTreeWidgetItem([a])
                root.setFlags(Qt.ItemIsEnabled)
                font = root.font(0)
                font.setBold(True)
                root.setFont(0, font)
                root.setIcon(0, AppIcons.get(
                    NAV_SECTION_ICONS.get(a, "nav_section"), 16))
                self.tree.addTopLevelItem(root)
                for label, key in b:
                    child = QTreeWidgetItem([label])
                    child.setData(0, Qt.UserRole, key)
                    child.setToolTip(0, label)
                    child.setIcon(
                        0, AppIcons.get(NAV_ICONS.get(key, "generic"), 16))
                    root.addChild(child)
                root.setExpanded(True)
            else:  # leaf — 与 Prepare Parts 同级
                leaf = QTreeWidgetItem([a])
                leaf.setData(0, Qt.UserRole, b)
                leaf.setToolTip(0, a)
                leaf.setIcon(
                    0, AppIcons.get(NAV_ICONS.get(b, "generic"), 16))
                self.tree.addTopLevelItem(leaf)

    def set_parts_control(self, flags: dict) -> None:
        """按 Parts Control 勾选刷新 Navigation 子项。"""
        self._parts_control = {
            "discontinuous": bool(flags.get("discontinuous")),
            "overset": bool(flags.get("overset")),
            "wrapping": bool(flags.get("wrapping")),
        }
        self._rebuild_tree()

    def set_polyhedral_mesher(self, enabled: bool) -> None:
        """Mesher/Faceter：Polyhedral 时显示 Build Analysis Model。"""
        enabled = bool(enabled)
        if self._polyhedral_mesher == enabled:
            return
        self._polyhedral_mesher = enabled
        self._rebuild_tree()

    def set_show_bam_item(self, enabled: bool) -> None:
        """Option → Navigation：是否显示 Build Analysis Model 节点。"""
        enabled = bool(enabled)
        if self._show_bam_item == enabled:
            return
        self._show_bam_item = enabled
        self._rebuild_tree()

    def set_show_mesher_item(self, enabled: bool) -> None:
        """Option → Navigation：是否显示 Mesher/Faceter Setting 节点。"""
        enabled = bool(enabled)
        if self._show_mesher_item == enabled:
            return
        self._show_mesher_item = enabled
        self._rebuild_tree()

    def _on_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.UserRole)
        if key:
            self.navigated.emit(key)

    def set_file_info(self, path: str, n_members: int, total_size: str) -> None:
        self.file_label.setText(
            f"{os.path.basename(path)}\n"
            f"{n_members} members · {total_size}")

    def set_loaded(self, loaded: bool) -> None:
        if not loaded:
            self.file_label.setText("No project")


class PropertyPanel(QWidget):
    """Property Window：选中树项的解析属性。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setColumnWidth(0, 120)
        layout.addWidget(self.tree, 1)

    def set_properties(self, props: dict) -> None:
        self.tree.clear()
        for key, value in props.items():
            item = QTreeWidgetItem([str(key), ""])
            self._fill(item, value)
            self.tree.addTopLevelItem(item)
            item.setExpanded(True)

    def _fill(self, item: QTreeWidgetItem, value) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                child = QTreeWidgetItem([str(k), ""])
                self._fill(child, v)
                item.addChild(child)
                child.setExpanded(True)
        elif isinstance(value, (list, tuple)):
            item.setText(1, f"[{len(value)} 项]")
            for v in value:
                child = QTreeWidgetItem(["", str(v)])
                item.addChild(child)
        else:
            item.setText(1, "" if value is None else str(value))


class StatusPanel(QWidget):
    """几何 / 八叉树 / 体网格状态（对齐 Tree 右键 Show … information）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.tabs = QTabWidget(self)
        self.geo_tree = QTreeWidget(self)
        self.oct_tree = QTreeWidget(self)
        self.mesh_tree = QTreeWidget(self)
        for tw, name in ((self.geo_tree, "几何"),
                         (self.oct_tree, "八叉树"),
                         (self.mesh_tree, "体网格")):
            tw.setHeaderLabels(["项", "值"])
            tw.setColumnWidth(0, 120)
            self.tabs.addTab(tw, name)
        layout.addWidget(self.tabs, 1)
        self._group_status: dict[str, dict] = {}

    def set_group_status(self, group: str, status: dict) -> None:
        self._group_status[group] = status
        self.show_group(group)

    def clear(self) -> None:
        self._group_status.clear()
        for tw in (self.geo_tree, self.oct_tree, self.mesh_tree):
            tw.clear()

    def show_group(self, group: str, focus: Optional[str] = None) -> None:
        st = self._group_status.get(group, {})
        self._fill_tree(self.geo_tree, st.get("geometry") or {"状态": "无 MDL"})
        self._fill_tree(self.oct_tree, st.get("octree") or {"状态": "无 OCT"})
        self._fill_tree(self.mesh_tree, st.get("mesh") or {"状态": "无 GPH"})
        if focus == "octree":
            self.tabs.setCurrentWidget(self.oct_tree)
        elif focus == "mesh":
            self.tabs.setCurrentWidget(self.mesh_tree)
        elif focus == "geometry":
            self.tabs.setCurrentWidget(self.geo_tree)

    @staticmethod
    def _fill_tree(tree: QTreeWidget, props: dict) -> None:
        tree.clear()
        for key, value in props.items():
            item = QTreeWidgetItem([str(key), ""])
            if isinstance(value, dict):
                item.setText(1, "")
                for k, v in value.items():
                    item.addChild(QTreeWidgetItem([str(k), str(v)]))
                item.setExpanded(True)
            elif isinstance(value, (list, tuple)):
                item.setText(1, f"[{len(value)}]")
                for v in value:
                    item.addChild(QTreeWidgetItem(["", str(v)]))
            else:
                item.setText(1, "" if value is None else str(value))
            tree.addTopLevelItem(item)


class ModelTree(QWidget):
    """scFLOWpre 风格 Part Tree：

    Project → Parts (Whole) → 几何名 / MeshClosedVolume* / Octree / Mesh  
    Fluid Region → 流体域 / Void Region  
    Region → Surface / Part Interface / Volume / Numerical / …

    勾选：零件与 MeshClosedVolume → 体域显隐；Surface Region → 面域显隐；
    Octree/Mesh → 图层总开关。
    """

    visibility_changed = pyqtSignal(str, set, set, bool)
    # (group, 隐藏的 body, 隐藏的 region, 组可见)
    layer_visibility_changed = pyqtSignal(str, str, bool)
    # (group, layer in mdl|oct|gph, visible)
    item_selected = pyqtSignal(dict)
    status_requested = pyqtSignal(str, str)
    focus_3d = pyqtSignal(str)
    select_mesh = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["模型", "状态"])
        self.tree.setColumnWidth(0, 180)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.setToolTip(
            "勾选=显示；零件/闭体控制体域，Surface Region 控制面域；"
            "Octree/Mesh 为图层开关")
        v.addWidget(self.tree)
        self._info: dict[str, dict] = {}
        self._project_name = ""
        self._regions_meta: dict = {}

    def groups(self) -> list[str]:
        return sorted(self._info)

    def populate(self, groups_info: dict, *, project_name: str = "",
                 regions_meta: Optional[dict] = None) -> None:
        """对齐 scFLOWpre Part Tree。

        ``groups_info[group]`` 含 part / oct_summary / gph_summary / paths /
        ``xml_parts``（[{name, cvols}]）。
        ``regions_meta`` 含 fluid / face / volume / numerical / …
        """
        self._info = groups_info
        self._project_name = project_name or "Project"
        self._regions_meta = regions_meta or {}
        self.tree.blockSignals(True)
        self.tree.clear()

        proj = QTreeWidgetItem([f"Project ({self._project_name})", ""])
        proj.setData(0, Qt.UserRole, ("project", "", None))
        proj.setFlags(proj.flags() | Qt.ItemIsUserCheckable)
        proj.setCheckState(0, Qt.Checked)
        proj.setIcon(0, AppIcons.get("project", 16))
        self.tree.addTopLevelItem(proj)

        parts_root = QTreeWidgetItem(["Parts (Whole)", ""])
        parts_root.setData(0, Qt.UserRole, ("parts_root", "", None))
        parts_root.setIcon(0, AppIcons.get("folder", 16))
        proj.addChild(parts_root)

        for group in sorted(groups_info):
            info = groups_info[group]
            parent = parts_root
            if len(groups_info) > 1:
                gnode = QTreeWidgetItem([group, "meshing group"])
                gnode.setData(0, Qt.UserRole, ("group", group, None))
                gnode.setFlags(gnode.flags() | Qt.ItemIsUserCheckable)
                gnode.setCheckState(0, Qt.Checked)
                gnode.setIcon(0, AppIcons.get("group", 16))
                parts_root.addChild(gnode)
                parent = gnode

            xml_parts = info.get("xml_parts") or []
            mdl = info.get("part")
            if not xml_parts and mdl is not None:
                xml_parts = self._parts_from_mdl(mdl)

            for pd in xml_parts:
                pname = pd["name"]
                body_id = self._part_body_id(mdl, pname)
                status = ""
                if body_id is not None and mdl is not None:
                    n = int(((mdl.csid[0] == body_id) | (mdl.csid[1] == body_id)).sum()) \
                        if mdl.csid[1].size else 0
                    status = f"{n:,} faces" if n else ""
                pitem = QTreeWidgetItem([pname, status])
                pitem.setData(0, Qt.UserRole, ("part", group, body_id))
                pitem.setFlags(pitem.flags() | Qt.ItemIsUserCheckable)
                pitem.setCheckState(0, Qt.Checked)
                pitem.setIcon(0, AppIcons.get("part", 16))
                parent.addChild(pitem)
                for cvol_txt in pd.get("cvols") or []:
                    disp = _mesh_closed_volume_label(cvol_txt)
                    cid = _closed_volume_id(cvol_txt)
                    # MeshClosedVolume 与零件共用 body 显隐（有体网格的零件）
                    citem = QTreeWidgetItem([disp, f"cvol={cid}" if cid else ""])
                    citem.setData(0, Qt.UserRole, ("cvol", group, body_id))
                    citem.setFlags(citem.flags() | Qt.ItemIsUserCheckable)
                    citem.setCheckState(0, Qt.Checked)
                    citem.setIcon(0, AppIcons.get("body", 16))
                    pitem.addChild(citem)
                pitem.setExpanded(True)

            # 图层：Octree / Mesh（几何显隐由零件勾选表达，不再单独挂 MDL 层）
            # 仍保留 mdl 图层逻辑：零件全关时等价隐藏几何；默认 mdl 层开
            oct_item = QTreeWidgetItem(["Octree", self._oct_status_text(info)])
            oct_item.setData(0, Qt.UserRole, ("layer", group, "oct"))
            oct_item.setFlags(oct_item.flags() | Qt.ItemIsUserCheckable)
            oct_item.setCheckState(0, Qt.Unchecked)
            oct_item.setIcon(0, AppIcons.get("octree", 16))
            if not info.get("paths", {}).get("oct"):
                oct_item.setFlags(oct_item.flags() & ~Qt.ItemIsEnabled)
            parent.addChild(oct_item)

            mesh_item = QTreeWidgetItem(["Mesh", self._mesh_status_text(info)])
            mesh_item.setData(0, Qt.UserRole, ("layer", group, "gph"))
            mesh_item.setFlags(mesh_item.flags() | Qt.ItemIsUserCheckable)
            has_gph = bool(info.get("paths", {}).get("gph"))
            mesh_item.setCheckState(0, Qt.Checked if has_gph else Qt.Unchecked)
            mesh_item.setIcon(0, AppIcons.get("mesh", 16))
            if not has_gph:
                mesh_item.setFlags(mesh_item.flags() & ~Qt.ItemIsEnabled)
            parent.addChild(mesh_item)

            # 隐式 mdl 层：始终视为开启（由零件勾选过滤）
            # 同步 layer_hidden 时不把 mdl 放进树

        parts_root.setExpanded(True)
        proj.setExpanded(True)

        # ── Fluid Region ──────────────────────────────────────────
        fluid_root = QTreeWidgetItem(["Fluid Region", ""])
        fluid_root.setData(0, Qt.UserRole, ("fluid_root", "", None))
        fluid_root.setIcon(0, AppIcons.get("fluid", 16))
        self.tree.addTopLevelItem(fluid_root)
        for fr in self._regions_meta.get("fluid") or []:
            label = fr.get("label") or fr.get("name") or "FluidRegion"
            item = QTreeWidgetItem([label, fr.get("sparts", "")])
            item.setData(0, Qt.UserRole, ("fluid", "", fr.get("name")))
            item.setIcon(0, AppIcons.get("fluid", 16))
            fluid_root.addChild(item)
        void_item = QTreeWidgetItem(["(Void Region)", ""])
        void_item.setData(0, Qt.UserRole, ("fluid", "", "__void__"))
        void_item.setIcon(0, AppIcons.get("fluid", 16))
        fluid_root.addChild(void_item)
        fluid_root.setExpanded(True)

        # ── Region ────────────────────────────────────────────────
        reg_root = QTreeWidgetItem(["Region", ""])
        reg_root.setData(0, Qt.UserRole, ("region_root", "", None))
        reg_root.setIcon(0, AppIcons.get("folder", 16))
        self.tree.addTopLevelItem(reg_root)

        # Surface Region：XML face + 回退 MDL（排除零件名）
        surf_node = QTreeWidgetItem(["Surface Region", ""])
        surf_node.setData(0, Qt.UserRole, ("region_cat", "", "face"))
        surf_node.setIcon(0, AppIcons.get("folder", 16))
        reg_root.addChild(surf_node)
        surf_entries = list(self._regions_meta.get("face") or [])
        if not surf_entries:
            surf_entries = self._fallback_surface_regions(groups_info)
        default_group = sorted(groups_info)[0] if groups_info else ""
        for se in surf_entries:
            g = se.get("group") or default_group
            item = QTreeWidgetItem([se["name"], f"frid={se['frid']}"])
            item.setData(0, Qt.UserRole, ("region", g, se["frid"]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setIcon(0, AppIcons.get("region", 16))
            surf_node.addChild(item)
        surf_node.setExpanded(True)

        for cat, title in (
            ("special_face", "Part Interface Region"),
            ("volume", "Volume Region"),
            ("numerical", "Numerical Region"),
            ("cross_section", "Cross Section Region"),
        ):
            node = QTreeWidgetItem([title, ""])
            node.setData(0, Qt.UserRole, ("region_cat", "", cat))
            node.setIcon(0, AppIcons.get("folder", 16))
            reg_root.addChild(node)
            for se in self._regions_meta.get(cat) or []:
                g = se.get("group") or default_group
                child = QTreeWidgetItem([se["name"], ""])
                child.setData(0, Qt.UserRole, ("region", g, se.get("frid")))
                if se.get("frid") is not None:
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.Checked)
                child.setIcon(0, AppIcons.get("region", 16))
                node.addChild(child)

        ref = QTreeWidgetItem(["Reference Point", ""])
        ref.setData(0, Qt.UserRole, ("region_cat", "", "reference"))
        ref.setIcon(0, AppIcons.get("dashboard", 16))
        reg_root.addChild(ref)
        reg_root.setExpanded(True)

        self.tree.blockSignals(False)

    @staticmethod
    def _part_body_id(mdl_model, part_name: str) -> Optional[int]:
        if mdl_model is None:
            return None
        for r in mdl_model.surface_regions:
            if r.name == part_name or r.name == f"@PartSurface_{part_name}":
                return int(r.index) + 1
        return None

    @staticmethod
    def _parts_from_mdl(mdl_model) -> list[dict]:
        """无 XML 时从 MDL @PartSurface_* 推导零件列表。"""
        seen: dict[str, int] = {}
        for r in mdl_model.surface_regions:
            if r.name.startswith("@PartSurface_"):
                seen.setdefault(r.name[len("@PartSurface_"):], r.index)
        # GPH 有 cvol 的零件才会挂 MeshClosedVolume；此处无 GPH 时不挂
        return [{"name": n, "cvols": []} for n in seen]

    @staticmethod
    def _fallback_surface_regions(groups_info: dict) -> list[dict]:
        """XML 无 face 时：MDL 面域中排除零件名后的项（如 open）。"""
        out = []
        for group, info in groups_info.items():
            mdl = info.get("part")
            if mdl is None:
                continue
            part_names = {r.name[len("@PartSurface_"):]
                          for r in mdl.surface_regions
                          if r.name.startswith("@PartSurface_")}
            seen: dict[int, str] = {}
            for r in mdl.surface_regions:
                if r.name.startswith("@"):
                    continue
                if r.name in part_names:
                    continue
                seen.setdefault(int(r.index), r.name)
            for frid, name in sorted(seen.items()):
                out.append({"name": name, "frid": frid, "group": group})
        return out

    @staticmethod
    def _oct_status_text(info: dict) -> str:
        s = info.get("oct_summary") or {}
        if not s:
            return "—"
        return f"{s.get('n_leaves', 0):,} leaves"

    @staticmethod
    def _mesh_status_text(info: dict) -> str:
        s = info.get("gph_summary") or {}
        if not s:
            return "—"
        links = s.get("links") or {}
        cells = links.get("n_cells", s.get("n_cells") or 0)
        return f"{cells:,} cells"

    def group_status_props(self, group: str) -> dict:
        """供 StatusPanel 使用的结构化状态。"""
        info = self._info.get(group, {})
        m = info.get("part")
        geo: dict = {"状态": "无 MDL"}
        if m is not None:
            bodies = sorted({int(x) for x in m.csid[1] if x > 0}) if m.csid[1].size else []
            regions = [(r.name, r.index) for r in m.surface_regions
                       if not r.name.startswith("@")]
            geo = {
                "类型": "MDL 面片几何",
                "顶点": f"{m.n_vertices:,}",
                "面": f"{m.n_faces:,}",
                "闭体数": m.n_closed_volumes,
                "闭体 ID": bodies,
                "体区域": m.volume_regions,
                "面区域": [f"{n} (frid={i})" for n, i in regions],
                "零件": [p.get("name") for p in (info.get("xml_parts") or [])],
            }
            if m.xyz.size:
                lo = m.xyz.min(axis=0)
                hi = m.xyz.max(axis=0)
                geo["包围盒"] = {
                    "xmin…xmax": f"{lo[0]:.6g} … {hi[0]:.6g}",
                    "ymin…ymax": f"{lo[1]:.6g} … {hi[1]:.6g}",
                    "zmin…zmax": f"{lo[2]:.6g} … {hi[2]:.6g}",
                }
        oct_s = info.get("oct_summary") or {}
        octree = {"状态": "无 OCT"} if not oct_s else {
            "类型": "OCT 八叉树",
            "节点": f"{oct_s.get('n_octants', 0):,}",
            "内部": f"{oct_s.get('n_internal', 0):,}",
            "叶子": f"{oct_s.get('n_leaves', 0):,}",
            "单位": oct_s.get("unit", ""),
            "最大深度": oct_s.get("max_depth", "—"),
        }
        gph = info.get("gph_summary") or {}
        mesh = {"状态": "无 GPH"}
        if gph:
            links = gph.get("links") or {}
            mesh = {
                "类型": "GPH 体网格",
                "单元": f"{links.get('n_cells', gph.get('n_cells') or 0):,}",
                "面": f"{links.get('n_faces', 0):,}",
                "边界面": f"{links.get('boundary_faces', 0):,}",
                "顶点": f"{gph.get('n_vertices', 0):,}",
                "方言": gph.get("dialect", ""),
                "npe": f"[{links.get('npe_min', 0)}..{links.get('npe_max', 0)}]",
                "体区域": gph.get("volume_regions") or [],
                "面区域": [n for n, _ in (gph.get("surface_regions") or [])],
                "闭体 cvol": gph.get("cvol_unique") or [],
                "Parts": gph.get("parts") or [],
            }
        return {"geometry": geo, "octree": octree, "mesh": mesh}

    def _iter_all_items(self):
        stack = [self.tree.topLevelItem(i)
                 for i in range(self.tree.topLevelItemCount())]
        while stack:
            node = stack.pop()
            yield node
            for j in range(node.childCount()):
                stack.append(node.child(j))

    def _items(self, group: str, kind: str):
        out = []
        for node in self._iter_all_items():
            data = node.data(0, Qt.UserRole)
            if data and data[0] == kind and data[1] == group:
                out.append(node)
        return out

    def _project_item(self) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            data = root.data(0, Qt.UserRole)
            if data and data[0] == "project":
                return root
        return None

    def group_visible(self, group: str) -> bool:
        proj = self._project_item()
        if proj is not None and proj.checkState(0) != Qt.Checked:
            return False
        for item in self._items(group, "group"):
            return item.checkState(0) == Qt.Checked
        return True

    def layer_visible(self, group: str, layer: str) -> bool:
        if layer == "mdl":
            # 几何由零件勾选控制；图层默认开
            return True
        for item in self._items(group, "layer"):
            if item.data(0, Qt.UserRole)[2] == layer:
                return item.checkState(0) == Qt.Checked
        return True

    def hidden_sets(self, group: str) -> tuple[set, set]:
        hidden_bodies: set = set()
        hidden_regions: set = set()
        for kind in ("part", "cvol", "body"):
            for item in self._items(group, kind):
                if item.checkState(0) != Qt.Checked:
                    bid = item.data(0, Qt.UserRole)[2]
                    if bid is not None:
                        hidden_bodies.add(bid)
        for item in self._items(group, "region"):
            if item.checkState(0) != Qt.Checked:
                frid = item.data(0, Qt.UserRole)[2]
                if frid is not None:
                    hidden_regions.add(frid)
        return hidden_bodies, hidden_regions

    def _emit_visibility(self, group: str) -> None:
        if not group:
            for g in self.groups():
                self._emit_visibility(g)
            return
        hidden_bodies, hidden_regions = self.hidden_sets(group)
        self.visibility_changed.emit(
            group, hidden_bodies, hidden_regions,
            self.group_visible(group))

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, group, value = data[0], data[1], data[2]
        if kind == "layer":
            self.layer_visibility_changed.emit(
                group, value, item.checkState(0) == Qt.Checked)
            return
        if kind == "project":
            self._emit_visibility("")
            return
        if kind in ("group", "part", "cvol", "body", "region"):
            # 零件取消勾选时同步其子 MeshClosedVolume
            if kind == "part":
                self.tree.blockSignals(True)
                state = item.checkState(0)
                for i in range(item.childCount()):
                    ch = item.child(i)
                    cd = ch.data(0, Qt.UserRole)
                    if cd and cd[0] == "cvol" and (ch.flags() & Qt.ItemIsUserCheckable):
                        ch.setCheckState(0, state)
                self.tree.blockSignals(False)
            self._emit_visibility(group)

    def _on_selection(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if not data:
            return
        kind, group, value = data[0], data[1], data[2]
        props: dict = {"节点": kind, "名称": items[0].text(0)}
        if group:
            props["网格组"] = group
        if kind in ("part", "cvol", "body"):
            props["闭体 / body"] = value
        elif kind == "region":
            props["面区域 frid"] = value
        elif kind == "layer":
            props["图层"] = {"oct": "Octree", "gph": "Mesh",
                             "mdl": "Geometry"}.get(value, value)
            props["状态列"] = items[0].text(1)
        elif kind == "fluid":
            props["流体域"] = value
        focus = ""
        if kind == "layer":
            focus = {"oct": "octree", "gph": "mesh"}.get(value, "")
        elif kind in ("part", "cvol", "body", "region"):
            focus = "geometry"
        self.item_selected.emit(props)
        if group:
            self.status_requested.emit(group, focus)

    def _context_menu(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu

        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, group, value = data[0], data[1], data[2]
        if not group and self.groups():
            group = self.groups()[0]
        menu = QMenu(self)
        act_only = menu.addAction("仅显示此项")
        act_hide = menu.addAction("隐藏此项")
        menu.addSeparator()
        act_all = menu.addAction("显示全部")
        act_none = menu.addAction("隐藏全部")
        menu.addSeparator()
        act_oct_info = menu.addAction("显示八叉树信息")
        act_mesh_info = menu.addAction("显示体网格信息")
        act_geo_info = menu.addAction("显示几何信息")
        act_sel_mesh = menu.addAction("选择体网格视图")
        menu.addSeparator()
        act_3d = menu.addAction("在 3D 中查看")
        act = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act is act_only:
            self._set_only(item, group)
        elif act is act_hide:
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(0, Qt.Unchecked)
        elif act is act_all:
            self._set_all(group, True)
        elif act is act_none:
            self._set_all(group, False)
        elif act is act_oct_info:
            self.status_requested.emit(group, "octree")
        elif act is act_mesh_info:
            self.status_requested.emit(group, "mesh")
        elif act is act_geo_info:
            self.status_requested.emit(group, "geometry")
        elif act is act_sel_mesh:
            self.select_mesh.emit(group)
        elif act is act_3d:
            self.focus_3d.emit(group)

    def _set_only(self, item: QTreeWidgetItem, group: str) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] in ("project", "group", "parts_root"):
            self._set_all(group, True)
            return
        if data[0] == "layer":
            self.tree.blockSignals(True)
            for other in self._items(group, "layer"):
                other.setCheckState(
                    0, Qt.Checked if other is item else Qt.Unchecked)
            self.tree.blockSignals(False)
            self.layer_visibility_changed.emit(group, data[2], True)
            for other in self._items(group, "layer"):
                if other is not item:
                    self.layer_visibility_changed.emit(
                        group, other.data(0, Qt.UserRole)[2], False)
            return
        if data[0] not in ("part", "cvol", "body", "region"):
            return
        self.tree.blockSignals(True)
        kind, _, value = data
        targets = (self._items(group, "part") + self._items(group, "cvol")
                   + self._items(group, "body") + self._items(group, "region"))
        for other in targets:
            od = other.data(0, Qt.UserRole)
            match = od[0] == kind and od[2] == value
            other.setCheckState(0, Qt.Checked if match else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._on_item_changed(item, 0)

    def _set_all(self, group: str, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        groups = [group] if group else self.groups()
        self.tree.blockSignals(True)
        proj = self._project_item()
        if proj is not None:
            proj.setCheckState(0, state)
        for g in groups:
            for item in (self._items(g, "group")
                         + self._items(g, "part")
                         + self._items(g, "cvol")
                         + self._items(g, "body")
                         + self._items(g, "region")
                         + self._items(g, "layer")):
                if item.flags() & Qt.ItemIsUserCheckable and (
                        item.flags() & Qt.ItemIsEnabled):
                    # Octree 默认仍保持关：仅在「显示全部」时打开 Mesh，不强制开 Octree
                    if (not checked) or item.data(0, Qt.UserRole)[2] != "oct":
                        item.setCheckState(0, state)
                    if checked and item.data(0, Qt.UserRole)[0] == "layer" \
                            and item.data(0, Qt.UserRole)[2] == "oct":
                        item.setCheckState(0, Qt.Unchecked)
        self.tree.blockSignals(False)
        for g in groups:
            self._emit_visibility(g)
            for item in self._items(g, "layer"):
                if item.flags() & Qt.ItemIsEnabled:
                    self.layer_visibility_changed.emit(
                        g, item.data(0, Qt.UserRole)[2],
                        item.checkState(0) == Qt.Checked)


class DashboardTab(QWidget):
    """文件格式数据看板：归档/网格/八叉树/面片/快照/Parasolid 卡片。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(8, 8, 8, 8)
        title = QLabel("PPH 格式数据看板", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.root.addWidget(title)
        self.msg = QLabel("打开 .pph 后自动填充；深度统计需点击刷新。", self)
        self.root.addWidget(self.msg)
        self.cards = QGridLayout()
        self.cards.setHorizontalSpacing(8)
        self.cards.setVerticalSpacing(8)
        self.root.addLayout(self.cards)
        self.chart_title = QLabel("成员大小分布（Top 12）", self)
        self.chart_title.setStyleSheet("font-weight: bold; margin-top: 6px;")
        self.root.addWidget(self.chart_title)
        self.chart = BarChart(self)
        self.chart.setMinimumHeight(300)
        self.root.addWidget(self.chart, 1)
        self.btn_deep = QPushButton("刷新深度统计（GPH/OCT/Parasolid）", self)
        self.btn_deep.clicked.connect(self.refresh_deep)
        self.root.addWidget(self.btn_deep)
        self._cards: dict[str, QLabel] = {}
        self._viewer: Optional[object] = None

    def _add_card(self, key: str, caption: str) -> QLabel:
        card = QFrame(self)
        card.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(card)
        v.setContentsMargins(8, 6, 8, 6)
        v.addWidget(QLabel(caption, card))
        value = QLabel("—", card)
        value.setStyleSheet("font-size: 18px; font-weight: bold;")
        value.setWordWrap(True)
        v.addWidget(value)
        v.addStretch(1)
        row, col = divmod(len(self._cards), 4)
        self.cards.addWidget(card, row, col)
        self._cards[key] = value
        return value

    def set_viewer(self, viewer) -> None:
        self._viewer = viewer

    def populate(self) -> None:
        """用快速统计填充看板（归档/文本/快照/MDL 轻量）。"""
        viewer = self._viewer
        if viewer is None or viewer.arch is None:
            self.msg.setText("请先打开 .pph 文件")
            return
        arch = viewer.arch
        # 清空旧卡片布局（避免重复 populate 叠加）
        while self.cards.count():
            item = self.cards.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards.clear()
        for key, caption in [
                ("archive", "归档"),
                ("compression", "压缩率"),
                ("gph", "体网格 GPH"),
                ("oct", "八叉树 OCT"),
                ("mdl", "面片几何 MDL"),
                ("snapshot", "快照"),
                ("parasolid", "Parasolid"),
                ("text", "文本成员")]:
            self._add_card(key, caption)
        sizes = [m.size for m in arch.members]
        comp = [m.compress_size for m in arch.members]
        self._cards["archive"].setText(
            f"{len(arch.members)} 成员\n{_fmt_size(sum(sizes))}")
        ratio = (sum(sizes) / sum(comp)) if sum(comp) else 0
        self._cards["compression"].setText(f"{ratio:.2f}x\nZIP/deflate")
        # 文本成员
        n_text = sum(1 for m in arch.members
                     if m.role in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                                   pph_parser.ROLE_XENV,
                                   pph_parser.ROLE_PROJECT_XML))
        self._cards["text"].setText(f"{n_text} 个\njs/prp/xenv/xml")
        # 快照
        try:
            snap = viewer.snap
            self._cards["snapshot"].setText(
                f"{len(snap.records)} 记录\n"
                f"未对齐 {snap.skipped_bytes} B" if snap else "—")
            bodies = snap.bodies() if snap else []
            self._cards["parasolid"].setText(f"{len(bodies)} 体")
        except Exception:  # noqa: BLE001
            self._cards["snapshot"].setText("解析失败")
        # 快速二进制统计（轻量）
        try:
            self._quick_gph_mdl_oct(viewer)
        except Exception as exc:  # noqa: BLE001
            self.msg.setText(f"深度统计未完成（点刷新重试）: {exc}")
        # 成员尺寸条形图
        top = sorted(arch.members, key=lambda m: -m.size)[:12]
        colors = pph_vtk.preset_colors(len(top))
        self.chart.set_data(
            [(m.name, m.size, colors[i]) for i, m in enumerate(top)],
            unit=" B")
        self.msg.setText("看板已更新（深度统计为轻量值，可点刷新获取完整值）")

    def _quick_gph_mdl_oct(self, viewer) -> None:
        import gphstats
        import mdl

        gph = octv = None
        part = None
        for m in viewer.arch.members:
            p = viewer.bin_paths.get(m.name)
            if p is None:
                continue
            # 大文件（>64 MiB）跳过深度解析，避免打开卡顿
            if os.path.getsize(p) > 64 * 1024 * 1024:
                self.msg.setText(
                    "检测到大网格文件（>64 MiB），深度统计已跳过；"
                    "可点刷新深度统计获取完整值（耗时较长）")
                continue
            if m.name.lower().endswith(".gph") and gph is None:
                with gphstats.open_buffer(p) as data:
                    s = gphstats.summarize(data)
                gph = s
            elif m.name.lower().endswith(".oct") and octv is None:
                import oct
                octv = oct.parse_oct(p)
            elif m.name.lower().endswith("_part.mdl") and part is None:
                part = mdl.parse_mdl(p, load_arrays=False)
        if gph is not None:
            links = gph["links"] or {}
            self._cards["gph"].setText(
                f"{links.get('n_faces', 0):,} 面\n"
                f"{links.get('n_cells', 0):,} 单元\n"
                f"顶点 {gph['n_vertices']:,}")
        else:
            self._cards["gph"].setText("—")
        if octv is not None:
            self._cards["oct"].setText(
                f"{octv.n_octants:,} 节点\n叶子 {octv.n_leaves:,}")
        else:
            self._cards["oct"].setText("—")
        if part is not None:
            self._cards["mdl"].setText(
                f"{part.n_faces:,} 面\n{part.n_vertices:,} 顶点\n"
                f"闭体 {part.n_closed_volumes} / "
                f"区域 {len(part.surface_regions)}")
        else:
            self._cards["mdl"].setText("—")

    def refresh_deep(self) -> None:
        viewer = self._viewer
        if viewer is None or viewer.arch is None:
            return
        self.msg.setText("正在解析…")
        QApplication.processEvents()
        try:
            self._quick_gph_mdl_oct(viewer)
            # Parasolid 深度统计
            try:
                import parasolid
                if viewer.snap is not None and viewer.snap.bodies():
                    bodies = viewer.snap.decompress_bodies()
                    schemas = set()
                    ents = set()
                    for b in bodies:
                        pt = b["pkbody3"].decrypt()
                        ps = parasolid.parse_transmit(pt)
                        schemas.add(ps.schema)
                        ents.update(ps.entities)
                    self._cards["parasolid"].setText(
                        f"{len(bodies)} 体\n{sorted(schemas)[0]}\n"
                        f"实体 {len(ents)} 类")
            except Exception as exc:  # noqa: BLE001
                self._cards["parasolid"].setText(f"失败: {exc}")
            self.msg.setText("深度统计完成")
        except Exception as exc:  # noqa: BLE001
            self.msg.setText(f"深度统计失败: {exc}")


class TextEditorTab(QWidget):
    """可编辑文本成员视图（跟踪修改，供另存为收集覆盖字节）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = QPlainTextEdit(self)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setFont(QFont("Consolas", 10))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)
        self.current_name: Optional[str] = None
        self._original = ""
        self._buffers: dict[str, str] = {}
        self._originals: dict[str, str] = {}

    def load_member(self, name: str, data: bytes) -> None:
        if self.current_name is not None:
            self._buffers[self.current_name] = self.editor.toPlainText()
        self.current_name = name
        self._original = self._norm(data)
        self._buffers[name] = self._original
        self.editor.setPlainText(self._original)
        self.editor.setReadOnly(False)

    def clear(self) -> None:
        if self.current_name is not None:
            self._buffers[self.current_name] = self.editor.toPlainText()
        self.current_name = None
        self.editor.clear()
        self.editor.setReadOnly(True)

    def overrides(self) -> dict[str, bytes]:
        if self.current_name is not None:
            self._buffers[self.current_name] = self.editor.toPlainText()
        out = {}
        for name, text in self._buffers.items():
            orig = self._originals.get(name)
            if orig is not None and text != orig:
                # xenv 保持 UTF-8 BOM（与 scFLOW 一致）
                if name.endswith(".xenv"):
                    out[name] = ("\ufeff" + text.lstrip("\ufeff")).encode("utf-8")
                else:
                    out[name] = text.encode("utf-8")
        return out

    def set_originals(self, originals: dict[str, bytes]) -> None:
        # 仅跟踪文本成员；切勿对 GPH/OCT/MDL 等二进制做 UTF-8 解码（大文件会卡死）
        text_ext = (".js", ".prp", ".xenv", ".xml", ".txt", ".csv")
        self._originals = {
            n: self._norm(b) for n, b in originals.items()
            if n.lower().endswith(text_ext)
        }

    def set_buffer_text(self, name: str, text: str) -> None:
        """外部写入成员缓冲（如 Condition 面板 Apply xenv）。"""
        norm = text.replace("\r\n", "\n").lstrip("\ufeff")
        self._buffers[name] = norm
        if self.current_name == name:
            self.editor.setPlainText(norm)

    @staticmethod
    def _norm(data: bytes) -> str:
        return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


class SnapshotTab(QWidget):
    """sctsnapshot 记录树 + 摘要。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["记录", "值 / 说明"])
        self.summary = QPlainTextEdit(self)
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.summary, 0)

    def clear(self) -> None:
        self.tree.clear()
        self.summary.clear()

    def load_snapshot(self, snap, bodies_summary: str) -> None:
        self.tree.clear()
        for r in snap.records:
            self._add_record(None, r, 0)
        self.tree.expandToDepth(1)
        self.summary.setPlainText(bodies_summary)

    def _add_record(self, parent, rec, depth: int) -> None:
        if depth > 40:
            return
        text = rec.text(200)
        item = QTreeWidgetItem(parent if parent is not None else self.tree)
        item.setText(0, rec.tag)
        item.setText(1, text[len(rec.tag):].strip(" []") or "")
        item.setData(0, Qt.UserRole, rec.tag)
        for c in rec.children:
            self._add_record(item, c, depth + 1)


class _RubberPolygonOverlay(QWidget):
    """框选多边形叠加层（VTK 坐标 y 向上，绘制时翻转为 Qt 坐标）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[tuple[int, int]] = []
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def set_points(self, points: list[tuple[int, int]]) -> None:
        self._points = list(points)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        pen = QPen(QColor(0, 200, 0), 2, Qt.DashLine)
        painter.setPen(pen)
        h = self.height()
        poly = QPolygon(
            [QPoint(int(x), h - int(y)) for x, y in self._points])
        painter.drawPolyline(poly)
        if len(self._points) >= 3:
            painter.setBrush(QColor(0, 200, 0, 30))
            painter.drawPolygon(poly)


class View3DTab(QWidget):
    """Draw Window：VTK 3D + 几何/网格视图 + 体网格剖切（Cross Section）。"""

    show_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from vtkmodules.qt.QVTKRenderWindowInteractor import (
            QVTKRenderWindowInteractor)

        self.group_box = QComboBox(self)
        self.group_box.currentTextChanged.connect(self._on_group_changed)
        self.chk_mdl_part = QCheckBox("几何 MDL", self)
        self.chk_mdl_part.setChecked(True)
        self.chk_cad = QCheckBox("CAD", self)
        self.chk_cad.setChecked(True)
        self.chk_cad.setToolTip(
            "Import 的 Parasolid .x_t 剖分预览（pskernel facet_2）")
        self.chk_mdl_ridge = QCheckBox("ridge", self)
        self.chk_mdl_ridge.setChecked(False)
        self.chk_oct = QCheckBox("八叉树", self)
        self.chk_oct.setChecked(False)
        self.chk_gph = QCheckBox("体网格", self)
        self.chk_gph.setChecked(True)  # 默认与几何 MDL / 网格线 / 坐标轴一同显示
        self.chk_edges = QCheckBox("网格线", self)
        self.chk_edges.setChecked(True)
        self.chk_edges.setToolTip(
            "面网格（GPH）边线；与几何同时显示时 MDL 只作半透明垫底，不画三角网线")
        self.chk_axes = QCheckBox("坐标轴", self)
        self.chk_axes.setChecked(True)
        self.chk_legend = QCheckBox("图例", self)
        self.chk_legend.setChecked(True)
        self.color_by = QComboBox(self)
        self.color_by.addItems(["frid", "csid"])
        self.view_kind = QComboBox(self)
        self.view_kind.addItems([
            "全部", "仅几何 (MDL)", "仅八叉树", "仅体网格 (GPH)"])
        self.view_kind.currentTextChanged.connect(self.render)
        self.display_mode = QComboBox(self)
        self.display_mode.addItems(["不透明", "半透明", "线框"])
        self.display_mode.setCurrentText("不透明")
        self.display_mode.setToolTip(
            "体网格/几何显示：不透明（默认）· 半透明 · 线框")
        self.display_mode.currentTextChanged.connect(self.render)
        self.chk_gph_color = QCheckBox("GPH owner 着色", self)
        self.chk_gph_color.setChecked(False)
        self.chk_gph_color.setToolTip(
            "默认关闭；勾选后按 owner 单元 ID 着色")
        self.chk_gph_color.toggled.connect(self.render)

        # ── Cross Section（对齐 scFLOW Mesh 页签）──────────────────
        self.chk_section = QCheckBox("剖切", self)
        self.chk_section.toggled.connect(self._on_section_toggled)
        self.section_target = QComboBox(self)
        self.section_target.addItems(["几何/八叉树", "体网格"])
        self.section_target.currentTextChanged.connect(self._on_section_ui)
        self.clip_axis = QComboBox(self)
        self.clip_axis.addItems(["X", "Y", "Z", "自定义 ABC"])
        self.clip_axis.currentIndexChanged.connect(self._on_axis_changed)
        self.clip_slider = QSlider(Qt.Horizontal, self)
        self.clip_slider.setRange(0, 100)
        self.clip_slider.setValue(50)
        self.clip_slider.valueChanged.connect(self._plane_slider_changed)
        self.spin_a = QDoubleSpinBox(self)
        self.spin_b = QDoubleSpinBox(self)
        self.spin_c = QDoubleSpinBox(self)
        self.spin_d = QDoubleSpinBox(self)
        for sp, val in ((self.spin_a, 1.0), (self.spin_b, 0.0),
                        (self.spin_c, 0.0), (self.spin_d, 0.0)):
            sp.setDecimals(6)
            sp.setRange(-1e9, 1e9)
            sp.setValue(val)
            sp.setMaximumWidth(90)
        self.chk_lines_only = QCheckBox("仅截面线", self)
        self.chk_lines_only.setToolTip(
            "Draw only sectional lines（体网格剖切）")
        self.chk_color_cvol = QCheckBox("按闭体着色", self)
        self.chk_color_cvol.setChecked(True)
        self.chk_opposite = QCheckBox("显示反侧", self)
        self.chk_opposite.setToolTip("Opposite side（几何裁剪取反）")
        self.btn_draw_section = QPushButton("Draw 剖切", self)
        self.btn_draw_section.setToolTip(
            "体网格剖切需指定平面后点击 Draw（对齐 scFLOW）")
        self.btn_draw_section.clicked.connect(self._draw_mesh_section)

        self.btn_render = QPushButton("渲染", self)
        self.btn_fit = QPushButton("Fit", self)
        self.btn_reset = QPushButton("Reset", self)
        self.btn_rubber = QPushButton("橡皮框", self)
        self.btn_pick = QPushButton("拾取面", self)
        self.btn_show_all = QPushButton("恢复全部", self)
        self.btn_rubber.setCheckable(True)
        self.btn_pick.setCheckable(True)
        self.btn_render.clicked.connect(self.render)
        self.btn_fit.clicked.connect(self.fit)
        self.btn_reset.clicked.connect(self.reset_viewpoint)
        self.btn_rubber.toggled.connect(self._toggle_rubber_select)
        self.btn_pick.toggled.connect(self._toggle_pick)
        self.btn_show_all.clicked.connect(self.clear_visibility)
        self.status = QLabel("未加载", self)

        panel = QFrame(self)
        panel.setFrameShape(QFrame.StyledPanel)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(6, 4, 6, 4)
        pv.setSpacing(3)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("网格组:", panel))
        row1.addWidget(self.group_box)
        row1.addWidget(QLabel("显示:", panel))
        row1.addWidget(self.display_mode)
        row1.addWidget(QLabel("着色:", panel))
        row1.addWidget(self.color_by)
        row1.addWidget(QLabel("视图:", panel))
        row1.addWidget(self.view_kind)
        row1.addStretch(1)
        for b in (self.btn_render, self.btn_fit, self.btn_reset,
                  self.btn_rubber, self.btn_pick, self.btn_show_all):
            row1.addWidget(b)
        pv.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("图层:", panel))
        for chk in (self.chk_mdl_part, self.chk_cad, self.chk_mdl_ridge,
                    self.chk_oct, self.chk_gph, self.chk_gph_color,
                    self.chk_edges, self.chk_axes, self.chk_legend):
            row2.addWidget(chk)
            if chk is not self.chk_gph_color:
                chk.toggled.connect(self.render)
        row2.addStretch(1)
        pv.addLayout(row2)

        sec = QGroupBox("Cross Section（剖切）", panel)
        sg = QGridLayout(sec)
        sg.setContentsMargins(6, 4, 6, 4)
        sg.addWidget(self.chk_section, 0, 0)
        sg.addWidget(QLabel("对象:"), 0, 1)
        sg.addWidget(self.section_target, 0, 2)
        sg.addWidget(QLabel("轴/平面:"), 0, 3)
        sg.addWidget(self.clip_axis, 0, 4)
        sg.addWidget(QLabel("Plane position:"), 0, 5)
        sg.addWidget(self.clip_slider, 0, 6, 1, 2)
        sg.addWidget(QLabel("A"), 1, 0)
        sg.addWidget(self.spin_a, 1, 1)
        sg.addWidget(QLabel("B"), 1, 2)
        sg.addWidget(self.spin_b, 1, 3)
        sg.addWidget(QLabel("C"), 1, 4)
        sg.addWidget(self.spin_c, 1, 5)
        sg.addWidget(QLabel("D"), 1, 6)
        sg.addWidget(self.spin_d, 1, 7)
        row_opt = QHBoxLayout()
        row_opt.addWidget(self.chk_lines_only)
        row_opt.addWidget(self.chk_color_cvol)
        row_opt.addWidget(self.chk_opposite)
        row_opt.addWidget(self.btn_draw_section)
        row_opt.addStretch(1)
        sg.addLayout(row_opt, 2, 0, 1, 8)
        pv.addWidget(sec)

        # VTK 容器：勿设 WA_NativeWindow（最大化后 HWND 易盖住右侧图例变黑）
        self._vtk_host = QFrame(self)
        self._vtk_host.setObjectName("VtkHost")
        self._vtk_host.setAutoFillBackground(True)
        self._vtk_host.setAttribute(Qt.WA_StyledBackground, True)
        self._vtk_host.setStyleSheet(
            "#VtkHost { background: #d8d8d8; border: none; }")
        host_lay = QVBoxLayout(self._vtk_host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        host_lay.setSpacing(0)
        self.vtk_widget = QVTKRenderWindowInteractor(self._vtk_host)
        self.vtk_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        host_lay.addWidget(self.vtk_widget, 1)

        self.renderer = pph_vtk.make_renderer([])
        self.renderer.GetActiveCamera().ParallelProjectionOn()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self._started = False

        # 图例放独立侧栏（白底），与 VTK 宿主分离，避免被 OpenGL 窗盖住
        self._legend_host = QFrame(self)
        self._legend_host.setObjectName("LegendHost")
        self._legend_host.setFixedWidth(188)
        self._legend_host.setAutoFillBackground(True)
        self._legend_host.setAttribute(Qt.WA_StyledBackground, True)
        pal = self._legend_host.palette()
        pal.setColor(QPalette.Window, QColor(255, 255, 255))
        self._legend_host.setPalette(pal)
        self._legend_host.setStyleSheet(
            "#LegendHost { background-color: #ffffff;"
            " border-left: 1px solid #9a9a9a; }")
        leg_lay = QVBoxLayout(self._legend_host)
        leg_lay.setContentsMargins(4, 4, 4, 4)
        self.legend = LegendPanel(self._legend_host)
        leg_lay.addWidget(self.legend, 1)
        self._legend_host.setVisible(False)

        self._orientation = None
        self._rubber_style = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._sync_vtk_viewport)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(panel)
        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(self._vtk_host, 1)
        hbox.addWidget(self._legend_host, 0)
        layout.addLayout(hbox, 1)
        self.status.setAutoFillBackground(True)
        self.status.setMinimumHeight(22)
        self.status.setMaximumHeight(40)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.groups: dict[str, dict] = {}
        self._cad_meshes: list = []  # cad_import.ImportedBody / TessPart
        self._mdl_filter: Optional[dict] = None
        self._pickable_actors: list = []
        self._pickable_meta: dict = {}  # actor -> {group, kind, path}
        self._pick_mode: str = "face"  # face|part|edge|vertex
        self._rubber_kind: str = "box"  # box|circle|polygon
        self._rubber_active: bool = False
        self._rubber_origin: Optional[QPoint] = None
        self._rubber_band: Optional[QRubberBand] = None
        self._rubber_style: Optional[object] = None
        self._rubber_center_cache: dict = {}
        self.last_pick: Optional[dict] = None
        self.picked_faces: list = []   # P5-3：面拾取累计（注册区域多面引用）
        self._picked_status = ""
        self._cache: dict[tuple, object] = {}
        self._hidden: dict[str, tuple[set, set]] = {}
        self._group_hidden: set[str] = set()
        self._layer_hidden: dict[str, set[str]] = {}
        self._mesh_section_pd = None  # Draw 后缓存的截面
        self._mesh_section_dirty = True
        self._bounds_cache: Optional[tuple] = None
        self._vtk_ok = True
        self._on_section_ui()

    def _sync_vtk_viewport(self) -> None:
        """把 Qt 控件尺寸同步到 VTK RenderWindow（最大化/缩放后必须）。"""
        if not self._started or not self._vtk_ok:
            return
        try:
            # 仅用 VTK 宿主尺寸，绝不包含右侧图例宽度
            w = max(1, self._vtk_host.width())
            h = max(1, self._vtk_host.height())
            self.vtk_widget.resize(w, h)
            rw = self.vtk_widget.GetRenderWindow()
            rw.SetSize(w, h)
            self.vtk_widget.update()
            self._vtk_host.update()
            # 图例侧栏置顶重绘，避免被 OpenGL 窗盖成黑块
            if self._legend_host.isVisible():
                self._legend_host.raise_()
                self._legend_host.repaint()
                self.legend.repaint()
            rw.Render()
        except Exception:  # noqa: BLE001
            self._vtk_ok = False

    def _safe_vtk_render(self) -> None:
        if not self._started or not self._vtk_ok:
            return
        try:
            w = max(1, self._vtk_host.width())
            h = max(1, self._vtk_host.height())
            self.vtk_widget.resize(w, h)
            rw = self.vtk_widget.GetRenderWindow()
            cur = rw.GetSize()
            if int(cur[0]) != w or int(cur[1]) != h:
                rw.SetSize(w, h)
            rw.Render()
            if self._legend_host.isVisible():
                self._legend_host.raise_()
                self.legend.update()
        except Exception:  # noqa: BLE001
            self._vtk_ok = False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 防抖：最大化动画结束后再同步 VTK，避免残影/重叠
        self._resize_timer.start(30)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        if not self._started:
            self._started = True
            try:
                from vtkmodules.vtkInteractionStyle import (
                    vtkInteractorStyleTrackballCamera)
                self._trackball_style = vtkInteractorStyleTrackballCamera()
                iren = self.vtk_widget.GetRenderWindow().GetInteractor()
                iren.SetInteractorStyle(self._trackball_style)
                iren.Initialize()
                # VTK 抢先收到按键时的备份路径（与 Qt shortcut 互补）
                if not getattr(self, "_view_key_obs", False):
                    iren.AddObserver(
                        "KeyPressEvent", self._on_vtk_key_press)
                    self._view_key_obs = True
            except Exception:  # noqa: BLE001
                pass
            self._sync_vtk_viewport()
            if self.groups:
                self.render()
        else:
            QTimer.singleShot(0, self._sync_vtk_viewport)

    def _on_vtk_key_press(self, obj, _event) -> None:
        try:
            sym = (obj.GetKeySym() or "").lower()
            shift = bool(obj.GetShiftKey())
        except Exception:  # noqa: BLE001
            return
        if sym.startswith("shift_"):
            return
        self.dispatch_view_key(sym, shift=shift)

    def set_groups(self, groups: dict[str, dict]) -> None:
        self.groups = groups
        self._mesh_section_pd = None
        self._mesh_section_dirty = True
        self._layer_hidden.clear()
        # 打开工程默认：几何 + 体网格 + 网格线 + 坐标轴
        self.chk_mdl_part.setChecked(True)
        self.chk_cad.setChecked(True)
        self.chk_gph.setChecked(True)
        self.chk_edges.setChecked(True)
        self.chk_axes.setChecked(True)
        self.chk_oct.setChecked(False)
        self.chk_gph_color.setChecked(False)
        self.group_box.blockSignals(True)
        self.group_box.clear()
        self.group_box.addItems(sorted(groups))
        self.group_box.blockSignals(False)
        if groups:
            self.group_box.setCurrentIndex(0)
            # 窗口未 show 前不触发 VTK Render（无 GL/offscreen 会崩）
            if self._started:
                self.render()
        elif self._cad_meshes and self._started:
            self.render()

    def set_cad_meshes(self, bodies: list, *, append: bool = False) -> None:
        """设置 Import .x_t 剖分结果（cabdecoding TessPart 列表）。"""
        items = []
        for b in bodies or []:
            tess = getattr(b, "tess", b)
            if tess is None:
                continue
            items.append(tess)
        if append:
            self._cad_meshes.extend(items)
        else:
            self._cad_meshes = items
        if self._started:
            self.render()
            if self._cad_meshes:
                self.fit()

    def select_group(self, name: str) -> None:
        if name in self.groups:
            self.group_box.setCurrentText(name)

    def set_view_mode(self, mode: str) -> None:
        """mode: all|geometry|octree|mesh"""
        mapping = {
            "all": "全部",
            "geometry": "仅几何 (MDL)",
            "octree": "仅八叉树",
            "mesh": "仅体网格 (GPH)",
        }
        text = mapping.get(mode, mode)
        idx = self.view_kind.findText(text)
        if idx >= 0:
            self.view_kind.setCurrentIndex(idx)

    def _on_group_changed(self, _name: str) -> None:
        self._mesh_section_pd = None
        self._mesh_section_dirty = True
        self.render()

    def _on_section_toggled(self, checked: bool) -> None:
        if not checked:
            self._mesh_section_pd = None
        self._on_section_ui()
        if self._started:
            self.render()

    def _on_section_ui(self, *_args) -> None:
        mesh_mode = self.section_target.currentText() == "体网格"
        self.chk_lines_only.setEnabled(mesh_mode)
        self.chk_color_cvol.setEnabled(mesh_mode)
        self.btn_draw_section.setEnabled(
            self.chk_section.isChecked() and mesh_mode)
        self.chk_opposite.setEnabled(
            self.chk_section.isChecked() and not mesh_mode)
        custom = self.clip_axis.currentText() == "自定义 ABC"
        for sp in (self.spin_a, self.spin_b, self.spin_c):
            sp.setEnabled(custom or mesh_mode)
        self.spin_d.setEnabled(True)

    def _on_axis_changed(self, *_args) -> None:
        self._sync_abcd_from_axis()
        self._on_section_ui()
        self._plane_slider_changed()

    def _sync_abcd_from_axis(self) -> None:
        axis = self.clip_axis.currentText()
        if axis == "自定义 ABC":
            return
        a = b = c = 0.0
        if axis == "X":
            a = 1.0
        elif axis == "Y":
            b = 1.0
        else:
            c = 1.0
        self.spin_a.blockSignals(True)
        self.spin_b.blockSignals(True)
        self.spin_c.blockSignals(True)
        self.spin_a.setValue(a)
        self.spin_b.setValue(b)
        self.spin_c.setValue(c)
        self.spin_a.blockSignals(False)
        self.spin_b.blockSignals(False)
        self.spin_c.blockSignals(False)
        self._update_d_from_slider()

    def _plane_slider_changed(self, *_args) -> None:
        self._update_d_from_slider()
        self._mesh_section_dirty = True
        if not self.chk_section.isChecked():
            return
        if self.section_target.currentText() == "体网格":
            # 对齐 scFLOW：体网格需 Draw，仅更新 D
            self.status.setText(
                "平面已更新 — 点击「Draw 剖切」刷新体网格截面")
            return
        self.render()

    def _update_d_from_slider(self) -> None:
        bounds = self._bounds_cache
        if bounds is None:
            return
        axis = self.clip_axis.currentText()
        frac = self.clip_slider.value() / 100.0
        if axis == "X":
            d = bounds[0] + frac * (bounds[1] - bounds[0])
        elif axis == "Y":
            d = bounds[2] + frac * (bounds[3] - bounds[2])
        elif axis == "Z":
            d = bounds[4] + frac * (bounds[5] - bounds[4])
        else:
            # 自定义：沿法向在包围盒中心附近平移
            import numpy as np
            n = np.array([self.spin_a.value(), self.spin_b.value(),
                          self.spin_c.value()], dtype=float)
            nn = float(np.linalg.norm(n)) or 1.0
            n /= nn
            center = np.array([(bounds[0] + bounds[1]) * 0.5,
                               (bounds[2] + bounds[3]) * 0.5,
                               (bounds[4] + bounds[5]) * 0.5])
            # 投影范围
            corners = np.array([
                [bounds[i], bounds[j], bounds[k]]
                for i in (0, 1) for j in (2, 3) for k in (4, 5)])
            projs = corners @ n
            d = float(projs.min() + frac * (projs.max() - projs.min()))
        self.spin_d.blockSignals(True)
        self.spin_d.setValue(d)
        self.spin_d.blockSignals(False)

    def _current_plane(self):
        return pph_vtk.plane_from_abcd(
            self.spin_a.value(), self.spin_b.value(),
            self.spin_c.value(), self.spin_d.value())

    def _draw_mesh_section(self) -> None:
        """体网格剖切 Draw：对含内部面的 GPH 执行 vtkCutter。"""
        name = self.group_box.currentText()
        group = self.groups.get(name)
        if not group or not group.get("gph"):
            self.status.setText("当前组无 GPH，无法剖切体网格")
            return
        try:
            import gphstats
            import numpy as np

            path = group["gph"]
            aux = self._gph_aux(path)
            mesh = aux["mesh"]
            mdl_model = self._mdl_model_for_group(group, name)
            face_mask = self._gph_visibility_mask(aux, name, mdl_model)
            face_scalars = None
            if self.chk_color_cvol.isChecked():
                cvol = aux.get("cvol")
                if cvol is not None and cvol.size:
                    owner = mesh["owner"]
                    face_scalars = np.zeros(mesh["n_faces"], dtype=np.float64)
                    valid = (owner >= 0) & (owner < cvol.size)
                    face_scalars[valid] = cvol[owner[valid]]
            pd = pph_vtk.gph_faces_mesh(
                mesh, max_faces=DEFAULT_CAPS["gph"] * 3,
                boundary_only=False, face_scalars=face_scalars,
                face_mask=face_mask)
            plane = self._current_plane()
            self._mesh_section_pd = pph_vtk.cut_polydata(pd, plane)
            self._mesh_section_dirty = False
            n = self._mesh_section_pd.GetNumberOfCells()
            self.status.setText(f"体网格剖切完成：截面单元 {n:,}")
            if self._started:
                self.render()
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"体网格剖切失败: {exc}")

    @staticmethod
    def _region_annotations(model) -> Optional[dict]:
        ann: dict[int, str] = {}
        for r in model.surface_regions:
            if r.name.startswith("@"):
                continue
            ann.setdefault(r.index, r.name)
        return ann or None

    def _cached(self, key: tuple, build) -> object:
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def _surface_opacity(self, kind: str) -> float:
        """按显示模式返回表面不透明度（线框时仍给 1.0）。"""
        mode = self.display_mode.currentText()
        if mode == "线框" or mode == "不透明":
            return 1.0
        # 半透明
        if kind == "gph":
            return 0.45
        if kind == "ridge":
            return 0.65
        return 0.7  # mdl

    def _gph_and_mdl_overlap(self, group_name: str) -> bool:
        """几何与体网格是否将同时显示（需叠层消花策略）。"""
        mdl_on = (self._layer_visible("mdl", group_name)
                  and self.chk_mdl_part.isChecked())
        gph_on = (self._layer_visible("gph", group_name)
                  and self.chk_gph.isChecked())
        return bool(mdl_on and gph_on)

    def _part_tree_filtered(self, group_name: Optional[str]) -> bool:
        """Part Tree 是否隐藏了部分闭体/面区域（勾选过滤中）。"""
        if not group_name:
            return False
        if group_name in self._group_hidden:
            return True
        hidden_bodies, hidden_regions = self._hidden.get(
            group_name, (set(), set()))
        return bool(hidden_bodies or hidden_regions)

    def _make_actor(self, kind: str, group: dict,
                    group_name: Optional[str] = None,
                    overlap_mesh: bool = False) -> Optional[LayerRender]:
        cap = DEFAULT_CAPS.get(kind, DEFAULT_CAPS["mdl"])
        try:
            if kind in ("mdl", "ridge"):
                key = "part" if kind == "mdl" else "ridge"
                path = group.get(key)
                if not path:
                    return None
                import mdl
                model = self._cached((kind, path), lambda: mdl.parse_mdl(path))
                mask = self._mdl_mask(model, group_name)
                pd = pph_vtk.mdl_mesh(
                    model, color_by=self.color_by.currentText(),
                    max_faces=cap, face_mask=mask)
                if (self.chk_section.isChecked()
                        and self.section_target.currentText() == "几何/八叉树"
                        and pd.GetNumberOfCells() > 0):
                    plane = self._current_plane()
                    pd = pph_vtk.clip_polydata(
                        pd, plane, inside_out=self.chk_opposite.isChecked())
                discrete = self.color_by.currentText() == "frid"
                ann = self._region_annotations(model) if discrete else None
                legend_entries = None
                if ann:
                    vals = sorted(ann)
                    colors = pph_vtk.preset_colors(len(vals))
                    legend_entries = [
                        (ann[v], colors[i]) for i, v in enumerate(vals)]
                wire = self.display_mode.currentText() == "线框"
                # 与体网格同显：MDL 仅半透明垫底，网格线留给 GPH 面网格
                if overlap_mesh and not wire:
                    opacity = 0.22
                    bias = "back"
                else:
                    opacity = self._surface_opacity(kind)
                    bias = "mid"
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=opacity,
                                           wireframe=wire,
                                           discrete=discrete,
                                           annotations=ann,
                                           depth_bias=bias),
                    f"MDL {key}", ann, edges=False,
                    legend_entries=legend_entries)
            if kind == "oct":
                path = group.get("oct")
                if not path:
                    return None
                import oct
                om = self._cached(("oct", path), lambda: oct.parse_oct(path))
                pd = pph_vtk.oct_leaves(om, max_leaves=cap)
                if (self.chk_section.isChecked()
                        and self.section_target.currentText() == "几何/八叉树"
                        and pd.GetNumberOfCells() > 0):
                    plane = self._current_plane()
                    pd = pph_vtk.clip_polydata(
                        pd, plane, inside_out=self.chk_opposite.isChecked())
                # 八叉树默认线框 + 单色（类似体网格风格），关闭深度彩虹着色以免花屏
                oct_color = (0.42, 0.36, 0.86)  # 紫蓝，区别于 GPH 灰青
                actor = pph_vtk.polydata_actor(
                    pd, wireframe=True, color=oct_color, opacity=1.0,
                    depth_bias="mid")
                actor.GetMapper().ScalarVisibilityOff()
                prop = actor.GetProperty()
                prop.SetLineWidth(1.2)
                prop.SetAmbient(1.0)
                prop.SetDiffuse(0.0)
                prop.LightingOff()
                return LayerRender(
                    actor, "OCT", edges=False,
                    legend_entries=[("octree", oct_color)])
            if kind == "gph":
                path = group.get("gph")
                if not path:
                    return None
                aux = self._gph_aux(path)
                mdl_model = self._mdl_model_for_group(group, group_name)
                face_mask = self._gph_visibility_mask(
                    aux, group_name, mdl_model)
                # 掩码随树勾选变化，不能缓存过滤后的 polydata。
                # Part Tree 过滤时不能只用外边界：rotation1 等旋转域的
                # @PartSurface 多为与流体的交界面（internal），boundary_only
                # 会把环面网格几乎滤光，只剩叶轮附近边界。
                if face_mask is not None:
                    pd = pph_vtk.gph_faces_mesh(
                        aux["mesh"], max_faces=max(cap, 800_000),
                        boundary_only=False, face_mask=face_mask)
                else:
                    pd = pph_vtk.gph_boundary_mesh(
                        aux["mesh"], max_faces=cap, face_mask=face_mask)
                opacity = self._surface_opacity("gph")
                wire = self.display_mode.currentText() == "线框"
                color_by_owner = self.chk_gph_color.isChecked()
                # 叠层时体网格在中层；网格线再前移
                bias = "mid" if overlap_mesh else "mid"
                if color_by_owner:
                    actor = pph_vtk.polydata_actor(
                        pd, opacity=opacity, wireframe=wire,
                        depth_bias=bias)
                    return LayerRender(actor, "GPH owner", edges=not wire)
                actor = pph_vtk.polydata_actor(
                    pd, opacity=opacity, wireframe=wire,
                    color=(0.72, 0.76, 0.82), depth_bias=bias)
                actor.GetMapper().ScalarVisibilityOff()
                return LayerRender(
                    actor, "GPH", edges=not wire,
                    legend_entries=[("mesh", (0.72, 0.76, 0.82))])
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"{kind} 渲染失败: {exc}")
            return None
        return None

    def render(self) -> None:
        name = self.group_box.currentText()
        group = self.groups.get(name)
        if not self._started:
            # 仅更新状态文案，避免无 GL 时组装 actor/Render 崩溃
            if not group and not self._cad_meshes:
                self.status.setText("无网格组数据")
            else:
                self.status.setText(f"组 {name or 'CAD'}：待显示窗口后渲染")
            return
        self.renderer.RemoveAllViewProps()
        if self._orientation is not None:
            try:
                self._orientation.SetEnabled(0)
            except Exception:  # noqa: BLE001
                pass
            self._orientation = None
        if not group and not self._cad_meshes:
            self.status.setText("无网格组数据")
            self._safe_vtk_render()
            return

        mesh_section = (self.chk_section.isChecked()
                        and self.section_target.currentText() == "体网格")
        lines_only = mesh_section and self.chk_lines_only.isChecked()
        tree_filtered = self._part_tree_filtered(name) if group else False
        # 体网格开着时始终叠层：MDL 垫底，网格线只来自 GPH 面网格
        overlap = (bool(group) and self._gph_and_mdl_overlap(name)
                   and not lines_only)

        layers: list[tuple[str, Optional[LayerRender]]] = []
        self._pickable_actors = []
        self._pickable_meta = {}
        # 绘制顺序：CAD → MDL → GPH → 网格线
        if self.chk_cad.isChecked() and self._cad_meshes and not lines_only:
            for tess in self._cad_meshes:
                try:
                    pd = pph_vtk.tris_to_polydata(
                        tess.points, tess.triangles)
                except Exception:  # noqa: BLE001
                    pd = None
                if pd is None:
                    continue
                actor = pph_vtk.polydata_actor(
                    pd, opacity=0.95, color=(0.35, 0.75, 0.45),
                    depth_bias="back")
                tname = getattr(tess, "name", "CAD") or "CAD"
                layers.append((
                    f"CAD {tname}",
                    LayerRender(actor=actor, title=tname,
                                legend_entries=[], edges=False)))
        # 绘制顺序：MDL（后）→ GPH（中）→ 网格线（前，后面单独加）
        if group and (self._layer_visible("mdl", name)
                      and self.chk_mdl_part.isChecked() and not lines_only):
            layers.append(
                ("MDL part",
                 self._make_actor("mdl", group, name, overlap_mesh=overlap)))
        if group and (self._layer_visible("ridge", name)
                      and self.chk_mdl_ridge.isChecked() and not lines_only):
            layers.append(
                ("MDL ridge",
                 self._make_actor("ridge", group, name, overlap_mesh=overlap)))
        if group and (self._layer_visible("oct", name)
                      and self.chk_oct.isChecked() and not lines_only):
            layers.append(("OCT", self._make_actor("oct", group)))
        if group and (self._layer_visible("gph", name)
                      and self.chk_gph.isChecked() and not lines_only):
            layers.append(
                ("GPH",
                 self._make_actor("gph", group, name, overlap_mesh=overlap)))

        mode = self.display_mode.currentText()
        wireframe = mode == "线框"
        legend_layers = []
        cells = []
        edge_actors = []
        for label, layer in layers:
            if layer is None:
                continue
            prop = layer.actor.GetProperty()
            if label == "OCT":
                # 八叉树始终线框，不受全局「不透明」显示模式改成实体面
                prop.SetRepresentationToWireframe()
                prop.SetOpacity(1.0)
                prop.SetLineWidth(1.2)
            elif wireframe:
                prop.SetRepresentationToWireframe()
                prop.SetOpacity(1.0)
            else:
                prop.SetRepresentationToSurface()
                if label == "GPH":
                    # 勾选过滤后不透明面网格，边线才是「面网格网格线」
                    if tree_filtered:
                        prop.SetOpacity(0.55 if mode == "半透明" else 1.0)
                    else:
                        prop.SetOpacity(0.45 if mode == "半透明" else 1.0)
                elif label.startswith("MDL"):
                    if overlap:
                        # 叠层策略：几何半透明垫底，避免与体网格花屏
                        prop.SetOpacity(0.22)
                        try:
                            prop.SetOpacityForceOpaque(False)
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        prop.SetOpacity(0.7 if mode == "半透明" else 1.0)
            self.renderer.AddActor(layer.actor)
            if label in ("MDL part", "MDL ridge"):
                self._pickable_actors.append(layer.actor)
                kind = "ridge" if label == "MDL ridge" else "mdl"
                path_key = "ridge" if kind == "ridge" else "part"
                self._pickable_meta[layer.actor] = {
                    "group": name, "kind": kind,
                    "path": (group or {}).get(path_key),
                }
            mapper = layer.actor.GetMapper()
            cells.append(f"{label}={mapper.GetInput().GetNumberOfCells():,}")
            lut = mapper.GetLookupTable()
            legend_layers.append((layer.title, lut, layer.legend_entries))
            # 仅体网格（GPH）叠加面网格线
            if self.chk_edges.isChecked() and layer.edges and not wireframe:
                edge_actors.append(
                    pph_vtk.edges_actor(mapper.GetInput()))
        for ea in edge_actors:
            self.renderer.AddActor(ea)

        # 体网格截面线（需先 Draw）
        if mesh_section and self._mesh_section_pd is not None:
            cut = self._mesh_section_pd
            if cut.GetNumberOfCells() > 0:
                actor = pph_vtk.polydata_actor(
                    cut, opacity=1.0, discrete=self.chk_color_cvol.isChecked())
                actor.GetProperty().SetLineWidth(2.0)
                actor.GetProperty().SetRepresentationToSurface()
                self.renderer.AddActor(actor)
                cells.append(f"截面={cut.GetNumberOfCells():,}")
                legend_layers.append(
                    ("截面 cvol" if self.chk_color_cvol.isChecked()
                     else "截面", actor.GetMapper().GetLookupTable(), None))

        if self.chk_legend.isChecked() and legend_layers:
            self.legend.set_layers(legend_layers)
            self._legend_host.setVisible(True)
            self._legend_host.raise_()
        else:
            self.legend.clear()
            self.legend.setVisible(False)
            self._legend_host.setVisible(False)
        if self.chk_axes.isChecked() and self._vtk_ok:
            try:
                self._orientation = pph_vtk.orientation_marker_widget(
                    self.vtk_widget.GetRenderWindow().GetInteractor())
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"坐标轴失败: {exc}")

        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        # 缓存包围盒供 Plane position
        try:
            b = self.renderer.ComputeVisiblePropBounds()
            if b[1] >= b[0]:
                self._bounds_cache = tuple(b)
                if not self.chk_section.isChecked():
                    self._update_d_from_slider()
        except Exception:  # noqa: BLE001
            pass
        self._safe_vtk_render()
        extra = ""
        if mesh_section and self._mesh_section_pd is None:
            extra = " | 体网格剖切：设置平面后点 Draw"
        elif mesh_section and self._mesh_section_dirty:
            extra = " | 平面已变，需重新 Draw"
        if overlap and not wireframe:
            extra += " | 叠层：MDL 半透明垫底，面网格线来自 GPH"
        elif tree_filtered and not wireframe:
            extra += " | 勾选过滤：显示对应 GPH 面网格线"
        self.status.setText(
            f"组 {name}：{', '.join(cells) if cells else '无可用几何'}"
            + (self._picked_status or "") + extra)

    def precache(self, group_models: dict) -> None:
        for _g, info in group_models.items():
            model = info.get("part")
            path = info.get("part_path")
            if model is not None and path:
                self._cache[("mdl", path)] = model

    def _layer_visible(self, kind: str, group: Optional[str] = None) -> bool:
        mode = self.view_kind.currentText()
        if mode == "仅几何 (MDL)":
            if kind not in ("mdl", "ridge"):
                return False
        elif mode == "仅八叉树":
            if kind != "oct":
                return False
        elif mode == "仅体网格 (GPH)":
            if kind != "gph":
                return False
        layer_key = {"mdl": "mdl", "ridge": "mdl", "oct": "oct",
                     "gph": "gph"}.get(kind, kind)
        if group and layer_key in self._layer_hidden.get(group, set()):
            return False
        return True

    def set_layer_visibility(self, group: str, layer: str,
                             visible: bool, *, refresh: bool = True) -> None:
        hidden = self._layer_hidden.setdefault(group, set())
        if visible:
            hidden.discard(layer)
        else:
            hidden.add(layer)
        # 同步工具栏勾选（当前组）
        if group == self.group_box.currentText():
            mapping = {"mdl": self.chk_mdl_part, "oct": self.chk_oct,
                       "gph": self.chk_gph}
            chk = mapping.get(layer)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(visible)
                chk.blockSignals(False)
        if refresh:
            self.render()

    def _mdl_mask(self, model, group: Optional[str] = None) -> Optional[object]:
        import numpy as np
        if model.n_faces == 0:
            return None
        if self._mdl_filter:
            kind = self._mdl_filter.get("kind")
            value = self._mdl_filter.get("value")
            if kind == "face":
                mask = np.zeros(model.n_faces, dtype=bool)
                if isinstance(value, int) and 0 <= value < model.n_faces:
                    mask[value] = True
                return mask
            if kind == "faces":
                values = [v for v in (self._mdl_filter.get("values") or [])
                          if isinstance(v, int) and 0 <= v < model.n_faces]
                if not values:
                    return np.zeros(model.n_faces, dtype=bool)
                mask = np.zeros(model.n_faces, dtype=bool)
                mask[values] = True
                return mask
            if kind == "body":
                b1, b2 = model.csid
                if b2.size:
                    return (b1 == value) | (b2 == value)
                return None
            if kind == "bodies":
                values = [v for v in (self._mdl_filter.get("values") or [])
                          if isinstance(v, int)]
                b1, b2 = model.csid
                if b2.size and values:
                    return (np.isin(b1, values) | np.isin(b2, values))
                return None
            if kind == "region":
                return model.frid == value
            return None
        if group is not None and group in self._group_hidden:
            return np.zeros(model.n_faces, dtype=bool)
        hidden_bodies, hidden_regions = self._hidden.get(
            group, (set(), set())) if group else (set(), set())
        if not hidden_bodies and not hidden_regions:
            return None
        mask = np.ones(model.n_faces, dtype=bool)
        if hidden_bodies:
            b1, b2 = model.csid
            if b2.size:
                ids = list(hidden_bodies)
                mask &= ~(np.isin(b1, ids) | np.isin(b2, ids))
        if hidden_regions:
            mask &= ~np.isin(model.frid, list(hidden_regions))
        return mask

    def _gph_aux(self, path: str) -> dict:
        """缓存 GPH 网格；区域/cvol 元数据按需加载（首显只需 mesh）。"""
        import gphstats

        def _load() -> dict:
            with gphstats.open_buffer(path) as data:
                mesh = gphstats.parse_mesh(data)
            return {
                "mesh": mesh,
                "path": path,
                "region_faces": None,
                "parts": None,
                "cvol": None,
                "_meta_loaded": False,
            }

        return self._cached(("gph_aux", path), _load)

    def _ensure_gph_meta(self, aux: dict) -> None:
        """加载 GPH 面区域 / cvol / parts（仅勾选过滤体时需要）。"""
        if aux.get("_meta_loaded"):
            return
        import gphstats

        path = aux.get("path")
        if not path:
            aux["_meta_loaded"] = True
            return
        with gphstats.open_buffer(path) as data:
            cvol = gphstats.cvol_ids(data)
            aux["cvol"] = cvol
            aux["region_faces"] = gphstats.surface_region_face_ids(data)
            aux["parts"] = gphstats.parts_summary(data, cvol)
        aux["_meta_loaded"] = True

    def _gph_visibility_mask(self, aux: dict, group_name: Optional[str],
                             mdl_model) -> Optional[object]:
        """由 Part Tree 勾选生成 GPH 面可见掩码（True=显示）。

        白名单勾选零件的 ``@PartSurface_*`` / 面区域，而不是按隐藏体的
        cvol 黑名单剔除——流体域 cvol 的边界面往往就是 case 等固体的
        面网格，黑名单会误删勾选零件上的 GPH 网线。
        """
        import numpy as np

        mesh = aux["mesh"]
        n = int(mesh["n_faces"])
        if group_name is not None and group_name in self._group_hidden:
            return np.zeros(n, dtype=bool)
        hidden_bodies, hidden_regions = self._hidden.get(
            group_name, (set(), set())) if group_name else (set(), set())
        if not hidden_bodies and not hidden_regions:
            return None
        if mdl_model is None:
            return None

        self._ensure_gph_meta(aux)
        region_faces: dict = aux.get("region_faces") or {}
        show = np.zeros(n, dtype=bool)

        def _or_faces(key: str) -> None:
            arr = region_faces.get(key)
            if arr is None or arr.size == 0:
                return
            valid = arr[(arr >= 0) & (arr < n)]
            show[valid] = True

        b1, b2 = mdl_model.csid
        frid = mdl_model.frid
        # body → 零件名；frid → 面区域名（均不含 @PartSurface_*）
        body_names: dict[int, set[str]] = {}
        region_by_frid: dict[int, list[str]] = {}
        for r in getattr(mdl_model, "surface_regions", None) or []:
            if r.name.startswith("@"):
                continue
            region_by_frid.setdefault(int(r.index), []).append(r.name)
            if b2.size == 0:
                continue
            sel = frid == int(r.index)
            if not sel.any():
                continue
            for bid in np.unique(np.concatenate([b1[sel], b2[sel]])):
                bid = int(bid)
                if bid <= 0:
                    continue
                body_names.setdefault(bid, set()).add(r.name)

        # 勾选零件 → 对应 GPH @PartSurface_* 面网格
        for bid, names in body_names.items():
            if bid in hidden_bodies:
                continue
            for name in names:
                _or_faces(f"@PartSurface_{name}")

        # 纯面区域（如 open）：GPH 里没有 @PartSurface_* 的同名节，按区域勾选
        for frid_i, names in region_by_frid.items():
            if frid_i in hidden_regions:
                continue
            for name in names:
                if f"@PartSurface_{name}" in region_faces:
                    continue  # 零件面已由 body 白名单处理
                _or_faces(name)

        return show

    def _mdl_model_for_group(self, group: dict, group_name: Optional[str]):
        path = group.get("part") if group else None
        if not path:
            return None
        import mdl
        return self._cached(("mdl", path), lambda: mdl.parse_mdl(path))

    def set_model_visibility(self, group: str, hidden_bodies,
                             hidden_regions, group_visible: bool = True) -> None:
        self._hidden[group] = (set(hidden_bodies), set(hidden_regions))
        if group_visible:
            self._group_hidden.discard(group)
        else:
            self._group_hidden.add(group)
        # 体网格剖切缓存依赖面掩码，勾选变化后需重 Draw
        self._mesh_section_pd = None
        self._mesh_section_dirty = True
        self.render()

    def set_model_filter(self, filter_: Optional[dict]) -> None:
        self._mdl_filter = filter_
        if filter_ is None:
            self._picked_status = " | 已恢复全部"
        else:
            kind = filter_.get("kind")
            value = filter_.get("value")
            if kind == "face":
                self._picked_status = f" | 仅显示面 #{value}"
            elif kind == "faces":
                self._picked_status = (
                    f" | 框选 {len(filter_.get('values') or [])} 面")
            elif kind == "body":
                self._picked_status = f" | 仅显示 body {value}"
            elif kind == "bodies":
                self._picked_status = (
                    f" | 框选 {len(filter_.get('values') or [])} body")
            elif kind == "region":
                self._picked_status = f" | 仅显示区域 frid={value}"
            elif kind == "edge":
                self._picked_status = f" | 拾取边（面 #{value}）"
            elif kind == "vertex":
                self._picked_status = f" | 拾取点 #{value}"
            elif kind == "vertices":
                self._picked_status = (
                    f" | 框选 {len(filter_.get('values') or [])} 顶点")
        self.render()

    def set_pick_mode(self, mode: str) -> None:
        """Select 菜单拾取模式：face / part / edge / vertex。"""
        mode = (mode or "face").lower()
        if mode not in ("face", "part", "edge", "vertex"):
            mode = "face"
        self._pick_mode = mode
        labels = {
            "face": "面", "part": "零件(body)",
            "edge": "边", "vertex": "顶点",
        }
        if not self.btn_pick.isChecked():
            self.btn_pick.setChecked(True)
        else:
            self.status.setText(
                f"拾取模式：点击 MDL 选择{labels.get(mode, mode)}")

    def clear_visibility(self) -> None:
        self._mdl_filter = None
        self.last_pick = None
        self._hidden.clear()
        self._group_hidden.clear()
        self._layer_hidden.clear()
        self._picked_status = " | 已恢复全部"
        self.show_all_requested.emit()
        self.render()

    def _toggle_pick(self, checked: bool) -> None:
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        if checked:
            iren.AddObserver("LeftButtonPressEvent", self._on_pick)
            labels = {
                "face": "面", "part": "零件(body)",
                "edge": "边", "vertex": "顶点",
            }
            self.status.setText(
                f"拾取模式：点击 MDL 选择"
                f"{labels.get(self._pick_mode, '面')}")
        else:
            iren.RemoveObservers("LeftButtonPressEvent")

    def _on_pick(self, obj, _event) -> None:
        import vtk

        mode = self._pick_mode
        x, y = obj.GetEventPosition()

        if mode == "vertex":
            picker = vtk.vtkPointPicker()
            if picker.Pick(x, y, 0, self.renderer) == 0:
                self.status.setText("拾取失败：未命中顶点")
                return
            actor = picker.GetActor()
            if actor is None or actor not in self._pickable_actors:
                self.status.setText("请在 MDL 面片上拾取顶点")
                return
            pid = int(picker.GetPointId())
            meta = dict(self._pickable_meta.get(actor) or {})
            self.last_pick = {
                "mode": "vertex", "point_id": pid, **meta}
            self.set_model_filter({"kind": "vertex", "value": pid})
            self.status.setText(f"已拾取顶点 #{pid}")
            return

        picker = vtk.vtkCellPicker()
        if picker.Pick(x, y, 0, self.renderer) == 0:
            self.status.setText("拾取失败：未命中单元")
            return
        actor = picker.GetActor()
        if actor is None or actor not in self._pickable_actors:
            self.status.setText("请在 MDL 面片（part/ridge）上拾取")
            return
        cell = int(picker.GetCellId())
        meta = dict(self._pickable_meta.get(actor) or {})
        path = meta.get("path")
        body_id = None
        frid = None
        if path:
            try:
                import mdl
                model = self._cached(
                    (meta.get("kind") or "mdl", path),
                    lambda: mdl.parse_mdl(path))
                if 0 <= cell < model.n_faces:
                    frid = int(model.frid[cell]) if getattr(
                        model, "frid", None) is not None else None
                    b1, b2 = model.csid
                    if b1 is not None and cell < len(b1):
                        body_id = int(b1[cell])
            except Exception:  # noqa: BLE001
                pass

        if mode == "part":
            if body_id is None:
                self.status.setText("无法解析 body id，回退为面拾取")
                mode = "face"
            else:
                self.last_pick = {
                    "mode": "part", "face": cell, "body": body_id,
                    "frid": frid, **meta}
                self.set_model_filter({"kind": "body", "value": body_id})
                self.status.setText(f"已拾取 Part/body {body_id}（面 #{cell}）")
                return

        if mode == "edge":
            # 边：从命中单元解析最近边，记录 (v0, v1)
            edge = None
            edge_mid = None
            ds = picker.GetDataSet()
            if ds is not None and 0 <= cell < ds.GetNumberOfCells():
                c = ds.GetCell(cell)
                ids = c.GetPointIds()
                n = ids.GetNumberOfIds()
                px, py, pz = picker.GetPickPosition()
                best = None
                best_d = float("inf")
                for k in range(n):
                    a = int(ids.GetId(k))
                    b = int(ids.GetId((k + 1) % n))
                    pa = ds.GetPoint(a)
                    pb = ds.GetPoint(b)
                    mx = (pa[0] + pb[0]) / 2.0
                    my = (pa[1] + pb[1]) / 2.0
                    mz = (pa[2] + pb[2]) / 2.0
                    d = ((mx - px) ** 2 + (my - py) ** 2 +
                         (mz - pz) ** 2)
                    if d < best_d:
                        best_d = d
                        best = (a, b, (mx, my, mz))
                if best is not None:
                    edge = (best[0], best[1])
                    edge_mid = best[2]
            self.last_pick = {
                "mode": "edge", "face": cell, "body": body_id,
                "frid": frid, "edge": edge, "edge_mid": edge_mid, **meta}
            if self.display_mode.currentText() != "线框":
                self.display_mode.setCurrentText("线框")
            self.set_model_filter({"kind": "edge", "value": cell})
            self.status.setText(
                f"已拾取边 {edge if edge else '（面 #' + str(cell) + '）'}")
            return

        # face（默认）
        self.last_pick = {
            "mode": "face", "face": cell, "body": body_id,
            "frid": frid, **meta}
        # P5-3：累计面拾取（注册 Surface Region 时写多面引用）
        key = (meta.get("path"), cell)
        if all(k != key for k in self.picked_faces):
            self.picked_faces.append(key)
        self.set_model_filter({"kind": "face", "value": cell})
        self.status.setText(
            f"已拾取面 #{cell}"
            + (f" frid={frid}" if frid is not None else "")
            + (f"（累计 {len(self.picked_faces)} 面）"
               if len(self.picked_faces) > 1 else ""))

    def _toggle_rubber_select(self, checked: bool) -> None:
        """橡皮框/圆/多边形选择：启用时拦截左键拖动，禁用时恢复相机。"""
        from vtkmodules.vtkInteractionStyle import (
            vtkInteractorStyleTrackballCamera)

        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        owner = self
        if checked:
            class _RubberStyle(vtkInteractorStyleTrackballCamera):
                def OnLeftButtonDown(self):
                    owner._rubber_press(
                        self.GetInteractor().GetEventPosition())

                def OnMouseMove(self):
                    if owner._rubber_active:
                        owner._rubber_move(
                            self.GetInteractor().GetEventPosition())
                    else:
                        super().OnMouseMove()

                def OnLeftButtonUp(self):
                    if owner._rubber_active:
                        owner._rubber_release(
                            self.GetInteractor().GetEventPosition())
                    else:
                        super().OnLeftButtonUp()

                def OnRightButtonDown(self):
                    if owner._rubber_active and owner._rubber_kind == "polygon":
                        owner._rubber_polygon_done()
                    else:
                        super().OnRightButtonDown()

                def OnKeyPress(self):
                    iren2 = self.GetInteractor()
                    if iren2.GetKeySym() == "Escape" and owner._rubber_active:
                        owner._rubber_cancel()
                    else:
                        super().OnKeyPress()

            style = _RubberStyle()
            self._rubber_style = style
            # 拾取观察者会与框选左键冲突，先关闭鼠标拾取
            if self.btn_pick.isChecked():
                self.btn_pick.setChecked(False)
            self.status.setText(
                f"Rubber {self._rubber_kind}: drag to select "
                f"(pick mode={self._pick_mode}; Esc cancels)")
        else:
            self._rubber_active = False
            if self._rubber_band is not None:
                self._rubber_band.hide()
            if getattr(self, "_rubber_overlay", None) is not None:
                self._rubber_overlay.hide()
            self._rubber_style = vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(self._rubber_style)

    def _rubber_press(self, pos) -> None:
        x, y = int(pos[0]), int(pos[1])
        if self._rubber_kind == "polygon":
            pts = list(getattr(self, "_rubber_poly_pts", []) or [])
            pts.append((x, y))
            self._rubber_poly_pts = pts
            if self._rubber_overlay is None:
                self._rubber_overlay = _RubberPolygonOverlay(self.vtk_widget)
            self._rubber_overlay.resize(self.vtk_widget.size())
            self._rubber_overlay.set_points(pts)
            self._rubber_overlay.show()
            self._rubber_active = True
            self.status.setText(
                f"Rubber polygon: {len(pts)} vertex(es); "
                "click to add, right-click to finish")
            return
        self._rubber_active = True
        self._rubber_origin = QPoint(x, y)
        if self._rubber_band is None:
            self._rubber_band = QRubberBand(
                QRubberBand.Rectangle, self.vtk_widget)
        qy = self.vtk_widget.height() - y
        self._rubber_band.setGeometry(x, qy, 0, 0)
        self._rubber_band.show()

    def _rubber_move(self, pos) -> None:
        if not self._rubber_active or self._rubber_origin is None:
            return
        x, y = int(pos[0]), int(pos[1])
        origin = self._rubber_origin
        qx = min(origin.x(), x)
        qy = self.vtk_widget.height() - max(origin.y(), y)
        qw = abs(x - origin.x())
        qh = abs(y - origin.y())
        self._rubber_band.setGeometry(qx, qy, qw, qh)

    def _rubber_release(self, pos) -> None:
        if not self._rubber_active:
            return
        self._rubber_complete(self._rubber_origin,
                              QPoint(int(pos[0]), int(pos[1])))

    def _rubber_cancel(self) -> None:
        self._rubber_active = False
        self._rubber_origin = None
        if self._rubber_band is not None:
            self._rubber_band.hide()
        if getattr(self, "_rubber_overlay", None) is not None:
            self._rubber_overlay.hide()
        self.status.setText("Rubber select cancelled")

    def _rubber_polygon_done(self) -> None:
        pts = list(getattr(self, "_rubber_poly_pts", []) or [])
        if len(pts) < 3:
            self._rubber_cancel()
            self.status.setText("Rubber polygon needs >= 3 vertices")
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self._rubber_active = False
        if self._rubber_overlay is not None:
            self._rubber_overlay.hide()
        self._rubber_apply_region(min(xs), min(ys), max(xs), max(ys),
                                  polygon=pts)

    def _rubber_complete(self, start: Optional[QPoint],
                         end: Optional[QPoint]) -> None:
        self._rubber_active = False
        self._rubber_origin = None
        if self._rubber_band is not None:
            self._rubber_band.hide()
        if start is None or end is None:
            return
        xmin, xmax = sorted((start.x(), end.x()))
        ymin, ymax = sorted((start.y(), end.y()))
        if xmax - xmin < 2 or ymax - ymin < 2:
            self.status.setText("Rubber select: 区域过小，未选择")
            return
        circle = None
        if self._rubber_kind == "circle":
            cx = (start.x() + end.x()) / 2.0
            cy = (start.y() + end.y()) / 2.0
            r = max(1.0, min(abs(end.x() - start.x()),
                             abs(end.y() - start.y())) / 2.0)
            circle = (cx, cy, r)
        self._rubber_apply_region(xmin, ymin, xmax, ymax, circle=circle)

    def _mdl_face_meta(self, cell: int, meta: dict) -> tuple:
        """从 MDL 数据解析 face 对应的 body/frid（与鼠标拾取一致）。"""
        path = meta.get("path")
        if not path:
            return None, None
        try:
            import mdl
            model = self._cached(
                (meta.get("kind") or "mdl", path),
                lambda: mdl.parse_mdl(path))
            if 0 <= cell < model.n_faces:
                frid = int(model.frid[cell]) if getattr(
                    model, "frid", None) is not None else None
                b1, b2 = model.csid
                body_id = int(b1[cell]) if (
                    b1 is not None and cell < len(b1)) else None
                return body_id, frid
        except Exception:  # noqa: BLE001
            pass
        return None, None

    def _rubber_project_center(self, actor, cell_id: int,
                               mode: str) -> Optional[tuple]:
        """把 cell/vertex 投影到显示坐标（供圆/多边形过滤）。"""
        key = (id(actor), cell_id, mode)
        if key in self._rubber_center_cache:
            return self._rubber_center_cache[key]
        result = None
        p = None
        try:
            ds = actor.GetMapper().GetInput()
            if mode == "vertex":
                if 0 <= cell_id < ds.GetNumberOfPoints():
                    p = ds.GetPoint(cell_id)
            else:
                if 0 <= cell_id < ds.GetNumberOfCells():
                    c = ds.GetCell(cell_id)
                    ids = c.GetPointIds()
                    n = ids.GetNumberOfIds()
                    if n:
                        p = [0.0, 0.0, 0.0]
                        for k in range(n):
                            q = ds.GetPoint(int(ids.GetId(k)))
                            p[0] += q[0] / n
                            p[1] += q[1] / n
                            p[2] += q[2] / n
            if p is not None:
                self.renderer.SetWorldPoint(p[0], p[1], p[2], 1.0)
                self.renderer.WorldToDisplay()
                dp = self.renderer.GetDisplayPoint()
                result = (float(dp[0]), float(dp[1]))
        except Exception:  # noqa: BLE001
            result = None
        self._rubber_center_cache[key] = result
        return result

    def _rubber_select_cells(self, xmin: int, ymin: int, xmax: int,
                             ymax: int) -> dict:
        """HardwareSelector 框选：返回 faces/bodies/frids/edges/vertices。"""
        import vtk

        mode = self._pick_mode
        sel = vtk.vtkHardwareSelector()
        sel.SetRenderer(self.renderer)
        sel.SetArea(xmin, ymin, xmax, ymax)
        sel.SetFieldAssociation(
            vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS
            if mode == "vertex"
            else vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS)
        result = sel.Select()
        faces: list[int] = []
        cells: list[tuple] = []      # (actor, cell_id)
        points: list[tuple] = []     # (actor, point_id)
        bodies: set[int] = set()
        frids: set[int] = set()
        edges: list[tuple] = []
        vertices: list[int] = []
        if result is None:
            return {"faces": faces, "bodies": bodies, "frids": frids,
                    "edges": edges, "vertices": vertices,
                    "cells": cells, "points": points}
        for i in range(result.GetNumberOfNodes()):
            node = result.GetNode(i)
            props = node.GetProperties()
            if not props.Has(vtk.vtkSelectionNode.PROP()):
                continue
            actor = props.Get(vtk.vtkSelectionNode.PROP())
            if actor is None or actor not in self._pickable_actors:
                continue
            ids = node.GetSelectionList()
            if ids is None:
                continue
            meta = self._pickable_meta.get(actor, {})
            if mode == "vertex":
                for j in range(ids.GetNumberOfTuples()):
                    vid = int(ids.GetValue(j))
                    vertices.append(vid)
                    points.append((actor, vid))
                continue
            ds = actor.GetMapper().GetInput()
            for j in range(ids.GetNumberOfTuples()):
                cell = int(ids.GetValue(j))
                faces.append(cell)
                cells.append((actor, cell))
                body_id, frid = self._mdl_face_meta(cell, meta)
                if body_id is not None:
                    bodies.add(body_id)
                if frid is not None:
                    frids.add(frid)
                if mode == "edge" and ds is not None \
                        and 0 <= cell < ds.GetNumberOfCells():
                    c = ds.GetCell(cell)
                    pids = c.GetPointIds()
                    n = pids.GetNumberOfIds()
                    for k in range(n):
                        a = int(pids.GetId(k))
                        b = int(pids.GetId((k + 1) % n))
                        pa = ds.GetPoint(a)
                        pb = ds.GetPoint(b)
                        edges.append((
                            cell, a, b,
                            ((pa[0] + pb[0]) / 2.0,
                             (pa[1] + pb[1]) / 2.0,
                             (pa[2] + pb[2]) / 2.0)))
        return {"faces": faces, "bodies": bodies, "frids": frids,
                "edges": edges, "vertices": vertices,
                "cells": cells, "points": points}

    def _rubber_apply_region(self, xmin: int, ymin: int, xmax: int,
                             ymax: int, *,
                             circle: Optional[tuple] = None,
                             polygon: Optional[list] = None) -> None:
        mode = self._pick_mode
        picked = self._rubber_select_cells(xmin, ymin, xmax, ymax)
        cells = picked["cells"]          # (actor, cell_id)
        points = picked["points"]        # (actor, point_id)
        faces = sorted(set(picked["faces"]))
        bodies = sorted(picked["bodies"])
        frids = sorted(picked["frids"])
        edges = picked["edges"]
        vertices = sorted(set(picked["vertices"]))

        def _inside(x: float, y: float) -> bool:
            if circle is not None:
                cx, cy, r = circle
                return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            if polygon is not None:
                inside = False
                j = len(polygon) - 1
                for i in range(len(polygon)):
                    xi, yi = polygon[i]
                    xj, yj = polygon[j]
                    if ((yi > y) != (yj > y)) and \
                            (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12)
                             + xi):
                        inside = not inside
                    j = i
                return inside
            return True

        if circle is not None or polygon is not None:
            if mode == "vertex":
                keep = []
                for actor, vid in points:
                    pt = self._rubber_project_center(actor, vid, "vertex")
                    if pt is not None and _inside(pt[0], pt[1]):
                        keep.append(vid)
                vertices = sorted(set(keep))
            else:
                keep_faces: list[int] = []
                keep_edges: list[tuple] = []
                for actor, cell in cells:
                    pt = self._rubber_project_center(actor, cell, "face")
                    if pt is not None and _inside(pt[0], pt[1]):
                        keep_faces.append(cell)
                faces = sorted(set(keep_faces))
                if mode == "edge":
                    keep_ids = set(keep_faces)
                    for edge in edges:
                        if edge[0] in keep_ids:
                            keep_edges.append(edge)
                    edges = keep_edges

        kind_label = {"box": "Box", "circle": "Circle",
                      "polygon": "Polygon"}.get(self._rubber_kind, "Box")
        if mode == "vertex":
            self.last_pick = {
                "mode": f"rubber_{self._rubber_kind}",
                "vertices": vertices,
            }
            self.set_model_filter({"kind": "vertices", "values": vertices})
            self.status.setText(
                f"Rubber {kind_label}: 已选 {len(vertices)} 顶点")
        elif mode == "edge":
            self.last_pick = {
                "mode": f"rubber_{self._rubber_kind}",
                "faces": faces, "bodies": bodies, "frids": frids,
                "edges": edges,
            }
            self.set_model_filter({"kind": "faces", "values": faces})
            self.status.setText(
                f"Rubber {kind_label}: 已选 {len(edges)} 边 "
                f"({len(faces)} 面)")
        elif mode == "part":
            self.last_pick = {
                "mode": f"rubber_{self._rubber_kind}",
                "faces": faces, "bodies": bodies, "frids": frids,
            }
            self.set_model_filter({"kind": "bodies", "values": bodies})
            self.status.setText(
                f"Rubber {kind_label}: 已选 {len(bodies)} body")
        else:
            self.last_pick = {
                "mode": f"rubber_{self._rubber_kind}",
                "faces": faces, "bodies": bodies, "frids": frids,
            }
            self.set_model_filter({"kind": "faces", "values": faces})
            self.status.setText(
                f"Rubber {kind_label}: 已选 {len(faces)} 面")

    def _ensure_parallel_camera(self) -> None:
        """Draw Window 固定使用平行投影（正交），对齐 scFLOWpre。"""
        cam = self.renderer.GetActiveCamera()
        cam.ParallelProjectionOn()

    def fit(self) -> None:
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self._safe_vtk_render()

    def reset_viewpoint(self) -> None:
        cam = self.renderer.GetActiveCamera()
        cam.SetViewUp(0, 1, 0)
        cam.SetPosition(1, 1, 1)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self._safe_vtk_render()

    def set_plane(self, plane: str, *, negative: bool = False) -> None:
        """正交视图：XY/XZ/YZ（对应快捷键 Z/Y/X，Shift 为对侧）。"""
        pos, up = plane_view_camera(plane, negative=negative)
        cam = self.renderer.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 0)
        cam.SetPosition(pos[0], pos[1], pos[2])
        cam.SetViewUp(up[0], up[1], up[2])
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self._safe_vtk_render()

    def dispatch_view_key(self, keysym: str, *, shift: bool = False
                          ) -> bool:
        """应用 Draw Window 视图键；已处理返回 True。"""
        action = view_key_action(keysym, shift=shift)
        if action is None:
            return False
        if action[0] == "fit":
            self.fit()
            return True
        _, plane, negative = action
        self.set_plane(plane, negative=negative)
        return True


class PphViewer(QMainWindow):
    """主窗口 —— scFLOWpre 式排版。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PPH Viewer — scFLOWpre layout")
        self.resize(1600, 900)
        self.arch: Optional[pph_parser.PphArchive] = None
        self.archive_path: Optional[str] = None
        self.member_bytes: dict[str, bytes] = {}
        self.bin_paths: dict[str, str] = {}
        self.tmp_dir: Optional[str] = None
        self.snap = None
        self._xenv: Optional[pphxml.XenvSettings] = None
        self._main_xml: Optional[pphxml.MainXml] = None
        self._prp: Optional[pphxml.PrpDatabase] = None
        self._groups_info: dict = {}
        self._regions_meta: dict = {}
        self._mouse_mode = "3btn"
        self._mouse_op_type = "CRADLE 3-Button Mode"
        self._viewer_mode = False
        self._ui_language = "en"
        self._last_api_step = ""
        # True=Prepare Parts 模式；False=已 Build Analysis Model（锁定实体编辑）
        self._prepare_parts_mode = True
        self._menu_acts: dict[str, QAction] = {}
        # NavDialogSession 在 _build_ui 中创建
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._refresh_layout)
        self._untitled = False
        self._build_ui()
        self._apply_style()
        self.log("Ready.")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        self._layout_timer.start(40)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            # 最大化 / 还原后 splitter 与 VTK 原生窗需二次刷新
            self._layout_timer.start(80)

    def _refresh_layout(self) -> None:
        """全屏/缩放后强制各子窗与 VTK 视口重绘，消除重叠残影。"""
        central = self.centralWidget()
        if central is not None:
            central.updateGeometry()
            for sp in central.findChildren(QSplitter):
                sp.updateGeometry()
                sp.update()
            for pane in central.findChildren(PaneFrame):
                pane.update()
        if hasattr(self, "message_win"):
            self.message_win.update()
            self.message_win.text.viewport().update()
        if hasattr(self, "view3d"):
            self.view3d._sync_vtk_viewport()
            if self.view3d._legend_host.isVisible():
                self.view3d._legend_host.raise_()
                self.view3d._legend_host.repaint()
            self.view3d.legend.update()
            self.view3d.status.update()
        self.update()
        QApplication.processEvents()

    def log(self, msg: str, level: str = "INFO") -> None:
        if hasattr(self, "message_win"):
            self.message_win.log(msg, level)
        self.statusBar().showMessage(msg, 8000)

    def show_page(self, name: str) -> None:
        """切换 Draw 区堆叠页：draw / dashboard / editor / snapshot。"""
        pages = {
            "draw": self.view3d,
            "dashboard": self.dashboard,
            "editor": self.editor_tab,
            "snapshot": self.snapshot_tab,
        }
        w = pages.get(name, self.view3d)
        self.work_stack.setCurrentWidget(w)
        titles = {
            "draw": "Draw Window",
            "dashboard": "Draw Window — Dashboard",
            "editor": "Draw Window — Text Editor",
            "snapshot": "Draw Window — Snapshot",
        }
        self.draw_pane.set_title(titles.get(name, "Draw Window"))

    def _build_ui(self) -> None:
        self._build_menus()
        self._build_toolbars()

        # ── Navigation ────────────────────────────────────────────
        self.navigation = NavigationWindow(self)
        self.navigation.navigated.connect(self._on_navigate)
        nav_pane = PaneFrame("Navigation", self.navigation)

        # ── Tree（模型 + 成员）────────────────────────────────────
        self.member_tree = QTreeWidget(self)
        self.member_tree.setHeaderLabels(["Member", "Role", "Size"])
        self.member_tree.setIconSize(QSize(16, 16))
        self.member_tree.itemClicked.connect(self._on_member_clicked)
        self.member_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.member_tree.customContextMenuRequested.connect(
            self._member_context_menu)
        self.model_tree = ModelTree(self)
        self.model_tree.visibility_changed.connect(self._on_model_visibility)
        self.model_tree.layer_visibility_changed.connect(
            self._on_layer_visibility)
        self.model_tree.item_selected.connect(self._on_model_item_selected)
        self.model_tree.status_requested.connect(self._on_status_requested)
        self.model_tree.focus_3d.connect(self._focus_model_3d)
        self.model_tree.select_mesh.connect(self._select_mesh_view)
        tree_tabs = QTabWidget(self)
        tree_tabs.addTab(self.model_tree, "Part Tree")
        tree_tabs.addTab(self.member_tree, "Archive")
        tree_pane = PaneFrame("Tree", tree_tabs)

        # ── Property（属性 + 几何/OCT/网格状态）──────────────────
        self.property_panel = PropertyPanel(self)
        self.status_panel = StatusPanel(self)
        self._nav_dialogs = nav_panels.NavDialogSession()
        prop_tabs = QTabWidget(self)
        prop_tabs.addTab(self.property_panel, "Property")
        prop_tabs.addTab(self.status_panel, "Status")
        self.prop_tabs = prop_tabs
        prop_pane = PaneFrame("Property", prop_tabs)

        mid_left = QSplitter(Qt.Vertical, self)
        mid_left.addWidget(tree_pane)
        mid_left.addWidget(prop_pane)
        mid_left.setStretchFactor(0, 3)
        mid_left.setStretchFactor(1, 2)
        mid_left.setSizes([480, 280])

        # ── Draw + Message ────────────────────────────────────────
        self.view3d = View3DTab(self)
        self.dashboard = DashboardTab(self)
        self.dashboard.set_viewer(self)
        self.editor_tab = TextEditorTab(self)
        self.snapshot_tab = SnapshotTab(self)
        self.view3d.show_all_requested.connect(self._show_all_models)
        # 工具栏 Display 与 Draw 内控件双向同步
        self.view3d.display_mode.currentTextChanged.connect(
            self._sync_tb_display)
        self.tb_display.blockSignals(True)
        self.tb_display.setCurrentText(self.view3d.display_mode.currentText())
        self.tb_display.blockSignals(False)
        self.work_stack = QStackedWidget(self)
        self.work_stack.addWidget(self.view3d)
        self.work_stack.addWidget(self.dashboard)
        self.work_stack.addWidget(self.editor_tab)
        self.work_stack.addWidget(self.snapshot_tab)
        # 兼容旧代码中的 self.tabs
        self.tabs = self.work_stack
        self.draw_pane = PaneFrame("Draw Window", self.work_stack)

        self.message_win = MessageWindow(self)
        msg_pane = PaneFrame("Message", self.message_win)

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.draw_pane)
        right.addWidget(msg_pane)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 1)
        right.setSizes([640, 140])

        # ── 三列主分割：Nav | Tree+Property | Draw+Message ────────
        main = QSplitter(Qt.Horizontal, self)
        main.addWidget(nav_pane)
        main.addWidget(mid_left)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 0)
        main.setStretchFactor(2, 1)
        main.setSizes([220, 300, 1000])
        self.setCentralWidget(main)
        self.statusBar().showMessage("No project")
        self._install_draw_view_shortcuts()

    def _install_draw_view_shortcuts(self) -> None:
        """Draw Window：X/Y/Z(/Shift) 平面视图 + F Fit（对齐 cabdecoding）。

        使用 WidgetWithChildrenShortcut，仅在 Draw Window 聚焦时生效；
        Ctrl+F 仍为窗口级 Fit。
        """
        vtk = getattr(getattr(self, "view3d", None), "vtk_widget", None)
        if vtk is None:
            return
        for act, seq in (
            (getattr(self, "_act_yz", None), "X"),
            (getattr(self, "_act_xz", None), "Y"),
            (getattr(self, "_act_xy", None), "Z"),
        ):
            if act is None:
                continue
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            vtk.addAction(act)
        for seq, plane in (("Shift+X", "yz"), ("Shift+Y", "xz"),
                           ("Shift+Z", "xy")):
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            act.triggered.connect(
                lambda _=False, p=plane: self.view3d.set_plane(
                    p, negative=True))
            vtk.addAction(act)
        act_f = QAction(self)
        act_f.setShortcut(QKeySequence("F"))
        act_f.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        act_f.triggered.connect(self.view3d.fit)
        vtk.addAction(act_f)
        tip = "Fit to Draw Window (F when Draw Window focused; Ctrl+F)"
        if getattr(self, "_act_fit", None) is not None:
            self._act_fit.setToolTip(tip)
            self._act_fit.setStatusTip(tip)

    def _build_menus(self) -> None:
        """按 scFLOWpre Menu Guide（hh_toc / Pre_eng）重建菜单栏。"""
        mb = self.menuBar()
        mb.clear()
        self._menu_acts.clear()

        def add_act(menu, text, slot=None, *, shortcut=None, tip=None,
                    key: Optional[str] = None, checkable: bool = False):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            if tip:
                act.setToolTip(tip)
                act.setStatusTip(tip)
            if checkable:
                act.setCheckable(True)
            if slot:
                act.triggered.connect(slot)
            else:
                # 未接线：灰显，避免误点刷屏；tooltip 标明 NYI
                act.setEnabled(False)
                tip_nyi = tip or (
                    f"Not available in PPH viewer: {text}")
                act.setToolTip(tip_nyi)
                act.setStatusTip(tip_nyi)
            menu.addAction(act)
            if key:
                self._menu_acts[key] = act
            return act

        def nav(key: str):
            return lambda _c=False, k=key: self._on_navigate(k)

        # ── File ──────────────────────────────────────────────────
        m = mb.addMenu("File(&F)")
        add_act(m, "New Project…", self.new_empty_project, key="file_new")
        add_act(m, "Open…", self.open_dialog, shortcut="Ctrl+O",
                key="file_open")
        add_act(m, "Save", self._file_save, shortcut="Ctrl+S",
                key="file_save")
        add_act(m, "Save As…", self.save_as_dialog, shortcut="Ctrl+Shift+S",
                key="file_save_as")
        add_act(m, "Open Project Folder", self._open_project_folder,
                key="file_folder")
        m.addSeparator()
        add_act(m, "Import…", nav("import_part"), key="file_import")
        add_act(m, "Export…", self._export_member, key="file_export")
        add_act(m, "Create Actran Files…", key="file_actran")
        m.addSeparator()
        add_act(m, "Start Recording VBScript", self._vbs_start_recording,
                key="file_vbs_start")
        add_act(m, "Stop Recording VBScript", self._vbs_stop_recording,
                key="file_vbs_stop")
        add_act(m, "Execute VBScript…", self._vbs_execute_file,
                key="file_vbs_exec")
        m.addSeparator()
        add_act(m, "Exit", self.close, shortcut="Alt+F4", key="file_exit")

        # ── Edit ──────────────────────────────────────────────────
        m = mb.addMenu("Edit(&E)")
        add_act(m, "Undo", self._edit_undo, shortcut="Ctrl+Z",
                key="edit_undo")
        m.addSeparator()
        add_act(m, "Create Parts…", nav("create_parts"),
                key="edit_create_parts")
        add_act(m, "Modify Parts…", nav("modify_parts"),
                key="edit_modify_parts")
        add_act(m, "Create Non-Solid Part…", nav("non_solid"),
                key="edit_non_solid")
        add_act(m, "Define Facet Part…", key="edit_define_facet")
        add_act(m, "Create Non-Facet/Closed Volume Part…",
                key="edit_non_facet_cv")
        m.addSeparator()
        add_act(m, "Register Region…", nav("regions"),
                key="edit_register_region")
        add_act(m, "Create 2D Sub-mesh Meshing Unit…",
                key="edit_2d_submesh")
        add_act(m, "Measurement Tool", self._measurement_tool,
                key="edit_measure")
        m.addSeparator()
        ridge = m.addMenu("Ridge")
        add_act(ridge, "Set Selected Edge to Ridge",
                lambda: self._ridge_op("set"), key="edit_ridge_set")
        add_act(ridge, "Set Selected Edge to Non-Ridge",
                lambda: self._ridge_op("unset"), key="edit_ridge_unset")
        add_act(ridge, "Recalc Ridge",
                lambda: self._ridge_op("recalc"), key="edit_ridge_recalc")
        m.addSeparator()
        add_act(m, "Refine Octants",
                lambda: self._octant_op("refine"), key="edit_refine_oct")
        add_act(m, "Refine Octants (Recursive)…",
                lambda: self._octant_op("refine_rec"),
                key="edit_refine_oct_rec")
        add_act(m, "Refine Octants by Number…",
                lambda: self._octant_op("refine_num"),
                key="edit_refine_oct_num")
        add_act(m, "Refine Octants from Curvature…",
                lambda: self._octant_op("refine_curv"),
                key="edit_refine_oct_curv")
        add_act(m, "Refine Octants from Separation…",
                lambda: self._octant_op("refine_sep"),
                key="edit_refine_oct_sep")
        add_act(m, "Merge Octants",
                lambda: self._octant_op("merge"), key="edit_merge_oct")
        add_act(m, "Show Octants by Marked Face",
                lambda: self._octant_op("show_by_face"),
                key="edit_oct_by_face")
        add_act(m, "Show Octants by Marked Edge",
                lambda: self._octant_op("show_by_edge"),
                key="edit_oct_by_edge")
        m.addSeparator()
        add_act(m, "Restore Closed Volume Data…",
                key="edit_restore_cv")
        add_act(m, "Fix Marked Element Shape", key="edit_fix_elem")

        # ── Select ────────────────────────────────────────────────
        m = mb.addMenu("Select(&S)")
        self._select_pick_group = QActionGroup(self)
        self._select_pick_group.setExclusive(True)
        for key, label, mode in (
            ("sel_pick_part", "Mouse Pick (Part)", "part"),
            ("sel_pick_face", "Mouse Pick (Face)", "face"),
            ("sel_pick_face_spread", "Mouse Pick (Face & Spread)", None),
            ("sel_pick_face_virtual",
             "Mouse Pick (Face, Based on virtual part face/"
             "closed volume face)", None),
            ("sel_pick_edge", "Mouse Pick (Edge)", "edge"),
            ("sel_pick_edge_spread", "Mouse Pick (Edge & Spread)", None),
            ("sel_pick_vertex", "Mouse Pick (Vertex)", "vertex"),
        ):
            if mode:
                act = add_act(
                    m, label,
                    lambda _c=False, md=mode: self._set_select_pick_mode(md),
                    checkable=True, key=key,
                    tip=f"Pick MDL {mode} in Draw Window")
            else:
                act = add_act(m, label, checkable=True, key=key)
            self._select_pick_group.addAction(act)
        self._menu_acts["sel_pick_face"].setChecked(False)
        m.addSeparator()
        add_act(m, "Rubber Box (Select)",
                lambda: self._rubber_select("box"), key="sel_rbox",
                tip="Rubber-box: drag over MDL to select faces/parts")
        add_act(m, "Rubber Circle (Select)",
                lambda: self._rubber_select("circle"), key="sel_rcircle",
                tip="Rubber-circle: drag from center to radius")
        add_act(m, "Rubber Polygon (Select)",
                lambda: self._rubber_select("polygon"), key="sel_rpoly",
                tip="Rubber-polygon: click vertices, right-click to finish")
        m.addSeparator()
        add_act(m, "Spread Selected Face to Selected Edge",
                key="sel_spread")
        add_act(m, "Select by Element Number…",
                self._select_by_element_number, key="sel_by_elem",
                tip="输入 MDL 面编号列表（支持区间）过滤显示")
        add_act(m, "Select Elements by List File…",
                self._select_by_list_file, key="sel_by_list",
                tip="读取求解器稳定化功能输出的单元列表文件，选中对应"
                    " MDL 面（复用 Select by Element Number 解析）")
        add_act(m, "Select Faces That Have the Same Area",
                self._select_same_area, key="sel_same_area",
                tip="以 Mouse Pick 拾取的面为参考，选中同面积的全部面")
        m.addSeparator()
        add_act(m, "Select All Parts", self._select_all_parts,
                key="sel_all_parts")
        add_act(m, "Select All Faces", self._select_all_faces,
                key="sel_all_faces")
        add_act(m, "Select All Edges", self._select_all_edges,
                key="sel_all_edges")
        add_act(m, "Select All Ridges", self._select_all_ridges,
                key="sel_all_ridges")
        m.addSeparator()
        add_act(m, "Deselect All Parts",
                self._deselect_all,
                key="sel_desel_parts")
        add_act(m, "Deselect All Faces",
                self._deselect_all,
                key="sel_desel_faces")
        add_act(m, "Deselect All Edges", self._deselect_all,
                key="sel_desel_edges")
        add_act(m, "Deselect All Vertices", self._deselect_all,
                key="sel_desel_verts")
        add_act(m, "Deselect All Elements", self._deselect_all,
                key="sel_desel_elems")
        m.addSeparator()
        add_act(m, "Element Quality Check…", self._element_quality_check,
                key="sel_quality")
        add_act(m, "Check Intersection", self._check_intersection,
                key="sel_intersect",
                tip="MDL 面片穿越相交检测（体间 + 跨组，本地算法）")

        # ── View ──────────────────────────────────────────────────
        m = mb.addMenu("View(&V)")
        add_act(m, "Part", nav("view_part"), key="view_part")
        add_act(m, "Octree", nav("view_octree"), key="view_octree")
        add_act(m, "Mesh", nav("view_mesh"), key="view_mesh")
        m.addSeparator()
        add_act(m, "Reset Viewpoint",
                lambda: self.view3d.reset_viewpoint(),
                key="view_reset")
        self._act_fit = add_act(
            m, "Fit to Draw Window",
            lambda: self.view3d.fit(), shortcut="Ctrl+F",
            tip="Fit to Draw Window (F when Draw Window focused; Ctrl+F)",
            key="view_fit")
        add_act(m, "Fit to Selected Face (Model)",
                self._fit_to_selection, key="view_fit_face_mdl")
        add_act(m, "Fit to Selected Face (Mesh)",
                self._fit_to_selection, key="view_fit_face_msh")
        add_act(m, "Fit to Selected Element (Mesh)",
                self._fit_to_selection, key="view_fit_elem")
        m.addSeparator()
        # Draw Window 快捷键 X/Y/Z（及 Shift+）在 _install_draw_view_shortcuts
        self._act_xy = add_act(
            m, "XY Plane",
            lambda: self.view3d.set_plane("xy"),
            tip="XY plane from +Z (Z when Draw Window focused)",
            key="view_xy")
        self._act_xz = add_act(
            m, "XZ Plane",
            lambda: self.view3d.set_plane("xz"),
            tip="XZ plane from +Y (Y when Draw Window focused)",
            key="view_xz")
        self._act_yz = add_act(
            m, "YZ Plane",
            lambda: self.view3d.set_plane("yz"),
            tip="YZ plane from +X (X when Draw Window focused)",
            key="view_yz")
        m.addSeparator()
        add_act(m, "Show All", nav("view_show_all"), key="view_show_all")
        add_act(m, "Hide Selected Parts", self._hide_selected_parts,
                key="view_hide_parts")
        add_act(m, "Hide Selected Faces", self._hide_selected_faces,
                key="view_hide_faces")
        add_act(m, "Only Selected Part", self._only_selected_part,
                key="view_only_part")
        add_act(m, "Only Selected Face", self._only_selected_face,
                key="view_only_face")
        add_act(m, "Only Selected Mesh", self._only_selected_mesh,
                key="view_only_mesh")
        m.addSeparator()
        add_act(m, "Change Display Type of Edge",
                self._toggle_edge_display, key="view_edge_type")
        add_act(m, "Switch Display Surface by Orientation",
                self._cycle_display_mode, key="view_surf_orient")
        m.addSeparator()
        rb = m.addMenu("Rubber Box")
        add_act(rb, "Rubber Box (Show)", self._toggle_rubber,
                key="view_rbox_show")
        add_act(rb, "Rubber Box (Hide)", self._toggle_rubber,
                key="view_rbox_hide")
        rc = m.addMenu("Rubber Circle")
        add_act(rc, "Rubber Circle (Show)", self._toggle_rubber,
                key="view_rcirc_show")
        add_act(rc, "Rubber Circle (Hide)", self._toggle_rubber,
                key="view_rcirc_hide")
        rp = m.addMenu("Rubber Polygon")
        add_act(rp, "Rubber Polygon (Show)", self._toggle_rubber,
                key="view_rpoly_show")
        add_act(rp, "Rubber Polygon (Hide)", self._toggle_rubber,
                key="view_rpoly_hide")
        m.addSeparator()
        add_act(m, "Refinement Level…", self._view_refinement_level,
                key="view_refine_level")
        add_act(m, "Display Octants Connected by Node",
                lambda: self._view_octants("node"), key="view_oct_node")
        add_act(m, "Display Octants Connected by Face",
                lambda: self._view_octants("face"), key="view_oct_face")
        add_act(m, "Display Neighbor Octants by Direction…",
                lambda: self._view_octants("dir"), key="view_oct_dir")
        m.addSeparator()
        add_act(m, "Report Prism Layer", self._report_prism_layer,
                key="view_prism")
        add_act(m, "Element Types…", self._report_element_types,
                key="view_elem_types")
        add_act(m, "Show Parts List Dialog…", self._show_parts_list,
                key="view_parts_list")
        add_act(m, "Show Region Registration Check Dialog…",
                self._show_region_check, key="view_region_check")
        add_act(m, "Cross Section View of Mesh", nav("view_section"),
                key="view_section")
        add_act(m, "Element Quality Check…", self._element_quality_check,
                key="view_quality")
        m.addSeparator()
        add_act(m, "Dashboard", nav("dashboard"), key="view_dashboard")
        add_act(m, "Snapshot", nav("snapshot"), key="view_snapshot")

        # ── Condition ─────────────────────────────────────────────
        m = mb.addMenu("Condition(&C)")
        add_act(m, "Parts Control…", nav("parts_control"),
                key="cond_parts_control")
        add_act(m, "Discontinuous Mesh…", nav("specify_disc"),
                key="cond_disc")
        add_act(m, "Overset Mesh…", nav("overset_mesh"),
                key="cond_overset")
        add_act(m, "Part Material…", nav("part_material"),
                key="cond_part_mat")
        add_act(m, "Fluid Region Material…", nav("part_material"),
                key="cond_fluid_mat")
        add_act(m, "Conditions…", nav("conditions"), key="cond_wizard")
        m.addSeparator()
        add_act(m, "Project Type Setting…", self._project_type_dialog,
                key="cond_project_type")
        add_act(m, "Mesher/Faceter Setting…", nav("mesher_faceter"),
                key="cond_mesher")
        m.addSeparator()
        add_act(m, "Wrapping Octree Parameter…", nav("wrap_octree"),
                key="cond_wrap_oct")
        add_act(m, "Octree Parameter for Building Analysis Model…",
                nav("build_am_detailed"), key="cond_bam_oct")
        add_act(m, "Wrapping Parameter…", nav("wrap_param"),
                key="cond_wrap_param")
        m.addSeparator()
        add_act(m, "Octree Parameter…", nav("oct_param"),
                key="cond_oct")
        add_act(m, "Mesh Parameter…", nav("mesh_param"),
                key="cond_mesh")

        # ── Execute ───────────────────────────────────────────────
        m = mb.addMenu("Execute(&X)")
        add_act(m, "Begin Wrapping", nav("begin_wrap"),
                key="exec_begin_wrap")
        add_act(m, "Cancel Wrapping", nav("cancel_wrap"),
                key="exec_cancel_wrap")
        add_act(m, "Execute Wrapping…", nav("exec_wrap"),
                key="exec_exec_wrap")
        add_act(m, "Retry Wrapping", nav("retry_wrap"),
                key="exec_retry_wrap")
        m.addSeparator()
        add_act(m, "Prepare Parts", self._execute_prepare_parts,
                key="exec_prepare")
        add_act(m, "Build Analysis Model", nav("build_am"),
                key="exec_bam")
        m.addSeparator()
        add_act(m, "Generate Octree for Meshing", nav("oct_param"),
                key="exec_octree")
        add_act(m, "Generate Mesh", nav("mesh_param"),
                key="exec_mesh")
        add_act(m, "Voxel Fitting Mesh (Self Build)…",
                self._build_voxel_mesh, key="exec_voxel_self",
                tip="自研 hex-dominant mesher（cfMesh/snappy 风格，"
                    "产物兼容 OCT/GPH，算法不等价 scFLOW）")
        add_act(m, "Polyhedral Mesh (Self Build)…",
                self._build_poly_mesh, key="exec_poly_self",
                tip="自研原生多面体 mesher（clipped Voronoi/Delaunay 对偶，"
                    "产物兼容 GPH，算法不等价 scFLOW）")
        add_act(m, "Execute Solver", nav("execute"),
                key="exec_solver")

        # ── Option ────────────────────────────────────────────────
        m = mb.addMenu("Option(&O)")
        self._mouse_mode_group = QActionGroup(self)
        self._mouse_mode_group.setExclusive(True)
        self._mouse_acts: dict[str, QAction] = {}
        for key, label, nbtn in (
            ("1btn", "1-Button Mode", 1),
            ("2btn", "2-Button Mode", 2),
            ("3btn_ctrl", "3-Button Mode (CTRL)", 3),
            ("3btn", "3-Button Mode", 3),
        ):
            act = QAction(option_dialogs.mouse_mode_icon(nbtn), label, self)
            act.setCheckable(True)
            act.setData(key)
            self._mouse_mode_group.addAction(act)
            m.addAction(act)
            self._mouse_acts[key] = act
            self._menu_acts[f"opt_mouse_{key}"] = act
            act.triggered.connect(
                lambda _c=False, k=key: self._set_mouse_mode(k))
        self._mouse_acts["3btn"].setChecked(True)
        m.addSeparator()
        self._opt_tool_group = QActionGroup(self)
        self._opt_tool_group.setExclusive(True)
        for key, label in (
            ("opt_3d_rot", "3D Rotation"),
            ("opt_2d_rot", "2D Rotation"),
            ("opt_trans", "Translation"),
            ("opt_zoom", "Zoom In/Out"),
        ):
            act = add_act(
                m, label,
                lambda _c=False, t=label: self._set_opt_1button_tool(t),
                checkable=True, key=key,
                tip=f"{label} (maps to Trackball / mouse mode)")
            self._opt_tool_group.addAction(act)
        m.addSeparator()
        add_act(m, "Operation…", self._option_operation, key="opt_operation")
        m.addSeparator()
        add_act(m, "Unit Conversion…", self._option_unit_conversion,
                key="opt_unit")
        m.addSeparator()
        add_act(m, "Settings…", self._option_settings, key="opt_settings")
        self.act_viewer_mode = QAction("Change to Viewer Mode", self)
        self.act_viewer_mode.setCheckable(True)
        self.act_viewer_mode.triggered.connect(self._toggle_viewer_mode)
        m.addAction(self.act_viewer_mode)
        self._menu_acts["opt_viewer"] = self.act_viewer_mode
        m.addSeparator()
        lang_menu = m.addMenu("Change Language")
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_acts: dict[str, QAction] = {}
        for code, name in option_dialogs.LANGUAGES:
            act = QAction(name, self)
            act.setCheckable(True)
            act.setData(code)
            self._lang_group.addAction(act)
            lang_menu.addAction(act)
            self._lang_acts[code] = act
            act.triggered.connect(
                lambda _c=False, c=code: self._set_language(c))
        self._lang_acts["en"].setChecked(True)

        # ── Help ──────────────────────────────────────────────────
        m = mb.addMenu("Help(&H)")
        add_act(m, "Tutorial", self._open_tutorial, key="help_tutorial")
        add_act(m, "Reference", self._open_manual, key="help_ref")
        add_act(m, "About scFLOWpre", self._about, key="help_about")

        self._update_menus_for_mode()

    def _build_toolbars(self) -> None:
        icon_sz = 22

        def _tb(name: str) -> QToolBar:
            tb = QToolBar(name, self)
            tb.setMovable(False)
            tb.setIconSize(QSize(icon_sz, icon_sz))
            tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            return tb

        tb_file = _tb("File")
        for text, icon, tip, slot in (
            ("Open", "open", "Open Project (PPH)", self.open_dialog),
            ("Save As", "save", "Save As…", self.save_as_dialog),
            ("Reload", "reload", "Reload Project", self.reload),
        ):
            act = QAction(AppIcons.get(icon, icon_sz), text, self)
            act.setToolTip(tip)
            act.triggered.connect(slot)
            tb_file.addAction(act)
        self.addToolBar(tb_file)

        tb_view = _tb("View")
        for text, icon, tip, key in (
            ("Part", "part", "View — Part (geometry)", "view_part"),
            ("Octree", "octree", "View — Octree", "view_octree"),
            ("Mesh", "mesh", "View — Mesh", "view_mesh"),
            ("Section", "section", "Cross Section View of Mesh", "view_section"),
            ("Fit", "fit",
             "Fit to Draw Window (F / Ctrl+F)", None),
            ("Show All", "show_all", "Show All", "view_show_all"),
        ):
            act = QAction(AppIcons.get(icon, icon_sz), text, self)
            act.setToolTip(tip)
            if key:
                act.triggered.connect(
                    lambda _c=False, k=key: self._on_navigate(k))
            else:
                act.triggered.connect(
                    lambda: self.view3d.fit() if hasattr(self, "view3d")
                    else None)
            tb_view.addAction(act)
        self.addToolBar(tb_view)

        tb_disp = _tb("Display")
        disp_label = QLabel()
        disp_label.setPixmap(AppIcons.get("display", 18).pixmap(18, 18))
        disp_label.setToolTip("Display mode")
        tb_disp.addWidget(disp_label)
        self.tb_display = QComboBox(self)
        self.tb_display.addItems(["不透明", "半透明", "线框"])
        self.tb_display.setCurrentText("不透明")
        self.tb_display.setToolTip("不透明（默认）/ 半透明 / 线框")
        self.tb_display.setMinimumWidth(88)
        self.tb_display.currentTextChanged.connect(self._toolbar_display)
        tb_disp.addWidget(self.tb_display)
        self.addToolBar(tb_disp)

    def _toolbar_display(self, mode: str) -> None:
        if not hasattr(self, "view3d"):
            return
        idx = self.view3d.display_mode.findText(mode)
        if idx >= 0 and self.view3d.display_mode.currentIndex() != idx:
            self.view3d.display_mode.setCurrentIndex(idx)

    def _sync_tb_display(self, mode: str) -> None:
        if self.tb_display.currentText() != mode:
            self.tb_display.blockSignals(True)
            self.tb_display.setCurrentText(mode)
            self.tb_display.blockSignals(False)

    def _nyi(self, name: str) -> None:
        self.log(
            f"[{name}] not available in PPH viewer "
            f"(scFLOWpre-only / not yet mapped).",
            "WARN")

    def _set_opt_1button_tool(self, label: str) -> None:
        """Option 1-Button 工具：记录会话，不触发 _nyi。"""
        sess = self._nav_dialogs.session.setdefault("option_tool", {})
        sess["tool"] = label
        self.log(f"Option — {label} (1-Button tool)")

    # ── Option(O) ─────────────────────────────────────────────────

    def _set_mouse_mode(self, mode: str) -> None:
        """1/2/3-Button Mode：写入会话并提示映射（VTK 仍用 Trackball）。"""
        self._mouse_mode = mode
        type_map = {
            "1btn": "CRADLE 1-Button Mode",
            "2btn": "CRADLE 2-Button Mode",
            "3btn_ctrl": "CRADLE 3-Button Mode (CTRL)",
            "3btn": "CRADLE 3-Button Mode",
        }
        self._mouse_op_type = type_map.get(mode, self._mouse_op_type)
        sess = self._nav_dialogs.session.setdefault("option_mouse", {})
        sess["mode"] = mode
        sess["operation_type"] = self._mouse_op_type
        act = self._mouse_acts.get(mode)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        self._update_menus_for_mode()
        self.log(f"Option — mouse mode: {self._mouse_op_type}")

    def _option_operation(self) -> None:
        dlg = option_dialogs.ChangeMouseOperationDialog(
            self._mouse_op_type, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        typ = dlg.selected_type()
        self._mouse_op_type = typ
        mode = "3btn"
        if "1-Button" in typ:
            mode = "1btn"
        elif "2-Button" in typ:
            mode = "2btn"
        elif "CTRL" in typ:
            mode = "3btn_ctrl"
        self._set_mouse_mode(mode)

    def _option_unit_conversion(self) -> None:
        option_dialogs.UnitConversionDialog(self).exec_()

    def _option_settings(self, page_key: str = "navigation") -> None:
        ctx = self._nav_context()
        dlg = option_dialogs.EnvironmentSettingsDialog(
            ctx, self,
            on_open_mesher=lambda: self._on_navigate("mesher_faceter"))
        if hasattr(dlg, "_select_key"):
            dlg._select_key(page_key)
        if dlg.exec_() == QDialog.Accepted:
            self._commit_nav_ctx("option_settings", ctx)
            self._apply_option_nav()
            self._update_menus_for_mode()
            self.log("Option — Settings applied")

    def _file_save(self) -> None:
        """File → Save：有路径时另存覆盖提示；否则走 Save As。"""
        if self._viewer_mode:
            self.log("Viewer Mode: Save disabled", "WARN")
            return
        if not self.archive_path:
            self.save_as_dialog()
            return
        # 查看器默认不覆盖原文件，引导 Save As
        self.save_as_dialog()

    def _execute_prepare_parts(self) -> None:
        """Execute → Prepare Parts：回到零件准备模式（解锁实体编辑）。"""
        if self._viewer_mode:
            self.log("Viewer Mode: Prepare Parts disabled", "WARN")
            return
        if not self._prepare_parts_mode:
            r = QMessageBox.question(
                self, "Prepare Parts",
                "Return to Prepare Parts mode?\n"
                "The analysis model will be treated as invalid until "
                "Build Analysis Model is run again.",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok)
            if r != QMessageBox.Ok:
                return
        self._prepare_parts_mode = True
        sess = self._nav_dialogs.session.setdefault("build_am", {})
        sess["prepare_parts_mode"] = True
        sess.pop("build_requested", None)
        self._update_menus_for_mode()
        self.log("Execute — Prepare Parts mode")

    def _update_menus_for_mode(self) -> None:
        """按 Viewer / Prepare Parts / BAM 状态刷新菜单使能。"""
        vm = self._viewer_mode
        prep = self._prepare_parts_mode
        # File save/export
        for k in ("file_save", "file_save_as", "file_export", "file_actran"):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(not vm)
        # Edit solid-part ops：仅 Prepare Parts 且非 Viewer
        for k in (
            "edit_create_parts", "edit_modify_parts", "edit_define_facet",
            "edit_non_facet_cv",
        ):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(prep and not vm)
        # Non-solid / region：BAM 后仍常可用（手册侧重 solid）
        for k in ("edit_non_solid", "edit_register_region"):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(not vm)
        # Execute BAM / mesh / solver
        for k in ("exec_bam", "exec_octree", "exec_mesh", "exec_solver"):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(not vm)
        # Octree Create 语义：BAM 后才完整可用（仍可打开参数对话框）
        act = self._menu_acts.get("cond_oct")
        if act:
            act.setEnabled(True)
        # Wrapping 项：需 Enable wrapping
        opt = {}
        if hasattr(self, "_nav_dialogs"):
            opt = self._nav_dialogs.session.get("option_nav") or {}
        wrap_on = bool(opt.get("enable_wrapping", False))
        for k in (
            "exec_begin_wrap", "exec_cancel_wrap", "exec_exec_wrap",
            "exec_retry_wrap", "cond_wrap_oct", "cond_wrap_param",
        ):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(wrap_on and not vm)
        # Option 1-button tools：仅 1-button mode
        one = self._mouse_mode == "1btn"
        for k in ("opt_3d_rot", "opt_2d_rot", "opt_trans", "opt_zoom"):
            act = self._menu_acts.get(k)
            if act:
                act.setEnabled(one and not vm)

    def _apply_option_nav(self) -> None:
        opt = self._nav_dialogs.session.get("option_nav") or {}
        self.navigation.set_show_bam_item(opt.get("show_bam_item", True))
        self.navigation.set_show_mesher_item(
            opt.get("show_mesher_item", True))
        # Enable wrapping：仅在 Settings 写过 option_nav 后同步
        if "enable_wrapping" not in opt:
            return
        pc = self._nav_dialogs.session.setdefault("parts_control", {})
        enable = bool(opt.get("enable_wrapping"))
        pc["enable_wrapping"] = enable
        pc["wrapping_allowed"] = enable
        if not enable and pc.get("wrapping"):
            pc["wrapping"] = False
        self.navigation.set_parts_control(pc)

    def _toggle_viewer_mode(self, checked: bool = False) -> None:
        self._viewer_mode = bool(checked)
        sess = self._nav_dialogs.session.setdefault("option_env", {})
        sess["viewer_mode"] = self._viewer_mode
        self._update_menus_for_mode()
        self.log(
            "Option — Viewer Mode "
            + ("ON (save/export/BAM/mesh/solid-edit restricted)"
               if self._viewer_mode else "OFF"))

    def _set_language(self, code: str) -> None:
        self._ui_language = code
        sess = self._nav_dialogs.session.setdefault("option_env", {})
        sess["language"] = code
        name = dict(option_dialogs.LANGUAGES).get(code, code)
        act = self._lang_acts.get(code)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        QMessageBox.information(
            self, "Change Language",
            f"Language preference set to: {name}\n\n"
            "UI strings remain English in this viewer; "
            "the preference is stored for host/scFLOWpre export.")
        self.log(f"Option — language: {name} ({code})")

    def _about(self) -> None:
        QMessageBox.about(
            self, "About scFLOWpre",
            "PPH Viewer\n"
            "Menus aligned with Cradle scFLOWpre (2025.2).\n"
            "Inspect / lightly edit scFLOW .pph archives.\n"
            "Host mesh/solver execution requires scFLOWpre.")

    def _open_manual(self) -> None:
        path = (r"C:\Program Files\Cradle\CradleCFD2025.2"
                r"\Manuals\scFLOW\HTML\Pre_eng\index.html")
        if os.path.isfile(path):
            os.startfile(path)  # noqa: S606 - Windows open
            self.log(f"Opened manual: {path}")
        else:
            self.log(f"Manual not found: {path}", "ERROR")

    def _open_tutorial(self) -> None:
        path = (r"C:\Program Files\Cradle\CradleCFD2025.2"
                r"\Manuals\scFLOW\HTML\Exercise_eng\index.html")
        if not os.path.isfile(path):
            path = (r"C:\Program Files\Cradle\CradleCFD2025.2"
                    r"\Manuals\scFLOW\HTML\Operation_eng\index.html")
        if os.path.isfile(path):
            os.startfile(path)  # noqa: S606
            self.log(f"Opened tutorial: {path}")
        else:
            self.log("Tutorial manual not found", "ERROR")

    def _open_project_folder(self) -> None:
        if not self.archive_path:
            self.log("No project open.", "WARN")
            return
        folder = os.path.dirname(os.path.abspath(self.archive_path))
        os.startfile(folder)  # noqa: S606
        self.log(f"Opened folder: {folder}")

    def _member_raw(self, name: str) -> Optional[bytes]:
        """读取成员字节：文本缓冲 / 落盘二进制 / 原归档。"""
        if name in self.member_bytes:
            return self.member_bytes[name]
        bp = self.bin_paths.get(name)
        if bp and os.path.isfile(bp):
            with open(bp, "rb") as f:
                return f.read()
        if self.arch is not None:
            try:
                return self.arch.read_member(name)
            except Exception:  # noqa: BLE001
                return None
        return None

    def _export_member(self) -> None:
        item = self.member_tree.currentItem()
        name = item.data(0, Qt.UserRole) if item else None
        data = self._member_raw(name) if name else None
        if not name or data is None:
            self.log("Select an archive member first.", "WARN")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {name}", name, "All files (*)")
        if not path:
            return
        with open(path, "wb") as f:
            f.write(data)
        self.log(f"Exported {name} → {path}")

    def _toggle_pick_face(self) -> None:
        self._set_select_pick_mode("face")

    def _set_select_pick_mode(self, mode: str) -> None:
        self.show_page("draw")
        key_map = {
            "part": "sel_pick_part", "face": "sel_pick_face",
            "edge": "sel_pick_edge", "vertex": "sel_pick_vertex",
        }
        act = self._menu_acts.get(key_map.get(mode, ""))
        if act is not None:
            act.setChecked(True)
        self.view3d.set_pick_mode(mode)
        self.log(f"Select — Mouse Pick ({mode})")

    def _toggle_rubber(self) -> None:
        self.show_page("draw")
        checked = not self.view3d.btn_rubber.isChecked()
        self.view3d.btn_rubber.setChecked(checked)

    def _rubber_select(self, kind: str = "box") -> None:
        """Rubber Box/Circle/Polygon Select：VTK HardwareSelector 真实框选。"""
        self.show_page("draw")
        self.view3d._rubber_kind = kind
        self.view3d._rubber_center_cache = {}
        self.view3d._rubber_poly_pts = []
        if not self.view3d.btn_rubber.isChecked():
            self.view3d.btn_rubber.setChecked(True)
        else:
            self.view3d._toggle_rubber_select(True)
        labels = {"box": "Box", "circle": "Circle",
                  "polygon": "Polygon"}
        self.log(f"Select — Rubber {labels.get(kind, kind)} "
                 f"(pick mode={self.view3d._pick_mode})")

    def _deselect_all(self) -> None:
        self.view3d.set_model_filter(None)
        self.view3d.clear_visibility()
        self.log("Deselect All — cleared filter / visibility")

    def _select_all_parts(self) -> None:
        self.show_page("draw")
        self.view3d.clear_visibility()
        for g in (getattr(self.model_tree, "_info", {}) or {}):
            self.view3d.set_layer_visibility(g, "mdl", True, refresh=False)
        self.view3d.render()
        self.log("Select All Parts — show all MDL layers")

    def _select_all_faces(self) -> None:
        self._select_all_parts()
        self.log("Select All Faces — same as show all MDL (face mask TBD)")

    def _select_all_edges(self) -> None:
        self.show_page("draw")
        self.view3d.chk_edges.setChecked(True)
        self.view3d.display_mode.setCurrentText("线框")
        self.view3d.clear_visibility()
        self.log("Select All Edges — wireframe + edge overlay")

    def _select_all_ridges(self) -> None:
        self.show_page("draw")
        self.view3d.chk_mdl_ridge.setChecked(True)
        for g in (getattr(self.model_tree, "_info", {}) or {}):
            self.view3d.set_layer_visibility(g, "mdl", True, refresh=False)
        self.view3d.render()
        self.log("Select All Ridges — ridge layer on")

    def _toggle_edge_display(self) -> None:
        self.show_page("draw")
        on = not self.view3d.chk_edges.isChecked()
        self.view3d.chk_edges.setChecked(on)
        self.log(f"Change Display Type of Edge — edges={'on' if on else 'off'}")

    def _cycle_display_mode(self) -> None:
        self.show_page("draw")
        modes = ["不透明", "半透明", "线框"]
        cur = self.view3d.display_mode.currentText()
        nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else modes[0]
        self.view3d.display_mode.setCurrentText(nxt)
        self.log(f"Switch Display Surface — mode={nxt}")

    def _view_refinement_level(self) -> None:
        """显示当前 OCT 深度直方图（Refinement Level）。"""
        lines = []
        for g, info in (self._groups_info or {}).items():
            path = (info.get("paths") or {}).get("oct") or info.get("oct")
            if not path:
                continue
            try:
                import oct
                om = oct.parse_oct(path)
                summ = om.leaf_stats()
                hist = summ.get("depth_histogram") or {}
                n = summ.get("n_leaves", om.n_leaves)
                lines.append(f"[{g}] leaves={n}")
                for d, c in sorted(hist.items()):
                    lines.append(f"  depth {d}: {c}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"[{g}] error: {exc}")
        if not lines:
            lines = ["No .oct loaded. Generate Octree first."]
        QMessageBox.information(
            self, "Refinement Level", "\n".join(lines))
        self.log("View — Refinement Level")

    def _view_octants(self, kind: str) -> None:
        self.show_page("draw")
        self.view3d.chk_oct.setChecked(True)
        self.view3d.render()
        pick = getattr(self.view3d, "last_pick", None)
        msg = {
            "node": "Display Octants Connected by Node",
            "face": "Display Octants Connected by Face",
            "dir": "Display Neighbor Octants by Direction",
        }.get(kind, kind)
        extra = f"\nlast_pick={pick}" if pick else "\n(no face pick — showing all octants)"
        self.log(f"View — {msg}")
        QMessageBox.information(
            self, msg,
            f"Octree layer enabled.{extra}\n"
            "Neighbor filtering TBD (uses full leaf display).")

    def _report_prism_layer(self) -> None:
        self.log("View — Report Prism Layer (stats from GPH if present)")
        QMessageBox.information(
            self, "Report Prism Layer",
            "Prism-layer report requires host mesh metadata.\n"
            "Use Element Types for basic GPH counts.")

    def _report_element_types(self) -> None:
        lines = []
        for g, info in (self._groups_info or {}).items():
            gs = info.get("gph_summary") or {}
            lines.append(f"[{g}] {gs or '(no GPH summary)'}")
        if not lines:
            lines = ["No mesh groups loaded."]
        QMessageBox.information(self, "Element Types", "\n".join(lines))
        self.log("View — Element Types")

    def _show_parts_list(self) -> None:
        rows = []
        for g, info in (self._groups_info or {}).items():
            for p in info.get("xml_parts") or []:
                name = p.get("name") if isinstance(p, dict) else p
                rows.append(f"{g} / {name}")
        if not rows:
            rows = ["(no parts in main.xml)"]
        QMessageBox.information(
            self, "Parts List", "\n".join(rows[:200]))
        self.log(f"View — Parts List ({len(rows)})")

    def _show_region_check(self) -> None:
        meta = getattr(self, "_regions_meta", {}) or {}
        lines = []
        for cat in ("fluid", "volume", "face", "special_face"):
            items = meta.get(cat) or []
            lines.append(f"{cat}: {len(items)}")
            for r in items[:20]:
                if isinstance(r, dict):
                    lines.append(f"  - {r.get('name') or r.get('label')}")
                else:
                    lines.append(f"  - {r}")
        QMessageBox.information(
            self, "Region Registration Check",
            "\n".join(lines) if lines else "(no regions_meta)")
        self.log("View — Region Registration Check")

    def _element_quality_check(self) -> None:
        """Element Quality Check：本地质量统计（P2-3 quality.py）。"""
        import quality

        paths: list[tuple[str, str]] = []
        for g, info in (self._groups_info or {}).items():
            p = (info.get("paths") or {}).get("gph")
            if p:
                paths.append((g, str(p)))
        if not paths:
            p, _f = QFileDialog.getOpenFileName(
                self, "Select GPH volume mesh", "", "GPH mesh (*.gph)")
            if p:
                paths.append((Path(p).stem, p))
            else:
                self.log("Element Quality Check — no GPH mesh", "WARN")
                return

        reports: list[tuple[str, "quality.QualityReport"]] = []
        for g, p in paths:
            try:
                reports.append((f"{g} ({Path(p).name})",
                                quality.from_gph(p)))
            except Exception as exc:  # noqa: BLE001
                self.log(f"quality {p}: {exc}", "WARN")
        if not reports:
            QMessageBox.warning(
                self, "Element Quality Check",
                "无法从 GPH 解析网格（LS_Links 缺失或损坏）")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Element Quality Check")
        dlg.resize(760, 700)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit(dlg)
        text.setReadOnly(True)
        text.setMinimumHeight(260)
        lay.addWidget(text)

        # 跨组聚合直方图（非正交度 / 偏斜度）
        for metric in ("non_orthogonality", "skewness"):
            agg: dict[str, int] = {}
            for _label, rep in reports:
                for lbl, cnt in rep.histogram(metric):
                    agg[lbl] = agg.get(lbl, 0) + cnt
            if not agg:
                continue
            chart = BarChart(dlg)
            n = max(1, len(agg) - 1)
            items = [(lbl, float(cnt),
                      (0.2 + 0.7 * i / n, 0.75 - 0.55 * i / n, 0.25))
                     for i, (lbl, cnt) in enumerate(agg.items())]
            chart.set_data(items, unit=" faces")
            lay.addWidget(chart)

        body = "\n\n".join(
            rep.format_report(f"[{label}]") for label, rep in reports)
        text.setPlainText(body)
        btn = QPushButton("Close", dlg)
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()
        s = reports[0][1].summary()
        self.log(f"Check — Element Quality Check: {len(reports)} mesh(es), "
                 f"max non-orthogonality {s['non_orthogonality']['max']:.1f}°")

    # ── P3-3：Select 菜单本地实现 ───────────────────────────────

    @staticmethod
    def _parse_element_numbers(text: str) -> list[int]:
        """解析编号列表：逗号/空格/换行分隔，支持区间（如 ``10-20``）。"""
        ids: list[int] = []
        for tok in text.replace(",", " ").split():
            if "-" in tok[1:]:
                lo, _, hi = tok.partition("-")
                try:
                    a, b = int(lo), int(hi)
                except ValueError:
                    continue
                if b >= a and b - a < 1_000_000:
                    ids.extend(range(a, b + 1))
            else:
                try:
                    ids.append(int(tok))
                except ValueError:
                    continue
        return ids

    def _current_mdl_model(self) -> tuple[Optional[str], Optional[object]]:
        """当前组的 MDL part 模型：``(group, MdlModel)``。"""
        g = self.view3d.group_box.currentText()
        info = (self._groups_info or {}).get(g) or {}
        model = info.get("part")
        if model is None:
            path = (info.get("paths") or {}).get("part")
            if path:
                try:
                    import mdl
                    model = self.view3d._cached(
                        ("mdl", path), lambda: mdl.parse_mdl(path))
                except Exception:  # noqa: BLE001
                    model = None
        return (g if model is not None else None), model

    def _select_by_element_number(self) -> None:
        """Select by Element Number：输入 MDL 面编号列表 → faces 过滤。"""
        text, ok = QInputDialog.getMultiLineText(
            self, "Select by Element Number",
            "输入面编号（逗号/空格/换行分隔，支持区间 如 12-18）：",
            "1, 5, 10-20")
        if not ok or not text.strip():
            return
        ids = self._parse_element_numbers(text)
        if not ids:
            QMessageBox.warning(self, "Select by Element Number",
                                "未能解析出任何编号。")
            return
        g, model = self._current_mdl_model()
        n = model.n_faces if model is not None else 0
        if n == 0:
            QMessageBox.warning(
                self, "Select by Element Number",
                f"组 {g or '(?)'} 无 MDL 几何。请先生成/载入 MDL。")
            return
        valid = sorted({i for i in ids if 0 <= i < n})
        dropped = len(set(ids)) - len(valid)
        if not valid:
            QMessageBox.warning(
                self, "Select by Element Number",
                f"编号全部越界（有效范围 0..{n - 1}）。")
            return
        self.show_page("draw")
        self.view3d.set_model_filter({"kind": "faces", "values": valid})
        self.log(f"Select by Element Number [{g}] — {len(valid)} faces"
                 + (f"，忽略 {dropped} 个越界编号" if dropped else ""))

    def _select_by_list_file(self) -> None:
        """Select Elements by List File（P4-4）：列表文件 → 面过滤。

        scFLOWpre 语义：读取求解器稳定化（Measures Against Divergence）
        输出的单元列表文件并选中。列表文件为自由文本（编号 + 可选区间），
        直接复用 :meth:`_parse_element_numbers`。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Elements by List File", "",
            "List files (*.txt *.dat *.lis *.list);;All files (*.*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "Select Elements by List File",
                                f"无法读取文件：{exc}")
            return
        ids = self._parse_element_numbers(text)
        if not ids:
            QMessageBox.warning(
                self, "Select Elements by List File",
                f"未在 {Path(path).name} 中解析出任何编号。")
            return
        g, model = self._current_mdl_model()
        n = model.n_faces if model is not None else 0
        if n == 0:
            QMessageBox.warning(
                self, "Select Elements by List File",
                f"组 {g or '(?)'} 无 MDL 几何。请先生成/载入 MDL。")
            return
        valid = sorted({i for i in ids if 0 <= i < n})
        dropped = len(set(ids)) - len(valid)
        if not valid:
            QMessageBox.warning(
                self, "Select Elements by List File",
                f"编号全部越界（有效范围 0..{n - 1}）。")
            return
        self.show_page("draw")
        self.view3d.set_model_filter({"kind": "faces", "values": valid})
        self.log(f"Select Elements by List File [{g}] {Path(path).name} — "
                 f"{len(valid)} faces"
                 + (f"，忽略 {dropped} 个越界编号" if dropped else ""))

    def _select_same_area(self) -> None:
        """Select Faces That Have the Same Area：以拾取面为参考选同面积面。"""
        pick = getattr(self.view3d, "last_pick", None)
        if not pick or pick.get("mode") != "face":
            QMessageBox.information(
                self, "Same Area",
                "请先启用 Mouse Pick (Face) 拾取一个参考面。")
            return
        fid = int(pick.get("face"))
        path = pick.get("path")
        if not path:
            QMessageBox.warning(self, "Same Area", "拾取面缺少 MDL 路径。")
            return
        try:
            import mdl
            model = self.view3d._cached(
                ("mdl", path), lambda: mdl.parse_mdl(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Same Area", f"MDL 解析失败：{exc}")
            return
        if not (0 <= fid < model.n_faces):
            QMessageBox.warning(self, "Same Area",
                                f"面 #{fid} 越界（n={model.n_faces}）。")
            return
        areas = mdl.face_areas(model)
        target = float(areas[fid])
        scale = float(np.linalg.norm(
            model.xyz.max(axis=0) - model.xyz.min(axis=0))) ** 2
        tol = max(1e-4 * target, 1e-12 * scale)
        hits = np.flatnonzero(np.abs(areas - target) <= tol)
        values = sorted(int(v) for v in hits)
        self.show_page("draw")
        self.view3d.set_model_filter({"kind": "faces", "values": values})
        self.log(f"Select Same Area [{pick.get('group', '?')}] — "
                 f"face #{fid} area={target:.6g}，命中 {len(values)} 面")

    def _check_intersection(self) -> None:
        """Check Intersection：MDL 面片穿越相交检测（本地，P3-3）。"""
        import mdl

        models: dict[str, object] = {}
        for g, info in (self._groups_info or {}).items():
            model = info.get("part")
            if model is not None:
                models[g] = model
        if not models:
            QMessageBox.warning(
                self, "Check Intersection",
                "无 MDL 几何（需要 *_part.mdl）。")
            return
        diag = 0.0
        for m in models.values():
            diag = max(diag, float(np.linalg.norm(
                m.xyz.max(axis=0) - m.xyz.min(axis=0))))
        vertex_tol = 1e-6 * diag

        lines: list[str] = []
        total = 0
        first_hit = None
        for g, m in models.items():
            try:
                hits = mdl.surface_intersections(m, vertex_tol=vertex_tol)
            except Exception as exc:  # noqa: BLE001
                lines.append(f"[{g}] 检测失败：{exc}")
                continue
            total += len(hits)
            if hits:
                h0 = hits[0]
                lines.append(
                    f"[{g}] 体间穿越 {len(hits)} 处（首例 body "
                    f"{h0['body_a']}×{h0['body_b']}，faces "
                    f"#{h0['face_a']}/#{h0['face_b']} @ "
                    f"({h0['point'][0]:.3g}, {h0['point'][1]:.3g}, "
                    f"{h0['point'][2]:.3g})）")
                if first_hit is None:
                    first_hit = (g, h0)
            else:
                lines.append(f"[{g}] 无体间穿越")
        groups = sorted(models)
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                ga, gb = groups[i], groups[j]
                try:
                    hits = mdl.surface_intersections(
                        models[ga], models[gb], vertex_tol=vertex_tol)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"[{ga} × {gb}] 检测失败：{exc}")
                    continue
                total += len(hits)
                if hits:
                    h0 = hits[0]
                    lines.append(
                        f"[{ga} × {gb}] 跨组穿越 {len(hits)} 处（首例 "
                        f"faces #{h0['face_a']}/#{h0['face_b']}）")
                    if first_hit is None:
                        first_hit = (ga, h0)
                else:
                    lines.append(f"[{ga} × {gb}] 无跨组穿越")

        verdict = ("发现 %d 处面片穿越（可能几何干涉）" % total
                   if total else "未发现面片穿越（几何无干涉）")
        QMessageBox.information(
            self, "Check Intersection",
            verdict + "\n\n" + "\n".join(lines)
            + "\n\n（共面贴合/拓扑连接按容差 "
              f"{vertex_tol:.3g} 排除；仅检测非共面穿越）")
        self.log(f"Check Intersection — {verdict}")

    def _fit_to_selection(self) -> None:
        self.show_page("draw")
        self.view3d.fit()
        self.log("Fit to selection — ResetCamera on visible props")

    def _hide_selected_parts(self) -> None:
        items = self.model_tree.tree.selectedItems()
        if not items:
            self.log("Hide Selected Parts — nothing selected in Model Tree",
                     "WARN")
            return
        for it in items:
            data = it.data(0, Qt.UserRole)
            # expect (group, ...) patterns used by model tree
            group = None
            if isinstance(data, (list, tuple)) and data:
                group = data[0]
            elif isinstance(data, str):
                group = data
            if group:
                self.view3d.set_layer_visibility(group, "mdl", False)
        self.log(f"Hide Selected Parts — {len(items)} tree item(s)")

    def _hide_selected_faces(self) -> None:
        self._hide_selected_parts()
        self.log("Hide Selected Faces — delegated to part hide (face TBD)")

    def _only_selected_part(self) -> None:
        items = self.model_tree.tree.selectedItems()
        groups = set()
        for it in items:
            data = it.data(0, Qt.UserRole)
            if isinstance(data, (list, tuple)) and data:
                groups.add(data[0])
            elif isinstance(data, str):
                groups.add(data)
        if not groups:
            self.log("Only Selected Part — select a Model Tree item", "WARN")
            return
        for g in (getattr(self.model_tree, "_info", {}) or {}):
            self.view3d.set_layer_visibility(
                g, "mdl", g in groups, refresh=False)
            self.view3d.set_layer_visibility(
                g, "gph", False, refresh=False)
        self.view3d.render()
        self.log(f"Only Selected Part — {sorted(groups)}")

    def _only_selected_face(self) -> None:
        self._only_selected_part()

    def _only_selected_mesh(self) -> None:
        items = self.model_tree.tree.selectedItems()
        groups = set()
        for it in items:
            data = it.data(0, Qt.UserRole)
            if isinstance(data, (list, tuple)) and data:
                groups.add(data[0])
            elif isinstance(data, str):
                groups.add(data)
        all_g = list(getattr(self.model_tree, "_info", {}) or {})
        if not groups and all_g:
            groups = set(all_g)
        for g in all_g:
            self.view3d.set_layer_visibility(
                g, "gph", g in groups, refresh=False)
            self.view3d.set_layer_visibility(
                g, "mdl", False, refresh=False)
        self.view3d.render()
        self.log(f"Only Selected Mesh — {sorted(groups)}")

    def _measurement_tool(self) -> None:
        """简易测量：显示当前模型包围盒对角线（完整两点拾取待扩展）。"""
        try:
            b = self.view3d.renderer.ComputeVisiblePropBounds()
            if b[1] < b[0]:
                self.log("Measurement — no visible geometry", "WARN")
                return
            import math
            dx, dy, dz = b[1] - b[0], b[3] - b[2], b[5] - b[4]
            diag = math.sqrt(dx * dx + dy * dy + dz * dz)
            msg = (
                f"AABB size = ({dx:.6g}, {dy:.6g}, {dz:.6g}) m\n"
                f"Diagonal = {diag:.6g} m\n"
                f"(Point-to-point pick TBD)")
            QMessageBox.information(self, "Measurement Tool", msg)
            self.log(f"Measurement — diag={diag:.6g} m")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Measurement failed: {exc}", "WARN")

    def _ridge_op(self, op: str) -> None:
        """Ridge 操作：VMDL API 生成可执行宿主 VBS（RecalcRidge 等已锁定）。"""
        if not self.archive_path:
            QMessageBox.information(self, "Ridge", "请先打开 PPH 项目")
            return
        from automation import edit_ops

        angle = None
        if op == "recalc":
            angle, ok = QInputDialog.getDouble(
                self, "Recalc Ridge", "Angle (degree):",
                30.0, 0.0, 180.0, 3)
            if not ok:
                angle = None
        out = Path(self.archive_path).with_suffix(f".ridge_{op}.vbs")
        marker = Path(self.archive_path).with_suffix(f".ridge_{op}.done")
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        pick = getattr(self.view3d, "last_pick", None) or {}
        edge = pick.get("edge")
        edit_ops.write_ridge_vbs(
            self.archive_path, op, out, angle=angle,
            select_all_edges=op in ("set", "unset"), marker=marker)
        note = ""
        if edge is not None and op in ("set", "unset"):
            note = (f"\n本地拾取边 (v0,v1)={edge}；宿主 VBS 无按坐标选边 API"
                    "（IVEdge 无几何端点），脚本默认选择全部边。")
        api_label = ("VMDL_.RecalcRidge / RecalcRidgeFromProjectSetting"
                     if op == "recalc"
                     else "VMDL_.SetSelectedEdgeToRidge / "
                          "SetSelectedEdgeToNonRidge")
        self.log(f"Ridge {op} — VBS written: {out} ({api_label})")
        if self._host_api_enabled():
            self._start_api_refresh_poll(marker)
            self._start_api_execute_thread(out)
            self.log(f"Ridge {op} — 已提交宿主后台执行")
            return
        QMessageBox.information(
            self, "Ridge",
            f"已写出可执行宿主脚本（{api_label}）：\n{out}\n"
            f"{note}\n"
            "请在 scFLOWpre 中 File → Execute VBScript 执行；"
            "勾选“使用 scFLOWpre API”后将自动后台执行并刷新。")

    def _octant_op(self, op: str) -> None:
        """Refine/Merge/Show Octants → Octree API 宿主 VBS（或本地算法）。"""
        if not self.archive_path:
            QMessageBox.information(self, "Octants", "请先打开 PPH 项目")
            return
        if op in ("refine", "merge") and not self._host_api_enabled():
            self._local_octant_op(op)
            return
        from automation import edit_ops

        if op == "refine_sep":
            QMessageBox.information(
                self, "Octants",
                "scFLOWpre VBS API（Octree 类手册）未提供 "
                "“Refine from Separation”方法；\n"
                "可改用 Refine Octants (Recursive) / Refine by Number，"
                "或 Merge Octants。")
            return
        params: dict = {}
        if op == "refine_rec":
            level, ok = QInputDialog.getInt(
                self, "Refine Octants (Recursive)", "Level:", 1, 1, 20)
            if not ok:
                return
            rng, ok = QInputDialog.getInt(
                self, "Refine Octants (Recursive)", "Range:", 1, 0, 20)
            if not ok:
                return
            params = {"level": level, "range_": rng}
        elif op == "refine_num":
            level, ok = QInputDialog.getInt(
                self, "Refine by Number", "Level:", 1, 1, 20)
            if not ok:
                return
            num, ok = QInputDialog.getInt(
                self, "Refine by Number", "Number of times:", 1, 1, 100)
            if not ok:
                return
            params = {"level": level, "num": num}
        elif op == "refine_curv":
            lower, ok = QInputDialog.getDouble(
                self, "Refine from Curvature", "Lower limit:",
                30.0, 0.0, 180.0, 3)
            if not ok:
                return
            rmin_txt, ok = QInputDialog.getText(
                self, "Refine from Curvature",
                "rangeminarray (comma separated, e.g. 0,0.1,0.2):",
                text="0,0.1,0.2")
            if not ok:
                return
            rmax_txt, ok = QInputDialog.getText(
                self, "Refine from Curvature",
                "rangemaxarray (comma separated, e.g. 0.1,0.2,0.3):",
                text="0.1,0.2,0.3")
            if not ok:
                return
            try:
                rmin = [float(v) for v in rmin_txt.replace(";", ",")
                        .split(",") if v.strip()]
                rmax = [float(v) for v in rmax_txt.replace(";", ",")
                        .split(",") if v.strip()]
                if not rmin or len(rmin) != len(rmax):
                    raise ValueError("length mismatch")
            except ValueError as exc:
                QMessageBox.warning(
                    self, "Refine from Curvature",
                    f"无法解析数组：{exc}")
                return
            params = {"rmin": rmin, "rmax": rmax, "lowerlimit": lower}
        out = Path(self.archive_path).with_suffix(f".octant_{op}.vbs")
        marker = Path(self.archive_path).with_suffix(f".octant_{op}.done")
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        edit_ops.write_octant_vbs(
            self.archive_path, op, out, marker=marker, **params)
        label = edit_ops.octant_op_label(op) or op
        if op.startswith("show"):
            self.show_page("draw")
            self.view3d.chk_oct.setChecked(True)
            self.view3d.render()
        self.log(f"Octants {op} — VBS written: {out} (Octree_.{label})")
        if self._host_api_enabled():
            self._start_api_refresh_poll(marker)
            self._start_api_execute_thread(out)
            self.log(f"Octants {op} — 已提交宿主后台执行")
            return
        QMessageBox.information(
            self, "Octants",
            f"{label}（Octree_.{label}）\n已写出可执行宿主脚本：\n{out}\n"
            "请在 scFLOWpre 中 File → Execute VBScript 执行；"
            "勾选“使用 scFLOWpre API”后将自动后台执行并刷新。")

    def _host_api_enabled(self) -> bool:
        """Execute 计划开关：勾选后编辑操作走宿主 COM API 后台执行。"""
        sess = getattr(self._nav_dialogs, "session", None) or {}
        return bool((sess.get("execute") or {}).get("use_api"))

    def _local_octant_op(self, op: str) -> None:
        """本地 Refine/Merge：解析 OCT → 变换 → 写回新 PPH 并打开（无宿主）。"""
        import oct as octmod
        import pphwriter

        member = next((m for m in self.arch.members if m.role == "octree"),
                      None)
        if member is None:
            QMessageBox.information(
                self, "Octants",
                "当前 PPH 没有 OCT 成员，无法本地 Refine/Merge。")
            return
        src = self.bin_paths.get(member.name)
        if not src or not os.path.exists(src):
            QMessageBox.information(self, "Octants", "OCT 文件未落盘。")
            return
        try:
            model = octmod.parse_oct(src)
            if op == "refine":
                new = octmod.refine_all_leaves(model)
            else:
                new = octmod.coarsen_all_leaves(model)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Octants", f"本地操作失败：{exc}")
            return
        tmp = os.path.join(self.tmp_dir, member.name + ".local.oct")
        try:
            octmod.write_oct(
                tmp, new.root_min, new.root_max, new.refinement,
                new.block_id, unit=new.unit,
                date=new.last_gen_year or 20260812)
            with open(tmp, "rb") as f:
                data = f.read()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Octants", f"写出 OCT 失败：{exc}")
            return
        out = Path(self.archive_path).with_suffix(".local.pph")
        try:
            pphwriter.clone_pph(self.archive_path, out,
                                {member.name: data})
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Octants", f"写回 PPH 失败：{exc}")
            return
        self.log(f"Octants — 本地 {op} OCT 完成: {out}")
        self.open_archive(str(out))

    def _build_voxel_mesh(self) -> None:
        """自研 Voxel/Hex-dominant：MDL → octree → hex/poly → 写回新 PPH。"""
        if not self.arch or not self.archive_path:
            QMessageBox.information(self, "Voxel Mesh", "请先打开 PPH 项目")
            return
        import pph_parser
        import pphwriter

        oct_members = self.arch.by_role(pph_parser.ROLE_OCT)
        gph_members = self.arch.by_role(pph_parser.ROLE_GPH)
        if not oct_members or not gph_members:
            QMessageBox.information(
                self, "Voxel Mesh",
                "当前 PPH 没有 OCT/GPH 成员（自研写回需要先有样例成员占位）。")
            return
        part_path = None
        for _g, info in (self._groups_info or {}).items():
            part_path = ((info.get("paths") or {}).get("part")
                         or info.get("part"))
            if part_path:
                break
        if not part_path:
            QMessageBox.information(
                self, "Voxel Mesh", "未找到 MDL part 面片（先 Prepare Parts）。")
            return
        params = _voxel_params_dialog(self)
        if params is None:
            return
        import voxmesh
        out = Path(self.tmp_dir) / "voxmesh_self"
        try:
            result, oct_p, gph_p = voxmesh.build_from_mdl(
                part_path, out, params)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Voxel Mesh",
                                 f"自研 mesher 失败：{exc}")
            return
        st = result.stats()
        overrides = {
            oct_members[0].name: oct_p.read_bytes(),
            gph_members[0].name: gph_p.read_bytes(),
        }
        dst = Path(self.archive_path).with_suffix(".voxmesh.pph")
        try:
            pphwriter.clone_pph(self.archive_path, dst, overrides)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Voxel Mesh",
                                 f"写回 PPH 失败：{exc}")
            return
        self.log("Voxel mesh (self): "
                 + ", ".join(f"{k}={v}" for k, v in st.items()))
        self.open_archive(str(dst))
        rows = "\n".join(
            f"{k}: {v:,}" if isinstance(v, int) else f"{k}: {v}"
            for k, v in st.items())
        QMessageBox.information(
            self, "Voxel Mesh (Self)",
            f"已生成 hex-dominant 网格并写回：\n{dst}\n\n{rows}")

    def _build_poly_mesh(self) -> None:
        """自研原生多面体：Delaunay/Voronoi 对偶 + 表面裁剪 → 写回 GPH。"""
        if not self.arch or not self.archive_path:
            QMessageBox.information(self, "Polyhedral Mesh", "请先打开 PPH 项目")
            return
        import pph_parser
        import pphwriter

        gph_members = self.arch.by_role(pph_parser.ROLE_GPH)
        if not gph_members:
            QMessageBox.information(
                self, "Polyhedral Mesh",
                "当前 PPH 没有 GPH 成员（自研写回需要先有样例成员占位）。")
            return
        part_path = None
        for _g, info in (self._groups_info or {}).items():
            part_path = ((info.get("paths") or {}).get("part")
                         or info.get("part"))
            if part_path:
                break
        if not part_path:
            QMessageBox.information(
                self, "Polyhedral Mesh",
                "未找到 MDL part 面片（先 Prepare Parts）。")
            return
        params = _poly_params_dialog(self)
        if params is None:
            return
        import polymesh
        out = Path(self.tmp_dir) / "polymesh_self"
        try:
            result, gph_p = polymesh.build_from_mdl(part_path, out, params)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Polyhedral Mesh",
                                 f"自研 mesher 失败：{exc}")
            return
        st = result.stats()
        dst = Path(self.archive_path).with_suffix(".polymesh.pph")
        try:
            pphwriter.clone_pph(
                self.archive_path, dst, {gph_members[0].name: gph_p.read_bytes()})
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Polyhedral Mesh",
                                 f"写回 PPH 失败：{exc}")
            return
        self.log("Polyhedral mesh (self): "
                 + ", ".join(f"{k}={v}" for k, v in st.items()))
        self.open_archive(str(dst))
        rows = "\n".join(
            f"{k}: {v:,}" if isinstance(v, int) else f"{k}: {v:.4g}"
            for k, v in st.items())
        QMessageBox.information(
            self, "Polyhedral Mesh (Self)",
            f"已生成原生多面体网格并写回：\n{dst}\n\n{rows}")

    def _edit_undo(self) -> None:
        stack = self._nav_dialogs.session.setdefault("_undo", [])
        if not stack:
            self.log("Undo — empty stack", "WARN")
            return
        snap = stack.pop()
        sess = self._nav_dialogs.session
        for k in ("create_parts", "modify_parts", "octree_param"):
            if k in snap:
                sess[k] = dict(snap[k])
        self.log(
            f"Undo — restored {snap.get('key', '?')} "
            f"({len(stack)} left)")

    def _project_type_dialog(self) -> None:
        """显示/记录当前项目类型（完整切换对话框后续扩展）。"""
        typ = "(unknown)"
        if self._main_xml is not None:
            try:
                typ = (self._main_xml.root.findtext(".//project_type")
                       or self._main_xml.root.findtext(".//ProjectType")
                       or typ)
            except Exception:  # noqa: BLE001
                pass
        QMessageBox.information(
            self, "Project Type Setting",
            f"Current project type: {typ}\n\n"
            "Changing analysis type requires scFLOWpre conversion;\n"
            "edit main.xml project_type only after confirming host support.")
        self._nav_dialogs.session.setdefault("project_type", {})["type"] = typ

    def _vbs_start_recording(self) -> None:
        self._com_vbs_record(True)

    def _vbs_stop_recording(self) -> None:
        self._com_vbs_record(False)

    def _com_vbs_record(self, start: bool) -> None:
        try:
            import pythoncom
            import win32com.client
            from automation.host_pipeline import PROGID_HOST
            pythoncom.CoInitialize()
            try:
                app = win32com.client.Dispatch(PROGID_HOST)
                method = "StartRecordVBS" if start else "EndRecordVBS"
                try:
                    app._FlagAsMethod(method)
                except Exception:  # noqa: BLE001
                    pass
                getattr(app, method)()
                self.log(f"VBScript — {method} OK")
            finally:
                pythoncom.CoUninitialize()
        except Exception as exc:  # noqa: BLE001
            self.log(f"VBScript record failed: {exc}", "WARN")
            QMessageBox.warning(
                self, "VBScript",
                f"无法调用宿主 {('Start' if start else 'End')}RecordVBS：\n{exc}")

    def _vbs_execute_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Execute VBScript", "",
            "VBScript (*.vbs);;All files (*)")
        if not path:
            return
        from automation import host_pipeline
        self.log(f"Executing VBS via COM: {path}")
        result = host_pipeline.run_in_host(path, backend="com")
        self.log(f"Execute VBScript 返回: {result}")

    def _focus_status(self, focus: str) -> None:
        groups = sorted(getattr(self.model_tree, "_info", {}) or {})
        if not groups:
            self.log("No meshing group loaded.", "WARN")
            return
        self.prop_tabs.setCurrentWidget(self.status_panel)
        self._on_status_requested(groups[0], focus)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #e8e8e8; }
            QMenuBar { background: #f0f0f0; }
            QToolBar { background: #f5f5f5; border: none; spacing: 2px;
                       padding: 2px; }
            QToolBar QToolButton {
                padding: 2px 6px 1px 6px; margin: 1px;
                border: 1px solid transparent; border-radius: 3px;
            }
            QToolBar QToolButton:hover {
                background: #e3f2fd; border: 1px solid #90caf9;
            }
            QToolBar QToolButton:pressed {
                background: #bbdefb;
            }
            #NavTree::item { padding: 2px 2px; height: 20px; }
            #PaneFrame, #PaneBody {
                background: #ffffff;
                border: 1px solid #9a9a9a;
            }
            #PaneBody { border: none; }
            #PaneTitleBar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #5b9bd5, stop:1 #2e75b6);
            }
            #PaneTitle {
                color: white; font-weight: bold; font-size: 11px;
            }
            #NavFileLabel {
                background: #eaf2fb; border: 1px solid #b9d3ee;
                padding: 4px; color: #234; font-size: 11px;
            }
            QTreeWidget, QPlainTextEdit {
                background: white; border: none;
            }
            QSplitter::handle { background: #c8c8c8; width: 3px; height: 3px; }
            QStatusBar { background: #f0f0f0; }
        """)

    # ── 打开 / 保存 ─────────────────────────────────────────────────
    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 PPH", "", "PPH 文件 (*.pph);;所有文件 (*)")
        if path:
            self.open_archive(path)

    @staticmethod
    def _empty_project_members() -> dict[str, bytes]:
        """最小可解析空工程：main.xml / xenv / prp / js。"""
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<scFLOWpre>
  <version>5225.20302.20251223</version>
  <date>{now}</date>
  <project>
    <name>Untitled</name>
    <showmode>1</showmode>
  </project>
  <parts>
    <meshinggroup>
      <phase>0</phase>
      <analysis_model_flag>false</analysis_model_flag>
      <sgs_name>MeshingGroup_1</sgs_name>
      <meshonly>false</meshonly>
      <mesh_visible>true</mesh_visible>
      <visible>true</visible>
      <mesh_state>0</mesh_state>
      <org_name/>
    </meshinggroup>
  </parts>
  <regions/>
  <conditions>
    <analysis_type>
      <Flow>true</Flow>
    </analysis_type>
    <basic_param>
      <steady>true</steady>
      <end_cycle>100</end_cycle>
    </basic_param>
  </conditions>
</scFLOWpre>
"""
        xenv = pphxml.XenvSettings()
        for sec, key, val in (
            ("TYPE", "PROJECT_TYPE", "scflow"),
            ("MESH", "MESHER", "0"),
            ("MESH", "SURF_MESHER", "0"),
            ("FACET", "MDL_METHOD", "1"),
            ("FACET", "USE_FACETTER", "true"),
            ("FACET", "PROJECT_SOLIDS", "true"),
            ("FACET", "PROJECT_SHEETS", "true"),
            ("FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0"),
            ("FACET", "USE_ABSOLUTE_VALUE", "false"),
            ("FACET", "SIMPLE_CHORD_TOLERANCE", "1"),
            ("FACET", "SIMPLE_MAX_ANGLE", "10"),
            ("FACET", "SIMPLE_MAX_WIDTH", "5"),
            ("FACET", "SOLID_BASE_MINIMUM_ANGLE", "10"),
            ("FACET", "SOLID_BASE_LENGTH_FACTOR", "0.05"),
            ("FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", "0.05"),
        ):
            pphxml.set_xenv_value(xenv, sec, key, val)
        prp = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<prp version="1" date="">\n'
            "</prp>\n"
        )
        js = (
            "//@FormattedScript\n"
            "function usr_input(nlines)\n{\n\n}\n"
        )
        return {
            "main.xml": xml.encode("utf-8"),
            "main.xenv": pphxml.serialize_xenv(xenv),
            "main.prp": prp.encode("utf-8"),
            "main.js": js.encode("utf-8"),
        }

    def new_empty_project(self) -> None:
        """初始化空 PPH 工程（对齐 File → New Project）。"""
        import zipfile

        self._cleanup()
        self.tmp_dir = tempfile.mkdtemp(prefix="pph_gui_")
        path = os.path.join(self.tmp_dir, "Untitled.pph")
        members = self._empty_project_members()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in members.items():
                z.writestr(name, data)

        self.arch = pph_parser.PphArchive.open(path)
        self.archive_path = path
        self._untitled = True
        self.member_bytes = dict(members)
        self.bin_paths = {}
        self._groups_info = {}
        self._regions_meta = {}
        self._prepare_parts_mode = True
        self._nav_dialogs.session.clear()

        self.editor_tab.set_originals(self.member_bytes)
        self._populate_tree()
        self.view3d.set_cad_meshes([])
        self._populate_3d()
        if hasattr(self, "snapshot_tab"):
            try:
                self.snapshot_tab.clear()
            except Exception:  # noqa: BLE001
                pass
        self.dashboard.populate()
        self._build_model_tree()
        self._load_text_project_data()
        self.property_panel.set_properties(self._archive_properties())
        self.navigation.set_file_info(
            "Untitled.pph", len(self.arch.members),
            _fmt_size(sum(m.size for m in self.arch.members)))
        self.show_page("draw")
        self.setWindowTitle("PPH Viewer — Untitled")
        self._update_menus_for_mode()
        self.log("New empty project (Untitled.pph)")

    def open_archive(self, path: str) -> bool:
        try:
            self._cleanup()
            self.arch = pph_parser.PphArchive.open(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", str(exc))
            return False
        self.archive_path = path
        self._untitled = False
        self.log(f"Opening {os.path.basename(path)} …")
        QApplication.processEvents()

        text_ext = (".js", ".prp", ".xenv", ".xml")
        bin_roles = (pph_parser.ROLE_SNAPSHOT, pph_parser.ROLE_GPH,
                     pph_parser.ROLE_OCT, pph_parser.ROLE_MDL_PART,
                     pph_parser.ROLE_MDL_RIDGE)
        self.member_bytes = {}
        self.tmp_dir = tempfile.mkdtemp(prefix="pph_gui_")
        self.bin_paths = {}
        for m in self.arch.members:
            data = self.arch.read_member(m.name)
            # 文本常驻内存供编辑；大二进制只落盘，避免重复占 RAM / 误当文本解码
            if m.name.lower().endswith(text_ext):
                self.member_bytes[m.name] = data
            if m.role in bin_roles:
                p = os.path.join(self.tmp_dir, m.name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
                self.bin_paths[m.name] = p
                del data  # 尽早释放大块
            QApplication.processEvents()

        self.editor_tab.set_originals(self.member_bytes)
        self._populate_tree()
        self.view3d.set_cad_meshes([])
        self._populate_3d()
        self._tessellate_xt_members()
        self._load_snapshot_member()
        self.dashboard.populate()
        QApplication.processEvents()
        self._build_model_tree()
        self._load_text_project_data()
        self.property_panel.set_properties(self._archive_properties())
        self.navigation.set_file_info(
            path, len(self.arch.members),
            _fmt_size(sum(m.size for m in self.arch.members)))
        self.show_page("draw")
        self.setWindowTitle(f"PPH Viewer — {os.path.basename(path)}")
        self.log(f"Opened {path} ({len(self.arch.members)} members)")
        # 大 GPH：默认只显示几何，勾选「体网格」再加载（避免打开即解析数千万面）
        large_gph = any(
            n.lower().endswith(".gph")
            and os.path.getsize(p) > 64 * 1024 * 1024
            for n, p in self.bin_paths.items())
        if large_gph:
            for g in self.view3d.groups:
                self.view3d.set_layer_visibility(g, "gph", False, refresh=False)
            self.view3d.chk_gph.blockSignals(True)
            self.view3d.chk_gph.setChecked(False)
            self.view3d.chk_gph.blockSignals(False)
            for g in self.model_tree.groups():
                for item in self.model_tree._items(g, "layer"):
                    if item.data(0, Qt.UserRole)[2] == "gph":
                        self.model_tree.tree.blockSignals(True)
                        item.setCheckState(0, Qt.Unchecked)
                        self.model_tree.tree.blockSignals(False)
            self.log("大体积网格：已显示几何；勾选「体网格」后再加载（可能需数十秒）")
        self.view3d.render()
        return True

    def _load_text_project_data(self) -> None:
        """解析 xenv/xml/prp，刷新 Condition 参数面板上下文。"""
        self._xenv = None
        self._main_xml = None
        self._prp = None
        try:
            if "main.xenv" in self.member_bytes:
                self._xenv = pphxml.parse_xenv(self.member_bytes["main.xenv"])
        except Exception as exc:  # noqa: BLE001
            self.log(f"xenv 解析失败: {exc}", "WARN")
        try:
            if "main.xml" in self.member_bytes:
                self._main_xml = pphxml.parse_main_xml(
                    self.member_bytes["main.xml"])
        except Exception as exc:  # noqa: BLE001
            self.log(f"xml 解析失败: {exc}", "WARN")
        try:
            if "main.prp" in self.member_bytes:
                self._prp = pphxml.parse_prp(self.member_bytes["main.prp"])
        except Exception as exc:  # noqa: BLE001
            self.log(f"prp 解析失败: {exc}", "WARN")
        self._sync_nav_mesher()

    def _sync_nav_mesher(self) -> None:
        """按 MESH/MESHER 刷新 Navigation 中 Build Analysis Model 可见性。"""
        mesher = "0"
        if self._xenv is not None:
            mesher = self._xenv.get("MESH", "MESHER", "0") or "0"
        sess = (self._nav_dialogs.session.get("mesher_faceter") or {})
        if sess.get("mesher") is not None:
            mesher = str(sess["mesher"])
        self.navigation.set_polyhedral_mesher(str(mesher) == "0")
        self._apply_option_nav()

    def _build_am_confirm_choice(self) -> str:
        """确认框：返回 ``ok`` / ``cancel`` / ``detailed``。"""
        msg = QMessageBox(self)
        msg.setWindowTitle("scFLOWpre")
        msg.setIcon(QMessageBox.Question)
        msg.setText("Build the analysis model from parts.")
        msg.setInformativeText(
            "If parts are overlapped, the lower part in the part tree "
            "will be used.\n\n"
            "Click [Detailed...] for Analysis Model Wizard settings.")
        btn_detailed = msg.addButton(
            "Detailed...", QMessageBox.ActionRole)
        btn_ok = msg.addButton(QMessageBox.Ok)
        msg.addButton(QMessageBox.Cancel)
        msg.setDefaultButton(btn_ok)
        msg.exec_()
        clicked = msg.clickedButton()
        if clicked == btn_detailed:
            return "detailed"
        if clicked == btn_ok:
            return "ok"
        return "cancel"

    def _confirm_build_analysis_model(self) -> None:
        """对齐 scFLOWpre：点击 Build Analysis Model 的确认框。

        Detailed… 打开 Analysis Model Wizard（面片精度 / 微小面 / Repair 等）。
        """
        choice = self._build_am_confirm_choice()
        if choice == "detailed":
            self.log("Build Analysis Model — Detailed (Analysis Model Wizard)")
            self._show_condition("build_am_detailed")
            return
        if choice == "ok":
            sess = self._nav_dialogs.session.setdefault("build_am", {})
            sess["build_requested"] = True
            # 对齐 scFLOWpre：BAM 后锁定 Create/Modify Parts，直至 Prepare Parts
            self._prepare_parts_mode = False
            sess["prepare_parts_mode"] = False
            self._update_menus_for_mode()
            opt = self._nav_dialogs.session.get("option_nav") or {}
            if opt.get("always_show_wizard"):
                self.log(
                    "Build Analysis Model — OK + Always show wizard "
                    "(进入 Analysis Model Wizard)")
                self._show_condition("build_am_detailed")
            else:
                self.log(
                    "Build Analysis Model — confirmed "
                    "(闭体识别/建面片在 scFLOWpre 中执行)")
            return
        self.log("Build Analysis Model — cancelled")

    def _nav_context(self) -> dict:
        groups = dict(self._groups_info)
        for g in groups:
            groups[g] = dict(groups[g])
            groups[g]["status"] = self.model_tree.group_status_props(g)
        return self._nav_dialogs.build_ctx(
            xenv=self._xenv,
            xml=self._main_xml,
            prp=self._prp,
            groups_info=groups,
            regions_meta=getattr(self, "_regions_meta", {}) or {},
            last_pick=getattr(self.view3d, "last_pick", None),
            picked_faces=list(getattr(self.view3d, "picked_faces", []) or []),
        )

    def _commit_nav_ctx(self, key: str, ctx: dict) -> None:
        """对话框 Apply/OK 后提交 xenv / xml 到 Save As 缓冲。"""
        # Undo：浅快照 session 关键键
        undo = self._nav_dialogs.session.setdefault("_undo", [])
        snap = {
            "key": key,
            "create_parts": dict(
                (ctx.get("session") or {}).get("create_parts") or {}),
            "modify_parts": dict(
                (ctx.get("session") or {}).get("modify_parts") or {}),
            "octree_param": dict(
                (ctx.get("session") or {}).get("octree_param") or {}),
        }
        undo.append(snap)
        if len(undo) > 32:
            del undo[:-32]

        msgs = []
        if ctx.get("xenv_dirty") and self._xenv is not None:
            data = pphxml.serialize_xenv(self._xenv)
            self.member_bytes["main.xenv"] = data
            self.editor_tab.set_buffer_text(
                "main.xenv", data.decode("utf-8-sig"))
            ctx["xenv_dirty"] = False
            msgs.append("main.xenv")
        if ctx.get("xml_dirty") and self._main_xml is not None:
            text = pphxml.serialize_main_xml(self._main_xml.root)
            if not text.lstrip().startswith("<?xml"):
                text = '<?xml version="1.0" encoding="utf-8"?>\n' + text
            data = text.encode("utf-8")
            self.member_bytes["main.xml"] = data
            self.editor_tab.set_buffer_text("main.xml", text)
            ctx["xml_dirty"] = False
            msgs.append("main.xml")
        pc = (ctx.get("session") or {}).get("parts_control") or {}
        if key == "parts_control" or pc.get("nav_dirty"):
            self.navigation.set_parts_control(pc)
            pc["nav_dirty"] = False
            flags = []
            if pc.get("discontinuous"):
                flags.append("Discontinuous")
            if pc.get("overset"):
                flags.append("Overset")
            if pc.get("wrapping"):
                flags.append("Wrapping")
            msgs.append(
                "Navigation: " + (", ".join(flags) if flags else "基础项"))
        if key == "mesher_faceter":
            self._sync_nav_mesher()
            poly = self.navigation._polyhedral_mesher
            msgs.append(
                "Build Analysis Model: "
                + ("显示" if poly else "隐藏 (非 Polyhedral)"))
        if key in ("option_nav", "option_settings"):
            self._apply_option_nav()
            msgs.append("Option → Navigation / Settings 已应用")

        pending = (ctx.get("session") or {}).pop("pending_vbs", None)
        if pending and self.archive_path:
            try:
                from automation.pipeline_plan import write_nav_vbs
                op = pending.get("op") or key
                out = Path(self.archive_path).with_suffix(f".{op}.vbs")
                write_nav_vbs(
                    op, self.archive_path, out,
                    draft=pending.get("draft"))
                msgs.append(f"VBS {out.name}")
                self.log(f"[{key}] VBS 草稿: {out}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"[{key}] VBS 写出失败: {exc}", "WARN")

        if msgs:
            self.log(f"[{key}] 已应用: {', '.join(msgs)}")
        else:
            self.log(f"[{key}] 会话参数已保存")

    def _show_condition(self, key: str) -> None:
        """弹出 scFLOWpre 风格参数子窗口（模态）。"""
        if key == "build_am":
            if not self.arch:
                self.new_empty_project()
            if not self.navigation._polyhedral_mesher:
                QMessageBox.information(
                    self, "scFLOWpre",
                    "Build Analysis Model is available only when "
                    "[Mesher/Faceter Setting] – Mesher is "
                    "Polyhedral mesher.")
                return
            self._confirm_build_analysis_model()
            return
        if key not in nav_panels.DIALOG_KEYS:
            return
        if not self.arch:
            self.new_empty_project()
        ctx = self._nav_context()
        dlg = self._nav_dialogs.open(key, ctx, self)
        if dlg is None:
            return
        bbox = dlg.findChild(QDialogButtonBox)
        if bbox is not None:
            ab = bbox.button(QDialogButtonBox.Apply)
            if ab is not None:
                def _apply(_=False, k=key, c=ctx):
                    self._commit_nav_ctx(k, c)
                    if k == "execute":
                        self._run_scflow_pipeline(c)
                ab.clicked.connect(_apply)
        self.log(f"Dialog — {dlg.windowTitle()}")
        if dlg.exec_() == QDialog.Accepted:
            commit_key = (
                "build_am" if key == "build_am_detailed" else key)
            self._commit_nav_ctx(commit_key, ctx)
            if key == "build_am_detailed":
                sess = ctx.setdefault("session", {}).setdefault(
                    "build_am", {})
                if sess.get("build_requested") or sess.get(
                        "create_facet_requested"):
                    self.log(
                        "Analysis Model Wizard — parameters saved; "
                        "build/facet flagged for scFLOWpre")
                    if sess.get("build_requested"):
                        self._prepare_parts_mode = False
                        self._update_menus_for_mode()
                    self._run_bam_pipeline(ctx)
            if key == "execute":
                self._run_scflow_pipeline(ctx)
            if key == "import_part":
                self._run_import_cad(ctx)
            if key == "create_parts":
                self._run_native_create_parts(ctx)
            if key == "modify_parts":
                self._run_native_modify_parts(ctx)

    def _tessellate_xt_members(self) -> None:
        """打开工程时剖分已归档的 ``.x_t`` 成员（对齐 cab_gui）。"""
        try:
            import cad_import
        except Exception:
            return
        if not cad_import.available():
            return
        xt_items = [
            (n, d) for n, d in self.member_bytes.items()
            if n.lower().endswith((".x_t", ".xmt_txt"))]
        if not xt_items:
            return
        bodies = []
        for name, data in xt_items:
            try:
                bodies.extend(cad_import.import_xt_bytes(
                    data, adaptive=True, default_name=Path(name).stem))
            except Exception as exc:  # noqa: BLE001
                self.log(f"XT tessellation skipped {name}: {exc}", "WARN")
        if bodies:
            self.view3d.set_cad_meshes(bodies)
            self.log(
                f"CAD tessellation — {len(bodies)} body from "
                f"{len(xt_items)} .x_t member(s)")

    def _run_import_cad(self, ctx: dict) -> None:
        """Import Part File → pskernel 剖分 .x_t 并显示 CAD 预览。"""
        sess = (ctx.get("session") or {}).get("import_part") or {}
        path = (sess.get("path") or "").strip()
        if not sess.get("open_requested") or not path:
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Import", f"文件不存在：\n{path}")
            return
        suf = os.path.splitext(path)[1].lower()
        if suf not in (".x_t", ".xmt_txt"):
            self.log(
                f"Import：暂仅支持 Parasolid .x_t/.xmt_txt（当前 {suf}）",
                "WARN")
            QMessageBox.information(
                self, "Import",
                "当前仅实现 Parasolid XT（*.x_t / *.xmt_txt）的 "
                "pskernel 剖分预览。")
            return
        try:
            import cad_import
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import", str(exc))
            return
        if not cad_import.available():
            QMessageBox.warning(
                self, "Import",
                "未找到 Cradle pskernel.dll。\n"
                "请安装 Cradle CFD，或设置环境变量 CRADLE_PROGRAMS\n"
                r"指向 …\CradleCFD*\Programs_x64")
            return
        self.log(f"Import CAD — tessellating {os.path.basename(path)} …")
        QApplication.processEvents()
        try:
            bodies = cad_import.import_xt_file(path, adaptive=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import 失败", str(exc))
            self.log(f"Import failed: {exc}", "ERROR")
            return
        if not bodies:
            QMessageBox.warning(
                self, "Import",
                "未剖分出任何几何（PK_PART_receive / facet_2 空结果）。")
            return
        # 归档原始 .x_t，便于 Save As 后仍可再剖分
        try:
            raw = Path(path).read_bytes()
            base = os.path.basename(path)
            member = base if base.lower().endswith(".x_t") else f"{base}.x_t"
            self.member_bytes[member] = raw
            if self.tmp_dir:
                out = os.path.join(self.tmp_dir, member)
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                Path(out).write_bytes(raw)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Import：写入工程成员失败: {exc}", "WARN")
        self.view3d.set_cad_meshes(bodies, append=True)
        self.show_page("draw")
        n_tris = sum(len(b.tess.triangles) for b in bodies)
        n_pts = sum(len(b.tess.points) for b in bodies)
        names = ", ".join(b.name for b in bodies)
        self.log(
            f"Import OK — {len(bodies)} body ({names}); "
            f"{n_pts} pts / {n_tris} tris")
        self.property_panel.set_properties({
            "Imported CAD": os.path.basename(path),
            "Bodies": str(len(bodies)),
            "Triangles": f"{n_tris:,}",
            "Points": f"{n_pts:,}",
        })

    # -- P0-4: CreateParts / ModifyParts 原生执行（pskernel 直调）---------

    def _unit_from_ctx(self, ctx: dict) -> str:
        xenv = ctx.get("xenv")
        if xenv is None:
            return "m"
        return (xenv.get("UNIT", "MODEL_LENGTH_UNIT", "m") or "m").strip()

    def _archive_xt_member(self, name: str, xt: bytes) -> None:
        """把 body 的 x_t 写入工程成员（对齐 _run_import_cad 归档路径）。"""
        member = f"{name}.x_t"
        try:
            self.member_bytes[member] = xt
            if self.tmp_dir:
                out = os.path.join(self.tmp_dir, member)
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                Path(out).write_bytes(xt)
        except Exception as exc:  # noqa: BLE001
            self.log(f"geometry_ops：写工程成员 {member} 失败: {exc}", "WARN")

    def _drop_xt_member(self, name: str) -> None:
        member = f"{name}.x_t"
        self.member_bytes.pop(member, None)
        if self.tmp_dir:
            try:
                p = Path(self.tmp_dir) / member
                if p.exists():
                    p.unlink()
            except OSError:
                pass

    def _run_native_create_parts(self, ctx: dict) -> None:
        """Create Parts → pskernel 原生建体 + 剖分显示 + 写回工程成员。"""
        draft = (ctx.get("session") or {}).get("create_parts") or {}
        if not draft:
            return
        try:
            import geometry_ops
        except Exception as exc:  # noqa: BLE001
            self.log(f"geometry_ops 导入失败: {exc}", "WARN")
            return
        if not geometry_ops.available():
            self.log(
                "Create Parts：pskernel 不可用，仅保存参数 + VBS 宿主草稿",
                "WARN")
            QMessageBox.information(
                self, "Create Parts",
                "未找到 Cradle pskernel.dll，仅保存参数与 VBS 草稿。\n"
                r"请设置 CRADLE_PROGRAMS 指向 …\CradleCFD*\Programs_x64")
            return
        try:
            res = geometry_ops.execute_create_parts(
                draft, self._unit_from_ctx(ctx))
        except NotImplementedError as exc:
            self.log(f"Create Parts：{exc}", "INFO")
            QMessageBox.information(
                self, "Create Parts",
                f"{exc}\n已保留 VBS 宿主草稿（{draft.get('shape')}）。")
            return
        except Exception as exc:  # noqa: BLE001
            self.log(f"Create Parts 原生执行失败: {exc}", "ERROR")
            QMessageBox.critical(self, "Create Parts", str(exc))
            return
        tess = res["tess"]
        self.view3d.set_cad_meshes([tess], append=True)
        self._archive_xt_member(res["name"], res["xt"])
        self.show_page("draw")
        vol = geometry_ops.mesh_volume_m3(tess.points, tess.triangles)
        self.log(
            f"Create Parts OK — {res['name']} (tag {res['tag']}); "
            f"{len(tess.points)} pts / {len(tess.triangles)} tris / "
            f"vol {vol:.6g} m³; 已写回 {res['name']}.x_t")
        self.property_panel.set_properties({
            "Created Part": res["name"],
            "Shape": str(draft.get("shape")),
            "Tag": str(res["tag"]),
            "Volume [m³]": f"{vol:.6g}",
        })

    def _run_native_modify_parts(self, ctx: dict) -> None:
        """Modify Parts → pskernel 原生布尔/变换（MVP）+ 刷新显示。"""
        draft = (ctx.get("session") or {}).get("modify_parts") or {}
        if not draft or not draft.get("op"):
            return
        try:
            import geometry_ops
        except Exception as exc:  # noqa: BLE001
            self.log(f"geometry_ops 导入失败: {exc}", "WARN")
            return
        if not geometry_ops.available():
            self.log(
                "Modify Parts：pskernel 不可用，仅保存参数 + VBS 宿主草稿",
                "WARN")
            return
        tag_by_name: dict = {}
        for m in self.view3d._cad_meshes:
            if getattr(m, "tag", 0):
                tag_by_name[m.name] = int(m.tag)
        try:
            res = geometry_ops.execute_modify_parts(
                draft, tag_by_name, self._unit_from_ctx(ctx))
        except NotImplementedError as exc:
            self.log(f"Modify Parts：{exc}", "INFO")
            QMessageBox.information(
                self, "Modify Parts",
                f"{exc}\n已保留 VBS 宿主草稿。")
            return
        except Exception as exc:  # noqa: BLE001
            self.log(f"Modify Parts 原生执行失败: {exc}", "ERROR")
            QMessageBox.critical(self, "Modify Parts", str(exc))
            return
        # 刷新 CAD 显示：移除 consumed，追加 boolean 结果
        removed = set(res.get("removed") or [])
        if removed:
            self.view3d._cad_meshes = [
                m for m in self.view3d._cad_meshes
                if m.name not in removed]
            for n in removed:
                self._drop_xt_member(n)
        for add in res.get("added") or []:
            self.view3d._cad_meshes.append(add["tess"])
            self._archive_xt_member(add["name"], add["xt"])
        if self.view3d._started:
            self.view3d.render()
        for n in (res.get("changed") or []):
            for m in self.view3d._cad_meshes:
                if m.name == n:
                    try:
                        fresh = geometry_ops.tessellate_body(int(m.tag), n)
                        if fresh is not None:
                            m.points = fresh.points
                            m.triangles = fresh.triangles
                    except Exception:  # noqa: BLE001
                        pass
        msg = (f"Modify Parts OK — [{res['op']}] "
               + (f"changed: {', '.join(res['changed'])}" if res["changed"] else "")
               + (f"; removed: {', '.join(res['removed'])}" if res["removed"] else "")
               + (f"; added: {len(res['added'])} body" if res["added"] else ""))
        for note in res.get("notes") or []:
            msg += f"\n{note}"
        self.log(msg)
        self.show_page("draw")

    def _run_scflow_pipeline(self, ctx: dict) -> None:
        """Execute 开关打开时：用 scFLOWpre API 构建 Model/Octree/Mesh。"""
        plan = (ctx.get("session") or {}).get("execute") or {}
        if not self.archive_path:
            QMessageBox.information(self, "提示", "请先打开 PPH 项目")
            return
        from automation.pipeline_plan import steps_from_execute_plan
        steps = steps_from_execute_plan(plan)
        if not steps:
            self.log("Execute 计划未选择任何步骤")
            return
        if not plan.get("use_api"):
            self._run_native_pipeline(ctx, plan, steps)
            return
        from automation.pipeline_plan import (
            build_execute_vbs, oct_param_sect_summary)
        self.log("Execute 步骤: " + " → ".join(steps))
        out = Path(self.archive_path).with_suffix(".scflow_api.vbs")
        marker = Path(self.archive_path).with_suffix(".scflow_api.done")
        step_marker = Path(self.archive_path).with_suffix(".scflow_api.step")
        try:
            marker.unlink(missing_ok=True)
            step_marker.unlink(missing_ok=True)
        except OSError:
            pass
        sess = ctx.get("session") or {}
        octree_sess = sess.get("octree_param") or {}
        pc_sess = sess.get("parts_control") or {}
        sects = oct_param_sect_summary(octree_sess)
        if "oct" in plan and plan.get("oct") and not sects:
            self.log(
                "警告：Octree Detail 未设置 Minimum octant size / 区域 Size；"
                "宿主可能复用旧八叉树尺寸",
                "WARN")
        elif sects:
            self.log("OctParam：" + "; ".join(sects))
        build_execute_vbs(self.archive_path, plan, out, marker=marker,
                          step_marker=step_marker,
                          xenv=ctx.get("xenv"), octree_sess=octree_sess,
                          parts_control_sess=pc_sess)
        self.log(f"scFLOWpre API 脚本已生成：{out}")
        from automation import host_pipeline
        self.log(f"自动定位 scFLOWpre: {host_pipeline.locate_scflowpre()}")
        self.log(
            "正在通过 scFLOWpre API 后台执行；"
            "完成后将自动刷新 Model / Octree / Mesh。")
        self._start_api_refresh_poll(marker, step_marker=step_marker)
        self._start_api_execute_thread(out)

    def _cad_surface_points_tris(self):
        """Import 剖分预览 → (points, tris)；无 CAD 则 None。"""
        import numpy as np
        meshes = getattr(self.view3d, "_cad_meshes", None) or []
        if not meshes:
            return None
        pts_list: list = []
        tris_list: list = []
        base = 0
        for tess in meshes:
            pts = getattr(tess, "points", None)
            tris = getattr(tess, "triangles", None)
            if pts is None or tris is None:
                continue
            pts = np.asarray(pts, dtype=float).reshape(-1, 3)
            tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
            if pts.size == 0 or tris.size == 0:
                continue
            pts_list.append(pts)
            tris_list.append(tris + base)
            base += len(pts)
        if not pts_list:
            return None
        return np.vstack(pts_list), np.vstack(tris_list)

    def _native_surface(self, part_path: Optional[str] = None):
        """原生 Execute 表面：优先 MDL，其次 Import CAD 剖分。"""
        import voxmesh
        if part_path:
            try:
                return voxmesh.surface_from_mdl(part_path), "MDL"
            except Exception as exc:  # noqa: BLE001
                self.log(f"Execute（原生模式）MDL 读取失败，尝试 CAD：{exc}",
                         "WARN")
        cad = self._cad_surface_points_tris()
        if cad is not None:
            return cad, "CAD"
        return None, None

    def _is_native_mdl(self, member_name: str) -> bool:
        """MDL 成员是否为本进程原生生成（Application 块 = pphdecoding）。

        仅原生生成的 MDL 允许被原生 BAM 覆写；宿主 MDL 保留原样。
        """
        try:
            head = bytes(self.arch.read_member(member_name)[:4096])
        except Exception:  # noqa: BLE001
            return False
        return b"pphdecod" in head

    def _native_member_names(self) -> tuple[str, str, str]:
        """MDL/OCT/GPH 成员名：已有则复用，空工程则追加 meshinggroup1.*。"""
        import pph_parser
        part_name = "meshinggroup1_part.mdl"
        oct_name = "meshinggroup1.oct"
        gph_name = "meshinggroup1.gph"
        if self.arch:
            pm = self.arch.by_role(pph_parser.ROLE_MDL_PART)
            om = self.arch.by_role(pph_parser.ROLE_OCT)
            gm = self.arch.by_role(pph_parser.ROLE_GPH)
            if pm:
                part_name = pm[0].name
            if om:
                oct_name = om[0].name
            if gm:
                gph_name = gm[0].name
        return part_name, oct_name, gph_name

    def _native_wrap_member_name(self) -> str:
        """Wrapping 生成的 MDL 成员名：已有 *_wrap.mdl 则复用。"""
        if self.arch:
            for m in self.arch.members:
                if "_wrap.mdl" in m.name.lower():
                    return m.name
        return "meshinggroup1_wrap.mdl"

    def _run_native_pipeline(self, ctx: dict, plan: dict,
                             steps: list[str]) -> None:
        """未启用 scFLOWpre API 时：用自研算法原生生成 Octree/Mesh。

        表面来源：工程内 MDL part，或 Import 的 CAD 剖分（Untitled + XT 预览）。
        空工程无 OCT/GPH 占位时，向 PPH 追加 ``meshinggroup1.oct/.gph``。
        """
        import pph_parser
        import pphwriter

        part_path = None
        for _g, info in (self._groups_info or {}).items():
            part_path = ((info.get("paths") or {}).get("part")
                         or info.get("part"))
            if part_path:
                break
        try:
            surface, src_kind = self._native_surface(part_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Execute（原生模式）", f"读取表面失败：{exc}")
            return
        if surface is None:
            QMessageBox.information(
                self, "Execute（原生模式）",
                "未找到 MDL part 或 Import CAD 剖分。\n"
                "请先 File → Import 导入 XT，或打开含 MDL 的工程。")
            return
        if not self.tmp_dir:
            self.tmp_dir = tempfile.mkdtemp(prefix="pph_gui_")
        points, tris = surface
        part_name, oct_name, gph_name = self._native_member_names()
        overrides: dict[str, bytes] = {}
        msgs: list[str] = []
        need_oct = any(s == "generate_octree" for s in steps)
        need_mesh = any(s == "generate_mesh" for s in steps)
        bam_result = None
        if any(s == "build_analysis_model" for s in steps):
            # 原生 BAM：对齐 Analysis Model Wizard 步骤（native_bam.py）——
            # CreateBoundary 闭体识别 → 多重边/面 → 面匹配 → 微小面去除 →
            # Repair → CheckMDLErrors，产物含 csid/frid/区域/闭体/ridge。
            import native_bam
            bam_sess = (ctx.get("session") or {}).get("build_am") or {}
            try:
                bam_result = native_bam.build_analysis_model(
                    points, tris,
                    native_bam.BamParams.from_session(bam_sess, self._xenv))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(
                    self, "Execute（原生模式）", f"原生 BAM 失败：{exc}")
                return
            points, tris = bam_result.tris()
            rep = bam_result.report
            bam_sess = (ctx.get("session") or {}).setdefault("build_am", {})
            bam_sess["native_report"] = {
                "rows": list(rep.rows),
                "closed_volumes": rep.n_closed_volumes,
                "buildable": rep.buildable,
                "summary": rep.summary_lines(),
            }
            msgs.append(
                f"BAM(闭体{rep.n_closed_volumes},多重边{rep.n_multifold_edges},"
                f"匹配{rep.n_matched_pairs},微小面-{rep.n_tiny_removed},"
                f"ridge{rep.n_ridge_edges})")
        if plan.get("wrapping"):
            try:
                import mdl as mdlmod
                tmp = Path(self.tmp_dir) / "native_wrap.mdl"
                mdlmod.write_mdl(
                    tmp, points, tris, app="pphdecoding", date=20260814)
                overrides[self._native_wrap_member_name()] = tmp.read_bytes()
                msgs.append("Wrapping(CAD→MDL)")
            except Exception as exc:  # noqa: BLE001
                self.log(f"Execute（原生模式）Wrapping 写出失败: {exc}",
                         "WARN")
        mdl_members = self.arch.by_role(pph_parser.ROLE_MDL_PART)
        if bam_result is not None:
            # 写出完整 *_part.mdl（csid/frid/区域/闭体/ridge 状态）。
            # 宿主生成的 MDL 不覆盖（避免丢失宿主 ridge/区域信息），仅更新报告。
            if (not mdl_members or src_kind == "CAD"
                    or self._is_native_mdl(mdl_members[0].name)):
                try:
                    tmp = Path(self.tmp_dir) / "native_part.mdl"
                    native_bam.write_bam_mdl(bam_result, tmp, date=20260814)
                    overrides[part_name] = tmp.read_bytes()
                    msgs.append("MDL(BAM)")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Execute（原生模式）MDL 写出失败: {exc}", "WARN")
            else:
                self.log("Execute（原生模式）：保留宿主 MDL，"
                         "原生 BAM 仅更新检测报告")
        elif src_kind == "CAD" and not mdl_members:
            # 未跑 BAM 时保持原行为：从 x_t 剖分生成最小 *_part.mdl 成员，
            # 让 Part Tree / 几何显示不依赖内存 CAD 预览。
            try:
                import mdl as mdlmod
                tmp = Path(self.tmp_dir) / "native_part.mdl"
                mdlmod.write_mdl(
                    tmp, points, tris, app="pphdecoding", date=20260814)
                overrides[part_name] = tmp.read_bytes()
                msgs.append("MDL(CAD生成)")
            except Exception as exc:  # noqa: BLE001
                self.log(f"Execute（原生模式）MDL 写出失败: {exc}", "WARN")
        for step in steps:
            if step == "generate_octree":
                try:
                    import oct as octmod
                    import voxmesh
                    root_min, root_max, refinement, leaves = \
                        voxmesh.build_octree(
                            points, tris,
                            voxmesh.VoxelMeshParams(
                                initial_depth=2, max_depth=4,
                                max_cells=500_000))
                    tmp = Path(self.tmp_dir) / "native_oct.oct"
                    octmod.write_oct(tmp, root_min, root_max,
                                     refinement, date=20260814)
                    overrides[oct_name] = tmp.read_bytes()
                    msgs.append(f"Octree({len(leaves):,}叶)")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Execute（原生模式）Octree 生成失败: {exc}",
                             "WARN")
            elif step == "generate_mesh":
                if plan.get("mesh_mode") == "Use existing":
                    msgs.append("Mesh(Use existing)")
                    continue
                mesher = "0"
                if self._xenv is not None:
                    mesher = (self._xenv.get("MESH", "MESHER", "0")
                              or "0")
                try:
                    tmp = Path(self.tmp_dir) / "native_mesh"
                    if mesher == "1":
                        import voxmesh
                        result, oct_p, gph_p = voxmesh.build_from_surface(
                            points, tris, tmp,
                            voxmesh.VoxelMeshParams(
                                initial_depth=2, max_depth=4,
                                max_cells=500_000, rough_poly=True))
                        kind = "voxel"
                        if need_oct and oct_name not in overrides:
                            overrides[oct_name] = oct_p.read_bytes()
                    else:
                        import polymesh
                        result, gph_p = polymesh.build_from_surface(
                            points, tris, tmp,
                            polymesh.PolyMeshParams(
                                divisions=10, surface_stride=12,
                                max_cells=200_000,
                                lloyd_iterations=2,
                                feature_preserve=True))
                        kind = "poly"
                    overrides[gph_name] = gph_p.read_bytes()
                    st = result.stats()
                    msgs.append(
                        f"Mesh({kind},{st['n_cells']:,}单元)")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Execute（原生模式）Mesh 生成失败: {exc}",
                             "WARN")
            elif step in ("build_analysis_model", "set_mode_octree",
                          "set_mode_mesh", "save_project"):
                continue
        if not overrides:
            hint = ""
            if need_oct or need_mesh:
                hint = "（Octree/Mesh 生成未写出，见 Message 日志）"
            self.log("Execute（原生模式）：无可写回成员，计划已保存" + hint)
            QMessageBox.information(
                self, "Execute（原生模式）",
                "已保存 Execute 计划，但没有可写回的 OCT/GPH。\n"
                "请确认已勾选 Generate Octree / Generate Mesh，"
                "并查看 Message 窗口是否有生成失败日志。")
            return
        dst = Path(self.archive_path).with_suffix(".native.pph")
        try:
            pphwriter.clone_pph(self.archive_path, dst, overrides)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Execute（原生模式）",
                                 f"写回 PPH 失败：{exc}")
            return
        self.log("Execute（原生模式）: " + " → ".join(msgs))
        self.log(f"Execute（原生模式）已写回: {dst}")
        self.open_archive(str(dst))
        QMessageBox.information(
            self, "Execute（原生模式）",
            f"已用自研算法生成并写回：\n{dst}\n\n"
            + "\n".join(msgs))

    def _run_bam_pipeline(self, ctx: dict) -> None:
        """Analysis Model Wizard 的 Create Facet / Build → 宿主 VBS 并自动刷新。"""
        if not self.archive_path:
            QMessageBox.information(self, "提示", "请先打开 PPH 项目")
            return
        plan = (ctx.get("session") or {}).get("execute") or {}
        if not plan.get("use_api", True):
            self._run_native_bam(ctx)
            return
        from automation.pipeline_plan import build_execute_vbs
        out = Path(self.archive_path).with_suffix(".bam.vbs")
        marker = Path(self.archive_path).with_suffix(".bam.done")
        step_marker = Path(self.archive_path).with_suffix(".bam.step")
        try:
            marker.unlink(missing_ok=True)
            step_marker.unlink(missing_ok=True)
        except OSError:
            pass
        build_execute_vbs(
            self.archive_path, {"bam": True}, out, marker=marker,
            step_marker=step_marker,
            xenv=ctx.get("xenv"),
            octree_sess=(ctx.get("session") or {}).get("build_am_octree"),
            parts_control_sess=(ctx.get("session") or {}).get(
                "parts_control"))
        # BAM Wizard Match/tiny 等步骤：追加为注释，便于录制对拍
        bam = (ctx.get("session") or {}).get("build_am") or {}
        steps = list(bam.get("vbs_steps") or [])
        if steps:
            text = out.read_text(encoding="utf-8", errors="replace")
            extra = "\n".join(f"' BAM wizard step: {s}" for s in steps)
            out.write_text(text + "\n" + extra + "\n", encoding="utf-8")
            self.log(f"BAM wizard VBS steps: {steps}")
        self.log(f"Analysis Model Wizard 脚本已生成：{out}")
        self.log(
            "正在通过 scFLOWpre API 后台执行；"
            "完成后将自动刷新分析模型。")
        self._start_api_refresh_poll(marker, step_marker=step_marker)
        self._start_api_execute_thread(out)

    def _run_native_bam(self, ctx: dict) -> None:
        """向导 Build/Create Facet 且未启用 scFLOWpre API → 原生 BAM。

        与 Execute 原生模式的 BAM 段共用 :mod:`native_bam` 管线；
        写回 ``*.native.pph`` 并刷新。
        """
        import pph_parser
        import pphwriter

        part_path = None
        for _g, info in (self._groups_info or {}).items():
            part_path = ((info.get("paths") or {}).get("part")
                         or info.get("part"))
            if part_path:
                break
        try:
            surface, src_kind = self._native_surface(part_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "BAM（原生模式）", f"读取表面失败：{exc}")
            return
        if surface is None:
            QMessageBox.information(
                self, "BAM（原生模式）",
                "未找到 MDL part 或 Import CAD 剖分。")
            return
        if not self.tmp_dir:
            self.tmp_dir = tempfile.mkdtemp(prefix="pph_gui_")
        import native_bam
        points, tris = surface
        bam_sess = (ctx.get("session") or {}).get("build_am") or {}
        try:
            result = native_bam.build_analysis_model(
                points, tris,
                native_bam.BamParams.from_session(bam_sess, self._xenv))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "BAM（原生模式）", f"原生 BAM 失败：{exc}")
            return
        rep = result.report
        sess = (ctx.get("session") or {}).setdefault("build_am", {})
        sess["native_report"] = {
            "rows": list(rep.rows),
            "closed_volumes": rep.n_closed_volumes,
            "buildable": rep.buildable,
            "summary": rep.summary_lines(),
        }
        part_name, _oct_name, _gph_name = self._native_member_names()
        mdl_members = self.arch.by_role(pph_parser.ROLE_MDL_PART)
        if mdl_members and src_kind != "CAD" and not self._is_native_mdl(
                mdl_members[0].name):
            self.log("BAM（原生模式）：保留宿主 MDL，仅更新检测报告")
            QMessageBox.information(
                self, "BAM（原生模式）",
                "分析模型检查完成（宿主 MDL 未改动）：\n\n"
                + "\n".join(rep.summary_lines()))
            return
        tmp = Path(self.tmp_dir) / "native_bam_part.mdl"
        try:
            native_bam.write_bam_mdl(result, tmp, date=20260814)
            dst = Path(self.archive_path).with_suffix(".native.pph")
            pphwriter.clone_pph(
                self.archive_path, dst, {part_name: tmp.read_bytes()})
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "BAM（原生模式）", f"写回失败：{exc}")
            return
        self.log("BAM（原生模式）: " + "；".join(rep.summary_lines()))
        self.open_archive(str(dst))
        QMessageBox.information(
            self, "BAM（原生模式）",
            f"已生成分析模型并写回：\n{dst}\n\n"
            + "\n".join(rep.summary_lines()))

    def _start_api_refresh_poll(self, marker: Path,
                                step_marker: Optional[Path] = None,
                                timeout: float = 600.0) -> None:
        """轮询宿主 VBS 写出的完成标记，出现后自动 Reload。"""
        start = time.monotonic()

        def poll() -> None:
            if step_marker is not None and step_marker.is_file():
                try:
                    steps = step_marker.read_text(
                        encoding="utf-8", errors="replace").split()
                    if steps and steps[-1] != self._last_api_step:
                        self._last_api_step = steps[-1]
                        self.log(f"scFLOWpre API 当前步骤: {steps[-1]}")
                except OSError:
                    pass
            if marker.is_file():
                self.log("scFLOWpre API 完成，正在刷新项目…")
                try:
                    marker.unlink(missing_ok=True)
                except OSError:
                    pass
                self.reload()
                self.log("已刷新 Model / Octree / Mesh")
                return
            if time.monotonic() - start > timeout:
                self.log(
                    f"等待 scFLOWpre API 完成超时（>{timeout:g}s），"
                    "停止轮询；可手动执行脚本后 Reload", "WARN")
                return
            QTimer.singleShot(2000, poll)
        QTimer.singleShot(2000, poll)

    def _start_api_execute_thread(self, vbs: Path) -> None:
        """后台调用宿主 COM API 执行 VBS；失败时回退为手动提示。"""
        def worker() -> None:
            try:
                from automation import host_pipeline
                result = host_pipeline.run_in_host(vbs, backend="com")
                self.log(f"scFLOWpre API 执行返回: {result}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"scFLOWpre API 自动执行失败: {exc}", "WARN")
                self.log(
                    f"请手动在 scFLOWpre 中 File → Execute VBScript 执行 "
                    f"{vbs}", "WARN")
        threading.Thread(target=worker, daemon=True).start()

    def reload(self) -> None:
        if self.archive_path:
            self.open_archive(self.archive_path)

    def _cleanup(self) -> None:
        if self.tmp_dir:
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self.tmp_dir = None

    def save_as_dialog(self) -> None:
        if not self.arch:
            QMessageBox.information(self, "提示", "请先打开文件")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为 PPH", "", "PPH 文件 (*.pph)")
        if not path:
            return
        overrides = self.editor_tab.overrides()
        try:
            pphwriter.rewrite_pph(self.archive_path, path, overrides)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.log(f"Saved {path}"
                 + (f" (overrides: {list(overrides)})" if overrides else ""))
        QMessageBox.information(self, "完成", f"已写出 {path}")

    # ── Navigation ──────────────────────────────────────────────────
    def _on_navigate(self, key: str) -> None:
        if key == "open":
            self.open_dialog()
        elif key == "reload":
            self.reload()
        elif key == "save":
            self.save_as_dialog()
        elif key == "dashboard":
            self.show_page("dashboard")
            self.dashboard.populate()
            self.log("Dashboard")
        elif key in ("view3d", "view_part"):
            self.show_page("draw")
            self.view3d.set_view_mode("geometry")
            self.view3d.chk_mdl_part.setChecked(True)
            self.view3d.chk_oct.setChecked(False)
            self.view3d.chk_gph.setChecked(False)
            self.view3d.render()
            self.log("View — Part (geometry)")
        elif key == "view_octree":
            self.show_page("draw")
            self.view3d.set_view_mode("octree")
            self.view3d.chk_oct.setChecked(True)
            self.view3d.render()
            self.log("View — Octree")
        elif key == "view_mesh":
            self.show_page("draw")
            self.view3d.set_view_mode("mesh")
            self.view3d.chk_gph.setChecked(True)
            # 网格模式默认不透明、关闭 owner 着色
            self.view3d.display_mode.setCurrentText("不透明")
            self.view3d.chk_gph_color.setChecked(False)
            self.view3d.render()
            self.log("View — Mesh (opaque, owner coloring off)")
        elif key == "view_section":
            self.show_page("draw")
            self.view3d.set_view_mode("mesh")
            self.view3d.chk_gph.setChecked(True)
            self.view3d.chk_section.setChecked(True)
            self.view3d.section_target.setCurrentText("体网格")
            self.log("View — Cross Section: set plane then Draw")
        elif key == "view_show_all":
            self.show_page("draw")
            self.view3d.clear_visibility()
            self.log("View — Show All")
        elif key == "snapshot":
            self.show_page("snapshot")
            self.log("Snapshot / Parasolid")
        elif key == "build_am":
            # 不在 PANEL_CLASSES（确认框走 QMessageBox，非 NavParamDialog）
            self._show_condition(key)
            self.show_page("draw")
        elif key in nav_panels.PANEL_CLASSES:
            self._show_condition(key)
            if key == "regions":
                self._focus_status("geometry")
            elif key == "oct_param":
                self._focus_status("octree")
            elif key == "mesh_param":
                self._focus_status("mesh")
        elif key in ("project", "gph", "oct", "mdl", "xml", "js", "groups"):
            name = self._member_for_nav(key)
            if name:
                self._select_member(name)
                self.log(f"Selected member: {name}")
            else:
                self.log(f"No member for '{key}'", "WARN")

    def _member_for_nav(self, key: str) -> Optional[str]:
        if key == "project":
            return "main.xenv"
        if key == "xml":
            return "main.xml"
        if key == "js":
            return "main.js"
        for m in self.arch.members if self.arch else []:
            if key == "gph" and m.name.lower().endswith(".gph"):
                return m.name
            if key == "oct" and m.name.lower().endswith(".oct"):
                return m.name
            if key == "mdl" and m.name.lower().endswith("_part.mdl"):
                return m.name
            if key == "groups" and m.name.lower().endswith(".gph"):
                return m.name
        return None

    def _select_member(self, name: str) -> None:
        item = self._find_tree_item(name)
        if item is not None:
            self.member_tree.setCurrentItem(item)
            self._on_member_clicked(item, 0)
            self.member_tree.scrollToItem(item)

    def _build_model_tree(self) -> None:
        """解析各网格组 MDL/OCT/GPH 摘要，填充模型树与 Status。"""
        import mdl

        groups: dict[str, dict] = {}
        self.model_models: dict[str, dict] = {}
        # 收集路径
        for name, path in self.bin_paths.items():
            g = _member_group(name)
            if not g:
                continue
            info = groups.setdefault(g, {"paths": {}, "part": None,
                                         "oct_summary": None,
                                         "gph_summary": None})
            low = name.lower()
            if low.endswith("_part.mdl"):
                info["paths"]["part"] = path
            elif low.endswith("_ridge.mdl"):
                info["paths"]["ridge"] = path
            elif low.endswith(".oct"):
                info["paths"]["oct"] = path
            elif low.endswith(".gph"):
                info["paths"]["gph"] = path

        self.status_panel.clear()
        for g, info in groups.items():
            part_path = info["paths"].get("part")
            if part_path:
                try:
                    model = mdl.parse_mdl(part_path, load_arrays=True)
                except Exception:  # noqa: BLE001
                    model = None
                info["part"] = model
                self.model_models[g] = {"part": model, "part_path": part_path}
            oct_path = info["paths"].get("oct")
            if oct_path:
                try:
                    import oct
                    om = oct.parse_oct(oct_path)
                    # 不遍历全部叶子求深度（百万级叶子可达数秒）
                    info["oct_summary"] = {
                        "n_octants": om.n_octants,
                        "n_internal": om.n_internal,
                        "n_leaves": om.n_leaves,
                        "unit": om.unit,
                        "max_depth": "—",
                    }
                except Exception:  # noqa: BLE001
                    info["oct_summary"] = None
            gph_path = info["paths"].get("gph")
            if gph_path:
                try:
                    import gphstats
                    large = os.path.getsize(gph_path) > 32 * 1024 * 1024
                    if large:
                        self.log(f"解析网格摘要 {g} …")
                        QApplication.processEvents()
                    with gphstats.open_buffer(gph_path) as data:
                        # 大文件用 quick，避免 nodes 全表扫描卡死 UI
                        if large:
                            info["gph_summary"] = gphstats.summarize_quick(data)
                        else:
                            info["gph_summary"] = gphstats.summarize(data)
                except Exception:  # noqa: BLE001
                    info["gph_summary"] = None
            QApplication.processEvents()

        project_name = ""
        regions_meta: dict = {}
        xml_parts_by_group: dict[str, list] = {}
        if "main.xml" in self.member_bytes:
            try:
                mx = pphxml.parse_main_xml(self.member_bytes["main.xml"])
                project_name = mx.project_name or ""
                regions_meta, xml_parts_by_group = _extract_part_tree_meta(mx)
            except Exception as exc:  # noqa: BLE001
                self.log(f"Part Tree XML 解析失败: {exc}", "WARN")
        if not project_name and self.archive_path:
            project_name = os.path.splitext(
                os.path.basename(self.archive_path))[0]
        # 将 XML 零件挂到网格组（名粗匹配 meshinggroup*）
        for g, info in groups.items():
            parts_list = xml_parts_by_group.get(g)
            if parts_list is None and len(xml_parts_by_group) == 1:
                parts_list = next(iter(xml_parts_by_group.values()))
            if parts_list is None:
                # 按 sgs / 组名模糊匹配
                for key, plist in xml_parts_by_group.items():
                    if key.replace("_", "").lower() in g.replace("_", "").lower() \
                            or g.replace("_", "").lower() in key.replace("_", "").lower():
                        parts_list = plist
                        break
            info["xml_parts"] = parts_list or []

        # Surface Region：用 MDL 名称匹配 frid
        for se in regions_meta.get("face") or []:
            for g, info in groups.items():
                m = info.get("part")
                if m is None:
                    continue
                for r in m.surface_regions:
                    if r.name == se["name"]:
                        se["frid"] = int(r.index)
                        se["group"] = g
                        break

        self.model_tree.populate(
            groups, project_name=project_name, regions_meta=regions_meta)
        self._groups_info = groups
        self._regions_meta = regions_meta
        for g in groups:
            self.status_panel.set_group_status(
                g, self.model_tree.group_status_props(g))
            # 批量设置图层，避免三次完整 Render（大 GPH 极慢）
            self.view3d.set_layer_visibility(g, "mdl", True, refresh=False)
            self.view3d.set_layer_visibility(g, "gph", True, refresh=False)
            self.view3d.set_layer_visibility(g, "oct", False, refresh=False)
        if groups:
            self.status_panel.show_group(sorted(groups)[0])
        self.view3d.precache(self.model_models)

    def _on_model_item_selected(self, props: dict) -> None:
        self.property_panel.set_properties(props)

    def _on_status_requested(self, group: str, focus: str) -> None:
        st = self.model_tree.group_status_props(group)
        self.status_panel.set_group_status(group, st)
        self.status_panel.show_group(group, focus or None)
        label = {"geometry": "几何", "octree": "八叉树",
                 "mesh": "体网格"}.get(focus, "状态")
        self.prop_tabs.setCurrentWidget(self.status_panel)
        self.log(f"{group} — {label}")

    def _focus_model_3d(self, group: str) -> None:
        self.show_page("draw")
        self.view3d.select_group(group)

    def _select_mesh_view(self, group: str) -> None:
        self.show_page("draw")
        self.view3d.select_group(group)
        self.view3d.set_view_mode("mesh")
        self.view3d.chk_gph.setChecked(True)
        self.view3d.display_mode.setCurrentText("不透明")
        self.view3d.chk_gph_color.setChecked(False)
        self.view3d.chk_section.setChecked(True)
        self.view3d.section_target.setCurrentText("体网格")
        self.log(f"{group}: mesh view — set plane then Draw section")

    def _on_layer_visibility(self, group: str, layer: str,
                             visible: bool) -> None:
        self.view3d.set_layer_visibility(group, layer, visible)
        self.log(f"{group}: layer {layer} = "
                 f"{'on' if visible else 'off'}")

    def _on_model_visibility(self, group: str, hidden_bodies: set,
                             hidden_regions: set, group_visible: bool) -> None:
        """模型树勾选 → 更新 3D 显隐（不跳转标签页，避免打断操作）。"""
        self.view3d.set_model_visibility(
            group, hidden_bodies, hidden_regions, group_visible)
        n_hidden = len(hidden_bodies) + len(hidden_regions)
        if n_hidden or not group_visible:
            self.log(
                f"{group}: {'hidden' if not group_visible else 'visible'}, "
                f"{n_hidden} items unchecked")
        else:
            self.log(f"{group}: show all")

    def _show_all_models(self) -> None:
        """3D「恢复全部」→ 模型树全部勾选。"""
        self.model_tree._set_all("", True)
        self.log("Show All")

    def _find_tree_item(self, name: str) -> Optional[QTreeWidgetItem]:
        stack = [self.member_tree.topLevelItem(i)
                 for i in range(self.member_tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, Qt.UserRole) == name:
                return item
            for i in range(item.childCount()):
                stack.append(item.child(i))
        return None

    # ── 成员树 ──────────────────────────────────────────────────────
    def _populate_tree(self) -> None:
        self.member_tree.clear()
        text_root = QTreeWidgetItem(["文本成员", "main.js / prp / xenv / xml", ""])
        text_root.setIcon(0, AppIcons.get("script", 16))
        snap_root = QTreeWidgetItem(["快照", "main.sctsnapshot", ""])
        snap_root.setIcon(0, AppIcons.get("snapshot", 16))
        group_roots: dict[str, QTreeWidgetItem] = {}
        role_icon = {
            pph_parser.ROLE_PROJECT_XML: "xml",
            pph_parser.ROLE_SCRIPT: "script",
            pph_parser.ROLE_PRP: "project",
            pph_parser.ROLE_XENV: "project",
            pph_parser.ROLE_SNAPSHOT: "snapshot",
            pph_parser.ROLE_GPH: "mesh",
            pph_parser.ROLE_OCT: "octree",
            pph_parser.ROLE_MDL_PART: "part",
            pph_parser.ROLE_MDL_RIDGE: "part",
        }
        for m in self.arch.members:
            item = QTreeWidgetItem([m.name, m.description, f"{m.size:,}"])
            item.setData(0, Qt.UserRole, m.name)
            item.setToolTip(0, m.name)
            item.setIcon(0, AppIcons.get(role_icon.get(m.role, "generic"), 16))
            if m.role in (pph_parser.ROLE_PROJECT_XML, pph_parser.ROLE_SCRIPT,
                          pph_parser.ROLE_PRP, pph_parser.ROLE_XENV):
                text_root.addChild(item)
            elif m.role == pph_parser.ROLE_SNAPSHOT:
                snap_root.addChild(item)
            else:
                g = _member_group(m.name)
                root = group_roots.setdefault(
                    g or m.name, QTreeWidgetItem([g or m.name, "网格组", ""]))
                if root.icon(0).isNull():
                    root.setIcon(0, AppIcons.get("group", 16))
                root.addChild(item)
        for root in (text_root, snap_root):
            if root.childCount():
                self.member_tree.addTopLevelItem(root)
                root.setExpanded(True)
        for root in group_roots.values():
            if root.childCount():
                self.member_tree.addTopLevelItem(root)
        self.member_tree.expandToDepth(1)

    def _member_context_menu(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu

        item = self.member_tree.itemAt(pos)
        if item is None:
            return
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        menu = QMenu(self)
        act_prop = menu.addAction("属性")
        act_3d = menu.addAction("在 3D 中显示")
        act_text = menu.addAction("在文本中打开")
        act_deep = None
        role, _ = pph_parser.classify_member(name)
        if role not in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                        pph_parser.ROLE_XENV, pph_parser.ROLE_PROJECT_XML,
                        pph_parser.ROLE_SNAPSHOT):
            act_deep = menu.addAction("解析属性（深度）")
        act = menu.exec_(self.member_tree.viewport().mapToGlobal(pos))
        if act is act_prop:
            self._show_member_properties(name)
        elif act is act_3d:
            self.show_page("draw")
            g = _member_group(name)
            if g and g in self.view3d.groups:
                self.view3d.group_box.setCurrentText(g)
        elif act is act_text:
            self._on_member_clicked(item, 0)
        elif act is act_deep:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                m2 = next((x for x in self.arch.members
                           if x.name == name), None)
                base = {
                    "成员": name,
                    "角色": m2.description if m2 else "",
                    "大小": f"{m2.size:,} B" if m2 else "",
                }
                self.property_panel.set_properties(
                    {**base, **self._binary_member_props(name)})
            finally:
                QApplication.restoreOverrideCursor()

    def _on_member_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        data = self.member_bytes.get(name)
        if data is None:
            return
        role, _ = pph_parser.classify_member(name)
        self._show_member_properties(name)
        if role in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                    pph_parser.ROLE_XENV, pph_parser.ROLE_PROJECT_XML):
            self.show_page("editor")
            self.editor_tab.load_member(name, data)
        elif role == pph_parser.ROLE_SNAPSHOT:
            self.show_page("snapshot")

    def _show_member_properties(self, name: str) -> None:
        m = next((x for x in self.arch.members if x.name == name), None)
        if m is None:
            return
        props = {
            "成员": name,
            "角色": m.description,
            "大小": f"{m.size:,} B",
            "压缩后": f"{m.compress_size:,} B",
        }
        role, _ = pph_parser.classify_member(name)
        if role in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                    pph_parser.ROLE_XENV, pph_parser.ROLE_PROJECT_XML):
            props.update(self._text_member_props(name))
        elif role == pph_parser.ROLE_SNAPSHOT:
            props.update(self._snapshot_props())
        elif self.bin_paths.get(name):
            # 轻量：单击不触发深度解析（大文件会卡界面）
            props["类型"] = {
                pph_parser.ROLE_GPH: "GPH 体网格",
                pph_parser.ROLE_OCT: "OCT 八叉树",
                pph_parser.ROLE_MDL_PART: "MDL 面片几何",
                pph_parser.ROLE_MDL_RIDGE: "MDL ridge 细节",
            }.get(role, "二进制成员")
            props["提示"] = "右键 →「解析属性（深度）」获取详细统计"
        self.property_panel.set_properties(props)

    def _text_member_props(self, name: str) -> dict:
        data = self.member_bytes.get(name, b"")
        try:
            if name == "main.xenv":
                import pphxml
                xenv = pphxml.parse_xenv(data)
                return {"Section 数": len(xenv.sections),
                        "Key 总数": sum(len(v) for v in xenv.sections.values())}
            if name == "main.prp":
                import pphxml
                prp = pphxml.parse_prp(data)
                return {"物性组数": len(prp.group_names()),
                        "版本": prp.version}
            if name == "main.js":
                import pphxml
                js = pphxml.parse_main_js(data)
                return {"函数数": len(js.functions())}
            if name == "main.xml":
                import pphxml
                root = pphxml.ET.fromstring(
                    pphxml.sanitize_scflow_xml(
                        data.decode("utf-8", errors="replace")))
                return {"顶层标签": root.tag,
                        "顶层子节点": len(list(root))}
        except Exception as exc:  # noqa: BLE001
            return {"解析": f"失败: {exc}"}
        return {}

    def _snapshot_props(self) -> dict:
        if self.snap is None:
            return {}
        props = {"顶层记录": len(self.snap.records),
                 "未对齐字节": self.snap.skipped_bytes}
        try:
            bodies = self.snap.bodies()
            props["Parasolid 体"] = len(bodies)
            if bodies:
                import parasolid
                ps = parasolid.parse_transmit(
                    bodies[0]["zip"].decompress_body().decrypt())
                props["Schema"] = ps.schema
                props["版本"] = ps.version
                props["实体"] = ", ".join(ps.entities)
        except Exception as exc:  # noqa: BLE001
            props["体解析"] = f"失败: {exc}"
        return props

    def _binary_member_props(self, name: str) -> dict:
        path = self.bin_paths.get(name)
        if not path:
            return {}
        try:
            if name.lower().endswith(".gph"):
                import gphstats
                with gphstats.open_buffer(path) as data:
                    s = gphstats.summarize(data)
                links = s["links"] or {}
                return {
                    "类型": "GPH 体网格",
                    "面": f"{links.get('n_faces', 0):,}",
                    "单元": f"{links.get('n_cells', 0):,}",
                    "顶点": f"{s['n_vertices']:,} ({s['dialect']})",
                    "边界面": f"{links.get('boundary_faces', 0):,}",
                    "npe": f"[{links.get('npe_min', 0)}.."
                           f"{links.get('npe_max', 0)}]",
                    "体区域": s["volume_regions"],
                    "面区域": [n for n, _ in s["surface_regions"]],
                }
            if name.lower().endswith(".oct"):
                import oct
                om = oct.parse_oct(path)
                return {
                    "类型": "OCT 八叉树",
                    "节点": f"{om.n_octants:,}",
                    "内部": f"{om.n_internal:,}",
                    "叶子": f"{om.n_leaves:,}",
                    "单位": om.unit,
                }
            if name.lower().endswith(".mdl"):
                import mdl
                m = mdl.parse_mdl(path, load_arrays=False)
                return {
                    "类型": "MDL 面片几何",
                    "顶点": f"{m.n_vertices:,}",
                    "面": f"{m.n_faces:,}",
                    "闭体": m.n_closed_volumes,
                    "体区域": m.volume_regions,
                    "面区域": [(r.name, r.index)
                               for r in m.surface_regions],
                }
        except Exception as exc:  # noqa: BLE001
            return {"解析": f"失败: {exc}"}
        return {}

    def _binary_details(self, name: str) -> str:
        props = self._binary_member_props(name)
        lines = [f"[{name}]"]
        for k, v in props.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def _archive_properties(self) -> dict:
        roles: dict[str, int] = {}
        for m in self.arch.members:
            roles[m.role] = roles.get(m.role, 0) + 1
        return {
            "归档": self.archive_path,
            "成员数": len(self.arch.members),
            "总大小": _fmt_size(sum(m.size for m in self.arch.members)),
            "角色分布": {k: f"{v} 个" for k, v in sorted(roles.items())},
        }

    # ── 快照 / 3D ───────────────────────────────────────────────────
    def _load_snapshot_member(self) -> None:
        for name, path in self.bin_paths.items():
            if pph_parser.classify_member(name)[0] == pph_parser.ROLE_SNAPSHOT:
                try:
                    import sctsnapshot
                    self.snap = sctsnapshot.SctSnapshot.load(path)
                    bodies = self.snap.bodies()
                    lines = [f"记录树 {len(self.snap.records)} 条顶层记录, "
                             f"未对齐字节 {self.snap.skipped_bytes}"]
                    if bodies:
                        lines.append(f"Parasolid 体: {len(bodies)} 个")
                    self.snapshot_tab.load_snapshot(
                        self.snap, "\n".join(lines))
                except Exception as exc:  # noqa: BLE001
                    self.snapshot_tab.summary.setPlainText(
                        f"快照解析失败: {exc}")
                return

    def _populate_3d(self) -> None:
        groups: dict[str, dict] = {}
        for name, path in self.bin_paths.items():
            if name.lower().endswith((".gph", ".oct", ".mdl")):
                g = _member_group(name)
                groups.setdefault(g, {})
                if name.lower().endswith("_part.mdl"):
                    groups[g]["part"] = path
                elif name.lower().endswith("_ridge.mdl"):
                    groups[g]["ridge"] = path
                elif name.lower().endswith(".oct"):
                    groups[g]["oct"] = path
                elif name.lower().endswith(".gph"):
                    groups[g]["gph"] = path
        self.view3d.set_groups(groups)


def main(argv: Optional[list[str]] = None) -> int:
    # Windows 常见无害警告：系统无 EUDC.TTE（用户自定义汉字字体）
    os.environ.setdefault(
        "QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")
    app = QApplication(argv if argv is not None else sys.argv)
    win = PphViewer()
    win.show()
    args = sys.argv[1:] if argv is None else argv
    if args:
        win.open_archive(args[0])
    else:
        # 无命令行工程时初始化空项目，避免“请先打开 PPH 工程”
        win.new_empty_project()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
