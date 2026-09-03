#!/usr/bin/env python3
"""P12-H3 特殊 6 类处置离线测试：归类器 / 日志解析 / 落点扫描 / 入册一致性。"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "p12h_special6", ROOT / "tools" / "_p12h_special6.py")
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)

COND_TYPES = json.loads(
    (ROOT / "schemas" / "cond_types.json").read_text(encoding="utf-8"))
REPORT = json.loads(
    (ROOT / "p12h_special6_report.json").read_text(encoding="utf-8"))


def _tmpdir():
    import tempfile
    return tempfile.TemporaryDirectory()


class TestClassify(unittest.TestCase):
    def _cls(self, landed=(), members=(), creates=None, universe="CondX"):
        creates = creates if creates is not None else {"named": "True"}
        return h.classify("arm", {"creates": creates, "probes": {}},
                          list(landed), list(members),
                          {"HumidityBoundary": "CondHumidity"},
                          {"CondKnown"}, universe)

    def test_exact_key(self):
        v = self._cls(landed=[("n", "CondX")])
        self.assertEqual(v["kind"], "exact_key")

    def test_alias(self):
        v = self._cls(landed=[("n", "HumidityBoundary")])
        self.assertEqual(v["kind"], "alias")
        self.assertEqual(v["targets"], ["CondHumidity"])

    def test_aliased_to_known(self):
        v = self._cls(landed=[("n", "CondKnown")], universe="CondOther")
        self.assertEqual(v["kind"], "aliased_to_known")

    def test_member_locus_beats_not_serialized(self):
        v = self._cls(members=["main.xml"])
        self.assertEqual(v["kind"], "member_locus")
        self.assertEqual(v["members"], ["main.xml"])

    def test_not_serialized(self):
        v = self._cls()
        self.assertEqual(v["kind"], "not_serialized")

    def test_create_returns_nothing(self):
        v = self._cls(creates={"named": "False"})
        self.assertEqual(v["kind"], "create_returns_nothing")


class TestParseLog(unittest.TestCase):
    def test_shapes_and_probes(self):
        tmp = Path(self.enterContext(_tmpdir()))
        log = tmp / "p12h3_unit.log"
        log.write_text(
            "open_err=0\ncreate_named=True err=0\ncreate_noarg=False err=0\n"
            "fmi_used=True err=0\ndirty_err=0\nsave_err=0\n"
            "out_exists=True\nend\n", encoding="mbcs")
        h_arm = h.ARMS["humidity"]
        # parse_log 只读约定路径；临时替换模块级 arm_paths 不可行（纯函数），
        # 直接调用并注入：以 patch 方式验证解析逻辑
        orig = h.arm_paths

        def fake(arm):
            return tmp / "p12h3_unit.vbs", log, tmp / "out.pph"

        h.arm_paths = fake
        try:
            facts = h.parse_log("humidity")
        finally:
            h.arm_paths = orig
        self.assertEqual(facts["creates"],
                         {"named": "True", "noarg": "False"})
        self.assertEqual(facts["probes"]["open_err"], "0")
        self.assertEqual(facts["probes"]["fmi_used"], "True")


class TestParseOutConditions(unittest.TestCase):
    def test_typed_condition_and_prefix_member(self):
        tmp = Path(self.enterContext(_tmpdir()))
        out = tmp / "p12h3_unit_out.pph"
        xml = (b'<?xml version="1.0"?><scFLOWpre><conditions>'
               b"<condition><name>P12h3BoundaryHumidity</name>"
               b"<type>HumidityBoundary</type></condition></conditions>"
               b"</scFLOWpre>")
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("main.xml", xml)
            zf.writestr("main.prp", b"P12h3Something")
            zf.writestr("main.js", b"noise")
        orig = h.arm_paths

        def fake(arm):
            return tmp / "v.vbs", tmp / "l.log", out

        h.arm_paths = fake
        try:
            landed, members = h.parse_out_conditions("humidity")
        finally:
            h.arm_paths = orig
        self.assertEqual(landed,
                         [("P12h3BoundaryHumidity", "HumidityBoundary")])
        # 字节扫描按 zip 成员序；main.xml 也含 PREFIX（typed 落点）
        self.assertEqual(members, ["main.xml", "main.prp"])

    def test_name_only_condition_not_landed(self):
        # output_timing 内联 condition 只有 name 无 type → 不入 landed，
        # 但字节扫描必须抓到（member_locus 依据）
        tmp = Path(self.enterContext(_tmpdir()))
        out = tmp / "p12h3_unit_out.pph"
        xml = (b'<?xml version="1.0"?><scFLOWpre><output_timing>'
               b"<condition><name>P12h3OutputLFileWaterLevel</name>"
               b"</condition></output_timing></scFLOWpre>")
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("main.xml", xml)
        orig = h.arm_paths

        def fake(arm):
            return tmp / "v.vbs", tmp / "l.log", out

        h.arm_paths = fake
        try:
            landed, members = h.parse_out_conditions("waterlevel")
        finally:
            h.arm_paths = orig
        self.assertEqual(landed, [])
        self.assertEqual(members, ["main.xml"])


class TestRegistryConsistency(unittest.TestCase):
    def test_special_six_plus_thermoregulation_covered(self):
        dispositions = COND_TYPES["dispositions"]
        universes = {spec["universe"] for spec in h.ARMS.values()}
        universes |= set(h.STATIC_DISPOSITIONS)
        # H4 全量入册（165 类 + 族级注记）：H3 六类仍是子集
        self.assertTrue(universes <= set(dispositions))

    def test_kinds_in_vocabulary(self):
        allowed = {"exact_key", "alias", "aliased_to_known", "member_locus",
                   "not_serialized", "create_returns_nothing",
                   "poison_isolated", "wizard_session_state_gated",
                   # H4 对账收束新增（165 类全量入册）
                   "registry_key", "wizard_session_state"}
        for name, d in COND_TYPES["dispositions"].items():
            self.assertIn(d["kind"], allowed, name)

    def test_alias_target_registered(self):
        d = COND_TYPES["dispositions"]["CondBoundaryHumidity"]
        self.assertEqual(d["kind"], "alias")
        self.assertIn(d["target"], set(COND_TYPES["aliases"].values()))

    def test_member_locus_targets_are_precise_keys(self):
        for name in ("CondOutputLFileWaterLevel", "CondFMIVariable"):
            d = COND_TYPES["dispositions"][name]
            self.assertEqual(d["kind"], "member_locus", name)
            self.assertTrue(d["target"].startswith("main.xml:"), name)

    def test_report_and_cond_types_agree(self):
        for name, d in REPORT["dispositions"].items():
            same = COND_TYPES["dispositions"][name]
            if d["kind"] == "create_returns_nothing":
                # H4 收束：实测形态入证据串，账面归属向导唯一路径族
                self.assertEqual(same["kind"], "wizard_session_state", name)
                self.assertIn("create_returns_nothing",
                              same.get("evidence", ""), name)
            else:
                self.assertEqual(d["kind"], same["kind"], name)
                self.assertEqual(d.get("target"), same.get("target"), name)

    def test_fmi_arm_facts_measured(self):
        arm = REPORT["arms"]["fmi_param"]
        self.assertEqual(arm["creates"]["named"], "True")
        self.assertEqual(arm["probes"]["fmi_param_err"], "0")
        self.assertEqual(arm["verdict"]["kind"], "member_locus")


if __name__ == "__main__":
    unittest.main()
