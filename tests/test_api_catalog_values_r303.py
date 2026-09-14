#!/usr/bin/env python3
"""R30-3 回归：VB 手册枚举取值进目录（假参数清零）。

背景：手册的 [Argument]/[Return Value] 表把取值写成**续行**（首格为空、
cells[1] = "poly"）。旧解析把它当成**新参数**（name 带引号、type 空）——
全库 1205 条假参数、239 个方法受影响，取值词表在自家 schema 里根本看不见。

代价已经付过一次：R29 只能猜 SetVoxelOctRefineType 的取值（猜 "octree"/
"voxel" 全错，手册真值是 "shape"/"speed"）；而宿主实测还多出一个手册未
列的 "octree" —— 故本文件同时钉住「词表来自手册」这一半，另半（宿主
getter 读回补全）由 tools/xenv_setter_probe.py 的实机档负责。
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EX = ROOT / "tools" / "extract_vb_api_scflow.py"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestEnumCell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r303", EX)

    def test_single_quoted_value(self):
        self.assertEqual(self.ex._enum_values('"poly"'),
                         [{"value": "poly", "description": ""}])

    def test_three_cell_row_value_plus_description(self):
        self.assertEqual(
            self.ex._enum_values('"LROP"'),
            [{"value": "LROP", "description": ""}])

    def test_multiple_values_in_one_cell(self):
        got = self.ex._enum_values(
            '"Numerical" : Display with numerical '
            '"Exponential" : Display with exponential')
        self.assertEqual([v["value"] for v in got],
                         ["Numerical", "Exponential"])
        self.assertEqual(got[0]["description"], "Display with numerical")

    def test_wide_quotes_and_unclosed_quote(self):
        """全角引号与漏闭合引号都是手册笔误，须一并接住。"""
        self.assertEqual([v["value"] for v in self.ex._enum_values("”GVEL”")],
                         ["GVEL"])
        self.assertEqual(self.ex._enum_values('"IRBN'),
                         [{"value": "IRBN", "description": ""}])
        self.assertEqual(self.ex._enum_values('"IRBN Mean radiant temp'),
                         [{"value": "IRBN",
                           "description": "Mean radiant temp"}])

    def test_numeric_value_cell(self):
        """0/1/2 型整数枚举（同格多值也要拆）。"""
        self.assertEqual(
            self.ex._numeric_values("0 Initial calculation 1 Restart calculation"),
            [{"value": "0", "description": "Initial calculation"},
             {"value": "1", "description": "Restart calculation"}])
        self.assertEqual(self.ex._numeric_values("2 Courant number"),
                         [{"value": "2", "description": "Courant number"}])

    def test_non_value_cell_yields_nothing(self):
        self.assertEqual(self.ex._enum_values("(BSTR)type"), [])
        self.assertEqual(self.ex._enum_values(""), [])


class TestContinuationDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r303b", EX)

    def test_enum_row_attaches_to_last_argument(self):
        entry = {"arguments": [{"type": "VARIANT", "name": "type",
                                "description": "Type (string)"}]}
        self.ex._parse_continuation(
            entry, "arg", ["", '"poly"', "", "Polyhedral mesher"], "")
        self.assertEqual(len(entry["arguments"]), 1, "取值行不得变成新参数")
        self.assertEqual(entry["arguments"][0]["values"],
                         [{"value": "poly",
                           "description": "Polyhedral mesher"}])

    def test_note_row_records_cross_ref(self):
        entry = {}
        self.ex._parse_continuation(
            entry, "arg",
            ["", "(Note) Refer to GetVoxelOctRefineType for details of "
                 "specification type."],
            '<td></td><td colspan="3"><b>(Note)</b> Refer to '
            '<a href="#GetVoxelOctRefineType">GetVoxelOctRefineType</a>')
        self.assertEqual(entry["note_ref"], "GetVoxelOctRefineType")
        self.assertIn("GetVoxelOctRefineType", entry["note"])

    def test_real_arg_continuation_still_becomes_argument(self):
        entry = {"arguments": [{"type": "VARIANT", "name": "a",
                                "description": "d"}]}
        self.ex._parse_continuation(
            entry, "arg", ["", "(BSTR)type", ":", "License mode ..."], "")
        self.assertEqual([a["name"] for a in entry["arguments"]], ["a", "type"])

    def test_enum_row_after_return_attaches_to_return(self):
        entry = {"arguments": [{"name": "n"}],
                 "return": {"type": "VARIANT", "name": "retval"}}
        self.ex._parse_continuation(
            entry, "ret", ["", '"shape"', "", "Model shape-weighted"], "")
        self.assertIsNone(entry["arguments"][0].get("values"))
        self.assertEqual(entry["return"]["values"],
                         [{"value": "shape",
                           "description": "Model shape-weighted"}])


_BLOCK = (
    "<dl><dd>retval=meshset.GetX</dd></dl>"
    '<dl><dd><table class="vbmethod">'
    "<tr><td>[Argument]</td><td>(VARIANT)key</td><td>:</td>"
    "<td>Variable type (string)</td></tr>"
    '<tr><td></td><td>"VELO"</td><td></td><td>Velocity vector</td></tr>'
    "<tr><td>(VARIANT)value</td><td>:</td>"
    "<td>Output setting (integer, input)</td></tr>"
    "<tr><td></td><td>0 Default setting</td><td></td><td></td></tr>"
    "<tr><td></td><td>1 Output</td><td></td><td></td></tr>"
    "</table></dd></dl>")


class TestMethodBlock(unittest.TestCase):
    """整块解析：取值挂对宿主、无表头参数行不得丢。"""

    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r303c", EX)

    def test_values_attach_hosts_and_headerless_arg_kept(self):
        entry = self.ex._parse_method_block(_BLOCK)
        args = {a["name"]: a for a in entry["arguments"]}
        self.assertEqual(sorted(args), ["key", "value"],
                         "无表头参数行 (VARIANT)value 不得丢")
        self.assertEqual([v["value"] for v in args["key"]["values"]], ["VELO"])
        self.assertEqual([v["value"] for v in args["value"]["values"]],
                         ["0", "1"])
        self.assertEqual(args["value"]["values"][0]["description"],
                         "Default setting")


class TestCatalogInvariants(unittest.TestCase):
    """目录级不变量（可复算，不写死条目数）。"""

    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _entries(self):
        for cls, info in self.cat["classes"].items():
            for kind in ("methods", "properties"):
                for name, entry in (info.get(kind) or {}).items():
                    yield cls, name, entry

    def test_no_quoted_name_arguments(self):
        bad = [(c, m, a.get("name"))
               for c, m, e in self._entries()
               for a in (e.get("arguments") or [])
               if not a.get("type")
               and str(a.get("name", "")).startswith(('"', "“", "”"))]
        self.assertEqual(bad, [], "取值行不得再被当成参数")

    def test_values_are_recorded_at_scale(self):
        n = sum(len(a.get("values") or [])
                for _c, _m, e in self._entries()
                for a in (e.get("arguments") or []) + [e.get("return") or {}]
                if isinstance(a, dict))
        self.assertGreaterEqual(n, 1200)  # 手册实测 1242 取值行 → 聚合 1519

    def test_voxel_oct_refine_type_vocabulary(self):
        """R30-1 的根因：setter 自己没有词表，词表在它注释指向的 getter 上。"""
        mgs = self.cat["classes"]["MeshingGroupSetting"]["methods"]
        self.assertEqual(
            [v["value"] for v in mgs["GetVoxelOctRefineType"]["return"]["values"]],
            ["shape", "speed"])
        self.assertEqual(mgs["SetVoxelOctRefineType"].get("note_ref"),
                         "GetVoxelOctRefineType")

    def test_integer_enum_method_keeps_its_argument(self):
        """GetFPHVariableOutput：旧解析丢了 (VARIANT)value 参数、还多出 3 条假参数。"""
        m = self.cat["classes"]["Conditions"]["methods"]["GetFPHVariableOutput"]
        args = {a["name"]: a for a in m["arguments"]}
        self.assertIn("value", args)
        self.assertEqual([v["value"] for v in args["value"]["values"]],
                         ["0", "1", "2"])
        self.assertGreaterEqual(len(args["key"]["values"]), 100)

    def test_change_mesher_values(self):
        m = self.cat["classes"]["MeshingGroupSetting"]["methods"]["ChangeMesher"]
        self.assertEqual([v["value"] for v in m["arguments"][0]["values"]],
                         ["poly", "oct"])


if __name__ == "__main__":
    unittest.main()
