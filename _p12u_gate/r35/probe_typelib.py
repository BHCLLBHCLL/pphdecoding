"""R35-1：能否**离线**从宿主二进制里读出类型库（真实成员表）？"""
import glob, os, sys
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
try:
    import pythoncom
    print("pythoncom OK", pythoncom.__file__)
except Exception as exc:
    print("no pythoncom:", exc); raise SystemExit(1)

cands = []
for root in (r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64",):
    for pat in ("*.exe", "*.dll", "*.ocx", "*.tlb"):
        cands += glob.glob(os.path.join(root, pat))
print("binaries:", len(cands))
import win32com.client.gencache  # noqa: F401  仅探测可用性
hits = []
for path in cands:
    low = os.path.basename(path).lower()
    if not any(k in low for k in ("scflowpre", "sctpre", "scflow")):
        continue
    try:
        lib = pythoncom.LoadTypeLib(path)
    except Exception as exc:
        print("  no tlb:", os.path.basename(path), type(exc).__name__)
        continue
    n = lib.GetTypeInfoCount()
    hits.append((path, n))
    print("  TLB:", os.path.basename(path), "types:", n)
print("提交流程可用:", len(hits) > 0)
