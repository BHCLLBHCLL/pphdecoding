#!/usr/bin/env python3
"""host_watchdog 边缘路径测试（J6.2 回归强化）。

覆盖：error 重试耗尽、completed_no_return、_rewrite_last_row、
log_size / has_end_marker 独立辅助函数。
"""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import host_watchdog  # noqa: E402


class FakeEnv:
    """复用 test_host_watchdog 的 FakeEnv 模式。"""

    def __init__(self, tmp: Path, hang_attempts=(), fail_attempts=()):
        self.tmp = tmp
        self.hang_attempts = set(hang_attempts)
        self.fail_attempts = set(fail_attempts)
        self.killed: list[int] = []
        self.dumps: list[tuple[int, str]] = []
        self.boots = 0
        self.hang_events: dict[int, threading.Event] = {}
        self.kill_all_calls = 0
        self.kill_all_clears = False
        self._host_present = True
        self._log = tmp / "flow.log"
        self._log.write_text("start\ns001=0\n", encoding="utf-8")

    def worker(self, vbs, timeout):
        self.n = getattr(self, "n", 0) + 1
        if self.n in self.hang_attempts:
            ev = threading.Event()
            self.hang_events[self.n] = ev
            ev.wait(30)
            raise RuntimeError("worker still blocked (fake hang)")
        if self.n in self.fail_attempts:
            return {"ok": False, "backend": "fake"}
        self._log.write_text(self._log.read_text(encoding="utf-8")
                             + "end\n", encoding="utf-8")
        return {"ok": True, "backend": "fake"}

    def dump(self, pid, path):
        self.dumps.append((pid, str(path)))
        Path(str(path)).write_bytes(b"MDMP")
        return str(path)

    def kill(self, pid):
        self.killed.append(pid)
        for ev in self.hang_events.values():
            ev.set()

    def kill_all(self):
        self.kill_all_calls += 1
        if self.kill_all_clears:
            self._host_present = False

    def diag(self, pid):
        return {"pid": pid, "CPU": 1.0}

    def boot(self):
        self.boots += 1
        return 4242

    def hosts(self):
        return [1111] if self._host_present else []


def make_executor(env: FakeEnv, **kw):
    tmp = env.tmp
    opts = dict(idle_limit=0.3, poll=0.05, attempts=2,
                error_retry_delay=0.0)
    opts.setdefault("kill_all_fn", env.kill_all)
    opts.update(kw)
    return host_watchdog.FlowExecutor(
        tmp / "flow.vbs", tmp / "flow.log", name="flow",
        work_dir=tmp, worker_fn=env.worker, boot_fn=env.boot,
        dump_fn=env.dump, kill_fn=env.kill, diag_fn=env.diag,
        host_fn=env.hosts, **opts)


class TestErrorRetryExhaustion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_watchdog_edge"
        self.tmp.mkdir(exist_ok=True)
        for p in self.tmp.iterdir():
            p.unlink()
        (self.tmp / "flow.vbs").write_text("' fake vbs\r\n",
                                           encoding="mbcs")

    def test_error_retry_exhausted_triggers_boot(self):
        # fail 3 次（无 end marker）→ 第 2 次重试触发 boot；最终 error
        # attempts=2 但 error 重试不消耗 n，所以需要更多 fail
        env = FakeEnv(self.tmp, fail_attempts=(1, 2, 3, 4, 5))
        ex = make_executor(env, attempts=2)
        res = ex.execute()
        self.assertFalse(res["ok"])
        self.assertEqual(res["outcome"], "error")
        self.assertGreaterEqual(env.boots, 1)

    def test_error_retry_does_not_consume_attempts(self):
        # fail 1 次 + 成功 → attempts 列表只有 2 项（重试不消耗 n）
        env = FakeEnv(self.tmp, fail_attempts=(1,))
        ex = make_executor(env)
        res = ex.execute()
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["attempts"]), 2)
        self.assertEqual(res["attempts"][0]["outcome"], "error")
        self.assertEqual(res["attempts"][1]["outcome"], "ok")


class TestCompletedNoReturn(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_watchdog_edge2"
        self.tmp.mkdir(exist_ok=True)
        for p in self.tmp.iterdir():
            p.unlink()
        (self.tmp / "flow.vbs").write_text("' fake vbs\r\n",
                                           encoding="mbcs")

    def test_completed_no_return_path(self):
        # worker 挂起但日志已有 end → completed_no_return
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        # 预先写 end 到日志
        env._log.write_text("start\ns001=0\nend\n", encoding="utf-8")
        ex = make_executor(env)
        res = ex.execute()
        self.assertTrue(res["ok"])
        self.assertEqual(res["outcome"], "completed_no_return")
        self.assertTrue(res["attempts"][0].get("rebooted"))


class TestRewriteLastRow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_watchdog_edge3"
        self.tmp.mkdir(exist_ok=True)
        for p in self.tmp.iterdir():
            p.unlink()
        (self.tmp / "flow.vbs").write_text("' fake vbs\r\n",
                                           encoding="mbcs")

    def test_rewrite_last_row_updates_jsonl(self):
        env = FakeEnv(self.tmp)
        ex = make_executor(env)
        jsonl = ex.characterization_path
        jsonl.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        ex._rewrite_last_row({"a": 2, "b": "updated"})
        rows = jsonl.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 2)
        last = json.loads(rows[-1])
        self.assertEqual(last["b"], "updated")

    def test_rewrite_last_row_empty_file_no_crash(self):
        env = FakeEnv(self.tmp)
        ex = make_executor(env)
        jsonl = ex.characterization_path
        jsonl.write_text("", encoding="utf-8")
        ex._rewrite_last_row({"a": 1})
        missing = self.tmp / "nonexistent.jsonl"
        ex.characterization_path = missing
        ex._rewrite_last_row({"a": 1})


class TestHelperFunctions(unittest.TestCase):
    def test_log_size_missing_file(self):
        self.assertEqual(host_watchdog.log_size(Path("_no_such.log")), 0)

    def test_has_end_marker_true_and_false(self):
        tmp = Path(__file__).parent / "_tmp_watchdog_edge4"
        tmp.mkdir(exist_ok=True)
        log_with = tmp / "with_end.log"
        log_with.write_text("start\nend\n", encoding="utf-8")
        self.assertTrue(host_watchdog.has_end_marker(log_with))

        log_without = tmp / "no_end.log"
        log_without.write_text("start\n", encoding="utf-8")
        self.assertFalse(host_watchdog.has_end_marker(log_without))

        self.assertFalse(host_watchdog.has_end_marker(
            Path("_no_such.log")))


if __name__ == "__main__":
    unittest.main()
