"""P12-I I1：域 5 reopen 正式 gate（DEV_PLAN §20.1）。

配方：结束残留宿主（§18.4 遗留③应对：挂起即换宿主实例）→
Kicker 冷启动新宿主 → :class:`ModalWatcher` 后台看守 Initial
Wizard 模态 → 复用 P12-E 编排器跑 reopen flow 取官方 gate
（err 全 0 + mg_/octree_ alive + end 标记）。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from automation import modal_watch  # noqa: E402


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(
        name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def kill_stale_hosts() -> list[int]:
    pids = modal_watch.host_pids()
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=15)
        print("killed stale host pid", pid)
    return pids


def main() -> int:
    t0 = time.time()
    stale = kill_stale_hosts()
    time.sleep(3)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    boot = subprocess.run(
        [sys.executable, str(ROOT / "scratch" / "_p12e_boot.py")],
        capture_output=True, text=True, timeout=420, env=env)
    sys.stdout.write(boot.stdout)
    if boot.returncode != 0:
        sys.stderr.write(boot.stderr)
        print("[i1] BOOT FAILED rc=" + str(boot.returncode))
        return 2
    line = [ln for ln in boot.stdout.splitlines()
            if ln.startswith("host ready, pid")]
    host_pid = int(line[-1].split()[-1]) if line else \
        (modal_watch.host_pids() or [0])[0]
    print("[i1] fresh host pid=" + str(host_pid)
          + " (stale killed: " + str(stale) + ")")

    run = load_module("p12e_run", "tools/_p12e_e2e_run.py")
    with modal_watch.ModalWatcher(pid=host_pid) as watcher:
        rc = run.main(["reopen"])
    print("[i1] watcher closures: " + str(watcher.closures))
    print("[i1] elapsed " + str(round(time.time() - t0, 1)) + "s")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
