"""Option → Settings (Environment Settings) page inventory vs scFLOWpre."""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication  # noqa: E402

from option_settings import (  # noqa: E402
    EnvironmentSettingsDialog, _DETAILED, _PROJECT,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_tree_matches_manual(qapp):
    assert [t for t, _ in _DETAILED] == [
        "Folder", "File", "Navigation", "Drawing (General)",
        "Drawing (Part)", "Drawing (Octree)", "Drawing (Mesh)",
        "Selection", "CAD Data", "Mesh", "Initialize",
    ]
    assert [t for t, _ in _PROJECT] == [
        "Project Type", "Unit", "CAD Data Import",
        "Precision of Closed Volume", "Tiny Faces", "Ridges",
        "Mesher/Faceter", "Voxel Fitting Mesher", "Mesh",
        "Mesh Parameter", "File", "MSC CoSim",
    ]


def test_dialog_pages_and_nav_apply(qapp):
    import pphxml
    from PyQt5.QtWidgets import QGroupBox, QLabel

    ctx = {
        "session": {},
        "xenv": pphxml.XenvSettings(),
        "groups_info": {},
    }
    dlg = EnvironmentSettingsDialog(ctx)
    assert set(dlg._pages) == {k for _, k in _DETAILED + _PROJECT}
    assert dlg.chk_show_bam.isChecked()
    assert "Enable condition settings" in dlg.chk_pre_bam.text()
    assert dlg.rad_comp0.isChecked()
    assert dlg.cb_project_type.currentText() == "scFLOW"
    assert dlg._mf_body is not None
    assert dlg._mf_body._settings_mode is True
    gbs = {g.title() for g in dlg.findChildren(QGroupBox)}
    assert "Edges to regard as 'Ridges'" in gbs
    assert "Width of faces to regard as 'Tiny'" in gbs
    assert any("Saving mapping information" in t for t in gbs)
    labs = [x.text() for x in dlg.findChildren(QLabel)]
    assert any("Two faces whose normal vectors" in t for t in labs)
    dlg.chk_enable_wrap.setChecked(True)
    assert dlg.apply(ctx)
    assert ctx["session"]["option_nav"]["enable_wrapping"] is True
    assert ctx["session"]["option_nav"]["show_bam_item"] is True
