#!/usr/bin/env python3
"""P12-C 收割机离线测试（无宿主）。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_p12c_cond_harvest", ROOT / "tools" / "_p12c_cond_harvest.py")
p12c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12c)


class TestHarvestTargets(unittest.TestCase):
    def test_poison_excluded(self):
        targets = p12c.harvest_targets()
        methods = {m for _t, m, _s in targets}
        self.assertEqual(methods & p12c.SAVE_POISON, set())

    def test_targets_have_known_shapes(self):
        for target, method, short in p12c.harvest_targets():
            self.assertTrue(target.startswith("Cond") or
                            target in ("CondFMIVariable",), target)
            self.assertTrue(method)
            self.assertTrue(short)

    def test_already_haved_universe_targets_skipped(self):
        # 已有精确键且在 universe 内的类型不应再收割
        have = json.loads((ROOT / "schemas" / "merged.json")
                          .read_text(encoding="utf-8"))
        have_types = set((have.get("conditions") or {})
                         .get("types") or {})
        univ = set(json.loads((ROOT / "schemas" / "cond_types.json")
                              .read_text(encoding="utf-8"))["types"])
        targets = {t for t, _m, _s in p12c.harvest_targets()}
        for t in targets:
            self.assertFalse(t in univ and t in have_types,
                             f"{t} already has exact keys")


class TestBuildHarvestVbs(unittest.TestCase):
    def test_single_script_contains_dirty_forcer_and_save(self):
        targets = p12c.harvest_targets()[:3]
        lines = p12c.build_harvest_vbs(targets)
        text = "\r\n".join(lines)
        self.assertIn("SetDefaultTemperature", text)
        self.assertIn("SaveProject", text)
        self.assertIn("open_err=", text)
        self.assertNotIn("Goto 0", text)

    def test_create_only_variant_omits_save(self):
        targets = p12c.harvest_targets()[:3]
        lines = p12c.build_harvest_vbs(targets, with_save=False)
        text = "\r\n".join(lines)
        self.assertNotIn("SaveProject", text)

    def test_noarg_fallback_logged(self):
        targets = [("CondCoSim", "CreateCondCoSim", "CoSim")]
        lines = p12c.build_harvest_vbs(targets)
        text = "\r\n".join(lines)
        self.assertIn("CreateCondCoSim(\"P12cHCoSim\")", text)
        self.assertIn("CreateCondCoSim()", text)
        self.assertIn("_mode=noarg", text)


class TestParseLog(unittest.TestCase):
    def test_parse_mk_and_tails(self):
        log = p12c.LOG
        p12c.LOG = ROOT / "scratch" / "_nonexistent.log"
        try:
            res = p12c.parse_log(ROOT / "scratch" / "_nonexistent.log")
            self.assertFalse(res["has_end"])
        finally:
            p12c.LOG = log

    def test_parse_log_content(self):
        import tempfile
        content = "\r\n".join([
            "open_err=0",
            "cond_alive=True err=0",
            "mk001_Acceleration_mode=noarg err=0",
            "mk001_Acceleration=True err=0",
            "mk002_CoSim=False err=5",
            "dirty_err=0",
            "save_err=0",
            "out_exists=True",
            "end",
        ])
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False,
                                         encoding="mbcs") as f:
            f.write(content)
            path = Path(f.name)
        try:
            res = p12c.parse_log(path)
        finally:
            path.unlink()
        self.assertEqual(res["open_err"], "0")
        self.assertEqual(res["save_err"], "0")
        self.assertTrue(res["has_end"])
        self.assertEqual(res["modes"], {"001_Acceleration": "noarg"})
        self.assertEqual(res["mk"]["001_Acceleration"]["alive"], "True")
        self.assertEqual(res["mk"]["002_CoSim"]["err"], "5")
        self.assertEqual(res["bad"], 1)


class TestAliasNormalization(unittest.TestCase):
    def test_measured_aliases_registered(self):
        ct = json.loads((ROOT / "schemas" / "cond_types.json")
                        .read_text(encoding="utf-8"))
        univ = set(ct["types"])
        # 实测别名（宿主落盘原始 type= 短名 → 注册表 Cond* 名）
        for raw, cond in (("ALECancel", "CondALECancel"),
                          ("BladeShape", "CondBladeShape"),
                          ("WaveGeneration", "CondWaveGeneration"),
                          ("SymmetricalBoundary", "CondSymmetricalBoundary")):
            self.assertEqual(ct["aliases"].get(raw), cond)
            self.assertIn(cond, univ)

    def test_universe_coverage_reported(self):
        merged = json.loads((ROOT / "schemas" / "merged.json")
                            .read_text(encoding="utf-8"))
        have = set((merged.get("conditions") or {}).get("types") or {})
        ct = json.loads((ROOT / "schemas" / "cond_types.json")
                        .read_text(encoding="utf-8"))
        univ = set(ct["types"])
        # 冲刺 C 基线（63）之上收割机净增类型
        self.assertGreaterEqual(len(univ & have), 90,
                                "in-universe exact keys regressed")


if __name__ == "__main__":
    unittest.main()
