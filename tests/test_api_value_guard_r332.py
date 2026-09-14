#!/usr/bin/env python3
"""R33-2 回归：取值校验接入 typed 桥的**派发路径**（三态，默认只告警）。

口径（审计 §45.3/§47.2）：`None`（手册无词表）与 `False`（有词表但取值不在内）
必须分开 —— 手册是子集（R30 实测宿主还认 `octree`），把「不在词表」当「非法」
直接抛会误杀宿主合法取值。故默认只记 `value_warnings`，`strict_values=True`
才抛 `ApiValueError`；两者都发生在**派发之前**。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import scflowpre_api as api  # noqa: E402


class _FakeCom:
    """最小 COM 替身：记录调用，不碰真宿主。"""

    def __init__(self):
        self.calls = []

    def _FlagAsMethod(self, name):  # noqa: N802 (COM 约定名)
        pass

    def ChangeMesher(self, kind):  # noqa: N802
        self.calls.append(("ChangeMesher", kind))
        return True

    def SetCompleteParallelFlag(self, flag):  # noqa: N802
        self.calls.append(("SetCompleteParallelFlag", flag))
        return True


class _Wrapped(api.ComObject):
    api_class = "MeshingGroupSetting"


class TestValueGuard(unittest.TestCase):
    def setUp(self):
        api.clear_value_warnings()
        self.com = _FakeCom()
        self.obj = _Wrapped(self.com)

    def test_documented_value_passes_silently(self):
        self.assertTrue(self.obj.call("ChangeMesher", "poly"))
        self.assertEqual(self.com.calls, [("ChangeMesher", "poly")])
        self.assertEqual(api.value_warnings, [])

    def test_undocumented_value_warns_but_still_dispatches(self):
        self.obj.call("ChangeMesher", "polyhedral")
        self.assertEqual(len(api.value_warnings), 1)
        self.assertIn("polyhedral", api.value_warnings[0])
        self.assertEqual(self.com.calls, [("ChangeMesher", "polyhedral")],
                         "默认模式必须照常派发（手册是子集，不拦）")

    def test_strict_mode_blocks_before_dispatch(self):
        self.obj.strict_values = True
        with self.assertRaises(api.ApiValueError):
            self.obj.call("ChangeMesher", "polyhedral")
        self.assertEqual(self.com.calls, [], "strict 模式必须在派发前拦下")
        self.assertFalse(api.value_warnings, "抛错就不该再记告警")

    def test_no_vocabulary_is_none_state(self):
        """无词表的成员一律不判（None ≠ False）。"""
        self.obj.call("SetCompleteParallelFlag", True)
        self.obj.strict_values = True
        self.obj.call("SetCompleteParallelFlag", True)
        self.assertEqual(api.value_warnings, [])

    def test_non_string_args_are_not_checked(self):
        self.obj.call("ChangeMesher", 3)
        self.assertEqual(api.value_warnings, [])

    def test_unwired_object_is_not_checked(self):
        class _Bare(api.ComObject):
            api_class = ""
        obj = _Bare(_FakeCom())
        obj.call("ChangeMesher", "definitely-not-a-value")
        self.assertEqual(api.value_warnings, [])


class TestWiring(unittest.TestCase):
    def test_typed_classes_are_wired_from_registry(self):
        n = api.wire_api_classes()
        self.assertGreaterEqual(len(api.TYPED_CLASSES), 17)
        for name, klass in api.TYPED_CLASSES.items():
            self.assertEqual(klass.api_class, name)
        self.assertGreaterEqual(n, 0)

    def test_vocabulary_is_reachable_for_wired_class(self):
        api.wire_api_classes()
        self.assertEqual(
            api.api_value_set(api.ScFlowpreMeshingGroupSetting.api_class,
                              "ChangeMesher", "type"),
            {"poly", "oct"})


if __name__ == "__main__":
    unittest.main()
