// scflow_com.cpp - in-proc COM wrapper for the NativeBridge pipeline.
//
// Registers as "pphdecoding.ScflowPipeline" (per-user, HKCU). A VBScript
// executed inside the scFLOWpre host (File -> Execute VBScript) can then
// CreateObject this class; the bridge runs inside the host process where
// the SCTprime document context is already initialized.
//
// The COM layer keeps the 16-byte interface wrappers internally and hands
// small integer handles to VBScript (VBScript cannot hold 64-bit addresses).

#include <windows.h>
#include <objbase.h>
#include <oleauto.h>

#include <array>
#include <cstdio>
#include <string>
#include <unordered_map>

#include "scflow_bridge.h"

// {9F8D2C1A-3B4E-4C5D-8E6F-1A2B3C4D5E6F}
static const CLSID CLSID_ScfPipeline = {
    0x9f8d2c1a, 0x3b4e, 0x4c5d,
    {0x8e, 0x6f, 0x1a, 0x2b, 0x3c, 0x4d, 0x5e, 0x6f}};
static const wchar_t* kProgId = L"pphdecoding.ScflowPipeline";

enum ScfPipelineDispId {
    kDispContextReady = 1,
    kDispCreateShapeGroupSet = 2,
    kDispCreateShapeGroup = 3,
    kDispCreateMDL = 4,
    kDispReleaseHandle = 5,
    kDispLastError = 6,
    kDispLastErrorMessage = 7,
};

static bool wcs_eq(const wchar_t* a, const wchar_t* b) {
    return _wcsicmp(a, b) == 0;
}

static DISPID lookup_disp_id(const wchar_t* name) {
    if (wcs_eq(name, L"ContextReady")) return kDispContextReady;
    if (wcs_eq(name, L"CreateShapeGroupSet")) return kDispCreateShapeGroupSet;
    if (wcs_eq(name, L"CreateShapeGroup")) return kDispCreateShapeGroup;
    if (wcs_eq(name, L"CreateMDL")) return kDispCreateMDL;
    if (wcs_eq(name, L"ReleaseHandle")) return kDispReleaseHandle;
    if (wcs_eq(name, L"LastError")) return kDispLastError;
    if (wcs_eq(name, L"LastErrorMessage")) return kDispLastErrorMessage;
    return DISPID_UNKNOWN;
}

static std::wstring variant_to_string(const VARIANT& v) {
    if (V_VT(&v) == VT_BSTR && V_BSTR(&v) != nullptr) {
        return V_BSTR(&v);
    }
    return L"";
}

static std::wstring error_message_for(int code) {
    switch (code) {
        case SCF_ERR_OK: return L"ok";
        case SCF_ERR_ARG: return L"invalid argument";
        case SCF_ERR_CONTEXT_NOT_READY:
            return L"SCTprime host context is not ready";
        case SCF_ERR_EXCEPTION: return L"access violation inside SCTprime";
        case SCF_ERR_SYMBOL: return L"pipeline symbol not resolved";
        case SCF_ERR_NULL_OBJECT:
            return L"SCTprime returned a null interface object";
        default: return L"unknown error";
    }
}

class ScfPipelineCom : public IDispatch {
  public:
    ScfPipelineCom() : ref_(1), next_id_(1), last_error_(SCF_ERR_OK),
                       initialized_(false) {}

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (ppv == nullptr) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IDispatch) {
            *ppv = static_cast<IDispatch*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override {
        return InterlockedIncrement(&ref_);
    }

    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = InterlockedDecrement(&ref_);
        if (r == 0) delete this;
        return r;
    }

    // IDispatch
    STDMETHODIMP GetTypeInfoCount(UINT* pctinfo) override {
        if (pctinfo == nullptr) return E_POINTER;
        *pctinfo = 0;
        return S_OK;
    }

    STDMETHODIMP GetTypeInfo(UINT, LCID, ITypeInfo** ppTInfo) override {
        if (ppTInfo == nullptr) return E_POINTER;
        *ppTInfo = nullptr;
        return E_NOTIMPL;
    }

    STDMETHODIMP GetIDsOfNames(REFIID, LPOLESTR* rgszNames, UINT cNames,
                               LCID, DISPID* rgDispId) override {
        if (rgszNames == nullptr || rgDispId == nullptr) return E_POINTER;
        for (UINT i = 0; i < cNames; ++i) {
            rgDispId[i] = lookup_disp_id(rgszNames[i]);
            if (rgDispId[i] == DISPID_UNKNOWN) return DISP_E_UNKNOWNNAME;
        }
        return S_OK;
    }

    STDMETHODIMP Invoke(DISPID disp_id, REFIID, LCID, WORD flags,
                        DISPPARAMS* params, VARIANT* result,
                        EXCEPINFO*, UINT*) override {
        if (params == nullptr) return E_POINTER;
        if (result != nullptr) V_VT(result) = VT_EMPTY;
        switch (disp_id) {
            case kDispContextReady: {
                EnsureInitialized();
                int ready = scf_pipeline_context_ready();
                last_error_ = SCF_ERR_OK;
                if (result != nullptr) {
                    V_VT(result) = VT_BOOL;
                    V_BOOL(result) = ready == 1 ? VARIANT_TRUE : VARIANT_FALSE;
                }
                return S_OK;
            }
            case kDispCreateShapeGroupSet: {
                if (params->cArgs < 1) return DISP_E_BADPARAMCOUNT;
                std::wstring name =
                    variant_to_string(params->rgvarg[params->cArgs - 1]);
                long id = DoCreateShapeGroupSet(name);
                if (result != nullptr) {
                    V_VT(result) = VT_I4;
                    V_I4(result) = id;
                }
                return S_OK;
            }
            case kDispCreateShapeGroup: {
                if (params->cArgs < 2) return DISP_E_BADPARAMCOUNT;
                long set_id = V_I4(&params->rgvarg[1]);
                std::wstring name = variant_to_string(params->rgvarg[0]);
                long id = DoCreateShapeGroup(set_id, name);
                if (result != nullptr) {
                    V_VT(result) = VT_I4;
                    V_I4(result) = id;
                }
                return S_OK;
            }
            case kDispCreateMDL: {
                if (params->cArgs < 1) return DISP_E_BADPARAMCOUNT;
                long group_id = V_I4(&params->rgvarg[0]);
                bool ok = DoCreateMDL(group_id);
                if (result != nullptr) {
                    V_VT(result) = VT_BOOL;
                    V_BOOL(result) = ok ? VARIANT_TRUE : VARIANT_FALSE;
                }
                return S_OK;
            }
            case kDispReleaseHandle: {
                if (params->cArgs < 1) return DISP_E_BADPARAMCOUNT;
                long id = V_I4(&params->rgvarg[0]);
                objects_.erase(id);
                return S_OK;
            }
            case kDispLastError: {
                if (result != nullptr) {
                    V_VT(result) = VT_I4;
                    V_I4(result) = last_error_;
                }
                return S_OK;
            }
            case kDispLastErrorMessage: {
                if (result != nullptr) {
                    std::wstring msg = error_message_for(last_error_);
                    V_VT(result) = VT_BSTR;
                    V_BSTR(result) = SysAllocString(msg.c_str());
                }
                return S_OK;
            }
            default:
                return DISP_E_MEMBERNOTFOUND;
        }
    }

  private:
    bool EnsureInitialized() {
        if (initialized_) return true;
        std::wstring dir;
        wchar_t env_buf[1024] = L"";
        if (GetEnvironmentVariableW(L"PPH_PROGRAMS_DIR", env_buf, 1024) > 0) {
            dir = env_buf;
        } else {
            wchar_t exe[MAX_PATH] = L"";
            GetModuleFileNameW(nullptr, exe, MAX_PATH);
            dir = exe;
            size_t pos = dir.find_last_of(L"\\/");
            if (pos != std::wstring::npos) dir = dir.substr(0, pos);
        }
        int loaded = scf_initialize(dir.c_str());
        initialized_ = loaded > 0;
        if (!initialized_) {
            last_error_ = SCF_ERR_ARG;
        }
        return initialized_;
    }

    void SetError(int code) {
        last_error_ = code;
    }

    long DoCreateShapeGroupSet(const std::wstring& name) {
        if (!EnsureInitialized()) return 0;
        std::array<unsigned char, 16> buf{};
        int err = 0;
        if (scf_pipeline_create_shape_group_set(name.c_str(), buf.data(),
                                                &err) != 1) {
            SetError(err);
            return 0;
        }
        long id = next_id_++;
        objects_[id] = buf;
        SetError(SCF_ERR_OK);
        return id;
    }

    long DoCreateShapeGroup(long set_id, const std::wstring& name) {
        auto it = objects_.find(set_id);
        if (it == objects_.end()) {
            SetError(SCF_ERR_ARG);
            return 0;
        }
        std::array<unsigned char, 16> buf{};
        int err = 0;
        unsigned __int64 handle =
            reinterpret_cast<unsigned __int64>(it->second.data());
        if (scf_pipeline_create_shape_group(handle, name.c_str(), buf.data(),
                                             &err) != 1) {
            SetError(err);
            return 0;
        }
        long id = next_id_++;
        objects_[id] = buf;
        SetError(SCF_ERR_OK);
        return id;
    }

    bool DoCreateMDL(long group_id) {
        auto it = objects_.find(group_id);
        if (it == objects_.end()) {
            SetError(SCF_ERR_ARG);
            return false;
        }
        int ok = 0;
        int err = 0;
        unsigned __int64 handle =
            reinterpret_cast<unsigned __int64>(it->second.data());
        if (scf_pipeline_create_mdl(handle, &ok, &err) != 1) {
            SetError(err);
            return false;
        }
        SetError(SCF_ERR_OK);
        return ok != 0;
    }

    LONG ref_;
    long next_id_;
    long last_error_;
    bool initialized_;
    std::unordered_map<long, std::array<unsigned char, 16>> objects_;
};

class ScfPipelineFactory : public IClassFactory {
  public:
    ScfPipelineFactory() : ref_(1) {}

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (ppv == nullptr) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override {
        return InterlockedIncrement(&ref_);
    }

    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = InterlockedDecrement(&ref_);
        if (r == 0) delete this;
        return r;
    }

    STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid,
                                void** ppv) override {
        if (outer != nullptr) return CLASS_E_NOAGGREGATION;
        ScfPipelineCom* obj = new ScfPipelineCom();
        HRESULT hr = obj->QueryInterface(riid, ppv);
        obj->Release();
        return hr;
    }

    STDMETHODIMP LockServer(BOOL) override { return S_OK; }

  private:
    LONG ref_;
};

static std::wstring guid_to_string(const GUID& g) {
    wchar_t buf[64] = L"";
    swprintf_s(buf, L"{%08X-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}",
               g.Data1, g.Data2, g.Data3, g.Data4[0], g.Data4[1], g.Data4[2],
               g.Data4[3], g.Data4[4], g.Data4[5], g.Data4[6], g.Data4[7]);
    return buf;
}

static bool write_reg_string(HKEY root, const std::wstring& path,
                             const std::wstring& name,
                             const std::wstring& value) {
    HKEY key = nullptr;
    if (RegCreateKeyExW(root, path.c_str(), 0, nullptr, 0, KEY_WRITE,
                        nullptr, &key, nullptr) != ERROR_SUCCESS) {
        return false;
    }
    LONG rc = RegSetValueExW(
        key, name.empty() ? nullptr : name.c_str(), 0, REG_SZ,
        reinterpret_cast<const BYTE*>(value.c_str()),
        static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t)));
    RegCloseKey(key);
    return rc == ERROR_SUCCESS;
}

static bool delete_reg_tree(HKEY root, const std::wstring& path) {
    return RegDeleteTreeW(root, path.c_str()) == ERROR_SUCCESS;
}

#pragma comment(linker, "/export:DllGetClassObject,PRIVATE")
#pragma comment(linker, "/export:DllCanUnloadNow,PRIVATE")
#pragma comment(linker, "/export:DllRegisterServer,PRIVATE")
#pragma comment(linker, "/export:DllUnregisterServer,PRIVATE")

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID* ppv) {
    if (ppv == nullptr) return E_POINTER;
    *ppv = nullptr;
    if (!IsEqualCLSID(rclsid, CLSID_ScfPipeline)) {
        return CLASS_E_CLASSNOTAVAILABLE;
    }
    ScfPipelineFactory* factory = new ScfPipelineFactory();
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow(void) {
    return S_FALSE;
}

STDAPI DllRegisterServer(void) {
    wchar_t dll_path[MAX_PATH] = L"";
    HMODULE mod = GetModuleHandleW(L"scflow_bridge.dll");
    GetModuleFileNameW(mod != nullptr ? mod : nullptr, dll_path, MAX_PATH);
    if (dll_path[0] == L'\0') return E_FAIL;

    std::wstring clsid = guid_to_string(CLSID_ScfPipeline);
    std::wstring clsid_root = L"Software\\Classes\\CLSID\\" + clsid;
    std::wstring inproc = clsid_root + L"\\InprocServer32";
    std::wstring progid_root = std::wstring(L"Software\\Classes\\") + kProgId;

    if (!write_reg_string(HKEY_CURRENT_USER, clsid_root, L"", kProgId) ||
        !write_reg_string(HKEY_CURRENT_USER, inproc, L"", dll_path) ||
        !write_reg_string(HKEY_CURRENT_USER, inproc, L"ThreadingModel",
                          L"Apartment") ||
        !write_reg_string(HKEY_CURRENT_USER, progid_root, L"",
                          L"pphdecoding NativeBridge pipeline") ||
        !write_reg_string(HKEY_CURRENT_USER, progid_root + L"\\CLSID", L"",
                          clsid)) {
        return E_FAIL;
    }
    return S_OK;
}

STDAPI DllUnregisterServer(void) {
    std::wstring clsid = guid_to_string(CLSID_ScfPipeline);
    delete_reg_tree(HKEY_CURRENT_USER, L"Software\\Classes\\CLSID\\" + clsid);
    delete_reg_tree(HKEY_CURRENT_USER,
                    std::wstring(L"Software\\Classes\\") + kProgId);
    return S_OK;
}
