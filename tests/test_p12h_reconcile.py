#!/usr/bin/env python3
"""P12-H4 对账收束离线测试：165/165 三类归属闭包 / 词汇表 / 证据一致 / round-trip。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "p12h_reconcile", ROOT / "tools" / "_p12h_reconcile.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

REPORT = json.loads(
    (ROOT / "p12h_registry_report.json").read_text(encoding="utf-8"))
COND_TYPES = json.loads(
    (ROOT / "schemas" / "cond_types.json").read_text(encoding="utf-8"))
MERGED = json.loads(
    (ROOT / "schemas" / "merged.json").read_text(encoding="utf-8"))
P12C = json.loads(
    (ROOT / "p12c_registry_report.json").read_text(encoding="utf-8"))
SPECIAL6 = json.loads(
    (ROOT / "p12h_special6_report.json").read_text(encoding="utf-8"))

DISP = REPORT["dispositions"]


class TestReportClosure(unittest.TestCase):
    def test_165_full_coverage(self):
        universe = set(COND_TYPES["types"])
        self.assertEqual(REPORT["universe"], 165)
        self.assertEqual(len(DISP), 165)
        self.assertEqual(set(DISP), universe)

    def test_bucket_partition(self):
        buckets = Counter(d["bucket"] for d in DISP.values())
        self.assertEqual(dict(buckets), {"exact_key": 92, "alias": 1,
                                         "boundary": 72})
        self.assertEqual(REPORT["summary"]["unclassified"], 0)
        self.assertEqual(REPORT["summary"],
                         {"exact_key": 92, "alias": 1, "boundary": 72,
                          "unclassified": 0})

    def test_kinds_distribution(self):
        kinds = Counter(d["kind"] for d in DISP.values())
        self.assertEqual(dict(kinds),
                         {"registry_key": 90, "wizard_session_state": 71,
                          "member_locus": 2, "poison_isolated": 1,
                          "alias": 1})


class TestVocabulary(unittest.TestCase):
    def test_bucket_kind_mapping(self):
        for name, d in DISP.items():
            self.assertEqual(d["bucket"], rc.BUCKET_OF_KIND[d["kind"]], name)

    def test_alias_unique_and_target_exact_key(self):
        aliases = {n for n, d in DISP.items() if d["kind"] == "alias"}
        self.assertEqual(aliases, {"CondBoundaryHumidity"})
        target = DISP["CondBoundaryHumidity"]["target"]
        self.assertEqual(target, "CondHumidity")
        self.assertIn(target, set(COND_TYPES["aliases"].values()))
        self.assertEqual(DISP[target]["bucket"], "exact_key")

    def test_member_locus_precise_keys(self):
        ml = {n: d for n, d in DISP.items()
              if d["kind"] == "member_locus"}
        self.assertEqual(set(ml), {"CondOutputLFileWaterLevel",
                                   "CondFMIVariable"})
        for name, d in ml.items():
            self.assertTrue(d["target"].startswith("main.xml:"), name)

    def test_poison_isolated_battery_only(self):
        poison = {n for n, d in DISP.items()
                  if d["kind"] == "poison_isolated"}
        self.assertEqual(poison, {"CondBatteryARCDataPreprocessing"})

    def test_registry_key_all_have_sample_evidence(self):
        counts = {k: v.get("count", 0)
                  for k, v in MERGED["conditions"]["types"].items()}
        for name, d in DISP.items():
            if d["kind"] != "registry_key":
                continue
            self.assertGreater(counts.get(name, 0), 0,
                               f"{name}: no official-sample evidence")
            self.assertIn("官方案例库实样", d["evidence"], name)


class TestEvidenceAgreement(unittest.TestCase):
    def test_report_matches_cond_types(self):
        book = COND_TYPES["dispositions"]
        for name, d in DISP.items():
            self.assertEqual(d, book[name], name)

    def test_family_annotation_preserved(self):
        book = COND_TYPES["dispositions"]
        anno = book.get("Thermoregulation")
        self.assertIsNotNone(anno)
        self.assertEqual(anno["kind"], "wizard_session_state_gated")
        self.assertNotIn("Thermoregulation", DISP)
        self.assertEqual(REPORT["family_annotations"]["Thermoregulation"],
                         anno)

    def test_special6_kinds_carried_or_reattributed(self):
        for name, d6 in SPECIAL6["dispositions"].items():
            if name == "Thermoregulation":
                continue
            d = DISP[name]
            if d6["kind"] == "create_returns_nothing":
                # H3 实测形态保留在证据串中，账面归属向导唯一路径族
                self.assertEqual(d["kind"], "wizard_session_state", name)
                self.assertIn("create_returns_nothing", d["evidence"], name)
            else:
                self.assertEqual(d["kind"], d6["kind"], name)
                self.assertEqual(d.get("target"), d6.get("target"), name)

    def test_wizard_batch_verdicts_recorded(self):
        self.assertEqual(Counter(REPORT["wizard_batch_verdicts"].values()),
                         Counter({"session_state": 25,
                                  "keys_projected": 1, "not_run": 1}))

    def test_no_missing_type_got_registry_key(self):
        miss = rc.missing_types(P12C)
        for name in miss:
            self.assertNotEqual(DISP[name]["kind"], "registry_key", name)

    def test_official_sample_projects_counted(self):
        self.assertEqual(REPORT["official_sample_projects"],
                         len(MERGED["projects"]))


class TestRoundTrip(unittest.TestCase):
    def test_reconcile_recompute_is_deterministic(self):
        inputs = rc.load_inputs()
        disp, problems = rc.attribute(inputs)
        self.assertEqual(problems, [])
        self.assertEqual(disp, DISP)
        problems2 = rc.check_closure(disp, inputs)
        self.assertEqual(problems2, [])

    def test_carry_dispositions_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cond_types.json"
            payload = {"version": 3,
                       "dispositions": {"CondX": {"kind": "alias"}}}
            p.write_text(json.dumps(payload), encoding="utf-8")
            from tools.extract_cond_types import carry_dispositions  # noqa: E402
            self.assertEqual(carry_dispositions(p),
                             {"CondX": {"kind": "alias"}})
            # regen 负载（无 dispositions）合并后账本保留、版本不降级
            regen = {"version": 1, "types": {}}
            regen["dispositions"] = carry_dispositions(p)
            prev = json.loads(p.read_text(encoding="utf-8"))
            regen["version"] = prev.get("version", 1)
            self.assertEqual(regen["version"], 3)
            self.assertEqual(regen["dispositions"],
                             {"CondX": {"kind": "alias"}})

    def test_carry_dispositions_missing_or_bad_file(self):
        from tools.extract_cond_types import carry_dispositions  # noqa: E402
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(carry_dispositions(Path(td) / "nope.json"), {})
            bad = Path(td) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(carry_dispositions(bad), {})

    def test_cond_types_version_advanced(self):
        self.assertGreaterEqual(COND_TYPES["version"], 6)
        self.assertEqual(len(COND_TYPES["dispositions"]), 166)


if __name__ == "__main__":
    unittest.main()
