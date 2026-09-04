#!/usr/bin/env python3
"""modal_watch 离线单测：注入假枚举/投递，不触真实窗口。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import modal_watch  # noqa: E402


def fake_enum(wins):
    def run(cb):
        for hwnd, cls, title, pid, visible in wins:
            if not cb(hwnd, 0):
                break
    return run


WINS = [
    (0x1, "#32770", "Initial Wizard     Project ( 1/6 ) step", 100, True),
    (0x2, "#32770", "Save changes?", 100, True),
    (0x3, "#32770", "Initial Wizard     Project ( 1/6 ) step", 200, True),
    (0x4, "#32770", "Initial Wizard     Project ( 1/6 ) step", 100, False),
    (0x5, "Afx:0", "start - STpre", 100, True),
]


class TestFindVisibleDialogs(unittest.TestCase):
    def test_filters_class_pid_title_visibility(self):
        meta = {w[0]: w for w in WINS}
        found = modal_watch.find_visible_dialogs(
            pid=100, title_contains="Initial Wizard",
            _enum=fake_enum(WINS),
            _text=lambda h: meta[h][2], _cls=lambda h: meta[h][1],
            _wpid=lambda h: meta[h][3], _vis=lambda h: meta[h][4])
        self.assertEqual([f["hwnd"] for f in found], [0x1])
        self.assertIn("Initial Wizard", found[0]["title"])

    def test_no_filter_returns_all_visible_dialogs(self):
        meta = {w[0]: w for w in WINS}
        found = modal_watch.find_visible_dialogs(
            _enum=fake_enum(WINS), _text=lambda h: meta[h][2],
            _cls=lambda h: meta[h][1],
            _wpid=lambda h: meta[h][3], _vis=lambda h: meta[h][4])
        self.assertEqual(sorted(f["hwnd"] for f in found), [0x1, 0x2, 0x3])


class TestCloseDialogs(unittest.TestCase):
    def test_close_posts_wm_close_only_to_matches(self):
        meta = {w[0]: w for w in WINS}
        posted = []

        def find(pid, title):
            return modal_watch.find_visible_dialogs(
                pid, title, _enum=fake_enum(WINS),
                _text=lambda h: meta[h][2], _cls=lambda h: meta[h][1],
                _wpid=lambda h: meta[h][3], _vis=lambda h: meta[h][4])

        closed = modal_watch.close_dialogs(
            100, "Initial Wizard", _find=find,
            _post=lambda h: posted.append(h) or True)
        self.assertEqual([c["hwnd"] for c in closed], [0x1])
        self.assertEqual(posted, [0x1])

    def test_post_failure_not_counted(self):
        found = [{"hwnd": 0x9, "title": "Initial Wizard"}]
        closed = modal_watch.close_dialogs(
            None, "Initial Wizard", _find=lambda p, t: found,
            _post=lambda h: False)
        self.assertEqual(closed, [])


class TestConfirmYes(unittest.TestCase):
    """Confirm Yes/No 模态（2023.2 CAB 载入 / patch 导入确认）。"""

    def _fake_children(self, buttons):
        def run(cb, hwnd):
            for hwnd_c, cls, title in buttons:
                if not cb(hwnd_c, 0):
                    break
        return run

    CONFIRM = [
        (0x10, "#32770", "Confirm", 300, True),
    ]
    BUTTONS = [
        (0x11, "Button", "是(&Y)"),
        (0x12, "Button", "否(&N)"),
        (0x13, "Static", "Load a CAB file created on the older version"),
    ]

    def test_finds_confirm_and_yes_button(self):
        texts = {0x10: "Confirm", 0x11: "是(&Y)", 0x12: "否(&N)",
                 0x13: "Load a CAB file"}
        clss = {0x10: "#32770", 0x11: "Button", 0x12: "Button",
                0x13: "Static"}
        found = modal_watch.find_confirm_yes(
            pid=300, _enum=fake_enum(self.CONFIRM),
            _text=lambda h: texts.get(h, ""), _cls=lambda h: clss.get(h, ""),
            _wpid=lambda h: 300, _vis=lambda h: True,
            _children=self._fake_children(self.BUTTONS))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["yes_hwnd"], 0x11)

    def test_clicks_yes_not_no(self):
        posted = []
        clicked = modal_watch.click_confirm_yes(
            _find=lambda p: [{"hwnd": 0x10, "title": "Confirm",
                              "yes_hwnd": 0x11}],
            _click=lambda h: posted.append(h) or True)
        self.assertEqual(posted, [0x11])
        self.assertEqual(clicked, [{"hwnd": 0x10, "title": "Confirm",
                                    "yes_hwnd": 0x11}])

    def test_no_button_no_click(self):
        clicked = modal_watch.click_confirm_yes(
            _find=lambda p: [{"hwnd": 0x10, "title": "Confirm",
                              "yes_hwnd": None}],
            _click=lambda h: self.fail("should not click"))
        self.assertEqual(clicked, [])

    def test_non_confirm_dialog_ignored(self):
        wins = [(0x20, "#32770", "Confirm", 300, True),
                (0x21, "#32770", "Save changes?", 300, True)]
        texts = {w[0]: w[2] for w in wins}
        clss = {w[0]: w[1] for w in wins}
        found = modal_watch.find_confirm_yes(
            pid=300, _enum=fake_enum(wins),
            _text=lambda h: texts.get(h, ""), _cls=lambda h: clss.get(h, ""),
            _wpid=lambda h: 300, _vis=lambda h: True,
            _children=self._fake_children(self.BUTTONS))
        self.assertEqual([f["hwnd"] for f in found], [0x20])


class TestModalWatcher(unittest.TestCase):
    def test_watch_once_records_closures(self):
        hits = [{"hwnd": 0x7, "title": "Initial Wizard"}]
        w = modal_watch.ModalWatcher(pid=5, interval=0.01,
                                     _find=lambda p, t: hits,
                                     _post=lambda h: True)
        n = w.watch_once()
        self.assertEqual(n, 1)
        self.assertEqual(w.closures[0]["hwnd"], 0x7)
        self.assertIn("t", w.closures[0])

    def test_start_stop_lifecycle(self):
        calls = {"n": 0}

        def find(p, t):
            calls["n"] += 1
            return []

        w = modal_watch.ModalWatcher(pid=5, interval=0.01, _find=find)
        with w:
            import time as _t
            _t.sleep(0.05)
        n = calls["n"]
        self.assertGreaterEqual(n, 1)
        _t.sleep(0.05)
        self.assertEqual(calls["n"], n)  # stop 后不再轮询


if __name__ == "__main__":
    unittest.main()
