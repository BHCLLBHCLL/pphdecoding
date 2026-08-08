#!/usr/bin/env python3
"""scFLOWpre 风格 Navigation 弹出对话框（Prepare Parts / Build Analysis Model）。

点击 Navigation 叶子项时弹出独立子窗口（OK / Cancel / Apply），绑定
``main.xenv`` / ``main.xml`` / ``main.prp`` 与网格组状态。CAD 建体、
网格生成等执行步骤在本查看器中保存参数并提示需 scFLOWpre 完成。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

import pphxml

# Navigation key → 是否弹出对话框
DIALOG_KEYS = frozenset({
    "parts_control", "import_part", "create_parts", "modify_parts",
    "mesher_faceter", "regions", "non_solid", "part_material",
    "conditions", "build_am", "oct_param", "mesh_param", "execute",
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

    def load(self, ctx: dict) -> None:
        pass

    def apply(self, ctx: dict) -> bool:
        return True


class PartsControlBody(_Body):
    title = "Parts Control"

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Condition] – [Parts Control]\n"
            "勾选后 Navigation 中会出现对应子项（Discontinuous / Overset / Wrapping）。"))
        box = QGroupBox("Analysis options")
        form = QVBoxLayout(box)
        self.chk_disc = QCheckBox("Rotate (Discontinuous mesh)")
        self.chk_overset = QCheckBox("Rotate, move (Overset mesh)")
        self.chk_wrap = QCheckBox("Wrapping")
        form.addWidget(self.chk_disc)
        form.addWidget(self.chk_overset)
        form.addWidget(self.chk_wrap)
        v.addWidget(box)
        box2 = QGroupBox("Part flags (main.xml)")
        f2 = QFormLayout(box2)
        self.ed_expand = QComboBox(); self.ed_expand.addItems(["true", "false"])
        self.ed_expand_disc = QComboBox(); self.ed_expand_disc.addItems(["true", "false"])
        self.ed_group = QComboBox(); self.ed_group.addItems(["true", "false"])
        self.ed_visible = QComboBox(); self.ed_visible.addItems(["true", "false"])
        f2.addRow("expand", self.ed_expand)
        f2.addRow("expand_discontinuous", self.ed_expand_disc)
        f2.addRow("group_part", self.ed_group)
        f2.addRow("visible", self.ed_visible)
        v.addWidget(box2)
        self.lab = QLabel()
        self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        v.addStretch(1)

    def load(self, ctx: dict) -> None:
        pc = ctx.setdefault("session", {}).setdefault("parts_control", {})
        self.chk_disc.setChecked(bool(pc.get("discontinuous")))
        self.chk_overset.setChecked(bool(pc.get("overset")))
        self.chk_wrap.setChecked(bool(pc.get("wrapping")))
        part = _first_part(ctx.get("xml"))
        if part is not None:
            for cb, tag in (
                (self.ed_expand, "expand"),
                (self.ed_expand_disc, "expand_discontinuous"),
                (self.ed_group, "group_part"),
                (self.ed_visible, "visible"),
            ):
                _set_combo_data(cb, part.findtext(tag, "false") or "false")
            self.lab.setText(f"Part name: {part.findtext('name', '')}")
        else:
            self.lab.setText("未找到 main.xml / part")

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["parts_control"] = {
            "discontinuous": self.chk_disc.isChecked(),
            "overset": self.chk_overset.isChecked(),
            "wrapping": self.chk_wrap.isChecked(),
            "expand": self.ed_expand.currentText(),
            "expand_discontinuous": self.ed_expand_disc.currentText(),
            "group_part": self.ed_group.currentText(),
            "visible": self.ed_visible.currentText(),
        }
        part = _first_part(ctx.get("xml"))
        if part is not None:
            for tag, cb in (
                ("expand", self.ed_expand),
                ("expand_discontinuous", self.ed_expand_disc),
                ("group_part", self.ed_group),
                ("visible", self.ed_visible),
            ):
                el = part.find(tag)
                if el is not None:
                    el.text = cb.currentText()
            ctx["xml_dirty"] = True
        return True


class ImportPartBody(_Body):
    title = "Import Part File"
    min_size = (560, 480)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[File] – [Import Part File]"))
        form = QFormLayout()
        self.cb_type = QComboBox()
        for label, data in (
            ("CAD (XT / STEP / CATIA / …)", "cad"),
            ("Patch (STL / MDL / …)", "patch"),
            ("OCT", "oct"),
            ("GPH / PRE / CGNS", "gph"),
            ("VIEW", "view"),
            ("Property (PRP)", "prp"),
            ("Project XML", "xml"),
        ):
            self.cb_type.addItem(label, data)
        self.ed_path = QLineEdit()
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.ed_path, 1)
        row.addWidget(btn)
        wrap = QWidget(); wrap.setLayout(row)
        form.addRow("File type", self.cb_type)
        form.addRow("File", wrap)
        v.addLayout(form)

        tabs = QTabWidget()
        # CAD options from xenv
        cad_w = QWidget()
        cad_f = QFormLayout(cad_w)
        self.cad_widgets: dict[str, QComboBox | QLineEdit] = {}
        for key, choices in (
            ("CAD_Import_TYPE", None),
            ("CAD_LIBRARY", None),
            ("USE_STEP_ASSISTANT", ("true", "false")),
            ("DELETE_COLORED_CAD_FACE", ("true", "false")),
            ("USE_ANCESTRAL_NAME", ("true", "false")),
            ("SEPARATE_DUPLICATE_SOLID", ("true", "false")),
            ("IGNORE_CAD_FACE_NAME", ("true", "false")),
            ("DKCT_VERSION", None),
        ):
            if choices:
                w = QComboBox()
                for c in choices:
                    w.addItem(c, c)
            else:
                w = QLineEdit()
            self.cad_widgets[key] = w
            cad_f.addRow(key, w)
        tabs.addTab(cad_w, "CAD options (xenv)")
        self.info = QTextEdit(); self.info.setReadOnly(True)
        tabs.addTab(self.info, "Project status")
        v.addWidget(tabs, 1)

    def _browse(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Import Part File", "")
        if path:
            self.ed_path.setText(path)

    def load(self, ctx: dict) -> None:
        xenv = ctx.get("xenv")
        if xenv:
            for key, w in self.cad_widgets.items():
                val = xenv.get("CAD", key, "") or ""
                if isinstance(w, QComboBox):
                    _set_combo_data(w, val)
                else:
                    w.setText(val)
        lines = ["已加载成员："]
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            paths = info.get("paths") or {}
            lines.append(
                f"  {g}: part={bool(paths.get('part'))} "
                f"oct={bool(paths.get('oct'))} gph={bool(paths.get('gph'))}")
        self.info.setPlainText("\n".join(lines))
        sess = ctx.setdefault("session", {}).setdefault("import_part", {})
        if sess.get("path"):
            self.ed_path.setText(sess["path"])
        if sess.get("type"):
            _set_combo_data(self.cb_type, sess["type"])

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["import_part"] = {
            "type": self.cb_type.currentData(),
            "path": self.ed_path.text().strip(),
        }
        xenv = ctx.get("xenv")
        if xenv:
            for key, w in self.cad_widgets.items():
                val = w.currentData() if isinstance(w, QComboBox) else w.text().strip()
                pphxml.set_xenv_value(xenv, "CAD", key, str(val))
            ctx["xenv_dirty"] = True
        return True


class CreatePartsBody(_Body):
    title = "Create Parts"
    min_size = (560, 520)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Edit] – [Create Parts]\n"
            "参数可保存；实体写入需 Parasolid / scFLOWpre。"))
        self.tabs = QTabWidget()
        self._shapes: dict[str, dict] = {}
        self.tabs.addTab(self._make_cuboid(), "Cuboid")
        self.tabs.addTab(self._make_cylinder(), "Cylinder")
        self.tabs.addTab(self._make_sphere(), "Sphere")
        self.tabs.addTab(self._make_rect(), "Rectangle")
        v.addWidget(self.tabs, 1)
        self.chk_fluid = QCheckBox("Register as fluid region")
        v.addWidget(self.chk_fluid)
        self.lab = QLabel()
        self.lab.setWordWrap(True)
        v.addWidget(self.lab)

    def _xyz(self, prefix: str) -> dict:
        d = {}
        for ax in "xyz":
            d[ax] = _spin_f(6, -1e9, 1e9, 0.0)
        return d

    def _make_cuboid(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        name = QLineEdit("Cuboid1")
        pos = self._xyz("p"); size = self._xyz("s")
        for ax in "xyz":
            size[ax].setValue(1.0)
        ext = QCheckBox("Extend surroundings")
        ext_len = _spin_f(6, 0, 1e9, 0.0)
        f.addRow("Part name", name)
        f.addRow("Position X", pos["x"]); f.addRow("Position Y", pos["y"]); f.addRow("Position Z", pos["z"])
        f.addRow("Size X", size["x"]); f.addRow("Size Y", size["y"]); f.addRow("Size Z", size["z"])
        f.addRow(ext); f.addRow("Extend length", ext_len)
        self._shapes["Cuboid"] = {
            "name": name, "pos": pos, "size": size, "ext": ext, "ext_len": ext_len}
        return w

    def _make_cylinder(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        name = QLineEdit("Cylinder1")
        bot = self._xyz("b")
        h = _spin_f(6, 0, 1e9, 1.0); r = _spin_f(6, 0, 1e9, 0.5)
        direc = QComboBox(); direc.addItems(["X direction", "Y direction", "Z direction"])
        f.addRow("Part name", name)
        f.addRow("Bottom center X", bot["x"]); f.addRow("Y", bot["y"]); f.addRow("Z", bot["z"])
        f.addRow("Height", h); f.addRow("Radius", r); f.addRow("Direction", direc)
        self._shapes["Cylinder"] = {
            "name": name, "bot": bot, "h": h, "r": r, "dir": direc}
        return w

    def _make_sphere(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        name = QLineEdit("Sphere1")
        c = self._xyz("c"); r = _spin_f(6, 0, 1e9, 0.5)
        seam = QCheckBox("Add seam line")
        f.addRow("Part name", name)
        f.addRow("Center X", c["x"]); f.addRow("Y", c["y"]); f.addRow("Z", c["z"])
        f.addRow("Radius", r); f.addRow(seam)
        self._shapes["Sphere"] = {"name": name, "c": c, "r": r, "seam": seam}
        return w

    def _make_rect(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        name = QLineEdit("Rectangle1")
        axis = QComboBox(); axis.addItems(["X", "Y", "Z"])
        pos = self._xyz("p"); size = self._xyz("s")
        for ax in "xyz":
            size[ax].setValue(1.0)
        cross = QCheckBox("Create as a cross section")
        f.addRow("Part name", name)
        f.addRow("Perpendicular to axis", axis)
        f.addRow("Position X", pos["x"]); f.addRow("Y", pos["y"]); f.addRow("Z", pos["z"])
        f.addRow("Size X", size["x"]); f.addRow("Y", size["y"]); f.addRow("Z", size["z"])
        f.addRow(cross)
        self._shapes["Rectangle"] = {
            "name": name, "axis": axis, "pos": pos, "size": size, "cross": cross}
        return w

    def load(self, ctx: dict) -> None:
        draft = ctx.setdefault("session", {}).get("create_parts") or {}
        shape = draft.get("shape", "Cuboid")
        idx = {"Cuboid": 0, "Cylinder": 1, "Sphere": 2, "Rectangle": 3}.get(shape, 0)
        self.tabs.setCurrentIndex(idx)
        self.chk_fluid.setChecked(bool(draft.get("fluid")))
        names = []
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None:
                for p in parts.iter("part"):
                    n = p.findtext("name")
                    if n:
                        names.append(n)
        self.lab.setText("Existing parts: " + (", ".join(names) if names else "(none)"))

    def apply(self, ctx: dict) -> bool:
        shape = self.tabs.tabText(self.tabs.currentIndex())
        d = self._shapes[shape]
        data = {"shape": shape, "fluid": self.chk_fluid.isChecked()}
        if shape == "Cuboid":
            data.update({
                "name": d["name"].text().strip(),
                "position": tuple(d["pos"][a].value() for a in "xyz"),
                "size": tuple(d["size"][a].value() for a in "xyz"),
                "extend": d["ext"].isChecked(),
                "extend_len": d["ext_len"].value(),
            })
        elif shape == "Cylinder":
            data.update({
                "name": d["name"].text().strip(),
                "bottom": tuple(d["bot"][a].value() for a in "xyz"),
                "height": d["h"].value(), "radius": d["r"].value(),
                "direction": d["dir"].currentText(),
            })
        elif shape == "Sphere":
            data.update({
                "name": d["name"].text().strip(),
                "center": tuple(d["c"][a].value() for a in "xyz"),
                "radius": d["r"].value(), "seam": d["seam"].isChecked(),
            })
        else:
            data.update({
                "name": d["name"].text().strip(),
                "axis": d["axis"].currentText(),
                "position": tuple(d["pos"][a].value() for a in "xyz"),
                "size": tuple(d["size"][a].value() for a in "xyz"),
                "cross_section": d["cross"].isChecked(),
            })
        ctx.setdefault("session", {})["create_parts"] = data
        return True


class ModifyPartsBody(_Body):
    title = "Modify Parts"
    min_size = (580, 520)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Edit] – [Modify Parts] — 容差写入 xenv；操作列表为会话设置。"))
        tabs = QTabWidget()
        # Data cleaning ops
        ops_w = QWidget(); ov = QVBoxLayout(ops_w)
        self.ops = {}
        for label, key in (
            ("Unite solids", "unite"),
            ("Remove overlap", "remove_overlap"),
            ("Sew sheets", "sew"),
            ("Remove tiny edges / faces", "tiny"),
            ("Data cleaning (auto)", "clean"),
        ):
            cb = QCheckBox(label)
            self.ops[key] = cb
            ov.addWidget(cb)
        ov.addStretch(1)
        tabs.addTab(ops_w, "Operations")

        tol_w = QWidget(); form = QFormLayout(tol_w)
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
            form.addRow(label, sp)
            self.sp[key] = sp
        self.tiny_rel = _bool_combo()
        self.tiny_den = _spin_f(0, 1, 1e9, 1000)
        self.tiny_abs = _spin_f(12, 0, 1, 1e-6)
        self.ridge_ang = _spin_f(2, 0, 180, 45)
        form.addRow("Tiny relative flag", self.tiny_rel)
        form.addRow("Tiny relative denom.", self.tiny_den)
        form.addRow("Tiny absolute size", self.tiny_abs)
        form.addRow("Ridge angle (deg)", self.ridge_ang)
        tabs.addTab(tol_w, "Tolerance")
        v.addWidget(tabs, 1)

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {}).setdefault("modify_parts", {})
        for k, cb in self.ops.items():
            cb.setChecked(bool(sess.get(k)))
        xenv = ctx.get("xenv")
        if not xenv:
            return
        for k, sp in self.sp.items():
            try:
                sp.setValue(float(xenv.get("TOLERANCE", k, "0") or 0))
            except ValueError:
                pass
        _set_combo_data(self.tiny_rel, xenv.get("TINYFACE", "RELATIVE_FLAG", "true") or "true")
        try:
            self.tiny_den.setValue(float(xenv.get("TINYFACE", "RELATIVE_DENOMINATOR", "1000") or 1000))
            self.tiny_abs.setValue(float(xenv.get("TINYFACE", "ABSOLUTE_SIZE", "0") or 0))
            self.ridge_ang.setValue(float(xenv.get("RIDGE", "ANGLE", "45") or 45))
        except ValueError:
            pass

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["modify_parts"] = {
            k: cb.isChecked() for k, cb in self.ops.items()}
        xenv = ctx.get("xenv")
        if not xenv:
            return True
        for k, sp in self.sp.items():
            pphxml.set_xenv_value(xenv, "TOLERANCE", k, _fmt_float(sp.value()))
        pphxml.set_xenv_value(xenv, "TINYFACE", "RELATIVE_FLAG", self.tiny_rel.currentData())
        pphxml.set_xenv_value(xenv, "TINYFACE", "RELATIVE_DENOMINATOR",
                              _fmt_float(self.tiny_den.value()))
        pphxml.set_xenv_value(xenv, "TINYFACE", "ABSOLUTE_SIZE",
                              _fmt_float(self.tiny_abs.value()))
        pphxml.set_xenv_value(xenv, "RIDGE", "ANGLE", _fmt_float(self.ridge_ang.value()))
        ctx["xenv_dirty"] = True
        return True


class MesherFaceterBody(_Body):
    title = "Mesher/Faceter Setting"
    min_size = (560, 560)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Condition] – [Mesher/Faceter Setting]"))
        tabs = QTabWidget()
        # Mesher
        m = QWidget(); mf = QFormLayout(m)
        self.cb_mesher = QComboBox()
        self.cb_mesher.addItem("Polyhedral", "0")
        self.cb_mesher.addItem("Voxel Fitting", "1")
        self.cb_surf = QComboBox()
        self.cb_surf.addItem("Facet-based", "0")
        self.cb_surf.addItem("Solid-based", "1")
        self.cb_rough = _bool_combo()
        self.sp_init = QSpinBox(); self.sp_init.setRange(0, 2_000_000_000)
        mf.addRow("Mesher", self.cb_mesher)
        mf.addRow("Surface mesher", self.cb_surf)
        mf.addRow("Rough poly when voxel", self.cb_rough)
        mf.addRow("Initial divisions (voxel)", self.sp_init)
        tabs.addTab(m, "Mesher")
        # Facet simple
        f = QWidget(); ff = QFormLayout(f)
        self.cb_simple = _bool_combo()
        self.cb_use_facetter = _bool_combo()
        self.sp_chord = _spin_f(6, 0, 1e6, 1)
        self.sp_ang = _spin_f(3, 0, 180, 5)
        self.sp_width = _spin_f(6, 0, 1e6, 5)
        self.cb_abs = _bool_combo()
        ff.addRow("Use simple setting", self.cb_simple)
        ff.addRow("Use facetter", self.cb_use_facetter)
        ff.addRow("Chord tolerance", self.sp_chord)
        ff.addRow("Max angle", self.sp_ang)
        ff.addRow("Max width", self.sp_width)
        ff.addRow("Use absolute value", self.cb_abs)
        tabs.addTab(f, "Facet (simple)")
        # Facet detail / solid-base
        d = QWidget(); df = QFormLayout(d)
        self.sp_d_chord_ang = _spin_f(3, 0, 180, 10)
        self.sp_d_surf_ang = _spin_f(3, 0, 180, 10)
        self.sp_sb_len = _spin_f(6, 0, 10, 0.05)
        self.sp_sb_ang = _spin_f(3, 0, 180, 10)
        self.sp_sb_oct_len = _spin_f(6, 0, 10, 0.25)
        self.sp_intersect = QSpinBox(); self.sp_intersect.setRange(0, 64)
        df.addRow("Detail chord angle", self.sp_d_chord_ang)
        df.addRow("Detail surf angle", self.sp_d_surf_ang)
        df.addRow("Solid-base length factor", self.sp_sb_len)
        df.addRow("Solid-base min angle", self.sp_sb_ang)
        df.addRow("Solid-base len (octree)", self.sp_sb_oct_len)
        df.addRow("Intersection detect depth", self.sp_intersect)
        tabs.addTab(d, "Facet (detail)")
        v.addWidget(tabs, 1)

    def load(self, ctx: dict) -> None:
        xenv = ctx.get("xenv")
        if not xenv:
            return
        _set_combo_data(self.cb_mesher, xenv.get("MESH", "MESHER", "1") or "1")
        _set_combo_data(self.cb_surf, xenv.get("MESH", "SURF_MESHER", "0") or "0")
        _set_combo_data(self.cb_rough,
                        xenv.get("MESH_COMMON", "USE_ROUGH_POLY_WHEN_VOXEL_MESHING", "false")
                        or "false")
        try:
            self.sp_init.setValue(int(float(
                xenv.get("MESH_COMMON", "NUMBER_OF_INITIAL_DIVISION_WHEN_VOXEL_MESHING",
                         "15000000") or 15000000)))
        except ValueError:
            pass
        _set_combo_data(self.cb_simple, xenv.get("FACET", "USE_SIMPLE_SETTING", "true") or "true")
        _set_combo_data(self.cb_use_facetter, xenv.get("FACET", "USE_FACETTER", "true") or "true")
        _set_combo_data(self.cb_abs, xenv.get("FACET", "USE_ABSOLUTE_VALUE", "false") or "false")
        for sp, key in (
            (self.sp_chord, "SIMPLE_CHORD_TOLERANCE"),
            (self.sp_ang, "SIMPLE_MAX_ANGLE"),
            (self.sp_width, "SIMPLE_MAX_WIDTH"),
            (self.sp_d_chord_ang, "DETAIL_CHORD_ANGLE"),
            (self.sp_d_surf_ang, "DETAIL_SURF_ANGLE"),
            (self.sp_sb_len, "SOLID_BASE_LENGTH_FACTOR"),
            (self.sp_sb_ang, "SOLID_BASE_MINIMUM_ANGLE"),
            (self.sp_sb_oct_len, "SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE"),
        ):
            try:
                sp.setValue(float(xenv.get("FACET", key, "0") or 0))
            except ValueError:
                pass
        try:
            self.sp_intersect.setValue(int(float(
                xenv.get("FACET", "INTERSECTION_DETECTION_DEPTH", "12") or 12)))
        except ValueError:
            pass

    def apply(self, ctx: dict) -> bool:
        xenv = ctx.get("xenv")
        if not xenv:
            return False
        pphxml.set_xenv_value(xenv, "MESH", "MESHER", self.cb_mesher.currentData())
        pphxml.set_xenv_value(xenv, "MESH", "SURF_MESHER", self.cb_surf.currentData())
        pphxml.set_xenv_value(xenv, "MESH_COMMON", "USE_ROUGH_POLY_WHEN_VOXEL_MESHING",
                              self.cb_rough.currentData())
        pphxml.set_xenv_value(xenv, "MESH_COMMON",
                              "NUMBER_OF_INITIAL_DIVISION_WHEN_VOXEL_MESHING",
                              str(self.sp_init.value()))
        pairs = (
            ("USE_SIMPLE_SETTING", self.cb_simple.currentData()),
            ("USE_FACETTER", self.cb_use_facetter.currentData()),
            ("USE_ABSOLUTE_VALUE", self.cb_abs.currentData()),
            ("SIMPLE_CHORD_TOLERANCE", _fmt_float(self.sp_chord.value())),
            ("SIMPLE_MAX_ANGLE", _fmt_float(self.sp_ang.value())),
            ("SIMPLE_MAX_WIDTH", _fmt_float(self.sp_width.value())),
            ("DETAIL_CHORD_ANGLE", _fmt_float(self.sp_d_chord_ang.value())),
            ("DETAIL_SURF_ANGLE", _fmt_float(self.sp_d_surf_ang.value())),
            ("SOLID_BASE_LENGTH_FACTOR", _fmt_float(self.sp_sb_len.value())),
            ("SOLID_BASE_MINIMUM_ANGLE", _fmt_float(self.sp_sb_ang.value())),
            ("SOLID_BASE_LENGTH_FACTOR_FOR_OCTREE",
             _fmt_float(self.sp_sb_oct_len.value())),
            ("INTERSECTION_DETECTION_DEPTH", str(self.sp_intersect.value())),
        )
        for k, val in pairs:
            pphxml.set_xenv_value(xenv, "FACET", k, val)
        ctx["xenv_dirty"] = True
        return True


class RegisterRegionBody(_Body):
    title = "Register Region"
    min_size = (640, 520)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Edit] – [Register Region]\n"
            "浏览已注册区域；新建区域会话草稿（写入 CAD 需 Pre）。"))
        self.tabs = QTabWidget()
        self.lists: dict[str, QTreeWidget] = {}
        for cat, title in (
            ("face", "Surface Region"),
            ("volume", "Volume Region"),
            ("fluid", "Fluid Region"),
            ("numerical", "Numerical Region"),
            ("cross_section", "Cross Section"),
            ("mdl", "MDL Surface"),
        ):
            tw = QTreeWidget()
            tw.setHeaderLabels(["Name", "Property / Part"])
            tw.setColumnWidth(0, 180)
            self.lists[cat] = tw
            self.tabs.addTab(tw, title)
        v.addWidget(self.tabs, 1)
        form = QFormLayout()
        self.ed_name = QLineEdit()
        self.cb_side = QComboBox()
        self.cb_side.addItems(["Both", "Front", "Back"])
        self.cb_target = QComboBox()
        self.cb_target.addItems([
            "Selected face", "Surface between virtual parts",
            "Surface of specified virtual part", "All faces of part",
        ])
        form.addRow("New region name", self.ed_name)
        form.addRow("Side", self.cb_side)
        form.addRow("Target", self.cb_target)
        v.addLayout(form)

    def load(self, ctx: dict) -> None:
        for tw in self.lists.values():
            tw.clear()
        xml = ctx.get("xml")
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat_el in list(regs):
                    tw = self.lists.get(cat_el.tag)
                    if tw is None:
                        continue
                    for r in cat_el.findall("region"):
                        tw.addTopLevelItem(QTreeWidgetItem([
                            r.findtext("name", "") or "?",
                            f"{r.findtext('property', '') or ''} / "
                            f"{r.findtext('spart', '') or ''}",
                        ]))
        mdl = self.lists["mdl"]
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            part = info.get("part")
            if part is None:
                continue
            root = QTreeWidgetItem([g, "MDL"])
            mdl.addTopLevelItem(root)
            for r in getattr(part, "surface_regions", None) or []:
                root.addChild(QTreeWidgetItem([
                    getattr(r, "name", str(r)),
                    f"frid={getattr(r, 'index', '')}",
                ]))
            root.setExpanded(True)
        draft = ctx.setdefault("session", {}).get("register_region") or {}
        if draft.get("name"):
            self.ed_name.setText(draft["name"])

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["register_region"] = {
            "name": self.ed_name.text().strip(),
            "side": self.cb_side.currentText(),
            "target": self.cb_target.currentText(),
            "tab": self.tabs.tabText(self.tabs.currentIndex()),
        }
        return True


class NonSolidBody(_Body):
    title = "Create Non-Solid Part"

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Edit] – [Create Non-Solid Part]"))
        form = QFormLayout()
        self.cb_kind = QComboBox()
        self.cb_kind.addItems([
            "Group Part",
            "Coordinates-Specified Part",
            "Surface Region–Derived Sheet",
        ])
        self.ed_name = QLineEdit("NonSolid1")
        form.addRow("Type", self.cb_kind)
        form.addRow("Name", self.ed_name)
        v.addLayout(form)
        self.lab = QLabel(); self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        v.addStretch(1)

    def load(self, ctx: dict) -> None:
        draft = ctx.setdefault("session", {}).get("non_solid") or {}
        if draft.get("kind"):
            i = self.cb_kind.findText(draft["kind"])
            if i >= 0:
                self.cb_kind.setCurrentIndex(i)
        if draft.get("name"):
            self.ed_name.setText(draft["name"])
        n = 0
        xml = ctx.get("xml")
        if xml is not None:
            parts = xml.section("parts")
            if parts is not None and parts.find("face_region_derived_sheets") is not None:
                n = len(list(parts.find("face_region_derived_sheets")))
        self.lab.setText(f"face_region_derived_sheets entries: {n}")

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["non_solid"] = {
            "kind": self.cb_kind.currentText(),
            "name": self.ed_name.text().strip(),
        }
        return True


class PartMaterialBody(_Body):
    title = "Part Material"
    min_size = (600, 480)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Condition] – [Part Material]"))
        self.tabs = QTabWidget()
        self.prp_tree = QTreeWidget()
        self.prp_tree.setHeaderLabels(["Key", "Name"])
        self.reg_tree = QTreeWidget()
        self.reg_tree.setHeaderLabels(["Region", "Material / Attribute"])
        self.tabs.addTab(self.prp_tree, "Property DB")
        self.tabs.addTab(self.reg_tree, "Region ↔ Material")
        v.addWidget(self.tabs, 1)
        form = QFormLayout()
        self.ed_region = QLineEdit()
        self.ed_mat = QLineEdit()
        self.cb_attr = QComboBox()
        self.cb_attr.addItems(["Fluid", "Solid", "Obstacle", "(keep)"])
        form.addRow("Assign region", self.ed_region)
        form.addRow("Material key", self.ed_mat)
        form.addRow("Attribute", self.cb_attr)
        v.addLayout(form)

    def load(self, ctx: dict) -> None:
        self.prp_tree.clear(); self.reg_tree.clear()
        prp = ctx.get("prp")
        if prp is not None:
            for g in prp.groups:
                self.prp_tree.addTopLevelItem(QTreeWidgetItem([
                    g.findtext("key") or "", g.findtext("name") or ""]))
        xml = ctx.get("xml")
        if xml is not None:
            regs = xml.section("regions")
            if regs is not None:
                for cat in list(regs):
                    for r in cat.findall("region"):
                        self.reg_tree.addTopLevelItem(QTreeWidgetItem([
                            f"{cat.tag}/{r.findtext('name', '')}",
                            r.findtext("property", "") or "",
                        ]))
        draft = ctx.setdefault("session", {}).get("part_material") or {}
        self.ed_region.setText(draft.get("region", ""))
        self.ed_mat.setText(draft.get("material", ""))

    def apply(self, ctx: dict) -> bool:
        region = self.ed_region.text().strip()
        mat = self.ed_mat.text().strip()
        ctx.setdefault("session", {})["part_material"] = {
            "region": region, "material": mat,
            "attribute": self.cb_attr.currentText(),
        }
        if not region or not mat:
            return True
        xml = ctx.get("xml")
        if xml is None:
            return True
        regs = xml.section("regions")
        if regs is None:
            return True
        for cat in list(regs):
            for r in cat.findall("region"):
                if (r.findtext("name") or "") == region:
                    el = r.find("property")
                    if el is not None:
                        el.text = mat
                        ctx["xml_dirty"] = True
        return True


class ConditionsBody(_Body):
    title = "Conditions"
    min_size = (640, 520)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Condition] – [Conditions]\n"
            "只读浏览 + 会话备注；完整向导请在 scFLOWpre 编辑。"))
        split = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Condition", "Type"])
        self.tree.itemSelectionChanged.connect(self._on_sel)
        self.detail = QTextEdit(); self.detail.setReadOnly(True)
        split.addWidget(self.tree, 2)
        split.addWidget(self.detail, 3)
        v.addLayout(split, 1)
        self.ed_note = QLineEdit()
        form = QFormLayout()
        form.addRow("Session note", self.ed_note)
        v.addLayout(form)
        self._summaries: list[dict] = []

    def _on_sel(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        idx = self.tree.indexOfTopLevelItem(items[0])
        if 0 <= idx < len(self._summaries):
            sm = self._summaries[idx]
            regs = sm.get("regions") or []
            self.detail.setPlainText(
                f"name: {sm.get('name')}\n"
                f"type: {sm.get('type')}\n"
                f"regions:\n  " + "\n  ".join(f"{a}: {b}" for a, b in regs))

    def load(self, ctx: dict) -> None:
        self.tree.clear(); self._summaries.clear(); self.detail.clear()
        xml = ctx.get("xml")
        if xml is None:
            return
        for cond in xml.conditions():
            sm = xml.condition_summary(cond)
            self._summaries.append(sm)
            self.tree.addTopLevelItem(QTreeWidgetItem([
                sm.get("name") or "(unnamed)", sm.get("type") or ""]))
        self.ed_note.setText(
            (ctx.setdefault("session", {}).get("conditions") or {}).get("note", ""))

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["conditions"] = {
            "note": self.ed_note.text().strip()}
        return True


class BuildAnalysisModelBody(_Body):
    title = "Build Analysis Model"
    min_size = (560, 420)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note(
            "[Execute] – [Build Analysis Model]\n"
            "识别闭体并生成分析模型。本对话框显示状态；执行请用 scFLOWpre。"))
        self.chk_wizard = QCheckBox("Show Analysis Model Wizard")
        self.chk_report = QCheckBox("Show error report after build")
        v.addWidget(self.chk_wizard)
        v.addWidget(self.chk_report)
        self.info = QTextEdit(); self.info.setReadOnly(True)
        v.addWidget(self.info, 1)

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {}).setdefault("build_am", {})
        self.chk_wizard.setChecked(bool(sess.get("wizard")))
        self.chk_report.setChecked(bool(sess.get("report", True)))
        lines = []
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            paths = info.get("paths") or {}
            st = (info.get("status") or {}).get("geometry") or {}
            lines.append(f"[{g}]")
            lines.append(f"  MDL={'yes' if paths.get('part') else 'no'}  "
                         f"OCT={'yes' if paths.get('oct') else 'no'}  "
                         f"GPH={'yes' if paths.get('gph') else 'no'}")
            for k, val in st.items():
                lines.append(f"  {k}: {val}")
        self.info.setPlainText("\n".join(lines) if lines else "No meshing groups.")

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["build_am"] = {
            "wizard": self.chk_wizard.isChecked(),
            "report": self.chk_report.isChecked(),
        }
        return True


class OctreeParamBody(_Body):
    title = "Octree Parameter"
    min_size = (580, 560)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Condition] – [Octree Parameter]"))
        mode = QGroupBox("Density mode")
        mv = QVBoxLayout(mode)
        self.rb_target = QRadioButton("Target number of elements")
        self.rb_min = QRadioButton("Minimum size")
        self.rb_oct = QRadioButton("Octant parameter")
        self.rb_oct.setChecked(True)
        self.sp_target = QSpinBox(); self.sp_target.setRange(1, 2_000_000_000)
        self.sp_target.setValue(1_000_000)
        self.sp_min = _spin_f(8, 0, 1e6, 0)
        row1 = QHBoxLayout(); row1.addWidget(self.rb_target); row1.addWidget(self.sp_target)
        row2 = QHBoxLayout(); row2.addWidget(self.rb_min); row2.addWidget(self.sp_min)
        mv.addLayout(row1); mv.addLayout(row2); mv.addWidget(self.rb_oct)
        v.addWidget(mode)
        tabs = QTabWidget()
        d = QWidget(); df = QFormLayout(d)
        self.sp_flen = _spin_f(6, 0, 1e6, 1)
        self.sp_fang = _spin_f(3, 0, 180, 5)
        self.sp_fwidth = _spin_f(6, 0, 1e6, 5)
        self.cb_refine = QComboBox()
        for i in range(6):
            self.cb_refine.addItem(str(i), str(i))
        self.sp_oct_itr = QSpinBox(); self.sp_oct_itr.setRange(0, 100)
        self.cb_oct_flag = _bool_combo()
        self.cb_each = _bool_combo()
        df.addRow("Facet length factor", self.sp_flen)
        df.addRow("Facet angle", self.sp_fang)
        df.addRow("Facet max width factor", self.sp_fwidth)
        df.addRow("Specify each region", self.cb_each)
        df.addRow("Voxel oct refine type", self.cb_refine)
        df.addRow("OCT length param flag", self.cb_oct_flag)
        df.addRow("OCT length param ITR", self.sp_oct_itr)
        tabs.addTab(d, "Detail (xenv)")
        self.result = QTextEdit(); self.result.setReadOnly(True)
        tabs.addTab(self.result, "OCT result")
        v.addWidget(tabs, 1)

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {}).setdefault("octree_param", {})
        mode = sess.get("mode", "octant")
        self.rb_target.setChecked(mode == "target")
        self.rb_min.setChecked(mode == "min")
        self.rb_oct.setChecked(mode == "octant")
        if "target" in sess:
            self.sp_target.setValue(int(sess["target"]))
        if "min_size" in sess:
            self.sp_min.setValue(float(sess["min_size"]))
        xenv = ctx.get("xenv")
        if xenv:
            for sp, sec, key in (
                (self.sp_flen, "OCT_MESH", "FACET_LENGTH_FACTOR"),
                (self.sp_fang, "OCT_MESH", "FACET_ANGLE"),
                (self.sp_fwidth, "OCT_MESH", "FACET_MAX_WIDTH_FACTOR"),
            ):
                try:
                    sp.setValue(float(xenv.get(sec, key, "0") or 0))
                except ValueError:
                    pass
            _set_combo_data(self.cb_refine,
                            xenv.get("OCT_MESH", "VOXEL_OCT_REFINE_TYPE", "3") or "3")
            _set_combo_data(self.cb_each,
                            xenv.get("OCT_MESH", "FACET_SPECIFY_EACH_REGION", "false")
                            or "false")
            _set_combo_data(self.cb_oct_flag,
                            xenv.get("FACET", "OCT_LENGTH_PARAM_FLAG", "true") or "true")
            try:
                self.sp_oct_itr.setValue(int(float(
                    xenv.get("FACET", "OCT_LENGTH_PARAM_ITR", "5") or 5)))
            except ValueError:
                pass
        lines = []
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            st = (info.get("status") or {}).get("octree") or {}
            if st:
                lines.append(f"[{g}]")
                for k, val in st.items():
                    lines.append(f"  {k}: {val}")
        self.result.setPlainText("\n".join(lines) if lines else "No OCT summary.")

    def apply(self, ctx: dict) -> bool:
        mode = ("target" if self.rb_target.isChecked()
                else "min" if self.rb_min.isChecked() else "octant")
        ctx.setdefault("session", {})["octree_param"] = {
            "mode": mode, "target": self.sp_target.value(),
            "min_size": self.sp_min.value(),
        }
        xenv = ctx.get("xenv")
        if not xenv:
            return True
        pphxml.set_xenv_value(xenv, "OCT_MESH", "FACET_LENGTH_FACTOR",
                              _fmt_float(self.sp_flen.value()))
        pphxml.set_xenv_value(xenv, "OCT_MESH", "FACET_ANGLE",
                              _fmt_float(self.sp_fang.value()))
        pphxml.set_xenv_value(xenv, "OCT_MESH", "FACET_MAX_WIDTH_FACTOR",
                              _fmt_float(self.sp_fwidth.value()))
        pphxml.set_xenv_value(xenv, "OCT_MESH", "FACET_SPECIFY_EACH_REGION",
                              self.cb_each.currentData())
        pphxml.set_xenv_value(xenv, "OCT_MESH", "VOXEL_OCT_REFINE_TYPE",
                              self.cb_refine.currentData())
        pphxml.set_xenv_value(xenv, "FACET", "OCT_LENGTH_PARAM_FLAG",
                              self.cb_oct_flag.currentData())
        pphxml.set_xenv_value(xenv, "FACET", "OCT_LENGTH_PARAM_ITR",
                              str(self.sp_oct_itr.value()))
        ctx["xenv_dirty"] = True
        return True


class MeshParamBody(_Body):
    title = "Mesh Parameter"
    min_size = (580, 520)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(_note("[Condition] – [Mesh Parameter]"))
        tabs = QTabWidget()
        p = QWidget(); pf = QFormLayout(p)
        self.sp_prism_t = _spin_f(4, 0, 100, 0.3)
        self.sp_prism_n = QSpinBox(); self.sp_prism_n.setRange(0, 100); self.sp_prism_n.setValue(3)
        self.cb_timing = QComboBox()
        self.cb_timing.addItems([
            "After volume meshing", "Before volume meshing",
            "After polyhedral conversion",
        ])
        pf.addRow("Prism thickness coeff.", self.sp_prism_t)
        pf.addRow("Number of prism layers", self.sp_prism_n)
        pf.addRow("Timing of prism insertion", self.cb_timing)
        tabs.addTab(p, "Prism layers")
        o = QWidget(); of = QFormLayout(o)
        self.cb_assign = QComboBox()
        self.cb_assign.addItems(["Ray-tracing", "Wrapping", "Individual"])
        self.cb_smooth = _bool_combo()
        self.cb_adapt = _bool_combo()
        of.addRow("Assign part to voxel mesh", self.cb_assign)
        of.addRow("Smoothing after volume", self.cb_smooth)
        of.addRow("Mesh adaptation", self.cb_adapt)
        tabs.addTab(o, "Other")
        self.result = QTextEdit(); self.result.setReadOnly(True)
        tabs.addTab(self.result, "GPH result")
        v.addWidget(tabs, 1)

    def load(self, ctx: dict) -> None:
        sess = ctx.setdefault("session", {}).setdefault("mesh_param", {})
        if "prism_t" in sess:
            self.sp_prism_t.setValue(float(sess["prism_t"]))
        if "prism_n" in sess:
            self.sp_prism_n.setValue(int(sess["prism_n"]))
        if sess.get("timing"):
            i = self.cb_timing.findText(sess["timing"])
            if i >= 0:
                self.cb_timing.setCurrentIndex(i)
        if sess.get("assign"):
            i = self.cb_assign.findText(sess["assign"])
            if i >= 0:
                self.cb_assign.setCurrentIndex(i)
        _set_combo_data(self.cb_smooth, sess.get("smooth", "true"))
        _set_combo_data(self.cb_adapt, sess.get("adapt", "false"))
        lines = []
        for g, info in sorted((ctx.get("groups_info") or {}).items()):
            st = (info.get("status") or {}).get("mesh") or {}
            if st:
                lines.append(f"[{g}]")
                for k, val in st.items():
                    lines.append(f"  {k}: {val}")
        self.result.setPlainText("\n".join(lines) if lines else "No GPH summary.")

    def apply(self, ctx: dict) -> bool:
        ctx.setdefault("session", {})["mesh_param"] = {
            "prism_t": self.sp_prism_t.value(),
            "prism_n": self.sp_prism_n.value(),
            "timing": self.cb_timing.currentText(),
            "assign": self.cb_assign.currentText(),
            "smooth": self.cb_smooth.currentData(),
            "adapt": self.cb_adapt.currentData(),
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
            "勾选步骤并 OK/Apply 保存计划；本查看器不调用网格器/求解器。"))
        box = QGroupBox("Process")
        bv = QVBoxLayout(box)
        self.chk_bam = QCheckBox("Build Analysis Model")
        self.chk_oct = QCheckBox("Generate Octree for Meshing")
        self.chk_mesh = QCheckBox("Generate Mesh")
        self.chk_files = QCheckBox("Create files (mesh / condition)")
        self.chk_save = QCheckBox("Save project")
        self.chk_solver = QCheckBox("Execute Solver")
        self.chk_bam.setChecked(True)
        self.chk_oct.setChecked(True)
        self.chk_mesh.setChecked(True)
        self.chk_use_api = QCheckBox(
            "使用 scFLOWpre API 构建 Model / Octree / Mesh")
        for w in (self.chk_bam, self.chk_oct, self.chk_mesh,
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
        self.chk_bam.setChecked(ex.get("bam", True))
        self.chk_oct.setChecked(ex.get("oct", True))
        self.chk_mesh.setChecked(ex.get("mesh", True))
        self.chk_files.setChecked(ex.get("files", False))
        self.chk_save.setChecked(ex.get("save", False))
        self.chk_solver.setChecked(ex.get("solver", False))
        self.chk_use_api.setChecked(bool(ex.get("use_api", False)))
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
        ctx.setdefault("session", {})["execute"] = {
            "bam": self.chk_bam.isChecked(),
            "oct": self.chk_oct.isChecked(),
            "mesh": self.chk_mesh.isChecked(),
            "files": self.chk_files.isChecked(),
            "save": self.chk_save.isChecked(),
            "solver": self.chk_solver.isChecked(),
            "mesh_mode": self.cb_mesh_mode.currentText(),
            "use_api": self.chk_use_api.isChecked(),
        }
        return True


BODY_CLASSES: dict[str, type] = {
    "parts_control": PartsControlBody,
    "import_part": ImportPartBody,
    "create_parts": CreatePartsBody,
    "modify_parts": ModifyPartsBody,
    "mesher_faceter": MesherFaceterBody,
    "regions": RegisterRegionBody,
    "non_solid": NonSolidBody,
    "part_material": PartMaterialBody,
    "conditions": ConditionsBody,
    "build_am": BuildAnalysisModelBody,
    "oct_param": OctreeParamBody,
    "mesh_param": MeshParamBody,
    "execute": ExecuteBody,
}

# 兼容旧引用
PANEL_CLASSES = BODY_CLASSES


class NavParamDialog(QDialog):
    """scFLOWpre 风格参数弹出子窗口：滚动内容 + OK / Cancel / Apply。"""

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            Qt.Horizontal, self)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
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
                  groups_info=None, **extra) -> dict:
        ctx = {
            "session": self.session,
            "xenv": xenv,
            "xml": xml,
            "prp": prp,
            "groups_info": groups_info or {},
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
