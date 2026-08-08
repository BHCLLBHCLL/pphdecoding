// abi_probe.cpp - one-shot ABI probe for SCTprime pipeline objects.
// Build: cl /nologo /EHsc /O2 abi_probe.cpp /Fe:abi_probe.exe
// Run:   abi_probe.exe ["C:\\Program Files\\Cradle\\CradleCFD2025.2\\Programs_x64"]
// The probe calls CreateShapeGroupSet / CreateShapeGroup / CreateMDL and
// dumps the returned wrapper bytes so the bridge can be written against
// the real MSVC ABI (sret + this order) without vendor headers.

#include <windows.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

struct ProbeObj {
    alignas(16) unsigned char data[256];
};

// std::vector<ISNode> as seen by MSVC: three pointers, empty = all zero.
struct VecLike {
    void* first;
    void* last;
    void* end;
};

typedef ProbeObj* (*CreateShapeGroupSetFn)(ProbeObj* ret, const wchar_t* name);
typedef unsigned __int64 (*CreateShapeGroupSetRegFn)(const wchar_t* name);
typedef unsigned __int64 (*GetPtrFn)(void* thisptr);
typedef bool (*BoolFn)(void* thisptr);
typedef ProbeObj* (*CreateShapeGroupFn)(void* thisptr, ProbeObj* ret,
                                        const wchar_t* name, VecLike* nodes);
typedef int (*IntFn)(void);
typedef int (*CIntFn)(void);
typedef int (*OpenCadFileFn)(const wchar_t* path, void* node_out);

static HMODULE g_mod = nullptr;
static HMODULE g_lib = nullptr;
static std::vector<HMODULE> g_all;

static bool in_module(const void* p) {
    MEMORY_BASIC_INFORMATION mbi;
    if (p == nullptr ||
        !VirtualQuery(p, &mbi, sizeof(mbi))) {
        return false;
    }
    return mbi.AllocationBase == static_cast<void*>(g_mod);
}

static void dump_obj(const char* label, const ProbeObj* obj) {
    const unsigned __int64* q =
        reinterpret_cast<const unsigned __int64*>(obj->data);
    printf("%s this=%p\n", label, static_cast<const void*>(obj));
    for (int i = 0; i < 4; ++i) {
        printf("  q[%d] = 0x%016llx%s\n", i, q[i],
               in_module(reinterpret_cast<const void*>(q[i]))
                   ? " (in-module)"
                   : "");
    }
}

static void* pick_this(const ProbeObj& obj) {
    const unsigned __int64* q =
        reinterpret_cast<const unsigned __int64*>(obj.data);
    if (q[0] != 0 && in_module(reinterpret_cast<const void*>(q[0]))) {
        printf("  -> first qword looks like a vptr, trying this+8\n");
        return const_cast<unsigned char*>(obj.data) + 8;
    }
    printf("  -> first qword does not look like a vptr, trying this+0\n");
    return const_cast<unsigned char*>(obj.data);
}

static void dump_global(void) {
    const unsigned __int64 rva = 0xD212B8ull;  // 0x180D212B8 - image base
    const unsigned char* p =
        reinterpret_cast<const unsigned char*>(g_mod) + rva;
    const unsigned __int64* q =
        reinterpret_cast<const unsigned __int64*>(p);
    unsigned __int64 f8 = 0;
    if (q[1] != 0) {
        const unsigned __int64* ctx =
            reinterpret_cast<const unsigned __int64*>(q[1] + 0xF8);
        f8 = ctx[0];
    }
    printf("global[%p] q0=0x%016llx q8=0x%016llx f8=0x%016llx\n",
           static_cast<const void*>(p), q[0], q[1], f8);
}

static int report_exception(PEXCEPTION_POINTERS ep) {
    const EXCEPTION_RECORD* rec = ep->ExceptionRecord;
    printf("EXCEPTION code=0x%08lx at=%p info0=0x%p info1=0x%p\n",
           rec->ExceptionCode, static_cast<void*>(rec->ExceptionAddress),
           reinterpret_cast<void*>(rec->ExceptionInformation[0]),
           reinterpret_cast<void*>(rec->ExceptionInformation[1]));
    return EXCEPTION_EXECUTE_HANDLER;
}

static int guarded_create_set(CreateShapeGroupSetFn fn, ProbeObj* obj,
                              const wchar_t* name) {
    __try {
        ProbeObj* ret = fn(obj, name);
        printf("CreateShapeGroupSet returned %p\n",
               static_cast<void*>(ret));
        return 0;
    } __except (report_exception(GetExceptionInformation())) {
        return 1;
    }
}

static int guarded_open_cad(OpenCadFileFn fn, const wchar_t* path,
                            ProbeObj* node_out) {
    __try {
        int rc = fn(path, node_out);
        printf("OpenCadFile -> %d\n", rc);
        return 0;
    } __except (report_exception(GetExceptionInformation())) {
        return 1;
    }
}

static int guarded_create_group(CreateShapeGroupFn fn, void* thisptr,
                                ProbeObj* ret, const wchar_t* name,
                                VecLike* nodes) {
    __try {
        ProbeObj* r = fn(thisptr, ret, name, nodes);
        printf("CreateShapeGroup returned %p\n", static_cast<void*>(r));
        return 0;
    } __except (report_exception(GetExceptionInformation())) {
        return 1;
    }
}

static int guarded_create_mdl(BoolFn fn, void* thisptr) {
    __try {
        bool ok = fn(thisptr);
        printf("CreateMDL -> %d\n", ok ? 1 : 0);
        return 0;
    } __except (report_exception(GetExceptionInformation())) {
        return 1;
    }
}

int wmain(int argc, wchar_t** argv) {
    setvbuf(stdout, nullptr, _IONBF, 0);
    const wchar_t* programs_dir =
        argc > 1 ? argv[1]
                 : L"C:\\Program Files\\Cradle\\CradleCFD2025.2\\Programs_x64";
    SetDllDirectoryW(programs_dir);
    {
        wchar_t old_path[32768] = L"";
        DWORD old_len = GetEnvironmentVariableW(L"PATH", old_path, 32768);
        std::wstring new_path = std::wstring(programs_dir) + L";" + old_path;
        SetEnvironmentVariableW(L"PATH", new_path.c_str());
        printf("PATH set (old_len=%lu)\n", old_len);
    }
    const wchar_t* key_dlls[] = {
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
    for (const wchar_t* name : key_dlls) {
        HMODULE h = LoadLibraryW((std::wstring(programs_dir) + L"\\" + name).c_str());
        g_all.push_back(h);
        printf("load %ls -> %p (err=%lu)\n", name, static_cast<void*>(h),
               GetLastError());
    }
    std::wstring dll_path = std::wstring(programs_dir) + L"\\SCTprime_Bx64.dll";
    g_mod = GetModuleHandleW(L"SCTprime_Bx64.dll");
    if (g_mod == nullptr) {
        printf("LoadLibrary failed: %lu\n", GetLastError());
        return 1;
    }
    printf("loaded %ls\n", dll_path.c_str());

    void* create_set_addr =
        GetProcAddress(g_mod,
                       "?CreateShapeGroupSet@SCTprime@@YA?AVIShapeGroupSet@1@PEB_W@Z");
    CreateShapeGroupSetFn create_set =
        reinterpret_cast<CreateShapeGroupSetFn>(create_set_addr);
    CreateShapeGroupSetRegFn create_set_reg =
        reinterpret_cast<CreateShapeGroupSetRegFn>(create_set_addr);
    GetPtrFn get_ptr_set = reinterpret_cast<GetPtrFn>(
        GetProcAddress(g_mod,
                       "?GetPTR@IShapeGroupSet@SCTprime@@QEAA_KXZ"));
    BoolFn is_valid_set = reinterpret_cast<BoolFn>(
        GetProcAddress(g_mod,
                       "?IsValid@IShapeGroupSet@SCTprime@@QEAA_NXZ"));
    CreateShapeGroupFn create_group = reinterpret_cast<CreateShapeGroupFn>(
        GetProcAddress(g_mod,
                       "?CreateShapeGroup@IShapeGroupSet@SCTprime@@QEAA?AVIShapeGroup@2@PEB_WAEAV?$vector@VISNode@SCTprime@@V?$allocator@VISNode@SCTprime@@@std@@@std@@@Z"));
    GetPtrFn get_ptr_group = reinterpret_cast<GetPtrFn>(
        GetProcAddress(g_mod,
                       "?GetPTR@IShapeGroup@SCTprime@@QEAA_KXZ"));
    BoolFn is_valid_group = reinterpret_cast<BoolFn>(
        GetProcAddress(g_mod,
                       "?IsValid@IShapeGroup@SCTprime@@QEAA_NXZ"));
    BoolFn create_mdl = reinterpret_cast<BoolFn>(
        GetProcAddress(g_mod,
                       "?CreateMDL@IShapeGroup@SCTprime@@QEAA_NXZ"));
    IntFn get_license = reinterpret_cast<IntFn>(
        GetProcAddress(g_mod,
                       "?GetLicenseType@SCTprime@@YA?AW4LICENSE_TYPE@1@XZ"));
    IntFn init_frame = reinterpret_cast<IntFn>(
        GetProcAddress(g_mod, "?InitializeMainFrame@@YAHXZ"));
    OpenCadFileFn open_cad = reinterpret_cast<OpenCadFileFn>(
        GetProcAddress(g_mod,
                       "?OpenCadFile@SCTprime@@YA?AW4ErrorCode@1@PEB_WPEAVISNode@1@@Z"));
    printf("symbols: set=%p getptr_set=%p valid_set=%p "
           "group=%p getptr_group=%p valid_group=%p mdl=%p\n",
           static_cast<void*>(create_set), static_cast<void*>(get_ptr_set),
           static_cast<void*>(is_valid_set), static_cast<void*>(create_group),
           static_cast<void*>(get_ptr_group),
           static_cast<void*>(is_valid_group), static_cast<void*>(create_mdl));

    bool use_sret = true;
    bool do_init = false;
    bool do_libinit = false;
    std::wstring set_name = L"Probe";
    std::wstring cad_path;
    for (int i = 2; i < argc; ++i) {
        if (wcscmp(argv[i], L"--reg") == 0) {
            use_sret = false;
        } else if (wcscmp(argv[i], L"--init") == 0) {
            do_init = true;
        } else if (wcscmp(argv[i], L"--libinit") == 0) {
            do_libinit = true;
        } else if (wcsncmp(argv[i], L"--name=", 7) == 0) {
            set_name = argv[i] + 7;
        } else if (wcsncmp(argv[i], L"--cad=", 6) == 0) {
            cad_path = argv[i] + 6;
        }
    }

    if (create_set == nullptr || get_ptr_set == nullptr ||
        is_valid_set == nullptr || create_group == nullptr ||
        get_ptr_group == nullptr || is_valid_group == nullptr ||
        create_mdl == nullptr) {
        printf("symbol resolution failed\n");
        return 2;
    }

    if (get_license != nullptr) {
        printf("GetLicenseType = %d\n", get_license());
    }
    dump_global();
    if (do_init && init_frame != nullptr) {
        int rc = init_frame();
        printf("InitializeMainFrame = %d\n", rc);
        dump_global();
    }
    if (do_libinit) {
        std::wstring lib_path = std::wstring(programs_dir) + L"\\SCTpreLib_Dx64.dll";
        g_lib = LoadLibraryW(lib_path.c_str());
        printf("SCTpreLib load %ls -> %p (err=%lu)\n", lib_path.c_str(),
               static_cast<void*>(g_lib), GetLastError());
        if (g_lib != nullptr) {
            const wchar_t* names[] = {
                L"InitSCTpreLib1", L"InitSCTpreLib2",
                L"InitSCTpreLib3", L"InitSCTpreLib4",
            };
            for (const wchar_t* n : names) {
                char narrow[64];
                int len = WideCharToMultiByte(CP_ACP, 0, n, -1,
                                              narrow, 64, nullptr, nullptr);
                CIntFn fn = reinterpret_cast<CIntFn>(
                    GetProcAddress(g_lib, narrow));
                if (fn == nullptr) {
                    printf("%ls -> unresolved\n", n);
                    continue;
                }
                int rc = fn();
                printf("%ls -> %d\n", n, rc);
            }
            CIntFn sctpre_init = reinterpret_cast<CIntFn>(
                GetProcAddress(g_lib,
                               "?Initialize@SCTpre@@YA?AW4ErrorCode@1@XZ"));
            if (sctpre_init != nullptr) {
                printf("SCTpre::Initialize -> %d\n", sctpre_init());
            }
            dump_global();
        }
    }
    if (!cad_path.empty() && open_cad != nullptr) {
        ProbeObj node_out{};
        guarded_open_cad(open_cad, cad_path.c_str(), &node_out);
        dump_obj("OpenCadFile node", &node_out);
        dump_global();
    }

    ProbeObj set_obj{};
    ProbeObj* set_ret = nullptr;
    if (use_sret) {
        printf("CreateShapeGroupSet mode=sret name=%ls\n", set_name.c_str());
        guarded_create_set(create_set, &set_obj, set_name.c_str());
        set_ret = &set_obj;
    } else {
        printf("CreateShapeGroupSet mode=reg name=%ls\n", set_name.c_str());
        unsigned __int64 raw = create_set_reg(set_name.c_str());
        printf("  raw RAX = 0x%016llx\n", raw);
        memcpy(set_obj.data, &raw, sizeof(raw));
        set_ret = &set_obj;
    }
    dump_obj("CreateShapeGroupSet", set_ret);
    void* set_this = pick_this(set_obj);
    printf("GetPTR(set@%p) = 0x%016llx\n", set_this,
           get_ptr_set(set_this));
    printf("IsValid(set@%p) = %d\n", set_this, is_valid_set(set_this) ? 1 : 0);

    VecLike nodes{};
    ProbeObj group_obj{};
    guarded_create_group(create_group, set_this, &group_obj, L"ProbeGroup",
                         &nodes);
    dump_obj("CreateShapeGroup", &group_obj);
    void* group_this = pick_this(group_obj);
    printf("GetPTR(group@%p) = 0x%016llx\n", group_this,
           get_ptr_group(group_this));
    printf("IsValid(group@%p) = %d\n", group_this,
           is_valid_group(group_this) ? 1 : 0);

    guarded_create_mdl(create_mdl, group_this);

    FreeLibrary(g_mod);
    return 0;
}
