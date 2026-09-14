#!/usr/bin/env python3
"""R32-3 回归：手册行型/表头变体 —— 拒行分类 + 表头归一 + 捞回真词表。

三件事：

1. **表头归一**：手册 `[Return Value]` 4617 行 vs `[Return value]` **4280 行**
   （还有 `[Arguments]`/`[Return]`/拼写错/日文）。旧实现只认大写 V ——
   等于**静默丢掉近一半方法的返回值**（1942 条，含其取值词表）。
2. **拒行分类**：R31-2 规则拒掉的 118 行里 88 条格式提示、16 条 Note、10 条带 2+ 取值；
   其中 5 个方法的词表是真词表 → 新增两条**窄**规则捞回（+32 取值）；
   第一版放宽过宽（混进 63 条颜色占位 `0xAABBGGRR`），故加格式提示过滤。
3. **不变量**：表头归一后 `Conditions.GetAnalysisType` 的 30 条取值必须仍挂在
   **参数 type** 上（差点因 `argi` 写错把 `[Argument]` 整类漏掉，靠这条护栏拦住）。
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EX = ROOT / "tools" / "extract_vb_api_scflow.py"
CATALOG = ROOT / "schemas" / "vb_api_catalog.json"
FORMAT_HINT = re.compile(r"0x[0-9A-Fa-f]{4,}|AABBGGRR")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestHeadKind(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r323", EX)

    def test_documented_spellings(self):
        for head, want in (("[Explanation]", "expl"), ("[Argument]", "arg"),
                           ("[Return Value]", "ret"),
                           ("[Return value]", "ret"), ("[Arguments]", "arg"),
                           ("[Return]", "ret")):
            self.assertEqual(self.ex._head_kind(head), want, head)

    def test_typos_and_japanese(self):
        for head, want in (("[Explnation]", "expl"), ("[Explanetion]", "expl"),
                           ("[xplanation]", "expl"), ("[Argiment]", "arg"),
                           ("[Resturn Value]", "ret"), ("[Return Value]]", "ret"),
                           ("[引数]", "arg"), ("[戻り値]", "ret"),
                           ("[戻り値/Return value]", "ret")):
            self.assertEqual(self.ex._head_kind(head), want, head)

    def test_non_headers(self):
        for head in ("", "  ", "[Description]", "plain text", "[Note] x"):
            self.assertIsNone(self.ex._head_kind(head), head)


class TestReturnValueHeaderParsed(unittest.TestCase):
    BLOCK = (
        "<dl><dd>retval=x.GetY</dd></dl>"
        '<dl><dd><table class="vbmethod">'
        "<tr><td>[Argument]</td><td>(VARIANT)type</td><td>:</td>"
        "<td>Type (string)</td></tr>"
        '<tr><td></td><td>"Flow"</td><td>Flow</td></tr>'
        "<tr><td>[Return value]</td><td>(VARIANT)retval</td><td>:</td>"
        "<td>True (successful), False (failure)</td></tr>"
        "</table></dd></dl>")

    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r323b", EX)

    def test_lowercase_v_header_yields_return(self):
        entry = self.ex._parse_method_block(self.BLOCK)
        self.assertIsNotNone(entry.get("return"),
                             "[Return value] 行必须被识别为返回值")
        self.assertEqual(entry["return"]["name"], "retval")
        # 取值仍挂在参数上（表头归一不得改变取值归属）
        self.assertEqual([v["value"] for v in entry["arguments"][0]["values"]],
                         ["Flow"])


class TestDescValueRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = _load("ex_r323c", EX)

    def test_marker_anywhere_with_two_tokens(self):
        got = self.ex._desc_values(
            '(VARIANT)retval Direction of region (string) If coordinate '
            'definition type is plane "positive_side" positive direction '
            '"negative_side" negative direction')
        self.assertEqual([v["value"] for v in got],
                         ["positive_side", "negative_side"])

    def test_single_token_format_hint_rejected(self):
        self.assertEqual(self.ex._desc_values(
            '(BSTR)color Color (string "0xAABBGGRR")'), [])
        self.assertEqual(self.ex._desc_values(
            'Color at the top end (output, string "0xAABBGGRR")'), [])

    def test_parenthesised_comma_list(self):
        got = self.ex._desc_values(
            '(BSTR)impactLevel String representing impact '
            '("none", "low", "medium", "high")')
        self.assertEqual([v["value"] for v in got],
                         ["none", "low", "medium", "high"])

    def test_note_prose_rejected(self):
        """Note 段落不是词表（R32-3 第一版曾把 SewSheets 的 Note 句当取值）。"""
        self.assertEqual(self.ex._desc_values(
            '(VARIANT)retval True (successful), False (failed) (Note) Failure '
            'occurs in the following cases: "not in part mode," '
            '"no part exists in the argument,"'), [])

    def test_full_width_paren_list(self):
        got = self.ex._desc_values(
            '(VARIANT)fieldName Field name to get（"summary", "detail", '
            '"solverComand"）')
        self.assertEqual([v["value"] for v in got],
                         ["summary", "detail", "solverComand"])


class TestCatalogAfterR323(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))

    def _method(self, cls, name):
        return (self.cat["classes"].get(cls, {}).get("methods") or {}).get(name)

    def _values(self, cls, name, arg=None):
        e = self._method(cls, name) or {}
        for a in (e.get("arguments") or []) + [e.get("return") or {}]:
            if arg is None or a.get("name") == arg:
                if a.get("values"):
                    return [v["value"] for v in a["values"]]
        return []

    def test_returns_recovered_at_scale(self):
        n = sum(1 for info in self.cat["classes"].values()
                for kind in ("methods", "properties")
                for e in (info.get(kind) or {}).values() if e.get("return"))
        self.assertGreaterEqual(n, 4100)  # 归一前约 2235（漏掉 1942 条）

    def test_recovered_vocabularies(self):
        self.assertEqual(self._values("Kicker.Application",
                                      "GetLaunchProgram"),
                         ["pre", "solver", "post"])
        self.assertIn("sct", self._values("Kicker.Application",
                                          "GetProductType"))
        self.assertEqual(
            self._values("Doc", "GetProjectTypeConversionMessages",
                         "impactLevel"),
            ["none", "low", "medium", "high"])

    def test_format_hints_stay_out(self):
        e = self._method("Doc", "AddTemporaryDrawingObjectPoint") or {}
        for a in e.get("arguments") or []:
            if a.get("name") == "color":
                self.assertEqual(a.get("values") or [], [])

    def test_no_format_hint_anywhere(self):
        bad = [(c, n, v["value"])
               for c, info in self.cat["classes"].items()
               for kind in ("methods", "properties")
               for n, e in (info.get(kind) or {}).items()
               for a in (e.get("arguments") or []) + [e.get("return") or {}]
               if isinstance(a, dict)
               for v in (a.get("values") or [])
               if FORMAT_HINT.search(v["value"] + (v.get("description") or ""))]
        self.assertEqual(bad, [])

    def test_values_attribution_survives_header_normalisation(self):
        """[Argument] 必须仍被识别 —— 取值挂在参数上，不是丢在条目级。"""
        got = self._values("Conditions", "GetAnalysisType", "type")
        self.assertGreaterEqual(len(got), 30)

    def test_declared_manual_typo_values(self):
        """手册笔误留下的两个取值：`"\'protectd1"` / `"\'orthogonality"`
        （引号内多一个单引号）。**不猜**其真值 —— 只在账上显式声明，
        待实机确认（候选 R33 项）。"""
        typos = [("Conditions", "GetPresetStabilityParam", "'protectd1"),
                 ("Conditions", "GetPresetStabilityParamGeom",
                  "'orthogonality")]
        for cls, name, want in typos:
            self.assertIn(want, self._values(cls, name, "param"))

    def test_no_bogus_arguments(self):
        bad = [(c, m, a.get("name"))
               for c, info in self.cat["classes"].items()
               for kind in ("methods", "properties")
               for m, e in (info.get(kind) or {}).items()
               for a in (e.get("arguments") or [])
               if not a.get("type")
               and str(a.get("name", "")).startswith(('"', "“", "”"))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
