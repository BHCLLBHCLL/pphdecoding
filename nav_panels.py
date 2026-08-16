#!/usr/bin/env python3
"""scFLOWpre 风格 Navigation 弹出对话框（Prepare Parts / Build Analysis Model）。

点击 Navigation 叶子项时弹出独立子窗口（OK / Cancel / Apply），绑定
``main.xenv`` / ``main.xml`` / ``main.prp`` 与网格组状态。CAD 建体、
网格生成等执行步骤在本查看器中保存参数并提示需 scFLOWpre 完成。
"""

from __future__ import annotations

import functools
import math
import os
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

from PyQt5.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import (
    QBrush, QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
    QPolygon,
)
from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QSlider, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import condition_tree
import pphxml


def patch_message_box_offscreen() -> None:
    """offscreen 平台下把 QMessageBox 静态弹窗替换为日志输出。

    Windows anaconda PyQt5 实测：``QT_QPA_PLATFORM=offscreen`` 时
    ``QMessageBox.information`` 等静态方法的模态 exec 会触发 Qt 原生
    访问冲突（0xC0000005，整个进程死亡）——这就是全量回归中
    ``test_register_region`` 崩溃的根因。无头/测试环境改为打印日志并
    返回"确认"结果；桌面平台不受影响。
    """
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return

    def _quiet(name: str, ret, *args, **kwargs):
        title = args[1] if len(args) > 1 else ""
        text = args[2] if len(args) > 2 else ""
        print(f"[QMessageBox.{name}] {title}: {text}", flush=True)
        return ret

    for name in ("information", "warning", "critical", "question"):
        ret = QMessageBox.Yes if name == "question" else QMessageBox.Ok
        setattr(QMessageBox, name, functools.partial(_quiet, name, ret))


patch_message_box_offscreen()

# Navigation key → 是否弹出对话框
DIALOG_KEYS = frozenset({
    "parts_control", "import_part", "create_parts", "modify_parts",
    "specify_disc", "overset_mesh",
    "wrap_octree", "wrap_param",
    "begin_wrap", "cancel_wrap", "exec_wrap", "retry_wrap",
    "mesher_faceter", "regions", "non_solid", "part_material",
    "conditions", "build_am_detailed", "oct_param", "mesh_param", "execute",
    "option_nav",
})


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color:#555; font-size:11px; margin-bottom:4px;")
    return lab


def _bool_combo(parent=None) -> QComboBox:
    cb = QComboBox(parent)
    cb.addItem("true", "true")
    cb.addItem("false", "false")
    return cb


def _set_combo_data(cb: QComboBox, data: str) -> None:
    i = cb.findData(data)
    if i < 0:
        i = cb.findText(data)
    if i >= 0:
        cb.setCurrentIndex(i)


def _fmt_float(v: float) -> str:
    return f"{v:.15g}"


def _spin_f(decimals=6, lo=0.0, hi=1e9, val=0.0) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setDecimals(decimals)
    sp.setRange(lo, hi)
    sp.setValue(val)
    return sp


def _first_part(xml: Optional[pphxml.MainXml]):
    if xml is None:
        return None
    parts = xml.section("parts")
    if parts is None:
        return None
    return next(parts.iter("part"), None)


# ── 对话框内容页 ───────────────────────────────────────────────────


class _Body(QWidget):
    title = "Dialog"
    min_size = (520, 420)
    # 覆盖则 NavParamDialog 使用该按钮组合（默认 OK/Cancel/Apply）
    dialog_buttons: Optional[int] = None

    def load(self, ctx: dict) -> None:
        pass

    def apply(self, ctx: dict) -> bool:
        return True


def _region_icon(kind: str, size: int = 14) -> QIcon:
    """volume=绿立方，surface=绿菱形（对齐 scFLOWpre Part Tree）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor(46, 160, 67)
    p.setBrush(color)
    p.setPen(QPen(QColor(20, 90, 30), 1))
    if kind == "volume":
        p.drawRect(2, 2, size - 5, size - 5)
    else:
        cx = cy = size / 2
        r = size / 2 - 2
        p.drawPolygon(
            QPointF(cx, cy - r), QPointF(cx + r, cy),
            QPointF(cx, cy + r), QPointF(cx - r, cy))
    p.end()
    return QIcon(pm)


def _collect_octree_regions(ctx: dict) -> list[dict]:
    """Detail「Size for regions」行：对齐 scFLOWpre（fluid / Part / face /
    Part surface (@PartName)）。

    零件名来自 ``groups_info[*].xml_parts``（main.xml meshinggroup），
    不再写死 ``Part`` / ``Part surface (@Part)``。
    """
    rows: list[dict] = []
    seen: set[str] = set()

    def _add(name: Optional[str], kind: str) -> None:
        if not name or name in seen:
            return
        seen.add(name)
        rows.append({"name": name, "kind": kind})

    meta = ctx.get("regions_meta") or {}

    # 1) FluidRegion：显示 material/property 标签（手册/宿主一致）
    for fr in meta.get("fluid") or []:
        if not isinstance(fr, dict):
            continue
        label = (fr.get("label") or "").strip()
        if not label:
            name = (fr.get("name") or "").strip()
            prop = (fr.get("property") or fr.get("material") or "").strip()
            label = f"{prop} ({name})" if prop and name else name
        _add(label, "volume")

    # 2) XML volume 区域
    for r in meta.get("volume") or []:
        _add(r.get("name") if isinstance(r, dict) else None, "volume")

    # 3) Parts（Whole）下各零件 → 体积区域行
    part_names: list[str] = []
    seen_parts: set[str] = set()
    for info in (ctx.get("groups_info") or {}).values():
        for p in info.get("xml_parts") or []:
            pname = (p.get("name") if isinstance(p, dict) else None) or ""
            pname = pname.strip()
            if not pname or pname in seen_parts:
                continue
            seen_parts.add(pname)
            part_names.append(pname)
    for pname in part_names:
        _add(pname, "volume")

    # 4) Surface / face 区域（如 open）
    for cat in ("face", "special_face"):
        for r in meta.get(cat) or []:
            _add(r.get("name") if isinstance(r, dict) else None, "surface")

    # 5) 每个 Part 对应 Part surface (@name)
    for pname in part_names:
        _add(f"Part surface (@{pname})", "surface")

    # 空工程回退（与 box 单 Part 录制一致）
    if not rows:
        _add("Part", "volume")
        _add("Part surface (@Part)", "surface")
    elif not part_names and not any(
            r["name"].startswith("Part surface (") for r in rows):
        _add("Part", "volume")
        _add("Part surface (@Part)", "surface")
    return rows


def _model_bounds_from_ctx(ctx: dict) -> tuple[list[float], list[float]]:
    """从首个 MDL part 取包围盒；失败则用手册样例 0…0.01。"""
    lo = [0.0, 0.0, 0.0]
    hi = [0.01, 0.01, 0.01]
    for info in (ctx.get("groups_info") or {}).values():
        part = info.get("part")
        if part is None:
            continue
        xyz = getattr(part, "xyz", None)
        if xyz is None or getattr(xyz, "size", 0) == 0:
            continue
        try:
            import numpy as np
            arr = np.asarray(xyz, dtype=float)
            return arr.min(axis=0).tolist(), arr.max(axis=0).tolist()
        except Exception:  # noqa: BLE001
            continue
    return lo, hi


class PartsControlBody(_Body):
    """[Condition] – [Parts Control]（对齐 scFLOWpre 手册截图）。

    勾选后 Navigation → Prepare Parts 下插入对应项：
    Specify Discontinuous Parts / Overset Mesh；Wrapping 相关项出现在
    Prepare Parts / Build Analysis Model（见 NavigationWindow.set_parts_control）。
    """

    title = "Parts Control"
    min_size = (460, 280)
    dialog_buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 8)
        v.setSpacing(8)

        intro = QLabel(
            "Enable functions which requires grouping of parts. "
            "For example, rotation, translation, and wrapping.")
        intro.setWordWrap(True)
        v.addWidget(intro)

        grp = QGroupBox("Rotation, translation")
        gh = QHBoxLayout(grp)
        self.chk_disc = QCheckBox("Rotate (Discontinuous mesh)")
        self.chk_overset = QCheckBox("Rotate, move (Overset mesh)")
        self.chk_disc.setToolTip(
            "勾选后 Navigation 出现 [Specify Discontinuous Parts]。")
        self.chk_overset.setToolTip(
            "勾选后 Navigation 出现 [Overset Mesh]。")
        gh.addWidget(self.chk_disc)
        gh.addWidget(self.chk_overset)
        gh.addStretch(1)
        v.addWidget(grp)

        info = QLabel(
            "By selecting [Rotate (Discontinuous mesh)] or "
            "[Rotate, move (Overset mesh)], regions and conditions for "
            "discontinuous mesh or overset mesh are automatically created. "
            "When mixing plane is used, the parameters of mixing plane "
            "are set in the condition of the discontinuous mesh.")
        info.setWordWrap(True)
        info.setStyleSheet(
            "border:1px solid #bbb; background:#fafafa; padding:8px;")
        v.addWidget(info)

        self.chk_wrap = QCheckBox("Wrapping")
        self.chk_wrap.setToolTip(
            "勾选后 Navigation 出现 Wrapping 相关项"
            "（需环境设置中 Enable wrapping）。")
        v.addWidget(self.chk_wrap)

        tip = QLabel(
            "Items selected here are inserted under [Prepare Parts] "
            "in the Navigation Window.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(tip)
        v.addStretch(1)
        self._enable_wrapping = True

    def load(self, ctx: dict) -> None:
        pc = ctx.setdefault("session", {}).setdefault("parts_control", {})
        self.chk_disc.setChecked(bool(pc.get("discontinuous")))
        self.chk_overset.setChecked(bool(pc.get("overset")))
        self.chk_wrap.setChecked(bool(pc.get("wrapping")))
        # Wrapping：环境 Enable wrapping 关闭时隐藏（手册）；默认显示
        # 用会话标志而非 isVisible()（未 show 的控件 isVisible 恒为 False）
        self._enable_wrapping = bool(pc.get("enable_wrapping", True))
        self.chk_wrap.setVisible(self._enable_wrapping)

    def apply(self, ctx: dict) -> bool:
        wrap_on = self._enable_wrapping and self.chk_wrap.isChecked()
        ctx.setdefault("session", {})["parts_control"] = {
            "discontinuous": self.chk_disc.isChecked(),
            "overset": self.chk_overset.isChecked(),
            "wrapping": wrap_on,
            "enable_wrapping": self._enable_wrapping,
            "nav_dirty": True,
        }
        return True


class _PartsControlFollowupBody(_Body):
    """Parts Control 勾选后插入的 Navigation 项。

    OK 时写出宿主 VBS 草稿（``session['pending_vbs']``），由 GUI 落盘。
    """

    dialog_buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    min_size = (420, 180)
    _hint = ""
    _vbs_op = ""  # pipeline_plan.wrapping_actions 的 op 键

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 8)
        v.addWidget(_note(self._hint))
        self.chk_write_vbs = QCheckBox(
            "写出 scFLOWpre VBS 草稿（PartsControl / Wrapping 占位）")
        self.chk_write_vbs.setChecked(True)
        v.addWidget(self.chk_write_vbs)
        v.addStretch(1)

    def load(self, ctx: dict) -> None:
        return

    def apply(self, ctx: dict) -> bool:
        if self.chk_write_vbs.isChecked() and self._vbs_op:
            ctx.setdefault("session", {})["pending_vbs"] = {
                "op": self._vbs_op,
                "label": self.title,
            }
        return True


class SpecifyDiscontinuousPartsBody(_PartsControlFollowupBody):
    title = "Specify Discontinuous Parts"
    _vbs_op = "specify_disc"
    _hint = (
        "[Condition] – [Specify Discontinuous Parts]\n"
        "OK 写出 SetPartsControl Discontinuous=True 的 VBS 草稿。")


class OversetMeshBody(_PartsControlFollowupBody):
    title = "Overset Mesh"
    _vbs_op = "overset_mesh"
    _hint = (
        "[Condition] – [Overset Mesh]\n"
        "OK 写出 SetPartsControl Overset=True 的 VBS 草稿。")


class WrappingOctreeParamBody(_PartsControlFollowupBody):
    title = "Wrapping Octree Parameter"
    _vbs_op = "wrap_octree"
    _hint = (
        "[Condition] – [Wrapping Octree Parameter]\n"
        "OK 写出 Wrapping=True + OctParam 占位 VBS（API 待录制锁定）。")


class WrappingParamBody(_PartsControlFollowupBody):
    title = "Wrapping Parameter"
    _vbs_op = "wrap_param"
    _hint = (
        "[Condition] – [Wrapping Parameter]\n"
        "OK 写出 Wrapping 参数占位 VBS。")


class BeginWrappingBody(_PartsControlFollowupBody):
    title = "Begin Wrapping"
    _vbs_op = "begin_wrap"
    _hint = (
        "[Execute] – [Begin Wrapping]\n"
        "OK 写出 NativeBridge/SCTprime 占位 VBS。")


class CancelWrappingBody(_PartsControlFollowupBody):
    title = "Cancel Wrapping"
    _vbs_op = "cancel_wrap"
    _hint = "[Execute] – [Cancel Wrapping] — VBS 草稿。"


class ExecuteWrappingBody(_PartsControlFollowupBody):
    title = "Execute Wrapping"
    _vbs_op = "exec_wrap"
    _hint = (
        "[Execute] – [Execute Wrapping]\n"
        "OK 写出 ExecuteWrapping 占位 VBS（录制未锁定）。")


class RetryWrappingBody(_PartsControlFollowupBody):
    title = "Retry Wrapping"
    _vbs_op = "retry_wrap"
    _hint = "[Execute] – [Retry Wrapping] — VBS 草稿。"


# scFLOWpre [File]–[Import] 文件类型（手册 Scf_pre_File-Import.html）
# data: (kind, Qt filter)
_IMPORT_FILE_TYPES: list[tuple[str, Optional[tuple[str, str]]]] = [
    ("── Part data (CAD) ──", None),
    ("XT Files (*.x_t *.x_b)",
     ("cad", "XT Files (*.x_t *.x_b);;All Files (*)")),
    ("STEP Files (*.step *.stp)",
     ("cad", "STEP Files (*.step *.stp);;All Files (*)")),
    ("CATIA V6 Files (*.3dxml)",
     ("cad", "CATIA V6 Files (*.3dxml);;All Files (*)")),
    ("CATIA V5 Files (*.CATPart *.CATProduct)",
     ("cad", "CATIA V5 Files (*.CATPart *.CATProduct);;All Files (*)")),
    ("CATIA V4 Files (*.model *.session)",
     ("cad", "CATIA V4 Files (*.model *.session);;All Files (*)")),
    ("CREO Files (*.prt* *.asm*)",
     ("cad", "CREO Files (*.prt* *.asm*);;All Files (*)")),
    ("SOLIDWORKS Files (*.sldprt *.sldasm)",
     ("cad", "SOLIDWORKS Files (*.sldprt *.sldasm);;All Files (*)")),
    ("NX Files (*.prt)",
     ("cad", "NX Files (*.prt);;All Files (*)")),
    ("SOLIDEDGE Files (*.par *.asm *.psm)",
     ("cad", "SOLIDEDGE Files (*.par *.asm *.psm);;All Files (*)")),
    ("INVENTOR Files (*.ipt *.iam)",
     ("cad", "INVENTOR Files (*.ipt *.iam);;All Files (*)")),
    ("Rhino Files (*.3dm)",
     ("cad", "Rhino Files (*.3dm);;All Files (*)")),
    ("IGES Files (*.igs *.iges)",
     ("cad", "IGES Files (*.igs *.iges);;All Files (*)")),
    ("JT Files (*.jt)",
     ("cad", "JT Files (*.jt);;All Files (*)")),
    ("VDAFS Files (*.vda)",
     ("cad", "VDAFS Files (*.vda);;All Files (*)")),
    ("ACIS Files (*.sat)",
     ("cad", "ACIS Files (*.sat);;All Files (*)")),
    ("IFC Files (*.ifc)",
     ("cad", "IFC Files (*.ifc);;All Files (*)")),
    ("── Part data (Patch) ──", None),
    ("DXF Files (*.dxf)",
     ("patch", "DXF Files (*.dxf);;All Files (*)")),
    ("NASTRAN Files (Model) (*.nas *.bdf)",
     ("patch", "NASTRAN Files (*.nas *.bdf);;All Files (*)")),
    ("STL Files (*.stl)",
     ("patch", "STL Files (*.stl);;All Files (*)")),
    ("MDL Files (*.mdl)",
     ("patch", "MDL Files (*.mdl);;All Files (*)")),
    ("── Octree data ──", None),
    ("OCT Files (*.oct)",
     ("oct", "OCT Files (*.oct);;All Files (*)")),
    ("── Mesh data ──", None),
    ("GPH Files (*.gph)",
     ("gph", "GPH Files (*.gph);;All Files (*)")),
    ("PRE Files (*.pre)",
     ("gph", "PRE Files (*.pre);;All Files (*)")),
    ("CGNS Files (*.cgns)",
     ("gph", "CGNS Files (*.cgns);;All Files (*)")),
    ("── Display information ──", None),
    ("VIEW Files (*.view)",
     ("view", "VIEW Files (*.view);;All Files (*)")),
    ("── Material property data ──", None),
    ("PRP Files (*.prp)",
     ("prp", "PRP Files (*.prp);;All Files (*)")),
    ("── Analysis condition ──", None),
    ("XML Files (*.xml)",
     ("xml", "XML Files (*.xml);;All Files (*)")),
]


class ImportPartBody(_Body):
    """[File] – [Import Part File]（对齐 scFLOWpre Open + CAD Data Import）。"""

    title = "Import Part File"
    min_size = (560, 560)
    dialog_buttons = QDialogButtonBox.Open | QDialogButtonBox.Cancel

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 8)
        v.setSpacing(8)

        intro = QLabel("Select a type of file to load.")
        v.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.cb_type = QComboBox()
        for label, data in _IMPORT_FILE_TYPES:
            idx = self.cb_type.count()
            self.cb_type.addItem(label, data)
            if data is None:
                item = self.cb_type.model().item(idx)
                if item is not None:
                    item.setEnabled(False)
        # 默认 XT
        for i in range(self.cb_type.count()):
            d = self.cb_type.itemData(i)
            if d and d[0] == "cad" and "XT" in self.cb_type.itemText(i):
                self.cb_type.setCurrentIndex(i)
                break
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("*.x_t")
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.ed_path, 1)
        row.addWidget(btn)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("Files of type", self.cb_type)
        form.addRow("File name", wrap)
        v.addLayout(form)

        tip = QLabel(
            "Items under Part data (CAD) other than XT/STEP may require "
            "Datakit, MSC CAD Translator, or scFLOW Extension Option "
            "(CAD Data Exchange) before import.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(tip)

        # ── CAD Data Import（Project Configuration 同款控件）──────────
        cad_box = QGroupBox("CAD Data Import")
        cad_v = QVBoxLayout(cad_box)

        type_box = QGroupBox("CAD data import type")
        type_v = QVBoxLayout(type_box)
        self.rb_solid = QRadioButton("Import as solid")
        self.rb_facet = QRadioButton("Import as facet")
        self._type_grp = QButtonGroup(self)
        self._type_grp.addButton(self.rb_solid)
        self._type_grp.addButton(self.rb_facet)
        self.rb_solid.setChecked(True)
        type_v.addWidget(self.rb_solid)

        lib_box = QGroupBox("CAD data conversion library")
        lib_v = QVBoxLayout(lib_box)
        self.rb_lib_ext = QRadioButton(
            "scFLOW Extension Option (CAD Data Exchange)")
        self.rb_lib_dk = QRadioButton("Datakit")
        self.rb_lib_msc = QRadioButton("MSC CAD Translator")
        self._lib_grp = QButtonGroup(self)
        self._lib_grp.addButton(self.rb_lib_ext)
        self._lib_grp.addButton(self.rb_lib_dk)
        self._lib_grp.addButton(self.rb_lib_msc)
        self.rb_lib_dk.setChecked(True)
        lib_v.addWidget(self.rb_lib_ext)
        lib_v.addWidget(self.rb_lib_dk)
        lib_v.addWidget(self.rb_lib_msc)
        # 缩进：库选项从属于 Import as solid
        lib_wrap = QHBoxLayout()
        lib_wrap.addSpacing(18)
        lib_wrap.addWidget(lib_box, 1)
        type_v.addLayout(lib_wrap)

        self.chk_ignore_color = QCheckBox(
            "Ignore face colors in Parasolid while loading")
        self.chk_ignore_name = QCheckBox(
            "Ignore face names in Parasolid while loading")
        self.chk_use_lib_step = QCheckBox(
            "Use CAD data conversion library for loading STEP files")
        type_v.addWidget(self.chk_ignore_color)
        type_v.addWidget(self.chk_ignore_name)
        type_v.addWidget(self.chk_use_lib_step)
        type_v.addWidget(self.rb_facet)
        cad_v.addWidget(type_box)

        self.chk_dk_ver = QCheckBox("Specify datakit version")
        dk_row = QHBoxLayout()
        dk_row.addWidget(QLabel("Datakit version"))
        self.sp_dk_ver = QSpinBox()
        self.sp_dk_ver.setRange(2015, 2035)
        self.sp_dk_ver.setValue(2025)
        dk_row.addWidget(self.sp_dk_ver)
        dk_row.addStretch(1)
        cad_v.addWidget(self.chk_dk_ver)
        cad_v.addLayout(dk_row)

        # 手册截图未展示、但 xenv 仍有的项
        adv = QGroupBox("Additional options")
        adv_f = QFormLayout(adv)
        self.chk_ancestral = QCheckBox("Use ancestral name for unnamed parts")
        self.chk_sep_dup = QCheckBox("Separate duplicate solid")
        adv_f.addRow(self.chk_ancestral)
        adv_f.addRow(self.chk_sep_dup)
        cad_v.addWidget(adv)

        v.addWidget(cad_box, 1)

        self.rb_solid.toggled.connect(self._sync_cad_enabled)
        self.chk_dk_ver.toggled.connect(self._sync_cad_enabled)
        self._sync_cad_enabled()

    def _sync_cad_enabled(self, *_args) -> None:
        solid = self.rb_solid.isChecked()
        for w in (self.rb_lib_ext, self.rb_lib_dk, self.rb_lib_msc,
                  self.chk_ignore_color, self.chk_ignore_name,
                  self.chk_use_lib_step):
            w.setEnabled(solid)
        self.sp_dk_ver.setEnabled(self.chk_dk_ver.isChecked())

    def _current_filter(self) -> str:
        data = self.cb_type.currentData()
        if data:
            return data[1]
        return "All Files (*)"

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", self.ed_path.text().strip() or "",
            self._current_filter())
        if path:
            self.ed_path.setText(path)
            # 按扩展名自动对齐 Files of type
            import os
            suf = os.path.splitext(path)[1].lower()
            for i in range(self.cb_type.count()):
                data = self.cb_type.itemData(i)
                if not data:
                    continue
                filt = data[1].lower()
                if suf and suf in filt:
                    self.cb_type.setCurrentIndex(i)
                    break

    def load(self, ctx: dict) -> None:
        xenv = ctx.get("xenv")
        if xenv:
            itype = (xenv.get("CAD", "CAD_Import_TYPE", "0") or "0").strip()
            self.rb_solid.setChecked(itype != "1")
            self.rb_facet.setChecked(itype == "1")
            lib = (xenv.get("CAD", "CAD_LIBRARY", "1") or "1").strip()
            self.rb_lib_ext.setChecked(lib == "0")
            self.rb_lib_dk.setChecked(lib == "1")
            self.rb_lib_msc.setChecked(lib == "2")
            # DELETE_COLORED_CAD_FACE true → ignore colors
            self.chk_ignore_color.setChecked(
                _xenv_bool(xenv, "CAD", "DELETE_COLORED_CAD_FACE", True))
            self.chk_ignore_name.setChecked(
                _xenv_bool(xenv, "CAD", "IGNORE_CAD_FACE_NAME", True))
            # USE_STEP_ASSISTANT true → 未勾选 “Use CAD library for STEP”
            self.chk_use_lib_step.setChecked(
                not _xenv_bool(xenv, "CAD", "USE_STEP_ASSISTANT", True))
            self.chk_dk_ver.setChecked(
                _xenv_bool(xenv, "CAD", "SELECT_DKCT_VERSION", False))
            try:
                self.sp_dk_ver.setValue(
                    int(float(xenv.get("CAD", "DKCT_VERSION", "2025") or 2025)))
            except (TypeError, ValueError):
                self.sp_dk_ver.setValue(2025)
            self.chk_ancestral.setChecked(
                _xenv_bool(xenv, "CAD", "USE_ANCESTRAL_NAME", False))
            self.chk_sep_dup.setChecked(
                _xenv_bool(xenv, "CAD", "SEPARATE_DUPLICATE_SOLID", False))
        sess = ctx.setdefault("session", {}).setdefault("import_part", {})
        if sess.get("path"):
            self.ed_path.setText(sess["path"])
        if sess.get("filter_label"):
            i = self.cb_type.findText(sess["filter_label"])
            if i >= 0:
                self.cb_type.setCurrentIndex(i)
        elif sess.get("type"):
            for i in range(self.cb_type.count()):
                data = self.cb_type.itemData(i)
                if data and data[0] == sess["type"]:
                    self.cb_type.setCurrentIndex(i)
                    break
        self._sync_cad_enabled()

    def apply(self, ctx: dict) -> bool:
        data = self.cb_type.currentData()
        kind = data[0] if data else "cad"
        path = self.ed_path.text().strip()
        ctx.setdefault("session", {})["import_part"] = {
            "type": kind,
            "path": path,
            "filter_label": self.cb_type.currentText(),
            "open_requested": bool(path),
        }
        xenv = ctx.get("xenv")
        if xenv:
            pphxml.set_xenv_value(
                xenv, "CAD", "CAD_Import_TYPE",
                "1" if self.rb_facet.isChecked() else "0")
            if self.rb_lib_ext.isChecked():
                lib = "0"
            elif self.rb_lib_msc.isChecked():
                lib = "2"
            else:
                lib = "1"
            pphxml.set_xenv_value(xenv, "CAD", "CAD_LIBRARY", lib)
            pphxml.set_xenv_value(
                xenv, "CAD", "DELETE_COLORED_CAD_FACE",
                "true" if self.chk_ignore_color.isChecked() else "false")
            pphxml.set_xenv_value(
                xenv, "CAD", "IGNORE_CAD_FACE_NAME",
                "true" if self.chk_ignore_name.isChecked() else "false")
            # 勾选 Use library for STEP → USE_STEP_ASSISTANT = false
            pphxml.set_xenv_value(
                xenv, "CAD", "USE_STEP_ASSISTANT",
                "false" if self.chk_use_lib_step.isChecked() else "true")
            pphxml.set_xenv_value(
                xenv, "CAD", "SELECT_DKCT_VERSION",
                "true" if self.chk_dk_ver.isChecked() else "false")
            pphxml.set_xenv_value(
                xenv, "CAD", "DKCT_VERSION", str(self.sp_dk_ver.value()))
            pphxml.set_xenv_value(
                xenv, "CAD", "USE_ANCESTRAL_NAME",
                "true" if self.chk_ancestral.isChecked() else "false")
            pphxml.set_xenv_value(
                xenv, "CAD", "SEPARATE_DUPLICATE_SOLID",
                "true" if self.chk_sep_dup.isChecked() else "false")
            ctx["xenv_dirty"] = True
        return True


def _xenv_bool(xenv, section: str, key: str, default: bool) -> bool:
    val = (xenv.get(section, key, "") or "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes", "on")


def _xyz_spins(val: float = 0.0, lo: float = -1e9, hi: float = 1e9,
               dec: int = 6) -> dict[str, QDoubleSpinBox]:
    return {a: _spin_f(dec, lo, hi, val) for a in "xyz"}


def _add_xyz_headers(grid: QGridLayout, row: int, col0: int = 1) -> None:
    for i, ax in enumerate("XYZ"):
        lab = QLabel(ax)
        lab.setAlignment(Qt.AlignCenter)
        grid.addWidget(lab, row, col0 + i)


def _add_xyz_row(grid: QGridLayout, row: int, label: str,
                 spins: dict[str, QDoubleSpinBox], col0: int = 1) -> None:
    grid.addWidget(QLabel(label), row, 0)
    for i, ax in enumerate("xyz"):
        grid.addWidget(spins[ax], row, col0 + i)


class CreatePartsBody(_Body):
    """[Edit] – [Create Parts]（对齐 scFLOWpre：Cuboid/Cylinder/Sphere/Rectangle）。"""

    title = "Create Parts"
    min_size = (500, 620)
    dialog_buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._shapes: dict[str, dict] = {}
        self._unit_labs: list[QLabel] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 4)
        v.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_cuboid(), "Cuboid")
        self.tabs.addTab(self._make_cylinder(), "Cylinder")
        self.tabs.addTab(self._make_sphere(), "Sphere")
        self.tabs.addTab(self._make_rect(), "Rectangle")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        v.addWidget(self.tabs, 1)

        foot = QHBoxLayout()
        self.chk_fluid = QCheckBox("Register as fluid region")
        foot.addWidget(self.chk_fluid)
        foot.addStretch(1)
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.clicked.connect(self._on_preview)
        foot.addWidget(self.btn_preview)
        v.addLayout(foot)

        self.lab = QLabel()
        self.lab.setWordWrap(True)
        self.lab.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(self.lab)

    def _unit_label(self) -> QLabel:
        lab = QLabel("Unit : m")
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._unit_labs.append(lab)
        return lab

    def _make_cuboid(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        box = QGroupBox("Size of cuboid")
        g = QGridLayout(box)
        g.addWidget(self._unit_label(), 0, 1, 1, 3)
        name = QLineEdit("Cuboid")
        g.addWidget(QLabel("Part name"), 1, 0)
        g.addWidget(name, 1, 1, 1, 3)
        _add_xyz_headers(g, 2)
        pos = _xyz_spins(0.0)
        size = _xyz_spins(1.0, lo=0.0)
        _add_xyz_row(g, 3, "Position", pos)
        _add_xyz_row(g, 4, "Size", size)
        btn = QPushButton("Calculate Size from Selected Parts")
        btn.clicked.connect(lambda: self._calc_size("Cuboid"))
        g.addWidget(btn, 5, 0, 1, 4)
        ext = QCheckBox("Extend surroundings")
        g.addWidget(ext, 6, 0, 1, 4)
        _add_xyz_headers(g, 7)
        min_side = _xyz_spins(0.0, lo=0.0)
        max_side = _xyz_spins(0.0, lo=0.0)
        _add_xyz_row(g, 8, "Minimum side", min_side)
        _add_xyz_row(g, 9, "Maximum side", max_side)
        outer.addWidget(box)
        outer.addStretch(1)

        def _sync(on: bool) -> None:
            for sp in (*min_side.values(), *max_side.values()):
                sp.setEnabled(on)

        ext.toggled.connect(_sync)
        _sync(False)
        self._shapes["Cuboid"] = {
            "name": name, "pos": pos, "size": size, "ext": ext,
            "min_side": min_side, "max_side": max_side,
        }
        return w

    def _make_cylinder(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        box = QGroupBox("Size of cylinder")
        g = QGridLayout(box)
        g.addWidget(self._unit_label(), 0, 1, 1, 3)
        name = QLineEdit("Cylinder")
        g.addWidget(QLabel("Part name"), 1, 0)
        g.addWidget(name, 1, 1, 1, 3)
        _add_xyz_headers(g, 2)
        bot = _xyz_spins(0.0)
        _add_xyz_row(g, 3, "Bottom center", bot)
        h = _spin_f(6, 0, 1e9, 1.0)
        r = _spin_f(6, 0, 1e9, 1.0)
        direc = QComboBox()
        direc.addItems(["X direction", "Y direction", "Z direction"])
        direc.setCurrentText("Z direction")
        g.addWidget(QLabel("Height"), 4, 0)
        g.addWidget(h, 4, 3)
        g.addWidget(QLabel("Radius"), 5, 0)
        g.addWidget(r, 5, 3)
        g.addWidget(QLabel("Direction"), 6, 0)
        g.addWidget(direc, 6, 3)
        btn = QPushButton("Calculate Size from Selected Parts")
        btn.clicked.connect(lambda: self._calc_size("Cylinder"))
        g.addWidget(btn, 7, 0, 1, 4)
        outer.addWidget(box)
        outer.addStretch(1)
        self._shapes["Cylinder"] = {
            "name": name, "bot": bot, "h": h, "r": r, "dir": direc,
        }
        return w

    def _make_sphere(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        box = QGroupBox("Size of sphere")
        g = QGridLayout(box)
        g.addWidget(self._unit_label(), 0, 1, 1, 3)
        name = QLineEdit("Sphere")
        g.addWidget(QLabel("Part name"), 1, 0)
        g.addWidget(name, 1, 1, 1, 3)
        _add_xyz_headers(g, 2)
        c = _xyz_spins(0.0)
        _add_xyz_row(g, 3, "Center of sphere", c)
        r = _spin_f(6, 0, 1e9, 1.0)
        g.addWidget(QLabel("Radius"), 4, 0)
        g.addWidget(r, 4, 3)
        btn = QPushButton("Calculate Size from Selected Parts")
        btn.clicked.connect(lambda: self._calc_size("Sphere"))
        g.addWidget(btn, 5, 0, 1, 4)
        seam = QCheckBox("Add seam line")
        g.addWidget(seam, 6, 0, 1, 4)
        outer.addWidget(box)
        outer.addStretch(1)
        self._shapes["Sphere"] = {"name": name, "c": c, "r": r, "seam": seam}
        return w

    def _make_rect(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        box = QGroupBox("Size of rectangle")
        g = QGridLayout(box)
        g.addWidget(self._unit_label(), 0, 1, 1, 3)
        name = QLineEdit("Rectangle")
        g.addWidget(QLabel("Part name"), 1, 0)
        g.addWidget(name, 1, 1, 1, 3)
        axis = QComboBox()
        axis.addItems(["X axis", "Y axis", "Z axis"])
        g.addWidget(QLabel("Perpendicular to axis"), 2, 0)
        g.addWidget(axis, 2, 1, 1, 3)
        _add_xyz_headers(g, 3)
        pos = _xyz_spins(0.0)
        size = _xyz_spins(1.0, lo=0.0)
        _add_xyz_row(g, 4, "Position", pos)
        _add_xyz_row(g, 5, "Size", size)
        btn = QPushButton("Calculate Size from Selected Parts")
        btn.clicked.connect(lambda: self._calc_size("Rectangle"))
        g.addWidget(btn, 6, 0, 1, 4)
        ext = QCheckBox("Extend surroundings")
        g.addWidget(ext, 7, 0, 1, 4)
        _add_xyz_headers(g, 8)
        min_side = _xyz_spins(0.0, lo=0.0)
        max_side = _xyz_spins(0.0, lo=0.0)
        _add_xyz_row(g, 9, "Minimum side", min_side)
        _add_xyz_row(g, 10, "Maximum side", max_side)
        test = QCheckBox("Create as a test section")
        g.addWidget(test, 11, 0, 1, 4, Qt.AlignRight)
        outer.addWidget(box)
        outer.addStretch(1)

        def _sync_ext(on: bool) -> None:
            ax = axis.currentIndex()  # 0=X,1=Y,2=Z
            for i, a in enumerate("xyz"):
                en = on and i != ax
                min_side[a].setEnabled(en)
                max_side[a].setEnabled(en)

        def _sync_axis(_i: int = 0) -> None:
            ax = axis.currentIndex()
            for i, a in enumerate("xyz"):
                size[a].setEnabled(i != ax)
            _sync_ext(ext.isChecked())

        ext.toggled.connect(_sync_ext)
        axis.currentIndexChanged.connect(_sync_axis)
        _sync_axis()
        self._shapes["Rectangle"] = {
            "name": name, "axis": axis, "pos": pos, "size": size,
            "ext": ext, "min_side": min_side, "max_side": max_side,
            "test": test,
        }
        return w

    def _on_tab_changed(self, idx: int) -> None:
        # Rectangle 不可注册为流体（手册）
        is_rect = self.tabs.tabText(idx) == "Rectangle"
        if is_rect:
            self.chk_fluid.setChecked(False)
        self.chk_fluid.setEnabled(not is_rect)

    def _set_unit(self, ctx: dict) -> None:
        unit = "m"
        xenv = ctx.get("xenv")
        if xenv is not None:
            unit = (xenv.get("UNIT", "MODEL_LENGTH_UNIT", "m") or "m").strip() or "m"
        text = f"Unit : {unit}"
        for lab in self._unit_labs:
            lab.setText(text)

    def _calc_size(self, shape: str) -> None:
        lo, hi = _model_bounds_from_ctx(self._ctx)
        size = [hi[i] - lo[i] for i in range(3)]
        d = self._shapes[shape]
        if shape == "Cuboid":
            for i, a in enumerate("xyz"):
                d["pos"][a].setValue(lo[i])
                d["size"][a].setValue(max(size[i], 0.0))
        elif shape == "Cylinder":
            axis = d["dir"].currentIndex()  # 0=X,1=Y,2=Z
            for i, a in enumerate("xyz"):
                d["bot"][a].setValue(lo[i] if i == axis else (lo[i] + hi[i]) * 0.5)
            d["h"].setValue(max(size[axis], 0.0))
            rads = [size[i] * 0.5 for i in range(3) if i != axis]
            d["r"].setValue(max(rads) if rads else 0.0)
        elif shape == "Sphere":
            for i, a in enumerate("xyz"):
                d["c"][a].setValue((lo[i] + hi[i]) * 0.5)
            d["r"].setValue(max(size) * 0.5)
        else:
            ax = d["axis"].currentIndex()
            for i, a in enumerate("xyz"):
                if i == ax:
                    d["pos"][a].setValue((lo[i] + hi[i]) * 0.5)
                    d["size"][a].setValue(0.0)
                else:
                    d["pos"][a].setValue(lo[i])
                    d["size"][a].setValue(max(size[i], 0.0))

    def _on_preview(self) -> None:
        shape = self.tabs.tabText(self.tabs.currentIndex())
        d = self._shapes[shape]
        name = d["name"].text().strip() or shape
        QMessageBox.information(
            self, "Preview",
            f"Preview “{name}” ({shape}).\n"
            "本查看器仅保存参数；几何预览请在 scFLOWpre 中执行。")

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        self._set_unit(ctx)
        draft = ctx.setdefault("session", {}).get("create_parts") or {}
        shape = draft.get("shape", "Cuboid")
        idx = {"Cuboid": 0, "Cylinder": 1, "Sphere": 2, "Rectangle": 3}.get(
            shape, 0)
        self.tabs.setCurrentIndex(idx)
        self.chk_fluid.setChecked(bool(draft.get("fluid")))
        self._on_tab_changed(idx)

        def _set_xyz(spins, vals, default=0.0):
            if not vals:
                return
            for i, a in enumerate("xyz"):
                try:
                    spins[a].setValue(float(vals[i]))
                except (TypeError, ValueError, IndexError):
                    spins[a].setValue(default)

        if shape in self._shapes and draft.get("name"):
            d = self._shapes[shape]
            d["name"].setText(str(draft["name"]))
            if shape == "Cuboid":
                _set_xyz(d["pos"], draft.get("position"))
                _set_xyz(d["size"], draft.get("size"), 1.0)
                d["ext"].setChecked(bool(draft.get("extend")))
                _set_xyz(d["min_side"], draft.get("min_side"))
                _set_xyz(d["max_side"], draft.get("max_side"))
            elif shape == "Cylinder":
                _set_xyz(d["bot"], draft.get("bottom"))
                if draft.get("height") is not None:
                    d["h"].setValue(float(draft["height"]))
                if draft.get("radius") is not None:
                    d["r"].setValue(float(draft["radius"]))
                if draft.get("direction"):
                    i = d["dir"].findText(str(draft["direction"]))
                    if i >= 0:
                        d["dir"].setCurrentIndex(i)
            elif shape == "Sphere":
                _set_xyz(d["c"], draft.get("center"))
                if draft.get("radius") is not None:
                    d["r"].setValue(float(draft["radius"]))
                d["seam"].setChecked(bool(draft.get("seam")))
            else:
                if draft.get("axis"):
                    i = d["axis"].findText(str(draft["axis"]))
                    if i >= 0:
                        d["axis"].setCurrentIndex(i)
                _set_xyz(d["pos"], draft.get("position"))
                _set_xyz(d["size"], draft.get("size"), 1.0)
                d["ext"].setChecked(bool(draft.get("extend")))
                _set_xyz(d["min_side"], draft.get("min_side"))
                _set_xyz(d["max_side"], draft.get("max_side"))
                d["test"].setChecked(bool(
                    draft.get("test_section", draft.get("cross_section"))))

        names = []
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                for p in parts.iter("part"):
                    n = p.findtext("name")
                    if n:
                        names.append(n)
        self.lab.setText(
            "Existing parts: " + (", ".join(names) if names else "(none)")
            + "\n参数可保存；实体创建需在 scFLOWpre 中执行。")

    def apply(self, ctx: dict) -> bool:
        shape = self.tabs.tabText(self.tabs.currentIndex())
        d = self._shapes[shape]
        name = d["name"].text().strip()
        if not name:
            QMessageBox.information(self, self.title, "Part name is required.")
            return False
        # 与已有 part 重名时仅警告（查看器不写实体）
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                for p in parts.iter("part"):
                    if (p.findtext("name") or "").strip() == name:
                        QMessageBox.information(
                            self, self.title,
                            f"Part name “{name}” already exists.")
                        return False
        fluid = self.chk_fluid.isChecked() and shape != "Rectangle"
        data: dict = {"shape": shape, "fluid": fluid, "name": name}
        if shape == "Cuboid":
            data.update({
                "position": tuple(d["pos"][a].value() for a in "xyz"),
                "size": tuple(d["size"][a].value() for a in "xyz"),
                "extend": d["ext"].isChecked(),
                "min_side": tuple(d["min_side"][a].value() for a in "xyz"),
                "max_side": tuple(d["max_side"][a].value() for a in "xyz"),
            })
        elif shape == "Cylinder":
            data.update({
                "bottom": tuple(d["bot"][a].value() for a in "xyz"),
                "height": d["h"].value(), "radius": d["r"].value(),
                "direction": d["dir"].currentText(),
            })
        elif shape == "Sphere":
            data.update({
                "center": tuple(d["c"][a].value() for a in "xyz"),
                "radius": d["r"].value(), "seam": d["seam"].isChecked(),
            })
        else:
            data.update({
                "axis": d["axis"].currentText(),
                "position": tuple(d["pos"][a].value() for a in "xyz"),
                "size": tuple(d["size"][a].value() for a in "xyz"),
                "extend": d["ext"].isChecked(),
                "min_side": tuple(d["min_side"][a].value() for a in "xyz"),
                "max_side": tuple(d["max_side"][a].value() for a in "xyz"),
                "test_section": d["test"].isChecked(),
            })
        ctx.setdefault("session", {})["create_parts"] = data
        ctx.setdefault("session", {})["pending_vbs"] = {
            "op": "create_parts",
            "label": f"Create {shape}",
            "draft": data,
        }
        return True


# scFLOWpre [Edit]–[Modify Parts]：页签 → 功能列表
# fields: key, label, icon png, short desc, select label, extras
# 图标几何取手册 PNG，线形/配色按主界面 AppIcons 重映射（见 _modify_op_icon）
# extras: "tol" | "thickness" | "priority" | "scale" | "translate" | "rotate"
_MODIFY_ICON_DIR = (
    r"C:\Program Files\Cradle\CradleCFD2025.2\Manuals\scFLOW"
    r"\HTML\Pre_eng\image"
)

def _mop(key, label, icon, desc, select, *extras):
    return {
        "key": key, "label": label, "icon": icon, "desc": desc,
        "select": select, "extras": frozenset(extras),
    }


_MODIFY_PARTS_TABS: list[tuple[str, list[dict]]] = [
    ("Data Cleaning", [
        _mop("remove_redundant_edges", "Remove Redundant Edges",
             "Scf_pre_Edit-Modify_Parts_2_e.png",
             "Remove redundant edges from specified solid.",
             "Solid to remove redundant edges from"),
        _mop("line_up_faces", "Line Up Faces Perpendicular to X,Y,Z",
             "Scf_pre_Edit-Modify_Parts_6_e.png",
             "Detect and repair small differences between faces "
             "perpendicular to X, Y or Z axis.",
             "Parts to align", "tol"),
        _mop("remove_tiny_edges", "Remove Tiny Edges",
             "Scf_pre_Edit-Modify_Parts_9_e.png",
             "Detect and remove tiny edges formed with planes.",
             "Parts which include tiny edges", "tol"),
        _mop("remove_close_faces", "Remove Close Faces",
             "Scf_pre_Edit-Modify_Parts_12_e.png",
             "Find and repair gaps between bodies smaller than tolerance.",
             "Solids to repair", "tol"),
        _mop("remove_close_similar", "Remove Close and Similar Faces",
             "Scf_pre_Edit-Modify_Parts_15_e.png",
             "Find and repair misalignments between bodies smaller "
             "than tolerance.",
             "Solids to repair", "tol"),
        _mop("simplify_face", "Simplify Face Geometry",
             "Scf_pre_Edit-Modify_Parts_18_e.png",
             "Simplify internal representation of face geometry.",
             "Solids to simplify"),
        _mop("rejoin_faces", "Rejoin Faces",
             "Scf_pre_Edit-Modify_Parts_19_e.png",
             "Separate solids/sheets and reconstruct by suitable "
             "edge tolerances.",
             "Solid or sheet"),
        _mop("closed_sheet_to_solid", "Closed Sheet to Solid",
             "Scf_pre_Edit-Modify_Parts_20_e.png",
             "Convert a closed sheet body (no isolated edges) to a solid.",
             "Sheets to convert"),
    ]),
    ("Edit Solid", [
        _mop("unite_solids", "Unite Solids",
             "Scf_pre_Edit-Modify_Parts_21_e.png",
             "Unite two or more solid bodies.",
             "Parts to be united"),
        _mop("remove_solid_overlap", "Remove Solid Overlap",
             "Scf_pre_Edit-Modify_Parts_24_e.png",
             "Remove overlapping volumes with specified priorities.",
             "Overlapping parts", "priority"),
        _mop("delete_faces", "Delete Faces",
             "Scf_pre_Edit-Modify_Parts_27_e.png",
             "Delete faces of solids and sheets.",
             "Parts (mark faces in Draw)"),
        _mop("offset_solid", "Offset Solid",
             "Scf_pre_Edit-Modify_Parts_30_e.png",
             "Offset all faces to inflate the solid.",
             "Solids to offset", "thickness"),
        _mop("offset_face_solid", "Offset Face",
             "Scf_pre_Edit-Modify_Parts_33_e.png",
             "Offset faces of a solid body.",
             "Parts (mark faces in Draw)", "thickness"),
        _mop("thicken_face_solid", "Thicken Face",
             "Scf_pre_Edit-Modify_Parts_36_e.png",
             "Thicken faces of a solid body.",
             "Parts (mark faces in Draw)", "thickness"),
        _mop("remove_patterns", "Recognize and Remove Patterns",
             "Scf_pre_Edit-Modify_Parts_39_e.png",
             "Find and remove bosses, holes, and fillets.",
             "Solid bodies"),
        _mop("merge_vertices", "Merge Vertices of Edge",
             "Scf_pre_Edit-Modify_Parts_42_e.png",
             "Simplify a part by collapsing a tiny-gap edge.",
             "Parts (mark edge in Draw)"),
        _mop("boundary_edges_solids", "Create Boundary Edges of Solids",
             "Scf_pre_Edit-Modify_Parts_45_e.png",
             "Create edges/faces from intersections of overlapped bodies.",
             "Bodies to create boundaries"),
        _mop("boundary_edges_groups",
             "Create Boundary Edges between Solids or Sheets",
             "Scf_pre_Edit-Modify_Parts_48_e.png",
             "Create boundary edges between groups of bodies.",
             "Parts in groups"),
        _mop("project_edge", "Project Edge to Solid",
             "Scf_pre_Edit-Modify_Parts_49_e.png",
             "Imprint specified edges onto another part.",
             "Target part"),
        _mop("trim_face", "Trim Face",
             "Scf_pre_Edit-Modify_Parts_52_e.png",
             "Simplify parts by trimming fillets / convexity / concavity.",
             "Parts (mark faces in Draw)"),
        _mop("trim_inside_loop", "Trim Inside Loop",
             "Scf_pre_Edit-Modify_Parts_55_e.png",
             "Trim faces surrounded by marked faces.",
             "Parts (mark faces in Draw)"),
        _mop("unify_surfaces", "Unify Surfaces",
             "Scf_pre_Edit-Modify_Parts_58_e.png",
             "Unify surfaces of different faces onto a destination face.",
             "Parts (mark faces in Draw)"),
        _mop("move_surface", "Move Surface to Point",
             "Scf_pre_Edit-Modify_Parts_61_e.png",
             "Move surfaces of faces to a specified point.",
             "Parts (mark faces in Draw)"),
    ]),
    ("Edit Sheet", [
        _mop("offset_sheet", "Offset Sheet",
             "Scf_pre_Edit-Modify_Parts_64_e.png",
             "Offset entire sheet body by specified thickness.",
             "Sheet body", "thickness"),
        _mop("offset_face_sheet", "Offset Face",
             "Scf_pre_Edit-Modify_Parts_67_e.png",
             "Offset faces of a sheet body by specified thickness.",
             "Sheet (mark faces in Draw)", "thickness"),
        _mop("thicken_face_sheet", "Thicken Face",
             "Scf_pre_Edit-Modify_Parts_70_e.png",
             "Create solid by thickening specified sheet faces.",
             "Sheet (mark faces in Draw)", "thickness"),
        _mop("symmetrize_sheet", "Symmetrize Sheet",
             "Scf_pre_Edit-Modify_Parts_73_e.png",
             "Supplement sheet as symmetric about X/Y/Z plane.",
             "Sheet body"),
        _mop("fill_sheet", "Fill Sheet",
             "Scf_pre_Edit-Modify_Parts_78_e.png",
             "Fill holes of an unclosed sheet automatically.",
             "Sheet body"),
        _mop("sew_sheet", "Sew Sheet",
             "Scf_pre_Edit-Modify_Parts_81_e.png",
             "Sew multiple sheet bodies with tolerances.",
             "Sheet bodies", "tol"),
        _mop("merge_closed_edges", "Merge Closed Edges",
             "Scf_pre_Edit-Modify_Parts_82_e.png",
             "Sew isolated edges of sheet bodies with tolerance.",
             "Sheet bodies", "tol"),
        _mop("merge_common_edges", "Merge Common Edges",
             "Scf_pre_Edit-Modify_Parts_83_e.png",
             "Sew isolated edges; create vertices near other edges.",
             "Sheet bodies", "tol"),
        _mop("merge_isolated_edges", "Merge Isolated Edges",
             "Scf_pre_Edit-Modify_Parts_84_e.png",
             "Sew isolated edges and rejoin with original sheets.",
             "Sheet bodies", "tol"),
        _mop("merge_marked_edges", "Merge Marked Edges",
             "Scf_pre_Edit-Modify_Parts_85_e.png",
             "Merge two marked edges of sheets.",
             "Sheet (mark edges in Draw)"),
    ]),
    ("Cross Section and Extraction", [
        _mop("cross_section_sheet", "Cross Section (Sheet)",
             "Scf_pre_Edit-Modify_Parts_88_e.png",
             "Create sheet assembly by cross-section of solids.",
             "Parts to section"),
        _mop("cross_section_solid", "Cross Section (Solid)",
             "Scf_pre_Edit-Modify_Parts_91_e.png",
             "Create solid assembly by cross-section of solids.",
             "Parts to section"),
        _mop("create_cover", "Create Cover",
             "Scf_pre_Edit-Modify_Parts_94_e.png",
             "Create solids that cover specified faces.",
             "Parts (mark faces in Draw)", "thickness"),
        _mop("extract_empty", "Extract Empty Region of Solid",
             "Scf_pre_Edit-Modify_Parts_97_e.png",
             "Create solids from inner empty regions.",
             "Solid"),
        _mop("sheet_from_edges", "Create Sheet from Edges",
             "Scf_pre_Edit-Modify_Parts_100_e.png",
             "Create a sheet by connecting marked edges.",
             "Parts (mark edges in Draw)"),
        _mop("face_to_sheet", "Face to Sheet",
             "Scf_pre_Edit-Modify_Parts_103_e.png",
             "Copy specified faces as a sheet.",
             "Parts (mark faces in Draw)"),
        _mop("disjoint_face", "Disjoint Face",
             "Scf_pre_Edit-Modify_Parts_106_e.png",
             "Separate specified faces from solids and sheets.",
             "Parts (mark faces in Draw)"),
        _mop("bounding_box", "Create Bounding Box (Arbitrary Direction)",
             "Scf_pre_Edit-Modify_Parts_109_e.png",
             "Create a cube body surrounding specified parts.",
             "Parts to surround"),
        _mop("bounding_cyl", "Create Bounding Cylinder (Arbitrary Direction)",
             "Scf_pre_Edit-Modify_Parts_112_e.png",
             "Create a cylinder body surrounding specified parts.",
             "Parts to surround"),
        _mop("untrim_face", "Untrim Face",
             "Scf_pre_Edit-Modify_Parts_115_e.png",
             "Expand the surface of a specified face to a sheet.",
             "Parts (mark face in Draw)"),
    ]),
    ("Transform", [
        _mop("scale_copy", "Scale Parts and Copy",
             "Scf_pre_Edit-Modify_Parts_118_e.png",
             "Scale specified parts about a center (optionally copy).",
             "Parts to scale", "scale"),
        _mop("translate_copy", "Translate Parts and Copy",
             "Scf_pre_Edit-Modify_Parts_121_e.png",
             "Translate specified parts by a distance (optionally copy).",
             "Parts to translate", "translate"),
        _mop("rotate_copy", "Rotate by Angle and Copy",
             "Scf_pre_Edit-Modify_Parts_124_e.png",
             "Rotate specified parts by axis and angle (optionally copy).",
             "Parts to rotate", "rotate"),
    ]),
    ("Turbo machinery", [
        _mop("extract_pitch", "Extract single pitch shape",
             "Scf_pre_Edit-Modify_Parts_127_e.png",
             "Extract a single-pitch blade from a periodic centrifugal pump.",
             "Part of centrifugal pump"),
    ]),
]


def _lerp_color(c0: QColor, c1: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c0.red() + (c1.red() - c0.red()) * t),
        int(c0.green() + (c1.green() - c0.green()) * t),
        int(c0.blue() + (c1.blue() - c0.blue()) * t),
        int(c0.alpha() + (c1.alpha() - c0.alpha()) * t),
    )


def _restyle_modify_pixmap(src: QPixmap) -> QPixmap:
    """保留 scFLOWpre 图标几何，线色/填色改为主界面 AppIcons 风格。"""
    img = src.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    out = QImage(w, h, QImage.Format_ARGB32)
    out.fill(Qt.transparent)

    # AppIcons 色板：描边偏蓝、填充浅蓝阶；薄片绿→紫；灰箭头→青灰
    stroke = QColor("#1565c0")
    fill_hi = QColor("#e3f2fd")
    fill_mid = QColor("#90caf9")
    fill_lo = QColor("#42a5f5")
    sheet_stroke = QColor("#6a1b9a")
    sheet_hi = QColor("#f3e5f5")
    sheet_mid = QColor("#ce93d8")
    sheet_lo = QColor("#ab47bc")
    gray_hi = QColor("#eceff1")
    gray_mid = QColor("#90a4ae")
    gray_lo = QColor("#546e7a")
    accent = QColor("#00838f")

    for y in range(h):
        for x in range(w):
            c = QColor.fromRgba(img.pixel(x, y))
            a = c.alpha()
            if a < 24:
                continue
            r, g, b = c.red(), c.green(), c.blue()
            # 手册白底 → 透明
            if r >= 248 and g >= 248 and b >= 248:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            sat = (mx - mn) / mx if mx else 0.0
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

            # 近黑描边 → 主界面圆角描边色（略提亮，避免死黑）
            if lum < 0.22 and sat < 0.35:
                nc = QColor(stroke)
                nc.setAlpha(a)
            elif sat < 0.12:
                # 灰色箭头 / 辅助线
                if lum > 0.85:
                    nc = QColor(gray_hi)
                elif lum > 0.45:
                    nc = _lerp_color(gray_lo, gray_mid, (lum - 0.45) / 0.4)
                else:
                    nc = QColor(gray_lo)
                nc.setAlpha(a)
            elif g > r + 12 and g >= b:
                # 绿色薄片族 → AppIcons octree/sheet 紫
                if lum > 0.75:
                    nc = QColor(sheet_hi)
                elif lum > 0.45:
                    nc = _lerp_color(sheet_lo, sheet_mid, (lum - 0.45) / 0.3)
                else:
                    nc = _lerp_color(sheet_stroke, sheet_lo, lum / 0.45)
                nc.setAlpha(a)
            elif b > r + 20 and b > g + 10:
                # 已有蓝色系：压到 AppIcons 蓝阶
                if lum > 0.7:
                    nc = QColor(fill_hi)
                elif lum > 0.4:
                    nc = QColor(fill_mid)
                else:
                    nc = QColor(fill_lo)
                nc.setAlpha(a)
            elif r > b + 8:
                # 橙/棕/米黄实体族 → part 蓝阶（按明度分面）
                if lum > 0.78:
                    nc = QColor(fill_hi)
                elif lum > 0.55:
                    nc = _lerp_color(fill_mid, fill_hi, (lum - 0.55) / 0.23)
                elif lum > 0.32:
                    nc = _lerp_color(fill_lo, fill_mid, (lum - 0.32) / 0.23)
                else:
                    nc = _lerp_color(stroke, fill_lo, lum / 0.32)
                nc.setAlpha(a)
            else:
                nc = _lerp_color(accent, fill_mid, lum)
                nc.setAlpha(a)

            out.setPixel(x, y, nc.rgba())

    return QPixmap.fromImage(out)


def _modify_op_fallback_icon(size: int = 16) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(1, size // 10)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    pen = QPen(QColor("#1565c0"))
    pen.setWidthF(1.3)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(QBrush(QColor("#90caf9")))
    p.drawRoundedRect(r, 3, 3)
    p.end()
    return QIcon(pm)


def _modify_op_icon(filename: str, size: int = 16) -> QIcon:
    """scFLOWpre 示意几何 + 主界面线形/配色；列表尺寸 16（非手册 32）。"""
    import os
    path = os.path.join(_MODIFY_ICON_DIR, filename)
    if not os.path.isfile(path):
        return _modify_op_fallback_icon(size)
    src = QPixmap(path)
    if src.isNull():
        return _modify_op_fallback_icon(size)
    styled = _restyle_modify_pixmap(src)
    # 先平滑缩到目标尺寸，再轻描边软化像素感
    scaled = styled.scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    # 居中到正方形画布
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    ox = (size - scaled.width()) // 2
    oy = (size - scaled.height()) // 2
    p.drawPixmap(ox, oy, scaled)
    p.end()
    return QIcon(canvas)


class _ModifyOpPanel(QWidget):
    """单个 Modify Parts 功能的右侧参数区。"""

    def __init__(self, op: dict, parent=None):
        super().__init__(parent)
        self.op = op
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)

        desc_box = QGroupBox("Description")
        dv = QVBoxLayout(desc_box)
        lab = QLabel(op["desc"])
        lab.setWordWrap(True)
        dv.addWidget(lab)
        v.addWidget(desc_box)

        v.addWidget(QLabel(op["select"]))
        self.lst = QListWidget()
        self.lst.setSelectionMode(QListWidget.ExtendedSelection)
        v.addWidget(self.lst, 1)

        extras = op["extras"]
        self.sp_tol = None
        self.sp_thick = None
        self.btn_up = self.btn_down = None
        self.scale = self.dist = self.angle = None
        self.center = None
        self.axis = None

        form = QFormLayout()
        if "tol" in extras:
            self.sp_tol = _spin_f(12, 0, 1, 1e-6)
            form.addRow("Tolerance", self.sp_tol)
        if "thickness" in extras:
            self.sp_thick = _spin_f(6, -1e6, 1e6, 0.001)
            form.addRow("Thickness", self.sp_thick)
        if "priority" in extras:
            row = QHBoxLayout()
            self.btn_up = QPushButton("Up")
            self.btn_down = QPushButton("Down")
            self.btn_up.clicked.connect(lambda: self._move_sel(-1))
            self.btn_down.clicked.connect(lambda: self._move_sel(1))
            row.addWidget(self.btn_up)
            row.addWidget(self.btn_down)
            row.addStretch(1)
            form.addRow("Priority", row)
        if "scale" in extras:
            self.center = _xyz_spins(0.0)
            self.scale = _xyz_spins(1.0, lo=1e-9)
            cg = QGridLayout()
            _add_xyz_headers(cg, 0)
            _add_xyz_row(cg, 1, "Center", self.center)
            _add_xyz_row(cg, 2, "Scale", self.scale)
            form.addRow(cg)
        if "translate" in extras:
            self.dist = _xyz_spins(0.0)
            cg = QGridLayout()
            _add_xyz_headers(cg, 0)
            _add_xyz_row(cg, 1, "Distance", self.dist)
            form.addRow(cg)
        if "rotate" in extras:
            self.center = _xyz_spins(0.0)
            self.axis = QComboBox()
            self.axis.addItems(["X direction", "Y direction", "Z direction"])
            self.angle = _spin_f(3, -3600, 3600, 90.0)
            cg = QGridLayout()
            _add_xyz_headers(cg, 0)
            _add_xyz_row(cg, 1, "Center", self.center)
            form.addRow(cg)
            form.addRow("Direction of rotation axis", self.axis)
            form.addRow("Angle [deg]", self.angle)
        if form.rowCount():
            v.addLayout(form)

    def _move_sel(self, delta: int) -> None:
        row = self.lst.currentRow()
        if row < 0:
            return
        new = row + delta
        if new < 0 or new >= self.lst.count():
            return
        item = self.lst.takeItem(row)
        self.lst.insertItem(new, item)
        self.lst.setCurrentRow(new)

    def set_parts(self, names: list[str]) -> None:
        sel = {i.text() for i in self.lst.selectedItems()}
        order = [self.lst.item(i).text() for i in range(self.lst.count())]
        self.lst.clear()
        # 保持已有顺序优先，再追加新名
        seen = set()
        for n in order + names:
            if n in seen or n not in names:
                continue
            seen.add(n)
            self.lst.addItem(n)
        for i in range(self.lst.count()):
            if self.lst.item(i).text() in sel:
                self.lst.item(i).setSelected(True)

    def selected_parts(self) -> list[str]:
        # priority 模式用列表顺序；否则用选中项
        if "priority" in self.op["extras"]:
            return [self.lst.item(i).text() for i in range(self.lst.count())]
        items = self.lst.selectedItems()
        if items:
            return [i.text() for i in items]
        return [self.lst.item(i).text() for i in range(self.lst.count())]

    def params(self) -> dict:
        out: dict = {}
        if self.sp_tol is not None:
            out["tolerance"] = self.sp_tol.value()
        if self.sp_thick is not None:
            out["thickness"] = self.sp_thick.value()
        if self.scale is not None:
            out["center"] = tuple(self.center[a].value() for a in "xyz")
            out["scale"] = tuple(self.scale[a].value() for a in "xyz")
        if self.dist is not None:
            out["distance"] = tuple(self.dist[a].value() for a in "xyz")
        if self.angle is not None:
            out["center"] = tuple(self.center[a].value() for a in "xyz")
            out["axis"] = self.axis.currentText()
            out["angle"] = self.angle.value()
        return out


class ModifyPartsBody(_Body):
    """[Edit] – [Modify Parts]（对齐 scFLOWpre：五/六页签 + 功能列表 + Execute）。"""

    title = "Modify Parts"
    min_size = (780, 540)
    dialog_buttons = QDialogButtonBox.Close

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._lists: list[QListWidget] = []
        self._stacks: list[QStackedWidget] = []
        self._panels: dict[str, _ModifyOpPanel] = {}
        self._tab_ops: list[list[dict]] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 4)
        v.setSpacing(6)

        self.tabs = QTabWidget()
        for tab_name, ops in _MODIFY_PARTS_TABS:
            self._tab_ops.append(ops)
            page = QWidget()
            h = QHBoxLayout(page)
            h.setContentsMargins(4, 4, 4, 4)
            lst = QListWidget()
            lst.setIconSize(QSize(16, 16))  # 与主界面 Navigation / Tree 一致
            lst.setMinimumWidth(220)
            lst.setMaximumWidth(280)
            stack = QStackedWidget()
            for op in ops:
                item = QListWidgetItem(
                    _modify_op_icon(op["icon"], 16), op["label"])
                item.setData(Qt.UserRole, op["key"])
                item.setToolTip(op["desc"])
                lst.addItem(item)
                panel = _ModifyOpPanel(op)
                stack.addWidget(panel)
                self._panels[op["key"]] = panel
            lst.currentRowChanged.connect(stack.setCurrentIndex)
            if ops:
                lst.setCurrentRow(0)
            h.addWidget(lst)
            h.addWidget(stack, 1)
            self._lists.append(lst)
            self._stacks.append(stack)
            self.tabs.addTab(page, tab_name)
        v.addWidget(self.tabs, 1)

        # 工程级容差（xenv），折叠在底部以免干扰主 UI
        tol_box = QGroupBox("Project tolerances (main.xenv)")
        tol_box.setCheckable(True)
        tol_box.setChecked(False)
        tol_f = QFormLayout(tol_box)
        self.sp = {}
        for key, label, dec in (
            ("OVERLAP_TOLERANCE", "Overlap", 12),
            ("SEWING_TOLERANCE", "Sewing", 12),
            ("INVALID_TOLERANCE", "Invalid", 12),
            ("CONTACT_TOLERANCE", "Contact", 12),
            ("MATCHING_TOLERANCE_FACTOR", "Matching factor", 6),
            ("SHORT_DISTANCE_PARAM", "Short distance", 12),
        ):
            sp = _spin_f(dec, 0, 10 if "FACTOR" in key else 1, 0)
            tol_f.addRow(label, sp)
            self.sp[key] = sp
        self.tiny_rel = _bool_combo()
        self.tiny_den = _spin_f(0, 1, 1e9, 1000)
        self.tiny_abs = _spin_f(12, 0, 1, 1e-6)
        self.ridge_ang = _spin_f(2, 0, 180, 45)
        tol_f.addRow("Tiny relative flag", self.tiny_rel)
        tol_f.addRow("Tiny relative denom.", self.tiny_den)
        tol_f.addRow("Tiny absolute size", self.tiny_abs)
        tol_f.addRow("Ridge angle (deg)", self.ridge_ang)
        v.addWidget(tol_box)
        self._tol_box = tol_box

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.chk_preview = QCheckBox("Preview")
        self.chk_overlay = QCheckBox("Overlay")
        self.btn_exec = QPushButton("Execute")
        self.btn_exec.setMinimumWidth(100)
        self.btn_exec.clicked.connect(self._on_execute)
        foot.addWidget(self.chk_preview)
        foot.addWidget(self.chk_overlay)
        foot.addWidget(self.btn_exec)
        v.addLayout(foot)

    def _current_op(self) -> Optional[dict]:
        ti = self.tabs.currentIndex()
        if ti < 0 or ti >= len(self._lists):
            return None
        row = self._lists[ti].currentRow()
        if row < 0 or row >= len(self._tab_ops[ti]):
            return None
        return self._tab_ops[ti][row]

    def _on_execute(self) -> None:
        op = self._current_op()
        if op is None:
            return
        panel = self._panels[op["key"]]
        parts = panel.selected_parts()
        self.apply(self._ctx)
        sess = self._ctx.setdefault("session", {}).setdefault("modify_parts", {})
        sess.update({
            "tab": self.tabs.tabText(self.tabs.currentIndex()),
            "op": op["key"],
            "op_label": op["label"],
            "parts": parts,
            "params": panel.params(),
            "preview": self.chk_preview.isChecked(),
            "overlay": self.chk_overlay.isChecked(),
            "execute_requested": True,
        })
        QMessageBox.information(
            self, "Execute",
            f"已记录 [{op['label']}]"
            + (f"\nParts: {', '.join(parts)}" if parts else "")
            + "\n\n几何编辑需在 scFLOWpre（Parasolid）中执行。")

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        names: list[str] = []
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                for p in parts.iter("part"):
                    n = (p.findtext("name") or "").strip()
                    if n:
                        names.append(n)
        if not names:
            for g in sorted((ctx.get("groups_info") or {})):
                names.append(g)
        for panel in self._panels.values():
            panel.set_parts(names)

        sess = ctx.setdefault("session", {}).setdefault("modify_parts", {})
        self.chk_preview.setChecked(bool(sess.get("preview")))
        self.chk_overlay.setChecked(bool(sess.get("overlay")))
        op_key = sess.get("op")
        if op_key:
            for ti, ops in enumerate(self._tab_ops):
                for ri, op in enumerate(ops):
                    if op["key"] == op_key:
                        self.tabs.setCurrentIndex(ti)
                        self._lists[ti].setCurrentRow(ri)
                        break

        xenv = ctx.get("xenv")
        if not xenv:
            return
        for k, sp in self.sp.items():
            try:
                sp.setValue(float(xenv.get("TOLERANCE", k, "0") or 0))
            except ValueError:
                pass
        _set_combo_data(
            self.tiny_rel,
            xenv.get("TINYFACE", "RELATIVE_FLAG", "true") or "true")
        try:
            self.tiny_den.setValue(float(
                xenv.get("TINYFACE", "RELATIVE_DENOMINATOR", "1000") or 1000))
            self.tiny_abs.setValue(float(
                xenv.get("TINYFACE", "ABSOLUTE_SIZE", "0") or 0))
            self.ridge_ang.setValue(float(
                xenv.get("RIDGE", "ANGLE", "45") or 45))
        except ValueError:
            pass

    def apply(self, ctx: dict) -> bool:
        op = self._current_op()
        panel = self._panels[op["key"]] if op else None
        data = {
            "tab": self.tabs.tabText(self.tabs.currentIndex())
            if self.tabs.currentIndex() >= 0 else "",
            "op": op["key"] if op else "",
            "op_label": op["label"] if op else "",
            "parts": panel.selected_parts() if panel else [],
            "params": panel.params() if panel else {},
            "preview": self.chk_preview.isChecked(),
            "overlay": self.chk_overlay.isChecked(),
        }
        prev = ctx.setdefault("session", {}).get("modify_parts") or {}
        if prev.get("execute_requested"):
            data["execute_requested"] = True
        ctx.setdefault("session", {})["modify_parts"] = data
        ctx.setdefault("session", {})["pending_vbs"] = {
            "op": "modify_parts",
            "label": data.get("op_label") or "Modify Parts",
            "draft": data,
        }

        xenv = ctx.get("xenv")
        if not xenv:
            return True
        for k, sp in self.sp.items():
            pphxml.set_xenv_value(xenv, "TOLERANCE", k, _fmt_float(sp.value()))
        pphxml.set_xenv_value(
            xenv, "TINYFACE", "RELATIVE_FLAG", self.tiny_rel.currentData())
        pphxml.set_xenv_value(
            xenv, "TINYFACE", "RELATIVE_DENOMINATOR",
            _fmt_float(self.tiny_den.value()))
        pphxml.set_xenv_value(
            xenv, "TINYFACE", "ABSOLUTE_SIZE",
            _fmt_float(self.tiny_abs.value()))
        pphxml.set_xenv_value(
            xenv, "RIDGE", "ANGLE", _fmt_float(self.ridge_ang.value()))
        ctx["xenv_dirty"] = True
        return True


def _mf_combo(items: list[tuple[str, str]]) -> QComboBox:
    cb = QComboBox()
    for label, data in items:
        cb.addItem(label, data)
    cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    return cb


class MesherFaceterBody(_Body):
    """[Condition] – [Mesher/Faceter Setting]（对齐 scFLOWpre 属性树）。

    ``settings_mode=True`` 时用于 [Option]–[Settings]–[Mesher/Faceter]：
    隐藏 Condition 专有 / Voxel Fitting Mesher 页专有行，并嵌套 Element/Octree。
    """

    title = "Mesher/Faceter Setting"
    min_size = (600, 620)
    dialog_buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

    def __init__(self, parent=None, *, settings_mode: bool = False):
        super().__init__(parent)
        self._settings_mode = settings_mode
        self._items: dict[str, QTreeWidgetItem] = {}
        self._editors: dict[str, QWidget] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 4)
        v.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Meshing unit"))
        self.cb_unit = QComboBox()
        self.cb_unit.setEnabled(False)
        self.cb_unit.setMinimumWidth(180)
        top.addWidget(self.cb_unit)
        top.addStretch(1)
        v.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Parameter", "Value", "Unit"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 220)
        self.tree.setColumnWidth(2, 40)
        v.addWidget(self.tree, 1)

        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet(
            "border:1px solid #bbb; background:#fafafa; padding:6px;")
        self.help.setMinimumHeight(48)
        v.addWidget(self.help)

        self._build_tree()
        for key in ("mesher", "surf", "mdl", "faceter", "acc_type",
                    "val_type", "simple"):
            w = self._editors.get(key)
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._sync_visibility)
        self._sync_visibility()

    def _add_branch(self, parent, key: str, label: str) -> QTreeWidgetItem:
        it = QTreeWidgetItem(parent if parent is not None else self.tree,
                             [label, "", ""])
        font = it.font(0)
        font.setBold(True)
        it.setFont(0, font)
        it.setExpanded(True)
        self._items[key] = it
        return it

    def _add_row(self, parent, key: str, label: str, editor: QWidget,
                 unit: str = "", *, branch: bool = False) -> QTreeWidgetItem:
        it = QTreeWidgetItem(parent if parent is not None else self.tree,
                             [label, "", unit])
        if branch:
            font = it.font(0)
            font.setBold(True)
            it.setFont(0, font)
        self.tree.setItemWidget(it, 1, editor)
        self._items[key] = it
        self._editors[key] = editor
        it.setExpanded(True)
        return it

    def _build_tree(self) -> None:
        # Mesher
        self.cb_mesher = _mf_combo([
            ("Polyhedral mesher", "0"),
            ("Voxel fitting mesher", "1"),
        ])
        mesher = self._add_row(None, "mesher", "Mesher", self.cb_mesher,
                               branch=True)

        self.cb_surf = _mf_combo([
            ("Facet-based surface mesher", "0"),
            ("Solid-based surface mesher", "1"),
        ])
        self._add_row(mesher, "surf", "Surface mesher", self.cb_surf)

        # Solid-based：嵌套 Element size / Octree parameter
        elem = self._add_branch(mesher, "elem", "Element size parameter")
        self.cb_elem_dir = _mf_combo([
            ("Fine side", "0"), ("Coarse side", "1")])
        self.sp_elem_effect = _spin_f(3, 0, 100, 1.0)
        self._add_row(elem, "elem_dir", "Direction of effect",
                      self.cb_elem_dir)
        self._add_row(elem, "elem_range", "Range of effect",
                      self.sp_elem_effect, "-")

        octp = self._add_branch(mesher, "oct_param", "Octree parameter")
        self.sp_oct_ang = _spin_f(3, 0, 180, 5)
        self.sp_oct_reduce = _spin_f(6, 0, 10, 0.25)
        self._add_row(octp, "oct_ang",
                      "Angle precision for the whole model",
                      self.sp_oct_ang, "deg")
        self._add_row(octp, "oct_reduce", "Reduction ratio of edge length",
                      self.sp_oct_reduce, "-")

        # Voxel extras
        self.cb_oct_include = _mf_combo([
            ("Include", "true"), ("Do not include", "false"),
        ])
        self._add_row(mesher, "oct_include",
                      "Inclusion of octree creation process in meshing",
                      self.cb_oct_include)
        vx_acc = self._add_branch(
            mesher, "vx_acc",
            "Facet accuracy for the whole model (relative to default value)")
        self.sp_vx_dist = _spin_f(3, 0, 100, 1)
        self.sp_vx_ang = _spin_f(3, 0, 180, 5)
        self.sp_vx_edge = _spin_f(3, 0, 100, 5)
        self._add_row(vx_acc, "vx_dist", "Precision of distance",
                      self.sp_vx_dist, "-")
        self._add_row(vx_acc, "vx_ang", "Precision of angle",
                      self.sp_vx_ang, "deg")
        self._add_row(vx_acc, "vx_edge", "Maximum edge length",
                      self.sp_vx_edge, "-")
        self.cb_vx_each = _mf_combo([
            ("Do not specify", "false"), ("Specify", "true"),
        ])
        self._add_row(mesher, "vx_each",
                      "Facet accuracy for part and region", self.cb_vx_each)
        # Condition 对话框遗留项；Settings / Voxel Fitting Mesher 页不显示
        self.cb_rough = _mf_combo([
            ("false", "false"), ("true", "true"),
        ])
        self.sp_init = QSpinBox()
        self.sp_init.setRange(0, 2_000_000_000)
        self.sp_init.setValue(15_000_000)
        self._add_row(mesher, "rough", "Use rough poly when voxel meshing",
                      self.cb_rough)
        self._add_row(mesher, "init_div",
                      "Number of initial divisions when voxel meshing",
                      self.sp_init)

        # Method for building analysis model
        self.cb_mdl = _mf_combo([
            ("Analysis Model Wizard", "1"),
            ("SCTpre V12 compatible", "0"),
        ])
        mdl = self._add_row(
            None, "mdl", "Method for building analysis model",
            self.cb_mdl, branch=True)

        self.cb_faceter = _mf_combo([
            ("Parasolid faceter", "false"),
            ("Solid-based faceter", "true"),
        ])
        self._add_row(mdl, "faceter", "Faceter type", self.cb_faceter)

        self.cb_acc_type = _mf_combo([
            ("Specify value", "0"),
            ("Specify octree", "1"),
        ])
        self._add_row(mdl, "acc_type",
                      "Specification type of faceting accuracy",
                      self.cb_acc_type)

        self.cb_val_type = _mf_combo([
            ("Specify relative value to default value", "false"),
            ("Specify absolute value", "true"),
        ])
        self._add_row(mdl, "val_type",
                      "Specification type of value of faceting accuracy",
                      self.cb_val_type)

        self.cb_simple = _mf_combo([
            ("Simple Settings of Faceting Accuracy "
             "(Relative to Default Value)", "true"),
            ("Detailed Settings of Faceting Accuracy (Absolute Value)",
             "false"),
        ])
        self._add_row(mdl, "simple", "Setting type of faceting accuracy",
                      self.cb_simple)

        # Faceting accuracy branch
        acc = QTreeWidgetItem(mdl, ["Faceting accuracy", "", ""])
        font = acc.font(0)
        font.setBold(True)
        acc.setFont(0, font)
        acc.setExpanded(True)
        self._items["acc"] = acc

        self.sp_chord = _spin_f(6, 0, 1e6, 1)
        self.sp_ang = _spin_f(3, 0, 180, 10)
        self.sp_width = _spin_f(6, 0, 1e6, 5)
        self.sp_width_sb = _spin_f(6, 0, 1e6, 5)
        self.sp_chord_abs = _spin_f(12, 0, 1e6, 0)
        self.sp_width_abs = _spin_f(12, 0, 1e6, 0)
        self.sp_sb_ang = _spin_f(3, 0, 180, 10)
        self.sp_sb_len = _spin_f(6, 0, 10, 0.05)
        self.sp_sb_tiny = _spin_f(3, 0, 100, 5)  # %
        self.sp_sb_oct_len = _spin_f(6, 0, 10, 0.25)
        self.sp_sb_oct_ang = _spin_f(3, 0, 180, 5)
        self.sp_d_chord = _spin_f(12, 0, 1e6, 0)
        self.sp_d_chord_ang = _spin_f(3, 0, 180, 10)
        self.sp_d_surf = _spin_f(12, 0, 1e6, 0)
        self.sp_d_surf_ang = _spin_f(3, 0, 180, 10)
        self.sp_d_width = _spin_f(12, 0, 1e6, 0)

        self._add_row(acc, "ps_dist", "Precision of distance",
                      self.sp_chord, "-")
        self._add_row(acc, "ps_ang", "Precision of angle",
                      self.sp_ang, "deg")
        self._add_row(acc, "ps_edge", "Maximum edge length",
                      self.sp_width, "-")
        self._add_row(acc, "ps_dist_abs", "Precision of distance (absolute)",
                      self.sp_chord_abs)
        self._add_row(acc, "ps_edge_abs", "Maximum edge length (absolute)",
                      self.sp_width_abs)

        self._add_row(acc, "sb_ang", "Lower limit of angular precision",
                      self.sp_sb_ang, "deg")
        self._add_row(acc, "sb_len", "Reduction ratio of edge length",
                      self.sp_sb_len, "-")
        self._add_row(acc, "sb_edge",
                      "Maximum edge length (relative to default value)",
                      self.sp_width_sb, "-")
        self._add_row(acc, "sb_tiny",
                      "Reference value for the automatic removal of tiny faces",
                      self.sp_sb_tiny, "%")
        self._add_row(acc, "sb_oct_len",
                      "Reduction ratio of edge length (for octree)",
                      self.sp_sb_oct_len, "-")
        self._add_row(acc, "sb_oct_ang",
                      "Angle precision for the whole model (for octree)",
                      self.sp_sb_oct_ang, "deg")

        self._add_row(acc, "d_width", "Maximum edge length",
                      self.sp_d_width)
        self._add_row(acc, "d_chord", "Maximum chordal divergence from curve",
                      self.sp_d_chord)
        self._add_row(acc, "d_chord_ang",
                      "Maximum angular divergence from curve",
                      self.sp_d_chord_ang, "deg")
        self._add_row(acc, "d_surf", "Maximum distance from surface",
                      self.sp_d_surf)
        self._add_row(acc, "d_surf_ang",
                      "Maximum angular divergence from surface",
                      self.sp_d_surf_ang, "deg")

        self.tree.expandAll()

    def _is_poly(self) -> bool:
        return self.cb_mesher.currentData() == "0"

    def _is_facet_surf(self) -> bool:
        return self.cb_surf.currentData() == "0"

    def _is_solid_surf(self) -> bool:
        return self.cb_surf.currentData() == "1"

    def _is_wizard(self) -> bool:
        return self.cb_mdl.currentData() == "1"

    def _is_af(self) -> bool:
        return self.cb_faceter.currentData() == "true"

    def _is_rel(self) -> bool:
        return self.cb_val_type.currentData() == "false"

    def _is_simple(self) -> bool:
        return self.cb_simple.currentData() == "true"

    def _hide(self, *keys: str, show: bool = False) -> None:
        for k in keys:
            it = self._items.get(k)
            if it is not None:
                it.setHidden(not show)

    def _sync_visibility(self, *_args) -> None:
        poly = self._is_poly()
        facet_surf = self._is_facet_surf()
        solid_surf = self._is_solid_surf()
        wizard = self._is_wizard()
        af = self._is_af()
        rel = self._is_rel()
        simple = self._is_simple()
        acc_val = self.cb_acc_type.currentData() == "0"

        # under Mesher
        self._hide("surf", show=poly)
        self._hide("elem", "elem_dir", "elem_range",
                   "oct_param", "oct_ang", "oct_reduce",
                   show=poly and solid_surf)
        self._hide("oct_include", "vx_acc", "vx_dist", "vx_ang", "vx_edge",
                   show=not poly)
        # Condition 专有：part/region；Voxel 页专有：rough / init
        show_cond_voxel = (not poly) and (not self._settings_mode)
        self._hide("vx_each", show=show_cond_voxel)
        self._hide("rough", "init_div", show=show_cond_voxel)

        # Method for BAM：仅 Polyhedral + Facet-based
        show_mdl = poly and facet_surf
        self._hide("mdl", show=show_mdl)
        if show_mdl:
            self._items["mdl"].setHidden(False)
        self._hide("faceter", "acc_type", "val_type",
                   show=show_mdl and wizard)
        self._hide("simple", show=show_mdl and not wizard)
        self._hide("acc", show=show_mdl)

        # accuracy children
        show_ps = show_mdl and (
            (wizard and not af) or (not wizard and simple))
        show_sb = show_mdl and wizard and af and acc_val
        show_sb_oct = show_mdl and wizard and af and not acc_val
        show_detail = show_mdl and (not wizard) and (not simple)

        self._hide("ps_dist", "ps_ang", "ps_edge",
                   show=show_ps and rel)
        self._hide("ps_dist_abs", "ps_edge_abs",
                   show=show_ps and (not rel))
        # angle always for parasolid-like
        if show_ps and not rel:
            self._hide("ps_ang", show=True)

        self._hide("sb_ang", "sb_len", "sb_edge", "sb_tiny",
                   show=show_sb)
        self._hide("sb_oct_len", "sb_oct_ang", show=show_sb_oct)
        self._hide("d_width", "d_chord", "d_chord_ang", "d_surf", "d_surf_ang",
                   show=show_detail)

        # help
        if not poly:
            self.help.setText(
                "Voxel fitting mesher generates hex-dominant polyhedron mesh "
                "directly from parts (no separate BAM / surface mesh).")
        elif solid_surf:
            self.help.setText(
                "When [Solid-based surface mesher] is selected, the analysis "
                "model is built with the solid-based faceter in the surface "
                "mesh generation process.")
        elif wizard and af:
            self.help.setText(
                "Solid-based faceter: set angular precision, edge-length "
                "reduction ratio, and maximum edge length for faceting "
                "during Build Analysis Model.")
        else:
            self.help.setText(
                "Set the type of mesher and faceter. Parameters correspond to "
                "[Option] – [Settings] – [Project Configuration] – "
                "[Mesher/Faceter].")

    def load(self, ctx: dict) -> None:
        groups = sorted((ctx.get("groups_info") or {}) or [])
        self.cb_unit.blockSignals(True)
        self.cb_unit.clear()
        if groups:
            for g in groups:
                self.cb_unit.addItem(g)
            self.cb_unit.setEnabled(len(groups) > 1)
        else:
            self.cb_unit.addItem("(default)")
            self.cb_unit.setEnabled(False)
        self.cb_unit.blockSignals(False)

        xenv = ctx.get("xenv")
        if not xenv:
            self._sync_visibility()
            return

        def _f(sec, key, default):
            try:
                return float(xenv.get(sec, key, default) or default)
            except ValueError:
                return float(default)

        def _i(sec, key, default):
            try:
                return int(float(xenv.get(sec, key, default) or default))
            except ValueError:
                return int(default)

        _set_combo_data(self.cb_mesher, xenv.get("MESH", "MESHER", "0") or "0")
        _set_combo_data(self.cb_surf,
                        xenv.get("MESH", "SURF_MESHER", "0") or "0")
        _set_combo_data(self.cb_mdl,
                        xenv.get("FACET", "MDL_METHOD", "1") or "1")
        use_af = xenv.get("FACET", "USE_FACETTER", "true") or "true"
        _set_combo_data(self.cb_faceter, use_af.lower())
        _set_combo_data(
            self.cb_acc_type,
            xenv.get("FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0") or "0")
        abs_flag = xenv.get("FACET", "USE_ABSOLUTE_VALUE", "false") or "false"
        _set_combo_data(self.cb_val_type, abs_flag.lower())
        _set_combo_data(
            self.cb_simple,
            xenv.get("FACET", "USE_SIMPLE_SETTING", "true") or "true")

        self.sp_chord.setValue(_f("FACET", "SIMPLE_CHORD_TOLERANCE", 1))
        self.sp_ang.setValue(_f("FACET", "SIMPLE_MAX_ANGLE", 10))
        w = _f("FACET", "SIMPLE_MAX_WIDTH", 5)
        self.sp_width.setValue(w)
        self.sp_width_sb.setValue(w)
        self.sp_chord_abs.setValue(_f("FACET", "SIMPLE_CHORD_TOLERANCE_ABS", 0))
        self.sp_width_abs.setValue(_f("FACET", "SIMPLE_MAX_WIDTH_ABS", 0))
        self.sp_sb_ang.setValue(_f("FACET", "SOLID_BASE_MINIMUM_ANGLE", 10))
        self.sp_sb_len.setValue(_f("FACET", "SOLID_BASE_LENGTH_FACTOR", 0.05))
        tiny = _f("FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", 0.05)
        self.sp_sb_tiny.setValue(tiny * 100.0 if tiny <= 1.0 else tiny)
        self.sp_sb_oct_len.setValue(
            _f("FACET", "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE", 0.25))
        self.sp_sb_oct_ang.setValue(
            _f("FACET", "SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE", 5))
        self.sp_d_chord.setValue(_f("FACET", "DETAIL_CHORD_TOLERANCE", 0))
        self.sp_d_chord_ang.setValue(_f("FACET", "DETAIL_CHORD_ANGLE", 10))
        self.sp_d_surf.setValue(_f("FACET", "DETAIL_SURF_TOLERANCE", 0))
        self.sp_d_surf_ang.setValue(_f("FACET", "DETAIL_SURF_ANGLE", 10))
        self.sp_d_width.setValue(_f("FACET", "DETAIL_MAX_WIDTH", 0))

        self.sp_oct_ang.setValue(_f("OCT_MESH", "FACET_ANGLE", 5))
        self.sp_oct_reduce.setValue(_f("OCT_MESH", "FACET_LENGTH_FACTOR", 0.25))
        self.sp_vx_dist.setValue(_f("OCT_MESH", "FACET_LENGTH_FACTOR", 1))
        self.sp_vx_ang.setValue(_f("OCT_MESH", "FACET_ANGLE", 5))
        self.sp_vx_edge.setValue(_f("OCT_MESH", "FACET_MAX_WIDTH_FACTOR", 5))
        _set_combo_data(
            self.cb_vx_each,
            (xenv.get("OCT_MESH", "FACET_SPECIFY_EACH_REGION", "false")
             or "false").lower())
        # COMPLETE_PARALLEL ~ include octree parallel path
        _set_combo_data(
            self.cb_oct_include,
            (xenv.get("OCT_MESH", "COMPLETE_PARALLEL", "false")
             or "false").lower())
        _set_combo_data(
            self.cb_rough,
            (xenv.get("MESH_COMMON", "USE_ROUGH_POLY_WHEN_VOXEL_MESHING",
                      "false") or "false").lower())
        self.sp_init.setValue(_i(
            "MESH_COMMON", "NUMBER_OF_INITIAL_DIVISION_WHEN_VOXEL_MESHING",
            15_000_000))
        self._sync_visibility()

    def apply(self, ctx: dict) -> bool:
        xenv = ctx.get("xenv")
        if not xenv:
            return False
        pphxml.set_xenv_value(
            xenv, "MESH", "MESHER", self.cb_mesher.currentData())
        pphxml.set_xenv_value(
            xenv, "MESH", "SURF_MESHER", self.cb_surf.currentData())
        pphxml.set_xenv_value(
            xenv, "FACET", "MDL_METHOD", self.cb_mdl.currentData())
        pphxml.set_xenv_value(
            xenv, "FACET", "USE_FACETTER", self.cb_faceter.currentData())
        pphxml.set_xenv_value(
            xenv, "FACET", "FACET_ACCURACY_SPECIFY_TYPE",
            self.cb_acc_type.currentData())
        pphxml.set_xenv_value(
            xenv, "FACET", "USE_ABSOLUTE_VALUE",
            self.cb_val_type.currentData())
        pphxml.set_xenv_value(
            xenv, "FACET", "USE_SIMPLE_SETTING",
            self.cb_simple.currentData())

        # 相对最大边长：Solid-based / Parasolid 路径共用 SIMPLE_MAX_WIDTH
        max_edge = (self.sp_width_sb.value()
                    if (self._is_wizard() and self._is_af())
                    else self.sp_width.value())
        pairs = (
            ("SIMPLE_CHORD_TOLERANCE", _fmt_float(self.sp_chord.value())),
            ("SIMPLE_MAX_ANGLE", _fmt_float(self.sp_ang.value())),
            ("SIMPLE_MAX_WIDTH", _fmt_float(max_edge)),
            ("SIMPLE_CHORD_TOLERANCE_ABS",
             _fmt_float(self.sp_chord_abs.value())),
            ("SIMPLE_MAX_WIDTH_ABS", _fmt_float(self.sp_width_abs.value())),
            ("SOLID_BASE_MINIMUM_ANGLE", _fmt_float(self.sp_sb_ang.value())),
            ("SOLID_BASE_LENGTH_FACTOR", _fmt_float(self.sp_sb_len.value())),
            ("SOLID_BASE_TINY_FACE_WIDTH_RATIO",
             _fmt_float(self.sp_sb_tiny.value() / 100.0)),
            ("SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE",
             _fmt_float(self.sp_sb_oct_len.value())),
            ("SOLID_BASE_MINIMUM_ANGLE_FOR_OCTREE",
             _fmt_float(self.sp_sb_oct_ang.value())),
            ("DETAIL_CHORD_TOLERANCE", _fmt_float(self.sp_d_chord.value())),
            ("DETAIL_CHORD_ANGLE", _fmt_float(self.sp_d_chord_ang.value())),
            ("DETAIL_SURF_TOLERANCE", _fmt_float(self.sp_d_surf.value())),
            ("DETAIL_SURF_ANGLE", _fmt_float(self.sp_d_surf_ang.value())),
            ("DETAIL_MAX_WIDTH", _fmt_float(self.sp_d_width.value())),
        )
        for k, val in pairs:
            pphxml.set_xenv_value(xenv, "FACET", k, val)

        pphxml.set_xenv_value(
            xenv, "OCT_MESH", "FACET_ANGLE",
            _fmt_float(self.sp_vx_ang.value() if not self._is_poly()
                       else self.sp_oct_ang.value()))
        pphxml.set_xenv_value(
            xenv, "OCT_MESH", "FACET_LENGTH_FACTOR",
            _fmt_float(self.sp_vx_dist.value() if not self._is_poly()
                       else self.sp_oct_reduce.value()))
        pphxml.set_xenv_value(
            xenv, "OCT_MESH", "FACET_MAX_WIDTH_FACTOR",
            _fmt_float(self.sp_vx_edge.value()))
        pphxml.set_xenv_value(
            xenv, "OCT_MESH", "FACET_SPECIFY_EACH_REGION",
            self.cb_vx_each.currentData())
        pphxml.set_xenv_value(
            xenv, "OCT_MESH", "COMPLETE_PARALLEL",
            self.cb_oct_include.currentData())
        pphxml.set_xenv_value(
            xenv, "MESH_COMMON", "USE_ROUGH_POLY_WHEN_VOXEL_MESHING",
            self.cb_rough.currentData())
        pphxml.set_xenv_value(
            xenv, "MESH_COMMON",
            "NUMBER_OF_INITIAL_DIVISION_WHEN_VOXEL_MESHING",
            str(self.sp_init.value()))
        ctx["xenv_dirty"] = True
        ctx.setdefault("session", {})["mesher_faceter"] = {
            "meshing_unit": self.cb_unit.currentText(),
            "mesher": self.cb_mesher.currentData(),
            "surf_mesher": self.cb_surf.currentData(),
        }
        return True


def _reg_icon(kind: str, size: int = 14) -> QIcon:
    """Register Region 列表图标：面=青菱形，体=绿立方，点=蓝圆。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if kind == "volume":
        p.setBrush(QColor(46, 160, 67))
        p.setPen(QPen(QColor(20, 90, 30), 1))
        p.drawRect(2, 2, size - 5, size - 5)
    elif kind == "point":
        p.setBrush(QColor(70, 130, 220))
        p.setPen(QPen(QColor(30, 70, 140), 1))
        p.drawEllipse(2, 2, size - 4, size - 4)
    else:
        p.setBrush(QColor(100, 180, 230))
        p.setPen(QPen(QColor(40, 90, 140), 1))
        cx = cy = size / 2
        r = size / 2 - 2
        p.drawPolygon(
            QPointF(cx, cy - r), QPointF(cx + r, cy),
            QPointF(cx, cy + r), QPointF(cx - r, cy))
    p.end()
    return QIcon(pm)


def _ensure_regions_cat(xml, cat: str) -> Optional[ET.Element]:
    if xml is None:
        return None
    regs = xml.section("regions")
    if regs is None:
        regs = ET.SubElement(xml.root, "regions")
    node = regs.find(cat)
    if node is None:
        node = ET.SubElement(regs, cat)
    return node


def _part_names_from_ctx(ctx: dict) -> list[str]:
    names: list[str] = []
    xml = ctx.get("xml")
    if xml is not None:
        parts = xml.section("parts")
        if parts is not None:
            for p in parts.iter("part"):
                n = (p.findtext("name") or "").strip()
                if n and n not in names:
                    names.append(n)
    if not names:
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            part = info.get("part")
            if part is None:
                names.append(g)
                continue
            for r in getattr(part, "surface_regions", None) or []:
                pass
            names.append(g)
    return names


class RegisterRegionBody(_Body):
    """[Edit] – [Register Region]（对齐 scFLOWpre：五页签左右分栏）。"""

    title = "Register Region"
    min_size = (780, 640)
    dialog_buttons = QDialogButtonBox.Close

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 4)

        self.tabs = QTabWidget()
        self._surf = self._make_surface_tab()
        self._iface = self._make_interface_tab()
        self._vol = self._make_volume_tab()
        self._fluid = self._make_fluid_tab()
        self._ref = self._make_refpoint_tab()
        self.tabs.addTab(self._surf["page"], "Surface Region")
        self.tabs.addTab(self._iface["page"], "Part Interface Region")
        self.tabs.addTab(self._vol["page"], "Volume Region")
        self.tabs.addTab(self._fluid["page"], "Fluid Region")
        self.tabs.addTab(self._ref["page"], "Reference Point")
        v.addWidget(self.tabs, 1)

    # ── 通用：左 Registered + 右 Register/Edit ─────────────────────
    def _split_page(self, left_title: str, right_title: str = "Register/Edit"):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)
        left = QGroupBox(left_title)
        lv = QVBoxLayout(left)
        tree = QTreeWidget()
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        lv.addWidget(tree, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_rename = QPushButton("Rename...")
        btn_delete = QPushButton("Delete")
        btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_delete)
        lv.addLayout(btn_row)
        right = QGroupBox(right_title)
        rv = QVBoxLayout(right)
        h.addWidget(left, 1)
        h.addWidget(right, 1)
        return {
            "page": page, "tree": tree, "right": rv,
            "btn_rename": btn_rename, "btn_delete": btn_delete,
        }

    def _make_surface_tab(self) -> dict:
        d = self._split_page("Registered region")
        d["tree"].setHeaderLabels(["Region Name", "Type", "Number of Faces"])
        d["tree"].setColumnWidth(0, 140)
        rv = d["right"]
        form = QFormLayout()
        d["cb_target"] = QComboBox()
        for t in (
            "Selected face",
            "Surface between virtual parts",
            "Surface of specified virtual part",
            "Surface between materials",
            "Surface between panel and part",
            "Cross section region",
        ):
            d["cb_target"].addItem(t)
        form.addRow("Target", d["cb_target"])
        d["ed_name"] = QLineEdit("face1")
        form.addRow("Region name", d["ed_name"])
        d["cb_side"] = QComboBox()
        d["cb_side"].addItems(["Both sides", "Front", "Back"])
        form.addRow("Selected face", d["cb_side"])
        rv.addLayout(form)

        d["stack"] = QStackedWidget()
        # 0 Selected face
        w0 = QWidget(); v0 = QVBoxLayout(w0); v0.setContentsMargins(0, 0, 0, 0)
        d["btn_verify_dir"] = QPushButton("Verify Direction")
        d["btn_verify_dir"].setEnabled(False)
        d["btn_verify_loc"] = QPushButton("Verify Location")
        v0.addWidget(d["btn_verify_dir"])
        v0.addWidget(d["btn_verify_loc"])
        d["sel_faces"] = QTreeWidget()
        d["sel_faces"].setHeaderLabels(["Part Name", "Face Number"])
        d["sel_faces"].setRootIsDecorated(False)
        v0.addWidget(d["sel_faces"], 1)
        d["chk_list_faces"] = QCheckBox("List selected faces")
        d["chk_list_faces"].setChecked(True)
        v0.addWidget(d["chk_list_faces"])
        d["stack"].addWidget(w0)
        # 1 between virtual parts
        w1 = QWidget(); f1 = QFormLayout(w1)
        d["cb_vp1"] = QComboBox(); d["cb_vp2"] = QComboBox()
        f1.addRow("Virtual Part 1", d["cb_vp1"])
        f1.addRow("Virtual Part 2", d["cb_vp2"])
        d["stack"].addWidget(w1)
        # 2 surface of virtual part
        w2 = QWidget(); v2 = QVBoxLayout(w2)
        v2.addWidget(QLabel("Virtual Part"))
        d["lst_vp"] = QListWidget()
        v2.addWidget(d["lst_vp"], 1)
        d["stack"].addWidget(w2)
        # 3 materials
        w3 = QWidget(); f3 = QFormLayout(w3)
        d["cb_mat1"] = QComboBox(); d["cb_mat2"] = QComboBox()
        f3.addRow("Material 1", d["cb_mat1"])
        f3.addRow("Material 2", d["cb_mat2"])
        d["stack"].addWidget(w3)
        # 4 panel and part
        w4 = QWidget(); f4 = QFormLayout(w4)
        d["cb_panel"] = QComboBox(); d["cb_panel_part"] = QComboBox()
        f4.addRow("Heat conduction panel", d["cb_panel"])
        f4.addRow("Part", d["cb_panel_part"])
        d["stack"].addWidget(w4)
        # 5 cross section → New/Edit
        w5 = QWidget(); v5 = QVBoxLayout(w5)
        v5.addWidget(_note(
            "Regions defined by a plane or sphere.\n"
            "Click New / Edit to open [Registration of Cross Section Regions]."))
        row = QHBoxLayout()
        d["btn_cs_new"] = QPushButton("New...")
        d["btn_cs_edit"] = QPushButton("Edit...")
        row.addWidget(d["btn_cs_new"]); row.addWidget(d["btn_cs_edit"])
        row.addStretch(1)
        v5.addLayout(row)
        v5.addStretch(1)
        d["stack"].addWidget(w5)
        rv.addWidget(d["stack"], 1)

        d["cb_target"].currentIndexChanged.connect(d["stack"].setCurrentIndex)
        # side row only for face targets
        def _sync_side(i: int) -> None:
            d["cb_side"].setEnabled(i < 5)
        d["cb_target"].currentIndexChanged.connect(_sync_side)

        row_reg = QHBoxLayout()
        row_reg.addStretch(1)
        d["btn_reg"] = QPushButton("Register")
        row_reg.addWidget(d["btn_reg"])
        rv.addLayout(row_reg)

        d["btn_rename"].clicked.connect(lambda: self._rename("face"))
        d["btn_delete"].clicked.connect(lambda: self._delete("face"))
        d["btn_reg"].clicked.connect(self._register_surface)
        d["btn_verify_loc"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Verify Location",
                "Verify Location 在 Draw Window 高亮选中面（需 scFLOWpre）。"))
        d["btn_cs_new"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Cross Section Region",
                "Registration of Cross Section Regions 需在 scFLOWpre 中完成。\n"
                "本查看器可在会话中记录草稿。"))
        d["btn_cs_edit"].clicked.connect(d["btn_cs_new"].click)
        return d

    def _make_interface_tab(self) -> dict:
        d = self._split_page("Registered region")
        d["tree"].setHeaderLabels(["Region Name", "Side", "Parts"])
        d["tree"].setColumnWidth(0, 140)
        rv = d["right"]
        form = QFormLayout()
        d["ed_name"] = QLineEdit("PartInterface1")
        d["cb_side"] = QComboBox()
        d["cb_side"].addItems(["Both sides", "Part1 side", "Part2 side"])
        form.addRow("Region name", d["ed_name"])
        form.addRow("Side", d["cb_side"])
        rv.addLayout(form)
        row = QHBoxLayout()
        box_all = QGroupBox("Parts List")
        va = QVBoxLayout(box_all)
        d["lst_parts"] = QListWidget()
        d["lst_parts"].setSelectionMode(QListWidget.ExtendedSelection)
        va.addWidget(d["lst_parts"])
        mid = QVBoxLayout()
        d["btn_add1"] = QPushButton("Add to Part 1")
        d["btn_add2"] = QPushButton("Add to Part 2")
        d["btn_del1"] = QPushButton("Delete from Part1")
        d["btn_del2"] = QPushButton("Delete from Part2")
        for b in (d["btn_add1"], d["btn_add2"], d["btn_del1"], d["btn_del2"]):
            mid.addWidget(b)
        mid.addStretch(1)
        box1 = QGroupBox("Part 1"); v1 = QVBoxLayout(box1)
        d["lst_p1"] = QListWidget(); v1.addWidget(d["lst_p1"])
        box2 = QGroupBox("Part 2"); v2 = QVBoxLayout(box2)
        d["lst_p2"] = QListWidget(); v2.addWidget(d["lst_p2"])
        row.addWidget(box_all, 1)
        row.addLayout(mid)
        col = QVBoxLayout(); col.addWidget(box1, 1); col.addWidget(box2, 1)
        row.addLayout(col, 1)
        rv.addLayout(row, 1)
        foot = QHBoxLayout()
        d["btn_verify"] = QPushButton("Verify Location")
        d["btn_reg"] = QPushButton("Register")
        foot.addWidget(d["btn_verify"])
        foot.addStretch(1)
        foot.addWidget(d["btn_reg"])
        rv.addLayout(foot)

        def _move(src, dst):
            for it in src.selectedItems():
                texts = [dst.item(i).text() for i in range(dst.count())]
                if it.text() not in texts:
                    dst.addItem(it.text())

        def _rm(lst):
            for it in lst.selectedItems():
                lst.takeItem(lst.row(it))

        d["btn_add1"].clicked.connect(
            lambda: _move(d["lst_parts"], d["lst_p1"]))
        d["btn_add2"].clicked.connect(
            lambda: _move(d["lst_parts"], d["lst_p2"]))
        d["btn_del1"].clicked.connect(lambda: _rm(d["lst_p1"]))
        d["btn_del2"].clicked.connect(lambda: _rm(d["lst_p2"]))
        d["btn_rename"].clicked.connect(lambda: self._rename("iface"))
        d["btn_delete"].clicked.connect(lambda: self._delete("iface"))
        d["btn_reg"].clicked.connect(self._register_interface)
        d["btn_verify"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Verify Location",
                "Part Interface 位置验证需在 Draw Window / scFLOWpre 中执行。"))
        return d

    def _make_volume_tab(self) -> dict:
        d = self._split_page("Registered region")
        d["tree"].setHeaderLabels(["Region Name", "Target", "Number of Parts"])
        d["tree"].setColumnWidth(0, 140)
        rv = d["right"]
        form = QFormLayout()
        d["cb_target"] = QComboBox()
        d["cb_target"].addItems(["Selected part", "Numerical region"])
        form.addRow("Target", d["cb_target"])
        d["ed_name"] = QLineEdit("Volume1")
        form.addRow("Region name", d["ed_name"])
        rv.addLayout(form)
        d["stack"] = QStackedWidget()
        w0 = QWidget(); v0 = QVBoxLayout(w0)
        d["chk_hidden"] = QCheckBox("Including parts not shown")
        v0.addWidget(d["chk_hidden"])
        d["lst_parts"] = QListWidget()
        d["lst_parts"].setSelectionMode(QListWidget.ExtendedSelection)
        v0.addWidget(d["lst_parts"], 1)
        d["stack"].addWidget(w0)
        w1 = QWidget(); v1 = QVBoxLayout(w1)
        v1.addWidget(_note(
            "Plane / Cuboid / Cylinder / Sphere / Combination.\n"
            "Click New / Edit for [Registration of Numerical Regions]."))
        row = QHBoxLayout()
        d["btn_num_new"] = QPushButton("New...")
        d["btn_num_edit"] = QPushButton("Edit...")
        row.addWidget(d["btn_num_new"]); row.addWidget(d["btn_num_edit"])
        row.addStretch(1)
        v1.addLayout(row)
        v1.addStretch(1)
        d["stack"].addWidget(w1)
        rv.addWidget(d["stack"], 1)
        d["cb_target"].currentIndexChanged.connect(d["stack"].setCurrentIndex)
        row_reg = QHBoxLayout()
        row_reg.addStretch(1)
        d["btn_reg"] = QPushButton("Register")
        row_reg.addWidget(d["btn_reg"])
        rv.addLayout(row_reg)
        d["btn_rename"].clicked.connect(lambda: self._rename("volume"))
        d["btn_delete"].clicked.connect(lambda: self._delete("volume"))
        d["btn_reg"].clicked.connect(self._register_volume)
        d["btn_num_new"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Numerical Region",
                "Registration of Numerical Regions 需在 scFLOWpre 中完成。"))
        d["btn_num_edit"].clicked.connect(d["btn_num_new"].click)
        return d

    def _make_fluid_tab(self) -> dict:
        d = self._split_page("Registered region")
        d["tree"].setHeaderLabels(["Region Name", "Property", "Parts"])
        d["tree"].setColumnWidth(0, 140)
        rv = d["right"]
        form = QFormLayout()
        d["ed_name"] = QLineEdit("FluidRegion")
        form.addRow("Region name", d["ed_name"])
        rv.addLayout(form)
        d["chk_hidden"] = QCheckBox("Including parts not shown")
        rv.addWidget(d["chk_hidden"])
        d["lst_parts"] = QListWidget()
        d["lst_parts"].setSelectionMode(QListWidget.ExtendedSelection)
        rv.addWidget(d["lst_parts"], 1)
        tip = QLabel(
            "The void region is automatically registered as the first "
            "fluid region in virtual parts recognition.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px;")
        rv.addWidget(tip)
        row_reg = QHBoxLayout()
        row_reg.addStretch(1)
        d["btn_reg"] = QPushButton("Register")
        row_reg.addWidget(d["btn_reg"])
        rv.addLayout(row_reg)
        d["btn_rename"].clicked.connect(lambda: self._rename("fluid"))
        d["btn_delete"].clicked.connect(lambda: self._delete("fluid"))
        d["btn_reg"].clicked.connect(self._register_fluid)
        return d

    def _make_refpoint_tab(self) -> dict:
        d = self._split_page("Registered reference point", "Register/Edit")
        d["tree"].setHeaderLabels(["Point Name", "Coordinates"])
        d["tree"].setColumnWidth(0, 140)
        # extra Export button
        export = QPushButton("Export to CSV file...")
        # insert before rename in the button row — rebuild footer
        lay = d["tree"].parent().layout()
        # find button row: last layout item
        btn_row = None
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is not None and item.layout() is not None:
                btn_row = item.layout()
        if btn_row is not None:
            btn_row.insertWidget(0, export)
        d["btn_export"] = export

        rv = d["right"]
        form = QFormLayout()
        d["cb_method"] = QComboBox()
        d["cb_method"].addItems([
            "Coordinate value",
            "Batch input (Straight line/Circumference)",
            "CSV file",
        ])
        form.addRow("Input method", d["cb_method"])
        d["ed_name"] = QLineEdit("Point_1")
        form.addRow("Name of reference point", d["ed_name"])
        rv.addLayout(form)
        d["stack"] = QStackedWidget()
        # coordinate
        w0 = QWidget(); v0 = QVBoxLayout(w0)
        box = QGroupBox("Coordinates")
        g = QGridLayout(box)
        d["sp_x"] = _spin_f(6, -1e9, 1e9, 0.0)
        d["sp_y"] = _spin_f(6, -1e9, 1e9, 0.0)
        d["sp_z"] = _spin_f(6, -1e9, 1e9, 0.0)
        for i, (lab, sp) in enumerate(
                (("X", d["sp_x"]), ("Y", d["sp_y"]), ("Z", d["sp_z"]))):
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(sp, i, 1)
            g.addWidget(QLabel("m"), i, 2)
        v0.addWidget(box)
        d["btn_view_center"] = QPushButton("Current view center coordinates")
        v0.addWidget(d["btn_view_center"])
        d["stack"].addWidget(w0)
        # batch
        w1 = QWidget(); v1 = QVBoxLayout(w1)
        v1.addWidget(_note("Batch Registration of Reference Points."))
        d["btn_batch"] = QPushButton("Create...")
        v1.addWidget(d["btn_batch"])
        v1.addStretch(1)
        d["stack"].addWidget(w1)
        # csv
        w2 = QWidget(); f2 = QFormLayout(w2)
        d["ed_csv"] = QLineEdit()
        btn = QPushButton("Refer...")
        row = QHBoxLayout(); row.addWidget(d["ed_csv"], 1); row.addWidget(btn)
        wrap = QWidget(); wrap.setLayout(row)
        f2.addRow("CSV file", wrap)
        d["stack"].addWidget(w2)
        rv.addWidget(d["stack"], 1)
        d["cb_method"].currentIndexChanged.connect(d["stack"].setCurrentIndex)
        foot = QHBoxLayout()
        d["btn_preview"] = QPushButton("Preview")
        d["btn_reg"] = QPushButton("Register")
        foot.addStretch(1)
        foot.addWidget(d["btn_preview"])
        foot.addWidget(d["btn_reg"])
        rv.addLayout(foot)

        d["btn_rename"].clicked.connect(lambda: self._rename("ref"))
        d["btn_delete"].clicked.connect(lambda: self._delete("ref"))
        d["btn_reg"].clicked.connect(self._register_refpoint)
        d["btn_preview"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Preview",
                f"Point ({d['sp_x'].value():g}, {d['sp_y'].value():g}, "
                f"{d['sp_z'].value():g}) — 预览需 Draw Window。"))
        d["btn_view_center"].clicked.connect(self._fill_view_center)
        d["btn_batch"].clicked.connect(
            lambda: QMessageBox.information(
                self, "Batch input",
                "Batch Registration of Reference Points 需在 scFLOWpre 中完成。"))
        btn.clicked.connect(self._browse_csv)
        export.clicked.connect(self._export_ref_csv)
        return d

    # ── 数据填充 ──────────────────────────────────────────────────
    def _fill_parts_lists(self) -> None:
        names = _part_names_from_ctx(self._ctx)
        for lst in (
            self._vol["lst_parts"], self._fluid["lst_parts"],
            self._iface["lst_parts"], self._surf["lst_vp"],
        ):
            if isinstance(lst, QListWidget):
                lst.clear()
                for n in names:
                    lst.addItem(n)
            else:
                lst.clear()
                for n in names:
                    lst.addItem(n)
        for cb in (self._surf["cb_vp1"], self._surf["cb_vp2"],
                   self._surf["cb_panel_part"]):
            cb.clear()
            cb.addItems(names or ["(none)"])
        # materials from fluid properties
        mats = []
        for fr in (self._ctx.get("regions_meta") or {}).get("fluid") or []:
            if isinstance(fr, dict) and fr.get("property"):
                mats.append(fr["property"])
        if not mats:
            mats = ["(material)"]
        for cb in (self._surf["cb_mat1"], self._surf["cb_mat2"],
                   self._surf["cb_panel"]):
            cb.clear()
            cb.addItems(mats)

    def _reload_trees(self) -> None:
        xml = self._ctx.get("xml")
        # Surface
        tw = self._surf["tree"]
        tw.clear()
        if xml is not None:
            regs = xml.section("regions")
            face = regs.find("face") if regs is not None else None
            if face is not None:
                for r in face.findall("region"):
                    name = (r.findtext("name") or "").strip() or "?"
                    typ = (r.findtext("face_region_type") or "Surface region")
                    if typ == "faces":
                        typ = "Surface region"
                    nfaces = 0
                    sface = r.find("sface_num")
                    if sface is not None:
                        for num in sface.findall("num"):
                            try:
                                nfaces += int((num.text or "0").strip() or 0)
                            except ValueError:
                                pass
                    it = QTreeWidgetItem([name, typ, str(nfaces or "-")])
                    it.setIcon(0, _reg_icon("surface"))
                    tw.addTopLevelItem(it)
        # also MDL surface regions as info rows if xml empty
        if tw.topLevelItemCount() == 0:
            for g, info in sorted((self._ctx.get("groups_info") or {}).items()):
                part = info.get("part")
                if part is None:
                    continue
                for r in getattr(part, "surface_regions", None) or []:
                    it = QTreeWidgetItem([
                        getattr(r, "name", str(r)),
                        "MDL surface",
                        str(getattr(r, "index", "-")),
                    ])
                    it.setIcon(0, _reg_icon("surface"))
                    tw.addTopLevelItem(it)

        # Interface — special_face or session
        tw = self._iface["tree"]
        tw.clear()
        sess_if = (self._ctx.get("session") or {}).get("part_interfaces") or []
        for rec in sess_if:
            it = QTreeWidgetItem([
                rec.get("name", "?"),
                rec.get("side", ""),
                ", ".join(rec.get("part1", []) + ["|"] + rec.get("part2", [])),
            ])
            it.setIcon(0, _reg_icon("surface"))
            tw.addTopLevelItem(it)
        if xml is not None:
            regs = xml.section("regions")
            spec = regs.find("special_face") if regs is not None else None
            if spec is not None:
                for r in spec.findall("region"):
                    name = (r.findtext("name") or "").strip()
                    if not name:
                        continue
                    it = QTreeWidgetItem([name, "Part interface", "-"])
                    it.setIcon(0, _reg_icon("surface"))
                    tw.addTopLevelItem(it)

        # Volume
        tw = self._vol["tree"]
        tw.clear()
        if xml is not None:
            regs = xml.section("regions")
            for cat, target in (("volume", "Selected part"),
                                ("numerical", "Numerical region")):
                node = regs.find(cat) if regs is not None else None
                if node is None:
                    continue
                for r in node.findall("region"):
                    name = (r.findtext("name") or "").strip() or "?"
                    sparts = r.findall("spart")
                    n = len(sparts) if sparts else "-"
                    it = QTreeWidgetItem([name, target, str(n)])
                    it.setIcon(0, _reg_icon("volume"))
                    tw.addTopLevelItem(it)

        # Fluid
        tw = self._fluid["tree"]
        tw.clear()
        if xml is not None:
            regs = xml.section("regions")
            fluid = regs.find("fluid") if regs is not None else None
            if fluid is not None:
                for r in fluid.findall("region"):
                    name = (r.findtext("name") or "").strip() or "?"
                    prop = (r.findtext("property") or "").strip()
                    sparts = ", ".join(
                        (s.text or "").strip() for s in r.findall("spart")
                        if (s.text or "").strip())
                    it = QTreeWidgetItem([name, prop, sparts or "-"])
                    it.setIcon(0, _reg_icon("volume"))
                    tw.addTopLevelItem(it)

        # Reference points from session
        tw = self._ref["tree"]
        tw.clear()
        for rec in (self._ctx.get("session") or {}).get("ref_points") or []:
            c = rec.get("xyz", (0, 0, 0))
            it = QTreeWidgetItem([
                rec.get("name", "?"),
                f"({c[0]:g}, {c[1]:g}, {c[2]:g})",
            ])
            it.setIcon(0, _reg_icon("point"))
            tw.addTopLevelItem(it)

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        self._fill_parts_lists()
        self._reload_trees()
        draft = ctx.setdefault("session", {}).get("register_region") or {}
        if draft.get("name"):
            self._surf["ed_name"].setText(draft["name"])
        if draft.get("side"):
            i = self._surf["cb_side"].findText(draft["side"])
            if i >= 0:
                self._surf["cb_side"].setCurrentIndex(i)
        if draft.get("target"):
            i = self._surf["cb_target"].findText(draft["target"])
            if i >= 0:
                self._surf["cb_target"].setCurrentIndex(i)
        # Draw Window 最近一次面拾取 → Selected faces 列表
        self._surf["sel_faces"].clear()
        pick = ctx.get("last_pick") or {}
        if pick.get("face") is not None:
            gname = pick.get("group") or "(current)"
            self._surf["sel_faces"].addTopLevelItem(
                QTreeWidgetItem([str(gname), str(pick["face"])]))

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["register_region"] = {
            "name": self._surf["ed_name"].text().strip(),
            "side": self._surf["cb_side"].currentText(),
            "target": self._surf["cb_target"].currentText(),
            "tab": self.tabs.tabText(self.tabs.currentIndex()),
            "ref_points": list(
                (ctx.get("session") or {}).get("ref_points") or []),
            "part_interfaces": list(
                (ctx.get("session") or {}).get("part_interfaces") or []),
        }
        return True

    # ── 操作 ──────────────────────────────────────────────────────
    def _tree_for(self, kind: str) -> QTreeWidget:
        return {
            "face": self._surf["tree"], "iface": self._iface["tree"],
            "volume": self._vol["tree"], "fluid": self._fluid["tree"],
            "ref": self._ref["tree"],
        }[kind]

    def _xml_cat(self, kind: str) -> Optional[str]:
        return {
            "face": "face", "iface": "special_face",
            "volume": "volume", "fluid": "fluid",
        }.get(kind)

    def _rename(self, kind: str) -> None:
        tw = self._tree_for(kind)
        items = tw.selectedItems()
        if not items:
            return
        old = items[0].text(0)
        new, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        items[0].setText(0, new)
        cat = self._xml_cat(kind)
        if cat:
            node = _ensure_regions_cat(self._ctx.get("xml"), cat)
            if node is not None:
                for r in node.findall("region"):
                    if (r.findtext("name") or "").strip() == old:
                        el = r.find("name")
                        if el is not None:
                            el.text = new
                        self._ctx["xml_dirty"] = True
                        break
        if kind == "ref":
            for rec in (self._ctx.get("session") or {}).get("ref_points") or []:
                if rec.get("name") == old:
                    rec["name"] = new
        if kind == "iface":
            for rec in (self._ctx.get("session") or {}).get(
                    "part_interfaces") or []:
                if rec.get("name") == old:
                    rec["name"] = new

    def _delete(self, kind: str) -> None:
        tw = self._tree_for(kind)
        items = tw.selectedItems()
        if not items:
            return
        name = items[0].text(0)
        if QMessageBox.question(
                self, "Delete", f"Delete “{name}”?") != QMessageBox.Yes:
            return
        tw.takeTopLevelItem(tw.indexOfTopLevelItem(items[0]))
        cat = self._xml_cat(kind)
        if cat:
            node = _ensure_regions_cat(self._ctx.get("xml"), cat)
            if node is not None:
                for r in list(node.findall("region")):
                    if (r.findtext("name") or "").strip() == name:
                        node.remove(r)
                        self._ctx["xml_dirty"] = True
                        break
        if kind == "ref":
            pts = (self._ctx.setdefault("session", {})
                   .setdefault("ref_points", []))
            self._ctx["session"]["ref_points"] = [
                p for p in pts if p.get("name") != name]
        if kind == "iface":
            ifs = (self._ctx.setdefault("session", {})
                   .setdefault("part_interfaces", []))
            self._ctx["session"]["part_interfaces"] = [
                p for p in ifs if p.get("name") != name]

    def _register_surface(self) -> None:
        name = self._surf["ed_name"].text().strip()
        if not name:
            QMessageBox.information(self, self.title, "Region name is required.")
            return
        target = self._surf["cb_target"].currentText()
        if target == "Cross section region":
            QMessageBox.information(
                self, self.title,
                "请使用 New... 注册 Cross section region。")
            return
        node = _ensure_regions_cat(self._ctx.get("xml"), "face")
        if node is not None:
            for r in node.findall("region"):
                if (r.findtext("name") or "").strip() == name:
                    QMessageBox.information(
                        self, self.title, f"Region “{name}” already exists.")
                    return
            r = ET.SubElement(node, "region")
            ET.SubElement(r, "name").text = name
            ET.SubElement(r, "discontinuous_flag").text = "false"
            ET.SubElement(r, "connection_type").text = "default"
            # P5-3：多面引用——累计拾取的面全部写入 sface_num（每个 face 一个
            # <num>），无累计时回退单次 last_pick
            face_ids: list = []
            for key in (self._ctx.get("picked_faces") or []):
                f = key[1] if isinstance(key, (tuple, list)) else key
                if isinstance(f, int) and f >= 0 and f not in face_ids:
                    face_ids.append(f)
            pick = self._ctx.get("last_pick") or {}
            one = pick.get("face")
            if not face_ids and isinstance(one, int) and one >= 0:
                face_ids = [one]
            sface = ET.SubElement(r, "sface_num")
            for i, f in enumerate(face_ids):
                num = ET.SubElement(sface, "num")
                num.set("index", str(i))
                num.text = str(f)
            ET.SubElement(r, "face_region_type").text = "faces"
            ET.SubElement(r, "color_set").text = "false"
            self._ctx["xml_dirty"] = True
            tip = (f" + sface={len(face_ids)} 面" if face_ids
                   else " (no pick — empty sface_num)")
        else:
            tip = ""
        it = QTreeWidgetItem([name, "Surface region", "-"])
        it.setIcon(0, _reg_icon("surface"))
        self._surf["tree"].addTopLevelItem(it)
        self.apply(self._ctx)
        if tip:
            QMessageBox.information(
                self, self.title,
                f"Registered surface region “{name}”{tip}.\n"
                "Save project to persist main.xml.")

    def _register_interface(self) -> None:
        name = self._iface["ed_name"].text().strip()
        if not name:
            QMessageBox.information(self, self.title, "Region name is required.")
            return
        p1 = [self._iface["lst_p1"].item(i).text()
              for i in range(self._iface["lst_p1"].count())]
        p2 = [self._iface["lst_p2"].item(i).text()
              for i in range(self._iface["lst_p2"].count())]
        if not p1 or not p2:
            QMessageBox.information(
                self, self.title, "Part 1 and Part 2 are required.")
            return
        rec = {
            "name": name, "side": self._iface["cb_side"].currentText(),
            "part1": p1, "part2": p2,
        }
        ifs = self._ctx.setdefault("session", {}).setdefault(
            "part_interfaces", [])
        ifs.append(rec)
        it = QTreeWidgetItem([
            name, rec["side"], ", ".join(p1 + ["|"] + p2)])
        it.setIcon(0, _reg_icon("surface"))
        self._iface["tree"].addTopLevelItem(it)

    def _register_volume(self) -> None:
        if self._vol["cb_target"].currentIndex() != 0:
            QMessageBox.information(
                self, self.title, "请使用 New... 注册 Numerical region。")
            return
        name = self._vol["ed_name"].text().strip()
        parts = [i.text() for i in self._vol["lst_parts"].selectedItems()]
        if not name:
            QMessageBox.information(self, self.title, "Region name is required.")
            return
        node = _ensure_regions_cat(self._ctx.get("xml"), "volume")
        if node is not None:
            r = ET.SubElement(node, "region")
            ET.SubElement(r, "name").text = name
            for p in parts:
                ET.SubElement(r, "spart").text = p
            self._ctx["xml_dirty"] = True
        it = QTreeWidgetItem([
            name, "Selected part", str(len(parts) or "-")])
        it.setIcon(0, _reg_icon("volume"))
        self._vol["tree"].addTopLevelItem(it)

    def _register_fluid(self) -> None:
        name = self._fluid["ed_name"].text().strip()
        parts = [i.text() for i in self._fluid["lst_parts"].selectedItems()]
        if not name:
            QMessageBox.information(self, self.title, "Region name is required.")
            return
        node = _ensure_regions_cat(self._ctx.get("xml"), "fluid")
        if node is not None:
            r = ET.SubElement(node, "region")
            ET.SubElement(r, "name").text = name
            for p in parts:
                ET.SubElement(r, "spart").text = p
            self._ctx["xml_dirty"] = True
        it = QTreeWidgetItem([name, "", ", ".join(parts) or "-"])
        it.setIcon(0, _reg_icon("volume"))
        self._fluid["tree"].addTopLevelItem(it)

    def _register_refpoint(self) -> None:
        if self._ref["cb_method"].currentIndex() != 0:
            QMessageBox.information(
                self, self.title,
                "Batch / CSV 注册请用对应按钮；当前仅 Coordinate value 写入会话。")
            return
        name = self._ref["ed_name"].text().strip() or "Point_1"
        xyz = (self._ref["sp_x"].value(), self._ref["sp_y"].value(),
               self._ref["sp_z"].value())
        pts = self._ctx.setdefault("session", {}).setdefault("ref_points", [])
        pts.append({"name": name, "xyz": xyz})
        it = QTreeWidgetItem([name, f"({xyz[0]:g}, {xyz[1]:g}, {xyz[2]:g})"])
        it.setIcon(0, _reg_icon("point"))
        self._ref["tree"].addTopLevelItem(it)

    def _fill_view_center(self) -> None:
        lo, hi = _model_bounds_from_ctx(self._ctx)
        self._ref["sp_x"].setValue((lo[0] + hi[0]) * 0.5)
        self._ref["sp_y"].setValue((lo[1] + hi[1]) * 0.5)
        self._ref["sp_z"].setValue((lo[2] + hi[2]) * 0.5)

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "CSV file", "", "CSV (*.csv);;All (*)")
        if path:
            self._ref["ed_csv"].setText(path)

    def _export_ref_csv(self) -> None:
        pts = (self._ctx.get("session") or {}).get("ref_points") or []
        if not pts:
            QMessageBox.information(self, self.title, "No reference points.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV file", "ref_points.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("name,x,y,z\n")
            for p in pts:
                x, y, z = p.get("xyz", (0, 0, 0))
                f.write(f"{p.get('name', '')},{x},{y},{z}\n")
        QMessageBox.information(self, self.title, f"Exported {path}")


class _CoordSpecifiedPartDialog(QDialog):
    """[Create Coordinates-Specified Part] 子对话框（对齐手册截图）。"""

    def __init__(self, part_names: list[str], unit: str = "m",
                 bounds_ctx: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._bounds_ctx = bounds_ctx or {}
        self.setWindowTitle("Create Coordinates-Specified Part")
        self.setModal(True)
        self.resize(580, 500)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_name = QLineEdit("CoordinatesSpecifiedPart")
        form.addRow("Name", self.ed_name)
        root.addLayout(form)

        mid = QHBoxLayout()
        box = QGroupBox("Coordinate value")
        g = QGridLayout(box)
        self.sp_x = _spin_f(6, -1e9, 1e9, 0.0)
        self.sp_y = _spin_f(6, -1e9, 1e9, 0.0)
        self.sp_z = _spin_f(6, -1e9, 1e9, 0.0)
        for i, (lab, sp) in enumerate(
                (("X", self.sp_x), ("Y", self.sp_y), ("Z", self.sp_z))):
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(sp, i, 1)
            g.addWidget(QLabel(unit), i, 2)
        self.btn_view = QPushButton("Current view center coordinates")
        self.btn_preview = QPushButton("Preview")
        g.addWidget(self.btn_view, 3, 0, 1, 3)
        g.addWidget(self.btn_preview, 4, 0, 1, 3)
        mid.addWidget(box, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Linked part"))
        self.ed_linked = QLineEdit()
        self.ed_linked.setReadOnly(True)
        right.addWidget(self.ed_linked)
        right.addWidget(QLabel("Candidates of linked part"))
        self.lst = QListWidget()
        self.lst.addItems(part_names or [])
        right.addWidget(self.lst, 1)
        self.btn_update = QPushButton("Update based on coordinates")
        self.btn_link = QPushButton("Register selected part as linked part")
        self.btn_unlink = QPushButton("Remove linked part")
        right.addWidget(self.btn_update)
        right.addWidget(self.btn_link)
        right.addWidget(self.btn_unlink)
        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        self._linked = ""
        self.btn_link.clicked.connect(self._on_link)
        self.btn_unlink.clicked.connect(self._on_unlink)
        self.btn_view.clicked.connect(self._fill_center)
        self.btn_preview.clicked.connect(
            lambda: QMessageBox.information(
                self, "Preview",
                f"({self.sp_x.value():g}, {self.sp_y.value():g}, "
                f"{self.sp_z.value():g}) — 预览需 Draw Window。"))
        self.btn_update.clicked.connect(
            lambda: QMessageBox.information(
                self, "Update",
                "按坐标过滤候选零件需几何查询；本查看器保留完整零件列表。"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _on_link(self) -> None:
        items = self.lst.selectedItems()
        if not items:
            return
        self._linked = items[0].text()
        self.ed_linked.setText(self._linked)

    def _on_unlink(self) -> None:
        self._linked = ""
        self.ed_linked.clear()

    def _fill_center(self) -> None:
        lo, hi = _model_bounds_from_ctx(self._bounds_ctx)
        self.sp_x.setValue((lo[0] + hi[0]) * 0.5)
        self.sp_y.setValue((lo[1] + hi[1]) * 0.5)
        self.sp_z.setValue((lo[2] + hi[2]) * 0.5)

    def result_data(self) -> dict:
        return {
            "name": self.ed_name.text().strip() or "CoordinatesSpecifiedPart",
            "xyz": (self.sp_x.value(), self.sp_y.value(), self.sp_z.value()),
            "linked": self._linked,
        }


class NonSolidBody(_Body):
    """[Edit] – [Create Non-Solid Part]（对齐 scFLOWpre 三页签）。"""

    title = "Create Non-Solid Part"
    min_size = (680, 520)
    dialog_buttons = QDialogButtonBox.Close

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 4)
        self.tabs = QTabWidget()
        self._group = self._make_group_tab()
        self._coord = self._make_coord_tab()
        self._sheet = self._make_sheet_tab()
        self.tabs.addTab(self._group["page"], "Group Part")
        self.tabs.addTab(self._coord["page"], "Coordinates Specified Part")
        self.tabs.addTab(self._sheet["page"], "Surface Region-Derived Sheet")
        v.addWidget(self.tabs, 1)

    def _make_group_tab(self) -> dict:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addWidget(QLabel(
            "Make a group to create mesh from multiple solid and sheet "
            "parts as a single part."))
        h = QHBoxLayout()
        left = QGroupBox("Registered part")
        lv = QVBoxLayout(left)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Part Name"])
        tree.setRootIsDecorated(False)
        lv.addWidget(tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_rename = QPushButton("Rename...")
        btn_release = QPushButton("Release Group Part")
        row.addWidget(btn_rename)
        row.addWidget(btn_release)
        lv.addLayout(row)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("Name"))
        ed_name = QLineEdit("GroupPart")
        rv.addWidget(ed_name)
        rv.addWidget(QLabel("Selected part"))
        sel = QListWidget()
        sel.setSelectionMode(QListWidget.ExtendedSelection)
        rv.addWidget(sel, 1)
        tip = QLabel(
            "Select parts in the list (from project parts), then Register.")
        tip.setStyleSheet("color:#555; font-size:11px;")
        tip.setWordWrap(True)
        rv.addWidget(tip)
        row_reg = QHBoxLayout()
        row_reg.addStretch(1)
        btn_reg = QPushButton("Register")
        row_reg.addWidget(btn_reg)
        rv.addLayout(row_reg)
        h.addWidget(left, 1)
        h.addWidget(right, 1)
        outer.addLayout(h, 1)
        d = {
            "page": page, "tree": tree, "ed_name": ed_name, "sel": sel,
            "btn_rename": btn_rename, "btn_release": btn_release,
            "btn_reg": btn_reg,
        }
        btn_reg.clicked.connect(self._register_group)
        btn_rename.clicked.connect(lambda: self._rename_list(
            tree, "group_parts", "name"))
        btn_release.clicked.connect(lambda: self._delete_list(
            tree, "group_parts", "name", title="Release Group Part"))
        return d

    def _make_coord_tab(self) -> dict:
        page = QWidget()
        h = QHBoxLayout(page)
        left = QGroupBox("Registered coordinates-specified part")
        lv = QVBoxLayout(left)
        row_t = QHBoxLayout()
        tree = QTreeWidget()
        tree.setHeaderLabels(["Part"])
        tree.setRootIsDecorated(False)
        row_t.addWidget(tree, 1)
        side = QVBoxLayout()
        btn_up = QPushButton("Up")
        btn_down = QPushButton("Down")
        side.addWidget(btn_up)
        side.addWidget(btn_down)
        side.addStretch(1)
        row_t.addLayout(side)
        lv.addLayout(row_t, 1)
        row_b = QHBoxLayout()
        btn_export = QPushButton("Export to CSV file...")
        btn_rename = QPushButton("Rename...")
        btn_delete = QPushButton("Delete")
        row_b.addWidget(btn_export)
        row_b.addStretch(1)
        row_b.addWidget(btn_rename)
        row_b.addWidget(btn_delete)
        lv.addLayout(row_b)

        right = QGroupBox("Register/Edit")
        rv = QVBoxLayout(right)
        form = QFormLayout()
        cb_type = QComboBox()
        cb_type.addItems([
            "Coordinate value",
            "CSV file",
            "Create from mesh closed volume",
        ])
        form.addRow("Creation type", cb_type)
        rv.addLayout(form)
        stack = QStackedWidget()
        w0 = QWidget(); v0 = QVBoxLayout(w0)
        btn_new = QPushButton("New...")
        btn_edit = QPushButton("Edit...")
        btn_edit.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(btn_new)
        row.addWidget(btn_edit)
        row.addStretch(1)
        v0.addLayout(row)
        v0.addWidget(_note(
            "Click New… to open [Create Coordinates-Specified Part]."))
        v0.addStretch(1)
        stack.addWidget(w0)
        w1 = QWidget(); f1 = QFormLayout(w1)
        ed_csv = QLineEdit()
        btn_csv = QPushButton("Refer...")
        r1 = QHBoxLayout(); r1.addWidget(ed_csv, 1); r1.addWidget(btn_csv)
        wrap1 = QWidget(); wrap1.setLayout(r1)
        f1.addRow("CSV file", wrap1)
        stack.addWidget(w1)
        w2 = QWidget(); v2 = QVBoxLayout(w2)
        btn_mesh = QPushButton("Create New...")
        v2.addWidget(btn_mesh)
        v2.addWidget(_note(
            "Create from mesh closed volume — available before meshing "
            "in scFLOWpre."))
        v2.addStretch(1)
        stack.addWidget(w2)
        rv.addWidget(stack, 1)
        cb_type.currentIndexChanged.connect(stack.setCurrentIndex)

        h.addWidget(left, 1)
        h.addWidget(right, 1)
        d = {
            "page": page, "tree": tree, "cb_type": cb_type, "stack": stack,
            "btn_new": btn_new, "btn_edit": btn_edit, "btn_up": btn_up,
            "btn_down": btn_down, "btn_export": btn_export,
            "btn_rename": btn_rename, "btn_delete": btn_delete,
            "ed_csv": ed_csv, "btn_csv": btn_csv, "btn_mesh": btn_mesh,
        }
        btn_new.clicked.connect(self._new_coord_part)
        btn_edit.clicked.connect(self._edit_coord_part)
        btn_up.clicked.connect(lambda: self._move_tree(tree, -1))
        btn_down.clicked.connect(lambda: self._move_tree(tree, 1))
        btn_rename.clicked.connect(lambda: self._rename_list(
            tree, "coord_parts", "name"))
        btn_delete.clicked.connect(lambda: self._delete_list(
            tree, "coord_parts", "name"))
        btn_export.clicked.connect(self._export_coord_csv)
        btn_csv.clicked.connect(self._browse_coord_csv)
        btn_mesh.clicked.connect(
            lambda: QMessageBox.information(
                self, "Create from mesh closed volume",
                "需在 scFLOWpre 中从网格闭体创建坐标指定零件。"))
        tree.itemSelectionChanged.connect(
            lambda: btn_edit.setEnabled(bool(tree.selectedItems())))
        return d

    def _make_sheet_tab(self) -> dict:
        page = QWidget()
        h = QHBoxLayout(page)
        left = QGroupBox("Registered part")
        lv = QVBoxLayout(left)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Part Name", "Number of Faces"])
        tree.setRootIsDecorated(False)
        tree.setColumnWidth(0, 160)
        lv.addWidget(tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_rename = QPushButton("Rename...")
        btn_delete = QPushButton("Delete")
        row.addWidget(btn_rename)
        row.addWidget(btn_delete)
        lv.addLayout(row)

        right = QGroupBox("Register/Edit")
        rv = QVBoxLayout(right)
        form = QFormLayout()
        cb_target = QComboBox()
        cb_target.addItems([
            "Selected face",
            "Registered faces of surface region (Individual)",
            "Registered faces of surface region (Batch)",
        ])
        form.addRow("Target", cb_target)
        ed_name = QLineEdit()
        form.addRow("Part name", ed_name)
        ed_prefix = QLineEdit("Sheet_")
        form.addRow("Prefix name of surface region-derived sheet", ed_prefix)
        rv.addLayout(form)
        stack = QStackedWidget()
        # selected face
        w0 = QWidget(); v0 = QVBoxLayout(w0)
        faces = QTreeWidget()
        faces.setHeaderLabels(["Part Name", "Face Number"])
        faces.setRootIsDecorated(False)
        v0.addWidget(faces, 1)
        chk = QCheckBox("List selected faces")
        chk.setChecked(True)
        v0.addWidget(chk)
        stack.addWidget(w0)
        # individual surface region
        w1 = QWidget(); v1 = QVBoxLayout(w1)
        v1.addWidget(QLabel("Surface region"))
        lst_reg = QListWidget()
        v1.addWidget(lst_reg, 1)
        stack.addWidget(w1)
        # batch
        w2 = QWidget(); v2 = QVBoxLayout(w2)
        v2.addWidget(QLabel("Surface region"))
        lst_batch = QListWidget()
        lst_batch.setSelectionMode(QListWidget.ExtendedSelection)
        v2.addWidget(lst_batch, 1)
        stack.addWidget(w2)
        rv.addWidget(stack, 1)
        cb_target.currentIndexChanged.connect(stack.setCurrentIndex)

        def _sync_name_fields(i: int) -> None:
            ed_name.setVisible(i < 2)
            # find label for part name / prefix — toggle prefix for batch
            ed_prefix.setVisible(i == 2)
            # form row visibility via widget
            for j in range(form.rowCount()):
                pass
            lab = form.labelForField(ed_name)
            if lab:
                lab.setVisible(i < 2)
            lab2 = form.labelForField(ed_prefix)
            if lab2:
                lab2.setVisible(i == 2)

        cb_target.currentIndexChanged.connect(_sync_name_fields)
        _sync_name_fields(0)

        row_reg = QHBoxLayout()
        row_reg.addStretch(1)
        btn_reg = QPushButton("Register")
        row_reg.addWidget(btn_reg)
        rv.addLayout(row_reg)

        h.addWidget(left, 1)
        h.addWidget(right, 1)
        d = {
            "page": page, "tree": tree, "cb_target": cb_target,
            "ed_name": ed_name, "ed_prefix": ed_prefix, "stack": stack,
            "faces": faces, "chk": chk, "lst_reg": lst_reg,
            "lst_batch": lst_batch, "btn_reg": btn_reg,
            "btn_rename": btn_rename, "btn_delete": btn_delete,
        }
        btn_reg.clicked.connect(self._register_sheet)
        btn_rename.clicked.connect(lambda: self._rename_list(
            tree, "sheet_parts", "name"))
        btn_delete.clicked.connect(lambda: self._delete_list(
            tree, "sheet_parts", "name"))
        return d

    def _sess(self) -> dict:
        return self._ctx.setdefault("session", {}).setdefault("non_solid", {})

    def _unit(self) -> str:
        xenv = self._ctx.get("xenv")
        if xenv is not None:
            return (xenv.get("UNIT", "MODEL_LENGTH_UNIT", "m") or "m").strip() or "m"
        return "m"

    def _reload_lists(self) -> None:
        sess = self._sess()
        # group
        tw = self._group["tree"]
        tw.clear()
        for rec in sess.get("group_parts") or []:
            it = QTreeWidgetItem([rec.get("name", "?")])
            it.setToolTip(0, ", ".join(rec.get("parts") or []))
            tw.addTopLevelItem(it)
        # coord
        tw = self._coord["tree"]
        tw.clear()
        for rec in sess.get("coord_parts") or []:
            xyz = rec.get("xyz", (0, 0, 0))
            it = QTreeWidgetItem([rec.get("name", "?")])
            it.setToolTip(
                0, f"({xyz[0]:g}, {xyz[1]:g}, {xyz[2]:g}) "
                   f"linked={rec.get('linked') or '-'}")
            tw.addTopLevelItem(it)
        # sheet — session + xml
        tw = self._sheet["tree"]
        tw.clear()
        for rec in sess.get("sheet_parts") or []:
            it = QTreeWidgetItem([
                rec.get("name", "?"), str(rec.get("nfaces", "-"))])
            tw.addTopLevelItem(it)
        xml = self._ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                node = parts.find("face_region_derived_sheets")
                if node is not None:
                    existing = {tw.topLevelItem(i).text(0)
                                for i in range(tw.topLevelItemCount())}
                    for el in list(node):
                        name = (el.findtext("name") or el.tag or "").strip()
                        if name and name not in existing:
                            tw.addTopLevelItem(QTreeWidgetItem([name, "-"]))

        # selectable parts for group
        names = _part_names_from_ctx(self._ctx)
        self._group["sel"].clear()
        for n in names:
            self._group["sel"].addItem(n)
        # surface regions for sheet tab
        regs = []
        for r in (self._ctx.get("regions_meta") or {}).get("face") or []:
            if isinstance(r, dict) and r.get("name"):
                regs.append(r["name"])
        if xml is not None:
            regions = xml.section("regions")
            face = regions.find("face") if regions is not None else None
            if face is not None:
                for r in face.findall("region"):
                    n = (r.findtext("name") or "").strip()
                    if n and n not in regs:
                        regs.append(n)
        for lst in (self._sheet["lst_reg"], self._sheet["lst_batch"]):
            lst.clear()
            lst.addItems(regs)

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        self._sess()  # ensure
        draft = ctx.setdefault("session", {}).get("non_solid") or {}
        tab = draft.get("tab")
        if tab:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab:
                    self.tabs.setCurrentIndex(i)
                    break
        if draft.get("group_name"):
            self._group["ed_name"].setText(draft["group_name"])
        self._reload_lists()

    def apply(self, ctx: dict) -> bool:
        sess = ctx.setdefault("session", {}).setdefault("non_solid", {})
        sess["tab"] = self.tabs.tabText(self.tabs.currentIndex())
        sess["group_name"] = self._group["ed_name"].text().strip()
        # preserve lists already in sess
        sess.setdefault("group_parts", [])
        sess.setdefault("coord_parts", [])
        sess.setdefault("sheet_parts", [])
        return True

    def _rename_list(self, tree: QTreeWidget, key: str, field: str) -> None:
        items = tree.selectedItems()
        if not items:
            return
        old = items[0].text(0)
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        items[0].setText(0, new)
        for rec in self._sess().get(key) or []:
            if rec.get(field) == old:
                rec[field] = new
                break

    def _delete_list(self, tree: QTreeWidget, key: str, field: str,
                     title: str = "Delete") -> None:
        items = tree.selectedItems()
        if not items:
            return
        name = items[0].text(0)
        if QMessageBox.question(
                self, title, f"{title} “{name}”?") != QMessageBox.Yes:
            return
        tree.takeTopLevelItem(tree.indexOfTopLevelItem(items[0]))
        sess = self._sess()
        sess[key] = [r for r in (sess.get(key) or [])
                     if r.get(field) != name]

    def _move_tree(self, tree: QTreeWidget, delta: int) -> None:
        row = tree.currentIndex().row()
        if row < 0:
            return
        new = row + delta
        if new < 0 or new >= tree.topLevelItemCount():
            return
        it = tree.takeTopLevelItem(row)
        tree.insertTopLevelItem(new, it)
        tree.setCurrentItem(it)
        # reorder session coord_parts
        parts = self._sess().get("coord_parts") or []
        if 0 <= row < len(parts) and 0 <= new < len(parts):
            parts.insert(new, parts.pop(row))

    def _register_group(self) -> None:
        name = self._group["ed_name"].text().strip() or "GroupPart"
        parts = [i.text() for i in self._group["sel"].selectedItems()]
        if not parts:
            QMessageBox.information(
                self, self.title, "Select one or more parts to group.")
            return
        sess = self._sess()
        groups = sess.setdefault("group_parts", [])
        if any(g.get("name") == name for g in groups):
            QMessageBox.information(
                self, self.title, f"Group “{name}” already exists.")
            return
        groups.append({"name": name, "parts": parts})
        it = QTreeWidgetItem([name])
        it.setToolTip(0, ", ".join(parts))
        self._group["tree"].addTopLevelItem(it)

    def _new_coord_part(self) -> None:
        dlg = _CoordSpecifiedPartDialog(
            _part_names_from_ctx(self._ctx), self._unit(),
            bounds_ctx=self._ctx, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.result_data()
        sess = self._sess()
        parts = sess.setdefault("coord_parts", [])
        parts.append(data)
        it = QTreeWidgetItem([data["name"]])
        xyz = data["xyz"]
        it.setToolTip(
            0, f"({xyz[0]:g}, {xyz[1]:g}, {xyz[2]:g}) "
               f"linked={data.get('linked') or '-'}")
        self._coord["tree"].addTopLevelItem(it)

    def _edit_coord_part(self) -> None:
        items = self._coord["tree"].selectedItems()
        if not items:
            return
        name = items[0].text(0)
        parts = self._sess().get("coord_parts") or []
        rec = next((p for p in parts if p.get("name") == name), None)
        if rec is None:
            return
        dlg = _CoordSpecifiedPartDialog(
            _part_names_from_ctx(self._ctx), self._unit(),
            bounds_ctx=self._ctx, parent=self)
        dlg.ed_name.setText(rec.get("name", ""))
        xyz = rec.get("xyz", (0, 0, 0))
        dlg.sp_x.setValue(xyz[0]); dlg.sp_y.setValue(xyz[1])
        dlg.sp_z.setValue(xyz[2])
        if rec.get("linked"):
            dlg._linked = rec["linked"]
            dlg.ed_linked.setText(dlg._linked)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.result_data()
        rec.update(data)
        items[0].setText(0, data["name"])
        items[0].setToolTip(
            0, f"({data['xyz'][0]:g}, {data['xyz'][1]:g}, "
               f"{data['xyz'][2]:g}) linked={data.get('linked') or '-'}")

    def _export_coord_csv(self) -> None:
        parts = self._sess().get("coord_parts") or []
        if not parts:
            QMessageBox.information(
                self, self.title, "No coordinates-specified parts.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV file", "coord_parts.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("name,x,y,z,linked\n")
            for p in parts:
                x, y, z = p.get("xyz", (0, 0, 0))
                f.write(f"{p.get('name','')},{x},{y},{z},"
                        f"{p.get('linked','')}\n")
        QMessageBox.information(self, self.title, f"Exported {path}")

    def _browse_coord_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "CSV file", "", "CSV (*.csv);;All (*)")
        if path:
            self._coord["ed_csv"].setText(path)
            # import lines as coord parts (name,x,y,z)
            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
            except OSError as exc:
                QMessageBox.warning(self, self.title, str(exc))
                return
            sess = self._sess()
            parts = sess.setdefault("coord_parts", [])
            for ln in lines[1:] if lines and lines[0].lower().startswith("name") else lines:
                cols = [c.strip() for c in ln.split(",")]
                if len(cols) < 4:
                    continue
                try:
                    xyz = (float(cols[1]), float(cols[2]), float(cols[3]))
                except ValueError:
                    continue
                rec = {
                    "name": cols[0], "xyz": xyz,
                    "linked": cols[4] if len(cols) > 4 else "",
                }
                parts.append(rec)
                it = QTreeWidgetItem([rec["name"]])
                it.setToolTip(0, f"({xyz[0]:g}, {xyz[1]:g}, {xyz[2]:g})")
                self._coord["tree"].addTopLevelItem(it)

    def _register_sheet(self) -> None:
        ti = self._sheet["cb_target"].currentIndex()
        sess = self._sess()
        sheets = sess.setdefault("sheet_parts", [])
        if ti == 0:
            name = self._sheet["ed_name"].text().strip()
            if not name:
                QMessageBox.information(
                    self, self.title, "Part name is required.")
                return
            sheets.append({"name": name, "nfaces": "-", "target": "Selected face"})
            self._sheet["tree"].addTopLevelItem(QTreeWidgetItem([name, "-"]))
        elif ti == 1:
            name = self._sheet["ed_name"].text().strip()
            items = self._sheet["lst_reg"].selectedItems()
            if not name or not items:
                QMessageBox.information(
                    self, self.title,
                    "Part name and a surface region are required.")
                return
            sheets.append({
                "name": name, "nfaces": "-",
                "target": "Individual", "region": items[0].text(),
            })
            self._sheet["tree"].addTopLevelItem(QTreeWidgetItem([name, "-"]))
        else:
            prefix = self._sheet["ed_prefix"].text().strip()
            items = self._sheet["lst_batch"].selectedItems()
            if not items:
                QMessageBox.information(
                    self, self.title, "Select one or more surface regions.")
                return
            for it in items:
                name = f"{prefix}{it.text()}"
                sheets.append({
                    "name": name, "nfaces": "-",
                    "target": "Batch", "region": it.text(),
                })
                self._sheet["tree"].addTopLevelItem(
                    QTreeWidgetItem([name, "-"]))


# ── Part Material / [Material] 对话框 ─────────────────────────────

_FLUID_PRP_TYPES = frozenset({"fluid", "compressive_fluid"})
_SOLID_PRP_TYPES = frozenset({"solid"})


def _prp_entry_type(entry: ET.Element) -> str:
    return (entry.findtext("type") or "").strip()


def _prp_entry_label(entry: ET.Element) -> str:
    return (entry.findtext("key")
            or entry.findtext("name")
            or "").strip()


def _prp_lookup(prp, key: str) -> Optional[tuple]:
    """返回 (group_key, entry) 或 None。"""
    if prp is None or not key or key in ("@Obstacle", "Obstacle"):
        return None
    for g in prp.groups:
        for e in prp.entries(g):
            if _prp_entry_label(e) == key or (e.findtext("key") or "") == key:
                return (g.findtext("key") or "", e)
    return None


_INSTALL_PRP_CACHE = None


def install_prp_fallback():
    """P4-2：安装目录属性库兜底（scFLOWpre.prp + STpre 双库合并）。

    项目 pph 未带 main.prp（或为空）时，材料树用安装目录的完整库
    （流体 ~130 + 固体 ~160）构建；形态与 :class:`PrpDatabase` 一致。
    """
    global _INSTALL_PRP_CACHE
    if _INSTALL_PRP_CACHE is not None:
        return _INSTALL_PRP_CACHE or None
    try:
        from material_lib import material_lib_cached
        from pphxml import PrpDatabase
        lib = material_lib_cached()
        if lib is None:
            _INSTALL_PRP_CACHE = False
            return None
        groups: dict[str, ET.Element] = {}
        order: list[ET.Element] = []
        for m in lib.property_entries():
            g = groups.get(m.group)
            if g is None:
                g = groups[m.group] = ET.Element("group")
                ET.SubElement(g, "key").text = m.group
                order.append(g)
            e = ET.SubElement(g, "entry")
            ET.SubElement(e, "key").text = m.name
            if m.kind:
                ET.SubElement(e, "type").text = m.kind
            for k, v in m.props.items():
                ET.SubElement(e, k).text = v
        db = PrpDatabase(groups=order)
        _INSTALL_PRP_CACHE = db
        return db
    except Exception:  # noqa: BLE001
        _INSTALL_PRP_CACHE = False
        return None


def _ui_attribute_from_property(prop: str, prp) -> str:
    prop = (prop or "").strip()
    if not prop or prop in ("@Obstacle", "Obstacle"):
        return "Obstacle"
    hit = _prp_lookup(prp, prop)
    if hit is None:
        return "Fluid"
    _gk, entry = hit
    t = _prp_entry_type(entry)
    if t in _SOLID_PRP_TYPES:
        return "Solid"
    return "Fluid"


def _display_material(prop: str) -> str:
    prop = (prop or "").strip()
    if not prop or prop in ("@Obstacle", "Obstacle"):
        return "Obstacle"
    return prop


def _ensure_child_text(parent: ET.Element, tag: str, text: str) -> None:
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    el.text = text


def _iter_xml_parts(xml) -> list[ET.Element]:
    """main.xml 中实体 Part（排除 face_region_derived_sheets）。"""
    if xml is None:
        return []
    parts = xml.section("parts")
    if parts is None:
        return []
    sheet_ids = set()
    frds = parts.find("face_region_derived_sheets")
    if frds is not None:
        for pt in frds.iter("part"):
            sheet_ids.add(id(pt))
    out = []
    for pt in parts.iter("part"):
        if id(pt) in sheet_ids:
            continue
        if (pt.findtext("name") or "").strip():
            out.append(pt)
    return out


def _iter_xml_sheet_parts(xml) -> list[ET.Element]:
    """Sheet / 派生薄片 Part（face_region_derived_sheets 等）。"""
    if xml is None:
        return []
    parts = xml.section("parts")
    if parts is None:
        return []
    out = []
    frds = parts.find("face_region_derived_sheets")
    if frds is not None:
        for pt in frds.iter("part"):
            if (pt.findtext("name") or "").strip():
                out.append(pt)
        for sh in list(frds.iter("sheet")):
            if (sh.findtext("name") or "").strip():
                out.append(sh)
    return out


def _part_thickness_mm(el: ET.Element) -> str:
    tv = el.find("thickness_val")
    if tv is None:
        return "-"
    try:
        val = float(tv.findtext("const_value") or "0")
    except ValueError:
        return "-"
    unit = (tv.findtext("unit") or "m").strip().lower()
    if unit == "m":
        val *= 1000.0
    elif unit == "cm":
        val *= 10.0
    if abs(val) < 1e-15:
        return "-"
    return f"{val:g} mm"


class _MaterialOptionsDialog(QDialog):
    """[Material Property Option]（手册 Options…）。"""

    def __init__(self, draft: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Material Property Option")
        self.setModal(True)
        self.resize(520, 280)
        v = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        rows = [
            ("Universal gas constant",
             draft.get("gas_constant", "Default (8.3144598)"), "", ""),
            ("Minimum depth of liquid film",
             draft.get("min_film", "Default (1e-15[m])"), "", ""),
            ("Percentage of implicit treatment by wall "
             "resistance of liquid film",
             draft.get("implicit_film", "Default (1.0)"), "", ""),
        ]
        for r in rows:
            self.tree.addTopLevelItem(QTreeWidgetItem(list(r)))
        v.addWidget(self.tree, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)

    def values(self) -> dict:
        out = {}
        keys = ("gas_constant", "min_film", "implicit_film")
        for i, k in enumerate(keys):
            it = self.tree.topLevelItem(i)
            out[k] = it.text(1) if it else ""
        return out


class _ContactThicknessDialog(QDialog):
    """[Contact Thickness]（Sheet Part）。"""

    def __init__(self, draft: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contact Thickness")
        self.setModal(True)
        self.resize(640, 420)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Set contact thickness of heat conduction panels."))
        g = QGroupBox("Default contact thickness")
        gv = QVBoxLayout(g)
        self.rb_dist = QRadioButton(
            "Distribute panel thickness to contacting solid parts")
        self.rb_zero = QRadioButton("0")
        if draft.get("default", "distribute") == "0":
            self.rb_zero.setChecked(True)
        else:
            self.rb_dist.setChecked(True)
        gv.addWidget(self.rb_dist)
        gv.addWidget(self.rb_zero)
        v.addWidget(g)

        h = QHBoxLayout()
        left = QGroupBox("Contact thickness setting")
        lv = QVBoxLayout(left)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Region Name", "Type", "Thickness"])
        self.tree.setRootIsDecorated(False)
        for row in draft.get("regions") or []:
            self.tree.addTopLevelItem(QTreeWidgetItem([
                row.get("name", ""), row.get("type", "Default"),
                row.get("thickness", ""),
            ]))
        lv.addWidget(self.tree, 1)
        right = QGroupBox("Thickness")
        rv = QFormLayout(right)
        self.cb_type = QComboBox()
        self.cb_type.addItems([
            "Default", "Thickness of panel",
            "Ratio to panel thickness", "Specify value",
        ])
        self.ed_val = QLineEdit()
        rv.addRow("Type", self.cb_type)
        rv.addRow(self.ed_val)
        row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply")
        self.btn_default = QPushButton("Default")
        row.addWidget(self.btn_apply)
        row.addWidget(self.btn_default)
        rv.addRow(row)
        h.addWidget(left, 3)
        h.addWidget(right, 2)
        v.addLayout(h, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)
        self.btn_apply.clicked.connect(self._apply_row)
        self.btn_default.clicked.connect(
            lambda: self.cb_type.setCurrentText("Default"))

    def _apply_row(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        for it in items:
            it.setText(1, self.cb_type.currentText())
            it.setText(2, self.ed_val.text().strip())

    def values(self) -> dict:
        regs = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            regs.append({
                "name": it.text(0), "type": it.text(1),
                "thickness": it.text(2),
            })
        return {
            "default": "0" if self.rb_zero.isChecked() else "distribute",
            "regions": regs,
        }


class PartMaterialBody(_Body):
    """[Condition] – [Part Material] → [Material]（对齐 scFLOWpre）。"""

    title = "Material"
    min_size = (820, 560)
    dialog_buttons = QDialogButtonBox.Ok

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._part_rows: list[dict] = []
        self._sheet_rows: list[dict] = []
        self._mat_index: dict[str, str] = {}  # material key → prp type
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 4)

        self.tabs = QTabWidget()
        self._part_tab = self._make_part_tab()
        self._sheet_tab = self._make_sheet_tab()
        self.tabs.addTab(self._part_tab["page"], "Part")
        self.tabs.addTab(self._sheet_tab["page"], "Sheet Part")
        v.addWidget(self.tabs, 1)

        foot = QHBoxLayout()
        self.btn_options = QPushButton("Options...")
        self.btn_local = QPushButton("Check local coordinates for parts")
        self.btn_local.setVisible(False)
        foot.addWidget(self.btn_options)
        foot.addWidget(self.btn_local)
        foot.addStretch(1)
        v.addLayout(foot)

        self.btn_options.clicked.connect(self._open_options)
        self.btn_local.clicked.connect(self._open_local_coords)
        self._part_tab["rb_obstacle"].toggled.connect(
            lambda _=False: self._rebuild_mat_tree("part"))
        self._part_tab["rb_fluid"].toggled.connect(
            lambda _=False: self._rebuild_mat_tree("part"))
        self._part_tab["rb_solid"].toggled.connect(
            lambda _=False: self._rebuild_mat_tree("part"))
        self._sheet_tab["cb_attr"].currentIndexChanged.connect(
            lambda _=0: self._rebuild_mat_tree("sheet"))
        self._part_tab["btn_apply"].clicked.connect(
            lambda: self._apply_selection("part"))
        self._part_tab["btn_remove"].clicked.connect(
            lambda: self._remove_selection("part"))
        self._sheet_tab["btn_apply"].clicked.connect(
            lambda: self._apply_selection("sheet"))
        self._sheet_tab["btn_remove"].clicked.connect(
            lambda: self._remove_selection("sheet"))
        self._part_tab["ed_search"].textChanged.connect(
            lambda t: self._filter_left("part", t))
        self._sheet_tab["ed_search"].textChanged.connect(
            lambda t: self._filter_left("sheet", t))
        self._sheet_tab["btn_contact"].clicked.connect(
            self._open_contact_thickness)

    def _make_part_tab(self) -> dict:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        tree = QTreeWidget()
        tree.setHeaderLabels(["#", "Part Name", "Attribute", "Material"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        tree.setSortingEnabled(True)
        tree.setColumnWidth(0, 36)
        tree.setColumnWidth(1, 140)
        lv.addWidget(tree, 1)
        chk = QCheckBox("Reflect selection in draw window")
        chk.setChecked(True)
        lv.addWidget(chk)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search by part name"))
        ed_search = QLineEdit()
        search_row.addWidget(ed_search, 1)
        lv.addLayout(search_row)

        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(4, 0, 4, 0)
        mv.addStretch(1)
        btn_apply = QPushButton("<<Apply")
        btn_remove = QPushButton("Cancel>>")
        mv.addWidget(btn_apply)
        mv.addWidget(btn_remove)
        mv.addStretch(1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        attr_box = QGroupBox("Attribute")
        ah = QHBoxLayout(attr_box)
        rb_obs = QRadioButton("Obstacle")
        rb_fluid = QRadioButton("Fluid")
        rb_solid = QRadioButton("Solid")
        rb_solid.setChecked(True)
        for rb in (rb_obs, rb_fluid, rb_solid):
            ah.addWidget(rb)
        ah.addStretch(1)
        rv.addWidget(attr_box)
        mat_box = QGroupBox("Material")
        ml = QVBoxLayout(mat_box)
        mat_tree = QTreeWidget()
        mat_tree.setHeaderHidden(True)
        mat_tree.setRootIsDecorated(True)
        mat_tree.setAlternatingRowColors(True)
        ml.addWidget(mat_tree, 1)
        rv.addWidget(mat_box, 1)

        h.addWidget(left, 3)
        h.addWidget(mid, 0)
        h.addWidget(right, 2)
        return {
            "page": page, "tree": tree, "chk_reflect": chk,
            "ed_search": ed_search, "btn_apply": btn_apply,
            "btn_remove": btn_remove, "rb_obstacle": rb_obs,
            "rb_fluid": rb_fluid, "rb_solid": rb_solid,
            "mat_tree": mat_tree,
        }

    def _make_sheet_tab(self) -> dict:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        tree = QTreeWidget()
        tree.setHeaderLabels(
            ["#", "Part Name", "Attribute", "Thickness", "Material"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        tree.setSortingEnabled(True)
        tree.setColumnWidth(0, 36)
        tree.setColumnWidth(1, 120)
        lv.addWidget(tree, 1)
        chk = QCheckBox("Reflect selection in draw window")
        chk.setChecked(True)
        lv.addWidget(chk)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search by part name"))
        ed_search = QLineEdit()
        search_row.addWidget(ed_search, 1)
        lv.addLayout(search_row)

        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(4, 0, 4, 0)
        mv.addStretch(1)
        btn_apply = QPushButton("<<Apply")
        btn_remove = QPushButton("Cancel>>")
        mv.addWidget(btn_apply)
        mv.addWidget(btn_remove)
        mv.addStretch(1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        cb_attr = QComboBox()
        cb_attr.addItems([
            "Obstacle",
            "Fluid (liquid panel)",
            "Solid (heat conduction panel)",
            "Solid (moving heat conduction panel)",
            "Test section",
        ])
        form.addRow("Attribute", cb_attr)
        thick_row = QHBoxLayout()
        sp_thick = _spin_f(3, 0.0, 1e6, 0.0)
        cb_unit = QComboBox()
        cb_unit.addItems(["mm", "m", "cm", "in"])
        thick_row.addWidget(sp_thick, 1)
        thick_row.addWidget(cb_unit)
        form.addRow("Thickness", thick_row)
        rv.addLayout(form)
        mat_box = QGroupBox("Material")
        ml = QVBoxLayout(mat_box)
        mat_tree = QTreeWidget()
        mat_tree.setHeaderHidden(True)
        mat_tree.setRootIsDecorated(True)
        ml.addWidget(mat_tree, 1)
        rv.addWidget(mat_box, 1)
        btn_contact = QPushButton("Contact thickness")
        rv.addWidget(btn_contact)

        h.addWidget(left, 3)
        h.addWidget(mid, 0)
        h.addWidget(right, 2)
        return {
            "page": page, "tree": tree, "chk_reflect": chk,
            "ed_search": ed_search, "btn_apply": btn_apply,
            "btn_remove": btn_remove, "cb_attr": cb_attr,
            "sp_thick": sp_thick, "cb_unit": cb_unit,
            "mat_tree": mat_tree, "btn_contact": btn_contact,
        }

    def _current_part_attr(self) -> str:
        d = self._part_tab
        if d["rb_obstacle"].isChecked():
            return "Obstacle"
        if d["rb_fluid"].isChecked():
            return "Fluid"
        return "Solid"

    def _set_part_attr_radios(self, attr: str) -> None:
        d = self._part_tab
        mapping = {
            "Obstacle": d["rb_obstacle"],
            "Fluid": d["rb_fluid"],
            "Solid": d["rb_solid"],
        }
        rb = mapping.get(attr, d["rb_solid"])
        rb.setChecked(True)

    def _rebuild_mat_tree(self, which: str) -> None:
        d = self._part_tab if which == "part" else self._sheet_tab
        tree: QTreeWidget = d["mat_tree"]
        tree.clear()
        # P4-2：项目 prp 缺失/为空时回退安装目录属性库（~130 流体
        # + ~160 固体）
        prp = self._ctx.get("prp")
        if prp is None or not prp.groups:
            prp = install_prp_fallback()
        if which == "part":
            attr = self._current_part_attr()
            if attr == "Obstacle":
                it = QTreeWidgetItem(["Obstacle"])
                it.setData(0, Qt.UserRole, "@Obstacle")
                tree.addTopLevelItem(it)
                return
            want = _FLUID_PRP_TYPES if attr == "Fluid" else _SOLID_PRP_TYPES
        else:
            attr = self._sheet_tab["cb_attr"].currentText()
            if attr == "Obstacle":
                it = QTreeWidgetItem(["Obstacle"])
                it.setData(0, Qt.UserRole, "@Obstacle")
                tree.addTopLevelItem(it)
                return
            if attr.startswith("Fluid"):
                want = _FLUID_PRP_TYPES
            else:
                want = _SOLID_PRP_TYPES

        if prp is None:
            return
        for g in prp.groups:
            ents = [e for e in prp.entries(g)
                    if _prp_entry_type(e) in want]
            if not ents:
                continue
            gname = g.findtext("key") or g.findtext("name") or "(group)"
            gitem = QTreeWidgetItem([gname])
            gitem.setFlags(gitem.flags() & ~Qt.ItemIsSelectable)
            for e in ents:
                label = _prp_entry_label(e)
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.UserRole, e.findtext("key") or label)
                gitem.addChild(child)
            tree.addTopLevelItem(gitem)

    def _selected_material_key(self, which: str) -> Optional[str]:
        d = self._part_tab if which == "part" else self._sheet_tab
        if which == "part" and self._current_part_attr() == "Obstacle":
            return "@Obstacle"
        if which == "sheet" and self._sheet_tab["cb_attr"].currentText() == "Obstacle":
            return "@Obstacle"
        items = d["mat_tree"].selectedItems()
        if not items:
            return None
        key = items[0].data(0, Qt.UserRole)
        if key is None and items[0].childCount() == 0:
            key = items[0].text(0)
        return key

    def _filter_left(self, which: str, text: str) -> None:
        d = self._part_tab if which == "part" else self._sheet_tab
        tree: QTreeWidget = d["tree"]
        needle = (text or "").strip().lower()
        for i in range(tree.topLevelItemCount()):
            it = tree.topLevelItem(i)
            name = it.text(1).lower()
            it.setHidden(bool(needle) and needle not in name)

    def _fill_left_trees(self) -> None:
        prp = self._ctx.get("prp")
        # Part tab
        pt = self._part_tab["tree"]
        pt.setSortingEnabled(False)
        pt.clear()
        for i, row in enumerate(self._part_rows, 1):
            attr = _ui_attribute_from_property(row.get("property", ""), prp)
            mat = _display_material(row.get("property", ""))
            it = QTreeWidgetItem([str(i), row["name"], attr, mat])
            it.setData(0, Qt.UserRole, row["name"])
            it.setIcon(1, _region_icon("volume", 14))
            pt.addTopLevelItem(it)
        pt.setSortingEnabled(True)

        st = self._sheet_tab["tree"]
        st.setSortingEnabled(False)
        st.clear()
        for i, row in enumerate(self._sheet_rows, 1):
            attr = row.get("sheet_attr") or "Obstacle"
            mat = _display_material(row.get("property", ""))
            thick = row.get("thickness") or "-"
            it = QTreeWidgetItem([str(i), row["name"], attr, thick, mat])
            it.setData(0, Qt.UserRole, row["name"])
            it.setIcon(1, _region_icon("surface", 14))
            st.addTopLevelItem(it)
        st.setSortingEnabled(True)

    def _apply_selection(self, which: str) -> None:
        d = self._part_tab if which == "part" else self._sheet_tab
        items = d["tree"].selectedItems()
        if not items:
            QMessageBox.information(
                self, "Material", "Select part(s) in the list.")
            return
        mat = self._selected_material_key(which)
        if which == "part":
            attr = self._current_part_attr()
            if attr != "Obstacle" and not mat:
                QMessageBox.information(
                    self, "Material", "Select a material on the right.")
                return
            if attr == "Obstacle":
                mat = "@Obstacle"
            for it in items:
                name = it.data(0, Qt.UserRole) or it.text(1)
                it.setText(2, attr)
                it.setText(3, _display_material(mat))
                self._write_part_material(name, mat, sheet=False)
        else:
            attr = self._sheet_tab["cb_attr"].currentText()
            if attr != "Obstacle" and not mat:
                QMessageBox.information(
                    self, "Material", "Select a material on the right.")
                return
            if attr == "Obstacle":
                mat = "@Obstacle"
            unit = self._sheet_tab["cb_unit"].currentText()
            thick = self._sheet_tab["sp_thick"].value()
            thick_s = "-" if attr == "Obstacle" else f"{thick:g} {unit}"
            for it in items:
                name = it.data(0, Qt.UserRole) or it.text(1)
                it.setText(2, attr)
                it.setText(3, thick_s)
                it.setText(4, _display_material(mat))
                self._write_part_material(
                    name, mat, sheet=True, sheet_attr=attr,
                    thickness=thick, unit=unit)
        self._sync_session()

    def _remove_selection(self, which: str) -> None:
        d = self._part_tab if which == "part" else self._sheet_tab
        items = d["tree"].selectedItems()
        if not items:
            return
        for it in items:
            name = it.data(0, Qt.UserRole) or it.text(1)
            if which == "part":
                it.setText(2, "Obstacle")
                it.setText(3, "Obstacle")
                self._write_part_material(name, "@Obstacle", sheet=False)
            else:
                it.setText(2, "Obstacle")
                it.setText(3, "-")
                it.setText(4, "Obstacle")
                self._write_part_material(
                    name, "@Obstacle", sheet=True, sheet_attr="Obstacle")
        self._sync_session()

    def _write_part_material(
            self, name: str, material: str, *, sheet: bool,
            sheet_attr: str = "", thickness: float = 0.0,
            unit: str = "mm") -> None:
        xml = self._ctx.get("xml")
        el = None
        if xml is not None:
            pool = (_iter_xml_sheet_parts(xml) if sheet
                    else _iter_xml_parts(xml))
            for pt in pool:
                if (pt.findtext("name") or "") == name:
                    el = pt
                    break
        if el is not None:
            _ensure_child_text(el, "property", material)
            if sheet:
                # sheettype / attribute 粗映射
                st_map = {
                    "Obstacle": "obstacle",
                    "Fluid (liquid panel)": "liquid_panel",
                    "Solid (heat conduction panel)": "heat_conduction_panel",
                    "Solid (moving heat conduction panel)":
                        "moving_heat_conduction_panel",
                    "Test section": "test_section",
                }
                if sheet_attr:
                    _ensure_child_text(
                        el, "sheettype", st_map.get(sheet_attr, "obstacle"))
                tv = el.find("thickness_val")
                if tv is None:
                    tv = ET.SubElement(el, "thickness_val")
                # 内部统一存 m
                val = thickness
                u = unit.lower()
                if u == "mm":
                    val = thickness / 1000.0
                elif u == "cm":
                    val = thickness / 100.0
                elif u == "in":
                    val = thickness * 0.0254
                _ensure_child_text(tv, "const_value", _fmt_float(val))
                _ensure_child_text(tv, "unit", "m")
            self._ctx["xml_dirty"] = True
        # 同步内存行
        rows = self._sheet_rows if sheet else self._part_rows
        for row in rows:
            if row["name"] == name:
                row["property"] = material
                if sheet:
                    row["sheet_attr"] = sheet_attr or row.get("sheet_attr")
                    row["thickness"] = (
                        "-" if (sheet_attr or "") == "Obstacle"
                        else f"{thickness:g} {unit}")
                break

    def _sync_session(self) -> None:
        sess = self._ctx.setdefault("session", {})
        sess["part_material"] = {
            "parts": [
                {"name": r["name"], "property": r.get("property", ""),
                 "attribute": _ui_attribute_from_property(
                     r.get("property", ""), self._ctx.get("prp"))}
                for r in self._part_rows
            ],
            "sheets": list(self._sheet_rows),
            "options": sess.get("part_material", {}).get("options") or {},
            "contact_thickness": sess.get("part_material", {}).get(
                "contact_thickness") or {},
            "reflect_part": self._part_tab["chk_reflect"].isChecked(),
            "reflect_sheet": self._sheet_tab["chk_reflect"].isChecked(),
        }

    def _open_options(self) -> None:
        draft = (self._ctx.get("session", {})
                 .get("part_material", {})
                 .get("options") or {})
        dlg = _MaterialOptionsDialog(draft, self)
        if dlg.exec_() == QDialog.Accepted:
            self._ctx.setdefault("session", {}).setdefault(
                "part_material", {})["options"] = dlg.values()

    def _open_contact_thickness(self) -> None:
        draft = (self._ctx.get("session", {})
                 .get("part_material", {})
                 .get("contact_thickness") or {})
        dlg = _ContactThicknessDialog(draft, self)
        if dlg.exec_() == QDialog.Accepted:
            self._ctx.setdefault("session", {}).setdefault(
                "part_material", {})["contact_thickness"] = dlg.values()

    def _open_local_coords(self) -> None:
        QMessageBox.information(
            self, "Local Coordinate System for Parts",
            "Local coordinates appear when a material that uses "
            "per-part axes is assigned. Edit them in scFLOWpre if needed.")

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        self._part_rows = []
        self._sheet_rows = []
        xml = ctx.get("xml")
        prp = ctx.get("prp")
        # index materials
        self._mat_index = {}
        if prp is not None:
            for g in prp.groups:
                for e in prp.entries(g):
                    k = e.findtext("key") or _prp_entry_label(e)
                    self._mat_index[k] = _prp_entry_type(e)

        seen = set()
        for pt in _iter_xml_parts(xml):
            name = (pt.findtext("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            self._part_rows.append({
                "name": name,
                "property": (pt.findtext("property") or "").strip(),
            })
        # groups_info 兜底（无 xml part 时）
        if not self._part_rows:
            for g in sorted((ctx.get("groups_info") or {})):
                self._part_rows.append({"name": g, "property": ""})

        for pt in _iter_xml_sheet_parts(xml):
            name = (pt.findtext("name") or "").strip()
            if not name:
                continue
            st = (pt.findtext("sheettype") or "obstacle").strip()
            st_ui = {
                "obstacle": "Obstacle",
                "liquid_panel": "Fluid (liquid panel)",
                "heat_conduction_panel": "Solid (heat conduction panel)",
                "moving_heat_conduction_panel":
                    "Solid (moving heat conduction panel)",
                "test_section": "Test section",
            }.get(st, "Obstacle")
            self._sheet_rows.append({
                "name": name,
                "property": (pt.findtext("property") or "").strip(),
                "sheet_attr": st_ui,
                "thickness": _part_thickness_mm(pt),
            })

        draft = ctx.setdefault("session", {}).get("part_material") or {}
        if draft.get("reflect_part") is False:
            self._part_tab["chk_reflect"].setChecked(False)
        if draft.get("reflect_sheet") is False:
            self._sheet_tab["chk_reflect"].setChecked(False)

        self._fill_left_trees()
        self._rebuild_mat_tree("part")
        self._rebuild_mat_tree("sheet")
        # 选中首行时同步右侧 Attribute
        if self._part_rows:
            attr = _ui_attribute_from_property(
                self._part_rows[0].get("property", ""), prp)
            self._set_part_attr_radios(attr)
            self._rebuild_mat_tree("part")

    def apply(self, ctx: dict) -> bool:
        self._ctx = ctx
        self._sync_session()
        return True


# ── Condition Wizard（[Condition] – [Conditions]）─────────────────

def _wizard_folder_icon(size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#c49a3a"), 1))
    p.setBrush(QBrush(QColor("#f4c542")))
    p.drawRoundedRect(1, 4, size - 3, size - 6, 1.0, 1.0)
    p.setBrush(QBrush(QColor("#ffd966")))
    p.drawRoundedRect(1, 2, int(size * 0.45), 4, 1.0, 1.0)
    p.end()
    return QIcon(pm)


def _wizard_leaf_icon(size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#1565c0"), 1))
    p.setBrush(QBrush(QColor("#64b5f6")))
    m = max(2, size // 5)
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return QIcon(pm)


def _ic_pen(color: str, w: float = 1.6) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def _ic_iso_cube(p: QPainter, r: QRectF, *, stroke: str, fill_top: str,
                 fill_left: str, fill_right: str, wire: bool = False) -> None:
    """等距立方体（Initial Condition 区域列表用）。"""
    x0, y0, w, h = r.left(), r.top(), r.width(), r.height()
    top = QPolygon([
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.08)),
        QPoint(int(x0 + w * 0.92), int(y0 + h * 0.28)),
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.48)),
        QPoint(int(x0 + w * 0.08), int(y0 + h * 0.28)),
    ])
    left = QPolygon([
        QPoint(int(x0 + w * 0.08), int(y0 + h * 0.28)),
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.48)),
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.92)),
        QPoint(int(x0 + w * 0.08), int(y0 + h * 0.72)),
    ])
    right = QPolygon([
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.48)),
        QPoint(int(x0 + w * 0.92), int(y0 + h * 0.28)),
        QPoint(int(x0 + w * 0.92), int(y0 + h * 0.72)),
        QPoint(int(x0 + w * 0.5), int(y0 + h * 0.92)),
    ])
    p.setPen(_ic_pen(stroke, 1.2))
    if wire:
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(top)
        p.drawPolygon(left)
        p.drawPolygon(right)
    else:
        p.setBrush(QBrush(QColor(fill_top)))
        p.drawPolygon(top)
        p.setBrush(QBrush(QColor(fill_left)))
        p.drawPolygon(left)
        p.setBrush(QBrush(QColor(fill_right)))
        p.drawPolygon(right)


def _ic_region_icon(kind: str, size: int = 16) -> QIcon:
    """Whole region / volume / special(JOS) 列表图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(1, size // 10)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    if kind == "whole":
        _ic_iso_cube(p, r, stroke="#2e7d32", fill_top="#a5d6a7",
                     fill_left="#66bb6a", fill_right="#43a047", wire=True)
    elif kind == "special":
        p.setPen(_ic_pen("#546e7a", 1.2))
        p.setBrush(QBrush(QColor("#eceff1")))
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width() * 0.38, r.height() * 0.38
        p.drawPolygon(QPolygon([
            QPoint(int(cx), int(cy - h)),
            QPoint(int(cx + w), int(cy)),
            QPoint(int(cx), int(cy + h)),
            QPoint(int(cx - w), int(cy)),
        ]))
    else:
        _ic_iso_cube(p, r, stroke="#1b5e20", fill_top="#c8e6c9",
                     fill_left="#81c784", fill_right="#4caf50", wire=False)
    p.end()
    return QIcon(pm)


def _ic_qmark_box(p: QPainter, r: QRectF, *, stroke="#455a64",
                  fill="#ffffff") -> None:
    p.setPen(_ic_pen(stroke, 1.3))
    p.setBrush(QBrush(QColor(fill)))
    p.drawRoundedRect(r, 2, 2)
    p.setPen(_ic_pen("#1565c0", max(1.2, r.height() * 0.12)))
    p.drawText(r, Qt.AlignCenter, "?")


def _ic_new_condition_icon(kind: str, size: int = 48) -> QIcon:
    """Initial Condition「New condition」示意图标（对齐 scFLOWpre 语义）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)

    if kind == "initial_value":
        # 绿源 → 蓝箭头 → ? 目标
        src = QRectF(r.left(), r.top(), r.width() * 0.42, r.height() * 0.42)
        dst = QRectF(r.right() - r.width() * 0.4, r.bottom() - r.height() * 0.4,
                     r.width() * 0.38, r.height() * 0.38)
        p.setPen(_ic_pen("#2e7d32", 1.4))
        p.setBrush(QBrush(QColor("#81c784")))
        p.drawRoundedRect(src, 3, 3)
        p.setPen(_ic_pen("#1565c0", 2.0))
        p.drawLine(src.bottomRight() - QPointF(2, 2),
                   dst.topLeft() + QPointF(2, 2))
        tip = QPolygon([
            QPoint(int(dst.left() + 1), int(dst.top() - 1)),
            QPoint(int(dst.left() - r.width() * 0.12),
                   int(dst.top() + r.height() * 0.02)),
            QPoint(int(dst.left() + r.width() * 0.02),
                   int(dst.top() + r.height() * 0.14)),
        ])
        p.setBrush(QBrush(QColor("#1565c0")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)
        _ic_qmark_box(p, dst)

    elif kind == "initial_field":
        src = QRectF(r.left(), r.top(), r.width() * 0.42, r.height() * 0.42)
        dst = QRectF(r.right() - r.width() * 0.4, r.bottom() - r.height() * 0.4,
                     r.width() * 0.38, r.height() * 0.38)
        p.setPen(_ic_pen("#b71c1c", 1.4))
        p.setBrush(QBrush(QColor("#ef9a9a")))
        p.drawRoundedRect(src, 3, 3)
        # 场示意：源内网格线
        p.setPen(_ic_pen("#c62828", 1.0))
        p.drawLine(QPointF(src.left() + src.width() * 0.33, src.top() + 2),
                   QPointF(src.left() + src.width() * 0.33, src.bottom() - 2))
        p.drawLine(QPointF(src.left() + 2, src.top() + src.height() * 0.5),
                   QPointF(src.right() - 2, src.top() + src.height() * 0.5))
        p.setPen(_ic_pen("#1565c0", 2.0))
        p.drawLine(src.bottomRight() - QPointF(2, 2),
                   dst.topLeft() + QPointF(2, 2))
        tip = QPolygon([
            QPoint(int(dst.left() + 1), int(dst.top() - 1)),
            QPoint(int(dst.left() - r.width() * 0.12),
                   int(dst.top() + r.height() * 0.02)),
            QPoint(int(dst.left() + r.width() * 0.02),
                   int(dst.top() + r.height() * 0.14)),
        ])
        p.setBrush(QBrush(QColor("#1565c0")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)
        _ic_qmark_box(p, dst)

    elif kind == "les":
        # ? 源 → 蓝目标（湍流注入）
        src = QRectF(r.left(), r.top(), r.width() * 0.38, r.height() * 0.38)
        dst = QRectF(r.right() - r.width() * 0.42, r.bottom() - r.height() * 0.42,
                     r.width() * 0.42, r.height() * 0.42)
        _ic_qmark_box(p, src)
        p.setPen(_ic_pen("#1565c0", 2.0))
        p.drawLine(src.bottomRight() - QPointF(1, 1),
                   dst.topLeft() + QPointF(2, 2))
        tip = QPolygon([
            QPoint(int(dst.left() + 1), int(dst.top() - 1)),
            QPoint(int(dst.left() - r.width() * 0.1),
                   int(dst.top() + r.height() * 0.02)),
            QPoint(int(dst.left() + r.width() * 0.02),
                   int(dst.top() + r.height() * 0.12)),
        ])
        p.setBrush(QBrush(QColor("#1565c0")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)
        p.setPen(_ic_pen("#0d47a1", 1.4))
        p.setBrush(QBrush(QColor("#64b5f6")))
        p.drawRoundedRect(dst, 3, 3)
        # 波浪示意湍流
        p.setPen(_ic_pen("#0d47a1", 1.3))
        path = QPainterPath()
        path.moveTo(dst.left() + 3, dst.center().y())
        path.cubicTo(dst.left() + dst.width() * 0.25, dst.top() + 4,
                     dst.left() + dst.width() * 0.35, dst.bottom() - 4,
                     dst.center().x(), dst.center().y())
        path.cubicTo(dst.left() + dst.width() * 0.65, dst.top() + 4,
                     dst.left() + dst.width() * 0.75, dst.bottom() - 4,
                     dst.right() - 3, dst.center().y())
        p.drawPath(path)

    else:  # jos / thermoregulation — 人形 + 温度计（偏小留白）
        # 内容区略收缩，避免按钮里显得过大
        pad = r.width() * 0.12
        rr = r.adjusted(pad, pad, -pad, -pad)
        p.setPen(_ic_pen("#c62828", 1.5))
        p.setBrush(QBrush(QColor("#fff5f5")))
        p.drawEllipse(rr)
        # 头肩剪影（偏左，为温度计留位）
        cx = rr.center().x() - rr.width() * 0.08
        cy = rr.center().y()
        hw = rr.width() * 0.13
        head = QRectF(cx - hw, cy - rr.height() * 0.34,
                      hw * 2, hw * 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#e53935")))
        p.drawEllipse(head)
        # 肩部梯形，轮廓更清晰
        shoulder = QPainterPath()
        sy = cy + rr.height() * 0.02
        shoulder.moveTo(cx - rr.width() * 0.26, cy + rr.height() * 0.36)
        shoulder.lineTo(cx - rr.width() * 0.22, sy)
        shoulder.quadTo(cx, sy - rr.height() * 0.04,
                        cx + rr.width() * 0.22, sy)
        shoulder.lineTo(cx + rr.width() * 0.26, cy + rr.height() * 0.36)
        shoulder.closeSubpath()
        p.drawPath(shoulder)
        # 右侧小温度计：示意「初始温度」
        tx = rr.right() - rr.width() * 0.28
        ty0 = rr.top() + rr.height() * 0.22
        ty1 = rr.bottom() - rr.height() * 0.28
        tube = QRectF(tx, ty0, rr.width() * 0.10, ty1 - ty0)
        p.setPen(_ic_pen("#1565c0", 1.1))
        p.setBrush(QBrush(QColor("#e3f2fd")))
        p.drawRoundedRect(tube, 2, 2)
        # 汞柱 + 球泡
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#e53935")))
        p.drawRoundedRect(
            QRectF(tube.left() + 1.5, tube.center().y(),
                   tube.width() - 3, tube.bottom() - tube.center().y()),
            1, 1)
        bulb_r = rr.width() * 0.09
        p.drawEllipse(QPointF(tube.center().x(), ty1 + bulb_r * 0.15),
                      bulb_r, bulb_r)

    p.end()
    return QIcon(pm)


_IC_NEW_COND_BUTTONS: list[tuple[str, str]] = [
    ("initial_value", "Initial value"),
    ("initial_field", "Initial field"),
    ("les", "Turbulence of the initial velocity (LES)"),
    ("jos", "Initial temperature of thermoregulation model"),
]


def _flow_bc_icon(kind: str, size: int = 48) -> QIcon:
    """Flow Boundary「New condition」示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)

    def arrows_inout(cx: float, y0: float, y1: float) -> None:
        p.setPen(_ic_pen("#1565c0", 1.8))
        p.setBrush(QBrush(QColor("#1565c0")))
        # 入流（上→下）
        p.drawLine(QPointF(cx - r.width() * 0.18, y0),
                   QPointF(cx - r.width() * 0.18, y1))
        tip_in = QPolygon([
            QPoint(int(cx - r.width() * 0.18), int(y1)),
            QPoint(int(cx - r.width() * 0.26), int(y1 - r.height() * 0.12)),
            QPoint(int(cx - r.width() * 0.10), int(y1 - r.height() * 0.12)),
        ])
        p.drawPolygon(tip_in)
        # 出流（下→上）
        p.drawLine(QPointF(cx + r.width() * 0.18, y1),
                   QPointF(cx + r.width() * 0.18, y0))
        tip_out = QPolygon([
            QPoint(int(cx + r.width() * 0.18), int(y0)),
            QPoint(int(cx + r.width() * 0.10), int(y0 + r.height() * 0.12)),
            QPoint(int(cx + r.width() * 0.26), int(y0 + r.height() * 0.12)),
        ])
        p.drawPolygon(tip_out)

    if kind == "io":
        # 绿色圆柱体 + 进出箭头
        body = QRectF(r.left() + r.width() * 0.22, r.top() + r.height() * 0.22,
                      r.width() * 0.56, r.height() * 0.56)
        p.setPen(_ic_pen("#2e7d32", 1.3))
        p.setBrush(QBrush(QColor("#a5d6a7")))
        p.drawEllipse(QRectF(body.left(), body.top() - body.height() * 0.12,
                             body.width(), body.height() * 0.28))
        p.setBrush(QBrush(QColor("#66bb6a")))
        p.drawRect(QRectF(body.left(), body.top() + body.height() * 0.08,
                          body.width(), body.height() * 0.62))
        p.setBrush(QBrush(QColor("#81c784")))
        p.drawEllipse(QRectF(body.left(), body.bottom() - body.height() * 0.28,
                             body.width(), body.height() * 0.28))
        arrows_inout(r.center().x(), r.top() + 1, r.bottom() - 1)

    elif kind == "liquid_film":
        # 黄色薄板 + 进出箭头
        slab = QPolygon([
            QPoint(int(r.left() + r.width() * 0.12), int(r.bottom() - 4)),
            QPoint(int(r.left() + r.width() * 0.28), int(r.top() + 6)),
            QPoint(int(r.right() - 4), int(r.top() + 6)),
            QPoint(int(r.right() - r.width() * 0.16), int(r.bottom() - 4)),
        ])
        p.setPen(_ic_pen("#ef6c00", 1.3))
        p.setBrush(QBrush(QColor("#ffe082")))
        p.drawPolygon(slab)
        arrows_inout(r.center().x(), r.top() + 2, r.bottom() - 2)

    elif kind == "gtsuite":
        box = r.adjusted(r.width() * 0.12, r.height() * 0.18,
                         -r.width() * 0.12, -r.height() * 0.18)
        p.setPen(_ic_pen("#37474f", 1.4))
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(_ic_pen("#2e7d32", 1.2))
        p.drawText(box, Qt.AlignCenter, "GTS")
        arrows_inout(r.center().x(), r.top() + 1, r.bottom() - 1)

    else:  # dem particle outflow
        box = r.adjusted(r.width() * 0.08, r.height() * 0.08,
                         -r.width() * 0.08, -r.height() * 0.08)
        p.setPen(_ic_pen("#546e7a", 1.4))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(box, 3, 3)
        # 禁止/出流：斜线 + 粒子圆
        p.setPen(_ic_pen("#455a64", 2.0))
        p.drawLine(box.topLeft() + QPointF(4, 4),
                   box.bottomRight() - QPointF(4, 4))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.setPen(_ic_pen("#37474f", 1.2))
        rad = r.width() * 0.12
        p.drawEllipse(QPointF(r.center().x() + r.width() * 0.12,
                              r.center().y() - r.height() * 0.08),
                      rad, rad)
        p.setPen(_ic_pen("#1565c0", 1.8))
        p.setBrush(QBrush(QColor("#1565c0")))
        p.drawLine(QPointF(r.center().x() - r.width() * 0.05, r.bottom() - 3),
                   QPointF(r.center().x() - r.width() * 0.05,
                           r.center().y() + r.height() * 0.05))
        tip = QPolygon([
            QPoint(int(r.center().x() - r.width() * 0.05),
                   int(r.center().y() + r.height() * 0.02)),
            QPoint(int(r.center().x() - r.width() * 0.14),
                   int(r.center().y() + r.height() * 0.18)),
            QPoint(int(r.center().x() + r.width() * 0.04),
                   int(r.center().y() + r.height() * 0.18)),
        ])
        p.drawPolygon(tip)

    p.end()
    return QIcon(pm)


def _flow_sheet_icon(size: int = 16) -> QIcon:
    """表面区域（薄片）列表图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(1, size // 10)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    sheet = QPolygon([
        QPoint(int(r.left() + r.width() * 0.1), int(r.bottom() - 1)),
        QPoint(int(r.left() + r.width() * 0.35), int(r.top() + 1)),
        QPoint(int(r.right() - 1), int(r.top() + 1)),
        QPoint(int(r.right() - r.width() * 0.25), int(r.bottom() - 1)),
    ])
    p.setPen(_ic_pen("#2e7d32", 1.1))
    p.setBrush(QBrush(QColor("#a5d6a7")))
    p.drawPolygon(sheet)
    p.end()
    return QIcon(pm)


_FLOW_BC_NEW_BUTTONS: list[tuple[str, str, str]] = [
    # kind, label, analysis_type gate (empty = always)
    ("io", "Inflow and outflow condition", ""),
    ("liquid_film", "Inflow and outflow condition (Liquid film)", "FreeSurface"),
    ("gtsuite", "GT-SUITE boundary condition", "GT-SUITE"),
    ("dem", "Particle outflow condition (DEM)", "ParticleTracking"),
]

_FLOW_BC_TYPES: list[str] = [
    "Normal velocity",
    "Velocity components",
    "Velocity components (Cylindrical coordinates)",
    "Velocity components (Angles of attack and sideslip)",
    "Mass flow rate",
    "Volume flow rate",
    "Static pressure",
    "Static pressure (Outflow)",
    "Total pressure (Incompressible)",
    "Total pressure (Compressible)",
    "Natural inflow / outflow",
    "Power law velocity",
    "Driver inflow",
]


def _wall_bc_icon(kind: str, size: int = 36) -> QIcon:
    """Wall Boundary「New condition」示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)

    if kind == "stress":
        # 黄色壁角（对齐 scFLOWpre 黄绿折角块）
        # 水平面
        top = QPolygon([
            QPoint(int(r.left() + r.width() * 0.08), int(r.top() + r.height() * 0.55)),
            QPoint(int(r.left() + r.width() * 0.45), int(r.top() + r.height() * 0.35)),
            QPoint(int(r.right() - 2), int(r.top() + r.height() * 0.45)),
            QPoint(int(r.left() + r.width() * 0.55), int(r.top() + r.height() * 0.68)),
        ])
        # 竖直面
        side = QPolygon([
            QPoint(int(r.left() + r.width() * 0.08), int(r.top() + r.height() * 0.55)),
            QPoint(int(r.left() + r.width() * 0.55), int(r.top() + r.height() * 0.68)),
            QPoint(int(r.left() + r.width() * 0.55), int(r.bottom() - 2)),
            QPoint(int(r.left() + r.width() * 0.08), int(r.bottom() - r.height() * 0.18)),
        ])
        p.setPen(_ic_pen("#f9a825", 1.2))
        p.setBrush(QBrush(QColor("#fff59d")))
        p.drawPolygon(top)
        p.setBrush(QBrush(QColor("#fdd835")))
        p.drawPolygon(side)
        # 壁面剪应力示意箭头（沿壁）
        p.setPen(_ic_pen("#1565c0", 1.5))
        p.setBrush(QBrush(QColor("#1565c0")))
        y = r.top() + r.height() * 0.42
        p.drawLine(QPointF(r.left() + r.width() * 0.35, y),
                   QPointF(r.right() - r.width() * 0.12, y - r.height() * 0.06))
        tip = QPolygon([
            QPoint(int(r.right() - r.width() * 0.10),
                   int(y - r.height() * 0.08)),
            QPoint(int(r.right() - r.width() * 0.22),
                   int(y - r.height() * 0.16)),
            QPoint(int(r.right() - r.width() * 0.20),
                   int(y + r.height() * 0.02)),
        ])
        p.drawPolygon(tip)

    elif kind == "particle":
        # 壁面 + 粒子贴附/滑动
        wall = QPolygon([
            QPoint(int(r.left() + 2), int(r.bottom() - 3)),
            QPoint(int(r.left() + r.width() * 0.35), int(r.top() + 4)),
            QPoint(int(r.right() - 2), int(r.top() + 4)),
            QPoint(int(r.right() - r.width() * 0.22), int(r.bottom() - 3)),
        ])
        p.setPen(_ic_pen("#6a1b9a", 1.2))
        p.setBrush(QBrush(QColor("#ce93d8")))
        p.drawPolygon(wall)
        p.setPen(_ic_pen("#37474f", 1.1))
        p.setBrush(QBrush(QColor("#90a4ae")))
        rad = r.width() * 0.12
        p.drawEllipse(QPointF(r.center().x() - r.width() * 0.05,
                              r.center().y() + r.height() * 0.05),
                      rad, rad)
        p.drawEllipse(QPointF(r.center().x() + r.width() * 0.18,
                              r.center().y() - r.height() * 0.08),
                      rad * 0.85, rad * 0.85)

    else:  # restitution
        # 壁面 + 反弹箭头
        wall = QRectF(r.left() + r.width() * 0.55, r.top() + 3,
                      r.width() * 0.35, r.height() - 6)
        p.setPen(_ic_pen("#ef6c00", 1.2))
        p.setBrush(QBrush(QColor("#ffe0b2")))
        p.drawRoundedRect(wall, 2, 2)
        p.setPen(_ic_pen("#1565c0", 1.7))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(r.left() + 3, r.bottom() - r.height() * 0.25)
        path.quadTo(r.center().x(), r.top() + 2,
                    wall.left() - 2, r.center().y() - r.height() * 0.05)
        p.drawPath(path)
        # 反弹离开
        path2 = QPainterPath()
        path2.moveTo(wall.left() - 2, r.center().y() - r.height() * 0.05)
        path2.quadTo(r.center().x() + r.width() * 0.05,
                     r.bottom() - 4,
                     r.left() + r.width() * 0.15, r.bottom() - 2)
        p.drawPath(path2)
        p.setBrush(QBrush(QColor("#1565c0")))
        p.setPen(Qt.NoPen)
        tip = QPolygon([
            QPoint(int(r.left() + r.width() * 0.12), int(r.bottom() - 1)),
            QPoint(int(r.left() + r.width() * 0.28), int(r.bottom() - r.height() * 0.18)),
            QPoint(int(r.left() + r.width() * 0.08), int(r.bottom() - r.height() * 0.16)),
        ])
        p.drawPolygon(tip)

    p.end()
    return QIcon(pm)


_WALL_BC_NEW_BUTTONS: list[tuple[str, str, str]] = [
    # kind, label, analysis_type gate
    ("stress", "Wall shear stress condition", ""),
    ("particle", "Particle boundary condition", "ParticleTracking"),
    ("restitution", "Restitution boundary condition", "ParticleTracking"),
]


def _thermal_bc_icon(kind: str, size: int = 36) -> QIcon:
    """Thermal Boundary「New condition」示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)

    def heat_block(fill: str, stroke: str, wavy: bool = False) -> None:
        block = QRectF(r.left() + r.width() * 0.12, r.top() + r.height() * 0.42,
                       r.width() * 0.76, r.height() * 0.42)
        p.setPen(_ic_pen(stroke, 1.2))
        p.setBrush(QBrush(QColor(fill)))
        p.drawRoundedRect(block, 2, 2)
        # 向上热流箭头
        p.setPen(_ic_pen("#c62828", 1.5))
        p.setBrush(QBrush(QColor("#c62828")))
        xs = (0.28, 0.50, 0.72)
        for xf in xs:
            x = r.left() + r.width() * xf
            y0 = block.top() - 1
            y1 = r.top() + r.height() * 0.12
            if wavy:
                path = QPainterPath()
                path.moveTo(x, y0)
                path.cubicTo(x - 3, (y0 + y1) * 0.5, x + 3, (y0 + y1) * 0.5, x, y1)
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
                p.setBrush(QBrush(QColor("#c62828")))
            else:
                p.drawLine(QPointF(x, y0), QPointF(x, y1 + 4))
            tip = QPolygon([
                QPoint(int(x), int(y1)),
                QPoint(int(x - r.width() * 0.07), int(y1 + r.height() * 0.14)),
                QPoint(int(x + r.width() * 0.07), int(y1 + r.height() * 0.14)),
            ])
            p.drawPolygon(tip)

    if kind == "heat":
        heat_block("#fff59d", "#f9a825", wavy=False)
    elif kind == "porous":
        heat_block("#a5d6a7", "#2e7d32", wavy=False)
        # 多孔示意点
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#66bb6a")))
        blk = QRectF(r.left() + r.width() * 0.12, r.top() + r.height() * 0.42,
                     r.width() * 0.76, r.height() * 0.42)
        for i in range(3):
            for j in range(2):
                p.drawEllipse(
                    QPointF(blk.left() + blk.width() * (0.25 + i * 0.25),
                            blk.top() + blk.height() * (0.35 + j * 0.3)),
                    1.6, 1.6)
    elif kind == "radiation":
        heat_block("#ef9a9a", "#c62828", wavy=True)
    else:  # solar
        # 太阳
        cx = r.center().x()
        cy = r.top() + r.height() * 0.32
        rad = r.width() * 0.16
        p.setPen(_ic_pen("#ef6c00", 1.2))
        p.setBrush(QBrush(QColor("#ffcc80")))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(_ic_pen("#ef6c00", 1.4))
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            p.drawLine(
                QPointF(cx + math.cos(a) * rad * 1.15,
                        cy + math.sin(a) * rad * 1.15),
                QPointF(cx + math.cos(a) * rad * 1.55,
                        cy + math.sin(a) * rad * 1.55))
        # 地面
        ground = QRectF(r.left() + r.width() * 0.1, r.bottom() - r.height() * 0.28,
                        r.width() * 0.8, r.height() * 0.18)
        p.setPen(_ic_pen("#546e7a", 1.1))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(ground, 2, 2)
        # 下行光线
        p.setPen(_ic_pen("#ef6c00", 1.3))
        for xf in (0.35, 0.50, 0.65):
            p.drawLine(QPointF(r.left() + r.width() * xf, cy + rad + 2),
                       QPointF(r.left() + r.width() * xf, ground.top() - 1))

    p.end()
    return QIcon(pm)


def _sym_bc_icon(kind: str = "flow", size: int = 36) -> QIcon:
    """Symmetrical Boundary 示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    # 中间对称线
    mid = r.center().x()
    p.setPen(_ic_pen("#455a64", 1.2))
    p.drawLine(QPointF(mid, r.top() + 2), QPointF(mid, r.bottom() - 2))
    # 左右镜像块
    left = QRectF(r.left() + 2, r.top() + r.height() * 0.18,
                  r.width() * 0.32, r.height() * 0.45)
    right = QRectF(r.right() - r.width() * 0.32 - 2, r.top() + r.height() * 0.18,
                   r.width() * 0.32, r.height() * 0.45)
    if kind == "particle":
        fills = ("#b0bec5", "#90caf9")
    elif kind == "thermal":
        fills = ("#ffcc80", "#ef9a9a")
    else:
        fills = ("#b0bec5", "#90caf9")
    p.setPen(_ic_pen("#37474f", 1.1))
    p.setBrush(QBrush(QColor(fills[0])))
    p.drawRoundedRect(left, 2, 2)
    p.setBrush(QBrush(QColor(fills[1])))
    p.drawRoundedRect(right, 2, 2)
    # 底部双向弧箭头
    p.setPen(_ic_pen("#1565c0", 1.6))
    p.setBrush(Qt.NoBrush)
    arc = QRectF(r.left() + r.width() * 0.15, r.bottom() - r.height() * 0.45,
                 r.width() * 0.7, r.height() * 0.4)
    p.drawArc(arc.toRect(), 20 * 16, 140 * 16)
    p.setBrush(QBrush(QColor("#1565c0")))
    p.setPen(Qt.NoPen)
    # 左右箭头尖
    p.drawPolygon(QPolygon([
        QPoint(int(arc.left()), int(arc.center().y())),
        QPoint(int(arc.left() + 6), int(arc.center().y() - 5)),
        QPoint(int(arc.left() + 6), int(arc.center().y() + 5)),
    ]))
    p.drawPolygon(QPolygon([
        QPoint(int(arc.right()), int(arc.center().y())),
        QPoint(int(arc.right() - 6), int(arc.center().y() - 5)),
        QPoint(int(arc.right() - 6), int(arc.center().y() + 5)),
    ]))
    p.end()
    return QIcon(pm)


def _periodic_bc_icon(size: int = 36) -> QIcon:
    """Periodic Boundary 示意图标：两面 + 循环箭头。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    a = QRectF(r.left(), r.top() + r.height() * 0.15,
               r.width() * 0.28, r.height() * 0.7)
    b = QRectF(r.right() - r.width() * 0.28, r.top() + r.height() * 0.15,
               r.width() * 0.28, r.height() * 0.7)
    p.setPen(_ic_pen("#6a1b9a", 1.2))
    p.setBrush(QBrush(QColor("#ce93d8")))
    p.drawRoundedRect(a, 2, 2)
    p.setBrush(QBrush(QColor("#ab47bc")))
    p.drawRoundedRect(b, 2, 2)
    # 循环箭头
    p.setPen(_ic_pen("#1565c0", 1.7))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(r.left() + r.width() * 0.22, r.top() + r.height() * 0.2,
                     r.width() * 0.56, r.height() * 0.6).toRect(),
              40 * 16, 280 * 16)
    p.setBrush(QBrush(QColor("#1565c0")))
    p.setPen(Qt.NoPen)
    cx, cy = r.center().x(), r.center().y()
    tip = QPolygon([
        QPoint(int(cx + r.width() * 0.28), int(cy - r.height() * 0.08)),
        QPoint(int(cx + r.width() * 0.12), int(cy - r.height() * 0.28)),
        QPoint(int(cx + r.width() * 0.32), int(cy - r.height() * 0.26)),
    ])
    p.drawPolygon(tip)
    p.end()
    return QIcon(pm)


_THERMAL_BC_NEW_BUTTONS: list[tuple[str, str, str]] = [
    ("heat", "Wall heat transfer condition", ""),
    ("porous", "Wall heat transfer condition (Porous media)", "PorousMedia"),
    ("radiation", "Radiation boundary condition", "Radiation"),
    ("solar", "Solar radiation boundary condition", "Solar"),
]

_SYM_BC_NEW_BUTTONS: list[tuple[str, str, str]] = [
    ("flow", "Symmetrical boundary condition", ""),
    ("particle", "Particle symmetrical boundary condition (DEM)",
     "ParticleTracking"),
    ("thermal", "Particle symmetrical thermal boundary condition (DEM)",
     "ParticleTracking"),
]


def _source_bc_icon(kind: str, size: int = 36) -> QIcon:
    """Source Condition「New condition」示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)

    def draw_out_arrows(cx: float, cy: float, span: float,
                        color: str = "#ef6c00") -> None:
        p.setPen(_ic_pen(color, 1.5))
        p.setBrush(QBrush(QColor(color)))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            x0 = cx + dx * span * 0.15
            y0 = cy + dy * span * 0.15
            x1 = cx + dx * span * 0.48
            y1 = cy + dy * span * 0.48
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            tip = QPolygon([
                QPoint(int(x1), int(y1)),
                QPoint(int(x1 - dy * 3 - dx * 4), int(y1 - dx * 3 - dy * 4)),
                QPoint(int(x1 + dy * 3 - dx * 4), int(y1 + dx * 3 - dy * 4)),
            ])
            p.drawPolygon(tip)

    if kind == "source":
        cube = QRectF(r.left() + r.width() * 0.18, r.top() + r.height() * 0.18,
                      r.width() * 0.64, r.height() * 0.64)
        p.setPen(_ic_pen("#c62828", 1.2))
        p.setBrush(QBrush(QColor("#ef5350")))
        p.drawRoundedRect(cube, 2, 2)
        draw_out_arrows(cube.center().x(), cube.center().y(),
                        min(cube.width(), cube.height()))
    elif kind == "area":
        # 斜面 + 向上箭头
        path = QPainterPath()
        path.moveTo(r.left() + r.width() * 0.12, r.bottom() - r.height() * 0.28)
        path.lineTo(r.left() + r.width() * 0.28, r.top() + r.height() * 0.45)
        path.lineTo(r.right() - r.width() * 0.12, r.top() + r.height() * 0.35)
        path.lineTo(r.right() - r.width() * 0.28, r.bottom() - r.height() * 0.38)
        path.closeSubpath()
        p.setPen(_ic_pen("#c62828", 1.2))
        p.setBrush(QBrush(QColor("#ef5350")))
        p.drawPath(path)
        p.setPen(_ic_pen("#ef6c00", 1.5))
        p.setBrush(QBrush(QColor("#ef6c00")))
        for xf in (0.35, 0.50, 0.65):
            x = r.left() + r.width() * xf
            y0 = r.top() + r.height() * 0.42
            y1 = r.top() + r.height() * 0.12
            p.drawLine(QPointF(x, y0), QPointF(x, y1 + 3))
            p.drawPolygon(QPolygon([
                QPoint(int(x), int(y1)),
                QPoint(int(x - 3), int(y1 + 5)),
                QPoint(int(x + 3), int(y1 + 5)),
            ]))
    elif kind in ("mass_vol", "mass_face"):
        # 灰云
        p.setPen(_ic_pen("#78909c", 1.1))
        p.setBrush(QBrush(QColor("#b0bec5")))
        cy = r.center().y() - (r.height() * 0.08 if kind == "mass_face" else 0)
        p.drawEllipse(QPointF(r.center().x() - r.width() * 0.12, cy),
                      r.width() * 0.18, r.height() * 0.14)
        p.drawEllipse(QPointF(r.center().x() + r.width() * 0.1, cy),
                      r.width() * 0.2, r.height() * 0.15)
        p.drawEllipse(QPointF(r.center().x(), cy - r.height() * 0.08),
                      r.width() * 0.16, r.height() * 0.13)
        if kind == "mass_face":
            base = QRectF(r.left() + r.width() * 0.18,
                          r.bottom() - r.height() * 0.28,
                          r.width() * 0.64, r.height() * 0.16)
            p.setPen(_ic_pen("#546e7a", 1.1))
            p.setBrush(QBrush(QColor("#90a4ae")))
            p.drawRoundedRect(base, 2, 2)
            p.setPen(_ic_pen("#455a64", 1.2))
            for xf in (0.3, 0.5, 0.7):
                x = r.left() + r.width() * xf
                p.drawLine(QPointF(x, base.top()),
                           QPointF(x, base.top() - r.height() * 0.08))
    elif kind == "pdrop_vol":
        cube = QRectF(r.left() + r.width() * 0.18, r.top() + r.height() * 0.18,
                      r.width() * 0.64, r.height() * 0.64)
        p.setPen(_ic_pen("#2e7d32", 1.2))
        p.setBrush(QBrush(QColor("#81c784")))
        p.drawRoundedRect(cube, 2, 2)
        p.setPen(_ic_pen("#1b5e20", 1.0))
        for i in range(1, 4):
            x = cube.left() + cube.width() * i / 4
            y = cube.top() + cube.height() * i / 4
            p.drawLine(QPointF(x, cube.top()), QPointF(x, cube.bottom()))
            p.drawLine(QPointF(cube.left(), y), QPointF(cube.right(), y))
    elif kind == "pdrop_face":
        face = QRectF(r.left() + r.width() * 0.15, r.top() + r.height() * 0.28,
                      r.width() * 0.7, r.height() * 0.44)
        p.setPen(_ic_pen("#2e7d32", 1.2))
        p.setBrush(QBrush(QColor("#a5d6a7")))
        p.drawRoundedRect(face, 2, 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#2e7d32")))
        for i in range(3):
            for j in range(2):
                p.drawEllipse(
                    QPointF(face.left() + face.width() * (0.25 + i * 0.25),
                            face.top() + face.height() * (0.35 + j * 0.3)),
                    1.8, 1.8)
    elif kind == "accel":
        # 速度表
        cx, cy = r.center().x(), r.center().y()
        rad = r.width() * 0.32
        p.setPen(_ic_pen("#1565c0", 1.4))
        p.setBrush(QBrush(QColor("#90caf9")))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setBrush(QBrush(QColor("#e3f2fd")))
        p.drawEllipse(QPointF(cx, cy), rad * 0.72, rad * 0.72)
        p.setPen(_ic_pen("#0d47a1", 1.6))
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + rad * 0.55, cy - rad * 0.35))
        p.setBrush(QBrush(QColor("#0d47a1")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)
    else:  # friction
        # 销 + 红板 + 热线
        pin = QRectF(r.center().x() - r.width() * 0.1,
                     r.top() + r.height() * 0.1,
                     r.width() * 0.2, r.height() * 0.55)
        p.setPen(_ic_pen("#ef6c00", 1.1))
        p.setBrush(QBrush(QColor("#ffb74d")))
        p.drawRoundedRect(pin, 2, 2)
        plate = QRectF(r.left() + r.width() * 0.12,
                       r.center().y() + r.height() * 0.05,
                       r.width() * 0.76, r.height() * 0.16)
        p.setPen(_ic_pen("#c62828", 1.1))
        p.setBrush(QBrush(QColor("#ef5350")))
        p.drawRoundedRect(plate, 2, 2)
        p.setPen(_ic_pen("#ef6c00", 1.3))
        p.setBrush(Qt.NoBrush)
        for xf in (0.28, 0.50, 0.72):
            x = r.left() + r.width() * xf
            path = QPainterPath()
            y0 = plate.bottom() + 1
            y1 = r.bottom() - 2
            path.moveTo(x, y0)
            path.cubicTo(x - 3, (y0 + y1) * 0.5, x + 3, (y0 + y1) * 0.5, x, y1)
            p.drawPath(path)

    p.end()
    return QIcon(pm)


def _fixed_bc_icon(size: int = 36) -> QIcon:
    """Fixed Condition 示意图标：灰底 + 顶部红色固定块。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    base = QRectF(r.left() + r.width() * 0.12, r.top() + r.height() * 0.42,
                  r.width() * 0.76, r.height() * 0.4)
    p.setPen(_ic_pen("#546e7a", 1.2))
    p.setBrush(QBrush(QColor("#b0bec5")))
    p.drawRoundedRect(base, 2, 2)
    top = QRectF(r.left() + r.width() * 0.28, r.top() + r.height() * 0.18,
                 r.width() * 0.44, r.height() * 0.28)
    p.setPen(_ic_pen("#c62828", 1.2))
    p.setBrush(QBrush(QColor("#ef5350")))
    p.drawRoundedRect(top, 2, 2)
    # 固定钉示意
    p.setPen(_ic_pen("#b71c1c", 1.3))
    p.drawLine(QPointF(top.center().x(), top.top() + 2),
               QPointF(top.center().x(), base.top() + 2))
    p.end()
    return QIcon(pm)


_SOURCE_BC_NEW_BUTTONS: list[tuple[str, str, str]] = [
    ("source", "Source condition", ""),
    ("area", "Area source condition", ""),
    ("mass_vol", "Mass source condition (Volume)", "mixed_gas"),
    ("mass_face", "Mass source condition (Face)", "mixed_gas"),
    ("pdrop_vol", "Pressure drop (Volume)", ""),
    ("pdrop_face", "Pressure drop (Face)", ""),
    ("accel", "Acceleration condition", ""),
    ("friction", "Frictional heat", ""),
]

_SOURCE_BC_TYPES: dict[str, list[str]] = {
    "source": [
        "Constant source (per unit volume)",
        "Constant source (total)",
        "Proportional to difference from base value",
        "Proportional to difference from base value (User definition)",
        "Mapping of external source term",
    ],
    "area": [
        "Constant source (per unit area)",
        "Constant source (total)",
        "Proportional to difference from base value",
        "Proportional to difference from base value (User definition)",
        "Mapping of external source term",
    ],
    "mass_vol": [
        "Constant source (per unit volume)",
        "Constant source (total)",
    ],
    "mass_face": [
        "Constant source (per unit area)",
        "Constant source (total)",
    ],
    "pdrop_vol": ["Isotropic", "Anisotropic"],
    "pdrop_face": ["Isotropic", "Anisotropic"],
    "accel": ["Acceleration"],
    "friction": ["Frictional heat"],
}


# Analysis Control 子导航：(key, label, children|None)
# children 为 None 表示叶子；有 children 则为分组
_AC_NAV_TREE: list[tuple[str, str, Optional[list[tuple[str, str]]]]] = [
    ("batch", "Batch Setting", None),
    ("stab", "Parameter of Stabilization", [
        ("undr", "Under-Relaxation Coefficient"),
        ("dtsr", "Pseudo Time Step Relaxation"),
        ("stab_v", "Avoidance of Divergence (Variable)"),
        ("stab_e", "Avoidance of Divergence (Elements)"),
    ]),
    ("loop_grp", "Loop", [
        ("loop", "Loop"),
        ("loop_eq", "Loop (Equation)"),
    ]),
    ("disc", "Discretization Accuracy", [
        ("upwd", "Accuracy of Convective Terms"),
        ("time_acc", "Accuracy of Time Derivative Term"),
        ("gradient", "Gradient Calculation"),
        ("diffusion", "Diffusion Term"),
    ]),
    ("solv", "Matrix Solvers", None),
    ("sted", "Convergence Criteria", None),
    ("pcty", "Pressure Computation Method", None),
    ("restart", "Restart", None),
    ("mapping", "Mapping", None),
    ("opts", "Options", [
        ("turb", "Turbulent flow"),
        ("equa", "Equation"),
        ("bund", "Boundary Condition"),
        ("geometry", "Element Geometry"),
        ("perf", "Performance Improvement"),
        ("mesh", "Mesh"),
        ("domain", "Domain partitioning"),
    ]),
]

_AC_LOOP_VARS: list[str] = [
    "X-component of momentum",
    "Y-component of momentum",
    "Z-component of momentum",
    "Pressure",
    "Temperature",
    "Turbulent kinetic energy",
    "Turbulent dissipation rate",
    "Eddy frequency",
    "Volume fraction of vapor",
    "Volume of fluid",
    "Electric potential",
    "Volume fraction of fluid",
    "Population balance",
    "Combustion",
]

_AC_UNDR_ROWS: list[tuple[str, str, float]] = [
    ("Momentum", "undr_momentum", 0.8),
    ("Energy", "undr_energy", 0.9),
    ("Energy (Incompressible fluid)", "undr_energy_incomp", 0.9),
    ("Energy (Solid)", "undr_energy_solid", 0.9),
    ("Energy (Compressible fluid)", "undr_energy_comp", 0.9),
    ("Energy (Porous media)", "undr_energy_porous", 0.9),
    ("Pressure", "undr_pressure", 0.4),
    ("Density", "undr_density", 0.5),
    ("Turbulence", "undr_turbulence", 0.7),
    ("Diffusion", "undr_diffusive_species", 0.9),
    ("Volume of fluid", "undr_vof", 0.9),
    ("Volume fraction (multiphase flow)", "undr_fvf", 0.9),
    ("Cavitation", "undr_cavi", 0.7),
    ("Population balance", "undr_pbe", 0.9),
    ("LOGE CPV (Combustion)", "undr_comb", 0.9),
]

_AC_LOOP_EQ_ROWS: list[tuple[str, str, str]] = [
    ("Momentum", "Default (1)", "Default (0.0001)"),
    ("Mass", "Default (1)", "Default (0.0001)"),
    ("Energy", "Default (1)", "Default (0.0001)"),
    ("Turbulence", "Default (1)", "Default (0.0001)"),
    ("Diffusion", "Default (1)", "Default (0.0001)"),
    ("Volume of fluid", "Default (1)", "Default (0.0001)"),
    ("Cavitation", "Default (1)", "Default (0.0001)"),
    ("Electric current", "Default (20)", "Default (1e-08)"),
]

_AC_UPWD_ROWS: list[tuple[str, str]] = [
    ("Momentum", "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Energy", "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Turbulence", "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Diffusion", "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Volume of fluid", "Default (2nd order (SMART))"),
    ("Cavitation", "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Volume fraction (multiphase flow)",
     "Default (Blending scheme (1st upwind + 2nd upwind))"),
    ("Population balance",
     "Default (Blending scheme (1st upwind + 2nd upwind))"),
]

_AC_UPWD_SCHEMES: list[str] = [
    "1st order",
    "2nd order (MUSCL)",
    "2nd order (QUICK)",
    "Blended upwind scheme of 1st and 2nd order",
    "2nd order (SMART)",
]

_AC_STED_CRITERIA: list[tuple[str, str]] = [
    ("X-component of momentum", "Evaluate convergence / 0.0001"),
    ("Y-component of momentum", "Default (Criterion = 0.0001)"),
    ("Z-component of momentum", "Default (Criterion = 0.0001)"),
    ("Pressure", "Evaluate convergence / 0.0001"),
    ("Temperature", "Evaluate convergence / 0.0001"),
    ("Turbulent kinetic energy", "Default (Criterion = 0.0001)"),
    ("Turbulent dissipation rate", "Default (Criterion = 0.0001)"),
    ("Volume of fluid", "Default (Criterion = 0.001)"),
    ("Cavitation", "Default (Criterion = 0.0001)"),
]


def _optional_cond_icon(kind: str, size: int = 36) -> QIcon:
    """Optional Conditions「New / Edit」示意图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(2, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    if kind == "created":
        # 条件列表剪贴板
        p.setPen(_ic_pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#bbdefb")))
        p.drawRoundedRect(r.adjusted(2, 4, -2, -2), 2, 2)
        p.setPen(_ic_pen("#0d47a1", 1.2))
        for i in range(3):
            y = r.top() + r.height() * (0.35 + i * 0.18)
            p.drawLine(QPointF(r.left() + 6, y), QPointF(r.right() - 6, y))
    elif kind == "table":
        p.setPen(_ic_pen("#2e7d32", 1.2))
        p.setBrush(QBrush(QColor("#c8e6c9")))
        p.drawRoundedRect(r.adjusted(2, 4, -2, -2), 2, 2)
        p.setPen(_ic_pen("#1b5e20", 1.0))
        for i in range(1, 3):
            x = r.left() + r.width() * i / 3
            y = r.top() + r.height() * i / 3
            p.drawLine(QPointF(x, r.top() + 4), QPointF(x, r.bottom() - 4))
            p.drawLine(QPointF(r.left() + 4, y), QPointF(r.right() - 4, y))
    elif kind == "script":
        p.setPen(_ic_pen("#6a1b9a", 1.2))
        p.setBrush(QBrush(QColor("#e1bee7")))
        p.drawRoundedRect(r.adjusted(2, 4, -2, -2), 2, 2)
        p.setPen(_ic_pen("#4a148c", 1.3))
        p.drawText(r.adjusted(4, 2, -4, -2), Qt.AlignCenter, "{ }")
    elif kind == "udf":
        p.setPen(_ic_pen("#e65100", 1.2))
        p.setBrush(QBrush(QColor("#ffe0b2")))
        p.drawRoundedRect(r.adjusted(2, 4, -2, -2), 2, 2)
        p.setPen(_ic_pen("#bf360c", 1.4))
        p.drawText(r, Qt.AlignCenter, "f(x)")
    elif kind == "mapping":
        a = QRectF(r.left(), r.top() + 4, r.width() * 0.4, r.height() * 0.7)
        b = QRectF(r.right() - r.width() * 0.4, r.top() + 8,
                   r.width() * 0.4, r.height() * 0.7)
        p.setPen(_ic_pen("#00695c", 1.2))
        p.setBrush(QBrush(QColor("#80cbc4")))
        p.drawRoundedRect(a, 2, 2)
        p.setBrush(QBrush(QColor("#4db6ac")))
        p.drawRoundedRect(b, 2, 2)
        p.setPen(_ic_pen("#004d40", 1.5))
        p.drawLine(QPointF(a.right(), a.center().y()),
                   QPointF(b.left(), b.center().y()))
    elif kind == "connect":
        p.setPen(_ic_pen("#37474f", 1.3))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(
            QRectF(r.left() + 2, r.top() + r.height() * 0.2,
                   r.width() * 0.35, r.height() * 0.6), 2, 2)
        p.drawRoundedRect(
            QRectF(r.right() - r.width() * 0.35 - 2, r.top() + r.height() * 0.2,
                   r.width() * 0.35, r.height() * 0.6), 2, 2)
        p.setPen(_ic_pen("#1565c0", 1.6))
        mid_y = r.center().y()
        p.drawLine(QPointF(r.left() + r.width() * 0.38, mid_y),
                   QPointF(r.right() - r.width() * 0.38, mid_y))
    else:  # unsupported
        p.setPen(_ic_pen("#c62828", 1.2))
        p.setBrush(QBrush(QColor("#ffcdd2")))
        p.drawEllipse(r.center(), r.width() * 0.35, r.height() * 0.35)
        p.setPen(_ic_pen("#b71c1c", 2.0))
        p.drawLine(QPointF(r.left() + r.width() * 0.28, r.top() + r.height() * 0.28),
                   QPointF(r.right() - r.width() * 0.28, r.bottom() - r.height() * 0.28))
    p.end()
    return QIcon(pm)


def _file_type_icon(tag: str, size: int = 16) -> QIcon:
    """File Name 行类型图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    colors = {
        "sph": "#1565c0", "gph": "#2e7d32", "fph": "#6a1b9a",
        "rph": "#ef6c00", "etco": "#455a64",
    }
    col = colors.get(tag, "#607d8b")
    p.setPen(_ic_pen(col, 1.1))
    p.setBrush(QBrush(QColor(col)))
    p.setOpacity(0.85)
    p.drawRoundedRect(2, 1, size - 4, size - 3, 2, 2)
    p.setOpacity(1.0)
    p.setPen(_ic_pen("#ffffff", 1.0))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter,
               (tag or "?")[:1].upper())
    p.end()
    return QIcon(pm)


_OUT_FIELD_NAV: list[tuple[str, str]] = [
    ("fph_setting", "Output Setting of Analysis Data"),
    ("fph_surface", "Surface Data"),
    ("fph_vars", "Variables"),
    ("fph_partial", "Partial Graphic (FPH) File"),
    ("fph_avg", "Averaging"),
    ("fph_tf", "Time-Frequency Analysis Output"),
    ("fph_elem", "Element Information (Measures Against Divergence)"),
    ("fph_opts", "Options"),
]

_OUT_LIST_NAV: list[tuple[str, str]] = [
    ("list_check", "Check Output"),
    ("list_region", "Region Output"),
    ("list_passage", "Region Output (Passage)"),
    ("list_scalar", "Region Output (Scalar Flux)"),
    ("list_force", "Output Surface Force"),
    ("list_moment", "Output Surface Moment"),
    ("list_yplus", "Non-Dimensional Distance from Wall Distribution"),
    ("list_ang", "Angular Momentum"),
    ("list_turbo", "Turbomachinery Performance"),
    ("list_load", "Load Distribution"),
    ("list_iter", "Information during Iterations"),
    ("list_elem_e", "Element Information (Measures Against Divergence: Elements)"),
    ("list_elem_v", "Element Information (Measures Against Divergence: Variables)"),
    ("list_opts", "Options"),
]

_OUT_OTHER_NAV: list[tuple[str, str]] = [
    ("oth_series", "Time Series"),
    ("oth_coord", "Coordinate - Variable"),
    ("oth_restart", "Restart File"),
    ("oth_heat", "Heat Path Data File"),
    ("oth_noise", "FlowNoise File"),
    ("oth_ring", "RingDipoles File"),
]

_OPTIONAL_NEW_BUTTONS: list[tuple[str, str]] = [
    ("created", "Created Condition"),
    ("table", "Table"),
    ("script", "Script"),
    ("udf", "User Defined Function"),
    ("mapping", "Mapping Conditions"),
    ("connect", "Connection of Two Sides of the Faces"),
    ("unsupported", "Unsupported Conditions"),
]

_FPH_VAR_ROWS: list[tuple[str, str]] = [
    ("Velocity vector", "Default (Output in case of analysis)"),
    ("Static pressure", "Default (Output in case of analysis)"),
    ("Total pressure", "Default (Do not output)"),
    ("Temperature", "Default (Output in case of analysis)"),
    ("Turbulent kinetic energy", "Default (Output in case of analysis)"),
    ("Turbulent dissipation rate", "Default (Output in case of analysis)"),
    ("Eddy frequency", "Default (Output in case of analysis)"),
    ("Density", "Default (Output in case of analysis)"),
    ("Mach number", "Default (Do not output)"),
    ("Y+", "Default (Output in case of analysis)"),
]

_LIST_CHECK_ROWS: list[tuple[str, str]] = [
    ("Residual of continuity equation", "Default"),
    ("Residual of momentum equation", "Default"),
    ("Residual of energy equation", "Default"),
    ("Residual of turbulence equation", "Default"),
    ("Maximum Courant number", "Default"),
]

_LIST_OPT_ROWS: list[tuple[str, str]] = [
    ("Output of flow rate", "Default (Output)"),
    ("Output of min/max values", "Default (Output)"),
    ("Output of non-dimensional distance from wall",
     "Default (Output in case of turbulence)"),
    ("Output of heat balance information", "Default (only in thermal)"),
    ("Output of matrix solver convergence", "Default (Output)"),
]


def _ac_nav_icon(kind: str = "leaf", size: int = 16) -> QIcon:
    """Analysis Control 子导航图标（文件夹 / 蓝圆叶子）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    m = max(1, size // 16)
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    if kind == "folder":
        # 黄文件夹
        body = QRectF(r.left(), r.top() + r.height() * 0.28,
                      r.width(), r.height() * 0.62)
        tab = QRectF(r.left(), r.top() + r.height() * 0.12,
                     r.width() * 0.45, r.height() * 0.22)
        p.setPen(_ic_pen("#f9a825", 1.0))
        p.setBrush(QBrush(QColor("#ffe082")))
        p.drawRoundedRect(tab, 1, 1)
        p.setBrush(QBrush(QColor("#ffca28")))
        p.drawRoundedRect(body, 1.5, 1.5)
    else:
        cx, cy = r.center().x(), r.center().y()
        rad = min(r.width(), r.height()) * 0.28
        p.setPen(_ic_pen("#1565c0", 1.1))
        p.setBrush(QBrush(QColor("#42a5f5")))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setBrush(QBrush(QColor("#e3f2fd")))
        p.drawEllipse(QPointF(cx, cy), rad * 0.45, rad * 0.45)
    p.end()
    return QIcon(pm)


def _xml_bool(text: Optional[str], default: bool = False) -> bool:
    if text is None:
        return default
    return str(text).strip().lower() in ("true", "1", "yes")


def _set_xml_bool(parent: ET.Element, tag: str, on: bool) -> None:
    _ensure_child_text(parent, tag, "true" if on else "false")


def _bp_get_const(bp: ET.Element, tag: str, default: float = 0.0) -> float:
    el = bp.find(tag)
    if el is None:
        return default
    try:
        return float(el.findtext("const_value") or default)
    except ValueError:
        return default


def _bp_set_const(bp: ET.Element, tag: str, value: float,
                  unit: str = "s") -> None:
    el = bp.find(tag)
    if el is None:
        el = ET.SubElement(bp, tag)
    _ensure_child_text(el, "type", el.findtext("type") or "0")
    _ensure_child_text(el, "mapping_type", el.findtext("mapping_type") or "0")
    _ensure_child_text(el, "const_value", _fmt_float(value))
    if el.find("input") is None:
        ET.SubElement(el, "input")
    _ensure_child_text(el, "udf_script_id",
                       el.findtext("udf_script_id") or "1")
    _ensure_child_text(el, "unit", unit)


def _set_combo_data_bool(cb: QComboBox, on: bool) -> None:
    _set_combo_data(cb, "true" if on else "false")


# Analysis Type 复选框：UI 标签 → main.xml <analysis_type> 子标签
_ANALYSIS_TYPE_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Flow", [("Flow", "Flow")]),
    ("Heat", [
        ("Heat", "Heat"), ("Radiation", "Radiation"),
        ("Solar radiation", "Solar"),
    ]),
    ("Rotation, translation", [
        ("Moving elements", "Moving"),
        ("Discontinuous mesh", "Discontinuous"),
        ("Overset mesh", "overset"),
    ]),
    ("Diffusion", [
        ("Diffusive species", "passive_scalar"),
        ("Humidity", "humidity"),
        ("Mixed gas", "mixed_gas"),
        ("Chemical reaction", "chemical_reaction"),
    ]),
    ("Multiphase flow", [
        ("Particle tracking", "ParticleTracking"),
        ("Spray", "Spray"),
        ("Dispersed multiphase flow", "MultiPhase"),
        ("Free surface", "FreeSurface"),
        ("Cavitation", "cavitation"),
        ("Solidification / Melting", "solidification"),
    ]),
    ("Modelization", [
        ("Fan/Propeller model", "fan"),
        ("Porous media", "PorousMedia"),
    ]),
    ("Other physical model", [
        ("Electric current", "electric"),
        ("Electric field", "electric_field"),
        ("LOGE CPV (Combustion Model)", "LOGE_CPV"),
        ("Thermoregulation model", "JOS"),
        ("Aerodynamic sound", "AerodynamicSound"),
        ("Battery model", "BatteryModel"),
    ]),
    ("MSC CoSim", [
        ("Structural coupled", "cosim_structure"),
        ("Mechanism coupled (Adams)", "cosim_move"),
    ]),
    ("Other co-simulation", [
        ("GT-SUITE", "GT-SUITE"),
        ("FMI", "FMI"),
    ]),
]

# 向导叶节点顺序（Back / Next）
_COND_WIZARD_LEAVES: list[tuple[str, str]] = [
    ("analysis_type", "Analysis Type"),
    ("basic_setting", "Basic Setting"),
    ("initial", "Initial Condition"),
    ("bc_flow", "Flow Boundary"),
    ("bc_wall", "Wall Boundary"),
    ("bc_thermal", "Thermal Boundary"),
    ("bc_sym", "Symmetrical Boundary"),
    ("bc_periodic", "Periodic Boundary"),
    ("source", "Source Condition"),
    ("fixed", "Fixed Condition"),
    ("analysis_control", "Analysis Control"),
    ("out_field", "Output of Field File"),
    ("out_list", "Output of List File"),
    ("out_other", "Other Output"),
    ("file_name", "File Name"),
    ("optional", "Optional Conditions"),
]

_BC_TYPE_FILTER: dict[str, frozenset[str]] = {
    "bc_flow": frozenset({"CondBoundaryFlowIO"}),
    "bc_wall": frozenset({
        "CondBoundaryWallStress", "CondBoundaryWallThermal"}),
    "bc_thermal": frozenset({"CondBoundaryWallThermal"}),
    "bc_sym": frozenset({"CondBoundarySymmetry", "SymmetricalBoundary"}),
    "bc_periodic": frozenset({"CondBoundaryPeriodic", "PeriodicBoundary"}),
    "source": frozenset({"CondSource"}),
    "fixed": frozenset({"CondFix"}),
    "initial": frozenset({
        "CondInitial", "CondInitialValue", "CondInitialField",
        "InitialCondition"}),
}

# 合并 schemas/conditions.yaml（若存在）扩展 Cond* 过滤器
try:
    from conditions_schema import load_bc_filters as _load_bc_filters
    for _k, _types in _load_bc_filters().items():
        _BC_TYPE_FILTER[_k] = frozenset(
            set(_BC_TYPE_FILTER.get(_k, frozenset())) | set(_types))
except Exception:  # noqa: BLE001
    pass


class SolverSettingsDialog(QDialog):
    """条件树驱动的求解设置编辑器（P4-0）。

    数据来自厂商 ``scflow_main.xml`` 解析出的
    ``schemas/condition_tree.json``（9 大类 / 10 section / 349 变量，
    含英/日显示名、单位键、依赖条件）。左侧类别树选 section，右侧
    渲染变量表单；值读写走 :mod:`condition_tree` 的 main.xml 绑定，
    OK 后置 ``xml_dirty``。条件型 section 按实例（type=name）切换。
    """

    def __init__(self, ctx: dict, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self.setWindowTitle("Solver Settings — condition tree")
        self.setMinimumSize(800, 560)
        self._tree = condition_tree.load_condition_tree() or {"categories": []}
        xml = ctx.get("xml")
        self._cond_root = xml.section("conditions") if xml is not None else None
        self._sections: list[dict] = []
        # (instance, variable, editor, old_value)
        self._rows: list[tuple[ET.Element, dict, QLineEdit, str]] = []

        outer = QVBoxLayout(self)
        split = QHBoxLayout()

        self.nav = QTreeWidget()
        self.nav.setHeaderHidden(True)
        self.nav.setMinimumWidth(230)
        self.nav.setMaximumWidth(300)
        for cat in self._tree.get("categories", []):
            top = QTreeWidgetItem([cat.get("eng") or "?"])
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            self.nav.addTopLevelItem(top)
            top.setExpanded(True)
            for sec in cat.get("sections", []):
                it = QTreeWidgetItem(
                    [sec.get("eng") or sec.get("xml_name") or "(section)"])
                it.setData(0, Qt.UserRole, len(self._sections))
                self._sections.append(sec)
                top.addChild(it)
        split.addWidget(self.nav)

        right = QVBoxLayout()
        self.lab_section = QLabel("")
        self.lab_section.setStyleSheet("font-weight:bold;")
        self.cb_instance = QComboBox()
        self.cb_instance.setVisible(False)
        right.addWidget(self.lab_section)
        right.addWidget(self.cb_instance)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setLabelAlignment(Qt.AlignRight)
        scroll.setWidget(self.form_host)
        right.addWidget(scroll, 1)
        split.addLayout(right, 1)
        outer.addLayout(split, 1)

        self.lab_note = _note(
            "灰显行 = 当前实例未满足依赖条件（如 flow_io_type 模式）；"
            "值留空不写回。")
        outer.addWidget(self.lab_note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

        self.nav.currentItemChanged.connect(self._on_nav)
        self.cb_instance.currentIndexChanged.connect(self._render_section)
        first_top = self.nav.topLevelItem(0)
        if first_top is not None and first_top.childCount():
            self.nav.setCurrentItem(first_top.child(0))

    # ── section / 实例选择 ────────────────────────────────────────
    def _current_section(self) -> Optional[dict]:
        it = self.nav.currentItem()
        if it is None:
            return None
        idx = it.data(0, Qt.UserRole)
        return self._sections[idx] if isinstance(idx, int) else None

    def _on_nav(self) -> None:
        sec = self._current_section()
        self._rows = []
        self.cb_instance.blockSignals(True)
        self.cb_instance.clear()
        if sec is None:
            self.lab_section.setText("")
            self.cb_instance.setVisible(False)
            self.cb_instance.blockSignals(False)
            self._render_section()
            return
        insts = (condition_tree.section_instances(self._cond_root, sec)
                 if self._cond_root is not None else [])
        self.lab_section.setText(
            f"{sec.get('eng')}   [{len(sec.get('variables', []))} vars]")
        if sec.get("xml_name") == "condition":
            self.cb_instance.setVisible(True)
            if insts:
                for el in insts:
                    self.cb_instance.addItem(
                        f"{el.findtext('type') or '?'} — "
                        f"{el.findtext('name') or '?'}")
            else:
                self.cb_instance.addItem("(no matching condition instance)")
        else:
            self.cb_instance.setVisible(False)
        self.cb_instance.blockSignals(False)
        self._render_section()

    def _current_instance(self) -> Optional[ET.Element]:
        sec = self._current_section()
        if sec is None or self._cond_root is None:
            return None
        insts = condition_tree.section_instances(self._cond_root, sec)
        if not insts:
            return None
        if len(insts) == 1:
            return insts[0]
        i = self.cb_instance.currentIndex()
        return insts[i] if 0 <= i < len(insts) else None

    # ── 表单渲染 ──────────────────────────────────────────────────
    def _render_section(self) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows = []
        sec = self._current_section()
        el = self._current_instance()
        for v in (sec or {}).get("variables", []):
            ed = QLineEdit()
            unit_txt = ""
            val = None
            if el is not None:
                val = condition_tree.read_variable(el, v)
                # 单位子键当前值（展示用）
                ukey = v.get("unit_key")
                if ukey:
                    tgt = el.find("/".join(v.get("path") or []))
                    if tgt is not None and tgt.find(ukey) is not None:
                        unit_txt = (tgt.find(ukey).text or "").strip()
            ed.setText(val if val is not None else "")
            roww = QWidget()
            h = QHBoxLayout(roww)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(ed, 1)
            if unit_txt:
                lab_u = QLabel(unit_txt)
                lab_u.setStyleSheet("color:#888;")
                h.addWidget(lab_u)
            active = (el is not None
                      and condition_tree.variable_active(el, v))
            ed.setEnabled(active)
            if not active:
                deps = "; ".join(
                    "/".join(cd.get("keys") or []) + "=" + (cd.get("value") or "")
                    for cd in v.get("conditions", []))
                ed.setToolTip(f"requires: {deps}" if deps else "no instance")
            label = v.get("display") or v["name"]
            self.form.addRow(label, roww)
            self._rows.append((el, v, ed, val or ""))

    # ── 写回 ──────────────────────────────────────────────────────
    def _on_ok(self) -> None:
        changed = False
        for el, v, ed, old in self._rows:
            new = ed.text().strip()
            if el is None or not new or new == old:
                continue
            if condition_tree.write_variable(el, v, new):
                changed = True
        if changed:
            self._ctx["xml_dirty"] = True
        self.accept()


class ConditionsBody(_Body):
    """[Condition] – [Conditions] → Condition Wizard（对齐 scFLOWpre）。"""

    title = "Condition Wizard"
    min_size = (960, 680)
    dialog_buttons = 0  # Back / Next / Finish 在内容区

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._pages: dict[str, QWidget] = {}
        self._leaf_keys = [k for k, _ in _COND_WIZARD_LEAVES]
        self._atype_checks: dict[str, QCheckBox] = {}
        self._file_edits: dict[str, QLineEdit] = {}
        self._file_checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        split = QHBoxLayout()

        self.nav = QTreeWidget()
        self.nav.setHeaderHidden(True)
        self.nav.setMinimumWidth(220)
        self.nav.setMaximumWidth(280)
        self.nav.setIndentation(14)
        self._build_nav_tree()
        split.addWidget(self.nav)

        self.stack = QStackedWidget()
        self._build_pages()
        split.addWidget(self.stack, 1)
        root.addLayout(split, 1)

        foot = QHBoxLayout()
        self.btn_detail = QPushButton("Detailed Settings...")
        self.btn_base = QPushButton("Base Value...")
        self.btn_base.setVisible(False)
        foot.addWidget(self.btn_detail)
        foot.addWidget(self.btn_base)
        foot.addStretch(1)
        self.btn_back = QPushButton("<< Back")
        self.btn_next = QPushButton("Next >>")
        self.btn_finish = QPushButton("Finish")
        foot.addWidget(self.btn_back)
        foot.addWidget(self.btn_next)
        foot.addWidget(self.btn_finish)
        root.addLayout(foot)

        self.nav.currentItemChanged.connect(self._on_nav)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_finish.clicked.connect(self._finish)
        self.btn_detail.clicked.connect(self._on_detailed)
        self.btn_base.clicked.connect(self._on_base_value)
        # 默认选中 Analysis Type
        first = self._find_nav_item("analysis_type")
        if first is not None:
            self.nav.setCurrentItem(first)

    def _build_nav_tree(self) -> None:
        fold = _wizard_folder_icon()
        leaf = _wizard_leaf_icon()
        self.nav.clear()

        def add_folder(parent, title: str) -> QTreeWidgetItem:
            it = QTreeWidgetItem([title])
            it.setIcon(0, fold)
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            if parent is None:
                self.nav.addTopLevelItem(it)
            else:
                parent.addChild(it)
            it.setExpanded(True)
            return it

        def add_leaf(parent, key: str, title: str) -> QTreeWidgetItem:
            it = QTreeWidgetItem([title])
            it.setIcon(0, leaf)
            it.setData(0, Qt.UserRole, key)
            parent.addChild(it)
            return it

        ac = add_folder(None, "Analysis Conditions")
        add_leaf(ac, "analysis_type", "Analysis Type")
        add_leaf(ac, "basic_setting", "Basic Setting")
        add_leaf(ac, "initial", "Initial Condition")
        bc = add_folder(ac, "Boundary Condition")
        add_leaf(bc, "bc_flow", "Flow Boundary")
        add_leaf(bc, "bc_wall", "Wall Boundary")
        add_leaf(bc, "bc_thermal", "Thermal Boundary")
        add_leaf(bc, "bc_sym", "Symmetrical Boundary")
        add_leaf(bc, "bc_periodic", "Periodic Boundary")
        add_leaf(ac, "source", "Source Condition")
        add_leaf(ac, "fixed", "Fixed Condition")
        add_leaf(ac, "analysis_control", "Analysis Control")

        out = add_folder(None, "Output Setting of Analysis Data")
        add_leaf(out, "out_field", "Output of Field File")
        add_leaf(out, "out_list", "Output of List File")
        add_leaf(out, "out_other", "Other Output")

        for key, title in (("file_name", "File Name"),
                           ("optional", "Optional Conditions")):
            it = QTreeWidgetItem([title])
            it.setIcon(0, leaf)
            it.setData(0, Qt.UserRole, key)
            self.nav.addTopLevelItem(it)

    def _build_pages(self) -> None:
        self._pages["analysis_type"] = self._page_analysis_type()
        self._pages["basic_setting"] = self._page_basic()
        self._pages["initial"] = self._page_initial_condition()
        self._pages["bc_flow"] = self._page_flow_boundary()
        self._pages["bc_wall"] = self._page_wall_boundary()
        self._pages["bc_thermal"] = self._page_thermal_boundary()
        self._pages["bc_sym"] = self._page_sym_boundary()
        self._pages["bc_periodic"] = self._page_periodic_boundary()
        self._pages["source"] = self._page_source_condition()
        self._pages["fixed"] = self._page_fixed_condition()
        self._pages["analysis_control"] = self._page_analysis_control()
        self._pages["out_field"] = self._page_output_field()
        self._pages["out_list"] = self._page_output_list()
        self._pages["out_other"] = self._page_output_other()
        self._pages["file_name"] = self._page_file_name()
        self._pages["optional"] = self._page_optional_conditions()
        for key, _title in _COND_WIZARD_LEAVES:
            self.stack.addWidget(self._pages[key])

    def _page_analysis_type(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("Set the analysis type."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        self._atype_checks.clear()
        for group, items in _ANALYSIS_TYPE_GROUPS:
            box = QGroupBox(group)
            gl = QGridLayout(box)
            for i, (label, tag) in enumerate(items):
                chk = QCheckBox(label)
                self._atype_checks[tag] = chk
                chk.toggled.connect(self._sync_flow_bc_buttons)
                chk.toggled.connect(self._sync_wall_bc_buttons)
                chk.toggled.connect(self._sync_thermal_bc_buttons)
                chk.toggled.connect(self._sync_sym_bc_buttons)
                chk.toggled.connect(self._sync_source_bc_buttons)
                row, col = divmod(i, 2)
                gl.addWidget(chk, row, col)
                if tag in ("Flow",):
                    # Method Setting 占位
                    btn = QPushButton("Method Setting...")
                    btn.setEnabled(True)
                    gl.addWidget(btn, row, 2)
            iv.addWidget(box)
        iv.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        return page

    def _page_basic(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("Set the basic parameters for the calculation."))
        box_st = QGroupBox("Steady/Transient")
        hs = QHBoxLayout(box_st)
        self.rb_steady = QRadioButton("Steady-state analysis")
        self.rb_trans = QRadioButton("Transient analysis")
        self.rb_steady.setChecked(True)
        hs.addWidget(self.rb_steady)
        hs.addWidget(self.rb_trans)
        hs.addStretch(1)
        v.addWidget(box_st)

        box_cy = QGroupBox("Cycle")
        cv = QVBoxLayout(box_cy)
        cv.addWidget(QLabel("Parameters of time and cycle"))
        self.cycle_tree = QTreeWidget()
        self.cycle_tree.setColumnCount(3)
        self.cycle_tree.setHeaderLabels(["Parameter", "Value", "Unit"])
        self.cycle_tree.setRootIsDecorated(False)
        self.cycle_tree.setAlternatingRowColors(True)
        self.cycle_tree.setUniformRowHeights(False)
        self.cycle_tree.setColumnWidth(0, 260)
        self.cycle_tree.setColumnWidth(1, 200)
        self._cycle_items: dict[str, QTreeWidgetItem] = {}
        self._cycle_editors: dict[str, QWidget] = {}

        def add_cycle(key: str, label: str, editor: QWidget,
                      unit: str = "") -> None:
            it = QTreeWidgetItem([label, "", unit])
            self.cycle_tree.addTopLevelItem(it)
            self.cycle_tree.setItemWidget(it, 1, editor)
            self._cycle_items[key] = it
            self._cycle_editors[key] = editor

        self.sp_last_cycle = QSpinBox()
        self.sp_last_cycle.setRange(1, 10_000_000)
        self.sp_last_cycle.setValue(400)
        add_cycle("last_cycle", "Last cycle", self.sp_last_cycle)

        self.cb_dt_type = QComboBox()
        self.cb_dt_type.addItem("Time step", "0")
        self.cb_dt_type.addItem("Courant number", "1")
        self.cb_dt_type.addItem("Courant number (power mean)", "2")
        add_cycle("dt_type", "Type", self.cb_dt_type)

        self.sp_dt = _spin_f(8, 0.0, 1e9, 0.0001)
        add_cycle("time_step", "Time step", self.sp_dt, "s")

        self.sp_dt_init = _spin_f(8, 0.0, 1e9, 0.01)
        add_cycle("dt_init", "Initial time step", self.sp_dt_init, "s")

        self.sp_courant = _spin_f(6, 0.0, 1e6, 0.9)
        add_cycle("courant", "Courant number", self.sp_courant, "-")

        self.cb_set_start = QComboBox()
        self.cb_set_start.addItem("Do not set", "false")
        self.cb_set_start.addItem("Set", "true")
        add_cycle("set_start", "Set start time", self.cb_set_start)

        self.sp_start_time = _spin_f(8, -1e9, 1e9, 0.0)
        add_cycle("start_time", "Start time", self.sp_start_time, "s")

        self.cb_set_stop = QComboBox()
        self.cb_set_stop.addItem("Do not set", "false")
        self.cb_set_stop.addItem("Set", "true")
        add_cycle("set_stop", "Set stop time", self.cb_set_stop)

        self.sp_stop_time = _spin_f(8, -1e9, 1e9, 100.0)
        add_cycle("stop_time", "Stop time", self.sp_stop_time, "s")

        self.cb_set_dt_limit = QComboBox()
        self.cb_set_dt_limit.addItem("Do not set", "false")
        self.cb_set_dt_limit.addItem("Set", "true")
        add_cycle("set_dt_limit", "Set limit of time step",
                  self.cb_set_dt_limit)

        self.sp_dt_upper = _spin_f(8, 0.0, 1e9, 1.0)
        add_cycle("dt_upper", "Upper limit", self.sp_dt_upper, "s")
        self.sp_dt_lower = _spin_f(8, 0.0, 1e9, 0.01)
        add_cycle("dt_lower", "Lower limit", self.sp_dt_lower, "s")

        self.cb_skip = QComboBox()
        self.cb_skip.addItem("Do not execute", "false")
        self.cb_skip.addItem("Execute", "true")
        add_cycle("skip_mode",
                  "Execute flow calculation with skip mode", self.cb_skip)

        self.sp_skip_duration = _spin_f(8, 0.0, 1e9, 0.0)
        add_cycle("skip_duration", "Duration time of flow calculation",
                  self.sp_skip_duration, "s")
        self.sp_skip_time = _spin_f(8, 0.0, 1e9, 0.0)
        add_cycle("skip_time", "Skip time", self.sp_skip_time, "s")
        self.sp_skip_dt = _spin_f(8, 0.0, 1e9, 0.0)
        add_cycle("skip_dt", "Interval time during skip phase",
                  self.sp_skip_dt, "s")

        cv.addWidget(self.cycle_tree, 1)
        v.addWidget(box_cy, 1)

        box_t = QGroupBox("Default temperature and unit setting")
        tf = QHBoxLayout(box_t)
        tf.addWidget(QLabel("Default temperature"))
        self.sp_def_temp = _spin_f(2, -273.15, 1e6, 20.0)
        self.cb_temp_unit = QComboBox()
        self.cb_temp_unit.addItems(["C", "K", "F", "R"])
        tf.addWidget(self.sp_def_temp)
        tf.addWidget(self.cb_temp_unit)
        tf.addStretch(1)
        v.addWidget(box_t)

        box_g = QGroupBox("Gravity")
        gv = QVBoxLayout(box_g)
        self.chk_gravity = QCheckBox("Consider gravity")
        gv.addWidget(self.chk_gravity)
        gf = QFormLayout()
        self.sp_gx = _spin_f(6, -1e6, 1e6, 0.0)
        self.sp_gy = _spin_f(6, -1e6, 1e6, 0.0)
        self.sp_gz = _spin_f(6, -1e6, 1e6, -1.0)
        self.sp_gmag = _spin_f(6, 0.0, 1e6, 9.8)
        dir_row = QHBoxLayout()
        for lab, sp in (("X", self.sp_gx), ("Y", self.sp_gy),
                        ("Z", self.sp_gz)):
            dir_row.addWidget(QLabel(lab))
            dir_row.addWidget(sp)
        gf.addRow("Direction", dir_row)
        mag_row = QHBoxLayout()
        mag_row.addWidget(self.sp_gmag)
        mag_row.addWidget(QLabel("m/s2"))
        gf.addRow("Magnitude", mag_row)
        gv.addLayout(gf)
        self.btn_buoyancy = QPushButton("Buoyancy Setting...")
        self.btn_buoyancy.setEnabled(False)
        gv.addWidget(self.btn_buoyancy)
        self.chk_gravity.toggled.connect(self.btn_buoyancy.setEnabled)
        v.addWidget(box_g)

        self.rb_trans.toggled.connect(self._sync_basic_cycle)
        self.cb_dt_type.currentIndexChanged.connect(self._sync_basic_cycle)
        self.cb_set_start.currentIndexChanged.connect(self._sync_basic_cycle)
        self.cb_set_stop.currentIndexChanged.connect(self._sync_basic_cycle)
        self.cb_set_dt_limit.currentIndexChanged.connect(
            self._sync_basic_cycle)
        self.cb_skip.currentIndexChanged.connect(self._sync_basic_cycle)
        self._sync_basic_cycle()
        return page

    def _sync_basic_cycle(self, *_args) -> None:
        """稳态只显示 Last cycle；瞬态按 Type / Set / Skip 动态显隐。"""
        transient = self.rb_trans.isChecked()
        dt = self.cb_dt_type.currentData() or "0"
        is_fixed_dt = dt == "0"
        is_courant = dt in ("1", "2")
        set_start = (self.cb_set_start.currentData() or "false") == "true"
        set_stop = (self.cb_set_stop.currentData() or "false") == "true"
        set_lim = (self.cb_set_dt_limit.currentData() or "false") == "true"
        skip_on = (self.cb_skip.currentData() or "false") == "true"

        vis = {
            "last_cycle": True,
            "dt_type": transient,
            "time_step": transient and is_fixed_dt,
            "dt_init": transient and is_courant,
            "courant": transient and is_courant,
            "set_start": transient,
            "start_time": transient and set_start,
            "set_stop": transient,
            "stop_time": transient and set_stop,
            "set_dt_limit": transient and is_courant,
            "dt_upper": transient and is_courant and set_lim,
            "dt_lower": transient and is_courant and set_lim,
            "skip_mode": transient,
            "skip_duration": transient and skip_on,
            "skip_time": transient and skip_on,
            "skip_dt": transient and skip_on,
        }
        for key, show in vis.items():
            it = self._cycle_items.get(key)
            if it is not None:
                it.setHidden(not show)

    def _page_initial_condition(self) -> QWidget:
        """Initial Condition：区域列表图标 + New condition 示意图按钮。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region", "Kind"])
        lst.setRootIsDecorated(False)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]

        right = QGroupBox("New condition")
        rv = QVBoxLayout(right)
        rv.setSpacing(8)
        page._ic_buttons = []  # type: ignore[attr-defined]
        # 示意图略小于 Flow Boundary，避免第 4 项人形图标显得臃肿
        ic_sz = 36
        for kind, label in _IC_NEW_COND_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_ic_new_condition_icon(kind, ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }")
            btn.clicked.connect(
                lambda _=False, lab=label:
                self._stub_new_condition("Initial Condition", lab))
            rv.addWidget(btn)
            page._ic_buttons.append(btn)  # type: ignore[attr-defined]

        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog("initial"))
        rv.addWidget(btn_more)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Initial Condition"))
        rv.addWidget(btn_ex)

        tip = QLabel(
            "Note 1) If an initial temperature condition for "
            "\"Whole region\" does not exist, an initial condition of "
            "the default temperature will be set automatically. "
            "If an initial condition for \"Whole region\" does not "
            "exist, an initial condition of the default value will be "
            "set automatically.\n"
            "Note 2) If both initial value and field conditions are "
            "set simultaneously, the initial value condition has "
            "priority.\n"
            "Note 3) Initial value settings for the \"Whole region\" "
            "are overwritten by those for other regions.")
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "color:#555; font-size:11px; margin-top:4px;")
        rv.addWidget(tip)
        rv.addStretch(1)

        h.addWidget(left, 2)
        h.addWidget(right, 3)
        return page

    def _page_flow_boundary(self) -> QWidget:
        """Flow Boundary：区域树 + New condition 示意图 / 通量条件编辑。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_flow_bc_sel)

        right_stack = QStackedWidget()
        page._flow_stack = right_stack  # type: ignore[attr-defined]

        # 0 — New condition 选择
        new_page = QWidget()
        nv = QVBoxLayout(new_page)
        nv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("New condition")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        page._flow_btns = {}  # type: ignore[attr-defined]
        flow_ic_sz = 36
        for kind, label, gate in _FLOW_BC_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_flow_bc_icon(kind, flow_ic_sz))
            btn.setIconSize(QSize(flow_ic_sz, flow_ic_sz))
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }"
                "QPushButton:disabled { color: #9e9e9e; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._open_flow_bc_editor(k, lab, new=True))
            bv.addWidget(btn)
            page._flow_btns[kind] = (btn, gate)  # type: ignore[attr-defined]
        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog("bc_flow"))
        bv.addWidget(btn_more)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Flow Boundary"))
        bv.addWidget(btn_ex)
        tip = QLabel(
            "* Particle outflow boundaries (DEM) are not necessary on "
            "flow boundaries of fluid when coupled with CFD. "
            "Destructing particles on an internal surface region "
            "requires this condition.\n"
            "* Liquid film / GT-SUITE / DEM buttons appear when the "
            "corresponding Analysis Type is enabled.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        nv.addWidget(box, 1)
        right_stack.addWidget(new_page)

        # 1 — Inflow/outflow 参数编辑
        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.flow_edit_title = QLabel("Inflow and outflow condition")
        self.flow_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.flow_edit_title)
        form = QFormLayout()
        self.ed_flow_name = QLineEdit("Flux")
        self.cb_flow_type = QComboBox()
        for t in _FLOW_BC_TYPES:
            self.cb_flow_type.addItem(t)
        form.addRow("Name", self.ed_flow_name)
        form.addRow("Type", self.cb_flow_type)
        ev.addLayout(form)
        self.flow_param_tree = QTreeWidget()
        self.flow_param_tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.flow_param_tree.setRootIsDecorated(False)
        self.flow_param_tree.setAlternatingRowColors(True)
        ev.addWidget(self.flow_param_tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_flow_preview = QPushButton("Preview")
        self.btn_flow_remove = QPushButton("Remove")
        self.btn_flow_set = QPushButton("Set")
        self.btn_flow_back_new = QPushButton("<< New condition")
        row.addWidget(self.btn_flow_back_new)
        row.addWidget(self.btn_flow_preview)
        row.addWidget(self.btn_flow_remove)
        row.addWidget(self.btn_flow_set)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        self.cb_flow_type.currentIndexChanged.connect(
            self._rebuild_flow_params)
        self.btn_flow_back_new.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_flow_set.clicked.connect(self._set_flow_bc)
        self.btn_flow_remove.clicked.connect(self._remove_flow_bc)
        self.btn_flow_preview.clicked.connect(self._preview_flow_bc)
        self._rebuild_flow_params()

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        page._flow_editing = None  # type: ignore[attr-defined]
        return page

    def _rebuild_flow_params(self, *_args) -> None:
        tree = self.flow_param_tree
        tree.clear()
        typ = self.cb_flow_type.currentText()
        rows: list[tuple[str, str, str]] = []
        if "Normal velocity" in typ:
            rows.append(("Vertical velocity", "0", "m/s"))
        elif "Velocity components" in typ and "Angle" not in typ:
            rows += [("X-velocity", "0", "m/s"),
                     ("Y-velocity", "0", "m/s"),
                     ("Z-velocity", "0", "m/s")]
        elif "Mass flow" in typ:
            rows.append(("Mass flow rate", "0", "kg/s"))
        elif "Volume flow" in typ:
            rows.append(("Volume flow rate", "0", "m3/s"))
        elif "Static pressure" in typ or "Total pressure" in typ:
            rows.append(("Pressure", "0", "Pa"))
        else:
            rows.append(("Value", "0", "-"))
        if "Outflow" not in typ and "Natural" not in typ:
            rows += [
                ("Inflow temperature type", "Default temperature", ""),
                ("Inflow turbulence type",
                 "Turbulence intensity and ratio", ""),
                ("Turbulence intensity", "5", "%"),
                ("Ratio (eddy viscosity/molecular viscosity)", "100", "-"),
            ]
        for name, val, unit in rows:
            tree.addTopLevelItem(QTreeWidgetItem([name, val, unit, ""]))
        self.btn_flow_preview.setEnabled("Velocity components" in typ)

    def _sync_flow_bc_buttons(self) -> None:
        page = self._pages.get("bc_flow")
        if page is None:
            return
        btns = getattr(page, "_flow_btns", {})
        for kind, (btn, gate) in btns.items():
            if not gate:
                btn.setVisible(True)
                btn.setEnabled(True)
                continue
            chk = self._atype_checks.get(gate)
            on = chk.isChecked() if chk is not None else False
            # FreeSurface 近似液体膜显隐；手册还要求 liquid film 模型
            btn.setVisible(True)
            btn.setEnabled(on)

    def _open_flow_bc_editor(self, kind: str, label: str, *,
                             new: bool = True,
                             name: str = "", typ: str = "") -> None:
        page = self._pages["bc_flow"]
        stack: QStackedWidget = page._flow_stack  # type: ignore[attr-defined]
        self.flow_edit_title.setText(label)
        if new:
            base = "Flux"
            n = 1
            existing: set[str] = set()
            lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
            root = lst.invisibleRootItem()
            for i in range(root.childCount()):
                reg = root.child(i)
                for j in range(reg.childCount()):
                    existing.add(reg.child(j).text(0))
            cand = base
            while cand in existing:
                n += 1
                cand = f"{base}[{n}]"
            self.ed_flow_name.setText(cand)
            self.cb_flow_type.setCurrentIndex(0)
        else:
            self.ed_flow_name.setText(name or "Flux")
            i = self.cb_flow_type.findText(typ)
            if i >= 0:
                self.cb_flow_type.setCurrentIndex(i)
        self._rebuild_flow_params()
        page._flow_editing = {  # type: ignore[attr-defined]
            "kind": kind, "label": label, "new": new}
        stack.setCurrentIndex(1)

    def _on_flow_bc_sel(self) -> None:
        page = self._pages.get("bc_flow")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            # 选中区域 → 回到 New condition
            page._flow_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        # 选中已有条件 → 打开编辑
        self._open_flow_bc_editor(
            "io", "Inflow and outflow condition",
            new=False, name=it.text(0),
            typ=it.data(0, Qt.UserRole) or "Normal velocity")

    def _selected_flow_region(self) -> str:
        page = self._pages["bc_flow"]
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _set_flow_bc(self) -> None:
        page = self._pages["bc_flow"]
        name = self.ed_flow_name.text().strip() or "Flux"
        typ = self.cb_flow_type.currentText()
        region = self._selected_flow_region() or "(unassigned)"
        params = {}
        for i in range(self.flow_param_tree.topLevelItemCount()):
            it = self.flow_param_tree.topLevelItem(i)
            params[it.text(0)] = {
                "value": it.text(1), "unit": it.text(2)}
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        flows = sess.setdefault("flow_boundaries", [])
        # 更新或追加
        hit = None
        for row in flows:
            if row.get("name") == name:
                hit = row
                break
        data = {
            "name": name, "type": typ, "region": region,
            "params": params,
        }
        if hit is None:
            flows.append(data)
        else:
            hit.update(data)
        # 写回 xml 粗略 stub
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            for c in cond_root.findall("condition"):
                if (c.findtext("type") == "CondBoundaryFlowIO"
                        and (c.findtext("name") or "") == name):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondBoundaryFlowIO")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(el, "flow_io_type", typ)
            regs = el.find("regions")
            if regs is None:
                regs = ET.SubElement(el, "regions")
            if region and region != "(unassigned)":
                # 清空后写一个 face 引用
                for ch in list(regs):
                    regs.remove(ch)
                face = ET.SubElement(regs, "face")
                face.text = region
            self._ctx["xml_dirty"] = True
        self._fill_flow_bc_tree()
        page._flow_stack.setCurrentIndex(0)  # type: ignore[attr-defined]

    def _remove_flow_bc(self) -> None:
        name = self.ed_flow_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    if (c.findtext("type") == "CondBoundaryFlowIO"
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        flows = (self._ctx.get("session", {})
                 .get("conditions", {})
                 .get("flow_boundaries") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["flow_boundaries"] = [
            r for r in flows if r.get("name") != name]
        self._fill_flow_bc_tree()
        self._pages["bc_flow"]._flow_stack.setCurrentIndex(0)  # type: ignore

    def _preview_flow_bc(self) -> None:
        QMessageBox.information(
            self, "Preview",
            "Flow direction preview is shown in the draw window "
            "in scFLOWpre when Type is Velocity components.")

    def _fill_flow_bc_tree(self) -> None:
        page = self._pages.get("bc_flow")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        # 区域节点
        regions: list[tuple[str, str]] = []  # name, kind
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("face", "special_face", "numerical"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            regions.append((name, cat))
            for sh in _iter_xml_sheet_parts(xml):
                name = (sh.findtext("name") or "").strip()
                if name:
                    regions.append((name, "sheet"))
        if not regions:
            regions = [("(no surface region)", "face")]

        # 条件 → 区域
        cond_by_reg: dict[str, list[tuple[str, str]]] = {}
        if xml is not None:
            for cond in xml.conditions():
                if cond.findtext("type") != "CondBoundaryFlowIO":
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                ctype = cond.findtext("flow_io_type") or "Normal velocity"
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked:
                    linked = ["(unassigned)"]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append((cname, ctype))

        sheet_ic = _flow_sheet_icon(18)
        fold_ic = _wizard_folder_icon(16)
        for rname, kind in regions:
            parent = QTreeWidgetItem([rname])
            parent.setIcon(
                0, fold_ic if kind in ("numerical",) else sheet_ic)
            parent.setData(0, Qt.UserRole, ("region", rname))
            lst.addTopLevelItem(parent)
            for cname, ctype in cond_by_reg.get(rname, []):
                child = QTreeWidgetItem([cname])
                child.setIcon(0, _flow_bc_icon("io", 16))
                child.setData(0, Qt.UserRole, ctype)
                parent.addChild(child)
            parent.setExpanded(True)
        # 未分配条件
        for cname, ctype in cond_by_reg.get("(unassigned)", []):
            # 若已挂到某区域则跳过；此处单独挂
            orphan = QTreeWidgetItem([cname])
            orphan.setIcon(0, _flow_bc_icon("io", 16))
            orphan.setData(0, Qt.UserRole, ctype)
            # 放在第一个区域下便于对照 scFLOW Sheet1>Flux
            if lst.topLevelItemCount():
                lst.topLevelItem(0).addChild(orphan)
            else:
                lst.addTopLevelItem(orphan)

    def _page_wall_boundary(self) -> QWidget:
        """Wall Boundary：区域树 + New condition 示意图 / 壁面剪应力编辑。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_wall_bc_sel)

        right_stack = QStackedWidget()
        page._wall_stack = right_stack  # type: ignore[attr-defined]

        # 0 — New condition
        new_page = QWidget()
        nv = QVBoxLayout(new_page)
        nv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("New condition")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        page._wall_btns = {}  # type: ignore[attr-defined]
        ic_sz = 36
        for kind, label, gate in _WALL_BC_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_wall_bc_icon(kind, ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }"
                "QPushButton:disabled { color: #9e9e9e; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._open_wall_bc_editor(k, lab, new=True))
            bv.addWidget(btn)
            page._wall_btns[kind] = (btn, gate)  # type: ignore[attr-defined]
        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog("bc_wall"))
        bv.addWidget(btn_more)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Wall Boundary"))
        bv.addWidget(btn_ex)
        tip = QLabel(
            "* Undefined (Stress / Particle) regions receive the "
            "default condition for surfaces without an explicit wall BC.\n"
            "* Particle / Restitution buttons appear when "
            "Particle tracking is enabled in Analysis Type.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        nv.addWidget(box, 1)
        right_stack.addWidget(new_page)

        # 1 — Wall shear stress 编辑
        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.wall_edit_title = QLabel("Wall shear stress condition")
        self.wall_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.wall_edit_title)
        form = QFormLayout()
        self.ed_wall_name = QLineEdit(
            "Default condition (Stress: All fluid boundary)")
        form.addRow("Name", self.ed_wall_name)
        ev.addLayout(form)
        self.wall_param_tree = QTreeWidget()
        self.wall_param_tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.wall_param_tree.setRootIsDecorated(True)
        self.wall_param_tree.setAlternatingRowColors(True)
        ev.addWidget(self.wall_param_tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_wall_back_new = QPushButton("<< New condition")
        self.btn_wall_preview = QPushButton("Preview")
        self.btn_wall_preview.setEnabled(False)
        self.btn_wall_remove = QPushButton("Remove")
        self.btn_wall_set = QPushButton("Set")
        row.addWidget(self.btn_wall_back_new)
        row.addWidget(self.btn_wall_preview)
        row.addWidget(self.btn_wall_remove)
        row.addWidget(self.btn_wall_set)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        # 2 — Particle / Restitution 简要编辑
        pedit = QWidget()
        pv = QVBoxLayout(pedit)
        pv.setContentsMargins(0, 0, 0, 0)
        self.wall_part_title = QLabel("Particle boundary condition")
        self.wall_part_title.setStyleSheet("font-weight:bold;")
        pv.addWidget(self.wall_part_title)
        pform = QFormLayout()
        self.ed_wall_part_name = QLineEdit("ParticleWall")
        self.cb_wall_part_type = QComboBox()
        for t in (
            "Adhere to the wall",
            "Move along the wall",
            "Completely bounce off walls",
            "Bounce off walls with repulsion coefficient",
        ):
            self.cb_wall_part_type.addItem(t)
        pform.addRow("Name", self.ed_wall_part_name)
        pform.addRow("Type", self.cb_wall_part_type)
        pv.addLayout(pform)
        tip2 = QLabel(
            "DEM particle–wall interaction. Set ALPH / restitution "
            "details in scFLOWpre when using repulsion coefficient type.")
        tip2.setWordWrap(True)
        tip2.setStyleSheet("color:#555; font-size:11px;")
        pv.addWidget(tip2)
        pv.addStretch(1)
        prow = QHBoxLayout()
        prow.addStretch(1)
        self.btn_wall_part_back = QPushButton("<< New condition")
        self.btn_wall_part_set = QPushButton("Set")
        prow.addWidget(self.btn_wall_part_back)
        prow.addWidget(self.btn_wall_part_set)
        pv.addLayout(prow)
        right_stack.addWidget(pedit)

        self.btn_wall_back_new.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_wall_part_back.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_wall_set.clicked.connect(self._set_wall_bc)
        self.btn_wall_remove.clicked.connect(self._remove_wall_bc)
        self.btn_wall_part_set.clicked.connect(self._set_wall_particle_bc)
        self._rebuild_wall_stress_params()

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        return page

    def _rebuild_wall_stress_params(self) -> None:
        tree = self.wall_param_tree
        tree.clear()
        stress = QTreeWidgetItem(["Stress", "No-slip", "", ""])
        tree.addTopLevelItem(stress)
        rough = QTreeWidgetItem(["Roughness", "Do not consider", "", ""])
        stress.addChild(rough)
        moving = QTreeWidgetItem(["Moving", "Static", "", ""])
        tree.addTopLevelItem(moving)
        stress.setExpanded(True)

    def _sync_wall_bc_buttons(self, *_args) -> None:
        page = self._pages.get("bc_wall")
        if page is None:
            return
        for kind, (btn, gate) in getattr(page, "_wall_btns", {}).items():
            if not gate:
                btn.setVisible(True)
                btn.setEnabled(True)
                continue
            chk = self._atype_checks.get(gate)
            on = chk.isChecked() if chk is not None else False
            btn.setVisible(True)
            btn.setEnabled(on)

    def _open_wall_bc_editor(self, kind: str, label: str, *,
                             new: bool = True, name: str = "") -> None:
        page = self._pages["bc_wall"]
        stack: QStackedWidget = page._wall_stack  # type: ignore[attr-defined]
        if kind == "stress":
            self.wall_edit_title.setText(label)
            if new:
                self.ed_wall_name.setText(
                    "Default condition (Stress: All fluid boundary)"
                    if "Undefined" in (self._selected_wall_region() or "")
                    else "WallStress")
            else:
                self.ed_wall_name.setText(name or "WallStress")
            self._rebuild_wall_stress_params()
            stack.setCurrentIndex(1)
        else:
            self.wall_part_title.setText(label)
            self.ed_wall_part_name.setText(
                name or ("RestitutionWall" if kind == "restitution"
                         else "ParticleWall"))
            stack.setCurrentIndex(2)

    def _selected_wall_region(self) -> str:
        page = self._pages.get("bc_wall")
        if page is None:
            return ""
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _on_wall_bc_sel(self) -> None:
        page = self._pages.get("bc_wall")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            page._wall_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        kind = it.data(0, Qt.UserRole) or "stress"
        if kind == "stress":
            self._open_wall_bc_editor(
                "stress", "Wall shear stress condition",
                new=False, name=it.text(0))
        else:
            self._open_wall_bc_editor(
                kind, it.text(0), new=False, name=it.text(0))

    def _set_wall_bc(self) -> None:
        name = self.ed_wall_name.text().strip() or "WallStress"
        region = self._selected_wall_region() or (
            "Undefined (Stress: All fluid boundary)")
        params = {}
        root = self.wall_param_tree.invisibleRootItem()
        for i in range(root.childCount()):
            it = root.child(i)
            params[it.text(0)] = it.text(1)
            for j in range(it.childCount()):
                ch = it.child(j)
                params[ch.text(0)] = ch.text(1)
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        walls = sess.setdefault("wall_boundaries", [])
        hit = next((r for r in walls if r.get("name") == name), None)
        data = {"name": name, "kind": "stress", "region": region,
                "params": params}
        if hit is None:
            walls.append(data)
        else:
            hit.update(data)
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            for c in cond_root.findall("condition"):
                if (c.findtext("type") == "CondBoundaryWallStress"
                        and (c.findtext("name") or "") == name):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondBoundaryWallStress")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(
                el, "stress_type", params.get("Stress", "No-slip"))
            self._ctx["xml_dirty"] = True
        self._fill_wall_bc_tree()
        self._pages["bc_wall"]._wall_stack.setCurrentIndex(0)  # type: ignore

    def _set_wall_particle_bc(self) -> None:
        name = self.ed_wall_part_name.text().strip() or "ParticleWall"
        typ = self.cb_wall_part_type.currentText()
        region = self._selected_wall_region() or (
            "Undefined (Particle: All fluid boundary)")
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        walls = sess.setdefault("wall_boundaries", [])
        data = {"name": name, "kind": "particle", "region": region,
                "type": typ}
        hit = next((r for r in walls if r.get("name") == name), None)
        if hit is None:
            walls.append(data)
        else:
            hit.update(data)
        self._fill_wall_bc_tree()
        self._pages["bc_wall"]._wall_stack.setCurrentIndex(0)  # type: ignore

    def _remove_wall_bc(self) -> None:
        name = self.ed_wall_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    if (c.findtext("type") == "CondBoundaryWallStress"
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        walls = (self._ctx.get("session", {})
                 .get("conditions", {})
                 .get("wall_boundaries") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["wall_boundaries"] = [
            r for r in walls if r.get("name") != name]
        self._fill_wall_bc_tree()
        self._pages["bc_wall"]._wall_stack.setCurrentIndex(0)  # type: ignore

    def _fill_wall_bc_tree(self) -> None:
        page = self._pages.get("bc_wall")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        sheet_ic = _flow_sheet_icon(18)
        stress_ic = _wall_bc_icon("stress", 16)
        part_ic = _wall_bc_icon("particle", 16)

        # 默认 Undefined 区域（手册）
        defaults = [
            ("Undefined (Stress: All fluid boundary)", "stress"),
            ("Undefined (Particle: All fluid boundary)", "particle"),
        ]
        regions: list[tuple[str, str]] = list(defaults)
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("face", "special_face"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            regions.append((name, "face"))

        cond_by_reg: dict[str, list[tuple[str, str]]] = {}
        if xml is not None:
            for cond in xml.conditions():
                ctype = cond.findtext("type") or ""
                if ctype not in (
                    "CondBoundaryWallStress", "CondBoundaryWallThermal",
                ):
                    continue
                # Thermal 有独立页；此处只挂 Stress
                if ctype != "CondBoundaryWallStress":
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked:
                    linked = ["Undefined (Stress: All fluid boundary)"]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append(
                        (cname, "stress"))

        # session 中新建的 particle 条件
        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("wall_boundaries")) or []):
            reg = row.get("region") or defaults[0][0]
            cond_by_reg.setdefault(reg, []).append(
                (row.get("name") or "?", row.get("kind") or "stress"))

        for rname, rkind in regions:
            parent = QTreeWidgetItem([rname])
            parent.setIcon(
                0, stress_ic if "Stress" in rname else (
                    part_ic if "Particle" in rname else sheet_ic))
            lst.addTopLevelItem(parent)
            seen = set()
            for cname, ckind in cond_by_reg.get(rname, []):
                if cname in seen:
                    continue
                seen.add(cname)
                child = QTreeWidgetItem([cname])
                child.setIcon(
                    0, stress_ic if ckind == "stress" else part_ic)
                child.setData(0, Qt.UserRole, ckind)
                parent.addChild(child)
            parent.setExpanded(True)

    # ------------------------------------------------------------------
    # Thermal Boundary
    # ------------------------------------------------------------------
    def _page_thermal_boundary(self) -> QWidget:
        """Thermal Boundary：区域树 + New condition 示意图 / 传热编辑。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_thermal_bc_sel)

        right_stack = QStackedWidget()
        page._thermal_stack = right_stack  # type: ignore[attr-defined]

        new_page = QWidget()
        nv = QVBoxLayout(new_page)
        nv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("New condition")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        page._thermal_btns = {}  # type: ignore[attr-defined]
        ic_sz = 36
        for kind, label, gate in _THERMAL_BC_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_thermal_bc_icon(kind, ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }"
                "QPushButton:disabled { color: #9e9e9e; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._open_thermal_bc_editor(k, lab, new=True))
            bv.addWidget(btn)
            page._thermal_btns[kind] = (btn, gate)  # type: ignore[attr-defined]
        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(
            lambda: self._open_cond_catalog("bc_thermal"))
        bv.addWidget(btn_more)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Thermal Boundary"))
        bv.addWidget(btn_ex)
        tip = QLabel(
            "* Undefined (Thermal / Radiation / Particle) regions receive "
            "the default condition for surfaces without an explicit "
            "thermal BC.\n"
            "* Porous / Radiation / Solar buttons appear when the "
            "corresponding Analysis Type is enabled.\n"
            "* Heat transfer across a discontinuous interface is set "
            "via Contact Type on fluid–solid / solid–solid boundaries.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        nv.addWidget(box, 1)
        right_stack.addWidget(new_page)

        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.thermal_edit_title = QLabel("Wall heat transfer condition")
        self.thermal_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.thermal_edit_title)
        form = QFormLayout()
        self.ed_thermal_name = QLineEdit("WallHeat")
        self.cb_thermal_transfer = QComboBox()
        for t in ("Heat transfer", "Adiabatic", "User definition"):
            self.cb_thermal_transfer.addItem(t)
        row_transfer = QHBoxLayout()
        row_transfer.addWidget(self.cb_thermal_transfer, 1)
        # P4-2：厂商换热系数预设（heattransfer_ENG.xml）
        self.btn_thermal_preset = QPushButton("Preset...")
        self.btn_thermal_preset.clicked.connect(self._pick_ht_preset)
        row_transfer.addWidget(self.btn_thermal_preset)
        w_transfer = QWidget()
        lv_t = QVBoxLayout(w_transfer)
        lv_t.setContentsMargins(0, 0, 0, 0)
        lv_t.addLayout(row_transfer)
        form.addRow("Name", self.ed_thermal_name)
        form.addRow("Transfer Type", w_transfer)
        ev.addLayout(form)
        self.thermal_param_tree = QTreeWidget()
        self.thermal_param_tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.thermal_param_tree.setRootIsDecorated(True)
        self.thermal_param_tree.setAlternatingRowColors(True)
        ev.addWidget(self.thermal_param_tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        # P4-2：太阳辐射站点选择（solar_ENG.xml / SolarNEDO11.xml）
        self.btn_thermal_location = QPushButton("Location...")
        self.btn_thermal_location.clicked.connect(self._pick_solar_site)
        self.btn_thermal_back_new = QPushButton("<< New condition")
        self.btn_thermal_preview = QPushButton("Preview")
        self.btn_thermal_preview.setEnabled(False)
        self.btn_thermal_remove = QPushButton("Remove")
        self.btn_thermal_set = QPushButton("Set")
        row.addWidget(self.btn_thermal_location)
        row.addWidget(self.btn_thermal_back_new)
        row.addWidget(self.btn_thermal_preview)
        row.addWidget(self.btn_thermal_remove)
        row.addWidget(self.btn_thermal_set)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        self.cb_thermal_transfer.currentIndexChanged.connect(
            self._rebuild_thermal_params)
        self.btn_thermal_back_new.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_thermal_set.clicked.connect(self._set_thermal_bc)
        self.btn_thermal_remove.clicked.connect(self._remove_thermal_bc)
        self._rebuild_thermal_params()
        page._thermal_kind = "heat"  # type: ignore[attr-defined]

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        return page

    def _rebuild_thermal_params(self, *_args) -> None:
        tree = self.thermal_param_tree
        tree.clear()
        kind = getattr(
            self._pages.get("bc_thermal"), "_thermal_kind", "heat")
        transfer = self.cb_thermal_transfer.currentText()
        if kind == "radiation":
            for name, val, unit in (
                ("Emissivity", "1", "-"),
                ("Absorptivity", "1", "-"),
                ("Outside radiation type", "External temperature", ""),
            ):
                tree.addTopLevelItem(
                    QTreeWidgetItem([name, val, unit, ""]))
            return
        if kind == "solar":
            for name, val, unit in (
                ("Absorptivity", "0.5", "-"),
                ("Reflectivity", "0.5", "-"),
                ("Transmissivity", "0", "-"),
                ("Location", "(not set)", "", ""),
            ):
                it = QTreeWidgetItem([name, val, unit, ""])
                tree.addTopLevelItem(it)
                if name == "Location":
                    for cname, cval, cunit in (
                        ("Site", "", ""),
                        ("Latitude", "35.68", "deg"),
                        ("Longitude", "139.77", "deg"),
                        ("Standard meridian", "135", "deg"),
                        ("Elevation", "0", "m"),
                    ):
                        it.addChild(QTreeWidgetItem(
                            [cname, cval, cunit, ""]))
                    it.setExpanded(True)
            return
        process = QTreeWidgetItem(
            ["Heat transfer process", "Heat conduction", "", ""])
        tree.addTopLevelItem(process)
        rough = QTreeWidgetItem(["Roughness", "Do not consider", "", ""])
        process.addChild(rough)
        if transfer == "Heat transfer":
            contact = QTreeWidgetItem(
                ["Contact Type", "No resistance", "", ""])
            tree.addTopLevelItem(contact)
        outside = QTreeWidgetItem(
            ["Outside region type", "External temperature", "", ""])
        tree.addTopLevelItem(outside)
        if "External" in outside.text(1) or True:
            temp = QTreeWidgetItem(
                ["External temperature", "20", "C", ""])
            outside.addChild(temp)
        if kind == "porous":
            tree.addTopLevelItem(QTreeWidgetItem(
                ["Porous heat transfer", "Enable", "", ""]))
        process.setExpanded(True)
        outside.setExpanded(True)

    def _sync_thermal_bc_buttons(self, *_args) -> None:
        page = self._pages.get("bc_thermal")
        if page is None:
            return
        for kind, (btn, gate) in getattr(page, "_thermal_btns", {}).items():
            if not gate:
                btn.setVisible(True)
                btn.setEnabled(True)
                continue
            chk = self._atype_checks.get(gate)
            on = chk.isChecked() if chk is not None else False
            btn.setVisible(True)
            btn.setEnabled(on)

    def _open_thermal_bc_editor(self, kind: str, label: str, *,
                                new: bool = True, name: str = "") -> None:
        page = self._pages["bc_thermal"]
        stack: QStackedWidget = page._thermal_stack  # type: ignore[attr-defined]
        page._thermal_kind = kind  # type: ignore[attr-defined]
        self.thermal_edit_title.setText(label)
        if new:
            defaults = {
                "heat": "WallHeat",
                "porous": "WallHeatPorous",
                "radiation": "RadiationBC",
                "solar": "SolarBC",
            }
            self.ed_thermal_name.setText(name or defaults.get(kind, "WallHeat"))
        else:
            self.ed_thermal_name.setText(name or "WallHeat")
        self.cb_thermal_transfer.setEnabled(kind in ("heat", "porous"))
        # P4-2：预设按钮仅换热模式；站点按钮仅太阳模式
        self.btn_thermal_preset.setVisible(kind in ("heat", "porous"))
        self.btn_thermal_location.setVisible(kind == "solar")
        self._rebuild_thermal_params()
        stack.setCurrentIndex(1)

    def _pick_ht_preset(self) -> None:
        """P4-2：换热系数预设 → 写入参数树。"""
        dlg = HeatTransferPresetDialog(self)
        if dlg.exec_() != QDialog.Accepted or dlg.preset is None:
            return
        p = dlg.preset
        vals = (p.values + [0.0, 0.0])[:2]
        tree = self.thermal_param_tree
        for i in range(tree.topLevelItemCount()):
            if tree.topLevelItem(i).text(0) == "Heat transfer coefficient":
                tree.takeTopLevelItem(i)
                break
        node = QTreeWidgetItem([
            "Heat transfer coefficient", p.subname or p.name, "W/m2K",
            "preset"])
        node.addChild(QTreeWidgetItem(
            ["Coefficient (heat flow up)", f"{vals[0]:g}", "W/m2K", ""]))
        node.addChild(QTreeWidgetItem(
            ["Coefficient (heat flow down)", f"{vals[1]:g}", "W/m2K", ""]))
        node.setExpanded(True)
        tree.addTopLevelItem(node)

    def _pick_solar_site(self) -> None:
        """P4-2：太阳站点选择 → 写入 Location 节点。"""
        dlg = SolarSiteDialog(self)
        if dlg.exec_() != QDialog.Accepted or dlg.site is None:
            return
        name, lat, lon, std, elev = dlg.site
        tree = self.thermal_param_tree
        for i in range(tree.topLevelItemCount()):
            it = tree.topLevelItem(i)
            if it.text(0) != "Location":
                continue
            it.setText(1, name)
            for j in range(it.childCount()):
                ch = it.child(j)
                if ch.text(0) == "Site":
                    ch.setText(1, name)
                elif ch.text(0) == "Latitude":
                    ch.setText(1, f"{lat:g}")
                elif ch.text(0) == "Longitude":
                    ch.setText(1, f"{lon:g}")
                elif ch.text(0) == "Standard meridian":
                    ch.setText(1, f"{std:g}")
                elif ch.text(0) == "Elevation":
                    ch.setText(1, f"{elev:g}")
            break

    def _selected_thermal_region(self) -> str:
        page = self._pages.get("bc_thermal")
        if page is None:
            return ""
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _on_thermal_bc_sel(self) -> None:
        page = self._pages.get("bc_thermal")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            page._thermal_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        kind = it.data(0, Qt.UserRole) or "heat"
        labels = {
            "heat": "Wall heat transfer condition",
            "porous": "Wall heat transfer condition (Porous media)",
            "radiation": "Radiation boundary condition",
            "solar": "Solar radiation boundary condition",
        }
        self._open_thermal_bc_editor(
            kind, labels.get(kind, it.text(0)),
            new=False, name=it.text(0))

    def _set_thermal_bc(self) -> None:
        name = self.ed_thermal_name.text().strip() or "WallHeat"
        page = self._pages["bc_thermal"]
        kind = getattr(page, "_thermal_kind", "heat")
        region = self._selected_thermal_region() or (
            "Undefined (Thermal:Boundary with outside)")
        params = {"Transfer Type": self.cb_thermal_transfer.currentText()}
        root = self.thermal_param_tree.invisibleRootItem()
        for i in range(root.childCount()):
            it = root.child(i)
            params[it.text(0)] = it.text(1)
            for j in range(it.childCount()):
                ch = it.child(j)
                params[ch.text(0)] = ch.text(1)
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        thermals = sess.setdefault("thermal_boundaries", [])
        data = {"name": name, "kind": kind, "region": region,
                "params": params}
        hit = next((r for r in thermals if r.get("name") == name), None)
        if hit is None:
            thermals.append(data)
        else:
            hit.update(data)
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            for c in cond_root.findall("condition"):
                if (c.findtext("type") == "CondBoundaryWallThermal"
                        and (c.findtext("name") or "") == name):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondBoundaryWallThermal")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(el, "thermal_kind", kind)
            _ensure_child_text(
                el, "transfer_type", params.get("Transfer Type", ""))
            self._ctx["xml_dirty"] = True
        self._fill_thermal_bc_tree()
        page._thermal_stack.setCurrentIndex(0)  # type: ignore[attr-defined]

    def _remove_thermal_bc(self) -> None:
        name = self.ed_thermal_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    if (c.findtext("type") == "CondBoundaryWallThermal"
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        thermals = (self._ctx.get("session", {})
                    .get("conditions", {})
                    .get("thermal_boundaries") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["thermal_boundaries"] = [
            r for r in thermals if r.get("name") != name]
        self._fill_thermal_bc_tree()
        self._pages["bc_thermal"]._thermal_stack.setCurrentIndex(0)  # type: ignore

    def _fill_thermal_bc_tree(self) -> None:
        page = self._pages.get("bc_thermal")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        sheet_ic = _flow_sheet_icon(18)
        heat_ic = _thermal_bc_icon("heat", 16)
        rad_ic = _thermal_bc_icon("radiation", 16)
        part_ic = _wall_bc_icon("particle", 16)

        defaults = [
            ("Undefined (Thermal:Boundary with outside)", "heat"),
            ("Undefined (Thermal:Fluid-Solid boundary)", "heat"),
            ("Undefined (Thermal:Solid-Solid boundary)", "heat"),
            ("Undefined (Radiation: Boundary with outside)", "radiation"),
            ("Undefined (Particle: All fluid boundary)", "particle"),
        ]
        regions: list[tuple[str, str]] = list(defaults)
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("face", "special_face"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            regions.append((name, "face"))

        cond_by_reg: dict[str, list[tuple[str, str]]] = {}
        if xml is not None:
            for cond in xml.conditions():
                if (cond.findtext("type") or "") != "CondBoundaryWallThermal":
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                ckind = (cond.findtext("thermal_kind") or "heat").strip()
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked:
                    linked = [defaults[0][0]]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append((cname, ckind))

        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("thermal_boundaries")) or []):
            reg = row.get("region") or defaults[0][0]
            cond_by_reg.setdefault(reg, []).append(
                (row.get("name") or "?", row.get("kind") or "heat"))

        for rname, rkind in regions:
            parent = QTreeWidgetItem([rname])
            if "Radiation" in rname:
                parent.setIcon(0, rad_ic)
            elif "Particle" in rname:
                parent.setIcon(0, part_ic)
            elif "Thermal" in rname:
                parent.setIcon(0, heat_ic)
            else:
                parent.setIcon(0, sheet_ic)
            lst.addTopLevelItem(parent)
            seen = set()
            for cname, ckind in cond_by_reg.get(rname, []):
                if cname in seen:
                    continue
                seen.add(cname)
                child = QTreeWidgetItem([cname])
                child.setIcon(
                    0, rad_ic if ckind == "radiation"
                    else heat_ic if ckind in ("heat", "porous", "solar")
                    else part_ic)
                child.setData(0, Qt.UserRole, ckind)
                parent.addChild(child)
            parent.setExpanded(True)

    # ------------------------------------------------------------------
    # Symmetrical Boundary
    # ------------------------------------------------------------------
    def _page_sym_boundary(self) -> QWidget:
        """Symmetrical Boundary：区域树 + Apply 示意图按钮。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_sym_bc_sel)

        right_stack = QStackedWidget()
        page._sym_stack = right_stack  # type: ignore[attr-defined]

        apply_page = QWidget()
        av = QVBoxLayout(apply_page)
        av.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Apply")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        page._sym_btns = {}  # type: ignore[attr-defined]
        ic_sz = 36
        for kind, label, gate in _SYM_BC_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_sym_bc_icon(kind, ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }"
                "QPushButton:disabled { color: #9e9e9e; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._apply_sym_bc(k, lab))
            bv.addWidget(btn)
            page._sym_btns[kind] = (btn, gate)  # type: ignore[attr-defined]
        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog("bc_sym"))
        bv.addWidget(btn_more)
        tip = QLabel(
            "* There is no parameter to set for a plain symmetrical "
            "boundary condition.\n"
            "* Particle / Particle thermal (DEM) buttons appear when "
            "Particle tracking is enabled in Analysis Type.\n"
            "* Undefined (Particle) receives the default DEM symmetrical "
            "condition for fluid surfaces without an explicit BC.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        av.addWidget(box, 1)
        right_stack.addWidget(apply_page)

        # 已应用条件：仅名称 + Remove（对称 BC 无参数）
        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.sym_edit_title = QLabel("Symmetrical boundary condition")
        self.sym_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.sym_edit_title)
        form = QFormLayout()
        self.ed_sym_name = QLineEdit("Symmetry")
        form.addRow("Name", self.ed_sym_name)
        ev.addLayout(form)
        note = QLabel(
            "No additional parameters. Use Remove to clear this "
            "condition from the selected region.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555; font-size:11px;")
        ev.addWidget(note)
        ev.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_sym_back = QPushButton("<< Apply")
        self.btn_sym_remove = QPushButton("Remove")
        row.addWidget(self.btn_sym_back)
        row.addWidget(self.btn_sym_remove)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        self.btn_sym_back.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_sym_remove.clicked.connect(self._remove_sym_bc)

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        return page

    def _sync_sym_bc_buttons(self, *_args) -> None:
        page = self._pages.get("bc_sym")
        if page is None:
            return
        for kind, (btn, gate) in getattr(page, "_sym_btns", {}).items():
            if not gate:
                btn.setVisible(True)
                btn.setEnabled(True)
                continue
            chk = self._atype_checks.get(gate)
            on = chk.isChecked() if chk is not None else False
            btn.setVisible(True)
            btn.setEnabled(on)

    def _selected_sym_region(self) -> str:
        page = self._pages.get("bc_sym")
        if page is None:
            return ""
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _on_sym_bc_sel(self) -> None:
        page = self._pages.get("bc_sym")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            page._sym_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        kind = it.data(0, Qt.UserRole) or "flow"
        labels = {
            "flow": "Symmetrical boundary condition",
            "particle": "Particle symmetrical boundary condition (DEM)",
            "thermal": "Particle symmetrical thermal boundary "
                       "condition (DEM)",
        }
        self.sym_edit_title.setText(labels.get(kind, it.text(0)))
        self.ed_sym_name.setText(it.text(0))
        page._sym_stack.setCurrentIndex(1)  # type: ignore[attr-defined]

    def _apply_sym_bc(self, kind: str, label: str) -> None:
        region = self._selected_sym_region()
        if not region:
            QMessageBox.information(
                self, "Symmetrical Boundary",
                "Select a region in the tree first.")
            return
        defaults = {
            "flow": "Symmetry",
            "particle": "ParticleSymmetry",
            "thermal": "ParticleThermalSymmetry",
        }
        name = defaults.get(kind, "Symmetry")
        # 同区域同 kind 复用名
        base = name
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        syms = sess.setdefault("sym_boundaries", [])
        existing = {r.get("name") for r in syms}
        n = 1
        while name in existing:
            n += 1
            name = f"{base}{n}"
        data = {"name": name, "kind": kind, "region": region,
                "label": label}
        syms.append(data)
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = ET.SubElement(cond_root, "condition")
            _ensure_child_text(el, "type", "CondBoundarySymmetry")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(el, "sym_kind", kind)
            regs = ET.SubElement(el, "regions")
            ET.SubElement(regs, "region").text = region
            self._ctx["xml_dirty"] = True
        self._fill_sym_bc_tree()

    def _remove_sym_bc(self) -> None:
        name = self.ed_sym_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    ctype = c.findtext("type") or ""
                    if (ctype in ("CondBoundarySymmetry",
                                  "SymmetricalBoundary")
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        syms = (self._ctx.get("session", {})
                .get("conditions", {})
                .get("sym_boundaries") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["sym_boundaries"] = [
            r for r in syms if r.get("name") != name]
        self._fill_sym_bc_tree()
        self._pages["bc_sym"]._sym_stack.setCurrentIndex(0)  # type: ignore

    def _fill_sym_bc_tree(self) -> None:
        page = self._pages.get("bc_sym")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        sheet_ic = _flow_sheet_icon(18)
        flow_ic = _sym_bc_icon("flow", 16)
        part_ic = _sym_bc_icon("particle", 16)

        defaults = [
            ("Undefined (Particle: All fluid boundary)", "particle"),
        ]
        regions: list[tuple[str, str]] = list(defaults)
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("face", "special_face"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            regions.append((name, "face"))

        cond_by_reg: dict[str, list[tuple[str, str]]] = {}
        if xml is not None:
            for cond in xml.conditions():
                ctype = cond.findtext("type") or ""
                if ctype not in (
                    "CondBoundarySymmetry", "SymmetricalBoundary",
                ):
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                ckind = (cond.findtext("sym_kind") or "flow").strip()
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked:
                    linked = [defaults[0][0]]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append((cname, ckind))

        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("sym_boundaries")) or []):
            reg = row.get("region") or defaults[0][0]
            cond_by_reg.setdefault(reg, []).append(
                (row.get("name") or "?", row.get("kind") or "flow"))

        for rname, _rkind in regions:
            parent = QTreeWidgetItem([rname])
            parent.setIcon(
                0, part_ic if "Particle" in rname else sheet_ic)
            lst.addTopLevelItem(parent)
            seen = set()
            for cname, ckind in cond_by_reg.get(rname, []):
                if cname in seen:
                    continue
                seen.add(cname)
                child = QTreeWidgetItem([cname])
                child.setIcon(
                    0, part_ic if ckind in ("particle", "thermal")
                    else flow_ic)
                child.setData(0, Qt.UserRole, ckind)
                parent.addChild(child)
            parent.setExpanded(True)

    # ------------------------------------------------------------------
    # Periodic Boundary
    # ------------------------------------------------------------------
    def _page_periodic_boundary(self) -> QWidget:
        """Periodic Boundary：条件表 + New/Edit/Delete 对话框。"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)

        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(_periodic_bc_icon(36).pixmap(36, 36))
        hdr.addWidget(ic)
        title = QLabel("Periodic boundary conditions")
        title.setStyleSheet("font-weight:bold; font-size:13px;")
        hdr.addWidget(title)
        hdr.addStretch(1)
        v.addLayout(hdr)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(
            ["Name", "Primary region", "Secondary region"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setIconSize(QSize(18, 18))
        v.addWidget(table, 1)
        page._cond_table = table  # type: ignore[attr-defined]
        page._cond_list = None  # type: ignore[attr-defined]

        tip = QLabel(
            "Click New... to define a pair of primary/secondary surface "
            "regions with rotation, translation, projection, and "
            "pressure difference.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(tip)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_periodic_new = QPushButton("New...")
        self.btn_periodic_new.setIcon(_periodic_bc_icon(20))
        self.btn_periodic_edit = QPushButton("Edit...")
        self.btn_periodic_delete = QPushButton("Delete")
        row.addWidget(self.btn_periodic_new)
        row.addWidget(self.btn_periodic_edit)
        row.addWidget(self.btn_periodic_delete)
        v.addLayout(row)

        self.btn_periodic_new.clicked.connect(
            lambda: self._edit_periodic_bc(new=True))
        self.btn_periodic_edit.clicked.connect(
            lambda: self._edit_periodic_bc(new=False))
        self.btn_periodic_delete.clicked.connect(self._delete_periodic_bc)
        table.itemDoubleClicked.connect(
            lambda *_: self._edit_periodic_bc(new=False))
        return page

    def _face_region_names(self) -> list[str]:
        names: list[str] = []
        xml = self._ctx.get("xml")
        if xml is None:
            return names
        regs = xml.section("regions")
        if regs is None:
            return names
        for cat in ("face", "special_face"):
            node = regs.find(cat)
            if node is None:
                continue
            for r in node.findall("region"):
                n = (r.findtext("name") or "").strip()
                if n:
                    names.append(n)
        return names

    def _edit_periodic_bc(self, *, new: bool) -> None:
        page = self._pages.get("bc_periodic")
        if page is None:
            return
        table: QTableWidget = page._cond_table  # type: ignore[attr-defined]
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        periods = sess.setdefault("periodic_boundaries", [])
        data = {
            "name": "Periodic1",
            "primary": "",
            "secondary": "",
            "rotation": "Do not consider",
            "translation": "Do not consider",
            "projection": "Plane",
            "pressure_diff": "0",
        }
        edit_idx = -1
        if not new:
            rows = table.selectionModel().selectedRows()
            if not rows:
                QMessageBox.information(
                    self, "Periodic Boundary",
                    "Select a condition to edit.")
                return
            edit_idx = rows[0].row()
            name_item = table.item(edit_idx, 0)
            cname = name_item.text() if name_item else ""
            hit = next((r for r in periods if r.get("name") == cname), None)
            if hit is None and self._ctx.get("xml") is not None:
                for cond in self._ctx["xml"].conditions():
                    ctype = cond.findtext("type") or ""
                    if (ctype in ("CondBoundaryPeriodic", "PeriodicBoundary")
                            and (cond.findtext("name") or "") == cname):
                        hit = {
                            "name": cname,
                            "primary": cond.findtext("primary") or "",
                            "secondary": cond.findtext("secondary") or "",
                            "rotation": cond.findtext("rotation")
                            or "Do not consider",
                            "translation": cond.findtext("translation")
                            or "Do not consider",
                            "projection": cond.findtext("projection")
                            or "Plane",
                            "pressure_diff": cond.findtext("pressure_diff")
                            or "0",
                        }
                        break
            if hit:
                data.update(hit)

        dlg = QDialog(self.window())
        dlg.setWindowTitle("Periodic Boundary Condition")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        ed_name = QLineEdit(data.get("name") or "Periodic1")
        faces = self._face_region_names()
        cb_pri = QComboBox()
        cb_pri.setEditable(True)
        cb_pri.addItems(faces)
        cb_pri.setCurrentText(data.get("primary") or "")
        cb_sec = QComboBox()
        cb_sec.setEditable(True)
        cb_sec.addItems(faces)
        cb_sec.setCurrentText(data.get("secondary") or "")
        cb_rot = QComboBox()
        cb_rot.addItems(["Do not consider", "Consider"])
        cb_rot.setCurrentText(data.get("rotation") or "Do not consider")
        cb_tr = QComboBox()
        cb_tr.addItems(["Do not consider", "Consider"])
        cb_tr.setCurrentText(data.get("translation") or "Do not consider")
        cb_proj = QComboBox()
        cb_proj.addItems(["Plane", "Cylinder"])
        cb_proj.setCurrentText(data.get("projection") or "Plane")
        ed_dp = QLineEdit(str(data.get("pressure_diff") or "0"))
        form.addRow("Name", ed_name)
        form.addRow("Primary region", cb_pri)
        form.addRow("Secondary region", cb_sec)
        form.addRow(QLabel("Parameter"))
        form.addRow("Rotation", cb_rot)
        form.addRow("Translation", cb_tr)
        form.addRow("Projection type", cb_proj)
        form.addRow("Pressure difference", ed_dp)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return

        name = ed_name.text().strip() or "Periodic1"
        row_data = {
            "name": name,
            "primary": cb_pri.currentText().strip(),
            "secondary": cb_sec.currentText().strip(),
            "rotation": cb_rot.currentText(),
            "translation": cb_tr.currentText(),
            "projection": cb_proj.currentText(),
            "pressure_diff": ed_dp.text().strip() or "0",
        }
        if edit_idx >= 0:
            old_name = table.item(edit_idx, 0).text()
            periods[:] = [r for r in periods if r.get("name") != old_name]
        else:
            periods[:] = [r for r in periods if r.get("name") != name]
        periods.append(row_data)

        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            target = (table.item(edit_idx, 0).text()
                      if edit_idx >= 0 else name)
            for c in list(cond_root.findall("condition")):
                ctype = c.findtext("type") or ""
                if (ctype in ("CondBoundaryPeriodic", "PeriodicBoundary")
                        and (c.findtext("name") or "") == target):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondBoundaryPeriodic")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(el, "primary", row_data["primary"])
            _ensure_child_text(el, "secondary", row_data["secondary"])
            _ensure_child_text(el, "rotation", row_data["rotation"])
            _ensure_child_text(el, "translation", row_data["translation"])
            _ensure_child_text(el, "projection", row_data["projection"])
            _ensure_child_text(
                el, "pressure_diff", row_data["pressure_diff"])
            self._ctx["xml_dirty"] = True
        self._fill_periodic_bc_list()

    def _delete_periodic_bc(self) -> None:
        page = self._pages.get("bc_periodic")
        if page is None:
            return
        table: QTableWidget = page._cond_table  # type: ignore[attr-defined]
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        name = table.item(rows[0].row(), 0).text()
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    ctype = c.findtext("type") or ""
                    if (ctype in ("CondBoundaryPeriodic", "PeriodicBoundary")
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        periods = (self._ctx.get("session", {})
                   .get("conditions", {})
                   .get("periodic_boundaries") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["periodic_boundaries"] = [
            r for r in periods if r.get("name") != name]
        self._fill_periodic_bc_list()

    def _fill_periodic_bc_list(self) -> None:
        page = self._pages.get("bc_periodic")
        if page is None:
            return
        table: QTableWidget = page._cond_table  # type: ignore[attr-defined]
        table.setRowCount(0)
        ic = _periodic_bc_icon(16)
        rows: list[dict] = []
        seen = set()
        xml = self._ctx.get("xml")
        if xml is not None:
            for cond in xml.conditions():
                ctype = cond.findtext("type") or ""
                if ctype not in (
                    "CondBoundaryPeriodic", "PeriodicBoundary",
                ):
                    continue
                name = cond.findtext("name") or "(unnamed)"
                if name in seen:
                    continue
                seen.add(name)
                rows.append({
                    "name": name,
                    "primary": cond.findtext("primary") or "",
                    "secondary": cond.findtext("secondary") or "",
                })
        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("periodic_boundaries")) or []):
            name = row.get("name") or "?"
            if name in seen:
                # session 覆盖 xml 同名行的区域显示
                for i, r in enumerate(rows):
                    if r.get("name") == name:
                        rows[i] = {
                            "name": name,
                            "primary": row.get("primary") or "",
                            "secondary": row.get("secondary") or "",
                        }
                        break
                continue
            seen.add(name)
            rows.append({
                "name": name,
                "primary": row.get("primary") or "",
                "secondary": row.get("secondary") or "",
            })
        for r in rows:
            i = table.rowCount()
            table.insertRow(i)
            name_item = QTableWidgetItem(r["name"])
            name_item.setIcon(ic)
            table.setItem(i, 0, name_item)
            table.setItem(i, 1, QTableWidgetItem(r.get("primary") or ""))
            table.setItem(i, 2, QTableWidgetItem(r.get("secondary") or ""))

    # ------------------------------------------------------------------
    # Source Condition
    # ------------------------------------------------------------------
    def _page_source_condition(self) -> QWidget:
        """Source Condition：区域树 + New condition 示意图 / 源项编辑。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_source_bc_sel)

        right_stack = QStackedWidget()
        page._source_stack = right_stack  # type: ignore[attr-defined]

        new_page = QWidget()
        nv = QVBoxLayout(new_page)
        nv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("New condition")
        bv = QVBoxLayout(box)
        bv.setSpacing(6)
        page._source_btns = {}  # type: ignore[attr-defined]
        ic_sz = 36
        for kind, label, gate in _SOURCE_BC_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_source_bc_icon(kind, ic_sz))
            btn.setIconSize(QSize(ic_sz, ic_sz))
            btn.setMinimumHeight(44)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }"
                "QPushButton:disabled { color: #9e9e9e; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._open_source_bc_editor(k, lab, new=True))
            bv.addWidget(btn)
            page._source_btns[kind] = (btn, gate)  # type: ignore[attr-defined]
        btn_more = QPushButton("More condition types...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog("source"))
        bv.addWidget(btn_more)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Source Condition"))
        bv.addWidget(btn_ex)
        tip = QLabel(
            "* Mass source (Volume / Face) buttons appear when "
            "Mixed gas is enabled in Analysis Type.\n"
            "* Select a volume or face region, then click a New "
            "condition button to edit Type / Variable / Source value.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        nv.addWidget(box, 1)
        right_stack.addWidget(new_page)

        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.source_edit_title = QLabel("Source term")
        self.source_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.source_edit_title)
        form = QFormLayout()
        self.ed_source_name = QLineEdit("Source")
        self.cb_source_type = QComboBox()
        form.addRow("Name", self.ed_source_name)
        form.addRow("Type", self.cb_source_type)
        ev.addLayout(form)
        self.source_param_tree = QTreeWidget()
        self.source_param_tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.source_param_tree.setRootIsDecorated(False)
        self.source_param_tree.setAlternatingRowColors(True)
        ev.addWidget(self.source_param_tree, 1)
        self.source_desc = QLabel(
            "The source term is set to a constant value.")
        self.source_desc.setWordWrap(True)
        self.source_desc.setStyleSheet(
            "color:#444; font-size:11px; background:#f5f5f5; "
            "padding:6px; border:1px solid #e0e0e0;")
        ev.addWidget(self.source_desc)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_source_back_new = QPushButton("<< New condition")
        self.btn_source_remove = QPushButton("Remove")
        self.btn_source_set = QPushButton("Set")
        row.addWidget(self.btn_source_back_new)
        row.addWidget(self.btn_source_remove)
        row.addWidget(self.btn_source_set)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        self.cb_source_type.currentIndexChanged.connect(
            self._rebuild_source_params)
        self.btn_source_back_new.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_source_set.clicked.connect(self._set_source_bc)
        self.btn_source_remove.clicked.connect(self._remove_source_bc)
        page._source_kind = "source"  # type: ignore[attr-defined]

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        return page

    def _rebuild_source_params(self, *_args) -> None:
        tree = self.source_param_tree
        tree.clear()
        page = self._pages.get("source")
        kind = getattr(page, "_source_kind", "source") if page else "source"
        typ = self.cb_source_type.currentText()
        rows: list[tuple[str, str, str]] = []
        desc = "The source term is set to a constant value."
        if kind in ("source", "area"):
            rows.append(("Variable", "Heat source", ""))
            if "total" in typ:
                unit = "W" if "Heat" in "Heat source" else "-"
                rows.append(("Source value", "0", unit))
                desc = ("The source term is set to a constant value.\n"
                        "Si = (VV / A) · Ai")
            elif "per unit" in typ:
                rows.append(("Source value", "0", "W/m3" if kind == "source"
                             else "W/m2"))
            elif "Proportional" in typ:
                rows += [("Coefficient", "0", "-"),
                         ("Base value", "0", "-")]
                desc = "S = C · (V − F) · Δ"
            elif "Mapping" in typ:
                rows += [("Source value", "(mapping)", ""),
                         ("Specify total amount of source value",
                          "Do not specify", "")]
            else:
                rows.append(("Source value", "0", "-"))
        elif kind in ("mass_vol", "mass_face"):
            rows += [
                ("Mixed gas species", "(default)", ""),
                ("Source value", "0", "kg/s" if "total" in typ else "kg/m3/s"),
                ("Velocity conditions of generated mass",
                 "Velocity of field", ""),
                ("Temperature of generated mass", "Temperature of field", ""),
                ("Turbulence conditions of generated mass",
                 "Turbulence of field", ""),
            ]
        elif kind in ("pdrop_vol", "pdrop_face"):
            rows += [
                ("Equation type", "Type 1", ""),
                ("CC", "0", "-"),
                ("BB", "0", "-"),
            ]
            if typ == "Anisotropic":
                rows += [
                    ("1st direction (X)", "1", "-"),
                    ("1st direction (Y)", "0", "-"),
                    ("1st direction (Z)", "0", "-"),
                    ("Flow-straightening effect", "Do not consider", ""),
                ]
            desc = "Pressure drop source based on velocity magnitude."
        elif kind == "accel":
            rows += [
                ("X component of Acceleration", "0", "m/s2"),
                ("Y component of Acceleration", "0", "m/s2"),
                ("Z component of Acceleration", "0", "m/s2"),
            ]
            desc = "Body-force acceleration applied to the selected region."
        else:  # friction
            rows += [
                ("Coefficient of kinetic friction", "0.3", "-"),
                ("Type of vertical load", "Per unit area", ""),
                ("Vertical load", "0", "Pa"),
                ("Limit parts which give friction heat", "Do not limit", ""),
            ]
            desc = "Frictional heat generated at contacting parts."
        for name, val, unit in rows:
            tree.addTopLevelItem(QTreeWidgetItem([name, val, unit, ""]))
        self.source_desc.setText(desc)

    def _sync_source_bc_buttons(self, *_args) -> None:
        page = self._pages.get("source")
        if page is None:
            return
        for kind, (btn, gate) in getattr(page, "_source_btns", {}).items():
            if not gate:
                btn.setVisible(True)
                btn.setEnabled(True)
                continue
            chk = self._atype_checks.get(gate)
            on = chk.isChecked() if chk is not None else False
            btn.setVisible(True)
            btn.setEnabled(on)

    def _open_source_bc_editor(self, kind: str, label: str, *,
                               new: bool = True, name: str = "") -> None:
        page = self._pages["source"]
        stack: QStackedWidget = page._source_stack  # type: ignore[attr-defined]
        page._source_kind = kind  # type: ignore[attr-defined]
        titles = {
            "source": "Source term",
            "area": "Area source condition",
            "mass_vol": "Mass source condition (Volume)",
            "mass_face": "Mass source condition (Face)",
            "pdrop_vol": "Pressure drop (Volume)",
            "pdrop_face": "Pressure drop (Face)",
            "accel": "Acceleration condition",
            "friction": "Frictional heat",
        }
        self.source_edit_title.setText(titles.get(kind, label))
        defaults = {
            "source": "Source", "area": "AreaSource",
            "mass_vol": "MassSource", "mass_face": "MassSourceFace",
            "pdrop_vol": "PressureDrop", "pdrop_face": "PressureDropFace",
            "accel": "Acceleration", "friction": "FrictionHeat",
        }
        self.ed_source_name.setText(name or defaults.get(kind, "Source"))
        self.cb_source_type.blockSignals(True)
        self.cb_source_type.clear()
        for t in _SOURCE_BC_TYPES.get(kind, ["Constant source (total)"]):
            self.cb_source_type.addItem(t)
        self.cb_source_type.blockSignals(False)
        self._rebuild_source_params()
        stack.setCurrentIndex(1)

    def _selected_source_region(self) -> str:
        page = self._pages.get("source")
        if page is None:
            return ""
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _on_source_bc_sel(self) -> None:
        page = self._pages.get("source")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            page._source_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        kind = it.data(0, Qt.UserRole) or "source"
        self._open_source_bc_editor(
            kind, it.text(0), new=False, name=it.text(0))

    def _set_source_bc(self) -> None:
        name = self.ed_source_name.text().strip() or "Source"
        page = self._pages["source"]
        kind = getattr(page, "_source_kind", "source")
        region = self._selected_source_region() or "FluidRegion"
        typ = self.cb_source_type.currentText()
        params = {}
        root = self.source_param_tree.invisibleRootItem()
        for i in range(root.childCount()):
            it = root.child(i)
            params[it.text(0)] = it.text(1)
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        sources = sess.setdefault("source_conditions", [])
        data = {"name": name, "kind": kind, "region": region,
                "type": typ, "params": params}
        hit = next((r for r in sources if r.get("name") == name), None)
        if hit is None:
            sources.append(data)
        else:
            hit.update(data)
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            for c in cond_root.findall("condition"):
                if (c.findtext("type") == "CondSource"
                        and (c.findtext("name") or "") == name):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondSource")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(el, "source_kind", kind)
            _ensure_child_text(el, "source_type", typ)
            regs = el.find("regions")
            if regs is None:
                regs = ET.SubElement(el, "regions")
            else:
                for ch in list(regs):
                    regs.remove(ch)
            ET.SubElement(regs, "region").text = region
            self._ctx["xml_dirty"] = True
        self._fill_source_bc_tree()
        page._source_stack.setCurrentIndex(0)  # type: ignore[attr-defined]

    def _remove_source_bc(self) -> None:
        name = self.ed_source_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    if (c.findtext("type") == "CondSource"
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        sources = (self._ctx.get("session", {})
                   .get("conditions", {})
                   .get("source_conditions") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["source_conditions"] = [
            r for r in sources if r.get("name") != name]
        self._fill_source_bc_tree()
        self._pages["source"]._source_stack.setCurrentIndex(0)  # type: ignore

    def _fill_source_bc_tree(self) -> None:
        page = self._pages.get("source")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        vol_ic = _ic_region_icon("volume", 18)
        face_ic = _flow_sheet_icon(18)
        src_ic = _source_bc_icon("source", 16)

        regions: list[tuple[str, str]] = []
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("fluid", "solid", "volume", "face", "special_face"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            kind = ("face" if cat in ("face", "special_face")
                                    else "volume")
                            regions.append((name, kind))
        if not regions:
            regions = [("FluidRegion", "volume")]

        cond_by_reg: dict[str, list[tuple[str, str]]] = {}
        if xml is not None:
            for cond in xml.conditions():
                if (cond.findtext("type") or "") != "CondSource":
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                ckind = (cond.findtext("source_kind") or "source").strip()
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked and regions:
                    linked = [regions[0][0]]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append((cname, ckind))

        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("source_conditions")) or []):
            reg = row.get("region") or (regions[0][0] if regions else "")
            cond_by_reg.setdefault(reg, []).append(
                (row.get("name") or "?", row.get("kind") or "source"))

        for rname, rkind in regions:
            parent = QTreeWidgetItem([rname])
            parent.setIcon(0, face_ic if rkind == "face" else vol_ic)
            lst.addTopLevelItem(parent)
            seen = set()
            for cname, ckind in cond_by_reg.get(rname, []):
                if cname in seen:
                    continue
                seen.add(cname)
                child = QTreeWidgetItem([cname])
                child.setIcon(
                    0, _source_bc_icon(ckind, 16)
                    if ckind in {k for k, _l, _g in _SOURCE_BC_NEW_BUTTONS}
                    else src_ic)
                child.setData(0, Qt.UserRole, ckind)
                parent.addChild(child)
            parent.setExpanded(True)

    # ------------------------------------------------------------------
    # Fixed Condition
    # ------------------------------------------------------------------
    def _page_fixed_condition(self) -> QWidget:
        """Fixed Condition：区域树 + New condition 示意图 / 固定值编辑。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Region / Condition"])
        lst.setRootIsDecorated(True)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]
        lst.itemSelectionChanged.connect(self._on_fixed_bc_sel)

        right_stack = QStackedWidget()
        page._fixed_stack = right_stack  # type: ignore[attr-defined]

        new_page = QWidget()
        nv = QVBoxLayout(new_page)
        nv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("New condition")
        bv = QVBoxLayout(box)
        bv.setSpacing(8)
        btn = QPushButton("Fixed condition")
        btn.setIcon(_fixed_bc_icon(36))
        btn.setIconSize(QSize(36, 36))
        btn.setMinimumHeight(46)
        btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 8px; "
            "font-size: 12px; }"
            "QPushButton:hover { background: #e3f2fd; }")
        btn.clicked.connect(
            lambda: self._open_fixed_bc_editor(new=True))
        bv.addWidget(btn)
        page._fixed_btn = btn  # type: ignore[attr-defined]
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda: self._show_existing("Fixed Condition"))
        bv.addWidget(btn_ex)
        tip = QLabel(
            "* Select a region, then click Fixed condition to pin a "
            "variable to a constant value (e.g. Temperature).")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        bv.addWidget(tip)
        bv.addStretch(1)
        nv.addWidget(box, 1)
        right_stack.addWidget(new_page)

        edit = QWidget()
        ev = QVBoxLayout(edit)
        ev.setContentsMargins(0, 0, 0, 0)
        self.fixed_edit_title = QLabel("Fixed condition")
        self.fixed_edit_title.setStyleSheet("font-weight:bold;")
        ev.addWidget(self.fixed_edit_title)
        form = QFormLayout()
        self.ed_fixed_name = QLineEdit("Fix")
        form.addRow("Name", self.ed_fixed_name)
        ev.addLayout(form)
        self.fixed_param_tree = QTreeWidget()
        self.fixed_param_tree.setHeaderLabels(
            ["Parameter", "Value", "Unit", "Type"])
        self.fixed_param_tree.setRootIsDecorated(False)
        self.fixed_param_tree.setAlternatingRowColors(True)
        ev.addWidget(self.fixed_param_tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_fixed_back_new = QPushButton("<< New condition")
        self.btn_fixed_remove = QPushButton("Remove")
        self.btn_fixed_set = QPushButton("Set")
        row.addWidget(self.btn_fixed_back_new)
        row.addWidget(self.btn_fixed_remove)
        row.addWidget(self.btn_fixed_set)
        ev.addLayout(row)
        right_stack.addWidget(edit)

        self.btn_fixed_back_new.clicked.connect(
            lambda: right_stack.setCurrentIndex(0))
        self.btn_fixed_set.clicked.connect(self._set_fixed_bc)
        self.btn_fixed_remove.clicked.connect(self._remove_fixed_bc)
        self._rebuild_fixed_params()

        h.addWidget(left, 2)
        h.addWidget(right_stack, 3)
        return page

    def _rebuild_fixed_params(self) -> None:
        tree = self.fixed_param_tree
        tree.clear()
        tree.addTopLevelItem(
            QTreeWidgetItem(["Variable", "Temperature", "", ""]))
        tree.addTopLevelItem(
            QTreeWidgetItem(["Constant value", "0", "C", ""]))

    def _open_fixed_bc_editor(self, *, new: bool = True,
                              name: str = "") -> None:
        page = self._pages["fixed"]
        stack: QStackedWidget = page._fixed_stack  # type: ignore[attr-defined]
        self.ed_fixed_name.setText(name or "Fix")
        if new:
            self._rebuild_fixed_params()
        stack.setCurrentIndex(1)

    def _selected_fixed_region(self) -> str:
        page = self._pages.get("fixed")
        if page is None:
            return ""
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return ""
        it = items[0]
        if it.parent() is not None:
            return it.parent().text(0)
        return it.text(0)

    def _on_fixed_bc_sel(self) -> None:
        page = self._pages.get("fixed")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        items = lst.selectedItems()
        if not items:
            return
        it = items[0]
        if it.parent() is None:
            page._fixed_stack.setCurrentIndex(0)  # type: ignore[attr-defined]
            return
        self._open_fixed_bc_editor(new=False, name=it.text(0))

    def _set_fixed_bc(self) -> None:
        name = self.ed_fixed_name.text().strip() or "Fix"
        region = self._selected_fixed_region() or "FluidRegion"
        params = {}
        root = self.fixed_param_tree.invisibleRootItem()
        for i in range(root.childCount()):
            it = root.child(i)
            params[it.text(0)] = it.text(1)
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        fixes = sess.setdefault("fixed_conditions", [])
        data = {"name": name, "region": region, "params": params}
        hit = next((r for r in fixes if r.get("name") == name), None)
        if hit is None:
            fixes.append(data)
        else:
            hit.update(data)
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is None:
                cond_root = ET.SubElement(xml.root, "conditions")
            el = None
            for c in cond_root.findall("condition"):
                if (c.findtext("type") == "CondFix"
                        and (c.findtext("name") or "") == name):
                    el = c
                    break
            if el is None:
                el = ET.SubElement(cond_root, "condition")
                _ensure_child_text(el, "type", "CondFix")
            _ensure_child_text(el, "name", name)
            _ensure_child_text(
                el, "variable", params.get("Variable", "Temperature"))
            _ensure_child_text(
                el, "const_value", params.get("Constant value", "0"))
            regs = el.find("regions")
            if regs is None:
                regs = ET.SubElement(el, "regions")
            else:
                for ch in list(regs):
                    regs.remove(ch)
            ET.SubElement(regs, "region").text = region
            self._ctx["xml_dirty"] = True
        self._fill_fixed_bc_tree()
        self._pages["fixed"]._fixed_stack.setCurrentIndex(0)  # type: ignore

    def _remove_fixed_bc(self) -> None:
        name = self.ed_fixed_name.text().strip()
        if not name:
            return
        xml = self._ctx.get("xml")
        if xml is not None:
            cond_root = xml.section("conditions")
            if cond_root is not None:
                for c in list(cond_root.findall("condition")):
                    if (c.findtext("type") == "CondFix"
                            and (c.findtext("name") or "") == name):
                        cond_root.remove(c)
                        self._ctx["xml_dirty"] = True
        fixes = (self._ctx.get("session", {})
                 .get("conditions", {})
                 .get("fixed_conditions") or [])
        self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})["fixed_conditions"] = [
            r for r in fixes if r.get("name") != name]
        self._fill_fixed_bc_tree()
        self._pages["fixed"]._fixed_stack.setCurrentIndex(0)  # type: ignore

    def _fill_fixed_bc_tree(self) -> None:
        page = self._pages.get("fixed")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        lst.clear()
        xml = self._ctx.get("xml")
        vol_ic = _ic_region_icon("volume", 18)
        fix_ic = _fixed_bc_icon(16)

        regions: list[str] = []
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in ("fluid", "solid", "volume"):
                    node = regs.find(cat)
                    if node is None:
                        continue
                    for r in node.findall("region"):
                        name = (r.findtext("name") or "").strip()
                        if name:
                            regions.append(name)
        if not regions:
            regions = ["FluidRegion"]

        cond_by_reg: dict[str, list[str]] = {}
        if xml is not None:
            for cond in xml.conditions():
                if (cond.findtext("type") or "") != "CondFix":
                    continue
                cname = cond.findtext("name") or "(unnamed)"
                linked = []
                regs_el = cond.find("regions")
                if regs_el is not None:
                    for ch in list(regs_el):
                        t = (ch.text or "").strip()
                        if t:
                            linked.append(t)
                if not linked:
                    linked = [regions[0]]
                for reg in linked:
                    cond_by_reg.setdefault(reg, []).append(cname)

        for row in ((self._ctx.get("session", {})
                     .get("conditions", {})
                     .get("fixed_conditions")) or []):
            reg = row.get("region") or regions[0]
            cond_by_reg.setdefault(reg, []).append(row.get("name") or "?")

        for rname in regions:
            parent = QTreeWidgetItem([rname])
            parent.setIcon(0, vol_ic)
            lst.addTopLevelItem(parent)
            seen = set()
            for cname in cond_by_reg.get(rname, []):
                if cname in seen:
                    continue
                seen.add(cname)
                child = QTreeWidgetItem([cname])
                child.setIcon(0, fix_ic)
                parent.addChild(child)
            parent.setExpanded(True)

    def _page_new_condition(
            self, title: str, buttons: list[str],
            note: str = "") -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Name", "Type"])
        lst.setRootIsDecorated(False)
        lst.setAlternatingRowColors(True)
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]

        right = QGroupBox("New condition")
        rv = QVBoxLayout(right)
        for label in buttons:
            btn = QPushButton(label)
            btn.setMinimumHeight(36)
            btn.clicked.connect(
                lambda _=False, t=title, lab=label:
                self._stub_new_condition(t, lab))
            rv.addWidget(btn)
        btn_ex = QPushButton("Existing Conditions...")
        btn_ex.clicked.connect(
            lambda _=False, t=title: self._show_existing(t))
        rv.addWidget(btn_ex)
        if note:
            tip = QLabel(note)
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#555; font-size:11px;")
            rv.addWidget(tip)
        rv.addStretch(1)
        h.addWidget(left, 2)
        h.addWidget(right, 3)
        return page

    def _page_analysis_control(self) -> QWidget:
        """Analysis Control：子导航树 + 各参数页（对齐 scFLOWpre）。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        nav = QTreeWidget()
        nav.setHeaderHidden(True)
        nav.setRootIsDecorated(True)
        nav.setIconSize(QSize(16, 16))
        nav.setMinimumWidth(200)
        nav.setMaximumWidth(280)
        # scFLOWpre：分组与一级叶子用蓝圆图标；子项缩进且无图标
        leaf_ic = _ac_nav_icon("leaf", 16)
        self._ac_nav_items: dict[str, QTreeWidgetItem] = {}
        for key, label, children in _AC_NAV_TREE:
            if children is None:
                it = QTreeWidgetItem([label])
                it.setIcon(0, leaf_ic)
                it.setData(0, Qt.UserRole, key)
                nav.addTopLevelItem(it)
                self._ac_nav_items[key] = it
            else:
                parent = QTreeWidgetItem([label])
                parent.setIcon(0, leaf_ic)
                parent.setData(0, Qt.UserRole, key)
                nav.addTopLevelItem(parent)
                self._ac_nav_items[key] = parent
                for ck, clab in children:
                    ch = QTreeWidgetItem([clab])
                    ch.setData(0, Qt.UserRole, ck)
                    parent.addChild(ch)
                    self._ac_nav_items[ck] = ch
                parent.setExpanded(True)

        stack = QStackedWidget()
        self._ac_stack = stack
        self._ac_pages: dict[str, QWidget] = {}
        self._ac_page_order: list[str] = []

        def add_page(key: str, w: QWidget) -> None:
            self._ac_pages[key] = w
            self._ac_page_order.append(key)
            stack.addWidget(w)

        add_page("batch", self._ac_page_batch())
        add_page("undr", self._ac_page_undr())
        add_page("dtsr", self._ac_page_dtsr())
        add_page("stab_v", self._ac_page_stab_v())
        add_page("stab_e", self._ac_page_stab_e())
        add_page("loop", self._ac_page_loop())
        add_page("loop_eq", self._ac_page_loop_eq())
        add_page("upwd", self._ac_page_upwd())
        add_page("time_acc", self._ac_page_time_acc())
        add_page("gradient", self._ac_page_gradient())
        add_page("diffusion", self._ac_page_diffusion())
        add_page("solv", self._ac_page_solv())
        add_page("sted", self._ac_page_sted())
        add_page("pcty", self._ac_page_pcty())
        add_page("restart", self._ac_page_restart())
        add_page("mapping", self._ac_page_mapping())
        add_page("turb", self._ac_page_form(
            "Set the option parameters for turbulent flow.",
            [
                ("Eddy viscosity coefficient", "Default",
                 ["Default", "Specify"]),
                ("Set the correction of eddy viscosity", "Default",
                 ["Default", "Do not perform correction", "Specify"]),
                ("Adaptive wall function", "Default",
                 ["Default", "0", "1"]),
            ]))
        add_page("equa", self._ac_page_form(
            "Set default values of equations and start cycle of "
            "calculation for equations.",
            [
                ("Calculation cycle for equations", "Do not control",
                 ["Do not control", "Control"]),
                ("Momentum and mass conservation equation",
                 "Solve all fluids at once",
                 ["Solve all fluids at once",
                  "Solve for each fluid material"]),
                ("Face gradient calculation method for the cross term "
                 "of the stress",
                 "Element gradient interpolation",
                 ["Element gradient interpolation",
                  "Alpha-damping method"]),
                ("External force term — Default setting of treatment",
                 "Obtain analytically",
                 ["Obtain analytically",
                  "Obtain from gradient calculation"]),
            ]))
        add_page("bund", self._ac_page_form(
            "Set the option parameters of boundary conditions.",
            [
                ("Correction of velocity near the wall "
                 "(Compressible fluid)", "Default",
                 ["Default", "Correct", "Do not correct"]),
                ("Correction of velocity near the wall "
                 "(Incompressible fluid)", "Default",
                 ["Default", "Correct", "Do not correct"]),
                ("Smoothing a pressure gradient used in pressure "
                 "gradient term", "Default",
                 ["Default", "Do not smooth", "Average (each component)",
                  "Average (magnitude)", "Ignore pressure gradient"]),
                ("Application of wall velocity in velocity gradient "
                 "calculation", "Default",
                 ["Default", "Apply", "Do not apply"]),
                ("Application of wall temperature in temperature "
                 "gradient calculation (fluid region)", "Default",
                 ["Default", "Apply", "Do not apply"]),
            ]))
        add_page("geometry", self._ac_page_form(
            "Set the method of calculation for element geometry.",
            [
                ("Method for calculating the coordinate of element "
                 "center", "Default",
                 ["Default", "Volume-weighted", "Node average"]),
                ("Method for calculating the coordinate of face "
                 "center", "Default",
                 ["Default", "Area-weighted", "Node average"]),
            ]))
        add_page("perf", self._ac_page_form(
            "Set output conditions of information during iterations "
            "in each cycle.",
            [
                ("Memory reduction control", "Do not apply",
                 ["Do not apply", "Apply"]),
                ("Setting of Face weighting for decomposition",
                 "Do not apply",
                 ["Do not apply", "Specify value"]),
            ]))
        add_page("mesh", self._ac_page_form(
            "Set the treatment of a region without mesh element.",
            [
                ("Stop calculation if there is an empty part",
                 "Default", ["Default", "Stop", "Do not stop"]),
                ("Stop calculation if there is an empty volume region",
                 "Default", ["Default", "Stop", "Do not stop"]),
                ("Stop calculation if there is an empty surface region",
                 "Default", ["Default", "Stop", "Do not stop"]),
            ]))
        add_page("domain", self._ac_page_form(
            "Set the parameters of domain partitioning in parallel "
            "computation.",
            [
                ("Partition algorithm", "Graph partitioning by ParMETIS",
                 ["Graph partitioning by ParMETIS",
                  "Graph partitioning by PT-Scotch",
                  "Rectangular partitioning by RCB method",
                  "User-defined partitioning"]),
                ("Restrict partitioning along axes", "Do not restrict",
                 ["Do not restrict", "Restrict"]),
            ]))

        def on_nav(cur: Optional[QTreeWidgetItem],
                   _prev: Optional[QTreeWidgetItem] = None) -> None:
            if cur is None:
                return
            key = cur.data(0, Qt.UserRole)
            if not key:
                return
            # 点到分组：选第一个子叶
            if key in ("stab", "loop_grp", "disc", "opts"):
                if cur.childCount():
                    nav.setCurrentItem(cur.child(0))
                return
            w = self._ac_pages.get(key)
            if w is not None:
                stack.setCurrentWidget(w)

        nav.currentItemChanged.connect(on_nav)
        nav.setCurrentItem(self._ac_nav_items["batch"])
        page._ac_nav = nav  # type: ignore[attr-defined]
        h.addWidget(nav, 2)
        h.addWidget(stack, 5)
        return page

    def _ac_page_batch(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Set various parameters of analysis control in a batch."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Type of parameters"))
        self.cb_ac_batch = QComboBox()
        self.cb_ac_batch.addItem("Default", "default")
        self.cb_ac_batch.addItem(
            "For transient analysis: Accuracy/Stability-oriented "
            "parameters", "transient_acc")
        row.addWidget(self.cb_ac_batch, 1)
        self.btn_ac_batch_apply = QPushButton("Apply")
        self.btn_ac_batch_apply.clicked.connect(self._ac_apply_batch)
        row.addWidget(self.btn_ac_batch_apply)
        v.addLayout(row)
        v.addStretch(1)
        return w

    def _ac_page_undr(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set the under-relaxation coefficient."))
        self.chk_ac_undr_transient = QCheckBox(
            "Use under-relaxation coefficient in the loop of the "
            "transient analysis.")
        v.addWidget(self.chk_ac_undr_transient)
        body = QHBoxLayout()
        self.ac_undr_tree = QTreeWidget()
        self.ac_undr_tree.setHeaderLabels(
            ["Equation", "Type", "Detail"])
        self.ac_undr_tree.setRootIsDecorated(False)
        self.ac_undr_tree.setAlternatingRowColors(True)
        for label, tag, val in _AC_UNDR_ROWS:
            it = QTreeWidgetItem(
                [label, "Constant value", f"Value : {val:g}"])
            it.setData(0, Qt.UserRole, tag)
            self.ac_undr_tree.addTopLevelItem(it)
        body.addWidget(self.ac_undr_tree, 3)
        side = QVBoxLayout()
        self.cb_ac_undr_type = QComboBox()
        self.cb_ac_undr_type.addItems([
            "Constant value", "Table", "Formatted Script",
            "Unformatted Script", "User Defined Function",
        ])
        self.sp_ac_undr_val = _spin_f(6, 0.0, 10.0, 0.8)
        side.addWidget(self.cb_ac_undr_type)
        side.addWidget(self.sp_ac_undr_val)
        btn_apply = QPushButton("Apply")
        btn_def = QPushButton("Default")
        btn_apply.clicked.connect(self._ac_undr_apply_sel)
        btn_def.clicked.connect(self._ac_undr_default_sel)
        side.addWidget(btn_apply)
        side.addWidget(btn_def)
        side.addStretch(1)
        body.addLayout(side, 1)
        v.addLayout(body, 1)
        self.ac_undr_tree.itemSelectionChanged.connect(
            self._ac_undr_on_sel)
        return w

    def _ac_page_dtsr(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set pseudo time step relaxation."))
        self.ac_dtsr_tree = QTreeWidget()
        self.ac_dtsr_tree.setHeaderLabels(
            ["Equation", "Target", "Type", "Detail"])
        self.ac_dtsr_tree.setRootIsDecorated(False)
        self.ac_dtsr_tree.setAlternatingRowColors(True)
        v.addWidget(self.ac_dtsr_tree, 1)
        box = QGroupBox("Parameter")
        bf = QFormLayout(box)
        self.cb_ac_dtsr_eq = QComboBox()
        self.cb_ac_dtsr_eq.addItems([
            "Momentum", "Energy", "Turbulence", "Diffusion",
            "Volume of fluid", "Cavitation",
        ])
        self.cb_ac_dtsr_target = QComboBox()
        self.cb_ac_dtsr_target.addItems([
            "Incompressible fluid", "Compressible fluid", "Solid",
            "Porous media",
        ])
        self.cb_ac_dtsr_type = QComboBox()
        self.cb_ac_dtsr_type.addItems([
            "Time step", "Courant number",
            "Courant number (Power Mean)",
            "Courant number (Each Element)",
            "No pseudo timestep relaxation",
        ])
        self.cb_ac_dtsr_type.setCurrentIndex(3)
        self.sp_ac_dtsr_val = _spin_f(4, 0.0, 1e9, 20.0)
        bf.addRow("Equation", self.cb_ac_dtsr_eq)
        bf.addRow("Target", self.cb_ac_dtsr_target)
        row_t = QHBoxLayout()
        row_t.addWidget(self.cb_ac_dtsr_type, 1)
        btn_def = QPushButton("Default")
        btn_def.clicked.connect(lambda: (
            self.cb_ac_dtsr_type.setCurrentIndex(3),
            self.sp_ac_dtsr_val.setValue(20.0)))
        row_t.addWidget(btn_def)
        bf.addRow("Type", row_t)
        tip = QLabel(
            "* Set the default type and value for the incompressible "
            "flow analysis.")
        tip.setStyleSheet("color:#555; font-size:11px;")
        bf.addRow(tip)
        bf.addRow("Value", self.sp_ac_dtsr_val)
        v.addWidget(box)
        brow = QHBoxLayout()
        brow.addWidget(QPushButton("Initial Pseudo Time Step Relaxation..."))
        brow.addWidget(QPushButton("Detailed Settings..."))
        brow.addStretch(1)
        btn_reg = QPushButton("Register")
        btn_reg.clicked.connect(self._ac_dtsr_register)
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self._ac_dtsr_delete)
        brow.addWidget(btn_reg)
        brow.addWidget(btn_del)
        v.addLayout(brow)
        return w

    def _ac_page_stab_v(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set the parameters to avoid the divergence."))
        self.ac_stabv_tree = QTreeWidget()
        self.ac_stabv_tree.setHeaderLabels(
            ["Variable", "Stop calculation",
             "Treatment of abnormal element"])
        self.ac_stabv_tree.setRootIsDecorated(False)
        self.ac_stabv_tree.setAlternatingRowColors(True)
        self.ac_stabv_tree.addTopLevelItem(QTreeWidgetItem([
            "Velocity X",
            "Stop(Upper limit: 1e+20, Lower limit: -1e+20)",
            "No treatment",
        ]))
        v.addWidget(self.ac_stabv_tree, 1)
        box = QGroupBox("Parameter")
        bf = QFormLayout(box)
        self.cb_ac_stabv_var = QComboBox()
        self.cb_ac_stabv_var.addItems([
            "Velocity X", "Velocity Y", "Velocity Z", "Pressure",
            "Temperature", "Density", "Turbulent kinetic energy",
        ])
        row_v = QHBoxLayout()
        row_v.addWidget(self.cb_ac_stabv_var, 1)
        row_v.addWidget(QPushButton("Default"))
        bf.addRow("Variable", row_v)
        self.chk_ac_stabv_stop = QCheckBox(
            "Stop the calculation when the value exceed upper/lower "
            "limit.")
        self.chk_ac_stabv_stop.setChecked(True)
        bf.addRow(self.chk_ac_stabv_stop)
        self.ed_ac_stabv_hi = QLineEdit("1e+20")
        self.ed_ac_stabv_lo = QLineEdit("-1e+20")
        bf.addRow("Upper limit", self.ed_ac_stabv_hi)
        bf.addRow("Lower limit", self.ed_ac_stabv_lo)
        self.cb_ac_stabv_treat = QComboBox()
        self.cb_ac_stabv_treat.addItems([
            "No treatment", "Restrict gradient",
            "Restrict to upper/lower limit", "Skip",
        ])
        bf.addRow("Treatment of abnormal element", self.cb_ac_stabv_treat)
        self.ed_ac_stabv_ahi = QLineEdit("1000")
        self.ed_ac_stabv_alo = QLineEdit("-1000")
        bf.addRow("Upper limit of abnormal treatment", self.ed_ac_stabv_ahi)
        bf.addRow("Lower limit of abnormal treatment", self.ed_ac_stabv_alo)
        brow = QHBoxLayout()
        brow.addStretch(1)
        btn_set = QPushButton("Set")
        btn_del = QPushButton("Delete")
        btn_set.clicked.connect(self._ac_stabv_set)
        btn_del.clicked.connect(self._ac_stabv_delete)
        brow.addWidget(btn_set)
        brow.addWidget(btn_del)
        bf.addRow(brow)
        v.addWidget(box)

        def sync_treat(idx: int) -> None:
            on = idx != 0
            self.ed_ac_stabv_ahi.setEnabled(on)
            self.ed_ac_stabv_alo.setEnabled(on)

        self.cb_ac_stabv_treat.currentIndexChanged.connect(sync_treat)
        sync_treat(0)
        return w

    def _ac_page_stab_e(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Set the parameters to avoid the divergence according to "
            "geometries and volumes of elements."))
        self.rb_ac_stabe_acc = QRadioButton("Accuracy-oriented")
        self.rb_ac_stabe_stab = QRadioButton("Stability-oriented")
        self.rb_ac_stabe_detail = QRadioButton("Detailed setting")
        self.rb_ac_stabe_acc.setChecked(True)
        v.addWidget(self.rb_ac_stabe_acc)
        v.addWidget(self.rb_ac_stabe_stab)
        v.addWidget(self.rb_ac_stabe_detail)
        self.btn_ac_stabe_refer = QPushButton("Refer...")
        v.addWidget(self.btn_ac_stabe_refer)

        def sync() -> None:
            self.btn_ac_stabe_refer.setText(
                "Edit..." if self.rb_ac_stabe_detail.isChecked()
                else "Refer...")

        self.rb_ac_stabe_detail.toggled.connect(lambda *_: sync())
        v.addStretch(1)
        return w

    def _ac_page_loop(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Specify maximum number of iterations in each cycle and "
            "criteria to terminate inner iteration of each cycle."))
        self.chk_ac_loop_default = QCheckBox("Default")
        self.chk_ac_loop_default.setChecked(True)
        v.addWidget(self.chk_ac_loop_default)
        form = QFormLayout()
        self.sp_ac_loop_max = QSpinBox()
        self.sp_ac_loop_max.setRange(1, 100000)
        self.sp_ac_loop_max.setValue(1)
        self.sp_ac_loop_min = QSpinBox()
        self.sp_ac_loop_min.setRange(1, 100000)
        self.sp_ac_loop_min.setValue(1)
        form.addRow("Maximum number of iterations in each cycle",
                    self.sp_ac_loop_max)
        form.addRow("Minimum number of iterations in each cycle",
                    self.sp_ac_loop_min)
        v.addLayout(form)
        v.addWidget(QLabel("Termination of inner iteration"))
        body = QHBoxLayout()
        self.ac_loop_tree = QTreeWidget()
        self.ac_loop_tree.setHeaderLabels(["Variable", "Criterion"])
        self.ac_loop_tree.setRootIsDecorated(False)
        self.ac_loop_tree.setAlternatingRowColors(True)
        for name in _AC_LOOP_VARS:
            self.ac_loop_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [name, "Default (Criterion = 0.0001)"]))
        body.addWidget(self.ac_loop_tree, 3)
        side = QVBoxLayout()
        side.addWidget(QLabel("Criterion to terminate inner iteration"))
        self.sp_ac_loop_crit = _spin_f(6, 0.0, 1.0, 0.0001)
        side.addWidget(self.sp_ac_loop_crit)
        self.btn_ac_loop_apply = QPushButton("Apply")
        self.btn_ac_loop_def = QPushButton("Default")
        side.addWidget(self.btn_ac_loop_apply)
        side.addWidget(self.btn_ac_loop_def)
        side.addStretch(1)
        body.addLayout(side, 1)
        v.addLayout(body, 1)

        def sync_default(on: bool) -> None:
            self.sp_ac_loop_max.setEnabled(not on)
            self.sp_ac_loop_min.setEnabled(not on)

        self.chk_ac_loop_default.toggled.connect(sync_default)
        sync_default(True)
        self.btn_ac_loop_apply.clicked.connect(self._ac_loop_apply_crit)
        self.btn_ac_loop_def.clicked.connect(self._ac_loop_default_crit)
        return w

    def _ac_page_loop_eq(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Specify a loop of each equation of each cycle."))
        body = QHBoxLayout()
        self.ac_loopeq_tree = QTreeWidget()
        self.ac_loopeq_tree.setHeaderLabels(
            ["Equation", "Maximum Number of Iterations", "Criterion"])
        self.ac_loopeq_tree.setRootIsDecorated(False)
        self.ac_loopeq_tree.setAlternatingRowColors(True)
        for eq, mx, cr in _AC_LOOP_EQ_ROWS:
            self.ac_loopeq_tree.addTopLevelItem(
                QTreeWidgetItem([eq, mx, cr]))
        body.addWidget(self.ac_loopeq_tree, 3)
        side = QVBoxLayout()
        side.addWidget(QLabel("Maximum number of iterations"))
        self.sp_ac_loopeq_max = QSpinBox()
        self.sp_ac_loopeq_max.setRange(1, 100000)
        self.sp_ac_loopeq_max.setValue(1)
        side.addWidget(self.sp_ac_loopeq_max)
        side.addWidget(QLabel("Criterion to terminate inner iteration"))
        self.sp_ac_loopeq_crit = _spin_f(8, 0.0, 1.0, 0.0001)
        side.addWidget(self.sp_ac_loopeq_crit)
        btn_a = QPushButton("Apply")
        btn_d = QPushButton("Default")
        btn_a.clicked.connect(self._ac_loopeq_apply)
        btn_d.clicked.connect(self._ac_loopeq_default)
        side.addWidget(btn_a)
        side.addWidget(btn_d)
        side.addStretch(1)
        body.addLayout(side, 1)
        v.addLayout(body, 1)
        return w

    def _ac_page_upwd(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Select the accuracy of convective terms of the equations "
            "to be used in the analysis."))
        body = QHBoxLayout()
        self.ac_upwd_tree = QTreeWidget()
        self.ac_upwd_tree.setHeaderLabels(
            ["Equation", "Accuracy of Convective Terms"])
        self.ac_upwd_tree.setRootIsDecorated(False)
        self.ac_upwd_tree.setAlternatingRowColors(True)
        for eq, acc in _AC_UPWD_ROWS:
            self.ac_upwd_tree.addTopLevelItem(QTreeWidgetItem([eq, acc]))
        body.addWidget(self.ac_upwd_tree, 3)
        side = QVBoxLayout()
        side.addWidget(QLabel("Accuracy of convective terms"))
        self.cb_ac_upwd = QComboBox()
        self.cb_ac_upwd.addItems(_AC_UPWD_SCHEMES)
        side.addWidget(self.cb_ac_upwd)
        btn_a = QPushButton("Apply")
        btn_d = QPushButton("Default")
        btn_a.clicked.connect(self._ac_upwd_apply)
        btn_d.clicked.connect(self._ac_upwd_default)
        side.addWidget(btn_a)
        side.addWidget(btn_d)
        side.addWidget(QPushButton("Optional Settings..."))
        side.addStretch(1)
        body.addLayout(side, 1)
        v.addLayout(body, 1)
        return w

    def _ac_page_time_acc(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Set the accuracy of time derivative terms."))
        self.rb_ac_time_1st = QRadioButton("First order")
        self.rb_ac_time_2nd = QRadioButton("Second order")
        self.rb_ac_time_1st.setChecked(True)
        v.addWidget(self.rb_ac_time_1st)
        v.addWidget(self.rb_ac_time_2nd)
        v.addStretch(1)
        return w

    def _ac_page_gradient(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Set the option parameters for the gradient calculation "
            "method."))
        form = QFormLayout()
        self.cb_ac_grad_type = QComboBox()
        self.cb_ac_grad_type.addItems([
            "Least squares",
            "Divergence theorem of Gauss",
            "Mixed method (least square, divergence theorem)",
            "Least squares with QR-decomposition method",
            "Least squares method with Cholesky-decomposition method",
        ])
        self.cb_ac_grad_type.setCurrentIndex(3)
        self.cb_ac_grad_weight = QComboBox()
        self.cb_ac_grad_weight.addItems([
            "No weight", "Power of the inverse distance",
            "Gaussian integral",
        ])
        self.cb_ac_grad_weight.setCurrentIndex(1)
        self.sp_ac_grad_power = _spin_f(4, 0.0, 10.0, 1.0)
        form.addRow("Global setting of Calculation type",
                    self.cb_ac_grad_type)
        form.addRow("Weight type", self.cb_ac_grad_weight)
        form.addRow("Power exponent", self.sp_ac_grad_power)
        v.addLayout(form)
        v.addWidget(QPushButton("Detailed Settings..."))
        v.addStretch(1)
        return w

    def _ac_page_diffusion(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set the option parameters for the diffusion term."))
        form = QFormLayout()
        self.cb_ac_diff_method = QComboBox()
        self.cb_ac_diff_method.addItems([
            "alpha_damping", "Default", "Over-relaxed",
        ])
        self.sp_ac_diff_alpha = _spin_f(4, 0.0, 10.0, 1.0)
        self.cb_ac_diff_cut = QComboBox()
        self.cb_ac_diff_cut.addItems(["default", "on", "off"])
        form.addRow("Method type", self.cb_ac_diff_method)
        form.addRow("Alpha", self.sp_ac_diff_alpha)
        form.addRow("Cut flux type", self.cb_ac_diff_cut)
        v.addLayout(form)
        v.addStretch(1)
        return w

    def _ac_page_solv(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Specify the type of the matrix solvers for equations "
            "used in an analysis."))
        self.rb_ac_solv_speed = QRadioButton("Speed-oriented")
        self.rb_ac_solv_acc = QRadioButton("Accuracy/Stability-oriented")
        self.rb_ac_solv_detail = QRadioButton("Detailed setting")
        self.rb_ac_solv_speed.setChecked(True)
        v.addWidget(self.rb_ac_solv_speed)
        v.addWidget(self.rb_ac_solv_acc)
        v.addWidget(self.rb_ac_solv_detail)
        self.btn_ac_solv_refer = QPushButton("Refer...")
        v.addWidget(self.btn_ac_solv_refer)

        def sync_btn() -> None:
            self.btn_ac_solv_refer.setText(
                "Edit..." if self.rb_ac_solv_detail.isChecked()
                else "Refer...")

        self.rb_ac_solv_detail.toggled.connect(lambda *_: sync_btn())
        v.addStretch(1)
        return w

    def _ac_page_sted(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Specifies parameters for evaluating convergence."))
        self.ac_sted_param = QTreeWidget()
        self.ac_sted_param.setHeaderLabels(["Parameter", "Value"])
        self.ac_sted_param.setRootIsDecorated(True)
        self.ac_sted_param.setAlternatingRowColors(True)
        start = QTreeWidgetItem(["Start cycle of evaluating convergence", ""])
        start.addChild(QTreeWidgetItem([
            "Steady analysis", "Default (From 50th cycle)"]))
        start.addChild(QTreeWidgetItem([
            "Transient analysis", "Do not evaluate convergence"]))
        self.ac_sted_param.addTopLevelItem(start)
        self.ac_sted_param.addTopLevelItem(QTreeWidgetItem([
            "Cycle interval of check output", "1"]))
        self.ac_sted_param.addTopLevelItem(QTreeWidgetItem([
            "Influence of under relaxation",
            "Default (Do not eliminate)"]))
        self.ac_sted_param.addTopLevelItem(QTreeWidgetItem([
            "Influence of pseudo time step",
            "Default (Do not reduce)"]))
        start.setExpanded(True)
        v.addWidget(self.ac_sted_param)
        # 兼容旧字段（apply 仍写 cycle_interval）
        self.sp_ac_sted_cycle = QSpinBox()
        self.sp_ac_sted_cycle.setRange(1, 100000)
        self.sp_ac_sted_cycle.setValue(1)
        self.sp_ac_sted_cycle.setVisible(False)
        v.addWidget(self.sp_ac_sted_cycle)
        v.addWidget(QLabel("Convergence criteria"))
        self.ac_sted_tree = QTreeWidget()
        self.ac_sted_tree.setHeaderLabels(
            ["Equation", "Criterion", "Unit", "Type"])
        self.ac_sted_tree.setRootIsDecorated(True)
        self.ac_sted_tree.setAlternatingRowColors(True)
        cycle = QTreeWidgetItem(["Cycle difference", "", "", ""])
        for name, crit in _AC_STED_CRITERIA:
            cycle.addChild(QTreeWidgetItem([name, crit, "", ""]))
        self.ac_sted_tree.addTopLevelItem(cycle)
        cycle.setExpanded(True)
        v.addWidget(self.ac_sted_tree, 1)
        return w

    def _ac_page_pcty(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "Specify the type of pressure correction and fixed "
            "pressure conditions."))
        form = QFormLayout()
        self.cb_ac_pcty = QComboBox()
        for lab, data in (
            ("Default (SIMPLEC method)", "default"),
            ("Only time-derivative terms are used for correction", "td"),
            ("SIMPLE method", "0"),
            ("SIMPLEC method", "2"),
            ("PISO method", "3"),
            ("PISOC method (PISO method based on SIMPLEC)", "4"),
        ):
            self.cb_ac_pcty.addItem(lab, data)
        form.addRow("Type of pressure correction", self.cb_ac_pcty)
        v.addLayout(form)
        # 兼容旧 batch / apply
        self.chk_ac_pcty_default = QCheckBox()
        self.chk_ac_pcty_default.setChecked(True)
        self.chk_ac_pcty_default.setVisible(False)
        v.addWidget(self.chk_ac_pcty_default)
        v.addWidget(QPushButton("Detailed Settings..."))
        v.addStretch(1)

        def sync_def(idx: int) -> None:
            self.chk_ac_pcty_default.setChecked(
                self.cb_ac_pcty.itemData(idx) == "default")

        self.cb_ac_pcty.currentIndexChanged.connect(sync_def)
        return w

    def _ac_page_restart(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set the restart options."))
        form = QFormLayout()
        self.cb_ac_restart = QComboBox()
        self.cb_ac_restart.addItems([
            "Do not use restart", "Use restart file",
        ])
        form.addRow("Restart", self.cb_ac_restart)
        v.addLayout(form)
        v.addStretch(1)
        return w

    def _ac_page_mapping(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Set the mapping options."))
        form = QFormLayout()
        self.sp_ac_map_prob = _spin_f(4, 0.0, 1.0, 0.9)
        self.cb_ac_map_avg = QComboBox()
        self.cb_ac_map_avg.addItems(["default", "on", "off"])
        self.cb_ac_map_fill = QComboBox()
        self.cb_ac_map_fill.addItems(["default", "nearest", "none"])
        form.addRow("Match probability", self.sp_ac_map_prob)
        form.addRow("Average field", self.cb_ac_map_avg)
        form.addRow("Filling method", self.cb_ac_map_fill)
        v.addLayout(form)
        v.addStretch(1)
        return w

    def _ac_page_form(
            self, desc: str,
            rows: list[tuple[str, str, list[str]]]) -> QWidget:
        """通用表单页：标签说明 + Parameter/Value 下拉表。"""
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel(desc)
        lab.setWordWrap(True)
        v.addWidget(lab)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Parameter", "Value"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setColumnWidth(0, 320)
        for label, default, choices in rows:
            it = QTreeWidgetItem([label, ""])
            tree.addTopLevelItem(it)
            cb = QComboBox()
            cb.addItems(choices)
            i = cb.findText(default)
            if i >= 0:
                cb.setCurrentIndex(i)
            tree.setItemWidget(it, 1, cb)
        v.addWidget(tree, 1)
        w._ac_param_tree = tree  # type: ignore[attr-defined]
        return w

    def _ac_apply_batch(self) -> None:
        mode = self.cb_ac_batch.currentData() or "default"
        if mode == "default":
            self.chk_ac_loop_default.setChecked(True)
            self.sp_ac_loop_max.setValue(1)
            self.sp_ac_loop_min.setValue(1)
            self.rb_ac_time_1st.setChecked(True)
            self.rb_ac_solv_speed.setChecked(True)
            i = self.cb_ac_pcty.findData("default")
            if i >= 0:
                self.cb_ac_pcty.setCurrentIndex(i)
            self._ac_undr_default()
            self._ac_loop_default_crit()
        else:
            self.chk_ac_loop_default.setChecked(False)
            self.sp_ac_loop_max.setValue(20)
            self.sp_ac_loop_min.setValue(2)
            self.rb_ac_time_2nd.setChecked(True)
            self.rb_ac_solv_acc.setChecked(True)
            i = self.cb_ac_pcty.findData("2")
            if i >= 0:
                self.cb_ac_pcty.setCurrentIndex(i)
            presets = {
                "undr_momentum": 1.0,
                "undr_turbulence": 0.8,
                "undr_cavi": 0.7,
            }
            for i in range(self.ac_undr_tree.topLevelItemCount()):
                it = self.ac_undr_tree.topLevelItem(i)
                tag = it.data(0, Qt.UserRole)
                if tag in presets:
                    it.setText(2, f"Value : {presets[tag]:g}")
                elif tag not in (
                    "undr_energy", "undr_energy_incomp",
                    "undr_energy_solid", "undr_energy_comp",
                    "undr_energy_porous",
                ):
                    it.setText(2, "Value : 0.9")

    def _ac_undr_on_sel(self) -> None:
        items = self.ac_undr_tree.selectedItems()
        if not items:
            return
        it = items[0]
        typ = it.text(1)
        i = self.cb_ac_undr_type.findText(typ)
        if i >= 0:
            self.cb_ac_undr_type.setCurrentIndex(i)
        detail = it.text(2)
        if ":" in detail:
            try:
                self.sp_ac_undr_val.setValue(float(detail.split(":")[-1]))
            except ValueError:
                pass

    def _ac_undr_apply_sel(self) -> None:
        items = self.ac_undr_tree.selectedItems()
        if not items:
            return
        it = items[0]
        it.setText(1, self.cb_ac_undr_type.currentText())
        it.setText(2, f"Value : {self.sp_ac_undr_val.value():g}")

    def _ac_undr_default_sel(self) -> None:
        items = self.ac_undr_tree.selectedItems()
        if not items:
            self._ac_undr_default()
            return
        it = items[0]
        tag = it.data(0, Qt.UserRole)
        defaults = {t: v for _l, t, v in _AC_UNDR_ROWS}
        it.setText(1, "Constant value")
        it.setText(2, f"Value : {defaults.get(tag, 0.9):g}")

    def _ac_undr_default(self) -> None:
        defaults = {tag: val for _lab, tag, val in _AC_UNDR_ROWS}
        for i in range(self.ac_undr_tree.topLevelItemCount()):
            it = self.ac_undr_tree.topLevelItem(i)
            tag = it.data(0, Qt.UserRole)
            it.setText(1, "Constant value")
            it.setText(2, f"Value : {defaults.get(tag, 0.9):g}")

    def _ac_dtsr_register(self) -> None:
        detail = f"Value : {self.sp_ac_dtsr_val.value():g}"
        self.ac_dtsr_tree.addTopLevelItem(QTreeWidgetItem([
            self.cb_ac_dtsr_eq.currentText(),
            self.cb_ac_dtsr_target.currentText(),
            self.cb_ac_dtsr_type.currentText(),
            detail,
        ]))

    def _ac_dtsr_delete(self) -> None:
        for it in self.ac_dtsr_tree.selectedItems():
            idx = self.ac_dtsr_tree.indexOfTopLevelItem(it)
            if idx >= 0:
                self.ac_dtsr_tree.takeTopLevelItem(idx)

    def _ac_stabv_set(self) -> None:
        stop = (
            f"Stop(Upper limit: {self.ed_ac_stabv_hi.text()}, "
            f"Lower limit: {self.ed_ac_stabv_lo.text()})"
            if self.chk_ac_stabv_stop.isChecked() else "Do not stop")
        treat = self.cb_ac_stabv_treat.currentText()
        var = self.cb_ac_stabv_var.currentText()
        for i in range(self.ac_stabv_tree.topLevelItemCount()):
            it = self.ac_stabv_tree.topLevelItem(i)
            if it.text(0) == var:
                it.setText(1, stop)
                it.setText(2, treat)
                return
        self.ac_stabv_tree.addTopLevelItem(
            QTreeWidgetItem([var, stop, treat]))

    def _ac_stabv_delete(self) -> None:
        for it in self.ac_stabv_tree.selectedItems():
            idx = self.ac_stabv_tree.indexOfTopLevelItem(it)
            if idx >= 0:
                self.ac_stabv_tree.takeTopLevelItem(idx)

    def _ac_loop_apply_crit(self) -> None:
        items = self.ac_loop_tree.selectedItems()
        if not items:
            return
        val = self.sp_ac_loop_crit.value()
        items[0].setText(1, f"Criterion = {val:g}")

    def _ac_loop_default_crit(self) -> None:
        items = self.ac_loop_tree.selectedItems()
        targets = items or [
            self.ac_loop_tree.topLevelItem(i)
            for i in range(self.ac_loop_tree.topLevelItemCount())]
        for it in targets:
            if it is not None:
                it.setText(1, "Default (Criterion = 0.0001)")

    def _ac_loopeq_apply(self) -> None:
        items = self.ac_loopeq_tree.selectedItems()
        if not items:
            return
        it = items[0]
        it.setText(1, str(self.sp_ac_loopeq_max.value()))
        it.setText(2, f"{self.sp_ac_loopeq_crit.value():g}")

    def _ac_loopeq_default(self) -> None:
        items = self.ac_loopeq_tree.selectedItems()
        if not items:
            return
        name = items[0].text(0)
        for eq, mx, cr in _AC_LOOP_EQ_ROWS:
            if eq == name:
                items[0].setText(1, mx)
                items[0].setText(2, cr)
                return

    def _ac_upwd_apply(self) -> None:
        items = self.ac_upwd_tree.selectedItems()
        if not items:
            return
        items[0].setText(1, self.cb_ac_upwd.currentText())

    def _ac_upwd_default(self) -> None:
        items = self.ac_upwd_tree.selectedItems()
        if not items:
            return
        name = items[0].text(0)
        for eq, acc in _AC_UPWD_ROWS:
            if eq == name:
                items[0].setText(1, acc)
                return

    def _make_out_subnav_page(
            self, nav_items: list[tuple[str, str]],
            builders: dict[str, Callable[[], QWidget]],
            attr_prefix: str) -> QWidget:
        """Output / Optional 共用：中栏子导航 + 右侧叠页。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        nav = QTreeWidget()
        nav.setHeaderHidden(True)
        nav.setRootIsDecorated(False)
        nav.setIconSize(QSize(16, 16))
        nav.setMinimumWidth(200)
        nav.setMaximumWidth(280)
        leaf_ic = _ac_nav_icon("leaf", 16)
        items: dict[str, QTreeWidgetItem] = {}
        for key, label in nav_items:
            it = QTreeWidgetItem([label])
            it.setIcon(0, leaf_ic)
            it.setData(0, Qt.UserRole, key)
            nav.addTopLevelItem(it)
            items[key] = it
        stack = QStackedWidget()
        pages: dict[str, QWidget] = {}
        for key, _lab in nav_items:
            w = builders[key]()
            pages[key] = w
            stack.addWidget(w)

        def on_nav(cur: Optional[QTreeWidgetItem],
                   _prev: Optional[QTreeWidgetItem] = None) -> None:
            if cur is None:
                return
            key = cur.data(0, Qt.UserRole)
            w = pages.get(key)
            if w is not None:
                stack.setCurrentWidget(w)

        nav.currentItemChanged.connect(on_nav)
        if nav_items:
            nav.setCurrentItem(items[nav_items[0][0]])
        setattr(page, f"_{attr_prefix}_nav", nav)
        setattr(self, f"_{attr_prefix}_pages", pages)
        setattr(self, f"_{attr_prefix}_stack", stack)
        setattr(self, f"_{attr_prefix}_nav_items", items)
        h.addWidget(nav, 2)
        h.addWidget(stack, 5)
        return page

    def _out_param_page(
            self, desc: str,
            rows: list[tuple[str, str]]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel(desc)
        lab.setWordWrap(True)
        v.addWidget(lab)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Parameter", "Value", "Unit", "Type"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        for name, val in rows:
            it = QTreeWidgetItem([name, val, "", ""])
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            tree.addTopLevelItem(it)
        tree.setEditTriggers(
            QTreeWidget.DoubleClicked | QTreeWidget.EditKeyPressed)
        v.addWidget(tree, 1)
        w._param_tree = tree  # type: ignore[attr-defined]
        return w

    def _out_list_new_page(
            self, desc: str, title: str = "Condition") -> QWidget:
        """Region Output 等：条件名列表 + New/Edit/Delete。"""
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel(desc)
        lab.setWordWrap(True)
        v.addWidget(lab)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Condition name"])
        lst.setRootIsDecorated(False)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(16, 16))
        v.addWidget(lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        for lab_btn in ("New...", "Edit...", "Delete"):
            row.addWidget(QPushButton(lab_btn))
        v.addLayout(row)
        w._cond_list = lst  # type: ignore[attr-defined]
        return w

    def _page_output_field(self) -> QWidget:
        """Output of Field File：子导航 + FPH 输出设置。"""
        # 兼容 apply/load：隐藏旧 combo/spin，与参数表同步
        self.cb_fph_type = QComboBox()
        self.cb_fph_type.addItems([
            "Last cycle", "Every specified cycle",
            "Cycle interval (table)", "Every specified time interval",
            "Time interval (table)",
        ])
        # xml 值映射
        self._fph_type_xml = {
            "Last cycle": "last_cycle",
            "Every specified cycle": "cycle_interval",
            "Cycle interval (table)": "cycle_interval_table",
            "Every specified time interval": "time_interval",
            "Time interval (table)": "time_interval_table",
        }
        self._fph_type_from_xml = {v: k for k, v in self._fph_type_xml.items()}
        self.sp_fph_cycle = QSpinBox()
        self.sp_fph_cycle.setRange(1, 10_000_000)
        self.sp_fph_cycle.setValue(100)

        def page_setting() -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel("Set the output conditions of field files."))
            tree = QTreeWidget()
            tree.setHeaderLabels(["Parameter", "Value", "Unit", "Type"])
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            it_t = QTreeWidgetItem(["Output timing", "", "", ""])
            it_c = QTreeWidgetItem(["Cycle interval", "", "", ""])
            it_i = QTreeWidgetItem(["Initial field", "", "", ""])
            tree.addTopLevelItem(it_t)
            tree.addTopLevelItem(it_c)
            tree.addTopLevelItem(it_i)
            tree.setItemWidget(it_t, 1, self.cb_fph_type)
            tree.setItemWidget(it_c, 1, self.sp_fph_cycle)
            self.cb_fph_init = QComboBox()
            self.cb_fph_init.addItems(["Do not output", "Output"])
            tree.setItemWidget(it_i, 1, self.cb_fph_init)
            v.addWidget(tree, 1)
            self.fph_setting_tree = tree

            def sync_cycle(*_a) -> None:
                self.sp_fph_cycle.setEnabled(
                    self.cb_fph_type.currentText() == "Every specified cycle")

            self.cb_fph_type.currentIndexChanged.connect(sync_cycle)
            sync_cycle()
            return w

        def page_vars() -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel(
                "Set variables to be output to field files."))
            body = QHBoxLayout()
            self.fph_var_tree = QTreeWidget()
            self.fph_var_tree.setHeaderLabels(
                ["Variable", "Output Setting of Analysis Data"])
            self.fph_var_tree.setRootIsDecorated(False)
            self.fph_var_tree.setAlternatingRowColors(True)
            for name, val in _FPH_VAR_ROWS:
                self.fph_var_tree.addTopLevelItem(
                    QTreeWidgetItem([name, val]))
            body.addWidget(self.fph_var_tree, 3)
            side = QVBoxLayout()
            for lab, setter in (
                ("Output", "Output"),
                ("Do not output", "Do not output"),
                ("Default", None),
            ):
                btn = QPushButton(lab)
                if setter is None:
                    btn.clicked.connect(self._fph_var_default)
                else:
                    btn.clicked.connect(
                        lambda _=False, s=setter: self._fph_var_set(s))
                side.addWidget(btn)
            side.addStretch(1)
            body.addLayout(side, 1)
            v.addLayout(body, 1)
            v.addWidget(QPushButton("Detailed Settings..."))
            return w

        builders = {
            "fph_setting": page_setting,
            "fph_surface": lambda: self._out_param_page(
                "Set the output of surface data.",
                [("Output surface data", "Do not output"),
                 ("Surface region", "(all)")]),
            "fph_vars": page_vars,
            "fph_partial": lambda: self._out_list_new_page(
                "Set partial graphic (FPH) file output conditions."),
            "fph_avg": lambda: self._out_param_page(
                "Set averaging of field data.",
                [("Averaging", "Do not execute"),
                 ("Start cycle", "1"),
                 ("End cycle", "Last cycle")]),
            "fph_tf": lambda: self._out_list_new_page(
                "Set time-frequency analysis output conditions."),
            "fph_elem": lambda: self._out_param_page(
                "Set output of element information for divergence measures.",
                [("Output element information", "Default"),
                 ("Upper limit of number of elements", "100")]),
            "fph_opts": lambda: self._out_param_page(
                "Set options of field file output.",
                [("Compress field file", "Default"),
                 ("Output binary format", "Default")]),
        }
        return self._make_out_subnav_page(
            _OUT_FIELD_NAV, builders, "out_field")

    def _fph_var_set(self, setting: str) -> None:
        for it in self.fph_var_tree.selectedItems():
            it.setText(1, setting)

    def _fph_var_default(self) -> None:
        defaults = dict(_FPH_VAR_ROWS)
        items = self.fph_var_tree.selectedItems()
        targets = items or [
            self.fph_var_tree.topLevelItem(i)
            for i in range(self.fph_var_tree.topLevelItemCount())]
        for it in targets:
            if it is not None:
                it.setText(1, defaults.get(it.text(0), "Default"))

    def _page_output_list(self) -> QWidget:
        """Output of List File：子导航 + Check/Region/Options 等。"""
        def page_check() -> QWidget:
            return self._out_param_page(
                "Specify the settings of check output to the list file.",
                _LIST_CHECK_ROWS)

        def page_opts() -> QWidget:
            return self._out_param_page(
                "Set the output of the minimum and maximum values of "
                "flow velocity, etc.",
                _LIST_OPT_ROWS)

        builders: dict[str, Callable[[], QWidget]] = {
            "list_check": page_check,
            "list_region": lambda: self._out_list_new_page(
                "Set region output conditions to the list file."),
            "list_passage": lambda: self._out_list_new_page(
                "Set region output (passage) conditions."),
            "list_scalar": lambda: self._out_list_new_page(
                "Set region output (scalar flux) conditions."),
            "list_force": lambda: self._out_list_new_page(
                "Set surface force output conditions."),
            "list_moment": lambda: self._out_list_new_page(
                "Set surface moment output conditions."),
            "list_yplus": lambda: self._out_list_new_page(
                "Set non-dimensional distance from wall distribution "
                "output."),
            "list_ang": lambda: self._out_list_new_page(
                "Set angular momentum output conditions."),
            "list_turbo": lambda: self._out_list_new_page(
                "Set turbomachinery performance output conditions."),
            "list_load": lambda: self._out_list_new_page(
                "Set load distribution output conditions."),
            "list_iter": lambda: self._out_param_page(
                "Set output of information during iterations.",
                [("Output information during iterations", "Default"),
                 ("Cycle interval", "1")]),
            "list_elem_e": lambda: self._out_param_page(
                "Set element information (elements) for divergence measures.",
                [("Output", "Default")]),
            "list_elem_v": lambda: self._out_param_page(
                "Set element information (variables) for divergence measures.",
                [("Output", "Default")]),
            "list_opts": page_opts,
        }
        return self._make_out_subnav_page(
            _OUT_LIST_NAV, builders, "out_list")

    def _page_output_other(self) -> QWidget:
        """Other Output：Time Series / Restart / Heat Path 等。"""
        def page_restart() -> QWidget:
            return self._out_param_page(
                "Set the output setting of the restart file.",
                [
                    ("Output timing", "Last cycle"),
                    ("Number of restart files", "1"),
                    ("Timing to delete an old restart file",
                     "Before a new file is output"),
                ])

        builders: dict[str, Callable[[], QWidget]] = {
            "oth_series": lambda: self._out_list_new_page(
                "Set the output condition of the time series."),
            "oth_coord": lambda: self._out_list_new_page(
                "Set coordinate–variable output conditions."),
            "oth_restart": page_restart,
            "oth_heat": lambda: self._out_param_page(
                "Set the heat path data file output.",
                [("Output heat path data", "Do not output"),
                 ("Cycle interval", "1")]),
            "oth_noise": lambda: self._out_list_new_page(
                "Set FlowNoise file output conditions."),
            "oth_ring": lambda: self._out_list_new_page(
                "Set RingDipoles file output conditions."),
        }
        return self._make_out_subnav_page(
            _OUT_OTHER_NAV, builders, "out_other")

    def _page_file_name(self) -> QWidget:
        """File Name：工程名 + 输出勾选 / 文件名表（对齐 scFLOWpre）。"""
        page = QWidget()
        v = QVBoxLayout(page)
        hdr = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(_file_type_icon("etco", 28).pixmap(28, 28))
        hdr.addWidget(ic)
        title = QLabel("File Name")
        title.setStyleSheet("font-weight:bold; font-size:13px;")
        hdr.addWidget(title)
        hdr.addStretch(1)
        v.addLayout(hdr)
        row = QHBoxLayout()
        row.addWidget(QLabel("Project (PPH file) name"))
        self.ed_project = QLineEdit()
        row.addWidget(self.ed_project, 1)
        self.btn_apply_names = QPushButton("Apply to Following File Names")
        row.addWidget(self.btn_apply_names)
        v.addLayout(row)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Type", "Output", "File Name"])
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setIconSize(QSize(16, 16))
        self.file_tree.setColumnWidth(0, 280)
        self.file_tree.setColumnWidth(1, 60)
        v.addWidget(self.file_tree, 1)
        self.btn_apply_names.clicked.connect(self._apply_project_to_files)
        # (tag, label, has_output_chk, has_browse)
        self._file_rows = [
            ("sph", "Analysis condition file (SPH)", False, True),
            ("gph", "Mesh file (GPH)", False, True),
            ("fph", "Field file (FPH)", False, False),
            ("rph", "Input/output restart file (RPH)", True, False),
            ("inir", "Initial field file (INIR)", False, True),
            ("inif", "Initial field file (INIF)", False, True),
            ("ri", "Input restart file (RI)", True, True),
            ("ro", "Output restart file (RO)", True, False),
            ("mapi", "Field file for mapping", True, True),
            ("csvi", "Field file for mapping (CSVI)", True, True),
            ("hpt", "Heat path data file (HPT)", True, False),
            ("etco", "Generic name for output files (ETCO)", False, False),
        ]
        self._file_editors: dict[str, QLineEdit] = {}
        self._file_checks: dict[str, QCheckBox] = {}
        tip = QLabel(
            "* Click Apply to Following File Names to copy the project "
            "name into SPH/GPH/FPH/RPH and related outputs.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px;")
        v.addWidget(tip)
        return page

    def _page_optional_conditions(self) -> QWidget:
        """Optional Conditions：Created / Table / Script 等示意图按钮。"""
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(4, 4, 4, 4)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lst = QTreeWidget()
        lst.setHeaderLabels(["Name", "Type"])
        lst.setRootIsDecorated(False)
        lst.setAlternatingRowColors(True)
        lst.setIconSize(QSize(18, 18))
        lv.addWidget(lst, 1)
        page._cond_list = lst  # type: ignore[attr-defined]

        right = QGroupBox("Optional condition")
        rv = QVBoxLayout(right)
        rv.setSpacing(6)
        page._opt_btns = []  # type: ignore[attr-defined]
        for kind, label in _OPTIONAL_NEW_BUTTONS:
            btn = QPushButton(label)
            btn.setIcon(_optional_cond_icon(kind, 36))
            btn.setIconSize(QSize(36, 36))
            btn.setMinimumHeight(44)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 8px; "
                "font-size: 12px; }"
                "QPushButton:hover { background: #e3f2fd; }")
            btn.clicked.connect(
                lambda _=False, k=kind, lab=label:
                self._open_optional(k, lab))
            rv.addWidget(btn)
            page._opt_btns.append(btn)  # type: ignore[attr-defined]
        btn_more = QPushButton("Condition Type Catalog (all)...")
        btn_more.clicked.connect(lambda: self._open_cond_catalog(""))
        rv.addWidget(btn_more)
        tip = QLabel(
            "* Created Condition lists all user-defined conditions.\n"
            "* Table / Script / UDF / Mapping open the corresponding "
            "editors (full editing in scFLOWpre).")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#555; font-size:11px; margin-top:4px;")
        rv.addWidget(tip)
        rv.addStretch(1)
        h.addWidget(left, 2)
        h.addWidget(right, 3)
        return page

    def _open_optional(self, kind: str, label: str) -> None:
        page = self._pages.get("optional")
        if page is None:
            return
        lst: QTreeWidget = page._cond_list  # type: ignore[attr-defined]
        name = label.replace(" ", "")
        # 避免重复添加同名
        for i in range(lst.topLevelItemCount()):
            if lst.topLevelItem(i).text(0) == name:
                lst.setCurrentItem(lst.topLevelItem(i))
                return
        it = QTreeWidgetItem([name, label])
        it.setIcon(0, _optional_cond_icon(kind, 16))
        it.setData(0, Qt.UserRole, kind)
        lst.addTopLevelItem(it)
        sess = self._ctx.setdefault("session", {}).setdefault(
            "conditions", {})
        opts = sess.setdefault("optional_conditions", [])
        opts.append({"name": name, "kind": kind, "label": label})

    def _page_stub(self, title: str, text: str) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel(title))
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet("color:#444;")
        v.addWidget(lab)
        v.addStretch(1)
        return page

    def _find_nav_item(self, key: str) -> Optional[QTreeWidgetItem]:
        def walk(it: QTreeWidgetItem):
            if it.data(0, Qt.UserRole) == key:
                return it
            for i in range(it.childCount()):
                hit = walk(it.child(i))
                if hit is not None:
                    return hit
            return None

        for i in range(self.nav.topLevelItemCount()):
            hit = walk(self.nav.topLevelItem(i))
            if hit is not None:
                return hit
        return None

    def _current_key(self) -> Optional[str]:
        it = self.nav.currentItem()
        if it is None:
            return None
        return it.data(0, Qt.UserRole)

    def _on_nav(self, cur: Optional[QTreeWidgetItem],
                _prev: Optional[QTreeWidgetItem] = None) -> None:
        if cur is None:
            return
        key = cur.data(0, Qt.UserRole)
        if not key:
            # 点到文件夹：选中第一个叶
            if cur.childCount():
                self.nav.setCurrentItem(cur.child(0))
            return
        page = self._pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
        self.btn_base.setVisible(key == "basic_setting")
        self.btn_detail.setVisible(key not in (
            "analysis_type", "file_name", "optional"))
        # Back/Next enable
        try:
            idx = self._leaf_keys.index(key)
        except ValueError:
            idx = 0
        self.btn_back.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(self._leaf_keys) - 1)

    def _go_back(self) -> None:
        key = self._current_key()
        if key not in self._leaf_keys:
            return
        idx = self._leaf_keys.index(key)
        if idx > 0:
            it = self._find_nav_item(self._leaf_keys[idx - 1])
            if it is not None:
                self.nav.setCurrentItem(it)

    def _go_next(self) -> None:
        key = self._current_key()
        if key not in self._leaf_keys:
            return
        idx = self._leaf_keys.index(key)
        if idx < len(self._leaf_keys) - 1:
            it = self._find_nav_item(self._leaf_keys[idx + 1])
            if it is not None:
                self.nav.setCurrentItem(it)

    def _finish(self) -> None:
        dlg = self.window()
        if isinstance(dlg, QDialog):
            # 走 NavParamDialog OK 路径
            if hasattr(dlg, "_on_ok"):
                dlg._on_ok()
            else:
                if self.apply(self._ctx):
                    dlg.accept()
        else:
            self.apply(self._ctx)

    def _on_detailed(self) -> None:
        # P4-0：条件树可用时打开全树编辑器；否则退回提示
        if condition_tree.load_condition_tree() is not None:
            dlg = SolverSettingsDialog(self._ctx, self)
            dlg.exec_()
            return
        key = self._current_key() or ""
        QMessageBox.information(
            self, "Detailed Settings",
            f"Detailed settings for '{key}' follow scFLOWpre.\n"
            "Key parameters are editable on this page; "
            "full sub-dialogs open in scFLOWpre.")

    def _on_base_value(self) -> None:
        QMessageBox.information(
            self, "Base Value",
            "Base temperature / pressure offsets are stored under "
            "basic_param/base_temp in main.xml.")

    def _open_cond_catalog(self, page_key: str = "") -> None:
        """打开条件类型目录（P4-1），按当前页过滤 category。"""
        cats = _PAGE_CATEGORIES.get(page_key)
        dlg = CondTypeCatalogDialog(self._ctx, cats, self)
        dlg.exec_()

    def _stub_new_condition(self, page: str, kind: str) -> None:
        # P1-3：schema 里有该类型 → 打开通用表单并写 main.xml；
        # P4-1：cond_types 目录命中（类型名/别名/显示名）亦可打开；
        # 否则维持旧的“仅记录 session”桩。
        ctype = None
        reg = condition_registry_cached()
        if reg is not None:
            ctype = reg.get(reg.resolve_alias(kind))
            if ctype is None:
                # 按显示名匹配（按钮标签是 UI 文案而非类型名）
                kl = kind.strip().lower()
                for t in reg.types.values():
                    if (t.display or "").strip().lower() == kl:
                        ctype = t
                        break
        if ctype is None:
            sess = self._ctx.setdefault("session", {}).setdefault(
                "conditions", {})
            created = sess.setdefault("created", [])
            created.append({"page": page, "kind": kind})
            QMessageBox.information(
                self, "New condition",
                f"'{kind}' on [{page}] recorded in session.\n"
                "No schema for this condition type; "
                "full creation UI runs in scFLOWpre.")
            return
        dlg = GenericCondBody(ctype.name, ctype, self._ctx, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.result_cond()
        if write_condition_to_xml(self._ctx, ctype, data):
            sess = self._ctx.setdefault("session", {}).setdefault(
                "conditions", {})
            sess.setdefault("created", []).append({
                "page": page, "kind": kind, "name": data["name"],
                "written": True,
            })
            self._fill_condition_lists()
            QMessageBox.information(
                self, "New condition",
                f"Condition '{data['name']}' ({kind}) written to main.xml.\n"
                "Save project 后随 .pph 持久化。")
        else:
            QMessageBox.warning(
                self, "New condition",
                "当前工程未加载 main.xml，无法写入（先打开 PPH 项目）。")

    def _show_existing(self, page: str) -> None:
        key = self._current_key() or ""
        filt = _BC_TYPE_FILTER.get(key, frozenset())
        lines = []
        xml = self._ctx.get("xml")
        if xml is not None:
            for cond in xml.conditions():
                sm = xml.condition_summary(cond)
                if filt and sm.get("type") not in filt:
                    continue
                lines.append(f"{sm.get('name')}  [{sm.get('type')}]")
        if not lines:
            lines = ["(none)"]
        QMessageBox.information(
            self, f"Existing Conditions – {page}",
            "\n".join(lines[:40]))

    def _apply_project_to_files(self) -> None:
        base = self.ed_project.text().strip()
        if not base:
            return
        for tag, ed in self._file_editors.items():
            if tag in ("sph", "gph"):
                ed.setText(f"{base}.{tag}")
            else:
                ed.setText(base)

    def _fill_condition_lists(self) -> None:
        xml = self._ctx.get("xml")
        self._fill_flow_bc_tree()
        self._sync_flow_bc_buttons()
        self._fill_wall_bc_tree()
        self._sync_wall_bc_buttons()
        self._fill_thermal_bc_tree()
        self._sync_thermal_bc_buttons()
        self._fill_sym_bc_tree()
        self._sync_sym_bc_buttons()
        self._fill_periodic_bc_list()
        self._fill_source_bc_tree()
        self._sync_source_bc_buttons()
        self._fill_fixed_bc_tree()
        for key, page in self._pages.items():
            if key in ("bc_flow", "bc_wall", "bc_thermal", "bc_sym",
                       "bc_periodic", "source", "fixed", "optional"):
                continue
            lst = getattr(page, "_cond_list", None)
            if lst is None:
                continue
            lst.clear()
            filt = _BC_TYPE_FILTER.get(key)
            if key == "initial":
                # 区域列表 + 示意图标
                lst.setHeaderLabels(["Region", "Kind"])
                lst.setIconSize(QSize(18, 18))
                whole = QTreeWidgetItem(["Whole region", "all"])
                whole.setIcon(0, _ic_region_icon("whole", 18))
                lst.addTopLevelItem(whole)
                if xml is not None:
                    regs = xml.section("regions")
                    if regs is not None:
                        for cat in list(regs):
                            for r in cat.findall("region"):
                                name = r.findtext("name") or ""
                                if not name:
                                    continue
                                kind = "special" if (
                                    cat.tag in ("numerical", "special")
                                    or name.upper() == "JOS"
                                ) else "volume"
                                it = QTreeWidgetItem([name, cat.tag])
                                it.setIcon(0, _ic_region_icon(kind, 18))
                                lst.addTopLevelItem(it)
                # groups_info 兜底零件名
                if lst.topLevelItemCount() <= 1:
                    for g in sorted((self._ctx.get("groups_info") or {})):
                        it = QTreeWidgetItem([g, "part"])
                        it.setIcon(0, _ic_region_icon("volume", 18))
                        lst.addTopLevelItem(it)
                continue
            lst.setHeaderLabels(["Name", "Type"])
            if xml is None:
                continue
            for cond in xml.conditions():
                sm = xml.condition_summary(cond)
                if filt and sm.get("type") not in filt:
                    continue
                lst.addTopLevelItem(QTreeWidgetItem([
                    sm.get("name") or "(unnamed)",
                    sm.get("type") or "",
                ]))

    def _fill_analysis_control(self) -> None:
        """从 main.xml analysis_control 填充各子页控件。"""
        xml = self._ctx.get("xml")
        ac = None
        if xml is not None:
            cond = xml.section("conditions")
            if cond is not None:
                ac = cond.find("analysis_control")

        # Loop
        if ac is not None:
            loop = ac.find("loop")
            if loop is not None:
                nloop_def = _xml_bool(loop.findtext("nloop_default"), True)
                self.chk_ac_loop_default.setChecked(nloop_def)
                try:
                    self.sp_ac_loop_max.setValue(
                        int(float(loop.findtext("const_value") or "1")))
                except ValueError:
                    pass
            loop_min = ac.find("loop_min")
            if loop_min is not None:
                try:
                    self.sp_ac_loop_min.setValue(
                        int(float(loop_min.findtext("const_value") or "1")))
                except ValueError:
                    pass
            # Time accuracy
            ta = ac.find("time_accuracy")
            if ta is not None:
                order = (ta.findtext("order") or "0").strip()
                if order in ("1", "2"):
                    self.rb_ac_time_2nd.setChecked(True)
                else:
                    self.rb_ac_time_1st.setChecked(True)
            # Matrix solvers
            solv = ac.find("solv")
            if solv is not None:
                st = (solv.findtext("type") or "speed").strip().lower()
                if st in ("accuracy", "acc", "stability"):
                    self.rb_ac_solv_acc.setChecked(True)
                elif st in ("detail", "detailed"):
                    self.rb_ac_solv_detail.setChecked(True)
                else:
                    self.rb_ac_solv_speed.setChecked(True)
            # Pressure method
            pcty = ac.find("pcty")
            if pcty is not None:
                bdef = _xml_bool(pcty.findtext("bdefault"), True)
                if bdef:
                    i = self.cb_ac_pcty.findData("default")
                else:
                    ip = (pcty.findtext("ipcty") or "2").strip()
                    i = self.cb_ac_pcty.findData(ip)
                    if i < 0:
                        i = self.cb_ac_pcty.findData("default")
                if i >= 0:
                    self.cb_ac_pcty.setCurrentIndex(i)
            # Under-relaxation
            undr = ac.find("undr")
            if undr is not None:
                self.chk_ac_undr_transient.setChecked(
                    _xml_bool(undr.findtext("loop_undr_flag"), False))
                for i in range(self.ac_undr_tree.topLevelItemCount()):
                    it = self.ac_undr_tree.topLevelItem(i)
                    tag = it.data(0, Qt.UserRole)
                    node = undr.find(tag) if tag else None
                    if node is None:
                        continue
                    cv = node.findtext("const_value")
                    if cv:
                        try:
                            it.setText(2, f"Value : {float(cv):g}")
                        except ValueError:
                            it.setText(2, f"Value : {cv}")
            # Convergence
            sted = ac.find("sted")
            if sted is not None:
                try:
                    cyc = int(float(sted.findtext("cycle_interval") or "1"))
                    self.sp_ac_sted_cycle.setValue(cyc)
                    # 同步参数树显示
                    for i in range(self.ac_sted_param.topLevelItemCount()):
                        it = self.ac_sted_param.topLevelItem(i)
                        if "Cycle interval" in it.text(0):
                            it.setText(1, str(cyc))
                except ValueError:
                    pass
            # Mapping / Diffusion dedicated widgets
            map_el = ac.find("mapping_option")
            if map_el is not None:
                try:
                    self.sp_ac_map_prob.setValue(
                        float(map_el.findtext("match_probability") or "0.9"))
                except ValueError:
                    pass
                avg = map_el.findtext("average_field") or "default"
                i = self.cb_ac_map_avg.findText(avg)
                if i >= 0:
                    self.cb_ac_map_avg.setCurrentIndex(i)
                fill = map_el.findtext("filling_method") or "default"
                i = self.cb_ac_map_fill.findText(fill)
                if i >= 0:
                    self.cb_ac_map_fill.setCurrentIndex(i)
            diff = ac.find("diffusion_option")
            if diff is not None:
                m = diff.findtext("diffopt_method_type") or "alpha_damping"
                i = self.cb_ac_diff_method.findText(m)
                if i >= 0:
                    self.cb_ac_diff_method.setCurrentIndex(i)
                try:
                    self.sp_ac_diff_alpha.setValue(
                        float(diff.findtext("alpha") or "1"))
                except ValueError:
                    pass

    def _fill_file_tree(self) -> None:
        self.file_tree.clear()
        self._file_editors.clear()
        self._file_checks.clear()
        xml = self._ctx.get("xml")
        file_el = None
        if xml is not None:
            cond = xml.section("conditions")
            if cond is not None:
                file_el = cond.find("file")
            self.ed_project.setText(xml.project_name or "")
        for tag, label, has_out, has_browse in self._file_rows:
            fn, out = "", "false"
            if file_el is not None:
                el = file_el.find(tag)
                if el is not None:
                    fn = el.findtext("filename") or ""
                    out = el.findtext("output") or "false"
            it = QTreeWidgetItem([label, "", ""])
            it.setData(0, Qt.UserRole, tag)
            it.setIcon(0, _file_type_icon(tag, 16))
            self.file_tree.addTopLevelItem(it)
            if has_out:
                chk = QCheckBox()
                chk.setChecked(_xml_bool(out, False))
                self.file_tree.setItemWidget(it, 1, chk)
                self._file_checks[tag] = chk
            ed = QLineEdit(fn)
            if has_browse:
                wrap = QWidget()
                hl = QHBoxLayout(wrap)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.setSpacing(2)
                hl.addWidget(ed, 1)
                btn = QPushButton("...")
                btn.setFixedWidth(28)
                btn.clicked.connect(
                    lambda _=False, e=ed, t=tag:
                    self._browse_file_name(e, t))
                hl.addWidget(btn)
                self.file_tree.setItemWidget(it, 2, wrap)
            else:
                self.file_tree.setItemWidget(it, 2, ed)
            self._file_editors[tag] = ed
        # Optional conditions list from session
        opt_page = self._pages.get("optional")
        if opt_page is not None:
            lst = getattr(opt_page, "_cond_list", None)
            if lst is not None:
                lst.clear()
                for row in ((self._ctx.get("session", {})
                             .get("conditions", {})
                             .get("optional_conditions")) or []):
                    it = QTreeWidgetItem([
                        row.get("name") or "?",
                        row.get("label") or row.get("kind") or "",
                    ])
                    kind = row.get("kind") or "created"
                    it.setIcon(0, _optional_cond_icon(kind, 16))
                    it.setData(0, Qt.UserRole, kind)
                    lst.addTopLevelItem(it)

    def _browse_file_name(self, ed: QLineEdit, tag: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {tag.upper()} file", ed.text())
        if path:
            ed.setText(path)

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        xml = ctx.get("xml")
        cond = xml.section("conditions") if xml is not None else None

        # Analysis Type
        at = cond.find("analysis_type") if cond is not None else None
        for tag, chk in self._atype_checks.items():
            val = False
            if at is not None:
                val = _xml_bool(at.findtext(tag), False)
            chk.setChecked(val)

        # Basic
        bp = cond.find("basic_param") if cond is not None else None
        if bp is not None:
            steady = _xml_bool(bp.findtext("steady"), True)
            self.rb_steady.setChecked(steady)
            self.rb_trans.setChecked(not steady)
            try:
                self.sp_last_cycle.setValue(
                    int(float(bp.findtext("end_cycle") or "400")))
            except ValueError:
                pass
            _set_combo_data(self.cb_dt_type, bp.findtext("type") or "0")
            self.sp_dt.setValue(
                _bp_get_const(bp, "const_time_step_val", 0.0001))
            self.sp_dt_init.setValue(
                _bp_get_const(bp, "courant_init_time_val", 0.01))
            self.sp_courant.setValue(
                _bp_get_const(bp, "courant_num_val", 0.9))
            _set_combo_data_bool(
                self.cb_set_start, _xml_bool(bp.findtext("set_start_time")))
            self.sp_start_time.setValue(
                _bp_get_const(bp, "start_time", 0.0))
            _set_combo_data_bool(
                self.cb_set_stop, _xml_bool(bp.findtext("set_stop_time")))
            self.sp_stop_time.setValue(
                _bp_get_const(bp, "stop_time", 100.0))
            # set_dt_limit 在 xml 中可能重复；取第一个
            _set_combo_data_bool(
                self.cb_set_dt_limit,
                _xml_bool(bp.findtext("set_dt_limit")))
            self.sp_dt_upper.setValue(
                _bp_get_const(bp, "upper_limit_val", 1.0))
            self.sp_dt_lower.setValue(
                _bp_get_const(bp, "lower_limit_val", 0.01))
            _set_combo_data_bool(
                self.cb_skip, _xml_bool(bp.findtext("flow_skip_mode")))
            self.sp_skip_duration.setValue(
                _bp_get_const(bp, "skip_duration_time", 0.0))
            self.sp_skip_time.setValue(
                _bp_get_const(bp, "skip_skip_time", 0.0))
            self.sp_skip_dt.setValue(
                _bp_get_const(bp, "skip_time_step", 0.0))
            try:
                self.sp_def_temp.setValue(
                    float(bp.findtext("default_temp") or "20"))
            except ValueError:
                pass
            unit = bp.findtext("default_temp_unit") or "C"
            i = self.cb_temp_unit.findText(unit)
            if i >= 0:
                self.cb_temp_unit.setCurrentIndex(i)
            self.chk_gravity.setChecked(_xml_bool(bp.findtext("gravity")))
            try:
                gx = float(bp.findtext("gravity_x") or "0")
                gy = float(bp.findtext("gravity_y") or "0")
                gz = float(bp.findtext("gravity_z") or "-9.8")
            except ValueError:
                gx, gy, gz = 0.0, 0.0, -9.8
            mag = (gx * gx + gy * gy + gz * gz) ** 0.5
            if mag > 1e-12:
                self.sp_gx.setValue(gx / mag)
                self.sp_gy.setValue(gy / mag)
                self.sp_gz.setValue(gz / mag)
                self.sp_gmag.setValue(mag)
            else:
                self.sp_gx.setValue(0)
                self.sp_gy.setValue(0)
                self.sp_gz.setValue(-1)
                self.sp_gmag.setValue(9.8)
            self._sync_basic_cycle()

        # Output field
        op = cond.find("output_param") if cond is not None else None
        if op is not None:
            fp = op.find("fph_param")
            if fp is not None:
                t = fp.findtext("fph_output_type") or "cycle_interval"
                label = self._fph_type_from_xml.get(t, t)
                i = self.cb_fph_type.findText(label)
                if i < 0:
                    # 兼容旧 xml 字面值
                    i = self.cb_fph_type.findText(t)
                if i >= 0:
                    self.cb_fph_type.setCurrentIndex(i)
                try:
                    self.sp_fph_cycle.setValue(
                        int(float(fp.findtext("fph_cycle_interval") or "100")))
                except ValueError:
                    pass
                init = fp.findtext("fph_initial_field") or ""
                if hasattr(self, "cb_fph_init"):
                    self.cb_fph_init.setCurrentIndex(
                        1 if _xml_bool(init, False) else 0)

        self._fill_condition_lists()
        self._fill_analysis_control()
        self._fill_file_tree()
        # 恢复向导页
        draft = ctx.setdefault("session", {}).get("conditions") or {}
        key = draft.get("wizard_page") or "analysis_type"
        it = self._find_nav_item(key)
        if it is not None:
            self.nav.setCurrentItem(it)

    def apply(self, ctx: dict) -> bool:
        self._ctx = ctx
        xml = ctx.get("xml")
        dirty = False
        if xml is not None:
            cond = xml.section("conditions")
            if cond is None:
                cond = ET.SubElement(xml.root, "conditions")
            # analysis_type
            at = cond.find("analysis_type")
            if at is None:
                at = ET.SubElement(cond, "analysis_type")
            for tag, chk in self._atype_checks.items():
                _set_xml_bool(at, tag, chk.isChecked())
                dirty = True
            # basic_param
            bp = cond.find("basic_param")
            if bp is None:
                bp = ET.SubElement(cond, "basic_param")
            _set_xml_bool(bp, "steady", self.rb_steady.isChecked())
            _ensure_child_text(
                bp, "end_cycle", str(self.sp_last_cycle.value()))
            _ensure_child_text(
                bp, "type", self.cb_dt_type.currentData() or "0")
            _bp_set_const(bp, "const_time_step_val", self.sp_dt.value(), "s")
            _bp_set_const(
                bp, "courant_init_time_val", self.sp_dt_init.value(), "s")
            _bp_set_const(
                bp, "courant_num_val", self.sp_courant.value(), "-")
            _set_xml_bool(
                bp, "set_start_time",
                (self.cb_set_start.currentData() or "false") == "true")
            _bp_set_const(bp, "start_time", self.sp_start_time.value(), "s")
            _set_xml_bool(
                bp, "set_stop_time",
                (self.cb_set_stop.currentData() or "false") == "true")
            _bp_set_const(bp, "stop_time", self.sp_stop_time.value(), "s")
            _set_xml_bool(
                bp, "set_dt_limit",
                (self.cb_set_dt_limit.currentData() or "false") == "true")
            _bp_set_const(
                bp, "upper_limit_val", self.sp_dt_upper.value(), "s")
            _bp_set_const(
                bp, "lower_limit_val", self.sp_dt_lower.value(), "s")
            _set_xml_bool(
                bp, "flow_skip_mode",
                (self.cb_skip.currentData() or "false") == "true")
            _bp_set_const(
                bp, "skip_duration_time", self.sp_skip_duration.value(), "s")
            _bp_set_const(
                bp, "skip_skip_time", self.sp_skip_time.value(), "s")
            _bp_set_const(
                bp, "skip_time_step", self.sp_skip_dt.value(), "s")
            _ensure_child_text(
                bp, "default_temp", _fmt_float(self.sp_def_temp.value()))
            _ensure_child_text(
                bp, "default_temp_unit", self.cb_temp_unit.currentText())
            _set_xml_bool(bp, "gravity", self.chk_gravity.isChecked())
            gx = self.sp_gx.value() * self.sp_gmag.value()
            gy = self.sp_gy.value() * self.sp_gmag.value()
            gz = self.sp_gz.value() * self.sp_gmag.value()
            _ensure_child_text(bp, "gravity_x", _fmt_float(gx))
            _ensure_child_text(bp, "gravity_y", _fmt_float(gy))
            _ensure_child_text(bp, "gravity_z", _fmt_float(gz))
            dirty = True
            # output
            op = cond.find("output_param")
            if op is None:
                op = ET.SubElement(cond, "output_param")
            fp = op.find("fph_param")
            if fp is None:
                fp = ET.SubElement(op, "fph_param")
            fph_lab = self.cb_fph_type.currentText()
            _ensure_child_text(
                fp, "fph_output_type",
                self._fph_type_xml.get(fph_lab, fph_lab))
            _ensure_child_text(
                fp, "fph_cycle_interval", str(self.sp_fph_cycle.value()))
            if hasattr(self, "cb_fph_init"):
                _set_xml_bool(
                    fp, "fph_initial_field",
                    self.cb_fph_init.currentIndex() == 1)
            # analysis_control
            ac = cond.find("analysis_control")
            if ac is None:
                ac = ET.SubElement(cond, "analysis_control")
            loop = ac.find("loop")
            if loop is None:
                loop = ET.SubElement(ac, "loop")
            _set_xml_bool(
                loop, "nloop_default", self.chk_ac_loop_default.isChecked())
            _ensure_child_text(loop, "type", "0")
            _ensure_child_text(
                loop, "const_value", str(self.sp_ac_loop_max.value()))
            loop_min = ac.find("loop_min")
            if loop_min is None:
                loop_min = ET.SubElement(ac, "loop_min")
            _ensure_child_text(loop_min, "type", "0")
            _ensure_child_text(
                loop_min, "const_value", str(self.sp_ac_loop_min.value()))
            ta = ac.find("time_accuracy")
            if ta is None:
                ta = ET.SubElement(ac, "time_accuracy")
            _ensure_child_text(
                ta, "order",
                "1" if self.rb_ac_time_2nd.isChecked() else "0")
            solv = ac.find("solv")
            if solv is None:
                solv = ET.SubElement(ac, "solv")
            if self.rb_ac_solv_acc.isChecked():
                stype = "accuracy"
            elif self.rb_ac_solv_detail.isChecked():
                stype = "detail"
            else:
                stype = "speed"
            _ensure_child_text(solv, "type", stype)
            pcty = ac.find("pcty")
            if pcty is None:
                pcty = ET.SubElement(ac, "pcty")
            pdata = self.cb_ac_pcty.currentData() or "default"
            is_def = pdata == "default"
            _set_xml_bool(pcty, "bdefault", is_def)
            # default → SIMPLEC(2)；其余直接写代码
            ipcty = "2" if is_def else (
                "2" if pdata == "td" else str(pdata))
            _ensure_child_text(pcty, "ipcty", ipcty)
            undr = ac.find("undr")
            if undr is None:
                undr = ET.SubElement(ac, "undr")
            _set_xml_bool(
                undr, "loop_undr_flag",
                self.chk_ac_undr_transient.isChecked())
            for i in range(self.ac_undr_tree.topLevelItemCount()):
                it = self.ac_undr_tree.topLevelItem(i)
                tag = it.data(0, Qt.UserRole)
                if not tag:
                    continue
                node = undr.find(tag)
                if node is None:
                    node = ET.SubElement(undr, tag)
                _ensure_child_text(node, "type", "0")
                detail = it.text(2) or "Value : 0.9"
                val = detail.split(":")[-1].strip() if ":" in detail else detail
                _ensure_child_text(node, "const_value", val or "0.9")
            sted = ac.find("sted")
            if sted is None:
                sted = ET.SubElement(ac, "sted")
            # 从参数树读 cycle interval（若有）
            cyc = self.sp_ac_sted_cycle.value()
            for i in range(self.ac_sted_param.topLevelItemCount()):
                it = self.ac_sted_param.topLevelItem(i)
                if "Cycle interval" in it.text(0) and it.text(1).strip():
                    try:
                        cyc = int(float(it.text(1)))
                    except ValueError:
                        pass
            self.sp_ac_sted_cycle.setValue(cyc)
            _ensure_child_text(sted, "cycle_interval", str(cyc))
            # mapping / diffusion
            map_el = ac.find("mapping_option")
            if map_el is None:
                map_el = ET.SubElement(ac, "mapping_option")
            _ensure_child_text(
                map_el, "match_probability",
                _fmt_float(self.sp_ac_map_prob.value()))
            _ensure_child_text(
                map_el, "average_field", self.cb_ac_map_avg.currentText())
            _ensure_child_text(
                map_el, "filling_method", self.cb_ac_map_fill.currentText())
            diff = ac.find("diffusion_option")
            if diff is None:
                diff = ET.SubElement(ac, "diffusion_option")
            _ensure_child_text(
                diff, "diffopt_method_type",
                self.cb_ac_diff_method.currentText())
            _ensure_child_text(
                diff, "alpha", _fmt_float(self.sp_ac_diff_alpha.value()))
            dirty = True
            # file names
            file_el = cond.find("file")
            if file_el is None:
                file_el = ET.SubElement(cond, "file")
            for tag, _lab, has_out, _br in self._file_rows:
                el = file_el.find(tag)
                if el is None:
                    el = ET.SubElement(file_el, tag)
                ed = self._file_editors.get(tag)
                _ensure_child_text(
                    el, "filename", ed.text().strip() if ed else "")
                if has_out:
                    chk = self._file_checks.get(tag)
                    _ensure_child_text(
                        el, "output",
                        "true" if (chk is not None and chk.isChecked())
                        else "false")
                else:
                    # SPH/GPH/FPH 等无勾选时保持已有或默认 false
                    if el.findtext("output") is None:
                        _ensure_child_text(el, "output", "false")
            dirty = True
            if dirty:
                ctx["xml_dirty"] = True

        sess = ctx.setdefault("session", {}).setdefault("conditions", {})
        sess["wizard_page"] = self._current_key() or "analysis_type"
        sess["analysis_type"] = {
            tag: chk.isChecked() for tag, chk in self._atype_checks.items()}
        sess["basic"] = {
            "steady": self.rb_steady.isChecked(),
            "end_cycle": self.sp_last_cycle.value(),
            "dt_type": self.cb_dt_type.currentData(),
            "time_step": self.sp_dt.value(),
            "dt_init": self.sp_dt_init.value(),
            "courant": self.sp_courant.value(),
            "set_start": self.cb_set_start.currentData(),
            "start_time": self.sp_start_time.value(),
            "set_stop": self.cb_set_stop.currentData(),
            "stop_time": self.sp_stop_time.value(),
            "set_dt_limit": self.cb_set_dt_limit.currentData(),
            "skip_mode": self.cb_skip.currentData(),
            "default_temp": self.sp_def_temp.value(),
            "temp_unit": self.cb_temp_unit.currentText(),
            "gravity": self.chk_gravity.isChecked(),
        }
        return True


_BAM_WIZARD_PAGES = [
    ("interference", "Solution Method for Solid/Sheet Interference"),
    ("multifold", "Configuration of Multi-fold Edges and Faces"),
    ("acc_whole", "Facet Accuracy for Whole Model"),
    ("acc_part", "Facet Accuracy for Part and Region"),
    ("influence", "Influence of adjacent part"),
    ("auto_tiny", "Automatic Removal of Tiny Faces"),
    ("face_match", "Create Facet/Face Matching"),
    ("remove_tiny", "Remove Tiny Faces"),
    ("repair", "Repair Facet/Result Report"),
]


def _bam_slider_row(label: str, spin: QWidget, unit: str = "",
                    lo: int = 0, hi: int = 100, val: int = 50) -> QWidget:
    """标签 + 滑条 + 数值控件（对齐 Analysis Model Wizard）。"""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2)
    lab = QLabel(label)
    lab.setMinimumWidth(220)
    h.addWidget(lab)
    sl = QSlider(Qt.Horizontal)
    sl.setRange(lo, hi)
    sl.setValue(val)
    h.addWidget(sl, 1)
    h.addWidget(spin)
    if unit:
        h.addWidget(QLabel(unit))
    w._slider = sl  # type: ignore[attr-defined]
    return w


class _FacetAccuracyEditDialog(QDialog):
    """Facet Accuracy for Part and Region — Edit 子对话框。

    Solid-based (AF)：角度下限 / 缩减比 1:N / 最大边；
    Parasolid：distance / angle / max edge。
    """

    def __init__(self, title: str, af: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Facet Accuracy — {title}")
        self._af = af
        form = QFormLayout(self)
        if af:
            self.sp_ang = _spin_f(3, 0, 180, 10)
            self.sp_den = QSpinBox(); self.sp_den.setRange(1, 1000)
            self.sp_den.setValue(20)
            self.sp_edge = _spin_f(6, 0, 1e6, 5)
            form.addRow("Lower limit of angular precision", self.sp_ang)
            form.addRow("Reduction ratio 1/N", self.sp_den)
            form.addRow("Maximum edge ×", self.sp_edge)
        else:
            self.sp_dist = _spin_f(6, 0, 1e6, 1)
            self.sp_ang = _spin_f(3, 0, 180, 10)
            self.sp_edge = _spin_f(6, 0, 1e6, 5)
            form.addRow("Precision of distance", self.sp_dist)
            form.addRow("Precision of angle", self.sp_ang)
            form.addRow("Maximum edge", self.sp_edge)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def label(self) -> str:
        if self._af:
            return (f"AF {self.sp_ang.value():g}° "
                    f"1/{self.sp_den.value()} ×{self.sp_edge.value():g}")
        return (f"PS d={self.sp_dist.value():g} "
                f"a={self.sp_ang.value():g} e={self.sp_edge.value():g}")


class AnalysisModelWizardBody(_Body):
    """Analysis Model Wizard — Build Analysis Model 确认框的 Detailed… 扩充。"""

    title = "Analysis Model Wizard"
    min_size = (920, 640)
    dialog_buttons = 0  # Back / Next / Create Facet / Close|Build 在内容区

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._pages: dict[str, QWidget] = {}
        self._page_keys = [k for k, _ in _BAM_WIZARD_PAGES]
        self._part_acc: dict[str, str] = {}
        self._region_acc: dict[str, str] = {}
        self._buildable = True

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        split = QHBoxLayout()

        self.nav = QListWidget()
        self.nav.setMinimumWidth(240)
        self.nav.setMaximumWidth(300)
        for key, title in _BAM_WIZARD_PAGES:
            it = QListWidgetItem(title)
            it.setData(Qt.UserRole, key)
            self.nav.addItem(it)
        split.addWidget(self.nav)

        self.stack = QStackedWidget()
        self._build_pages()
        for key, _ in _BAM_WIZARD_PAGES:
            self.stack.addWidget(self._pages[key])
        split.addWidget(self.stack, 1)
        root.addLayout(split, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_back = QPushButton("<< Back")
        self.btn_next = QPushButton("Next >>")
        self.btn_create = QPushButton("Create Facet")
        self.btn_close = QPushButton("Close")
        self.btn_build = QPushButton("Build")
        self.btn_build.setVisible(False)
        for b in (self.btn_back, self.btn_next, self.btn_create,
                  self.btn_close, self.btn_build):
            foot.addWidget(b)
        root.addLayout(foot)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_create.clicked.connect(self._create_facet)
        self.btn_close.clicked.connect(self._close)
        self.btn_build.clicked.connect(self._build)
        self.chk_use_af.toggled.connect(self._sync_faceter_ui)
        self.cb_acc_type.currentIndexChanged.connect(self._sync_faceter_ui)
        self.chk_abs.toggled.connect(self._sync_abs_ui)
        self.chk_elem_use.toggled.connect(self._sync_elem_ui)
        self.nav.setCurrentRow(0)
        self._sync_faceter_ui()
        self._sync_elem_ui()
        self._sync_nav_buttons()

    # ── pages ──────────────────────────────────────────────────────

    def _build_pages(self) -> None:
        self._pages["interference"] = self._page_interference()
        self._pages["multifold"] = self._page_multifold()
        self._pages["acc_whole"] = self._page_acc_whole()
        self._pages["acc_part"] = self._page_acc_part()
        self._pages["influence"] = self._page_influence()
        self._pages["auto_tiny"] = self._page_auto_tiny()
        self._pages["face_match"] = self._page_face_match()
        self._pages["remove_tiny"] = self._page_remove_tiny()
        self._pages["repair"] = self._page_repair()

    def _page_interference(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        gb = QGroupBox("Definition of boundary edges")
        gbv = QVBoxLayout(gb)
        self.chk_proj_solids = QCheckBox("Project solids")
        self.chk_proj_solids.setChecked(True)
        self.chk_proj_sheets = QCheckBox("Project sheets")
        self.chk_proj_sheets.setChecked(True)
        gbv.addWidget(self.chk_proj_solids)
        gbv.addWidget(self.chk_proj_sheets)
        v.addWidget(gb)

        self.chk_use_af = QCheckBox("Use solid-based faceter")
        self.chk_use_af.setChecked(True)
        v.addWidget(self.chk_use_af)

        row = QHBoxLayout()
        row.addWidget(QLabel("Specification type of faceting accuracy"))
        self.cb_acc_type = QComboBox()
        self.cb_acc_type.addItem("Specify value", "0")
        self.cb_acc_type.addItem("Specify octree", "1")
        self.cb_acc_type.setMinimumWidth(160)
        self.btn_bam_octree = QPushButton("Octree Parameter for BAM…")
        self.btn_bam_octree.clicked.connect(self._open_bam_octree)
        self.btn_bam_octree.setVisible(False)
        row.addWidget(self.cb_acc_type)
        row.addWidget(self.btn_bam_octree)
        row.addStretch(1)
        v.addLayout(row)

        self.gb_elem = QGroupBox("Element size parameter")
        eg = QGridLayout(self.gb_elem)
        self.chk_elem_use = QCheckBox("Use")
        eg.addWidget(self.chk_elem_use, 0, 0, 1, 2)
        eg.addWidget(QLabel("Direction of effect"), 1, 0)
        self.cb_elem_dir = QComboBox()
        self.cb_elem_dir.addItems([
            "Fix on fine side", "Fix on coarse side"])
        eg.addWidget(self.cb_elem_dir, 1, 1)
        eg.addWidget(QLabel("Range of effect"), 2, 0)
        self.sp_elem_range = QSpinBox()
        self.sp_elem_range.setRange(1, 100)
        self.sp_elem_range.setValue(5)
        self.sl_elem_range = QSlider(Qt.Horizontal)
        self.sl_elem_range.setRange(1, 100)
        self.sl_elem_range.setValue(5)
        self.sl_elem_range.valueChanged.connect(self.sp_elem_range.setValue)
        self.sp_elem_range.valueChanged.connect(self.sl_elem_range.setValue)
        er = QHBoxLayout()
        er.addWidget(self.sl_elem_range, 1)
        er.addWidget(self.sp_elem_range)
        eg.addLayout(er, 2, 1)
        v.addWidget(self.gb_elem)
        v.addStretch(1)
        return w

    def _page_multifold(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        self.tabs_mf = QTabWidget()
        # Edges
        pe = QWidget()
        ve = QVBoxLayout(pe)
        ve.addWidget(QLabel("Recognized multi-fold edges"))
        self.tree_mf_edges = QTreeWidget()
        self.tree_mf_edges.setHeaderHidden(True)
        self.tree_mf_edges.setRootIsDecorated(True)
        ve.addWidget(self.tree_mf_edges, 1)
        self.tabs_mf.addTab(pe, "Multi-Fold Edges")
        # Faces
        pf = QWidget()
        vf = QVBoxLayout(pf)
        vf.addWidget(QLabel("Recognized multi-fold faces"))
        self.tree_mf_faces = QTreeWidget()
        self.tree_mf_faces.setHeaderHidden(True)
        self.tree_mf_faces.setRootIsDecorated(True)
        vf.addWidget(self.tree_mf_faces, 1)
        self.tabs_mf.addTab(pf, "Multi-Fold Faces")
        v.addWidget(self.tabs_mf, 1)

        form = QGridLayout()
        form.addWidget(QLabel("Tolerance to regard as multi-fold edge"), 0, 0)
        row_e = QHBoxLayout()
        row_e.addWidget(QLabel("1/"))
        self.ed_tol_edge = QLineEdit("1e+06")
        self.ed_tol_edge.setMaximumWidth(120)
        row_e.addWidget(self.ed_tol_edge)
        row_e.addStretch(1)
        form.addLayout(row_e, 0, 1)
        form.addWidget(QLabel("Tolerance to regard as multi-fold face"), 1, 0)
        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("1/"))
        self.ed_tol_face = QLineEdit("1e+06")
        self.ed_tol_face.setMaximumWidth(120)
        row_f.addWidget(self.ed_tol_face)
        row_f.addStretch(1)
        form.addLayout(row_f, 1, 1)
        self.btn_mf_apply = QPushButton("Apply")
        self.btn_mf_apply.clicked.connect(self._apply_multifold)
        form.addWidget(self.btn_mf_apply, 0, 2, 2, 1)
        v.addLayout(form)
        return w

    def _page_acc_whole(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.addWidget(QLabel("Facet accuracy for the whole model"))
        self.lab_acc_hint = QLabel(
            "Set facet accuracy relative to the reference values.\n"
            "(Slide right to obtain finer facet)")
        self.lab_acc_hint.setStyleSheet("color:#444;")
        v.addWidget(self.lab_acc_hint)

        # Solid-based relative
        self.sp_sb_ang = _spin_f(3, 0, 180, 10)
        self.row_sb_ang = _bam_slider_row(
            "Lower limit of angular precision", self.sp_sb_ang, "deg",
            1, 90, 10)
        self.row_sb_ang._slider.valueChanged.connect(  # type: ignore
            lambda x: self.sp_sb_ang.setValue(float(x)))
        self.sp_sb_ang.valueChanged.connect(
            lambda x: self.row_sb_ang._slider.setValue(int(x)))  # type: ignore
        v.addWidget(self.row_sb_ang)

        self.sp_sb_den = QSpinBox()
        self.sp_sb_den.setRange(1, 10000)
        self.sp_sb_den.setValue(20)
        wrap_den = QWidget()
        hd = QHBoxLayout(wrap_den)
        hd.setContentsMargins(0, 0, 0, 0)
        hd.addWidget(QLabel("1 /"))
        hd.addWidget(self.sp_sb_den)
        self.row_sb_len = _bam_slider_row(
            "Reduction ratio of edge length", wrap_den, "", 1, 200, 20)
        self.row_sb_len._slider.valueChanged.connect(  # type: ignore
            self.sp_sb_den.setValue)
        self.sp_sb_den.valueChanged.connect(
            self.row_sb_len._slider.setValue)  # type: ignore
        v.addWidget(self.row_sb_len)

        self.sp_max_edge = _spin_f(3, 0, 1e6, 5)
        wrap_edge = QWidget()
        he = QHBoxLayout(wrap_edge)
        he.setContentsMargins(0, 0, 0, 0)
        he.addWidget(QLabel("x"))
        he.addWidget(self.sp_max_edge)
        self.row_max_edge = _bam_slider_row(
            "Maximum edge length", wrap_edge, "", 1, 100, 5)
        self.row_max_edge._slider.valueChanged.connect(  # type: ignore
            lambda x: self.sp_max_edge.setValue(float(x)))
        self.sp_max_edge.valueChanged.connect(
            lambda x: self.row_max_edge._slider.setValue(  # type: ignore
                int(min(100, max(1, x)))))
        v.addWidget(self.row_max_edge)

        # Parasolid relative (hidden when AF)
        self.sp_ps_dist = _spin_f(3, 0, 1e6, 1)
        self.row_ps_dist = _bam_slider_row(
            "Precision of distance", self.sp_ps_dist, "-", 1, 100, 1)
        v.addWidget(self.row_ps_dist)
        self.sp_ps_ang = _spin_f(3, 0, 180, 10)
        self.row_ps_ang = _bam_slider_row(
            "Precision of angle", self.sp_ps_ang, "deg", 1, 90, 10)
        v.addWidget(self.row_ps_ang)

        # Absolute extras
        self.sp_dist_abs = _spin_f(12, 0, 1e6, 0)
        self.row_dist_abs = _bam_slider_row(
            "Precision of distance (absolute)", self.sp_dist_abs, "m",
            0, 100, 0)
        v.addWidget(self.row_dist_abs)
        self.sp_edge_abs = _spin_f(12, 0, 1e6, 0)
        self.row_edge_abs = _bam_slider_row(
            "Maximum edge length (absolute)", self.sp_edge_abs, "m",
            0, 100, 0)
        v.addWidget(self.row_edge_abs)

        row_abs = QHBoxLayout()
        self.chk_abs = QCheckBox("Specify absolute value")
        row_abs.addWidget(self.chk_abs)
        row_abs.addStretch(1)
        self.btn_acc_reset = QPushButton("Reset to the default value")
        self.btn_acc_reset.clicked.connect(self._reset_acc_defaults)
        row_abs.addWidget(self.btn_acc_reset)
        v.addLayout(row_abs)

        gb = QGroupBox("Preview mesh accuracy")
        gbv = QVBoxLayout(gb)
        gbv.addWidget(_note("Mark parts or faces to verify facet precision."))
        br = QHBoxLayout()
        br.addStretch(1)
        self.btn_prev_clear = QPushButton("Clear preview")
        self.btn_prev_clear.setEnabled(False)
        self.btn_prev_draw = QPushButton("Preview in draw window")
        self.btn_prev_draw.setEnabled(False)
        br.addWidget(self.btn_prev_clear)
        br.addWidget(self.btn_prev_draw)
        gbv.addLayout(br)
        v.addWidget(gb)
        v.addStretch(1)
        return w

    def _page_acc_part(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.addWidget(_note(
            "Set facet accuracy for parts and regions. "
            "By default, the facet accuracy for the whole model is used."))
        row = QHBoxLayout()
        self.tree_acc_part = QTreeWidget()
        self.tree_acc_part.setHeaderLabels(["Region Name", "Facet Accuracy"])
        self.tree_acc_part.setColumnWidth(0, 220)
        row.addWidget(self.tree_acc_part, 1)
        side = QVBoxLayout()
        self.btn_acc_edit = QPushButton("Edit")
        self.btn_acc_def = QPushButton("Default")
        self.btn_acc_edit.clicked.connect(self._edit_part_acc)
        self.btn_acc_def.clicked.connect(self._default_part_acc)
        side.addWidget(self.btn_acc_edit)
        side.addWidget(self.btn_acc_def)
        side.addStretch(1)
        row.addLayout(side)
        v.addLayout(row, 1)

        gb = QGroupBox("Preview mesh accuracy")
        gbv = QVBoxLayout(gb)
        self.lab_prev_parts = QLabel("0 parts are marked.")
        gbv.addWidget(self.lab_prev_parts)
        br = QHBoxLayout()
        br.addStretch(1)
        btn_c = QPushButton("Clear preview")
        btn_c.setEnabled(False)
        btn_p = QPushButton("Preview in draw window")
        btn_p.setEnabled(False)
        br.addWidget(btn_c)
        br.addWidget(btn_p)
        gbv.addLayout(br)
        v.addWidget(gb)
        return w

    def _page_influence(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        self.chk_influence = QCheckBox(
            "Consider the edge lengths of spatially adjacent facets")
        v.addWidget(self.chk_influence)
        lab = QLabel(
            "Specify the region that affects the edge lengths of the "
            "spatially adjacent facets. When OFF, the Target column is "
            "ignored.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.tbl_influence = QTableWidget(0, 2)
        self.tbl_influence.setHorizontalHeaderLabels(
            ["Region Name", "Target"])
        self.tbl_influence.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl_influence, 1)
        row = QHBoxLayout()
        self.btn_inf_set = QPushButton("Set")
        self.btn_inf_remove = QPushButton("Remove")
        self.btn_inf_set.clicked.connect(self._influence_set)
        self.btn_inf_remove.clicked.connect(self._influence_remove)
        row.addWidget(self.btn_inf_set)
        row.addWidget(self.btn_inf_remove)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _influence_set(self) -> None:
        row = self.tbl_influence.currentRow()
        if row < 0:
            return
        item = self.tbl_influence.item(row, 1)
        if item is None:
            item = QTableWidgetItem("Target")
            self.tbl_influence.setItem(row, 1, item)
        item.setText("Target")

    def _influence_remove(self) -> None:
        row = self.tbl_influence.currentRow()
        if row >= 0:
            item = self.tbl_influence.item(row, 1)
            if item is not None:
                item.setText("")

    def _page_auto_tiny(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.addWidget(_note(
            "Set the reference value and target for the automatic removal "
            "of tiny faces. This setting is valid only when using the "
            "solid-based faceter."))
        self.chk_tiny_only = QCheckBox("Show only parts with tiny faces")
        self.chk_tiny_center = QCheckBox("Move view center to selection face")
        v.addWidget(self.chk_tiny_only)
        v.addWidget(self.chk_tiny_center)

        split = QHBoxLayout()
        left = QVBoxLayout()
        self.tree_tiny_parts = QTreeWidget()
        self.tree_tiny_parts.setHeaderLabels(["Part Name", "Reference"])
        self.tree_tiny_parts.setColumnWidth(0, 160)
        left.addWidget(self.tree_tiny_parts, 1)
        bl = QHBoxLayout()
        self.btn_tiny_edit = QPushButton("Edit")
        self.btn_tiny_def = QPushButton("Default")
        self.btn_tiny_edit.clicked.connect(self._edit_tiny_ref)
        self.btn_tiny_def.clicked.connect(self._default_tiny_ref)
        bl.addWidget(self.btn_tiny_edit)
        bl.addWidget(self.btn_tiny_def)
        left.addLayout(bl)
        self.btn_tiny_rerec = QPushButton("Re-recognize tiny faces")
        self.btn_tiny_rerec.clicked.connect(self._rerec_tiny)
        left.addWidget(self.btn_tiny_rerec)
        split.addLayout(left, 1)

        right = QVBoxLayout()
        self.tree_tiny_faces = QTreeWidget()
        self.tree_tiny_faces.setHeaderLabels(
            ["Part Name", "Num", "Width", "Target"])
        right.addWidget(self.tree_tiny_faces, 1)
        self.btn_tiny_excl = QPushButton("Exclude from auto removal")
        self.btn_tiny_incl = QPushButton("Specify for auto removal")
        right.addWidget(self.btn_tiny_excl)
        right.addWidget(self.btn_tiny_incl)
        split.addLayout(right, 1)
        v.addLayout(split, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Default reference value"))
        self.sp_tiny_pct = _spin_f(3, 0, 100, 5)
        row.addWidget(self.sp_tiny_pct)
        row.addWidget(QLabel("%"))
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _page_face_match(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.addWidget(QLabel("List of matching faces"))
        self.tbl_match = QTableWidget(0, 6)
        self.tbl_match.setHorizontalHeaderLabels([
            "", "Group1 (N)", "Group2 (N)", "Minimum distance",
            "Maximum distance", "Matching Direction",
        ])
        self.tbl_match.horizontalHeader().setStretchLastSection(True)
        self.tbl_match.setColumnWidth(0, 28)
        v.addWidget(self.tbl_match, 1)
        v.addWidget(_note(
            "The face matching is available when using the solid-based "
            "faceter."))
        grid = QGridLayout()
        self.btn_rev_dir = QPushButton("Reverse matching direction")
        self.btn_chg_tol = QPushButton("Change Tolerance")
        self.btn_match_prev = QPushButton("Preview")
        self.btn_match = QPushButton("Match")
        self.btn_rev_dir.clicked.connect(self._reverse_match_dir)
        self.btn_chg_tol.clicked.connect(self._change_match_tol)
        self.btn_match.clicked.connect(lambda: self._stub_action("Match"))
        self.btn_match_prev.clicked.connect(
            lambda: self._stub_action("Preview"))
        grid.addWidget(self.btn_rev_dir, 0, 0)
        grid.addWidget(self.btn_chg_tol, 0, 1)
        grid.addWidget(self.btn_match_prev, 1, 0)
        grid.addWidget(self.btn_match, 1, 1)
        v.addLayout(grid)
        self.sp_match_tol = _spin_f(6, 0, 1e3, 0.001)
        return w

    def _page_remove_tiny(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.addWidget(QLabel("Tiny face list"))
        self.tbl_rm_tiny = QTableWidget(0, 4)
        self.tbl_rm_tiny.setHorizontalHeaderLabels([
            "Part name", "Face ID", "Index value of face width",
            "Number of facets",
        ])
        self.tbl_rm_tiny.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl_rm_tiny, 1)

        gb = QGroupBox("Tolerance for tiny face")
        gbh = QHBoxLayout(gb)
        self.rb_tiny_abs = QRadioButton("Specify width by absolute value")
        self.rb_tiny_abs.setChecked(True)
        gbh.addWidget(self.rb_tiny_abs)
        self.sp_rm_tol = _spin_f(6, 0, 1e3, 0.001)
        gbh.addWidget(self.sp_rm_tol)
        gbh.addWidget(QLabel("m"))
        gbh.addStretch(1)
        v.addWidget(gb)

        br = QHBoxLayout()
        br.addStretch(1)
        self.btn_rm_refresh = QPushButton("Refresh list")
        self.btn_rm_remove = QPushButton("Remove")
        self.btn_rm_refresh.clicked.connect(self._refresh_rm_tiny)
        self.btn_rm_remove.clicked.connect(
            lambda: self._stub_action("Remove tiny faces"))
        br.addWidget(self.btn_rm_refresh)
        br.addWidget(self.btn_rm_remove)
        v.addLayout(br)
        return w

    def _page_repair(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel("Illegal shape report of created facet"))
        self.lab_err_count = QLabel("0")
        self.lab_err_count.setStyleSheet("font-weight:bold;")
        top.addWidget(self.lab_err_count)
        top.addStretch(1)
        v.addLayout(top)

        self.tbl_report = QTableWidget(0, 4)
        self.tbl_report.setHorizontalHeaderLabels([
            "Level", "Number of faces", "Type", "Cause",
        ])
        self.tbl_report.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl_report, 1)

        gb1 = QGroupBox("Type of problem")
        g1 = QHBoxLayout(gb1)
        g1.addWidget(QLabel("Level"))
        self.lab_prob_level = QLabel("0")
        g1.addWidget(self.lab_prob_level)
        self.ed_prob_filter = QLineEdit()
        self.ed_prob_filter.setEnabled(False)
        self.ed_prob_filter.setMaximumWidth(80)
        g1.addWidget(self.ed_prob_filter)
        g1.addStretch(1)
        self.btn_rep_refresh = QPushButton("Refresh list")
        self.btn_rep_refresh.clicked.connect(self._refresh_report)
        g1.addWidget(self.btn_rep_refresh)
        v.addWidget(gb1)

        gb2 = QGroupBox("Cause and solution")
        g2 = QVBoxLayout(gb2)
        self.txt_cause = QTextEdit()
        self.txt_cause.setReadOnly(True)
        self.txt_cause.setMaximumHeight(90)
        self.txt_cause.setPlainText(
            "No interference or unintentional isolated/multifold edge "
            "is found.")
        g2.addWidget(self.txt_cause)
        br = QHBoxLayout()
        br.addStretch(1)
        self.btn_clean_all = QPushButton("Clean all")
        self.btn_clean = QPushButton("Clean")
        self.btn_clean_all.clicked.connect(
            lambda: self._stub_action("Clean all"))
        self.btn_clean.clicked.connect(lambda: self._stub_action("Clean"))
        br.addWidget(self.btn_clean_all)
        br.addWidget(self.btn_clean)
        g2.addLayout(br)
        v.addWidget(gb2)
        return w

    # ── navigation / sync ──────────────────────────────────────────

    def _current_key(self) -> str:
        it = self.nav.currentItem()
        if it is None:
            return self._page_keys[0]
        return it.data(Qt.UserRole) or self._page_keys[0]

    def _on_nav(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        self._sync_nav_buttons()

    def _visible_keys(self) -> list[str]:
        keys = list(self._page_keys)
        # solid-based + octree：隐藏整模/局部精度与自动去除微小面
        if self.chk_use_af.isChecked() and self.cb_acc_type.currentData() == "1":
            for k in ("acc_whole", "acc_part", "auto_tiny"):
                if k in keys:
                    keys.remove(k)
        return keys

    def _sync_nav_list_visibility(self) -> None:
        vis = set(self._visible_keys())
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            key = it.data(Qt.UserRole)
            it.setHidden(key not in vis)

    def _sync_nav_buttons(self) -> None:
        keys = self._visible_keys()
        key = self._current_key()
        if key not in keys and keys:
            # 跳到第一个可见页
            for i in range(self.nav.count()):
                it = self.nav.item(i)
                if it.data(Qt.UserRole) == keys[0]:
                    self.nav.setCurrentRow(i)
                    key = keys[0]
                    break
        idx = keys.index(key) if key in keys else 0
        self.btn_back.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(keys) - 1)
        on_repair = key == "repair"
        self.btn_create.setVisible(not on_repair)
        self.btn_create.setEnabled(not on_repair)
        self.btn_close.setVisible(not on_repair)
        self.btn_build.setVisible(on_repair)
        self.btn_build.setEnabled(self._buildable)

    def _go_back(self) -> None:
        keys = self._visible_keys()
        key = self._current_key()
        if key not in keys:
            return
        idx = keys.index(key)
        if idx <= 0:
            return
        target = keys[idx - 1]
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == target:
                self.nav.setCurrentRow(i)
                break

    def _go_next(self) -> None:
        keys = self._visible_keys()
        key = self._current_key()
        if key not in keys:
            return
        idx = keys.index(key)
        if idx >= len(keys) - 1:
            return
        target = keys[idx + 1]
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == target:
                self.nav.setCurrentRow(i)
                break

    def _sync_elem_ui(self) -> None:
        on = self.chk_elem_use.isChecked()
        self.cb_elem_dir.setEnabled(on)
        self.sp_elem_range.setEnabled(on)
        self.sl_elem_range.setEnabled(on)

    def _sync_abs_ui(self) -> None:
        abs_on = self.chk_abs.isChecked()
        af = self.chk_use_af.isChecked()
        self.row_dist_abs.setVisible(abs_on)
        self.row_edge_abs.setVisible(abs_on)
        if af:
            self.row_max_edge.setVisible(not abs_on)
            self.row_sb_len.setVisible(True)
            self.row_sb_ang.setVisible(True)
        else:
            self.row_ps_dist.setVisible(not abs_on)
            self.row_max_edge.setVisible(not abs_on)

    def _sync_faceter_ui(self, *_args) -> None:
        af = self.chk_use_af.isChecked()
        octree = self.cb_acc_type.currentData() == "1"
        self.cb_acc_type.setEnabled(af)
        # Element size：手册图中默认灰显；solid-based 时可用
        self.gb_elem.setEnabled(af)
        if not af:
            self.chk_elem_use.setChecked(False)

        self.row_sb_ang.setVisible(af and not octree)
        self.row_sb_len.setVisible(af and not octree)
        self.row_ps_dist.setVisible(not af)
        self.row_ps_ang.setVisible(not af)
        self._sync_abs_ui()
        self.chk_abs.setEnabled(not octree)
        self.btn_bam_octree.setVisible(af and octree)
        self._sync_nav_list_visibility()
        self._sync_nav_buttons()
        # face matching / auto tiny only meaningful for AF
        for btn in (self.btn_match, self.btn_rev_dir, self.btn_chg_tol,
                    self.btn_match_prev, self.btn_tiny_edit,
                    self.btn_tiny_rerec):
            btn.setEnabled(af)

    def _open_bam_octree(self) -> None:
        data = self._ctx.setdefault("session", {}).setdefault(
            "build_am_octree", {})
        dlg = OctreeDetailDialog(data, self._ctx, self)
        if dlg.exec_() == QDialog.Accepted:
            # OctreeDetailDialog 会把参数写回 data（session["build_am_octree"]）
            self._ctx.setdefault("session", {})["build_am_octree"] = data

    def _reset_acc_defaults(self) -> None:
        self.sp_sb_ang.setValue(10)
        self.sp_sb_den.setValue(20)
        self.sp_max_edge.setValue(5)
        self.sp_ps_dist.setValue(1)
        self.sp_ps_ang.setValue(10)
        self.chk_abs.setChecked(False)
        self.sp_dist_abs.setValue(0)
        self.sp_edge_abs.setValue(0)

    # ── page actions ───────────────────────────────────────────────

    def _stub_action(self, name: str) -> None:
        """BAM Wizard 几何动作：记入 session 并生成 VBS 步骤注释。

        同时把动作映射为原生 BAM（``native_bam``）步骤标志：未启用
        scFLOWpre API 时由 Execute / Build 的原生管线执行对应步骤。
        """
        sess = self._ctx.setdefault("session", {}).setdefault("build_am", {})
        steps = list(sess.get("vbs_steps") or [])
        steps.append(name)
        sess["vbs_steps"] = steps
        sess["pending_vbs"] = {
            "op": "bam_wizard",
            "label": name,
            "steps": list(steps),
        }
        # 原生 BAM 步骤标志（与 MDLWizard 录制命令对应）
        flag = {
            "Match": "apply_face_matching",          # SetFaceMatched
            "Clean": "repair",                       # RepairMDL
            "Clean all": "repair",                   # RepairMDL
            "Remove tiny faces": "remove_tiny",      # SetTinyFacesRemoved
        }.get(name)
        if flag:
            sess[flag] = True
        QMessageBox.information(
            self, name,
            f"{name} recorded as VBS step "
            f"({len(steps)} queued).\n"
            "OK/Build will include these as comments in the host script;\n"
            "native mode (scFLOWpre API off) runs them via native_bam.")

    def _apply_multifold(self) -> None:
        sess = self._ctx.setdefault("session", {}).setdefault("build_am", {})
        sess["tol_multifold_edge"] = self.ed_tol_edge.text().strip()
        sess["tol_multifold_face"] = self.ed_tol_face.text().strip()
        QMessageBox.information(
            self, "Multi-fold",
            "Tolerance applied. Re-recognition of multi-fold edges/faces "
            "requires scFLOWpre.")

    def _edit_part_acc(self) -> None:
        it = self.tree_acc_part.currentItem()
        if it is None:
            return
        name = it.text(0)
        dlg = _FacetAccuracyEditDialog(
            name, self.chk_use_af.isChecked(), self)
        if dlg.exec_() == QDialog.Accepted:
            label = dlg.label()
            it.setText(1, label)
            self._region_acc[name] = label

    def _default_part_acc(self) -> None:
        it = self.tree_acc_part.currentItem()
        if it is None:
            return
        it.setText(1, "Default")
        self._region_acc[it.text(0)] = "Default"

    def _edit_tiny_ref(self) -> None:
        it = self.tree_tiny_parts.currentItem()
        if it is None:
            return
        val, ok = QInputDialog.getDouble(
            self, "Reference value",
            "Reference value for automatic removal of tiny faces (%)",
            self.sp_tiny_pct.value(), 0, 100, 3)
        if ok:
            it.setText(1, f"{val:g}")
            self.sp_tiny_pct.setValue(val)

    def _default_tiny_ref(self) -> None:
        it = self.tree_tiny_parts.currentItem()
        if it is None:
            return
        it.setText(1, f"Default ({self.sp_tiny_pct.value():g})")

    def _rerec_tiny(self) -> None:
        self._refresh_local_mdl_results(self._ctx)
        QMessageBox.information(
            self, "Re-recognize tiny faces",
            "已按当前容差重新识别本地 MDL 微小面。")

    def _reverse_match_dir(self) -> None:
        for r in range(self.tbl_match.rowCount()):
            cell = self.tbl_match.item(r, 0)
            if cell is None or cell.checkState() != Qt.Checked:
                continue
            d = self.tbl_match.item(r, 5)
            if d is not None:
                d.setText("Reverse" if d.text() == "Forward" else "Forward")

    def _change_match_tol(self) -> None:
        val, ok = QInputDialog.getDouble(
            self, "Change Tolerance",
            "Tolerance for matching face detection",
            self.sp_match_tol.value(), 0, 1e3, 6)
        if ok:
            self.sp_match_tol.setValue(val)

    def _refresh_rm_tiny(self) -> None:
        self._refresh_local_mdl_results(self._ctx)

    def _refresh_report(self) -> None:
        groups = self._ctx.get("groups_info") or {}
        lines = []
        for g, info in sorted(groups.items()):
            paths = info.get("paths") or {}
            st = (info.get("status") or {}).get("geometry") or {}
            has_mdl = bool(paths.get("part"))
            lines.append(f"[{g}] MDL={'yes' if has_mdl else 'no'}")
            for k, val in st.items():
                lines.append(f"  {k}: {val}")
        native_rep = ((self._ctx.get("session") or {})
                      .get("build_am", {}).get("native_report") or {})
        if native_rep.get("summary"):
            lines = ["Native BAM report:"] + list(native_rep["summary"]) \
                + [""] + lines
        if not lines:
            text = ("No interference or unintentional isolated/multifold "
                    "edge is found.")
        else:
            text = "\n".join(lines)
        self.txt_cause.setPlainText(text)
        self._refresh_local_mdl_results(self._ctx)

    def _refresh_local_mdl_results(self, ctx: dict) -> None:
        """从本地 MDL 回填 tiny / multi-fold / report 表（无宿主也可用）。"""
        import mdl
        from collections import defaultdict

        groups = ctx.get("groups_info") or {}
        tiny_rows: list[list] = []
        multifold: list[tuple[str, int, int, int]] = []
        mf_face_ids: list[int] = []
        match_rows: list[list] = []
        has_mdl = False
        for g, info in sorted(groups.items()):
            path = (info.get("paths") or {}).get("part")
            if not path:
                continue
            has_mdl = True
            try:
                model = mdl.parse_mdl(path, load_arrays=True)
            except Exception:  # noqa: BLE001
                continue
            tol = self.sp_rm_tol.value()
            for t in mdl.detect_tiny_faces(model, tol):
                tiny_rows.append(
                    [g, t["face_id"], f"{t['width']:.6g}", t["n_facets"]])
            for (a, b), faces in mdl.detect_multifold_edges(model).items():
                multifold.append((g, a, b, len(faces)))
                mf_face_ids.extend(faces)
            for mp in mdl.detect_matching_faces(model):
                match_rows.append(
                    [mp["group1"], mp["group2"], 0.0, 0.0,
                     mp["direction"]])

        self.tbl_match.setRowCount(len(match_rows))
        for r, row in enumerate(match_rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.tbl_match.setItem(r, 0, chk)
            for c, val in enumerate(row, start=1):
                self.tbl_match.setItem(r, c, QTableWidgetItem(str(val)))

        self.tbl_rm_tiny.setRowCount(len(tiny_rows))
        for r, row in enumerate(tiny_rows):
            for c, val in enumerate(row):
                self.tbl_rm_tiny.setItem(r, c, QTableWidgetItem(str(val)))

        self.tree_mf_edges.clear()
        by_group: dict[str, list] = defaultdict(list)
        for g, a, b, n in multifold:
            by_group[g].append((a, b, n))
        for g, edges in sorted(by_group.items()):
            root = QTreeWidgetItem([f"{g} ({len(edges)} pairs…)"])
            self.tree_mf_edges.addTopLevelItem(root)
            for a, b, n in edges:
                root.addChild(QTreeWidgetItem(
                    [f"edge {a}-{b} ({n} faces)"]))

        self.tree_mf_faces.clear()
        mf_faces = sorted(set(mf_face_ids))
        if mf_faces:
            root = QTreeWidgetItem(
                [f"Multi-fold faces ({len(mf_faces)})"])
            self.tree_mf_faces.addTopLevelItem(root)

        self.tree_tiny_faces.clear()
        tiny_by_part: dict[str, int] = defaultdict(int)
        for row in tiny_rows:
            tiny_by_part[row[0]] += 1
        for g, n in sorted(tiny_by_part.items()):
            self.tree_tiny_faces.addTopLevelItem(
                QTreeWidgetItem([g, str(n), "", ""]))

        self.lab_err_count.setText(str(len(tiny_rows)))
        self.lab_prob_level.setText(str(len(multifold)))
        self._buildable = has_mdl
        self.btn_build.setEnabled(has_mdl)
        self.tbl_report.setRowCount(0)
        if tiny_rows:
            self.tbl_report.insertRow(0)
            for c, val in enumerate(
                    ["1", str(len(tiny_rows)), "Tiny face",
                     "Face max edge < tolerance"]):
                self.tbl_report.setItem(0, c, QTableWidgetItem(val))
        if multifold:
            r = self.tbl_report.rowCount()
            self.tbl_report.insertRow(r)
            for c, val in enumerate(
                    ["2", str(len(multifold)), "Multi-fold edge",
                     "Edge shared by >2 faces"]):
                self.tbl_report.setItem(r, c, QTableWidgetItem(val))
        # 原生 BAM 报告（native_bam）优先于本地 MDL 启发式探测
        native_rep = ((ctx.get("session") or {})
                      .get("build_am", {}).get("native_report") or {})
        native_rows = list(native_rep.get("rows") or [])
        if native_rows:
            self.tbl_report.setRowCount(len(native_rows))
            for r, row in enumerate(native_rows):
                for c, key in enumerate(("level", "count", "type", "cause")):
                    self.tbl_report.setItem(
                        r, c, QTableWidgetItem(str(row.get(key, ""))))
            self.lab_err_count.setText(str(sum(
                int(x.get("count", 0)) for x in native_rows)))
            self.lab_prob_level.setText(str(max(
                [int(x.get("level", 0)) for x in native_rows], default=0)))
            self._buildable = bool(native_rep.get("buildable", True))
            self.btn_build.setEnabled(self._buildable)

    def _create_facet(self) -> None:
        if not self.apply(self._ctx):
            QMessageBox.information(
                self, "Create Facet", "No project data to write.")
            return
        sess = self._ctx.setdefault("session", {}).setdefault("build_am", {})
        sess["create_facet_requested"] = True
        QMessageBox.information(
            self, "Create Facet",
            "Parameters saved. Facet creation runs in scFLOWpre "
            "([Execute] – [Build Analysis Model]).")
        # 跳到 Repair 页（对齐向导集体执行后的报告页）
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == "repair":
                self.nav.setCurrentRow(i)
                break
        self._refresh_report()

    def _build(self) -> None:
        if not self.apply(self._ctx):
            return
        sess = self._ctx.setdefault("session", {}).setdefault("build_am", {})
        sess["build_requested"] = True
        dlg = self.window()
        if isinstance(dlg, QDialog):
            if hasattr(dlg, "_on_ok"):
                dlg._on_ok()
            else:
                dlg.accept()

    def _close(self) -> None:
        # 保存向导参数后关闭（与 Condition Wizard Finish 一致）
        dlg = self.window()
        if isinstance(dlg, QDialog):
            if hasattr(dlg, "_on_ok"):
                dlg._on_ok()
            else:
                if self.apply(self._ctx):
                    dlg.accept()
        else:
            self.apply(self._ctx)

    # ── load / apply ───────────────────────────────────────────────

    def _fill_part_trees(self, ctx: dict) -> None:
        self.tree_acc_part.clear()
        self.tree_tiny_parts.clear()
        self.tree_mf_edges.clear()
        self.tree_mf_faces.clear()
        ic_vol = _region_icon("volume")
        ic_surf = _region_icon("surface")

        names: list[str] = []
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                for p in parts.iter("part"):
                    n = (p.findtext("name") or "").strip()
                    if n:
                        names.append(n)
        if not names:
            names = sorted((ctx.get("groups_info") or {}) or [])

        sess = (ctx.get("session") or {}).get("build_am") or {}
        part_acc = dict(sess.get("part_acc") or {})
        tiny_ref = dict(sess.get("tiny_ref") or {})
        default_tiny = self.sp_tiny_pct.value()

        for n in names:
            acc = part_acc.get(n, "Default")
            it = QTreeWidgetItem([n, acc])
            it.setIcon(0, ic_vol)
            self.tree_acc_part.addTopLevelItem(it)
            ref = tiny_ref.get(n, f"Default ({default_tiny:g})")
            ti = QTreeWidgetItem([n, ref])
            ti.setIcon(0, ic_vol)
            self.tree_tiny_parts.addTopLevelItem(ti)
            self.tree_mf_edges.addTopLevelItem(QTreeWidgetItem([n]))
            self.tree_mf_faces.addTopLevelItem(QTreeWidgetItem([n]))

        # surface regions from xml
        if xml is not None:
            regions = xml.section("regions")
            if regions is not None:
                for face in regions.iter("face"):
                    for reg in face.iter("region"):
                        rn = (reg.findtext("name") or "").strip()
                        if not rn:
                            continue
                        acc = part_acc.get(rn, "Default")
                        it = QTreeWidgetItem([rn, acc])
                        it.setIcon(0, ic_surf)
                        self.tree_acc_part.addTopLevelItem(it)

        self._region_acc = part_acc
        self.lab_prev_parts.setText(
            f"{len(names)} parts are listed.")

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        sess = ctx.setdefault("session", {}).setdefault("build_am", {})
        xenv = ctx.get("xenv")

        def _b(sec, key, default=True):
            if not xenv:
                return default
            return (xenv.get(sec, key, "true" if default else "false")
                    or ("true" if default else "false")).lower() == "true"

        def _f(sec, key, default):
            if not xenv:
                return float(default)
            try:
                return float(xenv.get(sec, key, default) or default)
            except ValueError:
                return float(default)

        self.chk_proj_solids.setChecked(
            sess.get("project_solids", _b("FACET", "PROJECT_SOLIDS", True)))
        self.chk_proj_sheets.setChecked(
            sess.get("project_sheets", _b("FACET", "PROJECT_SHEETS", True)))
        use_af = sess.get("use_facetter", _b("FACET", "USE_FACETTER", True))
        self.chk_use_af.setChecked(bool(use_af))
        acc_type = str(sess.get(
            "acc_type",
            (xenv.get("FACET", "FACET_ACCURACY_SPECIFY_TYPE", "0")
             if xenv else "0") or "0"))
        _set_combo_data(self.cb_acc_type, acc_type)

        ang = float(sess.get("sb_ang", _f("FACET", "SOLID_BASE_MINIMUM_ANGLE", 10)))
        self.sp_sb_ang.setValue(ang)
        factor = float(sess.get(
            "sb_len", _f("FACET", "SOLID_BASE_LENGTH_FACTOR", 0.05)))
        den = int(round(1.0 / factor)) if factor > 0 else 20
        self.sp_sb_den.setValue(max(1, den))
        self.sp_max_edge.setValue(float(sess.get(
            "max_edge", _f("FACET", "SIMPLE_MAX_WIDTH", 5))))
        self.sp_ps_dist.setValue(float(sess.get(
            "ps_dist", _f("FACET", "SIMPLE_CHORD_TOLERANCE", 1))))
        self.sp_ps_ang.setValue(float(sess.get(
            "ps_ang", _f("FACET", "SIMPLE_MAX_ANGLE", 10))))
        abs_on = bool(sess.get(
            "absolute",
            _b("FACET", "USE_ABSOLUTE_VALUE", False)))
        self.chk_abs.setChecked(abs_on)
        self.sp_dist_abs.setValue(float(sess.get(
            "dist_abs", _f("FACET", "SIMPLE_CHORD_TOLERANCE_ABS", 0))))
        self.sp_edge_abs.setValue(float(sess.get(
            "edge_abs", _f("FACET", "SIMPLE_MAX_WIDTH_ABS", 0))))

        tiny = float(sess.get(
            "tiny_pct",
            _f("FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO", 0.05)))
        self.sp_tiny_pct.setValue(tiny * 100.0 if tiny <= 1.0 else tiny)

        self.ed_tol_edge.setText(str(sess.get("tol_multifold_edge", "1e+06")))
        self.ed_tol_face.setText(str(sess.get("tol_multifold_face", "1e+06")))
        self.sp_match_tol.setValue(float(sess.get("match_tol", 0.001)))
        self.sp_rm_tol.setValue(float(sess.get("remove_tiny_tol", 0.001)))
        self.chk_elem_use.setChecked(bool(sess.get("elem_use", False)))
        self.sp_elem_range.setValue(int(sess.get("elem_range", 5)))
        dir_i = int(sess.get("elem_dir", 0))
        self.cb_elem_dir.setCurrentIndex(0 if dir_i == 0 else 1)
        self.chk_influence.setChecked(bool(sess.get("influence_enable", False)))

        self._fill_part_trees(ctx)
        self._fill_influence(ctx)
        self._refresh_report()
        self._sync_faceter_ui()
        self._sync_elem_ui()

        page = sess.get("wizard_page") or "interference"
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == page:
                if not self.nav.item(i).isHidden():
                    self.nav.setCurrentRow(i)
                break

    def _fill_influence(self, ctx: dict) -> None:
        names: list[str] = []
        for meta in (ctx.get("regions_meta") or {}).values():
            for r in meta:
                n = r.get("name") if isinstance(r, dict) else None
                if n and n not in names:
                    names.append(n)
        targets = set((self._ctx.get("session") or {})
                      .get("build_am", {}).get("influence_targets", []))
        self.tbl_influence.setRowCount(len(names))
        for i, n in enumerate(names):
            self.tbl_influence.setItem(i, 0, QTableWidgetItem(n))
            self.tbl_influence.setItem(
                i, 1,
                QTableWidgetItem("Target" if n in targets else ""))

    def apply(self, ctx: dict) -> bool:
        self._ctx = ctx
        xenv = ctx.get("xenv")
        factor = 1.0 / max(1, self.sp_sb_den.value())
        tiny_ratio = self.sp_tiny_pct.value() / 100.0

        # part/region accuracy snapshot
        part_acc = {}
        for i in range(self.tree_acc_part.topLevelItemCount()):
            it = self.tree_acc_part.topLevelItem(i)
            part_acc[it.text(0)] = it.text(1)
        tiny_ref = {}
        for i in range(self.tree_tiny_parts.topLevelItemCount()):
            it = self.tree_tiny_parts.topLevelItem(i)
            tiny_ref[it.text(0)] = it.text(1)

        sess = {
            "wizard_page": self._current_key(),
            "project_solids": self.chk_proj_solids.isChecked(),
            "project_sheets": self.chk_proj_sheets.isChecked(),
            "use_facetter": self.chk_use_af.isChecked(),
            "acc_type": self.cb_acc_type.currentData(),
            "sb_ang": self.sp_sb_ang.value(),
            "sb_len": factor,
            "max_edge": self.sp_max_edge.value(),
            "ps_dist": self.sp_ps_dist.value(),
            "ps_ang": self.sp_ps_ang.value(),
            "absolute": self.chk_abs.isChecked(),
            "dist_abs": self.sp_dist_abs.value(),
            "edge_abs": self.sp_edge_abs.value(),
            "tiny_pct": self.sp_tiny_pct.value(),
            "tol_multifold_edge": self.ed_tol_edge.text().strip(),
            "tol_multifold_face": self.ed_tol_face.text().strip(),
            "match_tol": self.sp_match_tol.value(),
            "remove_tiny_tol": self.sp_rm_tol.value(),
            "elem_use": self.chk_elem_use.isChecked(),
            "elem_range": self.sp_elem_range.value(),
            "elem_dir": self.cb_elem_dir.currentIndex(),
            "influence_enable": self.chk_influence.isChecked(),
            "part_acc": part_acc,
            "tiny_ref": tiny_ref,
            "report": True,
        }
        influence_targets = []
        for i in range(self.tbl_influence.rowCount()):
            it0 = self.tbl_influence.item(i, 0)
            it1 = self.tbl_influence.item(i, 1)
            if it0 is not None and it1 is not None and it1.text().strip():
                influence_targets.append(it0.text())
        sess["influence_targets"] = influence_targets
        prev = ctx.setdefault("session", {}).get("build_am") or {}
        for k in ("create_facet_requested", "build_requested",
                  "apply_face_matching", "remove_tiny", "repair",
                  "native_report", "vbs_steps"):
            if k in prev:
                sess[k] = prev[k]
        ctx.setdefault("session", {})["build_am"] = sess

        if not xenv:
            return True

        pphxml.set_xenv_value(
            xenv, "FACET", "PROJECT_SOLIDS",
            "true" if self.chk_proj_solids.isChecked() else "false")
        pphxml.set_xenv_value(
            xenv, "FACET", "PROJECT_SHEETS",
            "true" if self.chk_proj_sheets.isChecked() else "false")
        pphxml.set_xenv_value(
            xenv, "FACET", "USE_FACETTER",
            "true" if self.chk_use_af.isChecked() else "false")
        pphxml.set_xenv_value(
            xenv, "FACET", "FACET_ACCURACY_SPECIFY_TYPE",
            self.cb_acc_type.currentData() or "0")
        pphxml.set_xenv_value(
            xenv, "FACET", "USE_ABSOLUTE_VALUE",
            "true" if self.chk_abs.isChecked() else "false")
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_MINIMUM_ANGLE",
            _fmt_float(self.sp_sb_ang.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_LENGTH_FACTOR",
            _fmt_float(factor))
        pphxml.set_xenv_value(
            xenv, "FACET", "SIMPLE_MAX_WIDTH",
            _fmt_float(self.sp_max_edge.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SIMPLE_CHORD_TOLERANCE",
            _fmt_float(self.sp_ps_dist.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SIMPLE_MAX_ANGLE",
            _fmt_float(self.sp_ps_ang.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SIMPLE_CHORD_TOLERANCE_ABS",
            _fmt_float(self.sp_dist_abs.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SIMPLE_MAX_WIDTH_ABS",
            _fmt_float(self.sp_edge_abs.value()))
        pphxml.set_xenv_value(
            xenv, "FACET", "SOLID_BASE_TINY_FACE_WIDTH_RATIO",
            _fmt_float(tiny_ratio))
        # Wizard 路径：MDL_METHOD = Analysis Model Wizard
        pphxml.set_xenv_value(xenv, "FACET", "MDL_METHOD", "1")
        ctx["xenv_dirty"] = True
        return True


class _RefineRangeDiagram(QWidget):
    """Other Settings 页的细化过渡示意（粉格）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._range = 3
        self.setMinimumHeight(120)
        self.setMinimumWidth(280)

    def set_range(self, value: int) -> None:
        self._range = max(1, int(value))
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(250, 250, 250))
        rng = self._range
        # 从细到粗：左细右粗，跨 rng 级
        levels = list(range(rng + 1))  # 0..rng → cell size 2^i
        margin, top = 24, 28
        w = self.width() - 2 * margin
        h = self.height() - top - 16
        x = margin
        fine_lv, coarse_lv = 2, 2 + rng
        p.setPen(QPen(QColor(80, 80, 80)))
        p.drawText(margin, 16, str(fine_lv))
        p.drawText(self.width() - margin - 12, 16, str(coarse_lv))
        fill = QColor(255, 160, 200)
        edge = QColor(200, 40, 140)
        for i, lv in enumerate(levels):
            cell = max(6, int(8 * (2 ** (lv * 0.35))))
            seg_w = w / len(levels)
            cols = max(1, int(seg_w / cell))
            rows = max(1, int(h / cell))
            for r in range(rows):
                for c in range(cols):
                    xx = x + c * cell
                    yy = top + r * cell
                    p.fillRect(xx, yy, cell - 1, cell - 1, fill)
                    p.setPen(QPen(edge, 1))
                    p.drawRect(xx, yy, cell - 1, cell - 1)
            x += seg_w
        p.end()


class OctreeDetailDialog(QDialog):
    """scFLOW [Octree Parameter] – Detail：左侧导航 + 五页设置。"""

    PAGES = [
        "Basic Settings",
        "Size Settings to Region",
        "Angle Settings to Region",
        "Proximity Settings to Region",
        "Other Settings",
    ]

    def __init__(self, data: dict, ctx: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Octree Parameter")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(780, 480)
        self._data = dict(data)
        self._ctx = ctx
        self._dirty_param = False

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.nav = QListWidget()
        self.nav.addItems(self.PAGES)
        self.nav.setFixedWidth(200)
        self.nav.setCurrentRow(0)
        root.addWidget(self.nav)

        right = QVBoxLayout()
        self.stack = QStackedWidget()
        self._build_basic()
        self._build_size()
        self._build_angle()
        self._build_proximity()
        self._build_other()
        right.addWidget(self.stack, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_create = QPushButton("Create")
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        btns.addWidget(self.btn_create)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        right.addLayout(btns)
        root.addLayout(right, 1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_create.clicked.connect(self._on_create)
        self._load_data()
        self._sync_enables()

    # ── pages ─────────────────────────────────────────────────────
    def _build_basic(self) -> None:
        page = QWidget()
        lay = QHBoxLayout(page)
        # Octant Size
        oct_box = QGroupBox("Octant Size")
        ov = QVBoxLayout(oct_box)
        self.rb_len = QRadioButton("Input by length")
        self.rb_param = QRadioButton("Input by parameters")
        self.rb_len.setChecked(True)
        ov.addWidget(self.rb_len)
        self.chk_max = QCheckBox("Restrict maximum octant size")
        self.sp_min_oct = _spin_f(8, 0, 1e6, 0.001)
        self.sp_max_oct = _spin_f(8, 0, 1e6, 0.001)
        form_len = QFormLayout()
        form_len.setContentsMargins(20, 0, 0, 0)
        form_len.addRow(self.chk_max)
        form_len.addRow("Minimum octant size", self.sp_min_oct)
        form_len.addRow("Maximum octant size", self.sp_max_oct)
        ov.addLayout(form_len)
        ov.addWidget(self.rb_param)
        self.chk_min_level = QCheckBox("Restrict minimum refinement level")
        self.sp_root_ratio = _spin_f(4, 1.0, 10.0, 1.6)
        self.sp_max_level = QSpinBox(); self.sp_max_level.setRange(1, 30)
        self.sp_max_level.setValue(4)
        self.sp_min_level = QSpinBox(); self.sp_min_level.setRange(0, 30)
        self.sp_min_level.setValue(4)
        form_p = QFormLayout()
        form_p.setContentsMargins(20, 0, 0, 0)
        form_p.addRow(self.chk_min_level)
        form_p.addRow("Size ratio of root octant", self.sp_root_ratio)
        form_p.addRow("Maximum refinement level", self.sp_max_level)
        form_p.addRow("Minimum refinement level", self.sp_min_level)
        ov.addLayout(form_p)
        ov.addStretch(1)
        lay.addWidget(oct_box, 1)

        # Model Size
        mdl_box = QGroupBox("Model Size")
        mg = QGridLayout(mdl_box)
        for i, axis in enumerate("XYZ"):
            mg.addWidget(QLabel(axis), 0, i + 1, Qt.AlignCenter)
        self.ed_min = [_readonly_line("0") for _ in range(3)]
        self.ed_max = [_readonly_line("0.01") for _ in range(3)]
        self.ed_size = [_readonly_line("0.01") for _ in range(3)]
        mg.addWidget(QLabel("Min"), 1, 0)
        mg.addWidget(QLabel("Max"), 2, 0)
        mg.addWidget(QLabel("Size"), 3, 0)
        for i in range(3):
            mg.addWidget(self.ed_min[i], 1, i + 1)
            mg.addWidget(self.ed_max[i], 2, i + 1)
            mg.addWidget(self.ed_size[i], 3, i + 1)
        self.chk_center = QCheckBox("Specify center of octree")
        self.chk_center.setChecked(True)
        mg.addWidget(self.chk_center, 4, 0, 1, 4)
        self.sp_cx = _spin_f(8, -1e9, 1e9, 0.005)
        self.sp_cy = _spin_f(8, -1e9, 1e9, 0.005)
        self.sp_cz = _spin_f(8, -1e9, 1e9, 0.005)
        mg.addWidget(self.sp_cx, 5, 1)
        mg.addWidget(self.sp_cy, 5, 2)
        mg.addWidget(self.sp_cz, 5, 3)
        mg.setRowStretch(6, 1)
        lay.addWidget(mdl_box, 1)

        self.rb_len.toggled.connect(self._sync_enables)
        self.rb_param.toggled.connect(self._sync_enables)
        self.chk_max.toggled.connect(self._sync_enables)
        self.chk_min_level.toggled.connect(self._sync_enables)
        self.chk_center.toggled.connect(self._sync_enables)
        self.stack.addWidget(page)

    def _build_size(self) -> None:
        page = QWidget()
        lay = QHBoxLayout(page)
        left = QVBoxLayout()
        left.addWidget(QLabel("Size for regions"))
        self.tree_size = QTreeWidget()
        self.tree_size.setHeaderLabels(["Region", "Size", "Range"])
        self.tree_size.setRootIsDecorated(False)
        self.tree_size.setColumnWidth(0, 200)
        left.addWidget(self.tree_size, 1)
        self.chk_rs_eval = QCheckBox(
            "Evaluate the influence range using the size from [Basic Settings]")
        left.addWidget(self.chk_rs_eval)
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        param = QGroupBox("Parameter")
        pf = QFormLayout(param)
        self.sp_rs_size = _spin_f(8, 0, 1e6, 0)
        self.sp_rs_range = _spin_f(4, 0, 1e6, 0)
        pf.addRow("Size", self.sp_rs_size)
        pf.addRow("Influence range", self.sp_rs_range)
        right.addWidget(param)
        self.btn_rs_apply = QPushButton("<< Apply")
        self.btn_rs_cancel = QPushButton(">> Cancel")
        self.btn_rs_confirm = QPushButton("Confirm Size")
        right.addWidget(self.btn_rs_apply)
        right.addWidget(self.btn_rs_cancel)
        right.addWidget(self.btn_rs_confirm)
        right.addStretch(1)
        lay.addLayout(right)
        self.tree_size.itemSelectionChanged.connect(
            lambda: self._select_region_row(self.tree_size, "size"))
        self.btn_rs_apply.clicked.connect(
            lambda: self._apply_region_row(self.tree_size, "size"))
        self.btn_rs_cancel.clicked.connect(
            lambda: self._select_region_row(self.tree_size, "size"))
        self.btn_rs_confirm.clicked.connect(self._confirm_size)
        self.stack.addWidget(page)

    def _build_angle(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Angle precision for region"))
        body = QHBoxLayout()
        self.tree_angle = QTreeWidget()
        self.tree_angle.setHeaderLabels(
            ["Region", "Angle", "Range", "Minimum size"])
        self.tree_angle.setRootIsDecorated(False)
        self.tree_angle.setColumnWidth(0, 180)
        body.addWidget(self.tree_angle, 1)
        right = QVBoxLayout()
        param = QGroupBox("Parameter")
        pf = QFormLayout(param)
        self.sp_ra_angle = _spin_f(3, 0, 180, 0)
        self.sp_ra_range = _spin_f(4, 0, 1e6, 0)
        self.chk_ra_restrict = QCheckBox("Restrict minimum size")
        self.sp_ra_min = _spin_f(8, 0, 1e6, 0)
        pf.addRow("Angle [deg]", self.sp_ra_angle)
        pf.addRow("Influence range", self.sp_ra_range)
        pf.addRow(self.chk_ra_restrict)
        pf.addRow("Minimum size", self.sp_ra_min)
        right.addWidget(param)
        self.btn_ra_apply = QPushButton("<< Apply")
        self.btn_ra_cancel = QPushButton(">> Cancel")
        right.addWidget(self.btn_ra_apply)
        right.addWidget(self.btn_ra_cancel)
        right.addStretch(1)
        body.addLayout(right)
        lay.addLayout(body, 1)
        help_l = QLabel(
            "Subdivide the octant to a size that keeps the curvature of the "
            "original shape within a specified angular error.")
        help_l.setWordWrap(True)
        help_l.setStyleSheet("color:#444; font-size:11px;")
        lay.addWidget(help_l)
        row = QHBoxLayout()
        self.chk_ra_all = QCheckBox("Set minimum size limits for all regions")
        self.sp_ra_all_min = _spin_f(8, 0, 1e6, 0)
        row.addWidget(self.chk_ra_all)
        row.addWidget(self.sp_ra_all_min)
        row.addStretch(1)
        lay.addLayout(row)
        self.chk_ra_restrict.toggled.connect(self._sync_enables)
        self.chk_ra_all.toggled.connect(self._sync_enables)
        self.tree_angle.itemSelectionChanged.connect(
            lambda: self._select_region_row(self.tree_angle, "angle"))
        self.btn_ra_apply.clicked.connect(
            lambda: self._apply_region_row(self.tree_angle, "angle"))
        self.btn_ra_cancel.clicked.connect(
            lambda: self._select_region_row(self.tree_angle, "angle"))
        self.stack.addWidget(page)

    def _build_proximity(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Proximity for regions"))
        body = QHBoxLayout()
        self.tree_prox = QTreeWidget()
        self.tree_prox.setHeaderLabels(
            ["Region", "Gap distance to ignore", "Octant Count", "Minimum size"])
        self.tree_prox.setRootIsDecorated(False)
        self.tree_prox.setColumnWidth(0, 160)
        body.addWidget(self.tree_prox, 1)
        right = QVBoxLayout()
        param = QGroupBox("Parameter")
        pf = QFormLayout(param)
        self.sp_rp_gap = _spin_f(8, 0, 1e6, 0.001)
        self.sp_rp_count = QSpinBox(); self.sp_rp_count.setRange(1, 1_000_000)
        self.sp_rp_count.setValue(1)
        self.sp_rp_min = _spin_f(8, 0, 1e6, 0.001)
        pf.addRow("Gap distance to ignore", self.sp_rp_gap)
        pf.addRow("Octant count", self.sp_rp_count)
        pf.addRow("Minimum size", self.sp_rp_min)
        right.addWidget(param)
        self.btn_rp_apply = QPushButton("<< Apply")
        self.btn_rp_cancel = QPushButton(">> Cancel")
        right.addWidget(self.btn_rp_apply)
        right.addWidget(self.btn_rp_cancel)
        right.addStretch(1)
        body.addLayout(right)
        lay.addLayout(body, 1)
        help_l = QLabel(
            "Divide octants until the gap near the region is filled with the "
            "specified number of octants. Gaps narrower than the "
            "[Gap distance to ignore] are ignored.")
        help_l.setWordWrap(True)
        help_l.setStyleSheet("color:#444; font-size:11px;")
        lay.addWidget(help_l)
        self.tree_prox.itemSelectionChanged.connect(
            lambda: self._select_region_row(self.tree_prox, "proximity"))
        self.btn_rp_apply.clicked.connect(
            lambda: self._apply_region_row(self.tree_prox, "proximity"))
        self.btn_rp_cancel.clicked.connect(
            lambda: self._select_region_row(self.tree_prox, "proximity"))
        self.stack.addWidget(page)

    def _build_other(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.chk_limit = QCheckBox(
            "Limit change in refinement level to no more than two levels "
            "within the specified range.")
        self.chk_limit.setChecked(True)
        lay.addWidget(self.chk_limit)
        row = QHBoxLayout()
        row.addWidget(QLabel("Range"))
        self.sp_other_range = QSpinBox()
        self.sp_other_range.setRange(1, 20)
        self.sp_other_range.setValue(3)
        row.addWidget(self.sp_other_range)
        row.addStretch(1)
        lay.addLayout(row)
        self.sl_other = QSlider(Qt.Horizontal)
        self.sl_other.setRange(1, 20)
        self.sl_other.setValue(3)
        lay.addWidget(self.sl_other)
        self.diagram = _RefineRangeDiagram()
        lay.addWidget(self.diagram, 1)
        self.sp_other_range.valueChanged.connect(self.sl_other.setValue)
        self.sl_other.valueChanged.connect(self.sp_other_range.setValue)
        self.sp_other_range.valueChanged.connect(self.diagram.set_range)
        self.chk_limit.toggled.connect(self._sync_enables)
        self.stack.addWidget(page)

    # ── data / enable ─────────────────────────────────────────────
    def _load_data(self) -> None:
        d = self._data
        self.rb_len.setChecked(d.get("input_by", "length") != "param")
        self.rb_param.setChecked(d.get("input_by") == "param")
        self.sp_min_oct.setValue(float(d.get("min_oct_size", 0.001)))
        self.sp_max_oct.setValue(float(d.get("max_oct_size", 0.001)))
        self.chk_max.setChecked(bool(d.get("restrict_max", False)))
        self.sp_root_ratio.setValue(float(d.get("root_ratio", 1.6)))
        self.sp_max_level.setValue(int(d.get("max_level", 4)))
        self.sp_min_level.setValue(int(d.get("min_level", 4)))
        self.chk_min_level.setChecked(bool(d.get("restrict_min_level", False)))
        self.chk_center.setChecked(bool(d.get("specify_center", True)))
        lo, hi = _model_bounds_from_ctx(self._ctx)
        size = [hi[i] - lo[i] for i in range(3)]
        center = [(lo[i] + hi[i]) / 2 for i in range(3)]
        for i in range(3):
            self.ed_min[i].setText(f"{lo[i]:.8g}")
            self.ed_max[i].setText(f"{hi[i]:.8g}")
            self.ed_size[i].setText(f"{size[i]:.8g}")
        self.sp_cx.setValue(float(d.get("center_x", center[0])))
        self.sp_cy.setValue(float(d.get("center_y", center[1])))
        self.sp_cz.setValue(float(d.get("center_z", center[2])))

        self.chk_rs_eval.setChecked(bool(d.get("region_size_eval", False)))
        self.chk_ra_all.setChecked(bool(d.get("region_angle_all_min", False)))
        self.sp_ra_all_min.setValue(float(d.get("region_angle_all_min_size", 0)))
        self.chk_limit.setChecked(bool(d.get("limit_refine", True)))
        self.sp_other_range.setValue(int(d.get("refine_range", 3)))
        self.diagram.set_range(self.sp_other_range.value())

        # 预填 Size for regions：空项用 Minimum octant size（对齐宿主默认）
        self._prefill_region_sizes()
        self._fill_region_trees()

    def _prefill_region_sizes(self) -> None:
        """未设置的区域 Size 预填为 min_oct_size / refine_range。"""
        d = self._data
        default_size = float(d.get("min_oct_size", 0.001) or 0.001)
        default_range = float(d.get("refine_range", 0) or 0)
        rs = d.setdefault("region_size", {})
        for r in _collect_octree_regions(self._ctx):
            name = r["name"]
            cur = rs.get(name)
            if not isinstance(cur, dict):
                rs[name] = {"size": default_size, "range": default_range}
                continue
            size = cur.get("size")
            if size is None or size == "" or float(size or 0) == 0:
                cur["size"] = default_size
            if cur.get("range") is None or cur.get("range") == "":
                cur["range"] = default_range
            rs[name] = cur

    def _fill_region_trees(self) -> None:
        regions = _collect_octree_regions(self._ctx)
        rs = self._data.setdefault("region_size", {})
        ra = self._data.setdefault("region_angle", {})
        rp = self._data.setdefault("region_proximity", {})
        self.tree_size.clear()
        self.tree_angle.clear()
        self.tree_prox.clear()
        for r in regions:
            name, kind = r["name"], r["kind"]
            icon = _region_icon(kind)
            # Size
            sv = rs.get(name, {})
            it = QTreeWidgetItem([
                name,
                _fmt_disp(sv.get("size")),
                _fmt_disp(sv.get("range")),
            ])
            it.setIcon(0, icon)
            it.setData(0, Qt.UserRole, name)
            self.tree_size.addTopLevelItem(it)
            # Angle — 仅面区域（手册/界面以面域为主）
            if kind == "surface":
                av = ra.get(name, {})
                it2 = QTreeWidgetItem([
                    name,
                    _fmt_disp(av.get("angle")),
                    _fmt_disp(av.get("range")),
                    _fmt_disp(av.get("min_size")),
                ])
                it2.setIcon(0, icon)
                it2.setData(0, Qt.UserRole, name)
                self.tree_angle.addTopLevelItem(it2)
                pv = rp.get(name, {})
                it3 = QTreeWidgetItem([
                    name,
                    _fmt_disp(pv.get("gap")),
                    _fmt_disp(pv.get("count")),
                    _fmt_disp(pv.get("min_size")),
                ])
                it3.setIcon(0, icon)
                it3.setData(0, Qt.UserRole, name)
                self.tree_prox.addTopLevelItem(it3)

    def _sync_enables(self) -> None:
        by_len = self.rb_len.isChecked()
        for w in (self.chk_max, self.sp_min_oct):
            w.setEnabled(by_len)
        self.sp_max_oct.setEnabled(by_len and self.chk_max.isChecked())
        for w in (self.chk_min_level, self.sp_root_ratio, self.sp_max_level):
            w.setEnabled(not by_len)
        self.sp_min_level.setEnabled(
            (not by_len) and self.chk_min_level.isChecked())
        for w in (self.sp_cx, self.sp_cy, self.sp_cz):
            w.setEnabled(self.chk_center.isChecked())
        self.sp_ra_min.setEnabled(self.chk_ra_restrict.isChecked())
        self.sp_ra_all_min.setEnabled(self.chk_ra_all.isChecked())
        lim = self.chk_limit.isChecked()
        self.sp_other_range.setEnabled(lim)
        self.sl_other.setEnabled(lim)

    def _select_region_row(self, tree: QTreeWidget, kind: str) -> None:
        items = tree.selectedItems()
        if not items:
            return
        name = items[0].data(0, Qt.UserRole)
        if kind == "size":
            v = self._data.get("region_size", {}).get(name, {})
            self.sp_rs_size.setValue(float(v.get("size", 0) or 0))
            self.sp_rs_range.setValue(float(v.get("range", 0) or 0))
        elif kind == "angle":
            v = self._data.get("region_angle", {}).get(name, {})
            self.sp_ra_angle.setValue(float(v.get("angle", 0) or 0))
            self.sp_ra_range.setValue(float(v.get("range", 0) or 0))
            self.sp_ra_min.setValue(float(v.get("min_size", 0) or 0))
            self.chk_ra_restrict.setChecked(bool(v.get("restrict", False)))
            self._sync_enables()
        else:
            v = self._data.get("region_proximity", {}).get(name, {})
            self.sp_rp_gap.setValue(float(v.get("gap", 0.001) or 0.001))
            self.sp_rp_count.setValue(int(v.get("count", 1) or 1))
            self.sp_rp_min.setValue(float(v.get("min_size", 0.001) or 0.001))

    def _apply_region_row(self, tree: QTreeWidget, kind: str) -> None:
        items = tree.selectedItems()
        if not items:
            QMessageBox.information(self, "Octree Parameter",
                                    "Select a region first.")
            return
        name = items[0].data(0, Qt.UserRole)
        it = items[0]
        if kind == "size":
            rec = {"size": self.sp_rs_size.value(),
                   "range": self.sp_rs_range.value()}
            self._data.setdefault("region_size", {})[name] = rec
            it.setText(1, _fmt_disp(rec["size"]))
            it.setText(2, _fmt_disp(rec["range"]))
        elif kind == "angle":
            rec = {
                "angle": self.sp_ra_angle.value(),
                "range": self.sp_ra_range.value(),
                "restrict": self.chk_ra_restrict.isChecked(),
                "min_size": self.sp_ra_min.value(),
            }
            self._data.setdefault("region_angle", {})[name] = rec
            it.setText(1, _fmt_disp(rec["angle"]))
            it.setText(2, _fmt_disp(rec["range"]))
            it.setText(3, _fmt_disp(rec["min_size"]))
        else:
            rec = {
                "gap": self.sp_rp_gap.value(),
                "count": self.sp_rp_count.value(),
                "min_size": self.sp_rp_min.value(),
            }
            self._data.setdefault("region_proximity", {})[name] = rec
            it.setText(1, _fmt_disp(rec["gap"]))
            it.setText(2, _fmt_disp(rec["count"]))
            it.setText(3, _fmt_disp(rec["min_size"]))

    def _confirm_size(self) -> None:
        QMessageBox.information(
            self, "Confirm Size",
            "Confirm Size 会在 Draw Window 预览区域八叉尺寸。\n"
            "本查看器仅保存参数；实际预览/生成请在 scFLOWpre 中执行。")

    def _collect(self) -> dict:
        d = dict(self._data)
        d.update({
            "input_by": "param" if self.rb_param.isChecked() else "length",
            "min_oct_size": self.sp_min_oct.value(),
            "max_oct_size": self.sp_max_oct.value(),
            "restrict_max": self.chk_max.isChecked(),
            "root_ratio": self.sp_root_ratio.value(),
            "max_level": self.sp_max_level.value(),
            "min_level": self.sp_min_level.value(),
            "restrict_min_level": self.chk_min_level.isChecked(),
            "specify_center": self.chk_center.isChecked(),
            "center_x": self.sp_cx.value(),
            "center_y": self.sp_cy.value(),
            "center_z": self.sp_cz.value(),
            "region_size_eval": self.chk_rs_eval.isChecked(),
            "region_angle_all_min": self.chk_ra_all.isChecked(),
            "region_angle_all_min_size": self.sp_ra_all_min.value(),
            "limit_refine": self.chk_limit.isChecked(),
            "refine_range": self.sp_other_range.value(),
        })
        return d

    def result_data(self) -> dict:
        return self._collect()

    def _on_ok(self) -> None:
        self._data = self._collect()
        self.accept()

    def _on_create(self) -> None:
        self._data = self._collect()
        self._data["create_requested"] = True
        QMessageBox.information(
            self, "Create Octree",
            "已记录 Create 请求。本查看器不调用网格器；\n"
            "请在 Execute 中勾选 Generate Octree，或于 scFLOWpre 中 Create。")
        self.accept()


def _readonly_line(text: str) -> QLineEdit:
    ed = QLineEdit(text)
    ed.setReadOnly(True)
    ed.setStyleSheet("background:#f0f0f0;")
    return ed


def _fmt_disp(v) -> str:
    if v is None or v == "" or v == 0 or v == 0.0:
        return ""
    try:
        f = float(v)
        if abs(f - int(f)) < 1e-12:
            return str(int(f))
        return f"{f:.8g}"
    except (TypeError, ValueError):
        return str(v)


class OctreeParamBody(_Body):
    """外层 [Octree Parameter]：密度三选一 + Detail…（对齐 scFLOWpre）。"""

    title = "Octree Parameter"
    min_size = (420, 200)
    dialog_buttons = (
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._detail: dict = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 6)

        self.rb_target = QRadioButton("Target number of elements")
        self.rb_min = QRadioButton("Minimum size")
        self.rb_oct = QRadioButton("Octree parameter")
        self.rb_oct.setChecked(True)
        self.sp_target = QSpinBox()
        self.sp_target.setRange(1, 2_000_000_000)
        self.sp_target.setValue(100_000)
        self.sp_min = _spin_f(8, 0, 1e6, 0.00021875)
        self.btn_detail = QPushButton("Detail...")
        self.btn_detail.setFixedWidth(80)

        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        g.addWidget(self.rb_target, 0, 0)
        g.addWidget(self.sp_target, 0, 1)
        g.addWidget(self.rb_min, 1, 0)
        row_min = QHBoxLayout()
        row_min.addWidget(self.sp_min)
        row_min.addWidget(QLabel("m"))
        row_min.addStretch(1)
        g.addLayout(row_min, 1, 1)
        g.addWidget(self.rb_oct, 2, 0)
        g.addWidget(self.btn_detail, 2, 1, Qt.AlignLeft)
        v.addLayout(g)

        row_c = QHBoxLayout()
        row_c.addStretch(1)
        self.btn_create = QPushButton("Create Octree")
        row_c.addWidget(self.btn_create)
        v.addLayout(row_c)
        v.addStretch(1)

        for rb in (self.rb_target, self.rb_min, self.rb_oct):
            rb.toggled.connect(self._sync_mode)
        self.btn_detail.clicked.connect(self._open_detail)
        self.btn_create.clicked.connect(self._create_octree)

    def _sync_mode(self) -> None:
        self.sp_target.setEnabled(self.rb_target.isChecked())
        self.sp_min.setEnabled(self.rb_min.isChecked())
        self.btn_detail.setEnabled(self.rb_oct.isChecked())

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        sess = ctx.setdefault("session", {}).setdefault("octree_param", {})
        self._detail = dict(sess.get("detail") or {})
        # 兼容旧会话扁平字段
        if not self._detail:
            for k in (
                "input_by", "min_oct_size", "max_oct_size", "restrict_max",
                "root_ratio", "max_level", "min_level", "restrict_min_level",
                "specify_center", "center_x", "center_y", "center_z",
                "region_size", "region_angle", "region_proximity",
                "region_size_eval", "region_angle_all_min",
            ):
                if k in sess:
                    self._detail[k] = sess[k]
        mode = sess.get("mode", "octant")
        self.rb_target.setChecked(mode == "target")
        self.rb_min.setChecked(mode == "min")
        self.rb_oct.setChecked(mode == "octant")
        if "target" in sess:
            self.sp_target.setValue(int(sess["target"]))
        if "min_size" in sess:
            self.sp_min.setValue(float(sess["min_size"]))
        # xenv：OCT_LENGTH_PARAM_* 反映密度模式
        xenv = ctx.get("xenv")
        if xenv and "min_oct_size" not in self._detail:
            try:
                # FACET_LENGTH_FACTOR 常与最小尺度相关，作初值参考
                fl = float(xenv.get("OCT_MESH", "FACET_LENGTH_FACTOR", "0") or 0)
                if fl > 0 and "min_oct_size" not in self._detail:
                    pass
            except ValueError:
                pass
        self._sync_mode()

    def _open_detail(self) -> None:
        dlg = OctreeDetailDialog(self._detail, self._ctx, self)
        if dlg.exec_() == QDialog.Accepted:
            self._detail = dlg.result_data()
            # Detail OK 立即写入 session，避免只关 Detail、未再点外层 OK
            # 时 Execute 脚本仍看不到区域 Size
            create = self._detail.pop("create_requested", False)
            sess = self._ctx.setdefault("session", {}).setdefault(
                "octree_param", {})
            sess["detail"] = dict(self._detail)
            for k, v in self._detail.items():
                sess[k] = v
            if create:
                self._create_octree()

    def _create_octree(self) -> None:
        sess = self._ctx.setdefault("session", {}).setdefault("octree_param", {})
        sess["create_requested"] = True
        QMessageBox.information(
            self, "Create Octree",
            "已记录 Create Octree。\n"
            "本查看器不执行网格器；请在 [Execute] 勾选 "
            "Generate Octree for Meshing，或于 scFLOWpre 中创建。")

    def apply(self, ctx: dict) -> bool:
        mode = ("target" if self.rb_target.isChecked()
                else "min" if self.rb_min.isChecked() else "octant")
        sess = ctx.setdefault("session", {}).setdefault("octree_param", {})
        sess["mode"] = mode
        sess["target"] = self.sp_target.value()
        sess["min_size"] = self.sp_min.value()
        sess["detail"] = dict(self._detail)
        # 扁平副本便于旧代码 / VBS 管线读取
        sess.update({k: self._detail[k] for k in self._detail
                     if k != "create_requested"})

        xenv = ctx.get("xenv")
        if not xenv:
            return True
        # 密度模式 → OCT_LENGTH_PARAM_*（录制/管线使用）
        pphxml.set_xenv_value(xenv, "FACET", "OCT_LENGTH_PARAM_FLAG", "true")
        # type: 经验映射 0=target 1=min 5=octant-detail（与样例默认 5 对齐）
        type_map = {"target": "0", "min": "1", "octant": "5"}
        pphxml.set_xenv_value(xenv, "FACET", "OCT_LENGTH_PARAM_TYPE",
                              type_map.get(mode, "5"))
        # 最小八叉尺寸写入 facet length 相关参考（Detail 按长度输入时）
        d = self._detail
        if d.get("input_by", "length") == "length" and d.get("min_oct_size"):
            # 不覆盖用户已有 FACET_LENGTH_FACTOR；仅在会话记录尺度
            pass
        if d.get("limit_refine") is not None:
            # Other Settings 无直接 xenv 键，保留在 session
            pass
        ctx["xenv_dirty"] = True
        return True


_MESH_OTHER_ITEMS = [
    "Surface Mesh",
    "Timing of Prism Layer Insertion",
    "Detailed Settings of Prism Layer",
    "Smoothing After Prism Layer",
    "Volume Mesh",
    "Element Size",
    "Smoothing After Volume Meshing",
    "Generation of All Mesh by Sweep",
    "Mesh Adaptation Analysis",
]

_MESH_SUB_SPECS: dict[str, list[tuple]] = {
    "Surface Mesh": [
        ("chord", "Chord tolerance", "float", 1),
        ("angle", "Max angle", "float", 5),
        ("width", "Max width", "float", 5),
    ],
    "Timing of Prism Layer Insertion": [
        ("timing", "Timing", "combo",
         ["After volume meshing", "Before volume meshing",
          "After polyhedral conversion"]),
    ],
    "Detailed Settings of Prism Layer": [
        ("thickness", "Thickness coefficient", "float", 0.2),
        ("layers", "Number of layers", "int", 2),
    ],
    "Smoothing After Prism Layer": [
        ("iterations", "Number of iterations", "int", 5),
    ],
    "Volume Mesh": [
        ("hexa", "Create spatial hexahedral mesh", "bool", True),
        ("hexa_prev", "Use previous(V2020) method", "bool", False),
        ("thin", "Generate sweep elements at thin space", "bool", False),
        ("thin_layers", "Number of layers", "int", 5),
        ("thin_ratio", "Ratio of thin space to octant size", "float", 0.5),
    ],
    "Element Size": [
        ("enable", "Enable", "bool", False),
        ("range", "Range of effect", "float", 1.0),
    ],
    "Smoothing After Volume Meshing": [
        ("iterations", "Number of iterations", "int", 5),
    ],
    "Generation of All Mesh by Sweep": [
        ("enable", "Enable", "bool", False),
    ],
    "Mesh Adaptation Analysis": [
        ("enable", "Enable", "bool", False),
    ],
}

# Detailed setting 下「稳定性 / 形状」预设（写入 other 子项默认值）
_MESH_PRESET_STABILITY: dict[str, dict] = {
    "Timing of Prism Layer Insertion": {
        "timing": "After volume meshing"},
    "Volume Mesh": {"hexa": "true", "thin": "false"},
    "Smoothing After Prism Layer": {"iterations": 5},
    "Smoothing After Volume Meshing": {"iterations": 5},
}
_MESH_PRESET_SHAPE: dict[str, dict] = {
    "Timing of Prism Layer Insertion": {
        "timing": "Before volume meshing"},
    "Volume Mesh": {"hexa": "true", "thin": "true", "thin_layers": 5,
                    "thin_ratio": 0.5},
    "Smoothing After Prism Layer": {"iterations": 3},
    "Smoothing After Volume Meshing": {"iterations": 3},
}


class _MeshSubDialog(QDialog):
    """Detailed setting 子项参数对话框。"""

    def __init__(self, title: str, spec: list[tuple],
                 values: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        form = QFormLayout(self)
        self._widgets: dict[str, QWidget] = {}
        for key, label, kind, default in spec:
            if kind == "float":
                w = _spin_f(6, 0, 1e6, float(default))
                if key in values:
                    w.setValue(float(values[key]))
            elif kind == "int":
                w = QSpinBox(); w.setRange(0, 1_000_000)
                w.setValue(int(values.get(key, default)))
            elif kind == "bool":
                w = _bool_combo()
                _set_combo_data(w, str(values.get(key, default)).lower())
            elif kind == "combo":
                w = QComboBox(); w.addItems(list(default))
                if key in values:
                    i = w.findText(str(values[key]))
                    if i >= 0:
                        w.setCurrentIndex(i)
            form.addRow(label, w)
            self._widgets[key] = w
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        out: dict = {}
        for key, w in self._widgets.items():
            if isinstance(w, QComboBox):
                if (w.count() == 2 and
                        w.itemData(0) in ("true", "false")):
                    out[key] = w.currentData()
                else:
                    out[key] = w.currentText()
            elif isinstance(w, QDoubleSpinBox):
                out[key] = w.value()
            elif isinstance(w, QSpinBox):
                out[key] = w.value()
        return out


def _default_prism_regions(ctx: dict) -> list[dict]:
    """Detail 面区域表默认行（手册：No-slip wall 等）。"""
    rows: list[dict] = []
    seen: set[str] = set()

    def _add(name: str, *, enabled: bool = False) -> None:
        if not name or name in seen:
            return
        seen.add(name)
        rows.append({
            "name": name,
            "enabled": enabled,
            "auto": True,
            "thickness": 1.0,
            "variation": 1.1,
            "layers": 2,
            "mode": "first",  # first | each
            "each_layers": [],
        })

    for r in (ctx.get("regions_meta") or {}).get("face") or []:
        _add(r.get("name") if isinstance(r, dict) else None)
    _add("Part surface (@Part)")
    _add("No-slip wall", enabled=True)
    _add("No slip wall", enabled=True)
    # 去重 No-slip / No slip
    out: list[dict] = []
    seen2: set[str] = set()
    for r in rows:
        key = r["name"].lower().replace("-", " ")
        if key in seen2:
            continue
        seen2.add(key)
        if key == "no slip wall":
            r["name"] = "No-slip wall"
            r["enabled"] = True
        out.append(r)
    if not out:
        _add("No-slip wall", enabled=True)
        out = rows
    return out


class PrismLayerDetailDialog(QDialog):
    """[Parameters for Prism Layer Insertion]（Mesh Parameter → Detail）。"""

    def __init__(self, data: dict, ctx: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parameters for Prism Layer Insertion")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(820, 520)
        self._data = dict(data)
        self._ctx = ctx
        self._regions: list[dict] = list(
            self._data.get("regions") or _default_prism_regions(ctx))

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Specify parameters for prism layer insertion."))
        self.chk_no_solid = QCheckBox(
            "Do not insert prism layers into solid mesh")
        self.chk_no_solid.setChecked(
            bool(self._data.get("no_solid", True)))
        root.addWidget(self.chk_no_solid)

        box = QGroupBox("Parameters for Surface Regions")
        body = QHBoxLayout(box)

        left = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Region name", "Thickness", "Variation rate", "No. of layers"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 160)
        left.addWidget(self.tree, 1)
        body.addLayout(left, 1)

        mid = QVBoxLayout()
        mid.addStretch(1)
        self.btn_apply = QPushButton("<< Apply")
        self.btn_cancel = QPushButton(">> Cancel")
        mid.addWidget(self.btn_apply)
        mid.addWidget(self.btn_cancel)
        mid.addStretch(1)
        body.addLayout(mid)

        param = QGroupBox("Parameter")
        pv = QVBoxLayout(param)
        self.rb_first = QRadioButton("Specify thickness of 1st layers")
        self.rb_each = QRadioButton("Specify thickness of each layer")
        self.rb_first.setChecked(True)
        pv.addWidget(self.rb_first)

        first = QWidget()
        ff = QFormLayout(first)
        ff.setContentsMargins(16, 0, 0, 0)
        self.chk_auto = QCheckBox(
            "Calculate thickness automatically from octant size")
        self.chk_auto.setChecked(True)
        self.sp_thick = _spin_f(6, 0, 1e6, 1)
        self.sp_var = _spin_f(4, 0, 100, 1.1)
        self.sp_layers = QSpinBox()
        self.sp_layers.setRange(0, 100)
        self.sp_layers.setValue(2)
        ff.addRow(self.chk_auto)
        ff.addRow("Thickness of 1st layer", self.sp_thick)
        ff.addRow("Variation rate of thickness", self.sp_var)
        ff.addRow("Number of layers", self.sp_layers)
        pv.addWidget(first)

        pv.addWidget(self.rb_each)
        each = QWidget()
        ev = QVBoxLayout(each)
        ev.setContentsMargins(16, 0, 0, 0)
        row_e = QHBoxLayout()
        self.lst_layers = QTreeWidget()
        self.lst_layers.setHeaderLabels(["Layer No.", "Thickness"])
        self.lst_layers.setRootIsDecorated(False)
        self.lst_layers.setMaximumHeight(140)
        row_e.addWidget(self.lst_layers, 1)
        side = QVBoxLayout()
        self.btn_up = QPushButton("Up")
        self.btn_down = QPushButton("Down")
        side.addWidget(self.btn_up)
        side.addWidget(self.btn_down)
        side.addStretch(1)
        row_e.addLayout(side)
        ev.addLayout(row_e)
        row_reg = QHBoxLayout()
        row_reg.addWidget(QLabel("Thickness"))
        self.sp_each_thick = _spin_f(6, 0, 1e6, 1)
        row_reg.addWidget(self.sp_each_thick)
        self.btn_reg = QPushButton("Register")
        self.btn_del = QPushButton("Delete")
        row_reg.addWidget(self.btn_reg)
        row_reg.addWidget(self.btn_del)
        ev.addLayout(row_reg)
        pv.addWidget(each)
        self._each_box = each
        self._first_box = first
        body.addWidget(param, 1)
        root.addWidget(box, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.rb_first.toggled.connect(self._sync_param_mode)
        self.rb_each.toggled.connect(self._sync_param_mode)
        self.chk_auto.toggled.connect(self._sync_param_mode)
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.btn_apply.clicked.connect(self._apply_row)
        self.btn_cancel.clicked.connect(self._on_select)
        self.btn_reg.clicked.connect(self._register_layer)
        self.btn_del.clicked.connect(self._delete_layer)
        self.btn_up.clicked.connect(lambda: self._move_layer(-1))
        self.btn_down.clicked.connect(lambda: self._move_layer(1))

        self._reload_tree()
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._sync_param_mode()

    def _reload_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for r in self._regions:
            if r.get("enabled"):
                th = "Auto" if r.get("auto") else _fmt_disp(r.get("thickness"))
                var = _fmt_disp(r.get("variation"))
                n = str(int(r.get("layers", 0) or 0))
            else:
                th = var = n = "-"
            it = QTreeWidgetItem([r["name"], th, var, n])
            it.setData(0, Qt.UserRole, r["name"])
            self.tree.addTopLevelItem(it)
        self.tree.blockSignals(False)

    def _find_region(self, name: str) -> Optional[dict]:
        for r in self._regions:
            if r["name"] == name:
                return r
        return None

    def _on_select(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        r = self._find_region(items[0].data(0, Qt.UserRole))
        if r is None:
            return
        mode_each = r.get("mode") == "each"
        self.rb_each.setChecked(mode_each)
        self.rb_first.setChecked(not mode_each)
        self.chk_auto.setChecked(bool(r.get("auto", True)))
        self.sp_thick.setValue(float(r.get("thickness", 1) or 1))
        self.sp_var.setValue(float(r.get("variation", 1.1) or 1.1))
        self.sp_layers.setValue(int(r.get("layers", 2) or 2))
        self._reload_each_list(r)
        self._sync_param_mode()

    def _reload_each_list(self, r: dict) -> None:
        self.lst_layers.clear()
        for i, th in enumerate(r.get("each_layers") or [], 1):
            self.lst_layers.addTopLevelItem(
                QTreeWidgetItem([str(i), _fmt_disp(th) or str(th)]))

    def _sync_param_mode(self) -> None:
        first = self.rb_first.isChecked()
        self._first_box.setEnabled(first)
        self._each_box.setEnabled(not first)
        self.sp_thick.setEnabled(first and not self.chk_auto.isChecked())

    def _apply_row(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            QMessageBox.information(self, self.windowTitle(),
                                    "Select a region first.")
            return
        name = items[0].data(0, Qt.UserRole)
        r = self._find_region(name)
        if r is None:
            return
        r["enabled"] = True
        r["mode"] = "each" if self.rb_each.isChecked() else "first"
        r["auto"] = self.chk_auto.isChecked()
        r["thickness"] = self.sp_thick.value()
        r["variation"] = self.sp_var.value()
        r["layers"] = self.sp_layers.value()
        if r["mode"] == "each":
            layers = []
            for i in range(self.lst_layers.topLevelItemCount()):
                try:
                    layers.append(float(self.lst_layers.topLevelItem(i).text(1)))
                except ValueError:
                    pass
            r["each_layers"] = layers
            r["layers"] = len(layers)
        self._reload_tree()
        # 恢复选中
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, Qt.UserRole) == name:
                self.tree.setCurrentItem(it)
                break

    def _register_layer(self) -> None:
        n = self.lst_layers.topLevelItemCount() + 1
        self.lst_layers.addTopLevelItem(
            QTreeWidgetItem([str(n), _fmt_disp(self.sp_each_thick.value())
                             or str(self.sp_each_thick.value())]))

    def _delete_layer(self) -> None:
        it = self.lst_layers.currentItem()
        if it is None:
            return
        idx = self.lst_layers.indexOfTopLevelItem(it)
        self.lst_layers.takeTopLevelItem(idx)
        for i in range(self.lst_layers.topLevelItemCount()):
            self.lst_layers.topLevelItem(i).setText(0, str(i + 1))

    def _move_layer(self, delta: int) -> None:
        it = self.lst_layers.currentItem()
        if it is None:
            return
        idx = self.lst_layers.indexOfTopLevelItem(it)
        j = idx + delta
        if j < 0 or j >= self.lst_layers.topLevelItemCount():
            return
        taken = self.lst_layers.takeTopLevelItem(idx)
        self.lst_layers.insertTopLevelItem(j, taken)
        self.lst_layers.setCurrentItem(taken)
        for i in range(self.lst_layers.topLevelItemCount()):
            self.lst_layers.topLevelItem(i).setText(0, str(i + 1))

    def _on_ok(self) -> None:
        self._data = {
            "no_solid": self.chk_no_solid.isChecked(),
            "regions": self._regions,
        }
        self.accept()

    def result_data(self) -> dict:
        return dict(self._data)


class MeshParamBody(_Body):
    """[Mesh Parameter] 外层：棱柱层 / 分配方法 / Other（对齐 scFLOWpre）。"""

    title = "Mesh Parameter"
    min_size = (460, 420)
    dialog_buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx: dict = {}
        self._prism_detail: dict = {}
        self._other_values: dict[str, dict] = {}
        self._part_assign: dict[str, str] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 6)

        # 1) Thickness and number of prism layers
        prism = QGroupBox("Thickness and number of prism layers")
        pf = QFormLayout(prism)
        self.sp_prism_t = _spin_f(4, 0, 100, 0.2)
        self.sp_prism_n = QSpinBox()
        self.sp_prism_n.setRange(0, 100)
        self.sp_prism_n.setValue(2)
        pf.addRow("Thickness coefficient", self.sp_prism_t)
        pf.addRow("Number of layers", self.sp_prism_n)
        row_d = QHBoxLayout()
        row_d.addStretch(1)
        self.btn_prism_detail = QPushButton("Detail...")
        row_d.addWidget(self.btn_prism_detail)
        pf.addRow(row_d)
        v.addWidget(prism)

        # 2) Method to assign part to mesh
        assign = QGroupBox("Method to assign part to mesh")
        av = QVBoxLayout(assign)
        self.rb_ray = QRadioButton("Ray-tracing")
        self.rb_wrap = QRadioButton("Wrapping")
        self.rb_indiv = QRadioButton("Individual")
        self.rb_ray.setChecked(True)
        self.btn_indiv_set = QPushButton("Set")
        self.btn_indiv_set.setEnabled(False)
        row_ind = QHBoxLayout()
        row_ind.addWidget(self.rb_indiv)
        row_ind.addWidget(self.btn_indiv_set)
        row_ind.addStretch(1)
        av.addWidget(self.rb_ray)
        av.addWidget(self.rb_wrap)
        av.addLayout(row_ind)
        v.addWidget(assign)

        # 3) Other parameters
        other = QGroupBox("Other parameters")
        ov = QVBoxLayout(other)
        self.rb_stable = QRadioButton("Stability-oriented")
        self.rb_shape = QRadioButton("Model shape-oriented")
        self.rb_detail = QRadioButton("Detailed setting")
        self.rb_shape.setChecked(True)
        ov.addWidget(self.rb_stable)
        ov.addWidget(self.rb_shape)
        ov.addWidget(self.rb_detail)
        row_mp = QHBoxLayout()
        self.cb_mesh_item = QComboBox()
        self.cb_mesh_item.addItems(_MESH_OTHER_ITEMS)
        self.cb_mesh_item.setEnabled(False)
        self.btn_mesh_set = QPushButton("Mesh Parameter")
        self.btn_mesh_set.setEnabled(False)
        row_mp.addWidget(self.cb_mesh_item, 1)
        row_mp.addWidget(self.btn_mesh_set)
        ov.addLayout(row_mp)
        self.btn_set_stable = QPushButton(
            "Set values of stability-oriented type")
        self.btn_set_shape = QPushButton(
            "Set values of model shape-oriented type")
        self.btn_set_stable.setEnabled(False)
        self.btn_set_shape.setEnabled(False)
        ov.addWidget(self.btn_set_stable)
        ov.addWidget(self.btn_set_shape)
        v.addWidget(other)

        row_c = QHBoxLayout()
        row_c.addStretch(1)
        self.btn_create = QPushButton("Create Mesh")
        row_c.addWidget(self.btn_create)
        v.addLayout(row_c)
        v.addStretch(1)

        for rb in (self.rb_ray, self.rb_wrap, self.rb_indiv):
            rb.toggled.connect(self._sync_assign)
        for rb in (self.rb_stable, self.rb_shape, self.rb_detail):
            rb.toggled.connect(self._sync_other)
        self.btn_prism_detail.clicked.connect(self._open_prism_detail)
        self.btn_mesh_set.clicked.connect(self._edit_mesh_item)
        self.btn_set_stable.clicked.connect(
            lambda: self._apply_preset("stability"))
        self.btn_set_shape.clicked.connect(
            lambda: self._apply_preset("shape"))
        self.btn_indiv_set.clicked.connect(self._edit_individual)
        self.btn_create.clicked.connect(self._create_mesh)
        self._sync_assign()
        self._sync_other()

    def _sync_assign(self) -> None:
        self.btn_indiv_set.setEnabled(self.rb_indiv.isChecked())

    def _sync_other(self) -> None:
        detailed = self.rb_detail.isChecked()
        self.cb_mesh_item.setEnabled(detailed)
        self.btn_mesh_set.setEnabled(detailed)
        # Detailed 下可用预设按钮灌入子项默认值
        self.btn_set_stable.setEnabled(detailed)
        self.btn_set_shape.setEnabled(detailed)

    def load(self, ctx: dict) -> None:
        self._ctx = ctx
        sess = ctx.setdefault("session", {}).setdefault("mesh_param", {})
        if "prism_t" in sess:
            self.sp_prism_t.setValue(float(sess["prism_t"]))
        if "prism_n" in sess:
            self.sp_prism_n.setValue(int(sess["prism_n"]))
        self._prism_detail = dict(sess.get("prism_detail") or {})
        assign = sess.get("assign", "Ray-tracing")
        self.rb_ray.setChecked(assign == "Ray-tracing")
        self.rb_wrap.setChecked(assign == "Wrapping")
        self.rb_indiv.setChecked(assign == "Individual")
        other = sess.get("other_type", "Model shape-oriented")
        self.rb_stable.setChecked(other == "Stability-oriented")
        self.rb_shape.setChecked(other == "Model shape-oriented")
        self.rb_detail.setChecked(other == "Detailed setting")
        self._other_values = dict(sess.get("other", {}) or {})
        self._part_assign = dict(sess.get("part_assign", {}) or {})
        self._sync_assign()
        self._sync_other()

    def _open_prism_detail(self) -> None:
        data = dict(self._prism_detail)
        if not data.get("regions"):
            data["regions"] = _default_prism_regions(self._ctx)
            # 用外层面板层数同步默认 No-slip wall
            for r in data["regions"]:
                if r["name"] == "No-slip wall":
                    r["layers"] = self.sp_prism_n.value()
                    r["enabled"] = self.sp_prism_n.value() > 0
        dlg = PrismLayerDetailDialog(data, self._ctx, self)
        if dlg.exec_() == QDialog.Accepted:
            self._prism_detail = dlg.result_data()
            sess = self._ctx.setdefault("session", {}).setdefault(
                "mesh_param", {})
            sess["prism_detail"] = dict(self._prism_detail)
            # 从 No-slip wall 回写外层 Number of layers（若启用）
            for r in self._prism_detail.get("regions") or []:
                if r.get("name") == "No-slip wall" and r.get("enabled"):
                    self.sp_prism_n.setValue(int(r.get("layers", 2) or 2))
                    break

    def _edit_mesh_item(self) -> None:
        name = self.cb_mesh_item.currentText()
        spec = _MESH_SUB_SPECS.get(name, [])
        if not spec:
            QMessageBox.information(self, "Mesh Parameter",
                                    f"「{name}」暂无详细字段。")
            return
        dlg = _MeshSubDialog(name, spec, self._other_values.get(name, {}), self)
        if dlg.exec_() == QDialog.Accepted:
            self._other_values[name] = dlg.values()

    def _apply_preset(self, kind: str) -> None:
        preset = (_MESH_PRESET_STABILITY if kind == "stability"
                  else _MESH_PRESET_SHAPE)
        for name, vals in preset.items():
            self._other_values[name] = dict(vals)
        QMessageBox.information(
            self, "Mesh Parameter",
            f"已载入 {'stability-oriented' if kind == 'stability' else 'model shape-oriented'} "
            "类型默认值到 Detailed setting。")

    def _edit_individual(self) -> None:
        # 简化：按零件名选择 Ray-tracing / Wrapping
        names = []
        for info in (self._ctx.get("groups_info") or {}).values():
            for p in info.get("xml_parts") or []:
                n = p.get("name") if isinstance(p, dict) else None
                if n:
                    names.append(n)
        if not names:
            names = ["Part"]
        dlg = QDialog(self)
        dlg.setWindowTitle("Individual assignment")
        form = QFormLayout(dlg)
        widgets: dict[str, QComboBox] = {}
        for n in names:
            cb = QComboBox()
            cb.addItems(["Ray-tracing", "Wrapping"])
            cur = self._part_assign.get(n, "Ray-tracing")
            i = cb.findText(cur)
            if i >= 0:
                cb.setCurrentIndex(i)
            form.addRow(n, cb)
            widgets[n] = cb
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec_() == QDialog.Accepted:
            self._part_assign = {n: w.currentText() for n, w in widgets.items()}

    def _create_mesh(self) -> None:
        sess = self._ctx.setdefault("session", {}).setdefault("mesh_param", {})
        sess["create_requested"] = True
        QMessageBox.information(
            self, "Create Mesh",
            "已记录 Create Mesh。\n"
            "本查看器不执行网格器；请在 [Execute] 勾选 Generate Mesh，"
            "或于 scFLOWpre 中 Create。")

    def apply(self, ctx: dict) -> bool:
        assign = ("Ray-tracing" if self.rb_ray.isChecked()
                  else "Wrapping" if self.rb_wrap.isChecked()
                  else "Individual")
        other = ("Stability-oriented" if self.rb_stable.isChecked()
                 else "Model shape-oriented" if self.rb_shape.isChecked()
                 else "Detailed setting")
        ctx.setdefault("session", {})["mesh_param"] = {
            "prism_t": self.sp_prism_t.value(),
            "prism_n": self.sp_prism_n.value(),
            "prism_detail": dict(self._prism_detail),
            "assign": assign,
            "part_assign": dict(self._part_assign),
            "other_type": other,
            "other": self._other_values,
        }
        return True


class ExecuteBody(_Body):
    title = "Execute"
    min_size = (520, 420)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Execute] 批处理\n"
            "勾选步骤并 OK/Apply；默认经 scFLOWpre COM API 执行 "
            "Wrapping / BAM / Octree / Mesh。\n"
            "Execute Solver 本查看器不支持（仍为 NYI）。"))
        box = QGroupBox("Process")
        bv = QVBoxLayout(box)
        self.chk_wrap = QCheckBox("Wrapping (from CAD)")
        self.chk_bam = QCheckBox("Build Analysis Model")
        self.chk_oct = QCheckBox("Generate Octree for Meshing")
        self.chk_mesh = QCheckBox("Generate Mesh")
        self.chk_files = QCheckBox("Create files (mesh / condition)")
        self.chk_save = QCheckBox("Save project")
        self.chk_solver = QCheckBox("Execute Solver (not available)")
        self.chk_wrap.setChecked(False)
        self.chk_bam.setChecked(True)
        self.chk_oct.setChecked(True)
        self.chk_mesh.setChecked(True)
        self.chk_use_api = QCheckBox(
            "使用 scFLOWpre API 构建 Model / Octree / Mesh")
        self.chk_use_api.setChecked(True)
        for w in (self.chk_wrap, self.chk_bam, self.chk_oct, self.chk_mesh,
                  self.chk_files, self.chk_save, self.chk_solver):
            bv.addWidget(w)
        bv.addWidget(self.chk_use_api)
        v.addWidget(box)
        self.cb_mesh_mode = QComboBox()
        self.cb_mesh_mode.addItems(["Create", "Use existing"])
        form = QFormLayout()
        form.addRow("Mesh file", self.cb_mesh_mode)
        v.addLayout(form)
        self.lab = QLabel(); self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        v.addStretch(1)

    def load(self, ctx: dict) -> None:
        ex = ctx.setdefault("session", {}).setdefault("execute", {})
        self.chk_wrap.setChecked(ex.get("wrapping", False))
        self.chk_bam.setChecked(ex.get("bam", True))
        self.chk_oct.setChecked(ex.get("oct", True))
        self.chk_mesh.setChecked(ex.get("mesh", True))
        self.chk_files.setChecked(ex.get("files", False))
        self.chk_save.setChecked(ex.get("save", False))
        self.chk_solver.setChecked(ex.get("solver", False))
        # 默认 True；仅当会话显式 False 时关闭
        self.chk_use_api.setChecked(bool(ex.get("use_api", True)))
        if ex.get("mesh_mode"):
            i = self.cb_mesh_mode.findText(ex["mesh_mode"])
            if i >= 0:
                self.cb_mesh_mode.setCurrentIndex(i)
        groups = ctx.get("groups_info") or {}
        has_mdl = any((i.get("paths") or {}).get("part") for i in groups.values())
        has_oct = any((i.get("paths") or {}).get("oct") for i in groups.values())
        has_gph = any((i.get("paths") or {}).get("gph") for i in groups.values())
        self.lab.setText(
            f"Current results — MDL: {'yes' if has_mdl else 'no'}, "
            f"OCT: {'yes' if has_oct else 'no'}, "
            f"GPH: {'yes' if has_gph else 'no'}")

    def apply(self, ctx: dict) -> bool:
        if self.chk_solver.isChecked():
            QMessageBox.information(
                self, "Execute Solver",
                "Execute Solver is not available in PPH viewer.\n"
                "Use scFLOWsolver / scPOST separately.")
        ctx.setdefault("session", {})["execute"] = {
            "wrapping": self.chk_wrap.isChecked(),
            "bam": self.chk_bam.isChecked(),
            "oct": self.chk_oct.isChecked(),
            "mesh": self.chk_mesh.isChecked(),
            "files": self.chk_files.isChecked(),
            "save": self.chk_save.isChecked(),
            "solver": False,  # 强制不进管线
            "mesh_mode": self.cb_mesh_mode.currentText(),
            "use_api": self.chk_use_api.isChecked(),
        }
        return True


class OptionNavBody(_Body):
    """Option → Navigation：Analysis Model Wizard 与导航项显隐。"""

    title = "Option - Navigation"
    min_size = (480, 240)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Option] – [Navigation]"))
        self.chk_always = QCheckBox(
            "Always show the analysis model wizard")
        self.chk_show_bam = QCheckBox(
            "Show [Build Analysis Model] item")
        self.chk_show_mesher = QCheckBox(
            "Show [Mesher/Faceter Setting] item")
        self.chk_show_bam.setChecked(True)
        self.chk_show_mesher.setChecked(True)
        v.addWidget(self.chk_always)
        v.addWidget(self.chk_show_bam)
        v.addWidget(self.chk_show_mesher)
        v.addStretch(1)

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {}).setdefault("option_nav", {})
        self.chk_always.setChecked(bool(sess.get("always_show_wizard", False)))
        self.chk_show_bam.setChecked(bool(sess.get("show_bam_item", True)))
        self.chk_show_mesher.setChecked(
            bool(sess.get("show_mesher_item", True)))

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["option_nav"] = {
            "always_show_wizard": self.chk_always.isChecked(),
            "show_bam_item": self.chk_show_bam.isChecked(),
            "show_mesher_item": self.chk_show_mesher.isChecked(),
        }
        return True


# ---------------------------------------------------------------------------
# P1-2/P1-3: schema 驱动的通用 Cond* 条件表单（GenericCondBody）
# ---------------------------------------------------------------------------
_COND_REGISTRY_CACHE: Optional[object] = None


def condition_registry_cached():
    """从 ``schemas/*.json`` 构建并缓存 ConditionRegistry（无则 None）。

    P4-1：额外合并 ``schemas/cond_types.json`` 目录（scFLOWpre 二进制
    扫描的 ~165 个 Cond* 类型 + HTML 帮助页交叉核对元数据），使全部
    已知类型可经通用表单新建。
    """
    global _COND_REGISTRY_CACHE
    if _COND_REGISTRY_CACHE is not None:
        return _COND_REGISTRY_CACHE or None
    try:
        from condition_registry import ConditionRegistry
        from schema_extract import load_schema_json
        schemas_dir = Path(__file__).resolve().parent / "schemas"
        items = []
        for p in sorted(schemas_dir.glob("*.json")):
            if p.name in ("cond_types.json", "condition_tree.json",
                          "cond_html_meta.json"):
                continue  # 目录/树元数据走 merge_catalog，非样本 schema
            try:
                items.append((load_schema_json(p), p.stem))
            except Exception:  # noqa: BLE001
                continue
        reg = ConditionRegistry.from_schemas(items) if items \
            else ConditionRegistry()
        catalog = schemas_dir / "cond_types.json"
        if catalog.is_file():
            reg.merge_catalog(catalog)
        reg = reg if reg.types else None
        _COND_REGISTRY_CACHE = reg or False
        return reg
    except Exception:  # noqa: BLE001
        _COND_REGISTRY_CACHE = False
        return None


def _region_names_for_cond(ctx: dict) -> list[str]:
    """当前可选区域名（face/special_face/numerical + 零件名兜底）。"""
    names: list[str] = []
    xml = ctx.get("xml")
    if xml is not None:
        regs = xml.section("regions")
        if regs is not None:
            for cat in ("face", "special_face", "numerical", "special",
                        "volume"):
                node = regs.find(cat)
                if node is None:
                    continue
                for r in node.findall("region"):
                    n = r.findtext("name") or ""
                    if n:
                        names.append(n)
    if not names:
        names = sorted((ctx.get("groups_info") or {}))
    return names


class GenericCondBody(QDialog):
    """schema 驱动的通用 Cond* 条件表单（新建）。

    字段来自 ConditionRegistry（schemas/*.json 语料合并）：类型推断
    （int/float/bool/string/enum）、必填标记（字段出现计数 = 类型实例数）
    与样本默认值。OK 后通过 :func:`write_condition_to_xml` 落 main.xml。
    """

    def __init__(self, cond_type: str, ctype, ctx: dict, parent=None):
        super().__init__(parent)
        self.cond_type = cond_type
        self.ctype = ctype
        self._widgets: dict[str, object] = {}   # path → widget
        self._meta: list[dict] = ctype.field_meta()
        self.setWindowTitle(f"New Condition — {cond_type}")
        self.setMinimumSize(520, 420)

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(8, 8, 8, 8)

        form0 = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Condition name (required)")
        form0.addRow("Name *", self.ed_name)
        lab_t = QLabel(cond_type)
        lab_t.setStyleSheet("color:#555;")
        form0.addRow("Type", lab_t)
        v.addLayout(form0)

        # 区域多选
        gb_reg = QGroupBox("Regions")
        lv = QVBoxLayout(gb_reg)
        self.lst_regions = QListWidget()
        self.lst_regions.setSelectionMode(QListWidget.MultiSelection)
        for n in _region_names_for_cond(ctx):
            self.lst_regions.addItem(n)
        if self.lst_regions.count():
            self.lst_regions.item(0).setSelected(True)
        lv.addWidget(self.lst_regions)
        v.addWidget(gb_reg)

        # 字段：按 "." 路径分组进嵌套 GroupBox
        gb_root = QGroupBox("Fields")
        fv = QVBoxLayout(gb_root)
        inner = self._build_group(self._meta, "")
        fv.addWidget(inner)
        v.addWidget(gb_root, 1)

        tip = _note("* required. 空的可选字段不会写入 XML；样本值仅为默认建议。")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addWidget(tip)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    # -- 表单构建 ---------------------------------------------------------
    def _build_group(self, meta: list[dict], prefix: str) -> QWidget:
        """递归构建一组字段的容器（直接叶子进 FormLayout）。"""
        form = QFormLayout()
        subs: list[tuple[str, list[dict]]] = []
        for m in meta:
            name = m["name"]
            # 去掉父前缀（含分隔点）得到本级段名
            seg = name[len(prefix) + 1:] if prefix and name.startswith(
                prefix + ".") else name
            if "." in seg:
                parent_seg = seg.split(".", 1)[0]
                sub_prefix = (prefix + "." + parent_seg) if prefix \
                    else parent_seg
                for sp, lst in subs:
                    if sp == sub_prefix:
                        lst.append(m)
                        break
                else:
                    subs.append((sub_prefix, [m]))
                continue
            form.addRow(self._field_label(m), self._field_widget(m))
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(form)
        for sub_prefix, lst in subs:
            gb = QGroupBox(sub_prefix.rsplit(".", 1)[-1])
            gl = QVBoxLayout(gb)
            gl.addWidget(self._build_group(lst, sub_prefix))
            lay.addWidget(gb)
        lay.addStretch(1)
        return w

    @staticmethod
    def _field_label(m: dict) -> str:
        return m["name"].rsplit(".", 1)[-1] + (" *" if m["required"] else "")

    def _field_widget(self, m: dict):
        kind, enum, default = m["kind"], m.get("enum") or [], m["default"]
        if enum:
            w = QComboBox()
            w.setEditable(True)
            w.addItems(enum)
            w.setCurrentText(default or enum[0])
        elif kind == "bool":
            w = _bool_combo()
            if default:
                _set_combo_data(w, default)
        else:
            w = QLineEdit(default)
            if kind in ("int", "float"):
                w.setPlaceholderText(kind)
        self._widgets[m["name"]] = w
        return w

    # -- 取值 / 校验 -------------------------------------------------------
    def _value(self, path: str, m: dict) -> str:
        w = self._widgets.get(path)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        return w.text().strip() if w is not None else ""

    def _validate(self) -> list[str]:
        errs: list[str] = []
        if not self.ed_name.text().strip():
            errs.append("Name is required.")
        for m in self._meta:
            val = self._value(m["name"], m)
            # empty（语料中空元素形态）/ composite（结构节点）无文本值，
            # 不做"必填非空"检查
            if (m["required"] and not val
                    and m["kind"] not in ("empty", "composite")):
                errs.append(f"Required field empty: {m['name']}")
            elif val and m["kind"] == "int":
                try:
                    int(val)
                except ValueError:
                    errs.append(f"Not an integer: {m['name']} = {val!r}")
            elif val and m["kind"] == "float":
                try:
                    float(val)
                except ValueError:
                    errs.append(f"Not a float: {m['name']} = {val!r}")
        return errs

    def _on_ok(self) -> None:
        errs = self._validate()
        if errs:
            QMessageBox.warning(self, "New Condition", "\n".join(errs[:8]))
            return
        self.accept()

    def result_cond(self) -> dict:
        regions = [i.text() for i in self.lst_regions.selectedItems()]
        fields = {}
        for m in self._meta:
            val = self._value(m["name"], m)
            if val:
                fields[m["name"]] = val
        return {
            "type": self.cond_type,
            "name": self.ed_name.text().strip(),
            "regions": regions,
            "fields": fields,
        }


# 页 key → 目录 category（CondTypeCatalogDialog 过滤用）
_PAGE_CATEGORIES: dict[str, list[str]] = {
    "initial": ["initial"],
    "bc_flow": ["bc_flow"],
    "bc_wall": ["bc_wall"],
    "bc_thermal": ["bc_thermal", "radiation", "solar", "humidity"],
    "bc_sym": ["bc_sym"],
    "bc_periodic": ["bc_periodic"],
    "source": ["source"],
    "fixed": ["fixed"],
}

_CATEGORY_LABELS: list[tuple[str, str]] = [
    ("initial", "Initial Condition"),
    ("bc_flow", "Flow Boundary"),
    ("bc_wall", "Wall Boundary"),
    ("bc_thermal", "Thermal Boundary"),
    ("bc_sym", "Symmetrical Boundary"),
    ("bc_periodic", "Periodic Boundary"),
    ("source", "Source Condition"),
    ("fixed", "Fixed Condition"),
    ("particle", "Particle / DEM"),
    ("moving", "Moving Condition"),
    ("porous", "Porous Media"),
    ("humidity", "Humidity"),
    ("radiation", "Radiation"),
    ("solar", "Solar Radiation"),
    ("reaction", "Reaction / Combustion"),
    ("multiphase", "Multiphase / Free Surface"),
    ("output", "Output"),
    ("overset", "Overset Mesh"),
    ("cosim", "Co-simulation (Nastran/Actran/FMI)"),
    ("battery", "Battery"),
    ("human", "Thermoregulation (JOS)"),
    ("basic", "Basic / Solver"),
    ("misc", "Miscellaneous"),
]


class CondTypeCatalogDialog(QDialog):
    """条件类型目录（P4-1）：二进制扫描目录 → 通用表单入口。

    左侧 category 分组树（含计数），右侧类型列表（显示名 + 类型名 +
    字段 schema/样本背书标记 + 帮助页）；顶部搜索框过滤双击新建，
    走 :class:`GenericCondBody`（样本类型带字段表单，目录类型仅
    name+regions，字段待样本补全）。
    """

    def __init__(self, ctx: dict, categories: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._cats = categories  # None = 全部
        self._selected: str = ""
        reg = condition_registry_cached()
        self._reg = reg

        self.setWindowTitle("Condition Type Catalog — scFLOWpre Cond*")
        self.setMinimumSize(760, 520)

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText(
            "Filter by display name / type name ...")
        self.ed_search.textChanged.connect(self._refilter)
        top.addWidget(self.ed_search, 1)
        outer.addLayout(top)

        split = QHBoxLayout()
        self.nav = QTreeWidget()
        self.nav.setHeaderHidden(True)
        self.nav.setMinimumWidth(220)
        self.nav.setMaximumWidth(280)
        split.addWidget(self.nav)

        right = QVBoxLayout()
        self.lst = QTreeWidget()
        self.lst.setHeaderLabels(
            ["Condition", "Type", "Fields", "Origin"])
        self.lst.setRootIsDecorated(False)
        self.lst.setAlternatingRowColors(True)
        self.lst.setColumnWidth(0, 280)
        self.lst.setColumnWidth(1, 220)
        self.lst.itemDoubleClicked.connect(self._on_create)
        right.addWidget(self.lst, 1)
        self.lab_detail = QLabel("")
        self.lab_detail.setWordWrap(True)
        self.lab_detail.setStyleSheet("color:#555; font-size:11px;")
        right.addWidget(self.lab_detail)
        self.lst.currentItemChanged.connect(self._on_select)
        split.addLayout(right, 1)
        outer.addLayout(split, 1)

        self.lab_note = _note(
            "双击类型打开通用表单。Fields 列：样本 schema 数（空 = 目录"
            "级，表单仅 name+regions）；Origin：sample=本地 pph 样本、"
            "gui/cmd=scFLOWpre 二进制目录。")
        outer.addWidget(self.lab_note)
        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("New condition")
        bb.accepted.connect(self._on_create_btn)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

        self._build_nav()

    def _build_nav(self) -> None:
        reg = self._reg
        counts: dict[str, int] = {}
        if reg is not None:
            for t in reg.types.values():
                counts[t.category or "misc"] = counts.get(
                    t.category or "misc", 0) + 1
        self.nav.clear()
        all_item = QTreeWidgetItem(["All types"])
        all_item.setData(0, Qt.UserRole, None)
        self.nav.addTopLevelItem(all_item)
        for key, label in _CATEGORY_LABELS:
            n = counts.get(key, 0)
            if self._cats is not None and key not in self._cats:
                continue
            if n == 0:
                continue
            it = QTreeWidgetItem([f"{label} ({n})"])
            it.setData(0, Qt.UserRole, [key])
            self.nav.addTopLevelItem(it)
        self.nav.setCurrentItem(all_item)
        self.nav.currentItemChanged.connect(lambda *_: self._refilter())
        self._refilter()

    def _refilter(self) -> None:
        reg = self._reg
        self.lst.clear()
        if reg is None:
            return
        item = self.nav.currentItem()
        cats = item.data(0, Qt.UserRole) if item else None
        if cats is None and self._cats is not None:
            cats = self._cats
        text = self.ed_search.text().strip().lower()
        for name in sorted(reg.types):
            t = reg.types[name]
            if cats is not None and (t.category or "misc") not in cats:
                continue
            disp = t.display or name
            if text and text not in disp.lower() \
                    and text not in name.lower():
                continue
            it = QTreeWidgetItem([
                disp, name,
                str(len(t.fields)) if t.fields else "—",
                "sample" if t.sample_count or t.count else t.lineage,
            ])
            it.setData(0, Qt.UserRole, name)
            self.lst.addTopLevelItem(it)

    def _on_select(self, cur, _prev) -> None:
        if cur is None:
            self.lab_detail.setText("")
            return
        name = cur.data(0, Qt.UserRole)
        t = self._reg.types.get(name) if self._reg else None
        if t is None:
            return
        bits = []
        if t.display and t.display != name:
            bits.append(t.display)
        if t.help_file:
            bits.append(f"help: {t.help_file}")
        if t.sample_count or t.count:
            bits.append(f"samples: {t.sample_count or t.count}")
        self.lab_detail.setText("  |  ".join(bits))

    def _on_create(self, *_args) -> None:
        it = self.lst.currentItem()
        if it is None:
            return
        name = it.data(0, Qt.UserRole)
        ctype = self._reg.types.get(name) if self._reg else None
        if ctype is None:
            return
        dlg = GenericCondBody(name, ctype, self._ctx, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.result_cond()
        if write_condition_to_xml(self._ctx, ctype, data):
            sess = self._ctx.setdefault("session", {}).setdefault(
                "conditions", {})
            sess.setdefault("created", []).append({
                "page": "catalog", "kind": name, "name": data["name"],
                "written": True,
            })
            nav = self.parent()
            fill = getattr(nav, "_fill_condition_lists", None)
            if fill is not None:
                fill()
            self.accept()

    def _on_create_btn(self) -> None:
        if self.lst.currentItem() is None:
            QMessageBox.information(
                self, "Condition Type Catalog", "请先选择一个条件类型。")
            return
        self._on_create()


class HeatTransferPresetDialog(QDialog):
    """换热系数预设选择器（P4-2，heattransfer_ENG.xml）。

    厂商预设（外壁 / 屋顶 / 地板 / 室内等 20 组，两向热流系数），
    双击返回 :class:`HeatTransferPreset`。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preset = None
        self.setWindowTitle("Heat Transfer Coefficient Presets")
        self.setMinimumSize(520, 420)
        from material_lib import material_lib_cached
        lib = material_lib_cached()

        v = QVBoxLayout(self)
        self.lst = QTreeWidget()
        self.lst.setHeaderLabels(
            ["Category", "Surface", "Up [W/m2K]", "Down [W/m2K]"])
        self.lst.setRootIsDecorated(False)
        self.lst.setAlternatingRowColors(True)
        self.lst.itemDoubleClicked.connect(self._pick)
        v.addWidget(self.lst, 1)
        labels = {1: "Wall (vertical)", 2: "Floor / horizontal",
                  3: "Indoor", 4: "Other"}
        if lib is not None:
            for p in lib.heat_transfer_presets():
                vals = p.values + [0.0, 0.0]
                it = QTreeWidgetItem([
                    labels.get(p.type_id, str(p.type_id)),
                    p.subname or p.name,
                    f"{vals[0]:g}", f"{vals[1]:g}",
                ])
                it.setData(0, Qt.UserRole, p)
                self.lst.addTopLevelItem(it)
        v.addWidget(_note("双击应用预设；来源 heattransfer_ENG.xml"
                          "（scSTREAM 建筑空调手册值）。"))

    def _pick(self, item, *_a):
        self.preset = item.data(0, Qt.UserRole)
        self.accept()


class SolarSiteDialog(QDialog):
    """太阳辐射站点选择器（P4-2：solar_ENG.xml + SolarNEDO11.xml）。

    世界城市（~10）+ 日本 NEDO 气象站点（837，按都道府县分组）；
    双击返回 ``(name, latitude, longitude, standard, elevation)``。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.site = None
        self.setWindowTitle("Solar Location — world cities / NEDO")
        self.setMinimumSize(600, 480)
        from material_lib import material_lib_cached
        lib = material_lib_cached()

        v = QVBoxLayout(self)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Filter sites ...")
        v.addWidget(self.ed_search)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)

        self.lst_world = QTreeWidget()
        self._fill_world(lib)
        self.tabs.addTab(self.lst_world, "World cities")
        self.lst_nedo = QTreeWidget()
        self._fill_nedo(lib)
        self.tabs.addTab(self.lst_nedo, "NEDO (Japan)")
        for lst in (self.lst_world, self.lst_nedo):
            lst.itemDoubleClicked.connect(self._pick)
        self.ed_search.textChanged.connect(self._filter)
        v.addWidget(_note("双击选用站点；来源 solar_ENG.xml / "
                          "SolarNEDO11.xml（MONSOLA-11, METPV-11）。"))

    @staticmethod
    def _columns() -> list[str]:
        return ["Site", "Latitude [deg]", "Longitude [deg]",
                "Standard [deg]", "Elevation [m]"]

    def _fill_world(self, lib):
        self.lst_world.setHeaderLabels(self._columns())
        self.lst_world.setRootIsDecorated(False)
        if lib is None:
            return
        for loc in lib.solar_locations():
            it = QTreeWidgetItem([
                loc.name, f"{loc.latitude:g}", f"{loc.longitude:g}",
                f"{loc.standard:g}", ""])
            it.setData(0, Qt.UserRole,
                       (loc.name, loc.latitude, loc.longitude,
                        loc.standard, 0.0))
            self.lst_world.addTopLevelItem(it)

    def _fill_nedo(self, lib):
        self.lst_nedo.setHeaderLabels(self._columns())
        if lib is None:
            return
        cats: dict[str, QTreeWidgetItem] = {}
        for s in lib.nedo_sites():
            top = cats.get(s.category)
            if top is None:
                top = cats[s.category] = QTreeWidgetItem(
                    [f"{s.category} / {s.category_jpn}"])
                top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
                self.lst_nedo.addTopLevelItem(top)
            label = s.name or s.name_jpn
            it = QTreeWidgetItem([
                f"{label} ({s.no})", f"{s.latitude:g}",
                f"{s.longitude:g}", f"{s.standard:g}",
                f"{s.elevation:g}",
            ])
            it.setData(0, Qt.UserRole,
                       (label, s.latitude, s.longitude, s.standard,
                        s.elevation))
            top.addChild(it)

    def _filter(self, text: str) -> None:
        t = text.strip().lower()
        for lst in (self.lst_world, self.lst_nedo):
            for i in range(lst.topLevelItemCount()):
                top = lst.topLevelItem(i)
                if top.childCount() == 0:
                    top.setHidden(bool(t) and t not in
                                  top.text(0).lower())
                    continue
                nvis = 0
                for j in range(top.childCount()):
                    ch = top.child(j)
                    hide = bool(t) and t not in ch.text(0).lower()
                    ch.setHidden(hide)
                    nvis += 0 if hide else 1
                top.setHidden(nvis == 0)

    def _pick(self, item, *_a):
        data = item.data(0, Qt.UserRole)
        if data is None:
            return
        self.site = data
        self.accept()


def write_condition_to_xml(ctx: dict, ctype, data: dict) -> bool:
    """把 GenericCondBody 结果写进 ctx['xml'] 的 ``<conditions>``。

    返回是否写入成功（无 xml 时 False）。字段按 schema 首现顺序重建，
    复合父节点按 "." 路径展开；区域子标签取 schema 中 regions.<tag>
    的首个形态（如 region/face）。
    """
    xml = ctx.get("xml")
    if xml is None:
        return False
    cond_root = xml.section("conditions")
    if cond_root is None:
        cond_root = ET.SubElement(xml.root, "conditions")
    el = ET.SubElement(cond_root, "condition")
    ET.SubElement(el, "type").text = data["type"]
    ET.SubElement(el, "name").text = data["name"]

    if data.get("regions"):
        regs = ET.SubElement(el, "regions")
        tag = "region"
        for fname in ctype.fields:
            if fname.startswith("regions."):
                tag = fname.rsplit(".", 1)[-1]
                break
        for r in data["regions"]:
            ET.SubElement(regs, tag).text = r

    def _ensure(parent: ET.Element, seg: str) -> ET.Element:
        node = parent.find(seg)
        if node is None:
            node = ET.SubElement(parent, seg)
        return node

    for path, value in data.get("fields", {}).items():
        segs = path.split(".")
        node = el
        for seg in segs[:-1]:
            node = _ensure(node, seg)
        ET.SubElement(node, segs[-1]).text = value

    ctx["xml_dirty"] = True
    return True


BODY_CLASSES: dict[str, type] = {
    "parts_control": PartsControlBody,
    "import_part": ImportPartBody,
    "create_parts": CreatePartsBody,
    "modify_parts": ModifyPartsBody,
    "specify_disc": SpecifyDiscontinuousPartsBody,
    "overset_mesh": OversetMeshBody,
    "wrap_octree": WrappingOctreeParamBody,
    "wrap_param": WrappingParamBody,
    "begin_wrap": BeginWrappingBody,
    "cancel_wrap": CancelWrappingBody,
    "exec_wrap": ExecuteWrappingBody,
    "retry_wrap": RetryWrappingBody,
    "mesher_faceter": MesherFaceterBody,
    "regions": RegisterRegionBody,
    "non_solid": NonSolidBody,
    "part_material": PartMaterialBody,
    "conditions": ConditionsBody,
    # build_am：Navigation 为确认框；Detailed… → Analysis Model Wizard
    "build_am_detailed": AnalysisModelWizardBody,
    "option_nav": OptionNavBody,

    "oct_param": OctreeParamBody,
    "mesh_param": MeshParamBody,
    "execute": ExecuteBody,
}

# 兼容旧引用
PANEL_CLASSES = BODY_CLASSES


class NavParamDialog(QDialog):
    """scFLOWpre 风格参数弹出子窗口：滚动内容 + OK / Cancel [/ Apply]。"""

    def __init__(self, key: str, body: _Body, ctx: dict, parent=None):
        super().__init__(parent)
        self._key = key
        self._body = body
        self._ctx = ctx
        self.setWindowTitle(body.title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        w, h = getattr(body, "min_size", (520, 420))
        self.resize(w, h)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        flags = getattr(body, "dialog_buttons", None)
        if flags is None:
            flags = (QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                     | QDialogButtonBox.Apply)
        # 0 / NoButton：内容页自带向导按钮（如 Condition Wizard）
        if flags:
            buttons = QDialogButtonBox(flags, Qt.Horizontal, self)
            buttons.accepted.connect(self._on_ok)
            buttons.rejected.connect(self.reject)
            apply_btn = buttons.button(QDialogButtonBox.Apply)
            if apply_btn is not None:
                apply_btn.clicked.connect(self._on_apply)
            root.addWidget(buttons)
        body.load(ctx)

    def _on_apply(self) -> bool:
        ok = self._body.apply(self._ctx)
        if not ok:
            QMessageBox.information(self, self.windowTitle(),
                                    "无项目数据或无可写字段")
        return ok

    def _on_ok(self) -> None:
        if self._on_apply():
            self.accept()


class NavDialogSession:
    """在主窗口上保持 session，并打开 Navigation 对话框。"""

    def __init__(self):
        self.session: dict = {}
        self._open: dict[str, NavParamDialog] = {}

    def build_ctx(self, *, xenv=None, xml=None, prp=None,
                  groups_info=None, regions_meta=None, **extra) -> dict:
        ctx = {
            "session": self.session,
            "xenv": xenv,
            "xml": xml,
            "prp": prp,
            "groups_info": groups_info or {},
            "regions_meta": regions_meta or {},
            "xenv_dirty": False,
            "xml_dirty": False,
        }
        ctx.update(extra)
        return ctx

    def open(self, key: str, ctx: dict, parent=None) -> Optional[NavParamDialog]:
        cls = BODY_CLASSES.get(key)
        if cls is None:
            return None
        # 同 key 已打开则前置
        existing = self._open.get(key)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return existing
        body = cls()
        dlg = NavParamDialog(key, body, ctx, parent)
        self._open[key] = dlg

        def _clear(_result=None, k=key):
            self._open.pop(k, None)

        dlg.finished.connect(_clear)
        return dlg
