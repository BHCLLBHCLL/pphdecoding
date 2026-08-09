#!/usr/bin/env python3
"""scFLOWpre [Option] 菜单对话框：Mouse Operation / Unit Conversion / Settings。"""

from __future__ import annotations

from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from option_settings import EnvironmentSettingsDialog  # noqa: F401

# ── mouse icons ────────────────────────────────────────────────────


def mouse_mode_icon(buttons: int, size: int = 18) -> QIcon:
    """buttons: 1 / 2 / 3；绘制简易鼠标示意。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    body = QRectF(3, 2, size - 6, size - 4)
    p.setPen(QPen(QColor(60, 60, 60), 1.2))
    p.setBrush(QBrush(QColor(230, 230, 230)))
    p.drawRoundedRect(body, 4, 4)
    # buttons
    mid_y = body.top() + body.height() * 0.42
    p.drawLine(QPoint(int(body.left() + 2), int(mid_y)),
               QPoint(int(body.right() - 2), int(mid_y)))
    cx = body.center().x()
    p.drawLine(QPoint(int(cx), int(body.top() + 2)),
               QPoint(int(cx), int(mid_y)))
    hot = QColor(70, 130, 220)
    if buttons >= 1:
        p.fillRect(QRectF(body.left() + 1, body.top() + 1,
                           cx - body.left() - 2, mid_y - body.top() - 2), hot)
    if buttons >= 2:
        p.fillRect(QRectF(cx + 1, body.top() + 1,
                           body.right() - cx - 2, mid_y - body.top() - 2),
                    hot)
    if buttons >= 3:
        # wheel / middle highlight
        p.setBrush(QBrush(QColor(40, 90, 180)))
        p.drawEllipse(QRectF(cx - 2, mid_y - 3, 4, 6))
    p.end()
    return QIcon(pm)


# ── Change Mouse Operation ─────────────────────────────────────────

_MOUSE_TYPES = [
    ("CRADLE 3-Button Mode",
     "Move : Middle Button + Right Button\n"
     "Rotate : Middle Button\n"
     "Zoom : Right Button"),
    ("CRADLE 3-Button Mode (CTRL)",
     "Move : CTRL + Left Button\n"
     "Rotate : Left Button\n"
     "Zoom : CTRL + Right Button"),
    ("CRADLE 2-Button Mode",
     "Move : Right Button + Left Button\n"
     "Rotate : Left Button\n"
     "Zoom : Right Button"),
    ("CRADLE 1-Button Mode",
     "Move : SHIFT + Left Button\n"
     "Rotate : Left Button\n"
     "Zoom : CTRL + Left Button"),
]


class ChangeMouseOperationDialog(QDialog):
    """[Option] – [Operation…] → Change Mouse Operation。"""

    def __init__(self, current_type: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Mouse Operation")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(320, 220)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Type :"))
        self.cb_type = QComboBox()
        for name, _desc in _MOUSE_TYPES:
            self.cb_type.addItem(name)
        if current_type:
            i = self.cb_type.findText(current_type)
            if i >= 0:
                self.cb_type.setCurrentIndex(i)
        row.addWidget(self.cb_type, 1)
        v.addLayout(row)
        self.lab_map = QLabel()
        self.lab_map.setWordWrap(True)
        self.lab_map.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lab_map.setMinimumHeight(80)
        self.lab_map.setStyleSheet(
            "border:1px solid #bbb; background:#fafafa; padding:8px;")
        v.addWidget(self.lab_map, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.cb_type.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        i = self.cb_type.currentIndex()
        self.lab_map.setText(_MOUSE_TYPES[i][1] if i >= 0 else "")

    def selected_type(self) -> str:
        return self.cb_type.currentText()


# ── Unit Conversion ────────────────────────────────────────────────

_LENGTH = [
    ("m", 1.0), ("mm", 1e-3), ("cm", 1e-2), ("km", 1e3),
    ("in", 0.0254), ("ft", 0.3048),
]
_TEMP = [("C", "C"), ("F", "F"), ("K", "K")]
_PRESSURE = [
    ("Pa", 1.0), ("kPa", 1e3), ("MPa", 1e6), ("bar", 1e5),
    ("atm", 101325.0), ("psi", 6894.757),
]
_VEL = [
    ("m/s", 1.0), ("km/h", 1 / 3.6), ("ft/s", 0.3048),
]


def _temp_to_k(v: float, u: str) -> float:
    if u == "C":
        return v + 273.15
    if u == "F":
        return (v - 32.0) * 5.0 / 9.0 + 273.15
    return v


def _temp_from_k(k: float, u: str) -> float:
    if u == "C":
        return k - 273.15
    if u == "F":
        return (k - 273.15) * 9.0 / 5.0 + 32.0
    return k


class UnitConversionDialog(QDialog):
    """[Option] – [Unit Conversion…]。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unit Conversion")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(360, 260)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_general(), "Unit conversion")
        self.tabs.addTab(self._tab_rpm(), "Unit conversion 2")
        root.addWidget(self.tabs)
        root.addWidget(QLabel(
            "Result is copied to the clip board when 'Copy' button is pressed."))
        row = QHBoxLayout()
        row.addStretch(1)
        btn_copy = QPushButton("Copy")
        btn_close = QPushButton("Close")
        btn_copy.clicked.connect(self._copy)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_copy)
        row.addWidget(btn_close)
        root.addLayout(row)

    def _tab_general(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.addWidget(QLabel("Convert"), 0, 0)
        g.addWidget(QLabel("to"), 0, 1, Qt.AlignCenter)
        g.addWidget(QLabel("Converted"), 0, 2)
        self.sp_in = QDoubleSpinBox()
        self.sp_in.setDecimals(8)
        self.sp_in.setRange(-1e30, 1e30)
        self.sp_in.setValue(25)
        self.ed_out = QLineEdit()
        self.ed_out.setReadOnly(True)
        self.cb_cat = QComboBox()
        self.cb_cat.addItems(["Temperature", "Length", "Pressure", "Velocity"])
        self.cb_from = QComboBox()
        self.cb_to = QComboBox()
        g.addWidget(self.sp_in, 1, 0)
        g.addWidget(self.ed_out, 1, 2)
        g.addWidget(self.cb_from, 2, 0)
        g.addWidget(self.cb_to, 2, 2)
        g.addWidget(self.cb_cat, 3, 0, 1, 3)
        self.cb_cat.currentIndexChanged.connect(self._fill_units)
        self.cb_from.currentIndexChanged.connect(self._recalc)
        self.cb_to.currentIndexChanged.connect(self._recalc)
        self.sp_in.valueChanged.connect(self._recalc)
        self._fill_units()
        return w

    def _fill_units(self) -> None:
        cat = self.cb_cat.currentText()
        self.cb_from.blockSignals(True)
        self.cb_to.blockSignals(True)
        self.cb_from.clear()
        self.cb_to.clear()
        if cat == "Temperature":
            for u, _ in _TEMP:
                self.cb_from.addItem(u, u)
                self.cb_to.addItem(u, u)
            self.cb_from.setCurrentText("C")
            self.cb_to.setCurrentText("F")
        else:
            table = {"Length": _LENGTH, "Pressure": _PRESSURE,
                     "Velocity": _VEL}[cat]
            for name, factor in table:
                self.cb_from.addItem(name, factor)
                self.cb_to.addItem(name, factor)
        self.cb_from.blockSignals(False)
        self.cb_to.blockSignals(False)
        self._recalc()

    def _recalc(self) -> None:
        cat = self.cb_cat.currentText()
        vin = self.sp_in.value()
        if cat == "Temperature":
            k = _temp_to_k(vin, self.cb_from.currentData() or "C")
            out = _temp_from_k(k, self.cb_to.currentData() or "F")
        else:
            f_from = float(self.cb_from.currentData() or 1)
            f_to = float(self.cb_to.currentData() or 1)
            si = vin * f_from
            out = si / f_to if f_to else 0.0
        self.ed_out.setText(f"{out:.8g}")

    def _tab_rpm(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        self.sp_rpm = QDoubleSpinBox()
        self.sp_rpm.setRange(1e-12, 1e12)
        self.sp_rpm.setDecimals(6)
        self.sp_rpm.setValue(60)
        self.sp_deg = QDoubleSpinBox()
        self.sp_deg.setRange(-1e12, 1e12)
        self.sp_deg.setDecimals(6)
        self.sp_deg.setValue(360)
        self.ed_sec = QLineEdit("1")
        self.ed_sec.setReadOnly(True)
        self.cb_rpm_mode = QComboBox()
        self.cb_rpm_mode.addItem("rpm, deg -> s", "rpm_deg_s")
        self.cb_rpm_mode.addItem("s, deg -> rpm", "s_deg_rpm")
        self.cb_rpm_mode.addItem("rpm, s -> deg", "rpm_s_deg")
        g.addWidget(self.sp_rpm, 0, 0)
        g.addWidget(QLabel("rpm"), 0, 1)
        g.addWidget(QLabel("to"), 0, 2, Qt.AlignCenter)
        g.addWidget(self.ed_sec, 0, 3)
        g.addWidget(QLabel("s"), 0, 4)
        g.addWidget(self.sp_deg, 1, 0)
        g.addWidget(QLabel("deg"), 1, 1)
        g.addWidget(self.cb_rpm_mode, 2, 0, 1, 5)
        for wdg in (self.sp_rpm, self.sp_deg):
            wdg.valueChanged.connect(self._recalc_rpm)
        self.cb_rpm_mode.currentIndexChanged.connect(self._recalc_rpm)
        self._recalc_rpm()
        return w

    def _recalc_rpm(self) -> None:
        mode = self.cb_rpm_mode.currentData()
        rpm = self.sp_rpm.value()
        deg = self.sp_deg.value()
        # t = deg / (rpm * 6)
        if mode == "rpm_deg_s":
            t = deg / (rpm * 6.0) if rpm else 0.0
            self.ed_sec.setText(f"{t:.8g}")
        elif mode == "s_deg_rpm":
            # reuse ed_sec as rpm output when mode changes — keep simple:
            # interpret sp_rpm field as seconds for this mode
            t = rpm
            out_rpm = deg / (t * 6.0) if t else 0.0
            self.ed_sec.setText(f"{out_rpm:.8g}")
        else:
            t = deg  # treat sp_deg as seconds when rpm_s_deg? use sp_deg as time
            # rpm_s_deg: deg = rpm * 6 * s ; use sp_deg as seconds
            s = deg
            out_deg = rpm * 6.0 * s
            self.ed_sec.setText(f"{out_deg:.8g}")

    def _copy(self) -> None:
        if self.tabs.currentIndex() == 0:
            text = self.ed_out.text()
        else:
            text = self.ed_sec.text()
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Unit Conversion",
                                f"Copied to clipboard:\n{text}")


# ── languages ──────────────────────────────────────────────────────

LANGUAGES = [
    ("en", "English"),
    ("ja", "日本語"),
    ("zh_CN", "简体中文"),
    ("zh_TW", "繁體中文"),
    ("ko", "한국어"),
]
