"""Empty / untitled PPH project on startup."""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication  # noqa: E402

import pph_gui  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_empty_project_members_zippable():
    members = pph_gui.PphViewer._empty_project_members()
    assert set(members) == {"main.xml", "main.xenv", "main.prp", "main.js"}
    with tempfile.NamedTemporaryFile(suffix=".pph", delete=False) as f:
        path = f.name
    try:
        with zipfile.ZipFile(path, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        with zipfile.ZipFile(path, "r") as zf:
            assert set(zf.namelist()) == set(members)
    finally:
        os.unlink(path)


def test_new_empty_project_loads(qapp):
    w = pph_gui.PphViewer()
    w.new_empty_project()
    assert w.arch is not None
    assert w._untitled is True
    assert "Untitled" in w.windowTitle()
    assert set(w.member_bytes) >= {"main.xml", "main.xenv", "main.prp", "main.js"}
    assert w._xenv is not None
    assert w._xenv.get("MESH", "MESHER") == "0"
    assert w.navigation._polyhedral_mesher is True
    xml = w._main_xml
    assert xml is not None
    mg = xml.section("parts").find("meshinggroup")
    assert mg.find("movinggroup") is not None


def test_save_as_appends_imported_xt(qapp):
    w = pph_gui.PphViewer()
    w.new_empty_project()
    w._set_member("box.x_t", b"XTDATA")
    import project_persist
    import pphwriter
    import pph_parser
    with tempfile.TemporaryDirectory() as td:
        dst = os.path.join(td, "saved.pph")
        overrides = project_persist.collect_save_overrides(
            w.arch, w.member_bytes, w.editor_tab.overrides(),
            dirty=w._dirty_members)
        pphwriter.rewrite_pph(w.archive_path, dst, overrides)
        arch = pph_parser.PphArchive.open(dst)
        names = {m.name for m in arch.members}
        assert "box.x_t" in names
        assert arch.read_member("box.x_t") == b"XTDATA"


def test_show_condition_auto_inits_when_no_arch(qapp):
    w = pph_gui.PphViewer()
    assert w.arch is None
    with patch.object(w, "new_empty_project", wraps=w.new_empty_project) as neo:
        with patch.object(w._nav_dialogs, "open", return_value=None):
            w._show_condition("parts_control")
    neo.assert_called_once()
    assert w.arch is not None
