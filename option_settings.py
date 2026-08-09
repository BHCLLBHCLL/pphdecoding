#!/usr/bin/env python3
"""scFLOWpre [Option] – [Settings…] → Environment Settings（右侧细节对齐手册）。"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

import pphxml

_DETAILED = [
    ("Folder", "folder"),
    ("File", "file_d"),
    ("Navigation", "navigation"),
    ("Drawing (General)", "draw_gen"),
    ("Drawing (Part)", "draw_part"),
    ("Drawing (Octree)", "draw_oct"),
    ("Drawing (Mesh)", "draw_mesh"),
    ("Selection", "selection"),
    ("CAD Data", "cad_d"),
    ("Mesh", "mesh_d"),
    ("Initialize", "initialize"),
]

_PROJECT = [
    ("Project Type", "project_type"),
    ("Unit", "unit"),
    ("CAD Data Import", "cad_import"),
    ("Precision of Closed Volume", "closed_vol"),
    ("Tiny Faces", "tiny_faces"),
    ("Ridges", "ridges"),
    ("Mesher/Faceter", "mesher_faceter"),
    ("Voxel Fitting Mesher", "voxel"),
    ("Mesh", "mesh_p"),
    ("Mesh Parameter", "mesh_param"),
    ("File", "file_p"),
    ("MSC CoSim", "msc"),
]


# ── helpers ─────────────────────────────────────────────────────────


class _ColorBtn(QPushButton):
    """色块按钮（scFLOWpre Parameter/Value 颜色格）。"""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(56, 22)
        self.clicked.connect(self._pick)
        self._paint()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, c: QColor) -> None:
        self._color = QColor(c)
        self._paint()

    def _paint(self) -> None:
        self.setStyleSheet(
            f"background:{self._color.name()}; border:1px solid #666;")

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "Select Color")
        if c.isValid():
            self.set_color(c)

    def to_hex(self) -> str:
        return self._color.name()


def _scroll(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa


def _make_refer(label: str, edit: QLineEdit, *, file_mode: bool = False,
                filter_: str = "") -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(edit, 1)
    btn = QPushButton("Refer...")
    btn.setFixedWidth(72)

    def _browse() -> None:
        if file_mode:
            path, _ = QFileDialog.getOpenFileName(
                edit, label, edit.text(), filter_ or "All (*)")
        else:
            path = QFileDialog.getExistingDirectory(
                edit, label, edit.text())
        if path:
            edit.setText(path)

    btn.clicked.connect(_browse)
    h.addWidget(btn)
    return w


def _default_bar(on_set: Callable, on_reset: Callable) -> QHBoxLayout:
    bar = QHBoxLayout()
    bar.addStretch(1)
    b1 = QPushButton("Set as Default")
    b2 = QPushButton("Reset to Default")
    b1.clicked.connect(on_set)
    b2.clicked.connect(on_reset)
    bar.addWidget(b1)
    bar.addWidget(b2)
    return bar


def _meshing_unit_row() -> tuple[QHBoxLayout, QComboBox]:
    row = QHBoxLayout()
    row.addWidget(QLabel("Meshing unit"))
    cb = QComboBox()
    cb.addItem("(default)")
    cb.setEnabled(False)
    cb.setMinimumWidth(160)
    row.addWidget(cb)
    row.addStretch(1)
    return row, cb


class _SciSpin(QDoubleSpinBox):
    """显示 1e-06 风格（对齐 scFLOWpre）。"""

    def __init__(self, value: float = 0.0, decimals: int = 12,
                 parent=None):
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setRange(0.0, 1e12)
        self.setValue(value)

    def textFromValue(self, v: float) -> str:  # noqa: N802
        if v == 0.0:
            return "0"
        if abs(v) < 1e-3 or abs(v) >= 1e4:
            return f"{v:.0e}".replace("e-0", "e-").replace("e+0", "e+")
        return f"{v:g}"

    def valueFromText(self, text: str) -> float:  # noqa: N802
        try:
            return float(text.strip())
        except ValueError:
            return self.value()


def _closed_group(title: str, desc: str, editor: QWidget,
                  unit: str = "") -> QGroupBox:
    g = QGroupBox(title)
    v = QVBoxLayout(g)
    lab = QLabel(desc)
    lab.setWordWrap(True)
    v.addWidget(lab)
    row = QHBoxLayout()
    row.addWidget(editor)
    if unit:
        row.addWidget(QLabel(unit))
    row.addStretch(1)
    v.addLayout(row)
    return g


class EnvironmentSettingsDialog(QDialog):
    """[Option] – [Settings…] → Environment Settings。"""

    def __init__(self, ctx: dict, parent=None,
                 on_open_mesher: Optional[Callable] = None):
        super().__init__(parent)
        self._ctx = ctx
        self._on_open_mesher = on_open_mesher
        self._mf_body = None
        self.setWindowTitle("Environment Settings")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(820, 600)

        root = QVBoxLayout(self)
        split = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(230)
        self.tree.setMaximumWidth(280)
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        self._build_tree()
        self._build_pages()
        split.addWidget(self.tree)
        split.addWidget(self.stack, 1)
        root.addLayout(split, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.tree.currentItemChanged.connect(self._on_nav)
        self._select_key("navigation")
        self.load(ctx)

    def _build_tree(self) -> None:
        det = QTreeWidgetItem(["Detailed Configuration"])
        det.setFlags(det.flags() & ~Qt.ItemIsSelectable)
        self.tree.addTopLevelItem(det)
        for title, key in _DETAILED:
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.UserRole, key)
            det.addChild(it)
        det.setExpanded(True)

        proj = QTreeWidgetItem(["Project Configuration"])
        proj.setFlags(proj.flags() & ~Qt.ItemIsSelectable)
        self.tree.addTopLevelItem(proj)
        for title, key in _PROJECT:
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.UserRole, key)
            proj.addChild(it)
        proj.setExpanded(True)

    def _add_page(self, key: str, w: QWidget) -> None:
        self._pages[key] = w
        self.stack.addWidget(w)

    def _build_pages(self) -> None:
        self._add_page("folder", _scroll(self._page_folder()))
        self._add_page("file_d", _scroll(self._page_file_d()))
        self._add_page("navigation", _scroll(self._page_navigation()))
        self._add_page("draw_gen", _scroll(self._page_draw_gen()))
        self._add_page("draw_part", _scroll(self._page_draw_part()))
        self._add_page("draw_oct", _scroll(self._page_draw_oct()))
        self._add_page("draw_mesh", _scroll(self._page_draw_mesh()))
        self._add_page("selection", _scroll(self._page_selection()))
        self._add_page("cad_d", _scroll(self._page_cad_d()))
        self._add_page("mesh_d", _scroll(self._page_mesh_d()))
        self._add_page("initialize", _scroll(self._page_initialize()))

        self._add_page("project_type", _scroll(self._page_project_type()))
        self._add_page("unit", _scroll(self._page_unit()))
        self._add_page("cad_import", _scroll(self._page_cad_import()))
        self._add_page("closed_vol", _scroll(self._page_closed_vol()))
        self._add_page("tiny_faces", _scroll(self._page_tiny_faces()))
        self._add_page("ridges", _scroll(self._page_ridges()))
        self._add_page("mesher_faceter", self._page_mesher_faceter())
        self._add_page("voxel", _scroll(self._page_voxel()))
        self._add_page("mesh_p", _scroll(self._page_mesh_p()))
        self._add_page("mesh_param", _scroll(self._page_mesh_param()))
        self._add_page("file_p", _scroll(self._page_file_p()))
        self._add_page("msc", _scroll(self._page_msc()))

    # ── Detailed pages ────────────────────────────────────────────

    def _page_folder(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ed_home = QLineEdit()
        self.ed_work = QLineEdit()
        f.addRow("Home folder",
                 _make_refer("Home folder", self.ed_home))
        f.addRow("Default work folder",
                 _make_refer("Default work folder", self.ed_work))
        self.chk_temp_in_work = QCheckBox(
            "Always create a temporary folder in the default work folder")
        f.addRow("", self.chk_temp_in_work)
        return w

    def _page_file_d(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        f = QFormLayout()
        self.ed_prp = QLineEdit()
        f.addRow("PRP file", _make_refer(
            "PRP file", self.ed_prp, file_mode=True,
            filter_="PRP (*.prp);;All (*)"))
        v.addLayout(f)
        g = QGroupBox("Compression level of the project file")
        gv = QVBoxLayout(g)
        self.rad_comp0 = QRadioButton("Level0 (No compression)")
        self.rad_comp1 = QRadioButton("Level1 (Fast)")
        self.rad_comp2 = QRadioButton("Level2 (Small)")
        self.rad_comp0.setChecked(True)
        self._comp_group = QButtonGroup(w)
        for r in (self.rad_comp0, self.rad_comp1, self.rad_comp2):
            self._comp_group.addButton(r)
            gv.addWidget(r)
        v.addWidget(g)
        self.chk_backup_mesh = QCheckBox(
            "Backup the project before meshing")
        v.addWidget(self.chk_backup_mesh)
        v.addStretch(1)
        return w

    def _page_navigation(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_show_bam = QCheckBox("Show [Build Analysis Model] item")
        self.chk_pre_bam = QCheckBox(
            "Enable condition settings and registration of regions "
            "before building analysis model.")
        self.chk_always_wiz = QCheckBox(
            "Always show the analysis model wizard")
        self.chk_show_mesher = QCheckBox(
            "Show [Mesher/Faceter Setting] item")
        self.chk_show_proj = QCheckBox(
            "Always show [Project Type Setting] item")
        self.chk_enable_wrap = QCheckBox("Enable wrapping")
        self.chk_show_bam.setChecked(True)
        self.chk_show_mesher.setChecked(True)
        for c in (self.chk_show_bam, self.chk_pre_bam, self.chk_always_wiz,
                  self.chk_show_mesher, self.chk_show_proj,
                  self.chk_enable_wrap):
            v.addWidget(c)
        v.addStretch(1)
        return w

    def _page_draw_gen(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        bg = QHBoxLayout()
        self.col_bg_top = _ColorBtn(QColor(100, 149, 237))
        self.col_bg_bot = _ColorBtn(QColor(255, 255, 255))
        bg.addWidget(QLabel("Top"))
        bg.addWidget(self.col_bg_top)
        bg.addWidget(QLabel("Bottom"))
        bg.addWidget(self.col_bg_bot)
        bg.addStretch(1)
        f.addRow("Background color", bg)

        self.cb_wire_drag = QComboBox()
        self.cb_wire_drag.addItems(["Display", "Not display"])
        f.addRow("Display wireframe while dragging", self.cb_wire_drag)

        self.sp_edge_th = QSpinBox()
        self.sp_edge_th.setRange(1, 20)
        self.sp_edge_th.setValue(1)
        f.addRow("Edge thickness", self.sp_edge_th)

        self.sp_point_sz = QSpinBox()
        self.sp_point_sz.setRange(1, 40)
        self.sp_point_sz.setValue(7)
        f.addRow("Point size", self.sp_point_sz)

        self.cb_draw_patch = QComboBox()
        self.cb_draw_patch.addItems([
            "SCTpre V9 compatible", "Standard", "Hardware acceleration"])
        self.cb_draw_patch.setCurrentText("Standard")
        f.addRow("Drawing mode (Patch and mesh)", self.cb_draw_patch)

        self.cb_draw_solid = QComboBox()
        self.cb_draw_solid.addItems(["Immediate", "DisplayList", "VBO"])
        self.cb_draw_solid.setCurrentText("VBO")
        f.addRow("Drawing mode (Solid)", self.cb_draw_solid)

        self.cb_draw_rubber = QComboBox()
        self.cb_draw_rubber.addItems(["GDI", "OpenGL"])
        self.cb_draw_rubber.setCurrentText("OpenGL")
        f.addRow("Drawing mode (Rubber-type functions)", self.cb_draw_rubber)
        return w

    def _page_draw_part(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.col_part_before = _ColorBtn(QColor(0, 255, 0))
        self.col_part_after = _ColorBtn(QColor(0, 0, 255))
        self.col_edge_cad = _ColorBtn(QColor(0, 0, 0))
        self.col_vertex = _ColorBtn(QColor(0, 0, 0))
        self.col_facet_mdl = _ColorBtn(QColor(0, 255, 255))
        self.col_wiz_ridge = _ColorBtn(QColor(255, 255, 0))
        self.col_wiz_facet = _ColorBtn(QColor(0, 0, 0))
        self.col_sel_before = _ColorBtn(QColor(173, 216, 230))
        self.col_sel_after = _ColorBtn(QColor(70, 130, 180))
        self.col_sel_face = _ColorBtn(QColor(128, 128, 128))
        self.col_sel_edge = _ColorBtn(QColor(255, 0, 0))
        self.col_sel_part_edge = _ColorBtn(QColor(0, 255, 255))
        self.col_hi_ridge = _ColorBtn(QColor(255, 255, 0))

        f.addRow("Color of parts / Before building model",
                 self.col_part_before)
        f.addRow("Color of parts / After building model",
                 self.col_part_after)
        f.addRow("Edge color of CAD parts/Ridge color", self.col_edge_cad)
        f.addRow("Vertex color", self.col_vertex)
        f.addRow("Facet edge color (MDL)", self.col_facet_mdl)

        self.cb_vp_edge = QComboBox()
        self.cb_vp_edge.addItems([
            "Same color with facet edge (MDL)",
            "Same color with individual surface",
            "Specify individually",
        ])
        f.addRow("Facet edge color (Virtual part)", self.cb_vp_edge)
        self.col_vp_edge = _ColorBtn(QColor(0, 255, 255))
        f.addRow("Edge color (Virtual part)", self.col_vp_edge)

        f.addRow("Analysis model wizard / Ridge color", self.col_wiz_ridge)
        f.addRow("Analysis model wizard / Facet edge color",
                 self.col_wiz_facet)
        f.addRow("Color of selected parts / Before building model",
                 self.col_sel_before)
        f.addRow("Color of selected parts / After building model",
                 self.col_sel_after)
        f.addRow("Selected face color", self.col_sel_face)
        f.addRow("Selected edge color", self.col_sel_edge)
        f.addRow("Edge color of selected parts", self.col_sel_part_edge)
        f.addRow("Highlighted ridge color", self.col_hi_ridge)

        self.sp_sel_edge_th = QSpinBox()
        self.sp_sel_edge_th.setRange(1, 20)
        self.sp_sel_edge_th.setValue(2)
        f.addRow("Selected edge thickness (CAD part/Virtual part)",
                 self.sp_sel_edge_th)
        self.sp_sel_part_th = QSpinBox()
        self.sp_sel_part_th.setRange(1, 20)
        self.sp_sel_part_th.setValue(4)
        f.addRow("Edge thickness of selected parts", self.sp_sel_part_th)

        self.cb_disp_vp_edge = QComboBox()
        self.cb_disp_vp_edge.addItems(["Display", "Not display"])
        self.cb_disp_vp_edge.setCurrentText("Not display")
        f.addRow("Display facet edge of virtual part", self.cb_disp_vp_edge)
        self.chk_smooth_diag = QCheckBox(
            "Display diagonal lines and curves smoothly")
        f.addRow("", self.chk_smooth_diag)

        self.cb_cad_acc = QComboBox()
        self.cb_cad_acc.addItems([
            "Very coarse", "Coarse", "Standard", "Fine", "Very fine"])
        self.cb_cad_acc.setCurrentText("Standard")
        f.addRow("Accuracy of CAD part display", self.cb_cad_acc)

        self.sl_trans = QSlider(Qt.Horizontal)
        self.sl_trans.setRange(0, 1000)
        self.sl_trans.setValue(498)
        self.lab_trans = QLabel("49.8")
        tr = QHBoxLayout()
        tr.addWidget(self.sl_trans, 1)
        tr.addWidget(self.lab_trans)
        self.sl_trans.valueChanged.connect(
            lambda v: self.lab_trans.setText(f"{v / 10.0:.1f}"))
        f.addRow("Transmittance", tr)
        return w

    def _page_draw_oct(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.col_oct_edge = _ColorBtn(QColor(255, 0, 255))
        self.col_oct_face = _ColorBtn(QColor(255, 182, 193))
        f.addRow("Edge color", self.col_oct_edge)
        f.addRow("Face color", self.col_oct_face)
        return w

    def _page_draw_mesh(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.col_mesh_edge = _ColorBtn(QColor(255, 0, 255))
        self.col_mesh_face = _ColorBtn(QColor(255, 255, 0))
        self.col_mesh_inner = _ColorBtn(QColor(0, 255, 0))
        self.col_mesh_sel = _ColorBtn(QColor(255, 0, 0))
        f.addRow("Edge color", self.col_mesh_edge)
        f.addRow("Face color", self.col_mesh_face)
        f.addRow("Inner face color", self.col_mesh_inner)
        f.addRow("Selected face color", self.col_mesh_sel)
        return w

    def _page_selection(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_ctrl_multi = QCheckBox(
            "Use Ctrl to select multiple parts")
        v.addWidget(self.chk_ctrl_multi)
        v.addStretch(1)
        return w

    def _page_cad_d(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_auto_repair = QCheckBox(
            "Run automatic repair after loading CAD files")
        self.chk_auto_repair.setChecked(True)
        v.addWidget(self.chk_auto_repair)

        self.chk_color_region = QCheckBox(
            "Define surface regions by color automatically "
            "when loading CAD files")
        self.chk_color_region.setChecked(True)
        v.addWidget(self.chk_color_region)

        f = QFormLayout()
        self.ed_colors_ini = QLineEdit("Colors.ini")
        f.addRow(
            "File which relates color to surface region name",
            _make_refer("Colors.ini", self.ed_colors_ini, file_mode=True,
                        filter_="INI (*.ini);;All (*)"))
        self.sp_color_thr = QDoubleSpinBox()
        self.sp_color_thr.setDecimals(4)
        self.sp_color_thr.setRange(0.0, 1.0)
        self.sp_color_thr.setSingleStep(0.01)
        self.sp_color_thr.setValue(0.0)
        self.sl_color_thr = QSlider(Qt.Horizontal)
        self.sl_color_thr.setRange(0, 255)
        thr = QHBoxLayout()
        thr.addWidget(self.sl_color_thr, 1)
        thr.addWidget(self.sp_color_thr)
        self.sl_color_thr.valueChanged.connect(
            lambda v: self.sp_color_thr.setValue(v / 255.0))
        self.sp_color_thr.valueChanged.connect(
            lambda v: self.sl_color_thr.setValue(int(round(v * 255))))
        f.addRow("Threshold of the 'Same' colors", thr)
        v.addLayout(f)

        self.chk_valid_solid = QCheckBox("Check the validity of solids")
        v.addWidget(self.chk_valid_solid)
        self.ed_valid_report = QLineEdit()
        rf = QFormLayout()
        rf.addRow(
            "Output destination of the report",
            _make_refer("Report", self.ed_valid_report, file_mode=True))
        v.addLayout(rf)
        v.addStretch(1)
        return w

    def _page_mesh_d(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_undef_prism = QCheckBox(
            "[Undefined (Fluid Stress)] region is displayed in the "
            "[Parameters for Prism Layer Insertion] dialog.")
        self.chk_quality = QCheckBox(
            "Element quality is checked after meshing process.")
        self.chk_target_elems = QCheckBox(
            "Set/Check the target number of elements to the default "
            "when changing the project type")
        self.chk_target_elems.setChecked(True)
        v.addWidget(self.chk_undef_prism)
        v.addWidget(self.chk_quality)
        v.addWidget(self.chk_target_elems)

        g = QGroupBox("Target number of elements")
        gf = QFormLayout(g)
        self.sp_nastran_elems = QSpinBox()
        self.sp_nastran_elems.setRange(1, 2_000_000_000)
        self.sp_nastran_elems.setValue(10000)
        gf.addRow("scFLOW2Nastran : Structural Session",
                  self.sp_nastran_elems)
        v.addWidget(g)

        self.chk_assoc_surf = QCheckBox(
            "Associate mesh surface with model surface in pph loading")
        self.chk_assoc_surf.setChecked(True)
        self.chk_parallel_facet = QCheckBox(
            "Use parallel version of facet creation for Voxel fitting mesher")
        v.addWidget(self.chk_assoc_surf)
        v.addWidget(self.chk_parallel_facet)
        v.addStretch(1)
        return w

    def _page_initialize(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Initialize window layout."))
        b1 = QPushButton("Reset to Initial Setting")
        b1.clicked.connect(lambda: QMessageBox.information(
            self, "Initialize",
            "Window layout will be restored on next launch "
            "(viewer session note)."))
        v.addWidget(b1)
        v.addSpacing(12)
        v.addWidget(QLabel("Initialize default project configurations."))
        b2 = QPushButton("Reset to Initial Setting")
        b2.clicked.connect(self._init_project_defaults)
        v.addWidget(b2)
        v.addStretch(1)
        return w

    # ── Project pages ─────────────────────────────────────────────

    def _page_project_type(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        note = QLabel(
            "Set the project type. When using the scFLOW2Actran or "
            "scFLOW2Nastran, select the session to be setup.")
        note.setWordWrap(True)
        v.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Project Type"))
        self.cb_project_type = QComboBox()
        self.cb_project_type.addItems([
            "scFLOW",
            "scFAST (GPU solver)",
            "scFLOW2Actran : Fluid Session",
            "scFLOW2Actran : Acoustic Session",
            "scFLOW2Nastran : Fluid Session",
            "scFLOW2Nastran : Structural Session",
        ])
        row.addWidget(self.cb_project_type, 1)
        v.addLayout(row)
        foot = QLabel(
            "* Project type can be changed to scFLOW2Actran acoustic "
            "session or scFLOW2Nastran structural session only before "
            "building analysis model.")
        foot.setWordWrap(True)
        v.addWidget(foot)
        v.addLayout(_default_bar(
            lambda: None,
            lambda: self.cb_project_type.setCurrentText("scFLOW")))
        v.addStretch(1)
        return w

    def _page_unit(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Internal unit"))
        self.cb_internal = QComboBox()
        self.cb_internal.addItems(["m", "mm", "cm", "km", "in", "ft"])
        row.addWidget(self.cb_internal)
        row.addStretch(1)
        v.addLayout(row)
        v.addWidget(QLabel("Display unit"))
        self.tbl_unit = QTableWidget(16, 3)
        self.tbl_unit.setHorizontalHeaderLabels(["Unit type", "Unit", ""])
        self.tbl_unit.setItem(0, 0, QTableWidgetItem("Length"))
        self.cb_display_len = QComboBox()
        self.cb_display_len.addItems(["m", "mm", "cm", "km", "in", "ft"])
        self.tbl_unit.setCellWidget(0, 1, self.cb_display_len)
        self.tbl_unit.horizontalHeader().setStretchLastSection(True)
        self.tbl_unit.verticalHeader().setVisible(False)
        self.tbl_unit.setMinimumHeight(280)
        v.addWidget(self.tbl_unit, 1)
        v.addLayout(_default_bar(lambda: None, self._reset_unit))
        return w

    def _page_cad_import(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox("CAD data import type")
        gv = QVBoxLayout(g)
        self.rad_import_solid = QRadioButton("Import as solid")
        self.rad_import_facet = QRadioButton("Import as facet")
        self.rad_import_solid.setChecked(True)
        self._import_type = QButtonGroup(w)
        self._import_type.addButton(self.rad_import_solid)
        self._import_type.addButton(self.rad_import_facet)
        gv.addWidget(self.rad_import_solid)

        self._solid_box = QWidget()
        sv = QVBoxLayout(self._solid_box)
        sv.setContentsMargins(20, 0, 0, 0)
        lib = QGroupBox("CAD data conversion library")
        lv = QVBoxLayout(lib)
        self.rad_lib_scf = QRadioButton(
            "scFLOW Extension Option (CAD Data Exchange)")
        self.rad_lib_datakit = QRadioButton("Datakit")
        self.rad_lib_msc = QRadioButton("MSC CAD Translator")
        self.rad_lib_datakit.setChecked(True)
        self._lib_group = QButtonGroup(w)
        for r in (self.rad_lib_scf, self.rad_lib_datakit, self.rad_lib_msc):
            self._lib_group.addButton(r)
            lv.addWidget(r)
        sv.addWidget(lib)
        self.chk_ignore_colors = QCheckBox(
            "Ignore face colors in Parasolid while loading")
        self.chk_ignore_names = QCheckBox(
            "Ignore face names in Parasolid while loading")
        self.chk_ignore_colors.setChecked(True)
        self.chk_ignore_names.setChecked(True)
        self.chk_step_lib = QCheckBox(
            "Use CAD data conversion library for loading STEP files")
        sv.addWidget(self.chk_ignore_colors)
        sv.addWidget(self.chk_ignore_names)
        sv.addWidget(self.chk_step_lib)
        gv.addWidget(self._solid_box)
        gv.addWidget(self.rad_import_facet)
        v.addWidget(g)

        self.chk_dk_ver = QCheckBox("Specify datakit version")
        self.cb_dk_ver = QComboBox()
        for ver in (
            "2021", "2021 (Datakit kernel)",
            "2022", "2022 (Datakit kernel)",
            "2023", "2023 (Datakit kernel)",
            "2024", "2024 (Datakit kernel)",
            "2025", "2025 (Datakit kernel)",
        ):
            self.cb_dk_ver.addItem(ver)
        self.cb_dk_ver.setCurrentText("2021")
        self.cb_dk_ver.setEnabled(False)
        self.chk_dk_ver.toggled.connect(self.cb_dk_ver.setEnabled)
        # 兼容旧 load 字段名
        self.sp_dk_ver = self.cb_dk_ver
        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 0, 0)
        row.addWidget(self.chk_dk_ver)
        row.addWidget(QLabel("Datakit version"))
        row.addWidget(self.cb_dk_ver)
        row.addStretch(1)
        v.addLayout(row)

        def _sync_solid(_=False) -> None:
            on = self.rad_import_solid.isChecked()
            self._solid_box.setEnabled(on)

        self.rad_import_solid.toggled.connect(_sync_solid)
        _sync_solid()
        v.addLayout(_default_bar(lambda: None, self._reset_cad_import))
        v.addStretch(1)
        return w

    def _page_closed_vol(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        mu, self.cb_mu_closed = _meshing_unit_row()
        v.addLayout(mu)
        self.sp_same = _SciSpin(1e-6)
        self.sp_sew = _SciSpin(1e-6)
        self.sp_nonman = _SciSpin(1e-6)
        self.sp_contact = _SciSpin(1e-6)
        self.sp_short = _SciSpin(1e-8)
        self.sp_face_match = QDoubleSpinBox()
        self.sp_face_match.setDecimals(6)
        self.sp_face_match.setRange(0.0, 1e6)
        self.sp_face_match.setValue(0.05)
        specs = (
            ("Distance to regard two bodies as 'Same' "
             "(Specified in the internal unit)",
             "When the displacement of two bodies is below this value, "
             "they are considered the same.",
             self.sp_same, "m"),
            ("Distance to sew two isolated edges "
             "(Specified in the internal unit)",
             "When the displacement of two isolated edges is below this "
             "value, sewing of the edges is attempted.",
             self.sp_sew, "m"),
            ("Distance to detect non-manifold shape "
             "(Specified in the internal unit)",
             "When the displacement of two neighboring faces is below "
             "this value, they are considered the same.",
             self.sp_nonman, "m"),
            ("Distance to detect contact bodies "
             "(Specified in the internal unit)",
             "When the displacement of two different faces is below this "
             "value, two bodies share one common face.",
             self.sp_contact, "m"),
            ("Parameter to calculate a short distance",
             "When the ratio of the distance to the model size is below "
             "this value, the distance is considered as the short distance.",
             self.sp_short, ""),
            ("Tolerance of face matching",
             "Set the tolerance of the face matching in Analysis Model "
             "Wizard as a ratio to facet edge length.",
             self.sp_face_match, ""),
        )
        for title, desc, ed, unit in specs:
            v.addWidget(_closed_group(title, desc, ed, unit))
        v.addLayout(_default_bar(lambda: None, self._reset_closed_vol))
        v.addStretch(1)
        return w

    def _page_tiny_faces(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        mu, self.cb_mu_tiny = _meshing_unit_row()
        v.addLayout(mu)
        g = QGroupBox("Width of faces to regard as 'Tiny'")
        gv = QVBoxLayout(g)
        self.rad_tiny_ratio = QRadioButton(
            "Specify ratio of assembly or parts size")
        self.rad_tiny_width = QRadioButton("Specify width of faces")
        self.rad_tiny_ratio.setChecked(True)
        self._tiny_group = QButtonGroup(w)
        self._tiny_group.addButton(self.rad_tiny_ratio)
        self._tiny_group.addButton(self.rad_tiny_width)
        gv.addWidget(self.rad_tiny_ratio)
        row = QHBoxLayout()
        row.addWidget(QLabel("Less than 1/"))
        self.sp_tiny_den = QSpinBox()
        self.sp_tiny_den.setRange(1, 1_000_000)
        self.sp_tiny_den.setValue(1000)
        row.addWidget(self.sp_tiny_den)
        row.addWidget(QLabel("of the size of assembly or parts size"))
        row.addStretch(1)
        gv.addLayout(row)
        gv.addWidget(self.rad_tiny_width)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Width of faces less than"))
        self.sp_tiny_abs = _SciSpin(1e-6)
        row2.addWidget(self.sp_tiny_abs)
        row2.addStretch(1)
        gv.addLayout(row2)
        v.addWidget(g)

        def _sync_tiny(_=False) -> None:
            ratio = self.rad_tiny_ratio.isChecked()
            self.sp_tiny_den.setEnabled(ratio)
            self.sp_tiny_abs.setEnabled(not ratio)

        self.rad_tiny_ratio.toggled.connect(_sync_tiny)
        _sync_tiny()
        v.addLayout(_default_bar(lambda: None, self._reset_tiny))
        v.addStretch(1)
        return w

    def _page_ridges(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        mu, self.cb_mu_ridge = _meshing_unit_row()
        v.addLayout(mu)
        g1 = QGroupBox("Edges to regard as 'Ridges'")
        r1 = QHBoxLayout(g1)
        r1.addWidget(QLabel(
            "Two faces whose normal vectors make angle greater than"))
        self.sp_ridge_ang = QDoubleSpinBox()
        self.sp_ridge_ang.setDecimals(1)
        self.sp_ridge_ang.setRange(0.0, 180.0)
        self.sp_ridge_ang.setValue(45.0)
        r1.addWidget(self.sp_ridge_ang)
        r1.addWidget(QLabel("degrees"))
        r1.addStretch(1)
        v.addWidget(g1)

        g2 = QGroupBox("When MDL ridges are calculated from solid object")
        gv = QVBoxLayout(g2)
        self.chk_all_edges_ridge = QCheckBox(
            "All edges of solids and sheets become ridges of MDL")
        self.chk_proj_solid = QCheckBox(
            "Project boundary edges of solids")
        self.chk_proj_sheet = QCheckBox(
            "Project boundary edges of sheets")
        self.chk_proj_solid.setChecked(True)
        self.chk_proj_sheet.setChecked(True)
        gv.addWidget(self.chk_all_edges_ridge)
        gv.addWidget(self.chk_proj_solid)
        gv.addWidget(self.chk_proj_sheet)
        v.addWidget(g2)
        v.addLayout(_default_bar(lambda: None, self._reset_ridges))
        v.addStretch(1)
        return w

    def _page_mesher_faceter(self) -> QWidget:
        """Reuse Condition Mesher/Faceter body（Settings 模式隐藏专有行）。"""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        try:
            from nav_panels import MesherFaceterBody
            self._mf_body = MesherFaceterBody(w, settings_mode=True)
            v.addWidget(self._mf_body, 1)
        except Exception as exc:  # noqa: BLE001
            self._mf_body = None
            lab = QLabel(
                f"Mesher/Faceter panel unavailable: {exc}\n"
                "Use [Condition] – [Mesher/Faceter Setting].")
            lab.setWordWrap(True)
            v.addWidget(lab)
            if self._on_open_mesher:
                btn = QPushButton("Open Mesher/Faceter Setting…")
                btn.clicked.connect(self._on_open_mesher)
                v.addWidget(btn)
        bar = _default_bar(lambda: None, self._reset_mesher_page)
        v.addLayout(bar)
        return w

    def _page_voxel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_voxel_convert = QCheckBox(
            "Convert octant to rough polyhedral mesh in output process "
            "of cmb file for better memory distribution in meshing")
        v.addWidget(self.chk_voxel_convert)
        row = QHBoxLayout()
        row.addWidget(QLabel("Initial maximum number of elements"))
        self.sp_voxel_max = QSpinBox()
        self.sp_voxel_max.setRange(1, 2_000_000_000)
        self.sp_voxel_max.setValue(15_000_000)
        self.sp_voxel_max.setEnabled(False)
        self.chk_voxel_convert.toggled.connect(self.sp_voxel_max.setEnabled)
        row.addWidget(self.sp_voxel_max)
        row.addStretch(1)
        v.addLayout(row)
        v.addLayout(_default_bar(lambda: None, self._reset_voxel))
        v.addStretch(1)
        return w

    def _page_mesh_p(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chk_keep_assy = QCheckBox(
            "Keep assembly information when loading GPH file")
        v.addWidget(self.chk_keep_assy)
        v.addLayout(_default_bar(
            lambda: None,
            lambda: self.chk_keep_assy.setChecked(False)))
        v.addStretch(1)
        return w

    def _page_mesh_param(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        for label in (
            "Octree parameter",
            "Surface mesh parameter",
            "Volume mesh parameter",
            "Prism layer parameter",
            "Polyhedral conversion parameter",
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            b1 = QPushButton("Set Current Settings as Default")
            b2 = QPushButton("Reset Current Settings to Default")
            b1.clicked.connect(
                lambda _=False, n=label: self._mesh_param_msg("set", n))
            b2.clicked.connect(
                lambda _=False, n=label: self._mesh_param_msg("reset", n))
            row.addWidget(b1)
            row.addWidget(b2)
            v.addLayout(row)
        v.addStretch(1)
        return w

    def _page_file_p(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        g1 = QGroupBox("Compression type of GPH file")
        r1 = QHBoxLayout(g1)
        self.cb_gph_comp = QComboBox()
        self.cb_gph_comp.addItems(["Uncompressed", "Compressed"])
        r1.addWidget(self.cb_gph_comp)
        r1.addStretch(1)
        v.addWidget(g1)

        g2 = QGroupBox(
            "Saving mapping information between model and mesh surfaces "
            "to GPH file")
        gv = QVBoxLayout(g2)
        self.cb_gph_map = QComboBox()
        self.cb_gph_map.addItems(["Save", "Do not save"])
        self.cb_gph_map.setCurrentText("Save")
        row = QHBoxLayout()
        row.addWidget(self.cb_gph_map)
        row.addStretch(1)
        gv.addLayout(row)
        n1 = QLabel(
            "* Surface region can be registered after meshing if meshing "
            "is done with setting of [Save].")
        n2 = QLabel(
            "* Mapping information is not saved when voxel-fitting mesher "
            "is used regardless of the setting.")
        for n in (n1, n2):
            n.setWordWrap(True)
            gv.addWidget(n)
        v.addWidget(g2)
        v.addLayout(_default_bar(lambda: None, self._reset_file_p))
        v.addStretch(1)
        return w

    def _page_msc(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox(
            "Command specification for the co-simulation using MSC CoSim")
        gv = QVBoxLayout(g)
        self.cb_msc = QComboBox()
        self.cb_msc.addItems([
            "Conventional specification", "New specification"])
        row = QHBoxLayout()
        row.addWidget(self.cb_msc)
        row.addStretch(1)
        gv.addLayout(row)
        for text in (
            "* When the [New specification] is selected, the COSIM "
            "command is used. When the [Conventional specification] is "
            "selected, the COSIM_STRUCTURE or COSIM_MOVE command is used.",
            "* The contents of the condition wizard changes depending on "
            "the selected specification.",
            "* The co-simulation settings need to be configured "
            "individually for each specification.",
        ):
            lab = QLabel(text)
            lab.setWordWrap(True)
            gv.addWidget(lab)
        v.addWidget(g)
        v.addLayout(_default_bar(
            lambda: None,
            lambda: self.cb_msc.setCurrentIndex(0)))
        v.addStretch(1)
        return w

    # ── navigation / load / apply ─────────────────────────────────

    def _select_key(self, key: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                it = root.child(j)
                if it.data(0, Qt.UserRole) == key:
                    self.tree.setCurrentItem(it)
                    return

    def _on_nav(self, cur: Optional[QTreeWidgetItem],
                _prev: Optional[QTreeWidgetItem]) -> None:
        if cur is None:
            return
        key = cur.data(0, Qt.UserRole)
        w = self._pages.get(key)
        if w is not None:
            self.stack.setCurrentWidget(w)

    def _reset_unit(self) -> None:
        self.cb_internal.setCurrentText("m")
        self.cb_display_len.setCurrentText("m")

    def _reset_cad_import(self) -> None:
        self.rad_import_solid.setChecked(True)
        self.rad_lib_datakit.setChecked(True)
        self.chk_ignore_colors.setChecked(True)
        self.chk_ignore_names.setChecked(True)
        self.chk_step_lib.setChecked(False)
        self.chk_dk_ver.setChecked(False)
        self.cb_dk_ver.setCurrentText("2021")

    def _reset_closed_vol(self) -> None:
        self.sp_same.setValue(1e-6)
        self.sp_sew.setValue(1e-6)
        self.sp_nonman.setValue(1e-6)
        self.sp_contact.setValue(1e-6)
        self.sp_short.setValue(1e-8)
        self.sp_face_match.setValue(0.05)

    def _reset_tiny(self) -> None:
        self.rad_tiny_ratio.setChecked(True)
        self.sp_tiny_den.setValue(1000)
        self.sp_tiny_abs.setValue(1e-6)
        self.sp_tiny_den.setEnabled(True)
        self.sp_tiny_abs.setEnabled(False)

    def _reset_ridges(self) -> None:
        self.sp_ridge_ang.setValue(45.0)
        self.chk_all_edges_ridge.setChecked(False)
        self.chk_proj_solid.setChecked(True)
        self.chk_proj_sheet.setChecked(True)

    def _reset_voxel(self) -> None:
        self.chk_voxel_convert.setChecked(False)
        self.sp_voxel_max.setValue(15_000_000)

    def _reset_file_p(self) -> None:
        self.cb_gph_comp.setCurrentText("Uncompressed")
        self.cb_gph_map.setCurrentText("Save")

    def _reset_mesher_page(self) -> None:
        if self._mf_body is not None:
            self._mf_body.load(self._ctx)

    def _mesh_param_msg(self, op: str, name: str) -> None:
        QMessageBox.information(
            self, "Mesh Parameter",
            f"{'Set' if op == 'set' else 'Reset'} defaults for [{name}] "
            "(stored as session preference).")

    def _init_project_defaults(self) -> None:
        if QMessageBox.question(
                self, "Initialize",
                "Reset Project Configuration defaults?") != QMessageBox.Yes:
            return
        self._reset_unit()
        self._reset_cad_import()
        self._reset_closed_vol()
        self._reset_tiny()
        self._reset_ridges()
        self._reset_voxel()
        self._reset_file_p()
        self.cb_project_type.setCurrentText("scFLOW")
        self.chk_keep_assy.setChecked(False)
        self.cb_msc.setCurrentIndex(0)
        self._reset_mesher_page()

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {})
        opt = sess.setdefault("option_nav", {})
        env = sess.setdefault("option_env", {})

        self.chk_show_bam.setChecked(bool(opt.get("show_bam_item", True)))
        self.chk_pre_bam.setChecked(
            bool(opt.get("enable_pre_bam_conditions", False)))
        self.chk_always_wiz.setChecked(
            bool(opt.get("always_show_wizard", False)))
        self.chk_show_mesher.setChecked(
            bool(opt.get("show_mesher_item", True)))
        self.chk_show_proj.setChecked(
            bool(opt.get("show_project_type", False)))
        self.chk_enable_wrap.setChecked(
            bool(opt.get("enable_wrapping", False)))

        self.ed_home.setText(str(env.get("home_folder", "")))
        self.ed_work.setText(str(env.get("work_folder", "")))
        self.chk_temp_in_work.setChecked(
            bool(env.get("temp_in_work", False)))
        self.ed_prp.setText(str(env.get("prp_file", "")))
        lvl = int(env.get("compress_level", 0) or 0)
        (self.rad_comp0, self.rad_comp1, self.rad_comp2)[
            max(0, min(2, lvl))].setChecked(True)
        self.chk_backup_mesh.setChecked(bool(env.get("backup_before_mesh", False)))

        unit = env.get("internal_unit", "m")
        i = self.cb_internal.findText(str(unit))
        if i >= 0:
            self.cb_internal.setCurrentIndex(i)
        disp = str(env.get("display_length", unit))
        i = self.cb_display_len.findText(disp)
        if i >= 0:
            self.cb_display_len.setCurrentIndex(i)
        else:
            self.cb_display_len.setCurrentText("m")

        pt = env.get("project_type", "scFLOW")
        j = self.cb_project_type.findText(str(pt))
        if j >= 0:
            self.cb_project_type.setCurrentIndex(j)

        # drawing / selection / cad / mesh detailed from env
        dg = env.get("draw_gen") or {}
        if "bg_top" in dg:
            self.col_bg_top.set_color(QColor(dg["bg_top"]))
        if "bg_bot" in dg:
            self.col_bg_bot.set_color(QColor(dg["bg_bot"]))
        if "wire_drag" in dg:
            self.cb_wire_drag.setCurrentText(str(dg["wire_drag"]))
        if "edge_th" in dg:
            self.sp_edge_th.setValue(int(dg["edge_th"]))
        if "point_sz" in dg:
            self.sp_point_sz.setValue(int(dg["point_sz"]))

        self.chk_ctrl_multi.setChecked(
            bool((env.get("selection") or {}).get("ctrl_multi", False)))
        cad = env.get("cad_d") or {}
        self.chk_auto_repair.setChecked(bool(cad.get("auto_repair", True)))
        self.chk_color_region.setChecked(bool(cad.get("color_region", True)))
        self.ed_colors_ini.setText(str(cad.get("colors_ini", "Colors.ini")))
        self.sp_color_thr.setValue(float(cad.get("color_thr", 0.0)))
        self.chk_valid_solid.setChecked(bool(cad.get("valid_solid", False)))
        self.ed_valid_report.setText(str(cad.get("valid_report", "")))

        md = env.get("mesh_d") or {}
        self.chk_undef_prism.setChecked(bool(md.get("undef_prism", False)))
        self.chk_quality.setChecked(bool(md.get("quality", False)))
        self.chk_target_elems.setChecked(bool(md.get("target_elems", True)))
        self.sp_nastran_elems.setValue(int(md.get("nastran_elems", 10000)))
        self.chk_assoc_surf.setChecked(bool(md.get("assoc_surf", True)))
        self.chk_parallel_facet.setChecked(
            bool(md.get("parallel_facet", False)))

        # project pages
        ci = env.get("cad_import") or {}
        if ci.get("as_facet"):
            self.rad_import_facet.setChecked(True)
        else:
            self.rad_import_solid.setChecked(True)
        lib = ci.get("library", "datakit")
        {"scf": self.rad_lib_scf, "datakit": self.rad_lib_datakit,
         "msc": self.rad_lib_msc}.get(lib, self.rad_lib_datakit).setChecked(True)
        self.chk_ignore_colors.setChecked(bool(ci.get("ignore_colors", True)))
        self.chk_ignore_names.setChecked(bool(ci.get("ignore_names", True)))
        self.chk_step_lib.setChecked(bool(ci.get("step_lib", False)))
        self.chk_dk_ver.setChecked(bool(ci.get("specify_dk", False)))
        dk = str(ci.get("dk_ver", "2021"))
        j = self.cb_dk_ver.findText(dk)
        if j < 0:
            # 旧版存整数年份
            j = self.cb_dk_ver.findText(dk.split()[0] if dk else "2021")
        if j >= 0:
            self.cb_dk_ver.setCurrentIndex(j)

        cv = env.get("closed_vol") or {}
        for sp, key, default in (
            (self.sp_same, "same", 1e-6),
            (self.sp_sew, "sew", 1e-6),
            (self.sp_nonman, "nonman", 1e-6),
            (self.sp_contact, "contact", 1e-6),
            (self.sp_short, "short", 1e-8),
            (self.sp_face_match, "face_match", 0.05),
        ):
            if key in cv:
                try:
                    sp.setValue(float(cv[key]))
                except (TypeError, ValueError):
                    sp.setValue(default)

        tf = env.get("tiny_faces") or {}
        if tf.get("mode") == "width":
            self.rad_tiny_width.setChecked(True)
        else:
            self.rad_tiny_ratio.setChecked(True)
        if "ratio_den" in tf:
            self.sp_tiny_den.setValue(int(tf["ratio_den"]))
        if "abs_width" in tf:
            self.sp_tiny_abs.setValue(float(tf["abs_width"]))

        rd = env.get("ridges") or {}
        if "angle" in rd:
            self.sp_ridge_ang.setValue(float(rd["angle"]))
        self.chk_all_edges_ridge.setChecked(bool(rd.get("all_edges", False)))
        self.chk_proj_solid.setChecked(bool(rd.get("proj_solid", True)))
        self.chk_proj_sheet.setChecked(bool(rd.get("proj_sheet", True)))

        vx = env.get("voxel") or {}
        self.chk_voxel_convert.setChecked(bool(vx.get("convert", False)))
        self.sp_voxel_max.setValue(int(vx.get("max_elems", 15_000_000)))
        self.chk_keep_assy.setChecked(
            bool((env.get("mesh_p") or {}).get("keep_assy", False)))
        fp = env.get("file_p") or {}
        if "gph_comp" in fp:
            self.cb_gph_comp.setCurrentText(str(fp["gph_comp"]))
        if "gph_map" in fp:
            self.cb_gph_map.setCurrentText(str(fp["gph_map"]))
        if "msc" in env:
            k = self.cb_msc.findText(str(env["msc"]))
            if k >= 0:
                self.cb_msc.setCurrentIndex(k)

        if self._mf_body is not None:
            self._mf_body.load(ctx)

    def apply(self, ctx: dict) -> bool:
        sess = ctx.setdefault("session", {})
        sess["option_nav"] = {
            "show_bam_item": self.chk_show_bam.isChecked(),
            "enable_pre_bam_conditions": self.chk_pre_bam.isChecked(),
            "always_show_wizard": self.chk_always_wiz.isChecked(),
            "show_mesher_item": self.chk_show_mesher.isChecked(),
            "show_project_type": self.chk_show_proj.isChecked(),
            "enable_wrapping": self.chk_enable_wrap.isChecked(),
        }
        lvl = 0
        if self.rad_comp1.isChecked():
            lvl = 1
        elif self.rad_comp2.isChecked():
            lvl = 2
        lib = "datakit"
        if self.rad_lib_scf.isChecked():
            lib = "scf"
        elif self.rad_lib_msc.isChecked():
            lib = "msc"
        env = {
            "home_folder": self.ed_home.text().strip(),
            "work_folder": self.ed_work.text().strip(),
            "temp_in_work": self.chk_temp_in_work.isChecked(),
            "prp_file": self.ed_prp.text().strip(),
            "compress_level": lvl,
            "backup_before_mesh": self.chk_backup_mesh.isChecked(),
            "internal_unit": self.cb_internal.currentText(),
            "display_length": self.cb_display_len.currentText(),
            "project_type": self.cb_project_type.currentText(),
            "draw_gen": {
                "bg_top": self.col_bg_top.to_hex(),
                "bg_bot": self.col_bg_bot.to_hex(),
                "wire_drag": self.cb_wire_drag.currentText(),
                "edge_th": self.sp_edge_th.value(),
                "point_sz": self.sp_point_sz.value(),
                "draw_patch": self.cb_draw_patch.currentText(),
                "draw_solid": self.cb_draw_solid.currentText(),
                "draw_rubber": self.cb_draw_rubber.currentText(),
            },
            "selection": {"ctrl_multi": self.chk_ctrl_multi.isChecked()},
            "cad_d": {
                "auto_repair": self.chk_auto_repair.isChecked(),
                "color_region": self.chk_color_region.isChecked(),
                "colors_ini": self.ed_colors_ini.text().strip(),
                "color_thr": self.sp_color_thr.value(),
                "valid_solid": self.chk_valid_solid.isChecked(),
                "valid_report": self.ed_valid_report.text().strip(),
            },
            "mesh_d": {
                "undef_prism": self.chk_undef_prism.isChecked(),
                "quality": self.chk_quality.isChecked(),
                "target_elems": self.chk_target_elems.isChecked(),
                "nastran_elems": self.sp_nastran_elems.value(),
                "assoc_surf": self.chk_assoc_surf.isChecked(),
                "parallel_facet": self.chk_parallel_facet.isChecked(),
            },
            "cad_import": {
                "as_facet": self.rad_import_facet.isChecked(),
                "library": lib,
                "ignore_colors": self.chk_ignore_colors.isChecked(),
                "ignore_names": self.chk_ignore_names.isChecked(),
                "step_lib": self.chk_step_lib.isChecked(),
                "specify_dk": self.chk_dk_ver.isChecked(),
                "dk_ver": self.cb_dk_ver.currentText(),
            },
            "closed_vol": {
                "same": self.sp_same.value(),
                "sew": self.sp_sew.value(),
                "nonman": self.sp_nonman.value(),
                "contact": self.sp_contact.value(),
                "short": self.sp_short.value(),
                "face_match": self.sp_face_match.value(),
            },
            "tiny_faces": {
                "mode": ("width" if self.rad_tiny_width.isChecked()
                         else "ratio"),
                "ratio_den": self.sp_tiny_den.value(),
                "abs_width": self.sp_tiny_abs.value(),
                # keep legacy key for xenv sync
                "tiny_ref": (1.0 / max(1, self.sp_tiny_den.value())
                             if self.rad_tiny_ratio.isChecked()
                             else self.sp_tiny_abs.value()),
            },
            "ridges": {
                "angle": self.sp_ridge_ang.value(),
                "all_edges": self.chk_all_edges_ridge.isChecked(),
                "proj_solid": self.chk_proj_solid.isChecked(),
                "proj_sheet": self.chk_proj_sheet.isChecked(),
            },
            "voxel": {
                "convert": self.chk_voxel_convert.isChecked(),
                "max_elems": self.sp_voxel_max.value(),
            },
            "mesh_p": {"keep_assy": self.chk_keep_assy.isChecked()},
            "file_p": {
                "gph_comp": self.cb_gph_comp.currentText(),
                "gph_map": self.cb_gph_map.currentText(),
            },
            "msc": self.cb_msc.currentText(),
        }
        sess["option_env"] = env

        if self.chk_enable_wrap.isChecked():
            sess.setdefault("parts_control", {})["wrapping_allowed"] = True
        else:
            sess.setdefault("parts_control", {})["wrapping_allowed"] = False

        xenv = ctx.get("xenv")
        if xenv is not None:
            tiny = env.get("tiny_faces") or {}
            if self.rad_tiny_ratio.isChecked() and "ratio_den" in tiny:
                pphxml.set_xenv_value(
                    xenv, "FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO",
                    f"{1.0 / max(1, int(tiny['ratio_den'])):.15g}")
                ctx["xenv_dirty"] = True
            rd = env.get("ridges") or {}
            pphxml.set_xenv_value(
                xenv, "FACET", "PROJECT_SOLIDS",
                "true" if rd.get("proj_solid", True) else "false")
            pphxml.set_xenv_value(
                xenv, "FACET", "PROJECT_SHEETS",
                "true" if rd.get("proj_sheet", True) else "false")
            ctx["xenv_dirty"] = True

        if self._mf_body is not None and ctx.get("xenv") is not None:
            self._mf_body.apply(ctx)
        return True

    def _on_ok(self) -> None:
        if self.apply(self._ctx):
            self.accept()
