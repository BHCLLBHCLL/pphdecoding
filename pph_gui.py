#!/usr/bin/env python3
"""PPH 查看/修改 GUI —— 对齐 scFLOWpre 主界面排版（PyQt5 + VTK）。

布局参照 Cradle scFLOWpre（Manuals/scFLOW/HTML/Pre_eng）：

  Menu: File / Edit / Select / View / Condition / Execute / Option / Help
  Toolbars + 主工作区：
    Navigation | Tree + Property | Draw + Message

PPH 只读/轻量编辑能力映射到对应菜单与导航项；未实现的
scFLOW 网格生成等操作在 Message 中提示。

用法：``python pph_gui.py [项目.pph]``。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygon,
)
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSlider,
    QSplitter, QStackedWidget, QTabWidget, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

import pph_parser
import pph_vtk
import pphwriter

try:  # VTK 工厂注册：交互样式 / OpenGL2 后端
    import vtkmodules.vtkInteractionStyle  # noqa: F401
    import vtkmodules.vtkRenderingOpenGL2   # noqa: F401
except Exception:  # noqa: BLE001 - 离屏/无显示环境下不阻塞导入
    pass


DEFAULT_CAPS = {"mdl": 300_000, "oct": 40_000, "gph": 120_000}
DEFAULT_CAPS["ridge"] = DEFAULT_CAPS["mdl"]


@dataclass
class LayerRender:
    """一个 3D 图层的渲染结果。"""

    actor: object
    title: str
    annotations: Optional[dict] = None
    edges: bool = True   # 是否叠加网格线
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
        p.setPen(cls._pen("#2e7d32", 1.2))
        p.setBrush(QBrush(QColor("#a5d6a7")))
        p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 3, 3)

    @classmethod
    def _draw_region(cls, p, r, _s):
        p.setPen(cls._pen("#f9a825", 1.3))
        p.setBrush(QBrush(QColor("#fff59d")))
        p.drawEllipse(r.adjusted(1, 1, -1, -1))

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
    "mdl": "part", "regions": "region",
    "oct": "octree", "oct_param": "param",
    "gph": "mesh", "mesh_param": "param",
    "snapshot": "snapshot",
    "view_part": "part", "view_octree": "octree", "view_mesh": "mesh",
    "view_section": "section", "view_show_all": "show_all",
    "xml": "xml", "js": "script", "dashboard": "dashboard", "save": "save",
}
NAV_SECTION_ICONS = {
    "Prepare Parts": "folder",
    "Build Analysis Model": "octree",
    "View": "show_all",
    "Data / Script": "script",
}


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
        self.setFixedWidth(180)
        self.setFrameShape(QFrame.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(6)
        self.setVisible(False)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_layers(self, layers) -> None:
        self.clear()
        for title, lut, entries in layers:
            self._layout.addWidget(QLabel(f"<b>{title}</b>", self))
            if entries:
                for label, rgb in entries:
                    row = QHBoxLayout()
                    swatch = QLabel(self)
                    swatch.setFixedSize(16, 16)
                    swatch.setStyleSheet(
                        f"background-color: rgb({int(rgb[0] * 255)},"
                        f"{int(rgb[1] * 255)},{int(rgb[2] * 255)});"
                        "border: 1px solid #888;")
                    row.addWidget(swatch)
                    row.addWidget(QLabel(label, self), 1)
                    self._layout.addLayout(row)
            elif lut is not None:
                row = QHBoxLayout()
                pm_label = QLabel(self)
                pm_label.setPixmap(self._gradient_pixmap(lut))
                row.addWidget(pm_label)
                rng = lut.GetRange()
                row.addWidget(QLabel(f"{rng[1]:g} … {rng[0]:g}", self), 1)
                self._layout.addLayout(row)
            else:
                self._layout.addWidget(QLabel("—", self))
        self._layout.addStretch(1)
        self.setVisible(True)

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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(24)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 6, 0)
        self.title_label = QLabel(title, bar)
        self.title_label.setObjectName("PaneTitle")
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        lay.addWidget(bar)
        lay.addWidget(content, 1)

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

    # 对齐 Pre Navigation 流程；key → PphViewer._on_navigate
    SECTIONS = [
        ("Prepare Parts", [
            ("Open Project (PPH)", "open"),
            ("Reload Project", "reload"),
            ("Project Info (xenv/prp)", "project"),
            ("Parts / Geometry (MDL)", "mdl"),
            ("Register Region", "regions"),
        ]),
        ("Build Analysis Model", [
            ("Octree (OCT)", "oct"),
            ("Octree Parameter (view)", "oct_param"),
            ("Mesh (GPH)", "gph"),
            ("Mesh Parameter (view)", "mesh_param"),
            ("Snapshot / Parasolid", "snapshot"),
        ]),
        ("View", [
            ("Draw — Part", "view_part"),
            ("Draw — Octree", "view_octree"),
            ("Draw — Mesh", "view_mesh"),
            ("Cross Section of Mesh", "view_section"),
            ("Show All", "view_show_all"),
        ]),
        ("Data / Script", [
            ("Project XML", "xml"),
            ("User Script (JS)", "js"),
            ("Format Dashboard", "dashboard"),
            ("Save As…", "save"),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
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
        for section, items in self.SECTIONS:
            root = QTreeWidgetItem([section])
            root.setFlags(Qt.ItemIsEnabled)
            font = root.font(0)
            font.setBold(True)
            root.setFont(0, font)
            root.setIcon(0, AppIcons.get(
                NAV_SECTION_ICONS.get(section, "nav_section"), 16))
            self.tree.addTopLevelItem(root)
            for label, key in items:
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.UserRole, key)
                child.setToolTip(0, label)
                child.setIcon(0, AppIcons.get(NAV_ICONS.get(key, "generic"), 16))
                root.addChild(child)
            root.setExpanded(True)
        v.addWidget(self.tree, 1)

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
    """scFLOW 风格模型树：网格组 → 几何 / 八叉树 / 体网格。

    - 勾选控制显隐（组 / 图层 / 闭体 / 面区域）；
    - 选中项刷新 Property / Status；
    - 右键：仅显示 / 显示全部 / 显示 octree·mesh 信息 / 在 3D 中查看。
    """

    visibility_changed = pyqtSignal(str, set, set, bool)
    # (group, 隐藏的 body, 隐藏的 region, 组可见)
    layer_visibility_changed = pyqtSignal(str, str, bool)
    # (group, layer in mdl|oct|gph, visible)
    item_selected = pyqtSignal(dict)
    # 选中项属性（给 Property）
    status_requested = pyqtSignal(str, str)
    # (group, focus: geometry|octree|mesh|"")
    focus_3d = pyqtSignal(str)
    # group → 切到 3D 并选中该组
    select_mesh = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["模型", "状态"])
        self.tree.setColumnWidth(0, 160)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.setToolTip(
            "勾选=显示；选中查看状态；右键可显示 octree/mesh 信息")
        v.addWidget(self.tree)
        self._info: dict[str, dict] = {}

    def populate(self, groups_info: dict) -> None:
        """``groups_info[group]`` 含 part / oct_summary / gph_summary / paths。"""
        self._info = groups_info
        self.tree.blockSignals(True)
        self.tree.clear()
        for group in sorted(groups_info):
            info = groups_info[group]
            root = QTreeWidgetItem([group, "网格组"])
            root.setData(0, Qt.UserRole, ("group", group, None))
            root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
            root.setCheckState(0, Qt.Checked)
            root.setIcon(0, AppIcons.get("group", 16))
            self.tree.addTopLevelItem(root)

            m = info.get("part")
            geo_status = self._geometry_status_text(info)
            geo = QTreeWidgetItem(["几何 (MDL)", geo_status])
            geo.setData(0, Qt.UserRole, ("layer", group, "mdl"))
            geo.setFlags(geo.flags() | Qt.ItemIsUserCheckable)
            geo.setCheckState(0, Qt.Checked if info.get("paths", {}).get("part")
                              else Qt.Unchecked)
            geo.setIcon(0, AppIcons.get("part", 16))
            if not info.get("paths", {}).get("part"):
                geo.setFlags(geo.flags() & ~Qt.ItemIsEnabled)
            root.addChild(geo)
            if m is not None:
                if m.csid[1].size:
                    bodies = sorted({int(x) for x in m.csid[1] if x > 0})
                    if bodies:
                        bnode = QTreeWidgetItem(["闭体", f"{len(bodies)}"])
                        bnode.setData(0, Qt.UserRole, ("folder", group, "body"))
                        bnode.setIcon(0, AppIcons.get("folder", 16))
                        for b in bodies:
                            item = QTreeWidgetItem([f"body {b}", "closed volume"])
                            item.setData(0, Qt.UserRole, ("body", group, b))
                            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                            item.setCheckState(0, Qt.Checked)
                            item.setIcon(0, AppIcons.get("body", 16))
                            bnode.addChild(item)
                        geo.addChild(bnode)
                seen: dict[int, str] = {}
                for r in m.surface_regions:
                    if not r.name.startswith("@"):
                        seen.setdefault(r.index, r.name)
                if seen:
                    rnode = QTreeWidgetItem(["面区域", f"{len(seen)}"])
                    rnode.setData(0, Qt.UserRole, ("folder", group, "region"))
                    rnode.setIcon(0, AppIcons.get("folder", 16))
                    for idx, name in sorted(seen.items()):
                        item = QTreeWidgetItem([name, f"frid={idx}"])
                        item.setData(0, Qt.UserRole, ("region", group, idx))
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.Checked)
                        item.setIcon(0, AppIcons.get("region", 16))
                        rnode.addChild(item)
                    geo.addChild(rnode)

            oct_status = self._oct_status_text(info)
            oct_item = QTreeWidgetItem(["八叉树 (OCT)", oct_status])
            oct_item.setData(0, Qt.UserRole, ("layer", group, "oct"))
            oct_item.setFlags(oct_item.flags() | Qt.ItemIsUserCheckable)
            has_oct = bool(info.get("paths", {}).get("oct"))
            # 默认不显示八叉树（与 3D 工具栏一致）
            oct_item.setCheckState(0, Qt.Unchecked)
            oct_item.setIcon(0, AppIcons.get("octree", 16))
            if not has_oct:
                oct_item.setFlags(oct_item.flags() & ~Qt.ItemIsEnabled)
            root.addChild(oct_item)

            mesh_status = self._mesh_status_text(info)
            mesh_item = QTreeWidgetItem(["体网格 (GPH)", mesh_status])
            mesh_item.setData(0, Qt.UserRole, ("layer", group, "gph"))
            mesh_item.setFlags(mesh_item.flags() | Qt.ItemIsUserCheckable)
            has_gph = bool(info.get("paths", {}).get("gph"))
            # 默认不显示体网格 GPH
            mesh_item.setCheckState(0, Qt.Unchecked)
            mesh_item.setIcon(0, AppIcons.get("mesh", 16))
            if not has_gph:
                mesh_item.setFlags(mesh_item.flags() & ~Qt.ItemIsEnabled)
            root.addChild(mesh_item)

            root.setExpanded(True)
            geo.setExpanded(True)
        self.tree.blockSignals(False)

    @staticmethod
    def _geometry_status_text(info: dict) -> str:
        m = info.get("part")
        if m is None:
            return "—"
        return f"{m.n_faces:,} 面 · {m.n_closed_volumes} 闭体"

    @staticmethod
    def _oct_status_text(info: dict) -> str:
        s = info.get("oct_summary") or {}
        if not s:
            return "—"
        return f"{s.get('n_leaves', 0):,} 叶 · {s.get('n_octants', 0):,} 节点"

    @staticmethod
    def _mesh_status_text(info: dict) -> str:
        s = info.get("gph_summary") or {}
        if not s:
            return "—"
        links = s.get("links") or {}
        cells = links.get("n_cells", s.get("n_cells") or 0)
        faces = links.get("n_faces", 0)
        return f"{cells:,} 单元 · {faces:,} 面"

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
            }
        return {"geometry": geo, "octree": octree, "mesh": mesh}

    def _items(self, group: str, kind: str):
        root = self._group_root(group)
        if root is None:
            return []
        out = []
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            node = stack.pop()
            data = node.data(0, Qt.UserRole)
            if data and data[0] == kind:
                out.append(node)
            for j in range(node.childCount()):
                stack.append(node.child(j))
        return out

    def _group_root(self, group: str) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            data = root.data(0, Qt.UserRole)
            if data and data[1] == group:
                return root
        return None

    def group_visible(self, group: str) -> bool:
        root = self._group_root(group)
        return root is not None and root.checkState(0) == Qt.Checked

    def layer_visible(self, group: str, layer: str) -> bool:
        for item in self._items(group, "layer"):
            if item.data(0, Qt.UserRole)[2] == layer:
                return item.checkState(0) == Qt.Checked
        return True

    def hidden_sets(self, group: str) -> tuple[set, set]:
        hidden_bodies: set = set()
        hidden_regions: set = set()
        for item in self._items(group, "body"):
            if item.checkState(0) != Qt.Checked:
                hidden_bodies.add(item.data(0, Qt.UserRole)[2])
        for item in self._items(group, "region"):
            if item.checkState(0) != Qt.Checked:
                hidden_regions.add(item.data(0, Qt.UserRole)[2])
        return hidden_bodies, hidden_regions

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, group, value = data[0], data[1], data[2]
        if kind == "layer":
            self.layer_visibility_changed.emit(
                group, value, item.checkState(0) == Qt.Checked)
            return
        if kind in ("group", "body", "region"):
            hidden_bodies, hidden_regions = self.hidden_sets(group)
            self.visibility_changed.emit(
                group, hidden_bodies, hidden_regions,
                self.group_visible(group))

    def _on_selection(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.UserRole)
        if not data:
            return
        kind, group, value = data[0], data[1], data[2]
        props = {"网格组": group, "节点": kind}
        if kind == "body":
            props["闭体 csid"] = value
        elif kind == "region":
            props["面区域 frid"] = value
            props["名称"] = items[0].text(0)
        elif kind == "layer":
            props["图层"] = {"mdl": "几何 MDL", "oct": "八叉树 OCT",
                             "gph": "体网格 GPH"}.get(value, value)
            props["状态列"] = items[0].text(1)
        st = self.group_status_props(group)
        focus = {"mdl": "geometry", "oct": "octree",
                 "gph": "mesh"}.get(value if kind == "layer" else "", "")
        self.item_selected.emit(props)
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
        if data[0] == "group":
            self._set_all(group, True)
            return
        if data[0] == "layer":
            self.tree.blockSignals(True)
            for other in self._items(group, "layer"):
                other.setCheckState(
                    0, Qt.Checked if other is item else Qt.Unchecked)
            root = self._group_root(group)
            if root is not None:
                root.setCheckState(0, Qt.Checked)
            self.tree.blockSignals(False)
            self.layer_visibility_changed.emit(
                group, data[2], True)
            for other in self._items(group, "layer"):
                if other is not item:
                    self.layer_visibility_changed.emit(
                        group, other.data(0, Qt.UserRole)[2], False)
            return
        if data[0] not in ("body", "region"):
            return
        self.tree.blockSignals(True)
        kind, _, value = data
        for other in self._items(group, "body") + self._items(group, "region"):
            od = other.data(0, Qt.UserRole)
            other.setCheckState(
                0, Qt.Checked if od[0] == kind and od[2] == value
                else Qt.Unchecked)
        root = self._group_root(group)
        if root is not None:
            root.setCheckState(0, Qt.Checked)
        self.tree.blockSignals(False)
        self._on_item_changed(item, 0)

    def _set_all(self, group: str, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        self.tree.blockSignals(True)
        root = self._group_root(group)
        if root is not None:
            root.setCheckState(0, state)
            for item in (self._items(group, "body")
                         + self._items(group, "region")
                         + self._items(group, "layer")):
                if item.flags() & Qt.ItemIsEnabled:
                    item.setCheckState(0, state)
        self.tree.blockSignals(False)
        if root is not None:
            self._on_item_changed(root, 0)
            for item in self._items(group, "layer"):
                if item.flags() & Qt.ItemIsEnabled:
                    self.layer_visibility_changed.emit(
                        group, item.data(0, Qt.UserRole)[2],
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
                out[name] = text.encode("utf-8")
        return out

    def set_originals(self, originals: dict[str, bytes]) -> None:
        self._originals = {n: self._norm(b) for n, b in originals.items()}

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
        self.chk_mdl_ridge = QCheckBox("ridge", self)
        self.chk_mdl_ridge.setChecked(False)
        self.chk_oct = QCheckBox("八叉树", self)
        self.chk_oct.setChecked(False)
        self.chk_gph = QCheckBox("体网格", self)
        self.chk_gph.setChecked(False)
        self.chk_edges = QCheckBox("网格线", self)
        self.chk_edges.setChecked(True)
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
        self.display_mode.addItems(["半透明", "不透明", "线框"])
        self.display_mode.setCurrentText("半透明")
        self.display_mode.setToolTip(
            "体网格/几何显示：半透明 · 不透明 · 线框")
        self.display_mode.currentTextChanged.connect(self.render)

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
        self.btn_rubber.toggled.connect(self._toggle_rubber_zoom)
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
        for chk in (self.chk_mdl_part, self.chk_mdl_ridge, self.chk_oct,
                    self.chk_gph, self.chk_edges, self.chk_axes,
                    self.chk_legend):
            row2.addWidget(chk)
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

        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.renderer = pph_vtk.make_renderer([])
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self._started = False
        self.legend = LegendPanel(self)
        self._orientation = None
        self._rubber_style = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)
        hbox = QHBoxLayout()
        hbox.addWidget(self.vtk_widget, 1)
        hbox.addWidget(self.legend, 0)
        layout.addLayout(hbox, 1)
        layout.addWidget(self.status)

        self.groups: dict[str, dict] = {}
        self._mdl_filter: Optional[dict] = None
        self._pickable_actors: list = []
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

    def _safe_vtk_render(self) -> None:
        if not self._started or not self._vtk_ok:
            return
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:  # noqa: BLE001
            self._vtk_ok = False

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
            except Exception:  # noqa: BLE001
                pass
            self._safe_vtk_render()
            if self.groups:
                self.render()

    def set_groups(self, groups: dict[str, dict]) -> None:
        self.groups = groups
        self._mesh_section_pd = None
        self._mesh_section_dirty = True
        self.group_box.blockSignals(True)
        self.group_box.clear()
        self.group_box.addItems(sorted(groups))
        self.group_box.blockSignals(False)
        if groups:
            self.group_box.setCurrentIndex(0)
            # 窗口未 show 前不触发 VTK Render（无 GL/offscreen 会崩）
            if self._started:
                self.render()

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
            mesh = self._cached(("gph_mesh", path), lambda: _gph_mesh(path))
            face_scalars = None
            if self.chk_color_cvol.isChecked():
                with gphstats.open_buffer(path) as data:
                    cvol = gphstats.cvol_ids(data)
                if cvol is not None and cvol.size:
                    owner = mesh["owner"]
                    face_scalars = np.zeros(mesh["n_faces"], dtype=np.float64)
                    valid = (owner >= 0) & (owner < cvol.size)
                    face_scalars[valid] = cvol[owner[valid]]
            pd = self._cached(
                ("gph_all", path, bool(self.chk_color_cvol.isChecked())),
                lambda: pph_vtk.gph_faces_mesh(
                    mesh, max_faces=DEFAULT_CAPS["gph"] * 3,
                    boundary_only=False, face_scalars=face_scalars))
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

    def _make_actor(self, kind: str, group: dict,
                    group_name: Optional[str] = None) -> Optional[LayerRender]:
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
                opacity = self._surface_opacity(kind)
                wire = self.display_mode.currentText() == "线框"
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=opacity,
                                           wireframe=wire,
                                           discrete=discrete,
                                           annotations=ann),
                    f"MDL {key}", ann, edges=not wire, legend_entries=legend_entries)
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
                return LayerRender(
                    pph_vtk.polydata_actor(pd, wireframe=True),
                    "OCT 深度", edges=False)
            if kind == "gph":
                path = group.get("gph")
                if not path:
                    return None
                pd = self._cached(
                    ("gph_pd", path),
                    lambda: pph_vtk.gph_boundary_mesh(
                        _gph_mesh(path), max_faces=cap))
                opacity = self._surface_opacity("gph")
                wire = self.display_mode.currentText() == "线框"
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=opacity, wireframe=wire),
                    "GPH owner", edges=not wire)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"{kind} 渲染失败: {exc}")
            return None
        return None

    def render(self) -> None:
        name = self.group_box.currentText()
        group = self.groups.get(name)
        if not self._started:
            # 仅更新状态文案，避免无 GL 时组装 actor/Render 崩溃
            if not group:
                self.status.setText("无网格组数据")
            else:
                self.status.setText(f"组 {name}：待显示窗口后渲染")
            return
        self.renderer.RemoveAllViewProps()
        if self._orientation is not None:
            try:
                self._orientation.SetEnabled(0)
            except Exception:  # noqa: BLE001
                pass
            self._orientation = None
        if not group:
            self.status.setText("无网格组数据")
            self._safe_vtk_render()
            return

        mesh_section = (self.chk_section.isChecked()
                        and self.section_target.currentText() == "体网格")
        lines_only = mesh_section and self.chk_lines_only.isChecked()

        layers: list[tuple[str, Optional[LayerRender]]] = []
        self._pickable_actors = []
        if (self._layer_visible("mdl", name)
                and self.chk_mdl_part.isChecked() and not lines_only):
            layers.append(("MDL part", self._make_actor("mdl", group, name)))
        if (self._layer_visible("ridge", name)
                and self.chk_mdl_ridge.isChecked() and not lines_only):
            layers.append(("MDL ridge", self._make_actor("ridge", group, name)))
        if (self._layer_visible("oct", name)
                and self.chk_oct.isChecked() and not lines_only):
            layers.append(("OCT", self._make_actor("oct", group)))
        if (self._layer_visible("gph", name) and self.chk_gph.isChecked()
                and not lines_only):
            layers.append(("GPH", self._make_actor("gph", group)))

        mode = self.display_mode.currentText()
        wireframe = mode == "线框"
        legend_layers = []
        cells = []
        for label, layer in layers:
            if layer is None:
                continue
            prop = layer.actor.GetProperty()
            if wireframe:
                prop.SetRepresentationToWireframe()
                prop.SetOpacity(1.0)
            else:
                prop.SetRepresentationToSurface()
                # 体网格按显示模式设透明度；几何在「半透明」时略透以便叠看
                if label == "GPH":
                    prop.SetOpacity(0.45 if mode == "半透明" else 1.0)
                elif label.startswith("MDL"):
                    prop.SetOpacity(0.7 if mode == "半透明" else 1.0)
            self.renderer.AddActor(layer.actor)
            if label in ("MDL part", "MDL ridge"):
                self._pickable_actors.append(layer.actor)
            mapper = layer.actor.GetMapper()
            cells.append(f"{label}={mapper.GetInput().GetNumberOfCells():,}")
            lut = mapper.GetLookupTable()
            legend_layers.append((layer.title, lut, layer.legend_entries))
            if self.chk_edges.isChecked() and layer.edges and not wireframe:
                self.renderer.AddActor(pph_vtk.edges_actor(mapper.GetInput()))

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

        if self.chk_legend.isChecked():
            self.legend.set_layers(legend_layers)
        else:
            self.legend.setVisible(False)
        if self.chk_axes.isChecked() and self._vtk_ok:
            try:
                self._orientation = pph_vtk.orientation_marker_widget(
                    self.vtk_widget.GetRenderWindow().GetInteractor())
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"坐标轴失败: {exc}")

        self.renderer.ResetCamera()
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
                             visible: bool) -> None:
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
            if kind == "body":
                b1, b2 = model.csid
                if b2.size:
                    return (b1 == value) | (b2 == value)
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

    def set_model_visibility(self, group: str, hidden_bodies,
                             hidden_regions, group_visible: bool = True) -> None:
        self._hidden[group] = (set(hidden_bodies), set(hidden_regions))
        if group_visible:
            self._group_hidden.discard(group)
        else:
            self._group_hidden.add(group)
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
            elif kind == "body":
                self._picked_status = f" | 仅显示 body {value}"
            elif kind == "region":
                self._picked_status = f" | 仅显示区域 frid={value}"
        self.render()

    def clear_visibility(self) -> None:
        self._mdl_filter = None
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
            self.status.setText("拾取模式：点击 MDL 面上的一个单元")
        else:
            iren.RemoveObservers("LeftButtonPressEvent")

    def _on_pick(self, obj, _event) -> None:
        import vtk

        picker = vtk.vtkCellPicker()
        x, y = obj.GetEventPosition()
        if picker.Pick(x, y, 0, self.renderer) == 0:
            self.status.setText("拾取失败：未命中单元")
            return
        actor = picker.GetActor()
        if actor is None or actor not in self._pickable_actors:
            self.status.setText("请在 MDL 面片（part/ridge）上拾取面")
            return
        cell = picker.GetCellId()
        self.set_model_filter({"kind": "face", "value": int(cell)})

    def _toggle_rubber_zoom(self, checked: bool) -> None:
        from vtkmodules.vtkInteractionStyle import (
            vtkInteractorStyleRubberBandZoom, vtkInteractorStyleTrackballCamera)

        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        if checked:
            style = vtkInteractorStyleRubberBandZoom()
            style.SetRenderOnMouseMove(1)
            self._rubber_style = style
        else:
            self._rubber_style = vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(self._rubber_style)

    def fit(self) -> None:
        self.renderer.ResetCamera()
        self._safe_vtk_render()

    def reset_viewpoint(self) -> None:
        self.renderer.ResetCamera()
        self.renderer.GetActiveCamera().ParallelProjectionOff()
        self._safe_vtk_render()


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
        self._build_ui()
        self._apply_style()
        self.log("Ready. Open a .pph project to begin.")

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

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def add_act(menu, text, slot=None, shortcut=None, tip=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            if tip:
                act.setToolTip(tip)
            if slot:
                act.triggered.connect(slot)
            else:
                act.triggered.connect(
                    lambda checked=False, t=text: self._nyi(t))
            menu.addAction(act)
            return act

        # File
        m = mb.addMenu("File(&F)")
        add_act(m, "Open…", self.open_dialog, "Ctrl+O")
        add_act(m, "Reload", self.reload, "F5")
        add_act(m, "Save As…", self.save_as_dialog, "Ctrl+Shift+S")
        m.addSeparator()
        add_act(m, "Open Project Folder", self._open_project_folder)
        add_act(m, "Export Member…", self._export_member)
        m.addSeparator()
        add_act(m, "Exit", self.close, "Alt+F4")

        # Edit
        m = mb.addMenu("Edit(&E)")
        add_act(m, "Create Parts")
        add_act(m, "Modify Parts")
        add_act(m, "Register Region",
                lambda: self._on_navigate("regions"))
        add_act(m, "Edit Project XML / JS",
                lambda: self._on_navigate("xml"))

        # Select
        m = mb.addMenu("Select(&S)")
        add_act(m, "Pick Face", self._toggle_pick_face)
        add_act(m, "Clear Selection",
                lambda: self.view3d.set_model_filter(None))

        # View
        m = mb.addMenu("View(&V)")
        add_act(m, "Part", lambda: self._on_navigate("view_part"))
        add_act(m, "Octree", lambda: self._on_navigate("view_octree"))
        add_act(m, "Mesh", lambda: self._on_navigate("view_mesh"))
        m.addSeparator()
        add_act(m, "Fit to Draw Window",
                lambda: self.view3d.fit(), "Ctrl+F")
        add_act(m, "Reset Viewpoint",
                lambda: self.view3d.reset_viewpoint())
        add_act(m, "Show All", lambda: self._on_navigate("view_show_all"))
        m.addSeparator()
        add_act(m, "Cross Section View of Mesh",
                lambda: self._on_navigate("view_section"))
        add_act(m, "Rubber Box Zoom", self._toggle_rubber)
        m.addSeparator()
        add_act(m, "Dashboard", lambda: self._on_navigate("dashboard"))
        add_act(m, "Snapshot", lambda: self._on_navigate("snapshot"))

        # Condition
        m = mb.addMenu("Condition(&C)")
        add_act(m, "Parts Control",
                lambda: self._on_navigate("mdl"))
        add_act(m, "Octree Parameter",
                lambda: self._on_navigate("oct_param"))
        add_act(m, "Mesh Parameter",
                lambda: self._on_navigate("mesh_param"))
        add_act(m, "Part Material / Conditions")

        # Execute
        m = mb.addMenu("Execute(&X)")
        add_act(m, "Build Analysis Model")
        add_act(m, "Generate Octree for Meshing")
        add_act(m, "Generate Mesh")
        add_act(m, "Execute Solver")

        # Option
        m = mb.addMenu("Option(&O)")
        add_act(m, "Environment Settings")
        add_act(m, "Show Geometry Status",
                lambda: self._focus_status("geometry"))
        add_act(m, "Show Octree Status",
                lambda: self._focus_status("octree"))
        add_act(m, "Show Mesh Status",
                lambda: self._focus_status("mesh"))

        # Help
        m = mb.addMenu("Help(&H)")
        add_act(m, "About PPH Viewer", self._about)
        add_act(m, "Open scFLOWpre Manual", self._open_manual)

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
            ("Fit", "fit", "Fit to Draw Window", None),
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
        self.tb_display.addItems(["半透明", "不透明", "线框"])
        self.tb_display.setCurrentText("半透明")
        self.tb_display.setToolTip("半透明 / 不透明 / 线框")
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

    def _about(self) -> None:
        QMessageBox.about(
            self, "About",
            "PPH Viewer\n"
            "Layout & menus aligned with Cradle scFLOWpre.\n"
            "Inspect / lightly edit scFLOW .pph archives.")

    def _open_manual(self) -> None:
        path = (r"C:\Program Files\Cradle\CradleCFD2025.2"
                r"\Manuals\scFLOW\HTML\Pre_eng\index.html")
        if os.path.isfile(path):
            os.startfile(path)  # noqa: S606 - Windows open
            self.log(f"Opened manual: {path}")
        else:
            self.log(f"Manual not found: {path}", "ERROR")

    def _open_project_folder(self) -> None:
        if not self.archive_path:
            self.log("No project open.", "WARN")
            return
        folder = os.path.dirname(os.path.abspath(self.archive_path))
        os.startfile(folder)  # noqa: S606
        self.log(f"Opened folder: {folder}")

    def _export_member(self) -> None:
        item = self.member_tree.currentItem()
        name = item.data(0, Qt.UserRole) if item else None
        if not name or name not in self.member_bytes:
            self.log("Select an archive member first.", "WARN")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {name}", name, "All files (*)")
        if not path:
            return
        with open(path, "wb") as f:
            f.write(self.member_bytes[name])
        self.log(f"Exported {name} → {path}")

    def _toggle_pick_face(self) -> None:
        self.show_page("draw")
        checked = not self.view3d.btn_pick.isChecked()
        self.view3d.btn_pick.setChecked(checked)

    def _toggle_rubber(self) -> None:
        self.show_page("draw")
        checked = not self.view3d.btn_rubber.isChecked()
        self.view3d.btn_rubber.setChecked(checked)

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
            #PaneFrame {
                background: #ffffff;
                border: 1px solid #9a9a9a;
            }
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

    def open_archive(self, path: str) -> bool:
        try:
            self._cleanup()
            self.arch = pph_parser.PphArchive.open(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", str(exc))
            return False
        self.archive_path = path
        self.member_bytes = {
            m.name: self.arch.read_member(m.name) for m in self.arch.members}
        self.editor_tab.set_originals(self.member_bytes)
        self.tmp_dir = tempfile.mkdtemp(prefix="pph_gui_")
        self.bin_paths = {}
        for m in self.arch.members:
            if m.role in (pph_parser.ROLE_SNAPSHOT, pph_parser.ROLE_GPH,
                          pph_parser.ROLE_OCT, pph_parser.ROLE_MDL_PART,
                          pph_parser.ROLE_MDL_RIDGE):
                p = os.path.join(self.tmp_dir, m.name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(self.member_bytes[m.name])
                self.bin_paths[m.name] = p
        self._populate_tree()
        self._populate_3d()
        self._load_snapshot_member()
        self.dashboard.populate()
        self._build_model_tree()
        self.property_panel.set_properties(self._archive_properties())
        self.navigation.set_file_info(
            path, len(self.arch.members),
            _fmt_size(sum(m.size for m in self.arch.members)))
        self.show_page("draw")
        self.setWindowTitle(f"PPH Viewer — {os.path.basename(path)}")
        self.log(f"Opened {path} ({len(self.arch.members)} members)")
        return True

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
            self.view3d.render()
            self.log("View — Mesh")
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
        elif key == "regions":
            self.show_page("draw")
            self._focus_status("geometry")
            self.log("Register Region — surface/volume regions in Status")
        elif key in ("oct_param",):
            self.show_page("draw")
            self._focus_status("octree")
            name = self._member_for_nav("oct")
            if name:
                self._select_member(name)
            self.log("Octree Parameter (status / member props)")
        elif key in ("mesh_param",):
            self.show_page("draw")
            self._focus_status("mesh")
            name = self._member_for_nav("gph")
            if name:
                self._select_member(name)
            self.log("Mesh Parameter (status / member props)")
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
                    max_depth = 0
                    try:
                        for _mn, _mx, d in om.iter_leaves():
                            if d > max_depth:
                                max_depth = d
                    except Exception:  # noqa: BLE001
                        max_depth = -1
                    info["oct_summary"] = {
                        "n_octants": om.n_octants,
                        "n_internal": om.n_internal,
                        "n_leaves": om.n_leaves,
                        "unit": om.unit,
                        "max_depth": max_depth if max_depth >= 0 else "—",
                    }
                except Exception:  # noqa: BLE001
                    info["oct_summary"] = None
            gph_path = info["paths"].get("gph")
            if gph_path:
                try:
                    import gphstats
                    with gphstats.open_buffer(gph_path) as data:
                        info["gph_summary"] = gphstats.summarize(data)
                except Exception:  # noqa: BLE001
                    info["gph_summary"] = None
        self.model_tree.populate(groups)
        for g in groups:
            self.status_panel.set_group_status(
                g, self.model_tree.group_status_props(g))
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
        for i in range(self.model_tree.tree.topLevelItemCount()):
            root = self.model_tree.tree.topLevelItem(i)
            data = root.data(0, Qt.UserRole)
            if data:
                self.model_tree._set_all(data[1], True)
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
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
