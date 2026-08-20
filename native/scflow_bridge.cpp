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

struct PipelineSymbol {
    const wchar_t* module;
    const char* symbol;
};

const PipelineSymbol kPipelineSymbols[] = {
    {L"SCTprime_Bx64.dll",
     "?CreateShapeGroupSet@SCTprime@@YA?AVIShapeGroupSet@1@PEB_W@Z"},
    {L"SCTprime_Bx64.dll",
     "?CreateShapeGroup@IShapeGroupSet@SCTprime@@QEAA?AVIShapeGroup@2@PEB_WAEAV?$vector@VISNode@SCTprime@@V?$allocator@VISNode@SCTprime@@@std@@@std@@@Z"},
    {L"SCTprime_Bx64.dll",
     "?CreateMDL@IShapeGroup@SCTprime@@QEAA_NXZ"},
    {L"SCTprime_Bx64.dll",
     "?CreateFacetOctree@IShapeGroup@SCTprime@@QEAA?AW4ErrorCode@2@PEB_WAEAVIOctree@2@@Z"},
    {L"SCTprime_Bx64.dll",
     "?ExecuteWrapping@IShapeGroup@SCTprime@@QEAA?AW4ErrorCode@2@XZ"},
    {L"SCTprime_Bx64.dll",
     "?CreateMeshOctreeByDefaultParam@IVMDL@SCTprime@@QEAA?AW4ErrorCode@2@AEAVIOctree@2@@Z"},
    {L"SCTprime_Bx64.dll",
     "?ConvertFacetToXT@SCTprime@@YA?AW4ErrorCode@1@PEB_W0@Z"},
    {L"ZipLibrary.dll", "?ExpandZip@@YAHPEB_W0@Z"},
    {L"scFLOWpreAPI_Bx64.dll", "?ExecuteVBS@scFLOWpre@@YA_NPEB_W@Z"},
};

const char* kCreateShapeGroupSetSymbol =
    "?CreateShapeGroupSet@SCTprime@@YA?AVIShapeGroupSet@1@PEB_W@Z";
const char* kCreateShapeGroupSymbol =
    "?CreateShapeGroup@IShapeGroupSet@SCTprime@@QEAA?AVIShapeGroup@2@PEB_WAEAV?$vector@VISNode@SCTprime@@V?$allocator@VISNode@SCTprime@@@std@@@std@@@Z";
const char* kCreateMDLSymbol =
    "?CreateMDL@IShapeGroup@SCTprime@@QEAA_NXZ";
const char* kCreateFacetOctreeSymbol =
    "?CreateFacetOctree@IShapeGroup@SCTprime@@QEAA?AW4ErrorCode@2@PEB_WAEAVIOctree@2@@Z";
const char* kExecuteWrappingSymbol =
    "?ExecuteWrapping@IShapeGroup@SCTprime@@QEAA?AW4ErrorCode@2@XZ";
const char* kCreateMeshOctreeSymbol =
    "?CreateMeshOctreeByDefaultParam@IVMDL@SCTprime@@QEAA?AW4ErrorCode@2@AEAVIOctree@2@@Z";
const char* kConvertFacetToXTSymbol =
    "?ConvertFacetToXT@SCTprime@@YA?AW4ErrorCode@1@PEB_W0@Z";

struct PipelineApi {
    void* create_set = nullptr;
    void* create_group = nullptr;
    void* create_mdl = nullptr;
    void* create_facet_octree = nullptr;
    void* execute_wrapping = nullptr;
    void* create_mesh_octree = nullptr;
    void* convert_facet_to_xt = nullptr;
};

PipelineApi g_pipeline_api;

// SCTprime private global (module base + RVA). 0xD212B8 was derived for
// 5225.20302.20251223 and re-verified on the installed 6025.20101.20251128:
//   - CreateShapeGroupSet does `lea rcx,[rip+G]; call get_[G+8]` (0x981880),
//     i.e. the host context object lives at [G+8] in BOTH builds;
//   - live-process ReadProcessMemory shows [G+8] non-null in Kicker-launched
//     instances (and null in a COM-LocalServer transient instance, which is
//     expected: that path lacks the Kicker product-key setup);
//   - the OLD [ctx+0xF8] document slot no longer matches the new build
//     (CreateShapeGroupSet now reads [ctx+0x4C8] for its group registry),
//     so context_ready is defined as [G+8] != null only.
const unsigned __int64 kSctGlobalRva = 0xD212B8ull;
const int kInterfaceObjSize = 16;

int g_last_exception_code = 0;
void* g_last_exception_addr = nullptr;

HMODULE find_module_handle(const wchar_t* name) {
    for (const ModuleEntry& entry : g_modules) {
        if (entry.handle != nullptr && entry.name == name) {
            return entry.handle;
        }
    }
    return nullptr;
}

int seh_filter(unsigned long code, PEXCEPTION_POINTERS ep) {
    g_last_exception_code = static_cast<int>(code);
    g_last_exception_addr = ep->ExceptionRecord->ExceptionAddress;
    return EXCEPTION_EXECUTE_HANDLER;
}

bool call_create_set_guarded(const wchar_t* name, void* out_obj) {
    __try {
        typedef void* (*CreateSetFn)(void* ret, const wchar_t* name);
        CreateSetFn fn = reinterpret_cast<CreateSetFn>(g_pipeline_api.create_set);
        fn(out_obj, name);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

bool call_create_group_guarded(void* thisptr, const wchar_t* name,
                               void* out_obj, void* nodes) {
    __try {
        typedef void* (*CreateGroupFn)(void* thisptr, void* ret,
                                       const wchar_t* name, void* nodes);
        CreateGroupFn fn =
            reinterpret_cast<CreateGroupFn>(g_pipeline_api.create_group);
        fn(thisptr, out_obj, name, nodes);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

bool call_create_mdl_guarded(void* thisptr, bool* result) {
    __try {
        typedef bool (*CreateMdlFn)(void* thisptr);
        CreateMdlFn fn =
            reinterpret_cast<CreateMdlFn>(g_pipeline_api.create_mdl);
        *result = fn(thisptr);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

// P11: 四个深管线成员/自由函数的 SEH 保护调用。返回值 ErrorCode 是
// 4 字节 enum；引用参数（IOctree&）在 x64 下按指针传。
bool call_create_facet_octree_guarded(void* thisptr, const wchar_t* name,
                                      void* out_octree, int* error_code) {
    __try {
        typedef int (*Fn)(void*, const wchar_t*, void*);
        Fn fn = reinterpret_cast<Fn>(g_pipeline_api.create_facet_octree);
        *error_code = fn(thisptr, name, out_octree);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

bool call_execute_wrapping_guarded(void* thisptr, int* error_code) {
    __try {
        typedef int (*Fn)(void*);
        Fn fn = reinterpret_cast<Fn>(g_pipeline_api.execute_wrapping);
        *error_code = fn(thisptr);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

bool call_create_mesh_octree_guarded(void* thisptr, void* out_octree,
                                     int* error_code) {
    __try {
        typedef int (*Fn)(void*, void*);
        Fn fn = reinterpret_cast<Fn>(g_pipeline_api.create_mesh_octree);
        *error_code = fn(thisptr, out_octree);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

bool call_convert_facet_to_xt_guarded(const wchar_t* src, const wchar_t* dst,
                                      int* error_code) {
    __try {
        typedef int (*Fn)(const wchar_t*, const wchar_t*);
        Fn fn = reinterpret_cast<Fn>(g_pipeline_api.convert_facet_to_xt);
        *error_code = fn(src, dst);
        return true;
    } __except (seh_filter(GetExceptionInformation()->ExceptionRecord->ExceptionCode,
                           GetExceptionInformation())) {
        return false;
    }
}

int pipeline_context_ready_raw() {
    HMODULE sct = find_module_handle(L"SCTprime_Bx64.dll");
    if (sct == nullptr || g_pipeline_api.create_set == nullptr) {
        return -1;
    }
    // SEH 保护：RVA 0xD212B8 是反汇编锁定的私有全局，若宿主版本布局
    // 变化导致该地址不可读，绝不能让 in-proc 崩溃拖垮 scFLOWpre 进程。
    __try {
        const unsigned char* global =
            reinterpret_cast<const unsigned char*>(sct) + kSctGlobalRva;
        const void* ctx = *reinterpret_cast<void* const*>(global + 8);
        return ctx != nullptr ? 1 : 0;
    } __except (seh_filter(
        GetExceptionInformation()->ExceptionRecord->ExceptionCode,
        GetExceptionInformation())) {
        return -1;
    }
}


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
    HMODULE sct = find_module_handle(L"SCTprime_Bx64.dll");
    if (sct != nullptr) {
        g_pipeline_api.create_set =
            reinterpret_cast<void*>(GetProcAddress(sct, kCreateShapeGroupSetSymbol));
        g_pipeline_api.create_group =
            reinterpret_cast<void*>(GetProcAddress(sct, kCreateShapeGroupSymbol));
        g_pipeline_api.create_mdl =
            reinterpret_cast<void*>(GetProcAddress(sct, kCreateMDLSymbol));
        g_pipeline_api.create_facet_octree =
            reinterpret_cast<void*>(GetProcAddress(sct, kCreateFacetOctreeSymbol));
        g_pipeline_api.execute_wrapping =
            reinterpret_cast<void*>(GetProcAddress(sct, kExecuteWrappingSymbol));
        g_pipeline_api.create_mesh_octree =
            reinterpret_cast<void*>(GetProcAddress(sct, kCreateMeshOctreeSymbol));
        g_pipeline_api.convert_facet_to_xt =
            reinterpret_cast<void*>(GetProcAddress(sct, kConvertFacetToXTSymbol));
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

SCF_API int scf_pipeline_probe(wchar_t* buffer, int buffer_len) {
    if (buffer == nullptr || buffer_len <= 0) {
        return -1;
    }
    std::wstring out;
    for (const PipelineSymbol& item : kPipelineSymbols) {
        out += item.module;
        out += L"|";
        for (const char* c = item.symbol; *c != '\0'; ++c) {
            out += static_cast<wchar_t>(*c);
        }
        out += (scf_resolve_symbol(item.module, item.symbol) == 1)
                   ? L"=1\n"
                   : L"=0\n";
    }
    const size_t copy_len = (out.size() < static_cast<size_t>(buffer_len - 1))
                                ? out.size()
                                : static_cast<size_t>(buffer_len - 1);
    wcsncpy_s(buffer, buffer_len, out.c_str(), copy_len);
    buffer[copy_len] = L'\0';
    return static_cast<int>(copy_len);
}

SCF_API int scf_call_zip_expand(const wchar_t* zip_path,
                                const wchar_t* out_dir) {
    if (zip_path == nullptr || out_dir == nullptr) {
        return -1;
    }
    for (ModuleEntry& entry : g_modules) {
        if (entry.handle != nullptr && entry.name == L"ZipLibrary.dll") {
            typedef int(__cdecl* ExpandZipFn)(const wchar_t*, const wchar_t*);
            ExpandZipFn fn = reinterpret_cast<ExpandZipFn>(
                GetProcAddress(entry.handle, "?ExpandZip@@YAHPEB_W0@Z"));
            return fn != nullptr ? fn(zip_path, out_dir) : -2;
        }
    }
    return -3;
}

SCF_API int scf_pipeline_context_ready(void) {
    return pipeline_context_ready_raw();
}

SCF_API int scf_last_exception_code(void) {
    return g_last_exception_code;
}

SCF_API int scf_pipeline_create_shape_group_set(const wchar_t* name,
                                                void* out_obj, int* err) {
    if (out_obj == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (name == nullptr) {
        return 0;
    }
    if (g_pipeline_api.create_set == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    int ready = pipeline_context_ready_raw();
    if (ready != 1) {
        *err = SCF_ERR_CONTEXT_NOT_READY;
        return 0;
    }
    memset(out_obj, 0, kInterfaceObjSize);
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_create_set_guarded(name, out_obj)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    if (*reinterpret_cast<void**>(out_obj) == nullptr) {
        *err = SCF_ERR_NULL_OBJECT;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_create_shape_group(unsigned __int64 set_handle,
                                            const wchar_t* name,
                                            void* out_obj, int* err) {
    if (set_handle == 0 || out_obj == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (name == nullptr) {
        return 0;
    }
    if (g_pipeline_api.create_group == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    memset(out_obj, 0, kInterfaceObjSize);
    // Empty std::vector<ISNode> under MSVC: three null pointers.
    void* empty_nodes[3] = {nullptr, nullptr, nullptr};
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_create_group_guarded(reinterpret_cast<void*>(set_handle),
                                   name, out_obj, empty_nodes)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    if (*reinterpret_cast<void**>(out_obj) == nullptr) {
        *err = SCF_ERR_NULL_OBJECT;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_create_mdl(unsigned __int64 group_handle,
                                    int* ok, int* err) {
    if (group_handle == 0 || ok == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (g_pipeline_api.create_mdl == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    bool result = false;
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_create_mdl_guarded(reinterpret_cast<void*>(group_handle),
                                 &result)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    *ok = result ? 1 : 0;
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_create_facet_octree(unsigned __int64 group_handle,
                                             const wchar_t* name,
                                             void* out_octree,
                                             int* error_code, int* err) {
    if (group_handle == 0 || name == nullptr || out_octree == nullptr ||
        error_code == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (g_pipeline_api.create_facet_octree == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    memset(out_octree, 0, kInterfaceObjSize);
    *error_code = 0;
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_create_facet_octree_guarded(reinterpret_cast<void*>(group_handle),
                                          name, out_octree, error_code)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_execute_wrapping(unsigned __int64 group_handle,
                                          int* error_code, int* err) {
    if (group_handle == 0 || error_code == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (g_pipeline_api.execute_wrapping == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    *error_code = 0;
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_execute_wrapping_guarded(reinterpret_cast<void*>(group_handle),
                                       error_code)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_create_mesh_octree(unsigned __int64 mdl_handle,
                                            void* out_octree,
                                            int* error_code, int* err) {
    if (mdl_handle == 0 || out_octree == nullptr ||
        error_code == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (g_pipeline_api.create_mesh_octree == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    memset(out_octree, 0, kInterfaceObjSize);
    *error_code = 0;
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_create_mesh_octree_guarded(reinterpret_cast<void*>(mdl_handle),
                                         out_octree, error_code)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
}

SCF_API int scf_pipeline_convert_facet_to_xt(const wchar_t* src,
                                             const wchar_t* dst,
                                             int* error_code, int* err) {
    if (src == nullptr || dst == nullptr ||
        error_code == nullptr || err == nullptr) {
        return 0;
    }
    *err = SCF_ERR_ARG;
    if (g_pipeline_api.convert_facet_to_xt == nullptr) {
        *err = SCF_ERR_SYMBOL;
        return 0;
    }
    *error_code = 0;
    g_last_exception_code = 0;
    g_last_exception_addr = nullptr;
    if (!call_convert_facet_to_xt_guarded(src, dst, error_code)) {
        *err = SCF_ERR_EXCEPTION;
        return 0;
    }
    *err = SCF_ERR_OK;
    return 1;
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
    g_pipeline_api = PipelineApi{};
}

}  // extern "C"
