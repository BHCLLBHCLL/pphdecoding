#!/usr/bin/env python3
"""host_watchdog 离线单测：注入假 worker/dump/kill/boot，不触真宿主。"""

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
    """worker/日志/宿主命假的受控环境。"""

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

    # worker：hang_attempts 中的尝试号阻塞（模拟宿主侧 COM 不返回），
    # fail_attempts 返回 ok=False（模拟宿主忙拒绝 ExecuteVBSWithFile）
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
        # 对齐真实行为：杀宿主后阻塞中的 COM 调用随连接断开退出
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


class TestFlowExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_watchdog"
        self.tmp.mkdir(exist_ok=True)
        for p in self.tmp.iterdir():
            p.unlink()
        (self.tmp / "flow.vbs").write_text("' fake vbs\r\n",
                                           encoding="mbcs")
        (self.tmp / "f.vbs").write_text("' fake vbs\r\n", encoding="mbcs")

    def test_ok_first_attempt(self):
        env = FakeEnv(self.tmp, hang_attempts=())
        res = make_executor(env).execute()
        self.assertTrue(res["ok"])
        self.assertEqual(res["outcome"], "ok")
        self.assertEqual(len(res["attempts"]), 1)
        self.assertEqual(env.killed, [])
        self.assertEqual(env.boots, 0)

    def test_hang_then_recover(self):
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        res = make_executor(env).execute()
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["attempts"]), 2)
        self.assertEqual(res["attempts"][0]["outcome"], "hung")
        # 挂起处置链：诊断含宿主 + 转储 + 杀宿主 + 重启
        self.assertEqual(env.dumps, [(1111, env.dumps[0][1])])
        self.assertEqual(env.killed, [1111])
        self.assertEqual(env.boots, 1)

    def test_hang_all_attempts(self):
        env = FakeEnv(self.tmp, hang_attempts=(1, 2))
        res = make_executor(env).execute()
        self.assertFalse(res["ok"])
        self.assertEqual(res["outcome"], "hung")
        self.assertEqual(len(res["attempts"]), 2)
        self.assertEqual(env.boots, 2)

    def test_host_gone_early_detection(self):
        # 宿主消失 + worker 阻塞 → 早判 hung（不等满 idle_limit）
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        ex = make_executor(env, idle_limit=420.0, gone_check_after=0.3,
                           gone_confirm=0.3)
        # 首次查询宿主已消失（attempt 1）；重启后宿主在场（attempt 2）
        calls = {"n": 0}

        def hosts():
            calls["n"] += 1
            return [] if calls["n"] == 1 else [1111]

        ex._host_fn = hosts
        res = ex.execute()
        self.assertTrue(res["ok"])
        self.assertEqual(res["attempts"][0]["outcome"], "hung")
        self.assertIn("host process gone", res["attempts"][0].get(
            "reason", "") or self._last_reason(self.tmp))
        self.assertEqual(env.boots, 1)

    @staticmethod
    def _last_reason(tmp):
        rows = [json.loads(ln) for ln in
                (tmp / "hang_characterization.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        return rows[0]["reason"]

    def test_characterization_rows(self):
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        make_executor(env).execute()
        rows = [json.loads(ln) for ln in
                (self.tmp / "hang_characterization.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        outcomes = [r["outcome"] for r in rows]
        self.assertEqual(outcomes, ["hung", "ok"])
        hung = rows[0]
        self.assertEqual(hung["flow"], "flow")
        self.assertEqual(hung["host_pids"], [1111])
        self.assertIn("dump", hung)
        self.assertGreaterEqual(hung["idle_s"], 0.3)
        self.assertIn("vbs_bytes", hung)

    def test_worker_exception_recorded_as_fail(self):
        def bad_worker(vbs, timeout):
            raise RuntimeError("com dead")

        ex = host_watchdog.FlowExecutor(
            self.tmp / "f.vbs", self.tmp / "f.log", name="f",
            idle_limit=0.3, poll=0.05, attempts=1, work_dir=self.tmp,
            worker_fn=bad_worker, boot_fn=lambda: 1, dump_fn=lambda p, d: None,
            kill_fn=lambda p: None, diag_fn=lambda p: {},
            host_fn=lambda: [], kill_all_fn=lambda: None)
        res = ex.execute()
        self.assertFalse(res["ok"])
        self.assertFalse(res["attempts"][0]["run"].get("ok", True))

    def test_kill_fallback_and_zombie_recorded(self):
        # kill_fn 杀不死（宿主仍在）→ 按映像名兜底 kill_all 仍清不掉
        # → 台账记 zombie（cold_boot 前置清场是最后防线）
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        env.kill_all_clears = False
        ex = make_executor(env, kill_settle=0.01)
        res = ex.execute()
        self.assertEqual(env.kill_all_calls, 1)
        rows = [json.loads(ln) for ln in
                (self.tmp / "hang_characterization.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0].get("zombie"), [1111])

    def test_kill_all_clears_no_zombie(self):
        env = FakeEnv(self.tmp, hang_attempts=(1,))
        env.kill_all_clears = True
        ex = make_executor(env, kill_settle=0.01)
        res = ex.execute()
        self.assertTrue(res["ok"])
        self.assertEqual(env.kill_all_calls, 1)
        rows = [json.loads(ln) for ln in
                (self.tmp / "hang_characterization.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        self.assertNotIn("zombie", rows[0])

    def test_error_no_end_retried_then_ok(self):
        # 宿主忙拒绝（ok=False + 日志无 end）→ 同宿主重跑一次成功
        env = FakeEnv(self.tmp, fail_attempts=(1,))
        ex = make_executor(env)
        res = ex.execute()
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["attempts"]), 2)
        self.assertEqual(res["attempts"][0]["outcome"], "error")
        self.assertEqual(res["attempts"][1]["outcome"], "ok")
        self.assertEqual(env.boots, 0)  # 不动宿主

    def test_error_with_end_not_retried(self):
        # 日志完整（有 end）的 error 不重试（真业务失败）
        env = FakeEnv(self.tmp)
        orig_worker = env.worker

        def worker(vbs, timeout):
            r = orig_worker(vbs, timeout)
            if getattr(env, "n", 0) == 1:
                return {"ok": False, "backend": "fake"}
            return r

        env.worker = worker
        ex = make_executor(env)
        res = ex.execute()
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["attempts"]), 1)


class TestWriteMinidump(unittest.TestCase):
    def test_invalid_pid_returns_none(self):
        # pid 0xAFFFFF 基本不存在；OpenProcess 失败 → None（不抛）
        self.assertIsNone(host_watchdog.write_minidump(
            0xAFFFFF, Path("_no_such_dump.dmp")))


if __name__ == "__main__":
    unittest.main()
