#!/usr/bin/env python3
"""Conditions schema 加载回归。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conditions_schema import load_bc_filters, load_conditions_yaml  # noqa: E402


class TestConditionsSchema(unittest.TestCase):
    def test_yaml_present(self):
        data = load_conditions_yaml()
        self.assertTrue(data.get("bc_filters") or data.get("version"))

    def test_bc_filters_merge_keys(self):
        f = load_bc_filters()
        self.assertIn("bc_flow", f)
        self.assertIn("CondBoundaryFlowIO", f["bc_flow"])

    def test_nav_panels_merged(self):
        from nav_panels import _BC_TYPE_FILTER
        self.assertIn("CondBoundaryFlowIO", _BC_TYPE_FILTER["bc_flow"])
        # schema 扩展项
        self.assertTrue(
            len(_BC_TYPE_FILTER["bc_flow"]) >= 1)


if __name__ == "__main__":
    unittest.main()
