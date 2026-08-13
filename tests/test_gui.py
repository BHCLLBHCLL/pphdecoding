"""GUI + VTK：几何构建器、离屏渲染、PyQt 主窗口烟囱与另存写回。"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import gphstats
import mdl
import oct
import pph_vtk


BOX_PART = r"tests\box\meshinggroup1_part.mdl"
BOX_RIDGE = r"tests\box\meshinggroup1_ridge.mdl"
BOX_OCT = r"tests\box\meshinggroup1.oct"
BOX_GPH = r"tests\box\meshinggroup1.gph"
BOX_PPH = r"box.pph"


# ── VTK 几何构建器 ─────────────────────────────────────────────────────────

def test_mdl_mesh_counts():
    m = mdl.parse_mdl(BOX_PART)
    pd = pph_vtk.mdl_mesh(m, "frid")
    assert pd.GetNumberOfCells() == m.n_faces
    assert pd.GetNumberOfPoints() == m.n_vertices
    assert pd.GetCellData().GetScalars() is not None
    pd2 = pph_vtk.mdl_mesh(m, "csid")
    assert pd2.GetNumberOfCells() == m.n_faces


def test_mdl_mesh_face_mask():
    import numpy as np

    m = mdl.parse_mdl(BOX_PART)
    mask = np.zeros(m.n_faces, dtype=bool)
    mask[123] = True
    pd = pph_vtk.mdl_mesh(m, "frid", face_mask=mask)
    assert pd.GetNumberOfCells() == 1
    # 空掩码 → 空 polydata
    empty = np.zeros(m.n_faces, dtype=bool)
    pd0 = pph_vtk.mdl_mesh(m, "frid", face_mask=empty)
    assert pd0.GetNumberOfCells() == 0


def test_oct_leaves_counts_and_depth_scalars():
    om = oct.parse_oct(BOX_OCT)
    pd = pph_vtk.oct_leaves(om)
    assert pd.GetNumberOfCells() == om.n_leaves * 6  # 每叶子 6 个四边形
    assert pd.GetCellData().GetScalars() is not None
    pd_capped = pph_vtk.oct_leaves(om, max_leaves=100)
    assert pd_capped.GetNumberOfCells() == 600


def test_gph_boundary_mesh():
    with gphstats.open_buffer(BOX_GPH) as data:
        mesh = gphstats.parse_mesh(data)
    pd = pph_vtk.gph_boundary_mesh(mesh)
    assert pd.GetNumberOfCells() == 600  # box 边界面
    assert mesh["vertices"].shape[1] == 3


def test_offscreen_render():
    m = mdl.parse_mdl(BOX_PART)
    actors = [pph_vtk.polydata_actor(pph_vtk.mdl_mesh(m))]
    assert pph_vtk.render_offscreen(actors) is True


def test_edges_actor_extracts_lines():
    m = mdl.parse_mdl(BOX_PART)
    pd = pph_vtk.mdl_mesh(m)
    actor = pph_vtk.edges_actor(pd)
    n_lines = actor.GetMapper().GetInput().GetNumberOfCells()
    assert n_lines > m.n_faces  # 边数 > 面数（三角/四边网格）
    c = actor.GetProperty().GetColor()
    assert c[0] < 0.3  # 暗色网格线


def test_scalar_bar_and_orientation_marker():
    import vtk

    lut = pph_vtk._make_lut((0, 3), discrete=True,
                            annotations={0: "open", 1: "case1"})
    assert lut.GetNumberOfTableValues() == 2  # 仅注解的两个离散值
    bar = pph_vtk.scalar_bar_actor("MDL part", lut)
    assert bar.GetTitle() == "MDL part"
    axes = pph_vtk.axes_actor()
    assert axes is not None


def test_polydata_actor_color_override():
    import vtk

    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    pts.InsertNextPoint(0, 0, 0)
    pts.InsertNextPoint(1, 0, 0)
    pts.InsertNextPoint(0, 1, 0)
    pd.SetPoints(pts)
    tri = vtk.vtkTriangle()
    tri.GetPointIds().SetId(0, 0)
    tri.GetPointIds().SetId(1, 1)
    tri.GetPointIds().SetId(2, 2)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(tri)
    pd.SetPolys(cells)
    actor = pph_vtk.polydata_actor(pd, color=(1.0, 0.0, 0.0))
    c = actor.GetProperty().GetColor()
    assert abs(c[0] - 1.0) < 1e-9


# ── GUI 烟囱（offscreen；3D 部件桩化避免无 GL 环境噪音）────────────────────

class _StubSignal:
    def connect(self, _f):
        return None


class _StubCombo:
    def __init__(self, items=None):
        self._items = list(items or [])
        self._text = self._items[0] if self._items else ""
        self.currentTextChanged = _StubSignal()

    def addItems(self, items):
        self._items = list(items)

    def addItem(self, item):
        self._items.append(item)

    def currentText(self):
        return self._text

    def setCurrentText(self, text):
        if text in self._items:
            self._text = text

    def findText(self, text):
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, idx):
        if 0 <= idx < len(self._items):
            self._text = self._items[idx]

    def currentIndex(self):
        try:
            return self._items.index(self._text)
        except ValueError:
            return -1


class _StubCheck:
    def __init__(self, checked=False):
        self._checked = checked

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked


class _StubView3D(__import__("PyQt5.QtWidgets", fromlist=["QWidget"]).QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.groups = {}
        self.status = type(
            "S", (),
            {"text": "", "update": lambda self: None,
             "setText": lambda self, t: setattr(self, "text", t)})()
        self.vis_calls = []
        self.show_all_requested = _StubSignal()
        self.display_mode = _StubCombo(["不透明", "半透明", "线框"])
        self.view_kind = _StubCombo(
            ["全部", "仅几何 (MDL)", "仅八叉树", "仅体网格 (GPH)"])
        self.chk_mdl_part = _StubCheck(True)
        self.chk_mdl_ridge = _StubCheck(False)
        self.chk_oct = _StubCheck(False)
        self.chk_gph = _StubCheck(True)
        self.chk_gph_color = _StubCheck(False)
        self.chk_edges = _StubCheck(True)
        self.chk_section = _StubCheck(False)
        self.section_target = _StubCombo(["几何/八叉树", "体网格"])
        self._legend_host = type(
            "S", (),
            {"isVisible": lambda self: False, "raise_": lambda self: None,
             "repaint": lambda self: None, "update": lambda self: None})()
        self.legend = type("S", (), {"update": lambda self: None})()

    def set_groups(self, groups):
        self.groups = groups

    def set_cad_meshes(self, bodies, *, append=False):
        self.cad_meshes = list(bodies)
        if append:
            self.cad_meshes.extend(list(bodies))

    def precache(self, group_models):
        pass

    def set_model_visibility(self, group, hidden_bodies,
                             hidden_regions, group_visible=True):
        self.vis_calls.append((group, set(hidden_bodies),
                               set(hidden_regions), group_visible))

    def set_layer_visibility(self, _group, _layer, _visible, *, refresh=True):
        return None

    def set_view_mode(self, _mode):
        return None

    def render(self):
        return None

    def clear_visibility(self):
        return None

    def set_model_filter(self, _filter_):
        return None

    def _sync_vtk_viewport(self):
        return None




def _make_viewer(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    monkeypatch.setattr(pph_gui, "View3DTab", _StubView3D)
    app = QApplication.instance() or QApplication([])
    win = pph_gui.PphViewer()
    return app, win


def test_gui_open_and_populate(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    assert win.arch is not None
    assert win.member_tree.topLevelItemCount() >= 3
    assert "meshinggroup1" in win.view3d.groups
    assert set(win.editor_tab._originals) == {
        "main.js", "main.prp", "main.xenv", "main.xml"}
    assert win.tabs.currentWidget() is win.view3d  # 3D 为默认显示区域
    win.close()


def test_pph_viewer_builds_with_real_view3d():
    """回归：真实 View3DTab 下 PphViewer 构造（show_all_requested 信号绑定）。"""
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    win = pph_gui.PphViewer()  # 构造即触发 view3d.show_all_requested.connect
    assert isinstance(win.view3d, pph_gui.View3DTab)
    assert win.view3d.show_all_requested is not None
    win.close()


def test_gui_edit_text_and_save(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    # 编辑 main.xenv（改一个值）
    data = win.member_bytes["main.xenv"]
    text = data.decode("utf-8", errors="replace")
    win.editor_tab.load_member("main.xenv", data)
    new_text = text.replace('<Key name="MODEL_LENGTH_UNIT">\r\n            m',
                            '<Key name="MODEL_LENGTH_UNIT">\r\n            mm', 1)
    assert new_text != text
    win.editor_tab.editor.setPlainText(new_text)
    overrides = win.editor_tab.overrides()
    assert set(overrides) == {"main.xenv"}
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "edited.pph")
        import pphwriter
        pphwriter.rewrite_pph(BOX_PPH, dst, overrides)
        import zipfile
        with zipfile.ZipFile(dst) as z:
            assert b"MODEL_LENGTH_UNIT\">\n            mm" in z.read("main.xenv")
    win.close()


def test_gui_view_only_creates_no_override(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    data = win.member_bytes["main.xenv"]
    win.editor_tab.load_member("main.xenv", data)
    assert win.editor_tab.overrides() == {}  # CRLF 规范化后不算修改
    win.close()


def test_view3d_show_event_initializes_interactor(monkeypatch):
    """VTK 9.3 的 QVTKRenderWindowInteractor 无 start()：showEvent 必须走
    GetInteractor().Initialize() 路径且不抛 AttributeError。"""
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda style: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    from PyQt5.QtGui import QShowEvent
    tab.showEvent(QShowEvent())  # 回归：旧代码调用 start() 会抛 AttributeError
    assert tab._started is True
    tab.close()


def test_default_caps_covers_all_layers():
    """render() 使用的全部图层名都必须在 DEFAULT_CAPS 中有上限。"""
    import pph_gui
    for kind in ("mdl", "ridge", "oct", "gph"):
        assert pph_gui.DEFAULT_CAPS[kind] > 0


def test_make_actor_ridge_no_keyerror():
    """回归：_make_actor('ridge') 此前因 DEFAULT_CAPS 缺键抛 KeyError。"""
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    layer = tab._make_actor("ridge", {"ridge": BOX_RIDGE})
    assert layer is not None
    assert layer.actor.GetMapper().GetInput().GetNumberOfCells() == 600
    assert layer.edges is False
    tab.close()


def test_make_actor_mdl_returns_region_annotations():
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    layer = tab._make_actor("mdl", {"part": BOX_PART})
    assert layer is not None
    assert layer.title == "MDL part"
    assert layer.annotations == {0: "open"}  # box：open(0)/Part(0) 去重
    assert layer.legend_entries == [("open", (0.9, 0.3, 0.25))]
    assert layer.actor.GetMapper().GetLookupTable() is not None
    tab.close()


def test_mdl_mask_rubber_list_filters():
    import numpy as np
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()

    class FakeModel:
        n_faces = 4
        csid = (np.array([1, 1, 2, 2]), np.array([0, 0, 0, 0]))
        frid = np.array([10, 11, 10, 12])

    tab._mdl_filter = {"kind": "faces", "values": [1, 3]}
    mask = tab._mdl_mask(FakeModel())
    assert mask.tolist() == [False, True, False, True]

    tab._mdl_filter = {"kind": "bodies", "values": [2]}
    mask = tab._mdl_mask(FakeModel())
    assert mask.tolist() == [False, False, True, True]
    tab.close()


def test_native_execute_helpers_present():
    """原生 Execute 流程辅助方法（CAD 回退 / 空工程成员追加）已接线。"""
    src = Path("pph_gui.py").read_text(encoding="utf-8")
    for needle in (
        "def _native_surface",
        "def _native_member_names",
        "def _cad_surface_points_tris",
        "meshinggroup1.oct",
        "meshinggroup1.gph",
    ):
        assert needle in src, needle


def test_render_pipeline_adds_layers_edges_and_legend(monkeypatch):
    """render() 全流程：图层 + 网格线进 renderer，Qt 图例面板填充。"""
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda s: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    monkeypatch.setattr(pph_vtk, "orientation_marker_widget", lambda iren: None)
    tab._started = True
    tab.groups = {
        "g": {"part": BOX_PART, "ridge": BOX_RIDGE,
              "oct": BOX_OCT, "gph": BOX_GPH}}
    tab.chk_mdl_ridge.setChecked(True)
    tab.chk_oct.setChecked(True)  # 打开全部四个图层
    tab.group_box.blockSignals(True)
    tab.group_box.clear()
    tab.group_box.addItem("g")
    tab.group_box.blockSignals(False)
    tab.group_box.setCurrentIndex(0)  # 触发 render()
    tab.render()
    n_props = tab.renderer.GetViewProps().GetNumberOfItems()
    # 4 图层 + 1 条 GPH 面网格线（MDL/OCT 不叠加网格线）；图例是 Qt 部件非 renderer prop
    assert n_props == 5
    assert "MDL part=60,492" in tab.status.text()
    assert "MDL ridge=600" in tab.status.text()
    assert not tab.legend.isHidden()  # 面板未显示其父窗口，用 isHidden 判定
    assert tab.legend._layout.count() >= 4  # 3 图层头 + 区域行/渐变行
    tab.close()


def test_legend_panel_discrete_and_gradient():
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    panel = pph_gui.LegendPanel()
    lut = pph_vtk._make_lut((0, 3), discrete=True,
                            annotations={0: "open", 1: "case1"})
    panel.set_layers([
        ("MDL part", lut, [("open", (0.9, 0.3, 0.25)),
                           ("case1", (0.25, 0.62, 0.90))]),
        ("GPH owner", pph_vtk._make_lut((0, 100)), None),
    ])
    assert not panel.isHidden()
    assert panel._layout.count() >= 6  # 2 标题 + 2 区域行 + 渐变行 + stretch
    panel.clear()
    assert panel._layout.count() == 0


def test_navigation_window_emits_key():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    import pph_gui

    app = QApplication.instance() or QApplication([])
    nav = pph_gui.NavigationWindow()
    got = []
    nav.navigated.connect(got.append)

    def find(key):
        for i in range(nav.tree.topLevelItemCount()):
            root = nav.tree.topLevelItem(i)
            for j in range(root.childCount()):
                child = root.child(j)
                if child.data(0, Qt.UserRole) == key:
                    return child
        return None

    nav._on_clicked(find("project"), 0)
    assert got == ["project"]
    nav._on_clicked(find("dashboard"), 0)
    assert got[-1] == "dashboard"
    nav._on_clicked(find("xml"), 0)
    assert got[-1] == "xml"

    nav.set_file_info(r"tests\box.pph", 9, "4.6 MiB")
    assert "box.pph" in nav.file_label.text()


def test_navigation_drives_viewer(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    assert "box.pph" in win.navigation.file_label.text()
    win._on_navigate("dashboard")
    assert win.tabs.currentWidget() is win.dashboard
    win._on_navigate("view3d")
    assert win.tabs.currentWidget() is win.view3d
    win._on_navigate("gph")
    assert win.member_tree.currentItem().data(0, 256) == "meshinggroup1.gph"
    win.close()


def test_property_panel_nested_values():
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    panel = pph_gui.PropertyPanel()
    panel.set_properties({
        "成员": "main.xenv",
        "角色分布": {"gph": "1 个", "mdl": "2 个"},
        "区域": ["open", "case1"],
    })
    assert panel.tree.topLevelItemCount() == 3
    root = panel.tree.topLevelItem(1)
    assert root.childCount() == 2


def test_dashboard_populate(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    win.dashboard.populate()
    assert win.dashboard._cards["archive"].text().startswith("9 成员")
    assert "面" in win.dashboard._cards["gph"].text()
    assert "单元" in win.dashboard._cards["gph"].text()
    assert win.dashboard.chart.items  # 条形图有数据


def test_view3d_display_mode_wireframe(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda s: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    monkeypatch.setattr(pph_vtk, "orientation_marker_widget", lambda iren: None)
    tab._started = True
    tab.groups = {"g": {"part": BOX_PART}}
    tab.group_box.blockSignals(True)
    tab.group_box.clear()
    tab.group_box.addItem("g")
    tab.group_box.blockSignals(False)
    tab.display_mode.setCurrentText("线框")  # 触发 render()
    tab.render()
    actor = tab.renderer.GetViewProps().GetItemAsObject(0)
    assert actor.GetProperty().GetRepresentation() == 1  # VTK_WIREFRAME


def test_view3d_clip_plane(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda s: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    monkeypatch.setattr(pph_vtk, "orientation_marker_widget", lambda iren: None)
    tab._started = True
    tab.groups = {"g": {"part": BOX_PART}}
    tab.group_box.blockSignals(True)
    tab.group_box.clear()
    tab.group_box.addItem("g")
    tab.group_box.blockSignals(False)
    tab.chk_section.setChecked(True)  # 触发 render()，启用剖面
    tab.render()
    assert tab.renderer.GetViewProps().GetNumberOfItems() >= 1
    n_before = tab.renderer.GetViewProps().GetNumberOfItems()
    tab.clip_slider.setValue(25)  # _plane_slider_changed 更新平面位置并重绘
    assert tab.renderer.GetViewProps().GetNumberOfItems() == n_before


def test_view3d_rubber_select_toggle(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    # 离屏环境桩化风格类，仅验证切换逻辑。
    recorded = []
    monkeypatch.setattr(
        iren, "SetInteractorStyle",
        lambda style: recorded.append(type(style).__name__))

    class FakeTrackball:
        pass

    monkeypatch.setattr("vtkmodules.vtkInteractionStyle."
                        "vtkInteractorStyleTrackballCamera", FakeTrackball)
    tab.btn_rubber.setChecked(True)
    tab.btn_rubber.setChecked(False)
    assert len(recorded) == 2
    assert recorded[0] == "_RubberStyle"
    assert recorded[1] == "FakeTrackball"
    tab.close()


def test_view_kind_filters_layers(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda s: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    monkeypatch.setattr(pph_vtk, "orientation_marker_widget", lambda iren: None)
    tab._started = True
    tab.groups = {
        "g": {"part": BOX_PART, "ridge": BOX_RIDGE,
              "oct": BOX_OCT, "gph": BOX_GPH}}
    tab.group_box.blockSignals(True)
    tab.group_box.clear()
    tab.group_box.addItem("g")
    tab.group_box.blockSignals(False)

    tab.chk_mdl_ridge.setChecked(True)
    # 仅几何：MDL part + ridge（当前实现不叠加几何网格线）
    tab.view_kind.setCurrentText("仅几何 (MDL)")
    tab.render()
    n_props = tab.renderer.GetViewProps().GetNumberOfItems()
    assert n_props == 2
    # 仅八叉树
    tab.chk_oct.setChecked(True)
    tab.view_kind.setCurrentText("仅八叉树")
    tab.render()
    n_props = tab.renderer.GetViewProps().GetNumberOfItems()
    assert n_props == 1
    # 仅体网格：GPH + 面网格线
    tab.view_kind.setCurrentText("仅体网格 (GPH)")
    tab.render()
    n_props = tab.renderer.GetViewProps().GetNumberOfItems()
    assert n_props == 2
    tab.close()


def test_model_tree_checkboxes_and_visibility():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tree = pph_gui.ModelTree()
    m = mdl.parse_mdl(BOX_PART)
    tree.populate({"meshinggroup1": {"part": m}})
    root = tree.tree.topLevelItem(0)
    assert root.text(0) == "Project (Project)"
    parts_root = root.child(0)
    assert parts_root.text(0) == "Parts (Whole)"
    got = []
    tree.visibility_changed.connect(
        lambda g, hb, hr, gv: got.append((g, hb, hr, gv)))

    part_item = None
    for i in range(parts_root.childCount()):
        node = parts_root.child(i)
        data = node.data(0, Qt.UserRole)
        if data and data[0] == "part":
            part_item = node
            break
    assert part_item is not None
    body_id = part_item.data(0, Qt.UserRole)[2]
    assert body_id is not None
    # 默认勾选
    assert part_item.checkState(0) == Qt.Checked
    assert root.checkState(0) == Qt.Checked
    # 取消勾选 part → 发射 hidden_bodies={body_id}
    part_item.setCheckState(0, Qt.Unchecked)
    assert got[-1] == ("meshinggroup1", {body_id}, set(), True)
    # 取消勾选组根 → 组不可见
    root.setCheckState(0, Qt.Unchecked)
    assert got[-1] == ("meshinggroup1", {body_id}, set(), False)
    # 右键"仅显示此项"：part 勾选、region 取消
    tree._set_all("meshinggroup1", True)
    tree._set_only(part_item, "meshinggroup1")
    hb, hr = tree.hidden_sets("meshinggroup1")
    assert hb == set() and hr == {0}  # 面区域 open(frid=0) 被隐藏
    # 隐藏全部
    tree._set_all("meshinggroup1", False)
    hb, hr = tree.hidden_sets("meshinggroup1")
    assert hb == {body_id} and hr == {0}



def test_model_tree_visibility_drives_3d(monkeypatch):
    from PyQt5.QtCore import Qt

    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    tree = win.model_tree
    root = tree.tree.topLevelItem(0)
    parts_root = root.child(0)
    part_item = None
    for i in range(parts_root.childCount()):
        node = parts_root.child(i)
        data = node.data(0, Qt.UserRole)
        if data and data[0] == "part":
            part_item = node
            break
    assert part_item is not None
    body_id = part_item.data(0, Qt.UserRole)[2]
    win.view3d.vis_calls.clear()
    part_item.setCheckState(0, 0)  # 取消勾选
    assert win.view3d.vis_calls[-1] == (
        "meshinggroup1", {body_id}, set(), True)
    win.close()



def test_model_filter_body_and_region(monkeypatch):
    from PyQt5.QtWidgets import QApplication
    import pph_gui

    app = QApplication.instance() or QApplication([])
    tab = pph_gui.View3DTab()
    iren = tab.vtk_widget.GetRenderWindow().GetInteractor()
    monkeypatch.setattr(iren, "SetInteractorStyle", lambda s: None)
    monkeypatch.setattr(iren, "Initialize", lambda: None)
    monkeypatch.setattr(tab.vtk_widget.GetRenderWindow(), "Render", lambda: None)
    monkeypatch.setattr(pph_vtk, "orientation_marker_widget", lambda iren: None)
    tab._started = True
    tab.groups = {"g": {"part": BOX_PART}}
    tab.group_box.blockSignals(True)
    tab.group_box.clear()
    tab.group_box.addItem("g")
    tab.group_box.blockSignals(False)
    tab.chk_mdl_ridge.setChecked(False)
    tab.chk_oct.setChecked(False)
    tab.chk_gph.setChecked(False)
    tab.chk_edges.setChecked(False)
    # 仅显示 body 1（box 全部面都属于 body 1）
    tab.set_model_filter({"kind": "body", "value": 1})
    actor = tab.renderer.GetViewProps().GetItemAsObject(0)
    assert actor.GetMapper().GetInput().GetNumberOfCells() == 60492
    assert "仅显示 body 1" in tab.status.text()
    # 恢复全部
    tab.set_model_filter(None)
    assert "已恢复全部" in tab.status.text()
    tab.close()


def test_gui_binary_details(monkeypatch):
    app, win = _make_viewer(monkeypatch)
    assert win.open_archive(BOX_PPH)
    text = win._binary_details("meshinggroup1_part.mdl")
    assert "面片几何" in text
    text = win._binary_details("meshinggroup1.gph")
    assert "面:" in text and "单元:" in text
    text = win._binary_details("meshinggroup1.oct")
    assert "八叉树" in text
    win.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
