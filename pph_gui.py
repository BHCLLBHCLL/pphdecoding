#!/usr/bin/env python3
"""PPH 查看/修改 GUI —— scFLOW Pre 风格界面（PyQt5 + VTK OpenGL 加速）。

参考 ``CradleCFD2025.2/Manuals/scFLOW/HTML/Pre_eng``（Navigation /
Tree / Property / Draw Window）重新设计：

- **Navigation Window**（左上方）：按操作顺序的功能导航
  （打开 → 项目信息 → 网格组 → GPH/OCT/MDL → 快照 → XML/JS → 看板）；
- **Tree Window**（左下方）：成员树（文本/快照/网格组）+ 右键菜单；
- **Draw Window**（中央 3D）：着色/线框显示模式、网格线叠加、截面裁剪、
  橡皮框缩放、Fit/Reset、坐标轴、Qt 图例；
- **Property Window**（右侧）：选中成员/树项的解析属性；
- **看板**（Dashboard）：归档、网格、八叉树、面片、快照、Parasolid
  的文件格式数据卡片 + 成员尺寸条形图。

用法：``python pph_gui.py [项目.pph]``。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QDockWidget, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSplitter,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
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


class NavigationWindow(QWidget):
    """scFLOW Pre 风格 Navigation Window：工具按钮 + 文件信息 + 分组导航。"""

    navigated = pyqtSignal(str)

    SECTIONS = [
        ("模型数据", [
            ("项目信息 (xenv/prp)", "project"),
            ("体网格 GPH", "gph"),
            ("八叉树 OCT", "oct"),
            ("面片几何 MDL", "mdl"),
        ]),
        ("视图", [
            ("快照 / Parasolid", "snapshot"),
            ("项目定义 XML", "xml"),
            ("用户脚本 JS", "js"),
            ("3D 视图", "view3d"),
        ]),
        ("数据", [
            ("格式数据看板", "dashboard"),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        title = QLabel("Navigation", self)
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1a5fb4;")
        v.addWidget(title)

        # 工具按钮行
        btns = QHBoxLayout()
        self.btn_open = QPushButton("打开", self)
        self.btn_save = QPushButton("另存为", self)
        self.btn_reload = QPushButton("重载", self)
        for b, key in ((self.btn_open, "open"), (self.btn_save, "save"),
                       (self.btn_reload, "reload")):
            b.setMinimumHeight(26)
            b.clicked.connect(lambda _c, k=key: self.navigated.emit(k))
            btns.addWidget(b)
        v.addLayout(btns)

        # 当前文件信息
        self.file_label = QLabel("未打开文件", self)
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet(
            "background: #eaf2fb; border: 1px solid #b9d3ee;"
            "border-radius: 3px; padding: 4px; color: #234;")
        v.addWidget(self.file_label)

        # 分组导航树
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.setStyleSheet(
            "QTreeWidget::item { padding: 3px; }")
        for section, items in self.SECTIONS:
            root = QTreeWidgetItem([section])
            root.setFlags(Qt.ItemIsEnabled)
            font = root.font(0)
            font.setBold(True)
            root.setFont(0, font)
            self.tree.addTopLevelItem(root)
            for label, key in items:
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.UserRole, key)
                child.setToolTip(0, label)
                root.addChild(child)
            root.setExpanded(True)
        v.addWidget(self.tree, 1)

    def _on_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.UserRole)
        if key:
            self.navigated.emit(key)

    def set_file_info(self, path: str, n_members: int, total_size: str) -> None:
        import os
        self.file_label.setText(
            f"文件: {os.path.basename(path)}\n"
            f"成员 {n_members} 个 · {total_size}")

    def set_loaded(self, loaded: bool) -> None:
        self.file_label.setText("未打开文件" if not loaded
                                else self.file_label.text())


class PropertyPanel(QWidget):
    """scFLOW Pre 风格 Property Window：选中树项的解析属性。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        title = QLabel("Property", self)
        title.setStyleSheet("font-weight: bold; color: #1a5fb4;")
        layout.addWidget(title)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["属性", "值"])
        self.tree.setColumnWidth(0, 130)
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


class ModelTree(QWidget):
    """模型树：复选框 + 右键菜单控制显隐（不使用单击/双击）。

    - 勾选 = 显示该项；取消勾选 = 隐藏该项（闭体按 csid、面区域按 frid
      从 MDL 掩码中排除）；
    - 右键菜单：仅显示此项 / 隐藏此项 / 显示全部 / 隐藏全部 / 在 3D 中查看。
    """

    visibility_changed = pyqtSignal(str, set, set, bool)
    # (group, 隐藏的body, 隐藏的region, 组可见)
    focus_3d = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["模型", "说明"])
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.setToolTip(
            "勾选=显示，取消勾选=隐藏；右键菜单可批量控制")
        v.addWidget(self.tree)

    def populate(self, groups_models: dict) -> None:
        """``groups_models``: {group: {'part': MdlModel 或 None}}。"""
        self.tree.blockSignals(True)
        self.tree.clear()
        for group in sorted(groups_models):
            root = QTreeWidgetItem([group, "网格组"])
            root.setData(0, Qt.UserRole, ("group", group, None))
            root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
            root.setCheckState(0, Qt.Checked)
            self.tree.addTopLevelItem(root)
            m = groups_models[group].get("part")
            if m is not None:
                if m.csid[1].size:
                    bodies = sorted({int(x) for x in m.csid[1] if x > 0})
                    if bodies:
                        bnode = QTreeWidgetItem(["闭体", "closed volumes"])
                        for b in bodies:
                            item = QTreeWidgetItem([f"body {b}", ""])
                            item.setData(0, Qt.UserRole, ("body", group, b))
                            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                            item.setCheckState(0, Qt.Checked)
                            bnode.addChild(item)
                        root.addChild(bnode)
                seen: dict[int, str] = {}
                for r in m.surface_regions:
                    if not r.name.startswith("@"):
                        seen.setdefault(r.index, r.name)
                if seen:
                    rnode = QTreeWidgetItem(["面区域", "surface regions"])
                    for idx, name in sorted(seen.items()):
                        item = QTreeWidgetItem([name, f"frid={idx}"])
                        item.setData(0, Qt.UserRole, ("region", group, idx))
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.Checked)
                        rnode.addChild(item)
                    root.addChild(rnode)
            root.setExpanded(True)
        self.tree.blockSignals(False)

    # ── 状态查询 ────────────────────────────────────────────────────
    def _items(self, group: str, kind: str):
        root = self._group_root(group)
        if root is None:
            return []
        out = []
        for i in range(root.childCount()):
            node = root.child(i)
            if node.text(0) in ("闭体", "面区域"):
                for j in range(node.childCount()):
                    child = node.child(j)
                    data = child.data(0, Qt.UserRole)
                    if data and data[0] == kind:
                        out.append(child)
        return out

    def _group_root(self, group: str) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            if root.data(0, Qt.UserRole) and root.data(0, Qt.UserRole)[1] == group:
                return root
        return None

    def group_visible(self, group: str) -> bool:
        root = self._group_root(group)
        return root is not None and root.checkState(0) == Qt.Checked

    def hidden_sets(self, group: str) -> tuple[set, set]:
        """返回 (隐藏的 body id 集合, 隐藏的 region frid 集合)。"""
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
        if data and data[0] in ("group", "body", "region"):
            group = data[1]
            hidden_bodies, hidden_regions = self.hidden_sets(group)
            self.visibility_changed.emit(group, hidden_bodies, hidden_regions,
                                         self.group_visible(group))

    # ── 右键菜单 ────────────────────────────────────────────────────
    def _context_menu(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu

        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        group = data[1] if data else None
        if group is None:
            return
        menu = QMenu(self)
        act_only = menu.addAction("仅显示此项")
        act_hide = menu.addAction("隐藏此项")
        menu.addSeparator()
        act_all = menu.addAction("显示全部")
        act_none = menu.addAction("隐藏全部")
        menu.addSeparator()
        act_3d = menu.addAction("在 3D 中查看")
        act = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act is act_only:
            self._set_only(item, group)
        elif act is act_hide:
            item.setCheckState(0, Qt.Unchecked)
        elif act is act_all:
            self._set_all(group, True)
        elif act is act_none:
            self._set_all(group, False)
        elif act is act_3d:
            self.focus_3d.emit()

    def _set_only(self, item: QTreeWidgetItem, group: str) -> None:
        """仅显示选中项：该项勾选，其余（同组 body/region）取消勾选。"""
        data = item.data(0, Qt.UserRole)
        if not data or data[0] == "group":
            self._set_all(group, True)
            return
        self.tree.blockSignals(True)
        kind, _, value = data
        for other in self._items(group, "body") + self._items(group, "region"):
            other.setCheckState(0, Qt.Checked
                                if other.data(0, Qt.UserRole)[2] == value
                                and other.data(0, Qt.UserRole)[0] == kind
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
            for item in self._items(group, "body") + self._items(group, "region"):
                item.setCheckState(0, state)
        self.tree.blockSignals(False)
        if root is not None:
            self._on_item_changed(root, 0)


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
    """Draw Window：VTK（OpenGL2）3D 视窗 + scFLOW 风格视图控制。"""

    show_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from vtkmodules.qt.QVTKRenderWindowInteractor import (
            QVTKRenderWindowInteractor)

        self.group_box = QComboBox(self)
        self.group_box.currentTextChanged.connect(self._on_group_changed)
        self.chk_mdl_part = QCheckBox("MDL part 面片", self)
        self.chk_mdl_part.setChecked(True)
        self.chk_mdl_ridge = QCheckBox("MDL ridge 细节", self)
        self.chk_mdl_ridge.setChecked(False)
        self.chk_oct = QCheckBox("OCT 叶子盒", self)
        self.chk_oct.setChecked(True)
        self.chk_gph = QCheckBox("GPH 边界面", self)
        self.chk_gph.setChecked(True)
        self.chk_edges = QCheckBox("网格线", self)
        self.chk_edges.setChecked(True)
        self.chk_axes = QCheckBox("坐标轴", self)
        self.chk_axes.setChecked(True)
        self.chk_legend = QCheckBox("图例", self)
        self.chk_legend.setChecked(True)
        self.color_by = QComboBox(self)
        self.color_by.addItems(["frid", "csid"])
        self.view_kind = QComboBox(self)
        self.view_kind.addItems(["全部", "仅几何 (MDL)", "仅网格 (GPH/OCT)"])
        self.view_kind.currentTextChanged.connect(self.render)
        self.display_mode = QComboBox(self)
        self.display_mode.addItems(["着色", "线框"])
        self.display_mode.currentTextChanged.connect(self.render)
        self.chk_clip = QCheckBox("剖面", self)
        self.chk_clip.toggled.connect(self.render)
        self.clip_slider = QSlider(Qt.Horizontal, self)
        self.clip_slider.setRange(0, 100)
        self.clip_slider.setValue(50)
        self.clip_slider.valueChanged.connect(self._clip_changed)
        self.clip_axis = QComboBox(self)
        self.clip_axis.addItems(["X", "Y", "Z"])
        self.clip_axis.currentIndexChanged.connect(self._clip_changed)
        self.btn_render = QPushButton("渲染", self)
        self.btn_fit = QPushButton("Fit", self)
        self.btn_reset = QPushButton("Reset", self)
        self.btn_rubber = QPushButton("橡皮框缩放", self)
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

        # ── 分组控制面板（替代单行拥挤排列）──────────────────────────
        panel = QFrame(self)
        panel.setFrameShape(QFrame.StyledPanel)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(6, 4, 6, 4)
        pv.setSpacing(3)
        # 行 1：网格组 / 显示 / 着色 / 视图按钮
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("网格组:", panel))
        row1.addWidget(self.group_box)
        row1.addSpacing(12)
        row1.addWidget(QLabel("显示:", panel))
        row1.addWidget(self.display_mode)
        row1.addWidget(QLabel("着色:", panel))
        row1.addWidget(self.color_by)
        row1.addWidget(QLabel("视图:", panel))
        row1.addWidget(self.view_kind)
        row1.addStretch(1)
        row1.addWidget(self.btn_render)
        row1.addWidget(self.btn_fit)
        row1.addWidget(self.btn_reset)
        row1.addWidget(self.btn_rubber)
        row1.addWidget(self.btn_pick)
        row1.addWidget(self.btn_show_all)
        pv.addLayout(row1)
        # 行 2：图层开关
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("图层:", panel))
        for chk in (self.chk_mdl_part, self.chk_mdl_ridge, self.chk_oct,
                    self.chk_gph, self.chk_edges, self.chk_axes,
                    self.chk_legend):
            row2.addWidget(chk)
        row2.addStretch(1)
        pv.addLayout(row2)
        # 行 3：剖面裁剪
        row3 = QHBoxLayout()
        row3.addWidget(self.chk_clip)
        row3.addWidget(QLabel("裁剪轴:", panel))
        row3.addWidget(self.clip_axis)
        row3.addWidget(QLabel("位置:", panel))
        row3.addWidget(self.clip_slider, 1)
        pv.addLayout(row3)

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
        self._clip_enabled = False
        self._mdl_filter: Optional[dict] = None
        self._pickable_actors: list = []
        self._picked_status = ""
        self._cache: dict[tuple, object] = {}
        self._hidden: dict[str, tuple[set, set]] = {}
        self._group_hidden: set[str] = set()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        if not self._started:
            self._started = True
            try:  # VTK 9.3：QVTKRenderWindowInteractor 无 start()，改用交互器初始化
                from vtkmodules.vtkInteractionStyle import (
                    vtkInteractorStyleTrackballCamera)
                self._trackball_style = vtkInteractorStyleTrackballCamera()
                iren = self.vtk_widget.GetRenderWindow().GetInteractor()
                iren.SetInteractorStyle(self._trackball_style)
                iren.Initialize()
            except Exception:  # noqa: BLE001 - 离屏/无 GL 环境不阻塞
                pass
            try:
                self.vtk_widget.GetRenderWindow().Render()
            except Exception:  # noqa: BLE001
                pass

    def set_groups(self, groups: dict[str, dict]) -> None:
        self.groups = groups
        self.group_box.blockSignals(True)
        self.group_box.clear()
        self.group_box.addItems(sorted(groups))
        self.group_box.blockSignals(False)
        if groups:
            self.group_box.setCurrentIndex(0)
            self.render()  # 显式触发首次渲染

    def _on_group_changed(self, _name: str) -> None:
        self.render()

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
                discrete = self.color_by.currentText() == "frid"
                ann = self._region_annotations(model) if discrete else None
                legend_entries = None
                if ann:
                    vals = sorted(ann)
                    colors = pph_vtk.preset_colors(len(vals))
                    legend_entries = [
                        (ann[v], colors[i]) for i, v in enumerate(vals)]
                opacity = 1.0 if kind == "mdl" else 0.85
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=opacity,
                                           discrete=discrete,
                                           annotations=ann),
                    f"MDL {key}", ann, True, legend_entries)
            if kind == "oct":
                path = group.get("oct")
                if not path:
                    return None
                import oct
                om = self._cached(("oct", path), lambda: oct.parse_oct(path))
                pd = pph_vtk.oct_leaves(om, max_leaves=cap)
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
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=0.9),
                    "GPH owner")
        except Exception as exc:  # noqa: BLE001 - 渲染尽力而为
            self.status.setText(f"{kind} 渲染失败: {exc}")
            return None
        return None

    def render(self) -> None:
        name = self.group_box.currentText()
        group = self.groups.get(name)
        self.renderer.RemoveAllViewProps()
        if self._orientation is not None:
            try:
                self._orientation.SetEnabled(0)
            except Exception:  # noqa: BLE001
                pass
            self._orientation = None
        if not group:
            self.status.setText("无网格组数据")
            self.vtk_widget.GetRenderWindow().Render()
            return
        layers: list[tuple[str, Optional[LayerRender]]] = []
        self._pickable_actors = []
        if self._layer_visible("mdl") and self.chk_mdl_part.isChecked():
            layers.append(("MDL part", self._make_actor("mdl", group, name)))
        if self._layer_visible("ridge") and self.chk_mdl_ridge.isChecked():
            layers.append(("MDL ridge", self._make_actor("ridge", group, name)))
        if self._layer_visible("oct") and self.chk_oct.isChecked():
            layers.append(("OCT", self._make_actor("oct", group)))
        if self._layer_visible("gph") and self.chk_gph.isChecked():
            layers.append(("GPH", self._make_actor("gph", group)))
        wireframe = self.display_mode.currentText() == "线框"
        legend_layers = []
        cells = []
        for label, layer in layers:
            if layer is None:
                continue
            if wireframe:
                layer.actor.GetProperty().SetRepresentationToWireframe()
            self.renderer.AddActor(layer.actor)
            if label in ("MDL part", "MDL ridge"):
                self._pickable_actors.append(layer.actor)
            mapper = layer.actor.GetMapper()
            cells.append(f"{label}={mapper.GetInput().GetNumberOfCells():,}")
            lut = mapper.GetLookupTable()
            legend_layers.append((layer.title, lut, layer.legend_entries))
            if self.chk_edges.isChecked() and layer.edges and not wireframe:
                self.renderer.AddActor(pph_vtk.edges_actor(mapper.GetInput()))
        if self.chk_legend.isChecked():
            self.legend.set_layers(legend_layers)
        else:
            self.legend.setVisible(False)
        if self.chk_axes.isChecked():
            try:
                self._orientation = pph_vtk.orientation_marker_widget(
                    self.vtk_widget.GetRenderWindow().GetInteractor())
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"坐标轴失败: {exc}")
        self.renderer.ResetCamera()
        self._clip_enabled = self.chk_clip.isChecked()
        self._apply_clip()
        self.vtk_widget.GetRenderWindow().Render()
        self.status.setText(
            f"组 {name}：{', '.join(cells) if cells else '无可用几何'}"
            + (f"（上限: {DEFAULT_CAPS}）" if not self._picked_status
               else self._picked_status))

    def precache(self, group_models: dict) -> None:
        """预置已解析的 MDL 模型，避免渲染时重复解析。"""
        for _g, info in group_models.items():
            model = info.get("part")
            path = info.get("part_path")
            if model is not None and path:
                self._cache[("mdl", path)] = model

    def _layer_visible(self, kind: str) -> bool:
        """视图类型过滤：仅几何(MDL) / 仅网格(GPH+OCT) / 全部。"""
        mode = self.view_kind.currentText()
        if mode == "仅几何 (MDL)":
            return kind in ("mdl", "ridge")
        if mode == "仅网格 (GPH/OCT)":
            return kind in ("oct", "gph")
        return True

    def _mdl_mask(self, model, group: Optional[str] = None) -> Optional[object]:
        """生成 MDL 面掩码：拾取面/单显过滤 + 模型树勾选隐藏。"""
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
        # 模型树勾选：隐藏的 body / region
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
        """模型树勾选 → 更新显隐并重渲染（模型已缓存，不重新解析）。"""
        self._hidden[group] = (set(hidden_bodies), set(hidden_regions))
        if group_visible:
            self._group_hidden.discard(group)
        else:
            self._group_hidden.add(group)
        self.render()

    def set_model_filter(self, filter_: Optional[dict]) -> None:
        """按模型树/拾取设置仅显示过滤（None = 全部）。"""
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
        """恢复全部：清空显隐过滤（同时触发 show_all_requested）。"""
        self._mdl_filter = None
        self._hidden.clear()
        self._group_hidden.clear()
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

    def _apply_clip(self) -> None:
        """截面裁剪：按 clip_axis/clip_slider 生成一个 vtkPlane。"""
        import vtk

        for i in range(self.renderer.GetViewProps().GetNumberOfItems()):
            prop = self.renderer.GetViewProps().GetItemAsObject(i)
            mapper = getattr(prop, "GetMapper", lambda: None)()
            if mapper is None or not hasattr(mapper, "SetClippingPlanes"):
                continue
            if not self._clip_enabled:
                mapper.SetClippingPlanes(vtk.vtkPlaneCollection())
                continue
            bounds = mapper.GetInput().GetBounds()
            if bounds is None or bounds[1] < bounds[0]:
                continue
            frac = self.clip_slider.value() / 100.0
            axes = {"X": 0, "Y": 1, "Z": 2}
            axis = axes[self.clip_axis.currentText()]
            planes = vtk.vtkPlaneCollection()
            plane = vtk.vtkPlane()
            origin = [(bounds[0] + bounds[1]) / 2,
                      (bounds[2] + bounds[3]) / 2,
                      (bounds[4] + bounds[5]) / 2]
            lo, hi = bounds[axis * 2], bounds[axis * 2 + 1]
            origin[axis] = lo + frac * (hi - lo)
            normal = [0.0, 0.0, 0.0]
            normal[axis] = 1.0
            plane.SetOrigin(*origin)
            plane.SetNormal(*normal)
            planes.AddItem(plane)
            mapper.SetClippingPlanes(planes)

    def _clip_changed(self, *_args) -> None:
        if self._clip_enabled:
            self._apply_clip()
            self.vtk_widget.GetRenderWindow().Render()

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
        self.vtk_widget.GetRenderWindow().Render()

    def reset_viewpoint(self) -> None:
        self.renderer.ResetCamera()
        self.renderer.GetActiveCamera().ParallelProjectionOff()
        self.vtk_widget.GetRenderWindow().Render()


class PphViewer(QMainWindow):
    """主窗口（scFLOW Pre 风格）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PPH 查看/修改器 (scFLOW Pre 风格)")
        self.resize(1440, 860)
        self.arch: Optional[pph_parser.PphArchive] = None
        self.archive_path: Optional[str] = None
        self.member_bytes: dict[str, bytes] = {}
        self.bin_paths: dict[str, str] = {}
        self.tmp_dir: Optional[str] = None
        self.snap = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        tb = self.addToolBar("文件")
        act_open = QAction("打开…", self)
        act_open.triggered.connect(self.open_dialog)
        act_save = QAction("另存为…", self)
        act_save.triggered.connect(self.save_as_dialog)
        act_reload = QAction("重新加载", self)
        act_reload.triggered.connect(self.reload)
        tb.addAction(act_open)
        tb.addAction(act_save)
        tb.addAction(act_reload)

        # 左侧：Navigation（上）+ Tree Window（下）
        self.navigation = NavigationWindow(self)
        self.navigation.navigated.connect(self._on_navigate)
        self.member_tree = QTreeWidget(self)
        self.member_tree.setHeaderLabels(["成员", "角色 / 说明", "大小"])
        self.member_tree.itemClicked.connect(self._on_member_clicked)
        self.member_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.member_tree.customContextMenuRequested.connect(
            self._member_context_menu)
        self.model_tree = ModelTree(self)
        self.model_tree.visibility_changed.connect(self._on_model_visibility)
        self.model_tree.focus_3d.connect(
            lambda: self.tabs.setCurrentWidget(self.view3d))
        left_tabs = QTabWidget(self)
        left_tabs.addTab(self.member_tree, "成员")
        left_tabs.addTab(self.model_tree, "模型")
        left = QSplitter(Qt.Vertical, self)
        left.addWidget(self.navigation)
        left.addWidget(left_tabs)
        left.setStretchFactor(0, 2)
        left.setStretchFactor(1, 3)
        dock = QDockWidget("Navigation / Tree", self)
        dock.setWidget(left)
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        # 右侧：Property Window
        self.property_panel = PropertyPanel(self)
        pdock = QDockWidget("Property", self)
        pdock.setWidget(self.property_panel)
        pdock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, pdock)

        # 中央标签页
        self.tabs = QTabWidget(self)
        self.view3d = View3DTab(self)
        self.dashboard = DashboardTab(self)
        self.dashboard.set_viewer(self)
        self.editor_tab = TextEditorTab(self)
        self.snapshot_tab = SnapshotTab(self)
        self.tabs.addTab(self.view3d, "3D")
        self.tabs.addTab(self.dashboard, "看板")
        self.tabs.addTab(self.editor_tab, "文本编辑")
        self.tabs.addTab(self.snapshot_tab, "快照")
        self.view3d.show_all_requested.connect(self._show_all_models)
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("未打开文件")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background: #f2f4f7; }"
            "QTreeWidget, QPlainTextEdit { background: white; }"
            "QDockWidget { font-weight: bold; }")

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
        self.tabs.setCurrentWidget(self.view3d)  # 3D 为默认显示区域
        self.setWindowTitle(f"PPH 查看/修改器 - {path}")
        self.statusBar().showMessage(f"已打开 {path}")
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
        self.statusBar().showMessage(
            f"已保存 {path}"
            + (f"（修改: {list(overrides)}）" if overrides else ""))
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
            self.tabs.setCurrentWidget(self.dashboard)
            self.dashboard.populate()
        elif key == "view3d":
            self.tabs.setCurrentWidget(self.view3d)
        elif key == "snapshot":
            self.tabs.setCurrentWidget(self.snapshot_tab)
        elif key in ("project", "gph", "oct", "mdl", "xml", "js", "groups"):
            name = self._member_for_nav(key)
            if name:
                self._select_member(name)

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
        """解析各网格组 _part.mdl（一次），填充模型树并预置 3D 缓存。"""
        import mdl
        groups: dict[str, dict] = {}
        self.model_models: dict[str, dict] = {}
        for name, path in self.bin_paths.items():
            if name.lower().endswith("_part.mdl"):
                g = _member_group(name)
                try:
                    model = mdl.parse_mdl(path, load_arrays=True)
                except Exception:  # noqa: BLE001 - 模型树尽力而为
                    model = None
                groups.setdefault(g, {})["part"] = model
                self.model_models[g] = {"part": model, "part_path": path}
        self.model_tree.populate(groups)
        self.view3d.precache(self.model_models)

    def _on_model_visibility(self, group: str, hidden_bodies: set,
                             hidden_regions: set, group_visible: bool) -> None:
        """模型树勾选 → 更新 3D 显隐（不跳转标签页，避免打断操作）。"""
        self.view3d.set_model_visibility(
            group, hidden_bodies, hidden_regions, group_visible)
        n_hidden = len(hidden_bodies) + len(hidden_regions)
        if n_hidden or not group_visible:
            self.statusBar().showMessage(
                f"组 {group}：{'已隐藏' if not group_visible else '可见'}，"
                f"隐藏 {n_hidden} 项")
        else:
            self.statusBar().showMessage(f"组 {group}：全部显示")

    def _show_all_models(self) -> None:
        """3D「恢复全部」→ 模型树全部勾选。"""
        for i in range(self.model_tree.tree.topLevelItemCount()):
            root = self.model_tree.tree.topLevelItem(i)
            data = root.data(0, Qt.UserRole)
            if data:
                self.model_tree._set_all(data[1], True)
        self.statusBar().showMessage("已恢复全部显示")

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
        snap_root = QTreeWidgetItem(["快照", "main.sctsnapshot", ""])
        group_roots: dict[str, QTreeWidgetItem] = {}
        for m in self.arch.members:
            item = QTreeWidgetItem([m.name, m.description, f"{m.size:,}"])
            item.setData(0, Qt.UserRole, m.name)
            item.setToolTip(0, m.name)
            if m.role in (pph_parser.ROLE_PROJECT_XML, pph_parser.ROLE_SCRIPT,
                          pph_parser.ROLE_PRP, pph_parser.ROLE_XENV):
                text_root.addChild(item)
            elif m.role == pph_parser.ROLE_SNAPSHOT:
                snap_root.addChild(item)
            else:
                g = _member_group(m.name)
                root = group_roots.setdefault(
                    g or m.name, QTreeWidgetItem([g or m.name, "网格组", ""]))
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
            self.tabs.setCurrentWidget(self.view3d)
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
            self.tabs.setCurrentWidget(self.editor_tab)
            self.editor_tab.load_member(name, data)
        elif role == pph_parser.ROLE_SNAPSHOT:
            self.tabs.setCurrentWidget(self.snapshot_tab)

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
    app = QApplication(argv if argv is not None else sys.argv)
    win = PphViewer()
    win.show()
    args = sys.argv[1:] if argv is None else argv
    if args:
        win.open_archive(args[0])
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
