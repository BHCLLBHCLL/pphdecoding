"""R1-8 回归：CAD 可用性判据必须区分「离线」与「宿主」。

背景（审计 §13.1/§13.3）：旧代码只有 cad_import.available()，它只查
Cradle 安装内的 pskernel.dll 是否在位。后果是"只装 Cradle 但无许可/未启动
宿主"的机器上，GUI 会认为 CAD 能力可用，用户点击 STEP/CATIA 导入后才在宿主
环节失败。现拆为 offline_available()（pskernel 在位，免宿主免许可）与
host_available()（STEP/CATIA 走宿主 OpenCadFile 所需）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cad_import  # noqa: E402


class TestCadAvailability(unittest.TestCase):
    def test_offline_and_legacy_alias_agree(self):
        """旧名 available() 必须等价于 offline_available()（向后兼容）。"""
        self.assertEqual(cad_import.available(),
                         cad_import.offline_available())

    def test_offline_available_requires_pskernel_only(self):
        """离线判据只依赖 pskernel：与宿主是否运行无关（本机有安装）。"""
        val = cad_import.offline_available()
        self.assertIsInstance(val, bool)
        if val:
            # 有 pskernel 就应能建会话（免许可，2026-09-13 实测）
            import ps_facet2_nodes as ps
            self.assertTrue(ps.available())

    def test_host_available_returns_dict_without_raising(self):
        """宿主判据必须无副作用：任何环境下都返回带固定键的 dict。"""
        st = cad_import.host_available()
        self.assertIsInstance(st, dict)
        for k in ("ok", "installed", "running", "gui_ready", "hint", "error"):
            self.assertIn(k, st)
        self.assertIsInstance(st["ok"], bool)
        # ok 蕴含 installed 且 running
        if st["ok"]:
            self.assertTrue(st["installed"])
            self.assertTrue(st["running"])
        # 不可用时必须给出可读理由（hint 或 error）
        if not st["ok"]:
            self.assertTrue((st["hint"] or "").strip()
                            or (st["error"] or "").strip(),
                            "host_available 不可用但既无 hint 也无 error")

    def test_gui_uses_split_predicates(self):
        """GUI 必须用拆分后的判据（防回退到单一 available()）。"""
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        self.assertIn("cad_import.offline_available()", src)
        self.assertIn("host_available()", src)
        self.assertNotIn("if not cad_import.available():", src)


if __name__ == "__main__":
    unittest.main()
