#!/usr/bin/env python3
"""PPH 查看/修改 GUI（PyQt5 + VTK OpenGL 加速）。

功能：

- 打开 ``.pph``（ZIP 容器），左侧成员树按角色/网格组组织；
- 文本成员（main.js / main.prp / main.xenv / main.xml）在编辑器内
  查看并修改，``另存为`` 通过 ``pphwriter`` 写回新 .pph；
- sctsnapshot 记录树浏览（含 PKBody3 / Parasolid 摘要）；
- 3D 视窗（VTK OpenGL2 渲染）：MDL 面片（按 frid/csid 着色）、
  OCT 叶子包围盒（按深度着色）、GPH 边界面（按 owner 着色），
  大网格自动限量渲染。

用法：

.. code-block:: text

    python pph_gui.py                 # 打开文件对话框
    python pph_gui.py 项目.pph        # 直接打开

依赖：PyQt5、vtk（wheel 自带 Qt 集成）、numpy——均为本仓库运行环境
已安装版本；若缺失可 ``pip install PyQt5 vtk numpy``。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget, QDockWidget, QFrame,
)

import pph_parser
import pph_vtk
import pphwriter

try:  # VTK 工厂注册：交互样式 / OpenGL2 后端
    import vtkmodules.vtkInteractionStyle  # noqa: F401
    import vtkmodules.vtkRenderingOpenGL2   # noqa: F401
except Exception:  # noqa: BLE001 - 离屏/无显示环境下不阻塞导入
    pass


# 渲染限量（防止打开 laptop 级大网格时内存爆炸）
DEFAULT_CAPS = {"mdl": 300_000, "oct": 40_000, "gph": 120_000}
# ridge 细节面片与 part 同规模上限（"ridge" 是 _make_actor 的图层名）
DEFAULT_CAPS["ridge"] = DEFAULT_CAPS["mdl"]


@dataclass
class LayerRender:
    """一个 3D 图层的渲染结果。"""

    actor: object
    title: str
    annotations: Optional[dict] = None
    edges: bool = True   # 是否叠加网格线
    legend_entries: Optional[list[tuple[str, tuple]]] = None  # (标签, RGB)


class LegendPanel(QFrame):
    """Qt 图例面板：离散区域色块行 + 连续渐变条（替代 VTK 色标条）。

    布局固定、文字始终可读，避免 vtkScalarBarActor 尺寸/重叠/离屏
    文本渲染问题。
    """

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
        """``layers``: [(title, lut 或 None, legend_entries 或 None)]。"""
        self.clear()
        for title, lut, entries in layers:
            head = QLabel(f"<b>{title}</b>", self)
            self._layout.addWidget(head)
            if entries:
                for label, rgb in entries:
                    row = QHBoxLayout()
                    swatch = QLabel(self)
                    swatch.setFixedSize(16, 16)
                    swatch.setStyleSheet(
                        f"background-color: rgb({int(rgb[0]*255)},"
                        f"{int(rgb[1]*255)},{int(rgb[2]*255)});"
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
                row.addWidget(
                    QLabel(f"{rng[1]:g} … {rng[0]:g}", self), 1)
                self._layout.addLayout(row)
            else:
                self._layout.addWidget(QLabel("—", self))
        self._layout.addStretch(1)
        self.setVisible(True)

    @staticmethod
    def _gradient_pixmap(lut, height: int = 120) -> QPixmap:
        """从 LUT 采样生成纵向渐变（顶部 = 最大值）。"""
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


def _member_group(name: str) -> str:
    """由成员名推导网格组名（如 meshinggroup1_part.mdl → meshinggroup1）。"""
    base = name.lower()
    for suffix in ("_part.mdl", "_ridge.mdl", ".gph", ".oct", ".mdl"):
        if base.endswith(suffix):
            return name[: -len(suffix)]
    return ""


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

    def is_modified(self) -> bool:
        return bool(self.overrides())

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
        """Qt 编辑器统一用 LF；CRLF 原始文件需同基准比较。"""
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
    """VTK（OpenGL2）3D 视窗 + 图层控制。"""

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
        self.chk_legend = QCheckBox("色标/图例", self)
        self.chk_legend.setChecked(True)
        self.color_by = QComboBox(self)
        self.color_by.addItems(["frid", "csid"])
        self.btn_render = QPushButton("渲染", self)
        self.btn_reset = QPushButton("重置视角", self)
        self.btn_render.clicked.connect(self.render)
        self.btn_reset.clicked.connect(self.reset_camera)
        self.status = QLabel("未加载", self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("网格组:"))
        controls.addWidget(self.group_box)
        controls.addWidget(self.chk_mdl_part)
        controls.addWidget(self.chk_mdl_ridge)
        controls.addWidget(self.chk_oct)
        controls.addWidget(self.chk_gph)
        controls.addWidget(self.chk_edges)
        controls.addWidget(self.chk_axes)
        controls.addWidget(self.chk_legend)
        controls.addWidget(QLabel("MDL 着色:"))
        controls.addWidget(self.color_by)
        controls.addWidget(self.btn_render)
        controls.addWidget(self.btn_reset)
        controls.addStretch(1)

        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.renderer = pph_vtk.make_renderer([])
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self._started = False
        self.legend = LegendPanel(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        hbox = QHBoxLayout()
        hbox.addWidget(self.vtk_widget, 1)
        hbox.addWidget(self.legend, 0)
        layout.addLayout(hbox, 1)
        layout.addWidget(self.status)
        self.groups: dict[str, dict] = {}
        self._orientation = None

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        if not self._started:
            self._started = True
            try:  # VTK 9.3：QVTKRenderWindowInteractor 无 start()，改用交互器初始化
                from vtkmodules.vtkInteractionStyle import (
                    vtkInteractorStyleTrackballCamera)
                iren = self.vtk_widget.GetRenderWindow().GetInteractor()
                iren.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
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
            self.render()  # 显式触发首次渲染（信号可能因索引未变化而不发）

    def _on_group_changed(self, _name: str) -> None:
        self.render()

    @staticmethod
    def _region_annotations(model) -> Optional[dict]:
        """frid → 区域名（跳过 @PartSurface 副本）。"""
        ann: dict[int, str] = {}
        for r in model.surface_regions:
            if r.name.startswith("@"):
                continue
            ann.setdefault(r.index, r.name)
        return ann or None

    def _make_actor(self, kind: str, group: dict) -> Optional[LayerRender]:
        cap = DEFAULT_CAPS.get(kind, DEFAULT_CAPS["mdl"])
        try:
            if kind == "mdl":
                path = group.get("part")
                if not path:
                    return None
                import mdl
                model = mdl.parse_mdl(path)
                pd = pph_vtk.mdl_mesh(
                    model, color_by=self.color_by.currentText(),
                    max_faces=cap)
                discrete = self.color_by.currentText() == "frid"
                ann = self._region_annotations(model) if discrete else None
                legend_entries = None
                if ann:
                    vals = sorted(ann)
                    colors = pph_vtk.preset_colors(len(vals))
                    legend_entries = [
                        (ann[v], colors[i]) for i, v in enumerate(vals)]
                return LayerRender(
                    pph_vtk.polydata_actor(pd, discrete=discrete,
                                           annotations=ann),
                    "MDL part", ann, True, legend_entries)
            if kind == "ridge":
                path = group.get("ridge")
                if not path:
                    return None
                import mdl
                model = mdl.parse_mdl(path)
                pd = pph_vtk.mdl_mesh(
                    model, color_by=self.color_by.currentText(),
                    max_faces=cap)
                discrete = self.color_by.currentText() == "frid"
                ann = self._region_annotations(model) if discrete else None
                legend_entries = None
                if ann:
                    vals = sorted(ann)
                    colors = pph_vtk.preset_colors(len(vals))
                    legend_entries = [
                        (ann[v], colors[i]) for i, v in enumerate(vals)]
                return LayerRender(
                    pph_vtk.polydata_actor(pd, opacity=0.85,
                                           discrete=discrete,
                                           annotations=ann),
                    "MDL ridge", ann, True, legend_entries)
            if kind == "oct":
                path = group.get("oct")
                if not path:
                    return None
                import oct
                om = oct.parse_oct(path)
                pd = pph_vtk.oct_leaves(om, max_leaves=cap)
                return LayerRender(
                    pph_vtk.polydata_actor(pd, wireframe=True),
                    "OCT 深度", edges=False)
            if kind == "gph":
                path = group.get("gph")
                if not path:
                    return None
                import gphstats
                with gphstats.open_buffer(path) as data:
                    mesh = gphstats.parse_mesh(data)
                pd = pph_vtk.gph_boundary_mesh(mesh, max_faces=cap)
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
        if self.chk_mdl_part.isChecked():
            layers.append(("MDL part", self._make_actor("mdl", group)))
        if self.chk_mdl_ridge.isChecked():
            layers.append(("MDL ridge", self._make_actor("ridge", group)))
        if self.chk_oct.isChecked():
            layers.append(("OCT", self._make_actor("oct", group)))
        if self.chk_gph.isChecked():
            layers.append(("GPH", self._make_actor("gph", group)))
        cells = []
        legend_layers = []
        for label, layer in layers:
            if layer is None:
                continue
            self.renderer.AddActor(layer.actor)
            mapper = layer.actor.GetMapper()
            cells.append(f"{label}={mapper.GetInput().GetNumberOfCells():,}")
            lut = mapper.GetLookupTable()
            legend_layers.append((layer.title, lut, layer.legend_entries))
            if self.chk_edges.isChecked() and layer.edges:
                edges = pph_vtk.edges_actor(mapper.GetInput())
                self.renderer.AddActor(edges)
        # Qt 图例面板（右缘，替代 VTK 色标条）
        if self.chk_legend.isChecked():
            self.legend.set_layers(legend_layers)
        else:
            self.legend.setVisible(False)
        # 坐标方向指示器（右上角）
        if self.chk_axes.isChecked():
            try:
                self._orientation = pph_vtk.orientation_marker_widget(
                    self.vtk_widget.GetRenderWindow().GetInteractor())
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"坐标轴失败: {exc}")
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()
        self.status.setText(
            f"组 {name}：{', '.join(cells) if cells else '无可用几何'}"
            f"（上限: {DEFAULT_CAPS}）")

    def reset_camera(self) -> None:
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()


class PphViewer(QMainWindow):
    """主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PPH 查看/修改器")
        self.resize(1280, 800)
        self.arch: Optional[pph_parser.PphArchive] = None
        self.archive_path: Optional[str] = None
        self.member_bytes: dict[str, bytes] = {}
        self.bin_paths: dict[str, str] = {}
        self.tmp_dir: Optional[str] = None
        self.snap = None

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        # 工具栏
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

        # 左侧成员树（可停靠）
        self.member_tree = QTreeWidget(self)
        self.member_tree.setHeaderLabels(["成员", "角色 / 说明", "大小"])
        self.member_tree.itemClicked.connect(self._on_member_clicked)
        dock = QDockWidget("成员", self)
        dock.setWidget(self.member_tree)
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        # 中央标签页
        self.tabs = QTabWidget(self)
        self.editor_tab = TextEditorTab(self)
        self.snapshot_tab = SnapshotTab(self)
        self.view3d = View3DTab(self)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.tabs.addTab(self.editor_tab, "文本编辑")
        self.tabs.addTab(self.snapshot_tab, "快照")
        self.tabs.addTab(self.view3d, "3D")
        self.tabs.addTab(self.details, "详情")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("未打开文件")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QMainWindow { background: #f5f6f8; }"
            "QTreeWidget, QPlainTextEdit { background: white; }")

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
            if m.role == pph_parser.ROLE_PROJECT_XML:
                text_root.addChild(item)
            elif m.role in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                            pph_parser.ROLE_XENV):
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

    def _on_member_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        data = self.member_bytes.get(name)
        if data is None:
            return
        role, _ = pph_parser.classify_member(name)
        if role in (pph_parser.ROLE_SCRIPT, pph_parser.ROLE_PRP,
                    pph_parser.ROLE_XENV, pph_parser.ROLE_PROJECT_XML):
            self.tabs.setCurrentWidget(self.editor_tab)
            self.editor_tab.load_member(name, data)
        elif role == pph_parser.ROLE_SNAPSHOT:
            self.tabs.setCurrentWidget(self.snapshot_tab)
            self._load_snapshot_tab(name)
        else:
            self.tabs.setCurrentWidget(self.details)
            self.details.setPlainText(self._binary_details(name))

    def _load_snapshot_tab(self, name: str) -> None:
        try:
            import sctsnapshot
            self.snap = sctsnapshot.SctSnapshot.load(self.bin_paths[name])
            bodies = self.snap.bodies()
            lines = [f"记录树 {len(self.snap.records)} 条顶层记录, "
                     f"未对齐字节 {self.snap.skipped_bytes}"]
            if bodies:
                lines.append(f"Parasolid 体: {len(bodies)} 个（LZMS 压缩）")
                try:
                    for b in self.snap.decompress_bodies():
                        pk = b["pkbody3"]
                        pt = pk.decrypt()
                        import parasolid
                        ps = parasolid.parse_transmit(pt)
                        lines.append(
                            f"  PKBODY_T={b['pk_body']} size={pk.logical_size}B "
                            f"schema={ps.schema} 实体={ps.entities}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"  （体解析失败: {exc}）")
            self.snapshot_tab.load_snapshot(self.snap, "\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            self.snapshot_tab.summary.setPlainText(f"快照解析失败: {exc}")

    def _binary_details(self, name: str) -> str:
        path = self.bin_paths.get(name)
        if not path:
            return f"{name}: 无二进制数据"
        try:
            if name.lower().endswith(".gph"):
                import gphstats
                with gphstats.open_buffer(path) as data:
                    s = gphstats.summarize(data)
                links = s["links"] or {}
                return (
                    f"[{name}] GPH 体网格\n"
                    f"面 {links.get('n_faces', 0):,} / "
                    f"单元 {links.get('n_cells', 0):,} / "
                    f"顶点 {s['n_vertices']:,} ({s['dialect']})\n"
                    f"边界面 {links.get('boundary_faces', 0):,} "
                    f"npe [{links.get('npe_min', 0)}..{links.get('npe_max', 0)}]"
                    + (" 多面体" if links.get("polyhedral") else "") + "\n"
                    f"体区域 {s['volume_regions']}\n"
                    f"面区域 {s['surface_regions']}\n"
                    f"Parts {[(n, gphstats.format_part_cvol_spec(p))
                              for n, p in s['parts']]}")
            if name.lower().endswith(".oct"):
                import oct
                om = oct.parse_oct(path)
                mn, mx = om.root_min, om.root_max
                return (
                    f"[{name}] 八叉树\n"
                    f"节点 {om.n_octants:,}（内部 {om.n_internal:,} / "
                    f"叶子 {om.n_leaves:,}）单位 {om.unit!r}\n"
                    f"根包围盒 ({mn[0]:.4g},{mn[1]:.4g},{mn[2]:.4g}) .. "
                    f"({mx[0]:.4g},{mx[1]:.4g},{mx[2]:.4g})")
            if name.lower().endswith(".mdl"):
                import mdl
                m = mdl.parse_mdl(path, load_arrays=False)
                return (
                    f"[{name}] 面片几何\n"
                    f"顶点 {m.n_vertices:,} / 面 {m.n_faces:,}\n"
                    f"闭体 {m.n_closed_volumes} 个, "
                    f"体区域 {m.volume_regions}\n"
                    f"面区域 {[(r.name, r.index)
                               for r in m.surface_regions]}")
        except Exception as exc:  # noqa: BLE001
            return f"{name}: 解析失败: {exc}"
        return f"{name}: 未识别成员"

    # ── 3D ──────────────────────────────────────────────────────────
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
