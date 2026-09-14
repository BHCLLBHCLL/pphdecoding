#!/usr/bin/env python3
"""R31-2 回归：取值写在**参数描述**里的行型（描述即词表）。

手册有两种写法把取值塞在描述格里：

  * `Type of connection (string)["default" (default), "connect" (connect)]`
  * `License mode "hpc" : HPC edition "lt" : LT edition`

R30 只处理了「整格是取值」的行，这类「描述即词表」的**词表一直不可见**（实测 116 行）。
判定条件（实测标定）：第一个引号之前必须出现**类型标记**（(string)/(BSTR)/(VARIANT)）
或 label 词（mode/type/…）；散文与格式提示必须被挡在门外（实测 118 行属此类）。
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


class TestDescValuesRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r312", EX)

    def test_parenthesised_list_after_type_marker(self):
        got = self.ex._desc_values(
            '(VARIANT)type Type of connection (string)["default" (default), '
            '"connect" (connect), "disconnect" (disconnect)]')
        self.assertEqual([v["value"] for v in got],
                         ["default", "connect", "disconnect"])
        self.assertEqual(got[0]["description"], "default")

    def test_value_paren_desc_pairs(self):
        got = self.ex._desc_values(
            '(VARIANT)key Amplitude type (string) "pressure"(pressure) '
            '"mass_flow_rate"(mass flow rate)')
        self.assertEqual([v["value"] for v in got],
                         ["pressure", "mass_flow_rate"])
        self.assertEqual(got[1]["description"], "mass flow rate")

    def test_label_word_prefix(self):
        got = self.ex._desc_values(
            '(BSTR)type License mode "hpc" : HPC edition "lt" : LT edition')
        self.assertEqual([v["value"] for v in got], ["hpc", "lt"])

    def test_note_prose_is_not_a_vocabulary(self):
        """R32-3 口径修正：Note 段落永远是散文（实测污染过 `Doc.SewSheets`）。

        注：原先拿 `Use "cycle_interval" to get cycle interval` 当反例，R32-3 判定
        它**是**词表（两个选择子 + 完整类型标记），见 §46.3 —— 反例换成 Note 文本。
        """
        self.assertEqual(self.ex._desc_values(
            '(VARIANT)retval True (successful), False (failed) (Note) Failure '
            'occurs in the following cases: "not in part mode," '
            '"no part exists in the argument,"'), [])

    def test_format_hint_is_not_a_vocabulary(self):
        self.assertEqual(self.ex._desc_values(
            '(VARIANT)retval Color at the top end (output, string '
            '"0xAABBGGRR")'), [])

    def test_pure_value_row_is_left_to_continuation_path(self):
        self.assertEqual(self.ex._desc_values('"poly"'), [])


class TestCatalogAfterR312(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _member(self, cls, member):
        info = self.cat["classes"][cls]
        return (info.get("methods") or {}).get(member)

    def test_connection_type_vocabulary_visible(self):
        ret = self._member("ClosedVolume", "GetConnectionType")["return"]
        self.assertEqual([v["value"] for v in ret["values"]],
                         ["default", "connect", "disconnect"])

    def test_prose_and_hint_rows_have_no_values(self):
        # R32-3：GetRadiationVFRETimingParam 已判定为**真词表**（cycle_interval /
        # time_interval），反例改用 Note 段落（SewSheets）与颜色格式提示。
        for cls, member in (("Doc", "SewSheets"),
                            ("Doc", "GetBkColor"),
                            ("Doc", "GetDefaultSolidPartColor")):
            e = self._member(cls, member)
            if e is None:
                continue
            for a in (e.get("arguments") or []) + [e.get("return") or {}]:
                self.assertFalse(a.get("values"),
                                 cls + "." + member + " 不得把散文当词表")

    def test_no_new_bogus_arguments(self):
        bad = [(c, m, a.get("name"))
               for c, info in self.cat["classes"].items()
               for kind in ("methods", "properties")
               for m, e in (info.get(kind) or {}).items()
               for a in (e.get("arguments") or [])
               if not a.get("type")
               and str(a.get("name", "")).startswith(('"', "“", "”"))]
        self.assertEqual(bad, [])

    def test_values_total_is_monotone(self):
        n = sum(len(a.get("values") or [])
                for info in self.cat["classes"].values()
                for kind in ("methods", "properties")
                for e in (info.get(kind) or {}).values()
                for a in (e.get("arguments") or []) + [e.get("return") or {}]
                if isinstance(a, dict))
        self.assertGreaterEqual(n, 1700)  # R30: 1519 → R31-2: 1738


if __name__ == "__main__":
    unittest.main()
