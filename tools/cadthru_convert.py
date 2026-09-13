#!/usr/bin/env python3
r"""CADthru 独立 COM 转换器 —— STEP/XT/STL/MDL → x_t（P1-0 实测配方）。

背景（2026-09-13 P1-0 验证，见 docs/CODE_STATE_AUDIT_20260906.md §15）
--------------------------------------------------------------------
* `scConverter_Sx64net.Application.2025` **不是** CAD 转换器：它只有
  `GetDialogFLD2FLD / GetDialogFLD2IFLD / GetDialogPFLD` 三个对话框，
  是**场数据（FLD/iFLD）转换器**，与 CAD 无关。
* `CADthru_Bx64net.Application.2025`（HKLM 已注册）才是 CAD 转换面，
  且**不需要 scFLOWpre 宿主、不需要 Kicker、不需要许可**（实测把
  `MSC_LICENSE_FILE`/`CRADLE_LICENSE_FILE` 指向死地址后仍成功）。
* 其 Document 的 `OpenXtFile` 按手册与厂商示例可开 **XT / STEP / STL / MDL**
  （`Manuals\SCT\HTML\VB_Interface_eng\Sct_vb_Pre_PrimeDocument_Class.html`）。

API 形态（踩坑记录，均为实测）
------------------------------
* 服务器是**纯 late-binding IDispatch，无 typelib**：`GetTypeInfo` 失败、
  `dir()` 为空；成员名需用 `_oleobj_.GetIDsOfNames(name)` 探测。
* `Application.CreateDocument` 是**属性**（不是方法）：写成
  `app.CreateDocument`，**不能加括号**（加括号报"找不到成员"）。
* `Document.SaveXTFile` 是**两参**：`(obj, path)`，**不是** `SaveXTFile(path)`
  （单参报"类型不匹配"）。
* `Document.Translate` **不是**格式转换入口（两参调用报类型不匹配），
  真正的转换由 `OpenXtFile` 内部按内容/扩展名完成。

用法
----
    python tools/cadthru_convert.py in.step out.x_t
    python tools/cadthru_convert.py in.step out.x_t --library datakit
    python -c "from tools.cadthru_convert import convert; print(convert('a.step','a.x_t'))"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

#: 仓库根入 sys.path（脚本方式运行时 sys.path[0] 是 tools/，导入不到 pphwriter）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROGIDS = ("CADthru_Bx64net.Application.2025",
           "CADthru_Bx64net.Application.2023")

#: `INT_CADIMPORTLIBRARYPRIORITY` 取值（厂商示例 CadDatakit_prime.vbs 实测）
CAD_LIBRARIES = {"InterOp": 0, "datakit": 1, "CoreTechnologie": 2}

SUPPORTED_IN = {".x_t", ".x_b", ".xmt_txt", ".xmt_bin", ".step", ".stp",
                ".stl", ".mdl", ".ct3", ".pre", ".fld"}


def available() -> bool:
    """CADthru COM 是否已注册（不启动进程）。"""
    try:
        import winreg
        for pid in PROGIDS:
            try:
                winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, pid).Close()
                return True
            except OSError:
                continue
        return False
    except Exception:
        return False


def convert(src: str | Path, dst: str | Path, *,
            library: str = "datakit",
            progid: Optional[str] = None,
            timeout: float = 300.0) -> dict:
    """把 CAD 文件 (`.step/.stp/.x_t/.stl/.mdl`) 转成 `x_t`。

    返回 `{ok, ret, src, dst, size, error_code, message, seconds}`。
    失败不抛异常（除非 COM 不可用），便于批量调用与证据留档。
    """
    # 必须绝对路径：CADthru 是独立进程，工作目录与本进程不同，
    # 相对路径会被它解析到别处（自测实测：ret=0 且文件缺失）。
    src, dst = Path(src).resolve(), Path(dst).resolve()
    out: dict = {"ok": False, "src": str(src), "dst": str(dst), "ret": None,
                 "size": 0, "error_code": None, "message": "", "seconds": 0.0}
    if not src.is_file():
        out["message"] = f"input not found: {src}"
        return out
    try:
        import win32com.client
    except Exception as exc:  # pragma: no cover
        out["message"] = f"pywin32 unavailable: {exc!r}"
        return out
    if not available() and progid is None:
        out["message"] = "CADthru COM not registered (HKCR)"
        return out

    app = None
    t0 = time.time()
    try:
        last = None
        for pid in ([progid] if progid else PROGIDS):
            try:
                app = win32com.client.Dispatch(pid)
                out["progid"] = pid
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if app is None:
            out["message"] = f"Dispatch failed: {last!r}"
            return out
        try:
            app.Visible = True
        except Exception:
            pass
        time.sleep(2.0)                       # 应用初始化
        doc = app.CreateDocument              # 属性！不可加括号
        if library in CAD_LIBRARIES:
            try:
                app.SetConfiguration("STARTUPSETTING",
                                     "INT_CADIMPORTLIBRARYPRIORITY",
                                     CAD_LIBRARIES[library], 0)
            except Exception:
                pass
        asm = doc.OpenXtFile(str(src))        # XT/STEP/STL/MDL 皆可
        if asm is None:
            out["message"] = "OpenXtFile returned Nothing"
            return out
        ret = doc.SaveXTFile(asm, str(dst))   # 两参：(obj, path)
        out["ret"] = ret
        out["size"] = dst.stat().st_size if dst.is_file() else 0
        try:
            out["error_code"] = doc.ErrorCode
            out["message"] = str(doc.GetDocumentMessage)[:400]
        except Exception:
            pass
        out["ok"] = bool(dst.is_file() and out["size"] > 0)
        return out
    except Exception as exc:  # noqa: BLE001
        out["message"] = f"{type(exc).__name__}: {exc}"
        return out
    finally:
        out["seconds"] = round(time.time() - t0, 1)
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass



# ────────────────────────────────────────────────────────────────────────────
# P1-3：转换缓存 + 工程成员写入
# ────────────────────────────────────────────────────────────────────────────

def cache_key(src: str | Path) -> str:
    """源文件内容 sha256（前 16 位）——缓存键。"""
    import hashlib
    h = hashlib.sha256(Path(src).read_bytes()).hexdigest()
    return h[:16]


def convert_cached(src: str | Path, cache_dir: str | Path, *,
                   library: str = "datakit",
                   progid: Optional[str] = None) -> dict:
    """STEP/XT → x_t，带内容寻址缓存（**命中即不再启动 CADthru**）。

    缓存路径：`<cache_dir>/<stem>-<sha16>.x_t`。同一源文件第二次调用时
    直接返回缓存文件（`cached=True`），因此"同一 STEP 二次处理不再需要
    转换器进程"这一 P1-3 验收句可直接由 `cached` 与耗时证实。
    """
    src = Path(src).resolve()
    cache = Path(cache_dir).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    dst = cache / f"{src.stem}-{cache_key(src)}.x_t"
    if dst.is_file() and dst.stat().st_size > 0:
        return {"ok": True, "cached": True, "src": str(src), "dst": str(dst),
                "size": dst.stat().st_size, "seconds": 0.0}
    res = convert(src, dst, library=library, progid=progid)
    res["cached"] = False
    return res


def inject_into_pph(pph_src: str | Path, pph_dst: str | Path,
                    member_name: str, data_path: str | Path) -> dict:
    """把（转换好的）x_t 作为成员写入 PPH 副本（未改动成员字节原样复制）。"""
    import pphwriter
    src = Path(pph_src).resolve()
    dst = Path(pph_dst).resolve()
    data = Path(data_path).read_bytes()
    out: dict = {"ok": False, "pph": str(dst), "member": member_name,
                 "size": len(data)}
    if not src.is_file():
        out["error"] = f"pph not found: {src}"
        return out
    if not data:
        out["error"] = "empty x_t payload"
        return out
    try:
        pphwriter.clone_pph(str(src), str(dst), {member_name: data})
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    import zipfile
    with zipfile.ZipFile(dst) as z:
        have = member_name in z.namelist()
        out["ok"] = have
        out["members"] = len(z.namelist())
        out["member_size"] = z.getinfo(member_name).file_size if have else 0
    return out


def import_cad_to_pph(cad: str | Path, pph_src: str | Path,
                      pph_dst: str | Path, cache_dir: str | Path, *,
                      member: Optional[str] = None,
                      library: str = "datakit",
                      progid: Optional[str] = None) -> dict:
    """一条命令完成 CAD → x_t（带内容寻址缓存）→ 写入 PPH 副本。

    R1-2 验收：同一 CAD 源二次导入为**纯缓存命中 + 注入**，不再启动 CADthru。
    成员名默认取源文件名 stem；缓存键为源文件 sha256 前 16 位，因此同源必得同名。
    """
    cad = Path(cad).resolve()
    src = Path(pph_src).resolve()
    dst = Path(pph_dst).resolve()
    cache = Path(cache_dir).resolve()
    member = member or (cad.stem + ".x_t")
    out: dict = {"ok": False, "cad": str(cad), "pph_in": str(src),
                 "pph_out": str(dst), "member": member}
    if not src.is_file():
        out["error"] = f"pph not found: {src}"
        return out
    conv = convert_cached(cad, cache, library=library, progid=progid)
    out["conversion"] = {k: conv.get(k) for k in
                         ("ok", "cached", "dst", "size", "seconds")}
    if not conv.get("ok"):
        out["error"] = conv.get("message") or "conversion failed"
        return out
    # 幂等：目标 PPH 已存在同名成员且内容一致 → 不重写
    try:
        import zipfile
        if dst.is_file():
            with zipfile.ZipFile(dst) as z:
                if member in z.namelist():
                    if z.read(member) == Path(conv["dst"]).read_bytes():
                        out.update(ok=True, skipped="member already present")
                        out["seconds"] = conv.get("seconds", 0.0)
                        return out
    except Exception:
        pass
    inj = inject_into_pph(src, dst, member, conv["dst"])
    out["inject"] = inj
    out["ok"] = bool(inj.get("ok"))
    out["seconds"] = conv.get("seconds", 0.0)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="CADthru standalone CAD -> x_t（P1-0/P1-3）")
    ap.add_argument("src", nargs="?", default=None,
                    help="输入 CAD 文件（--import-cad 模式下可省略）")
    ap.add_argument("dst", nargs="?", default=None,
                    help="输出 x_t；给了 --cache 时可省略（走缓存路径）")
    ap.add_argument("--library", default="datakit", choices=sorted(CAD_LIBRARIES))
    ap.add_argument("--progid", default=None)
    ap.add_argument("--cache", default=None, help="内容寻址缓存目录（P1-3）")
    ap.add_argument("--import-cad", default=None, metavar="CAD",
                    help="R1-2：一条命令 CAD→x_t(缓存)→写入 PPH（需 --pph/--out-pph/--cache）")
    ap.add_argument("--pph", default=None, help="把 x_t 写成该 PPH 的成员")
    ap.add_argument("--out-pph", default=None, help="PPH 副本输出路径")
    ap.add_argument("--member", default=None, help="成员名（默认 <stem>.x_t）")
    args = ap.parse_args(argv)

    if args.import_cad:
        if not (args.pph and args.out_pph and args.cache):
            ap.error("--import-cad 需要 --pph / --out-pph / --cache")
            return 2
        res = import_cad_to_pph(args.import_cad, args.pph, args.out_pph,
                                args.cache, member=args.member,
                                library=args.library, progid=args.progid)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    if args.cache:
        res = convert_cached(args.src, args.cache, library=args.library,
                             progid=args.progid)
        if res.get("ok") and args.dst:
            import shutil
            shutil.copyfile(res["dst"], args.dst)
            res["also_written"] = str(Path(args.dst).resolve())
    elif args.dst:
        res = convert(args.src, args.dst, library=args.library,
                      progid=args.progid)
    else:
        ap.error("需要 dst 或 --cache")
        return 2
    if res.get("ok") and args.pph and args.out_pph:
        member = args.member or (Path(args.src).stem + ".x_t")
        res["pph_inject"] = inject_into_pph(args.pph, args.out_pph, member,
                                            res["dst"])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
