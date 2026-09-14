"""R35-1 走注册表：ProgID → CLSID → TypeLib → 真实成员表（离线）。"""
import sys, winreg
sys.path.insert(0, ".")
import console_utf8; console_utf8.enable()
import pythoncom

PROGID = "scFLOWpre_Bx64net.Application.2025"


def clsid_of(progid):
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID") as k:
        return winreg.QueryValueEx(k, "")[0]


def typelib_of(clsid):
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                        "CLSID\\" + clsid + "\\TypeLib") as k:
        return winreg.QueryValueEx(k, "")[0]


def tlb_path(libid):
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib\\" + libid) as k:
        vers = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
    out = []
    for v in vers:
        for plat in ("win64", "win32", ""):
            try:
                sub = ("TypeLib\\" + libid + "\\" + v
                       + ("\\" + plat if plat else ""))
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, sub) as k2:
                    out.append((v, plat, winreg.QueryValueEx(k2, "")[0]))
            except OSError:
                continue
    return out


clsid = clsid_of(PROGID)
print("ProgID:", PROGID, "CLSID:", clsid)
libid = typelib_of(clsid)
print("LibID:", libid)
paths = tlb_path(libid)
for v, plat, p in paths:
    print("  ver", v, plat, p)
    try:
        lib = pythoncom.LoadTypeLib(p)
    except Exception as exc:
        print("     load failed:", type(exc).__name__, exc)
        continue
    n = lib.GetTypeInfoCount()
    names = []
    for i in range(n):
        try:
            names.append(lib.GetDocumentation(i)[0])
        except Exception:
            names.append("?")
    print("     types:", n, names[:12])
