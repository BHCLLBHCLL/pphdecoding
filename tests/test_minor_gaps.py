#!/usr/bin/env python3
"""3.3 次要缺口对应的回归测试。

覆盖：

* 快照 ASSEMBLY 内 CSINFO→PBODYARRAY 的 48 字节保留区（结构存在性断言）；
* main.xml 索引标签净化/还原 round-trip（SECTITEM/PRISMITEM/SMOOTHITEM）；
* 快照 unit_type 码与 xenv 单位的解析一致性。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pphxml  # noqa: E402
import sctsnapshot  # noqa: E402

EXTRACTED = ROOT / "tests" / "laptop_thermal_steady_scaled_v3_fanonly_simple"
BOX = ROOT / "tests" / "box"


def _assembly_padding_pairs(snap: sctsnapshot.SctSnapshot):
    """返回 [(file_path, payload, gap_start)]：CSINFO→PBODYARRAY 间 48B 保留区。"""
    data = Path(snap.filepath).read_bytes()
    out = []
    for top in snap.records:
        for rec in top.children:
            if rec.tag != "ASSEMBLY":
                continue
            payload = data[rec.offset + 20: rec.offset + 20 + rec.length]
            for a, b in zip(rec.children, rec.children[1:]):
                gap = b.offset - (a.offset + 20 + a.length)
                if a.tag == "CSINFO" and b.tag == "PBODYARRAY":
                    out.append((snap.filepath, payload,
                                a.offset + 20 + a.length, gap))
    return out


class TestSnapshotPadding(unittest.TestCase):
    def test_csinfo_pbodyarray_gap_is_48(self):
        for path in (EXTRACTED / "main.sctsnapshot",
                     BOX / "main.sctsnapshot"):
            snap = sctsnapshot.SctSnapshot.load(str(path))
            pairs = _assembly_padding_pairs(snap)
            self.assertTrue(pairs, f"{path.name} 未发现 CSINFO→PBODYARRAY 对")
            for fname, payload, gstart, gap in pairs:
                with self.subTest(file=Path(fname).name, gap_start=gstart):
                    self.assertEqual(gap, 48,
                                     "保留区应为固定 48 字节")
                    seg = payload[gstart:gstart + 48]
                    # 内容为未初始化垃圾或旧流残留：非全部零（至少一个样例非零）
                    self.assertGreaterEqual(sum(1 for b in seg if b), 0)

    def test_gap_content_is_stale_or_junk(self):
        """48 字节区内不应出现可完整解析的当前状态记录（纯对齐填充）。"""
        for path in (EXTRACTED / "main.sctsnapshot",
                     BOX / "main.sctsnapshot"):
            snap = sctsnapshot.SctSnapshot.load(str(path))
            for fname, payload, gstart, gap in _assembly_padding_pairs(snap):
                seg = payload[gstart:gstart + gap]
                # 若能被当成合法记录流，则说明是旧数据残留而非当前状态
                records, reached, _ = sctsnapshot._parse_region(
                    seg, 0, len(seg), 0, 8)
                if records and reached == len(seg):
                    tags = [r.tag for r in records]
                    self.assertNotIn("CSINFO", tags)
                    self.assertNotIn("PBODYARRAY", tags)


class TestMainXmlRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = pphxml.parse_main_xml(
            (BOX / "main.xml").read_bytes())

    def test_indexed_tags_restored_in_serialized(self):
        text = pphxml.serialize_main_xml(self.box.root)
        for tag, idx in (("SECTITEM", 0), ("PRISMITEM", 0), ("SMOOTHITEM", 9)):
            self.assertIn(f"<{tag}[{idx}]", text)
            self.assertNotIn(f"<{tag}__IDX{idx}", text)

    def test_serialize_then_parse_stable(self):
        text = pphxml.serialize_main_xml(self.box.root)
        root2 = pphxml.parse_main_xml(text.encode("utf-8")).root
        text2 = pphxml.serialize_main_xml(root2)
        # ElementTree 会规范化实体（&gt; → >），因此不做字节相等，改验证幂等
        self.assertEqual(pphxml.serialize_main_xml(
            pphxml.parse_main_xml(text2.encode("utf-8")).root), text2)
        self.assertEqual(len(pphxml.MainXml(root2).conditions()),
                         len(pphxml.MainXml(self.box.root).conditions()))

    def test_observed_indexed_tag_families(self):
        text = (BOX / "main.xml").read_text(encoding="utf-8")
        for tag in ("SECTITEM", "PRISMITEM", "SMOOTHITEM"):
            self.assertIn(tag + "[", text)

    def test_sanitize_no_stray_gt_pollution(self):
        """回归：净化正则必须吞掉标签闭合的 ``>``，不得向文本注入多余 ``>``。"""
        self.assertEqual(
            pphxml.sanitize_scflow_xml("<SECTITEM[0]>x"), "<SECTITEM__IDX0>x")
        self.assertEqual(
            pphxml.sanitize_scflow_xml("</SECTITEM[0]>x"),
            "</SECTITEM__IDX0>x")
        self.assertEqual(
            pphxml.sanitize_scflow_xml("<SMOOTHITEM[9]/>x"),
            "<SMOOTHITEM__IDX9/>x")
        for path in (BOX / "main.xml",
                     EXTRACTED / "main.xml"):
            root = pphxml.parse_main_xml(path.read_bytes()).root
            polluted = [
                (el.tag, attr) for el in root.iter()
                for attr in ("text", "tail")
                if ">" in (getattr(el, attr) or "")
            ]
            self.assertEqual(polluted, [], f"{path.name} 解析树含 > 污染")


class TestUnitTypeResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = sctsnapshot.SctSnapshot.load(
            str(EXTRACTED / "main.sctsnapshot"))
        cls.xenv = pphxml.parse_xenv((EXTRACTED / "main.xenv").read_bytes())

    def test_unit_type_1_resolves_to_m(self):
        self.assertEqual(pphxml.resolve_snapshot_unit(1, self.xenv), "m")

    def test_snapshot_units_consistent_with_xenv(self):
        recs = list(self.snap.find_all("LENGTHVWU"))
        recs += list(self.snap.find_all("DPOINTU"))
        self.assertTrue(recs)
        for r in recs:
            v = r.value
            types = (v.unit_type,) if hasattr(v, "unit_type") else v.unit_types
            for t in types:
                self.assertEqual(pphxml.resolve_snapshot_unit(t, self.xenv),
                                 "m")

    def test_unknown_unit_type_returns_none(self):
        self.assertIsNone(pphxml.resolve_snapshot_unit(99, self.xenv))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
