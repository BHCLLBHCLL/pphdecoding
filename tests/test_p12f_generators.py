#!/usr/bin/env python3
"""P12-F NYI 接线生成器回归（离线，不触宿主）。

覆盖：edit_ops 五个新 write_*_vbs（Define Facet Part / Coord Part /
2D Sub-mesh / Fix Marked / Actran）的 VBS 内容与完成标记，
以及 NYI 扫描器在接线后仅剩产品边界项。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import edit_ops  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "scan_nyi_menus", ROOT / "tools" / "scan_nyi_menus.py")
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)

PROJECT = Path("D:/proj/demo.pph")
CAD = Path("D:/cad/part.x_t")


def _read_vbs(path: Path) -> str:
    return path.read_text(encoding="utf-16-le")


class TestNyiGenerators(unittest.TestCase):
    def _gen(self, write, *args, marker=True, **kwargs) -> tuple[str, Path]:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.vbs"
            mk = Path(td) / "a.done" if marker else None
            write(*args, out, marker=mk, **kwargs)
            text = _read_vbs(out)
            if mk is not None:
                self.assertIn('CreateTextFile("' + str(mk) + '"', text)
            return text, out

    def test_facet_part(self):
        text, _ = self._gen(edit_ops.write_facet_part_vbs, PROJECT, CAD)
        self.assertIn(f'Doc_.OpenProject "{PROJECT.as_posix()}"', text)
        self.assertIn("Set FacetMG_ = Doc_.CreateMeshingGroup", text)
        self.assertIn(f'Doc_.ImportCADAsFacet "{CAD.as_posix()}", FacetMG_',
                      text)
        self.assertIn(f'Doc_.SaveProject "{PROJECT.as_posix()}"', text)

    def test_facet_part_save_redirect(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.vbs"
            save = Path(td) / "out.pph"
            edit_ops.write_facet_part_vbs(PROJECT, CAD, out, save_path=save)
            text = _read_vbs(out)
            self.assertIn(f'Doc_.SaveProject "{save.as_posix()}"', text)
            self.assertNotIn(PROJECT.as_posix() + '"\r\nDoc_.SaveProject',
                             text)

    def test_coord_part(self):
        text, _ = self._gen(edit_ops.write_coord_part_vbs, PROJECT, "CP1")
        self.assertIn(
            'Set CoordPart_ = Doc_.CreateCoordinatesSpecifiedPart("CP1")',
            text)
        self.assertIn('Doc_.SaveProject', text)

    def test_submesh_mg(self):
        text, _ = self._gen(edit_ops.write_submesh_mg_vbs, PROJECT, "SM1")
        self.assertIn(
            'Set SubMG_ = Doc_.CreateSubmeshMeshingGroup("SM1")', text)

    def test_fix_marked(self):
        text, _ = self._gen(edit_ops.write_fix_marked_vbs, PROJECT)
        self.assertIn(
            "Set MeshingGroup_ = Doc_.QueryMeshingGroupByIndex(0)", text)
        self.assertIn("fix_ret_ = MeshingGroup_.FixMarkedElements", text)

    def test_actran_no_save(self):
        folder = Path("D:/out/actran")
        text, _ = self._gen(edit_ops.write_actran_vbs, PROJECT, folder)
        self.assertIn(
            f'MeshingGroup_.CreateActranFilesMonitor "{folder.as_posix()}"',
            text)
        self.assertNotIn("SaveProject", text)


class TestNyiScanner(unittest.TestCase):
    def test_only_product_boundary_left(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        items = scan._extract_nyi_from_source(src)
        # Ridge 子菜单 addMenu 行之后、下一个 addMenu 之前 → 菜单归属 Ridge
        self.assertEqual(items, [("Ridge", "Restore Closed Volume Data…")])
        self.assertIn("Restore Closed Volume Data…", scan.EVALUATIONS)

    def test_wired_menus_have_slots(self):
        src = (ROOT / "pph_gui.py").read_text(encoding="utf-8")
        for label in ("Define Facet Part…",
                      "Create Non-Facet/Closed Volume Part…",
                      "Create 2D Sub-mesh Meshing Unit…",
                      "Fix Marked Element Shape", "Create Actran Files…"):
            self.assertIn(f'"{label}"', src)
            # 每个标签所在的 add_act 调用必须带 slot（非 key= 开头的参数）
            idx = src.index(f'"{label}"')
            call_start = src.rindex("add_act(", 0, idx)
            depth = 0
            end = call_start
            for j, ch in enumerate(src[call_start:], start=call_start):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
            call = src[call_start:end]
            after = call[call.index(label) + len(label) + 1:]
            self.assertTrue(" ".join(after.split()).startswith(", self._"),
                            f"{label} 未接线: {call!r}")


if __name__ == "__main__":
    unittest.main()
