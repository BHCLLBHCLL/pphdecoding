/*
 * scflow_bridge.cpp — M2 NativeBridge 原型实现。
 *
 * 仅做模块加载与符号解析探测，不调用任何 C++ 类方法。
 * 编译：native/build.ps1（MSVC Build Tools）。
 */
#include "scflow_bridge.h"

#include <windows.h>

#include <string>
#include <unordered_map>
#include <vector>

namespace {

struct ModuleEntry {
    std::wstring name;
    HMODULE handle = nullptr;
    int resolved = 0;
};

std::vector<ModuleEntry> g_modules;
std::wstring g_programs_dir;

const wchar_t* kKeyDlls[] = {
    L"scFLOWpreCmd_Bx64net.dll",
    L"scFLOWpreAPI_Bx64.dll",
    L"scFLOWpreDB_Bx64.dll",
    L"scFLOWpreGUI_Bx64net.dll",
    L"SCTpreCore_Dx64.dll",
    L"SCTpreLib_Dx64.dll",
    L"SCTpreSolver_Dx64.dll",
    L"SCTprime_Bx64.dll",
    L"ParasolidGW_Bx64.dll",
    L"ImportGeometry_Bx64.dll",
    L"ZipLibrary.dll",
};

const char* kProbeSymbols[] = {
    "?ExecuteVBS@scFLOWpre@@YA_NPEB_W@Z",
    "?CreateShapeGroupSet@SCTprime@@YA?AVIShapeGroupSet@1@PEB_W@Z",
    "?InitSCTpreLib1@@YAHXZ",
    "?ExpandZip@@YAHPEB_W0@Z",
};

}  // namespace

extern "C" {

SCF_API int scf_initialize(const wchar_t* programs_dir) {
    if (programs_dir == nullptr || *programs_dir == L'\0') {
        return -1;
    }
    g_programs_dir = programs_dir;
    g_modules.clear();
    int loaded = 0;
    for (const wchar_t* name : kKeyDlls) {
        std::wstring path = g_programs_dir + L"\\" + name;
        HMODULE h = LoadLibraryW(path.c_str());
        ModuleEntry entry;
        entry.name = name;
        entry.handle = h;
        if (h != nullptr) {
            for (const char* sym : kProbeSymbols) {
                if (GetProcAddress(h, sym) != nullptr) {
                    ++entry.resolved;
                }
            }
            ++loaded;
        }
        g_modules.push_back(entry);
    }
    return loaded;
}

SCF_API int scf_resolve_symbol(const wchar_t* dll_name, const char* symbol) {
    if (dll_name == nullptr || symbol == nullptr) {
        return -1;
    }
    for (ModuleEntry& entry : g_modules) {
        if (entry.handle != nullptr && entry.name == dll_name) {
            return GetProcAddress(entry.handle, symbol) != nullptr ? 1 : 0;
        }
    }
    return 0;
}

SCF_API int scf_status(wchar_t* buffer, int buffer_len) {
    if (buffer == nullptr || buffer_len <= 0) {
        return -1;
    }
    std::wstring out;
    for (const ModuleEntry& entry : g_modules) {
        out += entry.name;
        if (entry.handle == nullptr) {
            out += L" = not-loaded\n";
        } else {
            out += L" = loaded, symbols=";
            out += std::to_wstring(entry.resolved);
            out += L"\n";
        }
    }
    out += L"programs_dir = " + g_programs_dir + L"\n";
    const size_t copy_len = (out.size() < static_cast<size_t>(buffer_len - 1))
                                ? out.size()
                                : static_cast<size_t>(buffer_len - 1);
    wcsncpy_s(buffer, buffer_len, out.c_str(), copy_len);
    buffer[copy_len] = L'\0';
    return static_cast<int>(copy_len);
}

SCF_API void scf_finalize(void) {
    for (ModuleEntry& entry : g_modules) {
        if (entry.handle != nullptr) {
            FreeLibrary(entry.handle);
            entry.handle = nullptr;
        }
    }
    g_modules.clear();
    g_programs_dir.clear();
}

}  // extern "C"
