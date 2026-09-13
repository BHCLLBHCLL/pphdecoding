#!/usr/bin/env python3
"""batch_bridge + modal_watch 边缘路径测试（J6.3 回归强化）。

batch_bridge: _run_helper stderr fallback + BatchBridge.dry_run
modal_watch: visible_windows + ModalWatcher 累积/上下文管理器安全
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import automation.batch_bridge as batch  # noqa: E402
from automation import modal_watch  # noqa: E402


def fake_enum(wins):
    def run(cb):
        for hwnd, cls, title, pid, visible in wins:
            if not cb(hwnd, 0):
                break
    return run


class TestRunHelper(unittest.TestCase):
    def test_run_helper_parses_stdout(self):
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="line1\nline2\n", stderr="")
        with patch("automation.batch_bridge.subprocess.run",
                   return_value=fake_proc):
            lines = batch._run_helper(Path("helper.exe"), "all-cmdline",
                                      Path("pre.bat"), ["arg1"])
        self.assertEqual(lines, ["line1", "line2"])

    def test_run_helper_stderr_fallback(self):
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="err1\nerr2\n")
        with patch("automation.batch_bridge.subprocess.run",
                   return_value=fake_proc):
            lines = batch._run_helper(Path("helper.exe"), "all-cmdline",
                                      Path("pre.bat"), ["arg1"])
        self.assertEqual(lines, ["err1", "err2"])

    def test_run_helper_stdout_preferred_over_stderr(self):
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="out1\n", stderr="err1\n")
        with patch("automation.batch_bridge.subprocess.run",
                   return_value=fake_proc):
            lines = batch._run_helper(Path("helper.exe"), "all-cmdline",
                                      Path("pre.bat"), ["arg1"])
        self.assertEqual(lines, ["out1"])


class TestBatchBridgeDryRun(unittest.TestCase):
    def test_dry_run_calls_inspect(self):
        fake_bat = Path("pre.bat")
        fake_helper = Path("helper.exe")
        with patch.object(batch, "find_cli_bat", return_value=fake_bat):
            with patch.object(batch, "inspect",
                              return_value={"available": True,
                                            "lines": ["cmd line"]}) as m:
                bridge = batch.BatchBridge("pre")
                result = bridge.dry_run("case.cmb", 4)
                self.assertTrue(result["available"])
                m.assert_called_once()


class TestVisibleWindows(unittest.TestCase):
    WINS = [
        (0x1, "#32770", "Dialog 1", 100, True),
        (0x2, "Afx:0", "Main Window", 100, True),
        (0x3, "Button", "OK", 100, True),
        (0x4, "#32770", "Dialog 2", 200, True),
        (0x5, "Afx:0", "Other App", 300, True),
    ]

    def test_visible_windows_returns_all_classes(self):
        meta = {w[0]: w for w in self.WINS}
        found = modal_watch.visible_windows(
            pid=100,
            _enum=fake_enum(self.WINS),
            _text=lambda h: meta[h][2],
            _cls=lambda h: meta[h][1],
            _wpid=lambda h: meta[h][3],
            _vis=lambda h: meta[h][4])
        self.assertEqual(len(found), 3)
        classes = {w["cls"] for w in found}
        self.assertEqual(classes, {"#32770", "Afx:0", "Button"})

    def test_visible_windows_filters_by_pid(self):
        meta = {w[0]: w for w in self.WINS}
        found = modal_watch.visible_windows(
            pid=200,
            _enum=fake_enum(self.WINS),
            _text=lambda h: meta[h][2],
            _cls=lambda h: meta[h][1],
            _wpid=lambda h: meta[h][3],
            _vis=lambda h: meta[h][4])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["hwnd"], 0x4)


class TestModalWatcherEdge(unittest.TestCase):
    def test_watcher_accumulates_closures(self):
        hits_batch_1 = [{"hwnd": 0x7, "title": "Wizard"}]
        hits_batch_2 = [{"hwnd": 0x8, "title": "Wizard"}]
        batches = [hits_batch_1, hits_batch_2]
        batch_idx = {"i": 0}

        def find(p, t):
            idx = batch_idx["i"]
            batch_idx["i"] += 1
            return batches[idx] if idx < len(batches) else []

        w = modal_watch.ModalWatcher(pid=5, interval=0.01, _find=find,
                                     _post=lambda h: True)
        w.watch_once()
        w.watch_once()
        self.assertEqual(len(w.closures), 2)
        self.assertEqual(w.closures[0]["hwnd"], 0x7)
        self.assertEqual(w.closures[1]["hwnd"], 0x8)

    def test_watcher_context_manager_exception_safety(self):
        w = modal_watch.ModalWatcher(pid=5, interval=0.01,
                                     _find=lambda p, t: [],
                                     _post=lambda h: True)
        stopped = {"called": False}
        orig_stop = w.stop

        def track_stop():
            stopped["called"] = True
            return orig_stop()

        w.stop = track_stop
        try:
            with w:
                raise ValueError("test exception")
        except ValueError:
            pass
        self.assertTrue(stopped["called"])


if __name__ == "__main__":
    unittest.main()
