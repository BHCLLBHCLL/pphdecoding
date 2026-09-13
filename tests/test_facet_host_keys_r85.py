#!/usr/bin/env python3
"""R8-5 回归：Faceter 面板输出键 == R6-5/R7-4 实测宿主键。

闭环由两半组成：
  * 本文件（离线）：MesherFaceterBody.apply 写出的 FACET.* 键**就是**实测键名；
  * tools/xenv_host_write_check.py（实机，R7-4 已过）：这些键写进 main.xenv 后，
    宿主 MeshingGroupSetting getter 回读一致、工程 27/27 err=0。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402

CHECK = ROOT / "tools" / "xenv_host_write_check.py"
_APPS: list = []


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFacetKeysMatchHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import nav_panels
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("PyQt5 not available")
        cls.nav = nav_panels
        cls.check = _load("xhw_r85", CHECK)

    def _app(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(
            ["test", "-platform", "offscreen"])
        if not _APPS:
            _APPS.append(app)
        return _APPS[0]

    def test_panel_writes_verified_host_keys(self):
        self._app()
        xenv = pphxml.XenvSettings()
        ctx = {"xenv": xenv, "session": {}, "xml": None}
        body = self.nav.MesherFaceterBody()
        body.load(ctx)
        body.sp_chord.setValue(7.0)
        body.sp_ang.setValue(13.0)
        body.sp_width.setValue(9.0)
        self.assertTrue(body.apply(ctx))
        self.assertTrue(ctx.get("xenv_dirty"))
        self.assertEqual(xenv.get("FACET", "SIMPLE_CHORD_TOLERANCE"), "7")
        self.assertEqual(xenv.get("FACET", "SIMPLE_MAX_ANGLE"), "13")
        # 最大边长走面板自己的「相对最大边长」路径（Solid-based / Parasolid 共用
        # SIMPLE_MAX_WIDTH），不保证等于 sp_width 的输入值 —— 只断言它被写出
        # 且是数值（键名仍是实测宿主键）。
        width = xenv.get("FACET", "SIMPLE_MAX_WIDTH")
        self.assertIsNotNone(width)
        float(width)

    def test_verified_writes_are_covered_by_panel_contract(self):
        # 不变量（单调）：**每一个**已实测键都必须是面板真的写出的键名；
        # 具体集合随轮次增长（R8-5 两条 → R10-3 三条 → …），故不写死。
        verified = {key for key, _v, _g, _l in self.check.WRITES}
        self.assertGreaterEqual(len(verified), 3)
        src = (ROOT / "nav_panels.py").read_text(encoding="utf-8")
        for key in sorted(verified):
            self.assertIn(key, src, key)
        # 写宿主键的调用必须走 pphxml.set_xenv_value（写通道唯一入口）
        self.assertIn("set_xenv_value(", src)


if __name__ == "__main__":
    unittest.main()
